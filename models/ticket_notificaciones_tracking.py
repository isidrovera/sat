# -*- coding: utf-8 -*-
"""
Notificaciones WhatsApp — Tracking de técnicos
================================================
Archivo: models/ticket_notificaciones_tracking.py

Cambios v7:
  • Nuevos métodos para el flujo de retiro pendiente:
      - notificar_retiro_pendiente()     → WhatsApp al técnico con link
      - notificar_motivo_retiro()        → WhatsApp al grupo con el motivo confirmado
      - notificar_retiro_sin_respuesta() → WhatsApp al grupo si el técnico no respondió
      - notificar_retiro_cancelado()     → WhatsApp al grupo si el técnico regresó
  • Todo lo de v6 intacto
"""
import logging
from pytz import timezone as pytz_tz, UTC
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

GRUPO_TRACKING = '120363039024889968@g.us'  # UBICACION TECNICOS — activar después


class TicketNotificacionesTracking(models.Model):
    _inherit = 'ticket.alquiler'

    # ═══════════════════════════════════════════════════════════════
    #  HELPER: obtener destino configurado
    # ═══════════════════════════════════════════════════════════════

    def _get_destino_tracking(self):
        destino = self.env['ir.config_parameter'].sudo().get_param(
            'tracking.whatsapp_destino', GRUPO_TRACKING
        )
        return destino.strip()

    # ═══════════════════════════════════════════════════════════════
    #  HELPERS: formato
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _fmt_hora(dt):
        if not dt:
            return '--'
        try:
            return UTC.localize(dt).astimezone(pytz_tz('America/Lima')).strftime('%H:%M')
        except Exception:
            return dt.strftime('%H:%M')

    @staticmethod
    def _fmt_min(mins):
        if not mins:
            return '--'
        h, m = int(mins // 60), int(mins % 60)
        return f"{h}h {m}min" if h else f"{m}min"

    @staticmethod
    def _fmt_ubicacion(ubicacion_actual):
        """
        Recibe dict {'latitude': x, 'longitude': y} o None.
        Retorna línea con link Google Maps o cadena vacía.
        """
        if not ubicacion_actual:
            return ''
        lat = ubicacion_actual.get('latitude')
        lon = ubicacion_actual.get('longitude')
        if lat is None or lon is None:
            return ''
        maps_url = f"https://maps.google.com/?q={lat},{lon}"
        return f"\n📡 Ubicación actual: {maps_url}"

    # ═══════════════════════════════════════════════════════════════
    #  NOTIFICACIONES POR ESTADO (v6 — sin cambios)
    # ═══════════════════════════════════════════════════════════════

    def notificar_en_ruta(self, tickets_grupo=None, ubicacion_actual=None):
        """
        Notifica al grupo que el técnico está en ruta.
        Una sola llamada por técnico/cliente — el agrupamiento lo hace ticket_tracking.py
        """
        self.ensure_one()
        tickets = tickets_grupo or self
        destino = self._get_destino_tracking()

        tecnico     = self.responsable
        cliente     = self.partner_id
        agenda      = self._fmt_hora(self.agenda)
        hora_salida = self._fmt_hora(self.fecha_en_ruta)
        direccion   = self.direccion_id_r or 'Sin dirección'

        nombres_tickets = ' + '.join(t.name for t in tickets)
        cantidad = len(tickets) if hasattr(tickets, '__len__') else 1

        mensaje = (
            f"🚗 *EN RUTA*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {nombres_tickets} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"📍 {direccion}\n"
            f"⏰ Agenda: {agenda} | Salida: {hora_salida}"
        )

        if cantidad > 1:
            mensaje += f"\n📦 {cantidad} servicios agendados"

        mensaje += self._fmt_ubicacion(ubicacion_actual)

        self._enviar_notificacion_tracking(destino, mensaje)

    def notificar_en_sitio(self, tickets_grupo=None, ubicacion_actual=None):
        """
        Notifica al grupo que el técnico llegó al sitio.
        Una sola llamada por técnico/cliente — el agrupamiento lo hace ticket_tracking.py
        """
        self.ensure_one()
        tickets  = tickets_grupo or self
        destino  = self._get_destino_tracking()

        tecnico      = self.responsable
        cliente      = self.partner_id
        hora_llegada = self._fmt_hora(self.fecha_llegada)
        traslado     = self._fmt_min(self.tiempo_traslado_minutos)

        nombres_tickets = ' + '.join(t.name for t in tickets)
        cantidad = len(tickets) if hasattr(tickets, '__len__') else 1

        mensaje = (
            f"📍 *EN SITIO*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {nombres_tickets} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏰ Llegada: {hora_llegada}"
        )

        if self.tiempo_traslado_minutos:
            mensaje += f" | Traslado: {traslado}"

        if cantidad > 1:
            mensaje += f"\n📦 {cantidad} equipos a revisar"

        mensaje += self._fmt_ubicacion(ubicacion_actual)

        self._enviar_notificacion_tracking(destino, mensaje)

    def notificar_en_revision(self, tickets_grupo=None, ubicacion_actual=None):
        """
        Notifica al grupo que el técnico inició la revisión.
        """
        self.ensure_one()
        tickets = tickets_grupo or self
        destino = self._get_destino_tracking()

        tecnico        = self.responsable
        cliente        = self.partner_id
        hora_revision  = self._fmt_hora(self.fecha_inicio_revision)
        en_sitio       = self._fmt_min(
            (fields.Datetime.now() - self.fecha_llegada).total_seconds() / 60
            if self.fecha_llegada else 0
        )

        nombres_tickets = ' + '.join(t.name for t in tickets)

        mensaje = (
            f"🔧 *EN REVISIÓN*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {nombres_tickets} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏰ Inicio revisión: {hora_revision}"
        )

        if self.fecha_llegada:
            mensaje += f" | En sitio: {en_sitio}"

        mensaje += self._fmt_ubicacion(ubicacion_actual)

        self._enviar_notificacion_tracking(destino, mensaje)

    def notificar_salida_sitio(self, tickets_grupo=None, ubicacion_actual=None):
        """
        Notifica al grupo que el técnico salió del sitio.
        Una sola llamada por técnico/cliente — el agrupamiento lo hace ticket_tracking.py
        """
        self.ensure_one()
        tickets = tickets_grupo or self
        destino = self._get_destino_tracking()

        tecnico      = self.responsable
        cliente      = self.partner_id
        hora_salida  = self._fmt_hora(self.fecha_salida_sitio)
        tiempo_sitio = self._fmt_min(self.tiempo_en_sitio_minutos)

        nombres_tickets = ' + '.join(t.name for t in tickets)
        cantidad = len(tickets) if hasattr(tickets, '__len__') else 1

        mensaje = (
            f"📤 *SALIÓ DEL SITIO*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {nombres_tickets} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏰ Salida: {hora_salida} | En sitio: {tiempo_sitio}"
        )

        if cantidad > 1:
            mensaje += f"\n📦 {cantidad} equipos atendidos"

        mensaje += self._fmt_ubicacion(ubicacion_actual)

        self._enviar_notificacion_tracking(destino, mensaje)

    def notificar_finalizado(self, tickets_grupo=None, ubicacion_actual=None):
        """
        Notifica al grupo que el ticket fue finalizado.
        """
        self.ensure_one()
        tickets = tickets_grupo or self
        destino = self._get_destino_tracking()

        tecnico      = self.responsable
        cliente      = self.partner_id
        hora_fin     = self._fmt_hora(self.fecha_finalizacion)
        tiempo_sitio = self._fmt_min(self.tiempo_en_sitio_minutos)
        tiempo_total = self._fmt_min(self.tiempo_total_atencion_minutos)

        nombres_tickets = ' + '.join(t.name for t in tickets)
        cantidad = len(tickets) if hasattr(tickets, '__len__') else 1

        mensaje = (
            f"✅ *FINALIZADO*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {nombres_tickets} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏰ Fin: {hora_fin} | En sitio: {tiempo_sitio} | Total: {tiempo_total}"
        )

        if cantidad > 1:
            mensaje += f"\n📦 {cantidad} equipos atendidos"

        if self.fecha_llegada and self.agenda:
            if self.es_puntual:
                mensaje += "\n✅ Puntual"
            elif self.diferencia_puntualidad_minutos > 0:
                mensaje += f"\n⚠️ Tardanza: {self._fmt_min(self.diferencia_puntualidad_minutos)}"
            else:
                mensaje += f"\n✅ Llegó {self._fmt_min(abs(self.diferencia_puntualidad_minutos))} antes"

        mensaje += self._fmt_ubicacion(ubicacion_actual)

        self._enviar_notificacion_tracking(destino, mensaje)

    def notificar_siguiente_en_ruta(self, ticket_siguiente, ubicacion_actual=None):
        """
        Notifica que el técnico va hacia el siguiente servicio del día.
        """
        destino = self._get_destino_tracking()
        tecnico = ticket_siguiente.responsable
        cliente = ticket_siguiente.partner_id
        agenda  = self._fmt_hora(ticket_siguiente.agenda)

        mensaje = (
            f"🚗 *HACIA SIGUIENTE SERVICIO*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {ticket_siguiente.name} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"📍 {ticket_siguiente.direccion_id_r or 'Sin dirección'}\n"
            f"⏰ Agenda: {agenda}"
        )

        mensaje += self._fmt_ubicacion(ubicacion_actual)

        self._enviar_notificacion_tracking(destino, mensaje)

    # ═══════════════════════════════════════════════════════════════
    #  NOTIFICACIONES DE RETIRO PENDIENTE (NUEVO v7)
    # ═══════════════════════════════════════════════════════════════

    def notificar_retiro_pendiente(self, link, tiempo_en_sitio=0):
        """
        Envía WhatsApp DIRECTAMENTE AL TÉCNICO (no al grupo)
        con el link para confirmar el motivo del retiro.

        El número del técnico se obtiene de partner_id.mobile del usuario.
        """
        self.ensure_one()
        tecnico = self.responsable
        cliente = self.partner_id

        if not tecnico:
            _logger.warning("[RETIRO-NOTIF] Sin técnico en ticket %s", self.name)
            return

        # Obtener número del técnico
        numero_tecnico = None
        if tecnico.partner_id and tecnico.partner_id.mobile:
            numero_tecnico = tecnico.partner_id.mobile.strip()
        elif tecnico.partner_id and tecnico.partner_id.phone:
            numero_tecnico = tecnico.partner_id.phone.strip()

        # Normalizar: quitar espacios, guiones, paréntesis
        if numero_tecnico:
            import re
            numero_tecnico = re.sub(r'[\s\-\(\)\+]', '', numero_tecnico)
            # Si no tiene código de país (Perú = 51), agregarlo
            # Números peruanos sin código: 9 dígitos empezando en 9
            if len(numero_tecnico) == 9 and numero_tecnico.startswith('9'):
                numero_tecnico = f"51{numero_tecnico}"
            # Si empieza con 0 (formato local con 0), quitar el 0 y agregar 51
            elif len(numero_tecnico) == 10 and numero_tecnico.startswith('0'):
                numero_tecnico = f"51{numero_tecnico[1:]}"

            _logger.info(
                "[RETIRO-NOTIF] Número técnico normalizado: %s", numero_tecnico
            )

        if not numero_tecnico:
            _logger.warning(
                "[RETIRO-NOTIF] Técnico %s sin número móvil", tecnico.name
            )
            # Si no hay número, notificar al grupo para que alguien lo contacte
            self._notificar_retiro_sin_numero(tiempo_en_sitio)
            return

        tiempo_str = self._fmt_min(tiempo_en_sitio) if tiempo_en_sitio else '--'

        mensaje = (
            f"⚠️ *Confirmación requerida*\n"
            f"Hola {tecnico.name.split()[0]}, el sistema detectó que saliste "
            f"de la ubicación del servicio.\n\n"
            f"📋 *{self.name}* | {cliente.name if cliente else 'N/A'}\n"
            f"⏱ Tiempo en sitio: {tiempo_str}\n\n"
            f"Por favor confirma el motivo:\n"
            f"👉 {link}\n\n"
            f"_Tienes 15 minutos para responder._"
        )

        self._enviar_notificacion_tracking(numero_tecnico, mensaje)

        # También notificar al grupo que se está esperando confirmación
        destino_grupo = self._get_destino_tracking()
        msg_grupo = (
            f"⏳ *ESPERANDO CONFIRMACIÓN*\n"
            f"👨‍🔧 {tecnico.name}\n"
            f"📋 {self.name} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏱ Tiempo en sitio: {tiempo_str}\n"
            f"_Se preguntó al técnico el motivo del retiro. Esperando respuesta (15 min)._"
        )
        self._enviar_notificacion_tracking(destino_grupo, msg_grupo)

    def notificar_motivo_retiro(self, motivo, ubicacion_actual=None, tiempo_en_sitio=0):
        """
        Notifica al grupo el motivo de retiro confirmado por el técnico.
        """
        self.ensure_one()
        destino = self._get_destino_tracking()
        tecnico = self.responsable
        cliente = self.partner_id

        tiempo_str = self._fmt_min(tiempo_en_sitio) if tiempo_en_sitio else '--'

        iconos_motivo = {
            'cliente_tarde':     '⏳',
            'sin_autorizacion':  '🚫',
            'ausencia_temporal': '🔄',
        }
        textos_motivo = {
            'cliente_tarde':     'Cliente aún no llega, técnico esperando',
            'sin_autorizacion':  'No autorizaron el ingreso — requiere gestión',
            'ausencia_temporal': 'Salida temporal, regresa a terminar',
        }

        icono = iconos_motivo.get(motivo, '❓')
        texto = textos_motivo.get(motivo, motivo)

        mensaje = (
            f"{icono} *MOTIVO DE RETIRO CONFIRMADO*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {self.name} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏱ Tiempo en sitio: {tiempo_str}\n"
            f"📝 {texto}"
        )

        # Para sin_autorizacion agregar alerta especial
        if motivo == 'sin_autorizacion':
            mensaje += "\n\n⚠️ _Requiere gestión con el cliente para reagendar o autorizar acceso._"

        mensaje += self._fmt_ubicacion(ubicacion_actual)

        self._enviar_notificacion_tracking(destino, mensaje)

    def notificar_retiro_sin_respuesta(self, ubicacion_actual=None, tiempo_en_sitio=0):
        """
        Notifica al grupo que el técnico no respondió la confirmación de retiro.
        """
        self.ensure_one()
        destino = self._get_destino_tracking()
        tecnico = self.responsable
        cliente = self.partner_id

        tiempo_str = self._fmt_min(tiempo_en_sitio) if tiempo_en_sitio else '--'

        mensaje = (
            f"⚠️ *SIN RESPUESTA — RETIRO SIN CONFIRMAR*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {self.name} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏱ Tiempo en sitio: {tiempo_str}\n"
            f"_El técnico no confirmó el motivo de retiro en 15 minutos._\n\n"
        )

        if tiempo_en_sitio >= 60:
            mensaje += "✅ Se asumió finalizado por tiempo en sitio (≥ 60 min)."
        else:
            mensaje += (
                "🔴 Tiempo insuficiente en sitio — verificar con el técnico.\n"
                "_Se recomienda contactarlo directamente._"
            )

        mensaje += self._fmt_ubicacion(ubicacion_actual)

        self._enviar_notificacion_tracking(destino, mensaje)

    def notificar_retiro_cancelado(self):
        """
        Notifica al grupo que el técnico regresó al sitio
        (se canceló la confirmación de retiro pendiente).
        """
        self.ensure_one()
        destino = self._get_destino_tracking()
        tecnico = self.responsable
        cliente = self.partner_id

        mensaje = (
            f"↩️ *TÉCNICO REGRESÓ AL SITIO*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {self.name} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"_El técnico regresó a la ubicación del servicio. Continúa la revisión._"
        )

        self._enviar_notificacion_tracking(destino, mensaje)

    def _notificar_retiro_sin_numero(self, tiempo_en_sitio=0):
        """
        Fallback cuando el técnico no tiene número móvil registrado.
        Notifica al grupo para acción manual.
        """
        destino = self._get_destino_tracking()
        tecnico = self.responsable
        cliente = self.partner_id
        tiempo_str = self._fmt_min(tiempo_en_sitio) if tiempo_en_sitio else '--'

        mensaje = (
            f"⚠️ *RETIRO DETECTADO — SIN NÚMERO TÉCNICO*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {self.name} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏱ Tiempo en sitio: {tiempo_str}\n"
            f"🔴 El técnico no tiene número móvil registrado en el sistema.\n"
            f"_Contactarlo directamente para confirmar el motivo del retiro._"
        )

        self._enviar_notificacion_tracking(destino, mensaje)

    # ═══════════════════════════════════════════════════════════════
    #  MÉTODO BASE DE ENVÍO
    # ═══════════════════════════════════════════════════════════════

    def _enviar_notificacion_tracking(self, destino, mensaje):
        """
        Envía el mensaje al destino configurado.
        Usa send_whatsapp_message del módulo de mensajes.
        """
        try:
            _logger.info(
                "[TRACKING-WA] Enviando a %s: %s",
                destino, mensaje[:80]
            )
            resultado = self.send_whatsapp_message(destino, mensaje)

            if resultado and resultado.get('success'):
                _logger.info("[TRACKING-WA] ✅ Enviado correctamente a %s", destino)
            else:
                error = resultado.get('error', 'Sin detalle') if resultado else 'Sin respuesta'
                _logger.error("[TRACKING-WA] ❌ Error enviando a %s: %s", destino, error)
                self._registrar_evento(
                    f"⚠️ Error al enviar notificación WhatsApp: {error}"
                )

        except Exception as e:
            _logger.exception("[TRACKING-WA] Excepción enviando notificación: %s", e)
            try:
                self._registrar_evento(f"❌ Excepción notificación WhatsApp: {str(e)}")
            except Exception:
                pass