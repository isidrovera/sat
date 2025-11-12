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
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class GalleryController(http.Controller):
    _upload_sessions = {}

    # === Página de galería ===
    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public', website=True)
    def gallery_page(self, reparacion_id, **kwargs):
        try:
            rep = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not rep.exists():
                return request.not_found()
            fotos = request.env['reparaciones.foto'].sudo().get_photos_preview(reparacion_id)
            if fotos:
                for f in fotos:
                    f['thumb_url'] = f'/gallery/preview/{f["id"]}'
            return request.render('sat.gallery_page_template', {'reparacion': rep, 'fotos': fotos or []})
        except Exception as e:
            _logger.exception('[GALLERY] Error: %s', e)
            return request.not_found()

    # === Preview (thumbnail) ===
    @http.route('/gallery/preview/<int:foto_id>', type='http', auth='public')
    def get_preview(self, foto_id):
        try:
            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if not foto.exists() or not foto.file_id:
                return self._serve_placeholder()
            cfg = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            if not cfg: return self._serve_placeholder()
            thumb_url = foto._get_thumb_url(foto.file_id, cfg)
            if not thumb_url: return self._serve_placeholder()
            resp = requests.get(thumb_url, timeout=8)
            if resp.status_code == 200:
                headers = [('Content-Type', resp.headers.get('content-type', 'image/jpeg')),
                           ('Cache-Control','public, max-age=7200'),
                           ('Access-Control-Allow-Origin','*'),
                           ('X-Content-Type-Options','nosniff')]
                return Response(resp.content, headers=headers)
            return self._serve_placeholder()
        except Exception as e:
            _logger.exception('[PREVIEW] Error: %s', e)
            return self._serve_placeholder()

    # === Descargar original (visor imagen completa) ===
    @http.route('/gallery/download/<int:foto_id>', type='http', auth='public')
    def download_full(self, foto_id):
        try:
            foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
            if not foto.exists() or not foto.file_id:
                return Response(status=404)
            cfg = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            if not cfg: return Response(status=404)
            file_url = foto._get_file_url(foto.file_id, cfg)
            if not file_url: return Response(status=404)
            resp = requests.get(file_url, timeout=20, stream=True)
            if resp.status_code == 200:
                headers = [('Content-Type', resp.headers.get('content-type','application/octet-stream')),
                           ('Content-Disposition', 'inline; filename="%s"' % (foto.nombre_foto or 'archivo')),
                           ('Cache-Control','public, max-age=3600')]
                return Response(resp.content, headers=headers)
            return Response(status=404)
        except Exception as e:
            _logger.exception('[DOWNLOAD] Error: %s', e)
            return Response(status=500)

    def _serve_placeholder(self):
        try:
            module_path = os.path.dirname(os.path.dirname(__file__))
            placeholder_path = os.path.join(module_path, 'static', 'src', 'img', 'placeholder.png')
            if os.path.exists(placeholder_path):
                with open(placeholder_path, 'rb') as f:
                    return Response(f.read(), headers=[('Content-Type', 'image/png'), ('Cache-Control','public, max-age=7200')])
        except Exception as e:
            _logger.error('[PLACEHOLDER] %s', e)
        return Response(status=404)

    # === Validar sesión ===
    @http.route('/gallery/upload/validate/<int:reparacion_id>', type='json', auth='public', methods=['POST'])
    def validate_upload(self, reparacion_id, file_count=0, total_size=0):
        try:
            rep = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not rep.exists():
                return {'success': False, 'error': 'Reparación no encontrada', 'code': 'REPARACION_NOT_FOUND'}
            if not request.env.user or request.env.user._is_public():
                return {'success': False, 'error': 'Necesitas iniciar sesión', 'code': 'AUTH_REQUIRED'}
            session_id = str(uuid.uuid4())
            self._upload_sessions[session_id] = {'reparacion_id': reparacion_id, 'file_count': file_count or 0, 'uploaded': 0, 'failed': 0, 'start_time': time.time()}
            return {'success': True, 'session_id': session_id, 'limits': {'max_file_size': 10*1024*1024, 'max_files': 50, 'max_total_size': 100*1024*1024}}
        except Exception as e:
            _logger.exception('[VALIDATE] %s', e)
            return {'success': False, 'error': 'Error interno', 'code': 'INTERNAL_ERROR'}

    # === Upload link de pCloud para la carpeta de la reparación ===
    @http.route('/gallery/pcloud/uploadlink/<int:reparacion_id>', type='json', auth='user', methods=['POST'])
    def pcloud_upload_link(self, reparacion_id):
        try:
            rep = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not rep.exists():
                return {'success': False, 'error': 'Reparación no encontrada'}
            cfg = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            if not cfg or not cfg.access_token or not cfg.hostname:
                return {'success': False, 'error': 'Config pCloud inválida'}
            # resolver carpeta
            foto_model = request.env['reparaciones.foto'].sudo()
            folder_id = foto_model._obtener_folder_id(rep, cfg)
            # pedir upload link
            url = f"{cfg.hostname}/getuploadlink"
            params = {'access_token': cfg.access_token, 'folderid': folder_id, 'renameifexists': 1}
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            if r.status_code == 200 and data.get('result') == 0:
                upload_url = f"https://{data['hosts'][0]}{data['path']}"
                return {'success': True, 'upload_url': upload_url}
            return {'success': False, 'error': data}
        except Exception as e:
            _logger.exception('[UPLOADLINK] %s', e)
            return {'success': False, 'error': 'No se pudo obtener upload link'}

    # === Registrar archivo ya subido ===
    @http.route('/gallery/register', type='json', auth='user', methods=['POST'])
    def register_uploaded(self, **payload):
        try:
            data = request.jsonrequest or {}
            reparacion_id = int(data.get('reparacion_id') or 0)
            filename = data.get('filename')
            sequence = data.get('sequence')
            if not reparacion_id or not filename:
                return {'success': False, 'error': 'Parámetros inválidos'}
            foto_model = request.env['reparaciones.foto'].sudo()
            foto_info = foto_model.register_from_pcloud(reparacion_id, filename, sequence=sequence)
            return {'success': True, 'foto': foto_info}
        except ValidationError as ve:
            return {'success': False, 'error': str(ve)}
        except Exception as e:
            _logger.exception('[REGISTER] %s', e)
            return {'success': False, 'error': 'Error registrando archivo'}

    # === Siguiente secuencia ===
    @http.route('/gallery/next-sequence/<int:reparacion_id>', type='http', auth='user', methods=['GET'])
    def next_sequence(self, reparacion_id):
        try:
            foto = request.env['reparaciones.foto'].sudo()
            last = foto.search([('reparacion_id','=', reparacion_id)], order='sequence desc', limit=1)
            nxt = (last.sequence or 0) + 1
            return Response(json.dumps({'next_sequence': nxt}), headers=[('Content-Type','application/json')])
        except Exception as e:
            _logger.exception('[NEXTSEQ] %s', e)
            return Response(json.dumps({'next_sequence': 1}), headers=[('Content-Type','application/json')])
