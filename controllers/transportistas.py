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
            # Obtener registro con sudo()
            record = request.env['sat.sat'].with_context(active_test=False).sudo().browse(record_id)

            # Validar si existe el registro
            if not record.exists():
                _logger.error(f"Registro no encontrado: ID {record_id}")
                return request.render('sat.location_change_error', {
                    'error': 'No se encontró la máquina especificada'
                })

            # Validar modelo
            if record._name != 'sat.sat':
                _logger.error(f"Modelo incorrecto para ID {record_id}")
                return request.render('sat.location_change_error', {
                    'error': 'No se encontró la máquina especificada'
                })

            # Validar token
            if record.location_change_token != token:
                _logger.warning(f"Token inválido o ausente para el registro {record_id}")
                return request.render('sat.location_change_error', {
                    'error': 'El enlace no es válido o ha expirado'
                })

            # Verificar estado actual
            if record.ubicacion_id == 'primer_piso':
                return request.render('sat.location_already_changed', {
                    'message': 'La ubicación ya ha sido actualizada'
                })

            # Guardar ubicación anterior
            old_location = record.ubicacion_id

            # Actualizar la ubicación
            record.write({
                'ubicacion_id': 'primer_piso',
                'location_change_token': False
            })

            # Registrar cambio
            peru_tz = pytz.timezone('America/Lima')
            current_time = datetime.now(peru_tz).strftime('%Y-%m-%d %H:%M:%S')
            message = f"<b>Cambio de ubicación:</b> De {old_location} a <b>primer_piso</b> el {current_time}."
            record.message_post(body=message, subtype_id=request.env.ref('mail.mt_note').id)

            return request.render('sat.location_change_success', {
                'message': 'Ubicación actualizada correctamente'
            })

        except Exception as e:
            _logger.exception(f"Error al procesar cambio de ubicación para el registro {record_id}")
            return request.render('sat.location_change_error', {
                'error': 'Error al procesar la solicitud'
            })
