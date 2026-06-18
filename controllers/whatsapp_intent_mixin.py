# -*- coding: utf-8 -*-

import logging

from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppIntentMixin:
    # ==========================================================
    # Intención y acciones
    # ==========================================================
    def _detect_intent(self, message_text, partner=False, business_status=False, session=False, payload=False):
        """
        Detecta intención del mensaje.

        Orden de prioridad:
        1) Si n8n/Gemini envía ai_intent con confianza alta, usar esa intención.
        2) Si no hay ai_intent válido, usar whatsapp.intent.rule.
        3) Si ocurre error, devolver found=False.
        """
        payload = payload or {}
        business_status = business_status or {}

        applies_to = self._get_applies_to(
            partner,
            business_status=business_status,
        ) if partner else "new"

        text_debug = (message_text or "").strip()

        _logger.info(
            "[WA-INTENT] INICIO detectar intención | partner_id=%s session_id=%s applies_to=%s flow=%s text=%s",
            partner.id if partner else False,
            session.id if session else False,
            applies_to,
            session.current_flow if session else False,
            text_debug[:300],
        )

        ai_provider = (payload.get("ai_provider") or "").strip()
        ai_intent_raw = (payload.get("ai_intent") or "").strip()
        ai_sub_intent = (payload.get("ai_sub_intent") or "").strip()
        ai_summary = (payload.get("ai_summary") or "").strip()
        ai_reason = (payload.get("ai_reason") or "").strip()
        ai_needs_human = bool(payload.get("ai_needs_human"))

        try:
            ai_confidence = float(payload.get("ai_confidence") or 0.0)
        except Exception:
            ai_confidence = 0.0

        _logger.info(
            "[WA-INTENT-AI] Datos recibidos | provider=%s intent=%s sub_intent=%s confidence=%s needs_human=%s reason=%s summary=%s",
            ai_provider or False,
            ai_intent_raw or False,
            ai_sub_intent or False,
            ai_confidence,
            ai_needs_human,
            ai_reason or False,
            ai_summary[:300] if ai_summary else False,
        )

        ai_intent_map = {
            "toner": {
                "intent": "toner",
                "action": "start_flow_toner",
                "target_flow": "toner",
                "response_template": False,
            },

            "onsite_service": {
                "intent": "onsite_service",
                "action": "start_flow_onsite",
                "target_flow": "onsite",
                "response_template": False,
            },
            "service": {
                "intent": "onsite_service",
                "action": "start_flow_onsite",
                "target_flow": "onsite",
                "response_template": False,
            },
            "printer_issue": {
                "intent": "printer_issue",
                "action": "start_flow_onsite",
                "target_flow": "onsite",
                "response_template": False,
            },

            "remote_support": {
                "intent": "remote_service",
                "action": "start_flow_remote",
                "target_flow": "remote",
                "response_template": False,
            },
            "remote_service": {
                "intent": "remote_service",
                "action": "start_flow_remote",
                "target_flow": "remote",
                "response_template": False,
            },
            "anydesk": {
                "intent": "remote_service",
                "action": "start_flow_remote",
                "target_flow": "remote",
                "response_template": False,
            },
            "scanner": {
                "intent": "remote_service",
                "action": "start_flow_remote",
                "target_flow": "remote",
                "response_template": False,
            },

            "greeting": {
                "intent": "greeting",
                "action": "reply",
                "target_flow": "none",
                "response_template": "main_menu_technical",
            },
            "thanks": {
                "intent": "thanks",
                "action": "reply",
                "target_flow": "none",
                "response_template": "thanks_reply",
            },
            "goodbye": {
                "intent": "goodbye",
                "action": "reply",
                "target_flow": "none",
                "response_template": "goodbye_reply",
            },
            "sales": {
                "intent": "sales",
                "action": "reply",
                "target_flow": "none",
                "response_template": "sales_contact",
            },
            "billing": {
                "intent": "billing",
                "action": "reply",
                "target_flow": "none",
                "response_template": "billing_contact",
            },

            "human": {
                "intent": "human",
                "action": "handoff",
                "target_flow": "none",
                "response_template": "human_take",
            },
        }

        try:
            threshold_param = request.env["ir.config_parameter"].sudo().get_param(
                "sat.whatsapp_ai_intent_threshold",
                "0.75",
            )
            ai_threshold = float(threshold_param or 0.75)
        except Exception:
            ai_threshold = 0.75

        if ai_intent_raw and ai_confidence >= ai_threshold:
            ai_key = ai_intent_raw.strip().lower()

            if ai_key in ai_intent_map:
                mapped = ai_intent_map[ai_key]

                result = {
                    "found": True,
                    "source": "ai_intent",
                    "provider": ai_provider or "ai",
                    "intent": mapped.get("intent"),
                    "action": mapped.get("action"),
                    "target_flow": mapped.get("target_flow") or "none",
                    "response_template": mapped.get("response_template") or False,
                    "confidence": ai_confidence,
                    "ai_intent": ai_intent_raw,
                    "ai_sub_intent": ai_sub_intent or False,
                    "ai_summary": ai_summary or False,
                    "ai_reason": ai_reason or False,
                    "ai_needs_human": ai_needs_human,
                    "applies_to": applies_to,
                    "rule_id": False,
                    "rule_name": "AI / Gemini / n8n",
                    "stop_flow": False,
                    "allow_ai_after": False,
                }

                _logger.warning(
                    "[WA-INTENT-AI] USANDO intención AI | original_ai=%s mapped_intent=%s action=%s target_flow=%s confidence=%s threshold=%s sub_intent=%s text=%s",
                    ai_intent_raw,
                    result.get("intent"),
                    result.get("action"),
                    result.get("target_flow"),
                    ai_confidence,
                    ai_threshold,
                    ai_sub_intent or False,
                    text_debug[:300],
                )

                return result, applies_to

            _logger.warning(
                "[WA-INTENT-AI] AI intent no reconocido, se usará detector Odoo | ai_intent=%s confidence=%s text=%s",
                ai_intent_raw,
                ai_confidence,
                text_debug[:300],
            )

        elif ai_intent_raw:
            _logger.info(
                "[WA-INTENT-AI] AI intent ignorado por baja confianza | ai_intent=%s confidence=%s threshold=%s text=%s",
                ai_intent_raw,
                ai_confidence,
                ai_threshold,
                text_debug[:300],
            )
        else:
            _logger.info(
                "[WA-INTENT-AI] No llegó ai_intent desde n8n | text=%s",
                text_debug[:300],
            )

        try:
            _logger.info(
                "[WA-INTENT-ODOO] Ejecutando detector por reglas | applies_to=%s after_hours=%s current_flow=%s text=%s",
                applies_to,
                not business_status.get("is_open"),
                session.current_flow if session else False,
                text_debug[:300],
            )

            result = request.env["whatsapp.intent.rule"].sudo().detect_intent(
                message=message_text,
                partner=partner if partner else False,
                applies_to=applies_to,
                is_after_hours=not business_status.get("is_open"),
                current_flow=session.current_flow if session else False,
            )
            result = result or {"found": False}

            _logger.info(
                "[WA-INTENT-ODOO] Resultado reglas | found=%s intent=%s action=%s template=%s target_flow=%s",
                bool(result.get("found")),
                result.get("intent"),
                result.get("action"),
                result.get("response_template"),
                result.get("target_flow"),
            )

        except TypeError:
            _logger.warning(
                "[WA-INTENT-ODOO] detect_intent no acepta current_flow, usando compatibilidad antigua"
            )

            try:
                result = request.env["whatsapp.intent.rule"].sudo().detect_intent(
                    message=message_text,
                    partner=partner if partner else False,
                    applies_to=applies_to,
                    is_after_hours=not business_status.get("is_open"),
                )
                result = result or {"found": False}

                _logger.info(
                    "[WA-INTENT-ODOO] Resultado reglas compatibilidad | found=%s intent=%s action=%s template=%s target_flow=%s",
                    bool(result.get("found")),
                    result.get("intent"),
                    result.get("action"),
                    result.get("response_template"),
                    result.get("target_flow"),
                )

            except Exception:
                _logger.exception(
                    "[SAT-WHATSAPP-API] Error detectando intención por reglas compatibilidad"
                )
                result = {"found": False}

        except Exception:
            _logger.exception("[SAT-WHATSAPP-API] Error detectando intención")
            result = {"found": False}

        _logger.info(
            "[WA-INTENT] FIN detectar intención | found=%s intent=%s action=%s source=%s applies_to=%s",
            bool(result.get("found")),
            result.get("intent"),
            result.get("action"),
            result.get("source") or "odoo_rules",
            applies_to,
        )

        return result, applies_to

    def _execute_intent_action(
        self,
        partner,
        session,
        identifiers,
        message_text,
        intent_result,
        business_status,
        payload=False,
    ):
        intent_result = intent_result or {}
        intent = intent_result.get("intent") or "unknown"
        action = intent_result.get("action") or False

        text_lower = (message_text or "").strip().lower()

        if text_lower in ["cancelar", "cancela", "salir", "terminar"]:
            session.reset_conversation(reason="abandoned")
            return "Listo, cancelé el flujo activo. ¿En qué más podemos ayudarte?"

        if action == "ignore":
            return False

        if action == "cancel_flow":
            session.reset_conversation(reason="abandoned")
            return "Listo, cancelé el flujo activo. ¿En qué más podemos ayudarte?"

        if intent == "greeting":
            return self._get_greeting_message(
                partner=partner,
                session=session,
                business_status=business_status,
            )

        if action == "handoff" or intent == "human":
            request.env["whatsapp.handoff"].sudo().create_unknown_intent_handoff(
                partner,
                session=session,
                initial_message=message_text or "",
                context={
                    "intent_result": intent_result,
                    "reason": "Cliente solicitó atención humana.",
                },
            )

            partner.whatsapp_enable_human_mode_api(taken_by_name="Bot WhatsApp")
            session.action_set_human()

            return self._render_template(
                "human_take",
                partner=partner,
                session=session,
                fallback="He derivado tu conversación con un asesor. Te atenderán en breve.",
            )

        if action == "reply":
            template = intent_result.get("response_template")
            if template:
                rendered = self._render_template(
                    template,
                    partner=partner,
                    session=session,
                    company=partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False,
                    fallback=False,
                )
                if rendered:
                    return rendered

        if action == "ask_dni":
            return self._render_template(
                "ask_dni",
                partner=partner,
                session=session,
                fallback="Para poder ayudarte, por favor envíame tu DNI de 8 dígitos.",
            )

        if action == "ask_ruc":
            return self._render_template(
                "ask_ruc",
                partner=partner,
                session=session,
                fallback="Por favor envíame el RUC de tu empresa.",
            )

        if action == "select_company":
            return self._company_selection_message(partner, session=session)

        if action == "start_flow_toner" or intent == "toner":
            return self._start_toner_flow(
                partner,
                session,
                identifiers,
                payload=payload,
            )

        if action == "start_flow_onsite" or intent in [
            "onsite_service",
            "service",
            "printer_issue",
        ]:
            return self._start_onsite_flow(
                partner,
                session,
                identifiers,
                payload=payload,
            )

        if action == "start_flow_remote" or intent in [
            "remote_service",
            "anydesk",
            "scanner",
        ]:
            return self._start_remote_flow(
                partner,
                session,
                identifiers,
                payload=payload,
            )

        if action == "send_service_link":
            link = self._get_service_url(
                partner=partner,
                company=partner.whatsapp_active_company_id if partner else False,
            )
            return "Puedes registrar tu solicitud aquí:\n%s" % link

        if intent == "thanks":
            return self._render_template(
                "thanks_reply",
                partner=partner,
                session=session,
                fallback="Con gusto. ¿Necesitas algo más?",
            )

        if intent == "goodbye":
            return self._render_template(
                "goodbye_reply",
                partner=partner,
                session=session,
                fallback="Gracias por comunicarte con nosotros. Que tengas buen día.",
            )

        request.env["whatsapp.handoff"].sudo().create_unknown_intent_handoff(
            partner,
            session=session,
            initial_message=message_text,
            context={"intent_result": intent_result},
        )
        partner.whatsapp_enable_human_mode_api(taken_by_name="Bot WhatsApp")
        session.action_set_human()

        return (
            "No pude identificar con seguridad tu solicitud. "
            "Te estoy derivando con un asesor para que pueda ayudarte."
        )

    # ==========================================================
    # Menú principal
    # ==========================================================
    def _build_main_menu_text(self, partner=False, session=False):
        partner_name = "cliente"
        company_name = "No seleccionada"

        if partner:
            try:
                if partner.name:
                    partner_name = partner.name.split()[0]
            except Exception:
                partner_name = partner.name or "cliente"

            try:
                if partner.whatsapp_active_company_id:
                    company_name = partner.whatsapp_active_company_id.name or "No seleccionada"
            except Exception:
                company_name = "No seleccionada"

        has_multiple_companies = False
        try:
            if partner and hasattr(partner, "_get_whatsapp_available_companies"):
                companies = partner._get_whatsapp_available_companies()
                has_multiple_companies = bool(len(companies) > 1)
        except Exception:
            _logger.exception(
                "[WA-COMPANY] No se pudo verificar empresas asociadas para menú"
            )
            has_multiple_companies = False

        lines = [
            "Hola %s 👋" % partner_name,
            "",
            "Soy el asistente virtual de *ANDES SOLUTION COPIERS*.",
            "",
            "Empresa activa:",
            "🏢 *%s*" % company_name,
            "",
            "¿En qué podemos ayudarte hoy?",
            "",
            "*1* 🖨️ Solicitar tóner",
            "*2* 🛠️ Registrar servicio técnico",
            "*3* 💻 Asistencia remota",
            "*4* 👨‍💼 Hablar con un técnico",
        ]

        if has_multiple_companies:
            lines.append("*5* 🏢 Cambiar / ver empresa activa")

        return "\n".join(lines)