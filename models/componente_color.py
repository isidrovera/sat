# sat/models/componente_color.py
from odoo import models, fields

class ComponenteColor(models.Model):
    _name = 'componente.color'
    _description = 'Color de componente'
    _order = 'sequence, name'
    _rec_name = 'name'

    name = fields.Char(required=True)
    key = fields.Selection([('k','K'), ('c','C'), ('m','M'), ('y','Y')], required=True, index=True)
    sequence = fields.Integer(default=10)

    _sql_constraints = [('key_uniq', 'unique(key)', 'Color repetido.')]
