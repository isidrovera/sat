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
            _logger.info("Cargando galería para reparación ID: %s", reparacion_id)
            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                _logger.error("Reparación con ID %s no encontrada.", reparacion_id)
                return request.not_found()
            
            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])
            _logger.info("Número de fotos encontradas: %s", len(fotos))
            
            # Obtener configuración de pCloud
            pcloud_config = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            if not pcloud_config:
                _logger.error("Configuración de pCloud no encontrada.")
                return request.not_found()
            
            # Preparar datos de fotos con miniaturas
            fotos_data = []
            for foto in fotos:
                if foto.file_id:
                    thumb_url = self._get_thumbnail_url(foto.file_id, pcloud_config)
                    _logger.info("URL de miniatura para foto %s: %s", foto.id, thumb_url)
                    fotos_data.append({
                        'id': foto.id,
                        'nombre': foto.nombre_foto,
                        'preview_url': foto.url_foto,
                        'thumb_url': thumb_url or foto.url_foto,
                        'public_link': foto.public_link,
                    })
            
            return request.render('sat.gallery_page_template', {
                'reparacion': reparacion,
                'fotos': fotos_data,
            })
            
        except Exception as e:
            _logger.exception("Error al cargar la galería: %s", str(e))
            return request.not_found()

    def _get_thumbnail_url(self, file_id, pcloud_config):
        """Obtener URL de miniatura usando getthumblink"""
        try:
            _logger.info("Obteniendo thumbnail para file_id: %s", file_id)
            url = f"{pcloud_config.hostname}/getthumblink"
            params = {
                'access_token': pcloud_config.access_token,
                'fileid': file_id,
                'size': '256x256',
                'crop': 1,
            }
            
            response = requests.get(url, params=params)
            result = response.json()
            _logger.info("Respuesta de getthumblink para file_id %s: %s", file_id, result)
            
            if response.status_code == 200 and result.get('result') == 0:
                thumb_url = f"https://{result['hosts'][0]}{result['path']}"
                _logger.info("Thumbnail URL generada: %s", thumb_url)
                return thumb_url
            _logger.warning("No se pudo obtener thumbnail para file_id %s: %s", file_id, result)
            return None
        except Exception as e:
            _logger.exception("Error al obtener thumbnail: %s", str(e))
            return None

    @http.route('/gallery/download/<int:foto_id>', type='http', auth='public')
    def download_photo(self, foto_id):
        try:
            _logger.info("Descargando foto ID: %s", foto_id)
            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if not foto.exists():
                _logger.error("Foto con ID %s no encontrada.", foto_id)
                return request.not_found()

            # Obtener configuración de pCloud
            pcloud_config = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            if not pcloud_config:
                _logger.error("Configuración de pCloud no encontrada.")
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
            _logger.info("Respuesta de getfilelink para foto ID %s: %s", foto_id, result)

            if response.status_code != 200 or result.get('result') != 0:
                _logger.error("Error al obtener el link de descarga para foto ID %s.", foto_id)
                return request.not_found()

            # Obtener el archivo
            download_url = f"https://{result['hosts'][0]}{result['path']}"
            file_response = requests.get(download_url)

            if file_response.status_code != 200:
                _logger.error("Error al descargar el archivo de pCloud para foto ID %s.", foto_id)
                return request.not_found()

            return request.make_response(
                file_response.content,
                headers=[
                    ('Content-Type', 'application/octet-stream'),
                    ('Content-Disposition', f'attachment; filename="{foto.nombre_foto}"'),
                ]
            )

        except Exception as e:
            _logger.exception("Error al descargar foto: %s", str(e))
            return request.not_found()

    @http.route('/gallery/download_all/<int:reparacion_id>', type='http', auth='public')
    def download_all_photos(self, reparacion_id):
        try:
            _logger.info("Descargando todas las fotos para reparación ID: %s", reparacion_id)
            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])
            
            if not fotos:
                _logger.error("No se encontraron fotos para reparación ID %s.", reparacion_id)
                return request.not_found()

            # Usar el método existente de get_photos_zip
            result = fotos.get_photos_zip(fotos.ids)
            if not result or not result.get('content'):
                _logger.error("Error al generar el ZIP para reparación ID %s.", reparacion_id)
                return request.not_found()

            return request.make_response(
                base64.b64decode(result['content']),
                headers=[
                    ('Content-Type', 'application/zip'),
                    ('Content-Disposition', f'attachment; filename="{result["filename"]}"'),
                ]
            )
            
        except Exception as e:
            _logger.exception("Error al descargar todas las fotos: %s", str(e))
            return request.not_found()
