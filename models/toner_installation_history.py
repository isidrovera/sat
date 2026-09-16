# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError


_logger = logging.getLogger(__name__)


class TonerInstallationHistory(models.Model):
    """
    Historial físico de cada ciclo de tóner instalado en un equipo.

    Un registro representa UN cartucho/ciclo:

        inicio -> uso -> fin

    La información histórica nunca debe sobrescribirse para representar
    un cartucho posterior. Cuando existe un reemplazo, se cierra el ciclo
    activo y se crea otro registro.

    Este modelo NO administra stock. El stock se manejará en
    toner.stock.movement para mantener un kardex independiente.

    Este modelo está preparado para recibir eventos provenientes de
    toner.monitoring.event:

        EMPTY
            -> puede cerrar el ciclo activo.

        REPLACED
            -> cierra el ciclo anterior si sigue activo y abre uno nuevo.

        NORMAL después de EMPTY sin REPLACED
            -> podrá abrir un nuevo ciclo inferido utilizando como base
               el contador del EMPTY.

    La conexión automática con toner.monitoring.event se realizará en el
    siguiente paso para mantener cada cambio aislado y comprobable.
    """

    _name = "toner.installation.history"
    _description = "Historial de instalación de tóner"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, id desc"
    _rec_name = "display_name"

    # ============================================================
    # CONSTANTES
    # ============================================================

    COLOR_SELECTION = [
        ("black", "Negro"),
        ("cyan", "Cian"),
        ("magenta", "Magenta"),
        ("yellow", "Amarillo"),
    ]

    STATE_SELECTION = [
        ("active", "Activo"),
        ("finished", "Finalizado"),
        ("cancelled", "Cancelado"),
    ]

    SOURCE_SELECTION = [
        ("printtracker", "PrintTracker"),
        ("email", "Correo"),
        ("snmp", "SNMP"),
        ("api", "API externa"),
        ("manual", "Manual"),
        ("empty_inferred", "Inferido desde tóner vacío"),
        ("level_recovery", "Inferido por recuperación de nivel"),
        ("legacy", "Datos anteriores"),
        ("other", "Otro"),
    ]

    END_REASON_SELECTION = [
        ("empty", "Tóner vacío"),
        ("replaced", "Tóner reemplazado"),
        ("manual", "Cierre manual"),
        ("correction", "Corrección"),
        ("unknown", "No determinado"),
    ]

    # ============================================================
    # IDENTIFICACIÓN
    # ============================================================

    display_name = fields.Char(
        string="Nombre",
        compute="_compute_display_name",
        store=True,
        index=True,
    )

    equipment_id = fields.Many2one(
        "alquiler",
        string="Equipo",
        required=True,
        index=True,
        ondelete="restrict",
        tracking=True,
    )

    equipment_serial = fields.Char(
        string="Serie",
        related="equipment_id.serie",
        store=True,
        readonly=True,
        index=True,
    )

    partner_id = fields.Many2one(
        "res.partner",
        string="Cliente",
        compute="_compute_partner_id",
        store=True,
        readonly=True,
        index=True,
    )

    color = fields.Selection(
        COLOR_SELECTION,
        string="Color",
        required=True,
        index=True,
        tracking=True,
    )

    state = fields.Selection(
        STATE_SELECTION,
        string="Estado",
        required=True,
        default="active",
        index=True,
        tracking=True,
    )

    # ============================================================
    # IDENTIFICACIÓN DEL CARTUCHO
    # ============================================================

    toner_brand_id = fields.Many2one(
        "toner.brand",
        string="Marca del tóner",
        ondelete="restrict",
        index=True,
        tracking=True,
    )

    part_number = fields.Char(
        string="Número de parte",
        tracking=True,
    )

    cartridge_serial = fields.Char(
        string="Serie del cartucho",
        tracking=True,
    )

    printtracker_supply_id = fields.Many2one(
        "printtracker.supply",
        string="Suministro PrintTracker",
        ondelete="set null",
        index=True,
        copy=False,
    )

    supply_key = fields.Char(
        string="Supply Key",
        index=True,
        copy=False,
    )

    # ============================================================
    # INICIO DEL CICLO
    # ============================================================

    start_date = fields.Datetime(
        string="Fecha de inicio",
        required=True,
        default=fields.Datetime.now,
        index=True,
        tracking=True,
    )

    start_counter = fields.Integer(
        string="Contador inicial",
        required=True,
        default=0,
        tracking=True,
        help=(
            "Para negro se utiliza contador B/N. "
            "Para cian, magenta y amarillo se utiliza contador color."
        ),
    )

    start_source = fields.Selection(
        SOURCE_SELECTION,
        string="Origen del inicio",
        required=True,
        default="manual",
        index=True,
        tracking=True,
    )

    start_is_estimated = fields.Boolean(
        string="Inicio estimado",
        default=False,
        tracking=True,
        help=(
            "Marcado cuando el sistema infiere el comienzo del cartucho "
            "porque no recibió una notificación explícita de reemplazo."
        ),
    )

    start_event_id = fields.Many2one(
        "toner.monitoring.event",
        string="Evento de inicio",
        ondelete="set null",
        index=True,
        copy=False,
    )

    # ============================================================
    # FIN DEL CICLO
    # ============================================================

    end_date = fields.Datetime(
        string="Fecha de fin",
        index=True,
        tracking=True,
    )

    end_counter = fields.Integer(
        string="Contador final",
        tracking=True,
        help=(
            "Para negro se utiliza contador B/N. "
            "Para cian, magenta y amarillo se utiliza contador color."
        ),
    )

    end_source = fields.Selection(
        SOURCE_SELECTION,
        string="Origen del fin",
        index=True,
        tracking=True,
    )

    end_is_estimated = fields.Boolean(
        string="Fin estimado",
        default=False,
        tracking=True,
    )

    end_reason = fields.Selection(
        END_REASON_SELECTION,
        string="Motivo de fin",
        index=True,
        tracking=True,
    )

    end_event_id = fields.Many2one(
        "toner.monitoring.event",
        string="Evento de fin",
        ondelete="set null",
        index=True,
        copy=False,
    )

    # ============================================================
    # RELACIONES OPERATIVAS
    # ============================================================

    submission_id = fields.Many2one(
        "toner.counter.submission",
        string="Solicitud relacionada",
        ondelete="set null",
        index=True,
        copy=False,
        tracking=True,
    )

    delivery_id = fields.Many2one(
        "toner.delivery.schedule",
        string="Entrega relacionada",
        ondelete="set null",
        index=True,
        copy=False,
        tracking=True,
    )

    # ============================================================
    # RENDIMIENTO
    # ============================================================

    expected_yield = fields.Integer(
        string="Rendimiento esperado",
        default=0,
        tracking=True,
        help=(
            "Se guarda como snapshot al iniciar el ciclo para que un cambio "
            "posterior en la configuración del modelo no altere el histórico."
        ),
    )

    copies_produced = fields.Integer(
        string="Copias producidas",
        compute="_compute_performance",
        store=True,
    )

    yield_percent = fields.Float(
        string="Rendimiento real (%)",
        compute="_compute_performance",
        store=True,
        digits=(16, 2),
    )

    days_in_use = fields.Integer(
        string="Días en uso",
        compute="_compute_performance",
        store=True,
    )

    # ============================================================
    # CONTROL / AUDITORÍA
    # ============================================================

    opened_by_id = fields.Many2one(
        "res.users",
        string="Creado por",
        default=lambda self: self.env.user,
        readonly=True,
        index=True,
    )

    closed_by_id = fields.Many2one(
        "res.users",
        string="Cerrado por",
        readonly=True,
        copy=False,
        index=True,
    )

    notes = fields.Text(
        string="Observaciones",
        tracking=True,
    )

    # ============================================================
    # COMPUTES
    # ============================================================

    @api.depends("equipment_id", "color", "start_date", "state")
    def _compute_display_name(self):
        color_labels = dict(self.COLOR_SELECTION)
        state_labels = dict(self.STATE_SELECTION)

        for record in self:
            serial = (
                record.equipment_serial
                or (
                    record.equipment_id.serie
                    if record.equipment_id
                    else False
                )
                or _("Sin serie")
            )

            color = color_labels.get(
                record.color,
                record.color or _("Sin color"),
            )

            state = state_labels.get(
                record.state,
                record.state or "",
            )

            date_text = ""
            if record.start_date:
                try:
                    date_text = fields.Datetime.to_string(
                        record.start_date
                    )
                except Exception:
                    date_text = str(record.start_date)

            record.display_name = "%s - %s - %s - %s" % (
                serial,
                color,
                state,
                date_text,
            )

    @api.depends("equipment_id")
    def _compute_partner_id(self):
        for record in self:
            partner = False

            if record.equipment_id:
                if (
                    "cliente_id" in record.equipment_id._fields
                    and record.equipment_id.cliente_id
                ):
                    partner = record.equipment_id.cliente_id
                elif (
                    "partner_id" in record.equipment_id._fields
                    and record.equipment_id.partner_id
                ):
                    partner = record.equipment_id.partner_id

            record.partner_id = partner

    @api.depends(
        "start_counter",
        "end_counter",
        "expected_yield",
        "start_date",
        "end_date",
        "state",
    )
    def _compute_performance(self):
        now = fields.Datetime.now()

        for record in self:
            copies = 0
            yield_percent = 0.0

            if (
                record.end_counter
                and record.end_counter >= record.start_counter
            ):
                copies = int(
                    record.end_counter - record.start_counter
                )

            if record.expected_yield > 0 and copies >= 0:
                yield_percent = (
                    float(copies)
                    / float(record.expected_yield)
                    * 100.0
                )

            start_dt = fields.Datetime.to_datetime(
                record.start_date
            ) if record.start_date else False

            end_dt = fields.Datetime.to_datetime(
                record.end_date
            ) if record.end_date else now

            days = 0
            if start_dt and end_dt and end_dt >= start_dt:
                days = max(
                    0,
                    (end_dt - start_dt).days,
                )

            record.copies_produced = copies
            record.yield_percent = round(
                yield_percent,
                2,
            )
            record.days_in_use = days

    # ============================================================
    # VALIDACIONES
    # ============================================================

    @api.constrains(
        "start_counter",
        "end_counter",
        "start_date",
        "end_date",
        "state",
    )
    def _check_cycle_values(self):
        for record in self:
            if record.start_counter < 0:
                raise ValidationError(
                    _("El contador inicial no puede ser negativo.")
                )

            if record.end_counter and record.end_counter < 0:
                raise ValidationError(
                    _("El contador final no puede ser negativo.")
                )

            if (
                record.end_counter
                and record.end_counter < record.start_counter
            ):
                raise ValidationError(
                    _(
                        "El contador final no puede ser menor "
                        "que el contador inicial."
                    )
                )

            if record.start_date and record.end_date:
                start_dt = fields.Datetime.to_datetime(
                    record.start_date
                )
                end_dt = fields.Datetime.to_datetime(
                    record.end_date
                )

                if end_dt < start_dt:
                    raise ValidationError(
                        _(
                            "La fecha final no puede ser anterior "
                            "a la fecha inicial."
                        )
                    )

            if record.state == "finished":
                if not record.end_date:
                    raise ValidationError(
                        _(
                            "Un ciclo finalizado debe tener "
                            "fecha de fin."
                        )
                    )

                if not record.end_reason:
                    raise ValidationError(
                        _(
                            "Un ciclo finalizado debe tener "
                            "un motivo de fin."
                        )
                    )

    @api.constrains(
        "equipment_id",
        "color",
        "state",
    )
    def _check_single_active_cycle(self):
        """
        Solo puede existir un ciclo activo por equipo y color.

        Se valida a nivel ORM porque PostgreSQL no permite expresar
        fácilmente este índice parcial mediante _sql_constraints.
        """
        for record in self:
            if (
                not record.equipment_id
                or not record.color
                or record.state != "active"
            ):
                continue

            duplicate = self.search(
                [
                    ("id", "!=", record.id),
                    (
                        "equipment_id",
                        "=",
                        record.equipment_id.id,
                    ),
                    ("color", "=", record.color),
                    ("state", "=", "active"),
                ],
                limit=1,
            )

            if duplicate:
                raise ValidationError(
                    _(
                        "Ya existe un tóner %(color)s activo "
                        "para el equipo %(serie)s."
                    )
                    % {
                        "color": dict(
                            self.COLOR_SELECTION
                        ).get(
                            record.color,
                            record.color,
                        ),
                        "serie": (
                            record.equipment_serial
                            or record.equipment_id.serie
                            or record.equipment_id.display_name
                        ),
                    }
                )

    # ============================================================
    # HELPERS DE CONTADOR
    # ============================================================

    @api.model
    def get_counter_from_event(self, event, color=None):
        """
        Devuelve el contador relevante del evento.

        Negro:
            counter_bn

        C/M/Y:
            counter_color

        Devuelve 0 si el evento no tiene un contador utilizable.
        """
        if not event:
            return 0

        color = color or event.color

        if color == "black":
            return max(
                0,
                int(event.counter_bn or 0),
            )

        if color in (
            "cyan",
            "magenta",
            "yellow",
        ):
            return max(
                0,
                int(event.counter_color or 0),
            )

        return 0

    @api.model
    def _get_expected_yield_for_equipment(
        self,
        equipment,
        color,
    ):
        """
        Obtiene el rendimiento esperado usando la misma lógica conceptual
        que toner.counter.submission.

        Si el método oficial existe, se reutiliza.
        """
        if not equipment or not color:
            return 0

        Submission = self.env[
            "toner.counter.submission"
        ].sudo()

        if hasattr(
            Submission,
            "_get_expected_yield",
        ):
            try:
                return int(
                    Submission._get_expected_yield(
                        equipment,
                        color,
                    )
                    or 0
                )
            except Exception:
                _logger.exception(
                    "[TONER HISTORY] Error obteniendo rendimiento "
                    "equipo=%s color=%s",
                    equipment.id,
                    color,
                )

        return 0

    # ============================================================
    # HELPERS DE RELACIONES
    # ============================================================

    @api.model
    def _find_latest_delivered_for_color(
        self,
        equipment,
        color,
        before_date=False,
    ):
        """
        Busca la última entrega confirmada que contiene el color.

        Sirve para vincular el ciclo con la solicitud/entrega que
        probablemente entregó el cartucho utilizado.
        """
        if not equipment or not color:
            return self.env["toner.delivery.schedule"]

        quantity_field = {
            "black": "toner_black_qty",
            "cyan": "toner_cyan_qty",
            "magenta": "toner_magenta_qty",
            "yellow": "toner_yellow_qty",
        }.get(color)

        if not quantity_field:
            return self.env["toner.delivery.schedule"]

        domain = [
            ("equipment_id", "=", equipment.id),
            ("state", "=", "entregado"),
            (quantity_field, ">", 0),
        ]

        if before_date:
            domain += [
                "|",
                (
                    "delivery_date_actual",
                    "<=",
                    before_date,
                ),
                "&",
                (
                    "delivery_date_actual",
                    "=",
                    False,
                ),
                (
                    "creation_date",
                    "<=",
                    before_date,
                ),
            ]

        return self.env[
            "toner.delivery.schedule"
        ].sudo().search(
            domain,
            order=(
                "delivery_date_actual desc, "
                "creation_date desc, id desc"
            ),
            limit=1,
        )

    # ============================================================
    # OBTENER CICLO ACTIVO
    # ============================================================

    @api.model
    def get_active_cycle(
        self,
        equipment,
        color,
    ):
        if not equipment or not color:
            return self.browse()

        return self.sudo().search(
            [
                (
                    "equipment_id",
                    "=",
                    equipment.id,
                ),
                ("color", "=", color),
                ("state", "=", "active"),
            ],
            order="start_date desc, id desc",
            limit=1,
        )

    # ============================================================
    # ABRIR CICLO
    # ============================================================

    @api.model
    def open_cycle(
        self,
        equipment,
        color,
        start_counter=0,
        start_date=False,
        start_source="manual",
        start_is_estimated=False,
        start_event=False,
        toner_brand=False,
        printtracker_supply=False,
        submission=False,
        delivery=False,
        notes=False,
    ):
        """
        Crea un nuevo ciclo activo.

        No cierra automáticamente otro ciclo activo. Esa decisión debe
        hacerse explícitamente mediante replace_cycle() o close_cycle()
        para preservar trazabilidad.
        """
        if not equipment:
            raise ValidationError(
                _("Debe indicar el equipo.")
            )

        if color not in dict(
            self.COLOR_SELECTION
        ):
            raise ValidationError(
                _("Debe indicar un color de tóner válido.")
            )

        active = self.get_active_cycle(
            equipment,
            color,
        )

        if active:
            raise ValidationError(
                _(
                    "Ya existe un ciclo activo para el tóner %(color)s "
                    "del equipo %(serie)s."
                )
                % {
                    "color": dict(
                        self.COLOR_SELECTION
                    ).get(
                        color,
                        color,
                    ),
                    "serie": (
                        equipment.serie
                        or equipment.display_name
                    ),
                }
            )

        start_counter = max(
            0,
            int(start_counter or 0),
        )

        start_date = (
            start_date
            or (
                start_event.event_date
                if start_event
                else fields.Datetime.now()
            )
        )

        expected_yield = (
            self._get_expected_yield_for_equipment(
                equipment,
                color,
            )
        )

        if not delivery:
            delivery = (
                self._find_latest_delivered_for_color(
                    equipment,
                    color,
                    before_date=start_date,
                )
            )

        if not submission and delivery:
            submission = delivery.submission_id

        if (
            not toner_brand
            and submission
            and (
                "toner_brand_%s_id" % color
            ) in submission._fields
        ):
            toner_brand = getattr(
                submission,
                "toner_brand_%s_id" % color,
            )

        vals = {
            "equipment_id": equipment.id,
            "color": color,
            "state": "active",
            "start_date": start_date,
            "start_counter": start_counter,
            "start_source": start_source,
            "start_is_estimated": bool(
                start_is_estimated
            ),
            "start_event_id": (
                start_event.id
                if start_event
                else False
            ),
            "toner_brand_id": (
                toner_brand.id
                if toner_brand
                else False
            ),
            "printtracker_supply_id": (
                printtracker_supply.id
                if printtracker_supply
                else False
            ),
            "supply_key": (
                (
                    printtracker_supply.supply_key
                    if printtracker_supply
                    else False
                )
                or (
                    start_event.supply_key
                    if start_event
                    else False
                )
            ),
            "part_number": (
                (
                    printtracker_supply.part_number
                    if printtracker_supply
                    else False
                )
                or (
                    start_event.part_number
                    if start_event
                    else False
                )
            ),
            "submission_id": (
                submission.id
                if submission
                else False
            ),
            "delivery_id": (
                delivery.id
                if delivery
                else False
            ),
            "expected_yield": expected_yield,
            "notes": notes or False,
        }

        cycle = self.sudo().create(
            vals
        )

        cycle._post_equipment_chatter(
            _(
                "<b>Nuevo ciclo de tóner registrado</b><br/>"
                "<b>Color:</b> %(color)s<br/>"
                "<b>Contador inicial:</b> %(counter)s<br/>"
                "<b>Origen:</b> %(source)s<br/>"
                "<b>Estimado:</b> %(estimated)s"
            )
            % {
                "color": cycle._get_color_label(),
                "counter": cycle.start_counter,
                "source": cycle._get_source_label(
                    cycle.start_source
                ),
                "estimated": (
                    _("Sí")
                    if cycle.start_is_estimated
                    else _("No")
                ),
            }
        )

        _logger.info(
            "[TONER HISTORY] Ciclo abierto id=%s equipment=%s "
            "color=%s counter=%s source=%s estimated=%s",
            cycle.id,
            equipment.id,
            color,
            cycle.start_counter,
            cycle.start_source,
            cycle.start_is_estimated,
        )

        return cycle

    # ============================================================
    # CERRAR CICLO
    # ============================================================

    def close_cycle(
        self,
        end_counter=0,
        end_date=False,
        end_source="manual",
        end_reason="manual",
        end_is_estimated=False,
        end_event=False,
        notes=False,
    ):
        """
        Cierra un ciclo activo.

        Si el evento no trae contador, se permite cerrar con contador 0
        solo cuando start_counter también es 0. Cuando existe contador
        inicial positivo y falta contador final, el ciclo NO se cierra:
        se exige preservar la calidad del histórico.
        """
        self.ensure_one()

        if self.state == "finished":
            return self

        if self.state == "cancelled":
            raise UserError(
                _("No se puede cerrar un ciclo cancelado.")
            )

        counter = max(
            0,
            int(end_counter or 0),
        )

        if (
            self.start_counter > 0
            and counter <= 0
        ):
            raise ValidationError(
                _(
                    "No se puede finalizar este ciclo sin "
                    "un contador final válido."
                )
            )

        if (
            counter
            and counter < self.start_counter
        ):
            raise ValidationError(
                _(
                    "El contador final (%(end)s) no puede ser "
                    "menor que el inicial (%(start)s)."
                )
                % {
                    "end": counter,
                    "start": self.start_counter,
                }
            )

        end_date = (
            end_date
            or (
                end_event.event_date
                if end_event
                else fields.Datetime.now()
            )
        )

        vals = {
            "state": "finished",
            "end_date": end_date,
            "end_counter": counter,
            "end_source": end_source,
            "end_reason": end_reason,
            "end_is_estimated": bool(
                end_is_estimated
            ),
            "end_event_id": (
                end_event.id
                if end_event
                else False
            ),
            "closed_by_id": self.env.user.id,
        }

        if notes:
            vals["notes"] = (
                ("%s\n" % self.notes)
                if self.notes
                else ""
            ) + notes

        self.write(vals)

        self._post_equipment_chatter(
            _(
                "<b>Ciclo de tóner finalizado</b><br/>"
                "<b>Color:</b> %(color)s<br/>"
                "<b>Contador inicial:</b> %(start)s<br/>"
                "<b>Contador final:</b> %(end)s<br/>"
                "<b>Copias producidas:</b> %(copies)s<br/>"
                "<b>Motivo:</b> %(reason)s"
            )
            % {
                "color": self._get_color_label(),
                "start": self.start_counter,
                "end": self.end_counter,
                "copies": self.copies_produced,
                "reason": self._get_end_reason_label(),
            }
        )

        _logger.info(
            "[TONER HISTORY] Ciclo cerrado id=%s equipment=%s "
            "color=%s start=%s end=%s copies=%s reason=%s",
            self.id,
            self.equipment_id.id,
            self.color,
            self.start_counter,
            self.end_counter,
            self.copies_produced,
            self.end_reason,
        )

        return self

    # ============================================================
    # CERRAR POR EMPTY
    # ============================================================

    @api.model
    def close_from_empty_event(self, event):
        """
        Usa un evento EMPTY para finalizar el ciclo activo.

        EMPTY NO abre automáticamente el siguiente ciclo porque todavía
        no sabemos si el cliente ya instaló el cartucho de stock.

        El contador EMPTY queda como final del ciclo y podrá utilizarse
        después como base estimada del siguiente ciclo si nunca llega
        REPLACED.
        """
        if not event:
            return self.browse()

        if event.event_type != "empty":
            raise ValidationError(
                _(
                    "El evento debe ser de tipo Tóner vacío."
                )
            )

        if not event.equipment_id:
            raise ValidationError(
                _("El evento no tiene equipo relacionado.")
            )

        color = event.color
        if color not in dict(
            self.COLOR_SELECTION
        ):
            raise ValidationError(
                _(
                    "No se pudo identificar el color "
                    "del evento EMPTY."
                )
            )

        cycle = self.get_active_cycle(
            event.equipment_id,
            color,
        )

        if not cycle:
            _logger.warning(
                "[TONER HISTORY] EMPTY sin ciclo activo "
                "event=%s equipment=%s color=%s",
                event.id,
                event.equipment_id.id,
                color,
            )
            return self.browse()

        counter = self.get_counter_from_event(
            event,
            color,
        )

        if cycle.start_counter > 0 and counter <= 0:
            raise ValidationError(
                _(
                    "El evento EMPTY no tiene un contador "
                    "válido para cerrar el ciclo."
                )
            )

        return cycle.close_cycle(
            end_counter=counter,
            end_date=event.event_date,
            end_source=event.source,
            end_reason="empty",
            end_is_estimated=bool(
                event.counter_is_estimated
            ),
            end_event=event,
            notes=_(
                "Cierre automático por evento EMPTY."
            ),
        )

    # ============================================================
    # REEMPLAZO CONFIRMADO
    # ============================================================

    @api.model
    def replace_cycle_from_event(self, event):
        """
        Procesa un REPLACED confirmado.

        Reglas:

        1. Si hay ciclo activo:
           - lo cierra con el contador del REPLACED;
           - abre el nuevo ciclo en ese mismo contador.

        2. Si el ciclo anterior ya fue cerrado por EMPTY:
           - NO vuelve a cerrarlo;
           - abre el nuevo ciclo con el contador REPLACED.

        3. Si REPLACED no trae contador:
           - utiliza el end_counter del último ciclo EMPTY como base;
           - en ese caso el inicio se marca estimado.

        4. No modifica stock. El descuento de stock se hará mediante
           toner.stock.movement en el siguiente paso.
        """
        if not event:
            return self.browse()

        if event.event_type != "replaced":
            raise ValidationError(
                _(
                    "El evento debe ser de tipo "
                    "Tóner reemplazado."
                )
            )

        equipment = event.equipment_id

        if not equipment:
            raise ValidationError(
                _("El evento no tiene equipo relacionado.")
            )

        color = event.color

        if color not in dict(
            self.COLOR_SELECTION
        ):
            raise ValidationError(
                _(
                    "No se pudo identificar el color "
                    "del reemplazo."
                )
            )

        # Si ya existe un ciclo cuyo inicio es exactamente este evento,
        # devolverlo. Evita duplicar un reemplazo reintentado.
        already_created = self.sudo().search(
            [
                ("start_event_id", "=", event.id),
                ("equipment_id", "=", equipment.id),
                ("color", "=", color),
            ],
            limit=1,
        )

        if already_created:
            return already_created

        event_counter = self.get_counter_from_event(
            event,
            color,
        )

        active = self.get_active_cycle(
            equipment,
            color,
        )

        # --------------------------------------------------------
        # Cerrar ciclo anterior si continúa activo.
        # --------------------------------------------------------
        if active:
            if (
                active.start_counter > 0
                and event_counter <= 0
            ):
                raise ValidationError(
                    _(
                        "PrintTracker confirmó el reemplazo, "
                        "pero no existe un contador válido para "
                        "cerrar el ciclo anterior."
                    )
                )

            active.close_cycle(
                end_counter=event_counter,
                end_date=event.event_date,
                end_source=event.source,
                end_reason="replaced",
                end_is_estimated=bool(
                    event.counter_is_estimated
                ),
                end_event=event,
                notes=_(
                    "Cierre automático por reemplazo confirmado."
                ),
            )

        # --------------------------------------------------------
        # Si no hay contador REPLACED, buscar último EMPTY cerrado.
        # --------------------------------------------------------
        start_counter = event_counter
        start_is_estimated = bool(
            event.counter_is_estimated
        )
        start_source = event.source

        if start_counter <= 0:
            last_finished = self.sudo().search(
                [
                    ("equipment_id", "=", equipment.id),
                    ("color", "=", color),
                    ("state", "=", "finished"),
                    ("end_reason", "=", "empty"),
                    ("end_counter", ">", 0),
                ],
                order="end_date desc, id desc",
                limit=1,
            )

            if last_finished:
                start_counter = int(
                    last_finished.end_counter
                    or 0
                )
                start_is_estimated = True
                start_source = "empty_inferred"

        supply = (
            event.printtracker_supply_id
            if (
                "printtracker_supply_id"
                in event._fields
            )
            else False
        )

        return self.open_cycle(
            equipment=equipment,
            color=color,
            start_counter=start_counter,
            start_date=event.event_date,
            start_source=start_source,
            start_is_estimated=start_is_estimated,
            start_event=event,
            printtracker_supply=supply,
            notes=_(
                "Nuevo ciclo creado por evento REPLACED."
            ),
        )

    # ============================================================
    # INFERIR REEMPLAZO DESPUÉS DE EMPTY
    # ============================================================

    @api.model
    def infer_replacement_from_level_event(
        self,
        event,
    ):
        """
        Infiere un nuevo cartucho cuando:

            - existe un ciclo anterior finalizado por EMPTY;
            - no existe ciclo activo;
            - posteriormente llega un nivel NORMAL/LEVEL con nivel > 0.

        El inicio usa como base el contador final del EMPTY anterior.

        Esta inferencia es necesaria porque no todos los sistemas notifican
        explícitamente REPLACED.
        """
        if not event:
            return self.browse()

        if event.event_type not in (
            "normal",
            "level",
        ):
            return self.browse()

        if not event.equipment_id:
            return self.browse()

        color = event.color

        if color not in dict(
            self.COLOR_SELECTION
        ):
            return self.browse()

        # Debe existir evidencia de recuperación de nivel.
        if (
            event.level_percent is False
            or event.level_percent is None
            or float(
                event.level_percent
                or 0.0
            ) <= 0.0
        ):
            return self.browse()

        active = self.get_active_cycle(
            event.equipment_id,
            color,
        )

        if active:
            return active

        previous = self.sudo().search(
            [
                (
                    "equipment_id",
                    "=",
                    event.equipment_id.id,
                ),
                ("color", "=", color),
                ("state", "=", "finished"),
                ("end_reason", "=", "empty"),
                ("end_counter", ">", 0),
            ],
            order="end_date desc, id desc",
            limit=1,
        )

        if not previous:
            return self.browse()

        # No inferir si el evento es anterior o igual al EMPTY.
        if (
            previous.end_date
            and event.event_date
            and fields.Datetime.to_datetime(
                event.event_date
            )
            <= fields.Datetime.to_datetime(
                previous.end_date
            )
        ):
            return self.browse()

        supply = (
            event.printtracker_supply_id
            if (
                "printtracker_supply_id"
                in event._fields
            )
            else False
        )

        cycle = self.open_cycle(
            equipment=event.equipment_id,
            color=color,
            start_counter=int(
                previous.end_counter
                or 0
            ),
            start_date=event.event_date,
            start_source="level_recovery",
            start_is_estimated=True,
            start_event=event,
            printtracker_supply=supply,
            notes=_(
                "Inicio inferido: el sistema detectó una "
                "recuperación de nivel después de un EMPTY "
                "sin recibir un evento REPLACED."
            ),
        )

        _logger.info(
            "[TONER HISTORY] Reemplazo inferido cycle=%s "
            "previous=%s event=%s",
            cycle.id,
            previous.id,
            event.id,
        )

        return cycle

    # ============================================================
    # ACCIONES MANUALES
    # ============================================================

    def action_finish_manual(self):
        """
        No cierra silenciosamente sin contador. Se utiliza desde formularios
        donde el usuario ya haya registrado end_counter.
        """
        for record in self:
            if record.state != "active":
                continue

            record.close_cycle(
                end_counter=record.end_counter,
                end_date=(
                    record.end_date
                    or fields.Datetime.now()
                ),
                end_source="manual",
                end_reason=(
                    record.end_reason
                    or "manual"
                ),
                end_is_estimated=record.end_is_estimated,
                notes=_(
                    "Cierre realizado manualmente por %s."
                )
                % self.env.user.name,
            )

        return True

    def action_cancel_cycle(self):
        for record in self:
            if record.state == "finished":
                raise UserError(
                    _(
                        "No se puede cancelar un ciclo "
                        "ya finalizado."
                    )
                )

            record.write(
                {
                    "state": "cancelled",
                }
            )

        return True

    def action_reopen_cycle(self):
        """
        Solo permite reabrir si no existe otro ciclo activo del mismo
        equipo/color.
        """
        for record in self:
            if record.state != "finished":
                continue

            active = record.get_active_cycle(
                record.equipment_id,
                record.color,
            )

            if active:
                raise UserError(
                    _(
                        "No se puede reabrir porque ya existe "
                        "otro ciclo activo."
                    )
                )

            record.write(
                {
                    "state": "active",
                    "end_date": False,
                    "end_counter": 0,
                    "end_source": False,
                    "end_reason": False,
                    "end_is_estimated": False,
                    "end_event_id": False,
                    "closed_by_id": False,
                }
            )

        return True

    def action_view_equipment(self):
        self.ensure_one()

        return {
            "name": _("Equipo"),
            "type": "ir.actions.act_window",
            "res_model": "alquiler",
            "view_mode": "form",
            "res_id": self.equipment_id.id,
            "target": "current",
        }

    def action_view_submission(self):
        self.ensure_one()

        if not self.submission_id:
            raise UserError(
                _("No existe una solicitud relacionada.")
            )

        return {
            "name": _("Solicitud de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.counter.submission",
            "view_mode": "form",
            "res_id": self.submission_id.id,
            "target": "current",
        }

    def action_view_delivery(self):
        self.ensure_one()

        if not self.delivery_id:
            raise UserError(
                _("No existe una entrega relacionada.")
            )

        return {
            "name": _("Entrega de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.delivery.schedule",
            "view_mode": "form",
            "res_id": self.delivery_id.id,
            "target": "current",
        }

    # ============================================================
    # CHATTER / LABELS
    # ============================================================

    def _post_equipment_chatter(self, body):
        self.ensure_one()

        if not self.equipment_id:
            return False

        try:
            self.equipment_id.message_post(
                body=body,
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )
            return True

        except Exception:
            _logger.exception(
                "[TONER HISTORY] Error escribiendo chatter "
                "equipment=%s cycle=%s",
                self.equipment_id.id,
                self.id,
            )
            return False

    def _get_color_label(self):
        self.ensure_one()
        return dict(
            self.COLOR_SELECTION
        ).get(
            self.color,
            self.color or _("Sin color"),
        )

    @api.model
    def _get_source_label(self, source):
        return dict(
            self.SOURCE_SELECTION
        ).get(
            source,
            source or _("Sin origen"),
        )

    def _get_end_reason_label(self):
        self.ensure_one()
        return dict(
            self.END_REASON_SELECTION
        ).get(
            self.end_reason,
            self.end_reason or _("Sin motivo"),
        )
