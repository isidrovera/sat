from odoo import _, models, fields, api

class opciones_cliente(models.Model):

    _inherit = 'res.partner'

    asesora_id = fields.Many2one(
        'res.partner',
        string='Asesora',
        required=True

    )
    tipo_cliente = fields.Selection([('alquiler', 'Alquiler'), ('distribuidor', 'Distribuidor'),
                                     ('proveedor', 'Proveedor')], default="distribuidor",
                                    string='Tipo de cliente',
                                    required=True

                                    )
