# -*- coding: utf-8 -*-

import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from .base import AppBaseController


_logger = logging.getLogger(__name__)


class AppServiceController(
    AppBaseController
):

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/services",
            "/api/app/services/<int:service_id>",
            "/api/app/services/<int:service_id>/state",
            "/api/app/services/<int:service_id>/finalize",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def service_options(
        self,
        service_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # GET OWN SERVICE
    # ============================================================

    def _get_service(
        self,
        service_id,
        user,
    ):
        return request.env[
            "ticket.alquiler"
        ].search(
            [
                (
                    "id",
                    "=",
                    service_id,
                ),
                (
                    "responsable",
                    "=",
                    user.id,
                ),
            ],
            limit=1,
        )

    # ============================================================
    # SERIALIZERS
    # ============================================================

    def _serialize_service_short(
        self,
        ticket,
    ):
        return {
            "id": ticket.id,
            "reference": (
                ticket.name
                or ""
            ),
            "state": (
                ticket.estado
            ),
            "state_label": (
                self._selection_label(
                    ticket,
                    "estado",
                )
            ),
            "priority": (
                ticket.priority
            ),
            "priority_label": (
                self._selection_label(
                    ticket,
                    "priority",
                )
            ),
            "service_type": (
                ticket.tipo_servicio_id
            ),
            "service_type_label": (
                self._selection_label(
                    ticket,
                    "tipo_servicio_id",
                )
            ),
            "schedule": (
                ticket.agenda
            ),
            "client": (
                self._many2one(
                    ticket.partner_id
                )
                if ticket.partner_id
                else False
            ),
            "client_name": (
                ticket.nombre_cliente
                if "nombre_cliente"
                in ticket._fields
                else False
            ),
            "machine": (
                self._many2one(
                    ticket.product_alquiler
                )
                if ticket.product_alquiler
                else False
            ),
            "model": (
                ticket.modelo_id_r
                or False
            ),
            "brand": (
                ticket.marca_id_r
                or False
            ),
            "serial": (
                ticket.serie_id_r
                or False
            ),
            "address": (
                ticket.direccion_id_r
                or False
            ),
        }

    def _serialize_component(
        self,
        item,
    ):
        return {
            "id": item.id,
            "component": (
                self._many2one(
                    item.componente_tipo_id
                )
                if (
                    "componente_tipo_id"
                    in item._fields
                    and item.componente_tipo_id
                )
                else False
            ),
            "color": (
                self._many2one(
                    item.color_id
                )
                if (
                    "color_id"
                    in item._fields
                    and item.color_id
                )
                else False
            ),
            "state": (
                self._many2one(
                    item.estado_id
                )
                if (
                    "estado_id"
                    in item._fields
                    and item.estado_id
                )
                else False
            ),
            "observations": (
                item.observaciones
                if "observaciones"
                in item._fields
                else False
            ),
        }

    def _serialize_accessory(
        self,
        item,
    ):
        return {
            "id": item.id,
            "accessory": (
                self._many2one(
                    item.tipo_id
                )
                if (
                    "tipo_id"
                    in item._fields
                    and item.tipo_id
                )
                else False
            ),
            "state": (
                self._many2one(
                    item.estado_id
                )
                if (
                    "estado_id"
                    in item._fields
                    and item.estado_id
                )
                else False
            ),
            "observations": (
                item.observaciones
                if "observaciones"
                in item._fields
                else False
            ),
        }

    def _serialize_service_detail(
        self,
        ticket,
    ):
        result = (
            self._serialize_service_short(
                ticket
            )
        )

        result.update(
            {
                "description": (
                    ticket.description
                    or False
                ),
                "technical_report": (
                    ticket.informe_id
                    or False
                ),
                "contact": {
                    "name": (
                        ticket.contacto_id_r
                        or False
                    ),
                    "phone": (
                        ticket.celular_id_r
                        or False
                    ),
                    "email": (
                        ticket.corre_id_r
                        or False
                    ),
                    "floor": (
                        ticket.piso_id_r
                        or False
                    ),
                    "office": (
                        ticket.oficina_id_r
                        or False
                    ),
                    "area": (
                        ticket.area_id_r
                        or False
                    ),
                },
                "meters": {
                    "black": (
                        ticket.contometrok_id
                        or False
                    ),
                    "color": (
                        ticket.contometroc_id
                        or False
                    ),
                    "scanner": (
                        ticket.contometros_id
                        or False
                    ),
                    "total": (
                        ticket.total_copias_id
                        or False
                    ),
                },
                "quality": (
                    ticket.calidad_id
                    or False
                ),
                "quality_label": (
                    self._selection_label(
                        ticket,
                        "calidad_id",
                    )
                ),
                "components": [
                    self._serialize_component(
                        item
                    )
                    for item
                    in ticket.ticket_componente_eval_ids
                ],
                "accessories": [
                    self._serialize_accessory(
                        item
                    )
                    for item
                    in ticket.ticket_accesorio_eval_ids
                ],
                "parts_requests_count": (
                    ticket.ticket_pedido_count
                ),
            }
        )

        return result

    # ============================================================
    # LIST
    # ============================================================

    @http.route(
        "/api/app/services",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def services(
        self,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            state = (
                request.httprequest.args.get(
                    "state"
                )
            )

            search_term = (
                request.httprequest.args.get(
                    "search"
                )
                or ""
            ).strip()

            try:
                limit = min(
                    max(
                        int(
                            request.httprequest.args.get(
                                "limit",
                                50,
                            )
                        ),
                        1,
                    ),
                    100,
                )
            except Exception:
                limit = 50

            domain = [
                (
                    "responsable",
                    "=",
                    user.id,
                ),
            ]

            if state:
                domain.append(
                    (
                        "estado",
                        "=",
                        state,
                    )
                )

            if search_term:
                domain.extend(
                    [
                        "|",
                        "|",
                        "|",
                        (
                            "name",
                            "ilike",
                            search_term,
                        ),
                        (
                            "nombre_cliente",
                            "ilike",
                            search_term,
                        ),
                        (
                            "serie_id_r",
                            "ilike",
                            search_term,
                        ),
                        (
                            "modelo_id_r",
                            "ilike",
                            search_term,
                        ),
                    ]
                )

            Ticket = request.env[
                "ticket.alquiler"
            ]

            tickets = Ticket.search(
                domain,
                order=(
                    "agenda asc, "
                    "priority desc, "
                    "id desc"
                ),
                limit=limit,
            )

            return self._json_response(
                {
                    "success": True,
                    "count": len(
                        tickets
                    ),
                    "items": [
                        self._serialize_service_short(
                            ticket
                        )
                        for ticket
                        in tickets
                    ],
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # DETAIL
    # ============================================================

    @http.route(
        "/api/app/services/<int:service_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def service_detail(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = self._get_service(
                service_id,
                user,
            )

            if not ticket:
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_NOT_FOUND",
                        "message": (
                            "El servicio no existe "
                            "o no está asignado a este usuario."
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "service": (
                        self._serialize_service_detail(
                            ticket
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # UPDATE TECHNICAL INFORMATION
    # ============================================================

    @http.route(
        "/api/app/services/<int:service_id>",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def service_update(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = self._get_service(
                service_id,
                user,
            )

            if not ticket:
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_NOT_FOUND",
                        "message": (
                            "Servicio no encontrado."
                        ),
                    },
                    status=404,
                )

            data = self._get_json_body()

            allowed = {
                "description",
                "informe_id",
                "contometros_id",
                "contometrok_id",
                "contometroc_id",
                "calidad_id",
                "reporter_name",
                "reporter_phone",
            }

            vals = {}

            for field_name in allowed:
                if (
                    field_name
                    in data
                    and field_name
                    in ticket._fields
                ):
                    vals[
                        field_name
                    ] = data[
                        field_name
                    ]

            if not vals:
                return self._json_response(
                    {
                        "success": False,
                        "code": "NO_DATA",
                        "message": (
                            "No se recibieron campos "
                            "válidos para actualizar."
                        ),
                    },
                    status=400,
                )

            ticket.write(
                vals
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Servicio actualizado correctamente."
                    ),
                    "service": (
                        self._serialize_service_detail(
                            ticket
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # STATE
    # ============================================================

    @http.route(
        "/api/app/services/<int:service_id>/state",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def service_state(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = self._get_service(
                service_id,
                user,
            )

            if not ticket:
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_NOT_FOUND",
                        "message": (
                            "Servicio no encontrado."
                        ),
                    },
                    status=404,
                )

            data = self._get_json_body()

            new_state = (
                str(
                    data.get("state")
                    or ""
                )
                .strip()
            )

            transitions = {
                "proceso": {
                    "en_ruta",
                },
                "en_ruta": {
                    "en_sitio",
                },
                "en_sitio": {
                    "en_revision",
                },
            }

            allowed_next = transitions.get(
                ticket.estado,
                set(),
            )

            if (
                new_state
                not in allowed_next
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_STATE_TRANSITION",
                        "message": (
                            "No se puede cambiar "
                            f"de {ticket.estado} "
                            f"a {new_state}."
                        ),
                    },
                    status=400,
                )

            ticket.write(
                {
                    "estado": new_state,
                }
            )

            ticket.message_post(
                body=(
                    "Estado actualizado desde "
                    "la aplicación móvil: "
                    f"{self._selection_label(ticket, 'estado')}"
                ),
                message_type="notification",
            )

            return self._json_response(
                {
                    "success": True,
                    "state": (
                        ticket.estado
                    ),
                    "state_label": (
                        self._selection_label(
                            ticket,
                            "estado",
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # FINALIZE
    # ============================================================

    @http.route(
        "/api/app/services/<int:service_id>/finalize",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def service_finalize(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = self._get_service(
                service_id,
                user,
            )

            if not ticket:
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_NOT_FOUND",
                        "message": (
                            "Servicio no encontrado."
                        ),
                    },
                    status=404,
                )

            if ticket.estado == "finalizado":
                return self._json_response(
                    {
                        "success": True,
                        "message": (
                            "El servicio ya se encuentra finalizado."
                        ),
                        "service": (
                            self._serialize_service_detail(
                                ticket
                            )
                        ),
                    }
                )

            if not hasattr(
                ticket,
                "action_finalizar",
            ):
                raise UserError(
                    "El modelo no dispone "
                    "de action_finalizar()."
                )

            ticket.action_finalizar()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Servicio finalizado correctamente."
                    ),
                    "service": (
                        self._serialize_service_detail(
                            ticket
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )