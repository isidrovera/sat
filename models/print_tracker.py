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

    def sync_all_entities(self):
        """Sincroniza todas las entidades desde PrintTracker"""
        try:
            _logger.info(f"🔄 Iniciando sincronización de entidades...")
            
            response = requests.get(
                f'{self.api_url.rstrip("/")}/entity/{self.entity_bbbb_id}',
                headers=self.get_api_headers(),
                params={'includeChildren': True},
                timeout=self.timeout_seconds
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Crear/actualizar entidad principal
                self._sync_entity(data)
                
                # Sincronizar entidades hijas
                children_synced = 0
                if 'children' in data:
                    for child in data['children']:
                        # Obtener datos completos de cada entidad hija
                        child_response = requests.get(
                            f'{self.api_url.rstrip("/")}/entity/{child["id"]}',
                            headers=self.get_api_headers(),
                            timeout=self.timeout_seconds
                        )
                        
                        if child_response.status_code == 200:
                            child_data = child_response.json()
                            self._sync_entity(child_data, parent_entity_id=data['id'])
                            children_synced += 1
                
                self.last_sync_date = fields.Datetime.now()
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'✅ Sincronización completa: 1 entidad principal + {children_synced} entidades hijas',
                        'type': 'success'
                    }
                }
            else:
                error_msg = f'Error HTTP {response.status_code}: {response.text}'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'❌ Error sincronizando entidades: {error_msg}',
                        'type': 'danger'
                    }
                }
                
        except Exception as e:
            _logger.error(f"❌ Error sincronizando entidades: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'❌ Error: {str(e)}',
                    'type': 'danger'
                }
            }

    def _sync_entity(self, entity_data, parent_entity_id=None):
        """Sincroniza una entidad individual"""
        try:
            # Buscar si ya existe
            existing_entity = self.env['printtracker.entity'].search([
                ('pt_entity_id', '=', entity_data['id'])
            ], limit=1)
            
            # Buscar entidad padre
            parent_entity = None
            if parent_entity_id:
                parent_entity = self.env['printtracker.entity'].search([
                    ('pt_entity_id', '=', parent_entity_id)
                ], limit=1)
            
            entity_values = {
                'pt_entity_id': entity_data['id'],
                'name': entity_data.get('name', 'Sin nombre'),
                'genealogy': str(entity_data.get('genealogy', [])),
                'parent_id': parent_entity.id if parent_entity else False,
                'last_sync': fields.Datetime.now(),
                'sync_error': False,
                'is_active': True
            }
            
            if existing_entity:
                existing_entity.write(entity_values)
                _logger.info(f"📝 Entidad actualizada: {entity_data.get('name')}")
            else:
                new_entity = self.env['printtracker.entity'].create(entity_values)
                _logger.info(f"🆕 Entidad creada: {entity_data.get('name')}")
                
                # Sincronizar direcciones y labels
                if 'addresses' in entity_data:
                    new_entity._sync_addresses(entity_data['addresses'])
                if 'labels' in entity_data:
                    new_entity._sync_labels(entity_data['labels'])
                    
        except Exception as e:
            _logger.error(f"❌ Error sincronizando entidad {entity_data.get('name')}: {e}")

    def sync_all_devices(self):
        """Sincroniza todos los dispositivos desde PrintTracker"""
        try:
            _logger.info(f"🔄 Iniciando sincronización de dispositivos...")
            
            response = requests.get(
                f'{self.api_url.rstrip("/")}/entity/{self.entity_bbbb_id}/device',
                headers=self.get_api_headers(),
                params={
                    'includeChildren': True,
                    'excludeDisabled': False,
                    'limit': self.max_records_per_request
                },
                timeout=self.timeout_seconds
            )
            
            if response.status_code == 200:
                devices = response.json()
                devices_synced = 0
                devices_updated = 0
                
                for device_data in devices:
                    result = self._sync_device(device_data)
                    if result == 'created':
                        devices_synced += 1
                    elif result == 'updated':
                        devices_updated += 1
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'✅ Dispositivos sincronizados: {devices_synced} nuevos, {devices_updated} actualizados',
                        'type': 'success'
                    }
                }
            else:
                error_msg = f'Error HTTP {response.status_code}: {response.text}'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'❌ Error sincronizando dispositivos: {error_msg}',
                        'type': 'danger'
                    }
                }
                
        except Exception as e:
            _logger.error(f"❌ Error sincronizando dispositivos: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'❌ Error: {str(e)}',
                    'type': 'danger'
                }
            }

    def _sync_device(self, device_data):
        """
        MÉTODO CORREGIDO: Sincroniza un dispositivo individual - Solo equipos existentes
        Busca por serie y actualiza campos correctos
        """
        try:
            serial_number = device_data.get('serialNumber')
            
            # ✅ FILTRAR series inválidas
            if not serial_number or serial_number in ['notavailable', 'None', '', None]:
                _logger.info(f"⏭️ Saltando dispositivo con serie inválida: {serial_number}")
                return 'invalid_serial'
            
            # ✅ Buscar equipo existente por serie (campo correcto)
            existing_device = self.env['alquiler'].search([
                ('serie', '=', serial_number)
            ], limit=1)
            
            if existing_device:
                # ✅ Buscar entidad correspondiente
                entity = self.env['printtracker.entity'].search([
                    ('pt_entity_id', '=', device_data.get('entityKey'))
                ], limit=1)
                
                # ✅ PREPARAR CAMPOS DE ACTUALIZACIÓN
                update_values = {}
                
                # Campos de PrintTracker (solo si existen en el modelo)
                if hasattr(existing_device, 'pt_device_id'):
                    update_values['pt_device_id'] = device_data.get('id')
                
                if hasattr(existing_device, 'pt_entity_id'):
                    update_values['pt_entity_id'] = entity.id if entity else False
                
                if hasattr(existing_device, 'mac_address'):
                    update_values['mac_address'] = device_data.get('macAddress')
                
                if hasattr(existing_device, 'ip_address'):
                    update_values['ip_address'] = device_data.get('ipAddress')
                
                if hasattr(existing_device, 'custom_location'):
                    update_values['custom_location'] = device_data.get('customLocation')
                
                if hasattr(existing_device, 'asset_id'):
                    update_values['asset_id'] = device_data.get('assetID')
                
                if hasattr(existing_device, 'is_managed'):
                    update_values['is_managed'] = device_data.get('managed', True)
                
                # ✅ SOLO ACTUALIZAR SI HAY CAMPOS VÁLIDOS
                if update_values:
                    existing_device.sudo().write(update_values)
                    _logger.info(f"📝 Equipo actualizado: {serial_number} con campos PrintTracker")
                else:
                    _logger.info(f"📝 Equipo encontrado: {serial_number} (sin campos PrintTracker para actualizar)")
                
                return 'updated'
            else:
                # ✅ NO crear automáticamente, solo loggear
                _logger.info(f"📋 Equipo en PrintTracker no registrado en Odoo: {serial_number}")
                return 'not_in_odoo'
                
        except Exception as e:
            _logger.error(f"❌ Error sincronizando dispositivo: {e}")
            return 'error'
    # AGREGAR ESTE MÉTODO A PrintTrackerConfig

    def _parse_printtracker_datetime(self, datetime_str):
        """
        Convierte fecha de PrintTracker (ISO 8601) a formato Odoo
        """
        try:
            if not datetime_str:
                return None
            
            # PrintTracker format: '2023-09-01T20:25:58.672Z'
            # Odoo format: '2023-09-01 20:25:58'
            
            from datetime import datetime
            import re
            
            # Remover microsegundos y Z
            clean_datetime = re.sub(r'\.\d+Z?$', '', datetime_str)
            clean_datetime = clean_datetime.replace('T', ' ')
            clean_datetime = clean_datetime.replace('Z', '')
            
            # Verificar formato válido
            try:
                parsed_dt = datetime.strptime(clean_datetime, '%Y-%m-%d %H:%M:%S')
                return parsed_dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                _logger.error(f"❌ Formato de fecha inválido: {datetime_str}")
                return None
                
        except Exception as e:
            _logger.error(f"❌ Error parseando fecha: {e}")
            return None
    def sync_current_meters(self):
        """
        MÉTODO CORREGIDO: Sincroniza medidores actuales desde PrintTracker
        CORRECCIÓN: Agregado parámetro 'page' requerido por la API
        """
        try:
            _logger.info(f"🔄 Iniciando sincronización de medidores actuales...")
            
            # ✅ CORRECCIÓN: Agregar parámetro 'page' requerido por la API
            params = {
                'includeChildren': True,
                'excludeDisabled': False,
                'limit': self.max_records_per_request,
                'page': 1  # ← NUEVO: PrintTracker requiere page >= 1
            }
            
            _logger.info(f"📊 Parámetros de consulta: {params}")
            
            response = requests.get(
                f'{self.api_url.rstrip("/")}/entity/{self.entity_bbbb_id}/currentMeter',
                headers=self.get_api_headers(),
                params=params,
                timeout=self.timeout_seconds
            )
            
            _logger.info(f"📡 Respuesta API medidores: Status {response.status_code}")
            
            if response.status_code == 200:
                meters = response.json()
                
                # ✅ LOGGING CRÍTICO PARA DEBUG
                _logger.info(f"📊 Respuesta API medidores: {len(meters)} medidores recibidos")
                
                if not meters:
                    _logger.warning("⚠️ No se recibieron medidores de la API")
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'message': '⚠️ No se encontraron medidores en PrintTracker',
                            'type': 'warning'
                        }
                    }
                
                meters_synced = 0
                
                for i, meter_data in enumerate(meters):
                    _logger.info(f"🔍 === PROCESANDO MEDIDOR {i+1}/{len(meters)} ===")
                    _logger.info(f"📊 Medidor ID: {meter_data.get('id', 'Sin ID')}")
                    _logger.info(f"🎯 Device Key: {meter_data.get('deviceKey', 'Sin deviceKey')}")
                    
                    # ✅ LOGGING DE ESTRUCTURA DE DATOS
                    page_counts = meter_data.get('pageCounts', {})
                    life_counts = page_counts.get('life', {})
                    _logger.info(f"📄 Datos de contadores disponibles:")
                    _logger.info(f"   Total: {life_counts.get('total', {}).get('value', 'N/A')}")
                    _logger.info(f"   Black: {life_counts.get('totalBlack', {}).get('value', 'N/A')}")
                    _logger.info(f"   Color: {life_counts.get('totalColor', {}).get('value', 'N/A')}")
                    
                    try:
                        if self._sync_meter(meter_data):
                            meters_synced += 1
                            _logger.info(f"✅ Medidor {i+1} procesado exitosamente")
                        else:
                            _logger.warning(f"⚠️ Medidor {i+1} no pudo ser procesado")
                    except Exception as e:
                        _logger.error(f"❌ Error procesando medidor {i+1}: {e}")
                
                # ✅ RESULTADO FINAL DETALLADO
                _logger.info(f"🎯 === RESUMEN SINCRONIZACIÓN MEDIDORES ===")
                _logger.info(f"📊 Total recibidos: {len(meters)}")
                _logger.info(f"✅ Procesados exitosamente: {meters_synced}")
                _logger.info(f"❌ Fallidos: {len(meters) - meters_synced}")
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'✅ Medidores sincronizados: {meters_synced} de {len(meters)} lecturas procesadas',
                        'type': 'success'
                    }
                }
            else:
                error_msg = f'Error HTTP {response.status_code}: {response.text}'
                _logger.error(f"❌ Error de API: {error_msg}")
                
                # ✅ LOGGING ADICIONAL PARA DEBUG
                _logger.error(f"🔍 URL consultada: {self.api_url.rstrip('/')}/entity/{self.entity_bbbb_id}/currentMeter")
                _logger.error(f"🔍 Headers: {self.get_api_headers()}")
                _logger.error(f"🔍 Parámetros: {params}")
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'❌ Error sincronizando medidores: {error_msg}',
                        'type': 'danger'
                    }
                }
                
        except Exception as e:
            _logger.error(f"❌ Error sincronizando medidores: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'❌ Error: {str(e)}',
                    'type': 'danger'
                }
            }

    def _sync_meter(self, meter_data):
        """
        MÉTODO CORREGIDO: Sincroniza un medidor individual
        SOLUCIÓN FINAL: Usar datos de sincronización de dispositivos existentes
        """
        try:
            _logger.info(f"🔍 === PROCESANDO MEDIDOR ===")
            _logger.info(f"📊 Medidor ID: {meter_data.get('id', 'Sin ID')}")
            
            device_key = meter_data.get('deviceKey')
            _logger.info(f"🎯 Device Key: {device_key}")
            
            if not device_key:
                _logger.error("❌ No se proporcionó deviceKey en los datos del medidor")
                return False
            
            # ✅ ESTRATEGIA 1: Buscar por pt_device_id (si existe)
            device = self.env['alquiler'].search([
                ('pt_device_id', '=', device_key)
            ], limit=1)
            
            if device:
                _logger.info(f"✅ Dispositivo encontrado por pt_device_id: {device.serie} (ID: {device.id})")
            else:
                # ✅ ESTRATEGIA 2: Buscar en los datos de dispositivos sincronizados
                _logger.info(f"🔄 Dispositivo no encontrado por pt_device_id, buscando en datos sincronizados...")
                
                # Obtener lista completa de dispositivos de PrintTracker
                serie_equipo = self._find_serie_in_synced_devices(device_key)
                
                if serie_equipo:
                    _logger.info(f"📋 Serie encontrada en datos sincronizados: {serie_equipo}")
                    
                    # Buscar por serie en Odoo
                    device = self.env['alquiler'].search([
                        ('serie', '=', serie_equipo)
                    ], limit=1)
                    
                    if device:
                        _logger.info(f"✅ Dispositivo encontrado por serie: {device.serie} (ID: {device.id})")
                        
                        # ✅ IMPORTANTE: Actualizar pt_device_id para futuras sincronizaciones
                        try:
                            device.write({'pt_device_id': device_key})
                            _logger.info(f"🔗 pt_device_id actualizado: {device.serie} → {device_key}")
                        except Exception as e:
                            _logger.warning(f"⚠️ No se pudo actualizar pt_device_id: {e}")
                    else:
                        _logger.error(f"❌ Equipo con serie {serie_equipo} no encontrado en Odoo")
                        return False
                else:
                    _logger.error(f"❌ No se encontró serie para deviceKey: {device_key}")
                    _logger.error(f"💡 SOLUCIÓN: Ejecutar 'Sincronizar Dispositivos' primero")
                    return False
            
            # ✅ CONTINUAR CON PROCESAMIENTO NORMAL
            # ... resto del código de procesamiento de medidor
            
            # Crear o actualizar registro de medidor
            existing_meter = self.env['printtracker.meter'].search([
                ('pt_meter_id', '=', meter_data.get('id'))
            ], limit=1)
            
            # Extraer contadores de páginas
            page_counts = meter_data.get('pageCounts', {})
            life_counts = page_counts.get('life', {})
            equiv_counts = page_counts.get('equiv', {})
            
            # ✅ LOGGING DE DATOS EXTRAÍDOS
            _logger.info(f"📊 Contadores extraídos de PrintTracker:")
            _logger.info(f"   Total Life: {life_counts.get('total', {}).get('value', 0)}")
            _logger.info(f"   Black Life: {life_counts.get('totalBlack', {}).get('value', 0)}")
            _logger.info(f"   Color Life: {life_counts.get('totalColor', {}).get('value', 0)}")
            
            meter_values = {
                'pt_meter_id': meter_data.get('id'),
                'device_id': device.id,
                'reading_date': self._parse_printtracker_datetime(meter_data.get('timestamp')),  # ← CORRECCIÓN
                'console_status': meter_data.get('console'),
                'total_pages_life': life_counts.get('total', {}).get('value', 0),
                'black_pages_life': life_counts.get('totalBlack', {}).get('value', 0),
                'color_pages_life': life_counts.get('totalColor', {}).get('value', 0),
                'total_pages_equiv': equiv_counts.get('total', {}).get('value', 0),
                'black_pages_equiv': equiv_counts.get('totalBlack', {}).get('value', 0),
                'color_pages_equiv': equiv_counts.get('totalColor', {}).get('value', 0),
                'sync_source': 'api',
                'last_sync': fields.Datetime.now()
            }
            
            # ✅ ACTUALIZAR O CREAR MEDIDOR
            meter_record = None
            if existing_meter:
                _logger.info(f"📝 Actualizando medidor existente: {existing_meter.pt_meter_id}")
                existing_meter.write(meter_values)
                meter_record = existing_meter
            else:
                _logger.info(f"🆕 Creando nuevo medidor: {meter_data.get('id')}")
                meter_record = self.env['printtracker.meter'].create(meter_values)
            
            # ✅ SIEMPRE actualizar contadores del equipo
            _logger.info(f"🔄 Actualizando contadores del equipo...")
            if meter_record.update_device_counters():
                _logger.info(f"✅ Contadores del equipo actualizados exitosamente")
            else:
                _logger.warning(f"⚠️ No se pudieron actualizar los contadores del equipo")
            
            return True
            
        except Exception as e:
            _logger.error(f"❌ Error sincronizando medidor: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _find_serie_in_synced_devices(self, device_key):
        """
        OPTIMIZADO: Busca la serie en datos sincronizados con cache
        """
        try:
            # Cache estático para evitar múltiples consultas API
            if not hasattr(self, '_device_cache'):
                _logger.info(f"🔍 Cargando cache de dispositivos...")
                
                response = requests.get(
                    f'{self.api_url.rstrip("/")}/entity/{self.entity_bbbb_id}/device',
                    headers=self.get_api_headers(),
                    params={
                        'includeChildren': True,
                        'excludeDisabled': False,
                        'limit': 2000  # Límite alto para obtener todos
                    },
                    timeout=self.timeout_seconds
                )
                
                if response.status_code == 200:
                    devices = response.json()
                    _logger.info(f"📊 Cache cargado: {len(devices)} dispositivos")
                    
                    # Crear diccionario para búsqueda rápida
                    self._device_cache = {}
                    for device_data in devices:
                        device_id = device_data.get('id')
                        serie = device_data.get('serialNumber')
                        
                        if device_id and serie and serie not in ['notavailable', 'None', '', None]:
                            self._device_cache[device_id] = serie
                    
                    _logger.info(f"📋 Cache procesado: {len(self._device_cache)} dispositivos válidos")
                else:
                    _logger.error(f"❌ Error cargando cache: {response.status_code}")
                    self._device_cache = {}
            
            # Buscar en cache
            serie = self._device_cache.get(device_key)
            if serie:
                _logger.info(f"✅ Serie encontrada en cache: {serie} para deviceKey: {device_key}")
                return serie
            else:
                _logger.warning(f"❌ DeviceKey {device_key} no encontrado en cache de {len(self._device_cache)} dispositivos")
                return None
                
        except Exception as e:
            _logger.error(f"❌ Error en búsqueda optimizada: {e}")
            return None

    def sync_all_data(self):
        """Sincroniza todos los datos: entidades, dispositivos y medidores"""
        try:
            _logger.info(f"🔄 === SINCRONIZACIÓN COMPLETA INICIADA ===")
            
            # 1. Sincronizar entidades
            entities_result = self.sync_all_entities()
            if entities_result['params']['type'] != 'success':
                return entities_result
            
            # 2. Sincronizar dispositivos
            devices_result = self.sync_all_devices()
            if devices_result['params']['type'] != 'success':
                return devices_result
            
            # 3. Sincronizar medidores
            meters_result = self.sync_current_meters()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': '🎉 Sincronización completa finalizada exitosamente\nRevisa los menús de PrintTracker para ver los datos.',
                    'type': 'success'
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error en sincronización completa: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'❌ Error en sincronización completa: {str(e)}',
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
        """
        MÉTODO COMPLETO: Actualiza los contadores del equipo con validación de incrementos,
        verificación post-actualización y manejo de campos con tracking
        """
        try:
            _logger.info(f"💾 === INICIANDO ACTUALIZACIÓN PRINTTRACKER ===")
            
            # 1. OBTENER SERIE DEL DISPOSITIVO
            if not self.device_id:
                _logger.error("❌ No hay device_id asociado al medidor")
                return False
            
            # 2. BUSCAR EQUIPO POR SERIE (como hacen los otros métodos)
            serie_equipo = self.device_id.serie
            if not serie_equipo:
                _logger.error("❌ El dispositivo no tiene serie definida")
                return False
            
            # Buscar equipo en el modelo alquiler por serie
            equipo = self.env['alquiler'].search([('serie', '=', serie_equipo)], limit=1)
            if not equipo:
                _logger.error(f"❌ No se encontró equipo con serie: {serie_equipo}")
                return False
            
            _logger.info(f"🎯 Equipo encontrado: ID={equipo.id}, Serie={serie_equipo}")
            _logger.info(f"🔍 Equipo modelo: {equipo.name.name if equipo.name else 'Sin modelo'}")
            _logger.info(f"🔍 Equipo cliente: {equipo.cliente_id.name if equipo.cliente_id else 'Sin cliente'}")
            
            # 3. PREPARAR NUEVOS VALORES DESDE PRINTTRACKER
            nuevos_valores = {
                'contador_bn': self.black_pages_life or 0,
                'contador_color': self.color_pages_life or 0,
                'contador_scan': self.scan_pages or 0
            }
            
            _logger.info(f"📊 Nuevos valores desde PrintTracker:")
            _logger.info(f"   Contador BN: {nuevos_valores['contador_bn']}")
            _logger.info(f"   Contador Color: {nuevos_valores['contador_color']}")
            _logger.info(f"   Contador Scan: {nuevos_valores['contador_scan']}")
            
            # 4. OBTENER VALORES ACTUALES DEL EQUIPO
            valores_actuales = {
                'contador_bn': equipo.contador_bn or 0,
                'contador_color': equipo.contador_color or 0,
                'contador_scan': equipo.contador_scan or 0
            }
            
            _logger.info(f"📋 Valores actuales del equipo:")
            _logger.info(f"   Contador BN actual: {valores_actuales['contador_bn']}")
            _logger.info(f"   Contador Color actual: {valores_actuales['contador_color']}")
            _logger.info(f"   Contador Scan actual: {valores_actuales['contador_scan']}")
            _logger.info(f"   Fecha última actualización: {equipo.fecha_ultima_actualizacion or 'Nunca'}")
            
            # 5. VALIDAR INCREMENTOS Y PREPARAR ACTUALIZACIÓN
            valores_actualizacion = {}
            alertas = []
            hay_cambios = False
            
            _logger.info(f"🔍 === VALIDANDO INCREMENTOS ===")
            
            # Validar contador B/N
            nuevo_bn = nuevos_valores['contador_bn']
            actual_bn = valores_actuales['contador_bn']
            
            _logger.info(f"🖤 Validando BN: actual={actual_bn}, nuevo={nuevo_bn}")
            
            if nuevo_bn > actual_bn:
                valores_actualizacion['contador_bn'] = nuevo_bn
                hay_cambios = True
                incremento = nuevo_bn - actual_bn
                _logger.info(f"✅ BN: {actual_bn} → {nuevo_bn} (+{incremento})")
            elif nuevo_bn < actual_bn and nuevo_bn > 0:
                # Permitir decrementos (posible reset de equipo)
                valores_actualizacion['contador_bn'] = nuevo_bn
                alertas.append("BN decrementó - posible reset de equipo")
                hay_cambios = True
                decremento = actual_bn - nuevo_bn
                _logger.warning(f"⚠️ BN decrementó: {actual_bn} → {nuevo_bn} (-{decremento})")
            elif nuevo_bn == actual_bn:
                _logger.info(f"📍 BN sin cambios: {actual_bn}")
            else:
                _logger.info(f"⏭️ BN no actualizado: nuevo({nuevo_bn}) <= actual({actual_bn})")
            
            # Validar contador Color
            nuevo_color = nuevos_valores['contador_color']
            actual_color = valores_actuales['contador_color']
            
            _logger.info(f"🎨 Validando Color: actual={actual_color}, nuevo={nuevo_color}")
            
            if nuevo_color > actual_color:
                valores_actualizacion['contador_color'] = nuevo_color
                hay_cambios = True
                incremento = nuevo_color - actual_color
                _logger.info(f"✅ Color: {actual_color} → {nuevo_color} (+{incremento})")
            elif nuevo_color < actual_color and nuevo_color > 0:
                valores_actualizacion['contador_color'] = nuevo_color
                alertas.append("Color decrementó - posible reset de equipo")
                hay_cambios = True
                decremento = actual_color - nuevo_color
                _logger.warning(f"⚠️ Color decrementó: {actual_color} → {nuevo_color} (-{decremento})")
            elif nuevo_color == actual_color:
                _logger.info(f"📍 Color sin cambios: {actual_color}")
            else:
                _logger.info(f"⏭️ Color no actualizado: nuevo({nuevo_color}) <= actual({actual_color})")
            
            # Validar contador Scan
            nuevo_scan = nuevos_valores['contador_scan']
            actual_scan = valores_actuales['contador_scan']
            
            _logger.info(f"📄 Validando Scan: actual={actual_scan}, nuevo={nuevo_scan}")
            
            if nuevo_scan > actual_scan:
                valores_actualizacion['contador_scan'] = nuevo_scan
                hay_cambios = True
                incremento = nuevo_scan - actual_scan
                _logger.info(f"✅ Scan: {actual_scan} → {nuevo_scan} (+{incremento})")
            elif nuevo_scan < actual_scan and nuevo_scan > 0:
                valores_actualizacion['contador_scan'] = nuevo_scan
                alertas.append("Scan decrementó - posible reset de equipo")
                hay_cambios = True
                decremento = actual_scan - nuevo_scan
                _logger.warning(f"⚠️ Scan decrementó: {actual_scan} → {nuevo_scan} (-{decremento})")
            elif nuevo_scan == actual_scan:
                _logger.info(f"📍 Scan sin cambios: {actual_scan}")
            else:
                _logger.info(f"⏭️ Scan no actualizado: nuevo({nuevo_scan}) <= actual({actual_scan})")
            
            # 6. SIEMPRE ACTUALIZAR FECHA (USAR CAMPO CORRECTO)
            fecha_lectura = self.reading_date or fields.Datetime.now()
            valores_actualizacion['fecha_ultima_actualizacion'] = fecha_lectura
            _logger.info(f"📅 Fecha de actualización: {fecha_lectura}")
            
            # 7. EJECUTAR ACTUALIZACIÓN SI HAY CAMBIOS
            _logger.info(f"🔍 === EVALUANDO ACTUALIZACIÓN ===")
            _logger.info(f"📊 Hay cambios en contadores: {hay_cambios}")
            _logger.info(f"📊 Valores a actualizar: {len(valores_actualizacion)} campos")
            
            if hay_cambios or valores_actualizacion:
                _logger.info(f"💾 === EJECUTANDO ACTUALIZACIÓN ===")
                _logger.info(f"📊 Datos de actualización: {valores_actualizacion}")
                
                try:
                    # ✅ CORRECCIÓN: Usar contexto especial para campos tracked
                    _logger.info(f"🔐 Preparando contexto para actualización...")
                    
                    equipo_with_context = equipo.sudo().with_context(
                        tracking_disable=False,  # Permitir tracking
                        mail_notrack=False,      # Permitir notificaciones
                        from_printtracker=True,  # Marcar origen
                        check_company_ids=False  # Sin validación de compañía
                    )
                    
                    _logger.info(f"💾 Ejecutando write() con contexto especial...")
                    
                    # Ejecutar actualización con contexto
                    equipo_with_context.write(valores_actualizacion)
                    
                    _logger.info(f"✅ Write() ejecutado exitosamente")
                    
                    # ✅ VERIFICACIÓN INMEDIATA POST-ACTUALIZACIÓN
                    _logger.info(f"🔍 === VERIFICACIÓN POST-ACTUALIZACIÓN ===")
                    
                    # Recargar desde base de datos
                    equipo.refresh()
                    
                    _logger.info(f"📊 Estado actual del equipo después de write():")
                    _logger.info(f"   Serie: {equipo.serie}")
                    _logger.info(f"   ID: {equipo.id}")
                    _logger.info(f"   BN actual: {equipo.contador_bn}")
                    _logger.info(f"   Color actual: {equipo.contador_color}")
                    _logger.info(f"   Scan actual: {equipo.contador_scan}")
                    _logger.info(f"   Fecha actualización: {equipo.fecha_ultima_actualizacion}")
                    
                    # Verificar si los valores se aplicaron correctamente
                    valores_verificados = True
                    errores_verificacion = []
                    
                    if 'contador_bn' in valores_actualizacion:
                        esperado = valores_actualizacion['contador_bn']
                        actual = equipo.contador_bn
                        if actual != esperado:
                            valores_verificados = False
                            error_msg = f"BN esperado: {esperado}, actual: {actual}"
                            errores_verificacion.append(error_msg)
                            _logger.error(f"❌ ERROR BN: {error_msg}")
                        else:
                            _logger.info(f"✅ BN verificado correctamente: {actual}")
                    
                    if 'contador_color' in valores_actualizacion:
                        esperado = valores_actualizacion['contador_color']
                        actual = equipo.contador_color
                        if actual != esperado:
                            valores_verificados = False
                            error_msg = f"Color esperado: {esperado}, actual: {actual}"
                            errores_verificacion.append(error_msg)
                            _logger.error(f"❌ ERROR Color: {error_msg}")
                        else:
                            _logger.info(f"✅ Color verificado correctamente: {actual}")
                    
                    if 'contador_scan' in valores_actualizacion:
                        esperado = valores_actualizacion['contador_scan']
                        actual = equipo.contador_scan
                        if actual != esperado:
                            valores_verificados = False
                            error_msg = f"Scan esperado: {esperado}, actual: {actual}"
                            errores_verificacion.append(error_msg)
                            _logger.error(f"❌ ERROR Scan: {error_msg}")
                        else:
                            _logger.info(f"✅ Scan verificado correctamente: {actual}")
                    
                    if valores_verificados:
                        _logger.info(f"🎉 TODOS LOS VALORES SE APLICARON CORRECTAMENTE")
                    else:
                        _logger.error(f"💥 ERRORES EN VERIFICACIÓN:")
                        for error in errores_verificacion:
                            _logger.error(f"   - {error}")
                        
                        # Intentar con contexto de bypass
                        _logger.info(f"🔄 Reintentando con contexto de bypass...")
                        try:
                            equipo_bypass = equipo.sudo().with_context(
                                tracking_disable=True,   # Deshabilitar tracking
                                mail_notrack=True,       # Sin notificaciones
                                check_company_ids=False, # Sin validación de compañía
                                bypass_company_validation=True
                            )
                            equipo_bypass.write(valores_actualizacion)
                            
                            equipo.refresh()
                            _logger.info(f"✅ Actualización exitosa con contexto de bypass")
                            _logger.info(f"   BN: {equipo.contador_bn}, Color: {equipo.contador_color}, Scan: {equipo.contador_scan}")
                            
                        except Exception as bypass_error:
                            _logger.error(f"❌ Error incluso con bypass: {bypass_error}")
                            _logger.error(f"🔍 Tipo de error bypass: {type(bypass_error).__name__}")
                    
                except Exception as write_error:
                    _logger.error(f"❌ === ERROR EN WRITE() ===")
                    _logger.error(f"💥 Error: {write_error}")
                    _logger.error(f"🔍 Tipo de error: {type(write_error).__name__}")
                    
                    # Log adicional del error
                    import traceback
                    _logger.error(f"📋 Traceback completo:")
                    _logger.error(f"{traceback.format_exc()}")
                    
                    return False
                
                # 8. REGISTRAR EN CHATTER DEL EQUIPO
                if hay_cambios:
                    _logger.info(f"📝 === REGISTRANDO EN CHATTER ===")
                    
                    try:
                        mensaje_cambios = []
                        if 'contador_bn' in valores_actualizacion:
                            mensaje_cambios.append(f"BN: {valores_actuales['contador_bn']} → {valores_actualizacion['contador_bn']}")
                        if 'contador_color' in valores_actualizacion:
                            mensaje_cambios.append(f"Color: {valores_actuales['contador_color']} → {valores_actualizacion['contador_color']}")
                        if 'contador_scan' in valores_actualizacion:
                            mensaje_cambios.append(f"Scan: {valores_actuales['contador_scan']} → {valores_actualizacion['contador_scan']}")
                        
                        mensaje = f"📊 Contadores actualizados vía PrintTracker:\n" + "\n".join(mensaje_cambios)
                        if alertas:
                            mensaje += f"\n\n⚠️ Alertas: " + "; ".join(alertas)
                        
                        equipo.message_post(
                            body=mensaje,
                            message_type='notification',
                            subtype_xmlid='mail.mt_note'
                        )
                        
                        _logger.info(f"✅ Mensaje registrado en chatter")
                        
                    except Exception as chatter_error:
                        _logger.warning(f"⚠️ Error registrando en chatter: {chatter_error}")
                
            else:
                _logger.info(f"ℹ️ No hay cambios que aplicar al equipo")
            
            # 9. ACTUALIZAR RELACIÓN PRINTTRACKER (SOLO REFERENCIAS)
            _logger.info(f"🔗 === ACTUALIZANDO REFERENCIAS PRINTTRACKER ===")
            
            try:
                referencias_actualizadas = {}
                
                if hasattr(equipo, 'ultimo_medidor_pt'):
                    referencias_actualizadas['ultimo_medidor_pt'] = self.id
                    _logger.info(f"🔗 Actualizando ultimo_medidor_pt: {self.id}")
                
                if hasattr(equipo, 'fecha_ultima_lectura'):
                    referencias_actualizadas['fecha_ultima_lectura'] = self.reading_date
                    _logger.info(f"🔗 Actualizando fecha_ultima_lectura: {self.reading_date}")
                
                if referencias_actualizadas:
                    equipo.sudo().write(referencias_actualizadas)
                    _logger.info(f"✅ Referencias PrintTracker actualizadas")
                else:
                    _logger.info(f"ℹ️ No hay referencias PrintTracker para actualizar")
                    
            except Exception as ref_error:
                _logger.warning(f"⚠️ No se pudieron actualizar referencias PrintTracker: {ref_error}")
            
            _logger.info(f"🎉 === ACTUALIZACIÓN PRINTTRACKER COMPLETADA EXITOSAMENTE ===")
            return True
            
        except Exception as e:
            _logger.error(f"❌ === ERROR GENERAL EN ACTUALIZACIÓN ===")
            _logger.error(f"💥 Error: {e}")
            _logger.error(f"🔍 Tipo de error: {type(e).__name__}")
            
            import traceback
            _logger.error(f"📋 Traceback completo:")
            _logger.error(f"{traceback.format_exc()}")
            
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



