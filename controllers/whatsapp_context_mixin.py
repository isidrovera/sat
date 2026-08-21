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
    """
    Contexto conversacional compartido para WhatsApp.

    Responsabilidades:
    - renderizar plantillas;
    - construir mensajes sugeridos;
    - seleccionar saludo;
    - calcular horario/calendario;
    - clasificar el contexto funcional del contacto.

    Principio importante:
    el estado del contacto y el estado del horario son conceptos distintos.
    """

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
        if not template_name:
            _logger.warning(
                "[WA-TEMPLATE] Render solicitado sin nombre | "
                "partner_id=%s session_id=%s",
                partner.id if partner else False,
                session.id if session else False,
            )
            return fallback

        try:
            text = request.env["whatsapp.template"].sudo().get_rendered(
                name=template_name,
                partner=partner if partner else False,
                session=session if session else False,
                company=company if company else False,
                extra=extra or {},
            )

            if text:
                _logger.debug(
                    "[WA-TEMPLATE] Plantilla renderizada | "
                    "template=%s partner_id=%s session_id=%s",
                    template_name,
                    partner.id if partner else False,
                    session.id if session else False,
                )
                return text

            _logger.warning(
                "[WA-TEMPLATE] Plantilla vacía/no disponible; usando fallback | "
                "template=%s partner_id=%s session_id=%s",
                template_name,
                partner.id if partner else False,
                session.id if session else False,
            )
            return fallback

        except Exception:
            _logger.exception(
                "[WA-TEMPLATE] Error renderizando plantilla | "
                "template=%s partner_id=%s session_id=%s",
                template_name,
                partner.id if partner else False,
                session.id if session else False,
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
            "ask_dni": (
                "👋 Para identificarte y continuar con la atención, "
                "envíanos tu *DNI de 8 dígitos*."
            ),
            "ask_ruc": (
                "🏢 Ahora envíanos el *RUC de 11 dígitos* de la empresa "
                "con la que deseas realizar la atención."
            ),
            "blocked_contact": (
                "⚠️ Este número no se encuentra habilitado actualmente "
                "para recibir atención mediante este canal."
            ),
            "human_mode_active": (
                "👨‍💼 Tu conversación está siendo atendida por un integrante "
                "de nuestro equipo. La atención continuará por este mismo chat."
            ),
            "after_hours": (
                business_status.get("message")
                if business_status
                else "En este momento nos encontramos fuera del horario de atención."
            ),
            "in_break": (
                business_status.get("message")
                if business_status
                else "En este momento nuestro equipo se encuentra en horario de refrigerio."
            ),
            "select_company": (
                "🏢 Selecciona la empresa con la que deseas realizar esta atención."
            ),
            "greeting_registered": "¿En qué podemos ayudarte?",
        }

        if business_status and business_status.get("template_name"):
            fallback_map[template_name] = business_status.get("message") or fallback_map.get(
                template_name,
                "En este momento no contamos con atención en tiempo real.",
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

        fallback = (
            "%s%s. 👋\n\n"
            "Soy el asistente virtual de *ANDES SOLUTION COPIERS*.\n\n"
            "¿En qué podemos ayudarte?"
        ) % (
            fallback,
            name,
        )

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

            _logger.info(
                "[WA-HOURS] Estado por calendario | "
                "date=%s event_id=%s event_type=%s is_open=%s reason=%s",
                today,
                event.id if event else False,
                event.event_type if event else False,
                bool(status.get("is_open")),
                status.get("reason") or event.event_type,
            )

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
            _logger.warning(
                "[WA-HOURS] No existe configuración para el día | "
                "date=%s day_of_week=%s; se conserva is_open=True",
                today,
                day_of_week,
            )

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
            _logger.info(
                "[WA-HOURS] Estado horario calculado | "
                "date=%s day=%s hour=%s is_open=%s reason=%s",
                today,
                day_of_week,
                current_float,
                bool(status.get("is_open")),
                status.get("reason") or "open",
            )

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

    def _get_applies_to(
        self,
        partner,
        business_status=False,
        session=False,
    ):
        """
        Devuelve únicamente el contexto funcional del contacto.

        ``business_status`` se conserva como argumento por compatibilidad,
        pero ya no cambia el valor de applies_to.

        Ejemplos correctos:
            registered + break
            registered + after_hours
            registered + open

        La disponibilidad horaria se evalúa por separado después de detectar
        la intención.
        """
        if not partner:
            applies_to = "new"

        elif (
            partner.whatsapp_blocked
            or partner.whatsapp_access_level == "blocked"
        ):
            applies_to = "blocked"

        elif partner.whatsapp_human_mode:
            applies_to = "human"

        else:
            registration_state = getattr(
                partner,
                "whatsapp_registration_state",
                "none",
            )

            applies_to = (
                "registered"
                if registration_state == "registered"
                else "new"
            )

        _logger.info(
            "[WA-CONTEXT] Contexto funcional resuelto | "
            "partner_id=%s session_id=%s applies_to=%s "
            "business_is_open=%s business_reason=%s",
            partner.id if partner else False,
            session.id if session else False,
            applies_to,
            (
                business_status.get("is_open")
                if isinstance(business_status, dict)
                else False
            ),
            (
                business_status.get("reason")
                if isinstance(business_status, dict)
                else False
            ),
        )

        return applies_to
