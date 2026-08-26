# -*- coding: utf-8 -*-

"""
Relaciones operativas de Alquiler para Flutter.

Endpoints:
    GET  /api/app/rentals/<id>/related

Tickets:
    GET  /api/app/rentals/<id>/related/tickets
    POST /api/app/rentals/<id>/related/tickets
    GET  /api/app/rentals/<id>/related/tickets/<ticket_id>

Pedidos:
    GET  /api/app/rentals/<id>/related/orders
    POST /api/app/rentals/<id>/related/orders
    GET  /api/app/rentals/<id>/related/orders/<order_id>

Repuestos:
    GET  /api/app/rentals/<id>/related/spares

Solicitudes de partes:
    GET  /api/app/rentals/<id>/related/parts
    POST /api/app/rentals/<id>/related/parts
    GET  /api/app/rentals/<id>/related/parts/<request_id>

Partes retiradas:
    GET  /api/app/rentals/<id>/related/removed-parts

Contadores:
    GET  /api/app/rentals/<id>/related/counters

OBJETIVO
========
Este controlador concentra todas las relaciones de una máquina `alquiler`
sin duplicar la lógica de negocio de los modelos relacionados.

Se reutilizan, cuando corresponde, los métodos reales del modelo:
    get_ticket()
    create_ticket()
    get_pedidos()
    create_sale_order()
    get_repuestos()
    action_view_partes()
    action_solicitar_partes()
    action_open_contadores()

IMPORTANTE
==========
- La creación de ticket usa `alquiler.create_ticket()` para copiar cliente,
  dirección, contacto, celular, correo y product_alquiler exactamente como
  lo hace Odoo.
- La creación de pedido usa `alquiler.create_sale_order()`.
- Las solicitudes de partes se crean directamente en `solicitud.partes`
  solo con campos reales y permitidos; no se ejecutan aprobaciones desde
  este controlador.
- Las acciones avanzadas de tickets permanecen en service.py.
- No se permite ejecutar métodos arbitrarios enviados desde Flutter.
- No se eliminan registros desde esta API.
"""

import logging

from odoo import fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .base import RentalBaseController


_logger = logging.getLogger(__name__)


