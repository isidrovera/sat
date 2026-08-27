# -*- coding: utf-8 -*-

import logging

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from .base import RepairAdminBaseController


_logger = logging.getLogger(__name__)


class RepairAdminCreateController(RepairAdminBaseController):

    @http.route(
        [
            "/api/app/repairs/admin/technicians",
            "/api/app/repairs/admin/create",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def repair_admin_create_options(self, **kwargs):
        return self._options_response()

    @http.route(
        "/api/app/repairs/admin/technicians",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def repair_admin_technicians(self, **kwargs):
        user, error = self._ra_require_admin()
        if error:
            return error

        try:
            search_term = (
                request.httprequest.args.get("search")
                or ""
            ).strip().lower()

            users = self._ra_group_users(
                self.TECH_GROUP
            ).filtered(
                lambda item:
                    item.active
                    and not item.share
            )

            if search_term:
                users = users.filtered(
                    lambda item:
                        search_term
                        in (
                            item.display_name
                            or item.name
                            or ""
                        ).lower()
                        or search_term
                        in (
                            item.login
                            or ""
                        ).lower()
                )

            users = users.sorted(
                key=lambda item:
                    (
                        item.display_name
                        or item.name
                        or ""
                    ).lower()
            )

            items = []
            for technician in users:
                available = self._ra_technician_available(
                    technician
                )

                items.append(
                    {
                        "id": technician.id,
                        "name": (
                            technician.display_name
                            or technician.name
                            or ""
                        ),
                        "available": available,
                        "can_assign": available,
                    }
                )

            return self._json_response(
                {
                    "success": True,
                    "total": len(items),
                    "items": items,
                }
            )

        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/repairs/admin/create",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def repair_admin_create(self, **kwargs):
        user, error = self._ra_require_admin()
        if error:
            return error

        try:
            data = self._get_json_body()

            machine_id = self._ra_safe_int(
                data.get("machine_id"),
                0,
            )
            technician_id = self._ra_safe_int(
                data.get("technician_id")
                or data.get("responsible_id"),
                0,
            )

            if not machine_id:
                return self._json_response(
                    {
                        "success": False,
                        "code": "MACHINE_REQUIRED",
                        "message": (
                            "Debe seleccionar una máquina."
                        ),
                    },
                    status=400,
                )

            if not technician_id:
                return self._json_response(
                    {
                        "success": False,
                        "code": "TECHNICIAN_REQUIRED",
                        "message": (
                            "Debe seleccionar un técnico."
                        ),
                    },
                    status=400,
                )

            machine = self._ra_get_machine(machine_id)
            if not machine:
                return self._ra_machine_not_found()

            if (
                self._ra_safe_value(
                    machine,
                    "estado_ventas_id",
                    "",
                )
                != "para_revision"
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "MACHINE_NOT_IN_REVIEW_QUEUE",
                        "message": (
                            "Solo se puede crear la reparación "
                            "de una máquina que esté en "
                            "'Para revisión'."
                        ),
                    },
                    status=409,
                )

            existing = self._ra_get_existing_repair(machine)
            if existing:
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_ALREADY_EXISTS",
                        "message": (
                            "La máquina ya tiene una reparación "
                            "registrada."
                        ),
                        "repair": (
                            self._ra_serialize_repair_short(
                                existing
                            )
                        ),
                    },
                    status=409,
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
                            "El técnico seleccionado tiene "
                            "una ausencia o permiso activo "
                            "y no puede recibir la reparación."
                        ),
                    },
                    status=409,
                )

            Repair = request.env[
                self.REPAIR_MODEL
            ].sudo()

            # Se llama create() del modelo real.
            # Así se conservan:
            # - secuencia de reparación
            # - validación de técnico
            # - validación del modelo
            # - prueba automática
            # - carpeta pCloud
            # - QR
            # - carga de checklist/evaluaciones
            repair = Repair.create(
                {
                    "maquina_id": machine.id,
                    "responsable_id": technician.id,
                }
            )

            return self._json_response(
                {
                    "success": True,
                    "code": "REPAIR_CREATED",
                    "message": (
                        "Reparación creada y asignada "
                        "correctamente."
                    ),
                    "repair": (
                        self._ra_serialize_repair_detail(
                            repair
                        )
                    ),
                },
                status=201,
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
