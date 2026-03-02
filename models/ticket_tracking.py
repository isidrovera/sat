# -*- coding: utf-8 -*-
"""
Tracking GPS de técnicos en campo — v6
========================================
Archivo: models/ticket_tracking.py

Cambios v6:
  • Fix: una sola notificación por técnico/cliente (no una por ticket)
  • action_en_ruta / action_en_sitio / action_registrar_salida_sitio
    aceptan parámetro notificar=True para suprimir notif. individual
    cuando el llamador (GPS/cron) ya envía la notificación grupal.
  • Ubicación actual del técnico (lat/lon) se propaga desde el webhook
    hasta los métodos de notificación via ubicacion_actual dict.
  • _gps_procesar_* pasan ubicacion_actual a notificar_*
"""
import math
import logging
import requests
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
#  SERVICIO TRACCAR API
# ═══════════════════════════════════════════════════════════════════

class TraccarAPIService(models.AbstractModel):
    _name = 'traccar.api.service'
    _description = 'Servicio API Traccar'

    def _get_config(self):
        get = lambda k, d='': self.env['ir.config_parameter'].sudo().get_param(k, default=d)
        return {
            'url':      get('traccar.url', 'https://gps.andessolutioncopiers.com'),
            'email':    get('traccar.email'),
            'password': get('traccar.password'),
            'timeout':  int(get('traccar.timeout', '10')),
        }

    def _get_session(self):
        cfg = self._get_config()
        if not cfg['email'] or not cfg['password']:
            raise UserError(
                "Traccar no configurado.\n"
                "Configure traccar.url, traccar.email y traccar.password "
                "en Ajustes → Parámetros del sistema."
            )
        session = requests.Session()
        resp = session.post(
            f"{cfg['url']}/api/session",
            data={'email': cfg['email'], 'password': cfg['password']},
            timeout=cfg['timeout'],
        )
        if resp.status_code != 200:
            raise UserError(
                f"Error autenticando en Traccar: {resp.status_code} — {resp.text[:200]}"
            )
        _logger.info("[TRACCAR-API] Sesion iniciada como %s", cfg['email'])
        return session, cfg

    def get_all_positions(self):
        """
        Retorna dict {device_id: position_data} con todas las posiciones.
        Una sola llamada para todos los devices — eficiente para crons.
        """
        try:
            session, cfg = self._get_session()
            resp = session.get(
                f"{cfg['url']}/api/positions",
                timeout=cfg['timeout'],
            )
            if resp.status_code == 200:
                positions = resp.json()
                return {p['deviceId']: p for p in positions}
            else:
                _logger.error(
                    "[TRACCAR-API] Error obteniendo posiciones: %s", resp.status_code
                )
                return {}
        except Exception as e:
            _logger.error("[TRACCAR-API] Excepcion obteniendo posiciones: %s", e)
            return {}

    def crear_geocerca(self, nombre, latitud, longitud, radio_metros=150):
        try:
            session, cfg = self._get_session()
            payload = {
                'name':       nombre,
                'area':       f"CIRCLE({latitud} {longitud}, {radio_metros})",
                'attributes': {},
            }
            resp = session.post(
                f"{cfg['url']}/api/geofences",
                json=payload,
                timeout=cfg['timeout'],
            )
            if resp.status_code in (200, 201):
                geofence = resp.json()
                gid = geofence.get('id')
                _logger.info(
                    "[TRACCAR-API] Geocerca creada: '%s' ID=%s (%.6f, %.6f r=%dm)",
                    nombre, gid, latitud, longitud, radio_metros
                )
                return gid
            else:
                _logger.error(
                    "[TRACCAR-API] Error creando geocerca '%s': %s",
                    nombre, resp.status_code
                )
                return None
        except Exception as e:
            _logger.error("[TRACCAR-API] Excepcion creando geocerca '%s': %s", nombre, e)
            return None

    def borrar_geocerca(self, geofence_id):
        if not geofence_id:
            return False
        try:
            session, cfg = self._get_session()
            resp = session.delete(
                f"{cfg['url']}/api/geofences/{geofence_id}",
                timeout=cfg['timeout'],
            )
            if resp.status_code in (200, 204):
                _logger.info("[TRACCAR-API] Geocerca ID=%s eliminada", geofence_id)
                return True
            else:
                _logger.warning(
                    "[TRACCAR-API] No se pudo borrar geocerca ID=%s: %s",
                    geofence_id, resp.status_code
                )
                return False
        except Exception as e:
            _logger.error("[TRACCAR-API] Excepcion borrando geocerca %s: %s", geofence_id, e)
            return False

    def vincular_geocerca_dispositivo(self, geofence_id, device_id):
        try:
            session, cfg = self._get_session()
            resp = session.post(
                f"{cfg['url']}/api/permissions",
                json={'deviceId': device_id, 'geofenceId': geofence_id},
                timeout=cfg['timeout'],
            )
            if resp.status_code in (200, 204):
                _logger.info(
                    "[TRACCAR-API] Geocerca %s vinculada a device %s",
                    geofence_id, device_id
                )
                return True
            else:
                _logger.warning(
                    "[TRACCAR-API] Error vinculando geocerca %s device %s: %s",
                    geofence_id, device_id, resp.status_code
                )
                return False
        except Exception as e:
            _logger.error(
                "[TRACCAR-API] Excepcion vinculando geocerca %s device %s: %s",
                geofence_id, device_id, e
            )
            return False

    def desvincular_geocerca_dispositivo(self, geofence_id, device_id):
        try:
            session, cfg = self._get_session()
            resp = session.delete(
                f"{cfg['url']}/api/permissions",
                json={'deviceId': device_id, 'geofenceId': geofence_id},
                timeout=cfg['timeout'],
            )
            if resp.status_code in (200, 204):
                _logger.info(
                    "[TRACCAR-API] Geocerca %s desvinculada de device %s",
                    geofence_id, device_id
                )
                return True
            else:
                _logger.warning(
                    "[TRACCAR-API] Error desvinculando: %s", resp.status_code
                )
                return False
        except Exception as e:
            _logger.error("[TRACCAR-API] Excepcion desvinculando: %s", e)
            return False


