from odoo import http
from odoo.http import request

class SatController(http.Controller):

    @http.route('/sat/change_location/<int:record_id>', type='http', auth='user')
    def change_location(self, record_id, **kwargs):
        record = request.env['sat.sat'].browse(record_id)
        if record.exists():
            record.ubicacion_id = 'primer_piso'
            return request.render('sat.location_change_success', {'record': record})
        else:
            return request.not_found()
