# -*- coding: utf-8 -*-
"""
Tracking GPS de técnicos en campo
==================================
Herencia de ticket.alquiler para agregar:
  • Timestamps de cada etapa
  • Campos computados: tiempo traslado, en sitio, puntualidad
  • Métodos de transición de estado
  • API para actualizaciones desde Bot/Traccar
  • Vínculo técnico ↔ dispositivo Traccar

Archivo: models/ticket_tracking.py
"""
import math
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  MODELO: Vínculo Técnico ↔ Dispositivo Traccar
# ═══════════════════════════════════════════════════════════════════

class TecnicoDispositivoGPS(models.Model):
    _name = 'tecnico.dispositivo.gps'
    _description = 'Vínculo Técnico - Dispositivo GPS'
    _rec_name = 'user_id'

    user_id = fields.Many2one(
        'res.users', string='Técnico', required=True, index=True,
    )
    traccar_device_id = fields.Integer(
        string='Device ID (Traccar)', required=True,
        help='ID del dispositivo en Traccar',
    )
    traccar_unique_id = fields.Char(
        string='Identificador único',
        help='uniqueId del dispositivo en Traccar (ej: IMEI)',
    )
    nombre_dispositivo = fields.Char(
        string='Nombre dispositivo',
        help='Ej: "Celular Juan - Samsung A54"',
    )
    activo = fields.Boolean(string='Activo', default=True)

    _sql_constraints = [
        ('traccar_device_unique', 'unique(traccar_device_id)',
         'Este dispositivo de Traccar ya está vinculado a otro técnico.'),
    ]


# ═══════════════════════════════════════════════════════════════════
#  HERENCIA: ticket.alquiler — campos y métodos de tracking
# ═══════════════════════════════════════════════════════════════════

