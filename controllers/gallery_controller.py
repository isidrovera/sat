from odoo import http
from odoo.http import request
import base64
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
            
            # Obtener las fotos
            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])
            
            # Preparar datos de fotos
            fotos_data = []
            pcloud_config = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            
            for foto in fotos:
                # Obtener links de pCloud directamente usando los métodos del modelo
                download_url = foto._get_file_url(foto.file_id, pcloud_config)
                thumb_url = foto._get_thumb_url(foto.file_id, pcloud_config) or download_url
                
                fotos_data.append({
                    'id': foto.id,
                    'nombre': foto.nombre_foto,
                    'preview_url': download_url,  # URL para lightbox
                    'download_url': f'/gallery/download/{foto.id}',  # URL para descarga
                    'thumb_url': thumb_url  # URL para miniatura
                })
            
            return request.render('sat.gallery_page_template', {
                'reparacion': reparacion,
                'fotos': fotos_data,
            })
            
        except Exception as e:
            _logger.error("Error al cargar la galería: %s", str(e))
            return """
                <div style="text-align: center; padding: 50px;">
                    <h1>Error al cargar la galería</h1>
                </div>
            """

    @http.route('/gallery/download/<int:foto_id>', type='http', auth='public')
    def download_photo(self, foto_id, **kwargs):
        try:
            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if not foto.exists():
                return request.not_found()
            
            # Obtener contenido para descarga
            result = foto.get_download_content()
            if not result:
                return request.not_found()
            
            # Devolver el archivo forzando la descarga
            return request.make_response(
                base64.b64decode(result['content']),
                headers=[
                    ('Content-Type', result['mimetype']),
                    ('Content-Disposition', f'attachment; filename="{result["filename"]}"'),
                ]
            )
        except Exception as e:
            _logger.error("Error al descargar foto: %s", str(e))
            return request.not_found()

    @http.route('/gallery/download_all/<int:reparacion_id>', type='http', auth='public')
    def download_all_photos(self, reparacion_id):
        try:
            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])
            
            if not fotos:
                return request.not_found()
            
            # Usar el método existente para crear ZIP
            result = fotos.get_photos_zip(fotos.ids)
            if not result:
                return request.not_found()
            
            return request.make_response(
                base64.b64decode(result['content']),
                headers=[
                    ('Content-Type', 'application/zip'),
                    ('Content-Disposition', f'attachment; filename="{result["filename"]}"'),
                ]
            )
        except Exception as e:
            _logger.error("Error al descargar todas las fotos: %s", str(e))
            return request.not_found()