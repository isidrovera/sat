from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class SolicitudParteController(http.Controller):

    # ── Gerencia aprueba retiro ───────────────────────────────────────────
    @http.route(
        '/solicitud-parte/aprobar/<string:token>',
        type='http', auth='public', website=False, csrf=False)
    def aprobar_solicitud(self, token, **kwargs):
        env = request.env
        solicitud = env['solicitud.parte.tecnico'].sudo().search(
            [('access_token', '=', token)], limit=1)

        if not solicitud:
            return self._page_error('Token inválido o solicitud no encontrada.')

        if solicitud.state == 'completada':
            return self._page_info(
                '✅ Esta solicitud ya fue completada anteriormente.',
                solicitud.name)

        if solicitud.state != 'pendiente_aprobacion':
            return self._page_info(
                f'Esta solicitud se encuentra en estado: <b>{dict(solicitud._fields["state"].selection).get(solicitud.state)}</b>.<br/>'
                f'Solo se pueden aprobar solicitudes en estado Pendiente de Aprobación.',
                solicitud.name)

        try:
            solicitud.with_user(
                env.ref('base.user_admin')).action_aprobar()
        except Exception as e:
            _logger.error('Error aprobando solicitud %s: %s', token, e)
            return self._page_error(f'Error al procesar la aprobación: {e}')

        return self._page_exito(
            '✅ Solicitud Aprobada',
            f'La solicitud <b>{solicitud.name}</b> fue aprobada correctamente.<br/>'
            f'El técnico <b>{solicitud.tecnico_id.name}</b> fue notificado para proceder con el retiro.',
            color='#2f855a')

    # ── Técnico confirma retiro ───────────────────────────────────────────
    @http.route(
        '/solicitud-parte/confirmar/<string:token>',
        type='http', auth='public', website=False, csrf=False)
    def confirmar_retiro(self, token, **kwargs):
        env = request.env
        solicitud = env['solicitud.parte.tecnico'].sudo().search(
            [('access_token', '=', token)], limit=1)

        if not solicitud:
            return self._page_error('Token inválido o solicitud no encontrada.')

        if solicitud.state == 'completada':
            return self._page_info(
                '✅ El retiro ya fue confirmado anteriormente.',
                solicitud.name)

        if solicitud.state != 'aprobada':
            return self._page_info(
                f'Esta solicitud se encuentra en estado: <b>{dict(solicitud._fields["state"].selection).get(solicitud.state)}</b>.<br/>'
                f'Solo se pueden confirmar solicitudes aprobadas.',
                solicitud.name)

        try:
            solicitud.with_user(
                env.ref('base.user_admin')).action_confirmar_retiro()
        except Exception as e:
            _logger.error('Error confirmando retiro %s: %s', token, e)
            return self._page_error(f'Error al confirmar el retiro: {e}')

        return self._page_exito(
            '📦 Retiro Confirmado',
            f'La solicitud <b>{solicitud.name}</b> fue completada.<br/>'
            f'El movimiento quedó registrado en las máquinas origen.',
            color='#2b6cb0')

    # ── Helpers HTML ──────────────────────────────────────────────────────
    def _page_exito(self, titulo, mensaje, color='#2f855a'):
        return request.make_response(
            f"""<!DOCTYPE html><html><head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width,initial-scale=1">
            <title>{titulo}</title>
            <style>
                body{{font-family:Arial,sans-serif;background:#f5f5f5;
                      display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}}
                .card{{background:#fff;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,.1);
                       max-width:500px;width:90%;overflow:hidden;}}
                .header{{background:{color};padding:30px;text-align:center;}}
                .header h1{{color:#fff;margin:0;font-size:24px;}}
                .body{{padding:30px;text-align:center;line-height:1.6;}}
                .footer{{background:#edf2f7;padding:12px;text-align:center;
                         color:#718096;font-size:12px;}}
            </style></head><body>
            <div class="card">
                <div class="header"><h1>{titulo}</h1></div>
                <div class="body"><p>{mensaje}</p></div>
                <div class="footer">Sistema de Taller — Andes Solution Copiers</div>
            </div></body></html>""",
            headers={'Content-Type': 'text/html; charset=utf-8'})

    def _page_info(self, mensaje, nombre_solicitud):
        return self._page_exito(
            f'Solicitud {nombre_solicitud}', mensaje, color='#4a5568')

    def _page_error(self, mensaje):
        return self._page_exito('❌ Error', mensaje, color='#c53030')