# controllers/evaluation_controller.py
from odoo import http, fields
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

# Valores permitidos por campo: se descarta cualquier valor manipulado en el POST
# que no pertenezca a la selección, evitando errores de escritura o datos basura.
ALLOWED_VALUES = {
    'solucion_problema': {'1', '2', '3', '4', '5'},
    'explicacion_trabajo': {'1', '2', '3', '4', '5'},
    'realizo_pruebas': {'si', 'no'},
    'consulto_suministros': {'si', 'no'},
}

# Preguntas obligatorias de la encuesta simplificada
REQUIRED_FIELDS = [
    'solucion_problema',
    'explicacion_trabajo',
    'realizo_pruebas',
    'consulto_suministros',
]


class EvaluationController(http.Controller):

    def _get_evaluation_by_token(self, token):
        if not token:
            return request.env['client.service.evaluation'].sudo().browse()

        return request.env['client.service.evaluation'].sudo().search([
            ('token', '=', token),
            ('state', '=', 'sent')
        ], limit=1)

    @http.route(
        ['/evaluation/submit/<string:token>'],
        type='http',
        auth='public',
        website=True
    )
    def evaluation_form(self, token, **kw):
        evaluation = self._get_evaluation_by_token(token)

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

        evaluation = self._get_evaluation_by_token(token)

        if not evaluation:
            return request.render('sat.evaluation_expired', {})

        try:
            # Sanear: solo aceptar valores válidos de cada selección
            values = {}
            for field_name, allowed in ALLOWED_VALUES.items():
                raw_value = (post.get(field_name) or '').strip()
                values[field_name] = raw_value if raw_value in allowed else False

            # Validación servidor: las 4 preguntas son obligatorias.
            # El formulario ya las exige en el navegador, pero un POST
            # incompleto no debe completar la evaluación a medias.
            missing_fields = [
                field_name for field_name in REQUIRED_FIELDS
                if not values.get(field_name)
            ]

            if missing_fields:
                _logger.warning(
                    "POST incompleto para evaluación token %s. Faltan: %s",
                    token,
                    ', '.join(missing_fields)
                )
                return request.render('sat.evaluation_form_template', {
                    'evaluation': evaluation,
                    'error_message': 'Por favor responda todas las preguntas antes de enviar.',
                })

            comentarios = (post.get('comentarios') or '').strip()
            values['comentarios'] = comentarios or False

            # Completar desde portal: guarda respuestas, IP, navegador,
            # fecha real de respuesta y fuente de completado.
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