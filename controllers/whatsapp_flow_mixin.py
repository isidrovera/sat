# -*- coding: utf-8 -*-

import logging

from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppFlowMixin:
    # ==========================================================
    # Continuar flujo activo
    # ==========================================================
    def _continue_active_flow(self, partner, session, identifiers, message_text, payload=False):
        if not session:
            return "No pude encontrar una sesión activa. Escribe MENU para empezar nuevamente."

        flow = session.current_flow
        step = session.conversation_state

        _logger.info(
            "[WA-FLOW] Continuando flujo | partner_id=%s session_id=%s flow=%s step=%s message=%s",
            partner.id if partner else False,
            session.id if session else False,
            flow,
            step,
            (message_text or "")[:300],
        )

        text_lower = (message_text or "").strip().lower()

        if text_lower in ["cancelar", "cancela", "salir", "terminar", "anular"]:
            session.reset_conversation(reason="abandoned")
            return "Listo, cancelé el flujo activo. ¿En qué más podemos ayudarte?"

        if text_lower in ["menu", "menú", "inicio", "ayuda", "opciones"]:
            session.reset_conversation(reason="menu_requested")
            return self._build_main_menu_text(partner=partner, session=session)

        if flow == "registration":
            if step == "awaiting_company_selection":
                return self._continue_company_selection(
                    partner,
                    session,
                    message_text,
                )

            session.reset_conversation(reason="registration_unknown_step")
            return self._build_main_menu_text(partner=partner, session=session)

        if flow == "toner":
            return self._continue_toner_flow(
                partner,
                session,
                identifiers,
                message_text,
                payload=payload,
            )

        if flow == "onsite":
            return self._continue_onsite_flow(
                partner,
                session,
                identifiers,
                message_text,
                payload=payload,
            )

        if flow == "remote":
            return self._continue_remote_flow(
                partner,
                session,
                identifiers,
                message_text,
                payload=payload,
            )

        if flow == "greeting":
            session.reset_conversation(reason="greeting_completed")
            return self._build_main_menu_text(partner=partner, session=session)

        if flow == "other":
            session.reset_conversation(reason="unknown_other_flow")
            return self._build_main_menu_text(partner=partner, session=session)

        _logger.warning(
            "[WA-FLOW] Flujo no reconocido | partner_id=%s session_id=%s flow=%s step=%s",
            partner.id if partner else False,
            session.id if session else False,
            flow,
            step,
        )

        session.reset_conversation(reason="unknown_flow")
        return self._build_main_menu_text(partner=partner, session=session)