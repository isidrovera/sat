# -*- coding: utf-8 -*-
"""
Tracking GPS de técnicos en campo — v3
========================================
Archivo: models/ticket_tracking.py

Cambios v3:
  • Lógica secuencial: al salir de un cliente pasa al siguiente ticket
  • Cliente con varias máquinas: todos los tickets del mismo partner_id
    y misma agenda se procesan juntos
  • Cron cada 5 min: tickets en_sitio > 15 min → en_revision automático
  • Notificaciones WhatsApp en cada cambio de estado
  • Filtro de fecha HOY (zona horaria Lima)
  • deviceMoving solo actúa si agenda está dentro de ventana 2h
  • Chatter en cada evento incluso si se ignora
"""
import math
import logging
from datetime import date, timedelta

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
#  HERENCIA: ticket.alquiler
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
    #  CREATE / WRITE
    # ═══════════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        ahora = fields.Datetime.now()
        for vals in vals_list:
            if vals.get('responsable') and not vals.get('fecha_asignacion'):
                vals['fecha_asignacion'] = ahora
        records = super().create(vals_list)
        for rec in records:
            if rec.responsable and rec.fecha_asignacion:
                rec._registrar_evento(
                    f"📋 Ticket creado y asignado a {rec.responsable.name}"
                )
        return records

    def write(self, vals):
        resultado = super().write(vals)
        ahora = fields.Datetime.now()
        if 'responsable' in vals:
            for rec in self:
                if rec.responsable and not rec.fecha_asignacion:
                    rec.sudo().write({'fecha_asignacion': ahora})
                    rec._registrar_evento(
                        f"📋 Ticket asignado a {rec.responsable.name}"
                    )
        return resultado

    # ═══════════════════════════════════════════════════════════════
    #  CÁLCULO DE TIEMPOS
    # ═══════════════════════════════════════════════════════════════

    @api.depends(
        'fecha_en_ruta', 'fecha_llegada', 'fecha_salida_sitio',
        'fecha_finalizacion', 'fecha_asignacion', 'agenda',
    )
    def _compute_tiempos_tracking(self):
        for rec in self:
            if rec.fecha_en_ruta and rec.fecha_llegada:
                delta = rec.fecha_llegada - rec.fecha_en_ruta
                rec.tiempo_traslado_minutos = round(delta.total_seconds() / 60, 1)
            else:
                rec.tiempo_traslado_minutos = 0

            fin_sitio = rec.fecha_salida_sitio or rec.fecha_finalizacion
            if rec.fecha_llegada and fin_sitio:
                delta = fin_sitio - rec.fecha_llegada
                rec.tiempo_en_sitio_minutos = round(delta.total_seconds() / 60, 1)
            else:
                rec.tiempo_en_sitio_minutos = 0

            if rec.fecha_asignacion and rec.fecha_finalizacion:
                delta = rec.fecha_finalizacion - rec.fecha_asignacion
                rec.tiempo_total_atencion_minutos = round(delta.total_seconds() / 60, 1)
            else:
                rec.tiempo_total_atencion_minutos = 0

            if rec.fecha_llegada and rec.agenda:
                delta = rec.fecha_llegada - rec.agenda
                rec.diferencia_puntualidad_minutos = round(delta.total_seconds() / 60, 1)
                rec.es_puntual = abs(rec.diferencia_puntualidad_minutos) <= 15
            else:
                rec.diferencia_puntualidad_minutos = 0
                rec.es_puntual = False

    # ═══════════════════════════════════════════════════════════════
    #  HELPERS DE REGISTRO
    # ═══════════════════════════════════════════════════════════════

    def _chatter_tracking(self, mensaje):
        try:
            self.message_post(
                body=mensaje,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )
        except Exception as e:
            _logger.error("[TRACKING] Error chatter en %s: %s", self.name, e)

    def _append_tracking_log(self, mensaje):
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

    def _registrar_evento(self, mensaje):
        """Punto único: escribe en log interno y en chatter."""
        self._append_tracking_log(mensaje)
        self._chatter_tracking(mensaje)

    # ═══════════════════════════════════════════════════════════════
    #  HELPER: agrupar tickets del mismo cliente/visita
    # ═══════════════════════════════════════════════════════════════

    def _get_tickets_misma_visita(self, tickets_pool):
        """
        Retorna todos los tickets del mismo técnico y cliente
        cuya agenda esté dentro de ±30 min de este ticket.
        Cubre el caso de cliente con varias máquinas.
        """
        self.ensure_one()
        if not self.agenda or not self.partner_id:
            return self

        ventana = timedelta(minutes=30)
        agenda_ini = self.agenda - ventana
        agenda_fin = self.agenda + ventana

        misma_visita = tickets_pool.filtered(lambda t: (
            t.partner_id.id == self.partner_id.id
            and t.responsable.id == self.responsable.id
            and t.agenda
            and agenda_ini <= t.agenda <= agenda_fin
        ))
        return misma_visita if misma_visita else self

    # ═══════════════════════════════════════════════════════════════
    #  TRANSICIONES DE ESTADO
    # ═══════════════════════════════════════════════════════════════

    def action_en_ruta(self):
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
            ticket._registrar_evento(
                f"🚗 Técnico {ticket.responsable.name or 'N/A'} en ruta"
            )
            try:
                ticket.notificar_en_ruta()
            except Exception as e:
                _logger.error("[TRACKING] Error notificando en_ruta: %s", e)

    def action_en_sitio(self):
        ahora = fields.Datetime.now()
        for ticket in self:
            if ticket.estado not in ('proceso', 'en_ruta'):
                raise UserError(_(
                    "Solo se puede marcar 'En Sitio' desde asignado o en ruta.\n"
                    "Estado actual: %s"
                ) % ticket.estado)
            vals = {'estado': 'en_sitio'}
            if not ticket.fecha_llegada:
                vals['fecha_llegada'] = ahora
            if not ticket.fecha_en_ruta:
                vals['fecha_en_ruta'] = ahora
            ticket.write(vals)
            ticket._registrar_evento(
                f"📍 Técnico {ticket.responsable.name or 'N/A'} llegó al sitio"
            )
            try:
                ticket.notificar_en_sitio()
            except Exception as e:
                _logger.error("[TRACKING] Error notificando en_sitio: %s", e)

    def action_en_revision(self):
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
            ticket._registrar_evento(
                f"🔧 Técnico {ticket.responsable.name or 'N/A'} inició revisión"
            )
            try:
                ticket.notificar_en_revision()
            except Exception as e:
                _logger.error("[TRACKING] Error notificando en_revision: %s", e)

    def action_registrar_salida_sitio(self):
        ahora = fields.Datetime.now()
        for ticket in self:
            if not ticket.fecha_salida_sitio:
                ticket.write({'fecha_salida_sitio': ahora})
                ticket._registrar_evento(
                    f"📤 Técnico {ticket.responsable.name or 'N/A'} salió del sitio"
                )
                try:
                    ticket.notificar_salida_sitio()
                except Exception as e:
                    _logger.error("[TRACKING] Error notificando salida_sitio: %s", e)

    def action_proceso(self):
        ahora = fields.Datetime.now()
        for ticket in self:
            if not ticket.fecha_asignacion:
                ticket.fecha_asignacion = ahora
            ticket._registrar_evento(
                f"📋 Ticket asignado a {ticket.responsable.name or 'N/A'}"
            )
        return super().action_proceso()

    def _registrar_finalizacion_tracking(self):
        """Llamar desde action_finalizar antes de cambiar estado."""
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
            ticket._registrar_evento("✅ Ticket finalizado")
            try:
                ticket.notificar_finalizado()
            except Exception as e:
                _logger.error("[TRACKING] Error notificando finalizado: %s", e)

    # ═══════════════════════════════════════════════════════════════
    #  CRON: en_sitio → en_revision automático
    # ═══════════════════════════════════════════════════════════════

    @api.model
    def cron_actualizar_en_revision(self):
        """
        Ejecutar cada 5 minutos.
        Tickets en_sitio con fecha_llegada hace más de 15 min (configurable)
        pasan automáticamente a en_revision.
        """
        umbral = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'tracking.minutos_para_revision', '15'
            )
        )
        limite = fields.Datetime.now() - timedelta(minutes=umbral)

        tickets = self.sudo().search([
            ('estado', '=', 'en_sitio'),
            ('fecha_llegada', '<=', limite),
            ('fecha_inicio_revision', '=', False),
        ])

        if not tickets:
            return

        _logger.info("[CRON-REVISION] %d tickets → en_revision automático", len(tickets))

        for ticket in tickets:
            try:
                ticket.action_en_revision()
            except Exception as e:
                _logger.error("[CRON-REVISION] Error en %s: %s", ticket.name, e)
                ticket._registrar_evento(f"❌ Error cron en_revision: {str(e)}")

    # ═══════════════════════════════════════════════════════════════
    #  API GPS
    # ═══════════════════════════════════════════════════════════════

    @api.model
    def api_actualizar_estado_gps(self, tecnico_traccar_device_id, evento_tipo, datos=None):
        datos = datos or {}
        _logger.info(
            "[GPS-API] device=%s tipo=%s lat=%s lon=%s",
            tecnico_traccar_device_id, evento_tipo,
            datos.get('latitude'), datos.get('longitude')
        )

        vinculo = self.env['tecnico.dispositivo.gps'].sudo().search([
            ('traccar_device_id', '=', tecnico_traccar_device_id),
            ('activo', '=', True),
        ], limit=1)

        if not vinculo:
            _logger.warning("[GPS-API] Sin técnico para device_id=%s", tecnico_traccar_device_id)
            return {'success': False, 'error': f'Sin técnico para dispositivo {tecnico_traccar_device_id}'}

        tecnico = vinculo.user_id
        hoy_inicio, hoy_fin = self._get_rango_hoy()

        tickets_hoy = self.sudo().search([
            ('responsable', '=', tecnico.id),
            ('estado', 'in', ['proceso', 'en_ruta', 'en_sitio', 'en_revision']),
            ('agenda', '>=', hoy_inicio),
            ('agenda', '<=', hoy_fin),
        ], order='agenda asc')

        _logger.info("[GPS-API] Tickets HOY para %s: %d", tecnico.name, len(tickets_hoy))

        if not tickets_hoy:
            tickets_otros = self.sudo().search([
                ('responsable', '=', tecnico.id),
                ('estado', 'in', ['proceso', 'en_ruta', 'en_sitio', 'en_revision']),
            ], limit=5)
            if tickets_otros:
                detalle = ', '.join(f"{t.name}(agenda:{t.agenda})" for t in tickets_otros)
                return {
                    'success': True,
                    'message': f'Sin tickets HOY. Tickets otros días ignorados: {detalle}',
                    'tickets_actualizados': [],
                }
            return {
                'success': True,
                'message': f'Sin tickets activos para {tecnico.name}',
                'tickets_actualizados': [],
            }

        actualizados = self.env['ticket.alquiler']

        try:
            if evento_tipo == 'geofenceEnter':
                actualizados = self._gps_procesar_llegada(tickets_hoy, datos)
            elif evento_tipo == 'geofenceExit':
                actualizados = self._gps_procesar_salida(tickets_hoy, datos)
            elif evento_tipo == 'deviceMoving':
                actualizados = self._gps_procesar_movimiento(tickets_hoy, datos)
        except Exception as e:
            _logger.exception("[GPS-API] Error: %s", e)
            for t in tickets_hoy:
                t.sudo()._registrar_evento(f"❌ Error GPS [{evento_tipo}]: {str(e)}")
            return {'success': False, 'error': str(e), 'tickets_actualizados': []}

        return {
            'success': True,
            'tecnico': tecnico.name,
            'evento': evento_tipo,
            'tickets_actualizados': [
                {'id': t.id, 'name': t.name, 'estado': t.estado}
                for t in actualizados
            ],
        }

    def _gps_procesar_llegada(self, tickets_hoy, datos):
        """
        geofenceEnter → marcar en_sitio.

        Prioridad de match:
          1. Por traccar_geofence_id exacto
          2. Por proximidad GPS (≤ 200m) si llegan coordenadas
          3. Fallback: primer candidato disponible
             (cuando lat/lon son None y no hay geocerca configurada)
        """
        geofence_id   = datos.get('geofenceId')
        lat_tec       = datos.get('latitude')
        lon_tec       = datos.get('longitude')
        actualizados  = self.env['ticket.alquiler']

        candidatos = tickets_hoy.filtered(lambda t: t.estado in ('proceso', 'en_ruta'))
        if not candidatos:
            estados = ', '.join(set(tickets_hoy.mapped('estado')))
            for t in tickets_hoy:
                t._registrar_evento(
                    f"ℹ️ geofenceEnter ignorado — no hay candidatos "
                    f"(estados actuales: {estados})"
                )
            return actualizados

        ticket_match   = None
        distancia_match = None
        metodo_match   = None

        # ── 1. Match por geocerca ────────────────────────────────
        if geofence_id:
            for ticket in candidatos:
                if ticket.traccar_geofence_id == geofence_id:
                    ticket_match  = ticket
                    metodo_match  = f"geocerca ID:{geofence_id}"
                    break

        # ── 2. Match por proximidad GPS ──────────────────────────
        if not ticket_match and lat_tec and lon_tec:
            for ticket in candidatos:
                lat_eq = getattr(ticket, 'equipo_latitud', None)
                lon_eq = getattr(ticket, 'equipo_longitud', None)
                if lat_eq and lon_eq:
                    dist = self._haversine_metros(lat_tec, lon_tec, lat_eq, lon_eq)
                    if dist <= 200:
                        ticket_match    = ticket
                        distancia_match = dist
                        metodo_match    = f"proximidad GPS ({dist:.0f}m)"
                        break
                    else:
                        ticket._registrar_evento(
                            f"📡 Técnico a {dist:.0f}m del equipo (mín 200m para match)"
                        )

        # ── 3. Fallback: primer candidato ────────────────────────
        #    Aplica cuando Traccar no envía posición (lat/lon None)
        #    y el ticket no tiene geocerca configurada.
        #    Se toma el primero ordenado por agenda (orden del search).
        if not ticket_match:
            ticket_match = candidatos[0]
            metodo_match = "fallback (sin coordenadas ni geocerca configurada)"
            _logger.warning(
                "[GPS-LLEGADA] Usando fallback para ticket %s — "
                "geofence_id=%s lat=%s lon=%s",
                ticket_match.name, geofence_id, lat_tec, lon_tec
            )

        # ── Agrupar tickets del mismo cliente/agenda ─────────────
        tickets_visita = ticket_match._get_tickets_misma_visita(candidatos)

        for ticket in tickets_visita:
            ticket.sudo().action_en_sitio()
            ticket._registrar_evento(f"📍 Llegada registrada — método: {metodo_match}")
            actualizados |= ticket

        # ── Notificación grupal ──────────────────────────────────
        if actualizados:
            try:
                actualizados[0].notificar_en_sitio(tickets_grupo=actualizados)
            except Exception as e:
                _logger.error("[GPS] Error notificando en_sitio grupal: %s", e)

        return actualizados

    def _gps_procesar_salida(self, tickets_hoy, datos):
        """
        Al salir del cliente:
        1. Registrar salida de todos los tickets de esa visita
        2. Marcar en_ruta el siguiente ticket del día (secuencial)
        """
        actualizados = self.env['ticket.alquiler']

        en_sitio_o_revision = tickets_hoy.filtered(
            lambda t: t.estado in ('en_sitio', 'en_revision')
        )

        if not en_sitio_o_revision:
            for t in tickets_hoy:
                t._registrar_evento("ℹ️ geofenceExit ignorado — ningún ticket en sitio/revisión")
            return actualizados

        # Agrupar por cliente para no registrar salida doble
        clientes_procesados = set()
        tickets_salida = self.env['ticket.alquiler']
        for ticket in en_sitio_o_revision:
            clave = (ticket.partner_id.id, ticket.agenda.date() if ticket.agenda else None)
            if clave not in clientes_procesados:
                clientes_procesados.add(clave)
                tickets_visita = ticket._get_tickets_misma_visita(en_sitio_o_revision)
                tickets_salida |= tickets_visita

        for ticket in tickets_salida:
            ticket.sudo().action_registrar_salida_sitio()
            actualizados |= ticket

        if actualizados:
            try:
                actualizados[0].notificar_salida_sitio(tickets_grupo=actualizados)
            except Exception as e:
                _logger.error("[GPS] Error notificando salida grupal: %s", e)

        # ── Siguiente ticket del día (lógica secuencial) ─────────
        siguiente = tickets_hoy.filtered(lambda t: t.estado == 'proceso')
        if siguiente:
            sig = siguiente[0]
            try:
                sig.sudo().action_en_ruta()
                sig._registrar_evento("🚗 En ruta automático — salida del servicio anterior")
                try:
                    actualizados[0].notificar_siguiente_en_ruta(sig)
                except Exception as e:
                    _logger.error("[GPS] Error notificando siguiente: %s", e)
            except Exception as e:
                _logger.error("[GPS-SECUENCIAL] Error marcando siguiente en_ruta: %s", e)
                sig._registrar_evento(f"❌ Error al marcar en_ruta automático: {str(e)}")
        else:
            if actualizados:
                actualizados[0]._registrar_evento("ℹ️ Último servicio del día completado")

        return actualizados

    def _gps_procesar_movimiento(self, tickets_hoy, datos):
        """
        deviceMoving → en_ruta SOLO si:
        - Hay ticket en 'proceso'
        - Agenda dentro de ventana 2h
        - No hay ya un ticket en_ruta
        """
        actualizados = self.env['ticket.alquiler']
        ahora = fields.Datetime.now()
        ventana = timedelta(hours=2)

        ya_en_ruta = tickets_hoy.filtered(lambda t: t.estado == 'en_ruta')
        if ya_en_ruta:
            return actualizados

        for ticket in tickets_hoy.filtered(lambda t: t.estado == 'proceso'):
            if not ticket.agenda:
                continue
            diff = ticket.agenda - ahora
            ya_paso = diff.total_seconds() < 0
            esta_cerca = 0 <= diff.total_seconds() <= ventana.total_seconds()

            if ya_paso or esta_cerca:
                ticket.sudo().action_en_ruta()
                ticket._registrar_evento("🚗 En ruta detectado por movimiento GPS")
                actualizados |= ticket
                break
            else:
                h = int(diff.total_seconds() / 3600)
                m = int((diff.total_seconds() % 3600) / 60)
                ticket._registrar_evento(
                    f"ℹ️ deviceMoving ignorado — agenda en {h}h {m}min (ventana: 2h)"
                )

        return actualizados

    # ═══════════════════════════════════════════════════════════════
    #  HELPERS ESTÁTICOS
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _get_rango_hoy():
        from pytz import timezone as pytz_tz, UTC as pytz_UTC
        lima = pytz_tz('America/Lima')
        hoy_lima = date.today()
        inicio_lima = lima.localize(fields.Datetime.from_string(f"{hoy_lima} 00:00:00"))
        fin_lima = lima.localize(fields.Datetime.from_string(f"{hoy_lima} 23:59:59"))
        return (
            inicio_lima.astimezone(pytz_UTC).replace(tzinfo=None),
            fin_lima.astimezone(pytz_UTC).replace(tzinfo=None),
        )

    @staticmethod
    def _haversine_metros(lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = (math.sin(d_phi / 2) ** 2
             + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # ═══════════════════════════════════════════════════════════════
    #  RESUMEN WhatsApp
    # ═══════════════════════════════════════════════════════════════

    def get_tracking_summary(self):
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
            f"📋 Asignado: {fmt_hora(self.fecha_asignacion)}",
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