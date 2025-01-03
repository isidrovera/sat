# controllers/evaluation_controller.py
from odoo import http
from odoo.http import request
import werkzeug
import logging

_logger = logging.getLogger(__name__)

class EvaluationController(http.Controller):
    @http.route(['/evaluation/submit/<string:token>'], type='http', auth='public', website=True)
    def evaluation_form(self, token, **kw):
        evaluation = request.env['client.service.evaluation'].sudo().search([
            ('token', '=', token),
            ('state', '=', 'sent')
        ], limit=1)
        
        if not evaluation:
            return request.render('sat.evaluation_expired', {})
            
        return request.render('sat.evaluation_form_template', {
            'evaluation': evaluation,
        })

    @http.route(['/evaluation/submit/process'], type='http', auth='public', website=True, methods=['POST'])
    def process_evaluation(self, **post):
        token = post.get('token')
        evaluation = request.env['client.service.evaluation'].sudo().search([
            ('token', '=', token),
            ('state', '=', 'sent')
        ], limit=1)

        if not evaluation:
            return request.render('sat.evaluation_expired', {})

        try:
            # Actualizar evaluación
            values = {
                'saludo_presentacion': post.get('saludo_presentacion'),
                'diagnostico_problema': post.get('diagnostico_problema'),
                'solucion_problema': post.get('solucion_problema'),
                'explicacion_trabajo': post.get('explicacion_trabajo'),
                'limpieza_orden': post.get('limpieza_orden'),
                'revision_adicional': post.get('revision_adicional'),
                'realizo_pruebas': post.get('realizo_pruebas'),
                'consulto_suministros': post.get('consulto_suministros'),
                'consulto_problemas': post.get('consulto_problemas'),
                'retiro_tecnico':post.get('retiro_tecnico'),
                'comentarios': post.get('comentarios'),
                'state': 'completed'
            }
            
            evaluation.sudo().write(values)
            
            return request.render('sat.evaluation_thanks', {
                'evaluation': evaluation
            })
            
        except Exception as e:
            _logger.error("Error al procesar evaluación: %s", str(e))
            return request.render('sat.evaluation_error', {})
