# -*- coding: utf-8 -*-

import json
import logging
import time

from odoo import http
from odoo.http import request

from .whatsapp_partner_mixin import WhatsAppPartnerMixin
from .whatsapp_context_mixin import WhatsAppContextMixin
from .whatsapp_message_mixin import WhatsAppMessageMixin
from .whatsapp_machine_mixin import WhatsAppMachineMixin
from .whatsapp_intent_mixin import WhatsAppIntentMixin
from .whatsapp_flow_mixin import WhatsAppFlowMixin
from .whatsapp_toner_mixin import WhatsAppTonerMixin
from .whatsapp_onsite_mixin import WhatsAppOnsiteMixin
from .whatsapp_remote_mixin import WhatsAppRemoteMixin
from .whatsapp_endpoint_mixin import WhatsAppEndpointMixin
from .whatsapp_process_mixin import WhatsAppProcessMixin


_logger = logging.getLogger(__name__)


class WhatsAppPartnerApiController(
    WhatsAppPartnerMixin,
    WhatsAppContextMixin,
    WhatsAppMessageMixin,
    WhatsAppMachineMixin,
    WhatsAppIntentMixin,
    WhatsAppFlowMixin,
    WhatsAppTonerMixin,
    WhatsAppOnsiteMixin,
    WhatsAppRemoteMixin,
    WhatsAppEndpointMixin,
    WhatsAppProcessMixin,
    http.Controller,
):
    """
    API central WhatsApp para n8n / Baileys.

    Este archivo queda como controlador principal y orquestador.

    No debe contener lógica pesada de:
    - Identificación avanzada de contacto.
    - Registro DNI/RUC.
    - Horario/calendario/saludos.
    - Sesiones, mensajes, media, outbox.
    - Intenciones.
    - Flujos de tóner, servicio presencial o remoto.

    Esa lógica se divide en mixins dentro de controllers/.

    Archivos usados por este controlador:

    1) whatsapp_partner_mixin.py
       Maneja:
       - _only_digits
       - _clean_phone
       - _normalize_jid
       - _is_lid
       - _is_normal_whatsapp_jid
       - _phone_from_jid
       - _resolve_identifier_phone
       - _resolve_identifier_jid
       - _resolve_identifier_lid
       - _resolve_identifier_raw_jid
       - _extract_identifiers
       - _has_any_identifier
       - _get_latam_doc_type
       - _get_dni_type
       - _get_ruc_type
       - _run_partner_document_autoload
       - _prepare_partner_whatsapp_values
       - _find_partner_by_phone
       - _find_partner_by_identifiers
       - _update_partner_identifiers
       - _register_dni_inline
       - _register_ruc_inline
       - _company_selection_message
       - _continue_company_selection

    2) whatsapp_context_mixin.py
       Maneja:
       - _render_template
       - _get_status_template_name
       - _build_suggested_message
       - _get_greeting_message
       - _now_lima
       - _get_today_business_hours
       - _compute_business_status
       - _get_applies_to

    3) whatsapp_message_mixin.py
       Maneja:
       - _get_or_create_session
       - _create_media_from_payload
       - _record_whatsapp_message
       - _create_outbox
       - _emit_bot_reply
       - _safe_json_dict

    4) whatsapp_machine_mixin.py
       Maneja:
       - _get_base_url
       - _get_toner_url
       - _get_service_url
       - _field_exists
       - _get_machine_label
       - _record_matches_partner_company
       - _get_partner_machines
       - _build_machine_menu
       - _get_context_machine
       - _parse_menu_index
       - _is_yes
       - _is_no
       - _looks_like_dni
       - _looks_like_ruc
       - _looks_like_anydesk
       - _safe_model_create

    5) whatsapp_intent_mixin.py
       Maneja:
       - _detect_intent
       - _execute_intent_action
       - _build_main_menu_text

    6) whatsapp_flow_mixin.py
       Maneja:
       - _continue_active_flow

    7) whatsapp_toner_mixin.py
       Maneja:
       - _start_toner_flow
       - _continue_toner_flow
       - helpers internos de tóner

    8) whatsapp_onsite_mixin.py
       Maneja:
       - _start_onsite_flow
       - _continue_onsite_flow
       - _create_service_ticket

    9) whatsapp_remote_mixin.py
       Maneja:
       - _start_remote_flow
       - _continue_remote_flow

    10) whatsapp_endpoint_mixin.py
        Maneja endpoints auxiliares existentes:
        - /sat/whatsapp/profile
        - /sat/whatsapp/intent
        - /sat/whatsapp/template/render
        - /sat/whatsapp/message/out
        - /sat/whatsapp/outbox/pending
        - /sat/whatsapp/human/take
        - /sat/whatsapp/human/release

    11) whatsapp_process_mixin.py
        Maneja:
        - _process_whatsapp_conversation

        Esta función contiene el cuerpo interno del proceso central
        de /sat/whatsapp/process.
    """

    # ==========================================================
    # Helpers base del controlador principal
    # ==========================================================
    def _get_json_payload(self):
        try:
            if hasattr(request, "get_json_data"):
                return request.get_json_data() or {}
        except Exception:
            pass

        try:
            return request.jsonrequest or {}
        except Exception:
            return {}

    def _json_error(self, message, code="ERROR", status=200, extra=None):
        data = {
            "ok": False,
            "code": code,
            "status": status,
            "message": message,
        }
        if extra:
            data.update(extra)
        return data

    def _check_token(self):
        token = request.env["ir.config_parameter"].sudo().get_param(
            "sat.whatsapp_api_token"
        )

        if not token:
            _logger.warning(
                "[SAT-WHATSAPP-API] Falta configurar ir.config_parameter: sat.whatsapp_api_token"
            )
            return False

        auth_header = request.httprequest.headers.get("Authorization", "")
        expected = "Bearer %s" % token

        if auth_header != expected:
            _logger.warning("[SAT-WHATSAPP-API] Token inválido o ausente")
            return False

        return True

    def _safe_log_api(
        self,
        endpoint,
        payload,
        response,
        identifiers=None,
        partner=False,
        session=False,
        start_ts=False,
        status="success",
        error_code=False,
        error_message=False,
        source="api",
    ):
        try:
            identifiers = identifiers or {}
            duration_ms = 0
            if start_ts:
                duration_ms = int((time.time() - start_ts) * 1000)

            if "whatsapp.api.log" not in request.env:
                return

            try:
                safe_payload = json.loads(json.dumps(payload or {}, default=str))
            except Exception:
                safe_payload = {}

            try:
                safe_response = json.loads(json.dumps(response or {}, default=str))
            except Exception:
                safe_response = {}

            request.env["whatsapp.api.log"].sudo().create({
                "name": endpoint,
                "endpoint": endpoint,
                "method": request.httprequest.method,
                "phone": identifiers.get("phone") or False,
                "jid": identifiers.get("jid") or False,
                "lid": identifiers.get("lid") or False,
                "raw_jid": identifiers.get("raw_jid") or False,
                "partner_id": partner.id if partner else False,
                "session_id": session.id if session else False,
                "request_payload": safe_payload,
                "response_payload": safe_response,
                "status": status,
                "error_code": error_code or False,
                "error_message": error_message or False,
                "duration_ms": duration_ms,
                "source": source or "api",
            })
        except Exception:
            _logger.exception("[SAT-WHATSAPP-API] No se pudo guardar whatsapp.api.log")

    # ==========================================================
    # Endpoint central: procesar conversación completa
    # ==========================================================
    @http.route("/sat/whatsapp/process", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_process(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/process"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        _logger.info(
            "[WA-PROCESS] INICIO | endpoint=%s phone=%s jid=%s lid=%s raw_jid=%s message=%s ai_provider=%s ai_intent=%s ai_confidence=%s",
            endpoint,
            identifiers.get("phone") or False,
            identifiers.get("jid") or False,
            identifiers.get("lid") or False,
            identifiers.get("raw_jid") or False,
            (payload.get("message") or payload.get("text") or payload.get("content") or "")[:300],
            payload.get("ai_provider") or False,
            payload.get("ai_intent") or False,
            payload.get("ai_confidence") or 0,
        )

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)

            _logger.warning(
                "[WA-PROCESS] Token inválido | phone=%s jid=%s lid=%s raw_jid=%s",
                identifiers.get("phone") or False,
                identifiers.get("jid") or False,
                identifiers.get("lid") or False,
                identifiers.get("raw_jid") or False,
            )

            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="unauthorized",
                start_ts=start_ts,
            )
            return response

        if not self._has_any_identifier(identifiers):
            response = self._json_error(
                "Número, JID o LID requerido",
                "IDENTIFIER_REQUIRED",
                400,
            )

            _logger.warning(
                "[WA-PROCESS] Sin identificador válido | identifiers=%s payload_keys=%s",
                identifiers,
                list((payload or {}).keys()),
            )

            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="error",
                error_code="IDENTIFIER_REQUIRED",
                start_ts=start_ts,
            )
            return response

        try:
            return self._process_whatsapp_conversation(
                endpoint=endpoint,
                payload=payload,
                identifiers=identifiers,
                start_ts=start_ts,
            )
        except Exception as e:
            _logger.exception("[WA-PROCESS] Error general procesando conversación")

            response = self._json_error(
                "Error interno procesando WhatsApp.",
                "PROCESS_ERROR",
                500,
                extra={
                    "error": str(e),
                },
            )

            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="error",
                error_code="PROCESS_ERROR",
                error_message=str(e),
                start_ts=start_ts,
            )
            return response