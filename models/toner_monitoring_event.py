# -*- coding: utf-8 -*-

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


class TonerMonitoringEvent(models.Model):
    """
    Evento normalizado de monitoreo de tóner.

    Este modelo es la puerta de entrada común para:

        - PrintTracker
        - Correo
        - SNMP
        - API externa
        - Registro manual
        - Otros sistemas

    RESPONSABILIDADES
    =================

    1. Guardar el evento normalizado.
    2. Evitar procesar dos veces el mismo evento.
    3. Crear/enlazar toner.counter.submission cuando corresponda.
    4. Gestionar el ciclo físico del tóner mediante
       toner.installation.history.
    5. Gestionar el stock de respaldo del cliente mediante
       toner.stock.movement.

    REGLAS PRINCIPALES
    ==================

    LOW / CRITICAL
        - guardan evento;
        - crean solicitud si no existe una activa;
        - NO modifican stock;
        - NO cierran el ciclo instalado.

    EMPTY
        - guardan evento;
        - cierran el ciclo activo si existe y hay contador suficiente;
        - crean solicitud si no existe una activa;
        - NO descuentan stock todavía.

    REPLACED
        - guardan evento;
        - cierran ciclo anterior si sigue activo;
        - crean nuevo ciclo;
        - descuentan 1 del stock de respaldo;
        - NO crean una nueva solicitud.

    NORMAL / LEVEL después de EMPTY sin REPLACED
        - puede inferir un nuevo ciclo;
        - descuenta 1 del stock una sola vez;
        - inicio marcado como estimado.

    Este modelo NUNCA crea toner.delivery.schedule directamente.
    """

    _name = "toner.monitoring.event"
    _description = "Evento de monitoreo de tóner"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "event_date desc, id desc"
    _rec_name = "display_name"

    # ============================================================
    # CONSTANTES
    # ============================================================

    COLOR_SELECTION = [
        ("black", "Negro"),
        ("cyan", "Cian"),
        ("magenta", "Magenta"),
        ("yellow", "Amarillo"),
        ("unknown", "No identificado"),
    ]

    SOURCE_SELECTION = [
        ("printtracker", "PrintTracker"),
        ("email", "Correo"),
        ("snmp", "SNMP"),
        ("api", "API externa"),
        ("manual", "Manual"),
        ("other", "Otro"),
    ]

    EVENT_TYPE_SELECTION = [
        ("level", "Lectura de nivel"),
        ("low", "Tóner bajo"),
        ("critical", "Tóner crítico"),
        ("empty", "Tóner vacío"),
        ("replaced", "Tóner reemplazado"),
        ("normal", "Nivel normal"),
        ("estimated_depletion", "Agotamiento estimado"),
        ("supply_event", "Evento de suministro"),
        ("unknown", "Evento no identificado"),
    ]

    PROCESSING_STATE_SELECTION = [
        ("new", "Nuevo"),
        ("pending_data", "Pendiente de datos"),
        ("processed", "Procesado"),
        ("ignored", "Ignorado"),
        ("error", "Error"),
    ]

    REQUEST_TRIGGER_EVENTS = {
        "low",
        "critical",
        "empty",
    }

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

    # ============================================================
    # ORIGEN
    # ============================================================

    source = fields.Selection(
        SOURCE_SELECTION,
        string="Origen",
        required=True,
        default="manual",
        index=True,
        tracking=True,
    )

    external_event_id = fields.Char(
        string="ID externo del evento",
        index=True,
        copy=False,
        help=(
            "Identificador del evento en el sistema origen. "
            "Ejemplo: Event ID de PrintTracker o Message-ID de correo."
        ),
    )

    source_reference = fields.Char(
        string="Referencia externa",
        index=True,
        copy=False,
        help=(
            "Referencia adicional del sistema origen, por ejemplo "
            "Supply Key, Device Key o identificador de mensaje."
        ),
    )

    printtracker_alert_id = fields.Many2one(
        "printtracker.alert",
        string="Alerta PrintTracker",
        ondelete="set null",
        index=True,
        copy=False,
    )

    printtracker_supply_id = fields.Many2one(
        "printtracker.supply",
        string="Suministro PrintTracker",
        ondelete="set null",
        index=True,
        copy=False,
    )

    # ============================================================
    # EVENTO
    # ============================================================

    event_type = fields.Selection(
        EVENT_TYPE_SELECTION,
        string="Tipo de evento",
        required=True,
        default="unknown",
        index=True,
        tracking=True,
    )

    color = fields.Selection(
        COLOR_SELECTION,
        string="Color",
        required=True,
        default="unknown",
        index=True,
        tracking=True,
    )

    event_date = fields.Datetime(
        string="Fecha del evento",
        required=True,
        default=fields.Datetime.now,
        index=True,
        tracking=True,
    )

    level_percent = fields.Float(
        string="Nivel de tóner (%)",
        digits=(16, 2),
        tracking=True,
        help=(
            "Porcentaje informado por el sistema externo. "
            "Puede quedar vacío si el evento no incluye porcentaje."
        ),
    )

    level_value = fields.Integer(
        string="Nivel bruto",
        help="Valor bruto enviado por el sistema origen.",
    )

    level_max = fields.Integer(
        string="Nivel máximo",
        help="Valor máximo utilizado por el sistema origen.",
    )

    level_available = fields.Boolean(
        string="Nivel disponible",
        default=False,
        index=True,
        tracking=True,
        help=(
            "Indica que el nivel fue informado realmente por la fuente. "
            "Permite distinguir un 0% real de un dato ausente."
        ),
    )

    estimated_depletion_date = fields.Date(
        string="Agotamiento estimado",
        index=True,
        tracking=True,
        help=(
            "Fecha estimada de agotamiento informada por el sistema externo. "
            "Es información adicional del evento y no reemplaza su tipo "
            "principal (por ejemplo LOW o CRITICAL). Tampoco equivale a EMPTY."
        ),
    )

    # ============================================================
    # CONTADORES
    # ============================================================

    counter_bn = fields.Integer(
        string="Contador B/N",
        tracking=True,
        help="Contador B/N informado al momento del evento.",
    )

    counter_color = fields.Integer(
        string="Contador color",
        tracking=True,
        help="Contador color informado al momento del evento.",
    )

    counter_bn_available = fields.Boolean(
        string="Contador B/N disponible",
        default=False,
        index=True,
        help=(
            "Indica que counter_bn proviene de una lectura válida. "
            "Un valor 0 con este campo desmarcado significa dato ausente."
        ),
    )

    counter_color_available = fields.Boolean(
        string="Contador color disponible",
        default=False,
        index=True,
        help=(
            "Indica que counter_color proviene de una lectura válida. "
            "Un valor 0 con este campo desmarcado significa dato ausente."
        ),
    )

    counter_is_estimated = fields.Boolean(
        string="Contador estimado",
        default=False,
        tracking=True,
        help=(
            "Indica si el contador fue obtenido por inferencia o por una "
            "lectura cercana y no directamente desde el evento."
        ),
    )

    # ============================================================
    # DATOS DEL SUMINISTRO
    # ============================================================

    supply_key = fields.Char(
        string="Supply Key",
        index=True,
    )

    supply_type = fields.Char(
        string="Tipo de suministro externo",
    )

    supply_name = fields.Char(
        string="Nombre del suministro",
    )

    part_number = fields.Char(
        string="Número de parte",
    )

    toner_brand_id = fields.Many2one(
        "toner.brand",
        string="Marca del tóner",
        ondelete="restrict",
        index=True,
    )

    # ============================================================
    # DATOS ORIGINALES
    # ============================================================

    raw_description = fields.Text(
        string="Descripción original",
    )

    raw_subject = fields.Char(
        string="Asunto original",
    )

    raw_payload = fields.Text(
        string="Datos originales",
        copy=False,
        help=(
            "JSON, texto de correo o contenido original recibido. "
            "Se conserva para auditoría."
        ),
    )

    # ============================================================
    # PROCESAMIENTO
    # ============================================================

    processing_state = fields.Selection(
        PROCESSING_STATE_SELECTION,
        string="Estado de procesamiento",
        required=True,
        default="new",
        index=True,
        tracking=True,
    )

    processed = fields.Boolean(
        string="Procesado",
        compute="_compute_processed",
        store=True,
        index=True,
    )

    processed_date = fields.Datetime(
        string="Fecha de procesamiento",
        readonly=True,
        copy=False,
    )

    processing_message = fields.Text(
        string="Resultado del procesamiento",
        readonly=True,
        copy=False,
    )

    processing_error = fields.Text(
        string="Error",
        readonly=True,
        copy=False,
    )

    # ============================================================
    # RELACIONES DE NEGOCIO
    # ============================================================

    submission_id = fields.Many2one(
        "toner.counter.submission",
        string="Solicitud de tóner",
        ondelete="set null",
        index=True,
        copy=False,
        tracking=True,
    )

    submission_created = fields.Boolean(
        string="Solicitud creada automáticamente",
        readonly=True,
        copy=False,
    )

    duplicate_submission_id = fields.Many2one(
        "toner.counter.submission",
        string="Solicitud existente",
        readonly=True,
        copy=False,
        ondelete="set null",
    )

    installation_history_id = fields.Many2one(
        "toner.installation.history",
        string="Ciclo de tóner relacionado",
        ondelete="set null",
        index=True,
        copy=False,
        tracking=True,
    )

    stock_movement_id = fields.Many2one(
        "toner.stock.movement",
        string="Movimiento de stock relacionado",
        ondelete="set null",
        index=True,
        copy=False,
        tracking=True,
    )

    # ============================================================
    # SQL
    # ============================================================

    _sql_constraints = [
        (
            "toner_monitoring_level_percent_check",
            "CHECK(level_percent IS NULL OR "
            "(level_percent >= 0 AND level_percent <= 100))",
            "El nivel de tóner debe estar entre 0 y 100.",
        ),
        (
            "toner_monitoring_counter_bn_check",
            "CHECK(counter_bn >= 0)",
            "El contador B/N no puede ser negativo.",
        ),
        (
            "toner_monitoring_counter_color_check",
            "CHECK(counter_color >= 0)",
            "El contador color no puede ser negativo.",
        ),
    ]

    # ============================================================
    # COMPUTES
    # ============================================================

    @api.depends(
        "equipment_id",
        "equipment_serial",
        "event_type",
        "color",
        "event_date",
    )
    def _compute_display_name(self):
        event_labels = dict(self.EVENT_TYPE_SELECTION)
        color_labels = dict(self.COLOR_SELECTION)

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

            event_label = event_labels.get(
                record.event_type,
                record.event_type or _("Evento"),
            )

            color_label = color_labels.get(
                record.color,
                record.color or _("Sin color"),
            )

            record.display_name = "%s - %s - %s" % (
                serial,
                event_label,
                color_label,
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

    @api.depends("processing_state")
    def _compute_processed(self):
        for record in self:
            record.processed = record.processing_state in (
                "processed",
                "ignored",
            )

    # ============================================================
    # VALIDACIONES
    # ============================================================

    @api.constrains(
        "source",
        "external_event_id",
    )
    def _check_external_event_unique(self):
        """
        Un mismo ID puede existir en sistemas diferentes.
        La unicidad funcional correcta es:

            source + external_event_id
        """
        for record in self:
            if not record.external_event_id:
                continue

            duplicate = self.search(
                [
                    ("id", "!=", record.id),
                    ("source", "=", record.source),
                    (
                        "external_event_id",
                        "=",
                        record.external_event_id,
                    ),
                ],
                limit=1,
            )

            if duplicate:
                raise ValidationError(
                    _(
                        "El evento %(event)s del origen %(source)s "
                        "ya fue registrado."
                    )
                    % {
                        "event": record.external_event_id,
                        "source": record.source,
                    }
                )

    # ============================================================
    # CREACIÓN NORMALIZADA
    # ============================================================

    @api.model
    def create_normalized_event(self, values):
        """
        Punto de entrada recomendado para todas las integraciones.

        1. evita duplicados;
        2. crea el evento;
        3. ejecuta la lógica central;
        4. devuelve el registro.

        Si ya existe source + external_event_id devuelve el existente.
        """
        values = dict(values or {})

        source = values.get("source") or "other"
        external_event_id = values.get("external_event_id")

        if external_event_id:
            existing = self.search(
                [
                    ("source", "=", source),
                    (
                        "external_event_id",
                        "=",
                        external_event_id,
                    ),
                ],
                limit=1,
            )

            if existing:
                _logger.info(
                    "[TONER EVENT] Evento duplicado omitido "
                    "source=%s external_event_id=%s record=%s",
                    source,
                    external_event_id,
                    existing.id,
                )
                return existing

        event = self.create(values)

        try:
            event.action_process_event()
        except Exception:
            _logger.exception(
                "[TONER EVENT] Error procesando evento id=%s",
                event.id,
            )

        return event

    # ============================================================
    # PROCESAMIENTO CENTRAL
    # ============================================================

    def action_process_event(self):
        for event in self:
            try:
                event._process_event()

            except Exception as error:
                _logger.exception(
                    "[TONER EVENT] Error procesando evento "
                    "id=%s equipo=%s tipo=%s",
                    event.id,
                    event.equipment_serial,
                    event.event_type,
                )

                event.write(
                    {
                        "processing_state": "error",
                        "processing_error": str(error),
                        "processing_message": _(
                            "El evento no pudo procesarse."
                        ),
                    }
                )

        return True

    def _process_event(self):
        self.ensure_one()

        if self.processing_state == "processed":
            _logger.info(
                "[TONER EVENT] Evento %s ya procesado.",
                self.id,
            )
            return True

        if not self.equipment_id:
            self._mark_pending(
                _("No se pudo identificar el equipo.")
            )
            return False

        if self.event_type == "unknown":
            self._mark_pending(
                _("El tipo de evento no pudo identificarse.")
            )
            return False

        # --------------------------------------------------------
        # Normalizar color
        # --------------------------------------------------------

        if (
            self.event_type
            in (
                "low",
                "critical",
                "empty",
                "replaced",
                "normal",
                "level",
                "estimated_depletion",
                "supply_event",
            )
            and self.color == "unknown"
        ):
            if self.equipment_id.tipo_maquina_id != "color":
                self.color = "black"
            else:
                self._mark_pending(
                    _(
                        "El evento pertenece a un equipo color "
                        "pero no se pudo identificar el color."
                    )
                )
                return False

        # --------------------------------------------------------
        # LOW / CRITICAL
        # --------------------------------------------------------

        if self.event_type in (
            "low",
            "critical",
        ):
            return self._process_request_trigger()

        # --------------------------------------------------------
        # EMPTY
        # --------------------------------------------------------

        if self.event_type == "empty":
            return self._process_empty_event()

        # --------------------------------------------------------
        # REPLACED
        # --------------------------------------------------------

        if self.event_type == "replaced":
            return self._process_replaced_event()

        # --------------------------------------------------------
        # NORMAL / LEVEL
        # --------------------------------------------------------

        if self.event_type in (
            "normal",
            "level",
        ):
            return self._process_level_event()

        # --------------------------------------------------------
        # AGOTAMIENTO ESTIMADO
        # --------------------------------------------------------

        if self.event_type == "estimated_depletion":
            if self.estimated_depletion_date:
                self._mark_processed(
                    _(
                        "Predicción de agotamiento registrada para %(date)s. "
                        "No se modificó stock, no se cerró el ciclo y no se "
                        "interpretó como nivel 0%%."
                    )
                    % {
                        "date": fields.Date.to_string(
                            self.estimated_depletion_date
                        )
                    }
                )
            else:
                self._mark_processed(
                    _(
                        "Evento de agotamiento estimado registrado sin fecha "
                        "interpretable. No se modificó stock ni historial."
                    )
                )
            return True

        # --------------------------------------------------------
        # EVENTO DE SUMINISTRO GENÉRICO
        # --------------------------------------------------------

        if self.event_type == "supply_event":
            self._mark_processed(
                _(
                    "Evento de suministro registrado para auditoría. "
                    "No contiene una acción física confirmada."
                )
            )
            return True

        return False

    # ============================================================
    # EMPTY
    # ============================================================

    def _process_empty_event(self):
        """
        EMPTY:
            - cerrar ciclo activo si existe;
            - NO descontar stock;
            - crear/enlazar solicitud.
        """
        self.ensure_one()

        History = self.env[
            "toner.installation.history"
        ].sudo()

        active_cycle = History.get_active_cycle(
            self.equipment_id,
            self.color,
        )

        history_message = ""

        if active_cycle:
            try:
                closed = History.close_from_empty_event(
                    self
                )

                if closed:
                    self.installation_history_id = closed.id
                    history_message = _(
                        " Ciclo anterior cerrado por EMPTY."
                    )

            except ValidationError as error:
                # El evento se conserva, pero si falta contador no
                # destruimos el ciclo ni inventamos uno.
                _logger.warning(
                    "[TONER EVENT] EMPTY pendiente por historial "
                    "event=%s error=%s",
                    self.id,
                    error,
                )
                history_message = _(
                    " No se pudo cerrar el ciclo: %s"
                ) % error

        else:
            history_message = _(
                " No existía un ciclo activo para cerrar."
            )

        # EMPTY también puede iniciar el proceso de reposición.
        request_result = self._process_request_trigger(
            final_message_prefix=_(
                "Evento EMPTY registrado."
            )
            + history_message
        )

        return request_result

    # ============================================================
    # REPLACED
    # ============================================================

    def _process_replaced_event(self):
        """
        REPLACED:
            - crear/reutilizar nuevo ciclo;
            - descontar una unidad del stock;
            - no crear solicitud nueva.
        """
        self.ensure_one()

        History = self.env[
            "toner.installation.history"
        ].sudo()

        Stock = self.env[
            "toner.stock.movement"
        ].sudo()

        # --------------------------------------------------------
        # Crear/reutilizar ciclo nuevo
        # --------------------------------------------------------

        cycle = History.replace_cycle_from_event(
            self
        )

        if not cycle:
            self._mark_pending(
                _(
                    "Se recibió REPLACED pero no fue posible "
                    "crear el nuevo ciclo de tóner."
                )
            )
            return False

        self.installation_history_id = cycle.id

        # --------------------------------------------------------
        # Descontar stock
        # --------------------------------------------------------

        movement = Stock.consume_from_replacement_event(
            self,
            installation_history=cycle,
        )

        if movement:
            self.stock_movement_id = movement.id

        message = _(
            "Reemplazo confirmado. "
            "Nuevo ciclo %(cycle)s creado. "
            "Stock %(before)s → %(after)s."
        ) % {
            "cycle": cycle.display_name,
            "before": (
                movement.stock_before
                if movement
                else "?"
            ),
            "after": (
                movement.stock_after
                if movement
                else "?"
            ),
        }

        if (
            movement
            and movement.stock_discrepancy
        ):
            message += " " + _(
                "Se detectó discrepancia de stock: %s"
            ) % (
                movement.discrepancy_reason
                or _("sin detalle")
            )

        self._mark_processed(message)

        self._post_equipment_chatter(
            _(
                "<b>Reemplazo de tóner procesado</b><br/>"
                "<b>Color:</b> %(color)s<br/>"
                "<b>Ciclo:</b> %(cycle)s<br/>"
                "<b>Stock anterior:</b> %(before)s<br/>"
                "<b>Stock posterior:</b> %(after)s"
            )
            % {
                "color": self._get_color_label(),
                "cycle": cycle.display_name,
                "before": (
                    movement.stock_before
                    if movement
                    else "?"
                ),
                "after": (
                    movement.stock_after
                    if movement
                    else "?"
                ),
            }
        )

        return True

    # ============================================================
    # NORMAL / LEVEL
    # ============================================================

    def _process_level_event(self):
        """
        Una lectura normal puede confirmar indirectamente que hubo un
        reemplazo cuando previamente se recibió EMPTY pero nunca REPLACED.
        """
        self.ensure_one()

        if not self.level_available:
            self._mark_processed(
                _(
                    "Evento de nivel registrado sin lectura numérica válida. "
                    "No se infirió reemplazo y no se modificó stock."
                )
            )
            return True

        History = self.env[
            "toner.installation.history"
        ].sudo()

        Stock = self.env[
            "toner.stock.movement"
        ].sudo()

        cycle = History.infer_replacement_from_level_event(
            self
        )

        # Si no se infirió reemplazo, solo guardar la lectura.
        if not cycle:
            self._mark_processed(
                _("Lectura de nivel registrada.")
            )
            return True

        self.installation_history_id = cycle.id

        movement = Stock.consume_from_inferred_cycle(
            installation_history=cycle,
            monitoring_event=self,
        )

        if movement:
            self.stock_movement_id = movement.id

        message = _(
            "Se infirió un reemplazo por recuperación de nivel. "
            "Nuevo ciclo %(cycle)s. Stock %(before)s → %(after)s."
        ) % {
            "cycle": cycle.display_name,
            "before": (
                movement.stock_before
                if movement
                else "?"
            ),
            "after": (
                movement.stock_after
                if movement
                else "?"
            ),
        }

        if (
            movement
            and movement.stock_discrepancy
        ):
            message += " " + _(
                "Se detectó discrepancia de stock: %s"
            ) % (
                movement.discrepancy_reason
                or _("sin detalle")
            )

        self._mark_processed(message)

        self._post_equipment_chatter(
            _(
                "<b>Reemplazo de tóner inferido</b><br/>"
                "<b>Color:</b> %(color)s<br/>"
                "<b>Motivo:</b> recuperación de nivel "
                "después de EMPTY sin evento REPLACED.<br/>"
                "<b>Stock:</b> %(before)s → %(after)s"
            )
            % {
                "color": self._get_color_label(),
                "before": (
                    movement.stock_before
                    if movement
                    else "?"
                ),
                "after": (
                    movement.stock_after
                    if movement
                    else "?"
                ),
            }
        )

        return True

    # ============================================================
    # CREAR / ENLAZAR SOLICITUD
    # ============================================================

    def _process_request_trigger(
        self,
        final_message_prefix=False,
    ):
        """
        LOW / CRITICAL / EMPTY.

        Nunca crea despacho directamente.
        """
        self.ensure_one()

        existing_submission = self._find_open_submission()

        if existing_submission:
            self.write(
                {
                    "submission_id": existing_submission.id,
                    "duplicate_submission_id": existing_submission.id,
                    "submission_created": False,
                }
            )

            prefix = (
                (final_message_prefix + " ")
                if final_message_prefix
                else ""
            )

            self._mark_processed(
                prefix
                + _(
                    "Ya existe una solicitud activa %(sequence)s "
                    "para el tóner %(color)s."
                )
                % {
                    "sequence": (
                        existing_submission.secuencia
                        or existing_submission.display_name
                    ),
                    "color": self._get_color_label(),
                }
            )

            return True

        # --------------------------------------------------------
        # Contador B/N obligatorio por el modelo actual
        # --------------------------------------------------------

        if (
            not self.counter_bn_available
            or self.counter_bn <= 0
        ):
            prefix = (
                (final_message_prefix + " ")
                if final_message_prefix
                else ""
            )

            self._mark_pending(
                prefix
                + _(
                    "El evento fue registrado, pero no tiene "
                    "un contador B/N válido para crear "
                    "automáticamente la solicitud."
                )
            )

            return False

        if (
            self.color in ("cyan", "magenta", "yellow")
            and (
                not self.counter_color_available
                or self.counter_color <= 0
            )
        ):
            prefix = (
                (final_message_prefix + " ")
                if final_message_prefix
                else ""
            )

            self._mark_pending(
                prefix
                + _(
                    "El evento fue registrado, pero no tiene "
                    "un contador color válido para crear "
                    "automáticamente la solicitud."
                )
            )
            return False

        requested_toners = {
            "black": self.color == "black",
            "cyan": self.color == "cyan",
            "magenta": self.color == "magenta",
            "yellow": self.color == "yellow",
        }

        Submission = self.env[
            "toner.counter.submission"
        ].sudo()

        validation = Submission.validate_web_toner_request(
            equipment_id=self.equipment_id.id,
            requested_toners=requested_toners,
            current_counters={
                "bn": int(self.counter_bn or 0),
                "color": int(self.counter_color or 0),
            },
        )

        if not validation.get("can_create"):
            duplicate_id = (
                validation.get(
                    "duplicate_submission_id"
                )
                or validation.get("duplicate_id")
            )

            duplicate = (
                Submission.browse(
                    duplicate_id
                ).exists()
                if duplicate_id
                else False
            )

            prefix = (
                (final_message_prefix + " ")
                if final_message_prefix
                else ""
            )

            if duplicate:
                self.write(
                    {
                        "submission_id": duplicate.id,
                        "duplicate_submission_id": duplicate.id,
                        "submission_created": False,
                    }
                )

                self._mark_processed(
                    prefix
                    + (
                        validation.get("message")
                        or _(
                            "Solicitud activa encontrada."
                        )
                    )
                )
                return True

            self._mark_pending(
                prefix
                + (
                    validation.get("message")
                    or _(
                        "La solicitud no pudo ser creada."
                    )
                )
            )
            return False

        color_results = validation.get(
            "colors",
            [],
        )

        first_with_history = next(
            (
                item
                for item in color_results
                if item.get("base_counter")
                is not None
            ),
            {},
        )

        most_restrictive = next(
            (
                item
                for item in color_results
                if item.get("status")
                == "early_consumption"
            ),
            (
                color_results[0]
                if color_results
                else {}
            ),
        )

        no_history = any(
            item.get("status") == "no_history"
            for item in color_results
        )

        review_required = bool(
            validation.get("review_required")
            or validation.get(
                "requires_evidence"
            )
        )

        vals = {
            "equipment_id": self.equipment_id.id,
            "source": "api",
            "client_name": _(
                "Monitoreo automático - %s"
            )
            % self._get_source_label(),
            "client_email": (
                self.env.company.email
                or "soporte@andescopiers.com.pe"
            ),
            "client_phone": "",
            "counter_bn": int(
                self.counter_bn
                or 0
            ),
            "counter_color": int(
                self.counter_color
                or 0
            ),
            "requiere_toner_black": (
                self.color == "black"
            ),
            "requiere_toner_cyan": (
                self.color == "cyan"
            ),
            "requiere_toner_magenta": (
                self.color == "magenta"
            ),
            "requiere_toner_yellow": (
                self.color == "yellow"
            ),
            "cantidad_solicitada_black": (
                1
                if self.color == "black"
                else 0
            ),
            "cantidad_solicitada_cyan": (
                1
                if self.color == "cyan"
                else 0
            ),
            "cantidad_solicitada_magenta": (
                1
                if self.color == "magenta"
                else 0
            ),
            "cantidad_solicitada_yellow": (
                1
                if self.color == "yellow"
                else 0
            ),
            "analysis_result": (
                "early_consumption"
                if review_required
                else (
                    "no_history"
                    if no_history
                    else "normal"
                )
            ),
            "analysis_summary": "\n".join(
                item.get("message", "")
                for item in color_results
                if item.get("message")
            ),
            "analysis_json": json.dumps(
                validation,
                ensure_ascii=False,
                default=str,
                indent=2,
            ),
            "requires_evidence": bool(
                validation.get(
                    "requires_evidence"
                )
            ),
            "last_delivery_date": (
                most_restrictive.get(
                    "last_delivery_date"
                )
                or first_with_history.get(
                    "last_delivery_date"
                )
            ),
            "days_since_last_delivery": int(
                most_restrictive.get(
                    "days_since_last_delivery",
                    0,
                )
                or 0
            ),
            "expected_yield": int(
                most_restrictive.get(
                    "expected_yield",
                    0,
                )
                or 0
            ),
            "consumed_copies": int(
                most_restrictive.get(
                    "consumed_copies",
                    0,
                )
                or 0
            ),
            "consumption_percent": float(
                most_restrictive.get(
                    "consumption_percent",
                    0.0,
                )
                or 0.0
            ),
            "notes": self._build_submission_notes(),
            "state": "recibida",
        }

        submission = Submission.create(
            vals
        )

        self.write(
            {
                "submission_id": submission.id,
                "submission_created": True,
            }
        )

        prefix = (
            (final_message_prefix + " ")
            if final_message_prefix
            else ""
        )

        self._mark_processed(
            prefix
            + _(
                "Solicitud %(sequence)s creada automáticamente "
                "por evento %(event)s de %(source)s."
            )
            % {
                "sequence": (
                    submission.secuencia
                    or submission.display_name
                ),
                "event": self._get_event_label(),
                "source": self._get_source_label(),
            }
        )

        self._post_equipment_chatter(
            _(
                "<b>Solicitud automática de tóner creada</b><br/>"
                "<b>Evento:</b> %(event)s<br/>"
                "<b>Color:</b> %(color)s<br/>"
                "<b>Origen:</b> %(source)s<br/>"
                "<b>Solicitud:</b> %(sequence)s"
            )
            % {
                "event": self._get_event_label(),
                "color": self._get_color_label(),
                "source": self._get_source_label(),
                "sequence": (
                    submission.secuencia
                    or submission.display_name
                ),
            }
        )

        _logger.info(
            "[TONER EVENT] Solicitud automática creada "
            "event=%s submission=%s equipment=%s color=%s",
            self.id,
            submission.id,
            self.equipment_id.id,
            self.color,
        )

        return True

    # ============================================================
    # SOLICITUD ABIERTA
    # ============================================================

    def _find_open_submission(self):
        self.ensure_one()

        if self.color == "unknown":
            return False

        color_field = {
            "black": "requiere_toner_black",
            "cyan": "requiere_toner_cyan",
            "magenta": "requiere_toner_magenta",
            "yellow": "requiere_toner_yellow",
        }.get(self.color)

        quantity_field = {
            "black": "cantidad_solicitada_black",
            "cyan": "cantidad_solicitada_cyan",
            "magenta": "cantidad_solicitada_magenta",
            "yellow": "cantidad_solicitada_yellow",
        }.get(self.color)

        if not color_field or not quantity_field:
            return False

        Submission = self.env[
            "toner.counter.submission"
        ].sudo()

        open_states = getattr(
            Submission,
            "OPEN_STATES",
            [
                "recibida",
                "evaluacion",
                "pendiente_gerencia",
                "aprobada_gerencia",
                "confirmacion_ventas",
                "lista_despacho",
                "en_despacho",
            ],
        )

        return Submission.search(
            [
                ("equipment_id", "=", self.equipment_id.id),
                ("state", "in", open_states),
                "|",
                (color_field, "=", True),
                (quantity_field, ">", 0),
            ],
            order="submission_date desc, id desc",
            limit=1,
        )

    # ============================================================
    # ESTADOS DEL EVENTO
    # ============================================================

    def _mark_processed(self, message):
        self.ensure_one()

        self.write(
            {
                "processing_state": "processed",
                "processed_date": fields.Datetime.now(),
                "processing_message": message,
                "processing_error": False,
            }
        )

    def _mark_pending(self, message):
        self.ensure_one()

        self.write(
            {
                "processing_state": "pending_data",
                "processing_message": message,
                "processing_error": False,
            }
        )

    # ============================================================
    # NOTAS
    # ============================================================

    def _build_submission_notes(self):
        self.ensure_one()

        parts = [
            _(
                "Solicitud generada automáticamente "
                "por monitoreo."
            ),
            _("Origen: %s")
            % self._get_source_label(),
            _("Evento: %s")
            % self._get_event_label(),
            _("Color: %s")
            % self._get_color_label(),
        ]

        if self.external_event_id:
            parts.append(
                _("ID externo: %s")
                % self.external_event_id
            )

        if self.supply_key:
            parts.append(
                _("Supply Key: %s")
                % self.supply_key
            )

        if self.level_percent is not False:
            parts.append(
                _("Nivel informado: %.2f%%")
                % self.level_percent
            )

        if self.raw_description:
            parts.append(
                _("Descripción: %s")
                % self.raw_description
            )

        return "\n".join(parts)

    # ============================================================
    # CHATTER
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
                "[TONER EVENT] No se pudo escribir en chatter "
                "equipment=%s event=%s",
                self.equipment_id.id,
                self.id,
            )
            return False

    # ============================================================
    # ETIQUETAS
    # ============================================================

    def _get_color_label(self):
        self.ensure_one()

        return dict(
            self.COLOR_SELECTION
        ).get(
            self.color,
            self.color or _("No identificado"),
        )

    def _get_event_label(self):
        self.ensure_one()

        return dict(
            self.EVENT_TYPE_SELECTION
        ).get(
            self.event_type,
            self.event_type or _("Evento"),
        )

    def _get_source_label(self):
        self.ensure_one()

        return dict(
            self.SOURCE_SELECTION
        ).get(
            self.source,
            self.source or _("Otro"),
        )

    # ============================================================
    # ACCIONES MANUALES
    # ============================================================

    def action_retry_processing(self):
        """
        Reprocesa un evento pendiente/error.

        La idempotencia de:
            - external_event_id
            - start_event_id
            - external_key de stock
        evita duplicar solicitudes/ciclos/movimientos.
        """
        for event in self:
            event.write(
                {
                    "processing_state": "new",
                    "processing_error": False,
                    "processing_message": False,
                }
            )

        return self.action_process_event()

    def action_ignore(self):
        for event in self:
            event.write(
                {
                    "processing_state": "ignored",
                    "processed_date": fields.Datetime.now(),
                    "processing_message": _(
                        "Evento ignorado manualmente por %s."
                    )
                    % self.env.user.name,
                    "processing_error": False,
                }
            )

        return True

    def action_view_submission(self):
        self.ensure_one()

        if not self.submission_id:
            raise ValidationError(
                _("El evento no tiene una solicitud relacionada.")
            )

        return {
            "name": _("Solicitud de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.counter.submission",
            "view_mode": "form",
            "res_id": self.submission_id.id,
            "target": "current",
        }

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

    def action_view_installation_history(self):
        self.ensure_one()

        if not self.installation_history_id:
            raise ValidationError(
                _(
                    "El evento no tiene un ciclo "
                    "de tóner relacionado."
                )
            )

        return {
            "name": _("Historial de instalación"),
            "type": "ir.actions.act_window",
            "res_model": "toner.installation.history",
            "view_mode": "form",
            "res_id": self.installation_history_id.id,
            "target": "current",
        }

    def action_view_stock_movement(self):
        self.ensure_one()

        if not self.stock_movement_id:
            raise ValidationError(
                _(
                    "El evento no tiene un movimiento "
                    "de stock relacionado."
                )
            )

        return {
            "name": _("Movimiento de stock"),
            "type": "ir.actions.act_window",
            "res_model": "toner.stock.movement",
            "view_mode": "form",
            "res_id": self.stock_movement_id.id,
            "target": "current",
        }
