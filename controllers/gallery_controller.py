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

    # Cache simple en memoria para sesiones de subida por tandas (upload_single)
    _upload_sessions = {}

    # ==========================
    # UTILIDADES
    # ==========================

    def _json_response_http(self, data: dict, status=200):
        """Responde JSON en rutas type='http'."""
        return Response(
            json.dumps(data, ensure_ascii=False),
            status=status,
            headers=[('Content-Type', 'application/json; charset=utf-8')]
        )

    def _get_session_progress(self, session_id):
        if session_id not in self._upload_sessions:
            return None
        s = self._upload_sessions[session_id]
        total = s['file_count']
        completed = s['uploaded'] + s['failed']
        return {
            'total': total,
            'uploaded': s['uploaded'],
            'failed': s['failed'],
            'completed': completed,
            'percentage': (completed / total * 100) if total > 0 else 0,
            'is_complete': completed >= total
        }

    def _validate_single_file(self, file_storage):
        """Validación local básica para uploads 'clásicos'."""
        if not file_storage or not file_storage.filename:
            return {'valid': False, 'error': 'Archivo vacío'}
        # extensión
        if not any(file_storage.filename.lower().endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')):
            return {'valid': False, 'error': 'Tipo de archivo no permitido'}
        # tamaño
        file_storage.seek(0, 2)
        size = file_storage.tell()
        file_storage.seek(0)
        if size == 0:
            return {'valid': False, 'error': 'Archivo vacío'}
        if size > 10 * 1024 * 1024:
            return {'valid': False, 'error': 'Archivo excede 10MB'}
        return {'valid': True}

    def _serve_placeholder(self):
        """Devuelve imagen placeholder en caso de error/ausencia."""
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
            _logger.error("[PLACEHOLDER] Error: %s", e)
        return Response(status=404)

    # ==========================
    # PÁGINA + PREVIEWS
    # ==========================

    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public', website=True)
    def gallery_page(self, reparacion_id, **kwargs):
        """Renderiza la página de galería (usa template sat.gallery_page_template)."""
        _logger.info("[GALLERY] Reparación ID: %s", reparacion_id)
        try:
            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                return request.not_found()

            Foto = request.env['reparaciones.foto'].sudo()
            fotos = Foto.get_photos_preview(reparacion_id) or []

            # Asegurar thumb_url hacia nuestro endpoint de preview
            for it in fotos:
                it['thumb_url'] = f"/gallery/preview/{it['id']}"

            return request.render('sat.gallery_page_template', {
                'reparacion': reparacion,
                'fotos': fotos,
            })
        except Exception as e:
            _logger.exception("[GALLERY] Error: %s", e)
            return request.not_found()

    @http.route('/gallery/preview/<int:foto_id>', type='http', auth='public')
    def get_preview(self, foto_id):
        """Sirve una previsualización optimizada vía pCloud thumbnail."""
        try:
            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if not foto.exists():
                return self._serve_placeholder()

            pconf = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            if not pconf:
                return self._serve_placeholder()

            thumb_url = foto._get_thumb_url(foto.file_id, pconf)
            if not thumb_url:
                return self._serve_placeholder()

            try:
                r = requests.get(thumb_url, timeout=6)
                if r.status_code == 200 and r.content:
                    headers = [
                        ('Content-Type', r.headers.get('content-type', 'image/jpeg')),
                        ('Cache-Control', 'public, max-age=7200'),
                        ('Access-Control-Allow-Origin', '*'),
                        ('X-Content-Type-Options', 'nosniff'),
                    ]
                    return Response(r.content, headers=headers)
            except Exception as e:
                _logger.warning("[PREVIEW] Fetch thumb error: %s", e)

            return self._serve_placeholder()
        except Exception as e:
            _logger.exception("[PREVIEW] Error: %s", e)
            return self._serve_placeholder()

    # ==========================
    # VALIDACIÓN PREVIA (opcional, para UX)
    # ==========================

    @http.route('/gallery/upload/validate/<int:reparacion_id>', type='json', auth='public', methods=['POST'])
    def validate_upload(self, reparacion_id, file_count=0, total_size=0):
        """
        Validación previa (opcional) de límites antes de subir (para UI).
        """
        try:
            _logger.info("[VALIDATE] Reparación %s | files=%s, size=%s", reparacion_id, file_count, total_size)

            rep = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not rep.exists():
                return {'success': False, 'error': 'Reparación no encontrada', 'code': 'REPARACION_NOT_FOUND'}

            if not request.env.user or request.env.user._is_public():
                return {'success': False, 'error': 'Inicia sesión para subir archivos', 'code': 'AUTH_REQUIRED'}

            max_files = 50
            max_total_size = 100 * 1024 * 1024
            max_file_size = 10 * 1024 * 1024

            if file_count and int(file_count) > max_files:
                return {'success': False, 'error': f'Máximo {max_files} archivos', 'code': 'TOO_MANY_FILES'}

            if total_size and int(total_size) > max_total_size:
                return {'success': False, 'error': f'Tamaño total excede {max_total_size//1024//1024}MB', 'code': 'SIZE_EXCEEDED'}

            # crea sesión local para el flujo upload_single (opcional)
            session_id = str(uuid.uuid4())
            self._upload_sessions[session_id] = {
                'reparacion_id': reparacion_id,
                'file_count': int(file_count or 0),
                'uploaded': 0,
                'failed': 0,
                'results': [],
                'start_time': time.time(),
            }

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
            _logger.exception("[VALIDATE] Error: %s", e)
            return {'success': False, 'error': 'Error interno', 'code': 'INTERNAL_ERROR'}

    # ==========================
    # SUBIDA RÁPIDA: LINK (BROWSER -> PCLOUD)
    # ==========================

    @http.route('/gallery/pcloud/uploadlink/<int:reparacion_id>', type='json', auth='user', methods=['POST'])
    def get_upload_link(self, reparacion_id, **payload):
        """
        Obtiene o reusa un upload link de pCloud para subir DIRECTO desde el navegador.
        Devuelve: {success, endpoint, code, expires?}
        """
        try:
            file_count = int(payload.get('file_count') or 1)
            total_size = int(payload.get('total_size') or 10_000_000)

            rep = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not rep.exists():
                return {'success': False, 'error': 'Reparación no encontrada'}

            # Reusar/crear link vía método del modelo (rápido)
            link = rep._ensure_upload_link(file_count=file_count, total_size=total_size, hours_valid=6)

            return {
                'success': True,
                'endpoint': 'https://api.pcloud.com/uploadtolink',
                'code': link.get('code'),
                'expires': str(link.get('expires')) if link.get('expires') else None,
            }
        except Exception as e:
            _logger.exception("[UPLOAD_LINK] Error: %s", e)
            return {'success': False, 'error': 'Error interno'}

    @http.route('/gallery/pcloud/register', type='json', auth='user', methods=['POST'])
    def pcloud_register_file(self, **payload):
        """
        Registra en Odoo la foto ya subida a pCloud.
        payload:
        {
          "reparacion_id": 123,
          "sequence": 7,
          "filename": "image.jpg",
          "pcloud": {"fileid": 7783, "size": 123456, "contenttype": "image/jpeg"}
        }
        """
        try:
            reparacion_id = int(payload.get('reparacion_id'))
            sequence = int(payload.get('sequence') or 0)
            filename = (payload.get('filename') or 'foto.jpg').strip()
            meta = payload.get('pcloud') or {}
            fileid = meta.get('fileid')

            if not (reparacion_id and fileid):
                return {'success': False, 'error': 'Datos incompletos'}

            env = request.env
            Foto = env['reparaciones.foto'].sudo()
            pconf = env['pcloud.configuracion'].sudo().search([], limit=1)
            if not pconf:
                return {'success': False, 'error': 'Config pCloud no disponible'}

            # Evitar duplicados por file_id
            exists = Foto.search([('reparacion_id', '=', reparacion_id), ('file_id', '=', str(fileid))], limit=1)
            if exists:
                return {
                    'success': True,
                    'id': exists.id,
                    'file_id': exists.file_id,
                    'download_url': exists._get_file_url(exists.file_id, pconf),
                    'thumb_url': exists._get_thumb_url(exists.file_id, pconf),
                    'duplicate': True
                }

            # Crear registro (sin foto_binario)
            rec = Foto.create({
                'reparacion_id': reparacion_id,
                'nombre_foto': filename or f'foto_{fileid}.jpg',
                'sequence': sequence if sequence > 0 else 1,
                'file_id': str(fileid),
                'mimetype': meta.get('contenttype', 'application/octet-stream'),
                'size': int(meta.get('size') or 0),
                'state': 'done',
            })

            # Complementar URLs
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
            _logger.exception("[REGISTER] Error: %s", e)
            return {'success': False, 'error': str(e)}

    # ==========================
    # Fallbacks de subida (opcional)
    # ==========================

    @http.route('/gallery/pcloud/proxy-upload', type='http', auth='user', methods=['POST'], csrf=False)
    def proxy_upload(self, **kw):
        """
        Fallback si CORS bloquea el upload directo.
        Recibe 'code' y 'file' y reenvía a https://api.pcloud.com/uploadtolink
        """
        try:
            code = request.httprequest.form.get('code')
            f = request.httprequest.files.get('file')
            if not code or not f:
                return self._json_response_http({'success': False, 'error': 'Faltan parámetros'}, status=400)

            files = {'file': (f.filename, f.stream, f.mimetype)}
            data = {'code': code}
            r = requests.post('https://api.pcloud.com/uploadtolink', data=data, files=files, timeout=120)
            jr = r.json() if r.content else {}
            ok = (r.status_code == 200 and jr.get('result') == 0)
            return self._json_response_http({'success': ok, 'raw': jr}, status=200 if ok else 500)
        except Exception as e:
            _logger.exception('[PROXY_UPLOAD] Error: %s', e)
            return self._json_response_http({'success': False, 'error': 'Proxy error'}, status=500)

    @http.route('/gallery/pcloud/upload-direct/<int:reparacion_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def pcloud_upload_direct(self, reparacion_id, **kwargs):
        """
        Fallback de subida directa server->pCloud usando uploadfile.
        Menos rápido que upload link (pasa por tu servidor).
        """
        _logger.info("[UPLOAD_DIRECT] Reparación %s", reparacion_id)
        try:
            rep = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not rep.exists():
                return self._json_response_http({'success': False, 'error': 'Reparación no encontrada'}, status=404)

            pconf = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            if not pconf or not pconf.access_token:
                return self._json_response_http({'success': False, 'error': 'Config pCloud faltante'}, status=500)

            files = request.httprequest.files.getlist('file')
            if not files:
                return self._json_response_http({'success': False, 'error': 'No se encontró archivo'}, status=400)

            file = files[0]
            sequence = request.httprequest.form.get('sequence', '1')

            # Obtener/crear carpeta destino en pCloud (rápido)
            folder_id = rep._ensure_pcloud_folder()
            upload_url = f"{pconf.hostname}/uploadfile"
            up_files = {'file': (file.filename, file.stream, file.mimetype)}
            up_data = {
                'access_token': pconf.access_token,
                'folderid': folder_id,
                'renameifexists': 1,
                'nopartial': 1
            }
            rr = requests.post(upload_url, files=up_files, data=up_data, timeout=60)
            result = rr.json() if rr.content else {}

            if rr.status_code == 200 and result.get('result') == 0 and result.get('metadata'):
                meta = result['metadata'][0]
                file_id = meta.get('fileid')
                if not file_id:
                    return self._json_response_http({'success': False, 'error': 'Sin file_id'}, status=500)

                Foto = request.env['reparaciones.foto'].sudo()
                foto = Foto.create({
                    'reparacion_id': reparacion_id,
                    'nombre_foto': file.filename,
                    'sequence': int(sequence) if sequence.isdigit() else 1,
                    'file_id': str(file_id),
                    'state': 'done',
                    'size': meta.get('size', 0),
                    'mimetype': meta.get('contenttype', file.mimetype or 'application/octet-stream')
                })
                return self._json_response_http({
                    'success': True,
                    'foto_id': foto.id,
                    'file_id': file_id,
                    'sequence': foto.sequence,
                    'method': 'direct_upload'
                }, status=200)

            return self._json_response_http({'success': False, 'error': result.get('error', 'Error pCloud')}, status=500)
        except Exception as e:
            _logger.exception('[UPLOAD_DIRECT] Error: %s', e)
            return self._json_response_http({'success': False, 'error': 'Error interno'}, status=500)

    # ==========================
    # Subida clásica por lote (compatibilidad)
    # ==========================

    @http.route('/gallery/upload/<int:reparacion_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_photo(self, reparacion_id, **kwargs):
        """Compatibilidad: upload al servidor (NO recomendado si buscas rapidez)."""
        _logger.info("[UPLOAD_BATCH] Reparación %s", reparacion_id)
        try:
            if not request.env.user or request.env.user._is_public():
                return self._json_response_http({'success': False, 'error': 'Sesión expirada', 'code': 'AUTH_REQUIRED'}, status=401)

            files = request.httprequest.files.getlist('files[]')
            if not files:
                return self._json_response_http({'success': False, 'error': 'No hay archivos', 'code': 'NO_FILES'}, status=400)

            uploaded, failed = [], []
            Foto = request.env['reparaciones.foto'].sudo()

            for f in files:
                try:
                    val = self._validate_single_file(f)
                    if not val['valid']:
                        failed.append({'filename': f.filename, 'error': val['error']})
                        continue
                    foto = Foto.create({
                        'reparacion_id': reparacion_id,
                        'nombre_foto': f.filename,
                        'foto_binario': base64.b64encode(f.read()),
                    })
                    uploaded.append({'id': foto.id, 'nombre': foto.nombre_foto})
                except Exception as e:
                    failed.append({'filename': f.filename, 'error': str(e)})

            return self._json_response_http({
                'success': len(uploaded) > 0,
                'uploaded_count': len(uploaded),
                'failed_count': len(failed),
                'total_count': len(files),
                'files': uploaded,
                'failed_files': failed or None,
            })
        except RequestEntityTooLarge:
            return self._json_response_http({'success': False, 'error': 'Archivo demasiado grande'}, status=413)
        except Exception as e:
            _logger.exception("[UPLOAD_BATCH] Error: %s", e)
            return self._json_response_http({'success': False, 'error': 'Error interno'}, status=500)

    # ==========================
    # PROGRESO / COMPLETAR (para flujo por sesión opcional)
    # ==========================

    @http.route('/gallery/upload/progress/<session_id>', type='json', auth='user', methods=['GET'])
    def get_upload_progress(self, session_id):
        try:
            if session_id not in self._upload_sessions:
                return {'success': False, 'error': 'Sesión no encontrada'}
            return {'success': True, 'progress': self._get_session_progress(session_id)}
        except Exception as e:
            _logger.exception("[PROGRESS] Error: %s", e)
            return {'success': False, 'error': 'Error interno'}

    @http.route('/gallery/upload/complete/<session_id>', type='json', auth='user', methods=['POST'])
    def complete_upload_session(self, session_id):
        try:
            if session_id not in self._upload_sessions:
                return {'success': False, 'error': 'Sesión no encontrada'}
            s = self._upload_sessions[session_id]
            progress = self._get_session_progress(session_id)
            del self._upload_sessions[session_id]
            return {
                'success': True,
                'summary': {
                    'total_files': s['file_count'],
                    'uploaded': s['uploaded'],
                    'failed': s['failed'],
                    'duration': time.time() - s['start_time'],
                    'results': s['results']
                },
                'progress': progress
            }
        except Exception as e:
            _logger.exception("[COMPLETE] Error: %s", e)
            return {'success': False, 'error': 'Error interno'}

    # ==========================
    # DESCARGA(S)
    # ==========================

    @http.route('/gallery/download/<int:foto_id>', type='http', auth='public')
    def download_photo(self, foto_id):
        """Descarga directa de una foto (lee contenido desde pCloud/modelo)."""
        foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
        if not foto.exists():
            return request.not_found()
        content_info = foto.get_download_content()
        if not content_info:
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
        """Descarga ZIP con todas las fotos de la reparación."""
        try:
            Foto = request.env['reparaciones.foto'].sudo()
            ids = Foto.search([('reparacion_id', '=', reparacion_id)]).ids
            result = Foto.get_photos_zip(ids)
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
            _logger.exception("[DOWNLOAD_ALL] Error: %s", e)
            return request.not_found()

    # ==========================
    # BORRADO (ELIMINAR FOTOS)
    # ==========================

    @http.route('/gallery/delete/<int:foto_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def delete_photo(self, foto_id):
        """
        Elimina una foto (registro Odoo). Si tu modelo ya sincroniza con pCloud,
        puedes también llamar a la API de pCloud para borrarla allá (opcional).
        Respuesta JSON.
        """
        try:
            if not request.env.user or request.env.user._is_public():
                return self._json_response_http({'success': False, 'error': 'Sesión expirada', 'code': 'AUTH_REQUIRED'}, status=401)

            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if not foto.exists():
                return self._json_response_http({'success': False, 'error': 'Foto no encontrada', 'code': 'NOT_FOUND'}, status=404)

            # (Opcional) Borrar también en pCloud si tienes file_id y permisos:
            # pconf = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            # if pconf and foto.file_id:
            #     try:
            #         del_url = f"{pconf.hostname}/deletefile"
            #         requests.get(del_url, params={'access_token': pconf.access_token, 'fileid': int(foto.file_id)}, timeout=8)
            #     except Exception as e:
            #         _logger.warning("[DELETE] pCloud delete warning: %s", e)

            foto.unlink()
            return self._json_response_http({'success': True}, status=200)
        except Exception as e:
            _logger.exception("[DELETE] Error: %s", e)
            return self._json_response_http({'success': False, 'error': 'Error interno', 'code': 'INTERNAL_ERROR'}, status=500)

    # ==========================
    # SECUENCIAS Y LIMPIEZA
    # ==========================

    @http.route('/gallery/next-sequence/<int:reparacion_id>', type='http', auth='user', methods=['GET'])
    def get_next_sequence(self, reparacion_id):
        """Devuelve la siguiente secuencia disponible para esa reparación."""
        try:
            if not request.env.user or request.env.user._is_public():
                return self._json_response_http({'success': False, 'error': 'Sesión expirada', 'code': 'AUTH_REQUIRED'}, status=401)

            rep = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not rep.exists():
                return self._json_response_http({'success': False, 'error': 'Reparación no encontrada', 'code': 'REPARACION_NOT_FOUND'}, status=404)

            Foto = request.env['reparaciones.foto'].sudo()
            max_seq = Foto.search([('reparacion_id', '=', reparacion_id)], order='sequence desc', limit=1)
            next_sequence = (max_seq.sequence if max_seq else 0) + 1

            return self._json_response_http({'success': True, 'next_sequence': next_sequence, 'reparacion_id': reparacion_id}, status=200)
        except Exception as e:
            _logger.exception("[NEXT_SEQUENCE] Error: %s", e)
            return self._json_response_http({'success': False, 'error': 'Error interno'}, status=500)

    @http.route('/gallery/cleanup-sequences/<int:reparacion_id>', type='json', auth='user', methods=['POST'])
    def cleanup_duplicate_sequences(self, reparacion_id):
        """
        Reordena secuencias 1..N por fecha de creación.
        """
        try:
            if not request.env.user or request.env.user._is_public():
                return {'success': False, 'error': 'Sesión expirada', 'code': 'AUTH_REQUIRED'}

            rep = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not rep.exists():
                return {'success': False, 'error': 'Reparación no encontrada', 'code': 'REPARACION_NOT_FOUND'}

            Foto = request.env['reparaciones.foto'].sudo()
            fotos = Foto.search([('reparacion_id', '=', reparacion_id)], order='create_date asc')

            if not fotos:
                return {'success': True, 'message': 'No hay fotos para limpiar'}

            changed = 0
            for i, f in enumerate(fotos, start=1):
                if f.sequence != i:
                    f.write({'sequence': i})
                    changed += 1

            return {'success': True, 'cleaned_count': changed, 'total_fotos': len(fotos)}
        except Exception as e:
            _logger.exception("[CLEANUP_SEQUENCES] Error: %s", e)
            return {'success': False, 'error': 'Error interno'}

    # ==========================
    # SINCRONIZACIÓN DESDE PCLOUD
    # ==========================

    @http.route('/gallery/sync/<int:reparacion_id>', type='json', auth='user', methods=['POST'])
    def sync_from_pcloud(self, reparacion_id, **kw):
        """
        Revisa carpeta pCloud y crea reparaciones.foto faltantes (idempotente por file_id).
        """
        try:
            env = request.env
            rep = env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not rep.exists():
                return {'success': False, 'error': 'Reparación no encontrada'}

            pconf = env['pcloud.configuracion'].sudo().search([], limit=1)
            if not pconf or not pconf.access_token:
                return {'success': False, 'error': 'Falta configuración de pCloud'}

            folder_id = rep._ensure_pcloud_folder()

            list_url = f"{pconf.hostname}/listfolder"
            params = {'access_token': pconf.access_token, 'folderid': folder_id}
            r = requests.get(list_url, params=params, timeout=15)
            data = r.json()

            if r.status_code != 200 or data.get('result') != 0:
                return {'success': False, 'error': f"listfolder error: {data}"}

            contents = data.get('metadata', {}).get('contents', []) or []
            Foto = env['reparaciones.foto'].sudo()

            created = skipped = 0
            for it in contents:
                if it.get('isfolder'):
                    continue
                file_id = str(it.get('fileid'))
                if Foto.search_count([('reparacion_id', '=', rep.id), ('file_id', '=', file_id)]):
                    skipped += 1
                    continue
                Foto.create({
                    'reparacion_id': rep.id,
                    'nombre_foto': it.get('name') or f'foto_{file_id}.jpg',
                    'file_id': file_id,
                    'state': 'done',
                    'size': it.get('size') or 0,
                    'mimetype': it.get('contenttype') or 'application/octet-stream',
                })
                created += 1

            return {'success': True, 'message': f'Sync OK: {created} creadas, {skipped} ya existían.'}
        except Exception as e:
            _logger.exception('[SYNC] Error: %s', e)
            return {'success': False, 'error': 'Error interno'}

    # ==========================
    # SESIÓN (ping ligero)
    # ==========================

    @http.route('/web/session/check', type='http', auth='public', methods=['POST'], csrf=False)
    def check_session_status(self):
        """Ping simple: ¿hay usuario autenticado?"""
        try:
            if request.env.user and not request.env.user._is_public():
                return self._json_response_http({
                    'success': True,
                    'uid': request.env.user.id,
                    'username': request.env.user.name,
                    'is_authenticated': True
                })
            return self._json_response_http({
                'success': True,
                'uid': False,
                'username': None,
                'is_authenticated': False
            })
        except Exception as e:
            _logger.warning("[SESSION_CHECK] Error: %s", e)
            return self._json_response_http({
                'success': False,
                'error': 'Error verificando sesión',
                'uid': False,
                'is_authenticated': False
            }, status=500)
