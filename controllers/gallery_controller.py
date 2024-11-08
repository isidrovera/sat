from odoo import http
from odoo.http import request, Response
import logging
import json
import base64
import requests

_logger = logging.getLogger(__name__)

class GalleryController(http.Controller):
    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public', website=True)
    def gallery_page(self, reparacion_id, **kwargs):
        try:
            # Asegurar que tenemos una sesión válida
            if not request.session.uid:
                # Redirigir a login si no hay sesión
                return request.redirect('/web/login?redirect=/gallery/%s' % reparacion_id)

            # Obtener la reparación con sudo() para asegurar acceso
            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                return request.not_found()

            # Obtener configuración de pCloud
            pcloud_config = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            if not pcloud_config:
                return request.render('sat.gallery_error_template', {
                    'error': 'No se encontró configuración de pCloud'
                })

            # Verificar y refrescar token si es necesario
            if not self._verify_pcloud_token(pcloud_config):
                # Aquí podrías implementar la lógica para refrescar el token
                return request.render('sat.gallery_error_template', {
                    'error': 'Token de pCloud no válido'
                })

            # Obtener fotos con sus URLs
            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])

            fotos_data = []
            for foto in fotos:
                try:
                    thumb_url = foto._get_thumb_url(foto.file_id, pcloud_config)
                    download_url = foto._get_file_url(foto.file_id, pcloud_config)
                    if thumb_url and download_url:
                        fotos_data.append({
                            'id': foto.id,
                            'nombre_foto': foto.nombre_foto,
                            'thumb_url': thumb_url,
                            'download_url': download_url,
                        })
                except Exception as e:
                    _logger.error("Error procesando foto %s: %s", foto.id, str(e))

            # Renderizar template con los datos
            return request.render('sat.gallery_page_template', {
                'reparacion': reparacion,
                'fotos': fotos_data,
                'error': kwargs.get('error'),
                'success': kwargs.get('success')
            })

        except Exception as e:
            _logger.exception("Error en gallery_page: %s", str(e))
            return request.render('sat.gallery_error_template', {
                'error': str(e)
            })

    def _verify_pcloud_token(self, pcloud_config):
        """Verifica si el token de pCloud es válido"""
        try:
            url = f"{pcloud_config.hostname}/userinfo"
            params = {'access_token': pcloud_config.access_token}
            response = requests.get(url, params=params)
            return response.status_code == 200 and response.json().get('result') == 0
        except:
            return False

    @http.route('/gallery/refresh_gallery/<int:reparacion_id>', type='json', auth='public')
    def refresh_gallery(self, reparacion_id):
        """Endpoint para refrescar los datos de la galería via AJAX"""
        try:
            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])
            
            pcloud_config = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            fotos_data = []
            
            for foto in fotos:
                thumb_url = foto._get_thumb_url(foto.file_id, pcloud_config)
                download_url = foto._get_file_url(foto.file_id, pcloud_config)
                if thumb_url and download_url:
                    fotos_data.append({
                        'id': foto.id,
                        'nombre_foto': foto.nombre_foto,
                        'thumb_url': thumb_url,
                        'download_url': download_url,
                    })
            
            return {'success': True, 'fotos': fotos_data}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/gallery/upload/<int:reparacion_id>', type='http', auth='public', methods=['POST'], csrf=False)
    def upload_photo(self, reparacion_id, **kwargs):
        """Maneja la subida de fotos"""
        try:
            files = request.httprequest.files.getlist('files[]')
            if not files:
                return json.dumps({'error': 'No se encontraron archivos'})

            uploaded_files = []
            for file in files:
                foto_data = {
                    'reparacion_id': reparacion_id,
                    'nombre_foto': file.filename,
                    'foto_binario': base64.b64encode(file.read()),
                }
                foto = request.env['reparaciones.foto'].sudo().create(foto_data)
                uploaded_files.append({
                    'id': foto.id,
                    'nombre': foto.nombre_foto,
                    'url': foto.url_foto
                })

            return json.dumps({'success': True, 'files': uploaded_files})
        except Exception as e:
            _logger.exception("Error en la subida de fotos: %s", str(e))
            return json.dumps({'error': str(e)})

    @http.route('/gallery/delete/<int:foto_id>', type='http', auth='public', methods=['POST'], csrf=False)
    def delete_photo(self, foto_id):
        """Elimina una foto"""
        try:
            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if foto.exists():
                foto.unlink()
                return json.dumps({'success': True})
            return json.dumps({'error': 'Foto no encontrada'})
        except Exception as e:
            return json.dumps({'error': str(e)})

    @http.route('/gallery/download/<int:foto_id>', type='http', auth='public')
    def download_photo(self, foto_id):
        """Descarga una foto individual"""
        foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
        if not foto.exists():
            return request.not_found()
            
        content = foto.get_download_content()
        if not content:
            return request.not_found()
            
        return request.make_response(
            base64.b64decode(content['content']),
            headers=[
                ('Content-Type', content['mimetype']),
                ('Content-Disposition', f'attachment; filename="{content["filename"]}"')
            ]
        )