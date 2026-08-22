# -*- coding: utf-8 -*-

import json
import logging
import re

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


def _json_dumps_safe(value):
    try:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    except Exception:
        try:
            return str(value or '')
        except Exception:
            return ''


def _normalize_mac(value):
    """
    Normaliza una MAC al formato:

        AA:BB:CC:DD:EE:FF
    """
    value = _clean_text(value)

    if not value:
        return ''

    raw = re.sub(
        r'[^0-9a-fA-F]',
        '',
        value,
    )

    if len(raw) != 12:
        return value.upper()

    return ':'.join(
        raw[index:index + 2]
        for index in range(
            0,
            12,
            2,
        )
    ).upper()


def _valid_mac(value):
    if not value:
        return True

    return bool(
        re.fullmatch(
            r'[0-9A-Fa-f]{2}'
            r'(?::[0-9A-Fa-f]{2}){5}',
            value,
        )
    )


def _valid_ipv4(value):
    if not value:
        return True

    parts = value.split('.')

    if len(parts) != 4:
        return False

    try:
        return all(
            0 <= int(part) <= 255
            for part in parts
        )
    except Exception:
        return False


# ============================================================
# EQUIPO MONITOREADO
# ============================================================

class SatMonitoringDevice(models.Model):
    """
    Representa una impresora/MFP física monitoreada.

    Mantiene el ESTADO ACTUAL del dispositivo.

    El histórico se almacena en:

        sat.monitoring.snapshot
        sat.monitoring.reading
        sat.monitoring.alert

    Relaciones operativas:

        sat.monitoring.agent
                ↓
        sat.monitoring.network
                ↓
        sat.monitoring.device
                ↓
        sat.snmp.profile
                ↓
        sat.snmp.profile.metric
    """

    _name = 'sat.monitoring.device'
    _description = 'Equipo monitoreado SNMP'
    _inherit = [
        'mail.thread',
        'mail.activity.mixin',
    ]
    _order = (
        'monitoring_enabled desc, '
        'online desc, '
        'last_seen desc, '
        'name, '
        'id'
    )
    _rec_name = 'name'

    # ========================================================
    # IDENTIFICACIÓN
    # ========================================================

    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True,
        index=True,
        help=(
            'Nombre identificativo del equipo dentro '
            'del sistema de monitoreo.'
        ),
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
        tracking=True,
        index=True,
    )

    monitoring_enabled = fields.Boolean(
        string='Monitoreo habilitado',
        default=True,
        tracking=True,
        index=True,
    )

    inventory_enabled = fields.Boolean(
        string='Inventario habilitado',
        default=True,
        tracking=True,
        help=(
            'Permite mantener identidad, accesorios, capacidades '
            'y componentes aunque el polling frecuente esté desactivado.'
        ),
    )

    alert_monitoring_enabled = fields.Boolean(
        string='Monitorear alertas',
        default=True,
        tracking=True,
    )

    job_monitoring_enabled = fields.Boolean(
        string='Monitorear trabajos',
        default=False,
        tracking=True,
        help=(
            'Reservado para equipos/perfiles que expongan '
            'información de trabajos mediante SNMP.'
        ),
    )

    # ========================================================
    # RELACIÓN CON MÁQUINA SAT
    # ========================================================

    maquina_id = fields.Many2one(
        'sat.sat',
        string='Máquina SAT',
        ondelete='set null',
        tracking=True,
        index=True,
        help=(
            'Máquina registrada en SAT cuando el equipo '
            'monitoreado ya está relacionado al inventario existente.'
        ),
    )

    # ========================================================
    # CLIENTE
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
        string='Ubicación física',
        tracking=True,
        help=(
            'Ejemplo: Administración - Piso 2 - Contabilidad.'
        ),
    )

    # ========================================================
    # AGENTE / RED
    # ========================================================

    agent_id = fields.Many2one(
        'sat.monitoring.agent',
        string='Agente',
        ondelete='restrict',
        tracking=True,
        index=True,
        help=(
            'Agente responsable de consultar este equipo.'
        ),
    )

    network_id = fields.Many2one(
        'sat.monitoring.network',
        string='Red',
        ondelete='restrict',
        tracking=True,
        index=True,
        help=(
            'Red monitoreada en la que se encuentra el equipo.'
        ),
    )

    network_cidr = fields.Char(
        related='network_id.cidr',
        string='CIDR',
        store=True,
        readonly=True,
    )

    # ========================================================
    # CREDENCIAL
    # ========================================================

    credential_id = fields.Many2one(
        'sat.snmp.credential',
        string='Credencial SNMP',
        ondelete='restrict',
        tracking=True,
        index=True,
        help=(
            'Credencial específica de este equipo.\n'
            'Si queda vacía se utiliza la credencial '
            'configurada en la red.'
        ),
    )

    effective_credential_id = fields.Many2one(
        'sat.snmp.credential',
        string='Credencial efectiva',
        compute='_compute_effective_credential',
        readonly=True,
    )

    # ========================================================
    # MARCA / MODELO
    # ========================================================

    marca_id = fields.Many2one(
        'marca.marca',
        string='Marca',
        ondelete='restrict',
        tracking=True,
        index=True,
    )

    marca_codigo = fields.Char(
        related='marca_id.codigo_tecnico',
        string='Código marca',
        store=True,
        readonly=True,
        index=True,
    )

    manufacturer_raw = fields.Char(
        string='Fabricante SNMP RAW',
        readonly=True,
        copy=False,
        index=True,
    )

    model = fields.Char(
        string='Modelo',
        tracking=True,
        index=True,
    )

    model_raw = fields.Char(
        string='Modelo SNMP RAW',
        readonly=True,
        copy=False,
    )

    serial = fields.Char(
        string='Número de serie',
        tracking=True,
        index=True,
        copy=False,
    )

    firmware = fields.Char(
        string='Firmware',
        tracking=True,
        copy=False,
    )

    sysdescr = fields.Text(
        string='sysDescr',
        readonly=True,
        copy=False,
    )

    enterprise_id = fields.Char(
        string='Enterprise ID',
        tracking=True,
        index=True,
        copy=False,
    )

    technology = fields.Selection(
        [
            ('unknown', 'Desconocido'),
            ('mono', 'Monocromo'),
            ('color', 'Color'),
        ],
        string='Tecnología',
        default='unknown',
        tracking=True,
        index=True,
    )

    # ========================================================
    # IDENTIDAD SECUNDARIA
    # ========================================================

    system_name = fields.Char(
        string='System Name',
        readonly=True,
        copy=False,
    )

    system_location = fields.Char(
        string='System Location',
        readonly=True,
        copy=False,
    )

    system_contact = fields.Char(
        string='System Contact',
        readonly=True,
        copy=False,
    )

    engine_id = fields.Char(
        string='SNMP Engine ID',
        readonly=True,
        copy=False,
        index=True,
    )

    # ========================================================
    # PERFIL SNMP
    # ========================================================

    profile_id = fields.Many2one(
        'sat.snmp.profile',
        string='Perfil SNMP',
        ondelete='restrict',
        tracking=True,
        index=True,
    )

    profile_code = fields.Char(
        related='profile_id.code',
        string='Código perfil',
        store=True,
        readonly=True,
        index=True,
    )

    profile_version = fields.Char(
        related='profile_id.version',
        string='Versión perfil',
        store=True,
        readonly=True,
    )

    profile_revision = fields.Integer(
        related='profile_id.revision',
        string='Revisión perfil',
        store=True,
        readonly=True,
    )

    profile_match_score = fields.Integer(
        string='Puntuación perfil',
        readonly=True,
        copy=False,
    )

    profile_match_date = fields.Datetime(
        string='Fecha asignación perfil',
        readonly=True,
        copy=False,
    )

    profile_match_details = fields.Text(
        string='Detalle selección perfil',
        readonly=True,
        copy=False,
    )

    profile_manual = fields.Boolean(
        string='Perfil asignado manualmente',
        default=False,
        tracking=True,
    )

    # ========================================================
    # RED
    # ========================================================

    ip_address = fields.Char(
        string='Dirección IP',
        tracking=True,
        index=True,
        copy=False,
    )

    snmp_port = fields.Integer(
        string='Puerto SNMP',
        default=161,
        tracking=True,
    )

    hostname = fields.Char(
        string='Hostname',
        tracking=True,
        index=True,
        copy=False,
    )

    mac_address = fields.Char(
        string='Dirección MAC',
        tracking=True,
        index=True,
        copy=False,
    )

    gateway = fields.Char(
        string='Gateway',
        readonly=True,
        copy=False,
    )

    subnet_mask = fields.Char(
        string='Máscara',
        readonly=True,
        copy=False,
    )

    ipv6_address = fields.Char(
        string='IPv6',
        readonly=True,
        copy=False,
        index=True,
    )

    # ========================================================
    # SNMP
    # ========================================================

    snmp_version = fields.Selection(
        [
            ('1', 'SNMP v1'),
            ('2c', 'SNMP v2c'),
            ('3', 'SNMP v3'),
        ],
        string='Versión SNMP',
        default='2c',
        tracking=True,
        index=True,
    )

    snmp_available = fields.Boolean(
        string='SNMP disponible',
        default=False,
        readonly=True,
        index=True,
    )

    last_snmp_version_used = fields.Selection(
        [
            ('1', 'SNMP v1'),
            ('2c', 'SNMP v2c'),
            ('3', 'SNMP v3'),
        ],
        string='Última versión utilizada',
        readonly=True,
    )

    # ========================================================
    # ESTADO DE CONECTIVIDAD
    # ========================================================

    online = fields.Boolean(
        string='En línea',
        default=False,
        readonly=True,
        tracking=True,
        index=True,
    )

    status = fields.Selection(
        [
            ('unknown', 'Desconocido'),
            ('ready', 'Listo'),
            ('busy', 'Ocupado'),
            ('warning', 'Advertencia'),
            ('error', 'Error'),
            ('offline', 'Sin conexión'),
        ],
        string='Estado',
        default='unknown',
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

    last_poll_date = fields.Datetime(
        string='Último polling',
        readonly=True,
        copy=False,
        index=True,
    )

    last_successful_poll = fields.Datetime(
        string='Último polling exitoso',
        readonly=True,
        copy=False,
    )

    last_failed_poll = fields.Datetime(
        string='Último polling fallido',
        readonly=True,
        copy=False,
    )

    consecutive_failures = fields.Integer(
        string='Fallos consecutivos',
        default=0,
        readonly=True,
        copy=False,
    )

    last_response_ms = fields.Float(
        string='Respuesta SNMP (ms)',
        readonly=True,
        copy=False,
    )

    last_poll_error = fields.Text(
        string='Último error polling',
        readonly=True,
        copy=False,
    )

    # ========================================================
    # CONTADORES ACTUALES
    # ========================================================

    counter_machine_total = fields.Integer(
        string='Total máquina',
        readonly=True,
        copy=False,
    )

    counter_total_bw = fields.Integer(
        string='Total B/N',
        readonly=True,
        copy=False,
    )

    counter_total_color = fields.Integer(
        string='Total color',
        readonly=True,
        copy=False,
    )

    counter_copy_total = fields.Integer(
        string='Copias total',
        readonly=True,
        copy=False,
    )

    counter_copy_bw = fields.Integer(
        string='Copias B/N',
        readonly=True,
        copy=False,
    )

    counter_copy_color = fields.Integer(
        string='Copias color',
        readonly=True,
        copy=False,
    )

    counter_print_total = fields.Integer(
        string='Impresiones total',
        readonly=True,
        copy=False,
    )

    counter_print_bw = fields.Integer(
        string='Impresiones B/N',
        readonly=True,
        copy=False,
    )

    counter_print_color = fields.Integer(
        string='Impresiones color',
        readonly=True,
        copy=False,
    )

    counter_scan_total = fields.Integer(
        string='Escaneos total',
        readonly=True,
        copy=False,
    )

    counter_scan_bw = fields.Integer(
        string='Escaneos B/N',
        readonly=True,
        copy=False,
    )

    counter_scan_color = fields.Integer(
        string='Escaneos color',
        readonly=True,
        copy=False,
    )

    counter_fax_total = fields.Integer(
        string='Fax total',
        readonly=True,
        copy=False,
    )

    counter_duplex = fields.Integer(
        string='Dúplex',
        readonly=True,
        copy=False,
    )

    counter_large_paper = fields.Integer(
        string='A3 / Papel grande',
        readonly=True,
        copy=False,
    )

    # ========================================================
    # CONSUMIBLES ACTUALES
    # ========================================================

    toner_black = fields.Float(
        string='Tóner negro (%)',
        readonly=True,
        copy=False,
    )

    toner_cyan = fields.Float(
        string='Tóner cyan (%)',
        readonly=True,
        copy=False,
    )

    toner_magenta = fields.Float(
        string='Tóner magenta (%)',
        readonly=True,
        copy=False,
    )

    toner_yellow = fields.Float(
        string='Tóner amarillo (%)',
        readonly=True,
        copy=False,
    )

    toner_black_available = fields.Boolean(
        string='Tóner K disponible',
        default=False,
        readonly=True,
    )

    toner_cyan_available = fields.Boolean(
        string='Tóner C disponible',
        default=False,
        readonly=True,
    )

    toner_magenta_available = fields.Boolean(
        string='Tóner M disponible',
        default=False,
        readonly=True,
    )

    toner_yellow_available = fields.Boolean(
        string='Tóner Y disponible',
        default=False,
        readonly=True,
    )

    # ========================================================
    # CAPACIDADES
    # ========================================================

    capability_print = fields.Boolean(
        string='Impresión',
        readonly=True,
    )

    capability_copy = fields.Boolean(
        string='Copiadora',
        readonly=True,
    )

    capability_scan = fields.Boolean(
        string='Escáner',
        readonly=True,
    )

    capability_fax = fields.Boolean(
        string='Fax',
        readonly=True,
    )

    capability_color = fields.Boolean(
        string='Color',
        readonly=True,
    )

    capability_duplex = fields.Boolean(
        string='Dúplex',
        readonly=True,
    )

    capability_adf = fields.Boolean(
        string='ADF',
        readonly=True,
    )

    capability_radf = fields.Boolean(
        string='RADF',
        readonly=True,
    )

    capability_spdf = fields.Boolean(
        string='SPDF',
        readonly=True,
    )

    capability_ocr = fields.Boolean(
        string='OCR',
        readonly=True,
    )

    capability_searchable_pdf = fields.Boolean(
        string='PDF buscable',
        readonly=True,
    )

    capability_pdfa = fields.Boolean(
        string='PDF/A',
        readonly=True,
    )

    capability_hdd = fields.Boolean(
        string='Disco duro',
        readonly=True,
    )

    capability_ssd = fields.Boolean(
        string='SSD',
        readonly=True,
    )

    capability_wifi = fields.Boolean(
        string='Wi-Fi',
        readonly=True,
    )

    capability_nfc = fields.Boolean(
        string='NFC',
        readonly=True,
    )

    capability_card_reader = fields.Boolean(
        string='Lector tarjetas',
        readonly=True,
    )

    capability_finisher = fields.Boolean(
        string='Finisher',
        readonly=True,
    )

    capability_stapler = fields.Boolean(
        string='Engrapador',
        readonly=True,
    )

    capability_punch = fields.Boolean(
        string='Perforador',
        readonly=True,
    )

    capability_booklet = fields.Boolean(
        string='Booklet',
        readonly=True,
    )

    # ========================================================
    # HARDWARE
    # ========================================================

    installed_memory_mb = fields.Float(
        string='Memoria instalada (MB)',
        readonly=True,
    )

    storage_total_mb = fields.Float(
        string='Almacenamiento total (MB)',
        readonly=True,
    )

    storage_free_mb = fields.Float(
        string='Almacenamiento libre (MB)',
        readonly=True,
    )

    tray_count = fields.Integer(
        string='Bandejas detectadas',
        default=0,
        readonly=True,
    )

    accessory_count = fields.Integer(
        string='Accesorios detectados',
        default=0,
        readonly=True,
    )

    component_count = fields.Integer(
        string='Componentes detectados',
        default=0,
        readonly=True,
    )

    # ========================================================
    # ALERTAS
    # ========================================================

    active_alert_count = fields.Integer(
        string='Alertas activas',
        default=0,
        readonly=True,
        index=True,
    )

    has_active_alerts = fields.Boolean(
        string='Tiene alertas',
        compute='_compute_has_active_alerts',
        store=True,
        index=True,
    )

    highest_alert_severity = fields.Selection(
        [
            ('none', 'Sin alertas'),
            ('info', 'Información'),
            ('warning', 'Advertencia'),
            ('critical', 'Crítica'),
        ],
        string='Mayor severidad',
        default='none',
        readonly=True,
        index=True,
    )

    # ========================================================
    # DESCUBRIMIENTO
    # ========================================================

    discovery_state = fields.Selection(
        [
            ('new', 'Nuevo'),
            ('identified', 'Identificado'),
            ('profiled', 'Perfil asignado'),
            ('monitoring', 'Monitoreando'),
            ('unsupported', 'No soportado'),
            ('ignored', 'Ignorado'),
        ],
        string='Estado discovery',
        default='new',
        tracking=True,
        index=True,
    )

    first_discovered = fields.Datetime(
        string='Primera detección',
        default=fields.Datetime.now,
        readonly=True,
        copy=False,
        index=True,
    )

    last_discovery = fields.Datetime(
        string='Último discovery',
        readonly=True,
        copy=False,
    )

    needs_discovery = fields.Boolean(
        string='Requiere discovery',
        default=True,
        tracking=True,
        index=True,
    )

    discovery_reason = fields.Char(
        string='Motivo discovery',
        readonly=True,
        copy=False,
    )

    is_confirmed_printer = fields.Boolean(
        string='Impresora confirmada',
        default=False,
        tracking=True,
        index=True,
    )

    is_ignored = fields.Boolean(
        string='Ignorado',
        default=False,
        tracking=True,
        index=True,
    )

    # ========================================================
    # RAW / RESUMEN ACTUAL
    # ========================================================

    last_raw_payload = fields.Text(
        string='Último payload RAW',
        readonly=True,
        copy=False,
    )

    last_summary = fields.Text(
        string='Último resumen',
        readonly=True,
        copy=False,
    )

    # ========================================================
    # HISTÓRICO
    # ========================================================

    snapshot_ids = fields.One2many(
        'sat.monitoring.snapshot',
        'device_id',
        string='Snapshots',
        copy=False,
    )

    snapshot_count = fields.Integer(
        string='Snapshots',
        compute='_compute_snapshot_count',
    )

    reading_ids = fields.One2many(
        'sat.monitoring.reading',
        'device_id',
        string='Lecturas',
        copy=False,
    )

    alert_ids = fields.One2many(
        'sat.monitoring.alert',
        'device_id',
        string='Alertas',
        copy=False,
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
            'sat_monitoring_device_snmp_port_valid',
            'CHECK(snmp_port > 0 AND snmp_port <= 65535)',
            'El puerto SNMP debe estar entre 1 y 65535.',
        ),
        (
            'sat_monitoring_device_failures_positive',
            'CHECK(consecutive_failures >= 0)',
            'Los fallos consecutivos no pueden ser negativos.',
        ),
        (
            'sat_monitoring_device_alert_count_positive',
            'CHECK(active_alert_count >= 0)',
            'La cantidad de alertas no puede ser negativa.',
        ),
        (
            'sat_monitoring_device_tray_count_positive',
            'CHECK(tray_count >= 0)',
            'La cantidad de bandejas no puede ser negativa.',
        ),
        (
            'sat_monitoring_device_accessory_count_positive',
            'CHECK(accessory_count >= 0)',
            'La cantidad de accesorios no puede ser negativa.',
        ),
        (
            'sat_monitoring_device_component_count_positive',
            'CHECK(component_count >= 0)',
            'La cantidad de componentes no puede ser negativa.',
        ),
    ]

    # ========================================================
    # COMPUTES
    # ========================================================

    @api.depends(
        'credential_id',
        'network_id.credential_id',
    )
    def _compute_effective_credential(self):
        for record in self:
            record.effective_credential_id = (
                record.credential_id
                or record.network_id.credential_id
            )

    @api.depends('active_alert_count')
    def _compute_has_active_alerts(self):
        for record in self:
            record.has_active_alerts = (
                record.active_alert_count > 0
            )

    def _compute_snapshot_count(self):
        if not self.ids:
            for record in self:
                record.snapshot_count = 0
            return

        Snapshot = self.env[
            'sat.monitoring.snapshot'
        ]

        groups = Snapshot.read_group(
            [
                (
                    'device_id',
                    'in',
                    self.ids,
                ),
            ],
            ['device_id'],
            ['device_id'],
        )

        counts = {
            item['device_id'][0]:
                item['device_id_count']
            for item in groups
            if item.get('device_id')
        }

        for record in self:
            record.snapshot_count = counts.get(
                record.id,
                0,
            )

    # ========================================================
    # ONCHANGE
    # ========================================================

    @api.onchange('network_id')
    def _onchange_network_id(self):
        for record in self:
            if not record.network_id:
                continue

            if not record.agent_id:
                record.agent_id = (
                    record.network_id.agent_id
                )

            if not record.partner_id:
                record.partner_id = (
                    record.network_id.partner_id
                )

            if not record.branch_name:
                record.branch_name = (
                    record.network_id.branch_name
                )

    @api.onchange('agent_id')
    def _onchange_agent_id(self):
        for record in self:
            if (
                record.network_id
                and record.agent_id
                and record.network_id.agent_id
                != record.agent_id
            ):
                record.network_id = False

    @api.onchange('mac_address')
    def _onchange_mac_address(self):
        for record in self:
            if record.mac_address:
                record.mac_address = (
                    _normalize_mac(
                        record.mac_address
                    )
                )

    @api.onchange('technology')
    def _onchange_technology(self):
        for record in self:
            if record.technology == 'mono':
                record.capability_color = False

            elif record.technology == 'color':
                record.capability_color = True

    # ========================================================
    # CREATE
    # ========================================================

    @api.model_create_multi
    def create(self, vals_list):
        Network = self.env[
            'sat.monitoring.network'
        ]

        for vals in vals_list:
            if vals.get('mac_address'):
                vals['mac_address'] = (
                    _normalize_mac(
                        vals['mac_address']
                    )
                )

            network_id = vals.get(
                'network_id'
            )

            if network_id:
                network = Network.browse(
                    network_id
                )

                if network.exists():
                    vals.setdefault(
                        'agent_id',
                        network.agent_id.id,
                    )

                    if network.partner_id:
                        vals.setdefault(
                            'partner_id',
                            network.partner_id.id,
                        )

                    if network.branch_name:
                        vals.setdefault(
                            'branch_name',
                            network.branch_name,
                        )

            if not vals.get('name'):
                name_parts = []

                if vals.get('model'):
                    name_parts.append(
                        vals['model']
                    )

                if vals.get('serial'):
                    name_parts.append(
                        vals['serial']
                    )

                if vals.get('ip_address'):
                    name_parts.append(
                        vals['ip_address']
                    )

                vals['name'] = (
                    ' - '.join(
                        name_parts
                    )
                    or _('Equipo SNMP')
                )

        return super().create(
            vals_list
        )

    # ========================================================
    # WRITE
    # ========================================================

    def write(self, vals):
        if vals.get('mac_address'):
            vals['mac_address'] = (
                _normalize_mac(
                    vals['mac_address']
                )
            )

        if vals.get('network_id'):
            network = self.env[
                'sat.monitoring.network'
            ].browse(
                vals['network_id']
            )

            if network.exists():
                if 'agent_id' not in vals:
                    vals['agent_id'] = (
                        network.agent_id.id
                    )

                if (
                    'partner_id' not in vals
                    and network.partner_id
                ):
                    vals['partner_id'] = (
                        network.partner_id.id
                    )

                if (
                    'branch_name' not in vals
                    and network.branch_name
                ):
                    vals['branch_name'] = (
                        network.branch_name
                    )

        return super().write(vals)

    # ========================================================
    # VALIDACIONES
    # ========================================================

    @api.constrains('ip_address')
    def _check_ip_address(self):
        for record in self:
            if (
                record.ip_address
                and not _valid_ipv4(
                    record.ip_address
                )
            ):
                raise ValidationError(
                    _(
                        'La dirección IPv4 "%s" '
                        'no es válida.'
                    ) % record.ip_address
                )

    @api.constrains('mac_address')
    def _check_mac_address(self):
        for record in self:
            if (
                record.mac_address
                and not _valid_mac(
                    record.mac_address
                )
            ):
                raise ValidationError(
                    _(
                        'La dirección MAC "%s" '
                        'no es válida.'
                    ) % record.mac_address
                )

    @api.constrains(
        'agent_id',
        'network_id',
    )
    def _check_agent_network(self):
        for record in self:
            if not record.network_id:
                continue

            if (
                record.agent_id
                and record.network_id.agent_id
                != record.agent_id
            ):
                raise ValidationError(
                    _(
                        'El agente del equipo debe ser '
                        'el mismo agente asignado a la red.'
                    )
                )

    @api.constrains(
        'partner_id',
        'network_id',
    )
    def _check_partner_network(self):
        for record in self:
            if not (
                record.partner_id
                and record.network_id
                and record.network_id.partner_id
            ):
                continue

            if (
                record.partner_id
                != record.network_id.partner_id
            ):
                raise ValidationError(
                    _(
                        'El cliente del equipo no coincide '
                        'con el cliente configurado en la red.'
                    )
                )

    @api.constrains(
        'credential_id',
        'partner_id',
    )
    def _check_credential_partner(self):
        for record in self:
            credential = (
                record.credential_id
            )

            if not credential:
                continue

            if credential.global_credential:
                continue

            if (
                credential.partner_id
                and record.partner_id
                and credential.partner_id
                != record.partner_id
            ):
                raise ValidationError(
                    _(
                        'La credencial SNMP seleccionada '
                        'pertenece a otro cliente.'
                    )
                )

    @api.constrains(
        'ip_address',
        'network_id',
    )
    def _check_ip_inside_network(self):
        for record in self:
            if not (
                record.ip_address
                and record.network_id
            ):
                continue

            network = record.network_id

            if network.contains_ip(
                record.ip_address
            ):
                continue

            included = [
                line.strip()
                for line in (
                    network.included_ips or ''
                ).splitlines()
                if line.strip()
            ]

            if record.ip_address in included:
                continue

            raise ValidationError(
                _(
                    'La IP %(ip)s no pertenece a la red '
                    '%(network)s.'
                ) % {
                    'ip':
                        record.ip_address,

                    'network':
                        network.cidr,
                }
            )

    # ========================================================
    # ASIGNACIÓN AUTOMÁTICA DE PERFIL
    # ========================================================

    def action_find_snmp_profile(self):
        """
        Selecciona automáticamente el mejor perfil SNMP.
        """
        Profile = self.env[
            'sat.snmp.profile'
        ]

        for record in self:
            if (
                record.profile_manual
                and record.profile_id
            ):
                continue

            result = Profile.find_best_profile(
                brand_code=record.marca_codigo,
                manufacturer=record.manufacturer_raw,
                model=(
                    record.model
                    or record.model_raw
                ),
                sysdescr=record.sysdescr,
                enterprise_id=record.enterprise_id,
                firmware=record.firmware,
                technology=(
                    record.technology
                    if record.technology
                    in ('mono', 'color')
                    else None
                ),
                include_testing=True,
            )

            profile = result.get(
                'profile'
            )

            match = result.get(
                'match'
            )

            if profile and match:
                record.sudo().write({
                    'profile_id':
                        profile.id,

                    'profile_match_score':
                        match.get(
                            'score',
                            0,
                        ),

                    'profile_match_date':
                        fields.Datetime.now(),

                    'profile_match_details':
                        _json_dumps_safe(
                            match
                        ),

                    'discovery_state':
                        'profiled',

                    'needs_discovery':
                        False,

                    'discovery_reason':
                        False,
                })

            else:
                record.sudo().write({
                    'profile_id':
                        False,

                    'profile_match_score':
                        0,

                    'profile_match_date':
                        fields.Datetime.now(),

                    'profile_match_details':
                        _json_dumps_safe(
                            match or {}
                        ),

                    'needs_discovery':
                        True,

                    'discovery_reason':
                        'profile_not_found',
                })

        return True

    # ========================================================
    # PERFIL MANUAL
    # ========================================================

    def action_mark_profile_manual(self):
        for record in self:
            if not record.profile_id:
                raise UserError(
                    _(
                        'Debe seleccionar un perfil SNMP '
                        'antes de marcarlo como manual.'
                    )
                )

            record.write({
                'profile_manual':
                    True,
            })

        return True

    def action_enable_auto_profile(self):
        self.write({
            'profile_manual':
                False,
        })

        return self.action_find_snmp_profile()

    # ========================================================
    # POLLING EXITOSO
    # ========================================================

    def register_poll_success(
        self,
        response_ms=None,
        snmp_version=None,
    ):
        now = fields.Datetime.now()

        for record in self:
            values = {
                'online':
                    True,

                'snmp_available':
                    True,

                'last_seen':
                    now,

                'last_poll_date':
                    now,

                'last_successful_poll':
                    now,

                'consecutive_failures':
                    0,

                'last_poll_error':
                    False,
            }

            if not record.first_seen:
                values['first_seen'] = now

            if response_ms is not None:
                try:
                    values[
                        'last_response_ms'
                    ] = max(
                        float(response_ms),
                        0.0,
                    )
                except Exception:
                    pass

            if snmp_version in (
                '1',
                '2c',
                '3',
            ):
                values[
                    'last_snmp_version_used'
                ] = snmp_version

            if record.status == 'offline':
                values['status'] = 'unknown'

            if record.discovery_state in (
                'identified',
                'profiled',
            ):
                values[
                    'discovery_state'
                ] = 'monitoring'

            record.sudo().write(
                values
            )

        return True

    # ========================================================
    # POLLING FALLIDO
    # ========================================================

    def register_poll_failure(
        self,
        error_message=None,
    ):
        now = fields.Datetime.now()

        for record in self:
            failures = (
                record.consecutive_failures
                + 1
            )

            values = {
                'last_poll_date':
                    now,

                'last_failed_poll':
                    now,

                'consecutive_failures':
                    failures,

                'last_poll_error':
                    _clean_text(
                        error_message
                    ),
            }

            # Evita marcar offline por una pérdida puntual.
            if failures >= 3:
                values.update({
                    'online':
                        False,

                    'snmp_available':
                        False,

                    'status':
                        'offline',
                })

            record.sudo().write(
                values
            )

        return True

    # ========================================================
    # APLICAR IDENTIDAD
    # ========================================================

    def apply_identity_payload(
        self,
        payload,
    ):
        """
        Actualiza identidad descubierta.

        Payload conceptual:

        {
            "ip": "192.168.1.10",
            "mac": "...",
            "hostname": "...",

            "manufacturer": "RICOH",
            "brand_code": "ricoh",

            "model": "MP C307",
            "serial": "...",
            "firmware": "1.13",

            "enterprise_id": "367",
            "sysdescr": "...",

            "technology": "color",

            "system_name": "...",
            "system_location": "...",
            "system_contact": "...",
            "engine_id": "..."
        }
        """
        self.ensure_one()

        payload = payload or {}

        vals = {
            'last_discovery':
                fields.Datetime.now(),

            'manufacturer_raw':
                _clean_text(
                    payload.get(
                        'manufacturer'
                    )
                ),

            'model_raw':
                _clean_text(
                    payload.get(
                        'model_raw'
                    )
                    or payload.get(
                        'model'
                    )
                ),

            'sysdescr':
                _clean_text(
                    payload.get(
                        'sysdescr'
                    )
                    or payload.get(
                        'description'
                    )
                ),

            'enterprise_id':
                _clean_text(
                    payload.get(
                        'enterprise_id'
                    )
                ),

            'firmware':
                _clean_text(
                    payload.get(
                        'firmware'
                    )
                ),

            'hostname':
                _clean_text(
                    payload.get(
                        'hostname'
                    )
                ),

            'system_name':
                _clean_text(
                    payload.get(
                        'system_name'
                    )
                ),

            'system_location':
                _clean_text(
                    payload.get(
                        'system_location'
                    )
                ),

            'system_contact':
                _clean_text(
                    payload.get(
                        'system_contact'
                    )
                ),

            'engine_id':
                _clean_text(
                    payload.get(
                        'engine_id'
                    )
                ),
        }

        if payload.get('model'):
            vals['model'] = (
                _clean_text(
                    payload['model']
                )
            )

        if payload.get('serial'):
            vals['serial'] = (
                _clean_text(
                    payload['serial']
                )
            )

        if payload.get('ip'):
            vals['ip_address'] = (
                _clean_text(
                    payload['ip']
                )
            )

        if payload.get('mac'):
            vals['mac_address'] = (
                _normalize_mac(
                    payload['mac']
                )
            )

        if payload.get('gateway'):
            vals['gateway'] = (
                _clean_text(
                    payload['gateway']
                )
            )

        if payload.get('subnet_mask'):
            vals['subnet_mask'] = (
                _clean_text(
                    payload['subnet_mask']
                )
            )

        if payload.get('ipv6'):
            vals['ipv6_address'] = (
                _clean_text(
                    payload['ipv6']
                )
            )

        technology = _clean_text(
            payload.get(
                'technology'
            )
        ).lower()

        if technology in (
            'mono',
            'color',
        ):
            vals['technology'] = (
                technology
            )

            vals[
                'capability_color'
            ] = (
                technology == 'color'
            )

        brand_code = _clean_text(
            payload.get(
                'brand_code'
            )
        )

        if brand_code:
            marca = self.env[
                'marca.marca'
            ].search(
                [
                    (
                        'codigo_tecnico',
                        '=',
                        brand_code,
                    ),
                ],
                limit=1,
            )

            if marca:
                vals['marca_id'] = (
                    marca.id
                )

        vals['discovery_state'] = (
            'identified'
        )

        self.sudo().write(vals)

        if not self.profile_manual:
            self.action_find_snmp_profile()

        return True

    # ========================================================
    # APLICAR MÉTRICAS ACTUALES
    # ========================================================

    def apply_current_metrics(
        self,
        metrics,
    ):
        """
        Actualiza únicamente el resumen rápido del equipo.

        Todas las demás métricas permanecen disponibles
        en sat.monitoring.reading.
        """
        self.ensure_one()

        metrics = metrics or {}

        mapping = {
            # CONTADORES
            'machine_total':
                'counter_machine_total',

            'total_bw':
                'counter_total_bw',

            'total_color':
                'counter_total_color',

            'copy_total':
                'counter_copy_total',

            'copy_bw':
                'counter_copy_bw',

            'copy_color':
                'counter_copy_color',

            'print_total':
                'counter_print_total',

            'print_bw':
                'counter_print_bw',

            'print_color':
                'counter_print_color',

            'scan_total':
                'counter_scan_total',

            'scan_bw':
                'counter_scan_bw',

            'scan_color':
                'counter_scan_color',

            'fax_total':
                'counter_fax_total',

            'duplex_total':
                'counter_duplex',

            'large_paper_total':
                'counter_large_paper',

            # CAPACIDADES
            'print_supported':
                'capability_print',

            'copy_supported':
                'capability_copy',

            'scan_supported':
                'capability_scan',

            'fax_supported':
                'capability_fax',

            'color_supported':
                'capability_color',

            'duplex_supported':
                'capability_duplex',

            'adf_present':
                'capability_adf',

            'radf_present':
                'capability_radf',

            'spdf_present':
                'capability_spdf',

            'ocr_supported':
                'capability_ocr',

            'searchable_pdf_supported':
                'capability_searchable_pdf',

            'pdfa_supported':
                'capability_pdfa',

            'hdd_present':
                'capability_hdd',

            'ssd_present':
                'capability_ssd',

            'wifi_present':
                'capability_wifi',

            'nfc_present':
                'capability_nfc',

            'card_reader_present':
                'capability_card_reader',

            'finisher_present':
                'capability_finisher',

            'stapler_present':
                'capability_stapler',

            'punch_present':
                'capability_punch',

            'booklet_present':
                'capability_booklet',

            # HARDWARE
            'memory_mb':
                'installed_memory_mb',

            'storage_total_mb':
                'storage_total_mb',

            'storage_free_mb':
                'storage_free_mb',

            'tray_count':
                'tray_count',

            'accessory_count':
                'accessory_count',

            'component_count':
                'component_count',
        }

        vals = {}

        for metric_code, field_name in mapping.items():
            if metric_code not in metrics:
                continue

            value = metrics.get(
                metric_code
            )

            if value is None:
                continue

            vals[field_name] = value

        # ----------------------------------------------------
        # TÓNER
        # ----------------------------------------------------

        toner_mapping = {
            'toner_k': (
                'toner_black',
                'toner_black_available',
            ),

            'toner_c': (
                'toner_cyan',
                'toner_cyan_available',
            ),

            'toner_m': (
                'toner_magenta',
                'toner_magenta_available',
            ),

            'toner_y': (
                'toner_yellow',
                'toner_yellow_available',
            ),
        }

        for metric_code, (
            value_field,
            available_field,
        ) in toner_mapping.items():

            if metric_code not in metrics:
                continue

            value = metrics.get(
                metric_code
            )

            if value is None:
                continue

            try:
                numeric_value = float(
                    value
                )
            except Exception:
                continue

            # Valores negativos pueden ser sentinelas.
            # No convertir a 0 automáticamente.
            if numeric_value < 0:
                vals[
                    available_field
                ] = False

                continue

            vals[
                value_field
            ] = numeric_value

            vals[
                available_field
            ] = True

        if vals:
            self.sudo().write(vals)

        return True

    # ========================================================
    # ESTADO
    # ========================================================

    def apply_status(
        self,
        status=None,
        active_alert_count=None,
        highest_severity=None,
    ):
        self.ensure_one()

        vals = {}

        if status in (
            'unknown',
            'ready',
            'busy',
            'warning',
            'error',
            'offline',
        ):
            vals['status'] = status

        if active_alert_count is not None:
            try:
                vals[
                    'active_alert_count'
                ] = max(
                    int(
                        active_alert_count
                    ),
                    0,
                )
            except Exception:
                pass

        if highest_severity in (
            'none',
            'info',
            'warning',
            'critical',
        ):
            vals[
                'highest_alert_severity'
            ] = highest_severity

        if vals:
            self.sudo().write(vals)

        return True

    # ========================================================
    # DISCOVERY
    # ========================================================

    def action_require_discovery(
        self,
        reason=None,
    ):
        self.write({
            'needs_discovery':
                True,

            'discovery_reason':
                _clean_text(
                    reason
                )
                or 'manual_request',
        })

        return True

    def action_confirm_printer(self):
        self.write({
            'is_confirmed_printer':
                True,

            'is_ignored':
                False,
        })

        return True

    def action_ignore_device(self):
        self.write({
            'monitoring_enabled':
                False,

            'inventory_enabled':
                False,

            'is_ignored':
                True,

            'discovery_state':
                'ignored',
        })

        return True

    def action_enable_monitoring(self):
        self.write({
            'monitoring_enabled':
                True,

            'inventory_enabled':
                True,

            'is_ignored':
                False,

            'needs_discovery':
                True,

            'discovery_state':
                'new',
        })

        return True

    # ========================================================
    # CONFIGURACIÓN EFECTIVA
    # ========================================================

    def get_effective_credential(self):
        self.ensure_one()

        return (
            self.credential_id
            or self.network_id.credential_id
        )

    # ========================================================
    # CONFIGURACIÓN PARA AGENTE
    # ========================================================

    def get_agent_configuration(self):
        """
        Configuración completa del equipo.

        IMPORTANTE:
        La credencial todavía devuelve únicamente metadatos,
        mientras no implementemos el almacén reversible cifrado.
        """
        self.ensure_one()

        credential = (
            self.get_effective_credential()
        )

        credential_payload = {}

        if credential:
            credential_payload = (
                credential.get_agent_payload()
            )

        profile_payload = {}

        if self.profile_id:
            profile_payload = (
                self.profile_id.get_agent_payload()
            )

        return {
            'device': {
                'id':
                    self.id,

                'name':
                    self.name,

                'agent_id':
                    self.agent_id.id
                    if self.agent_id
                    else False,

                'network_id':
                    self.network_id.id
                    if self.network_id
                    else False,

                'ip':
                    self.ip_address or '',

                'port':
                    self.snmp_port,

                'mac':
                    self.mac_address or '',

                'hostname':
                    self.hostname or '',

                'brand_code':
                    self.marca_codigo or '',

                'manufacturer':
                    self.manufacturer_raw
                    or '',

                'model':
                    self.model or '',

                'model_raw':
                    self.model_raw or '',

                'serial':
                    self.serial or '',

                'firmware':
                    self.firmware or '',

                'enterprise_id':
                    self.enterprise_id
                    or '',

                'technology':
                    self.technology,

                'snmp_version':
                    self.snmp_version,

                'monitoring_enabled':
                    self.monitoring_enabled,

                'inventory_enabled':
                    self.inventory_enabled,

                'alert_monitoring_enabled':
                    self.alert_monitoring_enabled,

                'job_monitoring_enabled':
                    self.job_monitoring_enabled,

                'needs_discovery':
                    self.needs_discovery,

                'profile_manual':
                    self.profile_manual,
            },

            'credential':
                credential_payload,

            'profile':
                profile_payload,
        }

    # ========================================================
    # RESUMEN
    # ========================================================

    def get_device_summary(self):
        self.ensure_one()

        return {
            'id':
                self.id,

            'name':
                self.name,

            'client':
                self.partner_id.display_name
                if self.partner_id
                else '',

            'branch':
                self.branch_name or '',

            'agent':
                self.agent_id.code
                if self.agent_id
                else '',

            'network':
                self.network_id.cidr
                if self.network_id
                else '',

            'ip':
                self.ip_address or '',

            'mac':
                self.mac_address or '',

            'brand':
                self.marca_codigo or '',

            'model':
                self.model or self.model_raw or '',

            'serial':
                self.serial or '',

            'firmware':
                self.firmware or '',

            'technology':
                self.technology,

            'profile':
                self.profile_code or '',

            'profile_revision':
                self.profile_revision or 0,

            'online':
                self.online,

            'status':
                self.status,

            'last_seen':
                (
                    fields.Datetime.to_string(
                        self.last_seen
                    )
                    if self.last_seen
                    else ''
                ),

            'active_alert_count':
                self.active_alert_count,

            'highest_alert_severity':
                self.highest_alert_severity,

            'machine_total':
                self.counter_machine_total,

            'toner': {
                'k':
                    self.toner_black
                    if self.toner_black_available
                    else None,

                'c':
                    self.toner_cyan
                    if self.toner_cyan_available
                    else None,

                'm':
                    self.toner_magenta
                    if self.toner_magenta_available
                    else None,

                'y':
                    self.toner_yellow
                    if self.toner_yellow_available
                    else None,
            },
        }