# ================================================================================================
# MODELO: printtracker_alert_manager.py - Gestor de Alertas PrintTracker
# Corregido: Endpoints reales de API, sin duplicados, email configurable
# ================================================================================================

from odoo import models, fields, api
import logging
import traceback
from datetime import datetime, timedelta, date
import json
import requests

_logger = logging.getLogger(__name__)


class PrintTrackerAlertManager(models.TransientModel):
    _name = 'printtracker.alert.manager'
    _description = 'Gestor de Alertas PrintTracker'

    # ==========================================
    # CAMPOS DE CONFIGURACIÓN DE REVISIÓN
    # ==========================================
    revisar_suministros = fields.Boolean('Revisar Suministros', default=True)
    revisar_equipos_offline = fields.Boolean('Revisar Equipos Offline', default=True)
    revisar_uso_anomalo = fields.Boolean('Revisar Uso Anómalo', default=True)
    revisar_contadores_decrecen = fields.Boolean('Revisar Contadores que Decrecen', default=True)
    revisar_api_events = fields.Boolean('Revisar Events de API', default=True)

    # ==========================================
    # UMBRALES CONFIGURABLES
    # ==========================================
    umbral_suministro_bajo = fields.Float('Umbral Suministro Bajo (%)', default=15.0)
    umbral_suministro_critico = fields.Float('Umbral Suministro Crítico (%)', default=5.0)
    dias_offline_alerta = fields.Integer('Días Offline para Alerta', default=3)
    dias_offline_critico = fields.Integer('Días Offline Crítico', default=7)

    # ==========================================
    # RESULTADOS DE EJECUCIÓN
    # ==========================================
    alertas_suministros = fields.Integer('Alertas de Suministros', readonly=True)
    alertas_offline = fields.Integer('Alertas de Equipos Offline', readonly=True)
    alertas_uso_anomalo = fields.Integer('Alertas de Uso Anómalo', readonly=True)
    alertas_contadores = fields.Integer('Alertas de Contadores', readonly=True)
    alertas_api_events = fields.Integer('Alertas de API Events', readonly=True)
    notificaciones_enviadas = fields.Integer('Notificaciones Enviadas', readonly=True)
    errores_encontrados = fields.Integer('Errores Encontrados', readonly=True)
    ultimo_event_procesado = fields.Char('Último Event ID Procesado', readonly=True)
    tiempo_ejecucion = fields.Float('Tiempo de Ejecución (seg)', readonly=True)
    log_ejecucion = fields.Text('Log de Ejecución', readonly=True)

    # ==========================================
    # MÉTODO PRINCIPAL - CRON CADA 5 MINUTOS
    # ==========================================
    @api.model
    def ejecutar_revision_automatica(self):
        """
        Ejecutado por el cron cada 5 minutos.
        Revisa todos los tipos de alertas configurados.
        """
        try:
            _logger.info("🚨 === INICIANDO REVISIÓN AUTOMÁTICA DE ALERTAS ===")

            alert_manager = self.create({
                'revisar_suministros': True,
                'revisar_equipos_offline': True,
                'revisar_uso_anomalo': True,
                'revisar_contadores_decrecen': True,
                'revisar_api_events': True,
            })

            resultado = alert_manager.ejecutar_revision_completa()

            if resultado:
                total_alertas = (
                    alert_manager.alertas_suministros +
                    alert_manager.alertas_offline +
                    alert_manager.alertas_uso_anomalo +
                    alert_manager.alertas_contadores +
                    alert_manager.alertas_api_events
                )
                _logger.info(
                    f"✅ Revisión automática completada: {total_alertas} alertas, "
                    f"{alert_manager.notificaciones_enviadas} notificaciones"
                )
                if alert_manager.alertas_api_events > 0:
                    _logger.info(f"📋 API Events procesados: {alert_manager.alertas_api_events}")
                if alert_manager.ultimo_event_procesado:
                    _logger.info(f"🆔 Último event: {alert_manager.ultimo_event_procesado}")
            else:
                _logger.error("❌ Error en revisión automática de alertas")

            return resultado

        except Exception as e:
            _logger.error(f"❌ Error crítico en revisión automática: {e}")
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    # ==========================================
    # EJECUTAR REVISIÓN COMPLETA (TODAS LAS REVISIONES)
    # ==========================================
    def ejecutar_revision_completa(self):
        """Ejecuta revisión completa de todos los tipos de alertas."""
        try:
            inicio_tiempo = datetime.now()
            log_lines = []
            total_alertas = 0
            total_notificaciones = 0

            log_lines.append(f"🚨 === INICIANDO REVISIÓN DE ALERTAS ===")
            log_lines.append(f"⏰ Hora: {inicio_tiempo.strftime('%Y-%m-%d %H:%M:%S')}")
            log_lines.append("")

            # --- REVISIÓN 1: Suministros bajos/críticos ---
            if self.revisar_suministros:
                log_lines.append("🎨 === REVISANDO SUMINISTROS ===")
                resultado = self._revisar_suministros_bajos()
                log_lines.extend(resultado['log'])
                self.alertas_suministros = resultado['alertas']
                total_alertas += resultado['alertas']
                total_notificaciones += resultado['notificaciones']
                log_lines.append("")

            # --- REVISIÓN 2: Equipos offline ---
            if self.revisar_equipos_offline:
                log_lines.append("📵 === REVISANDO EQUIPOS OFFLINE ===")
                resultado = self._revisar_equipos_offline()
                log_lines.extend(resultado['log'])
                self.alertas_offline = resultado['alertas']
                total_alertas += resultado['alertas']
                total_notificaciones += resultado['notificaciones']
                log_lines.append("")

            # --- REVISIÓN 3: Uso anómalo ---
            if self.revisar_uso_anomalo:
                log_lines.append("📊 === REVISANDO USO ANÓMALO ===")
                resultado = self._revisar_uso_anomalo()
                log_lines.extend(resultado['log'])
                self.alertas_uso_anomalo = resultado['alertas']
                total_alertas += resultado['alertas']
                total_notificaciones += resultado['notificaciones']
                log_lines.append("")

            # --- REVISIÓN 4: Contadores que decrecen ---
            if self.revisar_contadores_decrecen:
                log_lines.append("⬇️ === REVISANDO CONTADORES QUE DECRECEN ===")
                resultado = self._revisar_contadores_decrecen()
                log_lines.extend(resultado['log'])
                self.alertas_contadores = resultado['alertas']
                total_alertas += resultado['alertas']
                total_notificaciones += resultado['notificaciones']
                log_lines.append("")

            # --- REVISIÓN 5: Events de PrintTracker API ---
            if self.revisar_api_events:
                log_lines.append("📋 === REVISANDO EVENTS DE PRINTTRACKER API ===")
                resultado = self._revisar_api_events()
                log_lines.extend(resultado['log'])
                self.alertas_api_events = resultado['alertas']
                self.ultimo_event_procesado = resultado.get('ultimo_event_id', '')
                total_alertas += resultado['alertas']
                total_notificaciones += resultado['notificaciones']
                log_lines.append("")

            # --- PASO FINAL: Notificaciones pendientes ---
            log_lines.append("📬 === PROCESANDO NOTIFICACIONES ===")
            resultado_notif = self._procesar_notificaciones_pendientes()
            log_lines.extend(resultado_notif['log'])
            total_notificaciones += resultado_notif['notificaciones']
            self.notificaciones_enviadas = total_notificaciones

            # --- Estadísticas finales ---
            tiempo_total = (datetime.now() - inicio_tiempo).total_seconds()
            self.tiempo_ejecucion = tiempo_total

            log_lines.append("📊 === ESTADÍSTICAS FINALES ===")
            log_lines.append(f"⏱️ Tiempo total: {tiempo_total:.2f} segundos")
            log_lines.append(f"🎨 Alertas suministros: {self.alertas_suministros}")
            log_lines.append(f"📵 Alertas offline: {self.alertas_offline}")
            log_lines.append(f"📊 Alertas uso anómalo: {self.alertas_uso_anomalo}")
            log_lines.append(f"⬇️ Alertas contadores: {self.alertas_contadores}")
            log_lines.append(f"📋 Alertas API events: {self.alertas_api_events}")
            log_lines.append(f"🚨 Total alertas: {total_alertas}")
            log_lines.append(f"📬 Notificaciones enviadas: {total_notificaciones}")
            log_lines.append(f"❌ Errores: {self.errores_encontrados}")
            if self.ultimo_event_procesado:
                log_lines.append(f"🆔 Último event procesado: {self.ultimo_event_procesado}")
            log_lines.append("")
            log_lines.append("✅ === REVISIÓN COMPLETADA ===")

            self.log_ejecucion = "\n".join(log_lines)

            _logger.info(
                f"✅ Revisión completada: {total_alertas} alertas, "
                f"{total_notificaciones} notificaciones, {tiempo_total:.2f}s"
            )
            return True

        except Exception as e:
            error_msg = f"❌ Error en revisión de alertas: {e}"
            _logger.error(error_msg)
            _logger.error(f"Traceback: {traceback.format_exc()}")
            self.log_ejecucion = (self.log_ejecucion or "") + f"\n{error_msg}"
            self.errores_encontrados = (self.errores_encontrados or 0) + 1
            return False

    # ==========================================
    # REVISIÓN 1: SUMINISTROS BAJOS/CRÍTICOS
    # ==========================================
    def _revisar_suministros_bajos(self):
        """Revisa suministros bajos y críticos."""
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0

            _logger.info("🎨 === INICIANDO REVISIÓN DE SUMINISTROS ===")

            suministros_problematicos = self.env['printtracker.supply'].search([
                ('is_active', '=', True),
                ('is_replaced', '=', False),
                '|',
                ('percent_remaining', '<=', self.umbral_suministro_bajo),
                ('percent_remaining', '=', 0)
            ])

            log_lines.append(f"🎨 Encontrados {len(suministros_problematicos)} suministros con problemas")
            _logger.info(f"🎨 Suministros problemáticos: {len(suministros_problematicos)}")

            for suministro in suministros_problematicos:
                try:
                    device_serial = suministro.device_id.serie if suministro.device_id else 'N/A'

                    nueva_alerta = self.env['printtracker.alert'].crear_alerta_suministro_bajo(suministro)

                    if nueva_alerta:
                        alertas_creadas += 1
                        log_lines.append(
                            f"🚨 Alerta: {device_serial} - {suministro.supply_type} "
                            f"({suministro.percent_remaining:.1f}%)"
                        )
                        # Notificación inmediata para suministros críticos
                        if suministro.percent_remaining <= self.umbral_suministro_critico:
                            nueva_alerta.procesar_notificaciones()
                            notificaciones += 1

                except Exception as e:
                    error_msg = f"❌ Error procesando suministro: {e}"
                    log_lines.append(error_msg)
                    _logger.error(error_msg)
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ Suministros: {alertas_creadas} alertas, {notificaciones} notificaciones")
            return {'alertas': alertas_creadas, 'notificaciones': notificaciones, 'log': log_lines}

        except Exception as e:
            error_msg = f"❌ Error crítico revisando suministros: {e}"
            _logger.error(error_msg)
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {'alertas': 0, 'notificaciones': 0, 'log': [error_msg]}

    # ==========================================
    # REVISIÓN 2: EQUIPOS OFFLINE
    # ==========================================
    def _revisar_equipos_offline(self):
        """Revisa equipos que no han reportado recientemente."""
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0

            _logger.info("📵 === INICIANDO REVISIÓN DE EQUIPOS OFFLINE ===")

            equipos_offline = self.env['printtracker.meter'].get_devices_without_recent_readings(
                days=self.dias_offline_alerta
            )

            log_lines.append(f"📵 Encontrados {len(equipos_offline)} equipos offline")
            _logger.info(f"📵 Equipos offline: {len(equipos_offline)}")

            for equipo_info in equipos_offline:
                try:
                    serie = equipo_info['serie']
                    dias_offline = equipo_info['days_offline']
                    ultima_lectura = equipo_info['last_reading']

                    nueva_alerta = self.env['printtracker.alert'].crear_alerta_equipo_offline(
                        serie, dias_offline, ultima_lectura
                    )

                    if nueva_alerta:
                        alertas_creadas += 1
                        log_lines.append(f"📵 Alerta offline: {serie} ({dias_offline} días)")

                        if dias_offline >= self.dias_offline_critico:
                            nueva_alerta.procesar_notificaciones()
                            notificaciones += 1

                except Exception as e:
                    error_msg = f"❌ Error procesando equipo offline {equipo_info.get('serie', 'N/A')}: {e}"
                    log_lines.append(error_msg)
                    _logger.error(error_msg)
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ Offline: {alertas_creadas} alertas, {notificaciones} notificaciones")
            return {'alertas': alertas_creadas, 'notificaciones': notificaciones, 'log': log_lines}

        except Exception as e:
            error_msg = f"❌ Error crítico revisando equipos offline: {e}"
            _logger.error(error_msg)
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {'alertas': 0, 'notificaciones': 0, 'log': [error_msg]}

    # ==========================================
    # REVISIÓN 3: USO ANÓMALO
    # ==========================================
    def _revisar_uso_anomalo(self):
        """Revisa uso anómalamente alto o bajo comparado con promedios."""
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0

            _logger.info("📊 === INICIANDO REVISIÓN DE USO ANÓMALO ===")

            fecha_hoy = date.today()
            fecha_ayer = fecha_hoy - timedelta(days=1)

            lecturas_ayer = self.env['printtracker.daily.reading'].search([
                ('fecha', '=', fecha_ayer),
                ('estado', '=', 'aplicado')
            ])

            log_lines.append(f"📊 Analizando {len(lecturas_ayer)} lecturas de ayer")
            _logger.info(f"📊 Lecturas a analizar: {len(lecturas_ayer)}")

            for lectura_ayer in lecturas_ayer:
                try:
                    serie = lectura_ayer.serie

                    # Promedio de los últimos 7 días (excluyendo ayer)
                    fecha_inicio_promedio = fecha_ayer - timedelta(days=7)
                    lecturas_historicas = self.env['printtracker.daily.reading'].search([
                        ('serie', '=', serie),
                        ('fecha', '>=', fecha_inicio_promedio),
                        ('fecha', '<', fecha_ayer),
                        ('estado', '=', 'aplicado')
                    ])

                    if len(lecturas_historicas) < 3:
                        continue

                    incrementos = [l.incremento_total for l in lecturas_historicas if l.incremento_total > 0]
                    if not incrementos:
                        continue

                    promedio_incremento = sum(incrementos) / len(incrementos)
                    incremento_ayer = lectura_ayer.incremento_total

                    # Uso anómalamente alto (> 3x promedio y > 1000 páginas)
                    if incremento_ayer > promedio_incremento * 3 and incremento_ayer > 1000:
                        nueva_alerta = self.env['printtracker.alert'].crear_alerta_uso_anomalo(
                            serie, 'alto', lectura_ayer.contador_total,
                            lectura_ayer.contador_total - incremento_ayer
                        )
                        if nueva_alerta:
                            alertas_creadas += 1
                            log_lines.append(
                                f"📈 Uso alto: {serie} ({incremento_ayer:,} vs {promedio_incremento:.0f} promedio)"
                            )

                    # Uso anómalamente bajo (< 0.3x promedio y promedio > 100)
                    elif incremento_ayer < promedio_incremento * 0.3 and promedio_incremento > 100:
                        nueva_alerta = self.env['printtracker.alert'].crear_alerta_uso_anomalo(
                            serie, 'bajo', lectura_ayer.contador_total,
                            lectura_ayer.contador_total - incremento_ayer
                        )
                        if nueva_alerta:
                            alertas_creadas += 1
                            log_lines.append(
                                f"📉 Uso bajo: {serie} ({incremento_ayer:,} vs {promedio_incremento:.0f} promedio)"
                            )

                except Exception as e:
                    error_msg = f"❌ Error analizando uso de {lectura_ayer.serie}: {e}"
                    log_lines.append(error_msg)
                    _logger.error(error_msg)
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ Uso anómalo: {alertas_creadas} alertas")
            return {'alertas': alertas_creadas, 'notificaciones': notificaciones, 'log': log_lines}

        except Exception as e:
            error_msg = f"❌ Error crítico revisando uso anómalo: {e}"
            _logger.error(error_msg)
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {'alertas': 0, 'notificaciones': 0, 'log': [error_msg]}

    # ==========================================
    # REVISIÓN 4: CONTADORES QUE DECRECEN
    # ==========================================
    def _revisar_contadores_decrecen(self):
        """Revisa contadores que han decrecido (posible reset o error)."""
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0

            _logger.info("⬇️ === INICIANDO REVISIÓN DE CONTADORES QUE DECRECEN ===")

            fecha_hoy = date.today()
            fecha_ayer = fecha_hoy - timedelta(days=1)
            fecha_anteayer = fecha_hoy - timedelta(days=2)

            lecturas_ayer = self.env['printtracker.daily.reading'].search([
                ('fecha', '=', fecha_ayer),
                ('estado', '=', 'aplicado')
            ])

            log_lines.append(f"⬇️ Analizando {len(lecturas_ayer)} lecturas para contadores que decrecen")
            _logger.info(f"⬇️ Lecturas a analizar: {len(lecturas_ayer)}")

            for lectura_ayer in lecturas_ayer:
                try:
                    serie = lectura_ayer.serie

                    lectura_anteayer = self.env['printtracker.daily.reading'].search([
                        ('serie', '=', serie),
                        ('fecha', '=', fecha_anteayer),
                        ('estado', '=', 'aplicado')
                    ], limit=1)

                    if not lectura_anteayer:
                        continue

                    decrementos = []

                    if lectura_ayer.contador_bn < lectura_anteayer.contador_bn - 100:
                        diferencia = lectura_anteayer.contador_bn - lectura_ayer.contador_bn
                        decrementos.append(('B/N', lectura_ayer.contador_bn, lectura_anteayer.contador_bn, diferencia))

                    if lectura_ayer.contador_color < lectura_anteayer.contador_color - 100:
                        diferencia = lectura_anteayer.contador_color - lectura_ayer.contador_color
                        decrementos.append(('Color', lectura_ayer.contador_color, lectura_anteayer.contador_color, diferencia))

                    if lectura_ayer.contador_scan < lectura_anteayer.contador_scan - 50:
                        diferencia = lectura_anteayer.contador_scan - lectura_ayer.contador_scan
                        decrementos.append(('Scan', lectura_ayer.contador_scan, lectura_anteayer.contador_scan, diferencia))

                    for tipo_contador, valor_actual, valor_anterior, diferencia in decrementos:
                        nueva_alerta = self.env['printtracker.alert'].crear_alerta_contador_decrece(
                            serie, tipo_contador, valor_actual, valor_anterior
                        )
                        if nueva_alerta:
                            alertas_creadas += 1
                            log_lines.append(
                                f"⬇️ Contador decrece: {serie} - {tipo_contador} "
                                f"({valor_anterior:,} → {valor_actual:,}, -{diferencia:,})"
                            )
                            if diferencia > 10000:
                                nueva_alerta.procesar_notificaciones()
                                notificaciones += 1

                except Exception as e:
                    error_msg = f"❌ Error analizando contadores de {lectura_ayer.serie}: {e}"
                    log_lines.append(error_msg)
                    _logger.error(error_msg)
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ Contadores: {alertas_creadas} alertas, {notificaciones} notificaciones")
            return {'alertas': alertas_creadas, 'notificaciones': notificaciones, 'log': log_lines}

        except Exception as e:
            error_msg = f"❌ Error crítico revisando contadores: {e}"
            _logger.error(error_msg)
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {'alertas': 0, 'notificaciones': 0, 'log': [error_msg]}

    # ==========================================
    # REVISIÓN 5: EVENTS DE PRINTTRACKER API
    # Endpoint real: GET /entity/{entityId}/events
    # Respuesta incluye: id, deviceKey, deviceSerialNumber,
    #   timestamp, description, alertType, supplyKey,
    #   resolutionStatus, acknowledged, meterRead
    # ==========================================
    def _revisar_api_events(self):
        """
        Consulta events de PrintTracker Pro API a nivel de entidad.
        Endpoint: GET /v1/entity/{entityId}/events
        Los events ya vienen con deviceSerialNumber, no se necesita iterar por device.
        """
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0
            ultimo_event_id = None

            _logger.info("📋 === INICIANDO REVISIÓN DE API EVENTS ===")

            # Obtener configuración de API
            api_config = self._get_printtracker_api_config()
            if not api_config:
                error_msg = "❌ Configuración de API PrintTracker no encontrada"
                log_lines.append(error_msg)
                _logger.error(error_msg)
                return {'alertas': 0, 'notificaciones': 0, 'log': log_lines}

            _logger.info(f"✅ Config API cargada: entity_id={api_config.get('entity_id')}")

            # Obtener último event procesado (de cualquier device)
            ultimo_timestamp = self._get_ultimo_event_timestamp()

            # Consultar events de la API a nivel de entidad
            events = self._consultar_printtracker_events(api_config, ultimo_timestamp)

            if not events:
                log_lines.append("ℹ️ No hay events nuevos")
                _logger.info("ℹ️ Sin events nuevos de la API")
                return {'alertas': 0, 'notificaciones': 0, 'log': log_lines}

            log_lines.append(f"📋 {len(events)} events nuevos encontrados")
            _logger.info(f"📋 {len(events)} events nuevos de API")

            # Procesar cada event
            for event in events:
                try:
                    event_id = event.get('id')
                    device_serial = event.get('deviceSerialNumber', 'N/A')
                    event_desc = (event.get('description', 'N/A'))[:80]

                    _logger.info(f"📝 Procesando event {event_id}: {device_serial} - {event_desc}")

                    # Verificar que no fue procesado ya (doble check)
                    if self._event_ya_procesado(event_id):
                        continue

                    nueva_alerta = self.env['printtracker.alert'].crear_alerta_desde_api_event(
                        event, device_serial
                    )

                    if nueva_alerta:
                        alertas_creadas += 1
                        ultimo_event_id = event_id

                        # Notificación inmediata si es crítico
                        if self._event_requiere_notificacion_inmediata(event):
                            nueva_alerta.procesar_notificaciones()
                            notificaciones += 1
                            _logger.info(f"📧 Notificación inmediata: event {event_id}")

                        log_lines.append(f"📋 {device_serial}: {event_desc}")

                except Exception as e:
                    error_msg = f"❌ Error procesando event {event.get('id', '?')}: {e}"
                    log_lines.append(error_msg)
                    _logger.error(error_msg)
                    _logger.error(f"Traceback: {traceback.format_exc()}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ API Events: {alertas_creadas} alertas, {notificaciones} notificaciones")
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
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {'alertas': 0, 'notificaciones': 0, 'log': [error_msg]}

    # ==========================================
    # FUNCIONES AUXILIARES PARA API
    # ==========================================

    def _get_printtracker_api_config(self):
        """
        Obtiene configuración de API desde printtracker.entity o parámetros del sistema.
        Retorna dict con: base_url, entity_id, api_key, timeout
        """
        try:
            # Intentar desde entidad activa
            entity = self.env['printtracker.entity'].search([
                ('is_active', '=', True)
            ], limit=1)

            config_params = self.env['ir.config_parameter'].sudo()
            base_url = config_params.get_param(
                'printtracker.api.base_url', 'https://papi.printtrackerpro.com/v1'
            )

            if entity and entity.entity_id:
                api_token = (
                    getattr(entity, 'api_token', None) or
                    config_params.get_param('printtracker.api.key')
                )
                if api_token:
                    _logger.info(f"✅ Config API desde entidad: {entity.name}")
                    return {
                        'base_url': base_url.rstrip('/'),
                        'entity_id': entity.entity_id,
                        'api_key': api_token,
                        'timeout': 30,
                    }

            # Fallback: todo desde parámetros del sistema
            entity_id = config_params.get_param('printtracker.api.entity_id')
            api_key = config_params.get_param('printtracker.api.key')

            if entity_id and api_key:
                _logger.info("✅ Config API desde parámetros del sistema (fallback)")
                return {
                    'base_url': base_url.rstrip('/'),
                    'entity_id': entity_id,
                    'api_key': api_key,
                    'timeout': 30,
                }

            _logger.error("❌ Configuración API incompleta: falta entity_id o api_key")
            return None

        except Exception as e:
            _logger.error(f"❌ Error obteniendo configuración API: {e}")
            return None

    def _get_ultimo_event_timestamp(self):
        """
        Obtiene el timestamp del último event procesado (de cualquier device).
        Se usa para filtrar la API y no reprocesar events.
        """
        try:
            ultima_alerta = self.env['printtracker.alert'].search([
                ('origen_datos', '=', 'api_events'),
                ('api_event_timestamp', '!=', False)
            ], order='api_event_timestamp desc', limit=1)

            if ultima_alerta and ultima_alerta.api_event_timestamp:
                _logger.debug(f"🔗 Último event timestamp: {ultima_alerta.api_event_timestamp}")
                return ultima_alerta.api_event_timestamp

            return None

        except Exception as e:
            _logger.error(f"❌ Error obteniendo último event timestamp: {e}")
            return None

    def _consultar_printtracker_events(self, api_config, ultimo_timestamp=None):
        """
        Consulta events de PrintTracker Pro API a nivel de entidad.
        Endpoint real: GET /v1/entity/{entityId}/events
        Parámetros: start, end, limit, page, includeChildren
        """
        try:
            url = f"{api_config['base_url']}/entity/{api_config['entity_id']}/events"

            headers = {
                'Authorization': f"Bearer {api_config['api_key']}",
                'Content-Type': 'application/json'
            }

            # Parámetros según documentación real de la API
            # La API usa start/end para rango de fechas (como meters y supplies)
            params = {
                'limit': 100,
                'page': 1,
                'includeChildren': 'true',
            }

            # Rango de fechas: desde último procesado hasta ahora
            if ultimo_timestamp:
                params['start'] = ultimo_timestamp.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            else:
                # Primera vez: últimas 24 horas
                start_date = datetime.utcnow() - timedelta(hours=24)
                params['start'] = start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')

            params['end'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')

            _logger.info(f"🌐 Consultando API: {url}")
            _logger.debug(f"📋 Parámetros: {params}")

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=api_config['timeout']
            )

            _logger.info(f"📡 Respuesta API: {response.status_code}")

            if response.status_code == 200:
                events_data = response.json()
                events = events_data if isinstance(events_data, list) else []

                _logger.info(f"📋 Events obtenidos de API: {len(events)}")

                # Filtrar los que ya fueron procesados
                events_nuevos = []
                for event in events:
                    event_id = event.get('id')
                    if event_id and not self._event_ya_procesado(event_id):
                        events_nuevos.append(event)

                _logger.info(f"📋 Events nuevos (no procesados): {len(events_nuevos)}")
                return events_nuevos

            elif response.status_code == 401:
                _logger.error("❌ Error de autenticación API PrintTracker (401)")
                return []
            elif response.status_code == 404:
                _logger.warning("⚠️ Entity no encontrada o sin events (404)")
                return []
            else:
                _logger.error(f"❌ Error API PrintTracker: {response.status_code} - {response.text[:200]}")
                return []

        except requests.exceptions.Timeout:
            _logger.error("❌ Timeout consultando PrintTracker API")
            return []
        except requests.exceptions.RequestException as e:
            _logger.error(f"❌ Error de conexión PrintTracker API: {e}")
            return []
        except Exception as e:
            _logger.error(f"❌ Error consultando PrintTracker events: {e}")
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    def _event_ya_procesado(self, event_id):
        """Verifica si un event de la API ya fue procesado."""
        try:
            return bool(self.env['printtracker.alert'].search([
                ('api_event_id', '=', event_id)
            ], limit=1))
        except Exception as e:
            _logger.error(f"❌ Error verificando event procesado: {e}")
            return False

    def _event_requiere_notificacion_inmediata(self, event):
        """
        Determina si un event requiere notificación inmediata a soporte.
        Basado en campos reales de la API: description, alertType, resolutionStatus, supplyKey
        """
        try:
            description = (event.get('description', '')).lower()
            alert_type = event.get('alertType')
            resolution_status = event.get('resolutionStatus', 'Open')

            # Atascos de papel
            if any(word in description for word in ['jam', 'atasco', 'trabamiento']):
                return True

            # Suministro vacío/agotado
            if any(word in description for word in ['toner', 'ink']) and \
               any(word in description for word in ['empty', 'vacio', 'agotado', 'depleted']):
                return True

            # Errores de dispositivo
            if any(word in description for word in ['error', 'fault', 'codigo']):
                return True

            # Problemas de conectividad
            if any(word in description for word in ['offline', 'connection']):
                return True

            # Events con alertType definido y estado Open
            if resolution_status == 'Open' and alert_type:
                return True

            return False

        except Exception as e:
            _logger.error(f"❌ Error evaluando notificación inmediata: {e}")
            return False

    # ==========================================
    # NOTIFICACIONES PENDIENTES
    # ==========================================
    def _procesar_notificaciones_pendientes(self):
        """Procesa notificaciones pendientes de alertas nuevas (últimos 10 minutos)."""
        try:
            log_lines = []
            notificaciones_enviadas = 0

            _logger.info("📬 === PROCESANDO NOTIFICACIONES PENDIENTES ===")

            alertas_pendientes = self.env['printtracker.alert'].search([
                ('estado', '=', 'nueva'),
                ('fecha_creacion', '>=', datetime.now() - timedelta(minutes=10))
            ])

            log_lines.append(f"📬 Procesando {len(alertas_pendientes)} alertas pendientes")
            _logger.info(f"📬 Alertas pendientes: {len(alertas_pendientes)}")

            for alerta in alertas_pendientes:
                try:
                    alerta.procesar_notificaciones()
                    if alerta.estado == 'notificada':
                        notificaciones_enviadas += 1
                        log_lines.append(f"📧 Notificada: {alerta.display_name}")

                except Exception as e:
                    error_msg = f"❌ Error notificando {alerta.display_name}: {e}"
                    log_lines.append(error_msg)
                    _logger.error(error_msg)
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1

            log_lines.append(f"✅ Notificaciones: {notificaciones_enviadas} enviadas")
            return {'notificaciones': notificaciones_enviadas, 'log': log_lines}

        except Exception as e:
            error_msg = f"❌ Error crítico procesando notificaciones: {e}"
            _logger.error(error_msg)
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {'notificaciones': 0, 'log': [error_msg]}

    # ==========================================
    # ACCIONES DE INTERFAZ
    # ==========================================
    def action_ejecutar_manual(self):
        """Acción para ejecutar revisión manual desde la interfaz."""
        self.ensure_one()

        try:
            _logger.info("🎯 === EJECUCIÓN MANUAL ===")
            resultado = self.ejecutar_revision_completa()

            total_alertas = (
                self.alertas_suministros + self.alertas_offline +
                self.alertas_uso_anomalo + self.alertas_contadores +
                self.alertas_api_events
            )

            if resultado:
                message = (
                    f"✅ Revisión ejecutada exitosamente\n\n"
                    f"🚨 Resumen:\n"
                    f"• Alertas suministros: {self.alertas_suministros}\n"
                    f"• Alertas offline: {self.alertas_offline}\n"
                    f"• Alertas uso anómalo: {self.alertas_uso_anomalo}\n"
                    f"• Alertas contadores: {self.alertas_contadores}\n"
                    f"• Alertas API events: {self.alertas_api_events}\n"
                    f"• Total: {total_alertas}\n"
                    f"• Notificaciones: {self.notificaciones_enviadas}\n"
                    f"• Tiempo: {self.tiempo_ejecucion:.2f}s\n"
                    f"• Errores: {self.errores_encontrados}"
                )
                if self.ultimo_event_procesado:
                    message += f"\n• Último event: {self.ultimo_event_procesado}"

                message_type = 'success' if self.errores_encontrados == 0 else 'warning'
            else:
                message = "❌ Error en revisión de alertas. Revisar log para detalles."
                message_type = 'danger'

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Revisión de Alertas PrintTracker',
                    'message': message,
                    'type': message_type,
                    'sticky': True,
                }
            }

        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'❌ Error: {str(e)}',
                    'type': 'danger',
                }
            }

    def action_view_log(self):
        """Acción para ver el log detallado en una ventana."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Log de Revisión de Alertas',
            'res_model': 'printtracker.alert.manager',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'form_view_initial_mode': 'readonly'},
        }

    # ==========================================
    # UTILIDADES
    # ==========================================
    @api.model
    def limpiar_alertas_resueltas(self):
        """Limpia alertas resueltas antiguas (ejecutar semanalmente vía cron)."""
        try:
            _logger.info("🗑️ === LIMPIEZA DE ALERTAS ===")
            count = self.env['printtracker.alert'].limpiar_alertas_antiguas(30)
            _logger.info(f"✅ Limpieza: {count} alertas antiguas eliminadas")
            return count
        except Exception as e:
            _logger.error(f"❌ Error en limpieza: {e}")
            return 0

    @api.model
    def obtener_dashboard_alertas(self):
        """Obtiene datos para dashboard de alertas."""
        try:
            alertas_activas = self.env['printtracker.alert'].search([
                ('estado', 'in', ['nueva', 'notificada', 'en_proceso'])
            ])

            # Obtener email de soporte configurado
            config_params = self.env['ir.config_parameter'].sudo()
            email_soporte = config_params.get_param(
                'printtracker.alert.email_destino', 'soporte@andescopiers.com.pe'
            )

            return {
                'alertas_por_prioridad': {
                    'urgente': len(alertas_activas.filtered(lambda a: a.prioridad == 'urgente')),
                    'critica': len(alertas_activas.filtered(lambda a: a.prioridad == 'critica')),
                    'alta': len(alertas_activas.filtered(lambda a: a.prioridad == 'alta')),
                    'media': len(alertas_activas.filtered(lambda a: a.prioridad == 'media')),
                    'baja': len(alertas_activas.filtered(lambda a: a.prioridad == 'baja')),
                },
                'alertas_por_tipo': {
                    'suministros': len(alertas_activas.filtered(lambda a: 'suministro' in a.tipo_alerta)),
                    'offline': len(alertas_activas.filtered(lambda a: a.tipo_alerta == 'equipo_offline')),
                    'uso_anomalo': len(alertas_activas.filtered(lambda a: 'uso_anomalo' in a.tipo_alerta)),
                    'contadores': len(alertas_activas.filtered(lambda a: a.tipo_alerta == 'contador_decrece')),
                    'api_events': len(alertas_activas.filtered(lambda a: a.origen_datos == 'api_events')),
                },
                'alertas_por_origen': {
                    'interno': len(alertas_activas.filtered(lambda a: a.origen_datos == 'interno')),
                    'api_events': len(alertas_activas.filtered(lambda a: a.origen_datos == 'api_events')),
                },
                'total_activas': len(alertas_activas),
                'equipos_con_problemas': len(set(alertas_activas.mapped('serie_equipo'))),
                'email_soporte': email_soporte,
                'ultima_revision': datetime.now().strftime('%H:%M:%S'),
            }

        except Exception as e:
            _logger.error(f"❌ Error obteniendo dashboard: {e}")
            return {}