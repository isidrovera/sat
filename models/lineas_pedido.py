# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class LineaPedido(models.Model):
    _inherit = 'sale.order.line'

    ticket_id = fields.Many2one('ticket.alquiler', string='Ticket de referencia')
    ticket_ref_id = fields.Many2one('ticket.alquiler', string='Referencia de Ticket')
    serie = fields.Char(related='ticket_id.serie_id_r', string='Serie')
    contometro = fields.Integer( string='Contometro actual', readonly=False)
    contometroa = fields.Integer(string='Contometro anterior')   
    pedido_id = fields.Many2one('sale.order', string='Pedido')  
    codigo_id = fields.Char(string='Referencia id')  
    estado_entrega = fields.Selection(
        string='Estado de entrega', 
        selection=[('sin_entregar', 'No entregado'), ('entregado', 'Entregado')], 
        related='order_id.estado_entrega',
        readonly=False
    )

    #@api.depends('contometro', 'contometroa')
    #def restar_field(self):
        #for record in self:
            #record.total_copias_id = record.contometro - record.contometroa if record.contometro and record.contometroa else 0

    total_copias_id = fields.Integer(string="Total de copias")

    