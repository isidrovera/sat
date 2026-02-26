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
        """Valida Authorization: Bearer <token>."""
        auth_header = request.httprequest.headers.get('Authorization', '')

        _logger.info(
            "[TRACCAR-AUTH] Header recibido: '%s...' (primeros 30 chars)",
            auth_header[:30]
        )

        if not auth_header.startswith('Bearer '):
            _logger.warning("[TRACCAR-AUTH] ❌ No tiene formato Bearer")
            return False

        token_recibido = auth_header[7:]
        token_config = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('traccar.api_key', default='')
        )

        if not token_config:
            _logger.error("[TRACCAR-AUTH] ❌ traccar.api_key no configurada en Odoo")
            return False

        coincide = token_recibido == token_config
        if not coincide:
            _logger.warning(
                "[TRACCAR-AUTH] ❌ Token NO coincide | "
                "Recibido: '%s' | Esperado: '%s'",
                token_recibido[:20], token_config[:20]
            )
        else:
            _logger.info("[TRACCAR-AUTH] ✅ Token válido")

        return coincide

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
        """
        Traccar envía JSON: {event, device, position, geofence}
        """
        try:
            raw_body = request.httprequest.data
            _logger.info("[TRACCAR-RAW] Body recibido: %s", raw_body[:500])
        except Exception:
            pass

        if not self._validar_authorization():
            _logger.warning("[TRACCAR] ❌ Petición rechazada — token inválido")
            return self._json_response({'success': False, 'error': 'No autorizado'}, 401)

        try:
            body = json.loads(request.httprequest.data)
        except Exception:
            _logger.error("[TRACCAR] ❌ JSON inválido")
            return self._json_response({'success': False, 'error': 'JSON inválido'}, 400)

        event    = body.get('event') or {}
        device   = body.get('device') or {}
        # ✅ CORRECCIÓN: proteger contra position=null y geofence=null
        position = body.get('position') or {}
        geofence = body.get('geofence') or {}

        event_type = event.get('type', 'unknown')
        device_id  = device.get('id')

        # ✅ Log completo para diagnóstico
        _logger.info(
            "[TRACCAR] ✅ Evento: %s | Device ID: %s | Device name: %s | "
            "lat: %s | lon: %s | geofence_id: %s",
            event_type, device_id, device.get('name'),
            position.get('latitude'), position.get('longitude'),
            geofence.get('id'),
        )

        eventos_ticket = ['geofenceEnter', 'geofenceExit', 'deviceMoving']
        odoo_result = None

        if event_type in eventos_ticket and device_id:
            try:
                datos = {
                    'latitude':   position.get('latitude'),
                    'longitude':  position.get('longitude'),
                    'speed':      position.get('speed'),
                    'address':    position.get('address'),
                    'geofenceId': geofence.get('id'),
                }

                _logger.info(
                    "[TRACCAR] Procesando: device_id=%s evento=%s datos=%s",
                    device_id, event_type, datos
                )

                odoo_result = (
                    request.env['ticket.alquiler']
                    .sudo()
                    .api_actualizar_estado_gps(device_id, event_type, datos)
                )

                _logger.info("[TRACCAR] Resultado: %s", odoo_result)

            except Exception:
                _logger.exception("[TRACCAR] ❌ Error actualizando tickets")
        else:
            _logger.info(
                "[TRACCAR] Evento '%s' ignorado (no es de ticket o sin device_id)",
                event_type
            )

        return self._json_response({
            'success': True,
            'event':   event_type,
            'device':  device.get('name'),
            'tickets': odoo_result.get('tickets_actualizados', []) if odoo_result else [],
        })