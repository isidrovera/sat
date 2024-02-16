from odoo import _, models, fields, api
class tipo_maquina(models.Model):

    _name = 'tipo.maquina'
    _description = 'Indica el tipo de maquina'
    name = fields.Char(
        string='Tipo de maquina',
        required=True)
    _sql_constraints = [("unique_name", "unique (name)",
                         "El tipo de maquina que intenta agregar ya existe")]
