from odoo import models, fields, api
import logging
from datetime import datetime, timedelta, date

_logger = logging.getLogger(__name__)


class PrintTrackerConsolidator(models.TransientModel):
    _name = 'printtracker.consolidator'
    _description = 'Consolidador de Datos PrintTracker'

    # Campos para configurar el procesamiento
    fecha_inicio = fields.Date('Fecha Inicio', default=lambda self: date.today() - timedelta(days=1))
    fecha_fin = fields.Date('Fecha Fin', default=lambda self: date.today())
    serie_especifica = fields.Char('Serie Específica', help='Dejar vacío para procesar todas')
    forzar_reproceso = fields.Boolean('Forzar Reproceso', default=False,
                                     help='Reprocesar registros ya consolidados')
    
    # Resultados del procesamiento
    registros_contador_automatico = fields.Integer('Registros Contador Automático', readonly=True)
    registros_printtracker = fields.Integer('Registros PrintTracker', readonly=True)
    lecturas_consolidadas = fields.Integer('Lecturas Consolidadas', readonly=True)
    conflictos_resueltos = fields.Integer('Conflictos Resueltos', readonly=True)
    equipos_actualizados = fields.Integer('Equipos Actualizados', readonly=True)
    errores_encontrados = fields.Integer('Errores Encontrados', readonly=True)
    
    log_procesamiento = fields.Text('Log de Procesamiento', readonly=True)

    @api.model
    def ejecutar_consolidacion_automatica(self):
        """
        MÉTODO PRINCIPAL: Ejecutado por el cron cada 2 horas
        Consolida datos de las últimas 24 horas
        """
        try:
            _logger.info("🔄 === INICIANDO CONSOLIDACIÓN AUTOMÁTICA ===")
            
            # Configurar fechas de procesamiento (últimas 24 horas)
            fecha_fin = date.today()
            fecha_inicio = fecha_fin - timedelta(days=1)
            
            # Crear registro de consolidación
            consolidador = self.create({
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'forzar_reproceso': False
            })
            
            # Ejecutar consolidación
            resultado = consolidador.ejecutar_consolidacion()
            
            if resultado:
                _logger.info(f"✅ Consolidación automática completada exitosamente")
                _logger.info(f"📊 Resumen: {consolidador.lecturas_consolidadas} consolidadas, "
                           f"{consolidador.conflictos_resueltos} conflictos, "
                           f"{consolidador.equipos_actualizados} equipos actualizados")
            else:
                _logger.error(f"❌ Error en consolidación automática")
            
            return resultado
            
        except Exception as e:
            _logger.error(f"❌ Error crítico en consolidación automática: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def ejecutar_consolidacion(self):
        """
        Ejecuta el proceso completo de consolidación
        """
        try:
            inicio_tiempo = datetime.now()
            log_lines = []
            
            log_lines.append(f"🔄 === INICIANDO CONSOLIDACIÓN ===")
            log_lines.append(f"📅 Período: {self.fecha_inicio} a {self.fecha_fin}")
            log_lines.append(f"🎯 Serie: {self.serie_especifica or 'TODAS'}")
            log_lines.append(f"🔄 Forzar reproceso: {'SÍ' if self.forzar_reproceso else 'NO'}")
            log_lines.append("")
            
            # PASO 1: Procesar registros de contador.automatico
            log_lines.append("📧 === PASO 1: PROCESANDO CONTADOR.AUTOMATICO ===")
            resultado_contador = self._procesar_contador_automatico()
            log_lines.extend(resultado_contador['log'])
            self.registros_contador_automatico = resultado_contador['procesados']
            
            # PASO 2: Procesar registros de PrintTracker
            log_lines.append("🔄 === PASO 2: PROCESANDO PRINTTRACKER ===")
            resultado_pt = self._procesar_printtracker_meters()
            log_lines.extend(resultado_pt['log'])
            self.registros_printtracker = resultado_pt['procesados']
            
            # PASO 3: Consolidar lecturas con conflictos
            log_lines.append("⚖️ === PASO 3: CONSOLIDANDO Y RESOLVIENDO CONFLICTOS ===")
            resultado_consolidacion = self._consolidar_lecturas_periodo()
            log_lines.extend(resultado_consolidacion['log'])
            self.lecturas_consolidadas = resultado_consolidacion['consolidadas']
            self.conflictos_resueltos = resultado_consolidacion['conflictos']
            
            # PASO 4: Aplicar a equipos
            log_lines.append("💾 === PASO 4: APLICANDO A EQUIPOS ===")
            resultado_equipos = self._aplicar_a_equipos()
            log_lines.extend(resultado_equipos['log'])
            self.equipos_actualizados = resultado_equipos['actualizados']
            
            # PASO 5: Limpieza y estadísticas finales
            log_lines.append("📊 === PASO 5: ESTADÍSTICAS FINALES ===")
            tiempo_total = (datetime.now() - inicio_tiempo).total_seconds()
            
            log_lines.append(f"⏱️ Tiempo total: {tiempo_total:.2f} segundos")
            log_lines.append(f"📧 Contador automático: {self.registros_contador_automatico} registros")
            log_lines.append(f"🔄 PrintTracker: {self.registros_printtracker} registros")
            log_lines.append(f"⚖️ Consolidadas: {self.lecturas_consolidadas} lecturas")
            log_lines.append(f"⚠️ Conflictos resueltos: {self.conflictos_resueltos}")
            log_lines.append(f"💾 Equipos actualizados: {self.equipos_actualizados}")
            log_lines.append(f"❌ Errores: {self.errores_encontrados}")
            log_lines.append("")
            log_lines.append("✅ === CONSOLIDACIÓN COMPLETADA ===")
            
            # Guardar log completo
            self.log_procesamiento = "\n".join(log_lines)
            
            _logger.info(f"✅ Consolidación completada: {self.lecturas_consolidadas} lecturas, "
                        f"{self.conflictos_resueltos} conflictos, {self.equipos_actualizados} equipos")
            
            return True
            
        except Exception as e:
            error_msg = f"❌ Error en consolidación: {e}"
            _logger.error(error_msg)
            self.log_procesamiento = (self.log_procesamiento or "") + f"\n{error_msg}"
            self.errores_encontrados = (self.errores_encontrados or 0) + 1
            return False

    def _procesar_contador_automatico(self):
        """
        Procesa registros nuevos de contador.automatico
        CORREGIDO: Actualiza registros de PrintTracker existentes
        """
        try:
            log_lines = []
            procesados = 0
            
            # Buscar registros nuevos de contador.automatico en el período
            domain = [
                ('estado', '=', 'procesado'),
                ('fecha_procesamiento', '>=', datetime.combine(self.fecha_inicio, datetime.min.time())),
                ('fecha_procesamiento', '<=', datetime.combine(self.fecha_fin, datetime.max.time())),
                ('serie_detectada', '!=', False)
            ]
            
            if self.serie_especifica:
                domain.append(('serie_detectada', '=', self.serie_especifica))
            
            registros_contador = self.env['contador.automatico'].search(domain)
            log_lines.append(f"📧 Encontrados {len(registros_contador)} registros de contador automático")
            
            for registro in registros_contador:
                try:
                    fecha_lectura = registro.fecha_procesamiento.date()
                    
                    # CORREGIDO: Buscar CUALQUIER lectura existente (no solo correo)
                    existing_reading = self.env['printtracker.daily.reading'].search([
                        ('fecha', '=', fecha_lectura),
                        ('serie', '=', registro.serie_detectada)
                    ], limit=1)
                    
                    if existing_reading:
                        if existing_reading.fuente_origen == 'printtracker':
                            # CASO 1: Actualizar registro de PrintTracker con correo
                            log_lines.append(f"🔄 Actualizando PrintTracker con correo: {registro.serie_detectada} - {fecha_lectura}")
                            
                            # CORREGIDO: Llamar método en la instancia, no en la clase
                            updated_reading = existing_reading._actualizar_lectura_printtracker_con_correo(
                                registro
                            )
                                                        
                            if updated_reading:
                                log_lines.append(f"✅ PrintTracker actualizado con correo: {registro.serie_detectada}")
                                procesados += 1
                            else:
                                log_lines.append(f"❌ Error actualizando PrintTracker: {registro.serie_detectada}")
                            continue
                            
                        elif existing_reading.fuente_origen == 'correo' and not self.forzar_reproceso:
                            # CASO 2: Ya existe correo, saltar
                            log_lines.append(f"⏭️ Ya existe lectura de correo para {registro.serie_detectada} - {fecha_lectura}")
                            continue
                            
                        elif existing_reading.fuente_origen == 'correo' and self.forzar_reproceso:
                            # CASO 3: Forzar actualización de correo
                            existing_reading.write({
                                'contador_bn': registro.contador_bn_detectado or 0,
                                'contador_color': registro.contador_color_detectado or 0,
                                'contador_scan': registro.contador_scan_detectado or 0,
                                'fecha_procesamiento': fields.Datetime.now()
                            })
                            log_lines.append(f"📝 Actualizado correo: {registro.serie_detectada} - {fecha_lectura}")
                            procesados += 1
                            continue
                            
                        elif existing_reading.fuente_origen == 'consolidado':
                            # CASO 4: Ya está consolidado, saltar salvo que se fuerce
                            if not self.forzar_reproceso:
                                log_lines.append(f"⏭️ Ya consolidado: {registro.serie_detectada} - {fecha_lectura}")
                                continue
                    
                    # CASO 5: No existe registro, crear nuevo desde correo
                    log_lines.append(f"🆕 Creando nuevo desde correo: {registro.serie_detectada} - {fecha_lectura}")
                    nueva_lectura = self.env['printtracker.daily.reading'].crear_desde_contador_automatico(registro)
                    if nueva_lectura:
                        log_lines.append(f"✅ Creado desde correo: {registro.serie_detectada}")
                        procesados += 1
                    else:
                        log_lines.append(f"❌ Error creando lectura para {registro.serie_detectada}")
                    
                except Exception as e:
                    log_lines.append(f"❌ Error procesando {registro.serie_detectada}: {e}")
                    _logger.error(f"❌ Error detallado procesando contador {registro.id}: {e}")
                    import traceback
                    _logger.error(f"Traceback: {traceback.format_exc()}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ Procesados {procesados} registros de contador automático")
            
            return {
                'procesados': procesados,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error procesando contador automático: {e}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"Traceback completo: {traceback.format_exc()}")
            return {
                'procesados': 0,
                'log': [error_msg]
            }

    def _procesar_printtracker_meters(self):
        """
        Procesa registros nuevos de printtracker.meter
        CORREGIDO: Actualiza registros de correo existentes
        """
        try:
            log_lines = []
            procesados = 0
            
            # Buscar registros nuevos de PrintTracker en el período
            domain = [
                ('reading_date', '>=', datetime.combine(self.fecha_inicio, datetime.min.time())),
                ('reading_date', '<=', datetime.combine(self.fecha_fin, datetime.max.time())),
                ('device_id', '!=', False),
                ('device_id.serie', '!=', False)
            ]
            
            if self.serie_especifica:
                domain.append(('device_id.serie', '=', self.serie_especifica))
            
            meters = self.env['printtracker.meter'].search(domain)
            log_lines.append(f"🔄 Encontrados {len(meters)} registros de PrintTracker")
            
            for meter in meters:
                try:
                    fecha_lectura = meter.reading_date.date()
                    serie = meter.device_id.serie
                    
                    # CORREGIDO: Buscar CUALQUIER lectura existente (no solo PrintTracker)
                    existing_reading = self.env['printtracker.daily.reading'].search([
                        ('fecha', '=', fecha_lectura),
                        ('serie', '=', serie)
                    ], limit=1)
                    
                    if existing_reading:
                        if existing_reading.fuente_origen == 'correo':
                            # CASO 1: Actualizar registro de correo con PrintTracker
                            log_lines.append(f"📧 Actualizando correo con PrintTracker: {serie} - {fecha_lectura}")
                            
                            # CORREGIDO: Pasar parámetros correctos (lectura_correo, meter_record)
                            updated_reading = existing_reading._actualizar_lectura_correo_con_printtracker(
                                meter
                            )
                            
                            if updated_reading:
                                log_lines.append(f"✅ Correo actualizado con PrintTracker: {serie}")
                                procesados += 1
                            else:
                                log_lines.append(f"❌ Error actualizando correo: {serie}")
                            continue
                            
                        elif existing_reading.fuente_origen == 'printtracker' and not self.forzar_reproceso:
                            # CASO 2: Ya existe PrintTracker, saltar
                            log_lines.append(f"⏭️ Ya existe lectura de PrintTracker para {serie} - {fecha_lectura}")
                            continue
                            
                        elif existing_reading.fuente_origen == 'printtracker' and self.forzar_reproceso:
                            # CASO 3: Forzar actualización de PrintTracker
                            existing_reading.write({
                                'contador_bn': meter.black_pages_life or 0,
                                'contador_color': meter.color_pages_life or 0,
                                'contador_scan': meter.scan_pages or 0,
                                'contador_copy': meter.copy_pages or 0,
                                'contador_fax': meter.fax_pages or 0,
                                'fecha_procesamiento': fields.Datetime.now()
                            })
                            log_lines.append(f"📝 Actualizado PrintTracker: {serie} - {fecha_lectura}")
                            procesados += 1
                            continue
                            
                        elif existing_reading.fuente_origen == 'consolidado':
                            # CASO 4: Ya está consolidado, saltar salvo que se fuerce
                            if not self.forzar_reproceso:
                                log_lines.append(f"⏭️ Ya consolidado: {serie} - {fecha_lectura}")
                                continue
                    
                    # CASO 5: No existe registro, crear nuevo desde PrintTracker
                    log_lines.append(f"🆕 Creando nuevo desde PrintTracker: {serie} - {fecha_lectura}")
                    nueva_lectura = self.env['printtracker.daily.reading'].crear_desde_printtracker(meter)
                    if nueva_lectura:
                        log_lines.append(f"✅ Creado desde PrintTracker: {serie}")
                        procesados += 1
                    else:
                        log_lines.append(f"❌ Error creando lectura para {serie}")
                    
                except Exception as e:
                    log_lines.append(f"❌ Error procesando {meter.device_id.serie}: {e}")
                    _logger.error(f"❌ Error detallado procesando meter {meter.id}: {e}")
                    import traceback
                    _logger.error(f"Traceback: {traceback.format_exc()}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ Procesados {procesados} registros de PrintTracker")
            
            return {
                'procesados': procesados,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error procesando PrintTracker: {e}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"Traceback completo: {traceback.format_exc()}")
            return {
                'procesados': 0,
                'log': [error_msg]
            }

    def _consolidar_lecturas_periodo(self):
        """
        Consolida lecturas del período aplicando reglas de conflicto
        """
        try:
            log_lines = []
            consolidadas = 0
            conflictos = 0
            
            # Obtener todas las fechas del período
            fecha_actual = self.fecha_inicio
            while fecha_actual <= self.fecha_fin:
                
                # Obtener series únicas para esta fecha
                domain = [('fecha', '=', fecha_actual)]
                if self.serie_especifica:
                    domain.append(('serie', '=', self.serie_especifica))
                
                lecturas_fecha = self.env['printtracker.daily.reading'].search(domain)
                series_fecha = list(set(lecturas_fecha.mapped('serie')))
                
                log_lines.append(f"📅 Procesando {fecha_actual}: {len(series_fecha)} series")
                
                for serie in series_fecha:
                    try:
                        # Consolidar esta serie en esta fecha
                        resultado = self.env['printtracker.daily.reading'].consolidar_lecturas(
                            fecha_objetivo=fecha_actual,
                            serie_objetivo=serie
                        )
                        
                        if resultado:
                            if resultado.get('consolidadas', 0) > 0:
                                consolidadas += resultado['consolidadas']
                            if resultado.get('conflictos', 0) > 0:
                                conflictos += resultado['conflictos']
                                log_lines.append(f"⚠️ Conflicto resuelto: {serie} - {fecha_actual}")
                        
                    except Exception as e:
                        log_lines.append(f"❌ Error consolidando {serie} en {fecha_actual}: {e}")
                        self.errores_encontrados = (self.errores_encontrados or 0) + 1
                
                fecha_actual += timedelta(days=1)
            
            log_lines.append(f"✅ Consolidación completada: {consolidadas} lecturas, {conflictos} conflictos")
            
            return {
                'consolidadas': consolidadas,
                'conflictos': conflictos,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error en consolidación: {e}"
            _logger.error(error_msg)
            return {
                'consolidadas': 0,
                'conflictos': 0,
                'log': [error_msg]
            }

    def _aplicar_a_equipos(self):
        """
        Aplica lecturas consolidadas pendientes a los equipos
        """
        try:
            log_lines = []
            actualizados = 0
            
            # Buscar lecturas validadas pero no aplicadas
            domain = [
                ('estado', '=', 'validado'),
                ('aplicado_a_equipo', '=', False),
                ('fecha', '>=', self.fecha_inicio),
                ('fecha', '<=', self.fecha_fin)
            ]
            
            if self.serie_especifica:
                domain.append(('serie', '=', self.serie_especifica))
            
            lecturas_pendientes = self.env['printtracker.daily.reading'].search(domain)
            log_lines.append(f"💾 Encontradas {len(lecturas_pendientes)} lecturas pendientes de aplicar")
            
            for lectura in lecturas_pendientes:
                try:
                    if lectura._aplicar_lectura_a_equipo(lectura):
                        actualizados += 1
                        log_lines.append(f"✅ Aplicado: {lectura.serie} - {lectura.fecha}")
                    else:
                        log_lines.append(f"❌ Error aplicando: {lectura.serie} - {lectura.fecha}")
                        self.errores_encontrados = (self.errores_encontrados or 0) + 1
                        
                except Exception as e:
                    log_lines.append(f"❌ Error aplicando {lectura.serie}: {e}")
                    self.errores_encontrados = (self.errores_encontrados or 0) + 1
            
            log_lines.append(f"✅ Aplicación completada: {actualizados} equipos actualizados")
            
            return {
                'actualizados': actualizados,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error aplicando a equipos: {e}"
            _logger.error(error_msg)
            return {
                'actualizados': 0,
                'log': [error_msg]
            }

    def action_ejecutar_manual(self):
        """
        Acción para ejecutar consolidación manual desde la interfaz
        """
        self.ensure_one()
        
        try:
            resultado = self.ejecutar_consolidacion()
            
            if resultado:
                message = f"""
                ✅ Consolidación ejecutada exitosamente
                
                📊 Resumen:
                • Contador automático: {self.registros_contador_automatico} registros
                • PrintTracker: {self.registros_printtracker} registros  
                • Consolidadas: {self.lecturas_consolidadas} lecturas
                • Conflictos resueltos: {self.conflictos_resueltos}
                • Equipos actualizados: {self.equipos_actualizados}
                • Errores: {self.errores_encontrados}
                """
                message_type = 'success'
            else:
                message = f"❌ Error en consolidación. Revisar log para detalles."
                message_type = 'danger'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Consolidación PrintTracker',
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
                    'message': f'❌ Error ejecutando consolidación: {str(e)}',
                    'type': 'danger'
                }
            }

    @api.model
    def obtener_estadisticas_consolidacion(self, dias=7):
        """
        Obtiene estadísticas de consolidación de los últimos N días
        """
        try:
            fecha_inicio = date.today() - timedelta(days=dias)
            
            # Estadísticas de lecturas diarias
            lecturas = self.env['printtracker.daily.reading'].search([
                ('fecha', '>=', fecha_inicio)
            ])
            
            stats = {
                'periodo': f"{fecha_inicio} a {date.today()}",
                'total_lecturas': len(lecturas),
                'lecturas_por_fuente': {
                    'correo': len(lecturas.filtered(lambda l: l.fuente_origen == 'correo')),
                    'printtracker': len(lecturas.filtered(lambda l: l.fuente_origen == 'printtracker')),
                    'consolidado': len(lecturas.filtered(lambda l: l.fuente_origen == 'consolidado')),
                    'manual': len(lecturas.filtered(lambda l: l.fuente_origen == 'manual'))
                },
                'conflictos_detectados': len(lecturas.filtered('conflicto_detectado')),
                'lecturas_aplicadas': len(lecturas.filtered('aplicado_a_equipo')),
                'series_unicas': len(set(lecturas.mapped('serie'))),
                'equipos_con_actividad': len(set(lecturas.mapped('equipo_id')))
            }
            
            return stats
            
        except Exception as e:
            _logger.error(f"❌ Error obteniendo estadísticas: {e}")
            return {}

    def action_view_log(self):
        """
        Acción para ver el log detallado en una ventana
        """
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Log de Consolidación',
            'res_model': 'printtracker.consolidator',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'form_view_initial_mode': 'readonly'
            }
        }