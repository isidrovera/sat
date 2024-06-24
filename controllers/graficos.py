from odoo import http
from odoo.http import request

class GraficoController(http.Controller):
    @http.route('/generar/grafico', type='http', auth='user', website=True)
    def mostrar_pagina_grafico(self, **kwargs):
        return request.render('sat.template_graficos_dinamicos')

    @http.route('/api/grafico/datos', type='json', auth='public', methods=['POST'])
    def obtener_datos_grafico(self, **post):
        modelo = post.get('modelo')
        fecha_inicio = post.get('fecha_inicio')
        fecha_fin = post.get('fecha_fin')
        campos = post.get('campos')

        Model = request.env[modelo]
        dominio = [('create_date', '>=', fecha_inicio), ('create_date', '<=', fecha_fin)]
        registros = Model.search(dominio)
        etiquetas = [getattr(r, 'name', 'Sin Nombre') for r in registros]  # Ajustar según el campo relevante
        datos = [getattr(r, campos[0], 0) for r in registros]  # Asumiendo un solo campo

        return {'labels': etiquetas, 'datasets': [{'label': modelo, 'data': datos}]}

    @http.route('/api/modelos', type='json', auth='public', methods=['GET'])
    def get_modelos(self):
        modelos = request.env['ir.model'].search([])
        return [{'model': m.model, 'name': m.name} for m in modelos]

    @http.route('/api/campos', type='json', auth='public', methods=['GET'])
    def get_campos(self, modelo):
        campos = request.env['ir.model.fields'].search([('model', '=', modelo)])
        return [{'field': c.name, 'name': c.field_description} for c in campos]
