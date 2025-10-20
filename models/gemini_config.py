# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

# ===== IMPORTAR GEMINI CON MANEJO DE ERRORES =====
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    _logger.warning("google-generativeai no está instalado. Instala con: pip install google-generativeai")


class GeminiConfiguracion(models.Model):
    _name = 'gemini.configuracion'
    _description = 'Configuración de Google Gemini API'
    _inherit = ['mail.thread', 'mail.activity.mixin']  # Para el chatter
    
    # ========================================
    # CAMPOS
    # ========================================
    name = fields.Char(
        string='Nombre', 
        default='Configuración Gemini', 
        required=True,
        tracking=True
    )
    
    api_key = fields.Char(
        string='API Key de Gemini', 
        required=True,
        tracking=True,
        help='Obtén tu API key en https://makersuite.google.com/app/apikey'
    )
    
    modelo = fields.Selection([
        ('gemini-1.5-flash', 'Gemini 1.5 Flash (Recomendado - Rápido y gratuito)'),
        ('gemini-1.5-pro', 'Gemini 1.5 Pro (Más potente pero más lento)'),
    ], string='Modelo', 
       default='gemini-1.5-flash', 
       required=True,
       tracking=True
    )
    
    activo = fields.Boolean(
        string='Activo', 
        default=True,
        tracking=True,
        help='Solo puede haber una configuración activa a la vez'
    )
    
    max_output_tokens = fields.Integer(
        string='Máximo tokens de salida', 
        default=2048,
        help='Límite de palabras en la respuesta (1 token ≈ 0.75 palabras)'
    )
    
    temperature = fields.Float(
        string='Temperature', 
        default=0.3,
        help='Controla la creatividad: 0.0 = más conservador y preciso, 1.0 = más creativo'
    )
    
    # Estadísticas de uso
    total_llamadas = fields.Integer(
        string='Total de llamadas', 
        readonly=True, 
        default=0,
        help='Número total de veces que se ha usado esta configuración'
    )
    
    ultima_llamada = fields.Datetime(
        string='Última llamada', 
        readonly=True,
        help='Fecha y hora de la última vez que se usó la API'
    )
    
    # ========================================
    # RESTRICCIONES SQL
    # ========================================
    _sql_constraints = [
        ('activo_unico', 'CHECK(activo = false OR (SELECT COUNT(*) FROM gemini_configuracion WHERE activo = true) = 1)', 
         'Solo puede haber una configuración activa a la vez')
    ]
    
    # ========================================
    # MÉTODOS
    # ========================================
    
    @api.model
    def get_config_activa(self):
        """
        Obtiene la configuración activa de Gemini.
        Lanza error si no existe ninguna.
        """
        config = self.search([('activo', '=', True)], limit=1)
        if not config:
            raise UserError(
                "⚠️ No hay configuración de Gemini activa.\n\n"
                "Para usar la generación con IA, necesitas:\n\n"
                "1. Ir a: Sistema de taller → Configuración → Gemini API\n"
                "2. Crear una configuración con tu API key\n"
                "3. Marcarla como 'Activa'\n\n"
                "Obtén tu API key gratuita en:\n"
                "https://makersuite.google.com/app/apikey"
            )
        return config
    
    def incrementar_contador(self):
        """Registra cada uso de la API (para estadísticas)"""
        self.ensure_one()
        self.sudo().write({
            'total_llamadas': self.total_llamadas + 1,
            'ultima_llamada': fields.Datetime.now()
        })
        _logger.info("Gemini API usada. Total llamadas: %s", self.total_llamadas + 1)
    
    def action_test_connection(self):
        """
        Prueba la conexión con la API de Gemini.
        Botón disponible en el formulario de configuración.
        """
        self.ensure_one()
        
        # Verificar que la librería esté instalada
        if not GEMINI_AVAILABLE:
            raise UserError(
                "❌ La librería google-generativeai no está instalada.\n\n"
                "Ejecuta en tu servidor:\n"
                "pip install google-generativeai\n\n"
                "O agrega al requirements.txt de tu módulo:\n"
                "google-generativeai>=0.3.0"
            )
        
        try:
            _logger.info("Probando conexión con Gemini API (modelo: %s)", self.modelo)
            
            # Configurar API con la key
            genai.configure(api_key=self.api_key)
            
            # Crear modelo
            model = genai.GenerativeModel(model_name=self.modelo)
            
            # Prueba simple
            _logger.debug("Enviando prompt de prueba...")
            response = model.generate_content("Responde solo con: OK")
            
            respuesta_texto = response.text.strip()
            _logger.info("Respuesta recibida: %s", respuesta_texto)
            
            # Registrar en el chatter
            self.message_post(
                body=f"✅ <b>Prueba de conexión exitosa</b><br/>"
                     f"<b>Modelo:</b> {self.modelo}<br/>"
                     f"<b>Respuesta:</b> {respuesta_texto}<br/>"
                     f"<b>Fecha:</b> {fields.Datetime.now()}"
            )
            
            # Mostrar notificación al usuario
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ Conexión exitosa',
                    'message': f'La API de Gemini está funcionando correctamente.\n\n'
                              f'Modelo: {self.modelo}\n'
                              f'Respuesta: {respuesta_texto}',
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            error_msg = str(e)
            _logger.error("Error al probar conexión con Gemini: %s", error_msg, exc_info=True)
            
            # Registrar error en el chatter
            self.message_post(
                body=f"❌ <b>Error al probar conexión</b><br/>"
                     f"<b>Error:</b> {error_msg}<br/>"
                     f"<b>Fecha:</b> {fields.Datetime.now()}"
            )
            
            # Mostrar error al usuario con ayuda
            mensaje_ayuda = self._get_mensaje_error_ayuda(error_msg)
            
            raise UserError(
                f"❌ Error al conectar con Gemini:\n\n"
                f"{error_msg}\n\n"
                f"{mensaje_ayuda}"
            )
    
    def _get_mensaje_error_ayuda(self, error_msg):
        """Retorna mensaje de ayuda según el tipo de error"""
        error_lower = error_msg.lower()
        
        if 'api key' in error_lower or 'invalid' in error_lower:
            return (
                "💡 Posible causa: API Key inválida\n\n"
                "Verifica que:\n"
                "• Copiaste la key completa (sin espacios)\n"
                "• La key está activa en Google AI Studio\n"
                "• Tienes acceso a Gemini API\n\n"
                "Obtén/verifica tu key en:\n"
                "https://makersuite.google.com/app/apikey"
            )
        elif 'quota' in error_lower or 'limit' in error_lower:
            return (
                "💡 Posible causa: Límite de cuota excedido\n\n"
                "El tier gratuito tiene límites:\n"
                "• 15 solicitudes por minuto\n"
                "• 1M tokens por minuto\n\n"
                "Espera un momento e intenta nuevamente."
            )
        elif 'network' in error_lower or 'connection' in error_lower:
            return (
                "💡 Posible causa: Problema de red\n\n"
                "Verifica que:\n"
                "• Tu servidor tiene acceso a internet\n"
                "• No hay firewall bloqueando la conexión\n"
                "• La URL de Google AI es accesible"
            )
        else:
            return (
                "💡 Verifica:\n"
                "• Que tu API key sea correcta\n"
                "• Que tengas conexión a internet\n"
                "• Los logs del servidor para más detalles"
            )
    
    @api.model
    def create(self, vals):
        """Sobrescribe create para desactivar otras configs si esta es activa"""
        if vals.get('activo'):
            # Desactivar todas las demás
            self.search([('activo', '=', True)]).write({'activo': False})
        return super().create(vals)
    
    def write(self, vals):
        """Sobrescribe write para desactivar otras configs si esta se activa"""
        if vals.get('activo'):
            # Desactivar todas las demás excepto esta
            self.search([('activo', '=', True), ('id', 'not in', self.ids)]).write({'activo': False})
        return super().write(vals)
    
    def action_reset_stats(self):
        """Reinicia las estadísticas de uso"""
        self.ensure_one()
        self.write({
            'total_llamadas': 0,
            'ultima_llamada': False
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '🔄 Estadísticas reiniciadas',
                'message': 'El contador de llamadas se ha reiniciado a cero.',
                'type': 'info',
            }
        }