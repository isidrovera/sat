# -*- coding: utf-8 -*-
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
    """
    Controlador de galería con:
    - Vista pública de galería y preview.
    - Subida DIRECTA y rápida a pCloud (uploadfile).
    - (Opcional) Upload link con createuploadlink.
    - Registro en Odoo tras subir a pCloud.
    - Eliminación de fotos (requiere login).
    - Descarga individual y en lote (usa método del modelo).
    - Limpieza y obtención de secuencias.
    - Verificación de sesión bajo demanda.
    """

    # Cache en-memoria por proceso para sesiones legacy (fallback)
    _upload_sessions = {}

    # --------------------- Utilidades internas ---------------------

    def _json_response(self, data, status=200, headers=None):
        """Respuesta JSON segura."""
        try:
            return request.make_json_response(data, status=status, headers=headers)
        except Exception:
            return Response(
                json.dumps(data, ensure_ascii=False),
                status=status,
                headers=[('Content-Type', 'application/json; charset=utf-8')] + (headers or []),
            )

    def _serve_placeholder(self):
        """Sirve una imagen placeholder si no hay preview real."""
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

    def _get_safe_sequence(self, reparacion_id, preferred_sequence=None):
        """Obtiene una secuencia segura evitando duplicados."""
        foto_obj = request.env['reparaciones.foto'].sudo()

        if preferred_sequence:
            existing = foto_obj.search([
                ('reparacion_id', '=', reparacion_id),
                ('sequence', '=', preferred_sequence)
            ], limit=1)
            if not existing:
                return preferred_sequence

        max_sequence = foto_obj.search([
            ('reparacion_id', '=', reparacion_id)
        ], order='sequence desc', limit=1)

        return (max_sequence.sequence if max_sequence else 0) + 1

    def _get_pcloud_host(self):
        """Devuelve el host de pCloud, por defecto https://api.pcloud.com"""
        pc = request.env['pcloud.configuracion'].sudo().search([], limit=1)
        host = (pc.hostname or '').strip() if pc else ''
        return host or 'https://api.pcloud.com'

    def _get_pcloud_token(self):
        pc = request.env['pcloud.configuracion'].sudo().search([], limit=1)
        return (pc.access_token or '').strip() if pc else ''

    def _ensure_logged_user_json(self):
        """Si no hay usuario logueado, devuelve dict con AUTH_REQUIRED y url de login (para JSON)."""
        if not request.env.user or request.env.user._is_public():
            return {
                'success': False,
                'code': 'AUTH_REQUIRED',
                'error': 'Necesitas iniciar sesión',
                'redirect_login': '/web/login?redirect=' + request.httprequest.path
            }
        return None

    # --------------------- Vistas públicas ---------------------

    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public', website=True)
    def gallery_page(self, reparacion_id, **kwargs):
        """Renderiza la página de galería (pública)."""
        _logger.info("[GALLERY] Accediendo a galería para reparación ID: %s", reparacion_id)
        try:
            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                _logger.error("[GALLERY] Reparación no encontrada: %s", reparacion_id)
                return request.not_found()

            foto_model = request.env['reparaciones.foto'].sudo()
            fotos = foto_model.get_photos_preview(reparacion_id)

            if fotos:
                for foto in fotos:
                    foto['thumb_url'] = f'/gallery/preview/{foto["id"]}'

            _logger.info("[GALLERY] Se encontraron %s fotos", len(fotos) if fotos else 0)

            return request.render('sat.gallery_page_template', {
                'reparacion': reparacion,
                'fotos': fotos or [],
            })
        except Exception as e:
            _logger.exception("[GALLERY] Error al cargar la galería: %s", str(e))
            return request.not_found()

    @http.route('/gallery/preview/<int:foto_id>', type='http', auth='public')
    def get_preview(self, foto_id):
        """Sirve previsualizaciones (thumb) con caché."""
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
            except Exception:
                pass

            return self._serve_placeholder()
        except Exception as e:
            _logger.exception("[PREVIEW] Error: %s", str(e))
            return self._serve_placeholder()

    # --------------------- Validación y progreso (fallback legacy) ---------------------

    @http.route('/gallery/upload/validate/<int:reparacion_id>', type='json', auth='public', methods=['POST'])
    def validate_upload(self, reparacion_id, file_count=0, total_size=0):
        """
        Valida previo a subir. SOLO exige login si luego subirás (JS decide).
        Mantiene compatibilidad con flujo legacy por sesión.
        """
        try:
            _logger.info("[VALIDATE] Reparación %s | files=%s, size=%s", reparacion_id, file_count, total_size)

            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                return {'success': False, 'error': 'Reparación no encontrada', 'code': 'REPARACION_NOT_FOUND'}

            # Si no hay login, no rompemos la vista: informamos que hará falta para subir
            if not request.env.user or request.env.user._is_public():
                return {
                    'success': True,
                    'session_id': None,
                    'limits': {'max_file_size': 10 * 1024 * 1024, 'max_files': 50, 'max_total_size': 100 * 1024 * 1024},
                    'auth': {'required_for_upload': True}
                }

            max_files = 50
            max_total_size = 100 * 1024 * 1024
            max_file_size = 10 * 1024 * 1024

            if file_count > max_files:
                return {'success': False, 'error': f'Máximo {max_files} archivos permitidos', 'code': 'TOO_MANY_FILES'}

            if total_size > max_total_size:
                return {'success': False, 'error': f'Tamaño total excede {max_total_size/1024/1024:.0f}MB', 'code': 'SIZE_EXCEEDED'}

            session_id = str(uuid.uuid4())
            self._upload_sessions[session_id] = {
                'reparacion_id': reparacion_id,
                'file_count': file_count,
                'uploaded': 0,
                'failed': 0,
                'results': [],
                'start_time': time.time()
            }

            _logger.info("[VALIDATE] OK, sesión: %s", session_id)
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
            _logger.exception("[VALIDATE] Error: %s", str(e))
            return {'success': False, 'error': 'Error interno del servidor', 'code': 'INTERNAL_ERROR'}

    @http.route('/gallery/upload/single/<session_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_single_photo(self, session_id, **kwargs):
        """Sube 1 archivo (fallback legacy, no recomendado si ya usas subida directa a pCloud)."""
        try:
            _logger.info("[UPLOAD_SINGLE] Sesión: %s", session_id)

            if session_id not in self._upload_sessions:
                return self._json_response({'success': False, 'error': 'Sesión inválida', 'code': 'INVALID_SESSION'})

            if not request.env.user or request.env.user._is_public():
                return self._json_response({
                    'success': False,
                    'error': 'Sesión expirada, inicia sesión nuevamente',
                    'code': 'SESSION_EXPIRED',
                    'redirect_login': '/web/login?redirect=' + request.httprequest.path
                }, status=401)

            session_data = self._upload_sessions[session_id]
            files = request.httprequest.files.getlist('file')
            if not files:
                session_data['failed'] += 1
                return self._json_response({'success': False, 'error': 'No se encontró archivo', 'code': 'NO_FILE'})

            file = files[0]

            sequence = request.httprequest.form.get('sequence')
            if not sequence:
                foto_obj = request.env['reparaciones.foto'].sudo()
                max_sequence = foto_obj.search([
                    ('reparacion_id', '=', session_data['reparacion_id'])
                ], order='sequence desc', limit=1)
                sequence = (max_sequence.sequence if max_sequence else 0) + 1
            else:
                try:
                    sequence = int(sequence)
                except ValueError:
                    sequence = 1

            def _validate_single_file(f):
                if not f or not f.filename:
                    return {'valid': False, 'error': 'Archivo vacío'}
                if not any(f.filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']):
                    return {'valid': False, 'error': 'Tipo de archivo no permitido'}
                f.seek(0, 2)
                size = f.tell()
                f.seek(0)
                max_size = 10 * 1024 * 1024
                if size > max_size:
                    return {'valid': False, 'error': f'Archivo excede {max_size/1024/1024:.0f}MB'}
                if size == 0:
                    return {'valid': False, 'error': 'Archivo vacío'}
                return {'valid': True}

            validation_result = _validate_single_file(file)
            if not validation_result['valid']:
                session_data['failed'] += 1
                session_data['results'].append({'filename': file.filename, 'success': False, 'error': validation_result['error']})
                return self._json_response({
                    'success': False,
                    'error': validation_result['error'],
                    'code': 'INVALID_FILE',
                    'progress': self._get_session_progress(session_id)
                })

            try:
                _logger.info("[UPLOAD_SINGLE] Procesando: %s", file.filename)
                data_bytes = file.read()
                file.seek(0)
                foto_data = {
                    'reparacion_id': session_data['reparacion_id'],
                    'nombre_foto': file.filename,
                    'foto_binario': base64.b64encode(data_bytes),
                    'sequence': sequence,
                }

                existing_foto = request.env['reparaciones.foto'].sudo().search([
                    ('reparacion_id', '=', session_data['reparacion_id']),
                    ('sequence', '=', sequence)
                ], limit=1)

                if existing_foto:
                    _logger.warning("[UPLOAD_SINGLE] Secuencia %s existe, re-asignando", sequence)
                    max_sequence = request.env['reparaciones.foto'].sudo().search([
                        ('reparacion_id', '=', session_data['reparacion_id'])
                    ], order='sequence desc', limit=1)
                    sequence = (max_sequence.sequence if max_sequence else 0) + 1
                    foto_data['sequence'] = sequence

                foto = request.env['reparaciones.foto'].sudo().create(foto_data)

                if foto:
                    session_data['uploaded'] += 1
                    session_data['results'].append({
                        'filename': file.filename,
                        'success': True,
                        'foto_id': foto.id,
                        'sequence': foto.sequence,
                        'url': foto.url_foto
                    })
                    return self._json_response({
                        'success': True,
                        'foto_id': foto.id,
                        'sequence': foto.sequence,
                        'filename': file.filename,
                        'progress': self._get_session_progress(session_id)
                    })
                else:
                    raise Exception("No se pudo crear el registro de foto")

            except Exception as e:
                error_msg = str(e)
                _logger.error("[UPLOAD_SINGLE] Error: %s", error_msg)
                session_data['failed'] += 1
                session_data['results'].append({'filename': file.filename, 'success': False, 'error': error_msg})
                return self._json_response({
                    'success': False,
                    'error': f'Error procesando {file.filename}: {error_msg}',
                    'code': 'PROCESSING_ERROR',
                    'progress': self._get_session_progress(session_id)
                })

        except RequestEntityTooLarge:
            return self._json_response({'success': False, 'error': 'Archivo demasiado grande', 'code': 'FILE_TOO_LARGE'}, status=413)
        except Exception as e:
            _logger.exception("[UPLOAD_SINGLE] Error general: %s", str(e))
            return self._json_response({'success': False, 'error': 'Error interno del servidor', 'code': 'INTERNAL_ERROR'}, status=500)

    @http.route('/gallery/upload/progress/<session_id>', type='json', auth='user', methods=['GET'])
    def get_upload_progress(self, session_id):
        """Estado del progreso (legacy)."""
        try:
            if session_id not in self._upload_sessions:
                return {'success': False, 'error': 'Sesión no encontrada'}

            return {'success': True, 'progress': self._get_session_progress(session_id)}
        except Exception as e:
            _logger.exception("[PROGRESS] Error: %s", str(e))
            return {'success': False, 'error': str(e)}

    @http.route('/gallery/upload/complete/<session_id>', type='json', auth='user', methods=['POST'])
    def complete_upload_session(self, session_id):
        """Finaliza sesión (legacy)."""
        try:
            if session_id not in self._upload_sessions:
                return {'success': False, 'error': 'Sesión no encontrada'}

            session_data = self._upload_sessions[session_id]
            progress = self._get_session_progress(session_id)
            del self._upload_sessions[session_id]

            _logger.info("[COMPLETE] Subidos=%s, fallidos=%s", session_data['uploaded'], session_data['failed'])
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

    def _get_session_progress(self, session_id):
        """Calcula progreso (legacy)."""
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

    # --------------------- Subida directa y registro pCloud ---------------------

    @http.route('/gallery/pcloud/direct-upload/<int:reparacion_id>', type='json', auth='user', methods=['POST'])
    def pcloud_direct_upload_info(self, reparacion_id):
        """
        Devuelve info para subida DIRECTA con uploadfile (rápida).
        El JS puede optar por POST directo a /gallery/pcloud/upload-direct/<id>.
        """
        start_time = time.time()
        _logger.info("[PCLOUD_DIRECT] Preparando subida directa | rep=%s", reparacion_id)

        try:
            # Requiere login solo aquí (subir)
            need = self._ensure_logged_user_json()
            if need:
                return need

            env = request.env
            reparacion = env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                return {'success': False, 'error': 'Reparación no encontrada'}

            token = self._get_pcloud_token()
            if not token:
                return {'success': False, 'error': 'Configuración pCloud faltante'}

            host = self._get_pcloud_host()

            # Valida token rápido
            try:
                v = requests.get(f"{host}/userinfo", params={'access_token': token}, timeout=6)
                jv = v.json() if v.content else {}
                if v.status_code != 200 or jv.get('result') != 0:
                    return {'success': False, 'error': 'Token inválido o sesión pCloud no aceptada', 'code': 'PCLOUD_AUTH'}
            except Exception as e:
                _logger.exception("[PCLOUD_DIRECT] userinfo error")
                return {'success': False, 'error': 'No se pudo validar token con pCloud', 'code': 'PCLOUD_AUTH'}

            folder_id = self._get_folder_id_fast(reparacion, request.env['pcloud.configuracion'].sudo().search([], limit=1))
            if not folder_id:
                return {'success': False, 'error': 'Error obteniendo carpeta', 'code': 'PCLOUD_FOLDER'}

            elapsed = time.time() - start_time
            _logger.info("[PCLOUD_DIRECT] Listo en %.2fs", elapsed)

            return {
                'success': True,
                'method': 'direct_upload',
                'folder_id': folder_id,
                'upload_endpoint': f"{host}/uploadfile",
                'processing_time': round(elapsed, 2),
            }

        except Exception as e:
            elapsed = time.time() - start_time
            _logger.exception("[PCLOUD_DIRECT] Error: %s", str(e))
            return {'success': False, 'error': f'Error interno: {str(e)}', 'processing_time': round(elapsed, 2)}

    @http.route('/gallery/pcloud/upload-direct/<int:reparacion_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def pcloud_upload_direct(self, reparacion_id, **kwargs):
        """
        Subida DIRECTA a pCloud con uploadfile (máxima velocidad).
        Recibe 'file' y opcional 'sequence'.
        """
        _logger.info("[PCLOUD_UPLOAD_DIRECT] Iniciando subida directa rep=%s", reparacion_id)
        try:
            # Requiere login
            if not request.env.user or request.env.user._is_public():
                return self._json_response({
                    'success': False,
                    'error': 'Necesitas iniciar sesión',
                    'code': 'AUTH_REQUIRED',
                    'redirect_login': '/web/login?redirect=' + request.httprequest.path
                }, status=401)

            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                return self._json_response({'success': False, 'error': 'Reparación no encontrada'})

            token = self._get_pcloud_token()
            host = self._get_pcloud_host()
            if not token:
                return self._json_response({'success': False, 'error': 'Configuración pCloud faltante'})

            files = request.httprequest.files.getlist('file')
            if not files:
                return self._json_response({'success': False, 'error': 'No se encontró archivo'})

            file = files[0]
            seq_raw = request.httprequest.form.get('sequence')
            try:
                sequence = int(seq_raw) if seq_raw else self._get_safe_sequence(reparacion_id)
            except Exception:
                sequence = self._get_safe_sequence(reparacion_id)

            folder_id = self._get_folder_id_fast(reparacion, request.env['pcloud.configuracion'].sudo().search([], limit=1))
            if not folder_id:
                return self._json_response({'success': False, 'error': 'Error obteniendo carpeta'})

            upload_url = f"{host}/uploadfile"
            upload_files = {'file': (file.filename, file.stream, file.mimetype)}
            upload_data = {
                'access_token': token,
                'folderid': folder_id,
                'renameifexists': 1,
                'nopartial': 1
            }

            rp = requests.post(upload_url, files=upload_files, data=upload_data, timeout=60)
            jr = rp.json() if rp.content else {}

            if rp.status_code == 200 and jr.get('result') == 0:
                meta = (jr.get('metadata') or [{}])[0]
                file_id = meta.get('fileid')
                if not file_id:
                    return self._json_response({'success': False, 'error': 'pCloud no devolvió fileid'})

                Foto = request.env['reparaciones.foto'].sudo()
                rec = Foto.create({
                    'reparacion_id': reparacion_id,
                    'nombre_foto': file.filename,
                    'sequence': sequence,
                    'file_id': str(file_id),
                    'state': 'done',
                    'size': meta.get('size', getattr(file, 'content_length', 0) or 0),
                    'mimetype': meta.get('contenttype', file.mimetype)
                })

                _logger.info("[PCLOUD_UPLOAD_DIRECT] Foto creada ID=%s file_id=%s", rec.id, file_id)
                return self._json_response({
                    'success': True,
                    'foto_id': rec.id,
                    'file_id': file_id,
                    'filename': file.filename,
                    'sequence': rec.sequence,
                    'method': 'direct_upload'
                })

            return self._json_response({
                'success': False,
                'error': f"Error de pCloud: {jr.get('error','desconocido')}",
                'raw': jr
            })

        except Exception as e:
            _logger.exception("[PCLOUD_UPLOAD_DIRECT] Error: %s", str(e))
            return self._json_response({'success': False, 'error': f'Error interno: {str(e)}'}, status=500)

    @http.route('/gallery/pcloud/register', type='json', auth='user', methods=['POST'])
    def pcloud_register_file(self, **payload):
        """
        Registra en Odoo una foto YA subida a pCloud.
        payload:
        {
          "reparacion_id": 123,
          "sequence": 7,
          "filename": "image.jpg",
          "pcloud": {"fileid": "7783...", "size": 123456, "contenttype": "image/jpeg"}
        }
        """
        try:
            need = self._ensure_logged_user_json()
            if need:
                return need

            # Aceptar payload robustamente si entra vacío
            if not payload:
                try:
                    payload = request.httprequest.get_json(silent=True) or {}
                except Exception:
                    payload = {}

            reparacion_id = int(payload.get('reparacion_id') or 0)
            sequence = int(payload.get('sequence') or 0)
            filename = payload.get('filename') or 'foto.jpg'
            pcloud_meta = payload.get('pcloud') or {}
            fileid = pcloud_meta.get('fileid')

            if not (reparacion_id and fileid):
                return {'success': False, 'error': 'Datos incompletos'}

            env = request.env
            Foto = env['reparaciones.foto'].sudo()
            pconf = env['pcloud.configuracion'].sudo().search([], limit=1)
            if not pconf:
                return {'success': False, 'error': 'Config pCloud no disponible'}

            if not sequence:
                sequence = self._get_safe_sequence(reparacion_id)

            rec = Foto.create({
                'reparacion_id': reparacion_id,
                'nombre_foto': filename,
                'sequence': sequence,
                'file_id': str(fileid),
                'mimetype': pcloud_meta.get('contenttype', 'application/octet-stream'),
                'size': int(pcloud_meta.get('size') or 0),
                'state': 'done',
            })

            file_url = rec._get_file_url(rec.file_id, pconf)
            thumb_url = rec._get_thumb_url(rec.file_id, pconf)
            rec.write({
                'url_foto': file_url,
                'public_link': rec._create_public_link(rec.file_id, pconf) or False,
            })

            return {
                'success': True,
                'id': rec.id,
                'file_id': rec.file_id,
                'download_url': file_url,
                'thumb_url': thumb_url,
            }

        except Exception as e:
            request.env.cr.rollback()
            return {'success': False, 'error': str(e)}

    # --------------------- Upload link (opcional) ---------------------

    @http.route('/gallery/pcloud/uploadlink/<int:reparacion_id>', type='json', auth='user', methods=['POST'])
    def get_upload_link(self, reparacion_id, **kw):
        """
        (Opcional) Crea upload link (createuploadlink) y devuelve endpoint + code.
        Se robusteció el acceso al payload para evitar AttributeError de jsonrequest.
        """
        try:
            # Requiere login solo para subir
            need = self._ensure_logged_user_json()
            if need:
                return need

            # Payload robusto: primero **kw, luego intento JSON crudo
            try:
                payload = kw or request.httprequest.get_json(silent=True) or {}
            except Exception:
                payload = {}

            file_count = int(payload.get('file_count') or 1)
            total_size = int(payload.get('total_size') or 10_000_000)

            rep = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not rep.exists():
                return {'success': False, 'error': 'Reparación no encontrada'}

            # Asegurar carpeta (usa tu método si existe; si no, uno rápido)
            folder_id = None
            if hasattr(rep, 'create_folder_in_pcloud'):
                folder_id = rep.create_folder_in_pcloud()
            if not folder_id:
                folder_id = self._get_folder_id_fast(rep, request.env['pcloud.configuracion'].sudo().search([], limit=1))
            if not folder_id:
                return {'success': False, 'error': 'Error creando/obteniendo carpeta en pCloud'}

            token = self._get_pcloud_token()
            host = self._get_pcloud_host()
            if not token:
                return {'success': False, 'error': 'Falta configuración de pCloud'}

            # Validar token antes
            try:
                u = requests.get(f"{host}/userinfo", params={'access_token': token}, timeout=8)
                uj = u.json() if u.content else {}
                if u.status_code != 200 or uj.get('result') != 0:
                    return {'success': False, 'code': 'PCLOUD_AUTH', 'error': f"Token inválido: {uj.get('error','sin detalle')}"}
            except Exception:
                _logger.exception("[UPLOAD_LINK] userinfo error")
                return {'success': False, 'code': 'PCLOUD_AUTH', 'error': 'No se pudo validar token con pCloud'}

            # Crear upload link
            try:
                url = f"{host}/createuploadlink"
                params = {
                    'access_token': token,
                    'folderid': folder_id,
                    'maxfiles': file_count,
                    'maxspace': total_size,
                    'comment': f"Upload Odoo Reparación {rep.name or rep.id}",
                }
                r = requests.get(url, params=params, timeout=12)
                data = r.json() if r.content else {}
                if r.status_code == 200 and data.get('result') == 0 and data.get('code'):
                    return {
                        'success': True,
                        'endpoint': 'https://api.pcloud.com/uploadtolink',
                        'code': data['code'],
                    }
                _logger.error("[UPLOAD_LINK] Error pCloud: %s", data)
                return {'success': False, 'error': f"pCloud error: {data.get('error','sin detalle')}", 'pcloud': data}
            except Exception:
                _logger.exception('[UPLOAD_LINK] createuploadlink error')
                return {'success': False, 'error': 'Error creando upload link en pCloud'}

        except Exception:
            _logger.exception('get_upload_link error')
            return {'success': False, 'error': 'Error interno'}

    @http.route('/gallery/pcloud/proxy-upload', type='http', auth='user', methods=['POST'], csrf=False)
    def proxy_upload(self, **kw):
        """
        Fallback por CORS: recibe 'code' + 'file' y reenvía a uploadtolink (público).
        """
        try:
            if not request.env.user or request.env.user._is_public():
                return self._json_response({
                    'success': False, 'error': 'Necesitas iniciar sesión',
                    'code': 'AUTH_REQUIRED',
                    'redirect_login': '/web/login?redirect=' + request.httprequest.path
                }, status=401)

            code = request.httprequest.form.get('code')
            f = request.httprequest.files.get('file')
            if not code or not f:
                return request.make_json_response({'success': False, 'error': 'Faltan parámetros'}, status=400)

            files = {'file': (f.filename, f.stream, f.mimetype)}
            data = {'code': code}
            r = requests.post('https://api.pcloud.com/uploadtolink', data=data, files=files, timeout=120)
            jr = r.json() if r.content else {}
            ok = (r.status_code == 200 and jr.get('result') == 0)
            return request.make_json_response({'success': ok, 'raw': jr}, status=200 if ok else 500)
        except Exception as e:
            _logger.exception('Error en proxy_upload: %s', e)
            return request.make_json_response({'success': False, 'error': 'Proxy error'}, status=500)

    # --------------------- Sync / eliminación / descarga ---------------------

    @http.route('/gallery/sync/<int:reparacion_id>', type='json', auth='user', methods=['POST'])
    def sync_from_pcloud(self, reparacion_id, **kw):
        """
        Sincroniza archivos nuevos del folder pCloud -> crea reparaciones.foto (idempotente por file_id).
        """
        try:
            need = self._ensure_logged_user_json()
            if need:
                return need

            env = request.env
            reparacion = env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                return {'success': False, 'error': 'Reparación no encontrada'}

            pcloud_config = env['pcloud.configuracion'].sudo().search([], limit=1)
            if not pcloud_config or not pcloud_config.access_token:
                return {'success': False, 'error': 'Falta configuración de pCloud'}

            folder_id = reparacion._ensure_pcloud_folder() if hasattr(reparacion, '_ensure_pcloud_folder') else None
            if not folder_id:
                folder_id = self._get_folder_id_fast(reparacion, pcloud_config)

            host = self._get_pcloud_host()
            list_url = f"{host}/listfolder"
            params = {'access_token': pcloud_config.access_token, 'folderid': folder_id}
            r = requests.get(list_url, params=params, timeout=15)
            data = r.json() if r.content else {}
            if r.status_code != 200 or data.get('result') != 0:
                return {'success': False, 'error': f"listfolder error: {data}"}

            contents = data.get('metadata', {}).get('contents', [])
            Foto = env['reparaciones.foto'].sudo()

            created = 0
            skipped = 0
            for it in contents:
                if it.get('isfolder'):
                    continue
                file_id = str(it.get('fileid'))
                if Foto.search_count([('reparacion_id', '=', reparacion.id), ('file_id', '=', file_id)]):
                    skipped += 1
                    continue

                vals = {
                    'reparacion_id': reparacion.id,
                    'nombre_foto': it.get('name') or f'foto_{file_id}.jpg',
                    'file_id': file_id,
                    'state': 'done',
                    'size': it.get('size') or 0,
                    'mimetype': it.get('contenttype') or 'application/octet-stream',
                }
                Foto.create(vals)
                created += 1

            return {'success': True, 'message': f'Sync OK: {created} creadas, {skipped} ya existían.'}
        except Exception as e:
            _logger.exception('Error en sync_from_pcloud: %s', e)
            return {'success': False, 'error': 'Error interno'}

    @http.route('/gallery/delete/<int:foto_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def delete_photo(self, foto_id):
        """Elimina una foto (requiere login)."""
        try:
            if not request.env.user or request.env.user._is_public():
                return self._json_response({
                    'success': False,
                    'error': 'Sesión expirada. Por favor, inicia sesión.',
                    'code': 'AUTH_REQUIRED',
                    'redirect_login': '/web/login?redirect=' + request.httprequest.path
                }, status=401)

            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if foto.exists():
                foto.unlink()
                return self._json_response({'success': True})
            return self._json_response({'success': False, 'error': 'Foto no encontrada', 'code': 'NOT_FOUND'})
        except Exception as e:
            return self._json_response({'success': False, 'error': str(e), 'code': 'INTERNAL_ERROR'}, status=500)

    @http.route('/gallery/download/<int:foto_id>', type='http', auth='public')
    def download_photo(self, foto_id):
        """Descarga individual."""
        foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
        if not foto.exists():
            _logger.error(f"[DOWNLOAD_PHOTO] Foto ID {foto_id} no encontrada")
            return request.not_found()

        content_info = foto.get_download_content()
        if not content_info:
            _logger.error(f"[DOWNLOAD_PHOTO] No se pudo obtener contenido para foto ID {foto_id}")
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
        """Descarga en ZIP (usa implementación de modelo get_photos_zip)."""
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

    # --------------------- Secuencias / sesión ---------------------

    @http.route('/gallery/next-sequence/<int:reparacion_id>', type='http', auth='user', methods=['GET'])
    def get_next_sequence(self, reparacion_id):
        """Siguiente secuencia disponible (requiere login)."""
        try:
            if not request.env.user or request.env.user._is_public():
                return self._json_response({
                    'success': False, 'error': 'Sesión expirada', 'code': 'AUTH_REQUIRED',
                    'redirect_login': '/web/login?redirect=' + request.httprequest.path
                }, status=401)

            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                return self._json_response({'success': False, 'error': 'Reparación no encontrada', 'code': 'REPARACION_NOT_FOUND'}, status=404)

            foto_obj = request.env['reparaciones.foto'].sudo()
            max_sequence = foto_obj.search([('reparacion_id', '=', reparacion_id)], order='sequence desc', limit=1)
            next_sequence = (max_sequence.sequence if max_sequence else 0) + 1

            return self._json_response({'success': True, 'next_sequence': next_sequence, 'reparacion_id': reparacion_id})
        except Exception as e:
            _logger.exception("[NEXT_SEQUENCE] Error: %s", str(e))
            return self._json_response({'success': False, 'error': 'Error interno del servidor', 'code': 'INTERNAL_ERROR'}, status=500)

    @http.route('/gallery/cleanup-sequences/<int:reparacion_id>', type='json', auth='user', methods=['POST'])
    def cleanup_duplicate_sequences(self, reparacion_id):
        """Reorganiza secuencias consecutivas (requiere login)."""
        try:
            need = self._ensure_logged_user_json()
            if need:
                return need

            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                return {'success': False, 'error': 'Reparación no encontrada', 'code': 'REPARACION_NOT_FOUND'}

            foto_obj = request.env['reparaciones.foto'].sudo()
            fotos = foto_obj.search([('reparacion_id', '=', reparacion_id)], order='create_date asc')
            if not fotos:
                return {'success': True, 'message': 'No hay fotos para limpiar'}

            cleaned_count = 0
            for index, foto in enumerate(fotos, start=1):
                if foto.sequence != index:
                    foto.write({'sequence': index})
                    cleaned_count += 1

            return {
                'success': True,
                'cleaned_count': cleaned_count,
                'total_fotos': len(fotos),
                'message': f'Se reorganizaron {cleaned_count} fotos'
            }

        except Exception as e:
            _logger.exception("[CLEANUP_SEQUENCES] Error: %s", str(e))
            return {'success': False, 'error': 'Error interno del servidor', 'code': 'INTERNAL_ERROR'}

    @http.route('/web/session/check', type='http', auth='public', methods=['POST'], csrf=False)
    def check_session_status(self):
        """Verifica estado de sesión; no rompe vista pública."""
        try:
            if request.env.user and not request.env.user._is_public():
                result = {'success': True, 'uid': request.env.user.id, 'username': request.env.user.name, 'is_authenticated': True}
            else:
                result = {'success': True, 'uid': False, 'username': None, 'is_authenticated': False}
            return self._json_response(result)
        except Exception as e:
            _logger.warning("[SESSION_CHECK] Error: %s", str(e))
            return self._json_response({'success': False, 'error': 'Error verificando sesión', 'uid': False, 'is_authenticated': False}, status=500)

    # --------------------- Soporte pCloud: folders ---------------------

    def _get_folder_id_fast(self, reparacion, pcloud_config):
        """Obtiene/crea folder destino rápidamente."""
        _logger.info("[FOLDER_FAST] Resolviendo folder_id")
        try:
            machine_name = reparacion.maquina_id.name.name if getattr(reparacion, 'maquina_id', False) and getattr(reparacion.maquina_id, 'name', False) else 'Sin_Maquina'
            serie = reparacion.serie_id or 'Sin_Serie'
            folder_name = f"{machine_name}_{serie}"

            root_folder_id = self._get_or_create_folder_fast('fotos_reparaciones', 0, pcloud_config, timeout=6)
            if not root_folder_id:
                raise Exception("No se pudo obtener carpeta raíz")

            target_folder_id = self._get_or_create_folder_fast(folder_name, root_folder_id, pcloud_config, timeout=8)
            if not target_folder_id:
                raise Exception(f"No se pudo obtener carpeta {folder_name}")

            return target_folder_id
        except Exception as e:
            _logger.error("[FOLDER_FAST] Error: %s", str(e))
            return None

    def _get_or_create_folder_fast(self, folder_name, parent_id, pcloud_config, timeout=6):
        """Listar y crear carpeta en pCloud con timeouts cortos."""
        try:
            host = (pcloud_config.hostname or 'https://api.pcloud.com').strip()
            token = (pcloud_config.access_token or '').strip()
            if not token:
                raise Exception("Token pCloud vacío")

            # listfolder
            list_url = f"{host}/listfolder"
            params = {'access_token': token, 'folderid': parent_id, 'nofiles': 1}
            response = requests.get(list_url, params=params, timeout=timeout)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code} listando carpetas")

            result = response.json() if response.content else {}
            if result.get('result') != 0:
                raise Exception(f"pCloud error listando: {result.get('error')}")

            for item in result.get('metadata', {}).get('contents', []):
                if item.get('isfolder') and item.get('name') == folder_name:
                    return item.get('folderid')

            # createfolder
            create_url = f"{host}/createfolder"
            create_params = {'access_token': token, 'name': folder_name, 'folderid': parent_id}
            create_response = requests.get(create_url, params=create_params, timeout=timeout)
            if create_response.status_code != 200:
                raise Exception(f"HTTP {create_response.status_code} creando carpeta")

            create_result = create_response.json() if create_response.content else {}
            if create_result.get('result') != 0:
                raise Exception(f"pCloud error creando carpeta: {create_result.get('error', 'desconocido')}")

            new_folder_id = create_result.get('metadata', {}).get('folderid')
            if not new_folder_id:
                raise Exception("pCloud no devolvió folderid")

            return new_folder_id
        except requests.exceptions.Timeout:
            _logger.error("[FOLDER_FAST] Timeout procesando carpeta '%s'", folder_name)
            return None
        except Exception as e:
            _logger.error("[FOLDER_FAST] Error '%s': %s", folder_name, str(e))
            return None

    # --------------------- Upload legacy masivo (compatibilidad) ---------------------

    @http.route('/gallery/upload/<int:reparacion_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_photo(self, reparacion_id, **kwargs):
        """Compatibilidad: subida múltiple al binario de Odoo (menos rápida que pCloud)."""
        _logger.info("[UPLOAD] Iniciando subida para reparación %s", reparacion_id)
        try:
            if not request.env.user or request.env.user._is_public():
                return json.dumps({
                    'success': False,
                    'error': 'Sesión expirada. Por favor, inicia sesión nuevamente.',
                    'code': 'AUTH_REQUIRED',
                    'redirect_login': '/web/login?redirect=' + request.httprequest.path
                })

            files = request.httprequest.files.getlist('files[]')
            if not files:
                _logger.warning("[UPLOAD] No se encontraron archivos")
                return json.dumps({'success': False, 'error': 'No se encontraron archivos', 'code': 'NO_FILES'})

            uploaded_files = []
            failed_files = []

            def _validate_single_file(f):
                if not f or not f.filename:
                    return {'valid': False, 'error': 'Archivo vacío'}
                if not any(f.filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']):
                    return {'valid': False, 'error': 'Tipo de archivo no permitido'}
                f.seek(0, 2)
                size = f.tell()
                f.seek(0)
                max_size = 10 * 1024 * 1024
                if size > max_size:
                    return {'valid': False, 'error': f'Archivo excede {max_size/1024/1024:.0f}MB'}
                if size == 0:
                    return {'valid': False, 'error': 'Archivo vacío'}
                return {'valid': True}

            for index, file in enumerate(files):
                try:
                    validation = _validate_single_file(file)
                    if not validation['valid']:
                        failed_files.append({'filename': file.filename, 'error': validation['error']})
                        continue

                    foto_data = {
                        'reparacion_id': reparacion_id,
                        'nombre_foto': file.filename,
                        'foto_binario': base64.b64encode(file.read()),
                    }
                    foto = request.env['reparaciones.foto'].sudo().create(foto_data)
                    if foto:
                        uploaded_files.append({'id': foto.id, 'nombre': foto.nombre_foto, 'url': foto.url_foto})
                    else:
                        failed_files.append({'filename': file.filename, 'error': 'No se pudo crear el registro'})

                except Exception as e:
                    failed_files.append({'filename': file.filename, 'error': str(e)})

            response_data = {
                'success': len(uploaded_files) > 0,
                'files': uploaded_files,
                'uploaded_count': len(uploaded_files),
                'failed_count': len(failed_files),
                'total_count': len(files)
            }
            response_data['message'] = (
                f"Se subieron {len(uploaded_files)} de {len(files)} archivos"
                if failed_files else f"Se subieron todos los {len(uploaded_files)} archivos correctamente"
            )
            if failed_files:
                response_data['failed_files'] = failed_files

            return json.dumps(response_data)

        except RequestEntityTooLarge:
            _logger.error("[UPLOAD] Archivo demasiado grande")
            return json.dumps({'success': False, 'error': 'Uno o más archivos son demasiado grandes', 'code': 'FILE_TOO_LARGE'})
        except Exception as e:
            _logger.exception("[UPLOAD] Error general: %s", str(e))
            return json.dumps({'success': False, 'error': f'Error interno: {str(e)}', 'code': 'INTERNAL_ERROR'})
