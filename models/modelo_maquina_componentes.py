# models/modelo_maquina_componentes.py
from odoo import models, fields

class ModeloMaquinaComponente(models.Model):
    _name = 'modelo.maquina.componente'
    _description = 'Componentes presentes en un modelo de máquina'

    modelo_id = fields.Many2one('modelo.maquina', required=True, ondelete='cascade')
    tipo_id = fields.Many2one('componente.tipo', required=True)
    color = fields.Selection(
        [('k','K'), ('c','C'), ('m','M'), ('y','Y')],
        string='Color', help='Solo si aplica (IU por color, etc.)'
    )
    subparte_ids = fields.Many2many('componente.subparte', string='Subpartes incluidas')
    vida_util_paginas = fields.Integer(string='Vida útil (pág.)')
    vida_util_meses = fields.Integer(string='Vida útil (meses)')
    prioridad = fields.Selection(
        [('1','Crítico'),('2','Medio'),('3','Bajo')],
        default='1', string='Prioridad'
    )
    frase_desgaste = fields.Char(string='Frase desgaste (opcional)')
    frase_cambio = fields.Char(string='Frase cambio/no (opcional)')

# Extiende tu modelo.maquina existente
from odoo import api, models, fields
class ModelosMaquin(models.Model):
    _inherit = 'modelo.maquina'

    componente_line_ids = fields.One2many(
        'modelo.maquina.componente', 'modelo_id',
        string='Componentes del modelo'
    )
