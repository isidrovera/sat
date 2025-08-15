from odoo import http
from odoo.http import request, Response
import logging
import json
import base64
import requests
import os
import time
import uuid
from werkzeug.exceptions import RequestEntityTooLarge

_logger = logging.getLogger(__name__)

class GalleryController(http.Controller):
    
    # Cache para sesiones de subida
    _upload_sessions = {}
    
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

    @http.route('/gallery/upload/validate/<int:reparacion_id>', type='json', auth='user', methods=['POST'])
    def validate_upload(self, reparacion_id, file_count=0, total_size=0):
        """Valida si la subida es posible antes de comenzar"""
        try:
            _logger.info("[VALIDATE] Validando subida: %s archivos, %s bytes", file_count, total_size)
            
            # Verificar que la reparación existe
            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                return {'success': False, 'error': 'Reparación no encontrada', 'code': 'REPARACION_NOT_FOUND'}
            
            # Verificar permisos de usuario
            if not request.env.user or request.env.user._is_public():
                return {'success': False, 'error': 'Necesitas iniciar sesión para subir archivos', 'code': 'AUTH_REQUIRED'}
            
            # Verificar límites
            max_files = 50  # Límite máximo de archivos por sesión
            max_total_size = 100 * 1024 * 1024  # 100MB total
            max_file_size = 10 * 1024 * 1024   # 10MB por archivo
            
            if file_count > max_files:
                return {'success': False, 'error': f'Máximo {max_files} archivos permitidos', 'code': 'TOO_MANY_FILES'}
            
            if total_size > max_total_size:
                return {'success': False, 'error': f'Tamaño total excede {max_total_size/1024/1024:.0f}MB', 'code': 'SIZE_EXCEEDED'}
            
            # Generar ID de sesión
            session_id = str(uuid.uuid4())
            self._upload_sessions[session_id] = {
                'reparacion_id': reparacion_id,
                'file_count': file_count,
                'uploaded': 0,
                'failed': 0,
                'results': [],
                'start_time': time.time()
            }
            
            _logger.info("[VALIDATE] Validación exitosa, sesión: %s", session_id)
            return {
                'success': True, 
                'session_id': session_id,
                'limits': {
                    'max_file_size': max_file_size,
                    'max_files': max_files,
                    'max_total_size': max_total_size
                }
            }
            
        except Exception as e:
            _logger.exception("[VALIDATE] Error en validación: %s", str(e))
            return {'success': False, 'error': 'Error interno del servidor', 'code': 'INTERNAL_ERROR'}

    @http.route('/gallery/upload/single/<session_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_single_photo(self, session_id, **kwargs):
        """Sube un solo archivo y actualiza el progreso de la sesión"""
        try:
            _logger.info("[UPLOAD_SINGLE] Subiendo archivo para sesión: %s", session_id)
            
            # Verificar sesión válida
            if session_id not in self._upload_sessions:
                return self._json_response({'success': False, 'error': 'Sesión inválida', 'code': 'INVALID_SESSION'})
            
            session_data = self._upload_sessions[session_id]
            
            # Verificar que el usuario sigue autenticado
            if not request.env.user or request.env.user._is_public():
                return self._json_response({'success': False, 'error': 'Sesión expirada, inicia sesión nuevamente', 'code': 'SESSION_EXPIRED'})
            
            # Obtener archivo
            files = request.httprequest.files.getlist('file')
            if not files:
                session_data['failed'] += 1
                return self._json_response({'success': False, 'error': 'No se encontró archivo', 'code': 'NO_FILE'})
            
            file = files[0]  # Solo procesamos un archivo
            
            # Validar archivo individual
            validation_result = self._validate_single_file(file)
            if not validation_result['valid']:
                session_data['failed'] += 1
                session_data['results'].append({
                    'filename': file.filename,
                    'success': False,
                    'error': validation_result['error']
                })
                return self._json_response({
                    'success': False, 
                    'error': validation_result['error'], 
                    'code': 'INVALID_FILE',
                    'progress': self._get_session_progress(session_id)
                })
            
            # Procesar archivo
            try:
                _logger.info("[UPLOAD_SINGLE] Procesando archivo: %s (%s bytes)", file.filename, len(file.read()))
                file.seek(0)  # Reset file pointer después de la validación
                
                foto_data = {
                    'reparacion_id': session_data['reparacion_id'],
                    'nombre_foto': file.filename,
                    'foto_binario': base64.b64encode(file.read()),
                }
                
                foto = request.env['reparaciones.foto'].sudo().create(foto_data)
                
                if foto:
                    session_data['uploaded'] += 1
                    session_data['results'].append({
                        'filename': file.filename,
                        'success': True,
                        'foto_id': foto.id,
                        'url': foto.url_foto
                    })
                    _logger.info("[UPLOAD_SINGLE] Archivo subido exitosamente: %s -> ID:%s", file.filename, foto.id)
                    
                    return self._json_response({
                        'success': True,
                        'foto_id': foto.id,
                        'filename': file.filename,
                        'progress': self._get_session_progress(session_id)
                    })
                else:
                    raise Exception("No se pudo crear el registro de foto")
                    
            except Exception as e:
                _logger.error("[UPLOAD_SINGLE] Error procesando archivo %s: %s", file.filename, str(e))
                session_data['failed'] += 1
                session_data['results'].append({
                    'filename': file.filename,
                    'success': False,
                    'error': str(e)
                })
                
                return self._json_response({
                    'success': False,
                    'error': f'Error procesando {file.filename}: {str(e)}',
                    'code': 'PROCESSING_ERROR',
                    'progress': self._get_session_progress(session_id)
                })
                
        except RequestEntityTooLarge:
            return self._json_response({'success': False, 'error': 'Archivo demasiado grande', 'code': 'FILE_TOO_LARGE'})
        except Exception as e:
            _logger.exception("[UPLOAD_SINGLE] Error general: %s", str(e))
            return self._json_response({'success': False, 'error': 'Error interno del servidor', 'code': 'INTERNAL_ERROR'})

    @http.route('/gallery/upload/progress/<session_id>', type='json', auth='user', methods=['GET'])
    def get_upload_progress(self, session_id):
        """Obtiene el progreso actual de una sesión de subida"""
        try:
            if session_id not in self._upload_sessions:
                return {'success': False, 'error': 'Sesión no encontrada'}
            
            progress = self._get_session_progress(session_id)
            return {'success': True, 'progress': progress}
            
        except Exception as e:
            _logger.exception("[PROGRESS] Error: %s", str(e))
            return {'success': False, 'error': str(e)}

    @http.route('/gallery/upload/complete/<session_id>', type='json', auth='user', methods=['POST'])
    def complete_upload_session(self, session_id):
        """Finaliza una sesión de subida y devuelve el resumen"""
        try:
            if session_id not in self._upload_sessions:
                return {'success': False, 'error': 'Sesión no encontrada'}
            
            session_data = self._upload_sessions[session_id]
            progress = self._get_session_progress(session_id)
            
            # Limpiar sesión después de obtener datos
            del self._upload_sessions[session_id]
            
            _logger.info("[COMPLETE] Sesión completada: %s subidos, %s fallidos", 
                        session_data['uploaded'], session_data['failed'])
            
            return {
                'success': True,
                'summary': {
                    'total_files': session_data['file_count'],
                    'uploaded': session_data['uploaded'],
                    'failed': session_data['failed'],
                    'duration': time.time() - session_data['start_time'],
                    'results': session_data['results']
                },
                'progress': progress
            }
            
        except Exception as e:
            _logger.exception("[COMPLETE] Error: %s", str(e))
            return {'success': False, 'error': str(e)}

    def _validate_single_file(self, file):
        """Valida un archivo individual"""
        if not file or not file.filename:
            return {'valid': False, 'error': 'Archivo vacío'}
        
        # Validar tipo de archivo
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp']
        if not any(file.filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']):
            return {'valid': False, 'error': 'Tipo de archivo no permitido'}
        
        # Validar tamaño
        file.seek(0, 2)  # Ir al final del archivo
        size = file.tell()
        file.seek(0)     # Volver al inicio
        
        max_size = 10 * 1024 * 1024  # 10MB
        if size > max_size:
            return {'valid': False, 'error': f'Archivo excede {max_size/1024/1024:.0f}MB'}
        
        if size == 0:
            return {'valid': False, 'error': 'Archivo vacío'}
        
        return {'valid': True}

    def _get_session_progress(self, session_id):
        """Calcula el progreso de una sesión"""
        if session_id not in self._upload_sessions:
            return None
        
        session_data = self._upload_sessions[session_id]
        total = session_data['file_count']
        completed = session_data['uploaded'] + session_data['failed']
        
        return {
            'total': total,
            'uploaded': session_data['uploaded'],
            'failed': session_data['failed'],
            'completed': completed,
            'percentage': (completed / total * 100) if total > 0 else 0,
            'is_complete': completed >= total
        }

    def _json_response(self, data):
        """Retorna una respuesta JSON válida"""
        return Response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')]
        )

    # MANTENER MÉTODOS EXISTENTES SIN CAMBIOS
    @http.route('/gallery/upload/<int:reparacion_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_photo(self, reparacion_id, **kwargs):
        """Maneja la subida de fotos - MÉTODO ORIGINAL MANTENIDO PARA COMPATIBILIDAD"""
        _logger.info("[UPLOAD] Iniciando subida para reparación %s", reparacion_id)
        try:
            # Verificar autenticación con mensaje específico
            if not request.env.user or request.env.user._is_public():
                return json.dumps({'success': False, 'error': 'Sesión expirada. Por favor, inicia sesión nuevamente.', 'code': 'AUTH_REQUIRED'})
            
            files = request.httprequest.files.getlist('files[]')
            if not files:
                _logger.warning("[UPLOAD] No se encontraron archivos")
                return json.dumps({'success': False, 'error': 'No se encontraron archivos', 'code': 'NO_FILES'})

            uploaded_files = []
            failed_files = []
            
            _logger.info("[UPLOAD] Procesando %s archivos", len(files))
            
            for index, file in enumerate(files):
                try:
                    _logger.info("[UPLOAD] Procesando archivo %s/%s: %s", index + 1, len(files), file.filename)
                    
                    # Validar archivo
                    validation = self._validate_single_file(file)
                    if not validation['valid']:
                        failed_files.append({
                            'filename': file.filename,
                            'error': validation['error']
                        })
                        continue
                    
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
                    else:
                        failed_files.append({
                            'filename': file.filename,
                            'error': 'No se pudo crear el registro'
                        })
                        
                except Exception as e:
                    error_msg = str(e)
                    _logger.error("[UPLOAD] Error al procesar archivo %s: %s", file.filename, error_msg)
                    failed_files.append({
                        'filename': file.filename,
                        'error': error_msg
                    })

            # Respuesta detallada con archivos exitosos y fallidos
            response_data = {
                'success': len(uploaded_files) > 0,
                'files': uploaded_files,
                'uploaded_count': len(uploaded_files),
                'failed_count': len(failed_files),
                'total_count': len(files)
            }
            
            if failed_files:
                response_data['failed_files'] = failed_files
                response_data['message'] = f'Se subieron {len(uploaded_files)} de {len(files)} archivos'
            else:
                response_data['message'] = f'Se subieron todos los {len(uploaded_files)} archivos correctamente'
            
            _logger.info("[UPLOAD] Completado: %s exitosos, %s fallidos", len(uploaded_files), len(failed_files))
            return json.dumps(response_data)
            
        except RequestEntityTooLarge:
            _logger.error("[UPLOAD] Archivo demasiado grande")
            return json.dumps({'success': False, 'error': 'Uno o más archivos son demasiado grandes', 'code': 'FILE_TOO_LARGE'})
        except Exception as e:
            _logger.exception("[UPLOAD] Error general: %s", str(e))
            return json.dumps({'success': False, 'error': f'Error interno: {str(e)}', 'code': 'INTERNAL_ERROR'})

    @http.route('/gallery/delete/<int:foto_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def delete_photo(self, foto_id):
        """Elimina una foto"""
        try:
            # Verificar autenticación
            if not request.env.user or request.env.user._is_public():
                return json.dumps({'success': False, 'error': 'Sesión expirada. Por favor, inicia sesión nuevamente.', 'code': 'AUTH_REQUIRED'})
            
            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if foto.exists():
                foto.unlink()
                return json.dumps({'success': True})
            return json.dumps({'success': False, 'error': 'Foto no encontrada', 'code': 'NOT_FOUND'})
        except Exception as e:
            return json.dumps({'success': False, 'error': str(e), 'code': 'INTERNAL_ERROR'})

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
                    file_url = f"/gallery/download/{foto.id}"
                    
                    if thumb_url:
                        foto.write({'url_foto': file_url})
                        updated_fotos.append({
                            'id': foto.id,
                            'nombre_foto': foto.nombre_foto,
                            'thumb_url': f'/gallery/preview/{foto.id}',
                            'download_url': file_url
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
        """Devuelve la imagen directamente para descargar"""
        foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
        if not foto.exists():
            _logger.error(f"[DOWNLOAD_PHOTO] Foto con ID {foto_id} no encontrada")
            return request.not_found()
    
        content_info = foto.get_download_content()
        if not content_info:
            _logger.error(f"[DOWNLOAD_PHOTO] No se pudo obtener contenido para la foto con ID {foto_id}")
            return request.not_found()
    
        return request.make_response(
            base64.b64decode(content_info['content']),
            headers=[
                ('Content-Type', content_info['content_type']),
                ('Content-Disposition', f'attachment; filename="{content_info["filename"]}"')
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