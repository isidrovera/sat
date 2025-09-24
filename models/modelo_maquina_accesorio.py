from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ModeloMaquinaAccesorio(models.Model):
    _name = 'modelo.maquina.accesorio'
    _description = 'Plantilla de accesorios por modelo de máquina'
    _order = 'tipo_id'

    modelo_id = fields.Many2one('modelo.maquina', required=True, ondelete='cascade', index=True)
    tipo_id = fields.Many2one('accesorio.tipo', required=True, ondelete='restrict', index=True)
    estado_predeterminado_id = fields.Many2one('accesorio.estado', string='Estado predeterminado', ondelete='restrict')
    obligatorio = fields.Boolean(string='Obligatorio en este modelo', default=False)
    nota = fields.Char(string='Nota')

    _sql_constraints = [
        ('uniq_modelo_accesorio', 'unique(modelo_id, tipo_id)', 'Accesorio repetido para el modelo.')
    ]


class ModelosMaquin(models.Model):
    _inherit = 'modelo.maquina'
    accesorio_line_ids = fields.One2many('modelo.maquina.accesorio', 'modelo_id', string='Accesorios del modelo')
