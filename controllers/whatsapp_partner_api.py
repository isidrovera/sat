# -*- coding: utf-8 -*-

import json
import logging
import re
import time
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from odoo import http, fields
from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppPartnerApiController(http.Controller):
    """
    API central WhatsApp para n8n / Baileys.

    Este controlador conserva los endpoints antiguos y agrega un endpoint
    orquestador:

        /sat/whatsapp/process

    Ese endpoint procesa una conversación completa:
    - Identifica contacto por teléfono/JID/LID.
    - Registra DNI/RUC si corresponde.
    - Evalúa horario, refrigerio y calendario.
    - Registra mensaje entrante.
    - Si hay flujo activo, continúa el estado.
    - Si no hay flujo activo, detecta intención.
    - Ejecuta acciones: tóner, servicio presencial, remoto/AnyDesk, humano.
    - Crea mensaje saliente y outbox.
    - Devuelve el mensaje listo para que n8n/Baileys lo envíe.
    """

    # ==========================================================
    # Helpers base
    # ==========================================================
    def _get_json_payload(self):
        try:
            if hasattr(request, "get_json_data"):
                return request.get_json_data() or {}
        except Exception:
            pass

        try:
            return request.jsonrequest or {}
        except Exception:
            return {}

    def _json_error(self, message, code="ERROR", status=200, extra=None):
        data = {
            "ok": False,
            "code": code,
            "status": status,
            "message": message,
        }
        if extra:
            data.update(extra)
        return data

    def _check_token(self):
        token = request.env["ir.config_parameter"].sudo().get_param(
            "sat.whatsapp_api_token"
        )

        if not token:
            _logger.warning(
                "[SAT-WHATSAPP-API] Falta configurar ir.config_parameter: sat.whatsapp_api_token"
            )
            return False

        auth_header = request.httprequest.headers.get("Authorization", "")
        expected = "Bearer %s" % token

        if auth_header != expected:
            _logger.warning("[SAT-WHATSAPP-API] Token inválido o ausente")
            return False

        return True

    def _safe_log_api(
        self,
        endpoint,
        payload,
        response,
        identifiers=None,
        partner=False,
        session=False,
        start_ts=False,
        status="success",
        error_code=False,
        error_message=False,
        source="api",
    ):
        try:
            identifiers = identifiers or {}
            duration_ms = 0
            if start_ts:
                duration_ms = int((time.time() - start_ts) * 1000)

            if "whatsapp.api.log" not in request.env:
                return

            request.env["whatsapp.api.log"].sudo().create({
                "name": endpoint,
                "endpoint": endpoint,
                "method": request.httprequest.method,
                "phone": identifiers.get("phone") or False,
                "jid": identifiers.get("jid") or False,
                "lid": identifiers.get("lid") or False,
                "raw_jid": identifiers.get("raw_jid") or False,
                "partner_id": partner.id if partner else False,
                "session_id": session.id if session else False,
                "request_payload": payload or {},
                "response_payload": response or {},
                "status": status,
                "error_code": error_code or False,
                "error_message": error_message or False,
                "duration_ms": duration_ms,
                "source": source or "api",
            })
        except Exception:
            _logger.exception("[SAT-WHATSAPP-API] No se pudo guardar whatsapp.api.log")

    # ==========================================================
    # Teléfono / JID / LID
    # ==========================================================
    def _only_digits(self, value):
        return re.sub(r"\D+", "", str(value or ""))

    def _clean_phone(self, value):
        value = value or ""
        value = str(value).strip()

        if not value:
            return ""

        lowered = value.lower()

        if "@lid" in lowered:
            return ""

        if "@s.whatsapp.net" in lowered or "@c.us" in lowered:
            value = value.split("@", 1)[0]

        digits = re.sub(r"\D+", "", value)

        if not digits:
            return ""

        digits = digits.lstrip("0")

        if len(digits) == 9:
            digits = "51" + digits

        return digits

    def _normalize_jid(self, value):
        value = (value or "").strip()
        return value or ""

    def _is_lid(self, value):
        value = (value or "").lower().strip()
        return "@lid" in value or value.endswith(".lid")

    def _is_normal_whatsapp_jid(self, value):
        value = (value or "").lower().strip()
        return "@s.whatsapp.net" in value or "@c.us" in value

    def _extract_identifiers(self, payload):
        phone = (
            payload.get("phone")
            or payload.get("whatsapp_number")
            or payload.get("number")
        )

        incoming_from = (
            payload.get("from")
            or payload.get("remoteJid")
            or payload.get("remote_jid")
        )

        jid = payload.get("jid") or payload.get("remote_jid")
        lid = payload.get("lid") or payload.get("remote_lid")
        raw_jid = payload.get("raw_jid") or incoming_from or jid or lid

        if incoming_from and self._is_normal_whatsapp_jid(incoming_from):
            jid = jid or incoming_from
            phone = phone or incoming_from

        if incoming_from and self._is_lid(incoming_from):
            lid = lid or incoming_from

        if jid and self._is_lid(jid):
            lid = lid or jid
            jid = False

        return {
            "phone": self._clean_phone(phone),
            "jid": self._normalize_jid(jid),
            "lid": self._normalize_jid(lid),
            "raw_jid": self._normalize_jid(raw_jid),
        }

    def _has_any_identifier(self, identifiers):
        return bool(
            identifiers.get("phone")
            or identifiers.get("jid")
            or identifiers.get("lid")
            or identifiers.get("raw_jid")
        )

    # ==========================================================
    # DNI / RUC
    # ==========================================================
    def _get_latam_doc_type(self, code=None, name=None):
        DocType = request.env["l10n_latam.identification.type"].sudo()

        if code:
            doc_type = DocType.search([("l10n_pe_vat_code", "=", code)], limit=1)
            if doc_type:
                return doc_type

        if name:
            doc_type = DocType.search([("name", "=", name)], limit=1)
            if doc_type:
                return doc_type

        return DocType

    def _get_dni_type(self):
        return self._get_latam_doc_type(code="1", name="DNI")

    def _get_ruc_type(self):
        return self._get_latam_doc_type(code="6", name="RUC")

    def _run_partner_document_autoload(self, partner):
        if hasattr(partner, "_doc_number_change"):
            partner._doc_number_change()
            return True
        return False

    def _prepare_partner_whatsapp_values(self, identifiers):
        vals = {}

        phone = identifiers.get("phone")
        jid = identifiers.get("jid")
        lid = identifiers.get("lid")
        raw_jid = identifiers.get("raw_jid")

        if phone:
            vals["mobile"] = "+%s" % phone if not str(phone).startswith("+") else phone
            vals["whatsapp_number"] = phone

        if jid:
            vals["whatsapp_jid"] = jid

        if lid:
            vals["whatsapp_lid"] = lid

        if raw_jid:
            vals["whatsapp_last_raw_jid"] = raw_jid

        return vals

    # ==========================================================
    # Buscar contacto
    # ==========================================================
    def _find_partner_by_phone(self, clean_phone):
        Partner = request.env["res.partner"].sudo()

        if not clean_phone:
            return Partner

        last9 = clean_phone[-9:]

        candidates = Partner.search([
            "|", "|", "|",
            ("whatsapp_number", "ilike", last9),
            ("mobile", "ilike", last9),
            ("phone", "ilike", last9),
            ("whatsapp_jid", "ilike", clean_phone),
        ], limit=50)

        if not candidates:
            return Partner

        for partner in candidates:
            for number in [partner.whatsapp_number, partner.mobile, partner.phone]:
                if self._clean_phone(number) == clean_phone:
                    return partner

        for partner in candidates:
            if partner.whatsapp_jid and clean_phone in partner.whatsapp_jid:
                return partner

        return candidates[:1]

    def _find_partner_by_identifiers(self, identifiers):
        Partner = request.env["res.partner"].sudo()

        clean_phone = identifiers.get("phone")
        clean_jid = identifiers.get("jid")
        clean_lid = identifiers.get("lid")
        raw_jid = identifiers.get("raw_jid")

        if clean_phone:
            partner = self._find_partner_by_phone(clean_phone)
            if partner:
                return partner

        if clean_jid:
            partner = Partner.search([("whatsapp_jid", "=", clean_jid)], limit=1)
            if partner:
                return partner

        if clean_lid:
            partner = Partner.search([("whatsapp_lid", "=", clean_lid)], limit=1)
            if partner:
                return partner

        if raw_jid and self._is_lid(raw_jid):
            partner = Partner.search([("whatsapp_lid", "=", raw_jid)], limit=1)
            if partner:
                return partner

        if raw_jid and self._is_normal_whatsapp_jid(raw_jid):
            partner = Partner.search([("whatsapp_jid", "=", raw_jid)], limit=1)
            if partner:
                return partner

        return Partner

    def _update_partner_identifiers(self, partner, identifiers):
        if not partner:
            return

        if hasattr(partner, "whatsapp_update_identifiers"):
            partner.whatsapp_update_identifiers(
                jid=identifiers.get("jid"),
                lid=identifiers.get("lid"),
                raw_jid=identifiers.get("raw_jid"),
            )

    # ==========================================================
    # Templates / textos
    # ==========================================================
    def _render_template(
        self,
        template_name,
        partner=False,
        session=False,
        company=False,
        extra=None,
        fallback=False,
    ):
        try:
            text = request.env["whatsapp.template"].sudo().get_rendered(
                name=template_name,
                partner=partner if partner else False,
                session=session if session else False,
                company=company if company else False,
                extra=extra or {},
            )
            return text or fallback
        except Exception:
            _logger.exception("[SAT-WHATSAPP-API] Error renderizando template %s", template_name)
            return fallback

    def _get_status_template_name(self, partner=False, business_status=False):
        if not partner:
            return "ask_dni"

        if partner.whatsapp_blocked or partner.whatsapp_access_level == "blocked":
            return "blocked_contact"

        if partner.whatsapp_human_mode:
            return "human_mode_active"

        if business_status and not business_status.get("is_open"):
            if business_status.get("reason") == "break":
                return "in_break"
            return "after_hours"

        registration_state = getattr(partner, "whatsapp_registration_state", "none")

        if registration_state in ("none", "waiting_dni"):
            return "ask_dni"

        if registration_state == "waiting_ruc":
            return "ask_ruc"

        if partner.whatsapp_requires_company_selection:
            return "select_company"

        return "greeting_registered"

    def _build_suggested_message(self, partner=False, session=False, business_status=False, extra=None):
        template_name = self._get_status_template_name(
            partner=partner,
            business_status=business_status,
        )

        fallback_map = {
            "ask_dni": "Para poder ayudarte, por favor envíame tu DNI de 8 dígitos.",
            "ask_ruc": "Gracias. Ahora envíame el RUC de tu empresa para completar el registro.",
            "blocked_contact": "Tu número no está habilitado para atención por este canal.",
            "human_mode_active": "Tu conversación está siendo atendida por un asesor.",
            "after_hours": business_status.get("message") if business_status else "Estamos fuera de horario de atención.",
            "in_break": business_status.get("message") if business_status else "Estamos en horario de refrigerio.",
            "select_company": "Tienes más de una empresa asociada. Indica con cuál deseas continuar.",
            "greeting_registered": "¿En qué podemos ayudarte?",
        }

        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False

        return {
            "template": template_name,
            "message": self._render_template(
                template_name,
                partner=partner,
                session=session,
                company=company,
                extra=extra or {},
                fallback=fallback_map.get(template_name, ""),
            ),
        }

    def _get_greeting_message(self, partner=False, session=False, business_status=False):
        now_lima = self._now_lima()
        hour = now_lima.hour + (now_lima.minute / 60.0)

        template_name = "greeting_morning"
        fallback = "Buenos días"

        if hour >= 12 and hour < 19:
            template_name = "greeting_afternoon"
            fallback = "Buenas tardes"
        elif hour >= 19 or hour < 5:
            template_name = "greeting_evening"
            fallback = "Buenas noches"

        name = ""
        if partner and partner.name:
            name = ", %s" % partner.name.split()[0]

        fallback = "%s%s. ¿En qué podemos ayudarte?" % (fallback, name)

        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False

        return self._render_template(
            template_name,
            partner=partner,
            session=session,
            company=company,
            fallback=fallback,
        )

    # ==========================================================
    # Horario / calendario
    # ==========================================================
    def _now_lima(self):
        if ZoneInfo:
            return datetime.now(ZoneInfo("America/Lima"))
        return datetime.utcnow() - timedelta(hours=5)

    def _compute_business_status(self, check_dt=False):
        check_dt = check_dt or self._now_lima()
        today = check_dt.date()
        current_float = check_dt.hour + (check_dt.minute / 60.0)
        day_of_week = str(check_dt.weekday())

        Event = request.env["whatsapp.calendar.event"].sudo()
        Hours = request.env["whatsapp.business.hours"].sudo()

        event = Event.search([
            ("active", "=", True),
            ("event_date", "=", today),
        ], order="event_type asc, id asc", limit=1)

        if event:
            if event.event_type in ("holiday", "manual_closed") or event.is_closed:
                return {
                    "is_open": False,
                    "reason": event.event_type,
                    "reason_label": event.name,
                    "message": event.message or "Hoy no tenemos atención. Puedes dejarnos tu consulta y te responderemos el siguiente día hábil.",
                    "date": str(today),
                    "event_id": event.id,
                    "display_hours": event.get_display_hours(),
                }

            if event.event_type == "special_hours":
                is_open = event.special_open_time <= current_float <= event.special_close_time
                in_break = (
                    event.has_special_break
                    and event.special_break_start <= current_float <= event.special_break_end
                )

                if in_break:
                    is_open = False

                return {
                    "is_open": bool(is_open),
                    "reason": "special_hours_break" if in_break else "special_hours",
                    "reason_label": event.name,
                    "message": event.message or "Estamos fuera de horario especial. Puedes dejarnos tu consulta.",
                    "date": str(today),
                    "event_id": event.id,
                    "display_hours": event.get_display_hours(),
                }

        hours = Hours.search([
            ("active", "=", True),
            ("day_of_week", "=", day_of_week),
        ], limit=1)

        if not hours:
            return {
                "is_open": True,
                "reason": "no_hours_config",
                "reason_label": "Sin horario configurado",
                "message": False,
                "date": str(today),
                "display_hours": False,
            }

        if not hours.is_workday:
            return {
                "is_open": False,
                "reason": "closed_day",
                "reason_label": "Día no laboral",
                "message": hours.after_hours_message,
                "date": str(today),
                "display_hours": hours.get_display_hours(),
            }

        in_work = hours.open_time <= current_float <= hours.close_time
        in_break = hours.has_break and hours.break_start <= current_float <= hours.break_end

        if in_break:
            return {
                "is_open": False,
                "reason": "break",
                "reason_label": "Refrigerio",
                "message": hours.break_message,
                "date": str(today),
                "display_hours": hours.get_display_hours(),
            }

        if not in_work:
            return {
                "is_open": False,
                "reason": "after_hours",
                "reason_label": "Fuera de horario",
                "message": hours.after_hours_message,
                "date": str(today),
                "display_hours": hours.get_display_hours(),
            }

        return {
            "is_open": True,
            "reason": "open",
            "reason_label": "Abierto",
            "message": False,
            "date": str(today),
            "display_hours": hours.get_display_hours(),
        }

    def _get_applies_to(self, partner, business_status=False):
        if not partner:
            return "new"

        if partner.whatsapp_blocked or partner.whatsapp_access_level == "blocked":
            return "blocked"

        if partner.whatsapp_human_mode:
            return "human"

        if business_status and not business_status.get("is_open"):
            return "after_hours"

        registration_state = getattr(partner, "whatsapp_registration_state", "none")
        if registration_state != "registered":
            return "new"

        return "registered"

    # ==========================================================
    # Sesiones / mensajes / media / outbox
    # ==========================================================
    def _get_or_create_session(self, partner, identifiers, intent=False, force_new_session=False):
        Session = request.env["whatsapp.session"].sudo()

        if not partner:
            return Session

        is_expired = False
        try:
            is_expired = partner._whatsapp_is_session_expired()
        except Exception:
            is_expired = False

        active_session = Session.search([
            ("partner_id", "=", partner.id),
            ("state", "in", ["open", "human"]),
        ], order="last_message_at desc, id desc", limit=1)

        if force_new_session or is_expired:
            if active_session and active_session.state == "open":
                active_session.action_expire()
            active_session = Session

        if not active_session:
            active_session = Session.create({
                "partner_id": partner.id,
                "active_company_id": partner.whatsapp_active_company_id.id if partner.whatsapp_active_company_id else False,
                "phone": identifiers.get("phone") or partner.whatsapp_number or self._clean_phone(partner.mobile),
                "jid": identifiers.get("jid") or partner.whatsapp_jid,
                "lid": identifiers.get("lid") or partner.whatsapp_lid,
                "raw_jid": identifiers.get("raw_jid") or partner.whatsapp_last_raw_jid,
                "state": "human" if partner.whatsapp_human_mode else "open",
                "source": "whatsapp",
                "last_intent": intent or False,
            })
        else:
            vals = {
                "last_message_at": fields.Datetime.now(),
                "active_company_id": partner.whatsapp_active_company_id.id if partner.whatsapp_active_company_id else False,
            }
            if identifiers.get("phone"):
                vals["phone"] = identifiers.get("phone")
            if identifiers.get("jid"):
                vals["jid"] = identifiers.get("jid")
            if identifiers.get("lid"):
                vals["lid"] = identifiers.get("lid")
            if identifiers.get("raw_jid"):
                vals["raw_jid"] = identifiers.get("raw_jid")
            if intent:
                vals["last_intent"] = intent
            if partner.whatsapp_human_mode:
                vals["state"] = "human"
            elif active_session.state == "human" and not partner.whatsapp_human_mode:
                vals["state"] = "open"

            active_session.write(vals)

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
            "phone": identifiers.get("phone") or False,
            "jid": identifiers.get("jid") or False,
            "lid": identifiers.get("lid") or False,
            "raw_jid": identifiers.get("raw_jid") or False,
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
            "phone": identifiers.get("phone") or False,
            "jid": identifiers.get("jid") or False,
            "lid": identifiers.get("lid") or False,
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
    # Enlaces configurables
    # ==========================================================
    def _get_base_url(self):
        return request.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")

    def _get_toner_url(self, partner=False, company=False, machine=False):
        ICP = request.env["ir.config_parameter"].sudo()
        base = self._get_base_url()
        url = ICP.get_param("sat.whatsapp_toner_url") or "%s/solicitud-toner" % base

        params = []
        if partner:
            params.append("partner_id=%s" % partner.id)
        if company:
            params.append("company_id=%s" % company.id)
        if machine:
            params.append("machine_id=%s" % machine.id)

        if params:
            joiner = "&" if "?" in url else "?"
            url = "%s%s%s" % (url, joiner, "&".join(params))

        return url

    def _get_service_url(self, partner=False, company=False, machine=False):
        ICP = request.env["ir.config_parameter"].sudo()
        base = self._get_base_url()
        url = ICP.get_param("sat.whatsapp_service_url") or "%s/solicitud-servicio" % base

        params = []
        if partner:
            params.append("partner_id=%s" % partner.id)
        if company:
            params.append("company_id=%s" % company.id)
        if machine:
            params.append("machine_id=%s" % machine.id)

        if params:
            joiner = "&" if "?" in url else "?"
            url = "%s%s%s" % (url, joiner, "&".join(params))

        return url

    # ==========================================================
    # Máquinas alquiladas
    # ==========================================================
    def _field_exists(self, model, field_name):
        return field_name in model._fields

    def _get_machine_label(self, machine):
        name = machine.display_name or machine.name or "Equipo"

        model_name = ""
        for field in ["modelo_id", "model_id", "modelo", "model", "equipo_modelo_id"]:
            if field in machine._fields:
                value = machine[field]
                if value:
                    model_name = value.display_name if hasattr(value, "display_name") else str(value)
                    break

        serie = ""
        for field in ["serie", "serial", "serial_number", "numero_serie", "nro_serie", "codigo_serie"]:
            if field in machine._fields and machine[field]:
                serie = machine[field]
                break

        ubicacion = ""
        for field in ["ubicacion", "location", "direccion", "address", "oficina", "area"]:
            if field in machine._fields and machine[field]:
                value = machine[field]
                ubicacion = value.display_name if hasattr(value, "display_name") else str(value)
                break

        parts = []
        if model_name:
            parts.append(model_name)
        else:
            parts.append(name)
        if serie:
            parts.append("Serie: %s" % serie)
        if ubicacion:
            parts.append("Ubicación: %s" % ubicacion)

        return " | ".join(parts)

    def _record_matches_partner_company(self, rec, partner=False, company=False):
        partner_ids = set()
        partner_names = set()
        partner_vats = set()

        if partner:
            partner_ids.add(partner.id)
            if partner.name:
                partner_names.add(partner.name.strip().lower())
            if partner.vat:
                partner_vats.add(str(partner.vat).strip())

        if company:
            partner_ids.add(company.id)
            if company.name:
                partner_names.add(company.name.strip().lower())
            if company.vat:
                partner_vats.add(str(company.vat).strip())

        if not partner_ids and not partner_names and not partner_vats:
            return False

        candidate_fields = [
            "partner_id",
            "cliente_id",
            "customer_id",
            "empresa_id",
            "company_partner_id",
            "res_partner_id",
            "contacto_id",
            "titular_id",
            "cliente",
            "empresa",
            "razon_social",
            "ruc",
            "vat",
        ]

        for field in candidate_fields:
            if field not in rec._fields:
                continue

            value = rec[field]

            if not value:
                continue

            # Many2one / recordset
            if hasattr(value, "id"):
                if value.id in partner_ids:
                    return True

                if getattr(value, "name", False):
                    if value.name.strip().lower() in partner_names:
                        return True

                if getattr(value, "vat", False):
                    if str(value.vat).strip() in partner_vats:
                        return True

                continue

            # Char / Text / Selection / cualquier valor simple
            value_text = str(value).strip()
            value_lower = value_text.lower()

            if value_lower in partner_names:
                return True

            if value_text in partner_vats:
                return True

        return False
    def _get_partner_machines(self, partner, limit=20):
        if "alquiler" not in request.env or not partner:
            return request.env["ir.model"].sudo().browse()

        Machine = request.env["alquiler"].sudo()
        company = partner.whatsapp_active_company_id if partner.whatsapp_active_company_id else False

        domain = []
        fields_map = Machine._fields

        state_field = False
        for candidate in ["state", "estado", "status"]:
            if candidate in fields_map:
                state_field = candidate
                break

        if state_field:
            domain = [
                (state_field, "not in", ["cancel", "cancelado", "baja", "retirado", "finalizado", "closed"])
            ]

        records = Machine.search(domain, limit=200, order="id desc")

        matched = request.env["alquiler"].sudo()
        for rec in records:
            if self._record_matches_partner_company(rec, partner=partner, company=company):
                matched |= rec
            if len(matched) >= limit:
                break

        if not matched and company:
            records = Machine.search([], limit=200, order="id desc")
            for rec in records:
                if self._record_matches_partner_company(rec, partner=company, company=company):
                    matched |= rec
                if len(matched) >= limit:
                    break

        return matched[:limit]

    def _build_machine_menu(self, machines, title, footer=None, include_link=False, link=False):
        lines = [title, ""]
        index = 1
        for machine in machines:
            lines.append("%s. %s" % (index, self._get_machine_label(machine)))
            index += 1

        if include_link and link:
            lines.append("")
            lines.append("También puedes usar este formulario:")
            lines.append(link)

        if footer:
            lines.append("")
            lines.append(footer)

        return "\n".join(lines)

    def _get_context_machine(self, context):
        machine_id = context.get("machine_id")
        if not machine_id or "alquiler" not in request.env:
            return False
        return request.env["alquiler"].sudo().browse(int(machine_id)).exists()

    # ==========================================================
    # Conversación: lectura básica
    # ==========================================================
    def _parse_menu_index(self, text):
        digits = self._only_digits(text)
        if not digits:
            return False
        try:
            return int(digits)
        except Exception:
            return False

    def _is_yes(self, text):
        text = (text or "").strip().lower()
        return text in ["si", "sí", "ok", "okay", "confirmo", "confirmar", "correcto", "dale", "ya"]

    def _is_no(self, text):
        text = (text or "").strip().lower()
        return text in ["no", "cancelar", "cancela", "anular", "salir"]

    def _looks_like_dni(self, text):
        digits = self._only_digits(text)
        return len(digits) == 8

    def _looks_like_ruc(self, text):
        digits = self._only_digits(text)
        return len(digits) == 11 and digits.startswith(("10", "20"))

    def _looks_like_anydesk(self, text):
        digits = self._only_digits(text)
        return len(digits) >= 6 and len(digits) <= 12

    # ==========================================================
    # Creación genérica de documentos
    # ==========================================================
    def _safe_model_create(self, model_name, preferred_vals):
        if model_name not in request.env:
            return False, "Modelo no encontrado: %s" % model_name

        Model = request.env[model_name].sudo()
        vals = {}

        for key, value in preferred_vals.items():
            if key in Model._fields:
                vals[key] = value

        try:
            rec = Model.create(vals)
            return rec, False
        except Exception as e:
            _logger.exception("[SAT-WHATSAPP-API] Error creando %s vals=%s", model_name, vals)
            return False, str(e)

    def _create_toner_request(self, partner, session, context):
        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False
        machine = self._get_context_machine(context)

        description = (
            "Solicitud de tóner vía WhatsApp\n"
            "Equipo: %s\n"
            "Color: %s\n"
            "Cantidad: %s\n"
            "Contador B/N: %s\n"
            "Contador color: %s\n"
            "Observaciones: %s"
        ) % (
            self._get_machine_label(machine) if machine else "",
            context.get("toner_color") or "",
            context.get("toner_quantity") or "",
            context.get("counter_bn") or "",
            context.get("counter_color") or "",
            context.get("observations") or "",
        )

        possible_models = [
            "toner.solicitud",
            "toner.solicitudes",
            "toner.delivery",
            "toner.request",
        ]

        preferred_vals = {
            "name": "Solicitud de tóner WhatsApp",
            "partner_id": partner.id if partner else False,
            "cliente_id": partner.id if partner else False,
            "company_id": company.id if company else False,
            "empresa_id": company.id if company else False,
            "alquiler_id": machine.id if machine else False,
            "machine_id": machine.id if machine else False,
            "equipo_id": machine.id if machine else False,
            "color": context.get("toner_color") or False,
            "cantidad": context.get("toner_quantity") or False,
            "quantity": context.get("toner_quantity") or False,
            "contador_bn": context.get("counter_bn") or False,
            "contador_color": context.get("counter_color") or False,
            "observaciones": context.get("observations") or False,
            "description": description,
            "descripcion": description,
            "origen": "whatsapp",
            "source": "whatsapp",
            "whatsapp_session_id": session.id if session else False,
        }

        for model_name in possible_models:
            if model_name in request.env:
                rec, error = self._safe_model_create(model_name, preferred_vals)
                if rec:
                    return rec, False
                return False, error

        return False, "No se encontró modelo de solicitud de tóner."

    def _create_service_ticket(self, partner, session, context, payload=False):
        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False
        machine = self._get_context_machine(context)
        payload = payload or {}

        description = context.get("service_description") or payload.get("message") or payload.get("text") or ""

        preferred_vals = {
            "name": "Servicio presencial WhatsApp",
            "partner_id": partner.id if partner else False,
            "cliente_id": partner.id if partner else False,
            "company_id": company.id if company else False,
            "empresa_id": company.id if company else False,
            "alquiler_id": machine.id if machine else False,
            "machine_id": machine.id if machine else False,
            "equipo_id": machine.id if machine else False,
            "descripcion": description,
            "description": description,
            "problema": description,
            "falla_reportada": description,
            "observaciones": description,
            "origen": "whatsapp",
            "source": "whatsapp",
            "whatsapp_session_id": session.id if session else False,
        }

        rec, error = self._safe_model_create("ticket.alquiler", preferred_vals)
        return rec, error

    # ==========================================================
    # Registro inline para /process
    # ==========================================================
    def _register_dni_inline(self, identifiers, dni, payload=False):
        Partner = request.env["res.partner"].sudo()
        partner = self._find_partner_by_identifiers(identifiers)

        vals = self._prepare_partner_whatsapp_values(identifiers)
        vals["vat"] = dni
        vals["whatsapp_registration_state"] = "waiting_ruc"

        dni_type = self._get_dni_type()
        if dni_type and "l10n_latam_identification_type_id" in Partner._fields:
            vals["l10n_latam_identification_type_id"] = dni_type.id

        if not partner:
            vals.setdefault("name", "DNI %s" % dni)
            partner = Partner.create(vals)
        else:
            partner.write(vals)

        self._update_partner_identifiers(partner, identifiers)

        try:
            self._run_partner_document_autoload(partner)
        except Exception:
            _logger.exception("[SAT-WHATSAPP-API] Error cargando datos DNI")
            partner.write({"whatsapp_registration_state": "manual_review"})

        session = self._get_or_create_session(partner, identifiers, intent="dni")

        message = self._render_template(
            "ask_ruc",
            partner=partner,
            session=session,
            fallback="Gracias. Ahora envíame el RUC de tu empresa para completar el registro.",
        )

        return partner, session, message

    def _register_ruc_inline(self, contact, identifiers, ruc, payload=False):
        Partner = request.env["res.partner"].sudo()

        company = Partner.search([("vat", "=", ruc), ("is_company", "=", True)], limit=1)
        company_created = False

        if not company:
            vals = {
                "name": "RUC %s" % ruc,
                "vat": ruc,
                "is_company": True,
                "company_type": "company",
                "whatsapp_registration_state": "registered",
            }

            ruc_type = self._get_ruc_type()
            if ruc_type and "l10n_latam_identification_type_id" in Partner._fields:
                vals["l10n_latam_identification_type_id"] = ruc_type.id

            company = Partner.create(vals)
            company_created = True

            try:
                self._run_partner_document_autoload(company)
            except Exception:
                _logger.exception("[SAT-WHATSAPP-API] Error cargando datos RUC")

        contact.write({
            "whatsapp_company_ids": [(4, company.id)],
            "whatsapp_active_company_id": company.id,
            "whatsapp_registration_state": "registered",
        })

        company.write({
            "whatsapp_registration_state": "registered",
        })

        session = self._get_or_create_session(contact, identifiers, intent="ruc")
        session.write({"active_company_id": company.id})

        message = self._render_template(
            "registration_completed",
            partner=contact,
            session=session,
            company=company,
            fallback="Registro completado correctamente. ¿En qué podemos ayudarte?",
        )

        return company, session, message, company_created

    # ==========================================================
    # Flujos: iniciar
    # ==========================================================
    def _start_toner_flow(self, partner, session, identifiers, payload=False):
        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False
        machines = self._get_partner_machines(partner)

        if not machines:
            handoff = request.env["whatsapp.handoff"].sudo().create_unknown_intent_handoff(
                partner,
                session=session,
                initial_message=(payload or {}).get("message") or (payload or {}).get("text") or "",
                context={"reason": "No se encontraron equipos alquilados para tóner."},
            )
            partner.whatsapp_enable_human_mode_api(taken_by_name="Bot WhatsApp")
            session.action_set_human()
            return (
                "No encontré equipos alquilados asociados a tu empresa. "
                "Voy a derivarte con un asesor para ayudarte con la solicitud de tóner."
            )

        link = self._get_toner_url(partner=partner, company=company)

        options = []
        for machine in machines:
            options.append({
                "id": machine.id,
                "label": self._get_machine_label(machine),
            })

        session.start_flow(
            "toner",
            "awaiting_machine_selection_toner",
            context={
                "intent": "toner",
                "machine_options": options,
                "form_url": link,
            },
        )

        return self._build_machine_menu(
            machines,
            "Claro. Estos son tus equipos alquilados. Responde con el número del equipo para solicitar tóner:",
            footer="También puedes escribir LINK si prefieres llenar el formulario.",
            include_link=True,
            link=link,
        )

    def _start_onsite_flow(self, partner, session, identifiers, payload=False):
        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False
        machines = self._get_partner_machines(partner)

        if not machines:
            request.env["whatsapp.handoff"].sudo().create_onsite_handoff(
                partner,
                session=session,
                initial_message=(payload or {}).get("message") or (payload or {}).get("text") or "",
                context={"reason": "No se encontraron equipos alquilados para servicio presencial."},
            )
            partner.whatsapp_enable_human_mode_api(taken_by_name="Bot WhatsApp")
            session.action_set_human()
            return (
                "No encontré equipos alquilados asociados a tu empresa. "
                "Voy a derivarte con un asesor para registrar tu servicio."
            )

        link = self._get_service_url(partner=partner, company=company)

        options = []
        for machine in machines:
            options.append({
                "id": machine.id,
                "label": self._get_machine_label(machine),
            })

        session.start_flow(
            "onsite",
            "awaiting_machine_selection_onsite",
            context={
                "intent": "onsite_service",
                "machine_options": options,
                "form_url": link,
            },
        )

        return self._build_machine_menu(
            machines,
            "De acuerdo. Selecciona el equipo para el servicio presencial:",
            footer="También puedes escribir LINK si prefieres llenar el formulario.",
            include_link=True,
            link=link,
        )

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
                "También puedes enviar una foto de la pantalla donde aparece el código."
            ),
        )

    # ==========================================================
    # Flujos: continuación
    # ==========================================================
    def _continue_toner_flow(self, partner, session, identifiers, text, payload=False):
        context = session.get_context()
        text_clean = (text or "").strip()

        if text_clean.lower() in ["link", "enlace", "url", "formulario"]:
            link = context.get("form_url") or self._get_toner_url(
                partner=partner,
                company=partner.whatsapp_active_company_id if partner else False,
            )
            return "Puedes registrar tu solicitud de tóner aquí:\n%s" % link

        if self._is_no(text_clean) and session.conversation_state not in [
            "awaiting_toner_counter_bn",
            "awaiting_toner_counter_color",
            "awaiting_toner_observations",
        ]:
            session.reset_conversation(reason="abandoned")
            return "Listo, cancelé la solicitud de tóner. Si necesitas algo más, escríbenos."
        state = session.conversation_state

        if state == "awaiting_machine_selection_toner":
            index = self._parse_menu_index(text_clean)
            options = context.get("machine_options") or []

            if not index or index < 1 or index > len(options):
                return "Por favor responde con el número del equipo de la lista."

            selected = options[index - 1]
            machine_id = selected.get("id")

            session.advance_state(
                "awaiting_toner_color",
                {
                    "machine_id": machine_id,
                    "machine_label": selected.get("label"),
                },
            )

            return (
                "Equipo seleccionado:\n%s\n\n"
                "¿Qué color de tóner necesitas?\n"
                "1. Negro\n"
                "2. Cyan\n"
                "3. Magenta\n"
                "4. Yellow\n"
                "5. Otro / no estoy seguro"
            ) % selected.get("label")

        if state == "awaiting_toner_color":
            color_map = {
                "1": "Negro",
                "2": "Cyan",
                "3": "Magenta",
                "4": "Yellow",
                "5": "Otro / no estoy seguro",
            }

            key = self._only_digits(text_clean)
            color = color_map.get(key)

            if not color:
                color_lower = text_clean.lower()
                if "negro" in color_lower or "black" in color_lower:
                    color = "Negro"
                elif "cyan" in color_lower or "cian" in color_lower:
                    color = "Cyan"
                elif "magenta" in color_lower:
                    color = "Magenta"
                elif "yellow" in color_lower or "amarillo" in color_lower:
                    color = "Yellow"
                else:
                    color = text_clean

            session.advance_state(
                "awaiting_toner_quantity",
                {"toner_color": color},
            )

            return "Perfecto. ¿Qué cantidad necesitas?"

        if state == "awaiting_toner_quantity":
            qty = self._only_digits(text_clean)
            if not qty:
                return "Por favor indica la cantidad en número. Ejemplo: 1"

            session.advance_state(
                "awaiting_toner_counter_bn",
                {"toner_quantity": qty},
            )

            return "Indícame el contador B/N actual del equipo. Si no lo tienes, escribe NO."

        if state == "awaiting_toner_counter_bn":
            value = self._only_digits(text_clean)
            if not value and not self._is_no(text_clean):
                return "Por favor envía el contador B/N en número o escribe NO."

            session.advance_state(
                "awaiting_toner_counter_color",
                {"counter_bn": value or "NO"},
            )

            return "Indícame el contador color actual. Si no aplica o no lo tienes, escribe NO."

        if state == "awaiting_toner_counter_color":
            value = self._only_digits(text_clean)
            if not value and not self._is_no(text_clean):
                return "Por favor envía el contador color en número o escribe NO."

            session.advance_state(
                "awaiting_toner_observations",
                {"counter_color": value or "NO"},
            )

            return "¿Deseas agregar alguna observación? Si no, escribe NO."

        if state == "awaiting_toner_observations":
            observations = "" if self._is_no(text_clean) else text_clean

            context = session.update_context({"observations": observations})

            summary = (
                "Confirma tu solicitud de tóner:\n\n"
                "Equipo: {machine}\n"
                "Color: {color}\n"
                "Cantidad: {qty}\n"
                "Contador B/N: {bn}\n"
                "Contador color: {color_counter}\n"
                "Observaciones: {obs}\n\n"
                "Responde SI para confirmar o NO para cancelar."
            ).format(
                machine=context.get("machine_label") or "",
                color=context.get("toner_color") or "",
                qty=context.get("toner_quantity") or "",
                bn=context.get("counter_bn") or "",
                color_counter=context.get("counter_color") or "",
                obs=context.get("observations") or "Sin observaciones",
            )

            session.advance_state("awaiting_toner_confirmation")

            return summary

        if state == "awaiting_toner_confirmation":
            if not self._is_yes(text_clean):
                if self._is_no(text_clean):
                    session.reset_conversation(reason="abandoned")
                    return "Listo, cancelé la solicitud de tóner."
                return "Por favor responde SI para confirmar o NO para cancelar."

            context = session.get_context()
            rec, error = self._create_toner_request(partner, session, context)

            if rec:
                session.complete_flow(close_reason="completed_toner")
                return (
                    "Solicitud de tóner registrada correctamente.\n"
                    "Número de referencia: %s"
                ) % (rec.display_name or rec.id)

            request.env["whatsapp.handoff"].sudo().create_unknown_intent_handoff(
                partner,
                session=session,
                initial_message=text_clean,
                context={
                    "reason": "No se pudo crear solicitud de tóner automáticamente.",
                    "error": error,
                    "flow_context": context,
                },
            )
            partner.whatsapp_enable_human_mode_api(taken_by_name="Bot WhatsApp")
            session.action_set_human()

            return (
                "Recibí la información, pero no pude registrar la solicitud automáticamente. "
                "Te estoy derivando con un asesor para completarla."
            )

        return "Estoy procesando tu solicitud de tóner. Por favor continúa con la información solicitada."

    def _continue_onsite_flow(self, partner, session, identifiers, text, payload=False):
        context = session.get_context()
        text_clean = (text or "").strip()

        if text_clean.lower() in ["link", "enlace", "url", "formulario"]:
            link = context.get("form_url") or self._get_service_url(
                partner=partner,
                company=partner.whatsapp_active_company_id if partner else False,
            )
            return "Puedes registrar tu servicio presencial aquí:\n%s" % link

        if self._is_no(text_clean) and session.conversation_state != "awaiting_service_photo":
            session.reset_conversation(reason="abandoned")
            return "Listo, cancelé la solicitud de servicio. Si necesitas algo más, escríbenos."

        state = session.conversation_state

        if state == "awaiting_machine_selection_onsite":
            index = self._parse_menu_index(text_clean)
            options = context.get("machine_options") or []

            if not index or index < 1 or index > len(options):
                return "Por favor responde con el número del equipo de la lista."

            selected = options[index - 1]
            session.advance_state(
                "awaiting_service_description",
                {
                    "machine_id": selected.get("id"),
                    "machine_label": selected.get("label"),
                },
            )

            return (
                "Equipo seleccionado:\n%s\n\n"
                "Por favor detállame el problema que presenta el equipo."
            ) % selected.get("label")

        if state == "awaiting_service_description":
            if len(text_clean) < 4:
                return "Por favor detalla un poco más el problema del equipo."

            session.advance_state(
                "awaiting_service_photo",
                {"service_description": text_clean},
            )

            return (
                "Gracias. Si tienes una foto del problema, envíala ahora. "
                "Si no tienes foto, escribe NO para registrar el servicio."
            )

        if state == "awaiting_service_photo":
            media = self._create_media_from_payload(
                session=session,
                partner=partner,
                message=False,
                payload=payload or {},
            )

            context_update = {}
            if media:
                context_update["media_id"] = media.id
                try:
                    media.mark_for_human_review(reason="Foto enviada para servicio presencial.")
                except Exception:
                    pass

            context = session.update_context(context_update)

            ticket, error = self._create_service_ticket(partner, session, context, payload=payload)

            if ticket:
                if media:
                    try:
                        media.attach_to_record("ticket.alquiler", ticket.id, purpose="service_issue")
                    except Exception:
                        pass

                session.complete_flow(close_reason="completed_onsite")
                return (
                    "Servicio presencial registrado correctamente.\n"
                    "Referencia: %s"
                ) % (ticket.display_name or ticket.id)

            request.env["whatsapp.handoff"].sudo().create_onsite_handoff(
                partner,
                session=session,
                machine=self._get_context_machine(context),
                initial_message=context.get("service_description") or text_clean,
                media=media if media else False,
                context={
                    "reason": "No se pudo crear ticket.alquiler automáticamente.",
                    "error": error,
                    "flow_context": context,
                },
            )
            partner.whatsapp_enable_human_mode_api(taken_by_name="Bot WhatsApp")
            session.action_set_human()

            return (
                "Recibí la información del servicio, pero no pude crear el ticket automáticamente. "
                "Te estoy derivando con un asesor."
            )

        return "Estoy procesando tu solicitud de servicio. Por favor continúa con la información solicitada."

    def _continue_remote_flow(self, partner, session, identifiers, text, payload=False):
        text_clean = (text or "").strip()
        state = session.conversation_state

        if self._is_no(text_clean):
            session.reset_conversation(reason="abandoned")
            return "Listo, cancelé la solicitud de soporte remoto."

        if state == "awaiting_anydesk_code":
            media = self._create_media_from_payload(
                session=session,
                partner=partner,
                message=False,
                payload=payload or {},
            )

            anydesk_code = False
            if self._looks_like_anydesk(text_clean):
                anydesk_code = self._only_digits(text_clean)

            if not anydesk_code and not media:
                return (
                    "Por favor envíanos tu código AnyDesk. "
                    "También puedes enviar una foto de la pantalla donde aparece el código."
                )

            context = session.update_context({
                "anydesk_code": anydesk_code or False,
                "remote_problem": (payload or {}).get("message") or (payload or {}).get("text") or "",
                "media_id": media.id if media else False,
            })

            if media:
                try:
                    media.mark_for_human_review(reason="Foto de AnyDesk enviada por cliente.")
                except Exception:
                    pass

            handoff = request.env["whatsapp.handoff"].sudo().create_remote_support_handoff(
                partner,
                session=session,
                machine=False,
                anydesk_code=anydesk_code,
                initial_message=text_clean,
                media=media if media else False,
                context=context,
            )

            partner.whatsapp_enable_human_mode_api(taken_by_name="Bot WhatsApp")
            session.action_set_human()

            return (
                "Gracias. Ya derivé tu solicitud a un técnico para soporte remoto. "
                "Un asesor continuará la atención."
            )

        return (
            "Para soporte remoto, envíanos tu código AnyDesk "
            "o una foto de la pantalla donde aparece el código."
        )

    def _continue_active_flow(self, partner, session, identifiers, text, payload=False):
        if session.is_conversation_expired():
            session.reset_conversation(reason="expired")
            return "El flujo anterior expiró por inactividad. Por favor vuelve a escribir tu solicitud."

        if session.current_flow == "toner":
            return self._continue_toner_flow(partner, session, identifiers, text, payload=payload)

        if session.current_flow == "onsite":
            return self._continue_onsite_flow(partner, session, identifiers, text, payload=payload)

        if session.current_flow == "remote":
            return self._continue_remote_flow(partner, session, identifiers, text, payload=payload)

        return False

    # ==========================================================
    # Intención y acciones
    # ==========================================================
    def _detect_intent(self, message_text, partner=False, business_status=False, session=False):
        applies_to = self._get_applies_to(partner, business_status=business_status) if partner else "new"

        try:
            result = request.env["whatsapp.intent.rule"].sudo().detect_intent(
                message=message_text,
                partner=partner if partner else False,
                applies_to=applies_to,
                is_after_hours=not business_status.get("is_open"),
                current_flow=session.current_flow if session else False,
            )
            result = result or {"found": False}
        except TypeError:
            result = request.env["whatsapp.intent.rule"].sudo().detect_intent(
                message=message_text,
                partner=partner if partner else False,
                applies_to=applies_to,
                is_after_hours=not business_status.get("is_open"),
            )
            result = result or {"found": False}
        except Exception:
            _logger.exception("[SAT-WHATSAPP-API] Error detectando intención")
            result = {"found": False}

        return result, applies_to

    def _execute_intent_action(self, partner, session, identifiers, message_text, intent_result, business_status, payload=False):
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
            return self._company_selection_message(partner, session)

        if action == "start_flow_toner" or intent == "toner":
            return self._start_toner_flow(partner, session, identifiers, payload=payload)

        if action == "start_flow_onsite" or intent in ["onsite_service", "service", "printer_issue"]:
            return self._start_onsite_flow(partner, session, identifiers, payload=payload)

        if action == "start_flow_remote" or intent in ["remote_service", "anydesk", "scanner"]:
            return self._start_remote_flow(partner, session, identifiers, payload=payload)

        if action == "send_service_link":
            link = self._get_service_url(
                partner=partner,
                company=partner.whatsapp_active_company_id if partner else False,
            )
            return "Puedes registrar tu solicitud aquí:\n%s" % link

        if action == "handoff" or intent == "human":
            request.env["whatsapp.handoff"].sudo().create_unknown_intent_handoff(
                partner,
                session=session,
                initial_message=message_text,
                context={"intent": intent, "action": action},
            )
            partner.whatsapp_enable_human_mode_api(taken_by_name="Bot WhatsApp")
            session.action_set_human()
            return "De acuerdo. Voy a derivarte con un asesor para continuar la atención."

        if intent == "greeting":
            return self._get_greeting_message(partner=partner, session=session, business_status=business_status)

        if intent == "thanks":
            return "Gracias a ti. ¿Necesitas algo más?"

        if intent == "goodbye":
            return "Gracias por comunicarte con nosotros. Que tengas buen día."

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
    # Empresas
    # ==========================================================
    def _company_selection_message(self, partner, session=False):
        if not partner:
            return "No pude identificar el contacto."

        companies = partner._get_whatsapp_available_companies()
        if not companies:
            return "No tienes empresas asociadas todavía. Por favor envíame el RUC de tu empresa."

        if len(companies) == 1:
            partner.whatsapp_set_active_company(companies[0])
            return "Empresa seleccionada: %s. ¿En qué podemos ayudarte?" % companies[0].name

        options = []
        lines = [
            "Tienes más de una empresa asociada. Responde con el número de la empresa:",
            "",
        ]

        idx = 1
        for company in companies:
            options.append({
                "id": company.id,
                "name": company.name,
                "vat": company.vat,
            })
            lines.append("%s. %s%s" % (
                idx,
                company.name,
                " | RUC: %s" % company.vat if company.vat else "",
            ))
            idx += 1

        if session:
            session.start_flow(
                "registration",
                "awaiting_company_selection",
                context={
                    "company_options": options,
                },
            )

        return "\n".join(lines)

    def _continue_company_selection(self, partner, session, text):
        context = session.get_context()
        options = context.get("company_options") or []
        index = self._parse_menu_index(text)

        if not index or index < 1 or index > len(options):
            return "Por favor responde con el número de la empresa de la lista."

        selected = options[index - 1]
        company = request.env["res.partner"].sudo().browse(selected.get("id")).exists()
        if not company:
            return "No pude encontrar la empresa seleccionada. Intenta nuevamente."

        partner.whatsapp_set_active_company(company)
        session.complete_flow(close_reason="completed_registration")

        return "Empresa seleccionada: %s. ¿En qué podemos ayudarte?" % company.name

    # ==========================================================
    # Endpoint central: procesar conversación completa
    # ==========================================================
    @http.route("/sat/whatsapp/process", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_process(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/process"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        if not self._has_any_identifier(identifiers):
            response = self._json_error("Número, JID o LID requerido", "IDENTIFIER_REQUIRED", 400)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="IDENTIFIER_REQUIRED", start_ts=start_ts)
            return response

        message_text = payload.get("message") or payload.get("text") or payload.get("content") or ""
        message_type = payload.get("message_type") or "text"
        external_message_id = payload.get("message_id") or payload.get("external_message_id") or False
        force_new_session = bool(payload.get("force_new_session"))

        business_status = self._compute_business_status()
        partner = self._find_partner_by_identifiers(identifiers)

        try:
            # ==================================================
            # 1) Contacto no existe: pedir DNI o registrar DNI
            # ==================================================
            if not partner:
                if self._looks_like_dni(message_text):
                    partner, session, reply = self._register_dni_inline(
                        identifiers,
                        self._only_digits(message_text),
                        payload=payload,
                    )

                    self._record_whatsapp_message(
                        session=session,
                        partner=partner,
                        identifiers=identifiers,
                        role="user",
                        direction="in",
                        message_type=message_type,
                        content=message_text,
                        intent="dni",
                        payload=payload,
                        external_message_id=external_message_id,
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
                        "registered_dni": True,
                        "next_step": "waiting_ruc",
                        "partner_id": partner.id,
                        "session_id": session.id,
                        "message": reply,
                        "outbox_id": emitted.get("outbox_id"),
                        "profile": partner.get_whatsapp_profile_payload(),
                    }
                    self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
                    return response

                response_message = self._render_template(
                    "ask_dni",
                    fallback="Para poder ayudarte, por favor envíame tu DNI de 8 dígitos.",
                )

                response = {
                    "ok": True,
                    "found": False,
                    "next_step": "waiting_dni",
                    "message": response_message,
                    "suggested": {
                        "template": "ask_dni",
                        "message": response_message,
                    },
                    "business": business_status,
                }
                self._safe_log_api(endpoint, payload, response, identifiers, status="not_found", start_ts=start_ts)
                return response

            self._update_partner_identifiers(partner, identifiers)
            session = self._get_or_create_session(
                partner,
                identifiers,
                force_new_session=force_new_session,
            )

            try:
                partner.whatsapp_touch_message(force_new_session=force_new_session)
            except Exception:
                _logger.exception("[SAT-WHATSAPP-API] No se pudo actualizar touch partner")

            # ==================================================
            # 2) Registrar mensaje entrante
            # ==================================================
            incoming = self._record_whatsapp_message(
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

            # ==================================================
            # 3) Bloqueado / modo humano
            # ==================================================
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
                self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
                return response

            if partner.whatsapp_human_mode or session.state == "human":
                response = {
                    "ok": True,
                    "found": True,
                    "human_mode": True,
                    "partner_id": partner.id,
                    "session_id": session.id,
                    "message": False,
                    "business": business_status,
                    "profile": partner.get_whatsapp_profile_payload(),
                }
                self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
                return response

            # ==================================================
            # 4) Registro DNI/RUC
            # ==================================================
            registration_state = getattr(partner, "whatsapp_registration_state", "none")

            if registration_state in ("none", "waiting_dni"):
                if self._looks_like_dni(message_text):
                    partner, session, reply = self._register_dni_inline(
                        identifiers,
                        self._only_digits(message_text),
                        payload=payload,
                    )
                else:
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
                    "next_step": "waiting_ruc" if self._looks_like_dni(message_text) else "waiting_dni",
                    "partner_id": partner.id,
                    "session_id": session.id,
                    "message": reply,
                    "outbox_id": emitted.get("outbox_id"),
                    "business": business_status,
                    "profile": partner.get_whatsapp_profile_payload(),
                }
                self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
                return response

            if registration_state == "waiting_ruc":
                if self._looks_like_ruc(message_text):
                    company, session, reply, company_created = self._register_ruc_inline(
                        partner,
                        identifiers,
                        self._only_digits(message_text),
                        payload=payload,
                    )
                else:
                    reply = self._render_template(
                        "ask_ruc",
                        partner=partner,
                        session=session,
                        fallback="Gracias. Ahora envíame el RUC de tu empresa para completar el registro.",
                    )
                    company_created = False

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
                    "registered_ruc": self._looks_like_ruc(message_text),
                    "company_created": company_created,
                    "next_step": "registered" if self._looks_like_ruc(message_text) else "waiting_ruc",
                    "partner_id": partner.id,
                    "session_id": session.id,
                    "message": reply,
                    "outbox_id": emitted.get("outbox_id"),
                    "business": business_status,
                    "profile": partner.get_whatsapp_profile_payload(),
                }
                self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
                return response

            # ==================================================
            # 5) Selección de empresa pendiente
            # ==================================================
            if session.current_flow == "registration" and session.conversation_state == "awaiting_company_selection":
                reply = self._continue_company_selection(partner, session, message_text)
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
                self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
                return response

            if partner.whatsapp_requires_company_selection:
                reply = self._company_selection_message(partner, session=session)
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
                self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
                return response

            # ==================================================
            # 6) Horario/refrigerio: informa, pero permite registrar
            # ==================================================
            outside_hours_note = False
            if business_status and not business_status.get("is_open"):
                outside_hours_note = business_status.get("message") or ""

            # ==================================================
            # 7) Continuar flujo activo
            # ==================================================
            if session.current_flow != "none" and session.conversation_state != "idle":
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

                response = {
                    "ok": True,
                    "found": True,
                    "continued_flow": True,
                    "flow": session.current_flow,
                    "step": session.conversation_state,
                    "partner_id": partner.id,
                    "session_id": session.id,
                    "message": reply,
                    "outbox_id": emitted.get("outbox_id"),
                    "business": business_status,
                    "profile": partner.get_whatsapp_profile_payload(),
                }
                self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
                return response

            # ==================================================
            # 8) Detectar intención y ejecutar acción
            # ==================================================
            intent_result, applies_to = self._detect_intent(
                message_text,
                partner=partner,
                business_status=business_status,
                session=session,
            )

            reply = self._execute_intent_action(
                partner,
                session,
                identifiers,
                message_text,
                intent_result,
                business_status,
                payload=payload,
            )

            if outside_hours_note and reply:
                reply = "%s\n\n%s" % (outside_hours_note, reply)

            if not reply:
                response = {
                    "ok": True,
                    "found": True,
                    "ignored": True,
                    "partner_id": partner.id,
                    "session_id": session.id,
                    "message": False,
                    "intent": intent_result,
                    "business": business_status,
                    "profile": partner.get_whatsapp_profile_payload(),
                }
                self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
                return response

            emitted = self._emit_bot_reply(
                session=session,
                partner=partner,
                identifiers=identifiers,
                content=reply,
                intent=intent_result.get("intent") if intent_result else False,
                payload=payload,
            )

            response = {
                "ok": True,
                "found": True,
                "applies_to": applies_to,
                "partner_id": partner.id,
                "session_id": session.id,
                "message": reply,
                "outbox_id": emitted.get("outbox_id"),
                "message_id": emitted.get("message_id"),
                "intent": intent_result,
                "business": business_status,
                "profile": partner.get_whatsapp_profile_payload(),
            }
            self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
            return response

        except Exception as e:
            _logger.exception("[SAT-WHATSAPP-API] Error procesando conversación")
            response = self._json_error(str(e), "PROCESS_ERROR", 500)
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                partner=partner if partner else False,
                session=session if "session" in locals() and session else False,
                status="error",
                error_code="PROCESS_ERROR",
                error_message=str(e),
                start_ts=start_ts,
            )
            return response

    # ==========================================================
    # Endpoint: perfil
    # ==========================================================
    @http.route("/sat/whatsapp/profile", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_profile(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/profile"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        if not self._has_any_identifier(identifiers):
            response = self._json_error("Número, JID o LID requerido", "IDENTIFIER_REQUIRED", 400)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="IDENTIFIER_REQUIRED", start_ts=start_ts)
            return response

        partner = self._find_partner_by_identifiers(identifiers)
        business_status = self._compute_business_status()

        if not partner:
            suggested = self._build_suggested_message(
                partner=False,
                session=False,
                business_status=business_status,
            )

            response = {
                "ok": True,
                "found": False,
                "phone": identifiers.get("phone"),
                "jid": identifiers.get("jid"),
                "lid": identifiers.get("lid"),
                "raw_jid": identifiers.get("raw_jid"),
                "business": business_status,
                "suggested": suggested,
                "profile": None,
                "message": "Contacto no encontrado",
            }
            self._safe_log_api(endpoint, payload, response, identifiers, status="not_found", start_ts=start_ts)
            return response

        self._update_partner_identifiers(partner, identifiers)

        intent = payload.get("intent") or False
        force_new_session = bool(payload.get("force_new_session"))
        session = self._get_or_create_session(
            partner,
            identifiers,
            intent=intent,
            force_new_session=force_new_session,
        )

        suggested = self._build_suggested_message(
            partner=partner,
            session=session,
            business_status=business_status,
        )

        response = {
            "ok": True,
            "found": True,
            "phone": identifiers.get("phone"),
            "jid": identifiers.get("jid"),
            "lid": identifiers.get("lid"),
            "raw_jid": identifiers.get("raw_jid"),
            "partner_id": partner.id,
            "session_id": session.id if session else False,
            "session_name": session.name if session else False,
            "business": business_status,
            "suggested": suggested,
            "profile": partner.get_whatsapp_profile_payload(),
        }
        self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
        return response

    # ==========================================================
    # Endpoint: touch / mensaje entrante
    # ==========================================================
    @http.route("/sat/whatsapp/touch", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_touch(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/touch"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        if not self._has_any_identifier(identifiers):
            response = self._json_error("Número, JID o LID requerido", "IDENTIFIER_REQUIRED", 400)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="IDENTIFIER_REQUIRED", start_ts=start_ts)
            return response

        partner = self._find_partner_by_identifiers(identifiers)

        if not partner:
            response = {
                "ok": True,
                "found": False,
                "phone": identifiers.get("phone"),
                "jid": identifiers.get("jid"),
                "lid": identifiers.get("lid"),
                "message": "Contacto no encontrado. No se actualizó sesión.",
            }
            self._safe_log_api(endpoint, payload, response, identifiers, status="not_found", start_ts=start_ts)
            return response

        self._update_partner_identifiers(partner, identifiers)

        intent = payload.get("intent") or False
        force_new_session = bool(payload.get("force_new_session"))
        text = payload.get("message") or payload.get("text") or payload.get("content") or False
        message_type = payload.get("message_type") or "text"
        external_message_id = payload.get("message_id") or payload.get("external_message_id") or False

        session = self._get_or_create_session(
            partner,
            identifiers,
            intent=intent,
            force_new_session=force_new_session,
        )

        partner.whatsapp_touch_message(
            intent=intent,
            force_new_session=force_new_session,
        )

        message = False
        if text or external_message_id or message_type != "text":
            message = self._record_whatsapp_message(
                session=session,
                partner=partner,
                identifiers=identifiers,
                role="user",
                direction="in",
                message_type=message_type,
                content=text,
                intent=intent,
                payload=payload,
                external_message_id=external_message_id,
            )

        response = {
            "ok": True,
            "found": True,
            "phone": identifiers.get("phone"),
            "jid": identifiers.get("jid"),
            "lid": identifiers.get("lid"),
            "partner_id": partner.id,
            "session_id": session.id if session else False,
            "message_id": message.id if message else False,
            "profile": partner.get_whatsapp_profile_payload(),
        }
        self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
        return response

    # ==========================================================
    # Endpoint: horario/calendario
    # ==========================================================
    @http.route("/sat/whatsapp/business/status", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_business_status(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/business/status"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        status = self._compute_business_status()
        template_name = "business_open" if status.get("is_open") else "after_hours"

        suggested = {
            "template": template_name,
            "message": self._render_template(
                template_name,
                extra={
                    "business_message": status.get("message") or "",
                    "display_hours": status.get("display_hours") or "",
                    "reason": status.get("reason_label") or "",
                },
                fallback=status.get("message") or "",
            ),
        }

        response = {
            "ok": True,
            "business": status,
            "suggested": suggested,
        }
        self._safe_log_api(endpoint, payload, response, identifiers, start_ts=start_ts)
        return response

    # ==========================================================
    # Endpoint: auto respuesta
    # ==========================================================
    @http.route("/sat/whatsapp/auto-response", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_auto_response(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/auto-response"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        message_text = payload.get("message") or payload.get("text") or ""
        partner = (
            self._find_partner_by_identifiers(identifiers)
            if self._has_any_identifier(identifiers)
            else request.env["res.partner"].sudo()
        )

        business_status = self._compute_business_status()
        applies_to = self._get_applies_to(partner, business_status=business_status) if partner else "new"

        result = request.env["whatsapp.auto.response"].sudo().find_response(
            message=message_text,
            partner=partner if partner else False,
            applies_to=applies_to,
            is_after_hours=not business_status.get("is_open"),
            extra={
                "business_message": business_status.get("message") or "",
            },
            current_flow=False,
        )

        response = {
            "ok": True,
            "found": bool(result.get("found")),
            "applies_to": applies_to,
            "business": business_status,
            "auto_response": result,
        }
        self._safe_log_api(endpoint, payload, response, identifiers, partner=partner if partner else False, start_ts=start_ts)
        return response

    # ==========================================================
    # Endpoint: intención
    # ==========================================================
    @http.route("/sat/whatsapp/intent", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_intent(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/intent"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        message_text = payload.get("message") or payload.get("text") or ""
        partner = (
            self._find_partner_by_identifiers(identifiers)
            if self._has_any_identifier(identifiers)
            else request.env["res.partner"].sudo()
        )

        business_status = self._compute_business_status()
        session = False
        if partner:
            session = self._get_or_create_session(partner, identifiers)

        result, applies_to = self._detect_intent(
            message_text,
            partner=partner if partner else False,
            business_status=business_status,
            session=session if session else False,
        )

        response = {
            "ok": True,
            "found": bool(result.get("found")),
            "applies_to": applies_to,
            "business": business_status,
            "intent": result,
        }
        self._safe_log_api(endpoint, payload, response, identifiers, partner=partner if partner else False, session=session if session else False, start_ts=start_ts)
        return response

    # ==========================================================
    # Endpoint: render plantilla
    # ==========================================================
    @http.route("/sat/whatsapp/template/render", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_template_render(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/template/render"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        template_name = payload.get("template") or payload.get("template_name") or payload.get("name")

        if not template_name:
            response = self._json_error("Nombre de plantilla requerido.", "TEMPLATE_REQUIRED", 400)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="TEMPLATE_REQUIRED", start_ts=start_ts)
            return response

        partner = False
        session = False
        company = False

        if self._has_any_identifier(identifiers):
            partner = self._find_partner_by_identifiers(identifiers)
            if partner:
                session = self._get_or_create_session(partner, identifiers)
                company = partner.whatsapp_active_company_id if partner.whatsapp_active_company_id else False

        text = self._render_template(
            template_name,
            partner=partner if partner else False,
            session=session if session else False,
            company=company if company else False,
            extra=payload.get("extra") or {},
            fallback=False,
        )

        response = {
            "ok": True,
            "found": bool(text),
            "template": template_name,
            "message": text,
            "partner_id": partner.id if partner else False,
            "session_id": session.id if session else False,
        }

        self._safe_log_api(endpoint, payload, response, identifiers, partner=partner if partner else False, session=session if session else False, start_ts=start_ts)
        return response

    # ==========================================================
    # Endpoint: mensaje saliente / outbox
    # ==========================================================
    @http.route("/sat/whatsapp/message/out", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_message_out(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/message/out"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        content = payload.get("message") or payload.get("text") or payload.get("content") or ""
        message_type = payload.get("message_type") or "text"
        template_name = payload.get("template") or payload.get("template_name")

        if not self._has_any_identifier(identifiers):
            response = self._json_error("Número, JID o LID requerido", "IDENTIFIER_REQUIRED", 400)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="IDENTIFIER_REQUIRED", start_ts=start_ts)
            return response

        partner = self._find_partner_by_identifiers(identifiers)

        if not partner:
            response = self._json_error("Contacto no encontrado.", "CONTACT_NOT_FOUND", 404)
            self._safe_log_api(endpoint, payload, response, identifiers, status="not_found", start_ts=start_ts)
            return response

        session = self._get_or_create_session(partner, identifiers)

        if template_name and not content:
            content = self._render_template(
                template_name,
                partner=partner,
                session=session,
                company=partner.whatsapp_active_company_id if partner.whatsapp_active_company_id else False,
                extra=payload.get("extra") or {},
                fallback="",
            )

        emitted = self._emit_bot_reply(
            session=session,
            partner=partner,
            identifiers=identifiers,
            content=content,
            intent=payload.get("intent") or False,
            payload=payload,
            message_type=message_type,
            create_outbox=True,
        )

        response = {
            "ok": True,
            "partner_id": partner.id,
            "session_id": session.id,
            "message_id": emitted.get("message_id"),
            "outbox_id": emitted.get("outbox_id"),
            "state": "pending",
            "message": content,
        }
        self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
        return response

    # ==========================================================
    # Endpoint: outbox pendientes
    # ==========================================================
    @http.route("/sat/whatsapp/outbox/pending", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_outbox_pending(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/outbox/pending"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        limit = int(payload.get("limit") or 20)
        Outbox = request.env["whatsapp.outbox"].sudo()

        records = Outbox.search([
            ("state", "in", ["pending", "queued"]),
            "|",
            ("next_retry_at", "<=", fields.Datetime.now()),
            "&",
            ("next_retry_at", "=", False),
            ("scheduled_at", "<=", fields.Datetime.now()),
        ], order="priority desc, scheduled_at asc, id asc", limit=limit)

        items = []
        for rec in records:
            try:
                rec.action_mark_queued()
            except Exception:
                _logger.exception("[SAT-WHATSAPP-API] No se pudo marcar queued outbox=%s", rec.id)

            items.append({
                "id": rec.id,
                "outbox_id": rec.id,
                "phone": rec.phone,
                "jid": rec.jid,
                "lid": rec.lid,
                "message_type": rec.message_type,
                "content": rec.content,
                "partner_id": rec.partner_id.id if rec.partner_id else False,
                "session_id": rec.session_id.id if rec.session_id else False,
                "media_id": rec.media_id.id if rec.media_id else False,
                "current_flow": rec.current_flow,
                "flow_step": rec.flow_step,
            })

        response = {
            "ok": True,
            "count": len(items),
            "items": items,
        }
        self._safe_log_api(endpoint, payload, response, identifiers, start_ts=start_ts)
        return response

    # ==========================================================
    # Endpoint: marcar outbox enviado
    # ==========================================================
    @http.route("/sat/whatsapp/outbox/mark-sent", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_outbox_mark_sent(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/outbox/mark-sent"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        outbox_id = payload.get("outbox_id")
        external_message_id = payload.get("external_message_id") or payload.get("message_id") or False

        if not outbox_id:
            response = self._json_error("outbox_id requerido", "OUTBOX_ID_REQUIRED", 400)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="OUTBOX_ID_REQUIRED", start_ts=start_ts)
            return response

        outbox = request.env["whatsapp.outbox"].sudo().browse(int(outbox_id)).exists()
        if not outbox:
            response = self._json_error("Outbox no encontrado", "OUTBOX_NOT_FOUND", 404)
            self._safe_log_api(endpoint, payload, response, identifiers, status="not_found", error_code="OUTBOX_NOT_FOUND", start_ts=start_ts)
            return response

        outbox.action_mark_sent(external_message_id=external_message_id)

        response = {
            "ok": True,
            "outbox_id": outbox.id,
            "state": outbox.state,
            "external_message_id": outbox.external_message_id,
        }
        self._safe_log_api(endpoint, payload, response, identifiers, partner=outbox.partner_id, session=outbox.session_id, start_ts=start_ts)
        return response

    # ==========================================================
    # Endpoint: marcar outbox fallido
    # ==========================================================
    @http.route("/sat/whatsapp/outbox/mark-failed", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_outbox_mark_failed(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/outbox/mark-failed"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        outbox_id = payload.get("outbox_id")
        if not outbox_id:
            response = self._json_error("outbox_id requerido", "OUTBOX_ID_REQUIRED", 400)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="OUTBOX_ID_REQUIRED", start_ts=start_ts)
            return response

        outbox = request.env["whatsapp.outbox"].sudo().browse(int(outbox_id)).exists()
        if not outbox:
            response = self._json_error("Outbox no encontrado", "OUTBOX_NOT_FOUND", 404)
            self._safe_log_api(endpoint, payload, response, identifiers, status="not_found", error_code="OUTBOX_NOT_FOUND", start_ts=start_ts)
            return response

        outbox.action_mark_failed(
            error_message=payload.get("error_message") or "Error reportado por n8n/Baileys",
            error_code=payload.get("error_code") or False,
            schedule_retry=payload.get("schedule_retry", True),
        )

        response = {
            "ok": True,
            "outbox_id": outbox.id,
            "state": outbox.state,
            "retry_count": outbox.retry_count,
            "next_retry_at": outbox.next_retry_at,
        }
        self._safe_log_api(endpoint, payload, response, identifiers, partner=outbox.partner_id, session=outbox.session_id, start_ts=start_ts)
        return response

    # ==========================================================
    # Endpoint: tomar humano
    # ==========================================================
    @http.route("/sat/whatsapp/human/take", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_human_take(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/human/take"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        taken_by_name = payload.get("taken_by_name") or payload.get("agent_name") or "API / n8n"
        reason = payload.get("reason") or False

        if not self._has_any_identifier(identifiers):
            response = self._json_error("Número, JID o LID requerido", "IDENTIFIER_REQUIRED", 400)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="IDENTIFIER_REQUIRED", start_ts=start_ts)
            return response

        partner = self._find_partner_by_identifiers(identifiers)

        if not partner:
            response = {
                "ok": True,
                "found": False,
                "message": "Contacto no encontrado. No se activó modo humano.",
            }
            self._safe_log_api(endpoint, payload, response, identifiers, status="not_found", start_ts=start_ts)
            return response

        self._update_partner_identifiers(partner, identifiers)
        session = self._get_or_create_session(partner, identifiers)
        partner.whatsapp_enable_human_mode_api(taken_by_name=taken_by_name)
        session.action_set_human()

        request.env["whatsapp.handoff"].sudo().create({
            "session_id": session.id,
            "partner_id": partner.id,
            "company_id": partner.whatsapp_active_company_id.id if partner.whatsapp_active_company_id else False,
            "state": "open",
            "taken_by_name": taken_by_name,
            "reason": reason,
        })

        suggested = {
            "template": "human_take",
            "message": self._render_template(
                "human_take",
                partner=partner,
                session=session,
                fallback="Un asesor continuará con la atención.",
            ),
        }

        response = {
            "ok": True,
            "found": True,
            "partner_id": partner.id,
            "session_id": session.id,
            "suggested": suggested,
            "profile": partner.get_whatsapp_profile_payload(),
        }
        self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
        return response

    # ==========================================================
    # Endpoint: liberar humano
    # ==========================================================
    @http.route("/sat/whatsapp/human/release", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_human_release(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/human/release"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        released_by_name = payload.get("released_by_name") or payload.get("agent_name") or "API / n8n"

        if not self._has_any_identifier(identifiers):
            response = self._json_error("Número, JID o LID requerido", "IDENTIFIER_REQUIRED", 400)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="IDENTIFIER_REQUIRED", start_ts=start_ts)
            return response

        partner = self._find_partner_by_identifiers(identifiers)

        if not partner:
            response = {
                "ok": True,
                "found": False,
                "message": "Contacto no encontrado. No se liberó modo humano.",
            }
            self._safe_log_api(endpoint, payload, response, identifiers, status="not_found", start_ts=start_ts)
            return response

        self._update_partner_identifiers(partner, identifiers)
        session = self._get_or_create_session(partner, identifiers)
        partner.whatsapp_release_human_mode_api()
        session.action_reopen()

        handoff = request.env["whatsapp.handoff"].sudo().search([
            ("partner_id", "=", partner.id),
            ("state", "in", ["open", "assigned", "pending"]),
        ], order="taken_at desc, id desc", limit=1)

        if handoff:
            handoff.action_release()

        suggested = {
            "template": "human_release",
            "message": self._render_template(
                "human_release",
                partner=partner,
                session=session,
                fallback="El modo humano fue liberado. El bot puede continuar la atención.",
            ),
        }

        response = {
            "ok": True,
            "found": True,
            "released_by_name": released_by_name,
            "partner_id": partner.id,
            "session_id": session.id,
            "suggested": suggested,
            "profile": partner.get_whatsapp_profile_payload(),
        }
        self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
        return response