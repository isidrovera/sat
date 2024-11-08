from odoo import http
from odoo.http import request
import base64
import logging
import requests
import io
import zipfile

_logger = logging.getLogger(__name__)

class GalleryController(http.Controller):
    
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
            _logger.error(f"Error al obtener thumbnail: {str(e)}")
            return None
    
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
                        'preview_url': foto.url_foto,  # URL completa
                        'thumb_url': thumb_url or foto.url_foto,  # Miniatura o URL completa como fallback
                        'public_link': foto.public_link,  # Link público
                    })
            
            return request.render('sat.gallery_page_template', {
                'reparacion': reparacion,
                'fotos': fotos_data,
            })
            
        except Exception as e:
            _logger.error("Error al cargar la galería: %s", str(e))
            return request.not_found()

    @http.route('/gallery/download_all/<int:reparacion_id>', type='http', auth='public')
    def download_all_photos(self, reparacion_id):
        try:
            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])
            
            if not fotos:
                return request.not_found()

            # Crear archivo ZIP en memoria
            memory_zip = io.BytesIO()
            
            with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for foto in fotos:
                    try:
                        # Descargar cada foto desde pCloud
                        if foto.url_foto:  # Si tenemos URL directa
                            response = requests.get(foto.url_foto)
                            if response.status_code == 200:
                                # Agregar al ZIP con el nombre original
                                zip_file.writestr(foto.nombre_foto, response.content)
                    except Exception as e:
                        _logger.error(f"Error al procesar foto {foto.id}: {str(e)}")
                        continue

            # Preparar el ZIP para descarga
            memory_zip.seek(0)
            
            # Generar nombre de archivo con fecha
            zip_filename = f"fotos_reparacion_{reparacion_id}.zip"
            
            # Devolver el archivo ZIP
            return request.make_response(
                memory_zip.getvalue(),
                headers=[
                    ('Content-Type', 'application/zip'),
                    ('Content-Disposition', f'attachment; filename="{zip_filename}"'),
                ]
            )
            
        except Exception as e:
            _logger.error(f"Error al crear ZIP: {str(e)}")
            return request.not_found()

    