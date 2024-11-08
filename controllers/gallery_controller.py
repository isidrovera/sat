from odoo import http
from odoo.http import request, Response
import logging
import json
import base64

_logger = logging.getLogger(__name__)

class GalleryController(http.Controller):
    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public', website=True)
    def gallery_page(self, reparacion_id, **kwargs):
        _logger.info("[GALLERY] Accediendo a galería para reparación ID: %s", reparacion_id)
        try:
            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                _logger.error("[GALLERY] Reparación no encontrada: %s", reparacion_id)
                return request.not_found()

            # Verificar y actualizar fotos
            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])
            _logger.info("[GALLERY] Encontradas %s fotos", len(fotos))

            fotos_data = []
            for foto in fotos:
                try:
                    # Verificar enlaces
                    if foto.verify_pcloud_links():
                        thumb_url = foto._get_thumb_url(foto.file_id)
                        download_url = foto._get_file_url(foto.file_id)
                        if thumb_url and download_url:
                            fotos_data.append({
                                'id': foto.id,
                                'nombre_foto': foto.nombre_foto,
                                'thumb_url': thumb_url,
                                'download_url': download_url
                            })
                            _logger.info("[GALLERY] Foto %s procesada correctamente", foto.id)
                except Exception as e:
                    _logger.error("[GALLERY] Error procesando foto %s: %s", foto.id, str(e))

            _logger.info("[GALLERY] Renderizando galería con %s fotos", len(fotos_data))
            return request.render('sat.gallery_page_template', {
                'reparacion': reparacion,
                'fotos': fotos_data,
            })

        except Exception as e:
            _logger.exception("[GALLERY] Error general: %s", str(e))
            return request.not_found()

    @http.route('/gallery/upload/<int:reparacion_id>', type='http', auth='public', methods=['POST'], csrf=False)
    def upload_photo(self, reparacion_id, **kwargs):
        """Maneja la subida de fotos"""
        _logger.info("[UPLOAD] Iniciando subida de fotos para reparación %s", reparacion_id)
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
                    _logger.info("[UPLOAD] Foto creada con ID: %s", foto.id)

                    # Verificar enlaces después de crear
                    if foto.verify_pcloud_links():
                        uploaded_files.append({
                            'id': foto.id,
                            'nombre': foto.nombre_foto,
                            'url': foto.url_foto
                        })
                        _logger.info("[UPLOAD] Foto %s subida correctamente", foto.id)
                    else:
                        _logger.error("[UPLOAD] Error verificando enlaces para foto %s", foto.id)
                except Exception as e:
                    _logger.exception("[UPLOAD] Error procesando archivo %s: %s", file.filename, str(e))

            return json.dumps({
                'success': True, 
                'files': uploaded_files,
                'message': f'Se subieron {len(uploaded_files)} archivos correctamente'
            })

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
            # Obtener configuración de pCloud
            pcloud_config = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            if not pcloud_config:
                _logger.error("[SYNC] No se encontró configuración de pCloud")
                return {'success': False, 'error': 'No se encontró configuración de pCloud'}

            # Obtener todas las fotos de la reparación
            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])
            _logger.info("[SYNC] Encontradas %s fotos para sincronizar", len(fotos))

            # Actualizar cada foto
            updated_fotos = []
            for foto in fotos:
                try:
                    _logger.info("[SYNC] Procesando foto ID: %s", foto.id)
                    # Obtener nuevos enlaces
                    thumb_url = foto._get_thumb_url(foto.file_id, pcloud_config)
                    file_url = foto._get_file_url(foto.file_id, pcloud_config)
                    
                    if thumb_url and file_url:
                        _logger.info("[SYNC] Enlaces actualizados para foto ID: %s", foto.id)
                        foto.write({
                            'url_foto': file_url,
                            'public_link': file_url
                        })
                        updated_fotos.append({
                            'id': foto.id,
                            'nombre_foto': foto.nombre_foto,
                            'thumb_url': thumb_url,
                            'download_url': file_url
                        })
                    else:
                        _logger.warning("[SYNC] No se pudieron obtener enlaces para foto ID: %s", foto.id)
                except Exception as e:
                    _logger.error("[SYNC] Error procesando foto %s: %s", foto.id, str(e))

            _logger.info("[SYNC] Sincronización completada. Actualizadas %s fotos", len(updated_fotos))
            return {
                'success': True,
                'fotos': updated_fotos,
                'message': f'Se actualizaron {len(updated_fotos)} fotos correctamente'
            }
        except Exception as e:
            _logger.exception("[SYNC] Error en la sincronización: %s", str(e))
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