from odoo import models, fields, api
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class PrintTrackerSupply(models.Model):
    _name = 'printtracker.supply'
    _description = 'Estado de Suministros PrintTracker'
    _order = 'device_id, supply_type, supply_color, installed_date desc'
    _rec_name = 'display_name'

    # Identificación básica
    device_id = fields.Many2one('alquiler', string='Equipo', required=True, index=True)
    supply_key = fields.Char('Clave Suministro PrintTracker', required=True, index=True,
                            help='Clave única del suministro en PrintTracker API')
    
    # Tipo y características del suministro
    supply_type = fields.Selection([
        ('toner', 'Toner'),
        ('ink', 'Tinta'), 
        ('drum', 'Drum'),
        ('fuser', 'Fusor'),
        ('transfer', 'Transfer Belt'),
        ('waste', 'Depósito Residuos'),
        ('maintenance', 'Kit Mantenimiento'),
        ('other', 'Otro')
    ], string='Tipo de Suministro', required=True, index=True)
    
    supply_color = fields.Selection([
        ('black', 'Negro'),
        ('cyan', 'Cian'),
        ('magenta', 'Magenta'),
        ('yellow', 'Amarillo'),
        ('color', 'Color'),
        ('colorless', 'Sin Color')
    ], string='Color del Suministro', index=True)
    
    # Información del suministro desde PrintTracker
    part_number = fields.Char('Número de Parte')
    serial_number = fields.Char('Número de Serie')
    description = fields.Char('Descripción')
    displayable_name = fields.Char('Nombre Mostrable')
    
    # Estado actual del nivel
    current_level = fields.Integer('Nivel Actual')
    max_level = fields.Integer('Nivel Máximo')
    percent_remaining = fields.Float('Porcentaje Restante (%)', 
                                   help='Porcentaje de suministro restante')
    
    # Fechas importantes
    installed_date = fields.Datetime('Fecha Instalación')
    replaced_date = fields.Datetime('Fecha Reemplazo')
    confirmed_replaced_date = fields.Datetime('Fecha Reemplazo Confirmada')
    estimated_depletion_date = fields.Datetime('Fecha Estimada Agotamiento')
    
    # Información de rendimiento y costos
    supply_cost = fields.Float('Costo del Suministro ($)')
    expected_yield = fields.Integer('Rendimiento Esperado (páginas)')
    expected_fill_rate = fields.Float('Tasa de Llenado Esperada')
    actual_fill_rate = fields.Float('Tasa de Llenado Real')
    actual_cost_per_page = fields.Float('Costo Real por Página ($)')
    
    # Estadísticas de uso
    pages_printed = fields.Integer('Páginas Impresas con este Suministro')
    lost_pages = fields.Integer('Páginas Perdidas')
    
    # Estado del suministro
    is_active = fields.Boolean('Suministro Activo', default=True,
                              help='Indica si es el suministro actualmente instalado')
    is_replaced = fields.Boolean('Reemplazado', compute='_compute_is_replaced', store=True)
    
    # Control de alertas
    low_supply_alert = fields.Boolean('Alerta de Suministro Bajo',
                                     compute='_compute_alerts', store=True)
    critical_supply_alert = fields.Boolean('Alerta Crítica',
                                          compute='_compute_alerts', store=True)
    skip_alerts = fields.Integer('Saltarse Alertas', default=0,
                                help='Número de alertas a omitir')
    
    # Relación con productos de Odoo (opcional)
    product_id = fields.Many2one('product.template', string='Producto Odoo',
                                help='Producto en Odoo correspondiente a este suministro')
    
    # Control de sincronización
    last_sync = fields.Datetime('Última Sincronización', readonly=True)
    sync_source = fields.Selection([
        ('api', 'API PrintTracker'),
        ('manual', 'Manual'),
        ('import', 'Importación')
    ], string='Origen', default='api')
    
    # Campo de display
    display_name = fields.Char('Nombre', compute='_compute_display_name', store=True)
    
    # Estado calculado del suministro
    supply_status = fields.Selection([
        ('normal', 'Normal'),
        ('low', 'Bajo'),
        ('critical', 'Crítico'),
        ('empty', 'Vacío'),
        ('replaced', 'Reemplazado')
    ], string='Estado', compute='_compute_supply_status', store=True)
    
    # Predicción inteligente
    predicted_depletion_date = fields.Datetime('Predicción Agotamiento', 
                                              compute='_compute_predictions', store=False)
    days_until_depletion = fields.Integer('Días hasta Agotamiento',
                                        compute='_compute_predictions', store=False)
    
    # Constrains
    _sql_constraints = [
        ('unique_supply_key', 'UNIQUE(supply_key)', 
         'Clave de suministro PrintTracker debe ser única'),
        ('positive_percent', 'CHECK(percent_remaining >= 0 AND percent_remaining <= 100)', 
         'Porcentaje restante debe estar entre 0 y 100'),
        ('positive_levels', 'CHECK(current_level >= 0 AND max_level >= 0)', 
         'Niveles deben ser positivos')
    ]

    @api.depends('device_id', 'supply_type', 'supply_color', 'percent_remaining')
    def _compute_display_name(self):
        """Genera nombre descriptivo para el suministro"""
        for supply in self:
            parts = []
            
            if supply.device_id:
                parts.append(supply.device_id.serie or f"Equipo {supply.device_id.id}")
            
            if supply.supply_type:
                type_name = dict(supply._fields['supply_type'].selection).get(supply.supply_type, supply.supply_type)
                parts.append(type_name)
            
            if supply.supply_color and supply.supply_color != 'colorless':
                color_name = dict(supply._fields['supply_color'].selection).get(supply.supply_color, supply.supply_color)
                parts.append(color_name)
            
            if supply.percent_remaining is not False:
                parts.append(f"({supply.percent_remaining:.0f}%)")
            
            supply.display_name = " - ".join(parts) if parts else f"Suministro {supply.id or 'nuevo'}"

    @api.depends('replaced_date')
    def _compute_is_replaced(self):
        """Calcula si el suministro ha sido reemplazado"""
        for supply in self:
            supply.is_replaced = bool(supply.replaced_date)

    @api.depends('percent_remaining', 'is_replaced', 'is_active')
    def _compute_alerts(self):
        """Calcula alertas de suministro bajo/crítico"""
        for supply in self:
            if supply.is_replaced or not supply.is_active:
                supply.low_supply_alert = False
                supply.critical_supply_alert = False
                continue
            
            percent = supply.percent_remaining or 0
            
            # Alerta crítica: menos del 5%
            supply.critical_supply_alert = percent < 5
            
            # Alerta baja: menos del 15% (pero no crítica)
            supply.low_supply_alert = percent < 15 and not supply.critical_supply_alert

    @api.depends('percent_remaining', 'is_replaced')
    def _compute_supply_status(self):
        """Calcula el estado general del suministro"""
        for supply in self:
            if supply.is_replaced:
                supply.supply_status = 'replaced'
            elif supply.percent_remaining <= 0:
                supply.supply_status = 'empty'
            elif supply.percent_remaining < 5:
                supply.supply_status = 'critical'
            elif supply.percent_remaining < 15:
                supply.supply_status = 'low'
            else:
                supply.supply_status = 'normal'

    @api.depends('percent_remaining', 'device_id')
    def _compute_predictions(self):
        """
        Calcula predicción de agotamiento basada en uso histórico
        """
        for supply in self:
            if not supply.device_id or supply.percent_remaining <= 0 or supply.is_replaced:
                supply.predicted_depletion_date = False
                supply.days_until_depletion = 0
                continue
            
            try:
                # Obtener uso promedio de los últimos 30 días
                thirty_days_ago = datetime.now() - timedelta(days=30)
                recent_meters = self.env['printtracker.meter'].search([
                    ('device_id', '=', supply.device_id.id),
                    ('reading_date', '>=', thirty_days_ago)
                ], order='reading_date asc')
                
                if len(recent_meters) < 2:
                    supply.predicted_depletion_date = False
                    supply.days_until_depletion = 0
                    continue
                
                # Calcular páginas por día promedio
                first_meter = recent_meters[0]
                last_meter = recent_meters[-1]
                
                days_diff = (last_meter.reading_date - first_meter.reading_date).days
                if days_diff <= 0:
                    supply.predicted_depletion_date = False
                    supply.days_until_depletion = 0
                    continue
                
                total_pages_diff = (last_meter.total_pages_life or 0) - (first_meter.total_pages_life or 0)
                pages_per_day = total_pages_diff / days_diff if days_diff > 0 else 0
                
                if pages_per_day <= 0:
                    supply.predicted_depletion_date = False
                    supply.days_until_depletion = 0
                    continue
                
                # Calcular páginas restantes basado en rendimiento esperado y porcentaje
                if supply.expected_yield and supply.expected_yield > 0:
                    remaining_pages = (supply.percent_remaining / 100) * supply.expected_yield
                    days_remaining = remaining_pages / pages_per_day
                    
                    supply.predicted_depletion_date = datetime.now() + timedelta(days=days_remaining)
                    supply.days_until_depletion = int(days_remaining)
                else:
                    supply.predicted_depletion_date = False
                    supply.days_until_depletion = 0
                    
            except Exception as e:
                _logger.warning(f"Error calculando predicción para suministro {supply.id}: {e}")
                supply.predicted_depletion_date = False
                supply.days_until_depletion = 0

    @api.model
    def create(self, vals):
        """Override create para marcar como activo si es necesario"""
        supply = super().create(vals)
        
        # Si es el primer suministro del tipo/color para el dispositivo, marcarlo como activo
        if not vals.get('is_active'):
            existing_active = self.search([
                ('device_id', '=', supply.device_id.id),
                ('supply_type', '=', supply.supply_type),
                ('supply_color', '=', supply.supply_color),
                ('is_active', '=', True),
                ('id', '!=', supply.id)
            ])
            
            if not existing_active:
                supply.is_active = True
        
        return supply

    def action_mark_as_replaced(self):
        """Marca el suministro como reemplazado"""
        for supply in self:
            supply.write({
                'replaced_date': fields.Datetime.now(),
                'is_active': False,
                'percent_remaining': 0
            })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Suministro(s) marcado(s) como reemplazado(s)',
                'type': 'success'
            }
        }

    def action_skip_alerts(self, alerts_to_skip=1):
        """Configura saltar alertas para este suministro"""
        for supply in self:
            supply.skip_alerts = alerts_to_skip
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Se saltarán {alerts_to_skip} alerta(s) para este suministro',
                'type': 'info'
            }
        }

    def action_view_device_meters(self):
        """Ver medidores del dispositivo relacionado"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Medidores - {self.device_id.serie}',
            'res_model': 'printtracker.meter',
            'view_mode': 'tree,form',
            'domain': [('device_id', '=', self.device_id.id)],
            'context': {'default_device_id': self.device_id.id},
            'target': 'current'
        }

    def action_create_purchase_order(self):
        """
        SIMPLIFICADO: Crea orden de compra básica para reposición
        """
        self.ensure_one()
        
        if not self.product_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'No hay producto asociado. Configure el producto primero.',
                    'type': 'warning'
                }
            }
        
        # Buscar el cliente del equipo
        if not hasattr(self.device_id, 'cliente_id') or not self.device_id.cliente_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'El equipo no tiene cliente asignado',
                    'type': 'warning'
                }
            }
        
        # Crear orden de compra básica
        try:
            purchase_order = self.env['purchase.order'].create({
                'partner_id': self.device_id.cliente_id.id,
                'origin': f'Suministro bajo - {self.device_id.serie} - {self.display_name}',
                'order_line': [(0, 0, {
                    'product_id': self.product_id.id,
                    'name': f'{self.product_id.name} - {self.device_id.serie}',
                    'product_qty': 1,
                    'price_unit': self.supply_cost or self.product_id.standard_price or 0,
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
            
        except Exception as e:
            _logger.error(f"Error creando orden de compra: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error creando orden de compra: {str(e)}',
                    'type': 'danger'
                }
            }

    @api.model
    def get_low_supplies(self, critical_only=False):
        """
        Obtiene suministros bajos o críticos
        """
        domain = [
            ('is_active', '=', True),
            ('is_replaced', '=', False)
        ]
        
        if critical_only:
            domain.append(('critical_supply_alert', '=', True))
        else:
            domain.extend([
                '|',
                ('low_supply_alert', '=', True),
                ('critical_supply_alert', '=', True)
            ])
        
        return self.search(domain, order='percent_remaining asc')

    @api.model
    def get_supplies_by_device(self, device_id, active_only=True):
        """
        Obtiene todos los suministros de un dispositivo
        """
        domain = [('device_id', '=', device_id)]
        
        if active_only:
            domain.append(('is_active', '=', True))
        
        return self.search(domain, order='supply_type, supply_color')

    @api.model
    def get_replacement_statistics(self, days=30):
        """
        Obtiene estadísticas de reemplazos en los últimos N días
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        replaced_supplies = self.search([
            ('replaced_date', '>=', cutoff_date),
            ('replaced_date', '!=', False)
        ])
        
        stats = {
            'total_replacements': len(replaced_supplies),
            'by_type': {},
            'by_device': {},
            'average_yield': 0
        }
        
        # Estadísticas por tipo
        for supply in replaced_supplies:
            supply_type = supply.supply_type
            if supply_type not in stats['by_type']:
                stats['by_type'][supply_type] = 0
            stats['by_type'][supply_type] += 1
            
            # Por dispositivo
            device_serie = supply.device_id.serie
            if device_serie not in stats['by_device']:
                stats['by_device'][device_serie] = 0
            stats['by_device'][device_serie] += 1
        
        # Rendimiento promedio
        if replaced_supplies:
            yields = [s.pages_printed for s in replaced_supplies if s.pages_printed > 0]
            stats['average_yield'] = sum(yields) / len(yields) if yields else 0
        
        return stats

    def get_supply_history_summary(self):
        """
        Obtiene resumen del historial del suministro
        """
        self.ensure_one()
        
        summary = {
            'supply_info': {
                'type': self.supply_type,
                'color': self.supply_color,
                'part_number': self.part_number,
                'description': self.description
            },
            'status': {
                'current_level': self.current_level,
                'max_level': self.max_level,
                'percent_remaining': self.percent_remaining,
                'status': self.supply_status,
                'is_active': self.is_active
            },
            'dates': {
                'installed': self.installed_date,
                'replaced': self.replaced_date,
                'estimated_depletion': self.estimated_depletion_date,
                'predicted_depletion': self.predicted_depletion_date
            },
            'performance': {
                'pages_printed': self.pages_printed,
                'expected_yield': self.expected_yield,
                'actual_cost_per_page': self.actual_cost_per_page,
                'supply_cost': self.supply_cost
            },
            'alerts': {
                'low_supply': self.low_supply_alert,
                'critical_supply': self.critical_supply_alert,
                'skip_alerts': self.skip_alerts
            }
        }
        
        return summary