from odoo import http
from odoo.http import request

class CorsMiddleware(http.Controller):

    @http.route('/api/<path:path>', type='http', auth='public', methods=['OPTIONS'], csrf=False)
    def options(self, path):
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization'
        }
        return request.make_response('OK', headers=headers)
