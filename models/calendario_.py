# -*- coding: utf-8 -*-
from odoo import models, fields

class mantenimiento(models.Model):
    _inherit = 'calendar.event'

    maquina_id = fields.Many2one('alquiler',string='Maquina')
    partner_id = fields.Many2one('res.partner',string='Empresa')
    "direccion_id = fields.Char(related='maquina_id.direccion',string='Dirección')