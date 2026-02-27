from odoo import http
from odoo.http import request

class SolicitudParteController(http.Controller):

    @http.route('/solicitud-parte/aprobar/<string:token>',
                 type='http', auth='public', website=True)
    def aprobar_solicitud(self, token, **kwargs):
         solicitud = request.env['solicitud.parte.tecnico'].sudo().search(
             [('access_token', '=', token)], limit=1)
         if not solicitud:
             return request.render('website.404')
         if solicitud.state != 'pendiente_aprobacion':
             return "<h2>Esta solicitud ya fue procesada.</h2>"
         solicitud.action_aprobar()
         return "<h2>✅ Solicitud aprobada correctamente. El técnico fue notificado.</h2>"

    @http.route('/solicitud-parte/confirmar/<string:token>',
                 type='http', auth='public', website=True)
    def confirmar_retiro(self, token, **kwargs):
         solicitud = request.env['solicitud.parte.tecnico'].sudo().search(
             [('access_token', '=', token)], limit=1)
         if not solicitud:
             return request.render('website.404')
         if solicitud.state != 'aprobada':
             return "<h2>Esta solicitud ya fue procesada.</h2>"
         solicitud.with_user(request.env.ref('base.user_admin')).action_confirmar_retiro()
         return "<h2>📦 Retiro confirmado. ¡Gracias!</h2>"