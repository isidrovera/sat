# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SaleOrderInherit(models.Model):
    _inherit = 'sale.order'

    equipo_id = fields.Many2one('alquiler', string='Equipo')
    obs = fields.Html(string='Observaciones', tracking=True)
    solicitante_id = fields.Many2one('res.users', string='Solicitante')
    ticket_id = fields.Many2one('ticket.alquiler', string='Ticket referente')
    tipo_pedido = fields.Selection(
        string='Tipo de cotización', 
        selection=[('normal', 'Normal'), ('delivery', 'Delivery')], 
        default="normal", 
        tracking=True
    )
    estado_entrega = fields.Selection(
        string='Estado de entrega', 
        selection=[('sin_entregar', 'No entregado'), ('entregado', 'Entregado')],
        default='sin_entregar', 
        tracking=True
    )
    repuestos_count_pedidos = fields.Integer(compute='compute_count_repuestos_pedidos', default=0)
    ticket_count_ticket = fields.Integer(compute='compute_count_ticket', default=0)

    def write(self, vals):
        res = super(SaleOrderInherit, self).write(vals)
        for order in self:
            if order.state == "sale" and order.tipo_pedido == "normal":
                ticket_alquiler = self.env['ticket.alquiler'].search(
                    [('codigo_id', '=', order.id)], limit=1
                )
                # Si no existe un ticket asociado, crearlo; si existe, actualizarlo
                ticket_values = {
                    'codigo_id': order.id,
                    'product_alquiler': order.equipo_id.id,
                    'partner_id': order.equipo_id.cliente_id.id,
                    'description': f"Cambiar repuestos según numero de pedido # {order.name}",
                    'direccion_id_r': order.equipo_id.direccion,
                    'contacto_id_r': order.equipo_id.contacto_id,
                    'tipo_servicio_id': 'cambio_repuestos',
                }
                if not ticket_alquiler:
                    self.env['ticket.alquiler'].create(ticket_values)
                else:
                    ticket_alquiler.write(ticket_values)
        return res

    def compute_count_repuestos_pedidos(self):
        for record in self:
            record.repuestos_count_pedidos = self.env['repuestos.alquiler'].search_count(
                [('modelo_id', '=', record.equipo_id.id)])

    def compute_count_ticket(self):
        for record in self:
            record.ticket_count_ticket = self.env['ticket.alquiler'].search_count(
                [('product_alquiler', '=', record.equipo_id.id)])

    def get_repuestos_pedidos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Repuestos_pedidos',
            'view_mode': 'list,form',
            'res_model': 'repuestos.alquiler',
            'domain': [('modelo_id', '=', self.equipo_id.id)],
            'context': "{'create': False}"
        }

    def get_ticket_ticket(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tickets_pedidos',
            'view_mode': 'list,form',
            'res_model': 'ticket.alquiler',
            'domain': [('product_alquiler', '=', self.equipo_id.id)],
            'context': "{'create': False}"
        }
