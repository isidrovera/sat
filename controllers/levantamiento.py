from odoo import http
from odoo.http import request
import werkzeug

class InspeccionController(http.Controller):

    @http.route(['/inspeccion/<string:token>'], type='http', auth='public', website=True)
    def formulario_inspeccion(self, token):
        alquiler = request.env['alquiler'].sudo().search([('token', '=', token)], limit=1)
        if not alquiler:
            return request.not_found()
        return request.render('mi_modulo.formulario_inspeccion_template', {
            'alquiler': alquiler
        })

    @http.route(['/inspeccion/submit'], type='http', auth='public', methods=['POST'], website=True, csrf=False)
    def submit_inspeccion(self, **post):
        alquiler = request.env['alquiler'].sudo().search([('token', '=', post.get('token'))], limit=1)
        if not alquiler:
            return request.not_found()
        
        vals = {
            'alquiler_id': alquiler.id,
            'punto_corriente': post.get('punto_corriente'),
            'voltaje': float(post.get('voltaje', 0)),
            'punto_tierra': post.get('punto_tierra') == 'true',
            'resistencia_tierra': float(post.get('resistencia_tierra', 0)),
            'punto_red': post.get('punto_red'),
            'wifi': post.get('wifi'),
            'piso': int(post.get('piso', 0)),
            'ascensor': post.get('ascensor') == 'true',
            'espacio': float(post.get('espacio', 0)),
            'ancho_pasillo': float(post.get('ancho_pasillo', 0)),
            'observaciones': post.get('observaciones')
        }
        
        resultado = request.env['inspeccion.resultado'].sudo().create(vals)
        return werkzeug.utils.redirect('/inspeccion/gracias')