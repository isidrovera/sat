# -*- coding: utf-8 -*-

import logging
import re
import unicodedata

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================

def _normalize_code(value):
    """
    Convierte cualquier texto en un código técnico estable.

    Ejemplos:
        Ricoh General         -> ricoh_general
        Konica Minolta Color -> konica_minolta_color
        Canon iR-ADV DX       -> canon_ir_adv_dx
    """
    value = value or ''

    value = unicodedata.normalize('NFKD', str(value))
    value = ''.join(
        character
        for character in value
        if not unicodedata.combining(character)
    )

    value = value.lower().strip()
    value = re.sub(r'[^a-z0-9]+', '_', value)
    value = re.sub(r'_+', '_', value)
    value = value.strip('_')

    return value


def _clean_text(value):
    if value in (None, False):
        return ''
    return str(value).strip()


def _normalize_compare(value):
    """
    Normalización ligera para comparaciones de fabricante/modelo.
    """
    value = _clean_text(value)

    value = unicodedata.normalize('NFKD', value)
    value = ''.join(
        character
        for character in value
        if not unicodedata.combining(character)
    )

    return value.lower().strip()


def _parse_lines(value):
    """
    Convierte un campo Text en una lista.

    Ignora:
        - líneas vacías
        - líneas que comienzan con #
    """
    result = []

    for line in (_clean_text(value)).splitlines():
        line = line.strip()

        if not line:
            continue

        if line.startswith('#'):
            continue

        result.append(line)

    return result


def _regex_matches(pattern, value):
    """
    Busca un patrón regex sin distinguir mayúsculas/minúsculas.

    Si value está vacío retorna False.
    """
    if not pattern or not value:
        return False

    try:
        return bool(
            re.search(
                pattern,
                value,
                flags=re.IGNORECASE,
            )
        )
    except re.error:
        return False


def _any_regex_matches(patterns, value):
    if not value:
        return False

    for pattern in patterns:
        if _regex_matches(pattern, value):
            return True

    return False


def _normalize_enterprise(value):
    """
    Normaliza Enterprise ID.

    Acepta, por ejemplo:

        367
        .1.3.6.1.4.1.367
        1.3.6.1.4.1.367
        1.3.6.1.4.1.367.3.2

    Mantiene únicamente números y puntos.
    """
    value = _clean_text(value)

    if not value:
        return ''

    value = value.strip('.')

    if re.fullmatch(r'\d+', value):
        return value

    if re.fullmatch(r'\d+(?:\.\d+)+', value):
        return value

    return value


def _enterprise_matches(configured_value, detected_value):
    """
    Compara Enterprise IDs de manera flexible.

    Ejemplos equivalentes:

        configurado: 367
        detectado:   1.3.6.1.4.1.367

    También permite que un perfil tenga una rama más completa:

        1.3.6.1.4.1.367.3.2
    """
    configured = _normalize_enterprise(configured_value)
    detected = _normalize_enterprise(detected_value)

    if not configured or not detected:
        return False

    if configured == detected:
        return True

    configured_parts = configured.split('.')
    detected_parts = detected.split('.')

    # Caso enterprise simple: 367
    if len(configured_parts) == 1:
        enterprise = configured_parts[0]

        if enterprise in detected_parts:
            try:
                idx = detected_parts.index(enterprise)

                prefix = detected_parts[:idx]

                if prefix == ['1', '3', '6', '1', '4', '1']:
                    return True

            except ValueError:
                pass

    # Comparación por prefijo OID completo.
    if detected.startswith(configured + '.'):
        return True

    if configured.startswith(detected + '.'):
        return True

    return False


# ============================================================
# PERFIL SNMP
# ============================================================

