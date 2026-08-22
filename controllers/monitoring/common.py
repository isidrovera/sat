# -*- coding: utf-8 -*-

import json
import logging
import traceback

from werkzeug.wrappers import Response

from odoo import _
from odoo.http import request


_logger = logging.getLogger(__name__)


MAX_BODY_BYTES = 10 * 1024 * 1024


class MonitoringApiError(Exception):
    """Error controlado de la API de monitoreo."""

    def __init__(self, message, status=400, code='bad_request', details=None):
        super().__init__(message)
        self.message = message
        self.status = int(status)
        self.code = code
        self.details = details or {}


class MonitoringApiMixin:
    """
    Helpers compartidos por todos los controladores del agente.

    Autenticación esperada:

        X-Agent-Code: cliente_lima_01
        Authorization: Bearer <TOKEN>

    Las rutas usan type='http' para exponer JSON REST normal y evitar
    el envoltorio JSON-RPC de Odoo.
    """

    # =========================================================
    # RESPUESTAS
    # =========================================================

    def _json_response(self, payload=None, status=200, headers=None):
        body = json.dumps(
            payload if payload is not None else {},
            ensure_ascii=False,
            separators=(',', ':'),
            default=str,
        )

        response_headers = [
            ('Content-Type', 'application/json; charset=utf-8'),
            ('Cache-Control', 'no-store'),
            ('Pragma', 'no-cache'),
            ('X-Content-Type-Options', 'nosniff'),
        ]

        for key, value in (headers or {}).items():
            response_headers.append((str(key), str(value)))

        return Response(
            body,
            status=int(status),
            headers=response_headers,
        )

    def _ok(self, data=None, status=200, **extra):
        payload = {
            'ok': True,
            'data': data if data is not None else {},
        }
        payload.update(extra)
        return self._json_response(payload, status=status)

    def _error(self, message, status=400, code='bad_request', details=None):
        return self._json_response(
            {
                'ok': False,
                'error': {
                    'code': code,
                    'message': str(message),
                    'details': details or {},
                },
            },
            status=status,
        )

    # =========================================================
    # REQUEST
    # =========================================================

    def _get_header(self, name):
        return (request.httprequest.headers.get(name) or '').strip()

    def _get_bearer_token(self):
        value = self._get_header('Authorization')
        if not value:
            return ''

        parts = value.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return ''

        return parts[1].strip()

    def _read_json(self, required=True):
        content_length = request.httprequest.content_length or 0
        if content_length > MAX_BODY_BYTES:
            raise MonitoringApiError(
                _('El cuerpo de la solicitud es demasiado grande.'),
                status=413,
                code='payload_too_large',
            )

        raw = request.httprequest.get_data(cache=True, as_text=True) or ''
        raw = raw.strip()

        if not raw:
            if required:
                raise MonitoringApiError(
                    _('La solicitud debe contener un JSON válido.'),
                    status=400,
                    code='empty_json_body',
                )
            return {}

        try:
            payload = json.loads(raw)
        except Exception:
            raise MonitoringApiError(
                _('El cuerpo de la solicitud no contiene JSON válido.'),
                status=400,
                code='invalid_json',
            )

        if not isinstance(payload, dict):
            raise MonitoringApiError(
                _('El JSON principal debe ser un objeto.'),
                status=400,
                code='json_object_required',
            )

        return payload

    # =========================================================
    # AUTENTICACIÓN
    # =========================================================

    def _authenticate_agent(self):
        agent_code = self._get_header('X-Agent-Code')
        token = self._get_bearer_token()

        if not agent_code or not token:
            raise MonitoringApiError(
                _('Faltan credenciales del agente.'),
                status=401,
                code='authentication_required',
            )

        agent = request.env['sat.monitoring.agent'].sudo().authenticate_agent(
            agent_code,
            token,
        )

        if not agent:
            raise MonitoringApiError(
                _('Credenciales del agente inválidas.'),
                status=401,
                code='invalid_agent_credentials',
            )

        if not agent.active or not agent.enabled:
            raise MonitoringApiError(
                _('El agente está deshabilitado.'),
                status=403,
                code='agent_disabled',
            )

        return agent.sudo()

    # =========================================================
    # PROPIEDAD / AUTORIZACIÓN
    # =========================================================

    def _get_agent_network(self, agent, network_id):
        try:
            network_id = int(network_id)
        except Exception:
            raise MonitoringApiError(
                _('network_id no es válido.'),
                status=400,
                code='invalid_network_id',
            )

        network = request.env['sat.monitoring.network'].sudo().search(
            [
                ('id', '=', network_id),
                ('agent_id', '=', agent.id),
                ('active', '=', True),
            ],
            limit=1,
        )

        if not network:
            raise MonitoringApiError(
                _('La red no pertenece al agente autenticado.'),
                status=403,
                code='network_not_allowed',
            )

        return network

    def _get_agent_device(self, agent, device_id, require_active=True):
        try:
            device_id = int(device_id)
        except Exception:
            raise MonitoringApiError(
                _('device_id no es válido.'),
                status=400,
                code='invalid_device_id',
            )

        domain = [
            ('id', '=', device_id),
            ('agent_id', '=', agent.id),
        ]
        if require_active:
            domain.append(('active', '=', True))

        device = request.env['sat.monitoring.device'].sudo().search(
            domain,
            limit=1,
        )

        if not device:
            raise MonitoringApiError(
                _('El equipo no pertenece al agente autenticado.'),
                status=403,
                code='device_not_allowed',
            )

        return device

    def _get_agent_credential(self, agent, credential_id):
        try:
            credential_id = int(credential_id)
        except Exception:
            raise MonitoringApiError(
                _('credential_id no es válido.'),
                status=400,
                code='invalid_credential_id',
            )

        credential = request.env['sat.snmp.credential'].sudo().browse(
            credential_id
        ).exists()

        if not credential:
            raise MonitoringApiError(
                _('La credencial SNMP no existe.'),
                status=404,
                code='credential_not_found',
            )

        if not credential.can_be_used_by_agent(agent):
            raise MonitoringApiError(
                _('El agente no está autorizado para usar esta credencial.'),
                status=403,
                code='credential_not_allowed',
            )

        return credential

    # =========================================================
    # UTILIDADES
    # =========================================================

    def _safe_int(self, value, default=0, minimum=None, maximum=None):
        try:
            result = int(value)
        except Exception:
            result = default

        if minimum is not None:
            result = max(result, minimum)
        if maximum is not None:
            result = min(result, maximum)

        return result

    def _safe_float(self, value, default=0.0, minimum=None, maximum=None):
        try:
            result = float(value)
        except Exception:
            result = default

        if minimum is not None:
            result = max(result, minimum)
        if maximum is not None:
            result = min(result, maximum)

        return result

    def _clean_text(self, value, max_length=None):
        if value in (None, False):
            return ''

        result = str(value).strip()
        if max_length:
            result = result[:max_length]
        return result

    def _included_ips(self, network):
        return {
            line.strip()
            for line in (network.included_ips or '').splitlines()
            if line.strip() and not line.strip().startswith('#')
        }

    def _ip_allowed_in_network(self, network, ip):
        ip = self._clean_text(ip)
        if not ip:
            return False

        if network.is_ip_excluded(ip):
            return False

        if network.contains_ip(ip):
            return True

        return ip in self._included_ips(network)

    # =========================================================
    # EXCEPCIONES
    # =========================================================

    def _handle_api_exception(self, error, endpoint=None):
        if isinstance(error, MonitoringApiError):
            return self._error(
                error.message,
                status=error.status,
                code=error.code,
                details=error.details,
            )

        try:
            request.env.cr.rollback()
        except Exception:
            pass

        _logger.error(
            '[MONITORING API] Unhandled error endpoint=%s error=%s\n%s',
            endpoint or '',
            error,
            traceback.format_exc(),
        )

        return self._error(
            _('Ocurrió un error interno procesando la solicitud.'),
            status=500,
            code='internal_server_error',
        )
