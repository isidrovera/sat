from odoo import http
from odoo.http import request
import logging
from datetime import datetime
import pytz

_logger = logging.getLogger(__name__)

class SatController(http.Controller):
    @http.route('/sat/change_location/<string:record_id>', type='http', auth='public', website=True)
    def change_location(self, record_id, token=None, **kwargs):
        """Controlador para manejar el cambio de ubicación al hacer clic en el enlace."""
        try:
            # Verificar que el record_id sea un número válido
            if not record_id.isdigit():
                _logger.error(f"Identificador no válido recibido: {record_id}")
                return request.render('sat.location_change_error', {
                    'error_message': f"Identificador no válido: {record_id}"
                })

            record_id = int(record_id)
            record = request.env['sat.sat'].sudo().browse(record_id)

            # Verificar si el registro existe y si el token coincide
            if not record.exists() or record.location_change_token != token:
                _logger.warning(f"Intento no autorizado para cambiar la ubicación del registro ID {record_id} con token: {token}")
                return request.render('sat.location_change_error', {
                    'error_message': "Token inválido o registro no encontrado."
                })

            # Verificar si la ubicación ya es 'primer_piso'
            if record.ubicacion_id == 'primer_piso':
                _logger.info(f"La ubicación del registro ID {record_id} ya estaba en 'primer_piso'.")
                return request.render('sat.location_already_changed', {
                    'message': "La ubicación ya estaba actualizada."
                })

            # Cambiar la ubicación a 'primer_piso' y registrar el cambio
            old_location = record.ubicacion_id
            peru_tz = pytz.timezone('America/Lima')
            current_time = datetime.now(peru_tz).strftime('%Y-%m-%d %H:%M:%S')
            record.write({'ubicacion_id': 'primer_piso', 'location_change_token': None})  # Invalida el token después del uso

            message = f"Ubicación cambiada de {old_location} a 'primer_piso' el {current_time}."
            record.message_post(body=message)
            _logger.info(f"Ubicación del registro ID {record_id} cambiada de {old_location} a 'primer_piso'.")
            
            return request.render('sat.location_change_success', {
                'message': "La ubicación fue actualizada correctamente."
            })

        except Exception as e:
            _logger.error(f"Error al procesar la solicitud para record_id={record_id}: {e}")
            return request.render('sat.location_change_error', {
                'error_message': "Ocurrió un error inesperado al procesar la solicitud."
            })
