# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class GeminiConfiguracion(models.Model):
    _name = 'gemini.configuracion'
    _description = 'Configuración de Google Gemini API'
    
    name = fields.Char(string='Nombre', default='Configuración Gemini', required=True)
    api_key = fields.Char(string='API Key de Gemini', required=True, 
                          help='Obtén tu API key en https://makersuite.google.com/app/apikey')
    modelo = fields.Selection([
        ('gemini-1.5-flash', 'Gemini 1.5 Flash (Recomendado - Rápido y gratuito)'),
        ('gemini-1.5-pro', 'Gemini 1.5 Pro (Más potente pero más lento)'),
    ], string='Modelo', default='gemini-1.5-flash', required=True)
    
    activo = fields.Boolean(string='Activo', default=True)
    max_output_tokens = fields.Integer(string='Máximo tokens de salida', default=2048,
                                       help='Límite de palabras en la respuesta')
    temperature = fields.Float(string='Temperature', default=0.3,
                               help='0.0 = más conservador, 1.0 = más creativo')
    
    # Estadísticas de uso
    total_llamadas = fields.Integer(string='Total de llamadas', readonly=True, default=0)
    ultima_llamada = fields.Datetime(string='Última llamada', readonly=True)
    
    _sql_constraints = [
        ('activo_unico', 'UNIQUE(activo)', 'Solo puede haber una configuración activa')
    ]
    
    @api.model
    def get_config_activa(self):
        """Obtiene la configuración activa"""
        config = self.search([('activo', '=', True)], limit=1)
        if not config:
            raise UserError(
                "No hay configuración de Gemini activa.\n\n"
                "Ve a: Sistema de taller → Configuración → Gemini API\n"
                "Y crea una configuración con tu API key."
            )
        return config
    
    def incrementar_contador(self):
        """Registra uso de la API"""
        self.ensure_one()
        self.sudo().write({
            'total_llamadas': self.total_llamadas + 1,
            'ultima_llamada': fields.Datetime.now()
        })