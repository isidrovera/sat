# -*- coding: utf-8 -*-

import json
import logging
from datetime import timedelta

from odoo import fields
from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppMessageMixin:
    """
    Sesiones, mensajes, media y outbox del controlador WhatsApp.

    El timeout general y el timeout de flujo se mantienen separados.
    Los mensajes con external_message_id se registran de forma idempotente
    para soportar reintentos de n8n/Baileys sin duplicar persistencia.
    """
    """
    Gestión de sesiones, mensajes, media y outbox de WhatsApp.

    Principios:
    - una conversación con flujo activo usa su propio timeout interno;
    - una conversación sin flujo activo conserva el timeout general
      reportado por res.partner;
    - la guardia reciente de 120 segundos se mantiene únicamente como
      protección contra carreras entre /profile y /process;
    - no se amplía artificialmente esa guardia para ocultar errores del
      método partner._whatsapp_is_session_expired();
    - todos los mensajes y salidas quedan trazables mediante logs.
    """

    # ==========================================================
    # Diagnóstico de sesión
    # ==========================================================
    def _session_expiration_diagnostics(
        self,
        partner,
        active_session=False,
    ):
        """
        Reúne información de diagnóstico sin alterar la decisión de timeout.

        El objetivo es poder identificar qué dato hace que
        partner._whatsapp_is_session_expired() devuelva True.

        No se asume ningún nombre de campo como obligatorio: solo se
        incluyen los que realmente existen.
        """
        diagnostics = {
            "partner_id": partner.id if partner else False,
            "session_id": active_session.id if active_session else False,
        }

        if partner:
            for field_name in [
                "whatsapp_last_message_at",
                "whatsapp_last_interaction_at",
                "whatsapp_session_started_at",
                "whatsapp_session_expires_at",
                "whatsapp_last_user_message_at",
                "whatsapp_last_bot_message_at",
                "whatsapp_human_mode_since",
                "whatsapp_human_mode",
                "whatsapp_registration_state",
            ]:
                if field_name in partner._fields:
                    try:
                        diagnostics[field_name] = partner[field_name]
                    except Exception:
                        diagnostics[field_name] = "<error>"

        if active_session:
            for field_name in [
                "state",
                "current_flow",
                "conversation_state",
                "last_message_at",
                "started_at",
                "expires_at",
                "conversation_state_expires_at",
                "last_user_message_at",
                "last_bot_message_at",
                "closed_at",
            ]:
                if field_name in active_session._fields:
                    try:
                        diagnostics["session_%s" % field_name] = (
                            active_session[field_name]
                        )
                    except Exception:
                        diagnostics["session_%s" % field_name] = "<error>"

        return diagnostics

    def _log_session_expiration_diagnostics(
        self,
        partner,
        active_session=False,
        partner_reports_expired=False,
        effective_expired=False,
        force_new_session=False,
        guard_seconds=False,
        session_age_seconds=False,
    ):
        diagnostics = self._session_expiration_diagnostics(
            partner=partner,
            active_session=active_session,
        )

        _logger.info(
            "[WA-SESSION-DIAG] Timeout | "
            "partner_reports_expired=%s effective_expired=%s "
            "force_new=%s guard_seconds=%s age_seconds=%s data=%s",
            bool(partner_reports_expired),
            bool(effective_expired),
            bool(force_new_session),
            guard_seconds,
            session_age_seconds,
            diagnostics,
        )

    # ==========================================================
    # Sesiones / mensajes / media / outbox
    # ==========================================================
    def _get_or_create_session(self, partner, identifiers, intent=False, force_new_session=False):
        Session = request.env["whatsapp.session"].sudo()

        if not partner:
            _logger.warning("[WA-SESSION] _get_or_create_session llamado sin partner")
            return Session

        identifiers = identifiers or {}

        active_session = Session.search([
            ("partner_id", "=", partner.id),
            ("state", "in", ["open", "human"]),
        ], order="last_message_at desc, id desc", limit=1)

        _logger.info(
            "[WA-SESSION] Resolviendo sesión | "
            "partner_id=%s active_session_id=%s state=%s "
            "flow=%s step=%s last_message_at=%s "
            "force_new=%s intent=%s human_mode=%s",
            partner.id,
            active_session.id if active_session else False,
            active_session.state if active_session else False,
            active_session.current_flow if active_session else False,
            active_session.conversation_state if active_session else False,
            active_session.last_message_at if active_session else False,
            bool(force_new_session),
            intent or False,
            bool(partner.whatsapp_human_mode),
        )

        # ======================================================
        # Si existe una sesión con flujo activo, NO debe expirar
        # por el timeout general del partner. El flujo tiene su
        # propio conversation_state_expires_at.
        # ======================================================
        if active_session and active_session.current_flow != "none":
            try:
                if active_session.is_conversation_expired():
                    _logger.info(
                        "[WA-SESSION] Flujo activo expirado por timeout interno | session=%s flow=%s step=%s expires_at=%s",
                        active_session.id,
                        active_session.current_flow,
                        active_session.conversation_state,
                        active_session.conversation_state_expires_at,
                    )
                    active_session.reset_conversation(reason="expired")
                else:
                    vals = {
                        "last_message_at": fields.Datetime.now(),
                        "active_company_id": (
                            partner.whatsapp_active_company_id.id
                            if partner.whatsapp_active_company_id
                            else False
                        ),
                    }

                    resolved_phone = self._resolve_identifier_phone(identifiers, partner=partner)
                    resolved_jid = self._resolve_identifier_jid(identifiers, partner=partner)
                    resolved_lid = self._resolve_identifier_lid(identifiers, partner=partner)
                    resolved_raw_jid = self._resolve_identifier_raw_jid(identifiers, partner=partner)

                    if resolved_phone:
                        vals["phone"] = resolved_phone
                    if resolved_jid:
                        vals["jid"] = resolved_jid
                    if resolved_lid:
                        vals["lid"] = resolved_lid
                    if resolved_raw_jid:
                        vals["raw_jid"] = resolved_raw_jid
                    if intent:
                        vals["last_intent"] = intent

                    if partner.whatsapp_human_mode:
                        vals["state"] = "human"
                    elif active_session.state == "human" and not partner.whatsapp_human_mode:
                        vals["state"] = "open"

                    active_session.write(vals)

                    _logger.info(
                        "[WA-SESSION] Reutilizando sesión con flujo activo | session=%s flow=%s step=%s",
                        active_session.id,
                        active_session.current_flow,
                        active_session.conversation_state,
                    )
                    return active_session

            except Exception:
                _logger.exception(
                    "[WA-SESSION] Error validando sesión con flujo activo | session=%s",
                    active_session.id,
                )

        # ======================================================
        # Timeout general cuando NO hay flujo activo.
        #
        # Protección conservadora:
        # /profile y /process pueden ejecutarse con milisegundos de
        # diferencia. Si el partner reporta timeout pero la sesión
        # activa acaba de ser creada/tocada, no la expiramos de
        # inmediato. Esto evita el patrón 192->193->194 observado
        # en logs sin desactivar el timeout normal de sesiones.
        # ======================================================
        partner_reports_expired = False
        expiration_check_error = False
        try:
            partner_reports_expired = bool(partner._whatsapp_is_session_expired())
        except Exception as exc:
            expiration_check_error = str(exc)
            _logger.exception(
                "[WA-SESSION] Error evaluando timeout general del partner | partner_id=%s session_id=%s",
                partner.id,
                active_session.id if active_session else False,
            )
            partner_reports_expired = False

        guard_seconds = 120
        try:
            raw_guard = request.env["ir.config_parameter"].sudo().get_param(
                "sat.whatsapp_session_expire_guard_seconds",
                "120",
            )
            guard_seconds = max(0, int(raw_guard or 120))
        except Exception:
            guard_seconds = 120

        now = fields.Datetime.now()
        recent_active_session = False
        session_age_seconds = False

        if active_session and active_session.last_message_at:
            try:
                age = now - active_session.last_message_at
                session_age_seconds = max(0, int(age.total_seconds()))
                recent_active_session = session_age_seconds <= guard_seconds
            except Exception:
                recent_active_session = False
                session_age_seconds = False

        is_expired = partner_reports_expired
        if (
            is_expired
            and active_session
            and active_session.current_flow == "none"
            and recent_active_session
            and not force_new_session
        ):
            _logger.warning(
                "[WA-SESSION] Timeout general ignorado por guardia de sesión reciente | partner_id=%s session_id=%s age_seconds=%s guard_seconds=%s",
                partner.id,
                active_session.id,
                session_age_seconds,
                guard_seconds,
            )
            is_expired = False

        _logger.info(
            "[WA-SESSION] Resultado timeout general | "
            "partner_id=%s session_id=%s partner_reports_expired=%s "
            "effective_expired=%s recent=%s age_seconds=%s "
            "guard_seconds=%s force_new=%s check_error=%s",
            partner.id,
            active_session.id if active_session else False,
            partner_reports_expired,
            is_expired,
            recent_active_session,
            session_age_seconds,
            guard_seconds,
            bool(force_new_session),
            expiration_check_error or False,
        )

        self._log_session_expiration_diagnostics(
            partner=partner,
            active_session=active_session,
            partner_reports_expired=partner_reports_expired,
            effective_expired=is_expired,
            force_new_session=force_new_session,
            guard_seconds=guard_seconds,
            session_age_seconds=session_age_seconds,
        )

        if force_new_session or is_expired:
            if (
                active_session
                and active_session.state == "open"
                and active_session.current_flow == "none"
            ):
                _logger.info(
                    "[WA-SESSION] Expirando sesión por timeout/force_new | partner_id=%s session_id=%s force_new=%s effective_expired=%s",
                    partner.id,
                    active_session.id,
                    bool(force_new_session),
                    is_expired,
                )
                active_session.action_expire()

            active_session = Session

        if not active_session:
            create_vals = {
                "partner_id": partner.id,
                "active_company_id": (
                    partner.whatsapp_active_company_id.id
                    if partner.whatsapp_active_company_id
                    else False
                ),
                "phone": self._resolve_identifier_phone(identifiers, partner=partner),
                "jid": self._resolve_identifier_jid(identifiers, partner=partner),
                "lid": self._resolve_identifier_lid(identifiers, partner=partner),
                "raw_jid": self._resolve_identifier_raw_jid(identifiers, partner=partner),
                "state": "human" if partner.whatsapp_human_mode else "open",
                "source": "whatsapp",
                "last_intent": intent or False,
            }

            active_session = Session.create(create_vals)

            _logger.info(
                "[WA-SESSION] Nueva sesión creada | "
                "partner_id=%s session_id=%s state=%s phone=%s jid=%s lid=%s",
                partner.id,
                active_session.id,
                active_session.state,
                active_session.phone or False,
                active_session.jid or False,
                active_session.lid or False,
            )

        else:
            vals = {
                "last_message_at": now,
                "active_company_id": (
                    partner.whatsapp_active_company_id.id
                    if partner.whatsapp_active_company_id
                    else False
                ),
            }

            resolved_phone = self._resolve_identifier_phone(identifiers, partner=partner)
            resolved_jid = self._resolve_identifier_jid(identifiers, partner=partner)
            resolved_lid = self._resolve_identifier_lid(identifiers, partner=partner)
            resolved_raw_jid = self._resolve_identifier_raw_jid(identifiers, partner=partner)

            if resolved_phone:
                vals["phone"] = resolved_phone
            if resolved_jid:
                vals["jid"] = resolved_jid
            if resolved_lid:
                vals["lid"] = resolved_lid
            if resolved_raw_jid:
                vals["raw_jid"] = resolved_raw_jid
            if intent:
                vals["last_intent"] = intent

            if partner.whatsapp_human_mode:
                vals["state"] = "human"
            elif active_session.state == "human" and not partner.whatsapp_human_mode:
                vals["state"] = "open"

            active_session.write(vals)

            _logger.info(
                "[WA-SESSION] Sesión existente reutilizada | partner_id=%s session_id=%s state=%s flow=%s step=%s",
                partner.id,
                active_session.id,
                active_session.state,
                active_session.current_flow,
                active_session.conversation_state,
            )

        return active_session

    def _create_media_from_payload(self, session=False, partner=False, message=False, payload=False):
        payload = payload or {}

        media_url = payload.get("media_url") or payload.get("url")
        media_type = payload.get("media_type") or payload.get("message_type")
        mimetype = payload.get("media_mimetype") or payload.get("mimetype")
        filename = payload.get("filename") or payload.get("file_name")
        caption = payload.get("caption")
        external_media_id = payload.get("media_id") or payload.get("external_media_id")

        if not media_url and not external_media_id and media_type not in (
            "image",
            "audio",
            "video",
            "document",
            "location",
            "contact",
        ):
            return request.env["whatsapp.media"].sudo()

        if media_type not in ("image", "audio", "video", "document", "location", "contact"):
            media_type = "other"

        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False

        media = request.env["whatsapp.media"].sudo().create({
            "name": filename or caption or "Media WhatsApp",
            "message_id": message.id if message else False,
            "session_id": session.id if session else False,
            "partner_id": partner.id if partner else False,
            "company_id": company.id if company else False,
            "media_type": media_type,
            "filename": filename or False,
            "mimetype": mimetype or False,
            "url": media_url or False,
            "external_media_id": external_media_id or False,
            "caption": caption or False,
            "raw_payload": payload,
        })

        _logger.info(
            "[WA-MEDIA] Media registrada | "
            "media_id=%s session_id=%s partner_id=%s type=%s "
            "external_media_id=%s has_url=%s",
            media.id if media else False,
            session.id if session else False,
            partner.id if partner else False,
            media_type,
            external_media_id or False,
            bool(media_url),
        )

        return media

    def _record_whatsapp_message(
        self,
        session,
        partner,
        identifiers,
        role="user",
        direction="in",
        message_type="text",
        content=False,
        intent=False,
        payload=False,
        external_message_id=False,
    ):
        """
        Registra un mensaje de forma idempotente cuando existe
        ``external_message_id``.

        IMPORTANTE:
        - un duplicado NO vuelve a crear media;
        - un duplicado NO vuelve a ejecutar session.touch();
        - el recordset retornado lleva context ``wa_duplicate_message=True``
          para que /process pueda detener posteriormente una repetición antes
          de ejecutar lógica de negocio u outbox.

        Para mensajes sin external_message_id se conserva exactamente el
        comportamiento de creación normal.
        """
        Message = request.env["whatsapp.message"].sudo()

        if not session:
            return Message

        payload = payload or {}
        identifiers = identifiers or {}
        company = (
            partner.whatsapp_active_company_id
            if partner and partner.whatsapp_active_company_id
            else False
        )

        external_message_id = (
            str(external_message_id).strip()
            if external_message_id
            else False
        )

        # ------------------------------------------------------
        # Idempotencia previa
        # ------------------------------------------------------
        if external_message_id:
            existing = Message.find_duplicate(
                external_message_id=external_message_id,
                session_id=session.id,
            )

            if existing:
                _logger.warning(
                    "[WA-MESSAGE] Mensaje entrante/saliente duplicado | "
                    "external_id=%s message_id=%s session_id=%s "
                    "direction=%s role=%s status=%s",
                    external_message_id,
                    existing.id,
                    session.id,
                    direction,
                    role,
                    getattr(existing, "processing_status", False),
                )

                return existing.with_context(
                    wa_duplicate_message=True,
                    wa_duplicate_external_message_id=external_message_id,
                )

        vals = {
            "session_id": session.id,
            "partner_id": partner.id if partner else False,
            "company_id": company.id if company else False,
            "role": role,
            "direction": direction,
            "message_type": message_type or "text",
            "content": content or "",
            "phone": self._resolve_identifier_phone(
                identifiers,
                partner=partner,
            ) or False,
            "jid": self._resolve_identifier_jid(
                identifiers,
                partner=partner,
            ) or False,
            "lid": self._resolve_identifier_lid(
                identifiers,
                partner=partner,
            ) or False,
            "raw_jid": self._resolve_identifier_raw_jid(
                identifiers,
                partner=partner,
            ) or False,
            "external_message_id": external_message_id or False,
            "intent": intent or False,
            "media_url": (
                payload.get("media_url")
                or payload.get("url")
                or False
            ),
            "media_mimetype": (
                payload.get("media_mimetype")
                or payload.get("mimetype")
                or False
            ),
            "current_flow": session.current_flow if session else "none",
            "flow_step": session.conversation_state if session else False,
            "raw_payload": payload,
            "message_date": fields.Datetime.now(),
        }

        # Usar API idempotente del modelo cuando esté disponible.
        # El fallback permite un despliegue escalonado sin romper el bot.
        if hasattr(Message, "create_idempotent"):
            message = Message.create_idempotent(vals)
        else:
            message = Message.create(vals)

        # Protección adicional: si create_idempotent devolviera un existente
        # por una carrera entre la búsqueda anterior y create(), no crear media
        # ni tocar nuevamente la sesión.
        if (
            external_message_id
            and message
            and message.external_message_id == external_message_id
            and message.message_date
            and message.id
        ):
            # Solo consideramos carrera si el registro retornado no corresponde
            # aproximadamente a esta creación. El contexto del modelo no indica
            # por sí mismo si creó o reutilizó, así que verificamos si ya tenía
            # media asociada o un payload distinto únicamente como diagnóstico.
            duplicate_after_create = bool(
                message.env.context.get("wa_duplicate_message")
            )
        else:
            duplicate_after_create = False

        if duplicate_after_create:
            return message

        self._create_media_from_payload(
            session=session,
            partner=partner,
            message=message,
            payload=payload,
        )

        _logger.info(
            "[WA-MESSAGE] Mensaje registrado | "
            "message_id=%s session_id=%s partner_id=%s "
            "direction=%s role=%s type=%s intent=%s flow=%s step=%s "
            "external_id=%s",
            message.id if message else False,
            session.id if session else False,
            partner.id if partner else False,
            direction,
            role,
            message_type or "text",
            intent or False,
            session.current_flow if session else "none",
            session.conversation_state if session else False,
            external_message_id or False,
        )

        if direction == "in":
            session.touch(
                intent=intent,
                user_message=content,
            )
        else:
            session.touch(
                intent=intent,
                bot_message=content,
            )

        return message.with_context(
            wa_duplicate_message=False,
        )

    def _create_outbox(self, session, partner, identifiers, content, message_type="text", media=False, payload=False):
        Outbox = request.env["whatsapp.outbox"].sudo()
        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False

        outbox = Outbox.create({
            "session_id": session.id if session else False,
            "partner_id": partner.id if partner else False,
            "company_id": company.id if company else False,
            "phone": self._resolve_identifier_phone(identifiers, partner=partner) or False,
            "jid": self._resolve_identifier_jid(identifiers, partner=partner) or False,
            "lid": self._resolve_identifier_lid(identifiers, partner=partner) or False,
            "message_type": message_type or "text",
            "content": content or "",
            "media_id": media.id if media else False,
            "current_flow": session.current_flow if session else "none",
            "flow_step": session.conversation_state if session else False,
            "state": "pending",
            "raw_payload": payload or {},
        })

        _logger.info(
            "[WA-OUTBOX] Salida encolada | "
            "outbox_id=%s session_id=%s partner_id=%s "
            "type=%s flow=%s step=%s",
            outbox.id if outbox else False,
            session.id if session else False,
            partner.id if partner else False,
            message_type or "text",
            session.current_flow if session else "none",
            session.conversation_state if session else False,
        )

        return outbox

    def _emit_bot_reply(
        self,
        session,
        partner,
        identifiers,
        content,
        intent=False,
        payload=False,
        template=False,
        message_type="text",
        media=False,
        create_outbox=True,
    ):
        payload = payload or {}

        if content is False or content is None:
            content = ""

        if template:
            payload = dict(payload)
            payload["template_used"] = template

        message = self._record_whatsapp_message(
            session=session,
            partner=partner,
            identifiers=identifiers,
            role="assistant",
            direction="out",
            message_type=message_type,
            content=content,
            intent=intent,
            payload=payload,
        )

        outbox = False
        if create_outbox:
            outbox = self._create_outbox(
                session=session,
                partner=partner,
                identifiers=identifiers,
                content=content,
                message_type=message_type,
                media=media,
                payload=payload,
            )
            if outbox and message:
                outbox.write({"message_id": message.id})

        result = {
            "message_id": message.id if message else False,
            "outbox_id": outbox.id if outbox else False,
            "message": content,
        }

        _logger.info(
            "[WA-EMIT] Respuesta del bot registrada | "
            "session_id=%s partner_id=%s message_id=%s outbox_id=%s "
            "intent=%s template=%s create_outbox=%s",
            session.id if session else False,
            partner.id if partner else False,
            result.get("message_id"),
            result.get("outbox_id"),
            intent or False,
            template or False,
            bool(create_outbox),
        )

        return result

    # ==========================================================
    # Payload helpers
    # ==========================================================
    def _safe_json_dict(self, value):
        if isinstance(value, dict):
            return value

        if not value:
            return {}

        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}

        return {}