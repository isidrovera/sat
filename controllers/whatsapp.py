from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class CustomerSearchController(http.Controller):

    @http.route('/api/customer_search', auth='public', type='json', methods=['POST'])
    def customer_search(self, **kwargs):
        name_part = kwargs.get('name')
        if not name_part:
            _logger.error("Name parameter is required but not provided.")
            return {'error': 'Name parameter is required'}

        try:
            # Buscar los clientes cuyo nombre coincida parcialmente
            _logger.info(f"Searching for customers with name part: {name_part}")
            clientes = request.env['res.partner'].sudo().search([('name', 'ilike', name_part)])
            _logger.info(f"Found {len(clientes)} customers.")

            if not clientes:
                _logger.warning(f"No customers found with the name part: {name_part}")
                return {'message': 'No customers found'}

            # Buscar registros de alquiler asociados con estos clientes
            registros = request.env['alquiler'].sudo().search([('cliente_id', 'in', clientes.ids)])
            _logger.info(f"Found {len(registros)} rental records for the customers.")

            if not registros:
                _logger.warning(f"No rental records found for the customer(s) with name part: {name_part}")
                return {'message': 'No rental records found for this customer'}

            # Suponiendo que rediriges al primer cliente encontrado
            cliente_id = clientes[0].id
            base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
            customer_url = f"{base_url}/customer/records?customer_id={cliente_id}"
            
            _logger.info(f"Returning URL: {customer_url}")
            return {'url': customer_url}

        except Exception as e:
            _logger.error(f"An error occurred while searching for customer: {str(e)}", exc_info=True)
            return {'error': 'An unexpected error occurred'}
class CustomerRecordsController(http.Controller):

    @http.route('/customer/records', auth='public', type='http', website=True)
    def show_customer_records(self, customer_id=None):
        if not customer_id:
            _logger.error("Customer ID not provided.")
            return request.render('sat.pagina_error', {})

        try:
            _logger.info(f"Fetching rental records for customer ID: {customer_id}")
            registros = request.env['alquiler'].sudo().search([('cliente_id', '=', int(customer_id))])

            if not registros:
                _logger.warning(f"No rental records found for customer ID: {customer_id}")
                return request.render('sat.pagina_sin_registros', {'cliente': request.env['res.partner'].sudo().browse(int(customer_id)).name})

            _logger.info(f"Found {len(registros)} rental records for customer ID: {customer_id}")
            return request.render('sat.customer_records_page', {
                'registros': registros,
                'cliente': request.env['res.partner'].sudo().browse(int(customer_id)).name
            })

        except Exception as e:
            _logger.error(f"An error occurred while displaying customer records for ID {customer_id}: {str(e)}", exc_info=True)
            return request.render('sat.pagina_error', {})
