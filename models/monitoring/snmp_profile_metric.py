# -*- coding: utf-8 -*-

import json
import logging
import re

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


def _json_loads_safe(value):
    if not value:
        return {}

    if isinstance(value, dict):
        return value

    try:
        return json.loads(value)
    except Exception:
        return {}


def _json_dumps_safe(value):
    try:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    except Exception:
        return '{}'


def _is_valid_oid(value):
    """
    Valida OIDs numéricos.

    Acepta:
        1.3.6.1
        .1.3.6.1
        1.3.6.1.4.1.367.3.2
    """
    value = _clean_text(value).strip('.')

    if not value:
        return False

    return bool(
        re.fullmatch(
            r'\d+(?:\.\d+)*',
            value,
        )
    )


def _normalize_oid(value):
    value = _clean_text(value).strip('.')
    return value


# ============================================================
# MÉTRICA SNMP
# ============================================================

class SatSnmpProfileMetric(models.Model):
    """
    Define UNA métrica o dato que puede obtener el agente SNMP.

    Ejemplos:

        MACHINE_TOTAL
        COPY_TOTAL
        PRINT_TOTAL
        TONER_K
        SERIAL
        FIRMWARE
        OCR_SUPPORTED
        FAX_SUPPORTED
        ADF_PRESENT
        FINISHER_PRESENT
        PAPER_JAM
        DEVICE_STATUS

    El agente no necesita conocer marcas.

    Recibe estas reglas desde Odoo y las ejecuta.
    """

    _name = 'sat.snmp.profile.metric'
    _description = 'Métrica de perfil SNMP'
    _order = (
        'profile_id, '
        'category, '
        'sequence, '
        'name, '
        'id'
    )

    # ========================================================
    # PERFIL
    # ========================================================

    profile_id = fields.Many2one(
        'sat.snmp.profile',
        string='Perfil SNMP',
        required=True,
        ondelete='cascade',
        index=True,
    )

    marca_id = fields.Many2one(
        related='profile_id.marca_id',
        string='Marca',
        store=True,
        readonly=True,
        index=True,
    )

    marca_codigo = fields.Char(
        related='profile_id.marca_codigo',
        string='Código marca',
        store=True,
        readonly=True,
        index=True,
    )

    # ========================================================
    # IDENTIFICACIÓN
    # ========================================================

    name = fields.Char(
        string='Nombre',
        required=True,
        index=True,
        help=(
            'Nombre humano de la métrica. '
            'Ejemplo: Contador total, Tóner negro, OCR.'
        ),
    )

    code = fields.Char(
        string='Código técnico',
        required=True,
        index=True,
        help=(
            'Código lógico estable utilizado por agente y API.\n\n'
            'Ejemplos:\n'
            'machine_total\n'
            'print_total\n'
            'toner_k\n'
            'ocr_supported\n'
            'finisher_present'
        ),
    )

    description = fields.Text(
        string='Descripción',
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
        index=True,
    )

    required = fields.Boolean(
        string='Obligatorio',
        default=False,
        help=(
            'Si está marcado y no puede obtenerse, el agente '
            'puede considerar incompleta la aplicación del perfil.'
        ),
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )

    priority = fields.Integer(
        string='Prioridad',
        default=100,
        help=(
            'Permite tener varias reglas candidatas para una misma '
            'métrica lógica. Mayor prioridad = preferida.'
        ),
    )

    # ========================================================
    # CATEGORÍA
    # ========================================================

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
        help=(
            'Clasificación adicional.\n'
            'Ejemplos: copy, print, scanner, toner, fuser, '
            'paper_input, finishing, OCR.'
        ),
    )

    # ========================================================
    # TIPO LÓGICO
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
    )

    unit = fields.Char(
        string='Unidad',
        help=(
            'Ejemplos: pages, percent, seconds, bytes, sheets, jobs.'
        ),
    )

    # ========================================================
    # MÉTODO DE OBTENCIÓN
    # ========================================================

    method = fields.Selection(
        [
            ('direct_oid', 'OID directo'),
            ('table_label_value', 'Tabla etiqueta / valor'),
            ('indexed_table', 'Tabla indexada'),
            ('walk_branch', 'WALK de rama'),
            ('presence', 'Detección de presencia'),
            ('enum_value', 'Valor enumerado'),
            ('bit_flag', 'Bit / Flag'),
            ('derived', 'Derivada'),
            ('dynamic_discovery', 'Descubrimiento dinámico'),
        ],
        string='Método',
        required=True,
        default='direct_oid',
        index=True,
    )

    # ========================================================
    # OID DIRECTO
    # ========================================================

    oid = fields.Char(
        string='OID',
        index=True,
        help='OID directo de lectura.',
    )

    oid_fallback = fields.Char(
        string='OID alternativo',
        help=(
            'OID secundario si el principal no responde.'
        ),
    )

    # ========================================================
    # TABLAS
    # ========================================================

    table_base_oid = fields.Char(
        string='OID base de tabla',
        help=(
            'Rama base utilizada para resolver métricas dinámicas.'
        ),
    )

    label_column_oid = fields.Char(
        string='Columna OID etiqueta',
        help=(
            'OID base de la columna que contiene los nombres/labels.'
        ),
    )

    value_column_oid = fields.Char(
        string='Columna OID valor',
        help=(
            'OID base de la columna que contiene el valor correspondiente.'
        ),
    )

    secondary_value_column_oid = fields.Char(
        string='Columna secundaria',
        help=(
            'Segunda columna relacionada cuando una tabla necesita '
            'más de un valor.'
        ),
    )

    index_oid = fields.Char(
        string='OID índice',
        help=(
            'OID/columna utilizada para resolver índices explícitos.'
        ),
    )

    fixed_index = fields.Integer(
        string='Índice fijo',
        default=0,
        help=(
            'Solo utilizar cuando el índice se haya comprobado '
            'como estable para este perfil.'
        ),
    )

    dynamic_index = fields.Boolean(
        string='Índice dinámico',
        default=False,
        help=(
            'El agente debe localizar primero la fila y luego usar '
            'su índice para obtener el valor.'
        ),
    )

    # ========================================================
    # ETIQUETAS
    # ========================================================

    label_exact = fields.Char(
        string='Etiqueta exacta',
        help=(
            'Nombre esperado exacto dentro de la tabla.'
        ),
    )

    label_regex = fields.Char(
        string='Expresión regular etiqueta',
        help=(
            'Expresión regular para localizar la fila.'
        ),
    )

    label_contains = fields.Char(
        string='Etiqueta contiene',
        help=(
            'Texto que puede buscarse dentro de la etiqueta.'
        ),
    )

    label_case_sensitive = fields.Boolean(
        string='Distinguir mayúsculas',
        default=False,
    )

    # ========================================================
    # FILTROS ADICIONALES DE FILA
    # ========================================================

    row_filter_oid = fields.Char(
        string='OID filtro de fila',
    )

    row_filter_operator = fields.Selection(
        [
            ('eq', '='),
            ('ne', '!='),
            ('gt', '>'),
            ('gte', '>='),
            ('lt', '<'),
            ('lte', '<='),
            ('contains', 'Contiene'),
            ('regex', 'Regex'),
        ],
        string='Operador filtro',
    )

    row_filter_value = fields.Char(
        string='Valor filtro',
    )

    # ========================================================
    # CAPACIDADES / PRESENCIA
    # ========================================================

    presence_mode = fields.Selection(
        [
            ('oid_exists', 'OID existe'),
            ('value_exists', 'Existe valor'),
            ('value_nonzero', 'Valor distinto de cero'),
            ('value_equals', 'Valor específico'),
            ('text_match', 'Coincidencia de texto'),
            ('row_exists', 'Fila existe'),
        ],
        string='Modo presencia',
        default='oid_exists',
        help=(
            'Útil para capacidades y accesorios como OCR, '
            'ADF, fax, finisher, HDD, Wi-Fi, etc.'
        ),
    )

    presence_expected_value = fields.Char(
        string='Valor esperado',
    )

    presence_expected_regex = fields.Char(
        string='Regex esperado',
    )

    # ========================================================
    # ENUMERADOS
    # ========================================================

    enum_map_json = fields.Text(
        string='Mapa enumerado JSON',
        default='{}',
        help=(
            'Mapea valores SNMP a valores normalizados.\n\n'
            'Ejemplo:\n'
            '{\n'
            '  "1": "other",\n'
            '  "3": "idle",\n'
            '  "4": "printing"\n'
            '}'
        ),
    )

    unknown_enum_value = fields.Char(
        string='Valor enum desconocido',
        default='unknown',
    )

    # ========================================================
    # BITS / FLAGS
    # ========================================================

    bit_position = fields.Integer(
        string='Posición bit',
        default=0,
    )

    bit_mask = fields.Char(
        string='Máscara',
        help='Ejemplo: 0x04',
    )

    bit_expected = fields.Boolean(
        string='Bit esperado activo',
        default=True,
    )

    # ========================================================
    # TRANSFORMACIÓN DEL VALOR
    # ========================================================

    multiplier = fields.Float(
        string='Multiplicador',
        default=1.0,
    )

    divisor = fields.Float(
        string='Divisor',
        default=1.0,
    )

    offset = fields.Float(
        string='Offset',
        default=0.0,
    )

    round_digits = fields.Integer(
        string='Decimales',
        default=0,
    )

    strip_text = fields.Boolean(
        string='Limpiar texto',
        default=True,
    )

    uppercase_text = fields.Boolean(
        string='Convertir a mayúsculas',
        default=False,
    )

    lowercase_text = fields.Boolean(
        string='Convertir a minúsculas',
        default=False,
    )

    # ========================================================
    # RANGO VÁLIDO
    # ========================================================

    minimum_value = fields.Float(
        string='Valor mínimo',
    )

    maximum_value = fields.Float(
        string='Valor máximo',
    )

    use_minimum_value = fields.Boolean(
        string='Validar mínimo',
        default=False,
    )

    use_maximum_value = fields.Boolean(
        string='Validar máximo',
        default=False,
    )

    # ========================================================
    # SENTINELAS / VALORES ESPECIALES
    # ========================================================

    sentinel_values = fields.Text(
        string='Valores especiales',
        help=(
            'Uno por línea.\n\n'
            'Ejemplos:\n'
            '-1\n'
            '-2\n'
            '-3\n'
            '-100\n\n'
            'No deben convertirse automáticamente a 0.'
        ),
    )

    sentinel_behavior = fields.Selection(
        [
            ('preserve', 'Conservar RAW'),
            ('unknown', 'Marcar desconocido'),
            ('unavailable', 'No disponible'),
            ('ignore', 'Ignorar lectura'),
        ],
        string='Comportamiento sentinel',
        default='preserve',
    )

    # ========================================================
    # DERIVADAS
    # ========================================================

    derived_formula = fields.Char(
        string='Fórmula derivada',
        help=(
            'Reservado para métricas calculadas a partir de otras.\n'
            'Ejemplo conceptual:\n'
            'copy_bw + print_bw'
        ),
    )

    dependency_codes = fields.Text(
        string='Dependencias',
        help=(
            'Códigos de métricas necesarias, uno por línea.'
        ),
    )

    # ========================================================
    # POLLING
    # ========================================================

    polling_group = fields.Selection(
        [
            ('fast', 'Rápido'),
            ('normal', 'Normal'),
            ('slow', 'Lento'),
            ('discovery', 'Solo discovery'),
        ],
        string='Grupo de polling',
        default='normal',
        index=True,
    )

    polling_interval = fields.Integer(
        string='Intervalo sugerido (seg)',
        default=300,
        help=(
            'Intervalo sugerido. El servidor puede imponer '
            'una política diferente.'
        ),
    )

    timeout_seconds = fields.Float(
        string='Timeout',
        default=2.0,
    )

    retries = fields.Integer(
        string='Reintentos',
        default=1,
    )

    # ========================================================
    # ALMACENAMIENTO
    # ========================================================

    store_current = fields.Boolean(
        string='Guardar actual',
        default=True,
    )

    store_history = fields.Boolean(
        string='Guardar histórico',
        default=True,
        help=(
            'Contadores, consumibles, componentes y estados '
            'pueden necesitar histórico.'
        ),
    )

    store_raw = fields.Boolean(
        string='Guardar RAW',
        default=False,
    )

    # ========================================================
    # CAMBIO / HISTÓRICO
    # ========================================================

    history_mode = fields.Selection(
        [
            ('always', 'Cada lectura'),
            ('on_change', 'Solo cuando cambia'),
            ('periodic', 'Periódico'),
            ('never', 'No guardar'),
        ],
        string='Modo histórico',
        default='always',
    )

    change_threshold = fields.Float(
        string='Umbral de cambio',
        default=0.0,
        help=(
            'Para valores numéricos permite ignorar cambios pequeños.'
        ),
    )

    # ========================================================
    # ALERTAS
    # ========================================================

    alert_enabled = fields.Boolean(
        string='Puede generar alerta',
        default=False,
    )

    alert_condition = fields.Selection(
        [
            ('truthy', 'Valor verdadero'),
            ('equals', 'Igual a'),
            ('not_equals', 'Distinto de'),
            ('greater', 'Mayor que'),
            ('greater_equal', 'Mayor o igual'),
            ('less', 'Menor que'),
            ('less_equal', 'Menor o igual'),
            ('regex', 'Regex'),
            ('exists', 'Existe'),
        ],
        string='Condición alerta',
    )

    alert_value = fields.Char(
        string='Valor alerta',
    )

    alert_severity = fields.Selection(
        [
            ('info', 'Información'),
            ('warning', 'Advertencia'),
            ('critical', 'Crítica'),
        ],
        string='Severidad',
        default='warning',
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

    tested_count = fields.Integer(
        string='Pruebas',
        default=0,
        readonly=True,
    )

    success_count = fields.Integer(
        string='Éxitos',
        default=0,
        readonly=True,
    )

    failure_count = fields.Integer(
        string='Fallos',
        default=0,
        readonly=True,
    )

    last_success_date = fields.Datetime(
        string='Último éxito',
        readonly=True,
    )

    last_failure_date = fields.Datetime(
        string='Último fallo',
        readonly=True,
    )

    # ========================================================
    # NOTAS
    # ========================================================

    technical_notes = fields.Text(
        string='Notas técnicas',
    )

    discovery_source = fields.Char(
        string='Origen descubrimiento',
        help=(
            'Ejemplo: walk, MIB, prueba manual, documentación fabricante.'
        ),
    )

    # ========================================================
    # SQL
    # ========================================================

    _sql_constraints = [
        (
            'sat_snmp_profile_metric_code_unique',
            'unique(profile_id, code)',
            'Ya existe una métrica con ese código dentro del perfil.',
        ),
        (
            'sat_snmp_profile_metric_polling_positive',
            'CHECK(polling_interval >= 0)',
            'El intervalo de polling no puede ser negativo.',
        ),
        (
            'sat_snmp_profile_metric_timeout_positive',
            'CHECK(timeout_seconds >= 0)',
            'El timeout no puede ser negativo.',
        ),
        (
            'sat_snmp_profile_metric_retries_positive',
            'CHECK(retries >= 0)',
            'Los reintentos no pueden ser negativos.',
        ),
        (
            'sat_snmp_profile_metric_divisor_nonzero',
            'CHECK(divisor <> 0)',
            'El divisor no puede ser cero.',
        ),
    ]

    # ========================================================
    # VALIDACIONES
    # ========================================================

    @api.constrains('code')
    def _check_code(self):
        for record in self:
            if not record.code:
                raise ValidationError(
                    _('La métrica debe tener código técnico.')
                )

            if not re.fullmatch(
                r'[a-z0-9_]+',
                record.code,
            ):
                raise ValidationError(
                    _(
                        'El código "%s" no es válido.\n'
                        'Use únicamente letras minúsculas, '
                        'números y guion bajo.'
                    ) % record.code
                )

    @api.constrains(
        'oid',
        'oid_fallback',
        'table_base_oid',
        'label_column_oid',
        'value_column_oid',
        'secondary_value_column_oid',
        'index_oid',
        'row_filter_oid',
    )
    def _check_oids(self):
        fields_to_validate = [
            'oid',
            'oid_fallback',
            'table_base_oid',
            'label_column_oid',
            'value_column_oid',
            'secondary_value_column_oid',
            'index_oid',
            'row_filter_oid',
        ]

        for record in self:
            for field_name in fields_to_validate:
                value = record[field_name]

                if not value:
                    continue

                if not _is_valid_oid(value):
                    raise ValidationError(
                        _(
                            'OID inválido en "%(field)s": %(oid)s'
                        ) % {
                            'field': field_name,
                            'oid': value,
                        }
                    )

    @api.constrains(
        'label_regex',
        'presence_expected_regex',
    )
    def _check_regex(self):
        for record in self:
            values = [
                (
                    _('Etiqueta'),
                    record.label_regex,
                ),
                (
                    _('Presencia'),
                    record.presence_expected_regex,
                ),
            ]

            for label, expression in values:
                if not expression:
                    continue

                try:
                    re.compile(expression)
                except re.error as error:
                    raise ValidationError(
                        _(
                            'Regex inválido en %(field)s:\n\n'
                            '%(regex)s\n\n'
                            '%(error)s'
                        ) % {
                            'field': label,
                            'regex': expression,
                            'error': str(error),
                        }
                    )

    @api.constrains('enum_map_json')
    def _check_enum_json(self):
        for record in self:
            if not record.enum_map_json:
                continue

            try:
                value = json.loads(
                    record.enum_map_json
                )
            except Exception as error:
                raise ValidationError(
                    _(
                        'El mapa enumerado debe ser JSON válido.\n\n%s'
                    ) % error
                )

            if not isinstance(value, dict):
                raise ValidationError(
                    _(
                        'El mapa enumerado debe ser un objeto JSON.'
                    )
                )

    @api.constrains(
        'use_minimum_value',
        'minimum_value',
        'use_maximum_value',
        'maximum_value',
    )
    def _check_min_max(self):
        for record in self:
            if (
                record.use_minimum_value
                and record.use_maximum_value
                and record.minimum_value > record.maximum_value
            ):
                raise ValidationError(
                    _(
                        'El valor mínimo no puede ser mayor '
                        'que el valor máximo.'
                    )
                )

    @api.constrains(
        'method',
        'oid',
        'label_column_oid',
        'value_column_oid',
        'label_exact',
        'label_regex',
        'label_contains',
    )
    def _check_method_configuration(self):
        for record in self:
            if record.method == 'direct_oid':
                if not record.oid:
                    raise ValidationError(
                        _(
                            'La métrica "%s" usa OID directo '
                            'pero no tiene OID.'
                        ) % record.display_name
                    )

            elif record.method == 'table_label_value':
                if not record.label_column_oid:
                    raise ValidationError(
                        _(
                            'La métrica "%s" necesita la columna '
                            'de etiquetas.'
                        ) % record.display_name
                    )

                if not record.value_column_oid:
                    raise ValidationError(
                        _(
                            'La métrica "%s" necesita la columna '
                            'de valores.'
                        ) % record.display_name
                    )

                if not (
                    record.label_exact
                    or record.label_regex
                    or record.label_contains
                ):
                    raise ValidationError(
                        _(
                            'La métrica "%s" debe definir cómo '
                            'localizar la etiqueta de la fila.'
                        ) % record.display_name
                    )

            elif record.method == 'walk_branch':
                if not (
                    record.table_base_oid
                    or record.oid
                ):
                    raise ValidationError(
                        _(
                            'Una métrica WALK debe tener '
                            'una rama base.'
                        )
                    )

            elif record.method == 'derived':
                if not record.derived_formula:
                    raise ValidationError(
                        _(
                            'Una métrica derivada necesita fórmula.'
                        )
                    )

    # ========================================================
    # ONCHANGE
    # ========================================================

    @api.onchange('method')
    def _onchange_method(self):
        """
        Solo prepara defaults, no elimina configuración existente.
        """
        for record in self:
            if record.method == 'table_label_value':
                record.dynamic_index = True

            elif record.method == 'direct_oid':
                record.dynamic_index = False

            elif record.method == 'presence':
                record.store_history = False
                record.history_mode = 'on_change'

            elif record.method == 'dynamic_discovery':
                record.polling_group = 'discovery'

    @api.onchange('category')
    def _onchange_category_defaults(self):
        for record in self:
            if record.category == 'counter':
                record.logical_type = 'integer'
                record.unit = record.unit or 'pages'
                record.store_history = True
                record.history_mode = 'always'

            elif record.category == 'consumable':
                record.logical_type = 'float'
                record.unit = record.unit or 'percent'
                record.store_history = True
                record.history_mode = 'on_change'

            elif record.category == 'capability':
                record.logical_type = 'boolean'
                record.store_history = False
                record.history_mode = 'on_change'

            elif record.category == 'alert':
                record.store_history = True
                record.history_mode = 'on_change'
                record.alert_enabled = True

    # ========================================================
    # CONFIANZA
    # ========================================================

    def register_test_result(
        self,
        success,
    ):
        for record in self:
            tested = record.tested_count + 1

            success_count = record.success_count
            failure_count = record.failure_count

            vals = {
                'tested_count': tested,
            }

            if success:
                success_count += 1

                vals.update({
                    'success_count': success_count,
                    'last_success_date':
                        fields.Datetime.now(),
                })

            else:
                failure_count += 1

                vals.update({
                    'failure_count': failure_count,
                    'last_failure_date':
                        fields.Datetime.now(),
                })

            rate = (
                success_count / tested * 100.0
                if tested
                else 0.0
            )

            if tested >= 10 and rate >= 98:
                vals['confidence'] = 'very_high'

            elif tested >= 4 and rate >= 95:
                vals['confidence'] = 'high'

            elif tested >= 2 and rate >= 90:
                vals['confidence'] = 'provisional'

            elif success_count:
                vals['confidence'] = 'candidate'

            else:
                vals['confidence'] = 'unknown'

            record.write(vals)

        return True

    # ========================================================
    # PAYLOAD PARA AGENTE
    # ========================================================

    def get_agent_payload(self):
        """
        Devuelve únicamente instrucciones técnicas necesarias
        para que el agente consulte esta métrica.

        No devuelve información administrativa innecesaria.
        """
        self.ensure_one()

        enum_map = _json_loads_safe(
            self.enum_map_json
        )

        sentinels = []

        for line in (
            self.sentinel_values or ''
        ).splitlines():
            line = line.strip()

            if line:
                sentinels.append(line)

        dependencies = []

        for line in (
            self.dependency_codes or ''
        ).splitlines():
            line = line.strip()

            if line:
                dependencies.append(line)

        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,

            'category': self.category,
            'subgroup': self.subgroup or '',

            'logical_type':
                self.logical_type,

            'unit':
                self.unit or '',

            'required':
                self.required,

            'priority':
                self.priority,

            'method':
                self.method,

            'oid':
                _normalize_oid(self.oid),

            'oid_fallback':
                _normalize_oid(
                    self.oid_fallback
                ),

            'table': {
                'base_oid':
                    _normalize_oid(
                        self.table_base_oid
                    ),

                'label_column_oid':
                    _normalize_oid(
                        self.label_column_oid
                    ),

                'value_column_oid':
                    _normalize_oid(
                        self.value_column_oid
                    ),

                'secondary_value_column_oid':
                    _normalize_oid(
                        self.secondary_value_column_oid
                    ),

                'index_oid':
                    _normalize_oid(
                        self.index_oid
                    ),

                'fixed_index':
                    self.fixed_index,

                'dynamic_index':
                    self.dynamic_index,
            },

            'label_match': {
                'exact':
                    self.label_exact or '',

                'regex':
                    self.label_regex or '',

                'contains':
                    self.label_contains or '',

                'case_sensitive':
                    self.label_case_sensitive,
            },

            'row_filter': {
                'oid':
                    _normalize_oid(
                        self.row_filter_oid
                    ),

                'operator':
                    self.row_filter_operator or '',

                'value':
                    self.row_filter_value or '',
            },

            'presence': {
                'mode':
                    self.presence_mode,

                'expected_value':
                    self.presence_expected_value or '',

                'expected_regex':
                    self.presence_expected_regex or '',
            },

            'enum': {
                'map': enum_map,

                'unknown':
                    self.unknown_enum_value
                    or 'unknown',
            },

            'bits': {
                'position':
                    self.bit_position,

                'mask':
                    self.bit_mask or '',

                'expected':
                    self.bit_expected,
            },

            'transform': {
                'multiplier':
                    self.multiplier,

                'divisor':
                    self.divisor,

                'offset':
                    self.offset,

                'round_digits':
                    self.round_digits,

                'strip_text':
                    self.strip_text,

                'uppercase':
                    self.uppercase_text,

                'lowercase':
                    self.lowercase_text,
            },

            'validation': {
                'use_minimum':
                    self.use_minimum_value,

                'minimum':
                    self.minimum_value,

                'use_maximum':
                    self.use_maximum_value,

                'maximum':
                    self.maximum_value,

                'sentinel_values':
                    sentinels,

                'sentinel_behavior':
                    self.sentinel_behavior,
            },

            'derived': {
                'formula':
                    self.derived_formula or '',

                'dependencies':
                    dependencies,
            },

            'polling': {
                'group':
                    self.polling_group,

                'interval':
                    self.polling_interval,

                'timeout':
                    self.timeout_seconds,

                'retries':
                    self.retries,
            },

            'storage': {
                'store_current':
                    self.store_current,

                'store_history':
                    self.store_history,

                'store_raw':
                    self.store_raw,

                'history_mode':
                    self.history_mode,

                'change_threshold':
                    self.change_threshold,
            },

            'alert': {
                'enabled':
                    self.alert_enabled,

                'condition':
                    self.alert_condition or '',

                'value':
                    self.alert_value or '',

                'severity':
                    self.alert_severity,
            },

            'confidence':
                self.confidence,
        }

    # ========================================================
    # RESUMEN
    # ========================================================

    def get_metric_summary(self):
        self.ensure_one()

        return {
            'id': self.id,
            'profile_id':
                self.profile_id.id,

            'profile_code':
                self.profile_id.code,

            'brand':
                self.marca_codigo,

            'code':
                self.code,

            'name':
                self.name,

            'category':
                self.category,

            'method':
                self.method,

            'logical_type':
                self.logical_type,

            'required':
                self.required,

            'active':
                self.active,

            'confidence':
                self.confidence,

            'tested_count':
                self.tested_count,

            'success_count':
                self.success_count,

            'failure_count':
                self.failure_count,
        }