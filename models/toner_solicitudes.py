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
            "En solicitudes del portal se obtiene del historial. "
            "En solicitudes manuales puede ingresarse directamente."
        ),
    )

    previous_counter_color = fields.Integer(
        string="Contador color anterior",
        default=0,
        tracking=True,
        help=(
            "En solicitudes del portal se obtiene del historial. "
            "En solicitudes manuales puede ingresarse directamente."
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
    )
    def _compute_period_copies(self):
        for record in self:
            record.copies_bn_period = max(
                0, (record.counter_bn or 0) - (record.previous_counter_bn or 0)
            )
            record.copies_color_period = max(
                0, (record.counter_color or 0) - (record.previous_counter_color or 0)
            )
            record.total_copies_period = (
                record.copies_bn_period + record.copies_color_period
            )

    # -------------------------------------------------------------------------
    # Utilidades
    # -------------------------------------------------------------------------

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
        return self.env["toner.delivery.schedule"].sudo().search(
            [
                ("equipment_id", "=", equipment_id),
                ("state", "=", "entregado"),
                (quantity_field, ">", 0),
            ],
            order="delivery_date_actual desc, id desc",
            limit=1,
        )

    @api.model
    def _analyze_color(
        self,
        equipment,
        color,
        current_counters,
        exclude_submission_id=False,
        base_counters=None,
    ):
        duplicate = self._find_open_duplicate(
            equipment.id,
            color,
            exclude_submission_id=exclude_submission_id,
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
                )
                % self.COLOR_LABELS[color],
            }

        expected_yield = self._get_expected_yield(
            equipment,
            color,
        )
        counter_key = "bn" if color == "black" else "color"
        current_counter = int(
            current_counters.get(counter_key, 0) or 0
        )

        # En una solicitud manual, el usuario puede indicar expresamente
        # el contador anterior que servirá como base del análisis.
        if base_counters is not None and counter_key in base_counters:
            base_counter = int(
                base_counters.get(counter_key, 0) or 0
            )

            if base_counter < 0:
                return {
                    "color": color,
                    "label": self.COLOR_LABELS[color],
                    "status": "invalid_counter",
                    "can_create": False,
                    "expected_yield": expected_yield,
                    "base_counter": base_counter,
                    "current_counter": current_counter,
                    "message": _(
                        "El contador anterior no puede ser negativo."
                    ),
                }

            if current_counter < base_counter:
                return {
                    "color": color,
                    "label": self.COLOR_LABELS[color],
                    "status": "invalid_counter",
                    "can_create": False,
                    "expected_yield": expected_yield,
                    "base_counter": base_counter,
                    "current_counter": current_counter,
                    "message": _(
                        "El contador actual no puede ser menor "
                        "al contador anterior ingresado."
                    ),
                }

            consumed = current_counter - base_counter
            percentage = (
                (consumed / expected_yield) * 100
                if expected_yield
                else 0.0
            )
            threshold = float(
                self.env["ir.config_parameter"]
                .sudo()
                .get_param(
                    "sat.toner_early_consumption_percent",
                    "50",
                )
            )
            requires_evidence = percentage < threshold

            return {
                "color": color,
                "label": self.COLOR_LABELS[color],
                "status": (
                    "early_consumption"
                    if requires_evidence
                    else "normal"
                ),
                "can_create": True,
                "requires_evidence": requires_evidence,
                "manual_base": True,
                "last_delivery_id": False,
                "last_delivery_date": False,
                "days_since_last_delivery": 0,
                "base_counter": base_counter,
                "current_counter": current_counter,
                "expected_yield": expected_yield,
                "consumed_copies": consumed,
                "consumption_percent": round(
                    percentage,
                    2,
                ),
                "message": (
                    _(
                        "Análisis con contador anterior manual: "
                        "%(consumed)s de %(yield)s copias "
                        "(%(percent).2f%%). Requiere revisión "
                        "y evidencia."
                    )
                    % {
                        "consumed": consumed,
                        "yield": expected_yield,
                        "percent": percentage,
                    }
                    if requires_evidence
                    else _(
                        "Análisis con contador anterior manual: "
                        "%(consumed)s de %(yield)s copias "
                        "(%(percent).2f%%)."
                    )
                    % {
                        "consumed": consumed,
                        "yield": expected_yield,
                        "percent": percentage,
                    }
                ),
            }

        last_delivery = self._find_last_delivered_schedule(
            equipment.id,
            color,
        )

        if not last_delivery:
            return {
                "color": color,
                "label": self.COLOR_LABELS[color],
                "status": "no_history",
                "can_create": True,
                "requires_evidence": False,
                "expected_yield": expected_yield,
                "consumed_copies": 0,
                "consumption_percent": 0.0,
                "message": _(
                    "No existe una entrega anterior confirmada "
                    "para comparar."
                ),
            }

        base_submission = last_delivery.submission_id
        if color == "black":
            base_counter = int(
                base_submission.counter_bn
                if base_submission
                else equipment.contador_bn or 0
            )
        else:
            base_counter = int(
                base_submission.counter_color
                if base_submission
                else equipment.contador_color or 0
            )

        if current_counter < base_counter:
            return {
                "color": color,
                "label": self.COLOR_LABELS[color],
                "status": "invalid_counter",
                "can_create": False,
                "expected_yield": expected_yield,
                "base_counter": base_counter,
                "current_counter": current_counter,
                "message": _(
                    "El contador actual no puede ser menor "
                    "al contador de la última entrega."
                ),
            }

        consumed = current_counter - base_counter
        percentage = (
            (consumed / expected_yield) * 100
            if expected_yield
            else 0.0
        )

        delivery_datetime = (
            fields.Datetime.to_datetime(
                last_delivery.delivery_date_actual
            )
            if last_delivery.delivery_date_actual
            else fields.Datetime.to_datetime(
                last_delivery.creation_date
            )
        )
        days = 0
        if delivery_datetime:
            days = max(
                0,
                (
                    fields.Datetime.now()
                    - delivery_datetime
                ).days,
            )

        threshold = float(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "sat.toner_early_consumption_percent",
                "50",
            )
        )
        requires_evidence = percentage < threshold

        return {
            "color": color,
            "label": self.COLOR_LABELS[color],
            "status": (
                "early_consumption"
                if requires_evidence
                else "normal"
            ),
            "can_create": True,
            "requires_evidence": requires_evidence,
            "last_delivery_id": last_delivery.id,
            "last_delivery_date": (
                fields.Datetime.to_string(
                    delivery_datetime
                )
                if delivery_datetime
                else False
            ),
            "days_since_last_delivery": days,
            "base_counter": base_counter,
            "current_counter": current_counter,
            "expected_yield": expected_yield,
            "consumed_copies": consumed,
            "consumption_percent": round(
                percentage,
                2,
            ),
            "message": (
                _(
                    "Consumo anticipado: %(consumed)s de "
                    "%(yield)s copias (%(percent).2f%%). "
                    "Requiere revisión y evidencia."
                )
                % {
                    "consumed": consumed,
                    "yield": expected_yield,
                    "percent": percentage,
                }
                if requires_evidence
                else _(
                    "Consumo razonable: %(consumed)s de "
                    "%(yield)s copias (%(percent).2f%%)."
                )
                % {
                    "consumed": consumed,
                    "yield": expected_yield,
                    "percent": percentage,
                }
            ),
        }

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
                equipment.contador_bn or 0,
            )
            or 0
        )
        counter_color = int(
            current_counters.get(
                "color",
                equipment.contador_color or 0,
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
            equipment = self.env["alquiler"].sudo().browse(
                int(web_data["equipment_id"])
            ).exists()
            if not equipment:
                return {"success": False, "error": _("Equipo no encontrado.")}

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
                "previous_counter_bn": int(
                    first_with_history.get("base_counter", equipment.contador_bn or 0)
                    if most_restrictive.get("color") == "black"
                    else equipment.contador_bn or 0
                ),
                "previous_counter_color": int(
                    first_with_history.get("base_counter", equipment.contador_color or 0)
                    if most_restrictive.get("color") != "black"
                    else equipment.contador_color or 0
                ),
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

        if self.source != "manual":
            if primary.get("color") == "black":
                self.previous_counter_bn = int(
                    primary.get(
                        "base_counter",
                        self.counter_bn or 0,
                    )
                    or 0
                )
            elif primary.get("color"):
                self.previous_counter_color = int(
                    primary.get(
                        "base_counter",
                        self.counter_color or 0,
                    )
                    or 0
                )

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

        base_counters = (
            {
                "bn": int(self.previous_counter_bn or 0),
                "color": int(
                    self.previous_counter_color or 0
                ),
            }
            if self.source == "manual"
            else None
        )

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

            record.counter_bn = int(record.equipment_id.contador_bn or 0)
            record.counter_color = int(
                record.equipment_id.contador_color or 0
            )

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

            base_counters = (
                {
                    "bn": int(
                        record.previous_counter_bn or 0
                    ),
                    "color": int(
                        record.previous_counter_color or 0
                    ),
                }
                if record.source == "manual"
                else None
            )

            validation = record.validate_web_toner_request(
                equipment_id=record.equipment_id.id,
                requested_toners=requested,
                current_counters=(
                    record._get_current_counters_from_record()
                ),
                exclude_submission_id=record.id or False,
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

            equipment_id = vals.get("equipment_id")
            if equipment_id:
                equipment = self.env["alquiler"].sudo().browse(
                    int(equipment_id)
                ).exists()
                if equipment:
                    vals.setdefault("counter_bn", int(equipment.contador_bn or 0))
                    vals.setdefault(
                        "counter_color",
                        int(equipment.contador_color or 0)
                        if equipment.tipo_maquina_id == "color"
                        else 0,
                    )

            if vals.get("secuencia", "New") == "New":
                vals["secuencia"] = (
                    self.env["ir.sequence"].next_by_code(
                        "toner.counter.submission"
                    )
                    or "TCS/001"
                )
        records = super().create(vals_list)
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

    @api.constrains(
        "counter_bn",
        "counter_color",
        "previous_counter_bn",
        "previous_counter_color",
    )
    def _check_counters(self):
        for record in self:
            if (
                record.counter_bn < 0
                or record.counter_color < 0
                or record.previous_counter_bn < 0
                or record.previous_counter_color < 0
            ):
                raise ValidationError(
                    _("Los contadores no pueden ser negativos.")
                )

            if (
                record.previous_counter_bn
                and record.counter_bn
                and record.counter_bn
                < record.previous_counter_bn
            ):
                raise ValidationError(
                    _(
                        "El contador B/N actual no puede ser "
                        "menor al contador B/N anterior."
                    )
                )

            if (
                record.tipo_maquina_id == "color"
                and record.previous_counter_color
                and record.counter_color
                and record.counter_color
                < record.previous_counter_color
            ):
                raise ValidationError(
                    _(
                        "El contador color actual no puede ser "
                        "menor al contador color anterior."
                    )
                )

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
                    "requested_qty": requested_qty,
                    "suggested_qty": int(
                        getattr(self, suggested_field, 0) or 0
                    ),
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

        base_counters = None
        if self.source == "manual":
            base_counters = {
                "bn": int(self.previous_counter_bn or 0),
                "color": int(self.previous_counter_color or 0),
            }

        lines = []
        for color, label in self.COLOR_LABELS.items():
            if not requested.get(color):
                continue

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
        for record in self:
            record.equipment_id.write(
                {
                    "contador_bn": record.counter_bn,
                    "contador_color": record.counter_color,
                    "fecha_ultima_actualizacion": fields.Datetime.now(),
                }
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