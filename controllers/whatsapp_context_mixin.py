# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppContextMixin:
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
            _logger.exception(
                "[SAT-WHATSAPP-API] Error renderizando template %s",
                template_name,
            )
            return fallback

    def _get_status_template_name(self, partner=False, business_status=False):
        if not partner:
            return "ask_dni"

        if partner.whatsapp_blocked or partner.whatsapp_access_level == "blocked":
            return "blocked_contact"

        if partner.whatsapp_human_mode:
            return "human_mode_active"

        if business_status and not business_status.get("is_open"):
            if business_status.get("template_name"):
                return business_status.get("template_name")

            if business_status.get("reason") in ("break", "special_hours_break"):
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

        if business_status and business_status.get("template_name"):
            fallback_map[template_name] = business_status.get("message") or fallback_map.get(
                template_name,
                "En este momento no tenemos atención disponible.",
            )

        company = (
            partner.whatsapp_active_company_id
            if partner and partner.whatsapp_active_company_id
            else False
        )

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

        hours = self._get_today_business_hours(now_lima)

        if hours:
            try:
                template_name = hours.get_greeting_template_name(hour)
            except Exception:
                _logger.exception(
                    "[WA-CONTEXT] Error obteniendo template saludo desde horario id=%s",
                    hours.id if hours else False,
                )
                template_name = False

            if not template_name:
                if hour >= 12 and hour < 19:
                    template_name = "greeting_afternoon"
                elif hour >= 19 or hour < 5:
                    template_name = "greeting_evening"
                else:
                    template_name = "greeting_morning"
        else:
            if hour >= 12 and hour < 19:
                template_name = "greeting_afternoon"
            elif hour >= 19 or hour < 5:
                template_name = "greeting_evening"
            else:
                template_name = "greeting_morning"

        if template_name == "greeting_afternoon":
            fallback = "Buenas tardes"
        elif template_name == "greeting_evening":
            fallback = "Buenas noches"
        else:
            fallback = "Buenos días"

        name = ""
        if partner and partner.name:
            name = ", %s" % partner.name.split()[0]

        fallback = "%s%s. ¿En qué podemos ayudarte?" % (fallback, name)

        company = (
            partner.whatsapp_active_company_id
            if partner and partner.whatsapp_active_company_id
            else False
        )

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

    def _get_today_business_hours(self, check_dt=False):
        check_dt = check_dt or self._now_lima()
        day_of_week = str(check_dt.weekday())

        return request.env["whatsapp.business.hours"].sudo().search([
            ("active", "=", True),
            ("day_of_week", "=", day_of_week),
        ], limit=1)

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
            try:
                status = event.evaluate_status(current_float)
            except Exception:
                _logger.exception(
                    "[WA-CONTEXT] Error evaluando calendario id=%s date=%s",
                    event.id if event else False,
                    today,
                )
                status = {}

            status = status or {}

            return {
                "is_open": bool(status.get("is_open")),
                "reason": status.get("reason") or event.event_type,
                "reason_label": status.get("reason_label") or event.name,
                "message": status.get("message") or event.message or "Hoy no tenemos atención. Puedes dejarnos tu consulta.",
                "template_name": status.get("template_name") or event.template_name or False,
                "date": str(today),
                "event_id": status.get("event_id") or event.id,
                "display_hours": status.get("display_hours") or event.get_display_hours(),
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
                "template_name": False,
                "date": str(today),
                "display_hours": False,
            }

        try:
            status = hours.evaluate_status(current_float)
        except Exception:
            _logger.exception(
                "[WA-CONTEXT] Error evaluando horario id=%s day=%s",
                hours.id if hours else False,
                day_of_week,
            )
            status = {}

        status = status or {}

        if status:
            return {
                "is_open": bool(status.get("is_open")),
                "reason": status.get("reason") or "open",
                "reason_label": status.get("reason_label") or "Abierto",
                "message": status.get("message") or False,
                "template_name": status.get("template_name") or False,
                "date": str(today),
                "display_hours": status.get("display_hours") or hours.get_display_hours(),
            }

        if not hours.is_workday:
            return {
                "is_open": False,
                "reason": "closed_day",
                "reason_label": "Día no laboral",
                "message": hours.after_hours_message,
                "template_name": hours.template_after_hours or "after_hours",
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
                "template_name": hours.template_break or "in_break",
                "date": str(today),
                "display_hours": hours.get_display_hours(),
            }

        if not in_work:
            return {
                "is_open": False,
                "reason": "after_hours",
                "reason_label": "Fuera de horario",
                "message": hours.after_hours_message,
                "template_name": hours.template_after_hours or "after_hours",
                "date": str(today),
                "display_hours": hours.get_display_hours(),
            }

        return {
            "is_open": True,
            "reason": "open",
            "reason_label": "Abierto",
            "message": False,
            "template_name": False,
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