from odoo import http
from odoo.http import request
import logging
from datetime import datetime
import pytz

_logger = logging.getLogger(__name__)

class SatController(http.Controller):
    @http.route('/sat/change_location/<int:record_id>', type='http', auth='public', website=True)
    def change_location(self, record_id, token=None, **kwargs):
        _logger.info(f"[CONTROLLER] Iniciando proceso de cambio de ubicación")
        _logger.info(f"[CONTROLLER] Record ID: {record_id}")
        _logger.info(f"[CONTROLLER] Token recibido: {token}")
        
        try:
            # Validar token
            if not token:
                _logger.error("[CONTROLLER] No se proporcionó token")
                return request.render('sat.location_change_error', {
                    'error': 'No se proporcionó token de validación'
                })
    
            # Obtener registro
            record = request.env['sat.sat'].with_context(active_test=False).sudo().browse(record_id)
            
            # Validar existencia del registro
            if not record.exists():
                _logger.error(f"[CONTROLLER] Registro {record_id} no encontrado")
                return request.render('sat.location_change_error', {
                    'error': 'No se encontró la máquina especificada'
                })
            
            _logger.info(f"[CONTROLLER] Token almacenado: {record.location_change_token}")
            
            # Validar coincidencia de token
            if record.location_change_token != token:
                _logger.error(f"[CONTROLLER] Token no coincide: {token} != {record.location_change_token}")
                return request.render('sat.location_change_error', {
                    'error': 'Token inválido o expirado'
                })
                
            # Verificar si ya está en primer piso
            if record.ubicacion_id == 'primer_piso':
                _logger.info("[CONTROLLER] La ubicación ya está en primer piso")
                return request.render('sat.location_already_changed', {
                    'message': 'La ubicación ya ha sido actualizada'
                })
                
            try:
                # Guardar ubicación anterior
                old_location = record.ubicacion_id
                _logger.info(f"[CONTROLLER] Ubicación anterior: {old_location}")
                
                # Actualizar ubicación
                record.write({
                    'ubicacion_id': 'primer_piso',
                    'location_change_token': False  # Invalidar token después de usarlo
                })
                _logger.info("[CONTROLLER] Ubicación actualizada a primer_piso")
                
                # Registrar el cambio
                peru_tz = pytz.timezone('America/Lima')
                current_time = datetime.now(peru_tz).strftime('%Y-%m-%d %H:%M:%S')
                message = f"<b>Cambio de ubicación:</b> De {old_location} a <b>primer_piso</b> el {current_time}"
                record.message_post(body=message, subtype_id=request.env.ref('mail.mt_note').id)
                _logger.info("[CONTROLLER] Cambio registrado en el historial")
                
                return request.render('sat.location_change_success', {
                    'message': 'Ubicación actualizada correctamente'
                })
                
            except Exception as e:
                _logger.error(f"[CONTROLLER] Error al actualizar ubicación: {str(e)}")
                return request.render('sat.location_change_error', {
                    'error': 'Error al actualizar la ubicación'
                })
                
        except Exception as e:
            _logger.exception(f"[CONTROLLER] Error general: {str(e)}")
            return request.render('sat.location_change_error', {
                'error': 'Error al procesar la solicitud'
            })