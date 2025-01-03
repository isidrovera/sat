from odoo import http
from odoo.http import request
import logging
import pytz
from datetime import datetime

_logger = logging.getLogger(__name__)

class SatController(http.Controller):
    @http.route('/sat/change_location/<int:record_id>', type='http', auth='public', website=True)
    def change_location(self, record_id, **kwargs):
        record = request.env['sat.sat'].sudo().browse(record_id)
        if not record.exists():
            return request.not_found()
            
        old_location = record.ubicacion_id
        record.write({'ubicacion_id': 'primer_piso'})
        
        # Log cambio
        peru_tz = pytz.timezone('America/Lima')
        current_time = datetime.now(peru_tz).strftime('%Y-%m-%d %H:%M:%S')
        record.message_post(body=f"Ubicación cambiada de {old_location} a primer_piso el {current_time}")
        
        return request.render('sat.location_change_success', {})
