# -*- coding: utf-8 -*-

from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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

    note = fields.Text(
        string="Notas internas",
    )

    _sql_constraints = [
        (
            "unique_whatsapp_calendar_event_date_type_name",
            "unique(event_date, event_type, name)",
            "Ya existe un evento con el mismo nombre, fecha y tipo.",
        )
    ]

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

    @api.model
    def get_peru_holidays(self, year):
        """
        Feriados nacionales Perú.
        Se carga localmente para no depender de una API externa.
        Puedes editar manualmente luego desde Odoo.
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

        return {
            "created": created,
            "updated": updated,
            "year": year,
        }

    def action_load_current_year_peru_holidays(self):
        return self.load_peru_holidays(fields.Date.today().year)

    def action_load_next_year_peru_holidays(self):
        return self.load_peru_holidays(fields.Date.today().year + 1)