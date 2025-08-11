from odoo import models, fields, api
import requests
import logging
import json

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
                               help='Entidad padre en la jerarquía', index=True)
    child_ids = fields.One2many('printtracker.entity', 'parent_id', 
                               string='Entidades Hijas')
    
    # Relación con clientes de Odoo (opcional)
    partner_id = fields.Many2one('res.partner', string='Cliente Odoo',
                                help='Cliente en Odoo correspondiente a esta entidad')
    
    # Información jerárquica
    genealogy = fields.Text('Genealogía',
                           help='Jerarquía completa de la entidad (JSON)')
    level = fields.Integer('Nivel Jerárquico', compute='_compute_level', store=True)
    complete_path = fields.Char('Ruta Completa', compute='_compute_complete_path', store=True)
    
    # Direcciones de la entidad
    address_ids = fields.One2many('printtracker.entity.address', 'entity_id',
                                 string='Direcciones')
    
    # Labels/Etiquetas
    label_ids = fields.One2many('printtracker.entity.label', 'entity_id',
                               string='Etiquetas')
    
    # Estado y control
    is_active = fields.Boolean('Activa', default=True)
    last_sync = fields.Datetime('Última Sincronización', readonly=True)
    sync_error = fields.Text('Error Sincronización', readonly=True)
    
    # Estadísticas calculadas
    device_count = fields.Integer('Cantidad de Equipos', compute='_compute_statistics')
    total_devices = fields.Integer('Total Dispositivos (incluyendo hijos)', 
                                  compute='_compute_statistics')
    active_devices = fields.Integer('Dispositivos Activos', compute='_compute_statistics')
    child_count = fields.Integer('Cantidad de Entidades Hijas', compute='_compute_statistics')
    
    # Información adicional
    description = fields.Text('Descripción')
    notes = fields.Text('Notas Internas')
    
    # Configuración de sincronización
    auto_sync = fields.Boolean('Sincronización Automática', default=True,
                              help='Si esta entidad debe sincronizarse automáticamente')
    
    # Campos computados para análisis
    last_device_activity = fields.Datetime('Última Actividad de Dispositivos',
                                         compute='_compute_activity', store=False)
    has_low_supplies = fields.Boolean('Tiene Suministros Bajos',
                                    compute='_compute_supply_status', store=False)
    
    # Constrains
    _sql_constraints = [
        ('unique_pt_entity', 'UNIQUE(pt_entity_id)', 
         'ID PrintTracker debe ser único'),
        ('no_self_parent', 'CHECK(id != parent_id)', 
         'Una entidad no puede ser su propio padre')
    ]

    @api.depends('parent_id')
    def _compute_level(self):
        """Calcula el nivel jerárquico de la entidad"""
        for entity in self:
            level = 0
            parent = entity.parent_id
            visited = set()  # Prevenir loops infinitos
            
            while parent and parent.id not in visited:
                level += 1
                visited.add(parent.id)
                parent = parent.parent_id
                
                if level > 20:  # Límite de seguridad
                    _logger.warning(f"Jerarquía muy profunda detectada para entidad {entity.name}")
                    break
                    
            entity.level = level

    @api.depends('name', 'parent_id')
    def _compute_complete_path(self):
        """Calcula la ruta completa jerárquica"""
        for entity in self:
            path_parts = []
            current = entity
            visited = set()
            
            while current and current.id not in visited:
                path_parts.append(current.name)
                visited.add(current.id)
                current = current.parent_id
                
                if len(path_parts) > 20:  # Límite de seguridad
                    break
            
            entity.complete_path = " / ".join(reversed(path_parts))

    @api.depends('child_ids')
    def _compute_statistics(self):
        """Calcula estadísticas de dispositivos y entidades hijas"""
        for entity in self:
            # Dispositivos directos de esta entidad
            direct_devices = self.env['alquiler'].search([
                ('pt_entity_id', '=', entity.id)
            ])
            entity.device_count = len(direct_devices)
            entity.active_devices = len(direct_devices.filtered(lambda d: getattr(d, 'active', True)))
            
            # Entidades hijas directas
            entity.child_count = len(entity.child_ids)
            
            # Total de dispositivos incluyendo entidades hijas
            all_child_entities = entity._get_all_children()
            all_entity_ids = [entity.id] + [child.id for child in all_child_entities]
            
            total_devices = self.env['alquiler'].search_count([
                ('pt_entity_id', 'in', all_entity_ids)
            ])
            entity.total_devices = total_devices

    def _compute_activity(self):
        """Calcula la última actividad de dispositivos en esta entidad"""
        for entity in self:
            # Buscar la lectura más reciente de cualquier dispositivo de esta entidad
            devices = self.env['alquiler'].search([
                ('pt_entity_id', '=', entity.id)
            ])
            
            if devices:
                latest_meter = self.env['printtracker.meter'].search([
                    ('device_id', 'in', devices.ids)
                ], limit=1, order='reading_date desc')
                
                entity.last_device_activity = latest_meter.reading_date if latest_meter else False
            else:
                entity.last_device_activity = False

    def _compute_supply_status(self):
        """Verifica si hay suministros bajos en esta entidad"""
        for entity in self:
            devices = self.env['alquiler'].search([
                ('pt_entity_id', '=', entity.id)
            ])
            
            if devices:
                low_supplies = self.env['printtracker.supply'].search([
                    ('device_id', 'in', devices.ids),
                    ('is_active', '=', True),
                    '|',
                    ('low_supply_alert', '=', True),
                    ('critical_supply_alert', '=', True)
                ], limit=1)
                
                entity.has_low_supplies = bool(low_supplies)
            else:
                entity.has_low_supplies = False

    def _get_all_children(self):
        """
        Obtiene todas las entidades hijas recursivamente
        """
        all_children = self.env['printtracker.entity']
        
        def collect_children(entity):
            children = entity.child_ids
            all_children |= children
            for child in children:
                collect_children(child)
        
        collect_children(self)
        return all_children

    def sync_with_printtracker(self):
        """
        SIMPLIFICADO: Sincroniza esta entidad específica con PrintTracker
        """
        try:
            config = self.env['printtracker.config'].get_active_config()
            
            def _entity_call():
                return requests.get(
                    f'{config.api_url.rstrip("/")}/entity/{self.pt_entity_id}',
                    headers=config.get_api_headers(),
                    params={'includeChildren': True},
                    timeout=config.timeout_seconds
                )
            
            response = config._retry_api_call(_entity_call)
            
            if response.status_code == 200:
                data = response.json()
                
                # Actualizar datos básicos
                update_values = {
                    'name': data.get('name', self.name),
                    'genealogy': json.dumps(data.get('genealogy', [])),
                    'last_sync': fields.Datetime.now(),
                    'sync_error': False
                }
                
                self.write(update_values)
                
                # Sincronizar direcciones
                if 'addresses' in data:
                    self._sync_addresses(data['addresses'])
                
                # Sincronizar labels
                if 'labels' in data:
                    self._sync_labels(data['labels'])
                
                _logger.info(f"✅ Entidad {self.name} sincronizada exitosamente")
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'✅ Entidad {self.name} sincronizada exitosamente',
                        'type': 'success'
                    }
                }
                
            else:
                error_msg = f"Error HTTP {response.status_code}: {response.text}"
                self.write({
                    'sync_error': error_msg,
                    'last_sync': fields.Datetime.now()
                })
                
                _logger.error(f"❌ Error sincronizando entidad {self.name}: {error_msg}")
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'❌ Error sincronizando: {error_msg}',
                        'type': 'danger'
                    }
                }
                
        except Exception as e:
            error_msg = str(e)
            self.write({
                'sync_error': error_msg,
                'last_sync': fields.Datetime.now()
            })
            
            _logger.error(f"❌ Error sincronizando entidad {self.name}: {error_msg}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'❌ Error: {error_msg}',
                    'type': 'danger'
                }
            }

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

    def action_view_devices(self):
        """Acción para ver dispositivos de esta entidad"""
        return {
            'type': 'ir.actions.act_window',
            'name': f'Dispositivos - {self.name}',
            'res_model': 'alquiler',
            'view_mode': 'tree,form',
            'domain': [('pt_entity_id', '=', self.id)],
            'context': {
                'default_pt_entity_id': self.id,
                'search_default_pt_entity_id': self.id
            },
            'target': 'current'
        }

    def action_view_all_devices(self):
        """Acción para ver todos los dispositivos (incluyendo entidades hijas)"""
        all_children = self._get_all_children()
        all_entity_ids = [self.id] + [child.id for child in all_children]
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Todos los Dispositivos - {self.name}',
            'res_model': 'alquiler',
            'view_mode': 'tree,form',
            'domain': [('pt_entity_id', 'in', all_entity_ids)],
            'context': {
                'search_default_pt_entity_id': self.id
            },
            'target': 'current'
        }

    def action_view_supplies_status(self):
        """Acción para ver estado de suministros de esta entidad"""
        devices = self.env['alquiler'].search([
            ('pt_entity_id', '=', self.id)
        ])
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Estado Suministros - {self.name}',
            'res_model': 'printtracker.supply',
            'view_mode': 'tree,form',
            'domain': [
                ('device_id', 'in', devices.ids),
                ('is_active', '=', True)
            ],
            'context': {
                'search_default_low_supplies': True
            },
            'target': 'current'
        }

    def action_view_meters(self):
        """Acción para ver lecturas de medidores de esta entidad"""
        devices = self.env['alquiler'].search([
            ('pt_entity_id', '=', self.id)
        ])
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Lecturas de Medidores - {self.name}',
            'res_model': 'printtracker.meter',
            'view_mode': 'tree,form',
            'domain': [('device_id', 'in', devices.ids)],
            'context': {
                'search_default_current_month': True
            },
            'target': 'current'
        }

    def action_sync_children(self):
        """Sincroniza esta entidad y todas sus hijas"""
        entities_to_sync = [self] + self._get_all_children().filtered('auto_sync')
        
        success_count = 0
        error_count = 0
        
        for entity in entities_to_sync:
            try:
                result = entity.sync_with_printtracker()
                if result['params']['type'] == 'success':
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                _logger.error(f"Error sincronizando entidad {entity.name}: {e}")
                error_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Sincronización completa: {success_count} éxitos, {error_count} errores',
                'type': 'success' if error_count == 0 else 'warning'
            }
        }

    def action_link_to_partner(self):
        """
        Acción para vincular entidad con un partner de Odoo
        """
        return {
            'type': 'ir.actions.act_window',
            'name': 'Vincular con Cliente',
            'res_model': 'res.partner',
            'view_mode': 'tree,form',
            'target': 'new',
            'context': {
                'dialog_size': 'medium',
                'form_view_initial_mode': 'readonly'
            }
        }

    @api.model
    def get_root_entities(self):
        """Obtiene todas las entidades raíz (sin padre)"""
        return self.search([('parent_id', '=', False)], order='name')

    @api.model
    def get_entities_with_devices(self):
        """Obtiene entidades que tienen dispositivos asignados"""
        return self.search([('device_count', '>', 0)], order='name')

    @api.model
    def get_entities_needing_sync(self, hours=24):
        """
        Obtiene entidades que necesitan sincronización
        """
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(hours=hours)
        
        return self.search([
            ('auto_sync', '=', True),
            '|',
            ('last_sync', '=', False),
            ('last_sync', '<', cutoff_date)
        ], order='last_sync asc')

    def get_entity_summary(self):
        """
        Obtiene resumen completo de la entidad
        """
        self.ensure_one()
        
        return {
            'entity_info': {
                'name': self.name,
                'pt_entity_id': self.pt_entity_id,
                'level': self.level,
                'complete_path': self.complete_path,
                'partner': self.partner_id.name if self.partner_id else None
            },
            'hierarchy': {
                'parent': self.parent_id.name if self.parent_id else None,
                'children_count': self.child_count,
                'level': self.level
            },
            'devices': {
                'direct_count': self.device_count,
                'total_count': self.total_devices,
                'active_count': self.active_devices
            },
            'status': {
                'is_active': self.is_active,
                'last_sync': self.last_sync,
                'has_sync_error': bool(self.sync_error),
                'last_activity': self.last_device_activity,
                'has_low_supplies': self.has_low_supplies
            },
            'addresses_count': len(self.address_ids),
            'labels_count': len(self.label_ids)
        }

    def get_hierarchy_tree(self, max_depth=5):
        """
        Obtiene árbol jerárquico completo desde esta entidad
        """
        def build_tree(entity, current_depth=0):
            if current_depth >= max_depth:
                return None
            
            node = {
                'id': entity.id,
                'name': entity.name,
                'pt_entity_id': entity.pt_entity_id,
                'device_count': entity.device_count,
                'level': entity.level,
                'children': []
            }
            
            for child in entity.child_ids.filtered('is_active'):
                child_node = build_tree(child, current_depth + 1)
                if child_node:
                    node['children'].append(child_node)
            
            return node
        
        return build_tree(self)

    @api.model
    def cleanup_inactive_entities(self):
        """
        UTILIDAD: Limpia entidades inactivas sin dispositivos
        """
        inactive_entities = self.search([
            ('is_active', '=', False),
            ('device_count', '=', 0),
            ('child_count', '=', 0)
        ])
        
        count = len(inactive_entities)
        inactive_entities.unlink()
        
        _logger.info(f"🗑️ Limpieza: {count} entidades inactivas eliminadas")
        
        return count