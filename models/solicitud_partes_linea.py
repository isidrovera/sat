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
class SolicitudPartesLinea(models.Model):
    _name = 'solicitud.partes.linea'
    _description = 'Línea de Solicitud de Partes'

    solicitud_id = fields.Many2one('solicitud.partes', string='Solicitud')
    parte = fields.Char(string='Parte/Unidad', required=True)
    descripcion = fields.Text(string='Descripción')
    estado = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('retirado', 'Retirado'),
        ('reemplazado', 'Reemplazado')
    ], string='Estado', default='pendiente')

    # Campos de reemplazo
    fecha_reemplazo = fields.Datetime(string='Fecha Reemplazo')
    reemplazado_por = fields.Many2one('res.users', string='Reemplazado por')
    condicion = fields.Selection([
        ('bueno', 'Buen Estado'),
        ('defectuoso', 'Defectuoso')
    ], string='Condición')

    # Relación con máquina origen a través de solicitud
    maquina_origen_id = fields.Many2one(
        'alquiler',
        string='Máquina Origen',
        related='solicitud_id.maquina_origen_id',
        store=True
    )

    def action_retirar(self):
        self.write({'estado': 'retirado'})

    def action_reemplazar(self):
        self.write({
            'estado': 'reemplazado',
            'fecha_reemplazo': fields.Datetime.now(),
            'reemplazado_por': self.env.user.id
        })

    def action_registrar_condicion(self):
        return {
            'name': 'Registrar Condición',
            'type': 'ir.actions.act_window',
            'res_model': 'registro.condicion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_parte_id': self.id}
        }
