from odoo import http
from odoo.http import request
import logging
import requests
import base64

_logger = logging.getLogger(__name__)

class GalleryController(http.Controller):

    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public', website=True)
    def gallery_page(self, reparacion_id, **kwargs):
        reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
        if not reparacion.exists():
            return request.not_found()
        
        fotos = request.env['reparaciones.foto'].sudo().search([('reparacion_id', '=', reparacion_id)])

        # Preparar datos para la galería
        fotos_data = []
        for foto in fotos:
            if foto.file_id:
                # Obtener URLs de miniatura y descarga
                thumb_url = foto._get_thumb_url(foto.file_id)
                download_url = foto._get_file_url(foto.file_id)
                fotos_data.append({
                    'id': foto.id,
                    'nombre': foto.nombre_foto,
                    'thumb_url': thumb_url,
                    'download_url': download_url,
                })
        
        return request.render('sat.gallery_page_template', {
            'reparacion': reparacion,
            'fotos': fotos_data,
        })

    @http.route('/gallery/upload_photo', type='http', auth='user', methods=['POST'], csrf=False)
    def upload_photo(self, reparacion_id, **kwargs):
        file = request.httprequest.files.get('file')
        if not file:
            return request.redirect(f'/gallery/{reparacion_id}')

        foto_binario = base64.b64encode(file.read()).decode('utf-8')
        
        foto_obj = request.env['reparaciones.foto'].sudo().create({
            'nombre_foto': file.filename,
            'foto_binario': foto_binario,
            'reparacion_id': reparacion_id,
        })

        foto_obj.upload_to_pcloud()

        return request.redirect(f'/gallery/{reparacion_id}')

    @http.route('/gallery/download/<int:foto_id>', type='http', auth='public')
    def download_photo(self, foto_id):
        foto = request.env['reparaciones.foto'].sudo().browse(foto_id)
        if not foto.exists():
            return request.not_found()

        download_url = foto._get_file_url(foto.file_id)

        return request.redirect(download_url)