class SatSnmpProfile(models.Model):
    """
    Perfil SNMP central.

    Este modelo NO representa una impresora física.

    Representa el conocimiento necesario para saber qué conjunto de
    métricas debe utilizar el agente según:

        - marca
        - familia
        - modelo
        - tecnología color / monocromo
        - Enterprise ID
        - sysDescr
        - firmware
        - prioridad
        - reglas de compatibilidad

    Los OIDs y reglas individuales viven en:
        sat.snmp.profile.metric
    """

    _name = 'sat.snmp.profile'
    _description = 'Perfil SNMP de impresoras'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'marca_id, priority desc, sequence, name, id'

    # ========================================================
    # IDENTIFICACIÓN
    # ========================================================

    name = fields.Char(
        string='Nombre del perfil',
        required=True,
        tracking=True,
        index=True,
        help=(
            'Nombre funcional del perfil SNMP. '
            'Ejemplo: Ricoh General, Ricoh MP Monocromo, '
            'Konica Minolta bizhub Color.'
        ),
    )

    code = fields.Char(
        string='Código técnico',
        required=True,
        copy=False,
        tracking=True,
        index=True,
        help=(
            'Código estable utilizado por API y agente. '
            'Ejemplo: ricoh_general, ricoh_mp_mono.'
        ),
    )

    marca_id = fields.Many2one(
        'marca.marca',
        string='Marca',
        required=True,
        ondelete='restrict',
        tracking=True,
        index=True,
        help='Marca de equipos a la que pertenece este perfil.',
    )

    marca_codigo = fields.Char(
        string='Código marca',
        related='marca_id.codigo_tecnico',
        store=True,
        readonly=True,
        index=True,
    )

    description = fields.Text(
        string='Descripción',
        help=(
            'Descripción técnica del alcance de este perfil y cualquier '
            'consideración especial conocida.'
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
        help='Orden administrativo del perfil.',
    )

    priority = fields.Integer(
        string='Prioridad de selección',
        default=100,
        tracking=True,
        index=True,
        help=(
            'Cuando varios perfiles coinciden con un equipo, el perfil '
            'con mejor puntuación y mayor prioridad será preferido.'
        ),
    )

    # ========================================================
    # VERSIÓN
    # ========================================================

    version = fields.Char(
        string='Versión',
        required=True,
        default='1.0',
        tracking=True,
        help='Versión funcional del perfil SNMP.',
    )

    revision = fields.Integer(
        string='Revisión',
        default=1,
        required=True,
        tracking=True,
        help=(
            'Número interno de revisión. Puede incrementarse cuando '
            'cambian las métricas del perfil.'
        ),
    )

    # ========================================================
    # ESTADO
    # ========================================================

    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('testing', 'En pruebas'),
            ('validated', 'Validado'),
            ('deprecated', 'Obsoleto'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
        index=True,
    )

    is_default_for_brand = fields.Boolean(
        string='Perfil general de la marca',
        default=False,
        tracking=True,
        help=(
            'Perfil de respaldo cuando no existe uno más específico '
            'para el modelo/familia detectado.'
        ),
    )

    # ========================================================
    # FAMILIA / GENERACIÓN
    # ========================================================

    family = fields.Char(
        string='Familia',
        tracking=True,
        index=True,
        help=(
            'Familia técnica o comercial. '
            'Ejemplo: MP, IM, bizhub, imageRUNNER ADVANCE.'
        ),
    )

    series = fields.Char(
        string='Serie / generación',
        tracking=True,
        index=True,
        help=(
            'Serie o generación si es necesario diferenciar perfiles '
            'dentro de una misma familia.'
        ),
    )

    technology = fields.Selection(
        [
            ('any', 'Cualquiera'),
            ('mono', 'Monocromo'),
            ('color', 'Color'),
        ],
        string='Tecnología',
        required=True,
        default='any',
        tracking=True,
        index=True,
        help=(
            'Permite restringir el perfil a equipos monocromos o color. '
            'Cualquiera permite utilizarlo en ambos.'
        ),
    )

    # ========================================================
    # SNMP SOPORTADO
    # ========================================================

    supports_snmp_v1 = fields.Boolean(
        string='SNMP v1',
        default=True,
    )

    supports_snmp_v2c = fields.Boolean(
        string='SNMP v2c',
        default=True,
    )

    supports_snmp_v3 = fields.Boolean(
        string='SNMP v3',
        default=True,
    )

    preferred_snmp_version = fields.Selection(
        [
            ('1', 'SNMP v1'),
            ('2c', 'SNMP v2c'),
            ('3', 'SNMP v3'),
        ],
        string='Versión SNMP preferida',
        default='2c',
        required=True,
        tracking=True,
    )

    # ========================================================
    # ESTRATEGIA DEL AGENTE
    # ========================================================

    polling_strategy = fields.Selection(
        [
            ('profile', 'Solo perfil'),
            ('hybrid', 'Perfil + descubrimiento si falla'),
            ('discovery', 'Descubrimiento dinámico'),
        ],
        string='Estrategia',
        default='hybrid',
        required=True,
        tracking=True,
        help=(
            'Solo perfil: consulta únicamente métricas conocidas.\n'
            'Perfil + descubrimiento: usa el perfil y amplía búsqueda '
            'si faltan datos importantes.\n'
            'Descubrimiento dinámico: se utiliza para investigación '
            'de familias aún no consolidadas.'
        ),
    )

    allow_fallback_discovery = fields.Boolean(
        string='Permitir descubrimiento de respaldo',
        default=True,
        help=(
            'Si una métrica obligatoria no responde, permite al agente '
            'realizar una exploración adicional para intentar localizarla.'
        ),
    )

    preserve_raw_data = fields.Boolean(
        string='Conservar RAW',
        default=True,
        help=(
            'Indica al agente/servidor que debe conservar los valores '
            'SNMP crudos necesarios para auditoría y aprendizaje.'
        ),
    )

    # ========================================================
    # ENTERPRISE ID
    # ========================================================

    enterprise_ids = fields.Text(
        string='Enterprise IDs compatibles',
        help=(
            'Uno por línea.\n\n'
            'Ejemplos:\n'
            '367\n'
            '1.3.6.1.4.1.367\n\n'
            'Se permiten varias ramas cuando una marca o familia '
            'utiliza diferentes identificadores.'
        ),
    )

    enterprise_strict = fields.Boolean(
        string='Enterprise ID obligatorio',
        default=False,
        help=(
            'Si está activo y se conoce el Enterprise ID del equipo, '
            'el perfil será descartado cuando no coincida.'
        ),
    )

    # ========================================================
    # REGLAS DE FABRICANTE
    # ========================================================

    manufacturer_patterns = fields.Text(
        string='Patrones de fabricante',
        help=(
            'Expresiones regulares, una por línea.\n'
            'Ejemplo para Ricoh:\n'
            '^RICOH$'
        ),
    )

    # ========================================================
    # REGLAS DE MODELO
    # ========================================================

    model_patterns = fields.Text(
        string='Patrones de modelo',
        help=(
            'Expresiones regulares de modelos compatibles, '
            'una por línea.\n\n'
            'Ejemplos:\n'
            '^MP 30\\d\\d$\\n'
            '^IM C\\d+$'
        ),
    )

    excluded_model_patterns = fields.Text(
        string='Modelos excluidos',
        help=(
            'Expresiones regulares de modelos que deben ser '
            'rechazados aunque otras reglas coincidan.'
        ),
    )

    # ========================================================
    # REGLAS DE SYSDESCR
    # ========================================================

    sysdescr_patterns = fields.Text(
        string='Patrones sysDescr',
        help=(
            'Expresiones regulares buscadas dentro de sysDescr. '
            'Una por línea.'
        ),
    )

    # ========================================================
    # REGLAS DE FIRMWARE
    # ========================================================

    firmware_patterns = fields.Text(
        string='Patrones de firmware',
        help=(
            'Permite restringir un perfil a determinados firmwares '
            'cuando una generación cambia de estructura SNMP.'
        ),
    )

    # ========================================================
    # UMBRAL DE SELECCIÓN
    # ========================================================

    minimum_match_score = fields.Integer(
        string='Puntuación mínima',
        default=100,
        required=True,
        help=(
            'Puntuación mínima para que el agente/servidor considere '
            'este perfil compatible con un equipo.'
        ),
    )

    # ========================================================
    # MÉTRICAS
    # ========================================================

    metric_ids = fields.One2many(
        'sat.snmp.profile.metric',
        'profile_id',
        string='Métricas SNMP',
        copy=True,
    )

    metric_count = fields.Integer(
        string='Métricas',
        compute='_compute_metric_stats',
        store=True,
    )

    required_metric_count = fields.Integer(
        string='Métricas obligatorias',
        compute='_compute_metric_stats',
        store=True,
    )

    enabled_metric_count = fields.Integer(
        string='Métricas activas',
        compute='_compute_metric_stats',
        store=True,
    )

    # ========================================================
    # VALIDACIÓN DEL PERFIL
    # ========================================================

    tested_device_count = fields.Integer(
        string='Equipos probados',
        default=0,
        readonly=True,
        copy=False,
        tracking=True,
    )

    successful_device_count = fields.Integer(
        string='Pruebas exitosas',
        default=0,
        readonly=True,
        copy=False,
        tracking=True,
    )

    failed_device_count = fields.Integer(
        string='Pruebas fallidas',
        default=0,
        readonly=True,
        copy=False,
        tracking=True,
    )

    success_rate = fields.Float(
        string='Éxito (%)',
        compute='_compute_success_rate',
        store=True,
        digits=(5, 2),
    )

    confidence = fields.Selection(
        [
            ('unknown', 'Sin validar'),
            ('candidate', 'Candidato'),
            ('provisional', 'Provisional'),
            ('high', 'Alta'),
            ('very_high', 'Muy alta'),
        ],
        string='Confianza',
        compute='_compute_confidence',
        store=True,
        index=True,
    )

    last_validation_date = fields.Datetime(
        string='Última validación',
        readonly=True,
        copy=False,
    )

    last_validation_user_id = fields.Many2one(
        'res.users',
        string='Última validación por',
        readonly=True,
        copy=False,
    )

    validation_notes = fields.Text(
        string='Notas de validación',
        tracking=True,
    )

    # ========================================================
    # AUDITORÍA
    # ========================================================

    last_agent_request = fields.Datetime(
        string='Última solicitud de agente',
        readonly=True,
        copy=False,
        help=(
            'Última vez que este perfil fue solicitado para '
            'configurar un agente.'
        ),
    )

    agent_request_count = fields.Integer(
        string='Solicitudes de agentes',
        default=0,
        readonly=True,
        copy=False,
    )

    # ========================================================
    # SQL
    # ========================================================

    _sql_constraints = [
        (
            'sat_snmp_profile_code_unique',
            'unique(code)',
            'El código técnico del perfil SNMP ya está siendo utilizado.',
        ),
        (
            'sat_snmp_profile_revision_positive',
            'CHECK(revision > 0)',
            'La revisión del perfil debe ser mayor que cero.',
        ),
        (
            'sat_snmp_profile_priority_positive',
            'CHECK(priority >= 0)',
            'La prioridad del perfil no puede ser negativa.',
        ),
        (
            'sat_snmp_profile_min_score_positive',
            'CHECK(minimum_match_score >= 0)',
            'La puntuación mínima no puede ser negativa.',
        ),
        (
            'sat_snmp_profile_test_count_positive',
            'CHECK(tested_device_count >= 0)',
            'La cantidad de equipos probados no puede ser negativa.',
        ),
        (
            'sat_snmp_profile_success_count_positive',
            'CHECK(successful_device_count >= 0)',
            'La cantidad de pruebas exitosas no puede ser negativa.',
        ),
        (
            'sat_snmp_profile_failed_count_positive',
            'CHECK(failed_device_count >= 0)',
            'La cantidad de pruebas fallidas no puede ser negativa.',
        ),
    ]

    # ========================================================
    # ONCHANGE / CREATE
    # ========================================================

    @api.onchange('name', 'marca_id')
    def _onchange_generate_code(self):
        """
        Propone el código técnico sin reemplazar uno ingresado manualmente.
        """
        for record in self:
            if record.code:
                continue

            parts = []

            if record.marca_id:
                marca_code = (
                    record.marca_id.codigo_tecnico
                    or record.marca_id.name
                )
                if marca_code:
                    parts.append(marca_code)

            if record.name:
                parts.append(record.name)

            if parts:
                record.code = _normalize_code('_'.join(parts))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                marca_code = ''

                if vals.get('marca_id'):
                    marca = self.env['marca.marca'].browse(
                        vals['marca_id']
                    )
                    marca_code = (
                        marca.codigo_tecnico
                        or marca.name
                        or ''
                    )

                source = '_'.join(
                    item
                    for item in [
                        marca_code,
                        vals.get('name') or '',
                    ]
                    if item
                )

                vals['code'] = _normalize_code(source)

        records = super().create(vals_list)

        return records

    # ========================================================
    # COMPUTES
    # ========================================================

    @api.depends(
        'metric_ids',
        'metric_ids.active',
        'metric_ids.required',
    )
    def _compute_metric_stats(self):
        for record in self:
            metrics = record.metric_ids

            record.metric_count = len(metrics)

            record.enabled_metric_count = len(
                metrics.filtered(
                    lambda metric: metric.active
                )
            )

            record.required_metric_count = len(
                metrics.filtered(
                    lambda metric:
                    metric.active and metric.required
                )
            )

    @api.depends(
        'tested_device_count',
        'successful_device_count',
    )
    def _compute_success_rate(self):
        for record in self:
            if record.tested_device_count <= 0:
                record.success_rate = 0.0
                continue

            record.success_rate = (
                record.successful_device_count
                / record.tested_device_count
            ) * 100.0

    @api.depends(
        'tested_device_count',
        'successful_device_count',
        'failed_device_count',
        'success_rate',
    )
    def _compute_confidence(self):
        """
        Escala conservadora.

        0 pruebas:
            unknown

        1 equipo exitoso:
            candidate

        >= 2 y tasa >= 90:
            provisional

        >= 4 y tasa >= 95:
            high

        >= 10 y tasa >= 98:
            very_high
        """
        for record in self:
            tested = record.tested_device_count
            successful = record.successful_device_count
            rate = record.success_rate

            if tested <= 0:
                record.confidence = 'unknown'

            elif successful <= 0:
                record.confidence = 'candidate'

            elif tested >= 10 and rate >= 98.0:
                record.confidence = 'very_high'

            elif tested >= 4 and rate >= 95.0:
                record.confidence = 'high'

            elif tested >= 2 and rate >= 90.0:
                record.confidence = 'provisional'

            else:
                record.confidence = 'candidate'

    # ========================================================
    # VALIDACIONES
    # ========================================================

    @api.constrains('code')
    def _check_code(self):
        for record in self:
            normalized = _normalize_code(record.code)

            if not normalized:
                raise ValidationError(
                    _('El código técnico del perfil no es válido.')
                )

            if normalized != record.code:
                raise ValidationError(
                    _(
                        'El código técnico debe utilizar únicamente '
                        'letras minúsculas, números y guion bajo.\n\n'
                        'Código sugerido: %s'
                    ) % normalized
                )

    @api.constrains(
        'manufacturer_patterns',
        'model_patterns',
        'excluded_model_patterns',
        'sysdescr_patterns',
        'firmware_patterns',
    )
    def _check_regex_patterns(self):
        fields_to_check = [
            ('manufacturer_patterns', _('Fabricante')),
            ('model_patterns', _('Modelo')),
            ('excluded_model_patterns', _('Modelos excluidos')),
            ('sysdescr_patterns', _('sysDescr')),
            ('firmware_patterns', _('Firmware')),
        ]

        for record in self:
            for field_name, label in fields_to_check:
                patterns = _parse_lines(
                    record[field_name]
                )

                for pattern in patterns:
                    try:
                        re.compile(
                            pattern,
                            flags=re.IGNORECASE,
                        )
                    except re.error as error:
                        raise ValidationError(
                            _(
                                'Existe una expresión regular inválida '
                                'en "%(field)s".\n\n'
                                'Patrón: %(pattern)s\n'
                                'Error: %(error)s'
                            ) % {
                                'field': label,
                                'pattern': pattern,
                                'error': str(error),
                            }
                        )

    @api.constrains('enterprise_ids')
    def _check_enterprise_ids(self):
        """
        Permitimos:
            367
            1.3.6.1.4.1.367
            ramas OID completas.
        """
        for record in self:
            for enterprise in _parse_lines(
                record.enterprise_ids
            ):
                enterprise = enterprise.strip('.')

                if not re.fullmatch(
                    r'\d+(?:\.\d+)*',
                    enterprise,
                ):
                    raise ValidationError(
                        _(
                            'Enterprise ID inválido:\n\n%s\n\n'
                            'Debe contener únicamente números y puntos.'
                        ) % enterprise
                    )

    @api.constrains(
        'supports_snmp_v1',
        'supports_snmp_v2c',
        'supports_snmp_v3',
        'preferred_snmp_version',
    )
    def _check_snmp_versions(self):
        for record in self:
            if not (
                record.supports_snmp_v1
                or record.supports_snmp_v2c
                or record.supports_snmp_v3
            ):
                raise ValidationError(
                    _(
                        'El perfil debe soportar por lo menos '
                        'una versión SNMP.'
                    )
                )

            if (
                record.preferred_snmp_version == '1'
                and not record.supports_snmp_v1
            ):
                raise ValidationError(
                    _('SNMP v1 está definido como preferido pero no soportado.')
                )

            if (
                record.preferred_snmp_version == '2c'
                and not record.supports_snmp_v2c
            ):
                raise ValidationError(
                    _('SNMP v2c está definido como preferido pero no soportado.')
                )

            if (
                record.preferred_snmp_version == '3'
                and not record.supports_snmp_v3
            ):
                raise ValidationError(
                    _('SNMP v3 está definido como preferido pero no soportado.')
                )

    @api.constrains(
        'tested_device_count',
        'successful_device_count',
        'failed_device_count',
    )
    def _check_validation_counts(self):
        for record in self:
            if (
                record.successful_device_count
                + record.failed_device_count
                > record.tested_device_count
            ):
                raise ValidationError(
                    _(
                        'La suma de pruebas exitosas y fallidas '
                        'no puede superar la cantidad total de '
                        'equipos probados.'
                    )
                )

    # ========================================================
    # ESTADOS
    # ========================================================

    def action_set_draft(self):
        self.write({
            'state': 'draft',
        })

        return True

    def action_set_testing(self):
        for record in self:
            if not record.metric_ids:
                raise UserError(
                    _(
                        'No puede poner el perfil "%s" en pruebas '
                        'porque todavía no contiene métricas SNMP.'
                    ) % record.display_name
                )

        self.write({
            'state': 'testing',
        })

        return True

    def action_validate(self):
        for record in self:
            active_metrics = record.metric_ids.filtered(
                lambda metric: metric.active
            )

            if not active_metrics:
                raise UserError(
                    _(
                        'No puede validar el perfil "%s" porque '
                        'no contiene métricas activas.'
                    ) % record.display_name
                )

            required_metrics = active_metrics.filtered(
                lambda metric: metric.required
            )

            if not required_metrics:
                raise UserError(
                    _(
                        'El perfil "%s" debe tener por lo menos '
                        'una métrica obligatoria antes de validarse.'
                    ) % record.display_name
                )

            record.write({
                'state': 'validated',
                'last_validation_date': fields.Datetime.now(),
                'last_validation_user_id': self.env.user.id,
            })

        return True

    def action_deprecate(self):
        self.write({
            'state': 'deprecated',
        })

        return True

    # ========================================================
    # REGISTRO DE RESULTADOS DE PRUEBA
    # ========================================================

    def register_test_result(
        self,
        success,
        notes=None,
    ):
        """
        Registra una validación realizada contra un equipo real.

        Se utilizará posteriormente desde discovery/agente.
        """
        for record in self:
            vals = {
                'tested_device_count':
                    record.tested_device_count + 1,

                'last_validation_date':
                    fields.Datetime.now(),

                'last_validation_user_id':
                    self.env.user.id,
            }

            if success:
                vals['successful_device_count'] = (
                    record.successful_device_count + 1
                )
            else:
                vals['failed_device_count'] = (
                    record.failed_device_count + 1
                )

            if notes:
                previous = record.validation_notes or ''

                timestamp = fields.Datetime.now()

                new_note = (
                    '[%s] %s'
                    % (
                        timestamp,
                        _clean_text(notes),
                    )
                )

                vals['validation_notes'] = (
                    previous + '\n' + new_note
                    if previous
                    else new_note
                )

            record.write(vals)

        return True

    # ========================================================
    # MATCHING DEL EQUIPO
    # ========================================================

    def get_device_match_result(
        self,
        brand_code=None,
        manufacturer=None,
        model=None,
        sysdescr=None,
        enterprise_id=None,
        firmware=None,
        technology=None,
    ):
        """
        Evalúa qué tan bien coincide este perfil con un equipo.

        Retorna un dict detallado para que podamos auditar por qué
        un perfil fue seleccionado o rechazado.

        Esto será utilizado por la API/agente.
        """
        self.ensure_one()

        brand_code = _normalize_code(
            brand_code or ''
        )

        manufacturer = _clean_text(
            manufacturer
        )

        model = _clean_text(
            model
        )

        sysdescr = _clean_text(
            sysdescr
        )

        enterprise_id = _normalize_enterprise(
            enterprise_id
        )

        firmware = _clean_text(
            firmware
        )

        technology = _clean_text(
            technology
        ).lower()

        result = {
            'profile_id': self.id,
            'profile_code': self.code,
            'profile_name': self.name,

            'matched': False,
            'score': 0,

            'minimum_score':
                self.minimum_match_score,

            'rejected': False,
            'rejection_reason': '',

            'matches': [],
            'warnings': [],
        }

        # ----------------------------------------------------
        # Perfil no utilizable
        # ----------------------------------------------------

        if not self.active:
            result['rejected'] = True
            result['rejection_reason'] = 'profile_inactive'
            return result

        if self.state == 'deprecated':
            result['rejected'] = True
            result['rejection_reason'] = 'profile_deprecated'
            return result

        # ----------------------------------------------------
        # Marca
        # ----------------------------------------------------

        configured_brand = _normalize_code(
            self.marca_codigo
            or self.marca_id.name
        )

        if brand_code:
            if brand_code != configured_brand:
                result['rejected'] = True
                result['rejection_reason'] = 'brand_mismatch'
                return result

            result['score'] += 100
            result['matches'].append('brand')

        else:
            result['warnings'].append(
                'brand_not_provided'
            )

        # ----------------------------------------------------
        # Tecnología
        # ----------------------------------------------------

        if (
            self.technology != 'any'
            and technology
        ):
            if technology != self.technology:
                result['rejected'] = True
                result['rejection_reason'] = 'technology_mismatch'
                return result

            result['score'] += 25
            result['matches'].append(
                'technology'
            )

        elif self.technology == 'any':
            result['score'] += 5

        # ----------------------------------------------------
        # Modelo excluido
        # ----------------------------------------------------

        excluded_patterns = _parse_lines(
            self.excluded_model_patterns
        )

        if (
            model
            and excluded_patterns
            and _any_regex_matches(
                excluded_patterns,
                model,
            )
        ):
            result['rejected'] = True
            result['rejection_reason'] = 'model_explicitly_excluded'
            return result

        # ----------------------------------------------------
        # Enterprise ID
        # ----------------------------------------------------

        enterprise_patterns = _parse_lines(
            self.enterprise_ids
        )

        enterprise_match = False

        if enterprise_patterns and enterprise_id:
            enterprise_match = any(
                _enterprise_matches(
                    configured,
                    enterprise_id,
                )
                for configured in enterprise_patterns
            )

            if enterprise_match:
                result['score'] += 70
                result['matches'].append(
                    'enterprise_id'
                )

            elif self.enterprise_strict:
                result['rejected'] = True
                result['rejection_reason'] = 'enterprise_mismatch'
                return result

            else:
                result['warnings'].append(
                    'enterprise_mismatch'
                )

        elif (
            self.enterprise_strict
            and enterprise_id
            and enterprise_patterns
        ):
            result['rejected'] = True
            result['rejection_reason'] = 'enterprise_mismatch'
            return result

        # ----------------------------------------------------
        # Fabricante
        # ----------------------------------------------------

        manufacturer_patterns = _parse_lines(
            self.manufacturer_patterns
        )

        if manufacturer_patterns and manufacturer:
            if _any_regex_matches(
                manufacturer_patterns,
                manufacturer,
            ):
                result['score'] += 30
                result['matches'].append(
                    'manufacturer'
                )
            else:
                result['warnings'].append(
                    'manufacturer_pattern_not_matched'
                )

        # ----------------------------------------------------
        # Modelo
        # ----------------------------------------------------

        model_patterns = _parse_lines(
            self.model_patterns
        )

        if model_patterns and model:
            if _any_regex_matches(
                model_patterns,
                model,
            ):
                result['score'] += 80
                result['matches'].append(
                    'model'
                )
            else:
                result['warnings'].append(
                    'model_pattern_not_matched'
                )

        # ----------------------------------------------------
        # sysDescr
        # ----------------------------------------------------

        sysdescr_patterns = _parse_lines(
            self.sysdescr_patterns
        )

        if sysdescr_patterns and sysdescr:
            if _any_regex_matches(
                sysdescr_patterns,
                sysdescr,
            ):
                result['score'] += 40
                result['matches'].append(
                    'sysdescr'
                )
            else:
                result['warnings'].append(
                    'sysdescr_pattern_not_matched'
                )

        # ----------------------------------------------------
        # Firmware
        # ----------------------------------------------------

        firmware_patterns = _parse_lines(
            self.firmware_patterns
        )

        if firmware_patterns and firmware:
            if _any_regex_matches(
                firmware_patterns,
                firmware,
            ):
                result['score'] += 15
                result['matches'].append(
                    'firmware'
                )
            else:
                result['warnings'].append(
                    'firmware_pattern_not_matched'
                )

        # ----------------------------------------------------
        # Perfil general
        # ----------------------------------------------------

        if self.is_default_for_brand:
            result['score'] += 5
            result['matches'].append(
                'brand_default_profile'
            )

        # ----------------------------------------------------
        # Prioridad
        # ----------------------------------------------------

        result['score'] += max(
            self.priority,
            0,
        )

        # ----------------------------------------------------
        # Resultado final
        # ----------------------------------------------------

        result['matched'] = (
            result['score']
            >= self.minimum_match_score
        )

        if not result['matched']:
            result['rejection_reason'] = (
                'score_below_minimum'
            )

        return result

    # ========================================================
    # BUSCAR MEJOR PERFIL
    # ========================================================

    @api.model
    def find_best_profile(
        self,
        brand_code=None,
        manufacturer=None,
        model=None,
        sysdescr=None,
        enterprise_id=None,
        firmware=None,
        technology=None,
        include_testing=True,
    ):
        """
        Selecciona el mejor perfil disponible para un equipo.

        El agente NO debe elegir por sí mismo qué perfil utilizar.
        Odoo toma la decisión y devuelve el resultado.
        """
        domain = [
            ('active', '=', True),
        ]

        allowed_states = ['validated']

        if include_testing:
            allowed_states.append('testing')

        domain.append(
            ('state', 'in', allowed_states)
        )

        brand_code_normalized = _normalize_code(
            brand_code or ''
        )

        if brand_code_normalized:
            domain.append(
                (
                    'marca_codigo',
                    '=',
                    brand_code_normalized,
                )
            )

        profiles = self.search(
            domain,
            order=(
                'priority desc, '
                'is_default_for_brand asc, '
                'sequence asc, id asc'
            ),
        )

        evaluated = []

        for profile in profiles:
            result = profile.get_device_match_result(
                brand_code=brand_code,
                manufacturer=manufacturer,
                model=model,
                sysdescr=sysdescr,
                enterprise_id=enterprise_id,
                firmware=firmware,
                technology=technology,
            )

            if result.get('matched'):
                evaluated.append(
                    (
                        result.get('score', 0),
                        profile.priority,
                        profile.id,
                        profile,
                        result,
                    )
                )

        if not evaluated:
            return {
                'profile': self.browse(),
                'match': False,
                'evaluated_count': len(profiles),
            }

        evaluated.sort(
            key=lambda item: (
                item[0],
                item[1],
                item[2],
            ),
            reverse=True,
        )

        best = evaluated[0]

        return {
            'profile': best[3],
            'match': best[4],
            'evaluated_count': len(profiles),
        }

    # ========================================================
    # PAYLOAD PARA EL AGENTE
    # ========================================================

    def get_agent_payload(self):
        """
        Devuelve la configuración pública que podrá consumir el agente.

        IMPORTANTE:
        No contiene communities, passwords ni credenciales SNMP.

        Cada métrica implementará posteriormente:
            metric.get_agent_payload()
        """
        self.ensure_one()

        metrics = self.metric_ids.filtered(
            lambda metric: metric.active
        ).sorted(
            key=lambda metric: (
                metric.sequence,
                metric.id,
            )
        )

        payload = {
            'profile': {
                'id': self.id,
                'code': self.code,
                'name': self.name,

                'brand': {
                    'id': self.marca_id.id,
                    'code': self.marca_codigo,
                    'name': self.marca_id.name,
                },

                'family': self.family or '',
                'series': self.series or '',
                'technology': self.technology,

                'version': self.version,
                'revision': self.revision,

                'state': self.state,
                'confidence': self.confidence,

                'polling_strategy':
                    self.polling_strategy,

                'allow_fallback_discovery':
                    self.allow_fallback_discovery,

                'preserve_raw_data':
                    self.preserve_raw_data,

                'preferred_snmp_version':
                    self.preferred_snmp_version,

                'supported_snmp_versions': {
                    'v1': self.supports_snmp_v1,
                    'v2c': self.supports_snmp_v2c,
                    'v3': self.supports_snmp_v3,
                },
            },

            'metrics': [
                metric.get_agent_payload()
                for metric in metrics
            ],
        }

        # Auditoría sin generar tracking/chatter innecesario.
        self.sudo().with_context(
            tracking_disable=True,
            mail_notrack=True,
        ).write({
            'last_agent_request':
                fields.Datetime.now(),

            'agent_request_count':
                self.agent_request_count + 1,
        })

        return payload

    # ========================================================
    # INFORMACIÓN DE DEBUG
    # ========================================================

    def get_profile_summary(self):
        """
        Resumen técnico útil para API, logs y diagnóstico.
        """
        self.ensure_one()

        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,

            'brand_code': self.marca_codigo,
            'brand_name': self.marca_id.name,

            'family': self.family or '',
            'series': self.series or '',
            'technology': self.technology,

            'version': self.version,
            'revision': self.revision,

            'state': self.state,
            'confidence': self.confidence,

            'priority': self.priority,

            'metric_count': self.metric_count,
            'enabled_metric_count':
                self.enabled_metric_count,
            'required_metric_count':
                self.required_metric_count,

            'tested_device_count':
                self.tested_device_count,

            'successful_device_count':
                self.successful_device_count,

            'failed_device_count':
                self.failed_device_count,

            'success_rate':
                self.success_rate,
        }