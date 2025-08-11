from odoo import models, fields, api
import requests
import logging
import time
from datetime import datetime

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
    max_retries = fields.Integer('Reintentos Máximos', default=3)
    retry_delay = fields.Integer('Delay entre Reintentos (seg)', default=5)

    def _safe_int(self, value, default=0):
        """Convierte un valor a entero de forma segura"""
        try:
            if value is None or value == '' or value == 'N/A':
                return default
            # Si es string, quitar caracteres no numéricos
            if isinstance(value, str):
                value = ''.join(filter(str.isdigit, value))
                if not value:
                    return default
            return int(value)
        except (ValueError, TypeError):
            _logger.warning(f"⚠️ No se pudo convertir '{value}' a entero, usando {default}")
            return default

    def _retry_api_call(self, func, *args, **kwargs):
        """Wrapper para reintentar llamadas API fallidas"""
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise e
                _logger.warning(f"⚠️ Intento {attempt + 1} falló, reintentando en {self.retry_delay}s...")
                time.sleep(self.retry_delay)

    def test_connection(self):
        """Prueba la conexión con PrintTracker API"""
        try:
            _logger.info(f"🔍 Probando conexión a {self.api_url} con entidad {self.entity_bbbb_id}")
            
            def _test_call():
                return requests.get(
                    f'{self.api_url.rstrip("/")}/entity/{self.entity_bbbb_id}',
                    headers=self.get_api_headers(),
                    timeout=self.timeout_seconds
                )
            
            response = self._retry_api_call(_test_call)
            
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
            
            def _sync_call():
                return requests.get(
                    f'{self.api_url.rstrip("/")}/entity/{self.entity_bbbb_id}',
                    headers=self.get_api_headers(),
                    params={'includeChildren': True},
                    timeout=self.timeout_seconds
                )
            
            response = self._retry_api_call(_sync_call)
            
            if response.status_code == 200:
                data = response.json()
                
                # Crear/actualizar entidad principal
                self._sync_entity(data)
                
                # Sincronizar entidades hijas
                children_synced = 0
                if 'children' in data:
                    for child in data['children']:
                        def _child_call():
                            return requests.get(
                                f'{self.api_url.rstrip("/")}/entity/{child["id"]}',
                                headers=self.get_api_headers(),
                                timeout=self.timeout_seconds
                            )
                        
                        child_response = self._retry_api_call(_child_call)
                        
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
        """Sincroniza una entidad individual - SIMPLIFICADO"""
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
        """Sincroniza todos los dispositivos desde PrintTracker - SIMPLIFICADO"""
        try:
            _logger.info(f"🔄 Iniciando sincronización de dispositivos...")
            
            def _devices_call():
                return requests.get(
                    f'{self.api_url.rstrip("/")}/entity/{self.entity_bbbb_id}/device',
                    headers=self.get_api_headers(),
                    params={
                        'includeChildren': True,
                        'excludeDisabled': not self.solo_equipos_gestionados,
                        'limit': self.max_records_per_request
                    },
                    timeout=self.timeout_seconds
                )
            
            response = self._retry_api_call(_devices_call)
            
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
        LIMPIO: Sincroniza un dispositivo individual - Solo mapeo con alquiler
        NO actualiza contadores (eso va al cron consolidador)
        """
        try:
            serial_number = device_data.get('serialNumber')
            
            # Filtrar series inválidas
            if not serial_number or serial_number in ['notavailable', 'None', '', None]:
                _logger.info(f"⏭️ Saltando dispositivo con serie inválida: {serial_number}")
                return 'invalid_serial'
            
            # Buscar equipo existente por serie
            existing_device = self.env['alquiler'].search([
                ('serie', '=', serial_number)
            ], limit=1)
            
            if existing_device:
                # Buscar entidad correspondiente
                entity = self.env['printtracker.entity'].search([
                    ('pt_entity_id', '=', device_data.get('entityKey'))
                ], limit=1)
                
                # SOLO actualizar campos de mapeo PrintTracker - SIN CONTADORES
                update_values = {
                    'pt_device_id': device_data.get('id'),
                    'pt_entity_id': entity.id if entity else False,
                    'pt_last_sync': fields.Datetime.now()
                }
                
                # Campos adicionales si existen en el modelo alquiler
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
                
                existing_device.sudo().write(update_values)
                _logger.info(f"📝 Equipo mapeado con PrintTracker: {serial_number}")
                
                return 'updated'
            else:
                _logger.info(f"📋 Equipo en PrintTracker no registrado en Odoo: {serial_number}")
                return 'not_in_odoo'
                
        except Exception as e:
            _logger.error(f"❌ Error sincronizando dispositivo: {e}")
            return 'error'

    def sync_current_meters(self):
        """
        CORREGIDO: Sincroniza medidores actuales desde PrintTracker 
        CAMBIO CRÍTICO: Usa estructura 'default' en lugar de 'life'
        NO actualiza contadores de equipos (eso va al cron consolidador)
        """
        try:
            _logger.info(f"🔄 Iniciando sincronización de medidores actuales...")
            
            all_meters = []
            page = 1
            total_pages_processed = 0
            
            # Paginación completa: Obtener todos los medidores
            while True:
                _logger.info(f"📄 === PROCESANDO PÁGINA {page} ===")
                
                params = {
                    'includeChildren': True,
                    'excludeDisabled': not self.solo_equipos_gestionados,
                    'limit': self.max_records_per_request,
                    'page': page
                }
                
                def _meters_call():
                    return requests.get(
                        f'{self.api_url.rstrip("/")}/entity/{self.entity_bbbb_id}/currentMeter',
                        headers=self.get_api_headers(),
                        params=params,
                        timeout=self.timeout_seconds
                    )
                
                response = self._retry_api_call(_meters_call)
                
                _logger.info(f"📡 Respuesta API página {page}: Status {response.status_code}")
                
                if response.status_code == 200:
                    meters_page = response.json()
                    
                    _logger.info(f"📊 Página {page}: {len(meters_page)} medidores recibidos")
                    
                    if not meters_page:
                        _logger.info(f"📄 Página {page} vacía - Fin de datos")
                        break
                    
                    all_meters.extend(meters_page)
                    total_pages_processed += 1
                    
                    if len(meters_page) < self.max_records_per_request:
                        _logger.info(f"📄 Página {page} incompleta - Última página")
                        break
                    
                    page += 1
                    
                    # Límite de seguridad
                    if page > 50:
                        _logger.warning(f"⚠️ Límite de seguridad alcanzado: {page-1} páginas")
                        break
                        
                else:
                    error_msg = f'Error HTTP {response.status_code} en página {page}: {response.text}'
                    _logger.error(f"❌ Error de API: {error_msg}")
                    
                    if page == 1:
                        return {
                            'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'message': f'❌ Error sincronizando medidores: {error_msg}',
                                'type': 'danger'
                            }
                        }
                    else:
                        _logger.warning(f"⚠️ Error en página {page}, continuando con {len(all_meters)} medidores")
                        break
            
            # Procesar todos los medidores obtenidos
            _logger.info(f"🔄 === PROCESANDO {len(all_meters)} MEDIDORES ===")
            
            meters_synced = 0
            meters_failed = 0
            
            for i, meter_data in enumerate(all_meters):
                try:
                    if self._sync_meter(meter_data):
                        meters_synced += 1
                    else:
                        meters_failed += 1
                except Exception as e:
                    meters_failed += 1
                    _logger.error(f"❌ Error procesando medidor {i+1}: {e}")
                
                # Progreso cada 10 medidores
                if (i + 1) % 10 == 0:
                    _logger.info(f"📊 Progreso: {i+1}/{len(all_meters)} medidores procesados")
            
            # Resultado final
            _logger.info(f"🎯 === RESUMEN FINAL ===")
            _logger.info(f"📄 Páginas: {total_pages_processed}")
            _logger.info(f"📊 Total: {len(all_meters)}")
            _logger.info(f"✅ Exitosos: {meters_synced}")
            _logger.info(f"❌ Fallidos: {meters_failed}")
            
            if meters_synced > 0:
                message_type = 'success'
                if meters_failed > 0:
                    message = f'✅ Sincronización parcial: {meters_synced} éxitos, {meters_failed} fallos'
                else:
                    message = f'🎉 Sincronización completa: {meters_synced} medidores procesados'
            else:
                message_type = 'warning'
                message = f'⚠️ No se pudo procesar ningún medidor'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': message,
                    'type': message_type
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error sincronizando medidores: {e}")
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
        LIMPIO: Sincroniza un medidor individual 
        CORREGIDO: Usa estructura 'default' en lugar de 'life'
        SIMPLIFICADO: Solo guarda en printtracker.meter, NO actualiza equipos
        """
        try:
            device_key = meter_data.get('deviceKey')
            if not device_key:
                _logger.error("❌ No se proporcionó deviceKey")
                return False
            
            # Buscar equipo por pt_device_id
            device = self.env['alquiler'].search([
                ('pt_device_id', '=', device_key)
            ], limit=1)
            
            if not device:
                _logger.warning(f"⚠️ No se encontró equipo con pt_device_id: {device_key}")
                return False
            
            # CORRECCIÓN CRÍTICA: Usar 'default' en lugar de 'life'
            page_counts = meter_data.get('pageCounts', {})
            default_counts = page_counts.get('default', {})
            
            if not default_counts:
                _logger.warning(f"⚠️ No se encontró estructura 'default' en pageCounts")
                # Fallback: intentar con 'life' por compatibilidad
                default_counts = page_counts.get('life', {})
                if not default_counts:
                    _logger.error(f"❌ No se encontró estructura de contadores válida")
                    return False
            
            # Extraer todos los contadores disponibles
            meter_values = {
                'pt_meter_id': meter_data.get('id'),
                'device_id': device.id,
                'reading_date': self._parse_printtracker_datetime(meter_data.get('timestamp')),
                'console_status': meter_data.get('console'),
                
                # Contadores principales
                'total_pages_life': self._safe_int(default_counts.get('total', {}).get('value', 0)),
                'black_pages_life': self._safe_int(default_counts.get('totalBlack', {}).get('value', 0)),
                'color_pages_life': self._safe_int(default_counts.get('totalColor', {}).get('value', 0)),
                
                # NUEVOS CONTADORES DISPONIBLES
                'scan_pages': self._safe_int(default_counts.get('totalScans', {}).get('value', 0)),
                'copy_pages': self._safe_int(default_counts.get('totalCopies', {}).get('value', 0)),
                'fax_pages': self._safe_int(default_counts.get('totalFaxes', {}).get('value', 0)),
                'print_pages': self._safe_int(default_counts.get('totalPrints', {}).get('value', 0)),
                
                # Control de sincronización
                'sync_source': 'api',
                'last_sync': fields.Datetime.now()
            }
            
            # Buscar medidor existente
            existing_meter = self.env['printtracker.meter'].search([
                ('pt_meter_id', '=', meter_data.get('id'))
            ], limit=1)
            
            if existing_meter:
                existing_meter.write(meter_values)
                _logger.info(f"📝 Medidor actualizado: {device.serie}")
            else:
                self.env['printtracker.meter'].create(meter_values)
                _logger.info(f"🆕 Medidor creado: {device.serie}")
            
            return True
            
        except Exception as e:
            _logger.error(f"❌ Error sincronizando medidor: {e}")
            return False

    def _parse_printtracker_datetime(self, datetime_str):
        """Convierte fecha de PrintTracker (ISO 8601) a formato Odoo"""
        try:
            if not datetime_str:
                return None
            
            from datetime import datetime
            import re
            
            # PrintTracker: '2025-08-07T14:31:02.011Z'
            # Odoo: '2025-08-07 14:31:02'
            
            clean_datetime = re.sub(r'\.\d+Z?$', '', datetime_str)
            clean_datetime = clean_datetime.replace('T', ' ')
            clean_datetime = clean_datetime.replace('Z', '')
            
            try:
                parsed_dt = datetime.strptime(clean_datetime, '%Y-%m-%d %H:%M:%S')
                return parsed_dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                _logger.error(f"❌ Formato de fecha inválido: {datetime_str}")
                return None
                
        except Exception as e:
            _logger.error(f"❌ Error parseando fecha: {e}")
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
            'x-api-key': self.api_key,
            'Content-Type': 'application/json'
        }
    
    @api.model
    def get_active_config(self):
        """Obtiene la configuración activa"""
        config = self.search([('sync_enabled', '=', True)], limit=1)
        if not config:
            raise ValueError("No hay configuración activa de PrintTracker")
        return config