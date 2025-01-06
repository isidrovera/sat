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
            record = request.env['sat.sat'].with_context(force_location_change=True).sudo().browse(record_id)
            
            # Validar existencia y token
            if not record.exists():
                _logger.error(f"[CONTROLLER] Registro {record_id} no encontrado")
                return request.render('sat.location_change_error', {
                    'error': 'No se encontró la máquina especificada'
                })
                
            _logger.info(f"[CONTROLLER] Token almacenado: {record.location_change_token}")
            
            # Validar token
            if record.location_change_token != token:
                _logger.error("[CONTROLLER] Token inválido")
                return request.render('sat.location_change_error', {
                    'error': 'Token inválido o expirado'
                })
            
            # Actualizar ubicación usando SQL directo para evitar las restricciones del write
            request.env.cr.execute("""
                UPDATE sat_sat 
                SET ubicacion_id = 'primer_piso',
                    location_change_token = NULL
                WHERE id = %s
            """, (record_id,))
            
            # Registrar el cambio en el historial
            peru_tz = pytz.timezone('America/Lima')
            current_time = datetime.now(peru_tz).strftime('%Y-%m-%d %H:%M:%S')
            message = f"<b>Cambio de ubicación:</b> De {record.ubicacion_id} a <b>primer_piso</b> el {current_time}"
            record.message_post(body=message, subtype_id=request.env.ref('mail.mt_note').id)
            
            return request.render('sat.location_change_success', {
                'message': 'Ubicación actualizada correctamente'
            })
            
        except Exception as e:
            _logger.error(f"[CONTROLLER] Error: {str(e)}")
            return request.render('sat.location_change_error', {
                'error': str(e)
            })