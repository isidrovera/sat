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
    
    def limpiar_html_correo(self, html_content):
        """
        Convierte HTML a texto plano y limpia el contenido
        """
        try:
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
            
            # Remover tags HTML
            stripper = MLStripper()
            stripper.feed(contenido)
            texto_limpio = stripper.get_data()
            
            # Limpiar espacios extra y saltos de línea
            texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()
            
            _logger.info(f"🧹 HTML convertido a texto: {len(texto_limpio)} caracteres")
            
            return texto_limpio
            
        except Exception as e:
            _logger.warning(f"⚠️ Error limpiando HTML: {e}")
            return str(html_content)

    def buscar_patrones_contadores(self, texto):
        """
        Busca patrones comunes de contadores en el texto
        """
        contadores = {}
        
        # Patrones comunes para contadores (más amplio que la API)
        patrones = {
            'contador_bn': [
                r'(?:contador|total|copies?)?\s*(?:b/?n|blanco?\s*y?\s*negro|black)\s*:?\s*(\d{1,9})',
                r'(?:impresiones?|copies?)\s*(?:b/?n|blanco)\s*:?\s*(\d{1,9})',
                r'b/?n\s*:?\s*(\d{1,9})',
                r'(?:mono|monocromatico)\s*:?\s*(\d{1,9})',
            ],
            'contador_color': [
                r'(?:contador|total|copies?)?\s*(?:color|col)\s*:?\s*(\d{1,9})',
                r'(?:impresiones?|copies?)\s*color\s*:?\s*(\d{1,9})',
                r'color\s*:?\s*(\d{1,9})',
                r'(?:full\s*color|a\s*color)\s*:?\s*(\d{1,9})',
            ],
            'contador_scan': [
                r'(?:contador|total)?\s*(?:scan|escaner|digitalizacion)\s*:?\s*(\d{1,9})',
                r'(?:escaneos?|scans?)\s*:?\s*(\d{1,9})',
                r'scan\s*:?\s*(\d{1,9})',
                r'(?:digitalizacion|digitalización)\s*:?\s*(\d{1,9})',
            ]
        }
        
        _logger.info(f"🔍 Buscando contadores en texto: {texto[:200]}...")
        
        for tipo_contador, lista_patrones in patrones.items():
            for patron in lista_patrones:
                matches = re.finditer(patron, texto, re.IGNORECASE)
                for match in matches:
                    numero = int(match.group(1))
                    if numero > 0:  # Solo números positivos
                        contadores[tipo_contador] = numero
                        _logger.info(f"✅ {tipo_contador} encontrado: {numero} (patrón: {patron})")
                        break
            
            if tipo_contador in contadores:
                continue  # Si ya encontramos este tipo, pasar al siguiente
        
        return contadores

    def buscar_serie_en_texto(self, texto):
        """
        Busca número de serie en el texto del correo
        """
        # Patrones comunes para números de serie
        patrones_serie = [
            r'(?:serie|serial|s/?n)\s*:?\s*([A-Z0-9]{5,15})',
            r'(?:equipo|printer|impresora)\s*:?\s*([A-Z0-9]{5,15})',
            r'(?:modelo|model)\s*:?\s*([A-Z0-9]{5,15})',
            r'([A-Z]{2,4}\d{5,10})',  # Formato como AB12345678
            r'(\d{4}[A-Z]{2}\d{5})',  # Formato como 1234AB56789
        ]
        
        _logger.info(f"🔍 Buscando serie en texto...")
        
        for patron in patrones_serie:
            matches = re.finditer(patron, texto, re.IGNORECASE)
            for match in matches:
                serie_candidata = match.group(1).upper()
                # Validar que la serie tenga sentido
                if len(serie_candidata) >= 5 and re.match(r'^[A-Z0-9]+$', serie_candidata):
                    _logger.info(f"📋 Serie encontrada en texto: {serie_candidata}")
                    return serie_candidata
        
        return None

    def buscar_equipo_por_serie(self, serie):
        """
        Busca el equipo en alquiler por serie
        """
        if not serie:
            return None
            
        equipo = self.env['alquiler'].search([('serie', '=', serie)], limit=1)
        
        if equipo:
            _logger.info(f"✅ Equipo encontrado: ID={equipo.id}, Serie={serie}")
            return equipo
        else:
            _logger.warning(f"⚠️ No se encontró equipo con serie: {serie}")
            return None

    def procesar_correo_automaticamente(self):
        """
        Procesa automáticamente el correo para extraer contadores
        """
        try:
            _logger.info(f"🤖 Iniciando procesamiento automático del registro ID={self.id}")
            
            # 1. Limpiar HTML si existe
            if self.contenido_original:
                texto_limpio = self.limpiar_html_correo(self.contenido_original)
                self.contenido_procesado = texto_limpio
            else:
                texto_limpio = self.name or ""  # Usar asunto si no hay contenido
            
            # 2. Buscar contadores
            contadores_encontrados = self.buscar_patrones_contadores(texto_limpio)
            
            # 3. Actualizar contadores detectados
            if 'contador_bn' in contadores_encontrados:
                self.contador_bn_detectado = contadores_encontrados['contador_bn']
            if 'contador_color' in contadores_encontrados:
                self.contador_color_detectado = contadores_encontrados['contador_color']
            if 'contador_scan' in contadores_encontrados:
                self.contador_scan_detectado = contadores_encontrados['contador_scan']
            
            # 4. Buscar serie
            serie_encontrada = self.buscar_serie_en_texto(texto_limpio)
            if serie_encontrada:
                self.serie_detectada = serie_encontrada
                
                # 5. Buscar equipo
                equipo = self.buscar_equipo_por_serie(serie_encontrada)
                if equipo:
                    self.equipo_id = equipo.id
                    
                    # 6. Si encontramos contadores y equipo, actualizar automáticamente
                    if contadores_encontrados:
                        self.actualizar_contadores_equipo(equipo, contadores_encontrados)
                    else:
                        self.estado = 'manual'
                        self.mensaje_error = "Se encontró el equipo pero no se detectaron contadores válidos"
                else:
                    self.estado = 'manual'
                    self.mensaje_error = f"No se encontró equipo con serie: {serie_encontrada}"
            else:
                self.estado = 'manual'
                self.mensaje_error = "No se detectó número de serie en el correo"
            
            self.fecha_procesamiento = fields.Datetime.now()
            
            if self.estado == 'pendiente':  # Si no se cambió a manual o error
                self.estado = 'procesado'
                self.procesado_automaticamente = True
            
            _logger.info(f"✅ Procesamiento completado. Estado: {self.estado}")
            
        except Exception as e:
            _logger.error(f"❌ Error en procesamiento automático: {e}")
            self.estado = 'error'
            self.mensaje_error = f"Error técnico: {str(e)}"
            self.fecha_procesamiento = fields.Datetime.now()

    def actualizar_contadores_equipo(self, equipo, contadores):
        """
        Actualiza los contadores del equipo
        """
        try:
            _logger.info(f"💾 Actualizando contadores del equipo ID={equipo.id}")
            
            # Backup de valores actuales
            self.contador_bn_anterior = getattr(equipo, 'contador_bn', 0) or 0
            self.contador_color_anterior = getattr(equipo, 'contador_color', 0) or 0
            self.contador_scan_anterior = getattr(equipo, 'contador_scan', 0) or 0
            
            # Preparar valores para actualizar
            valores_actualizacion = {}
            
            if 'contador_bn' in contadores:
                valores_actualizacion['contador_bn'] = contadores['contador_bn']
            if 'contador_color' in contadores:
                valores_actualizacion['contador_color'] = contadores['contador_color']
            if 'contador_scan' in contadores:
                valores_actualizacion['contador_scan'] = contadores['contador_scan']
            
            # Agregar fecha de actualización
            valores_actualizacion['fecha_ultima_actualizacion'] = fields.Datetime.now()
            
            # Realizar actualización
            equipo.sudo().write(valores_actualizacion)
            
            # Log de éxito
            _logger.info(f"✅ Contadores actualizados exitosamente:")
            _logger.info(f"   Anteriores: BN={self.contador_bn_anterior}, Color={self.contador_color_anterior}, Scan={self.contador_scan_anterior}")
            _logger.info(f"   Nuevos: {valores_actualizacion}")
            
            # Crear mensaje en el equipo
            equipo.message_post(
                body=f"""
                <p><strong>Contadores actualizados automáticamente desde correo</strong></p>
                <ul>
                    <li>Remitente: {self.remitente or 'No especificado'}</li>
                    <li>Asunto: {self.name}</li>
                    <li>Procesado: {fields.Datetime.now()}</li>
                </ul>
                """,
                subject="Actualización automática de contadores"
            )
            
        except Exception as e:
            _logger.error(f"❌ Error actualizando contadores: {e}")
            raise

    @api.model
    def crear_desde_correo(self, subject, body, email_from):
        """
        Crea un registro desde un correo y lo procesa automáticamente
        """
        try:
            _logger.info(f"📧 Creando registro desde correo: {subject}")
            
            # Crear registro
            registro = self.create({
                'name': subject or 'Correo sin asunto',
                'remitente': email_from or 'Remitente desconocido',
                'contenido_original': body or '',
                'estado': 'pendiente'
            })
            
            # Procesar automáticamente
            registro.procesar_correo_automaticamente()
            
            return registro
            
        except Exception as e:
            _logger.error(f"❌ Error creando registro desde correo: {e}")
            return None

    def reprocesar_manualmente(self):
        """
        Permite reprocesar un registro manualmente
        """
        self.ensure_one()
        self.estado = 'pendiente'
        self.mensaje_error = ''
        self.fecha_procesamiento = False
        self.procesado_automaticamente = False
        self.procesar_correo_automaticamente()

    @api.model
    def buscar_y_procesar_correos(self):
        """
        Busca correos en el canal "Correos" y los registra como contadores
        """
        try:
            _logger.info("🔍 Buscando correos en canal 'Correos'...")
            
            # Buscar canal "Correos"
            canal_correos = self.env['mail.channel'].search([
                ('name', 'ilike', 'correos')
            ], limit=1)
            
            if not canal_correos:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'No se encontró el canal "Correos"',
                        'type': 'warning'
                    }
                }
            
            # Buscar mensajes en el canal
            mensajes = self.env['mail.message'].search([
                ('model', '=', 'mail.channel'),
                ('res_id', '=', canal_correos.id),
                ('message_type', '=', 'email')
            ])
            
            # Obtener asuntos ya procesados
            asuntos_procesados = self.search([]).mapped('name')
            
            correos_nuevos = 0
            for mensaje in mensajes:
                asunto = mensaje.subject or 'Sin asunto'
                if asunto not in asuntos_procesados:
                    # Crear registro
                    registro = self.create({
                        'name': asunto,
                        'remitente': mensaje.email_from or 'Desconocido',
                        'contenido_original': mensaje.body or '',
                        'estado': 'pendiente'
                    })
                    # Procesar automáticamente
                    registro.procesar_correo_automaticamente()
                    correos_nuevos += 1
            
            mensaje = f'Se procesaron {correos_nuevos} correos nuevos' if correos_nuevos > 0 else 'No hay correos nuevos'
            tipo = 'success' if correos_nuevos > 0 else 'info'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': mensaje,
                    'type': tipo
                }
            }
                
        except Exception as e:
            _logger.error(f"❌ Error procesando correos: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'Error: {str(e)}',
                    'type': 'danger'
                }
            }

    def marcar_como_procesado_manual(self):
        """
        Marca el registro como procesado manualmente
        """
        self.ensure_one()
        self.estado = 'procesado'
        self.procesado_automaticamente = False
        self.fecha_procesamiento = fields.Datetime.now()


