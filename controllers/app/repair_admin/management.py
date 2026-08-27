# -*- coding: utf-8 -*-

import logging

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from .base import RepairAdminBaseController


_logger = logging.getLogger(__name__)


class RepairAdminManagementController(RepairAdminBaseController):

    @http.route(
        [
            "/api/app/repairs/admin/repairs",
            "/api/app/repairs/admin/repairs/<int:repair_id>",
            "/api/app/repairs/admin/repairs/<int:repair_id>/reassign",
            "/api/app/repairs/admin/repairs/<int:repair_id>/state",
            "/api/app/repairs/admin/repairs/<int:repair_id>/finalize",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def repair_admin_management_options(
        self,
        repair_id=None,
        **kwargs,
    ):
        return self._options_response()

    @http.route(
        "/api/app/repairs/admin/repairs",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def repair_admin_repairs(self, **kwargs):
        user, error = self._ra_require_admin()
        if error:
            return error

        try:
            args = request.httprequest.args

            state = (args.get("state") or "").strip()
            search_term = (
                args.get("search") or ""
            ).strip()
            technician_id = self._ra_safe_int(
                args.get("technician_id"),
                0,
            )
            scope = (
                args.get("scope")
                or "active"
            ).strip()
            limit = self._ra_limit(
                args.get("limit"),
                default=100,
                maximum=300,
            )
            offset = self._ra_offset(
                args.get("offset")
            )

            Repair = request.env[
                self.REPAIR_MODEL
            ].sudo()

            domain = []

            if scope == "active":
                domain.append(
                    (
                        "estado_id",
                        "not in",
                        list(self.FINAL_STATES),
                    )
                )
            elif scope == "finalized":
                domain.append(
                    (
                        "estado_id",
                        "in",
                        list(self.FINAL_STATES),
                    )
                )
            elif scope == "all":
                pass
            else:
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_SCOPE",
                        "message": (
                            "scope debe ser active, "
                            "finalized o all."
                        ),
                    },
                    status=400,
                )

            if state:
                domain.append(
                    ("estado_id", "=", state)
                )

            if technician_id:
                domain.append(
                    (
                        "responsable_id",
                        "=",
                        technician_id,
                    )
                )

            if search_term:
                domain += [
                    "|",
                    "|",
                    "|",
                    ("name", "ilike", search_term),
                    ("serie_id", "ilike", search_term),
                    (
                        "cliente_id.name",
                        "ilike",
                        search_term,
                    ),
                    (
                        "maquina_id.name.name",
                        "ilike",
                        search_term,
                    ),
                ]

            total = Repair.search_count(domain)

            records = Repair.search(
                domain,
                order="create_date desc, id desc",
                limit=limit,
                offset=offset,
            )

            return self._json_response(
                {
                    "success": True,
                    "scope": scope,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "items": [
                        self._ra_serialize_repair_short(
                            repair
                        )
                        for repair in records
                    ],
                }
            )

        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/repairs/admin/repairs/<int:repair_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def repair_admin_detail(
        self,
        repair_id,
        **kwargs,
    ):
        user, error = self._ra_require_admin()
        if error:
            return error

        try:
            repair = self._ra_get_repair(repair_id)
            if not repair:
                return self._ra_repair_not_found()

            return self._json_response(
                {
                    "success": True,
                    "repair": (
                        self._ra_serialize_repair_detail(
                            repair
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/repairs/admin/repairs/<int:repair_id>/reassign",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def repair_admin_reassign(
        self,
        repair_id,
        **kwargs,
    ):
        user, error = self._ra_require_admin()
        if error:
            return error

        try:
            repair = self._ra_get_repair(repair_id)
            if not repair:
                return self._ra_repair_not_found()

            if (
                self._ra_safe_value(
                    repair,
                    "estado_id",
                    "",
                )
                in self.FINAL_STATES
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_READ_ONLY",
                        "message": (
                            "No se puede reasignar una "
                            "reparación finalizada."
                        ),
                    },
                    status=409,
                )

            data = self._get_json_body()
            technician_id = self._ra_safe_int(
                data.get("technician_id")
                or data.get("responsible_id"),
                0,
            )

            if not technician_id:
                return self._json_response(
                    {
                        "success": False,
                        "code": "TECHNICIAN_REQUIRED",
                        "message": (
                            "Debe seleccionar el nuevo técnico."
                        ),
                    },
                    status=400,
                )

            technician = request.env[
                self.USER_MODEL
            ].sudo().browse(
                technician_id
            ).exists()

            if (
                not technician
                or not self._ra_is_valid_technician(
                    technician
                )
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_TECHNICIAN",
                        "message": (
                            "El usuario seleccionado no es "
                            "un técnico válido."
                        ),
                    },
                    status=400,
                )

            if not self._ra_technician_available(
                technician
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "TECHNICIAN_UNAVAILABLE",
                        "message": (
                            "El técnico seleccionado no está "
                            "disponible en este momento."
                        ),
                    },
                    status=409,
                )

            previous = self._ra_many2one(
                repair,
                "responsable_id",
            )

            # El write() real del modelo vuelve a validar
            # disponibilidad y conserva toda su lógica.
            repair.sudo().write(
                {
                    "responsable_id": technician.id,
                }
            )

            repair.invalidate_recordset()

            return self._json_response(
                {
                    "success": True,
                    "code": "REPAIR_REASSIGNED",
                    "message": (
                        "Técnico reasignado correctamente."
                    ),
                    "previous_responsible": previous,
                    "repair": (
                        self._ra_serialize_repair_detail(
                            repair
                        )
                    ),
                }
            )

        except (ValidationError, UserError) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "REPAIR_VALIDATION_ERROR",
                    "message": str(exc),
                },
                status=400,
            )

        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/repairs/admin/repairs/<int:repair_id>/state",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def repair_admin_state(
        self,
        repair_id,
        **kwargs,
    ):
        user, error = self._ra_require_admin()
        if error:
            return error

        try:
            repair = self._ra_get_repair(repair_id)
            if not repair:
                return self._ra_repair_not_found()

            current_state = (
                self._ra_safe_value(
                    repair,
                    "estado_id",
                    "",
                )
                or ""
            )

            if current_state in self.FINAL_STATES:
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_READ_ONLY",
                        "message": (
                            "La reparación finalizada "
                            "es de solo lectura."
                        ),
                    },
                    status=409,
                )

            data = self._get_json_body()
            new_state = (
                data.get("state")
                or ""
            ).strip()

            valid_states = {
                item["value"]
                for item in self._ra_selection_options(
                    repair,
                    "estado_id",
                )
            }

            if new_state not in valid_states:
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_STATE",
                        "message": (
                            "El estado solicitado no es válido."
                        ),
                    },
                    status=400,
                )

            if new_state == "finalizado":
                return self._json_response(
                    {
                        "success": False,
                        "code": "USE_ADMIN_FINALIZE_ENDPOINT",
                        "message": (
                            "Para finalizar use el endpoint "
                            "administrativo /finalize."
                        ),
                    },
                    status=400,
                )

            repair.sudo().write(
                {"estado_id": new_state}
            )
            repair.invalidate_recordset()

            return self._json_response(
                {
                    "success": True,
                    "code": "REPAIR_STATE_CHANGED",
                    "message": (
                        "Estado actualizado correctamente."
                    ),
                    "repair": (
                        self._ra_serialize_repair_detail(
                            repair
                        )
                    ),
                }
            )

        except (ValidationError, UserError) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "REPAIR_VALIDATION_ERROR",
                    "message": str(exc),
                },
                status=400,
            )

        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/repairs/admin/repairs/<int:repair_id>/finalize",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def repair_admin_finalize(
        self,
        repair_id,
        **kwargs,
    ):
        """
        Usa action_finalizar_reparacion() del modelo real.
        No fuerza estado_id='finalizado', para no saltarse
        la Verificación Andes ni otras validaciones de Odoo.
        """
        user, error = self._ra_require_admin()
        if error:
            return error

        try:
            repair = self._ra_get_repair(repair_id)
            if not repair:
                return self._ra_repair_not_found()

            if (
                self._ra_safe_value(
                    repair,
                    "estado_id",
                    "",
                )
                == "finalizado"
            ):
                return self._json_response(
                    {
                        "success": True,
                        "message": (
                            "La reparación ya está finalizada."
                        ),
                        "repair": (
                            self._ra_serialize_repair_detail(
                                repair
                            )
                        ),
                    }
                )

            method = getattr(
                repair,
                "action_finalizar_reparacion",
                None,
            )

            if not callable(method):
                raise UserError(
                    "No existe "
                    "action_finalizar_reparacion()."
                )

            result = method()

            if (
                isinstance(result, dict)
                and result.get("target") == "new"
            ):
                model_name = (
                    result.get("res_model") or ""
                )

                if (
                    model_name
                    == "reparacion.autenticacion.wizard"
                ):
                    return self._json_response(
                        {
                            "success": False,
                            "code": (
                                "ANDES_VERIFICATION_REQUIRED"
                            ),
                            "message": (
                                "Debe completar la "
                                "Verificación Andes antes "
                                "de finalizar."
                            ),
                            "verified": False,
                        },
                        status=409,
                    )

                return self._json_response(
                    {
                        "success": False,
                        "code": "ODOO_ACTION_REQUIRED",
                        "message": (
                            "Odoo requiere completar una "
                            "validación adicional antes "
                            "de finalizar."
                        ),
                    },
                    status=409,
                )

            repair.invalidate_recordset()

            return self._json_response(
                {
                    "success": True,
                    "code": "REPAIR_FINALIZED",
                    "message": (
                        "Reparación finalizada correctamente."
                    ),
                    "repair": (
                        self._ra_serialize_repair_detail(
                            repair
                        )
                    ),
                }
            )

        except (ValidationError, UserError) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "REPAIR_VALIDATION_ERROR",
                    "message": str(exc),
                },
                status=400,
            )

        except Exception as exc:
            return self._error_response(exc)
