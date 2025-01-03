from odoo import _, models, fields, api

class ajustes(models.Model):

    _name = 'ajustes.ajustes'
    _description = 'Ajustes_de_maquina'

    name = fields.Char(string='Referencia de reparación')