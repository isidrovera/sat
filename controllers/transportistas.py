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
        _logger.info(f"[CONTROLLER] Parámetros adicionales: {kwargs}")
        
        try:
            _logger.info(f"[CONTROLLER] Buscando registro con ID: {record_id}")
            record = request.env['sat.sat'].with_context(force_location_change=True).sudo().browse(record_id)
            
            _logger.info(f"[CONTROLLER] Registro encontrado: {record.exists()}")
            
            # Validar existencia y token
            if not record.exists():
                _logger.error(f"[CONTROLLER] Registro {record_id} no encontrado")
                return self._render_error('No se encontró la máquina especificada')
                
            # Verificar si el campo location_change_token existe en el modelo
            if not hasattr(record, 'location_change_token'):
                _logger.error(f"[CONTROLLER] El campo 'location_change_token' no existe en el modelo")
                return self._render_error('Error de configuración: Campo de token no existe')
            
            _logger.info(f"[CONTROLLER] Token almacenado: {record.location_change_token}")
            
            # Validar token (solo si hay token)
            if token and record.location_change_token != token:
                _logger.error(f"[CONTROLLER] Token inválido: {token} vs {record.location_change_token}")
                return self._render_error('Token inválido o expirado')
            
            # Guardar ubicación anterior para el registro en el historial
            ubicacion_anterior = record.ubicacion_id
            _logger.info(f"[CONTROLLER] Ubicación anterior: {ubicacion_anterior}")
            
            # Actualizar ubicación usando SQL directo para evitar las restricciones del write
            _logger.info(f"[CONTROLLER] Actualizando ubicación a primer_piso")
            request.env.cr.execute("""
                UPDATE sat_sat 
                SET ubicacion_id = 'primer_piso',
                    location_change_token = NULL
                WHERE id = %s
            """, (record_id,))
            
            # Registrar el cambio en el historial
            _logger.info(f"[CONTROLLER] Creando mensaje en el historial")
            peru_tz = pytz.timezone('America/Lima')
            current_time = datetime.now(peru_tz).strftime('%Y-%m-%d %H:%M:%S')
            message = f"<b>Cambio de ubicación:</b> De {ubicacion_anterior} a <b>primer_piso</b> el {current_time}"
            record.message_post(body=message, subtype_id=request.env.ref('mail.mt_note').id)
            
            _logger.info(f"[CONTROLLER] Proceso completado exitosamente")
            return self._render_success('Ubicación actualizada correctamente')
            
        except Exception as e:
            _logger.error(f"[CONTROLLER] Error: {str(e)}", exc_info=True)
            return self._render_error(str(e))
    
    def _render_error(self, error_message):
        """Renderiza una página de error simple sin depender de una plantilla XML"""
        _logger.info(f"[CONTROLLER] Renderizando página de error: {error_message}")
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Error - Cambio de Ubicación</title>
            <meta charset="utf-8"/>
            <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .alert-danger {{ background-color: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; }}
                .btn {{ display: inline-block; padding: 6px 12px; margin-top: 15px; 
                       background-color: #007bff; color: white; text-decoration: none; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="alert-danger">
                    <h3>Error</h3>
                    <p>{error_message}</p>
                </div>
                <a href="/" class="btn">Volver al inicio</a>
            </div>
        </body>
        </html>
        """
        return http.Response(html, status=200, mimetype='text/html')
    
    def _render_success(self, message):
        """Renderiza una página de éxito simple sin depender de una plantilla XML"""
        _logger.info(f"[CONTROLLER] Renderizando página de éxito: {message}")
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Éxito - Cambio de Ubicación</title>
            <meta charset="utf-8"/>
            <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .alert-success {{ background-color: #d4edda; color: #155724; padding: 15px; border-radius: 5px; }}
                .btn {{ display: inline-block; padding: 6px 12px; margin-top: 15px; 
                       background-color: #007bff; color: white; text-decoration: none; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="alert-success">
                    <h3>Éxito</h3>
                    <p>{message}</p>
                </div>
                <a href="/" class="btn">Volver al inicio</a>
            </div>
        </body>
        </html>
        """
        return http.Response(html, status=200, mimetype='text/html')