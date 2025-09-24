from odoo import models, fields

class ColorTipo(models.Model):
    _name = 'color.tipo'
    _description = 'Catálogo de colores (K/C/M/Y)'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)  # 'k','c','m','y'
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('color_code_uniq', 'unique(code)', 'El código de color ya existe.'),
    ]
