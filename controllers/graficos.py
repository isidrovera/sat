import json
import logging
from odoo import http
from odoo.http import request
from odoo.http import request
_logger = logging.getLogger(__name__)

class GraficoController(http.Controller):

    def _add_cors_headers(self, response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

    @http.route('/generar/grafico', type='http', auth='public', website=True)
    def mostrar_pagina_grafico(self, **kwargs):
        _logger.info("Rendering gráficos dinámicos template")
        response = request.render('sat.template_graficos_dinamicos')
        return self._add_cors_headers(response)

    @http.route('/api/grafico/datos', type='json', auth='public', methods=['POST'], csrf=False)
    def obtener_datos_grafico(self, **post):
        try:
            _logger.info("Request data for grafico: %s", json.dumps(post))
            modelo = post.get('modelo')
            fecha_inicio = post.get('fecha_inicio')
            fecha_fin = post.get('fecha_fin')
            campos = post.get('campos')

            _logger.info("Received params: modelo=%s, fecha_inicio=%s, fecha_fin=%s, campos=%s", modelo, fecha_inicio, fecha_fin, campos)

            if not modelo or not fecha_inicio or not fecha_fin or not campos:
                raise ValueError("Missing required parameters")

            Model = request.env[modelo]
            dominio = [('create_date', '>=', fecha_inicio), ('create_date', '<=', fecha_fin)]
            registros = Model.search(dominio)

            _logger.info("Registros encontrados: %s", registros)

            etiquetas = [str(r.create_date) for r in registros]  # Suponiendo que `create_date` es relevante
            datos = [getattr(r, campos[0], 0) for r in registros]  # Asumiendo un solo campo

            _logger.info("Data prepared for grafico: labels=%s, datasets=%s", etiquetas, datos)
            response_data = {'labels': etiquetas, 'datasets': [{'label': modelo, 'data': datos}]}
            response = request.make_response(json.dumps(response_data), headers={'Content-Type': 'application/json'})
            return self._add_cors_headers(response)
        except Exception as e:
            _logger.error("Error in obtener_datos_grafico: %s", str(e))
            response = request.make_response(json.dumps({'error': str(e)}), headers={'Content-Type': 'application/json'})
            return self._add_cors_headers(response)

    @http.route('/api/modelos', type='http', auth='public', methods=['GET'])
    def get_modelos(self):
        try:
            _logger.info("Fetching modelos")
            modelos = request.env['ir.model'].search([])
            result = [{'model': m.model, 'name': m.name} for m in modelos]
            _logger.info("Modelos fetched: %s", json.dumps(result))
            response = request.make_response(json.dumps(result), headers={'Content-Type': 'application/json'})
            return self._add_cors_headers(response)
        except Exception as e:
            _logger.error("Error in get_modelos: %s", str(e))
            response = request.make_response(json.dumps({'error': str(e)}), headers={'Content-Type': 'application/json'})
            return self._add_cors_headers(response)

    @http.route('/api/campos', type='http', auth='public', methods=['GET'])
    def get_campos(self, **kwargs):
        try:
            modelo = kwargs.get('modelo')
            _logger.info("Fetching campos for modelo: %s", modelo)
            campos = request.env['ir.model.fields'].search([('model', '=', modelo)])
            result = [{'field': c.name, 'name': c.field_description} for c in campos]
            _logger.info("Campos fetched: %s", json.dumps(result))
            response = request.make_response(json.dumps(result), headers={'Content-Type': 'application/json'})
            return self._add_cors_headers(response)
        except Exception as e:
            _logger.error("Error in get_campos: %s", str(e))
            response = request.make_response(json.dumps({'error': str(e)}), headers={'Content-Type': 'application/json'})
            return self._add_cors_headers(response)
class TicketAlquilerController(http.Controller):

    @http.route('/ticket/alquiler/chart_data', type='json', auth='user')
    def get_chart_data(self):
        tickets = request.env['ticket.alquiler'].search([])
        data = {
            'months': [],
            'counts': [],
        }

        # Suponiendo que quieres mostrar la cantidad de tickets por mes
        ticket_counts = {}
        for ticket in tickets:
            month = ticket.agenda.strftime('%Y-%m') if ticket.agenda else 'NA'
            if month not in ticket_counts:
                ticket_counts[month] = 0
            ticket_counts[month] += 1

        for month in sorted(ticket_counts.keys()):
            data['months'].append(month)
            data['counts'].append(ticket_counts[month])

        return data