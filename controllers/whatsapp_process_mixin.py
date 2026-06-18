# -*- coding: utf-8 -*-

import logging

from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppProcessMixin:
    """
    Mixin principal del proceso conversacional WhatsApp.

    Este archivo NO define rutas HTTP.

    La ruta /sat/whatsapp/process queda en:
        controllers/whatsapp_api_controller.py

    Este mixin se encarga de ejecutar el flujo interno:
    - Buscar contacto por teléfono/JID/LID.
    - Actualizar identificadores.
    - Evaluar horario/calendario.
    - Crear/actualizar sesión.
    - Registrar mensaje entrante.
    - Validar bloqueado / humano / registro / empresa.
    - Continuar flujo activo.
    - Detectar intención.
    - Ejecutar acción.
    - Emitir respuesta y outbox.
    """

    def _process_whatsapp_conversation(self, endpoint, payload, identifiers, start_ts=False):
        payload = payload or {}
        identifiers = identifiers or {}

        message_text = (
            payload.get("message")
            or payload.get("text")
            or payload.get("content")
            or payload.get("body")
            or ""
        )
        message_text = str(message_text or "").strip()

        message_type = payload.get("message_type") or "text"
        external_message_id = (
            payload.get("external_message_id")
            or payload.get("message_id")
            or payload.get("id")
            or False
        )

        _logger.info(
            "[WA-PROCESS] Procesando conversación | phone=%s jid=%s lid=%s raw_jid=%s message=%s",
            identifiers.get("phone") or False,
            identifiers.get("jid") or False,
            identifiers.get("lid") or False,
            identifiers.get("raw_jid") or False,
            message_text[:300] if message_text else "",
        )

        # ======================================================
        # 1) Buscar contacto
        # ======================================================
        partner = self._find_partner_by_identifiers(identifiers)

        _logger.info(
            "[WA-PROCESS] Partner resuelto | partner_id=%s name=%s",
            partner.id if partner else False,
            partner.name if partner else False,
        )

        # ======================================================
        # 2) Si no existe partner y el mensaje parece DNI, registrar DNI
        # ======================================================
        if not partner and self._looks_like_dni(message_text):
            _logger.info(
                "[WA-PROCESS] Partner no existe y mensaje parece DNI | dni=%s",
                message_text,
            )

            partner, session, reply = self._register_dni_inline(
                identifiers,
                self._only_digits(message_text),
                payload=payload,
            )

            business_status = self._compute_business_status()

            emitted = self._emit_bot_reply(
                session=session,
                partner=partner,
                identifiers=identifiers,
                content=reply,
                intent="dni",
                payload=payload,
            )

            response = {
                "ok": True,
                "found": True,
                "registered_dni": True,
                "next_step": "waiting_ruc",
                "partner_id": partner.id if partner else False,
                "session_id": session.id if session else False,
                "message": reply,
                "outbox_id": emitted.get("outbox_id"),
                "business": business_status,
                "profile": partner.get_whatsapp_profile_payload() if partner else False,
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

        # ======================================================
        # 3) Si no existe partner, pedir DNI
        # ======================================================
        if not partner:
            business_status = self._compute_business_status()

            reply = self._render_template(
                "ask_dni",
                partner=False,
                session=False,
                fallback="Para poder ayudarte, por favor envíame tu DNI de 8 dígitos.",
            )

            response = {
                "ok": True,
                "found": False,
                "next_step": "waiting_dni",
                "message": reply,
                "business": business_status,
                "profile": False,
            }

            _logger.info(
                "[WA-PROCESS] Partner no encontrado. Se solicita DNI | phone=%s jid=%s lid=%s",
                identifiers.get("phone") or False,
                identifiers.get("jid") or False,
                identifiers.get("lid") or False,
            )

            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                partner=False,
                session=False,
                start_ts=start_ts,
            )
            return response

        # ======================================================
        # 4) Actualizar identificadores y contexto base
        # ======================================================
        self._update_partner_identifiers(partner, identifiers)

        business_status = self._compute_business_status()

        session = self._get_or_create_session(
            partner,
            identifiers,
        )

        incoming_message = self._record_whatsapp_message(
            session=session,
            partner=partner,
            identifiers=identifiers,
            role="user",
            direction="in",
            message_type=message_type,
            content=message_text,
            intent=False,
            payload=payload,
            external_message_id=external_message_id,
        )

        _logger.info(
            "[WA-PROCESS] Mensaje entrante registrado | message_id=%s partner_id=%s session_id=%s business_reason=%s business_open=%s",
            incoming_message.id if incoming_message else False,
            partner.id if partner else False,
            session.id if session else False,
            business_status.get("reason") if business_status else False,
            business_status.get("is_open") if business_status else False,
        )

        # ======================================================
        # 5) Contacto bloqueado
        # ======================================================
        if partner.whatsapp_blocked or partner.whatsapp_access_level == "blocked":
            reply = self._render_template(
                "blocked_contact",
                partner=partner,
                session=session,
                fallback="Tu número no está habilitado para atención por este canal.",
            )

            emitted = self._emit_bot_reply(
                session=session,
                partner=partner,
                identifiers=identifiers,
                content=reply,
                intent="blocked",
                payload=payload,
            )

            response = {
                "ok": True,
                "found": True,
                "blocked": True,
                "partner_id": partner.id,
                "session_id": session.id,
                "message": reply,
                "outbox_id": emitted.get("outbox_id"),
                "business": business_status,
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

        # ======================================================
        # 6) Modo humano activo
        # ======================================================
        if partner.whatsapp_human_mode:
            _logger.info(
                "[WA-PROCESS] Partner en modo humano. Bot no responde | partner_id=%s session_id=%s",
                partner.id,
                session.id,
            )

            response = {
                "ok": True,
                "found": True,
                "human_mode": True,
                "bot_reply": False,
                "partner_id": partner.id,
                "session_id": session.id,
                "message": False,
                "outbox_id": False,
                "business": business_status,
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

        # ======================================================
        # 7) Registro DNI/RUC pendiente
        # ======================================================
        registration_state = getattr(partner, "whatsapp_registration_state", "none")

        if registration_state in ("none", "waiting_dni"):
            if self._looks_like_dni(message_text):
                partner, session, reply = self._register_dni_inline(
                    identifiers,
                    self._only_digits(message_text),
                    payload=payload,
                )

                emitted = self._emit_bot_reply(
                    session=session,
                    partner=partner,
                    identifiers=identifiers,
                    content=reply,
                    intent="dni",
                    payload=payload,
                )

                response = {
                    "ok": True,
                    "found": True,
                    "registered_dni": True,
                    "next_step": "waiting_ruc",
                    "partner_id": partner.id,
                    "session_id": session.id,
                    "message": reply,
                    "outbox_id": emitted.get("outbox_id"),
                    "business": business_status,
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

            reply = self._render_template(
                "ask_dni",
                partner=partner,
                session=session,
                fallback="Para poder ayudarte, por favor envíame tu DNI de 8 dígitos.",
            )

            emitted = self._emit_bot_reply(
                session=session,
                partner=partner,
                identifiers=identifiers,
                content=reply,
                intent="ask_dni",
                payload=payload,
            )

            response = {
                "ok": True,
                "found": True,
                "next_step": "waiting_dni",
                "partner_id": partner.id,
                "session_id": session.id,
                "message": reply,
                "outbox_id": emitted.get("outbox_id"),
                "business": business_status,
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

        if registration_state == "waiting_ruc":
            if self._looks_like_ruc(message_text):
                company, session, reply, company_created = self._register_ruc_inline(
                    partner,
                    identifiers,
                    self._only_digits(message_text),
                    payload=payload,
                )

                emitted = self._emit_bot_reply(
                    session=session,
                    partner=partner,
                    identifiers=identifiers,
                    content=reply,
                    intent="ruc",
                    payload=payload,
                )

                response = {
                    "ok": True,
                    "found": True,
                    "registered_ruc": True,
                    "company_created": company_created,
                    "next_step": "registered",
                    "partner_id": partner.id,
                    "company_id": company.id if company else False,
                    "session_id": session.id,
                    "message": reply,
                    "outbox_id": emitted.get("outbox_id"),
                    "business": business_status,
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

            reply = self._render_template(
                "ask_ruc",
                partner=partner,
                session=session,
                fallback="Gracias. Ahora envíame el RUC de tu empresa para completar el registro.",
            )

            emitted = self._emit_bot_reply(
                session=session,
                partner=partner,
                identifiers=identifiers,
                content=reply,
                intent="ask_ruc",
                payload=payload,
            )

            response = {
                "ok": True,
                "found": True,
                "next_step": "waiting_ruc",
                "partner_id": partner.id,
                "session_id": session.id,
                "message": reply,
                "outbox_id": emitted.get("outbox_id"),
                "business": business_status,
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

        # ======================================================
        # 8) Selección de empresa pendiente
        # ======================================================
        if (
            session.current_flow == "registration"
            and session.conversation_state == "awaiting_company_selection"
        ):
            _logger.info(
                "[WA-PROCESS] Continuando selección de empresa | partner_id=%s session_id=%s message=%s",
                partner.id if partner else False,
                session.id if session else False,
                message_text[:300] if message_text else "",
            )

            reply = self._continue_company_selection(
                partner,
                session,
                message_text,
            )

            emitted = self._emit_bot_reply(
                session=session,
                partner=partner,
                identifiers=identifiers,
                content=reply,
                intent="company_selection",
                payload=payload,
            )

            response = {
                "ok": True,
                "found": True,
                "partner_id": partner.id,
                "session_id": session.id,
                "message": reply,
                "outbox_id": emitted.get("outbox_id"),
                "business": business_status,
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

        if partner.whatsapp_requires_company_selection:
            _logger.info(
                "[WA-PROCESS] Requiere selección de empresa | partner_id=%s session_id=%s",
                partner.id if partner else False,
                session.id if session else False,
            )

            reply = self._company_selection_message(
                partner,
                session=session,
            )

            emitted = self._emit_bot_reply(
                session=session,
                partner=partner,
                identifiers=identifiers,
                content=reply,
                intent="select_company",
                payload=payload,
            )

            response = {
                "ok": True,
                "found": True,
                "next_step": "select_company",
                "partner_id": partner.id,
                "session_id": session.id,
                "message": reply,
                "outbox_id": emitted.get("outbox_id"),
                "business": business_status,
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

        # ======================================================
        # 9) Horario/refrigerio: informa, pero permite registrar
        # ======================================================
        outside_hours_note = False

        if business_status and not business_status.get("is_open"):
            outside_hours_note = business_status.get("message") or ""

            _logger.info(
                "[WA-PROCESS] Fuera de horario/refrigerio | reason=%s message=%s",
                business_status.get("reason") or False,
                outside_hours_note[:300] if outside_hours_note else False,
            )

        # ======================================================
        # 10) Continuar flujo activo
        # ======================================================
        if session.current_flow != "none" and session.conversation_state != "idle":
            _logger.info(
                "[WA-PROCESS] Continuando flujo activo | partner_id=%s session_id=%s flow=%s step=%s message=%s",
                partner.id if partner else False,
                session.id if session else False,
                session.current_flow,
                session.conversation_state,
                message_text[:300] if message_text else "",
            )

            reply = self._continue_active_flow(
                partner,
                session,
                identifiers,
                message_text,
                payload=payload,
            )

            if outside_hours_note and reply:
                reply = "%s\n\n%s" % (outside_hours_note, reply)

            emitted = self._emit_bot_reply(
                session=session,
                partner=partner,
                identifiers=identifiers,
                content=reply,
                intent=session.current_flow,
                payload=payload,
            )

            response = {
                "ok": True,
                "found": True,
                "continued_flow": True,
                "flow": session.current_flow,
                "step": session.conversation_state,
                "partner_id": partner.id,
                "session_id": session.id,
                "message": reply,
                "outbox_id": emitted.get("outbox_id"),
                "business": business_status,
                "profile": partner.get_whatsapp_profile_payload(),
            }

            _logger.info(
                "[WA-PROCESS] Flujo activo respondido | partner_id=%s session_id=%s flow=%s step=%s outbox_id=%s",
                partner.id if partner else False,
                session.id if session else False,
                session.current_flow,
                session.conversation_state,
                emitted.get("outbox_id"),
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

        # ======================================================
        # 11) Detectar intención y ejecutar acción
        # ======================================================
        _logger.info(
            "[WA-PROCESS] Detectar intención | partner_id=%s session_id=%s message=%s ai_provider=%s ai_intent=%s ai_sub_intent=%s ai_confidence=%s ai_reason=%s",
            partner.id if partner else False,
            session.id if session else False,
            message_text[:300] if message_text else "",
            payload.get("ai_provider") or False,
            payload.get("ai_intent") or False,
            payload.get("ai_sub_intent") or False,
            payload.get("ai_confidence") or 0,
            payload.get("ai_reason") or False,
        )

        intent_result, applies_to = self._detect_intent(
            message_text,
            partner=partner if partner else False,
            business_status=business_status,
            session=session if session else False,
            payload=payload,
        )

        intent_result = intent_result or {"found": False}

        reply = self._execute_intent_action(
            partner,
            session,
            identifiers,
            message_text,
            intent_result,
            business_status,
            payload=payload,
        )

        if outside_hours_note and reply:
            reply = "%s\n\n%s" % (outside_hours_note, reply)

        if not reply:
            response = {
                "ok": True,
                "found": False,
                "ignored": True,
                "applies_to": applies_to,
                "intent": intent_result,
                "partner_id": partner.id,
                "session_id": session.id,
                "message": False,
                "outbox_id": False,
                "business": business_status,
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

        emitted = self._emit_bot_reply(
            session=session,
            partner=partner,
            identifiers=identifiers,
            content=reply,
            intent=intent_result.get("intent") or "unknown",
            payload=payload,
            template=intent_result.get("response_template") or False,
        )

        response = {
            "ok": True,
            "found": bool(intent_result.get("found")),
            "applies_to": applies_to,
            "intent": intent_result,
            "partner_id": partner.id,
            "session_id": session.id,
            "message": reply,
            "outbox_id": emitted.get("outbox_id"),
            "business": business_status,
            "profile": partner.get_whatsapp_profile_payload(),
        }

        _logger.info(
            "[WA-PROCESS] Respuesta final emitida | partner_id=%s session_id=%s intent=%s action=%s outbox_id=%s",
            partner.id if partner else False,
            session.id if session else False,
            intent_result.get("intent") or False,
            intent_result.get("action") or False,
            emitted.get("outbox_id"),
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