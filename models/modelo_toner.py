# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ModeloToner(models.Model):
    _name = 'modelo.toner'
    _description = 'Modelo de tóner'
    _order = 'marca_id, name, color'
    _rec_name = 'display_name'

    # =========================================================
    # IDENTIFICACIÓN
    # =========================================================

    name = fields.Char(
        string='Modelo de tóner',
        required=True,
        index=True,
        tracking=True,
        help=(
            'Referencia comercial del tóner. '
            'Ejemplo: TN-324K, MP 6054 Black, T-302K.'
        ),
    )

    display_name = fields.Char(
        string='Nombre mostrado',
        compute='_compute_display_name',
        store=True,
    )

    marca_id = fields.Many2one(
        'marca.marca',
        string='Marca',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
    )

    color = fields.Selection(
        [
            ('black', 'Negro'),
            ('cyan', 'Cian'),
            ('magenta', 'Magenta'),
            ('yellow', 'Amarillo'),
            ('white', 'Blanco'),
        ],
        string='Color',
        required=True,
        index=True,
        tracking=True,
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
    )

    # =========================================================
    # CÓDIGOS Y REFERENCIAS
    # =========================================================

    codigo_parte = fields.Char(
        string='Código de parte principal',
        index=True,
        tracking=True,
        help=(
            'Código OEM o número de parte principal del tóner. '
            'Ejemplo: A8DA130.'
        ),
    )

    codigo_parte_alternativo = fields.Char(
        string='Código de parte alternativo',
        index=True,
        tracking=True,
        help=(
            'Código alternativo, regional o equivalente del fabricante.'
        ),
    )

    codigo_fabricante = fields.Char(
        string='Código del fabricante',
        index=True,
        help='Código adicional usado por el fabricante o catálogo.',
    )

    referencia_alternativa = fields.Char(
        string='Referencia alternativa',
        help=(
            'Nombre o referencia comercial alternativa del mismo tóner.'
        ),
    )

    # =========================================================
    # RENDIMIENTO / DURACIÓN
    # =========================================================

    duracion_fabricante = fields.Integer(
        string='Duración fabricante (páginas)',
        default=0,
        tracking=True,
        help=(
            'Rendimiento oficial indicado por el fabricante '
            'bajo sus condiciones de cobertura.'
        ),
    )

    duracion_referencial = fields.Integer(
        string='Duración referencial (páginas)',
        default=0,
        tracking=True,
        help=(
            'Duración utilizada internamente como referencia '
            'para análisis de consumo.'
        ),
    )

    duracion_aplicable = fields.Integer(
        string='Duración aplicable',
        compute='_compute_duracion_aplicable',
        store=True,
        help=(
            'Usa primero la duración referencial. '
            'Si no existe, utiliza la duración del fabricante.'
        ),
    )

    cobertura_referencia = fields.Float(
        string='Cobertura de referencia (%)',
        digits=(16, 2),
        default=5.0,
        help=(
            'Cobertura utilizada como referencia por el fabricante, '
            'cuando corresponda.'
        ),
    )

    # =========================================================
    # CAPACIDAD / PRESENTACIÓN
    # =========================================================

    capacidad_gramos = fields.Float(
        string='Capacidad aproximada (g)',
        digits=(16, 2),
        help='Cantidad aproximada de tóner en gramos.',
    )

    tipo_presentacion = fields.Selection(
        [
            ('cartucho', 'Cartucho'),
            ('botella', 'Botella'),
            ('tubo', 'Tubo'),
            ('kit', 'Kit'),
            ('otro', 'Otro'),
        ],
        string='Presentación',
        default='cartucho',
    )

    descripcion_presentacion = fields.Char(
        string='Detalle de presentación',
    )

    # =========================================================
    # INFORMACIÓN DE ORIGEN
    # =========================================================

    fuente_informacion = fields.Selection(
        [
            ('fabricante', 'Ficha del fabricante'),
            ('manual', 'Manual técnico'),
            ('catalogo', 'Catálogo de suministros'),
            ('proveedor', 'Información del proveedor'),
            ('interno', 'Validación interna'),
            ('pendiente', 'Pendiente de verificar'),
        ],
        string='Fuente de información',
        default='pendiente',
        tracking=True,
    )

    fecha_verificacion = fields.Date(
        string='Fecha de verificación',
        tracking=True,
    )

    url_referencia = fields.Char(
        string='URL de referencia',
        help='Enlace a ficha técnica, catálogo o fuente utilizada.',
    )

    observaciones = fields.Text(
        string='Observaciones',
        help=(
            'Notas sobre referencias regionales, equivalencias, '
            'rendimiento o información pendiente.'
        ),
    )

    # =========================================================
    # CONTROL INTERNO
    # =========================================================

    usar_para_analisis_consumo = fields.Boolean(
        string='Usar para análisis de consumo',
        default=True,
        help=(
            'Si está activo, este tóner puede utilizarse como '
            'referencia para validar rendimiento.'
        ),
    )

    validado_internamente = fields.Boolean(
        string='Validado internamente',
        default=False,
        tracking=True,
    )

    fecha_validacion_interna = fields.Date(
        string='Fecha de validación interna',
    )

    usuario_validacion_id = fields.Many2one(
        'res.users',
        string='Validado por',
        readonly=True,
        copy=False,
    )

    # =========================================================
    # COMPATIBILIDAD
    # =========================================================

    modelo_maquina_ids = fields.Many2many(
        'modelo.maquina',
        'modelo_toner_maquina_rel',
        'toner_id',
        'modelo_maquina_id',
        string='Modelos de máquina compatibles',
        help=(
            'Modelos de máquina que pueden utilizar este tóner.'
        ),
    )

    modelo_maquina_count = fields.Integer(
        string='Modelos compatibles',
        compute='_compute_modelo_maquina_count',
    )

    # =========================================================
    # CAMPOS CALCULADOS
    # =========================================================

    @api.depends(
        'marca_id',
        'name',
        'color',
        'codigo_parte',
    )
    def _compute_display_name(self):
        color_labels = dict(
            self._fields['color'].selection
        )

        for record in self:
            parts = []

            if record.marca_id:
                parts.append(record.marca_id.name)

            if record.name:
                parts.append(record.name)

            if record.color:
                parts.append(
                    color_labels.get(record.color, record.color)
                )

            if record.codigo_parte:
                parts.append(record.codigo_parte)

            record.display_name = ' / '.join(parts) or _('Nuevo tóner')

    @api.depends(
        'duracion_referencial',
        'duracion_fabricante',
    )
    def _compute_duracion_aplicable(self):
        for record in self:
            record.duracion_aplicable = (
                record.duracion_referencial
                or record.duracion_fabricante
                or 0
            )

    @api.depends('modelo_maquina_ids')
    def _compute_modelo_maquina_count(self):
        for record in self:
            record.modelo_maquina_count = len(
                record.modelo_maquina_ids
            )

    # =========================================================
    # ONCHANGE
    # =========================================================

    @api.onchange('duracion_fabricante')
    def _onchange_duracion_fabricante(self):
        for record in self:
            if (
                record.duracion_fabricante
                and not record.duracion_referencial
            ):
                record.duracion_referencial = (
                    record.duracion_fabricante
                )

    @api.onchange('validado_internamente')
    def _onchange_validado_internamente(self):
        for record in self:
            if record.validado_internamente:
                record.fecha_validacion_interna = (
                    fields.Date.today()
                )
                record.usuario_validacion_id = self.env.user
            else:
                record.fecha_validacion_interna = False
                record.usuario_validacion_id = False

    # =========================================================
    # VALIDACIONES
    # =========================================================

    @api.constrains(
        'duracion_fabricante',
        'duracion_referencial',
    )
    def _check_duraciones(self):
        for record in self:
            if record.duracion_fabricante < 0:
                raise ValidationError(
                    _(
                        'La duración del fabricante '
                        'no puede ser negativa.'
                    )
                )

            if record.duracion_referencial < 0:
                raise ValidationError(
                    _(
                        'La duración referencial '
                        'no puede ser negativa.'
                    )
                )

    @api.constrains('capacidad_gramos')
    def _check_capacidad_gramos(self):
        for record in self:
            if record.capacidad_gramos < 0:
                raise ValidationError(
                    _(
                        'La capacidad en gramos '
                        'no puede ser negativa.'
                    )
                )

    @api.constrains('cobertura_referencia')
    def _check_cobertura_referencia(self):
        for record in self:
            if (
                record.cobertura_referencia < 0
                or record.cobertura_referencia > 100
            ):
                raise ValidationError(
                    _(
                        'La cobertura de referencia debe '
                        'estar entre 0 y 100 %.'
                    )
                )

    @api.constrains(
        'marca_id',
        'name',
        'color',
        'codigo_parte',
    )
    def _check_duplicate_toner(self):
        for record in self:
            domain = [
                ('id', '!=', record.id),
                ('marca_id', '=', record.marca_id.id),
                ('name', '=ilike', record.name),
                ('color', '=', record.color),
            ]

            duplicate = self.search(
                domain,
                limit=1,
            )

            if duplicate:
                raise ValidationError(
                    _(
                        'Ya existe el tóner "%(toner)s" '
                        'para la marca "%(brand)s" '
                        'y color "%(color)s".'
                    )
                    % {
                        'toner': record.name,
                        'brand': record.marca_id.name,
                        'color': dict(
                            self._fields['color'].selection
                        ).get(
                            record.color,
                            record.color,
                        ),
                    }
                )

    # =========================================================
    # ACCIONES
    # =========================================================

    def action_validar_internamente(self):
        for record in self:
            record.write(
                {
                    'validado_internamente': True,
                    'fecha_validacion_interna': fields.Date.today(),
                    'usuario_validacion_id': self.env.user.id,
                }
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tóner validado'),
                'message': _(
                    'La información del modelo de tóner '
                    'fue marcada como validada.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_view_modelos_maquina(self):
        self.ensure_one()

        return {
            'name': _(
                'Modelos compatibles - %s'
            ) % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'modelo.maquina',
            'view_mode': 'list,form',
            'domain': [
                ('id', 'in', self.modelo_maquina_ids.ids)
            ],
            'context': {
                'create': False,
            },
        }