from odoo import http
from odoo.http import request
import base64
import logging
import requests
import io
import zipfile

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
                    thumb_url = self._get_thumbnail_url(foto.file_id, pcloud_config)
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

    def _get_thumbnail_url(self, file_id, pcloud_config):
        """Obtener URL de miniatura usando getthumblink"""
        try:
            url = f"{pcloud_config.hostname}/getthumblink"
            params = {
                'access_token': pcloud_config.access_token,
                'fileid': file_id,
                'size': '256x256',
                'crop': 1,
            }
            
            response = requests.get(url, params=params)
            result = response.json()
            
            if response.status_code == 200 and result.get('result') == 0:
                return f"https://{result['hosts'][0]}{result['path']}"
            return None
        except Exception as e:
            _logger.error("Error al obtener thumbnail: %s", str(e))
            return None

    @http.route('/gallery/download/<int:foto_id>', type='http', auth='public')
    def download_photo(self, foto_id):
        try:
            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if not foto.exists():
                return request.not_found()

            # Obtener configuración de pCloud
            pcloud_config = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            if not pcloud_config:
                return request.not_found()

            # Obtener URL de descarga
            url = f"{pcloud_config.hostname}/getfilelink"
            params = {
                'access_token': pcloud_config.access_token,
                'fileid': foto.file_id,
                'forcedownload': 1
            }

            response = requests.get(url, params=params)
            result = response.json()

            if response.status_code != 200 or result.get('result') != 0:
                return request.not_found()

            # Obtener el archivo
            download_url = f"https://{result['hosts'][0]}{result['path']}"
            file_response = requests.get(download_url)

            if file_response.status_code != 200:
                return request.not_found()

            return request.make_response(
                file_response.content,
                headers=[
                    ('Content-Type', 'application/octet-stream'),
                    ('Content-Disposition', f'attachment; filename="{foto.nombre_foto}"'),
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

            # Usar el método existente de get_photos_zip
            result = fotos.get_photos_zip(fotos.ids)
            if not result or not result.get('content'):
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