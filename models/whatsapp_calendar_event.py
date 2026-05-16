# -*- coding: utf-8 -*-

import logging
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class WhatsappCalendarEvent(models.Model):
    _name = "whatsapp.calendar.event"
    _description = "Calendario WhatsApp"
    _order = "event_date asc, name asc"

    name = fields.Char(
        string="Nombre",
        required=True,
        index=True,
    )

    event_date = fields.Date(
        string="Fecha",
        required=True,
        index=True,
    )

    active = fields.Boolean(
        string="Activo",
        default=True,
        index=True,
    )

    event_type = fields.Selection(
        selection=[
            ("holiday", "Feriado Perú"),
            ("manual_closed", "Cierre manual"),
            ("special_hours", "Horario especial"),
            ("info", "Informativo"),
        ],
        string="Tipo",
        required=True,
        default="holiday",
        index=True,
    )

    source = fields.Selection(
        selection=[
            ("peru_auto", "Feriado Perú automático"),
            ("manual", "Manual"),
            ("api", "API"),
        ],
        string="Origen",
        default="manual",
        required=True,
        index=True,
    )

    is_closed = fields.Boolean(
        string="Cerrado todo el día",
        default=True,
        help="Si está activo, WhatsApp se considera fuera de horario todo el día.",
    )

    special_open_time = fields.Float(
        string="Apertura especial",
        help="Solo aplica si el tipo es Horario especial.",
    )

    special_close_time = fields.Float(
        string="Cierre especial",
        help="Solo aplica si el tipo es Horario especial.",
    )

    has_special_break = fields.Boolean(
        string="Refrigerio especial",
        default=False,
    )

    special_break_start = fields.Float(
        string="Inicio refrigerio especial",
    )

    special_break_end = fields.Float(
        string="Fin refrigerio especial",
    )

    message = fields.Text(
        string="Mensaje",
        help="Mensaje que se usará cuando este evento aplique.",
    )

    template_name = fields.Char(
        string="Plantilla asociada",
        help="Nombre técnico de whatsapp.template a usar para este evento (opcional).",
    )

    note = fields.Text(string="Notas internas")

    _sql_constraints = [
        (
            "unique_whatsapp_calendar_event_date_type_name",
            "unique(event_date, event_type, name)",
            "Ya existe un evento con el mismo nombre, fecha y tipo.",
        )
    ]

    # ==========================================================
    # Constraints
    # ==========================================================
    @api.constrains(
        "event_type",
        "special_open_time",
        "special_close_time",
        "special_break_start",
        "special_break_end",
    )
    def _check_special_hours(self):
        for rec in self:
            if rec.event_type != "special_hours":
                continue

            if rec.special_open_time < 0 or rec.special_open_time >= 24:
                raise ValidationError(_("La apertura especial debe estar entre 0 y 23.99."))

            if rec.special_close_time < 0 or rec.special_close_time >= 24:
                raise ValidationError(_("El cierre especial debe estar entre 0 y 23.99."))

            if rec.special_open_time >= rec.special_close_time:
                raise ValidationError(_("La apertura especial debe ser menor que el cierre especial."))

            if rec.has_special_break:
                if rec.special_break_start >= rec.special_break_end:
                    raise ValidationError(_("El inicio de refrigerio especial debe ser menor que el fin."))
                if (
                    rec.special_break_start < rec.special_open_time
                    or rec.special_break_end > rec.special_close_time
                ):
                    raise ValidationError(_("El refrigerio especial debe estar dentro del horario especial."))

    # ==========================================================
    # Create / Write con logs
    # ==========================================================
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            _logger.info(
                "[WA-CAL] Evento creado id=%s name=%s date=%s type=%s source=%s",
                rec.id, rec.name, rec.event_date, rec.event_type, rec.source,
            )
        return records

    # ==========================================================
    # Helpers
    # ==========================================================
    def _float_to_hhmm(self, value):
        hours = int(value)
        minutes = int(round((value - hours) * 60))
        if minutes == 60:
            hours += 1
            minutes = 0
        return "%02d:%02d" % (hours, minutes)

    def get_display_hours(self):
        self.ensure_one()

        if self.is_closed:
            return "Cerrado"

        if self.event_type == "special_hours":
            text = "%s - %s" % (
                self._float_to_hhmm(self.special_open_time),
                self._float_to_hhmm(self.special_close_time),
            )
            if self.has_special_break:
                text += " / Refrigerio %s - %s" % (
                    self._float_to_hhmm(self.special_break_start),
                    self._float_to_hhmm(self.special_break_end),
                )
            return text

        return ""

    def evaluate_status(self, current_hour_float):
        """
        Evalúa el estado del evento para una hora dada.

        :param current_hour_float: hora decimal
        :return: dict con is_open, reason, message, etc.
        """
        self.ensure_one()

        if self.event_type in ("holiday", "manual_closed") or self.is_closed:
            _logger.info(
                "[WA-CAL] Evento cerrado id=%s date=%s type=%s",
                self.id, self.event_date, self.event_type,
            )
            return {
                "is_open": False,
                "reason": self.event_type,
                "reason_label": self.name,
                "message": self.message or "Hoy no tenemos atención. Puedes dejarnos tu consulta.",
                "template_name": self.template_name or False,
                "event_id": self.id,
                "display_hours": self.get_display_hours(),
            }

        if self.event_type == "special_hours":
            in_work = self.special_open_time <= current_hour_float <= self.special_close_time
            in_break = (
                self.has_special_break
                and self.special_break_start <= current_hour_float <= self.special_break_end
            )

            if in_break:
                _logger.info(
                    "[WA-CAL] Evento en break especial id=%s hour=%s",
                    self.id, current_hour_float,
                )
                return {
                    "is_open": False,
                    "reason": "special_hours_break",
                    "reason_label": self.name,
                    "message": self.message or "Estamos en refrigerio especial.",
                    "template_name": self.template_name or False,
                    "event_id": self.id,
                    "display_hours": self.get_display_hours(),
                }

            if in_work:
                return {
                    "is_open": True,
                    "reason": "special_hours_open",
                    "reason_label": self.name,
                    "message": False,
                    "template_name": False,
                    "event_id": self.id,
                    "display_hours": self.get_display_hours(),
                }

            return {
                "is_open": False,
                "reason": "special_hours_closed",
                "reason_label": self.name,
                "message": self.message or "Estamos fuera de horario especial.",
                "template_name": self.template_name or False,
                "event_id": self.id,
                "display_hours": self.get_display_hours(),
            }

        # event_type = "info" no afecta apertura
        return {
            "is_open": True,
            "reason": "info_event",
            "reason_label": self.name,
            "message": self.message or False,
            "template_name": self.template_name or False,
            "event_id": self.id,
            "display_hours": "",
        }

    # ==========================================================
    # Feriados Perú
    # ==========================================================
    @api.model
    def get_peru_holidays(self, year):
        """
        Feriados nacionales Perú.
        Se carga localmente para no depender de una API externa.
        """
        year = int(year)

        return [
            (date(year, 1, 1), "Año Nuevo"),
            (date(year, 4, 17), "Jueves Santo"),
            (date(year, 4, 18), "Viernes Santo"),
            (date(year, 5, 1), "Día del Trabajo"),
            (date(year, 6, 7), "Batalla de Arica y Día de la Bandera"),
            (date(year, 6, 29), "San Pedro y San Pablo"),
            (date(year, 7, 23), "Día de la Fuerza Aérea del Perú"),
            (date(year, 7, 28), "Fiestas Patrias"),
            (date(year, 7, 29), "Fiestas Patrias"),
            (date(year, 8, 6), "Batalla de Junín"),
            (date(year, 8, 30), "Santa Rosa de Lima"),
            (date(year, 10, 8), "Combate de Angamos"),
            (date(year, 11, 1), "Día de Todos los Santos"),
            (date(year, 12, 8), "Inmaculada Concepción"),
            (date(year, 12, 9), "Batalla de Ayacucho"),
            (date(year, 12, 25), "Navidad"),
        ]

    @api.model
    def load_peru_holidays(self, year=False):
        year = int(year or fields.Date.today().year)

        _logger.info("[WA-CAL] Cargando feriados Perú año=%s", year)

        holidays = self.get_peru_holidays(year)
        created = 0
        updated = 0

        default_message = (
            "Hoy no tenemos atención por feriado. "
            "Puedes dejarnos tu consulta y te responderemos el siguiente día hábil."
        )

        for holiday_date, holiday_name in holidays:
            existing = self.search([
                ("event_date", "=", holiday_date),
                ("event_type", "=", "holiday"),
                ("source", "=", "peru_auto"),
            ], limit=1)

            vals = {
                "name": holiday_name,
                "event_date": holiday_date,
                "event_type": "holiday",
                "source": "peru_auto",
                "is_closed": True,
                "message": default_message,
                "active": True,
            }

            if existing:
                existing.write(vals)
                updated += 1
            else:
                self.create(vals)
                created += 1

        _logger.info(
            "[WA-CAL] Feriados Perú cargados año=%s created=%s updated=%s",
            year, created, updated,
        )

        return {
            "created": created,
            "updated": updated,
            "year": year,
        }

    def action_load_current_year_peru_holidays(self):
        return self.load_peru_holidays(fields.Date.today().year)

    def action_load_next_year_peru_holidays(self):
        return self.load_peru_holidays(fields.Date.today().year + 1)

    # ==========================================================
    # Cron de carga automática de feriados
    # ==========================================================
    @api.model
    def cron_load_next_year_holidays(self):
        """Cron anual que carga los feriados del siguiente año."""
        next_year = fields.Date.today().year + 1
        _logger.info("[WA-CAL] cron_load_next_year_holidays año=%s", next_year)
        try:
            return self.load_peru_holidays(next_year)
        except Exception as e:
            _logger.exception(
                "[WA-CAL] Error en cron_load_next_year_holidays: %s", str(e),
            )
            return False