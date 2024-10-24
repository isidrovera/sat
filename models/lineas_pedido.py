

# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class linea_pedido(models.Model):
    _inherit = 'sale.order.line'

    ticket_id = fields.Many2one('ticket.alquiler', string='Ticket de referencia',related='order_id.ticket_id'
    )
    
    serie  = fields.Char(related='ticket_id.serie_id_r',string='Serie')
    contometro =  fields.Integer(related='ticket_id.total_copias_id',string='Contometro actual', readonly=False 
    )
    contometroa  = fields.Integer(string='Contometro anterior')   
    
    pedido_id = fields.Many2one('sale.order',string='Pedido')  
    codigo_id  = fields.Char(string='Referencia id')  
    estado_entrega = fields.Selection(string='Estado de entrega', selection=[('sin_entregar', 'No entregado'), ('entregado', 'Entregado')], 
    related='order_id.estado_entrega',
    readonly=False,   
                                    
                                      )

    @api.depends('contometro', 'contometroa')
    def restar_field(self):
        for record in self:
            if record.contometro and record.contometroa:
                record.total_copias_id = record.contometro - record.contometroa
            else:
                record.total_copias_id = 0

    total_copias_id = fields.Integer(string="Total de copias", compute=restar_field)

    @api.model
    def write(self, vals):
        if 'estado_entrega' in vals and vals['estado_entrega'] == 'entregado':
            _logger = logging.getLogger(__name__)
            _logger.debug("Se detectó un cambio al estado 'entregado'.")
            RepuestosAlquiler = self.env['repuestos.alquiler']
            for record in self:
                # Busca el registro existente
                repuesto = RepuestosAlquiler.search([('codigo_id', '=', record.id)], limit=1)
                repuesto_vals = {
                    'referencia_reparacion_id': record.order_id.name,
                    'serie_id': record.order_id.equipo_id.serie,
                    'modelo_id': record.order_id.equipo_id.id,
                    'cliente_id': record.order_id.partner_id.name,
                    'cantidad': record.product_uom_qty,
                    'contometro_actual': record.contometro,
                    'contometro_ultimo': record.contometroa,
                    'solicitante_id': record.order_id.solicitante_id.name,
                    'name': record.product_template_id.name,
                    'codigo_id': record.id,
                }
                
                if not repuesto:
                    # Si no existe, crea uno nuevo
                    _logger.debug("Creando nuevo registro en repuestos.alquiler.")
                    RepuestosAlquiler.create(repuesto_vals)
                else:
                    # Si existe, actualiza
                    _logger.debug("Actualizando registro existente en repuestos.alquiler.")
                    repuesto.write(repuesto_vals)

        return super(linea_pedido, self).write(vals)

        
                        
                            
                            