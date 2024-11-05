from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class SatController(http.Controller):

    @http.route('/sat/change_location/<int:record_id>', type='http', auth='public', website=True)
    def change_location(self, record_id, **kwargs):
        _logger.info(f"Request received to change location for record ID: {record_id}")
        record = request.env['sat.sat'].sudo().browse(record_id)
        if record.exists():
            _logger.info(f"Record found: {record.name.name} with current location {record.ubicacion_id}")
            record.ubicacion_id = 'primer_piso'
            _logger.info(f"Location changed to 'primer_piso' for record ID: {record_id}")
            context = {
                'record': record,
                'website': request.env['website'].get_current_website() if request.env['website'].search([]) else None,
            }
            return request.render('sat.location_change_success', context)
        else:
            _logger.error(f"Record with ID {record_id} not found")
            return request.not_found()
class PublicPageController(http.Controller):
    @http.route('/fotos', type='http', auth='public', website=True)
    def mi_pagina_publica(self, **kwargs):
        # Puedes agregar aquí la lógica que necesites
        valores = {
            'mensaje': 'Bienvenido a la página pública',
            # Puedes pasar más valores si es necesario
        }
        return request.render('reparaciones.GalleryWidget', valores)