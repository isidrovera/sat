from odoo import http
from odoo.http import request
import logging
import requests
import base64

_logger = logging.getLogger(__name__)

class GalleryController(http.Controller):

    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public')
    def gallery_page(self, reparacion_id, **kwargs):
        try:
            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                return request.not_found()
            
            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])
            
            # Obtener configuración de pCloud
            pcloud_config = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            
            # Preparar datos de fotos con miniaturas
            fotos_data = []
            for foto in fotos:
                if foto.file_id:
                    thumb_url = foto._get_thumb_url(foto.file_id, pcloud_config)  # Pasa `pcloud_config`
                    fotos_data.append({
                        'id': foto.id,
                        'nombre': foto.nombre_foto,
                        'preview_url': foto.url_foto,  # URL original para previsualización
                        'thumb_url': thumb_url or foto.url_foto,  # Miniatura o URL original como fallback
                        'public_link': foto.public_link,  # Link público
                    })
            
            return request.render('sat.gallery_page_template', {
                'reparacion': reparacion,
                'fotos': fotos_data,
            })
            
        except Exception as e:
            _logger.error("Error al cargar la galería: %s", str(e))
            return request.not_found()


    @http.route('/gallery/upload_photo', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_photo(self, reparacion_id, **kwargs):
        file = request.httprequest.files.get('file')
        if not file:
            return request.redirect(f'/gallery/{reparacion_id}')

        foto_binario = base64.b64encode(file.read()).decode('utf-8')
        
        foto_obj = request.env['reparaciones.foto'].sudo().create({
            'nombre_foto': file.filename,
            'foto_binario': foto_binario,
            'reparacion_id': reparacion_id,
        })

        foto_obj.upload_to_pcloud()

        return request.redirect(f'/gallery/{reparacion_id}')

    @http.route('/gallery/download/<int:foto_id>', type='http', auth='public')
    def download_photo(self, foto_id):
        foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
        if not foto.exists():
            return request.not_found()

        download_url = foto._get_file_url(foto.file_id)

        return request.redirect(download_url)
