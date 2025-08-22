from odoo import models, fields, api
import logging
from datetime import datetime, timedelta, date

_logger = logging.getLogger(__name__)


class PrintTrackerDailyReading(models.Model):
    _name = 'printtracker.daily.reading'
    _description = 'Lecturas Diarias PrintTracker'
    _order = 'fecha desc, serie'
    _rec_name = 'display_name'

    # ========================================
    # CAMPOS DEL MODELO SIMPLIFICADOS
    # ========================================
    
    # Identificación principal
    fecha = fields.Date('Fecha', required=True, index=True)
    serie = fields.Char('Serie del Equipo', required=True, index=True)
    equipo_id = fields.Many2one('alquiler', string='Equipo', 
                               compute='_compute_equipo_id', store=True, index=True)
    
    # Contadores finales
    contador_bn = fields.Integer('Contador B/N', default=0)
    contador_color = fields.Integer('Contador Color', default=0) 
    contador_scan = fields.Integer('Contador Scan', default=0)
    contador_copy = fields.Integer('Contador Copy', default=0)
    contador_fax = fields.Integer('Contador Fax', default=0)
    contador_total = fields.Integer('Contador Total', compute='_compute_contador_total', store=True)
    
    # Información de origen simplificada
    fuente_origen = fields.Selection([
        ('printtracker', 'PrintTracker API'),
        ('manual', 'Manual')
    ], string='Fuente de Origen', required=True, index=True, default='printtracker')
    
    # Referencia a registro de origen
    printtracker_meter_id = fields.Many2one('printtracker.meter', 
                                          string='Registro PrintTracker')
    
    # Información de procesamiento
    fecha_procesamiento = fields.Datetime('Fecha de Procesamiento', 
                                         default=fields.Datetime.now, readonly=True)
    procesado_por = fields.Many2one('res.users', string='Procesado Por', 
                                    default=lambda self: self.env.user, readonly=True)
    
    # Campos de análisis
    incremento_bn = fields.Integer('Incremento B/N', compute='_compute_incrementos', store=True)
    incremento_color = fields.Integer('Incremento Color', compute='_compute_incrementos', store=True)
    incremento_scan = fields.Integer('Incremento Scan', compute='_compute_incrementos', store=True)
    incremento_total = fields.Integer('Incremento Total', compute='_compute_incrementos', store=True)
    
    # Estado y validación
    estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('validado', 'Validado'),
        ('aplicado', 'Aplicado al Equipo'),
        ('error', 'Error')
    ], string='Estado', default='validado', index=True)
    
    mensaje_error = fields.Text('Mensaje de Error')
    aplicado_a_equipo = fields.Boolean('Aplicado al Equipo', default=False)
    fecha_aplicacion = fields.Datetime('Fecha de Aplicación')
    
    # Campo de display
    display_name = fields.Char('Nombre', compute='_compute_display_name', store=True)
    
    # Información adicional del equipo (cache)
    cliente_nombre = fields.Char('Cliente', compute='_compute_equipo_info', store=True)
    modelo_equipo = fields.Char('Modelo', compute='_compute_equipo_info', store=True)
    tipo_equipo = fields.Selection([
        ('color', 'Color'),
        ('monocromatica', 'Monocromática')
    ], string='Tipo Equipo', compute='_compute_equipo_info', store=True)
    
    # Constrains simplificados
    _sql_constraints = [
        ('unique_fecha_serie', 'UNIQUE(fecha, serie)', 
         'Solo puede haber una lectura por fecha y serie'),
        ('positive_counters', 'CHECK(contador_bn >= 0 AND contador_color >= 0 AND contador_scan >= 0)', 
         'Los contadores deben ser positivos'),
        ('valid_date', 'CHECK(fecha <= CURRENT_DATE)', 
         'La fecha no puede ser futura')
    ]
    # ========================================
    # MÉTODOS DE CREACIÓN SIMPLIFICADOS
    # ========================================

    @api.model
    def crear_desde_printtracker(self, meter_record):
        """
        SIMPLIFICADO: Crea lectura desde PrintTracker - UNA SOLA FUENTE
        """
        try:
            _logger.info(f"🔄 ===== CREANDO LECTURA DESDE PRINTTRACKER =====")
            _logger.info(f"🔄 Device ID: {meter_record.device_id}")
            _logger.info(f"🔄 ID meter: {meter_record.id}")
            
            if not meter_record.device_id or not meter_record.device_id.serie:
                _logger.error("❌ PRINTTRACKER - Meter sin serie")
                return False
            
            serie = meter_record.device_id.serie
            fecha_lectura = meter_record.reading_date.date() if meter_record.reading_date else date.today()
            
            # Valores de PrintTracker
            pt_bn = meter_record.black_pages_life or 0
            pt_color = meter_record.color_pages_life or 0
            pt_scan = meter_record.scan_pages or 0
            pt_copy = meter_record.copy_pages or 0
            pt_fax = meter_record.fax_pages or 0
            
            _logger.info(f"🔄 Serie: {serie}")
            _logger.info(f"🔄 Fecha de lectura: {fecha_lectura}")
            _logger.info(f"🔄 Contadores: BN={pt_bn}, Color={pt_color}, Scan={pt_scan}, Copy={pt_copy}, Fax={pt_fax}")
            
            # Buscar lectura existente
            existing_reading = self.search([
                ('fecha', '=', fecha_lectura),
                ('serie', '=', serie)
            ], limit=1)
            
            if existing_reading:
                _logger.info(f"🔄 Lectura existente encontrada: ID={existing_reading.id}")
                _logger.info(f"🔄 Fuente existente: {existing_reading.fuente_origen}")
                
                if existing_reading.fuente_origen == 'printtracker':
                    # Actualizar lectura existente con valores más recientes
                    _logger.info(f"📝 Actualizando lectura PrintTracker existente...")
                    existing_reading.write({
                        'contador_bn': pt_bn,
                        'contador_color': pt_color,
                        'contador_scan': pt_scan,
                        'contador_copy': pt_copy,
                        'contador_fax': pt_fax,
                        'printtracker_meter_id': meter_record.id,
                        'fecha_procesamiento': fields.Datetime.now()
                    })
                    _logger.info(f"✅ Lectura actualizada exitosamente")
                    return existing_reading
                
                elif existing_reading.fuente_origen == 'manual':
                    # No sobrescribir lecturas manuales
                    _logger.warning(f"⚠️ Existe lectura manual - no se sobrescribe")
                    return existing_reading
            
            # Crear nueva lectura
            _logger.info(f"🆕 === CREANDO NUEVA LECTURA DESDE PRINTTRACKER ===")
            
            valores = {
                'fecha': fecha_lectura,
                'serie': serie,
                'contador_bn': pt_bn,
                'contador_color': pt_color,
                'contador_scan': pt_scan,
                'contador_copy': pt_copy,
                'contador_fax': pt_fax,
                'fuente_origen': 'printtracker',
                'printtracker_meter_id': meter_record.id,
                'estado': 'validado'
            }
            
            nueva_lectura = self.create(valores)
            _logger.info(f"✅ Lectura creada desde PrintTracker: {nueva_lectura.display_name}")
            _logger.info(f"🔄 ===== FIN CREACIÓN DESDE PRINTTRACKER =====")
            
            return nueva_lectura
            
        except Exception as e:
            _logger.error(f"❌ Error creando desde PrintTracker: {str(e)}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return False

    @api.model
    def crear_lectura_manual(self, serie, fecha, contadores):
        """
        NUEVO: Método para crear lecturas manuales
        """
        try:
            _logger.info(f"✋ ===== CREANDO LECTURA MANUAL =====")
            _logger.info(f"✋ Serie: {serie}")
            _logger.info(f"✋ Fecha: {fecha}")
            _logger.info(f"✋ Contadores: {contadores}")
            
            # Verificar si ya existe lectura para esta fecha/serie
            existing_reading = self.search([
                ('fecha', '=', fecha),
                ('serie', '=', serie)
            ], limit=1)
            
            if existing_reading:
                _logger.warning(f"⚠️ Ya existe lectura para {serie} - {fecha}")
                return False
            
            # Crear lectura manual
            valores = {
                'fecha': fecha,
                'serie': serie,
                'contador_bn': contadores.get('bn', 0),
                'contador_color': contadores.get('color', 0),
                'contador_scan': contadores.get('scan', 0),
                'contador_copy': contadores.get('copy', 0),
                'contador_fax': contadores.get('fax', 0),
                'fuente_origen': 'manual',
                'estado': 'validado'
            }
            
            nueva_lectura = self.create(valores)
            _logger.info(f"✅ Lectura manual creada: {nueva_lectura.display_name}")
            
            return nueva_lectura
            
        except Exception as e:
            _logger.error(f"❌ Error creando lectura manual: {str(e)}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return False

    # ========================================
    # MÉTODOS COMPUTE (SIN CAMBIOS)
    # ========================================
    
    @api.depends('serie')
    def _compute_equipo_id(self):
        """Busca el equipo por serie"""
        for reading in self:
            if reading.serie:
                equipo = self.env['alquiler'].search([
                    ('serie', '=', reading.serie)
                ], limit=1)
                reading.equipo_id = equipo.id if equipo else False
            else:
                reading.equipo_id = False

    @api.depends('equipo_id')
    def _compute_equipo_info(self):
        """Cachea información básica del equipo"""
        for reading in self:
            if reading.equipo_id:
                equipo = reading.equipo_id
                reading.cliente_nombre = equipo.cliente_id.name if hasattr(equipo, 'cliente_id') and equipo.cliente_id else ''
                reading.modelo_equipo = equipo.name.name if hasattr(equipo, 'name') and equipo.name else ''
                reading.tipo_equipo = getattr(equipo, 'tipo_maquina_id', None)
            else:
                reading.cliente_nombre = ''
                reading.modelo_equipo = ''
                reading.tipo_equipo = None

    @api.depends('serie', 'fecha', 'contador_total', 'fuente_origen')
    def _compute_display_name(self):
        """Genera nombre descriptivo"""
        for reading in self:
            parts = []
            
            if reading.serie:
                parts.append(reading.serie)
            
            if reading.fecha:
                parts.append(reading.fecha.strftime('%Y-%m-%d'))
            
            if reading.contador_total:
                parts.append(f"({reading.contador_total:,} págs)")
            
            if reading.fuente_origen:
                fuente_display = dict(reading._fields['fuente_origen'].selection).get(reading.fuente_origen, '')
                parts.append(f"[{fuente_display}]")
            
            reading.display_name = " - ".join(parts) if parts else f"Lectura {reading.id or 'nueva'}"

    @api.depends('contador_bn', 'contador_color', 'contador_scan')
    def _compute_contador_total(self):
        """Calcula contador total"""
        for reading in self:
            reading.contador_total = (reading.contador_bn or 0) + (reading.contador_color or 0) + (reading.contador_scan or 0)

    @api.depends('fecha', 'serie', 'contador_bn', 'contador_color', 'contador_scan', 'contador_total')
    def _compute_incrementos(self):
        """Calcula incrementos respecto al día anterior"""
        for reading in self:
            if not reading.fecha or not reading.serie:
                reading.incremento_bn = 0
                reading.incremento_color = 0
                reading.incremento_scan = 0
                reading.incremento_total = 0
                continue
            
            # Buscar lectura del día anterior
            dia_anterior = reading.fecha - timedelta(days=1)
            lectura_anterior = self.search([
                ('serie', '=', reading.serie),
                ('fecha', '=', dia_anterior),
                ('estado', 'in', ['validado', 'aplicado'])
            ], limit=1)
            
            if lectura_anterior:
                reading.incremento_bn = (reading.contador_bn or 0) - (lectura_anterior.contador_bn or 0)
                reading.incremento_color = (reading.contador_color or 0) - (lectura_anterior.contador_color or 0)
                reading.incremento_scan = (reading.contador_scan or 0) - (lectura_anterior.contador_scan or 0)
                reading.incremento_total = (reading.contador_total or 0) - (lectura_anterior.contador_total or 0)
            else:
                # Primera lectura o día anterior no encontrado
                reading.incremento_bn = reading.contador_bn or 0
                reading.incremento_color = reading.contador_color or 0
                reading.incremento_scan = reading.contador_scan or 0
                reading.incremento_total = reading.contador_total or 0

    # ========================================
    # APLICACIÓN AL EQUIPO Y MÉTODOS DE UTILIDAD
    # ========================================

    def _aplicar_lectura_a_equipo(self, lectura):
        """
        SIMPLIFICADO: Aplica los contadores al equipo en alquiler
        SIN lógica de consolidación - aplicación directa
        """
        try:
            _logger.info(f"🚀 ===== APLICANDO LECTURA AL EQUIPO =====")
            _logger.info(f"📋 Lectura ID: {lectura.id}")
            _logger.info(f"📋 Serie: {lectura.serie}")
            _logger.info(f"📋 Fecha: {lectura.fecha}")
            _logger.info(f"📋 Fuente: {lectura.fuente_origen}")
            _logger.info(f"📋 Estado actual: {lectura.estado}")
            
            # Validación inicial - buscar equipo
            if not lectura.equipo_id:
                _logger.warning(f"⚠️ Buscando equipo por serie: {lectura.serie}")
                
                equipo = self.env['alquiler'].search([
                    ('serie', '=', lectura.serie)
                ], limit=1)
                
                if equipo:
                    _logger.info(f"✅ Equipo encontrado: ID={equipo.id}, Nombre={equipo.name}")
                    lectura.write({'equipo_id': equipo.id})
                else:
                    _logger.error(f"❌ No se encontró equipo para serie: {lectura.serie}")
                    lectura.write({
                        'estado': 'error',
                        'mensaje_error': f'No se encontró equipo para serie {lectura.serie}'
                    })
                    return False
            
            equipo = lectura.equipo_id
            _logger.info(f"🎯 Aplicando al equipo: {equipo.name} (ID: {equipo.id})")
            
            # Obtener valores actuales del equipo
            valores_actuales = {
                'contador_bn': getattr(equipo, 'contador_bn', 0) or 0,
                'contador_color': getattr(equipo, 'contador_color', 0) or 0,
                'contador_scan': getattr(equipo, 'contador_scan', 0) or 0,
            }
            
            _logger.info(f"📊 Valores actuales del equipo:")
            _logger.info(f"📊   - BN: {valores_actuales['contador_bn']}")
            _logger.info(f"📊   - Color: {valores_actuales['contador_color']}")
            _logger.info(f"📊   - Scan: {valores_actuales['contador_scan']}")
            
            # Valores de la lectura
            valores_lectura = {
                'contador_bn': lectura.contador_bn or 0,
                'contador_color': lectura.contador_color or 0,
                'contador_scan': lectura.contador_scan or 0,
            }
            
            _logger.info(f"📋 Valores de la lectura:")
            _logger.info(f"📋   - BN: {valores_lectura['contador_bn']}")
            _logger.info(f"📋   - Color: {valores_lectura['contador_color']}")
            _logger.info(f"📋   - Scan: {valores_lectura['contador_scan']}")
            
            # Preparar valores a actualizar
            valores_actualizar = {}
            cambios_realizados = []
            
            # REGLA SIMPLE: Solo actualizar si el valor de la lectura es mayor
            for contador in ['contador_bn', 'contador_color', 'contador_scan']:
                valor_actual = valores_actuales[contador]
                valor_lectura = valores_lectura[contador]
                
                if valor_lectura > valor_actual:
                    valores_actualizar[contador] = valor_lectura
                    cambios_realizados.append(f"{contador}: {valor_actual} → {valor_lectura}")
                    _logger.info(f"✅ Actualización: {contador}: {valor_actual} → {valor_lectura}")
                elif valor_lectura < valor_actual:
                    _logger.warning(f"⚠️ Valor menor ignorado: {contador}: lectura({valor_lectura}) < equipo({valor_actual})")
                else:
                    _logger.info(f"ℹ️ Sin cambio: {contador}: {valor_actual}")
            
            # Siempre actualizar fecha
            valores_actualizar['fecha_ultima_actualizacion'] = fields.Datetime.now()
            
            # Aplicar actualizaciones
            if len(valores_actualizar) > 1:  # Más que solo la fecha
                _logger.info(f"🔄 Aplicando {len(valores_actualizar)-1} actualizaciones...")
                _logger.info(f"🔄 Cambios: {cambios_realizados}")
                
                try:
                    equipo.sudo().write(valores_actualizar)
                    _logger.info(f"✅ Contadores actualizados exitosamente")
                    
                    lectura.write({
                        'aplicado_a_equipo': True,
                        'fecha_aplicacion': fields.Datetime.now(),
                        'estado': 'aplicado',
                        'mensaje_error': None
                    })
                    
                    _logger.info(f"✅ Estado actualizado a 'aplicado'")
                    return True
                    
                except Exception as e:
                    _logger.error(f"❌ Error escribiendo en equipo: {str(e)}")
                    lectura.write({
                        'estado': 'error',
                        'mensaje_error': f'Error actualizando equipo: {str(e)}'
                    })
                    return False
            else:
                _logger.info(f"ℹ️ No hay cambios de contadores")
                
                lectura.write({
                    'aplicado_a_equipo': True,
                    'fecha_aplicacion': fields.Datetime.now(),
                    'estado': 'aplicado',
                    'mensaje_error': None
                })
                
                _logger.info(f"✅ Marcado como aplicado (sin cambios)")
                return True
                
        except Exception as e:
            _logger.error(f"❌ ERROR CRÍTICO aplicando lectura: {str(e)}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            
            try:
                lectura.write({
                    'estado': 'error',
                    'mensaje_error': f'Error crítico: {str(e)}'
                })
            except:
                _logger.error(f"❌ No se pudo actualizar estado de error")
            
            return False

    @api.model
    def procesar_lecturas_pendientes(self, dias_atras=1):
        """
        SIMPLIFICADO: Procesa lecturas pendientes de aplicar
        """
        try:
            fecha_inicio = date.today() - timedelta(days=dias_atras)
            
            _logger.info(f"🔄 ===== PROCESANDO LECTURAS PENDIENTES =====")
            _logger.info(f"📅 Desde: {fecha_inicio} hasta: {date.today()}")
            
            lecturas_pendientes = self.search([
                ('fecha', '>=', fecha_inicio),
                ('estado', '=', 'validado'),
                ('aplicado_a_equipo', '=', False)
            ])
            
            _logger.info(f"📊 Lecturas pendientes: {len(lecturas_pendientes)}")
            
            if not lecturas_pendientes:
                _logger.info(f"ℹ️ No hay lecturas pendientes")
                return {'procesadas': 0, 'exitosas': 0, 'errores': 0}
            
            exitosas = 0
            errores = 0
            
            for lectura in lecturas_pendientes:
                _logger.info(f"🔄 Procesando: {lectura.serie} - {lectura.fecha}")
                
                if self._aplicar_lectura_a_equipo(lectura):
                    exitosas += 1
                    _logger.info(f"✅ Aplicada: {lectura.serie}")
                else:
                    errores += 1
                    _logger.error(f"❌ Error: {lectura.serie}")
            
            _logger.info(f"🎯 Procesamiento completado: {exitosas} exitosas, {errores} errores")
            
            return {
                'procesadas': len(lecturas_pendientes),
                'exitosas': exitosas,
                'errores': errores
            }
            
        except Exception as e:
            _logger.error(f"❌ Error procesando pendientes: {str(e)}")
            return {'procesadas': 0, 'exitosas': 0, 'errores': 1}

    def action_diagnostico_sistema(self):
        """
        SIMPLIFICADO: Diagnóstico del sistema PrintTracker
        """
        try:
            _logger.info(f"🔍 ===== INICIANDO DIAGNÓSTICO =====")
            
            # Datos básicos
            printrackers = self.search([('fuente_origen', '=', 'printtracker')])
            manuales = self.search([('fuente_origen', '=', 'manual')])
            meters = self.env['printtracker.meter'].search([])
            
            # Mensaje de diagnóstico
            mensaje = "=== DIAGNÓSTICO PRINTTRACKER ===\n\n"
            
            mensaje += "📊 ESTADÍSTICAS:\n"
            mensaje += f"• Lecturas PrintTracker: {len(printrackers)}\n"
            mensaje += f"• Lecturas manuales: {len(manuales)}\n"
            mensaje += f"• Meters originales: {len(meters)}\n\n"
            
            # Series
            series_pt = set(printrackers.mapped('serie'))
            series_manual = set(manuales.mapped('serie'))
            
            mensaje += "📟 SERIES:\n"
            mensaje += f"• Series PrintTracker: {len(series_pt)}\n"
            mensaje += f"• Series manuales: {len(series_manual)}\n"
            mensaje += f"• Total únicas: {len(series_pt | series_manual)}\n\n"
            
            # Estados
            for fuente, lecturas in [('PrintTracker', printrackers), ('Manual', manuales)]:
                if lecturas:
                    mensaje += f"📊 ESTADOS {fuente.upper()}:\n"
                    for estado in ['borrador', 'validado', 'aplicado', 'error']:
                        count = len(lecturas.filtered(lambda l: l.estado == estado))
                        if count > 0:
                            mensaje += f"  • {estado}: {count}\n"
                    mensaje += "\n"
            
            # Problemas
            mensaje += "🔍 PROBLEMAS:\n"
            
            sin_equipo = (printrackers | manuales).filtered(lambda l: not l.equipo_id)
            en_error = (printrackers | manuales).filtered(lambda l: l.estado == 'error')
            pendientes = (printrackers | manuales).filtered(
                lambda l: l.estado == 'validado' and not l.aplicado_a_equipo
            )
            
            if sin_equipo:
                mensaje += f"• {len(sin_equipo)} sin equipo asociado\n"
            if en_error:
                mensaje += f"• {len(en_error)} en estado error\n"
            if pendientes:
                mensaje += f"• {len(pendientes)} pendientes aplicar\n"
            
            if not any([sin_equipo, en_error, pendientes]):
                mensaje += "• No se detectaron problemas\n"
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Diagnóstico PrintTracker',
                    'message': mensaje,
                    'type': 'info',
                    'sticky': True
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error en diagnóstico: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error: {str(e)}',
                    'type': 'danger'
                }
            }

    def action_aplicar_manual(self):
        """Acción manual para aplicar lectura"""
        self.ensure_one()
        
        if self.estado == 'aplicado':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Esta lectura ya fue aplicada',
                    'type': 'warning'
                }
            }
        
        success = self._aplicar_lectura_a_equipo(self)
        
        if success:
            mensaje = f'✅ Lectura aplicada exitosamente\nSerie: {self.serie}'
            tipo = 'success'
        else:
            mensaje = f'❌ Error aplicando lectura\nSerie: {self.serie}\nError: {self.mensaje_error or "Error desconocido"}'
            tipo = 'danger'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': mensaje,
                'type': tipo
            }
        }

    def action_view_equipo(self):
        """Ver equipo relacionado"""
        self.ensure_one()
        
        if not self.equipo_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'No se encontró equipo para esta serie',
                    'type': 'warning'
                }
            }
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Equipo - {self.serie}',
            'res_model': 'alquiler',
            'res_id': self.equipo_id.id,
            'view_mode': 'form',
            'target': 'current'
        }

    @api.model
    def obtener_estadisticas(self, dias=7):
        """
        Estadísticas simplificadas del sistema
        """
        try:
            fecha_inicio = date.today() - timedelta(days=dias)
            lecturas = self.search([('fecha', '>=', fecha_inicio)])
            
            stats = {
                'total_lecturas': len(lecturas),
                'por_fuente': {
                    'printtracker': len(lecturas.filtered(lambda l: l.fuente_origen == 'printtracker')),
                    'manual': len(lecturas.filtered(lambda l: l.fuente_origen == 'manual'))
                },
                'por_estado': {
                    'validado': len(lecturas.filtered(lambda l: l.estado == 'validado')),
                    'aplicado': len(lecturas.filtered(lambda l: l.estado == 'aplicado')),
                    'error': len(lecturas.filtered(lambda l: l.estado == 'error'))
                },
                'aplicadas_equipos': len(lecturas.filtered('aplicado_a_equipo')),
                'series_unicas': len(set(lecturas.mapped('serie')))
            }
            
            return stats
            
        except Exception as e:
            _logger.error(f"❌ Error generando estadísticas: {str(e)}")
            return {}