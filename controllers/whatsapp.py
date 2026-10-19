
# -*- coding: utf-8 -*-

import logging

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class CustomerSearchController(http.Controller):

    @http.route(
        '/api/customer_search',
        auth='user',
        type='jsonrpc',
        methods=['POST'],
    )
    def customer_search(self, **kwargs):
        name_part = (kwargs.get('name') or '').strip()

        if not name_part:
            _logger.warning(
                "[CUSTOMER SEARCH] No se recibió el parámetro name."
            )
            return {
                'error': 'El parámetro "name" es requerido'
            }

        try:
            _logger.info(
                "[CUSTOMER SEARCH] Buscando clientes."
            )

            clientes = request.env['res.partner'].search(
                [('name', 'ilike', name_part)],
                limit=100,
            )

            if not clientes:
                return {
                    'message': 'No se encontraron clientes'
                }

            registros = request.env['alquiler'].search(
                [('cliente_id', 'in', clientes.ids)],
                limit=1,
            )

            if not registros:
                return {
                    'message': (
                        'No se encontraron registros de alquiler '
                        'para este cliente'
                    )
                }

            cliente_id = registros.cliente_id.id

            customer_url = (
                f"/customer/records?customer_id={cliente_id}"
            )

            _logger.info(
                "[CUSTOMER SEARCH] Cliente encontrado ID=%s",
                cliente_id,
            )

            return {
                'url': customer_url
            }

        except Exception:
            _logger.exception(
                "[CUSTOMER SEARCH] Error buscando clientes."
            )
            return {
                'error': 'Ocurrió un error inesperado'
            }


class CustomerRecordsController(http.Controller):

    @http.route(
        '/customer/records',
        auth='user',
        type='http',
        website=True,
        methods=['GET'],
    )
    def show_customer_records(
        self,
        customer_id=None,
        user_name=None,
        phone_number=None,
        **kwargs
    ):
        _logger.info(
            "[CUSTOMER RECORDS] Inicio customer_id=%s",
            customer_id,
        )

        if not customer_id:
            return request.render(
                'sat.pagina_error',
                {}
            )

        try:
            cliente_id_int = int(customer_id)

            cliente = request.env['res.partner'].browse(
                cliente_id_int
            ).exists()

            if not cliente:
                return request.render(
                    'sat.pagina_error',
                    {}
                )

            registros = request.env['alquiler'].search(
                [
                    ('cliente_id', '=', cliente.id),
                ]
            )

            _logger.info(
                "[CUSTOMER RECORDS] Cliente ID=%s equipos=%s",
                cliente.id,
                len(registros),
            )

            if not registros:
                return request.render(
                    'sat.pagina_sin_registros',
                    {
                        'cliente': cliente.name,
                        'user_name': user_name,
                        'phone_number': phone_number,
                    }
                )

            return request.render(
                'sat.customer_records_page',
                {
                    'registros': registros,
                    'cliente': cliente.name,
                    'user_name': user_name,
                    'phone_number': phone_number,
                }
            )

        except Exception:
            _logger.exception(
                "[CUSTOMER RECORDS] Error consultando equipos."
            )

            return request.render(
                'sat.pagina_error',
                {}
            )
