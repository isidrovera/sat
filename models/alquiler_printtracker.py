from odoo import models, fields, api

class AlquilerPrintTracker(models.Model):
    _inherit = 'alquiler'
    
    # Campos PrintTracker
    pt_device_id = fields.Char('ID Dispositivo PrintTracker', index=True,
                              help='ID único del dispositivo en PrintTracker')
    pt_entity_id = fields.Many2one('printtracker.entity', string='Entidad PrintTracker',
                                  help='Entidad PrintTracker a la que pertenece')
    
    # Información adicional de PrintTracker
    mac_address = fields.Char('Dirección MAC')
    ip_address = fields.Char('Dirección IP')
    firmware_version = fields.Char('Versión de Firmware')
    is_managed = fields.Boolean('Gestionado en PrintTracker', default=True,
                               help='Si está siendo monitoreado por PrintTracker')
    custom_location = fields.Char('Ubicación Personalizada')
    asset_id = fields.Char('ID de Activo')
    install_keys = fields.Text('Claves de Instalación',
                              help='Claves de instalación de PrintTracker (JSON)')
    
    # Fechas de sincronización
    fecha_ultima_lectura = fields.Datetime('Última Lectura PrintTracker', readonly=True)
    ultimo_medidor_pt = fields.Many2one('printtracker.meter', string='Último Medidor PT',
                                       readonly=True)
    
    # Estadísticas adicionales
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
        """Sincroniza este equipo específico con PrintTracker"""
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
            
            # Sincronizar medidor actual del dispositivo
            response = requests.get(
                f'{config.api_url.rstrip("/")}/entity/{self.pt_entity_id.pt_entity_id}/device/{self.pt_device_id}/meter/current',
                headers=config.get_api_headers(),
                timeout=config.timeout_seconds
            )
            
            if response.status_code == 200:
                meters = response.json()
                if meters:
                    # Procesar último medidor
                    latest_meter = meters[0]
                    # ... procesamiento del medidor
                    
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
                        'message': f'Error sincronizando: HTTP {response.status_code}',
                        'type': 'danger'
                    }
                }
                
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error: {str(e)}',
                    'type': 'danger'
                }
            }