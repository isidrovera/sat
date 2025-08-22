from odoo import models, fields, api
import logging
from datetime import datetime, timedelta, date

_logger = logging.getLogger(__name__)


class PrintTrackerConsolidator(models.TransientModel):
    _name = 'printtracker.consolidator'
    _description = 'Consolidador de Datos PrintTracker'

    # ========================================
    # CAMPOS DEL MODELO
    # ========================================
    
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

    # ========================================
    # PARTE 1: MÉTODOS PRINCIPALES Y AUTOMATIZACIÓN
    # ========================================

    @api.model
    def ejecutar_consolidacion_automatica(self):
        """
        PARTE 1 - CORREGIDO: Método ejecutado por el cron cada 2 horas
        Consolida datos de las últimas 24 horas
        """
        try:
            _logger.info("🔄 ===== INICIANDO CONSOLIDACIÓN AUTOMÁTICA =====")
            _logger.info(f"🕐 Hora de ejecución: {datetime.now()}")
            
            # Configurar fechas de procesamiento (últimas 24 horas)
            fecha_fin = date.today()
            fecha_inicio = fecha_fin - timedelta(days=1)
            
            _logger.info(f"📅 Período automático: {fecha_inicio} a {fecha_fin}")
            
            # Crear registro de consolidación temporal
            consolidador = self.create({
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'forzar_reproceso': False  # Automático no fuerza reproceso
            })
            
            _logger.info(f"🆕 Consolidador creado: ID={consolidador.id}")
            
            # Ejecutar consolidación
            _logger.info(f"🚀 Iniciando ejecución de consolidación...")
            resultado = consolidador.ejecutar_consolidacion()
            
            if resultado:
                _logger.info(f"✅ ===== CONSOLIDACIÓN AUTOMÁTICA EXITOSA =====")
                _logger.info(f"📊 Contador automático: {consolidador.registros_contador_automatico} registros")
                _logger.info(f"📊 PrintTracker: {consolidador.registros_printtracker} registros")
                _logger.info(f"📊 Consolidadas: {consolidador.lecturas_consolidadas} lecturas")
                _logger.info(f"📊 Conflictos resueltos: {consolidador.conflictos_resueltos}")
                _logger.info(f"📊 Equipos actualizados: {consolidador.equipos_actualizados}")
                _logger.info(f"📊 Errores: {consolidador.errores_encontrados}")
                
                # Log de resumen en una línea para fácil búsqueda
                _logger.info(f"📈 RESUMEN: C={consolidador.registros_contador_automatico}, "
                           f"PT={consolidador.registros_printtracker}, "
                           f"CON={consolidador.lecturas_consolidadas}, "
                           f"CONF={consolidador.conflictos_resueltos}, "
                           f"EQ={consolidador.equipos_actualizados}, "
                           f"ERR={consolidador.errores_encontrados}")
            else:
                _logger.error(f"❌ ===== ERROR EN CONSOLIDACIÓN AUTOMÁTICA =====")
                _logger.error(f"📊 Errores: {consolidador.errores_encontrados}")
                _logger.error(f"📋 Log: {consolidador.log_procesamiento}")
            
            return resultado
            
        except Exception as e:
            _logger.error(f"❌ ERROR CRÍTICO en consolidación automática: {str(e)}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return False

    def ejecutar_consolidacion(self):
        """
        PARTE 1 - CORREGIDO: Ejecuta el proceso completo de consolidación
        """
        try:
            inicio_tiempo = datetime.now()
            log_lines = []
            
            _logger.info(f"🔄 ===== INICIANDO PROCESO DE CONSOLIDACIÓN =====")
            _logger.info(f"🆔 Consolidador ID: {self.id}")
            _logger.info(f"📅 Período: {self.fecha_inicio} a {self.fecha_fin}")
            _logger.info(f"🎯 Serie: {self.serie_especifica or 'TODAS'}")
            _logger.info(f"🔄 Forzar reproceso: {'SÍ' if self.forzar_reproceso else 'NO'}")
            
            log_lines.append(f"🔄 === INICIANDO CONSOLIDACIÓN ===")
            log_lines.append(f"📅 Período: {self.fecha_inicio} a {self.fecha_fin}")
            log_lines.append(f"🎯 Serie: {self.serie_especifica or 'TODAS LAS SERIES'}")
            log_lines.append(f"🔄 Forzar reproceso: {'SÍ' if self.forzar_reproceso else 'NO'}")
            log_lines.append(f"🕐 Inicio: {inicio_tiempo}")
            log_lines.append("")
            
            # Inicializar contadores
            self.registros_contador_automatico = 0
            self.registros_printtracker = 0
            self.lecturas_consolidadas = 0
            self.conflictos_resueltos = 0
            self.equipos_actualizados = 0
            self.errores_encontrados = 0
            
            # PASO 1: Procesar registros de contador.automatico
            _logger.info("📧 === INICIANDO PASO 1: CONTADOR.AUTOMATICO ===")
            log_lines.append("📧 === PASO 1: PROCESANDO CONTADOR.AUTOMATICO ===")
            
            resultado_contador = self._procesar_contador_automatico()
            log_lines.extend(resultado_contador['log'])
            self.registros_contador_automatico = resultado_contador['procesados']
            self.errores_encontrados += resultado_contador.get('errores', 0)
            
            _logger.info(f"📧 Paso 1 completado: {self.registros_contador_automatico} procesados")
            
            # PASO 2: Procesar registros de PrintTracker
            _logger.info("🔄 === INICIANDO PASO 2: PRINTTRACKER ===")
            log_lines.append("🔄 === PASO 2: PROCESANDO PRINTTRACKER ===")
            
            resultado_pt = self._procesar_printtracker_meters()
            log_lines.extend(resultado_pt['log'])
            self.registros_printtracker = resultado_pt['procesados']
            self.errores_encontrados += resultado_pt.get('errores', 0)
            
            _logger.info(f"🔄 Paso 2 completado: {self.registros_printtracker} procesados")
            
            # PASO 3: Consolidar lecturas con conflictos
            _logger.info("⚖️ === INICIANDO PASO 3: CONSOLIDACIÓN ===")
            log_lines.append("⚖️ === PASO 3: CONSOLIDANDO Y RESOLVIENDO CONFLICTOS ===")
            
            resultado_consolidacion = self._consolidar_lecturas_periodo()
            log_lines.extend(resultado_consolidacion['log'])
            self.lecturas_consolidadas = resultado_consolidacion['consolidadas']
            self.conflictos_resueltos = resultado_consolidacion['conflictos']
            self.errores_encontrados += resultado_consolidacion.get('errores', 0)
            
            _logger.info(f"⚖️ Paso 3 completado: {self.lecturas_consolidadas} consolidadas, {self.conflictos_resueltos} conflictos")
            
            # PASO 4: Aplicar a equipos
            _logger.info("💾 === INICIANDO PASO 4: APLICACIÓN A EQUIPOS ===")
            log_lines.append("💾 === PASO 4: APLICANDO A EQUIPOS ===")
            
            resultado_equipos = self._aplicar_a_equipos()
            log_lines.extend(resultado_equipos['log'])
            self.equipos_actualizados = resultado_equipos['actualizados']
            self.errores_encontrados += resultado_equipos.get('errores', 0)
            
            _logger.info(f"💾 Paso 4 completado: {self.equipos_actualizados} equipos actualizados")
            
            # PASO 5: Estadísticas finales
            _logger.info("📊 === GENERANDO ESTADÍSTICAS FINALES ===")
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
            
            # Determinar éxito/fracaso
            exito = self.errores_encontrados == 0
            if exito:
                log_lines.append("✅ === CONSOLIDACIÓN COMPLETADA EXITOSAMENTE ===")
                _logger.info(f"✅ ===== CONSOLIDACIÓN COMPLETADA EXITOSAMENTE =====")
            else:
                log_lines.append(f"⚠️ === CONSOLIDACIÓN COMPLETADA CON {self.errores_encontrados} ERRORES ===")
                _logger.warning(f"⚠️ ===== CONSOLIDACIÓN COMPLETADA CON {self.errores_encontrados} ERRORES =====")
            
            # Guardar log completo
            self.log_procesamiento = "\n".join(log_lines)
            
            _logger.info(f"📊 Resumen final: C={self.registros_contador_automatico}, "
                        f"PT={self.registros_printtracker}, CON={self.lecturas_consolidadas}, "
                        f"CONF={self.conflictos_resueltos}, EQ={self.equipos_actualizados}, "
                        f"ERR={self.errores_encontrados}, T={tiempo_total:.1f}s")
            
            return exito
            
        except Exception as e:
            error_msg = f"❌ ERROR CRÍTICO en consolidación: {str(e)}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            
            # Intentar guardar error en log
            try:
                current_log = self.log_procesamiento or ""
                self.log_procesamiento = current_log + f"\n{error_msg}\n{traceback.format_exc()}"
                self.errores_encontrados = (self.errores_encontrados or 0) + 1
            except:
                _logger.error("❌ No se pudo guardar error en log del consolidador")
            
            return False

    def action_ejecutar_manual(self):
        """
        PARTE 1 - MEJORADO: Acción para ejecutar consolidación manual desde la interfaz
        """
        self.ensure_one()
        
        try:
            _logger.info(f"✋ ===== CONSOLIDACIÓN MANUAL SOLICITADA =====")
            _logger.info(f"🆔 Consolidador ID: {self.id}")
            _logger.info(f"📅 Período: {self.fecha_inicio} a {self.fecha_fin}")
            _logger.info(f"🎯 Serie: {self.serie_especifica or 'TODAS'}")
            _logger.info(f"🔄 Forzar: {self.forzar_reproceso}")
            
            resultado = self.ejecutar_consolidacion()
            
            if resultado:
                message = f"""✅ CONSOLIDACIÓN EJECUTADA EXITOSAMENTE

📊 RESUMEN DE RESULTADOS:
• Período: {self.fecha_inicio} a {self.fecha_fin}
• Serie: {self.serie_especifica or 'TODAS'}

📧 Contador automático: {self.registros_contador_automatico} registros
🔄 PrintTracker: {self.registros_printtracker} registros  
⚖️ Consolidadas: {self.lecturas_consolidadas} lecturas
⚠️ Conflictos resueltos: {self.conflictos_resueltos}
💾 Equipos actualizados: {self.equipos_actualizados}
❌ Errores: {self.errores_encontrados}

Ver log completo para detalles."""
                
                message_type = 'success'
                _logger.info(f"✅ Consolidación manual exitosa")
            else:
                message = f"""❌ CONSOLIDACIÓN COMPLETADA CON ERRORES

📊 RESUMEN:
• Errores encontrados: {self.errores_encontrados}
• Procesados parcialmente: {self.registros_contador_automatico + self.registros_printtracker}

⚠️ Revisar log completo para detalles de errores."""
                
                message_type = 'warning'
                _logger.warning(f"⚠️ Consolidación manual con errores")
            
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
            error_msg = f'❌ ERROR EJECUTANDO CONSOLIDACIÓN: {str(e)}'
            _logger.error(error_msg)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error Consolidación',
                    'message': error_msg,
                    'type': 'danger',
                    'sticky': True
                }
            }

    def action_view_log(self):
        """
        PARTE 1 - SIN CAMBIOS: Acción para ver el log detallado en una ventana
        """
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Log de Consolidación - {self.fecha_inicio} a {self.fecha_fin}',
            'res_model': 'printtracker.consolidator',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'form_view_initial_mode': 'readonly'
            }
        }

    # ========================================
    # PARTE 2: PROCESAMIENTO DE CONTADOR AUTOMÁTICO Y PRINTTRACKER
    # ========================================

    def _procesar_contador_automatico(self):
        """
        PARTE 2 - CORREGIDO: Procesa registros nuevos de contador.automatico
        NUEVA LÓGICA: Usa métodos crear_desde_* sin actualizaciones automáticas
        """
        try:
            log_lines = []
            procesados = 0
            errores = 0
            
            _logger.info("📧 ===== INICIANDO PROCESAMIENTO CONTADOR AUTOMÁTICO =====")
            
            # Construir dominio de búsqueda
            domain = [
                ('estado', '=', 'procesado'),
                ('fecha_procesamiento', '>=', datetime.combine(self.fecha_inicio, datetime.min.time())),
                ('fecha_procesamiento', '<=', datetime.combine(self.fecha_fin, datetime.max.time())),
                ('serie_detectada', '!=', False)
            ]
            
            if self.serie_especifica:
                domain.append(('serie_detectada', '=', self.serie_especifica))
                _logger.info(f"📧 Filtrando por serie específica: {self.serie_especifica}")
            
            # Buscar registros de contador automático
            _logger.info(f"📧 Buscando registros contador automático en período...")
            registros_contador = self.env['contador.automatico'].search(domain)
            
            _logger.info(f"📧 Encontrados {len(registros_contador)} registros de contador automático")
            log_lines.append(f"📧 Encontrados {len(registros_contador)} registros de contador automático")
            
            if not registros_contador:
                log_lines.append("ℹ️ No hay registros de contador automático para procesar")
                _logger.info("ℹ️ No hay registros de contador automático para procesar")
                return {
                    'procesados': 0,
                    'errores': 0,
                    'log': log_lines
                }
            
            # Procesar cada registro
            for i, registro in enumerate(registros_contador, 1):
                try:
                    _logger.info(f"📧 --- Procesando registro {i}/{len(registros_contador)}: {registro.serie_detectada} ---")
                    
                    fecha_lectura = registro.fecha_procesamiento.date() if registro.fecha_procesamiento else date.today()
                    
                    _logger.info(f"📧 Registro ID: {registro.id}")
                    _logger.info(f"📧 Serie: {registro.serie_detectada}")
                    _logger.info(f"📧 Fecha lectura: {fecha_lectura}")
                    _logger.info(f"📧 Contadores: BN={registro.contador_bn_detectado}, Color={registro.contador_color_detectado}, Scan={registro.contador_scan_detectado}")
                    
                    # NUEVA LÓGICA: Buscar CUALQUIER lectura existente para esta fecha/serie
                    existing_readings = self.env['printtracker.daily.reading'].search([
                        ('fecha', '=', fecha_lectura),
                        ('serie', '=', registro.serie_detectada)
                    ])
                    
                    _logger.info(f"📧 Lecturas existentes encontradas: {len(existing_readings)}")
                    
                    if existing_readings:
                        for j, reading in enumerate(existing_readings):
                            _logger.info(f"📧 Lectura existente {j+1}: ID={reading.id}, Fuente={reading.fuente_origen}, Estado={reading.estado}")
                        
                        # CASO 1: Ya existe(n) lectura(s) para esta fecha/serie
                        if not self.forzar_reproceso:
                            _logger.info(f"📧 Saltando {registro.serie_detectada} - {fecha_lectura} (ya existe, no forzado)")
                            log_lines.append(f"⏭️ Ya existe lectura para {registro.serie_detectada} - {fecha_lectura}")
                            continue
                        else:
                            # CASO 2: Forzar reproceso - buscar lectura de correo para actualizar
                            lectura_correo = existing_readings.filtered(lambda l: l.fuente_origen == 'correo')
                            
                            if lectura_correo:
                                _logger.info(f"📧 Forzando actualización de lectura de correo existente")
                                lectura_correo = lectura_correo[0]  # Tomar la primera si hay múltiples
                                
                                lectura_correo.write({
                                    'contador_bn': registro.contador_bn_detectado or 0,
                                    'contador_color': registro.contador_color_detectado or 0,
                                    'contador_scan': registro.contador_scan_detectado or 0,
                                    'contador_automatico_id': registro.id,
                                    'fecha_procesamiento': fields.Datetime.now()
                                })
                                
                                log_lines.append(f"📝 FORZADO: Actualizada lectura correo {registro.serie_detectada} - {fecha_lectura}")
                                _logger.info(f"✅ Actualización forzada completada para {registro.serie_detectada}")
                                procesados += 1
                                continue
                            else:
                                _logger.info(f"📧 No hay lectura de correo para forzar, intentando crear nueva")
                                # Continuar al CASO 3 (crear nueva)
                    
                    # CASO 3: No existe lectura O no hay lectura de correo para forzar - crear nueva
                    _logger.info(f"📧 Creando nueva lectura desde contador automático")
                    
                    nueva_lectura = self.env['printtracker.daily.reading'].crear_desde_contador_automatico(registro)
                    
                    if nueva_lectura:
                        _logger.info(f"✅ Lectura creada exitosamente: ID={nueva_lectura.id}")
                        log_lines.append(f"✅ Creada desde correo: {registro.serie_detectada} - {fecha_lectura}")
                        procesados += 1
                    else:
                        _logger.error(f"❌ Error creando lectura para {registro.serie_detectada}")
                        log_lines.append(f"❌ Error creando lectura para {registro.serie_detectada} - {fecha_lectura}")
                        errores += 1
                    
                except Exception as e:
                    error_msg = f"❌ Error procesando registro contador {registro.serie_detectada}: {str(e)}"
                    _logger.error(error_msg)
                    import traceback
                    _logger.error(f"❌ Traceback: {traceback.format_exc()}")
                    
                    log_lines.append(f"❌ Error procesando {registro.serie_detectada}: {str(e)}")
                    errores += 1
            
            # Resumen final
            _logger.info(f"📧 ===== PROCESAMIENTO CONTADOR AUTOMÁTICO COMPLETADO =====")
            _logger.info(f"📧 Total registros: {len(registros_contador)}")
            _logger.info(f"📧 Procesados exitosamente: {procesados}")
            _logger.info(f"📧 Errores: {errores}")
            
            log_lines.append(f"✅ Procesamiento contador automático completado: {procesados}/{len(registros_contador)} exitosos, {errores} errores")
            
            return {
                'procesados': procesados,
                'errores': errores,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ ERROR CRÍTICO procesando contador automático: {str(e)}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            
            return {
                'procesados': 0,
                'errores': 1,
                'log': [error_msg]
            }

    def _procesar_printtracker_meters(self):
        """
        PARTE 2 - CORREGIDO: Procesa registros nuevos de printtracker.meter
        NUEVA LÓGICA: Usa métodos crear_desde_* sin actualizaciones automáticas
        """
        try:
            log_lines = []
            procesados = 0
            errores = 0
            
            _logger.info("🔄 ===== INICIANDO PROCESAMIENTO PRINTTRACKER =====")
            
            # Construir dominio de búsqueda
            domain = [
                ('reading_date', '>=', datetime.combine(self.fecha_inicio, datetime.min.time())),
                ('reading_date', '<=', datetime.combine(self.fecha_fin, datetime.max.time())),
                ('device_id', '!=', False),
                ('device_id.serie', '!=', False)
            ]
            
            if self.serie_especifica:
                domain.append(('device_id.serie', '=', self.serie_especifica))
                _logger.info(f"🔄 Filtrando por serie específica: {self.serie_especifica}")
            
            # Buscar registros de PrintTracker
            _logger.info(f"🔄 Buscando registros PrintTracker en período...")
            meters = self.env['printtracker.meter'].search(domain)
            
            _logger.info(f"🔄 Encontrados {len(meters)} registros de PrintTracker")
            log_lines.append(f"🔄 Encontrados {len(meters)} registros de PrintTracker")
            
            if not meters:
                log_lines.append("ℹ️ No hay registros de PrintTracker para procesar")
                _logger.info("ℹ️ No hay registros de PrintTracker para procesar")
                return {
                    'procesados': 0,
                    'errores': 0,
                    'log': log_lines
                }
            
            # Procesar cada registro
            for i, meter in enumerate(meters, 1):
                try:
                    _logger.info(f"🔄 --- Procesando meter {i}/{len(meters)}: {meter.device_id.serie} ---")
                    
                    fecha_lectura = meter.reading_date.date() if meter.reading_date else date.today()
                    serie = meter.device_id.serie
                    
                    _logger.info(f"🔄 Meter ID: {meter.id}")
                    _logger.info(f"🔄 Serie: {serie}")
                    _logger.info(f"🔄 Fecha lectura: {fecha_lectura}")
                    _logger.info(f"🔄 Contadores: BN={meter.black_pages_life}, Color={meter.color_pages_life}, Scan={meter.scan_pages}, Copy={meter.copy_pages}, Fax={meter.fax_pages}")
                    
                    # NUEVA LÓGICA: Buscar CUALQUIER lectura existente para esta fecha/serie
                    existing_readings = self.env['printtracker.daily.reading'].search([
                        ('fecha', '=', fecha_lectura),
                        ('serie', '=', serie)
                    ])
                    
                    _logger.info(f"🔄 Lecturas existentes encontradas: {len(existing_readings)}")
                    
                    if existing_readings:
                        for j, reading in enumerate(existing_readings):
                            _logger.info(f"🔄 Lectura existente {j+1}: ID={reading.id}, Fuente={reading.fuente_origen}, Estado={reading.estado}")
                        
                        # CASO 1: Ya existe(n) lectura(s) para esta fecha/serie
                        if not self.forzar_reproceso:
                            _logger.info(f"🔄 Saltando {serie} - {fecha_lectura} (ya existe, no forzado)")
                            log_lines.append(f"⏭️ Ya existe lectura para {serie} - {fecha_lectura}")
                            continue
                        else:
                            # CASO 2: Forzar reproceso - buscar lectura de PrintTracker para actualizar
                            lectura_pt = existing_readings.filtered(lambda l: l.fuente_origen == 'printtracker')
                            
                            if lectura_pt:
                                _logger.info(f"🔄 Forzando actualización de lectura PrintTracker existente")
                                lectura_pt = lectura_pt[0]  # Tomar la primera si hay múltiples
                                
                                lectura_pt.write({
                                    'contador_bn': meter.black_pages_life or 0,
                                    'contador_color': meter.color_pages_life or 0,
                                    'contador_scan': meter.scan_pages or 0,
                                    'contador_copy': meter.copy_pages or 0,
                                    'contador_fax': meter.fax_pages or 0,
                                    'printtracker_meter_id': meter.id,
                                    'fecha_procesamiento': fields.Datetime.now()
                                })
                                
                                log_lines.append(f"📝 FORZADO: Actualizada lectura PrintTracker {serie} - {fecha_lectura}")
                                _logger.info(f"✅ Actualización forzada completada para {serie}")
                                procesados += 1
                                continue
                            else:
                                _logger.info(f"🔄 No hay lectura de PrintTracker para forzar, intentando crear nueva")
                                # Continuar al CASO 3 (crear nueva)
                    
                    # CASO 3: No existe lectura O no hay lectura de PrintTracker para forzar - crear nueva
                    _logger.info(f"🔄 Creando nueva lectura desde PrintTracker")
                    
                    nueva_lectura = self.env['printtracker.daily.reading'].crear_desde_printtracker(meter)
                    
                    if nueva_lectura:
                        _logger.info(f"✅ Lectura creada exitosamente: ID={nueva_lectura.id}")
                        log_lines.append(f"✅ Creada desde PrintTracker: {serie} - {fecha_lectura}")
                        procesados += 1
                    else:
                        _logger.error(f"❌ Error creando lectura para {serie}")
                        log_lines.append(f"❌ Error creando lectura para {serie} - {fecha_lectura}")
                        errores += 1
                    
                except Exception as e:
                    serie_error = getattr(getattr(meter, 'device_id', None), 'serie', 'DESCONOCIDA')
                    error_msg = f"❌ Error procesando meter {serie_error}: {str(e)}"
                    _logger.error(error_msg)
                    import traceback
                    _logger.error(f"❌ Traceback: {traceback.format_exc()}")
                    
                    log_lines.append(f"❌ Error procesando {serie_error}: {str(e)}")
                    errores += 1
            
            # Resumen final
            _logger.info(f"🔄 ===== PROCESAMIENTO PRINTTRACKER COMPLETADO =====")
            _logger.info(f"🔄 Total registros: {len(meters)}")
            _logger.info(f"🔄 Procesados exitosamente: {procesados}")
            _logger.info(f"🔄 Errores: {errores}")
            
            log_lines.append(f"✅ Procesamiento PrintTracker completado: {procesados}/{len(meters)} exitosos, {errores} errores")
            
            return {
                'procesados': procesados,
                'errores': errores,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ ERROR CRÍTICO procesando PrintTracker: {str(e)}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            
            return {
                'procesados': 0,
                'errores': 1,
                'log': [error_msg]
            }

    def _verificar_registros_duplicados(self):
        """
        PARTE 2 - NUEVO: Verifica y reporta registros duplicados en el período
        """
        try:
            log_lines = []
            
            _logger.info("🔍 ===== VERIFICANDO REGISTROS DUPLICADOS =====")
            
            # Buscar lecturas del período
            domain = [
                ('fecha', '>=', self.fecha_inicio),
                ('fecha', '<=', self.fecha_fin)
            ]
            
            if self.serie_especifica:
                domain.append(('serie', '=', self.serie_especifica))
            
            lecturas = self.env['printtracker.daily.reading'].search(domain)
            
            # Agrupar por fecha/serie
            grupos = {}
            for lectura in lecturas:
                key = (lectura.fecha, lectura.serie)
                if key not in grupos:
                    grupos[key] = []
                grupos[key].append(lectura)
            
            # Identificar duplicados
            duplicados = {k: v for k, v in grupos.items() if len(v) > 1}
            
            _logger.info(f"🔍 Total grupos fecha/serie: {len(grupos)}")
            _logger.info(f"🔍 Grupos con duplicados: {len(duplicados)}")
            
            log_lines.append(f"🔍 Verificación de duplicados:")
            log_lines.append(f"• Total grupos fecha/serie: {len(grupos)}")
            log_lines.append(f"• Grupos con duplicados: {len(duplicados)}")
            
            if duplicados:
                log_lines.append(f"⚠️ DUPLICADOS ENCONTRADOS:")
                for (fecha, serie), lecturas_grupo in list(duplicados.items())[:10]:  # Mostrar solo primeros 10
                    fuentes = [l.fuente_origen for l in lecturas_grupo]
                    log_lines.append(f"  • {serie} - {fecha}: {fuentes}")
                    _logger.warning(f"🔍 Duplicado: {serie} - {fecha}: {fuentes}")
                
                if len(duplicados) > 10:
                    log_lines.append(f"  ... y {len(duplicados) - 10} más")
            else:
                log_lines.append("✅ No se encontraron duplicados")
                _logger.info("✅ No se encontraron duplicados")
            
            return {
                'total_grupos': len(grupos),
                'duplicados': len(duplicados),
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error verificando duplicados: {str(e)}"
            _logger.error(error_msg)
            
            return {
                'total_grupos': 0,
                'duplicados': 0,
                'log': [error_msg]
            }

    # ========================================
    # PARTE 3: CONSOLIDACIÓN Y APLICACIÓN A EQUIPOS
    # ========================================

    def _consolidar_lecturas_periodo(self):
        """
        PARTE 3 - CORREGIDO: Consolida lecturas del período aplicando reglas de conflicto
        USA los métodos corregidos de consolidación
        """
        try:
            log_lines = []
            consolidadas = 0
            conflictos = 0
            errores = 0
            ya_consolidadas = 0
            aplicadas_directas = 0
            sin_datos = 0
            
            _logger.info("⚖️ ===== INICIANDO CONSOLIDACIÓN DE LECTURAS =====")
            _logger.info(f"⚖️ Período: {self.fecha_inicio} a {self.fecha_fin}")
            
            # Iterar por cada fecha del período
            fecha_actual = self.fecha_inicio
            total_dias = (self.fecha_fin - self.fecha_inicio).days + 1
            
            _logger.info(f"⚖️ Total días a procesar: {total_dias}")
            log_lines.append(f"⚖️ Consolidando período: {self.fecha_inicio} a {self.fecha_fin} ({total_dias} días)")
            
            while fecha_actual <= self.fecha_fin:
                try:
                    _logger.info(f"⚖️ --- Procesando fecha: {fecha_actual} ---")
                    
                    # Obtener series únicas para esta fecha
                    domain = [('fecha', '=', fecha_actual)]
                    if self.serie_especifica:
                        domain.append(('serie', '=', self.serie_especifica))
                    
                    lecturas_fecha = self.env['printtracker.daily.reading'].search(domain)
                    series_fecha = list(set(lecturas_fecha.mapped('serie')))
                    
                    _logger.info(f"⚖️ Fecha {fecha_actual}: {len(lecturas_fecha)} lecturas, {len(series_fecha)} series únicas")
                    
                    if not series_fecha:
                        _logger.info(f"⚖️ No hay series para procesar en {fecha_actual}")
                        fecha_actual += timedelta(days=1)
                        continue
                    
                    log_lines.append(f"📅 {fecha_actual}: {len(series_fecha)} series")
                    
                    # Procesar cada serie en esta fecha
                    for i, serie in enumerate(series_fecha, 1):
                        try:
                            _logger.info(f"⚖️ Procesando serie {i}/{len(series_fecha)}: {serie}")
                            
                            # Llamar al método de consolidación corregido
                            resultado = self.env['printtracker.daily.reading'].consolidar_lecturas(
                                fecha_objetivo=fecha_actual,
                                serie_objetivo=serie
                            )
                            
                            if resultado:
                                # Procesar resultados según el nuevo formato
                                if resultado.get('consolidadas', 0) > 0:
                                    consolidadas += resultado['consolidadas']
                                    _logger.info(f"✅ Serie {serie}: CONSOLIDADA")
                                
                                if resultado.get('conflictos', 0) > 0:
                                    conflictos += resultado['conflictos']
                                    log_lines.append(f"⚠️ Conflicto resuelto: {serie} - {fecha_actual}")
                                    _logger.warning(f"⚠️ Serie {serie}: CONFLICTO RESUELTO")
                                
                                if resultado.get('ya_consolidadas', 0) > 0:
                                    ya_consolidadas += resultado['ya_consolidadas']
                                    _logger.info(f"ℹ️ Serie {serie}: YA CONSOLIDADA")
                                
                                if resultado.get('aplicadas_directas', 0) > 0:
                                    aplicadas_directas += resultado['aplicadas_directas']
                                    _logger.info(f"➡️ Serie {serie}: APLICADA DIRECTA")
                                
                                if resultado.get('sin_datos', 0) > 0:
                                    sin_datos += resultado['sin_datos']
                                    _logger.info(f"➖ Serie {serie}: SIN DATOS")
                                
                                if resultado.get('errores', 0) > 0:
                                    errores += resultado['errores']
                                    log_lines.append(f"❌ Error consolidando: {serie} - {fecha_actual}")
                                    _logger.error(f"❌ Serie {serie}: ERROR")
                            else:
                                _logger.error(f"❌ Error en consolidación de {serie} - {fecha_actual}: resultado nulo")
                                log_lines.append(f"❌ Error consolidando: {serie} - {fecha_actual}")
                                errores += 1
                        
                        except Exception as e:
                            error_msg = f"❌ Error consolidando serie {serie} en {fecha_actual}: {str(e)}"
                            _logger.error(error_msg)
                            import traceback
                            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
                            
                            log_lines.append(f"❌ Error: {serie} - {fecha_actual}")
                            errores += 1
                    
                except Exception as e:
                    error_msg = f"❌ Error procesando fecha {fecha_actual}: {str(e)}"
                    _logger.error(error_msg)
                    log_lines.append(error_msg)
                    errores += 1
                
                fecha_actual += timedelta(days=1)
            
            # Resumen final
            _logger.info(f"⚖️ ===== CONSOLIDACIÓN DE LECTURAS COMPLETADA =====")
            _logger.info(f"⚖️ Consolidadas: {consolidadas}")
            _logger.info(f"⚖️ Conflictos: {conflictos}")
            _logger.info(f"⚖️ Ya consolidadas: {ya_consolidadas}")
            _logger.info(f"⚖️ Aplicadas directas: {aplicadas_directas}")
            _logger.info(f"⚖️ Sin datos: {sin_datos}")
            _logger.info(f"⚖️ Errores: {errores}")
            
            log_lines.append(f"✅ Consolidación completada:")
            log_lines.append(f"  • Consolidadas: {consolidadas}")
            log_lines.append(f"  • Conflictos resueltos: {conflictos}")
            log_lines.append(f"  • Ya consolidadas: {ya_consolidadas}")
            log_lines.append(f"  • Aplicadas directas: {aplicadas_directas}")
            log_lines.append(f"  • Sin datos: {sin_datos}")
            log_lines.append(f"  • Errores: {errores}")
            
            return {
                'consolidadas': consolidadas,
                'conflictos': conflictos,
                'errores': errores,
                'ya_consolidadas': ya_consolidadas,
                'aplicadas_directas': aplicadas_directas,
                'sin_datos': sin_datos,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ ERROR CRÍTICO en consolidación de lecturas: {str(e)}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            
            return {
                'consolidadas': 0,
                'conflictos': 0,
                'errores': 1,
                'log': [error_msg]
            }

    def _aplicar_a_equipos(self):
        """
        PARTE 3 - CORREGIDO: Aplica lecturas consolidadas pendientes a los equipos
        USA el método _aplicar_lectura_a_equipo corregido
        """
        try:
            log_lines = []
            actualizados = 0
            errores = 0
            ya_aplicados = 0
            sin_equipo = 0
            
            _logger.info("💾 ===== INICIANDO APLICACIÓN A EQUIPOS =====")
            _logger.info(f"💾 Período: {self.fecha_inicio} a {self.fecha_fin}")
            
            # Buscar lecturas que necesitan ser aplicadas
            domain = [
                ('fecha', '>=', self.fecha_inicio),
                ('fecha', '<=', self.fecha_fin),
                ('estado', 'in', ['validado', 'borrador'])  # Solo validadas o borradores, no aplicadas
            ]
            
            if self.serie_especifica:
                domain.append(('serie', '=', self.serie_especifica))
            
            lecturas_pendientes = self.env['printtracker.daily.reading'].search(domain)
            
            _logger.info(f"💾 Lecturas pendientes encontradas: {len(lecturas_pendientes)}")
            log_lines.append(f"💾 Encontradas {len(lecturas_pendientes)} lecturas pendientes de aplicar")
            
            # Verificar también lecturas ya aplicadas para estadísticas
            domain_aplicadas = domain.copy()
            domain_aplicadas[2] = ('estado', '=', 'aplicado')
            lecturas_aplicadas = self.env['printtracker.daily.reading'].search(domain_aplicadas)
            ya_aplicados = len(lecturas_aplicadas)
            
            _logger.info(f"💾 Lecturas ya aplicadas en período: {ya_aplicados}")
            log_lines.append(f"💾 Ya aplicadas en período: {ya_aplicados}")
            
            if not lecturas_pendientes:
                log_lines.append("ℹ️ No hay lecturas pendientes de aplicar")
                _logger.info("ℹ️ No hay lecturas pendientes de aplicar")
                
                return {
                    'actualizados': 0,
                    'errores': 0,
                    'ya_aplicados': ya_aplicados,
                    'sin_equipo': 0,
                    'log': log_lines
                }
            
            # Procesar cada lectura pendiente
            for i, lectura in enumerate(lecturas_pendientes, 1):
                try:
                    _logger.info(f"💾 --- Aplicando lectura {i}/{len(lecturas_pendientes)}: {lectura.serie} ---")
                    _logger.info(f"💾 Lectura ID: {lectura.id}")
                    _logger.info(f"💾 Fecha: {lectura.fecha}")
                    _logger.info(f"💾 Fuente: {lectura.fuente_origen}")
                    _logger.info(f"💾 Estado actual: {lectura.estado}")
                    _logger.info(f"💾 Ya aplicado: {lectura.aplicado_a_equipo}")
                    
                    # Verificar si tiene equipo
                    if not lectura.equipo_id:
                        _logger.warning(f"💾 Sin equipo: {lectura.serie}")
                        log_lines.append(f"⚠️ Sin equipo: {lectura.serie} - {lectura.fecha}")
                        sin_equipo += 1
                        continue
                    
                    # Verificar si ya fue aplicada (doble verificación)
                    if lectura.aplicado_a_equipo:
                        _logger.info(f"💾 Ya aplicada: {lectura.serie}")
                        ya_aplicados += 1
                        continue
                    
                    # Aplicar al equipo usando el método corregido
                    _logger.info(f"💾 Llamando _aplicar_lectura_a_equipo...")
                    resultado_aplicacion = lectura._aplicar_lectura_a_equipo(lectura)
                    
                    if resultado_aplicacion:
                        _logger.info(f"✅ Aplicada exitosamente: {lectura.serie}")
                        log_lines.append(f"✅ Aplicado: {lectura.serie} - {lectura.fecha} → {lectura.equipo_id.name}")
                        actualizados += 1
                    else:
                        _logger.error(f"❌ Error aplicando: {lectura.serie}")
                        error_detail = lectura.mensaje_error or "Error desconocido"
                        log_lines.append(f"❌ Error aplicando: {lectura.serie} - {lectura.fecha} ({error_detail})")
                        errores += 1
                        
                except Exception as e:
                    error_msg = f"❌ Error aplicando lectura {lectura.serie}: {str(e)}"
                    _logger.error(error_msg)
                    import traceback
                    _logger.error(f"❌ Traceback: {traceback.format_exc()}")
                    
                    log_lines.append(f"❌ Error aplicando: {lectura.serie} - {lectura.fecha}")
                    errores += 1
            
            # Resumen final
            _logger.info(f"💾 ===== APLICACIÓN A EQUIPOS COMPLETADA =====")
            _logger.info(f"💾 Total pendientes: {len(lecturas_pendientes)}")
            _logger.info(f"💾 Aplicadas exitosamente: {actualizados}")
            _logger.info(f"💾 Ya aplicadas: {ya_aplicados}")
            _logger.info(f"💾 Sin equipo: {sin_equipo}")
            _logger.info(f"💾 Errores: {errores}")
            
            log_lines.append(f"✅ Aplicación completada:")
            log_lines.append(f"  • Aplicadas exitosamente: {actualizados}")
            log_lines.append(f"  • Ya aplicadas: {ya_aplicados}")
            log_lines.append(f"  • Sin equipo: {sin_equipo}")
            log_lines.append(f"  • Errores: {errores}")
            
            return {
                'actualizados': actualizados,
                'errores': errores,
                'ya_aplicados': ya_aplicados,
                'sin_equipo': sin_equipo,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ ERROR CRÍTICO aplicando a equipos: {str(e)}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            
            return {
                'actualizados': 0,
                'errores': 1,
                'log': [error_msg]
            }

    @api.model
    def obtener_estadisticas_consolidacion(self, dias=7):
        """
        PARTE 3 - MEJORADO: Obtiene estadísticas detalladas de consolidación
        """
        try:
            _logger.info(f"📊 Generando estadísticas de consolidación para últimos {dias} días")
            
            fecha_inicio = date.today() - timedelta(days=dias)
            
            # Estadísticas de lecturas diarias
            lecturas = self.env['printtracker.daily.reading'].search([
                ('fecha', '>=', fecha_inicio)
            ])
            
            _logger.info(f"📊 Total lecturas encontradas: {len(lecturas)}")
            
            # Estadísticas por fuente
            lecturas_por_fuente = {
                'correo': len(lecturas.filtered(lambda l: l.fuente_origen == 'correo')),
                'printtracker': len(lecturas.filtered(lambda l: l.fuente_origen == 'printtracker')),
                'consolidado': len(lecturas.filtered(lambda l: l.fuente_origen == 'consolidado')),
                'manual': len(lecturas.filtered(lambda l: l.fuente_origen == 'manual'))
            }
            
            # Estadísticas por estado
            lecturas_por_estado = {
                'borrador': len(lecturas.filtered(lambda l: l.estado == 'borrador')),
                'validado': len(lecturas.filtered(lambda l: l.estado == 'validado')),
                'aplicado': len(lecturas.filtered(lambda l: l.estado == 'aplicado')),
                'error': len(lecturas.filtered(lambda l: l.estado == 'error'))
            }
            
            # Estadísticas adicionales
            conflictos_detectados = len(lecturas.filtered('conflicto_detectado'))
            lecturas_aplicadas = len(lecturas.filtered('aplicado_a_equipo'))
            series_unicas = len(set(lecturas.mapped('serie')))
            equipos_con_actividad = len(set(lecturas.filtered('equipo_id').mapped('equipo_id')))
            lecturas_sin_equipo = len(lecturas.filtered(lambda l: not l.equipo_id))
            
            # Compilar estadísticas
            stats = {
                'periodo': {
                    'fecha_inicio': fecha_inicio.strftime('%Y-%m-%d'),
                    'fecha_fin': date.today().strftime('%Y-%m-%d'),
                    'dias': dias
                },
                'totales': {
                    'total_lecturas': len(lecturas),
                    'series_unicas': series_unicas,
                    'equipos_con_actividad': equipos_con_actividad,
                    'lecturas_sin_equipo': lecturas_sin_equipo
                },
                'por_fuente': lecturas_por_fuente,
                'por_estado': lecturas_por_estado,
                'consolidacion': {
                    'conflictos_detectados': conflictos_detectados,
                    'lecturas_aplicadas': lecturas_aplicadas,
                    'pendientes_aplicar': len(lecturas.filtered(lambda l: l.estado == 'validado' and not l.aplicado_a_equipo))
                }
            }
            
            # Agregar promedios si hay lecturas
            if lecturas:
                stats['promedios'] = {
                    'contador_bn': sum(l.contador_bn or 0 for l in lecturas) / len(lecturas),
                    'contador_color': sum(l.contador_color or 0 for l in lecturas) / len(lecturas),
                    'contador_scan': sum(l.contador_scan or 0 for l in lecturas) / len(lecturas),
                    'contador_total': sum(l.contador_total or 0 for l in lecturas) / len(lecturas)
                }
                
                # Series más activas (top 10)
                from collections import Counter
                series_count = Counter(lecturas.mapped('serie'))
                stats['series_mas_activas'] = series_count.most_common(10)
            
            _logger.info(f"📊 Estadísticas generadas: {len(lecturas)} lecturas, {series_unicas} series")
            
            return stats
            
        except Exception as e:
            _logger.error(f"❌ Error generando estadísticas: {str(e)}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return {}

    def action_diagnostico_completo(self):
        """
        PARTE 3 - NUEVO: Diagnóstico completo del sistema
        """
        try:
            _logger.info("🔍 ===== INICIANDO DIAGNÓSTICO COMPLETO =====")
            
            # Obtener estadísticas
            stats = self.obtener_estadisticas_consolidacion(dias=7)
            
            # Verificar duplicados
            duplicados_info = self._verificar_registros_duplicados()
            
            # Crear mensaje de diagnóstico
            mensaje = "🔍 === DIAGNÓSTICO COMPLETO CONSOLIDACIÓN ===\n\n"
            
            if stats:
                mensaje += f"📅 PERÍODO: {stats['periodo']['fecha_inicio']} a {stats['periodo']['fecha_fin']}\n\n"
                
                mensaje += "📊 TOTALES:\n"
                mensaje += f"• Total lecturas: {stats['totales']['total_lecturas']}\n"
                mensaje += f"• Series únicas: {stats['totales']['series_unicas']}\n"
                mensaje += f"• Equipos activos: {stats['totales']['equipos_con_actividad']}\n"
                mensaje += f"• Sin equipo: {stats['totales']['lecturas_sin_equipo']}\n\n"
                
                mensaje += "📋 POR FUENTE:\n"
                for fuente, count in stats['por_fuente'].items():
                    mensaje += f"• {fuente.title()}: {count}\n"
                mensaje += "\n"
                
                mensaje += "📊 POR ESTADO:\n"
                for estado, count in stats['por_estado'].items():
                    mensaje += f"• {estado.title()}: {count}\n"
                mensaje += "\n"
                
                mensaje += "⚖️ CONSOLIDACIÓN:\n"
                mensaje += f"• Conflictos detectados: {stats['consolidacion']['conflictos_detectados']}\n"
                mensaje += f"• Lecturas aplicadas: {stats['consolidacion']['lecturas_aplicadas']}\n"
                mensaje += f"• Pendientes aplicar: {stats['consolidacion']['pendientes_aplicar']}\n\n"
            
            if duplicados_info:
                mensaje += f"🔍 DUPLICADOS:\n"
                mensaje += f"• Total grupos: {duplicados_info['total_grupos']}\n"
                mensaje += f"• Con duplicados: {duplicados_info['duplicados']}\n\n"
            
            # Recomendaciones
            mensaje += "💡 RECOMENDACIONES:\n"
            if stats and stats['consolidacion']['pendientes_aplicar'] > 0:
                mensaje += f"• Ejecutar aplicación a equipos ({stats['consolidacion']['pendientes_aplicar']} pendientes)\n"
            if duplicados_info and duplicados_info['duplicados'] > 0:
                mensaje += f"• Revisar {duplicados_info['duplicados']} grupos duplicados\n"
            if stats and stats['totales']['lecturas_sin_equipo'] > 0:
                mensaje += f"• Revisar {stats['totales']['lecturas_sin_equipo']} lecturas sin equipo\n"
            
            if not any([
                stats and stats['consolidacion']['pendientes_aplicar'] > 0,
                duplicados_info and duplicados_info['duplicados'] > 0,
                stats and stats['totales']['lecturas_sin_equipo'] > 0
            ]):
                mensaje += "• Sistema funcionando correctamente ✅\n"
            
            _logger.info("✅ Diagnóstico completo generado")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Diagnóstico Completo',
                    'message': mensaje,
                    'type': 'info',
                    'sticky': True
                }
            }
            
        except Exception as e:
            error_msg = f'❌ Error en diagnóstico: {str(e)}'
            _logger.error(error_msg)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': error_msg,
                    'type': 'danger'
                }
            }