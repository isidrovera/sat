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
    contador_bn_detectado = fields.Integer('Contador B/N detectado')
    contador_color_detectado = fields.Integer('Contador Color detectado')
    contador_scan_detectado = fields.Integer('Contador Scan detectado')
    
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
        CORREGIDO: Asignación correcta de contadores a los campos del registro
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

            contadores_encontrados = self.buscar_patrones_contadores_dinamico(texto_limpio)

            # ===== NUEVA LÓGICA: IDENTIFICACIÓN DE TIPO DE EQUIPO =====
            equipo_detectado = None
            tipo_maquina_detectado = None
            cliente_detectado = None

            if serie_encontrada:
                _logger.info(f"🎯 === IDENTIFICANDO TIPO DE EQUIPO POR SERIE ===")
                
                # NUEVO: Identificar tipo de equipo por serie
                equipo_detectado, tipo_maquina_detectado, cliente_detectado = self.identificar_tipo_equipo_por_serie(serie_encontrada)
                
                if equipo_detectado and tipo_maquina_detectado:
                    _logger.info(f"🎯 Equipo identificado: {equipo_detectado.id} - Tipo: {tipo_maquina_detectado}")
                    
                    # NUEVO: Asignar contadores según tipo de equipo
                    contadores_encontrados = self.asignar_contadores_por_tipo_equipo(
                        contadores_encontrados, tipo_maquina_detectado
                    )
                    
                    # CORRECCIÓN: Actualizar campos del registro INMEDIATAMENTE
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
                    
                    # NUEVO: Guardar información adicional del equipo
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
                    
                    # CORRECCIÓN: Pasar contadores_encontrados que ya están procesados
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


       
    def verificar_asignacion_contadores(self):
        """
        NUEVO: Verifica que los contadores se hayan asignado correctamente
        """
        try:
            _logger.info(f"🔍 === VERIFICANDO ASIGNACIÓN DE CONTADORES ===")
            _logger.info(f"📊 Registro ID: {self.id}")
            _logger.info(f"🎯 Serie: {self.serie_detectada}")
            
            _logger.info(f"📊 Contadores detectados:")
            _logger.info(f"   contador_bn_detectado: {self.contador_bn_detectado}")
            _logger.info(f"   contador_color_detectado: {self.contador_color_detectado}")
            _logger.info(f"   contador_scan_detectado: {self.contador_scan_detectado}")
            
            # Verificar si hay valores
            hay_contadores = (self.contador_bn_detectado or 0) + (self.contador_color_detectado or 0) + (self.contador_scan_detectado or 0)
            
            if hay_contadores == 0:
                _logger.error(f"❌ NO HAY CONTADORES ASIGNADOS")
                return False
            else:
                _logger.info(f"✅ Contadores asignados correctamente")
                return True
                
        except Exception as e:
            _logger.error(f"❌ Error verificando asignación: {e}")
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

    # REEMPLAZAR la sección fallback_por_tipo en buscar_patrones_contadores_dinamico

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
        es_monocroma = self._detectar_maquina_monocroma(texto, self.idioma_detectado or 'desconocido')
        if es_monocroma:
            _logger.info("🖤 === MÁQUINA MONOCROMA DETECTADA ===")
            _logger.info("ℹ️ Buscando 'total' como contador B/N, omitiendo color")

        # NUEVA LÓGICA: Detectar tipo de correo PRIMERO
        es_correo_color = '[Total Color Counter]' in texto or '[Total Black Counter]' in texto
        es_correo_monocroma = '[Total Counter]' in texto and not es_correo_color
        
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
                    # PRIORIDAD 2: Otros patrones BN
                    r'(?:black|b\/w|mono).*?(\d{4,9})',
                    r'T_TotalPrtPGS:\s*(\d{4,9})',
                ],
                'contador_color': [
                    # PRIORIDAD 1: Contador específico de Color
                    r'\[Total Color Counter\][^0-9]*(\d{4,9})',
                    # PRIORIDAD 2: Otros patrones Color  
                    r'(?:color|colour).*?(\d{4,9})',
                    r'T_ColorPrtPGS:\s*(\d{4,9})'
                ],
                'contador_scan': [
                    r'\[Total Scan\/Fax Counter\][^0-9]*(\d{4,9})',
                    r'(?:scan|fax|copy).*?(\d{4,9})',
                    r'T_ScanPGS:\s*(\d{4,9})'
                ]
            }
            _logger.info("🌈 Usando patrones para CORREO COLOR")
            
        else:
            # PARA CORREOS MONOCROMA: Total Counter va a BN
            fallback_por_tipo = {
                'contador_bn': [
                    # PRIORIDAD 1: Para monocromas, Total Counter es BN
                    r'\[Total Counter\][^0-9]*(\d{4,9})',
                    # PRIORIDAD 2: Black específico si existe
                    r'\[Total Black Counter\][^0-9]*(\d{4,9})',
                    # PRIORIDAD 3: Otros patrones BN
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


    def debuggear_patrones_dinamicos(self, serie_objetivo):
        """
        DEBUG: Investiga específicamente qué patrones dinámicos están detectando valores incorrectos
        """
        try:
            _logger.info(f"🔬 === DEBUG PATRONES DINÁMICOS PARA SERIE {serie_objetivo} ===")
            
            # Buscar registro con esa serie
            registro = self.env['contador.automatico'].search([
                ('serie_detectada', '=', serie_objetivo)
            ], limit=1)
            
            if not registro:
                _logger.error(f"❌ No se encontró registro con serie {serie_objetivo}")
                return
            
            texto = registro.contenido_procesado or registro.contenido_original or ""
            if not texto:
                _logger.error(f"❌ No hay contenido para analizar")
                return
            
            _logger.info(f"📄 Contenido disponible: {len(texto)} caracteres")
            
            # Verificar todos los patrones activos
            patrones_activos = self.env['patron.contador'].search([('activo', '=', True)])
            _logger.info(f"📊 Total patrones activos: {len(patrones_activos)}")
            
            for tipo in ['contador_bn', 'contador_color', 'contador_scan']:
                _logger.info(f"🔍 === ANALIZANDO PATRONES PARA {tipo.upper()} ===")
                
                patrones_tipo = patrones_activos.filtered(lambda p: p.tipo == tipo)
                _logger.info(f"📋 Patrones de {tipo}: {len(patrones_tipo)}")
                
                for patron in patrones_tipo:
                    _logger.info(f"🎯 Probando patrón: '{patron.name}' - '{patron.patron_regex}'")
                    
                    try:
                        matches = re.finditer(patron.patron_regex, texto, re.IGNORECASE)
                        match_count = 0
                        
                        for match in matches:
                            match_count += 1
                            if match.groups():
                                valor_raw = match.group(1).strip()
                                valor_num = int(re.sub(r'[^0-9]', '', valor_raw)) if valor_raw else 0
                                
                                _logger.info(f"   Match {match_count}: '{valor_raw}' → {valor_num}")
                                
                                # ALERTA SI ES 5763
                                if valor_num == 5763:
                                    _logger.error(f"🔴 PATRÓN PROBLEMÁTICO ENCONTRADO!")
                                    _logger.error(f"🔴 Patrón: {patron.name} - {patron.patron_regex}")
                                    _logger.error(f"🔴 Match completo: '{match.group(0)}'")
                                    _logger.error(f"🔴 Valor extraído: {valor_num}")
                                    
                                    # Contexto
                                    inicio = max(0, match.start() - 50)
                                    fin = min(len(texto), match.end() + 50)
                                    contexto = texto[inicio:fin]
                                    _logger.error(f"🔴 Contexto: ...{contexto}...")
                                    
                                    # ¿Este patrón está activo?
                                    _logger.error(f"🔴 Patrón activo: {patron.activo}")
                                    _logger.error(f"🔴 Orden del patrón: {patron.orden}")
                                    _logger.error(f"🔴 Auto-generado: {getattr(patron, 'auto_generado', 'N/A')}")
                        
                        if match_count == 0:
                            _logger.info(f"   Sin coincidencias para este patrón")
                            
                    except Exception as e:
                        _logger.error(f"❌ Error procesando patrón {patron.name}: {e}")
            
            # Verificar método buscar_por_tipo específicamente
            _logger.info(f"🔍 === PROBANDO MÉTODO buscar_por_tipo DIRECTAMENTE ===")
            
            for tipo in ['contador_bn', 'contador_color', 'contador_scan']:
                _logger.info(f"🎯 Ejecutando buscar_por_tipo('{tipo}', texto)")
                resultado = self.env['patron.contador'].buscar_por_tipo(tipo, texto)
                _logger.info(f"   Resultado: {resultado}")
                
                if resultado == 5763:
                    _logger.error(f"🔴 buscar_por_tipo DEVOLVIÓ 5763 PARA {tipo}!")
                    
                    # Investigar qué patrón fue el primero en hacer match
                    patrones_tipo = self.env['patron.contador'].search([
                        ('tipo', '=', tipo),
                        ('activo', '=', True)
                    ], order='orden')
                    
                    for patron in patrones_tipo:
                        try:
                            matches = list(re.finditer(patron.patron_regex, texto, re.IGNORECASE))
                            if matches:
                                for match in matches:
                                    if match.groups():
                                        valor = match.group(1).strip()
                                        numero = int(re.sub(r'[^0-9]', '', valor)) if valor else 0
                                        if numero == resultado:
                                            _logger.error(f"🔴 PATRÓN CULPABLE: {patron.name}")
                                            _logger.error(f"🔴 Regex: {patron.patron_regex}")
                                            _logger.error(f"🔴 Orden: {patron.orden}")
                                            break
                                break
                        except:
                            continue
            
            _logger.info(f"🔬 === FIN DEBUG PATRONES DINÁMICOS ===")
            
        except Exception as e:
            _logger.error(f"❌ Error en debug de patrones dinámicos: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")

    def investigar_origen_5763_completo(self):
        """
        INVESTIGACIÓN COMPLETA: Busca el origen del valor 5763 en todo el sistema
        """
        try:
            _logger.info(f"🕵️ === INVESTIGACIÓN COMPLETA DEL VALOR 5763 ===")
            
            # 1. Buscar en registros contador.automatico
            registros_con_5763 = self.env['contador.automatico'].search([
                '|', '|',
                ('contador_bn_detectado', '=', 5763),
                ('contador_color_detectado', '=', 5763),
                ('contador_scan_detectado', '=', 5763)
            ])
            
            _logger.info(f"📊 Registros con 5763: {len(registros_con_5763)}")
            
            for registro in registros_con_5763:
                _logger.info(f"📋 Registro ID={registro.id}:")
                _logger.info(f"   Serie: {registro.serie_detectada}")
                _logger.info(f"   BN: {registro.contador_bn_detectado}")
                _logger.info(f"   Color: {registro.contador_color_detectado}")
                _logger.info(f"   Scan: {registro.contador_scan_detectado}")
                _logger.info(f"   Fecha: {registro.create_date}")
                _logger.info(f"   Estado: {registro.estado}")
                
                # Verificar si 5763 está en el contenido original
                contenido = registro.contenido_procesado or registro.contenido_original or ""
                if '5763' in contenido:
                    _logger.error(f"🔴 5763 SÍ está en el contenido del registro {registro.id}")
                    # Encontrar contexto
                    pos = contenido.find('5763')
                    inicio = max(0, pos - 50)
                    fin = min(len(contenido), pos + 50)
                    contexto = contenido[inicio:fin]
                    _logger.error(f"📄 Contexto: ...{contexto}...")
                else:
                    _logger.error(f"🔴 5763 NO está en el contenido del registro {registro.id} - ¡PROBLEMA!")
            
            # 2. Buscar en equipos (modelo alquiler)
            try:
                equipos_con_5763 = self.env['alquiler'].search([
                    '|', '|',
                    ('contador_bn', '=', 5763),
                    ('contador_color', '=', 5763),
                    ('contador_scan', '=', 5763)
                ])
                
                _logger.info(f"🏭 Equipos con 5763: {len(equipos_con_5763)}")
                
                for equipo in equipos_con_5763:
                    _logger.info(f"🏭 Equipo ID={equipo.id}:")
                    _logger.info(f"   Serie: {equipo.serie}")
                    _logger.info(f"   BN: {getattr(equipo, 'contador_bn', 'N/A')}")
                    _logger.info(f"   Color: {getattr(equipo, 'contador_color', 'N/A')}")
                    _logger.info(f"   Scan: {getattr(equipo, 'contador_scan', 'N/A')}")
                    
            except Exception as e:
                _logger.error(f"❌ Error buscando en equipos: {e}")
            
            # 3. Buscar en patrones
            try:
                patrones = self.env['patron.contador'].search([])
                patrones_con_5763 = []
                
                for patron in patrones:
                    if '5763' in (patron.patron_regex or '') or '5763' in (patron.ejemplo or ''):
                        patrones_con_5763.append(patron)
                
                _logger.info(f"🎯 Patrones que contienen 5763: {len(patrones_con_5763)}")
                
                for patron in patrones_con_5763:
                    _logger.info(f"🎯 Patrón sospechoso: {patron.name}")
                    _logger.info(f"   Regex: {patron.patron_regex}")
                    _logger.info(f"   Ejemplo: {patron.ejemplo}")
                    
            except Exception as e:
                _logger.error(f"❌ Error buscando en patrones: {e}")
            
            _logger.info(f"🕵️ === FIN INVESTIGACIÓN 5763 ===")
            
        except Exception as e:
            _logger.error(f"❌ Error en investigación completa: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
    # TAMBIÉN AGREGAR este método para verificar tipo de correo
    def _detectar_tipo_correo_por_contenido(self, texto):
        """
        NUEVO: Detecta si es correo de máquina color o monocroma por el contenido
        """
        try:
            _logger.info("🔍 === DETECTANDO TIPO DE CORREO POR CONTENIDO ===")
            
            # Buscar indicadores de correo color
            indicadores_color = [
                '[Total Color Counter]',
                '[Total Black Counter]',
                'T_ColorPrtPGS'
            ]
            
            # Buscar indicadores de correo monocroma
            indicadores_monocroma = [
                '[Total Counter]'  # Solo si no hay color/black específicos
            ]
            
            tiene_indicadores_color = any(ind in texto for ind in indicadores_color)
            tiene_total_generico = '[Total Counter]' in texto
            
            if tiene_indicadores_color:
                tipo = 'color'
                razon = "Contiene contadores específicos Black/Color"
            elif tiene_total_generico and not tiene_indicadores_color:
                tipo = 'monocroma'
                razon = "Solo contiene Total Counter genérico"
            else:
                tipo = 'desconocido'
                razon = "No se detectaron patrones claros"
            
            _logger.info(f"🎯 Tipo de correo detectado: {tipo}")
            _logger.info(f"💡 Razón: {razon}")
            
            return tipo, razon
            
        except Exception as e:
            _logger.error(f"❌ Error detectando tipo de correo: {e}")
            return 'desconocido', f"Error: {str(e)}"

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
        CORREGIDO: Valida que los contadores incrementen naturalmente
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
                anterior = valores_anteriores.get('contador_bn', 0)
                
                if nuevo_valor > anterior:
                    valores_actualizacion['contador_bn'] = nuevo_valor
                    self.contador_bn_anterior = anterior
                    _logger.info(f"✅ BN: {anterior} → {nuevo_valor} (+{nuevo_valor - anterior})")
                elif nuevo_valor == anterior:
                    _logger.info(f"ℹ️ BN sin cambios: {nuevo_valor}")
                else:
                    # Valor menor - posible reset
                    _logger.warning(f"⚠️ BN decrementó: {anterior} → {nuevo_valor}")
                    if nuevo_valor > 0:  # Solo actualizar si no es 0
                        valores_actualizacion['contador_bn'] = nuevo_valor
                        self.contador_bn_anterior = anterior
                        alertas.append("BN decrementó - posible reset de equipo")
                        _logger.warning(f"⚠️ Actualizando BN pese a decremento")
                    else:
                        alertas.append("BN en 0 - no actualizado")
                        _logger.warning(f"❌ No actualizando BN (valor 0)")
            
            # Procesar contador Color
            if 'contador_color' in contadores:
                nuevo_valor = contadores['contador_color']
                anterior = valores_anteriores.get('contador_color', 0)
                
                if nuevo_valor > anterior:
                    valores_actualizacion['contador_color'] = nuevo_valor
                    self.contador_color_anterior = anterior
                    _logger.info(f"✅ Color: {anterior} → {nuevo_valor} (+{nuevo_valor - anterior})")
                elif nuevo_valor == anterior:
                    _logger.info(f"ℹ️ Color sin cambios: {nuevo_valor}")
                else:
                    # Valor menor - posible reset
                    _logger.warning(f"⚠️ Color decrementó: {anterior} → {nuevo_valor}")
                    if nuevo_valor > 0:  # Solo actualizar si no es 0
                        valores_actualizacion['contador_color'] = nuevo_valor
                        self.contador_color_anterior = anterior
                        alertas.append("Color decrementó - posible reset de equipo")
                        _logger.warning(f"⚠️ Actualizando Color pese a decremento")
                    else:
                        alertas.append("Color en 0 - no actualizado")
                        _logger.warning(f"❌ No actualizando Color (valor 0)")
            
            # Procesar contador Scan
            if 'contador_scan' in contadores:
                nuevo_valor = contadores['contador_scan']
                anterior = valores_anteriores.get('contador_scan', 0)
                
                if nuevo_valor > anterior:
                    valores_actualizacion['contador_scan'] = nuevo_valor
                    self.contador_scan_anterior = anterior
                    _logger.info(f"✅ Scan: {anterior} → {nuevo_valor} (+{nuevo_valor - anterior})")
                elif nuevo_valor == anterior:
                    _logger.info(f"ℹ️ Scan sin cambios: {nuevo_valor}")
                else:
                    # Valor menor - posible reset
                    _logger.warning(f"⚠️ Scan decrementó: {anterior} → {nuevo_valor}")
                    if nuevo_valor > 0:  # Solo actualizar si no es 0
                        valores_actualizacion['contador_scan'] = nuevo_valor
                        self.contador_scan_anterior = anterior
                        alertas.append("Scan decrementó - posible reset de equipo")
                        _logger.warning(f"⚠️ Actualizando Scan pese a decremento")
                    else:
                        alertas.append("Scan en 0 - no actualizado")
                        _logger.warning(f"❌ No actualizando Scan (valor 0)")
            
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
                if not self.mensaje_error:
                    self.mensaje_error = f"Alertas: {mensaje_alertas}"
                else:
                    self.mensaje_error += f" | Alertas: {mensaje_alertas}"
                _logger.info(f"🔔 Alertas registradas: {mensaje_alertas}")
            
            _logger.info(f"🎉 === ACTUALIZACIÓN DE EQUIPO COMPLETADA ===")
            
        except Exception as e:
            _logger.error(f"❌ === ERROR ACTUALIZANDO EQUIPO ===")
            _logger.error(f"Error: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            raise
    def _guardar_estadisticas_cron_seguro(self, resumen):
        """
        SOLUCIÓN: Guardar estadísticas de forma segura
        """
        try:
            hoy = fields.Date.today()
            
            # Verificar si el modelo existe
            try:
                estadisticas = self.env['contador.automatico.estadisticas'].search([
                    ('fecha', '=', hoy)
                ], limit=1)
            except:
                _logger.warning("⚠️ Modelo 'contador.automatico.estadisticas' no existe, saltando estadísticas")
                return
            
            datos_estadisticas = {
                'fecha': hoy,
                'correos_encontrados_cron': resumen.get('correos_encontrados', 0),
                'correos_procesados_cron': resumen.get('correos_procesados', 0),
                'correos_fallidos_cron': resumen.get('correos_fallidos', 0),
                'ejecuciones_cron': 1
            }
            
            if not estadisticas:
                estadisticas = self.env['contador.automatico.estadisticas'].create(datos_estadisticas)
                _logger.info(f"📊 Nuevas estadísticas CRON creadas para {hoy}")
            else:
                # Acumular valores existentes
                estadisticas.write({
                    'correos_encontrados_cron': estadisticas.correos_encontrados_cron + datos_estadisticas['correos_encontrados_cron'],
                    'correos_procesados_cron': estadisticas.correos_procesados_cron + datos_estadisticas['correos_procesados_cron'],
                    'correos_fallidos_cron': estadisticas.correos_fallidos_cron + datos_estadisticas['correos_fallidos_cron'],
                    'ejecuciones_cron': estadisticas.ejecuciones_cron + 1
                })
                _logger.info(f"📊 Estadísticas CRON actualizadas para {hoy}")
            
        except Exception as e:
            _logger.error(f"❌ Error guardando estadísticas CRON: {e}")

    @api.model
    def limpiar_registros_problematicos_total(self):
        """
        SOLUCIÓN: Limpieza completa de registros que pueden estar causando problemas
        """
        try:
            _logger.info("🧹 === INICIO LIMPIEZA TOTAL DE REGISTROS PROBLEMÁTICOS ===")
            
            # 1. Registros sin fecha de procesamiento
            sin_fecha = self.env['contador.automatico'].search([
                ('fecha_procesamiento', '=', False)
            ])
            _logger.info(f"🔍 Registros sin fecha_procesamiento: {len(sin_fecha)}")
            
            # 2. Registros en estado pendiente o error
            estados_problematicos = self.env['contador.automatico'].search([
                ('estado', 'in', ['pendiente', 'error'])
            ])
            _logger.info(f"🔍 Registros en estado problemático: {len(estados_problematicos)}")
            
            # 3. Registros duplicados (mismo asunto y remitente)
            todos_registros = self.env['contador.automatico'].search([])
            claves_vistas = {}
            duplicados = []
            
            for registro in todos_registros:
                clave = f"{registro.name}|{registro.remitente or ''}"
                if clave in claves_vistas:
                    # Es duplicado, marcar el más antiguo para eliminar
                    registro_anterior = claves_vistas[clave]
                    if registro.create_date < registro_anterior.create_date:
                        duplicados.append(registro_anterior)
                        claves_vistas[clave] = registro
                    else:
                        duplicados.append(registro)
                else:
                    claves_vistas[clave] = registro
            
            _logger.info(f"🔍 Registros duplicados encontrados: {len(duplicados)}")
            
            # 4. Combinar todos los registros problemáticos
            registros_a_eliminar = sin_fecha | estados_problematicos
            for dup in duplicados:
                registros_a_eliminar |= dup
            
            # Remover duplicados de la lista
            registros_a_eliminar = list(set(registros_a_eliminar.ids))
            
            _logger.info(f"📊 Total de registros problemáticos a eliminar: {len(registros_a_eliminar)}")
            
            if registros_a_eliminar:
                # Mostrar detalles antes de eliminar
                for reg_id in registros_a_eliminar[:10]:  # Mostrar solo primeros 10
                    registro = self.env['contador.automatico'].browse(reg_id)
                    _logger.info(f"🗑️ A eliminar: ID={registro.id}, Estado={registro.estado}, Asunto='{registro.name}', Fecha={registro.fecha_procesamiento}")
                
                # Eliminar en lotes para evitar problemas de memoria
                batch_size = 50
                eliminados = 0
                
                for i in range(0, len(registros_a_eliminar), batch_size):
                    batch = registros_a_eliminar[i:i+batch_size]
                    registros_batch = self.env['contador.automatico'].browse(batch)
                    registros_batch.unlink()
                    eliminados += len(batch)
                    _logger.info(f"🗑️ Eliminados {eliminados}/{len(registros_a_eliminar)} registros...")
                
                _logger.info(f"✅ Limpieza completada: {eliminados} registros problemáticos eliminados")
            else:
                _logger.info("ℹ️ No se encontraron registros problemáticos para eliminar")
            
            # 5. Limpiar estadísticas antiguas también
            try:
                fecha_limite_stats = fields.Date.today() - timedelta(days=30)
                stats_antiguas = self.env['contador.automatico.estadisticas'].search([
                    ('fecha', '<', fecha_limite_stats)
                ])
                
                if stats_antiguas:
                    stats_antiguas.unlink()
                    _logger.info(f"🗑️ Eliminadas {len(stats_antiguas)} estadísticas antiguas")
            except:
                _logger.info("ℹ️ Modelo de estadísticas no existe, saltando limpieza")
            
            _logger.info("🧹 === FIN LIMPIEZA TOTAL ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Limpieza completada: {len(registros_a_eliminar)} registros problemáticos eliminados',
                    'type': 'success'
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error en limpieza total: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error en limpieza: {str(e)}',
                    'type': 'danger'
                }
            }
     @api.model
    @api.model
    def cron_procesar_correos_perdidos(self):
        _logger.info("⏰ Iniciando cron_procesar_correos_perdidos")
        ahora = fields.Datetime.now()
        fecha_limite = ahora - timedelta(hours=24)

        # Buscar mails de las últimas 24h
        correos = self.env['mail.message'].search([
            ('message_type', '=', 'email'),
            ('date', '>=', fecha_limite),
        ], order='date desc')
        _logger.info("📧 Correos totales últimos 24h: %d", len(correos))

        # Excluir ya procesados
        procesados = self.mapped('original_mail_id.id')
        correos = correos.filtered(lambda m: m.id not in procesados)
        _logger.info("🔍 Correos nuevos: %d", len(correos))

        # Filtrar por asunto
        claves = ['counter', 'contador']
        correos = correos.filtered(lambda m: any(k in (m.subject or '').lower() for k in claves))
        _logger.info("✅ Correos con clave en asunto: %d", len(correos))

        exitosos = errors = no_data = 0
        for mail in correos:
            try:
                reg = self.create({
                    'name': mail.subject or 'Sin asunto',
                    'remitente': mail.email_from,
                    'contenido_original': mail.body or mail.subject,
                    'estado': 'pendiente',
                    'original_mail_id': mail.id,
                })
                if reg.procesar_correo_inteligente():
                    if reg.serie_detectada and (reg.contador_bn_detectado or reg.contador_color_detectado or reg.contador_scan_detectado):
                        exitosos += 1
                    else:
                        no_data += 1
                else:
                    no_data += 1
            except Exception as e:
                errors += 1
                _logger.error("❌ Error procesando mail.id=%d: %s", mail.id, e, exc_info=True)

        _logger.info("🎯 Resumen cron: éxitos=%d, sin datos=%d, errores=%d", exitosos, no_data, errors)
        return True
    def limpiar_duplicados_mismo_dia(self):
        """
        NUEVO: Limpia duplicados que fueron creados el mismo día
        """
        try:
            _logger.info(f"🧹 === LIMPIANDO DUPLICADOS DEL MISMO DÍA ===")
            
            # Buscar todas las series
            series_unicas = self.search([
                ('serie_detectada', '!=', False),
                ('estado', 'in', ['procesado', 'manual'])
            ]).mapped('serie_detectada')
            
            series_unicas = list(set(series_unicas))  # Eliminar duplicados
            _logger.info(f"🔍 Series únicas encontradas: {len(series_unicas)}")
            
            total_eliminados = 0
            
            for serie in series_unicas:
                _logger.info(f"🔍 Analizando serie: {serie}")
                
                # Buscar todos los registros de esta serie de los últimos 7 días
                fecha_limite = fields.Date.today() - timedelta(days=7)
                registros_serie = self.search([
                    ('serie_detectada', '=', serie),
                    ('estado', 'in', ['procesado', 'manual']),
                    ('create_date', '>=', fecha_limite)
                ], order='create_date desc')
                
                if len(registros_serie) <= 1:
                    continue
                
                # Agrupar por día
                registros_por_dia = {}
                for registro in registros_serie:
                    dia = registro.create_date.date()
                    if dia not in registros_por_dia:
                        registros_por_dia[dia] = []
                    registros_por_dia[dia].append(registro)
                
                # Revisar cada día que tenga múltiples registros
                for dia, registros_dia in registros_por_dia.items():
                    if len(registros_dia) <= 1:
                        continue
                    
                    _logger.info(f"📅 Día {dia}: {len(registros_dia)} registros")
                    
                    # Agrupar por contadores idénticos
                    grupos_contadores = {}
                    for registro in registros_dia:
                        clave = f"{registro.contador_bn_detectado}_{registro.contador_color_detectado}_{registro.contador_scan_detectado}"
                        if clave not in grupos_contadores:
                            grupos_contadores[clave] = []
                        grupos_contadores[clave].append(registro)
                    
                    # Eliminar duplicados (mantener el más reciente)
                    for clave, registros_grupo in grupos_contadores.items():
                        if len(registros_grupo) > 1:
                            # Ordenar por fecha (más reciente primero)
                            registros_ordenados = sorted(registros_grupo, key=lambda r: r.create_date, reverse=True)
                            
                            # Mantener el primero, eliminar el resto
                            for registro_dup in registros_ordenados[1:]:
                                _logger.info(f"🗑️ Eliminando duplicado: ID={registro_dup.id}, Fecha={registro_dup.create_date}")
                                _logger.info(f"   Contadores: BN={registro_dup.contador_bn_detectado}, C={registro_dup.contador_color_detectado}, S={registro_dup.contador_scan_detectado}")
                                registro_dup.unlink()
                                total_eliminados += 1
            
            _logger.info(f"✅ Limpieza completada: {total_eliminados} duplicados del mismo día eliminados")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Limpieza completada: {total_eliminados} duplicados del mismo día eliminados',
                    'type': 'success'
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error limpiando duplicados del mismo día: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error en limpieza: {str(e)}',
                    'type': 'danger'
                }
            }


    # MÉTODO PARA FORZAR PROCESAMIENTO DE UN CORREO HOY
    def forzar_procesamiento_hoy(self, serie_equipo):
        """
        NUEVO: Fuerza el procesamiento de un correo Counter List para hoy
        """
        try:
            _logger.info(f"🔄 === FORZANDO PROCESAMIENTO PARA HOY ===")
            _logger.info(f"🎯 Serie: {serie_equipo}")
            
            # CORRECCIÓN: Buscar correos Counter List recientes de esta serie
            # Primero buscar por asunto Counter List, luego filtrar por contenido
            correos_counter_list = self.env['mail.message'].search([
                ('message_type', '=', 'email'),
                ('date', '>=', fields.Datetime.now() - timedelta(hours=24)),
                '|', '|', '|',
                ('subject', 'ilike', 'counter list'),
                ('subject', 'ilike', 'counter page'),
                ('subject', 'ilike', 'page counter'),
                ('subject', 'ilike', 'lista contador')
            ], order='date desc')
            
            _logger.info(f"📧 Correos Counter List encontrados: {len(correos_counter_list)}")
            
            # Filtrar por serie en el contenido
            correo_encontrado = None
            for correo in correos_counter_list:
                contenido = correo.body or ""
                if serie_equipo.upper() in contenido.upper():
                    correo_encontrado = correo
                    _logger.info(f"✅ Correo encontrado con serie {serie_equipo}")
                    break
            
            if not correo_encontrado:
                mensaje = f"No se encontraron correos Counter List recientes para la serie {serie_equipo}"
                _logger.warning(f"⚠️ {mensaje}")
                _logger.info(f"💡 Correos Counter List disponibles:")
                for correo in correos_counter_list[:5]:
                    contenido_muestra = (correo.body or "")[:100]
                    _logger.info(f"   - {correo.subject} | {contenido_muestra}...")
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': mensaje,
                        'type': 'warning'
                    }
                }
            
            asunto = correo_encontrado.subject or f'Sin asunto - {correo_encontrado.id}'
            
            _logger.info(f"📧 Procesando correo: '{asunto}'")
            _logger.info(f"📅 Fecha correo: {correo_encontrado.date}")
            
            # CORRECCIÓN: Verificar si ya existe un registro hoy para evitar duplicados
            hoy = fields.Date.today()
            registro_hoy = self.search([
                ('serie_detectada', '=', serie_equipo),
                ('create_date', '>=', hoy),
                ('create_date', '<', hoy + timedelta(days=1))
            ], limit=1)
            
            if registro_hoy:
                mensaje = f"⚠️ Ya existe un registro hoy para la serie {serie_equipo} (ID: {registro_hoy.id})"
                _logger.warning(mensaje)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': mensaje,
                        'type': 'info'
                    }
                }
            
            # Crear registro forzado
            registro = self.create({
                'name': f"{asunto} (Forzado {fields.Date.today()})",
                'remitente': correo_encontrado.email_from,
                'contenido_original': correo_encontrado.body or asunto,
                'estado': 'pendiente'
            })
            
            _logger.info(f"🆕 Registro forzado creado: ID={registro.id}")
            
            # Procesar
            if registro.procesar_correo_inteligente():
                mensaje = f"✅ Procesamiento forzado exitoso para serie {serie_equipo}. Serie detectada: {registro.serie_detectada}, BN: {registro.contador_bn_detectado}, Scan: {registro.contador_scan_detectado}"
                _logger.info(mensaje)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f"✅ Procesamiento forzado exitoso para serie {serie_equipo}",
                        'type': 'success'
                    }
                }
            else:
                mensaje = f"❌ Error en procesamiento forzado para serie {serie_equipo}. Estado: {registro.estado}, Error: {registro.mensaje_error}"
                _logger.warning(mensaje)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f"❌ Error en procesamiento forzado para serie {serie_equipo}",
                        'type': 'danger'
                    }
                }
            
        except Exception as e:
            _logger.error(f"❌ Error en procesamiento forzado: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error: {str(e)}',
                    'type': 'danger'
                }
            }
    @api.model
    def buscar_correos_counter_list_especificos(self, horas=48):
        """
        NUEVO: Busca SOLO correos que contengan 'Counter List' o 'Counter Page'
        """
        try:
            _logger.info(f"🔍 === BÚSQUEDA ESPECÍFICA: COUNTER LIST/PAGE ===")
            
            fecha_limite = fields.Datetime.now() - timedelta(hours=horas)
            
            # Buscar SOLO correos con Counter List/Page en el asunto
            correos_counter = self.env['mail.message'].search([
                ('message_type', '=', 'email'),
                ('date', '>=', fecha_limite),
                '|', '|', '|',
                ('subject', 'ilike', 'counter list'),
                ('subject', 'ilike', 'counter page'),
                ('subject', 'ilike', 'page counter'),
                ('subject', 'ilike', 'lista contador')
            ], order='date desc')
            
            _logger.info(f"📧 Correos Counter List/Page encontrados: {len(correos_counter)}")
            
            if not correos_counter:
                _logger.warning("⚠️ NO SE ENCONTRARON CORREOS 'COUNTER LIST' NI 'COUNTER PAGE'")
                _logger.info("💡 Esto significa que:")
                _logger.info("   1. No han llegado correos de contadores en las últimas 48h, O")
                _logger.info("   2. Los correos tienen un asunto diferente al esperado")
                return []
            
            correos_no_procesados = []
            
            for i, correo in enumerate(correos_counter, 1):
                asunto = correo.subject or f'Sin asunto - {correo.id}'
                remitente = correo.email_from or 'Sin remitente'
                fecha_str = correo.date.strftime('%Y-%m-%d %H:%M') if correo.date else 'Sin fecha'
                
                _logger.info(f"📧 {i}. COUNTER LIST/PAGE:")
                _logger.info(f"    Asunto: '{asunto}'")
                _logger.info(f"    Remitente: {remitente}")
                _logger.info(f"    Fecha: {fecha_str}")
                
                # Verificar si ya fue procesado
                existe = self.search([
                    ('name', '=', asunto),
                    ('remitente', '=', remitente)
                ], limit=1)
                
                if existe:
                    _logger.info(f"    ✅ Ya procesado: ID={existe.id}, Estado={existe.estado}")
                    if existe.estado == 'filtrado':
                        _logger.warning(f"    ⚠️ PROBLEMA: Counter List fue filtrado incorrectamente")
                else:
                    _logger.info(f"    🆕 NO PROCESADO - Necesita procesamiento")
                    correos_no_procesados.append(correo)
                    
                    # Mostrar contenido para verificar
                    contenido = correo.body or "Sin contenido"
                    if len(contenido) > 100:
                        _logger.info(f"    📄 Contenido (muestra): {contenido[:200]}...")
                        
                        # Buscar indicadores de contadores reales
                        indicadores = ['serial', 'serie', 'T_Total', 'total', 'black', 'color', 'scan']
                        encontrados = [ind for ind in indicadores if ind.lower() in contenido.lower()]
                        if encontrados:
                            _logger.info(f"    ✅ Contiene indicadores: {encontrados}")
                        else:
                            _logger.warning(f"    ⚠️ No contiene indicadores obvios de contadores")
            
            _logger.info(f"📊 === RESUMEN COUNTER LIST/PAGE ===")
            _logger.info(f"🔍 Total encontrados: {len(correos_counter)}")
            _logger.info(f"🆕 No procesados: {len(correos_no_procesados)}")
            _logger.info(f"✅ Ya procesados: {len(correos_counter) - len(correos_no_procesados)}")
            
            return correos_no_procesados
            
        except Exception as e:
            _logger.error(f"❌ Error buscando Counter List: {e}")
            return []


    # MÉTODO PARA PROCESAR MANUALMENTE LOS COUNTER LIST NO PROCESADOS
    def procesar_counter_list_pendientes(self):
        """
        NUEVO: Procesa manualmente los correos Counter List que no se procesaron
        """
        try:
            _logger.info(f"🔄 === PROCESANDO COUNTER LIST PENDIENTES ===")
            
            # Buscar correos Counter List no procesados
            correos_pendientes = self.buscar_correos_counter_list_especificos(48)
            
            if not correos_pendientes:
                mensaje = "No se encontraron correos 'Counter List' pendientes de procesar"
                _logger.info(f"ℹ️ {mensaje}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': mensaje,
                        'type': 'info'
                    }
                }
            
            procesados_exitosos = 0
            errores = 0
            
            for correo in correos_pendientes:
                try:
                    asunto = correo.subject or f'Sin asunto - {correo.id}'
                    
                    _logger.info(f"🔄 Procesando: '{asunto}'")
                    
                    # Crear y procesar registro
                    registro = self.create({
                        'name': asunto,
                        'remitente': correo.email_from,
                        'contenido_original': correo.body or asunto,
                        'estado': 'pendiente'
                    })
                    
                    if registro.procesar_correo_inteligente():
                        procesados_exitosos += 1
                        _logger.info(f"✅ Procesado exitosamente: {asunto}")
                    else:
                        errores += 1
                        _logger.warning(f"⚠️ Error procesando: {asunto}")
                    
                except Exception as e:
                    errores += 1
                    _logger.error(f"❌ Error procesando correo: {e}")
            
            mensaje = f"Procesamiento completado: {procesados_exitosos} exitosos, {errores} errores de {len(correos_pendientes)} correos Counter List"
            _logger.info(f"📊 {mensaje}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': mensaje,
                    'type': 'success' if errores == 0 else 'warning'
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error procesando Counter List pendientes: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error: {str(e)}',
                    'type': 'danger'
                }
            }


    # MÉTODO PARA LIMPIAR REGISTROS QUE NO SON COUNTER LIST
    def limpiar_registros_no_counter_list(self):
        """
        NUEVO: Elimina todos los registros que NO son Counter List ni Counter Page
        """
        try:
            _logger.info(f"🧹 === LIMPIANDO REGISTROS QUE NO SON COUNTER LIST ===")
            
            # Buscar todos los registros que NO contienen Counter List/Page
            registros_incorrectos = self.search([
                ('name', 'not ilike', 'counter list'),
                ('name', 'not ilike', 'counter page'),
                ('name', 'not ilike', 'page counter'),
                ('name', 'not ilike', 'lista contador')
            ])
            
            _logger.info(f"📋 Registros que NO son Counter List encontrados: {len(registros_incorrectos)}")
            
            # Mostrar algunos ejemplos antes de eliminar
            for i, registro in enumerate(registros_incorrectos[:10], 1):
                _logger.info(f"🗑️ {i}. A eliminar: '{registro.name}' (ID={registro.id})")
            
            if len(registros_incorrectos) > 10:
                _logger.info(f"   ... y {len(registros_incorrectos) - 10} más")
            
            if registros_incorrectos:
                cantidad = len(registros_incorrectos)
                registros_incorrectos.unlink()
                _logger.info(f"✅ Eliminados {cantidad} registros que no son Counter List")
            else:
                cantidad = 0
                _logger.info("ℹ️ No se encontraron registros incorrectos para eliminar")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Limpieza completada: {cantidad} registros eliminados',
                    'type': 'success'
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error limpiando registros: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error en limpieza: {str(e)}',
                    'type': 'danger'
                }
            }

    
    @api.model
    def procesar_correos_directos_manual(self, horas=24):
        """
        NUEVO: Procesamiento manual directo desde mail.message
        Útil para probar o procesar correos específicos
        CORRECCIÓN: Manejo de parámetros que vienen como lista
        """
        try:
            # CORRECCIÓN: Validar y convertir el parámetro horas si viene como lista
            if isinstance(horas, list):
                if len(horas) > 0 and isinstance(horas[0], (int, float)):
                    horas = int(horas[0])
                    _logger.info(f"🔧 Parámetro horas convertido de lista a entero: {horas}")
                else:
                    _logger.warning(f"⚠️ Parámetro horas inválido en lista: {horas}, usando valor por defecto")
                    horas = 24
            elif not isinstance(horas, (int, float)):
                _logger.warning(f"⚠️ Parámetro horas inválido: {horas} (tipo: {type(horas)}), usando valor por defecto")
                horas = 24
            
            # Asegurar que sea entero positivo
            horas = max(1, int(horas))
            
            _logger.info(f"🔧 === PROCESAMIENTO MANUAL DIRECTO ({horas}h) ===")
            
            fecha_limite = fields.Datetime.now() - timedelta(hours=horas)
            
            # Buscar correos de contadores directamente
            correos_contadores = self.env['mail.message'].search([
                ('message_type', '=', 'email'),
                ('date', '>=', fecha_limite),
                '|', '|', '|',
                ('subject', 'ilike', 'counter'),
                ('subject', 'ilike', 'contador'),
                ('email_from', 'ilike', 'printer@andescopiers.com.pe'),
                ('body', 'ilike', 'serial number')
            ], order='date desc')
            
            _logger.info(f"📧 Correos de contadores encontrados: {len(correos_contadores)}")
            
            # Mostrar lista para revisar
            for i, correo in enumerate(correos_contadores[:10], 1):  # Mostrar primeros 10
                _logger.info(f"{i}. '{correo.subject}' - {correo.email_from} - {correo.date}")
            
            # Procesar cada correo
            procesados = 0
            errores = 0
            
            for correo in correos_contadores:
                try:
                    # Verificar si ya existe
                    existe = self.search([
                        ('name', '=', correo.subject),
                        ('remitente', '=', correo.email_from)
                    ], limit=1)
                    
                    if not existe:
                        # Crear y procesar
                        registro = self.create({
                            'name': correo.subject or f'Sin asunto - {correo.id}',
                            'remitente': correo.email_from,
                            'contenido_original': correo.body or '',
                            'estado': 'pendiente'
                        })
                        
                        if registro.procesar_correo_inteligente():
                            procesados += 1
                            _logger.info(f"✅ Procesado: {registro.name}")
                        else:
                            _logger.warning(f"⚠️ Falló: {registro.name}")
                            
                except Exception as e:
                    errores += 1
                    _logger.error(f"❌ Error procesando correo: {e}")
            
            mensaje = f"Procesamiento manual completado: {procesados} procesados, {errores} errores de {len(correos_contadores)} encontrados"
            _logger.info(mensaje)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': mensaje,
                    'type': 'success' if errores == 0 else 'warning'
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error en procesamiento manual: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error: {str(e)}',
                    'type': 'danger'
                }
            }
    def test_sistema_inteligente(self):
        """
        Método de prueba para el sistema inteligente
        CORRECCIÓN: Mejorado con más casos de prueba
        """
        try:
            _logger.info("🧪 === PROBANDO SISTEMA INTELIGENTE ===")
            
            # Probar filtro de asuntos
            asuntos_prueba = [
                "Counter List",          # Válido
                "Page Counter",          # Válido
                "counter list",          # Válido (case insensitive)
                "Ricoh Counter Report",  # Válido
                "Error Alert",           # No válido
                "Maintenance Required",  # No válido
                "contador konica",       # Válido
                "contadores ricoh"       # Válido
            ]
            
            _logger.info("🔍 === PROBANDO FILTRO DE ASUNTOS ===")
            for asunto in asuntos_prueba:
                resultado = self._es_correo_de_contadores_mejorado(asunto)
                _logger.info(f"📧 '{asunto}' → {'✅ VÁLIDO' if resultado else '❌ FILTRADO'}")
            
            # Probar detección de idioma
            textos_prueba = {
                'bizhub_es': "[Número de serie], A5C4011011874 [Contador total],00268741",
                'ricoh_en': "Serial No: 3359PB02667 T_TotalPrtPGS:36089",
                'ricoh_es': "Nº de serie: 3359PB02667 T_TotalPrtPGS:36089",
                'generico': "Model XYZ123 Pages: 15000 Date: 2025-01-01",
                'monocroma': "Total Counter: 25000 Black Pages: 25000 Serial: ABC123456"
            }
            
            _logger.info("🌍 === PROBANDO DETECCIÓN DE IDIOMA ===")
            for nombre, texto in textos_prueba.items():
                idioma, confianza, palabras = self.detectar_idioma_automatico(texto)
                _logger.info(f"🌍 {nombre} → {idioma} ({confianza:.1f}%) | Palabras: {palabras[:3]}")
            
            # Probar detección de marca
            _logger.info("🏭 === PROBANDO DETECCIÓN DE MARCA ===")
            for nombre, texto in textos_prueba.items():
                marca = self.detectar_marca_automatico(texto)
                _logger.info(f"🏭 {nombre} → Marca: {marca}")
            
            # Probar detección de máquina monocroma
            _logger.info("🖤 === PROBANDO DETECCIÓN MONOCROMA ===")
            textos_monocroma = {
                'mono_explicito': "Monochrome printer - Total pages: 15000",
                'mono_implicito': "Total Counter: 25000 Black White printer",
                'color_explicito': "Color Counter: 5000 Black Counter: 20000",
                'ricoh_mono': "T_TotalPrtPGS: 25000 Serial No: ABC123"
            }
            
            for nombre, texto in textos_monocroma.items():
                es_mono = self._detectar_maquina_monocroma(texto, 'english')
                _logger.info(f"🖤 {nombre} → {'MONOCROMA' if es_mono else 'COLOR'}")
            
            # Probar búsqueda de series
            _logger.info("🔍 === PROBANDO BÚSQUEDA DE SERIES ===")
            for nombre, texto in textos_prueba.items():
                serie = self._buscar_serie_fallback(texto)
                _logger.info(f"🔍 {nombre} → Serie: {serie or 'No encontrada'}")
            
            _logger.info("✅ === PRUEBAS COMPLETADAS ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Prueba del sistema inteligente completada. Revisa logs para detalles.',
                    'type': 'success'
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error en prueba: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error en prueba: {str(e)}',
                    'type': 'danger'
                }
            }

    def generar_patrones_para_correo_actual(self):
        """
        Genera patrones específicamente para el correo actual
        CORRECCIÓN: Validaciones mejoradas
        """
        try:
            _logger.info(f"🎯 === GENERANDO PATRONES PARA CORREO ACTUAL ===")
            _logger.info(f"📧 Registro ID={self.id}")
            
            if not self.contenido_procesado:
                # CORRECCIÓN: Intentar procesar el contenido si no existe
                if self.contenido_original:
                    texto_limpio = self.limpiar_html_correo(self.contenido_original)
                    self.contenido_procesado = texto_limpio
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'message': 'No hay contenido para procesar. Verifique el correo original.',
                            'type': 'warning'
                        }
                    }
            
            # Realizar análisis si no se ha hecho
            if not self.idioma_detectado:
                idioma, confianza, palabras = self.detectar_idioma_automatico(self.contenido_procesado)
                self.idioma_detectado = idioma
                self.confianza_deteccion = confianza
                self.palabras_clave_encontradas = ', '.join(palabras)
            
            if not self.marca_detectada:
                self.marca_detectada = self.detectar_marca_automatico(self.contenido_procesado)
            
            if not self.formato_detectado:
                estructura = self.analizar_estructura_contenido(self.contenido_procesado)
                self.formato_detectado = estructura.get('estructura_tipo', 'desconocida')
                self.estructura_detectada = str(estructura)
            
            # Generar patrones
            patrones_anteriores = self.patrones_auto_generados
            if self.generar_patrones_automaticamente():
                patrones_nuevos = self.patrones_auto_generados - patrones_anteriores
                mensaje = f"✅ Patrones generados exitosamente para este correo. {patrones_nuevos} patrones nuevos creados."
                tipo = 'success'
            else:
                mensaje = "⚠️ No se pudieron generar patrones para este correo. Revise el contenido y formato."
                tipo = 'warning'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': mensaje,
                    'type': tipo
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error generando patrones para correo actual: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error: {str(e)}',
                    'type': 'danger'
                }
            }


    @api.model
    def obtener_estadisticas_dashboard(self):
        """
        Obtiene estadísticas para dashboard de monitoreo
        CORRECCIÓN: Manejo seguro de errores y validaciones
        """
        try:
            _logger.info("📊 === GENERANDO ESTADÍSTICAS DASHBOARD ===")
            
            # Estadísticas generales
            total_registros = self.env['contador.automatico'].search_count([])
            
            registros_procesados = self.env['contador.automatico'].search_count([
                ('estado', '=', 'procesado')
            ])
            
            registros_manual = self.env['contador.automatico'].search_count([
                ('estado', '=', 'manual')
            ])
            
            registros_error = self.env['contador.automatico'].search_count([
                ('estado', '=', 'error')
            ])
            
            registros_filtrados = self.env['contador.automatico'].search_count([
                ('estado', '=', 'filtrado')
            ])
            
            # Estadísticas de últimos 7 días
            hace_7_dias = fields.Date.today() - timedelta(days=7)
            registros_ultima_semana = self.env['contador.automatico'].search_count([
                ('create_date', '>=', hace_7_dias)
            ])
            
            # Estadísticas de aprendizaje automático
            registros_con_aprendizaje = self.env['contador.automatico'].search_count([
                ('requiere_aprendizaje', '=', True)
            ])
            
            registros_aprendizaje_completado = self.env['contador.automatico'].search_count([
                ('aprendizaje_completado', '=', True)
            ])
            
            total_patrones_generados = self.env['contador.automatico'].search([
                ('patrones_auto_generados', '>', 0)
            ])
            suma_patrones = sum(registro.patrones_auto_generados for registro in total_patrones_generados)
            
            # Estadísticas por marca (con manejo de errores)
            try:
                marcas_detectadas = self.env['contador.automatico'].read_group(
                    [('marca_detectada', '!=', False)],
                    ['marca_detectada'],
                    ['marca_detectada']
                )
            except:
                marcas_detectadas = []
            
            # Estadísticas por idioma (con manejo de errores)
            try:
                idiomas_detectados = self.env['contador.automatico'].read_group(
                    [('idioma_detectado', '!=', False)],
                    ['idioma_detectado'],
                    ['idioma_detectado']
                )
            except:
                idiomas_detectados = []
            
            # Patrones activos (verificar si el modelo existe)
            try:
                total_patrones_activos = self.env['patron.contador'].search_count([
                    ('activo', '=', True)
                ])
                
                patrones_auto_generados = self.env['patron.contador'].search_count([
                    ('activo', '=', True),
                    ('auto_generado', '=', True)
                ])
            except:
                total_patrones_activos = 0
                patrones_auto_generados = 0
            
            # Estadísticas CRON (con manejo de errores)
            try:
                estadisticas_cron = self.env['contador.automatico.estadisticas'].search([
                    ('fecha', '>=', hace_7_dias)
                ])
                total_cron_encontrados = sum(est.correos_encontrados_cron for est in estadisticas_cron)
                total_cron_procesados = sum(est.correos_procesados_cron for est in estadisticas_cron)
            except:
                total_cron_encontrados = 0
                total_cron_procesados = 0
            
            # CORRECCIÓN: Calcular tasas de éxito
            tasa_procesamiento = (registros_procesados / total_registros * 100) if total_registros > 0 else 0
            tasa_automatico = (registros_aprendizaje_completado / total_registros * 100) if total_registros > 0 else 0
            
            estadisticas = {
                'resumen_general': {
                    'total_registros': total_registros,
                    'procesados': registros_procesados,
                    'manual': registros_manual,
                    'error': registros_error,
                    'filtrados': registros_filtrados,
                    'ultima_semana': registros_ultima_semana,
                    'tasa_procesamiento': round(tasa_procesamiento, 1),
                    'tasa_automatico': round(tasa_automatico, 1)
                },
                'aprendizaje_automatico': {
                    'requiere_aprendizaje': registros_con_aprendizaje,
                    'aprendizaje_completado': registros_aprendizaje_completado,
                    'patrones_generados_total': suma_patrones
                },
                'patrones': {
                    'total_activos': total_patrones_activos,
                    'auto_generados': patrones_auto_generados,
                    'efectividad': round((patrones_auto_generados / total_patrones_activos * 100) if total_patrones_activos > 0 else 0, 1)
                },
                'distribucion_marcas': [
                    {'marca': marca['marca_detectada'], 'cantidad': marca['marca_detectada_count']}
                    for marca in marcas_detectadas
                ],
                'distribucion_idiomas': [
                    {'idioma': idioma['idioma_detectado'], 'cantidad': idioma['idioma_detectado_count']}
                    for idioma in idiomas_detectados
                ],
                'cron_stats': {
                    'correos_encontrados_7_dias': total_cron_encontrados,
                    'correos_procesados_7_dias': total_cron_procesados,
                    'efectividad_cron': round((total_cron_procesados / total_cron_encontrados * 100) if total_cron_encontrados > 0 else 0, 1)
                }
            }
            
            _logger.info("✅ Estadísticas dashboard generadas exitosamente")
            _logger.info(f"📊 Resumen: {total_registros} total, {registros_procesados} procesados ({tasa_procesamiento:.1f}%)")
            
            return estadisticas
            
        except Exception as e:
            _logger.error(f"❌ Error generando estadísticas dashboard: {e}")
            return {
                'resumen_general': {
                    'total_registros': 0,
                    'procesados': 0,
                    'manual': 0,
                    'error': 0,
                    'filtrados': 0,
                    'ultima_semana': 0,
                    'tasa_procesamiento': 0,
                    'tasa_automatico': 0
                },
                'error': str(e)
            }

    def optimizar_patrones_automaticamente(self):
        """
        Optimiza automáticamente los patrones basado en estadísticas de uso
        CORRECCIÓN: Validaciones mejoradas y manejo de errores
        """
        try:
            _logger.info("🔧 === OPTIMIZANDO PATRONES AUTOMÁTICAMENTE ===")
            
            # Verificar si el modelo de patrones existe
            try:
                patrones_disponibles = self.env['patron.contador'].search_count([])
                if patrones_disponibles == 0:
                    _logger.warning("⚠️ No hay patrones disponibles para optimizar")
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'message': 'No hay patrones disponibles para optimizar',
                            'type': 'info'
                        }
                    }
            except:
                _logger.error("❌ Modelo 'patron.contador' no disponible")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'Modelo de patrones no disponible',
                        'type': 'error'
                    }
                }
            
            # Buscar patrones con baja efectividad
            patrones_problematicos = self.env['patron.contador'].search([
                ('activo', '=', True),
                ('veces_usado', '>', 0)
            ])
            
            patrones_optimizados = 0
            patrones_desactivados = 0
            
            for patron in patrones_problematicos:
                # Calcular tasa de éxito
                tasa_exito = 0
                if hasattr(patron, 'casos_detectados') and hasattr(patron, 'casos_fallidos'):
                    total_casos = patron.casos_detectados + patron.casos_fallidos
                    if total_casos > 0:
                        tasa_exito = (patron.casos_detectados / total_casos) * 100
                
                # CORRECCIÓN: Criterios más estrictos para desactivar patrones
                if tasa_exito < 15 and patron.veces_usado > 10:  # Más estricto
                    patron.write({'activo': False})
                    patrones_desactivados += 1
                    _logger.info(f"⏸️ Patrón desactivado por baja efectividad: {patron.name} ({tasa_exito:.1f}%)")
                
                # Si el patrón nunca se usa, reducir prioridad gradualmente
                elif patron.veces_usado == 0 and patron.create_date < (fields.Datetime.now() - timedelta(days=14)):
                    if patron.orden < 50:
                        patron.write({'orden': patron.orden + 5})  # Incremento menor
                        patrones_optimizados += 1
                        _logger.info(f"📉 Reducida prioridad de patrón no usado: {patron.name}")
            
            # Buscar patrones muy exitosos para darles mayor prioridad
            patrones_exitosos = self.env['patron.contador'].search([
                ('activo', '=', True),
                ('veces_usado', '>', 5)  # Reducido el umbral
            ])
            
            for patron in patrones_exitosos:
                if hasattr(patron, 'casos_detectados') and hasattr(patron, 'casos_fallidos'):
                    total_casos = patron.casos_detectados + patron.casos_fallidos
                    if total_casos > 0:
                        tasa_exito = (patron.casos_detectados / total_casos) * 100
                        
                        # Si tiene alta efectividad, darle mayor prioridad
                        if tasa_exito > 85 and patron.orden > 2:  # Más permisivo
                            nuevo_orden = max(1, patron.orden - 1)
                            patron.write({'orden': nuevo_orden})
                            patrones_optimizados += 1
                            _logger.info(f"📈 Aumentada prioridad de patrón exitoso: {patron.name} ({tasa_exito:.1f}%)")
            
            # CORRECCIÓN: Optimizar patrones auto-generados poco efectivos
            patrones_auto = self.env['patron.contador'].search([
                ('auto_generado', '=', True),
                ('activo', '=', True),
                ('veces_usado', '>', 3)
            ])
            
            for patron in patrones_auto:
                if hasattr(patron, 'casos_detectados') and hasattr(patron, 'casos_fallidos'):
                    total_casos = patron.casos_detectados + patron.casos_fallidos
                    if total_casos > 0:
                        tasa_exito = (patron.casos_detectados / total_casos) * 100
                        
                        # Patrones auto-generados con muy baja efectividad
                        if tasa_exito < 25:
                            patron.write({'activo': False})
                            patrones_desactivados += 1
                            _logger.info(f"🤖⏸️ Patrón auto-generado desactivado: {patron.name} ({tasa_exito:.1f}%)")
            
            _logger.info(f"✅ Optimización completada: {patrones_optimizados} optimizados, {patrones_desactivados} desactivados")
            
            mensaje = f'Optimización completada: {patrones_optimizados} patrones optimizados, {patrones_desactivados} desactivados'
            if patrones_optimizados == 0 and patrones_desactivados == 0:
                mensaje = 'Optimización completada: No se encontraron patrones que requieran ajustes'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': mensaje,
                    'type': 'success'
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error optimizando patrones: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error en optimización: {str(e)}',
                    'type': 'danger'
                }
            }

    def generar_reporte_actividad(self, dias=7):
        """
        Genera reporte de actividad de los últimos N días
        CORRECCIÓN: Manejo mejorado de errores y más detalles
        """
        try:
            _logger.info(f"📋 === GENERANDO REPORTE DE ACTIVIDAD ({dias} días) ===")
            
            fecha_inicio = fields.Date.today() - timedelta(days=dias)
            
            # Registros por día (con manejo de errores)
            try:
                registros_por_dia = self.env['contador.automatico'].read_group(
                    [('create_date', '>=', fecha_inicio)],
                    ['create_date:day', 'estado'],
                    ['create_date:day', 'estado'],
                    lazy=False
                )
            except:
                registros_por_dia = []
            
            # Procesamiento por estado
            try:
                estados_resumen = self.env['contador.automatico'].read_group(
                    [('create_date', '>=', fecha_inicio)],
                    ['estado'],
                    ['estado']
                )
            except:
                estados_resumen = []
            
            # Marcas más procesadas
            try:
                marcas_resumen = self.env['contador.automatico'].read_group(
                    [
                        ('create_date', '>=', fecha_inicio),
                        ('marca_detectada', '!=', False)
                    ],
                    ['marca_detectada'],
                    ['marca_detectada']
                )
            except:
                marcas_resumen = []
            
            # Patrones más usados (con verificación del modelo)
            try:
                patrones_mas_usados = self.env['patron.contador'].search([
                    ('veces_usado', '>', 0)
                ], order='veces_usado desc', limit=10)
                
                patrones_info = [
                    {
                        'nombre': p.name,
                        'tipo': p.tipo,
                        'veces_usado': p.veces_usado,
                        'ultima_deteccion': p.ultima_deteccion,
                        'auto_generado': getattr(p, 'auto_generado', False)
                    }
                    for p in patrones_mas_usados
                ]
            except:
                patrones_info = []
            
            # CORRECCIÓN: Estadísticas adicionales
            total_registros_periodo = self.env['contador.automatico'].search_count([
                ('create_date', '>=', fecha_inicio)
            ])
            
            procesados_periodo = self.env['contador.automatico'].search_count([
                ('create_date', '>=', fecha_inicio),
                ('estado', '=', 'procesado')
            ])
            
            tasa_exito_periodo = (procesados_periodo / total_registros_periodo * 100) if total_registros_periodo > 0 else 0
            
            reporte = {
                'periodo': f"Últimos {dias} días",
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fields.Date.today(),
                'total_registros': total_registros_periodo,
                'procesados': procesados_periodo,
                'tasa_exito': round(tasa_exito_periodo, 1),
                'registros_por_dia': registros_por_dia,
                'resumen_estados': estados_resumen,
                'marcas_procesadas': marcas_resumen,
                'patrones_top': patrones_info,
                'generado_en': fields.Datetime.now()
            }
            
            _logger.info(f"✅ Reporte de actividad generado: {total_registros_periodo} registros, {tasa_exito_periodo:.1f}% éxito")
            return reporte
            
        except Exception as e:
            _logger.error(f"❌ Error generando reporte: {e}")
            return {
                'error': str(e),
                'periodo': f"Últimos {dias} días",
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fields.Date.today(),
            }

    def limpiar_registros_antiguos(self, dias_mantener=90):
        """
        Limpia registros antiguos para mantener la BD optimizada
        CORRECCIÓN: Criterios más inteligentes de limpieza
        """
        try:
            _logger.info(f"🧹 === LIMPIANDO REGISTROS ANTIGUOS (>{dias_mantener} días) ===")
            
            fecha_limite = fields.Date.today() - timedelta(days=dias_mantener)
            
            # CORRECCIÓN: Criterios más específicos para limpiar
            # 1. Registros filtrados antiguos (no son útiles)
            registros_filtrados = self.env['contador.automatico'].search([
                ('estado', '=', 'filtrado'),
                ('create_date', '<', fecha_limite)
            ])
            
            # 2. Registros en error muy antiguos (más de 6 meses)
            fecha_error_limite = fields.Date.today() - timedelta(days=180)
            registros_error_antiguos = self.env['contador.automatico'].search([
                ('estado', '=', 'error'),
                ('create_date', '<', fecha_error_limite)
            ])
            
            # 3. Registros duplicados (mismo asunto, remitente y fecha similar)
            registros_duplicados = self._encontrar_registros_duplicados()
            
            if not (registros_filtrados or registros_error_antiguos or registros_duplicados):
                _logger.info("ℹ️ No hay registros antiguos para limpiar")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'No hay registros antiguos para limpiar',
                        'type': 'info'
                    }
                }
            
            # CORRECCIÓN: Preservar registros importantes
            registros_importantes = self.env['contador.automatico'].search([
                ('estado', '=', 'procesado'),
                ('equipo_id', '!=', False),
                ('create_date', '<', fecha_limite)
            ])
            
            # Combinar registros a eliminar
            registros_eliminar = registros_filtrados | registros_error_antiguos
            for dup in registros_duplicados:
                registros_eliminar |= dup
            
            # No eliminar los importantes
            registros_eliminar = registros_eliminar - registros_importantes
            
            if registros_eliminar:
                cantidad_eliminar = len(registros_eliminar)
                
                # Log de muestra antes de eliminar
                for registro in registros_eliminar[:5]:
                    _logger.info(f"🗑️ A eliminar: ID={registro.id}, Estado={registro.estado}, Fecha={registro.create_date}")
                
                registros_eliminar.unlink()
                _logger.info(f"🗑️ Eliminados {cantidad_eliminar} registros antiguos")
            else:
                cantidad_eliminar = 0
            
            if registros_importantes:
                _logger.info(f"💾 Conservados {len(registros_importantes)} registros procesados importantes")
            
            # CORRECCIÓN: Limpiar también estadísticas muy antiguas
            try:
                fecha_stats_limite = fields.Date.today() - timedelta(days=60)
                stats_antiguas = self.env['contador.automatico.estadisticas'].search([
                    ('fecha', '<', fecha_stats_limite)
                ])
                
                if stats_antiguas:
                    cantidad_stats = len(stats_antiguas)
                    stats_antiguas.unlink()
                    _logger.info(f"📊 Eliminadas {cantidad_stats} estadísticas antiguas")
                else:
                    cantidad_stats = 0
            except:
                cantidad_stats = 0
                _logger.info("ℹ️ Modelo de estadísticas no existe, saltando limpieza")
            
            mensaje = f'Limpieza completada: {cantidad_eliminar} registros eliminados'
            if registros_importantes:
                mensaje += f', {len(registros_importantes)} importantes conservados'
            if cantidad_stats > 0:
                mensaje += f', {cantidad_stats} estadísticas limpiadas'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': mensaje,
                    'type': 'success'
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error limpiando registros: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error en limpieza: {str(e)}',
                    'type': 'danger'
                }
            }

    def _encontrar_registros_duplicados(self):
        """
        NUEVO: Encuentra registros duplicados de forma más inteligente
        """
        try:
            registros_duplicados = []
            todos_registros = self.env['contador.automatico'].search([])
            
            # Agrupar por clave similar
            grupos = {}
            for registro in todos_registros:
                # Crear clave más flexible
                asunto_limpio = re.sub(r'\s+', ' ', registro.name.lower().strip())
                fecha_str = registro.create_date.strftime('%Y-%m-%d') if registro.create_date else 'sin_fecha'
                clave = f"{asunto_limpio}|{registro.remitente or ''}|{fecha_str}"
                
                if clave not in grupos:
                    grupos[clave] = []
                grupos[clave].append(registro)
            
            # Encontrar grupos con más de un registro
            for clave, registros_grupo in grupos.items():
                if len(registros_grupo) > 1:
                    # Mantener el más reciente, marcar otros para eliminar
                    registros_grupo_ordenados = sorted(registros_grupo, key=lambda r: r.create_date, reverse=True)
                    for registro_dup in registros_grupo_ordenados[1:]:  # Saltar el primero (más reciente)
                        registros_duplicados.append(registro_dup)
                        
            _logger.info(f"🔍 Encontrados {len(registros_duplicados)} registros duplicados")
            return registros_duplicados
            
        except Exception as e:
            _logger.error(f"❌ Error encontrando duplicados: {e}")
            return []

    @api.model
    def mantenimiento_automatico_sistema(self):
        """
        Ejecuta mantenimiento automático completo del sistema
        CORRECCIÓN: Mantenimiento más inteligente y seguro
        """
        try:
            _logger.info("🔧 === INICIO MANTENIMIENTO AUTOMÁTICO SISTEMA ===")
            
            resultados = {
                'correos_procesados': 0,
                'patrones_optimizados': 0,
                'registros_limpiados': 0,
                'errores': []
            }
            
            # 1. Procesar correos perdidos
            _logger.info("📧 Ejecutando procesamiento de correos perdidos...")
            try:
                if self.cron_procesar_correos_perdidos():
                    resultados['correos_procesados'] = 1  # Indicador de éxito
                    _logger.info("✅ Procesamiento de correos completado")
                else:
                    resultados['errores'].append("Fallo en procesamiento de correos")
            except Exception as e:
                _logger.error(f"❌ Error procesando correos: {e}")
                resultados['errores'].append(f"Error correos: {str(e)}")
            
            # 2. Optimizar patrones (solo si hay registros para analizar)
            total_registros = self.env['contador.automatico'].search_count([])
            if total_registros > 10:  # Solo optimizar si hay suficientes datos
                _logger.info("⚙️ Ejecutando optimización de patrones...")
                try:
                    dummy_registro = self.env['contador.automatico'].search([], limit=1)
                    if dummy_registro:
                        resultado_opt = dummy_registro.optimizar_patrones_automaticamente()
                        if 'params' in resultado_opt and 'success' in resultado_opt['params']['type']:
                            resultados['patrones_optimizados'] = 1
                            _logger.info("✅ Optimización de patrones completada")
                except Exception as e:
                    _logger.error(f"❌ Error optimizando patrones: {e}")
                    resultados['errores'].append(f"Error optimización: {str(e)}")
            else:
                _logger.info("⏭️ Saltando optimización - pocos registros para analizar")
            
            # 3. Limpiar registros antiguos (solo domingos para evitar sobrecarga)
            hoy = fields.Date.today()
            if hoy.weekday() == 6:  # Domingo
                _logger.info("🧹 Ejecutando limpieza semanal...")
                try:
                    dummy_registro = self.env['contador.automatico'].search([], limit=1)
                    if dummy_registro:
                        resultado_limp = dummy_registro.limpiar_registros_antiguos()
                        if 'params' in resultado_limp and 'success' in resultado_limp['params']['type']:
                            resultados['registros_limpiados'] = 1
                            _logger.info("✅ Limpieza semanal completada")
                except Exception as e:
                    _logger.error(f"❌ Error en limpieza: {e}")
                    resultados['errores'].append(f"Error limpieza: {str(e)}")
            else:
                _logger.info("⏭️ Saltando limpieza - solo se ejecuta los domingos")
            
            # 4. Resumen final
            exitos = sum([resultados['correos_procesados'], resultados['patrones_optimizados'], resultados['registros_limpiados']])
            total_errores = len(resultados['errores'])
            
            _logger.info(f"📊 === RESUMEN MANTENIMIENTO ===")
            _logger.info(f"✅ Tareas exitosas: {exitos}")
            _logger.info(f"❌ Errores: {total_errores}")
            
            if total_errores == 0:
                _logger.info("🎉 Mantenimiento automático completado exitosamente")
                return True
            else:
                _logger.warning(f"⚠️ Mantenimiento completado con {total_errores} errores")
                for error in resultados['errores']:
                    _logger.warning(f"  - {error}")
                return False
            
        except Exception as e:
            _logger.error(f"❌ Error crítico en mantenimiento automático: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False


    def _enviar_notificacion_cron(self, resumen):
        """
        Envía notificación sobre la ejecución del CRON
        CORRECCIÓN: Notificaciones más inteligentes y menos invasivas
        """
        try:
            # CORRECCIÓN: Solo notificar en casos importantes
            debe_notificar = False
            razon_notificacion = ""
            
            # Notificar si hay correos procesados exitosamente
            if resumen.get('correos_procesados', 0) > 0:
                debe_notificar = True
                razon_notificacion = f"{resumen['correos_procesados']} correos procesados"
            
            # Notificar si hay muchos fallos (más del 50%)
            correos_encontrados = resumen.get('correos_encontrados', 0)
            correos_fallidos = resumen.get('correos_fallidos', 0)
            if correos_encontrados > 0 and (correos_fallidos / correos_encontrados) > 0.5:
                debe_notificar = True
                if razon_notificacion:
                    razon_notificacion += f", {correos_fallidos} fallos críticos"
                else:
                    razon_notificacion = f"{correos_fallidos} fallos críticos"
            
            if not debe_notificar:
                _logger.info("ℹ️ No se requiere notificación - ejecución normal sin eventos significativos")
                return
            
            _logger.info(f"📧 Enviando notificación CRON: {razon_notificacion}")
            
            # Buscar usuarios para notificar (con fallbacks)
            usuarios_notificar = []
            
            try:
                # Intentar grupo de administradores
                grupo_admin = self.env.ref('base.group_system')
                usuarios_notificar = grupo_admin.users[:3]  # Máximo 3 usuarios
            except:
                try:
                    # Fallback: usuario admin
                    usuario_admin = self.env['res.users'].search([('login', '=', 'admin')], limit=1)
                    if usuario_admin:
                        usuarios_notificar = [usuario_admin]
                except:
                    pass
            
            if not usuarios_notificar:
                _logger.warning("⚠️ No se encontraron usuarios para notificar")
                return
            
            # CORRECCIÓN: Preparar mensaje más conciso y útil
            fecha_str = resumen.get('fecha_ejecucion', fields.Datetime.now()).strftime('%Y-%m-%d %H:%M')
            
            # Determinar nivel de urgencia
            if correos_fallidos > correos_encontrados * 0.7:
                nivel = "🔴 CRÍTICO"
                color = "red"
            elif correos_fallidos > correos_encontrados * 0.3:
                nivel = "🟡 ATENCIÓN"
                color = "orange"
            else:
                nivel = "🟢 NORMAL"
                color = "green"
            
            asunto = f"CRON Contadores {nivel} - {razon_notificacion}"
            
            cuerpo = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px;">
                <h3 style="color: {color};">{nivel} - Procesamiento Automático de Contadores</h3>
                
                <table style="border-collapse: collapse; width: 100%; margin: 15px 0;">
                    <tr style="background-color: #f5f5f5;">
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Fecha de ejecución:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{fecha_str}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Correos encontrados:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{resumen.get('correos_encontrados', 0)}</td>
                    </tr>
                    <tr style="background-color: #f5f5f5;">
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Procesados exitosamente:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd; color: green;"><strong>{resumen.get('correos_procesados', 0)}</strong></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Fallos:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd; color: {color};"><strong>{correos_fallidos}</strong></td>
                    </tr>
                    <tr style="background-color: #f5f5f5;">
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Período revisado:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{resumen.get('horas_revision', 24)} horas</td>
                    </tr>
                </table>
                
                {f'<div style="background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; margin: 15px 0; border-radius: 5px;"><strong>⚠️ Atención:</strong> Alta tasa de fallos ({correos_fallidos}/{correos_encontrados}). Revisar logs del sistema.</div>' if correos_fallidos > correos_encontrados * 0.3 else ''}
                
                <div style="margin: 20px 0; padding: 10px; background-color: #e8f5e8; border-radius: 5px;">
                    <small><em>📧 Notificación automática del sistema de procesamiento de contadores.<br>
                    Para revisar detalles, consulte los logs del sistema o el dashboard de contadores.</em></small>
                </div>
            </div>
            """
            
            # Enviar notificación a usuarios seleccionados
            notificaciones_enviadas = 0
            for usuario in usuarios_notificar:
                try:
                    # CORRECCIÓN: Usar método más confiable de notificación
                    self.env['mail.mail'].create({
                        'subject': asunto,
                        'body_html': cuerpo,
                        'email_to': usuario.email or usuario.partner_id.email,
                        'auto_delete': True,
                        'state': 'outgoing'
                    })
                    notificaciones_enviadas += 1
                    _logger.info(f"📧 Notificación enviada a {usuario.name} ({usuario.email})")
                    
                except Exception as e:
                    _logger.error(f"❌ Error enviando notificación a {usuario.name}: {e}")
                    
                    # Fallback: mensaje interno en Odoo
                    try:
                        self.env['mail.message'].create({
                            'subject': asunto,
                            'body': cuerpo,
                            'message_type': 'notification',
                            'partner_ids': [(4, usuario.partner_id.id)],
                            'needaction_partner_ids': [(4, usuario.partner_id.id)]
                        })
                        notificaciones_enviadas += 1
                        _logger.info(f"📧 Notificación interna enviada a {usuario.name}")
                    except Exception as e2:
                        _logger.error(f"❌ Error también en notificación interna: {e2}")
            
            if notificaciones_enviadas > 0:
                _logger.info(f"✅ Notificaciones CRON enviadas exitosamente a {notificaciones_enviadas} usuarios")
            else:
                _logger.error("❌ No se pudo enviar ninguna notificación")
            
        except Exception as e:
            _logger.error(f"❌ Error crítico enviando notificaciones CRON: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")

    @api.model
    def diagnosticar_sistema(self):
        """
        NUEVO: Diagnóstico completo del sistema para detectar problemas
        """
        try:
            _logger.info("🔬 === INICIANDO DIAGNÓSTICO DEL SISTEMA ===")
            
            diagnostico = {
                'fecha_diagnostico': fields.Datetime.now(),
                'estado_general': 'saludable',
                'problemas_encontrados': [],
                'recomendaciones': [],
                'estadisticas': {}
            }
            
            # 1. Verificar modelos requeridos
            _logger.info("🔍 Verificando modelos del sistema...")
            try:
                self.env['patron.contador'].search_count([])
                diagnostico['modelo_patrones'] = 'disponible'
            except:
                diagnostico['modelo_patrones'] = 'no_disponible'
                diagnostico['problemas_encontrados'].append("Modelo 'patron.contador' no disponible")
                diagnostico['estado_general'] = 'problemas_menores'
            
            try:
                self.env['alquiler'].search_count([])
                diagnostico['modelo_equipos'] = 'disponible'
            except:
                diagnostico['modelo_equipos'] = 'no_disponible'
                diagnostico['problemas_encontrados'].append("Modelo 'alquiler' no disponible")
                diagnostico['estado_general'] = 'problemas_criticos'
            
            # 2. Verificar canal de correos
            _logger.info("📧 Verificando canal de correos...")
            canal_correos = self.env['discuss.channel'].search([('name', 'ilike', 'correos')], limit=1)
            if canal_correos:
                diagnostico['canal_correos'] = 'encontrado'
                
                # Verificar mensajes recientes
                hace_24h = fields.Datetime.now() - timedelta(hours=24)
                mensajes_recientes = self.env['mail.message'].search_count([
                    ('model', '=', 'discuss.channel'),
                    ('res_id', '=', canal_correos.id),
                    ('date', '>=', hace_24h)
                ])
                diagnostico['mensajes_24h'] = mensajes_recientes
                
                if mensajes_recientes == 0:
                    diagnostico['problemas_encontrados'].append("No hay mensajes recientes en canal de correos")
                    diagnostico['recomendaciones'].append("Verificar configuración del canal de correos")
            else:
                diagnostico['canal_correos'] = 'no_encontrado'
                diagnostico['problemas_encontrados'].append("Canal 'correos' no encontrado")
                diagnostico['recomendaciones'].append("Crear canal 'correos' para recibir correos automáticos")
                diagnostico['estado_general'] = 'problemas_criticos'
            
            # 3. Analizar registros problemáticos
            _logger.info("📊 Analizando registros...")
            total_registros = self.env['contador.automatico'].search_count([])
            registros_error = self.env['contador.automatico'].search_count([('estado', '=', 'error')])
            registros_manual = self.env['contador.automatico'].search_count([('estado', '=', 'manual')])
            registros_procesados = self.env['contador.automatico'].search_count([('estado', '=', 'procesado')])
            
            diagnostico['estadisticas'].update({
                'total_registros': total_registros,
                'registros_error': registros_error,
                'registros_manual': registros_manual,
                'registros_procesados': registros_procesados,
                'tasa_exito': round((registros_procesados / total_registros * 100) if total_registros > 0 else 0, 1)
            })
            
            # Detectar problemas en tasas
            if total_registros > 10:
                tasa_error = registros_error / total_registros
                tasa_manual = registros_manual / total_registros
                
                if tasa_error > 0.2:  # Más del 20% en error
                    diagnostico['problemas_encontrados'].append(f"Alta tasa de errores: {tasa_error:.1%}")
                    diagnostico['recomendaciones'].append("Revisar logs para identificar errores recurrentes")
                    diagnostico['estado_general'] = 'problemas_menores'
                
                if tasa_manual > 0.5:  # Más del 50% requiere procesamiento manual
                    diagnostico['problemas_encontrados'].append(f"Alta tasa de procesamiento manual: {tasa_manual:.1%}")
                    diagnostico['recomendaciones'].append("Mejorar patrones automáticos o entrenar el sistema")
                    diagnostico['estado_general'] = 'problemas_menores'
            
            # 4. Verificar patrones
            if diagnostico['modelo_patrones'] == 'disponible':
                _logger.info("🎯 Analizando patrones...")
                try:
                    total_patrones = self.env['patron.contador'].search_count([('activo', '=', True)])
                    patrones_auto = self.env['patron.contador'].search_count([('auto_generado', '=', True), ('activo', '=', True)])
                    
                    diagnostico['estadisticas'].update({
                        'total_patrones_activos': total_patrones,
                        'patrones_auto_generados': patrones_auto
                    })
                    
                    if total_patrones < 5:
                        diagnostico['problemas_encontrados'].append("Pocos patrones activos disponibles")
                        diagnostico['recomendaciones'].append("Ejecutar creación de patrones por defecto")
                        
                except Exception as e:
                    _logger.error(f"Error analizando patrones: {e}")
            
            # 5. Determinar estado final
            if diagnostico['problemas_encontrados']:
                if any('criticos' in problema for problema in diagnostico['problemas_encontrados']):
                    diagnostico['estado_general'] = 'problemas_criticos'
                elif diagnostico['estado_general'] == 'saludable':
                    diagnostico['estado_general'] = 'problemas_menores'
            
            # 6. Generar recomendaciones automáticas
            if not diagnostico['recomendaciones']:
                diagnostico['recomendaciones'].append("Sistema funcionando correctamente")
            
            _logger.info(f"🔬 === DIAGNÓSTICO COMPLETADO ===")
            _logger.info(f"Estado general: {diagnostico['estado_general']}")
            _logger.info(f"Problemas encontrados: {len(diagnostico['problemas_encontrados'])}")
            _logger.info(f"Recomendaciones: {len(diagnostico['recomendaciones'])}")
            
            return diagnostico
            
        except Exception as e:
            _logger.error(f"❌ Error en diagnóstico del sistema: {e}")
            return {
                'fecha_diagnostico': fields.Datetime.now(),
                'estado_general': 'error_diagnostico',
                'error': str(e),
                'problemas_encontrados': [f"Error ejecutando diagnóstico: {str(e)}"],
                'recomendaciones': ["Contactar soporte técnico"]
            }

    def ejecutar_diagnostico_completo(self):
        """
        NUEVO: Método wrapper para ejecutar diagnóstico desde interfaz
        """
        try:
            diagnostico = self.diagnosticar_sistema()
            
            # Preparar mensaje para mostrar
            estado = diagnostico['estado_general']
            problemas = len(diagnostico.get('problemas_encontrados', []))
            
            if estado == 'saludable':
                mensaje = "✅ Sistema funcionando correctamente"
                tipo = 'success'
            elif estado == 'problemas_menores':
                mensaje = f"⚠️ Sistema funcional con {problemas} problemas menores detectados"
                tipo = 'warning'
            else:
                mensaje = f"❌ Sistema con {problemas} problemas críticos - requiere atención"
                tipo = 'danger'
            
            # Log detallado
            _logger.info(f"📋 Diagnóstico completado: {mensaje}")
            for problema in diagnostico.get('problemas_encontrados', []):
                _logger.info(f"  ⚠️ {problema}")
            for recomendacion in diagnostico.get('recomendaciones', []):
                _logger.info(f"  💡 {recomendacion}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': mensaje,
                    'type': tipo
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error ejecutando diagnóstico: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error en diagnóstico: {str(e)}',
                    'type': 'danger'
                }
            }

    def mostrar_resumen_estado(self):
        """
        NUEVO: Muestra un resumen rápido del estado del sistema
        """
        try:
            # Estadísticas rápidas
            total = self.env['contador.automatico'].search_count([])
            procesados = self.env['contador.automatico'].search_count([('estado', '=', 'procesado')])
            ultima_semana = self.env['contador.automatico'].search_count([
                ('create_date', '>=', fields.Date.today() - timedelta(days=7))
            ])
            
            tasa_exito = (procesados / total * 100) if total > 0 else 0
            
            # Mensaje de estado
            if tasa_exito >= 80:
                estado_emoji = "🟢"
                estado_texto = "Excelente"
            elif tasa_exito >= 60:
                estado_emoji = "🟡"
                estado_texto = "Bueno"
            else:
                estado_emoji = "🔴"
                estado_texto = "Requiere atención"
            
            mensaje = f"""
            {estado_emoji} Estado del Sistema: {estado_texto}
            
            📊 Estadísticas:
            • Total registros: {total}
            • Procesados exitosamente: {procesados} ({tasa_exito:.1f}%)
            • Actividad última semana: {ultima_semana} registros
            
            🔄 Para diagnóstico completo, use el botón "Diagnosticar Sistema"
            """
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': mensaje,
                    'type': 'info',
                    'sticky': True
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error obteniendo estado: {str(e)}',
                    'type': 'danger'
                }
            }


















    
class ContadorAutomaticoEstadisticas(models.Model):
        _name = 'contador.automatico.estadisticas'
        _description = 'Estadísticas diarias del procesamiento de contadores'
        _order = 'fecha desc'
        
        fecha = fields.Date('Fecha', required=True, default=fields.Date.today)
        correos_encontrados_cron = fields.Integer('Correos Encontrados por CRON', default=0)
        correos_procesados_cron = fields.Integer('Correos Procesados por CRON', default=0)
        correos_fallidos_cron = fields.Integer('Correos Fallidos por CRON', default=0)
        ejecuciones_cron = fields.Integer('Ejecuciones CRON', default=0)
        
        patrones_generados_dia = fields.Integer('Patrones Generados en el Día', default=0)
        registros_procesados_dia = fields.Integer('Registros Procesados en el Día', default=0)
        registros_manuales_dia = fields.Integer('Registros Manuales en el Día', default=0)
        
        @api.model
        def actualizar_estadisticas_diarias(self):
            '''Actualiza estadísticas del día actual'''
            hoy = fields.Date.today()
            
            estadisticas = self.search([('fecha', '=', hoy)], limit=1)
            if not estadisticas:
                estadisticas = self.create({'fecha': hoy})
            
            # Contar registros del día
            registros_hoy = self.env['contador.automatico'].search_count([
                ('create_date', '>=', hoy),
                ('create_date', '<', hoy + timedelta(days=1))
            ])
            
            registros_procesados = self.env['contador.automatico'].search_count([
                ('create_date', '>=', hoy),
                ('create_date', '<', hoy + timedelta(days=1)),
                ('estado', '=', 'procesado')
            ])
            
            registros_manuales = self.env['contador.automatico'].search_count([
                ('create_date', '>=', hoy),
                ('create_date', '<', hoy + timedelta(days=1)),
                ('estado', '=', 'manual')
            ])
            
            estadisticas.write({
                'registros_procesados_dia': registros_procesados,
                'registros_manuales_dia': registros_manuales
            })
            
            return estadisticas
    