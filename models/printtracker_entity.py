from odoo import models, fields, api
import requests
import logging

_logger = logging.getLogger(__name__)


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


