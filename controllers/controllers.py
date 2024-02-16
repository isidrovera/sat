from odoo import http
from odoo.http import request
import json
import logging
from datetime import date


class AlquilerQRController(http.Controller):
    @http.route('/api/escanear_qr', auth='public', type='http', methods=['GET'], website=True)
    def escanear_qr(self, id_registro=None):
        if not id_registro:
            return request.redirect('/pagina_error')
        
        registro = request.env['alquiler'].sudo().search([('id', '=', int(id_registro))])
        if not registro:
            return request.redirect('/pagina_error')

        # Aquí se podrían agregar más datos según sea necesario
        datos_registro = {
            'id': registro.id,
            'modelo_maquina': registro.name.name,
            'serie': registro.serie,
            'cliente': registro.cliente_id.name,
        }
        
        # Redirigir a la página con opciones, pasando los datos_registro como contexto
        return request.render('sat.pagina_con_opciones', {'datos_registro': datos_registro})
    


class PublicTicketController(http.Controller):
    # Ruta GET para mostrar el formulario
    @http.route('/ticket/reportar_incidencia', type='http', auth="public", methods=['GET'], website=True, csrf=False)
    def display_reportar_incidencia(self, **kw):
        # Obtener datos necesarios para prellenar el formulario o cualquier otra lógica
        values = {
            # Suponiendo que hay lógica para obtener estos valores
            'partner_id': ...,  # ID del cliente
            'direccion': ...,   # Dirección
            'contacto_id': ..., # ID de contacto
            'celular': ...,     # Número de celular
            'correo': ...,      # Correo electrónico
            'product_id': ...,  # ID del producto
        }
        return request.render('sat.reportar_incidencia_form', values)

    # Ruta POST para procesar el formulario
   # Asumiendo que las rutas son las mismas que las anteriores

    # Ruta POST para procesar el formulario
    @http.route('/ticket/reportar_incidencia', type='http', auth="public", methods=['POST'], website=True)
    def submit_reportar_incidencia(self, **post):
        try:
            ticket_vals = {
                'partner_id': int(post.get('partner_id')),
                'direccion_id_r': post.get('direccion'),
                'contacto_id_r': post.get('contacto_id'),
                'celular_id_r': post.get('celular'),
                'corre_id_r': post.get('correo'),
                'product_alquiler': int(post.get('product_id')),
                'description': post.get('description'),
            }
            # Crear el ticket
            request.env['ticket.alquiler'].sudo().create(ticket_vals)
            return request.redirect('/pagina_confirmacion')
        except Exception as e:
            # Log the error and redirect to an error page
            _logger.exception("Failed to create ticket: %s", e)
            return request.render('sat.error_page', {'error': str(e)})


class AlquilerAPI(http.Controller):
    @http.route('/api/alquiler/<int:alquiler_id>', auth='public', methods=['GET'], type='json')
    def get_alquiler_data(self, alquiler_id):
        record = request.env['alquiler'].sudo().browse(alquiler_id)
        if record.exists():
            return {
                'id': record.id,
                'modelo_maquina': record.name.name,
                'serie': record.serie,
                # Agrega todos los campos necesarios aquí
            }
        return {'error': 'Registro no encontrado'}
    
class AlquilerAPI(http.Controller):
    @http.route('/api/alquiler/ticket', auth='user', methods=['POST'], type='json')
    def create_alquiler_ticket(self, **post):
        # Aquí debes asegurarte de validar los datos y manejar errores correctamente.
        new_ticket = request.env['ticket.alquiler'].sudo().create(post)
        return {'success': True, 'ticket_id': new_ticket.id}

class AlquilerAPI(http.Controller):
    @http.route('/api/alquiler/repuestos/<int:alquiler_id>', auth='user', methods=['GET'], type='json')
    def list_alquiler_repuestos(self, alquiler_id):
        repuestos = request.env['repuestos.alquiler'].sudo().search([('alquiler_id', '=', alquiler_id)])
        repuestos_data = [{'id': repuesto.id, 'name': repuesto.name} for repuesto in repuestos]
        return {'repuestos': repuestos_data}
    
class AlquilerAPI(http.Controller):
    @http.route('/api/alquiler/pedido', auth='user', methods=['POST'], type='json')
    def create_sale_order(self, **post):
        # Crear el pedido de venta
        sale_order = request.env['sale.order'].sudo().create(post)
        
        # Enviar correo electrónico (esto es solo un esquema, necesitarás una plantilla de correo real)
        template = request.env.ref('tu_modulo.email_template_nuevo_pedido')
        if template:
            template.sudo().send_mail(sale_order.id, force_send=True)
        
        # Devolver la respuesta
        return {'success': True, 'order_id': sale_order.id}
