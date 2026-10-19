
# -*- coding: utf-8 -*-

import json
import logging

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class GraficoController(http.Controller):

    def _json_response(self, data, status=200):
        return request.make_response(
            json.dumps(data, ensure_ascii=False, default=str),
            headers=[
                ('Content-Type', 'application/json; charset=utf-8'),
                ('Cache-Control', 'no-store'),
            ],
            status=status,
        )

    @http.route(
        '/generar/grafico',
        type='http',
        auth='user',
        website=True,
        methods=['GET'],
    )
    def mostrar_pagina_grafico(self, **kwargs):
        _logger.info("[GRAFICOS] Renderizando página de gráficos")

        return request.render(
            'sat.template_graficos_dinamicos'
        )

    @http.route(
        '/api/grafico/datos',
        type='jsonrpc',
        auth='user',
        methods=['POST'],
    )
    def obtener_datos_grafico(self, **post):
        try:
            modelo = post.get('modelo')
            fecha_inicio = post.get('fecha_inicio')
            fecha_fin = post.get('fecha_fin')
            campos = post.get('campos')

            _logger.info(
                "[GRAFICOS] Consultando modelo=%s inicio=%s fin=%s campos=%s",
                modelo,
                fecha_inicio,
                fecha_fin,
                campos,
            )

            if not modelo or not fecha_inicio or not fecha_fin or not campos:
                return {
                    'error': 'Faltan parámetros obligatorios.'
                }

            if not isinstance(campos, list) or not campos:
                return {
                    'error': 'Debe indicar una lista de campos.'
                }

            if modelo not in request.env:
                return {
                    'error': 'El modelo solicitado no existe.'
                }

            Model = request.env[modelo]

            campo = campos[0]

            if campo not in Model._fields:
                return {
                    'error': 'El campo solicitado no existe.'
                }

            field = Model._fields[campo]

            if field.type not in ('integer', 'float', 'monetary'):
                return {
                    'error': 'El campo debe ser numérico.'
                }

            dominio = [
                ('create_date', '>=', fecha_inicio),
                ('create_date', '<=', fecha_fin),
            ]

            registros = Model.search(dominio)

            etiquetas = []
            datos = []

            for registro in registros:
                etiquetas.append(
                    str(registro.create_date or '')
                )

                valor = registro[campo]

                datos.append(
                    float(valor or 0)
                )

            _logger.info(
                "[GRAFICOS] Consulta completada modelo=%s registros=%s",
                modelo,
                len(registros),
            )

            return {
                'labels': etiquetas,
                'datasets': [
                    {
                        'label': modelo,
                        'data': datos,
                    }
                ],
            }

        except Exception:
            _logger.exception(
                "[GRAFICOS] Error obteniendo datos del gráfico"
            )

            return {
                'error': 'No se pudieron obtener los datos del gráfico.'
            }

    @http.route(
        '/api/modelos',
        type='http',
        auth='user',
        methods=['GET'],
    )
    def get_modelos(self, **kwargs):
        try:
            _logger.info("[GRAFICOS] Consultando modelos")

            modelos = request.env['ir.model'].search([])

            result = []

            for modelo in modelos:
                if modelo.model not in request.env:
                    continue

                Model = request.env[modelo.model]

                if not Model.check_access('read', raise_exception=False):
                    continue

                result.append({
                    'model': modelo.model,
                    'name': modelo.name,
                })

            return self._json_response(result)

        except Exception:
            _logger.exception(
                "[GRAFICOS] Error consultando modelos"
            )

            return self._json_response(
                {'error': 'No se pudieron consultar los modelos.'},
                status=500,
            )

    @http.route(
        '/api/campos',
        type='http',
        auth='user',
        methods=['GET'],
    )
    def get_campos(self, **kwargs):
        try:
            modelo = kwargs.get('modelo')

            if not modelo or modelo not in request.env:
                return self._json_response(
                    {'error': 'Modelo no válido.'},
                    status=400,
                )

            Model = request.env[modelo]

            if not Model.check_access('read', raise_exception=False):
                return self._json_response(
                    {'error': 'Acceso denegado.'},
                    status=403,
                )

            campos = request.env['ir.model.fields'].search([
                ('model', '=', modelo),
            ])

            result = []

            for campo in campos:
                if campo.name not in Model._fields:
                    continue

                field = Model._fields[campo.name]

                if field.type not in (
                    'integer',
                    'float',
                    'monetary',
                ):
                    continue

                result.append({
                    'field': campo.name,
                    'name': campo.field_description,
                })

            _logger.info(
                "[GRAFICOS] Campos consultados modelo=%s total=%s",
                modelo,
                len(result),
            )

            return self._json_response(result)

        except Exception:
            _logger.exception(
                "[GRAFICOS] Error consultando campos"
            )

            return self._json_response(
                {'error': 'No se pudieron consultar los campos.'},
                status=500,
            )
