# -*- coding: utf-8 -*-

import json
import logging

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ReparacionesWhatsapp(models.Model):
    _inherit = 'reparaciones.reparaciones'

    responsable_mobile_clean = fields.Char(
        string='Número de celular responsable limpio',
        compute='_compute_responsable_mobile_clean',
        store=True,
    )

    asesora_mobile_clean = fields.Char(
        string='Número de celular asesora limpio',
        compute='_compute_asesora_mobile_clean',
        store=True,
    )

    # -------------------------------------------------------------------------
    # UTILIDADES
    # -------------------------------------------------------------------------

    def _whatsapp_clean_phone(self, phone):
        """
        Limpia un número telefónico para enviarlo al gateway WhatsApp.

        Mantiene la lógica actual:
        - elimina '+'
        - elimina espacios
        - agrega prefijo 51 si no lo tiene
        """
        if not phone:
            return ''

        phone = str(phone).replace('+', '')
        phone = ''.join(phone.split())

        if phone and not phone.startswith('51'):
            phone = '51' + phone

        return phone

    def _get_responsable_phone_raw(self):
        """
        Obtiene el teléfono del responsable sin romper instalaciones existentes.

        Primero intenta usar mobile_phone si existe en res.users,
        porque tu código actual usa responsable_id.mobile_phone.

        Luego usa partner_id.mobile / partner_id.phone como respaldo.
        """
        self.ensure_one()

        responsable = self.responsable_id
        if not responsable:
            return ''

        phone = ''

        if 'mobile_phone' in responsable._fields:
            phone = responsable.mobile_phone

        if not phone and responsable.partner_id:
            phone = responsable.partner_id.mobile or responsable.partner_id.phone

        return phone or ''

    def _get_asesora_phone_raw(self):
        """
        Obtiene el teléfono de la asesora según la lógica actual del modelo.

        Actualmente se usa:
        maquina_id.cliente_id.asesora_id.mobile
        """
        self.ensure_one()

        asesora = self.maquina_id.cliente_id.asesora_id if self.maquina_id and self.maquina_id.cliente_id else False
        if not asesora:
            return ''

        phone = ''
        if 'mobile' in asesora._fields:
            phone = asesora.mobile

        if not phone and 'phone' in asesora._fields:
            phone = asesora.phone

        return phone or ''

    def _safe_text(self, value, default='NA'):
        """
        Devuelve texto seguro para mensajes.
        """
        if not value:
            return default

        if hasattr(value, 'display_name'):
            return value.display_name or default

        return str(value)

    def _get_action_record_url(self):
        """
        Genera URL del formulario de reparación.
        """
        self.ensure_one()

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action_id = self.env.ref('sat.action_reparaciones_window').id
        menu_id = self.env.ref('sat.reparaciones').id

        return (
            f"{base_url}/web#id={self.id}"
            f"&view_type=form"
            f"&model=reparaciones.reparaciones"
            f"&action={action_id}"
            f"&menu_id={menu_id}"
        )

    def _get_gallery_url(self):
        """
        Genera URL de la galería de fotos.
        """
        self.ensure_one()

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/gallery/{self.id}"

    # -------------------------------------------------------------------------
    # COMPUTES
    # -------------------------------------------------------------------------

    @api.depends(
        'responsable_id',
        'responsable_id.partner_id.mobile',
        'responsable_id.partner_id.phone',
    )
    def _compute_responsable_mobile_clean(self):
        for record in self:
            try:
                phone = record._get_responsable_phone_raw()
                record.responsable_mobile_clean = record._whatsapp_clean_phone(phone)
            except Exception as e:
                _logger.warning(
                    "[WHATSAPP REPARACIONES] No se pudo limpiar teléfono del responsable en reparación ID %s: %s",
                    record.id,
                    e,
                )
                record.responsable_mobile_clean = ''

    @api.depends(
        'maquina_id',
        'maquina_id.cliente_id',
        'maquina_id.cliente_id.asesora_id',
        'maquina_id.cliente_id.asesora_id.mobile',
    )
    def _compute_asesora_mobile_clean(self):
        for record in self:
            try:
                phone = record._get_asesora_phone_raw()
                record.asesora_mobile_clean = record._whatsapp_clean_phone(phone)
            except Exception as e:
                _logger.warning(
                    "[WHATSAPP REPARACIONES] No se pudo limpiar teléfono de asesora en reparación ID %s: %s",
                    record.id,
                    e,
                )
                record.asesora_mobile_clean = ''

    # -------------------------------------------------------------------------
    # GATEWAY WHATSAPP
    # -------------------------------------------------------------------------

    def send_whatsapp_message(self, phone, message):
        """
        Envía un mensaje de WhatsApp utilizando la API externa configurada
        en parámetros del sistema.

        Parámetros usados:
        - sat.whatsapp_gateway_base_url
        - sat.whatsapp_gateway_api_key

        Mantiene el endpoint actual:
        /api/send-message
        """
        try:
            ICP = self.env['ir.config_parameter'].sudo()

            base_url = ICP.get_param('sat.whatsapp_gateway_base_url')
            api_key = ICP.get_param('sat.whatsapp_gateway_api_key')

            if not base_url:
                error_msg = "Falta configurar el parámetro sat.whatsapp_gateway_base_url"
                _logger.error("❌ %s", error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                }

            if not api_key:
                error_msg = "Falta configurar el parámetro sat.whatsapp_gateway_api_key"
                _logger.error("❌ %s", error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                }

            base_url = base_url.rstrip('/')
            url = f"{base_url}/api/send-message"

            data = {
                'to': phone,
                'message': message,
            }

            headers = {
                'Content-Type': 'application/json',
                'x-api-key': api_key,
            }

            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=30,
            )

            _logger.info(
                "[WHATSAPP REPARACIONES] Código de estado API: %s",
                response.status_code,
            )
            _logger.info(
                "[WHATSAPP REPARACIONES] Respuesta API: %s",
                response.text,
            )

            try:
                response_json = response.json()
            except json.JSONDecodeError as e:
                error_msg = f"La respuesta no contiene un JSON válido: {str(e)}"
                _logger.error("❌ %s", error_msg)
                _logger.error(
                    "[WHATSAPP REPARACIONES] Respuesta raw API: %s",
                    response.text,
                )
                return {
                    'success': False,
                    'error': error_msg,
                    'status_code': response.status_code,
                    'raw_response': response.text,
                }

            _logger.info(
                "[WHATSAPP REPARACIONES] Respuesta JSON API: %s",
                response_json,
            )

            if response.status_code == 200 and response_json.get('success'):
                _logger.info(
                    "✅ [WHATSAPP REPARACIONES] Mensaje enviado exitosamente a %s",
                    phone,
                )
                return response_json

            error_msg = response_json.get('error', 'Error desconocido')
            _logger.error(
                "❌ [WHATSAPP REPARACIONES] Error en API WhatsApp: %s",
                error_msg,
            )

            return {
                'success': False,
                'error': error_msg,
                'status_code': response.status_code,
                'response': response_json,
            }

        except requests.exceptions.Timeout:
            error_msg = f"Timeout al enviar mensaje a {phone}"
            _logger.error("❌ %s", error_msg)
            return {
                'success': False,
                'error': error_msg,
            }

        except requests.exceptions.RequestException as e:
            error_msg = f"Error de red al enviar mensaje: {str(e)}"
            _logger.exception("❌ %s", error_msg)
            return {
                'success': False,
                'error': error_msg,
            }

        except Exception as e:
            error_msg = f"Error inesperado al enviar WhatsApp: {str(e)}"
            _logger.exception("❌ %s", error_msg)
            return {
                'success': False,
                'error': error_msg,
            }
    def send_whatsapp_media_message(self, phone, attachment, caption=False):
        """
        Envía una imagen/documento por WhatsApp usando el gateway.

        Requiere que el gateway soporte envío media en base64.

        Parámetros:
        - sat.whatsapp_gateway_base_url
        - sat.whatsapp_gateway_api_key
        - sat.whatsapp_gateway_media_endpoint opcional
        Por defecto: /api/send-media
        """
        try:
            ICP = self.env['ir.config_parameter'].sudo()

            base_url = ICP.get_param('sat.whatsapp_gateway_base_url')
            api_key = ICP.get_param('sat.whatsapp_gateway_api_key')
            media_endpoint = ICP.get_param(
                'sat.whatsapp_gateway_media_endpoint',
                '/api/send-media'
            )

            if not base_url:
                return {
                    'success': False,
                    'error': 'Falta configurar sat.whatsapp_gateway_base_url',
                }

            if not api_key:
                return {
                    'success': False,
                    'error': 'Falta configurar sat.whatsapp_gateway_api_key',
                }

            if not attachment or not attachment.datas:
                return {
                    'success': False,
                    'error': 'Adjunto vacío o sin datos',
                }

            base_url = base_url.rstrip('/')
            media_endpoint = media_endpoint if media_endpoint.startswith('/') else '/' + media_endpoint
            url = f"{base_url}{media_endpoint}"

            payload = {
                'to': phone,
                'caption': caption or '',
                'filename': attachment.name or 'foto_avance.jpg',
                'mimetype': attachment.mimetype or 'image/jpeg',
                'mediaBase64': attachment.datas.decode() if isinstance(attachment.datas, bytes) else attachment.datas,
            }

            headers = {
                'Content-Type': 'application/json',
                'x-api-key': api_key,
            }

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=60,
            )

            _logger.info(
                "[WHATSAPP MEDIA] Código de estado API: %s",
                response.status_code,
            )
            _logger.info(
                "[WHATSAPP MEDIA] Respuesta API: %s",
                response.text,
            )

            try:
                response_json = response.json()
            except Exception:
                return {
                    'success': False,
                    'error': 'La respuesta media no contiene JSON válido',
                    'status_code': response.status_code,
                    'raw_response': response.text,
                }

            if response.status_code == 200 and response_json.get('success'):
                return response_json

            return {
                'success': False,
                'error': response_json.get('error', 'Error desconocido enviando media'),
                'status_code': response.status_code,
                'response': response_json,
            }

        except Exception as e:
            _logger.exception("[WHATSAPP MEDIA] Error enviando media: %s", e)
            return {
                'success': False,
                'error': str(e),
            }
    # -------------------------------------------------------------------------
    # SELECTION LABELS
    # -------------------------------------------------------------------------

    def get_selection_labels(self):
        """
        Devuelve etiquetas legibles de todos los campos selection del registro.
        Mantiene tu lógica actual para usarla en plantillas y mensajes.
        """
        self.ensure_one()

        selection_labels = {}

        for field_name, field in self._fields.items():
            if field.type != 'selection':
                continue

            if not hasattr(self, field_name):
                continue

            value = getattr(self, field_name)

            if not value:
                selection_labels[field_name] = 'NA'
                continue

            selection = field.selection
            if callable(selection):
                selection = selection(self)

            label = 'NA'
            for option_value, option_label in selection:
                if option_value == value:
                    label = option_label
                    break

            selection_labels[field_name] = label

        return selection_labels

    # -------------------------------------------------------------------------
    # MENSAJE A TÉCNICO / RESPONSABLE
    # -------------------------------------------------------------------------

    def _build_whatsapp_msg_reparacion_asignada(self, selection_labels):
        """
        Construye el mensaje de WhatsApp para el técnico.
        Mantiene la misma información que tu mensaje actual.
        """
        self.ensure_one()

        record_url = self._get_action_record_url()
        gallery_url = self._get_gallery_url()

        responsable = self.responsable_id.name if self.responsable_id else 'NA'
        cliente = self.cliente_id.name if self.cliente_id else 'NA'

        modelo = 'NA'
        if self.maquina_id and self.maquina_id.name and self.maquina_id.name.name:
            modelo = self.maquina_id.name.name
        elif self.nombre_maquina:
            modelo = self.nombre_maquina

        asesora = self.asesora_id or 'NA'

        msg = f"""Hola;
*{responsable}*

Se te ha asignado la inspección y elaboración del informe de la máquina que se encuentra en el taller.

*REPARACIÓN N°:* {self.name or 'NA'}
*Cliente:* {cliente}
*Importación:* {self.importacion or 'NA'}
*Tipo de equipo:* {self.tipo_machine or 'NA'}
*Marca:* {self.marca or 'NA'}
*Modelo:* {modelo}
*Serie:* {self.serie_id or 'NA'}
*Estado:* {selection_labels.get('estado_id', 'NA')}
*Ubicación:* {selection_labels.get('ubicacion_id', 'NA')}
*Asesora:* {asesora}

*Enlaces:*
- Acceso al registro: {record_url}
- Galería de fotos: {gallery_url}"""

        return msg

    def enviar_mensaje_whatsapp_reparaciones(self):
        """
        Acción actual:
        - obtiene labels de selections,
        - envía correo con plantilla sat.email_template_reparaciones,
        - genera URL del registro y galería,
        - envía WhatsApp al responsable,
        - cambia estado a en_revision,
        - cierra ventana.

        Se mantiene la lógica original.
        """
        self.ensure_one()

        selection_labels = self.get_selection_labels()

        context = dict(self.env.context or {})
        context.update({
            'selection_labels': selection_labels,
        })

        template = self.env.ref('sat.email_template_reparaciones')
        template.with_context(**context).send_mail(self.id, force_send=True)

        msg = self._build_whatsapp_msg_reparacion_asignada(selection_labels)

        if self.responsable_id and self.responsable_mobile_clean:
            phone_number = self.responsable_mobile_clean
            result = self.send_whatsapp_message(phone_number, msg)

            if not result.get('success'):
                self.message_post(
                    body=_(
                        "⚠️ No se pudo enviar WhatsApp al responsable.<br/>"
                        "<b>Número:</b> %(phone)s<br/>"
                        "<b>Error:</b> %(error)s"
                    ) % {
                        'phone': phone_number,
                        'error': result.get('error', 'Error desconocido'),
                    }
                )
        else:
            self.message_post(
                body=_(
                    "⚠️ No se envió WhatsApp al responsable porque no tiene número móvil configurado."
                )
            )

        self.estado_id = 'en_revision'

        return {
            'type': 'ir.actions.act_window_close',
        }

    # -------------------------------------------------------------------------
    # MENSAJE FINAL A ASESORA
    # -------------------------------------------------------------------------

    def _get_estado_legible_safe(self):
        """
        Obtiene estado legible sin romper si el método no existe.
        """
        self.ensure_one()

        if hasattr(self, 'obtener_estado_legible'):
            try:
                return self.obtener_estado_legible() or 'NA'
            except Exception as e:
                _logger.warning(
                    "[WHATSAPP REPARACIONES] No se pudo obtener estado legible para reparación ID %s: %s",
                    self.id,
                    e,
                )

        selection_labels = self.get_selection_labels()
        return selection_labels.get('estado_id', 'NA')

    def _build_whatsapp_msg_finalizacion_asesora(self):
        """
        Construye el mensaje final para la asesora.
        Mantiene la misma información que tu mensaje actual.
        """
        self.ensure_one()

        pdf_url = self.generate_pdf_report_url()
        gallery_url = self._get_gallery_url()

        cliente = self.cliente_id.name if self.cliente_id else 'NA'
        tecnico = self.responsable_id.name if self.responsable_id else 'NA'

        msg = f"""*Reparación Finalizada*

*Cliente:* {cliente}
*Marca:* {self.marca or 'NA'}
*Modelo:* {self.nombre_maquina or 'NA'}
*Serie:* {self.serie_id or 'NA'}
*Contómetro:* {self.contometrok_id or 'NA'}
*Estado:* {self._get_estado_legible_safe()}
*Técnico:* {tecnico}

*Enlaces:*
Reporte: {pdf_url}
Fotos: {gallery_url}
"""

        return msg

    def enviar_mensaje_finalizacion_asesora(self):
        """
        Envía WhatsApp final a asesora.
        Mantiene la lógica original: solo envía si existe asesora_mobile_clean.
        """
        self.ensure_one()

        msg = self._build_whatsapp_msg_finalizacion_asesora()

        if self.asesora_mobile_clean:
            phone_number = self.asesora_mobile_clean
            result = self.send_whatsapp_message(phone_number, msg)

            if not result.get('success'):
                self.message_post(
                    body=_(
                        "⚠️ No se pudo enviar WhatsApp de finalización a la asesora.<br/>"
                        "<b>Número:</b> %(phone)s<br/>"
                        "<b>Error:</b> %(error)s"
                    ) % {
                        'phone': phone_number,
                        'error': result.get('error', 'Error desconocido'),
                    }
                )
        else:
            self.message_post(
                body=_(
                    "⚠️ No se envió WhatsApp de finalización porque la asesora no tiene número móvil configurado."
                )
            )