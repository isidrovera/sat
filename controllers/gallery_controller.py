# controllers/gallery_controller.py
from odoo import http
from odoo.http import request
import base64
from werkzeug.exceptions import NotFound
import logging

_logger = logging.getLogger(__name__)

class GalleryController(http.Controller):
    
    def _prepare_photo_data(self, foto):
        """Prepara los datos de la foto para la vista"""
        return {
            'id': foto.id,
            'nombre': foto.nombre_foto,
            'image_url': f'/gallery/image/{foto.id}',
            'download_url': f'/gallery/download/{foto.id}'
        }
    
    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public', website=True)
    def gallery_page(self, reparacion_id, **kwargs):
        reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
        if not reparacion.exists():
            raise NotFound()
            
        fotos = request.env['reparaciones.foto'].sudo().search([
            ('reparacion_id', '=', reparacion_id)
        ])
        
        # Preparar los datos de las fotos
        fotos_data = [self._prepare_photo_data(foto) for foto in fotos]
        
        values = {
            'reparacion': reparacion,
            'fotos': fotos_data,
        }
        return request.render('sat.gallery_page_template', values)

    @http.route('/gallery/image/<int:foto_id>', type='http', auth='public')
    def get_image(self, foto_id, **kwargs):
        try:
            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if not foto.exists() or not foto.foto_binario:
                raise NotFound()

            binary_content = base64.b64decode(foto.foto_binario)
            return request.make_response(
                binary_content,
                headers=[
                    ('Content-Type', 'image/jpeg'),
                    ('Content-Length', len(binary_content))
                ]
            )
        except Exception as e:
            _logger.error("Error al obtener imagen %s: %s", foto_id, str(e))
            raise NotFound()
        
    @http.route('/gallery/download/<int:foto_id>', type='http', auth='public')
    def download_photo(self, foto_id, **kwargs):
        try:
            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if not foto.exists() or not foto.foto_binario:
                raise NotFound()
                
            binary_content = base64.b64decode(foto.foto_binario)
            
            return request.make_response(
                binary_content,
                headers=[
                    ('Content-Type', 'application/octet-stream'),
                    ('Content-Disposition', f'attachment; filename="{foto.nombre_foto}"'),
                    ('Content-Length', len(binary_content))
                ]
            )
        except Exception as e:
            _logger.error("Error al descargar foto %s: %s", foto_id, str(e))
            raise NotFound()