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

class repuestos_alquiler(models.Model):
    _name = 'repuestos.alquiler'
    name = fields.Char("Descripción")

    cliente_id = fields.Char("Cliente")
    modelo_id = fields.Many2one('alquiler', string="Modelo")
    serie_id = fields.Char("Serie")
    contometro_actual = fields.Integer(string="Contometro actual")
    contometro_ultimo = fields.Integer(string="Contometro ultimo cambio")
    cantidad = fields.Integer(string="Cantidad")
    referencia_reparacion_id = fields.Char("Pedido N°")
    duracion_repuesto = fields.Integer(string="Duración referencial")
    solicitante_id = fields.Char(string="Solicitante")
    rendimiento = fields.Integer(
        string="Rendimiento", compute="compute_repuestos_count")

    @api.depends('contometro_actual')
    def compute_repuestos_count(self):

        for record in self:
            record.rendimiento = record.contometro_actual - record.contometro_ultimo

    precio_compra = fields.Float(string='Precio de compra')

    @api.model
    def _default_currency_id(self):
        value = self.env['res.currency'].search(
            [('name', '=', 'USD')], limit=1)
        return value and value.id or False

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency', default=_default_currency_id)
    codigo_id = fields.Char(string='Codigo de pedido')