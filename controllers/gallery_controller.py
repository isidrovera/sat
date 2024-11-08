import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class GalleryController(http.Controller):

    @http.route('/gallery/<int:reparacion_id>', type='http', auth='public')
    def gallery_page(self, reparacion_id, **kwargs):
        _logger.info("Iniciando carga de la galería para la reparación ID: %s", reparacion_id)
        
        try:
            reparacion = request.env['reparaciones.reparaciones'].sudo().browse(reparacion_id)
            if not reparacion.exists():
                _logger.error("Reparación ID %s no encontrada", reparacion_id)
                return request.not_found()

            fotos = request.env['reparaciones.foto'].sudo().search([
                ('reparacion_id', '=', reparacion_id)
            ])
            _logger.info("Total de fotos encontradas para la reparación ID %s: %s", reparacion_id, len(fotos))
            
            # Obtener configuración de pCloud
            pcloud_config = request.env['pcloud.configuracion'].sudo().search([], limit=1)
            if not pcloud_config or not pcloud_config.access_token:
                _logger.error("Configuración de pCloud no encontrada o falta el token de acceso.")
                raise ValidationError("Configuración de pCloud no encontrada")

            # Preparar datos de fotos con miniaturas y enlaces de descarga
            fotos_data = []
            for foto in fotos:
                try:
                    _logger.info("Procesando foto ID: %s", foto.id)
                    thumb_url = foto._get_thumb_url(foto.file_id, pcloud_config)
                    download_url = foto._get_file_url(foto.file_id, pcloud_config) if foto.file_id else None

                    fotos_data.append({
                        'id': foto.id,
                        'nombre': foto.nombre_foto,
                        'preview_url': foto.url_foto,  # URL original para previsualización
                        'thumb_url': thumb_url or foto.url_foto,  # Miniatura o URL original como fallback
                        'public_link': foto.public_link,  # Link público
                        'download_url': download_url or ''  # Asegúrate de que `download_url` esté presente
                    })
                    _logger.info("Foto ID %s procesada con éxito", foto.id)

                except Exception as foto_error:
                    _logger.error("Error al procesar la foto ID %s: %s", foto.id, str(foto_error))
                    fotos_data.append({
                        'id': foto.id,
                        'nombre': foto.nombre_foto,
                        'preview_url': foto.url_foto,
                        'thumb_url': foto.url_foto,
                        'public_link': foto.public_link,
                        'download_url': ''  # Establecer como vacío en caso de error
                    })

            _logger.info("Galería preparada con %s fotos para la reparación ID %s", len(fotos_data), reparacion_id)
            return request.render('sat.gallery_page_template', {
                'reparacion': reparacion,
                'fotos': fotos_data,
            })

        except ValidationError as val_err:
            _logger.error("Error de validación al cargar la galería: %s", str(val_err))
            return request.not_found()

        except Exception as e:
            _logger.exception("Error inesperado al cargar la galería para la reparación ID %s: %s", reparacion_id, str(e))
            return request.not_found()
