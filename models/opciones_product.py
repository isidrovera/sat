# -*- coding: utf-8 -*-
from odoo import models, fields, api

class opciones_productos(models.Model):
    _inherit = 'product.template'

    durabilidad = fields.Char(string='Durabilidad')
