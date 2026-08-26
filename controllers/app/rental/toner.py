# -*- coding: utf-8 -*-

"""
Tóner para Flutter - módulo Alquiler.

Endpoints de equipo:
    GET   /api/app/rentals/<id>/toner
    PATCH /api/app/rentals/<id>/toner/stock
    POST  /api/app/rentals/<id>/toner/install
    POST  /api/app/rentals/<id>/toner/reminder
    GET   /api/app/rentals/<id>/toner/model-config

Reportes / solicitudes:
    GET   /api/app/rentals/<id>/toner/reports
    GET   /api/app/rentals/<id>/toner/reports/<report_id>
    POST  /api/app/rentals/<id>/toner/reports/<report_id>/action

Entregas:
    GET   /api/app/rentals/<id>/toner/deliveries
    POST  /api/app/rentals/<id>/toner/deliveries
    GET   /api/app/rentals/<id>/toner/deliveries/<delivery_id>
    PATCH /api/app/rentals/<id>/toner/deliveries/<delivery_id>
    POST  /api/app/rentals/<id>/toner/deliveries/<delivery_id>/action

Dashboard:
    GET   /api/app/rentals/toner/dashboard

DISEÑO
======
El modelo `alquiler` todavía contiene varios botones temporales:
    action_view_toner_reports()
    action_view_toner_deliveries()
    action_create_manual_delivery()
    action_update_toner_stock()
    action_install_new_toner()

Esos métodos actualmente levantan UserError indicando "en desarrollo".

Sin embargo, la instalación ya contiene modelos reales:
    toner.counter.submission
    toner.delivery.schedule

Por ese motivo este controlador NO llama esos placeholders.
Trabaja directamente con los modelos reales cuando existen.

También mantiene compatibilidad defensiva con versiones antiguas y nuevas
del flujo de toner.counter.submission. No se permite ejecutar métodos
arbitrarios enviados por Flutter.

No se usa sudo para saltar ACL/record rules del usuario interno.
"""

import logging
from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .base import RentalBaseController


_logger = logging.getLogger(__name__)


