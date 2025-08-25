from odoo import models, fields, api
import logging
from datetime import datetime, timedelta, date

_logger = logging.getLogger(__name__)


class PrintTrackerProcessor(models.TransientModel):
    _name = 'printtracker.processor'
    _description = 'Procesador de Datos PrintTracker'

    # ========================================
    # CAMPOS DEL MODELO SIMPLIFICADOS
    # ========================================
    
    # Campos para configurar el procesamiento
    fecha_inicio = fields.Date('Fecha Inicio', default=lambda self: date.today() - timedelta(days=1))
    fecha_fin = fields.Date('Fecha Fin', default=lambda self: date.today())
    serie_especifica = fields.Char('Serie Específica', help='Dejar vacío para procesar todas')
    forzar_reproceso = fields.Boolean('Forzar Reproceso', default=False,
                                     help='Reprocesar registros ya procesados')
    
    # Resultados del procesamiento (simplificados)
    registros_printtracker = fields.Integer('Registros PrintTracker', readonly=True)
    lecturas_procesadas = fields.Integer('Lecturas Procesadas', readonly=True)
    equipos_actualizados = fields.Integer('Equipos Actualizados', readonly=True)
    errores_encontrados = fields.Integer('Errores Encontrados', readonly=True)
    
    log_procesamiento = fields.Text('Log de Procesamiento', readonly=True)

    # ========================================
    # MÉTODOS PRINCIPALES SIMPLIFICADOS
    # ========================================

    @api.model
    def ejecutar_procesamiento_automatico(self):
        """
        MEJORADO: Procesamiento automático completo con lógica clara
        """
        try:
            _logger.info("🔄 ===== PROCESAMIENTO AUTOMÁTICO DIARIO =====")
            hora_actual = datetime.now()
            _logger.info(f"🕐 Ejecutándose a las: {hora_actual}")
            
            # PASO 1: SINCRONIZAR CON API PRINTTRACKER
            _logger.info("🔄 === PASO 1: SINCRONIZACIÓN API ===")
            config = self.env['printtracker.config'].search([('sync_enabled', '=', True)], limit=1)
            
            if not config:
                _logger.error("❌ No hay configuración activa de PrintTracker")
                return False
            
            # Sincronizar dispositivos y medidores
            _logger.info("📱 Sincronizando dispositivos...")
            result_devices = config.sync_all_devices()
            
            _logger.info("📊 Sincronizando medidores...")  
            result_meters = config.sync_current_meters()
            
            # PASO 2: PROCESAR METERS A LECTURAS DIARIAS
            _logger.info("🔄 === PASO 2: GENERANDO LECTURAS DIARIAS ===")
            
            # Buscar meters de las últimas 48 horas que no tienen lectura diaria
            cutoff_date = datetime.now() - timedelta(hours=48)
            meters_sin_procesar = self.env['printtracker.meter'].search([
                ('reading_date', '>=', cutoff_date),
                ('id', 'not in', self.env['printtracker.daily.reading'].search([
                    ('printtracker_meter_id', '!=', False)
                ]).mapped('printtracker_meter_id.id'))
            ])
            
            _logger.info(f"📊 Meters sin procesar: {len(meters_sin_procesar)}")
            
            lecturas_creadas = 0
            for meter in meters_sin_procesar:
                if meter._crear_o_actualizar_lectura_diaria():
                    lecturas_creadas += 1
            
            _logger.info(f"📋 Lecturas diarias creadas/actualizadas: {lecturas_creadas}")
            
            # PASO 3: APLICAR LECTURAS PENDIENTES A EQUIPOS  
            _logger.info("🔄 === PASO 3: APLICANDO A EQUIPOS ===")
            
            # Buscar lecturas validadas no aplicadas
            lecturas_pendientes = self.env['printtracker.daily.reading'].search([
                ('estado', '=', 'validado'),
                ('aplicado_a_equipo', '=', False),
                ('fecha', '>=', date.today() - timedelta(days=2))  # Últimos 2 días
            ])
            
            _logger.info(f"💾 Lecturas pendientes: {len(lecturas_pendientes)}")
            
            equipos_actualizados = 0
            for lectura in lecturas_pendientes:
                if lectura._aplicar_lectura_a_equipo(lectura):
                    equipos_actualizados += 1
            
            _logger.info(f"💾 Equipos actualizados: {equipos_actualizados}")
            
            # PASO 4: LIMPIEZA AUTOMÁTICA (OPCIONAL)
            if hora_actual.hour == 2:  # Solo a las 2 AM
                _logger.info("🗑️ === PASO 4: LIMPIEZA AUTOMÁTICA ===")
                
                # Limpiar meters antiguos (mantener 90 días)
                cleanup_result = self.env['printtracker.meter'].cleanup_old_readings(90)
                _logger.info(f"🗑️ Limpieza: {cleanup_result['deleted_count']} meters eliminados")
            
            # RESUMEN FINAL
            _logger.info("✅ ===== PROCESAMIENTO AUTOMÁTICO COMPLETADO =====")
            _logger.info(f"📊 Lecturas creadas: {lecturas_creadas}")
            _logger.info(f"💾 Equipos actualizados: {equipos_actualizados}")
            _logger.info(f"🕐 Duración: {(datetime.now() - hora_actual).total_seconds():.1f}s")
            
            return True
            
        except Exception as e:
            _logger.error(f"❌ ERROR CRÍTICO en procesamiento automático: {str(e)}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return False

    def ejecutar_procesamiento(self):
        """
        SIMPLIFICADO: Ejecuta el proceso de PrintTracker sin consolidación
        """
        try:
            inicio_tiempo = datetime.now()
            log_lines = []
            
            _logger.info(f"🔄 ===== INICIANDO PROCESO PRINTTRACKER =====")
            _logger.info(f"🆔 Procesador ID: {self.id}")
            _logger.info(f"📅 Período: {self.fecha_inicio} a {self.fecha_fin}")
            _logger.info(f"🎯 Serie: {self.serie_especifica or 'TODAS'}")
            _logger.info(f"🔄 Forzar reproceso: {'SÍ' if self.forzar_reproceso else 'NO'}")
            
            log_lines.append(f"🔄 === INICIANDO PROCESAMIENTO ===")
            log_lines.append(f"📅 Período: {self.fecha_inicio} a {self.fecha_fin}")
            log_lines.append(f"🎯 Serie: {self.serie_especifica or 'TODAS LAS SERIES'}")
            log_lines.append(f"🔄 Forzar reproceso: {'SÍ' if self.forzar_reproceso else 'NO'}")
            log_lines.append(f"🕐 Inicio: {inicio_tiempo}")
            log_lines.append("")
            
            # Inicializar contadores
            self.registros_printtracker = 0
            self.lecturas_procesadas = 0
            self.equipos_actualizados = 0
            self.errores_encontrados = 0
            
            # PASO 1: Procesar registros de PrintTracker
            _logger.info("🔄 === INICIANDO PASO 1: PRINTTRACKER ===")
            log_lines.append("🔄 === PASO 1: PROCESANDO PRINTTRACKER ===")
            
            resultado_pt = self._procesar_printtracker_meters()
            log_lines.extend(resultado_pt['log'])
            self.registros_printtracker = resultado_pt['procesados']
            self.errores_encontrados += resultado_pt.get('errores', 0)
            
            _logger.info(f"🔄 Paso 1 completado: {self.registros_printtracker} procesados")
            
            # PASO 2: Aplicar a equipos
            _logger.info("💾 === INICIANDO PASO 2: APLICACIÓN A EQUIPOS ===")
            log_lines.append("💾 === PASO 2: APLICANDO A EQUIPOS ===")
            
            resultado_equipos = self._aplicar_a_equipos()
            log_lines.extend(resultado_equipos['log'])
            self.equipos_actualizados = resultado_equipos['actualizados']
            self.lecturas_procesadas = resultado_equipos.get('procesadas', 0)
            self.errores_encontrados += resultado_equipos.get('errores', 0)
            
            _logger.info(f"💾 Paso 2 completado: {self.equipos_actualizados} equipos actualizados")
            
            # PASO 3: Estadísticas finales
            _logger.info("📊 === GENERANDO ESTADÍSTICAS FINALES ===")
            log_lines.append("📊 === PASO 3: ESTADÍSTICAS FINALES ===")
            
            tiempo_total = (datetime.now() - inicio_tiempo).total_seconds()
            
            log_lines.append(f"⏱️ Tiempo total: {tiempo_total:.2f} segundos")
            log_lines.append(f"🔄 PrintTracker: {self.registros_printtracker} registros")
            log_lines.append(f"📋 Lecturas procesadas: {self.lecturas_procesadas}")
            log_lines.append(f"💾 Equipos actualizados: {self.equipos_actualizados}")
            log_lines.append(f"❌ Errores: {self.errores_encontrados}")
            log_lines.append("")
            
            # Determinar éxito/fracaso
            exito = self.errores_encontrados == 0
            if exito:
                log_lines.append("✅ === PROCESAMIENTO COMPLETADO EXITOSAMENTE ===")
                _logger.info(f"✅ ===== PROCESAMIENTO COMPLETADO EXITOSAMENTE =====")
            else:
                log_lines.append(f"⚠️ === PROCESAMIENTO COMPLETADO CON {self.errores_encontrados} ERRORES ===")
                _logger.warning(f"⚠️ ===== PROCESAMIENTO COMPLETADO CON {self.errores_encontrados} ERRORES =====")
            
            # Guardar log completo
            self.log_procesamiento = "\n".join(log_lines)
            
            _logger.info(f"📊 Resumen final: PT={self.registros_printtracker}, "
                        f"PROC={self.lecturas_procesadas}, EQ={self.equipos_actualizados}, "
                        f"ERR={self.errores_encontrados}, T={tiempo_total:.1f}s")
            
            return exito
            
        except Exception as e:
            error_msg = f"❌ ERROR CRÍTICO en procesamiento: {str(e)}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            
            # Intentar guardar error en log
            try:
                current_log = self.log_procesamiento or ""
                self.log_procesamiento = current_log + f"\n{error_msg}\n{traceback.format_exc()}"
                self.errores_encontrados = (self.errores_encontrados or 0) + 1
            except:
                _logger.error("❌ No se pudo guardar error en log del procesador")
            
            return False

    def action_ejecutar_manual(self):
        """
        SIMPLIFICADO: Acción para ejecutar procesamiento manual
        """
        self.ensure_one()
        
        try:
            _logger.info(f"✋ ===== PROCESAMIENTO MANUAL SOLICITADO =====")
            _logger.info(f"🆔 Procesador ID: {self.id}")
            _logger.info(f"📅 Período: {self.fecha_inicio} a {self.fecha_fin}")
            _logger.info(f"🎯 Serie: {self.serie_especifica or 'TODAS'}")
            _logger.info(f"🔄 Forzar: {self.forzar_reproceso}")
            
            resultado = self.ejecutar_procesamiento()
            
            if resultado:
                message = f"""✅ PROCESAMIENTO EJECUTADO EXITOSAMENTE

📊 RESUMEN DE RESULTADOS:
- Período: {self.fecha_inicio} a {self.fecha_fin}
- Serie: {self.serie_especifica or 'TODAS'}

🔄 PrintTracker: {self.registros_printtracker} registros
📋 Lecturas procesadas: {self.lecturas_procesadas}
💾 Equipos actualizados: {self.equipos_actualizados}
❌ Errores: {self.errores_encontrados}

Ver log completo para detalles."""
                
                message_type = 'success'
                _logger.info(f"✅ Procesamiento manual exitoso")
            else:
                message = f"""❌ PROCESAMIENTO COMPLETADO CON ERRORES

📊 RESUMEN:
- Errores encontrados: {self.errores_encontrados}
- Procesados parcialmente: {self.registros_printtracker}

⚠️ Revisar log completo para detalles de errores."""
                
                message_type = 'warning'
                _logger.warning(f"⚠️ Procesamiento manual con errores")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Procesamiento PrintTracker',
                    'message': message,
                    'type': message_type,
                    'sticky': True
                }
            }
            
        except Exception as e:
            error_msg = f'❌ ERROR EJECUTANDO PROCESAMIENTO: {str(e)}'
            _logger.error(error_msg)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error Procesamiento',
                    'message': error_msg,
                    'type': 'danger',
                    'sticky': True
                }
            }

    def action_view_log(self):
        """Ver el log detallado en una ventana"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Log de Procesamiento - {self.fecha_inicio} a {self.fecha_fin}',
            'res_model': 'printtracker.processor',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'form_view_initial_mode': 'readonly'
            }
        }

    # ========================================
    # PROCESAMIENTO DE PRINTTRACKER SIMPLIFICADO
    # ========================================

    def _procesar_printtracker_meters(self):
        """
        SIMPLIFICADO: Procesa registros de printtracker.meter
        Sin consolidación - flujo directo
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
                    _logger.info(f"🔄 Contadores: BN={meter.black_pages_life}, Color={meter.color_pages_life}, Scan={meter.scan_pages}")
                    
                    # Buscar lectura existente
                    existing_reading = self.env['printtracker.daily.reading'].search([
                        ('fecha', '=', fecha_lectura),
                        ('serie', '=', serie)
                    ], limit=1)
                    
                    if existing_reading:
                        _logger.info(f"🔄 Lectura existente encontrada: ID={existing_reading.id}")
                        
                        if not self.forzar_reproceso:
                            _logger.info(f"🔄 Saltando {serie} - {fecha_lectura} (ya existe, no forzado)")
                            log_lines.append(f"⏭️ Ya existe lectura para {serie} - {fecha_lectura}")
                            continue
                        else:
                            # Forzar reproceso: actualizar lectura existente
                            _logger.info(f"🔄 Forzando actualización de lectura existente")
                            
                            existing_reading.write({
                                'contador_bn': meter.black_pages_life or 0,
                                'contador_color': meter.color_pages_life or 0,
                                'contador_scan': meter.scan_pages or 0,
                                'contador_copy': meter.copy_pages or 0,
                                'contador_fax': meter.fax_pages or 0,
                                'printtracker_meter_id': meter.id,
                                'fecha_procesamiento': fields.Datetime.now()
                            })
                            
                            log_lines.append(f"📝 FORZADO: Actualizada lectura {serie} - {fecha_lectura}")
                            _logger.info(f"✅ Actualización forzada completada para {serie}")
                            procesados += 1
                            continue
                    
                    # Crear nueva lectura usando el método simplificado
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

    def _verificar_registros_inconsistentes(self):
        """
        NUEVO: Verifica registros con inconsistencias en el período
        """
        try:
            log_lines = []
            
            _logger.info("🔍 ===== VERIFICANDO INCONSISTENCIAS =====")
            
            # Buscar lecturas del período
            domain = [
                ('fecha', '>=', self.fecha_inicio),
                ('fecha', '<=', self.fecha_fin)
            ]
            
            if self.serie_especifica:
                domain.append(('serie', '=', self.serie_especifica))
            
            lecturas = self.env['printtracker.daily.reading'].search(domain)
            
            _logger.info(f"🔍 Analizando {len(lecturas)} lecturas...")
            
            # Verificar problemas
            problemas = {
                'sin_equipo': len(lecturas.filtered(lambda l: not l.equipo_id)),
                'en_error': len(lecturas.filtered(lambda l: l.estado == 'error')),
                'sin_aplicar': len(lecturas.filtered(lambda l: l.estado == 'validado' and not l.aplicado_a_equipo)),
                'contadores_negativos': len(lecturas.filtered(lambda l: 
                    (l.contador_bn or 0) < 0 or (l.contador_color or 0) < 0 or (l.contador_scan or 0) < 0))
            }
            
            _logger.info(f"🔍 Problemas encontrados: {problemas}")
            
            log_lines.append(f"🔍 Verificación de inconsistencias:")
            log_lines.append(f"• Total lecturas analizadas: {len(lecturas)}")
            log_lines.append(f"• Sin equipo asociado: {problemas['sin_equipo']}")
            log_lines.append(f"• En estado error: {problemas['en_error']}")
            log_lines.append(f"• Sin aplicar: {problemas['sin_aplicar']}")
            log_lines.append(f"• Contadores negativos: {problemas['contadores_negativos']}")
            
            total_problemas = sum(problemas.values())
            
            if total_problemas > 0:
                log_lines.append(f"⚠️ Total problemas encontrados: {total_problemas}")
                _logger.warning(f"⚠️ Total problemas encontrados: {total_problemas}")
            else:
                log_lines.append("✅ No se encontraron inconsistencias")
                _logger.info("✅ No se encontraron inconsistencias")
            
            return {
                'total_lecturas': len(lecturas),
                'problemas': problemas,
                'total_problemas': total_problemas,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ Error verificando inconsistencias: {str(e)}"
            _logger.error(error_msg)
            
            return {
                'total_lecturas': 0,
                'problemas': {},
                'total_problemas': 0,
                'log': [error_msg]
            }

    def _sincronizar_con_api(self):
        """
        NUEVO: Sincroniza con la API de PrintTracker antes del procesamiento
        """
        try:
            log_lines = []
            _logger.info("🔄 ===== SINCRONIZANDO CON API PRINTTRACKER =====")
            
            # Obtener configuración activa
            config = self.env['printtracker.config'].search([
                ('sync_enabled', '=', True)
            ], limit=1)
            
            if not config:
                error_msg = "❌ No se encontró configuración activa de PrintTracker"
                _logger.error(error_msg)
                log_lines.append(error_msg)
                return {
                    'dispositivos': 0,
                    'medidores': 0,
                    'errores': 1,
                    'log': log_lines
                }
            
            _logger.info(f"🔄 Usando configuración: {config.name}")
            log_lines.append(f"🔄 Sincronizando con configuración: {config.name}")
            
            dispositivos_sync = 0
            medidores_sync = 0
            errores_sync = 0
            
            try:
                # Sincronizar dispositivos
                _logger.info("📱 Sincronizando dispositivos...")
                resultado_devices = config.sync_all_devices()
                
                if resultado_devices and resultado_devices.get('params', {}).get('type') == 'success':
                    dispositivos_sync = 1  # Éxito en sincronización
                    log_lines.append("✅ Dispositivos sincronizados")
                    _logger.info("✅ Dispositivos sincronizados exitosamente")
                else:
                    errores_sync += 1
                    log_lines.append("❌ Error sincronizando dispositivos")
                    _logger.error("❌ Error sincronizando dispositivos")
                
            except Exception as e:
                errores_sync += 1
                _logger.error(f"❌ Error en sincronización de dispositivos: {str(e)}")
                log_lines.append(f"❌ Error dispositivos: {str(e)}")
            
            try:
                # Sincronizar medidores
                _logger.info("📊 Sincronizando medidores...")
                resultado_meters = config.sync_current_meters()
                
                if resultado_meters and resultado_meters.get('params', {}).get('type') == 'success':
                    medidores_sync = 1  # Éxito en sincronización
                    log_lines.append("✅ Medidores sincronizados")
                    _logger.info("✅ Medidores sincronizados exitosamente")
                else:
                    errores_sync += 1
                    log_lines.append("❌ Error sincronizando medidores")
                    _logger.error("❌ Error sincronizando medidores")
                
            except Exception as e:
                errores_sync += 1
                _logger.error(f"❌ Error en sincronización de medidores: {str(e)}")
                log_lines.append(f"❌ Error medidores: {str(e)}")
            
            # Resumen
            _logger.info(f"🔄 Sincronización completada: {errores_sync} errores")
            if errores_sync == 0:
                log_lines.append("✅ Sincronización API completada exitosamente")
            else:
                log_lines.append(f"⚠️ Sincronización completada con {errores_sync} errores")
            
            return {
                'dispositivos': dispositivos_sync,
                'medidores': medidores_sync,
                'errores': errores_sync,
                'log': log_lines
            }
            
        except Exception as e:
            error_msg = f"❌ ERROR CRÍTICO en sincronización API: {str(e)}"
            _logger.error(error_msg)
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            
            return {
                'dispositivos': 0,
                'medidores': 0,
                'errores': 1,
                'log': [error_msg]
            }

    @api.model
    def ejecutar_sincronizacion_completa(self):
        """
        NUEVO: Método específico para sincronización completa con API
        """
        try:
            _logger.info("🔄 ===== SINCRONIZACIÓN COMPLETA INICIADA =====")
            
            # Crear procesador temporal para sincronización
            procesador = self.create({
                'fecha_inicio': date.today(),
                'fecha_fin': date.today(),
                'forzar_reproceso': False
            })
            
            # Ejecutar sincronización
            resultado = procesador._sincronizar_con_api()
            
            # Log del resultado
            if resultado['errores'] == 0:
                _logger.info("✅ Sincronización completa exitosa")
                return True
            else:
                _logger.warning(f"⚠️ Sincronización con {resultado['errores']} errores")
                return False
                
        except Exception as e:
            _logger.error(f"❌ Error en sincronización completa: {str(e)}")
            return False

    # ========================================
    # APLICACIÓN A EQUIPOS Y UTILIDADES SIMPLIFICADAS
    # ========================================

    def _aplicar_a_equipos(self):
        """
        SIMPLIFICADO: Aplica lecturas pendientes a los equipos
        Sin lógica de consolidación - aplicación directa
        """
        try:
            log_lines = []
            actualizados = 0
            errores = 0
            ya_aplicados = 0
            sin_equipo = 0
            procesadas = 0
            
            _logger.info("💾 ===== INICIANDO APLICACIÓN A EQUIPOS =====")
            _logger.info(f"💾 Período: {self.fecha_inicio} a {self.fecha_fin}")
            
            # Buscar lecturas que necesitan ser aplicadas
            domain = [
                ('fecha', '>=', self.fecha_inicio),
                ('fecha', '<=', self.fecha_fin),
                ('estado', '=', 'validado'),
                ('aplicado_a_equipo', '=', False)
            ]
            
            if self.serie_especifica:
                domain.append(('serie', '=', self.serie_especifica))
            
            lecturas_pendientes = self.env['printtracker.daily.reading'].search(domain)
            
            _logger.info(f"💾 Lecturas pendientes encontradas: {len(lecturas_pendientes)}")
            log_lines.append(f"💾 Encontradas {len(lecturas_pendientes)} lecturas pendientes")
            
            # Verificar lecturas ya aplicadas para estadísticas
            domain_aplicadas = domain.copy()
            domain_aplicadas[2] = ('aplicado_a_equipo', '=', True)
            lecturas_aplicadas = self.env['printtracker.daily.reading'].search(domain_aplicadas)
            ya_aplicados = len(lecturas_aplicadas)
            
            _logger.info(f"💾 Lecturas ya aplicadas: {ya_aplicados}")
            log_lines.append(f"💾 Ya aplicadas en período: {ya_aplicados}")
            
            if not lecturas_pendientes:
                log_lines.append("ℹ️ No hay lecturas pendientes de aplicar")
                _logger.info("ℹ️ No hay lecturas pendientes de aplicar")
                
                return {
                    'actualizados': 0,
                    'procesadas': ya_aplicados,
                    'errores': 0,
                    'ya_aplicados': ya_aplicados,
                    'sin_equipo': 0,
                    'log': log_lines
                }
            
            # Procesar cada lectura pendiente
            for i, lectura in enumerate(lecturas_pendientes, 1):
                try:
                    _logger.info(f"💾 --- Aplicando {i}/{len(lecturas_pendientes)}: {lectura.serie} ---")
                    
                    # Verificar si tiene equipo
                    if not lectura.equipo_id:
                        _logger.warning(f"💾 Sin equipo: {lectura.serie}")
                        log_lines.append(f"⚠️ Sin equipo: {lectura.serie} - {lectura.fecha}")
                        sin_equipo += 1
                        continue
                    
                    # Aplicar al equipo
                    _logger.info(f"💾 Aplicando lectura al equipo...")
                    resultado_aplicacion = lectura._aplicar_lectura_a_equipo(lectura)
                    
                    if resultado_aplicacion:
                        _logger.info(f"✅ Aplicada exitosamente: {lectura.serie}")
                        log_lines.append(f"✅ {lectura.serie} → {lectura.equipo_id.name}")
                        actualizados += 1
                        procesadas += 1
                    else:
                        _logger.error(f"❌ Error aplicando: {lectura.serie}")
                        error_detail = lectura.mensaje_error or "Error desconocido"
                        log_lines.append(f"❌ Error: {lectura.serie} ({error_detail})")
                        errores += 1
                        
                except Exception as e:
                    error_msg = f"❌ Error aplicando {lectura.serie}: {str(e)}"
                    _logger.error(error_msg)
                    import traceback
                    _logger.error(f"❌ Traceback: {traceback.format_exc()}")
                    
                    log_lines.append(f"❌ Error: {lectura.serie}")
                    errores += 1
            
            # Incluir ya aplicadas en el total procesadas
            procesadas += ya_aplicados
            
            # Resumen final
            _logger.info(f"💾 ===== APLICACIÓN A EQUIPOS COMPLETADA =====")
            _logger.info(f"💾 Nuevas aplicadas: {actualizados}")
            _logger.info(f"💾 Ya aplicadas: {ya_aplicados}")
            _logger.info(f"💾 Total procesadas: {procesadas}")
            _logger.info(f"💾 Sin equipo: {sin_equipo}")
            _logger.info(f"💾 Errores: {errores}")
            
            log_lines.append(f"✅ Aplicación completada:")
            log_lines.append(f"  • Nuevas aplicadas: {actualizados}")
            log_lines.append(f"  • Ya aplicadas: {ya_aplicados}")
            log_lines.append(f"  • Total procesadas: {procesadas}")
            log_lines.append(f"  • Sin equipo: {sin_equipo}")
            log_lines.append(f"  • Errores: {errores}")
            
            return {
                'actualizados': actualizados,
                'procesadas': procesadas,
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
                'procesadas': 0,
                'errores': 1,
                'log': [error_msg]
            }

    @api.model
    def obtener_estadisticas_sistema(self, dias=7):
        """
        SIMPLIFICADO: Estadísticas del sistema PrintTracker
        """
        try:
            _logger.info(f"📊 Generando estadísticas para últimos {dias} días")
            
            fecha_inicio = date.today() - timedelta(days=dias)
            
            # Estadísticas de lecturas diarias
            lecturas = self.env['printtracker.daily.reading'].search([
                ('fecha', '>=', fecha_inicio)
            ])
            
            _logger.info(f"📊 Total lecturas encontradas: {len(lecturas)}")
            
            # Estadísticas por fuente (simplificadas)
            lecturas_por_fuente = {
                'printtracker': len(lecturas.filtered(lambda l: l.fuente_origen == 'printtracker')),
                'manual': len(lecturas.filtered(lambda l: l.fuente_origen == 'manual'))
            }
            
            # Estadísticas por estado
            lecturas_por_estado = {
                'validado': len(lecturas.filtered(lambda l: l.estado == 'validado')),
                'aplicado': len(lecturas.filtered(lambda l: l.estado == 'aplicado')),
                'error': len(lecturas.filtered(lambda l: l.estado == 'error'))
            }
            
            # Estadísticas adicionales
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
                'procesamiento': {
                    'lecturas_aplicadas': lecturas_aplicadas,
                    'pendientes_aplicar': len(lecturas.filtered(lambda l: l.estado == 'validado' and not l.aplicado_a_equipo)),
                    'tasa_exito': (lecturas_aplicadas / len(lecturas) * 100) if len(lecturas) > 0 else 0
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

    def action_diagnostico_sistema(self):
        """
        SIMPLIFICADO: Diagnóstico completo del sistema
        """
        try:
            _logger.info("🔍 ===== INICIANDO DIAGNÓSTICO SISTEMA =====")
            
            # Obtener estadísticas
            stats = self.obtener_estadisticas_sistema(dias=7)
            
            # Verificar inconsistencias
            inconsistencias_info = self._verificar_registros_inconsistentes()
            
            # Crear mensaje de diagnóstico
            mensaje = "🔍 === DIAGNÓSTICO SISTEMA PRINTTRACKER ===\n\n"
            
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
                
                mensaje += "💾 PROCESAMIENTO:\n"
                mensaje += f"• Lecturas aplicadas: {stats['procesamiento']['lecturas_aplicadas']}\n"
                mensaje += f"• Pendientes aplicar: {stats['procesamiento']['pendientes_aplicar']}\n"
                mensaje += f"• Tasa éxito: {stats['procesamiento']['tasa_exito']:.1f}%\n\n"
            
            if inconsistencias_info:
                mensaje += f"🔍 INCONSISTENCIAS:\n"
                mensaje += f"• Total lecturas analizadas: {inconsistencias_info['total_lecturas']}\n"
                for problema, count in inconsistencias_info['problemas'].items():
                    if count > 0:
                        mensaje += f"• {problema.replace('_', ' ').title()}: {count}\n"
                mensaje += "\n"
            
            # Recomendaciones
            mensaje += "💡 RECOMENDACIONES:\n"
            if stats and stats['procesamiento']['pendientes_aplicar'] > 0:
                mensaje += f"• Ejecutar aplicación a equipos ({stats['procesamiento']['pendientes_aplicar']} pendientes)\n"
            if inconsistencias_info and inconsistencias_info['total_problemas'] > 0:
                mensaje += f"• Revisar {inconsistencias_info['total_problemas']} inconsistencias\n"
            if stats and stats['totales']['lecturas_sin_equipo'] > 0:
                mensaje += f"• Revisar {stats['totales']['lecturas_sin_equipo']} lecturas sin equipo\n"
            
            if not any([
                stats and stats['procesamiento']['pendientes_aplicar'] > 0,
                inconsistencias_info and inconsistencias_info['total_problemas'] > 0,
                stats and stats['totales']['lecturas_sin_equipo'] > 0
            ]):
                mensaje += "• Sistema funcionando correctamente ✅\n"
            
            _logger.info("✅ Diagnóstico sistema generado")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Diagnóstico Sistema',
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

    @api.model
    def limpiar_datos_antiguos(self, dias=30):
        """
        NUEVO: Limpia datos antiguos del sistema
        """
        try:
            fecha_limite = date.today() - timedelta(days=dias)
            _logger.info(f"🗑️ Iniciando limpieza de datos anteriores a: {fecha_limite}")
            
            # Limpiar lecturas diarias antiguas en estado 'aplicado'
            lecturas_antiguas = self.env['printtracker.daily.reading'].search([
                ('fecha', '<', fecha_limite),
                ('estado', '=', 'aplicado'),
                ('aplicado_a_equipo', '=', True)
            ])
            
            count_lecturas = len(lecturas_antiguas)
            
            # Limpiar meters antiguos (mantener solo últimos 30 días)
            meters_antiguos = self.env['printtracker.meter'].search([
                ('reading_date', '<', datetime.combine(fecha_limite, datetime.min.time()))
            ])
            
            count_meters = len(meters_antiguos)
            
            if count_lecturas > 0:
                lecturas_antiguas.unlink()
                _logger.info(f"✅ Limpieza lecturas: {count_lecturas} registros eliminados")
            
            if count_meters > 0:
                meters_antiguos.unlink()
                _logger.info(f"✅ Limpieza meters: {count_meters} registros eliminados")
            
            if count_lecturas == 0 and count_meters == 0:
                _logger.info(f"ℹ️ No hay datos antiguos para eliminar")
            
            return {
                'lecturas_eliminadas': count_lecturas,
                'meters_eliminados': count_meters,
                'fecha_limite': fecha_limite
            }
            
        except Exception as e:
            _logger.error(f"❌ Error en limpieza: {str(e)}")
            return {
                'lecturas_eliminadas': 0,
                'meters_eliminados': 0,
                'error': str(e)
            }

    def action_sincronizar_api(self):
        """
        NUEVO: Acción manual para sincronizar con API
        """
        self.ensure_one()
        
        try:
            _logger.info("🔄 Sincronización manual con API solicitada")
            
            resultado = self._sincronizar_con_api()
            
            if resultado['errores'] == 0:
                mensaje = f"""✅ SINCRONIZACIÓN API EXITOSA

📊 RESULTADOS:
- Dispositivos: {'✅' if resultado['dispositivos'] else '⚠️'}
- Medidores: {'✅' if resultado['medidores'] else '⚠️'}
- Errores: {resultado['errores']}

La sincronización se completó correctamente."""
                
                message_type = 'success'
            else:
                mensaje = f"""⚠️ SINCRONIZACIÓN CON ERRORES

📊 RESULTADOS:
- Dispositivos: {'✅' if resultado['dispositivos'] else '❌'}
- Medidores: {'✅' if resultado['medidores'] else '❌'}
- Errores: {resultado['errores']}

Revisar configuración de PrintTracker."""
                
                message_type = 'warning'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sincronización API',
                    'message': mensaje,
                    'type': message_type,
                    'sticky': True
                }
            }
            
        except Exception as e:
            error_msg = f'❌ Error en sincronización: {str(e)}'
            _logger.error(error_msg)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': error_msg,
                    'type': 'danger'
                }
            }