# ═══════════════════════════════════════════════════════════════════
#  HERENCIA: ticket.alquiler
# ═══════════════════════════════════════════════════════════════════

class TicketAlquilerTracking(models.Model):
    _inherit = 'ticket.alquiler'

    fecha_asignacion = fields.Datetime(
        string='Fecha asignacion', readonly=True, tracking=True,
    )
    fecha_en_ruta = fields.Datetime(
        string='Tecnico en ruta', readonly=True, tracking=True,
    )
    fecha_llegada = fields.Datetime(
        string='Llegada al sitio', readonly=True, tracking=True,
    )
    fecha_inicio_revision = fields.Datetime(
        string='Inicio revision', readonly=True, tracking=True,
    )
    fecha_salida_sitio = fields.Datetime(
        string='Salida del sitio', readonly=True, tracking=True,
    )
    fecha_finalizacion = fields.Datetime(
        string='Fecha finalizacion', readonly=True, tracking=True,
    )
    tiempo_traslado_minutos = fields.Float(
        string='Tiempo traslado (min)',
        compute='_compute_tiempos_tracking', store=True,
    )
    tiempo_en_sitio_minutos = fields.Float(
        string='Tiempo en sitio (min)',
        compute='_compute_tiempos_tracking', store=True,
    )
    tiempo_total_atencion_minutos = fields.Float(
        string='Tiempo total atencion (min)',
        compute='_compute_tiempos_tracking', store=True,
    )
    diferencia_puntualidad_minutos = fields.Float(
        string='Puntualidad (min)',
        compute='_compute_tiempos_tracking', store=True,
        help='Negativo = llego antes, Positivo = llego tarde',
    )
    es_puntual = fields.Boolean(
        string='Fue puntual?',
        compute='_compute_tiempos_tracking', store=True,
    )
    traccar_geofence_id = fields.Integer(
        string='Geocerca Traccar ID',
        readonly=True,
        help='ID de la geocerca creada automaticamente en Traccar para este ticket',
    )
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
                    f"Ticket creado y asignado a {rec.responsable.name}"
                )
            if rec.responsable and rec.equipo_tiene_coordenadas:
                rec._geocerca_crear()
        return records

    def write(self, vals):
        tecnico_anterior = {rec.id: rec.responsable.id for rec in self}
        resultado = super().write(vals)
        ahora = fields.Datetime.now()
        for rec in self:
            if 'responsable' in vals:
                tecnico_cambio = tecnico_anterior[rec.id] != rec.responsable.id
                if rec.responsable and not rec.fecha_asignacion:
                    rec.sudo().write({'fecha_asignacion': ahora})
                    rec._registrar_evento(
                        f"Ticket asignado a {rec.responsable.name}"
                    )
                if tecnico_cambio and rec.responsable and rec.equipo_tiene_coordenadas:
                    if rec.traccar_geofence_id:
                        rec._geocerca_borrar()
                    rec._geocerca_crear()
        return resultado

    # ═══════════════════════════════════════════════════════════════
    #  GEOCERCAS
    # ═══════════════════════════════════════════════════════════════

    def _geocerca_crear(self):
        self.ensure_one()
        if not self.equipo_latitud or not self.equipo_longitud:
            return False
        if not self.responsable:
            return False
        vinculo = self.env['tecnico.dispositivo.gps'].sudo().search([
            ('user_id', '=', self.responsable.id),
            ('activo', '=', True),
        ], limit=1)
        if not vinculo:
            _logger.warning("[GEO-AUTO] Tecnico %s sin dispositivo GPS", self.responsable.name)
            return False
        cliente = self.partner_id.name or 'Cliente'
        nombre  = f"{self.name} - {cliente}"[:100]
        radio   = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'traccar.geocerca_radio_metros', '150'
            )
        )
        traccar     = self.env['traccar.api.service']
        geofence_id = traccar.crear_geocerca(
            nombre=nombre,
            latitud=self.equipo_latitud,
            longitud=self.equipo_longitud,
            radio_metros=radio,
        )
        if not geofence_id:
            self._registrar_evento("No se pudo crear geocerca en Traccar")
            return False
        traccar.vincular_geocerca_dispositivo(
            geofence_id=geofence_id,
            device_id=vinculo.traccar_device_id,
        )
        self.sudo().write({'traccar_geofence_id': geofence_id})
        self._registrar_evento(
            f"Geocerca Traccar creada automaticamente "
            f"(ID:{geofence_id}, radio:{radio}m) - "
            f"{self.equipo_latitud:.6f}, {self.equipo_longitud:.6f}"
        )
        return geofence_id

    def _geocerca_borrar(self):
        self.ensure_one()
        if not self.traccar_geofence_id:
            return False
        geofence_id = self.traccar_geofence_id
        traccar     = self.env['traccar.api.service']
        if self.responsable:
            vinculo = self.env['tecnico.dispositivo.gps'].sudo().search([
                ('user_id', '=', self.responsable.id),
                ('activo', '=', True),
            ], limit=1)
            if vinculo:
                traccar.desvincular_geocerca_dispositivo(
                    geofence_id=geofence_id,
                    device_id=vinculo.traccar_device_id,
                )
        traccar.borrar_geocerca(geofence_id)
        self.sudo().write({'traccar_geofence_id': 0})
        self._registrar_evento(f"Geocerca Traccar ID:{geofence_id} eliminada")
        return True

    def action_crear_geocerca_manual(self):
        self.ensure_one()
        if self.traccar_geofence_id:
            self._geocerca_borrar()
        result = self._geocerca_crear()
        if result:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title':   'Geocerca creada',
                    'message': f'Geocerca ID:{result} creada y vinculada en Traccar.',
                    'type':    'success',
                },
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title':   'Error',
                'message': 'No se pudo crear la geocerca. Revise logs.',
                'type':    'warning',
            },
        }

    # ═══════════════════════════════════════════════════════════════
    #  CALCULO DE TIEMPOS
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
        log_actual  = self.tracking_log or ''
        nueva_linea = f"[{ts}] {mensaje}"
        self.tracking_log = f"{log_actual}\n{nueva_linea}" if log_actual else nueva_linea

    def _registrar_evento(self, mensaje):
        self._append_tracking_log(mensaje)
        self._chatter_tracking(mensaje)

    def _get_tickets_misma_visita(self, tickets_pool):
        self.ensure_one()
        if not self.agenda or not self.partner_id:
            return self
        ventana    = timedelta(minutes=30)
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
    #  CAMBIO v6: parámetro notificar=True en action_en_ruta,
    #             action_en_sitio y action_registrar_salida_sitio.
    #  Cuando notificar=False el llamador (GPS/cron) es responsable
    #  de enviar UNA notificación grupal después del loop.
    # ═══════════════════════════════════════════════════════════════

    def action_en_ruta(self, notificar=True):
        ahora = fields.Datetime.now()
        for ticket in self:
            if ticket.estado not in ('proceso',):
                raise UserError(_(
                    "Solo se puede marcar En Ruta un ticket asignado.\n"
                    "Estado actual: %s"
                ) % ticket.estado)
            vals = {'estado': 'en_ruta'}
            if not ticket.fecha_en_ruta:
                vals['fecha_en_ruta'] = ahora
            ticket.write(vals)
            ticket._registrar_evento(
                f"Tecnico {ticket.responsable.name or 'N/A'} en ruta"
            )
            if notificar:
                try:
                    ticket.notificar_en_ruta()
                except Exception as e:
                    _logger.error("[TRACKING] Error notificando en_ruta: %s", e)

    def action_en_sitio(self, notificar=True):
        ahora = fields.Datetime.now()
        for ticket in self:
            if ticket.estado not in ('proceso', 'en_ruta'):
                raise UserError(_(
                    "Solo se puede marcar En Sitio desde asignado o en ruta.\n"
                    "Estado actual: %s"
                ) % ticket.estado)
            vals = {'estado': 'en_sitio'}
            if not ticket.fecha_llegada:
                vals['fecha_llegada'] = ahora
            if not ticket.fecha_en_ruta:
                vals['fecha_en_ruta'] = ahora
            ticket.write(vals)
            ticket._registrar_evento(
                f"Tecnico {ticket.responsable.name or 'N/A'} llego al sitio"
            )
            if notificar:
                try:
                    ticket.notificar_en_sitio()
                except Exception as e:
                    _logger.error("[TRACKING] Error notificando en_sitio: %s", e)

    def action_en_revision(self):
        ahora = fields.Datetime.now()
        for ticket in self:
            if ticket.estado not in ('en_sitio',):
                raise UserError(_(
                    "Solo se puede iniciar revision cuando el tecnico esta en sitio.\n"
                    "Estado actual: %s"
                ) % ticket.estado)
            vals = {'estado': 'en_revision'}
            if not ticket.fecha_inicio_revision:
                vals['fecha_inicio_revision'] = ahora
            ticket.write(vals)
            ticket._registrar_evento(
                f"Tecnico {ticket.responsable.name or 'N/A'} inicio revision"
            )
            try:
                ticket.notificar_en_revision()
            except Exception as e:
                _logger.error("[TRACKING] Error notificando en_revision: %s", e)

    def action_registrar_salida_sitio(self, notificar=True):
        ahora = fields.Datetime.now()
        for ticket in self:
            if not ticket.fecha_salida_sitio:
                ticket.write({'fecha_salida_sitio': ahora})
                ticket._registrar_evento(
                    f"Tecnico {ticket.responsable.name or 'N/A'} salio del sitio"
                )
                if notificar:
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
                f"Ticket asignado a {ticket.responsable.name or 'N/A'}"
            )
        return super().action_proceso()

    def _registrar_finalizacion_tracking(self):
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
            ticket._registrar_evento("Ticket finalizado")
            ticket._geocerca_borrar()
            try:
                ticket.notificar_finalizado()
            except Exception as e:
                _logger.error("[TRACKING] Error notificando finalizado: %s", e)

    # ═══════════════════════════════════════════════════════════════
    #  CRONS — RED DE SEGURIDAD GPS
    # ═══════════════════════════════════════════════════════════════

    @api.model
    def cron_gps_detectar_movimiento(self):
        """
        Red de seguridad para deviceMoving.
        proceso → en_ruta si el tecnico esta en movimiento en Traccar.
        Frecuencia: cada 5 minutos.
        """
        _logger.info("[CRON-MOVIMIENTO] Iniciando verificacion de movimiento GPS")

        hoy_inicio, hoy_fin = self._get_rango_hoy()
        ahora   = fields.Datetime.now()
        ventana = timedelta(hours=2)

        tickets = self.sudo().search([
            ('estado', '=', 'proceso'),
            ('responsable', '!=', False),
            ('agenda', '>=', hoy_inicio),
            ('agenda', '<=', hoy_fin),
        ], order='agenda asc')

        if not tickets:
            _logger.info("[CRON-MOVIMIENTO] Sin tickets en proceso para hoy")
            return

        tecnicos_ids = tickets.mapped('responsable.id')
        vinculos = self.env['tecnico.dispositivo.gps'].sudo().search([
            ('user_id', 'in', tecnicos_ids),
            ('activo', '=', True),
        ])
        if not vinculos:
            return

        posiciones = self.env['traccar.api.service'].get_all_positions()
        if not posiciones:
            _logger.warning("[CRON-MOVIMIENTO] No se obtuvieron posiciones de Traccar")
            return

        mapa_tecnico_device = {v.user_id.id: v.traccar_device_id for v in vinculos}

        # Agrupar tickets por tecnico para enviar UNA notificación por tecnico
        tickets_por_tecnico = {}
        for ticket in tickets:
            tid = ticket.responsable.id
            tickets_por_tecnico.setdefault(tid, self.env['ticket.alquiler'])
            tickets_por_tecnico[tid] |= ticket

        procesados = 0

        for tecnico_id, tickets_tecnico in tickets_por_tecnico.items():
            try:
                device_id = mapa_tecnico_device.get(tecnico_id)
                if not device_id:
                    continue

                pos = posiciones.get(device_id)
                if not pos:
                    continue

                attrs  = pos.get('attributes', {})
                speed  = pos.get('speed', 0) or 0
                motion = attrs.get('motion', False)

                if not (speed > 1 or motion):
                    continue

                # Ubicación actual del técnico para incluir en notificación
                ubicacion_actual = {
                    'latitude':  pos.get('latitude'),
                    'longitude': pos.get('longitude'),
                    'speed':     speed,
                }

                ahora_local = fields.Datetime.now()
                marcados = self.env['ticket.alquiler']

                for ticket in tickets_tecnico:
                    diff       = ticket.agenda - ahora_local
                    ya_paso    = diff.total_seconds() < 0
                    esta_cerca = 0 <= diff.total_seconds() <= ventana.total_seconds()
                    if not ya_paso and not esta_cerca:
                        continue

                    _logger.info(
                        "[CRON-MOVIMIENTO] Tecnico %s en movimiento "
                        "(speed=%.1f motion=%s) -> en_ruta ticket %s",
                        ticket.responsable.name, speed, motion, ticket.name
                    )
                    # notificar=False → evitamos notif individual
                    ticket.sudo().action_en_ruta(notificar=False)
                    ticket._registrar_evento(
                        f"En ruta detectado por cron GPS "
                        f"(speed={speed:.1f} motion={motion})"
                    )
                    marcados |= ticket
                    procesados += 1

                # UNA notificación grupal por técnico
                if marcados:
                    try:
                        marcados[0].notificar_en_ruta(
                            tickets_grupo=marcados,
                            ubicacion_actual=ubicacion_actual,
                        )
                    except Exception as e:
                        _logger.error("[CRON-MOVIMIENTO] Error notificando en_ruta: %s", e)

            except Exception as e:
                _logger.error("[CRON-MOVIMIENTO] Error tecnico ID %s: %s", tecnico_id, e)

        _logger.info("[CRON-MOVIMIENTO] Completado — %d tickets marcados en_ruta", procesados)

    @api.model
    def cron_gps_detectar_llegada(self):
        """
        Red de seguridad para geofenceEnter.
        en_ruta/proceso → en_sitio si tecnico esta dentro de geocerca.
        Frecuencia: cada 3 minutos.
        """
        _logger.info("[CRON-LLEGADA] Iniciando verificacion de llegada GPS")

        hoy_inicio, hoy_fin = self._get_rango_hoy()

        tickets = self.sudo().search([
            ('estado', 'in', ['en_ruta', 'proceso']),
            ('responsable', '!=', False),
            ('traccar_geofence_id', '!=', 0),
            ('traccar_geofence_id', '!=', False),
            ('agenda', '>=', hoy_inicio),
            ('agenda', '<=', hoy_fin),
        ], order='agenda asc')

        if not tickets:
            _logger.info("[CRON-LLEGADA] Sin tickets candidatos para verificar llegada")
            return

        tecnicos_ids = tickets.mapped('responsable.id')
        vinculos = self.env['tecnico.dispositivo.gps'].sudo().search([
            ('user_id', 'in', tecnicos_ids),
            ('activo', '=', True),
        ])
        if not vinculos:
            return

        posiciones = self.env['traccar.api.service'].get_all_positions()
        if not posiciones:
            _logger.warning("[CRON-LLEGADA] No se obtuvieron posiciones de Traccar")
            return

        mapa_tecnico_device = {v.user_id.id: v.traccar_device_id for v in vinculos}

        tickets_por_tecnico = {}
        for ticket in tickets:
            tid = ticket.responsable.id
            tickets_por_tecnico.setdefault(tid, self.env['ticket.alquiler'])
            tickets_por_tecnico[tid] |= ticket

        procesados = 0
        for tecnico_id, tickets_tecnico in tickets_por_tecnico.items():
            try:
                device_id = mapa_tecnico_device.get(tecnico_id)
                if not device_id:
                    continue

                pos = posiciones.get(device_id)
                if not pos:
                    continue

                geofence_ids_activos = pos.get('geofenceIds') or []
                ubicacion_actual = {
                    'latitude':  pos.get('latitude'),
                    'longitude': pos.get('longitude'),
                }

                for ticket in tickets_tecnico:
                    if ticket.traccar_geofence_id in geofence_ids_activos:
                        _logger.info(
                            "[CRON-LLEGADA] Tecnico %s dentro geocerca %s -> en_sitio %s",
                            ticket.responsable.name,
                            ticket.traccar_geofence_id,
                            ticket.name,
                        )
                        tickets_visita = ticket._get_tickets_misma_visita(tickets_tecnico)
                        marcados = self.env['ticket.alquiler']
                        for t in tickets_visita:
                            if t.estado in ('en_ruta', 'proceso'):
                                # notificar=False → evitamos notif individual
                                t.sudo().action_en_sitio(notificar=False)
                                t._registrar_evento(
                                    f"Llegada detectada por cron GPS "
                                    f"(geocerca ID:{ticket.traccar_geofence_id})"
                                )
                                marcados |= t
                                procesados += 1

                        # UNA notificación grupal por visita/cliente
                        if marcados:
                            try:
                                marcados[0].notificar_en_sitio(
                                    tickets_grupo=marcados,
                                    ubicacion_actual=ubicacion_actual,
                                )
                            except Exception as e:
                                _logger.error("[CRON-LLEGADA] Error notificando en_sitio: %s", e)
                        break

            except Exception as e:
                _logger.error(
                    "[CRON-LLEGADA] Error tecnico ID %s: %s", tecnico_id, e
                )

        _logger.info("[CRON-LLEGADA] Completado — %d tickets marcados en_sitio", procesados)

    @api.model
    def cron_gps_detectar_salida(self):
        """
        Red de seguridad para geofenceExit.
        en_sitio/en_revision → salida si tecnico ya NO esta en geocerca.
        Frecuencia: cada 5 minutos.
        """
        _logger.info("[CRON-SALIDA] Iniciando verificacion de salida GPS")

        hoy_inicio, hoy_fin = self._get_rango_hoy()

        tickets = self.sudo().search([
            ('estado', 'in', ['en_sitio', 'en_revision']),
            ('responsable', '!=', False),
            ('fecha_salida_sitio', '=', False),
            ('traccar_geofence_id', '!=', 0),
            ('traccar_geofence_id', '!=', False),
            ('agenda', '>=', hoy_inicio),
            ('agenda', '<=', hoy_fin),
        ], order='agenda asc')

        if not tickets:
            _logger.info("[CRON-SALIDA] Sin tickets en sitio para verificar salida")
            return

        tecnicos_ids = tickets.mapped('responsable.id')
        vinculos = self.env['tecnico.dispositivo.gps'].sudo().search([
            ('user_id', 'in', tecnicos_ids),
            ('activo', '=', True),
        ])
        if not vinculos:
            return

        posiciones = self.env['traccar.api.service'].get_all_positions()
        if not posiciones:
            _logger.warning("[CRON-SALIDA] No se obtuvieron posiciones de Traccar")
            return

        mapa_tecnico_device = {v.user_id.id: v.traccar_device_id for v in vinculos}

        tickets_por_tecnico = {}
        for ticket in tickets:
            tid = ticket.responsable.id
            tickets_por_tecnico.setdefault(tid, self.env['ticket.alquiler'])
            tickets_por_tecnico[tid] |= ticket

        procesados = 0
        for tecnico_id, tickets_tecnico in tickets_por_tecnico.items():
            try:
                device_id = mapa_tecnico_device.get(tecnico_id)
                if not device_id:
                    continue

                pos = posiciones.get(device_id)
                if not pos:
                    continue

                geofence_ids_activos = pos.get('geofenceIds') or []
                ubicacion_actual = {
                    'latitude':  pos.get('latitude'),
                    'longitude': pos.get('longitude'),
                }

                for ticket in tickets_tecnico:
                    if ticket.traccar_geofence_id not in geofence_ids_activos:
                        _logger.info(
                            "[CRON-SALIDA] Tecnico %s fuera geocerca %s -> salida %s",
                            ticket.responsable.name,
                            ticket.traccar_geofence_id,
                            ticket.name,
                        )
                        tickets_visita = ticket._get_tickets_misma_visita(tickets_tecnico)
                        tickets_salida = tickets_visita.filtered(
                            lambda t: not t.fecha_salida_sitio
                        )
                        marcados = self.env['ticket.alquiler']
                        for t in tickets_salida:
                            # notificar=False → evitamos notif individual
                            t.sudo().action_registrar_salida_sitio(notificar=False)
                            t._registrar_evento(
                                f"Salida detectada por cron GPS "
                                f"(geocerca ID:{ticket.traccar_geofence_id})"
                            )
                            marcados |= t
                            procesados += 1

                        # UNA notificación grupal por visita/cliente
                        if marcados:
                            try:
                                marcados[0].notificar_salida_sitio(
                                    tickets_grupo=marcados,
                                    ubicacion_actual=ubicacion_actual,
                                )
                            except Exception as e:
                                _logger.error("[CRON-SALIDA] Error notificando salida: %s", e)

                        # Siguiente ticket en_ruta automatico
                        todos_hoy = self.sudo().search([
                            ('responsable', '=', tecnico_id),
                            ('estado', 'in', ['proceso', 'en_ruta', 'en_sitio', 'en_revision']),
                            ('agenda', '>=', hoy_inicio),
                            ('agenda', '<=', hoy_fin),
                        ], order='agenda asc')
                        siguiente = todos_hoy.filtered(lambda t: t.estado == 'proceso')
                        if siguiente:
                            sig = siguiente[0]
                            try:
                                sig.sudo().action_en_ruta(notificar=False)
                                sig._registrar_evento(
                                    "En ruta automatico por cron — salida del servicio anterior"
                                )
                                # Notificación del siguiente con ubicación actual
                                try:
                                    sig.notificar_en_ruta(
                                        tickets_grupo=sig,
                                        ubicacion_actual=ubicacion_actual,
                                    )
                                except Exception as e:
                                    _logger.error(
                                        "[CRON-SALIDA] Error notificando siguiente: %s", e
                                    )
                            except Exception as e:
                                _logger.error(
                                    "[CRON-SALIDA] Error marcando siguiente en_ruta: %s", e
                                )
                        break

            except Exception as e:
                _logger.error("[CRON-SALIDA] Error tecnico ID %s: %s", tecnico_id, e)

        _logger.info("[CRON-SALIDA] Completado — %d tickets con salida registrada", procesados)

    @api.model
    def cron_actualizar_en_revision(self):
        """
        en_sitio con fecha_llegada hace mas de 15 min -> en_revision.
        Frecuencia: cada 5 minutos.
        """
        umbral = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'tracking.minutos_para_revision', '15'
            )
        )
        limite  = fields.Datetime.now() - timedelta(minutes=umbral)
        tickets = self.sudo().search([
            ('estado', '=', 'en_sitio'),
            ('fecha_llegada', '<=', limite),
            ('fecha_inicio_revision', '=', False),
        ])
        if not tickets:
            return
        _logger.info("[CRON-REVISION] %d tickets -> en_revision automatico", len(tickets))
        for ticket in tickets:
            try:
                ticket.action_en_revision()
            except Exception as e:
                _logger.error("[CRON-REVISION] Error en %s: %s", ticket.name, e)
                ticket._registrar_evento(f"Error cron en_revision: {str(e)}")

    # ═══════════════════════════════════════════════════════════════
    #  API GPS (webhook Traccar)
    # ═══════════════════════════════════════════════════════════════

    @api.model
    def api_actualizar_estado_gps(self, tecnico_traccar_device_id, evento_tipo, datos=None):
        datos = datos or {}
        _logger.info(
            "[GPS-API] device=%s tipo=%s lat=%s lon=%s geofence_id=%s",
            tecnico_traccar_device_id, evento_tipo,
            datos.get('latitude'), datos.get('longitude'),
            datos.get('geofenceId'),
        )
        vinculo = self.env['tecnico.dispositivo.gps'].sudo().search([
            ('traccar_device_id', '=', tecnico_traccar_device_id),
            ('activo', '=', True),
        ], limit=1)
        if not vinculo:
            _logger.warning("[GPS-API] Sin tecnico para device_id=%s", tecnico_traccar_device_id)
            return {'success': False, 'error': f'Sin tecnico para dispositivo {tecnico_traccar_device_id}'}

        tecnico    = vinculo.user_id
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
                    'message': f'Sin tickets HOY. Ignorados: {detalle}',
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
                t.sudo()._registrar_evento(f"Error GPS [{evento_tipo}]: {str(e)}")
            return {'success': False, 'error': str(e), 'tickets_actualizados': []}

        return {
            'success': True,
            'tecnico': tecnico.name,
            'evento':  evento_tipo,
            'tickets_actualizados': [
                {'id': t.id, 'name': t.name, 'estado': t.estado}
                for t in actualizados
            ],
        }

    def _gps_procesar_llegada(self, tickets_hoy, datos):
        geofence_id  = datos.get('geofenceId')
        lat_tec      = datos.get('latitude')
        lon_tec      = datos.get('longitude')
        actualizados = self.env['ticket.alquiler']

        # Ubicación actual del técnico (viene del webhook)
        ubicacion_actual = {
            'latitude':  lat_tec,
            'longitude': lon_tec,
        }

        candidatos = tickets_hoy.filtered(lambda t: t.estado in ('proceso', 'en_ruta'))
        if not candidatos:
            estados = ', '.join(set(tickets_hoy.mapped('estado')))
            for t in tickets_hoy:
                t._registrar_evento(f"geofenceEnter ignorado — sin candidatos (estados: {estados})")
            return actualizados

        ticket_match = None
        metodo_match = None

        if geofence_id:
            for ticket in candidatos:
                if ticket.traccar_geofence_id == geofence_id:
                    ticket_match = ticket
                    metodo_match = f"geocerca automatica ID:{geofence_id}"
                    break

        if not ticket_match and lat_tec and lon_tec:
            for ticket in candidatos:
                lat_eq = getattr(ticket, 'equipo_latitud', None)
                lon_eq = getattr(ticket, 'equipo_longitud', None)
                if lat_eq and lon_eq:
                    dist = self._haversine_metros(lat_tec, lon_tec, lat_eq, lon_eq)
                    if dist <= 200:
                        ticket_match = ticket
                        metodo_match = f"proximidad GPS ({dist:.0f}m)"
                        break
                    else:
                        ticket._registrar_evento(
                            f"Tecnico a {dist:.0f}m del equipo (min 200m)"
                        )

        if not ticket_match:
            ticket_match = candidatos[0]
            metodo_match = "fallback — sin geocerca ni coordenadas"
            _logger.warning(
                "[GPS-LLEGADA] Fallback para ticket %s | geofence=%s lat=%s lon=%s",
                ticket_match.name, geofence_id, lat_tec, lon_tec,
            )

        tickets_visita = ticket_match._get_tickets_misma_visita(candidatos)

        # Marcar todos sin notificar individualmente
        for ticket in tickets_visita:
            ticket.sudo().action_en_sitio(notificar=False)
            ticket._registrar_evento(f"Llegada registrada — metodo: {metodo_match}")
            actualizados |= ticket

        # UNA sola notificación grupal con ubicación actual
        if actualizados:
            try:
                actualizados[0].notificar_en_sitio(
                    tickets_grupo=actualizados,
                    ubicacion_actual=ubicacion_actual,
                )
            except Exception as e:
                _logger.error("[GPS] Error notificando en_sitio grupal: %s", e)

        return actualizados

    def _gps_procesar_salida(self, tickets_hoy, datos):
        actualizados = self.env['ticket.alquiler']

        ubicacion_actual = {
            'latitude':  datos.get('latitude'),
            'longitude': datos.get('longitude'),
        }

        en_sitio_o_revision = tickets_hoy.filtered(
            lambda t: t.estado in ('en_sitio', 'en_revision')
        )
        if not en_sitio_o_revision:
            for t in tickets_hoy:
                t._registrar_evento("geofenceExit ignorado — ningun ticket en sitio/revision")
            return actualizados

        clientes_procesados = set()
        tickets_salida = self.env['ticket.alquiler']
        for ticket in en_sitio_o_revision:
            clave = (ticket.partner_id.id, ticket.agenda.date() if ticket.agenda else None)
            if clave not in clientes_procesados:
                clientes_procesados.add(clave)
                tickets_salida |= ticket._get_tickets_misma_visita(en_sitio_o_revision)

        # Marcar salida sin notificar individualmente
        for ticket in tickets_salida:
            ticket.sudo().action_registrar_salida_sitio(notificar=False)
            actualizados |= ticket

        # UNA sola notificación grupal con ubicación actual
        if actualizados:
            try:
                actualizados[0].notificar_salida_sitio(
                    tickets_grupo=actualizados,
                    ubicacion_actual=ubicacion_actual,
                )
            except Exception as e:
                _logger.error("[GPS] Error notificando salida grupal: %s", e)

        siguiente = tickets_hoy.filtered(lambda t: t.estado == 'proceso')
        if siguiente:
            sig = siguiente[0]
            try:
                sig.sudo().action_en_ruta(notificar=False)
                sig._registrar_evento("En ruta automatico — salida del servicio anterior")
                try:
                    # Notificación siguiente también con ubicación actual
                    actualizados[0].notificar_siguiente_en_ruta(
                        sig,
                        ubicacion_actual=ubicacion_actual,
                    )
                except Exception as e:
                    _logger.error("[GPS] Error notificando siguiente: %s", e)
            except Exception as e:
                _logger.error("[GPS-SECUENCIAL] Error marcando siguiente en_ruta: %s", e)
                sig._registrar_evento(f"Error al marcar en_ruta automatico: {str(e)}")
        else:
            if actualizados:
                actualizados[0]._registrar_evento("Ultimo servicio del dia completado")

        return actualizados

    def _gps_procesar_movimiento(self, tickets_hoy, datos):
        actualizados = self.env['ticket.alquiler']
        ahora   = fields.Datetime.now()
        ventana = timedelta(hours=2)

        ubicacion_actual = {
            'latitude':  datos.get('latitude'),
            'longitude': datos.get('longitude'),
            'speed':     datos.get('speed', 0),
        }

        ya_en_ruta = tickets_hoy.filtered(lambda t: t.estado == 'en_ruta')
        if ya_en_ruta:
            return actualizados

        for ticket in tickets_hoy.filtered(lambda t: t.estado == 'proceso'):
            if not ticket.agenda:
                continue
            diff       = ticket.agenda - ahora
            ya_paso    = diff.total_seconds() < 0
            esta_cerca = 0 <= diff.total_seconds() <= ventana.total_seconds()
            if ya_paso or esta_cerca:
                # notificar=False → evitamos notif individual
                ticket.sudo().action_en_ruta(notificar=False)
                ticket._registrar_evento("En ruta detectado por movimiento GPS")
                actualizados |= ticket
                break
            else:
                h = int(diff.total_seconds() / 3600)
                m = int((diff.total_seconds() % 3600) / 60)
                ticket._registrar_evento(
                    f"deviceMoving ignorado — agenda en {h}h {m}min (ventana: 2h)"
                )

        # UNA sola notificación grupal con ubicación actual
        if actualizados:
            try:
                actualizados[0].notificar_en_ruta(
                    tickets_grupo=actualizados,
                    ubicacion_actual=ubicacion_actual,
                )
            except Exception as e:
                _logger.error("[GPS] Error notificando en_ruta grupal: %s", e)

        return actualizados

    # ═══════════════════════════════════════════════════════════════
    #  HELPERS ESTATICOS
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _get_rango_hoy():
        from pytz import timezone as pytz_tz, UTC as pytz_UTC
        lima     = pytz_tz('America/Lima')
        hoy_lima = date.today()
        inicio_lima = lima.localize(fields.Datetime.from_string(f"{hoy_lima} 00:00:00"))
        fin_lima    = lima.localize(fields.Datetime.from_string(f"{hoy_lima} 23:59:59"))
        return (
            inicio_lima.astimezone(pytz_UTC).replace(tzinfo=None),
            fin_lima.astimezone(pytz_UTC).replace(tzinfo=None),
        )

    @staticmethod
    def _haversine_metros(lat1, lon1, lat2, lon2):
        R    = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi      = math.radians(lat2 - lat1)
        d_lambda   = math.radians(lon2 - lon1)
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
            f"Resumen — {self.name}",
            f"Tecnico: {self.responsable.name or 'N/A'}",
            f"Cliente: {self.partner_id.name or 'N/A'}",
            "",
            f"Asignado:  {fmt_hora(self.fecha_asignacion)}",
            f"Agendado:  {fmt_hora(self.agenda)}",
            f"En ruta:   {fmt_hora(self.fecha_en_ruta)}",
            f"Llegada:   {fmt_hora(self.fecha_llegada)}",
            f"Revision:  {fmt_hora(self.fecha_inicio_revision)}",
            f"Salida:    {fmt_hora(self.fecha_salida_sitio)}",
            f"Finalizado:{fmt_hora(self.fecha_finalizacion)}",
            "",
            f"Traslado:  {fmt_min(self.tiempo_traslado_minutos)}",
            f"En sitio:  {fmt_min(self.tiempo_en_sitio_minutos)}",
            f"Total:     {fmt_min(self.tiempo_total_atencion_minutos)}",
        ]

        if self.fecha_llegada and self.agenda:
            if self.es_puntual:
                lines.append("Puntualidad: A tiempo")
            elif self.diferencia_puntualidad_minutos > 0:
                lines.append(f"Llego {fmt_min(self.diferencia_puntualidad_minutos)} tarde")
            else:
                lines.append(f"Llego {fmt_min(abs(self.diferencia_puntualidad_minutos))} antes")

        return '\n'.join(lines)