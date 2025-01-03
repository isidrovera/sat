# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class SaleOrderInherit(models.Model):
    _inherit = 'sale.order'

    equipo_id = fields.Many2one('alquiler', string='Equipo')
    serie_id = fields.Char(related='equipo_id.serie', string='Serie')
    obs = fields.Html(string='Observaciones')
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

    @api.onchange('estado_entrega')
    def _onchange_estado_entrega(self):
        _logger.info("=== INICIO ONCHANGE ESTADO ENTREGA ===")
        _logger.info(f"Estado actual: {self.estado_entrega}")
        if self.estado_entrega == 'entregado':
            _logger.info("Estado cambiado a 'entregado' - Llamando a crear_actualizar_repuestos")
            self._crear_actualizar_repuestos()
        else:
            _logger.info(f"Estado no es 'entregado' ({self.estado_entrega}) - No se procesa")
        _logger.info("=== FIN ONCHANGE ESTADO ENTREGA ===")

    def _crear_actualizar_repuestos(self):
        _logger.info("=== INICIO CREAR/ACTUALIZAR REPUESTOS ===")
        for order in self:
            _logger.info(f"Procesando orden: {order.name}")
            _logger.info(f"Cliente: {order.partner_id.name}")
            _logger.info(f"Equipo: {order.equipo_id.name if order.equipo_id else 'No definido'}")
            
            if not order.order_line:
                _logger.warning(f"La orden {order.name} no tiene líneas")
                continue
                
            _logger.info(f"Número de líneas a procesar: {len(order.order_line)}")
            
            for line in order.order_line:
                _logger.info(f"=== Procesando línea ID: {line.id} ===")
                _logger.info(f"Producto: {line.product_template_id.name}")
                _logger.info(f"Cantidad: {line.product_uom_qty}")
                
                try:
                    RepuestosAlquiler = self.env['repuestos.alquiler'].sudo()
                    _logger.info("Buscando repuesto existente...")
                    
                    repuesto = RepuestosAlquiler.search([
                        ('codigo_id', '=', str(line.id))
                    ], limit=1)
                    
                    _logger.info(f"Repuesto existente encontrado: {bool(repuesto)}")
                    
                    vals_repuesto = {
                        'referencia_reparacion_id': order.name,
                        'serie_id': order.equipo_id.serie if order.equipo_id else False,
                        'modelo_id': order.equipo_id.id if order.equipo_id else False,
                        'cliente_id': order.partner_id.name,
                        'cantidad': line.product_uom_qty,
                        'contometro_actual': line.contometro or '0',
                        'contometro_ultimo': line.contometroa or '0',
                        'solicitante_id': order.solicitante_id.name if order.solicitante_id else False,
                        'name': line.product_template_id.name,
                        'codigo_id': str(line.id),
                    }
                    
                    _logger.info("Valores a guardar:")
                    for key, value in vals_repuesto.items():
                        _logger.info(f"{key}: {value}")
                    
                    if not repuesto:
                        _logger.info("Creando nuevo repuesto...")
                        new_repuesto = RepuestosAlquiler.create(vals_repuesto)
                        _logger.info(f"Repuesto creado con ID: {new_repuesto.id}")
                    else:
                        _logger.info(f"Actualizando repuesto existente ID: {repuesto.id}")
                        repuesto.write(vals_repuesto)
                        _logger.info("Repuesto actualizado exitosamente")
                        
                except Exception as e:
                    _logger.error(f"ERROR procesando línea {line.id}:")
                    _logger.error(f"Tipo de error: {type(e).__name__}")
                    _logger.error(f"Descripción: {str(e)}")
                    _logger.error("Traceback completo:", exc_info=True)
                
                _logger.info(f"=== Fin procesamiento línea {line.id} ===")
            
            _logger.info(f"Finalizado procesamiento de orden {order.name}")
        
        _logger.info("=== FIN CREAR/ACTUALIZAR REPUESTOS ===")


    def write(self, vals):
        res = super(SaleOrderInherit, self).write(vals)
        
        if vals.get('state') == 'sale':
            self._crear_actualizar_ticket()
        
        return res

    def _crear_actualizar_ticket(self):
        _logger.info("=== INICIO CREAR/ACTUALIZAR TICKET ===")
        
        for order in self:
            if order.tipo_pedido == "normal":
                try:
                    TicketAlquiler = self.env['ticket.alquiler'].sudo()
                    ticket = TicketAlquiler.search([('codigo_id', '=', order.id)], limit=1)
                    
                    vals_ticket = {
                        'codigo_id': order.id,
                        'product_alquiler': order.equipo_id.id,
                        'partner_id': order.equipo_id.cliente_id.id,
                        'description': f"Cambiar repuestos según numero de pedido # {order.name}",
                        'direccion_id_r': order.equipo_id.direccion,
                        'contacto_id_r': order.equipo_id.contacto_id,
                        'tipo_servicio_id': 'cambio_repuestos'
                    }
                    
                    if not ticket:
                        _logger.info("Creando nuevo ticket...")
                        new_ticket = TicketAlquiler.create(vals_ticket)
                        _logger.info(f"Ticket creado con ID: {new_ticket.id}")
                    else:
                        _logger.info(f"Actualizando ticket existente ID: {ticket.id}")
                        ticket.write(vals_ticket)
                        _logger.info("Ticket actualizado exitosamente")
                        
                except Exception as e:
                    _logger.error(f"ERROR procesando ticket para orden {order.name}:")
                    _logger.error(f"Tipo de error: {type(e).__name__}")
                    _logger.error(f"Descripción: {str(e)}")
                    _logger.error("Traceback completo:", exc_info=True)
        
        _logger.info("=== FIN CREAR/ACTUALIZAR TICKET ===")

    def compute_count_repuestos_pedidos(self):
        _logger.info("Calculando conteo de repuestos")
        for record in self:
            count = self.env['repuestos.alquiler'].search_count([('modelo_id', '=', record.equipo_id.id)])
            _logger.info(f"Repuestos encontrados para equipo {record.equipo_id.name}: {count}")
            record.repuestos_count_pedidos = count

    def compute_count_ticket(self):
        _logger.info("Calculando conteo de tickets")
        for record in self:
            count = self.env['ticket.alquiler'].search_count([('product_alquiler', '=', record.equipo_id.id)])
            _logger.info(f"Tickets encontrados para equipo {record.equipo_id.name}: {count}")
            record.ticket_count_ticket = count

    def get_repuestos_pedidos(self):
        _logger.info(f"Obteniendo repuestos para equipo: {self.equipo_id.name}")
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
        _logger.info(f"Obteniendo tickets para equipo: {self.equipo_id.name}")
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tickets_pedidos',
            'view_mode': 'list,form',
            'res_model': 'ticket.alquiler',
            'domain': [('product_alquiler', '=', self.equipo_id.id)],
            'context': "{'create': False}"
        }