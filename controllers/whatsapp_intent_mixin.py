# -*- coding: utf-8 -*-

import logging

from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppIntentMixin:
    """
    Detección y ejecución de intenciones para WhatsApp.

    Principios de esta versión:
    - Gemini/n8n interpreta, Odoo valida y ejecuta.
    - No se modifica el umbral de IA ni el mapeo de intenciones.
    - La solicitud de atención humana siempre requiere confirmación.
    - Los mensajes se renderizan desde whatsapp.template cuando existe
      una plantilla profesional disponible.
    - La navegación principal se mantiene consistente con MENU,
      ATRÁS y CANCELAR.
    """

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
            "[WA-INTENT] INICIO detectar intención | "
            "partner_id=%s session_id=%s applies_to=%s flow=%s "
            "after_hours=%s business_reason=%s text=%s",
            partner.id if partner else False,
            session.id if session else False,
            applies_to,
            current_flow,
            after_hours,
            business_status.get("reason") or False,
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
    # Helpers de presentación / disponibilidad
    # ==========================================================
    def _intent_business_status_safe(self, business_status=None):
        if isinstance(business_status, dict) and business_status:
            return business_status

        try:
            status = self._compute_business_status()
            return status if isinstance(status, dict) else {}
        except Exception:
            _logger.exception(
                "[WA-INTENT] No se pudo evaluar estado horario"
            )
            return {}

    def _intent_realtime_unavailable(self, business_status=None):
        status = self._intent_business_status_safe(
            business_status
        )
        return not bool(status.get("is_open"))

    def _render_human_confirmation(
        self,
        partner,
        session,
    ):
        return self._render_template(
            "human_confirmation",
            partner=partner,
            session=session,
            fallback=(
                "👨‍💼 *Atención con un asesor*\n\n"
                "¿Deseas que tu conversación sea derivada a uno "
                "de nuestros asesores?\n\n"
                "Responde:\n"
                "*SI* — solicitar atención humana\n"
                "*NO* — continuar con el asistente virtual\n\n"
                "🏠 También puedes escribir *MENU*."
            ),
        )

    def _render_first_clarification(
        self,
        partner,
        session,
    ):
        return self._render_template(
            "clarification_first",
            partner=partner,
            session=session,
            fallback=(
                "🤔 *Necesito un poco más de información*\n\n"
                "No pude identificar con suficiente seguridad lo que "
                "necesitas. Describe brevemente tu consulta o selecciona "
                "una opción:\n\n"
                "*1* 🖨️ Solicitar tóner\n"
                "*2* 🛠️ Registrar servicio técnico\n"
                "*3* 💻 Asistencia remota\n"
                "*4* 👨‍💼 Hablar con un técnico\n"
                "*5* 🏢 Cambiar / ver empresa activa\n\n"
                "Escribe *MENU* para volver al menú principal."
            ),
        )

    def _render_human_offer_after_clarification(
        self,
        partner,
        session,
    ):
        return self._render_template(
            "clarification_human_offer",
            partner=partner,
            session=session,
            fallback=(
                "🤝 *Podemos derivar tu consulta*\n\n"
                "Todavía no pude identificar con claridad tu solicitud.\n\n"
                "¿Deseas que un asesor continúe la atención?\n\n"
                "Responde *SI* o *NO*."
            ),
        )

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

        # Si la intención actual ya fue reconocida, se limpia el
        # contador de unknown previo sin borrar el resto del contexto.
        if session and intent not in ("unknown", "human") and action not in ("ai", "handoff"):
            try:
                context = session.get_context()
                if isinstance(context, dict):
                    changed = False
                    for key in ("unknown_attempts", "last_unknown_message"):
                        if key in context:
                            context.pop(key, None)
                            changed = True
                    if changed:
                        session.set_context(context)
                        _logger.info(
                            "[WA-HUMAN] Contador unknown limpiado por intención reconocida | session_id=%s intent=%s action=%s",
                            session.id,
                            intent,
                            action,
                        )
            except Exception:
                _logger.exception(
                    "[WA-HUMAN] No se pudo limpiar contador unknown | session_id=%s",
                    session.id if session else False,
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
                fallback=(
                    "✅ *Operación cancelada*\n\n"
                    "La gestión actual fue cancelada correctamente.\n\n"
                    "Escribe *MENU* para volver al menú principal."
                ),
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
                    business_message = (
                        "Nuestro equipo se encuentra disponible "
                        "dentro del horario de atención."
                    )
                else:
                    business_message = (
                        "En este momento no contamos con atención "
                        "en tiempo real. Las solicitudes de tóner y "
                        "servicio técnico pueden continuar registrándose "
                        "por este canal."
                    )

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
                    fallback=self._build_main_menu_text(partner=partner, session=session),
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
                fallback=self._build_main_menu_text(partner=partner, session=session),
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
        # Solicitud de atención humana
        #
        # Primero se pide confirmación. El modo humano se activa
        # recién cuando el cliente responde SÍ en /process.
        # ======================================================
        if action == "handoff" or intent == "human":
            reason = (
                result.get("ai_reason")
                or result.get("reason")
                or "Cliente solicita atención humana."
            )

            # Protección defensiva adicional:
            # process_mixin ya bloquea humano fuera de horario antes de
            # ejecutar esta acción. Esto evita que una llamada directa a
            # este método pueda saltarse esa política.
            if self._intent_realtime_unavailable(
                business_status
            ):
                message = self._render_template(
                    "human_unavailable",
                    partner=partner,
                    session=session,
                    extra={
                        "business_reason": (
                            business_status.get("reason_label")
                            or business_status.get("reason")
                            or "Fuera de horario"
                        ),
                        "business_message": (
                            business_status.get("message")
                            or ""
                        ),
                        "display_hours": (
                            business_status.get("display_hours")
                            or ""
                        ),
                    },
                    fallback=(
                        "👨‍💼 *Atención directa con un técnico*\n\n"
                        "En este momento la atención directa con nuestro "
                        "equipo técnico no se encuentra disponible.\n\n"
                        "Puedes registrar una solicitud de tóner o "
                        "servicio técnico para que sea atendida al "
                        "retomar el horario correspondiente.\n\n"
                        "Escribe *MENU* para volver al menú principal."
                    ),
                )

                _logger.info(
                    "[WA-HUMAN] Solicitud humana bloqueada por horario | "
                    "partner_id=%s session_id=%s reason=%s",
                    partner.id if partner else False,
                    session.id if session else False,
                    business_status.get("reason") or False,
                )

                return {
                    "content": message,
                    "intent": "human",
                    "action": "human_unavailable",
                    "template": "human_unavailable",
                    "create_outbox": True,
                    "stop": True,
                    "stop_bot": False,
                    "pending_human_confirmation": False,
                    "human_mode": False,
                }

            if session:
                try:
                    context = session.get_context()
                    if not isinstance(context, dict):
                        context = {}

                    context.update({
                        "pending_human_confirmation": True,
                        "human_confirmation_message": message_text or False,
                        "human_confirmation_reason": reason,
                        "human_confirmation_intent": result,
                    })
                    context.pop("unknown_attempts", None)
                    context.pop("last_unknown_message", None)
                    session.set_context(context)

                    _logger.info(
                        "[WA-HUMAN] Confirmación humana pendiente | partner_id=%s session_id=%s reason=%s",
                        partner.id if partner else False,
                        session.id if session else False,
                        reason,
                    )
                except Exception:
                    _logger.exception(
                        "[WA-HUMAN] Error guardando confirmación humana | partner_id=%s session_id=%s",
                        partner.id if partner else False,
                        session.id if session else False,
                    )

            message = self._render_human_confirmation(
                partner=partner,
                session=session,
            )

            return {
                "content": message,
                "intent": "human",
                "action": "confirm_handoff",
                "template": "human_confirmation",
                "create_outbox": True,
                "stop": True,
                "stop_bot": False,
                "pending_human_confirmation": True,
                "human_mode": False,
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
                fallback=self._build_main_menu_text(partner=partner, session=session),
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
                fallback=(
                    "👋 Para identificarte y continuar con la atención, "
                    "envíanos tu *DNI de 8 dígitos*."
                ),
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
                fallback=(
                    "Ahora envíanos el *RUC de 11 dígitos* de la empresa "
                    "con la que deseas realizar la atención."
                ),
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
                fallback=(
                    "🛠️ *Registro de servicio técnico*\n\n"
                    "Puedes registrar tu solicitud mediante el siguiente "
                    "enlace:\n\n%s\n\n"
                    "Escribe *MENU* para volver al menú principal."
                ) % service_link,
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
                fallback=(
                    "Con mucho gusto. 🙌\n\n"
                    "Estamos para ayudarte. Si necesitas realizar otra "
                    "gestión, escribe *MENU*."
                ),
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
                fallback=(
                    "Gracias por comunicarte con *ANDES SOLUTION COPIERS*. 👋\n\n"
                    "Cuando necesites una nueva gestión, puedes escribirnos "
                    "nuevamente por este mismo medio."
                ),
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
        # Fallback: intención no entendida
        #
        # 1er intento: pedir aclaración.
        # 2do intento consecutivo: preguntar si desea asesor.
        # No se activa modo humano sin confirmación del cliente.
        # ======================================================
        context = {}
        unknown_attempts = 0

        if session:
            try:
                context = session.get_context()
                if not isinstance(context, dict):
                    context = {}
                unknown_attempts = int(context.get("unknown_attempts") or 0)
            except Exception:
                context = {}
                unknown_attempts = 0
                _logger.exception(
                    "[WA-HUMAN] Error leyendo contador unknown | session_id=%s",
                    session.id if session else False,
                )

        unknown_attempts += 1

        if unknown_attempts <= 1:
            if session:
                try:
                    context["unknown_attempts"] = 1
                    context["last_unknown_message"] = message_text or False
                    context.pop("pending_human_confirmation", None)
                    context.pop("human_confirmation_message", None)
                    context.pop("human_confirmation_reason", None)
                    context.pop("human_confirmation_intent", None)
                    session.set_context(context)
                except Exception:
                    _logger.exception(
                        "[WA-HUMAN] Error guardando primer unknown | session_id=%s",
                        session.id if session else False,
                    )

            _logger.info(
                "[WA-HUMAN] Primer unknown: se solicita aclaración | partner_id=%s session_id=%s message=%r",
                partner.id if partner else False,
                session.id if session else False,
                message_text[:160] if message_text else "",
            )

            message = self._render_first_clarification(
                partner=partner,
                session=session,
            )

            return {
                "content": message,
                "intent": intent or "unknown",
                "action": "clarify",
                "template": "clarification_first",
                "create_outbox": True,
                "stop": True,
                "stop_bot": False,
                "pending_human_confirmation": False,
                "human_mode": False,
            }

        reason = "La consulta no pudo identificarse después de un intento de aclaración."

        if self._intent_realtime_unavailable(
            business_status
        ):
            if session:
                try:
                    context["unknown_attempts"] = 1
                    context["last_unknown_message"] = (
                        message_text
                        or False
                    )
                    context.pop(
                        "pending_human_confirmation",
                        None,
                    )
                    context.pop(
                        "human_confirmation_message",
                        None,
                    )
                    context.pop(
                        "human_confirmation_reason",
                        None,
                    )
                    context.pop(
                        "human_confirmation_intent",
                        None,
                    )
                    session.set_context(context)
                except Exception:
                    _logger.exception(
                        "[WA-HUMAN] Error evitando oferta humana "
                        "fuera de horario | session_id=%s",
                        session.id if session else False,
                    )

            _logger.info(
                "[WA-HUMAN] Segundo unknown sin oferta humana "
                "por horario | partner_id=%s session_id=%s reason=%s",
                partner.id if partner else False,
                session.id if session else False,
                business_status.get("reason") or False,
            )

            message = self._render_first_clarification(
                partner=partner,
                session=session,
            )

            return {
                "content": message,
                "intent": intent or "unknown",
                "action": "clarify",
                "template": "clarification_first",
                "create_outbox": True,
                "stop": True,
                "stop_bot": False,
                "pending_human_confirmation": False,
                "human_mode": False,
            }

        if session:
            try:
                context["unknown_attempts"] = unknown_attempts
                context["last_unknown_message"] = message_text or False
                context["pending_human_confirmation"] = True
                context["human_confirmation_message"] = message_text or False
                context["human_confirmation_reason"] = reason
                context["human_confirmation_intent"] = result
                session.set_context(context)
            except Exception:
                _logger.exception(
                    "[WA-HUMAN] Error guardando confirmación tras unknown | session_id=%s",
                    session.id if session else False,
                )

        _logger.info(
            "[WA-HUMAN] Segundo unknown: se solicita confirmación humana | partner_id=%s session_id=%s attempts=%s",
            partner.id if partner else False,
            session.id if session else False,
            unknown_attempts,
        )

        message = self._render_human_offer_after_clarification(
            partner=partner,
            session=session,
        )

        return {
            "content": message,
            "intent": intent or "unknown",
            "action": "confirm_handoff",
            "template": "clarification_human_offer",
            "create_outbox": True,
            "stop": True,
            "stop_bot": False,
            "pending_human_confirmation": True,
            "human_mode": False,
        }

    # ==========================================================
    # Menú principal
    # ==========================================================
    def _build_main_menu_text(self, partner=False, session=False):
        """
        Construye el menú principal de respaldo.

        La plantilla main_menu_technical continúa siendo la opción preferida.
        Este método garantiza una respuesta profesional aun cuando la
        plantilla no esté disponible.
        """
        _logger.debug(
            "[WA-MENU] Construyendo menú principal | "
            "partner_id=%s session_id=%s",
            partner.id if partner else False,
            session.id if session else False,
        )

        partner_name = ""
        company_name = "Sin empresa activa"

        try:
            if partner:
                partner_name = (
                    partner.name
                    or ""
                )
                if partner.whatsapp_active_company_id:
                    company_name = (
                        partner.whatsapp_active_company_id.display_name
                        or company_name
                    )
        except Exception:
            pass

        greeting = (
            "Hola, %s. 👋"
            % partner_name
            if partner_name
            else "Hola. 👋"
        )

        lines = [
            greeting,
            "",
            "Soy el asistente virtual de *ANDES SOLUTION COPIERS*.",
            "",
            "🏢 Empresa activa: *%s*" % company_name,
            "",
            "¿En qué podemos ayudarte?",
            "",
            "*1* 🖨️ Solicitar tóner",
            "*2* 🛠️ Registrar servicio técnico",
            "*3* 💻 Asistencia remota",
            "*4* 👨‍💼 Hablar con un técnico",
            "*5* 🏢 Cambiar / ver empresa activa",
            "",
            "Responde con el *número* de una opción.",
            "",
            "Durante cualquier proceso puedes escribir:",
            "↩️ *ATRÁS* para regresar al paso anterior",
            "🏠 *MENU* para volver al menú principal",
            "❌ *CANCELAR* para cancelar la operación actual",
            "",
            "También puedes escribir directamente tu consulta.",
        ]

        return "\n".join(lines)
