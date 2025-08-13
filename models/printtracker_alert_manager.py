# ================================================================================================
# MODELO 2 - PARTE 1/3: printtracker_alert_manager.py - IMPORTS Y CAMPOS
# ================================================================================================

from odoo import models, fields, api
import logging
from datetime import datetime, timedelta, date
import json
import requests

_logger = logging.getLogger(__name__)


class PrintTrackerAlertManager(models.TransientModel):
    _name = 'printtracker.alert.manager'
    _description = 'Gestor de Alertas PrintTracker'

    # Configuración de revisión - CAMPOS EXISTENTES
    revisar_suministros = fields.Boolean('Revisar Suministros', default=True)
    revisar_equipos_offline = fields.Boolean('Revisar Equipos Offline', default=True)
    revisar_uso_anomalo = fields.Boolean('Revisar Uso Anómalo', default=True)
    revisar_contadores_decrecen = fields.Boolean('Revisar Contadores que Decrecen', default=True)
    
    # NUEVO CAMPO - AGREGAR
    revisar_api_events = fields.Boolean('Revisar Events de API', default=True)
    
    # Umbrales configurables - CAMPOS EXISTENTES
    umbral_suministro_bajo = fields.Float('Umbral Suministro Bajo (%)', default=15.0)
    umbral_suministro_critico = fields.Float('Umbral Suministro Crítico (%)', default=5.0)
    dias_offline_alerta = fields.Integer('Días Offline para Alerta', default=3)
    dias_offline_critico = fields.Integer('Días Offline Crítico', default=7)
    
    # Resultados de la ejecución - CAMPOS EXISTENTES
    alertas_suministros = fields.Integer('Alertas de Suministros', readonly=True)
    alertas_offline = fields.Integer('Alertas de Equipos Offline', readonly=True)
    alertas_uso_anomalo = fields.Integer('Alertas de Uso Anómalo', readonly=True)
    alertas_contadores = fields.Integer('Alertas de Contadores', readonly=True)
    notificaciones_enviadas = fields.Integer('Notificaciones Enviadas', readonly=True)
    errores_encontrados = fields.Integer('Errores Encontrados', readonly=True)
    
    # NUEVOS CAMPOS - AGREGAR
    alertas_api_events = fields.Integer('Alertas de API Events', readonly=True)
    ultimo_event_procesado = fields.Char('Último Event ID Procesado', readonly=True)
    
    # CAMPOS EXISTENTES
    tiempo_ejecucion = fields.Float('Tiempo de Ejecución (seg)', readonly=True)
    log_ejecucion = fields.Text('Log de Ejecución', readonly=True)

    @api.model
    def ejecutar_revision_automatica(self):
        """
        MÉTODO PRINCIPAL: Ejecutado por el cron cada 5 minutos
        Revisa todos los tipos de alertas configurados
        """
        try:
            _logger.info("🚨 === INICIANDO REVISIÓN AUTOMÁTICA DE ALERTAS ===")
            
            # Crear registro de ejecución
            alert_manager = self.create({
                'revisar_suministros': True,
                'revisar_equipos_offline': True,
                'revisar_uso_anomalo': True,
                'revisar_contadores_decrecen': True,
                'revisar_api_events': True  # NUEVO
            })
            
            # Ejecutar revisión
            resultado = alert_manager.ejecutar_revision_completa()
            
            if resultado:
                _logger.info(f"✅ Revisión automática completada exitosamente")
                total_alertas = (alert_manager.alertas_suministros + alert_manager.alertas_offline + 
                               alert_manager.alertas_uso_anomalo + alert_manager.alertas_contadores + 
                               alert_manager.alertas_api_events)  # NUEVO
                _logger.info(f"🚨 Resumen: {total_alertas} alertas generadas, "
                           f"{alert_manager.notificaciones_enviadas} notificaciones enviadas")
                
                # NUEVO - Log de API Events
                if alert_manager.alertas_api_events > 0:
                    _logger.info(f"📋 API Events procesados: {alert_manager.alertas_api_events}")
                if alert_manager.ultimo_event_procesado:
                    _logger.info(f"🆔 Último event procesado: {alert_manager.ultimo_event_procesado}")
            else:
                _logger.error(f"❌ Error en revisión automática de alertas")
            
            return resultado
            
        except Exception as e:
            _logger.error(f"❌ Error crítico en revisión automática de alertas: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def ejecutar_revision_completa(self):
        """
        Ejecuta revisión completa de todos los tipos de alertas - FUNCIÓN MODIFICADA
        """
        try:
            inicio_tiempo = datetime.now()
            log_lines = []
            
            log_lines.append(f"🚨 === INICIANDO REVISIÓN DE ALERTAS ===")
            log_lines.append(f"⏰ Hora: {inicio_tiempo.strftime('%Y-%m-%d %H:%M:%S')}")
            log_lines.append("")
            
            total_alertas = 0
            total_notificaciones = 0
            
            # REVISIÓN 1: Suministros bajos/críticos
            if self.revisar_suministros:
                log_lines.append("🎨 === REVISANDO SUMINISTROS ===")
                resultado_suministros = self._revisar_suministros_bajos()
                log_lines.extend(resultado_suministros['log'])
                self.alertas_suministros = resultado_suministros['alertas']
                total_alertas += resultado_suministros['alertas']
                total_notificaciones += resultado_suministros['notificaciones']
                log_lines.append("")
            
            # REVISIÓN 2: Equipos offline
            if self.revisar_equipos_offline:
                log_lines.append("📵 === REVISANDO EQUIPOS OFFLINE ===")
                resultado_offline = self._revisar_equipos_offline()
                log_lines.extend(resultado_offline['log'])
                self.alertas_offline = resultado_offline['alertas']
                total_alertas += resultado_offline['alertas']
                total_notificaciones += resultado_offline['notificaciones']
                log_lines.append("")
            
            # REVISIÓN 3: Uso anómalo
            if self.revisar_uso_anomalo:
                log_lines.append("📊 === REVISANDO USO ANÓMALO ===")
                resultado_uso = self._revisar_uso_anomalo()
                log_lines.extend(resultado_uso['log'])
                self.alertas_uso_anomalo = resultado_uso['alertas']
                total_alertas += resultado_uso['alertas']
                total_notificaciones += resultado_uso['notificaciones']
                log_lines.append("")
            
            # REVISIÓN 4: Contadores que decrecen
            if self.revisar_contadores_decrecen:
                log_lines.append("⬇️ === REVISANDO CONTADORES QUE DECRECEN ===")
                resultado_contadores = self._revisar_contadores_decrecen()
                log_lines.extend(resultado_contadores['log'])
                self.alertas_contadores = resultado_contadores['alertas']
                total_alertas += resultado_contadores['alertas']
                total_notificaciones += resultado_contadores['notificaciones']
                log_lines.append("")
            
            # REVISIÓN 5: NUEVA - Events de PrintTracker API
            if self.revisar_api_events:
                log_lines.append("📋 === REVISANDO EVENTS DE PRINTTRACKER API ===")
                resultado_api_events = self._revisar_api_events()
                log_lines.extend(resultado_api_events['log'])
                self.alertas_api_events = resultado_api_events['alertas']
                self.ultimo_event_procesado = resultado_api_events.get('ultimo_event_id', '')
                total_alertas += resultado_api_events['alertas']
                total_notificaciones += resultado_api_events['notificaciones']
                log_lines.append("")
            
            # PASO FINAL: Procesar notificaciones pendientes
            log_lines.append("📬 === PROCESANDO NOTIFICACIONES ===")
            resultado_notif = self._procesar_notificaciones_pendientes()
            log_lines.extend(resultado_notif['log'])
            total_notificaciones += resultado_notif['notificaciones']
            self.notificaciones_enviadas = total_notificaciones
            
            # Estadísticas finales
            tiempo_total = (datetime.now() - inicio_tiempo).total_seconds()
            self.tiempo_ejecucion = tiempo_total
            
            log_lines.append("📊 === ESTADÍSTICAS FINALES ===")
            log_lines.append(f"⏱️ Tiempo total: {tiempo_total:.2f} segundos")
            log_lines.append(f"🎨 Alertas suministros: {self.alertas_suministros}")
            log_lines.append(f"📵 Alertas offline: {self.alertas_offline}")
            log_lines.append(f"📊 Alertas uso anómalo: {self.alertas_uso_anomalo}")
            log_lines.append(f"⬇️ Alertas contadores: {self.alertas_contadores}")
            log_lines.append(f"📋 Alertas API events: {self.alertas_api_events}")  # NUEVO
            log_lines.append(f"🚨 Total alertas: {total_alertas}")
            log_lines.append(f"📬 Notificaciones enviadas: {total_notificaciones}")
            log_lines.append(f"❌ Errores: {self.errores_encontrados}")
            if self.ultimo_event_procesado:  # NUEVO
                log_lines.append(f"🆔 Último event procesado: {self.ultimo_event_procesado}")
            log_lines.append("")
            log_lines.append("✅ === REVISIÓN COMPLETADA ===")
            
            # Guardar log completo
            self.log_ejecucion = "\n".join(log_lines)
            
            _logger.info(f"✅ Revisión de alertas completada: {total_alertas} alertas, "
                        f"{total_notificaciones} notificaciones, {tiempo_total:.2f}s")
            
            return True
            
        except Exception as e:
            error_msg = f"❌ Error en revisión de alertas: {e}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            self.log_ejecucion = (self.log_ejecucion or "") + f"\n{error_msg}"
            self.errores_encontrados = (self.errores_encontrados or 0) + 1
            return False

    def _revisar_api_events(self):
        """
        Revisa events de PrintTracker Pro API y crea alertas
        """
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0
            ultimo_event_id = None
            
            _logger.info("📋 === INICIANDO REVISIÓN DE API EVENTS ===")
            
            # Obtener configuración de API desde printtracker.entity
            api_config = self._get_printtracker_api_config()
            if not api_config:
                error_msg = "❌ Configuración de API PrintTracker no encontrada"
                log_lines.append(error_msg)
                _logger.error(error_msg)
                return {'alertas': 0, 'notificaciones': 0, 'log': log_lines}
            
            _logger.info(f"✅ Configuración API cargada: entity_id={api_config.get('entity_id')}")
            
            # Obtener devices activos con pt_device_id configurado
            devices = self._get_active_devices()
            log_lines.append(f"📋 Revisando events para {len(devices)} dispositivos")
            _logger.info(f"📋 Dispositivos a procesar: {len(devices)}")
            
            for device in devices:
                try:
                    device_serial = device.serie
                    device_key = device.pt_device_id  # Usando el campo existente
                    
                    if not device_key:
                        log_lines.append(f"⚠️ Device {device_serial} sin pt_device_id configurado")
                        _logger.warning(f"⚠️ Device {device_serial} sin pt_device_id")
                        continue
                    
                    _logger.info(f"🔍 Procesando device: {device_serial} (key: {device_key})")
                    
                    # Obtener último event procesado para este device
                    ultimo_event_procesado = self._get_ultimo_event_procesado(device_serial)
                    _logger.debug(f"🔗 Último event procesado para {device_serial}: {ultimo_event_procesado}")
                    
                    # Consultar events de la API
                    events = self._consultar_printtracker_events(
                        api_config, device_key, ultimo_event_procesado
                    )
                    
                    if not events:
                        _logger.debug(f"ℹ️ No hay events nuevos para {device_serial}")
                        continue
                    
                    log_lines.append(f"📋 Device {device_serial}: {len(events)} events nuevos")
                    _logger.info(f"📋 Device {device_serial}: {len(events)} events nuevos encontrados")
                    
                    # Procesar cada event
                    for event in events:
                        try:
                            event_id = event.get('id')
                            event_desc = event.get('description', 'N/A')[:50]
                            _logger.info(f"📝 Procesando event {event_id}: {event_desc}...")
                            
                            nueva_alerta = self.env['printtracker.alert'].crear_alerta_desde_api_event(
                                event, device_serial
                            )
                            
                            if nueva_alerta:
                                alertas_creadas += 1
                                ultimo_event_id = event_id
                                
                                # Determinar si necesita notificación inmediata
                                if self._event_requiere_notificacion_inmediata(event):
                                    nueva_alerta.procesar_notificaciones()
                                    notificaciones += 1
                                    _logger.info(f"📧 Notificación inmediata enviada para event {event_id}")
                                
                                log_lines.append(f"📋 Event procesado: {event_desc}...")
                                _logger.info(f"✅ Event {event_id} procesado exitosamente")
                            else:
                                _logger.warning(f"⚠️ No se pudo crear alerta para event {event_id}")
                            
                        except Exception as e:
                            error_msg = f"❌ Error procesando event {event.get('id', 'unknown')}: {e}"
                            log_lines.append(error_msg)
                            _logger.error(error_msg)
                            import traceback
                            _logger.error(f"Traceback: {traceback.format_exc()}")
                            self.errores_encontrados = (self.errores_encontrados or 0) + 1
                
                except Exception as e:
                    error_msg = f"❌ Error procesando device {device_serial}: {e}"
                    log_lines.append(error_msg)
                    _logger.error(error_msg)
                    import traceback
                    _logger.error(f"Traceback: {traceback.format_exc()}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ API Events: {alertas_creadas} alertas creadas, {notificaciones} notificaciones")
            _logger.info(f"✅ API Events completado: {alertas_creadas} alertas, {notificaciones} notificaciones")
            
            return {
                'alertas': alertas_creadas,
                'notificaciones': notificaciones,
                'ultimo_event_id': ultimo_event_id,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error crítico revisando API events: {e}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'alertas': 0,
                'notificaciones': 0,
                'log': [error_msg]
            }

    # FUNCIONES AUXILIARES PARA API - NUEVAS
    def _get_printtracker_api_config(self):
        """
        Obtiene configuración de API desde el modelo printtracker.entity - CORREGIDO
        """
        try:
            # Buscar la entidad PrintTracker configurada
            entity = self.env['printtracker.entity'].search([
                ('is_active', '=', True)
            ], limit=1)
            
            if not entity:
                _logger.error("❌ No se encontró entidad PrintTracker activa")
                return None
            
            # CORRECCIÓN: Verificar campos disponibles y usar URL base de parámetros del sistema
            if not entity.entity_id:
                _logger.error(f"❌ Entidad PrintTracker sin entity_id: {entity.name}")
                return None
            
            # Obtener URL base desde parámetros del sistema como fallback
            config_params = self.env['ir.config_parameter'].sudo()
            base_url = config_params.get_param('printtracker.api.base_url', 'https://papi.printtrackerpro.com/v1')
            
            # Verificar si la entidad tiene campos de API, sino usar parámetros del sistema
            api_token = getattr(entity, 'api_token', None) or config_params.get_param('printtracker.api.key')
            
            if not api_token:
                _logger.error(f"❌ No se encontró token de API en entidad ni parámetros del sistema")
                return None
            
            api_config = {
                'base_url': base_url.rstrip('/'),
                'entity_id': entity.entity_id,
                'api_key': api_token,
                'timeout': 30
            }
            
            _logger.info(f"✅ Configuración API obtenida desde entidad: {entity.name}")
            _logger.debug(f"🔧 Config: base_url={base_url}, entity_id={entity.entity_id}")
            return api_config
            
        except Exception as e:
            _logger.error(f"❌ Error obteniendo configuración API: {e}")
            # FALLBACK: Intentar obtener todo desde parámetros del sistema
            try:
                config_params = self.env['ir.config_parameter'].sudo()
                fallback_config = {
                    'base_url': config_params.get_param('printtracker.api.base_url', 'https://papi.printtrackerpro.com/v1'),
                    'entity_id': config_params.get_param('printtracker.api.entity_id'),
                    'api_key': config_params.get_param('printtracker.api.key'),
                    'timeout': 30
                }
                
                if fallback_config['entity_id'] and fallback_config['api_key']:
                    _logger.info(f"✅ Usando configuración fallback desde parámetros del sistema")
                    return fallback_config
                else:
                    _logger.error(f"❌ Configuración fallback incompleta")
                    return None
                    
            except Exception as fallback_error:
                _logger.error(f"❌ Error en configuración fallback: {fallback_error}")
                return None
    @api.model
    def crear_alerta_equipo_offline(self, serie_equipo, dias_sin_lecturas, ultima_lectura=None):
        """
        Crea alerta para equipo offline (CORREGIDO CON MANEJO DE CONCURRENCIA)
        """
        # Agregar retry en caso de error de concurrencia
        max_retries = 3
        for attempt in range(max_retries):
            try:
                _logger.info(f"📵 Procesando equipo offline: {serie_equipo} ({dias_sin_lecturas} días sin lecturas)")
                
                # Usar with_for_update para evitar concurrencia
                existing_alert = self.search([
                    ('serie_equipo', '=', serie_equipo),
                    ('tipo_alerta', '=', 'equipo_offline'),
                    ('origen_datos', '=', 'interno'),
                    ('estado', 'in', ['nueva', 'notificada', 'en_proceso'])
                ], limit=1)
                
                # Si existe, usar transacción para actualizar de forma segura
                if existing_alert:
                    _logger.info(f"🔄 Alerta offline existente: {existing_alert.display_name} (rep: {existing_alert.contador_repeticiones}/{existing_alert.max_repeticiones})")
                    
                    # VERIFICAR LÍMITE antes de incrementar
                    if existing_alert.contador_repeticiones < existing_alert.max_repeticiones:
                        update_vals = {
                            'dias_sin_lecturas': dias_sin_lecturas,
                            'contador_repeticiones': existing_alert.contador_repeticiones + 1,
                            'ultima_revision': fields.Datetime.now()
                        }
                        
                        # Escalamiento según días
                        if dias_sin_lecturas >= 14 and existing_alert.prioridad != 'urgente':
                            update_vals.update({
                                'prioridad': 'urgente',
                                'titulo': f"🚨 URGENTE: Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
                            })
                            _logger.error(f"🚨 Alerta offline escalada a URGENTE: {serie_equipo}")
                        elif dias_sin_lecturas >= 7 and existing_alert.prioridad not in ['critica', 'urgente']:
                            update_vals.update({
                                'prioridad': 'critica',
                                'titulo': f"🔴 CRÍTICO: Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
                            })
                            _logger.warning(f"⬆️ Alerta offline escalada a CRÍTICA: {serie_equipo}")
                        
                        # TRANSACCIÓN SEGURA para evitar concurrencia
                        with self.env.cr.savepoint():
                            existing_alert.write(update_vals)
                            self.env.cr.commit()
                        
                        _logger.info(f"✅ Alerta offline actualizada: {existing_alert.display_name}")
                        return existing_alert
                    else:
                        # Límite alcanzado - escalar a urgente y marcar como en proceso
                        _logger.warning(f"🚨 Alerta offline {existing_alert.display_name} alcanzó máximo repeticiones")
                        
                        with self.env.cr.savepoint():
                            existing_alert.write({
                                'prioridad': 'urgente',
                                'estado': 'en_proceso',
                                'notas_resolucion': f'Equipo offline {dias_sin_lecturas} días. Máximo repeticiones alcanzado. Requiere intervención técnica urgente.',
                                'accion_automatica': 'notificar_tecnico'
                            })
                            self.env.cr.commit()
                        
                        _logger.error(f"🔥 Alerta offline escalada por límite: {serie_equipo}")
                        return existing_alert
                
                # Determinar prioridad según días offline (resto de la función igual)
                if dias_sin_lecturas >= 14:
                    prioridad = 'urgente'
                    titulo = f"🚨 URGENTE: Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
                    _logger.error(f"🚨 EQUIPO OFFLINE URGENTE: {serie_equipo} ({dias_sin_lecturas} días)")
                elif dias_sin_lecturas >= 7:
                    prioridad = 'critica'
                    titulo = f"🔴 CRÍTICO: Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
                    _logger.warning(f"🔴 EQUIPO OFFLINE CRÍTICO: {serie_equipo} ({dias_sin_lecturas} días)")
                elif dias_sin_lecturas >= 3:
                    prioridad = 'alta'
                    titulo = f"📵 Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
                    _logger.warning(f"🟠 EQUIPO OFFLINE: {serie_equipo} ({dias_sin_lecturas} días)")
                else:
                    prioridad = 'media'
                    titulo = f"📵 Equipo offline {dias_sin_lecturas} días - {serie_equipo}"
                    _logger.info(f"🟡 Equipo offline detectado: {serie_equipo} ({dias_sin_lecturas} días)")
                
                # Crear nueva alerta con transacción segura
                with self.env.cr.savepoint():
                    nueva_alerta = self.create({
                        'serie_equipo': serie_equipo,
                        'tipo_alerta': 'equipo_offline',
                        'prioridad': prioridad,
                        'titulo': titulo,
                        'descripcion': f"El equipo no ha reportado lecturas en {dias_sin_lecturas} días. Última lectura: {ultima_lectura or 'No disponible'}",
                        'dias_sin_lecturas': dias_sin_lecturas,
                        'ultima_lectura': ultima_lectura,
                        'fecha_deteccion': fields.Datetime.now(),
                        'origen_datos': 'interno',
                        'accion_automatica': 'notificar_tecnico' if dias_sin_lecturas >= 3 else 'ninguna'
                    })
                    self.env.cr.commit()
                
                _logger.info(f"📵 Nueva alerta offline creada: {nueva_alerta.display_name}")
                return nueva_alerta
                
            except Exception as e:
                if 'could not serialize access due to concurrent update' in str(e) and attempt < max_retries - 1:
                    _logger.warning(f"⚠️ Error de concurrencia en intento {attempt + 1}, reintentando...")
                    import time
                    time.sleep(0.1 * (attempt + 1))  # Backoff exponencial
                    continue
                else:
                    _logger.error(f"❌ Error creando alerta offline (intento {attempt + 1}): {e}")
                    import traceback
                    _logger.error(f"Traceback: {traceback.format_exc()}")
                    return False
        
        _logger.error(f"❌ Falló después de {max_retries} intentos para {serie_equipo}")
        return False
    def _get_active_devices(self):
        """
        Obtiene lista de devices activos que tienen configuración de PrintTracker
        """
        try:
            # Buscar equipos activos con pt_device_id configurado
            devices = self.env['alquiler'].search([
                ('estado', '=', 'activo'),  # Ajustar según tu campo de estado
                ('pt_device_id', '!=', False),
                ('pt_device_id', '!=', '')
            ])
            
            _logger.info(f"📋 Encontrados {len(devices)} devices activos con pt_device_id")
            return devices
            
        except Exception as e:
            _logger.error(f"❌ Error obteniendo devices activos: {e}")
            return []

    def _get_ultimo_event_procesado(self, device_serial):
        """
        Obtiene el ID del último event procesado para un device específico
        """
        try:
            ultima_alerta = self.env['printtracker.alert'].search([
                ('serie_equipo', '=', device_serial),
                ('origen_datos', '=', 'api_events'),
                ('api_event_id', '!=', False)
            ], order='api_event_timestamp desc', limit=1)
            
            ultimo_event_id = ultima_alerta.api_event_id if ultima_alerta else None
            _logger.debug(f"🔗 Último event para {device_serial}: {ultimo_event_id}")
            return ultimo_event_id
            
        except Exception as e:
            _logger.error(f"❌ Error obteniendo último event procesado: {e}")
            return None

    def _consultar_printtracker_events(self, api_config, device_key, ultimo_event_id=None):
        """
        Consulta events de PrintTracker Pro API para un device específico
        """
        try:
            # Construir URL
            url = f"{api_config['base_url']}/entity/{api_config['entity_id']}/device/{device_key}/events"
            
            # Headers de autenticación
            headers = {
                'Authorization': f"Bearer {api_config['api_key']}",
                'Content-Type': 'application/json'
            }
            
            # Parámetros de consulta
            params = {
                'limit': 50,  # Máximo events por consulta
                'sort': 'timestamp:desc'  # Más recientes primero
            }
            
            # Filtrar por timestamp si tenemos último event
            if ultimo_event_id:
                # Obtener timestamp del último event procesado
                ultima_alerta = self.env['printtracker.alert'].search([
                    ('api_event_id', '=', ultimo_event_id)
                ], limit=1)
                
                if ultima_alerta and ultima_alerta.api_event_timestamp:
                    # Solo events más recientes que el último procesado
                    timestamp_filtro = ultima_alerta.api_event_timestamp.isoformat()
                    if not timestamp_filtro.endswith('Z'):
                        timestamp_filtro += 'Z'
                    params['timestamp[gt]'] = timestamp_filtro
                    _logger.debug(f"🔍 Filtrando events después de: {timestamp_filtro}")
            
            _logger.info(f"🌐 Consultando API: {url}")
            _logger.debug(f"📋 Parámetros: {params}")
            
            # Realizar petición HTTP
            response = requests.get(
                url, 
                headers=headers, 
                params=params, 
                timeout=api_config['timeout']
            )
            
            _logger.info(f"📡 Respuesta API: {response.status_code}")
            
            if response.status_code == 200:
                events_data = response.json()
                # La API devuelve una lista de events
                events = events_data if isinstance(events_data, list) else []
                
                _logger.info(f"📋 Events obtenidos de API: {len(events)}")
                
                # Filtrar events que no han sido procesados
                events_nuevos = []
                for event in events:
                    event_id = event.get('id')
                    if event_id and not self._event_ya_procesado(event_id):
                        events_nuevos.append(event)
                
                _logger.info(f"📋 Events nuevos (no procesados): {len(events_nuevos)}")
                return events_nuevos
                
            elif response.status_code == 404:
                # Device no encontrado o sin events
                _logger.warning(f"⚠️ Device {device_key} no encontrado o sin events")
                return []
            elif response.status_code == 401:
                _logger.error(f"❌ Error de autenticación API PrintTracker: {response.status_code}")
                return []
            else:
                _logger.error(f"❌ Error API PrintTracker: {response.status_code} - {response.text}")
                return []
            
        except requests.exceptions.Timeout:
            _logger.error(f"❌ Timeout consultando PrintTracker API para device {device_key}")
            return []
        except requests.exceptions.RequestException as e:
            _logger.error(f"❌ Error de conexión PrintTracker API: {e}")
            return []
        except Exception as e:
            _logger.error(f"❌ Error consultando PrintTracker events: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    def _event_ya_procesado(self, event_id):
        """
        Verifica si un event ya fue procesado
        """
        try:
            existing_alert = self.env['printtracker.alert'].search([
                ('api_event_id', '=', event_id)
            ], limit=1)
            
            ya_procesado = bool(existing_alert)
            if ya_procesado:
                _logger.debug(f"⚠️ Event {event_id} ya procesado")
            
            return ya_procesado
            
        except Exception as e:
            _logger.error(f"❌ Error verificando si event ya fue procesado: {e}")
            return False

    def _event_requiere_notificacion_inmediata(self, event):
        """
        Determina si un event requiere notificación inmediata
        """
        try:
            description = (event.get('description', '')).lower()
            alert_type = event.get('alertType')
            resolution_status = event.get('resolutionStatus', 'Open')
            
            _logger.debug(f"🔍 Evaluando notificación inmediata para: {description[:30]}...")
            
            # Events críticos que requieren notificación inmediata
            eventos_criticos = [
                'jam', 'atasco', 'trabamiento',  # Atascos
                'error', 'fault', 'codigo',      # Errores
                'offline', 'connection',          # Conectividad
                'maintenance', 'service'          # Mantenimiento
            ]
            
            # Events de suministros críticos
            if any(word in description for word in ['toner', 'ink']) and any(word in description for word in ['empty', 'vacio', 'agotado']):
                _logger.info(f"🚨 Notificación inmediata: suministro vacío")
                return True
            
            # Events críticos generales
            if any(word in description for word in eventos_criticos):
                _logger.info(f"🚨 Notificación inmediata: event crítico detectado")
                return True
            
            # Events con resolution status Open y alertType específico
            if resolution_status == 'Open' and alert_type:
                _logger.info(f"🚨 Notificación inmediata: event abierto con alertType")
                return True
            
            _logger.debug(f"ℹ️ Event no requiere notificación inmediata")
            return False
            
        except Exception as e:
            _logger.error(f"❌ Error evaluando notificación inmediata: {e}")
            return False

    # FUNCIONES EXISTENTES MODIFICADAS CON LOGS MEJORADOS
    def _revisar_suministros_bajos(self):
        """
        Revisa suministros bajos y críticos - FUNCIÓN MODIFICADA CON LOGS
        """
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0
            
            _logger.info("🎨 === INICIANDO REVISIÓN DE SUMINISTROS ===")
            
            # Obtener suministros activos con alertas
            suministros_problematicos = self.env['printtracker.supply'].search([
                ('is_active', '=', True),
                ('is_replaced', '=', False),
                '|',
                ('percent_remaining', '<=', self.umbral_suministro_bajo),
                ('percent_remaining', '=', 0)
            ])
            
            log_lines.append(f"🎨 Encontrados {len(suministros_problematicos)} suministros con problemas")
            _logger.info(f"🎨 Suministros problemáticos encontrados: {len(suministros_problematicos)}")
            
            for suministro in suministros_problematicos:
                try:
                    device_serial = suministro.device_id.serie if suministro.device_id else 'N/A'
                    _logger.debug(f"🎨 Procesando suministro: {device_serial} - {suministro.supply_type} ({suministro.percent_remaining:.1f}%)")
                    
                    # Crear alerta según el nivel
                    nueva_alerta = self.env['printtracker.alert'].crear_alerta_suministro_bajo(suministro)
                    
                    if nueva_alerta:
                        alertas_creadas += 1
                        log_lines.append(f"🚨 Alerta creada: {device_serial} - {suministro.supply_type} ({suministro.percent_remaining:.1f}%)")
                        
                        # Procesar notificación inmediatamente para suministros críticos
                        if suministro.percent_remaining <= self.umbral_suministro_critico:
                            nueva_alerta.procesar_notificaciones()
                            notificaciones += 1
                            _logger.info(f"📧 Notificación crítica enviada: {device_serial}")
                    else:
                        _logger.debug(f"ℹ️ No se creó alerta para {device_serial} (posiblemente ya existe)")
                    
                except Exception as e:
                    error_msg = f"❌ Error procesando suministro {suministro.device_id.serie if suministro.device_id else 'N/A'}: {e}"
                    log_lines.append(error_msg)
                    _logger.error(error_msg)
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ Suministros: {alertas_creadas} alertas creadas, {notificaciones} notificaciones críticas")
            _logger.info(f"✅ Suministros completado: {alertas_creadas} alertas, {notificaciones} notificaciones")
            
            return {
                'alertas': alertas_creadas,
                'notificaciones': notificaciones,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error crítico revisando suministros: {e}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'alertas': 0,
                'notificaciones': 0,
                'log': [error_msg]
            }


    def _revisar_equipos_offline(self):
        """
        Revisa equipos que no han reportado recientemente - FUNCIÓN MODIFICADA CON LOGS
        """
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0
            
            _logger.info("📵 === INICIANDO REVISIÓN DE EQUIPOS OFFLINE ===")
            
            # Obtener equipos sin lecturas recientes
            equipos_offline = self.env['printtracker.meter'].get_devices_without_recent_readings(
                days=self.dias_offline_alerta
            )
            
            log_lines.append(f"📵 Encontrados {len(equipos_offline)} equipos offline")
            _logger.info(f"📵 Equipos offline encontrados: {len(equipos_offline)}")
            
            for equipo_info in equipos_offline:
                try:
                    serie = equipo_info['serie']
                    dias_offline = equipo_info['days_offline']
                    ultima_lectura = equipo_info['last_reading']
                    
                    _logger.debug(f"📵 Procesando equipo offline: {serie} ({dias_offline} días)")
                    
                    # Crear alerta
                    nueva_alerta = self.env['printtracker.alert'].crear_alerta_equipo_offline(
                        serie, dias_offline, ultima_lectura
                    )
                    
                    if nueva_alerta:
                        alertas_creadas += 1
                        log_lines.append(f"📵 Alerta offline: {serie} ({dias_offline} días)")
                        
                        # Notificación inmediata para casos críticos
                        if dias_offline >= self.dias_offline_critico:
                            nueva_alerta.procesar_notificaciones()
                            notificaciones += 1
                            _logger.warning(f"📧 Notificación crítica offline enviada: {serie}")
                    else:
                        _logger.debug(f"ℹ️ No se creó alerta offline para {serie} (posiblemente ya existe)")
                    
                except Exception as e:
                    error_msg = f"❌ Error procesando equipo offline {equipo_info.get('serie', 'unknown')}: {e}"
                    log_lines.append(error_msg)
                    _logger.error(error_msg)
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ Offline: {alertas_creadas} alertas creadas, {notificaciones} notificaciones críticas")
            _logger.info(f"✅ Equipos offline completado: {alertas_creadas} alertas, {notificaciones} notificaciones")
            
            return {
                'alertas': alertas_creadas,
                'notificaciones': notificaciones,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error crítico revisando equipos offline: {e}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'alertas': 0,
                'notificaciones': 0,
                'log': [error_msg]
            }

    def _revisar_uso_anomalo(self):
        """
        Revisa uso anómalamente alto o bajo comparado con promedios - FUNCIÓN MODIFICADA CON LOGS
        """
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0
            
            _logger.info("📊 === INICIANDO REVISIÓN DE USO ANÓMALO ===")
            
            # Obtener lecturas de los últimos 2 días para comparar
            fecha_hoy = date.today()
            fecha_ayer = fecha_hoy - timedelta(days=1)
            fecha_anteayer = fecha_hoy - timedelta(days=2)
            
            # Lecturas de ayer
            lecturas_ayer = self.env['printtracker.daily.reading'].search([
                ('fecha', '=', fecha_ayer),
                ('estado', '=', 'aplicado')
            ])
            
            log_lines.append(f"📊 Analizando {len(lecturas_ayer)} lecturas de ayer para uso anómalo")
            _logger.info(f"📊 Lecturas a analizar: {len(lecturas_ayer)} del {fecha_ayer}")
            
            for lectura_ayer in lecturas_ayer:
                try:
                    serie = lectura_ayer.serie
                    
                    _logger.debug(f"📊 Analizando uso anómalo: {serie}")
                    
                    # Obtener promedio de los últimos 7 días (excluyendo ayer)
                    fecha_inicio_promedio = fecha_ayer - timedelta(days=7)
                    lecturas_historicas = self.env['printtracker.daily.reading'].search([
                        ('serie', '=', serie),
                        ('fecha', '>=', fecha_inicio_promedio),
                        ('fecha', '<', fecha_ayer),
                        ('estado', '=', 'aplicado')
                    ])
                    
                    if len(lecturas_historicas) < 3:  # Necesitamos al menos 3 días de historia
                        _logger.debug(f"ℹ️ Insuficiente historia para {serie}: {len(lecturas_historicas)} días")
                        continue
                    
                    # Calcular promedio de incremento diario
                    incrementos = [l.incremento_total for l in lecturas_historicas if l.incremento_total > 0]
                    if not incrementos:
                        _logger.debug(f"ℹ️ Sin incrementos válidos para {serie}")
                        continue
                    
                    promedio_incremento = sum(incrementos) / len(incrementos)
                    incremento_ayer = lectura_ayer.incremento_total
                    
                    _logger.debug(f"📊 {serie}: incremento ayer={incremento_ayer:,}, promedio={promedio_incremento:.0f}")
                    
                    # Detectar anomalías (mayor a 3x o menor a 0.3x el promedio)
                    if incremento_ayer > promedio_incremento * 3 and incremento_ayer > 1000:
                        # Uso anómalamente alto
                        nueva_alerta = self.env['printtracker.alert'].crear_alerta_uso_anomalo(
                            serie, 'alto', lectura_ayer.contador_total, 
                            lectura_ayer.contador_total - incremento_ayer
                        )
                        if nueva_alerta:
                            alertas_creadas += 1
                            log_lines.append(f"📈 Uso alto: {serie} ({incremento_ayer:,} vs {promedio_incremento:.0f} promedio)")
                            _logger.warning(f"📈 USO ALTO ANÓMALO: {serie}")
                    
                    elif incremento_ayer < promedio_incremento * 0.3 and promedio_incremento > 100:
                        # Uso anómalamente bajo
                        nueva_alerta = self.env['printtracker.alert'].crear_alerta_uso_anomalo(
                            serie, 'bajo', lectura_ayer.contador_total,
                            lectura_ayer.contador_total - incremento_ayer
                        )
                        if nueva_alerta:
                            alertas_creadas += 1
                            log_lines.append(f"📉 Uso bajo: {serie} ({incremento_ayer:,} vs {promedio_incremento:.0f} promedio)")
                            _logger.info(f"📉 USO BAJO ANÓMALO: {serie}")
                    
                except Exception as e:
                    error_msg = f"❌ Error analizando uso de {lectura_ayer.serie}: {e}"
                    log_lines.append(error_msg)
                    _logger.error(error_msg)
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ Uso anómalo: {alertas_creadas} alertas creadas")
            _logger.info(f"✅ Uso anómalo completado: {alertas_creadas} alertas")
            
            return {
                'alertas': alertas_creadas,
                'notificaciones': notificaciones,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error crítico revisando uso anómalo: {e}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'alertas': 0,
                'notificaciones': 0,
                'log': [error_msg]
            }

    def _revisar_contadores_decrecen(self):
        """
        Revisa contadores que han decrecido (posible reset o error) - FUNCIÓN MODIFICADA CON LOGS
        """
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0
            
            _logger.info("⬇️ === INICIANDO REVISIÓN DE CONTADORES QUE DECRECEN ===")
            
            # Obtener lecturas de los últimos 2 días para comparar
            fecha_hoy = date.today()
            fecha_ayer = fecha_hoy - timedelta(days=1)
            fecha_anteayer = fecha_hoy - timedelta(days=2)
            
            # Lecturas de ayer
            lecturas_ayer = self.env['printtracker.daily.reading'].search([
                ('fecha', '=', fecha_ayer),
                ('estado', '=', 'aplicado')
            ])
            
            log_lines.append(f"⬇️ Analizando {len(lecturas_ayer)} lecturas para contadores que decrecen")
            _logger.info(f"⬇️ Lecturas a analizar: {len(lecturas_ayer)} del {fecha_ayer}")
            
            for lectura_ayer in lecturas_ayer:
                try:
                    serie = lectura_ayer.serie
                    
                    _logger.debug(f"⬇️ Analizando contadores: {serie}")
                    
                    # Buscar lectura de anteayer
                    lectura_anteayer = self.env['printtracker.daily.reading'].search([
                        ('serie', '=', serie),
                        ('fecha', '=', fecha_anteayer),
                        ('estado', '=', 'aplicado')
                    ], limit=1)
                    
                    if not lectura_anteayer:
                        _logger.debug(f"ℹ️ Sin lectura de anteayer para {serie}")
                        continue
                    
                    # Verificar si algún contador decreció significativamente
                    decrementos = []
                    
                    if lectura_ayer.contador_bn < lectura_anteayer.contador_bn - 100:
                        diferencia = lectura_anteayer.contador_bn - lectura_ayer.contador_bn
                        decrementos.append(('B/N', lectura_ayer.contador_bn, lectura_anteayer.contador_bn, diferencia))
                        _logger.warning(f"⬇️ {serie}: Contador B/N decreció {diferencia:,}")
                    
                    if lectura_ayer.contador_color < lectura_anteayer.contador_color - 100:
                        diferencia = lectura_anteayer.contador_color - lectura_ayer.contador_color
                        decrementos.append(('Color', lectura_ayer.contador_color, lectura_anteayer.contador_color, diferencia))
                        _logger.warning(f"⬇️ {serie}: Contador Color decreció {diferencia:,}")
                    
                    if lectura_ayer.contador_scan < lectura_anteayer.contador_scan - 50:
                        diferencia = lectura_anteayer.contador_scan - lectura_ayer.contador_scan
                        decrementos.append(('Scan', lectura_ayer.contador_scan, lectura_anteayer.contador_scan, diferencia))
                        _logger.warning(f"⬇️ {serie}: Contador Scan decreció {diferencia:,}")
                    
                    # Crear alertas para decrementos significativos
                    for tipo_contador, valor_actual, valor_anterior, diferencia in decrementos:
                        nueva_alerta = self.env['printtracker.alert'].crear_alerta_contador_decrece(
                            serie, tipo_contador, valor_actual, valor_anterior
                        )
                        if nueva_alerta:
                            alertas_creadas += 1
                            log_lines.append(f"⬇️ Contador decrece: {serie} - {tipo_contador} ({valor_anterior:,} → {valor_actual:,}, -{diferencia:,})")
                            
                            # Notificación inmediata para decrementos grandes
                            if diferencia > 10000:
                                nueva_alerta.procesar_notificaciones()
                                notificaciones += 1
                                _logger.error(f"📧 Notificación crítica: contador decrece {serie}")
                    
                except Exception as e:
                    error_msg = f"❌ Error analizando contadores de {lectura_ayer.serie}: {e}"
                    log_lines.append(error_msg)
                    _logger.error(error_msg)
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ Contadores: {alertas_creadas} alertas creadas, {notificaciones} notificaciones")
            _logger.info(f"✅ Contadores que decrecen completado: {alertas_creadas} alertas, {notificaciones} notificaciones")
            
            return {
                'alertas': alertas_creadas,
                'notificaciones': notificaciones,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error crítico revisando contadores que decrecen: {e}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'alertas': 0,
                'notificaciones': 0,
                'log': [error_msg]
            }

    def _procesar_notificaciones_pendientes(self):
        """
        Procesa notificaciones pendientes de alertas nuevas - FUNCIÓN MODIFICADA CON LOGS
        """
        try:
            log_lines = []
            notificaciones_enviadas = 0
            
            _logger.info("📬 === INICIANDO PROCESAMIENTO DE NOTIFICACIONES ===")
            
            # Buscar alertas nuevas que necesitan notificación
            alertas_pendientes = self.env['printtracker.alert'].search([
                ('estado', '=', 'nueva'),
                ('fecha_creacion', '>=', datetime.now() - timedelta(minutes=10))  # Solo últimos 10 minutos
            ])
            
            log_lines.append(f"📬 Procesando {len(alertas_pendientes)} alertas pendientes de notificación")
            _logger.info(f"📬 Alertas pendientes: {len(alertas_pendientes)}")
            
            for alerta in alertas_pendientes:
                try:
                    _logger.debug(f"📬 Procesando notificaciones: {alerta.display_name}")
                    
                    # Procesar notificaciones
                    alerta.procesar_notificaciones()
                    
                    if alerta.estado == 'notificada':
                        notificaciones_enviadas += 1
                        log_lines.append(f"📧 Notificada: {alerta.display_name}")
                        _logger.info(f"✅ Notificación enviada: {alerta.display_name}")
                    else:
                        _logger.debug(f"ℹ️ Alerta no cambió a notificada: {alerta.display_name}")
                    
                except Exception as e:
                    error_msg = f"❌ Error notificando {alerta.display_name}: {e}"
                    log_lines.append(error_msg)
                    _logger.error(error_msg)
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ Notificaciones: {notificaciones_enviadas} enviadas")
            _logger.info(f"✅ Notificaciones completadas: {notificaciones_enviadas} enviadas")
            
            return {
                'notificaciones': notificaciones_enviadas,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error crítico procesando notificaciones: {e}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'notificaciones': 0,
                'log': [error_msg]
            }

    def action_ejecutar_manual(self):
        """
        Acción para ejecutar revisión manual desde la interfaz - FUNCIÓN MODIFICADA
        """
        self.ensure_one()
        
        try:
            _logger.info("🎯 === INICIANDO EJECUCIÓN MANUAL ===")
            
            resultado = self.ejecutar_revision_completa()
            
            total_alertas = (self.alertas_suministros + self.alertas_offline + 
                           self.alertas_uso_anomalo + self.alertas_contadores + 
                           self.alertas_api_events)  # NUEVO
            
            if resultado:
                message = f"""
                ✅ Revisión de alertas ejecutada exitosamente
                
                🚨 Resumen:
                • Alertas de suministros: {self.alertas_suministros}
                • Alertas de equipos offline: {self.alertas_offline}
                • Alertas de uso anómalo: {self.alertas_uso_anomalo}
                • Alertas de contadores: {self.alertas_contadores}
                • Alertas de API events: {self.alertas_api_events}
                • Total alertas generadas: {total_alertas}
                • Notificaciones enviadas: {self.notificaciones_enviadas}
                • Tiempo: {self.tiempo_ejecucion:.2f} segundos
                • Errores: {self.errores_encontrados}
                """
                if self.ultimo_event_procesado:  # NUEVO
                    message += f"\n• Último event procesado: {self.ultimo_event_procesado}"
                
                message_type = 'success' if self.errores_encontrados == 0 else 'warning'
                _logger.info(f"✅ Ejecución manual completada: {total_alertas} alertas, {self.errores_encontrados} errores")
            else:
                message = f"❌ Error en revisión de alertas. Revisar log para detalles."
                message_type = 'danger'
                _logger.error("❌ Error en ejecución manual")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Revisión de Alertas PrintTracker',
                    'message': message,
                    'type': message_type,
                    'sticky': True
                }
            }
            
        except Exception as e:
            error_msg = f'❌ Error ejecutando revisión de alertas: {str(e)}'
            _logger.error(error_msg)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': error_msg,
                    'type': 'danger'
                }
            }

    @api.model
    def limpiar_alertas_resueltas(self):
        """
        UTILIDAD: Limpia alertas resueltas antiguas (ejecutar semanalmente) - FUNCIÓN MODIFICADA
        """
        try:
            _logger.info("🗑️ === INICIANDO LIMPIEZA DE ALERTAS ===")
            
            count_limpiadas = self.env['printtracker.alert'].limpiar_alertas_antiguas(30)
            _logger.info(f"✅ Limpieza semanal completada: {count_limpiadas} alertas antiguas eliminadas")
            return count_limpiadas
        except Exception as e:
            _logger.error(f"❌ Error en limpieza de alertas: {e}")
            return 0

    @api.model
    def obtener_dashboard_alertas(self):
        """
        Obtiene datos para dashboard de alertas - FUNCIÓN MODIFICADA
        """
        try:
            _logger.debug("📊 Obteniendo datos del dashboard de alertas")
            
            # Alertas activas por prioridad
            alertas_activas = self.env['printtracker.alert'].search([
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso'])
            ])
            
            dashboard = {
                'alertas_por_prioridad': {
                    'urgente': len(alertas_activas.filtered(lambda a: a.prioridad == 'urgente')),
                    'critica': len(alertas_activas.filtered(lambda a: a.prioridad == 'critica')),
                    'alta': len(alertas_activas.filtered(lambda a: a.prioridad == 'alta')),
                    'media': len(alertas_activas.filtered(lambda a: a.prioridad == 'media')),
                    'baja': len(alertas_activas.filtered(lambda a: a.prioridad == 'baja'))
                },
                'alertas_por_tipo': {
                    'suministros': len(alertas_activas.filtered(lambda a: 'suministro' in a.tipo_alerta)),
                    'offline': len(alertas_activas.filtered(lambda a: a.tipo_alerta == 'equipo_offline')),
                    'uso_anomalo': len(alertas_activas.filtered(lambda a: 'uso_anomalo' in a.tipo_alerta)),
                    'contadores': len(alertas_activas.filtered(lambda a: a.tipo_alerta == 'contador_decrece')),
                    'api_events': len(alertas_activas.filtered(lambda a: a.origen_datos == 'api_events'))  # NUEVO
                },
                'alertas_por_origen': {  # NUEVO
                    'interno': len(alertas_activas.filtered(lambda a: a.origen_datos == 'interno')),
                    'api_events': len(alertas_activas.filtered(lambda a: a.origen_datos == 'api_events'))
                },
                'total_activas': len(alertas_activas),
                'equipos_con_problemas': len(set(alertas_activas.mapped('serie_equipo'))),
                'ultima_revision': datetime.now().strftime('%H:%M:%S')
            }
            
            _logger.debug(f"📊 Dashboard generado: {dashboard['total_activas']} alertas activas")
            return dashboard
            
        except Exception as e:
            _logger.error(f"❌ Error obteniendo dashboard: {e}")
            return {}

    def action_view_log(self):
        """
        Acción para ver el log detallado en una ventana - FUNCIÓN EXISTENTE SIN CAMBIOS
        """
        self.ensure_one()
        
        _logger.info(f"👁️ Abriendo log de ejecución: {self.id}")
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Log de Revisión de Alertas',
            'res_model': 'printtracker.alert.manager',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'form_view_initial_mode': 'readonly'
            }
        }