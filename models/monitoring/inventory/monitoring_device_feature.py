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


def _to_float(value):
    if value in (None, False, ''):
        return None

    try:
        return float(value)
    except Exception:
        return None


def _to_int(value):
    if value in (None, False, ''):
        return None

    try:
        return int(float(value))
    except Exception:
        return None


def _to_bool(value):
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
        'installed',
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
        'not_installed',
        'unavailable',
        'unsupported',
    ):
        return False

    return None


# ============================================================
# FEATURE / INVENTARIO DINÁMICO
# ============================================================

class SatMonitoringDeviceFeature(models.Model):
    """
    Inventario dinámico actual de una impresora/MFP.

    Representa características estructurales o semi-estables:

        - capacidades
        - accesorios
        - opciones
        - componentes
        - bandejas
        - almacenamiento
        - memoria
        - lenguajes de impresión
        - funciones de escaneo
        - interfaces de red
        - software/opciones
        - firmware específico
        - cualquier característica futura

    Ejemplos:

        ocr_supported = True
        searchable_pdf_supported = True
        pcl6_supported = True
        postscript3_supported = True

        finisher = SR3210
        adf = SPDF
        punch_unit = PU3070

        hdd_capacity = 320 GB
        ram = 2048 MB

        fuser_life = 74 %
        drum_k_life = 82 %

        tray_1_size = A4
        tray_1_capacity = 550 sheets

    Este modelo representa principalmente el ESTADO ACTUAL.

    El historial completo sigue estando disponible mediante:

        sat.monitoring.snapshot
        sat.monitoring.reading

    Nunca se borra automáticamente una característica que desaparece;
    se marca como no presente/inactiva y se conserva cuándo fue vista.
    """

    _name = 'sat.monitoring.device.feature'
    _description = 'Característica de equipo monitoreado'
    _order = (
        'device_id, '
        'category, '
        'sequence, '
        'name, '
        'id'
    )
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

    marca_id = fields.Many2one(
        related='device_id.marca_id',
        string='Marca',
        store=True,
        readonly=True,
        index=True,
    )

    agent_id = fields.Many2one(
        related='device_id.agent_id',
        string='Agente',
        store=True,
        readonly=True,
        index=True,
    )

    network_id = fields.Many2one(
        related='device_id.network_id',
        string='Red',
        store=True,
        readonly=True,
        index=True,
    )

    # ========================================================
    # ORIGEN
    # ========================================================

    profile_id = fields.Many2one(
        'sat.snmp.profile',
        string='Perfil SNMP',
        ondelete='set null',
        index=True,
        readonly=True,
    )

    metric_id = fields.Many2one(
        'sat.snmp.profile.metric',
        string='Métrica origen',
        ondelete='set null',
        index=True,
        readonly=True,
    )

    snapshot_id = fields.Many2one(
        'sat.monitoring.snapshot',
        string='Último snapshot',
        ondelete='set null',
        index=True,
        readonly=True,
    )

    first_snapshot_id = fields.Many2one(
        'sat.monitoring.snapshot',
        string='Primer snapshot',
        ondelete='set null',
        index=True,
        readonly=True,
    )

    reading_id = fields.Many2one(
        'sat.monitoring.reading',
        string='Última lectura',
        ondelete='set null',
        index=True,
        readonly=True,
    )

    # ========================================================
    # IDENTIFICACIÓN
    # ========================================================

    code = fields.Char(
        string='Código técnico',
        required=True,
        index=True,
        help=(
            'Código estable de la característica.\n\n'
            'Ejemplos:\n'
            'ocr_supported\n'
            'finisher\n'
            'tray_1_size\n'
            'fuser_life\n'
            'postscript3_supported'
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

    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )

    # ========================================================
    # CATEGORÍA
    # ========================================================

    category = fields.Selection(
        [
            ('capability', 'Capacidad'),
            ('accessory', 'Accesorio'),
            ('component', 'Componente'),
            ('tray', 'Bandeja'),
            ('storage', 'Almacenamiento'),
            ('memory', 'Memoria'),
            ('language', 'Lenguaje de impresión'),
            ('scanner', 'Escáner'),
            ('fax', 'Fax'),
            ('network', 'Red / conectividad'),
            ('software', 'Software / opción'),
            ('firmware', 'Firmware'),
            ('security', 'Seguridad'),
            ('finishing', 'Acabado'),
            ('paper', 'Papel'),
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
        help=(
            'Ejemplos: OCR, finishing, paper_input, drum, '
            'fuser, network_protocol.'
        ),
    )

    feature_type = fields.Selection(
        [
            ('boolean', 'Sí / No'),
            ('integer', 'Entero'),
            ('float', 'Decimal'),
            ('text', 'Texto'),
            ('enum', 'Enumerado'),
            ('percent', 'Porcentaje'),
            ('capacity', 'Capacidad'),
            ('counter', 'Contador'),
            ('version', 'Versión'),
            ('model', 'Modelo'),
            ('status', 'Estado'),
            ('raw', 'RAW'),
        ],
        string='Tipo',
        required=True,
        default='text',
        index=True,
    )

    # ========================================================
    # PRESENCIA
    # ========================================================

    present = fields.Boolean(
        string='Presente',
        default=True,
        index=True,
        help=(
            'Indica que el accesorio/capacidad/componente '
            'está presente actualmente.'
        ),
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
        index=True,
        help=(
            'Registro vigente dentro del inventario actual.'
        ),
    )

    installed = fields.Boolean(
        string='Instalado',
        default=True,
        index=True,
        help=(
            'Se utiliza especialmente para accesorios y opciones.'
        ),
    )

    supported = fields.Boolean(
        string='Soportado',
        default=True,
        index=True,
        help=(
            'Se utiliza especialmente para capacidades funcionales.'
        ),
    )

    # ========================================================
    # VALORES NORMALIZADOS
    # ========================================================

    value_boolean = fields.Boolean(
        string='Valor Sí/No',
    )

    value_integer = fields.Integer(
        string='Valor entero',
    )

    value_numeric = fields.Float(
        string='Valor numérico',
        digits=(20, 6),
    )

    value_text = fields.Text(
        string='Valor texto',
    )

    has_boolean_value = fields.Boolean(
        string='Tiene booleano',
        default=False,
    )

    has_integer_value = fields.Boolean(
        string='Tiene entero',
        default=False,
    )

    has_numeric_value = fields.Boolean(
        string='Tiene numérico',
        default=False,
    )

    has_text_value = fields.Boolean(
        string='Tiene texto',
        default=False,
    )

    unit = fields.Char(
        string='Unidad',
        index=True,
        help=(
            'Ejemplos: percent, MB, GB, sheets, dpi, ppm.'
        ),
    )

    # ========================================================
    # DATOS ADICIONALES DE HARDWARE
    # ========================================================

    manufacturer = fields.Char(
        string='Fabricante accesorio/componente',
    )

    model = fields.Char(
        string='Modelo accesorio/componente',
        index=True,
    )

    serial = fields.Char(
        string='Serie accesorio/componente',
        index=True,
    )

    version = fields.Char(
        string='Versión',
    )

    capacity = fields.Float(
        string='Capacidad',
        digits=(20, 6),
    )

    capacity_unit = fields.Char(
        string='Unidad capacidad',
    )

    life_percent = fields.Float(
        string='Vida (%)',
        digits=(5, 2),
    )

    # ========================================================
    # BANDEJAS
    # ========================================================

    tray_index = fields.Char(
        string='Índice bandeja',
        index=True,
    )

    tray_name = fields.Char(
        string='Nombre bandeja',
    )

    paper_size = fields.Char(
        string='Tamaño papel',
        index=True,
    )

    paper_type = fields.Char(
        string='Tipo papel',
    )

    paper_level = fields.Float(
        string='Nivel papel',
        digits=(10, 2),
    )

    paper_level_unit = fields.Char(
        string='Unidad nivel',
    )

    max_capacity = fields.Float(
        string='Capacidad máxima',
        digits=(20, 2),
    )

    # ========================================================
    # COMPONENTES
    # ========================================================

    component_index = fields.Char(
        string='Índice componente',
        index=True,
    )

    component_color = fields.Selection(
        [
            ('black', 'Negro'),
            ('cyan', 'Cyan'),
            ('magenta', 'Magenta'),
            ('yellow', 'Amarillo'),
            ('none', 'Sin color'),
            ('unknown', 'Desconocido'),
        ],
        string='Color componente',
        default='none',
        index=True,
    )

    component_status = fields.Char(
        string='Estado componente',
    )

    # ========================================================
    # OID / ORIGEN TÉCNICO
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
        string='Índice OID',
        index=True,
    )

    source_label = fields.Char(
        string='Etiqueta origen',
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
            ('manual', 'Manual'),
            ('unknown', 'Desconocido'),
        ],
        string='Método origen',
        default='unknown',
        index=True,
    )

    discovered_dynamically = fields.Boolean(
        string='Descubierto dinámicamente',
        default=False,
        index=True,
    )

    # ========================================================
    # RAW
    # ========================================================

    raw_value = fields.Text(
        string='Valor RAW',
    )

    raw_json = fields.Text(
        string='RAW JSON',
    )

    # ========================================================
    # TIEMPOS
    # ========================================================

    first_seen = fields.Datetime(
        string='Primera detección',
        required=True,
        default=fields.Datetime.now,
        readonly=True,
        index=True,
    )

    last_seen = fields.Datetime(
        string='Última confirmación',
        required=True,
        default=fields.Datetime.now,
        readonly=True,
        index=True,
    )

    removed_at = fields.Datetime(
        string='Retirado / desaparecido',
        readonly=True,
        copy=False,
        index=True,
    )

    last_changed_at = fields.Datetime(
        string='Último cambio',
        readonly=True,
        copy=False,
    )

    observation_count = fields.Integer(
        string='Observaciones',
        default=1,
        readonly=True,
    )

    # ========================================================
    # CAMBIO
    # ========================================================

    changed = fields.Boolean(
        string='Cambió recientemente',
        default=False,
        readonly=True,
        index=True,
    )

    previous_value_text = fields.Text(
        string='Valor anterior',
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

    # ========================================================
    # NOTAS
    # ========================================================

    notes = fields.Text(
        string='Notas',
    )

    # ========================================================
    # SQL
    # ========================================================

    _sql_constraints = [
        (
            'sat_monitoring_device_feature_unique',
            'unique(device_id, code)',
            'Ya existe esta característica para el equipo.',
        ),
        (
            'sat_monitoring_device_feature_observation_positive',
            'CHECK(observation_count >= 0)',
            'Las observaciones no pueden ser negativas.',
        ),
        (
            'sat_monitoring_device_feature_life_range',
            'CHECK(life_percent >= 0 AND life_percent <= 100)',
            'La vida útil debe estar entre 0 y 100.',
        ),
    ]

    # ========================================================
    # DISPLAY NAME
    # ========================================================

    @api.depends(
        'device_id',
        'name',
        'present',
        'value_text',
        'value_numeric',
        'value_integer',
        'value_boolean',
        'has_text_value',
        'has_numeric_value',
        'has_integer_value',
        'has_boolean_value',
        'unit',
    )
    def _compute_display_name(self):
        for record in self:
            value_display = ''

            if record.has_boolean_value:
                value_display = (
                    _('Sí')
                    if record.value_boolean
                    else _('No')
                )

            elif record.has_integer_value:
                value_display = str(
                    record.value_integer
                )

            elif record.has_numeric_value:
                value_display = str(
                    record.value_numeric
                )

            elif record.has_text_value:
                value_display = (
                    record.value_text or ''
                )

            if value_display and record.unit:
                value_display = '%s %s' % (
                    value_display,
                    record.unit,
                )

            if not record.present:
                state = _('No presente')
            else:
                state = value_display or _('Presente')

            record.display_name = '%s - %s: %s' % (
                record.device_id.display_name
                if record.device_id
                else _('Equipo'),
                record.name or record.code,
                state,
            )

    # ========================================================
    # VALIDACIONES
    # ========================================================

    @api.constrains('life_percent')
    def _check_life_percent(self):
        for record in self:
            if (
                record.life_percent < 0
                or record.life_percent > 100
            ):
                raise ValidationError(
                    _(
                        'La vida útil debe estar '
                        'entre 0 y 100.'
                    )
                )

    @api.constrains(
        'metric_id',
        'profile_id',
    )
    def _check_metric_profile(self):
        for record in self:
            if not (
                record.metric_id
                and record.profile_id
            ):
                continue

            if (
                record.metric_id.profile_id
                != record.profile_id
            ):
                raise ValidationError(
                    _(
                        'La métrica seleccionada no pertenece '
                        'al perfil SNMP indicado.'
                    )
                )

    # ========================================================
    # VALOR ACTUAL
    # ========================================================

    def get_normalized_value(self):
        self.ensure_one()

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
    # REPRESENTACIÓN TEXTO
    # ========================================================

    def _normalized_value_as_text(self):
        self.ensure_one()

        value = self.get_normalized_value()

        if value is None:
            return ''

        return str(value)

    # ========================================================
    # PREPARAR VALOR
    # ========================================================

    @api.model
    def _prepare_value_fields(
        self,
        values,
        feature_type,
        value,
    ):
        """
        Limpia todos los flags y guarda el valor según su tipo.
        """

        values.update({
            'has_boolean_value':
                False,

            'has_integer_value':
                False,

            'has_numeric_value':
                False,

            'has_text_value':
                False,

            'value_boolean':
                False,

            'value_integer':
                0,

            'value_numeric':
                0.0,

            'value_text':
                False,
        })

        if value is None:
            return

        # ----------------------------------------------------
        # BOOLEAN
        # ----------------------------------------------------

        if feature_type == 'boolean':
            boolean_value = _to_bool(
                value
            )

            if boolean_value is not None:
                values.update({
                    'value_boolean':
                        boolean_value,

                    'has_boolean_value':
                        True,
                })

            return

        # ----------------------------------------------------
        # INTEGER / COUNTER
        # ----------------------------------------------------

        if feature_type in (
            'integer',
            'counter',
        ):
            integer_value = _to_int(
                value
            )

            if integer_value is not None:
                values.update({
                    'value_integer':
                        integer_value,

                    'value_numeric':
                        float(
                            integer_value
                        ),

                    'has_integer_value':
                        True,

                    'has_numeric_value':
                        True,
                })

            return

        # ----------------------------------------------------
        # NUMERIC
        # ----------------------------------------------------

        if feature_type in (
            'float',
            'percent',
            'capacity',
        ):
            numeric_value = _to_float(
                value
            )

            if numeric_value is not None:
                values.update({
                    'value_numeric':
                        numeric_value,

                    'has_numeric_value':
                        True,
                })

            return

        # ----------------------------------------------------
        # TEXTUAL
        # ----------------------------------------------------

        text_value = _clean_text(
            value
        )

        if text_value:
            values.update({
                'value_text':
                    text_value,

                'has_text_value':
                    True,
            })

    # ========================================================
    # CREAR / ACTUALIZAR DESDE LECTURA
    # ========================================================

    @api.model
    def update_from_reading(
        self,
        reading,
        feature_data=None,
    ):
        """
        Crea o actualiza una característica a partir de
        sat.monitoring.reading.

        feature_data permite complementar datos específicos.

        Ejemplo:

        {
            "feature_type": "boolean",
            "present": true,
            "installed": true,
            "supported": true,
            "model": "SR3210",
            "capacity": 550,
            "capacity_unit": "sheets"
        }
        """
        reading.ensure_one()

        feature_data = feature_data or {}

        device = reading.device_id

        if not device:
            return self.browse()

        code = _clean_text(
            feature_data.get(
                'code'
            )
            or reading.metric_code
        )

        if not code:
            return self.browse()

        feature_type = _clean_text(
            feature_data.get(
                'feature_type'
            )
        )

        if not feature_type:
            logical_map = {
                'boolean':
                    'boolean',

                'integer':
                    'integer',

                'counter64':
                    'counter',

                'gauge':
                    'float',

                'float':
                    'float',

                'enum':
                    'enum',

                'string':
                    'text',

                'octets':
                    'raw',

                'oid':
                    'text',

                'bits':
                    'raw',

                'raw':
                    'raw',
            }

            feature_type = (
                logical_map.get(
                    reading.logical_type,
                    'text',
                )
            )

        category = _clean_text(
            feature_data.get(
                'category'
            )
            or reading.category
        )

        allowed_categories = {
            'capability',
            'accessory',
            'component',
            'tray',
            'storage',
            'memory',
            'language',
            'scanner',
            'fax',
            'network',
            'software',
            'firmware',
            'security',
            'finishing',
            'paper',
            'system',
            'other',
        }

        if category not in allowed_categories:
            if reading.category == 'capability':
                category = 'capability'

            elif reading.category == 'accessory':
                category = 'accessory'

            elif reading.category == 'component':
                category = 'component'

            elif reading.category == 'tray':
                category = 'tray'

            elif reading.category == 'storage':
                category = 'storage'

            elif reading.category == 'memory':
                category = 'memory'

            elif reading.category == 'firmware':
                category = 'firmware'

            elif reading.category == 'network':
                category = 'network'

            else:
                category = 'other'

        value = reading.get_normalized_value()

        if 'value' in feature_data:
            value = feature_data.get(
                'value'
            )

        present = feature_data.get(
            'present'
        )

        if present is None:
            if reading.success:
                if (
                    feature_type
                    == 'boolean'
                ):
                    boolean_value = _to_bool(
                        value
                    )

                    present = (
                        boolean_value
                        if boolean_value
                        is not None
                        else True
                    )
                else:
                    present = True

            else:
                present = False

        supported = feature_data.get(
            'supported'
        )

        if supported is None:
            supported = bool(
                present
            )

        installed = feature_data.get(
            'installed'
        )

        if installed is None:
            installed = bool(
                present
            )

        now = (
            reading.date
            or fields.Datetime.now()
        )

        existing = self.search(
            [
                (
                    'device_id',
                    '=',
                    device.id,
                ),
                (
                    'code',
                    '=',
                    code,
                ),
            ],
            limit=1,
        )

        profile = (
            reading.profile_id
            or (
                reading.metric_id.profile_id
                if reading.metric_id
                else False
            )
        )

        vals = {
            'device_id':
                device.id,

            'profile_id':
                profile.id
                if profile
                else False,

            'metric_id':
                reading.metric_id.id
                if reading.metric_id
                else False,

            'snapshot_id':
                reading.snapshot_id.id,

            'reading_id':
                reading.id,

            'code':
                code,

            'name':
                _clean_text(
                    feature_data.get(
                        'name'
                    )
                    or reading.metric_name
                    or code
                ),

            'description':
                _clean_text(
                    feature_data.get(
                        'description'
                    )
                ),

            'category':
                category,

            'subgroup':
                _clean_text(
                    feature_data.get(
                        'subgroup'
                    )
                    or reading.subgroup
                ),

            'feature_type':
                feature_type,

            'present':
                bool(
                    present
                ),

            'active':
                bool(
                    present
                ),

            'installed':
                bool(
                    installed
                ),

            'supported':
                bool(
                    supported
                ),

            'unit':
                _clean_text(
                    feature_data.get(
                        'unit'
                    )
                    or reading.unit
                ),

            'manufacturer':
                _clean_text(
                    feature_data.get(
                        'manufacturer'
                    )
                ),

            'model':
                _clean_text(
                    feature_data.get(
                        'model'
                    )
                ),

            'serial':
                _clean_text(
                    feature_data.get(
                        'serial'
                    )
                ),

            'version':
                _clean_text(
                    feature_data.get(
                        'version'
                    )
                ),

            'oid':
                reading.oid or '',

            'oid_name':
                reading.oid_name or '',

            'oid_index':
                reading.oid_index or '',

            'source_label':
                reading.source_label or '',

            'source_method':
                reading.source_method
                or 'unknown',

            'discovered_dynamically':
                reading.discovered_dynamically,

            'raw_value':
                reading.raw_value_text or '',

            'raw_json':
                reading.raw_value_json or '',

            'last_seen':
                now,

            'confidence':
                reading.confidence,

            'removed_at':
                False
                if present
                else (
                    existing.removed_at
                    if existing
                    else now
                ),
        }

        # ----------------------------------------------------
        # CAPACIDAD / VIDA
        # ----------------------------------------------------

        capacity = _to_float(
            feature_data.get(
                'capacity'
            )
        )

        if capacity is not None:
            vals['capacity'] = capacity

        if feature_data.get(
            'capacity_unit'
        ):
            vals[
                'capacity_unit'
            ] = _clean_text(
                feature_data.get(
                    'capacity_unit'
                )
            )

        life_percent = _to_float(
            feature_data.get(
                'life_percent'
            )
        )

        if life_percent is not None:
            vals[
                'life_percent'
            ] = max(
                min(
                    life_percent,
                    100.0,
                ),
                0.0,
            )

        # ----------------------------------------------------
        # BANDEJA
        # ----------------------------------------------------

        vals.update({
            'tray_index':
                _clean_text(
                    feature_data.get(
                        'tray_index'
                    )
                ),

            'tray_name':
                _clean_text(
                    feature_data.get(
                        'tray_name'
                    )
                ),

            'paper_size':
                _clean_text(
                    feature_data.get(
                        'paper_size'
                    )
                ),

            'paper_type':
                _clean_text(
                    feature_data.get(
                        'paper_type'
                    )
                ),

            'paper_level_unit':
                _clean_text(
                    feature_data.get(
                        'paper_level_unit'
                    )
                ),

            'component_index':
                _clean_text(
                    feature_data.get(
                        'component_index'
                    )
                ),

            'component_status':
                _clean_text(
                    feature_data.get(
                        'component_status'
                    )
                ),
        })

        paper_level = _to_float(
            feature_data.get(
                'paper_level'
            )
        )

        if paper_level is not None:
            vals['paper_level'] = (
                paper_level
            )

        max_capacity = _to_float(
            feature_data.get(
                'max_capacity'
            )
        )

        if max_capacity is not None:
            vals['max_capacity'] = (
                max_capacity
            )

        component_color = _clean_text(
            feature_data.get(
                'component_color'
            )
        ).lower()

        if component_color in (
            'black',
            'cyan',
            'magenta',
            'yellow',
            'none',
            'unknown',
        ):
            vals[
                'component_color'
            ] = component_color

        # ----------------------------------------------------
        # VALOR NORMALIZADO
        # ----------------------------------------------------

        self._prepare_value_fields(
            vals,
            feature_type,
            value,
        )

        # ----------------------------------------------------
        # CREAR
        # ----------------------------------------------------

        if not existing:
            vals.update({
                'first_snapshot_id':
                    reading.snapshot_id.id,

                'first_seen':
                    now,

                'observation_count':
                    1,

                'changed':
                    False,

                'last_changed_at':
                    now,
            })

            return self.create(
                vals
            )

        # ----------------------------------------------------
        # DETECTAR CAMBIO
        # ----------------------------------------------------

        old_value = (
            existing._normalized_value_as_text()
        )

        old_present = (
            existing.present
        )

        new_value_temp = {}

        self._prepare_value_fields(
            new_value_temp,
            feature_type,
            value,
        )

        if new_value_temp.get(
            'has_boolean_value'
        ):
            new_value = str(
                new_value_temp.get(
                    'value_boolean'
                )
            )

        elif new_value_temp.get(
            'has_integer_value'
        ):
            new_value = str(
                new_value_temp.get(
                    'value_integer'
                )
            )

        elif new_value_temp.get(
            'has_numeric_value'
        ):
            new_value = str(
                new_value_temp.get(
                    'value_numeric'
                )
            )

        elif new_value_temp.get(
            'has_text_value'
        ):
            new_value = (
                new_value_temp.get(
                    'value_text'
                )
                or ''
            )

        else:
            new_value = ''

        changed = (
            old_value != new_value
            or old_present != bool(
                present
            )
        )

        vals.update({
            'observation_count':
                existing.observation_count
                + 1,

            'changed':
                changed,
        })

        if changed:
            vals.update({
                'previous_value_text':
                    old_value,

                'last_changed_at':
                    now,
            })

        # ----------------------------------------------------
        # REMOCIÓN
        # ----------------------------------------------------

        if (
            old_present
            and not present
        ):
            vals[
                'removed_at'
            ] = now

        elif present:
            vals[
                'removed_at'
            ] = False

        existing.sudo().write(
            vals
        )

        return existing

    # ========================================================
    # PROCESAR SNAPSHOT COMPLETO
    # ========================================================

    @api.model
    def update_from_snapshot(
        self,
        snapshot,
        categories=None,
        complete_inventory=False,
    ):
        """
        Actualiza inventario a partir de las readings del snapshot.

        categories permite limitar qué tipos deben tratarse como
        inventario.

        complete_inventory=True significa:

            "este snapshot representa una exploración completa
             del inventario actual"

        En ese caso, las características que existían antes y
        no aparecieron pueden marcarse como no presentes.

        NO usar complete_inventory=True en polling parcial.
        """
        snapshot.ensure_one()

        if categories is None:
            categories = {
                'capability',
                'accessory',
                'component',
                'tray',
                'storage',
                'memory',
                'firmware',
                'network',
            }

        else:
            categories = set(
                categories
            )

        readings = snapshot.reading_ids.filtered(
            lambda reading:
                reading.success
                and reading.category
                in categories
        )

        seen_codes = set()

        updated = self.browse()

        for reading in readings:
            feature = self.update_from_reading(
                reading=reading,
            )

            if feature:
                updated |= feature

                seen_codes.add(
                    feature.code
                )

        # ----------------------------------------------------
        # INVENTARIO COMPLETO
        # ----------------------------------------------------

        if complete_inventory:
            current_features = self.search(
                [
                    (
                        'device_id',
                        '=',
                        snapshot.device_id.id,
                    ),
                    (
                        'active',
                        '=',
                        True,
                    ),
                    (
                        'category',
                        'in',
                        list(categories),
                    ),
                ]
            )

            now = (
                snapshot.date
                or fields.Datetime.now()
            )

            for feature in current_features:
                if feature.code in seen_codes:
                    continue

                feature.sudo().write({
                    'present':
                        False,

                    'installed':
                        False,

                    'active':
                        False,

                    'removed_at':
                        now,

                    'last_changed_at':
                        now,

                    'changed':
                        True,

                    'snapshot_id':
                        snapshot.id,

                    'previous_value_text':
                        feature._normalized_value_as_text(),
                })

        snapshot.device_id.recalculate_feature_summary()

        return updated

    # ========================================================
    # REGISTRAR FEATURE DESDE PAYLOAD DIRECTO
    # ========================================================

    @api.model
    def register_feature(
        self,
        device,
        feature_data,
        snapshot=None,
    ):
        """
        Permite registrar características descubiertas que todavía
        no vienen de una sat.monitoring.reading concreta.

        Útil para discovery estructural.

        Se crea una reading sintética antes de actualizar el feature,
        manteniendo trazabilidad.
        """
        device.ensure_one()

        feature_data = feature_data or {}

        code = _clean_text(
            feature_data.get(
                'code'
            )
        )

        if not code:
            raise ValidationError(
                _(
                    'La característica debe tener '
                    'un código técnico.'
                )
            )

        if not snapshot:
            snapshot = self.env[
                'sat.monitoring.snapshot'
            ].create_for_device(
                device=device,
            )

        metric = False

        if device.profile_id:
            metric = self.env[
                'sat.snmp.profile.metric'
            ].search(
                [
                    (
                        'profile_id',
                        '=',
                        device.profile_id.id,
                    ),
                    (
                        'code',
                        '=',
                        code,
                    ),
                ],
                limit=1,
            )

        Reading = self.env[
            'sat.monitoring.reading'
        ]

        result = {
            'code':
                code,

            'name':
                _clean_text(
                    feature_data.get(
                        'name'
                    )
                    or code
                ),

            'category':
                _clean_text(
                    feature_data.get(
                        'reading_category'
                    )
                    or feature_data.get(
                        'category'
                    )
                    or 'other'
                ),

            'logical_type':
                _clean_text(
                    feature_data.get(
                        'logical_type'
                    )
                    or 'string'
                ),

            'success':
                True,

            'status':
                'success',

            'value':
                feature_data.get(
                    'value'
                ),

            'normalized_value':
                feature_data.get(
                    'value'
                ),

            'raw_value':
                feature_data.get(
                    'raw_value'
                ),

            'oid':
                feature_data.get(
                    'oid'
                ),

            'oid_name':
                feature_data.get(
                    'oid_name'
                ),

            'index':
                feature_data.get(
                    'oid_index'
                ),

            'source_label':
                feature_data.get(
                    'source_label'
                ),

            'method':
                feature_data.get(
                    'source_method'
                )
                or 'dynamic_discovery',

            'discovered_dynamically':
                feature_data.get(
                    'discovered_dynamically',
                    True,
                ),

            'confidence':
                feature_data.get(
                    'confidence'
                )
                or 'candidate',
        }

        reading = (
            Reading.create_from_agent_result(
                snapshot=snapshot,
                result=result,
                metric=metric,
            )
        )

        return self.update_from_reading(
            reading=reading,
            feature_data=feature_data,
        )

    # ========================================================
    # MARCAR COMO RETIRADO
    # ========================================================

    def mark_removed(
        self,
        snapshot=None,
    ):
        now = (
            snapshot.date
            if snapshot
            and snapshot.date
            else fields.Datetime.now()
        )

        for record in self:
            vals = {
                'present':
                    False,

                'installed':
                    False,

                'active':
                    False,

                'removed_at':
                    now,

                'last_changed_at':
                    now,

                'changed':
                    True,

                'previous_value_text':
                    record._normalized_value_as_text(),
            }

            if snapshot:
                vals[
                    'snapshot_id'
                ] = snapshot.id

            record.sudo().write(
                vals
            )

        devices = self.mapped(
            'device_id'
        )

        for device in devices:
            device.recalculate_feature_summary()

        return True

    # ========================================================
    # REACTIVAR
    # ========================================================

    def mark_present(
        self,
        snapshot=None,
    ):
        now = (
            snapshot.date
            if snapshot
            and snapshot.date
            else fields.Datetime.now()
        )

        for record in self:
            vals = {
                'present':
                    True,

                'active':
                    True,

                'removed_at':
                    False,

                'last_seen':
                    now,

                'last_changed_at':
                    now,

                'changed':
                    True,
            }

            if snapshot:
                vals[
                    'snapshot_id'
                ] = snapshot.id

            record.sudo().write(
                vals
            )

        devices = self.mapped(
            'device_id'
        )

        for device in devices:
            device.recalculate_feature_summary()

        return True

    # ========================================================
    # RESUMEN PARA API
    # ========================================================

    def get_feature_payload(self):
        self.ensure_one()

        return {
            'id':
                self.id,

            'code':
                self.code,

            'name':
                self.name,

            'category':
                self.category,

            'subgroup':
                self.subgroup or '',

            'type':
                self.feature_type,

            'present':
                self.present,

            'active':
                self.active,

            'installed':
                self.installed,

            'supported':
                self.supported,

            'value':
                self.get_normalized_value(),

            'unit':
                self.unit or '',

            'manufacturer':
                self.manufacturer or '',

            'model':
                self.model or '',

            'serial':
                self.serial or '',

            'version':
                self.version or '',

            'capacity':
                (
                    self.capacity
                    if self.capacity
                    else None
                ),

            'capacity_unit':
                self.capacity_unit or '',

            'life_percent':
                (
                    self.life_percent
                    if self.life_percent
                    else None
                ),

            'tray': {
                'index':
                    self.tray_index or '',

                'name':
                    self.tray_name or '',

                'paper_size':
                    self.paper_size or '',

                'paper_type':
                    self.paper_type or '',

                'paper_level':
                    self.paper_level,

                'paper_level_unit':
                    self.paper_level_unit or '',

                'max_capacity':
                    self.max_capacity,
            },

            'component': {
                'index':
                    self.component_index or '',

                'color':
                    self.component_color,

                'status':
                    self.component_status or '',
            },

            'source': {
                'profile_id':
                    self.profile_id.id
                    if self.profile_id
                    else False,

                'metric_id':
                    self.metric_id.id
                    if self.metric_id
                    else False,

                'snapshot_id':
                    self.snapshot_id.id
                    if self.snapshot_id
                    else False,

                'reading_id':
                    self.reading_id.id
                    if self.reading_id
                    else False,

                'oid':
                    self.oid or '',

                'oid_name':
                    self.oid_name or '',

                'oid_index':
                    self.oid_index or '',

                'label':
                    self.source_label or '',

                'method':
                    self.source_method,

                'dynamic':
                    self.discovered_dynamically,
            },

            'confidence':
                self.confidence,

            'first_seen':
                (
                    fields.Datetime.to_string(
                        self.first_seen
                    )
                    if self.first_seen
                    else ''
                ),

            'last_seen':
                (
                    fields.Datetime.to_string(
                        self.last_seen
                    )
                    if self.last_seen
                    else ''
                ),

            'removed_at':
                (
                    fields.Datetime.to_string(
                        self.removed_at
                    )
                    if self.removed_at
                    else ''
                ),
        }