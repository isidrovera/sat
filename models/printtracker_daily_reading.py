from odoo import models, fields, api
import logging
from datetime import datetime, timedelta, date

_logger = logging.getLogger(__name__)


class PrintTrackerDailyReading(models.Model):
    _name = 'printtracker.daily.reading'
    _description = 'Lecturas Diarias Consolidadas PrintTracker'
    _order = 'fecha desc, serie'
    _rec_name = 'display_name'

    # ========================================
    # CAMPOS DEL MODELO (SIN CAMBIOS)
    # ========================================
    
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

    # ========================================
    # PARTE 1: MÉTODOS DE CREACIÓN CORREGIDOS
    # ========================================

    @api.model
    def crear_desde_contador_automatico(self, registro_contador):
        """
        PARTE 1 - CORREGIDO: Crea una lectura diaria desde un registro de contador.automatico
        CAMBIO PRINCIPAL: Solo crea, NO actualiza automáticamente
        """
        try:
            _logger.info(f"📧 ===== INICIANDO CREACIÓN DESDE CORREO =====")
            _logger.info(f"📧 Serie detectada: {registro_contador.serie_detectada}")
            _logger.info(f"📧 ID registro contador: {registro_contador.id}")
            _logger.info(f"📧 Fecha procesamiento: {registro_contador.fecha_procesamiento}")
            
            # Validación inicial
            if not registro_contador.serie_detectada:
                _logger.error("❌ CORREO - Registro sin serie detectada")
                _logger.error(f"❌ CORREO - Registro ID: {registro_contador.id}")
                _logger.error(f"❌ CORREO - Campos disponibles: {list(registro_contador._fields.keys())}")
                return False
            
            # Obtener fecha de lectura
            fecha_lectura = registro_contador.fecha_procesamiento.date() if registro_contador.fecha_procesamiento else date.today()
            _logger.info(f"📧 Fecha de lectura calculada: {fecha_lectura}")
            
            # Extraer valores de contadores
            contador_bn = registro_contador.contador_bn_detectado or 0
            contador_color = registro_contador.contador_color_detectado or 0
            contador_scan = registro_contador.contador_scan_detectado or 0
            
            _logger.info(f"📧 Contadores extraídos - BN: {contador_bn}, Color: {contador_color}, Scan: {contador_scan}")
            
            # Buscar si ya existe registro para esta fecha/serie
            _logger.info(f"📧 Buscando registros existentes para serie '{registro_contador.serie_detectada}' en fecha '{fecha_lectura}'")
            
            existing = self.search([
                ('fecha', '=', fecha_lectura),
                ('serie', '=', registro_contador.serie_detectada)
            ])
            
            _logger.info(f"📧 Registros existentes encontrados: {len(existing)}")
            
            if existing:
                for i, registro in enumerate(existing):
                    _logger.info(f"📧 Registro existente {i+1}: ID={registro.id}, Fuente={registro.fuente_origen}, Estado={registro.estado}")
                    _logger.info(f"📧 Contadores existentes: BN={registro.contador_bn}, Color={registro.contador_color}, Scan={registro.contador_scan}")
                
                # CAMBIO PRINCIPAL: No actualizar automáticamente, solo reportar
                _logger.warning(f"⚠️ CORREO - Ya existe(n) {len(existing)} lectura(s) para {registro_contador.serie_detectada} en {fecha_lectura}")
                _logger.warning(f"⚠️ CORREO - Fuente(s) existente(s): {[r.fuente_origen for r in existing]}")
                _logger.warning(f"⚠️ CORREO - Se requiere consolidación manual posterior")
                return existing[0]  # Retornar el primero encontrado
            
            # CASO NUEVO: No existe registro, crear nuevo
            _logger.info(f"🆕 CORREO - Creando nuevo registro para serie: {registro_contador.serie_detectada}")
            _logger.info(f"🆕 CORREO - Fecha: {fecha_lectura}")
            
            # Preparar valores para creación
            valores = {
                'fecha': fecha_lectura,
                'serie': registro_contador.serie_detectada,
                'contador_bn': contador_bn,
                'contador_color': contador_color,
                'contador_scan': contador_scan,
                'contador_copy': 0,  # Correo no detecta copy/fax
                'contador_fax': 0,
                'fuente_origen': 'correo',
                'contador_automatico_id': registro_contador.id,
                'estado': 'validado'
            }
            
            _logger.info(f"🆕 CORREO - Valores para creación: {valores}")
            
            # Crear nueva lectura
            nueva_lectura = self.create(valores)
            
            _logger.info(f"✅ CORREO - Lectura creada exitosamente: ID={nueva_lectura.id}")
            _logger.info(f"✅ CORREO - Display name: {nueva_lectura.display_name}")
            _logger.info(f"✅ CORREO - Total contador: {nueva_lectura.contador_total}")
            _logger.info(f"📧 ===== FIN CREACIÓN DESDE CORREO =====")
            
            return nueva_lectura
            
        except Exception as e:
            _logger.error(f"❌ CORREO - Error crítico creando lectura desde contador automático")
            _logger.error(f"❌ CORREO - Exception: {str(e)}")
            _logger.error(f"❌ CORREO - Serie: {getattr(registro_contador, 'serie_detectada', 'N/A')}")
            import traceback
            _logger.error(f"❌ CORREO - Traceback: {traceback.format_exc()}")
            return False

    @api.model
    def crear_desde_printtracker(self, meter_record):
        """
        PARTE 1 - CORREGIDO: Crea una lectura diaria desde un registro de printtracker.meter
        CAMBIO PRINCIPAL: Solo crea, NO actualiza automáticamente
        """
        try:
            _logger.info(f"🔄 ===== INICIANDO CREACIÓN DESDE PRINTTRACKER =====")
            _logger.info(f"🔄 Device ID: {meter_record.device_id}")
            _logger.info(f"🔄 ID meter record: {meter_record.id}")
            _logger.info(f"🔄 Reading date: {meter_record.reading_date}")
            
            # Validación inicial
            if not meter_record.device_id:
                _logger.error("❌ PRINTTRACKER - Meter sin device_id")
                _logger.error(f"❌ PRINTTRACKER - Meter ID: {meter_record.id}")
                return False
                
            if not meter_record.device_id.serie:
                _logger.error("❌ PRINTTRACKER - Device sin serie")
                _logger.error(f"❌ PRINTTRACKER - Device ID: {meter_record.device_id.id}")
                _logger.error(f"❌ PRINTTRACKER - Device name: {meter_record.device_id.name}")
                return False
            
            # Obtener datos básicos
            serie = meter_record.device_id.serie
            fecha_lectura = meter_record.reading_date.date() if meter_record.reading_date else date.today()
            
            _logger.info(f"🔄 Serie extraída: {serie}")
            _logger.info(f"🔄 Fecha de lectura calculada: {fecha_lectura}")
            
            # Extraer contadores
            contador_bn = meter_record.black_pages_life or 0
            contador_color = meter_record.color_pages_life or 0
            contador_scan = meter_record.scan_pages or 0
            contador_copy = meter_record.copy_pages or 0
            contador_fax = meter_record.fax_pages or 0
            
            _logger.info(f"🔄 Contadores extraídos:")
            _logger.info(f"🔄   - BN: {contador_bn}")
            _logger.info(f"🔄   - Color: {contador_color}")
            _logger.info(f"🔄   - Scan: {contador_scan}")
            _logger.info(f"🔄   - Copy: {contador_copy}")
            _logger.info(f"🔄   - Fax: {contador_fax}")
            
            # Buscar registros existentes
            _logger.info(f"🔄 Buscando registros existentes para serie '{serie}' en fecha '{fecha_lectura}'")
            
            existing = self.search([
                ('fecha', '=', fecha_lectura),
                ('serie', '=', serie)
            ])
            
            _logger.info(f"🔄 Registros existentes encontrados: {len(existing)}")
            
            if existing:
                for i, registro in enumerate(existing):
                    _logger.info(f"🔄 Registro existente {i+1}: ID={registro.id}, Fuente={registro.fuente_origen}, Estado={registro.estado}")
                    _logger.info(f"🔄 Contadores existentes: BN={registro.contador_bn}, Color={registro.contador_color}, Scan={registro.contador_scan}")
                
                # CAMBIO PRINCIPAL: No actualizar automáticamente
                _logger.warning(f"⚠️ PRINTTRACKER - Ya existe(n) {len(existing)} lectura(s) para {serie} en {fecha_lectura}")
                _logger.warning(f"⚠️ PRINTTRACKER - Fuente(s) existente(s): {[r.fuente_origen for r in existing]}")
                _logger.warning(f"⚠️ PRINTTRACKER - Se requiere consolidación manual posterior")
                return existing[0]  # Retornar el primero encontrado
            
            # CASO NUEVO: No existe registro, crear nuevo
            _logger.info(f"🆕 PRINTTRACKER - Creando nuevo registro para serie: {serie}")
            _logger.info(f"🆕 PRINTTRACKER - Fecha: {fecha_lectura}")
            
            # Preparar valores para creación
            valores = {
                'fecha': fecha_lectura,
                'serie': serie,
                'contador_bn': contador_bn,
                'contador_color': contador_color,
                'contador_scan': contador_scan,
                'contador_copy': contador_copy,
                'contador_fax': contador_fax,
                'fuente_origen': 'printtracker',
                'printtracker_meter_id': meter_record.id,
                'estado': 'validado'
            }
            
            _logger.info(f"🆕 PRINTTRACKER - Valores para creación: {valores}")
            
            # Crear nueva lectura
            nueva_lectura = self.create(valores)
            
            _logger.info(f"✅ PRINTTRACKER - Lectura creada exitosamente: ID={nueva_lectura.id}")
            _logger.info(f"✅ PRINTTRACKER - Display name: {nueva_lectura.display_name}")
            _logger.info(f"✅ PRINTTRACKER - Total contador: {nueva_lectura.contador_total}")
            _logger.info(f"🔄 ===== FIN CREACIÓN DESDE PRINTTRACKER =====")
            
            return nueva_lectura
            
        except Exception as e:
            _logger.error(f"❌ PRINTTRACKER - Error crítico creando lectura desde PrintTracker")
            _logger.error(f"❌ PRINTTRACKER - Exception: {str(e)}")
            _logger.error(f"❌ PRINTTRACKER - Device: {getattr(meter_record, 'device_id', 'N/A')}")
            _logger.error(f"❌ PRINTTRACKER - Serie: {getattr(getattr(meter_record, 'device_id', None), 'serie', 'N/A')}")
            import traceback
            _logger.error(f"❌ PRINTTRACKER - Traceback: {traceback.format_exc()}")
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
    # PARTE 2: MÉTODOS DE CONSOLIDACIÓN CORREGIDOS
    # ========================================

    @api.model
    def consolidar_lecturas(self, fecha_objetivo=None, serie_objetivo=None):
        """
        PARTE 2 - MÉTODO PRINCIPAL: Consolida lecturas de ambas fuentes
        CORREGIDO: Lógica clara y logs detallados
        """
        try:
            if not fecha_objetivo:
                fecha_objetivo = date.today()
            
            _logger.info(f"🔄 ============= INICIANDO CONSOLIDACIÓN PRINCIPAL =============")
            _logger.info(f"📅 Fecha objetivo: {fecha_objetivo}")
            _logger.info(f"📟 Serie objetivo: {serie_objetivo or 'TODAS LAS SERIES'}")
            _logger.info(f"🕐 Hora inicio: {datetime.now()}")
            
            # Determinar series a procesar
            if serie_objetivo:
                series_proceso = [serie_objetivo]
                _logger.info(f"🎯 Modo serie específica: {serie_objetivo}")
            else:
                # Obtener todas las series con lecturas en la fecha
                _logger.info(f"🔍 Buscando todas las series con lecturas en fecha {fecha_objetivo}")
                
                domain = [('fecha', '=', fecha_objetivo)]
                lecturas_fecha = self.search(domain)
                series_proceso = list(set(lecturas_fecha.mapped('serie')))
                
                _logger.info(f"📊 Total lecturas encontradas en fecha: {len(lecturas_fecha)}")
                _logger.info(f"📊 Series únicas encontradas: {len(series_proceso)}")
                _logger.info(f"📊 Primeras 5 series: {series_proceso[:5]}")
            
            # Contadores de resultados
            consolidadas = 0
            conflictos = 0
            ya_consolidadas = 0
            aplicadas_directas = 0
            errores = 0
            sin_datos = 0
            
            _logger.info(f"🚀 Iniciando procesamiento de {len(series_proceso)} series...")
            
            # Procesar cada serie
            for i, serie in enumerate(series_proceso, 1):
                _logger.info(f"📍 === PROCESANDO SERIE {i}/{len(series_proceso)}: {serie} ===")
                
                try:
                    resultado = self._consolidar_serie_fecha(serie, fecha_objetivo)
                    
                    # Contar resultados
                    if resultado == 'consolidado':
                        consolidadas += 1
                        _logger.info(f"✅ Serie {serie}: CONSOLIDADA")
                    elif resultado == 'conflicto':
                        conflictos += 1
                        _logger.warning(f"⚠️ Serie {serie}: CONFLICTO DETECTADO")
                    elif resultado == 'ya_consolidado':
                        ya_consolidadas += 1
                        _logger.info(f"ℹ️ Serie {serie}: YA CONSOLIDADA")
                    elif resultado == 'aplicado_directo':
                        aplicadas_directas += 1
                        _logger.info(f"✅ Serie {serie}: APLICADA DIRECTAMENTE")
                    elif resultado == 'sin_datos':
                        sin_datos += 1
                        _logger.info(f"➖ Serie {serie}: SIN DATOS")
                    else:
                        errores += 1
                        _logger.error(f"❌ Serie {serie}: ERROR ({resultado})")
                        
                except Exception as e:
                    errores += 1
                    _logger.error(f"❌ Error procesando serie {serie}: {str(e)}")
                    import traceback
                    _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            
            # Resumen final
            _logger.info(f"🎯 ============= CONSOLIDACIÓN COMPLETADA =============")
            _logger.info(f"📊 RESUMEN DE RESULTADOS:")
            _logger.info(f"✅ Consolidadas: {consolidadas}")
            _logger.info(f"⚠️ Conflictos: {conflictos}")
            _logger.info(f"ℹ️ Ya consolidadas: {ya_consolidadas}")
            _logger.info(f"➡️ Aplicadas directas: {aplicadas_directas}")
            _logger.info(f"➖ Sin datos: {sin_datos}")
            _logger.info(f"❌ Errores: {errores}")
            _logger.info(f"📊 Total procesadas: {len(series_proceso)}")
            _logger.info(f"🕐 Hora fin: {datetime.now()}")
            
            return {
                'consolidadas': consolidadas,
                'conflictos': conflictos,
                'ya_consolidadas': ya_consolidadas,
                'aplicadas_directas': aplicadas_directas,
                'sin_datos': sin_datos,
                'errores': errores,
                'series_procesadas': len(series_proceso),
                'series_lista': series_proceso
            }
            
        except Exception as e:
            _logger.error(f"❌ ERROR CRÍTICO en consolidación principal: {str(e)}")
            import traceback
            _logger.error(f"❌ Traceback completo: {traceback.format_exc()}")
            return False

    def _consolidar_serie_fecha(self, serie, fecha):
        """
        PARTE 2 - Consolida lecturas de una serie específica en una fecha específica
        CORREGIDO: Lógica clara y manejo de todos los casos
        """
        try:
            _logger.info(f"🔄 --- Iniciando consolidación: {serie} - {fecha} ---")
            
            # Buscar lecturas existentes
            _logger.info(f"🔍 Buscando lecturas existentes...")
            lecturas = self.search([
                ('fecha', '=', fecha),
                ('serie', '=', serie)
            ])
            
            _logger.info(f"📊 Lecturas encontradas: {len(lecturas)}")
            
            # Analizar lecturas encontradas
            for i, lectura in enumerate(lecturas):
                _logger.info(f"📋 Lectura {i+1}: ID={lectura.id}, Fuente={lectura.fuente_origen}, Estado={lectura.estado}")
                _logger.info(f"📋 Contadores: BN={lectura.contador_bn}, Color={lectura.contador_color}, Scan={lectura.contador_scan}")
            
            # CASO 1: No hay lecturas
            if len(lecturas) == 0:
                _logger.info(f"➖ No hay lecturas para consolidar")
                return 'sin_datos'
            
            # CASO 2: Solo una lectura
            if len(lecturas) == 1:
                lectura = lecturas[0]
                _logger.info(f"📍 Solo una lectura encontrada: Fuente={lectura.fuente_origen}, Estado={lectura.estado}")
                
                if lectura.estado == 'validado':
                    _logger.info(f"🚀 Aplicando lectura única al equipo...")
                    resultado_aplicacion = self._aplicar_lectura_a_equipo(lectura)
                    if resultado_aplicacion:
                        _logger.info(f"✅ Lectura única aplicada exitosamente")
                    else:
                        _logger.error(f"❌ Error aplicando lectura única")
                else:
                    _logger.info(f"ℹ️ Lectura única ya procesada (estado: {lectura.estado})")
                
                return 'aplicado_directo'
            
            # CASO 3: Múltiples lecturas - analizar tipos
            _logger.info(f"🔍 Múltiples lecturas encontradas, analizando tipos...")
            
            lectura_correo = lecturas.filtered(lambda l: l.fuente_origen == 'correo')
            lectura_pt = lecturas.filtered(lambda l: l.fuente_origen == 'printtracker')
            lectura_consolidada = lecturas.filtered(lambda l: l.fuente_origen == 'consolidado')
            lectura_manual = lecturas.filtered(lambda l: l.fuente_origen == 'manual')
            
            _logger.info(f"📊 Análisis de fuentes:")
            _logger.info(f"📧 Correo: {len(lectura_correo)} registros")
            _logger.info(f"🔄 PrintTracker: {len(lectura_pt)} registros")
            _logger.info(f"🔗 Consolidado: {len(lectura_consolidada)} registros")
            _logger.info(f"✋ Manual: {len(lectura_manual)} registros")
            
            # CASO 3.1: Ya existe consolidada
            if lectura_consolidada:
                _logger.info(f"ℹ️ Ya existe lectura consolidada, verificando si necesita aplicación...")
                consolidada = lectura_consolidada[0]
                
                if consolidada.estado == 'validado':
                    _logger.info(f"🚀 Aplicando lectura consolidada existente...")
                    resultado_aplicacion = self._aplicar_lectura_a_equipo(consolidada)
                    if resultado_aplicacion:
                        _logger.info(f"✅ Lectura consolidada aplicada exitosamente")
                    else:
                        _logger.error(f"❌ Error aplicando lectura consolidada")
                else:
                    _logger.info(f"ℹ️ Lectura consolidada ya procesada (estado: {consolidada.estado})")
                
                return 'ya_consolidado'
            
            # CASO 3.2: Consolidar correo + printtracker
            if lectura_correo and lectura_pt:
                _logger.info(f"🔄 Consolidando correo + PrintTracker...")
                return self._consolidar_dos_fuentes(lectura_correo[0], lectura_pt[0])
            
            # CASO 3.3: Solo múltiples de una fuente (caso raro)
            if len(lectura_correo) > 1:
                _logger.warning(f"⚠️ Múltiples lecturas de correo para misma serie/fecha")
                return 'error'
            
            if len(lectura_pt) > 1:
                _logger.warning(f"⚠️ Múltiples lecturas de PrintTracker para misma serie/fecha")
                return 'error'
            
            # CASO 3.4: Solo manual (aplicar directamente)
            if lectura_manual:
                lectura = lectura_manual[0]
                if lectura.estado == 'validado':
                    _logger.info(f"🚀 Aplicando lectura manual...")
                    self._aplicar_lectura_a_equipo(lectura)
                return 'aplicado_directo'
            
            # CASO 3.5: Situación no contemplada
            _logger.warning(f"⚠️ Situación no contemplada para {serie}")
            _logger.warning(f"⚠️ Lecturas: {[(l.fuente_origen, l.estado) for l in lecturas]}")
            return 'error'
                
        except Exception as e:
            _logger.error(f"❌ Error consolidando {serie}: {str(e)}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return 'error'

    def _consolidar_dos_fuentes(self, lectura_correo, lectura_pt):
        """
        PARTE 2 - NUEVO: Consolida datos de dos fuentes en una sola lectura
        REGLAS CLARAS Y LOGS DETALLADOS
        """
        try:
            _logger.info(f"🔄 ======= CONSOLIDANDO DOS FUENTES =======")
            _logger.info(f"📧 CORREO - ID: {lectura_correo.id}")
            _logger.info(f"📧 CORREO - BN: {lectura_correo.contador_bn}, Color: {lectura_correo.contador_color}, Scan: {lectura_correo.contador_scan}")
            _logger.info(f"📧 CORREO - Estado: {lectura_correo.estado}")
            
            _logger.info(f"🔄 PRINTTRACKER - ID: {lectura_pt.id}")
            _logger.info(f"🔄 PRINTTRACKER - BN: {lectura_pt.contador_bn}, Color: {lectura_pt.contador_color}, Scan: {lectura_pt.contador_scan}")
            _logger.info(f"🔄 PRINTTRACKER - Copy: {lectura_pt.contador_copy}, Fax: {lectura_pt.contador_fax}")
            _logger.info(f"🔄 PRINTTRACKER - Estado: {lectura_pt.estado}")
            
            # Aplicar reglas de consolidación
            _logger.info(f"⚙️ Aplicando reglas de consolidación...")
            
            # REGLA 1: Mayor valor para BN/Color
            contador_bn_final = max(lectura_correo.contador_bn or 0, lectura_pt.contador_bn or 0)
            contador_color_final = max(lectura_correo.contador_color or 0, lectura_pt.contador_color or 0)
            
            _logger.info(f"⚙️ REGLA 1 (Mayor valor BN/Color):")
            _logger.info(f"⚙️   BN: max({lectura_correo.contador_bn}, {lectura_pt.contador_bn}) = {contador_bn_final}")
            _logger.info(f"⚙️   Color: max({lectura_correo.contador_color}, {lectura_pt.contador_color}) = {contador_color_final}")
            
            # REGLA 2: PrintTracker gana para scan/copy/fax (más precisos)
            contador_scan_final = lectura_pt.contador_scan or lectura_correo.contador_scan or 0
            contador_copy_final = lectura_pt.contador_copy or 0
            contador_fax_final = lectura_pt.contador_fax or 0
            
            _logger.info(f"⚙️ REGLA 2 (PrintTracker gana para scan/copy/fax):")
            _logger.info(f"⚙️   Scan: PT({lectura_pt.contador_scan}) o Correo({lectura_correo.contador_scan}) = {contador_scan_final}")
            _logger.info(f"⚙️   Copy: {contador_copy_final} (solo PrintTracker)")
            _logger.info(f"⚙️   Fax: {contador_fax_final} (solo PrintTracker)")
            
            # Preparar valores consolidados
            valores_consolidados = {
                'contador_bn': contador_bn_final,
                'contador_color': contador_color_final,
                'contador_scan': contador_scan_final,
                'contador_copy': contador_copy_final,
                'contador_fax': contador_fax_final,
            }
            
            _logger.info(f"📊 Valores consolidados finales: {valores_consolidados}")
            
            # Detectar conflictos
            _logger.info(f"🔍 Detectando conflictos...")
            conflictos = []
            
            if (lectura_correo.contador_bn != lectura_pt.contador_bn and 
                lectura_correo.contador_bn > 0 and lectura_pt.contador_bn > 0):
                conflicto_bn = f"BN: Correo({lectura_correo.contador_bn}) vs PT({lectura_pt.contador_bn})"
                conflictos.append(conflicto_bn)
                _logger.warning(f"⚠️ CONFLICTO: {conflicto_bn}")
            
            if (lectura_correo.contador_color != lectura_pt.contador_color and 
                lectura_correo.contador_color > 0 and lectura_pt.contador_color > 0):
                conflicto_color = f"Color: Correo({lectura_correo.contador_color}) vs PT({lectura_pt.contador_color})"
                conflictos.append(conflicto_color)
                _logger.warning(f"⚠️ CONFLICTO: {conflicto_color}")
            
            if (lectura_correo.contador_scan != lectura_pt.contador_scan and 
                lectura_correo.contador_scan > 0 and lectura_pt.contador_scan > 0):
                conflicto_scan = f"Scan: Correo({lectura_correo.contador_scan}) vs PT({lectura_pt.contador_scan})"
                conflictos.append(conflicto_scan)
                _logger.warning(f"⚠️ CONFLICTO: {conflicto_scan}")
            
            hay_conflictos = bool(conflictos)
            _logger.info(f"🔍 Conflictos detectados: {'SÍ' if hay_conflictos else 'NO'}")
            if hay_conflictos:
                _logger.info(f"📋 Lista de conflictos: {conflictos}")
            
            # ESTRATEGIA: Actualizar lectura de correo como consolidada
            _logger.info(f"🔄 Actualizando lectura de correo como consolidada...")
            
            valores_actualizar = {
                'contador_bn': valores_consolidados['contador_bn'],
                'contador_color': valores_consolidados['contador_color'],
                'contador_scan': valores_consolidados['contador_scan'],
                'contador_copy': valores_consolidados['contador_copy'],
                'contador_fax': valores_consolidados['contador_fax'],
                'fuente_origen': 'consolidado',
                'printtracker_meter_id': lectura_pt.printtracker_meter_id.id,
                'conflicto_detectado': hay_conflictos,
                'detalle_conflicto': '; '.join(conflictos) if conflictos else None,
                'resolucion_aplicada': 'mayor_valor',
                'fecha_procesamiento': fields.Datetime.now()
            }
            
            _logger.info(f"📝 Valores a actualizar en correo: {valores_actualizar}")
            
            lectura_correo.write(valores_actualizar)
            _logger.info(f"✅ Lectura de correo actualizada como consolidada")
            
            # Marcar PrintTracker como procesada
            _logger.info(f"📝 Marcando lectura PrintTracker como procesada...")
            lectura_pt.write({'estado': 'aplicado'})
            _logger.info(f"✅ Lectura PrintTracker marcada como aplicada")
            
            # Aplicar al equipo
            _logger.info(f"🚀 Aplicando lectura consolidada al equipo...")
            resultado_aplicacion = self._aplicar_lectura_a_equipo(lectura_correo)
            
            if resultado_aplicacion:
                _logger.info(f"✅ Lectura consolidada aplicada exitosamente al equipo")
            else:
                _logger.error(f"❌ Error aplicando lectura consolidada al equipo")
            
            _logger.info(f"🎯 === CONSOLIDACIÓN DE DOS FUENTES COMPLETADA ===")
            _logger.info(f"📊 Resultado final:")
            _logger.info(f"📊   - BN: {valores_consolidados['contador_bn']}")
            _logger.info(f"📊   - Color: {valores_consolidados['contador_color']}")
            _logger.info(f"📊   - Scan: {valores_consolidados['contador_scan']}")
            _logger.info(f"📊   - Copy: {valores_consolidados['contador_copy']}")
            _logger.info(f"📊   - Fax: {valores_consolidados['contador_fax']}")
            _logger.info(f"📊   - Conflictos: {'SÍ' if hay_conflictos else 'NO'}")
            
            return 'consolidado'
            
        except Exception as e:
            _logger.error(f"❌ ERROR CRÍTICO consolidando dos fuentes: {str(e)}")
            _logger.error(f"❌ Correo ID: {getattr(lectura_correo, 'id', 'N/A')}")
            _logger.error(f"❌ PrintTracker ID: {getattr(lectura_pt, 'id', 'N/A')}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return 'error'

    @api.model
    def consolidar_lecturas_pendientes(self, dias_atras=1):
        """
        PARTE 2 - NUEVO: Consolida lecturas pendientes de los últimos N días
        Útil para ejecutar como cron job
        """
        try:
            fecha_inicio = date.today() - timedelta(days=dias_atras)
            
            _logger.info(f"🔄 ===== CONSOLIDANDO LECTURAS PENDIENTES =====")
            _logger.info(f"📅 Desde fecha: {fecha_inicio}")
            _logger.info(f"📅 Hasta fecha: {date.today()}")
            _logger.info(f"🕐 Hora inicio: {datetime.now()}")
            
            # Buscar fechas que necesitan consolidación
            _logger.info(f"🔍 Buscando lecturas pendientes...")
            
            lecturas_pendientes = self.search([
                ('fecha', '>=', fecha_inicio),
                ('estado', '=', 'validado')
            ])
            
            _logger.info(f"📊 Total lecturas pendientes encontradas: {len(lecturas_pendientes)}")
            
            # Agrupar por fecha y serie
            _logger.info(f"📊 Agrupando por fecha y serie...")
            grupos = {}
            for lectura in lecturas_pendientes:
                key = (lectura.fecha, lectura.serie)
                if key not in grupos:
                    grupos[key] = []
                grupos[key].append(lectura)
            
            _logger.info(f"📊 Grupos encontrados: {len(grupos)}")
            
            # Identificar grupos que necesitan consolidación (más de 1 lectura)
            grupos_consolidar = {k: v for k, v in grupos.items() if len(v) > 1}
            _logger.info(f"📊 Grupos que necesitan consolidación: {len(grupos_consolidar)}")
            
            if not grupos_consolidar:
                _logger.info(f"ℹ️ No hay grupos que necesiten consolidación")
                return {
                    'grupos_procesados': len(grupos),
                    'grupos_consolidados': 0,
                    'consolidadas': 0
                }
            
            # Procesar grupos que necesitan consolidación
            consolidadas = 0
            for i, ((fecha, serie), lecturas_grupo) in enumerate(grupos_consolidar.items(), 1):
                _logger.info(f"🔄 Procesando grupo {i}/{len(grupos_consolidar)}: {serie} - {fecha}")
                _logger.info(f"🔄 Lecturas en grupo: {len(lecturas_grupo)}")
                
                resultado = self._consolidar_serie_fecha(serie, fecha)
                if resultado == 'consolidado':
                    consolidadas += 1
                    _logger.info(f"✅ Grupo consolidado: {serie} - {fecha}")
                else:
                    _logger.warning(f"⚠️ Grupo no consolidado ({resultado}): {serie} - {fecha}")
            
            _logger.info(f"🎯 ===== CONSOLIDACIÓN PENDIENTE COMPLETADA =====")
            _logger.info(f"📊 Grupos procesados: {len(grupos)}")
            _logger.info(f"📊 Grupos que necesitaban consolidación: {len(grupos_consolidar)}")
            _logger.info(f"✅ Consolidaciones exitosas: {consolidadas}")
            _logger.info(f"🕐 Hora fin: {datetime.now()}")
            
            return {
                'grupos_procesados': len(grupos),
                'grupos_que_necesitaban_consolidacion': len(grupos_consolidar),
                'consolidadas': consolidadas,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': date.today()
            }
            
        except Exception as e:
            _logger.error(f"❌ ERROR CRÍTICO en consolidación pendiente: {str(e)}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return False



    # ========================================
    # PARTE 3: APLICACIÓN AL EQUIPO Y MÉTODOS DE UTILIDAD
    # ========================================

    def _aplicar_lectura_a_equipo(self, lectura):
        """
        PARTE 3 - CORREGIDO: Aplica los contadores consolidados al equipo en alquiler
        MEJORAS: Logs detallados, validaciones y manejo de errores
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
                
                # Intentar buscar equipo manualmente
                equipo = self.env['alquiler'].search([
                    ('serie', '=', lectura.serie)
                ], limit=1)
                
                if equipo:
                    _logger.info(f"✅ Equipo encontrado: ID={equipo.id}, Nombre={equipo.name}")
                    # Actualizar referencia en la lectura
                    lectura.write({'equipo_id': equipo.id})
                else:
                    _logger.error(f"❌ No se encontró equipo para serie: {lectura.serie}")
                    lectura.write({
                        'estado': 'error',
                        'mensaje_error': f'No se encontró equipo para serie {lectura.serie}'
                    })
                    return False
            else:
                _logger.info(f"✅ Equipo ya referenciado: ID={lectura.equipo_id.id}")
            
            equipo = lectura.equipo_id
            _logger.info(f"🎯 Aplicando al equipo: {equipo.name} (ID: {equipo.id})")
            
            # Obtener valores actuales del equipo
            _logger.info(f"📊 Obteniendo valores actuales del equipo...")
            
            valores_actuales = {
                'contador_bn': getattr(equipo, 'contador_bn', 0) or 0,
                'contador_color': getattr(equipo, 'contador_color', 0) or 0,
                'contador_scan': getattr(equipo, 'contador_scan', 0) or 0,
                'contador_copy': getattr(equipo, 'contador_copy', 0) or 0,
                'contador_fax': getattr(equipo, 'contador_fax', 0) or 0,
            }
            
            _logger.info(f"📊 Valores actuales del equipo:")
            _logger.info(f"📊   - BN: {valores_actuales['contador_bn']}")
            _logger.info(f"📊   - Color: {valores_actuales['contador_color']}")
            _logger.info(f"📊   - Scan: {valores_actuales['contador_scan']}")
            _logger.info(f"📊   - Copy: {valores_actuales['contador_copy']}")
            _logger.info(f"📊   - Fax: {valores_actuales['contador_fax']}")
            
            # Valores de la lectura
            valores_lectura = {
                'contador_bn': lectura.contador_bn or 0,
                'contador_color': lectura.contador_color or 0,
                'contador_scan': lectura.contador_scan or 0,
                'contador_copy': lectura.contador_copy or 0,
                'contador_fax': lectura.contador_fax or 0,
            }
            
            _logger.info(f"📋 Valores de la lectura:")
            _logger.info(f"📋   - BN: {valores_lectura['contador_bn']}")
            _logger.info(f"📋   - Color: {valores_lectura['contador_color']}")
            _logger.info(f"📋   - Scan: {valores_lectura['contador_scan']}")
            _logger.info(f"📋   - Copy: {valores_lectura['contador_copy']}")
            _logger.info(f"📋   - Fax: {valores_lectura['contador_fax']}")
            
            # Comparar y preparar valores a actualizar
            _logger.info(f"⚙️ Comparando valores para determinar actualizaciones...")
            valores_actualizar = {}
            cambios_realizados = []
            
            for contador in ['contador_bn', 'contador_color', 'contador_scan', 'contador_copy', 'contador_fax']:
                valor_actual = valores_actuales[contador]
                valor_lectura = valores_lectura[contador]
                
                # REGLA: Solo actualizar si el valor de la lectura es mayor
                if valor_lectura > valor_actual:
                    valores_actualizar[contador] = valor_lectura
                    cambios_realizados.append(f"{contador}: {valor_actual} → {valor_lectura}")
                    _logger.info(f"✅ Actualización: {contador}: {valor_actual} → {valor_lectura}")
                elif valor_lectura < valor_actual:
                    _logger.warning(f"⚠️ Valor menor ignorado: {contador}: lectura({valor_lectura}) < equipo({valor_actual})")
                else:
                    _logger.info(f"ℹ️ Sin cambio: {contador}: {valor_actual} (igual)")
            
            # Siempre actualizar fecha de última actualización
            valores_actualizar['fecha_ultima_actualizacion'] = fields.Datetime.now()
            
            # Aplicar actualizaciones si hay cambios
            if len(valores_actualizar) > 1:  # Más que solo la fecha
                _logger.info(f"🔄 Aplicando {len(valores_actualizar)-1} actualizaciones al equipo...")
                _logger.info(f"🔄 Cambios: {cambios_realizados}")
                
                try:
                    # Usar sudo() para asegurar permisos
                    equipo.sudo().write(valores_actualizar)
                    _logger.info(f"✅ Contadores actualizados en equipo exitosamente")
                    
                    # Actualizar estado de la lectura
                    lectura.write({
                        'aplicado_a_equipo': True,
                        'fecha_aplicacion': fields.Datetime.now(),
                        'estado': 'aplicado',
                        'mensaje_error': None  # Limpiar errores anteriores
                    })
                    
                    _logger.info(f"✅ Estado de lectura actualizado a 'aplicado'")
                    
                    # Log de resumen
                    _logger.info(f"📊 RESUMEN DE APLICACIÓN:")
                    _logger.info(f"📊   - Equipo: {equipo.name} (ID: {equipo.id})")
                    _logger.info(f"📊   - Cambios aplicados: {len(cambios_realizados)}")
                    _logger.info(f"📊   - Lista de cambios: {cambios_realizados}")
                    
                    return True
                    
                except Exception as e:
                    _logger.error(f"❌ Error escribiendo en equipo: {str(e)}")
                    lectura.write({
                        'estado': 'error',
                        'mensaje_error': f'Error actualizando equipo: {str(e)}'
                    })
                    return False
                    
            else:
                _logger.info(f"ℹ️ No hay contadores mayores para aplicar en {equipo.name}")
                _logger.info(f"ℹ️ Solo se actualiza fecha de procesamiento")
                
                # Marcar como aplicado aunque no haya cambios de contadores
                lectura.write({
                    'aplicado_a_equipo': True,
                    'fecha_aplicacion': fields.Datetime.now(),
                    'estado': 'aplicado',
                    'mensaje_error': None
                })
                
                _logger.info(f"✅ Lectura marcada como aplicada (sin cambios de contadores)")
                return True
                
        except Exception as e:
            _logger.error(f"❌ ERROR CRÍTICO aplicando lectura al equipo")
            _logger.error(f"❌ Lectura ID: {getattr(lectura, 'id', 'N/A')}")
            _logger.error(f"❌ Serie: {getattr(lectura, 'serie', 'N/A')}")
            _logger.error(f"❌ Exception: {str(e)}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            
            try:
                lectura.write({
                    'estado': 'error',
                    'mensaje_error': f'Error crítico aplicando al equipo: {str(e)}'
                })
            except:
                _logger.error(f"❌ No se pudo actualizar estado de error en lectura")
            
            return False

    @api.model
    def obtener_estadisticas_consolidacion(self, dias=7):
        """
        PARTE 3 - MEJORADO: Obtiene estadísticas detalladas de consolidación
        """
        try:
            _logger.info(f"📊 ===== GENERANDO ESTADÍSTICAS DE CONSOLIDACIÓN =====")
            _logger.info(f"📅 Últimos {dias} días")
            
            fecha_inicio = date.today() - timedelta(days=dias)
            _logger.info(f"📅 Desde: {fecha_inicio} hasta: {date.today()}")
            
            domain = [('fecha', '>=', fecha_inicio)]
            lecturas = self.search(domain)
            
            _logger.info(f"📊 Total lecturas encontradas: {len(lecturas)}")
            
            # Estadísticas básicas
            stats = {
                'periodo': {
                    'fecha_inicio': fecha_inicio,
                    'fecha_fin': date.today(),
                    'dias': dias
                },
                'total_lecturas': len(lecturas),
                'por_fuente': {},
                'conflictos_detectados': len(lecturas.filtered('conflicto_detectado')),
                'aplicadas_equipos': len(lecturas.filtered('aplicado_a_equipo')),
                'series_unicas': len(set(lecturas.mapped('serie'))),
                'por_estado': {},
                'por_fecha': {},
                'equipos_sin_serie': 0,
                'errores_aplicacion': len(lecturas.filtered(lambda l: l.estado == 'error'))
            }
            
            _logger.info(f"📊 Calculando estadísticas por fuente...")
            # Por fuente
            for fuente in ['correo', 'printtracker', 'consolidado', 'manual']:
                count = len(lecturas.filtered(lambda l: l.fuente_origen == fuente))
                stats['por_fuente'][fuente] = count
                _logger.info(f"📊   {fuente}: {count}")
            
            _logger.info(f"📊 Calculando estadísticas por estado...")
            # Por estado
            for estado in ['borrador', 'validado', 'aplicado', 'error']:
                count = len(lecturas.filtered(lambda l: l.estado == estado))
                stats['por_estado'][estado] = count
                _logger.info(f"📊   {estado}: {count}")
            
            _logger.info(f"📊 Calculando estadísticas por fecha...")
            # Por fecha (últimos días)
            for i in range(dias):
                fecha = date.today() - timedelta(days=i)
                count = len(lecturas.filtered(lambda l: l.fecha == fecha))
                stats['por_fecha'][fecha.strftime('%Y-%m-%d')] = count
            
            # Equipos sin serie
            _logger.info(f"📊 Buscando lecturas sin equipo asociado...")
            stats['equipos_sin_serie'] = len(lecturas.filtered(lambda l: not l.equipo_id))
            
            # Estadísticas adicionales
            if lecturas:
                _logger.info(f"📊 Calculando estadísticas adicionales...")
                
                # Promedio de contadores
                stats['promedios'] = {
                    'contador_bn': sum(l.contador_bn or 0 for l in lecturas) / len(lecturas),
                    'contador_color': sum(l.contador_color or 0 for l in lecturas) / len(lecturas),
                    'contador_scan': sum(l.contador_scan or 0 for l in lecturas) / len(lecturas),
                    'contador_total': sum(l.contador_total or 0 for l in lecturas) / len(lecturas)
                }
                
                # Series más activas
                series_count = {}
                for lectura in lecturas:
                    if lectura.serie in series_count:
                        series_count[lectura.serie] += 1
                    else:
                        series_count[lectura.serie] = 1
                
                stats['series_mas_activas'] = sorted(
                    series_count.items(), 
                    key=lambda x: x[1], 
                    reverse=True
                )[:10]  # Top 10
            
            _logger.info(f"✅ Estadísticas generadas exitosamente")
            _logger.info(f"📊 Resumen: {stats['total_lecturas']} lecturas, {stats['series_unicas']} series únicas")
            
            return stats
            
        except Exception as e:
            _logger.error(f"❌ Error generando estadísticas: {str(e)}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return False

    def action_aplicar_manual(self):
        """
        PARTE 3 - MEJORADO: Acción manual para aplicar lectura al equipo
        """
        self.ensure_one()
        
        _logger.info(f"✋ ===== APLICACIÓN MANUAL SOLICITADA =====")
        _logger.info(f"📋 Lectura ID: {self.id}")
        _logger.info(f"📋 Serie: {self.serie}")
        _logger.info(f"📋 Estado actual: {self.estado}")
        _logger.info(f"📋 Ya aplicado: {self.aplicado_a_equipo}")
        
        if self.estado == 'aplicado':
            _logger.warning(f"⚠️ Lectura ya aplicada al equipo")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Esta lectura ya fue aplicada al equipo',
                    'type': 'warning'
                }
            }
        
        if self.aplicado_a_equipo:
            _logger.warning(f"⚠️ Lectura marcada como aplicada")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Esta lectura ya está marcada como aplicada',
                    'type': 'warning'
                }
            }
        
        _logger.info(f"🚀 Iniciando aplicación manual...")
        success = self._aplicar_lectura_a_equipo(self)
        
        if success:
            _logger.info(f"✅ Aplicación manual exitosa")
            mensaje = f'✅ Lectura aplicada al equipo exitosamente\nSerie: {self.serie}\nContadores aplicados al equipo {self.equipo_id.name if self.equipo_id else "N/A"}'
            tipo = 'success'
        else:
            _logger.error(f"❌ Error en aplicación manual")
            mensaje = f'❌ Error aplicando lectura\nSerie: {self.serie}\nError: {self.mensaje_error or "Error desconocido"}'
            tipo = 'danger'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': mensaje,
                'type': tipo,
                'sticky': True if not success else False
            }
        }

    def action_diagnostico_consolidacion(self):
        """
        PARTE 3 - MEJORADO: Diagnóstico completo del sistema de consolidación
        """
        try:
            _logger.info(f"🔍 ===== INICIANDO DIAGNÓSTICO =====")
            
            # Buscar datos básicos
            correos = self.env['printtracker.daily.reading'].search([
                ('fuente_origen', '=', 'correo')
            ])
            
            printrackers = self.env['printtracker.daily.reading'].search([
                ('fuente_origen', '=', 'printtracker')
            ])
            
            consolidados = self.env['printtracker.daily.reading'].search([
                ('fuente_origen', '=', 'consolidado')
            ])
            
            meters = self.env['printtracker.meter'].search([])
            contadores_auto = self.env['contador.automatico'].search([])
            
            # Crear mensaje de diagnóstico
            mensaje = "=== DIAGNÓSTICO CONSOLIDACIÓN ===\n\n"
            
            # Estadísticas generales
            mensaje += "📊 ESTADÍSTICAS GENERALES:\n"
            mensaje += f"• Total lecturas correo: {len(correos)}\n"
            mensaje += f"• Total lecturas PrintTracker: {len(printrackers)}\n"
            mensaje += f"• Total lecturas consolidadas: {len(consolidados)}\n"
            mensaje += f"• Total meters PT originales: {len(meters)}\n"
            mensaje += f"• Total contadores automáticos: {len(contadores_auto)}\n\n"
            
            # Series únicas
            series_correo = set(correos.mapped('serie')) if correos else set()
            series_pt = set(printrackers.mapped('serie')) if printrackers else set()
            series_todas = series_correo | series_pt
            
            mensaje += "📟 SERIES:\n"
            mensaje += f"• Series únicas en correo: {len(series_correo)}\n"
            mensaje += f"• Series únicas en PrintTracker: {len(series_pt)}\n"
            mensaje += f"• Series que coinciden: {len(series_correo & series_pt)}\n"
            mensaje += f"• Total series únicas: {len(series_todas)}\n\n"
            
            # Fechas recientes
            if correos or printrackers:
                fechas_correo = correos.mapped('fecha') if correos else []
                fechas_pt = printrackers.mapped('fecha') if printrackers else []
                
                mensaje += "📅 FECHAS RECIENTES:\n"
                if fechas_correo:
                    mensaje += f"• Última fecha correo: {max(fechas_correo)}\n"
                if fechas_pt:
                    mensaje += f"• Última fecha PrintTracker: {max(fechas_pt)}\n"
                mensaje += "\n"
            
            # Estados
            estados_correo = {}
            estados_pt = {}
            
            for estado in ['borrador', 'validado', 'aplicado', 'error']:
                estados_correo[estado] = len(correos.filtered(lambda l: l.estado == estado))
                estados_pt[estado] = len(printrackers.filtered(lambda l: l.estado == estado))
            
            mensaje += "📊 ESTADOS:\n"
            mensaje += "Correo:\n"
            for estado, count in estados_correo.items():
                mensaje += f"  • {estado}: {count}\n"
            mensaje += "PrintTracker:\n"
            for estado, count in estados_pt.items():
                mensaje += f"  • {estado}: {count}\n"
            mensaje += "\n"
            
            # Conflictos
            conflictos = (correos | printrackers | consolidados).filtered('conflicto_detectado')
            mensaje += f"⚠️ CONFLICTOS DETECTADOS: {len(conflictos)}\n\n"
            
            # Problemas potenciales
            mensaje += "🔍 PROBLEMAS POTENCIALES:\n"
            
            # Lecturas sin equipo
            sin_equipo = (correos | printrackers | consolidados).filtered(lambda l: not l.equipo_id)
            if sin_equipo:
                mensaje += f"• {len(sin_equipo)} lecturas sin equipo asociado\n"
            
            # Lecturas en error
            en_error = (correos | printrackers | consolidados).filtered(lambda l: l.estado == 'error')
            if en_error:
                mensaje += f"• {len(en_error)} lecturas en estado de error\n"
            
            # Pendientes de aplicar
            pendientes = (correos | printrackers | consolidados).filtered(
                lambda l: l.estado == 'validado' and not l.aplicado_a_equipo
            )
            if pendientes:
                mensaje += f"• {len(pendientes)} lecturas pendientes de aplicar\n"
            
            if not sin_equipo and not en_error and not pendientes:
                mensaje += "• No se detectaron problemas\n"
            
            mensaje += "\n"
            
            # Ejemplos
            if series_todas:
                mensaje += "🔍 EJEMPLOS:\n"
                serie_ejemplo = list(series_todas)[0]
                
                correo_ej = correos.filtered(lambda l: l.serie == serie_ejemplo)[:1]
                pt_ej = printrackers.filtered(lambda l: l.serie == serie_ejemplo)[:1]
                
                if correo_ej:
                    mensaje += f"• Correo ejemplo ({serie_ejemplo}):\n"
                    mensaje += f"  BN: {correo_ej.contador_bn}, Color: {correo_ej.contador_color}, Scan: {correo_ej.contador_scan}\n"
                
                if pt_ej:
                    mensaje += f"• PrintTracker ejemplo ({serie_ejemplo}):\n"
                    mensaje += f"  BN: {pt_ej.contador_bn}, Color: {pt_ej.contador_color}, Scan: {pt_ej.contador_scan}\n"
            
            _logger.info(f"✅ Diagnóstico completado")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Diagnóstico Consolidación',
                    'message': mensaje,
                    'type': 'info',
                    'sticky': True
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error en diagnóstico: {str(e)}")
            import traceback
            _logger.error(f"❌ Traceback: {traceback.format_exc()}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error en diagnóstico: {str(e)}',
                    'type': 'danger'
                }
            }

    def action_view_equipo(self):
        """
        PARTE 3 - SIN CAMBIOS: Acción para ver el equipo relacionado
        """
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
    def accion_consolidacion_manual(self, fecha_objetivo=None):
        """
        PARTE 3 - NUEVO: Acción para ejecutar consolidación manual desde interfaz
        """
        try:
            if not fecha_objetivo:
                fecha_objetivo = date.today()
            
            _logger.info(f"✋ Consolidación manual solicitada para fecha: {fecha_objetivo}")
            
            resultado = self.consolidar_lecturas(fecha_objetivo=fecha_objetivo)
            
            if resultado:
                mensaje = f"""🎯 CONSOLIDACIÓN COMPLETADA
                
📅 Fecha: {fecha_objetivo}
✅ Consolidadas: {resultado['consolidadas']}
⚠️ Conflictos: {resultado['conflictos']}
➡️ Aplicadas directas: {resultado['aplicadas_directas']}
ℹ️ Ya consolidadas: {resultado['ya_consolidadas']}
➖ Sin datos: {resultado['sin_datos']}
❌ Errores: {resultado['errores']}
📊 Total series: {resultado['series_procesadas']}"""
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Consolidación Manual',
                        'message': mensaje,
                        'type': 'success',
                        'sticky': True
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'Error ejecutando consolidación manual',
                        'type': 'danger'
                    }
                }
                
        except Exception as e:
            _logger.error(f"❌ Error en consolidación manual: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error: {str(e)}',
                    'type': 'danger'
                }
            }

            