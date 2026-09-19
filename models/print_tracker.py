from odoo import _, models, fields, api
from odoo.exceptions import UserError

import requests
import logging
import time
import json
from datetime import datetime, timedelta
from html import escape
from lxml import etree

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
        """Sincroniza todos los dispositivos desde PrintTracker - CON PAGINACIÓN"""
        try:
            _logger.info(f"🔄 Iniciando sincronización de dispositivos...")
            
            all_devices = []
            page = 1
            total_pages_processed = 0
            
            # PAGINACIÓN COMPLETA: Obtener todos los dispositivos
            while True:
                _logger.info(f"📄 === PROCESANDO PÁGINA {page} ===")
                
                params = {
                    'includeChildren': True,
                    'excludeDisabled': not self.solo_equipos_gestionados,
                    'limit': self.max_records_per_request,
                    'page': page  # ← ESTE PARÁMETRO FALTABA
                }
                
                def _devices_call():
                    return requests.get(
                        f'{self.api_url.rstrip("/")}/entity/{self.entity_bbbb_id}/device',
                        headers=self.get_api_headers(),
                        params=params,
                        timeout=self.timeout_seconds
                    )
                
                response = self._retry_api_call(_devices_call)
                
                _logger.info(f"📡 Respuesta API página {page}: Status {response.status_code}")
                
                if response.status_code == 200:
                    devices_page = response.json()
                    
                    _logger.info(f"📊 Página {page}: {len(devices_page)} dispositivos recibidos")
                    
                    if not devices_page:
                        _logger.info(f"📄 Página {page} vacía - Fin de datos")
                        break
                    
                    all_devices.extend(devices_page)
                    total_pages_processed += 1
                    
                    # Si la página está incompleta, es la última
                    if len(devices_page) < self.max_records_per_request:
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
                                'message': f'❌ Error sincronizando dispositivos: {error_msg}',
                                'type': 'danger'
                            }
                        }
                    else:
                        _logger.warning(f"⚠️ Error en página {page}, continuando con {len(all_devices)} dispositivos")
                        break
            
            # PROCESAR TODOS LOS DISPOSITIVOS OBTENIDOS
            _logger.info(f"🔄 === PROCESANDO {len(all_devices)} DISPOSITIVOS ===")
            
            devices_synced = 0
            devices_updated = 0
            devices_not_in_odoo = 0
            devices_invalid_serial = 0
            devices_error = 0
            
            for i, device_data in enumerate(all_devices):
                try:
                    result = self._sync_device(device_data)
                    if result == 'created':
                        devices_synced += 1
                    elif result == 'updated':
                        devices_updated += 1
                    elif result == 'not_in_odoo':
                        devices_not_in_odoo += 1
                    elif result == 'invalid_serial':
                        devices_invalid_serial += 1
                    else:
                        devices_error += 1
                except Exception as e:
                    devices_error += 1
                    _logger.error(f"❌ Error procesando dispositivo {i+1}: {e}")
                
                # Progreso cada 10 dispositivos
                if (i + 1) % 10 == 0:
                    _logger.info(f"📊 Progreso: {i+1}/{len(all_devices)} dispositivos procesados")
            
            # RESULTADO FINAL DETALLADO
            _logger.info(f"🎯 === RESUMEN FINAL ===")
            _logger.info(f"📄 Páginas: {total_pages_processed}")
            _logger.info(f"📊 Total: {len(all_devices)}")
            _logger.info(f"✅ Creados: {devices_synced}")
            _logger.info(f"📝 Actualizados: {devices_updated}")
            _logger.info(f"❌ No en Odoo: {devices_not_in_odoo}")
            _logger.info(f"⚠️ Series inválidas: {devices_invalid_serial}")
            _logger.info(f"💥 Errores: {devices_error}")
            
            total_processed = devices_synced + devices_updated
            
            if total_processed > 0:
                message_type = 'success'
                if devices_not_in_odoo > 0:
                    message = f'✅ Dispositivos procesados: {devices_synced} nuevos, {devices_updated} actualizados, {devices_not_in_odoo} no están en Odoo'
                else:
                    message = f'🎉 Sincronización completa: {devices_synced} nuevos, {devices_updated} actualizados'
            else:
                message_type = 'warning'
                message = f'⚠️ No se pudo procesar ningún dispositivo. {devices_not_in_odoo} no están en Odoo, {devices_invalid_serial} series inválidas'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': message,
                    'type': message_type
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
    
    # ============================================================
    # DIAGNÓSTICO INTEGRAL PRINTTRACKER - SOLO LECTURA
    # ============================================================

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        """
        Añade automáticamente el botón de diagnóstico al formulario de
        printtracker.config sin requerir modificar la vista XML existente.
        No reemplaza ni elimina botones/campos actuales.
        """
        result = super().get_view(view_id=view_id, view_type=view_type, **options)

        if view_type != 'form' or not result.get('arch'):
            return result

        try:
            arch = etree.fromstring(result['arch'])

            if arch.xpath("//button[@name='action_check_all_processes']"):
                return result

            button = etree.Element(
                'button',
                name='action_check_all_processes',
                string='Comprobar procesos PrintTracker',
                type='object',
                **{
                    'class': 'oe_highlight',
                    'icon': 'fa-stethoscope',
                    'help': (
                        'Comprueba en modo solo lectura la conexión, entidades, '
                        'dispositivos, medidores, consumibles, events/alertas, '
                        'clasificación Odoo, correo y cron.'
                    ),
                },
            )

            headers = arch.xpath('//form/header')
            if headers:
                headers[0].append(button)
            else:
                form_nodes = arch.xpath('//form')
                if form_nodes:
                    header = etree.Element('header')
                    header.append(button)
                    form_nodes[0].insert(0, header)

            result['arch'] = etree.tostring(arch, encoding='unicode')
        except Exception:
            _logger.exception(
                "❌ No se pudo insertar el botón de diagnóstico PrintTracker"
            )

        return result

    def _diagnostic_request(self, endpoint, params=None):
        """GET de diagnóstico. No escribe datos en Odoo ni en PrintTracker."""
        self.ensure_one()

        url = f'{self.api_url.rstrip("/")}/{endpoint.lstrip("/")}'
        started = time.monotonic()

        try:
            response = requests.get(
                url,
                headers=self.get_api_headers(),
                params=params or {},
                timeout=self.timeout_seconds,
            )
            elapsed = time.monotonic() - started

            try:
                payload = response.json()
            except Exception:
                payload = None

            return {
                'ok': response.status_code == 200,
                'status_code': response.status_code,
                'elapsed': elapsed,
                'url': response.url,
                'payload': payload,
                'text': response.text or '',
            }

        except requests.exceptions.Timeout as error:
            return {
                'ok': False,
                'status_code': 0,
                'elapsed': time.monotonic() - started,
                'url': url,
                'payload': None,
                'text': f'Timeout: {error}',
            }
        except requests.exceptions.RequestException as error:
            return {
                'ok': False,
                'status_code': 0,
                'elapsed': time.monotonic() - started,
                'url': url,
                'payload': None,
                'text': str(error),
            }
        except Exception as error:
            _logger.exception("❌ Error inesperado en diagnóstico API")
            return {
                'ok': False,
                'status_code': 0,
                'elapsed': time.monotonic() - started,
                'url': url,
                'payload': None,
                'text': str(error),
            }

    @staticmethod
    def _diagnostic_normalize_serial(value):
        return str(value or '').strip().upper()

    @staticmethod
    def _diagnostic_sample_text(value, max_length=180):
        text = str(value or '').replace('\n', ' ').replace('\r', ' ').strip()
        if len(text) > max_length:
            return text[:max_length - 3] + '...'
        return text

    def _diagnostic_classify_event(self, event):
        """
        Usa el clasificador REAL de printtracker.alert cuando está disponible.
        Si el módulo no está cargado o el método falta, no inventa clasificación.
        """
        try:
            Alert = self.env['printtracker.alert'].sudo()
            classifier = getattr(Alert, '_clasificar_event_api', None)
            if classifier:
                result = classifier(event)
                if isinstance(result, dict):
                    return result
        except Exception as error:
            _logger.warning(
                "⚠️ Diagnóstico: no se pudo ejecutar clasificador de alertas: %s",
                error,
            )

        return {
            'tipo': 'NO_DISPONIBLE',
            'prioridad': '-',
            'titulo': 'Clasificador no disponible',
        }

    def _diagnostic_get_cron_status(self):
        """Busca el cron de alertas sin depender de un XML ID concreto."""
        self.ensure_one()

        Cron = self.env['ir.cron'].sudo()
        cron = Cron.search([
            ('code', 'ilike', 'ejecutar_revision_automatica'),
        ], limit=1)

        if not cron:
            try:
                model = self.env['ir.model'].sudo().search([
                    ('model', '=', 'printtracker.alert.manager'),
                ], limit=1)
                if model:
                    cron = Cron.search([
                        ('model_id', '=', model.id),
                    ], limit=1)
            except Exception:
                cron = Cron.browse()

        if not cron:
            return {
                'found': False,
                'active': False,
                'name': '-',
                'nextcall': False,
                'lastcall': False,
                'interval': '-',
            }

        interval = '%s %s' % (
            getattr(cron, 'interval_number', '') or '',
            getattr(cron, 'interval_type', '') or '',
        )

        return {
            'found': True,
            'active': bool(getattr(cron, 'active', False)),
            'name': cron.name or '-',
            'nextcall': getattr(cron, 'nextcall', False),
            'lastcall': getattr(cron, 'lastcall', False),
            'interval': interval.strip() or '-',
        }

    def action_check_all_processes(self):
        """
        Diagnóstico integral SOLO LECTURA.

        Comprueba conexión, devices, currentMeter, supplies, events de las
        últimas 24 horas, coincidencia con equipos alquilados, clasificación
        real de printtracker.alert, alertas existentes, correo y cron.

        NO crea alertas, NO envía correos, NO cambia stock, NO crea solicitudes
        y NO modifica historial de tóner.
        """
        self.ensure_one()

        now_utc = datetime.utcnow()
        start_24h = now_utc - timedelta(hours=24)
        start_30d = now_utc - timedelta(days=30)

        start_24h_str = start_24h.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        start_30d_str = start_30d.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        end_str = now_utc.strftime('%Y-%m-%dT%H:%M:%S.000Z')

        include_children = bool(self.incluir_entidades_hijas)
        exclude_disabled = bool(self.solo_equipos_gestionados)
        large_limit = 50000

        report = []
        warnings = []
        errors = []
        raw_events = []

        def add(title, value='', status='info'):
            icon = {
                'ok': '✅',
                'warn': '⚠️',
                'error': '❌',
                'info': 'ℹ️',
            }.get(status, 'ℹ️')
            report.append(f'{icon} {title}: {value}')

        report.append('=== DIAGNÓSTICO INTEGRAL PRINTTRACKER ===')
        report.append('Fecha UTC: %s' % now_utc.strftime('%Y-%m-%d %H:%M:%S'))
        report.append('Modo: SOLO LECTURA - no crea alertas, stock, solicitudes ni correos')
        report.append('')

        # 1. ENTIDAD / CONEXIÓN
        report.append('--- 1. CONEXIÓN / ENTIDAD ---')
        entity = self._diagnostic_request(
            f'entity/{self.entity_bbbb_id}',
            {'includeChildren': include_children},
        )

        if entity['ok'] and isinstance(entity['payload'], dict):
            entity_name = entity['payload'].get('name') or 'Sin nombre'
            children = entity['payload'].get('children') or []
            add('API entidad', f"HTTP {entity['status_code']} - {entity_name} ({entity['elapsed']:.2f}s)", 'ok')
            add('Entidades hijas visibles', len(children), 'ok')
        else:
            message = self._diagnostic_sample_text(entity['text'], 300)
            add('API entidad', f"HTTP {entity['status_code']} - {message}", 'error')
            errors.append('Falló la conexión con la entidad principal.')

        report.append('')

        # 2. DISPOSITIVOS
        report.append('--- 2. DISPOSITIVOS ---')
        devices = self._diagnostic_request(
            f'entity/{self.entity_bbbb_id}/device',
            {
                'includeChildren': include_children,
                'excludeDisabled': exclude_disabled,
                'limit': large_limit,
                'page': 1,
            },
        )
        device_rows = devices['payload'] if isinstance(devices['payload'], list) else []

        if devices['ok']:
            add('Devices API', f"HTTP {devices['status_code']} - {len(device_rows)} registros ({devices['elapsed']:.2f}s)", 'ok')
        else:
            add('Devices API', f"HTTP {devices['status_code']} - {self._diagnostic_sample_text(devices['text'], 250)}", 'error')
            errors.append('Falló la consulta de dispositivos.')

        device_serials = {
            self._diagnostic_normalize_serial(row.get('serialNumber'))
            for row in device_rows
            if self._diagnostic_normalize_serial(row.get('serialNumber'))
        }
        add('Series válidas recibidas', len(device_serials), 'info')
        report.append('')

        # 3. MEDIDORES
        report.append('--- 3. MEDIDORES ACTUALES ---')
        meters = self._diagnostic_request(
            f'entity/{self.entity_bbbb_id}/currentMeter',
            {
                'includeChildren': include_children,
                'excludeDisabled': exclude_disabled,
                'limit': large_limit,
                'page': 1,
            },
        )
        meter_rows = meters['payload'] if isinstance(meters['payload'], list) else []

        if meters['ok']:
            add('CurrentMeter API', f"HTTP {meters['status_code']} - {len(meter_rows)} registros ({meters['elapsed']:.2f}s)", 'ok')
            with_default = 0
            with_life = 0
            for row in meter_rows:
                page_counts = row.get('pageCounts') or {}
                if isinstance(page_counts, dict):
                    if page_counts.get('default'):
                        with_default += 1
                    if page_counts.get('life'):
                        with_life += 1
            add('Medidores con pageCounts.default', with_default, 'info')
            add('Medidores con pageCounts.life', with_life, 'info')
        else:
            add('CurrentMeter API', f"HTTP {meters['status_code']} - {self._diagnostic_sample_text(meters['text'], 250)}", 'error')
            errors.append('Falló la consulta de medidores.')

        report.append('')

        # 4. CONSUMIBLES
        report.append('--- 4. CONSUMIBLES / SUPPLIES ---')
        supplies = self._diagnostic_request(
            f'entity/{self.entity_bbbb_id}/supplies',
            {
                'includeChildren': include_children,
                'replaced': False,
                'start': start_30d_str,
                'end': end_str,
                'limit': large_limit,
                'page': 1,
            },
        )
        supply_rows = supplies['payload'] if isinstance(supplies['payload'], list) else []

        if supplies['ok']:
            add('Supplies API', f"HTTP {supplies['status_code']} - {len(supply_rows)} registros ({supplies['elapsed']:.2f}s)", 'ok')
            supply_types = {}
            for row in supply_rows:
                key = row.get('supply') or 'sin_identificar'
                supply_types[key] = supply_types.get(key, 0) + 1
            if supply_types:
                top_supplies = sorted(supply_types.items(), key=lambda item: (-item[1], item[0]))[:10]
                add('Tipos principales', ', '.join(f'{key}={count}' for key, count in top_supplies), 'info')
        else:
            add('Supplies API', f"HTTP {supplies['status_code']} - {self._diagnostic_sample_text(supplies['text'], 250)}", 'error')
            errors.append('Falló la consulta de supplies.')

        report.append('')

        # 5. EVENTS / ALERTAS
        report.append('--- 5. EVENTS / ALERTAS (ÚLTIMAS 24 HORAS) ---')
        events = self._diagnostic_request(
            f'entity/{self.entity_bbbb_id}/events',
            {
                'excludeDisabled': exclude_disabled,
                'includeChildren': include_children,
                'start': start_24h_str,
                'end': end_str,
            },
        )
        event_rows = events['payload'] if isinstance(events['payload'], list) else []
        raw_events = event_rows

        if events['ok']:
            add('Events API', f"HTTP {events['status_code']} - {len(event_rows)} eventos ({events['elapsed']:.2f}s)", 'ok' if event_rows else 'warn')
            add('Rango consultado', f'{start_24h_str} → {end_str}', 'info')
            if not event_rows:
                warnings.append('La API respondió correctamente pero no devolvió events en las últimas 24 horas.')
        else:
            add('Events API', f"HTTP {events['status_code']} - {self._diagnostic_sample_text(events['text'], 300)}", 'error')
            errors.append('Falló la consulta de events.')

        # 6. EQUIPOS ALQUILADOS / COINCIDENCIAS
        rented_serials = set()
        try:
            rented = self.env['alquiler'].sudo().search([
                ('estado_alquiler_id', '=', 'alquilada'),
            ])
            rented_serials = {
                self._diagnostic_normalize_serial(value)
                for value in rented.mapped('serie')
                if self._diagnostic_normalize_serial(value)
            }
            add('Equipos alquilados en Odoo', len(rented_serials), 'ok')
        except Exception as error:
            add('Equipos alquilados en Odoo', str(error), 'error')
            errors.append('No se pudo consultar equipos alquilados.')

        relevant_events = []
        outside_events = []
        for event in event_rows:
            serial = self._diagnostic_normalize_serial(event.get('deviceSerialNumber'))
            if serial and serial in rented_serials:
                relevant_events.append(event)
            else:
                outside_events.append(event)

        add('Events de equipos alquilados', len(relevant_events), 'ok' if relevant_events else 'warn')
        add('Events fuera del filtro de alquiler', len(outside_events), 'info')

        # 7. CLASIFICACIÓN REAL DE ODOO
        report.append('')
        report.append('--- 6. CLASIFICACIÓN ODOO ---')
        class_counts = {}
        classification_errors = 0
        for event in event_rows:
            try:
                classification = self._diagnostic_classify_event(event)
                alert_kind = classification.get('tipo') or 'sin_tipo'
                class_counts[alert_kind] = class_counts.get(alert_kind, 0) + 1
            except Exception:
                classification_errors += 1

        if class_counts:
            for alert_kind, count in sorted(class_counts.items(), key=lambda item: (-item[1], item[0])):
                add(alert_kind, count, 'info')
        elif events['ok']:
            add('Clasificación', 'Sin events para clasificar', 'warn')

        if classification_errors:
            add('Errores clasificando', classification_errors, 'error')
            errors.append('Existen events que no pudieron clasificarse.')

        # 8. DEDUPLICACIÓN / ALERTAS EXISTENTES
        report.append('')
        report.append('--- 7. REGISTROS DE ALERTA ODOO ---')
        try:
            event_ids = [str(event.get('id')) for event in event_rows if event.get('id')]
            existing_alerts = self.env['printtracker.alert'].sudo().search([
                ('api_event_id', 'in', event_ids),
            ]) if event_ids else self.env['printtracker.alert'].browse()
            add('Events del rango ya registrados', len(existing_alerts), 'info')
            add('Events del rango aún no registrados', max(0, len(event_ids) - len(existing_alerts)), 'info')
        except Exception as error:
            add('Modelo printtracker.alert', str(error), 'error')
            errors.append('No se pudo comprobar printtracker.alert.')

        # 9. CORREO
        report.append('')
        report.append('--- 8. NOTIFICACIONES POR CORREO ---')
        try:
            cp = self.env['ir.config_parameter'].sudo()
            destination = cp.get_param('printtracker.alert.email_destino', 'soporte@andescopiers.com.pe')
            mail_servers = self.env['ir.mail_server'].sudo().search([])
            add('Correo destino', destination or 'NO CONFIGURADO', 'ok' if destination else 'warn')
            add('Servidores salientes configurados', len(mail_servers), 'ok' if mail_servers else 'warn')
            if not mail_servers:
                warnings.append('No se encontró un servidor de correo saliente en Odoo. No se envió ningún correo durante este diagnóstico.')
        except Exception as error:
            add('Configuración de correo', str(error), 'error')
            errors.append('No se pudo comprobar configuración de correo.')

        # 10. CRON
        report.append('')
        report.append('--- 9. CRON DE ALERTAS ---')
        cron = self._diagnostic_get_cron_status()
        if cron['found']:
            add('Cron', cron['name'], 'ok')
            add('Activo', 'Sí' if cron['active'] else 'No', 'ok' if cron['active'] else 'error')
            add('Intervalo', cron['interval'], 'info')
            add('Próxima ejecución', cron['nextcall'] or '-', 'info')
            add('Última ejecución', cron['lastcall'] or '-', 'info')
            if not cron['active']:
                errors.append('El cron de alertas está desactivado.')
        else:
            add('Cron', 'No encontrado', 'error')
            errors.append('No se encontró un ir.cron relacionado con ejecutar_revision_automatica.')

        # 11. MUESTRA DE EVENTS
        report.append('')
        report.append('--- 10. MUESTRA DE EVENTS DEVUELTOS ---')
        if event_rows:
            for index, event in enumerate(event_rows[:25], start=1):
                classification = self._diagnostic_classify_event(event)
                report.append(
                    '#%s | serie=%s | alertType=%s | supplyKey=%s | status=%s | Odoo=%s/%s | %s'
                    % (
                        index,
                        event.get('deviceSerialNumber') or '-',
                        event.get('alertType') or '-',
                        event.get('supplyKey') or '-',
                        event.get('resolutionStatus') or '-',
                        classification.get('tipo') or '-',
                        classification.get('prioridad') or '-',
                        self._diagnostic_sample_text(event.get('description') or '-', 140),
                    )
                )
        else:
            report.append('Sin events en el rango consultado.')

        # RESULTADO GENERAL
        report.append('')
        report.append('=== RESULTADO GENERAL ===')
        if errors:
            overall = 'error'
            report.append('❌ Se encontraron problemas que requieren revisión:')
            for item in errors:
                report.append(f'   - {item}')
        elif warnings:
            overall = 'warning'
            report.append('⚠️ Los procesos principales responden, con observaciones:')
            for item in warnings:
                report.append(f'   - {item}')
        else:
            overall = 'ok'
            report.append('✅ Todas las comprobaciones ejecutadas respondieron correctamente.')

        report_text = '\n'.join(str(line) for line in report)
        _logger.info("🔎 === DIAGNÓSTICO PRINTTRACKER ===\n%s", report_text)

        html_report = '<pre style="white-space: pre-wrap; font-family: monospace;">%s</pre>' % escape(report_text)
        raw_events_text = json.dumps(raw_events, ensure_ascii=False, indent=2, default=str)

        diagnostic = self.env['printtracker.diagnostic.result'].sudo().create({
            'name': 'Diagnóstico PrintTracker - %s' % fields.Datetime.now(),
            'status': overall,
            'generated_at': fields.Datetime.now(),
            'report_html': html_report,
            'raw_events': raw_events_text,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Diagnóstico PrintTracker',
            'res_model': 'printtracker.diagnostic.result',
            'res_id': diagnostic.id,
            'view_mode': 'form',
            'target': 'new',
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


    @api.model
    def run_consolidation(self):
        """
        Server Action entrypoint: busca la config activa y corre la sincronización completa.
        Debe devolver un dict de ir.actions.client (notificación).
        """
        config = self.get_active_config()  # ya lo tienes implementado
        # Asegura que sea un único registro
        if not config or len(config) != 1:
            raise UserError(_("No se encontró una configuración activa única de PrintTracker."))

        # Ejecuta tu pipeline completo (ya devuelve notificación)
        return config.sync_all_data()

class PrintTrackerDiagnosticResult(models.TransientModel):
    _name = 'printtracker.diagnostic.result'
    _description = 'Resultado de Diagnóstico PrintTracker'
    _rec_name = 'name'

    name = fields.Char(string='Diagnóstico', readonly=True)
    status = fields.Selection([
        ('ok', 'Correcto'),
        ('warning', 'Con observaciones'),
        ('error', 'Con errores'),
    ], string='Estado', readonly=True)
    generated_at = fields.Datetime(string='Generado', readonly=True)
    report_html = fields.Html(string='Resultado', readonly=True, sanitize=False)
    raw_events = fields.Text(string='Events API - JSON bruto', readonly=True)

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)

        if view_type == 'form':
            result['arch'] = """<form string="Diagnóstico PrintTracker" create="0" edit="0" delete="0">
                <header>
                    <button string="Cerrar" special="cancel" class="btn-secondary" icon="fa-times"/>
                </header>
                <sheet>
                    <widget name="web_ribbon" title="Correcto" bg_color="bg-success" invisible="status != 'ok'"/>
                    <widget name="web_ribbon" title="Observaciones" bg_color="bg-warning" invisible="status != 'warning'"/>
                    <widget name="web_ribbon" title="Con errores" bg_color="bg-danger" invisible="status != 'error'"/>

                    <div class="d-flex align-items-center justify-content-between flex-wrap gap-3 mb-4">
                        <div class="d-flex align-items-center">
                            <div class="rounded-circle bg-primary-subtle text-primary d-flex align-items-center justify-content-center me-3"
                                 style="width:48px;height:48px;">
                                <i class="fa fa-stethoscope fa-lg"/>
                            </div>
                            <div>
                                <h1 class="mb-1"><field name="name" readonly="1"/></h1>
                                <div class="text-muted">Comprobación integral de la integración PrintTracker Pro</div>
                            </div>
                        </div>

                        <div class="d-flex gap-2 align-items-center">
                            <field name="status"
                                   widget="badge"
                                   readonly="1"
                                   decoration-success="status == 'ok'"
                                   decoration-warning="status == 'warning'"
                                   decoration-danger="status == 'error'"/>
                        </div>
                    </div>

                    <div class="row g-3 mb-4">
                        <div class="col-12 col-md-6">
                            <div class="card border-0 shadow-sm h-100">
                                <div class="card-body p-3">
                                    <div class="text-muted small mb-1">Generado</div>
                                    <div class="fw-semibold"><field name="generated_at" readonly="1" nolabel="1"/></div>
                                </div>
                            </div>
                        </div>
                        <div class="col-12 col-md-6">
                            <div class="card border-0 shadow-sm h-100">
                                <div class="card-body p-3">
                                    <div class="text-muted small mb-1">Modo</div>
                                    <div class="fw-semibold text-success"><i class="fa fa-shield me-1"/> Solo lectura · Sin cambios productivos</div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <notebook>
                        <page string="Resultado" name="diagnostic_result">
                            <div class="card border-0 shadow-sm mt-3">
                                <div class="card-header bg-transparent border-0 pt-4 px-4">
                                    <div class="d-flex align-items-center">
                                        <i class="fa fa-list-alt me-2 text-primary"/>
                                        <h3 class="mb-0">Resultado de comprobación</h3>
                                    </div>
                                </div>
                                <div class="card-body px-4 pb-4">
                                    <field name="report_html" readonly="1" nolabel="1"/>
                                </div>
                            </div>
                        </page>

                        <page string="Events JSON" name="diagnostic_json">
                            <div class="alert alert-info mt-3 mb-3">
                                <i class="fa fa-info-circle me-1"/>
                                Respuesta JSON bruta del endpoint de eventos para diagnóstico técnico.
                            </div>
                            <field name="raw_events" readonly="1" nolabel="1"/>
                        </page>
                    </notebook>
                </sheet>
            </form>"""

        return result

