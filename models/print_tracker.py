from odoo import _, models, fields, api
from odoo.exceptions import UserError

import requests
import logging
import time
import json
from datetime import datetime, timedelta
from html import escape

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

    # Resultado del diagnóstico integral. Se guarda en la propia configuración
    # para no depender de un modelo transient adicional ni de ACLs extra.
    diagnostic_status = fields.Selection([
        ('ok', 'Correcto'),
        ('warning', 'Con observaciones'),
        ('error', 'Con errores'),
    ], string='Estado diagnóstico', readonly=True, copy=False)
    diagnostic_generated_at = fields.Datetime(
        'Fecha diagnóstico', readonly=True, copy=False
    )
    diagnostic_report_html = fields.Html(
        'Resultado diagnóstico', readonly=True, sanitize=False, copy=False
    )
    diagnostic_raw_events = fields.Text(
        'Events API - JSON bruto', readonly=True, copy=False
    )
    
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
        """
        Wrapper para llamadas API con reintentos.

        max_retries representa reintentos adicionales a la primera llamada.
        Ejemplo: max_retries=3 -> hasta 4 intentos totales.
        """
        retries = max(int(self.max_retries or 0), 0)
        attempts = retries + 1
        last_error = None

        for attempt in range(attempts):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.RequestException as error:
                last_error = error
                if attempt >= attempts - 1:
                    raise

                delay = max(int(self.retry_delay or 0), 0)
                _logger.warning(
                    "⚠️ Llamada API falló intento %s/%s: %s. Reintentando en %ss...",
                    attempt + 1,
                    attempts,
                    error,
                    delay,
                )
                if delay:
                    time.sleep(delay)

        if last_error:
            raise last_error

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
                
                # Crear/actualizar entidad principal aislando errores SQL
                with self.env.cr.savepoint():
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
                            try:
                                with self.env.cr.savepoint():
                                    self._sync_entity(
                                        child_data,
                                        parent_entity_id=data['id'],
                                    )
                                children_synced += 1
                            except Exception:
                                _logger.exception(
                                    "❌ Error sincronizando entidad hija id=%s name=%s parent=%s",
                                    child_data.get('id'),
                                    child_data.get('name'),
                                    data.get('id'),
                                )
                
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
        """
        Sincroniza una entidad individual.

        No absorbe errores SQL: el llamador debe usar savepoint para aislarlos.
        """
        entity_id = entity_data.get('id')
        entity_name = entity_data.get('name') or 'Sin nombre'

        if not entity_id:
            raise ValueError("PrintTracker devolvió una entidad sin campo 'id'.")

        existing_entity = self.env['printtracker.entity'].search([
            ('pt_entity_id', '=', entity_id)
        ], limit=1)

        parent_entity = self.env['printtracker.entity'].browse()
        if parent_entity_id:
            parent_entity = self.env['printtracker.entity'].search([
                ('pt_entity_id', '=', parent_entity_id)
            ], limit=1)

        entity_values = {
            'pt_entity_id': entity_id,
            'name': entity_name,
            'genealogy': str(entity_data.get('genealogy', [])),
            'parent_id': parent_entity.id if parent_entity else False,
            'last_sync': fields.Datetime.now(),
            'sync_error': False,
            'is_active': True,
        }

        try:
            if existing_entity:
                existing_entity.write(entity_values)
                entity = existing_entity
                _logger.info("📝 Entidad actualizada: %s (%s)", entity_name, entity_id)
            else:
                entity = self.env['printtracker.entity'].create(entity_values)
                _logger.info("🆕 Entidad creada: %s (%s)", entity_name, entity_id)

            if 'addresses' in entity_data:
                sync_addresses = getattr(entity, '_sync_addresses', None)
                if callable(sync_addresses):
                    sync_addresses(entity_data.get('addresses') or [])

            if 'labels' in entity_data:
                sync_labels = getattr(entity, '_sync_labels', None)
                if callable(sync_labels):
                    sync_labels(entity_data.get('labels') or {})

            return entity
        except Exception:
            _logger.exception(
                "❌ Error sincronizando entidad name=%s id=%s parent=%s",
                entity_name,
                entity_id,
                parent_entity_id,
            )
            raise

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
                    'excludeDisabled': bool(self.solo_equipos_gestionados),
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

                    if not isinstance(devices_page, list):
                        raise ValueError(
                            "PrintTracker /device devolvió un JSON no-lista "
                            f"en página {page}: {type(devices_page).__name__}"
                        )

                    _logger.info(
                        "📊 Página %s: %s dispositivos recibidos",
                        page,
                        len(devices_page),
                    )
                    
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
                serial_number = device_data.get('serialNumber')
                device_key = device_data.get('id')

                try:
                    with self.env.cr.savepoint():
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

                except Exception:
                    devices_error += 1
                    _logger.exception(
                        "❌ Error procesando dispositivo %s/%s serial=%s pt_device_id=%s",
                        i + 1,
                        len(all_devices),
                        serial_number,
                        device_key,
                    )

                if (i + 1) % 10 == 0:
                    _logger.info(
                        "📊 Progreso: %s/%s dispositivos procesados",
                        i + 1,
                        len(all_devices),
                    )

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
            _logger.exception("❌ Error sincronizando dispositivos: %s", e)
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
        Sincroniza el mapeo de un dispositivo PrintTracker con alquiler.

        No actualiza contadores. Los errores SQL se propagan para que el
        savepoint del llamador revierta únicamente este dispositivo.
        """
        serial_number = str(device_data.get('serialNumber') or '').strip()
        device_key = device_data.get('id')

        if not serial_number or serial_number.lower() in ('notavailable', 'none'):
            _logger.info("⏭️ Saltando dispositivo con serie inválida: %s", serial_number)
            return 'invalid_serial'

        existing_device = self.env['alquiler'].search([
            ('serie', '=', serial_number)
        ], limit=1)

        if not existing_device:
            _logger.info(
                "📋 Equipo en PrintTracker no registrado en Odoo: serial=%s pt_device_id=%s",
                serial_number,
                device_key,
            )
            return 'not_in_odoo'

        entity = self.env['printtracker.entity'].search([
            ('pt_entity_id', '=', device_data.get('entityKey'))
        ], limit=1)

        update_values = {
            'pt_device_id': device_key,
            'pt_entity_id': entity.id if entity else False,
            'pt_last_sync': fields.Datetime.now(),
        }

        if 'mac_address' in existing_device._fields:
            update_values['mac_address'] = device_data.get('macAddress')
        if 'ip_address' in existing_device._fields:
            update_values['ip_address'] = device_data.get('ipAddress')
        if 'custom_location' in existing_device._fields:
            update_values['custom_location'] = device_data.get('customLocation')
        if 'asset_id' in existing_device._fields:
            update_values['asset_id'] = (
                device_data.get('assetID')
                if device_data.get('assetID') is not None
                else device_data.get('assetId')
            )
        if 'is_managed' in existing_device._fields:
            update_values['is_managed'] = device_data.get('managed', True)

        try:
            existing_device.sudo().write(update_values)
            _logger.info(
                "📝 Equipo mapeado con PrintTracker: serial=%s pt_device_id=%s entity=%s",
                serial_number,
                device_key,
                device_data.get('entityKey'),
            )
            return 'updated'
        except Exception:
            _logger.exception(
                "❌ Error sincronizando dispositivo serial=%s pt_device_id=%s entity=%s values=%s",
                serial_number,
                device_key,
                device_data.get('entityKey'),
                update_values,
            )
            raise

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
                    'excludeDisabled': bool(self.solo_equipos_gestionados),
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

                    if not isinstance(meters_page, list):
                        raise ValueError(
                            "PrintTracker /currentMeter devolvió un JSON no-lista "
                            f"en página {page}: {type(meters_page).__name__}"
                        )

                    _logger.info(
                        "📊 Página %s: %s medidores recibidos",
                        page,
                        len(meters_page),
                    )
                    
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
                device_key = meter_data.get('deviceKey')
                meter_id = meter_data.get('id')

                try:
                    with self.env.cr.savepoint():
                        result = self._sync_meter(meter_data)

                    if result:
                        meters_synced += 1
                    else:
                        meters_failed += 1

                except Exception:
                    meters_failed += 1
                    _logger.exception(
                        "❌ Error procesando medidor %s/%s meter_id=%s deviceKey=%s",
                        i + 1,
                        len(all_meters),
                        meter_id,
                        device_key,
                    )

                if (i + 1) % 10 == 0:
                    _logger.info(
                        "📊 Progreso: %s/%s medidores procesados (ok=%s fallidos=%s)",
                        i + 1,
                        len(all_meters),
                        meters_synced,
                        meters_failed,
                    )

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
            _logger.exception("❌ Error sincronizando medidores: %s", e)
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
        Sincroniza una lectura actual de PrintTracker en printtracker.meter.

        La documentación actual de GET /currentMeter muestra pageCounts.life.
        Para compatibilidad aceptamos: life -> default -> equiv.
        Este método NO actualiza los contadores del equipo alquiler.
        """
        device_key = meter_data.get('deviceKey')
        meter_id = meter_data.get('id')

        if not device_key:
            _logger.warning("⚠️ Medidor omitido: falta deviceKey meter_id=%s", meter_id)
            return False

        device = self.env['alquiler'].search([
            ('pt_device_id', '=', device_key)
        ], limit=1)

        if not device:
            _logger.warning(
                "⚠️ Medidor omitido: no existe alquiler con pt_device_id=%s meter_id=%s",
                device_key,
                meter_id,
            )
            return False

        page_counts = meter_data.get('pageCounts') or {}
        if not isinstance(page_counts, dict):
            _logger.warning(
                "⚠️ Medidor omitido: pageCounts no es dict meter_id=%s deviceKey=%s type=%s",
                meter_id,
                device_key,
                type(page_counts).__name__,
            )
            return False

        counter_format = None
        counts = {}
        for candidate in ('life', 'default', 'equiv'):
            candidate_counts = page_counts.get(candidate)
            if isinstance(candidate_counts, dict) and candidate_counts:
                counter_format = candidate
                counts = candidate_counts
                break

        if not counts:
            _logger.warning(
                "⚠️ Medidor omitido: no existe pageCounts.life/default/equiv meter_id=%s deviceKey=%s keys=%s",
                meter_id,
                device_key,
                list(page_counts.keys()),
            )
            return False

        if counter_format != 'life':
            _logger.info(
                "ℹ️ Medidor usando formato alternativo pageCounts.%s meter_id=%s deviceKey=%s",
                counter_format,
                meter_id,
                device_key,
            )

        def _counter(name):
            raw = counts.get(name) or {}
            if isinstance(raw, dict):
                raw = raw.get('value', 0)
            return self._safe_int(raw, 0)

        meter_values = {
            'pt_meter_id': meter_id,
            'device_id': device.id,
            'reading_date': self._parse_printtracker_datetime(meter_data.get('timestamp')),
            'console_status': meter_data.get('console'),
            'total_pages_life': _counter('total'),
            'black_pages_life': _counter('totalBlack'),
            'color_pages_life': _counter('totalColor'),
            'scan_pages': _counter('totalScans'),
            'copy_pages': _counter('totalCopies'),
            'fax_pages': _counter('totalFaxes'),
            'print_pages': _counter('totalPrints'),
            'sync_source': 'api',
            'last_sync': fields.Datetime.now(),
        }

        try:
            existing_meter = self.env['printtracker.meter'].search([
                ('pt_meter_id', '=', meter_id)
            ], limit=1)

            if existing_meter:
                existing_meter.write(meter_values)
                _logger.info(
                    "📝 Medidor actualizado: serie=%s meter_id=%s deviceKey=%s format=%s total=%s bn=%s color=%s",
                    device.serie,
                    meter_id,
                    device_key,
                    counter_format,
                    meter_values['total_pages_life'],
                    meter_values['black_pages_life'],
                    meter_values['color_pages_life'],
                )
            else:
                self.env['printtracker.meter'].create(meter_values)
                _logger.info(
                    "🆕 Medidor creado: serie=%s meter_id=%s deviceKey=%s format=%s total=%s bn=%s color=%s",
                    device.serie,
                    meter_id,
                    device_key,
                    counter_format,
                    meter_values['total_pages_life'],
                    meter_values['black_pages_life'],
                    meter_values['color_pages_life'],
                )

            return True
        except Exception:
            _logger.exception(
                "❌ Error SQL/ORM sincronizando medidor serie=%s meter_id=%s deviceKey=%s format=%s values=%s",
                device.serie,
                meter_id,
                device_key,
                counter_format,
                meter_values,
            )
            raise

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

    def _diagnostic_request(self, endpoint, params=None, timeout=None):
        """GET de diagnóstico. No escribe datos operativos en Odoo ni en PrintTracker."""
        self.ensure_one()

        url = f'{self.api_url.rstrip("/")}/{endpoint.lstrip("/")}'
        started = time.monotonic()

        try:
            response = requests.get(
                url,
                headers=self.get_api_headers(),
                params=params or {},
                timeout=(timeout or self.timeout_seconds),
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
                # Diagnóstico: basta una muestra reciente; no intentamos
                # descargar todo el histórico de suministros.
                'start': start_30d_str,
                'end': end_str,
                'limit': min(int(self.max_records_per_request or 100), 200),
                'page': 1,
            },
            timeout=max(int(self.timeout_seconds or 30), 45),
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
            add(
                'Supplies API',
                f"HTTP {supplies['status_code']} - {self._diagnostic_sample_text(supplies['text'], 250)}",
                'warn',
            )
            warnings.append(
                'La consulta de supplies no respondió dentro del tiempo esperado. '
                'Esto no bloquea la detección de alerts/events.'
            )

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

        self.sudo().write({
            'diagnostic_status': overall,
            'diagnostic_generated_at': fields.Datetime.now(),
            'diagnostic_report_html': html_report,
            'diagnostic_raw_events': raw_events_text,
        })

        action = {
            'type': 'ir.actions.act_window',
            'name': 'Diagnóstico PrintTracker',
            'res_model': 'printtracker.config',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self.env.context, printtracker_diagnostic_mode=True),
        }

        # Usar la vista moderna dedicada si está cargada. Si por alguna razón
        # no existe todavía, Odoo abrirá el formulario normal sin romper la prueba.
        try:
            diagnostic_view = self.env.ref(
                'sat.view_printtracker_config_diagnostic_form',
                raise_if_not_found=False,
            )
            if diagnostic_view:
                action['view_id'] = diagnostic_view.id
                action['views'] = [(diagnostic_view.id, 'form')]
        except Exception:
            _logger.exception(
                '⚠️ No se pudo resolver la vista moderna de diagnóstico PrintTracker'
            )

        return action

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
