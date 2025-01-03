from odoo import _, models, fields, api
from dateutil.relativedelta import relativedelta
from datetime import datetime
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)
import xlwt
from io import BytesIO
import base64
import re

class informes(models.Model):
    _name = ('informes')
    _description = 'Registro de informes proveedores'

    name = fields.Char(string="Informe N°",
                       default='New',
                       copy=False, required=True,
                       readonly=True)

    @api.model
    def create(self, vals):
        # We generate a standard reference
        vals['name'] = self.env['ir.sequence'].next_by_code('informes') or '/'
        return super(informes, self).create(vals)

    proveedor_id = fields.Many2one('res.partner', string='Proveedor', )
    
    importacion = fields.Char(string="Importación")
    invoice = fields.Char(string="Invoice")
    informe = fields.Text(string="Informe", 
    default='Estimados señores,\n\nMediante el presente documento, les entregamos el informe del estado de las máquinas fotocopiadoras.\n\n Durante el mantenimiento realizado, se detectaron fallas y se identificaron los elementos que deben ser reemplazados para asegurar su correcto funcionamiento.\n\nA continuación, detallamos el informe de cada una de las máquinas:'
    )



                                
    detalle_ids = fields.Many2many('fallas')

    def send_email(self):
        template_id = self.env.ref('sat.email_template_informes')
        template_id.send_mail(self.id, force_send=True)