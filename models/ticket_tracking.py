# -*- coding: utf-8 -*-
"""
Tracking GPS de técnicos en campo.
Corrección: fechas por transición real de estado, diagnóstico persistente,
fecha local de Lima y salida GPS separada del cierre del servicio.
La salida física no reemplaza las validaciones de action_finalizar.
"""
import math
import logging
import requests
from datetime import timedelta, datetime, timezone

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Umbrales para confirmar salida física sin preguntar
UMBRAL_MINUTOS_SITIO = 60   # minutos mínimos en sitio
UMBRAL_METROS_SALIDA = 2000  # 2 km de distancia para confirmar salida


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

    
    _traccar_device_unique = models.Constraint(
        'UNIQUE(traccar_device_id)',
        'Este dispositivo de Traccar ya está vinculado a otro técnico.',
    )



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
    gps_geofence_device_id = fields.Integer(string='Dispositivo vinculado a geocerca', readonly=True, copy=False)
    gps_salida_detectada_utc = fields.Datetime(string='Detección GPS de retiro', readonly=True, copy=False)
    gps_aviso_retiro_estado = fields.Selection([('pendiente', 'Pendiente'), ('solicitado', 'Solicitado al proveedor'), ('error', 'Error de envío')], string='Estado aviso de retiro', readonly=True, copy=False)
    gps_aviso_retiro_error = fields.Text(string='Error aviso retiro', readonly=True, copy=False)
    gps_salida_fuente = fields.Selection([('webhook', 'Evento Traccar'), ('cron', 'Observación GPS'), ('manual', 'Confirmación manual')], string='Fuente detección de retiro', readonly=True, copy=False)
    gps_salida_latitud = fields.Float(string='Latitud última detección', digits=(10, 7), readonly=True, copy=False)
    gps_salida_longitud = fields.Float(string='Longitud última detección', digits=(10, 7), readonly=True, copy=False)
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
        # Completar solo la fecha del estado que realmente se está registrando.
        # No reconstruir horarios anteriores con la hora actual.
        ahora = fields.Datetime.now()
        campos_estado = {
            'en_ruta': 'fecha_en_ruta',
            'en_sitio': 'fecha_llegada',
            'en_revision': 'fecha_inicio_revision',
            'finalizado': 'fecha_finalizacion',
        }
        resultado = True
        for rec in self:
            anterior = rec.estado
            tecnico_anterior = rec.responsable.id
            valores = dict(vals)
            nuevo_estado = valores.get('estado')
            cambio_estado = 'estado' in valores and nuevo_estado != anterior
            campo = campos_estado.get(nuevo_estado) if cambio_estado else None
            if campo and not valores.get(campo) and not rec[campo]:
                if nuevo_estado in ('en_ruta', 'en_sitio') and rec.gps_visita_id:
                    origen = rec.gps_visita_id.fecha_en_ruta if nuevo_estado == 'en_ruta' else rec.gps_visita_id.fecha_llegada
                    if not origen:
                        raise UserError(_('La visita no tiene evento físico verificado para este estado.'))
                    valores[campo] = origen
                elif nuevo_estado not in ('en_ruta', 'en_sitio'):
                    valores[campo] = ahora
            if (valores.get('responsable') and not rec.fecha_asignacion
                    and not valores.get('fecha_asignacion')):
                valores['fecha_asignacion'] = ahora
            resultado = super(TicketAlquilerTracking, rec).write(valores) and resultado
            if cambio_estado:
                rec._registrar_evento(
                    f"Estado: {anterior} → {rec.estado}. "
                    f"Registrado por: {self.env.user.name}"
                )
            if 'responsable' in vals:
                tecnico_cambio = tecnico_anterior != rec.responsable.id
                if tecnico_cambio:
                    rec._registrar_evento(
                        f"Responsable actualizado: {rec.responsable.name or 'Sin asignar'}"
                    )
                if tecnico_cambio and rec.responsable and rec.equipo_tiene_coordenadas:
                    if not rec.traccar_geofence_id or rec._geocerca_borrar():
                        rec._geocerca_crear()
        return resultado

    # ═══════════════════════════════════════════════════════════════
    #  GEOCERCAS
    # ═══════════════════════════════════════════════════════════════

    def _geocerca_crear(self):
        self.ensure_one()
        if not self.equipo_latitud or not self.equipo_longitud:
            self._registrar_evento('Geocerca pendiente: faltan coordenadas del equipo')
            return False
        if not self.responsable:
            self._registrar_evento('Geocerca pendiente: falta asignar responsable')
            return False
        vinculo = self.env['tecnico.dispositivo.gps'].sudo().search([
            ('user_id', '=', self.responsable.id),
            ('activo', '=', True),
        ], limit=1)
        if not vinculo:
            self._registrar_evento(
                f"Geocerca pendiente: {self.responsable.name} no tiene dispositivo GPS activo vinculado"
            )
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
        vinculado = traccar.vincular_geocerca_dispositivo(
            geofence_id=geofence_id,
            device_id=vinculo.traccar_device_id,
        )
        if not vinculado:
            traccar.borrar_geocerca(geofence_id)
            self._registrar_evento('Geocerca no vinculada; no se registró como activa')
            return False
        self.sudo().write({'traccar_geofence_id': geofence_id, 'gps_geofence_device_id': vinculo.traccar_device_id})
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
        gid = self.traccar_geofence_id
        device_id = self.gps_geofence_device_id
        api = self.env['traccar.api.service']
        # Retener referencias si Traccar está inaccesible; evitar geocercas huérfanas.
        if device_id and not api.desvincular_geocerca_dispositivo(gid, device_id):
            self._registrar_evento('Geocerca no eliminada: falló desvinculación en Traccar')
            return False
        if not api.borrar_geocerca(gid):
            self._registrar_evento('Geocerca pendiente de eliminación en Traccar')
            return False
        self.sudo().write({'traccar_geofence_id': 0, 'gps_geofence_device_id': 0})
        self._registrar_evento(f'Geocerca Traccar ID:{gid} eliminada')
        return True

    def action_crear_geocerca_manual(self):
        self.ensure_one()
        if self.traccar_geofence_id and not self._geocerca_borrar():
            raise UserError('No se pudo retirar la geocerca anterior en Traccar.')
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
            fin_sitio = rec.fecha_salida_sitio
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
                rec.es_puntual = rec.diferencia_puntualidad_minutos <= 15
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

    def _registrar_impedimento_tracking(self, mensaje):
        for ticket in self:
            ultima = (ticket.tracking_log or '').splitlines()
            if not ultima or not ultima[-1].endswith(mensaje):
                ticket._registrar_evento(mensaje)

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
            and (not self.equipo_latitud or not self.equipo_longitud
                 or (t.equipo_latitud and t.equipo_longitud
                     and self._haversine_metros(self.equipo_latitud, self.equipo_longitud,
                                                t.equipo_latitud, t.equipo_longitud) <= 200))
        ))
        return misma_visita if misma_visita else self

    @staticmethod
    def _gps_fecha_evento(datos):
        """Solo devuelve una hora de evento explícita; nunca usa serverTime/fixTime como sustitutos."""
        valor = (datos or {}).get('eventTime')
        if not valor:
            return None
        try:
            if isinstance(valor, datetime):
                dt = valor
            else:
                dt = datetime.fromisoformat(str(valor).strip().replace('Z', '+00:00'))
            if not dt.tzinfo:
                return None
            utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
            if utc > fields.Datetime.now() + timedelta(minutes=2):
                return None
            return utc
        except (ValueError, TypeError, OverflowError):
            return None

    @staticmethod
    def _gps_posicion_valida(pos, max_edad_min=10):
        """Para crons: la antigüedad y validez de una posición son obligatorias."""
        if not pos or pos.get('valid') is not True:
            return False
        valor = pos.get('fixTime')
        if not valor:
            return False
        try:
            dt = datetime.fromisoformat(str(valor).replace('Z', '+00:00'))
            if not dt.tzinfo:
                return False
            edad = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
            return -120 <= edad <= max_edad_min * 60
        except (ValueError, TypeError, OverflowError):
            return False

    def _registrar_deteccion_salida(self, lat=None, lon=None, fecha_evento=None, fuente='cron'):
        """Detección != salida confirmada, != ticket finalizado."""
        self.ensure_one()
        if self.fecha_salida_sitio:
            return
        if self.gps_salida_detectada_utc and fecha_evento and fecha_evento >= self.gps_salida_detectada_utc:
            return
        vals = {'gps_salida_fuente': fuente}
        if fecha_evento:
            vals['gps_salida_detectada_utc'] = fecha_evento
        # Si falta hora de evento, no presentar 'ahora' como hora GPS.
        if lat is not None:
            vals['gps_salida_latitud'] = lat
        if lon is not None:
            vals['gps_salida_longitud'] = lon
        self.sudo().write(vals)

    # ═══════════════════════════════════════════════════════════════
    #  LÓGICA DE RETIRO PENDIENTE (NUEVO v7)
    #
    #  Punto de entrada único: _evaluar_salida_geocerca()
    #  Llamado SOLO desde _gps_procesar_salida y cron_gps_detectar_salida
    #  en reemplazo de action_registrar_salida_sitio directo.
    #
    #  Reglas:
    #   1. Ya tiene token pendiente → no hacer nada, ya se preguntó
    #   2. Tiempo >= 60 min Y distancia >= 2 km → registrar salida física
    #   3. Cualquier otro caso → crear token y enviar link al técnico
    # ═══════════════════════════════════════════════════════════════

    def _evaluar_salida_geocerca(self, lat_actual=None, lon_actual=None,
                                fecha_evento=None, fuente='cron'):
        """Evalúa una DETECCIÓN de retiro; nunca finaliza el ticket.

        Si hay evidencia suficiente de permanencia + distancia y evento fechado,
        puede registrar salida. De otro modo requiere confirmación del técnico.
        """
        self.ensure_one()
        if self.fecha_salida_sitio:
            return 'salida_ya_registrada'
        self._registrar_deteccion_salida(lat_actual, lon_actual, fecha_evento, fuente)
        token_existente = self.env['ticket.retiro.token'].sudo().search([
            ('ticket_id', '=', self.id), ('estado', '=', 'pendiente'),
        ], limit=1)
        if token_existente:
            return 'ya_preguntado'
        if not self.fecha_llegada:
            self._registrar_evento('Retiro detectado sin llegada verificada; se solicita confirmación')
        referencia = fecha_evento or fields.Datetime.now()
        minutos = max(0.0, (referencia - self.fecha_llegada).total_seconds() / 60) if self.fecha_llegada else 0.0
        distancia = None
        if (lat_actual is not None and lon_actual is not None and
                self.equipo_latitud and self.equipo_longitud):
            distancia = self._haversine_metros(lat_actual, lon_actual,
                                               self.equipo_latitud, self.equipo_longitud)
        # Un geofenceExit acredita detección, no necesariamente retiro definitivo.
        # La confirmación se tramita mediante el token de retiro y la visita.
        # Usar API existente de tokens, sin inventar fechas de salida.
        token = self.env['ticket.retiro.token'].sudo().crear_token_retiro(
            ticket=self, lat=lat_actual, lon=lon_actual, tiempo_en_sitio=minutos,
        )
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        link = f"{base_url.rstrip('/')}/sat/retiro/{token.token}"
        self._registrar_evento('Posible retiro GPS detectado; esperando confirmación del técnico')
        try:
            aceptado = self.notificar_retiro_pendiente(link=link, tiempo_en_sitio=minutos)
            self.sudo().write({'gps_aviso_retiro_estado': 'solicitado' if aceptado else 'error',
                               'gps_aviso_retiro_error': False if aceptado else 'Proveedor no aceptó el envío'})
            self._registrar_evento('Solicitud de retiro aceptada por proveedor; entrega no verificada' if aceptado
                                   else 'ERROR: proveedor no aceptó el aviso de retiro')
        except Exception as e:
            _logger.exception('[RETIRO] Falló aviso ticket %s: %s', self.id, e)
            self.sudo().write({'gps_aviso_retiro_estado': 'error', 'gps_aviso_retiro_error': str(e)})
            self._registrar_evento(f'ERROR enviando confirmación de retiro: {e}')
        return 'token_enviado_o_intentado'

    def action_reenviar_aviso_retiro(self):
        """Reintento explícito si el proveedor falló, sin duplicar tokens."""
        for ticket in self:
            token = self.env['ticket.retiro.token'].sudo().search([
                ('ticket_id', '=', ticket.id), ('estado', '=', 'pendiente')
            ], limit=1)
            if not token:
                raise UserError('No existe solicitud de retiro pendiente para reenviar.')
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
            url = f"{base_url.rstrip('/')}/sat/retiro/{token.token}"
            minutos = max(0, (fields.Datetime.now() - ticket.fecha_llegada).total_seconds() / 60) if ticket.fecha_llegada else 0
            try:
                ticket.notificar_retiro_pendiente(link=url, tiempo_en_sitio=minutos)
                ticket.sudo().write({'gps_aviso_retiro_estado': 'solicitado', 'gps_aviso_retiro_error': False})
                ticket._registrar_evento('Reintento de aviso retiro solicitado al proveedor; entrega no verificada')
            except Exception as exc:
                ticket.sudo().write({'gps_aviso_retiro_estado': 'error', 'gps_aviso_retiro_error': str(exc)})
                ticket._registrar_evento(f'Fallo reintento aviso retiro: {exc}')
                raise UserError(f'No se pudo reenviar la notificación: {exc}') from exc
        return True

    def _cancelar_tokens_retiro_pendientes(self):
        """
        Cancela tokens pendientes del ticket cuando el técnico regresa a la geocerca.
        """
        self.ensure_one()
        tokens = self.env['ticket.retiro.token'].sudo().search([
            ('ticket_id', '=', self.id),
            ('estado',    '=', 'pendiente'),
        ])
        if tokens:
            for t in tokens:
                t.cancelar()
            self._registrar_evento(
                "Técnico regresó a la geocerca — confirmación de retiro cancelada"
            )
            try:
                self.notificar_retiro_cancelado()
            except Exception as e:
                _logger.error("[RETIRO] Error notificando cancelación: %s", e)

    # ═══════════════════════════════════════════════════════════════
    #  TRANSICIONES DE ESTADO
    #  Sin cambios respecto a v6
    # ═══════════════════════════════════════════════════════════════

    def action_en_ruta(self, notificar=True):
        """La ruta empieza en la visita; jamás por movimiento genérico."""
        for ticket in self:
            visita = ticket.gps_visita_id
            if not visita:
                raise UserError(_('Asigne una visita física antes de iniciar ruta.'))
            if visita.estado != 'en_ruta':
                raise UserError(_('Inicie el recorrido desde la visita física.'))
            visita._validar_siguiente_ruta()
            if ticket.estado == 'proceso':
                # La visita es dueña del horario. No generar una segunda fecha.
                ticket.write({'estado': 'en_ruta', 'fecha_en_ruta': visita.fecha_en_ruta})
        return True

    def action_en_sitio(self, notificar=True, fecha_evento=None):
        """La llegada física se registra y notifica UNA VEZ en la visita."""
        for ticket in self:
            visita = ticket.gps_visita_id
            if not visita:
                raise UserError(_('El ticket no está asociado a una visita física.'))
            if not visita.fecha_llegada:
                raise UserError(_('La visita no tiene llegada física confirmada.'))
            if ticket.estado in ('proceso', 'en_ruta'):
                ticket.write({'estado': 'en_sitio', 'fecha_llegada': visita.fecha_llegada})
            ticket._cancelar_tokens_retiro_pendientes()
        return True

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

    def action_registrar_salida_sitio(self, notificar=True, fecha_salida=None, fuente='manual'):
        """La visita confirma la salida; este método no finaliza servicios."""
        for ticket in self:
            visita = ticket.gps_visita_id
            if not visita:
                raise UserError(_('Vincule el ticket a una visita física.'))
            if visita.fecha_salida:
                if not ticket.fecha_salida_sitio:
                    ticket.write({'fecha_salida_sitio': visita.fecha_salida})
                continue
            # No se permite inventar fechas GPS a partir de la hora de Odoo.
            if fuente.lower() not in ('manual', 'confirmacion_manual', 'traccar'):
                raise UserError(_('Fuente de salida no reconocida.'))
            if fuente.lower() == 'traccar' and not fecha_salida:
                raise UserError(_('La salida GPS requiere fecha original del evento.'))
            fecha = fecha_salida or fields.Datetime.now()
            referencia = 'odoo-user:%s' % self.env.uid if fuente.lower() != 'traccar' else self.env.context.get('traccar_event_reference')
            if not referencia:
                raise UserError(_('Falta referencia verificable del evento GPS.'))
            visita.registrar_salida_confirmada(fecha, 'traccar' if fuente.lower() == 'traccar' else 'manual', referencia)
        return True

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
        self = self.filtered(lambda ticket: ticket.estado == 'finalizado')
        ahora = fields.Datetime.now()
        for ticket in self:
            vals = {}
            if not ticket.fecha_finalizacion:
                vals['fecha_finalizacion'] = ahora
            if vals:
                ticket.write(vals)
            ticket._registrar_evento("Ticket finalizado")
            if not ticket.gps_visita_id or ticket.gps_visita_id.estado in ('salida_confirmada', 'cancelada'):
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
        """El movimiento general del celular NO acredita desplazamiento hacia un ticket."""
        _logger.info('[CRON-MOVIMIENTO] Observación sin cambio de estado: no se inventa fecha en ruta')
        return True

    @api.model
    def cron_gps_detectar_llegada(self):
        """Detecta presencia confirmada mediante DOS posiciones recientes distintas.

        Si el webhook geofenceEnter no llegó (p.ej. técnico ya estaba dentro),
        permite registrar el instante de la segunda observación, NUNCA la hora
        histórica de entrada. No altera tickets sin visita vinculada o ante
        varias visitas candidatas. No usa coordenadas de otra geocerca.
        """
        posiciones = self.env['traccar.api.service'].get_all_positions()
        if not posiciones:
            return True
        ahora = fields.Datetime.now()
        parametros = self.env['ir.config_parameter'].sudo()
        Vinculo = self.env['tecnico.dispositivo.gps'].sudo()
        Visita = self.env['sat.visita.tecnica'].sudo()
        for vinculo in Vinculo.search([('activo', '=', True)]):
            try:
                pos = posiciones.get(vinculo.traccar_device_id)
                if not self._gps_posicion_valida(pos, max_edad_min=5):
                    continue
                lat = pos.get('latitude')
                lon = pos.get('longitude')
                if lat is None or lon is None:
                    continue
                lat, lon = float(lat), float(lon)
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                precision = pos.get('accuracy')
                if precision is None:
                    precision = (pos.get('attributes') or {}).get('accuracy')
                if precision is not None and float(precision) > 100:
                    continue
                fix = datetime.fromisoformat(str(pos['fixTime']).replace('Z', '+00:00'))
                fix_utc = fix.astimezone(timezone.utc).replace(tzinfo=None)
                if fix_utc > ahora + timedelta(minutes=2):
                    continue
                visitas = Visita.search([
                    ('tecnico_id', '=', vinculo.user_id.id),
                    ('estado', 'in', ['programada', 'en_ruta']),
                    ('agenda', '>=', ahora - timedelta(days=1)),
                    ('agenda', '<=', ahora + timedelta(days=1)),
                ])
                candidatos = visitas.filtered(lambda v: (
                    v.ticket_ids and v.latitud and v.longitud
                    and self._haversine_metros(lat, lon, v.latitud, v.longitud) <= 100
                    and any(t.traccar_geofence_id for t in v.ticket_ids)
                ))
                if len(candidatos) != 1:
                    if visitas and not candidatos:
                        _logger.info('[CRON-LLEGADA] Técnico %s: ninguna visita coincide con GPS actual', vinculo.user_id.id)
                    continue
                visita = candidatos[0]
                # Verificar además la geocerca efectiva del ticket (no otro círculo).
                gids = (pos.get('geofenceIds') if isinstance(pos.get('geofenceIds'), list) else None)
                ids_visita = {t.traccar_geofence_id for t in visita.ticket_ids if t.traccar_geofence_id}
                if gids is not None and not ids_visita.intersection(set(gids)):
                    continue
                clave = 'sat.gps.presencia.%s.%s' % (vinculo.traccar_device_id, visita.id)
                anterior = parametros.get_param(clave, default='')
                # Los puntos deben ser distintos y separados al menos 20 segundos.
                if not anterior:
                    parametros.set_param(clave, fix_utc.isoformat())
                    continue
                try:
                    primera = datetime.fromisoformat(anterior)
                except (ValueError, TypeError):
                    primera = False
                if not primera or (fix_utc - primera).total_seconds() > 300 or fix_utc < primera:
                    parametros.set_param(clave, fix_utc.isoformat())
                    continue
                if (fix_utc - primera).total_seconds() < 20:
                    continue
                if visita.fecha_en_ruta and fix_utc < visita.fecha_en_ruta:
                    continue
                referencia = 'traccar-position:%s@%s' % (pos.get('id'), fix_utc.isoformat())
                if visita.registrar_llegada_verificada(fix_utc, referencia, 'traccar'):
                    visita.ticket_ids.filtered(lambda t: t.estado in ('proceso', 'en_ruta')).action_en_sitio(notificar=False, fecha_evento=fix_utc)
                    _logger.info('[CRON-LLEGADA] Llegada observada por doble posición: visita=%s tecnico=%s', visita.id, vinculo.user_id.id)
                    # El cron y el webhook son caminos alternativos. La llegada
                    # solo se registra una vez; por ello no duplicamos el aviso.
                    principal = visita.ticket_ids[:1]
                    if principal:
                        try:
                            aceptado = principal.notificar_en_sitio(
                                tickets_grupo=visita.ticket_ids,
                                ubicacion_actual={'latitude': lat, 'longitude': lon},
                            )
                            visita._registrar_evento(
                                'aviso', 'whatsapp',
                                detalle=('Llegada por cron: solicitud aceptada' if aceptado
                                         else 'Llegada por cron: envío rechazado'),
                            )
                            _logger.info('[TRACKING-WA] Aviso de llegada por cron visita=%s aceptado=%s', visita.id, aceptado)
                        except Exception:
                            _logger.exception('[TRACKING-WA] Error notificando llegada por cron visita=%s', visita.id)
                parametros.set_param(clave, '')
            except Exception:
                _logger.exception('[CRON-LLEGADA] Error verificando técnico %s; no se modificó llegada por esta observación', vinculo.user_id.id)
        return True

    @api.model
    def cron_gps_detectar_salida(self):
        """Las instantáneas no acreditan salida histórica; no cambiar estados."""
        _logger.info('[CRON-GPS] Sin geofenceExit fechado no se confirma salida física')
        return True

    @api.model
    def cron_actualizar_en_revision(self):
        """Desactivado deliberadamente: permanencia no prueba inicio de revisión."""
        _logger.info('[CRON-REVISION] No se infiere revisión por el paso del tiempo')
        return True

    @api.model
    def api_actualizar_estado_gps(self, tecnico_traccar_device_id, evento_tipo, datos=None):
        datos = datos or {}
        datos['_fecha_evento_validada'] = self._gps_fecha_evento(datos)
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
        """Solo geofenceEnter explícito con visita y geocerca correspondiente."""
        resultado = self.env['ticket.alquiler']
        gid = datos.get('geofenceId')
        fecha = datos.get('_fecha_evento_validada')
        if not gid or not fecha:
            return resultado
        candidatos = tickets_hoy.filtered(lambda t: t.gps_visita_id and
            t.gps_visita_id.estado in ('programada', 'en_ruta') and
            t.traccar_geofence_id == gid)
        visitas = candidatos.mapped('gps_visita_id')
        if len(visitas) != 1:
            _logger.warning('[GPS] geofenceEnter no corresponde a visita única device/geofence=%s', gid)
            return resultado
        visita = visitas[0]
        ref = 'traccar-event:%s' % datos.get('eventId') if datos.get('eventId') else 'traccar-geofence:%s@%s' % (gid, fields.Datetime.to_string(fecha))
        if visita.registrar_llegada_verificada(fecha, ref, 'traccar'):
            visita.ticket_ids.filtered(lambda t: t.estado in ('proceso', 'en_ruta')).action_en_sitio(
                notificar=False, fecha_evento=fecha)
            resultado = visita.ticket_ids
            if resultado:
                try:
                    aceptado = resultado[0].notificar_en_sitio(
                        tickets_grupo=resultado, ubicacion_actual={
                            'latitude': datos.get('latitude'), 'longitude': datos.get('longitude')})
                    visita._registrar_evento('aviso', 'whatsapp', detalle='Solicitud aceptada' if aceptado else 'Envío rechazado')
                except Exception:
                    _logger.exception('[GPS] Error avisando llegada visita %s', visita.id)
        return resultado

    def _gps_procesar_salida(self, tickets_hoy, datos):
        """geofenceExit: solo visita correspondiente; sin finalizar tickets."""
        resultado = self.env['ticket.alquiler']
        gid = datos.get('geofenceId')
        fecha = datos.get('_fecha_evento_validada')
        if not gid or not fecha:
            return resultado
        candidatos = tickets_hoy.filtered(lambda t: t.gps_visita_id and
            t.gps_visita_id.estado in ('en_sitio', 'salida_pendiente') and
            t.traccar_geofence_id == gid)
        visitas = candidatos.mapped('gps_visita_id')
        if len(visitas) != 1:
            return resultado
        visita = visitas[0]
        if visita.fecha_llegada and fecha < visita.fecha_llegada:
            return resultado
        referencia = 'traccar-event:%s' % datos.get('eventId') if datos.get('eventId') else 'traccar-geofence:%s@%s' % (gid, fields.Datetime.to_string(fecha))
        if visita.estado == 'en_sitio':
            visita.registrar_salida_detectada(referencia=referencia)
        # No confirmar únicamente por 60 min o porque el dispositivo está lejos.
        # El técnico confirma mediante el token vigente, o una integración GPS
        # validada acepta evidencia inequívoca en el flujo de la visita.
        principal = visita.ticket_ids[:1]
        if principal:
            t = principal[0]
            if not t.fecha_salida_sitio:
                t._evaluar_salida_geocerca(datos.get('latitude'), datos.get('longitude'),
                                           fecha_evento=fecha, fuente='webhook')
            resultado = visita.ticket_ids
        return resultado

    def _gps_procesar_movimiento(self, tickets_hoy, datos):
        """deviceMoving no permite determinar a cuál cliente se dirige el técnico."""
        return self.env['ticket.alquiler']

    @staticmethod
    def _get_rango_hoy():
        from pytz import timezone as pytz_tz, UTC as pytz_UTC
        lima     = pytz_tz('America/Lima')
        hoy_lima = fields.Datetime.now().replace(tzinfo=pytz_UTC).astimezone(lima).date()
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