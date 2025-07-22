from odoo import models, fields, api
import requests
import logging

_logger = logging.getLogger(__name__)

class PrintTrackerConfig(models.Model):
    _name = 'printtracker.config'
    _description = 'Configuración API PrintTracker Pro'
    _rec_name = 'name'

    name = fields.Char('Nombre de Configuración', required=True, default='PrintTracker Pro Config')
    api_url = fields.Char('URL Base API', required=True, 
                         default='https://papi.printtrackerpro.com/v1',
                         help='URL base de la API de PrintTracker Pro')
    api_key = fields.Char('API Key', required=True,
                         help='Token de autenticación para la API')
    entity_bbbb_id = fields.Char('ID Entidad Principal', required=True,
                                help='ID de la entidad BBBB en PrintTracker')
    
    # Configuración de sincronización
    sync_interval = fields.Integer('Intervalo de Sincronización (minutos)', default=60,
                                  help='Cada cuántos minutos sincronizar con PrintTracker')
    last_sync_date = fields.Datetime('Última Sincronización', readonly=True)
    sync_enabled = fields.Boolean('Sincronización Activa', default=True)
    
    # Configuración de filtros
    incluir_entidades_hijas = fields.Boolean('Incluir Entidades Hijas', default=True,
                                           help='Sincronizar todas las entidades bajo BBBB')
    solo_equipos_gestionados = fields.Boolean('Solo Equipos Gestionados', default=True,
                                            help='Sincronizar solo equipos con managed=True')
    
    # Estado de conexión
    connection_status = fields.Selection([
        ('not_tested', 'No Probado'),
        ('connected', 'Conectado'),
        ('error', 'Error de Conexión')
    ], string='Estado Conexión', default='not_tested', readonly=True)
    
    last_error = fields.Text('Último Error', readonly=True)
    
    # Configuración avanzada
    timeout_seconds = fields.Integer('Timeout (segundos)', default=30)
    max_records_per_request = fields.Integer('Registros por Petición', default=100,
                                           help='Máximo registros por petición API')
    
    def test_connection(self):
        """Prueba la conexión con PrintTracker API"""
        try:
            _logger.info(f"🔍 Probando conexión a {self.api_url} con entidad {self.entity_bbbb_id}")
            
            headers = {
                'x-api-key': self.api_key,  # ← CORRECCIÓN: usar x-api-key
                'Content-Type': 'application/json'
            }
            
            # URL correcta según documentación: /entity/{entityId}
            response = requests.get(
                f'{self.api_url.rstrip("/")}/entity/{self.entity_bbbb_id}',  # ← CORRECCIÓN: /entity/ no /entities/
                headers=headers,
                timeout=self.timeout_seconds
            )
            
            _logger.info(f"📡 Respuesta API: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                entity_name = data.get('name', 'Sin nombre')
                
                self.write({
                    'connection_status': 'connected',
                    'last_error': False,
                    'last_sync_date': fields.Datetime.now()
                })
                
                _logger.info(f"✅ Conexión exitosa con entidad: {entity_name}")
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'✅ Conexión exitosa con PrintTracker Pro\nEntidad: {entity_name}',
                        'type': 'success'
                    }
                }
            else:
                error_msg = f'Error HTTP {response.status_code}: {response.text}'
                _logger.error(f"❌ Error de conexión: {error_msg}")
                
                self.write({
                    'connection_status': 'error',
                    'last_error': error_msg
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'❌ Error de conexión: {error_msg}',
                        'type': 'danger'
                    }
                }
                
        except Exception as e:
            error_msg = str(e)
            _logger.error(f"❌ Excepción en test_connection: {error_msg}")
            
            self.write({
                'connection_status': 'error',
                'last_error': error_msg
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'❌ Error: {error_msg}',
                    'type': 'danger'
                }
            }
    
    def get_api_headers(self):
        """Retorna headers para requests a la API"""
        return {
            'x-api-key': self.api_key,  # ← CORRECCIÓN: usar x-api-key en lugar de Authorization
            'Content-Type': 'application/json'
        }
    
    @api.model
    def get_active_config(self):
        """Obtiene la configuración activa"""
        config = self.search([('sync_enabled', '=', True)], limit=1)
        if not config:
            raise ValueError("No hay configuración activa de PrintTracker")
        return config

