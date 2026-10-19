from odoo import _, models, fields, api
class tipo_maquina(models.Model):

    _name = 'tipo.maquina'
    _description = 'Indica el tipo de maquina'
    name = fields.Char(
        string='Tipo de maquina',
        required=True)
    
    _unique_name = models.Constraint(
        'UNIQUE(name)',
        'El tipo de maquina que intenta agregar ya existe',
    )
