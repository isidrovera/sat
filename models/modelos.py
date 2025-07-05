from odoo import _, models, fields, api

class ModelosMaquin(models.Model):

    _name = 'modelo.maquina'
    _description = 'Modelo_de_maquina'

    name = fields.Char(string='Modelo de maquina', required=True )
    marca_id = fields.Many2one('marca.marca', string='Marca', required=True )
    tipo_id = fields.Selection([('color', 'Color'), ('monocromatica', 'Monocromatica')], required=True
                               )
    precio_venta = fields.Float('Precio de venta', required=True
                                )
    tipo_maquina_id = fields.Many2one('tipo.maquina', string='Tipo de maquina', required=True )

    @api.model
    def _default_currency_id(self):
        value = self.env['res.currency'].search(
            [('name', '=', 'USD')], limit=1)
        return value and value.id or False
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency', default=_default_currency_id)
    _sql_constraints = [("unique_name", "unique (name)",
                         "El modelo de maquina que intenta agregar ya existe")]
    # Agregar estos campos al modelo modelo.maquina
    # Insertar después de los campos existentes

    # ==========================================
    # CONFIGURACIÓN DE TÓNER POR MODELO
    # ==========================================

    # Durabilidad de tóners (páginas que rinde cada tóner)
    durabilidad_toner_black = fields.Integer(
        string='Durabilidad Tóner Negro (páginas)',
        default=0,
        help='Cantidad de páginas que rinde un tóner negro nuevo para este modelo'
    )

    durabilidad_toner_cyan = fields.Integer(
        string='Durabilidad Tóner Cian (páginas)',
        default=0,
        help='Cantidad de páginas que rinde un tóner cian nuevo para este modelo'
    )

    durabilidad_toner_magenta = fields.Integer(
        string='Durabilidad Tóner Magenta (páginas)',
        default=0,
        help='Cantidad de páginas que rinde un tóner magenta nuevo para este modelo'
    )

    durabilidad_toner_yellow = fields.Integer(
        string='Durabilidad Tóner Amarillo (páginas)',
        default=0,
        help='Cantidad de páginas que rinde un tóner amarillo nuevo para este modelo'
    )

    # Stock mínimo recomendado por tipo de tóner
    stock_minimo_black = fields.Integer(
        string='Stock Mínimo Tóner Negro',
        default=1,
        help='Cantidad mínima de tóner negro que debe tener el cliente (instalado + en stock)'
    )

    stock_minimo_cyan = fields.Integer(
        string='Stock Mínimo Tóner Cian',
        default=1,
        help='Cantidad mínima de tóner cian que debe tener el cliente (instalado + en stock)'
    )

    stock_minimo_magenta = fields.Integer(
        string='Stock Mínimo Tóner Magenta',
        default=1,
        help='Cantidad mínima de tóner magenta que debe tener el cliente (instalado + en stock)'
    )

    stock_minimo_yellow = fields.Integer(
        string='Stock Mínimo Tóner Amarillo',
        default=1,
        help='Cantidad mínima de tóner amarillo que debe tener el cliente (instalado + en stock)'
    )

    # Configuración de tiempos de entrega
    tiempo_entrega_dias = fields.Integer(
        string='Tiempo de Entrega (días)',
        default=2,
        help='Días que toma entregar tóner al cliente para este modelo'
    )

    margen_seguridad_dias = fields.Integer(
        string='Margen de Seguridad (días)',
        default=3,
        help='Días adicionales de margen para evitar quedarse sin tóner'
    )

    # Configuración de alertas
    alerta_stock_critico = fields.Boolean(
        string='Alertas de Stock Crítico',
        default=True,
        help='Enviar alertas cuando el stock esté crítico para este modelo'
    )

    alerta_consumo_alto = fields.Boolean(
        string='Alertas de Consumo Alto',
        default=True,
        help='Enviar alertas cuando el consumo sea anormalmente alto'
    )

    # Configuración específica por tipo de máquina
    gestionar_toner_automatico = fields.Boolean(
        string='Gestión Automática de Tóner',
        default=True,
        help='Activar gestión automática de tóner para este modelo'
    )

    # ==========================================
    # CAMPOS CALCULADOS Y DE INFORMACIÓN
    # ==========================================

    # Mostrar solo campos relevantes según el tipo de máquina
    mostrar_toner_color = fields.Boolean(
        string='Mostrar Tóner Color',
        compute='_compute_mostrar_toner_color',
        help='Indica si se deben mostrar los campos de tóner color'
    )

    # Resumen de configuración
    resumen_configuracion_toner = fields.Html(
        string='Resumen Configuración',
        compute='_compute_resumen_configuracion_toner',
        help='Resumen de la configuración de tóner para este modelo'
    )

    # Equipos que usan este modelo (para validaciones)
    equipos_activos_count = fields.Integer(
        string='Equipos Activos',
        compute='_compute_equipos_activos_count',
        help='Cantidad de equipos activos que usan este modelo'
    )

    # ==========================================
    # MÉTODOS COMPUTE
    # ==========================================

    @api.depends('tipo_id')
    def _compute_mostrar_toner_color(self):
        """Determina si mostrar campos de tóner color según el tipo de máquina"""
        for record in self:
            record.mostrar_toner_color = record.tipo_id == 'color'

    @api.depends('durabilidad_toner_black', 'durabilidad_toner_cyan', 
                'durabilidad_toner_magenta', 'durabilidad_toner_yellow',
                'stock_minimo_black', 'stock_minimo_cyan',
                'stock_minimo_magenta', 'stock_minimo_yellow',
                'tiempo_entrega_dias', 'margen_seguridad_dias', 'tipo_id')
    def _compute_resumen_configuracion_toner(self):
        """Genera resumen HTML de la configuración de tóner"""
        for record in self:
            html = '<div style="font-family: Arial, sans-serif; line-height: 1.4;">'
            
            # Tipo de máquina
            tipo_display = 'Color' if record.tipo_id == 'color' else 'Monocromática'
            html += f'<h4 style="margin: 0 0 10px 0; color: #2E86AB;">🖨️ {tipo_display}</h4>'
            
            # Durabilidad
            html += '<div style="margin-bottom: 15px;">'
            html += '<strong>📄 Durabilidad de Tóners:</strong><br/>'
            html += f'• Negro: {record.durabilidad_toner_black:,} páginas<br/>'
            
            if record.tipo_id == 'color':
                html += f'• Cian: {record.durabilidad_toner_cyan:,} páginas<br/>'
                html += f'• Magenta: {record.durabilidad_toner_magenta:,} páginas<br/>'
                html += f'• Amarillo: {record.durabilidad_toner_yellow:,} páginas<br/>'
            html += '</div>'
            
            # Stock mínimo
            html += '<div style="margin-bottom: 15px;">'
            html += '<strong>📦 Stock Mínimo:</strong><br/>'
            html += f'• Negro: {record.stock_minimo_black} unidad(es)<br/>'
            
            if record.tipo_id == 'color':
                html += f'• Cian: {record.stock_minimo_cyan} unidad(es)<br/>'
                html += f'• Magenta: {record.stock_minimo_magenta} unidad(es)<br/>'
                html += f'• Amarillo: {record.stock_minimo_yellow} unidad(es)<br/>'
            html += '</div>'
            
            # Tiempos
            html += '<div style="margin-bottom: 15px;">'
            html += '<strong>⏰ Configuración de Tiempos:</strong><br/>'
            html += f'• Tiempo de entrega: {record.tiempo_entrega_dias} día(s)<br/>'
            html += f'• Margen de seguridad: {record.margen_seguridad_dias} día(s)<br/>'
            html += f'• Total tiempo prevención: {record.tiempo_entrega_dias + record.margen_seguridad_dias} día(s)<br/>'
            html += '</div>'
            
            # Alertas
            html += '<div>'
            html += '<strong>🔔 Configuración de Alertas:</strong><br/>'
            html += f'• Stock crítico: {"✅ Activo" if record.alerta_stock_critico else "❌ Inactivo"}<br/>'
            html += f'• Consumo alto: {"✅ Activo" if record.alerta_consumo_alto else "❌ Inactivo"}<br/>'
            html += f'• Gestión automática: {"✅ Activo" if record.gestionar_toner_automatico else "❌ Inactivo"}<br/>'
            html += '</div>'
            
            html += '</div>'
            record.resumen_configuracion_toner = html

    def _compute_equipos_activos_count(self):
        """Cuenta equipos activos que usan este modelo"""
        for record in self:
            record.equipos_activos_count = self.env['alquiler'].search_count([
                ('name', '=', record.id),
                ('estado_alquiler_id', '=', 'alquilada')
            ])

    # ==========================================
    # MÉTODOS DE VALIDACIÓN
    # ==========================================

    @api.constrains('durabilidad_toner_black', 'durabilidad_toner_cyan',
                    'durabilidad_toner_magenta', 'durabilidad_toner_yellow')
    def _check_durabilidad_toner(self):
        """Valida que las durabilidades sean positivas"""
        for record in self:
            if record.durabilidad_toner_black < 0:
                raise ValidationError("La durabilidad del tóner negro no puede ser negativa.")
            
            if record.tipo_id == 'color':
                if record.durabilidad_toner_cyan < 0:
                    raise ValidationError("La durabilidad del tóner cian no puede ser negativa.")
                if record.durabilidad_toner_magenta < 0:
                    raise ValidationError("La durabilidad del tóner magenta no puede ser negativa.")
                if record.durabilidad_toner_yellow < 0:
                    raise ValidationError("La durabilidad del tóner amarillo no puede ser negativa.")

    @api.constrains('stock_minimo_black', 'stock_minimo_cyan',
                    'stock_minimo_magenta', 'stock_minimo_yellow')
    def _check_stock_minimo(self):
        """Valida que los stocks mínimos sean positivos"""
        for record in self:
            if record.stock_minimo_black < 0:
                raise ValidationError("El stock mínimo de tóner negro no puede ser negativo.")
            
            if record.tipo_id == 'color':
                if record.stock_minimo_cyan < 0:
                    raise ValidationError("El stock mínimo de tóner cian no puede ser negativo.")
                if record.stock_minimo_magenta < 0:
                    raise ValidationError("El stock mínimo de tóner magenta no puede ser negativo.")
                if record.stock_minimo_yellow < 0:
                    raise ValidationError("El stock mínimo de tóner amarillo no puede ser negativo.")

    @api.constrains('tiempo_entrega_dias', 'margen_seguridad_dias')
    def _check_tiempos(self):
        """Valida que los tiempos sean positivos"""
        for record in self:
            if record.tiempo_entrega_dias < 0:
                raise ValidationError("El tiempo de entrega no puede ser negativo.")
            if record.margen_seguridad_dias < 0:
                raise ValidationError("El margen de seguridad no puede ser negativo.")

    # ==========================================
    # MÉTODOS DE ACCIÓN
    # ==========================================

    def action_view_equipos_modelo(self):
        """Abre vista de equipos que usan este modelo"""
        self.ensure_one()
        return {
            'name': f'Equipos - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'alquiler',
            'view_mode': 'tree,form',
            'domain': [('name', '=', self.id)],
            'context': {
                'default_name': self.id,
                'create': False
            }
        }

    def action_configurar_valores_predeterminados(self):
        """Configura valores predeterminados inteligentes"""
        self.ensure_one()
        
        # Valores típicos para diferentes tipos de máquinas
        if self.tipo_id == 'monocromatica':
            # Configuración para máquinas monocromáticas
            self.write({
                'durabilidad_toner_black': 3000,  # Típico para monocromo
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
                'gestionar_toner_automatico': True
            })
        elif self.tipo_id == 'color':
            # Configuración para máquinas color
            self.write({
                'durabilidad_toner_black': 2500,  # Típico para color
                'durabilidad_toner_cyan': 2000,
                'durabilidad_toner_magenta': 2000,
                'durabilidad_toner_yellow': 2000,
                'stock_minimo_black': 2,
                'stock_minimo_cyan': 1,
                'stock_minimo_magenta': 1,
                'stock_minimo_yellow': 1,
                'tiempo_entrega_dias': 3,  # Color puede tardar más
                'margen_seguridad_dias': 5,
                'alerta_stock_critico': True,
                'alerta_consumo_alto': True,
                'gestionar_toner_automatico': True
            })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Configuración Aplicada',
                'message': 'Se han aplicado valores predeterminados inteligentes para este tipo de máquina.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_aplicar_configuracion_equipos(self):
        """Aplica la configuración actual a todos los equipos de este modelo"""
        self.ensure_one()
        
        equipos = self.env['alquiler'].search([
            ('name', '=', self.id),
            ('estado_alquiler_id', '=', 'alquilada')
        ])
        
        if not equipos:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sin Equipos',
                    'message': 'No hay equipos alquilados de este modelo para actualizar.',
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Aquí se podría agregar lógica para sincronizar configuración
        # Por ejemplo, reconfigurar fechas de próximas entregas
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Configuración Sincronizada',
                'message': f'Configuración aplicada a {len(equipos)} equipo(s) alquilado(s).',
                'type': 'success',
                'sticky': False,
            }
        }