class PrintTrackerEntity(models.Model):
    _name = 'printtracker.entity'
    _description = 'Entidades PrintTracker Pro'
    _rec_name = 'name'
    _order = 'parent_id, name'

    # Información básica
    pt_entity_id = fields.Char('ID PrintTracker', required=True, index=True,
                              help='ID único de la entidad en PrintTracker')
    name = fields.Char('Nombre Entidad', required=True)
    parent_id = fields.Many2one('printtracker.entity', string='Entidad Padre',
                               help='Entidad padre en la jerarquía')
    child_ids = fields.One2many('printtracker.entity', 'parent_id', 
                               string='Entidades Hijas')
    
    # Relación con clientes de Odoo
    partner_id = fields.Many2one('res.partner', string='Cliente Odoo',
                                help='Cliente en Odoo correspondiente a esta entidad')
    
    # Información jerárquica
    genealogy = fields.Text('Genealogía',
                           help='Jerarquía completa de la entidad (JSON)')
    level = fields.Integer('Nivel Jerárquico', compute='_compute_level', store=True)
    
    # Direcciones de la entidad
    address_ids = fields.One2many('printtracker.entity.address', 'entity_id',
                                 string='Direcciones')
    
    # Control de sincronización
    is_active = fields.Boolean('Activa', default=True)
    last_sync = fields.Datetime('Última Sincronización', readonly=True)
    sync_error = fields.Text('Error Sincronización', readonly=True)
    
    # Labels/Etiquetas
    label_ids = fields.One2many('printtracker.entity.label', 'entity_id',
                               string='Etiquetas')
    
    # Estadísticas
    device_count = fields.Integer('Cantidad de Equipos', compute='_compute_device_count')
    
    @api.depends('parent_id')
    def _compute_level(self):
        """Calcula el nivel jerárquico de la entidad"""
        for entity in self:
            level = 0
            parent = entity.parent_id
            while parent:
                level += 1
                parent = parent.parent_id
                if level > 10:  # Prevenir loops infinitos
                    break
            entity.level = level
    
    def _compute_device_count(self):
        """Cuenta los dispositivos asociados a esta entidad"""
        for entity in self:
            # Contar en el modelo que extends alquiler
            count = self.env['alquiler'].search_count([
                ('pt_entity_id', '=', entity.id)
            ])
            entity.device_count = count
    
    def sync_with_printtracker(self):
        """Sincroniza esta entidad con PrintTracker"""
        try:
            config = self.env['printtracker.config'].get_active_config()
            
            response = requests.get(
                f'{config.api_url.rstrip("/")}/entities/{self.pt_entity_id}',
                headers=config.get_api_headers(),
                params={'includeChildren': True},
                timeout=config.timeout_seconds
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Actualizar datos básicos
                self.write({
                    'name': data.get('name', self.name),
                    'genealogy': str(data.get('genealogy', [])),
                    'last_sync': fields.Datetime.now(),
                    'sync_error': False
                })
                
                # Sincronizar direcciones
                self._sync_addresses(data.get('addresses', []))
                
                # Sincronizar labels
                self._sync_labels(data.get('labels', {}))
                
                _logger.info(f"✅ Entidad {self.name} sincronizada exitosamente")
                return True
                
            else:
                error_msg = f"Error HTTP {response.status_code}: {response.text}"
                self.write({
                    'sync_error': error_msg,
                    'last_sync': fields.Datetime.now()
                })
                _logger.error(f"❌ Error sincronizando entidad {self.name}: {error_msg}")
                return False
                
        except Exception as e:
            error_msg = str(e)
            self.write({
                'sync_error': error_msg,
                'last_sync': fields.Datetime.now()
            })
            _logger.error(f"❌ Error sincronizando entidad {self.name}: {error_msg}")
            return False
    
    def _sync_addresses(self, addresses_data):
        """Sincroniza las direcciones de la entidad"""
        # Limpiar direcciones existentes
        self.address_ids.unlink()
        
        # Crear nuevas direcciones
        for addr_data in addresses_data:
            self.env['printtracker.entity.address'].create({
                'entity_id': self.id,
                'name': addr_data.get('name', ''),
                'address1': addr_data.get('address1', ''),
                'address2': addr_data.get('address2', ''),
                'city': addr_data.get('city', ''),
                'state': addr_data.get('state', ''),
                'zip_code': addr_data.get('zipOrPostalCode', ''),
                'country': addr_data.get('country', ''),
            })
    
    def _sync_labels(self, labels_data):
        """Sincroniza las etiquetas de la entidad"""
        # Limpiar etiquetas existentes
        self.label_ids.unlink()
        
        # Crear nuevas etiquetas
        for key, value in labels_data.items():
            self.env['printtracker.entity.label'].create({
                'entity_id': self.id,
                'key': key,
                'value': str(value)
            })


class PrintTrackerEntityAddress(models.Model):
    _name = 'printtracker.entity.address'
    _description = 'Direcciones de Entidades PrintTracker'
    _rec_name = 'name'

    entity_id = fields.Many2one('printtracker.entity', string='Entidad',
                               required=True, ondelete='cascade')
    name = fields.Char('Nombre Dirección', required=True)
    address1 = fields.Char('Dirección 1')
    address2 = fields.Char('Dirección 2')
    city = fields.Char('Ciudad')
    state = fields.Char('Estado/Provincia')
    zip_code = fields.Char('Código Postal')
    country = fields.Char('País')
    
    def get_formatted_address(self):
        """Retorna la dirección formateada"""
        parts = [
            self.address1,
            self.address2,
            self.city,
            self.state,
            self.zip_code,
            self.country
        ]
        return ', '.join([part for part in parts if part])

class PrintTrackerEntityLabel(models.Model):
    _name = 'printtracker.entity.label'
    _description = 'Etiquetas de Entidades PrintTracker'
    _rec_name = 'display_name'

    entity_id = fields.Many2one('printtracker.entity', string='Entidad',
                               required=True, ondelete='cascade')
    key = fields.Char('Clave', required=True)
    value = fields.Char('Valor', required=True)
    display_name = fields.Char('Etiqueta', compute='_compute_display_name', store=True)
    
    @api.depends('key', 'value')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.key}: {record.value}"



