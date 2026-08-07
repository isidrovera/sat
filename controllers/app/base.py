# -*- coding: utf-8 -*-

import json
import logging
import re
from datetime import date, datetime

from odoo import http
from odoo.exceptions import (
    AccessError,
    AccessDenied,
    UserError,
    ValidationError,
)
from odoo.http import request


_logger = logging.getLogger(__name__)


_ALLOWED_ORIGINS = {
    "https://andessolutioncopiers.com",
}


class AppHomeController(
    AppBaseController
):

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        "/api/app/home",
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def home_options(
        self,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # USER
    # ============================================================

    def _serialize_user(
        self,
        user,
    ):
        employee = False

        if (
            "employee_id"
            in user._fields
            and user.employee_id
        ):
            employee = {
                "id": user.employee_id.id,
                "name": user.employee_id.name,
                "job_title": (
                    user.employee_id.job_title
                    if "job_title"
                    in user.employee_id._fields
                    else False
                ),
            }

        return {
            "id": user.id,
            "name": user.name,
            "login": user.login,
            "company": self._many2one(
                user.company_id
            ),
            "employee": employee,
        }

    # ============================================================
    # TODAY RANGE
    # ============================================================

    def _today_utc_range(
        self,
        user,
    ):
        tz_name = (
            user.tz
            or "America/Lima"
        )

        try:
            timezone = pytz.timezone(
                tz_name
            )
        except Exception:
            timezone = pytz.timezone(
                "America/Lima"
            )

        now_local = datetime.now(
            timezone
        )

        start_local = timezone.localize(
            datetime.combine(
                now_local.date(),
                time.min,
            )
        )

        end_local = timezone.localize(
            datetime.combine(
                now_local.date(),
                time.max,
            )
        )

        start_utc = (
            start_local
            .astimezone(pytz.UTC)
            .replace(tzinfo=None)
        )

        end_utc = (
            end_local
            .astimezone(pytz.UTC)
            .replace(tzinfo=None)
        )

        return (
            fields.Datetime.to_string(
                start_utc
            ),
            fields.Datetime.to_string(
                end_utc
            ),
        )

    # ============================================================
    # RECENT ACTIVITY
    # ============================================================

    def _recent_activity(
        self,
        user,
    ):
        result = []

        # --------------------------------------------------------
        # Servicios
        # --------------------------------------------------------

        if self._can_read_model(
            "ticket.alquiler"
        ):
            tickets = request.env[
                "ticket.alquiler"
            ].search(
                [
                    (
                        "responsable",
                        "=",
                        user.id,
                    ),
                ],
                order="write_date desc",
                limit=3,
            )

            for ticket in tickets:
                result.append(
                    {
                        "type": "service",
                        "id": ticket.id,
                        "reference": (
                            ticket.name
                            or ""
                        ),
                        "title": (
                            ticket.nombre_cliente
                            if "nombre_cliente"
                            in ticket._fields
                            else ticket.display_name
                        ),
                        "status": (
                            ticket.estado
                        ),
                        "status_label": (
                            self._selection_label(
                                ticket,
                                "estado",
                            )
                        ),
                        "date": (
                            ticket.write_date
                        ),
                    }
                )

        # --------------------------------------------------------
        # Reparaciones
        # --------------------------------------------------------

        if self._can_read_model(
            "reparaciones.reparaciones"
        ):
            repairs = request.env[
                "reparaciones.reparaciones"
            ].search(
                [
                    (
                        "responsable_id",
                        "=",
                        user.id,
                    ),
                ],
                order="write_date desc",
                limit=3,
            )

            for repair in repairs:
                result.append(
                    {
                        "type": "repair",
                        "id": repair.id,
                        "reference": (
                            repair.name
                            or ""
                        ),
                        "title": (
                            repair.serie_id
                            or repair.display_name
                        ),
                        "status": (
                            repair.estado_id
                        ),
                        "status_label": (
                            self._selection_label(
                                repair,
                                "estado_id",
                            )
                        ),
                        "date": (
                            repair.write_date
                        ),
                    }
                )

        # --------------------------------------------------------
        # Permisos
        # --------------------------------------------------------

        if self._can_read_model(
            "mantenimiento.tecnico.ausencia"
        ):
            permissions = request.env[
                "mantenimiento.tecnico.ausencia"
            ].search(
                [
                    (
                        "tecnico_id",
                        "=",
                        user.id,
                    ),
                ],
                order="write_date desc",
                limit=3,
            )

            for permission in permissions:
                result.append(
                    {
                        "type": "permission",
                        "id": permission.id,
                        "reference": (
                            permission.name
                            or ""
                        ),
                        "title": (
                            self._selection_label(
                                permission,
                                "tipo",
                            )
                        ),
                        "status": (
                            permission.estado
                        ),
                        "status_label": (
                            self._selection_label(
                                permission,
                                "estado",
                            )
                        ),
                        "date": (
                            permission.write_date
                        ),
                    }
                )

        result.sort(
            key=lambda item: (
                item.get("date")
                or datetime.min
            ),
            reverse=True,
        )

        return result[:5]

    # ============================================================
    # HOME
    # ============================================================

    @http.route(
        "/api/app/home",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def home(
        self,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            start_today, end_today = (
                self._today_utc_range(
                    user
                )
            )

            # ====================================================
            # SERVICES
            # ====================================================

            service_visible = (
                self._can_read_model(
                    "ticket.alquiler"
                )
            )

            services_active = 0
            services_today = 0

            if service_visible:
                Ticket = request.env[
                    "ticket.alquiler"
                ]

                services_active = (
                    Ticket.search_count(
                        [
                            (
                                "responsable",
                                "=",
                                user.id,
                            ),
                            (
                                "estado",
                                "!=",
                                "finalizado",
                            ),
                        ]
                    )
                )

                services_today = (
                    Ticket.search_count(
                        [
                            (
                                "responsable",
                                "=",
                                user.id,
                            ),
                            (
                                "agenda",
                                ">=",
                                start_today,
                            ),
                            (
                                "agenda",
                                "<=",
                                end_today,
                            ),
                        ]
                    )
                )

            # ====================================================
            # REPAIRS
            # ====================================================

            repair_visible = (
                self._can_read_model(
                    "reparaciones.reparaciones"
                )
            )

            repairs_active = 0

            if repair_visible:
                Repair = request.env[
                    "reparaciones.reparaciones"
                ]

                repairs_active = (
                    Repair.search_count(
                        [
                            (
                                "responsable_id",
                                "=",
                                user.id,
                            ),
                            (
                                "estado_id",
                                "not in",
                                [
                                    "finalizado",
                                    "entregada",
                                ],
                            ),
                        ]
                    )
                )

            # ====================================================
            # PERMISSIONS
            # ====================================================

            permission_visible = (
                self._can_read_model(
                    "mantenimiento.tecnico.ausencia"
                )
            )

            permission_count = 0
            permission_pending = 0

            if permission_visible:
                Permission = request.env[
                    "mantenimiento.tecnico.ausencia"
                ]

                permission_count = (
                    Permission.search_count(
                        [
                            (
                                "tecnico_id",
                                "=",
                                user.id,
                            ),
                        ]
                    )
                )

                permission_pending = (
                    Permission.search_count(
                        [
                            (
                                "tecnico_id",
                                "=",
                                user.id,
                            ),
                            (
                                "estado",
                                "=",
                                "pendiente",
                            ),
                        ]
                    )
                )

            return self._json_response(
                {
                    "success": True,
                    "user": (
                        self._serialize_user(
                            user
                        )
                    ),
                    "modules": {
                        "services": {
                            "visible": (
                                service_visible
                            ),
                            "count": (
                                services_active
                            ),
                            "today": (
                                services_today
                            ),
                        },
                        "repairs": {
                            "visible": (
                                repair_visible
                            ),
                            "count": (
                                repairs_active
                            ),
                        },
                        "permissions": {
                            "visible": (
                                permission_visible
                            ),
                            "can_create": (
                                self._can_create_model(
                                    "mantenimiento.tecnico.ausencia"
                                )
                            ),
                            "count": (
                                permission_count
                            ),
                            "pending": (
                                permission_pending
                            ),
                        },
                        "profile": {
                            "visible": True,
                        },
                    },
                    "recent_activity": (
                        self._recent_activity(
                            user
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )