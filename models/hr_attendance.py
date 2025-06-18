# -*- coding: utf-8 -*-
from odoo import models, fields

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    # Solo un campo de prueba primero
    location_source = fields.Selection([
        ('geoip', 'IP Geolocation'),
        ('gps', 'GPS'),
        ('manual', 'Manual'),
    ], string='Location Source', default='geoip')