# -*- coding: utf-8 -*-

import hashlib
import logging
import secrets

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================

def _clean_text(value):
    if value in (None, False):
        return ''
    return str(value).strip()


def _hash_token(token):
    token = _clean_text(token)

    if not token:
        return ''

    return hashlib.sha256(
        token.encode('utf-8')
    ).hexdigest()


# ============================================================
# AGENTE DE MONITOREO
# ============================================================

class SatMonitoringAgent(models.Model):
    """
    Agente instalado en la red del cliente.

    Responsabilidades conceptuales:

        - autenticarse contra Odoo
        - obtener redes asignadas
        - obtener equipos conocidos
        - obtener perfiles SNMP
        - hacer discovery
        - hacer polling
        - enviar snapshots
        - enviar lecturas
        - enviar alertas
        - reportar estado propio

    IMPORTANTE:
    El token real NO se almacena en texto plano.
    """

    _name = 'sat.monitoring.agent'
    _description = 'Agente de monitoreo SNMP'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'online desc, last_seen desc, name, id'

    # ========================================================
    # IDENTIFICACIÓN
    # ========================================================

    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True,
        index=True,
        help=(
            'Nombre administrativo del agente.\n'
            'Ejemplo: Agente CONSORCIO S&F - Lima.'
        ),
    )

    code = fields.Char(
        string='Código técnico',
        required=True,
        copy=False,
        tracking=True,
        index=True,
        help=(
            'Código estable utilizado por API.\n'
            'Ejemplo: consorcio_sf_lima_01.'
        ),
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
        tracking=True,
        index=True,
    )

    enabled = fields.Boolean(
        string='Habilitado',
        default=True,
        tracking=True,
        index=True,
        help=(
            'Si se desactiva, el agente no debe recibir '
            'configuración ni enviar monitoreo.'
        ),
    )

    # ========================================================
    # CLIENTE / UBICACIÓN
    # ========================================================

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        ondelete='set null',
        tracking=True,
        index=True,
    )

    branch_name = fields.Char(
        string='Sede',
        tracking=True,
        index=True,
    )

    location_description = fields.Char(
        string='Ubicación',
        tracking=True,
        help=(
            'Ubicación física o lógica del dispositivo donde '
            'corre el agente.'
        ),
    )

    # ========================================================
    # TOKEN
    # ========================================================

    token_hash = fields.Char(
        string='Hash token',
        readonly=True,
        copy=False,
        index=True,
    )

    token_preview = fields.Char(
        string='Token',
        readonly=True,
        copy=False,
        help=(
            'Solo muestra una referencia parcial. '
            'El token completo se entrega únicamente al generarlo.'
        ),
    )

    token_generated_at = fields.Datetime(
        string='Token generado',
        readonly=True,
        copy=False,
    )

    token_generated_by = fields.Many2one(
        'res.users',
        string='Token generado por',
        readonly=True,
        copy=False,
    )

    token_last_used_at = fields.Datetime(
        string='Último uso token',
        readonly=True,
        copy=False,
    )

    # ========================================================
    # IDENTIDAD REPORTADA
    # ========================================================

    hostname = fields.Char(
        string='Hostname',
        readonly=True,
        copy=False,
        index=True,
    )

    os_name = fields.Char(
        string='Sistema operativo',
        readonly=True,
        copy=False,
    )

    os_version = fields.Char(
        string='Versión sistema',
        readonly=True,
        copy=False,
    )

    architecture = fields.Char(
        string='Arquitectura',
        readonly=True,
        copy=False,
        help='Ejemplo: x86_64, aarch64.',
    )

    agent_version = fields.Char(
        string='Versión agente',
        readonly=True,
        copy=False,
        index=True,
    )

    python_version = fields.Char(
        string='Versión Python',
        readonly=True,
        copy=False,
    )

    # ========================================================
    # RED DEL AGENTE
    # ========================================================

    local_ip = fields.Char(
        string='IP local',
        readonly=True,
        copy=False,
        index=True,
    )

    public_ip = fields.Char(
        string='IP pública',
        readonly=True,
        copy=False,
    )

    mac_address = fields.Char(
        string='MAC agente',
        readonly=True,
        copy=False,
    )

    # ========================================================
    # ESTADO
    # ========================================================

    online = fields.Boolean(
        string='En línea',
        default=False,
        readonly=True,
        index=True,
        tracking=True,
    )

    state = fields.Selection(
        [
            ('new', 'Nuevo'),
            ('online', 'En línea'),
            ('warning', 'Advertencia'),
            ('offline', 'Sin conexión'),
            ('disabled', 'Deshabilitado'),
            ('error', 'Error'),
        ],
        string='Estado',
        default='new',
        readonly=True,
        tracking=True,
        index=True,
    )

    first_seen = fields.Datetime(
        string='Primera conexión',
        readonly=True,
        copy=False,
        index=True,
    )

    last_seen = fields.Datetime(
        string='Última conexión',
        readonly=True,
        copy=False,
        index=True,
    )

    last_heartbeat = fields.Datetime(
        string='Último heartbeat',
        readonly=True,
        copy=False,
        index=True,
    )

    last_config_request = fields.Datetime(
        string='Última solicitud configuración',
        readonly=True,
        copy=False,
    )

    # ========================================================
    # HEARTBEAT / DISPONIBILIDAD
    # ========================================================

    heartbeat_interval = fields.Integer(
        string='Heartbeat (seg)',
        default=300,
        required=True,
        help=(
            'Frecuencia recomendada para que el agente reporte '
            'que continúa activo.'
        ),
    )

    offline_after_seconds = fields.Integer(
        string='Considerar offline después de (seg)',
        default=900,
        required=True,
        help=(
            'Tiempo sin heartbeat después del cual puede '
            'considerarse al agente fuera de línea.'
        ),
    )

    # ========================================================
    # POLÍTICA GENERAL
    # ========================================================

    discovery_enabled = fields.Boolean(
        string='Discovery habilitado',
        default=True,
        tracking=True,
    )

    polling_enabled = fields.Boolean(
        string='Polling habilitado',
        default=True,
        tracking=True,
    )

    discovery_interval = fields.Integer(
        string='Discovery cada (seg)',
        default=21600,
        help='Ejemplo: 21600 = cada 6 horas.',
    )

    default_poll_interval = fields.Integer(
        string='Polling por defecto (seg)',
        default=300,
        help='Intervalo general cuando la métrica no indica otro.',
    )

    max_parallel_hosts = fields.Integer(
        string='Hosts simultáneos',
        default=10,
        help=(
            'Cantidad máxima sugerida de dispositivos procesados '
            'simultáneamente.'
        ),
    )

    max_parallel_snmp = fields.Integer(
        string='Consultas SNMP simultáneas',
        default=20,
        help=(
            'Límite sugerido de operaciones SNMP concurrentes.'
        ),
    )

    # ========================================================
    # CAPACIDADES DEL AGENTE
    # ========================================================

    supports_snmp_v1 = fields.Boolean(
        string='Soporta SNMP v1',
        default=True,
        readonly=True,
    )

    supports_snmp_v2c = fields.Boolean(
        string='Soporta SNMP v2c',
        default=True,
        readonly=True,
    )

    supports_snmp_v3 = fields.Boolean(
        string='Soporta SNMP v3',
        default=False,
        readonly=True,
    )

    supports_walk = fields.Boolean(
        string='Soporta WALK',
        default=True,
        readonly=True,
    )

    supports_bulk = fields.Boolean(
        string='Soporta GETBULK',
        default=True,
        readonly=True,
    )

    supports_icmp = fields.Boolean(
        string='Soporta ICMP',
        default=True,
        readonly=True,
    )

    # ========================================================
    # REDES ASIGNADAS
    # ========================================================

    network_ids = fields.One2many(
        'sat.monitoring.network',
        'agent_id',
        string='Redes',
        copy=False,
    )

    network_count = fields.Integer(
        string='Redes',
        compute='_compute_network_count',
    )

    # ========================================================
    # EQUIPOS
    # ========================================================

    device_ids = fields.One2many(
        'sat.monitoring.device',
        'agent_id',
        string='Equipos',
        copy=False,
    )

    device_count = fields.Integer(
        string='Equipos',
        compute='_compute_device_stats',
    )

    online_device_count = fields.Integer(
        string='Equipos en línea',
        compute='_compute_device_stats',
    )

    offline_device_count = fields.Integer(
        string='Equipos sin conexión',
        compute='_compute_device_stats',
    )

    # ========================================================
    # ESTADÍSTICAS
    # ========================================================

    heartbeat_count = fields.Integer(
        string='Heartbeats',
        default=0,
        readonly=True,
        copy=False,
    )

    config_request_count = fields.Integer(
        string='Solicitudes configuración',
        default=0,
        readonly=True,
        copy=False,
    )

    discovery_count = fields.Integer(
        string='Discoveries',
        default=0,
        readonly=True,
        copy=False,
    )

    poll_count = fields.Integer(
        string='Pollings',
        default=0,
        readonly=True,
        copy=False,
    )

    successful_poll_count = fields.Integer(
        string='Pollings exitosos',
        default=0,
        readonly=True,
        copy=False,
    )

    failed_poll_count = fields.Integer(
        string='Pollings fallidos',
        default=0,
        readonly=True,
        copy=False,
    )

    # ========================================================
    # ÚLTIMO ERROR
    # ========================================================

    last_error_date = fields.Datetime(
        string='Último error',
        readonly=True,
        copy=False,
    )

    last_error_code = fields.Char(
        string='Código último error',
        readonly=True,
        copy=False,
        index=True,
    )

    last_error_message = fields.Text(
        string='Último error',
        readonly=True,
        copy=False,
    )

    consecutive_errors = fields.Integer(
        string='Errores consecutivos',
        default=0,
        readonly=True,
        copy=False,
    )

    # ========================================================
    # CONFIGURACIÓN / SINCRONIZACIÓN
    # ========================================================

    config_revision = fields.Integer(
        string='Revisión configuración',
        default=1,
        required=True,
        readonly=True,
        copy=False,
        help=(
            'Incrementa cuando cambia configuración que el agente '
            'debe volver a descargar.'
        ),
    )

    last_config_sync_revision = fields.Integer(
        string='Última revisión sincronizada',
        default=0,
        readonly=True,
        copy=False,
    )

    last_config_sync_at = fields.Datetime(
        string='Última sincronización',
        readonly=True,
        copy=False,
    )

    needs_config_sync = fields.Boolean(
        string='Requiere sincronización',
        compute='_compute_needs_config_sync',
        store=True,
        index=True,
    )

    # ========================================================
    # NOTAS
    # ========================================================

    notes = fields.Text(
        string='Notas',
        tracking=True,
    )

    # ========================================================
    # SQL
    # ========================================================

    _sql_constraints = [
        (
            'sat_monitoring_agent_code_unique',
            'unique(code)',
            'El código técnico del agente ya está siendo utilizado.',
        ),
        (
            'sat_monitoring_agent_heartbeat_positive',
            'CHECK(heartbeat_interval > 0)',
            'El intervalo heartbeat debe ser mayor que cero.',
        ),
        (
            'sat_monitoring_agent_offline_positive',
            'CHECK(offline_after_seconds > 0)',
            'El tiempo para considerar offline debe ser mayor que cero.',
        ),
        (
            'sat_monitoring_agent_discovery_positive',
            'CHECK(discovery_interval >= 0)',
            'El intervalo discovery no puede ser negativo.',
        ),
        (
            'sat_monitoring_agent_poll_positive',
            'CHECK(default_poll_interval > 0)',
            'El intervalo de polling debe ser mayor que cero.',
        ),
        (
            'sat_monitoring_agent_parallel_hosts_positive',
            'CHECK(max_parallel_hosts > 0)',
            'La cantidad de hosts simultáneos debe ser mayor que cero.',
        ),
        (
            'sat_monitoring_agent_parallel_snmp_positive',
            'CHECK(max_parallel_snmp > 0)',
            'La cantidad de consultas SNMP simultáneas debe ser mayor que cero.',
        ),
        (
            'sat_monitoring_agent_config_revision_positive',
            'CHECK(config_revision > 0)',
            'La revisión de configuración debe ser mayor que cero.',
        ),
    ]

    # ========================================================
    # COMPUTES
    # ========================================================

    def _compute_network_count(self):
        Network = self.env[
            'sat.monitoring.network'
        ]

        grouped = Network.read_group(
            [
                (
                    'agent_id',
                    'in',
                    self.ids,
                ),
            ],
            ['agent_id'],
            ['agent_id'],
        )

        counts = {
            item['agent_id'][0]:
                item['agent_id_count']
            for item in grouped
            if item.get('agent_id')
        }

        for record in self:
            record.network_count = counts.get(
                record.id,
                0,
            )

    def _compute_device_stats(self):
        Device = self.env[
            'sat.monitoring.device'
        ]

        for record in self:
            devices = Device.search(
                [
                    (
                        'agent_id',
                        '=',
                        record.id,
                    ),
                ]
            )

            record.device_count = len(
                devices
            )

            record.online_device_count = len(
                devices.filtered(
                    lambda device:
                        device.online
                )
            )

            record.offline_device_count = (
                record.device_count
                - record.online_device_count
            )

    @api.depends(
        'config_revision',
        'last_config_sync_revision',
    )
    def _compute_needs_config_sync(self):
        for record in self:
            record.needs_config_sync = (
                record.last_config_sync_revision
                < record.config_revision
            )

    # ========================================================
    # VALIDACIONES
    # ========================================================

    @api.constrains('code')
    def _check_code(self):
        for record in self:
            code = _clean_text(
                record.code
            )

            if not code:
                raise ValidationError(
                    _('El agente debe tener un código técnico.')
                )

            valid = all(
                (
                    character.islower()
                    or character.isdigit()
                    or character == '_'
                )
                for character in code
            )

            if not valid:
                raise ValidationError(
                    _(
                        'El código técnico debe usar únicamente '
                        'letras minúsculas, números y guion bajo.'
                    )
                )

    @api.constrains(
        'heartbeat_interval',
        'offline_after_seconds',
    )
    def _check_heartbeat_values(self):
        for record in self:
            if (
                record.offline_after_seconds
                < record.heartbeat_interval
            ):
                raise ValidationError(
                    _(
                        'El tiempo para considerar offline debe ser '
                        'igual o mayor que el intervalo heartbeat.'
                    )
                )

    # ========================================================
    # CREATE
    # ========================================================

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(
            vals_list
        )

        # Los agentes nacen sin token.
        # Se genera explícitamente para no exponer uno
        # automáticamente sin que el administrador lo vea.
        return records

    # ========================================================
    # TOKEN
    # ========================================================

    def action_generate_token(self):
        """
        Genera un token nuevo.

        IMPORTANTE:
        El valor completo NO se guarda.

        Se devuelve en una notificación una sola vez.
        """
        self.ensure_one()

        token = secrets.token_urlsafe(
            48
        )

        token_hash = _hash_token(
            token
        )

        preview = '%s...%s' % (
            token[:8],
            token[-6:],
        )

        self.write({
            'token_hash':
                token_hash,

            'token_preview':
                preview,

            'token_generated_at':
                fields.Datetime.now(),

            'token_generated_by':
                self.env.user.id,

            'token_last_used_at':
                False,
        })

        _logger.info(
            '[MONITORING AGENT] Token regenerated | agent=%s code=%s user=%s',
            self.id,
            self.code,
            self.env.user.id,
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title':
                    _('Token del agente'),

                'message':
                    _(
                        'Copie este token ahora. '
                        'No volverá a mostrarse completo:\n\n%s'
                    ) % token,

                'type':
                    'warning',

                'sticky':
                    True,
            },
        }

    def action_revoke_token(self):
        self.write({
            'token_hash':
                False,

            'token_preview':
                False,

            'token_generated_at':
                False,

            'token_generated_by':
                False,

            'token_last_used_at':
                False,
        })

        return True

    @api.model
    def authenticate_agent(
        self,
        code,
        token,
    ):
        """
        Valida credenciales del agente.

        Retorna recordset vacío si falla.
        """
        code = _clean_text(
            code
        )

        token = _clean_text(
            token
        )

        if not code or not token:
            return self.browse()

        agent = self.sudo().search(
            [
                (
                    'code',
                    '=',
                    code,
                ),
                (
                    'active',
                    '=',
                    True,
                ),
                (
                    'enabled',
                    '=',
                    True,
                ),
            ],
            limit=1,
        )

        if not agent:
            _logger.warning(
                '[MONITORING AGENT AUTH] Agent not found/disabled | code=%s',
                code,
            )

            return self.browse()

        received_hash = _hash_token(
            token
        )

        if not agent.token_hash:
            _logger.warning(
                '[MONITORING AGENT AUTH] Agent without token | agent=%s code=%s',
                agent.id,
                code,
            )

            return self.browse()

        if not secrets.compare_digest(
            agent.token_hash,
            received_hash,
        ):
            _logger.warning(
                '[MONITORING AGENT AUTH] Invalid token | agent=%s code=%s',
                agent.id,
                code,
            )

            return self.browse()

        agent.sudo().write({
            'token_last_used_at':
                fields.Datetime.now(),
        })

        return agent

    # ========================================================
    # HEARTBEAT
    # ========================================================

    def register_heartbeat(
        self,
        payload=None,
    ):
        """
        Payload esperado conceptualmente:

        {
            "hostname": "...",
            "os_name": "...",
            "os_version": "...",
            "architecture": "aarch64",
            "agent_version": "1.0.0",
            "python_version": "3.14",
            "local_ip": "...",
            "public_ip": "...",
            "mac_address": "...",

            "capabilities": {
                "snmp_v1": true,
                "snmp_v2c": true,
                "snmp_v3": false,
                "walk": true,
                "bulk": true,
                "icmp": true
            }
        }
        """
        self.ensure_one()

        payload = payload or {}

        capabilities = (
            payload.get('capabilities')
            if isinstance(
                payload.get('capabilities'),
                dict,
            )
            else {}
        )

        now = fields.Datetime.now()

        vals = {
            'online':
                True,

            'state':
                'online',

            'last_seen':
                now,

            'last_heartbeat':
                now,

            'heartbeat_count':
                self.heartbeat_count + 1,

            'consecutive_errors':
                0,
        }

        if not self.first_seen:
            vals[
                'first_seen'
            ] = now

        field_map = {
            'hostname':
                'hostname',

            'os_name':
                'os_name',

            'os_version':
                'os_version',

            'architecture':
                'architecture',

            'agent_version':
                'agent_version',

            'python_version':
                'python_version',

            'local_ip':
                'local_ip',

            'public_ip':
                'public_ip',

            'mac_address':
                'mac_address',
        }

        for payload_key, field_name in field_map.items():
            if payload_key not in payload:
                continue

            value = _clean_text(
                payload.get(
                    payload_key
                )
            )

            if value:
                vals[field_name] = value

        capability_map = {
            'snmp_v1':
                'supports_snmp_v1',

            'snmp_v2c':
                'supports_snmp_v2c',

            'snmp_v3':
                'supports_snmp_v3',

            'walk':
                'supports_walk',

            'bulk':
                'supports_bulk',

            'icmp':
                'supports_icmp',
        }

        for payload_key, field_name in capability_map.items():
            if payload_key in capabilities:
                vals[field_name] = bool(
                    capabilities.get(
                        payload_key
                    )
                )

        self.sudo().write(
            vals
        )

        return self.get_heartbeat_response()

    def get_heartbeat_response(self):
        self.ensure_one()

        return {
            'agent_id':
                self.id,

            'agent_code':
                self.code,

            'enabled':
                self.enabled,

            'server_time':
                fields.Datetime.to_string(
                    fields.Datetime.now()
                ),

            'heartbeat_interval':
                self.heartbeat_interval,

            'config_revision':
                self.config_revision,

            'needs_config_sync':
                self.needs_config_sync,
        }

    # ========================================================
    # REGISTRAR ERROR
    # ========================================================

    def register_error(
        self,
        error_code=None,
        error_message=None,
    ):
        now = fields.Datetime.now()

        for record in self:
            errors = (
                record.consecutive_errors
                + 1
            )

            values = {
                'last_error_date':
                    now,

                'last_error_code':
                    _clean_text(
                        error_code
                    ),

                'last_error_message':
                    _clean_text(
                        error_message
                    ),

                'consecutive_errors':
                    errors,

                'state':
                    (
                        'error'
                        if errors >= 3
                        else 'warning'
                    ),
            }

            record.sudo().write(
                values
            )

        return True

    # ========================================================
    # MARCAR OFFLINE
    # ========================================================

    def mark_offline(self):
        self.write({
            'online':
                False,

            'state':
                'offline',
        })

        return True

    # ========================================================
    # HABILITAR / DESHABILITAR
    # ========================================================

    def action_disable(self):
        self.write({
            'enabled':
                False,

            'online':
                False,

            'state':
                'disabled',
        })

        return True

    def action_enable(self):
        self.write({
            'enabled':
                True,

            'state':
                'new',
        })

        return True

    # ========================================================
    # REVISIÓN CONFIGURACIÓN
    # ========================================================

    def bump_config_revision(self):
        for record in self:
            record.sudo().write({
                'config_revision':
                    record.config_revision + 1,
            })

        return True

    def mark_config_synced(
        self,
        revision=None,
    ):
        self.ensure_one()

        revision = (
            revision
            if revision is not None
            else self.config_revision
        )

        try:
            revision = int(
                revision
            )
        except Exception:
            revision = self.config_revision

        self.sudo().write({
            'last_config_sync_revision':
                revision,

            'last_config_sync_at':
                fields.Datetime.now(),

            'last_config_request':
                fields.Datetime.now(),

            'config_request_count':
                self.config_request_count
                + 1,
        })

        return True

    # ========================================================
    # DISCOVERY STATS
    # ========================================================

    def register_discovery_run(
        self,
    ):
        for record in self:
            record.sudo().write({
                'discovery_count':
                    record.discovery_count
                    + 1,

                'last_seen':
                    fields.Datetime.now(),
            })

        return True

    # ========================================================
    # POLLING STATS
    # ========================================================

    def register_poll_result(
        self,
        success=True,
    ):
        for record in self:
            vals = {
                'poll_count':
                    record.poll_count
                    + 1,

                'last_seen':
                    fields.Datetime.now(),
            }

            if success:
                vals[
                    'successful_poll_count'
                ] = (
                    record.successful_poll_count
                    + 1
                )
            else:
                vals[
                    'failed_poll_count'
                ] = (
                    record.failed_poll_count
                    + 1
                )

            record.sudo().write(
                vals
            )

        return True

    # ========================================================
    # CONFIGURACIÓN PARA EL AGENTE
    # ========================================================

    def get_agent_configuration(self):
        """
        Devuelve la configuración general del agente.

        Las credenciales SNMP se incorporarán después desde
        sat.snmp.credential mediante las redes asignadas.
        """
        self.ensure_one()

        self.sudo().write({
            'last_config_request':
                fields.Datetime.now(),

            'config_request_count':
                self.config_request_count
                + 1,
        })

        networks = self.network_ids.filtered(
            lambda network:
                network.active
        ).sorted(
            key=lambda network: (
                network.sequence,
                network.id,
            )
        )

        return {
            'agent': {
                'id':
                    self.id,

                'code':
                    self.code,

                'name':
                    self.name,

                'enabled':
                    self.enabled,

                'config_revision':
                    self.config_revision,

                'discovery_enabled':
                    self.discovery_enabled,

                'polling_enabled':
                    self.polling_enabled,

                'heartbeat_interval':
                    self.heartbeat_interval,

                'discovery_interval':
                    self.discovery_interval,

                'default_poll_interval':
                    self.default_poll_interval,

                'max_parallel_hosts':
                    self.max_parallel_hosts,

                'max_parallel_snmp':
                    self.max_parallel_snmp,
            },

            'networks': [
                network.get_agent_payload()
                for network in networks
            ],
        }