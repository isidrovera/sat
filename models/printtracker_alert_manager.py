from odoo import models, fields, api
import logging
from datetime import datetime, timedelta, date

_logger = logging.getLogger(__name__)


class PrintTrackerAlertManager(models.TransientModel):
    _name = 'printtracker.alert.manager'
    _description = 'Gestor de Alertas PrintTracker'

    # Configuración de revisión
    revisar_suministros = fields.Boolean('Revisar Suministros', default=True)
    revisar_equipos_offline = fields.Boolean('Revisar Equipos Offline', default=True)
    revisar_uso_anomalo = fields.Boolean('Revisar Uso Anómalo', default=True)
    revisar_contadores_decrecen = fields.Boolean('Revisar Contadores que Decrecen', default=True)
    
    # Umbrales configurables
    umbral_suministro_bajo = fields.Float('Umbral Suministro Bajo (%)', default=15.0)
    umbral_suministro_critico = fields.Float('Umbral Suministro Crítico (%)', default=5.0)
    dias_offline_alerta = fields.Integer('Días Offline para Alerta', default=3)
    dias_offline_critico = fields.Integer('Días Offline Crítico', default=7)
    
    # Resultados de la ejecución
    alertas_suministros = fields.Integer('Alertas de Suministros', readonly=True)
    alertas_offline = fields.Integer('Alertas de Equipos Offline', readonly=True)
    alertas_uso_anomalo = fields.Integer('Alertas de Uso Anómalo', readonly=True)
    alertas_contadores = fields.Integer('Alertas de Contadores', readonly=True)
    notificaciones_enviadas = fields.Integer('Notificaciones Enviadas', readonly=True)
    errores_encontrados = fields.Integer('Errores Encontrados', readonly=True)
    
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
                'revisar_contadores_decrecen': True
            })
            
            # Ejecutar revisión
            resultado = alert_manager.ejecutar_revision_completa()
            
            if resultado:
                _logger.info(f"✅ Revisión automática completada exitosamente")
                _logger.info(f"🚨 Resumen: {alert_manager.alertas_suministros + alert_manager.alertas_offline + alert_manager.alertas_uso_anomalo + alert_manager.alertas_contadores} alertas generadas, "
                           f"{alert_manager.notificaciones_enviadas} notificaciones enviadas")
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
        Ejecuta revisión completa de todos los tipos de alertas
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
            log_lines.append(f"🚨 Total alertas: {total_alertas}")
            log_lines.append(f"📬 Notificaciones enviadas: {total_notificaciones}")
            log_lines.append(f"❌ Errores: {self.errores_encontrados}")
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
            self.log_ejecucion = (self.log_ejecucion or "") + f"\n{error_msg}"
            self.errores_encontrados = (self.errores_encontrados or 0) + 1
            return False

    def _revisar_suministros_bajos(self):
        """
        Revisa suministros bajos y críticos
        """
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0
            
            # Obtener suministros activos con alertas
            suministros_problematicos = self.env['printtracker.supply'].search([
                ('is_active', '=', True),
                ('is_replaced', '=', False),
                '|',
                ('percent_remaining', '<=', self.umbral_suministro_bajo),
                ('percent_remaining', '=', 0)
            ])
            
            log_lines.append(f"🎨 Encontrados {len(suministros_problematicos)} suministros con problemas")
            
            for suministro in suministros_problematicos:
                try:
                    # Crear alerta según el nivel
                    nueva_alerta = self.env['printtracker.alert'].crear_alerta_suministro_bajo(suministro)
                    
                    if nueva_alerta:
                        alertas_creadas += 1
                        log_lines.append(f"🚨 Alerta creada: {suministro.device_id.serie} - {suministro.supply_type} ({suministro.percent_remaining:.1f}%)")
                        
                        # Procesar notificación inmediatamente para suministros críticos
                        if suministro.percent_remaining <= self.umbral_suministro_critico:
                            nueva_alerta.procesar_notificaciones()
                            notificaciones += 1
                    
                except Exception as e:
                    log_lines.append(f"❌ Error procesando suministro {suministro.device_id.serie}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ Suministros: {alertas_creadas} alertas creadas, {notificaciones} notificaciones críticas")
            
            return {
                'alertas': alertas_creadas,
                'notificaciones': notificaciones,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error revisando suministros: {e}"
            _logger.error(error_msg)
            return {
                'alertas': 0,
                'notificaciones': 0,
                'log': [error_msg]
            }

    def _revisar_equipos_offline(self):
        """
        Revisa equipos que no han reportado recientemente
        """
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0
            
            # Obtener equipos sin lecturas recientes
            equipos_offline = self.env['printtracker.meter'].get_devices_without_recent_readings(
                days=self.dias_offline_alerta
            )
            
            log_lines.append(f"📵 Encontrados {len(equipos_offline)} equipos offline")
            
            for equipo_info in equipos_offline:
                try:
                    serie = equipo_info['serie']
                    dias_offline = equipo_info['days_offline']
                    ultima_lectura = equipo_info['last_reading']
                    
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
                    
                except Exception as e:
                    log_lines.append(f"❌ Error procesando equipo offline {equipo_info.get('serie', 'unknown')}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ Offline: {alertas_creadas} alertas creadas, {notificaciones} notificaciones críticas")
            
            return {
                'alertas': alertas_creadas,
                'notificaciones': notificaciones,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error revisando equipos offline: {e}"
            _logger.error(error_msg)
            return {
                'alertas': 0,
                'notificaciones': 0,
                'log': [error_msg]
            }

    def _revisar_uso_anomalo(self):
        """
        Revisa uso anómalamente alto o bajo comparado con promedios
        """
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0
            
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
            
            for lectura_ayer in lecturas_ayer:
                try:
                    serie = lectura_ayer.serie
                    
                    # Obtener promedio de los últimos 7 días (excluyendo ayer)
                    fecha_inicio_promedio = fecha_ayer - timedelta(days=7)
                    lecturas_historicas = self.env['printtracker.daily.reading'].search([
                        ('serie', '=', serie),
                        ('fecha', '>=', fecha_inicio_promedio),
                        ('fecha', '<', fecha_ayer),
                        ('estado', '=', 'aplicado')
                    ])
                    
                    if len(lecturas_historicas) < 3:  # Necesitamos al menos 3 días de historia
                        continue
                    
                    # Calcular promedio de incremento diario
                    incrementos = [l.incremento_total for l in lecturas_historicas if l.incremento_total > 0]
                    if not incrementos:
                        continue
                    
                    promedio_incremento = sum(incrementos) / len(incrementos)
                    incremento_ayer = lectura_ayer.incremento_total
                    
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
                    
                    elif incremento_ayer < promedio_incremento * 0.3 and promedio_incremento > 100:
                        # Uso anómalamente bajo
                        nueva_alerta = self.env['printtracker.alert'].crear_alerta_uso_anomalo(
                            serie, 'bajo', lectura_ayer.contador_total,
                            lectura_ayer.contador_total - incremento_ayer
                        )
                        if nueva_alerta:
                            alertas_creadas += 1
                            log_lines.append(f"📉 Uso bajo: {serie} ({incremento_ayer:,} vs {promedio_incremento:.0f} promedio)")
                    
                except Exception as e:
                    log_lines.append(f"❌ Error analizando uso de {lectura_ayer.serie}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ Uso anómalo: {alertas_creadas} alertas creadas")
            
            return {
                'alertas': alertas_creadas,
                'notificaciones': notificaciones,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error revisando uso anómalo: {e}"
            _logger.error(error_msg)
            return {
                'alertas': 0,
                'notificaciones': 0,
                'log': [error_msg]
            }

    def _revisar_contadores_decrecen(self):
        """
        Revisa contadores que han decrecido (posible reset o error)
        """
        try:
            log_lines = []
            alertas_creadas = 0
            notificaciones = 0
            
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
            
            for lectura_ayer in lecturas_ayer:
                try:
                    serie = lectura_ayer.serie
                    
                    # Buscar lectura de anteayer
                    lectura_anteayer = self.env['printtracker.daily.reading'].search([
                        ('serie', '=', serie),
                        ('fecha', '=', fecha_anteayer),
                        ('estado', '=', 'aplicado')
                    ], limit=1)
                    
                    if not lectura_anteayer:
                        continue
                    
                    # Verificar si algún contador decreció significativamente
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
                    
                except Exception as e:
                    log_lines.append(f"❌ Error analizando contadores de {lectura_ayer.serie}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ Contadores: {alertas_creadas} alertas creadas, {notificaciones} notificaciones")
            
            return {
                'alertas': alertas_creadas,
                'notificaciones': notificaciones,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error revisando contadores que decrecen: {e}"
            _logger.error(error_msg)
            return {
                'alertas': 0,
                'notificaciones': 0,
                'log': [error_msg]
            }

    def _procesar_notificaciones_pendientes(self):
        """
        Procesa notificaciones pendientes de alertas nuevas
        """
        try:
            log_lines = []
            notificaciones_enviadas = 0
            
            # Buscar alertas nuevas que necesitan notificación
            alertas_pendientes = self.env['printtracker.alert'].search([
                ('estado', '=', 'nueva'),
                ('fecha_creacion', '>=', datetime.now() - timedelta(minutes=10))  # Solo últimos 10 minutos
            ])
            
            log_lines.append(f"📬 Procesando {len(alertas_pendientes)} alertas pendientes de notificación")
            
            for alerta in alertas_pendientes:
                try:
                    # Procesar notificaciones
                    alerta.procesar_notificaciones()
                    
                    if alerta.estado == 'notificada':
                        notificaciones_enviadas += 1
                        log_lines.append(f"📧 Notificada: {alerta.display_name}")
                    
                except Exception as e:
                    log_lines.append(f"❌ Error notificando {alerta.display_name}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ Notificaciones: {notificaciones_enviadas} enviadas")
            
            return {
                'notificaciones': notificaciones_enviadas,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error procesando notificaciones: {e}"
            _logger.error(error_msg)
            return {
                'notificaciones': 0,
                'log': [error_msg]
            }

    def action_ejecutar_manual(self):
        """
        Acción para ejecutar revisión manual desde la interfaz
        """
        self.ensure_one()
        
        try:
            resultado = self.ejecutar_revision_completa()
            
            total_alertas = (self.alertas_suministros + self.alertas_offline + 
                           self.alertas_uso_anomalo + self.alertas_contadores)
            
            if resultado:
                message = f"""
                ✅ Revisión de alertas ejecutada exitosamente
                
                🚨 Resumen:
                • Alertas de suministros: {self.alertas_suministros}
                • Alertas de equipos offline: {self.alertas_offline}
                • Alertas de uso anómalo: {self.alertas_uso_anomalo}
                • Alertas de contadores: {self.alertas_contadores}
                • Total alertas generadas: {total_alertas}
                • Notificaciones enviadas: {self.notificaciones_enviadas}
                • Tiempo: {self.tiempo_ejecucion:.2f} segundos
                • Errores: {self.errores_encontrados}
                """
                message_type = 'success' if self.errores_encontrados == 0 else 'warning'
            else:
                message = f"❌ Error en revisión de alertas. Revisar log para detalles."
                message_type = 'danger'
            
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
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'❌ Error ejecutando revisión de alertas: {str(e)}',
                    'type': 'danger'
                }
            }

    @api.model
    def limpiar_alertas_resueltas(self):
        """
        UTILIDAD: Limpia alertas resueltas antiguas (ejecutar semanalmente)
        """
        try:
            count_limpiadas = self.env['printtracker.alert'].limpiar_alertas_antiguas(30)
            _logger.info(f"🗑️ Limpieza semanal: {count_limpiadas} alertas antiguas eliminadas")
            return count_limpiadas
        except Exception as e:
            _logger.error(f"❌ Error en limpieza de alertas: {e}")
            return 0

    @api.model
    def obtener_dashboard_alertas(self):
        """
        Obtiene datos para dashboard de alertas
        """
        try:
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
                    'contadores': len(alertas_activas.filtered(lambda a: a.tipo_alerta == 'contador_decrece'))
                },
                'total_activas': len(alertas_activas),
                'equipos_con_problemas': len(set(alertas_activas.mapped('serie_equipo'))),
                'ultima_revision': datetime.now().strftime('%H:%M:%S')
            }
            
            return dashboard
            
        except Exception as e:
            _logger.error(f"❌ Error obteniendo dashboard: {e}")
            return {}

    def action_view_log(self):
        """
        Acción para ver el log detallado en una ventana
        """
        self.ensure_one()
        
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