class TicketAlquilerTracking(models.Model):
    _inherit = 'ticket.alquiler'

    # ─── TIMESTAMPS ───────────────────────────────────────────────
    fecha_asignacion = fields.Datetime(
        string='Fecha asignación', readonly=True, tracking=True,
    )
    fecha_en_ruta = fields.Datetime(
        string='Técnico en ruta', readonly=True, tracking=True,
    )
    fecha_llegada = fields.Datetime(
        string='Llegada al sitio', readonly=True, tracking=True,
    )
    fecha_inicio_revision = fields.Datetime(
        string='Inicio revisión', readonly=True, tracking=True,
    )
    fecha_salida_sitio = fields.Datetime(
        string='Salida del sitio', readonly=True, tracking=True,
    )
    fecha_finalizacion = fields.Datetime(
        string='Fecha finalización', readonly=True, tracking=True,
    )

    # ─── CAMPOS COMPUTADOS ────────────────────────────────────────
    tiempo_traslado_minutos = fields.Float(
        string='Tiempo traslado (min)',
        compute='_compute_tiempos_tracking', store=True,
    )
    tiempo_en_sitio_minutos = fields.Float(
        string='Tiempo en sitio (min)',
        compute='_compute_tiempos_tracking', store=True,
    )
    tiempo_total_atencion_minutos = fields.Float(
        string='Tiempo total atención (min)',
        compute='_compute_tiempos_tracking', store=True,
    )
    diferencia_puntualidad_minutos = fields.Float(
        string='Puntualidad (min)',
        compute='_compute_tiempos_tracking', store=True,
        help='Negativo = llegó antes, Positivo = llegó tarde',
    )
    es_puntual = fields.Boolean(
        string='¿Fue puntual?',
        compute='_compute_tiempos_tracking', store=True,
        help='True si llegó dentro de 15 minutos de la hora agendada',
    )

    # ─── TRACCAR ──────────────────────────────────────────────────
    traccar_geofence_id = fields.Integer(
        string='Geocerca Traccar ID', readonly=True,
    )

    # ─── LOG ──────────────────────────────────────────────────────
    tracking_log = fields.Text(
        string='Log de tracking GPS', readonly=True,
    )

    # ═══════════════════════════════════════════════════════════════
    #  CÁLCULO DE TIEMPOS
    # ═══════════════════════════════════════════════════════════════

    @api.depends(
        'fecha_en_ruta', 'fecha_llegada', 'fecha_salida_sitio',
        'fecha_finalizacion', 'fecha_asignacion', 'agenda',
    )
    def _compute_tiempos_tracking(self):
        for rec in self:
            # Traslado: en_ruta → llegada
            if rec.fecha_en_ruta and rec.fecha_llegada:
                delta = rec.fecha_llegada - rec.fecha_en_ruta
                rec.tiempo_traslado_minutos = round(delta.total_seconds() / 60, 1)
            else:
                rec.tiempo_traslado_minutos = 0

            # En sitio: llegada → salida o finalización
            fin_sitio = rec.fecha_salida_sitio or rec.fecha_finalizacion
            if rec.fecha_llegada and fin_sitio:
                delta = fin_sitio - rec.fecha_llegada
                rec.tiempo_en_sitio_minutos = round(delta.total_seconds() / 60, 1)
            else:
                rec.tiempo_en_sitio_minutos = 0

            # Total: asignación → finalización
            if rec.fecha_asignacion and rec.fecha_finalizacion:
                delta = rec.fecha_finalizacion - rec.fecha_asignacion
                rec.tiempo_total_atencion_minutos = round(delta.total_seconds() / 60, 1)
            else:
                rec.tiempo_total_atencion_minutos = 0

            # Puntualidad: llegada real vs agenda
            if rec.fecha_llegada and rec.agenda:
                delta = rec.fecha_llegada - rec.agenda
                rec.diferencia_puntualidad_minutos = round(delta.total_seconds() / 60, 1)
                rec.es_puntual = abs(rec.diferencia_puntualidad_minutos) <= 15
            else:
                rec.diferencia_puntualidad_minutos = 0
                rec.es_puntual = False

    # ═══════════════════════════════════════════════════════════════
    #  HELPER: Log de tracking
    # ═══════════════════════════════════════════════════════════════

    def _append_tracking_log(self, mensaje):
        """Agrega una línea al log con timestamp en hora Lima."""
        from pytz import timezone as pytz_tz, UTC
        ahora = fields.Datetime.now()
        try:
            local = UTC.localize(ahora).astimezone(pytz_tz('America/Lima'))
            ts = local.strftime('%d/%m/%Y %H:%M:%S')
        except Exception:
            ts = ahora.strftime('%d/%m/%Y %H:%M:%S')

        log_actual = self.tracking_log or ''
        nueva_linea = f"[{ts}] {mensaje}"
        self.tracking_log = f"{log_actual}\n{nueva_linea}" if log_actual else nueva_linea

    # ═══════════════════════════════════════════════════════════════
    #  TRANSICIONES DE ESTADO
    # ═══════════════════════════════════════════════════════════════

    def action_en_ruta(self):
        """Marca el ticket como 'en_ruta'."""
        ahora = fields.Datetime.now()
        for ticket in self:
            if ticket.estado not in ('proceso',):
                raise UserError(_(
                    "Solo se puede marcar 'En Ruta' un ticket asignado.\n"
                    "Estado actual: %s"
                ) % ticket.estado)

            vals = {'estado': 'en_ruta'}
            if not ticket.fecha_en_ruta:
                vals['fecha_en_ruta'] = ahora
            ticket.write(vals)

            ticket._append_tracking_log(
                f"🚗 Técnico {ticket.responsable.name or 'N/A'} en ruta"
            )
            _logger.info("[TRACKING] %s → en_ruta | Técnico: %s",
                         ticket.name, ticket.responsable.name)

    def action_en_sitio(self):
        """Marca el ticket como 'en_sitio'."""
        ahora = fields.Datetime.now()
        for ticket in self:
            if ticket.estado not in ('proceso', 'en_ruta'):
                raise UserError(_(
                    "Solo se puede marcar 'En Sitio' un ticket asignado o en ruta.\n"
                    "Estado actual: %s"
                ) % ticket.estado)

            vals = {'estado': 'en_sitio'}
            if not ticket.fecha_llegada:
                vals['fecha_llegada'] = ahora
            if not ticket.fecha_en_ruta:
                vals['fecha_en_ruta'] = ahora
            ticket.write(vals)

            ticket._append_tracking_log(
                f"📍 Técnico {ticket.responsable.name or 'N/A'} llegó al sitio"
            )
            _logger.info("[TRACKING] %s → en_sitio | Técnico: %s",
                         ticket.name, ticket.responsable.name)

    def action_en_revision(self):
        """Marca el ticket como 'en_revision'."""
        ahora = fields.Datetime.now()
        for ticket in self:
            if ticket.estado not in ('en_sitio',):
                raise UserError(_(
                    "Solo se puede iniciar revisión cuando el técnico está en sitio.\n"
                    "Estado actual: %s"
                ) % ticket.estado)

            vals = {'estado': 'en_revision'}
            if not ticket.fecha_inicio_revision:
                vals['fecha_inicio_revision'] = ahora
            ticket.write(vals)

            ticket._append_tracking_log(
                f"🔧 Técnico {ticket.responsable.name or 'N/A'} inició revisión"
            )
            _logger.info("[TRACKING] %s → en_revision | Técnico: %s",
                         ticket.name, ticket.responsable.name)

    def action_registrar_salida_sitio(self):
        """Registra salida del técnico (no cambia estado)."""
        ahora = fields.Datetime.now()
        for ticket in self:
            if not ticket.fecha_salida_sitio:
                ticket.write({'fecha_salida_sitio': ahora})
                ticket._append_tracking_log(
                    f"📤 Técnico {ticket.responsable.name or 'N/A'} salió del sitio"
                )

    # ─── Override action_proceso: registrar timestamp ─────────────

    def action_proceso(self):
        ahora = fields.Datetime.now()
        for ticket in self:
            if not ticket.fecha_asignacion:
                ticket.fecha_asignacion = ahora
            ticket._append_tracking_log(
                f"📋 Ticket asignado a {ticket.responsable.name or 'N/A'}"
            )
        return super().action_proceso()

    # ─── Hook para action_finalizar: registrar timestamps ─────────
    # Llama esto DENTRO de tu action_finalizar original, justo antes
    # del ticket.write({'estado': 'finalizado'})

    def _registrar_finalizacion_tracking(self):
        """Registra timestamps de finalización. Llamar desde action_finalizar."""
        ahora = fields.Datetime.now()
        for ticket in self:
            vals = {}
            if not ticket.fecha_finalizacion:
                vals['fecha_finalizacion'] = ahora
            if not ticket.fecha_salida_sitio:
                vals['fecha_salida_sitio'] = ahora
            if not ticket.fecha_inicio_revision and ticket.fecha_llegada:
                vals['fecha_inicio_revision'] = ticket.fecha_llegada
            if vals:
                ticket.write(vals)
            ticket._append_tracking_log("✅ Ticket finalizado")

    # ═══════════════════════════════════════════════════════════════
    #  API: Actualización desde Bot / Traccar
    # ═══════════════════════════════════════════════════════════════

    @api.model
    def api_actualizar_estado_gps(self, tecnico_traccar_device_id, evento_tipo, datos=None):
        """
        Punto de entrada para actualizaciones desde el bot.

        Args:
            tecnico_traccar_device_id (int): ID del dispositivo en Traccar
            evento_tipo (str): geofenceEnter, geofenceExit, deviceMoving
            datos (dict): latitude, longitude, speed, address, geofenceId
        """
        datos = datos or {}
        _logger.info("[GPS-API] device=%s tipo=%s", tecnico_traccar_device_id, evento_tipo)

        # Buscar técnico
        vinculo = self.env['tecnico.dispositivo.gps'].sudo().search([
            ('traccar_device_id', '=', tecnico_traccar_device_id),
            ('activo', '=', True),
        ], limit=1)

        if not vinculo:
            _logger.warning("[GPS-API] Sin técnico para device_id=%s", tecnico_traccar_device_id)
            return {'success': False, 'error': f'Sin técnico para dispositivo {tecnico_traccar_device_id}'}

        tecnico = vinculo.user_id

        # Tickets activos del técnico
        tickets_activos = self.sudo().search([
            ('responsable', '=', tecnico.id),
            ('estado', 'in', ['proceso', 'en_ruta', 'en_sitio', 'en_revision']),
        ], order='agenda asc')

        if not tickets_activos:
            return {'success': True, 'message': 'Sin tickets activos', 'tickets_actualizados': []}

        # Procesar según evento
        actualizados = self.env['ticket.alquiler']

        if evento_tipo == 'geofenceEnter':
            actualizados = self._gps_procesar_llegada(tickets_activos, datos)
        elif evento_tipo == 'geofenceExit':
            actualizados = self._gps_procesar_salida(tickets_activos, datos)
        elif evento_tipo == 'deviceMoving':
            actualizados = self._gps_procesar_movimiento(tickets_activos, datos)

        return {
            'success': True,
            'tecnico': tecnico.name,
            'evento': evento_tipo,
            'tickets_actualizados': [
                {'id': t.id, 'name': t.name, 'estado': t.estado}
                for t in actualizados
            ],
        }

    def _gps_procesar_llegada(self, tickets, datos):
        """Procesa geofenceEnter: marca tickets en_sitio."""
        geofence_id = datos.get('geofenceId')
        actualizados = self.env['ticket.alquiler']

        for ticket in tickets:
            if ticket.estado not in ('proceso', 'en_ruta'):
                continue

            # Match por geocerca
            if geofence_id and ticket.traccar_geofence_id == geofence_id:
                ticket.sudo().action_en_sitio()
                actualizados |= ticket
                continue

            # Match por proximidad GPS (200m)
            if (ticket.equipo_latitud and ticket.equipo_longitud
                    and datos.get('latitude') and datos.get('longitude')):
                dist = self._haversine_metros(
                    datos['latitude'], datos['longitude'],
                    ticket.equipo_latitud, ticket.equipo_longitud,
                )
                if dist <= 200:
                    ticket.sudo().action_en_sitio()
                    ticket._append_tracking_log(f"📍 Llegada por proximidad GPS ({dist:.0f}m)")
                    actualizados |= ticket

        return actualizados

    def _gps_procesar_salida(self, tickets, datos):
        """Procesa geofenceExit: registra salida."""
        actualizados = self.env['ticket.alquiler']
        for ticket in tickets:
            if ticket.estado in ('en_sitio', 'en_revision'):
                ticket.sudo().action_registrar_salida_sitio()
                actualizados |= ticket
        return actualizados

    def _gps_procesar_movimiento(self, tickets, datos):
        """Procesa deviceMoving: marca primer ticket asignado como en_ruta."""
        actualizados = self.env['ticket.alquiler']
        siguiente = tickets.filtered(lambda t: t.estado == 'proceso')
        if siguiente:
            siguiente[0].sudo().action_en_ruta()
            actualizados |= siguiente[0]
        return actualizados

    @staticmethod
    def _haversine_metros(lat1, lon1, lat2, lon2):
        """Distancia en metros entre dos puntos GPS."""
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = (math.sin(d_phi / 2) ** 2
             + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # ═══════════════════════════════════════════════════════════════
    #  RESUMEN para WhatsApp
    # ═══════════════════════════════════════════════════════════════

    def get_tracking_summary(self):
        """Retorna resumen formateado para WhatsApp."""
        self.ensure_one()
        from pytz import timezone as pytz_tz, UTC

        def fmt_min(mins):
            if not mins:
                return '--'
            h, m = int(mins // 60), int(mins % 60)
            return f"{h}h {m}min" if h else f"{m} min"

        def fmt_hora(dt):
            if not dt:
                return '--'
            try:
                return UTC.localize(dt).astimezone(pytz_tz('America/Lima')).strftime('%H:%M')
            except Exception:
                return dt.strftime('%H:%M')

        lines = [
            f"📊 *Resumen — {self.name}*",
            f"🚘 Técnico: {self.responsable.name or 'N/A'}",
            f"🏢 Cliente: {self.partner_id.name or 'N/A'}",
            "",
            f"⏰ Agendado: {fmt_hora(self.agenda)}",
            f"🚗 En ruta: {fmt_hora(self.fecha_en_ruta)}",
            f"📍 Llegada: {fmt_hora(self.fecha_llegada)}",
            f"🔧 Revisión: {fmt_hora(self.fecha_inicio_revision)}",
            f"📤 Salida: {fmt_hora(self.fecha_salida_sitio)}",
            f"✅ Finalizado: {fmt_hora(self.fecha_finalizacion)}",
            "",
            f"🚗 Traslado: {fmt_min(self.tiempo_traslado_minutos)}",
            f"🏢 En sitio: {fmt_min(self.tiempo_en_sitio_minutos)}",
            f"⏱️ Total: {fmt_min(self.tiempo_total_atencion_minutos)}",
        ]

        if self.fecha_llegada and self.agenda:
            if self.es_puntual:
                lines.append("✅ Puntualidad: A tiempo")
            elif self.diferencia_puntualidad_minutos > 0:
                lines.append(f"⚠️ Llegó {fmt_min(self.diferencia_puntualidad_minutos)} tarde")
            else:
                lines.append(f"✅ Llegó {fmt_min(abs(self.diferencia_puntualidad_minutos))} antes")

        return '\n'.join(lines)