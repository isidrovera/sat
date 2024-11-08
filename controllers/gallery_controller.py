from odoo import http
from odoo.http import request, Response
import logging

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

    @http.route('/gallery/api/fotos/<int:reparacion_id>', type='json', auth='public', methods=['GET'], cors='*')
    def get_gallery_photos(self, reparacion_id, **kwargs):
        """API para obtener datos de las fotos en JSON."""
        _logger.info("Solicitando datos JSON para las fotos de la reparación ID: %s", reparacion_id)

        reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
        if not reparacion.exists():
            _logger.error("Reparación no encontrada: ID %s", reparacion_id)
            return {'error': 'Reparación no encontrada'}, 404

        fotos = request.env['reparaciones.foto'].sudo().search([('reparacion_id', '=', reparacion_id)], order="sequence")
        fotos_data = []
        for foto in fotos:
            try:
                thumb_url = foto._get_thumb_url(foto.file_id)
                file_url = foto._get_file_url(foto.file_id)
                if thumb_url and file_url:
                    fotos_data.append({
                        'id': foto.id,
                        'nombre_foto': foto.nombre_foto,
                        'thumb_url': thumb_url,
                        'download_url': file_url,
                    })
            except Exception as e:
                _logger.error("Error procesando la foto ID %s: %s", foto.id, e)
                continue

        _logger.info("Datos JSON de galería generados exitosamente")
        return {'fotos': fotos_data}
