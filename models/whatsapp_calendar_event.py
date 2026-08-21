# -*- coding: utf-8 -*-

import logging
from datetime import date, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class WhatsappCalendarEvent(models.Model):
    """
    Excepciones de calendario utilizadas por WhatsApp y otros procesos
    laborales compartidos.

    Responsabilidad exclusiva:
    determinar si una fecha/hora está abierta, cerrada o en refrigerio
    especial. Este modelo no decide intención, tipo de contacto ni modo
    humano.

    Tipos:
    - holiday: feriado nacional;
    - manual_closed: cierre manual;
    - special_hours: horario excepcional para una fecha;
    - info: evento informativo que no altera disponibilidad.
    """

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
        help=(
            "Si está activo, la fecha se considera cerrada todo el día. "
            "Para Horario especial e Informativo normalmente debe estar desactivado."
        ),
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
        normalized_list = []

        for vals in vals_list:
            vals = dict(vals or {})
            event_type = vals.get(
                "event_type",
                "holiday",
            )

            # El default histórico de is_closed es True. Para eventos que
            # por definición no son cierres totales, corregimos solo cuando
            # el valor no fue especificado explícitamente.
            if "is_closed" not in vals:
                if event_type in (
                    "special_hours",
                    "info",
                ):
                    vals["is_closed"] = False
                elif event_type in (
                    "holiday",
                    "manual_closed",
                ):
                    vals["is_closed"] = True

            normalized_list.append(
                vals
            )

        records = super().create(
            normalized_list
        )

        for rec in records:
            _logger.info(
                "[WA-CAL] Evento creado | "
                "id=%s name=%s date=%s type=%s source=%s "
                "is_closed=%s display_hours=%s",
                rec.id,
                rec.name,
                rec.event_date,
                rec.event_type,
                rec.source,
                rec.is_closed,
                rec.get_display_hours(),
            )

        return records

    def write(self, vals):
        vals = dict(vals or {})

        # Si el usuario cambia el tipo y no indicó expresamente is_closed,
        # mantener una configuración coherente con ese nuevo tipo.
        if (
            "event_type" in vals
            and "is_closed" not in vals
        ):
            if vals["event_type"] in (
                "special_hours",
                "info",
            ):
                vals["is_closed"] = False
            elif vals["event_type"] in (
                "holiday",
                "manual_closed",
            ):
                vals["is_closed"] = True

        result = super().write(
            vals
        )

        tracked = {
            "active",
            "event_date",
            "event_type",
            "is_closed",
            "special_open_time",
            "special_close_time",
            "has_special_break",
            "special_break_start",
            "special_break_end",
            "message",
            "template_name",
        }

        if tracked.intersection(vals.keys()):
            for rec in self:
                _logger.info(
                    "[WA-CAL] Evento modificado | "
                    "id=%s date=%s type=%s active=%s is_closed=%s "
                    "display_hours=%s",
                    rec.id,
                    rec.event_date,
                    rec.event_type,
                    rec.active,
                    rec.is_closed,
                    rec.get_display_hours(),
                )

        return result

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
        Evalúa exclusivamente disponibilidad para una hora decimal.

        El dict retornado es compatible con _compute_business_status().
        """
        self.ensure_one()

        try:
            current_hour_float = float(
                current_hour_float
            )
        except Exception:
            _logger.warning(
                "[WA-CAL] Hora inválida para evaluar evento | "
                "id=%s value=%r",
                self.id,
                current_hour_float,
            )
            current_hour_float = 0.0

        if (
            self.event_type in (
                "holiday",
                "manual_closed",
            )
            or self.is_closed
        ):
            _logger.info(
                "[WA-CAL] Fecha cerrada por calendario | "
                "id=%s date=%s type=%s name=%s",
                self.id,
                self.event_date,
                self.event_type,
                self.name,
            )

            return {
                "is_open": False,
                "reason": self.event_type,
                "reason_label": self.name,
                "message": (
                    self.message
                    or (
                        "Hoy no contamos con atención en tiempo real. "
                        "Puedes registrar solicitudes permitidas por este canal."
                    )
                ),
                "template_name": (
                    self.template_name
                    or False
                ),
                "event_id": self.id,
                "display_hours": (
                    self.get_display_hours()
                ),
            }

        if self.event_type == "special_hours":
            in_work = (
                self.special_open_time
                <= current_hour_float
                <= self.special_close_time
            )

            in_break = (
                self.has_special_break
                and self.special_break_start
                <= current_hour_float
                <= self.special_break_end
            )

            if in_break:
                _logger.info(
                    "[WA-CAL] Refrigerio especial | "
                    "id=%s date=%s hour=%s break=%s-%s",
                    self.id,
                    self.event_date,
                    current_hour_float,
                    self.special_break_start,
                    self.special_break_end,
                )

                return {
                    "is_open": False,
                    "reason": "special_hours_break",
                    "reason_label": self.name,
                    "message": (
                        self.message
                        or (
                            "En este momento nuestro equipo se encuentra "
                            "en horario de refrigerio especial."
                        )
                    ),
                    "template_name": (
                        self.template_name
                        or False
                    ),
                    "event_id": self.id,
                    "display_hours": (
                        self.get_display_hours()
                    ),
                }

            if in_work:
                _logger.debug(
                    "[WA-CAL] Horario especial abierto | "
                    "id=%s date=%s hour=%s",
                    self.id,
                    self.event_date,
                    current_hour_float,
                )

                return {
                    "is_open": True,
                    "reason": "special_hours_open",
                    "reason_label": self.name,
                    "message": False,
                    "template_name": False,
                    "event_id": self.id,
                    "display_hours": (
                        self.get_display_hours()
                    ),
                }

            _logger.info(
                "[WA-CAL] Fuera de horario especial | "
                "id=%s date=%s hour=%s hours=%s",
                self.id,
                self.event_date,
                current_hour_float,
                self.get_display_hours(),
            )

            return {
                "is_open": False,
                "reason": "special_hours_closed",
                "reason_label": self.name,
                "message": (
                    self.message
                    or (
                        "En este momento nos encontramos fuera "
                        "del horario especial de atención."
                    )
                ),
                "template_name": (
                    self.template_name
                    or False
                ),
                "event_id": self.id,
                "display_hours": (
                    self.get_display_hours()
                ),
            }

        # Informativo: no cambia disponibilidad.
        return {
            "is_open": True,
            "reason": "info_event",
            "reason_label": self.name,
            "message": self.message or False,
            "template_name": (
                self.template_name
                or False
            ),
            "event_id": self.id,
            "display_hours": "",
        }

    # ==========================================================
    # Calendario laboral compartido
    # ==========================================================
    @api.model
    def is_closed_date(self, work_date):
        """Indica si la fecha está cerrada por feriado o cierre manual."""
        if not work_date:
            return False

        try:
            work_date = fields.Date.to_date(
                work_date
            )
        except Exception:
            _logger.warning(
                "[WA-CAL] Fecha inválida en is_closed_date | value=%r",
                work_date,
            )
            return False

        event = self.search([
            ("event_date", "=", work_date),
            ("active", "=", True),
            ("is_closed", "=", True),
            (
                "event_type",
                "in",
                [
                    "holiday",
                    "manual_closed",
                ],
            ),
        ], limit=1)

        return bool(event)

    @api.model
    def get_workday_factor(self, work_date):
        """
        Factor laboral general usado por evaluación y ausencias:
        - feriado/cierre: 0.0
        - lunes a viernes: 1.0
        - sábado: 0.5
        - domingo: 0.0
        """
        if not work_date or self.is_closed_date(work_date):
            return 0.0
        if work_date.weekday() < 5:
            return 1.0
        if work_date.weekday() == 5:
            return 0.5
        return 0.0

    @api.model
    def get_working_days_equivalent(self, start_date, end_date):
        """Suma factores laborales en el rango [start_date, end_date)."""
        if not start_date or not end_date or end_date <= start_date:
            return 0.0

        total = 0.0
        current = start_date
        while current < end_date:
            total += self.get_workday_factor(current)
            current += timedelta(days=1)
        return total

    @api.model
    def _easter_sunday(self, year):
        """Calcula el Domingo de Pascua para el calendario gregoriano."""
        year = int(year)
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        return date(year, month, day)

    # ==========================================================
    # Feriados Perú
    # ==========================================================
    @api.model
    def get_peru_holidays(self, year):
        """Feriados nacionales del Perú, incluyendo Semana Santa móvil."""
        year = int(year)
        easter = self._easter_sunday(year)
        holy_thursday = easter - timedelta(days=3)
        good_friday = easter - timedelta(days=2)

        return [
            (date(year, 1, 1), "Año Nuevo"),
            (holy_thursday, "Jueves Santo"),
            (good_friday, "Viernes Santo"),
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

        _logger.info("[WA-CAL] Cargando feriados Perú | year=%s", year)

        holidays = self.get_peru_holidays(year)
        created = 0
        updated = 0

        default_message = (
            "Hoy nuestro equipo se encuentra fuera del horario regular por feriado. "
            "Las solicitudes habilitadas por el asistente virtual pueden registrarse "
            "normalmente; la atención remota o humana continuará en horario disponible."
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
            "[WA-CAL] Feriados Perú cargados | year=%s created=%s updated=%s",
            year,
            created,
            updated,
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