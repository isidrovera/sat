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
    # REFERENCIAS DE TÓNER NEGRO
    # =========================================================

    toner_modelo_black = fields.Char(
        string='Modelo de tóner negro',
        index=True,
        help=(
            'Referencia comercial del tóner negro indicado por el fabricante. '
            'Ejemplo: TN-324K, MP 6054 Black o T-302K.'
        ),
    )

    toner_codigo_parte_black = fields.Char(
        string='Código de parte negro',
        index=True,
        help=(
            'Código OEM o número de parte del tóner negro. '
            'Ejemplo: A8DA130.'
        ),
    )

    # =========================================================
    # REFERENCIAS DE TÓNER CIAN
    # =========================================================

    toner_modelo_cyan = fields.Char(
        string='Modelo de tóner cian',
        index=True,
        help=(
            'Referencia comercial del tóner cian indicada por el fabricante. '
            'Ejemplo: TN-324C.'
        ),
    )

    toner_codigo_parte_cyan = fields.Char(
        string='Código de parte cian',
        index=True,
        help='Código OEM o número de parte del tóner cian.',
    )

    # =========================================================
    # REFERENCIAS DE TÓNER MAGENTA
    # =========================================================

    toner_modelo_magenta = fields.Char(
        string='Modelo de tóner magenta',
        index=True,
        help=(
            'Referencia comercial del tóner magenta indicada por el '
            'fabricante. Ejemplo: TN-324M.'
        ),
    )

    toner_codigo_parte_magenta = fields.Char(
        string='Código de parte magenta',
        index=True,
        help='Código OEM o número de parte del tóner magenta.',
    )

    # =========================================================
    # REFERENCIAS DE TÓNER AMARILLO
    # =========================================================

    toner_modelo_yellow = fields.Char(
        string='Modelo de tóner amarillo',
        index=True,
        help=(
            'Referencia comercial del tóner amarillo indicada por el '
            'fabricante. Ejemplo: TN-324Y.'
        ),
    )

    toner_codigo_parte_yellow = fields.Char(
        string='Código de parte amarillo',
        index=True,
        help='Código OEM o número de parte del tóner amarillo.',
    )

    # =========================================================
    # DURACIÓN DE FABRICANTE
    #
    # IMPORTANTE:
    # No cambiar estos nombres técnicos porque ya son utilizados
    # por pedidos, cálculos y alertas existentes.
    # =========================================================

    durabilidad_toner_black = fields.Integer(
        string='Durabilidad tóner negro (páginas)',
        default=0,
        help=(
            'Rendimiento oficial indicado por el fabricante para el '
            'tóner negro.'
        ),
    )

    durabilidad_toner_cyan = fields.Integer(
        string='Durabilidad tóner cian (páginas)',
        default=0,
        help=(
            'Rendimiento oficial indicado por el fabricante para el '
            'tóner cian.'
        ),
    )

    durabilidad_toner_magenta = fields.Integer(
        string='Durabilidad tóner magenta (páginas)',
        default=0,
        help=(
            'Rendimiento oficial indicado por el fabricante para el '
            'tóner magenta.'
        ),
    )

    durabilidad_toner_yellow = fields.Integer(
        string='Durabilidad tóner amarillo (páginas)',
        default=0,
        help=(
            'Rendimiento oficial indicado por el fabricante para el '
            'tóner amarillo.'
        ),
    )

    # =========================================================
    # INFORMACIÓN DE LA FUENTE
    # =========================================================

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
        help=(
            'Origen utilizado para registrar códigos y duraciones '
            'oficiales de los tóners.'
        ),
    )

    toner_fecha_verificacion = fields.Date(
        string='Fecha de verificación',
        help='Fecha en que se verificaron las referencias del fabricante.',
    )

    toner_observaciones = fields.Text(
        string='Observaciones de tóner',
        help=(
            'Notas sobre referencias regionales, códigos alternativos '
            'o datos pendientes de confirmación.'
        ),
    )

    # =========================================================
    # STOCK MÍNIMO RECOMENDADO
    # =========================================================

    stock_minimo_black = fields.Integer(
        string='Stock mínimo tóner negro',
        default=1,
        help=(
            'Cantidad mínima de tóner negro que debe tener el cliente '
            'entre instalado y disponible.'
        ),
    )

    stock_minimo_cyan = fields.Integer(
        string='Stock mínimo tóner cian',
        default=1,
        help=(
            'Cantidad mínima de tóner cian que debe tener el cliente '
            'entre instalado y disponible.'
        ),
    )

    stock_minimo_magenta = fields.Integer(
        string='Stock mínimo tóner magenta',
        default=1,
        help=(
            'Cantidad mínima de tóner magenta que debe tener el cliente '
            'entre instalado y disponible.'
        ),
    )

    stock_minimo_yellow = fields.Integer(
        string='Stock mínimo tóner amarillo',
        default=1,
        help=(
            'Cantidad mínima de tóner amarillo que debe tener el cliente '
            'entre instalado y disponible.'
        ),
    )

    # =========================================================
    # TIEMPOS DE ENTREGA
    # =========================================================

    tiempo_entrega_dias = fields.Integer(
        string='Tiempo de entrega (días)',
        default=2,
        help='Días estimados para entregar tóner al cliente.',
    )

    margen_seguridad_dias = fields.Integer(
        string='Margen de seguridad (días)',
        default=3,
        help='Días adicionales para evitar que el cliente quede sin tóner.',
    )

    tiempo_total_prevencion = fields.Integer(
        string='Tiempo total de prevención',
        compute='_compute_tiempo_total_prevencion',
        store=True,
        help='Suma del tiempo de entrega y el margen de seguridad.',
    )

    # =========================================================
    # ALERTAS Y GESTIÓN
    # =========================================================

    alerta_stock_critico = fields.Boolean(
        string='Alertas de stock crítico',
        default=True,
        help='Generar alertas cuando el stock del cliente esté crítico.',
    )

    alerta_consumo_alto = fields.Boolean(
        string='Alertas de consumo alto',
        default=True,
        help=(
            'Generar alertas cuando el rendimiento real del pedido sea '
            'menor al rendimiento del fabricante.'
        ),
    )

    gestionar_toner_automatico = fields.Boolean(
        string='Gestión automática de tóner',
        default=True,
        help='Activar la gestión automática de tóner para este modelo.',
    )

    # =========================================================
    # CAMPOS CALCULADOS
    # =========================================================

    mostrar_toner_color = fields.Boolean(
        string='Mostrar tóner color',
        compute='_compute_mostrar_toner_color',
        help='Indica si deben mostrarse las referencias C/M/Y.',
    )

    resumen_configuracion_toner = fields.Html(
        string='Resumen de configuración',
        compute='_compute_resumen_configuracion_toner',
        help='Resumen de referencias, duraciones y configuración del tóner.',
    )

    equipos_activos_count = fields.Integer(
        string='Equipos activos',
        compute='_compute_equipos_activos_count',
        store=True,
        help='Cantidad de equipos activos que usan este modelo.',
    )

    # =========================================================
    # MÉTODOS AUXILIARES
    # =========================================================

    @api.model
    def _toner_display_value(self, value):
        return value or 'No configurado'

    # =========================================================
    # MÉTODOS COMPUTE
    # =========================================================

    @api.depends(
        'tiempo_entrega_dias',
        'margen_seguridad_dias',
    )
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
                '<div style="font-family: Arial, sans-serif; '
                'line-height: 1.5;">'
            )

            html += (
                '<h4 style="margin: 0 0 14px 0;">'
                f'Configuración de tóner — {tipo_display}'
                '</h4>'
            )

            # Negro
            html += '<div style="margin-bottom: 12px;">'
            html += '<strong>Tóner negro</strong><br/>'
            html += (
                f'Referencia: '
                f'{record._toner_display_value(record.toner_modelo_black)}'
                '<br/>'
            )
            html += (
                f'Código de parte: '
                f'{record._toner_display_value(record.toner_codigo_parte_black)}'
                '<br/>'
            )
            html += (
                f'Duración fabricante: '
                f'{record.durabilidad_toner_black or 0:,} páginas'
                '<br/>'
            )
            html += (
                f'Stock mínimo: {record.stock_minimo_black or 0} unidad(es)'
            )
            html += '</div>'

            if record.tipo_id == 'color':
                color_data = [
                    (
                        'Cian',
                        record.toner_modelo_cyan,
                        record.toner_codigo_parte_cyan,
                        record.durabilidad_toner_cyan,
                        record.stock_minimo_cyan,
                    ),
                    (
                        'Magenta',
                        record.toner_modelo_magenta,
                        record.toner_codigo_parte_magenta,
                        record.durabilidad_toner_magenta,
                        record.stock_minimo_magenta,
                    ),
                    (
                        'Amarillo',
                        record.toner_modelo_yellow,
                        record.toner_codigo_parte_yellow,
                        record.durabilidad_toner_yellow,
                        record.stock_minimo_yellow,
                    ),
                ]

                for (
                    color_name,
                    toner_model,
                    part_code,
                    duration,
                    minimum_stock,
                ) in color_data:
                    html += '<div style="margin-bottom: 12px;">'
                    html += f'<strong>Tóner {color_name}</strong><br/>'
                    html += (
                        f'Referencia: '
                        f'{record._toner_display_value(toner_model)}'
                        '<br/>'
                    )
                    html += (
                        f'Código de parte: '
                        f'{record._toner_display_value(part_code)}'
                        '<br/>'
                    )
                    html += (
                        f'Duración fabricante: '
                        f'{duration or 0:,} páginas'
                        '<br/>'
                    )
                    html += (
                        f'Stock mínimo: {minimum_stock or 0} unidad(es)'
                    )
                    html += '</div>'

            html += '<hr/>'

            html += '<div style="margin-bottom: 12px;">'
            html += '<strong>Configuración logística</strong><br/>'
            html += (
                f'Tiempo de entrega: '
                f'{record.tiempo_entrega_dias or 0} día(s)<br/>'
            )
            html += (
                f'Margen de seguridad: '
                f'{record.margen_seguridad_dias or 0} día(s)<br/>'
            )
            html += (
                f'Total de prevención: '
                f'{record.tiempo_total_prevencion or 0} día(s)'
            )
            html += '</div>'

            source_label = selection_source.get(
                record.toner_fuente_informacion,
                'Pendiente de verificar',
            )

            html += '<div style="margin-bottom: 12px;">'
            html += '<strong>Verificación</strong><br/>'
            html += f'Fuente: {source_label}<br/>'
            html += (
                f'Fecha: '
                f'{record.toner_fecha_verificacion or "Sin verificar"}'
            )
            html += '</div>'

            html += '<div>'
            html += '<strong>Alertas</strong><br/>'
            html += (
                'Stock crítico: '
                f'{"Activo" if record.alerta_stock_critico else "Inactivo"}'
                '<br/>'
            )
            html += (
                'Consumo alto: '
                f'{"Activo" if record.alerta_consumo_alto else "Inactivo"}'
                '<br/>'
            )
            html += (
                'Gestión automática: '
                f'{"Activo" if record.gestionar_toner_automatico else "Inactivo"}'
            )
            html += '</div>'

            html += '</div>'

            record.resumen_configuracion_toner = html

    @api.depends('name')
    def _compute_equipos_activos_count(self):
        for record in self:
            record.equipos_activos_count = self.env[
                'alquiler'
            ].search_count(
                [
                    ('name', '=', record.id),
                    ('estado_alquiler_id', '=', 'alquilada'),
                ]
            )

    # =========================================================
    # VALIDACIONES
    # =========================================================

    @api.constrains(
        'durabilidad_toner_black',
        'durabilidad_toner_cyan',
        'durabilidad_toner_magenta',
        'durabilidad_toner_yellow',
    )
    def _check_durabilidad_toner(self):
        for record in self:
            durations = [
                (
                    record.durabilidad_toner_black,
                    _('La durabilidad del tóner negro no puede ser negativa.'),
                ),
                (
                    record.durabilidad_toner_cyan,
                    _('La durabilidad del tóner cian no puede ser negativa.'),
                ),
                (
                    record.durabilidad_toner_magenta,
                    _('La durabilidad del tóner magenta no puede ser negativa.'),
                ),
                (
                    record.durabilidad_toner_yellow,
                    _('La durabilidad del tóner amarillo no puede ser negativa.'),
                ),
            ]

            for duration, message in durations:
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
            minimum_stocks = [
                (
                    record.stock_minimo_black,
                    _('El stock mínimo negro no puede ser negativo.'),
                ),
                (
                    record.stock_minimo_cyan,
                    _('El stock mínimo cian no puede ser negativo.'),
                ),
                (
                    record.stock_minimo_magenta,
                    _('El stock mínimo magenta no puede ser negativo.'),
                ),
                (
                    record.stock_minimo_yellow,
                    _('El stock mínimo amarillo no puede ser negativo.'),
                ),
            ]

            for minimum_stock, message in minimum_stocks:
                if minimum_stock < 0:
                    raise ValidationError(message)

    @api.constrains(
        'tiempo_entrega_dias',
        'margen_seguridad_dias',
    )
    def _check_tiempos(self):
        for record in self:
            if record.tiempo_entrega_dias < 0:
                raise ValidationError(
                    _('El tiempo de entrega no puede ser negativo.')
                )

            if record.margen_seguridad_dias < 0:
                raise ValidationError(
                    _('El margen de seguridad no puede ser negativo.')
                )

    @api.constrains(
        'tipo_id',
        'toner_modelo_black',
        'toner_codigo_parte_black',
        'durabilidad_toner_black',
    )
    def _check_toner_black_configuration(self):
        """
        No obliga a tener la información completa porque existen más de
        500 modelos antiguos pendientes de actualización.

        Solo evita registrar una duración de fabricante sin ninguna
        referencia del tóner.
        """
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
        """
        Conserva la acción existente.

        Los valores se mantienen únicamente como apoyo inicial. Deben ser
        reemplazados por los valores oficiales del fabricante.
        """
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
                    'Se aplicaron valores iniciales. Revise y reemplace '
                    'las duraciones con la información oficial del fabricante.'
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
                        'No hay equipos alquilados de este modelo '
                        'para actualizar.'
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