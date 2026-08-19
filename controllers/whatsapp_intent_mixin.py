# -*- coding: utf-8 -*-

import logging

from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppIntentMixin:
    # ==========================================================
    # Detectar intención
    # ==========================================================
    def _detect_intent(
        self,
        text,
        partner=False,
        business_status=None,
        session=False,
        payload=False,
    ):
        payload = payload or {}
        business_status = business_status or {}

        applies_to = self._get_applies_to(
            partner=partner,
            business_status=business_status,
        )

        current_flow = "none"
        if session and session.current_flow:
            current_flow = session.current_flow or "none"

        after_hours = not bool(business_status.get("is_open"))

        _logger.info(
            "[WA-INTENT] INICIO detectar intención | partner_id=%s session_id=%s applies_to=%s flow=%s text=%s",
            partner.id if partner else False,
            session.id if session else False,
            applies_to,
            current_flow,
            text,
        )

        # ======================================================
        # 1) Intento recibido desde IA / n8n
        # ======================================================
        ai_provider = payload.get("ai_provider") or False
        ai_intent = payload.get("ai_intent") or False
        ai_sub_intent = payload.get("ai_sub_intent") or False
        ai_reason = payload.get("ai_reason") or False
        ai_summary = payload.get("ai_summary") or False
        ai_needs_human = bool(payload.get("ai_needs_human"))

        try:
            ai_confidence = float(payload.get("ai_confidence") or 0)
        except Exception:
            ai_confidence = 0.0

        try:
            threshold = float(
                request.env["ir.config_parameter"].sudo().get_param(
                    "sat.whatsapp_ai_intent_threshold",
                    default="0.75",
                )
            )
        except Exception:
            threshold = 0.75

        _logger.info(
            "[WA-INTENT-AI] Datos recibidos | provider=%s intent=%s sub_intent=%s confidence=%s needs_human=%s reason=%s summary=%s",
            ai_provider,
            ai_intent,
            ai_sub_intent,
            ai_confidence,
            ai_needs_human,
            ai_reason,
            ai_summary,
        )

        if ai_needs_human:
            return {
                "found": True,
                "intent": "human",
                "action": "handoff",
                "target_flow": "none",
                "response_template": "human_take",
                "source": "ai",
                "confidence": ai_confidence,
                "ai_provider": ai_provider,
                "ai_reason": ai_reason,
                "ai_summary": ai_summary,
            }, applies_to

        if ai_intent and ai_confidence >= threshold:
            normalized_ai_intent = str(ai_intent or "").strip().lower()

            ai_map = {
                "toner": {
                    "intent": "toner",
                    "action": "start_flow_toner",
                    "target_flow": "toner",
                },
                "supplies": {
                    "intent": "toner",
                    "action": "start_flow_toner",
                    "target_flow": "toner",
                },
                "suministros": {
                    "intent": "toner",
                    "action": "start_flow_toner",
                    "target_flow": "toner",
                },
                "onsite_service": {
                    "intent": "onsite_service",
                    "action": "start_flow_onsite",
                    "target_flow": "onsite",
                },
                "service": {
                    "intent": "onsite_service",
                    "action": "start_flow_onsite",
                    "target_flow": "onsite",
                },
                "printer_issue": {
                    "intent": "printer_issue",
                    "action": "start_flow_onsite",
                    "target_flow": "onsite",
                },
                "technical_service": {
                    "intent": "onsite_service",
                    "action": "start_flow_onsite",
                    "target_flow": "onsite",
                },
                "remote_service": {
                    "intent": "remote_service",
                    "action": "start_flow_remote",
                    "target_flow": "remote",
                },
                "remote_support": {
                    "intent": "remote_service",
                    "action": "start_flow_remote",
                    "target_flow": "remote",
                },
                "anydesk": {
                    "intent": "remote_service",
                    "action": "start_flow_remote",
                    "target_flow": "remote",
                },
                "scanner": {
                    "intent": "remote_service",
                    "action": "start_flow_remote",
                    "target_flow": "remote",
                },
                "scan": {
                    "intent": "remote_service",
                    "action": "start_flow_remote",
                    "target_flow": "remote",
                },
                "business_hours": {
                    "intent": "business_hours",
                    "action": "business_hours",
                    "target_flow": "none",
                    "response_template": "business_hours_query",
                },
                "hours": {
                    "intent": "business_hours",
                    "action": "business_hours",
                    "target_flow": "none",
                    "response_template": "business_hours_query",
                },
                "schedule": {
                    "intent": "business_hours",
                    "action": "business_hours",
                    "target_flow": "none",
                    "response_template": "business_hours_query",
                },
                "calendar": {
                    "intent": "business_hours",
                    "action": "business_hours",
                    "target_flow": "none",
                    "response_template": "business_hours_query",
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
                "billing": {
                    "intent": "billing",
                    "action": "reply",
                    "target_flow": "none",
                    "response_template": "billing_contact",
                },
                "sales": {
                    "intent": "sales",
                    "action": "reply",
                    "target_flow": "none",
                    "response_template": "sales_contact",
                },
                "human": {
                    "intent": "human",
                    "action": "handoff",
                    "target_flow": "none",
                    "response_template": "human_take",
                },
            }

            mapped = ai_map.get(normalized_ai_intent)

            if mapped:
                result = dict(mapped)
                result.update({
                    "found": True,
                    "source": "ai_intent",
                    "confidence": ai_confidence,
                    "ai_provider": ai_provider,
                    "ai_intent": ai_intent,
                    "ai_sub_intent": ai_sub_intent,
                    "ai_reason": ai_reason,
                    "ai_summary": ai_summary,
                })

                _logger.info(
                    "[WA-INTENT-AI] Intención aceptada | intent=%s action=%s confidence=%s threshold=%s",
                    result.get("intent"),
                    result.get("action"),
                    ai_confidence,
                    threshold,
                )

                return result, applies_to

            _logger.info(
                "[WA-INTENT-AI] Intent IA no mapeado | intent=%s confidence=%s",
                ai_intent,
                ai_confidence,
            )

        elif ai_intent:
            _logger.info(
                "[WA-INTENT-AI] Intent IA descartado por confianza | intent=%s confidence=%s threshold=%s",
                ai_intent,
                ai_confidence,
                threshold,
            )
        else:
            _logger.info(
                "[WA-INTENT-AI] No llegó ai_intent desde n8n | text=%s",
                text,
            )

        # ======================================================
        # 2) Detector de reglas Odoo
        # ======================================================
        _logger.info(
            "[WA-INTENT-ODOO] Ejecutando detector por reglas | applies_to=%s after_hours=%s current_flow=%s text=%s",
            applies_to,
            after_hours,
            current_flow,
            text,
        )

        IntentRule = request.env["whatsapp.intent.rule"].sudo()

        try:
            result = IntentRule.detect_intent(
                message=text or "",
                partner=partner if partner else False,
                applies_to=applies_to,
                is_after_hours=after_hours,
                current_flow=current_flow,
            )
        except TypeError:
            result = IntentRule.detect_intent(
                message=text or "",
                partner=partner if partner else False,
                applies_to=applies_to,
                is_after_hours=after_hours,
            )

        result = result or {}

        if "found" not in result:
            result["found"] = False

        if not result.get("intent"):
            result["intent"] = "unknown"

        if not result.get("action"):
            result["action"] = "ai"

        if not result.get("target_flow"):
            result["target_flow"] = "none"

        result["source"] = result.get("source") or "odoo_rules"

        _logger.info(
            "[WA-INTENT-ODOO] Resultado reglas | found=%s intent=%s action=%s template=%s target_flow=%s",
            result.get("found"),
            result.get("intent"),
            result.get("action"),
            result.get("response_template"),
            result.get("target_flow"),
        )

        _logger.info(
            "[WA-INTENT] FIN detectar intención | found=%s intent=%s action=%s source=%s applies_to=%s",
            result.get("found"),
            result.get("intent"),
            result.get("action"),
            result.get("source"),
            applies_to,
        )

        return result, applies_to

    # ==========================================================
    # Ejecutar intención
    # ==========================================================
    def _execute_intent_action(
        self,
        result,
        partner,
        session,
        identifiers,
        payload=False,
        business_status=None,
    ):
        result = result or {}
        payload = payload or {}
        business_status = business_status or {}

        intent = result.get("intent") or "unknown"
        action = result.get("action") or "ai"
        target_flow = result.get("target_flow") or "none"
        template = result.get("response_template") or False

        message_text = (
            payload.get("message")
            or payload.get("text")
            or payload.get("content")
            or ""
        )

        _logger.info(
            "[WA-INTENT] Ejecutando acción | partner_id=%s session_id=%s intent=%s action=%s target_flow=%s template=%s",
            partner.id if partner else False,
            session.id if session else False,
            intent,
            action,
            target_flow,
            template,
        )

        # ======================================================
        # Cancelar flujo activo
        # ======================================================
        if (
            intent == "cancel"
            or action == "cancel_flow"
            or result.get("cancels_active_flow")
        ):
            if session:
                session.reset_conversation(reason="cancelled_by_user")

            message = self._render_template(
                template or "cancel_flow_reply",
                partner=partner,
                session=session,
                fallback="✅ Se canceló la operación actual. Puedes escribir MENÚ para ver las opciones disponibles.",
            )

            return {
                "content": message,
                "intent": "cancel",
                "action": "cancel_flow",
                "template": template or "cancel_flow_reply",
                "create_outbox": True,
                "stop": True,
            }

        # ======================================================
        # Ignorar
        # ======================================================
        if action == "ignore":
            return {
                "content": "",
                "intent": intent,
                "action": action,
                "template": False,
                "create_outbox": False,
                "stop": True,
            }

        # ======================================================
        # Consulta de horario / calendario
        # IMPORTANTE: antes de action == reply
        # ======================================================
        if action == "business_hours" or intent == "business_hours":
            business_status = business_status or self._compute_business_status()

            company = (
                partner.whatsapp_active_company_id
                if partner and partner.whatsapp_active_company_id
                else False
            )

            reason_label = (
                business_status.get("reason_label")
                or business_status.get("reason")
                or ""
            )

            business_message = (
                business_status.get("message")
                or business_status.get("business_message")
                or ""
            )

            display_hours = business_status.get("display_hours") or ""

            if not display_hours:
                display_hours = "Horario no configurado para hoy."

            if not business_message:
                if business_status.get("is_open"):
                    business_message = "Estamos en horario de atención."
                else:
                    business_message = "En este momento estamos fuera de horario de atención."

            message = self._render_template(
                template or "business_hours_query",
                partner=partner,
                session=session,
                company=company,
                extra={
                    "business_reason": reason_label,
                    "business_message": business_message,
                    "display_hours": display_hours,
                    "business_date": business_status.get("date") or "",
                    "business_is_open": business_status.get("is_open"),
                },
                fallback=(
                    "🕒 *Horario de atención*\n\n"
                    "Estado actual: *%s*\n\n"
                    "Horario de hoy:\n"
                    "%s\n\n"
                    "%s"
                ) % (
                    reason_label or "Consulta de horario",
                    display_hours,
                    business_message,
                ),
            )

            return {
                "content": message,
                "intent": "business_hours",
                "action": "business_hours",
                "template": template or "business_hours_query",
                "create_outbox": True,
                "stop": False,
            }

        # ======================================================
        # Saludo
        # IMPORTANTE: antes de action == reply
        # ======================================================
        if intent == "greeting":
            company = (
                partner.whatsapp_active_company_id
                if partner and partner.whatsapp_active_company_id
                else False
            )

            if template:
                message = self._render_template(
                    template,
                    partner=partner,
                    session=session,
                    company=company,
                    fallback=self._build_main_menu_text(partner=partner),
                )
            else:
                message = self._get_greeting_message(
                    partner=partner,
                    session=session,
                    business_status=business_status,
                )

            return {
                "content": message,
                "intent": "greeting",
                "action": "reply",
                "template": template or "main_menu_technical",
                "create_outbox": True,
                "stop": False,
            }
        # ======================================================
        # Mostrar menú principal
        # ======================================================
        if intent == "menu":
            company = (
                partner.whatsapp_active_company_id
                if partner and partner.whatsapp_active_company_id
                else False
            )

            message = self._render_template(
                template or "main_menu_technical",
                partner=partner,
                session=session,
                company=company,
                fallback=self._build_main_menu_text(partner=partner),
            )

            return {
                "content": message,
                "intent": "menu",
                "action": "reply",
                "template": template or "main_menu_technical",
                "create_outbox": True,
                "stop": False,
            }
        # ======================================================
        # Handoff humano
        # IMPORTANTE: antes de action == reply
        # ======================================================
        if action == "handoff" or intent == "human":
            try:
                request.env["whatsapp.handoff"].sudo().create_unknown_intent_handoff(
                    partner,
                    session=session,
                    initial_message=message_text,
                    context={
                        "reason": result.get("ai_reason")
                        or result.get("reason")
                        or "Cliente solicita atención humana.",
                        "intent_result": result,
                    },
                )
            except Exception:
                _logger.exception(
                    "[WA-INTENT] No se pudo crear handoff humano partner=%s session=%s",
                    partner.id if partner else False,
                    session.id if session else False,
                )

            if partner:
                partner.whatsapp_enable_human_mode_api(taken_by_name="Bot WhatsApp")

            if session:
                session.action_set_human()

            message = self._render_template(
                template or "human_take",
                partner=partner,
                session=session,
                fallback="👨‍💼 Un asesor continuará con la atención.",
            )

            return {
                "content": message,
                "intent": "human",
                "action": "handoff",
                "template": template or "human_take",
                "create_outbox": True,
                "stop": True,
            }

        # ======================================================
        # Respuesta por plantilla
        # ======================================================
        if action == "reply":
            message = self._render_template(
                template or "fallback",
                partner=partner,
                session=session,
                company=(
                    partner.whatsapp_active_company_id
                    if partner and partner.whatsapp_active_company_id
                    else False
                ),
                fallback=self._build_main_menu_text(partner),
            )

            return {
                "content": message,
                "intent": intent,
                "action": "reply",
                "template": template or "fallback",
                "create_outbox": True,
                "stop": False,
            }

        # ======================================================
        # Solicitar DNI
        # ======================================================
        if action == "ask_dni":
            if session:
                session.start_flow(
                    "registration",
                    "awaiting_dni",
                    context={
                        "intent": "registration",
                    },
                )

            message = self._render_template(
                template or "ask_dni",
                partner=partner,
                session=session,
                fallback="Para poder ayudarte, por favor envíame tu DNI de 8 dígitos.",
            )

            return {
                "content": message,
                "intent": "dni",
                "action": "ask_dni",
                "template": template or "ask_dni",
                "create_outbox": True,
                "stop": False,
            }

        # ======================================================
        # Solicitar RUC
        # ======================================================
        if action == "ask_ruc":
            if session:
                session.start_flow(
                    "registration",
                    "awaiting_ruc",
                    context={
                        "intent": "registration",
                        "dni": self._only_digits(message_text),
                    },
                )

            message = self._render_template(
                template or "ask_ruc",
                partner=partner,
                session=session,
                fallback="Ahora envíame el RUC de tu empresa para completar el registro.",
            )

            return {
                "content": message,
                "intent": "ruc",
                "action": "ask_ruc",
                "template": template or "ask_ruc",
                "create_outbox": True,
                "stop": False,
            }

        # ======================================================
        # Seleccionar empresa
        # ======================================================
        if action == "select_company" or intent == "select_company":
            message = self._company_selection_message(partner, session)

            return {
                "content": message,
                "intent": "select_company",
                "action": "select_company",
                "template": template or "select_company",
                "create_outbox": True,
                "stop": False,
            }

        # ======================================================
        # Flujo tóner
        # ======================================================
        if action == "start_flow_toner" or target_flow == "toner" or intent == "toner":
            message = self._start_toner_flow(
                partner=partner,
                session=session,
                identifiers=identifiers,
                payload=payload,
            )

            return {
                "content": message,
                "intent": "toner",
                "action": "start_flow_toner",
                "template": False,
                "create_outbox": True,
                "stop": False,
            }

        # ======================================================
        # Flujo servicio presencial
        # ======================================================
        if (
            action == "start_flow_onsite"
            or target_flow == "onsite"
            or intent in ["onsite_service", "printer_issue", "service"]
        ):
            message = self._start_onsite_flow(
                partner=partner,
                session=session,
                identifiers=identifiers,
                payload=payload,
            )

            return {
                "content": message,
                "intent": intent or "onsite_service",
                "action": "start_flow_onsite",
                "template": False,
                "create_outbox": True,
                "stop": False,
            }

        # ======================================================
        # Flujo soporte remoto
        # ======================================================
        if (
            action == "start_flow_remote"
            or target_flow == "remote"
            or intent in ["remote_service", "scanner", "remote_support"]
        ):
            message = self._start_remote_flow(
                partner=partner,
                session=session,
                identifiers=identifiers,
                payload=payload,
            )

            return {
                "content": message,
                "intent": "remote_service",
                "action": "start_flow_remote",
                "template": False,
                "create_outbox": True,
                "stop": False,
            }

        # ======================================================
        # Link servicio
        # ======================================================
        if action == "send_service_link":
            company = (
                partner.whatsapp_active_company_id
                if partner and partner.whatsapp_active_company_id
                else False
            )

            machine = self._get_context_machine(session.get_context() if session else {})
            service_link = self._get_service_url(
                partner=partner,
                company=company,
                machine=machine,
            )

            message = self._render_template(
                template or "service_link",
                partner=partner,
                session=session,
                company=company,
                extra={
                    "service_link": service_link,
                },
                fallback="Puedes registrar tu servicio técnico aquí:\n%s" % service_link,
            )

            return {
                "content": message,
                "intent": "onsite_service",
                "action": "send_service_link",
                "template": template or "service_link",
                "create_outbox": True,
                "stop": False,
            }

        # ======================================================
        # Agradecimiento
        # ======================================================
        if intent == "thanks":
            message = self._render_template(
                template or "thanks_reply",
                partner=partner,
                session=session,
                fallback="Con gusto. Estamos para ayudarte.",
            )

            return {
                "content": message,
                "intent": "thanks",
                "action": "reply",
                "template": template or "thanks_reply",
                "create_outbox": True,
                "stop": False,
            }

        # ======================================================
        # Despedida
        # ======================================================
        if intent == "goodbye":
            message = self._render_template(
                template or "goodbye_reply",
                partner=partner,
                session=session,
                fallback="Gracias por comunicarte con ANDES SOLUTION COPIERS. Que tengas un excelente día.",
            )

            return {
                "content": message,
                "intent": "goodbye",
                "action": "reply",
                "template": template or "goodbye_reply",
                "create_outbox": True,
                "stop": False,
            }

        # ======================================================
        # Fallback: no entendido => handoff
        # ======================================================
        try:
            request.env["whatsapp.handoff"].sudo().create_unknown_intent_handoff(
                partner,
                session=session,
                initial_message=message_text,
                context={
                    "reason": "Intención no reconocida automáticamente.",
                    "intent_result": result,
                },
            )
        except Exception:
            _logger.exception(
                "[WA-INTENT] No se pudo crear handoff de intención desconocida partner=%s session=%s",
                partner.id if partner else False,
                session.id if session else False,
            )

        if partner:
            partner.whatsapp_enable_human_mode_api(taken_by_name="Bot WhatsApp")

        if session:
            session.action_set_human()

        message = self._render_template(
            "unknown_with_menu",
            partner=partner,
            session=session,
            fallback=(
                "No pude identificar con seguridad tu solicitud. "
                "Un asesor continuará con la atención."
            ),
        )

        return {
            "content": message,
            "intent": intent or "unknown",
            "action": action or "ai",
            "template": "unknown_with_menu",
            "create_outbox": True,
            "stop": True,
        }

    # ==========================================================
    # Menú principal
    # ==========================================================
    def _build_main_menu_text(self, partner=False, session=False):
        # ``session`` se acepta por compatibilidad con otros mixins.
        # El menú no depende de la sesión para construir su contenido,
        # pero algunos flujos (por ejemplo selección de empresa) la pasan.
        _logger.debug(
            "[WA-MENU] Construyendo menú principal | partner_id=%s session_id=%s",
            partner.id if partner else False,
            session.id if session else False,
        )

        company_name = "Sin empresa activa"

        try:
            if partner and partner.whatsapp_active_company_id:
                company_name = partner.whatsapp_active_company_id.display_name
        except Exception:
            pass

        show_company_option = False
        try:
            if partner and len(partner.whatsapp_company_ids) > 1:
                show_company_option = True
        except Exception:
            show_company_option = False

        lines = [
            "Hola 👋 Soy el asistente virtual de *ANDES SOLUTION COPIERS*.",
            "",
            "Empresa activa: 🏢 *%s*" % company_name,
            "",
            "¿En qué podemos ayudarte hoy?",
            "",
            "*1* 🖨️ Solicitar tóner",
            "*2* 🛠️ Registrar servicio técnico",
            "*3* 💻 Asistencia remota",
            "*4* 👨‍💼 Hablar con un técnico",
        ]

        if show_company_option:
            lines.append("*5* 🏢 Cambiar / ver empresa activa")

        lines.append("")
        lines.append("También puedes escribir directamente tu consulta.")

        return "\n".join(lines)