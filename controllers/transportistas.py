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
            
            _logger.info(f"[CONTROLLER] Registro encontrado: {record}")
            
            # Validar existencia
            if not record.exists():
                _logger.error(f"[CONTROLLER] Registro {record_id} no encontrado")
                return self._render_error('No se encontró la máquina especificada')
                
            # Verificar campo token
            if not hasattr(record, 'location_change_token'):
                _logger.error(f"[CONTROLLER] El campo 'location_change_token' no existe en el modelo")
                return self._render_error('Error de configuración: Campo de token no existe')
            
            _logger.info(f"[CONTROLLER] Token almacenado en BD: {record.location_change_token}")
            _logger.info(f"[CONTROLLER] Token recibido en URL: {token}")
            
            # Validación mejorada de token
            if not token:
                _logger.error(f"[CONTROLLER] No se proporcionó token en la URL")
                return self._render_error('Token requerido')
                
            if not record.location_change_token:
                _logger.error(f"[CONTROLLER] No hay token válido en la base de datos para el registro {record_id}")
                return self._render_error('Token no válido o ya utilizado')
                
            if record.location_change_token != token:
                _logger.error(f"[CONTROLLER] Token inválido: {token} vs {record.location_change_token}")
                return self._render_error('Token inválido o expirado')
            
            _logger.info(f"[CONTROLLER] Token validado correctamente")
            
            # Guardar información antes del cambio
            ubicacion_anterior = record.ubicacion_id
            _logger.info(f"[CONTROLLER] Ubicación anterior: {ubicacion_anterior}")
            
            # Cambiar ubicación y limpiar token usando el método del modelo
            try:
                _logger.info(f"[CONTROLLER] Ejecutando cambio de ubicación a primer_piso")
                record.write({'ubicacion_id': 'primer_piso'})
                _logger.info(f"[CONTROLLER] Ubicación actualizada exitosamente")
                
                # Invalidar token usando el método del modelo
                _logger.info(f"[CONTROLLER] Invalidando token")
                if record.invalidar_token_ubicacion():
                    _logger.info(f"[CONTROLLER] Token invalidado correctamente")
                else:
                    _logger.warning(f"[CONTROLLER] No se pudo invalidar el token completamente")
                
                # Confirmar cambios
                request.env.cr.commit()
                _logger.info(f"[CONTROLLER] Cambios confirmados en la base de datos")
                
            except Exception as e:
                _logger.error(f"[CONTROLLER] Error al cambiar ubicación: {str(e)}")
                request.env.cr.rollback()
                return self._render_error(f'Error al cambiar ubicación: {str(e)}')
            
            # Registrar el cambio en el historial
            try:
                _logger.info(f"[CONTROLLER] Creando mensaje en el historial")
                peru_tz = pytz.timezone('America/Lima')
                current_time = datetime.now(peru_tz).strftime('%Y-%m-%d %H:%M:%S')
                message = f"<b>Cambio de ubicación por transportista:</b> De {ubicacion_anterior} a <b>primer_piso</b> el {current_time}"
                record.message_post(body=message, subtype_id=request.env.ref('mail.mt_note').id)
                _logger.info(f"[CONTROLLER] Mensaje registrado en el historial")
                
            except Exception as e:
                _logger.error(f"[CONTROLLER] Error al crear mensaje en historial: {str(e)}")
                # No fallar por esto, continuar
            
            # Recargar el registro para obtener los datos actualizados
            record = request.env['sat.sat'].sudo().browse(record_id)
            
            # Obtener información del modelo para la página de éxito
            model_info = {
                'name': record.name.name if hasattr(record, 'name') and record.name else 'Desconocido',
                'serie': record.serie_id if hasattr(record, 'serie_id') else 'Desconocido',
                'marca': record.marca if hasattr(record, 'marca') else 'Desconocido',
                'ubicacion': 'Primer piso'
            }
            
            _logger.info(f"[CONTROLLER] Información de la máquina: {model_info}")
            _logger.info(f"[CONTROLLER] Proceso completado exitosamente para registro {record_id}")
            
            return self._render_success('Ubicación actualizada correctamente', model_info)
            
        except Exception as e:
            _logger.error(f"[CONTROLLER] Error general: {str(e)}", exc_info=True)
            request.env.cr.rollback()
            return self._render_error(f'Error interno: {str(e)}')
    
    def _render_error(self, error_message):
        """Renderiza una página de error moderna con cierre automático"""
        _logger.info(f"[CONTROLLER] Renderizando página de error: {error_message}")
        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <title>Error - Cambio de Ubicación</title>
            <meta charset="utf-8"/>
            <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
            <style>
                body {{
                    background-color: #f8f9fa;
                    font-family: 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
                }}
                .page-container {{
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    padding: 20px;
                }}
                .card {{
                    border: none;
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                    max-width: 500px;
                    width: 100%;
                }}
                .card-header {{
                    background-color: #dc3545;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-bottom: none;
                }}
                .icon-bg {{
                    font-size: 60px;
                    margin-bottom: 10px;
                }}
                .card-body {{
                    padding: 30px;
                    background: white;
                }}
                .progress-bar {{
                    height: 5px;
                    transition: width 1s linear;
                }}
                .btn-custom {{
                    background-color: #dc3545;
                    border-color: #dc3545;
                    padding: 10px 20px;
                    font-weight: 500;
                }}
                .btn-custom:hover {{
                    background-color: #c82333;
                    border-color: #bd2130;
                }}
                .countdown {{
                    font-size: 14px;
                    color: #6c757d;
                    margin-top: 15px;
                    text-align: center;
                }}
            </style>
        </head>
        <body>
            <div class="page-container">
                <div class="card">
                    <div class="card-header">
                        <div class="icon-bg">
                            <i class="fas fa-exclamation-circle"></i>
                        </div>
                        <h3 class="m-0">Error</h3>
                    </div>
                    <div class="progress" style="height: 5px;">
                        <div id="progress-bar" class="progress-bar bg-danger" role="progressbar" style="width: 100%"></div>
                    </div>
                    <div class="card-body">
                        <div class="alert alert-danger mb-4" role="alert">
                            <i class="fas fa-exclamation-triangle me-2"></i>
                            {error_message}
                        </div>
                        <div class="d-grid gap-2">
                            <a href="/" class="btn btn-custom">
                                <i class="fas fa-home me-2"></i> Volver al Inicio
                            </a>
                        </div>
                        <div class="countdown mt-3">
                            Esta página se cerrará automáticamente en <span id="timer" class="fw-bold">10</span> segundos.
                        </div>
                    </div>
                </div>
            </div>
            
            <script>
                // Contador para cerrar la página automáticamente
                var seconds = 10;
                var progressBar = document.getElementById('progress-bar');
                var initialWidth = 100;
                var step = initialWidth / seconds;
                
                function updateCountdown() {{
                    document.getElementById('timer').textContent = seconds;
                    progressBar.style.width = (seconds * step) + '%';
                    
                    if (seconds <= 0) {{
                        window.close();
                        // Si la ventana no se cierra, redirigimos a la página principal
                        window.location.href = '/';
                    }} else {{
                        seconds--;
                        setTimeout(updateCountdown, 1000);
                    }}
                }}
                
                // Iniciar el contador cuando se carga la página
                window.onload = function() {{
                    updateCountdown();
                }};
            </script>
        </body>
        </html>
        """
        return http.Response(html, status=200, mimetype='text/html')
    
    def _render_success(self, message, model_info=None):
        """Renderiza una página de éxito moderna con cierre automático"""
        _logger.info(f"[CONTROLLER] Renderizando página de éxito: {message}")
        
        model_details = ""
        if model_info:
            model_details = f"""
            <div class="card mb-4">
                <div class="card-header bg-light">
                    <h5 class="m-0"><i class="fas fa-info-circle me-2"></i>Detalles de la máquina</h5>
                </div>
                <div class="card-body">
                    <ul class="list-group list-group-flush">
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <span><i class="fas fa-tag me-2 text-secondary"></i>Modelo:</span>
                            <span class="fw-bold">{model_info.get('name', 'N/A')}</span>
                        </li>
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <span><i class="fas fa-barcode me-2 text-secondary"></i>Serie:</span>
                            <span class="fw-bold">{model_info.get('serie', 'N/A')}</span>
                        </li>
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <span><i class="fas fa-copyright me-2 text-secondary"></i>Marca:</span>
                            <span class="fw-bold">{model_info.get('marca', 'N/A')}</span>
                        </li>
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <span><i class="fas fa-map-marker-alt me-2 text-secondary"></i>Nueva ubicación:</span>
                            <span class="fw-bold">{model_info.get('ubicacion', 'N/A')}</span>
                        </li>
                    </ul>
                </div>
            </div>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <title>Éxito - Cambio de Ubicación</title>
            <meta charset="utf-8"/>
            <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
            <style>
                body {{
                    background-color: #f8f9fa;
                    font-family: 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
                }}
                .page-container {{
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    padding: 20px;
                }}
                .card {{
                    border: none;
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                    max-width: 500px;
                    width: 100%;
                }}
                .card-header {{
                    background-color: #28a745;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-bottom: none;
                }}
                .icon-bg {{
                    font-size: 60px;
                    margin-bottom: 10px;
                }}
                .card-body {{
                    padding: 30px;
                    background: white;
                }}
                .progress-bar {{
                    height: 5px;
                    transition: width 1s linear;
                }}
                .btn-custom {{
                    background-color: #28a745;
                    border-color: #28a745;
                    padding: 10px 20px;
                    font-weight: 500;
                }}
                .btn-custom:hover {{
                    background-color: #218838;
                    border-color: #1e7e34;
                }}
                .countdown {{
                    font-size: 14px;
                    color: #6c757d;
                    margin-top: 15px;
                    text-align: center;
                }}
            </style>
        </head>
        <body>
            <div class="page-container">
                <div class="card">
                    <div class="card-header">
                        <div class="icon-bg">
                            <i class="fas fa-check-circle"></i>
                        </div>
                        <h3 class="m-0">¡Éxito!</h3>
                    </div>
                    <div class="progress" style="height: 5px;">
                        <div id="progress-bar" class="progress-bar bg-success" role="progressbar" style="width: 100%"></div>
                    </div>
                    <div class="card-body">
                        <div class="alert alert-success mb-4" role="alert">
                            <i class="fas fa-check-circle me-2"></i>
                            {message}
                        </div>
                        
                        {model_details}
                        
                        <div class="d-grid gap-2">
                            <a href="/" class="btn btn-custom">
                                <i class="fas fa-home me-2"></i> Volver al Inicio
                            </a>
                        </div>
                        <div class="countdown mt-3">
                            Esta página se cerrará automáticamente en <span id="timer" class="fw-bold">10</span> segundos.
                        </div>
                    </div>
                </div>
            </div>
            
            <script>
                // Contador para cerrar la página automáticamente
                var seconds = 10;
                var progressBar = document.getElementById('progress-bar');
                var initialWidth = 100;
                var step = initialWidth / seconds;
                
                function updateCountdown() {{
                    document.getElementById('timer').textContent = seconds;
                    progressBar.style.width = (seconds * step) + '%';
                    
                    if (seconds <= 0) {{
                        window.close();
                        // Si la ventana no se cierra, redirigimos a la página principal
                        window.location.href = '/';
                    }} else {{
                        seconds--;
                        setTimeout(updateCountdown, 1000);
                    }}
                }}
                
                // Iniciar el contador cuando se carga la página
                window.onload = function() {{
                    updateCountdown();
                }};
            </script>
        </body>
        </html>
        """
        return http.Response(html, status=200, mimetype='text/html')