# models/mail_thread_inherit.py

class MailThreadInherit(models.AbstractModel):
    _inherit = 'mail.thread'
    
    @api.model
    def message_process(self, model, message, custom_values=None, save_original=False, strip_attachments=False, thread_id=None):
        """
        Intercepta correos que llegan al canal "Correos" para procesamiento automático
        """
        result = super().message_process(
            model, message, custom_values, save_original, strip_attachments, thread_id
        )
        
        try:
            # Solo procesar si es un canal específico
            if model == 'mail.channel' and thread_id:
                canal = self.env['mail.channel'].browse(thread_id)
                
                # Verificar si es el canal "Correos" (puedes cambiar el nombre)
                if canal.name and 'correos' in canal.name.lower():
                    _logger.info(f"📧 Correo detectado en canal de contadores: {canal.name}")
                    
                    # Extraer información del mensaje
                    import email
                    msg = email.message_from_bytes(message)
                    
                    subject = msg.get('Subject', 'Sin asunto')
                    email_from = msg.get('From', 'Remitente desconocido')
                    
                    # Obtener cuerpo del mensaje
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                break
                            elif part.get_content_type() == "text/html":
                                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    else:
                        body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                    
                    # Crear y procesar registro automáticamente
                    self.env['contador.automatico'].crear_desde_correo(subject, body, email_from)
                    
        except Exception as e:
            _logger.error(f"❌ Error en procesamiento automático de correo: {e}")
            # No fallar el procesamiento normal del correo
        
        return result
