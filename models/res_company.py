# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    # Solo un campo de prueba primero
    attendance_gps_required = fields.Boolean(
        string='Require GPS Location',
        default=False,
        help='Require GPS location for attendance records'
    )