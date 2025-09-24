from odoo import models, fields

class AccesorioTipo(models.Model):
    _name = 'accesorio.tipo'
    _description = 'Catálogo de tipos de accesorio'
    _order = 'sequence, name'

    name = fields.Char(required=True)            # ej: LCT, Bandeja OT, Disco duro, Wi-Fi…
    code = fields.Char(required=True, index=True) # ej: lct, ot, hdd, wifi, panel_smart
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    descripcion = fields.Text()

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Código de accesorio duplicado.')
    ]
