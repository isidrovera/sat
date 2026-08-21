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
    - Detectar intención con el horario real, sin alterar el tipo de contacto.
    - Aplicar disponibilidad después de conocer la intención.
    - Ejecutar acción.
    - Emitir respuesta y outbox.
    """

    # ==========================================================
    # Helpers de registro para contactos existentes
    # ==========================================================
    def _get_partner_whatsapp_companies_safe(self, partner):
        """
        Devuelve empresas asociadas al contacto para WhatsApp.

        Maneja:
        - whatsapp_company_ids
        - whatsapp_active_company_id
        - parent_id si el contacto pertenece a una empresa
        - el mismo partner si es empresa
        - método _get_whatsapp_available_companies() si existe
        """
        Partner = request.env["res.partner"].sudo()

        if not partner:
            return Partner

        companies = Partner

        try:
            if hasattr(partner, "_get_whatsapp_available_companies"):
                available = partner._get_whatsapp_available_companies()
                if available:
                    companies |= available
        except Exception:
            _logger.exception(
                "[WA-PROCESS] Error obteniendo empresas disponibles partner=%s",
                partner.id if partner else False,
            )

        try:
            if getattr(partner, "whatsapp_company_ids", False):
                companies |= partner.whatsapp_company_ids
        except Exception:
            pass

        try:
            if getattr(partner, "whatsapp_active_company_id", False):
                companies |= partner.whatsapp_active_company_id
        except Exception:
            pass

        try:
            if partner.parent_id and partner.parent_id.is_company:
                companies |= partner.parent_id
        except Exception:
            pass

        try:
            if partner.is_company:
                companies |= partner
        except Exception:
            pass

        return companies

    def _ensure_existing_partner_whatsapp_registration(self, partner, session=False):
        """
        Corrige el estado de registro WhatsApp para contactos ya existentes.

        Regla:
        1) Si el contacto ya está vinculado a una empresa:
           - NO pedir DNI
           - NO pedir RUC
           - marcar como registered

        2) Si el contacto ya tiene DNI/VAT pero no tiene empresa:
           - NO pedir DNI
           - pedir RUC

        3) Si no tiene DNI/VAT ni empresa:
           - mantener estado para pedir DNI.
        """
        if not partner:
            return "none"

        registration_state = (
            getattr(partner, "whatsapp_registration_state", "none")
            or "none"
        )

        companies = self._get_partner_whatsapp_companies_safe(partner)

        active_company = False
        try:
            active_company = (
                partner.whatsapp_active_company_id
                if partner.whatsapp_active_company_id
                else False
            )
        except Exception:
            active_company = False

        has_company = bool(active_company or companies)

        partner_vat_digits = self._only_digits(
            getattr(partner, "vat", "") or ""
        )

        # ======================================================
        # Si ya tiene empresa asociada, queda registrado.
        # No pedir DNI ni RUC.
        # ======================================================
        if has_company:
            selected_company = active_company

            # Solo asignar empresa automática si hay una sola.
            # Si hay varias, se deja que luego entre a selección de empresa.
            if not selected_company and companies and len(companies) == 1:
                selected_company = companies[0]

            vals = {}

            if selected_company and not active_company:
                vals["whatsapp_active_company_id"] = selected_company.id

            if registration_state != "registered":
                vals["whatsapp_registration_state"] = "registered"

            if vals:
                try:
                    partner.sudo().write(vals)
                except Exception:
                    _logger.exception(
                        "[WA-PROCESS] No se pudo marcar partner existente como registered | partner_id=%s vals=%s",
                        partner.id if partner else False,
                        vals,
                    )

            if session and selected_company:
                try:
                    session.sudo().write({
                        "active_company_id": selected_company.id,
                    })
                except Exception:
                    _logger.exception(
                        "[WA-PROCESS] No se pudo actualizar empresa activa en sesión | session_id=%s company_id=%s",
                        session.id if session else False,
                        selected_company.id if selected_company else False,
                    )

            _logger.info(
                "[WA-PROCESS] Partner existente con empresa. No se pide DNI/RUC | partner_id=%s state_before=%s company_id=%s companies=%s",
                partner.id if partner else False,
                registration_state,
                selected_company.id if selected_company else False,
                len(companies) if companies else 0,
            )

            return "registered"

        # ======================================================
        # Si tiene DNI/VAT pero no empresa, no pedir DNI.
        # Pedir RUC.
        # ======================================================
        if partner_vat_digits:
            if registration_state in ("none", "waiting_dni"):
                try:
                    partner.sudo().write({
                        "whatsapp_registration_state": "waiting_ruc",
                    })
                except Exception:
                    _logger.exception(
                        "[WA-PROCESS] No se pudo marcar partner existente como waiting_ruc | partner_id=%s",
                        partner.id if partner else False,
                    )

                _logger.info(
                    "[WA-PROCESS] Partner existente con DNI/VAT y sin empresa. No se pide DNI, se pedirá RUC | partner_id=%s vat=%s",
                    partner.id if partner else False,
                    partner.vat,
                )

                return "waiting_ruc"

        return registration_state


    # ==========================================================
    # Helpers: contexto / confirmación / handoff humano
    # ==========================================================
    def _get_session_context_safe(self, session):
        """Devuelve el contexto de sesión como dict sin romper /process."""
        if not session:
            return {}

        try:
            context = session.get_context()
            if isinstance(context, dict):
                return context
        except Exception:
            _logger.exception(
                "[WA-HUMAN] Error leyendo contexto de sesión | session_id=%s",
                session.id if session else False,
            )

        return {}

    def _write_session_context_safe(self, session, context):
        """Guarda el contexto de sesión de forma segura."""
        if not session or not isinstance(context, dict):
            return False

        try:
            session.set_context(context)
            return True
        except Exception:
            _logger.exception(
                "[WA-HUMAN] Error guardando contexto de sesión | session_id=%s keys=%s",
                session.id if session else False,
                list(context.keys()) if isinstance(context, dict) else [],
            )
            return False

    def _clear_human_confirmation_pending(self, session, clear_unknown=False):
        """Limpia solo las claves usadas por la confirmación humana."""
        if not session:
            return False

        context = self._get_session_context_safe(session)

        for key in (
            "pending_human_confirmation",
            "human_confirmation_message",
            "human_confirmation_reason",
            "human_confirmation_intent",
        ):
            context.pop(key, None)

        if clear_unknown:
            context.pop("unknown_attempts", None)
            context.pop("last_unknown_message", None)

        saved = self._write_session_context_safe(session, context)

        _logger.info(
            "[WA-HUMAN] Confirmación humana limpiada | session_id=%s clear_unknown=%s saved=%s",
            session.id if session else False,
            clear_unknown,
            saved,
        )
        return saved

    def _activate_human_handoff(
        self,
        partner,
        session=False,
        initial_message=False,
        reason=False,
        intent_result=None,
    ):
        """
        Activa de forma consistente el handoff humano y evita duplicados activos.
        """
        intent_result = intent_result if isinstance(intent_result, dict) else {}
        Handoff = request.env["whatsapp.handoff"].sudo()
        handoff = Handoff

        try:
            domain = [
                ("partner_id", "=", partner.id if partner else False),
                ("state", "in", ["pending", "assigned", "open", "escalated"]),
            ]
            if session:
                domain.append(("session_id", "=", session.id))

            handoff = Handoff.search(domain, order="id desc", limit=1)

            if handoff:
                _logger.info(
                    "[WA-HUMAN] Reutilizando handoff activo | handoff_id=%s partner_id=%s session_id=%s state=%s",
                    handoff.id,
                    partner.id if partner else False,
                    session.id if session else False,
                    handoff.state,
                )
            else:
                handoff = Handoff.create_unknown_intent_handoff(
                    partner,
                    session=session,
                    initial_message=initial_message,
                    context={
                        "reason": reason or "Cliente confirmó atención humana.",
                        "intent_result": intent_result,
                        "confirmed_by_customer": True,
                    },
                )
                _logger.info(
                    "[WA-HUMAN] Handoff creado | handoff_id=%s partner_id=%s session_id=%s",
                    handoff.id if handoff else False,
                    partner.id if partner else False,
                    session.id if session else False,
                )
        except Exception:
            handoff = Handoff
            _logger.exception(
                "[WA-HUMAN] Error creando/reutilizando handoff | partner_id=%s session_id=%s",
                partner.id if partner else False,
                session.id if session else False,
            )

        if partner:
            try:
                partner.whatsapp_enable_human_mode_api(
                    taken_by_name="Bot WhatsApp"
                )
                _logger.info(
                    "[WA-HUMAN] Partner puesto en modo humano | partner_id=%s human_mode=%s",
                    partner.id,
                    bool(getattr(partner, "whatsapp_human_mode", False)),
                )
            except Exception:
                _logger.exception(
                    "[WA-HUMAN] Error activando modo humano en partner | partner_id=%s",
                    partner.id,
                )

        if session:
            try:
                session.action_set_human()
                _logger.info(
                    "[WA-HUMAN] Sesión puesta en modo humano | session_id=%s state=%s",
                    session.id,
                    session.state,
                )
            except Exception:
                _logger.exception(
                    "[WA-HUMAN] Error poniendo sesión en modo humano | session_id=%s",
                    session.id,
                )

        return handoff if handoff else False

    # ==========================================================
    # Helpers: disponibilidad según horario
    # ==========================================================
    def _is_realtime_attention_unavailable(self, business_status):
        """
        Devuelve True cuando no existe atención en tiempo real.

        Se considera no disponible:
        - refrigerio;
        - fuera de horario;
        - día no laboral;
        - feriado/cierre manual;
        - cualquier estado calendario que indique is_open=False.

        Esto NO bloquea el registro de solicitudes que pueden quedar
        pendientes, como tóner o servicio técnico presencial.
        """
        business_status = business_status or {}
        return not bool(business_status.get("is_open"))

    def _is_navigation_command_safe(self, message):
        """
        Detecta comandos de navegación sin depender del estado del flujo.

        Se usa en /process para permitir navegación incluso cuando el flujo
        remoto está bloqueado por horario. Si WhatsAppFlowMixin expone sus
        helpers, se reutilizan; si no, existe fallback local compatible.
        """
        message = str(message or "").strip()

        try:
            if hasattr(self, "_is_flow_menu_command") and self._is_flow_menu_command(message):
                return True
        except Exception:
            pass

        try:
            if hasattr(self, "_is_flow_back_command") and self._is_flow_back_command(message):
                return True
        except Exception:
            pass

        try:
            if hasattr(self, "_is_flow_cancel_command") and self._is_flow_cancel_command(message):
                return True
        except Exception:
            pass

        normalized = message.strip().lower()

        return normalized in {
            "menu",
            "menú",
            "inicio",
            "opciones",
            "ayuda",
            "atras",
            "atrás",
            "volver",
            "regresar",
            "retroceder",
            "cancelar",
            "salir",
            "terminar",
            "anular",
        }

    def _get_realtime_blocked_intent(self, intent_result):
        """
        Indica si una intención requiere atención humana en tiempo real.

        Política:
        - remote_service / flujo remote: requiere técnico disponible.
        - human / handoff: requiere atención humana disponible.
        - tóner, servicio presencial y empresa NO se bloquean aquí.
        """
        intent_result = intent_result or {}

        intent = str(intent_result.get("intent") or "").strip().lower()
        action = str(intent_result.get("action") or "").strip().lower()
        target_flow = str(intent_result.get("target_flow") or "").strip().lower()

        if (
            intent == "human"
            or action == "handoff"
        ):
            return "human"

        if (
            intent == "remote_service"
            or action == "start_flow_remote"
            or target_flow == "remote"
        ):
            return "remote"

        return False

    def _render_realtime_unavailable(
        self,
        blocked_type,
        partner,
        session,
        business_status,
    ):
        """
        Renderiza una respuesta profesional para acciones que requieren
        atención en tiempo real y no están disponibles por horario.
        """
        business_status = business_status or {}
        reason = business_status.get("reason") or "after_hours"

        extra = {
            "business_reason": business_status.get("reason_label") or reason,
            "business_message": business_status.get("message") or "",
            "display_hours": business_status.get("display_hours") or "",
        }

        if blocked_type == "remote":
            return self._render_template(
                "remote_unavailable",
                partner=partner,
                session=session,
                extra=extra,
                fallback=(
                    "💻 *Asistencia remota*\n\n"
                    "En este momento la asistencia remota no se encuentra "
                    "disponible. Puedes registrar un servicio técnico y "
                    "nuestro equipo continuará la atención al retomar el "
                    "horario correspondiente.\n\n"
                    "Escribe *MENU* para volver al menú principal."
                ),
            )

        return self._render_template(
            "human_unavailable",
            partner=partner,
            session=session,
            extra=extra,
            fallback=(
                "👨‍💼 *Atención directa con un técnico*\n\n"
                "En este momento la atención directa con nuestro equipo "
                "técnico no se encuentra disponible. Puedes registrar una "
                "solicitud de tóner o servicio técnico para ser atendida "
                "al retomar el horario correspondiente.\n\n"
                "Escribe *MENU* para volver al menú principal."
            ),
        )

    def _emit_realtime_unavailable_response(
        self,
        endpoint,
        payload,
        identifiers,
        start_ts,
        partner,
        session,
        business_status,
        blocked_type,
        intent_result=False,
    ):
        """
        Emite una respuesta estándar cuando una intención de atención
        en tiempo real está bloqueada por horario.
        """
        reply = self._render_realtime_unavailable(
            blocked_type=blocked_type,
            partner=partner,
            session=session,
            business_status=business_status,
        )

        intent_name = (
            "remote_service"
            if blocked_type == "remote"
            else "human"
        )

        template_name = (
            "remote_unavailable"
            if blocked_type == "remote"
            else "human_unavailable"
        )

        emitted = self._emit_bot_reply(
            session=session,
            partner=partner,
            identifiers=identifiers,
            content=reply,
            intent=intent_name,
            payload=payload,
            template=template_name,
        )

        response = {
            "ok": True,
            "found": True,
            "availability_blocked": True,
            "blocked_service": blocked_type,
            "human_mode": False,
            "bot_reply": True,
            "stop_bot": False,
            "partner_id": partner.id if partner else False,
            "session_id": session.id if session else False,
            "message": reply,
            "outbox_id": emitted.get("outbox_id"),
            "business": business_status,
            "intent": intent_result or False,
            "profile": (
                partner.get_whatsapp_profile_payload()
                if partner
                else False
            ),
        }

        _logger.info(
            "[WA-HOURS] Acción bloqueada por disponibilidad | "
            "partner_id=%s session_id=%s blocked_service=%s "
            "reason=%s outbox_id=%s",
            partner.id if partner else False,
            session.id if session else False,
            blocked_type,
            (business_status or {}).get("reason") or False,
            emitted.get("outbox_id"),
        )

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
    # Proceso principal
    # ==========================================================
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
            "[WA-PROCESS] Mensaje entrante registrado | "
            "message_id=%s partner_id=%s session_id=%s "
            "external_message_id=%s business_reason=%s business_open=%s",
            incoming_message.id if incoming_message else False,
            partner.id if partner else False,
            session.id if session else False,
            external_message_id or False,
            business_status.get("reason") if business_status else False,
            business_status.get("is_open") if business_status else False,
        )

        # ======================================================
        # 5) Idempotencia del mensaje entrante
        # ======================================================
        duplicate_message = bool(
            incoming_message
            and incoming_message.env.context.get(
                "wa_duplicate_message"
            )
        )

        if duplicate_message:
            _logger.warning(
                "[WA-PROCESS] Mensaje duplicado detenido antes de negocio | "
                "message_id=%s external_message_id=%s "
                "partner_id=%s session_id=%s processing_status=%s",
                incoming_message.id,
                external_message_id or False,
                partner.id if partner else False,
                session.id if session else False,
                getattr(
                    incoming_message,
                    "processing_status",
                    False,
                ),
            )

            response = {
                "ok": True,
                "found": True,
                "duplicate": True,
                "ignored": True,
                "bot_reply": False,
                "stop_bot": False,
                "message_id": incoming_message.id,
                "external_message_id": (
                    incoming_message.external_message_id
                    or external_message_id
                    or False
                ),
                "processing_status": getattr(
                    incoming_message,
                    "processing_status",
                    False,
                ),
                "partner_id": partner.id,
                "session_id": session.id,
                "message": False,
                "outbox_id": False,
                "business": business_status,
                "profile": (
                    partner.get_whatsapp_profile_payload()
                ),
            }

            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                partner=partner,
                session=session,
                status="duplicate",
                start_ts=start_ts,
            )

            return response

        # ======================================================
        # 6) Contacto bloqueado
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
        # 7) Modo humano activo
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
        # 8) Registro DNI/RUC pendiente
        # ======================================================
        registration_state = (
            getattr(partner, "whatsapp_registration_state", "none")
            or "none"
        )

        _logger.info(
            "[WA-PROCESS] Estado registro inicial | partner_id=%s registration_state=%s vat=%s active_company=%s company_count=%s",
            partner.id if partner else False,
            registration_state,
            getattr(partner, "vat", False),
            partner.whatsapp_active_company_id.id if partner and partner.whatsapp_active_company_id else False,
            len(partner.whatsapp_company_ids) if partner and partner.whatsapp_company_ids else 0,
        )

        registration_state = self._ensure_existing_partner_whatsapp_registration(
            partner,
            session=session,
        )

        _logger.info(
            "[WA-PROCESS] Estado registro corregido | partner_id=%s registration_state=%s",
            partner.id if partner else False,
            registration_state,
        )

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
            companies = self._get_partner_whatsapp_companies_safe(partner)
            has_company = bool(partner.whatsapp_active_company_id or companies)

            if has_company:
                selected_company = partner.whatsapp_active_company_id

                if not selected_company and companies and len(companies) == 1:
                    selected_company = companies[0]

                try:
                    vals = {
                        "whatsapp_registration_state": "registered",
                    }

                    if selected_company and not partner.whatsapp_active_company_id:
                        vals["whatsapp_active_company_id"] = selected_company.id

                    partner.sudo().write(vals)

                    if session and selected_company:
                        session.sudo().write({
                            "active_company_id": selected_company.id,
                        })

                except Exception:
                    _logger.exception(
                        "[WA-PROCESS] Error marcando registered a partner con empresa existente | partner_id=%s",
                        partner.id if partner else False,
                    )

                registration_state = "registered"

                _logger.info(
                    "[WA-PROCESS] Partner ya tenía empresa. No se pide RUC | partner_id=%s company_id=%s companies=%s",
                    partner.id if partner else False,
                    selected_company.id if selected_company else False,
                    len(companies) if companies else 0,
                )

            else:
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
        # 9) Selección de empresa pendiente
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
        # 10) Confirmación pendiente de atención humana
        # ======================================================
        session_context = self._get_session_context_safe(session)
        pending_human_confirmation = bool(
            session_context.get("pending_human_confirmation")
        )

        if pending_human_confirmation:
            _logger.info(
                "[WA-HUMAN] Respuesta a confirmación pendiente | partner_id=%s session_id=%s message=%r",
                partner.id if partner else False,
                session.id if session else False,
                message_text[:160] if message_text else "",
            )

            if self._is_yes(message_text):
                if self._is_realtime_attention_unavailable(business_status):
                    self._clear_human_confirmation_pending(
                        session,
                        clear_unknown=True,
                    )

                    _logger.info(
                        "[WA-HUMAN] Confirmación SÍ bloqueada por horario | "
                        "partner_id=%s session_id=%s reason=%s",
                        partner.id if partner else False,
                        session.id if session else False,
                        (business_status or {}).get("reason") or False,
                    )

                    return self._emit_realtime_unavailable_response(
                        endpoint=endpoint,
                        payload=payload,
                        identifiers=identifiers,
                        start_ts=start_ts,
                        partner=partner,
                        session=session,
                        business_status=business_status,
                        blocked_type="human",
                        intent_result={
                            "found": True,
                            "intent": "human",
                            "action": "handoff",
                            "target_flow": "none",
                            "source": "pending_confirmation",
                        },
                    )

                original_message = (
                    session_context.get("human_confirmation_message")
                    or message_text
                )
                reason = (
                    session_context.get("human_confirmation_reason")
                    or "Cliente confirmó atención humana."
                )
                intent_result_context = (
                    session_context.get("human_confirmation_intent")
                    if isinstance(session_context.get("human_confirmation_intent"), dict)
                    else {}
                )

                handoff = self._activate_human_handoff(
                    partner=partner,
                    session=session,
                    initial_message=original_message,
                    reason=reason,
                    intent_result=intent_result_context,
                )

                reply = self._render_template(
                    "human_take",
                    partner=partner,
                    session=session,
                    fallback=(
                        "👨‍💼 Listo. Te derivé con un asesor de "
                        "*ANDES SOLUTION COPIERS*. Por favor espera un momento."
                    ),
                )

                emitted = self._emit_bot_reply(
                    session=session,
                    partner=partner,
                    identifiers=identifiers,
                    content=reply,
                    intent="human",
                    payload=payload,
                    template="human_take",
                )

                response = {
                    "ok": True,
                    "found": True,
                    "human_mode": True,
                    "bot_reply": True,
                    "stop_bot": True,
                    "handoff_created": bool(handoff),
                    "handoff_id": handoff.id if handoff else False,
                    "partner_id": partner.id,
                    "session_id": session.id,
                    "message": reply,
                    "outbox_id": emitted.get("outbox_id"),
                    "business": business_status,
                    "profile": partner.get_whatsapp_profile_payload(),
                }

                _logger.info(
                    "[WA-HUMAN] Confirmación SÍ procesada | partner_id=%s session_id=%s handoff_id=%s human_mode=%s outbox_id=%s",
                    partner.id if partner else False,
                    session.id if session else False,
                    handoff.id if handoff else False,
                    bool(getattr(partner, "whatsapp_human_mode", False)),
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

            if self._is_no(message_text):
                self._clear_human_confirmation_pending(
                    session,
                    clear_unknown=True,
                )

                reply = (
                    "Perfecto, continuamos con el asistente virtual.\n\n"
                    + self._build_main_menu_text(partner=partner, session=session)
                )

                emitted = self._emit_bot_reply(
                    session=session,
                    partner=partner,
                    identifiers=identifiers,
                    content=reply,
                    intent="human_declined",
                    payload=payload,
                )

                response = {
                    "ok": True,
                    "found": True,
                    "human_mode": False,
                    "bot_reply": True,
                    "stop_bot": False,
                    "human_declined": True,
                    "partner_id": partner.id,
                    "session_id": session.id,
                    "message": reply,
                    "outbox_id": emitted.get("outbox_id"),
                    "business": business_status,
                    "profile": partner.get_whatsapp_profile_payload(),
                }

                _logger.info(
                    "[WA-HUMAN] Confirmación NO procesada | partner_id=%s session_id=%s outbox_id=%s",
                    partner.id if partner else False,
                    session.id if session else False,
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

            # Si el cliente respondió otra cosa, no lo bloqueamos en un sí/no.
            # Se cancela la confirmación y el mensaje actual continúa por la
            # detección normal de intención.
            self._clear_human_confirmation_pending(
                session,
                clear_unknown=False,
            )
            _logger.info(
                "[WA-HUMAN] Respuesta distinta de SÍ/NO; se continúa con clasificación normal | partner_id=%s session_id=%s",
                partner.id if partner else False,
                session.id if session else False,
            )

        # ======================================================
        # 11) Horario/refrigerio: informa, pero permite registrar
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
        # 12) Continuar flujo activo
        # ======================================================
        if session.current_flow != "none" and session.conversation_state != "idle":
            navigation_command = self._is_navigation_command_safe(message_text)

            if (
                session.current_flow == "remote"
                and self._is_realtime_attention_unavailable(business_status)
                and not navigation_command
            ):
                _logger.info(
                    "[WA-HOURS] Flujo remoto activo detenido por disponibilidad | "
                    "partner_id=%s session_id=%s step=%s reason=%s",
                    partner.id if partner else False,
                    session.id if session else False,
                    session.conversation_state,
                    (business_status or {}).get("reason") or False,
                )

                try:
                    session.reset_conversation(
                        reason="remote_unavailable_by_business_hours"
                    )
                except Exception:
                    _logger.exception(
                        "[WA-HOURS] No se pudo resetear flujo remoto bloqueado | "
                        "session_id=%s",
                        session.id if session else False,
                    )

                return self._emit_realtime_unavailable_response(
                    endpoint=endpoint,
                    payload=payload,
                    identifiers=identifiers,
                    start_ts=start_ts,
                    partner=partner,
                    session=session,
                    business_status=business_status,
                    blocked_type="remote",
                    intent_result={
                        "found": True,
                        "intent": "remote_service",
                        "action": "start_flow_remote",
                        "target_flow": "remote",
                        "source": "active_flow",
                    },
                )

            if (
                session.current_flow == "remote"
                and self._is_realtime_attention_unavailable(business_status)
                and navigation_command
            ):
                _logger.info(
                    "[WA-NAV] Navegación permitida en flujo remoto fuera de horario | "
                    "partner_id=%s session_id=%s step=%s command=%r",
                    partner.id if partner else False,
                    session.id if session else False,
                    session.conversation_state,
                    message_text,
                )

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

            current_human_mode = bool(
                getattr(partner, "whatsapp_human_mode", False)
            )

            response = {
                "ok": True,
                "found": True,
                "continued_flow": True,
                "flow": session.current_flow,
                "step": session.conversation_state,
                "human_mode": current_human_mode,
                "bot_reply": bool(reply),
                "stop_bot": current_human_mode,
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
        # 13) Detectar intención y ejecutar acción
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

        # La clasificación funcional del contacto ya no depende de is_open.
        # _get_applies_to() distingue new/registered/blocked/human, mientras
        # business_status conserva el horario REAL para reglas
        # only_business_hours / only_after_hours.
        intent_result, applies_to = self._detect_intent(
            message_text,
            partner=partner if partner else False,
            business_status=business_status,
            session=session if session else False,
            payload=payload,
        )

        intent_result = intent_result or {"found": False}

        _logger.info(
            "[WA-HOURS] Intención detectada antes de validar disponibilidad | "
            "partner_id=%s session_id=%s applies_to=%s intent=%s action=%s "
            "target_flow=%s business_reason=%s business_is_open=%s",
            partner.id if partner else False,
            session.id if session else False,
            applies_to,
            intent_result.get("intent") or False,
            intent_result.get("action") or False,
            intent_result.get("target_flow") or False,
            (business_status or {}).get("reason") or False,
            bool((business_status or {}).get("is_open")),
        )

        blocked_type = False
        if self._is_realtime_attention_unavailable(business_status):
            blocked_type = self._get_realtime_blocked_intent(intent_result)

        if blocked_type:
            return self._emit_realtime_unavailable_response(
                endpoint=endpoint,
                payload=payload,
                identifiers=identifiers,
                start_ts=start_ts,
                partner=partner,
                session=session,
                business_status=business_status,
                blocked_type=blocked_type,
                intent_result=intent_result,
            )

        # ======================================================
        # IMPORTANTE:
        # _execute_intent_action está definido como:
        #   _execute_intent_action(result, partner, session, identifiers,
        #                          payload=False, business_status=None)
        #
        # Por eso el primer argumento debe ser intent_result.
        # Además esta función devuelve un dict, no texto directo.
        # ======================================================
        action_result = self._execute_intent_action(
            intent_result,
            partner,
            session,
            identifiers,
            payload=payload,
            business_status=business_status,
        )

        action_result = action_result or {}

        reply = action_result.get("content") or ""

        if outside_hours_note and reply:
            action_template = (
                action_result.get("template")
                or intent_result.get("response_template")
                or False
            )
            if action_template not in (
                "remote_unavailable",
                "human_unavailable",
                "in_break",
                "after_hours",
            ):
                reply = "%s\n\n%s" % (outside_hours_note, reply)

        if not reply:
            current_human_mode = bool(
                action_result.get("human_mode")
                or getattr(partner, "whatsapp_human_mode", False)
            )

            response = {
                "ok": True,
                "found": False,
                "ignored": True,
                "applies_to": applies_to,
                "intent": intent_result,
                "action": action_result,
                "human_mode": current_human_mode,
                "bot_reply": False,
                "stop_bot": bool(action_result.get("stop_bot") or current_human_mode),
                "handoff_id": action_result.get("handoff_id") or False,
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
            intent=action_result.get("intent") or intent_result.get("intent") or "unknown",
            payload=payload,
            template=action_result.get("template") or intent_result.get("response_template") or False,
        )

        current_human_mode = bool(
            action_result.get("human_mode")
            or getattr(partner, "whatsapp_human_mode", False)
        )

        response = {
            "ok": True,
            "found": bool(intent_result.get("found")),
            "applies_to": applies_to,
            "intent": intent_result,
            "action": action_result,
            "human_mode": current_human_mode,
            "bot_reply": bool(reply),
            "stop_bot": bool(action_result.get("stop_bot") or current_human_mode),
            "handoff_id": action_result.get("handoff_id") or False,
            "pending_human_confirmation": bool(
                action_result.get("pending_human_confirmation")
            ),
            "partner_id": partner.id,
            "session_id": session.id,
            "message": reply,
            "outbox_id": emitted.get("outbox_id"),
            "business": business_status,
            "profile": partner.get_whatsapp_profile_payload(),
        }

        _logger.info(
            "[WA-PROCESS] Respuesta final emitida | partner_id=%s session_id=%s intent=%s action=%s human_mode=%s pending_human_confirmation=%s stop_bot=%s outbox_id=%s",
            partner.id if partner else False,
            session.id if session else False,
            action_result.get("intent") or intent_result.get("intent") or False,
            action_result.get("action") or intent_result.get("action") or False,
            current_human_mode,
            bool(action_result.get("pending_human_confirmation")),
            bool(action_result.get("stop_bot") or current_human_mode),
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