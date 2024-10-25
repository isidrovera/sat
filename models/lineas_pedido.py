# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class LineaPedido(models.Model):
    _inherit = 'sale.order.line'

    ticket_id = fields.Many2one('ticket.alquiler', string='Ticket de referencia', related='order_id.ticket_id')
    ticket_ref_id = fields.Many2one('ticket.alquiler', string='Referencia de Ticket')
    serie = fields.Char(related='ticket_id.serie_id_r', string='Serie')
    contometro = fields.Integer(related='ticket_id.total_copias_id', string='Contometro actual', readonly=False)
    contometroa = fields.Integer(string='Contometro anterior')
    pedido_id = fields.Many2one('sale.order', string='Pedido')
    codigo_id = fields.Char(string='Referencia id')
    estado_entrega = fields.Selection(
        string='Estado de entrega', 
        selection=[('sin_entregar', 'No entregado'), ('entregado', 'Entregado')], 
        related='order_id.estado_entrega',
        readonly=False
    )

    @api.depends('contometro', 'contometroa')
    def restar_field(self):
        for record in self:
            record.total_copias_id = record.contometro - record.contometroa if record.contometro and record.contometroa else 0

    total_copias_id = fields.Integer(string="Total de copias", compute="restar_field")

    def write(self, vals):
        if 'estado_entrega' in vals and vals['estado_entrega'] == 'entregado':
            _logger.debug("Se detectó un cambio al estado 'entregado' para el registro.")
            RepuestosAlquiler = self.env['repuestos.alquiler']
            
            for record in self:
                repuesto = RepuestosAlquiler.search([('codigo_id', '=', record.id)], limit=1)
                repuesto_vals = {
                    'referencia_reparacion_id': record.order_id.name,
                    'serie_id': record.order_id.equipo_id.serie if record.order_id.equipo_id else None,
                    'modelo_id': record.order_id.equipo_id.id if record.order_id.equipo_id else None,
                    'cliente_id': record.order_id.partner_id.name,
                    'cantidad': record.product_uom_qty,
                    'contometro_actual': record.contometro,
                    'contometro_ultimo': record.contometroa,
                    'solicitante_id': record.order_id.solicitante_id.name if record.order_id.solicitante_id else None,
                    'name': record.product_template_id.name if record.product_template_id else None,
                    'codigo_id': record.id,
                }
                
                if not repuesto:
                    _logger.debug("Creando nuevo registro en repuestos.alquiler para ID de producto: %s", record.product_template_id.id if record.product_template_id else 'No disponible')
                    RepuestosAlquiler.create(repuesto_vals)
                else:
                    _logger.debug("Actualizando registro existente en repuestos.alquiler para ID de producto: %s", record.product_template_id.id if record.product_template_id else 'No disponible')
                    repuesto.write(repuesto_vals)

        return super(LineaPedido, self).write(vals)
