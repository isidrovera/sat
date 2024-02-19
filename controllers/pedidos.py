from odoo import http
from odoo.http import request
import base64
import logging

_logger = logging.getLogger(__name__)

class SaleOrderController(http.Controller):
    @http.route('/order/create_order', type='http', auth="public", methods=['GET'], website=True)
    def display_create_order_form(self, **kw):
        id_registro = kw.get('id_registro')
        registro = request.env['alquiler'].sudo().search([('id', '=', int(id_registro))])
        
        # Asumiendo que los campos necesarios son similares a los usados en el ticket
        values = {
            'partner_id': registro.cliente_id.id if registro.cliente_id else '',
            'celular': registro.celular if registro.celular else '',
            # Supongamos que aquí necesitas pasar más información relevante para el pedido
            'nombre': registro.nombre if registro.nombre else '',  # Ejemplo de campo adicional
            'product_id': registro.producto_id.id if registro.producto_id else '',  # ID del producto
            # Agrega aquí los campos 'contometro black' y 'contometro color' si están disponibles en 'registro'
        }
        
        # Asegúrate de cambiar 'tu_modulo.sale_order_form' por la ruta correcta a tu formulario
        return request.render('sat.sale_order_form', values)

    @http.route('/order/submit_order', type='http', auth="public", methods=['POST'], website=True)
    def submit_create_order(self, **post):
        try:
            # Manejo de la carga de archivo para la foto, si es aplicable
            file_base64 = None
            if 'foto' in post:  # Asumiendo que el campo se llama 'foto'
                file_storage = post['foto']
                if file_storage:
                    file_content = file_storage.read()
                    file_base64 = base64.b64encode(file_content).decode('utf-8')
            
            # Aquí se construyen los valores para crear el pedido de venta
            order_vals = {
                'partner_id': int(post.get('partner_id')),
                'order_line': [
                    (0, 0, {
                        'product_id': int(post.get('product_id')),
                        'name': post.get('nombre'),  # Nombre/descripción del producto
                        'product_uom_qty': 1,  # Cantidad, ajustar según necesidad
                        # Añade más campos a la línea de pedido si es necesario
                    })
                ],
                # Suponiendo que tienes campos personalizados para celular, foto, etc. en 'sale.order'
                'celular_cliente': post.get('celular'),
                'foto_cliente': file_base64,
                # Asegúrate de añadir los campos 'contometro_black' y 'contometro_color' aquí si son necesarios
            }
            
            # Creando el pedido de venta
            request.env['sale.order'].sudo().create(order_vals)
            return request.redirect('/pagina_confirmacion')
        except Exception as e:
            _logger.exception("Failed to create sale order: %s", e)
            return request.render('tu_modulo.error_page', {'error': str(e)})