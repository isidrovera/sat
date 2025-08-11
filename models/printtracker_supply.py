from odoo import models, fields, api
import requests
import logging

_logger = logging.getLogger(__name__)

class PrintTrackerSupply(models.Model):
    _name = 'printtracker.supply'
    _description = 'Seguimiento de Suministros PrintTracker'
    _order = 'device_id, supply_type, installed_date desc'

    # Identificación
    device_id = fields.Many2one('alquiler', string='Equipo', required=True, index=True)
    supply_key = fields.Char('Clave Suministro', required=True,
                            help='Clave única del suministro en PrintTracker')
    
    # Tipo y características del suministro
    supply_type = fields.Selection([
        ('toner', 'Toner'),
        ('ink', 'Tinta'),
        ('drum', 'Drum'),
        ('fuser', 'Fusor'),
        ('transfer', 'Transfer'),
        ('waste', 'Depósito Residuos'),
        ('maintenance', 'Kit Mantenimiento'),
        ('other', 'Otro')
    ], string='Tipo de Suministro', required=True)
    
    supply_color = fields.Selection([
        ('black', 'Negro'),
        ('cyan', 'Cian'),
        ('magenta', 'Magenta'),
        ('yellow', 'Amarillo'),
        ('color', 'Color'),
        ('colorless', 'Sin Color')
    ], string='Color')
    
    # Información del suministro
    part_number = fields.Char('Número de Parte')
    serial_number = fields.Char('Número de Serie')
    description = fields.Char('Descripción')
    displayable_name = fields.Char('Nombre Mostrable')
    
    # Estado actual
    current_level = fields.Integer('Nivel Actual')
    max_level = fields.Integer('Nivel Máximo')
    percent_remaining = fields.Float('Porcentaje Restante')
    
    # Fechas importantes
    installed_date = fields.Datetime('Fecha Instalación')
    replaced_date = fields.Datetime('Fecha Reemplazo')
    confirmed_replaced_date = fields.Datetime('Fecha Reemplazo Confirmada')
    estimated_depletion_date = fields.Datetime('Fecha Estimada Agotamiento')
    
    # Configuración y costos
    supply_cost = fields.Float('Costo del Suministro')
    expected_yield = fields.Integer('Rendimiento Esperado')
    expected_fill_rate = fields.Float('Tasa de Llenado Esperada')
    actual_fill_rate = fields.Float('Tasa de Llenado Real')
    
    # Estadísticas de uso
    pages_printed = fields.Integer('Páginas Impresas')
    actual_cost_per_page = fields.Float('Costo Real por Página')
    lost_pages = fields.Integer('Páginas Perdidas')
    
    # Estado del suministro
    is_active = fields.Boolean('Suministro Activo', default=True,
                              help='Indica si es el suministro actualmente instalado')
    is_replaced = fields.Boolean('Reemplazado', compute='_compute_is_replaced', store=True)
    
    # Control de alertas
    low_supply_alert = fields.Boolean('Alerta de Suministro Bajo',
                                     compute='_compute_low_supply_alert', store=True)
    skip_alerts = fields.Integer('Saltarse Alertas', default=0,
                                help='Número de alertas a omitir')
    
    # Relación con productos de Odoo
    product_id = fields.Many2one('product.template', string='Producto Odoo',
                                help='Producto en Odoo correspondiente a este suministro')
    
    # Control de sincronización
    last_sync = fields.Datetime('Última Sincronización', readonly=True)
    
    @api.depends('replaced_date')
    def _compute_is_replaced(self):
        for supply in self:
            supply.is_replaced = bool(supply.replaced_date)
    
    @api.depends('percent_remaining')
    def _compute_low_supply_alert(self):
        for supply in self:
            # Alerta si queda menos del 10%
            supply.low_supply_alert = (supply.percent_remaining < 10 and 
                                     supply.is_active and 
                                     not supply.is_replaced)
    
    def create_purchase_order(self):
        """Crea una orden de compra para este suministro"""
        if not self.product_id:
            raise ValueError("No hay producto asociado para crear la orden de compra")
        
        # Buscar el cliente del equipo
        partner_id = self.device_id.cliente_id if hasattr(self.device_id, 'cliente_id') else False
        
        if not partner_id:
            raise ValueError("El equipo no tiene cliente asignado")
        
        # Crear orden de compra
        purchase_order = self.env['purchase.order'].create({
            'partner_id': partner_id.id,
            'origin': f'Suministro bajo - {self.device_id.serie}',
            'order_line': [(0, 0, {
                'product_id': self.product_id.id,
                'name': f'{self.product_id.name} - {self.device_id.serie}',
                'product_qty': 1,
                'price_unit': self.supply_cost or self.product_id.standard_price,
                'date_planned': fields.Datetime.now(),
            })]
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Orden de Compra Generada',
            'res_model': 'purchase.order',
            'res_id': purchase_order.id,
            'view_mode': 'form',
            'target': 'current'
        }
    
    def get_supply_status(self):
        """Retorna el estado actual del suministro"""
        if self.is_replaced:
            return 'replaced'
        elif self.percent_remaining <= 0:
            return 'empty'
        elif self.percent_remaining < 10:
            return 'critical'
        elif self.percent_remaining < 25:
            return 'low'
        else:
            return 'normal'
    
    def get_days_until_depletion(self):
        """Calcula días hasta agotamiento estimado"""
        if not self.estimated_depletion_date:
            return None
        
        today = fields.Date.today()
        depletion_date = self.estimated_depletion_date.date()
        
        if depletion_date <= today:
            return 0
        
        return (depletion_date - today).days



