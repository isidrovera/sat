from odoo import http
from odoo.http import request
import json

class InspeccionController(http.Controller):
    @http.route('/inspeccion/sitio', type='http', auth='public', website=True)
    def formulario_inspeccion(self, token):
        alquiler = request.env['alquiler'].sudo().search([('token_inspeccion', '=', token)], limit=1)
        if not alquiler:
            return request.render('sat.inspeccion_error')
        return request.render('sat.inspeccion_formulario', {
            'alquiler': alquiler
        })

    @http.route('/inspeccion/submit', type='http', auth='public', methods=['POST'], csrf=False)
    def submit_inspeccion(self, **post):
        alquiler = request.env['alquiler'].sudo().search([
            ('token_inspeccion', '=', post.get('token'))
        ], limit=1)
        if not alquiler:
            return json.dumps({'error': 'Token inválido'})

        try:
            resultado = request.env['inspeccion.resultado'].sudo().create({
                'alquiler_id': alquiler.id,
                'punto_corriente': post.get('punto_corriente'),
                'voltaje': float(post.get('voltaje', 0)),
                'punto_red': post.get('punto_red'),
                'wifi': post.get('wifi'),
                'piso': int(post.get('piso', 0)),
                'ascensor': bool(post.get('ascensor')),
                'espacio': float(post.get('espacio', 0)),
                'ancho_pasillo': float(post.get('ancho_pasillo', 0)),
                'observaciones': post.get('observaciones'),
            })
            return json.dumps({'success': True})
        except Exception as e:
            return json.dumps({'error': str(e)})