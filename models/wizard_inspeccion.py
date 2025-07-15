
import calendar
import requests
import uuid
from urllib.parse import urlencode
from odoo.exceptions import UserError, ValidationError
import io
import qrcode
import re
import base64
from io import BytesIO
import xlwt
from odoo import _, models, fields, api
from dateutil.relativedelta import relativedelta
from datetime import datetime
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)
class WizardEnviarInspeccion(models.TransientModel):
    _name = 'wizard.enviar.inspeccion'
    _description = 'Asistente para enviar inspección'

    correo = fields.Char(string='Correo electrónico', required=True)
    alquiler_id = fields.Many2one('alquiler', string='Alquiler', required=True)

    def action_enviar(self):
        self.ensure_one()
        url = self.alquiler_id._generar_url_inspeccion()
        template = self.env.ref('sat.mail_template_inspeccion')
        template.with_context(url_inspeccion=url).send_mail(
            self.alquiler_id.id,
            email_values={'email_to': self.correo},
            force_send=True
        )
        return {'type': 'ir.actions.act_window_close'}

