from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class SatController(http.Controller):

    @http.route('/sat/change_location/<int:record_id>', type='http', auth='public')
    def change_location(self, record_id, **kwargs):
        _logger.info(f"Request received to change location for record ID: {record_id}")
        record = request.env['sat.sat'].browse(record_id)
        if record.exists():
            _logger.info(f"Record found: {record.name} with current location {record.ubicacion_id}")
            record.ubicacion_id = 'primer_piso'
            _logger.info(f"Location changed to 'primer_piso' for record ID: {record_id}")
            return request.render('sat.location_change_success', {'record': record})
        else:
            _logger.error(f"Record with ID {record_id} not found")
            return request.not_found()
