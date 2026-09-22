# -*- coding: utf-8 -*-

import json
import logging
import secrets
from datetime import timedelta

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class TonerCounterSubmission(models.Model):
    """
    Solicitud de tóner y evaluación interna.

    Flujo:
    recibida -> evaluacion -> pendiente_gerencia -> aprobada_gerencia
    -> confirmacion_ventas -> lista_despacho -> en_despacho -> entregada

    El cliente nunca aprueba ni autoriza el despacho desde el portal.
    """
    _name = "toner.counter.submission"
    _description = "Solicitud y evaluación de tóner"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "submission_date desc, id desc"
    _rec_name = "display_name"

    COLOR_LABELS = {
        "black": "Negro",
        "cyan": "Cian",
        "magenta": "Magenta",
        "yellow": "Amarillo",
    }

    OPEN_STATES = [
        "recibida",
        "evaluacion",
        "pendiente_gerencia",
        "aprobada_gerencia",
        "confirmacion_ventas",
        "lista_despacho",
        "en_despacho",
    ]

    # -------------------------------------------------------------------------
    # Identificación
    # -------------------------------------------------------------------------

    display_name = fields.Char(
        string="Nombre",
        compute="_compute_display_name",
        store=True,
    )

    equipment_serie = fields.Char(related="equipment_id.serie", string="Serie", readonly=True)
    history_snapshot_json = fields.Text(string="Referencia histórica por color", readonly=True, copy=False)
    toner_brand_black_id = fields.Many2one("toner.brand", string="Marca del tóner a enviar", tracking=True, ondelete="restrict", copy=False)
    history_available_black = fields.Boolean(string="Con historial", compute="_compute_color_analysis")
    base_counter_black = fields.Integer(string="Contador anterior", compute="_compute_color_analysis")
    consumed_copies_black = fields.Integer(string="Copias consumidas", compute="_compute_color_analysis")
    consumption_percent_black = fields.Float(string="Rendimiento consumido (%)", compute="_compute_color_analysis")
    days_since_delivery_black = fields.Integer(string="Días desde entrega", compute="_compute_color_analysis")
    last_delivery_date_black = fields.Datetime(string="Última entrega", compute="_compute_color_analysis")
    expected_yield_black = fields.Integer(string="Rendimiento esperado", compute="_compute_color_analysis")
    toner_brand_cyan_id = fields.Many2one("toner.brand", string="Marca del tóner a enviar", tracking=True, ondelete="restrict", copy=False)
    history_available_cyan = fields.Boolean(string="Con historial", compute="_compute_color_analysis")
    base_counter_cyan = fields.Integer(string="Contador anterior", compute="_compute_color_analysis")
    consumed_copies_cyan = fields.Integer(string="Copias consumidas", compute="_compute_color_analysis")
    consumption_percent_cyan = fields.Float(string="Rendimiento consumido (%)", compute="_compute_color_analysis")
    days_since_delivery_cyan = fields.Integer(string="Días desde entrega", compute="_compute_color_analysis")
    last_delivery_date_cyan = fields.Datetime(string="Última entrega", compute="_compute_color_analysis")
    expected_yield_cyan = fields.Integer(string="Rendimiento esperado", compute="_compute_color_analysis")
    toner_brand_magenta_id = fields.Many2one("toner.brand", string="Marca del tóner a enviar", tracking=True, ondelete="restrict", copy=False)
    history_available_magenta = fields.Boolean(string="Con historial", compute="_compute_color_analysis")
    base_counter_magenta = fields.Integer(string="Contador anterior", compute="_compute_color_analysis")
    consumed_copies_magenta = fields.Integer(string="Copias consumidas", compute="_compute_color_analysis")
    consumption_percent_magenta = fields.Float(string="Rendimiento consumido (%)", compute="_compute_color_analysis")
    days_since_delivery_magenta = fields.Integer(string="Días desde entrega", compute="_compute_color_analysis")
    last_delivery_date_magenta = fields.Datetime(string="Última entrega", compute="_compute_color_analysis")
    expected_yield_magenta = fields.Integer(string="Rendimiento esperado", compute="_compute_color_analysis")
    toner_brand_yellow_id = fields.Many2one("toner.brand", string="Marca del tóner a enviar", tracking=True, ondelete="restrict", copy=False)
    history_available_yellow = fields.Boolean(string="Con historial", compute="_compute_color_analysis")
    base_counter_yellow = fields.Integer(string="Contador anterior", compute="_compute_color_analysis")
    consumed_copies_yellow = fields.Integer(string="Copias consumidas", compute="_compute_color_analysis")
    consumption_percent_yellow = fields.Float(string="Rendimiento consumido (%)", compute="_compute_color_analysis")
    days_since_delivery_yellow = fields.Integer(string="Días desde entrega", compute="_compute_color_analysis")
    last_delivery_date_yellow = fields.Datetime(string="Última entrega", compute="_compute_color_analysis")
    expected_yield_yellow = fields.Integer(string="Rendimiento esperado", compute="_compute_color_analysis")

    equipment_id = fields.Many2one(
        "alquiler",
        string="Equipo",
        required=True,
        tracking=True,
        index=True,
        domain=[("estado_alquiler_id", "=", "alquilada")],
    )
    tipo_maquina_id = fields.Selection(
        related="equipment_id.tipo_maquina_id",
        string="Tipo de Equipo",
        readonly=True,
        store=True,
    )

    partner_id = fields.Many2one(
        "res.partner",
        string="Cliente",
        related="equipment_id.cliente_id",
        store=True,
        readonly=True,
        index=True,
    )

    submission_date = fields.Datetime(
        string="Fecha de solicitud",
        default=fields.Datetime.now,
        required=True,
        tracking=True,
        index=True,
    )

    secuencia = fields.Char(
        string="Número de solicitud",
        default="New",
        copy=False,
        readonly=True,
        required=True,
        index=True,
    )

    source = fields.Selection(
        [
            ("portal", "Portal del cliente"),
            ("manual", "Registro manual"),
            ("api", "Integración/API"),
        ],
        string="Origen",
        default="manual",
        required=True,
        readonly=True,
        tracking=True,
        index=True,
    )

    created_by_user_id = fields.Many2one(
        "res.users",
        string="Registrado por",
        default=lambda self: self.env.user,
        readonly=True,
        required=True,
        tracking=True,
        index=True,
    )

    # -------------------------------------------------------------------------
    # Solicitante
    # -------------------------------------------------------------------------

    client_name = fields.Char(
        string="Nombre del solicitante",
        required=True,
        tracking=True,
        default=lambda self: self.env.user.name or "",
    )

    client_email = fields.Char(
        string="Correo del solicitante",
        required=True,
        tracking=True,
        default=lambda self: (
            self.env.user.email
            or self.env.user.partner_id.email
            or "soporte@andescopiers.com.pe"
        ),
    )

    client_phone = fields.Char(
        string="Teléfono del solicitante",
        tracking=True,
        default=lambda self: (
            self.env.user.partner_id.mobile
            or self.env.user.partner_id.phone
            or ""
        ),
    )

    client_phone_clean = fields.Char(
        string="Teléfono limpio",
        compute="_compute_client_phone_clean",
        store=True,
    )

    # -------------------------------------------------------------------------
    # Contadores
    # -------------------------------------------------------------------------

    counter_bn = fields.Integer(
        string="Contador B/N actual",
        required=True,
        tracking=True,
    )

    counter_color = fields.Integer(
        string="Contador color actual",
        default=0,
        tracking=True,
    )

    previous_counter_bn = fields.Integer(
        string="Contador B/N anterior",
        default=0,
        tracking=True,
        help=(
            "Referencia automática de la última entrega confirmada. "
            "Consultar las bases individuales en cada tarjeta de color."
        ),
    )

    previous_counter_color = fields.Integer(
        string="Contador color anterior",
        default=0,
        tracking=True,
        help=(
            "Referencia automática de la última entrega confirmada. "
            "Consultar las bases individuales en cada tarjeta de color."
        ),
    )

    copies_bn_period = fields.Integer(
        string="Copias B/N desde la base",
        compute="_compute_period_copies",
        store=True,
    )

    copies_color_period = fields.Integer(
        string="Copias color desde la base",
        compute="_compute_period_copies",
        store=True,
    )

    total_copies_period = fields.Integer(
        string="Copias totales desde la base",
        compute="_compute_period_copies",
        store=True,
    )

    # -------------------------------------------------------------------------
    # Tóner solicitado
    # -------------------------------------------------------------------------

    requiere_toner_black = fields.Boolean(
        string="Solicita tóner negro",
        tracking=True,
    )
    requiere_toner_cyan = fields.Boolean(
        string="Solicita tóner cian",
        tracking=True,
    )
    requiere_toner_magenta = fields.Boolean(
        string="Solicita tóner magenta",
        tracking=True,
    )
    requiere_toner_yellow = fields.Boolean(
        string="Solicita tóner amarillo",
        tracking=True,
    )

    cantidad_solicitada_black = fields.Integer(
        string="Cantidad solicitada negro",
        default=0,
        tracking=True,
    )
    cantidad_solicitada_cyan = fields.Integer(
        string="Cantidad solicitada cian",
        default=0,
        tracking=True,
    )
    cantidad_solicitada_magenta = fields.Integer(
        string="Cantidad solicitada magenta",
        default=0,
        tracking=True,
    )
    cantidad_solicitada_yellow = fields.Integer(
        string="Cantidad solicitada amarillo",
        default=0,
        tracking=True,
    )

    cantidad_sugerida_black = fields.Integer(
        string="Cantidad sugerida negro",
        default=0,
        tracking=True,
    )
    cantidad_sugerida_cyan = fields.Integer(
        string="Cantidad sugerida cian",
        default=0,
        tracking=True,
    )
    cantidad_sugerida_magenta = fields.Integer(
        string="Cantidad sugerida magenta",
        default=0,
        tracking=True,
    )
    cantidad_sugerida_yellow = fields.Integer(
        string="Cantidad sugerida amarillo",
        default=0,
        tracking=True,
    )

    # -------------------------------------------------------------------------
    # Evaluación comercial por color
    # -------------------------------------------------------------------------

    COMMERCIAL_COLOR_DECISIONS = [
        ("pending", "Pendiente"),
        ("procede", "Procede"),
        ("no_procede", "No procede"),
    ]

    decision_black = fields.Selection(
        COMMERCIAL_COLOR_DECISIONS, string="Evaluación negro", default="pending", tracking=True
    )
    decision_cyan = fields.Selection(
        COMMERCIAL_COLOR_DECISIONS, string="Evaluación cian", default="pending", tracking=True
    )
    decision_magenta = fields.Selection(
        COMMERCIAL_COLOR_DECISIONS, string="Evaluación magenta", default="pending", tracking=True
    )
    decision_yellow = fields.Selection(
        COMMERCIAL_COLOR_DECISIONS, string="Evaluación amarillo", default="pending", tracking=True
    )

    motivo_no_procede_black = fields.Char(string="Motivo negro", tracking=True)
    motivo_no_procede_cyan = fields.Char(string="Motivo cian", tracking=True)
    motivo_no_procede_magenta = fields.Char(string="Motivo magenta", tracking=True)
    motivo_no_procede_yellow = fields.Char(string="Motivo amarillo", tracking=True)

    cantidad_aprobada_black = fields.Integer(
        string="Cantidad aprobada negro",
        default=0,
        tracking=True,
    )
    cantidad_aprobada_cyan = fields.Integer(
        string="Cantidad aprobada cian",
        default=0,
        tracking=True,
    )
    cantidad_aprobada_magenta = fields.Integer(
        string="Cantidad aprobada magenta",
        default=0,
        tracking=True,
    )
    cantidad_aprobada_yellow = fields.Integer(
        string="Cantidad aprobada amarillo",
        default=0,
        tracking=True,
    )

    # -------------------------------------------------------------------------
    # Stock reportado y nivel instalado
    # -------------------------------------------------------------------------

    stock_reportado_black = fields.Integer(string="Stock cliente negro", default=0)
    stock_reportado_cyan = fields.Integer(string="Stock cliente cian", default=0)
    stock_reportado_magenta = fields.Integer(string="Stock cliente magenta", default=0)
    stock_reportado_yellow = fields.Integer(string="Stock cliente amarillo", default=0)

    nivel_toner_black = fields.Selection(
        [
            ("lleno", "Lleno"),
            ("medio", "Medio"),
            ("bajo", "Bajo"),
            ("critico", "Crítico"),
            ("agotado", "Agotado"),
        ],
        string="Nivel negro",
    )
    nivel_toner_cyan = fields.Selection(
        [
            ("lleno", "Lleno"),
            ("medio", "Medio"),
            ("bajo", "Bajo"),
            ("critico", "Crítico"),
            ("agotado", "Agotado"),
        ],
        string="Nivel cian",
    )
    nivel_toner_magenta = fields.Selection(
        [
            ("lleno", "Lleno"),
            ("medio", "Medio"),
            ("bajo", "Bajo"),
            ("critico", "Crítico"),
            ("agotado", "Agotado"),
        ],
        string="Nivel magenta",
    )
    nivel_toner_yellow = fields.Selection(
        [
            ("lleno", "Lleno"),
            ("medio", "Medio"),
            ("bajo", "Bajo"),
            ("critico", "Crítico"),
            ("agotado", "Agotado"),
        ],
        string="Nivel amarillo",
    )

    # -------------------------------------------------------------------------
    # Resultado de evaluación automática
    # -------------------------------------------------------------------------

    analysis_result = fields.Selection(
        [
            ("normal", "Consumo razonable"),
            ("early_consumption", "Consumo anticipado"),
            ("duplicate", "Solicitud duplicada"),
            ("no_history", "Sin historial suficiente"),
            ("manual_review", "Revisión manual"),
        ],
        string="Resultado automático",
        default="manual_review",
        tracking=True,
        index=True,
    )

    analysis_summary = fields.Text(
        string="Resumen del análisis",
        readonly=True,
    )

    analysis_json = fields.Text(
        string="Detalle técnico JSON",
        readonly=True,
    )

    requires_evidence = fields.Boolean(
        string="Requiere evidencia",
        tracking=True,
    )

    early_request_reason = fields.Text(
        string="Motivo de solicitud anticipada",
        tracking=True,
    )

    duplicate_submission_id = fields.Many2one(
        "toner.counter.submission",
        string="Solicitud duplicada encontrada",
        readonly=True,
    )

    last_delivery_date = fields.Datetime(
        string="Última entrega de referencia",
        readonly=True,
    )

    days_since_last_delivery = fields.Integer(
        string="Días desde la última entrega",
        readonly=True,
    )

    expected_yield = fields.Integer(
        string="Rendimiento esperado",
        readonly=True,
    )

    consumed_copies = fields.Integer(
        string="Copias consumidas",
        readonly=True,
    )

    consumption_percent = fields.Float(
        string="% de rendimiento consumido",
        digits=(16, 2),
        readonly=True,
    )

    # -------------------------------------------------------------------------
    # Gestión interna
    # -------------------------------------------------------------------------

    state = fields.Selection(
        [
            ("recibida", "Solicitud recibida"),
            ("evaluacion", "En evaluación"),
            ("pendiente_gerencia", "Pendiente de gerencia"),
            ("aprobada_gerencia", "Aprobada por gerencia"),
            ("rechazada_gerencia", "Rechazada por gerencia"),
            ("devuelta", "Devuelta para corrección"),
            ("confirmacion_ventas", "Pendiente de confirmación de stock"),
            ("lista_despacho", "Lista para despacho"),
            ("en_despacho", "En despacho"),
            ("entregada", "Entregada"),
            ("cancelada", "Cancelada"),
        ],
        string="Estado",
        default="recibida",
        tracking=True,
        index=True,
        required=True,
    )

    reviewer_id = fields.Many2one("res.users", string="Evaluado por", tracking=True)
    review_date = fields.Datetime(string="Fecha de evaluación", tracking=True)
    review_notes = fields.Text(string="Evaluación de asesora/alquiler", tracking=True)

    management_user_id = fields.Many2one("res.users", string="Gerencia", tracking=True)
    management_date = fields.Datetime(string="Fecha decisión gerencia", tracking=True)
    management_notes = fields.Text(string="Decisión de gerencia", tracking=True)

    management_decision = fields.Selection(
        [
            ("approved", "Aprobada"),
            ("information_requested", "Solicitó información"),
            ("rejected", "Rechazada"),
            ("cancelled", "Cancelada"),
        ],
        string="Decisión de gerencia",
        readonly=True,
        tracking=True,
        index=True,
    )

    management_decision_name = fields.Char(
        string="Nombre de quien decidió",
        readonly=True,
        tracking=True,
    )

    management_decision_ip = fields.Char(
        string="IP de decisión",
        readonly=True,
    )

    management_access_token = fields.Char(
        string="Token de decisión",
        copy=False,
        readonly=True,
        index=True,
    )

    management_token_expires_at = fields.Datetime(
        string="Vencimiento del enlace",
        copy=False,
        readonly=True,
    )

    management_token_used_at = fields.Datetime(
        string="Enlace utilizado",
        copy=False,
        readonly=True,
    )

    stock_confirmed_by_id = fields.Many2one(
        "res.users",
        string="Stock confirmado por",
        readonly=True,
        tracking=True,
    )

    stock_confirmation_date = fields.Datetime(
        string="Fecha de confirmación de stock",
        readonly=True,
        tracking=True,
    )

    stock_confirmation_notes = fields.Text(
        string="Observaciones de stock",
        tracking=True,
    )

    sales_user_id = fields.Many2one("res.users", string="Confirmado por ventas", tracking=True)
    sales_confirmation_date = fields.Datetime(
        string="Fecha de confirmación comercial",
        tracking=True,
    )
    sales_notes = fields.Text(string="Coordinación comercial", tracking=True)

    delivery_scheduled_id = fields.Many2one(
        "toner.delivery.schedule",
        string="Entrega programada",
        readonly=True,
        tracking=True,
    )

    # Campos puente para operar el despacho desde la solicitud principal.
    delivery_state = fields.Selection(
        related="delivery_scheduled_id.state", string="Estado del despacho", readonly=True
    )
    delivery_confirmation_id = fields.Many2one(
        related="delivery_scheduled_id.confirmation_id",
        string="Confirmación de entrega",
        readonly=True,
    )
    delivery_date_planned_ui = fields.Date(
        related="delivery_scheduled_id.delivery_date_planned",
        string="Fecha programada",
        readonly=False,
    )
    delivery_assigned_user_id = fields.Many2one(
        related="delivery_scheduled_id.assigned_user",
        string="Responsable de entrega",
        readonly=False,
    )
    delivery_method_ui = fields.Selection(
        related="delivery_scheduled_id.delivery_method",
        string="Método de entrega",
        readonly=False,
    )
    delivery_tracking_number_ui = fields.Char(
        related="delivery_scheduled_id.tracking_number",
        string="Número de seguimiento",
        readonly=False,
    )
    delivery_address_ui = fields.Text(
        related="delivery_scheduled_id.delivery_address",
        string="Dirección de entrega",
        readonly=True,
    )
    delivery_contact_person_ui = fields.Char(
        related="delivery_scheduled_id.contact_person",
        string="Contacto de entrega",
        readonly=True,
    )
    delivery_contact_phone_ui = fields.Char(
        related="delivery_scheduled_id.contact_phone",
        string="Teléfono de entrega",
        readonly=True,
    )

    notes = fields.Text(string="Observaciones del cliente")
    photo_counter = fields.Binary(string="Foto del contador")
    photo_counter_filename = fields.Char(string="Archivo contador")
    photo_toner = fields.Binary(string="Foto del tóner")
    photo_toner_filename = fields.Char(string="Archivo tóner")

    # -------------------------------------------------------------------------
    # Cálculos
    # -------------------------------------------------------------------------

    @api.depends("equipment_id", "submission_date", "client_name", "secuencia")
    def _compute_display_name(self):
        for record in self:
            equipment_name = (
                record.equipment_id.name.name
                if record.equipment_id and record.equipment_id.name
                else "Sin equipo"
            )
            record.display_name = "%s - %s - %s" % (
                record.secuencia or "Nueva",
                equipment_name,
                record.client_name or "Sin solicitante",
            )

    @api.depends("client_phone")
    def _compute_client_phone_clean(self):
        for record in self:
            record.client_phone_clean = record._clean_phone(record.client_phone)

    @api.depends(
        "counter_bn",
        "counter_color",
        "previous_counter_bn",
        "previous_counter_color",
        "analysis_json",
        "history_snapshot_json",
    )
    def _compute_period_copies(self):
        for record in self:
            try:
                results = json.loads(record.analysis_json or "{}").get("colors", [])
            except (ValueError, TypeError):
                results = []
            bn = next((r for r in results if r.get("color") == "black"), {})
            color = next((r for r in results if r.get("color") in ("cyan", "magenta", "yellow")
                          and r.get("history_available")), {})
            record.copies_bn_period = int(bn.get("consumed_copies", 0) or 0)
            record.copies_color_period = int(color.get("consumed_copies", 0) or 0)
            record.total_copies_period = record.copies_bn_period + record.copies_color_period

    # -------------------------------------------------------------------------
    # Utilidades
    # -------------------------------------------------------------------------

    @api.model
    def _get_color_history(self, equipment, color):
        delivery = self._find_last_delivered_schedule(equipment.id, color)
        submission = delivery.submission_id if delivery else False
        # No usar el contador mutable del equipo si falta la solicitud histórica.
        if not submission:
            return {"history_available": False, "last_delivery_id": False,
                    "last_delivery_date": False, "base_counter": 0}
        return {"history_available": True, "last_delivery_id": delivery.id,
                "last_delivery_date": fields.Datetime.to_string(delivery.delivery_date_actual or delivery.creation_date),
                "base_counter": int(submission.counter_bn if color == "black" else submission.counter_color)}

    def _capture_toner_history(self):
        self.ensure_one()
        service = self.with_context(toner_history_before=fields.Datetime.to_string(self.submission_date or fields.Datetime.now()), toner_history_exclude=self._origin.id or False)
        return json.dumps({color: service._get_color_history(self.equipment_id, color)
                           for color in self.COLOR_LABELS}, default=str)

    @api.depends("analysis_json", "history_snapshot_json")
    def _compute_color_analysis(self):
        for record in self:
            try:
                results = {r["color"]: r for r in json.loads(record.analysis_json or "{}").get("colors", [])}
                history = json.loads(record.history_snapshot_json or "{}")
            except (ValueError, TypeError, KeyError):
                results, history = {}, {}
            for color in record.COLOR_LABELS:
                item = dict(history.get(color, {}), **results.get(color, {}))
                for prefix, key in [("history_available", "history_available"),
                                    ("base_counter", "base_counter"),
                                    ("consumed_copies", "consumed_copies"),
                                    ("consumption_percent", "consumption_percent"),
                                    ("days_since_delivery", "days_since_last_delivery"),
                                    ("expected_yield", "expected_yield"),
                                    ("last_delivery_date", "last_delivery_date")]:
                    setattr(record, prefix + "_" + color, item.get(key) or False)

    @api.model
    def _clean_phone(self, phone):
        phone = (phone or "").replace("@c.us", "")
        phone = "".join(character for character in phone if character.isdigit())
        if phone and not phone.startswith("51") and len(phone) == 9:
            phone = "51" + phone
        return phone

    @api.model
    def _requested_colors_from_values(self, values):
        colors = []
        for color in self.COLOR_LABELS:
            if values.get("requires_%s" % color):
                colors.append(color)
        return colors

    @api.model
    def _color_boolean_field(self, color):
        return {
            "black": "requiere_toner_black",
            "cyan": "requiere_toner_cyan",
            "magenta": "requiere_toner_magenta",
            "yellow": "requiere_toner_yellow",
        }[color]

    @api.model
    def _delivery_quantity_field(self, color):
        return {
            "black": "toner_black_qty",
            "cyan": "toner_cyan_qty",
            "magenta": "toner_magenta_qty",
            "yellow": "toner_yellow_qty",
        }[color]

    @api.model
    def _requested_quantity_field(self, color):
        return "cantidad_solicitada_%s" % color

    @api.model
    def _suggested_quantity_field(self, color):
        return "cantidad_sugerida_%s" % color

    @api.model
    def _approved_quantity_field(self, color):
        return "cantidad_aprobada_%s" % color

    @api.model
    def _get_expected_yield(self, equipment, color):
        """
        Busca el rendimiento sin imponer un único nombre de campo.
        Usa el primer campo existente y con valor.
        """
        model = equipment.name
        candidates = {
            "black": [
                "durabilidad_toner_black",
                "rendimiento_toner_black",
                "rendimiento_black",
            ],
            "cyan": [
                "durabilidad_toner_cyan",
                "rendimiento_toner_cyan",
                "rendimiento_cyan",
            ],
            "magenta": [
                "durabilidad_toner_magenta",
                "rendimiento_toner_magenta",
                "rendimiento_magenta",
            ],
            "yellow": [
                "durabilidad_toner_yellow",
                "rendimiento_toner_yellow",
                "rendimiento_yellow",
            ],
        }

        for field_name in candidates[color]:
            if field_name in model._fields:
                value = int(getattr(model, field_name) or 0)
                if value > 0:
                    return value

        parameter = self.env["ir.config_parameter"].sudo()
        default_value = int(
            parameter.get_param(
                "sat.toner_default_yield_%s" % color,
                "10000" if color == "black" else "8000",
            )
        )
        return max(default_value, 1)

    @api.model
    def _find_open_duplicate(self, equipment_id, color, exclude_submission_id=False):
        field_name = self._color_boolean_field(color)
        domain = [
            ("equipment_id", "=", equipment_id),
            (field_name, "=", True),
            ("state", "in", self.OPEN_STATES),
        ]
        if exclude_submission_id:
            domain.append(("id", "!=", int(exclude_submission_id)))

        return self.search(
            domain,
            order="submission_date desc, id desc",
            limit=1,
        )

    @api.model
    def _find_last_delivered_schedule(self, equipment_id, color):
        quantity_field = self._delivery_quantity_field(color)
        domain = [("equipment_id", "=", equipment_id),
                  ("state", "=", "entregado"), (quantity_field, ">", 0)]
        exclude = self.env.context.get("toner_history_exclude")
        if exclude:
            domain.append(("submission_id", "!=", exclude))
        before = self.env.context.get("toner_history_before")
        if before:
            domain += ["|", ("delivery_date_actual", "<=", before),
                       "&", ("delivery_date_actual", "=", False),
                       ("creation_date", "<=", before)]
        return self.env["toner.delivery.schedule"].sudo().search(
            domain, order="delivery_date_actual desc, id desc", limit=1)


    @api.model
    def _get_known_counter_floor(self, equipment):
        """Devuelve el mayor contador conocido y confiable del equipo.

        La validación de una nueva solicitud nunca debe permitir que B/N o
        color retrocedan respecto de un contador ya conocido. Se toman como
        referencia los campos actuales del equipo y, cuando existen, los
        eventos de monitoreo históricos con contador positivo.
        """
        known_bn = int(equipment.contador_bn or 0)
        known_color = int(equipment.contador_color or 0)

        try:
            Event = self.env["toner.monitoring.event"].sudo()

            max_bn_event = Event.search(
                [
                    ("equipment_id", "=", equipment.id),
                    ("counter_bn", ">", 0),
                ],
                order="counter_bn desc, event_date desc, id desc",
                limit=1,
            )
            if max_bn_event:
                known_bn = max(known_bn, int(max_bn_event.counter_bn or 0))

            if equipment.tipo_maquina_id == "color":
                max_color_event = Event.search(
                    [
                        ("equipment_id", "=", equipment.id),
                        ("counter_color", ">", 0),
                    ],
                    order="counter_color desc, event_date desc, id desc",
                    limit=1,
                )
                if max_color_event:
                    known_color = max(
                        known_color,
                        int(max_color_event.counter_color or 0),
                    )
        except Exception:
            # La solicitud no debe fallar solo porque el modelo de monitoreo no
            # esté disponible. Los contadores del equipo siguen siendo una base
            # válida y la excepción queda registrada para diagnóstico.
            _logger.exception(
                "[TONER] No se pudo consultar historial de contadores equipo=%s",
                equipment.id,
            )

        return {
            "bn": known_bn,
            "color": known_color if equipment.tipo_maquina_id == "color" else 0,
        }

    @api.model
    def _analyze_color(self, equipment, color, current_counters,
                       exclude_submission_id=False, base_counters=None):
        """
        Analiza el consumo de un color.

        Regla de contador base:
        - Si existe una entrega anterior, SIEMPRE usa el contador actual de esa
          solicitud entregada como contador anterior del nuevo pedido.
        - Si no existe ninguna entrega anterior, permite usar el contador
          anterior ingresado manualmente en el formulario.
        """
        duplicate = self._find_open_duplicate(
            equipment.id, color, exclude_submission_id
        )
        if duplicate:
            return {
                "color": color,
                "label": self.COLOR_LABELS[color],
                "status": "duplicate",
                "can_create": False,
                "duplicate_id": duplicate.id,
                "duplicate_sequence": duplicate.secuencia,
                "message": _(
                    "Ya existe una solicitud activa para el tóner %s."
                ) % self.COLOR_LABELS[color],
            }

        history = None
        record = False
        if exclude_submission_id:
            record = self.browse(exclude_submission_id).exists()
            if (
                record
                and record.equipment_id == equipment
                and record.history_snapshot_json
            ):
                try:
                    history = json.loads(record.history_snapshot_json).get(color)
                except (ValueError, TypeError):
                    history = None

        if history is None:
            service = self
            if exclude_submission_id and record:
                service = self.with_context(
                    toner_history_before=fields.Datetime.to_string(
                        record.submission_date
                    ),
                    toner_history_exclude=record.id,
                )
            history = service._get_color_history(equipment, color)

        history = history or {
            "history_available": False,
            "last_delivery_id": False,
            "last_delivery_date": False,
            "base_counter": 0,
        }

        counter_key = "bn" if color == "black" else "color"
        current = int(current_counters.get(counter_key, 0) or 0)
        expected = self._get_expected_yield(equipment, color)

        manual_base = 0
        if base_counters:
            manual_base = int(base_counters.get(counter_key, 0) or 0)

        # La entrega anterior tiene prioridad absoluta. Solo si no existe
        # historial se acepta el contador anterior escrito manualmente.
        if history.get("history_available"):
            base = int(history.get("base_counter", 0) or 0)
            base_source = "history"
        elif manual_base > 0:
            base = manual_base
            base_source = "manual"
        else:
            base = 0
            base_source = "none"

        result = dict(
            history,
            color=color,
            label=self.COLOR_LABELS[color],
            current_counter=current,
            expected_yield=expected,
            can_create=True,
            requires_evidence=False,
            consumed_copies=0,
            consumption_percent=0.0,
            days_since_last_delivery=0,
            base_counter=base,
            base_source=base_source,
            manual_base=(base_source == "manual"),
        )

        if base_source == "none":
            result.update(
                status="no_history",
                message=_(
                    "Sin historial anterior para el tóner %s. "
                    "Puede ingresar manualmente el contador anterior."
                ) % self.COLOR_LABELS[color],
            )
            return result

        if current < base:
            result.update(
                status="invalid_counter",
                can_create=False,
                message=_(
                    "El contador actual de %s no puede ser menor al contador anterior."
                ) % self.COLOR_LABELS[color],
            )
            return result

        consumed = current - base
        percent = consumed / expected * 100 if expected else 0.0
        threshold = float(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("sat.toner_early_consumption_percent", "50")
        )

        reference_date = fields.Datetime.now()
        if exclude_submission_id and record:
            reference_date = fields.Datetime.to_datetime(record.submission_date)

        delivery_date = fields.Datetime.to_datetime(
            history.get("last_delivery_date")
        )
        days = (
            max(0, (reference_date - delivery_date).days)
            if delivery_date
            else 0
        )

        result.update(
            status="early_consumption" if percent < threshold else "normal",
            requires_evidence=percent < threshold,
            consumed_copies=consumed,
            consumption_percent=round(percent, 2),
            days_since_last_delivery=days,
            message=_(
                "%(color)s: %(copies)s de %(yield)s copias "
                "(%(percent).2f%%), %(days)s días desde la entrega."
            ) % {
                "color": self.COLOR_LABELS[color],
                "copies": consumed,
                "yield": expected,
                "percent": percent,
                "days": days,
            },
        )
        return result

    @api.model
    def validate_web_toner_request(
        self,
        equipment_id,
        requested_toners,
        current_counters=None,
        exclude_submission_id=False,
        base_counters=None,
    ):
        current_counters = current_counters or {}
        equipment = (
            self.env["alquiler"]
            .sudo()
            .browse(int(equipment_id))
            .exists()
        )

        if not equipment:
            return {
                "valid": False,
                "can_create": False,
                "reason": "equipment_not_found",
                "message": _("El equipo no existe."),
                "colors": [],
            }

        selected_colors = [
            color
            for color in self.COLOR_LABELS
            if requested_toners.get(color)
        ]
        if not selected_colors:
            return {
                "valid": False,
                "can_create": False,
                "reason": "no_toner_selected",
                "message": _(
                    "Debe seleccionar al menos un tóner."
                ),
                "colors": [],
            }

        if equipment.tipo_maquina_id != "color":
            selected_colors = [
                color
                for color in selected_colors
                if color == "black"
            ]

        counter_bn = int(
            current_counters.get(
                "bn",
                0,
            )
            or 0
        )
        counter_color = int(
            current_counters.get(
                "color",
                0,
            )
            or 0
        )

        if counter_bn <= 0:
            return {
                "valid": False,
                "can_create": False,
                "reason": "invalid_counter",
                "message": _(
                    "El contador B/N debe ser mayor que cero."
                ),
                "colors": [],
            }

        if equipment.tipo_maquina_id == "color" and counter_color <= 0:
            return {
                "valid": False,
                "can_create": False,
                "reason": "invalid_counter",
                "message": _(
                    "El contador color debe ser mayor que cero."
                ),
                "colors": [],
            }

        known_counters = self._get_known_counter_floor(equipment)
        known_bn = int(known_counters.get("bn", 0) or 0)
        known_color = int(known_counters.get("color", 0) or 0)

        if known_bn > 0 and counter_bn < known_bn:
            return {
                "valid": False,
                "can_create": False,
                "reason": "counter_lower_than_known",
                "message": _(
                    "El contador B/N ingresado (%(current)s) no puede ser "
                    "menor al último contador conocido del equipo (%(known)s)."
                ) % {
                    "current": counter_bn,
                    "known": known_bn,
                },
                "colors": [],
                "known_counters": known_counters,
            }

        if (
            equipment.tipo_maquina_id == "color"
            and known_color > 0
            and counter_color < known_color
        ):
            return {
                "valid": False,
                "can_create": False,
                "reason": "counter_lower_than_known",
                "message": _(
                    "El contador color ingresado (%(current)s) no puede ser "
                    "menor al último contador conocido del equipo (%(known)s)."
                ) % {
                    "current": counter_color,
                    "known": known_color,
                },
                "colors": [],
                "known_counters": known_counters,
            }

        _logger.info(
            "[TONER] Validación de contadores equipo=%s serie=%s "
            "actual_bn=%s conocido_bn=%s actual_color=%s conocido_color=%s",
            equipment.id,
            equipment.serie,
            counter_bn,
            known_bn,
            counter_color,
            known_color,
        )

        results = [
            self._analyze_color(
                equipment,
                color,
                {
                    "bn": counter_bn,
                    "color": counter_color,
                },
                exclude_submission_id=(
                    exclude_submission_id
                ),
                base_counters=base_counters,
            )
            for color in selected_colors
        ]

        blocking = [
            item
            for item in results
            if not item.get("can_create")
        ]
        review_required = any(
            item.get("requires_evidence")
            for item in results
        )

        if blocking:
            duplicate = next(
                (
                    item
                    for item in blocking
                    if item.get("status") == "duplicate"
                ),
                None,
            )
            return {
                "valid": False,
                "can_create": False,
                "reason": (
                    duplicate.get("status")
                    if duplicate
                    else "blocked"
                ),
                "message": " ".join(
                    item["message"]
                    for item in blocking
                ),
                "colors": results,
                "duplicate_submission_id": (
                    duplicate.get("duplicate_id")
                    if duplicate
                    else False
                ),
                "duplicate_sequence": (
                    duplicate.get("duplicate_sequence")
                    if duplicate
                    else False
                ),
            }

        return {
            "valid": True,
            "can_create": True,
            "reason": (
                "review_required"
                if review_required
                else "received"
            ),
            "review_required": review_required,
            "requires_evidence": review_required,
            "message": (
                _(
                    "La solicitud puede registrarse, "
                    "pero requiere revisión por consumo anticipado."
                )
                if review_required
                else _(
                    "La solicitud puede registrarse "
                    "para evaluación interna."
                )
            ),
            "colors": results,
        }

    @api.model
    def create_from_web_request(self, web_data):
        try:
            if "counter_bn" not in web_data:
                raise ValidationError(_("Debe enviar el contador B/N actual."))
            equipment = self.env["alquiler"].sudo().browse(
                int(web_data["equipment_id"])
            ).exists()
            if not equipment:
                return {"success": False, "error": _("Equipo no encontrado.")}

            if equipment.tipo_maquina_id == "color":
                if "counter_color" not in web_data:
                    raise ValidationError(_("Debe enviar el contador color actual."))
                if int(web_data.get("counter_color", 0) or 0) <= 0:
                    raise ValidationError(_("El contador color debe ser mayor que cero."))
            requested_toners = {
                color: bool(web_data.get("requires_%s" % color))
                for color in self.COLOR_LABELS
            }

            validation = self.validate_web_toner_request(
                equipment_id=equipment.id,
                requested_toners=requested_toners,
                current_counters={
                    "bn": int(web_data.get("counter_bn", 0) or 0),
                    "color": int(web_data.get("counter_color", 0) or 0),
                },
            )

            if not validation.get("can_create"):
                return {
                    "success": False,
                    "blocked": True,
                    "validation": validation,
                    "error": validation.get("message"),
                }

            color_results = validation.get("colors", [])
            first_with_history = next(
                (
                    item
                    for item in color_results
                    if item.get("base_counter") is not None
                ),
                {},
            )
            most_restrictive = next(
                (
                    item
                    for item in color_results
                    if item.get("status") == "early_consumption"
                ),
                color_results[0] if color_results else {},
            )

            vals = {
                "equipment_id": equipment.id,
                "source": "portal",
                "created_by_user_id": self.env.user.id,
                "client_name": web_data.get("client_name") or _("Sin nombre"),
                "client_email": web_data.get("client_email")
                or "soporte@andescopiers.com.pe",
                "client_phone": self._clean_phone(web_data.get("client_phone")),
                "counter_bn": int(web_data.get("counter_bn", 0) or 0),
                "counter_color": int(web_data.get("counter_color", 0) or 0),
                "previous_counter_bn": 0,
                "previous_counter_color": 0,
                "requiere_toner_black": requested_toners["black"],
                "requiere_toner_cyan": requested_toners["cyan"],
                "requiere_toner_magenta": requested_toners["magenta"],
                "requiere_toner_yellow": requested_toners["yellow"],
                "cantidad_solicitada_black": 1 if requested_toners["black"] else 0,
                "cantidad_solicitada_cyan": 1 if requested_toners["cyan"] else 0,
                "cantidad_solicitada_magenta": 1 if requested_toners["magenta"] else 0,
                "cantidad_solicitada_yellow": 1 if requested_toners["yellow"] else 0,
                "cantidad_sugerida_black": 1
                if requested_toners["black"]
                and not next(
                    (
                        item.get("requires_evidence")
                        for item in color_results
                        if item["color"] == "black"
                    ),
                    False,
                )
                else 0,
                "cantidad_sugerida_cyan": 1
                if requested_toners["cyan"]
                and not next(
                    (
                        item.get("requires_evidence")
                        for item in color_results
                        if item["color"] == "cyan"
                    ),
                    False,
                )
                else 0,
                "cantidad_sugerida_magenta": 1
                if requested_toners["magenta"]
                and not next(
                    (
                        item.get("requires_evidence")
                        for item in color_results
                        if item["color"] == "magenta"
                    ),
                    False,
                )
                else 0,
                "cantidad_sugerida_yellow": 1
                if requested_toners["yellow"]
                and not next(
                    (
                        item.get("requires_evidence")
                        for item in color_results
                        if item["color"] == "yellow"
                    ),
                    False,
                )
                else 0,
                "analysis_result": (
                    "early_consumption"
                    if validation.get("review_required")
                    else (
                        "no_history"
                        if any(
                            item.get("status") == "no_history"
                            for item in color_results
                        )
                        else "normal"
                    )
                ),
                "analysis_summary": "\n".join(
                    item.get("message", "") for item in color_results
                ),
                "analysis_json": json.dumps(
                    validation,
                    ensure_ascii=False,
                    default=str,
                    indent=2,
                ),
                "requires_evidence": bool(validation.get("requires_evidence")),
                "last_delivery_date": most_restrictive.get("last_delivery_date"),
                "days_since_last_delivery": int(
                    most_restrictive.get("days_since_last_delivery", 0) or 0
                ),
                "expected_yield": int(
                    most_restrictive.get("expected_yield", 0) or 0
                ),
                "consumed_copies": int(
                    most_restrictive.get("consumed_copies", 0) or 0
                ),
                "consumption_percent": float(
                    most_restrictive.get("consumption_percent", 0.0) or 0.0
                ),
                "notes": web_data.get("notes"),
                "state": "recibida",
            }

            submission = self.sudo().create(vals)
            submission._create_internal_activity()

            _logger.info(
                "[TONER] Solicitud creada secuencia=%s equipo=%s colores=%s "
                "resultado=%s evidencia=%s",
                submission.secuencia,
                equipment.id,
                self._requested_colors_from_values(web_data),
                submission.analysis_result,
                submission.requires_evidence,
            )

            return {
                "success": True,
                "submission_id": submission.id,
                "secuencia": submission.secuencia,
                "state": submission.state,
                "message": _(
                    "Solicitud registrada correctamente. Será evaluada por el área responsable."
                ),
                "requires_evidence": submission.requires_evidence,
                "analysis_result": submission.analysis_result,
                "validation": validation,
            }
        except Exception as error:
            _logger.exception(
                "[TONER] Error creando solicitud web data=%s error=%s",
                web_data,
                str(error),
            )
            return {"success": False, "error": str(error)}


    # -------------------------------------------------------------------------
    # Creación manual segura
    # -------------------------------------------------------------------------

    def _get_requested_toners_from_record(self):
        self.ensure_one()
        return {
            "black": bool(
                self.requiere_toner_black
                or self.cantidad_solicitada_black > 0
            ),
            "cyan": bool(
                self.requiere_toner_cyan
                or self.cantidad_solicitada_cyan > 0
            ),
            "magenta": bool(
                self.requiere_toner_magenta
                or self.cantidad_solicitada_magenta > 0
            ),
            "yellow": bool(
                self.requiere_toner_yellow
                or self.cantidad_solicitada_yellow > 0
            ),
        }

    def _get_current_counters_from_record(self):
        self.ensure_one()
        return {
            "bn": int(self.counter_bn or 0),
            "color": int(self.counter_color or 0),
        }

    def _apply_validation_result(self, validation):
        """Aplica el análisis sin cambiar el estado ni aprobar la solicitud."""
        self.ensure_one()

        self = self.with_context(toner_analysis_write=True)
        color_results = validation.get("colors", [])
        primary = next(
            (
                item
                for item in color_results
                if item.get("status") == "early_consumption"
            ),
            color_results[0] if color_results else {},
        )

        self.analysis_result = (
            "duplicate"
            if validation.get("reason") == "duplicate"
            else "early_consumption"
            if validation.get("review_required")
            else "no_history"
            if any(item.get("status") == "no_history" for item in color_results)
            else "normal"
            if validation.get("can_create")
            else "manual_review"
        )
        self.analysis_summary = "\n".join(
            item.get("message", "") for item in color_results
        ) or validation.get("message", "")
        self.analysis_json = json.dumps(
            validation,
            ensure_ascii=False,
            default=str,
            indent=2,
        )
        self.requires_evidence = bool(validation.get("requires_evidence"))
        self.duplicate_submission_id = validation.get(
            "duplicate_submission_id"
        ) or False
        self.last_delivery_date = primary.get("last_delivery_date") or False
        self.days_since_last_delivery = int(
            primary.get("days_since_last_delivery", 0) or 0
        )
        self.expected_yield = int(primary.get("expected_yield", 0) or 0)
        self.consumed_copies = int(primary.get("consumed_copies", 0) or 0)
        self.consumption_percent = float(
            primary.get("consumption_percent", 0.0) or 0.0
        )

        by_color = {item["color"]: item for item in color_results}

        # B/N: si existe historial real, el contador actual de la última
        # solicitud entregada se convierte en el contador anterior.
        # Si no existe historial, se conserva exactamente el valor manual.
        black_result = by_color.get("black", {})
        if black_result.get("history_available"):
            automatic_previous_bn = int(
                black_result.get("base_counter", 0) or 0
            )
            if automatic_previous_bn > 0:
                self.previous_counter_bn = automatic_previous_bn

        # Color: misma regla. Cian, magenta y amarillo comparten el contador
        # color del equipo, por eso se toma una referencia histórica válida.
        reference = next(
            (
                by_color[c]
                for c in ("cyan", "magenta", "yellow")
                if by_color.get(c, {}).get("history_available")
            ),
            {},
        )
        if reference:
            automatic_previous_color = int(
                reference.get("base_counter", 0) or 0
            )
            if automatic_previous_color > 0:
                self.previous_counter_color = automatic_previous_color

        for color in self.COLOR_LABELS:
            requested_field = self._requested_quantity_field(color)
            suggested_field = self._suggested_quantity_field(color)
            boolean_field = self._color_boolean_field(color)

            current_requested_qty = int(
                getattr(self, requested_field, 0) or 0
            )
            requested = bool(
                getattr(self, boolean_field)
                or current_requested_qty > 0
            )

            setattr(self, boolean_field, requested)

            if requested and current_requested_qty <= 0:
                current_requested_qty = 1
            elif not requested:
                current_requested_qty = 0

            setattr(self, requested_field, current_requested_qty)

            result = next(
                (
                    item
                    for item in color_results
                    if item.get("color") == color
                ),
                {},
            )

            current_suggested_qty = int(
                getattr(self, suggested_field, 0) or 0
            )

            if (
                requested
                and result.get("can_create", True)
                and not result.get("requires_evidence")
            ):
                suggested = (
                    current_suggested_qty
                    if current_suggested_qty > 0
                    else current_requested_qty
                )
            else:
                suggested = 0

            setattr(self, suggested_field, suggested)

    def _validate_record_for_workflow(self):
        """Validación definitiva para portal, formulario manual, API e importación."""
        self.ensure_one()

        if not self.equipment_id:
            raise UserError(_("Debe seleccionar un equipo."))

        requested_toners = self._get_requested_toners_from_record()
        if not any(requested_toners.values()):
            raise UserError(_("Debe seleccionar al menos un tóner."))

        base_counters = {
            "bn": int(self.previous_counter_bn or 0),
            "color": int(self.previous_counter_color or 0),
        }

        validation = self.validate_web_toner_request(
            equipment_id=self.equipment_id.id,
            requested_toners=requested_toners,
            current_counters=(
                self._get_current_counters_from_record()
            ),
            exclude_submission_id=self.id,
            base_counters=base_counters,
        )

        if not validation.get("can_create"):
            raise UserError(
                validation.get("message")
                or _("La solicitud no supera la validación.")
            )

        return validation

    @api.onchange("equipment_id")
    def _onchange_equipment_id_manual(self):
        """Carga equipo, contadores y usuario sin alterar el flujo."""
        for record in self:
            if not record.equipment_id:
                record.counter_bn = 0
                record.counter_color = 0
                continue

            record.counter_bn = 0
            record.counter_color = 0
            record.history_snapshot_json = record._capture_toner_history()

            if not record.client_name:
                record.client_name = record.env.user.name or ""
            if not record.client_email:
                record.client_email = (
                    record.env.user.email
                    or record.env.user.partner_id.email
                    or "soporte@andescopiers.com.pe"
                )
            if not record.client_phone:
                record.client_phone = (
                    record.env.user.partner_id.mobile
                    or record.env.user.partner_id.phone
                    or ""
                )

            if record.equipment_id.tipo_maquina_id != "color":
                record.requiere_toner_cyan = False
                record.requiere_toner_magenta = False
                record.requiere_toner_yellow = False
                record.cantidad_solicitada_cyan = 0
                record.cantidad_solicitada_magenta = 0
                record.cantidad_solicitada_yellow = 0
                record.previous_counter_color = 0
                record.counter_color = 0


    @api.onchange(
        "cantidad_solicitada_black",
        "cantidad_solicitada_cyan",
        "cantidad_solicitada_magenta",
        "cantidad_solicitada_yellow",
    )
    def _onchange_requested_quantities(self):
        for record in self:
            for color in self.COLOR_LABELS:
                quantity_field = record._requested_quantity_field(color)
                boolean_field = record._color_boolean_field(color)
                quantity = int(getattr(record, quantity_field, 0) or 0)

                if quantity < 0:
                    setattr(record, quantity_field, 0)
                    quantity = 0

                setattr(record, boolean_field, quantity > 0)

            if (
                record.equipment_id
                and record.equipment_id.tipo_maquina_id != "color"
            ):
                record.requiere_toner_cyan = False
                record.requiere_toner_magenta = False
                record.requiere_toner_yellow = False
                record.cantidad_solicitada_cyan = 0
                record.cantidad_solicitada_magenta = 0
                record.cantidad_solicitada_yellow = 0

    @api.onchange(
        "requiere_toner_black",
        "requiere_toner_cyan",
        "requiere_toner_magenta",
        "requiere_toner_yellow",
    )
    def _onchange_requested_toner_flags(self):
        for record in self:
            for color in self.COLOR_LABELS:
                boolean_field = record._color_boolean_field(color)
                quantity_field = record._requested_quantity_field(color)
                selected = bool(getattr(record, boolean_field))
                quantity = int(getattr(record, quantity_field, 0) or 0)

                if selected and quantity <= 0:
                    setattr(record, quantity_field, 1)
                elif not selected:
                    setattr(record, quantity_field, 0)

            if (
                record.equipment_id
                and record.equipment_id.tipo_maquina_id != "color"
            ):
                record.requiere_toner_cyan = False
                record.requiere_toner_magenta = False
                record.requiere_toner_yellow = False
                record.cantidad_solicitada_cyan = 0
                record.cantidad_solicitada_magenta = 0
                record.cantidad_solicitada_yellow = 0

    @api.onchange(
        "equipment_id",
        "counter_bn",
        "counter_color",
        "previous_counter_bn",
        "previous_counter_color",
        "requiere_toner_black",
        "requiere_toner_cyan",
        "requiere_toner_magenta",
        "requiere_toner_yellow",
        "cantidad_solicitada_black",
        "cantidad_solicitada_cyan",
        "cantidad_solicitada_magenta",
        "cantidad_solicitada_yellow",
    )
    def _onchange_manual_analysis(self):
        for record in self:
            if not record.equipment_id:
                continue

            requested = record._get_requested_toners_from_record()
            if not any(requested.values()):
                record.analysis_result = "manual_review"
                record.analysis_summary = False
                record.analysis_json = False
                record.requires_evidence = False
                record.duplicate_submission_id = False
                continue

            base_counters = {
                "bn": int(record.previous_counter_bn or 0),
                "color": int(record.previous_counter_color or 0),
            }

            validation = record.validate_web_toner_request(
                equipment_id=record.equipment_id.id,
                requested_toners=requested,
                current_counters=(
                    record._get_current_counters_from_record()
                ),
                exclude_submission_id=record._origin.id or False,
                base_counters=base_counters,
            )
            record._apply_validation_result(validation)

            if not validation.get("can_create"):
                return {
                    "warning": {
                        "title": _("Solicitud bloqueada"),
                        "message": validation.get("message"),
                    }
                }

            if validation.get("requires_evidence"):
                return {
                    "warning": {
                        "title": _("Consumo anticipado"),
                        "message": validation.get("message"),
                    }
                }

    # -------------------------------------------------------------------------
    # Create, restricciones y chatter
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        with self.env.cr.savepoint():
            current_user = self.env.user
            current_partner = current_user.partner_id

            for vals in vals_list:
                vals.setdefault("created_by_user_id", current_user.id)
                vals.setdefault("source", "manual")
                vals.setdefault("client_name", current_user.name or "")
                vals.setdefault(
                    "client_email",
                    current_user.email
                    or current_partner.email
                    or "soporte@andescopiers.com.pe",
                )
                vals.setdefault(
                    "client_phone",
                    current_partner.mobile
                    or current_partner.phone
                    or "",
                )

                if "counter_bn" not in vals or int(vals.get("counter_bn") or 0) <= 0:
                    raise ValidationError(_("Debe enviar el contador B/N actual de esta solicitud."))
                equipment = self.env["alquiler"].browse(vals.get("equipment_id")).exists()
                if equipment and equipment.tipo_maquina_id == "color":
                    if "counter_color" not in vals:
                        raise ValidationError(_("Debe enviar el contador color actual de esta solicitud."))
                    if int(vals.get("counter_color") or 0) <= 0:
                        raise ValidationError(_("El contador color debe ser mayor que cero."))
                # Respetar contadores anteriores ingresados manualmente.
                # Si hay historial entregado, el análisis posterior los
                # reemplazará por el contador actual de la última entrega.
                vals.setdefault("previous_counter_bn", 0)
                vals.setdefault("previous_counter_color", 0)
                vals["history_snapshot_json"] = False

                if vals.get("secuencia", "New") == "New":
                    vals["secuencia"] = (
                        self.env["ir.sequence"].next_by_code(
                            "toner.counter.submission"
                        )
                        or "TCS/001"
                    )
            records = super().create(vals_list)
            for record in records:
                record.with_context(toner_analysis_write=True).write({
                    "history_snapshot_json": record._capture_toner_history()})
                record._apply_validation_result(record._validate_record_for_workflow())
            for record in records:
                try:
                    record._create_chatter_note()
                    record.send_whatsapp_received()
                    record._notify_new_request_to_commercial()
                except Exception:
                    _logger.exception(
                        "[TONER] Error en notificación inicial solicitud=%s",
                        record.id,
                    )
            return records

    def write(self, vals):
        if self.env.context.get("toner_analysis_write"):
            return super().write(vals)
        vals = dict(vals)
        vals.pop("history_snapshot_json", None)
        # previous_counter_bn y previous_counter_color NO se eliminan.
        # Deben poder guardarse manualmente cuando no existe historial.
        triggers = {
            "equipment_id",
            "counter_bn",
            "counter_color",
            "previous_counter_bn",
            "previous_counter_color",
        }
        triggers.update("requiere_toner_" + c for c in self.COLOR_LABELS)
        triggers.update("cantidad_solicitada_" + c for c in self.COLOR_LABELS)
        if "equipment_id" in vals:
            for record in self:
                if vals["equipment_id"] != record.equipment_id.id:
                    if "counter_bn" not in vals or "counter_color" not in vals:
                        raise ValidationError(_("Al cambiar de equipo, registre sus contadores actuales."))
        result = super().write(vals)
        if triggers.intersection(vals):
            for record in self:
                if "equipment_id" in vals or not record.history_snapshot_json:
                    record.with_context(toner_analysis_write=True).write({
                        "history_snapshot_json": record._capture_toner_history()})
                record._apply_validation_result(record._validate_record_for_workflow())
        return result

    @api.constrains(
        "counter_bn",
        "counter_color",
        "previous_counter_bn",
        "previous_counter_color",
    )
    def _check_counters(self):
        for record in self:
            if any(getattr(record, name) < 0 for name in
                   ("counter_bn", "counter_color", "previous_counter_bn", "previous_counter_color")):
                raise ValidationError(_("Los contadores no pueden ser negativos."))

            if record.counter_bn <= 0:
                raise ValidationError(_("El contador B/N debe ser mayor que cero."))

            if (
                record.equipment_id
                and record.equipment_id.tipo_maquina_id == "color"
                and record.counter_color <= 0
            ):
                raise ValidationError(_("El contador color debe ser mayor que cero."))

            # La comparación contra el mayor contador conocido se realiza en
            # _validate_record_for_workflow para portal, formulario manual,
            # API e importación.

    @api.constrains(
        "cantidad_solicitada_black",
        "cantidad_solicitada_cyan",
        "cantidad_solicitada_magenta",
        "cantidad_solicitada_yellow",
        "cantidad_sugerida_black",
        "cantidad_sugerida_cyan",
        "cantidad_sugerida_magenta",
        "cantidad_sugerida_yellow",
        "cantidad_aprobada_black",
        "cantidad_aprobada_cyan",
        "cantidad_aprobada_magenta",
        "cantidad_aprobada_yellow",
    )
    def _check_quantities(self):
        for record in self:
            for field_name in [
                "cantidad_solicitada_black",
                "cantidad_solicitada_cyan",
                "cantidad_solicitada_magenta",
                "cantidad_solicitada_yellow",
                "cantidad_sugerida_black",
                "cantidad_sugerida_cyan",
                "cantidad_sugerida_magenta",
                "cantidad_sugerida_yellow",
                "cantidad_aprobada_black",
                "cantidad_aprobada_cyan",
                "cantidad_aprobada_magenta",
                "cantidad_aprobada_yellow",
            ]:
                if getattr(record, field_name) < 0:
                    raise ValidationError(_("Las cantidades no pueden ser negativas."))

    def _create_chatter_note(self):
        for record in self:
            colors = [
                self.COLOR_LABELS[color]
                for color in self.COLOR_LABELS
                if getattr(record, record._color_boolean_field(color))
            ]
            record.message_post(
                body=_(
                    """
                    <b>Nueva solicitud de tóner recibida</b><br/>
                    <b>Equipo:</b> %(equipment)s<br/>
                    <b>Serie:</b> %(serie)s<br/>
                    <b>Cliente:</b> %(client)s<br/>
                    <b>Solicitante:</b> %(reporter)s<br/>
                    <b>Tóner:</b> %(colors)s<br/>
                    <b>Contador B/N:</b> %(bn)s<br/>
                    <b>Contador color:</b> %(color)s<br/>
                    <b>Resultado automático:</b> %(analysis)s<br/>
                    <b>Requiere evidencia:</b> %(evidence)s<br/><br/>
                    <b>Análisis:</b><br/>%(summary)s
                    """
                )
                % {
                    "equipment": record.equipment_id.name.name
                    if record.equipment_id.name
                    else "Sin modelo",
                    "serie": record.equipment_id.serie or "Sin serie",
                    "client": record.partner_id.name
                    if record.partner_id
                    else "Sin cliente",
                    "reporter": record.client_name,
                    "colors": ", ".join(colors),
                    "bn": record.counter_bn,
                    "color": record.counter_color,
                    "analysis": dict(
                        record._fields["analysis_result"].selection
                    ).get(record.analysis_result),
                    "evidence": "Sí" if record.requires_evidence else "No",
                    "summary": (record.analysis_summary or "").replace("\n", "<br/>"),
                },
                message_type="notification",
            )

    def _create_internal_activity(self):
        self.ensure_one()
        try:
            group = self.env.ref("sales_team.group_sale_salesman", False)
            assignee = group.users[:1] if group and group.users else self.env.user
            user = assignee[0] if hasattr(assignee, "__len__") else assignee
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                date_deadline=fields.Date.today() + timedelta(days=1),
                summary=_("Evaluar solicitud de tóner %s") % self.secuencia,
                note=_(
                    "Revisar contadores, consumo, historial y evidencia antes de enviar a gerencia."
                ),
            )
        except Exception:
            _logger.exception(
                "[TONER] No se pudo crear actividad solicitud=%s",
                self.id,
            )


    # -------------------------------------------------------------------------
    # Correos XML, enlaces y decisión segura de gerencia
    # -------------------------------------------------------------------------

    def get_commercial_emails(self):
        self.ensure_one()
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "sat.toner_commercial_emails",
                "comercial01@andescopiers.com.pe,comercial@andescopiers.com.pe",
            )
        )

    def get_management_emails(self):
        self.ensure_one()
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "sat.toner_management_emails",
                "gerencia@corapsac.com",
            )
        )

    def get_dispatch_emails(self):
        self.ensure_one()
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "sat.toner_dispatch_emails",
                "comercial01@andescopiers.com.pe,comercial@andescopiers.com.pe",
            )
        )

    def _commercial_decision_field(self, color):
        return "decision_%s" % color

    def _commercial_reason_field(self, color):
        return "motivo_no_procede_%s" % color

    def _validate_commercial_color_decisions(self):
        """Valida únicamente los colores realmente solicitados."""
        self.ensure_one()
        errors = []
        for color, label in self.COLOR_LABELS.items():
            requested_qty = int(getattr(self, self._requested_quantity_field(color), 0) or 0)
            selected = bool(getattr(self, self._color_boolean_field(color), False) or requested_qty > 0)
            if not selected:
                continue

            decision_field = self._commercial_decision_field(color)
            reason_field = self._commercial_reason_field(color)
            suggested_field = self._suggested_quantity_field(color)
            decision = getattr(self, decision_field, False) or "pending"
            suggested_qty = int(getattr(self, suggested_field, 0) or 0)
            reason = (getattr(self, reason_field, False) or "").strip()

            if decision == "pending":
                errors.append(_("%(color)s: indique si procede o no procede.") % {"color": label})
            elif decision == "procede" and suggested_qty <= 0:
                errors.append(_("%(color)s: si procede, la cantidad propuesta debe ser mayor a cero.") % {"color": label})
            elif decision == "no_procede":
                if suggested_qty != 0:
                    setattr(self, suggested_field, 0)
                if not reason:
                    errors.append(_("%(color)s: indique el motivo de 'No procede'.") % {"color": label})

        if errors:
            raise UserError(_("Complete la evaluación comercial antes de enviar a gerencia:\n\n%s") % "\n".join("• %s" % e for e in errors))

    def _commercial_decision_label(self, color):
        self.ensure_one()
        value = getattr(self, self._commercial_decision_field(color), False) or "pending"
        return dict(self.COMMERCIAL_COLOR_DECISIONS).get(value, value)

    def get_requested_toner_email_lines(self):
        """
        Devuelve una línea por cada tóner solicitado.
        Usa el booleano o la cantidad para no omitir colores.
        """
        self.ensure_one()

        lines = []
        for color, label in self.COLOR_LABELS.items():
            boolean_field = self._color_boolean_field(color)
            requested_field = self._requested_quantity_field(color)
            suggested_field = self._suggested_quantity_field(color)
            approved_field = self._approved_quantity_field(color)

            requested_qty = int(
                getattr(self, requested_field, 0) or 0
            )
            selected = bool(
                getattr(self, boolean_field, False)
                or requested_qty > 0
            )

            if not selected:
                continue

            lines.append(
                {
                    "color": color,
                    "label": label,
                    "brand": getattr(self, "toner_brand_%s_id" % color).name or "",
                    "requested_qty": requested_qty,
                    "suggested_qty": int(
                        getattr(self, suggested_field, 0) or 0
                    ),
                    "decision": getattr(
                        self, self._commercial_decision_field(color), "pending"
                    ) or "pending",
                    "decision_label": self._commercial_decision_label(color),
                    "reason": getattr(
                        self, self._commercial_reason_field(color), False
                    ) or "",
                    "approved_qty": int(
                        getattr(self, approved_field, 0) or 0
                    ),
                }
            )

        return lines

    def get_toner_consumption_email_lines(self):
        """
        Devuelve el análisis separado por cada color solicitado.

        Para negro usa contador B/N.
        Para cian, magenta y amarillo usa contador color.
        """
        self.ensure_one()

        requested = self._get_requested_toners_from_record()
        current_counters = {
            "bn": int(self.counter_bn or 0),
            "color": int(self.counter_color or 0),
        }

        base_counters = {
            "bn": int(self.previous_counter_bn or 0),
            "color": int(self.previous_counter_color or 0),
        }

        lines = []
        for color, label in self.COLOR_LABELS.items():
            if not requested.get(color):
                continue

            saved = json.loads(self.analysis_json or "{}").get("colors", [])
            result = next((item for item in saved if item.get("color") == color), {})
            if not result:
                result = self._analyze_color(
                    self.equipment_id,
                    color,
                    current_counters,
                    exclude_submission_id=self.id,
                    base_counters=base_counters,
                )

            counter_key = "bn" if color == "black" else "color"
            lines.append(
                {
                    "color": color,
                    "label": label,
                    "counter_type": (
                        "B/N" if color == "black" else "Color"
                    ),
                    "base_counter": int(
                        result.get(
                            "base_counter",
                            self.previous_counter_bn
                            if color == "black"
                            else self.previous_counter_color,
                        )
                        or 0
                    ),
                    "current_counter": int(
                        result.get(
                            "current_counter",
                            current_counters[counter_key],
                        )
                        or 0
                    ),
                    "consumed_copies": int(
                        result.get("consumed_copies", 0) or 0
                    ),
                    "expected_yield": int(
                        result.get(
                            "expected_yield",
                            self._get_expected_yield(
                                self.equipment_id,
                                color,
                            ),
                        )
                        or 0
                    ),
                    "consumption_percent": float(
                        result.get("consumption_percent", 0.0)
                        or 0.0
                    ),
                    "days": int(
                        result.get(
                            "days_since_last_delivery",
                            0,
                        )
                        or 0
                    ),
                    "last_delivery_date": result.get(
                        "last_delivery_date"
                    )
                    or False,
                    "status": result.get("status")
                    or "manual_review",
                    "message": result.get("message") or "",
                    "requires_evidence": bool(
                        result.get("requires_evidence")
                    ),
                }
            )

        return lines

    def get_backend_record_url(self):
        self.ensure_one()
        base_url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("web.base.url", "")
            .rstrip("/")
        )
        if not base_url:
            return ""

        action = self.env.ref(
            "sat.action_toner_counter_submission",
            raise_if_not_found=False,
        )
        if action:
            return "%s/odoo/action-%s/%s" % (
                base_url,
                action.id,
                self.id,
            )

        return "%s/odoo/%s/%s" % (
            base_url,
            self._name,
            self.id,
        )

    def _generate_management_access_token(self):
        self.ensure_one()
        token_hours = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("sat.toner_management_token_hours", "72")
        )
        token = secrets.token_urlsafe(40)
        self.write(
            {
                "management_access_token": token,
                "management_token_expires_at": (
                    fields.Datetime.now()
                    + timedelta(hours=max(token_hours, 1))
                ),
                "management_token_used_at": False,
            }
        )
        return token

    def get_management_decision_url(self, decision):
        self.ensure_one()
        valid_decisions = {
            "approve",
            "request_information",
            "reject",
            "cancel",
        }
        if decision not in valid_decisions:
            return "#"

        base_url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("web.base.url", "")
            .rstrip("/")
        )
        if not base_url or not self.management_access_token:
            return "#"

        return "%s/toner/management/%s/%s" % (
            base_url,
            self.management_access_token,
            decision,
        )

    def _send_mail_template(self, xmlid, force_send=True):
        self.ensure_one()
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            _logger.error(
                "[TONER] Plantilla no encontrada xmlid=%s solicitud=%s",
                xmlid,
                self.id,
            )
            return False

        try:
            mail_id = template.sudo().send_mail(
                self.id,
                force_send=force_send,
                raise_exception=True,
            )
            _logger.info(
                "[TONER] Plantilla enviada xmlid=%s solicitud=%s mail_id=%s",
                xmlid,
                self.id,
                mail_id,
            )
            self.message_post(
                body=_("Correo enviado: %s") % template.name
            )
            return mail_id
        except Exception:
            _logger.exception(
                "[TONER] Error enviando plantilla xmlid=%s solicitud=%s",
                xmlid,
                self.id,
            )
            return False

    def _notify_new_request_to_commercial(self):
        for record in self:
            record._send_mail_template(
                "sat.mail_template_toner_new_request_commercial"
            )

    def _notify_management(self):
        for record in self:
            record._generate_management_access_token()
            record._send_mail_template(
                "sat.mail_template_toner_management_decision"
            )

    def _notify_commercial_management_result(self):
        self.ensure_one()
        template_by_decision = {
            "approved": "sat.mail_template_toner_management_approved_commercial",
            "information_requested": "sat.mail_template_toner_management_information_requested",
            "rejected": "sat.mail_template_toner_management_rejected_commercial",
            "cancelled": "sat.mail_template_toner_management_cancelled_commercial",
        }
        xmlid = template_by_decision.get(self.management_decision)
        if xmlid:
            self._send_mail_template(xmlid)

    def _notify_ready_for_dispatch(self):
        for record in self:
            record._send_mail_template(
                "sat.mail_template_toner_ready_for_dispatch"
            )

    def _ensure_management_token_valid(self, token):
        self.ensure_one()

        if not token or token != self.management_access_token:
            raise UserError(_("El enlace de decisión no es válido."))

        if self.management_token_used_at:
            raise UserError(_("Este enlace ya fue utilizado."))

        if (
            not self.management_token_expires_at
            or fields.Datetime.now() > self.management_token_expires_at
        ):
            raise UserError(_("El enlace de decisión venció."))

        if self.state != "pendiente_gerencia":
            raise UserError(
                _("La solicitud ya no está pendiente de gerencia.")
            )

    def register_management_decision(
        self,
        token,
        decision,
        decision_name,
        notes=False,
        remote_ip=False,
    ):
        self.ensure_one()
        self._ensure_management_token_valid(token)

        valid_decisions = {
            "approve",
            "request_information",
            "reject",
            "cancel",
        }
        if decision not in valid_decisions:
            raise UserError(_("La decisión no es válida."))

        decision_name = (decision_name or "").strip()
        notes = (notes or "").strip()

        if not decision_name:
            raise UserError(
                _("Ingrese el nombre de quien toma la decisión.")
            )

        if decision in {
            "request_information",
            "reject",
            "cancel",
        } and not notes:
            raise UserError(
                _("Debe indicar el motivo de la decisión.")
            )

        now = fields.Datetime.now()
        values = {
            "management_date": now,
            "management_notes": notes,
            "management_decision_name": decision_name,
            "management_decision_ip": remote_ip or False,
            "management_token_used_at": now,
        }

        if decision == "approve":
            approved_values = {}
            for color in self.COLOR_LABELS:
                approved_field = self._approved_quantity_field(color)
                suggested_field = self._suggested_quantity_field(color)
                approved_qty = int(
                    getattr(self, approved_field) or 0
                )
                suggested_qty = int(
                    getattr(self, suggested_field) or 0
                )
                approved_values[approved_field] = (
                    approved_qty
                    if approved_qty > 0
                    else suggested_qty
                )

            if not any(
                quantity > 0
                for quantity in approved_values.values()
            ):
                raise UserError(
                    _("No existe una cantidad sugerida para aprobar.")
                )

            values.update(approved_values)
            values.update(
                {
                    "management_decision": "approved",
                    "state": "confirmacion_ventas",
                }
            )
            message = _(
                "Gerencia aprobó la solicitud. "
                "Queda pendiente la confirmación de stock."
            )

        elif decision == "request_information":
            values.update(
                {
                    "management_decision": "information_requested",
                    "state": "devuelta",
                }
            )
            message = _(
                "Gerencia solicitó información adicional."
            )

        elif decision == "reject":
            values.update(
                {
                    "management_decision": "rejected",
                    "state": "rechazada_gerencia",
                }
            )
            message = _("Gerencia rechazó la solicitud.")

        else:
            values.update(
                {
                    "management_decision": "cancelled",
                    "state": "cancelada",
                }
            )
            message = _("Gerencia canceló la solicitud.")

        self.sudo().write(values)
        self.message_post(
            body=_(
                "%(message)s<br/>"
                "<b>Decidido por:</b> %(name)s<br/>"
                "<b>Observación:</b> %(notes)s"
            )
            % {
                "message": message,
                "name": decision_name,
                "notes": notes or _("Sin observaciones"),
            }
        )

        _logger.info(
            "[TONER] Decisión gerencia solicitud=%s decision=%s "
            "name=%s ip=%s",
            self.id,
            decision,
            decision_name,
            remote_ip,
        )

        self._notify_commercial_management_result()

        if decision == "approve":
            self.send_whatsapp_management_approved()
        elif decision == "reject":
            self.send_whatsapp_management_rejected()

        return True

    # -------------------------------------------------------------------------
    # Flujo interno
    # -------------------------------------------------------------------------

    def action_start_review(self):
        for record in self:
            if record.state not in ("recibida", "devuelta"):
                raise UserError(_("Solo se pueden evaluar solicitudes recibidas o devueltas."))

            validation = record._validate_record_for_workflow()
            record._apply_validation_result(validation)

            record.write(
                {
                    "analysis_result": record.analysis_result,
                    "analysis_summary": record.analysis_summary,
                    "analysis_json": record.analysis_json,
                    "requires_evidence": record.requires_evidence,
                    "duplicate_submission_id": record.duplicate_submission_id.id
                    if record.duplicate_submission_id
                    else False,
                    "last_delivery_date": record.last_delivery_date,
                    "days_since_last_delivery": record.days_since_last_delivery,
                    "expected_yield": record.expected_yield,
                    "consumed_copies": record.consumed_copies,
                    "consumption_percent": record.consumption_percent,
                    "previous_counter_bn": record.previous_counter_bn,
                    "previous_counter_color": record.previous_counter_color,
                    "cantidad_solicitada_black": record.cantidad_solicitada_black,
                    "cantidad_solicitada_cyan": record.cantidad_solicitada_cyan,
                    "cantidad_solicitada_magenta": record.cantidad_solicitada_magenta,
                    "cantidad_solicitada_yellow": record.cantidad_solicitada_yellow,
                    "cantidad_sugerida_black": record.cantidad_sugerida_black,
                    "cantidad_sugerida_cyan": record.cantidad_sugerida_cyan,
                    "cantidad_sugerida_magenta": record.cantidad_sugerida_magenta,
                    "cantidad_sugerida_yellow": record.cantidad_sugerida_yellow,
                    "state": "evaluacion",
                    "reviewer_id": self.env.user.id,
                    "review_date": fields.Datetime.now(),
                }
            )
            record.message_post(
                body=_("Evaluación iniciada por %s.") % self.env.user.name
            )

    def action_send_to_management(self):
        for record in self:
            if record.state != "evaluacion":
                raise UserError(_("La solicitud debe estar en evaluación."))
            if record.requires_evidence and not (
                record.photo_counter or record.photo_toner or record.early_request_reason
            ):
                raise UserError(
                    _(
                        "El consumo es anticipado. Registre el motivo o adjunte evidencia antes de enviarlo a gerencia."
                    )
                )

            # Comercial debe resolver cada color solicitado antes de que Gerencia vea la solicitud.
            record._validate_commercial_color_decisions()

            record.write({"state": "pendiente_gerencia"})
            record.message_post(
                body=_("Solicitud enviada a gerencia por %s.") % self.env.user.name
            )
            record._notify_management()

    def action_management_approve(self):
        for record in self:
            if record.state != "pendiente_gerencia":
                raise UserError(
                    _("La solicitud no está pendiente de gerencia.")
                )

            approved_values = {}
            for color in self.COLOR_LABELS:
                approved_field = record._approved_quantity_field(color)
                suggested_field = record._suggested_quantity_field(color)
                approved_qty = int(
                    getattr(record, approved_field) or 0
                )
                suggested_qty = int(
                    getattr(record, suggested_field) or 0
                )
                approved_values[approved_field] = (
                    approved_qty
                    if approved_qty > 0
                    else suggested_qty
                )

            if not any(
                quantity > 0
                for quantity in approved_values.values()
            ):
                raise UserError(
                    _("Gerencia debe aprobar al menos una cantidad.")
                )

            approved_values.update(
                {
                    "state": "confirmacion_ventas",
                    "management_decision": "approved",
                    "management_user_id": self.env.user.id,
                    "management_decision_name": self.env.user.name,
                    "management_date": fields.Datetime.now(),
                    "management_token_used_at": fields.Datetime.now(),
                }
            )
            record.write(approved_values)
            record.message_post(
                body=_(
                    "Solicitud aprobada por gerencia. "
                    "Queda pendiente la confirmación de stock."
                )
            )
            record._notify_commercial_management_result()
            record.send_whatsapp_management_approved()

    def action_management_reject(self):
        for record in self:
            if record.state != "pendiente_gerencia":
                raise UserError(
                    _("La solicitud no está pendiente de gerencia.")
                )
            if not record.management_notes:
                raise UserError(
                    _("Ingrese el motivo del rechazo.")
                )

            record.write(
                {
                    "state": "rechazada_gerencia",
                    "management_decision": "rejected",
                    "management_user_id": self.env.user.id,
                    "management_decision_name": self.env.user.name,
                    "management_date": fields.Datetime.now(),
                    "management_token_used_at": fields.Datetime.now(),
                }
            )
            record.message_post(
                body=_(
                    "Solicitud rechazada por gerencia: %s."
                )
                % self.env.user.name
            )
            record._notify_commercial_management_result()
            record.send_whatsapp_management_rejected()

    def action_return_for_correction(self):
        for record in self:
            if record.state != "pendiente_gerencia":
                raise UserError(
                    _("La solicitud no está pendiente de gerencia.")
                )
            if not record.management_notes:
                raise UserError(
                    _("Indique la información adicional requerida.")
                )

            record.write(
                {
                    "state": "devuelta",
                    "management_decision": "information_requested",
                    "management_user_id": self.env.user.id,
                    "management_decision_name": self.env.user.name,
                    "management_date": fields.Datetime.now(),
                    "management_token_used_at": fields.Datetime.now(),
                }
            )
            record.message_post(
                body=_("Gerencia solicitó información adicional.")
            )
            record._notify_commercial_management_result()

    def action_send_to_sales_confirmation(self):
        """Compatibilidad con solicitudes antiguas aprobadas."""
        for record in self:
            if record.state != "aprobada_gerencia":
                raise UserError(
                    _("La solicitud debe estar aprobada por gerencia.")
                )
            record.write({"state": "confirmacion_ventas"})
            record.message_post(
                body=_("Solicitud pendiente de confirmación de stock.")
            )

    def action_sales_confirm(self):
        for record in self:
            if record.state != "confirmacion_ventas":
                raise UserError(
                    _("La solicitud no está pendiente de confirmación de stock.")
                )

            if not any(
                getattr(
                    record,
                    record._approved_quantity_field(color),
                ) > 0
                for color in self.COLOR_LABELS
            ):
                raise UserError(
                    _("No existen cantidades aprobadas para confirmar.")
                )

            record.write(
                {
                    "state": "lista_despacho",
                    "stock_confirmed_by_id": self.env.user.id,
                    "stock_confirmation_date": fields.Datetime.now(),
                    "sales_user_id": self.env.user.id,
                    "sales_confirmation_date": fields.Datetime.now(),
                }
            )
            record.message_post(
                body=_(
                    "Stock confirmado por %s. "
                    "La solicitud está lista para despacho."
                )
                % self.env.user.name
            )
            record._notify_ready_for_dispatch()
            record.send_whatsapp_ready_for_dispatch()

    def action_create_dispatch(self):
        self.ensure_one()
        if self.state != "lista_despacho":
            raise UserError(_("La solicitud debe estar lista para despacho."))
        if self.delivery_scheduled_id:
            return self.action_view_delivery()

        delivery_values = {
            "equipment_id": self.equipment_id.id,
            "submission_id": self.id,
            "delivery_date_planned": fields.Date.today() + timedelta(days=1),
            "toner_black_qty": self.cantidad_aprobada_black,
            "toner_cyan_qty": self.cantidad_aprobada_cyan,
            "toner_magenta_qty": self.cantidad_aprobada_magenta,
            "toner_yellow_qty": self.cantidad_aprobada_yellow,
            "calculation_basis": "reporte_cliente",
            "priority": "alta" if self.requires_evidence else "normal",
            "notes": _(
                "Generado desde la solicitud %(sequence)s.\n%(notes)s"
            )
            % {
                "sequence": self.secuencia,
                "notes": self.sales_notes or "",
            },
        }
        brand_lines = []
        for color, label in self.COLOR_LABELS.items():
            if getattr(self, "cantidad_aprobada_%s" % color) > 0:
                brand = getattr(self, "toner_brand_%s_id" % color)
                brand_lines.append("%s: %s" % (label, brand.name or _("Sin marca indicada")))
        if brand_lines:
            delivery_values["notes"] += "\n" + _("Marcas de tóner a enviar:") + "\n" + "\n".join(brand_lines)
        delivery = self.env["toner.delivery.schedule"].sudo().create(
            delivery_values
        )
        self.write(
            {
                "delivery_scheduled_id": delivery.id,
                "state": "en_despacho",
            }
        )
        self.message_post(
            body=_("Proceso de despacho creado: %s.") % delivery.display_name
        )
        return self.action_view_delivery()

    def action_confirm_stock_and_prepare(self):
        """Un solo paso visible: confirma stock, crea el despacho y lo deja preparando.

        Reutiliza los métodos existentes para conservar chatter, correos y WhatsApp.
        """
        self.ensure_one()

        if self.state == "confirmacion_ventas":
            self.action_sales_confirm()

        if self.state == "lista_despacho":
            self.action_create_dispatch()

        delivery = self.delivery_scheduled_id
        if not delivery:
            raise UserError(_("No se pudo crear el despacho."))

        if delivery.state == "programado":
            delivery.action_confirm()
        if delivery.state == "confirmado":
            delivery.action_prepare()

        self.message_post(body=_("Stock confirmado y despacho enviado a preparación."))
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_prepare_dispatch(self):
        self.ensure_one()
        delivery = self.delivery_scheduled_id
        if not delivery:
            raise UserError(_("Primero debe existir un despacho."))
        if delivery.state == "programado":
            delivery.action_confirm()
        if delivery.state == "confirmado":
            delivery.action_prepare()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_send_dispatch(self):
        self.ensure_one()
        delivery = self.delivery_scheduled_id
        if not delivery:
            raise UserError(_("Primero debe existir un despacho."))
        if delivery.state != "preparando":
            raise UserError(_("El despacho debe estar en preparación antes de enviarlo."))
        # action_send conserva la notificación WhatsApp existente al cliente.
        delivery.action_send()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_register_delivery(self):
        """Abre la confirmación existente o crea la confirmación mediante la lógica actual."""
        self.ensure_one()
        delivery = self.delivery_scheduled_id
        if not delivery:
            raise UserError(_("Primero debe existir un despacho."))

        if delivery.confirmation_id:
            return delivery.action_view_confirmation()

        if delivery.state not in ("enviado", "preparando"):
            raise UserError(_("El despacho debe estar en preparación o enviado."))

        return delivery.action_deliver()

    def action_mark_delivered(self):
        for record in self:
            if (
                not record.delivery_scheduled_id
                or record.delivery_scheduled_id.state != "entregado"
            ):
                raise UserError(
                    _("Primero debe confirmarse la entrega en el proceso de despacho.")
                )
            record.write({"state": "entregada"})
            record._update_equipment_counters()
            record.message_post(body=_("Solicitud cerrada como entregada."))

    def action_cancel(self):
        for record in self:
            if record.state == "entregada":
                raise UserError(_("No se puede cancelar una solicitud entregada."))
            record.write({"state": "cancelada"})
            record.message_post(
                body=_("Solicitud cancelada por %s.") % self.env.user.name
            )

    def action_view_delivery(self):
        self.ensure_one()
        if not self.delivery_scheduled_id:
            raise UserError(_("No existe un despacho relacionado."))
        return {
            "name": _("Entrega de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.delivery.schedule",
            "view_mode": "form",
            "res_id": self.delivery_scheduled_id.id,
            "target": "current",
        }

    def _update_equipment_counters(self):
        """Actualiza el equipo sin retroceder contadores ni rejuvenecer lecturas.

        El contador de la solicitud corresponde a ``submission_date``. Si entre
        la solicitud y la entrega el equipo ya recibió una lectura mayor, esa
        lectura más reciente se conserva y el cierre de la entrega no la pisa.
        """
        for record in self:
            equipment = record.equipment_id
            request_bn = int(record.counter_bn or 0)
            request_color = int(record.counter_color or 0)

            if request_bn <= 0:
                raise ValidationError(_("El contador B/N debe ser mayor que cero."))
            if equipment.tipo_maquina_id == "color" and request_color <= 0:
                raise ValidationError(_("El contador color debe ser mayor que cero."))

            stored_bn = int(equipment.contador_bn or 0)
            stored_color = int(equipment.contador_color or 0)
            request_date = fields.Datetime.to_datetime(
                record.submission_date or fields.Datetime.now()
            )
            stored_date = fields.Datetime.to_datetime(
                equipment.fecha_ultima_actualizacion
            ) if equipment.fecha_ultima_actualizacion else False

            vals = {}
            counter_updated = False

            if request_bn >= stored_bn:
                vals["contador_bn"] = request_bn
                counter_updated = request_bn > stored_bn

            if equipment.tipo_maquina_id == "color" and request_color >= stored_color:
                vals["contador_color"] = request_color
                counter_updated = counter_updated or request_color > stored_color

            # La fecha solo avanza hasta la fecha real de la lectura de la
            # solicitud; nunca hasta la fecha posterior de entrega.
            if not stored_date or request_date > stored_date:
                vals["fecha_ultima_actualizacion"] = request_date

            if vals:
                equipment.write(vals)

            _logger.info(
                "[TONER] Cierre solicitud=%s equipo=%s request_bn=%s "
                "stored_bn=%s request_color=%s stored_color=%s "
                "fecha_solicitud=%s contador_actualizado=%s vals=%s",
                record.secuencia,
                equipment.id,
                request_bn,
                stored_bn,
                request_color if equipment.tipo_maquina_id == "color" else 0,
                stored_color if equipment.tipo_maquina_id == "color" else 0,
                request_date,
                counter_updated,
                vals,
            )

    # -------------------------------------------------------------------------
    # Notificaciones
    # -------------------------------------------------------------------------

    def _notify_management_legacy(self):
        for record in self:
            record._notify_management()

    def _send_internal_email(self, subject, title):
        """Método conservado por compatibilidad; los correos usan mail.template XML."""
        self.ensure_one()
        _logger.warning(
            "[TONER] _send_internal_email obsoleto solicitud=%s subject=%s title=%s",
            self.id,
            subject,
            title,
        )
        return False

    def send_whatsapp_received(self):
        for record in self:
            message = (
                "*🏢 Soporte*\n\n"
                "✅ *Solicitud de tóner recibida*\n\n"
                "Estimado/a %s,\n\n"
                "Registramos su solicitud con el número *%s*.\n"
                "Será evaluada por el área responsable. "
                "Este mensaje no autoriza todavía el despacho.\n\n"
                "🖨️ *Equipo:* %s\n"
                "🔢 *Serie:* %s\n"
            ) % (
                record.client_name,
                record.secuencia,
                record.equipment_id.name.name
                if record.equipment_id.name
                else "Sin modelo",
                record.equipment_id.serie or "Sin serie",
            )
            record.send_whatsapp_message(record.client_phone_clean, message)

    def send_whatsapp_management_approved(self):
        for record in self:
            message = (
                "*🏢 Soporte*\n\n"
                "✅ *Solicitud aprobada por gerencia*\n\n"
                "Su solicitud *%s* fue aprobada y regresó al área comercial "
                "para coordinar el despacho.\n"
            ) % record.secuencia
            record.send_whatsapp_message(record.client_phone_clean, message)

    def send_whatsapp_management_rejected(self):
        for record in self:
            message = (
                "*🏢 Soporte*\n\n"
                "❌ *Solicitud no aprobada*\n\n"
                "La solicitud *%s* no fue aprobada.\n"
                "Motivo: %s\n"
            ) % (
                record.secuencia,
                record.management_notes or "No especificado",
            )
            record.send_whatsapp_message(record.client_phone_clean, message)

    def send_whatsapp_ready_for_dispatch(self):
        for record in self:
            message = (
                "*🏢 Soporte*\n\n"
                "📦 *Pedido confirmado para preparación*\n\n"
                "La solicitud *%s* tiene stock confirmado y pasará al proceso de despacho.\n"
            ) % record.secuencia
            record.send_whatsapp_message(record.client_phone_clean, message)

    def send_whatsapp_message(self, phone, message):
        self.ensure_one()
        if not phone:
            _logger.warning(
                "[TONER] Sin teléfono para WhatsApp solicitud=%s",
                self.id,
            )
            return False

        parameters = self.env["ir.config_parameter"].sudo()
        base_url = parameters.get_param("sat.whatsapp_gateway_base_url")
        api_key = parameters.get_param("sat.whatsapp_gateway_api_key")

        if not base_url or not api_key:
            _logger.error(
                "[TONER] Configuración WhatsApp incompleta solicitud=%s",
                self.id,
            )
            return False

        try:
            response = requests.post(
                "%s/api/send-message" % base_url.rstrip("/"),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                },
                json={"to": phone, "message": message},
                timeout=30,
            )
            data = response.json()
            if response.status_code == 200 and data.get("success"):
                _logger.info(
                    "[TONER] WhatsApp enviado solicitud=%s teléfono=%s",
                    self.id,
                    phone,
                )
                return True

            _logger.error(
                "[TONER] Error WhatsApp solicitud=%s status=%s response=%s",
                self.id,
                response.status_code,
                response.text[:500],
            )
            return False
        except Exception:
            _logger.exception(
                "[TONER] Excepción WhatsApp solicitud=%s",
                self.id,
            )
            return False



class TonerBrand(models.Model):
    _name = "toner.brand"
    _description = "Marca de tóner"
    _order = "name, id"

    name = fields.Char(string="Marca", required=True, index=True)
    active = fields.Boolean(string="Activo", default=True)

    _sql_constraints = [
        ("name_unique", "unique(name)", "Esta marca de tóner ya existe."),
    ]
