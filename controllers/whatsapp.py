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
        _logger.info(
            f"[customer/records] === INICIO === "
            f"customer_id={customer_id} | user_name={user_name} | phone_number={phone_number}"
        )

        if not customer_id:
            _logger.warning("[customer/records] No se recibió customer_id, renderizando pagina_error")
            return request.render('sat.pagina_error', {})

        try:
            cliente_id_int = int(customer_id)
            _logger.info(f"[customer/records] Buscando alquileres para cliente_id={cliente_id_int}")

            registros = request.env['alquiler'].sudo().search([('cliente_id', '=', cliente_id_int)])
            _logger.info(f"[customer/records] Registros encontrados: {len(registros)}")

            # Log detallado de cada registro para detectar campos vacíos o inconsistentes
            for r in registros:
                try:
                    name_val = r.name
                    name_type = type(name_val).__name__
                    name_inner = getattr(name_val, 'name', 'NO TIENE .name')
                    estado = getattr(r, 'estado_alquiler_id', 'NO EXISTE CAMPO')
                    _logger.info(
                        f"[customer/records] alquiler id={r.id} | "
                        f"name={name_val!r} (type={name_type}) | "
                        f"name.name={name_inner!r} | "
                        f"serie={r.serie!r} | "
                        f"ubicacion_instalacion={r.ubicacion_instalacion!r} | "
                        f"estado_alquiler_id={estado!r}"
                    )
                except Exception as e_log:
                    _logger.error(
                        f"[customer/records] Error leyendo campos del alquiler id={r.id}: {str(e_log)}",
                        exc_info=True
                    )

            cliente_name = request.env['res.partner'].sudo().browse(cliente_id_int).name
            _logger.info(f"[customer/records] Cliente resuelto: {cliente_name!r}")

            if not registros:
                _logger.info(f"[customer/records] Sin registros, renderizando pagina_sin_registros")
                return request.render('sat.pagina_sin_registros', {
                    'cliente': cliente_name,
                    'user_name': user_name,
                    'phone_number': phone_number
                })

            _logger.info(f"[customer/records] Renderizando customer_records_page con {len(registros)} registros")
            return request.render('sat.customer_records_page', {
                'registros': registros,
                'cliente': cliente_name,
                'user_name': user_name,
                'phone_number': phone_number
            })

        except Exception as e:
            _logger.error(
                f"[customer/records] ERROR cliente_id={customer_id}: {str(e)}",
                exc_info=True
            )
            return request.render('sat.pagina_error', {})