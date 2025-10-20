# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

# ===== IMPORTAR NUEVA LIBRERÍA GOOGLE-GENAI =====
try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    _logger.warning("google-genai no está instalado. Instala con: pip install google-genai")


class GeminiConfiguracion(models.Model):
    _name = 'gemini.configuracion'
    _description = 'Configuración de Google Gemini API'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
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
        help='Obtén tu API key en https://aistudio.google.com/apikey'
    )
    
    modelo = fields.Selection([
        ('gemini-2.0-flash-exp', 'Gemini 2.0 Flash Experimental (Más nuevo y rápido) 🆕'),
        ('gemini-1.5-flash', 'Gemini 1.5 Flash (Estable y rápido) ⚡'),
        ('gemini-1.5-pro', 'Gemini 1.5 Pro (Más potente) 🧠'),
        ('gemini-1.0-pro', 'Gemini 1.0 Pro (Versión anterior) 📦'),
    ], string='Modelo', 
       default='gemini-2.0-flash-exp', 
       required=True,
       tracking=True,
       help='Modelo de IA a utilizar para generar informes'
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
        help='Límite de tokens en la respuesta (1 token ≈ 0.75 palabras)'
    )
    
    temperature = fields.Float(
        string='Temperature', 
        default=0.3,
        help='Creatividad: 0.0 = preciso y conservador, 1.0 = creativo'
    )
    
    # Estadísticas
    total_llamadas = fields.Integer(
        string='Total de llamadas', 
        readonly=True, 
        default=0
    )
    
    ultima_llamada = fields.Datetime(
        string='Última llamada', 
        readonly=True
    )
    
    # ========================================
    # RESTRICCIONES
    # ========================================
    _sql_constraints = [
        ('activo_unico', 
         'CHECK(activo = false OR (SELECT COUNT(*) FROM gemini_configuracion WHERE activo = true) = 1)', 
         'Solo puede haber una configuración activa')
    ]
    
    # ========================================
    # MÉTODOS
    # ========================================
    
    @api.model
    def get_config_activa(self):
        """Obtiene la configuración activa"""
        config = self.search([('activo', '=', True)], limit=1)
        if not config:
            raise UserError(
                "⚠️ No hay configuración de Gemini activa.\n\n"
                "Para usar IA:\n"
                "1. Ve a: Sistema de taller → Configuración → Gemini API\n"
                "2. Crea una configuración con tu API key\n"
                "3. Márcala como 'Activa'\n\n"
                "Obtén tu API key en: https://aistudio.google.com/apikey"
            )
        return config
    
    def incrementar_contador(self):
        """Registra uso de la API"""
        self.ensure_one()
        self.sudo().write({
            'total_llamadas': self.total_llamadas + 1,
            'ultima_llamada': fields.Datetime.now()
        })
        _logger.info("Gemini API usada. Total: %s", self.total_llamadas + 1)
    
    def action_test_connection(self):
        """Prueba la conexión con Gemini API (NUEVA SINTAXIS)"""
        self.ensure_one()
        
        if not GEMINI_AVAILABLE:
            raise UserError(
                "❌ La librería google-genai no está instalada.\n\n"
                "Ejecuta: pip install google-genai"
            )
        
        try:
            _logger.info("Probando Gemini API - Modelo: %s", self.modelo)
            
            # NUEVA SINTAXIS: Crear cliente
            client = genai.Client(api_key=self.api_key)
            
            # Llamada simple de prueba
            response = client.models.generate_content(
                model=self.modelo,
                contents="Responde solo con: OK"
            )
            
            respuesta_texto = response.text.strip()
            _logger.info("✅ Respuesta recibida: %s", respuesta_texto)
            
            # Registrar en chatter
            self.message_post(
                body=f"✅ <b>Prueba de conexión exitosa</b><br/>"
                     f"<b>Modelo:</b> {self.modelo}<br/>"
                     f"<b>Respuesta:</b> {respuesta_texto}<br/>"
                     f"<b>Fecha:</b> {fields.Datetime.now()}"
            )
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ Conexión exitosa',
                    'message': f'Gemini funcionando correctamente.\n\n'
                              f'Modelo: {self.modelo}\n'
                              f'Respuesta: {respuesta_texto}',
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            error_msg = str(e)
            _logger.error("❌ Error Gemini: %s", error_msg, exc_info=True)
            
            self.message_post(
                body=f"❌ <b>Error al probar conexión</b><br/>"
                     f"<b>Error:</b> {error_msg}"
            )
            
            mensaje_ayuda = self._get_mensaje_error_ayuda(error_msg)
            
            raise UserError(
                f"❌ Error al conectar con Gemini:\n\n"
                f"{error_msg}\n\n"
                f"{mensaje_ayuda}"
            )
    
    def _get_mensaje_error_ayuda(self, error_msg):
        """Mensaje de ayuda según el error"""
        error_lower = error_msg.lower()
        
        if 'api key' in error_lower or 'invalid' in error_lower or '400' in error_lower:
            return (
                "💡 API Key inválida\n\n"
                "Verifica:\n"
                "• Key completa copiada (sin espacios)\n"
                "• Key activa en Google AI Studio\n\n"
                "Obtén/verifica: https://aistudio.google.com/apikey"
            )
        elif '404' in error_lower or 'not found' in error_lower:
            return (
                "💡 Modelo no encontrado\n\n"
                "Prueba cambiar a:\n"
                "• gemini-2.0-flash-exp\n"
                "• gemini-1.5-flash\n"
                "• gemini-1.5-pro"
            )
        elif 'quota' in error_lower or 'limit' in error_lower or '429' in error_lower:
            return (
                "💡 Límite de cuota excedido\n\n"
                "Tier gratuito:\n"
                "• 15 solicitudes/minuto\n"
                "• 1M tokens/minuto\n\n"
                "Espera un momento."
            )
        else:
            return (
                "💡 Verifica:\n"
                "• API key correcta\n"
                "• Conexión a internet\n"
                "• Logs del servidor"
            )
    
    @api.model
    def create(self, vals):
        """Desactiva otras configs si esta es activa"""
        if vals.get('activo'):
            self.search([('activo', '=', True)]).write({'activo': False})
        return super().create(vals)
    
    def write(self, vals):
        """Desactiva otras configs si esta se activa"""
        if vals.get('activo'):
            self.search([('activo', '=', True), ('id', 'not in', self.ids)]).write({'activo': False})
        return super().write(vals)
    
    def action_reset_stats(self):
        """Reinicia estadísticas"""
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
                'message': 'Contador reiniciado a cero.',
                'type': 'info',
            }
        }