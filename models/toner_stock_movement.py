# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


class TonerStockMovement(models.Model):
    """
    Kardex histórico del stock de tóner que permanece físicamente
    en las instalaciones del cliente.

    CONCEPTO
    ========

    El stock del cliente NO es el tóner que está instalado en la máquina.

    Ejemplo:

        Máquina:
            1 tóner instalado
            1 tóner de respaldo en stock cliente

        REPLACED:
            el cliente utiliza el repuesto
            stock cliente 1 -> 0

        entrega de 2:
            stock cliente 0 -> 2

    Este modelo registra movimientos y conserva:

        stock_before
        quantity
        stock_after

    El stock actual se obtiene del último movimiento válido del equipo/color,
    no de un campo histórico que se sobrescribe.

    REGLAS
    ======

    + Entrega confirmada:
        quantity = +N

    - Instalación/reemplazo:
        quantity = -1

    + Ajuste:
        puede ser positivo o negativo.

    - Devolución/retiro:
        quantity negativa.

    Si llega REPLACED y el sistema tenía stock 0:

        NO se genera stock -1.

        Se registra una discrepancia:

            stock_before = 0
            quantity_requested = -1
            quantity = 0
            stock_after = 0
            stock_discrepancy = True

    Así mantenemos trazabilidad sin inventar stock negativo.
    """

    _name = "toner.stock.movement"
    _description = "Movimiento de stock de tóner del cliente"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "movement_date desc, id desc"
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

    MOVEMENT_TYPE_SELECTION = [
        ("initial", "Stock inicial"),
        ("delivery", "Entrega al cliente"),
        ("installation", "Instalación / consumo de repuesto"),
        ("adjustment_in", "Ajuste de entrada"),
        ("adjustment_out", "Ajuste de salida"),
        ("return", "Devolución / retiro"),
        ("correction", "Corrección"),
    ]

    SOURCE_SELECTION = [
        ("delivery", "Entrega confirmada"),
        ("printtracker", "PrintTracker"),
        ("email", "Correo"),
        ("snmp", "SNMP"),
        ("api", "API externa"),
        ("manual", "Manual"),
        ("inferred", "Inferido"),
        ("migration", "Migración"),
        ("other", "Otro"),
    ]

    STATE_SELECTION = [
        ("posted", "Confirmado"),
        ("cancelled", "Anulado"),
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

    movement_type = fields.Selection(
        MOVEMENT_TYPE_SELECTION,
        string="Tipo de movimiento",
        required=True,
        index=True,
        tracking=True,
    )

    source = fields.Selection(
        SOURCE_SELECTION,
        string="Origen",
        required=True,
        default="manual",
        index=True,
        tracking=True,
    )

    state = fields.Selection(
        STATE_SELECTION,
        string="Estado",
        required=True,
        default="posted",
        index=True,
        tracking=True,
    )

    movement_date = fields.Datetime(
        string="Fecha del movimiento",
        required=True,
        default=fields.Datetime.now,
        index=True,
        tracking=True,
    )

    # ============================================================
    # CANTIDAD / SALDOS
    # ============================================================

    quantity_requested = fields.Integer(
        string="Cantidad solicitada al kardex",
        required=True,
        default=0,
        readonly=True,
        help=(
            "Cantidad que el evento pretendía mover. "
            "Puede diferir de quantity cuando el sistema detecta "
            "una discrepancia y evita stock negativo."
        ),
    )

    quantity = fields.Integer(
        string="Movimiento aplicado",
        required=True,
        default=0,
        readonly=True,
        tracking=True,
        help=(
            "Cantidad realmente aplicada al stock. "
            "Entradas positivas; salidas negativas."
        ),
    )

    stock_before = fields.Integer(
        string="Stock anterior",
        required=True,
        default=0,
        readonly=True,
        tracking=True,
    )

    stock_after = fields.Integer(
        string="Stock posterior",
        required=True,
        default=0,
        readonly=True,
        tracking=True,
    )

    # ============================================================
    # DISCREPANCIAS
    # ============================================================

    stock_discrepancy = fields.Boolean(
        string="Discrepancia de stock",
        default=False,
        readonly=True,
        index=True,
        tracking=True,
    )

    discrepancy_reason = fields.Text(
        string="Motivo de discrepancia",
        readonly=True,
        tracking=True,
    )

    # ============================================================
    # MARCA / REFERENCIA DEL TÓNER
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

    # ============================================================
    # RELACIONES CON EL FLUJO
    # ============================================================

    submission_id = fields.Many2one(
        "toner.counter.submission",
        string="Solicitud de tóner",
        ondelete="set null",
        index=True,
        copy=False,
    )

    delivery_id = fields.Many2one(
        "toner.delivery.schedule",
        string="Entrega",
        ondelete="set null",
        index=True,
        copy=False,
    )

    monitoring_event_id = fields.Many2one(
        "toner.monitoring.event",
        string="Evento de monitoreo",
        ondelete="set null",
        index=True,
        copy=False,
    )

    installation_history_id = fields.Many2one(
        "toner.installation.history",
        string="Ciclo de tóner",
        ondelete="set null",
        index=True,
        copy=False,
    )

    # ============================================================
    # CONTROL DE IDEMPOTENCIA
    # ============================================================

    external_key = fields.Char(
        string="Clave única del movimiento",
        index=True,
        copy=False,
        readonly=True,
        help=(
            "Clave técnica para evitar movimientos duplicados. "
            "Ejemplos: delivery:25:black o replacement:88:black."
        ),
    )

    # ============================================================
    # AUDITORÍA
    # ============================================================

    created_by_id = fields.Many2one(
        "res.users",
        string="Registrado por",
        default=lambda self: self.env.user,
        readonly=True,
        index=True,
    )

    notes = fields.Text(
        string="Observaciones",
        tracking=True,
    )

    # ============================================================
    # SQL
    # ============================================================

    _sql_constraints = [
        (
            "toner_stock_non_negative_before",
            "CHECK(stock_before >= 0)",
            "El stock anterior no puede ser negativo.",
        ),
        (
            "toner_stock_non_negative_after",
            "CHECK(stock_after >= 0)",
            "El stock posterior no puede ser negativo.",
        ),
        (
            "toner_stock_external_key_unique",
            "UNIQUE(external_key)",
            "Este movimiento de stock ya fue registrado.",
        ),
    ]

    # ============================================================
    # COMPUTES
    # ============================================================

    @api.depends(
        "equipment_id",
        "equipment_serial",
        "color",
        "movement_type",
        "movement_date",
    )
    def _compute_display_name(self):
        color_labels = dict(self.COLOR_SELECTION)
        type_labels = dict(self.MOVEMENT_TYPE_SELECTION)

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

            movement = type_labels.get(
                record.movement_type,
                record.movement_type or _("Movimiento"),
            )

            record.display_name = "%s - %s - %s" % (
                serial,
                color,
                movement,
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

    # ============================================================
    # PROTECCIÓN DE HISTÓRICO
    # ============================================================

    def write(self, vals):
        """
        Los movimientos confirmados son históricos.

        Solo permitimos cambiar campos descriptivos. Para corregir saldos
        debe crearse un movimiento de corrección, no editar el pasado.
        """
        if self.env.context.get("allow_toner_stock_history_write"):
            return super().write(vals)

        protected = {
            "equipment_id",
            "color",
            "movement_type",
            "source",
            "movement_date",
            "quantity_requested",
            "quantity",
            "stock_before",
            "stock_after",
            "stock_discrepancy",
            "discrepancy_reason",
            "submission_id",
            "delivery_id",
            "monitoring_event_id",
            "installation_history_id",
            "external_key",
        }

        if protected.intersection(vals):
            raise UserError(
                _(
                    "Los datos contables del movimiento de stock "
                    "no se pueden modificar. Registre una corrección."
                )
            )

        return super().write(vals)

    def unlink(self):
        """
        Nunca eliminar movimientos confirmados desde operación normal.
        """
        if not self.env.context.get("allow_toner_stock_history_unlink"):
            raise UserError(
                _(
                    "Los movimientos de stock no se eliminan. "
                    "Si existe un error, registre un movimiento "
                    "de corrección."
                )
            )

        return super().unlink()

    # ============================================================
    # STOCK ACTUAL
    # ============================================================

    @api.model
    def get_current_stock(
        self,
        equipment,
        color,
    ):
        """
        Devuelve el stock vigente del cliente para equipo/color.

        Se toma el último movimiento confirmado.
        Si no existe historial, devuelve 0.
        """
        if not equipment or color not in dict(self.COLOR_SELECTION):
            return 0

        last = self.sudo().search(
            [
                ("equipment_id", "=", equipment.id),
                ("color", "=", color),
                ("state", "=", "posted"),
            ],
            order="movement_date desc, id desc",
            limit=1,
        )

        return int(
            last.stock_after
            if last
            else 0
        )

    @api.model
    def get_stock_summary(self, equipment):
        """
        Stock actual K/C/M/Y para un equipo.
        """
        return {
            color: self.get_current_stock(
                equipment,
                color,
            )
            for color, _label in self.COLOR_SELECTION
        }

    # ============================================================
    # CREACIÓN CENTRAL DE MOVIMIENTO
    # ============================================================

    @api.model
    def create_stock_movement(
        self,
        equipment,
        color,
        quantity,
        movement_type,
        source="manual",
        movement_date=False,
        external_key=False,
        submission=False,
        delivery=False,
        monitoring_event=False,
        installation_history=False,
        toner_brand=False,
        part_number=False,
        notes=False,
        prevent_negative=True,
    ):
        """
        Único método recomendado para registrar movimientos.

        Es idempotente cuando recibe external_key.

        quantity:
            + entrada
            - salida

        Si prevent_negative=True y una salida excede el stock:
            no permite stock negativo;
            aplica solamente la cantidad disponible;
            marca discrepancia.
        """

        if not equipment:
            raise ValidationError(
                _("Debe indicar el equipo.")
            )

        if color not in dict(self.COLOR_SELECTION):
            raise ValidationError(
                _("Debe indicar un color válido.")
            )

        if movement_type not in dict(
            self.MOVEMENT_TYPE_SELECTION
        ):
            raise ValidationError(
                _("Tipo de movimiento inválido.")
            )

        if source not in dict(
            self.SOURCE_SELECTION
        ):
            raise ValidationError(
                _("Origen del movimiento inválido.")
            )

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise ValidationError(
                _("La cantidad del movimiento debe ser numérica.")
            )

        if quantity == 0 and movement_type not in (
            "correction",
            "installation",
        ):
            raise ValidationError(
                _("La cantidad del movimiento no puede ser cero.")
            )

        # --------------------------------------------------------
        # IDEMPOTENCIA
        # --------------------------------------------------------

        if external_key:
            existing = self.sudo().search(
                [
                    ("external_key", "=", external_key),
                ],
                limit=1,
            )

            if existing:
                _logger.info(
                    "[TONER STOCK] Movimiento duplicado omitido "
                    "key=%s movement=%s",
                    external_key,
                    existing.id,
                )
                return existing

        # --------------------------------------------------------
        # SALDO ANTERIOR
        # --------------------------------------------------------

        stock_before = self.get_current_stock(
            equipment,
            color,
        )

        requested = quantity
        applied = quantity

        discrepancy = False
        discrepancy_reason = False

        # --------------------------------------------------------
        # EVITAR STOCK NEGATIVO
        # --------------------------------------------------------

        if prevent_negative and quantity < 0:
            requested_out = abs(quantity)

            if requested_out > stock_before:
                # Solo se puede consumir lo que el sistema tenía
                # registrado. Si era cero, applied será cero.
                applied = -stock_before

                discrepancy = True
                discrepancy_reason = _(
                    "Se solicitó descontar %(requested)s unidad(es), "
                    "pero el stock registrado era %(stock)s. "
                    "No se permitió stock negativo."
                ) % {
                    "requested": requested_out,
                    "stock": stock_before,
                }

        stock_after = stock_before + applied

        if stock_after < 0:
            # Seguridad adicional: nunca debería ocurrir.
            stock_after = 0
            discrepancy = True

            if not discrepancy_reason:
                discrepancy_reason = _(
                    "El movimiento fue ajustado para impedir "
                    "un stock negativo."
                )

        vals = {
            "equipment_id": equipment.id,
            "color": color,
            "movement_type": movement_type,
            "source": source,
            "state": "posted",
            "movement_date": (
                movement_date
                or fields.Datetime.now()
            ),
            "quantity_requested": requested,
            "quantity": applied,
            "stock_before": stock_before,
            "stock_after": stock_after,
            "stock_discrepancy": discrepancy,
            "discrepancy_reason": discrepancy_reason,
            "external_key": external_key or False,
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
            "monitoring_event_id": (
                monitoring_event.id
                if monitoring_event
                else False
            ),
            "installation_history_id": (
                installation_history.id
                if installation_history
                else False
            ),
            "toner_brand_id": (
                toner_brand.id
                if toner_brand
                else False
            ),
            "part_number": part_number or False,
            "notes": notes or False,
        }

        movement = self.sudo().create(vals)

        movement._post_equipment_chatter()

        _logger.info(
            "[TONER STOCK] movement=%s equipment=%s color=%s "
            "type=%s requested=%s applied=%s before=%s after=%s "
            "discrepancy=%s",
            movement.id,
            equipment.id,
            color,
            movement_type,
            requested,
            applied,
            stock_before,
            stock_after,
            discrepancy,
        )

        return movement

    # ============================================================
    # STOCK INICIAL
    # ============================================================

    @api.model
    def create_initial_stock(
        self,
        equipment,
        color,
        quantity,
        notes=False,
    ):
        """
        Registra el saldo inicial al comenzar a utilizar el kardex.

        Solo puede existir si todavía no hay movimientos del equipo/color.
        """

        existing = self.sudo().search_count(
            [
                ("equipment_id", "=", equipment.id),
                ("color", "=", color),
                ("state", "=", "posted"),
            ]
        )

        if existing:
            raise ValidationError(
                _(
                    "Ya existen movimientos para este equipo/color. "
                    "Utilice un ajuste en lugar de stock inicial."
                )
            )

        quantity = int(quantity or 0)

        if quantity < 0:
            raise ValidationError(
                _("El stock inicial no puede ser negativo.")
            )

        return self.create_stock_movement(
            equipment=equipment,
            color=color,
            quantity=quantity,
            movement_type="initial",
            source="manual",
            external_key=(
                "initial:%s:%s"
                % (
                    equipment.id,
                    color,
                )
            ),
            notes=notes,
            prevent_negative=True,
        )

    # ============================================================
    # ENTREGA CONFIRMADA
    # ============================================================

    @api.model
    def create_delivery_movements(self, delivery):
        """
        Registra stock SOLO cuando toner.delivery.schedule está ENTREGADO.

        Nunca se incrementa stock por:
            - aprobación;
            - confirmación de ventas;
            - preparación;
            - envío.

        La entrega debe tener state == 'entregado'.

        Devuelve los movimientos creados/reutilizados.
        """
        if not delivery:
            raise ValidationError(
                _("Debe indicar la entrega.")
            )

        if delivery.state != "entregado":
            raise ValidationError(
                _(
                    "El stock del cliente solo puede incrementarse "
                    "cuando la entrega está confirmada como entregada."
                )
            )

        equipment = delivery.equipment_id

        if not equipment:
            raise ValidationError(
                _("La entrega no tiene equipo relacionado.")
            )

        submission = (
            delivery.submission_id
            if (
                "submission_id" in delivery._fields
                and delivery.submission_id
            )
            else False
        )

        movement_date = (
            delivery.delivery_date_actual
            if (
                "delivery_date_actual" in delivery._fields
                and delivery.delivery_date_actual
            )
            else fields.Datetime.now()
        )

        quantity_fields = {
            "black": "toner_black_qty",
            "cyan": "toner_cyan_qty",
            "magenta": "toner_magenta_qty",
            "yellow": "toner_yellow_qty",
        }

        movements = self.browse()

        for color, field_name in quantity_fields.items():
            if field_name not in delivery._fields:
                continue

            qty = int(
                getattr(
                    delivery,
                    field_name,
                    0,
                )
                or 0
            )

            if qty <= 0:
                continue

            toner_brand = False

            if (
                submission
                and (
                    "toner_brand_%s_id" % color
                ) in submission._fields
            ):
                toner_brand = getattr(
                    submission,
                    "toner_brand_%s_id" % color,
                )

            movement = self.create_stock_movement(
                equipment=equipment,
                color=color,
                quantity=qty,
                movement_type="delivery",
                source="delivery",
                movement_date=movement_date,
                external_key=(
                    "delivery:%s:%s"
                    % (
                        delivery.id,
                        color,
                    )
                ),
                submission=submission,
                delivery=delivery,
                toner_brand=toner_brand,
                notes=_(
                    "Entrada automática por entrega confirmada."
                ),
                prevent_negative=True,
            )

            movements |= movement

        return movements

    # ============================================================
    # CONSUMO POR REEMPLAZO / INSTALACIÓN
    # ============================================================

    @api.model
    def consume_for_installation(
        self,
        equipment,
        color,
        monitoring_event=False,
        installation_history=False,
        submission=False,
        delivery=False,
        toner_brand=False,
        source=False,
        movement_date=False,
        notes=False,
    ):
        """
        Descuenta UNA unidad del stock del cliente porque se instaló
        el cartucho de respaldo.

        Si el stock estaba en 0:
            se conserva 0;
            se registra discrepancia;
            no se genera -1.
        """

        if not equipment:
            raise ValidationError(
                _("Debe indicar el equipo.")
            )

        if color not in dict(self.COLOR_SELECTION):
            raise ValidationError(
                _("Color de tóner inválido.")
            )

        if monitoring_event:
            event_key = (
                monitoring_event.external_event_id
                or monitoring_event.id
            )

            external_key = (
                "installation-event:%s:%s"
                % (
                    event_key,
                    color,
                )
            )

            movement_date = (
                movement_date
                or monitoring_event.event_date
                or fields.Datetime.now()
            )

            source = (
                source
                or (
                    monitoring_event.source
                    if monitoring_event.source
                    in dict(self.SOURCE_SELECTION)
                    else "other"
                )
            )

        elif installation_history:
            external_key = (
                "installation-cycle:%s:%s"
                % (
                    installation_history.id,
                    color,
                )
            )

            movement_date = (
                movement_date
                or installation_history.start_date
                or fields.Datetime.now()
            )

            source = source or (
                "inferred"
                if installation_history.start_is_estimated
                else "manual"
            )

        else:
            # Un consumo manual necesita una clave basada en fecha.
            external_key = False
            source = source or "manual"

        return self.create_stock_movement(
            equipment=equipment,
            color=color,
            quantity=-1,
            movement_type="installation",
            source=source,
            movement_date=movement_date,
            external_key=external_key,
            submission=submission,
            delivery=delivery,
            monitoring_event=monitoring_event,
            installation_history=installation_history,
            toner_brand=toner_brand,
            notes=(
                notes
                or _(
                    "Consumo de una unidad del stock del cliente "
                    "por instalación/reemplazo."
                )
            ),
            prevent_negative=True,
        )

    # ============================================================
    # REEMPLAZO CONFIRMADO
    # ============================================================

    @api.model
    def consume_from_replacement_event(
        self,
        event,
        installation_history=False,
    ):
        """
        Atajo para REPLACED confirmado.

        NO vuelve a descontar si el mismo evento ya fue procesado,
        porque external_key garantiza idempotencia.
        """

        if not event:
            raise ValidationError(
                _("Debe indicar el evento.")
            )

        if event.event_type != "replaced":
            raise ValidationError(
                _(
                    "Solo un evento REPLACED puede consumir "
                    "stock mediante este método."
                )
            )

        if not event.equipment_id:
            raise ValidationError(
                _("El evento no tiene equipo relacionado.")
            )

        if event.color not in dict(self.COLOR_SELECTION):
            raise ValidationError(
                _("El evento no tiene un color válido.")
            )

        submission = (
            event.submission_id
            if (
                "submission_id" in event._fields
                and event.submission_id
            )
            else False
        )

        delivery = False
        toner_brand = False

        if installation_history:
            delivery = installation_history.delivery_id
            submission = (
                installation_history.submission_id
                or submission
            )
            toner_brand = installation_history.toner_brand_id

        return self.consume_for_installation(
            equipment=event.equipment_id,
            color=event.color,
            monitoring_event=event,
            installation_history=installation_history,
            submission=submission,
            delivery=delivery,
            toner_brand=toner_brand,
            source=(
                event.source
                if event.source in dict(
                    self.SOURCE_SELECTION
                )
                else "other"
            ),
            movement_date=event.event_date,
            notes=_(
                "Salida automática de stock por reemplazo "
                "confirmado por %(source)s."
            )
            % {
                "source": event.source,
            },
        )

    # ============================================================
    # REEMPLAZO INFERIDO
    # ============================================================

    @api.model
    def consume_from_inferred_cycle(
        self,
        installation_history,
        monitoring_event=False,
    ):
        """
        Descuenta stock cuando el nuevo ciclo fue inferido después
        de EMPTY + recuperación de nivel.

        Se usa una clave por ciclo para no duplicar el descuento.
        """

        if not installation_history:
            raise ValidationError(
                _("Debe indicar el ciclo de tóner.")
            )

        if installation_history.state != "active":
            raise ValidationError(
                _("El ciclo inferido debe estar activo.")
            )

        if not installation_history.start_is_estimated:
            raise ValidationError(
                _(
                    "Este método está reservado para ciclos "
                    "con inicio estimado."
                )
            )

        return self.consume_for_installation(
            equipment=installation_history.equipment_id,
            color=installation_history.color,
            monitoring_event=monitoring_event,
            installation_history=installation_history,
            submission=installation_history.submission_id,
            delivery=installation_history.delivery_id,
            toner_brand=installation_history.toner_brand_id,
            source="inferred",
            movement_date=installation_history.start_date,
            notes=_(
                "Salida de stock por reemplazo inferido "
                "después de recuperación de nivel."
            ),
        )

    # ============================================================
    # AJUSTES MANUALES
    # ============================================================

    @api.model
    def create_adjustment(
        self,
        equipment,
        color,
        quantity,
        notes,
    ):
        """
        Ajuste explícito de inventario.

        quantity > 0:
            ajuste de entrada

        quantity < 0:
            ajuste de salida
        """

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise ValidationError(
                _("La cantidad debe ser un número entero.")
            )

        if quantity == 0:
            raise ValidationError(
                _("El ajuste no puede ser cero.")
            )

        if not notes:
            raise ValidationError(
                _(
                    "Debe indicar el motivo del ajuste."
                )
            )

        return self.create_stock_movement(
            equipment=equipment,
            color=color,
            quantity=quantity,
            movement_type=(
                "adjustment_in"
                if quantity > 0
                else "adjustment_out"
            ),
            source="manual",
            notes=notes,
            prevent_negative=True,
        )

    # ============================================================
    # CORRECCIÓN
    # ============================================================

    @api.model
    def set_stock_by_correction(
        self,
        equipment,
        color,
        real_stock,
        notes,
    ):
        """
        Corrige el sistema hacia el stock físico contado.

        Ejemplo:
            sistema = 0
            físico = 2

            crea +2

        No edita movimientos anteriores.
        """

        try:
            real_stock = int(real_stock)
        except (TypeError, ValueError):
            raise ValidationError(
                _("El stock real debe ser numérico.")
            )

        if real_stock < 0:
            raise ValidationError(
                _("El stock real no puede ser negativo.")
            )

        if not notes:
            raise ValidationError(
                _("Debe indicar el motivo de la corrección.")
            )

        current = self.get_current_stock(
            equipment,
            color,
        )

        difference = real_stock - current

        if difference == 0:
            raise ValidationError(
                _(
                    "El stock registrado ya coincide "
                    "con el stock físico."
                )
            )

        return self.create_stock_movement(
            equipment=equipment,
            color=color,
            quantity=difference,
            movement_type="correction",
            source="manual",
            notes=notes,
            prevent_negative=True,
        )

    # ============================================================
    # ANULACIÓN CONTABLE
    # ============================================================

    def action_reverse(self):
        """
        No modifica el movimiento original.

        Crea un movimiento opuesto y marca el original como cancelado
        mediante contexto técnico permitido.
        """

        reversed_records = self.browse()

        for record in self:
            if record.state == "cancelled":
                continue

            reversal_key = (
                "reverse:%s"
                % record.id
            )

            reversal = self.create_stock_movement(
                equipment=record.equipment_id,
                color=record.color,
                quantity=-record.quantity,
                movement_type="correction",
                source="manual",
                external_key=reversal_key,
                submission=record.submission_id,
                delivery=record.delivery_id,
                monitoring_event=record.monitoring_event_id,
                installation_history=record.installation_history_id,
                toner_brand=record.toner_brand_id,
                part_number=record.part_number,
                notes=_(
                    "Reversión del movimiento %s."
                )
                % record.display_name,
                prevent_negative=True,
            )

            record.with_context(
                allow_toner_stock_history_write=True
            ).write(
                {
                    "state": "cancelled",
                    "notes": (
                        (
                            record.notes
                            + "\n"
                        )
                        if record.notes
                        else ""
                    )
                    + _(
                        "Movimiento revertido mediante %s."
                    )
                    % reversal.display_name,
                }
            )

            reversed_records |= reversal

        return reversed_records

    # ============================================================
    # CHATTER
    # ============================================================

    def _post_equipment_chatter(self):
        self.ensure_one()

        if not self.equipment_id:
            return False

        try:
            body = _(
                "<b>Movimiento de stock de tóner</b><br/>"
                "<b>Color:</b> %(color)s<br/>"
                "<b>Tipo:</b> %(type)s<br/>"
                "<b>Movimiento:</b> %(qty)s<br/>"
                "<b>Stock anterior:</b> %(before)s<br/>"
                "<b>Stock posterior:</b> %(after)s"
            ) % {
                "color": dict(
                    self.COLOR_SELECTION
                ).get(
                    self.color,
                    self.color,
                ),
                "type": dict(
                    self.MOVEMENT_TYPE_SELECTION
                ).get(
                    self.movement_type,
                    self.movement_type,
                ),
                "qty": self.quantity,
                "before": self.stock_before,
                "after": self.stock_after,
            }

            if self.stock_discrepancy:
                body += _(
                    "<br/><b>⚠ Discrepancia:</b> %s"
                ) % (
                    self.discrepancy_reason
                    or _("Stock inconsistente")
                )

            self.equipment_id.message_post(
                body=body,
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )

            return True

        except Exception:
            _logger.exception(
                "[TONER STOCK] Error escribiendo chatter "
                "equipment=%s movement=%s",
                self.equipment_id.id,
                self.id,
            )
            return False

    # ============================================================
    # ACCIONES
    # ============================================================

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

    def action_view_monitoring_event(self):
        self.ensure_one()

        if not self.monitoring_event_id:
            raise UserError(
                _("No existe un evento relacionado.")
            )

        return {
            "name": _("Evento de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.monitoring.event",
            "view_mode": "form",
            "res_id": self.monitoring_event_id.id,
            "target": "current",
        }

    def action_view_installation_history(self):
        self.ensure_one()

        if not self.installation_history_id:
            raise UserError(
                _("No existe un ciclo relacionado.")
            )

        return {
            "name": _("Historial de instalación"),
            "type": "ir.actions.act_window",
            "res_model": "toner.installation.history",
            "view_mode": "form",
            "res_id": self.installation_history_id.id,
            "target": "current",
        }
