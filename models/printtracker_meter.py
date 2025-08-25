from odoo import models, fields, api
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class PrintTrackerMeter(models.Model):
    _name = 'printtracker.meter'
    _description = 'Lecturas de Medidores PrintTracker'
    _order = 'reading_date desc'
    _rec_name = 'display_name'

    # Identificación
    pt_meter_id = fields.Char('ID PrintTracker', required=True, index=True)
    device_id = fields.Many2one('alquiler', string='Equipo',
                               required=True, index=True)
    
    # Fecha y estado
    reading_date = fields.Datetime('Fecha de Lectura', required=True, index=True)
    console_status = fields.Char('Estado Consola')
    
    # Contadores principales (structure 'default' de PrintTracker)
    total_pages_life = fields.Integer('Total Páginas')
    black_pages_life = fields.Integer('Páginas Negras')
    color_pages_life = fields.Integer('Páginas Color')
    
    # NUEVOS CONTADORES específicos disponibles en PrintTracker
    scan_pages = fields.Integer('Páginas Escaneadas')
    copy_pages = fields.Integer('Páginas Copiadas')
    fax_pages = fields.Integer('Páginas de Fax')
    print_pages = fields.Integer('Páginas Impresas')
    
    # Contadores equivalentes (para facturación si PrintTracker los provee)
    total_pages_equiv = fields.Integer('Total Páginas (Equiv)')
    black_pages_equiv = fields.Integer('Páginas Negras (Equiv)')
    color_pages_equiv = fields.Integer('Páginas Color (Equiv)')
    
    # Control de sincronización
    last_sync = fields.Datetime('Última Sincronización', readonly=True)
    sync_source = fields.Selection([
        ('api', 'API PrintTracker'),
        ('manual', 'Manual'),
        ('import', 'Importación')
    ], string='Origen', default='api')
    
    # Campos calculados para análisis
    pages_increment = fields.Integer('Incremento Total', 
                                   compute='_compute_increments', store=True)
    black_increment = fields.Integer('Incremento Negro',
                                    compute='_compute_increments', store=True)
    color_increment = fields.Integer('Incremento Color',
                                    compute='_compute_increments', store=True)
    scan_increment = fields.Integer('Incremento Scan',
                                   compute='_compute_increments', store=True)
    
    # Campo de display para el tree view
    display_name = fields.Char('Nombre', compute='_compute_display_name', store=True)
    
    # Campos de análisis adicionales
    daily_usage = fields.Float('Uso Diario', compute='_compute_daily_usage', store=False)
    is_current = fields.Boolean('Es Lectura Actual', 
                               help='Indica si es la lectura más reciente del dispositivo')
    
    # Constrains para evitar duplicados
    _sql_constraints = [
        ('unique_pt_meter', 'UNIQUE(pt_meter_id)', 
         'ID de medidor PrintTracker debe ser único'),
        ('unique_device_date', 'UNIQUE(device_id, reading_date)', 
         'Solo puede haber una lectura por dispositivo por fecha/hora exacta')
    ]

    @api.depends('device_id', 'reading_date', 'total_pages_life')
    def _compute_display_name(self):
        """Genera nombre descriptivo para el medidor"""
        for meter in self:
            if meter.device_id and meter.reading_date:
                device_name = meter.device_id.serie or f"Equipo {meter.device_id.id}"
                date_str = meter.reading_date.strftime('%Y-%m-%d %H:%M')
                total = meter.total_pages_life or 0
                meter.display_name = f"{device_name} - {date_str} ({total:,} págs)"
            else:
                meter.display_name = f"Medidor {meter.id or 'nuevo'}"

    @api.depends('device_id', 'total_pages_life', 'black_pages_life', 'color_pages_life', 'scan_pages')
    def _compute_increments(self):
        """
        SIMPLIFICADO: Calcula incrementos respecto a la lectura anterior
        Solo análisis, no actualiza equipos
        """
        for meter in self:
            if not meter.device_id or not meter.reading_date:
                meter.pages_increment = 0
                meter.black_increment = 0
                meter.color_increment = 0
                meter.scan_increment = 0
                continue
                
            # Buscar lectura anterior del mismo dispositivo
            previous_meter = self.search([
                ('device_id', '=', meter.device_id.id),
                ('reading_date', '<', meter.reading_date)
            ], limit=1, order='reading_date desc')
            
            if previous_meter:
                # Calcular incrementos
                meter.pages_increment = (meter.total_pages_life or 0) - (previous_meter.total_pages_life or 0)
                meter.black_increment = (meter.black_pages_life or 0) - (previous_meter.black_pages_life or 0)
                meter.color_increment = (meter.color_pages_life or 0) - (previous_meter.color_pages_life or 0)
                meter.scan_increment = (meter.scan_pages or 0) - (previous_meter.scan_pages or 0)
                
                _logger.debug(f"📊 Incrementos calculados para {meter.device_id.serie}: "
                            f"Total={meter.pages_increment}, BN={meter.black_increment}, "
                            f"Color={meter.color_increment}, Scan={meter.scan_increment}")
            else:
                # Primera lectura - usar valores absolutos
                meter.pages_increment = meter.total_pages_life or 0
                meter.black_increment = meter.black_pages_life or 0
                meter.color_increment = meter.color_pages_life or 0
                meter.scan_increment = meter.scan_pages or 0
                
                _logger.debug(f"📊 Primera lectura para {meter.device_id.serie}: "
                            f"Total={meter.pages_increment}")

    @api.depends('device_id', 'reading_date')
    def _compute_daily_usage(self):
        """Calcula uso diario promedio basado en lecturas anteriores"""
        for meter in self:
            if not meter.device_id or not meter.reading_date:
                meter.daily_usage = 0
                continue
                
            # Buscar lectura del día anterior (±12 horas)
            yesterday = meter.reading_date - timedelta(days=1)
            prev_meter = self.search([
                ('device_id', '=', meter.device_id.id),
                ('reading_date', '>=', yesterday - timedelta(hours=12)),
                ('reading_date', '<=', yesterday + timedelta(hours=12))
            ], limit=1)
            
            if prev_meter:
                days_diff = (meter.reading_date - prev_meter.reading_date).days
                if days_diff > 0:
                    total_increment = (meter.total_pages_life or 0) - (prev_meter.total_pages_life or 0)
                    meter.daily_usage = total_increment / days_diff
                else:
                    meter.daily_usage = 0
            else:
                meter.daily_usage = 0

    @api.model
    def create(self, vals):
        """Override create para marcar como lectura actual Y crear lectura diaria"""
        meter = super().create(vals)
        meter._update_current_flag()
        
        # NUEVO: Crear o actualizar lectura diaria automáticamente
        meter._crear_o_actualizar_lectura_diaria()
        
        return meter
    @api.model
    def generar_lecturas_diarias_desde_meters(self, dias_atras=1):
        """
        NUEVO: Genera lecturas diarias desde meters existentes
        Útil para reprocesar datos o catch-up
        """
        try:
            fecha_inicio = date.today() - timedelta(days=dias_atras)
            
            _logger.info(f"🔄 === GENERANDO LECTURAS DIARIAS ===")
            _logger.info(f"📅 Desde: {fecha_inicio}")
            
            # Buscar todos los meters del período
            meters = self.env['printtracker.meter'].search([
                ('reading_date', '>=', datetime.combine(fecha_inicio, datetime.min.time()))
            ], order='device_id, reading_date')
            
            _logger.info(f"📊 Meters encontrados: {len(meters)}")
            
            if not meters:
                _logger.info("ℹ️ No hay meters para procesar")
                return {'creadas': 0, 'actualizadas': 0, 'errores': 0}
            
            # Agrupar por dispositivo y fecha
            from collections import defaultdict
            meters_by_device_date = defaultdict(list)
            
            for meter in meters:
                if meter.device_id and meter.reading_date:
                    fecha_key = meter.reading_date.date()
                    device_key = meter.device_id.id
                    meters_by_device_date[(device_key, fecha_key)].append(meter)
            
            _logger.info(f"📊 Combinaciones dispositivo-fecha: {len(meters_by_device_date)}")
            
            creadas = 0
            actualizadas = 0
            errores = 0
            
            for (device_id, fecha), device_meters in meters_by_device_date.items():
                try:
                    # Tomar el meter más reciente del día para ese dispositivo
                    latest_meter = max(device_meters, key=lambda m: m.reading_date)
                    
                    _logger.info(f"🔄 Procesando: Dispositivo {device_id}, Fecha {fecha}")
                    _logger.info(f"🔄 Meter seleccionado: {latest_meter.id} ({latest_meter.reading_date})")
                    
                    # Verificar si ya existe lectura diaria
                    existing = self.env['printtracker.daily.reading'].search([
                        ('serie', '=', latest_meter.device_id.serie),
                        ('fecha', '=', fecha)
                    ], limit=1)
                    
                    if existing:
                        if existing.fuente_origen == 'manual':
                            _logger.info(f"⏭️ Saltando: existe lectura manual para {latest_meter.device_id.serie} - {fecha}")
                            continue
                        
                        # Actualizar si es PrintTracker y este meter es más reciente
                        if (not existing.printtracker_meter_id or 
                            latest_meter.reading_date > existing.printtracker_meter_id.reading_date):
                            
                            existing.write({
                                'contador_bn': latest_meter.black_pages_life or 0,
                                'contador_color': latest_meter.color_pages_life or 0,
                                'contador_scan': latest_meter.scan_pages or 0,
                                'contador_copy': latest_meter.copy_pages or 0,
                                'contador_fax': latest_meter.fax_pages or 0,
                                'printtracker_meter_id': latest_meter.id,
                                'fecha_procesamiento': fields.Datetime.now()
                            })
                            
                            actualizadas += 1
                            _logger.info(f"📝 Actualizada: {latest_meter.device_id.serie} - {fecha}")
                    else:
                        # Crear nueva lectura
                        nueva_lectura = self.env['printtracker.daily.reading'].create({
                            'fecha': fecha,
                            'serie': latest_meter.device_id.serie,
                            'contador_bn': latest_meter.black_pages_life or 0,
                            'contador_color': latest_meter.color_pages_life or 0,
                            'contador_scan': latest_meter.scan_pages or 0,
                            'contador_copy': latest_meter.copy_pages or 0,
                            'contador_fax': latest_meter.fax_pages or 0,
                            'fuente_origen': 'printtracker',
                            'printtracker_meter_id': latest_meter.id,
                            'estado': 'validado'
                        })
                        
                        creadas += 1
                        _logger.info(f"🆕 Creada: {latest_meter.device_id.serie} - {fecha}")
                    
                except Exception as e:
                    errores += 1
                    _logger.error(f"❌ Error procesando dispositivo {device_id}: {e}")
            
            _logger.info(f"✅ Generación completada: {creadas} creadas, {actualizadas} actualizadas, {errores} errores")
            
            return {
                'creadas': creadas,
                'actualizadas': actualizadas,
                'errores': errores,
                'total_procesadas': creadas + actualizadas
            }
            
        except Exception as e:
            _logger.error(f"❌ Error generando lecturas diarias: {e}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return {'creadas': 0, 'actualizadas': 0, 'errores': 1}

    def action_generar_lecturas_diarias(self):
        """
        NUEVO: Acción manual para generar lecturas diarias desde meters
        """
        try:
            _logger.info("✋ Generación manual de lecturas diarias solicitada")
            
            resultado = self.generar_lecturas_diarias_desde_meters(dias_atras=2)
            
            mensaje = f"""✅ GENERACIÓN DE LECTURAS COMPLETADA

    📊 RESULTADOS:
    • Lecturas creadas: {resultado['creadas']}
    • Lecturas actualizadas: {resultado['actualizadas']}
    • Errores: {resultado['errores']}
    • Total procesadas: {resultado['total_procesadas']}

    📅 Período: Últimos 2 días

    Las lecturas están listas para aplicar a equipos."""
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Generación de Lecturas',
                    'message': mensaje,
                    'type': 'success' if resultado['errores'] == 0 else 'warning',
                    'sticky': True
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'❌ Error: {str(e)}',
                    'type': 'danger'
                }
            }

    def _crear_o_actualizar_lectura_diaria(self):
        """
        CORREGIDO: Lógica mejorada para crear lecturas diarias
        """
        try:
            self.ensure_one()
            _logger.info(f"🔄 === PROCESANDO METER A LECTURA DIARIA ===")
            _logger.info(f"🔄 Serie: {self.device_id.serie}")
            _logger.info(f"🔄 Fecha meter: {self.reading_date}")
            
            if not self.device_id or not self.device_id.serie:
                _logger.error("❌ Meter sin dispositivo o serie")
                return False
            
            # EXTRAER SOLO LA FECHA (sin hora)
            fecha_lectura = self.reading_date.date() if self.reading_date else date.today()
            serie = self.device_id.serie
            
            _logger.info(f"🔄 Fecha objetivo: {fecha_lectura}")
            
            # BUSCAR LECTURA EXISTENTE DEL DÍA
            existing_reading = self.env['printtracker.daily.reading'].search([
                ('fecha', '=', fecha_lectura),
                ('serie', '=', serie)
            ], limit=1)
            
            # VALORES DEL METER ACTUAL
            valores_meter = {
                'contador_bn': self.black_pages_life or 0,
                'contador_color': self.color_pages_life or 0,
                'contador_scan': self.scan_pages or 0,
                'contador_copy': self.copy_pages or 0,
                'contador_fax': self.fax_pages or 0,
            }
            
            if existing_reading:
                _logger.info(f"📋 Lectura existente encontrada: {existing_reading.fuente_origen}")
                
                # REGLA 1: NO SOBRESCRIBIR LECTURAS MANUALES
                if existing_reading.fuente_origen == 'manual':
                    _logger.info(f"🚫 Lectura manual existente - NO se actualiza")
                    return existing_reading
                
                # REGLA 2: ACTUALIZAR SOLO SI ES MÁS RECIENTE
                elif existing_reading.fuente_origen == 'printtracker':
                    # Comparar si este meter es más reciente que el ya registrado
                    if (existing_reading.printtracker_meter_id and 
                        existing_reading.printtracker_meter_id.reading_date >= self.reading_date):
                        _logger.info(f"⏭️ Meter más antiguo - no se actualiza")
                        return existing_reading
                    
                    # Este meter es más reciente - actualizar
                    _logger.info(f"📝 Actualizando con meter más reciente...")
                    existing_reading.write({
                        **valores_meter,
                        'printtracker_meter_id': self.id,
                        'fecha_procesamiento': fields.Datetime.now()
                    })
                    _logger.info(f"✅ Lectura actualizada")
                    return existing_reading
            
            # CREAR NUEVA LECTURA
            _logger.info(f"🆕 Creando nueva lectura diaria...")
            nueva_lectura = self.env['printtracker.daily.reading'].create({
                'fecha': fecha_lectura,
                'serie': serie,
                **valores_meter,
                'fuente_origen': 'printtracker',
                'printtracker_meter_id': self.id,
                'estado': 'validado'  # Listo para aplicar
            })
            
            _logger.info(f"✅ Nueva lectura creada: ID={nueva_lectura.id}")
            return nueva_lectura
            
        except Exception as e:
            _logger.error(f"❌ Error en trigger de lectura diaria: {e}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return False

    def write(self, vals):
        """Override write para marcar como lectura actual"""
        result = super().write(vals)
        if 'reading_date' in vals:
            self._update_current_flag()
        return result

    def _update_current_flag(self):
        """Actualiza el flag is_current para el dispositivo"""
        for meter in self:
            if meter.device_id:
                # Desmarcar todas las lecturas del dispositivo
                all_meters = self.search([('device_id', '=', meter.device_id.id)])
                all_meters.write({'is_current': False})
                
                # Marcar la más reciente como actual
                latest_meter = self.search([
                    ('device_id', '=', meter.device_id.id)
                ], limit=1, order='reading_date desc')
                
                if latest_meter:
                    latest_meter.write({'is_current': True})

    @api.model
    def get_latest_for_device(self, device_id):
        """Obtiene la lectura más reciente para un equipo"""
        return self.search([
            ('device_id', '=', device_id)
        ], limit=1, order='reading_date desc')

    @api.model
    def get_latest_for_all_devices(self):
        """Obtiene las lecturas más recientes de todos los dispositivos"""
        return self.search([('is_current', '=', True)])

    def get_reading_summary(self):
        """Retorna resumen de la lectura en formato dict"""
        self.ensure_one()
        return {
            'device_serial': self.device_id.serie if self.device_id else 'N/A',
            'device_id': self.device_id.id if self.device_id else None,
            'reading_date': self.reading_date,
            'console_status': self.console_status,
            'counters': {
                'total_pages': self.total_pages_life,
                'black_pages': self.black_pages_life,
                'color_pages': self.color_pages_life,
                'scan_pages': self.scan_pages,
                'copy_pages': self.copy_pages,
                'fax_pages': self.fax_pages,
                'print_pages': self.print_pages
            },
            'increments': {
                'total': self.pages_increment,
                'black': self.black_increment,
                'color': self.color_increment,
                'scan': self.scan_increment
            },
            'daily_usage': self.daily_usage,
            'is_current': self.is_current
        }

    def get_device_usage_trend(self, days=30):
        """
        Obtiene tendencia de uso del dispositivo en los últimos N días
        """
        self.ensure_one()
        
        if not self.device_id:
            return {}
        
        # Fecha límite
        start_date = self.reading_date - timedelta(days=days)
        
        # Obtener lecturas del período
        meters = self.search([
            ('device_id', '=', self.device_id.id),
            ('reading_date', '>=', start_date),
            ('reading_date', '<=', self.reading_date)
        ], order='reading_date asc')
        
        if len(meters) < 2:
            return {'error': 'Insuficientes datos para calcular tendencia'}
        
        # Calcular estadísticas
        first_meter = meters[0]
        last_meter = meters[-1]
        
        days_period = (last_meter.reading_date - first_meter.reading_date).days
        if days_period <= 0:
            return {'error': 'Período inválido'}
        
        total_increment = (last_meter.total_pages_life or 0) - (first_meter.total_pages_life or 0)
        black_increment = (last_meter.black_pages_life or 0) - (first_meter.black_pages_life or 0)
        color_increment = (last_meter.color_pages_life or 0) - (first_meter.color_pages_life or 0)
        scan_increment = (last_meter.scan_pages or 0) - (first_meter.scan_pages or 0)
        
        return {
            'period_days': days_period,
            'total_increment': total_increment,
            'daily_average': total_increment / days_period if days_period > 0 else 0,
            'increments': {
                'black': black_increment,
                'color': color_increment,
                'scan': scan_increment
            },
            'daily_averages': {
                'black': black_increment / days_period if days_period > 0 else 0,
                'color': color_increment / days_period if days_period > 0 else 0,
                'scan': scan_increment / days_period if days_period > 0 else 0
            },
            'readings_count': len(meters),
            'first_reading': first_meter.reading_date,
            'last_reading': last_meter.reading_date
        }

    @api.model
    def get_devices_without_recent_readings(self, days=7):
        """
        Obtiene dispositivos que no han reportado en los últimos N días
        Útil para detectar equipos offline
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Obtener todos los dispositivos con lecturas
        devices_with_readings = self.env['alquiler'].search([
            ('pt_device_id', '!=', False),
            ('pt_device_id', '!=', '')
        ])
                
        offline_devices = []
        
        for device in devices_with_readings:
            latest_meter = self.search([
                ('device_id', '=', device.id)
            ], limit=1, order='reading_date desc')
            
            if not latest_meter or latest_meter.reading_date < cutoff_date:
                offline_devices.append({
                    'device_id': device.id,
                    'serie': device.serie,
                    'last_reading': latest_meter.reading_date if latest_meter else None,
                    'days_offline': (datetime.now() - latest_meter.reading_date).days if latest_meter else 999
                })
        
        return offline_devices

    @api.model
    def cleanup_old_readings(self, days_to_keep=365):
        """
        UTILIDAD: Limpia lecturas antiguas para mantener rendimiento
        Mantiene solo las lecturas de los últimos N días
        """
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        old_meters = self.search([
            ('reading_date', '<', cutoff_date),
            ('is_current', '=', False)  # No eliminar lecturas actuales
        ])
        
        count = len(old_meters)
        old_meters.unlink()
        
        _logger.info(f"🗑️ Limpieza: {count} lecturas antiguas eliminadas (anteriores a {cutoff_date.date()})")
        
        return {
            'deleted_count': count,
            'cutoff_date': cutoff_date
        }

    def action_view_device_history(self):
        """Acción para ver el histórico del dispositivo"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Histórico de Medidores - {self.device_id.serie}',
            'res_model': 'printtracker.meter',
            'view_mode': 'tree,form',
            'domain': [('device_id', '=', self.device_id.id)],
            'context': {
                'default_device_id': self.device_id.id,
                'search_default_device_id': self.device_id.id
            },
            'target': 'current'
        }

    def action_view_usage_analysis(self):
        """Acción para ver análisis de uso del dispositivo"""
        self.ensure_one()
        
        # Calcular estadísticas básicas
        trend_30 = self.get_device_usage_trend(30)
        
        message = f"""
        📊 ANÁLISIS DE USO - {self.device_id.serie}
        
        📅 Lectura actual: {self.reading_date.strftime('%Y-%m-%d %H:%M')}
        📈 Total páginas: {self.total_pages_life:,}
        
        🖤 Negro: {self.black_pages_life:,} páginas
        🎨 Color: {self.color_pages_life:,} páginas  
        📄 Scan: {self.scan_pages:,} páginas
        📋 Copy: {self.copy_pages:,} páginas
        📠 Fax: {self.fax_pages:,} páginas
        
        📊 Uso diario promedio: {self.daily_usage:.1f} páginas/día
        
        📈 Tendencia últimos 30 días:
        - Incremento total: {trend_30.get('total_increment', 0):,} páginas
        - Promedio diario: {trend_30.get('daily_average', 0):.1f} páginas/día
        """
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Análisis de Uso',
                'message': message,
                'type': 'info',
                'sticky': True
            }
        }