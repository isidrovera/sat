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
    def _safe_int(self, value, default=0):
        """Convierte un valor a entero de forma segura"""
        try:
            if value is None or value == '' or value == 'N/A':
                return default
            return int(value)
        except (ValueError, TypeError):
            _logger.warning(f"⚠️ No se pudo convertir '{value}' a entero, usando {default}")
            return default
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
        """Sincroniza todos los dispositivos desde PrintTracker y limpia cache"""
        try:
            _logger.info(f"🔄 Iniciando sincronización de dispositivos...")
            
            # ✅ LIMPIAR cache antes de sincronizar
            self.clear_device_cache()
            
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
                
                # ✅ LIMPIAR cache después de sincronizar para forzar recarga
                self.clear_device_cache()
                
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
        CORREGIDO: Sincroniza medidores actuales desde PrintTracker con PAGINACIÓN COMPLETA
        NUEVO: Obtiene TODOS los medidores, no solo los primeros 100
        """
        try:
            _logger.info(f"🔄 Iniciando sincronización de medidores actuales...")
            
            all_meters = []
            page = 1
            total_pages_processed = 0
            
            # ✅ PAGINACIÓN COMPLETA: Obtener todos los medidores
            while True:
                _logger.info(f"📄 === PROCESANDO PÁGINA {page} ===")
                
                params = {
                    'includeChildren': True,
                    'excludeDisabled': False,
                    'limit': self.max_records_per_request,  # Típicamente 100
                    'page': page
                }
                
                _logger.info(f"📊 Parámetros de consulta página {page}: {params}")
                
                response = requests.get(
                    f'{self.api_url.rstrip("/")}/entity/{self.entity_bbbb_id}/currentMeter',
                    headers=self.get_api_headers(),
                    params=params,
                    timeout=self.timeout_seconds
                )
                
                _logger.info(f"📡 Respuesta API página {page}: Status {response.status_code}")
                
                if response.status_code == 200:
                    meters_page = response.json()
                    
                    _logger.info(f"📊 Página {page}: {len(meters_page)} medidores recibidos")
                    
                    # Si no hay medidores en esta página, terminamos
                    if not meters_page:
                        _logger.info(f"📄 Página {page} vacía - Fin de datos")
                        break
                    
                    # Agregar medidores de esta página al total
                    all_meters.extend(meters_page)
                    total_pages_processed += 1
                    
                    # Si recibimos menos del límite, es la última página
                    if len(meters_page) < self.max_records_per_request:
                        _logger.info(f"📄 Página {page} incompleta ({len(meters_page)} < {self.max_records_per_request}) - Última página")
                        break
                    
                    # Pasar a la siguiente página
                    page += 1
                    
                    # ✅ LÍMITE DE SEGURIDAD: Evitar loops infinitos
                    if page > 50:  # Máximo 50 páginas = 5000 medidores
                        _logger.warning(f"⚠️ Límite de seguridad alcanzado: {page-1} páginas procesadas")
                        break
                        
                else:
                    error_msg = f'Error HTTP {response.status_code} en página {page}: {response.text}'
                    _logger.error(f"❌ Error de API: {error_msg}")
                    
                    # Si falla la primera página, es error crítico
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
                        # Si falla una página posterior, continuar con lo que tenemos
                        _logger.warning(f"⚠️ Error en página {page}, continuando con {len(all_meters)} medidores obtenidos")
                        break
            
            # ✅ RESUMEN DE PAGINACIÓN
            _logger.info(f"🎯 === RESUMEN PAGINACIÓN ===")
            _logger.info(f"📄 Páginas procesadas: {total_pages_processed}")
            _logger.info(f"📊 Total medidores obtenidos: {len(all_meters)}")
            
            # Verificar si tenemos medidores para procesar
            if not all_meters:
                _logger.warning("⚠️ No se recibieron medidores de la API")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': '⚠️ No se encontraron medidores en PrintTracker',
                        'type': 'warning'
                    }
                }
            
            # ✅ PROCESAR TODOS LOS MEDIDORES OBTENIDOS
            _logger.info(f"🔄 === INICIANDO PROCESAMIENTO DE {len(all_meters)} MEDIDORES ===")
            
            meters_synced = 0
            meters_failed = 0
            
            for i, meter_data in enumerate(all_meters):
                _logger.info(f"🔍 === PROCESANDO MEDIDOR {i+1}/{len(all_meters)} ===")
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
                        meters_failed += 1
                        _logger.warning(f"⚠️ Medidor {i+1} no pudo ser procesado")
                except Exception as e:
                    meters_failed += 1
                    _logger.error(f"❌ Error procesando medidor {i+1}: {e}")
                
                # ✅ PROGRESO CADA 10 MEDIDORES
                if (i + 1) % 10 == 0:
                    _logger.info(f"📊 Progreso: {i+1}/{len(all_meters)} medidores procesados")
            
            # ✅ RESULTADO FINAL DETALLADO
            _logger.info(f"🎯 === RESUMEN FINAL SINCRONIZACIÓN MEDIDORES ===")
            _logger.info(f"📄 Páginas consultadas: {total_pages_processed}")
            _logger.info(f"📊 Total medidores recibidos: {len(all_meters)}")
            _logger.info(f"✅ Procesados exitosamente: {meters_synced}")
            _logger.info(f"❌ Fallidos: {meters_failed}")
            _logger.info(f"📈 Tasa de éxito: {(meters_synced/len(all_meters)*100):.1f}%")
            
            # ✅ MENSAJE DE RESULTADO MEJORADO
            if meters_synced > 0:
                message_type = 'success'
                if meters_failed > 0:
                    message = f'✅ Sincronización parcial: {meters_synced} éxitos, {meters_failed} fallos de {len(all_meters)} medidores ({total_pages_processed} páginas)'
                else:
                    message = f'🎉 Sincronización completa: {meters_synced} medidores procesados exitosamente de {total_pages_processed} páginas'
            else:
                message_type = 'warning'
                message = f'⚠️ No se pudo procesar ningún medidor de {len(all_meters)} recibidos'
            
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
        MODIFICADO: Integración con contador.automatico - crear o actualizar registro del día
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
            
            # ===== NUEVA LÓGICA: INTEGRACIÓN CON CONTADOR.AUTOMATICO =====
            if device and device.serie:
                _logger.info(f"🔄 === VERIFICANDO REGISTRO CONTADOR.AUTOMATICO ===")
                _logger.info(f"📊 Serie del equipo: {device.serie}")
                
                # BUSCAR si ya existe registro del día para esta serie
                registro_del_dia = self.env['contador.automatico'].buscar_registro_del_dia(device.serie)
                
                if registro_del_dia:
                    _logger.info(f"📝 EXISTE registro contador.automatico para {device.serie}")
                    _logger.info(f"📋 Registro ID: {registro_del_dia.id}")
                    _logger.info(f"📅 Fecha registro: {registro_del_dia.fecha_procesamiento}")
                    _logger.info(f"🔗 Origen registro: {getattr(registro_del_dia, 'origen', 'No definido')}")
                    _logger.info(f"📊 Estado registro: {registro_del_dia.estado}")
                    
                    # ACTUALIZAR registro existente con datos de PrintTracker
                    actualizado = self._actualizar_registro_contador_automatico(registro_del_dia, meter_data, device)
                    if actualizado:
                        _logger.info(f"✅ Registro contador.automatico actualizado desde PrintTracker")
                    else:
                        _logger.info(f"ℹ️ Registro contador.automatico no requirió actualización")
                else:
                    _logger.info(f"🆕 NO EXISTE registro contador.automatico para {device.serie}")
                    _logger.info(f"🔄 Creando registro desde PrintTracker...")
                    
                    # CREAR nuevo registro desde PrintTracker
                    creado = self._crear_registro_contador_automatico(device, meter_data)
                    if creado:
                        _logger.info(f"✅ Registro contador.automatico creado desde PrintTracker")
                    else:
                        _logger.error(f"❌ No se pudo crear registro contador.automatico")
            
            # ===== LÓGICA ORIGINAL: CONTINUAR CON PROCESAMIENTO PRINTTRACKER.METER =====
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
                'reading_date': self._parse_printtracker_datetime(meter_data.get('timestamp')),
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
        CORREGIDO: Busca la serie en datos sincronizados con cache estático
        FIX: Usar cache a nivel de clase en lugar de instancia
        """
        try:
            # ✅ CORRECCIÓN: Cache estático a nivel de clase
            cache_key = f'_device_cache_{self.id}'
            
            # Verificar si el cache existe en el contexto global
            if not hasattr(self.__class__, cache_key):
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
                    device_cache = {}
                    for device_data in devices:
                        device_id = device_data.get('id')
                        serie = device_data.get('serialNumber')
                        
                        if device_id and serie and serie not in ['notavailable', 'None', '', None]:
                            device_cache[device_id] = serie
                    
                    # ✅ GUARDAR en cache de clase
                    setattr(self.__class__, cache_key, device_cache)
                    _logger.info(f"📋 Cache procesado: {len(device_cache)} dispositivos válidos")
                else:
                    _logger.error(f"❌ Error cargando cache: {response.status_code}")
                    setattr(self.__class__, cache_key, {})
            
            # ✅ OBTENER cache de clase
            device_cache = getattr(self.__class__, cache_key, {})
            
            # Buscar en cache
            serie = device_cache.get(device_key)
            if serie:
                _logger.info(f"✅ Serie encontrada en cache: {serie} para deviceKey: {device_key}")
                return serie
            else:
                _logger.warning(f"❌ DeviceKey {device_key} no encontrado en cache de {len(device_cache)} dispositivos")
                return None
                
        except Exception as e:
            _logger.error(f"❌ Error en búsqueda optimizada: {e}")
            return None

    def clear_device_cache(self):
        """Limpia el cache de dispositivos"""
        cache_key = f'_device_cache_{self.id}'
        if hasattr(self.__class__, cache_key):
            delattr(self.__class__, cache_key)
            _logger.info(f"🗑️ Cache de dispositivos limpiado")

    def _actualizar_registro_contador_automatico(self, registro, meter_data, device):
        """
        CORREGIDO: Actualiza un registro existente de contador.automatico con datos de PrintTracker
        FIX: Conversión de tipos y cálculo correcto de scan
        
        Args:
            registro: Registro de contador.automatico existente
            meter_data: Datos del medidor desde PrintTracker
            device: Equipo relacionado
        
        Returns:
            bool: True si se actualizó algo, False si no
        """
        try:
            _logger.info(f"📝 === ACTUALIZANDO REGISTRO CONTADOR.AUTOMATICO ===")
            _logger.info(f"📋 Registro ID: {registro.id}")
            _logger.info(f"🎯 Serie: {registro.serie_detectada}")
            
            # Extraer datos del medidor PrintTracker
            page_counts = meter_data.get('pageCounts', {})
            life_counts = page_counts.get('life', {})
            
            # ✅ CORRECCIÓN 1: Usar _safe_int para conversión segura
            total_value = life_counts.get('total', {}).get('value', 0)
            black_value = life_counts.get('totalBlack', {}).get('value', 0)
            color_value = life_counts.get('totalColor', {}).get('value', 0)
            
            # Convertir a enteros de forma segura
            valores_pt = {
                'total': self._safe_int(total_value),
                'black': self._safe_int(black_value),
                'color': self._safe_int(color_value),
            }
            
            # ✅ CORRECCIÓN 2: Cálculo correcto de scan
            # Método 1: Buscar campo scan directo en PrintTracker
            scan_direct = meter_data.get('scanPages', 0)
            if scan_direct:
                valores_pt['scan'] = self._safe_int(scan_direct)
            else:
                # Método 2: Calcular como diferencia si no hay campo directo
                scan_calculated = max(0, valores_pt['total'] - valores_pt['black'] - valores_pt['color'])
                valores_pt['scan'] = scan_calculated
            
            # ✅ CORRECCIÓN 3: Para equipos monocromáticos, scan podría ser parte del total
            tipo_equipo = getattr(device, 'tipo_maquina_id', None)
            if hasattr(device, 'name') and device.name:
                modelo_name = device.name.name.upper() if hasattr(device.name, 'name') else str(device.name).upper()
                
                # Si es monocromático y no hay scan calculado, asumir que total incluye scan
                if ('MONO' in modelo_name or tipo_equipo == 'monocromatica') and valores_pt['scan'] == 0:
                    # Para monos: total = black + scan (aproximadamente)
                    if valores_pt['total'] > valores_pt['black']:
                        valores_pt['scan'] = valores_pt['total'] - valores_pt['black']
                        _logger.info(f"📄 Equipo mono - Scan calculado: {valores_pt['scan']} (total - black)")
            
            _logger.info(f"📊 Valores desde PrintTracker (convertidos):")
            _logger.info(f"   Total: {valores_pt['total']}")
            _logger.info(f"   Black: {valores_pt['black']}")
            _logger.info(f"   Color: {valores_pt['color']}")
            _logger.info(f"   Scan: {valores_pt['scan']}")
            
            # Valores actuales del registro
            valores_actuales = {
                'black': registro.contador_bn_detectado or 0,
                'color': registro.contador_color_detectado or 0,
                'scan': registro.contador_scan_detectado or 0
            }
            
            _logger.info(f"📋 Valores actuales del registro:")
            _logger.info(f"   Black: {valores_actuales['black']}")
            _logger.info(f"   Color: {valores_actuales['color']}")
            _logger.info(f"   Scan: {valores_actuales['scan']}")
            
            # Determinar qué campos actualizar
            valores_actualizacion = {}
            campos_actualizados = []
            
            # ✅ CORRECCIÓN 4: Lógica mejorada de actualización
            # Actualizar BN si está vacío o PrintTracker tiene valor mayor
            if valores_actuales['black'] == 0 or valores_pt['black'] > valores_actuales['black']:
                if valores_pt['black'] > 0:
                    valores_actualizacion['contador_bn_detectado'] = valores_pt['black']
                    campos_actualizados.append(f"BN: {valores_actuales['black']} → {valores_pt['black']}")
            
            # Actualizar Color si está vacío o PrintTracker tiene valor mayor
            if valores_actuales['color'] == 0 or valores_pt['color'] > valores_actuales['color']:
                if valores_pt['color'] >= 0:  # Color puede ser 0 legítimamente
                    valores_actualizacion['contador_color_detectado'] = valores_pt['color']
                    campos_actualizados.append(f"Color: {valores_actuales['color']} → {valores_pt['color']}")
            
            # ✅ CORRECCIÓN 5: Siempre actualizar Scan si PrintTracker tiene valor
            if valores_actuales['scan'] == 0 or valores_pt['scan'] > valores_actuales['scan']:
                if valores_pt['scan'] > 0:
                    valores_actualizacion['contador_scan_detectado'] = valores_pt['scan']
                    campos_actualizados.append(f"Scan: {valores_actuales['scan']} → {valores_pt['scan']}")
            
            # Actualizar información adicional de PrintTracker
            if not getattr(registro, 'marca_detectada', None) or registro.marca_detectada == 'Desconocida':
                valores_actualizacion['marca_detectada'] = 'PrintTracker'
            
            # Marcar como híbrido si se está enriqueciendo desde PrintTracker
            origen_actual = getattr(registro, 'origen', 'correo')
            if campos_actualizados and origen_actual == 'correo':
                valores_actualizacion['origen'] = 'hibrido'
            elif not campos_actualizados and origen_actual == 'correo':
                # Si no hay cambios pero venimos de correo, mantener origen pero marcar como verificado
                valores_actualizacion['marca_detectada'] = 'PrintTracker (verificado)'
            
            # Aplicar actualizaciones si las hay
            if valores_actualizacion:
                _logger.info(f"💾 Aplicando actualizaciones:")
                for campo in campos_actualizados:
                    _logger.info(f"   📊 {campo}")
                
                if 'origen' in valores_actualizacion:
                    _logger.info(f"   🔗 Origen: {origen_actual} → {valores_actualizacion['origen']}")
                
                # Ejecutar actualización
                registro.sudo().write(valores_actualizacion)
                
                # ✅ CORRECCIÓN 6: Actualizar contadores del equipo con valores finales correctos
                if any(key.startswith('contador_') for key in valores_actualizacion.keys()):
                    _logger.info(f"🔄 Actualizando contadores del equipo desde registro híbrido...")
                    
                    # Obtener valores finales (actuales + nuevos)
                    contadores_finales = {
                        'contador_bn': valores_actualizacion.get('contador_bn_detectado', registro.contador_bn_detectado),
                        'contador_color': valores_actualizacion.get('contador_color_detectado', registro.contador_color_detectado),
                        'contador_scan': valores_actualizacion.get('contador_scan_detectado', registro.contador_scan_detectado)
                    }
                    
                    _logger.info(f"📊 Contadores finales para equipo:")
                    _logger.info(f"   BN: {contadores_finales['contador_bn']}")
                    _logger.info(f"   Color: {contadores_finales['contador_color']}")
                    _logger.info(f"   Scan: {contadores_finales['contador_scan']}")
                    
                    # ✅ CORRECCIÓN 7: Usar método directo de actualización si existe
                    try:
                        if hasattr(registro, 'actualizar_contadores_equipo'):
                            registro.actualizar_contadores_equipo(device, contadores_finales)
                            _logger.info(f"✅ Equipo actualizado con datos híbridos vía método específico")
                        else:
                            # Fallback: actualización directa del equipo
                            valores_equipo = {
                                'contador_bn': contadores_finales['contador_bn'],
                                'contador_color': contadores_finales['contador_color'],
                                'contador_scan': contadores_finales['contador_scan'],
                                'fecha_ultima_actualizacion': fields.Datetime.now()
                            }
                            
                            device.sudo().write(valores_equipo)
                            _logger.info(f"✅ Equipo actualizado con datos híbridos vía write directo")
                            
                    except Exception as equipo_error:
                        _logger.error(f"❌ Error actualizando equipo: {equipo_error}")
                        # No es crítico, el registro se actualizó correctamente
                
                _logger.info(f"✅ Registro actualizado exitosamente: {len(campos_actualizados)} campos")
                return True
            else:
                _logger.info(f"ℹ️ No se requieren actualizaciones - registro ya completo o valores menores")
                
                # ✅ CORRECCIÓN 8: Aún así verificar si el equipo necesita actualización
                try:
                    if (device.contador_scan == 0 and valores_pt['scan'] > 0) or \
                    (device.contador_bn < valores_pt['black']) or \
                    (device.contador_color < valores_pt['color']):
                        
                        _logger.info(f"🔄 Equipo necesita actualización aunque registro esté completo...")
                        
                        valores_equipo = {
                            'contador_bn': max(device.contador_bn or 0, valores_pt['black']),
                            'contador_color': max(device.contador_color or 0, valores_pt['color']),
                            'contador_scan': max(device.contador_scan or 0, valores_pt['scan']),
                            'fecha_ultima_actualizacion': fields.Datetime.now()
                        }
                        
                        device.sudo().write(valores_equipo)
                        _logger.info(f"✅ Equipo actualizado con valores máximos")
                        
                except Exception as equipo_sync_error:
                    _logger.warning(f"⚠️ Error en sincronización adicional del equipo: {equipo_sync_error}")
                
                return False
                
        except Exception as e:
            _logger.error(f"❌ Error actualizando registro contador automático: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    def _crear_registro_contador_automatico(self, device, meter_data):
        """
        CORREGIDO: Crea un nuevo registro en contador.automatico desde PrintTracker
        FIX: Cálculo correcto de scan y manejo de tipos
        
        Args:
            device: Equipo de alquiler
            meter_data: Datos del medidor desde PrintTracker
        
        Returns:
            bool: True si se creó exitosamente, False si no
        """
        try:
            _logger.info(f"🆕 === CREANDO REGISTRO DESDE PRINTTRACKER ===")
            _logger.info(f"🎯 Equipo: ID={device.id}, Serie={device.serie}")
            
            # Extraer datos del medidor PrintTracker
            page_counts = meter_data.get('pageCounts', {})
            life_counts = page_counts.get('life', {})
            
            # ✅ CORRECCIÓN 1: Usar _safe_int para conversión segura
            total_value = life_counts.get('total', {}).get('value', 0)
            black_value = life_counts.get('totalBlack', {}).get('value', 0)
            color_value = life_counts.get('totalColor', {}).get('value', 0)
            
            # Obtener valores de contadores con conversión segura
            total_pages = self._safe_int(total_value)
            black_pages = self._safe_int(black_value)
            color_pages = self._safe_int(color_value)
            
            # ✅ CORRECCIÓN 2: Cálculo mejorado de scan
            scan_pages = 0
            
            # Método 1: Buscar campo scan directo
            scan_direct = meter_data.get('scanPages', 0)
            if scan_direct:
                scan_pages = self._safe_int(scan_direct)
                _logger.info(f"📄 Scan directo desde PrintTracker: {scan_pages}")
            else:
                # Método 2: Calcular según tipo de equipo
                tipo_equipo = getattr(device, 'tipo_maquina_id', None)
                modelo_name = ""
                
                if hasattr(device, 'name') and device.name:
                    modelo_name = device.name.name.upper() if hasattr(device.name, 'name') else str(device.name).upper()
                
                _logger.info(f"📋 Tipo equipo: {tipo_equipo}, Modelo: {modelo_name}")
                
                if tipo_equipo == 'monocromatica' or 'MONO' in modelo_name:
                    # Para equipos monocromáticos: scan = total - black
                    scan_pages = max(0, total_pages - black_pages)
                    _logger.info(f"📄 Equipo mono - Scan calculado: {scan_pages} (total - black)")
                else:
                    # Para equipos color: scan = total - black - color
                    scan_pages = max(0, total_pages - black_pages - color_pages)
                    _logger.info(f"📄 Equipo color - Scan calculado: {scan_pages} (total - black - color)")
                
                # ✅ CORRECCIÓN 3: Validación adicional para scan
                # Si el scan calculado es muy alto comparado con total, probablemente hay error
                if scan_pages > total_pages * 0.8:  # Más del 80% del total sería scan
                    _logger.warning(f"⚠️ Scan calculado muy alto ({scan_pages}), ajustando...")
                    scan_pages = max(0, int(total_pages * 0.1))  # Asumir 10% como scan
                    _logger.info(f"📄 Scan ajustado conservadoramente: {scan_pages}")
            
            _logger.info(f"📊 Datos extraídos de PrintTracker:")
            _logger.info(f"   Total: {total_pages}")
            _logger.info(f"   Black: {black_pages}")
            _logger.info(f"   Color: {color_pages}")
            _logger.info(f"   Scan (final): {scan_pages}")
            
            # Determinar tipo de equipo para ajustar contadores finales
            cliente = getattr(device, 'cliente_id', None)
            modelo = getattr(device, 'name', None)
            
            _logger.info(f"📋 Información del equipo:")
            _logger.info(f"   Tipo: {tipo_equipo}")
            _logger.info(f"   Cliente: {cliente.name if cliente else 'Sin cliente'}")
            _logger.info(f"   Modelo: {modelo.name if modelo else 'Sin modelo'}")
            
            # ✅ CORRECCIÓN 4: Ajustar contadores según tipo de equipo
            if tipo_equipo == 'monocromatica':
                # Para monocromas: todo el black va a BN, color = 0
                contador_bn_final = black_pages
                contador_color_final = 0
                contador_scan_final = scan_pages
                _logger.info(f"🖤 Equipo monocromático - BN: {contador_bn_final}, Scan: {contador_scan_final}")
            else:
                # Para color: usar contadores separados
                contador_bn_final = black_pages
                contador_color_final = color_pages
                contador_scan_final = scan_pages
                _logger.info(f"🌈 Equipo color - BN: {contador_bn_final}, Color: {contador_color_final}, Scan: {contador_scan_final}")
            
            # Preparar datos del registro
            nombre_registro = f"PrintTracker - {device.serie}"
            if cliente:
                nombre_registro += f" - {cliente.name}"
            
            timestamp_pt = meter_data.get('timestamp')
            fecha_lectura = self._parse_printtracker_datetime(timestamp_pt) if timestamp_pt else fields.Datetime.now()
            
            datos_registro = {
                'name': nombre_registro,
                'serie_detectada': device.serie,
                'equipo_id': device.id,
                'contador_bn_detectado': contador_bn_final,
                'contador_color_detectado': contador_color_final,
                'contador_scan_detectado': contador_scan_final,
                'fecha_procesamiento': fecha_lectura,
                'estado': 'procesado',
                'procesado_automaticamente': True,
                'origen': 'printtracker',
                'marca_detectada': 'PrintTracker',
                'idioma_detectado': 'sistema',
                'formato_detectado': 'api_printtracker',
                'tipo_equipo_detectado': tipo_equipo,
                'cliente_detectado': cliente.name if cliente else None,
                'confianza_deteccion': 100.0,  # Alta confianza en datos de API
                'contenido_procesado': f'Datos automáticos desde PrintTracker API para {device.serie}',
                'remitente': 'PrintTracker API',
                'contador_total_detectado': total_pages
            }
            
            _logger.info(f"📝 Creando registro con datos:")
            for campo, valor in datos_registro.items():
                if valor:
                    _logger.info(f"   {campo}: {valor}")
            
            # Crear el registro
            nuevo_registro = self.env['contador.automatico'].create(datos_registro)
            
            if nuevo_registro:
                _logger.info(f"✅ Registro contador.automatico creado: ID={nuevo_registro.id}")
                
                # ✅ CORRECCIÓN 5: Actualizar contadores del equipo con manejo de errores
                contadores_para_equipo = {
                    'contador_bn': contador_bn_final,
                    'contador_color': contador_color_final,
                    'contador_scan': contador_scan_final,
                    'fecha_ultima_actualizacion': fecha_lectura
                }
                
                _logger.info(f"🔄 Actualizando contadores del equipo...")
                _logger.info(f"📊 Valores para equipo: {contadores_para_equipo}")
                
                try:
                    # Método 1: Usar método específico si existe
                    if hasattr(nuevo_registro, 'actualizar_contadores_equipo'):
                        nuevo_registro.actualizar_contadores_equipo(device, contadores_para_equipo)
                        _logger.info(f"✅ Equipo actualizado con método específico")
                    else:
                        # Método 2: Actualización directa
                        device.sudo().write(contadores_para_equipo)
                        _logger.info(f"✅ Equipo actualizado con write directo")
                        
                    # Verificar actualización
                    device.refresh()
                    _logger.info(f"📊 Verificación post-actualización:")
                    _logger.info(f"   BN: {device.contador_bn}")
                    _logger.info(f"   Color: {device.contador_color}")
                    _logger.info(f"   Scan: {device.contador_scan}")
                    
                except Exception as equipo_error:
                    _logger.error(f"❌ Error actualizando equipo: {equipo_error}")
                    # No es crítico, el registro se creó correctamente
                    _logger.info(f"ℹ️ Registro creado pero equipo no actualizado")
                
                # ✅ CORRECCIÓN 6: Registrar en chatter con información detallada
                try:
                    mensaje_chatter = f"""📊 Contadores creados automáticamente desde PrintTracker:
    • Total: {total_pages:,} páginas
    • B/N: {contador_bn_final:,} páginas  
    • Color: {contador_color_final:,} páginas
    • Scan: {contador_scan_final:,} páginas
    • Tipo equipo: {tipo_equipo or 'No definido'}
    • Fuente: PrintTracker API
    • Registro: contador.automatico ID {nuevo_registro.id}
    • Fecha: {fecha_lectura}"""
                    
                    device.message_post(
                        body=mensaje_chatter,
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )
                    _logger.info(f"📝 Mensaje registrado en chatter del equipo")
                except Exception as chatter_error:
                    _logger.warning(f"⚠️ Error registrando en chatter: {chatter_error}")
                
                return True
            else:
                _logger.error(f"❌ No se pudo crear el registro")
                return False
                
        except Exception as e:
            _logger.error(f"❌ Error creando registro contador automático: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False
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
    def debug_write_issue(self, meter_data, device):
        """
        NUEVO: Diagnóstico para identificar por qué write() resetea contadores
        """
        try:
            _logger.info(f"🔍 === DIAGNÓSTICO DETALLADO WRITE() ===")
            
            # 1. VERIFICAR ESTADO ACTUAL DEL EQUIPO
            _logger.info(f"📊 Estado ANTES de cualquier operación:")
            _logger.info(f"   ID: {device.id}")
            _logger.info(f"   Serie: {device.serie}")
            _logger.info(f"   contador_bn: {device.contador_bn}")
            _logger.info(f"   contador_color: {device.contador_color}")
            _logger.info(f"   contador_scan: {device.contador_scan}")
            
            # 2. PREPARAR VALORES EXACTOS
            page_counts = meter_data.get('pageCounts', {})
            life_counts = page_counts.get('life', {})
            
            valores_nuevos = {
                'contador_bn': life_counts.get('totalBlack', {}).get('value', 0),
                'contador_color': life_counts.get('totalColor', {}).get('value', 0),
                'contador_scan': 0,
                'fecha_ultima_actualizacion': fields.Datetime.now()
            }
            
            _logger.info(f"📊 Valores a escribir: {valores_nuevos}")
            
            # 3. VERIFICAR DEFINICIÓN DE CAMPOS
            _logger.info(f"🔍 === VERIFICANDO DEFINICIÓN DE CAMPOS ===")
            
            field_info = device.fields_get(['contador_bn', 'contador_color', 'contador_scan'])
            for field_name, field_data in field_info.items():
                _logger.info(f"📋 {field_name}:")
                _logger.info(f"   Tipo: {field_data.get('type')}")
                _logger.info(f"   Store: {field_data.get('store', True)}")
                _logger.info(f"   Readonly: {field_data.get('readonly', False)}")
                _logger.info(f"   Required: {field_data.get('required', False)}")
                
                # ❌ PROBLEMA COMÚN: Campos computados sin store
                if 'compute' in field_data and not field_data.get('store', True):
                    _logger.error(f"❌ PROBLEMA: {field_name} es computado sin store=True")
                    _logger.error(f"💡 SOLUCIÓN: Los campos computados sin store se recalculan y pierden valores")
            
            # 4. PROBAR WRITE MÍNIMO
            _logger.info(f"🧪 === PRUEBA 1: WRITE MÍNIMO ===")
            try:
                # Solo actualizar fecha para probar write básico
                device.write({'fecha_ultima_actualizacion': fields.Datetime.now()})
                _logger.info(f"✅ Write mínimo exitoso")
                
                # Verificar que los contadores NO se perdieron
                device.refresh()
                _logger.info(f"📊 Después de write mínimo:")
                _logger.info(f"   contador_bn: {device.contador_bn}")
                _logger.info(f"   contador_color: {device.contador_color}")
                _logger.info(f"   contador_scan: {device.contador_scan}")
                
                if device.contador_bn == 0 and device.contador_color == 0 and device.contador_scan == 0:
                    _logger.error(f"❌ PROBLEMA CONFIRMADO: Write mínimo resetea contadores")
                    _logger.error(f"💡 Probable causa: Campos computados o método write() personalizado")
                    return False
                else:
                    _logger.info(f"✅ Write mínimo preserva contadores")
                    
            except Exception as write_error:
                _logger.error(f"❌ Error en write mínimo: {write_error}")
                return False
            
            # 5. VERIFICAR MÉTODO WRITE PERSONALIZADO
            _logger.info(f"🔍 === VERIFICANDO MÉTODO WRITE PERSONALIZADO ===")
            
            alquiler_model = type(device)
            if hasattr(alquiler_model, 'write'):
                import inspect
                write_method = getattr(alquiler_model, 'write')
                
                # Verificar si el write está sobrescrito
                if write_method.__module__ != 'odoo.models':
                    _logger.warning(f"⚠️ ENCONTRADO: write() personalizado en {write_method.__module__}")
                    _logger.warning(f"🔍 Archivo: {inspect.getfile(write_method)}")
                    _logger.warning(f"💡 REVISAR: El write personalizado puede estar interfiriendo")
                else:
                    _logger.info(f"✅ write() usa el método estándar de Odoo")
            
            return True
            
        except Exception as e:
            _logger.error(f"❌ Error en diagnóstico: {e}")
            return False
    
    def update_device_counters_safe(self):
        """
        NUEVO: Actualización segura con múltiples estrategias
        """
        try:
            _logger.info(f"💾 === ACTUALIZACIÓN SEGURA DE CONTADORES ===")
            
            if not self.device_id:
                _logger.error("❌ No hay device_id asociado")
                return False
            
            # Buscar equipo
            equipo = self.env['alquiler'].search([('serie', '=', self.device_id.serie)], limit=1)
            if not equipo:
                _logger.error(f"❌ No se encontró equipo con serie: {self.device_id.serie}")
                return False
            
            _logger.info(f"🎯 Equipo encontrado: {equipo.serie} (ID: {equipo.id})")
            
            # Preparar valores
            nuevos_valores = {
                'contador_bn': self.black_pages_life or 0,
                'contador_color': self.color_pages_life or 0,
                'fecha_ultima_actualizacion': self.reading_date or fields.Datetime.now()
            }
            
            # ✅ ESTRATEGIA 1: Contexto que deshabilita recálculos
            try:
                _logger.info(f"📝 Intentando actualización con contexto seguro...")
                
                equipo_ctx = equipo.with_context(
                    # Desactivar recompute de campos computados
                    recompute=False,
                    # Sin validaciones de tracking si causan problemas
                    tracking_disable=True,
                    # Sin mail tracking
                    mail_notrack=True,
                    # Marcar como actualización automática
                    automatic_update=True
                )
                
                equipo_ctx.write(nuevos_valores)
                
                # Verificar resultado
                equipo.refresh()
                
                if (equipo.contador_bn == nuevos_valores['contador_bn'] and 
                    equipo.contador_color == nuevos_valores['contador_color']):
                    _logger.info(f"✅ Actualización exitosa con contexto seguro")
                    return True
                else:
                    _logger.warning(f"⚠️ Contexto seguro no preservó valores")
                    
            except Exception as ctx_error:
                _logger.warning(f"⚠️ Error con contexto seguro: {ctx_error}")
            
            # ✅ ESTRATEGIA 2: Actualización campo por campo
            try:
                _logger.info(f"📝 Intentando actualización campo por campo...")
                
                success_count = 0
                
                # BN
                if nuevos_valores['contador_bn'] > 0:
                    equipo.write({'contador_bn': nuevos_valores['contador_bn']})
                    equipo.refresh()
                    if equipo.contador_bn == nuevos_valores['contador_bn']:
                        success_count += 1
                        _logger.info(f"✅ contador_bn actualizado: {equipo.contador_bn}")
                    else:
                        _logger.error(f"❌ contador_bn falló")
                
                # Color
                if nuevos_valores['contador_color'] >= 0:
                    equipo.write({'contador_color': nuevos_valores['contador_color']})
                    equipo.refresh()
                    if equipo.contador_color == nuevos_valores['contador_color']:
                        success_count += 1
                        _logger.info(f"✅ contador_color actualizado: {equipo.contador_color}")
                    else:
                        _logger.error(f"❌ contador_color falló")
                
                # Fecha
                equipo.write({'fecha_ultima_actualizacion': nuevos_valores['fecha_ultima_actualizacion']})
                success_count += 1
                
                if success_count >= 2:
                    _logger.info(f"✅ Actualización campo por campo exitosa ({success_count}/3)")
                    return True
                    
            except Exception as field_error:
                _logger.error(f"❌ Error en actualización campo por campo: {field_error}")
            
            # Si llegamos aquí, hay un problema serio
            _logger.error(f"❌ === TODAS LAS ESTRATEGIAS DE ACTUALIZACIÓN FALLARON ===")
            _logger.error(f"💡 RECOMENDACIÓN: Revisar modelo 'alquiler' por:")
            _logger.error(f"   1. Método write() personalizado problemático")
            _logger.error(f"   2. Campos computados que se recalculan")
            _logger.error(f"   3. Constrains que validan valores")
            _logger.error(f"   4. Triggers que modifican datos")
            
            return False
            
        except Exception as e:
            _logger.error(f"❌ Error en actualización segura: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False
   
    def update_device_counters(self):
        """
        MÉTODO DEFINITIVO: Actualiza contadores con manejo específico de tracking
        CORRECCIÓN: Desactiva tracking temporalmente para evitar conflictos
        """
        try:
            _logger.info(f"💾 === INICIANDO ACTUALIZACIÓN PRINTTRACKER DEFINITIVA ===")
            
            if not self.device_id:
                _logger.error("❌ No hay device_id asociado al medidor")
                return False
            
            # Buscar equipo por serie
            serie_equipo = self.device_id.serie
            if not serie_equipo:
                _logger.error("❌ El dispositivo no tiene serie definida")
                return False
            
            equipo = self.env['alquiler'].search([('serie', '=', serie_equipo)], limit=1)
            if not equipo:
                _logger.error(f"❌ No se encontró equipo con serie: {serie_equipo}")
                return False
            
            _logger.info(f"🎯 Equipo encontrado: ID={equipo.id}, Serie={serie_equipo}")
            
            # Preparar nuevos valores
            nuevos_valores = {
                'contador_bn': self.black_pages_life or 0,
                'contador_color': self.color_pages_life or 0,
                'contador_scan': self.scan_pages or 0,
                'fecha_ultima_actualizacion': self.reading_date or fields.Datetime.now()
            }
            
            _logger.info(f"📊 Valores a actualizar: {nuevos_valores}")
            
            # ✅ ESTRATEGIA DEFINITIVA: Write con tracking desactivado
            try:
                _logger.info(f"📝 Estrategia 1: Write con tracking desactivado...")
                
                # Contexto que desactiva COMPLETAMENTE el tracking y mail
                equipo_no_track = equipo.sudo().with_context(
                    tracking_disable=True,       # Sin tracking
                    mail_notrack=True,          # Sin mail
                    mail_create_nosubscribe=True, # Sin suscripciones
                    mail_create_nolog=True,     # Sin log en chatter
                    no_reset_password=True,     # Sin reset password
                    import_file=True,           # Simular importación
                    install_mode=True,          # Modo instalación
                    active_test=False           # Sin test activo
                )
                
                # Ejecutar write
                equipo_no_track.write(nuevos_valores)
                _logger.info(f"✅ Write sin tracking ejecutado")
                
                # ✅ VERIFICACIÓN INMEDIATA con búsqueda fresca
                equipo_fresh = self.env['alquiler'].browse(equipo.id)
                equipo_fresh.invalidate_cache()
                
                _logger.info(f"📊 Verificación inmediata:")
                _logger.info(f"   BN: {equipo_fresh.contador_bn}")
                _logger.info(f"   Color: {equipo_fresh.contador_color}")
                _logger.info(f"   Scan: {equipo_fresh.contador_scan}")
                
                # Verificar si funcionó
                if (equipo_fresh.contador_bn == nuevos_valores['contador_bn'] and 
                    equipo_fresh.contador_color == nuevos_valores['contador_color']):
                    _logger.info(f"🎉 ÉXITO: Valores actualizados correctamente")
                    return True
                else:
                    _logger.error(f"❌ Falló estrategia 1, probando estrategia 2...")
                    
            except Exception as strategy1_error:
                _logger.error(f"❌ Error en estrategia 1: {strategy1_error}")
            
            # ✅ ESTRATEGIA 2: Update field por field con commit
            try:
                _logger.info(f"📝 Estrategia 2: Actualización campo por campo con commit...")
                
                success_fields = []
                
                # BN
                if nuevos_valores['contador_bn'] > 0:
                    equipo.sudo().write({'contador_bn': nuevos_valores['contador_bn']})
                    self.env.cr.commit()  # Commit inmediato
                    
                    equipo.invalidate_cache()
                    if equipo.contador_bn == nuevos_valores['contador_bn']:
                        success_fields.append('contador_bn')
                        _logger.info(f"✅ contador_bn actualizado: {equipo.contador_bn}")
                
                # Color
                if nuevos_valores['contador_color'] >= 0:
                    equipo.sudo().write({'contador_color': nuevos_valores['contador_color']})
                    self.env.cr.commit()  # Commit inmediato
                    
                    equipo.invalidate_cache()
                    if equipo.contador_color == nuevos_valores['contador_color']:
                        success_fields.append('contador_color')
                        _logger.info(f"✅ contador_color actualizado: {equipo.contador_color}")
                
                # Scan
                if nuevos_valores['contador_scan'] >= 0:
                    equipo.sudo().write({'contador_scan': nuevos_valores['contador_scan']})
                    self.env.cr.commit()  # Commit inmediato
                    
                    equipo.invalidate_cache()
                    if equipo.contador_scan == nuevos_valores['contador_scan']:
                        success_fields.append('contador_scan')
                        _logger.info(f"✅ contador_scan actualizado: {equipo.contador_scan}")
                
                # Fecha
                equipo.sudo().write({'fecha_ultima_actualizacion': nuevos_valores['fecha_ultima_actualizacion']})
                self.env.cr.commit()
                success_fields.append('fecha_ultima_actualizacion')
                
                if len(success_fields) >= 3:  # Al menos 3 campos actualizados
                    _logger.info(f"🎉 ÉXITO: Estrategia 2 funcionó - {len(success_fields)} campos")
                    return True
                else:
                    _logger.error(f"❌ Estrategia 2 parcial: solo {len(success_fields)} campos")
                    
            except Exception as strategy2_error:
                _logger.error(f"❌ Error en estrategia 2: {strategy2_error}")
            
            # ✅ ESTRATEGIA 3: SQL directo como último recurso (SOLO LOGGING)
            _logger.error(f"❌ TODAS LAS ESTRATEGIAS ORM FALLARON")
            _logger.error(f"💡 DIAGNÓSTICO NECESARIO:")
            _logger.error(f"   1. Verificar permisos del usuario")
            _logger.error(f"   2. Revisar si hay triggers en la base de datos")
            _logger.error(f"   3. Verificar constrains del modelo")
            _logger.error(f"   4. Revisar módulos que hereden de 'alquiler'")
            
            # Log de información técnica para diagnóstico
            _logger.error(f"📋 Info técnica del equipo:")
            _logger.error(f"   ID: {equipo.id}")
            _logger.error(f"   Modelo: {equipo._name}")
            _logger.error(f"   Usuario: {self.env.user.login}")
            _logger.error(f"   Compañía: {self.env.company.name}")
            
            return False
            
        except Exception as e:
            _logger.error(f"❌ Error general en actualización: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
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



