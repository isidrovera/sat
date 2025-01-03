from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class CustomerSearchController(http.Controller):

    @http.route('/api/customer_search', auth='public', type='json', methods=['POST'])
    def customer_search(self, **kwargs):
        name_part = kwargs.get('name')
        if not name_part:
            _logger.error("El parámetro 'name' es requerido pero no fue proporcionado.")
            return {'error': 'El parámetro "name" es requerido'}

        try:
            # Buscar los clientes cuyo nombre coincida parcialmente
            _logger.info(f"Buscando clientes con nombre que contiene: {name_part}")
            clientes = request.env['res.partner'].sudo().search([('name', 'ilike', name_part)])
            _logger.info(f"Se encontraron {len(clientes)} clientes.")

            if not clientes:
                _logger.warning(f"No se encontraron clientes con el nombre que contiene: {name_part}")
                return {'message': 'No se encontraron clientes'}

            # Buscar registros de alquiler asociados con estos clientes
            registros = request.env['alquiler'].sudo().search([('cliente_id', 'in', clientes.ids)])
            _logger.info(f"Se encontraron {len(registros)} registros de alquiler para los clientes.")

            if not registros:
                _logger.warning(f"No se encontraron registros de alquiler para el/los cliente(s) con nombre que contiene: {name_part}")
                return {'message': 'No se encontraron registros de alquiler para este cliente'}

            # Se redirige al primer cliente encontrado
            cliente_id = clientes[0].id
            base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
            customer_url = f"{base_url}/customer/records?customer_id={cliente_id}"
            
            _logger.info(f"Devolviendo URL: {customer_url}")
            return {'url': customer_url}

        except Exception as e:
            _logger.error(f"Ocurrió un error al buscar el cliente: {str(e)}", exc_info=True)
            return {'error': 'Ocurrió un error inesperado'}
class CustomerRecordsController(http.Controller):

    @http.route('/customer/records', auth='public', type='http', website=True)
    def show_customer_records(self, customer_id=None, user_name=None, phone_number=None):
        if not customer_id:
            return request.render('sat.pagina_error', {})

        try:
            registros = request.env['alquiler'].sudo().search([('cliente_id', '=', int(customer_id))])

            if not registros:
                return request.render('sat.pagina_sin_registros', {
                    'cliente': request.env['res.partner'].sudo().browse(int(customer_id)).name,
                    'user_name': user_name,
                    'phone_number': phone_number
                })

            return request.render('sat.customer_records_page', {
                'registros': registros,
                'cliente': request.env['res.partner'].sudo().browse(int(customer_id)).name,
                'user_name': user_name,
                'phone_number': phone_number
            })

        except Exception as e:
            _logger.error(f"An error occurred while displaying customer records: {str(e)}", exc_info=True)
            return request.render('sat.pagina_error', {})