class PrintTrackerMeter(models.Model):
    _name = 'printtracker.meter'
    _description = 'Lecturas de Medidores PrintTracker'
    _order = 'reading_date desc'

    # Identificación
    pt_meter_id = fields.Char('ID PrintTracker', required=True, index=True)
    device_id = fields.Many2one('alquiler', string='Equipo',
                               required=True, index=True)
    
    # Fecha y estado
    reading_date = fields.Datetime('Fecha de Lectura', required=True, index=True)
    console_status = fields.Char('Estado Consola')
    
    # Contadores de páginas - Life (contadores reales de vida del equipo)
    total_pages_life = fields.Integer('Total Páginas (Life)')
    black_pages_life = fields.Integer('Páginas Negras (Life)')
    color_pages_life = fields.Integer('Páginas Color (Life)')
    
    # Contadores equivalentes (páginas equivalentes para facturación)
    total_pages_equiv = fields.Integer('Total Páginas (Equiv)')
    black_pages_equiv = fields.Integer('Páginas Negras (Equiv)')
    color_pages_equiv = fields.Integer('Páginas Color (Equiv)')
    
    # Contadores adicionales
    scan_pages = fields.Integer('Páginas Escaneadas')
    fax_pages = fields.Integer('Páginas de Fax')
    copy_pages = fields.Integer('Páginas Copiadas')
    
    # Control de sincronización
    last_sync = fields.Datetime('Última Sincronización', readonly=True)
    sync_source = fields.Selection([
        ('api', 'API PrintTracker'),
        ('manual', 'Manual'),
        ('import', 'Importación'),
        ('counter_automatic', 'Sistema Automático Contadores')
    ], string='Origen', default='api')
    
    # Campos calculados
    pages_increment = fields.Integer('Incremento Total', 
                                   compute='_compute_increments', store=True)
    black_increment = fields.Integer('Incremento Negro',
                                    compute='_compute_increments', store=True)
    color_increment = fields.Integer('Incremento Color',
                                    compute='_compute_increments', store=True)
    
    @api.depends('device_id', 'total_pages_life', 'black_pages_life', 'color_pages_life')
    def _compute_increments(self):
        """Calcula incrementos respecto a la lectura anterior"""
        for meter in self:
            if not meter.device_id:
                meter.pages_increment = 0
                meter.black_increment = 0
                meter.color_increment = 0
                continue
                
            # Buscar lectura anterior
            previous_meter = self.search([
                ('device_id', '=', meter.device_id.id),
                ('reading_date', '<', meter.reading_date)
            ], limit=1, order='reading_date desc')
            
            if previous_meter:
                meter.pages_increment = (meter.total_pages_life or 0) - (previous_meter.total_pages_life or 0)
                meter.black_increment = (meter.black_pages_life or 0) - (previous_meter.black_pages_life or 0)
                meter.color_increment = (meter.color_pages_life or 0) - (previous_meter.color_pages_life or 0)
            else:
                # Primera lectura
                meter.pages_increment = meter.total_pages_life or 0
                meter.black_increment = meter.black_pages_life or 0
                meter.color_increment = meter.color_pages_life or 0
    
    def update_device_counters(self):
        """Actualiza los contadores del equipo con esta lectura"""
        if not self.device_id:
            return False
        
        try:
            self.device_id.write({
                'contador_bn': self.black_pages_life or 0,
                'contador_color': self.color_pages_life or 0,
                'contador_scan': self.scan_pages or 0,
                'fecha_ultima_lectura': self.reading_date,
                'ultimo_medidor_pt': self.id
            })
            
            _logger.info(f"✅ Contadores actualizados para equipo {self.device_id.serie}")
            return True
            
        except Exception as e:
            _logger.error(f"❌ Error actualizando contadores: {e}")
            return False
    
    @api.model
    def get_latest_for_device(self, device_id):
        """Obtiene la lectura más reciente para un equipo"""
        return self.search([
            ('device_id', '=', device_id)
        ], limit=1, order='reading_date desc')
    
    def get_reading_summary(self):
        """Retorna resumen de la lectura en formato dict"""
        return {
            'device_serial': self.device_id.serie if self.device_id else 'N/A',
            'reading_date': self.reading_date,
            'total_pages': self.total_pages_life,
            'black_pages': self.black_pages_life,
            'color_pages': self.color_pages_life,
            'scan_pages': self.scan_pages,
            'increments': {
                'total': self.pages_increment,
                'black': self.black_increment,
                'color': self.color_increment
            }
        }

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



