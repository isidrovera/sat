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


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


# ============================================================
# ALERTA DE MONITOREO
# ============================================================

class SatMonitoringAlert(models.Model):
    """
    Alerta detectada por SNMP.

    A diferencia de sat.monitoring.reading, una alerta mantiene
    un ciclo de vida:

        primera detección
            ↓
        permanece activa
            ↓
        última detección
            ↓
        desaparece
            ↓
        se cierra

    Ejemplos:

        paper_jam
        toner_black_low
        cover_open
        no_paper
        service_call
        fuser_error
        drum_warning
        waste_toner_full
        offline
    """

    _name = 'sat.monitoring.alert'
    _description = 'Alerta de monitoreo SNMP'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'active desc, severity_rank desc, first_seen desc, id desc'
    _rec_name = 'display_name'

    # ========================================================
    # RELACIONES
    # ========================================================

    device_id = fields.Many2one(
        'sat.monitoring.device',
        string='Equipo',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
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

    snapshot_id = fields.Many2one(
        'sat.monitoring.snapshot',
        string='Último snapshot',
        ondelete='set null',
        index=True,
    )

    first_snapshot_id = fields.Many2one(
        'sat.monitoring.snapshot',
        string='Primer snapshot',
        ondelete='set null',
        readonly=True,
        index=True,
    )

    metric_id = fields.Many2one(
        'sat.snmp.profile.metric',
        string='Métrica origen',
        ondelete='set null',
        index=True,
    )

    # ========================================================
    # IDENTIFICACIÓN
    # ========================================================

    key = fields.Char(
        string='Clave técnica',
        required=True,
        index=True,
        help=(
            'Clave estable utilizada para identificar la misma alerta '
            'en lecturas consecutivas.\n\n'
            'Ejemplos:\n'
            'paper_jam\n'
            'toner_black_low\n'
            'cover_open\n'
            'service_call_sc542'
        ),
    )

    code = fields.Char(
        string='Código',
        index=True,
        help=(
            'Código reportado por el fabricante cuando exista.'
        ),
    )

    name = fields.Char(
        string='Nombre',
        required=True,
        index=True,
    )

    description = fields.Text(
        string='Descripción',
    )

    category = fields.Selection(
        [
            ('device', 'Equipo'),
            ('paper', 'Papel'),
            ('toner', 'Tóner'),
            ('consumable', 'Consumible'),
            ('component', 'Componente'),
            ('cover', 'Tapa / puerta'),
            ('jam', 'Atasco'),
            ('service', 'Servicio técnico'),
            ('network', 'Red'),
            ('storage', 'Almacenamiento'),
            ('temperature', 'Temperatura'),
            ('security', 'Seguridad'),
            ('supply', 'Suministro'),
            ('offline', 'Conectividad'),
            ('other', 'Otro'),
        ],
        string='Categoría',
        default='other',
        required=True,
        index=True,
    )

    group = fields.Char(
        string='Grupo',
        index=True,
    )

    location = fields.Char(
        string='Ubicación',
        index=True,
        help=(
            'Ejemplo: Tray 1, Fuser, ADF, Finisher.'
        ),
    )

    # ========================================================
    # SEVERIDAD
    # ========================================================

    severity = fields.Selection(
        [
            ('info', 'Información'),
            ('warning', 'Advertencia'),
            ('critical', 'Crítica'),
        ],
        string='Severidad',
        default='warning',
        required=True,
        tracking=True,
        index=True,
    )

    severity_rank = fields.Integer(
        string='Nivel severidad',
        compute='_compute_severity_rank',
        store=True,
        index=True,
    )

    # ========================================================
    # ESTADO / CICLO DE VIDA
    # ========================================================

    active = fields.Boolean(
        string='Activa',
        default=True,
        tracking=True,
        index=True,
    )

    state = fields.Selection(
        [
            ('open', 'Abierta'),
            ('acknowledged', 'Reconocida'),
            ('resolved', 'Resuelta'),
            ('ignored', 'Ignorada'),
        ],
        string='Estado',
        default='open',
        required=True,
        tracking=True,
        index=True,
    )

    first_seen = fields.Datetime(
        string='Primera detección',
        default=fields.Datetime.now,
        required=True,
        readonly=True,
        index=True,
    )

    last_seen = fields.Datetime(
        string='Última detección',
        default=fields.Datetime.now,
        required=True,
        readonly=True,
        index=True,
    )

    resolved_at = fields.Datetime(
        string='Fecha resolución',
        readonly=True,
        copy=False,
        index=True,
    )

    acknowledged_at = fields.Datetime(
        string='Fecha reconocimiento',
        readonly=True,
        copy=False,
    )

    acknowledged_by = fields.Many2one(
        'res.users',
        string='Reconocida por',
        readonly=True,
        copy=False,
    )

    occurrence_count = fields.Integer(
        string='Detecciones',
        default=1,
        readonly=True,
    )

    # ========================================================
    # DURACIÓN
    # ========================================================

    duration_seconds = fields.Float(
        string='Duración (seg)',
        compute='_compute_duration',
        store=True,
    )

    duration_minutes = fields.Float(
        string='Duración (min)',
        compute='_compute_duration',
        store=True,
    )

    duration_hours = fields.Float(
        string='Duración (h)',
        compute='_compute_duration',
        store=True,
    )

    # ========================================================
    # INFORMACIÓN SNMP
    # ========================================================

    oid = fields.Char(
        string='OID',
        index=True,
    )

    oid_name = fields.Char(
        string='OID nombre',
        index=True,
    )

    oid_index = fields.Char(
        string='Índice',
        index=True,
    )

    source_label = fields.Char(
        string='Etiqueta origen',
    )

    source_name = fields.Char(
        string='Origen',
    )

    snmp_type = fields.Char(
        string='Tipo SNMP',
    )

    # ========================================================
    # VALORES
    # ========================================================

    value_text = fields.Text(
        string='Valor',
    )

    raw_value = fields.Text(
        string='Valor RAW',
    )

    raw_json = fields.Text(
        string='RAW JSON',
    )

    # ========================================================
    # FABRICANTE / EQUIPO OBSERVADO
    # ========================================================

    manufacturer = fields.Char(
        string='Fabricante',
        readonly=True,
    )

    model = fields.Char(
        string='Modelo',
        readonly=True,
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

    # ========================================================
    # CONFIANZA
    # ========================================================

    confidence = fields.Selection(
        [
            ('unknown', 'Sin validar'),
            ('candidate', 'Candidato'),
            ('provisional', 'Provisional'),
            ('high', 'Alta'),
            ('very_high', 'Muy alta'),
        ],
        string='Confianza',
        default='unknown',
        index=True,
    )

    # ========================================================
    # CLASIFICACIÓN
    # ========================================================

    requires_service = fields.Boolean(
        string='Requiere servicio técnico',
        default=False,
        tracking=True,
    )

    prevents_printing = fields.Boolean(
        string='Impide imprimir',
        default=False,
    )

    prevents_copying = fields.Boolean(
        string='Impide copiar',
        default=False,
    )

    prevents_scanning = fields.Boolean(
        string='Impide escanear',
        default=False,
    )

    # ========================================================
    # REVISIÓN
    # ========================================================

    requires_review = fields.Boolean(
        string='Requiere revisión',
        default=False,
        index=True,
    )

    review_reason = fields.Char(
        string='Motivo revisión',
    )

    notes = fields.Text(
        string='Notas',
        tracking=True,
    )

    # ========================================================
    # COMPUTES
    # ========================================================

    @api.depends('severity')
    def _compute_severity_rank(self):
        ranking = {
            'info': 1,
            'warning': 2,
            'critical': 3,
        }

        for record in self:
            record.severity_rank = ranking.get(
                record.severity,
                0,
            )

    @api.depends(
        'first_seen',
        'last_seen',
        'resolved_at',
        'active',
    )
    def _compute_duration(self):
        for record in self:
            record.duration_seconds = 0.0
            record.duration_minutes = 0.0
            record.duration_hours = 0.0

            if not record.first_seen:
                continue

            end_date = (
                record.resolved_at
                if not record.active and record.resolved_at
                else record.last_seen
            )

            if not end_date:
                continue

            try:
                seconds = (
                    end_date - record.first_seen
                ).total_seconds()

                seconds = max(
                    seconds,
                    0.0,
                )

                record.duration_seconds = seconds
                record.duration_minutes = seconds / 60.0
                record.duration_hours = seconds / 3600.0

            except Exception:
                continue

    @api.depends(
        'name',
        'code',
        'device_id',
        'active',
        'severity',
    )
    def _compute_display_name(self):
        for record in self:
            parts = []

            if record.device_id:
                parts.append(
                    record.device_id.display_name
                )

            parts.append(
                record.name
                or record.code
                or record.key
                or _('Alerta')
            )

            if record.severity:
                parts.append(
                    dict(
                        self._fields[
                            'severity'
                        ].selection
                    ).get(
                        record.severity,
                        record.severity,
                    )
                )

            record.display_name = ' - '.join(
                parts
            )

    # ========================================================
    # SQL
    # ========================================================

    _sql_constraints = [
        (
            'sat_monitoring_alert_occurrence_positive',
            'CHECK(occurrence_count >= 0)',
            'La cantidad de detecciones no puede ser negativa.',
        ),
    ]

    # ========================================================
    # VALIDACIONES
    # ========================================================

    @api.constrains(
        'first_seen',
        'last_seen',
        'resolved_at',
    )
    def _check_dates(self):
        for record in self:
            if (
                record.first_seen
                and record.last_seen
                and record.last_seen < record.first_seen
            ):
                raise ValidationError(
                    _(
                        'La última detección no puede ser anterior '
                        'a la primera detección.'
                    )
                )

            if (
                record.first_seen
                and record.resolved_at
                and record.resolved_at < record.first_seen
            ):
                raise ValidationError(
                    _(
                        'La fecha de resolución no puede ser anterior '
                        'a la primera detección.'
                    )
                )

    # ========================================================
    # GENERAR CLAVE
    # ========================================================

    @api.model
    def build_alert_key(
        self,
        code=None,
        name=None,
        oid=None,
        location=None,
        source_label=None,
    ):
        """
        Genera una clave suficientemente estable para reconocer
        una misma alerta en snapshots consecutivos.

        Prioridad:
            código fabricante
            nombre
            OID
            ubicación
            etiqueta
        """
        parts = []

        for value in (
            code,
            name,
            oid,
            location,
            source_label,
        ):
            value = _clean_text(
                value
            ).lower()

            if value:
                parts.append(value)

        if not parts:
            return 'unknown_alert'

        result = '|'.join(
            parts
        )

        return result[:250]

    # ========================================================
    # CREAR / ACTUALIZAR ALERTA
    # ========================================================

    @api.model
    def register_alert(
        self,
        device,
        alert_data,
        snapshot=None,
        metric=None,
    ):
        """
        Registra una alerta detectada por el agente.

        Si ya existe activa para el mismo equipo/key:
            - NO crea duplicado
            - actualiza last_seen
            - incrementa occurrence_count
            - actualiza RAW y snapshot

        Si no existe:
            - crea una alerta nueva

        alert_data conceptual:

        {
            "key": "paper_jam_tray_2",
            "code": "...",
            "name": "Paper Jam",
            "description": "...",
            "severity": "warning",
            "category": "jam",
            "location": "Tray 2",
            "oid": "...",
            "value": "...",
            "raw_value": "...",
            "raw": {...}
        }
        """
        device.ensure_one()

        alert_data = alert_data or {}

        if snapshot:
            snapshot.ensure_one()

        if metric:
            metric.ensure_one()

        code = _clean_text(
            alert_data.get('code')
        )

        name = _clean_text(
            alert_data.get('name')
            or alert_data.get('description')
            or code
            or _('Alerta SNMP')
        )

        oid = _clean_text(
            alert_data.get('oid')
        )

        location = _clean_text(
            alert_data.get('location')
        )

        source_label = _clean_text(
            alert_data.get('source_label')
        )

        key = _clean_text(
            alert_data.get('key')
        )

        if not key:
            key = self.build_alert_key(
                code=code,
                name=name,
                oid=oid,
                location=location,
                source_label=source_label,
            )

        severity = _clean_text(
            alert_data.get('severity')
        ).lower()

        if severity not in (
            'info',
            'warning',
            'critical',
        ):
            severity = 'warning'

        category = _clean_text(
            alert_data.get('category')
        ).lower()

        allowed_categories = {
            'device',
            'paper',
            'toner',
            'consumable',
            'component',
            'cover',
            'jam',
            'service',
            'network',
            'storage',
            'temperature',
            'security',
            'supply',
            'offline',
            'other',
        }

        if category not in allowed_categories:
            category = 'other'

        now = (
            snapshot.date
            if snapshot and snapshot.date
            else fields.Datetime.now()
        )

        # ----------------------------------------------------
        # BUSCAR ALERTA ACTIVA
        # ----------------------------------------------------

        existing = self.search(
            [
                (
                    'device_id',
                    '=',
                    device.id,
                ),
                (
                    'key',
                    '=',
                    key,
                ),
                (
                    'active',
                    '=',
                    True,
                ),
            ],
            order='id desc',
            limit=1,
        )

        vals = {
            'device_id':
                device.id,

            'snapshot_id':
                snapshot.id
                if snapshot
                else False,

            'metric_id':
                metric.id
                if metric
                else False,

            'key':
                key,

            'code':
                code,

            'name':
                name,

            'description':
                _clean_text(
                    alert_data.get(
                        'description'
                    )
                ),

            'category':
                category,

            'group':
                _clean_text(
                    alert_data.get('group')
                ),

            'location':
                location,

            'severity':
                severity,

            'last_seen':
                now,

            'oid':
                oid,

            'oid_name':
                _clean_text(
                    alert_data.get(
                        'oid_name'
                    )
                ),

            'oid_index':
                _clean_text(
                    alert_data.get(
                        'index'
                    )
                    or alert_data.get(
                        'oid_index'
                    )
                ),

            'source_label':
                source_label,

            'source_name':
                _clean_text(
                    alert_data.get(
                        'source_name'
                    )
                ),

            'snmp_type':
                _clean_text(
                    alert_data.get(
                        'snmp_type'
                    )
                ),

            'value_text':
                _clean_text(
                    alert_data.get(
                        'value'
                    )
                ),

            'raw_value':
                _clean_text(
                    alert_data.get(
                        'raw_value'
                    )
                ),

            'raw_json':
                _json_dumps_safe(
                    alert_data
                ),

            'manufacturer':
                device.manufacturer_raw
                or '',

            'model':
                device.model
                or device.model_raw
                or '',

            'serial':
                device.serial
                or '',

            'firmware':
                device.firmware
                or '',

            'confidence':
                _clean_text(
                    alert_data.get(
                        'confidence'
                    )
                    or (
                        metric.confidence
                        if metric
                        else 'unknown'
                    )
                ),

            'requires_service':
                bool(
                    alert_data.get(
                        'requires_service'
                    )
                ),

            'prevents_printing':
                bool(
                    alert_data.get(
                        'prevents_printing'
                    )
                ),

            'prevents_copying':
                bool(
                    alert_data.get(
                        'prevents_copying'
                    )
                ),

            'prevents_scanning':
                bool(
                    alert_data.get(
                        'prevents_scanning'
                    )
                ),
        }

        if existing:
            vals[
                'occurrence_count'
            ] = (
                existing.occurrence_count
                + 1
            )

            # No reabrir automáticamente una alerta ignorada.
            if existing.state != 'ignored':
                vals['active'] = True

            existing.sudo().write(
                vals
            )

            return existing

        # ----------------------------------------------------
        # CREAR NUEVA
        # ----------------------------------------------------

        vals.update({
            'first_snapshot_id':
                snapshot.id
                if snapshot
                else False,

            'first_seen':
                now,

            'active':
                True,

            'state':
                'open',

            'occurrence_count':
                1,
        })

        return self.sudo().create(
            vals
        )

    # ========================================================
    # REGISTRO MASIVO
    # ========================================================

    @api.model
    def register_snapshot_alerts(
        self,
        snapshot,
        alerts,
    ):
        """
        Procesa todas las alertas enviadas en un snapshot.

        También cierra alertas que estaban activas pero dejaron
        de aparecer.

        IMPORTANTE:
        Solo cierra automáticamente alertas SNMP administradas
        mediante este método.
        """
        snapshot.ensure_one()

        device = snapshot.device_id

        alerts = alerts or []

        seen_keys = set()

        created_or_updated = self.browse()

        Metric = self.env[
            'sat.snmp.profile.metric'
        ]

        metrics_by_code = {}

        if snapshot.profile_id:
            metrics = Metric.search(
                [
                    (
                        'profile_id',
                        '=',
                        snapshot.profile_id.id,
                    ),
                    (
                        'active',
                        '=',
                        True,
                    ),
                ]
            )

            metrics_by_code = {
                metric.code:
                    metric
                for metric in metrics
            }

        for alert_data in alerts:
            if not isinstance(
                alert_data,
                dict,
            ):
                continue

            metric = False

            metric_code = _clean_text(
                alert_data.get(
                    'metric_code'
                )
            )

            if metric_code:
                metric = metrics_by_code.get(
                    metric_code
                )

            key = _clean_text(
                alert_data.get('key')
            )

            if not key:
                key = self.build_alert_key(
                    code=alert_data.get(
                        'code'
                    ),
                    name=alert_data.get(
                        'name'
                    )
                    or alert_data.get(
                        'description'
                    ),
                    oid=alert_data.get(
                        'oid'
                    ),
                    location=alert_data.get(
                        'location'
                    ),
                    source_label=alert_data.get(
                        'source_label'
                    ),
                )

                alert_data = dict(
                    alert_data
                )

                alert_data['key'] = key

            seen_keys.add(
                key
            )

            alert = self.register_alert(
                device=device,
                alert_data=alert_data,
                snapshot=snapshot,
                metric=metric,
            )

            created_or_updated |= alert

        # ----------------------------------------------------
        # CERRAR LAS QUE YA NO APARECEN
        # ----------------------------------------------------

        active_alerts = self.search(
            [
                (
                    'device_id',
                    '=',
                    device.id,
                ),
                (
                    'active',
                    '=',
                    True,
                ),
                (
                    'state',
                    '!=',
                    'ignored',
                ),
            ]
        )

        for alert in active_alerts:
            if alert.key in seen_keys:
                continue

            alert.resolve_alert(
                snapshot=snapshot,
                reason='not_present_in_latest_snapshot',
            )

        # ----------------------------------------------------
        # ACTUALIZAR RESUMEN DEL EQUIPO
        # ----------------------------------------------------

        self.update_device_alert_summary(
            device
        )

        snapshot.sudo().write({
            'alert_count':
                len(seen_keys),
        })

        return created_or_updated

    # ========================================================
    # CERRAR ALERTA
    # ========================================================

    def resolve_alert(
        self,
        snapshot=None,
        reason=None,
    ):
        """
        Cierra la alerta conservando todo el histórico.
        """
        now = (
            snapshot.date
            if snapshot and snapshot.date
            else fields.Datetime.now()
        )

        for record in self:
            vals = {
                'active':
                    False,

                'state':
                    'resolved',

                'resolved_at':
                    now,
            }

            if snapshot:
                vals[
                    'snapshot_id'
                ] = snapshot.id

            if reason:
                previous_notes = (
                    record.notes or ''
                )

                line = _(
                    'Resolución automática: %s'
                ) % _clean_text(reason)

                vals['notes'] = (
                    previous_notes
                    + '\n'
                    + line
                    if previous_notes
                    else line
                )

            record.sudo().write(
                vals
            )

        devices = self.mapped(
            'device_id'
        )

        for device in devices:
            self.update_device_alert_summary(
                device
            )

        return True

    # ========================================================
    # RECONOCER ALERTA
    # ========================================================

    def action_acknowledge(self):
        now = fields.Datetime.now()

        for record in self:
            if not record.active:
                continue

            record.write({
                'state':
                    'acknowledged',

                'acknowledged_at':
                    now,

                'acknowledged_by':
                    self.env.user.id,
            })

        return True

    # ========================================================
    # IGNORAR ALERTA
    # ========================================================

    def action_ignore(self):
        """
        Ignora administrativamente una alerta.

        No la elimina.

        Si vuelve a llegar desde el equipo, register_alert() la
        actualizará pero no la reabrirá automáticamente.
        """
        self.write({
            'state':
                'ignored',

            'active':
                False,

            'resolved_at':
                fields.Datetime.now(),
        })

        devices = self.mapped(
            'device_id'
        )

        for device in devices:
            self.update_device_alert_summary(
                device
            )

        return True

    # ========================================================
    # REABRIR
    # ========================================================

    def action_reopen(self):
        now = fields.Datetime.now()

        for record in self:
            record.write({
                'state':
                    'open',

                'active':
                    True,

                'resolved_at':
                    False,

                'last_seen':
                    now,
            })

        devices = self.mapped(
            'device_id'
        )

        for device in devices:
            self.update_device_alert_summary(
                device
            )

        return True

    # ========================================================
    # RESUMEN DE ALERTAS DEL EQUIPO
    # ========================================================

    @api.model
    def update_device_alert_summary(
        self,
        device,
    ):
        """
        Actualiza:

            active_alert_count
            highest_alert_severity

        dentro de sat.monitoring.device.
        """
        device.ensure_one()

        active_alerts = self.search(
            [
                (
                    'device_id',
                    '=',
                    device.id,
                ),
                (
                    'active',
                    '=',
                    True,
                ),
            ]
        )

        severity = 'none'

        if active_alerts.filtered(
            lambda alert:
                alert.severity
                == 'critical'
        ):
            severity = 'critical'

        elif active_alerts.filtered(
            lambda alert:
                alert.severity
                == 'warning'
        ):
            severity = 'warning'

        elif active_alerts:
            severity = 'info'

        device.sudo().apply_status(
            active_alert_count=len(
                active_alerts
            ),
            highest_severity=severity,
        )

        return True

    # ========================================================
    # OBTENER ACTIVAS
    # ========================================================

    @api.model
    def get_active_alerts(
        self,
        device,
    ):
        device.ensure_one()

        alerts = self.search(
            [
                (
                    'device_id',
                    '=',
                    device.id,
                ),
                (
                    'active',
                    '=',
                    True,
                ),
            ],
            order=(
                'severity_rank desc, '
                'first_seen desc, '
                'id desc'
            ),
        )

        result = []

        for alert in alerts:
            result.append({
                'id':
                    alert.id,

                'key':
                    alert.key,

                'code':
                    alert.code or '',

                'name':
                    alert.name,

                'description':
                    alert.description or '',

                'category':
                    alert.category,

                'severity':
                    alert.severity,

                'location':
                    alert.location or '',

                'first_seen':
                    fields.Datetime.to_string(
                        alert.first_seen
                    ),

                'last_seen':
                    fields.Datetime.to_string(
                        alert.last_seen
                    ),

                'occurrence_count':
                    alert.occurrence_count,

                'requires_service':
                    alert.requires_service,

                'prevents_printing':
                    alert.prevents_printing,

                'prevents_copying':
                    alert.prevents_copying,

                'prevents_scanning':
                    alert.prevents_scanning,

                'oid':
                    alert.oid or '',

                'value':
                    alert.value_text or '',
            })

        return result