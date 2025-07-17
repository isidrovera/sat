from odoo import models, fields, api
import logging
import re
import html
from html.parser import HTMLParser
from datetime import timedelta

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
        # Fecha en que se completa el procesamiento (añadido)
    fecha_procesamiento = fields.Datetime('Fecha de procesamiento', readonly=True)

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
    patrones_aplicados = fields.Text('Patrones Aplicados', readonly=True)
    
    
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
                'Bizhub': ['bizhub', 'konica', 'minolta', 'nombre del modelo'],  # Agregar "nombre del modelo"
                'Ricoh': ['ricoh', 'T_TotalPrtPGS', 'T_ColorPrtPGS', 'nº de serie'],  # Agregar "nº de serie"
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

    
    # NUEVOS CAMPOS PARA AGREGAR AL MODELO (después de los campos existentes):
    idioma_detectado = fields.Char('Idioma Detectado', readonly=True)
    formato_detectado = fields.Char('Formato Detectado', readonly=True) 
    confianza_deteccion = fields.Float('Confianza de Detección (%)', readonly=True)
    requiere_aprendizaje = fields.Boolean('Requiere Aprendizaje', default=False)
    estructura_detectada = fields.Text('Estructura Detectada', readonly=True)
    marca_detectada = fields.Char('Marca Detectada', readonly=True)
    palabras_clave_encontradas = fields.Text('Palabras Clave Encontradas', readonly=True)
    patrones_auto_generados = fields.Integer('Patrones Auto-generados', default=0, readonly=True)
    aprendizaje_completado = fields.Boolean('Aprendizaje Completado', default=False)

    # ACTUALIZAR EL CAMPO ESTADO EXISTENTE:
    estado = fields.Selection([
        ('pendiente', 'Pendiente de procesar'),
        ('procesado', 'Procesado exitosamente'),
        ('error', 'Error en procesamiento'),
        ('manual', 'Requiere intervención manual'),
        ('filtrado', 'Filtrado - No es correo de contadores')
    ], default='pendiente', tracking=True)

    def es_correo_de_contadores(self, asunto):
        """
        Filtro: Correos que CONTENGAN palabras clave de contadores
        """
        if not asunto:
            _logger.info("❌ Sin asunto - No es correo de contadores")
            return False
            
        asunto_lower = asunto.lower().strip()
        
        # Palabras clave que SI indican correos de contadores
        # Si el asunto CONTIENE cualquiera de estas, es válido
        palabras_validas = [
            'counter list',            
            'counter',
            'page counter', 
            'page count',
            'contador',
            'contadores',
            'ricoh'
        ]
        
        # Verificar si CONTIENE alguna palabra clave
        for palabra in palabras_validas:
            if palabra in asunto_lower:
                _logger.info(f"✅ Asunto válido detectado: '{asunto}' contiene '{palabra}'")
                return True
        
        _logger.info(f"❌ Asunto no válido para contadores: '{asunto}'")
        return False

    
    
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
            self.patrones_aplicados = f"Auto-generados: {patrones_creados} patrones"
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

            # 2) Entre corchetes solo si la etiqueta es “Serial Number” o “Número de serie”
            series_corchetes = re.findall(
                r'\[(?:Serial Number|Número de serie)\][^A-Z0-9]*([A-Z0-9]{5,15})',
                texto, re.IGNORECASE
            )
            if series_corchetes:
                _logger.info(f"🔍 Series en corchetes: {series_corchetes}")
                posibles_series.extend(series_corchetes)

            # 3) Tras dos puntos con “serial” o “serie”
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
        """
        try:
            _logger.info(f"📊 === GENERANDO PATRONES DE CONTADORES ===")
            
            patrones_contadores = []
            
            # Buscar números que parezcan contadores (4-9 dígitos)
            numeros_contador = re.findall(r'\d{4,9}', texto)
            _logger.info(f"🔢 Números de contador encontrados: {numeros_contador}")
            
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
            
            palabras_idioma = palabras_contador.get(idioma, palabras_contador.get('english', {}))
            
            # Generar patrones para cada tipo de contador
            for tipo_contador, palabras in palabras_idioma.items():
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
                'activo': True
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
                'activo': True
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

    def procesar_correo_inteligente(self):
        """
        Procesamiento inteligente del correo con análisis y generación automática
        """
        try:
            _logger.info(f"🧠 === INICIO PROCESAMIENTO INTELIGENTE ===")
            _logger.info(f"📧 Registro ID={self.id}, Asunto='{self.name}'")

            # 1. VERIFICAR SI ES CORREO DE CONTADORES
            if not self.es_correo_de_contadores(self.name):
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
            # Descartar si la “serie” es solo dígitos
            if serie_encontrada and serie_encontrada.isdigit():
                _logger.warning(f"💥 Serie descartada tras validación: '{serie_encontrada}'")
                serie_encontrada = None

            contadores_encontrados = self.buscar_patrones_contadores_dinamico(texto_limpio)

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

                if serie_encontrada:
                    self.serie_detectada = serie_encontrada

                    # Actualizar contadores detectados
                    if 'contador_bn' in contadores_encontrados:
                        self.contador_bn_detectado = contadores_encontrados['contador_bn']
                    if 'contador_color' in contadores_encontrados:
                        self.contador_color_detectado = contadores_encontrados['contador_color']
                    if 'contador_scan' in contadores_encontrados:
                        self.contador_scan_detectado = contadores_encontrados['contador_scan']

                    # Buscar equipo y actualizar
                    equipo = self.buscar_equipo_por_serie(serie_encontrada)
                    if equipo and contadores_encontrados:
                        self.equipo_id = equipo.id
                        self.actualizar_contadores_equipo(equipo, contadores_encontrados)
                        self.estado = 'procesado'
                        self.procesado_automaticamente = True
                    else:
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
            # también usar write() aquí si quieres persistir fecha de error:
            self.write({'fecha_procesamiento': fields.Datetime.now()})
            return False

    def buscar_y_procesar_correos_inteligente(self):
        """
        Versión inteligente de búsqueda y procesamiento de correos
        """
        try:
            _logger.info("🧠 === INICIO BÚSQUEDA Y PROCESAMIENTO INTELIGENTE ===")
            
            # Buscar canal "Correos"
            _logger.info("🔍 Buscando canal 'Correos'...")
            canal_correos = self.env['discuss.channel'].search([
                ('name', 'ilike', 'correos')
            ], limit=1)
            
            if not canal_correos:
                _logger.warning("❌ No se encontró canal 'Correos'")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'No se encontró el canal "Correos"',
                        'type': 'warning'
                    }
                }
            
            _logger.info(f"✅ Canal encontrado: '{canal_correos.name}' (ID: {canal_correos.id})")
            
            # Buscar mensajes en el canal
            _logger.info("📧 Buscando mensajes de correo en el canal...")
            mensajes = self.env['mail.message'].search([
                ('model', '=', 'discuss.channel'),
                ('res_id', '=', canal_correos.id),
                ('message_type', 'in', ['email', 'comment']),
            ], order='date desc')
            
            _logger.info(f"📧 Total de mensajes encontrados: {len(mensajes)}")
            
            # Obtener registros ya procesados
            registros_existentes = self.env['contador.automatico'].search([])
            claves_procesadas = set()
            
            for registro in registros_existentes:
                clave = f"{registro.name}|{registro.remitente or ''}"
                claves_procesadas.add(clave)
            
            _logger.info(f"📋 Total claves procesadas: {len(claves_procesadas)}")
            
            # Procesar mensajes con sistema inteligente
            correos_procesados = 0
            correos_filtrados = 0
            correos_ignorados = 0
            correos_aprendizaje = 0
            
            for i, mensaje in enumerate(mensajes):
                asunto = mensaje.subject or f'Sin asunto - {mensaje.id}'
                remitente = mensaje.email_from or mensaje.author_id.email if mensaje.author_id else 'Desconocido'
                clave_mensaje = f"{asunto}|{remitente}"
                
                _logger.info(f"📨 Analizando mensaje {i+1}/{len(mensajes)}: '{asunto}'")
                
                # FILTRO INTELIGENTE 1: Verificar si es correo de contadores
                dummy_registro = self.env['contador.automatico'].new()
                if not dummy_registro.es_correo_de_contadores(asunto):
                    correos_filtrados += 1
                    _logger.info(f"🚫 Correo filtrado - No es de contadores")
                    continue
                
                # FILTRO 2: Verificar si ya fue procesado
                if clave_mensaje in claves_procesadas:
                    _logger.info(f"⏭️ Correo ya procesado")
                    continue
                
                # FILTRO 3: Validaciones básicas
                if not asunto or asunto.strip() == '':
                    correos_ignorados += 1
                    continue
                
                if mensaje.message_type == 'notification':
                    correos_ignorados += 1
                    continue
                
                # CREAR Y PROCESAR REGISTRO CON SISTEMA INTELIGENTE
                _logger.info(f"🧠 Creando registro inteligente...")
                
                try:
                    registro = self.env['contador.automatico'].create({
                        'name': asunto,
                        'remitente': remitente,
                        'contenido_original': mensaje.body or '',
                        'estado': 'pendiente'
                    })
                    
                    _logger.info(f"✅ Registro creado con ID={registro.id}")
                    claves_procesadas.add(clave_mensaje)
                    
                    # Procesar con sistema inteligente
                    _logger.info(f"🧠 Iniciando procesamiento inteligente...")
                    if registro.procesar_correo_inteligente():
                        correos_procesados += 1
                        if registro.requiere_aprendizaje:
                            correos_aprendizaje += 1
                        _logger.info(f"✅ Procesamiento inteligente completado")
                    else:
                        _logger.warning(f"⚠️ Procesamiento inteligente con problemas")
                    
                except Exception as e:
                    _logger.error(f"❌ Error procesando mensaje {mensaje.id}: {e}")
                    continue
            
            # Preparar resultado
            mensaje_result = f"Procesamiento inteligente completado: {correos_procesados} procesados, {correos_filtrados} filtrados, {correos_ignorados} ignorados"
            if correos_aprendizaje > 0:
                mensaje_result += f", {correos_aprendizaje} con aprendizaje automático"
            
            tipo = 'success' if correos_procesados > 0 else 'info'
            
            _logger.info(f"🎯 === RESULTADO FINAL INTELIGENTE ===")
            _logger.info(f"Correos procesados: {correos_procesados}")
            _logger.info(f"Correos filtrados: {correos_filtrados}")
            _logger.info(f"Correos ignorados: {correos_ignorados}")
            _logger.info(f"Correos con aprendizaje: {correos_aprendizaje}")
            _logger.info(f"🏁 === FIN PROCESAMIENTO INTELIGENTE ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': mensaje_result,
                    'type': tipo
                }
            }
                
        except Exception as e:
            _logger.error(f"❌ Error en procesamiento inteligente: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error técnico: {str(e)}',
                    'type': 'danger'
                }
            }

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
                    'activo': True
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
                    'activo': True
                }
                
                return self._crear_patron_si_no_existe(patron_data)
            
            return False
            
        except Exception as e:
            _logger.error(f"❌ Error aprendiendo patrón de contador: {e}")
            return False
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
            fecha_limite_stats = fields.Date.today() - timedelta(days=30)
            stats_antiguas = self.env['contador.automatico.estadisticas'].search([
                ('fecha', '<', fecha_limite_stats)
            ])
            
            if stats_antiguas:
                stats_antiguas.unlink()
                _logger.info(f"🗑️ Eliminadas {len(stats_antiguas)} estadísticas antiguas")
            
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

    # MÉTODOS DE PRUEBA Y DEBUG PARA SISTEMA INTELIGENTE
    def test_sistema_inteligente(self):
        """
        Método de prueba para el sistema inteligente
        """
        try:
            _logger.info("🧪 === PROBANDO SISTEMA INTELIGENTE ===")
            
            # Probar filtro de asuntos
            asuntos_prueba = [
                "Counter List",  # Válido
                "Page Counter",  # Válido
                "Error Alert",   # No válido
                "counter list",  # Válido (case insensitive)
                "Maintenance Required"  # No válido
            ]
            
            for asunto in asuntos_prueba:
                resultado = self.es_correo_de_contadores(asunto)
                _logger.info(f"📧 '{asunto}' → {'✅ VÁLIDO' if resultado else '❌ FILTRADO'}")
            
            # Probar detección de idioma
            textos_prueba = {
                'bizhub_es': "[Número de serie], A5C4011011874 [Contador total],00268741",
                'ricoh_en': "Serial No: 3359PB02667 T_TotalPrtPGS:36089",
                'generico': "Model XYZ123 Pages: 15000 Date: 2025-01-01"
            }
            
            for nombre, texto in textos_prueba.items():
                idioma, confianza, palabras = self.detectar_idioma_automatico(texto)
                _logger.info(f"🌍 {nombre} → {idioma} ({confianza:.1f}%)")
            
            # Probar detección de marca
            for nombre, texto in textos_prueba.items():
                marca = self.detectar_marca_automatico(texto)
                _logger.info(f"🏭 {nombre} → Marca: {marca}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Prueba del sistema inteligente completada. Revisa logs.',
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
        """
        try:
            _logger.info(f"🎯 === GENERANDO PATRONES PARA CORREO ACTUAL ===")
            _logger.info(f"📧 Registro ID={self.id}")
            
            if not self.contenido_procesado:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'No hay contenido procesado para generar patrones',
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
            if self.generar_patrones_automaticamente():
                mensaje = f"✅ Patrones generados exitosamente para este correo. {self.patrones_auto_generados} patrones creados."
                tipo = 'success'
            else:
                mensaje = "⚠️ No se pudieron generar patrones para este correo"
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
    def cron_procesar_correos_perdidos(self):
        """
        CRON SIMPLE: Solo procesar correos que NO existen en la BD
        """
        try:
            _logger.info("⏰ === INICIO CRON SIMPLE - SOLO CORREOS NO EXISTENTES ===")
            
            from datetime import datetime, time
            ahora = fields.Datetime.now()
            
            # Buscar correos de las últimas 24 horas (ventana fija)
            fecha_limite = ahora - timedelta(hours=24)
            
            _logger.info(f"🔍 Buscando correos de las últimas 24 horas desde: {fecha_limite}")
            _logger.info(f"⏰ Hora actual: {ahora}")
            
            # Buscar canal "Correos"
            canal_correos = self.env['discuss.channel'].search([
                ('name', 'ilike', 'correos')
            ], limit=1)
            
            if not canal_correos:
                _logger.warning("❌ CRON: No se encontró canal 'Correos'")
                return False
            
            _logger.info(f"✅ CRON: Canal encontrado: '{canal_correos.name}' (ID: {canal_correos.id})")
            
            # Buscar TODOS los mensajes de las últimas 24 horas
            mensajes_canal = self.env['mail.message'].search([
                ('model', '=', 'discuss.channel'),
                ('res_id', '=', canal_correos.id),
                ('message_type', 'in', ['email', 'comment']),
                ('date', '>=', fecha_limite)
            ], order='date desc')
            
            _logger.info(f"📧 CRON: Total mensajes en canal (últimas 24h): {len(mensajes_canal)}")
            
            # Obtener TODAS las claves de correos ya existentes en la BD
            registros_existentes = self.env['contador.automatico'].search([])
            claves_existentes = set()
            
            for registro in registros_existentes:
                clave = f"{registro.name}|{registro.remitente or ''}"
                claves_existentes.add(clave)
            
            _logger.info(f"📋 CRON: Total claves existentes en BD: {len(claves_existentes)}")
            
            # Filtrar mensajes para encontrar solo los NO EXISTENTES
            mensajes_nuevos = []
            correos_filtrados = 0
            
            for mensaje in mensajes_canal:
                asunto = mensaje.subject or f'Sin asunto - {mensaje.id}'
                remitente = mensaje.email_from or mensaje.author_id.email if mensaje.author_id else 'Desconocido'
                clave_mensaje = f"{asunto}|{remitente}"
                
                # Solo procesar si es correo de contadores Y no existe
                if self._es_correo_de_contadores_mejorado(asunto):
                    if clave_mensaje not in claves_existentes:
                        mensajes_nuevos.append(mensaje)
                        _logger.info(f"🆕 NUEVO correo encontrado: '{asunto}' - Fecha: {mensaje.date}")
                    else:
                        _logger.info(f"⏭️ Ya existe: '{asunto}'")
                else:
                    correos_filtrados += 1
            
            _logger.info(f"📧 CRON: Mensajes REALMENTE NUEVOS (no existen en BD): {len(mensajes_nuevos)}")
            _logger.info(f"🚫 CRON: Correos filtrados (no son de contadores): {correos_filtrados}")
            
            if not mensajes_nuevos:
                _logger.info("ℹ️ CRON: No hay correos REALMENTE NUEVOS para procesar")
                # Guardar estadísticas vacías
                self._guardar_estadisticas_cron_seguro({
                    'fecha_ejecucion': ahora,
                    'correos_analizados': len(mensajes_canal),
                    'correos_validos': 0,
                    'correos_encontrados': 0,
                    'correos_procesados': 0,
                    'correos_fallidos': 0,
                    'horas_revision': 24
                })
                return True
            
            # PROCESAR SOLO LOS MENSAJES REALMENTE NUEVOS
            correos_analizados = len(mensajes_canal)
            correos_validos = len(mensajes_nuevos)
            correos_procesados_exitosos = 0
            correos_fallidos = 0
            
            for i, mensaje in enumerate(mensajes_nuevos):
                asunto = mensaje.subject or f'Sin asunto - {mensaje.id}'
                remitente = mensaje.email_from or mensaje.author_id.email if mensaje.author_id else 'Desconocido'
                fecha_mensaje = mensaje.date
                
                _logger.info(f"📨 CRON: === PROCESANDO CORREO NUEVO {i+1}/{len(mensajes_nuevos)} ===")
                _logger.info(f"📧 Asunto: '{asunto}'")
                _logger.info(f"⏰ Fecha mensaje: {fecha_mensaje}")
                _logger.info(f"👤 Remitente: '{remitente}'")
                
                # CREAR Y PROCESAR REGISTRO NUEVO
                try:
                    _logger.info(f"🆕 CRON: Creando registro para correo NUEVO...")
                    
                    registro = self.env['contador.automatico'].create({
                        'name': asunto,
                        'remitente': remitente,
                        'contenido_original': mensaje.body or '',
                        'estado': 'pendiente'
                    })
                    
                    _logger.info(f"✅ CRON: Registro creado con ID={registro.id}")
                    
                    # Procesar con sistema inteligente
                    _logger.info(f"🧠 CRON: Iniciando procesamiento inteligente...")
                    
                    if registro.procesar_correo_inteligente():
                        correos_procesados_exitosos += 1
                        _logger.info(f"🎉 CRON: ¡PROCESADO EXITOSAMENTE!")
                        _logger.info(f"📝 Estado final: {registro.estado}")
                        _logger.info(f"🎯 Serie detectada: {registro.serie_detectada}")
                        
                        # Log de contadores detectados
                        contadores_info = []
                        if registro.contador_bn_detectado:
                            contadores_info.append(f"BN={registro.contador_bn_detectado}")
                        if registro.contador_color_detectado:
                            contadores_info.append(f"Color={registro.contador_color_detectado}")
                        if registro.contador_scan_detectado:
                            contadores_info.append(f"Scan={registro.contador_scan_detectado}")
                        
                        if contadores_info:
                            _logger.info(f"📊 Contadores: {', '.join(contadores_info)}")
                        
                        if registro.equipo_id:
                            _logger.info(f"🎯 Equipo actualizado: ID={registro.equipo_id.id}")
                        
                        # Asegurar que fecha_procesamiento esté configurada
                        if not registro.fecha_procesamiento:
                            registro.write({'fecha_procesamiento': ahora})
                            _logger.info(f"📅 Fecha de procesamiento actualizada")
                        
                    else:
                        _logger.warning(f"⚠️ CRON: Procesamiento con problemas")
                        _logger.warning(f"Estado: {registro.estado}")
                        if registro.mensaje_error:
                            _logger.warning(f"Error: {registro.mensaje_error}")
                        
                        # Asegurar fecha incluso en casos problemáticos
                        if not registro.fecha_procesamiento:
                            registro.write({'fecha_procesamiento': ahora})
                    
                except Exception as e:
                    correos_fallidos += 1
                    _logger.error(f"❌ CRON: Error procesando correo '{asunto}': {e}")
                    import traceback
                    _logger.error(f"Traceback: {traceback.format_exc()}")
                    continue
            
            # RESUMEN FINAL
            _logger.info(f"📊 === RESUMEN PROCESAMIENTO SIMPLE ===")
            _logger.info(f"📧 Total mensajes analizados (últimas 24h): {correos_analizados}")
            _logger.info(f"✅ Correos nuevos válidos encontrados: {correos_validos}")
            _logger.info(f"🎉 Correos procesados exitosamente: {correos_procesados_exitosos}")
            _logger.info(f"❌ Correos con fallos: {correos_fallidos}")
            _logger.info(f"🚫 Correos filtrados (no contadores): {correos_filtrados}")
            
            if correos_validos > 0:
                eficiencia = (correos_procesados_exitosos / correos_validos) * 100
                _logger.info(f"📈 Eficiencia: {eficiencia:.1f}%")
            
            if correos_procesados_exitosos > 0:
                _logger.info(f"🎉 ¡SE PROCESARON {correos_procesados_exitosos} CORREOS NUEVOS!")
            elif correos_validos == 0:
                _logger.info(f"ℹ️ No había correos de contadores nuevos en las últimas 24h")
            else:
                _logger.warning(f"⚠️ Se encontraron {correos_validos} correos válidos pero no se procesaron exitosamente")
            
            # Guardar estadísticas
            resumen = {
                'fecha_ejecucion': ahora,
                'correos_analizados': correos_analizados,
                'correos_validos': correos_validos,
                'correos_encontrados': correos_validos,
                'correos_procesados': correos_procesados_exitosos,
                'correos_fallidos': correos_fallidos,
                'horas_revision': 24
            }
            
            self._guardar_estadisticas_cron_seguro(resumen)
            
            _logger.info("⏰ === FIN CRON SIMPLE - SOLO CORREOS NO EXISTENTES ===")
            return True
            
        except Exception as e:
            _logger.error(f"❌ === ERROR CRÍTICO EN CRON SIMPLE ===")
            _logger.error(f"Error: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    def _es_correo_de_contadores_mejorado(self, asunto):
            """
            SOLUCIÓN: Función mejorada de filtrado de correos
            """
            if not asunto:
                return False
                
            asunto_lower = asunto.lower().strip()
            
            # TODAS en minúsculas para coincidencia exacta
            palabras_validas = [
                'counter list',
                'counter page',
                'counter',
                'page counter', 
                'page count',
                'contador',
                'contadores',
                'ricoh'
            ]
            
            for palabra in palabras_validas:
                if palabra in asunto_lower:
                    _logger.info(f"✅ CRON: Asunto válido detectado: '{asunto}' contiene '{palabra}'")
                    return True
            
            _logger.info(f"❌ CRON: Asunto no válido para contadores: '{asunto}'")
            return False

    def _guardar_estadisticas_cron_seguro(self, resumen):
        """
        SOLUCIÓN: Guardar estadísticas de forma segura
        """
        try:
            hoy = fields.Date.today()
            estadisticas = self.env['contador.automatico.estadisticas'].search([
                ('fecha', '=', hoy)
            ], limit=1)
            
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
    def _guardar_estadisticas_cron(self, resumen):
        """
        Guarda estadísticas de ejecución del CRON
        """
        try:
            # Buscar o crear registro de estadísticas de hoy
            hoy = fields.Date.today()
            estadisticas = self.env['contador.automatico.estadisticas'].search([
                ('fecha', '=', hoy)
            ], limit=1)
            
            if not estadisticas:
                estadisticas = self.env['contador.automatico.estadisticas'].create({
                    'fecha': hoy,
                    'correos_encontrados_cron': resumen['correos_encontrados'],
                    'correos_procesados_cron': resumen['correos_procesados'],
                    'correos_fallidos_cron': resumen['correos_fallidos'],
                    'ejecuciones_cron': 1
                })
            else:
                estadisticas.write({
                    'correos_encontrados_cron': estadisticas.correos_encontrados_cron + resumen['correos_encontrados'],
                    'correos_procesados_cron': estadisticas.correos_procesados_cron + resumen['correos_procesados'],
                    'correos_fallidos_cron': estadisticas.correos_fallidos_cron + resumen['correos_fallidos'],
                    'ejecuciones_cron': estadisticas.ejecuciones_cron + 1
                })
            
            _logger.info(f"📊 Estadísticas CRON guardadas para {hoy}")
            
        except Exception as e:
            _logger.error(f"❌ Error guardando estadísticas CRON: {e}")

    def _enviar_notificacion_cron(self, resumen):
        """
        Envía notificación sobre la ejecución del CRON
        """
        try:
            # Solo notificar si hay correos encontrados o fallos
            if resumen['correos_encontrados'] == 0 and resumen['correos_fallidos'] == 0:
                return
            
            # Buscar usuarios administradores o grupo específico
            try:
                grupo_admin = self.env.ref('base.group_system')
                usuarios_notificar = grupo_admin.users
            except:
                # Fallback: buscar usuario admin
                usuarios_notificar = self.env['res.users'].search([('login', '=', 'admin')], limit=1)
            
            if not usuarios_notificar:
                _logger.warning("⚠️ No se encontraron usuarios para notificar")
                return
            
            # Preparar mensaje
            asunto = f"CRON Contadores - {resumen['correos_encontrados']} correos perdidos procesados"
            
            if resumen['correos_fallidos'] > 0:
                asunto += f" ({resumen['correos_fallidos']} fallos)"
            
            cuerpo = f"""
            <h3>Resumen de ejecución CRON - Procesamiento de Contadores</h3>
            <p><strong>Fecha:</strong> {resumen['fecha_ejecucion']}</p>
            <ul>
                <li><strong>Correos perdidos encontrados:</strong> {resumen['correos_encontrados']}</li>
                <li><strong>Correos procesados exitosamente:</strong> {resumen['correos_procesados']}</li>
                <li><strong>Correos con fallos:</strong> {resumen['correos_fallidos']}</li>
                <li><strong>Período revisado:</strong> {resumen['horas_revision']} horas</li>
            </ul>
            
            {f'<p style="color: orange;"><strong>⚠️ Atención:</strong> {resumen["correos_fallidos"]} correos fallaron al procesarse. Revisa los logs para más detalles.</p>' if resumen['correos_fallidos'] > 0 else ''}
            
            <p><em>Este es un mensaje automático del sistema de procesamiento de contadores.</em></p>
            """
            
            # Enviar mensaje interno en Odoo
            for usuario in usuarios_notificar:
                try:
                    self.env['mail.message'].create({
                        'subject': asunto,
                        'body': cuerpo,
                        'message_type': 'notification',
                        'partner_ids': [(4, usuario.partner_id.id)],
                        'needaction_partner_ids': [(4, usuario.partner_id.id)]
                    })
                except Exception as e:
                    _logger.error(f"❌ Error enviando notificación a {usuario.name}: {e}")
            
            _logger.info(f"📧 Notificaciones CRON enviadas a {len(usuarios_notificar)} usuarios")
            
        except Exception as e:
            _logger.error(f"❌ Error enviando notificaciones CRON: {e}")

    @api.model
    def obtener_estadisticas_dashboard(self):
        """
        Obtiene estadísticas para dashboard de monitoreo
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
            
            # Estadísticas por marca
            marcas_detectadas = self.env['contador.automatico'].read_group(
                [('marca_detectada', '!=', False)],
                ['marca_detectada'],
                ['marca_detectada']
            )
            
            # Estadísticas por idioma
            idiomas_detectados = self.env['contador.automatico'].read_group(
                [('idioma_detectado', '!=', False)],
                ['idioma_detectado'],
                ['idioma_detectado']
            )
            
            # Patrones activos
            total_patrones_activos = self.env['patron.contador'].search_count([
                ('activo', '=', True)
            ])
            
            patrones_auto_generados = self.env['patron.contador'].search_count([
                ('activo', '=', True),
                ('name', 'ilike', 'auto-generado')
            ])
            
            # Estadísticas CRON (si existen)
            try:
                estadisticas_cron = self.env['contador.automatico.estadisticas'].search([
                    ('fecha', '>=', hace_7_dias)
                ])
                total_cron_encontrados = sum(est.correos_encontrados_cron for est in estadisticas_cron)
                total_cron_procesados = sum(est.correos_procesados_cron for est in estadisticas_cron)
            except:
                total_cron_encontrados = 0
                total_cron_procesados = 0
            
            estadisticas = {
                'resumen_general': {
                    'total_registros': total_registros,
                    'procesados': registros_procesados,
                    'manual': registros_manual,
                    'error': registros_error,
                    'filtrados': registros_filtrados,
                    'ultima_semana': registros_ultima_semana
                },
                'aprendizaje_automatico': {
                    'requiere_aprendizaje': registros_con_aprendizaje,
                    'aprendizaje_completado': registros_aprendizaje_completado,
                    'patrones_generados_total': suma_patrones
                },
                'patrones': {
                    'total_activos': total_patrones_activos,
                    'auto_generados': patrones_auto_generados
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
                    'correos_procesados_7_dias': total_cron_procesados
                }
            }
            
            _logger.info("✅ Estadísticas dashboard generadas exitosamente")
            return estadisticas
            
        except Exception as e:
            _logger.error(f"❌ Error generando estadísticas dashboard: {e}")
            return {}

    def optimizar_patrones_automaticamente(self):
        """
        Optimiza automáticamente los patrones basado en estadísticas de uso
        """
        try:
            _logger.info("🔧 === OPTIMIZANDO PATRONES AUTOMÁTICAMENTE ===")
            
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
                
                # Si el patrón tiene muy baja efectividad, desactivarlo
                if tasa_exito < 20 and patron.veces_usado > 5:
                    patron.write({'activo': False})
                    patrones_desactivados += 1
                    _logger.info(f"⏸️ Patrón desactivado por baja efectividad: {patron.name} ({tasa_exito:.1f}%)")
                
                # Si el patrón nunca se usa, marcarlo para revisión
                elif patron.veces_usado == 0 and patron.create_date < (fields.Datetime.now() - timedelta(days=7)):
                    # Patrón no usado en 7 días, reducir prioridad
                    if patron.orden < 50:
                        patron.write({'orden': patron.orden + 10})
                        patrones_optimizados += 1
                        _logger.info(f"📉 Reducida prioridad de patrón no usado: {patron.name}")
            
            # Buscar patrones muy exitosos para darles mayor prioridad
            patrones_exitosos = self.env['patron.contador'].search([
                ('activo', '=', True),
                ('veces_usado', '>', 10)
            ])
            
            for patron in patrones_exitosos:
                if hasattr(patron, 'casos_detectados') and hasattr(patron, 'casos_fallidos'):
                    total_casos = patron.casos_detectados + patron.casos_fallidos
                    if total_casos > 0:
                        tasa_exito = (patron.casos_detectados / total_casos) * 100
                        
                        # Si tiene alta efectividad, darle mayor prioridad
                        if tasa_exito > 90 and patron.orden > 3:
                            patron.write({'orden': max(1, patron.orden - 2)})
                            patrones_optimizados += 1
                            _logger.info(f"📈 Aumentada prioridad de patrón exitoso: {patron.name} ({tasa_exito:.1f}%)")
            
            _logger.info(f"✅ Optimización completada: {patrones_optimizados} optimizados, {patrones_desactivados} desactivados")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Optimización completada: {patrones_optimizados} patrones optimizados, {patrones_desactivados} desactivados',
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
        """
        try:
            _logger.info(f"📋 === GENERANDO REPORTE DE ACTIVIDAD ({dias} días) ===")
            
            fecha_inicio = fields.Date.today() - timedelta(days=dias)
            
            # Registros por día
            registros_por_dia = self.env['contador.automatico'].read_group(
                [('create_date', '>=', fecha_inicio)],
                ['create_date:day', 'estado'],
                ['create_date:day', 'estado'],
                lazy=False
            )
            
            # Procesamiento por estado
            estados_resumen = self.env['contador.automatico'].read_group(
                [('create_date', '>=', fecha_inicio)],
                ['estado'],
                ['estado']
            )
            
            # Marcas más procesadas
            marcas_resumen = self.env['contador.automatico'].read_group(
                [
                    ('create_date', '>=', fecha_inicio),
                    ('marca_detectada', '!=', False)
                ],
                ['marca_detectada'],
                ['marca_detectada']
            )
            
            # Patrones más usados
            patrones_mas_usados = self.env['patron.contador'].search([
                ('veces_usado', '>', 0)
            ], order='veces_usado desc', limit=10)
            
            reporte = {
                'periodo': f"Últimos {dias} días",
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fields.Date.today(),
                'registros_por_dia': registros_por_dia,
                'resumen_estados': estados_resumen,
                'marcas_procesadas': marcas_resumen,
                'patrones_top': [
                    {
                        'nombre': p.name,
                        'tipo': p.tipo,
                        'veces_usado': p.veces_usado,
                        'ultima_deteccion': p.ultima_deteccion
                    }
                    for p in patrones_mas_usados
                ]
            }
            
            _logger.info("✅ Reporte de actividad generado")
            return reporte
            
        except Exception as e:
            _logger.error(f"❌ Error generando reporte: {e}")
            return {}

    def limpiar_registros_antiguos(self, dias_mantener=90):
        """
        Limpia registros antiguos para mantener la BD optimizada
        """
        try:
            _logger.info(f"🧹 === LIMPIANDO REGISTROS ANTIGUOS (>{dias_mantener} días) ===")
            
            fecha_limite = fields.Date.today() - timedelta(days=dias_mantener)
            
            # Buscar registros antiguos filtrados o con error
            registros_limpiar = self.env['contador.automatico'].search([
                '|',
                ('estado', 'in', ['filtrado', 'error']),
                ('create_date', '<', fecha_limite)
            ])
            
            if not registros_limpiar:
                _logger.info("ℹ️ No hay registros antiguos para limpiar")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'No hay registros antiguos para limpiar',
                        'type': 'info'
                    }
                }
            
            cantidad_eliminar = len(registros_limpiar)
            
            # Crear backup de información importante antes de eliminar
            registros_importantes = registros_limpiar.filtered(
                lambda r: r.estado == 'procesado' and r.equipo_id
            )
            
            # Solo eliminar registros no importantes
            registros_eliminar = registros_limpiar.filtered(
                lambda r: r.estado in ['filtrado', 'error'] or not r.equipo_id
            )
            
            if registros_eliminar:
                registros_eliminar.unlink()
                _logger.info(f"🗑️ Eliminados {len(registros_eliminar)} registros antiguos")
            
            if registros_importantes:
                _logger.info(f"💾 Conservados {len(registros_importantes)} registros importantes")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Limpieza completada: {len(registros_eliminar)} registros eliminados, {len(registros_importantes)} conservados',
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

    # MÉTODO PRINCIPAL PARA MANTENIMIENTO AUTOMÁTICO
    @api.model
    def mantenimiento_automatico_sistema(self):
        """
        Ejecuta mantenimiento automático completo del sistema
        """
        try:
            _logger.info("🔧 === INICIO MANTENIMIENTO AUTOMÁTICO SISTEMA ===")
            
            # 1. Procesar correos perdidos
            _logger.info("📧 Ejecutando procesamiento de correos perdidos...")
            self.cron_procesar_correos_perdidos()
            
            # 2. Optimizar patrones
            _logger.info("⚙️ Ejecutando optimización de patrones...")
            dummy_registro = self.env['contador.automatico'].browse(1)
            if dummy_registro.exists():
                dummy_registro.optimizar_patrones_automaticamente()
            
            # 3. Limpiar registros antiguos (solo una vez por semana)
            hoy = fields.Date.today()
            if hoy.weekday() == 6:  # Domingo
                _logger.info("🧹 Ejecutando limpieza semanal...")
                if dummy_registro.exists():
                    dummy_registro.limpiar_registros_antiguos()
            
            _logger.info("✅ Mantenimiento automático completado exitosamente")
            return True
            
        except Exception as e:
            _logger.error(f"❌ Error en mantenimiento automático: {e}")
            return False
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
        🔧 Fallback con soporte para español, inglés y Ricoh
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
            r'(?:serie|serial)\s*(?:no\.?)?\s*:?\s*([A-Z0-9]{5,15})'  # Genérico
        ]
        
        for pat in patrones:
            _logger.info(f"🔍 Probando fallback: '{pat}'")
            for match in re.finditer(pat, texto, re.IGNORECASE):
                serie = match.group(1).upper()
                if len(serie) >= 5:
                    _logger.info(f"✅ Serie encontrada con fallback '{pat}': {serie}")
                    return serie
        return None


    def buscar_patrones_contadores_dinamico(self, texto):
        """
        🔍 Busca patrones de contadores usando configuración dinámica,
        con fallback tipo‑a‑tipo si no encuentra nada.
        """
        contadores = {}
        patrones_usados = []

        _logger.info("🔍 Iniciando búsqueda de contadores con patrones dinámicos...")
        _logger.info(f"📄 Texto a analizar (primeros 200 chars): {texto[:200]}...")

        # Verificar si existen patrones configurados
        total_patrones = self.env['patron.contador'].search_count([('activo', '=', True)])
        _logger.info(f"📊 Total de patrones activos disponibles: {total_patrones}")

        # Tipos de contador a buscar
        tipos = ['contador_bn', 'contador_color', 'contador_scan']

        # Fallback regexs específicas para etiquetas en inglés
        fallback_por_tipo = {
            'contador_bn': [
                # INGLÉS
                r'\[Total Black Counter\][^0-9]*(\d{4,9})',
                r'(?:black|b\/w).*?(\d{4,9})',
                
                # ESPAÑOL 
                r'\[Contador de negro total\][^0-9]*(\d{4,9})',     # [Contador de negro total],00183098
                r'\[Contador negro total\][^0-9]*(\d{4,9})',        # Variante sin "de"
                r'Contador de negro[^0-9]*(\d{4,9})',               # Sin corchetes
                r'Contador negro[^0-9]*(\d{4,9})',                  # Sin corchetes, sin "de"
                
                # RICOH
                r'T_TotalPrtPGS:\s*(\d{4,9})',                      # RICOH: Total páginas
                r'T_MonoPrtPGS:\s*(\d{4,9})'                        # RICOH: Páginas mono
            ],
            
            'contador_color': [
                # INGLÉS
                r'\[Total Color Counter\][^0-9]*(\d{4,9})',
                r'(?:color|colour).*?(\d{4,9})',
                
                # ESPAÑOL
                r'\[Contador de color total\][^0-9]*(\d{4,9})',     # [Contador de color total],00085643
                r'\[Contador color total\][^0-9]*(\d{4,9})',        # Variante sin "de"
                r'Contador de color[^0-9]*(\d{4,9})',               # Sin corchetes
                r'Contador color[^0-9]*(\d{4,9})',                  # Sin corchetes, sin "de"
                
                # RICOH
                r'T_ColorPrtPGS:\s*(\d{4,9})'                       # RICOH: Páginas color
            ],
            
            'contador_scan': [
                # INGLÉS
                r'\[Total Scan\/Fax Counter\][^0-9]*(\d{4,9})',
                r'(?:scan|fax|copy).*?(\d{4,9})',
                
                # ESPAÑOL
                r'\[Contador total de escaneo\/fax\][^0-9]*(\d{4,9})',  # [Contador total de escaneo/fax],00066775
                r'\[Contador de escaneo total\][^0-9]*(\d{4,9})',       # Variante
                r'\[Contador escaneo total\][^0-9]*(\d{4,9})',          # Sin "de"
                r'Contador.*escaneo[^0-9]*(\d{4,9})',                   # Genérico escaneo
                r'Contador.*fax[^0-9]*(\d{4,9})',                       # Genérico fax
                
                # RICOH (normalmente no envía scan separado)
                r'T_ScanPGS:\s*(\d{4,9})'                               # RICOH: Páginas scan (raro)
            ],
        }

        for tipo in tipos:
            _logger.info(f"🔍 Buscando patrones para: {tipo}")
            # 1) Intento con patrones dinámicos
            resultado = self.env['patron.contador'].buscar_por_tipo(tipo, texto)
            if resultado:
                contadores[tipo] = resultado
                patron_usado = self._encontrar_patron_usado(tipo, texto, resultado)
                if patron_usado:
                    patrones_usados.append(f"{tipo}: {patron_usado.name}")
                    _logger.info(f"✅ {tipo} encontrado: {resultado} usando patrón '{patron_usado.name}'")
                else:
                    _logger.info(f"✅ {tipo} encontrado: {resultado}")
                continue

            # 2) Fallback específico si no hay detección dinámica
            _logger.warning(f"❌ No se encontró {tipo} con patrones dinámicos, intentando fallback...")
            for pat in fallback_por_tipo[tipo]:
                for match in re.finditer(pat, texto, re.IGNORECASE):
                    raw = match.group(1)
                    numero = int(re.sub(r'[^0-9]', '', raw))
                    if numero > 0:
                        contadores[tipo] = numero
                        patrones_usados.append(f"{tipo}: fallback '{pat}'")
                        _logger.info(f"✅ {tipo} encontrado por fallback: {numero} usando patrón '{pat}'")
                        break
                if tipo in contadores:
                    break
            if tipo not in contadores:
                _logger.info(f"❌ No se encontró {tipo} incluso en fallback")

        # Guardamos el detalle de qué patrones se usaron
        if patrones_usados:
            self.patrones_usados = "; ".join(patrones_usados)
            _logger.info(f"📋 Patrones utilizados: {self.patrones_usados}")

        _logger.info(f"🎯 Resultado final de contadores: {contadores}")
        return contadores


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

    def _buscar_patrones_fallback(self, texto):
        """
        Patrones de fallback si no hay configuración dinámica
        """
        _logger.info(f"🔧 Usando patrones de fallback...")
        contadores = {}
        
        # Patrones básicos de fallback
        patrones = {
            'contador_bn': [
                r'(?:negro|black|b/?n).*?(\d{5,9})',
                r'\[Contador de negro total\].*?(\d{5,9})'
            ],
            'contador_color': [
                r'(?:color).*?(\d{5,9})',
                r'\[Contador de color total\].*?(\d{5,9})'
            ],
            'contador_scan': [
                r'(?:scan|escaneo).*?(\d{5,9})',
                r'\[Contador total de escaneo\].*?(\d{5,9})'
            ]
        }
        
        for tipo, lista_patrones in patrones.items():
            for patron in lista_patrones:
                matches = re.finditer(patron, texto, re.IGNORECASE)
                for match in matches:
                    numero = int(re.sub(r'[^0-9]', '', match.group(1)))
                    if numero > 0:
                        contadores[tipo] = numero
                        _logger.info(f"✅ {tipo} encontrado (fallback): {numero}")
                        break
        
        return contadores

    

    def buscar_equipo_por_serie(self, serie):
        """
        Busca el equipo en alquiler por serie
        """
        if not serie:
            _logger.warning(f"⚠️ No se proporcionó serie para buscar equipo")
            return None
        
        _logger.info(f"🔍 Buscando equipo con serie: '{serie}'")
        
        try:
            equipo = self.env['alquiler'].search([('serie', '=', serie)], limit=1)
            
            if equipo:
                _logger.info(f"✅ Equipo encontrado: ID={equipo.id}, Serie={serie}")
                return equipo
            else:
                _logger.warning(f"❌ No se encontró equipo con serie: '{serie}'")
                return None
                
        except Exception as e:
            _logger.error(f"❌ Error buscando equipo: {e}")
            return None

    def actualizar_contadores_equipo(self, equipo, contadores):
        """
        Actualiza los contadores del equipo
        """
        try:
            _logger.info(f"💾 === INICIANDO ACTUALIZACIÓN DE EQUIPO ===")
            _logger.info(f"🎯 Equipo ID={equipo.id}, Serie={equipo.serie}")
            _logger.info(f"📊 Contadores a actualizar: {contadores}")
            
            # Preparar valores para actualizar
            valores_actualizacion = {}
            
            if 'contador_bn' in contadores:
                valores_actualizacion['contador_bn'] = contadores['contador_bn']
                _logger.info(f"✅ Preparando actualización BN: → {contadores['contador_bn']}")
            
            if 'contador_color' in contadores:
                valores_actualizacion['contador_color'] = contadores['contador_color']
                _logger.info(f"✅ Preparando actualización Color: → {contadores['contador_color']}")
            
            if 'contador_scan' in contadores:
                valores_actualizacion['contador_scan'] = contadores['contador_scan']
                _logger.info(f"✅ Preparando actualización Scan: → {contadores['contador_scan']}")
            
            # Realizar actualización
            _logger.info(f"💾 Ejecutando write() en equipo...")
            equipo.sudo().write(valores_actualizacion)
            _logger.info(f"✅ Write() ejecutado exitosamente")
            
            _logger.info(f"🎉 === ACTUALIZACIÓN DE EQUIPO COMPLETADA ===")
            
        except Exception as e:
            _logger.error(f"❌ === ERROR ACTUALIZANDO EQUIPO ===")
            _logger.error(f"Error: {e}")
            raise

    # Agregar el campo patrones_usados si no existe
    patrones_usados = fields.Text('Patrones utilizados', readonly=True, 
                                help="Registro de qué patrones se usaron para detectar datos")

    
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
    