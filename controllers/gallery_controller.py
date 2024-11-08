from odoo import http
from odoo.http import request, Response
import logging
import json
import base64

_logger = logging.getLogger(__name__)

class GalleryController(http.Controller):
    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public', website=True)
    def gallery_page(self, reparacion_id, **kwargs):
        """Renderiza la página de galería"""
        reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
        if not reparacion.exists():
            return request.not_found()

        # Obtener fotos con sus datos
        fotos = request.env['reparaciones.foto'].sudo().get_photos_preview(reparacion_id)
        
        return request.render('sat.gallery_page_template', {
            'reparacion': reparacion,
            'fotos': fotos,
        })

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

    @http.route('/gallery/sync/<int:reparacion_id>', type='json', auth='public')
    def sync_photos(self, reparacion_id):
        """Sincroniza los enlaces de las fotos con pCloud"""
        try:
            fotos = request.env['reparaciones.foto'].sudo().get_photos_preview(reparacion_id)
            return {
                'success': True,
                'fotos': fotos,
                'message': 'Sincronización completada'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

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

    @http.route('/gallery/download_all/<int:reparacion_id>', type='http', auth='public')
    def download_all(self, reparacion_id):
        """Descarga todas las fotos en ZIP"""
        try:
            foto_obj = request.env['reparaciones.foto'].sudo()
            result = foto_obj.get_photos_zip(foto_obj.search([('reparacion_id', '=', reparacion_id)]).ids)
            
            if not result:
                return request.not_found()
                
            return request.make_response(
                base64.b64decode(result['content']),
                headers=[
                    ('Content-Type', 'application/zip'),
                    ('Content-Disposition', f'attachment; filename="{result["filename"]}"')
                ]
            )
        except Exception as e:
            _logger.exception("Error al descargar todas las fotos: %s", str(e))
            return request.not_found()