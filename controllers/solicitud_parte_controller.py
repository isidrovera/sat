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

    # ── NUEVO: Logística confirma que SÍ tiene en stock ──────────────────
    @http.route(
        '/solicitud-parte/logistica/<string:token>/tiene',
        type='http', auth='public', website=False, csrf=False)
    def logistica_tiene(self, token, **kwargs):
        env = request.env
        solicitud = env['solicitud.parte.tecnico'].sudo().search(
            [('access_token_logistica', '=', token)], limit=1)

        if not solicitud:
            return self._page_error('Token inválido o solicitud no encontrada.')

        if solicitud.state == 'pendiente_aprobacion':
            return self._page_info(
                '✅ Ya confirmaste que tienes stock para esta solicitud.<br/>'
                'Gerencia fue notificada y está pendiente de aprobación.',
                solicitud.name)

        if solicitud.state != 'consulta_logistica':
            estado_label = dict(solicitud._fields['state'].selection).get(solicitud.state, solicitud.state)
            return self._page_info(
                f'Esta solicitud ya fue procesada.<br/>'
                f'Estado actual: <b>{estado_label}</b>.',
                solicitud.name)

        try:
            solicitud.with_user(
                env.ref('base.user_admin')).action_logistica_tiene()
        except Exception as e:
            _logger.error('Error en respuesta logistica_tiene %s: %s', token, e)
            return self._page_error(f'Error al procesar la respuesta: {e}')

        # Construir lista de partes para mostrar en pantalla
        partes_html = ''.join([
            f'<div style="padding:8px 12px;margin-bottom:6px;'
            f'border-left:4px solid #805ad5;background:#faf5ff;">'
            f'<b>{l.parte}</b>'
            f'{"<br/><span style=\'color:#718096;font-size:13px\'>" + l.descripcion + "</span>" if l.descripcion else ""}'
            f'</div>'
            for l in solicitud.linea_ids.filtered(lambda l: l.state == 'en_stock_logistica')
        ])

        return self._page_exito(
            '✅ Confirmado — Tienes Stock',
            f'<p>Confirmaste disponibilidad en stock para la solicitud <b>{solicitud.name}</b>.</p>'
            f'<p style="color:#553c9a;font-weight:bold;">Repuestos confirmados:</p>'
            f'{partes_html}'
            f'<p style="margin-top:20px;">Gerencia fue notificada y debe autorizar la salida.<br/>'
            f'Recibirás un correo y WhatsApp cuando la entrega sea aprobada.</p>',
            color='#6b46c1')

    # ── NUEVO: Logística confirma que NO tiene en stock ───────────────────
    @http.route(
        '/solicitud-parte/logistica/<string:token>/no-tiene',
        type='http', auth='public', website=False, csrf=False)
    def logistica_no_tiene(self, token, **kwargs):
        env = request.env
        solicitud = env['solicitud.parte.tecnico'].sudo().search(
            [('access_token_logistica', '=', token)], limit=1)

        if not solicitud:
            return self._page_error('Token inválido o solicitud no encontrada.')

        if solicitud.state == 'pendiente_aprobacion_compra':
            return self._page_info(
                '❌ Ya confirmaste que no tienes stock para esta solicitud.<br/>'
                'Gerencia fue notificada para autorizar la compra externa.',
                solicitud.name)

        if solicitud.state != 'consulta_logistica':
            estado_label = dict(solicitud._fields['state'].selection).get(solicitud.state, solicitud.state)
            return self._page_info(
                f'Esta solicitud ya fue procesada.<br/>'
                f'Estado actual: <b>{estado_label}</b>.',
                solicitud.name)

        try:
            solicitud.with_user(
                env.ref('base.user_admin')).action_logistica_no_tiene()
        except Exception as e:
            _logger.error('Error en respuesta logistica_no_tiene %s: %s', token, e)
            return self._page_error(f'Error al procesar la respuesta: {e}')

        # Construir lista de partes para mostrar en pantalla
        partes_html = ''.join([
            f'<div style="padding:8px 12px;margin-bottom:6px;'
            f'border-left:4px solid #ed8936;background:#fffaf0;">'
            f'<b>{l.parte}</b>'
            f'{"<br/><span style=\'color:#718096;font-size:13px\'>" + l.descripcion + "</span>" if l.descripcion else ""}'
            f'</div>'
            for l in solicitud.linea_ids.filtered(lambda l: l.state == 'compra_externa')
        ])

        return self._page_exito(
            '❌ Confirmado — Sin Stock',
            f'<p>Confirmaste que <b>no tienes disponibilidad</b> en stock para la solicitud <b>{solicitud.name}</b>.</p>'
            f'<p style="color:#c05621;font-weight:bold;">Repuestos a conseguir:</p>'
            f'{partes_html}'
            f'<p style="margin-top:20px;">Gerencia fue notificada para autorizar la compra externa.<br/>'
            f'Recibirás un correo y WhatsApp con la orden de compra una vez aprobada.</p>',
            color='#c05621')

    # ── NUEVO: Gerencia aprueba compra externa ────────────────────────────
    @http.route(
        '/solicitud-parte/aprobar-compra/<string:token>',
        type='http', auth='public', website=False, csrf=False)
    def aprobar_compra(self, token, **kwargs):
        env = request.env
        solicitud = env['solicitud.parte.tecnico'].sudo().search(
            [('access_token', '=', token)], limit=1)

        if not solicitud:
            return self._page_error('Token inválido o solicitud no encontrada.')

        if solicitud.state == 'por_conseguir':
            return self._page_info(
                '✅ La compra ya fue aprobada anteriormente.<br/>'
                'Logística ya recibió la orden de gestionar la adquisición.',
                solicitud.name)

        if solicitud.state != 'pendiente_aprobacion_compra':
            estado_label = dict(solicitud._fields['state'].selection).get(solicitud.state, solicitud.state)
            return self._page_info(
                f'Esta solicitud se encuentra en estado: <b>{estado_label}</b>.<br/>'
                f'Solo se pueden aprobar compras en estado Pendiente Aprobación Compra.',
                solicitud.name)

        try:
            solicitud.with_user(
                env.ref('base.user_admin')).action_aprobar_compra()
        except Exception as e:
            _logger.error('Error aprobando compra %s: %s', token, e)
            return self._page_error(f'Error al procesar la aprobación: {e}')

        # Construir lista de partes para mostrar en pantalla
        partes_html = ''.join([
            f'<div style="padding:8px 12px;margin-bottom:6px;'
            f'border-left:4px solid #ed8936;background:#fffaf0;">'
            f'<b>{l.parte}</b>'
            f'{"<br/><span style=\'color:#718096;font-size:13px\'>" + l.descripcion + "</span>" if l.descripcion else ""}'
            f'</div>'
            for l in solicitud.linea_ids.filtered(lambda l: l.state == 'compra_externa')
        ])

        return self._page_exito(
            '🛒 Compra Aprobada',
            f'<p>La compra externa para la solicitud <b>{solicitud.name}</b> fue autorizada.</p>'
            f'<p style="color:#c05621;font-weight:bold;">Repuestos a adquirir:</p>'
            f'{partes_html}'
            f'<p style="margin-top:20px;">'
            f'Logística recibió la orden de gestionar la adquisición.<br/>'
            f'El técnico <b>{solicitud.tecnico_id.name}</b> fue notificado que está en gestión.</p>',
            color='#c05621')

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
                       max-width:520px;width:90%;overflow:hidden;}}
                .header{{background:{color};padding:30px;text-align:center;}}
                .header h1{{color:#fff;margin:0;font-size:22px;}}
                .body{{padding:30px;line-height:1.6;color:#2d3748;}}
                .body p{{margin:0 0 12px 0;}}
                .footer{{background:#edf2f7;padding:12px;text-align:center;
                         color:#718096;font-size:12px;}}
            </style></head><body>
            <div class="card">
                <div class="header"><h1>{titulo}</h1></div>
                <div class="body">{mensaje}</div>
                <div class="footer">Sistema de Taller — Andes Solution Copiers</div>
            </div></body></html>""",
            headers={'Content-Type': 'text/html; charset=utf-8'})

    def _page_info(self, mensaje, nombre_solicitud):
        return self._page_exito(
            f'Solicitud {nombre_solicitud}', mensaje, color='#4a5568')

    def _page_error(self, mensaje):
        return self._page_exito('❌ Error', mensaje, color='#c53030')