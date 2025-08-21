from odoo import models, fields, api
import logging
from datetime import datetime, timedelta, date

_logger = logging.getLogger(__name__)


class PrintTrackerDailyReading(models.Model):
    _name = 'printtracker.daily.reading'
    _description = 'Lecturas Diarias Consolidadas PrintTracker'
    _order = 'fecha desc, serie'
    _rec_name = 'display_name'

    # Identificación principal
    fecha = fields.Date('Fecha', required=True, index=True)
    serie = fields.Char('Serie del Equipo', required=True, index=True)
    equipo_id = fields.Many2one('alquiler', string='Equipo', 
                               compute='_compute_equipo_id', store=True, index=True)
    
    # Contadores consolidados finales
    contador_bn = fields.Integer('Contador B/N', default=0)
    contador_color = fields.Integer('Contador Color', default=0) 
    contador_scan = fields.Integer('Contador Scan', default=0)
    contador_copy = fields.Integer('Contador Copy', default=0)
    contador_fax = fields.Integer('Contador Fax', default=0)
    contador_total = fields.Integer('Contador Total', compute='_compute_contador_total', store=True)
    
    # Información de origen de los datos
    fuente_origen = fields.Selection([
        ('correo', 'Contador Automático (Correo)'),
        ('printtracker', 'PrintTracker API'),
        ('consolidado', 'Consolidado (Ambas Fuentes)'),
        ('manual', 'Manual')
    ], string='Fuente de Origen', required=True, index=True)
    
    # Referencias a registros de origen
    contador_automatico_id = fields.Many2one('contador.automatico', 
                                           string='Registro Contador Automático')
    printtracker_meter_id = fields.Many2one('printtracker.meter', 
                                          string='Registro PrintTracker')
    
    # Información de consolidación
    fecha_procesamiento = fields.Datetime('Fecha de Procesamiento', 
                                         default=fields.Datetime.now, readonly=True)
    consolidado_por = fields.Many2one('res.users', string='Consolidado Por', 
                                    default=lambda self: self.env.user, readonly=True)
    
    # Detalles de la consolidación
    conflicto_detectado = fields.Boolean('Conflicto Detectado', default=False,
                                        help='Si hubo conflicto entre fuentes de datos')
    detalle_conflicto = fields.Text('Detalle del Conflicto')
    resolucion_aplicada = fields.Selection([
        ('mayor_valor', 'Mayor Valor'),
        ('printtracker_prioridad', 'Prioridad PrintTracker'),
        ('correo_prioridad', 'Prioridad Correo'),
        ('manual', 'Resolución Manual')
    ], string='Resolución Aplicada')
    
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
    ], string='Estado', default='borrador', index=True)
    
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
    
    # Constrains
    _sql_constraints = [
        ('unique_fecha_serie', 'UNIQUE(fecha, serie)', 
         'Solo puede haber una lectura consolidada por fecha y serie'),
        ('positive_counters', 'CHECK(contador_bn >= 0 AND contador_color >= 0 AND contador_scan >= 0)', 
         'Los contadores deben ser positivos'),
        ('valid_date', 'CHECK(fecha <= CURRENT_DATE)', 
         'La fecha no puede ser futura')
    ]

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

    @api.model
    def crear_desde_contador_automatico(self, registro_contador):
        """
        Crea una lectura diaria desde un registro de contador.automatico
        CORREGIDO: Actualiza registro de PrintTracker si ya existe
        """
        try:
            _logger.info(f"📧 Creando lectura desde contador automático: {registro_contador.serie_detectada}")
            
            if not registro_contador.serie_detectada:
                _logger.error("❌ Registro sin serie detectada")
                return False
            
            # Usar fecha de procesamiento como fecha de la lectura
            fecha_lectura = registro_contador.fecha_procesamiento.date() if registro_contador.fecha_procesamiento else date.today()
            
            # Verificar si ya existe
            existing = self.search([
                ('fecha', '=', fecha_lectura),
                ('serie', '=', registro_contador.serie_detectada)
            ], limit=1)
            
            if existing:
                if existing.fuente_origen == 'printtracker':
                    # CASO 1: ACTUALIZAR registro de PrintTracker con datos de correo
                    _logger.info(f"📧 Actualizando registro de PrintTracker con datos de correo: {registro_contador.serie_detectada} - {fecha_lectura}")
                    return self._actualizar_lectura_printtracker_con_correo(existing, registro_contador)
                else:
                    # CASO 2: Ya existe correo, no duplicar
                    _logger.warning(f"⚠️ Ya existe lectura de correo para {registro_contador.serie_detectada} en {fecha_lectura}")
                    return existing
            
            # CASO 3: No existe registro, crear nuevo
            _logger.info(f"🆕 Creando nuevo registro desde correo: {registro_contador.serie_detectada} - {fecha_lectura}")
            
            valores = {
                'fecha': fecha_lectura,
                'serie': registro_contador.serie_detectada,
                'contador_bn': registro_contador.contador_bn_detectado or 0,
                'contador_color': registro_contador.contador_color_detectado or 0,
                'contador_scan': registro_contador.contador_scan_detectado or 0,
                'fuente_origen': 'correo',
                'contador_automatico_id': registro_contador.id,
                'estado': 'validado'
            }
            
            nueva_lectura = self.create(valores)
            _logger.info(f"✅ Lectura creada desde correo: {nueva_lectura.display_name}")
            
            return nueva_lectura
            
        except Exception as e:
            _logger.error(f"❌ Error creando lectura desde contador automático: {e}")
            return False

    def _actualizar_lectura_printtracker_con_correo(self, lectura_pt, registro_contador):
        """
        NUEVO: Actualiza registro de PrintTracker existente con datos de correo
        """
        try:
            _logger.info(f"📧 === ACTUALIZANDO PRINTTRACKER CON CORREO ===")
            _logger.info(f"🔄 PrintTracker actual: BN={lectura_pt.contador_bn}, Color={lectura_pt.contador_color}, Scan={lectura_pt.contador_scan}")
            _logger.info(f"📧 Correo: BN={registro_contador.contador_bn_detectado}, Color={registro_contador.contador_color_detectado}, Scan={registro_contador.contador_scan_detectado}")
            
            # Preparar valores a actualizar
            valores_actualizar = {}
            
            # REGLA: Si PrintTracker tiene 0 en algún contador, usar valor de correo
            if lectura_pt.contador_bn == 0 and (registro_contador.contador_bn_detectado or 0) > 0:
                valores_actualizar['contador_bn'] = registro_contador.contador_bn_detectado
                _logger.info(f"✅ Actualizando BN: 0 → {registro_contador.contador_bn_detectado}")
            
            if lectura_pt.contador_color == 0 and (registro_contador.contador_color_detectado or 0) > 0:
                valores_actualizar['contador_color'] = registro_contador.contador_color_detectado
                _logger.info(f"✅ Actualizando Color: 0 → {registro_contador.contador_color_detectado}")
            
            # REGLA ESPECIAL: Si correo tiene scan y PrintTracker no, actualizar
            if lectura_pt.contador_scan == 0 and (registro_contador.contador_scan_detectado or 0) > 0:
                valores_actualizar['contador_scan'] = registro_contador.contador_scan_detectado
                _logger.info(f"✅ Actualizando Scan: 0 → {registro_contador.contador_scan_detectado}")
            
            # Cambiar fuente y agregar referencia correo
            valores_actualizar.update({
                'fuente_origen': 'consolidado',
                'contador_automatico_id': registro_contador.id,
                'fecha_procesamiento': fields.Datetime.now()
            })
            
            if valores_actualizar:
                lectura_pt.write(valores_actualizar)
                _logger.info(f"✅ Lectura de PrintTracker actualizada con correo: {lectura_pt.display_name}")
            else:
                _logger.info(f"ℹ️ No hay valores de correo para actualizar")
            
            return lectura_pt
            
        except Exception as e:
            _logger.error(f"❌ Error actualizando PrintTracker con correo: {e}")
            return lectura_pt
    @api.model
    def crear_desde_printtracker(self, meter_record):
        """
        Crea una lectura diaria desde un registro de printtracker.meter
        CORREGIDO: Actualiza registro de correo si ya existe
        """
        try:
            _logger.info(f"🔄 Creando lectura desde PrintTracker: {meter_record.device_id.serie}")
            
            if not meter_record.device_id or not meter_record.device_id.serie:
                _logger.error("❌ Meter sin serie de equipo")
                return False
            
            # Usar fecha de lectura como fecha de la lectura
            fecha_lectura = meter_record.reading_date.date() if meter_record.reading_date else date.today()
            serie = meter_record.device_id.serie
            
            # Verificar si ya existe
            existing = self.search([
                ('fecha', '=', fecha_lectura),
                ('serie', '=', serie)
            ], limit=1)
            
            if existing:
                if existing.fuente_origen == 'correo':
                    # CASO 1: ACTUALIZAR registro de correo con datos PrintTracker
                    _logger.info(f"🔄 Actualizando registro de correo con datos PrintTracker: {serie} - {fecha_lectura}")
                    return self._actualizar_lectura_correo_con_printtracker(existing, meter_record)
                else:
                    # CASO 2: Ya existe PrintTracker, no duplicar
                    _logger.warning(f"⚠️ Ya existe lectura de PrintTracker para {serie} en {fecha_lectura}")
                    return existing
            
            # CASO 3: No existe registro, crear nuevo
            _logger.info(f"🆕 Creando nuevo registro desde PrintTracker: {serie} - {fecha_lectura}")
            
            valores = {
                'fecha': fecha_lectura,
                'serie': serie,
                'contador_bn': meter_record.black_pages_life or 0,
                'contador_color': meter_record.color_pages_life or 0,
                'contador_scan': meter_record.scan_pages or 0,
                'contador_copy': meter_record.copy_pages or 0,
                'contador_fax': meter_record.fax_pages or 0,
                'fuente_origen': 'printtracker',
                'printtracker_meter_id': meter_record.id,
                'estado': 'validado'
            }
            
            nueva_lectura = self.create(valores)
            _logger.info(f"✅ Lectura creada desde PrintTracker: {nueva_lectura.display_name}")
            
            return nueva_lectura
            
        except Exception as e:
            _logger.error(f"❌ Error creando lectura desde PrintTracker: {e}")
            return False
    def _actualizar_lectura_correo_con_printtracker(self, lectura_correo, meter_record):
        """
        NUEVO: Actualiza registro de correo existente con datos de PrintTracker
        """
        try:
            _logger.info(f"🔄 === ACTUALIZANDO CORREO CON PRINTTRACKER ===")
            _logger.info(f"📧 Correo actual: BN={lectura_correo.contador_bn}, Color={lectura_correo.contador_color}, Scan={lectura_correo.contador_scan}")
            _logger.info(f"🔄 PrintTracker: BN={meter_record.black_pages_life}, Color={meter_record.color_pages_life}, Scan={meter_record.scan_pages}")
            
            # Preparar valores a actualizar
            valores_actualizar = {}
            
            # REGLA: Si correo tiene 0 en algún contador, usar valor de PrintTracker
            if lectura_correo.contador_scan == 0 and (meter_record.scan_pages or 0) > 0:
                valores_actualizar['contador_scan'] = meter_record.scan_pages
                _logger.info(f"✅ Actualizando Scan: 0 → {meter_record.scan_pages}")
            
            if lectura_correo.contador_bn == 0 and (meter_record.black_pages_life or 0) > 0:
                valores_actualizar['contador_bn'] = meter_record.black_pages_life
                _logger.info(f"✅ Actualizando BN: 0 → {meter_record.black_pages_life}")
            
            if lectura_correo.contador_color == 0 and (meter_record.color_pages_life or 0) > 0:
                valores_actualizar['contador_color'] = meter_record.color_pages_life
                _logger.info(f"✅ Actualizando Color: 0 → {meter_record.color_pages_life}")
            
            # Siempre agregar contadores que solo tiene PrintTracker
            if (meter_record.copy_pages or 0) > 0:
                valores_actualizar['contador_copy'] = meter_record.copy_pages
            
            if (meter_record.fax_pages or 0) > 0:
                valores_actualizar['contador_fax'] = meter_record.fax_pages
            
            # Cambiar fuente y agregar referencia PrintTracker
            valores_actualizar.update({
                'fuente_origen': 'consolidado',
                'printtracker_meter_id': meter_record.id,
                'fecha_procesamiento': fields.Datetime.now()
            })
            
            if valores_actualizar:
                lectura_correo.write(valores_actualizar)
                _logger.info(f"✅ Lectura de correo actualizada con PrintTracker: {lectura_correo.display_name}")
            else:
                _logger.info(f"ℹ️ No hay valores de PrintTracker para actualizar")
            
            return lectura_correo
            
        except Exception as e:
            _logger.error(f"❌ Error actualizando correo con PrintTracker: {e}")
            return lectura_correo
    @api.model
    def consolidar_lecturas(self, fecha_objetivo=None, serie_objetivo=None):
        """
        MÉTODO PRINCIPAL: Consolida lecturas de ambas fuentes
        """
        try:
            if not fecha_objetivo:
                fecha_objetivo = date.today()
            
            _logger.info(f"🔄 === INICIANDO CONSOLIDACIÓN ===")
            _logger.info(f"📅 Fecha objetivo: {fecha_objetivo}")
            _logger.info(f"📟 Serie objetivo: {serie_objetivo or 'TODAS'}")
            
            # Determinar series a procesar
            if serie_objetivo:
                series_proceso = [serie_objetivo]
            else:
                # Obtener todas las series con lecturas en la fecha
                domain = [('fecha', '=', fecha_objetivo)]
                lecturas_fecha = self.search(domain)
                series_proceso = list(set(lecturas_fecha.mapped('serie')))
            
            consolidadas = 0
            conflictos = 0
            
            for serie in series_proceso:
                resultado = self._consolidar_serie_fecha(serie, fecha_objetivo)
                if resultado == 'consolidado':
                    consolidadas += 1
                elif resultado == 'conflicto':
                    conflictos += 1
            
            _logger.info(f"🎯 === CONSOLIDACIÓN COMPLETADA ===")
            _logger.info(f"✅ Consolidadas: {consolidadas}")
            _logger.info(f"⚠️ Conflictos: {conflictos}")
            
            return {
                'consolidadas': consolidadas,
                'conflictos': conflictos,
                'series_procesadas': len(series_proceso)
            }
            
        except Exception as e:
            _logger.error(f"❌ Error en consolidación: {e}")
            return False

    def _consolidar_serie_fecha(self, serie, fecha):
        """
        Consolida lecturas de una serie específica en una fecha específica
        """
        try:
            _logger.info(f"🔄 Consolidando {serie} - {fecha}")
            
            # Buscar lecturas existentes
            lecturas = self.search([
                ('fecha', '=', fecha),
                ('serie', '=', serie)
            ])
            
            if len(lecturas) == 0:
                _logger.info(f"ℹ️ No hay lecturas para consolidar")
                return 'sin_datos'
            
            if len(lecturas) == 1:
                # Solo una fuente, marcar como aplicada
                lectura = lecturas[0]
                if lectura.estado == 'validado':
                    self._aplicar_lectura_a_equipo(lectura)
                _logger.info(f"ℹ️ Solo una fuente, aplicada directamente")
                return 'aplicado_directo'
            
            # Múltiples lecturas - consolidar
            lectura_correo = lecturas.filtered(lambda l: l.fuente_origen == 'correo')
            lectura_pt = lecturas.filtered(lambda l: l.fuente_origen == 'printtracker')
            
            if lectura_correo and lectura_pt:
                return self._resolver_conflicto_lecturas(lectura_correo[0], lectura_pt[0])
            else:
                # Caso raro - múltiples lecturas de misma fuente
                _logger.warning(f"⚠️ Múltiples lecturas de misma fuente para {serie}")
                return 'error'
                
        except Exception as e:
            _logger.error(f"❌ Error consolidando {serie}: {e}")
            return 'error'

    def _resolver_conflicto_lecturas(self, lectura_correo, lectura_pt):
        """
        Resuelve conflicto entre lectura de correo y PrintTracker
        REGLA: Mayor valor gana
        """
        try:
            _logger.info(f"⚠️ === RESOLVIENDO CONFLICTO ===")
            _logger.info(f"📧 Correo: BN={lectura_correo.contador_bn}, Color={lectura_correo.contador_color}, Scan={lectura_correo.contador_scan}")
            _logger.info(f"🔄 PrintTracker: BN={lectura_pt.contador_bn}, Color={lectura_pt.contador_color}, Scan={lectura_pt.contador_scan}")
            
            # Aplicar regla "mayor valor gana"
            valores_consolidados = {
                'contador_bn': max(lectura_correo.contador_bn or 0, lectura_pt.contador_bn or 0),
                'contador_color': max(lectura_correo.contador_color or 0, lectura_pt.contador_color or 0),
                'contador_scan': max(lectura_correo.contador_scan or 0, lectura_pt.contador_scan or 0),
                'contador_copy': lectura_pt.contador_copy or 0,  # Solo PrintTracker tiene copy/fax
                'contador_fax': lectura_pt.contador_fax or 0,
            }
            
            # Detectar si hubo conflicto real
            hay_conflicto = (
                lectura_correo.contador_bn != lectura_pt.contador_bn or
                lectura_correo.contador_color != lectura_pt.contador_color or
                lectura_correo.contador_scan != lectura_pt.contador_scan
            )
            
            # Crear lectura consolidada
            lectura_consolidada = self.create({
                'fecha': lectura_correo.fecha,
                'serie': lectura_correo.serie,
                'contador_bn': valores_consolidados['contador_bn'],
                'contador_color': valores_consolidados['contador_color'],
                'contador_scan': valores_consolidados['contador_scan'],
                'contador_copy': valores_consolidados['contador_copy'],
                'contador_fax': valores_consolidados['contador_fax'],
                'fuente_origen': 'consolidado',
                'contador_automatico_id': lectura_correo.contador_automatico_id.id,
                'printtracker_meter_id': lectura_pt.printtracker_meter_id.id,
                'conflicto_detectado': hay_conflicto,
                'resolucion_aplicada': 'mayor_valor',
                'detalle_conflicto': f"Correo vs PT: BN({lectura_correo.contador_bn} vs {lectura_pt.contador_bn}), Color({lectura_correo.contador_color} vs {lectura_pt.contador_color}), Scan({lectura_correo.contador_scan} vs {lectura_pt.contador_scan})",
                'estado': 'validado'
            })
            
            # Aplicar al equipo
            self._aplicar_lectura_a_equipo(lectura_consolidada)
            
            # Marcar lecturas originales como procesadas
            (lectura_correo | lectura_pt).write({'estado': 'aplicado'})
            
            _logger.info(f"✅ Conflicto resuelto y consolidado: {lectura_consolidada.display_name}")
            
            return 'consolidado'
            
        except Exception as e:
            _logger.error(f"❌ Error resolviendo conflicto: {e}")
            return 'error'

    def _aplicar_lectura_a_equipo(self, lectura):
        """
        Aplica los contadores consolidados al equipo en alquiler
        REGLA: Solo aplicar si los valores son mayores a los actuales
        """
        try:
            if not lectura.equipo_id:
                _logger.error(f"❌ No se encontró equipo para serie: {lectura.serie}")
                return False
            
            equipo = lectura.equipo_id
            
            # Obtener valores actuales del equipo
            valores_actuales = {
                'contador_bn': getattr(equipo, 'contador_bn', 0) or 0,
                'contador_color': getattr(equipo, 'contador_color', 0) or 0,
                'contador_scan': getattr(equipo, 'contador_scan', 0) or 0,
            }
            
            # Preparar valores a actualizar (solo si son mayores)
            valores_actualizar = {}
            
            if lectura.contador_bn > valores_actuales['contador_bn']:
                valores_actualizar['contador_bn'] = lectura.contador_bn
            
            if lectura.contador_color > valores_actuales['contador_color']:
                valores_actualizar['contador_color'] = lectura.contador_color
            
            if lectura.contador_scan > valores_actuales['contador_scan']:
                valores_actualizar['contador_scan'] = lectura.contador_scan
            
            # Siempre actualizar fecha
            valores_actualizar['fecha_ultima_actualizacion'] = fields.Datetime.now()
            
            if valores_actualizar:
                equipo.sudo().write(valores_actualizar)
                lectura.write({
                    'aplicado_a_equipo': True,
                    'fecha_aplicacion': fields.Datetime.now(),
                    'estado': 'aplicado'
                })
                
                _logger.info(f"✅ Contadores aplicados al equipo {equipo.serie}: {valores_actualizar}")
                return True
            else:
                _logger.info(f"ℹ️ No hay contadores mayores para aplicar en {equipo.serie}")
                lectura.write({'estado': 'aplicado'})
                return True
                
        except Exception as e:
            _logger.error(f"❌ Error aplicando lectura al equipo: {e}")
            lectura.write({
                'estado': 'error',
                'mensaje_error': str(e)
            })
            return False

    @api.model
    def obtener_estadisticas_consolidacion(self, dias=7):
        """
        Obtiene estadísticas de consolidación de los últimos N días
        """
        fecha_inicio = date.today() - timedelta(days=dias)
        
        domain = [('fecha', '>=', fecha_inicio)]
        lecturas = self.search(domain)
        
        stats = {
            'total_lecturas': len(lecturas),
            'por_fuente': {},
            'conflictos_detectados': len(lecturas.filtered('conflicto_detectado')),
            'aplicadas_equipos': len(lecturas.filtered('aplicado_a_equipo')),
            'series_unicas': len(set(lecturas.mapped('serie'))),
            'por_estado': {}
        }
        
        # Por fuente
        for fuente in ['correo', 'printtracker', 'consolidado', 'manual']:
            count = len(lecturas.filtered(lambda l: l.fuente_origen == fuente))
            stats['por_fuente'][fuente] = count
        
        # Por estado
        for estado in ['borrador', 'validado', 'aplicado', 'error']:
            count = len(lecturas.filtered(lambda l: l.estado == estado))
            stats['por_estado'][estado] = count
        
        return stats

    def action_aplicar_manual(self):
        """Acción manual para aplicar lectura al equipo"""
        self.ensure_one()
        
        if self.estado == 'aplicado':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Esta lectura ya fue aplicada al equipo',
                    'type': 'warning'
                }
            }
        
        success = self._aplicar_lectura_a_equipo(self)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': '✅ Lectura aplicada al equipo exitosamente' if success else '❌ Error aplicando lectura',
                'type': 'success' if success else 'danger'
            }
        }

    def action_view_equipo(self):
        """Acción para ver el equipo relacionado"""
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