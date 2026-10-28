# -*- coding: utf-8 -*-
"""Formulario público de evaluaciones de SAT - Odoo 19."""
import logging
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)

ALLOWED_VALUES = {
    'solucion_problema': {'1', '2', '3', '4', '5'},
    'explicacion_trabajo': {'1', '2', '3', '4', '5'},
    'realizo_pruebas': {'si', 'no'},
    'consulto_suministros': {'si', 'no'},
}
REQUIRED_FIELDS = tuple(ALLOWED_VALUES)


class EvaluationController(http.Controller):

    def _find_evaluation(self, token):
        Model = request.env['client.service.evaluation'].sudo()
        if not token or not isinstance(token, str):
            return Model.browse()
        return Model.search([('token', '=', token)], limit=1)

    def _is_available(self, evaluation):
        if not evaluation:
            return False
        if evaluation.state != 'sent' or evaluation._has_answered_evaluation():
            return False
        if not evaluation.expiration_date or evaluation.expiration_date <= fields.Datetime.now():
            return False
        return True

    @http.route(
        ['/evaluation/submit/<string:token>'],
        type='http', auth='public', website=True, methods=['GET'],
    )
    def evaluation_form(self, token, **kw):
        evaluation = self._find_evaluation(token)
        if not self._is_available(evaluation):
            return request.render('sat.evaluation_expired', {})
        try:
            evaluation._register_portal_access(request=request)
        except Exception:
            _logger.exception('Error registrando acceso evaluación id=%s', evaluation.id)
        return request.render('sat.evaluation_form_template', {
            'evaluation': evaluation,
            'error_message': False,
        })

    @http.route(
        ['/evaluation/submit/process'],
        type='http', auth='public', website=True, methods=['POST'], csrf=True,
    )
    def process_evaluation(self, **post):
        token = (post.get('token') or '').strip()
        evaluation = self._find_evaluation(token)
        if not self._is_available(evaluation):
            return request.render('sat.evaluation_expired', {})

        vals = {}
        for key, allowed in ALLOWED_VALUES.items():
            raw = str(post.get(key) or '').strip()
            vals[key] = raw if raw in allowed else False
        if any(not vals[field] for field in REQUIRED_FIELDS):
            return request.render('sat.evaluation_form_template', {
                'evaluation': evaluation,
                'error_message': 'Por favor responda todas las preguntas antes de enviar.',
            })
        vals['comentarios'] = str(post.get('comentarios') or '').strip()[:1000] or False

        try:
            # Bloqueo transaccional: impide dos respuestas simultáneas al mismo token.
            request.env.cr.execute(
                'SELECT id FROM client_service_evaluation WHERE id = %s FOR UPDATE',
                (evaluation.id,),
            )
            evaluation.invalidate_recordset()
            if not self._is_available(evaluation):
                return request.render('sat.evaluation_expired', {})
            evaluation.action_complete_from_portal(vals=vals, request=request)
        except Exception:
            _logger.exception('Error guardando evaluación id=%s', evaluation.id)
            return request.render('sat.evaluation_error', {})
        return request.render('sat.evaluation_thanks', {'evaluation': evaluation})
