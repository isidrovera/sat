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
from urllib.parse import quote
from werkzeug.exceptions import RequestEntityTooLarge
from psycopg2.errors import SerializationFailure

_logger = logging.getLogger(__name__)

LOGIN_PATH = "/web/login"

def _login_redirect_response():
    """Redirige al login preservando la URL actual (para rutas type='http')."""
    current = request.httprequest.base_url
    target = f"{LOGIN_PATH}?redirect={quote(current, safe='')}"
    return request.redirect(target, 302)

def _json_auth_required():
    """Respuesta JSON para rutas type='json' cuando no hay sesión."""
    login_url = f"{LOGIN_PATH}?redirect={quote(request.httprequest.base_url, safe='')}"
    payload = {'success': False, 'code': 'AUTH_REQUIRED', 'error': 'Autenticación requerida', 'login_url': login_url}
    return Response(json.dumps(payload), status=401, headers=[('Content-Type', 'application/json')])

class GalleryController(http.Controller):

    # Cache en memoria para sesiones de subida "legacy"
    _upload_sessions = {}

    # ---------------------
    # VISTA GALERÍA PÚBLICA
    # ---------------------
    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public', website=True)
    def gallery_page(self, reparacion_id, **kwargs):

        _logger.info("[GALLERY] Accediendo a galería para reparación ID: %s", reparacion_id)

        try:

            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)

            if not reparacion.exists():
                _logger.error("[GALLERY] Reparación no encontrada: %s", reparacion_id)
                return request.not_found()

            foto_model = request.env['reparaciones.foto'].sudo()

            fotos = foto_model.get_photos_preview(reparacion_id) or []

            # SOLO fallback si no existe thumb_url
            for f in fotos:

                if not f.get('thumb_url'):

                    _logger.warning(
                        "[GALLERY] Foto %s sin thumb_url, usando preview fallback",
                        f.get('id')
                    )

                    f['thumb_url'] = f"/gallery/preview/{f['id']}"

            _logger.info("[GALLERY] Se encontraron %s fotos", len(fotos))

            return request.render('sat.gallery_page_template', {
                'reparacion': reparacion,
                'fotos': fotos,
            })

        except Exception as e:

            _logger.exception("[GALLERY] Error al cargar la galería: %s", e)

            return request.not_found()

    # -----------------------
    # PREVIEW (PÚBLICO)
    # -----------------------
    @http.route('/gallery/preview/<int:foto_id>', type='http', auth='public')
    def get_preview(self, foto_id):
        """Sirve una miniatura proxy (con cache) o placeholder."""
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
                resp = requests.get(thumb_url, timeout=6)
                if resp.status_code == 200 and resp.content:
                    return Response(
                        resp.content,
                        headers=[
                            ('Content-Type', resp.headers.get('content-type', 'image/jpeg')),
                            ('Cache-Control', 'public, max-age=7200'),
                            ('Access-Control-Allow-Origin', '*'),
                            ('X-Content-Type-Options', 'nosniff'),
                        ]
                    )
            except Exception:
                pass
            return self._serve_placeholder()
        except Exception as e:
            _logger.exception("[PREVIEW] Error: %s", e)
            return self._serve_placeholder()

    def _serve_placeholder(self):
        try:
            module_path = os.path.dirname(os.path.dirname(__file__))
            placeholder_path = os.path.join(module_path, 'static', 'src', 'img', 'placeholder.png')
            if os.path.exists(placeholder_path):
                with open(placeholder_path, 'rb') as f:
                    return Response(
                        f.read(),
                        headers=[('Content-Type', 'image/png'), ('Cache-Control', 'public, max-age=7200')]
                    )
        except Exception as e:
            _logger.error("[PLACEHOLDER] Error: %s", e)
        return Response(status=404)

    # ------------------------------------------------
    # VALIDACIÓN DE SESIÓN / LÍMITES (JSON, REQUIERE LOGIN)
    # ------------------------------------------------
    @http.route('/gallery/upload/validate/<int:reparacion_id>', type='json', auth='user', methods=['POST'])
    def validate_upload(self, reparacion_id, file_count=0, total_size=0):
        """Valida antes de subir; devuelve una sesión 'legacy' si la necesitas."""
        try:
            # auth='user' ya fuerza login, pero si llega público:
            if request.env.user._is_public():
                return _json_auth_required()

            _logger.info("[VALIDATE] Reparación %s | files=%s, size=%s", reparacion_id, file_count, total_size)

            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                return {'success': False, 'code': 'REPARACION_NOT_FOUND', 'error': 'Reparación no encontrada'}

            max_files = 200
            max_total_size = 300 * 1024 * 1024  # 300 MB

            if file_count and file_count > max_files:
                return {'success': False, 'code': 'TOO_MANY_FILES', 'error': f'Máximo {max_files} archivos por lote'}

            if total_size and total_size > max_total_size:
                return {'success': False, 'code': 'SIZE_EXCEEDED', 'error': f'El lote excede {max_total_size/1024/1024:.0f}MB'}

            session_id = str(uuid.uuid4())
            self._upload_sessions[session_id] = {
                'reparacion_id': reparacion_id,
                'file_count': int(file_count or 0),
                'uploaded': 0,
                'failed': 0,
                'results': [],
                'start_time': time.time(),
            }
            _logger.info("[VALIDATE] OK, sesión: %s", session_id)
            return {'success': True, 'session_id': session_id}
        except Exception as e:
            _logger.exception("[VALIDATE] Error: %s", e)
            return {'success': False, 'code': 'INTERNAL_ERROR', 'error': 'Error interno del servidor'}

    # ------------------------------------------------
    # SUBIDA DIRECTA A PCLOUD (HTTP, REQUIERE LOGIN)
    # ------------------------------------------------
    @http.route('/gallery/pcloud/upload-direct/<int:reparacion_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def pcloud_upload_direct(self, reparacion_id, **kwargs):

        from psycopg2.errors import SerializationFailure

        if not request.env.user or request.env.user._is_public():
            return _login_redirect_response()

        _logger.info("[PCL_UPLOAD_DIRECT] Reparación %s", reparacion_id)

        try:

            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)

            if not reparacion.exists():
                return self._json({'success': False, 'error': 'Reparación no encontrada'}, status=404)

            pconf = request.env['pcloud.configuracion'].sudo().search([], limit=1)

            if not pconf or not pconf.access_token or not pconf.hostname:
                return self._json({'success': False, 'error': 'Configuración pCloud faltante'}, status=500)

            files = request.httprequest.files.getlist('file')

            if not files:
                return self._json({'success': False, 'error': 'No se recibió archivo'}, status=400)

            file = files[0]

            folder_id = self._ensure_folder_in_pcloud(reparacion, pconf)

            if not folder_id:
                return self._json({'success': False, 'error': 'No se pudo obtener carpeta'}, status=500)

            upload_url = f"{pconf.hostname}/uploadfile"

            files_payload = {
                'file': (file.filename, file.stream, file.mimetype)
            }

            data_payload = {
                'access_token': pconf.access_token,
                'folderid': folder_id,
                'renameifexists': 1,
                'nopartial': 1,
            }

            _logger.info("[PCL_UPLOAD_DIRECT] Subiendo %s a folder %s", file.filename, folder_id)

            r = requests.post(upload_url, files=files_payload, data=data_payload, timeout=90)

            j = r.json() if r.content else {}

            if r.status_code != 200 or j.get('result') != 0:

                _logger.error("[PCL_UPLOAD_DIRECT] Error pCloud: %s", j)

                return self._json({'success': False, 'error': 'Error pCloud'}, status=502)

            meta = (j.get('metadata') or [{}])[0]

            file_id = meta.get('fileid')

            if not file_id:
                return self._json({'success': False, 'error': 'pCloud no devolvió fileid'}, status=502)

            Foto = request.env['reparaciones.foto'].sudo()

            # -------------------------
            # CREATE CON RETRY
            # -------------------------
            max_retry = 5
            attempt = 0

            while True:

                try:

                    rec = Foto.create({
                        'reparacion_id': reparacion_id,
                        'nombre_foto': file.filename,
                        'file_id': str(file_id),
                        'state': 'done',
                        'size': meta.get('size') or 0,
                        'mimetype': meta.get('contenttype') or file.mimetype or 'image/jpeg',
                    })

                    break

                except SerializationFailure:

                    attempt += 1
                    request.env.cr.rollback()

                    if attempt >= max_retry:
                        raise

                    _logger.warning(
                        "[PCL_UPLOAD_DIRECT] Retry create foto (%s/%s)",
                        attempt,
                        max_retry
                    )

                    time.sleep(0.2)

            # -------------------------
            # GENERAR URLs
            # -------------------------
            try:

                file_url = rec._get_file_url(rec.file_id, pconf)
                thumb_url = rec._get_thumb_url(rec.file_id, pconf)
                public_link = rec._create_public_link(rec.file_id, pconf)

                rec.write({
                    'url_foto': file_url,
                    'thumb_url': thumb_url,
                    'public_link': public_link or False,
                })

                _logger.info("[PCL_UPLOAD_DIRECT] URLs guardadas para foto %s", rec.id)

            except Exception as e:

                _logger.warning("[PCL_UPLOAD_DIRECT] No se pudieron generar URLs: %s", e)

            _logger.info(
                "[PCL_UPLOAD_DIRECT] OK -> foto_id=%s file_id=%s seq=%s",
                rec.id,
                file_id,
                rec.sequence
            )

            return self._json({
                'success': True,
                'foto_id': rec.id,
                'file_id': file_id,
                'sequence': rec.sequence,
                'filename': rec.nombre_foto,
            })

        except Exception as e:

            _logger.exception("[PCL_UPLOAD_DIRECT] Error: %s", e)

            return self._json({'success': False, 'error': 'Error interno'}, status=500)

    # -------------------------------------------------------------
    # STUB: createuploadlink (SE DESHABILITA; FORZAMOS MODO DIRECTO)
    # -------------------------------------------------------------
    @http.route('/gallery/pcloud/uploadlink/<int:reparacion_id>', type='json', auth='user', methods=['POST'])
    def get_upload_link(self, reparacion_id, **kw):
        """
        Deshabilitado a propósito. Indicamos al frontend usar la subida directa
        vía /gallery/pcloud/upload-direct/<id>.
        """
        if request.env.user._is_public():
            return _json_auth_required()
        _logger.info("[UPLOAD_LINK] Deshabilitado: usar modo DIRECTO")
        return {'success': False, 'code': 'USE_DIRECT_UPLOAD', 'error': 'El modo upload-link está deshabilitado'}

    # --------------------------
    # ELIMINAR (HTTP, REQUIERE LOGIN)
    # --------------------------
    @http.route('/gallery/delete/<int:foto_id>', type='http', auth='user', methods=['POST'], csrf=False)
    def delete_photo(self, foto_id):
        if not request.env.user or request.env.user._is_public():
            return _login_redirect_response()
        try:
            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if foto.exists():
                foto.unlink()
                return self._json({'success': True})
            return self._json({'success': False, 'code': 'NOT_FOUND', 'error': 'Foto no encontrada'}, status=404)
        except Exception as e:
            _logger.exception("[DELETE] Error: %s", e)
            return self._json({'success': False, 'code': 'INTERNAL_ERROR', 'error': 'Error interno'}, status=500)

    # ------------------------------------
    # DESCARGA INDIVIDUAL (PÚBLICO)
    # ------------------------------------
    @http.route('/gallery/download/<int:foto_id>', type='http', auth='public')
    def download_photo(self, foto_id):
        """Descarga una foto individual."""
        try:
            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if not foto.exists():
                _logger.error("[DOWNLOAD] Foto %s no encontrada", foto_id)
                return request.not_found()
            
            content = foto.get_download_content()
            if not content:
                _logger.error("[DOWNLOAD] No se pudo obtener contenido de foto %s", foto_id)
                return request.not_found()
            
            return request.make_response(
                base64.b64decode(content['content']),
                headers=[
                    ('Content-Type', content['content_type']),
                    ('Content-Disposition', f'attachment; filename="{content["filename"]}"'),
                    ('Cache-Control', 'no-cache'),
                ]
            )
        except Exception as e:
            _logger.exception("[DOWNLOAD] Error descargando foto %s: %s", foto_id, e)
            return request.not_found()

    # ------------------------------------
    # DESCARGA MASIVA EN ZIP (PÚBLICO)
    # ------------------------------------
    @http.route('/gallery/download_all/<int:reparacion_id>', type='http', auth='public')
    def download_all(self, reparacion_id):
        """Descarga todas las fotos de una reparación en un archivo ZIP."""
        try:
            _logger.info("[DOWNLOAD_ALL] Iniciando descarga ZIP para reparación %s", reparacion_id)
            
            # Verificar que existe la reparación
            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                _logger.error("[DOWNLOAD_ALL] Reparación %s no encontrada", reparacion_id)
                return request.not_found()
            
            # Buscar todas las fotos de esta reparación
            foto_obj = request.env['reparaciones.foto'].sudo()
            fotos = foto_obj.search([('reparacion_id', '=', reparacion_id)])
            
            if not fotos:
                _logger.warning("[DOWNLOAD_ALL] No hay fotos para la reparación %s", reparacion_id)
                return Response(
                    json.dumps({'error': 'No hay fotos para descargar'}),
                    status=404,
                    headers=[('Content-Type', 'application/json')]
                )
            
            _logger.info("[DOWNLOAD_ALL] Generando ZIP con %s fotos", len(fotos))
            
            # Generar el ZIP usando el método del modelo
            res = foto_obj.get_photos_zip(fotos.ids)
            
            if not res or not res.get('content'):
                _logger.error("[DOWNLOAD_ALL] Error generando ZIP para reparación %s", reparacion_id)
                return request.not_found()
            
            # Nombre del archivo ZIP
            machine_name = reparacion.maquina_id.name.name if reparacion.maquina_id and reparacion.maquina_id.name else 'Sin_Maquina'
            serie = reparacion.serie_id or 'Sin_Serie'
            filename = res.get('filename', f'Fotos_{machine_name}_{serie}.zip')
            
            _logger.info("[DOWNLOAD_ALL] Enviando ZIP: %s (%s fotos)", filename, len(fotos))
            
            return request.make_response(
                base64.b64decode(res['content']),
                headers=[
                    ('Content-Type', 'application/zip'),
                    ('Content-Disposition', f'attachment; filename="{filename}"'),
                    ('Cache-Control', 'no-cache'),
                    ('Content-Length', str(len(base64.b64decode(res['content'])))),
                ]
            )
            
        except Exception as e:
            _logger.exception("[DOWNLOAD_ALL] Error generando ZIP para reparación %s: %s", reparacion_id, e)
            return Response(
                json.dumps({'error': 'Error generando archivo ZIP'}),
                status=500,
                headers=[('Content-Type', 'application/json')]
            )

    # ------------------------------------
    # SECUENCIA (HTTP JSON), REQUIERE LOGIN
    # ------------------------------------
    @http.route('/gallery/next-sequence/<int:reparacion_id>', type='http', auth='user', methods=['GET'])
    def get_next_sequence(self, reparacion_id):
        if request.env.user._is_public():
            return _login_redirect_response()
        try:
            next_seq = self._next_sequence_value(reparacion_id)
            return self._json({'success': True, 'next_sequence': next_seq, 'reparacion_id': reparacion_id})
        except Exception as e:
            _logger.exception("[NEXT_SEQUENCE] Error: %s", e)
            return self._json({'success': False, 'error': 'Error interno'}, status=500)

    # -----------------------
    # UTILIDADES INTERNAS
    # -----------------------
    def _json(self, data, status=200):
        return Response(json.dumps(data), status=status, headers=[('Content-Type', 'application/json')])

    def _next_sequence_value(self, reparacion_id):
        # 1. Lock exclusivo sobre la reparación padre
        request.env.cr.execute(
            "SELECT id FROM reparaciones_reparaciones WHERE id = %s FOR UPDATE NOWAIT",
            [reparacion_id]
        )
        # 2. Leer MAX directo desde SQL (sin caché ORM)
        request.env.cr.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM reparaciones_foto WHERE reparacion_id = %s",
            [reparacion_id]
        )
        return request.env.cr.fetchone()[0]
    def _ensure_folder_in_pcloud(self, reparacion, pconf):
        """
        Garantiza:
        - Carpeta raíz: 'fotos_reparaciones' (parent_id=0)
        - Carpeta por reparación: <maquina>_<serie>
        """

        # -------------------------------------------------
        # 1️⃣ Usar folder_id guardado si existe
        # -------------------------------------------------
        if reparacion.pcloud_folder_id:
            _logger.info(
                "[ENSURE_FOLDER] Usando folder_id almacenado en reparación %s: %s",
                reparacion.id,
                reparacion.pcloud_folder_id
            )
            return reparacion.pcloud_folder_id

        _logger.info(
            "[ENSURE_FOLDER] No existe folder_id almacenado. Creando estructura en pCloud..."
        )

        try:
            raiz_id = self._get_or_create_folder('fotos_reparaciones', 0, pconf, timeout=6)

            if not raiz_id:
                _logger.error("[ENSURE_FOLDER] No se pudo obtener carpeta raíz fotos_reparaciones")
                return None

            machine = reparacion.maquina_id.name.name if reparacion.maquina_id and reparacion.maquina_id.name else 'Sin_Maquina'
            serie = reparacion.serie_id or 'Sin_Serie'
            name = f"{machine}_{serie}"

            folder_id = self._get_or_create_folder(name, raiz_id, pconf, timeout=8)

            if not folder_id:
                _logger.error("[ENSURE_FOLDER] No se pudo crear carpeta de reparación: %s", name)
                return None

            # -------------------------------------------------
            # 2️⃣ Guardar folder_id en reparación
            # -------------------------------------------------
            reparacion.sudo().write({
                'pcloud_folder_id': str(folder_id)
            })

            _logger.info(
                "[ENSURE_FOLDER] Carpeta creada y guardada en reparación %s: %s",
                reparacion.id,
                folder_id
            )

            return folder_id

        except Exception as e:
            _logger.exception("[ENSURE_FOLDER] Error: %s", e)
            return None

    def _get_or_create_folder(self, folder_name, parent_id, pconf, timeout=6):
        """Usa listfolder y createfolder de https://api.pcloud.com"""
        # listfolder
        try:
            r = requests.get(
                f"{pconf.hostname}/listfolder",
                params={'access_token': pconf.access_token, 'folderid': parent_id, 'nofiles': 1},
                timeout=timeout
            )
            j = r.json() if r.content else {}
            if r.status_code == 200 and j.get('result') == 0:
                for item in j.get('metadata', {}).get('contents', []) or []:
                    if item.get('isfolder') and item.get('name') == folder_name:
                        return item.get('folderid')
            else:
                _logger.warning("[PCL] listfolder error: %s", j)
        except Exception as e:
            _logger.warning("[PCL] listfolder ex: %s", e)

        # createfolder
        try:
            r2 = requests.get(
                f"{pconf.hostname}/createfolder",
                params={'access_token': pconf.access_token, 'name': folder_name, 'folderid': parent_id},
                timeout=timeout
            )
            j2 = r2.json() if r2.content else {}
            if r2.status_code == 200 and j2.get('result') == 0:
                return j2.get('metadata', {}).get('folderid')
            _logger.error("[PCL] createfolder error: %s", j2)
        except Exception as e:
            _logger.error("[PCL] createfolder ex: %s", e)
        return None

    # --------------------------
    # COMPROBAR SESIÓN (PÚBLICO)
    # --------------------------
    @http.route('/web/session/check', type='http', auth='public', methods=['POST'], csrf=False)
    def check_session_status(self):
        try:
            if request.env.user and not request.env.user._is_public():
                return self._json({
                    'success': True,
                    'uid': request.env.user.id,
                    'username': request.env.user.name,
                    'is_authenticated': True
                })
            return self._json({'success': True, 'uid': False, 'username': None, 'is_authenticated': False})
        except Exception as e:
            _logger.warning("[SESSION_CHECK] Error: %s", e)
            return self._json({'success': False, 'error': 'Error verificando sesión', 'uid': False, 'is_authenticated': False}, status=500)