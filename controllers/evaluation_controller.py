# controllers/evaluation_controller.py
from odoo import http, fields
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class EvaluationController(http.Controller):

    @http.route(
        ['/evaluation/submit/<string:token>'],
        type='http',
        auth='public',
        website=True
    )
    def evaluation_form(self, token, **kw):
        evaluation = request.env['client.service.evaluation'].sudo().search([
            ('token', '=', token),
            ('state', '=', 'sent')
        ], limit=1)

        if not evaluation:
            return request.render('sat.evaluation_expired', {})

        # Registrar acceso al portal
        try:
            evaluation.sudo()._register_portal_access(request=request)
        except Exception as e:
            _logger.warning(
                "No se pudo registrar acceso al portal para evaluación token %s: %s",
                token,
                str(e)
            )

        return request.render('sat.evaluation_form_template', {
            'evaluation': evaluation,
        })

    @http.route(
        ['/evaluation/submit/process'],
        type='http',
        auth='public',
        website=True,
        methods=['POST'],
        csrf=True
    )
    def process_evaluation(self, **post):
        token = post.get('token')

        if not token:
            return request.render('sat.evaluation_expired', {})

        evaluation = request.env['client.service.evaluation'].sudo().search([
            ('token', '=', token),
            ('state', '=', 'sent')
        ], limit=1)

        if not evaluation:
            return request.render('sat.evaluation_expired', {})

        try:
            values = {
                'saludo_presentacion': post.get('saludo_presentacion') or False,
                'diagnostico_problema': post.get('diagnostico_problema') or False,
                'solucion_problema': post.get('solucion_problema') or False,
                'explicacion_trabajo': post.get('explicacion_trabajo') or False,
                'limpieza_orden': post.get('limpieza_orden') or False,
                'revision_adicional': post.get('revision_adicional') or False,
                'realizo_pruebas': post.get('realizo_pruebas') or False,
                'consulto_suministros': post.get('consulto_suministros') or False,
                'consulto_problemas': post.get('consulto_problemas') or False,
                'retiro_tecnico': post.get('retiro_tecnico') or False,
                'comentarios': post.get('comentarios') or False,
            }

            # Completar desde portal.
            # Este método debe existir en el modelo client.service.evaluation mejorado.
            evaluation.sudo().action_complete_from_portal(
                vals=values,
                request=request
            )

            return request.render('sat.evaluation_thanks', {
                'evaluation': evaluation
            })

        except Exception as e:
            _logger.exception(
                "Error al procesar evaluación con token %s: %s",
                token,
                str(e)
            )
            return request.render('sat.evaluation_error', {})