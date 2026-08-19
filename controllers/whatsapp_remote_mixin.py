# -*- coding: utf-8 -*-

import logging

from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppRemoteMixin:
    # ==========================================================
    # Flujo remoto / AnyDesk: iniciar
    # ==========================================================
    def _start_remote_flow(self, partner, session, identifiers, payload=False):
        session.start_flow(
            "remote",
            "awaiting_anydesk_code",
            context={
                "intent": "remote_service",
                "initial_message": (payload or {}).get("message") or (payload or {}).get("text") or "",
            },
        )

        return self._render_template(
            "ask_anydesk_code",
            partner=partner,
            session=session,
            fallback=(
                "Claro. Para soporte remoto, envíanos tu código AnyDesk. "
                "Debe tener entre 6 y 12 dígitos."
            ),
        )

    # ==========================================================
    # Flujo remoto / AnyDesk: continuación
    # ==========================================================
    def _continue_remote_flow(self, partner, session, identifiers, text, payload=False):
        context = session.get_context()
        text_clean = (text or "").strip()
        state = session.conversation_state

        _logger.info(
            "[WA-REMOTE] Continuando flujo partner=%s session=%s state=%s text=%r context=%s",
            partner.id if partner else False,
            session.id if session else False,
            state,
            text_clean,
            context,
        )

        if state == "awaiting_anydesk_code":
            media = False

            if payload and (
                payload.get("media_url")
                or payload.get("url")
                or payload.get("media_id")
                or payload.get("external_media_id")
            ):
                media = self._create_media_from_payload(
                    session=session,
                    partner=partner,
                    message=False,
                    payload=payload or {},
                )

                if media:
                    try:
                        media.mark_for_human_review(
                            reason="Imagen/documento enviado como código AnyDesk."
                        )
                    except Exception:
                        pass

                    handoff = (
                        request.env["whatsapp.handoff"]
                        .sudo()
                        .create_remote_support_handoff(
                            partner,
                            session=session,
                            anydesk_code=False,
                            initial_message=(
                                text_clean
                                or "Cliente envió imagen/documento con AnyDesk."
                            ),
                            media=media,
                            context={
                                "reason": "Cliente envió media para código AnyDesk.",
                                "flow_context": context,
                            },
                        )
                    )

                    _logger.info(
                        "[WA-REMOTE] Handoff remoto por media creado | "
                        "handoff_id=%s partner=%s session=%s",
                        handoff.id if handoff else False,
                        partner.id if partner else False,
                        session.id if session else False,
                    )

                    partner.whatsapp_enable_human_mode_api(
                        taken_by_name="Bot WhatsApp"
                    )
                    session.action_set_human()

                    _logger.info(
                        "[WA-REMOTE] Modo humano activado por media | "
                        "partner=%s session=%s handoff_id=%s",
                        partner.id if partner else False,
                        session.id if session else False,
                        handoff.id if handoff else False,
                    )

                    return (
                        "Recibí la imagen/documento con tu código AnyDesk. "
                        "Te estoy derivando con un asesor para revisarlo."
                    )

            if not self._looks_like_anydesk(text_clean):
                _logger.info(
                    "[WA-REMOTE] Código AnyDesk inválido | "
                    "partner=%s session=%s value=%r",
                    partner.id if partner else False,
                    session.id if session else False,
                    text_clean,
                )
                return (
                    "No reconozco un código AnyDesk válido. "
                    "Envíame solo los números del código, entre 6 y 12 dígitos."
                )

            anydesk_code = self._only_digits(text_clean)

            session.advance_state(
                "awaiting_remote_problem",
                {
                    "anydesk_code": anydesk_code,
                },
            )

            _logger.info(
                "[WA-REMOTE] Código AnyDesk aceptado | "
                "partner=%s session=%s anydesk=%s next_state=awaiting_remote_problem",
                partner.id if partner else False,
                session.id if session else False,
                anydesk_code,
            )

            return (
                "Código AnyDesk recibido: %s\n\n"
                "Ahora descríbenos brevemente el problema que presenta el equipo."
            ) % anydesk_code

        if state == "awaiting_remote_problem":
            if len(text_clean) < 3:
                return (
                    "Por favor describe brevemente el problema "
                    "para que el técnico pueda ayudarte."
                )

            context = session.update_context({
                "remote_problem": text_clean,
            })

            anydesk_code = context.get("anydesk_code") or ""

            handoff = (
                request.env["whatsapp.handoff"]
                .sudo()
                .create_remote_support_handoff(
                    partner,
                    session=session,
                    anydesk_code=anydesk_code,
                    initial_message=text_clean,
                    context={
                        "reason": "Solicitud de soporte remoto.",
                        "flow_context": context,
                    },
                )
            )

            _logger.info(
                "[WA-REMOTE] Handoff remoto creado | "
                "handoff_id=%s partner=%s session=%s anydesk=%s problem=%r",
                handoff.id if handoff else False,
                partner.id if partner else False,
                session.id if session else False,
                anydesk_code,
                text_clean,
            )

            partner.whatsapp_enable_human_mode_api(taken_by_name="Bot WhatsApp")
            session.action_set_human()

            _logger.info(
                "[WA-REMOTE] Modo humano activado | "
                "partner=%s session=%s handoff_id=%s",
                partner.id if partner else False,
                session.id if session else False,
                handoff.id if handoff else False,
            )

            return self._render_template(
                "remote_handoff_created",
                partner=partner,
                session=session,
                extra={
                    "anydesk_code": anydesk_code,
                    "remote_problem": text_clean,
                },
                fallback=(
                    "Gracias. Ya derivé tu solicitud de soporte remoto con un técnico.\n"
                    "Código AnyDesk: %s"
                ) % anydesk_code,
            )

        _logger.warning(
            "[WA-REMOTE] Estado no reconocido state=%s session=%s",
            state,
            session.id if session else False,
        )

        return (
            "Estoy procesando tu solicitud de soporte remoto. "
            "Por favor continúa con la información solicitada."
        )
