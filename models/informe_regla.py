# models/informe_regla.py
from odoo import models, fields

class InformeRegla(models.Model):
    _name = 'informe.regla'
    _description = 'Reglas para generar conclusiones del informe'

    tipo_id = fields.Many2one('componente.tipo', required=True)
    color = fields.Selection([('k','K'),('c','C'),('m','M'),('y','Y')], string='Color')
    estado_check = fields.Selection(
        [('si','Sí'),('desgaste','Desgaste'),('cambio','Cambio'),('no','No')],
        required=True
    )
    calidad = fields.Selection([('buena','Buena'),('regular','Regular'),('mala','Mala')], required=True)
    estado_operativo = fields.Selection(
        [('operativo','Operativo'),('parcial','Operativo parcial'),('no_op','No operativo')],
        required=True
    )
    frase_hallazgo = fields.Char(required=True, help="8–15 palabras máximo")
    frase_recomendacion = fields.Char(required=True)
    severidad = fields.Selection([('alta','Alta'),('media','Media'),('baja','Baja')], default='media')
    sequence = fields.Integer(default=10)
