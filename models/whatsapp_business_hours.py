# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


class WhatsappBusinessHours(models.Model):
    _name = "whatsapp.business.hours"
    _description = "Horario de atención WhatsApp"
    _order = "day_of_week asc"

    # ==========================================================
    # Identificación
    # ==========================================================
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
        help="Permite habilitar o deshabilitar esta configuración de horario.",
    )

    is_workday = fields.Boolean(
        string="Día laboral",
        default=True,
        help=(
            "Si está desmarcado, el día se considera cerrado para atención "
            "en tiempo real."
        ),
    )

    # ==========================================================
    # Horario laboral
    # ==========================================================
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
        help="Indica si este día tiene un intervalo de refrigerio.",
    )

    break_start = fields.Float(
        string="Inicio refrigerio",
        default=13.0,
        help="Hora de inicio del refrigerio en formato decimal.",
    )

    break_end = fields.Float(
        string="Fin refrigerio",
        default=14.0,
        help="Hora de fin del refrigerio en formato decimal.",
    )

    # ==========================================================
    # Saludos por período del día
    # ==========================================================
    morning_end = fields.Float(
        string="Fin de la mañana",
        default=12.0,
        help=(
            "Hora hasta la cual se considera 'mañana' para seleccionar "
            "el saludo correspondiente."
        ),
    )

    afternoon_end = fields.Float(
        string="Fin de la tarde",
        default=19.0,
        help=(
            "Hora hasta la cual se considera 'tarde' para seleccionar "
            "el saludo correspondiente."
        ),
    )

    # ==========================================================
    # Mensajes de respaldo
    # ==========================================================
    after_hours_message = fields.Text(
        string="Mensaje fuera de horario",
        default=(
            "En este momento nuestro equipo se encuentra fuera del horario "
            "habitual de atención. Puedes registrar por este canal una "
            "solicitud de tóner o servicio técnico y nuestro equipo la "
            "revisará al retomar sus actividades. La asistencia remota y "
            "la atención directa con un técnico estarán disponibles "
            "nuevamente dentro del horario de atención."
        ),
        help=(
            "Mensaje de respaldo utilizado cuando no se puede renderizar "
            "la plantilla configurada para fuera de horario."
        ),
    )

    break_message = fields.Text(
        string="Mensaje en refrigerio",
        default=(
            "En este momento nuestro equipo se encuentra en horario de "
            "refrigerio. Puedes registrar por este canal una solicitud de "
            "tóner o servicio técnico y quedará disponible para continuar "
            "su atención al retomar nuestras actividades. La asistencia "
            "remota y la atención directa con un técnico estarán disponibles "
            "nuevamente al finalizar el horario de refrigerio."
        ),
        help=(
            "Mensaje de respaldo utilizado cuando no se puede renderizar "
            "la plantilla configurada para refrigerio."
        ),
    )

    # ==========================================================
    # Plantillas asociadas
    # ==========================================================
    template_after_hours = fields.Char(
        string="Plantilla fuera de horario",
        default="after_hours",
        help=(
            "Nombre técnico de whatsapp.template utilizado cuando la "
            "atención se encuentra fuera de horario."
        ),
    )

    template_break = fields.Char(
        string="Plantilla refrigerio",
        default="in_break",
        help=(
            "Nombre técnico de whatsapp.template utilizado durante el "
            "horario de refrigerio."
        ),
    )

    template_greeting_morning = fields.Char(
        string="Plantilla saludo mañana",
        default="greeting_morning",
        help="Nombre técnico de la plantilla utilizada para el saludo de mañana.",
    )

    template_greeting_afternoon = fields.Char(
        string="Plantilla saludo tarde",
        default="greeting_afternoon",
        help="Nombre técnico de la plantilla utilizada para el saludo de tarde.",
    )

    template_greeting_evening = fields.Char(
        string="Plantilla saludo noche",
        default="greeting_evening",
        help="Nombre técnico de la plantilla utilizada para el saludo de noche.",
    )

    note = fields.Text(
        string="Notas internas",
        help="Observaciones administrativas sobre la configuración del horario.",
    )

    # ==========================================================
    # Restricciones SQL
    # ==========================================================
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
    @api.constrains(
        "open_time",
        "close_time",
        "break_start",
        "break_end",
        "morning_end",
        "afternoon_end",
    )
    def _check_hours(self):
        """
        Valida que todos los valores horarios sean coherentes.

        Se conserva la misma lógica funcional:
        - Todas las horas deben estar entre 0 y 23.99.
        - En un día laboral, apertura < cierre.
        - Si existe refrigerio, inicio < fin.
        - El refrigerio debe estar dentro del horario laboral.
        - El final de la mañana debe ser anterior al final de la tarde.
        """
        for rec in self:
            for field_name in [
                "open_time",
                "close_time",
                "break_start",
                "break_end",
                "morning_end",
                "afternoon_end",
            ]:
                value = rec[field_name]

                if value < 0 or value >= 24:
                    raise ValidationError(
                        _("Las horas deben estar entre 0 y 23.99.")
                    )

            if rec.is_workday and rec.open_time >= rec.close_time:
                raise ValidationError(
                    _("La hora de apertura debe ser menor que la hora de cierre.")
                )

            if rec.has_break:
                if rec.break_start >= rec.break_end:
                    raise ValidationError(
                        _(
                            "El inicio de refrigerio debe ser menor "
                            "que el fin de refrigerio."
                        )
                    )

                if (
                    rec.break_start < rec.open_time
                    or rec.break_end > rec.close_time
                ):
                    raise ValidationError(
                        _("El refrigerio debe estar dentro del horario laboral.")
                    )

            if rec.morning_end >= rec.afternoon_end:
                raise ValidationError(
                    _(
                        "El fin de la mañana debe ser menor "
                        "que el fin de la tarde."
                    )
                )

    # ==========================================================
    # Helpers de presentación
    # ==========================================================
    def _float_to_hhmm(self, value):
        """
        Convierte una hora decimal a HH:MM.

        Ejemplos:
            8.5  -> 08:30
            13.0 -> 13:00
        """
        hours = int(value)
        minutes = int(round((value - hours) * 60))

        if minutes == 60:
            hours += 1
            minutes = 0

        return "%02d:%02d" % (hours, minutes)

    def get_display_hours(self):
        """
        Devuelve una representación legible del horario configurado.
        """
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

    # ==========================================================
    # Helpers de saludo
    # ==========================================================
    def get_greeting_period(self, current_hour_float):
        """
        Determina el período del día según la hora.

        :param current_hour_float: hora decimal, por ejemplo 14.5 = 14:30.
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
        Devuelve el nombre técnico de la plantilla de saludo correspondiente
        al período actual.
        """
        self.ensure_one()

        period = self.get_greeting_period(current_hour_float)

        if period == "morning":
            return self.template_greeting_morning or "greeting_morning"

        if period == "afternoon":
            return self.template_greeting_afternoon or "greeting_afternoon"

        return self.template_greeting_evening or "greeting_evening"

    # ==========================================================
    # Evaluación del estado del horario
    # ==========================================================
    def evaluate_status(self, current_hour_float):
        """
        Evalúa el estado de atención para una hora determinada.

        IMPORTANTE:
        Este método únicamente clasifica el estado del horario.

        No decide qué servicios puede o no puede utilizar el cliente.
        Esa decisión corresponde a la capa conversacional/controlador.

        Estados conservados:
            open
                Horario laboral y fuera del intervalo de refrigerio.

            break
                Dentro del intervalo configurado como refrigerio.

            after_hours
                Día laboral, pero antes de apertura o después del cierre.

            closed_day
                Día configurado como no laboral.

        :param current_hour_float: hora decimal.
        :return: dict con is_open, reason, message, template_name,
                 display_hours y period.
        """
        self.ensure_one()

        # ------------------------------------------------------
        # Día configurado como no laboral
        # ------------------------------------------------------
        if not self.is_workday:
            _logger.info(
                "[WA-HOURS] Estado horario | "
                "day=%s hour=%s status=closed_day is_open=False "
                "display_hours=%s",
                self.day_of_week,
                current_hour_float,
                self.get_display_hours(),
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

        # ------------------------------------------------------
        # Cálculo normal del día
        # ------------------------------------------------------
        in_work = self.open_time <= current_hour_float <= self.close_time

        in_break = (
            self.has_break
            and self.break_start <= current_hour_float <= self.break_end
        )

        # ------------------------------------------------------
        # Refrigerio
        # ------------------------------------------------------
        if in_break:
            _logger.info(
                "[WA-HOURS] Estado horario | "
                "day=%s hour=%s status=break is_open=False "
                "open=%s close=%s break_start=%s break_end=%s",
                self.day_of_week,
                current_hour_float,
                self.open_time,
                self.close_time,
                self.break_start,
                self.break_end,
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

        # ------------------------------------------------------
        # Fuera de horario
        # ------------------------------------------------------
        if not in_work:
            _logger.info(
                "[WA-HOURS] Estado horario | "
                "day=%s hour=%s status=after_hours is_open=False "
                "open=%s close=%s",
                self.day_of_week,
                current_hour_float,
                self.open_time,
                self.close_time,
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

        # ------------------------------------------------------
        # Horario abierto
        # ------------------------------------------------------
        _logger.info(
            "[WA-HOURS] Estado horario | "
            "day=%s hour=%s status=open is_open=True "
            "open=%s close=%s",
            self.day_of_week,
            current_hour_float,
            self.open_time,
            self.close_time,
        )

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
        """
        Crea o actualiza la configuración horaria base.

        Se conserva exactamente la configuración funcional existente.
        """
        _logger.info(
            "[WA-HOURS] Inicializando configuración de horarios por defecto"
        )

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

        for (
            day,
            is_workday,
            open_time,
            close_time,
            has_break,
            break_start,
            break_end,
        ) in defaults:
            existing = self.search(
                [("day_of_week", "=", day)],
                limit=1,
            )

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

                _logger.info(
                    "[WA-HOURS] Horario actualizado | "
                    "day=%s open=%s close=%s has_break=%s "
                    "break_start=%s break_end=%s is_workday=%s",
                    day,
                    open_time,
                    close_time,
                    has_break,
                    break_start,
                    break_end,
                    is_workday,
                )

            else:
                self.create(vals)
                created += 1

                _logger.info(
                    "[WA-HOURS] Horario creado | "
                    "day=%s open=%s close=%s has_break=%s "
                    "break_start=%s break_end=%s is_workday=%s",
                    day,
                    open_time,
                    close_time,
                    has_break,
                    break_start,
                    break_end,
                    is_workday,
                )

        _logger.info(
            "[WA-HOURS] Inicialización completada | created=%s updated=%s",
            created,
            updated,
        )

        return {
            "created": created,
            "updated": updated,
        }
