from odoo import models, fields, api
import requests
import logging

_logger = logging.getLogger(__name__)

class AlquilerPrintTracker(models.Model):
    _inherit = 'alquiler'
    
    # Campos PrintTracker (MANTENER)
    pt_device_id = fields.Char('ID Dispositivo PrintTracker', index=True,
                              help='ID único del dispositivo en PrintTracker')
    pt_entity_id = fields.Many2one('printtracker.entity', string='Entidad PrintTracker',
                                  help='Entidad PrintTracker a la que pertenece')
    
    # Información adicional de PrintTracker (MANTENER)
    mac_address = fields.Char('Dirección MAC')
    ip_address = fields.Char('Dirección IP')
    firmware_version = fields.Char('Versión de Firmware')
    is_managed = fields.Boolean('Gestionado en PrintTracker', default=True,
                               help='Si está siendo monitoreado por PrintTracker')
    custom_location = fields.Char('Ubicación Personalizada')
    asset_id = fields.Char('ID de Activo')
    install_keys = fields.Text('Claves de Instalación',
                              help='Claves de instalación de PrintTracker (JSON)')
    
    # ❌ ELIMINAR ESTOS CAMPOS DUPLICADOS:
    # fecha_ultima_lectura = fields.Datetime('Última Lectura PrintTracker', readonly=True)
    # ✅ USAR: fecha_ultima_actualizacion (ya existe en modelo base)
    
    # Referencia al último medidor (MANTENER)
    ultimo_medidor_pt = fields.Many2one('printtracker.meter', string='Último Medidor PT',
                                       readonly=True)
    
    # Estadísticas adicionales (MANTENER)
    total_meter_readings = fields.Integer('Total de Lecturas', 
                                        compute='_compute_meter_stats', store=False)
    last_supply_alert = fields.Datetime('Última Alerta de Suministro', readonly=True)
    
    @api.depends('ultimo_medidor_pt')
    def _compute_meter_stats(self):
        """Calcula estadísticas de medidores"""
        for record in self:
            if record.pt_device_id:
                count = self.env['printtracker.meter'].search_count([
                    ('device_id', '=', record.id)
                ])
                record.total_meter_readings = count
            else:
                record.total_meter_readings = 0
    
    def sync_with_printtracker(self):
        """
        MÉTODO CORREGIDO: Sincroniza este equipo específico con PrintTracker
        """
        if not self.pt_device_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Este equipo no tiene ID de PrintTracker asociado',
                    'type': 'warning'
                }
            }
        
        try:
            config = self.env['printtracker.config'].get_active_config()
            
            # ✅ CORRECCIÓN: URL correcta según API PrintTracker
            if not self.pt_entity_id or not self.pt_entity_id.pt_entity_id:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'Este equipo no tiene entidad PrintTracker asociada',
                        'type': 'warning'
                    }
                }
            
            # Sincronizar medidor actual del dispositivo
            response = requests.get(
                f'{config.api_url.rstrip("/")}/entity/{self.pt_entity_id.pt_entity_id}/device/{self.pt_device_id}/meter/current',
                headers=config.get_api_headers(),
                timeout=config.timeout_seconds
            )
            
            if response.status_code == 200:
                meter_data = response.json()
                if meter_data:
                    # ✅ CREAR/ACTUALIZAR MEDIDOR usando el método corregido
                    meter_values = {
                        'pt_meter_id': meter_data.get('id'),
                        'device_id': self.id,
                        'reading_date': meter_data.get('timestamp'),
                        'console_status': meter_data.get('console'),
                    }
                    
                    # Extraer contadores
                    page_counts = meter_data.get('pageCounts', {})
                    life_counts = page_counts.get('life', {})
                    
                    meter_values.update({
                        'total_pages_life': life_counts.get('total', {}).get('value', 0),
                        'black_pages_life': life_counts.get('totalBlack', {}).get('value', 0),
                        'color_pages_life': life_counts.get('totalColor', {}).get('value', 0),
                        'sync_source': 'manual_sync',
                        'last_sync': fields.Datetime.now()
                    })
                    
                    # Buscar medidor existente o crear nuevo
                    existing_meter = self.env['printtracker.meter'].search([
                        ('pt_meter_id', '=', meter_data.get('id'))
                    ], limit=1)
                    
                    if existing_meter:
                        existing_meter.write(meter_values)
                    else:
                        new_meter = self.env['printtracker.meter'].create(meter_values)
                        # ✅ USAR MÉTODO CORREGIDO para actualizar contadores
                        new_meter.update_device_counters()
                    
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'Equipo sincronizado exitosamente con PrintTracker',
                        'type': 'success'
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'Error sincronizando: HTTP {response.status_code} - {response.text}',
                        'type': 'danger'
                    }
                }
                
        except Exception as e:
            _logger.error(f"❌ Error sincronizando equipo {self.serie}: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error: {str(e)}',
                    'type': 'danger'
                }
            }