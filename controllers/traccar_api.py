# -*- coding: utf-8 -*-
"""
Controlador API: Traccar → Odoo
================================
Archivo: controllers/traccar_api.py
"""
import json
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class TraccarController(http.Controller):

    def _validar_authorization(self):
        """Valida Authorization tolerante a espacios y formato."""

        auth_header = request.httprequest.headers.get('Authorization')
        if not auth_header:
            _logger.warning("[TRACCAR-AUTH] ❌ Sin header Authorization")
            return False

        _logger.info("[TRACCAR-AUTH] HEADER COMPLETO >>> %s <<<", auth_header)

        auth_header = auth_header.strip()

        parts = auth_header.split()

        if len(parts) != 2:
            _logger.warning("[TRACCAR-AUTH] ❌ Formato inválido")
            return False

        esquema, token_recibido = parts

        if esquema.lower() != 'bearer':
            _logger.warning("[TRACCAR-AUTH] ❌ No es esquema Bearer")
            return False

        token_config = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('traccar.api_key', default='')
        )

        if not token_config:
            _logger.error("[TRACCAR-AUTH] ❌ traccar.api_key no configurada")
            return False

        if token_recibido != token_config:
            _logger.warning(
                "[TRACCAR-AUTH] ❌ Token incorrecto | Recibido: %s | Esperado: %s",
                token_recibido[:20], token_config[:20]
            )
            return False

        _logger.info("[TRACCAR-AUTH] ✅ Token válido")
        return True

    def _json_response(self, data, status=200):
        return Response(
            json.dumps(data, ensure_ascii=False, default=str),
            status=status,
            content_type='application/json',
        )

    @http.route(
        '/api/traccar/evento',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def recibir_evento_traccar(self, **kwargs):

        raw_body = request.httprequest.data

        try:
            body = json.loads(raw_body)
        except Exception:
            _logger.error("[TRACCAR] ❌ JSON inválido")
            return self._json_response({'success': False, 'error': 'JSON inválido'}, 400)

        event    = body.get('event') or {}
        device   = body.get('device') or {}
        position = body.get('position') or {}
        geofence = body.get('geofence') or {}

        event_type = event.get('type', 'unknown')
        device_id  = device.get('id')

        # 🔥 SOLO estos eventos necesitan seguridad + procesamiento
        eventos_ticket = ['geofenceEnter', 'geofenceExit', 'deviceMoving']

        if event_type not in eventos_ticket:
            _logger.info("[TRACCAR] Evento '%s' ignorado (no relevante)", event_type)
            return self._json_response({'success': True})

        # 🔐 Validar token SOLO si el evento es relevante
        if not self._validar_authorization():
            _logger.warning("[TRACCAR] ❌ Token inválido para evento relevante")
            return self._json_response({'success': False, 'error': 'No autorizado'}, 401)

        # ---- Procesamiento normal ----

        _logger.info(
            "[TRACCAR] ✅ Evento: %s | Device: %s",
            event_type, device.get('name')
        )

        try:
            datos = {
                'latitude':   position.get('latitude'),
                'longitude':  position.get('longitude'),
                'speed':      position.get('speed'),
                'address':    position.get('address'),
                'geofenceId': geofence.get('id'),
            }

            odoo_result = (
                request.env['ticket.alquiler']
                .sudo()
                .api_actualizar_estado_gps(device_id, event_type, datos)
            )

        except Exception:
            _logger.exception("[TRACCAR] ❌ Error actualizando tickets")
            return self._json_response({'success': False}, 500)

        return self._json_response({
            'success': True,
            'event': event_type,
            'device': device.get('name'),
            'tickets': odoo_result.get('tickets_actualizados', []) if odoo_result else [],
        })