class RentalTonerController(RentalBaseController):

    # ============================================================
    # MODELOS
    # ============================================================

    REPORT_MODEL = "toner.counter.submission"
    DELIVERY_MODEL = "toner.delivery.schedule"

    COLORS = (
        "black",
        "cyan",
        "magenta",
        "yellow",
    )

    COLOR_LABELS = {
        "black": "Negro",
        "cyan": "Cian",
        "magenta": "Magenta",
        "yellow": "Amarillo",
    }

    # ============================================================
    # ACCIONES DE REPORTES
    # ============================================================

    """
    Soporta el flujo nuevo y el flujo histórico.

    Flujo nuevo observado:
        recibida
        evaluacion
        pendiente_gerencia
        aprobada_gerencia
        confirmacion_ventas
        lista_despacho
        en_despacho
        entregada
        devuelta/cancelada según versión

    Flujo antiguo observado:
        pending
        reviewed
        approved
        processed
        rejected
    """

    REPORT_ACTION_METHODS = {
        # Flujo nuevo
        "start_review": (
            "action_start_review",
            "action_review",
        ),
        "send_management": (
            "action_send_to_management",
        ),
        "management_approve": (
            "action_management_approve",
        ),
        "management_reject": (
            "action_management_reject",
        ),
        "return_correction": (
            "action_return_for_correction",
        ),
        "send_sales_confirmation": (
            "action_send_to_sales_confirmation",
        ),
        "sales_confirm": (
            "action_sales_confirm",
        ),
        "create_dispatch": (
            "action_create_dispatch",
            "action_process_delivery",
        ),
        "mark_delivered": (
            "action_mark_delivered",
        ),
        "cancel": (
            "action_cancel",
            "action_reject",
        ),

        # Compatibilidad flujo antiguo
        "approve": (
            "action_approve",
        ),
        "process_delivery": (
            "action_process_delivery",
        ),
        "reject": (
            "action_reject",
        ),
        "reset_pending": (
            "action_reset_to_pending",
        ),
    }

    REPORT_DESTRUCTIVE_ACTIONS = {
        "management_approve",
        "management_reject",
        "return_correction",
        "sales_confirm",
        "create_dispatch",
        "mark_delivered",
        "cancel",
        "approve",
        "process_delivery",
        "reject",
        "reset_pending",
    }

    # ============================================================
    # ACCIONES DE ENTREGA
    # ============================================================

    DELIVERY_ACTION_METHODS = {
        "confirm": (
            "action_confirm",
        ),
        "prepare": (
            "action_prepare",
        ),
        "send": (
            "action_send",
        ),
        "deliver": (
            "action_deliver",
        ),
        "reschedule": (
            "action_reschedule",
        ),
        "cancel": (
            "action_cancel",
        ),
        "duplicate": (
            "action_duplicate_delivery",
        ),
    }

    DELIVERY_DESTRUCTIVE_ACTIONS = {
        "confirm",
        "prepare",
        "send",
        "deliver",
        "reschedule",
        "cancel",
        "duplicate",
    }

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/rentals/toner/dashboard",
            "/api/app/rentals/<int:rental_id>/toner",
            "/api/app/rentals/<int:rental_id>/toner/stock",
            "/api/app/rentals/<int:rental_id>/toner/install",
            "/api/app/rentals/<int:rental_id>/toner/reminder",
            "/api/app/rentals/<int:rental_id>/toner/model-config",
            "/api/app/rentals/<int:rental_id>/toner/reports",
            "/api/app/rentals/<int:rental_id>/toner/reports/<int:report_id>",
            "/api/app/rentals/<int:rental_id>/toner/reports/<int:report_id>/action",
            "/api/app/rentals/<int:rental_id>/toner/deliveries",
            "/api/app/rentals/<int:rental_id>/toner/deliveries/<int:delivery_id>",
            "/api/app/rentals/<int:rental_id>/toner/deliveries/<int:delivery_id>/action",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def rental_toner_options(
        self,
        rental_id=None,
        report_id=None,
        delivery_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # JSON / BASIC HELPERS
    # ============================================================

    def _json_body(self):
        try:
            data = request.httprequest.get_json(
                silent=True
            )

            if isinstance(
                data,
                dict,
            ):
                return data
        except Exception:
            pass

        return {}

    def _truthy(
        self,
        value,
    ):
        if value is True:
            return True

        if value in (
            None,
            False,
            "",
        ):
            return False

        return (
            str(
                value
            )
            .strip()
            .lower()
            in (
                "1",
                "true",
                "yes",
                "si",
                "sí",
                "on",
                "confirm",
                "confirmed",
            )
        )

    def _model_available(
        self,
        model_name,
    ):
        try:
            request.env[
                model_name
            ]
            return True
        except Exception:
            return False

    def _report_model(self):
        if not self._model_available(
            self.REPORT_MODEL
        ):
            raise UserError(
                "El modelo de solicitudes/reportes de tóner "
                "no está disponible."
            )

        return request.env[
            self.REPORT_MODEL
        ]

    def _delivery_model(self):
        if not self._model_available(
            self.DELIVERY_MODEL
        ):
            raise UserError(
                "El modelo de entregas de tóner "
                "no está disponible."
            )

        return request.env[
            self.DELIVERY_MODEL
        ]

    # ============================================================
    # GENERIC SERIALIZATION
    # ============================================================

    def _serialize_value(
        self,
        record,
        field_name,
    ):
        if field_name not in record._fields:
            return False

        field = record._fields[
            field_name
        ]

        value = record[
            field_name
        ]

        field_type = getattr(
            field,
            "type",
            False,
        )

        if field_type == "many2one":
            return (
                self._many2one(
                    value
                )
                if value
                else False
            )

        if field_type in (
            "one2many",
            "many2many",
        ):
            return [
                self._many2one(
                    item
                )
                for item in value
            ]

        if field_type in (
            "date",
            "datetime",
        ):
            return self._safe_date_value(
                value
            )

        if field_type == "boolean":
            return bool(
                value
            )

        if field_type in (
            "integer",
            "float",
            "monetary",
        ):
            return value or 0

        return value or False

    def _generic_detail(
        self,
        record,
        *,
        exclude=None,
    ):
        exclude = set(
            exclude
            or []
        )

        exclude.update(
            {
                "__last_update",
                "message_ids",
                "message_follower_ids",
                "message_partner_ids",
                "activity_ids",
                "activity_exception_decoration",
                "activity_exception_icon",
                "activity_state",
                "activity_summary",
                "activity_type_icon",
                "activity_type_id",
                "activity_user_id",
                "has_message",
                "message_attachment_count",
                "message_has_error",
                "message_has_error_counter",
                "message_has_sms_error",
                "message_is_follower",
                "message_needaction",
                "message_needaction_counter",
            }
        )

        result = {}

        allowed_types = {
            "char",
            "text",
            "html",
            "boolean",
            "integer",
            "float",
            "monetary",
            "date",
            "datetime",
            "selection",
            "many2one",
        }

        for field_name, field in record._fields.items():
            if field_name in exclude:
                continue

            field_type = getattr(
                field,
                "type",
                False,
            )

            if field_type not in allowed_types:
                continue

            try:
                result[
                    field_name
                ] = self._serialize_value(
                    record,
                    field_name,
                )
            except Exception:
                continue

        return result

    # ============================================================
    # MODEL CONFIG
    # ============================================================

    def _model_toner_config(
        self,
        rental,
    ):
        model = self._field(
            rental,
            "name",
            False,
        )

        if not model:
            return False

        fields_map = {
            "toner_modelo_black": "model",
            "toner_codigo_parte_black": "part_code",
            "durabilidad_toner_black": "yield_pages",
            "stock_minimo_black": "minimum_stock",
        }

        result = {
            "id": model.id,
            "name": (
                model.display_name
                or model.name
                or ""
            ),
            "automatic_management": (
                bool(
                    model[
                        "gestionar_toner_automatico"
                    ]
                )
                if "gestionar_toner_automatico"
                in model._fields
                else False
            ),
            "delivery_days": (
                int(
                    model[
                        "tiempo_entrega_dias"
                    ]
                    or 0
                )
                if "tiempo_entrega_dias"
                in model._fields
                else 0
            ),
            "safety_margin_days": (
                int(
                    model[
                        "margen_seguridad_dias"
                    ]
                    or 0
                )
                if "margen_seguridad_dias"
                in model._fields
                else 0
            ),
            "colors": {},
        }

        for color in self.COLORS:
            color_data = {}

            dynamic = {
                "model": "toner_modelo_%s" % color,
                "part_code": "toner_codigo_parte_%s" % color,
                "yield_pages": "durabilidad_toner_%s" % color,
                "minimum_stock": "stock_minimo_%s" % color,
            }

            for key, field_name in dynamic.items():
                if field_name not in model._fields:
                    continue

                value = model[
                    field_name
                ]

                if getattr(
                    model._fields[
                        field_name
                    ],
                    "type",
                    False,
                ) == "many2one":
                    value = (
                        self._many2one(
                            value
                        )
                        if value
                        else False
                    )

                color_data[
                    key
                ] = value or 0 if key in (
                    "yield_pages",
                    "minimum_stock",
                ) else value or False

            result[
                "colors"
            ][
                color
            ] = color_data

        if "tiempo_total_prevencion" in model._fields:
            result[
                "prevention_days"
            ] = int(
                model.tiempo_total_prevencion
                or 0
            )

        if "toner_fuente_informacion" in model._fields:
            result[
                "information_source"
            ] = model.toner_fuente_informacion or False
            result[
                "information_source_label"
            ] = self._selection_label_safe(
                model,
                "toner_fuente_informacion",
            )

        if "toner_fecha_verificacion" in model._fields:
            result[
                "verification_date"
            ] = self._safe_date_value(
                model.toner_fecha_verificacion
            )

        return result

    # ============================================================
    # TONER DAYS ESTIMATE
    # ============================================================

    def _toner_days_remaining(
        self,
        rental,
    ):
        method = getattr(
            rental,
            "_calcular_dias_restantes_toner",
            None,
        )

        if not callable(
            method
        ):
            return False

        try:
            return int(
                method()
            )
        except Exception:
            _logger.exception(
                "No se pudieron calcular días restantes de tóner "
                "para alquiler %s.",
                rental.id,
            )
            return False

    # ============================================================
    # REAL COUNTS
    # ============================================================

    def _real_toner_counts(
        self,
        rental,
    ):
        reports = 0
        deliveries = 0

        if self._model_available(
            self.REPORT_MODEL
        ):
            Report = self._report_model()

            if "equipment_id" in Report._fields:
                try:
                    reports = Report.search_count(
                        [
                            (
                                "equipment_id",
                                "=",
                                rental.id,
                            )
                        ]
                    )
                except Exception:
                    reports = 0

        if self._model_available(
            self.DELIVERY_MODEL
        ):
            Delivery = self._delivery_model()

            if "equipment_id" in Delivery._fields:
                try:
                    deliveries = Delivery.search_count(
                        [
                            (
                                "equipment_id",
                                "=",
                                rental.id,
                            )
                        ]
                    )
                except Exception:
                    deliveries = 0

        return {
            "reports": reports,
            "deliveries": deliveries,
        }

    # ============================================================
    # EQUIPMENT TONER ACTIONS
    # ============================================================

    def _toner_actions(
        self,
        rental,
        user,
    ):
        can_write = bool(
            self._is_system_user(
                user
            )
            or self._rental_model_access(
                user
            )["write"]
        )

        rented = (
            self._safe_string(
                rental,
                "estado_alquiler_id",
            )
            == "alquilada"
        )

        has_client = bool(
            self._field(
                rental,
                "cliente_id",
                False,
            )
        )

        has_email = bool(
            self._safe_string(
                rental,
                "correo_",
            )
        )

        return {
            "edit_stock": can_write,
            "install_toner": can_write,
            "view_reports": (
                self._model_available(
                    self.REPORT_MODEL
                )
            ),
            "view_deliveries": (
                self._model_available(
                    self.DELIVERY_MODEL
                )
            ),
            "create_delivery": bool(
                can_write
                and rented
                and self._model_available(
                    self.DELIVERY_MODEL
                )
            ),
            "view_model_config": bool(
                self._field(
                    rental,
                    "name",
                    False,
                )
            ),
            "send_reminder": bool(
                can_write
                and has_client
                and has_email
                and self._method_exists(
                    rental,
                    "action_send_stock_reminder",
                )
            ),
            "calculate_days_remaining": bool(
                self._method_exists(
                    rental,
                    "_calcular_dias_restantes_toner",
                )
            ),
        }

    # ============================================================
    # EQUIPMENT TONER PAYLOAD
    # ============================================================

    def _toner_payload(
        self,
        rental,
        user,
    ):
        payload = self._serialize_rental_toner(
            rental
        )

        # Corrección explícita para instalación actual:
        # el modelo usa 'monocromatica' y 'color'.
        machine_type = self._safe_string(
            rental,
            "tipo_maquina_id",
        )

        payload[
            "machine_type"
        ] = machine_type

        payload[
            "is_color"
        ] = (
            machine_type == "color"
        )

        if machine_type != "color":
            payload[
                "colors"
            ] = {
                "black": payload.get(
                    "colors",
                    {},
                ).get(
                    "black",
                    self._serialize_toner_color(
                        rental,
                        "black",
                    ),
                )
            }

        payload[
            "real_counts"
        ] = self._real_toner_counts(
            rental
        )

        payload[
            "estimated_days_black"
        ] = self._toner_days_remaining(
            rental
        )

        payload[
            "model_config"
        ] = self._model_toner_config(
            rental
        )

        payload[
            "actions"
        ] = self._toner_actions(
            rental,
            user,
        )

        return payload

    # ============================================================
    # STOCK VALIDATION
    # ============================================================

    def _stock_field(
        self,
        color,
    ):
        return (
            "stock_cliente_toner_%s"
            % color
        )

    def _installed_field(
        self,
        color,
    ):
        return (
            "toner_%s_instalado"
            % color
        )

    def _install_date_field(
        self,
        color,
    ):
        return (
            "fecha_instalacion_toner_%s"
            % color
        )

    def _install_counter_field(
        self,
        color,
    ):
        return (
            "contador_instalacion_toner_%s"
            % color
        )

    def _normalize_stock(
        self,
        value,
        color,
    ):
        try:
            qty = int(
                value
            )
        except Exception:
            raise UserError(
                "El stock de tóner %s debe ser un número entero."
                % self.COLOR_LABELS[
                    color
                ]
            )

        if qty < 0:
            raise UserError(
                "El stock de tóner %s no puede ser negativo."
                % self.COLOR_LABELS[
                    color
                ]
            )

        if qty > 10000:
            raise UserError(
                "El stock indicado es demasiado alto."
            )

        return qty

    # ============================================================
    # REPORT ACCESS
    # ============================================================

    def _get_report(
        self,
        rental,
        report_id,
        *,
        require_write=False,
    ):
        Report = self._report_model()

        try:
            report = Report.browse(
                int(
                    report_id
                )
            ).exists()

            if not report:
                return Report.browse()

            if (
                "equipment_id"
                in report._fields
                and report.equipment_id
                and report.equipment_id.id
                != rental.id
            ):
                return Report.browse()

            if hasattr(
                report,
                "check_access",
            ):
                report.check_access(
                    "write"
                    if require_write
                    else "read"
                )

            return report

        except (
            AccessError,
            ValueError,
            TypeError,
        ):
            return Report.browse()

    # ============================================================
    # REPORT ACTION RESOLUTION
    # ============================================================

    def _resolve_report_action(
        self,
        report,
        action_key,
    ):
        candidates = self.REPORT_ACTION_METHODS.get(
            action_key,
            ()
        )

        for method_name in candidates:
            if callable(
                getattr(
                    report,
                    method_name,
                    None,
                )
            ):
                return method_name

        return False

    def _report_action_available_by_state(
        self,
        report,
        action_key,
    ):
        state = (
            report.state
            if "state" in report._fields
            else False
        )

        # Flujo moderno.
        new_rules = {
            "start_review": {
                "recibida",
                "devuelta",
            },
            "send_management": {
                "evaluacion",
            },
            "management_approve": {
                "pendiente_gerencia",
            },
            "management_reject": {
                "pendiente_gerencia",
            },
            "return_correction": {
                "pendiente_gerencia",
            },
            "send_sales_confirmation": {
                "aprobada_gerencia",
            },
            "sales_confirm": {
                "confirmacion_ventas",
            },
            "create_dispatch": {
                "lista_despacho",
            },
            "mark_delivered": {
                "en_despacho",
                "lista_despacho",
            },
        }

        if action_key in new_rules:
            return (
                state in new_rules[
                    action_key
                ]
            )

        if action_key == "cancel":
            return state not in (
                "entregada",
                "processed",
            )

        # Flujo histórico.
        old_rules = {
            "approve": {
                "pending",
                "reviewed",
            },
            "process_delivery": {
                "approved",
            },
            "reject": {
                "pending",
                "reviewed",
            },
            "reset_pending": {
                "reviewed",
                "approved",
                "rejected",
                "pending",
            },
        }

        if action_key in old_rules:
            return (
                state in old_rules[
                    action_key
                ]
            )

        return True

    def _report_actions(
        self,
        report,
        user,
    ):
        can_write = bool(
            self._is_system_user(
                user
            )
            or self._model_has_access(
                self.REPORT_MODEL,
                "write",
            )
        )

        result = {}

        for action_key in self.REPORT_ACTION_METHODS:
            method_name = self._resolve_report_action(
                report,
                action_key,
            )

            result[
                action_key
            ] = {
                "available": bool(
                    can_write
                    and method_name
                    and self._report_action_available_by_state(
                        report,
                        action_key,
                    )
                ),
                "method": method_name or False,
                "requires_confirmation": (
                    action_key
                    in self.REPORT_DESTRUCTIVE_ACTIONS
                ),
            }

        return result

    # ============================================================
    # REPORT SERIALIZER
    # ============================================================

    def _serialize_report(
        self,
        report,
        user,
        *,
        full=False,
    ):
        result = {
            "id": report.id,
            "display_name": (
                report.display_name
                or ""
            ),
        }

        common_fields = (
            "secuencia",
            "equipment_id",
            "partner_id",
            "submission_date",
            "source",
            "created_by_user_id",
            "client_name",
            "client_email",
            "client_phone",
            "state",
            "urgente",
            "requires_evidence",
            "requiere_entrega_automatica",
            "delivery_scheduled_id",

            "counter_bn",
            "counter_color",
            "counter_scan",
            "contador_bn",
            "contador_color",
            "copies_bn_period",
            "copies_color_period",
            "total_copies_period",

            "stock_reportado_black",
            "stock_reportado_cyan",
            "stock_reportado_magenta",
            "stock_reportado_yellow",
            "stock_total_black",
            "stock_total_cyan",
            "stock_total_magenta",
            "stock_total_yellow",

            "nivel_toner_black",
            "nivel_toner_cyan",
            "nivel_toner_magenta",
            "nivel_toner_yellow",

            "requiere_toner_black",
            "requiere_toner_cyan",
            "requiere_toner_magenta",
            "requiere_toner_yellow",

            "early_request_reason",
            "management_notes",
            "sales_notes",
            "dispatch_notes",
            "create_date",
            "write_date",
        )

        for field_name in common_fields:
            if field_name not in report._fields:
                continue

            result[
                field_name
            ] = self._serialize_value(
                report,
                field_name,
            )

        if "state" in report._fields:
            result[
                "state_label"
            ] = self._selection_label_safe(
                report,
                "state",
            )

        if full:
            result[
                "extra"
            ] = self._generic_detail(
                report,
                exclude=common_fields,
            )

        result[
            "actions"
        ] = self._report_actions(
            report,
            user,
        )

        return result

    # ============================================================
    # DELIVERY ACCESS
    # ============================================================

    def _get_delivery(
        self,
        rental,
        delivery_id,
        *,
        require_write=False,
    ):
        Delivery = self._delivery_model()

        try:
            delivery = Delivery.browse(
                int(
                    delivery_id
                )
            ).exists()

            if not delivery:
                return Delivery.browse()

            if (
                "equipment_id"
                in delivery._fields
                and delivery.equipment_id
                and delivery.equipment_id.id
                != rental.id
            ):
                return Delivery.browse()

            if hasattr(
                delivery,
                "check_access",
            ):
                delivery.check_access(
                    "write"
                    if require_write
                    else "read"
                )

            return delivery

        except (
            AccessError,
            ValueError,
            TypeError,
        ):
            return Delivery.browse()

    # ============================================================
    # DELIVERY ACTIONS
    # ============================================================

    def _resolve_delivery_action(
        self,
        delivery,
        action_key,
    ):
        candidates = (
            self.DELIVERY_ACTION_METHODS.get(
                action_key,
                ()
            )
        )

        for method_name in candidates:
            if callable(
                getattr(
                    delivery,
                    method_name,
                    None,
                )
            ):
                return method_name

        return False

    def _delivery_action_available_by_state(
        self,
        delivery,
        action_key,
    ):
        state = (
            delivery.state
            if "state" in delivery._fields
            else False
        )

        rules = {
            "confirm": {
                "programado",
            },
            "prepare": {
                "programado",
                "confirmado",
            },
            "send": {
                "preparando",
            },
            "deliver": {
                "enviado",
                "preparando",
            },
            "reschedule": {
                "programado",
                "confirmado",
                "preparando",
                "enviado",
                "reprogramado",
            },
            "cancel": {
                "programado",
                "confirmado",
                "preparando",
                "enviado",
                "reprogramado",
            },
            "duplicate": {
                "programado",
                "confirmado",
                "preparando",
                "enviado",
                "entregado",
                "reprogramado",
                "cancelado",
            },
        }

        allowed_states = rules.get(
            action_key
        )

        if not allowed_states:
            return True

        return state in allowed_states

    def _delivery_actions(
        self,
        delivery,
        user,
    ):
        can_write = bool(
            self._is_system_user(
                user
            )
            or self._model_has_access(
                self.DELIVERY_MODEL,
                "write",
            )
        )

        result = {}

        for action_key in self.DELIVERY_ACTION_METHODS:
            method_name = self._resolve_delivery_action(
                delivery,
                action_key,
            )

            result[
                action_key
            ] = {
                "available": bool(
                    can_write
                    and method_name
                    and self._delivery_action_available_by_state(
                        delivery,
                        action_key,
                    )
                ),
                "method": method_name or False,
                "requires_confirmation": (
                    action_key
                    in self.DELIVERY_DESTRUCTIVE_ACTIONS
                ),
            }

        return result

    # ============================================================
    # DELIVERY SERIALIZER
    # ============================================================

    def _serialize_delivery(
        self,
        delivery,
        user,
        *,
        full=False,
    ):
        result = {
            "id": delivery.id,
            "display_name": (
                delivery.display_name
                or ""
            ),
        }

        common_fields = (
            "secuencia",
            "equipment_id",
            "partner_id",
            "submission_id",
            "confirmation_id",

            "delivery_date_planned",
            "delivery_date_confirmed",
            "delivery_date_actual",
            "creation_date",

            "toner_black_qty",
            "toner_cyan_qty",
            "toner_magenta_qty",
            "toner_yellow_qty",
            "total_units",

            "calculation_basis",
            "state",
            "priority",
            "urgente",

            "responsible_id",
            "user_id",
            "delivery_address",
            "contact_person",
            "contact_phone",

            "notes",
            "tracking_number",
            "shipping_company",

            "days_until_delivery",
            "is_overdue",
            "delivery_status",

            "create_date",
            "write_date",
        )

        for field_name in common_fields:
            if field_name not in delivery._fields:
                continue

            result[
                field_name
            ] = self._serialize_value(
                delivery,
                field_name,
            )

        for selection_field in (
            "state",
            "priority",
            "calculation_basis",
            "delivery_status",
        ):
            if selection_field in delivery._fields:
                result[
                    "%s_label"
                    % selection_field
                ] = self._selection_label_safe(
                    delivery,
                    selection_field,
                )

        if full:
            result[
                "extra"
            ] = self._generic_detail(
                delivery,
                exclude=common_fields,
            )

        result[
            "actions"
        ] = self._delivery_actions(
            delivery,
            user,
        )

        return result

    # ============================================================
    # DELIVERY CREATE / UPDATE NORMALIZATION
    # ============================================================

    def _normalize_qty(
        self,
        value,
        label,
    ):
        try:
            qty = int(
                value
                or 0
            )
        except Exception:
            raise UserError(
                "%s debe ser un número entero."
                % label
            )

        if qty < 0:
            raise UserError(
                "%s no puede ser negativa."
                % label
            )

        return qty

    def _normalize_date(
        self,
        value,
        label,
    ):
        if value in (
            None,
            "",
            False,
        ):
            return False

        try:
            return fields.Date.to_date(
                value
            )
        except Exception:
            raise UserError(
                "%s no es válida."
                % label
            )

    def _normalize_selection_value(
        self,
        model_or_record,
        field_name,
        value,
        *,
        allow_false=False,
    ):
        if value in (
            None,
            "",
            False,
        ):
            if allow_false:
                return False

            raise UserError(
                "Debe seleccionar %s."
                % field_name
            )

        options = self._selection_options_safe(
            model_or_record,
            field_name,
        )

        allowed = {
            item[
                "value"
            ]
            for item in options
        }

        if (
            allowed
            and value not in allowed
        ):
            raise UserError(
                "El valor '%s' no es válido para %s."
                % (
                    value,
                    field_name,
                )
            )

        return value

    def _prepare_delivery_values(
        self,
        rental,
        data,
        *,
        creating=False,
    ):
        Delivery = self._delivery_model()

        values = {}

        if creating:
            values[
                "equipment_id"
            ] = rental.id

        quantity_fields = {
            "toner_black_qty": "Cantidad de tóner negro",
            "toner_cyan_qty": "Cantidad de tóner cian",
            "toner_magenta_qty": "Cantidad de tóner magenta",
            "toner_yellow_qty": "Cantidad de tóner amarillo",
        }

        for field_name, label in quantity_fields.items():
            if field_name in data:
                values[
                    field_name
                ] = self._normalize_qty(
                    data.get(
                        field_name
                    ),
                    label,
                )

        if (
            creating
            and not any(
                values.get(
                    field_name,
                    0,
                )
                for field_name
                in quantity_fields
            )
        ):
            raise UserError(
                "Debe indicar al menos un tóner para la entrega."
            )

        if (
            self._safe_string(
                rental,
                "tipo_maquina_id",
            )
            == "monocromatica"
        ):
            if any(
                values.get(
                    field_name,
                    0,
                )
                for field_name in (
                    "toner_cyan_qty",
                    "toner_magenta_qty",
                    "toner_yellow_qty",
                )
            ):
                raise UserError(
                    "No se pueden programar tóners de color "
                    "para una máquina monocromática."
                )

        if "delivery_date_planned" in data:
            values[
                "delivery_date_planned"
            ] = self._normalize_date(
                data.get(
                    "delivery_date_planned"
                ),
                "La fecha programada",
            )

        elif creating:
            model = self._field(
                rental,
                "name",
                False,
            )

            delivery_days = 2

            if (
                model
                and "tiempo_entrega_dias"
                in model._fields
            ):
                delivery_days = int(
                    model.tiempo_entrega_dias
                    or 2
                )

            values[
                "delivery_date_planned"
            ] = (
                fields.Date.today()
                + timedelta(
                    days=delivery_days
                )
            )

        if "delivery_date_confirmed" in data:
            values[
                "delivery_date_confirmed"
            ] = self._normalize_date(
                data.get(
                    "delivery_date_confirmed"
                ),
                "La fecha confirmada",
            )

        if "calculation_basis" in data:
            values[
                "calculation_basis"
            ] = self._normalize_selection_value(
                Delivery,
                "calculation_basis",
                data.get(
                    "calculation_basis"
                ),
                allow_false=True,
            )

        elif (
            creating
            and "calculation_basis"
            in Delivery._fields
        ):
            options = {
                item["value"]
                for item in self._selection_options_safe(
                    Delivery,
                    "calculation_basis",
                )
            }

            if "manual" in options:
                values[
                    "calculation_basis"
                ] = "manual"

        if "priority" in data:
            values[
                "priority"
            ] = self._normalize_selection_value(
                Delivery,
                "priority",
                data.get(
                    "priority"
                ),
                allow_false=True,
            )

        for field_name in (
            "notes",
            "delivery_address",
            "contact_person",
            "contact_phone",
            "tracking_number",
            "shipping_company",
        ):
            if (
                field_name in data
                and field_name
                in Delivery._fields
            ):
                value = data.get(
                    field_name
                )

                values[
                    field_name
                ] = (
                    str(
                        value
                    ).strip()
                    if value
                    else False
                )

        return values

    # ============================================================
    # GET TONER
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/toner",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_get(
        self,
        rental_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
            )

            if not rental:
                return self._rental_not_found_response()

            return self._json_response(
                {
                    "success": True,
                    "toner": self._toner_payload(
                        rental,
                        user,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando tóner alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # STOCK UPDATE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/toner/stock",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_stock_update(
        self,
        rental_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
                require_write=True,
            )

            if not rental:
                return self._rental_not_found_response()

            write_error = (
                self._require_rental_write_access(
                    rental,
                    user,
                )
            )

            if write_error:
                return write_error

            data = self._json_body()

            stock = data.get(
                "stock"
            )

            if isinstance(
                stock,
                dict,
            ):
                data = stock

            values = {}

            for color in self.COLORS:
                if color not in data:
                    continue

                if (
                    color != "black"
                    and self._safe_string(
                        rental,
                        "tipo_maquina_id",
                    )
                    != "color"
                ):
                    raise UserError(
                        "La máquina no admite tóner %s."
                        % self.COLOR_LABELS[
                            color
                        ]
                    )

                field_name = self._stock_field(
                    color
                )

                if field_name not in rental._fields:
                    continue

                values[
                    field_name
                ] = self._normalize_stock(
                    data.get(
                        color
                    ),
                    color,
                )

            if not values:
                raise UserError(
                    "No se recibió ningún stock válido."
                )

            rental.write(
                values
            )

            rental.invalidate_recordset()

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s actualizó "
                    "el stock de tóner del cliente (%s)."
                    % (
                        user.name,
                        ", ".join(
                            sorted(
                                values.keys()
                            )
                        ),
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Stock de tóner actualizado."
                    ),
                    "changed_fields": sorted(
                        values.keys()
                    ),
                    "toner": self._toner_payload(
                        rental,
                        user,
                    ),
                    "rental": (
                        self._serialize_rental_detail(
                            rental,
                            user,
                        )
                    ),
                }
            )

        except (
            UserError,
            ValidationError,
            AccessError,
        ) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_TONER_STOCK_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error actualizando stock tóner alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # INSTALL TONER
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/toner/install",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_install(
        self,
        rental_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
                require_write=True,
            )

            if not rental:
                return self._rental_not_found_response()

            write_error = (
                self._require_rental_write_access(
                    rental,
                    user,
                )
            )

            if write_error:
                return write_error

            data = self._json_body()

            color = str(
                data.get(
                    "color"
                )
                or ""
            ).strip().lower()

            if color not in self.COLORS:
                raise UserError(
                    "Debe indicar un color de tóner válido."
                )

            if (
                color != "black"
                and self._safe_string(
                    rental,
                    "tipo_maquina_id",
                )
                != "color"
            ):
                raise UserError(
                    "La máquina es monocromática."
                )

            if not self._truthy(
                data.get(
                    "confirmed"
                )
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "CONFIRMATION_REQUIRED",
                        "message": (
                            "¿Confirmar la instalación de un tóner %s?"
                            % self.COLOR_LABELS[
                                color
                            ]
                        ),
                        "requires_confirmation": True,
                        "color": color,
                    },
                    status=409,
                )

            stock_field = self._stock_field(
                color
            )

            installed_field = self._installed_field(
                color
            )

            date_field = self._install_date_field(
                color
            )

            counter_field = self._install_counter_field(
                color
            )

            required_fields = (
                stock_field,
                installed_field,
                date_field,
                counter_field,
            )

            missing_fields = [
                field_name
                for field_name in required_fields
                if field_name
                not in rental._fields
            ]

            if missing_fields:
                raise UserError(
                    "El modelo no tiene todos los campos "
                    "necesarios para registrar la instalación."
                )

            consume_client_stock = self._truthy(
                data.get(
                    "consume_client_stock",
                    True,
                )
            )

            current_stock = int(
                rental[
                    stock_field
                ]
                or 0
            )

            if (
                consume_client_stock
                and current_stock <= 0
            ):
                raise UserError(
                    "El cliente no tiene stock disponible "
                    "de tóner %s."
                    % self.COLOR_LABELS[
                        color
                    ]
                )

            if color == "black":
                current_counter = (
                    self._safe_int(
                        rental,
                        "contador_actual_black",
                    )
                    or self._safe_int(
                        rental,
                        "contador_bn",
                    )
                )
            else:
                current_counter = (
                    self._safe_int(
                        rental,
                        "contador_actual_color",
                    )
                    or self._safe_int(
                        rental,
                        "contador_color",
                    )
                )

            values = {
                installed_field: True,
                date_field: fields.Date.today(),
                counter_field: current_counter,
            }

            if consume_client_stock:
                values[
                    stock_field
                ] = (
                    current_stock
                    - 1
                )

            rental.write(
                values
            )

            rental.invalidate_recordset()

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s registró instalación "
                    "de tóner %s. Contador: %s%s."
                    % (
                        user.name,
                        self.COLOR_LABELS[
                            color
                        ],
                        current_counter,
                        (
                            " | Se descontó 1 unidad del stock del cliente"
                            if consume_client_stock
                            else ""
                        ),
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Instalación de tóner registrada."
                    ),
                    "color": color,
                    "counter": current_counter,
                    "consumed_client_stock": consume_client_stock,
                    "toner": self._toner_payload(
                        rental,
                        user,
                    ),
                    "rental": (
                        self._serialize_rental_detail(
                            rental,
                            user,
                        )
                    ),
                }
            )

        except (
            UserError,
            ValidationError,
            AccessError,
        ) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_TONER_INSTALL_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error instalando tóner alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # REMINDER
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/toner/reminder",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_reminder(
        self,
        rental_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
                require_write=True,
            )

            if not rental:
                return self._rental_not_found_response()

            write_error = (
                self._require_rental_write_access(
                    rental,
                    user,
                )
            )

            if write_error:
                return write_error

            if not self._method_exists(
                rental,
                "action_send_stock_reminder",
            ):
                raise UserError(
                    "El recordatorio de stock no está disponible."
                )

            if not self._field(
                rental,
                "cliente_id",
                False,
            ):
                raise UserError(
                    "La máquina no tiene cliente asignado."
                )

            if not self._safe_string(
                rental,
                "correo_",
            ):
                raise UserError(
                    "La máquina no tiene correo configurado."
                )

            data = self._json_body()

            if not self._truthy(
                data.get(
                    "confirmed"
                )
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "CONFIRMATION_REQUIRED",
                        "message": (
                            "¿Registrar el recordatorio de stock "
                            "para %s?"
                            % self._safe_string(
                                rental,
                                "correo_",
                            )
                        ),
                        "requires_confirmation": True,
                    },
                    status=409,
                )

            result = rental.action_send_stock_reminder()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Recordatorio de stock registrado."
                    ),
                    "email": self._safe_string(
                        rental,
                        "correo_",
                    ),
                    "model_result": bool(
                        result
                    ),
                    "toner": self._toner_payload(
                        rental,
                        user,
                    ),
                }
            )

        except (
            UserError,
            ValidationError,
            AccessError,
        ) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_TONER_REMINDER_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error recordatorio tóner alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # MODEL CONFIG ENDPOINT
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/toner/model-config",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_model_config(
        self,
        rental_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
            )

            if not rental:
                return self._rental_not_found_response()

            config = self._model_toner_config(
                rental
            )

            if not config:
                return self._json_response(
                    {
                        "success": False,
                        "code": "TONER_MODEL_CONFIG_NOT_FOUND",
                        "message": (
                            "La máquina no tiene un modelo configurado."
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "config": config,
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error configuración modelo tóner alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # REPORT LIST
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/toner/reports",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_reports(
        self,
        rental_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
            )

            if not rental:
                return self._rental_not_found_response()

            Report = self._report_model()

            domain = [
                (
                    "equipment_id",
                    "=",
                    rental.id,
                )
            ]

            state = self._query_arg(
                "state",
                "",
            )

            if (
                state
                and "state"
                in Report._fields
            ):
                allowed = {
                    item["value"]
                    for item
                    in self._selection_options_safe(
                        Report,
                        "state",
                    )
                }

                if (
                    not allowed
                    or state in allowed
                ):
                    domain.append(
                        (
                            "state",
                            "=",
                            state,
                        )
                    )

            limit = self._positive_int(
                self._query_arg(
                    "limit",
                    100,
                ),
                100,
                minimum=1,
                maximum=500,
            )

            order = (
                "submission_date desc, id desc"
                if "submission_date"
                in Report._fields
                else "id desc"
            )

            reports = Report.search(
                domain,
                order=order,
                limit=limit,
            )

            return self._json_response(
                {
                    "success": True,
                    "count": len(
                        reports
                    ),
                    "items": [
                        self._serialize_report(
                            report,
                            user,
                        )
                        for report in reports
                    ],
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error listando reportes tóner alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # REPORT DETAIL
    # ============================================================

    @http.route(
        (
            "/api/app/rentals/<int:rental_id>"
            "/toner/reports/<int:report_id>"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_report_detail(
        self,
        rental_id,
        report_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
            )

            if not rental:
                return self._rental_not_found_response()

            report = self._get_report(
                rental,
                report_id,
            )

            if not report:
                return self._json_response(
                    {
                        "success": False,
                        "code": "TONER_REPORT_NOT_FOUND",
                        "message": (
                            "El reporte no existe o no pertenece "
                            "a esta máquina."
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "report": self._serialize_report(
                        report,
                        user,
                        full=True,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error detalle reporte tóner rental=%s report=%s.",
                rental_id,
                report_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # REPORT ACTION
    # ============================================================

    @http.route(
        (
            "/api/app/rentals/<int:rental_id>"
            "/toner/reports/<int:report_id>/action"
        ),
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_report_action(
        self,
        rental_id,
        report_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
                require_write=True,
            )

            if not rental:
                return self._rental_not_found_response()

            report = self._get_report(
                rental,
                report_id,
                require_write=True,
            )

            if not report:
                return self._json_response(
                    {
                        "success": False,
                        "code": "TONER_REPORT_NOT_FOUND",
                        "message": (
                            "El reporte no existe o no pertenece "
                            "a esta máquina."
                        ),
                    },
                    status=404,
                )

            data = self._json_body()

            action_key = str(
                data.get(
                    "action"
                )
                or ""
            ).strip()

            if action_key not in self.REPORT_ACTION_METHODS:
                raise UserError(
                    "La acción de reporte no está permitida."
                )

            method_name = self._resolve_report_action(
                report,
                action_key,
            )

            if not method_name:
                return self._json_response(
                    {
                        "success": False,
                        "code": "TONER_REPORT_ACTION_UNAVAILABLE",
                        "message": (
                            "La acción no existe en la versión actual "
                            "del modelo de solicitudes de tóner."
                        ),
                        "action": action_key,
                    },
                    status=501,
                )

            actions = self._report_actions(
                report,
                user,
            )

            if not actions[
                action_key
            ][
                "available"
            ]:
                return self._json_response(
                    {
                        "success": False,
                        "code": "TONER_REPORT_ACTION_NOT_ALLOWED",
                        "message": (
                            "La acción no está disponible "
                            "para el estado actual."
                        ),
                        "action": action_key,
                    },
                    status=409,
                )

            if (
                action_key
                in self.REPORT_DESTRUCTIVE_ACTIONS
                and not self._truthy(
                    data.get(
                        "confirmed"
                    )
                )
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "CONFIRMATION_REQUIRED",
                        "message": (
                            "¿Confirmar la acción '%s' "
                            "sobre esta solicitud de tóner?"
                            % action_key
                        ),
                        "requires_confirmation": True,
                        "action": action_key,
                    },
                    status=409,
                )

            method = getattr(
                report,
                method_name
            )

            result = method()

            report.invalidate_recordset()
            rental.invalidate_recordset()

            delivery = False

            if (
                "delivery_scheduled_id"
                in report._fields
                and report.delivery_scheduled_id
            ):
                delivery = report.delivery_scheduled_id

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s ejecutó '%s' "
                    "en solicitud de tóner %s."
                    % (
                        user.name,
                        action_key,
                        report.id,
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Acción de solicitud de tóner ejecutada."
                    ),
                    "action": action_key,
                    "report": self._serialize_report(
                        report,
                        user,
                        full=True,
                    ),
                    "delivery": (
                        self._serialize_delivery(
                            delivery,
                            user,
                            full=True,
                        )
                        if delivery
                        else False
                    ),
                    "toner": self._toner_payload(
                        rental,
                        user,
                    ),
                    "model_result": bool(
                        result
                    ),
                }
            )

        except (
            UserError,
            ValidationError,
            AccessError,
        ) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_TONER_REPORT_ACTION_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error acción reporte tóner rental=%s report=%s.",
                rental_id,
                report_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # DELIVERY LIST / CREATE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/toner/deliveries",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_deliveries(
        self,
        rental_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
            )

            if not rental:
                return self._rental_not_found_response()

            Delivery = self._delivery_model()

            domain = [
                (
                    "equipment_id",
                    "=",
                    rental.id,
                )
            ]

            state = self._query_arg(
                "state",
                "",
            )

            if (
                state
                and "state"
                in Delivery._fields
            ):
                allowed = {
                    item["value"]
                    for item
                    in self._selection_options_safe(
                        Delivery,
                        "state",
                    )
                }

                if (
                    not allowed
                    or state in allowed
                ):
                    domain.append(
                        (
                            "state",
                            "=",
                            state,
                        )
                    )

            limit = self._positive_int(
                self._query_arg(
                    "limit",
                    100,
                ),
                100,
                minimum=1,
                maximum=500,
            )

            order = (
                "delivery_date_planned desc, id desc"
                if "delivery_date_planned"
                in Delivery._fields
                else "id desc"
            )

            deliveries = Delivery.search(
                domain,
                order=order,
                limit=limit,
            )

            return self._json_response(
                {
                    "success": True,
                    "count": len(
                        deliveries
                    ),
                    "items": [
                        self._serialize_delivery(
                            delivery,
                            user,
                        )
                        for delivery in deliveries
                    ],
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error listando entregas tóner alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    @http.route(
        "/api/app/rentals/<int:rental_id>/toner/deliveries",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_delivery_create(
        self,
        rental_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
                require_write=True,
            )

            if not rental:
                return self._rental_not_found_response()

            write_error = (
                self._require_rental_write_access(
                    rental,
                    user,
                )
            )

            if write_error:
                return write_error

            if (
                self._safe_string(
                    rental,
                    "estado_alquiler_id",
                )
                != "alquilada"
            ):
                raise UserError(
                    "Solo se pueden programar entregas "
                    "para equipos alquilados."
                )

            Delivery = self._delivery_model()

            if not self._model_has_access(
                self.DELIVERY_MODEL,
                "create",
            ) and not self._is_system_user(
                user
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "TONER_DELIVERY_CREATE_DENIED",
                        "message": (
                            "No tienes permiso para crear entregas de tóner."
                        ),
                    },
                    status=403,
                )

            data = self._json_body()

            values = self._prepare_delivery_values(
                rental,
                data,
                creating=True,
            )

            delivery = Delivery.create(
                values
            )

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s creó entrega "
                    "de tóner %s."
                    % (
                        user.name,
                        (
                            delivery.secuencia
                            if "secuencia"
                            in delivery._fields
                            else delivery.id
                        ),
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Entrega de tóner creada."
                    ),
                    "delivery": self._serialize_delivery(
                        delivery,
                        user,
                        full=True,
                    ),
                    "toner": self._toner_payload(
                        rental,
                        user,
                    ),
                },
                status=201,
            )

        except (
            UserError,
            ValidationError,
            AccessError,
        ) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_TONER_DELIVERY_CREATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error creando entrega tóner alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # DELIVERY DETAIL
    # ============================================================

    @http.route(
        (
            "/api/app/rentals/<int:rental_id>"
            "/toner/deliveries/<int:delivery_id>"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_delivery_detail(
        self,
        rental_id,
        delivery_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
            )

            if not rental:
                return self._rental_not_found_response()

            delivery = self._get_delivery(
                rental,
                delivery_id,
            )

            if not delivery:
                return self._json_response(
                    {
                        "success": False,
                        "code": "TONER_DELIVERY_NOT_FOUND",
                        "message": (
                            "La entrega no existe o no pertenece "
                            "a esta máquina."
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "delivery": self._serialize_delivery(
                        delivery,
                        user,
                        full=True,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error detalle entrega tóner rental=%s delivery=%s.",
                rental_id,
                delivery_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # DELIVERY UPDATE
    # ============================================================

    @http.route(
        (
            "/api/app/rentals/<int:rental_id>"
            "/toner/deliveries/<int:delivery_id>"
        ),
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_delivery_update(
        self,
        rental_id,
        delivery_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
                require_write=True,
            )

            if not rental:
                return self._rental_not_found_response()

            delivery = self._get_delivery(
                rental,
                delivery_id,
                require_write=True,
            )

            if not delivery:
                return self._json_response(
                    {
                        "success": False,
                        "code": "TONER_DELIVERY_NOT_FOUND",
                        "message": (
                            "La entrega no existe o no pertenece "
                            "a esta máquina."
                        ),
                    },
                    status=404,
                )

            state = (
                delivery.state
                if "state"
                in delivery._fields
                else False
            )

            if state in (
                "entregado",
                "cancelado",
            ):
                raise UserError(
                    "No se puede modificar una entrega "
                    "entregada o cancelada."
                )

            data = self._json_body()

            if (
                "values"
                in data
                and isinstance(
                    data[
                        "values"
                    ],
                    dict,
                )
            ):
                data = data[
                    "values"
                ]

            values = self._prepare_delivery_values(
                rental,
                data,
                creating=False,
            )

            if not values:
                raise UserError(
                    "No se recibieron cambios válidos."
                )

            delivery.write(
                values
            )

            delivery.invalidate_recordset()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Entrega de tóner actualizada."
                    ),
                    "changed_fields": sorted(
                        values.keys()
                    ),
                    "delivery": self._serialize_delivery(
                        delivery,
                        user,
                        full=True,
                    ),
                }
            )

        except (
            UserError,
            ValidationError,
            AccessError,
        ) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_TONER_DELIVERY_UPDATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error actualizando entrega tóner rental=%s delivery=%s.",
                rental_id,
                delivery_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # DELIVERY ACTION
    # ============================================================

    @http.route(
        (
            "/api/app/rentals/<int:rental_id>"
            "/toner/deliveries/<int:delivery_id>/action"
        ),
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_delivery_action(
        self,
        rental_id,
        delivery_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
                require_write=True,
            )

            if not rental:
                return self._rental_not_found_response()

            delivery = self._get_delivery(
                rental,
                delivery_id,
                require_write=True,
            )

            if not delivery:
                return self._json_response(
                    {
                        "success": False,
                        "code": "TONER_DELIVERY_NOT_FOUND",
                        "message": (
                            "La entrega no existe o no pertenece "
                            "a esta máquina."
                        ),
                    },
                    status=404,
                )

            data = self._json_body()

            action_key = str(
                data.get(
                    "action"
                )
                or ""
            ).strip()

            if action_key not in self.DELIVERY_ACTION_METHODS:
                raise UserError(
                    "La acción de entrega no está permitida."
                )

            method_name = self._resolve_delivery_action(
                delivery,
                action_key,
            )

            if not method_name:
                return self._json_response(
                    {
                        "success": False,
                        "code": "TONER_DELIVERY_ACTION_UNAVAILABLE",
                        "message": (
                            "La acción no está implementada "
                            "en la versión actual."
                        ),
                        "action": action_key,
                    },
                    status=501,
                )

            actions = self._delivery_actions(
                delivery,
                user,
            )

            if not actions[
                action_key
            ][
                "available"
            ]:
                return self._json_response(
                    {
                        "success": False,
                        "code": "TONER_DELIVERY_ACTION_NOT_ALLOWED",
                        "message": (
                            "La acción no está disponible "
                            "para el estado actual."
                        ),
                        "action": action_key,
                    },
                    status=409,
                )

            if (
                action_key
                in self.DELIVERY_DESTRUCTIVE_ACTIONS
                and not self._truthy(
                    data.get(
                        "confirmed"
                    )
                )
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "CONFIRMATION_REQUIRED",
                        "message": (
                            "¿Confirmar la acción '%s' "
                            "sobre esta entrega de tóner?"
                            % action_key
                        ),
                        "requires_confirmation": True,
                        "action": action_key,
                    },
                    status=409,
                )

            method = getattr(
                delivery,
                method_name
            )

            result = method()

            delivery.invalidate_recordset()
            rental.invalidate_recordset()

            related_delivery = False

            if (
                isinstance(
                    result,
                    dict,
                )
                and result.get(
                    "res_model"
                )
                == self.DELIVERY_MODEL
                and result.get(
                    "res_id"
                )
            ):
                related_delivery = self._get_delivery(
                    rental,
                    result[
                        "res_id"
                    ],
                )

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s ejecutó '%s' "
                    "en entrega de tóner %s."
                    % (
                        user.name,
                        action_key,
                        delivery.id,
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Acción de entrega ejecutada."
                    ),
                    "action": action_key,
                    "delivery": self._serialize_delivery(
                        delivery,
                        user,
                        full=True,
                    ),
                    "related_delivery": (
                        self._serialize_delivery(
                            related_delivery,
                            user,
                            full=True,
                        )
                        if related_delivery
                        and related_delivery.id
                        != delivery.id
                        else False
                    ),
                    "toner": self._toner_payload(
                        rental,
                        user,
                    ),
                }
            )

        except (
            UserError,
            ValidationError,
            AccessError,
        ) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_TONER_DELIVERY_ACTION_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error acción entrega tóner rental=%s delivery=%s.",
                rental_id,
                delivery_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # DASHBOARD
    # ============================================================

    @http.route(
        "/api/app/rentals/toner/dashboard",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_toner_dashboard(
        self,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            Rental = self._rental_model()

            base_domain = []

            if "estado_alquiler_id" in Rental._fields:
                base_domain.append(
                    (
                        "estado_alquiler_id",
                        "=",
                        "alquilada",
                    )
                )

            total_rented = Rental.search_count(
                base_domain
            )

            critical = 0
            low = 0
            automatic = 0

            if "estado_stock_toner" in Rental._fields:
                critical = Rental.search_count(
                    base_domain
                    + [
                        (
                            "estado_stock_toner",
                            "=",
                            "critico",
                        )
                    ]
                )

                low = Rental.search_count(
                    base_domain
                    + [
                        (
                            "estado_stock_toner",
                            "=",
                            "bajo",
                        )
                    ]
                )

            if (
                "name"
                in Rental._fields
                and self._field_exists(
                    Rental,
                    "name",
                )
            ):
                try:
                    automatic = Rental.search_count(
                        base_domain
                        + [
                            (
                                "name.gestionar_toner_automatico",
                                "=",
                                True,
                            )
                        ]
                    )
                except Exception:
                    automatic = 0

            pending_reports = 0
            report_states = []

            if self._model_available(
                self.REPORT_MODEL
            ):
                Report = self._report_model()

                if "state" in Report._fields:
                    report_states = (
                        self._selection_options_safe(
                            Report,
                            "state",
                        )
                    )

                    available_values = {
                        item["value"]
                        for item in report_states
                    }

                    open_candidates = [
                        "recibida",
                        "evaluacion",
                        "pendiente_gerencia",
                        "aprobada_gerencia",
                        "confirmacion_ventas",
                        "lista_despacho",
                        "en_despacho",
                        "pending",
                        "reviewed",
                        "approved",
                    ]

                    open_values = [
                        value
                        for value in open_candidates
                        if value
                        in available_values
                    ]

                    if open_values:
                        pending_reports = Report.search_count(
                            [
                                (
                                    "state",
                                    "in",
                                    open_values,
                                )
                            ]
                        )

            pending_deliveries = 0
            overdue_deliveries = 0
            delivery_states = []

            if self._model_available(
                self.DELIVERY_MODEL
            ):
                Delivery = self._delivery_model()

                if "state" in Delivery._fields:
                    delivery_states = (
                        self._selection_options_safe(
                            Delivery,
                            "state",
                        )
                    )

                    pending_deliveries = Delivery.search_count(
                        [
                            (
                                "state",
                                "in",
                                [
                                    "programado",
                                    "confirmado",
                                    "preparando",
                                    "enviado",
                                    "reprogramado",
                                ],
                            )
                        ]
                    )

                if "is_overdue" in Delivery._fields:
                    overdue_deliveries = (
                        Delivery.search_count(
                            [
                                (
                                    "is_overdue",
                                    "=",
                                    True,
                                )
                            ]
                        )
                    )

            return self._json_response(
                {
                    "success": True,
                    "dashboard": {
                        "total_rented": total_rented,
                        "critical_stock": critical,
                        "low_stock": low,
                        "automatic_management": automatic,
                        "pending_reports": pending_reports,
                        "pending_deliveries": pending_deliveries,
                        "overdue_deliveries": overdue_deliveries,
                    },
                    "options": {
                        "report_states": report_states,
                        "delivery_states": delivery_states,
                        "delivery_priorities": (
                            self._selection_options_safe(
                                self._delivery_model(),
                                "priority",
                            )
                            if self._model_available(
                                self.DELIVERY_MODEL
                            )
                            else []
                        ),
                        "delivery_basis": (
                            self._selection_options_safe(
                                self._delivery_model(),
                                "calculation_basis",
                            )
                            if self._model_available(
                                self.DELIVERY_MODEL
                            )
                            else []
                        ),
                    },
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando dashboard de tóner."
            )

            return self._error_response(
                exc
            )
