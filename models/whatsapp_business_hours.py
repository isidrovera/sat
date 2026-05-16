# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


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

    # ==========================================================
    # Saludos por período del día
    # ==========================================================
    morning_end = fields.Float(
        string="Fin de la mañana",
        default=12.0,
        help="Hora hasta la cual se considera 'mañana' para saludos (default 12:00).",
    )

    afternoon_end = fields.Float(
        string="Fin de la tarde",
        default=19.0,
        help="Hora hasta la cual se considera 'tarde' para saludos (default 19:00).",
    )

    # ==========================================================
    # Mensajes
    # ==========================================================
    after_hours_message = fields.Text(
        string="Mensaje fuera de horario",
        default="En este momento estamos fuera de horario de atención. Puedes dejarnos tu consulta y te responderemos apenas retomemos la atención.",
    )

    break_message = fields.Text(
        string="Mensaje en refrigerio",
        default="Estamos en horario de refrigerio. Puedes dejarnos tu consulta y te responderemos apenas retomemos la atención.",
    )

    # ==========================================================
    # Plantillas asociadas
    # ==========================================================
    template_after_hours = fields.Char(
        string="Plantilla fuera de horario",
        default="after_hours",
        help="Nombre técnico de whatsapp.template para fuera de horario.",
    )

    template_break = fields.Char(
        string="Plantilla refrigerio",
        default="in_break",
        help="Nombre técnico de whatsapp.template para horario de refrigerio.",
    )

    template_greeting_morning = fields.Char(
        string="Plantilla saludo mañana",
        default="greeting_morning",
    )

    template_greeting_afternoon = fields.Char(
        string="Plantilla saludo tarde",
        default="greeting_afternoon",
    )

    template_greeting_evening = fields.Char(
        string="Plantilla saludo noche",
        default="greeting_evening",
    )

    note = fields.Text(string="Notas internas")

    _sql_constraints = [
        (
            "unique_whatsapp_business_day",
            "unique(day_of_week)",
            "Ya existe una configuración de horario para este día.",
        )
    ]

    # ==========================================================
    # Computes
    # ==========================================================
    @api.depends("day_of_week")
    def _compute_name(self):
        day_map = dict(self._fields["day_of_week"].selection)
        for rec in self:
            rec.name = day_map.get(rec.day_of_week, "Horario")

    # ==========================================================
    # Constraints
    # ==========================================================
    @api.constrains("open_time", "close_time", "break_start", "break_end",
                    "morning_end", "afternoon_end")
    def _check_hours(self):
        for rec in self:
            for field_name in [
                "open_time", "close_time", "break_start", "break_end",
                "morning_end", "afternoon_end",
            ]:
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

            if rec.morning_end >= rec.afternoon_end:
                raise ValidationError(_("El fin de la mañana debe ser menor que el fin de la tarde."))

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

    def get_greeting_period(self, current_hour_float):
        """
        Determina el período del día según la hora.

        :param current_hour_float: hora decimal (ej. 14.5 = 14:30)
        :return: 'morning' | 'afternoon' | 'evening'
        """
        self.ensure_one()

        if current_hour_float < self.morning_end:
            return "morning"
        if current_hour_float < self.afternoon_end:
            return "afternoon"
        return "evening"

    def get_greeting_template_name(self, current_hour_float):
        """
        Devuelve el nombre de la plantilla de saludo según hora.
        """
        self.ensure_one()
        period = self.get_greeting_period(current_hour_float)
        if period == "morning":
            return self.template_greeting_morning or "greeting_morning"
        if period == "afternoon":
            return self.template_greeting_afternoon or "greeting_afternoon"
        return self.template_greeting_evening or "greeting_evening"

    def evaluate_status(self, current_hour_float):
        """
        Evalúa el estado del horario para una hora dada.

        :param current_hour_float: hora decimal
        :return: dict con is_open, reason, message, template_name
        """
        self.ensure_one()

        if not self.is_workday:
            _logger.debug(
                "[WA-HOURS] Día no laboral day=%s hour=%s",
                self.day_of_week, current_hour_float,
            )
            return {
                "is_open": False,
                "reason": "closed_day",
                "reason_label": "Día no laboral",
                "message": self.after_hours_message,
                "template_name": self.template_after_hours or "after_hours",
                "display_hours": self.get_display_hours(),
                "period": self.get_greeting_period(current_hour_float),
            }

        in_work = self.open_time <= current_hour_float <= self.close_time
        in_break = (
            self.has_break
            and self.break_start <= current_hour_float <= self.break_end
        )

        if in_break:
            _logger.info(
                "[WA-HOURS] En refrigerio day=%s hour=%s",
                self.day_of_week, current_hour_float,
            )
            return {
                "is_open": False,
                "reason": "break",
                "reason_label": "Refrigerio",
                "message": self.break_message,
                "template_name": self.template_break or "in_break",
                "display_hours": self.get_display_hours(),
                "period": self.get_greeting_period(current_hour_float),
            }

        if not in_work:
            _logger.debug(
                "[WA-HOURS] Fuera de horario day=%s hour=%s",
                self.day_of_week, current_hour_float,
            )
            return {
                "is_open": False,
                "reason": "after_hours",
                "reason_label": "Fuera de horario",
                "message": self.after_hours_message,
                "template_name": self.template_after_hours or "after_hours",
                "display_hours": self.get_display_hours(),
                "period": self.get_greeting_period(current_hour_float),
            }

        return {
            "is_open": True,
            "reason": "open",
            "reason_label": "Abierto",
            "message": False,
            "template_name": False,
            "display_hours": self.get_display_hours(),
            "period": self.get_greeting_period(current_hour_float),
        }

    # ==========================================================
    # Inicialización de datos por defecto
    # ==========================================================
    @api.model
    def init_default_hours(self):
        _logger.info("[WA-HOURS] Inicializando horarios por defecto")

        defaults = [
            ("0", True, 8.5, 18.5, True, 13.0, 14.0),   # Lunes
            ("1", True, 8.5, 18.5, True, 13.0, 14.0),   # Martes
            ("2", True, 8.5, 18.5, True, 13.0, 14.0),   # Miércoles
            ("3", True, 8.5, 18.0, True, 13.0, 14.0),   # Jueves
            ("4", True, 8.5, 18.0, True, 13.0, 14.0),   # Viernes
            ("5", True, 9.0, 13.0, False, 0.0, 0.0),    # Sábado
            ("6", False, 0.0, 0.0, False, 0.0, 0.0),    # Domingo
        ]

        created = 0
        updated = 0

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
                updated += 1
            else:
                self.create(vals)
                created += 1

        _logger.info(
            "[WA-HOURS] init_default_hours completado created=%s updated=%s",
            created, updated,
        )
        return {"created": created, "updated": updated}