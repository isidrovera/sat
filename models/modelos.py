# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ModelosMaquin(models.Model):
    _name = 'modelo.maquina'
    _description = 'Modelos de máquinas de impresión y multifuncionales'

    # =========================================================
    # INFORMACIÓN PRINCIPAL
    # =========================================================

    name = fields.Char(
        string='Modelo de máquina',
        required=True,
        tracking=True,
    )

    marca_id = fields.Many2one(
        'marca.marca',
        string='Marca',
        required=True,
    )

    tipo_id = fields.Selection(
        [
            ('color', 'Color'),
            ('monocromatica', 'Monocromática'),
        ],
        string='Tecnología',
        required=True,
        tracking=True,
    )

    precio_venta = fields.Float(
        string='Precio de venta',
        required=True,
    )

    tipo_maquina_id = fields.Many2one(
        'tipo.maquina',
        string='Tipo de máquina',
        required=True,
        tracking=True,
    )

    @api.model
    def _default_currency_id(self):
        currency = self.env['res.currency'].search(
            [('name', '=', 'USD')],
            limit=1,
        )
        return currency.id if currency else False

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=_default_currency_id,
    )

    _sql_constraints = [
        (
            'unique_name',
            'unique(name)',
            'El modelo de máquina que intenta agregar ya existe.',
        ),
    ]

    # =========================================================
    # CATÁLOGO MAESTRO DE TÓNER
    # =========================================================

    toner_black_id = fields.Many2one(
        'modelo.toner',
        string='Tóner negro',
        ondelete='restrict',
        index=True,
        tracking=True,
        domain="[('marca_id', '=', marca_id), ('color', '=', 'black'), ('active', '=', True)]",
    )

    toner_cyan_id = fields.Many2one(
        'modelo.toner',
        string='Tóner cian',
        ondelete='restrict',
        index=True,
        tracking=True,
        domain="[('marca_id', '=', marca_id), ('color', '=', 'cyan'), ('active', '=', True)]",
    )

    toner_magenta_id = fields.Many2one(
        'modelo.toner',
        string='Tóner magenta',
        ondelete='restrict',
        index=True,
        tracking=True,
        domain="[('marca_id', '=', marca_id), ('color', '=', 'magenta'), ('active', '=', True)]",
    )

    toner_yellow_id = fields.Many2one(
        'modelo.toner',
        string='Tóner amarillo',
        ondelete='restrict',
        index=True,
        tracking=True,
        domain="[('marca_id', '=', marca_id), ('color', '=', 'yellow'), ('active', '=', True)]",
    )

    # =========================================================
    # CAMPOS EXISTENTES - SE MANTIENEN SIN CAMBIAR NOMBRES/TIPOS
    # =========================================================

    toner_modelo_black = fields.Char(
        string='Modelo de tóner negro',
        index=True,
    )
    toner_codigo_parte_black = fields.Char(
        string='Código de parte negro',
        index=True,
    )

    toner_modelo_cyan = fields.Char(
        string='Modelo de tóner cian',
        index=True,
    )
    toner_codigo_parte_cyan = fields.Char(
        string='Código de parte cian',
        index=True,
    )

    toner_modelo_magenta = fields.Char(
        string='Modelo de tóner magenta',
        index=True,
    )
    toner_codigo_parte_magenta = fields.Char(
        string='Código de parte magenta',
        index=True,
    )

    toner_modelo_yellow = fields.Char(
        string='Modelo de tóner amarillo',
        index=True,
    )
    toner_codigo_parte_yellow = fields.Char(
        string='Código de parte amarillo',
        index=True,
    )

    durabilidad_toner_black = fields.Integer(
        string='Durabilidad tóner negro (páginas)',
        default=0,
    )
    durabilidad_toner_cyan = fields.Integer(
        string='Durabilidad tóner cian (páginas)',
        default=0,
    )
    durabilidad_toner_magenta = fields.Integer(
        string='Durabilidad tóner magenta (páginas)',
        default=0,
    )
    durabilidad_toner_yellow = fields.Integer(
        string='Durabilidad tóner amarillo (páginas)',
        default=0,
    )

    toner_fuente_informacion = fields.Selection(
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
    )

    toner_fecha_verificacion = fields.Date(
        string='Fecha de verificación',
    )

    toner_observaciones = fields.Text(
        string='Observaciones de tóner',
    )

    stock_minimo_black = fields.Integer(
        string='Stock mínimo tóner negro',
        default=1,
    )
    stock_minimo_cyan = fields.Integer(
        string='Stock mínimo tóner cian',
        default=1,
    )
    stock_minimo_magenta = fields.Integer(
        string='Stock mínimo tóner magenta',
        default=1,
    )
    stock_minimo_yellow = fields.Integer(
        string='Stock mínimo tóner amarillo',
        default=1,
    )

    tiempo_entrega_dias = fields.Integer(
        string='Tiempo de entrega (días)',
        default=2,
    )

    margen_seguridad_dias = fields.Integer(
        string='Margen de seguridad (días)',
        default=3,
    )

    tiempo_total_prevencion = fields.Integer(
        string='Tiempo total de prevención',
        compute='_compute_tiempo_total_prevencion',
        store=True,
    )

    alerta_stock_critico = fields.Boolean(
        string='Alertas de stock crítico',
        default=True,
    )

    alerta_consumo_alto = fields.Boolean(
        string='Alertas de consumo alto',
        default=True,
    )

    gestionar_toner_automatico = fields.Boolean(
        string='Gestión automática de tóner',
        default=True,
    )

    mostrar_toner_color = fields.Boolean(
        string='Mostrar tóner color',
        compute='_compute_mostrar_toner_color',
    )

    resumen_configuracion_toner = fields.Html(
        string='Resumen de configuración',
        compute='_compute_resumen_configuracion_toner',
    )

    equipos_activos_count = fields.Integer(
        string='Equipos activos',
        compute='_compute_equipos_activos_count',
        store=True,
    )

    # =========================================================
    # MAPEO Y SINCRONIZACIÓN CON modelo.toner
    # =========================================================

    TONER_COLOR_CONFIG = {
        'black': {
            'relation': 'toner_black_id',
            'legacy_model': 'toner_modelo_black',
            'legacy_part': 'toner_codigo_parte_black',
            'legacy_duration': 'durabilidad_toner_black',
        },
        'cyan': {
            'relation': 'toner_cyan_id',
            'legacy_model': 'toner_modelo_cyan',
            'legacy_part': 'toner_codigo_parte_cyan',
            'legacy_duration': 'durabilidad_toner_cyan',
        },
        'magenta': {
            'relation': 'toner_magenta_id',
            'legacy_model': 'toner_modelo_magenta',
            'legacy_part': 'toner_codigo_parte_magenta',
            'legacy_duration': 'durabilidad_toner_magenta',
        },
        'yellow': {
            'relation': 'toner_yellow_id',
            'legacy_model': 'toner_modelo_yellow',
            'legacy_part': 'toner_codigo_parte_yellow',
            'legacy_duration': 'durabilidad_toner_yellow',
        },
    }

    @api.model
    def _toner_display_value(self, value):
        return value or 'No configurado'

    @api.model
    def _get_toner_duration(self, toner):
        if not toner:
            return 0

        if 'duracion_referencial' in toner._fields:
            value = int(toner.duracion_referencial or 0)
            if value > 0:
                return value

        if 'duracion_fabricante' in toner._fields:
            value = int(toner.duracion_fabricante or 0)
            if value > 0:
                return value

        if 'duracion_aplicable' in toner._fields:
            return int(toner.duracion_aplicable or 0)

        return 0

    @api.model
    def _get_legacy_values_from_toner(self, toner, color):
        config = self.TONER_COLOR_CONFIG[color]

        if not toner:
            return {
                config['legacy_model']: False,
                config['legacy_part']: False,
                config['legacy_duration']: 0,
            }

        return {
            config['legacy_model']: toner.name or False,
            config['legacy_part']: toner.codigo_parte or False,
            config['legacy_duration']: self._get_toner_duration(toner),
        }

    @api.model
    def _inject_toner_values(self, vals):
        vals = dict(vals)

        for color, config in self.TONER_COLOR_CONFIG.items():
            relation_field = config['relation']

            if relation_field not in vals:
                continue

            toner_id = vals.get(relation_field)
            toner = (
                self.env['modelo.toner'].browse(toner_id).exists()
                if toner_id
                else self.env['modelo.toner']
            )

            vals.update(
                self._get_legacy_values_from_toner(
                    toner,
                    color,
                )
            )

        return vals

    def _apply_toner_to_legacy_fields(self, color):
        self.ensure_one()

        config = self.TONER_COLOR_CONFIG[color]
        toner = self[config['relation']]
        values = self._get_legacy_values_from_toner(toner, color)

        for field_name, value in values.items():
            self[field_name] = value

    # =========================================================
    # ONCHANGE
    # =========================================================

    @api.onchange('toner_black_id')
    def _onchange_toner_black_id(self):
        for record in self:
            record._apply_toner_to_legacy_fields('black')

    @api.onchange('toner_cyan_id')
    def _onchange_toner_cyan_id(self):
        for record in self:
            record._apply_toner_to_legacy_fields('cyan')

    @api.onchange('toner_magenta_id')
    def _onchange_toner_magenta_id(self):
        for record in self:
            record._apply_toner_to_legacy_fields('magenta')

    @api.onchange('toner_yellow_id')
    def _onchange_toner_yellow_id(self):
        for record in self:
            record._apply_toner_to_legacy_fields('yellow')

    @api.onchange('marca_id')
    def _onchange_marca_toners(self):
        for record in self:
            for config in self.TONER_COLOR_CONFIG.values():
                toner = record[config['relation']]
                if (
                    toner
                    and record.marca_id
                    and toner.marca_id != record.marca_id
                ):
                    record[config['relation']] = False

    @api.onchange('tipo_id')
    def _onchange_tipo_id_toners(self):
        for record in self:
            if record.tipo_id == 'monocromatica':
                record.toner_cyan_id = False
                record.toner_magenta_id = False
                record.toner_yellow_id = False

    # =========================================================
    # CREATE / WRITE
    # =========================================================

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [
            self._inject_toner_values(vals)
            for vals in vals_list
        ]
        return super().create(vals_list)

    def write(self, vals):
        vals = self._inject_toner_values(vals)
        return super().write(vals)

    # =========================================================
    # COMPUTES EXISTENTES
    # =========================================================

    @api.depends('tiempo_entrega_dias', 'margen_seguridad_dias')
    def _compute_tiempo_total_prevencion(self):
        for record in self:
            record.tiempo_total_prevencion = (
                (record.tiempo_entrega_dias or 0)
                + (record.margen_seguridad_dias or 0)
            )

    @api.depends('tipo_id')
    def _compute_mostrar_toner_color(self):
        for record in self:
            record.mostrar_toner_color = record.tipo_id == 'color'

    @api.depends(
        'tipo_id',
        'toner_black_id',
        'toner_cyan_id',
        'toner_magenta_id',
        'toner_yellow_id',
        'toner_modelo_black',
        'toner_codigo_parte_black',
        'toner_modelo_cyan',
        'toner_codigo_parte_cyan',
        'toner_modelo_magenta',
        'toner_codigo_parte_magenta',
        'toner_modelo_yellow',
        'toner_codigo_parte_yellow',
        'durabilidad_toner_black',
        'durabilidad_toner_cyan',
        'durabilidad_toner_magenta',
        'durabilidad_toner_yellow',
        'stock_minimo_black',
        'stock_minimo_cyan',
        'stock_minimo_magenta',
        'stock_minimo_yellow',
        'tiempo_entrega_dias',
        'margen_seguridad_dias',
        'tiempo_total_prevencion',
        'alerta_stock_critico',
        'alerta_consumo_alto',
        'gestionar_toner_automatico',
        'toner_fuente_informacion',
        'toner_fecha_verificacion',
    )
    def _compute_resumen_configuracion_toner(self):
        selection_source = dict(
            self._fields['toner_fuente_informacion'].selection
        )

        for record in self:
            tipo_display = (
                'Color'
                if record.tipo_id == 'color'
                else 'Monocromática'
            )

            html = (
                '<div style="font-family: Arial, sans-serif; line-height: 1.5;">'
                f'<h4 style="margin: 0 0 14px 0;">'
                f'Configuración de tóner — {tipo_display}</h4>'
            )

            html += '<div style="margin-bottom: 12px;">'
            html += '<strong>Tóner negro</strong><br/>'
            if record.toner_black_id:
                html += f'Catálogo maestro: {record.toner_black_id.display_name}<br/>'
            html += (
                f'Referencia: {record._toner_display_value(record.toner_modelo_black)}<br/>'
                f'Código de parte: {record._toner_display_value(record.toner_codigo_parte_black)}<br/>'
                f'Duración aplicable: {record.durabilidad_toner_black or 0:,} páginas<br/>'
                f'Stock mínimo: {record.stock_minimo_black or 0} unidad(es)'
            )
            html += '</div>'

            if record.tipo_id == 'color':
                color_data = [
                    (
                        'Cian',
                        record.toner_cyan_id,
                        record.toner_modelo_cyan,
                        record.toner_codigo_parte_cyan,
                        record.durabilidad_toner_cyan,
                        record.stock_minimo_cyan,
                    ),
                    (
                        'Magenta',
                        record.toner_magenta_id,
                        record.toner_modelo_magenta,
                        record.toner_codigo_parte_magenta,
                        record.durabilidad_toner_magenta,
                        record.stock_minimo_magenta,
                    ),
                    (
                        'Amarillo',
                        record.toner_yellow_id,
                        record.toner_modelo_yellow,
                        record.toner_codigo_parte_yellow,
                        record.durabilidad_toner_yellow,
                        record.stock_minimo_yellow,
                    ),
                ]

                for color_name, toner, model_name, part, duration, stock in color_data:
                    html += '<div style="margin-bottom: 12px;">'
                    html += f'<strong>Tóner {color_name}</strong><br/>'
                    if toner:
                        html += f'Catálogo maestro: {toner.display_name}<br/>'
                    html += (
                        f'Referencia: {record._toner_display_value(model_name)}<br/>'
                        f'Código de parte: {record._toner_display_value(part)}<br/>'
                        f'Duración aplicable: {duration or 0:,} páginas<br/>'
                        f'Stock mínimo: {stock or 0} unidad(es)'
                    )
                    html += '</div>'

            html += '<hr/>'
            html += '<div style="margin-bottom: 12px;">'
            html += '<strong>Configuración logística</strong><br/>'
            html += (
                f'Tiempo de entrega: {record.tiempo_entrega_dias or 0} día(s)<br/>'
                f'Margen de seguridad: {record.margen_seguridad_dias or 0} día(s)<br/>'
                f'Total de prevención: {record.tiempo_total_prevencion or 0} día(s)'
            )
            html += '</div>'

            source_label = selection_source.get(
                record.toner_fuente_informacion,
                'Pendiente de verificar',
            )
            html += '<div style="margin-bottom: 12px;">'
            html += '<strong>Verificación</strong><br/>'
            html += (
                f'Fuente: {source_label}<br/>'
                f'Fecha: {record.toner_fecha_verificacion or "Sin verificar"}'
            )
            html += '</div>'

            html += '<div>'
            html += '<strong>Alertas</strong><br/>'
            html += (
                'Stock crítico: '
                f'{"Activo" if record.alerta_stock_critico else "Inactivo"}<br/>'
                'Consumo alto: '
                f'{"Activo" if record.alerta_consumo_alto else "Inactivo"}<br/>'
                'Gestión automática: '
                f'{"Activo" if record.gestionar_toner_automatico else "Inactivo"}'
            )
            html += '</div></div>'

            record.resumen_configuracion_toner = html

    @api.depends('name')
    def _compute_equipos_activos_count(self):
        for record in self:
            record.equipos_activos_count = self.env['alquiler'].search_count(
                [
                    ('name', '=', record.id),
                    ('estado_alquiler_id', '=', 'alquilada'),
                ]
            )

    # =========================================================
    # VALIDACIONES
    # =========================================================

    @api.constrains(
        'toner_black_id',
        'toner_cyan_id',
        'toner_magenta_id',
        'toner_yellow_id',
        'marca_id',
        'tipo_id',
    )
    def _check_toner_catalog_relations(self):
        labels = {
            'black': _('Negro'),
            'cyan': _('Cian'),
            'magenta': _('Magenta'),
            'yellow': _('Amarillo'),
        }

        for record in self:
            for color, config in self.TONER_COLOR_CONFIG.items():
                toner = record[config['relation']]

                if not toner:
                    continue

                if toner.color != color:
                    raise ValidationError(
                        _(
                            'El tóner "%(toner)s" no corresponde al color %(color)s.'
                        )
                        % {
                            'toner': toner.display_name,
                            'color': labels[color],
                        }
                    )

                if record.marca_id and toner.marca_id != record.marca_id:
                    raise ValidationError(
                        _(
                            'El tóner "%(toner)s" pertenece a la marca '
                            '"%(toner_brand)s", pero el modelo pertenece a "%(machine_brand)s".'
                        )
                        % {
                            'toner': toner.display_name,
                            'toner_brand': toner.marca_id.name,
                            'machine_brand': record.marca_id.name,
                        }
                    )

            if record.tipo_id == 'monocromatica' and (
                record.toner_cyan_id
                or record.toner_magenta_id
                or record.toner_yellow_id
            ):
                raise ValidationError(
                    _(
                        'Un modelo monocromático no puede tener asociados '
                        'tóners Cian, Magenta o Amarillo.'
                    )
                )

    @api.constrains(
        'durabilidad_toner_black',
        'durabilidad_toner_cyan',
        'durabilidad_toner_magenta',
        'durabilidad_toner_yellow',
    )
    def _check_durabilidad_toner(self):
        for record in self:
            values = [
                (record.durabilidad_toner_black, _('La durabilidad del tóner negro no puede ser negativa.')),
                (record.durabilidad_toner_cyan, _('La durabilidad del tóner cian no puede ser negativa.')),
                (record.durabilidad_toner_magenta, _('La durabilidad del tóner magenta no puede ser negativa.')),
                (record.durabilidad_toner_yellow, _('La durabilidad del tóner amarillo no puede ser negativa.')),
            ]
            for duration, message in values:
                if duration < 0:
                    raise ValidationError(message)

    @api.constrains(
        'stock_minimo_black',
        'stock_minimo_cyan',
        'stock_minimo_magenta',
        'stock_minimo_yellow',
    )
    def _check_stock_minimo(self):
        for record in self:
            values = [
                (record.stock_minimo_black, _('El stock mínimo negro no puede ser negativo.')),
                (record.stock_minimo_cyan, _('El stock mínimo cian no puede ser negativo.')),
                (record.stock_minimo_magenta, _('El stock mínimo magenta no puede ser negativo.')),
                (record.stock_minimo_yellow, _('El stock mínimo amarillo no puede ser negativo.')),
            ]
            for value, message in values:
                if value < 0:
                    raise ValidationError(message)

    @api.constrains('tiempo_entrega_dias', 'margen_seguridad_dias')
    def _check_tiempos(self):
        for record in self:
            if record.tiempo_entrega_dias < 0:
                raise ValidationError(_('El tiempo de entrega no puede ser negativo.'))
            if record.margen_seguridad_dias < 0:
                raise ValidationError(_('El margen de seguridad no puede ser negativo.'))

    @api.constrains(
        'tipo_id',
        'toner_modelo_black',
        'toner_codigo_parte_black',
        'durabilidad_toner_black',
    )
    def _check_toner_black_configuration(self):
        for record in self:
            if (
                record.durabilidad_toner_black > 0
                and not record.toner_modelo_black
                and not record.toner_codigo_parte_black
            ):
                raise ValidationError(
                    _(
                        'Ha indicado una duración para el tóner negro, '
                        'pero no registró su modelo ni su código de parte.'
                    )
                )

    # =========================================================
    # ACCIONES
    # =========================================================

    def action_actualizar_desde_modelos_toner(self):
        for record in self:
            values = {}

            for color, config in self.TONER_COLOR_CONFIG.items():
                toner = record[config['relation']]
                if toner:
                    values.update(
                        record._get_legacy_values_from_toner(
                            toner,
                            color,
                        )
                    )

            if values:
                record.write(values)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tóner actualizado'),
                'message': _(
                    'Se actualizaron referencias, códigos de parte y '
                    'duraciones desde el catálogo maestro de tóner.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_view_equipos_modelo(self):
        self.ensure_one()

        return {
            'name': _('Equipos - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'alquiler',
            'view_mode': 'list,form',
            'domain': [('name', '=', self.id)],
            'context': {
                'default_name': self.id,
                'create': False,
            },
        }

    def action_configurar_valores_predeterminados(self):
        self.ensure_one()

        if self.tipo_id == 'monocromatica':
            self.write(
                {
                    'durabilidad_toner_black': 3000,
                    'stock_minimo_black': 2,
                    'durabilidad_toner_cyan': 0,
                    'durabilidad_toner_magenta': 0,
                    'durabilidad_toner_yellow': 0,
                    'stock_minimo_cyan': 0,
                    'stock_minimo_magenta': 0,
                    'stock_minimo_yellow': 0,
                    'tiempo_entrega_dias': 2,
                    'margen_seguridad_dias': 3,
                    'alerta_stock_critico': True,
                    'alerta_consumo_alto': True,
                    'gestionar_toner_automatico': True,
                }
            )

        elif self.tipo_id == 'color':
            self.write(
                {
                    'durabilidad_toner_black': 2500,
                    'durabilidad_toner_cyan': 2000,
                    'durabilidad_toner_magenta': 2000,
                    'durabilidad_toner_yellow': 2000,
                    'stock_minimo_black': 2,
                    'stock_minimo_cyan': 1,
                    'stock_minimo_magenta': 1,
                    'stock_minimo_yellow': 1,
                    'tiempo_entrega_dias': 3,
                    'margen_seguridad_dias': 5,
                    'alerta_stock_critico': True,
                    'alerta_consumo_alto': True,
                    'gestionar_toner_automatico': True,
                }
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuración aplicada'),
                'message': _(
                    'Se aplicaron valores iniciales. Revise las duraciones '
                    'y reemplácelas con la información oficial/referencial.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_aplicar_configuracion_equipos(self):
        self.ensure_one()

        equipos = self.env['alquiler'].search(
            [
                ('name', '=', self.id),
                ('estado_alquiler_id', '=', 'alquilada'),
            ]
        )

        if not equipos:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin equipos'),
                    'message': _(
                        'No hay equipos alquilados de este modelo para actualizar.'
                    ),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuración sincronizada'),
                'message': _(
                    'Configuración aplicada a %s equipo(s) alquilado(s).'
                ) % len(equipos),
                'type': 'success',
                'sticky': False,
            },
        }
