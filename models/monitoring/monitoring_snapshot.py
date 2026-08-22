# -*- coding: utf-8 -*-

import json
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


# ============================================================
# SNAPSHOT DE MONITOREO
# ============================================================

class SatMonitoringSnapshot(models.Model):
    """
    Representa un ciclo completo de polling SNMP.

    Conserva históricamente:

        - equipo
        - cliente
        - agente
        - red
        - credencial utilizada
        - perfil utilizado
        - versión/revisión del perfil
        - identidad vista durante la lectura
        - métricas
        - alertas
        - estado
        - tiempos
        - errores
        - payload RAW

    Esto permite auditar exactamente cómo se obtuvo una lectura.
    """

    _name = 'sat.monitoring.snapshot'
    _description = 'Snapshot de monitoreo SNMP'
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    # ========================================================
    # EQUIPO
    # ========================================================

    device_id = fields.Many2one(
        'sat.monitoring.device',
        string='Equipo',
        required=True,
        ondelete='cascade',
        index=True,
    )

    maquina_id = fields.Many2one(
        related='device_id.maquina_id',
        string='Máquina SAT',
        store=True,
        readonly=True,
        index=True,
    )

    partner_id = fields.Many2one(
        related='device_id.partner_id',
        string='Cliente',
        store=True,
        readonly=True,
        index=True,
    )

    # ========================================================
    # AGENTE
    # ========================================================

    agent_id = fields.Many2one(
        'sat.monitoring.agent',
        string='Agente',
        ondelete='set null',
        readonly=True,
        index=True,
    )

    agent_code = fields.Char(
        string='Código agente',
        readonly=True,
        index=True,
    )

    agent_name = fields.Char(
        string='Nombre agente',
        readonly=True,
    )

    agent_identifier = fields.Char(
        string='Identificador reportado',
        readonly=True,
        index=True,
    )

    agent_version = fields.Char(
        string='Versión agente',
        readonly=True,
    )

    agent_hostname = fields.Char(
        string='Host agente',
        readonly=True,
    )

    # ========================================================
    # RED
    # ========================================================

    network_id = fields.Many2one(
        'sat.monitoring.network',
        string='Red',
        ondelete='set null',
        readonly=True,
        index=True,
    )

    network_code = fields.Char(
        string='Código red',
        readonly=True,
        index=True,
    )

    network_cidr = fields.Char(
        string='CIDR',
        readonly=True,
    )

    branch_name = fields.Char(
        string='Sede',
        readonly=True,
        index=True,
    )

    # ========================================================
    # CREDENCIAL
    # ========================================================

    credential_id = fields.Many2one(
        'sat.snmp.credential',
        string='Credencial SNMP',
        ondelete='set null',
        readonly=True,
        index=True,
    )

    credential_code = fields.Char(
        string='Código credencial',
        readonly=True,
        index=True,
    )

    credential_name = fields.Char(
        string='Nombre credencial',
        readonly=True,
    )

    credential_snmp_version = fields.Selection(
        [
            ('1', 'SNMP v1'),
            ('2c', 'SNMP v2c'),
            ('3', 'SNMP v3'),
        ],
        string='Versión credencial',
        readonly=True,
    )

    # ========================================================
    # PERFIL
    # ========================================================

    profile_id = fields.Many2one(
        'sat.snmp.profile',
        string='Perfil SNMP',
        ondelete='set null',
        readonly=True,
        index=True,
    )

    profile_code = fields.Char(
        string='Código perfil',
        readonly=True,
        index=True,
    )

    profile_name = fields.Char(
        string='Nombre perfil',
        readonly=True,
    )

    profile_version = fields.Char(
        string='Versión perfil',
        readonly=True,
    )

    profile_revision = fields.Integer(
        string='Revisión perfil',
        readonly=True,
    )

    profile_confidence = fields.Selection(
        [
            ('unknown', 'Sin validar'),
            ('candidate', 'Candidato'),
            ('provisional', 'Provisional'),
            ('high', 'Alta'),
            ('very_high', 'Muy alta'),
        ],
        string='Confianza perfil',
        readonly=True,
    )

    profile_match_score = fields.Integer(
        string='Puntuación perfil',
        readonly=True,
    )

    # ========================================================
    # FECHAS
    # ========================================================

    date = fields.Datetime(
        string='Fecha lectura',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )

    started_at = fields.Datetime(
        string='Inicio',
        index=True,
    )

    finished_at = fields.Datetime(
        string='Fin',
        index=True,
    )

    duration_ms = fields.Float(
        string='Duración total (ms)',
        default=0.0,
    )

    snmp_response_ms = fields.Float(
        string='Respuesta SNMP (ms)',
        default=0.0,
    )

    # ========================================================
    # ESTADO
    # ========================================================

    state = fields.Selection(
        [
            ('running', 'En proceso'),
            ('success', 'Correcto'),
            ('partial', 'Parcial'),
            ('failed', 'Fallido'),
            ('timeout', 'Timeout'),
            ('offline', 'Sin conexión'),
        ],
        string='Resultado',
        required=True,
        default='running',
        index=True,
    )

    success = fields.Boolean(
        string='Exitoso',
        compute='_compute_result_flags',
        store=True,
        index=True,
    )

    partial = fields.Boolean(
        string='Parcial',
        compute='_compute_result_flags',
        store=True,
        index=True,
    )

    failed = fields.Boolean(
        string='Fallido',
        compute='_compute_result_flags',
        store=True,
        index=True,
    )

    error_code = fields.Char(
        string='Código error',
        index=True,
    )

    error_message = fields.Text(
        string='Error',
    )

    warning_message = fields.Text(
        string='Advertencias',
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
        string='Versión SNMP utilizada',
        readonly=True,
        index=True,
    )

    snmp_port = fields.Integer(
        string='Puerto SNMP',
        default=161,
        readonly=True,
    )

    # ========================================================
    # IDENTIDAD OBSERVADA
    # ========================================================

    ip_address = fields.Char(
        string='IP',
        readonly=True,
        index=True,
    )

    ipv6_address = fields.Char(
        string='IPv6',
        readonly=True,
        index=True,
    )

    mac_address = fields.Char(
        string='MAC',
        readonly=True,
        index=True,
    )

    hostname = fields.Char(
        string='Hostname',
        readonly=True,
    )

    manufacturer = fields.Char(
        string='Fabricante',
        readonly=True,
        index=True,
    )

    brand_code = fields.Char(
        string='Código marca',
        readonly=True,
        index=True,
    )

    model = fields.Char(
        string='Modelo',
        readonly=True,
        index=True,
    )

    serial = fields.Char(
        string='Serie',
        readonly=True,
        index=True,
    )

    firmware = fields.Char(
        string='Firmware',
        readonly=True,
    )

    enterprise_id = fields.Char(
        string='Enterprise ID',
        readonly=True,
        index=True,
    )

    sysdescr = fields.Text(
        string='sysDescr',
        readonly=True,
    )

    system_name = fields.Char(
        string='System Name',
        readonly=True,
    )

    system_location = fields.Char(
        string='System Location',
        readonly=True,
    )

    system_contact = fields.Char(
        string='System Contact',
        readonly=True,
    )

    engine_id = fields.Char(
        string='SNMP Engine ID',
        readonly=True,
    )

    technology = fields.Selection(
        [
            ('unknown', 'Desconocido'),
            ('mono', 'Monocromo'),
            ('color', 'Color'),
        ],
        string='Tecnología',
        readonly=True,
    )

    # ========================================================
    # MÉTRICAS
    # ========================================================

    expected_metric_count = fields.Integer(
        string='Métricas esperadas',
        default=0,
    )

    attempted_metric_count = fields.Integer(
        string='Métricas consultadas',
        default=0,
    )

    successful_metric_count = fields.Integer(
        string='Métricas exitosas',
        default=0,
    )

    failed_metric_count = fields.Integer(
        string='Métricas fallidas',
        default=0,
    )

    missing_required_metric_count = fields.Integer(
        string='Obligatorias faltantes',
        default=0,
    )

    metric_success_rate = fields.Float(
        string='Éxito métricas (%)',
        compute='_compute_metric_success_rate',
        store=True,
        digits=(5, 2),
    )

    # ========================================================
    # CATEGORÍAS
    # ========================================================

    identity_count = fields.Integer(
        string='Identidad',
        default=0,
    )

    counter_count = fields.Integer(
        string='Contadores',
        default=0,
    )

    consumable_count = fields.Integer(
        string='Consumibles',
        default=0,
    )

    component_count = fields.Integer(
        string='Componentes',
        default=0,
    )

    tray_count = fields.Integer(
        string='Bandejas',
        default=0,
    )

    accessory_count = fields.Integer(
        string='Accesorios',
        default=0,
    )

    capability_count = fields.Integer(
        string='Capacidades',
        default=0,
    )

    status_count = fields.Integer(
        string='Estados',
        default=0,
    )

    firmware_count = fields.Integer(
        string='Firmware',
        default=0,
    )

    network_metric_count = fields.Integer(
        string='Métricas red',
        default=0,
    )

    storage_count = fields.Integer(
        string='Almacenamiento',
        default=0,
    )

    memory_count = fields.Integer(
        string='Memoria',
        default=0,
    )

    job_count = fields.Integer(
        string='Trabajos',
        default=0,
    )

    alert_count = fields.Integer(
        string='Alertas detectadas',
        default=0,
    )

    # ========================================================
    # RELACIONES
    # ========================================================

    reading_ids = fields.One2many(
        'sat.monitoring.reading',
        'snapshot_id',
        string='Lecturas',
        copy=False,
    )

    reading_count = fields.Integer(
        string='Lecturas guardadas',
        compute='_compute_reading_count',
    )

    alert_ids = fields.One2many(
        'sat.monitoring.alert',
        'snapshot_id',
        string='Alertas',
        copy=False,
    )

    # ========================================================
    # DISCOVERY
    # ========================================================

    discovery_used = fields.Boolean(
        string='Se utilizó discovery',
        default=False,
        readonly=True,
    )

    fallback_discovery_used = fields.Boolean(
        string='Discovery de respaldo',
        default=False,
        readonly=True,
    )

    full_walk_used = fields.Boolean(
        string='Se realizó WALK completo',
        default=False,
        readonly=True,
    )

    discovered_oid_count = fields.Integer(
        string='OIDs descubiertos',
        default=0,
        readonly=True,
    )

    unknown_oid_count = fields.Integer(
        string='OIDs no clasificados',
        default=0,
        readonly=True,
    )

    # ========================================================
    # VALIDACIÓN / PERFIL
    # ========================================================

    profile_mismatch = fields.Boolean(
        string='Posible incompatibilidad de perfil',
        default=False,
        index=True,
    )

    profile_mismatch_reason = fields.Char(
        string='Motivo incompatibilidad',
    )

    requires_review = fields.Boolean(
        string='Requiere revisión',
        default=False,
        index=True,
    )

    review_reason = fields.Char(
        string='Motivo revisión',
    )

    # ========================================================
    # RAW
    # ========================================================

    raw_payload_json = fields.Text(
        string='Payload RAW',
        readonly=True,
        copy=False,
    )

    agent_payload_json = fields.Text(
        string='Payload completo agente',
        readonly=True,
        copy=False,
    )

    summary_text = fields.Text(
        string='Resumen',
        readonly=True,
        copy=False,
    )

    # ========================================================
    # PROCESAMIENTO
    # ========================================================

    processed = fields.Boolean(
        string='Procesado',
        default=False,
        readonly=True,
        index=True,
    )

    processed_at = fields.Datetime(
        string='Procesado en',
        readonly=True,
    )

    # ========================================================
    # SQL
    # ========================================================

    _sql_constraints = [
        (
            'sat_monitoring_snapshot_duration_positive',
            'CHECK(duration_ms >= 0)',
            'La duración no puede ser negativa.',
        ),
        (
            'sat_monitoring_snapshot_response_positive',
            'CHECK(snmp_response_ms >= 0)',
            'El tiempo de respuesta no puede ser negativo.',
        ),
        (
            'sat_monitoring_snapshot_expected_positive',
            'CHECK(expected_metric_count >= 0)',
            'Las métricas esperadas no pueden ser negativas.',
        ),
        (
            'sat_monitoring_snapshot_attempted_positive',
            'CHECK(attempted_metric_count >= 0)',
            'Las métricas consultadas no pueden ser negativas.',
        ),
        (
            'sat_monitoring_snapshot_success_positive',
            'CHECK(successful_metric_count >= 0)',
            'Las métricas exitosas no pueden ser negativas.',
        ),
        (
            'sat_monitoring_snapshot_failed_positive',
            'CHECK(failed_metric_count >= 0)',
            'Las métricas fallidas no pueden ser negativas.',
        ),
        (
            'sat_monitoring_snapshot_required_positive',
            'CHECK(missing_required_metric_count >= 0)',
            'Las métricas obligatorias faltantes no pueden ser negativas.',
        ),
    ]

    # ========================================================
    # DISPLAY NAME
    # ========================================================

    @api.depends(
        'device_id',
        'date',
        'state',
    )
    def _compute_display_name(self):
        state_labels = dict(
            self._fields['state'].selection
        )

        for record in self:
            device_name = (
                record.device_id.display_name
                if record.device_id
                else _('Equipo')
            )

            date_text = (
                fields.Datetime.to_string(
                    record.date
                )
                if record.date
                else ''
            )

            state_name = state_labels.get(
                record.state,
                record.state or '',
            )

            record.display_name = (
                '%s - %s - %s'
                % (
                    device_name,
                    date_text,
                    state_name,
                )
            )

    # ========================================================
    # COMPUTES
    # ========================================================

    @api.depends('state')
    def _compute_result_flags(self):
        for record in self:
            record.success = (
                record.state == 'success'
            )

            record.partial = (
                record.state == 'partial'
            )

            record.failed = (
                record.state
                in (
                    'failed',
                    'timeout',
                    'offline',
                )
            )

    @api.depends(
        'attempted_metric_count',
        'successful_metric_count',
    )
    def _compute_metric_success_rate(self):
        for record in self:
            if record.attempted_metric_count <= 0:
                record.metric_success_rate = 0.0
                continue

            record.metric_success_rate = (
                record.successful_metric_count
                / record.attempted_metric_count
            ) * 100.0

    def _compute_reading_count(self):
        if not self.ids:
            for record in self:
                record.reading_count = 0
            return

        Reading = self.env[
            'sat.monitoring.reading'
        ]

        groups = Reading.read_group(
            [
                (
                    'snapshot_id',
                    'in',
                    self.ids,
                ),
            ],
            ['snapshot_id'],
            ['snapshot_id'],
        )

        counts = {
            item['snapshot_id'][0]:
                item['snapshot_id_count']
            for item in groups
            if item.get('snapshot_id')
        }

        for record in self:
            record.reading_count = (
                counts.get(
                    record.id,
                    0,
                )
            )

    # ========================================================
    # VALIDACIONES
    # ========================================================

    @api.constrains(
        'device_id',
        'agent_id',
        'network_id',
    )
    def _check_traceability(self):
        for record in self:
            device = record.device_id

            if not device:
                continue

            if (
                record.agent_id
                and device.agent_id
                and record.agent_id
                != device.agent_id
            ):
                raise ValidationError(
                    _(
                        'El agente del snapshot no coincide '
                        'con el agente del equipo.'
                    )
                )

            if (
                record.network_id
                and device.network_id
                and record.network_id
                != device.network_id
            ):
                raise ValidationError(
                    _(
                        'La red del snapshot no coincide '
                        'con la red del equipo.'
                    )
                )

    @api.constrains(
        'expected_metric_count',
        'attempted_metric_count',
        'successful_metric_count',
        'failed_metric_count',
    )
    def _check_metric_counts(self):
        for record in self:
            if (
                record.successful_metric_count
                > record.attempted_metric_count
            ):
                raise ValidationError(
                    _(
                        'Las métricas exitosas no pueden '
                        'superar las métricas consultadas.'
                    )
                )

            if (
                record.failed_metric_count
                > record.attempted_metric_count
            ):
                raise ValidationError(
                    _(
                        'Las métricas fallidas no pueden '
                        'superar las métricas consultadas.'
                    )
                )

            if (
                record.successful_metric_count
                + record.failed_metric_count
                > record.attempted_metric_count
            ):
                raise ValidationError(
                    _(
                        'La suma de métricas exitosas y fallidas '
                        'no puede superar las métricas consultadas.'
                    )
                )

    # ========================================================
    # CREAR SNAPSHOT PARA UN EQUIPO
    # ========================================================

    @api.model
    def create_for_device(
        self,
        device,
        started_at=None,
        agent_info=None,
    ):
        """
        Crea el encabezado del ciclo antes de guardar lecturas.

        La información administrativa se copia al snapshot
        para no depender de cambios posteriores en el equipo.
        """
        device.ensure_one()

        agent_info = agent_info or {}

        agent = device.agent_id
        network = device.network_id
        credential = (
            device.get_effective_credential()
        )
        profile = device.profile_id

        now = fields.Datetime.now()

        vals = {
            'device_id':
                device.id,

            'date':
                now,

            'started_at':
                started_at or now,

            'state':
                'running',

            # AGENTE
            'agent_id':
                agent.id
                if agent
                else False,

            'agent_code':
                agent.code
                if agent
                else '',

            'agent_name':
                agent.name
                if agent
                else '',

            'agent_identifier':
                _clean_text(
                    agent_info.get(
                        'identifier'
                    )
                    or (
                        agent.code
                        if agent
                        else ''
                    )
                ),

            'agent_version':
                _clean_text(
                    agent_info.get(
                        'version'
                    )
                    or (
                        agent.agent_version
                        if agent
                        else ''
                    )
                ),

            'agent_hostname':
                _clean_text(
                    agent_info.get(
                        'hostname'
                    )
                    or (
                        agent.hostname
                        if agent
                        else ''
                    )
                ),

            # RED
            'network_id':
                network.id
                if network
                else False,

            'network_code':
                network.code
                if network
                else '',

            'network_cidr':
                network.cidr
                if network
                else '',

            'branch_name':
                (
                    device.branch_name
                    or (
                        network.branch_name
                        if network
                        else ''
                    )
                    or ''
                ),

            # CREDENCIAL
            'credential_id':
                credential.id
                if credential
                else False,

            'credential_code':
                credential.code
                if credential
                else '',

            'credential_name':
                credential.name
                if credential
                else '',

            'credential_snmp_version':
                credential.snmp_version
                if credential
                else False,

            # PERFIL
            'profile_id':
                profile.id
                if profile
                else False,

            'profile_code':
                profile.code
                if profile
                else '',

            'profile_name':
                profile.name
                if profile
                else '',

            'profile_version':
                profile.version
                if profile
                else '',

            'profile_revision':
                profile.revision
                if profile
                else 0,

            'profile_confidence':
                profile.confidence
                if profile
                else 'unknown',

            'profile_match_score':
                device.profile_match_score
                or 0,

            # SNMP
            'snmp_version':
                device.snmp_version,

            'snmp_port':
                device.snmp_port,

            # IDENTIDAD
            'ip_address':
                device.ip_address or '',

            'ipv6_address':
                device.ipv6_address or '',

            'mac_address':
                device.mac_address or '',

            'hostname':
                device.hostname or '',

            'manufacturer':
                device.manufacturer_raw or '',

            'brand_code':
                device.marca_codigo or '',

            'model':
                (
                    device.model
                    or device.model_raw
                    or ''
                ),

            'serial':
                device.serial or '',

            'firmware':
                device.firmware or '',

            'enterprise_id':
                device.enterprise_id or '',

            'sysdescr':
                device.sysdescr or '',

            'system_name':
                device.system_name or '',

            'system_location':
                device.system_location or '',

            'system_contact':
                device.system_contact or '',

            'engine_id':
                device.engine_id or '',

            'technology':
                device.technology,

            'expected_metric_count':
                len(
                    profile.metric_ids.filtered(
                        lambda metric:
                            metric.active
                    )
                )
                if profile
                else 0,
        }

        return self.create(vals)

    # ========================================================
    # APLICAR IDENTIDAD OBSERVADA
    # ========================================================

    def apply_identity(
        self,
        identity,
    ):
        """
        Conserva la identidad observada en ese ciclo.

        No sobrescribe con valores vacíos.
        """
        self.ensure_one()

        identity = identity or {}

        mapping = {
            'ip':
                'ip_address',

            'ipv6':
                'ipv6_address',

            'mac':
                'mac_address',

            'hostname':
                'hostname',

            'manufacturer':
                'manufacturer',

            'brand_code':
                'brand_code',

            'model':
                'model',

            'serial':
                'serial',

            'firmware':
                'firmware',

            'enterprise_id':
                'enterprise_id',

            'sysdescr':
                'sysdescr',

            'system_name':
                'system_name',

            'system_location':
                'system_location',

            'system_contact':
                'system_contact',

            'engine_id':
                'engine_id',
        }

        vals = {}

        for source, target in mapping.items():
            value = identity.get(
                source
            )

            if value in (
                None,
                False,
                '',
            ):
                continue

            vals[target] = _clean_text(
                value
            )

        technology = _clean_text(
            identity.get(
                'technology'
            )
        ).lower()

        if technology in (
            'mono',
            'color',
            'unknown',
        ):
            vals[
                'technology'
            ] = technology

        if vals:
            self.sudo().write(vals)

        return True

    # ========================================================
    # ESTADÍSTICAS
    # ========================================================

    def _prepare_statistics(
        self,
        statistics,
    ):
        statistics = statistics or {}

        def _integer(key):
            try:
                return max(
                    int(
                        statistics.get(
                            key,
                            0,
                        )
                        or 0
                    ),
                    0,
                )
            except Exception:
                return 0

        return {
            'attempted_metric_count':
                _integer('attempted'),

            'successful_metric_count':
                _integer('successful'),

            'failed_metric_count':
                _integer('failed'),

            'missing_required_metric_count':
                _integer('missing_required'),

            'identity_count':
                _integer('identity'),

            'counter_count':
                _integer('counters'),

            'consumable_count':
                _integer('consumables'),

            'component_count':
                _integer('components'),

            'tray_count':
                _integer('trays'),

            'accessory_count':
                _integer('accessories'),

            'capability_count':
                _integer('capabilities'),

            'status_count':
                _integer('statuses'),

            'firmware_count':
                _integer('firmware'),

            'network_metric_count':
                _integer('network'),

            'storage_count':
                _integer('storage'),

            'memory_count':
                _integer('memory'),

            'job_count':
                _integer('jobs'),

            'alert_count':
                _integer('alerts'),

            'discovered_oid_count':
                _integer('discovered_oids'),

            'unknown_oid_count':
                _integer('unknown_oids'),

            'discovery_used':
                bool(
                    statistics.get(
                        'discovery_used'
                    )
                ),

            'fallback_discovery_used':
                bool(
                    statistics.get(
                        'fallback_discovery_used'
                    )
                ),

            'full_walk_used':
                bool(
                    statistics.get(
                        'full_walk_used'
                    )
                ),
        }

    # ========================================================
    # FINALIZACIÓN COMÚN
    # ========================================================

    def _prepare_finish_values(
        self,
        duration_ms=None,
        response_ms=None,
        statistics=None,
        raw_payload=None,
        agent_payload=None,
        summary=None,
    ):
        vals = {
            'finished_at':
                fields.Datetime.now(),

            'processed':
                True,

            'processed_at':
                fields.Datetime.now(),
        }

        if duration_ms is not None:
            try:
                vals['duration_ms'] = max(
                    float(duration_ms),
                    0.0,
                )
            except Exception:
                pass

        if response_ms is not None:
            try:
                vals[
                    'snmp_response_ms'
                ] = max(
                    float(response_ms),
                    0.0,
                )
            except Exception:
                pass

        vals.update(
            self._prepare_statistics(
                statistics
            )
        )

        if raw_payload is not None:
            vals[
                'raw_payload_json'
            ] = _json_dumps_safe(
                raw_payload
            )

        if agent_payload is not None:
            vals[
                'agent_payload_json'
            ] = _json_dumps_safe(
                agent_payload
            )

        if summary is not None:
            vals[
                'summary_text'
            ] = _clean_text(
                summary
            )

        return vals

    # ========================================================
    # FINALIZAR OK
    # ========================================================

    def finish_success(
        self,
        duration_ms=None,
        response_ms=None,
        statistics=None,
        raw_payload=None,
        agent_payload=None,
        summary=None,
        snmp_version=None,
    ):
        self.ensure_one()

        vals = self._prepare_finish_values(
            duration_ms=duration_ms,
            response_ms=response_ms,
            statistics=statistics,
            raw_payload=raw_payload,
            agent_payload=agent_payload,
            summary=summary,
        )

        vals.update({
            'state':
                'success',

            'error_code':
                False,

            'error_message':
                False,
        })

        if snmp_version in (
            '1',
            '2c',
            '3',
        ):
            vals[
                'snmp_version'
            ] = snmp_version

        self.sudo().write(vals)

        self.device_id.register_poll_success(
            response_ms=response_ms,
            snmp_version=(
                snmp_version
                or self.snmp_version
            ),
        )

        if self.agent_id:
            self.agent_id.register_poll_result(
                success=True
            )

        if self.credential_id:
            self.credential_id.register_use()

        return True

    # ========================================================
    # FINALIZAR PARCIAL
    # ========================================================

    def finish_partial(
        self,
        warning_message=None,
        duration_ms=None,
        response_ms=None,
        statistics=None,
        raw_payload=None,
        agent_payload=None,
        summary=None,
        snmp_version=None,
    ):
        self.ensure_one()

        vals = self._prepare_finish_values(
            duration_ms=duration_ms,
            response_ms=response_ms,
            statistics=statistics,
            raw_payload=raw_payload,
            agent_payload=agent_payload,
            summary=summary,
        )

        vals.update({
            'state':
                'partial',

            'warning_message':
                _clean_text(
                    warning_message
                ),
        })

        if snmp_version in (
            '1',
            '2c',
            '3',
        ):
            vals[
                'snmp_version'
            ] = snmp_version

        self.sudo().write(vals)

        # Hubo comunicación, aunque faltaron datos.
        self.device_id.register_poll_success(
            response_ms=response_ms,
            snmp_version=(
                snmp_version
                or self.snmp_version
            ),
        )

        if self.agent_id:
            self.agent_id.register_poll_result(
                success=True
            )

        if self.credential_id:
            self.credential_id.register_use()

        return True

    # ========================================================
    # FINALIZAR FALLIDO
    # ========================================================

    def finish_failure(
        self,
        state='failed',
        error_code=None,
        error_message=None,
        duration_ms=None,
        response_ms=None,
        raw_payload=None,
        agent_payload=None,
    ):
        self.ensure_one()

        if state not in (
            'failed',
            'timeout',
            'offline',
        ):
            state = 'failed'

        vals = self._prepare_finish_values(
            duration_ms=duration_ms,
            response_ms=response_ms,
            statistics=None,
            raw_payload=raw_payload,
            agent_payload=agent_payload,
            summary=None,
        )

        vals.update({
            'state':
                state,

            'error_code':
                _clean_text(
                    error_code
                ),

            'error_message':
                _clean_text(
                    error_message
                ),
        })

        self.sudo().write(vals)

        self.device_id.register_poll_failure(
            error_message=error_message,
        )

        if self.agent_id:
            self.agent_id.register_poll_result(
                success=False
            )

        return True

    # ========================================================
    # REVISIÓN
    # ========================================================

    def require_review(
        self,
        reason=None,
    ):
        self.write({
            'requires_review':
                True,

            'review_reason':
                _clean_text(
                    reason
                )[:250],
        })

        return True

    def mark_profile_mismatch(
        self,
        reason=None,
    ):
        self.write({
            'profile_mismatch':
                True,

            'profile_mismatch_reason':
                _clean_text(
                    reason
                )[:250],

            'requires_review':
                True,

            'review_reason':
                _clean_text(
                    reason
                )[:250]
                or 'profile_mismatch',
        })

        self.device_id.action_require_discovery(
            reason=(
                reason
                or 'profile_mismatch'
            )
        )

        return True

    # ========================================================
    # RECALCULAR ESTADÍSTICAS
    # ========================================================

    def recalculate_statistics(self):
        """
        Recalcula contadores desde sat.monitoring.reading.

        Esto permite reprocesar snapshots posteriormente.
        """
        for snapshot in self:
            readings = (
                snapshot.reading_ids
            )

            successful = readings.filtered(
                lambda reading:
                    reading.success
            )

            failed = readings.filtered(
                lambda reading:
                    not reading.success
            )

            required_missing = readings.filtered(
                lambda reading:
                    reading.required
                    and not reading.success
            )

            def category_count(
                category
            ):
                return len(
                    readings.filtered(
                        lambda reading:
                            reading.category
                            == category
                    )
                )

            snapshot.sudo().write({
                'attempted_metric_count':
                    len(readings),

                'successful_metric_count':
                    len(successful),

                'failed_metric_count':
                    len(failed),

                'missing_required_metric_count':
                    len(
                        required_missing
                    ),

                'identity_count':
                    category_count(
                        'identity'
                    ),

                'counter_count':
                    category_count(
                        'counter'
                    ),

                'consumable_count':
                    category_count(
                        'consumable'
                    ),

                'component_count':
                    category_count(
                        'component'
                    ),

                'tray_count':
                    category_count(
                        'tray'
                    ),

                'accessory_count':
                    category_count(
                        'accessory'
                    ),

                'capability_count':
                    category_count(
                        'capability'
                    ),

                'status_count':
                    category_count(
                        'status'
                    ),

                'firmware_count':
                    category_count(
                        'firmware'
                    ),

                'network_metric_count':
                    category_count(
                        'network'
                    ),

                'storage_count':
                    category_count(
                        'storage'
                    ),

                'memory_count':
                    category_count(
                        'memory'
                    ),

                'job_count':
                    category_count(
                        'job'
                    ),

                'alert_count':
                    category_count(
                        'alert'
                    ),
            })

        return True

    # ========================================================
    # PROCESAR LECTURAS
    # ========================================================

    def process_readings(
        self,
        results,
    ):
        """
        Guarda las lecturas del agente y actualiza el resumen actual
        del dispositivo.
        """
        self.ensure_one()

        readings = self.env[
            'sat.monitoring.reading'
        ].create_batch_from_agent(
            snapshot=self,
            results=results or [],
        )

        readings.update_device_current_values()

        return readings

    # ========================================================
    # PROCESAR ALERTAS
    # ========================================================

    def process_alerts(
        self,
        alerts,
        complete_list=True,
    ):
        """
        Procesa alertas.

        complete_list=True significa:
            "esta lista contiene TODAS las alertas activas actuales".

        Esto será importante para evitar cerrar alertas por error
        cuando en el futuro hagamos polling parcial.
        """
        self.ensure_one()

        Alert = self.env[
            'sat.monitoring.alert'
        ]

        if complete_list:
            return Alert.register_snapshot_alerts(
                snapshot=self,
                alerts=alerts or [],
            )

        # Lista parcial:
        # únicamente crear/actualizar, sin cerrar otras.
        created = Alert.browse()

        metrics_by_code = {}

        if self.profile_id:
            metrics_by_code = {
                metric.code: metric
                for metric
                in self.profile_id.metric_ids.filtered(
                    lambda metric:
                        metric.active
                )
            }

        for alert_data in (
            alerts or []
        ):
            if not isinstance(
                alert_data,
                dict,
            ):
                continue

            metric_code = _clean_text(
                alert_data.get(
                    'metric_code'
                )
            )

            metric = (
                metrics_by_code.get(
                    metric_code
                )
                if metric_code
                else False
            )

            alert = Alert.register_alert(
                device=self.device_id,
                alert_data=alert_data,
                snapshot=self,
                metric=metric,
            )

            created |= alert

        Alert.update_device_alert_summary(
            self.device_id
        )

        return created