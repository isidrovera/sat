# -*- coding: utf-8 -*-
from odoo import models, fields, api

class LineaPedido(models.Model):
    _inherit = 'sale.order.line'

    ticket_id = fields.Many2one('ticket.alquiler', string='Ticket de referencia', related='order_id.ticket_id')
    ticket_ref_id = fields.Many2one('ticket.alquiler', string='Referencia de Ticket')
    serie = fields.Char(related='ticket_id.serie_id_r', string='Serie')
    contometro = fields.Char(related='ticket_id.total_copias_id', string='Contometro actual', readonly=False)
    contometroa = fields.Char(string='Contometro anterior')
    pedido_id = fields.Many2one('sale.order', string='Pedido')
    codigo_id = fields.Char(string='Referencia id')
    estado_entrega = fields.Selection(
        string='Estado de entrega', 
        selection=[('sin_entregar', 'No entregado'), ('entregado', 'Entregado')], 
        related='order_id.estado_entrega',
        store=True,
        readonly=False
    )

    @api.depends('contometro', 'contometroa')
    def _compute_total_copias(self):
        for record in self:
            contometro = int(record.contometro) if isinstance(record.contometro, str) and record.contometro.isdigit() else 0
            contometroa = int(record.contometroa) if isinstance(record.contometroa, str) and record.contometroa.isdigit() else 0
            record.total_copias_id = str(contometro - contometroa)

    total_copias_id = fields.Char(string="Total de copias", compute="_compute_total_copias")