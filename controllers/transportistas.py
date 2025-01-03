from odoo import http
from odoo.http import request
import logging
from datetime import datetime
import pytz

_logger = logging.getLogger(__name__)

class SatController(http.Controller):
    @http.route('/sat/change_location/<int:record_id>', type='http', auth='public', website=True)
    def change_location(self, record_id, **kwargs):
        record = request.env['sat.sat'].sudo().browse(record_id)
        if not record.exists():
            return request.render('sat.location_change_error', {})

        if record.ubicacion_id == 'primer_piso':
            return request.render('sat.location_already_changed', {})

        old_location = record.ubicacion_id
        record.write({'ubicacion_id': 'primer_piso'})
        
        # Registrar el cambio
        peru_tz = pytz.timezone('America/Lima')
        current_time = datetime.now(peru_tz).strftime('%Y-%m-%d %H:%M:%S')
        message = f"Ubicación cambiada de {old_location} a primer_piso el {current_time}"
        record.message_post(body=message)
        
        return request.render('sat.location_change_success', {})
