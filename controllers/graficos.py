import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class GraficoController(http.Controller):
    @http.route('/generar/grafico', type='http', auth='public', website=True)
    def mostrar_pagina_grafico(self, **kwargs):
        _logger.info("Rendering gráficos dinámicos template")
        return request.render('sat.template_graficos_dinamicos')

    @http.route('/api/grafico/datos', type='json', auth='public', methods=['POST'])
    def obtener_datos_grafico(self, **post):
        try:
            _logger.info("Request data for grafico: %s", json.dumps(post))
            modelo = post.get('modelo')
            fecha_inicio = post.get('fecha_inicio')
            fecha_fin = post.get('fecha_fin')
            campos = post.get('campos')

            Model = request.env[modelo]
            dominio = [('create_date', '>=', fecha_inicio), ('create_date', '<=', fecha_fin)]
            registros = Model.search(dominio)
            etiquetas = [getattr(r, 'name', 'Sin Nombre') for r in registros]  # Ajustar según el campo relevante
            datos = [getattr(r, campos[0], 0) for r in registros]  # Asumiendo un solo campo

            _logger.info("Data prepared for grafico: labels=%s, datasets=%s", etiquetas, datos)
            return {'labels': etiquetas, 'datasets': [{'label': modelo, 'data': datos}]}
        except Exception as e:
            _logger.error("Error in obtener_datos_grafico: %s", str(e))
            return {'error': str(e)}

    @http.route('/api/modelos', type='json', auth='public', methods=['GET'])
    def get_modelos(self):
        try:
            _logger.info("Fetching modelos")
            modelos = request.env['ir.model'].search([])
            result = [{'model': m.model, 'name': m.name} for m in modelos]
            _logger.info("Modelos fetched: %s", json.dumps(result))
            return result
        except Exception as e:
            _logger.error("Error in get_modelos: %s", str(e))
            return {'error': str(e)}

    @http.route('/api/campos', type='json', auth='public', methods=['GET'])
    def get_campos(self, modelo):
        try:
            _logger.info("Fetching campos for modelo: %s", modelo)
            campos = request.env['ir.model.fields'].search([('model', '=', modelo)])
            result = [{'field': c.name, 'name': c.field_description} for c in campos]
            _logger.info("Campos fetched: %s", json.dumps(result))
            return result
        except Exception as e:
            _logger.error("Error in get_campos: %s", str(e))
            return {'error': str(e)}
