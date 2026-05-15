# -*- coding: utf-8 -*-

from odoo import _, models, fields, api
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)
import xlwt
from io import BytesIO
import base64
import re
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
import tempfile
import os
import io
import pytz
import qrcode
import requests

class HeredaSatNotificaciones(models.Model):
    _inherit = 'sat.sat'
    _description = 'Hereda Sat Notificaciones'
    

    def _send_whatsapp_message_boot(self, phone, message):
        """Envía WhatsApp usando la API BOOT externa."""
        url = 'https://boot.andessolutioncopiers.com/api/send-message'
        data = {'to': phone, 'message': message}
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': 'wg_fc215093f007df7ff4a32c04c7d8170d11960583e3a1b43a695037f5a627d3e3'
        }

        try:
            resp = requests.post(url, headers=headers, json=data, timeout=30)
            _logger.info("[WA BOOT] status=%s body=%s", resp.status_code, resp.text)

            try:
                js = resp.json()
            except Exception:
                js = {}

            if resp.status_code == 200 and js.get('success'):
                return True

            _logger.warning("[WA BOOT] No success. phone=%s resp=%s", phone, js or resp.text)
            return False

        except requests.exceptions.Timeout:
            _logger.error("[WA BOOT] Timeout enviando a %s", phone)
            return False
        except requests.exceptions.RequestException as e:
            _logger.error("[WA BOOT] Error de red enviando a %s: %s", phone, e)
            return False
        except Exception as e:
            _logger.error("[WA BOOT] Error inesperado: %s", e)
            return False

    def _notify_tecnico_guardar_hoja_contometro_snmp(self, old_val, new_val):
        """
        Se dispara cuando SNMP actualiza el contómetro.
        Envía WhatsApp al técnico responsable (si hay reparación activa en_revision).
        Anti-spam: no reenvía si ya notificó el mismo new_val.
        """
        self.ensure_one()

        # Anti-spam por valor notificado
        last_sent = (self.last_snmp_counter_whatsapp or '').strip()
        try:
            if last_sent and int(last_sent) == int(new_val):
                _logger.debug("[SNMP->WA] Ya notificado new_val=%s para sat.sat ID=%s", new_val, self.id)
                return False
        except Exception:
            pass

        rep = self._get_reparacion_activa_para_alerta_snmp()
        if not rep:
            _logger.debug("[SNMP->WA] No hay reparación activa en_revision para sat.sat ID=%s", self.id)
            return False

        phone = (rep.responsable_mobile_clean or '').strip()
        if not phone:
            _logger.warning("[SNMP->WA] Reparación %s sin responsable_mobile_clean", rep.id)
            return False

        # URL del equipo (si tienes generate_record_url en sat.sat)
        try:
            url_equipo = self.generate_record_url(self)
        except Exception:
            url_equipo = ""

        modelo_txt = self.name.name if self.name and hasattr(self.name, 'name') else (self.name or 'NA')

        msg = (
            f"📌 *ALERTA SNMP (Contómetro actualizado)*\n"
            f"Equipo: *{modelo_txt}*\n"
            f"Serie: *{self.serie_id or 'NA'}*\n"
            f"Contómetro SNMP: *{old_val:,} → {new_val:,}*\n\n"
            f"✅ *Acción requerida:*\n"
            f"Guarda la *hoja / sustento del contómetro* enviado por el proveedor.\n\n"
            f"🔗 Odoo: {url_equipo}"
        )

        ok = self._send_whatsapp_message_boot(phone, msg)

        if ok:
            self.sudo().write({
                'last_snmp_counter_whatsapp': str(int(new_val)),
                'last_snmp_whatsapp_at': fields.Datetime.now(),
            })

            # Registrar nota en chatter de la reparación (opcional pero recomendado)
            try:
                rep.message_post(
                    body=(
                        "📩 WhatsApp enviado al técnico por actualización SNMP del contómetro.<br/>"
                        f"Anterior: <b>{old_val:,}</b> → Nuevo: <b>{new_val:,}</b>"
                    ),
                    subtype_xmlid='mail.mt_note'
                )
            except Exception as e:
                _logger.warning("No se pudo registrar message_post en reparación %s: %s", rep.id, e)

        return ok

    def enviar_mensaje_problema_asesora(self):
        """Envía mensaje WhatsApp (si hay cliente y asesora) y siempre intenta enviar correo electrónico."""
        
        url = self.generate_record_url(self)
        estado_actual = dict(self._fields['estado_ventas_id'].selection).get(self.estado_ventas_id)

        mensaje = f"""*¡Atención! Máquina con problemas*
    *Cliente:* {self.cliente_id.name if self.cliente_id else 'No asignado'}
    *Marca:* {self.marca}
    *Modelo:* {self.name.name}
    *Serie:* {self.serie_id}
    *Estado:* {estado_actual}
    *Descripción:* {self.descripcion or 'Sin descripción'}

    Para ver más detalles, ingrese al siguiente enlace:
    {url}"""

        # 🔥 CAMBIO CRÍTICO: Usar la API BOOT funcional
        if self.cliente_id and self.asesora_mobile_clean:
            try:
                
                resultado = self._send_whatsapp_message_boot(self.asesora_mobile_clean, mensaje)
                
                if resultado:
                    self.message_post(
                        body=f"✅ WhatsApp enviado exitosamente a la asesora {self.cliente_id.asesora_id.name}",
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )
                    _logger.info(f"WhatsApp enviado exitosamente a {self.asesora_mobile_clean} para ID {self.id}")
                else:
                    self.message_post(
                        body=f"⚠️ No se pudo enviar WhatsApp a la asesora {self.cliente_id.asesora_id.name}",
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )
                    _logger.warning(f"Fallo al enviar WhatsApp a {self.asesora_mobile_clean} para ID {self.id}")
                    
            except Exception as e:
                _logger.error(f"Error al enviar WhatsApp para ID {self.id}: {str(e)}", exc_info=True)
                self.message_post(
                    body=f"❌ Error al enviar WhatsApp: {str(e)}",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
        else:
            _logger.warning(
                f"No se envió WhatsApp para ID {self.id}: "
                f"cliente={bool(self.cliente_id)}, asesora_mobile={bool(self.asesora_mobile_clean)}"
            )

        # Enviar correo electrónico siempre
        template = self.env.ref('sat.email_template_maquinas_problema', raise_if_not_found=False)
        if template:
            try:
                template.sudo().send_mail(self.id, force_send=True)
                self.message_post(
                    body="✅ Correo electrónico enviado notificando problema en la máquina.",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
            except Exception as e:
                _logger.error(f"Error al enviar correo electrónico para ID {self.id}: {str(e)}")
        else:
            _logger.warning(f"No se encontró la plantilla de correo para ID {self.id}")

        return True

    def enviar_notificacion_disponibilidad(self):
        """Envía notificación de disponibilidad cuando se resuelve un problema de la máquina."""
        # Generar la URL del registro
        url = self.generate_record_url(self)
        estado_actual = dict(self._fields['estado_ventas_id'].selection).get(self.estado_ventas_id)

        # Construcción del mensaje de WhatsApp
        mensaje = f"""*¡Notificación! Problema resuelto en la máquina*
    *Cliente:* {self.cliente_id.name if self.cliente_id else 'No asignado'}
    *Marca:* {self.marca}
    *Modelo:* {self.name.name}
    *Serie:* {self.serie_id}
    *Estado:* {estado_actual}

    ✅ La máquina ya está disponible nuevamente.

    Para ver más detalles, ingrese al siguiente enlace:
    {url}"""

        # 🔥 CAMBIO: Enviar mensaje por WhatsApp usando API BOOT
        if self.cliente_id and self.asesora_mobile_clean:
            try:
                resultado = self._send_whatsapp_message_boot(self.asesora_mobile_clean, mensaje)
                
                if resultado:
                    self.message_post(
                        body=f"✅ WhatsApp enviado exitosamente a la asesora {self.cliente_id.asesora_id.name} notificando que se corrigió el problema.",
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )
                    _logger.info(f"WhatsApp de disponibilidad enviado exitosamente a {self.asesora_mobile_clean} para ID {self.id}")
                else:
                    self.message_post(
                        body=f"⚠️ No se pudo enviar WhatsApp a la asesora {self.cliente_id.asesora_id.name}",
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )
                    _logger.warning(f"Fallo al enviar WhatsApp de disponibilidad a {self.asesora_mobile_clean} para ID {self.id}")
                    
            except Exception as e:
                _logger.error(f"Error al enviar WhatsApp de disponibilidad para ID {self.id}: {str(e)}", exc_info=True)
                self.message_post(
                    body=f"❌ Error al enviar WhatsApp: {str(e)}",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
        else:
            _logger.warning(
                f"No se envió WhatsApp de disponibilidad para ID {self.id}: "
                f"cliente={bool(self.cliente_id)}, asesora_mobile={bool(self.asesora_mobile_clean)}"
            )

        # Enviar correo electrónico siempre, incluso si no hay cliente
        template = self.env.ref('sat.email_template_maquinas_disponible', raise_if_not_found=False)
        if template:
            try:
                template.sudo().send_mail(self.id, force_send=True)
                self.message_post(
                    body="✅ Correo electrónico enviado indicando que se corrigió el problema.",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
                _logger.info(f"Correo de disponibilidad enviado para ID {self.id}")
            except Exception as e:
                _logger.error(f"Error al enviar correo electrónico de disponibilidad para ID {self.id}: {str(e)}")
                self.message_post(
                    body=f"❌ Error al enviar correo electrónico: {str(e)}",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
        else:
            _logger.warning(f"No se encontró la plantilla de correo 'sat.email_template_maquinas_disponible' para ID {self.id}")

        return True
    def enviar_mensaje_transportistas(self):
        """Envía notificación a transportistas para traer la máquina."""
        transportista_numeros = ['51924894872']
        
        # Obtener el display name de la ubicación
        ubicacion_display = dict(self._fields['ubicacion_id'].selection).get(self.ubicacion_id, self.ubicacion_id)
        
        mensaje = f"""*Solicitud de traslado de máquina*

    📦 *Detalles del equipo:*
    - Modelo: *{self.name.name}*
    - Serie: *{self.serie_id}*
    - Ubicación actual: *{ubicacion_display}*

    📍 *Destino:* Primer piso

    Para registrar el cambio de ubicación cuando llegue la máquina, 
    haga clic en el siguiente enlace:
    {self.crear_url_cambio_ubicacion(self)}"""

        _logger.info(f"Enviando mensaje a transportistas para máquina {self.serie_id}")

        exito_total = True
        for numero in transportista_numeros:
            try:
                # 🔥 CAMBIO: Usar API BOOT
                resultado = self._send_whatsapp_message_boot(numero, mensaje)
                
                if resultado:
                    _logger.info(f"✅ Mensaje enviado exitosamente a transportista {numero} para máquina {self.serie_id}")
                else:
                    _logger.warning(f"⚠️ Fallo al enviar mensaje a transportista {numero} para máquina {self.serie_id}")
                    exito_total = False
                    
            except Exception as e:
                _logger.error(f"❌ Error al enviar mensaje a transportista {numero} para máquina {self.serie_id}: {e}", exc_info=True)
                exito_total = False
        
        # Registrar en el chatter
        if exito_total:
            self.message_post(
                body=f"✅ Notificación enviada a transportistas para traer el equipo desde {ubicacion_display}.",
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
        else:
            self.message_post(
                body=f"⚠️ Hubo problemas al enviar la notificación a algunos transportistas. Revisar logs.",
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
        
        return exito_total