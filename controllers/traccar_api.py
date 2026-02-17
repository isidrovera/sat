# -*- coding: utf-8 -*-
"""
Controlador API: Traccar → Odoo
================================
Recibe eventos GPS de Traccar (event.forward) y actualiza tickets.
Sin notificaciones WhatsApp (se agregará después).

Autenticación: Authorization: Bearer <token>
Parámetro Odoo: traccar.api_key

Archivo: controllers/traccar_api.py
"""
import json
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class TraccarController(http.Controller):

    def _validar_authorization(self):
        """Valida Authorization: Bearer <token>."""
        auth_header = request.httprequest.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False

        token_recibido = auth_header[7:]
        token_config = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('traccar.api_key', default='')
        )

        if not token_config:
            _logger.error("[TRACCAR] traccar.api_key no configurada")
            return False

        return token_recibido == token_config

    def _json_response(self, data, status=200):
        return Response(
            json.dumps(data, ensure_ascii=False, default=str),
            status=status,
            content_type='application/json',
        )

    # ═══════════════════════════════════════════════════════════
    #  POST /api/traccar/evento
    #  Recibe evento directo de Traccar (event.forward)
    # ═══════════════════════════════════════════════════════════

    @http.route(
        '/api/traccar/evento',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def recibir_evento_traccar(self, **kwargs):
        """
        Traccar envía JSON: {event, device, position, geofence}
        Odoo actualiza el estado del ticket según el evento.
        """
        if not self._validar_authorization():
            return self._json_response({'success': False, 'error': 'No autorizado'}, 401)

        try:
            body = json.loads(request.httprequest.data)
        except Exception:
            return self._json_response({'success': False, 'error': 'JSON inválido'}, 400)

        event = body.get('event', {})
        device = body.get('device', {})
        position = body.get('position', {})
        geofence = body.get('geofence')

        event_type = event.get('type', 'unknown')
        device_id = device.get('id')

        _logger.info(
            "[TRACCAR] Evento: %s | Device: %s (%s)",
            event_type, device.get('name'), device_id,
        )

        # Solo eventos que afectan tickets
        eventos_ticket = ['geofenceEnter', 'geofenceExit', 'deviceMoving']
        odoo_result = None

        if event_type in eventos_ticket and device_id:
            try:
                datos = {
                    'latitude': position.get('latitude'),
                    'longitude': position.get('longitude'),
                    'speed': position.get('speed'),
                    'address': position.get('address'),
                    'geofenceId': geofence.get('id') if geofence else None,
                }

                odoo_result = (
                    request.env['ticket.alquiler']
                    .sudo()
                    .api_actualizar_estado_gps(device_id, event_type, datos)
                )

                _logger.info("[TRACCAR] Resultado: %s", odoo_result)

            except Exception:
                _logger.exception("[TRACCAR] Error actualizando tickets")

        return self._json_response({
            'success': True,
            'event': event_type,
            'device': device.get('name'),
            'tickets': odoo_result.get('tickets_actualizados', []) if odoo_result else [],
        })