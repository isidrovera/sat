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
            # Debug logging inicial
            _logger.info(f"[DEBUG] Procesando cambio de ubicación para registro {record_id}")
            _logger.info(f"[DEBUG] Token recibido: {token}")
            
            if not token:
                _logger.error("No se proporcionó token")
                return request.render('sat.location_change_error', {
                    'error': 'Token no proporcionado'
                })
    
            # Obtener registro
            record = request.env['sat.sat'].with_context(active_test=False).sudo().browse(record_id)
            
            # Validar existencia
            if not record.exists():
                _logger.error(f"Registro {record_id} no encontrado")
                return request.render('sat.location_change_error', {
                    'error': 'No se encontró la máquina especificada'
                })
                
            # Debug del token almacenado
            _logger.info(f"[DEBUG] Token almacenado: {record.location_change_token}")
                
            # Validar token
            if not record.location_change_token or record.location_change_token != token:
                _logger.warning(f"Token inválido - Almacenado: {record.location_change_token}, Recibido: {token}")
                return request.render('sat.location_change_error', {
                    'error': 'El enlace no es válido o ha expirado'
                })
                
            # Verificar ubicación actual
            if record.ubicacion_id == 'primer_piso':
                _logger.info("La ubicación ya está en primer piso")
                return request.render('sat.location_already_changed', {
                    'message': 'La ubicación ya ha sido actualizada'
                })
                
            # Guardar ubicación anterior y actualizar
            old_location = record.ubicacion_id
            try:
                record.write({
                    'ubicacion_id': 'primer_piso',
                    'location_change_token': False
                })
                _logger.info(f"Ubicación actualizada de {old_location} a primer_piso")
            except Exception as e:
                _logger.error(f"Error al actualizar ubicación: {str(e)}")
                raise
    
            # Registrar el cambio
            peru_tz = pytz.timezone('America/Lima')
            current_time = datetime.now(peru_tz).strftime('%Y-%m-%d %H:%M:%S')
            message = f"<b>Cambio de ubicación:</b> De {old_location} a <b>primer_piso</b> el {current_time}."
            record.message_post(body=message, subtype_id=request.env.ref('mail.mt_note').id)
            
            return request.render('sat.location_change_success', {
                'message': 'Ubicación actualizada correctamente'
            })
            
        except Exception as e:
            _logger.exception(f"Error al procesar cambio de ubicación: {str(e)}")
            return request.render('sat.location_change_error', {
                'error': 'Error al procesar la solicitud'
            })@http.route('/sat/change_location/<int:record_id>', type='http', auth='public', website=True)
    def change_location(self, record_id, token=None, **kwargs):
        try:
            # Debug logging inicial
            _logger.info(f"[DEBUG] Procesando cambio de ubicación para registro {record_id}")
            _logger.info(f"[DEBUG] Token recibido: {token}")
            
            if not token:
                _logger.error("No se proporcionó token")
                return request.render('sat.location_change_error', {
                    'error': 'Token no proporcionado'
                })
    
            # Obtener registro
            record = request.env['sat.sat'].with_context(active_test=False).sudo().browse(record_id)
            
            # Validar existencia
            if not record.exists():
                _logger.error(f"Registro {record_id} no encontrado")
                return request.render('sat.location_change_error', {
                    'error': 'No se encontró la máquina especificada'
                })
                
            # Debug del token almacenado
            _logger.info(f"[DEBUG] Token almacenado: {record.location_change_token}")
                
            # Validar token
            if not record.location_change_token or record.location_change_token != token:
                _logger.warning(f"Token inválido - Almacenado: {record.location_change_token}, Recibido: {token}")
                return request.render('sat.location_change_error', {
                    'error': 'El enlace no es válido o ha expirado'
                })
                
            # Verificar ubicación actual
            if record.ubicacion_id == 'primer_piso':
                _logger.info("La ubicación ya está en primer piso")
                return request.render('sat.location_already_changed', {
                    'message': 'La ubicación ya ha sido actualizada'
                })
                
            # Guardar ubicación anterior y actualizar
            old_location = record.ubicacion_id
            try:
                record.write({
                    'ubicacion_id': 'primer_piso',
                    'location_change_token': False
                })
                _logger.info(f"Ubicación actualizada de {old_location} a primer_piso")
            except Exception as e:
                _logger.error(f"Error al actualizar ubicación: {str(e)}")
                raise
    
            # Registrar el cambio
            peru_tz = pytz.timezone('America/Lima')
            current_time = datetime.now(peru_tz).strftime('%Y-%m-%d %H:%M:%S')
            message = f"<b>Cambio de ubicación:</b> De {old_location} a <b>primer_piso</b> el {current_time}."
            record.message_post(body=message, subtype_id=request.env.ref('mail.mt_note').id)
            
            return request.render('sat.location_change_success', {
                'message': 'Ubicación actualizada correctamente'
            })
            
        except Exception as e:
            _logger.exception(f"Error al procesar cambio de ubicación: {str(e)}")
            return request.render('sat.location_change_error', {
                'error': 'Error al procesar la solicitud'
            })