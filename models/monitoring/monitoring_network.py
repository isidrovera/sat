# -*- coding: utf-8 -*-

import ipaddress
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================

def _clean_text(value):
    if value in (None, False):
        return ''
    return str(value).strip()


def _parse_lines(value):
    result = []

    for line in (_clean_text(value)).splitlines():
        line = line.strip()

        if not line:
            continue

        if line.startswith('#'):
            continue

        result.append(line)

    return result


def _normalize_cidr(value):
    value = _clean_text(value)

    if not value:
        return ''

    try:
        network = ipaddress.ip_network(
            value,
            strict=False,
        )

        return str(network)

    except Exception:
        return value


def _is_valid_cidr(value):
    if not value:
        return False

    try:
        ipaddress.ip_network(
            value,
            strict=False,
        )
        return True

    except Exception:
        return False


def _is_valid_ip(value):
    if not value:
        return False

    try:
        ipaddress.ip_address(value)
        return True

    except Exception:
        return False


# ============================================================
# RED DE MONITOREO
# ============================================================

class SatMonitoringNetwork(models.Model):
    """
    Red que debe monitorear un agente.

    Ejemplos:

        192.168.10.0/24
        192.168.20.0/24
        10.10.0.0/16

    Un agente puede tener varias redes.

    Una red pertenece normalmente a:
        - cliente
        - sede
        - agente
        - credencial SNMP por defecto
    """

    _name = 'sat.monitoring.network'
    _description = 'Red de monitoreo SNMP'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'agent_id, sequence, name, id'

    # ========================================================
    # IDENTIFICACIÓN
    # ========================================================

    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True,
        index=True,
        help=(
            'Nombre administrativo de la red.\n'
            'Ejemplo: Red principal - Administración.'
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
            'Ejemplo: consorcio_sf_lima_admin.'
        ),
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
        tracking=True,
        index=True,
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )

    # ========================================================
    # RELACIONES
    # ========================================================

    agent_id = fields.Many2one(
        'sat.monitoring.agent',
        string='Agente',
        required=True,
        ondelete='cascade',
        tracking=True,
        index=True,
    )

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

    # ========================================================
    # RED
    # ========================================================

    cidr = fields.Char(
        string='Red CIDR',
        required=True,
        tracking=True,
        index=True,
        help=(
            'Ejemplo:\n'
            '192.168.10.0/24\n'
            '10.0.0.0/16'
        ),
    )

    network_address = fields.Char(
        string='Dirección de red',
        compute='_compute_network_info',
        store=True,
        readonly=True,
        index=True,
    )

    prefix_length = fields.Integer(
        string='Prefijo',
        compute='_compute_network_info',
        store=True,
        readonly=True,
    )

    netmask = fields.Char(
        string='Máscara',
        compute='_compute_network_info',
        store=True,
        readonly=True,
    )

    broadcast_address = fields.Char(
        string='Broadcast',
        compute='_compute_network_info',
        store=True,
        readonly=True,
    )

    ip_version = fields.Selection(
        [
            ('4', 'IPv4'),
            ('6', 'IPv6'),
        ],
        string='Versión IP',
        compute='_compute_network_info',
        store=True,
        readonly=True,
        index=True,
    )

    total_addresses = fields.Integer(
        string='Direcciones totales',
        compute='_compute_network_info',
        store=True,
        readonly=True,
    )

    usable_host_count = fields.Integer(
        string='Hosts estimados',
        compute='_compute_network_info',
        store=True,
        readonly=True,
    )

    gateway = fields.Char(
        string='Gateway',
        tracking=True,
    )

    vlan_id = fields.Integer(
        string='VLAN',
        help='ID VLAN cuando aplique.',
    )

    dns_name = fields.Char(
        string='Nombre de red / dominio',
    )

    # ========================================================
    # EXCLUSIONES
    # ========================================================

    excluded_ips = fields.Text(
        string='IPs excluidas',
        help=(
            'Una IP por línea.\n\n'
            'Ejemplo:\n'
            '192.168.10.1\n'
            '192.168.10.254'
        ),
    )

    excluded_ranges = fields.Text(
        string='Rangos excluidos',
        help=(
            'Un rango o CIDR por línea.\n\n'
            'Ejemplo:\n'
            '192.168.10.1-192.168.10.20\n'
            '192.168.10.128/26'
        ),
    )

    included_ips = fields.Text(
        string='IPs adicionales',
        help=(
            'IPs que deben consultarse incluso si están fuera '
            'del rango CIDR principal.'
        ),
    )

    # ========================================================
    # DISCOVERY
    # ========================================================

    discovery_enabled = fields.Boolean(
        string='Discovery habilitado',
        default=True,
        tracking=True,
        index=True,
    )

    discovery_method = fields.Selection(
        [
            ('snmp', 'SNMP directo'),
            ('icmp_snmp', 'ICMP + SNMP'),
            ('tcp_snmp', 'TCP + SNMP'),
            ('hybrid', 'Híbrido'),
        ],
        string='Método discovery',
        default='hybrid',
        required=True,
        tracking=True,
    )

    discovery_interval = fields.Integer(
        string='Discovery cada (seg)',
        default=21600,
        help='Ejemplo: 21600 = 6 horas.',
    )

    discovery_timeout = fields.Float(
        string='Timeout discovery',
        default=1.5,
    )

    discovery_retries = fields.Integer(
        string='Reintentos discovery',
        default=1,
    )

    discovery_snmp_first = fields.Boolean(
        string='Intentar SNMP primero',
        default=True,
        help=(
            'Permite detectar impresoras que bloquean ICMP '
            'pero responden por SNMP.'
        ),
    )

    # ========================================================
    # POLLING
    # ========================================================

    polling_enabled = fields.Boolean(
        string='Polling habilitado',
        default=True,
        tracking=True,
        index=True,
    )

    poll_interval = fields.Integer(
        string='Polling cada (seg)',
        default=300,
    )

    poll_timeout = fields.Float(
        string='Timeout polling',
        default=2.0,
    )

    poll_retries = fields.Integer(
        string='Reintentos polling',
        default=1,
    )

    # ========================================================
    # CREDENCIAL SNMP
    # ========================================================

    credential_id = fields.Many2one(
        'sat.snmp.credential',
        string='Credencial SNMP por defecto',
        ondelete='restrict',
        tracking=True,
        index=True,
    )

    allow_credential_fallback = fields.Boolean(
        string='Permitir otras credenciales',
        default=True,
        help=(
            'Si la credencial principal falla, permite probar '
            'credenciales autorizadas de respaldo.'
        ),
    )

    # ========================================================
    # FILTRO DE DISPOSITIVOS
    # ========================================================

    printers_only = fields.Boolean(
        string='Solo impresoras/MFP',
        default=True,
        help=(
            'Evita registrar automáticamente otros dispositivos '
            'SNMP encontrados en la red.'
        ),
    )

    auto_create_devices = fields.Boolean(
        string='Crear equipos automáticamente',
        default=True,
        tracking=True,
    )

    auto_assign_profile = fields.Boolean(
        string='Asignar perfil automáticamente',
        default=True,
        tracking=True,
    )

    monitor_unknown_devices = fields.Boolean(
        string='Monitorear equipos desconocidos',
        default=False,
        help=(
            'Si no existe perfil compatible, permite mantener '
            'el equipo registrado para discovery/aprendizaje.'
        ),
    )

    # ========================================================
    # LÍMITES
    # ========================================================

    max_hosts_per_cycle = fields.Integer(
        string='Máximo hosts por ciclo',
        default=1024,
        help=(
            'Protección para evitar explorar accidentalmente '
            'redes demasiado grandes en un solo ciclo.'
        ),
    )

    max_parallel_hosts = fields.Integer(
        string='Hosts simultáneos',
        default=10,
    )

    # ========================================================
    # ESTADO
    # ========================================================

    last_discovery_at = fields.Datetime(
        string='Último discovery',
        readonly=True,
        copy=False,
        index=True,
    )

    last_discovery_success = fields.Boolean(
        string='Último discovery correcto',
        readonly=True,
        copy=False,
    )

    last_discovery_duration_ms = fields.Float(
        string='Duración discovery (ms)',
        readonly=True,
        copy=False,
    )

    last_discovered_host_count = fields.Integer(
        string='Hosts encontrados',
        default=0,
        readonly=True,
        copy=False,
    )

    last_printer_count = fields.Integer(
        string='Impresoras encontradas',
        default=0,
        readonly=True,
        copy=False,
    )

    last_error_date = fields.Datetime(
        string='Último error',
        readonly=True,
        copy=False,
    )

    last_error_message = fields.Text(
        string='Último error',
        readonly=True,
        copy=False,
    )

    # ========================================================
    # EQUIPOS
    # ========================================================

    device_ids = fields.One2many(
        'sat.monitoring.device',
        'network_id',
        string='Equipos',
        copy=False,
    )

    device_count = fields.Integer(
        string='Equipos',
        compute='_compute_device_stats',
    )

    online_device_count = fields.Integer(
        string='En línea',
        compute='_compute_device_stats',
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
            'sat_monitoring_network_code_unique',
            'unique(code)',
            'El código técnico de la red ya está siendo utilizado.',
        ),
        (
            'sat_monitoring_network_agent_cidr_unique',
            'unique(agent_id, cidr)',
            'El agente ya tiene configurada esta red.',
        ),
        (
            'sat_monitoring_network_discovery_interval_positive',
            'CHECK(discovery_interval >= 0)',
            'El intervalo de discovery no puede ser negativo.',
        ),
        (
            'sat_monitoring_network_poll_interval_positive',
            'CHECK(poll_interval > 0)',
            'El intervalo de polling debe ser mayor que cero.',
        ),
        (
            'sat_monitoring_network_max_hosts_positive',
            'CHECK(max_hosts_per_cycle > 0)',
            'El máximo de hosts debe ser mayor que cero.',
        ),
        (
            'sat_monitoring_network_parallel_positive',
            'CHECK(max_parallel_hosts > 0)',
            'Los hosts simultáneos deben ser mayores que cero.',
        ),
    ]

    # ========================================================
    # COMPUTES
    # ========================================================

    @api.depends('cidr')
    def _compute_network_info(self):
        for record in self:
            record.network_address = False
            record.prefix_length = 0
            record.netmask = False
            record.broadcast_address = False
            record.ip_version = False
            record.total_addresses = 0
            record.usable_host_count = 0

            if not record.cidr:
                continue

            try:
                network = ipaddress.ip_network(
                    record.cidr,
                    strict=False,
                )
            except Exception:
                continue

            record.network_address = str(
                network.network_address
            )

            record.prefix_length = (
                network.prefixlen
            )

            record.netmask = str(
                network.netmask
            )

            record.ip_version = str(
                network.version
            )

            total = int(
                network.num_addresses
            )

            record.total_addresses = min(
                total,
                2147483647,
            )

            if network.version == 4:
                if network.prefixlen <= 30:
                    usable = max(
                        total - 2,
                        0,
                    )
                else:
                    usable = total

                record.broadcast_address = str(
                    network.broadcast_address
                )

            else:
                usable = total
                record.broadcast_address = False

            record.usable_host_count = min(
                usable,
                2147483647,
            )

    def _compute_device_stats(self):
        Device = self.env[
            'sat.monitoring.device'
        ]

        for record in self:
            devices = Device.search(
                [
                    (
                        'network_id',
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

    # ========================================================
    # CREATE / WRITE
    # ========================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('cidr'):
                vals['cidr'] = _normalize_cidr(
                    vals['cidr']
                )

        records = super().create(
            vals_list
        )

        for record in records:
            record.agent_id.bump_config_revision()

        return records

    def write(self, vals):
        if vals.get('cidr'):
            vals['cidr'] = _normalize_cidr(
                vals['cidr']
            )

        config_fields = {
            'active',
            'cidr',
            'gateway',
            'excluded_ips',
            'excluded_ranges',
            'included_ips',
            'discovery_enabled',
            'discovery_method',
            'discovery_interval',
            'discovery_timeout',
            'discovery_retries',
            'discovery_snmp_first',
            'polling_enabled',
            'poll_interval',
            'poll_timeout',
            'poll_retries',
            'credential_id',
            'allow_credential_fallback',
            'printers_only',
            'auto_create_devices',
            'auto_assign_profile',
            'monitor_unknown_devices',
            'max_hosts_per_cycle',
            'max_parallel_hosts',
        }

        must_bump = bool(
            config_fields.intersection(
                vals.keys()
            )
        )

        agents_before = self.mapped(
            'agent_id'
        )

        result = super().write(vals)

        if must_bump:
            agents = (
                agents_before
                | self.mapped('agent_id')
            )

            agents.bump_config_revision()

        return result

    def unlink(self):
        agents = self.mapped(
            'agent_id'
        )

        result = super().unlink()

        agents.bump_config_revision()

        return result

    # ========================================================
    # VALIDACIONES
    # ========================================================

    @api.constrains('cidr')
    def _check_cidr(self):
        for record in self:
            if not _is_valid_cidr(
                record.cidr
            ):
                raise ValidationError(
                    _(
                        'La red CIDR "%s" no es válida.'
                    ) % record.cidr
                )

    @api.constrains('gateway', 'cidr')
    def _check_gateway(self):
        for record in self:
            if not record.gateway:
                continue

            if not _is_valid_ip(
                record.gateway
            ):
                raise ValidationError(
                    _(
                        'El gateway "%s" no es una IP válida.'
                    ) % record.gateway
                )

    @api.constrains('excluded_ips')
    def _check_excluded_ips(self):
        for record in self:
            for value in _parse_lines(
                record.excluded_ips
            ):
                if not _is_valid_ip(
                    value
                ):
                    raise ValidationError(
                        _(
                            'IP excluida inválida: %s'
                        ) % value
                    )

    @api.constrains('included_ips')
    def _check_included_ips(self):
        for record in self:
            for value in _parse_lines(
                record.included_ips
            ):
                if not _is_valid_ip(
                    value
                ):
                    raise ValidationError(
                        _(
                            'IP adicional inválida: %s'
                        ) % value
                    )

    @api.constrains('excluded_ranges')
    def _check_excluded_ranges(self):
        for record in self:
            for value in _parse_lines(
                record.excluded_ranges
            ):
                if '/' in value:
                    if not _is_valid_cidr(
                        value
                    ):
                        raise ValidationError(
                            _(
                                'CIDR excluido inválido: %s'
                            ) % value
                        )

                    continue

                if '-' not in value:
                    raise ValidationError(
                        _(
                            'Rango excluido inválido: %s'
                        ) % value
                    )

                start, end = [
                    item.strip()
                    for item in value.split(
                        '-',
                        1,
                    )
                ]

                if not (
                    _is_valid_ip(start)
                    and _is_valid_ip(end)
                ):
                    raise ValidationError(
                        _(
                            'Rango de IP inválido: %s'
                        ) % value
                    )

                try:
                    start_ip = ipaddress.ip_address(
                        start
                    )

                    end_ip = ipaddress.ip_address(
                        end
                    )

                    if (
                        start_ip.version
                        != end_ip.version
                    ):
                        raise ValidationError(
                            _(
                                'Las IP del rango deben usar '
                                'la misma versión: %s'
                            ) % value
                        )

                    if int(start_ip) > int(end_ip):
                        raise ValidationError(
                            _(
                                'El inicio del rango no puede '
                                'ser mayor que el final: %s'
                            ) % value
                        )

                except ValidationError:
                    raise

                except Exception:
                    raise ValidationError(
                        _(
                            'Rango de IP inválido: %s'
                        ) % value
                    )

    @api.constrains(
        'discovery_timeout',
        'poll_timeout',
        'discovery_retries',
        'poll_retries',
    )
    def _check_timeouts(self):
        for record in self:
            if record.discovery_timeout < 0:
                raise ValidationError(
                    _(
                        'El timeout de discovery '
                        'no puede ser negativo.'
                    )
                )

            if record.poll_timeout < 0:
                raise ValidationError(
                    _(
                        'El timeout de polling '
                        'no puede ser negativo.'
                    )
                )

            if record.discovery_retries < 0:
                raise ValidationError(
                    _(
                        'Los reintentos de discovery '
                        'no pueden ser negativos.'
                    )
                )

            if record.poll_retries < 0:
                raise ValidationError(
                    _(
                        'Los reintentos de polling '
                        'no pueden ser negativos.'
                    )
                )

    @api.constrains(
        'credential_id',
        'partner_id',
    )
    def _check_credential_partner(self):
        """
        Evita asignar accidentalmente una credencial privada
        de otro cliente cuando la credencial tiene cliente definido.
        """
        for record in self:
            credential = record.credential_id

            if not credential:
                continue

            if (
                credential.partner_id
                and record.partner_id
                and credential.partner_id
                != record.partner_id
            ):
                raise ValidationError(
                    _(
                        'La credencial SNMP seleccionada pertenece '
                        'a otro cliente.'
                    )
                )

    # ========================================================
    # ESTADÍSTICAS DISCOVERY
    # ========================================================

    def register_discovery_result(
        self,
        success=True,
        duration_ms=None,
        host_count=0,
        printer_count=0,
        error_message=None,
    ):
        now = fields.Datetime.now()

        for record in self:
            vals = {
                'last_discovery_at':
                    now,

                'last_discovery_success':
                    bool(success),

                'last_discovered_host_count':
                    max(
                        int(host_count or 0),
                        0,
                    ),

                'last_printer_count':
                    max(
                        int(printer_count or 0),
                        0,
                    ),
            }

            if duration_ms is not None:
                try:
                    vals[
                        'last_discovery_duration_ms'
                    ] = max(
                        float(duration_ms),
                        0.0,
                    )
                except Exception:
                    pass

            if not success:
                vals.update({
                    'last_error_date':
                        now,

                    'last_error_message':
                        _clean_text(
                            error_message
                        ),
                })

            record.sudo().write(
                vals
            )

            record.agent_id.register_discovery_run()

        return True

    # ========================================================
    # CONFIGURACIÓN PARA AGENTE
    # ========================================================

    def get_agent_payload(self):
        """
        Devuelve la configuración de esta red.

        La credencial se serializará mediante:
            credential.get_agent_payload()
        """
        self.ensure_one()

        excluded_ips = _parse_lines(
            self.excluded_ips
        )

        excluded_ranges = _parse_lines(
            self.excluded_ranges
        )

        included_ips = _parse_lines(
            self.included_ips
        )

        credential_payload = {}

        if self.credential_id:
            credential_payload = (
                self.credential_id.get_agent_payload()
            )

        return {
            'id':
                self.id,

            'code':
                self.code,

            'name':
                self.name,

            'partner_id':
                self.partner_id.id
                if self.partner_id
                else False,

            'branch_name':
                self.branch_name or '',

            'cidr':
                self.cidr,

            'network_address':
                self.network_address or '',

            'prefix_length':
                self.prefix_length,

            'ip_version':
                self.ip_version or '',

            'gateway':
                self.gateway or '',

            'vlan_id':
                self.vlan_id or 0,

            'discovery': {
                'enabled':
                    self.discovery_enabled,

                'method':
                    self.discovery_method,

                'interval':
                    self.discovery_interval,

                'timeout':
                    self.discovery_timeout,

                'retries':
                    self.discovery_retries,

                'snmp_first':
                    self.discovery_snmp_first,

                'printers_only':
                    self.printers_only,

                'auto_create_devices':
                    self.auto_create_devices,

                'auto_assign_profile':
                    self.auto_assign_profile,

                'monitor_unknown_devices':
                    self.monitor_unknown_devices,

                'max_hosts_per_cycle':
                    self.max_hosts_per_cycle,

                'max_parallel_hosts':
                    self.max_parallel_hosts,
            },

            'polling': {
                'enabled':
                    self.polling_enabled,

                'interval':
                    self.poll_interval,

                'timeout':
                    self.poll_timeout,

                'retries':
                    self.poll_retries,
            },

            'scope': {
                'excluded_ips':
                    excluded_ips,

                'excluded_ranges':
                    excluded_ranges,

                'included_ips':
                    included_ips,
            },

            'credential':
                credential_payload,

            'allow_credential_fallback':
                self.allow_credential_fallback,
        }

    # ========================================================
    # COMPROBAR SI IP PERTENECE A LA RED
    # ========================================================

    def contains_ip(
        self,
        ip,
    ):
        self.ensure_one()

        try:
            address = ipaddress.ip_address(
                _clean_text(ip)
            )

            network = ipaddress.ip_network(
                self.cidr,
                strict=False,
            )

            return address in network

        except Exception:
            return False

    # ========================================================
    # COMPROBAR SI IP ESTÁ EXCLUIDA
    # ========================================================

    def is_ip_excluded(
        self,
        ip,
    ):
        self.ensure_one()

        try:
            address = ipaddress.ip_address(
                _clean_text(ip)
            )
        except Exception:
            return True

        # IP exacta
        for item in _parse_lines(
            self.excluded_ips
        ):
            try:
                if address == ipaddress.ip_address(
                    item
                ):
                    return True
            except Exception:
                continue

        # Rangos / CIDR
        for item in _parse_lines(
            self.excluded_ranges
        ):
            try:
                if '/' in item:
                    network = ipaddress.ip_network(
                        item,
                        strict=False,
                    )

                    if address in network:
                        return True

                    continue

                start, end = [
                    value.strip()
                    for value in item.split(
                        '-',
                        1,
                    )
                ]

                start_ip = ipaddress.ip_address(
                    start
                )

                end_ip = ipaddress.ip_address(
                    end
                )

                if (
                    address.version
                    == start_ip.version
                    == end_ip.version
                    and int(start_ip)
                    <= int(address)
                    <= int(end_ip)
                ):
                    return True

            except Exception:
                continue

        return False