from odoo import http
from odoo.http import request, Response
import logging
import zipfile
import io

_logger = logging.getLogger(__name__)

class GalleryController(http.Controller):
    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public', website=True, cors='*')
    def gallery_page(self, reparacion_id, **kwargs):
        """Renderiza la página de galería para una reparación específica."""
        _logger.info("Iniciando carga de la galería para la reparación ID: %s", reparacion_id)

        # Buscar la reparación y sus fotos asociadas
        reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
        if not reparacion.exists():
            _logger.error("No se encontró la reparación con ID: %s", reparacion_id)
            return request.not_found()

        fotos = request.env['reparaciones.foto'].sudo().search([('reparacion_id', '=', reparacion_id)], order="sequence")
        _logger.info("Total de fotos encontradas para la reparación ID %s: %s", reparacion_id, len(fotos))

        # Procesar las fotos para generar URLs de miniaturas y descargas
        fotos_data = []
        for foto in fotos:
            try:
                _logger.info("Procesando foto ID: %s", foto.id)
                thumb_url = foto._get_thumb_url(foto.file_id)
                file_url = foto._get_file_url(foto.file_id)

                if not thumb_url or not file_url:
                    _logger.warning("No se generó URL de miniatura o descarga para la foto ID %s", foto.id)
                    continue

                fotos_data.append({
                    'id': foto.id,
                    'nombre_foto': foto.nombre_foto,
                    'thumb_url': thumb_url,
                    'download_url': file_url,
                })
                _logger.info("Foto ID %s procesada con éxito", foto.id)

            except Exception as e:
                _logger.exception("Error al procesar la foto ID %s: %s", foto.id, str(e))

        _logger.info("Galería preparada con %s fotos para la reparación ID %s", len(fotos_data), reparacion_id)

        # Renderizar la plantilla de galería
        return request.render('sat.gallery_page_template', {
            'reparacion': reparacion,
            'fotos': fotos_data,
        })

    @http.route('/gallery/api/download_all/<int:reparacion_id>', type='http', auth='public', cors='*')
    def download_all_photos(self, reparacion_id, **kwargs):
        """Descarga todas las fotos de una reparación en un archivo zip."""
        _logger.info("Solicitando descarga de todas las fotos para la reparación ID: %s", reparacion_id)

        reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
        if not reparacion.exists():
            _logger.error("Reparación no encontrada: ID %s", reparacion_id)
            return request.not_found()

        fotos = request.env['reparaciones.foto'].sudo().search([('reparacion_id', '=', reparacion_id)], order="sequence")
        if not fotos:
            _logger.warning("No hay fotos para la reparación ID %s", reparacion_id)
            return request.not_found()

        # Crear el archivo zip en memoria
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for foto in fotos:
                try:
                    file_url = foto._get_file_url(foto.file_id)
                    if file_url:
                        # Añadir la imagen al zip
                        response = request.env['ir.http']._url_open(file_url)
                        zip_file.writestr(f"{foto.nombre_foto}.jpg", response.read())
                        _logger.info("Foto ID %s añadida al zip", foto.id)
                except Exception as e:
                    _logger.error("Error al añadir la foto ID %s al zip: %s", foto.id, str(e))

        zip_buffer.seek(0)
        return Response(zip_buffer, headers=[
            ('Content-Type', 'application/zip'),
            ('Content-Disposition', f'attachment; filename="fotos_reparacion_{reparacion_id}.zip"')
        ])
