from odoo import http
from odoo.http import request, Response
import logging
import json
import base64
import requests
import os

_logger = logging.getLogger(__name__)

class GalleryController(http.Controller):
    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public', website=True)
    def gallery_page(self, reparacion_id, **kwargs):
        """Renderiza la página de galería"""
        _logger.info("[GALLERY] Accediendo a galería para reparación ID: %s", reparacion_id)
        try:
            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                _logger.error("[GALLERY] Reparación no encontrada: %s", reparacion_id)
                return request.not_found()

            # Obtener fotos con previsualizaciones
            foto_model = request.env['reparaciones.foto'].sudo()
            fotos = foto_model.get_photos_preview(reparacion_id)
            
            # Modificar las URLs para usar el nuevo endpoint de preview
            if fotos:
                for foto in fotos:
                    foto['thumb_url'] = f'/gallery/preview/{foto["id"]}'
                    
            _logger.info("[GALLERY] Se encontraron %s fotos", len(fotos) if fotos else 0)
            
            # Renderizar template
            return request.render('sat.gallery_page_template', {
                'reparacion': reparacion,
                'fotos': fotos or [],
            })
        except Exception as e:
            _logger.exception("[GALLERY] Error al cargar la galería: %s", str(e))
            return request.not_found()

    @http.route('/gallery/preview/<int:foto_id>', type='http', auth='public')
    def get_preview(self, foto_id):
        """Nuevo endpoint para servir previsualizaciones optimizadas"""
        try:
            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if not foto.exists():
                return self._serve_placeholder()

            pcloud_config = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            if not pcloud_config:
                return self._serve_placeholder()

            thumb_url = foto._get_thumb_url(foto.file_id, pcloud_config)
            if not thumb_url:
                return self._serve_placeholder()

            try:
                response = requests.get(thumb_url, timeout=5)
                if response.status_code == 200:
                    headers = [
                        ('Content-Type', response.headers.get('content-type', 'image/jpeg')),
                        ('Cache-Control', 'public, max-age=7200'),
                        ('Access-Control-Allow-Origin', '*'),
                        ('X-Content-Type-Options', 'nosniff'),
                    ]
                    return Response(response.content, headers=headers)
            except:
                pass

            return self._serve_placeholder()
        except Exception as e:
            _logger.exception("[PREVIEW] Error: %s", str(e))
            return self._serve_placeholder()

    def _serve_placeholder(self):
        """Sirve una imagen placeholder"""
        try:
            module_path = os.path.dirname(os.path.dirname(__file__))
            placeholder_path = os.path.join(module_path, 'static', 'src', 'img', 'placeholder.png')
            if os.path.exists(placeholder_path):
                with open(placeholder_path, 'rb') as f:
                    return Response(
                        f.read(),
                        headers=[
                            ('Content-Type', 'image/png'),
                            ('Cache-Control', 'public, max-age=7200'),
                        ]
                    )
        except Exception as e:
            _logger.error("[PLACEHOLDER] Error: %s", str(e))
        return Response(status=404)

    @http.route('/gallery/upload/<int:reparacion_id>', type='http', auth='public', methods=['POST'], csrf=False)
    def upload_photo(self, reparacion_id, **kwargs):
        """Maneja la subida de fotos"""
        _logger.info("[UPLOAD] Iniciando subida para reparación %s", reparacion_id)
        try:
            files = request.httprequest.files.getlist('files[]')
            if not files:
                _logger.warning("[UPLOAD] No se encontraron archivos")
                return json.dumps({'error': 'No se encontraron archivos'})

            uploaded_files = []
            for file in files:
                try:
                    _logger.info("[UPLOAD] Procesando archivo: %s", file.filename)
                    foto_data = {
                        'reparacion_id': reparacion_id,
                        'nombre_foto': file.filename,
                        'foto_binario': base64.b64encode(file.read()),
                    }
                    foto = request.env['reparaciones.foto'].sudo().create(foto_data)
                    if foto:
                        uploaded_files.append({
                            'id': foto.id,
                            'nombre': foto.nombre_foto,
                            'url': foto.url_foto
                        })
                        _logger.info("[UPLOAD] Foto subida correctamente: %s", foto.id)
                except Exception as e:
                    _logger.error("[UPLOAD] Error al procesar archivo %s: %s", file.filename, str(e))

            return json.dumps({'success': True, 'files': uploaded_files})
        except Exception as e:
            _logger.exception("[UPLOAD] Error general: %s", str(e))
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
        _logger.info("[SYNC] Iniciando sincronización para reparación ID: %s", reparacion_id)
        try:
            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])
            
            pcloud_config = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            
            updated_fotos = []
            for foto in fotos:
                try:
                    thumb_url = foto._get_thumb_url(foto.file_id, pcloud_config)
                    file_url = f"/gallery/download/{foto.id}"  # Actualizar URL de descarga para forzar descarga
                    
                    if thumb_url:
                        foto.write({'url_foto': file_url})  # Almacenar la URL de descarga
                        updated_fotos.append({
                            'id': foto.id,
                            'nombre_foto': foto.nombre_foto,
                            'thumb_url': f'/gallery/preview/{foto.id}',  # Usar nuevo endpoint de vista previa
                            'download_url': file_url  # Asegurar URL de descarga correcta
                        })
                except Exception as e:
                    _logger.error("[SYNC] Error procesando foto %s: %s", foto.id, str(e))

            _logger.info("[SYNC] Actualización completada: %s fotos", len(updated_fotos))
            return {
                'success': True,
                'fotos': updated_fotos,
                'message': f'Se actualizaron {len(updated_fotos)} fotos'
            }

        except Exception as e:
            _logger.exception("[SYNC] Error en sincronización: %s", str(e))
            return {'success': False, 'error': str(e)}


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
