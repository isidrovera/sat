# En tu módulo, por ejemplo en my_module/controllers/main.py
from odoo import http
from odoo.http import request

class GraficoController(http.Controller):
    @http.route('/generar/grafico', type='http', auth='user', website=True)
    def mostrar_pagina_grafico(self, **kwargs):
        return request.render('sat.template_graficos_dinamicos')

    @http.route('/api/grafico/datos', type='json', auth='user', methods=['POST'])
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
