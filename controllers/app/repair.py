# -*- coding: utf-8 -*-

import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from .base import AppBaseController


_logger = logging.getLogger(__name__)


class AppRepairController(
    AppBaseController
):

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/repairs",
            "/api/app/repairs/<int:repair_id>",
            "/api/app/repairs/<int:repair_id>/finalize",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def repair_options(
        self,
        repair_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # OWN REPAIR
    # ============================================================

    def _get_repair(
        self,
        repair_id,
        user,
    ):
        return request.env[
            "reparaciones.reparaciones"
        ].search(
            [
                (
                    "id",
                    "=",
                    repair_id,
                ),
                (
                    "responsable_id",
                    "=",
                    user.id,
                ),
            ],
            limit=1,
        )

    # ============================================================
    # EVALUATIONS
    # ============================================================

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

    # ============================================================
    # SERIALIZER
    # ============================================================

    def _serialize_repair(
        self,
        repair,
        detail=False,
    ):
        result = {
            "id": repair.id,
            "reference": (
                repair.name
                or ""
            ),
            "state": (
                repair.estado_id
            ),
            "state_label": (
                self._selection_label(
                    repair,
                    "estado_id",
                )
            ),
            "responsible": (
                self._many2one(
                    repair.responsable_id
                )
                if repair.responsable_id
                else False
            ),
            "machine": (
                self._many2one(
                    repair.maquina_id
                )
                if repair.maquina_id
                else False
            ),
            "serial": (
                repair.serie_id
                or False
            ),
            "client": (
                self._many2one(
                    repair.cliente_id
                )
                if (
                    "cliente_id"
                    in repair._fields
                    and repair.cliente_id
                )
                else False
            ),
            "priority": (
                repair.prioridad
                if "prioridad"
                in repair._fields
                else False
            ),
            "meter_initial": (
                repair.contometro_inicial
                or False
            ),
            "meter_current": (
                repair.contometrok_id
                or False
            ),
            "finish_date": (
                repair.fecha_finalizacion
                if "fecha_finalizacion"
                in repair._fields
                else False
            ),
            "photos_count": (
                len(
                    repair.fotos_ids
                )
                if "fotos_ids"
                in repair._fields
                else 0
            ),
        }

        if not detail:
            return result

        result.update(
            {
                "report": (
                    repair.informe
                    if "informe"
                    in repair._fields
                    else False
                ),
                "components": [
                    self._serialize_component(
                        item
                    )
                    for item
                    in repair.componente_eval_ids
                ],
                "accessories": [
                    self._serialize_accessory(
                        item
                    )
                    for item
                    in repair.accesorio_eval_ids
                ],
                "parts_requests": (
                    len(
                        repair.parts_request_ids
                    )
                    if "parts_request_ids"
                    in repair._fields
                    else 0
                ),
            }
        )

        return result

    # ============================================================
    # LIST
    # ============================================================

    @http.route(
        "/api/app/repairs",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def repairs(
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

            domain = [
                (
                    "responsable_id",
                    "=",
                    user.id,
                ),
            ]

            if state:
                domain.append(
                    (
                        "estado_id",
                        "=",
                        state,
                    )
                )

            if search_term:
                domain.extend(
                    [
                        "|",
                        "|",
                        (
                            "name",
                            "ilike",
                            search_term,
                        ),
                        (
                            "serie_id",
                            "ilike",
                            search_term,
                        ),
                        (
                            "cliente_id.name",
                            "ilike",
                            search_term,
                        ),
                    ]
                )

            records = request.env[
                "reparaciones.reparaciones"
            ].search(
                domain,
                order="id desc",
                limit=100,
            )

            return self._json_response(
                {
                    "success": True,
                    "count": len(
                        records
                    ),
                    "items": [
                        self._serialize_repair(
                            record
                        )
                        for record
                        in records
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
        "/api/app/repairs/<int:repair_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def repair_detail(
        self,
        repair_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            repair = self._get_repair(
                repair_id,
                user,
            )

            if not repair:
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_NOT_FOUND",
                        "message": (
                            "La reparación no existe "
                            "o no está asignada al usuario."
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "repair": (
                        self._serialize_repair(
                            repair,
                            detail=True,
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # UPDATE
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def repair_update(
        self,
        repair_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            repair = self._get_repair(
                repair_id,
                user,
            )

            if not repair:
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_NOT_FOUND",
                        "message": (
                            "Reparación no encontrada."
                        ),
                    },
                    status=404,
                )

            data = self._get_json_body()

            allowed = {
                "informe",
                "contometrok_id",
                "calidad_id",
            }

            vals = {}

            for field_name in allowed:
                if (
                    field_name in data
                    and field_name
                    in repair._fields
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
                            "No existen campos válidos "
                            "para actualizar."
                        ),
                    },
                    status=400,
                )

            repair.write(
                vals
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Reparación actualizada correctamente."
                    ),
                    "repair": (
                        self._serialize_repair(
                            repair,
                            detail=True,
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
        "/api/app/repairs/<int:repair_id>/finalize",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def repair_finalize(
        self,
        repair_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            repair = self._get_repair(
                repair_id,
                user,
            )

            if not repair:
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_NOT_FOUND",
                        "message": (
                            "Reparación no encontrada."
                        ),
                    },
                    status=404,
                )

            if (
                repair.estado_id
                == "finalizado"
            ):
                return self._json_response(
                    {
                        "success": True,
                        "message": (
                            "La reparación ya está finalizada."
                        ),
                        "repair": (
                            self._serialize_repair(
                                repair,
                                detail=True,
                            )
                        ),
                    }
                )

            if not hasattr(
                repair,
                "action_finalizar_reparacion",
            ):
                raise UserError(
                    "No existe "
                    "action_finalizar_reparacion()."
                )

            repair.action_finalizar_reparacion()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Reparación finalizada correctamente."
                    ),
                    "repair": (
                        self._serialize_repair(
                            repair,
                            detail=True,
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )