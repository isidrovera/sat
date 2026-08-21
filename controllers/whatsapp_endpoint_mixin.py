# -*- coding: utf-8 -*-

import logging
import time

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppEndpointMixin:
    """
    Endpoints públicos utilizados por n8n / Baileys.

    Este mixin conserva las rutas y contratos JSON existentes y delega
    la lógica funcional a los modelos/mixins correspondientes.

    En particular:
    - outbox/pending delega en whatsapp.outbox.get_pending_payload();
    - los ACK delegan en métodos idempotentes del modelo outbox;
    - human/take y human/release mantienen sincronizados partner,
      sesión y handoffs;
    - los identificadores numéricos recibidos desde API se validan antes
      de realizar browse() para evitar errores 500 por payload inválido.
    """

    def _endpoint_positive_int(
        self,
        value,
        default=False,
        minimum=1,
        maximum=False,
    ):
        try:
            parsed = int(value)
        except Exception:
            return default

        if parsed < minimum:
            return default

        if maximum and parsed > maximum:
            return maximum

        return parsed

    def _endpoint_bool(
        self,
        value,
        default=False,
    ):
        if value is None:
            return bool(default)

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return bool(value)

        text = str(value).strip().lower()

        if text in (
            "1",
            "true",
            "yes",
            "si",
            "sí",
            "on",
        ):
            return True

        if text in (
            "0",
            "false",
            "no",
            "off",
            "",
        ):
            return False

        return bool(default)

    # ==========================================================
    # Endpoint: perfil
    # ==========================================================
    @http.route("/sat/whatsapp/profile", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_profile(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/profile"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
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

        partner = self._find_partner_by_identifiers(identifiers)
        business_status = self._compute_business_status()

        if not partner:
            suggested = self._build_suggested_message(
                partner=False,
                session=False,
                business_status=business_status,
            )

            response = {
                "ok": True,
                "found": False,
                "phone": identifiers.get("phone"),
                "jid": identifiers.get("jid"),
                "lid": identifiers.get("lid"),
                "raw_jid": identifiers.get("raw_jid"),
                "business": business_status,
                "suggested": suggested,
                "profile": None,
                "message": "Contacto no encontrado",
            }

            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="not_found",
                start_ts=start_ts,
            )
            return response

        self._update_partner_identifiers(partner, identifiers)

        intent = payload.get("intent") or False
        force_new_session = bool(payload.get("force_new_session"))

        session = self._get_or_create_session(
            partner,
            identifiers,
            intent=intent,
            force_new_session=force_new_session,
        )

        suggested = self._build_suggested_message(
            partner=partner,
            session=session,
            business_status=business_status,
        )

        response = {
            "ok": True,
            "found": True,
            "partner_id": partner.id,
            "session_id": session.id if session else False,
            "business": business_status,
            "suggested": suggested,
            "profile": partner.get_whatsapp_profile_payload(),
        }

        self._safe_log_api(
            endpoint,
            payload,
            response,
            identifiers,
            partner=partner,
            session=session if session else False,
            start_ts=start_ts,
        )
        return response

    # ==========================================================
    # Endpoint: intención
    # ==========================================================
    @http.route("/sat/whatsapp/intent", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_intent(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/intent"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="unauthorized",
                start_ts=start_ts,
            )
            return response

        message_text = payload.get("message") or payload.get("text") or ""

        partner = (
            self._find_partner_by_identifiers(identifiers)
            if self._has_any_identifier(identifiers)
            else request.env["res.partner"].sudo()
        )

        business_status = self._compute_business_status()

        session = False
        if partner:
            session = self._get_or_create_session(partner, identifiers)

        result, applies_to = self._detect_intent(
            message_text,
            partner=partner if partner else False,
            business_status=business_status,
            session=session if session else False,
            payload=payload,
        )

        response = {
            "ok": True,
            "found": bool(result.get("found")),
            "applies_to": applies_to,
            "business": business_status,
            "intent": result,
        }

        self._safe_log_api(
            endpoint,
            payload,
            response,
            identifiers,
            partner=partner if partner else False,
            session=session if session else False,
            start_ts=start_ts,
        )
        return response

    # ==========================================================
    # Endpoint: render plantilla
    # ==========================================================
    @http.route("/sat/whatsapp/template/render", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_template_render(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/template/render"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="unauthorized",
                start_ts=start_ts,
            )
            return response

        template_name = (
            payload.get("template")
            or payload.get("template_name")
            or payload.get("name")
        )

        if not template_name:
            response = self._json_error(
                "Nombre de plantilla requerido.",
                "TEMPLATE_REQUIRED",
                400,
            )
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="error",
                error_code="TEMPLATE_REQUIRED",
                start_ts=start_ts,
            )
            return response

        partner = False
        session = False
        company = False

        if self._has_any_identifier(identifiers):
            partner = self._find_partner_by_identifiers(identifiers)

            if partner:
                session = self._get_or_create_session(partner, identifiers)
                company = (
                    partner.whatsapp_active_company_id
                    if partner.whatsapp_active_company_id
                    else False
                )

        text = self._render_template(
            template_name,
            partner=partner if partner else False,
            session=session if session else False,
            company=company if company else False,
            extra=payload.get("extra") or {},
            fallback=False,
        )

        response = {
            "ok": True,
            "found": bool(text),
            "template": template_name,
            "message": text,
            "partner_id": partner.id if partner else False,
            "session_id": session.id if session else False,
        }

        self._safe_log_api(
            endpoint,
            payload,
            response,
            identifiers,
            partner=partner if partner else False,
            session=session if session else False,
            start_ts=start_ts,
        )
        return response

    # ==========================================================
    # Endpoint: mensaje saliente / outbox
    # ==========================================================
    @http.route("/sat/whatsapp/message/out", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_message_out(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/message/out"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="unauthorized",
                start_ts=start_ts,
            )
            return response

        content = (
            payload.get("message")
            or payload.get("text")
            or payload.get("content")
            or ""
        )

        message_type = payload.get("message_type") or "text"
        template_name = payload.get("template") or payload.get("template_name")

        if not self._has_any_identifier(identifiers):
            response = self._json_error(
                "Número, JID o LID requerido",
                "IDENTIFIER_REQUIRED",
                400,
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

        partner = self._find_partner_by_identifiers(identifiers)

        if not partner:
            response = self._json_error(
                "Contacto no encontrado.",
                "CONTACT_NOT_FOUND",
                404,
            )
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="not_found",
                start_ts=start_ts,
            )
            return response

        session = self._get_or_create_session(partner, identifiers)

        if template_name and not content:
            content = self._render_template(
                template_name,
                partner=partner,
                session=session,
                company=partner.whatsapp_active_company_id if partner.whatsapp_active_company_id else False,
                extra=payload.get("extra") or {},
                fallback="",
            )

        emitted = self._emit_bot_reply(
            session=session,
            partner=partner,
            identifiers=identifiers,
            content=content,
            intent=payload.get("intent") or False,
            payload=payload,
            template=template_name or False,
            message_type=message_type,
            create_outbox=True,
        )

        response = {
            "ok": True,
            "partner_id": partner.id,
            "session_id": session.id,
            "message_id": emitted.get("message_id"),
            "outbox_id": emitted.get("outbox_id"),
            "state": "pending",
            "message": content,
        }

        self._safe_log_api(
            endpoint,
            payload,
            response,
            identifiers,
            partner=partner,
            session=session,
            start_ts=start_ts,
        )
        return response

    # ==========================================================
    # Endpoint: outbox pendientes
    # ==========================================================
    @http.route(
        "/sat/whatsapp/outbox/pending",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_outbox_pending(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/outbox/pending"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error(
                "No autorizado",
                "UNAUTHORIZED",
                401,
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

        limit = self._endpoint_positive_int(
            payload.get("limit"),
            default=20,
            minimum=1,
            maximum=100,
        )

        partner_id = self._endpoint_positive_int(
            payload.get("partner_id"),
            default=False,
            minimum=1,
        )

        Outbox = request.env["whatsapp.outbox"].sudo()

        items = Outbox.get_pending_payload(
            limit=limit,
            partner_id=partner_id,
        )

        response = {
            "ok": True,
            "count": len(items),
            "items": items,
        }

        _logger.info(
            "[WA-ENDPOINT] Outbox pendientes entregados | "
            "count=%s limit=%s partner_id=%s",
            len(items),
            limit,
            partner_id or False,
        )

        self._safe_log_api(
            endpoint,
            payload,
            response,
            identifiers,
            start_ts=start_ts,
        )
        return response

    # ==========================================================
    # Endpoint: tomar humano
    # ==========================================================
    @http.route(
        "/sat/whatsapp/human/take",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_human_take(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/human/take"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error(
                "No autorizado",
                "UNAUTHORIZED",
                401,
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

        taken_by_name = (
            payload.get("taken_by_name")
            or payload.get("agent_name")
            or "API / n8n"
        )
        reason = (
            payload.get("reason")
            or "Tomado por asesor desde API."
        )

        if not self._has_any_identifier(identifiers):
            response = self._json_error(
                "Número, JID o LID requerido",
                "IDENTIFIER_REQUIRED",
                400,
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

        partner = self._find_partner_by_identifiers(
            identifiers
        )

        if not partner:
            response = {
                "ok": True,
                "found": False,
                "message": (
                    "Contacto no encontrado. "
                    "No se activó modo humano."
                ),
            }
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="not_found",
                start_ts=start_ts,
            )
            return response

        self._update_partner_identifiers(
            partner,
            identifiers,
        )

        session = self._get_or_create_session(
            partner,
            identifiers,
        )

        Handoff = request.env[
            "whatsapp.handoff"
        ].sudo()

        handoff = Handoff.search([
            ("partner_id", "=", partner.id),
            ("session_id", "=", session.id),
            ("state", "in", [
                "pending",
                "assigned",
                "open",
                "escalated",
            ]),
        ], order="taken_at desc, id desc", limit=1)

        # Si ya existe una derivación para esta conversación, reutilizarla
        # evita crear handoffs duplicados por llamadas repetidas de n8n.
        if handoff:
            handoff.write({
                "state": "open",
                "taken_by_name": taken_by_name,
                "reason": reason or handoff.reason,
            })

            try:
                handoff._activate_human_context()
            except Exception:
                _logger.exception(
                    "[WA-HUMAN] No se pudo sincronizar handoff existente | "
                    "handoff_id=%s",
                    handoff.id,
                )
        else:
            handoff = Handoff.create({
                "session_id": session.id,
                "partner_id": partner.id,
                "company_id": (
                    partner.whatsapp_active_company_id.id
                    if partner.whatsapp_active_company_id
                    else False
                ),
                "state": "open",
                "taken_by_name": taken_by_name,
                "reason": reason,
                "handoff_type": "manual",
            })

            try:
                handoff._activate_human_context()
            except Exception:
                _logger.exception(
                    "[WA-HUMAN] No se pudo sincronizar nuevo handoff | "
                    "handoff_id=%s",
                    handoff.id,
                )

        # Compatibilidad defensiva si se despliega endpoint antes que
        # whatsapp_handoff_PROFESIONAL.py.
        if not partner.whatsapp_human_mode:
            partner.whatsapp_enable_human_mode_api(
                taken_by_name=taken_by_name
            )

        if session.state != "human":
            session.action_set_human()

        suggested = {
            "template": "human_take",
            "message": self._render_template(
                "human_take",
                partner=partner,
                session=session,
                fallback=(
                    "👨‍💼 Un integrante de nuestro equipo "
                    "continuará con la atención por este chat."
                ),
            ),
        }

        response = {
            "ok": True,
            "found": True,
            "partner_id": partner.id,
            "session_id": session.id,
            "handoff_id": (
                handoff.id
                if handoff
                else False
            ),
            "suggested": suggested,
            "profile": (
                partner.get_whatsapp_profile_payload()
            ),
        }

        _logger.info(
            "[WA-HUMAN] Atención tomada por API | "
            "partner_id=%s session_id=%s handoff_id=%s agent=%s",
            partner.id,
            session.id,
            handoff.id if handoff else False,
            taken_by_name,
        )

        self._safe_log_api(
            endpoint,
            payload,
            response,
            identifiers,
            partner=partner,
            session=session,
            start_ts=start_ts,
        )
        return response

    # ==========================================================
    # Endpoint: liberar humano
    # ==========================================================
    @http.route(
        "/sat/whatsapp/human/release",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_human_release(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/human/release"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error(
                "No autorizado",
                "UNAUTHORIZED",
                401,
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

        released_by_name = (
            payload.get("released_by_name")
            or payload.get("agent_name")
            or "API / n8n"
        )

        if not self._has_any_identifier(identifiers):
            response = self._json_error(
                "Número, JID o LID requerido",
                "IDENTIFIER_REQUIRED",
                400,
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

        partner = self._find_partner_by_identifiers(
            identifiers
        )

        if not partner:
            response = {
                "ok": True,
                "found": False,
                "message": (
                    "Contacto no encontrado. "
                    "No se liberó modo humano."
                ),
            }
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="not_found",
                start_ts=start_ts,
            )
            return response

        self._update_partner_identifiers(
            partner,
            identifiers,
        )

        session = self._get_or_create_session(
            partner,
            identifiers,
        )

        Handoff = request.env[
            "whatsapp.handoff"
        ].sudo()

        handoffs = Handoff.search([
            ("partner_id", "=", partner.id),
            ("session_id", "=", session.id),
            ("state", "in", [
                "pending",
                "assigned",
                "open",
                "escalated",
            ]),
        ], order="taken_at desc, id desc")

        handoff_ids = handoffs.ids

        # Al liberar la conversación desde API, cerramos todas las
        # derivaciones activas de esa sesión. Si se cerrara solo la última,
        # otra derivación activa podría mantener el partner en modo humano.
        for handoff in handoffs:
            try:
                handoff.action_release()

                if (
                    released_by_name
                    and handoff.released_by_name
                    != released_by_name
                ):
                    handoff.write({
                        "released_by_name": (
                            released_by_name
                        ),
                    })

            except Exception:
                _logger.exception(
                    "[WA-HUMAN] No se pudo liberar handoff | "
                    "handoff_id=%s",
                    handoff.id,
                )

        # Compatibilidad si no existía handoff o si se despliega este
        # endpoint antes que la versión profesional del modelo.
        if partner.whatsapp_human_mode:
            partner.whatsapp_release_human_mode_api()

        if session.state == "human":
            session.action_reopen()

        suggested = {
            "template": "human_release",
            "message": self._render_template(
                "human_release",
                partner=partner,
                session=session,
                fallback=(
                    "✅ La atención humana finalizó. "
                    "El asistente virtual puede continuar."
                ),
            ),
        }

        response = {
            "ok": True,
            "found": True,
            "partner_id": partner.id,
            "session_id": session.id,
            "handoff_id": (
                handoff_ids[0]
                if handoff_ids
                else False
            ),
            "handoff_ids": handoff_ids,
            "released_count": len(handoff_ids),
            "suggested": suggested,
            "profile": (
                partner.get_whatsapp_profile_payload()
            ),
        }

        _logger.info(
            "[WA-HUMAN] Atención liberada por API | "
            "partner_id=%s session_id=%s handoffs=%s agent=%s",
            partner.id,
            session.id,
            handoff_ids,
            released_by_name,
        )

        self._safe_log_api(
            endpoint,
            payload,
            response,
            identifiers,
            partner=partner,
            session=session,
            start_ts=start_ts,
        )
        return response



    # ==========================================================
    # Endpoint: marcar outbox enviado
    # ==========================================================
    @http.route(
        "/sat/whatsapp/outbox/mark-sent",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_outbox_mark_sent(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/outbox/mark-sent"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error(
                "No autorizado",
                "UNAUTHORIZED",
                401,
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

        outbox_id = self._endpoint_positive_int(
            payload.get("outbox_id"),
            default=False,
        )

        external_message_id = (
            payload.get("external_message_id")
            or payload.get("message_id")
            or False
        )

        if not outbox_id:
            response = self._json_error(
                "outbox_id requerido o inválido",
                "OUTBOX_ID_REQUIRED",
                400,
            )
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="error",
                error_code="OUTBOX_ID_REQUIRED",
                start_ts=start_ts,
            )
            return response

        outbox = (
            request.env["whatsapp.outbox"]
            .sudo()
            .browse(outbox_id)
            .exists()
        )

        if not outbox:
            response = self._json_error(
                "Outbox no encontrado",
                "OUTBOX_NOT_FOUND",
                404,
            )
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="not_found",
                error_code="OUTBOX_NOT_FOUND",
                start_ts=start_ts,
            )
            return response

        previous_state = outbox.state

        outbox.action_mark_sent(
            external_message_id=(
                external_message_id
            )
        )

        response = {
            "ok": True,
            "outbox_id": outbox.id,
            "previous_state": previous_state,
            "state": outbox.state,
            "external_message_id": (
                outbox.external_message_id
            ),
            "idempotent": (
                previous_state
                in (
                    "sent",
                    "delivered",
                    "read",
                )
            ),
        }

        _logger.info(
            "[WA-ENDPOINT] ACK sent | "
            "outbox_id=%s previous=%s current=%s external_id=%s",
            outbox.id,
            previous_state,
            outbox.state,
            outbox.external_message_id or False,
        )

        self._safe_log_api(
            endpoint,
            payload,
            response,
            identifiers,
            partner=outbox.partner_id,
            session=outbox.session_id,
            start_ts=start_ts,
        )
        return response

    # ==========================================================
    # Endpoint: marcar outbox fallido
    # ==========================================================
    @http.route(
        "/sat/whatsapp/outbox/mark-failed",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_outbox_mark_failed(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/outbox/mark-failed"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error(
                "No autorizado",
                "UNAUTHORIZED",
                401,
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

        outbox_id = self._endpoint_positive_int(
            payload.get("outbox_id"),
            default=False,
        )

        if not outbox_id:
            response = self._json_error(
                "outbox_id requerido o inválido",
                "OUTBOX_ID_REQUIRED",
                400,
            )
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="error",
                error_code="OUTBOX_ID_REQUIRED",
                start_ts=start_ts,
            )
            return response

        outbox = (
            request.env["whatsapp.outbox"]
            .sudo()
            .browse(outbox_id)
            .exists()
        )

        if not outbox:
            response = self._json_error(
                "Outbox no encontrado",
                "OUTBOX_NOT_FOUND",
                404,
            )
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="not_found",
                error_code="OUTBOX_NOT_FOUND",
                start_ts=start_ts,
            )
            return response

        previous_state = outbox.state

        schedule_retry = self._endpoint_bool(
            payload.get("schedule_retry"),
            default=True,
        )

        outbox.action_mark_failed(
            error_message=(
                payload.get("error_message")
                or "Error reportado por n8n/Baileys"
            ),
            error_code=(
                payload.get("error_code")
                or False
            ),
            schedule_retry=schedule_retry,
        )

        response = {
            "ok": True,
            "outbox_id": outbox.id,
            "previous_state": previous_state,
            "state": outbox.state,
            "retry_count": outbox.retry_count,
            "max_retries": outbox.max_retries,
            "next_retry_at": outbox.next_retry_at,
            "schedule_retry": schedule_retry,
            "ignored_terminal_state": (
                previous_state
                in (
                    "sent",
                    "delivered",
                    "read",
                    "cancelled",
                )
            ),
        }

        _logger.info(
            "[WA-ENDPOINT] ACK failed | "
            "outbox_id=%s previous=%s current=%s retry=%s/%s "
            "schedule_retry=%s error_code=%s",
            outbox.id,
            previous_state,
            outbox.state,
            outbox.retry_count,
            outbox.max_retries,
            schedule_retry,
            payload.get("error_code") or False,
        )

        self._safe_log_api(
            endpoint,
            payload,
            response,
            identifiers,
            partner=outbox.partner_id,
            session=outbox.session_id,
            start_ts=start_ts,
        )
        return response
