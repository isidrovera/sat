# -*- coding: utf-8 -*-

import json
import logging
import math

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
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    except Exception:
        try:
            return str(value)
        except Exception:
            return ''


def _to_float_or_false(value):
    """
    Convierte valores numéricos sin convertir vacío a cero.

    Retorna False cuando no puede interpretarse.
    """
    if value is None or value is False:
        return False

    try:
        if isinstance(value, bool):
            return float(int(value))

        if isinstance(value, (int, float)):
            result = float(value)

            if math.isnan(result) or math.isinf(result):
                return False

            return result

        text = str(value).strip()

        if not text:
            return False

        result = float(
            text.replace(',', '')
        )

        if math.isnan(result) or math.isinf(result):
            return False

        return result

    except Exception:
        return False


def _to_bool_or_false(value):
    """
    Convierte valores comunes a booleano.

    False como resultado válido puede ser ambiguo, por eso se usa
    None internamente para "no interpretable".
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value).strip().lower()

    if text in (
        '1',
        'true',
        'yes',
        'y',
        'si',
        'sí',
        'on',
        'enabled',
        'present',
        'available',
        'supported',
    ):
        return True

    if text in (
        '0',
        'false',
        'no',
        'n',
        'off',
        'disabled',
        'absent',
        'unavailable',
        'unsupported',
    ):
        return False

    return None


# ============================================================
# LECTURA SNMP
# ============================================================

class SatMonitoringReading(models.Model):
    """
    Representa UNA métrica obtenida durante un snapshot.

    Ejemplos:

        machine_total = 183915
        toner_k = 80
        ocr_supported = True
        fuser_life = 64
        finisher_model = SR3260
        firmware_controller = 1.23
        tray_1_level = 75

    La misma tabla sirve para:
        - contadores
        - consumibles
        - componentes
        - bandejas
        - accesorios
        - capacidades
        - firmware
        - red
        - almacenamiento
        - memoria
        - estados
        - alertas detectadas por métrica
        - datos aún no clasificados
    """

    _name = 'sat.monitoring.reading'
    _description = 'Lectura SNMP de equipo'
    _order = 'snapshot_id desc, category, sequence, metric_code, id'
    _rec_name = 'display_name'

    # ========================================================
    # RELACIONES
    # ========================================================

    snapshot_id = fields.Many2one(
        'sat.monitoring.snapshot',
        string='Snapshot',
        required=True,
        ondelete='cascade',
        index=True,
    )

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

    metric_id = fields.Many2one(
        'sat.snmp.profile.metric',
        string='Métrica configurada',
        ondelete='set null',
        index=True,
    )

    profile_id = fields.Many2one(
        related='snapshot_id.profile_id',
        string='Perfil SNMP',
        store=True,
        readonly=True,
        index=True,
    )

    # ========================================================
    # FECHA
    # ========================================================

    date = fields.Datetime(
        string='Fecha lectura',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )

    # ========================================================
    # IDENTIDAD DE MÉTRICA
    # ========================================================

    metric_code = fields.Char(
        string='Código métrica',
        required=True,
        index=True,
        help=(
            'Código lógico estable.\n'
            'Ejemplos: machine_total, toner_k, ocr_supported.'
        ),
    )

    metric_name = fields.Char(
        string='Nombre métrica',
        required=True,
        index=True,
    )

    category = fields.Selection(
        [
            ('identity', 'Identidad'),
            ('counter', 'Contador'),
            ('consumable', 'Consumible'),
            ('component', 'Componente'),
            ('tray', 'Bandeja'),
            ('accessory', 'Accesorio'),
            ('capability', 'Capacidad'),
            ('status', 'Estado'),
            ('alert', 'Alerta'),
            ('firmware', 'Firmware'),
            ('network', 'Red'),
            ('storage', 'Almacenamiento'),
            ('memory', 'Memoria'),
            ('job', 'Trabajo'),
            ('system', 'Sistema'),
            ('other', 'Otro'),
        ],
        string='Categoría',
        required=True,
        default='other',
        index=True,
    )

    subgroup = fields.Char(
        string='Subgrupo',
        index=True,
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )

    required = fields.Boolean(
        string='Obligatoria',
        default=False,
        index=True,
    )

    # ========================================================
    # RESULTADO DE LA CONSULTA
    # ========================================================

    success = fields.Boolean(
        string='Lectura exitosa',
        default=True,
        index=True,
    )

    status = fields.Selection(
        [
            ('success', 'Correcto'),
            ('missing', 'No encontrado'),
            ('timeout', 'Timeout'),
            ('error', 'Error'),
            ('sentinel', 'Valor especial'),
            ('invalid', 'Valor inválido'),
            ('unsupported', 'No soportado'),
            ('skipped', 'Omitido'),
        ],
        string='Resultado',
        default='success',
        required=True,
        index=True,
    )

    error_code = fields.Char(
        string='Código error',
        index=True,
    )

    error_message = fields.Text(
        string='Error',
    )

    # ========================================================
    # TIPO DE DATO
    # ========================================================

    logical_type = fields.Selection(
        [
            ('integer', 'Entero'),
            ('float', 'Decimal'),
            ('string', 'Texto'),
            ('boolean', 'Booleano'),
            ('enum', 'Enumerado'),
            ('counter64', 'Counter64'),
            ('gauge', 'Gauge'),
            ('timeticks', 'TimeTicks'),
            ('octets', 'Octetos'),
            ('oid', 'OID'),
            ('bits', 'Bits / Flags'),
            ('raw', 'RAW'),
        ],
        string='Tipo lógico',
        required=True,
        default='string',
        index=True,
    )

    snmp_type = fields.Char(
        string='Tipo SNMP',
        help=(
            'Tipo real recibido del agente: Integer, Counter32, '
            'Counter64, Gauge32, OctetString, TimeTicks, etc.'
        ),
    )

    unit = fields.Char(
        string='Unidad',
        index=True,
    )

    # ========================================================
    # VALORES NORMALIZADOS
    # ========================================================

    value_numeric = fields.Float(
        string='Valor numérico',
        digits=(20, 6),
    )

    value_integer = fields.Integer(
        string='Valor entero',
    )

    value_text = fields.Text(
        string='Valor texto',
    )

    value_boolean = fields.Boolean(
        string='Valor booleano',
    )

    has_numeric_value = fields.Boolean(
        string='Tiene valor numérico',
        default=False,
        index=True,
    )

    has_integer_value = fields.Boolean(
        string='Tiene valor entero',
        default=False,
    )

    has_text_value = fields.Boolean(
        string='Tiene valor texto',
        default=False,
    )

    has_boolean_value = fields.Boolean(
        string='Tiene valor booleano',
        default=False,
    )

    # ========================================================
    # VALOR RAW
    # ========================================================

    raw_value_text = fields.Text(
        string='Valor RAW',
        help='Valor exactamente recibido desde SNMP/agente.',
    )

    raw_value_json = fields.Text(
        string='RAW JSON',
        help=(
            'Objeto completo recibido para esta métrica.'
        ),
    )

    # ========================================================
    # INFORMACIÓN OID
    # ========================================================

    oid = fields.Char(
        string='OID utilizado',
        index=True,
    )

    oid_name = fields.Char(
        string='OID nombre/label',
        index=True,
    )

    oid_index = fields.Char(
        string='Índice',
        index=True,
        help=(
            'Índice resuelto dinámicamente dentro de una tabla.'
        ),
    )

    source_label = fields.Char(
        string='Etiqueta origen',
        help=(
            'Texto encontrado en la tabla. '
            'Ejemplo: Counter:Print:Total.'
        ),
    )

    source_method = fields.Selection(
        [
            ('direct_oid', 'OID directo'),
            ('table_label_value', 'Tabla etiqueta / valor'),
            ('indexed_table', 'Tabla indexada'),
            ('walk_branch', 'WALK de rama'),
            ('presence', 'Detección presencia'),
            ('enum_value', 'Enumerado'),
            ('bit_flag', 'Bit / Flag'),
            ('derived', 'Derivada'),
            ('dynamic_discovery', 'Discovery dinámico'),
            ('unknown', 'Desconocido'),
        ],
        string='Método usado',
        default='unknown',
        index=True,
    )

    fallback_used = fields.Boolean(
        string='Se utilizó fallback',
        default=False,
    )

    discovered_dynamically = fields.Boolean(
        string='Descubierto dinámicamente',
        default=False,
        index=True,
    )

    # ========================================================
    # SENTINELAS
    # ========================================================

    is_sentinel = fields.Boolean(
        string='Valor especial',
        default=False,
        index=True,
    )

    sentinel_value = fields.Char(
        string='Sentinel',
    )

    sentinel_interpretation = fields.Selection(
        [
            ('unknown', 'Desconocido'),
            ('unavailable', 'No disponible'),
            ('empty', 'Vacío'),
            ('full', 'Lleno'),
            ('not_installed', 'No instalado'),
            ('not_supported', 'No soportado'),
            ('device_defined', 'Definido por fabricante'),
        ],
        string='Interpretación sentinel',
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
    # CAMBIO RESPECTO A LECTURA ANTERIOR
    # ========================================================

    previous_reading_id = fields.Many2one(
        'sat.monitoring.reading',
        string='Lectura anterior',
        ondelete='set null',
        readonly=True,
        index=True,
    )

    previous_numeric_value = fields.Float(
        string='Valor anterior',
        readonly=True,
        digits=(20, 6),
    )

    delta_numeric = fields.Float(
        string='Delta',
        readonly=True,
        digits=(20, 6),
    )

    changed = fields.Boolean(
        string='Cambió',
        default=False,
        readonly=True,
        index=True,
    )

    # ========================================================
    # FLAGS PARA ANÁLISIS
    # ========================================================

    anomaly = fields.Boolean(
        string='Anomalía',
        default=False,
        index=True,
    )

    anomaly_reason = fields.Char(
        string='Motivo anomalía',
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
    # ALMACENAMIENTO / HISTÓRICO
    # ========================================================

    history_mode = fields.Selection(
        [
            ('always', 'Cada lectura'),
            ('on_change', 'Solo cambio'),
            ('periodic', 'Periódico'),
            ('never', 'No histórico'),
        ],
        string='Política histórica',
        default='always',
    )

    # ========================================================
    # SQL
    # ========================================================

    _sql_constraints = [
        (
            'sat_monitoring_reading_snapshot_metric_unique',
            'unique(snapshot_id, metric_code)',
            'Ya existe una lectura con este código dentro del snapshot.',
        ),
    ]

    # ========================================================
    # DISPLAY NAME
    # ========================================================

    @api.depends(
        'metric_name',
        'value_text',
        'value_numeric',
        'has_numeric_value',
    )
    def _compute_display_name(self):
        for record in self:
            if record.has_numeric_value:
                value = record.value_numeric

                if record.unit:
                    value_display = '%s %s' % (
                        value,
                        record.unit,
                    )
                else:
                    value_display = str(value)

            elif record.has_text_value:
                value_display = (
                    record.value_text or ''
                )

            elif record.has_boolean_value:
                value_display = (
                    _('Sí')
                    if record.value_boolean
                    else _('No')
                )

            else:
                value_display = record.status or ''

            record.display_name = '%s: %s' % (
                record.metric_name or record.metric_code,
                value_display,
            )

    # ========================================================
    # CREATE
    # ========================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            snapshot_id = vals.get(
                'snapshot_id'
            )

            if snapshot_id and not vals.get(
                'device_id'
            ):
                snapshot = self.env[
                    'sat.monitoring.snapshot'
                ].browse(snapshot_id)

                vals['device_id'] = (
                    snapshot.device_id.id
                )

            metric_id = vals.get(
                'metric_id'
            )

            if metric_id:
                metric = self.env[
                    'sat.snmp.profile.metric'
                ].browse(metric_id)

                vals.setdefault(
                    'metric_code',
                    metric.code,
                )

                vals.setdefault(
                    'metric_name',
                    metric.name,
                )

                vals.setdefault(
                    'category',
                    metric.category,
                )

                vals.setdefault(
                    'subgroup',
                    metric.subgroup,
                )

                vals.setdefault(
                    'logical_type',
                    metric.logical_type,
                )

                vals.setdefault(
                    'unit',
                    metric.unit,
                )

                vals.setdefault(
                    'required',
                    metric.required,
                )

                vals.setdefault(
                    'sequence',
                    metric.sequence,
                )

                vals.setdefault(
                    'confidence',
                    metric.confidence,
                )

                vals.setdefault(
                    'history_mode',
                    metric.history_mode,
                )

        records = super().create(
            vals_list
        )

        records._link_previous_readings()

        return records

    # ========================================================
    # VALIDACIONES
    # ========================================================

    @api.constrains(
        'snapshot_id',
        'device_id',
    )
    def _check_device_snapshot(self):
        for record in self:
            if (
                record.snapshot_id
                and record.device_id
                and record.snapshot_id.device_id
                != record.device_id
            ):
                raise ValidationError(
                    _(
                        'La lectura pertenece a un equipo diferente '
                        'al equipo del snapshot.'
                    )
                )

    # ========================================================
    # BUSCAR LECTURA ANTERIOR
    # ========================================================

    def _link_previous_readings(self):
        """
        Busca la última lectura anterior de la misma métrica
        en el mismo equipo.

        Esto permite:
            - delta de contador
            - detectar cambio de tóner
            - detectar cambio de firmware
            - detectar instalación de accesorio
            - tendencias
        """
        for record in self:
            if not record.device_id:
                continue

            previous = self.search(
                [
                    (
                        'device_id',
                        '=',
                        record.device_id.id,
                    ),
                    (
                        'metric_code',
                        '=',
                        record.metric_code,
                    ),
                    (
                        'id',
                        '!=',
                        record.id,
                    ),
                    (
                        'date',
                        '<=',
                        record.date,
                    ),
                    (
                        'success',
                        '=',
                        True,
                    ),
                ],
                order='date desc, id desc',
                limit=1,
            )

            if not previous:
                continue

            vals = {
                'previous_reading_id':
                    previous.id,
            }

            # -----------------------------------------------
            # NUMÉRICO
            # -----------------------------------------------

            if (
                record.has_numeric_value
                and previous.has_numeric_value
            ):
                current = record.value_numeric
                old = previous.value_numeric

                vals[
                    'previous_numeric_value'
                ] = old

                vals[
                    'delta_numeric'
                ] = current - old

                vals['changed'] = (
                    current != old
                )

                # Contadores no deberían decrecer normalmente.
                if (
                    record.category == 'counter'
                    and current < old
                ):
                    vals.update({
                        'anomaly': True,
                        'anomaly_reason':
                            'counter_decreased',
                        'requires_review':
                            True,
                        'review_reason':
                            'counter_decreased',
                    })

            # -----------------------------------------------
            # BOOLEANO
            # -----------------------------------------------

            elif (
                record.has_boolean_value
                and previous.has_boolean_value
            ):
                vals['changed'] = (
                    record.value_boolean
                    != previous.value_boolean
                )

            # -----------------------------------------------
            # TEXTO
            # -----------------------------------------------

            elif (
                record.has_text_value
                and previous.has_text_value
            ):
                vals['changed'] = (
                    (record.value_text or '')
                    !=
                    (previous.value_text or '')
                )

            record.sudo().write(vals)

    # ========================================================
    # CREAR DESDE RESPUESTA DEL AGENTE
    # ========================================================

    @api.model
    def create_from_agent_result(
        self,
        snapshot,
        result,
        metric=None,
    ):
        """
        Método central para crear una lectura desde el resultado
        enviado por el agente.

        Ejemplo conceptual:

        {
            "code": "machine_total",
            "name": "Machine Total",
            "category": "counter",
            "success": true,
            "value": 183915,
            "raw_value": "183915",
            "oid": "...9.1",
            "oid_name": "...5.1",
            "index": "1",
            "source_label": "Counter: Machine Total",
            "snmp_type": "Integer"
        }
        """
        snapshot.ensure_one()

        result = result or {}

        if metric:
            metric.ensure_one()

        success = bool(
            result.get(
                'success',
                True,
            )
        )

        status = _clean_text(
            result.get(
                'status'
            )
        )

        if not status:
            status = (
                'success'
                if success
                else 'error'
            )

        allowed_status = {
            'success',
            'missing',
            'timeout',
            'error',
            'sentinel',
            'invalid',
            'unsupported',
            'skipped',
        }

        if status not in allowed_status:
            status = (
                'success'
                if success
                else 'error'
            )

        metric_code = _clean_text(
            result.get('code')
            or (
                metric.code
                if metric
                else ''
            )
        )

        metric_name = _clean_text(
            result.get('name')
            or (
                metric.name
                if metric
                else metric_code
            )
        )

        category = _clean_text(
            result.get('category')
            or (
                metric.category
                if metric
                else 'other'
            )
        )

        logical_type = _clean_text(
            result.get('logical_type')
            or (
                metric.logical_type
                if metric
                else 'string'
            )
        )

        vals = {
            'snapshot_id':
                snapshot.id,

            'device_id':
                snapshot.device_id.id,

            'metric_id':
                metric.id
                if metric
                else False,

            'date':
                snapshot.date
                or fields.Datetime.now(),

            'metric_code':
                metric_code,

            'metric_name':
                metric_name,

            'category':
                category,

            'subgroup':
                _clean_text(
                    result.get('subgroup')
                    or (
                        metric.subgroup
                        if metric
                        else ''
                    )
                ),

            'sequence':
                (
                    metric.sequence
                    if metric
                    else 10
                ),

            'required':
                (
                    metric.required
                    if metric
                    else bool(
                        result.get(
                            'required'
                        )
                    )
                ),

            'success':
                success,

            'status':
                status,

            'logical_type':
                logical_type,

            'snmp_type':
                _clean_text(
                    result.get(
                        'snmp_type'
                    )
                ),

            'unit':
                _clean_text(
                    result.get('unit')
                    or (
                        metric.unit
                        if metric
                        else ''
                    )
                ),

            'oid':
                _clean_text(
                    result.get('oid')
                ),

            'oid_name':
                _clean_text(
                    result.get('oid_name')
                ),

            'oid_index':
                _clean_text(
                    result.get('index')
                    or result.get('oid_index')
                ),

            'source_label':
                _clean_text(
                    result.get(
                        'source_label'
                    )
                ),

            'source_method':
                _clean_text(
                    result.get('method')
                    or (
                        metric.method
                        if metric
                        else 'unknown'
                    )
                ),

            'fallback_used':
                bool(
                    result.get(
                        'fallback_used'
                    )
                ),

            'discovered_dynamically':
                bool(
                    result.get(
                        'discovered_dynamically'
                    )
                ),

            'error_code':
                _clean_text(
                    result.get(
                        'error_code'
                    )
                ),

            'error_message':
                _clean_text(
                    result.get(
                        'error_message'
                    )
                ),

            'confidence':
                _clean_text(
                    result.get('confidence')
                    or (
                        metric.confidence
                        if metric
                        else 'unknown'
                    )
                ),

            'history_mode':
                (
                    metric.history_mode
                    if metric
                    else 'always'
                ),

            'raw_value_text':
                _clean_text(
                    result.get('raw_value')
                    if 'raw_value' in result
                    else result.get('value')
                ),

            'raw_value_json':
                _json_dumps_safe(
                    result
                ),
        }

        # ----------------------------------------------------
        # SENTINEL
        # ----------------------------------------------------

        if result.get('is_sentinel'):
            vals.update({
                'is_sentinel':
                    True,

                'status':
                    'sentinel',

                'sentinel_value':
                    _clean_text(
                        result.get(
                            'sentinel_value'
                        )
                        or result.get(
                            'value'
                        )
                    ),

                'sentinel_interpretation':
                    _clean_text(
                        result.get(
                            'sentinel_interpretation'
                        )
                    )
                    or 'unknown',
            })

        # ----------------------------------------------------
        # VALOR NORMALIZADO
        # ----------------------------------------------------

        value = result.get(
            'normalized_value'
        )

        if value is None:
            value = result.get(
                'value'
            )

        self._prepare_value_fields(
            vals,
            value,
            logical_type,
        )

        return self.create(vals)

    # ========================================================
    # PREPARAR VALORES
    # ========================================================

    @api.model
    def _prepare_value_fields(
        self,
        vals,
        value,
        logical_type,
    ):
        """
        Completa vals según el tipo lógico.

        Importante:
        Un booleano False sigue siendo un valor válido.
        Un contador 0 sigue siendo un valor válido.
        """

        # ----------------------------------------------------
        # ENTEROS
        # ----------------------------------------------------

        if logical_type in (
            'integer',
            'counter64',
            'gauge',
            'timeticks',
        ):
            numeric = _to_float_or_false(
                value
            )

            if numeric is not False:
                integer_value = int(
                    numeric
                )

                vals.update({
                    'value_numeric':
                        float(integer_value),

                    'value_integer':
                        integer_value,

                    'has_numeric_value':
                        True,

                    'has_integer_value':
                        True,
                })

            return

        # ----------------------------------------------------
        # FLOAT
        # ----------------------------------------------------

        if logical_type == 'float':
            numeric = _to_float_or_false(
                value
            )

            if numeric is not False:
                vals.update({
                    'value_numeric':
                        numeric,

                    'has_numeric_value':
                        True,
                })

            return

        # ----------------------------------------------------
        # BOOLEAN
        # ----------------------------------------------------

        if logical_type == 'boolean':
            boolean_value = (
                _to_bool_or_false(
                    value
                )
            )

            if boolean_value is not None:
                vals.update({
                    'value_boolean':
                        boolean_value,

                    'has_boolean_value':
                        True,
                })

            return

        # ----------------------------------------------------
        # ENUM
        # ----------------------------------------------------

        if logical_type == 'enum':
            if value is not None:
                vals.update({
                    'value_text':
                        _clean_text(value),

                    'has_text_value':
                        True,
                })

                numeric = _to_float_or_false(
                    value
                )

                if numeric is not False:
                    vals.update({
                        'value_numeric':
                            numeric,

                        'has_numeric_value':
                            True,
                    })

            return

        # ----------------------------------------------------
        # STRING / OID / OCTETS / BITS / RAW
        # ----------------------------------------------------

        if value is not None:
            vals.update({
                'value_text':
                    _clean_text(value),

                'has_text_value':
                    True,
            })

    # ========================================================
    # CREAR MÚLTIPLES DESDE AGENTE
    # ========================================================

    @api.model
    def create_batch_from_agent(
        self,
        snapshot,
        results,
    ):
        """
        Crea todas las lecturas enviadas por el agente.

        Cada resultado puede venir con metric_id o solamente code.
        """
        snapshot.ensure_one()

        results = results or []

        created = self.browse()

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
                ]
            )

            metrics_by_code = {
                metric.code: metric
                for metric in metrics
            }

        for result in results:
            if not isinstance(
                result,
                dict,
            ):
                continue

            metric = False

            metric_id = result.get(
                'metric_id'
            )

            if metric_id:
                metric = Metric.browse(
                    metric_id
                ).exists()

            if not metric:
                code = _clean_text(
                    result.get('code')
                )

                metric = (
                    metrics_by_code.get(
                        code
                    )
                    if code
                    else False
                )

            reading = (
                self.create_from_agent_result(
                    snapshot=snapshot,
                    result=result,
                    metric=metric,
                )
            )

            created |= reading

        snapshot.recalculate_statistics()

        return created

    # ========================================================
    # ACTUALIZAR ESTADO ACTUAL DEL DEVICE
    # ========================================================

    def update_device_current_values(self):
        """
        Convierte las lecturas exitosas del snapshot en el estado
        actual rápido de sat.monitoring.device.

        Solo las métricas conocidas por el modelo principal se
        copian allí.

        Todas las demás permanecen disponibles en readings.
        """
        devices = self.mapped(
            'device_id'
        )

        for device in devices:
            readings = self.filtered(
                lambda reading:
                    reading.device_id == device
                    and reading.success
            )

            metrics = {}

            for reading in readings:
                if reading.is_sentinel:
                    continue

                if reading.has_boolean_value:
                    value = (
                        reading.value_boolean
                    )

                elif reading.has_integer_value:
                    value = (
                        reading.value_integer
                    )

                elif reading.has_numeric_value:
                    value = (
                        reading.value_numeric
                    )

                elif reading.has_text_value:
                    value = (
                        reading.value_text
                    )

                else:
                    continue

                metrics[
                    reading.metric_code
                ] = value

            if metrics:
                device.apply_current_metrics(
                    metrics
                )

        return True

    # ========================================================
    # OBTENER VALOR NORMALIZADO
    # ========================================================

    def get_normalized_value(self):
        self.ensure_one()

        if not self.success:
            return None

        if self.is_sentinel:
            return None

        if self.has_boolean_value:
            return self.value_boolean

        if self.has_integer_value:
            return self.value_integer

        if self.has_numeric_value:
            return self.value_numeric

        if self.has_text_value:
            return self.value_text

        return None

    # ========================================================
    # HISTÓRICO DE UNA MÉTRICA
    # ========================================================

    @api.model
    def get_metric_history(
        self,
        device,
        metric_code,
        limit=100,
    ):
        """
        Devuelve historial ordenado de una métrica.

        Será útil después para:
            gráficas
            tendencias
            producción
            consumo de tóner
            predicciones
        """
        device.ensure_one()

        try:
            limit = max(
                min(
                    int(limit),
                    10000,
                ),
                1,
            )
        except Exception:
            limit = 100

        readings = self.search(
            [
                (
                    'device_id',
                    '=',
                    device.id,
                ),
                (
                    'metric_code',
                    '=',
                    metric_code,
                ),
                (
                    'success',
                    '=',
                    True,
                ),
            ],
            order='date desc, id desc',
            limit=limit,
        )

        result = []

        for reading in readings:
            result.append({
                'id':
                    reading.id,

                'date':
                    fields.Datetime.to_string(
                        reading.date
                    ),

                'value':
                    reading.get_normalized_value(),

                'unit':
                    reading.unit or '',

                'oid':
                    reading.oid or '',

                'delta':
                    (
                        reading.delta_numeric
                        if reading.has_numeric_value
                        else None
                    ),

                'changed':
                    reading.changed,

                'anomaly':
                    reading.anomaly,

                'confidence':
                    reading.confidence,
            })

        return result