from odoo import http
from odoo.http import request
import logging
from datetime import datetime
import pytz

_logger = logging.getLogger(__name__)

class SatController(http.Controller):
    @http.route('/sat/change_location/<int:record_id>', type='http', auth='public', website=True)
    def change_location(self, record_id, token=None, **kwargs):
        try:
            # Obtenemos el registro con sudo() para asegurar acceso
            record = request.env['sat.sat'].with_context(active_test=False).sudo().browse(record_id)
            
            # Verificación más detallada de la existencia del registro
            if not record.exists():
                _logger.error(f"Registro no encontrado: ID {record_id}")
                return request.render('sat.location_change_error', {
                    'error': 'No se encontró la máquina especificada'
                })
    
            # Verificación del token
            if not token or record.location_change_token != token:
                _logger.error(f"Token inválido para el registro {record_id}")
                return request.render('sat.location_change_error', {
                    'error': 'El enlace no es válido o ha expirado'
                })
    
            # Verificación del estado actual
            if record.ubicacion_id == 'primer_piso':
                return request.render('sat.location_already_changed', {
                    'message': 'La ubicación ya ha sido actualizada'
                })
    
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
            
            return request.render('sat.location_change_success', {
                'message': 'Ubicación actualizada correctamente'
            })
            
        except Exception as e:
            _logger.error(f"Error al procesar cambio de ubicación: {str(e)}")
            return request.render('sat.location_change_error', {
                'error': 'Error al procesar la solicitud'
            })