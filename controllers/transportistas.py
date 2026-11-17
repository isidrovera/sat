from odoo import http
from odoo.http import request
import logging
from datetime import datetime
import pytz
from html import escape

_logger = logging.getLogger(__name__)

class SatController(http.Controller):
    @http.route(
        '/sat/change_location/<int:record_id>',
        type='http', auth='public', methods=['GET'], website=True,
    )
    def change_location(self, record_id, token=None, **kwargs):
        """El GET solo muestra confirmación; jamás mueve la máquina."""
        try:
            record = request.env['sat.sat'].sudo().browse(record_id).exists()
            if not record or not token or record.location_change_token != token:
                return self._render_error('Enlace inválido o ya utilizado')
            if record.ubicacion_id not in ('segundo_local', 'covida'):
                return self._render_error('Esta máquina ya no está pendiente de traslado')
            return self._render_confirmation(record, token)
        except Exception:
            _logger.exception('[TRANSPORTE] Error preparando confirmación de máquina %s', record_id)
            return self._render_error('No se pudo cargar la confirmación')

    @http.route(
        '/sat/change_location/<int:record_id>',
        type='http', auth='public', methods=['POST'], website=True, csrf=True,
    )
    def confirm_change_location(self, record_id, token=None, **kwargs):
        """Solo un POST explícito confirma la llegada al primer piso."""
        try:
            # Serializar confirmaciones simultáneas del mismo enlace.
            request.env.cr.execute('SELECT id FROM sat_sat WHERE id = %s FOR UPDATE', [record_id])
            if not request.env.cr.fetchone():
                return self._render_error('No se encontró la máquina')
            record = request.env['sat.sat'].sudo().browse(record_id).exists()
            record.invalidate_recordset(['location_change_token', 'ubicacion_id'])
            if not record or not token or record.location_change_token != token:
                return self._render_error('Enlace inválido o ya utilizado')
            if record.ubicacion_id not in ('segundo_local', 'covida'):
                return self._render_error('Esta máquina ya no está pendiente de traslado')

            anterior = record.ubicacion_id
            record.with_context(force_location_change=True).write({
                'ubicacion_id': 'primer_piso',
                'location_change_token': False,
            })
            peru_tz = pytz.timezone('America/Lima')
            fecha = datetime.now(peru_tz).strftime('%Y-%m-%d %H:%M:%S')
            record.message_post(
                body=(
                    '<b>Traslado confirmado por enlace:</b> '
                    f'{escape(anterior)} → <b>Primer piso</b> el {fecha}'
                ),
                subtype_xmlid='mail.mt_note',
            )
            return self._render_success('Ubicación actualizada correctamente', {
                'name': record.name.name if record.name else 'Desconocido',
                'serie': record.serie_id or 'Desconocido',
                'marca': record.marca or 'Desconocido',
                'ubicacion': 'Primer piso',
            })
        except Exception:
            _logger.exception('[TRANSPORTE] Error confirmando máquina %s', record_id)
            return self._render_error('No se pudo confirmar el traslado. Intente nuevamente')

    def _render_confirmation(self, record, token):
        nombre = escape(record.name.name if record.name else 'Máquina')
        serie = escape(record.serie_id or '')
        ubicaciones = dict(record._fields['ubicacion_id'].selection)
        origen = escape(ubicaciones.get(record.ubicacion_id, record.ubicacion_id))
        csrf = escape(request.csrf_token(), quote=True)
        token_value = escape(token, quote=True)
        html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="referrer" content="no-referrer"/>
<title>Confirmar traslado SAT</title>
<style>
body{{font-family:system-ui,Arial,sans-serif;background:#f1f5fa;margin:0;padding:24px;color:#183153}}
.card{{max-width:440px;margin:8vh auto;background:#fff;border-radius:20px;padding:30px;box-shadow:0 15px 40px #18315318}}
h1{{font-size:24px;margin:0 0 8px}}p{{line-height:1.6}}.muted{{color:#64748b}}
button{{border:0;background:#1d57b7;color:white;width:100%;padding:16px;border-radius:12px;font-weight:700;font-size:16px;cursor:pointer}}
</style></head><body><main class="card">
<h1>Confirmar llegada</h1>
<p class="muted">Verifique que la máquina ya se encuentre físicamente en el primer piso.</p>
<p><b>Modelo:</b> {nombre}<br/><b>Serie:</b> {serie}<br/><b>Origen:</b> {origen}<br/><b>Destino:</b> Primer piso</p>
<form method="post" action="/sat/change_location/{record.id}">
<input type="hidden" name="csrf_token" value="{csrf}"/>
<input type="hidden" name="token" value="{token_value}"/>
<button type="submit">Confirmar llegada al primer piso</button></form>
</main></body></html>"""
        return request.make_response(html, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Cache-Control', 'no-store'),
            ('Referrer-Policy', 'no-referrer'),
        ])
    
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



