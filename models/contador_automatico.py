from odoo import models, fields, api
import logging
import re
import html
from html.parser import HTMLParser
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class ContadorAutomatico(models.Model):
    _name = 'contador.automatico'
    _description = 'Procesamiento automático de contadores desde correos'
    _order = 'id desc'
    _inherit = ['mail.thread']

    
    name = fields.Char('Asunto del correo', required=True, tracking=True)
    remitente = fields.Char('Remitente', tracking=True)
    contenido_original = fields.Html('Contenido original del correo')
    contenido_procesado = fields.Text('Contenido procesado (texto plano)')
    serie_detectada = fields.Char('Serie detectada', tracking=True)
    equipo_id = fields.Many2one('alquiler', string='Equipo relacionado', tracking=True)
    fecha_procesamiento = fields.Datetime('Fecha de procesamiento', readonly=True)
    original_mail_id = fields.Many2one(
        'mail.message',
        string='Correo origen',
        readonly=True,
        index=True,
        help="Mail.message procesado para evitar duplicados"
    )
    # Contadores detectados
    contador_bn_detectado = fields.Integer('Contador B/N')
    contador_color_detectado = fields.Integer('Contador Color')
    contador_scan_detectado = fields.Integer('Contador Scan')
    
    mensaje_error = fields.Text('Mensaje de error')
    procesado_automaticamente = fields.Boolean('Procesado automáticamente', default=False)
    
    # Valores anteriores del equipo
    contador_bn_anterior = fields.Integer('Contador B/N anterior')
    contador_color_anterior = fields.Integer('Contador Color anterior')
    contador_scan_anterior = fields.Integer('Contador Scan anterior')
    
    # CAMPOS PARA SISTEMA INTELIGENTE
    idioma_detectado = fields.Char('Idioma Detectado', readonly=True)
    formato_detectado = fields.Char('Formato Detectado', readonly=True) 
    confianza_deteccion = fields.Float('Confianza de Detección (%)', readonly=True)
    requiere_aprendizaje = fields.Boolean('Requiere Aprendizaje', default=False)
    estructura_detectada = fields.Text('Estructura Detectada', readonly=True)
    marca_detectada = fields.Char('Marca Detectada', readonly=True)
    palabras_clave_encontradas = fields.Text('Palabras Clave Encontradas', readonly=True)
    patrones_auto_generados = fields.Integer('Patrones Auto-generados', default=0, readonly=True)
    aprendizaje_completado = fields.Boolean('Aprendizaje Completado', default=False)
    patrones_usados = fields.Text('Patrones utilizados', readonly=True, 
                                help="Registro de qué patrones se usaron para detectar datos")
    # NUEVOS CAMPOS PARA INFORMACIÓN DEL EQUIPO
    cliente_detectado = fields.Char('Cliente Detectado', readonly=True)
    tipo_equipo_detectado = fields.Selection([
        ('color', 'Color'), 
        ('monocromatica', 'Monocromática')
    ], string='Tipo Equipo Detectado', readonly=True)


    contador_total_detectado = fields.Integer(
        'Contador Total', 
        compute='_compute_contador_total', 
        store=True,
        help="Suma de BN + Color (o solo BN para monocromáticas)"
    )
    # Agregar este campo en la clase ContadorAutomatico

    origen = fields.Selection([
        ('correo', 'Correo automático'),
        ('printtracker', 'PrintTracker'),
        ('hibrido', 'Correo + PrintTracker')
    ], string='Origen de datos', default='correo', tracking=True,
    help="Indica la fuente de donde provienen los datos del registro")
    @api.depends('contador_bn_detectado', 'contador_color_detectado', 'tipo_equipo_detectado')
    def _compute_contador_total(self):
        """
        Calcula el contador total según el tipo de equipo
        """
        for registro in self:
            if registro.tipo_equipo_detectado == 'monocromatica':
                # Para monocromáticas: solo BN
                registro.contador_total_detectado = registro.contador_bn_detectado or 0
            else:
                # Para color: BN + Color
                bn = registro.contador_bn_detectado or 0
                color = registro.contador_color_detectado or 0
                registro.contador_total_detectado = bn + color
    # CAMPO ESTADO
    estado = fields.Selection([
        ('pendiente', 'Pendiente de procesar'),
        ('procesado', 'Procesado exitosamente'),
        ('error', 'Error en procesamiento'),
        ('manual', 'Requiere intervención manual'),
        ('filtrado', 'Filtrado - No es correo de contadores')
    ], default='pendiente', tracking=True)

    # CORRECCIÓN: Agregar método de filtrado mejorado
    def _es_correo_de_contadores_mejorado(self, asunto):
        """
        FUNCIÓN MEJORADA: Filtrado de correos por palabras clave en asunto
        SINCRONIZADA con el CRON para máxima compatibilidad
        """
        if not asunto:
            return False
            
        asunto_lower = asunto.lower().strip()
        
        # Lista completa de palabras clave (sincronizada con CRON)
        palabras_validas = [
            'counter list',
            'counter page', 
            'page counter',
            'counter',
            'page count',
            'contador',
            'contadores',
            'ricoh',
            'bizhub',
            'printer counter',
            'scan counter'
        ]
        
        for palabra in palabras_validas:
            if palabra in asunto_lower:
                _logger.info(f"✅ Asunto válido detectado: '{asunto}' contiene '{palabra}'")
                return True
        
        _logger.info(f"❌ Asunto no válido para contadores: '{asunto}'")
        return False

    def detectar_idioma_automatico(self, texto):
        """
        Detecta automáticamente el idioma del contenido del correo,
        pero ignora detecciones con confianza < 30%
        """
        try:
            _logger.info("🌍 === DETECTANDO IDIOMA AUTOMÁTICAMENTE ===")
            _logger.info(f"📝 Texto a analizar: {len(texto)} caracteres")
            
            # Palabras clave por idioma para contadores
            palabras_clave = {
                'español': [
                    'número de serie', 'contador', 'negro', 'color', 'total',
                    'escaneo', 'serie', 'fecha', 'modelo', 'impresiones',
                    'bizhub', 'de envío', 'blanco y negro'
                ],
                'english': [
                    'serial number', 'counter', 'black', 'color', 'total',
                    'scan', 'serial', 'date', 'model', 'prints', 'pages',
                    'white', 'print counter', 'page counter'
                ],
                'ricoh_format': [
                    't_totalprtpgs', 't_colorprtpgs', 't_scanpgs',
                    'chargecounterdisptype', 'nº de serie'
                ],
                'bizhub_format': [
                    '[número de serie]', '[contador total]', '[contador de negro total]',
                    '[contador de color total]', '[fecha de envío]'
                ]
            }
            
            texto_lower = texto.lower()
            coincidencias = {idioma: 0 for idioma in palabras_clave}
            palabras_encontradas = {idioma: [] for idioma in palabras_clave}
            
            for idioma, lista in palabras_clave.items():
                for palabra in lista:
                    if palabra in texto_lower:
                        coincidencias[idioma] += 1
                        palabras_encontradas[idioma].append(palabra)
                        _logger.info(f"🔍 Palabra '{palabra}' encontrada en '{idioma}'")
            
            if not any(coincidencias.values()):
                _logger.warning("⚠️ No se detectaron palabras clave conocidas")
                return 'desconocido', 0.0, []
            
            idioma_detectado = max(coincidencias, key=coincidencias.get)
            max_coinc = coincidencias[idioma_detectado]
            total = len(palabras_clave[idioma_detectado])
            confianza = (max_coinc / total) * 100
            
            _logger.info(f"🎯 Idioma candidato: {idioma_detectado} ({max_coinc}/{total}) → {confianza:.1f}%")
            
            # Umbral mínimo
            if confianza < 30.0:
                _logger.warning(f"🔻 Confianza baja ({confianza:.1f}%), marcando como 'desconocido'")
                return 'desconocido', confianza, []
            
            _logger.info(f"✅ Idioma confirmado: {idioma_detectado} con {confianza:.1f}% de confianza")
            return idioma_detectado, confianza, palabras_encontradas[idioma_detectado]
        
        except Exception as e:
            _logger.error(f"❌ Error detectando idioma: {e}", exc_info=True)
            return 'error', 0.0, []

    def detectar_marca_automatico(self, texto):
        """
        Detecta automáticamente la marca del equipo
        """
        try:
            _logger.info(f"🏭 === DETECTANDO MARCA AUTOMÁTICAMENTE ===")
            
            marcas_conocidas = {
                'Bizhub': ['bizhub', 'konica', 'minolta', 'nombre del modelo'],
                'Ricoh': ['ricoh', 'T_TotalPrtPGS', 'T_ColorPrtPGS', 'nº de serie'],
                'Canon': ['canon', 'imagerunner'],
                'HP': ['hp', 'hewlett', 'packard', 'laserjet'],
                'Xerox': ['xerox', 'workcentre'],
                'Brother': ['brother'],
                'Epson': ['epson'],
                'Samsung': ['samsung', 'proxpress']
            }
                        
            texto_lower = texto.lower()
            marcas_detectadas = {}
            
            for marca, keywords in marcas_conocidas.items():
                marcas_detectadas[marca] = 0
                for keyword in keywords:
                    if keyword in texto_lower:
                        marcas_detectadas[marca] += 1
                        _logger.info(f"🏷️ Keyword '{keyword}' encontrado para marca {marca}")
            
            if any(marcas_detectadas.values()):
                marca_detectada = max(marcas_detectadas, key=marcas_detectadas.get)
                _logger.info(f"✅ Marca detectada: {marca_detectada}")
                return marca_detectada
            else:
                _logger.info("❓ Marca no identificada")
                return 'Desconocida'
                
        except Exception as e:
            _logger.error(f"❌ Error detectando marca: {e}")
            return 'Error'
    def limpiar_html_correo(self, html_content):
        """
        Convierte HTML a texto plano y limpia el contenido
        """
        try:
            _logger.info(f"🧹 Iniciando limpieza de HTML...")
            
            class MLStripper(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.reset()
                    self.fed = []
                
                def handle_data(self, d):
                    self.fed.append(d)
                
                def get_data(self):
                    return ''.join(self.fed)
            
            # Decodificar entidades HTML
            contenido = html.unescape(html_content)
            _logger.info(f"🔧 HTML decodificado: {len(contenido)} caracteres")
            
            # Remover tags HTML
            stripper = MLStripper()
            stripper.feed(contenido)
            texto_limpio = stripper.get_data()
            
            # Limpiar espacios extra y saltos de línea
            texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()
            
            _logger.info(f"✅ HTML convertido a texto: {len(texto_limpio)} caracteres")
            _logger.info(f"📄 Texto limpio (primeros 150 chars): {texto_limpio[:150]}...")
            
            return texto_limpio
            
        except Exception as e:
            _logger.error(f"❌ Error limpiando HTML: {e}")
            return str(html_content)

    def analizar_estructura_contenido(self, texto):
        """
        Analiza la estructura del contenido para identificar patrones
        """
        try:
            _logger.info(f"🔍 === ANALIZANDO ESTRUCTURA DEL CONTENIDO ===")
            
            estructura = {
                'tiene_corchetes': '[' in texto and ']' in texto,
                'tiene_dos_puntos': ':' in texto,
                'tiene_numeros_serie': bool(re.search(r'[A-Z0-9]{5,15}', texto)),
                'tiene_contadores': bool(re.search(r'\d{4,9}', texto)),
                'formato_fecha': None,
                'separadores': [],
                'patrones_numericos': [],
                'estructura_tipo': 'desconocida'
            }
            
            # Detectar formato de fecha
            if re.search(r'\d{2}/\d{2}/\d{2,4}', texto):
                estructura['formato_fecha'] = 'DD/MM/YYYY'
            elif re.search(r'\w{3}\s+\w{3}\s+\d{1,2}', texto):
                estructura['formato_fecha'] = 'Day Mon DD'
            
            # Detectar separadores
            if ',' in texto:
                estructura['separadores'].append('coma')
            if ';' in texto:
                estructura['separadores'].append('punto_coma')
            if '|' in texto:
                estructura['separadores'].append('pipe')
            
            # Detectar patrones numéricos
            numeros = re.findall(r'\d{4,9}', texto)
            estructura['patrones_numericos'] = numeros[:5]  # Primeros 5 números
            
            # Determinar tipo de estructura
            if estructura['tiene_corchetes']:
                estructura['estructura_tipo'] = 'formato_corchetes'
            elif 'T_' in texto and estructura['tiene_dos_puntos']:
                estructura['estructura_tipo'] = 'formato_ricoh'
            elif estructura['tiene_dos_puntos']:
                estructura['estructura_tipo'] = 'formato_dos_puntos'
            else:
                estructura['estructura_tipo'] = 'formato_libre'
            
            _logger.info(f"📋 Estructura detectada: {estructura['estructura_tipo']}")
            _logger.info(f"🔢 Números encontrados: {len(numeros)} números")
            _logger.info(f"📐 Características: corchetes={estructura['tiene_corchetes']}, dos_puntos={estructura['tiene_dos_puntos']}")
            
            return estructura
            
        except Exception as e:
            _logger.error(f"❌ Error analizando estructura: {e}")
            return {'estructura_tipo': 'error', 'error': str(e)}

    def generar_patrones_automaticamente(self):
        """
        Motor principal de generación automática de patrones
        """
        try:
            _logger.info(f"🤖 === INICIANDO GENERACIÓN AUTOMÁTICA DE PATRONES ===")
            _logger.info(f"📝 Analizando contenido para generar patrones...")
            
            if not self.contenido_procesado:
                _logger.warning("⚠️ No hay contenido procesado para analizar")
                return False
            
            texto = self.contenido_procesado
            patrones_generados = []
            
            # Generar patrones según el formato detectado
            formato = self.formato_detectado or 'desconocida'
            idioma = self.idioma_detectado or 'desconocido'
            marca = self.marca_detectada or 'desconocida'
            
            _logger.info(f"📋 Generando patrones para: Formato={formato}, Idioma={idioma}, Marca={marca}")
            
            # 1. GENERAR PATRONES PARA SERIE
            patrones_serie = self._generar_patrones_serie(texto, formato, idioma, marca)
            patrones_generados.extend(patrones_serie)
            
            # 2. GENERAR PATRONES PARA CONTADORES
            patrones_contadores = self._generar_patrones_contadores(texto, formato, idioma, marca)
            patrones_generados.extend(patrones_contadores)
            
            # 3. CREAR LOS PATRONES EN LA BASE DE DATOS
            patrones_creados = 0
            for patron_data in patrones_generados:
                if self._crear_patron_si_no_existe(patron_data):
                    patrones_creados += 1
            
            _logger.info(f"✅ Patrones generados automáticamente: {patrones_creados}")
            
            # 4. ACTUALIZAR INFORMACIÓN DEL REGISTRO
            self.patrones_auto_generados = patrones_creados
            
            # 5. INTENTAR PROCESAR CON LOS NUEVOS PATRONES
            if patrones_creados > 0:
                _logger.info(f"🔄 Reintentando procesamiento con nuevos patrones...")
                return self._procesar_con_patrones_generados()
            
            return patrones_creados > 0
            
        except Exception as e:
            _logger.error(f"❌ Error generando patrones automáticamente: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _generar_patrones_serie(self, texto, formato, idioma, marca):
        """
        🔢 Genera patrones automáticos para números de serie,
        basados únicamente en contexto (palabras clave, corchetes, dos puntos).
        """
        try:
            _logger.info("🔢 === GENERANDO PATRONES DE SERIE ===")
            patrones_serie = []
            posibles_series = []

            # 1) Buscamos tras palabras clave según idioma
            palabras_serie = {
                'español': ['número de serie', 'serie', 'serial'],
                'english': ['serial number', 'serial no', 'serial'],
                'bizhub_format': ['número de serie'],
                'ricoh_format': ['nº de serie']
            }
            for palabra in palabras_serie.get(idioma, []):
                patron_busqueda = rf'{re.escape(palabra)}[^\w]*([A-Z0-9]{{5,15}})'
                matches = re.findall(patron_busqueda, texto, re.IGNORECASE)
                if matches:
                    _logger.info(f"🔍 Series tras '{palabra}': {matches}")
                posibles_series.extend(matches)

            # 2) Entre corchetes solo si la etiqueta es "Serial Number" o "Número de serie"
            series_corchetes = re.findall(
                r'\[(?:Serial Number|Número de serie)\][^A-Z0-9]*([A-Z0-9]{5,15})',
                texto, re.IGNORECASE
            )
            if series_corchetes:
                _logger.info(f"🔍 Series en corchetes: {series_corchetes}")
                posibles_series.extend(series_corchetes)

            # 3) Tras dos puntos con "serial" o "serie"
            series_dos_puntos = re.findall(
                r'(?:serial no\.?|serial|serie)\s*:?\s*([A-Z0-9]{5,15})',
                texto, re.IGNORECASE
            )
            if series_dos_puntos:
                _logger.info(f"🔍 Series tras dos puntos: {series_dos_puntos}")
                posibles_series.extend(series_dos_puntos)

            _logger.info(f"🔍 Posibles series encontradas (filtradas): {posibles_series}")

            # 4) Creamos patrones solo de los valores únicos y con al menos una letra
            for i, serie in enumerate(set(posibles_series)):
                if len(serie) >= 5 and re.search(r'[A-Z]', serie):
                    patron_data = self._crear_patron_serie_automatico(
                        texto, serie, formato, idioma, marca, i
                    )
                    if patron_data:
                        patrones_serie.append(patron_data)

            _logger.info(f"✅ Patrones de serie generados: {len(patrones_serie)}")
            return patrones_serie

        except Exception as e:
            _logger.error(f"❌ Error generando patrones de serie: {e}")
            return []

    def _generar_patrones_contadores(self, texto, formato, idioma, marca):
        """
        Genera patrones automáticos para contadores
        CORRECCIÓN: Mejorado para detectar máquinas monocromas donde el total=BN
        """
        try:
            _logger.info(f"📊 === GENERANDO PATRONES DE CONTADORES ===")
            
            patrones_contadores = []
            
            # Buscar números que parezcan contadores (4-9 dígitos)
            numeros_contador = re.findall(r'\d{4,9}', texto)
            _logger.info(f"🔢 Números de contador encontrados: {numeros_contador}")
            
            # CORRECCIÓN: Detectar si es máquina monocroma
            es_monocroma = self._detectar_maquina_monocroma(texto, idioma)
            if es_monocroma:
                _logger.info("🖤 === MÁQUINA MONOCROMA DETECTADA ===")
                _logger.info("ℹ️ El contador total será usado como contador B/N")
            
            # Palabras clave por tipo de contador e idioma
            palabras_contador = {
                'español': {
                    'contador_bn': ['negro', 'blanco y negro', 'b/n', 'bn', 'monocromo'],
                    'contador_color': ['color', 'col'],
                    'contador_scan': ['escaneo', 'scan', 'total', 'fax', 'digitalizacion']
                },
                'english': {
                    'contador_bn': ['black', 'mono', 'monochrome', 'b/w'],
                    'contador_color': ['color', 'colour'],
                    'contador_scan': ['scan', 'total', 'fax', 'copy']
                },
                'bizhub_format': {
                    'contador_bn': ['contador de negro total'],
                    'contador_color': ['contador de color total'],
                    'contador_scan': ['contador total']
                },
                'ricoh_format': {
                    'contador_bn': ['T_TotalPrtPGS'],
                    'contador_color': ['T_ColorPrtPGS'],
                    'contador_scan': ['T_ScanPGS']
                }
            }
            
            # CORRECCIÓN: Si es monocroma, agregar "total" a contador_bn
            if es_monocroma:
                for idioma_key in palabras_contador:
                    if 'total' not in palabras_contador[idioma_key]['contador_bn']:
                        palabras_contador[idioma_key]['contador_bn'].append('total')
                    # Remover color para máquinas monocromas
                    palabras_contador[idioma_key]['contador_color'] = []
            
            palabras_idioma = palabras_contador.get(idioma, palabras_contador.get('english', {}))
            
            # Generar patrones para cada tipo de contador
            for tipo_contador, palabras in palabras_idioma.items():
                # Saltar contador_color si es monocroma
                if es_monocroma and tipo_contador == 'contador_color':
                    continue
                    
                for palabra in palabras:
                    patron_data = self._crear_patron_contador_automatico(
                        texto, palabra, tipo_contador, formato, idioma, marca
                    )
                    if patron_data:
                        patrones_contadores.append(patron_data)
            
            _logger.info(f"✅ Patrones de contadores generados: {len(patrones_contadores)}")
            return patrones_contadores
            
        except Exception as e:
            _logger.error(f"❌ Error generando patrones de contadores: {e}")
            return []

    def _detectar_maquina_monocroma(self, texto, idioma):
        """
        NUEVO: Detecta si la máquina es monocroma analizando el contenido
        """
        try:
            texto_lower = texto.lower()
            
            # Indicadores de máquina monocroma
            indicadores_monocroma = [
                'monochrome', 'monocromo', 'mono', 'b/w', 'black and white',
                'blanco y negro'
            ]
            
            # Buscar ausencia de contadores de color específicos
            sin_color = True
            indicadores_color = ['color counter', 'contador color', 'color total']
            
            for indicador in indicadores_color:
                if indicador in texto_lower:
                    sin_color = False
                    break
            
            # Buscar presencia de indicadores monocroma
            con_mono = False
            for indicador in indicadores_monocroma:
                if indicador in texto_lower:
                    con_mono = True
                    break
            
            # Si tiene indicadores mono Y no tiene contadores color específicos
            es_monocroma = con_mono or sin_color
            
            _logger.info(f"🔍 Análisis monocroma: con_mono={con_mono}, sin_color={sin_color}, resultado={es_monocroma}")
            
            return es_monocroma
            
        except Exception as e:
            _logger.error(f"❌ Error detectando máquina monocroma: {e}")
            return False

    def _crear_patron_serie_automatico(self, texto, serie, formato, idioma, marca, indice):
        """
        Crea un patrón automático para una serie específica
        """
        try:
            # Encontrar el contexto de la serie en el texto
            posicion = texto.upper().find(serie.upper())
            if posicion == -1:
                return None
            
            # Extraer contexto antes de la serie (30 caracteres)
            inicio_contexto = max(0, posicion - 30)
            contexto_previo = texto[inicio_contexto:posicion]
            
            # Generar patrón basado en el contexto
            if '[' in contexto_previo and ']' in contexto_previo:
                # Formato corchetes
                etiqueta = re.search(r'\[([^\]]+)\]', contexto_previo)
                if etiqueta:
                    etiqueta_texto = etiqueta.group(1)
                    patron_regex = rf'\[{re.escape(etiqueta_texto)}\][^A-Z0-9]*([A-Z0-9]{{5,15}})'
                else:
                    patron_regex = rf'\[[^\]]*serie[^\]]*\][^A-Z0-9]*([A-Z0-9]{{5,15}})'
            elif ':' in contexto_previo:
                # Formato dos puntos
                palabras_antes = re.findall(r'\b\w+\b', contexto_previo.lower())
                if palabras_antes:
                    ultima_palabra = palabras_antes[-1]
                    patron_regex = rf'{re.escape(ultima_palabra)}\s*:?\s*([A-Z0-9]{{5,15}})'
                else:
                    patron_regex = rf'[^A-Z0-9]+([A-Z0-9]{{5,15}})'
            else:
                # Formato libre - buscar palabra clave más cercana
                palabras_serie = ['serie', 'serial', 'model', 'número']
                palabra_encontrada = None
                for palabra in palabras_serie:
                    if palabra in contexto_previo.lower():
                        palabra_encontrada = palabra
                        break
                
                if palabra_encontrada:
                    patron_regex = rf'{re.escape(palabra_encontrada)}[^A-Z0-9]*([A-Z0-9]{{5,15}})'
                else:
                    patron_regex = rf'\b([A-Z0-9]{{5,15}})\b'
            
            # Crear datos del patrón
            patron_data = {
                'name': f'Serie {marca} Auto-generada {indice+1}',
                'tipo': 'serie',
                'patron_regex': patron_regex,
                'descripcion': f'Patrón auto-generado para serie {serie} en formato {formato}',
                'ejemplo': f'Detecta series como: {serie}',
                'orden': 1,
                'activo': True,
                'auto_generado': True,  # CORRECCIÓN: Marcar como auto-generado
                'idioma_patron': idioma,
                'marca_patron': marca,
                'formato_origen': formato
            }
            
            _logger.info(f"🎯 Patrón de serie creado: {patron_regex}")
            return patron_data
            
        except Exception as e:
            _logger.error(f"❌ Error creando patrón de serie: {e}")
            return None

    def _crear_patron_contador_automatico(self, texto, palabra_clave, tipo_contador, formato, idioma, marca):
        """
        Crea un patrón automático para un contador específico
        """
        try:
            # Buscar la palabra clave en el texto
            if palabra_clave.lower() not in texto.lower():
                return None
            
            # Generar patrón según el formato detectado
            if formato == 'formato_corchetes':
                # Formato [Contador de negro total],00183098
                patron_regex = rf'\[.*{re.escape(palabra_clave)}.*\][^0-9]*(\d{{4,9}})'
            elif formato == 'formato_ricoh':
                # Formato T_TotalPrtPGS:36089
                patron_regex = rf'{re.escape(palabra_clave)}\s*:?\s*(\d{{4,9}})'
            elif formato == 'formato_dos_puntos':
                # Formato genérico con dos puntos
                patron_regex = rf'(?:contador\s*)?{re.escape(palabra_clave)}\s*:?\s*(\d{{4,9}})'
            else:
                # Formato libre
                patron_regex = rf'{re.escape(palabra_clave)}[^0-9]*(\d{{4,9}})'
            
            # Nombres descriptivos por tipo
            nombres_tipo = {
                'contador_bn': 'B/N',
                'contador_color': 'Color', 
                'contador_scan': 'Scan/Total'
            }
            
            nombre_tipo = nombres_tipo.get(tipo_contador, tipo_contador)
            
            patron_data = {
                'name': f'Contador {nombre_tipo} {marca} Auto-generado',
                'tipo': tipo_contador,
                'patron_regex': patron_regex,
                'descripcion': f'Patrón auto-generado para {nombre_tipo} basado en "{palabra_clave}"',
                'ejemplo': f'Detecta contadores con palabra clave: {palabra_clave}',
                'orden': 1,
                'activo': True,
                'auto_generado': True,  # CORRECCIÓN: Marcar como auto-generado
                'idioma_patron': idioma,
                'marca_patron': marca,
                'formato_origen': formato
            }
            
            _logger.info(f"📊 Patrón de contador creado: {nombre_tipo} → {patron_regex}")
            return patron_data
            
        except Exception as e:
            _logger.error(f"❌ Error creando patrón de contador: {e}")
            return None

    def _crear_patron_si_no_existe(self, patron_data):
        """
        Crea un patrón solo si no existe uno similar
        """
        try:
            # Buscar patrones similares existentes
            patrones_similares = self.env['patron.contador'].search([
                ('tipo', '=', patron_data['tipo']),
                ('patron_regex', '=', patron_data['patron_regex']),
                ('activo', '=', True)
            ])
            
            if patrones_similares:
                _logger.info(f"⏭️ Patrón similar ya existe: {patron_data['name']}")
                return False
            
            # Verificar si existe uno con el mismo nombre
            patron_mismo_nombre = self.env['patron.contador'].search([
                ('name', '=', patron_data['name'])
            ])
            
            if patron_mismo_nombre:
                # Modificar el nombre para hacerlo único
                patron_data['name'] = f"{patron_data['name']} v{len(patron_mismo_nombre) + 1}"
            
            # Crear el patrón
            nuevo_patron = self.env['patron.contador'].create(patron_data)
            _logger.info(f"✅ Patrón creado: {nuevo_patron.name} (ID: {nuevo_patron.id})")
            
            return True
            
        except Exception as e:
            _logger.error(f"❌ Error creando patrón: {e}")
            return False

    def _procesar_con_patrones_generados(self):
        """
        Intenta procesar el correo con los patrones recién generados
        """
        try:
            _logger.info(f"🔄 === PROCESANDO CON PATRONES GENERADOS ===")
            
            texto = self.contenido_procesado
            
            # Buscar serie usando los nuevos patrones
            serie_encontrada = self.env['patron.contador'].buscar_por_tipo('serie', texto)
            if serie_encontrada:
                self.serie_detectada = serie_encontrada
                _logger.info(f"✅ Serie detectada con patrones generados: {serie_encontrada}")
            
            # Buscar contadores usando los nuevos patrones
            contadores_encontrados = {}
            for tipo in ['contador_bn', 'contador_color', 'contador_scan']:
                resultado = self.env['patron.contador'].buscar_por_tipo(tipo, texto)
                if resultado:
                    contadores_encontrados[tipo] = resultado
                    _logger.info(f"✅ {tipo} detectado: {resultado}")
            
            # Actualizar campos de contadores detectados
            if 'contador_bn' in contadores_encontrados:
                self.contador_bn_detectado = contadores_encontrados['contador_bn']
            
            if 'contador_color' in contadores_encontrados:
                self.contador_color_detectado = contadores_encontrados['contador_color']
            
            if 'contador_scan' in contadores_encontrados:
                self.contador_scan_detectado = contadores_encontrados['contador_scan']
            
            # Evaluar si el procesamiento fue exitoso
            if serie_encontrada and contadores_encontrados:
                # Buscar equipo
                equipo = self.buscar_equipo_por_serie(serie_encontrada)
                if equipo:
                    self.equipo_id = equipo.id
                    # Actualizar contadores del equipo
                    self.actualizar_contadores_equipo(equipo, contadores_encontrados)
                    self.estado = 'procesado'
                    self.procesado_automaticamente = True
                    self.aprendizaje_completado = True
                    _logger.info(f"🎉 Procesamiento exitoso con patrones generados")
                    return True
                else:
                    self.estado = 'manual'
                    self.mensaje_error = f"Serie detectada pero equipo no encontrado: {serie_encontrada}"
            elif serie_encontrada:
                self.estado = 'manual' 
                self.mensaje_error = "Serie detectada pero sin contadores válidos"
            elif contadores_encontrados:
                self.estado = 'manual'
                self.mensaje_error = "Contadores detectados pero sin serie válida"
            else:
                self.estado = 'manual'
                self.mensaje_error = "Patrones generados pero no se detectaron valores"
            
            self.fecha_procesamiento = fields.Datetime.now()
            return False
            
        except Exception as e:
            _logger.error(f"❌ Error procesando con patrones generados: {e}")
            self.estado = 'error'
            self.mensaje_error = f"Error procesando con patrones generados: {str(e)}"
            return False

    def identificar_tipo_equipo_por_serie(self, serie):
        """
        NUEVO: Identifica si el equipo es color o monocromático basado en la serie
        """
        try:
            if not serie:
                return None, None, None
            
            _logger.info(f"🔍 Identificando tipo de equipo para serie: {serie}")
            
            # Buscar equipo por serie
            equipo = self.buscar_equipo_por_serie(serie)
            if not equipo:
                _logger.warning(f"❌ No se encontró equipo con serie: {serie}")
                return None, None, None
            
            # Obtener información del equipo
            tipo_maquina = equipo.tipo_maquina_id if hasattr(equipo, 'tipo_maquina_id') else None
            cliente = equipo.cliente_id if hasattr(equipo, 'cliente_id') else None
            
            _logger.info(f"✅ Equipo encontrado: ID={equipo.id}")
            _logger.info(f"🎨 Tipo: {tipo_maquina}")
            _logger.info(f"👤 Cliente: {cliente.name if cliente else 'Sin cliente'}")
            
            return equipo, tipo_maquina, cliente
            
        except Exception as e:
            _logger.error(f"❌ Error identificando tipo de equipo: {e}")
            return None, None, None


    def asignar_contadores_por_tipo_equipo(self, contadores_detectados, tipo_maquina):
        """
        CORREGIDO DEFINITIVAMENTE: Asigna contadores SIN cálculos incorrectos
        PROBLEMA SOLUCIONADO: Para COLOR, usar valores directos sin restar
        """
        try:
            _logger.info(f"📊 === ASIGNANDO CONTADORES CORREGIDO ===")
            _logger.info(f"🎨 Tipo de máquina: {tipo_maquina}")
            _logger.info(f"🏭 Marca detectada: {self.marca_detectada}")
            _logger.info(f"📄 Formato detectado: {self.formato_detectado}")
            _logger.info(f"📊 Contadores detectados originales: {contadores_detectados}")
            
            contadores_finales = {}
            
            # DETECTAR FORMATO DEL CORREO
            formato = getattr(self, 'formato_detectado', 'desconocido')
            marca = getattr(self, 'marca_detectada', 'Desconocida')
            
            _logger.info(f"🔍 Formato: {formato}, Marca: {marca}")
            
            # LÓGICA POR FORMATO DETECTADO
            if formato == 'formato_corchetes':
                _logger.info("🏭 === FORMATO CORCHETES (KONICA MINOLTA) ===")
                
                if tipo_maquina == 'monocromatica':
                    _logger.info("🖤 KONICA MINOLTA MONOCROMÁTICA")
                    
                    # Para Konica Minolta monocromas:
                    # [Total Counter] = Total de páginas impresas (usar como BN)
                    # [Total Scan/Fax Counter] = Total de escaneos
                    
                    if 'contador_bn' in contadores_detectados:
                        # [Total Counter] va a contador_bn para monocromas
                        contadores_finales['contador_bn'] = contadores_detectados['contador_bn']
                        _logger.info(f"🖤 [Total Counter] → BN: {contadores_detectados['contador_bn']}")
                    
                    if 'contador_scan' in contadores_detectados:
                        # [Total Scan/Fax Counter] va a contador_scan
                        contadores_finales['contador_scan'] = contadores_detectados['contador_scan']
                        _logger.info(f"📄 [Scan/Fax Counter] → Scan: {contadores_detectados['contador_scan']}")
                    
                    # Color siempre 0 para monocromas
                    contadores_finales['contador_color'] = 0
                    _logger.info("🚫 Color = 0 (monocromática)")
                    
                elif tipo_maquina == 'color':
                    _logger.info("🌈 KONICA MINOLTA COLOR")
                    
                    # CORRECCIÓN CRÍTICA: Para Konica Minolta COLOR con contadores separados
                    # [Total Black Counter] = Páginas BN directas (NO restar nada)
                    # [Total Color Counter] = Páginas color directas
                    # [Total Scan/Fax Counter] = Escaneos
                    
                    # DETECTAR QUÉ TIPO DE CORREO COLOR ES
                    tiene_black_separado = 'contador_bn' in contadores_detectados
                    tiene_color_separado = 'contador_color' in contadores_detectados
                    
                    _logger.info(f"🔍 Análisis de contadores separados:")
                    _logger.info(f"   Tiene Black separado: {tiene_black_separado}")
                    _logger.info(f"   Tiene Color separado: {tiene_color_separado}")
                    
                    if tiene_black_separado and tiene_color_separado:
                        # CASO 1: Contadores separados - USAR DIRECTAMENTE (SIN CALCULAR)
                        _logger.info("✅ CASO: Contadores Black y Color separados")
                        
                        contadores_finales['contador_bn'] = contadores_detectados['contador_bn']
                        contadores_finales['contador_color'] = contadores_detectados['contador_color']
                        
                        _logger.info(f"🖤 [Total Black Counter] → BN: {contadores_detectados['contador_bn']} (DIRECTO)")
                        _logger.info(f"🎨 [Total Color Counter] → Color: {contadores_detectados['contador_color']} (DIRECTO)")
                        
                    elif tiene_black_separado and not tiene_color_separado:
                        # CASO 2: Solo Black separado
                        _logger.info("⚠️ CASO: Solo Black separado, Color = 0")
                        
                        contadores_finales['contador_bn'] = contadores_detectados['contador_bn']
                        contadores_finales['contador_color'] = 0
                        
                        _logger.info(f"🖤 [Total Black Counter] → BN: {contadores_detectados['contador_bn']}")
                        _logger.info("🎨 Color = 0 (no detectado por separado)")
                        
                    elif not tiene_black_separado and tiene_color_separado:
                        # CASO 3: Solo Color separado (raro)
                        _logger.info("⚠️ CASO: Solo Color separado, BN = 0")
                        
                        contadores_finales['contador_bn'] = 0
                        contadores_finales['contador_color'] = contadores_detectados['contador_color']
                        
                        _logger.info("🖤 BN = 0 (no detectado por separado)")
                        _logger.info(f"🎨 [Total Color Counter] → Color: {contadores_detectados['contador_color']}")
                        
                    else:
                        # CASO 4: Ninguno separado - buscar total genérico
                        _logger.info("⚠️ CASO: Sin contadores separados, buscando total genérico")
                        
                        # Podría haber un [Total Counter] genérico que necesita distribución
                        total_generico = contadores_detectados.get('contador_total', 0)
                        
                        if total_generico > 0:
                            # Distribuir de alguna manera - pero sin información no podemos
                            contadores_finales['contador_bn'] = total_generico
                            contadores_finales['contador_color'] = 0
                            _logger.info(f"🖤 Total genérico → BN: {total_generico}")
                            _logger.info("🎨 Color = 0 (sin información para distribuir)")
                        else:
                            contadores_finales['contador_bn'] = 0
                            contadores_finales['contador_color'] = 0
                            _logger.warning("⚠️ No se encontraron contadores válidos")
                    
                    # Scan siempre directo
                    contadores_finales['contador_scan'] = contadores_detectados.get('contador_scan', 0)
                    _logger.info(f"📄 Scan: {contadores_finales['contador_scan']}")
            
            elif formato == 'formato_ricoh':
                _logger.info("🏭 === FORMATO RICOH ===")
                
                # Para Ricoh: usar los contadores tal como vienen
                # T_TotalPrtPGS = Total páginas impresas
                # T_ColorPrtPGS = Páginas color (si existe)
                # T_ScanPGS = Páginas escaneadas
                
                if tipo_maquina == 'monocromatica':
                    _logger.info("🖤 RICOH MONOCROMÁTICA")
                    contadores_finales['contador_bn'] = contadores_detectados.get('contador_bn', 0)
                    contadores_finales['contador_color'] = 0
                    contadores_finales['contador_scan'] = contadores_detectados.get('contador_scan', 0)
                else:
                    _logger.info("🌈 RICOH COLOR")
                    contadores_finales['contador_bn'] = contadores_detectados.get('contador_bn', 0)
                    contadores_finales['contador_color'] = contadores_detectados.get('contador_color', 0)
                    contadores_finales['contador_scan'] = contadores_detectados.get('contador_scan', 0)
            
            else:
                _logger.info("🏭 === FORMATO GENÉRICO ===")
                
                # Para otros formatos: usar contadores tal como vienen
                if tipo_maquina == 'monocromatica':
                    _logger.info("🖤 MÁQUINA MONOCROMÁTICA GENÉRICA")
                    contadores_finales['contador_bn'] = contadores_detectados.get('contador_bn', 0)
                    contadores_finales['contador_color'] = 0
                    contadores_finales['contador_scan'] = contadores_detectados.get('contador_scan', 0)
                else:
                    _logger.info("🌈 MÁQUINA COLOR GENÉRICA")
                    contadores_finales['contador_bn'] = contadores_detectados.get('contador_bn', 0)
                    contadores_finales['contador_color'] = contadores_detectados.get('contador_color', 0)
                    contadores_finales['contador_scan'] = contadores_detectados.get('contador_scan', 0)
            
            # VALIDACIÓN FINAL: Asegurar que todos los campos existen
            for campo in ['contador_bn', 'contador_color', 'contador_scan']:
                if campo not in contadores_finales:
                    contadores_finales[campo] = 0
                elif contadores_finales[campo] is None:
                    contadores_finales[campo] = 0
            
            _logger.info(f"✅ === CONTADORES FINALES ASIGNADOS ===")
            _logger.info(f"🖤 BN: {contadores_finales['contador_bn']}")
            _logger.info(f"🎨 Color: {contadores_finales['contador_color']}")
            _logger.info(f"📄 Scan: {contadores_finales['contador_scan']}")
            
            # ACTUALIZAR LOS CAMPOS DEL REGISTRO
            self.write({
                'contador_bn_detectado': contadores_finales['contador_bn'],
                'contador_color_detectado': contadores_finales['contador_color'],
                'contador_scan_detectado': contadores_finales['contador_scan']
            })
            
            _logger.info(f"💾 Campos del registro actualizados correctamente")
            
            return contadores_finales
            
        except Exception as e:
            _logger.error(f"❌ Error asignando contadores: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return contadores_detectados
    
    def procesar_correo_inteligente(self):
        """
        Procesamiento inteligente del correo con análisis y generación automática
        MODIFICADO: Verificación de registro existente del día antes de procesar
        """
        try:
            _logger.info(f"🧠 === INICIO PROCESAMIENTO INTELIGENTE ===")
            _logger.info(f"📧 Registro ID={self.id}, Asunto='{self.name}'")

            # 1. VERIFICAR SI ES CORREO DE CONTADORES
            if not self._es_correo_de_contadores_mejorado(self.name):
                self.estado = 'filtrado'
                self.mensaje_error = 'Asunto no corresponde a correo de contadores'
                _logger.info(f"🚫 Correo filtrado - No es de contadores")
                return False

            # 2. LIMPIAR CONTENIDO HTML
            if self.contenido_original:
                texto_limpio = self.limpiar_html_correo(self.contenido_original)
                self.contenido_procesado = texto_limpio
            else:
                texto_limpio = self.name or ""

            # 3. ANÁLISIS INTELIGENTE DEL CONTENIDO
            _logger.info(f"🔍 === FASE: ANÁLISIS INTELIGENTE ===")

            # Detectar idioma
            idioma, confianza_idioma, palabras_clave = self.detectar_idioma_automatico(texto_limpio)
            self.idioma_detectado = idioma
            self.confianza_deteccion = confianza_idioma
            self.palabras_clave_encontradas = ', '.join(palabras_clave)

            # Detectar marca
            marca = self.detectar_marca_automatico(texto_limpio)
            self.marca_detectada = marca

            # Analizar estructura
            estructura = self.analizar_estructura_contenido(texto_limpio)
            self.formato_detectado = estructura.get('estructura_tipo', 'desconocida')
            self.estructura_detectada = str(estructura)

            _logger.info(f"🌍 Idioma: {idioma} ({confianza_idioma:.1f}%)")
            _logger.info(f"🏭 Marca: {marca}")
            _logger.info(f"📐 Formato: {estructura.get('estructura_tipo')}")

            # 4. INTENTAR PROCESAMIENTO CON PATRONES EXISTENTES
            _logger.info(f"📊 === FASE: PROCESAMIENTO CON PATRONES EXISTENTES ===")

            serie_encontrada = self.buscar_serie_dinamico(texto_limpio)
            # Descartar si la "serie" es solo dígitos
            if serie_encontrada and serie_encontrada.isdigit():
                _logger.warning(f"💥 Serie descartada tras validación: '{serie_encontrada}'")
                serie_encontrada = None

            # ===== NUEVA LÓGICA: VERIFICACIÓN DE REGISTRO EXISTENTE =====
            if serie_encontrada:
                _logger.info(f"🔍 === VERIFICANDO REGISTRO EXISTENTE DEL DÍA ===")
                _logger.info(f"🎯 Serie detectada: {serie_encontrada}")
                
                # BUSCAR si ya existe registro del día para esta serie
                registro_existente = self.buscar_registro_del_dia(serie_encontrada)
                
                if registro_existente:
                    _logger.warning(f"🚫 YA EXISTE registro para serie {serie_encontrada} hoy")
                    _logger.warning(f"📋 Registro existente: ID={registro_existente.id}")
                    _logger.warning(f"📅 Fecha registro existente: {registro_existente.fecha_procesamiento}")
                    _logger.warning(f"📊 Estado registro existente: {registro_existente.estado}")
                    _logger.warning(f"🔗 Origen registro existente: {getattr(registro_existente, 'origen', 'No definido')}")
                    
                    # Marcar este correo como filtrado
                    self.estado = 'filtrado'
                    self.mensaje_error = f'Ya existe registro del día para esta serie (ID: {registro_existente.id})'
                    self.write({'fecha_procesamiento': fields.Datetime.now()})
                    
                    _logger.info(f"🚫 Correo descartado - Registro del día ya existe")
                    return False
                else:
                    _logger.info(f"✅ No existe registro para {serie_encontrada} hoy - Continuando procesamiento")

            contadores_encontrados = self.buscar_patrones_contadores_dinamico(texto_limpio)

            # ===== LÓGICA ORIGINAL: IDENTIFICACIÓN DE TIPO DE EQUIPO =====
            equipo_detectado = None
            tipo_maquina_detectado = None
            cliente_detectado = None

            if serie_encontrada:
                _logger.info(f"🎯 === IDENTIFICANDO TIPO DE EQUIPO POR SERIE ===")
                
                # Identificar tipo de equipo por serie
                equipo_detectado, tipo_maquina_detectado, cliente_detectado = self.identificar_tipo_equipo_por_serie(serie_encontrada)
                
                if equipo_detectado and tipo_maquina_detectado:
                    _logger.info(f"🎯 Equipo identificado: {equipo_detectado.id} - Tipo: {tipo_maquina_detectado}")
                    
                    # Asignar contadores según tipo de equipo
                    contadores_encontrados = self.asignar_contadores_por_tipo_equipo(
                        contadores_encontrados, tipo_maquina_detectado
                    )
                    
                    # Actualizar campos del registro INMEDIATAMENTE
                    _logger.info(f"📊 === ACTUALIZANDO CAMPOS DEL REGISTRO ===")
                    _logger.info(f"📊 Contadores procesados: {contadores_encontrados}")
                    
                    # Asignar serie
                    self.serie_detectada = serie_encontrada
                    _logger.info(f"✅ Serie asignada: {self.serie_detectada}")
                    
                    # Asignar contadores al registro
                    if 'contador_bn' in contadores_encontrados:
                        self.contador_bn_detectado = contadores_encontrados['contador_bn']
                        _logger.info(f"✅ BN asignado: {self.contador_bn_detectado}")
                    
                    if 'contador_color' in contadores_encontrados:
                        self.contador_color_detectado = contadores_encontrados['contador_color']
                        _logger.info(f"✅ Color asignado: {self.contador_color_detectado}")
                    
                    if 'contador_scan' in contadores_encontrados:
                        self.contador_scan_detectado = contadores_encontrados['contador_scan']
                        _logger.info(f"✅ Scan asignado: {self.contador_scan_detectado}")
                    
                    # Guardar información adicional del equipo
                    self.tipo_equipo_detectado = tipo_maquina_detectado
                    if cliente_detectado:
                        self.cliente_detectado = cliente_detectado.name
                        _logger.info(f"👤 Cliente detectado: {cliente_detectado.name}")
                    
                    _logger.info(f"📊 === VERIFICACIÓN FINAL DE ASIGNACIÓN ===")
                    _logger.info(f"   BN: {self.contador_bn_detectado}")
                    _logger.info(f"   Color: {self.contador_color_detectado}")
                    _logger.info(f"   Scan: {self.contador_scan_detectado}")
                    _logger.info(f"   Serie: {self.serie_detectada}")
                    
                else:
                    _logger.warning(f"⚠️ No se pudo identificar tipo de equipo para serie: {serie_encontrada}")
                    
                    # Asignar datos básicos aunque no se identifique el equipo
                    self.serie_detectada = serie_encontrada
                    if 'contador_bn' in contadores_encontrados:
                        self.contador_bn_detectado = contadores_encontrados['contador_bn']
                    if 'contador_color' in contadores_encontrados:
                        self.contador_color_detectado = contadores_encontrados['contador_color']
                    if 'contador_scan' in contadores_encontrados:
                        self.contador_scan_detectado = contadores_encontrados['contador_scan']

            # 5. SI NO ENCONTRÓ DATOS, GENERAR PATRONES AUTOMÁTICAMENTE
            if not serie_encontrada or not contadores_encontrados:
                _logger.info(f"🤖 === FASE: GENERACIÓN AUTOMÁTICA DE PATRONES ===")
                _logger.warning(f"⚠️ Patrones existentes insuficientes. Generando automáticamente...")

                self.requiere_aprendizaje = True

                # Generar patrones automáticamente
                if self.generar_patrones_automaticamente():
                    _logger.info(f"✅ Patrones generados y aplicados exitosamente")
                else:
                    _logger.warning(f"⚠️ No se pudieron generar patrones efectivos")
            else:
                # Procesamiento exitoso con patrones existentes
                _logger.info(f"✅ Procesamiento exitoso con patrones existentes")

                # Usar equipo ya detectado o buscarlo de nuevo
                if equipo_detectado:
                    equipo = equipo_detectado
                else:
                    equipo = self.buscar_equipo_por_serie(serie_encontrada) if serie_encontrada else None
                
                if equipo and contadores_encontrados:
                    self.equipo_id = equipo.id
                    
                    # Pasar contadores_encontrados que ya están procesados
                    self.actualizar_contadores_equipo(equipo, contadores_encontrados)
                    self.estado = 'procesado'
                    self.procesado_automaticamente = True
                    _logger.info(f"🎉 === PROCESAMIENTO EXITOSO CON TIPO DE EQUIPO ===")
                    _logger.info(f"🎯 Equipo: {equipo.id} - Tipo: {tipo_maquina_detectado}")
                    _logger.info(f"👤 Cliente: {cliente_detectado.name if cliente_detectado else 'N/A'}")
                elif serie_encontrada:
                    self.estado = 'manual'
                    self.mensaje_error = f"Serie detectada pero equipo no encontrado: {serie_encontrada}"
                else:
                    self.estado = 'manual'
                    self.mensaje_error = "No se detectó número de serie"

            # 6. ACTUALIZAR fecha_procesamiento
            self.write({'fecha_procesamiento': fields.Datetime.now()})

            _logger.info(f"📊 === RESUMEN PROCESAMIENTO INTELIGENTE ===")
            _logger.info(f"Estado final: {self.estado}")
            _logger.info(f"Idioma: {self.idioma_detectado}")
            _logger.info(f"Marca: {self.marca_detectada}")
            _logger.info(f"Formato: {self.formato_detectado}")
            _logger.info(f"Serie: {self.serie_detectada or 'No detectada'}")
            _logger.info(f"Tipo equipo: {self.tipo_equipo_detectado or 'No detectado'}")
            _logger.info(f"Cliente: {self.cliente_detectado or 'No detectado'}")
            _logger.info(f"Requiere aprendizaje: {self.requiere_aprendizaje}")
            _logger.info(f"Patrones auto-generados: {self.patrones_auto_generados}")
            _logger.info(f"🏁 === FIN PROCESAMIENTO INTELIGENTE ===")

            return True

        except Exception as e:
            _logger.error(f"❌ === ERROR EN PROCESAMIENTO INTELIGENTE ===")
            _logger.error(f"Error: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")

            self.estado = 'error'
            self.mensaje_error = f"Error en procesamiento inteligente: {str(e)}"
            self.write({'fecha_procesamiento': fields.Datetime.now()})
            return False


       
    

    def aprender_de_procesamiento_manual(self):
        """
        Aprende de correcciones manuales para mejorar patrones futuros
        """
        try:
            _logger.info(f"🎓 === APRENDIENDO DE PROCESAMIENTO MANUAL ===")
            
            if not self.serie_detectada or not any([
                self.contador_bn_detectado,
                self.contador_color_detectado, 
                self.contador_scan_detectado
            ]):
                _logger.warning("⚠️ No hay datos manuales suficientes para aprender")
                return False
            
            # Crear patrones basados en los valores manuales
            texto = self.contenido_procesado
            patrones_aprendidos = 0
            
            # Aprender patrón de serie
            if self.serie_detectada:
                if self._aprender_patron_serie_manual(texto, self.serie_detectada):
                    patrones_aprendidos += 1
            
            # Aprender patrones de contadores
            if self.contador_bn_detectado:
                if self._aprender_patron_contador_manual(texto, self.contador_bn_detectado, 'contador_bn'):
                    patrones_aprendidos += 1
            
            if self.contador_color_detectado:
                if self._aprender_patron_contador_manual(texto, self.contador_color_detectado, 'contador_color'):
                    patrones_aprendidos += 1
            
            if self.contador_scan_detectado:
                if self._aprender_patron_contador_manual(texto, self.contador_scan_detectado, 'contador_scan'):
                    patrones_aprendidos += 1
            
            _logger.info(f"🎓 Patrones aprendidos del procesamiento manual: {patrones_aprendidos}")
            
            # Marcar como aprendido
            self.requiere_aprendizaje = False
            self.aprendizaje_completado = True
            self.patrones_auto_generados += patrones_aprendidos
            
            return patrones_aprendidos > 0
            
        except Exception as e:
            _logger.error(f"❌ Error en aprendizaje manual: {e}")
            return False

    def _aprender_patron_serie_manual(self, texto, serie_manual):
        """
        Aprende patrón de serie basado en valor manual
        """
        try:
            # Encontrar dónde está la serie en el texto
            posicion = texto.upper().find(serie_manual.upper())
            if posicion == -1:
                return False
            
            # Analizar contexto
            inicio_contexto = max(0, posicion - 50)
            contexto = texto[inicio_contexto:posicion + len(serie_manual) + 10]
            
            # Generar patrón más específico
            patron_regex = self._extraer_patron_de_contexto(contexto, serie_manual)
            
            if patron_regex:
                patron_data = {
                    'name': f'Serie Aprendida Manual - {self.marca_detectada}',
                    'tipo': 'serie',
                    'patron_regex': patron_regex,
                    'descripcion': f'Patrón aprendido de corrección manual',
                    'ejemplo': f'Detecta: {serie_manual}',
                    'orden': 1,
                    'activo': True,
                    'auto_generado': True,
                    'validado_manualmente': True
                }
                
                return self._crear_patron_si_no_existe(patron_data)
            
            return False
            
        except Exception as e:
            _logger.error(f"❌ Error aprendiendo patrón de serie: {e}")
            return False

    def _aprender_patron_contador_manual(self, texto, valor_manual, tipo_contador):
        """
        Aprende patrón de contador basado en valor manual
        """
        try:
            # Encontrar dónde está el contador en el texto
            str_valor = str(valor_manual).zfill(8)  # Pad con ceros
            
            # Buscar el valor en diferentes formatos
            posibles_posiciones = []
            for formato_buscar in [str(valor_manual), str_valor, str_valor.lstrip('0')]:
                pos = texto.find(formato_buscar)
                if pos != -1:
                    posibles_posiciones.append((pos, formato_buscar))
            
            if not posibles_posiciones:
                return False
            
            # Usar la primera posición encontrada
            posicion, valor_encontrado = posibles_posiciones[0]
            
            # Analizar contexto antes del número
            inicio_contexto = max(0, posicion - 50)
            contexto_previo = texto[inicio_contexto:posicion]
            
            # Generar patrón basado en contexto
            patron_regex = self._extraer_patron_contador_de_contexto(contexto_previo, tipo_contador)
            
            if patron_regex:
                nombres_tipo = {
                    'contador_bn': 'B/N',
                    'contador_color': 'Color',
                    'contador_scan': 'Scan'
                }
                
                patron_data = {
                    'name': f'Contador {nombres_tipo[tipo_contador]} Aprendido Manual',
                    'tipo': tipo_contador,
                    'patron_regex': patron_regex,
                    'descripcion': f'Patrón aprendido de corrección manual para {nombres_tipo[tipo_contador]}',
                    'ejemplo': f'Detecta valores como: {valor_manual}',
                    'orden': 1,
                    'activo': True,
                    'auto_generado': True,
                    'validado_manualmente': True
                }
                
                return self._crear_patron_si_no_existe(patron_data)
            
            return False
            
        except Exception as e:
            _logger.error(f"❌ Error aprendiendo patrón de contador: {e}")
            return False

    def _extraer_patron_de_contexto(self, contexto, valor):
        """
        Extrae un patrón regex del contexto que rodea un valor
        """
        try:
            # Buscar estructuras comunes
            if '[' in contexto and ']' in contexto:
                # Formato corchetes
                match = re.search(r'\[([^\]]+)\]', contexto)
                if match:
                    etiqueta = match.group(1)
                    return rf'\[{re.escape(etiqueta)}\][^A-Z0-9]*([A-Z0-9]{{5,15}})'
            
            elif ':' in contexto:
                # Formato dos puntos
                palabras_antes = re.findall(r'\b\w+\b', contexto)
                if palabras_antes:
                    palabra_clave = palabras_antes[-1]
                    return rf'{re.escape(palabra_clave)}\s*:?\s*([A-Z0-9]{{5,15}})'
            
            # Formato libre - buscar palabra clave más cercana
            palabras_clave = ['serie', 'serial', 'model', 'número', 'no']
            for palabra in palabras_clave:
                if palabra.lower() in contexto.lower():
                    return rf'{re.escape(palabra)}[^A-Z0-9]*([A-Z0-9]{{5,15}})'
            
            return rf'\b([A-Z0-9]{{5,15}})\b'
            
        except Exception as e:
            _logger.error(f"❌ Error extrayendo patrón de contexto: {e}")
            return None

    def _extraer_patron_contador_de_contexto(self, contexto, tipo_contador):
        """
        Extrae un patrón regex para contador del contexto
        """
        try:
            # Palabras clave por tipo de contador
            palabras_clave = {
                'contador_bn': ['negro', 'black', 'mono', 'b/n'],
                'contador_color': ['color', 'colour'],
                'contador_scan': ['scan', 'total', 'escaneo']
            }
            
            # Buscar formato específico
            if '[' in contexto and ']' in contexto:
                # Formato corchetes
                match = re.search(r'\[([^\]]+)\]', contexto)
                if match:
                    etiqueta = match.group(1)
                    return rf'\[{re.escape(etiqueta)}\][^0-9]*(\d{{4,9}})'
            
            elif 'T_' in contexto:
                # Formato Ricoh
                match = re.search(r'(T_\w+)', contexto)
                if match:
                    campo_ricoh = match.group(1)
                    return rf'{re.escape(campo_ricoh)}\s*:?\s*(\d{{4,9}})'
            
            else:
                # Buscar palabra clave más cercana
                for palabra in palabras_clave.get(tipo_contador, []):
                    if palabra.lower() in contexto.lower():
                        return rf'{re.escape(palabra)}[^0-9]*(\d{{4,9}})'
            
            return rf'(\d{{4,9}})'  # Patrón genérico
            
        except Exception as e:
            _logger.error(f"❌ Error extrayendo patrón de contador: {e}")
            return None

    def buscar_serie_dinamico(self, texto):
        """
        🔍 Busca número de serie usando patrones dinámicos,
        con fallback si no encuentra nada.
        """
        _logger.info("🔍 Iniciando búsqueda de serie con patrones dinámicos...")

        # 1) ¿Tenemos patrones activos de tipo 'serie'?
        cnt = self.env['patron.contador'].search_count([
            ('tipo', '=', 'serie'),
            ('activo', '=', True)
        ])
        _logger.info(f"📊 Patrones de serie disponibles: {cnt}")

        if cnt == 0:
            _logger.warning("⚠️ No hay patrones de serie configurados. Usando fallback...")
            return self._buscar_serie_fallback(texto)

        # 2) Intentamos detectar con patrones configurados
        resultado = self.env['patron.contador'].buscar_por_tipo('serie', texto)
        if resultado:
            patron = self._encontrar_patron_usado('serie', texto, resultado)
            if patron:
                detalle = f"serie: {patron.name}"
                self.patrones_usados = (
                    f"{self.patrones_usados}; {detalle}"
                    if self.patrones_usados else detalle
                )
                _logger.info(f"✅ Serie encontrada: {resultado} usando patrón '{patron.name}'")
            else:
                _logger.info(f"✅ Serie encontrada: {resultado}")
            return resultado

        # 3) Si no, lanzamos fallback
        _logger.warning("❌ No se encontró serie con patrones dinámicos, intentando fallback...")
        serie = self._buscar_serie_fallback(texto)
        if serie:
            _logger.info(f"✅ Serie encontrada (fallback): {serie}")
        else:
            _logger.warning("❌ Tampoco en fallback se encontró serie")
        return serie

    def _buscar_serie_fallback(self, texto):
        """
        🔧 Fallback COMPLETO con soporte para español, inglés y Ricoh
        """
        _logger.info("🔧 Usando patrones de serie de fallback...")

        patrones = [
            # ESPAÑOL (Konica/Minolta)
            r'\[Número de serie\].*?([A-Z0-9]{5,15})',          # [Número de serie], X...
            r'Número de serie[^\w]*([A-Z0-9]{5,15})',           # Número de serie: X...
            r'Serie[^\w]*([A-Z0-9]{5,15})',                     # Serie: X...
            
            # INGLÉS (Konica/Minolta)
            r'\[Serial Number\].*?([A-Z0-9]{5,15})',            # [Serial Number], X...
            r'Serial\s*No\.?:\s*([A-Z0-9]{5,15})',              # Serial No.: X...
            r'Serial\s*Number[^\w]*([A-Z0-9]{5,15})',           # Serial Number: X...
            
            # RICOH (español)
            r'Nº de serie:\s*([A-Z0-9]{5,15})',                 # Nº de serie: X...
            r'N° de serie:\s*([A-Z0-9]{5,15})',                 # N° de serie: X...
            
            # RICOH (inglés)
            r'Serial\s*No\s*:\s*([A-Z0-9]{5,15})',              # Serial No : X...
            
            # GENÉRICOS
            r'Page\s*Counter\s*:\s*([A-Z0-9]{5,15})',           # Page Counter: X...
            r'(?:serie|serial)\s*(?:no\.?)?\s*:?\s*([A-Z0-9]{5,15})',  # Genérico
            
            # FALLBACK FINAL - Cualquier código alfanumérico de 5-15 caracteres que tenga al menos una letra
            r'\b([A-Z0-9]{5,15})\b'
        ]
        
        for pat in patrones:
            _logger.info(f"🔍 Probando fallback: '{pat}'")
            for match in re.finditer(pat, texto, re.IGNORECASE):
                serie = match.group(1).upper()
                # CORRECCIÓN: Validar que tenga al menos una letra y longitud mínima
                if len(serie) >= 5 and re.search(r'[A-Z]', serie):
                    _logger.info(f"✅ Serie encontrada con fallback '{pat}': {serie}")
                    return serie
        
        _logger.warning("❌ No se encontró serie válida en fallback")
        return None

    def _encontrar_patron_usado(self, tipo, texto, valor_encontrado):
        """
        Encuentra qué patrón específico se usó para detectar un valor
        """
        try:
            patrones = self.env['patron.contador'].search([
                ('tipo', '=', tipo),
                ('activo', '=', True)
            ], order='orden')
            
            for patron in patrones:
                try:
                    matches = re.finditer(patron.patron_regex, texto, re.IGNORECASE)
                    for match in matches:
                        if match.groups():
                            valor = match.group(1).strip()
                            # Comparar valores
                            if tipo == 'serie':
                                if valor.upper() == str(valor_encontrado).upper():
                                    return patron
                            else:
                                valor_num = int(re.sub(r'[^0-9]', '', valor))
                                if valor_num == valor_encontrado:
                                    return patron
                except:
                    continue
            return None
        except Exception as e:
            _logger.error(f"❌ Error encontrando patrón usado: {e}")
            return None


    def buscar_patrones_contadores_dinamico(self, texto):
        """
        LÓGICA CORREGIDA: Detecta contadores en el orden correcto para Color vs Monocroma
        VERSIÓN DEBUG: Con logging detallado para encontrar origen de valores incorrectos
        """
        contadores = {}
        patrones_usados = []

        _logger.info("🔍 Iniciando búsqueda de contadores con patrones dinámicos...")
        _logger.info(f"📄 Texto a analizar (primeros 200 chars): {texto[:200]}...")
        
        # DEBUG: Verificar si 5763 está en el texto original
        if '5763' in texto:
            _logger.error(f"🔴 ALERTA: 5763 ENCONTRADO EN TEXTO ORIGINAL!")
            # Encontrar contexto
            pos_5763 = texto.find('5763')
            inicio = max(0, pos_5763 - 50)
            fin = min(len(texto), pos_5763 + 50)
            contexto = texto[inicio:fin]
            _logger.error(f"📄 Contexto de 5763: ...{contexto}...")
        else:
            _logger.info(f"✅ 5763 NO está en el texto original")

        # DEBUG: Mostrar TODOS los números del texto
        todos_numeros = re.findall(r'\d{4,9}', texto)
        _logger.info(f"🔢 TODOS los números (4-9 dígitos) en el texto: {todos_numeros}")

        # Verificar si existen patrones configurados
        total_patrones = self.env['patron.contador'].search_count([('activo', '=', True)])
        _logger.info(f"📊 Total de patrones activos disponibles: {total_patrones}")

        # Detectar si es máquina monocroma
        # CORRECCIÓN: Si el correo tiene Total_Color, definitivamente NO es monocroma
        tiene_total_color = 'Total_Color:' in texto
        if tiene_total_color:
            es_monocroma = False
            _logger.info("🌈 Correo con Total_Color detectado - forzando detección COLOR")
        else:
            es_monocroma = self._detectar_maquina_monocroma(texto, self.idioma_detectado or 'desconocido')
            if es_monocroma:
                _logger.info("🖤 === MÁQUINA MONOCROMA DETECTADA ===")
                _logger.info("ℹ️ Buscando 'total' como contador B/N, omitiendo color")

        # NUEVA LÓGICA: Detectar tipo de correo CORREGIDA
        es_correo_color = (
            '[Total Color Counter]' in texto or 
            '[Total Black Counter]' in texto or
            'Total_Color:' in texto or           # NUEVO: Detectar formato Total_Color:
            'Total_BW:' in texto                 # NUEVO: Detectar formato Total_BW:
        )
        
        es_correo_monocroma = (
            '[Total Counter]' in texto and 
            not es_correo_color and
            'Total_Color:' not in texto          # NUEVO: Asegurar que no tenga color
        )
        
        _logger.info(f"🔍 Análisis de tipo de correo:")
        _logger.info(f"   Correo color (tiene Black/Color específicos): {es_correo_color}")
        _logger.info(f"   Correo monocroma (solo Total genérico): {es_correo_monocroma}")

        # PATRONES FALLBACK REORDENADOS POR TIPO DE CORREO
        if es_correo_color:
            # PARA CORREOS COLOR: Priorizar contadores específicos
            fallback_por_tipo = {
                'contador_bn': [
                    # PRIORIDAD 1: Contador específico de Black
                    r'\[Total Black Counter\][^0-9]*(\d{4,9})',
                    # PRIORIDAD 2: Total_BW con espacios opcionales alrededor de ':'
                    r'Total_BW\s*:\s*(\d{4,9})',    # Total_BW : 141078 o Total_BW: 141078
                    # PRIORIDAD 3: Otros patrones BN
                    r'(?:black|b\/w|mono).*?(\d{4,9})',
                    r'T_TotalPrtPGS\s*:\s*(\d{4,9})',
                ],
                'contador_color': [
                    # PRIORIDAD 1: Contador específico de Color
                    r'\[Total Color Counter\][^0-9]*(\d{4,9})',
                    # PRIORIDAD 2: Total_Color con espacios opcionales alrededor de ':'
                    r'Total_Color\s*:\s*(\d{4,9})',  # Total_Color : 148948 o Total_Color:148948
                    # PRIORIDAD 3: Otros patrones Color  
                    r'(?:color|colour).*?(\d{4,9})',
                    r'T_ColorPrtPGS\s*:\s*(\d{4,9})'
                ],
                'contador_scan': [
                    r'\[Total Scan\/Fax Counter\][^0-9]*(\d{4,9})',
                    r'(?:scan|fax|copy).*?(\d{4,9})',
                    r'T_ScanPGS\s*:\s*(\d{4,9})'
                ]
            }
            _logger.info("🌈 Usando patrones para CORREO COLOR")
            
        else:
            # PARA CORREOS MONOCROMA: Total Counter va a BN
            fallback_por_tipo = {
                    'contador_bn': [
                        # PRIORIDAD 1: Para monocromas, Total Counter es BN
                        r'\[Total Counter\][^0-9]*(\d{4,9})',
                        # PRIORIDAD 2: Nuevo formato Total_BW (también puede ser monocroma)
                        r'Total_BW\s*:\s*(\d{4,9})',  # NUEVO: Total_BW:141078
                        # PRIORIDAD 3: Black específico si existe
                        r'\[Total Black Counter\][^0-9]*(\d{4,9})',
                        # PRIORIDAD 4: Otros patrones BN
                        r'(?:black|b\/w|total).*?(\d{4,9})',
                        r'T_TotalPrtPGS:\s*(\d{4,9})',
                    ],
                    'contador_color': [
                        # Para monocromas, NO debe detectar color (será 0)
                    ],
                    'contador_scan': [
                        r'\[Total Scan\/Fax Counter\][^0-9]*(\d{4,9})',
                        r'(?:scan|fax|copy).*?(\d{4,9})',
                        r'T_ScanPGS:\s*(\d{4,9})'
                    ]
                }
            _logger.info("🖤 Usando patrones para CORREO MONOCROMA")

        # Tipos de contador a buscar
        tipos = ['contador_bn', 'contador_color', 'contador_scan']

        for tipo in tipos:
            _logger.info(f"🔍 === DETECTANDO {tipo.upper()} ===")
            
            # Saltar color si es monocroma
            if es_monocroma and tipo == 'contador_color':
                _logger.info(f"⏭️ Saltando {tipo} - máquina monocroma detectada")
                continue
            
            # 1) Intento con patrones dinámicos
            _logger.info(f"🎯 Paso 1: Intentando patrones dinámicos para {tipo}")
            resultado = self.env['patron.contador'].buscar_por_tipo(tipo, texto)
            if resultado:
                _logger.info(f"✅ {tipo} encontrado con patrón dinámico: {resultado}")
                
                # DEBUG: Verificar si es 5763
                if resultado == 5763:
                    _logger.error(f"🔴 ALERTA: Patrón dinámico devolvió 5763 para {tipo}!")
                    _logger.error(f"🔍 Investigar qué patrón dinámico lo detectó")
                    
                    # Buscar qué patrón específico lo detectó
                    patron_usado = self._encontrar_patron_usado(tipo, texto, resultado)
                    if patron_usado:
                        _logger.error(f"🔴 PATRÓN PROBLEMÁTICO: {patron_usado.name} - {patron_usado.patron_regex}")
                    
                contadores[tipo] = resultado
                patron_usado = self._encontrar_patron_usado(tipo, texto, resultado)
                if patron_usado:
                    patrones_usados.append(f"{tipo}: {patron_usado.name}")
                    _logger.info(f"✅ {tipo} encontrado: {resultado} usando patrón '{patron_usado.name}'")
                else:
                    _logger.info(f"✅ {tipo} encontrado: {resultado}")
                continue

            # 2) Fallback específico según tipo de correo
            _logger.info(f"🎯 Paso 2: Intentando fallback para {tipo}")
            _logger.warning(f"❌ No se encontró {tipo} con patrones dinámicos, intentando fallback...")
            patrones_fallback = fallback_por_tipo.get(tipo, [])
            
            for i, pat in enumerate(patrones_fallback, 1):
                _logger.info(f"🔍 Probando fallback {i}/{len(patrones_fallback)} para {tipo}: '{pat}'")
                
                matches = list(re.finditer(pat, texto, re.IGNORECASE))
                _logger.info(f"   Coincidencias encontradas: {len(matches)}")
                
                for j, match in enumerate(matches, 1):
                    raw = match.group(1)
                    numero = int(re.sub(r'[^0-9]', '', raw))
                    _logger.info(f"   Match {j}: raw='{raw}' → numero={numero}")
                    
                    # DEBUG: Verificar si es 5763
                    if numero == 5763:
                        _logger.error(f"🔴 ALERTA: Fallback generó 5763!")
                        _logger.error(f"🔴 Patrón problemático: '{pat}'")
                        _logger.error(f"🔴 Match completo: '{match.group(0)}'")
                        _logger.error(f"🔴 Posición en texto: {match.start()}-{match.end()}")
                        
                        # Contexto del match
                        inicio_ctx = max(0, match.start() - 30)
                        fin_ctx = min(len(texto), match.end() + 30)
                        contexto_match = texto[inicio_ctx:fin_ctx]
                        _logger.error(f"🔴 Contexto: ...{contexto_match}...")
                    
                    if numero > 0:
                        contadores[tipo] = numero
                        patrones_usados.append(f"{tipo}: fallback '{pat}'")
                        _logger.info(f"✅ {tipo} encontrado por fallback: {numero} usando patrón '{pat}'")
                        break
                if tipo in contadores:
                    break
            
            if tipo not in contadores:
                _logger.info(f"❌ No se encontró {tipo} incluso en fallback")

        # CORRECCIÓN FINAL: Si es monocroma y solo encontramos scan/total, asignarlo también a BN
        if es_monocroma and 'contador_scan' in contadores and 'contador_bn' not in contadores:
            valor_scan = contadores['contador_scan']
            _logger.info(f"🔄 Máquina monocroma: copiando total ({valor_scan}) a contador BN")
            
            # DEBUG: Verificar si es 5763
            if valor_scan == 5763:
                _logger.error(f"🔴 ALERTA: Se va a copiar 5763 desde scan a BN!")
            
            contadores['contador_bn'] = valor_scan
            patrones_usados.append("contador_bn: copiado de total (máquina monocroma)")

        # DEBUG FINAL: Verificar todos los valores detectados
        _logger.info(f"🎯 === RESULTADO FINAL DETALLADO ===")
        for tipo, valor in contadores.items():
            _logger.info(f"📊 {tipo}: {valor}")
            if valor == 5763:
                _logger.error(f"🔴 PROBLEMA CONFIRMADO: {tipo} tiene valor 5763!")
            
            # Verificar si el valor existe en el texto original
            if str(valor) not in texto:
                _logger.error(f"🔴 PROBLEMA: {tipo}={valor} NO existe en el texto original!")
            else:
                _logger.info(f"✅ {tipo}={valor} SÍ existe en el texto original")

        # Guardamos el detalle de qué patrones se usaron
        if patrones_usados:
            self.patrones_usados = "; ".join(patrones_usados)
            _logger.info(f"📋 Patrones utilizados: {self.patrones_usados}")

        _logger.info(f"🎯 Resultado final de contadores: {contadores}")
        return contadores

        
    def buscar_equipo_por_serie(self, serie):
        """
        Busca el equipo en alquiler por serie
        CORRECCIÓN: Mejorado con múltiples intentos de búsqueda
        """
        if not serie:
            _logger.warning(f"⚠️ No se proporcionó serie para buscar equipo")
            return None
        
        _logger.info(f"🔍 Buscando equipo con serie: '{serie}'")
        
        try:
            # 1. Búsqueda exacta
            equipo = self.env['alquiler'].search([('serie', '=', serie)], limit=1)
            if equipo:
                _logger.info(f"✅ Equipo encontrado (exacto): ID={equipo.id}, Serie={serie}")
                return equipo
            
            # 2. Búsqueda case-insensitive
            equipo = self.env['alquiler'].search([('serie', 'ilike', serie)], limit=1)
            if equipo:
                _logger.info(f"✅ Equipo encontrado (ilike): ID={equipo.id}, Serie={equipo.serie}")
                return equipo
            
            # 3. Búsqueda con wildcards (contiene)
            equipo = self.env['alquiler'].search([('serie', 'like', f'%{serie}%')], limit=1)
            if equipo:
                _logger.info(f"✅ Equipo encontrado (like): ID={equipo.id}, Serie={equipo.serie}")
                return equipo
            
            # 4. Búsqueda inversa (el campo contiene nuestra serie)
            equipos_posibles = self.env['alquiler'].search([])
            for equipo in equipos_posibles:
                if equipo.serie and serie.upper() in equipo.serie.upper():
                    _logger.info(f"✅ Equipo encontrado (inverso): ID={equipo.id}, Serie={equipo.serie}")
                    return equipo
            
            _logger.warning(f"❌ No se encontró equipo con serie: '{serie}' tras múltiples intentos")
            return None
                
        except Exception as e:
            _logger.error(f"❌ Error buscando equipo: {e}")
            return None



    def actualizar_contadores_equipo(self, equipo, contadores):
        """
        Actualiza los contadores del equipo con validación de incrementos
        y registra la fecha de última actualización.
        """
        try:
            _logger.info(f"💾 === INICIANDO ACTUALIZACIÓN DE EQUIPO CON VALIDACIÓN ===")
            _logger.info(f"🎯 Equipo ID={equipo.id}, Serie={equipo.serie}")
            _logger.info(f"📊 Contadores a actualizar: {contadores}")

            # Guardar valores anteriores para comparación
            valores_anteriores = {
                'contador_bn': getattr(equipo, 'contador_bn', 0) or 0,
                'contador_color': getattr(equipo, 'contador_color', 0) or 0,
                'contador_scan': getattr(equipo, 'contador_scan', 0) or 0
            }
            _logger.info(f"📋 Valores actuales del equipo: {valores_anteriores}")

            # Preparar valores para actualizar
            valores_actualizacion = {}
            alertas = []

            # Procesar contador B/N
            if 'contador_bn' in contadores:
                nuevo_valor = contadores['contador_bn']
                anterior = valores_anteriores['contador_bn']
                if nuevo_valor > anterior:
                    valores_actualizacion['contador_bn'] = nuevo_valor
                    self.contador_bn_anterior = anterior
                    _logger.info(f"✅ BN: {anterior} → {nuevo_valor} (+{nuevo_valor - anterior})")
                elif nuevo_valor < anterior and nuevo_valor > 0:
                    valores_actualizacion['contador_bn'] = nuevo_valor
                    self.contador_bn_anterior = anterior
                    alertas.append("BN decrementó - posible reset de equipo")
                    _logger.warning(f"⚠️ BN decrementó: {anterior} → {nuevo_valor}")

            # Procesar contador Color
            if 'contador_color' in contadores:
                nuevo_valor = contadores['contador_color']
                anterior = valores_anteriores['contador_color']
                if nuevo_valor > anterior:
                    valores_actualizacion['contador_color'] = nuevo_valor
                    self.contador_color_anterior = anterior
                    _logger.info(f"✅ Color: {anterior} → {nuevo_valor} (+{nuevo_valor - anterior})")
                elif nuevo_valor < anterior and nuevo_valor > 0:
                    valores_actualizacion['contador_color'] = nuevo_valor
                    self.contador_color_anterior = anterior
                    alertas.append("Color decrementó - posible reset de equipo")
                    _logger.warning(f"⚠️ Color decrementó: {anterior} → {nuevo_valor}")

            # Procesar contador Scan
            if 'contador_scan' in contadores:
                nuevo_valor = contadores['contador_scan']
                anterior = valores_anteriores['contador_scan']
                if nuevo_valor > anterior:
                    valores_actualizacion['contador_scan'] = nuevo_valor
                    self.contador_scan_anterior = anterior
                    _logger.info(f"✅ Scan: {anterior} → {nuevo_valor} (+{nuevo_valor - anterior})")
                elif nuevo_valor < anterior and nuevo_valor > 0:
                    valores_actualizacion['contador_scan'] = nuevo_valor
                    self.contador_scan_anterior = anterior
                    alertas.append("Scan decrementó - posible reset de equipo")
                    _logger.warning(f"⚠️ Scan decrementó: {anterior} → {nuevo_valor}")

            # Siempre registrar la fecha de última actualización
            valores_actualizacion['fecha_ultima_actualizacion'] = fields.Datetime.now()

            # Realizar actualización solo si hay cambios
            if valores_actualizacion:
                _logger.info(f"💾 Ejecutando write() en equipo con: {valores_actualizacion}")
                equipo.sudo().write(valores_actualizacion)
                _logger.info(f"✅ Write() ejecutado exitosamente")
            else:
                _logger.info(f"ℹ️ No hay cambios que actualizar en el equipo")

            # Registrar alertas si las hay
            if alertas:
                mensaje_alertas = "; ".join(alertas)
                self.mensaje_error = (self.mensaje_error or "") + f" | Alertas: {mensaje_alertas}"
                _logger.info(f"🔔 Alertas registradas: {mensaje_alertas}")

            _logger.info(f"🎉 === ACTUALIZACIÓN DE EQUIPO COMPLETADA ===")

        except Exception as e:
            _logger.error(f"❌ === ERROR ACTUALIZANDO EQUIPO === {e}", exc_info=True)
            raise

    @api.model
    def buscar_registro_del_dia(self, serie, fecha=None):
        """
        Busca si ya existe un registro para esta serie en el día especificado
        
        Args:
            serie (str): Número de serie del equipo
            fecha (date, optional): Fecha a verificar. Si no se proporciona, usa hoy
        
        Returns:
            recordset: Registro encontrado o False si no existe
        """
        try:
            if not serie:
                _logger.warning("⚠️ No se proporcionó serie para buscar registro del día")
                return False
            
            # Si no se proporciona fecha, usar hoy
            if not fecha:
                fecha = fields.Date.today()
            
            # Convertir fecha a datetime para el rango del día
            inicio_dia = datetime.combine(fecha, datetime.min.time())
            fin_dia = datetime.combine(fecha, datetime.max.time())
            
            _logger.info(f"🔍 Buscando registro del día para:")
            _logger.info(f"   Serie: {serie}")
            _logger.info(f"   Fecha: {fecha}")
            _logger.info(f"   Rango: {inicio_dia} - {fin_dia}")
            
            # Buscar registro en el rango del día
            registro = self.search([
                ('serie_detectada', '=', serie),
                ('fecha_procesamiento', '>=', inicio_dia),
                ('fecha_procesamiento', '<=', fin_dia)
            ], limit=1)
            
            if registro:
                _logger.info(f"✅ Registro encontrado:")
                _logger.info(f"   ID: {registro.id}")
                _logger.info(f"   Estado: {registro.estado}")
                _logger.info(f"   Fecha procesamiento: {registro.fecha_procesamiento}")
                _logger.info(f"   Origen: {getattr(registro, 'origen', 'No definido')}")
                return registro
            else:
                _logger.info(f"❌ No se encontró registro del día para serie {serie}")
                return False
                
        except Exception as e:
            _logger.error(f"❌ Error buscando registro del día: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False