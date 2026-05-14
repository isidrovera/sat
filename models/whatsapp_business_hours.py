# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WhatsappBusinessHours(models.Model):
    _name = "whatsapp.business.hours"
    _description = "Horario de atención WhatsApp"
    _order = "day_of_week asc"

    name = fields.Char(
        string="Nombre",
        compute="_compute_name",
        store=True,
    )

    day_of_week = fields.Selection(
        selection=[
            ("0", "Lunes"),
            ("1", "Martes"),
            ("2", "Miércoles"),
            ("3", "Jueves"),
            ("4", "Viernes"),
            ("5", "Sábado"),
            ("6", "Domingo"),
        ],
        string="Día",
        required=True,
        index=True,
    )

    active = fields.Boolean(
        string="Activo",
        default=True,
    )

    is_workday = fields.Boolean(
        string="Día laboral",
        default=True,
        help="Si está desmarcado, este día se considera cerrado.",
    )

    open_time = fields.Float(
        string="Hora apertura",
        default=8.5,
        help="Usar formato decimal. Ejemplo: 8.5 = 08:30.",
    )

    close_time = fields.Float(
        string="Hora cierre",
        default=18.0,
        help="Usar formato decimal. Ejemplo: 18.5 = 18:30.",
    )

    has_break = fields.Boolean(
        string="Tiene refrigerio",
        default=True,
    )

    break_start = fields.Float(
        string="Inicio refrigerio",
        default=13.0,
    )

    break_end = fields.Float(
        string="Fin refrigerio",
        default=14.0,
    )

    after_hours_message = fields.Text(
        string="Mensaje fuera de horario",
        default="En este momento estamos fuera de horario de atención. Puedes dejarnos tu consulta y te responderemos apenas retomemos la atención.",
    )

    break_message = fields.Text(
        string="Mensaje en refrigerio",
        default="Estamos en horario de refrigerio. Puedes dejarnos tu consulta y te responderemos apenas retomemos la atención.",
    )

    note = fields.Text(
        string="Notas internas",
    )

    _sql_constraints = [
        (
            "unique_whatsapp_business_day",
            "unique(day_of_week)",
            "Ya existe una configuración de horario para este día.",
        )
    ]

    @api.depends("day_of_week")
    def _compute_name(self):
        day_map = dict(self._fields["day_of_week"].selection)
        for rec in self:
            rec.name = day_map.get(rec.day_of_week, "Horario")

    @api.constrains("open_time", "close_time", "break_start", "break_end")
    def _check_hours(self):
        for rec in self:
            for field_name in ["open_time", "close_time", "break_start", "break_end"]:
                value = rec[field_name]
                if value < 0 or value >= 24:
                    raise ValidationError(_("Las horas deben estar entre 0 y 23.99."))

            if rec.is_workday and rec.open_time >= rec.close_time:
                raise ValidationError(_("La hora de apertura debe ser menor que la hora de cierre."))

            if rec.has_break:
                if rec.break_start >= rec.break_end:
                    raise ValidationError(_("El inicio de refrigerio debe ser menor que el fin de refrigerio."))
                if rec.break_start < rec.open_time or rec.break_end > rec.close_time:
                    raise ValidationError(_("El refrigerio debe estar dentro del horario laboral."))

    def _float_to_hhmm(self, value):
        hours = int(value)
        minutes = int(round((value - hours) * 60))
        if minutes == 60:
            hours += 1
            minutes = 0
        return "%02d:%02d" % (hours, minutes)

    def get_display_hours(self):
        self.ensure_one()

        if not self.is_workday:
            return "Cerrado"

        text = "%s - %s" % (
            self._float_to_hhmm(self.open_time),
            self._float_to_hhmm(self.close_time),
        )

        if self.has_break:
            text += " / Refrigerio %s - %s" % (
                self._float_to_hhmm(self.break_start),
                self._float_to_hhmm(self.break_end),
            )

        return text

    @api.model
    def init_default_hours(self):
        defaults = [
            ("0", True, 8.5, 18.5, True, 13.0, 14.0),   # Lunes
            ("1", True, 8.5, 18.5, True, 13.0, 14.0),   # Martes
            ("2", True, 8.5, 18.5, True, 13.0, 14.0),   # Miércoles
            ("3", True, 8.5, 18.0, True, 13.0, 14.0),   # Jueves
            ("4", True, 8.5, 18.0, True, 13.0, 14.0),   # Viernes
            ("5", True, 9.0, 13.0, False, 0.0, 0.0),    # Sábado
            ("6", False, 0.0, 0.0, False, 0.0, 0.0),    # Domingo
        ]

        for day, is_workday, open_time, close_time, has_break, break_start, break_end in defaults:
            existing = self.search([("day_of_week", "=", day)], limit=1)
            vals = {
                "day_of_week": day,
                "is_workday": is_workday,
                "open_time": open_time,
                "close_time": close_time,
                "has_break": has_break,
                "break_start": break_start,
                "break_end": break_end,
                "active": True,
            }
            if existing:
                existing.write(vals)
            else:
                self.create(vals)

        return True