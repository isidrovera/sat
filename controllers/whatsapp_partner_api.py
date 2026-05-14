# -*- coding: utf-8 -*-

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

    Maneja:
    - Perfil por número / JID / LID
    - Registro DNI / RUC
    - Sesiones
    - Mensajes entrantes y salientes
    - Logs API
    - Auto respuestas
    - Reglas de intención
    - Horario semanal
    - Calendario / feriados / cierres manuales
    - Plantillas
    - Media
    - Handoff humano
    - Outbox
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

        # Perú: si viene 9 dígitos, asumimos prefijo 51
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

        clean_phone = self._clean_phone(phone)
        clean_jid = self._normalize_jid(jid)
        clean_lid = self._normalize_jid(lid)
        clean_raw_jid = self._normalize_jid(raw_jid)

        return {
            "phone": clean_phone,
            "jid": clean_jid,
            "lid": clean_lid,
            "raw_jid": clean_raw_jid,
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
        """
        Usa tu lógica ya existente en res.partner:
        - _doc_number_change()
        - ConsultarDNI()
        - ValidarRUC()
        - ConsultarRUC()
        """
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

        partner.whatsapp_update_identifiers(
            jid=identifiers.get("jid"),
            lid=identifiers.get("lid"),
            raw_jid=identifiers.get("raw_jid"),
        )

    # ==========================================================
    # Templates
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
            "ask_dni": "Buenos días. Para poder ayudarte, por favor envíame tu DNI de 8 dígitos.",
            "ask_ruc": "Gracias. Ahora envíame el RUC de tu empresa para completar el registro.",
            "blocked_contact": "Tu número no está habilitado para atención por este canal.",
            "human_mode_active": "Tu conversación está siendo atendida por un asesor.",
            "after_hours": business_status.get("message") if business_status else "Estamos fuera de horario de atención.",
            "select_company": "Tienes más de una empresa asociada. Indica con cuál deseas continuar.",
            "greeting_registered": "Buenos días, ¿en qué podemos ayudarte?",
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
            "state": "pending",
            "raw_payload": payload or {},
        })

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
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="error",
                error_code="IDENTIFIER_REQUIRED",
                start_ts=start_ts,
            )
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
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="error",
                error_code="IDENTIFIER_REQUIRED",
                start_ts=start_ts,
            )
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
        )

        response = {
            "ok": True,
            "found": bool(result.get("found")),
            "applies_to": applies_to,
            "business": business_status,
            "auto_response": result,
        }
        self._safe_log_api(
            endpoint,
            payload,
            response,
            identifiers,
            partner=partner if partner else False,
            start_ts=start_ts,
        )
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
        applies_to = self._get_applies_to(partner, business_status=business_status) if partner else "new"

        result = request.env["whatsapp.intent.rule"].sudo().detect_intent(
            message=message_text,
            partner=partner if partner else False,
            applies_to=applies_to,
            is_after_hours=not business_status.get("is_open"),
        )

        response = {
            "ok": True,
            "found": bool(result.get("found")),
            "applies_to": applies_to,
            "business": business_status,
            "intent": result,
        }
        self._safe_log_api(
            endpoint,
            payload,
            response,
            identifiers,
            partner=partner if partner else False,
            start_ts=start_ts,
        )
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
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="error",
                error_code="TEMPLATE_REQUIRED",
                start_ts=start_ts,
            )
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
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="error",
                error_code="IDENTIFIER_REQUIRED",
                start_ts=start_ts,
            )
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
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="error",
                error_code="IDENTIFIER_REQUIRED",
                start_ts=start_ts,
            )
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
            ("state", "=", "open"),
        ], order="taken_at desc, id desc", limit=1)

        if handoff:
            handoff.write({
                "state": "released",
                "released_at": fields.Datetime.now(),
                "released_by_name": released_by_name,
            })

        suggested = {
            "template": "human_release",
            "message": self._render_template(
                "human_release",
                partner=partner,
                session=session,
                fallback="El bot ha sido habilitado nuevamente para continuar la atención.",
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
    # Endpoint: seleccionar empresa
    # ==========================================================
    @http.route("/sat/whatsapp/company/select", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_company_select(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/company/select"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        company_id = payload.get("company_id")

        if not self._has_any_identifier(identifiers):
            response = self._json_error("Número, JID o LID requerido", "IDENTIFIER_REQUIRED", 400)
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="error",
                error_code="IDENTIFIER_REQUIRED",
                start_ts=start_ts,
            )
            return response

        if not company_id:
            response = self._json_error("company_id requerido", "COMPANY_REQUIRED", 400)
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                status="error",
                error_code="COMPANY_REQUIRED",
                start_ts=start_ts,
            )
            return response

        partner = self._find_partner_by_identifiers(identifiers)

        if not partner:
            response = {
                "ok": True,
                "found": False,
                "message": "Contacto no encontrado. No se seleccionó empresa.",
            }
            self._safe_log_api(endpoint, payload, response, identifiers, status="not_found", start_ts=start_ts)
            return response

        self._update_partner_identifiers(partner, identifiers)

        try:
            company_id = int(company_id)
            company = request.env["res.partner"].sudo().browse(company_id).exists()

            if not company:
                response = self._json_error("Empresa no encontrada", "COMPANY_NOT_FOUND", 404)
                self._safe_log_api(
                    endpoint,
                    payload,
                    response,
                    identifiers,
                    partner=partner,
                    status="error",
                    error_code="COMPANY_NOT_FOUND",
                    start_ts=start_ts,
                )
                return response

            partner.whatsapp_set_active_company(company)

            session = self._get_or_create_session(partner, identifiers)
            session.write({"active_company_id": company.id})

            suggested = {
                "template": "company_selected",
                "message": self._render_template(
                    "company_selected",
                    partner=partner,
                    session=session,
                    company=company,
                    fallback="Empresa seleccionada correctamente. ¿En qué podemos ayudarte?",
                ),
            }

            response = {
                "ok": True,
                "found": True,
                "partner_id": partner.id,
                "active_company_id": company.id,
                "active_company_name": company.name,
                "session_id": session.id,
                "suggested": suggested,
                "profile": partner.get_whatsapp_profile_payload(),
            }
            self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
            return response

        except Exception as e:
            _logger.exception("[SAT-WHATSAPP-API] Error seleccionando empresa activa")
            response = self._json_error(str(e), "COMPANY_SELECTION_ERROR", 400)
            self._safe_log_api(
                endpoint,
                payload,
                response,
                identifiers,
                partner=partner,
                status="error",
                error_code="COMPANY_SELECTION_ERROR",
                error_message=str(e),
                start_ts=start_ts,
            )
            return response

    # ==========================================================
    # Endpoint: registrar DNI
    # ==========================================================
    @http.route("/sat/whatsapp/register/dni", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_register_dni(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/register/dni"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        dni = self._only_digits(
            payload.get("dni")
            or payload.get("vat")
            or payload.get("document_number")
        )

        if len(dni) != 8:
            response = self._json_error("DNI inválido. Debe tener 8 dígitos.", "INVALID_DNI", 400)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="INVALID_DNI", start_ts=start_ts)
            return response

        if not self._has_any_identifier(identifiers):
            response = self._json_error("Número, JID o LID requerido", "IDENTIFIER_REQUIRED", 400)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="IDENTIFIER_REQUIRED", start_ts=start_ts)
            return response

        Partner = request.env["res.partner"].sudo()
        dni_type = self._get_dni_type()

        if not dni_type:
            response = self._json_error("No se encontró tipo de documento DNI en Odoo.", "DNI_TYPE_NOT_FOUND", 500)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="DNI_TYPE_NOT_FOUND", start_ts=start_ts)
            return response

        partner_by_identifier = self._find_partner_by_identifiers(identifiers)

        partner_by_dni = Partner.search([
            ("vat", "=", dni),
            ("l10n_latam_identification_type_id", "=", dni_type.id),
        ], limit=1)

        if partner_by_identifier and partner_by_dni and partner_by_identifier.id != partner_by_dni.id:
            response = self._json_error(
                "El DNI ya está asociado a otro contacto.",
                "DNI_ALREADY_LINKED",
                409,
                extra={
                    "existing_partner_id": partner_by_dni.id,
                    "identifier_partner_id": partner_by_identifier.id,
                },
            )
            self._safe_log_api(endpoint, payload, response, identifiers, partner=partner_by_identifier, status="error", error_code="DNI_ALREADY_LINKED", start_ts=start_ts)
            return response

        partner = partner_by_identifier or partner_by_dni

        if partner and partner.vat and partner.vat != dni:
            response = self._json_error(
                "El contacto encontrado ya tiene otro documento registrado.",
                "DOCUMENT_CONFLICT",
                409,
                extra={
                    "partner_id": partner.id,
                    "current_vat": partner.vat,
                    "received_dni": dni,
                },
            )
            self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, status="error", error_code="DOCUMENT_CONFLICT", start_ts=start_ts)
            return response

        vals = self._prepare_partner_whatsapp_values(identifiers)
        vals.update({
            "company_type": "person",
            "is_company": False,
            "l10n_latam_identification_type_id": dni_type.id,
            "vat": dni,
            "whatsapp_enabled": True,
            "whatsapp_registration_state": "waiting_ruc",
        })

        try:
            if not partner:
                vals.setdefault("name", "DNI %s" % dni)
                partner = Partner.create(vals)
            else:
                partner.write(vals)

            self._update_partner_identifiers(partner, identifiers)

            try:
                self._run_partner_document_autoload(partner)
            except Exception as e:
                _logger.exception("[SAT-WHATSAPP-API] Error cargando datos DNI")
                partner.write({"whatsapp_registration_state": "manual_review"})

                suggested = {
                    "template": "dni_error",
                    "message": self._render_template(
                        "dni_error",
                        partner=partner,
                        fallback="No pude validar el DNI automáticamente. Por favor verifica el número o espera atención de un asesor.",
                    ),
                }

                response = self._json_error(
                    "No se pudo consultar o cargar el DNI automáticamente.",
                    "DNI_AUTOLOAD_ERROR",
                    400,
                    extra={
                        "detail": str(e),
                        "partner_id": partner.id,
                        "suggested": suggested,
                        "profile": partner.get_whatsapp_profile_payload(),
                    },
                )
                self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, status="error", error_code="DNI_AUTOLOAD_ERROR", error_message=str(e), start_ts=start_ts)
                return response

            partner.write({"whatsapp_registration_state": "waiting_ruc"})
            session = self._get_or_create_session(partner, identifiers, intent="dni")

            suggested = {
                "template": "ask_ruc",
                "message": self._render_template(
                    "ask_ruc",
                    partner=partner,
                    session=session,
                    fallback="Gracias. Ahora envíame el RUC de tu empresa para completar el registro.",
                ),
            }

            response = {
                "ok": True,
                "found": True,
                "registered_dni": True,
                "next_step": "waiting_ruc",
                "message": suggested["message"],
                "suggested": suggested,
                "partner_id": partner.id,
                "session_id": session.id if session else False,
                "profile": partner.get_whatsapp_profile_payload(),
            }
            self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
            return response

        except Exception as e:
            _logger.exception("[SAT-WHATSAPP-API] Error registrando DNI")
            response = self._json_error(str(e), "DNI_REGISTER_ERROR", 500)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="DNI_REGISTER_ERROR", error_message=str(e), start_ts=start_ts)
            return response

    # ==========================================================
    # Endpoint: registrar RUC
    # ==========================================================
    @http.route("/sat/whatsapp/register/ruc", type="json", auth="public", methods=["POST"], csrf=False)
    def whatsapp_register_ruc(self, **kwargs):
        start_ts = time.time()
        endpoint = "/sat/whatsapp/register/ruc"
        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not self._check_token():
            response = self._json_error("No autorizado", "UNAUTHORIZED", 401)
            self._safe_log_api(endpoint, payload, response, identifiers, status="unauthorized", start_ts=start_ts)
            return response

        ruc = self._only_digits(
            payload.get("ruc")
            or payload.get("vat")
            or payload.get("document_number")
        )

        if len(ruc) != 11:
            response = self._json_error("RUC inválido. Debe tener 11 dígitos.", "INVALID_RUC", 400)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="INVALID_RUC", start_ts=start_ts)
            return response

        if not self._has_any_identifier(identifiers):
            response = self._json_error("Número, JID o LID requerido", "IDENTIFIER_REQUIRED", 400)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="IDENTIFIER_REQUIRED", start_ts=start_ts)
            return response

        Partner = request.env["res.partner"].sudo()
        ruc_type = self._get_ruc_type()

        if not ruc_type:
            response = self._json_error("No se encontró tipo de documento RUC en Odoo.", "RUC_TYPE_NOT_FOUND", 500)
            self._safe_log_api(endpoint, payload, response, identifiers, status="error", error_code="RUC_TYPE_NOT_FOUND", start_ts=start_ts)
            return response

        contact = self._find_partner_by_identifiers(identifiers)

        if not contact:
            response = self._json_error("Primero debe registrarse el contacto con DNI.", "CONTACT_NOT_FOUND", 404)
            self._safe_log_api(endpoint, payload, response, identifiers, status="not_found", start_ts=start_ts)
            return response

        self._update_partner_identifiers(contact, identifiers)

        company = Partner.search([
            ("vat", "=", ruc),
            ("l10n_latam_identification_type_id", "=", ruc_type.id),
            ("is_company", "=", True),
        ], limit=1)

        company_created = False

        try:
            if not company:
                company = Partner.create({
                    "name": "RUC %s" % ruc,
                    "is_company": True,
                    "company_type": "company",
                    "l10n_latam_identification_type_id": ruc_type.id,
                    "vat": ruc,
                    "whatsapp_enabled": True,
                    "whatsapp_registration_state": "registered",
                })
                company_created = True
            else:
                company.write({
                    "is_company": True,
                    "company_type": "company",
                    "l10n_latam_identification_type_id": ruc_type.id,
                    "vat": ruc,
                    "whatsapp_enabled": True,
                })

            try:
                self._run_partner_document_autoload(company)
            except Exception as e:
                _logger.exception("[SAT-WHATSAPP-API] Error cargando datos RUC")

                if company_created and company.exists():
                    company.unlink()

                suggested = {
                    "template": "ruc_error",
                    "message": self._render_template(
                        "ruc_error",
                        partner=contact,
                        fallback="No pude validar el RUC automáticamente. Verifica el número e intenta nuevamente.",
                    ),
                }

                response = self._json_error(
                    "No se pudo consultar o cargar el RUC automáticamente.",
                    "RUC_AUTOLOAD_ERROR",
                    400,
                    extra={
                        "detail": str(e),
                        "contact_id": contact.id,
                        "company_created": company_created,
                        "suggested": suggested,
                        "profile": contact.get_whatsapp_profile_payload(),
                    },
                )
                self._safe_log_api(endpoint, payload, response, identifiers, partner=contact, status="error", error_code="RUC_AUTOLOAD_ERROR", error_message=str(e), start_ts=start_ts)
                return response

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

            suggested = {
                "template": "registration_completed",
                "message": self._render_template(
                    "registration_completed",
                    partner=contact,
                    session=session,
                    company=company,
                    fallback="Registro completado correctamente. ¿En qué podemos ayudarte?",
                ),
            }

            response = {
                "ok": True,
                "found": True,
                "registered_ruc": True,
                "company_created": company_created,
                "next_step": "registered",
                "message": suggested["message"],
                "suggested": suggested,
                "partner_id": contact.id,
                "company_id": company.id,
                "company_name": company.name,
                "session_id": session.id if session else False,
                "profile": contact.get_whatsapp_profile_payload(),
            }
            self._safe_log_api(endpoint, payload, response, identifiers, partner=contact, session=session, start_ts=start_ts)
            return response

        except Exception as e:
            _logger.exception("[SAT-WHATSAPP-API] Error registrando RUC")
            response = self._json_error(str(e), "RUC_REGISTER_ERROR", 500)
            self._safe_log_api(endpoint, payload, response, identifiers, partner=contact, status="error", error_code="RUC_REGISTER_ERROR", error_message=str(e), start_ts=start_ts)
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

        message = self._record_whatsapp_message(
            session=session,
            partner=partner,
            identifiers=identifiers,
            role=payload.get("role") or "assistant",
            direction="out",
            message_type=message_type,
            content=content,
            intent=payload.get("intent") or False,
            payload=payload,
            external_message_id=payload.get("external_message_id") or payload.get("message_id") or False,
        )

        media = self._create_media_from_payload(
            session=session,
            partner=partner,
            message=message,
            payload=payload,
        )

        outbox = self._create_outbox(
            session,
            partner,
            identifiers,
            content,
            message_type=message_type,
            media=media if media else False,
            payload=payload,
        )
        outbox.write({"message_id": message.id})

        response = {
            "ok": True,
            "partner_id": partner.id,
            "session_id": session.id,
            "message_id": message.id,
            "outbox_id": outbox.id,
            "state": outbox.state,
            "message": content,
        }
        self._safe_log_api(endpoint, payload, response, identifiers, partner=partner, session=session, start_ts=start_ts)
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

        try:
            outbox_id = int(outbox_id or 0)
        except Exception:
            outbox_id = 0

        outbox = request.env["whatsapp.outbox"].sudo().browse(outbox_id).exists()

        if not outbox:
            response = self._json_error("Outbox no encontrado.", "OUTBOX_NOT_FOUND", 404)
            self._safe_log_api(endpoint, payload, response, identifiers, status="not_found", start_ts=start_ts)
            return response

        outbox.action_mark_sent(external_message_id=external_message_id)

        response = {
            "ok": True,
            "outbox_id": outbox.id,
            "state": outbox.state,
            "external_message_id": outbox.external_message_id,
        }
        self._safe_log_api(
            endpoint,
            payload,
            response,
            identifiers,
            partner=outbox.partner_id,
            session=outbox.session_id,
            start_ts=start_ts,
        )
        return response