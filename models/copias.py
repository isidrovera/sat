# -*- coding: utf-8 -*-

from odoo import _, models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
import logging
import base64
from io import BytesIO
import qrcode

_logger = logging.getLogger(__name__)

class SatSat(models.Model):
    _name = 'sat.sat'
    _description = 'Registro de maquina'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Many2one('modelo.maquina', string='Modelo', required=True, tracking=True)
    serie_id = fields.Char(string='Serie', tracking=True, required=True)
    estado_ventas_id = fields.Selection([('sin_revisar', 'Sin revisar'), ('para_revision', 'Para revision'), 
                                         ('asignado', 'Asignado'), ('en_revision', 'En revisión'), 
                                         ('finalizado', 'Finalizado'), ('con_problemas', 'Con problemas'), 
                                         ('de_partes', 'De partes'), ('entregada', 'Entregada')],
                                        string='Estado de revisión', default='sin_revisar', tracking=True)
    tipo_revision = fields.Selection([('paso_papel', 'Paso papel'), ('regular', 'Regular'), 
                                      ('cliente_final', 'Cliente final')], tracking=True)
    prioridad = fields.Selection([('bajaubicacion', 'Baja'), ('alta', 'Alta')], tracking=True)
    fecha_para_revision = fields.Datetime(string="Fecha para Revisión", readonly=True)
    trabajadores_id = fields.Many2one('hr.employee', string='Trabajadores', tracking=True, default=1)
    disponibilidad_id = fields.Selection([('disponible', 'Disponible'), ('separada', 'Separada'), 
                                          ('no_disponible', 'No disponible')], default='disponible', 
                                          tracking=True, readonly=True, compute='_compute_disponibilidad_id', store=True)

    @api.depends('cliente_id', 'estado_ventas_id')
    def _compute_disponibilidad_id(self):
        for record in self:
            if record.estado_ventas_id in ['sin_revisar', 'en_revision', 'finalizado', 'para_revision'] and record.cliente_id:
                record.disponibilidad_id = 'separada'
                record.fecha_separacion = fields.Date.today()
            elif record.estado_ventas_id in ['sin_revisar', 'en_revision', 'finalizado', 'para_revision'] and not record.cliente_id:
                record.disponibilidad_id = 'disponible'
                record.fecha_separacion = False
            else:
                record.disponibilidad_id = 'no_disponible'
                record.fecha_separacion = False

    def get_isidro_partner_id(self):
        isidro_user = self.env['res.users'].search([('name', '=', 'Isidro Vera Polo')], limit=1)
        if isidro_user:
            return isidro_user.partner_id.id
        return False

    def write(self, vals):
        estados_permitidos_para_cambio = ['sin_revisar', 'para_revision']
        tipo_revision_modificado = 'tipo_revision' in vals
        prioridad_modificada = 'prioridad' in vals
        isidro_partner_id = self.get_isidro_partner_id()

        for record in self:
            estado_actual = record.estado_ventas_id

            if estado_actual in estados_permitidos_para_cambio:
                if tipo_revision_modificado or prioridad_modificada:
                    if vals.get('tipo_revision') or vals.get('prioridad'):
                        vals['estado_ventas_id'] = 'para_revision'
                        vals['fecha_para_revision'] = fields.Datetime.now()

                        if isidro_partner_id:
                            user_name = self.env.user.name
                            record_name = record.name.name
                            serie = record.serie_id
                            message = f"Se ha colocado una nueva máquina para revisión.\n\nDetalles del equipo:\n- Nombre: {record_name}\n- Serie: {serie}\n\nModificado por: {user_name}"
                            record.message_post(body=message, partner_ids=[isidro_partner_id], subtype='mail.mt_comment')
                    else:
                        vals['estado_ventas_id'] = 'sin_revisar'
                        vals['fecha_para_revision'] = None

        return super(SatSat, self).write(vals)
# -*- coding: utf-8 -*-

from odoo import _, models, fields, api
from odoo.exceptions import ValidationError
import logging
import base64
from io import BytesIO
import qrcode
import requests
import json

_logger = logging.getLogger(__name__)

class reparaciones(models.Model):
    _name = 'reparaciones.reparaciones'
    _description = 'Reparaciones Ventas'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Reparacion N°', default='New', copy=False, required=True, readonly=True)
    maquina_id = fields.Many2one('sat.sat', string='Maquina', tracking=True)
    estado_id = fields.Selection([('sin_revisar', 'Sin revisar'), ('para_revision', 'Para revision'), 
                                  ('asignado', 'Asignado'), ('en_revision', 'En revisión'), 
                                  ('finalizado', 'Finalizado'), ('con_problemas', 'Con problemas'), 
                                  ('de_partes', 'De partes'), ('entregada', 'Entregada')],
                                 string='Estado de revisión', related='maquina_id.estado_ventas_id', 
                                 readonly=False, store=True)
    fecha_finalizacion = fields.Datetime(string='Fecha de Finalización', readonly=True, store=True)
    responsable_id = fields.Many2one('res.users', string='Responsable', tracking=True)

    @api.model
    def create(self, vals):
        vals['name'] = self.env['ir.sequence'].next_by_code('reparaciones.reparaciones') or '/'
        record = super(reparaciones, self).create(vals)
        return record

    def _create_next_reparacion(self):
        next_maquina = self.env['sat.sat'].search([
            ('estado_ventas_id', '=', 'para_revision')
        ], order='fecha_para_revision asc', limit=1)
        
        if next_maquina:
            next_maquina.write({
                'estado_ventas_id': 'en_revision',
                'trabajadores_id': self.responsable_id.id
            })
            self.env['reparaciones.reparaciones'].create({
                'maquina_id': next_maquina.id,
                'responsable_id': self.responsable_id.id,
            })

    def write(self, vals):
        finalizado = vals.get('estado_id') == 'finalizado'
        
        if finalizado:
            for rec in self:
                if rec.estado_id == 'en_revision':
                    vals['fecha_finalizacion'] = fields.Datetime.now()

        res = super(reparaciones, self).write(vals)
        
        if 'falla_proveedor' in vals:
            for rec in self:
                existing_record = rec.env['fallas'].search([
                    ('name', '=', rec.maquina_id.invoice),
                    ('modelo_id', '=', rec.maquina_id.name.name),
                    ('importacion', '=', rec.maquina_id.importacion),
                    ('proveedor_id', '=', rec.maquina_id.proveedor_id.name),
                    ('marca', '=', rec.maquina_id.marca),
                    ('serie', '=', rec.maquina_id.serie_id),
                    ('usuario_id', '=', rec.responsable_id.name),
                ], limit=1)
                if existing_record:
                    existing_record.write({
                        'descripcion': rec.falla_proveedor,
                    })
                else:
                    rec.env['fallas'].create({
                        'descripcion': rec.falla_proveedor,
                        'name': rec.maquina_id.invoice,
                        'modelo_id': rec.maquina_id.name.name,
                        'importacion': rec.maquina_id.importacion,
                        'proveedor_id': rec.maquina_id.proveedor_id.name,
                        'marca': rec.maquina_id.marca,
                        'serie': rec.maquina_id.serie_id,
                        'usuario_id': rec.responsable_id.name,
                    })
        
        if finalizado:
            self._create_next_reparacion()

        return res
