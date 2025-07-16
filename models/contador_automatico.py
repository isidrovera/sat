# models/contador_automatico.py - PARTE 1

from odoo import models, fields, api
import logging
import re
import html
from html.parser import HTMLParser

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
    
    # Contadores detectados
    contador_bn_detectado = fields.Integer('Contador B/N detectado')
    contador_color_detectado = fields.Integer('Contador Color detectado')
    contador_scan_detectado = fields.Integer('Contador Scan detectado')
    
    # Control del proceso
    estado = fields.Selection([
        ('pendiente', 'Pendiente de procesar'),
        ('procesado', 'Procesado exitosamente'),
        ('error', 'Error en procesamiento'),
        ('manual', 'Requiere intervención manual')
    ], default='pendiente', tracking=True)
    
    fecha_procesamiento = fields.Datetime('Fecha de procesamiento')
    mensaje_error = fields.Text('Mensaje de error')
    procesado_automaticamente = fields.Boolean('Procesado automáticamente', default=False)
    
    # Valores anteriores del equipo
    contador_bn_anterior = fields.Integer('Contador B/N anterior')
    contador_color_anterior = fields.Integer('Contador Color anterior')
    contador_scan_anterior = fields.Integer('Contador Scan anterior')
    
    # Información de patrones utilizados
    patrones_usados = fields.Text('Patrones utilizados', readonly=True, 
                                 help="Registro de qué patrones se usaron para detectar datos")

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
            _logger.warning(f"⚠️ Usando contenido original como fallback")
            return str(html_content)

    def buscar_patrones_contadores_dinamico(self, texto):
        """
        Busca patrones de contadores usando configuración dinámica
        """
        contadores = {}
        patrones_usados = []
        
        _logger.info(f"🔍 Iniciando búsqueda de contadores con patrones dinámicos...")
        _logger.info(f"📄 Texto a analizar (primeros 200 chars): {texto[:200]}...")
        
        # Verificar si existen patrones configurados
        total_patrones = self.env['patron.contador'].search_count([('activo', '=', True)])
        _logger.info(f"📊 Total de patrones activos disponibles: {total_patrones}")
        
        if total_patrones == 0:
            _logger.warning(f"⚠️ No hay patrones activos configurados. Usando patrones por defecto...")
            return self._buscar_patrones_fallback(texto)
        
        # Buscar cada tipo de contador
        tipos = ['contador_bn', 'contador_color', 'contador_scan']
        
        for tipo in tipos:
            _logger.info(f"🔍 Buscando patrones para: {tipo}")
            
            resultado = self.env['patron.contador'].buscar_por_tipo(tipo, texto)
            
            if resultado:
                contadores[tipo] = resultado
                # Encontrar qué patrón se usó
                patron_usado = self._encontrar_patron_usado(tipo, texto, resultado)
                if patron_usado:
                    patrones_usados.append(f"{tipo}: {patron_usado.name}")
                    _logger.info(f"✅ {tipo} encontrado: {resultado} usando patrón '{patron_usado.name}'")
                else:
                    _logger.info(f"✅ {tipo} encontrado: {resultado}")
            else:
                _logger.info(f"❌ No se encontró {tipo} en el texto")
        
        # Guardar información de patrones usados
        if patrones_usados:
            self.patrones_usados = "; ".join(patrones_usados)
            _logger.info(f"📋 Patrones utilizados: {self.patrones_usados}")
        
        _logger.info(f"🎯 Resultado final de contadores: {contadores}")
        return contadores

    def buscar_serie_dinamico(self, texto):
        """
        Busca número de serie usando patrones dinámicos
        """
        _logger.info(f"🔍 Iniciando búsqueda de serie con patrones dinámicos...")
        
        # Verificar si existen patrones de serie
        patrones_serie = self.env['patron.contador'].search_count([
            ('tipo', '=', 'serie'),
            ('activo', '=', True)
        ])
        _logger.info(f"📊 Patrones de serie disponibles: {patrones_serie}")
        
        if patrones_serie == 0:
            _logger.warning(f"⚠️ No hay patrones de serie configurados. Usando patrones por defecto...")
            return self._buscar_serie_fallback(texto)
        
        resultado = self.env['patron.contador'].buscar_por_tipo('serie', texto)
        
        if resultado:
            # Encontrar qué patrón se usó
            patron_usado = self._encontrar_patron_usado('serie', texto, resultado)
            if patron_usado:
                patrones_info = f"serie: {patron_usado.name}"
                if self.patrones_usados:
                    self.patrones_usados += f"; {patrones_info}"
                else:
                    self.patrones_usados = patrones_info
                _logger.info(f"✅ Serie encontrada: {resultado} usando patrón '{patron_usado.name}'")
            else:
                _logger.info(f"✅ Serie encontrada: {resultado}")
            
            return resultado
        else:
            _logger.warning(f"❌ No se encontró serie en el texto")
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

    def _buscar_serie_fallback(self, texto):
        """
        Búsqueda de serie de fallback si no hay configuración dinámica
        """
        _logger.info(f"🔧 Usando patrones de serie de fallback...")
        
        patrones_serie = [
            r'\[Número de serie\].*?([A-Z0-9]{5,15})',
            r'([A-Z]{2,4}\d{5,10})',
            r'(?:serie|serial).*?([A-Z0-9]{5,15})'
        ]
        
        for patron in patrones_serie:
            matches = re.finditer(patron, texto, re.IGNORECASE)
            for match in matches:
                serie = match.group(1).upper()
                if len(serie) >= 5:
                    _logger.info(f"✅ Serie encontrada (fallback): {serie}")
                    return serie
        
        return None

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
                
                # Log información adicional del equipo
                try:
                    if hasattr(equipo, 'name'):
                        _logger.info(f"📋 Nombre del equipo: '{equipo.name}'")
                    if hasattr(equipo, 'state'):
                        _logger.info(f"📊 Estado del equipo: '{equipo.state}'")
                except:
                    pass
                
                return equipo
            else:
                _logger.warning(f"❌ No se encontró equipo con serie: '{serie}'")
                
                # Buscar equipos similares para sugerir
                try:
                    equipos_similares = self.env['alquiler'].search([
                        '|',
                        ('serie', 'ilike', f'%{serie[:5]}%'),
                        ('serie', 'ilike', f'%{serie[-5:]}%')
                    ], limit=3)
                    
                    if equipos_similares:
                        series_similares = [eq.serie for eq in equipos_similares]
                        _logger.info(f"💡 Series similares encontradas: {', '.join(series_similares)}")
                except:
                    pass
                
                return None
                
        except Exception as e:
            _logger.error(f"❌ Error buscando equipo: {e}")
            return None
    def procesar_correo_automaticamente(self):
        """
        Procesa automáticamente el correo para extraer contadores usando patrones dinámicos
        """
        try:
            _logger.info(f"🤖 === INICIO PROCESAMIENTO AUTOMÁTICO ===")
            _logger.info(f"📧 Registro ID={self.id}, Asunto='{self.name}'")
            
            # 1. Limpiar HTML si existe
            if self.contenido_original:
                _logger.info(f"📄 Procesando contenido HTML de {len(self.contenido_original)} caracteres")
                texto_limpio = self.limpiar_html_correo(self.contenido_original)
                self.contenido_procesado = texto_limpio
            else:
                _logger.info(f"📄 No hay contenido HTML, usando asunto como texto")
                texto_limpio = self.name or ""
            
            _logger.info(f"✅ Texto final para análisis: {len(texto_limpio)} caracteres")
            
            # 2. Buscar contadores usando patrones dinámicos
            _logger.info(f"📊 === FASE: DETECCIÓN DE CONTADORES ===")
            contadores_encontrados = self.buscar_patrones_contadores_dinamico(texto_limpio)
            
            # 3. Actualizar contadores detectados
            _logger.info(f"💾 Actualizando campos de contadores detectados...")
            if 'contador_bn' in contadores_encontrados:
                self.contador_bn_detectado = contadores_encontrados['contador_bn']
                _logger.info(f"✅ Contador BN actualizado: {self.contador_bn_detectado}")
            
            if 'contador_color' in contadores_encontrados:
                self.contador_color_detectado = contadores_encontrados['contador_color']
                _logger.info(f"✅ Contador Color actualizado: {self.contador_color_detectado}")
            
            if 'contador_scan' in contadores_encontrados:
                self.contador_scan_detectado = contadores_encontrados['contador_scan']
                _logger.info(f"✅ Contador Scan actualizado: {self.contador_scan_detectado}")
            
            # 4. Buscar serie usando patrones dinámicos
            _logger.info(f"🔍 === FASE: DETECCIÓN DE SERIE ===")
            serie_encontrada = self.buscar_serie_dinamico(texto_limpio)
            
            if serie_encontrada:
                self.serie_detectada = serie_encontrada
                _logger.info(f"✅ Serie detectada y guardada: '{serie_encontrada}'")
                
                # 5. Buscar equipo
                _logger.info(f"🔍 === FASE: BÚSQUEDA DE EQUIPO ===")
                equipo = self.buscar_equipo_por_serie(serie_encontrada)
                
                if equipo:
                    self.equipo_id = equipo.id
                    _logger.info(f"✅ Equipo asociado: ID={equipo.id}")
                    
                    # 6. Si encontramos contadores y equipo, actualizar automáticamente
                    if contadores_encontrados:
                        _logger.info(f"🚀 === FASE: ACTUALIZACIÓN DE EQUIPO ===")
                        self.actualizar_contadores_equipo(equipo, contadores_encontrados)
                        self.estado = 'procesado'
                        self.procesado_automaticamente = True
                        _logger.info(f"🎉 Procesamiento completado exitosamente")
                    else:
                        self.estado = 'manual'
                        self.mensaje_error = "Se encontró el equipo pero no se detectaron contadores válidos"
                        _logger.warning(f"⚠️ Equipo encontrado pero sin contadores: {self.mensaje_error}")
                else:
                    self.estado = 'manual'
                    self.mensaje_error = f"No se encontró equipo con serie: {serie_encontrada}"
                    _logger.warning(f"⚠️ Serie detectada pero equipo no encontrado: {self.mensaje_error}")
            else:
                self.estado = 'manual'
                self.mensaje_error = "No se detectó número de serie en el correo"
                _logger.warning(f"⚠️ No se detectó serie: {self.mensaje_error}")
            
            # Actualizar fecha de procesamiento
            self.fecha_procesamiento = fields.Datetime.now()
            
            _logger.info(f"📊 === RESUMEN FINAL ===")
            _logger.info(f"Estado final: {self.estado}")
            _logger.info(f"Serie detectada: {self.serie_detectada or 'No detectada'}")
            _logger.info(f"Equipo ID: {self.equipo_id.id if self.equipo_id else 'No encontrado'}")
            _logger.info(f"Contadores detectados: BN={self.contador_bn_detectado}, Color={self.contador_color_detectado}, Scan={self.contador_scan_detectado}")
            _logger.info(f"Procesado automáticamente: {self.procesado_automaticamente}")
            _logger.info(f"🏁 === FIN PROCESAMIENTO AUTOMÁTICO ===")
            
        except Exception as e:
            _logger.error(f"❌ === ERROR EN PROCESAMIENTO AUTOMÁTICO ===")
            _logger.error(f"Error: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            
            self.estado = 'error'
            self.mensaje_error = f"Error técnico: {str(e)}"
            self.fecha_procesamiento = fields.Datetime.now()
            
            _logger.error(f"💾 Estado cambiado a ERROR: {self.mensaje_error}")

    def actualizar_contadores_equipo(self, equipo, contadores):
        """
        Actualiza los contadores del equipo
        """
        try:
            _logger.info(f"💾 === INICIANDO ACTUALIZACIÓN DE EQUIPO ===")
            _logger.info(f"🎯 Equipo ID={equipo.id}, Serie={equipo.serie}")
            _logger.info(f"📊 Contadores a actualizar: {contadores}")
            
            # Backup de valores actuales
            self.contador_bn_anterior = getattr(equipo, 'contador_bn', 0) or 0
            self.contador_color_anterior = getattr(equipo, 'contador_color', 0) or 0
            self.contador_scan_anterior = getattr(equipo, 'contador_scan', 0) or 0
            
            _logger.info(f"📋 Valores actuales del equipo:")
            _logger.info(f"   - Contador BN anterior: {self.contador_bn_anterior}")
            _logger.info(f"   - Contador Color anterior: {self.contador_color_anterior}")
            _logger.info(f"   - Contador Scan anterior: {self.contador_scan_anterior}")
            
            # Preparar valores para actualizar
            valores_actualizacion = {}
            
            if 'contador_bn' in contadores:
                valores_actualizacion['contador_bn'] = contadores['contador_bn']
                _logger.info(f"✅ Preparando actualización BN: {self.contador_bn_anterior} → {contadores['contador_bn']}")
            
            if 'contador_color' in contadores:
                valores_actualizacion['contador_color'] = contadores['contador_color']
                _logger.info(f"✅ Preparando actualización Color: {self.contador_color_anterior} → {contadores['contador_color']}")
            
            if 'contador_scan' in contadores:
                valores_actualizacion['contador_scan'] = contadores['contador_scan']
                _logger.info(f"✅ Preparando actualización Scan: {self.contador_scan_anterior} → {contadores['contador_scan']}")
            
            # Agregar fecha de actualización
            fecha_actualizacion = fields.Datetime.now()
            valores_actualizacion['fecha_ultima_actualizacion'] = fecha_actualizacion
            _logger.info(f"⏰ Fecha de actualización: {fecha_actualizacion}")
            
            # Realizar actualización
            _logger.info(f"💾 Ejecutando write() en equipo...")
            equipo.sudo().write(valores_actualizacion)
            _logger.info(f"✅ Write() ejecutado exitosamente")
            
            # Crear mensaje en el equipo
            try:
                _logger.info(f"📝 Creando mensaje de seguimiento en equipo...")
                equipo.message_post(
                    body=f"""
                    <p><strong>Contadores actualizados automáticamente desde correo</strong></p>
                    <ul>
                        <li>Remitente: {self.remitente or 'No especificado'}</li>
                        <li>Asunto: {self.name}</li>
                        <li>Procesado: {fields.Datetime.now()}</li>
                        <li>Registro ID: {self.id}</li>
                    </ul>
                    <p><strong>Valores anteriores:</strong> BN={self.contador_bn_anterior}, Color={self.contador_color_anterior}, Scan={self.contador_scan_anterior}</p>
                    <p><strong>Valores nuevos:</strong> {', '.join([f'{k}={v}' for k, v in contadores.items()])}</p>
                    """,
                    subject="Actualización automática de contadores"
                )
                _logger.info(f"✅ Mensaje de seguimiento creado")
            except Exception as e:
                _logger.warning(f"⚠️ No se pudo crear mensaje de seguimiento: {e}")
            
            _logger.info(f"🎉 === ACTUALIZACIÓN DE EQUIPO COMPLETADA ===")
            
        except Exception as e:
            _logger.error(f"❌ === ERROR ACTUALIZANDO EQUIPO ===")
            _logger.error(f"Error: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    @api.model
    def crear_desde_correo(self, subject, body, email_from):
        """
        Crea un registro desde un correo y lo procesa automáticamente
        """
        try:
            _logger.info(f"📧 === CREANDO REGISTRO DESDE CORREO ===")
            _logger.info(f"Asunto: '{subject}'")
            _logger.info(f"Remitente: '{email_from}'")
            _logger.info(f"Tamaño del cuerpo: {len(body) if body else 0} caracteres")
            
            # Crear registro
            registro = self.create({
                'name': subject or 'Correo sin asunto',
                'remitente': email_from or 'Remitente desconocido',
                'contenido_original': body or '',
                'estado': 'pendiente'
            })
            
            _logger.info(f"✅ Registro creado con ID={registro.id}")
            
            # Procesar automáticamente
            _logger.info(f"🚀 Iniciando procesamiento automático...")
            registro.procesar_correo_automaticamente()
            
            _logger.info(f"🏁 Creación y procesamiento completado para ID={registro.id}")
            return registro
            
        except Exception as e:
            _logger.error(f"❌ Error creando registro desde correo: {e}")
            import traceback
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def reprocesar_manualmente(self):
        """
        Permite reprocesar un registro manualmente
        """
        _logger.info(f"🔄 === REPROCESAMIENTO MANUAL ===")
        _logger.info(f"Registro ID={self.id}, Estado actual='{self.estado}'")
        
        self.ensure_one()
        
        # Limpiar estado anterior
        self.estado = 'pendiente'
        self.mensaje_error = ''
        self.fecha_procesamiento = False
        self.procesado_automaticamente = False
        self.patrones_usados = ''
        
        _logger.info(f"🧹 Estado limpiado, iniciando reprocesamiento...")
        
        # Procesar de nuevo
        self.procesar_correo_automaticamente()
        
        _logger.info(f"✅ Reprocesamiento completado. Nuevo estado: '{self.estado}'")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Registro reprocesado. Estado: {self.estado}',
                'type': 'success' if self.estado == 'procesado' else 'info'
            }
        }

    def marcar_como_procesado_manual(self):
        """
        Marca el registro como procesado manualmente
        """
        _logger.info(f"✋ Marcando registro ID={self.id} como procesado manualmente")
        
        self.ensure_one()
        self.estado = 'procesado'
        self.procesado_automaticamente = False
        self.fecha_procesamiento = fields.Datetime.now()
        
        _logger.info(f"✅ Registro marcado como procesado manualmente")

    def buscar_y_procesar_correos(self):
        """
        Busca correos en el canal "Correos" y los registra como contadores
        VERSIÓN CORREGIDA - Mejor detección de correos nuevos
        """
        try:
            _logger.info("🔍 === INICIO BÚSQUEDA Y PROCESAMIENTO DE CORREOS ===")
            
            # Buscar canal "Correos" - Odoo 18 usa discuss.channel
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
            
            # Buscar mensajes en el canal - MEJORADO: ordenar por fecha desc y buscar más tipos
            _logger.info("📧 Buscando mensajes de correo en el canal...")
            mensajes = self.env['mail.message'].search([
                ('model', '=', 'discuss.channel'),
                ('res_id', '=', canal_correos.id),
                ('message_type', 'in', ['email', 'comment']),  # Incluir también comments
            ], order='date desc')  # Ordenar por fecha descendente
            
            _logger.info(f"📧 Total de mensajes encontrados: {len(mensajes)}")
            
            # MEJORADO: Obtener registros ya procesados usando una clave más robusta
            _logger.info("📋 Verificando mensajes ya procesados...")
            
            # Crear clave única combinando asunto y remitente
            registros_existentes = self.env['contador.automatico'].search([])
            claves_procesadas = set()
            
            for registro in registros_existentes:
                # Crear clave única: asunto + remitente
                clave = f"{registro.name}|{registro.remitente or ''}"
                claves_procesadas.add(clave)
                _logger.info(f"📋 Clave procesada: {clave}")
            
            _logger.info(f"📋 Total claves procesadas: {len(claves_procesadas)}")
            
            # Procesar mensajes nuevos
            correos_nuevos = 0
            mensajes_ignorados = 0
            
            for i, mensaje in enumerate(mensajes):
                asunto = mensaje.subject or f'Sin asunto - {mensaje.id}'
                remitente = mensaje.email_from or mensaje.author_id.email if mensaje.author_id else 'Desconocido'
                
                # Crear clave única para este mensaje
                clave_mensaje = f"{asunto}|{remitente}"
                
                _logger.info(f"📨 Procesando mensaje {i+1}/{len(mensajes)}")
                _logger.info(f"   📧 Asunto: '{asunto}'")
                _logger.info(f"   👤 Remitente: '{remitente}'")
                _logger.info(f"   🔑 Clave: '{clave_mensaje}'")
                _logger.info(f"   📅 Fecha: {mensaje.date}")
                _logger.info(f"   📝 Tipo: {mensaje.message_type}")
                
                # Verificar si es un mensaje válido para procesar
                if not asunto or asunto.strip() == '':
                    _logger.info(f"⏭️ Mensaje sin asunto válido, saltando...")
                    mensajes_ignorados += 1
                    continue
                
                # Filtros adicionales para evitar mensajes del sistema
                if mensaje.message_type == 'notification':
                    _logger.info(f"⏭️ Mensaje de notificación del sistema, saltando...")
                    mensajes_ignorados += 1
                    continue
                
                # Verificar si ya fue procesado
                if clave_mensaje in claves_procesadas:
                    _logger.info(f"⏭️ Mensaje ya procesado (clave existe), saltando...")
                    continue
                
                _logger.info(f"🆕 Mensaje nuevo detectado, creando registro...")
                
                try:
                    # Crear registro
                    registro = self.env['contador.automatico'].create({
                        'name': asunto,
                        'remitente': remitente,
                        'contenido_original': mensaje.body or '',
                        'estado': 'pendiente'
                    })
                    
                    _logger.info(f"✅ Registro creado con ID={registro.id}")
                    
                    # Agregar la clave a las procesadas para evitar duplicados en esta sesión
                    claves_procesadas.add(clave_mensaje)
                    
                    # Procesar automáticamente
                    _logger.info(f"🚀 Iniciando procesamiento automático para ID={registro.id}")
                    registro.procesar_correo_automaticamente()
                    
                    _logger.info(f"✅ Procesamiento completado para ID={registro.id}, Estado: {registro.estado}")
                    correos_nuevos += 1
                    
                except Exception as e:
                    _logger.error(f"❌ Error procesando mensaje {mensaje.id}: {e}")
                    continue
            
            # Preparar resultado
            if correos_nuevos > 0:
                mensaje_result = f'Se procesaron {correos_nuevos} correos nuevos'
                tipo = 'success'
            elif mensajes_ignorados > 0:
                mensaje_result = f'No hay correos nuevos para procesar. {mensajes_ignorados} mensajes ignorados (sin asunto válido o notificaciones del sistema)'
                tipo = 'info'
            else:
                mensaje_result = 'No hay correos nuevos para procesar'
                tipo = 'info'
            
            _logger.info(f"🎯 === RESULTADO FINAL ===")
            _logger.info(f"Total correos procesados: {correos_nuevos}")
            _logger.info(f"Total mensajes ignorados: {mensajes_ignorados}")
            _logger.info(f"Mensaje: {mensaje_result}")
            _logger.info(f"🏁 === FIN BÚSQUEDA Y PROCESAMIENTO ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': mensaje_result,
                    'type': tipo
                }
            }
                
        except Exception as e:
            _logger.error(f"❌ === ERROR EN BÚSQUEDA Y PROCESAMIENTO ===")
            _logger.error(f"Error: {e}")
            import traceback
            _logger.error(f"Traceback completo: {traceback.format_exc()}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error técnico: {str(e)}',
                    'type': 'danger'
                }
            }

    # MÉTODO ADICIONAL PARA DEBUG
    def debug_canal_correos(self):
        """
        Método de debug para inspeccionar el canal de correos
        """
        try:
            _logger.info("🔍 === DEBUG CANAL CORREOS ===")
            
            # Buscar canal
            canal_correos = self.env['discuss.channel'].search([
                ('name', 'ilike', 'correos')
            ], limit=1)
            
            if not canal_correos:
                _logger.warning("❌ No se encontró canal 'Correos'")
                return
            
            _logger.info(f"✅ Canal: '{canal_correos.name}' (ID: {canal_correos.id})")
            
            # Buscar TODOS los mensajes (sin filtros)
            todos_mensajes = self.env['mail.message'].search([
                ('model', '=', 'discuss.channel'),
                ('res_id', '=', canal_correos.id),
            ], order='date desc', limit=10)
            
            _logger.info(f"📧 Total mensajes en canal: {len(todos_mensajes)}")
            
            for i, msg in enumerate(todos_mensajes):
                _logger.info(f"📨 Mensaje {i+1}:")
                _logger.info(f"   ID: {msg.id}")
                _logger.info(f"   Asunto: '{msg.subject}'")
                _logger.info(f"   Tipo: {msg.message_type}")
                _logger.info(f"   Remitente: {msg.email_from}")
                _logger.info(f"   Autor: {msg.author_id.name if msg.author_id else 'Sin autor'}")
                _logger.info(f"   Fecha: {msg.date}")
                _logger.info(f"   Cuerpo (primeros 100 chars): {(msg.body or '')[:100]}...")
                _logger.info(f"   ---")
            
            # Verificar registros existentes
            registros = self.env['contador.automatico'].search([], order='create_date desc', limit=5)
            _logger.info(f"📋 Últimos registros procesados:")
            for reg in registros:
                _logger.info(f"   ID: {reg.id}, Asunto: '{reg.name}', Remitente: '{reg.remitente}', Estado: {reg.estado}")
            
            _logger.info("🏁 === FIN DEBUG ===")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Debug completado. Revisa los logs para detalles. Mensajes en canal: {len(todos_mensajes)}',
                    'type': 'info'
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error en debug: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error en debug: {str(e)}',
                    'type': 'danger'
                }
            }

    @api.model
    def inicializar_patrones_default(self):
        """
        Método para inicializar patrones por defecto desde la UI
        """
        try:
            _logger.info("🔧 === INICIALIZANDO PATRONES POR DEFECTO ===")
            
            # Verificar si ya existen patrones
            total_existentes = self.env['patron.contador'].search_count([])
            _logger.info(f"📊 Patrones existentes: {total_existentes}")
            
            if total_existentes > 0:
                _logger.info("⚠️ Ya existen patrones configurados")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'Ya existen {total_existentes} patrones configurados',
                        'type': 'info'
                    }
                }
            
            # Crear patrones por defecto
            self.env['patron.contador'].create_default_patterns()
            
            # Contar patrones creados
            total_creados = self.env['patron.contador'].search_count([])
            _logger.info(f"✅ Total patrones creados: {total_creados}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Se crearon {total_creados} patrones por defecto exitosamente',
                    'type': 'success'
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error inicializando patrones: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error: {str(e)}',
                    'type': 'danger'
                }
            }

    def action_test_patterns(self):
        """
        Acción para probar patrones con el contenido del registro actual
        """
        self.ensure_one()
        
        try:
            _logger.info(f"🧪 === PROBANDO PATRONES CON REGISTRO ID={self.id} ===")
            
            if not self.contenido_procesado:
                _logger.warning("⚠️ No hay contenido procesado disponible")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'No hay contenido procesado para probar patrones',
                        'type': 'warning'
                    }
                }
            
            texto = self.contenido_procesado
            _logger.info(f"📄 Texto a analizar: {len(texto)} caracteres")
            
            # Probar patrones de serie
            serie_resultado = self.env['patron.contador'].buscar_por_tipo('serie', texto)
            _logger.info(f"🔍 Resultado serie: {serie_resultado}")
            
            # Probar patrones de contadores
            bn_resultado = self.env['patron.contador'].buscar_por_tipo('contador_bn', texto)
            color_resultado = self.env['patron.contador'].buscar_por_tipo('contador_color', texto)
            scan_resultado = self.env['patron.contador'].buscar_por_tipo('contador_scan', texto)
            
            _logger.info(f"🔍 Resultado BN: {bn_resultado}")
            _logger.info(f"🔍 Resultado Color: {color_resultado}")
            _logger.info(f"🔍 Resultado Scan: {scan_resultado}")
            
            # Preparar mensaje de resultado
            resultados = []
            if serie_resultado:
                resultados.append(f"Serie: {serie_resultado}")
            if bn_resultado:
                resultados.append(f"BN: {bn_resultado}")
            if color_resultado:
                resultados.append(f"Color: {color_resultado}")
            if scan_resultado:
                resultados.append(f"Scan: {scan_resultado}")
            
            if resultados:
                mensaje = f"Patrones detectaron: {', '.join(resultados)}"
                tipo = 'success'
            else:
                mensaje = "Los patrones no detectaron ningún valor"
                tipo = 'warning'
            
            _logger.info(f"✅ Prueba completada: {mensaje}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': mensaje,
                    'type': tipo
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ Error probando patrones: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error: {str(e)}',
                    'type': 'danger'
                }
            }


