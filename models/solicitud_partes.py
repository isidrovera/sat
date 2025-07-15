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
class SolicitudPartes(models.Model):
    _name = 'solicitud.partes'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Solicitud de Partes'
    _order = 'fecha_solicitud desc, id desc'

    name = fields.Char(string='Número de Solicitud',
                       readonly=True, copy=False, default='Nuevo')

    maquina_origen_id = fields.Many2one(
        'alquiler',
        string='Máquina Origen',
        required=True,
        tracking=True,
        domain="[('estado_alquiler_id', 'not in', ['vendida', 'partes'])]"
    )
    maquina_destino_id = fields.Many2one(
        'alquiler',
        string='Máquina Destino',
        tracking=True,
        domain="[('id', '!=', maquina_origen_id), ('estado_alquiler_id', 'not in', ['vendida'])]"
    )

    fecha_solicitud = fields.Datetime(
        string='Fecha de Solicitud', default=fields.Datetime.now, tracking=True, readonly=True)
    solicitante_id = fields.Many2one('res.users', string='Solicitante',
                                     default=lambda self: self.env.user, tracking=True, readonly=True)

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('submitted', 'Enviado'),
        ('approved', 'Aprobado'),
        ('completed', 'Completado'),
        ('replaced', 'Reemplazado'),
        ('rejected', 'Rechazado')
    ], string='Estado', default='draft', tracking=True)

    # Campos de autorización
    autorizado_por = fields.Many2one(
        'res.users', string='Autorizado por', tracking=True, readonly=False)
    fecha_autorizacion = fields.Datetime(
        string='Fecha de Autorización', tracking=True, readonly=False)

    # Campos de retiro
    retirado_por = fields.Many2one(
        'res.users', string='Retirado por', tracking=True, readonly=False)
    fecha_retiro = fields.Datetime(
        string='Fecha de Retiro', tracking=True, readonly=False)

    # Campos de reemplazo
    reemplazado_por = fields.Many2one(
        'res.users', string='Reemplazado por', tracking=True, readonly=False)
    fecha_reemplazo = fields.Datetime(
        string='Fecha de Reemplazo', tracking=True, readonly=False)

    parte_ids = fields.One2many(
        'solicitud.partes.linea', 'solicitud_id', string='Partes Solicitadas')
    access_token = fields.Char('Token de Acceso', copy=False, readonly=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'Nuevo') == 'Nuevo':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'solicitud.partes') or 'Nuevo'
        vals['access_token'] = uuid.uuid4().hex
        return super().create(vals)

    def action_submit(self):
        self.ensure_one()
        if not self.parte_ids:
            raise UserError(
                _('Debe agregar al menos una parte antes de enviar la solicitud.'))
        self.write({'state': 'submitted'})
        template = self.env.ref('sat.email_template_solicitud_partes_alquiler')
        template.send_mail(self.id, force_send=True)

    def action_approve(self):
        self.ensure_one()
        self.write({
            'state': 'approved',
            'autorizado_por': self.env.user.id,
            'fecha_autorizacion': fields.Datetime.now()
        })

    def action_complete(self):
        self.ensure_one()
        if not all(line.estado in ['retirado', 'reemplazado'] for line in self.parte_ids):
            raise UserError(
                _('Todas las partes deben estar retiradas o reemplazadas.'))
        self.write({
            'state': 'completed',
            'retirado_por': self.env.user.id,
            'fecha_retiro': fields.Datetime.now()
        })
        self.maquina_origen_id.write({'estado_alquiler_id': 'con_problemas'})

    def action_replace(self):
        self.ensure_one()
        if not all(line.estado == 'reemplazado' for line in self.parte_ids):
            raise UserError(_('Todas las partes deben estar reemplazadas.'))
        self.write({
            'state': 'replaced',
            'reemplazado_por': self.env.user.id,
            'fecha_reemplazo': fields.Datetime.now()
        })
        # Si todas las partes están en buen estado, restaurar estado de la máquina
        if all(line.condicion == 'bueno' for line in self.parte_ids):
            self.maquina_origen_id.write({'estado_alquiler_id': 'alquilada'})

    def action_reject(self):
        self.write({'state': 'rejected'})

    @api.model
    def approve_from_token(self, token):
        solicitud = self.search([
            ('access_token', '=', token),
            ('state', '=', 'submitted')
        ], limit=1)

        if solicitud:
            try:
                solicitud.action_approve()
                return {'success': True}
            except Exception as e:
                return {'error': str(e)}
        return {'error': 'Token inválido o solicitud no encontrada'}

