# -*- coding: utf-8 -*-

import json
import logging
from datetime import timedelta

from odoo import fields
from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppMessageMixin:
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
            "[WA-SESSION] Resolviendo sesión | partner_id=%s active_session_id=%s state=%s flow=%s step=%s last_message_at=%s force_new=%s intent=%s human_mode=%s",
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
            "[WA-SESSION] Resultado timeout general | partner_id=%s session_id=%s partner_reports_expired=%s effective_expired=%s recent=%s age_seconds=%s guard_seconds=%s force_new=%s check_error=%s",
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
                "[WA-SESSION] Nueva sesión resuelta | partner_id=%s session_id=%s state=%s phone=%s jid=%s lid=%s",
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

        return request.env["whatsapp.media"].sudo().create({
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
        Message = request.env["whatsapp.message"].sudo()

        if not session:
            return Message

        payload = payload or {}
        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False

        message = Message.create({
            "session_id": session.id,
            "partner_id": partner.id if partner else False,
            "company_id": company.id if company else False,
            "role": role,
            "direction": direction,
            "message_type": message_type or "text",
            "content": content or "",
            "phone": self._resolve_identifier_phone(identifiers, partner=partner) or False,
            "jid": self._resolve_identifier_jid(identifiers, partner=partner) or False,
            "lid": self._resolve_identifier_lid(identifiers, partner=partner) or False,
            "raw_jid": self._resolve_identifier_raw_jid(identifiers, partner=partner) or False,
            "external_message_id": external_message_id or False,
            "intent": intent or False,
            "media_url": payload.get("media_url") or payload.get("url") or False,
            "media_mimetype": payload.get("media_mimetype") or payload.get("mimetype") or False,
            "current_flow": session.current_flow if session else "none",
            "flow_step": session.conversation_state if session else False,
            "raw_payload": payload,
            "message_date": fields.Datetime.now(),
        })

        self._create_media_from_payload(
            session=session,
            partner=partner,
            message=message,
            payload=payload,
        )

        if direction == "in":
            session.touch(intent=intent, user_message=content)
        else:
            session.touch(intent=intent, bot_message=content)

        return message

    def _create_outbox(self, session, partner, identifiers, content, message_type="text", media=False, payload=False):
        Outbox = request.env["whatsapp.outbox"].sudo()
        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False

        return Outbox.create({
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

        return {
            "message_id": message.id if message else False,
            "outbox_id": outbox.id if outbox else False,
            "message": content,
        }

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