# -*- coding: utf-8 -*-
"""
Notificaciones WhatsApp — Tracking de técnicos
================================================
Envía mensajes al grupo/número configurado en cada cambio de estado.

Parámetro de sistema:
  tracking.whatsapp_destino → número o ID de grupo destino
  (cambiar de 51975399303 a 120363039024889968@g.us cuando se verifique)

Archivo: models/ticket_notificaciones_tracking.py
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
        """
        Retorna el número/grupo destino desde parámetros del sistema.
        Cambiar valor cuando se verifique que funciona.
        """
        destino = self.env['ir.config_parameter'].sudo().get_param(
            'tracking.whatsapp_destino', '51975399303'
        )
        return destino.strip()

    # ═══════════════════════════════════════════════════════════════
    #  HELPER: formatear hora Lima
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

    # ═══════════════════════════════════════════════════════════════
    #  NOTIFICACIONES POR ESTADO
    # ═══════════════════════════════════════════════════════════════

    def notificar_en_ruta(self, tickets_grupo=None):
        """
        Notifica al grupo que el técnico está en ruta.
        tickets_grupo: lista de tickets del mismo técnico en ruta (puede ser 1)
        """
        self.ensure_one()
        tickets = tickets_grupo or self
        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id
        agenda = self._fmt_hora(self.agenda)
        hora_salida = self._fmt_hora(self.fecha_en_ruta)

        # Tickets del mismo cliente si hay varios
        nombres_tickets = ' + '.join(t.name for t in tickets)
        direccion = self.direccion_id_r or 'Sin dirección'

        mensaje = (
            f"🚗 *EN RUTA*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {nombres_tickets} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"📍 {direccion}\n"
            f"⏰ Agenda: {agenda} | Salida: {hora_salida}"
        )

        self._enviar_notificacion_tracking(destino, mensaje)

    def notificar_en_sitio(self, tickets_grupo=None):
        """
        Notifica al grupo que el técnico llegó al sitio.
        Si hay varios tickets del mismo cliente, los agrupa en un solo mensaje.
        """
        self.ensure_one()
        tickets = tickets_grupo or self
        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id
        hora_llegada = self._fmt_hora(self.fecha_llegada)
        traslado = self._fmt_min(self.tiempo_traslado_minutos)

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

        self._enviar_notificacion_tracking(destino, mensaje)

    def notificar_en_revision(self, tickets_grupo=None):
        """
        Notifica al grupo que el técnico inició la revisión.
        """
        self.ensure_one()
        tickets = tickets_grupo or self
        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id
        hora_revision = self._fmt_hora(self.fecha_inicio_revision)
        en_sitio = self._fmt_min(
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

        self._enviar_notificacion_tracking(destino, mensaje)

    def notificar_salida_sitio(self, tickets_grupo=None):
        """
        Notifica al grupo que el técnico salió del sitio.
        """
        self.ensure_one()
        tickets = tickets_grupo or self
        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id
        hora_salida = self._fmt_hora(self.fecha_salida_sitio)
        tiempo_sitio = self._fmt_min(self.tiempo_en_sitio_minutos)

        nombres_tickets = ' + '.join(t.name for t in tickets)

        mensaje = (
            f"📤 *SALIÓ DEL SITIO*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {nombres_tickets} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏰ Salida: {hora_salida} | En sitio: {tiempo_sitio}"
        )

        self._enviar_notificacion_tracking(destino, mensaje)

    def notificar_finalizado(self, tickets_grupo=None):
        """
        Notifica al grupo que el ticket fue finalizado.
        """
        self.ensure_one()
        tickets = tickets_grupo or self
        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id
        hora_fin = self._fmt_hora(self.fecha_finalizacion)
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

        # Puntualidad
        if self.fecha_llegada and self.agenda:
            if self.es_puntual:
                mensaje += "\n✅ Puntual"
            elif self.diferencia_puntualidad_minutos > 0:
                mensaje += f"\n⚠️ Tardanza: {self._fmt_min(self.diferencia_puntualidad_minutos)}"
            else:
                mensaje += f"\n✅ Llegó {self._fmt_min(abs(self.diferencia_puntualidad_minutos))} antes"

        self._enviar_notificacion_tracking(destino, mensaje)

    def notificar_siguiente_en_ruta(self, ticket_siguiente):
        """
        Notifica que el técnico va hacia el siguiente servicio del día.
        """
        destino = self._get_destino_tracking()
        tecnico = ticket_siguiente.responsable
        cliente = ticket_siguiente.partner_id
        agenda = self._fmt_hora(ticket_siguiente.agenda)

        mensaje = (
            f"🚗 *HACIA SIGUIENTE SERVICIO*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {ticket_siguiente.name} | Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"📍 {ticket_siguiente.direccion_id_r or 'Sin dirección'}\n"
            f"⏰ Agenda: {agenda}"
        )

        self._enviar_notificacion_tracking(destino, mensaje)

    # ═══════════════════════════════════════════════════════════════
    #  MÉTODO BASE DE ENVÍO
    # ═══════════════════════════════════════════════════════════════

    def _enviar_notificacion_tracking(self, destino, mensaje):
        """
        Envía el mensaje al destino configurado.
        Usa send_whatsapp_message del módulo de mensajes.
        Registra en chatter si hay error.
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