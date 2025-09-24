from odoo import models, fields

class AccesorioEstado(models.Model):
    _name = 'accesorio.estado'
    _description = 'Estados/presencia de accesorio'
    _order = 'sequence, name'

    name = fields.Char(required=True)            # Instalado y operativo / Instalado con falla / No instalado / No aplica
    code = fields.Char(required=True, index=True) # instalado_operativo / instalado_con_falla / no_instalado / no_aplica
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    descripcion = fields.Text()

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Código de estado de accesorio duplicado.')
    ]
