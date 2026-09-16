# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class UnidadAlquiler(models.Model):
    """
    Integración de gestión de tóner sobre alquiler.

    FUENTES DE VERDAD
    =================

    1. toner.monitoring.event
       Eventos externos / monitoreo.

    2. toner.installation.history
       Ciclos físicos de cartuchos instalados.

    3. toner.stock.movement
       Kardex del stock de respaldo que permanece con el cliente.

    4. toner.counter.submission
       Solicitud / aprobación / despacho.

    Los campos históricos antiguos de alquiler se conservan por
    compatibilidad con vistas y código existente, pero ahora se calculan
    a partir de los modelos históricos. Ya no son la fuente de verdad.
    """

    _inherit = "alquiler"

    # ============================================================
    # ESTADO GENERAL
    # ============================================================

    estado_stock_toner = fields.Selection(
        [
            ("critico", "Crítico"),
            ("bajo", "Bajo"),
            ("normal", "Normal"),
            ("alto", "Alto"),
        ],
        string="Estado Stock Tóner",
        compute="_compute_toner_dashboard_fields",
        store=False,
        help=(
            "Estado calculado desde el stock histórico del cliente "
            "registrado en toner.stock.movement."
        ),
    )

    # ============================================================
    # STOCK CLIENTE - COMPATIBILIDAD
    # ============================================================
    #
    # Estos campos existían antes como enteros editables.
    # Se mantienen con los mismos nombres para no romper vistas,
    # pero ahora se derivan del kardex.
    # ============================================================

    stock_cliente_toner_black = fields.Integer(
        string="Stock Cliente - Tóner Negro",
        compute="_compute_toner_dashboard_fields",
        store=False,
        help="Stock de respaldo negro calculado desde el kardex.",
    )

    stock_cliente_toner_cyan = fields.Integer(
        string="Stock Cliente - Tóner Cian",
        compute="_compute_toner_dashboard_fields",
        store=False,
        help="Stock de respaldo cian calculado desde el kardex.",
    )

    stock_cliente_toner_magenta = fields.Integer(
        string="Stock Cliente - Tóner Magenta",
        compute="_compute_toner_dashboard_fields",
        store=False,
        help="Stock de respaldo magenta calculado desde el kardex.",
    )

    stock_cliente_toner_yellow = fields.Integer(
        string="Stock Cliente - Tóner Amarillo",
        compute="_compute_toner_dashboard_fields",
        store=False,
        help="Stock de respaldo amarillo calculado desde el kardex.",
    )

    # ============================================================
    # CARTUCHO INSTALADO - COMPATIBILIDAD
    # ============================================================

    toner_black_instalado = fields.Boolean(
        string="Tóner Negro Instalado",
        compute="_compute_toner_cycle_compatibility",
        store=False,
    )

    toner_cyan_instalado = fields.Boolean(
        string="Tóner Cian Instalado",
        compute="_compute_toner_cycle_compatibility",
        store=False,
    )

    toner_magenta_instalado = fields.Boolean(
        string="Tóner Magenta Instalado",
        compute="_compute_toner_cycle_compatibility",
        store=False,
    )

    toner_yellow_instalado = fields.Boolean(
        string="Tóner Amarillo Instalado",
        compute="_compute_toner_cycle_compatibility",
        store=False,
    )

    # ============================================================
    # FECHAS DE INSTALACIÓN - COMPATIBILIDAD
    # ============================================================

    fecha_instalacion_toner_black = fields.Date(
        string="Fecha Instalación Tóner Negro",
        compute="_compute_toner_cycle_compatibility",
        store=False,
    )

    fecha_instalacion_toner_cyan = fields.Date(
        string="Fecha Instalación Tóner Cian",
        compute="_compute_toner_cycle_compatibility",
        store=False,
    )

    fecha_instalacion_toner_magenta = fields.Date(
        string="Fecha Instalación Tóner Magenta",
        compute="_compute_toner_cycle_compatibility",
        store=False,
    )

    fecha_instalacion_toner_yellow = fields.Date(
        string="Fecha Instalación Tóner Amarillo",
        compute="_compute_toner_cycle_compatibility",
        store=False,
    )

    # ============================================================
    # CONTADORES DE INSTALACIÓN - COMPATIBILIDAD
    # ============================================================

    contador_instalacion_toner_black = fields.Integer(
        string="Contador al Instalar Tóner Negro",
        compute="_compute_toner_cycle_compatibility",
        store=False,
    )

    contador_instalacion_toner_cyan = fields.Integer(
        string="Contador al Instalar Tóner Cian",
        compute="_compute_toner_cycle_compatibility",
        store=False,
    )

    contador_instalacion_toner_magenta = fields.Integer(
        string="Contador al Instalar Tóner Magenta",
        compute="_compute_toner_cycle_compatibility",
        store=False,
    )

    contador_instalacion_toner_yellow = fields.Integer(
        string="Contador al Instalar Tóner Amarillo",
        compute="_compute_toner_cycle_compatibility",
        store=False,
    )

    # ============================================================
    # CONTADORES ACTUALES - COMPATIBILIDAD
    # ============================================================

    contador_actual_black = fields.Integer(
        string="Contador Actual B/N",
        compute="_compute_current_counter_compatibility",
        store=False,
    )

    contador_actual_color = fields.Integer(
        string="Contador Actual Color",
        compute="_compute_current_counter_compatibility",
        store=False,
    )

    fecha_ultima_lectura = fields.Datetime(
        string="Fecha Última Lectura",
        compute="_compute_current_counter_compatibility",
        store=False,
    )

    # ============================================================
    # RENDIMIENTO DEL CICLO ACTUAL
    # ============================================================

    paginas_usadas_toner_black = fields.Integer(
        string="Páginas Usadas Tóner Negro",
        compute="_compute_toner_usage",
        store=False,
    )

    paginas_usadas_toner_cyan = fields.Integer(
        string="Páginas Usadas Tóner Cian",
        compute="_compute_toner_usage",
        store=False,
    )

    paginas_usadas_toner_magenta = fields.Integer(
        string="Páginas Usadas Tóner Magenta",
        compute="_compute_toner_usage",
        store=False,
    )

    paginas_usadas_toner_yellow = fields.Integer(
        string="Páginas Usadas Tóner Amarillo",
        compute="_compute_toner_usage",
        store=False,
    )

    paginas_restantes_toner_black = fields.Integer(
        string="Páginas Restantes Tóner Negro",
        compute="_compute_toner_usage",
        store=False,
    )

    paginas_restantes_toner_cyan = fields.Integer(
        string="Páginas Restantes Tóner Cian",
        compute="_compute_toner_usage",
        store=False,
    )

    paginas_restantes_toner_magenta = fields.Integer(
        string="Páginas Restantes Tóner Magenta",
        compute="_compute_toner_usage",
        store=False,
    )

    paginas_restantes_toner_yellow = fields.Integer(
        string="Páginas Restantes Tóner Amarillo",
        compute="_compute_toner_usage",
        store=False,
    )

    # ============================================================
    # NIVEL DE TÓNER
    # ============================================================

    nivel_toner_black = fields.Float(
        string="Nivel Tóner Negro (%)",
        compute="_compute_toner_levels",
        store=False,
    )

    nivel_toner_cyan = fields.Float(
        string="Nivel Tóner Cian (%)",
        compute="_compute_toner_levels",
        store=False,
    )

    nivel_toner_magenta = fields.Float(
        string="Nivel Tóner Magenta (%)",
        compute="_compute_toner_levels",
        store=False,
    )

    nivel_toner_yellow = fields.Float(
        string="Nivel Tóner Amarillo (%)",
        compute="_compute_toner_levels",
        store=False,
    )

    # ============================================================
    # TOTAL FÍSICO
    # ============================================================
    #
    # TOTAL FÍSICO = cartucho instalado + repuestos en stock.
    #
    # El stock del cliente por sí solo sigue siendo únicamente el
    # repuesto almacenado.
    # ============================================================

    stock_total_toner_black = fields.Integer(
        string="Stock Total Tóner Negro",
        compute="_compute_toner_dashboard_fields",
        store=False,
    )

    stock_total_toner_cyan = fields.Integer(
        string="Stock Total Tóner Cian",
        compute="_compute_toner_dashboard_fields",
        store=False,
    )

    stock_total_toner_magenta = fields.Integer(
        string="Stock Total Tóner Magenta",
        compute="_compute_toner_dashboard_fields",
        store=False,
    )

    stock_total_toner_yellow = fields.Integer(
        string="Stock Total Tóner Amarillo",
        compute="_compute_toner_dashboard_fields",
        store=False,
    )

    # ============================================================
    # CONTADORES SMART BUTTON
    # ============================================================

    toner_reports_count = fields.Integer(
        string="Solicitudes de Tóner",
        compute="_compute_toner_counts",
    )

    toner_deliveries_count = fields.Integer(
        string="Entregas de Tóner",
        compute="_compute_toner_counts",
    )

    toner_monitoring_events_count = fields.Integer(
        string="Eventos de Tóner",
        compute="_compute_toner_counts",
    )

    toner_installation_history_count = fields.Integer(
        string="Historial de Tóner",
        compute="_compute_toner_counts",
    )

    toner_stock_movements_count = fields.Integer(
        string="Movimientos de Stock",
        compute="_compute_toner_counts",
    )

    toner_stock_discrepancy_count = fields.Integer(
        string="Discrepancias de Stock",
        compute="_compute_toner_counts",
    )

    # ============================================================
    # HELPERS GENERALES
    # ============================================================

    @api.model
    def _toner_colors(self):
        return (
            "black",
            "cyan",
            "magenta",
            "yellow",
        )

    def _get_current_counter(self, color):
        """
        Obtiene el contador actual del equipo sin depender de los campos
        legacy de esta extensión.

        Negro:
            contador_bn si existe.

        C/M/Y:
            contador_color si existe.

        Como respaldo usa la última observación toner.monitoring.event.
        """
        self.ensure_one()

        field_name = (
            "contador_bn"
            if color == "black"
            else "contador_color"
        )

        if field_name in self._fields:
            value = int(
                getattr(
                    self,
                    field_name,
                    0,
                )
                or 0
            )

            if value > 0:
                return value

        event = self.env[
            "toner.monitoring.event"
        ].sudo().search(
            [
                ("equipment_id", "=", self.id),
                ("color", "=", color),
                (
                    "counter_bn"
                    if color == "black"
                    else "counter_color",
                    ">",
                    0,
                ),
            ],
            order="event_date desc, id desc",
            limit=1,
        )

        if event:
            return int(
                event.counter_bn
                if color == "black"
                else event.counter_color
            )

        return 0

    def _get_active_toner_cycle(self, color):
        self.ensure_one()

        return self.env[
            "toner.installation.history"
        ].sudo().get_active_cycle(
            self,
            color,
        )

    def _get_latest_toner_level_event(self, color):
        self.ensure_one()

        return self.env[
            "toner.monitoring.event"
        ].sudo().search(
            [
                ("equipment_id", "=", self.id),
                ("color", "=", color),
                ("level_percent", ">=", 0),
                (
                    "event_type",
                    "in",
                    [
                        "level",
                        "normal",
                        "low",
                        "critical",
                        "empty",
                        "replaced",
                    ],
                ),
            ],
            order="event_date desc, id desc",
            limit=1,
        )

    def _get_toner_min_stock(self, color):
        """
        Stock mínimo se interpreta como stock de respaldo esperado
        en el cliente, no como cartucho instalado.
        """
        self.ensure_one()

        if not self.name:
            return 1

        field_name = "stock_minimo_%s" % color

        if field_name in self.name._fields:
            return max(
                0,
                int(
                    getattr(
                        self.name,
                        field_name,
                        0,
                    )
                    or 0
                ),
            )

        return 1

    # ============================================================
    # COMPATIBILIDAD: CICLO ACTUAL
    # ============================================================

    def _compute_toner_cycle_compatibility(self):
        for record in self:
            cycles = {
                color: record._get_active_toner_cycle(
                    color
                )
                for color in record._toner_colors()
            }

            for color in record._toner_colors():
                cycle = cycles[color]

                setattr(
                    record,
                    "toner_%s_instalado" % color,
                    bool(cycle),
                )

                setattr(
                    record,
                    "fecha_instalacion_toner_%s" % color,
                    (
                        fields.Date.to_date(
                            cycle.start_date
                        )
                        if cycle
                        and cycle.start_date
                        else False
                    ),
                )

                setattr(
                    record,
                    "contador_instalacion_toner_%s" % color,
                    (
                        int(
                            cycle.start_counter
                            or 0
                        )
                        if cycle
                        else 0
                    ),
                )

    # ============================================================
    # COMPATIBILIDAD: CONTADORES
    # ============================================================

    def _compute_current_counter_compatibility(self):
        Event = self.env[
            "toner.monitoring.event"
        ].sudo()

        for record in self:
            record.contador_actual_black = (
                record._get_current_counter(
                    "black"
                )
            )

            color_values = [
                record._get_current_counter(
                    color
                )
                for color in (
                    "cyan",
                    "magenta",
                    "yellow",
                )
            ]

            record.contador_actual_color = max(
                color_values
                or [0]
            )

            last_event = Event.search(
                [
                    ("equipment_id", "=", record.id),
                    "|",
                    ("counter_bn", ">", 0),
                    ("counter_color", ">", 0),
                ],
                order="event_date desc, id desc",
                limit=1,
            )

            if last_event:
                record.fecha_ultima_lectura = (
                    last_event.event_date
                )
            elif (
                "fecha_ultima_actualizacion"
                in record._fields
            ):
                record.fecha_ultima_lectura = (
                    record.fecha_ultima_actualizacion
                )
            else:
                record.fecha_ultima_lectura = False

    # ============================================================
    # RENDIMIENTO DEL CICLO ACTIVO
    # ============================================================

    def _compute_toner_usage(self):
        for record in self:
            for color in record._toner_colors():
                cycle = record._get_active_toner_cycle(
                    color
                )

                used = 0
                remaining = 0

                if cycle:
                    current = (
                        record._get_current_counter(
                            color
                        )
                    )

                    start = int(
                        cycle.start_counter
                        or 0
                    )

                    if (
                        current > 0
                        and current >= start
                    ):
                        used = current - start

                    expected = int(
                        cycle.expected_yield
                        or 0
                    )

                    if expected <= 0:
                        expected = int(
                            self.env[
                                "toner.installation.history"
                            ].sudo()._get_expected_yield_for_equipment(
                                record,
                                color,
                            )
                            or 0
                        )

                    remaining = max(
                        0,
                        expected - used,
                    )

                setattr(
                    record,
                    "paginas_usadas_toner_%s" % color,
                    used,
                )

                setattr(
                    record,
                    "paginas_restantes_toner_%s" % color,
                    remaining,
                )

    # ============================================================
    # NIVEL DE TÓNER
    # ============================================================

    def _compute_toner_levels(self):
        for record in self:
            for color in record._toner_colors():
                event = (
                    record._get_latest_toner_level_event(
                        color
                    )
                )

                level = False

                if event:
                    level = float(
                        event.level_percent
                        or 0.0
                    )

                # Si no hay lectura de nivel, estimar desde rendimiento
                # del ciclo únicamente para visualización.
                if not event:
                    cycle = (
                        record._get_active_toner_cycle(
                            color
                        )
                    )

                    if cycle:
                        expected = int(
                            cycle.expected_yield
                            or 0
                        )

                        if expected > 0:
                            current = (
                                record._get_current_counter(
                                    color
                                )
                            )

                            used = max(
                                0,
                                current
                                - int(
                                    cycle.start_counter
                                    or 0
                                ),
                            )

                            level = max(
                                0.0,
                                min(
                                    100.0,
                                    (
                                        (
                                            expected
                                            - used
                                        )
                                        / expected
                                    )
                                    * 100.0,
                                ),
                            )

                setattr(
                    record,
                    "nivel_toner_%s" % color,
                    float(
                        level
                        if level is not False
                        else 0.0
                    ),
                )

    # ============================================================
    # STOCK Y ESTADO GENERAL
    # ============================================================

    def _compute_toner_dashboard_fields(self):
        Stock = self.env[
            "toner.stock.movement"
        ].sudo()

        History = self.env[
            "toner.installation.history"
        ].sudo()

        for record in self:
            stock = Stock.get_stock_summary(
                record
            )

            active = {
                color: bool(
                    History.get_active_cycle(
                        record,
                        color,
                    )
                )
                for color in record._toner_colors()
            }

            for color in record._toner_colors():
                client_stock = int(
                    stock.get(
                        color,
                        0,
                    )
                    or 0
                )

                setattr(
                    record,
                    "stock_cliente_toner_%s" % color,
                    client_stock,
                )

                setattr(
                    record,
                    "stock_total_toner_%s" % color,
                    client_stock
                    + (
                        1
                        if active[color]
                        else 0
                    ),
                )

            colors_to_evaluate = ["black"]

            if record.tipo_maquina_id == "color":
                colors_to_evaluate = [
                    "black",
                    "cyan",
                    "magenta",
                    "yellow",
                ]

            states = []

            for color in colors_to_evaluate:
                client_stock = int(
                    stock.get(
                        color,
                        0,
                    )
                    or 0
                )

                minimum = record._get_toner_min_stock(
                    color
                )

                # El estado se calcula sobre REPUESTOS DEL CLIENTE.
                # El cartucho instalado no cuenta como stock de respaldo.
                if client_stock <= 0:
                    states.append("critico")
                elif client_stock < minimum:
                    states.append("bajo")
                elif (
                    minimum > 0
                    and client_stock > minimum * 2
                ):
                    states.append("alto")
                else:
                    states.append("normal")

            if "critico" in states:
                record.estado_stock_toner = "critico"
            elif "bajo" in states:
                record.estado_stock_toner = "bajo"
            elif (
                states
                and all(
                    state == "alto"
                    for state in states
                )
            ):
                record.estado_stock_toner = "alto"
            else:
                record.estado_stock_toner = "normal"

    # ============================================================
    # SMART BUTTON COUNTS
    # ============================================================

    def _compute_toner_counts(self):
        Submission = self.env[
            "toner.counter.submission"
        ].sudo()

        Delivery = self.env[
            "toner.delivery.schedule"
        ].sudo()

        Event = self.env[
            "toner.monitoring.event"
        ].sudo()

        History = self.env[
            "toner.installation.history"
        ].sudo()

        Movement = self.env[
            "toner.stock.movement"
        ].sudo()

        for record in self:
            record.toner_reports_count = (
                Submission.search_count(
                    [
                        (
                            "equipment_id",
                            "=",
                            record.id,
                        )
                    ]
                )
            )

            record.toner_deliveries_count = (
                Delivery.search_count(
                    [
                        (
                            "equipment_id",
                            "=",
                            record.id,
                        )
                    ]
                )
            )

            record.toner_monitoring_events_count = (
                Event.search_count(
                    [
                        (
                            "equipment_id",
                            "=",
                            record.id,
                        )
                    ]
                )
            )

            record.toner_installation_history_count = (
                History.search_count(
                    [
                        (
                            "equipment_id",
                            "=",
                            record.id,
                        )
                    ]
                )
            )

            record.toner_stock_movements_count = (
                Movement.search_count(
                    [
                        (
                            "equipment_id",
                            "=",
                            record.id,
                        )
                    ]
                )
            )

            record.toner_stock_discrepancy_count = (
                Movement.search_count(
                    [
                        (
                            "equipment_id",
                            "=",
                            record.id,
                        ),
                        (
                            "stock_discrepancy",
                            "=",
                            True,
                        ),
                        (
                            "state",
                            "=",
                            "posted",
                        ),
                    ]
                )
            )

    # ============================================================
    # ACCIONES SMART BUTTON
    # ============================================================

    def action_view_toner_reports(self):
        self.ensure_one()

        return {
            "name": _("Solicitudes de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.counter.submission",
            "view_mode": "list,form",
            "domain": [
                (
                    "equipment_id",
                    "=",
                    self.id,
                )
            ],
            "context": {
                "default_equipment_id": self.id,
            },
            "target": "current",
        }

    def action_view_toner_deliveries(self):
        self.ensure_one()

        return {
            "name": _("Entregas de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.delivery.schedule",
            "view_mode": "list,form",
            "domain": [
                (
                    "equipment_id",
                    "=",
                    self.id,
                )
            ],
            "context": {
                "default_equipment_id": self.id,
            },
            "target": "current",
        }

    def action_view_toner_monitoring_events(self):
        self.ensure_one()

        return {
            "name": _("Eventos de monitoreo de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.monitoring.event",
            "view_mode": "list,form",
            "domain": [
                (
                    "equipment_id",
                    "=",
                    self.id,
                )
            ],
            "context": {
                "default_equipment_id": self.id,
            },
            "target": "current",
        }

    def action_view_toner_installation_history(self):
        self.ensure_one()

        return {
            "name": _("Historial de instalación de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.installation.history",
            "view_mode": "list,form",
            "domain": [
                (
                    "equipment_id",
                    "=",
                    self.id,
                )
            ],
            "context": {
                "default_equipment_id": self.id,
            },
            "target": "current",
        }

    def action_view_toner_stock_movements(self):
        self.ensure_one()

        return {
            "name": _("Kardex de stock de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.stock.movement",
            "view_mode": "list,form",
            "domain": [
                (
                    "equipment_id",
                    "=",
                    self.id,
                )
            ],
            "context": {
                "default_equipment_id": self.id,
            },
            "target": "current",
        }

    def action_view_toner_stock_discrepancies(self):
        self.ensure_one()

        return {
            "name": _("Discrepancias de stock de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.stock.movement",
            "view_mode": "list,form",
            "domain": [
                (
                    "equipment_id",
                    "=",
                    self.id,
                ),
                (
                    "stock_discrepancy",
                    "=",
                    True,
                ),
            ],
            "target": "current",
        }

    # ============================================================
    # CONFIGURACIÓN DEL MODELO
    # ============================================================

    def action_view_model_toner_config(self):
        self.ensure_one()

        if not self.name:
            raise UserError(
                _("Este equipo no tiene un modelo asignado.")
            )

        return {
            "name": _(
                "Configuración Tóner - %s"
            )
            % self.name.name,
            "type": "ir.actions.act_window",
            "res_model": "modelo.maquina",
            "res_id": self.name.id,
            "view_mode": "form",
            "target": "current",
        }

    # ============================================================
    # CREACIÓN MANUAL DE SOLICITUD
    # ============================================================

    def action_create_manual_delivery(self):
        """
        Compatibilidad con el botón antiguo.

        Ya NO crea toner.delivery.schedule.

        Abre una nueva toner.counter.submission para que siga el flujo:
            evaluación -> gerencia -> ventas -> despacho.
        """
        self.ensure_one()

        return {
            "name": _("Nueva solicitud de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.counter.submission",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_equipment_id": self.id,
                "default_source": "manual",
            },
        }

    # ============================================================
    # AJUSTE DE STOCK
    # ============================================================

    def action_update_toner_stock(self):
        """
        Ya no se permite escribir stock_cliente_toner_* directamente.

        Mientras no exista wizard dedicado, abre el kardex para que
        los ajustes se registren mediante toner.stock.movement.
        """
        self.ensure_one()

        return self.action_view_toner_stock_movements()

    # ============================================================
    # INSTALACIÓN MANUAL
    # ============================================================

    def action_install_new_toner(self):
        """
        No escribimos fecha/contador en alquiler.

        Abrimos el historial para registrar un nuevo ciclo físico.
        """
        self.ensure_one()

        return {
            "name": _("Registrar instalación de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.installation.history",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_equipment_id": self.id,
                "default_state": "active",
                "default_start_source": "manual",
                "default_start_date": fields.Datetime.now(),
            },
        }

    # ============================================================
    # RECORDATORIO
    # ============================================================

    def action_send_stock_reminder(self):
        """
        Conserva el comportamiento anterior sin fingir que envió email.
        Solo registra el recordatorio en chatter.
        """
        self.ensure_one()

        if not self.cliente_id:
            raise UserError(
                _("No hay cliente asignado a este equipo.")
            )

        email = (
            self.correo_
            if "correo_" in self._fields
            else False
        )

        if not email:
            raise UserError(
                _("No hay email configurado para este equipo.")
            )

        self.message_post(
            body=_(
                "📧 Recordatorio de stock registrado para %s."
            )
            % email,
            message_type="notification",
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Recordatorio registrado"),
                "message": _(
                    "Recordatorio de stock registrado para %s."
                )
                % email,
                "type": "success",
                "sticky": False,
            },
        }

    # ============================================================
    # PREVENCIÓN
    # ============================================================

    def _calcular_dias_restantes_toner(self):
        """
        Estimación conservadora para el tóner negro activo.

        Se utiliza solamente como apoyo preventivo. Nunca crea despacho.

        Se calcula usando:
            - ciclo activo;
            - contador actual;
            - rendimiento esperado;
            - consumo promedio de solicitudes históricas cuando existe.
        """
        self.ensure_one()

        cycle = self._get_active_toner_cycle(
            "black"
        )

        if not cycle:
            return 0

        current = self._get_current_counter(
            "black"
        )

        start = int(
            cycle.start_counter
            or 0
        )

        expected = int(
            cycle.expected_yield
            or 0
        )

        if expected <= 0:
            expected = int(
                self.env[
                    "toner.installation.history"
                ].sudo()._get_expected_yield_for_equipment(
                    self,
                    "black",
                )
                or 0
            )

        if expected <= 0:
            return 30

        used = max(
            0,
            current - start,
        )

        remaining = max(
            0,
            expected - used,
        )

        if remaining <= 0:
            return 0

        submissions = self.env[
            "toner.counter.submission"
        ].sudo().search(
            [
                ("equipment_id", "=", self.id),
                (
                    "state",
                    "in",
                    [
                        "entregada",
                        "en_despacho",
                        "lista_despacho",
                        "confirmacion_ventas",
                        "aprobada_gerencia",
                    ],
                ),
                ("counter_bn", ">", 0),
            ],
            order="submission_date desc, id desc",
            limit=5,
        )

        if len(submissions) < 2:
            delivery_days = (
                int(
                    getattr(
                        self.name,
                        "tiempo_entrega_dias",
                        0,
                    )
                    or 0
                )
                if self.name
                else 0
            )

            safety_days = (
                int(
                    getattr(
                        self.name,
                        "margen_seguridad_dias",
                        0,
                    )
                    or 0
                )
                if self.name
                else 0
            )

            return max(
                1,
                delivery_days
                + safety_days
                or 7,
            )

        total_days = 0
        total_copies = 0

        ordered = submissions.sorted(
            key=lambda record: (
                record.submission_date
                or fields.Datetime.now()
            ),
            reverse=True,
        )

        for index in range(
            len(ordered) - 1
        ):
            newer = ordered[index]
            older = ordered[index + 1]

            if (
                not newer.submission_date
                or not older.submission_date
            ):
                continue

            days = (
                fields.Datetime.to_datetime(
                    newer.submission_date
                )
                - fields.Datetime.to_datetime(
                    older.submission_date
                )
            ).days

            copies = (
                int(
                    newer.counter_bn
                    or 0
                )
                - int(
                    older.counter_bn
                    or 0
                )
            )

            if days > 0 and copies > 0:
                total_days += days
                total_copies += copies

        if (
            total_days <= 0
            or total_copies <= 0
        ):
            return 30

        daily_average = (
            total_copies
            / total_days
        )

        if daily_average <= 0:
            return 30

        return max(
            0,
            int(
                remaining
                / daily_average
            ),
        )

    def _crear_alerta_toner_preventiva(self):
        """
        La lógica antigua creaba toner.delivery.schedule directamente.

        La nueva lógica genera un toner.monitoring.event LOW que, a su vez,
        crea/enlaza toner.counter.submission y respeta aprobación de gerencia.

        Devuelve True solamente si creó un nuevo evento preventivo.
        """
        self.ensure_one()

        if not self.name:
            return False

        days_remaining = (
            self._calcular_dias_restantes_toner()
        )

        critical_days = int(
            getattr(
                self.name,
                "tiempo_total_prevencion",
                0,
            )
            or 7
        )

        if days_remaining > critical_days:
            return False

        # Si ya existe solicitud negra abierta, no generar otro evento.
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

        existing_submission = (
            Submission.search(
                [
                    (
                        "equipment_id",
                        "=",
                        self.id,
                    ),
                    (
                        "state",
                        "in",
                        open_states,
                    ),
                    (
                        "requiere_toner_black",
                        "=",
                        True,
                    ),
                ],
                limit=1,
            )
        )

        if existing_submission:
            return False

        today_key = fields.Date.to_string(
            fields.Date.context_today(
                self
            )
        )

        external_event_id = (
            "preventive:%s:black:%s"
            % (
                self.id,
                today_key,
            )
        )

        Event = self.env[
            "toner.monitoring.event"
        ].sudo()

        existing_event = Event.search(
            [
                (
                    "source",
                    "=",
                    "manual",
                ),
                (
                    "external_event_id",
                    "=",
                    external_event_id,
                ),
            ],
            limit=1,
        )

        if existing_event:
            return False

        counter_bn = (
            self._get_current_counter(
                "black"
            )
        )

        event = (
            Event.create_normalized_event(
                {
                    "equipment_id": self.id,
                    "source": "manual",
                    "external_event_id": external_event_id,
                    "event_type": "low",
                    "color": "black",
                    "event_date": fields.Datetime.now(),
                    "counter_bn": counter_bn,
                    "raw_description": _(
                        "Alerta preventiva: se estiman "
                        "%s día(s) restantes."
                    )
                    % days_remaining,
                }
            )
        )

        self.message_post(
            body=_(
                "🔔 Alerta preventiva de tóner creada. "
                "Estimación: %s día(s) restantes. "
                "El evento fue enviado al flujo normal "
                "de solicitud y aprobación."
            )
            % days_remaining,
            message_type="notification",
        )

        return bool(event)

    @api.model
    def check_toner_alerts(self):
        """
        Cron preventivo.

        No crea entregas.
        Genera eventos normalizados que respetan el workflow oficial.
        """
        domain = [
            (
                "estado_alquiler_id",
                "=",
                "alquilada",
            )
        ]

        # Mantener compatibilidad si el modelo conserva el flag.
        if (
            "name" in self._fields
            and self.env["modelo.maquina"]._fields.get(
                "gestionar_toner_automatico"
            )
        ):
            domain.append(
                (
                    "name.gestionar_toner_automatico",
                    "=",
                    True,
                )
            )

        equipments = self.search(domain)

        created = 0

        for equipment in equipments:
            try:
                if (
                    equipment._crear_alerta_toner_preventiva()
                ):
                    created += 1
            except Exception:
                _logger.exception(
                    "[TONER] Error preventivo equipo=%s",
                    equipment.serie,
                )

        _logger.info(
            "[TONER] Alertas preventivas creadas: %s/%s",
            created,
            len(equipments),
        )

        return created

    # ============================================================
    # DASHBOARD
    # ============================================================

    @api.model
    def get_toner_dashboard_data(self):
        base_domain = [
            (
                "estado_alquiler_id",
                "=",
                "alquilada",
            )
        ]

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

        return {
            "equipos_criticos": self.search_count(
                base_domain
                + [
                    (
                        "estado_stock_toner",
                        "=",
                        "critico",
                    )
                ]
            ),
            "equipos_bajo_stock": self.search_count(
                base_domain
                + [
                    (
                        "estado_stock_toner",
                        "=",
                        "bajo",
                    )
                ]
            ),
            "entregas_pendientes": self.env[
                "toner.delivery.schedule"
            ].sudo().search_count(
                [
                    (
                        "state",
                        "in",
                        [
                            "programado",
                            "confirmado",
                            "preparando",
                            "enviado",
                        ],
                    )
                ]
            ),
            "solicitudes_pendientes": Submission.search_count(
                [
                    (
                        "state",
                        "in",
                        open_states,
                    )
                ]
            ),
            "eventos_pendientes": self.env[
                "toner.monitoring.event"
            ].sudo().search_count(
                [
                    (
                        "processing_state",
                        "in",
                        [
                            "new",
                            "pending_data",
                            "error",
                        ],
                    )
                ]
            ),
            "discrepancias_stock": self.env[
                "toner.stock.movement"
            ].sudo().search_count(
                [
                    (
                        "stock_discrepancy",
                        "=",
                        True,
                    ),
                    (
                        "state",
                        "=",
                        "posted",
                    ),
                ]
            ),
            "total_alquilados": self.search_count(
                base_domain
            ),
        }
