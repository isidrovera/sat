# -*- coding: utf-8 -*-

import logging

from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppFlowMixin:
    """
    Navegación global y continuación de flujos activos.

    Este mixin no crea solicitudes ni tickets por sí mismo.
    Su responsabilidad es:

    - Permitir cancelar un flujo activo.
    - Volver al menú principal.
    - Regresar un paso mediante ATRÁS / VOLVER / REGRESAR.
    - Delegar la continuación al mixin específico:
      toner / onsite / remote / registration.

    La lógica específica de negocio permanece en cada flujo.
    """

    # ==========================================================
    # Normalización de comandos globales
    # ==========================================================
    def _normalize_flow_command(self, text):
        """
        Normaliza únicamente comandos de navegación.

        No se utiliza como normalizador general de intención.
        """
        return (text or "").strip().lower()

    def _is_flow_cancel_command(self, text):
        command = self._normalize_flow_command(text)
        return command in {
            "cancelar",
            "cancela",
            "salir",
            "terminar",
            "anular",
        }

    def _is_flow_menu_command(self, text):
        command = self._normalize_flow_command(text)
        return command in {
            "menu",
            "menú",
            "inicio",
            "opciones",
            "ayuda",
        }

    def _is_flow_back_command(self, text):
        command = self._normalize_flow_command(text)
        return command in {
            "atras",
            "atrás",
            "volver",
            "regresar",
            "retroceder",
        }

    # ==========================================================
    # Contexto de flujo
    # ==========================================================
    def _get_flow_context_safe(self, session):
        if not session:
            return {}

        try:
            context = session.get_context()
            return context if isinstance(context, dict) else {}
        except Exception:
            _logger.exception(
                "[WA-FLOW] No se pudo leer contexto | session_id=%s",
                session.id if session else False,
            )
            return {}

    def _set_flow_context_safe(self, session, context):
        if not session or not isinstance(context, dict):
            return False

        try:
            session.set_context(context)
            return True
        except Exception:
            _logger.exception(
                "[WA-FLOW] No se pudo guardar contexto | session_id=%s keys=%s",
                session.id if session else False,
                list(context.keys()) if isinstance(context, dict) else [],
            )
            return False

    def _clean_flow_context_keys(self, session, keys):
        """
        Elimina únicamente claves posteriores al paso al que se está
        retrocediendo. No borra la información base del flujo.
        """
        context = self._get_flow_context_safe(session)

        removed = []

        for key in keys:
            if key in context:
                removed.append(key)
            context.pop(key, None)

        saved = self._set_flow_context_safe(session, context)

        _logger.debug(
            "[WA-FLOW] Contexto limpiado para retroceso | "
            "session_id=%s removed=%s saved=%s remaining_keys=%s",
            session.id if session else False,
            removed,
            saved,
            sorted(context.keys()),
        )

        return context

    # ==========================================================
    # Mensajes estándar de navegación
    # ==========================================================
    def _flow_navigation_footer(self, include_back=True):
        parts = []

        if include_back:
            parts.append("↩️ Escribe *ATRÁS* para regresar al paso anterior.")

        parts.append("🏠 Escribe *MENU* o *AYUDA* para volver al menú principal.")
        parts.append("❌ Escribe *CANCELAR* para cancelar la operación.")

        return "\n".join(parts)

    def _flow_cancel_reply(self, partner=False, session=False):
        """
        Usa plantilla si existe. Mantiene fallback seguro.
        """
        return self._render_template(
            "cancel_flow_reply",
            partner=partner,
            session=session,
            fallback=(
                "✅ *Operación cancelada*\n\n"
                "La gestión en curso fue cancelada correctamente.\n\n"
                "Escribe *MENU* o *AYUDA* para volver al menú principal."
            ),
        )

    def _flow_back_intro(self, partner=False, session=False):
        """
        Plantilla breve reutilizable antes de la instrucción específica.
        """
        return self._render_template(
            "back_step",
            partner=partner,
            session=session,
            fallback="↩️ *Regresamos al paso anterior*",
        )

    def _get_flow_machine_safe(self, session, context=None):
        """
        Recupera el equipo almacenado en conversation_context sin permitir
        que un machine_id inválido rompa el comando ATRÁS.
        """
        context = (
            context
            if isinstance(context, dict)
            else self._get_flow_context_safe(session)
        )

        machine_id = context.get("machine_id")

        if not machine_id:
            return request.env["alquiler"].sudo()

        try:
            machine_id = int(machine_id)
        except Exception:
            _logger.warning(
                "[WA-FLOW] machine_id inválido en contexto | "
                "session_id=%s machine_id=%r",
                session.id if session else False,
                machine_id,
            )
            return request.env["alquiler"].sudo()

        return (
            request.env["alquiler"]
            .sudo()
            .browse(machine_id)
            .exists()
        )

    # ==========================================================
    # ATRÁS: registro / empresa
    # ==========================================================
    def _go_back_registration_flow(self, partner, session, identifiers, step):
        """
        En selección de empresa no existe un paso anterior útil dentro
        del mismo flujo. Regresar equivale a volver al menú principal.
        """
        _logger.info(
            "[WA-FLOW] ATRÁS registration | partner_id=%s session_id=%s step=%s",
            partner.id if partner else False,
            session.id if session else False,
            step,
        )

        session.reset_conversation(reason="back_from_registration")

        return self._build_main_menu_text(
            partner=partner,
            session=session,
        )

    # ==========================================================
    # ATRÁS: flujo tóner
    # ==========================================================
    def _go_back_toner_flow(self, partner, session, identifiers, step, payload=False):
        context = self._get_flow_context_safe(session)

        # ------------------------------------------------------
        # Primer paso: volver al menú principal
        # ------------------------------------------------------
        if step == "awaiting_machine_selection_toner":
            session.reset_conversation(reason="back_from_toner_start")

            _logger.info(
                "[WA-FLOW] ATRÁS tóner -> menú | partner_id=%s session_id=%s",
                partner.id if partner else False,
                session.id if session else False,
            )

            return self._build_main_menu_text(
                partner=partner,
                session=session,
            )

        # ------------------------------------------------------
        # Color -> selección de equipo
        # ------------------------------------------------------
        if step == "awaiting_toner_color":
            _logger.info(
                "[WA-FLOW] ATRÁS tóner | session_id=%s from=%s to=awaiting_machine_selection_toner",
                session.id if session else False,
                step,
            )

            return self._start_toner_flow(
                partner,
                session,
                identifiers,
                payload=payload,
            )

        # ------------------------------------------------------
        # Cantidad -> color, excepto monocromático
        # ------------------------------------------------------
        if step == "awaiting_toner_quantity":
            machine_is_color = bool(context.get("machine_is_color"))

            self._clean_flow_context_keys(
                session,
                [
                    "toner_quantity",
                    "counter_bn",
                    "counter_color",
                    "counter_source",
                    "counter_recent",
                    "counter_recent_reason",
                    "observations",
                ],
            )

            if machine_is_color:
                session.advance_state("awaiting_toner_color")

                machine = self._get_flow_machine_safe(
                    session,
                    context=context,
                )

                if machine:
                    color_menu = self._toner_build_color_menu(machine)
                    options = color_menu.get("options") or []

                    context = self._get_flow_context_safe(session)
                    context["toner_color_options"] = options
                    context.pop("toner_color", None)
                    context.pop("toner_colors", None)
                    context.pop("toner_color_label", None)
                    self._set_flow_context_safe(session, context)

                    return (
                        "%s\n\n"
                        "🎨 *Selecciona nuevamente el tóner o color*\n\n"
                        "%s\n\n"
                        "%s"
                    ) % (
                        self._flow_back_intro(partner, session),
                        color_menu.get("menu_text")
                        or "Selecciona una de las opciones disponibles.",
                        self._flow_navigation_footer(include_back=True),
                    )

            # En una máquina monocromática el color se seleccionó
            # automáticamente; volver un paso significa elegir equipo.
            return self._start_toner_flow(
                partner,
                session,
                identifiers,
                payload=payload,
            )

        # ------------------------------------------------------
        # Contador B/N -> cantidad
        # ------------------------------------------------------
        if step == "awaiting_toner_counter_bn":
            self._clean_flow_context_keys(
                session,
                [
                    "counter_bn",
                    "counter_color",
                    "counter_source",
                    "counter_recent",
                    "counter_recent_reason",
                    "observations",
                ],
            )
            session.advance_state("awaiting_toner_quantity")

            return (
                "%s\n\n"
                "🔢 *Cantidad de tóner*\n\n"
                "Indica nuevamente cuántos tóner necesitas.\n\n"
                "%s"
            ) % (
                self._flow_back_intro(partner, session),
                self._flow_navigation_footer(include_back=True),
            )

        # ------------------------------------------------------
        # Contador color -> contador B/N
        # ------------------------------------------------------
        if step == "awaiting_toner_counter_color":
            self._clean_flow_context_keys(
                session,
                [
                    "counter_bn",
                    "counter_color",
                    "counter_source",
                    "observations",
                ],
            )
            session.advance_state("awaiting_toner_counter_bn")

            return (
                "%s\n\n"
                "🧮 *Contador B/N*\n\n"
                "Envía nuevamente el contador B/N actual del equipo.\n\n"
                "%s"
            ) % (
                self._flow_back_intro(partner, session),
                self._flow_navigation_footer(include_back=True),
            )

        # ------------------------------------------------------
        # Observaciones -> último paso real antes de observaciones
        # ------------------------------------------------------
        if step == "awaiting_toner_observations":
            machine = self._get_flow_machine_safe(
                session,
                context=context,
            )

            counter_recent = bool(context.get("counter_recent"))

            self._clean_flow_context_keys(
                session,
                ["observations"],
            )

            # Si los contadores fueron obtenidos automáticamente,
            # el paso anterior real fue cantidad.
            if counter_recent:
                session.advance_state("awaiting_toner_quantity")

                return (
                    "%s\n\n"
                    "🔢 *Cantidad de tóner*\n\n"
                    "Indica nuevamente cuántos tóner necesitas.\n\n"
                    "%s"
                ) % (
                    self._flow_back_intro(partner, session),
                    self._flow_navigation_footer(include_back=True),
                )

            # Si fueron manuales, regresar al último contador requerido.
            is_color = False
            try:
                if machine:
                    is_color = bool(self._toner_is_color_machine(machine))
            except Exception:
                is_color = bool(context.get("machine_is_color"))

            if is_color:
                self._clean_flow_context_keys(
                    session,
                    ["counter_color"],
                )
                session.advance_state("awaiting_toner_counter_color")

                return (
                    "%s\n\n"
                    "🎨 *Contador color*\n\n"
                    "Envía nuevamente el contador color actual del equipo.\n\n"
                    "%s"
                ) % (
                    self._flow_back_intro(partner, session),
                    self._flow_navigation_footer(include_back=True),
                )

            self._clean_flow_context_keys(
                session,
                ["counter_bn"],
            )
            session.advance_state("awaiting_toner_counter_bn")

            return (
                "%s\n\n"
                "🧮 *Contador B/N*\n\n"
                "Envía nuevamente el contador B/N actual del equipo.\n\n"
                "%s"
            ) % (
                self._flow_back_intro(partner, session),
                self._flow_navigation_footer(include_back=True),
            )

        # ------------------------------------------------------
        # Confirmación -> observaciones
        # ------------------------------------------------------
        if step == "awaiting_toner_confirmation":
            self._clean_flow_context_keys(
                session,
                ["observations"],
            )
            session.advance_state("awaiting_toner_observations")

            return (
                "%s\n\n"
                "📝 *Observaciones*\n\n"
                "Puedes modificar o agregar una observación.\n"
                "Si no deseas agregar ninguna, escribe *NO*.\n\n"
                "%s"
            ) % (
                self._flow_back_intro(partner, session),
                self._flow_navigation_footer(include_back=True),
            )

        _logger.warning(
            "[WA-FLOW] ATRÁS tóner sin mapa | session_id=%s step=%s",
            session.id if session else False,
            step,
        )

        session.reset_conversation(reason="back_unknown_toner_step")

        return self._build_main_menu_text(
            partner=partner,
            session=session,
        )

    # ==========================================================
    # ATRÁS: servicio presencial
    # ==========================================================
    def _go_back_onsite_flow(self, partner, session, identifiers, step, payload=False):
        # Primer paso -> menú
        if step == "awaiting_machine_selection_onsite":
            session.reset_conversation(reason="back_from_onsite_start")

            return self._build_main_menu_text(
                partner=partner,
                session=session,
            )

        # Descripción -> selección de equipo
        if step == "awaiting_service_description":
            _logger.info(
                "[WA-FLOW] ATRÁS onsite | session_id=%s from=%s to=awaiting_machine_selection_onsite",
                session.id if session else False,
                step,
            )

            return self._start_onsite_flow(
                partner,
                session,
                identifiers,
                payload=payload,
            )

        # Foto -> descripción
        if step == "awaiting_service_photo":
            self._clean_flow_context_keys(
                session,
                [
                    "service_description",
                    "media_id",
                ],
            )
            session.advance_state("awaiting_service_description")

            return (
                "%s\n\n"
                "🛠️ *Descripción del problema*\n\n"
                "Describe nuevamente, de forma breve, el problema que presenta el equipo.\n\n"
                "%s"
            ) % (
                self._flow_back_intro(partner, session),
                self._flow_navigation_footer(include_back=True),
            )

        _logger.warning(
            "[WA-FLOW] ATRÁS onsite sin mapa | session_id=%s step=%s",
            session.id if session else False,
            step,
        )

        session.reset_conversation(reason="back_unknown_onsite_step")

        return self._build_main_menu_text(
            partner=partner,
            session=session,
        )

    # ==========================================================
    # ATRÁS: asistencia remota
    # ==========================================================
    def _go_back_remote_flow(self, partner, session, identifiers, step, payload=False):
        # Primer paso -> menú
        if step == "awaiting_anydesk_code":
            session.reset_conversation(reason="back_from_remote_start")

            return self._build_main_menu_text(
                partner=partner,
                session=session,
            )

        # Problema -> código AnyDesk
        if step == "awaiting_remote_problem":
            self._clean_flow_context_keys(
                session,
                [
                    "anydesk_code",
                    "remote_problem",
                ],
            )
            session.advance_state("awaiting_anydesk_code")

            return self._render_template(
                "ask_anydesk_code",
                partner=partner,
                session=session,
                fallback=(
                    "%s\n\n"
                    "💻 *Asistencia remota · Código AnyDesk*\n\n"
                    "Envía nuevamente el código AnyDesk, entre 6 y 12 dígitos.\n\n"
                    "%s"
                ) % (
                    self._flow_back_intro(partner, session),
                    self._flow_navigation_footer(include_back=True),
                ),
            )

        _logger.warning(
            "[WA-FLOW] ATRÁS remote sin mapa | session_id=%s step=%s",
            session.id if session else False,
            step,
        )

        session.reset_conversation(reason="back_unknown_remote_step")

        return self._build_main_menu_text(
            partner=partner,
            session=session,
        )

    # ==========================================================
    # Ejecutar ATRÁS
    # ==========================================================
    def _go_back_active_flow(
        self,
        partner,
        session,
        identifiers,
        payload=False,
    ):
        if not session:
            return (
                "No pude encontrar una operación activa.\n\n"
                "Escribe *MENU* para ver las opciones disponibles."
            )

        flow = session.current_flow or "none"
        step = session.conversation_state or "idle"

        _logger.info(
            "[WA-FLOW] Comando ATRÁS | partner_id=%s session_id=%s flow=%s step=%s",
            partner.id if partner else False,
            session.id if session else False,
            flow,
            step,
        )

        if flow == "registration":
            return self._go_back_registration_flow(
                partner,
                session,
                identifiers,
                step,
            )

        if flow == "toner":
            return self._go_back_toner_flow(
                partner,
                session,
                identifiers,
                step,
                payload=payload,
            )

        if flow == "onsite":
            return self._go_back_onsite_flow(
                partner,
                session,
                identifiers,
                step,
                payload=payload,
            )

        if flow == "remote":
            return self._go_back_remote_flow(
                partner,
                session,
                identifiers,
                step,
                payload=payload,
            )

        # Para greeting, other o cualquier flujo desconocido,
        # regresar equivale a volver al menú principal.
        session.reset_conversation(reason="back_to_main_menu")

        return self._build_main_menu_text(
            partner=partner,
            session=session,
        )

    # ==========================================================
    # Continuar flujo activo
    # ==========================================================
    def _continue_active_flow(
        self,
        partner,
        session,
        identifiers,
        message_text,
        payload=False,
    ):
        """
        Punto único de entrada para cualquier mensaje mientras existe
        un flujo conversacional activo.

        Orden de prioridad:
        1. CANCELAR
        2. MENU / AYUDA
        3. ATRÁS / VOLVER / REGRESAR
        4. Continuación del flujo específico

        De este modo ningún flujo puede dejar al cliente atrapado.
        """
        if not session:
            return (
                "No pude encontrar una sesión activa.\n\n"
                "Escribe *MENU* para comenzar nuevamente."
            )

        flow = session.current_flow
        step = session.conversation_state

        _logger.info(
            "[WA-FLOW] Continuando flujo | "
            "partner_id=%s session_id=%s flow=%s step=%s message=%s",
            partner.id if partner else False,
            session.id if session else False,
            flow,
            step,
            (message_text or "")[:300],
        )

        # ======================================================
        # CANCELAR: prioridad global
        # ======================================================
        if self._is_flow_cancel_command(message_text):
            _logger.info(
                "[WA-FLOW] Comando CANCELAR | "
                "partner_id=%s session_id=%s flow=%s step=%s",
                partner.id if partner else False,
                session.id if session else False,
                flow,
                step,
            )

            session.reset_conversation(reason="cancelled_by_user")

            return self._flow_cancel_reply(
                partner=partner,
                session=session,
            )

        # ======================================================
        # MENU: prioridad global
        # ======================================================
        if self._is_flow_menu_command(message_text):
            _logger.info(
                "[WA-FLOW] Comando MENU/AYUDA | "
                "partner_id=%s session_id=%s flow=%s step=%s",
                partner.id if partner else False,
                session.id if session else False,
                flow,
                step,
            )

            session.reset_conversation(reason="menu_requested")

            return self._build_main_menu_text(
                partner=partner,
                session=session,
            )

        # ======================================================
        # ATRÁS: prioridad global
        # ======================================================
        if self._is_flow_back_command(message_text):
            return self._go_back_active_flow(
                partner=partner,
                session=session,
                identifiers=identifiers,
                payload=payload,
            )

        # ======================================================
        # Registro / selección de empresa
        # ======================================================
        if flow == "registration":
            if step == "awaiting_company_selection":
                return self._continue_company_selection(
                    partner,
                    session,
                    message_text,
                )

            _logger.warning(
                "[WA-FLOW] Paso registration no reconocido | "
                "partner_id=%s session_id=%s step=%s",
                partner.id if partner else False,
                session.id if session else False,
                step,
            )

            session.reset_conversation(
                reason="registration_unknown_step"
            )

            return self._build_main_menu_text(
                partner=partner,
                session=session,
            )

        # ======================================================
        # Tóner
        # ======================================================
        if flow == "toner":
            return self._continue_toner_flow(
                partner,
                session,
                identifiers,
                message_text,
                payload=payload,
            )

        # ======================================================
        # Servicio presencial
        # ======================================================
        if flow == "onsite":
            return self._continue_onsite_flow(
                partner,
                session,
                identifiers,
                message_text,
                payload=payload,
            )

        # ======================================================
        # Asistencia remota
        # ======================================================
        if flow == "remote":
            return self._continue_remote_flow(
                partner,
                session,
                identifiers,
                message_text,
                payload=payload,
            )

        # ======================================================
        # Flujos auxiliares
        # ======================================================
        if flow == "greeting":
            session.reset_conversation(
                reason="greeting_completed"
            )

            return self._build_main_menu_text(
                partner=partner,
                session=session,
            )

        if flow == "other":
            session.reset_conversation(
                reason="unknown_other_flow"
            )

            return self._build_main_menu_text(
                partner=partner,
                session=session,
            )

        # ======================================================
        # Flujo desconocido: recuperación segura
        # ======================================================
        _logger.warning(
            "[WA-FLOW] Flujo no reconocido | "
            "partner_id=%s session_id=%s flow=%s step=%s",
            partner.id if partner else False,
            session.id if session else False,
            flow,
            step,
        )

        session.reset_conversation(reason="unknown_flow")

        return self._build_main_menu_text(
            partner=partner,
            session=session,
        )
