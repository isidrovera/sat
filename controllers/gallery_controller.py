# controllers/gallery_controller.py
from odoo import http
from odoo.http import request
import base64
from werkzeug.utils import redirect
from werkzeug.wrappers import Response

class GalleryController(http.Controller):
    
    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public', website=True)
    def gallery_page(self, reparacion_id, **kwargs):
        reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
        if not reparacion.exists():
            return request.not_found()
            
        fotos = request.env['reparaciones.foto'].sudo().search([
            ('reparacion_id', '=', reparacion_id)
        ])
        
        values = {
            'reparacion': reparacion,
            'fotos': fotos,
        }
        return request.render('sat.gallery_page_template', values)
        
    @http.route('/gallery/download/<int:foto_id>', type='http', auth='public')
    def download_photo(self, foto_id, **kwargs):
        foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
        if not foto.exists():
            return request.not_found()
            
        if not foto.foto_binario:
            return request.not_found()
            
        binary_content = base64.b64decode(foto.foto_binario)
        
        return request.make_response(
            binary_content,
            headers=[
                ('Content-Type', 'image/jpeg'),
                ('Content-Disposition', f'attachment; filename="{foto.nombre_foto}"'),
                ('Content-Length', len(binary_content))
            ]
        )
        
    @http.route('/gallery/download_all/<int:reparacion_id>', type='http', auth='public')
    def download_all_photos(self, reparacion_id, **kwargs):
        fotos = request.env['reparaciones.foto'].sudo().search([
            ('reparacion_id', '=', reparacion_id)
        ])
        
        if not fotos:
            return request.not_found()
            
        # Reutilizamos el método existente para crear el ZIP
        result = fotos.get_photos_zip(fotos.ids)
        
        if not result or not result.get('content'):
            return request.not_found()
            
        zip_content = base64.b64decode(result['content'])
        
        return request.make_response(
            zip_content,
            headers=[
                ('Content-Type', 'application/zip'),
                ('Content-Disposition', f'attachment; filename="{result["filename"]}"'),
                ('Content-Length', len(zip_content))
            ]
        )