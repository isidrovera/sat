# -*- coding: utf-8 -*-

import logging

from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppRemoteMixin:
    """
    Flujo conversacional para asistencia remota mediante AnyDesk.

    Se conserva la lógica funcional corregida:
    - solicitar código AnyDesk;
    - aceptar código numérico de 6 a 12 dígitos;
    - aceptar imagen/documento cuando el cliente envía el código como media;
    - solicitar descripción del problema;
    - crear handoff con create_remote_support_handoff();
    - activar modo humano únicamente cuando existe atención disponible.

    La asistencia remota requiere disponibilidad de un técnico, por lo que
    este mixin incorpora una validación defensiva de horario además de la
    validación central realizada en whatsapp_process_mixin.py.
    """

    # ==========================================================
    # Navegación
    # ==========================================================
    def _remote_navigation_footer(self, include_back=True):
        """
        Devuelve la navegación estándar para WhatsApp.
        """
        if hasattr(self, "_flow_navigation_footer"):
            try:
                return self._flow_navigation_footer(
                    include_back=include_back
                )
            except Exception:
                pass

        lines = []

        if include_back:
            lines.append(
                "↩️ Escribe *ATRÁS* para regresar al paso anterior."
            )

        lines.append(
            "🏠 Escribe *MENU* para volver al menú principal."
        )
        lines.append(
            "❌ Escribe *CANCELAR* para cancelar la solicitud."
        )

        return "\n".join(lines)

    # ==========================================================
    # Disponibilidad horaria
    # ==========================================================
    def _remote_business_status_safe(self):
        """
        Obtiene el estado del horario sin romper el flujo si existe
        algún problema con calendario/configuración.
        """
        try:
            status = self._compute_business_status()
            return status if isinstance(status, dict) else {}
        except Exception:
            _logger.exception(
                "[WA-REMOTE] Error evaluando horario"
            )
            return {}

    def _remote_is_available(self, business_status=None):
        """
        La asistencia remota solo está disponible cuando is_open=True.
        """
        business_status = (
            business_status
            if isinstance(business_status, dict)
            else self._remote_business_status_safe()
        )

        return bool(
            business_status.get("is_open")
        )

    def _remote_unavailable_reply(
        self,
        partner,
        session,
        business_status=None,
    ):
        """
        Devuelve el mensaje profesional configurado para remoto no disponible.
        """
        business_status = (
            business_status
            if isinstance(business_status, dict)
            else self._remote_business_status_safe()
        )

        return self._render_template(
            "remote_unavailable",
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
                "💻 *Asistencia remota*\n\n"
                "La asistencia remota requiere la disponibilidad "
                "de uno de nuestros técnicos y en este momento no "
                "se encuentra disponible.\n\n"
                "Puedes registrar un *servicio técnico* para que "
                "nuestro equipo continúe la atención al retomar "
                "el horario correspondiente.\n\n"
                "🏠 Escribe *MENU* para volver al menú principal."
            ),
        )

    # ==========================================================
    # Handoff remoto
    # ==========================================================
    def _create_remote_support_handoff_safe(
        self,
        partner,
        session,
        anydesk_code=False,
        initial_message=False,
        media=False,
        context=None,
    ):
        """
        Crea el handoff remoto usando exclusivamente el helper correcto:
        create_remote_support_handoff().

        No activa modo humano si no existe atención disponible.
        """
        context = context if isinstance(context, dict) else {}
        business_status = self._remote_business_status_safe()
        realtime_available = self._remote_is_available(
            business_status
        )

        handoff = False

        try:
            handoff = (
                request.env["whatsapp.handoff"]
                .sudo()
                .create_remote_support_handoff(
                    partner,
                    session=session,
                    anydesk_code=(
                        anydesk_code
                        or False
                    ),
                    initial_message=(
                        initial_message
                        or ""
                    ),
                    media=(
                        media
                        if media
                        else False
                    ),
                    context={
                        "reason": (
                            context.get("reason")
                            or "Solicitud de soporte remoto."
                        ),
                        "flow_context": (
                            context.get("flow_context")
                            if isinstance(
                                context.get("flow_context"),
                                dict,
                            )
                            else context
                        ),
                        "business_status": business_status,
                        "pending_until_business_hours": (
                            not realtime_available
                        ),
                    },
                )
            )

            _logger.info(
                "[WA-REMOTE] Handoff remoto creado | "
                "handoff_id=%s partner_id=%s session_id=%s "
                "anydesk=%s media_id=%s realtime_available=%s",
                handoff.id if handoff else False,
                partner.id if partner else False,
                session.id if session else False,
                anydesk_code or False,
                media.id if media else False,
                realtime_available,
            )

        except Exception:
            _logger.exception(
                "[WA-REMOTE] Error creando handoff remoto | "
                "partner_id=%s session_id=%s anydesk=%s",
                partner.id if partner else False,
                session.id if session else False,
                anydesk_code or False,
            )

        if realtime_available:
            try:
                partner.whatsapp_enable_human_mode_api(
                    taken_by_name="Bot WhatsApp"
                )
                session.action_set_human()

                _logger.info(
                    "[WA-REMOTE] Modo humano activado | "
                    "partner_id=%s session_id=%s handoff_id=%s",
                    partner.id if partner else False,
                    session.id if session else False,
                    handoff.id if handoff else False,
                )

            except Exception:
                _logger.exception(
                    "[WA-REMOTE] Error activando modo humano | "
                    "partner_id=%s session_id=%s",
                    partner.id if partner else False,
                    session.id if session else False,
                )

            return handoff, True, business_status

        try:
            if session and session.current_flow != "none":
                session.reset_conversation(
                    reason="remote_pending_after_hours"
                )
        except Exception:
            _logger.exception(
                "[WA-REMOTE] Error cerrando flujo remoto "
                "fuera de horario | session_id=%s",
                session.id if session else False,
            )

        return handoff, False, business_status

    # ==========================================================
    # Flujo remoto / AnyDesk: iniciar
    # ==========================================================
    def _start_remote_flow(
        self,
        partner,
        session,
        identifiers,
        payload=False,
    ):
        """
        Inicia asistencia remota únicamente si existe atención disponible.

        whatsapp_process_mixin.py ya realiza esta validación antes de llamar
        a este método. La validación aquí es defensiva para evitar que una
        llamada directa o futura reutilización salte la política de horario.
        """
        business_status = self._remote_business_status_safe()

        if not self._remote_is_available(
            business_status
        ):
            _logger.info(
                "[WA-REMOTE] Inicio bloqueado por horario | "
                "partner_id=%s session_id=%s reason=%s",
                partner.id if partner else False,
                session.id if session else False,
                business_status.get("reason") or False,
            )

            try:
                if session and session.current_flow != "none":
                    session.reset_conversation(
                        reason="remote_unavailable_at_start"
                    )
            except Exception:
                pass

            return self._remote_unavailable_reply(
                partner=partner,
                session=session,
                business_status=business_status,
            )

        session.start_flow(
            "remote",
            "awaiting_anydesk_code",
            context={
                "intent": "remote_service",
                "initial_message": (
                    (payload or {}).get("message")
                    or (payload or {}).get("text")
                    or ""
                ),
            },
        )

        _logger.info(
            "[WA-REMOTE] Flujo iniciado | "
            "partner_id=%s session_id=%s state=awaiting_anydesk_code",
            partner.id if partner else False,
            session.id if session else False,
        )

        return self._render_template(
            "ask_anydesk_code",
            partner=partner,
            session=session,
            fallback=(
                "💻 *Asistencia remota · Paso 1*\n\n"
                "Para continuar, envíanos el *código AnyDesk* "
                "del equipo o computadora que deseas que revisemos.\n\n"
                "El código debe contener entre *6 y 12 dígitos*.\n\n"
                "%s"
            ) % self._remote_navigation_footer(
                include_back=True
            ),
        )

    # ==========================================================
    # Flujo remoto / AnyDesk: continuación
    # ==========================================================
    def _continue_remote_flow(
        self,
        partner,
        session,
        identifiers,
        text,
        payload=False,
    ):
        """
        Continúa el flujo remoto.

        Estados:
        - awaiting_anydesk_code
        - awaiting_remote_problem
        """
        context = session.get_context()
        context = (
            context
            if isinstance(context, dict)
            else {}
        )

        text_clean = (
            text
            or ""
        ).strip()

        state = session.conversation_state

        _logger.info(
            "[WA-REMOTE] Continuando flujo | "
            "partner_id=%s session_id=%s state=%s text=%r "
            "context_keys=%s",
            partner.id if partner else False,
            session.id if session else False,
            state,
            text_clean[:200],
            list(context.keys()),
        )

        # ------------------------------------------------------
        # Validación defensiva de horario
        # ------------------------------------------------------
        business_status = self._remote_business_status_safe()

        if not self._remote_is_available(
            business_status
        ):
            _logger.info(
                "[WA-REMOTE] Continuación bloqueada por horario | "
                "partner_id=%s session_id=%s state=%s reason=%s",
                partner.id if partner else False,
                session.id if session else False,
                state,
                business_status.get("reason") or False,
            )

            try:
                session.reset_conversation(
                    reason="remote_unavailable_during_flow"
                )
            except Exception:
                _logger.exception(
                    "[WA-REMOTE] No se pudo cerrar flujo bloqueado | "
                    "session_id=%s",
                    session.id if session else False,
                )

            return self._remote_unavailable_reply(
                partner=partner,
                session=session,
                business_status=business_status,
            )

        # ======================================================
        # PASO 1: CÓDIGO ANYDESK
        # ======================================================
        if state == "awaiting_anydesk_code":
            media = False

            # --------------------------------------------------
            # Cliente envía imagen/documento con el código
            # --------------------------------------------------
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
                            reason=(
                                "Imagen/documento enviado "
                                "como código AnyDesk."
                            )
                        )
                    except Exception:
                        _logger.exception(
                            "[WA-REMOTE] No se pudo marcar media | "
                            "media_id=%s",
                            media.id,
                        )

                    handoff, human_active, business_status = (
                        self._create_remote_support_handoff_safe(
                            partner=partner,
                            session=session,
                            anydesk_code=False,
                            initial_message=(
                                text_clean
                                or (
                                    "Cliente envió imagen/documento "
                                    "con AnyDesk."
                                )
                            ),
                            media=media,
                            context={
                                "reason": (
                                    "Cliente envió media "
                                    "para código AnyDesk."
                                ),
                                "flow_context": context,
                            },
                        )
                    )

                    if human_active:
                        return (
                            "✅ *Información recibida*\n\n"
                            "Recibí la imagen o documento con los datos "
                            "de AnyDesk y la solicitud fue derivada a "
                            "nuestro equipo técnico.\n\n"
                            "Por favor mantén AnyDesk disponible y "
                            "permanece atento(a) a este chat."
                        )

                    return self._remote_unavailable_reply(
                        partner=partner,
                        session=session,
                        business_status=business_status,
                    )

            # --------------------------------------------------
            # Código escrito por texto
            # --------------------------------------------------
            if not self._looks_like_anydesk(
                text_clean
            ):
                _logger.info(
                    "[WA-REMOTE] Código AnyDesk inválido | "
                    "partner_id=%s session_id=%s value=%r",
                    partner.id if partner else False,
                    session.id if session else False,
                    text_clean,
                )

                return (
                    "⚠️ *Código AnyDesk no válido*\n\n"
                    "Envía únicamente los números del código AnyDesk. "
                    "Debe contener entre *6 y 12 dígitos*.\n\n"
                    "Ejemplo: *123456789*\n\n"
                    "%s"
                ) % self._remote_navigation_footer(
                    include_back=True
                )

            anydesk_code = self._only_digits(
                text_clean
            )

            session.advance_state(
                "awaiting_remote_problem",
                {
                    "anydesk_code": (
                        anydesk_code
                    ),
                },
            )

            _logger.info(
                "[WA-REMOTE] Código AnyDesk aceptado | "
                "partner_id=%s session_id=%s anydesk=%s "
                "next_state=awaiting_remote_problem",
                partner.id if partner else False,
                session.id if session else False,
                anydesk_code,
            )

            return (
                "✅ *Código AnyDesk recibido*\n"
                "*%s*\n\n"
                "💻 *Asistencia remota · Paso 2*\n\n"
                "Describe brevemente el problema que deseas que "
                "revise nuestro técnico.\n\n"
                "Ejemplos:\n"
                "• No puedo imprimir.\n"
                "• El escáner no envía al correo.\n"
                "• La impresora no aparece en mi computadora.\n\n"
                "%s"
            ) % (
                anydesk_code,
                self._remote_navigation_footer(
                    include_back=True
                ),
            )

        # ======================================================
        # PASO 2: DESCRIPCIÓN DEL PROBLEMA
        # ======================================================
        if state == "awaiting_remote_problem":
            if len(text_clean) < 3:
                return (
                    "⚠️ *Necesito un poco más de información*\n\n"
                    "Describe brevemente el inconveniente para que "
                    "el técnico pueda identificar qué debe revisar.\n\n"
                    "%s"
                ) % self._remote_navigation_footer(
                    include_back=True
                )

            context = session.update_context({
                "remote_problem": text_clean,
            })

            anydesk_code = (
                context.get("anydesk_code")
                or ""
            )

            handoff, human_active, business_status = (
                self._create_remote_support_handoff_safe(
                    partner=partner,
                    session=session,
                    anydesk_code=anydesk_code,
                    initial_message=text_clean,
                    context={
                        "reason": (
                            "Solicitud de soporte remoto."
                        ),
                        "flow_context": context,
                    },
                )
            )

            _logger.info(
                "[WA-REMOTE] Solicitud remota procesada | "
                "partner_id=%s session_id=%s handoff_id=%s "
                "anydesk=%s human_active=%s problem=%r",
                partner.id if partner else False,
                session.id if session else False,
                handoff.id if handoff else False,
                anydesk_code,
                human_active,
                text_clean[:250],
            )

            if not human_active:
                return self._remote_unavailable_reply(
                    partner=partner,
                    session=session,
                    business_status=business_status,
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
                    "✅ *Solicitud de asistencia remota registrada*\n\n"
                    "Código AnyDesk: *%s*\n"
                    "Problema reportado: %s\n\n"
                    "La solicitud fue derivada a nuestro equipo técnico. "
                    "Por favor mantén AnyDesk disponible y permanece "
                    "atento(a) a este chat."
                ) % (
                    anydesk_code,
                    text_clean,
                ),
            )

        # ======================================================
        # Estado desconocido
        # ======================================================
        _logger.warning(
            "[WA-REMOTE] Estado no reconocido | "
            "partner_id=%s session_id=%s state=%s",
            partner.id if partner else False,
            session.id if session else False,
            state,
        )

        return (
            "⚠️ No pude determinar en qué paso de la asistencia "
            "remota te encuentras.\n\n"
            "Escribe *MENU* para volver al menú principal e iniciar "
            "nuevamente la solicitud."
        )
