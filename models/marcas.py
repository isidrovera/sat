from odoo import _, models, fields, api

class marcas(models.Model):

    _name = 'marca.marca'
    _description = 'Marca_de_maquina'

    name = fields.Char(string='Marca de maquina')
 
    _sql_constraints = [("unique_name", "unique (name)",
                         "La marca que intenta agregar ya existe")]