from odoo import http
from odoo.http import request
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class MaintenanceController(http.Controller):

    @http.route('/mantenimiento/confirmar/<int:alquiler_id>', type='http', auth='public', website=True)
    def confirm_maintenance(self, alquiler_id):
        try:
            alquiler = request.env['alquiler'].sudo().browse(alquiler_id)
            if not alquiler.exists():
                return request.render('sat.maintenance_error_template', {
                    'error_message': 'No se encontró el registro de mantenimiento solicitado.'
                })

            # Crear tickets
            if alquiler._create_maintenance_tickets():
                # La fecha ya viene como date desde el modelo
                fecha_visita = alquiler.fecha_recurrente
                
                return request.render('sat.maintenance_confirmation_template', {
                    'message': 'Gracias por confirmar la fecha de mantenimiento. Nuestro equipo técnico lo visitará según lo programado.',
                    'visit_date': fecha_visita,
                    'datetime': datetime  # Pasar el módulo datetime al template
                })
            else:
                return request.render('sat.maintenance_error_template', {
                    'error_message': 'No se pudo procesar la confirmación. Por favor, inténtelo nuevamente.'
                })

        except Exception as e:
            _logger.error("Error en confirmación de mantenimiento: %s", str(e))
            return request.render('sat.maintenance_error_template', {
                'error_message': 'Ocurrió un error al procesar su solicitud.'
            })

    @http.route('/mantenimiento/reprogramar/<int:alquiler_id>', type='http', auth='public', website=True)
    def request_reschedule(self, alquiler_id):
        try:
            alquiler = request.env['alquiler'].sudo().browse(alquiler_id)
            if not alquiler.exists():
                return request.render('sat.maintenance_error_template', {
                    'error_message': 'No se encontró el registro de mantenimiento solicitado.'
                })

            if alquiler._send_reschedule_request():
                return request.render('sat.maintenance_reschedule_template', {
                    'message': 'Su solicitud de reprogramación ha sido recibida. Nos pondremos en contacto con usted pronto.'
                })
            else:
                return request.render('sat.maintenance_error_template', {
                    'error_message': 'No se pudo procesar la solicitud de reprogramación.'
                })

        except Exception as e:
            _logger.error("Error en solicitud de reprogramación: %s", str(e))
            return request.render('sat.maintenance_error_template', {
                'error_message': 'Ocurrió un error al procesar su solicitud.'
            })