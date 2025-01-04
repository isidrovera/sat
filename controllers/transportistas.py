from odoo import http
from odoo.http import request
import logging
from datetime import datetime
import pytz

_logger = logging.getLogger(__name__)

class SatController(http.Controller):
    @http.route('/sat/change_location/<int:record_id>', type='http', auth='public', website=True)
    def change_location(self, record_id, token=None, **kwargs):
        # Verificar que se proporcionó un token
        if not token:
            return request.render('sat.location_change_error', {
                'error_message': 'No se proporcionó token de validación'
            })

        record = request.env['sat.sat'].sudo().browse(record_id)
        
        # Verificar que el registro existe
        if not record.exists():
            return request.render('sat.location_change_error', {
                'error_message': 'Registro no encontrado'
            })

        # Verificar que el token es válido
        if record.location_change_token != token:
            return request.render('sat.location_change_error', {
                'error_message': 'Token de validación inválido'
            })
            
        # Verificar que la ubicación no sea ya primer piso
        if record.ubicacion_id == 'primer_piso':
            return request.render('sat.location_already_changed', {})

        try:
            # Guardar la ubicación anterior
            old_location = record.ubicacion_id
            
            # Actualizar la ubicación
            record.write({
                'ubicacion_id': 'primer_piso',
                'location_change_token': False  # Invalidar el token después de usarlo
            })
            
            # Registrar el cambio
            peru_tz = pytz.timezone('America/Lima')
            current_time = datetime.now(peru_tz).strftime('%Y-%m-%d %H:%M:%S')
            message = f"Ubicación cambiada de {old_location} a primer_piso el {current_time}"
            record.message_post(body=message)
            
            return request.render('sat.location_change_success', {})
            
        except Exception as e:
            _logger.error(f"Error al cambiar la ubicación: {str(e)}")
            return request.render('sat.location_change_error', {
                'error_message': 'Error al actualizar la ubicación'
            })
