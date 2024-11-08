# controllers/gallery_controller.py
from odoo import http
from odoo.http import request
import base64
import zipfile
import io
import logging

_logger = logging.getLogger(__name__)

class GalleryController(http.Controller):
    
    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public')
    def gallery_page(self, reparacion_id, **kwargs):
        try:
            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                return """
                    <div style="text-align: center; padding: 50px;">
                        <h1>Reparación no encontrada</h1>
                    </div>
                """
                
            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])
            
            return request.render('sat.gallery_page_template', {
                'reparacion': reparacion,
                'fotos': fotos,
            })
            
        except Exception as e:
            _logger.error("Error al cargar la galería: %s", str(e))
            return """
                <div style="text-align: center; padding: 50px;">
                    <h1>Error al cargar la galería</h1>
                </div>
            """
    
    @http.route('/gallery/download_all/<int:reparacion_id>', type='http', auth='public')
    def download_all_photos(self, reparacion_id):
        try:
            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])
            
            if not fotos:
                return request.not_found()
            
            # Crear ZIP en memoria
            memory_zip = io.BytesIO()
            
            with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                for foto in fotos:
                    if foto.foto_binario:
                        zf.writestr(
                            foto.nombre_foto,
                            base64.b64decode(foto.foto_binario)
                        )
            
            memory_zip.seek(0)
            
            return request.make_response(
                memory_zip.read(),
                headers=[
                    ('Content-Type', 'application/zip'),
                    ('Content-Disposition', 'attachment; filename=fotos.zip'),
                ]
            )
            
        except Exception as e:
            _logger.error("Error al descargar todas las fotos: %s", str(e))
            return request.not_found()