# -*- coding: utf-8 -*-

import logging
import time

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppEndpointMixin:
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
    @http.route("/sat/whatsapp/outbox/pending", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_outbox_pending(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/outbox/pending"
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

        limit = payload.get("limit") or 20
        partner_id = payload.get("partner_id") or False

        try:
            limit = int(limit)
        except Exception:
            limit = 20

        if limit > 100:
            limit = 100

        items = request.env["whatsapp.outbox"].sudo().get_pending_payload(
            limit=limit,
            partner_id=partner_id,
        )

        response = {
            "ok": True,
            "count": len(items),
            "items": items,
        }

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
    @http.route("/sat/whatsapp/human/take", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_human_take(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/human/take"
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

        taken_by_name = payload.get("taken_by_name") or payload.get("agent_name") or "API / n8n"
        reason = payload.get("reason") or "Tomado por asesor desde API."

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
            response = {
                "ok": True,
                "found": False,
                "message": "Contacto no encontrado. No se activó modo humano.",
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

        session = self._get_or_create_session(partner, identifiers)

        partner.whatsapp_enable_human_mode_api(taken_by_name=taken_by_name)
        session.action_set_human()

        request.env["whatsapp.handoff"].sudo().create({
            "session_id": session.id,
            "partner_id": partner.id,
            "company_id": partner.whatsapp_active_company_id.id if partner.whatsapp_active_company_id else False,
            "state": "open",
            "taken_by_name": taken_by_name,
            "reason": reason,
        })

        suggested = {
            "template": "human_take",
            "message": self._render_template(
                "human_take",
                partner=partner,
                session=session,
                fallback="Un asesor continuará con la atención.",
            ),
        }

        response = {
            "ok": True,
            "found": True,
            "partner_id": partner.id,
            "session_id": session.id,
            "suggested": suggested,
            "profile": partner.get_whatsapp_profile_payload(),
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
    # Endpoint: liberar humano
    # ==========================================================
    @http.route("/sat/whatsapp/human/release", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_human_release(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/human/release"
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

        released_by_name = payload.get("released_by_name") or payload.get("agent_name") or "API / n8n"

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
            response = {
                "ok": True,
                "found": False,
                "message": "Contacto no encontrado. No se liberó modo humano.",
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

        session = self._get_or_create_session(partner, identifiers)

        partner.whatsapp_release_human_mode_api()
        session.action_reopen()

        handoff = request.env["whatsapp.handoff"].sudo().search([
            ("partner_id", "=", partner.id),
            ("session_id", "=", session.id),
            ("state", "in", ["pending", "assigned", "open", "escalated"]),
        ], order="taken_at desc, id desc", limit=1)

        if handoff:
            try:
                handoff.write({
                    "state": "released",
                    "released_by_name": released_by_name,
                })
                handoff.action_release()
            except Exception:
                _logger.exception(
                    "[WA-HUMAN] No se pudo liberar handoff id=%s",
                    handoff.id if handoff else False,
                )

        suggested = {
            "template": "human_release",
            "message": self._render_template(
                "human_release",
                partner=partner,
                session=session,
                fallback="El modo humano fue desactivado. El asistente virtual puede continuar.",
            ),
        }

        response = {
            "ok": True,
            "found": True,
            "partner_id": partner.id,
            "session_id": session.id,
            "handoff_id": handoff.id if handoff else False,
            "suggested": suggested,
            "profile": partner.get_whatsapp_profile_payload(),
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
    # Endpoint: marcar outbox enviado
    # ==========================================================
    @http.route("/sat/whatsapp/outbox/mark-sent", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_outbox_mark_sent(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/outbox/mark-sent"
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

        outbox_id = payload.get("outbox_id")
        external_message_id = (
            payload.get("external_message_id")
            or payload.get("message_id")
            or False
        )

        if not outbox_id:
            response = self._json_error(
                "outbox_id requerido",
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

        outbox = request.env["whatsapp.outbox"].sudo().browse(int(outbox_id)).exists()

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

        outbox.action_mark_sent(external_message_id=external_message_id)

        response = {
            "ok": True,
            "outbox_id": outbox.id,
            "state": outbox.state,
            "external_message_id": outbox.external_message_id,
        }

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
    @http.route("/sat/whatsapp/outbox/mark-failed", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_outbox_mark_failed(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/outbox/mark-failed"
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

        outbox_id = payload.get("outbox_id")

        if not outbox_id:
            response = self._json_error(
                "outbox_id requerido",
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

        outbox = request.env["whatsapp.outbox"].sudo().browse(int(outbox_id)).exists()

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

        outbox.action_mark_failed(
            error_message=payload.get("error_message") or "Error reportado por n8n/Baileys",
            error_code=payload.get("error_code") or False,
            schedule_retry=payload.get("schedule_retry", True),
        )

        response = {
            "ok": True,
            "outbox_id": outbox.id,
            "state": outbox.state,
            "retry_count": outbox.retry_count,
            "next_retry_at": outbox.next_retry_at,
        }

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