from odoo import models, fields

class User(models.Model):
    _inherit = 'res.users'

    mobile_phone_international = fields.Char(string="Mobile Phone (International)")

