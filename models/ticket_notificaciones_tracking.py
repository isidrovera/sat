
# -*- coding: utf-8 -*-
"""
Notificaciones WhatsApp — Tracking de técnicos
Archivo: models/ticket_notificaciones_tracking.py

Odoo 19

La salida física del cliente y la finalización
administrativa del ticket son independientes.
"""

import logging
import re

from pytz import timezone as pytz_tz, UTC
from odoo import models, fields

_logger = logging.getLogger(__name__)

GRUPO_TRACKING = '120363039024889968@g.us'


class TicketNotificacionesTracking(models.Model):
    _inherit = 'ticket.alquiler'

    # ==========================================================
    # CONFIGURACIÓN
    # ==========================================================

    def _get_destino_tracking(self):
        destino = self.env['ir.config_parameter'].sudo().get_param(
            'tracking.whatsapp_destino',
            GRUPO_TRACKING,
        )
        return (destino or '').strip()

    # ==========================================================
    # FORMATO DE FECHAS, DURACIONES Y UBICACIÓN
    # ==========================================================

    @staticmethod
    def _fmt_hora(dt):
        if not dt:
            return '--'

        try:
            fecha = fields.Datetime.to_datetime(dt)
            if fecha.tzinfo is None:
                fecha = UTC.localize(fecha)

            return fecha.astimezone(
                pytz_tz('America/Lima')
            ).strftime('%H:%M')

        except Exception:
            _logger.exception(
                "[TRACKING-WA] Error formateando fecha"
            )
            return '--'

    @staticmethod
    def _fmt_min(mins):
        if mins is None or mins is False:
            return '--'

        try:
            minutos = float(mins)
            if minutos < 0:
                return '--'

            total = int(minutos)
            horas, restantes = divmod(total, 60)

            if horas:
                return f"{horas}h {restantes}min"

            return f"{restantes}min"

        except (ValueError, TypeError):
            return '--'

    @staticmethod
    def _fmt_ubicacion(ubicacion_actual):
        if not ubicacion_actual:
            return ''

        lat = ubicacion_actual.get('latitude')
        lon = ubicacion_actual.get('longitude')

        if lat is None or lon is None:
            return ''

        try:
            lat = float(lat)
            lon = float(lon)

            if not (-90 <= lat <= 90):
                return ''

            if not (-180 <= lon <= 180):
                return ''

        except (ValueError, TypeError):
            return ''

        maps_url = (
            f"https://maps.google.com/?q={lat},{lon}"
        )

        return f"\n📡 Ubicación GPS: {maps_url}"

    # ==========================================================
    # TICKETS AGRUPADOS
    # ==========================================================

    def _tracking_tickets_grupo(self, tickets_grupo=None):
        self.ensure_one()

        if tickets_grupo is None:
            return self

        if not tickets_grupo:
            return self

        return tickets_grupo

    def _tracking_nombres_tickets(self, tickets):
        return ' + '.join(
            ticket.name or str(ticket.id)
            for ticket in tickets
        )

    # ==========================================================
    # NOTIFICACIÓN EN RUTA
    # ==========================================================

    def notificar_en_ruta(
        self,
        tickets_grupo=None,
        ubicacion_actual=None,
    ):
        self.ensure_one()

        tickets = self._tracking_tickets_grupo(
            tickets_grupo
        )

        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id

        agenda = self._fmt_hora(self.agenda)
        hora_ruta = self._fmt_hora(self.fecha_en_ruta)

        direccion = (
            self.direccion_id_r or 'Sin dirección'
        )

        nombres = self._tracking_nombres_tickets(
            tickets
        )

        mensaje = (
            "🚗 *EN RUTA*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {nombres}\n"
            f"🏢 Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"📍 {direccion}\n"
            f"⏰ Agenda: {agenda}\n"
            f"🚗 Inicio de ruta: {hora_ruta}"
        )

        if len(tickets) > 1:
            mensaje += (
                f"\n📦 {len(tickets)} servicios "
                "programados en la visita"
            )

        mensaje += self._fmt_ubicacion(
            ubicacion_actual
        )

        return self._enviar_notificacion_tracking(
            destino,
            mensaje,
        )

    # ==========================================================
    # NOTIFICACIÓN LLEGADA AL CLIENTE
    # ==========================================================

    def notificar_en_sitio(
        self,
        tickets_grupo=None,
        ubicacion_actual=None,
    ):
        self.ensure_one()

        tickets = self._tracking_tickets_grupo(
            tickets_grupo
        )

        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id

        hora_llegada = self._fmt_hora(
            self.fecha_llegada
        )

        traslado = self._fmt_min(
            self.tiempo_traslado_minutos
        )

        nombres = self._tracking_nombres_tickets(
            tickets
        )

        mensaje = (
            "📍 *LLEGADA AL CLIENTE*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {nombres}\n"
            f"🏢 Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏰ Llegada: {hora_llegada}"
        )

        if (
            self.fecha_en_ruta
            and self.fecha_llegada
            and self.tiempo_traslado_minutos >= 0
        ):
            mensaje += (
                f"\n🚗 Tiempo de traslado: {traslado}"
            )

        if len(tickets) > 1:
            mensaje += (
                f"\n📦 {len(tickets)} equipos "
                "programados"
            )

        mensaje += self._fmt_ubicacion(
            ubicacion_actual
        )

        return self._enviar_notificacion_tracking(
            destino,
            mensaje,
        )

    # ==========================================================
    # NOTIFICACIÓN INICIO DE REVISIÓN
    # ==========================================================

    def notificar_en_revision(
        self,
        tickets_grupo=None,
        ubicacion_actual=None,
    ):
        self.ensure_one()

        tickets = self._tracking_tickets_grupo(
            tickets_grupo
        )

        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id

        hora_revision = self._fmt_hora(
            self.fecha_inicio_revision
        )

        nombres = self._tracking_nombres_tickets(
            tickets
        )

        mensaje = (
            "🔧 *EN REVISIÓN*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {nombres}\n"
            f"🏢 Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏰ Inicio de revisión: {hora_revision}"
        )

        # No calcular ni suponer una hora de inicio.
        # La fecha debe provenir del flujo de tracking.

        mensaje += self._fmt_ubicacion(
            ubicacion_actual
        )

        return self._enviar_notificacion_tracking(
            destino,
            mensaje,
        )

    # ==========================================================
    # NOTIFICACIÓN SALIDA FÍSICA DEL CLIENTE
    # ==========================================================

    def notificar_salida_sitio(
        self,
        tickets_grupo=None,
        ubicacion_actual=None,
    ):
        """
        Comunica exclusivamente la salida física.

        No finaliza tickets.
        No modifica estado.
        No ejecuta action_finalizar().
        """
        self.ensure_one()

        tickets = self._tracking_tickets_grupo(
            tickets_grupo
        )

        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id

        hora_salida = self._fmt_hora(
            self.fecha_salida_sitio
        )

        nombres = self._tracking_nombres_tickets(
            tickets
        )

        mensaje = (
            "📤 *SALIDA FÍSICA DEL CLIENTE*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {nombres}\n"
            f"🏢 Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏰ Salida: {hora_salida}"
        )

        if (
            self.fecha_llegada
            and self.fecha_salida_sitio
            and self.fecha_salida_sitio >= self.fecha_llegada
        ):
            tiempo_sitio = self._fmt_min(
                self.tiempo_en_sitio_minutos
            )

            mensaje += (
                f"\n⏱ Permanencia física: {tiempo_sitio}"
            )

        if len(tickets) > 1:
            mensaje += (
                f"\n📦 {len(tickets)} tickets "
                "de la visita"
            )

        mensaje += (
            "\n\nℹ️ La salida física no significa "
            "que los tickets estén finalizados."
        )

        mensaje += self._fmt_ubicacion(
            ubicacion_actual
        )

        return self._enviar_notificacion_tracking(
            destino,
            mensaje,
        )

    # ==========================================================
    # FINALIZACIÓN ADMINISTRATIVA DEL TICKET
    # ==========================================================

    def notificar_finalizado(
        self,
        tickets_grupo=None,
        ubicacion_actual=None,
    ):
        """
        Comunica únicamente tickets finalizados.

        No registra salida física.
        No supone que el técnico salió.
        """
        self.ensure_one()

        tickets = self._tracking_tickets_grupo(
            tickets_grupo
        )

        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id

        hora_fin = self._fmt_hora(
            self.fecha_finalizacion
        )

        nombres = self._tracking_nombres_tickets(
            tickets
        )

        mensaje = (
            "✅ *TICKET FINALIZADO*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {nombres}\n"
            f"🏢 Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏰ Finalización: {hora_fin}"
        )

        if len(tickets) > 1:
            mensaje += (
                f"\n📦 {len(tickets)} tickets "
                "incluidos en la notificación"
            )

        # Solo informar la puntualidad cuando los
        # datos de llegada y agenda estén disponibles.
        if self.fecha_llegada and self.agenda:
            diferencia = (
                self.fecha_llegada - self.agenda
            ).total_seconds() / 60

            if diferencia > 15:
                mensaje += (
                    "\n⚠️ Llegada posterior a la agenda: "
                    f"{self._fmt_min(diferencia)}"
                )
            elif diferencia < 0:
                mensaje += (
                    "\nℹ️ Llegada antes de la agenda: "
                    f"{self._fmt_min(abs(diferencia))}"
                )
            else:
                mensaje += "\n✅ Llegada dentro del margen"

        mensaje += self._fmt_ubicacion(
            ubicacion_actual
        )

        return self._enviar_notificacion_tracking(
            destino,
            mensaje,
        )

    # ==========================================================
    # SIGUIENTE SERVICIO EN RUTA
    # ==========================================================

    def notificar_siguiente_en_ruta(
        self,
        ticket_siguiente,
        ubicacion_actual=None,
    ):
        """
        Solamente comunica un desplazamiento ya validado.

        La autorización de iniciar la siguiente ruta
        corresponde al modelo de visitas/tracking GPS.
        """
        self.ensure_one()

        destino = self._get_destino_tracking()

        tecnico = ticket_siguiente.responsable
        cliente = ticket_siguiente.partner_id

        agenda = self._fmt_hora(
            ticket_siguiente.agenda
        )

        hora_ruta = self._fmt_hora(
            ticket_siguiente.fecha_en_ruta
        )

        mensaje = (
            "🚗 *HACIA SIGUIENTE SERVICIO*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {ticket_siguiente.name}\n"
            f"🏢 Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"📍 {ticket_siguiente.direccion_id_r or 'Sin dirección'}\n"
            f"⏰ Agenda: {agenda}\n"
            f"🚗 Inicio de ruta: {hora_ruta}"
        )

        mensaje += self._fmt_ubicacion(
            ubicacion_actual
        )

        return self._enviar_notificacion_tracking(
            destino,
            mensaje,
        )

    # ==========================================================
    # RETIRO PENDIENTE DE CONFIRMACIÓN
    # ==========================================================

    def notificar_retiro_pendiente(
        self,
        link,
        tiempo_en_sitio=0,
    ):
        """
        Solicita al técnico confirmar el motivo
        de retiro mediante token.

        No registra salida automáticamente.
        No finaliza el ticket.
        """
        self.ensure_one()

        tecnico = self.responsable
        cliente = self.partner_id

        if not tecnico:
            _logger.warning(
                "[RETIRO-NOTIF] Ticket %s sin técnico",
                self.name,
            )
            return False

        partner = tecnico.partner_id

        numero_tecnico = ''

        if partner:
            for campo in ('mobile', 'phone'):
                if campo not in partner._fields:
                    continue

                valor = partner[campo]

                if valor and str(valor).strip():
                    numero_tecnico = str(valor).strip()
                    break

        numero_tecnico = re.sub(
            r'\D',
            '',
            numero_tecnico,
        )

        if (
            len(numero_tecnico) == 9
            and numero_tecnico.startswith('9')
        ):
            numero_tecnico = '51' + numero_tecnico

        elif (
            len(numero_tecnico) == 10
            and numero_tecnico.startswith('09')
        ):
            numero_tecnico = '51' + numero_tecnico[1:]

        elif (
            numero_tecnico.startswith('0051')
            and len(numero_tecnico) == 13
        ):
            numero_tecnico = numero_tecnico[2:]

        if not re.fullmatch(
            r'519\d{8}',
            numero_tecnico,
        ):
            _logger.warning(
                "[RETIRO-NOTIF] Técnico %s sin "
                "celular peruano válido. Ticket %s",
                tecnico.name,
                self.name,
            )

            self._notificar_retiro_sin_numero(
                tiempo_en_sitio
            )
            return False

        tiempo_str = self._fmt_min(
            tiempo_en_sitio
        )

        mensaje = (
            "⚠️ *CONFIRMACIÓN DE RETIRO*\n"
            f"Hola {(tecnico.name or 'Técnico').split()[0]}, "
            "el sistema detectó una posible salida "
            "de la ubicación del servicio.\n\n"
            f"📋 {self.name}\n"
            f"🏢 {cliente.name if cliente else 'N/A'}\n"
            f"⏱ Tiempo registrado: {tiempo_str}\n\n"
            "Confirma el motivo de tu retiro:\n"
            f"👉 {link}\n\n"
            "_Tienes 15 minutos para responder._"
        )

        enviado = self._enviar_notificacion_tracking(
            numero_tecnico,
            mensaje,
        )

        if not enviado:
            _logger.error(
                "[RETIRO-NOTIF] No se pudo solicitar "
                "confirmación al técnico. Ticket %s",
                self.name,
            )
            return False

        destino_grupo = self._get_destino_tracking()

        mensaje_grupo = (
            "⏳ *RETIRO PENDIENTE DE CONFIRMACIÓN*\n"
            f"👨‍🔧 {tecnico.name}\n"
            f"📋 {self.name}\n"
            f"🏢 Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏱ Tiempo registrado: {tiempo_str}\n"
            "Se solicitó confirmar el motivo del retiro.\n"
            "_Pendiente de respuesta del técnico._"
        )

        self._enviar_notificacion_tracking(
            destino_grupo,
            mensaje_grupo,
        )

        return True

    # ==========================================================
    # MOTIVO DE RETIRO CONFIRMADO
    # ==========================================================

    def notificar_motivo_retiro(
        self,
        motivo,
        ubicacion_actual=None,
        tiempo_en_sitio=0,
    ):
        self.ensure_one()

        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id

        tiempo_str = self._fmt_min(
            tiempo_en_sitio
        )

        iconos = {
            'cliente_tarde': '⏳',
            'sin_autorizacion': '🚫',
            'ausencia_temporal': '🔄',
        }

        textos = {
            'cliente_tarde': (
                'Cliente aún no llega, técnico esperando'
            ),
            'sin_autorizacion': (
                'No autorizaron el ingreso'
            ),
            'ausencia_temporal': (
                'Salida temporal, regresa a terminar'
            ),
        }

        icono = iconos.get(motivo, '❓')
        texto = textos.get(motivo, motivo)

        mensaje = (
            f"{icono} *MOTIVO DE RETIRO CONFIRMADO*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {self.name}\n"
            f"🏢 Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏱ Tiempo registrado: {tiempo_str}\n"
            f"📝 {texto}"
        )

        if motivo == 'sin_autorizacion':
            mensaje += (
                "\n\n⚠️ Requiere gestión con el cliente "
                "para autorizar el ingreso o reagendar."
            )

        if motivo == 'ausencia_temporal':
            mensaje += (
                "\n\nℹ️ Retiro temporal. "
                "La visita todavía requiere seguimiento."
            )

        mensaje += self._fmt_ubicacion(
            ubicacion_actual
        )

        return self._enviar_notificacion_tracking(
            destino,
            mensaje,
        )

    # ==========================================================
    # RETIRO SIN RESPUESTA
    # ==========================================================

    def notificar_retiro_sin_respuesta(
        self,
        ubicacion_actual=None,
        tiempo_en_sitio=0,
    ):
        """
        No asumir salida física ni finalización
        solamente por el tiempo transcurrido.
        """
        self.ensure_one()

        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id

        tiempo_str = self._fmt_min(
            tiempo_en_sitio
        )

        mensaje = (
            "⚠️ *RETIRO SIN CONFIRMAR*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {self.name}\n"
            f"🏢 Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏱ Tiempo registrado: {tiempo_str}\n\n"
            "El técnico no respondió la confirmación "
            "de retiro dentro del plazo establecido.\n\n"
            "🔴 Contactar al técnico y verificar "
            "la evidencia GPS.\n"
            "_No se supone finalización ni salida confirmada._"
        )

        mensaje += self._fmt_ubicacion(
            ubicacion_actual
        )

        return self._enviar_notificacion_tracking(
            destino,
            mensaje,
        )

    # ==========================================================
    # REGRESO AL CLIENTE
    # ==========================================================

    def notificar_retiro_cancelado(self):
        self.ensure_one()

        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id

        mensaje = (
            "↩️ *REGRESO AL CLIENTE*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {self.name}\n"
            f"🏢 Cliente: {cliente.name if cliente else 'N/A'}\n\n"
            "Se detectó el regreso del técnico "
            "a la ubicación del servicio.\n"
            "La confirmación de retiro pendiente "
            "fue cancelada."
        )

        return self._enviar_notificacion_tracking(
            destino,
            mensaje,
        )

    # ==========================================================
    # TÉCNICO SIN NÚMERO MÓVIL
    # ==========================================================

    def _notificar_retiro_sin_numero(
        self,
        tiempo_en_sitio=0,
    ):
        self.ensure_one()

        destino = self._get_destino_tracking()

        tecnico = self.responsable
        cliente = self.partner_id

        tiempo_str = self._fmt_min(
            tiempo_en_sitio
        )

        mensaje = (
            "⚠️ *RETIRO DETECTADO — SIN CELULAR*\n"
            f"👨‍🔧 {tecnico.name if tecnico else 'N/A'}\n"
            f"📋 {self.name}\n"
            f"🏢 Cliente: {cliente.name if cliente else 'N/A'}\n"
            f"⏱ Tiempo registrado: {tiempo_str}\n\n"
            "El técnico no tiene un celular válido "
            "registrado para recibir el enlace.\n"
            "_Administración debe verificar el retiro._"
        )

        return self._enviar_notificacion_tracking(
            destino,
            mensaje,
        )

    # ==========================================================
    # ENVÍO CENTRALIZADO WHATSAPP
    # ==========================================================

    def _enviar_notificacion_tracking(
        self,
        destino,
        mensaje,
    ):
        """
        Envía una solicitud al proveedor WhatsApp.

        True indica que la integración reportó
        success=True.

        No confirma entrega al dispositivo
        ni lectura del mensaje.
        """
        self.ensure_one()

        if not destino:
            _logger.warning(
                "[TRACKING-WA] Destino vacío. Ticket %s",
                self.name,
            )
            return False

        try:
            _logger.info(
                "[TRACKING-WA] Solicitando envío "
                "ticket=%s destino=%s",
                self.name,
                destino,
            )

            resultado = self.send_whatsapp_message(
                destino,
                mensaje,
            )

            if (
                isinstance(resultado, dict)
                and resultado.get('success') is True
            ):
                _logger.info(
                    "[TRACKING-WA] Solicitud aceptada. "
                    "Ticket=%s destino=%s",
                    self.name,
                    destino,
                )
                return True

            if isinstance(resultado, dict):
                error = resultado.get(
                    'error',
                    'Proveedor no confirmó aceptación',
                )
            else:
                error = (
                    f"Respuesta no verificable: "
                    f"{type(resultado).__name__}"
                )

            _logger.error(
                "[TRACKING-WA] Error ticket=%s "
                "destino=%s detalle=%s",
                self.name,
                destino,
                error,
            )

            self._registrar_error_notificacion_tracking(
                error
            )

            return False

        except Exception as exc:
            _logger.exception(
                "[TRACKING-WA] Excepción de envío "
                "ticket=%s",
                self.name,
            )

            self._registrar_error_notificacion_tracking(
                str(exc)
            )

            return False

    # ==========================================================
    # REGISTRO DE ERRORES
    # ==========================================================

    def _registrar_error_notificacion_tracking(
        self,
        error,
    ):
        """
        Registra el error sin modificar el estado SAT.

        No genera fechas GPS.
        No marca notificaciones como entregadas.
        """
        self.ensure_one()

        mensaje = (
            "Error en solicitud de notificación "
            f"WhatsApp: {error}"
        )

        try:
            self.message_post(
                body=mensaje,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )
        except Exception:
            _logger.exception(
                "[TRACKING-WA] No se pudo registrar "
                "error en chatter. Ticket=%s",
                self.name,
            )