class RentalRelatedController(RentalBaseController):

    # ============================================================
    # MODELOS
    # ============================================================

    TICKET_MODEL = "ticket.alquiler"
    ORDER_MODEL = "sale.order"
    SPARE_MODEL = "repuestos.alquiler"
    PART_REQUEST_MODEL = "solicitud.partes"
    PART_LINE_MODEL = "solicitud.partes.linea"
    REMOVED_PART_MODEL = "solicitud.parte.tecnico.linea"
    COUNTER_MODEL = "contador.automatico"

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/rentals/<int:rental_id>/related",
            "/api/app/rentals/<int:rental_id>/related/tickets",
            "/api/app/rentals/<int:rental_id>/related/tickets/<int:ticket_id>",
            "/api/app/rentals/<int:rental_id>/related/orders",
            "/api/app/rentals/<int:rental_id>/related/orders/<int:order_id>",
            "/api/app/rentals/<int:rental_id>/related/spares",
            "/api/app/rentals/<int:rental_id>/related/parts",
            "/api/app/rentals/<int:rental_id>/related/parts/<int:request_id>",
            "/api/app/rentals/<int:rental_id>/related/removed-parts",
            "/api/app/rentals/<int:rental_id>/related/counters",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def rental_related_options(
        self,
        rental_id=None,
        ticket_id=None,
        order_id=None,
        request_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # HELPERS
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

    def _model(
        self,
        model_name,
        label,
    ):
        if not self._model_available(
            model_name
        ):
            raise UserError(
                "%s no está disponible en esta instalación."
                % label
            )

        return request.env[
            model_name
        ]

    def _safe_limit(
        self,
        default=100,
        maximum=500,
    ):
        return self._positive_int(
            self._query_arg(
                "limit",
                default,
            ),
            default,
            minimum=1,
            maximum=maximum,
        )

    # ============================================================
    # SERIALIZACIÓN GENÉRICA
    # ============================================================

    def _serialize_field(
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

    def _serialize_extra(
        self,
        record,
        *,
        exclude=None,
    ):
        excluded = set(
            exclude
            or []
        )

        excluded.update(
            {
                "__last_update",
                "message_ids",
                "message_follower_ids",
                "message_partner_ids",
                "activity_ids",
                "activity_state",
                "activity_summary",
                "activity_type_id",
                "activity_user_id",
                "message_needaction",
                "message_needaction_counter",
                "message_has_error",
                "message_has_error_counter",
            }
        )

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

        result = {}

        for field_name, field in record._fields.items():
            if (
                field_name in excluded
                or field_name.startswith(
                    "message_"
                )
                or field_name.startswith(
                    "activity_"
                )
            ):
                continue

            if getattr(
                field,
                "type",
                False,
            ) not in allowed_types:
                continue

            try:
                result[
                    field_name
                ] = self._serialize_field(
                    record,
                    field_name,
                )

                if getattr(
                    field,
                    "type",
                    False,
                ) == "selection":
                    result[
                        "%s_label"
                        % field_name
                    ] = self._selection_label_safe(
                        record,
                        field_name,
                    )
            except Exception:
                continue

        return result

    # ============================================================
    # RECORD ACCESS
    # ============================================================

    def _get_related_record(
        self,
        model_name,
        record_id,
        *,
        domain,
        require_write=False,
    ):
        Model = request.env[
            model_name
        ]

        try:
            record = Model.browse(
                int(
                    record_id
                )
            ).exists()

            if not record:
                return Model.browse()

            if not Model.search_count(
                [
                    (
                        "id",
                        "=",
                        record.id,
                    )
                ]
                + list(
                    domain
                )
            ):
                return Model.browse()

            if hasattr(
                record,
                "check_access",
            ):
                record.check_access(
                    "write"
                    if require_write
                    else "read"
                )

            return record

        except (
            AccessError,
            ValueError,
            TypeError,
        ):
            return Model.browse()

    # ============================================================
    # TICKET SERIALIZER
    # ============================================================

    def _serialize_ticket(
        self,
        ticket,
        *,
        full=False,
    ):
        fields_to_show = (
            "name",
            "partner_id",
            "product_alquiler",
            "responsable",
            "responsable_id",
            "tecnico_asignado",
            "tipo_servicio_id",
            "estado",
            "estado_id",
            "state",
            "direccion_id_r",
            "contacto_id_r",
            "celular_id_r",
            "corre_id_r",
            "fecha_visita",
            "fecha_programada",
            "asistencia",
            "asistencia_directa",
            "descripcion",
            "observaciones",
            "informe_tecnico",
            "create_date",
            "write_date",
        )

        result = {
            "id": ticket.id,
            "display_name": (
                ticket.display_name
                or ""
            ),
        }

        for field_name in fields_to_show:
            if field_name not in ticket._fields:
                continue

            try:
                result[
                    field_name
                ] = self._serialize_field(
                    ticket,
                    field_name,
                )

                if getattr(
                    ticket._fields[
                        field_name
                    ],
                    "type",
                    False,
                ) == "selection":
                    result[
                        "%s_label"
                        % field_name
                    ] = self._selection_label_safe(
                        ticket,
                        field_name,
                    )
            except Exception:
                continue

        if full:
            result[
                "extra"
            ] = self._serialize_extra(
                ticket,
                exclude=fields_to_show,
            )

        return result

    # ============================================================
    # ORDER SERIALIZER
    # ============================================================

    def _serialize_order(
        self,
        order,
        *,
        full=False,
    ):
        fields_to_show = (
            "name",
            "partner_id",
            "equipo_id",
            "tipo_pedido",
            "estado_entrega",
            "state",
            "date_order",
            "commitment_date",
            "user_id",
            "amount_untaxed",
            "amount_tax",
            "amount_total",
            "currency_id",
            "invoice_status",
            "note",
            "create_date",
            "write_date",
        )

        result = {
            "id": order.id,
            "display_name": (
                order.display_name
                or ""
            ),
        }

        for field_name in fields_to_show:
            if field_name not in order._fields:
                continue

            try:
                result[
                    field_name
                ] = self._serialize_field(
                    order,
                    field_name,
                )

                if getattr(
                    order._fields[
                        field_name
                    ],
                    "type",
                    False,
                ) == "selection":
                    result[
                        "%s_label"
                        % field_name
                    ] = self._selection_label_safe(
                        order,
                        field_name,
                    )
            except Exception:
                continue

        if "order_line" in order._fields:
            result[
                "line_count"
            ] = len(
                order.order_line
            )

            if full:
                result[
                    "lines"
                ] = [
                    {
                        "id": line.id,
                        "product": self._serialize_field(
                            line,
                            "product_id",
                        )
                        if "product_id"
                        in line._fields
                        else False,
                        "description": self._serialize_field(
                            line,
                            "name",
                        )
                        if "name"
                        in line._fields
                        else False,
                        "quantity": self._serialize_field(
                            line,
                            "product_uom_qty",
                        )
                        if "product_uom_qty"
                        in line._fields
                        else 0,
                        "price_unit": self._serialize_field(
                            line,
                            "price_unit",
                        )
                        if "price_unit"
                        in line._fields
                        else 0,
                        "subtotal": self._serialize_field(
                            line,
                            "price_subtotal",
                        )
                        if "price_subtotal"
                        in line._fields
                        else 0,
                    }
                    for line in order.order_line
                ]

        if full:
            result[
                "extra"
            ] = self._serialize_extra(
                order,
                exclude=fields_to_show,
            )

        return result

    # ============================================================
    # SPARE SERIALIZER
    # ============================================================

    def _serialize_spare(
        self,
        spare,
        *,
        full=False,
    ):
        fields_to_show = (
            "name",
            "modelo_id",
            "product_id",
            "producto_id",
            "repuesto_id",
            "cantidad",
            "qty",
            "stock",
            "estado",
            "state",
            "observacion",
            "observaciones",
            "create_date",
            "write_date",
        )

        result = {
            "id": spare.id,
            "display_name": (
                spare.display_name
                or ""
            ),
        }

        for field_name in fields_to_show:
            if field_name not in spare._fields:
                continue

            try:
                result[
                    field_name
                ] = self._serialize_field(
                    spare,
                    field_name,
                )

                if getattr(
                    spare._fields[
                        field_name
                    ],
                    "type",
                    False,
                ) == "selection":
                    result[
                        "%s_label"
                        % field_name
                    ] = self._selection_label_safe(
                        spare,
                        field_name,
                    )
            except Exception:
                continue

        if full:
            result[
                "extra"
            ] = self._serialize_extra(
                spare,
                exclude=fields_to_show,
            )

        return result

    # ============================================================
    # PART REQUEST SERIALIZER
    # ============================================================

    def _serialize_part_request(
        self,
        part_request,
        *,
        full=False,
    ):
        fields_to_show = (
            "name",
            "maquina_origen_id",
            "maquina_destino_id",
            "tecnico_asignado_id",
            "responsable_reposicion_id",
            "solicitante_id",
            "state",
            "estado",
            "prioridad",
            "motivo",
            "descripcion",
            "observaciones",
            "fecha_solicitud",
            "fecha_aprobacion",
            "fecha_retiro",
            "fecha_reposicion",
            "create_date",
            "write_date",
        )

        result = {
            "id": part_request.id,
            "display_name": (
                part_request.display_name
                or ""
            ),
        }

        for field_name in fields_to_show:
            if field_name not in part_request._fields:
                continue

            try:
                result[
                    field_name
                ] = self._serialize_field(
                    part_request,
                    field_name,
                )

                if getattr(
                    part_request._fields[
                        field_name
                    ],
                    "type",
                    False,
                ) == "selection":
                    result[
                        "%s_label"
                        % field_name
                    ] = self._selection_label_safe(
                        part_request,
                        field_name,
                    )
            except Exception:
                continue

        line_field = False

        for candidate in (
            "linea_ids",
            "line_ids",
            "partes_ids",
        ):
            if candidate in part_request._fields:
                line_field = candidate
                break

        if line_field:
            lines = part_request[
                line_field
            ]

            result[
                "line_count"
            ] = len(
                lines
            )

            if full:
                result[
                    "lines"
                ] = [
                    self._serialize_part_line(
                        line,
                    )
                    for line in lines
                ]

        if full:
            result[
                "extra"
            ] = self._serialize_extra(
                part_request,
                exclude=fields_to_show,
            )

        return result

    def _serialize_part_line(
        self,
        line,
    ):
        fields_to_show = (
            "name",
            "product_id",
            "repuesto_id",
            "parte_id",
            "subparte_id",
            "cantidad",
            "qty",
            "state",
            "estado",
            "observacion",
            "observaciones",
            "fecha_retiro_real",
            "reemplazado_por",
            "fecha_reemplazo",
        )

        result = {
            "id": line.id,
            "display_name": (
                line.display_name
                or ""
            ),
        }

        for field_name in fields_to_show:
            if field_name not in line._fields:
                continue

            try:
                result[
                    field_name
                ] = self._serialize_field(
                    line,
                    field_name,
                )

                if getattr(
                    line._fields[
                        field_name
                    ],
                    "type",
                    False,
                ) == "selection":
                    result[
                        "%s_label"
                        % field_name
                    ] = self._selection_label_safe(
                        line,
                        field_name,
                    )
            except Exception:
                continue

        return result

    # ============================================================
    # REMOVED PART SERIALIZER
    # ============================================================

    def _serialize_removed_part(
        self,
        line,
        *,
        full=False,
    ):
        fields_to_show = (
            "name",
            "maquina_origen_alquiler_id",
            "solicitud_id",
            "solicitud_parte_id",
            "product_id",
            "repuesto_id",
            "parte_id",
            "subparte_id",
            "cantidad",
            "qty",
            "state",
            "estado",
            "tecnico_id",
            "fecha_retiro",
            "fecha_retiro_real",
            "observacion",
            "observaciones",
            "create_date",
            "write_date",
        )

        result = {
            "id": line.id,
            "display_name": (
                line.display_name
                or ""
            ),
        }

        for field_name in fields_to_show:
            if field_name not in line._fields:
                continue

            try:
                result[
                    field_name
                ] = self._serialize_field(
                    line,
                    field_name,
                )

                if getattr(
                    line._fields[
                        field_name
                    ],
                    "type",
                    False,
                ) == "selection":
                    result[
                        "%s_label"
                        % field_name
                    ] = self._selection_label_safe(
                        line,
                        field_name,
                    )
            except Exception:
                continue

        if full:
            result[
                "extra"
            ] = self._serialize_extra(
                line,
                exclude=fields_to_show,
            )

        return result

    # ============================================================
    # COUNTER SERIALIZER
    # ============================================================

    def _serialize_counter(
        self,
        counter,
        *,
        full=False,
    ):
        fields_to_show = (
            "name",
            "equipo_id",
            "fecha",
            "fecha_lectura",
            "contador_bn",
            "contador_color",
            "contador_scan",
            "contador_total",
            "origen",
            "source",
            "estado",
            "state",
            "observaciones",
            "create_date",
            "write_date",
        )

        result = {
            "id": counter.id,
            "display_name": (
                counter.display_name
                or ""
            ),
        }

        for field_name in fields_to_show:
            if field_name not in counter._fields:
                continue

            try:
                result[
                    field_name
                ] = self._serialize_field(
                    counter,
                    field_name,
                )

                if getattr(
                    counter._fields[
                        field_name
                    ],
                    "type",
                    False,
                ) == "selection":
                    result[
                        "%s_label"
                        % field_name
                    ] = self._selection_label_safe(
                        counter,
                        field_name,
                    )
            except Exception:
                continue

        if full:
            result[
                "extra"
            ] = self._serialize_extra(
                counter,
                exclude=fields_to_show,
            )

        return result

    # ============================================================
    # COUNTS / ACTIONS
    # ============================================================

    def _related_counts(
        self,
        rental,
    ):
        counts = {
            "tickets": 0,
            "orders": 0,
            "pending_orders": 0,
            "spares": 0,
            "part_requests": 0,
            "removed_parts": 0,
            "counters": 0,
        }

        if self._model_available(
            self.TICKET_MODEL
        ):
            Ticket = request.env[
                self.TICKET_MODEL
            ]

            if "product_alquiler" in Ticket._fields:
                counts[
                    "tickets"
                ] = Ticket.search_count(
                    [
                        (
                            "product_alquiler",
                            "=",
                            rental.id,
                        )
                    ]
                )

        if self._model_available(
            self.ORDER_MODEL
        ):
            Order = request.env[
                self.ORDER_MODEL
            ]

            if "equipo_id" in Order._fields:
                domain = [
                    (
                        "equipo_id",
                        "=",
                        rental.id,
                    )
                ]

                counts[
                    "orders"
                ] = Order.search_count(
                    domain
                )

                if "estado_entrega" in Order._fields:
                    counts[
                        "pending_orders"
                    ] = Order.search_count(
                        domain
                        + [
                            (
                                "estado_entrega",
                                "=",
                                "sin_entregar",
                            )
                        ]
                    )

        if self._model_available(
            self.SPARE_MODEL
        ):
            Spare = request.env[
                self.SPARE_MODEL
            ]

            if "modelo_id" in Spare._fields:
                counts[
                    "spares"
                ] = Spare.search_count(
                    [
                        (
                            "modelo_id",
                            "=",
                            rental.id,
                        )
                    ]
                )

        if self._model_available(
            self.PART_REQUEST_MODEL
        ):
            Part = request.env[
                self.PART_REQUEST_MODEL
            ]

            domains = []

            if "maquina_origen_id" in Part._fields:
                domains.append(
                    (
                        "maquina_origen_id",
                        "=",
                        rental.id,
                    )
                )

            if "maquina_destino_id" in Part._fields:
                domains.append(
                    (
                        "maquina_destino_id",
                        "=",
                        rental.id,
                    )
                )

            if len(
                domains
            ) == 2:
                counts[
                    "part_requests"
                ] = Part.search_count(
                    [
                        "|",
                        domains[0],
                        domains[1],
                    ]
                )
            elif domains:
                counts[
                    "part_requests"
                ] = Part.search_count(
                    [
                        domains[0]
                    ]
                )

        if self._model_available(
            self.REMOVED_PART_MODEL
        ):
            Removed = request.env[
                self.REMOVED_PART_MODEL
            ]

            if "maquina_origen_alquiler_id" in Removed._fields:
                counts[
                    "removed_parts"
                ] = Removed.search_count(
                    [
                        (
                            "maquina_origen_alquiler_id",
                            "=",
                            rental.id,
                        )
                    ]
                )

        if self._model_available(
            self.COUNTER_MODEL
        ):
            Counter = request.env[
                self.COUNTER_MODEL
            ]

            if "equipo_id" in Counter._fields:
                counts[
                    "counters"
                ] = Counter.search_count(
                    [
                        (
                            "equipo_id",
                            "=",
                            rental.id,
                        )
                    ]
                )

        return counts

    def _related_actions(
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

        has_client = bool(
            self._field(
                rental,
                "cliente_id",
                False,
            )
        )

        service_operational = (
            self._safe_string(
                rental,
                "estado_bloqueo",
                "activo",
            )
            not in (
                "suspendido",
                "bloqueado",
                "no_accesible",
            )
        )

        return {
            "view_tickets": self._model_available(
                self.TICKET_MODEL
            ),
            "create_ticket": bool(
                can_write
                and has_client
                and service_operational
                and self._method_exists(
                    rental,
                    "create_ticket",
                )
            ),
            "view_orders": self._model_available(
                self.ORDER_MODEL
            ),
            "create_order": bool(
                can_write
                and has_client
                and self._method_exists(
                    rental,
                    "create_sale_order",
                )
            ),
            "view_spares": self._model_available(
                self.SPARE_MODEL
            ),
            "view_part_requests": self._model_available(
                self.PART_REQUEST_MODEL
            ),
            "create_part_request": bool(
                can_write
                and service_operational
                and self._model_available(
                    self.PART_REQUEST_MODEL
                )
                and self._model_has_access(
                    self.PART_REQUEST_MODEL,
                    "create",
                )
            ),
            "view_removed_parts": self._model_available(
                self.REMOVED_PART_MODEL
            ),
            "view_counters": self._model_available(
                self.COUNTER_MODEL
            ),
        }

    # ============================================================
    # OVERVIEW
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/related",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_related_overview(
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
                    "related": {
                        "counts": self._related_counts(
                            rental
                        ),
                        "actions": self._related_actions(
                            rental,
                            user,
                        ),
                    },
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando relaciones alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # TICKETS LIST
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/related/tickets",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_related_tickets(
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

            Ticket = self._model(
                self.TICKET_MODEL,
                "El modelo de tickets",
            )

            domain = [
                (
                    "product_alquiler",
                    "=",
                    rental.id,
                )
            ]

            state = self._query_arg(
                "state",
                "",
            )

            for state_field in (
                "estado",
                "estado_id",
                "state",
            ):
                if (
                    state
                    and state_field in Ticket._fields
                ):
                    domain.append(
                        (
                            state_field,
                            "=",
                            state,
                        )
                    )
                    break

            tickets = Ticket.search(
                domain,
                order=(
                    "create_date desc, id desc"
                    if "create_date" in Ticket._fields
                    else "id desc"
                ),
                limit=self._safe_limit(),
            )

            return self._json_response(
                {
                    "success": True,
                    "count": len(
                        tickets
                    ),
                    "items": [
                        self._serialize_ticket(
                            ticket
                        )
                        for ticket in tickets
                    ],
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error listando tickets alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # CREATE TICKET
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/related/tickets",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_related_ticket_create(
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

            write_error = self._require_rental_write_access(
                rental,
                user,
            )

            if write_error:
                return write_error

            if not self._field(
                rental,
                "cliente_id",
                False,
            ):
                raise UserError(
                    "La máquina debe tener un cliente asignado."
                )

            blocking_state = self._safe_string(
                rental,
                "estado_bloqueo",
                "activo",
            )

            if blocking_state in (
                "suspendido",
                "bloqueado",
                "no_accesible",
            ):
                raise UserError(
                    "No se puede crear un ticket mientras "
                    "el servicio esté suspendido, bloqueado "
                    "o no accesible."
                )

            if not self._method_exists(
                rental,
                "create_ticket",
            ):
                raise UserError(
                    "La creación de ticket desde alquiler "
                    "no está disponible."
                )

            action = rental.create_ticket()

            ticket_id = (
                action.get(
                    "res_id"
                )
                if isinstance(
                    action,
                    dict,
                )
                else False
            )

            Ticket = request.env[
                self.TICKET_MODEL
            ]

            ticket = (
                Ticket.browse(
                    ticket_id
                ).exists()
                if ticket_id
                else Ticket.browse()
            )

            if not ticket:
                raise UserError(
                    "El método de creación no devolvió "
                    "un ticket válido."
                )

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s creó el ticket %s."
                    % (
                        user.name,
                        ticket.display_name
                        or ticket.id,
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": "Ticket creado.",
                    "ticket": self._serialize_ticket(
                        ticket,
                        full=True,
                    ),
                    "counts": self._related_counts(
                        rental
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
                    "code": "RENTAL_TICKET_CREATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error creando ticket alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # TICKET DETAIL
    # ============================================================

    @http.route(
        (
            "/api/app/rentals/<int:rental_id>"
            "/related/tickets/<int:ticket_id>"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_related_ticket_detail(
        self,
        rental_id,
        ticket_id,
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

            ticket = self._get_related_record(
                self.TICKET_MODEL,
                ticket_id,
                domain=[
                    (
                        "product_alquiler",
                        "=",
                        rental.id,
                    )
                ],
            )

            if not ticket:
                return self._json_response(
                    {
                        "success": False,
                        "code": "RENTAL_TICKET_NOT_FOUND",
                        "message": (
                            "El ticket no existe o no pertenece "
                            "a esta máquina."
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "ticket": self._serialize_ticket(
                        ticket,
                        full=True,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error detalle ticket rental=%s ticket=%s.",
                rental_id,
                ticket_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # ORDERS LIST
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/related/orders",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_related_orders(
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

            Order = self._model(
                self.ORDER_MODEL,
                "El modelo de pedidos",
            )

            domain = [
                (
                    "equipo_id",
                    "=",
                    rental.id,
                )
            ]

            delivery_state = self._query_arg(
                "delivery_state",
                "",
            )

            if (
                delivery_state
                and "estado_entrega"
                in Order._fields
            ):
                domain.append(
                    (
                        "estado_entrega",
                        "=",
                        delivery_state,
                    )
                )

            orders = Order.search(
                domain,
                order=(
                    "date_order desc, id desc"
                    if "date_order" in Order._fields
                    else "id desc"
                ),
                limit=self._safe_limit(),
            )

            return self._json_response(
                {
                    "success": True,
                    "count": len(
                        orders
                    ),
                    "items": [
                        self._serialize_order(
                            order
                        )
                        for order in orders
                    ],
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error listando pedidos alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # CREATE ORDER
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/related/orders",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_related_order_create(
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

            write_error = self._require_rental_write_access(
                rental,
                user,
            )

            if write_error:
                return write_error

            if not self._field(
                rental,
                "cliente_id",
                False,
            ):
                raise UserError(
                    "La máquina debe tener un cliente asignado."
                )

            if not self._method_exists(
                rental,
                "create_sale_order",
            ):
                raise UserError(
                    "La creación de pedido desde alquiler "
                    "no está disponible."
                )

            action = rental.create_sale_order()

            order_id = (
                action.get(
                    "res_id"
                )
                if isinstance(
                    action,
                    dict,
                )
                else False
            )

            Order = request.env[
                self.ORDER_MODEL
            ]

            order = (
                Order.browse(
                    order_id
                ).exists()
                if order_id
                else Order.browse()
            )

            if not order:
                raise UserError(
                    "El método de creación no devolvió "
                    "un pedido válido."
                )

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s creó el pedido %s."
                    % (
                        user.name,
                        order.name
                        or order.id,
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": "Pedido creado.",
                    "order": self._serialize_order(
                        order,
                        full=True,
                    ),
                    "counts": self._related_counts(
                        rental
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
                    "code": "RENTAL_ORDER_CREATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error creando pedido alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # ORDER DETAIL
    # ============================================================

    @http.route(
        (
            "/api/app/rentals/<int:rental_id>"
            "/related/orders/<int:order_id>"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_related_order_detail(
        self,
        rental_id,
        order_id,
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

            order = self._get_related_record(
                self.ORDER_MODEL,
                order_id,
                domain=[
                    (
                        "equipo_id",
                        "=",
                        rental.id,
                    )
                ],
            )

            if not order:
                return self._json_response(
                    {
                        "success": False,
                        "code": "RENTAL_ORDER_NOT_FOUND",
                        "message": (
                            "El pedido no existe o no pertenece "
                            "a esta máquina."
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "order": self._serialize_order(
                        order,
                        full=True,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error detalle pedido rental=%s order=%s.",
                rental_id,
                order_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # SPARES
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/related/spares",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_related_spares(
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

            Spare = self._model(
                self.SPARE_MODEL,
                "El modelo de repuestos",
            )

            if "modelo_id" not in Spare._fields:
                raise UserError(
                    "El modelo de repuestos no contiene modelo_id."
                )

            spares = Spare.search(
                [
                    (
                        "modelo_id",
                        "=",
                        rental.id,
                    )
                ],
                order="id desc",
                limit=self._safe_limit(),
            )

            return self._json_response(
                {
                    "success": True,
                    "count": len(
                        spares
                    ),
                    "items": [
                        self._serialize_spare(
                            spare,
                            full=True,
                        )
                        for spare in spares
                    ],
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error listando repuestos alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # PART REQUEST DOMAIN
    # ============================================================

    def _part_request_domain(
        self,
        rental,
    ):
        Part = request.env[
            self.PART_REQUEST_MODEL
        ]

        origin = (
            "maquina_origen_id"
            in Part._fields
        )

        destination = (
            "maquina_destino_id"
            in Part._fields
        )

        if origin and destination:
            return [
                "|",
                (
                    "maquina_origen_id",
                    "=",
                    rental.id,
                ),
                (
                    "maquina_destino_id",
                    "=",
                    rental.id,
                ),
            ]

        if origin:
            return [
                (
                    "maquina_origen_id",
                    "=",
                    rental.id,
                )
            ]

        if destination:
            return [
                (
                    "maquina_destino_id",
                    "=",
                    rental.id,
                )
            ]

        raise UserError(
            "El modelo solicitud.partes no contiene "
            "una relación conocida con alquiler."
        )

    # ============================================================
    # PART REQUEST LIST
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/related/parts",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_related_parts(
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

            Part = self._model(
                self.PART_REQUEST_MODEL,
                "El modelo de solicitudes de partes",
            )

            domain = self._part_request_domain(
                rental
            )

            state = self._query_arg(
                "state",
                "",
            )

            for state_field in (
                "state",
                "estado",
            ):
                if (
                    state
                    and state_field in Part._fields
                ):
                    domain.append(
                        (
                            state_field,
                            "=",
                            state,
                        )
                    )
                    break

            requests = Part.search(
                domain,
                order=(
                    "create_date desc, id desc"
                    if "create_date" in Part._fields
                    else "id desc"
                ),
                limit=self._safe_limit(),
            )

            return self._json_response(
                {
                    "success": True,
                    "count": len(
                        requests
                    ),
                    "items": [
                        self._serialize_part_request(
                            item
                        )
                        for item in requests
                    ],
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error listando solicitudes partes alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # PART REQUEST CREATE
    # ============================================================

    def _prepare_part_request_values(
        self,
        rental,
        data,
    ):
        Part = self._part_request_model()

        values = {}

        if "maquina_origen_id" in Part._fields:
            values[
                "maquina_origen_id"
            ] = rental.id

        simple_fields = (
            "motivo",
            "descripcion",
            "observaciones",
        )

        for field_name in simple_fields:
            if (
                field_name in Part._fields
                and field_name in data
            ):
                raw = data.get(
                    field_name
                )

                values[
                    field_name
                ] = (
                    str(
                        raw
                    ).strip()
                    if raw
                    else False
                )

        for selection_field in (
            "prioridad",
            "state",
            "estado",
        ):
            if (
                selection_field
                not in Part._fields
                or selection_field
                not in data
            ):
                continue

            value = data.get(
                selection_field
            )

            options = self._selection_options_safe(
                Part,
                selection_field,
            )

            valid = {
                item[
                    "value"
                ]
                for item in options
            }

            if (
                valid
                and value not in valid
            ):
                raise UserError(
                    "El valor de %s no es válido."
                    % selection_field
                )

            values[
                selection_field
            ] = value

        return values

    def _part_request_model(self):
        return self._model(
            self.PART_REQUEST_MODEL,
            "El modelo de solicitudes de partes",
        )

    @http.route(
        "/api/app/rentals/<int:rental_id>/related/parts",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_related_part_create(
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

            write_error = self._require_rental_write_access(
                rental,
                user,
            )

            if write_error:
                return write_error

            blocking_state = self._safe_string(
                rental,
                "estado_bloqueo",
                "activo",
            )

            if blocking_state in (
                "suspendido",
                "bloqueado",
                "no_accesible",
            ):
                raise UserError(
                    "No se puede crear una solicitud de partes "
                    "mientras el servicio esté suspendido, "
                    "bloqueado o no accesible."
                )

            Part = self._part_request_model()

            if (
                not self._model_has_access(
                    self.PART_REQUEST_MODEL,
                    "create",
                )
                and not self._is_system_user(
                    user
                )
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "PART_REQUEST_CREATE_DENIED",
                        "message": (
                            "No tienes permiso para crear "
                            "solicitudes de partes."
                        ),
                    },
                    status=403,
                )

            data = self._json_body()

            values = self._prepare_part_request_values(
                rental,
                data,
            )

            # Si hay campos obligatorios adicionales en la instalación,
            # Odoo será la autoridad y devolverá ValidationError.
            part_request = Part.create(
                values
            )

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s creó "
                    "la solicitud de partes %s."
                    % (
                        user.name,
                        part_request.display_name
                        or part_request.id,
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Solicitud de partes creada."
                    ),
                    "request": self._serialize_part_request(
                        part_request,
                        full=True,
                    ),
                    "counts": self._related_counts(
                        rental
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
                    "code": "PART_REQUEST_CREATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error creando solicitud partes alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # PART REQUEST DETAIL
    # ============================================================

    @http.route(
        (
            "/api/app/rentals/<int:rental_id>"
            "/related/parts/<int:request_id>"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_related_part_detail(
        self,
        rental_id,
        request_id,
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

            Part = self._part_request_model()

            request_record = Part.browse(
                request_id
            ).exists()

            if not request_record:
                return self._json_response(
                    {
                        "success": False,
                        "code": "PART_REQUEST_NOT_FOUND",
                        "message": (
                            "La solicitud de partes no existe."
                        ),
                    },
                    status=404,
                )

            domain = self._part_request_domain(
                rental
            )

            domain = [
                (
                    "id",
                    "=",
                    request_record.id,
                )
            ] + domain

            if not Part.search_count(
                domain
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "PART_REQUEST_NOT_FOUND",
                        "message": (
                            "La solicitud no pertenece "
                            "a esta máquina."
                        ),
                    },
                    status=404,
                )

            if hasattr(
                request_record,
                "check_access",
            ):
                request_record.check_access(
                    "read"
                )

            return self._json_response(
                {
                    "success": True,
                    "request": self._serialize_part_request(
                        request_record,
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
                    "code": "PART_REQUEST_DETAIL_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error detalle solicitud partes rental=%s request=%s.",
                rental_id,
                request_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # REMOVED PARTS
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/related/removed-parts",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_related_removed_parts(
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

            Removed = self._model(
                self.REMOVED_PART_MODEL,
                "El historial de partes retiradas",
            )

            if (
                "maquina_origen_alquiler_id"
                not in Removed._fields
            ):
                raise UserError(
                    "El historial de partes retiradas no contiene "
                    "maquina_origen_alquiler_id."
                )

            lines = Removed.search(
                [
                    (
                        "maquina_origen_alquiler_id",
                        "=",
                        rental.id,
                    )
                ],
                order=(
                    "create_date desc, id desc"
                    if "create_date" in Removed._fields
                    else "id desc"
                ),
                limit=self._safe_limit(
                    default=200
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "count": len(
                        lines
                    ),
                    "items": [
                        self._serialize_removed_part(
                            line,
                            full=True,
                        )
                        for line in lines
                    ],
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error partes retiradas alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # COUNTERS
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/related/counters",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_related_counters(
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

            Counter = self._model(
                self.COUNTER_MODEL,
                "El historial de contadores",
            )

            if "equipo_id" not in Counter._fields:
                raise UserError(
                    "El modelo de contadores no contiene equipo_id."
                )

            order_parts = []

            for candidate in (
                "fecha_lectura",
                "fecha",
                "create_date",
            ):
                if candidate in Counter._fields:
                    order_parts.append(
                        "%s desc"
                        % candidate
                    )
                    break

            order_parts.append(
                "id desc"
            )

            counters = Counter.search(
                [
                    (
                        "equipo_id",
                        "=",
                        rental.id,
                    )
                ],
                order=", ".join(
                    order_parts
                ),
                limit=self._safe_limit(
                    default=200
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "current": {
                        "black_white": self._safe_int(
                            rental,
                            "contador_bn",
                        ),
                        "color": self._safe_int(
                            rental,
                            "contador_color",
                        ),
                        "scan": self._safe_int(
                            rental,
                            "contador_scan",
                        ),
                    },
                    "count": len(
                        counters
                    ),
                    "items": [
                        self._serialize_counter(
                            counter,
                            full=True,
                        )
                        for counter in counters
                    ],
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error contadores relacionados alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )
