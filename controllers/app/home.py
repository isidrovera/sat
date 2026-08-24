# -*- coding: utf-8 -*-

import logging
from datetime import datetime, time

import pytz

from odoo import fields, http
from odoo.http import request

from .base import AppBaseController


_logger = logging.getLogger(__name__)


class AppHomeController(AppBaseController):

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
    def home_options(self, **kwargs):
        return self._options_response()

    # ============================================================
    # USER
    # ============================================================

    def _serialize_user(self, user):
        employee = False

        if (
            "employee_id" in user._fields
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
    # TODAY
    # ============================================================

    def _today_utc_range(self, user):
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
    def home(self, **kwargs):
        user, error = self._require_user()

        if error:
            return error

        try:
            start_today, end_today = (
                self._today_utc_range(
                    user
                )
            )

            # ====================================================
            # APP AREAS / GROUP PERMISSIONS
            # ====================================================

            is_system = user.has_group(
                "base.group_system"
            )

            is_sales = user.has_group(
                "sat.Sat_ventas_group_user"
            )

            is_logistics = user.has_group(
                "sat.sat_logistica_group_user"
            )

            is_technical = user.has_group(
                "sat.sat_tecnica_group_user"
            )

            is_head = user.has_group(
                "sat.sat_jefes_group_user"
            )

            is_commercial_authorizer = user.has_group(
                "sat.group_reserva_comercial_autorizado"
            )

            sales_visible = bool(
                is_sales
                or is_head
                or is_commercial_authorizer
                or is_system
            )

            logistics_visible = bool(
                is_logistics
                or is_head
                or is_system
            )

            # ====================================================
            # SERVICES
            # ====================================================

            service_visible = bool(
                (
                    is_technical
                    or is_head
                    or is_system
                )
                and self._can_read_model(
                    "ticket.alquiler"
                )
            )

            services_active = 0
            services_today = 0

            services_process = 0
            services_on_route = 0
            services_on_site = 0
            services_in_review = 0

            if service_visible:
                Ticket = request.env[
                    "ticket.alquiler"
                ]

                base_domain = [
                    (
                        "responsable",
                        "=",
                        user.id,
                    ),
                ]

                # ----------------------------------------------
                # TODOS LOS SERVICIOS SIN FINALIZAR
                # ----------------------------------------------

                services_active = (
                    Ticket.search_count(
                        base_domain
                        + [
                            (
                                "estado",
                                "!=",
                                "finalizado",
                            ),
                        ]
                    )
                )

                # ----------------------------------------------
                # SERVICIOS AGENDADOS PARA HOY
                # ----------------------------------------------

                services_today = (
                    Ticket.search_count(
                        base_domain
                        + [
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

                # ----------------------------------------------
                # ESTADO: PROCESO
                # ----------------------------------------------

                services_process = (
                    Ticket.search_count(
                        base_domain
                        + [
                            (
                                "estado",
                                "=",
                                "proceso",
                            ),
                        ]
                    )
                )

                # ----------------------------------------------
                # ESTADO: EN RUTA
                # ----------------------------------------------

                services_on_route = (
                    Ticket.search_count(
                        base_domain
                        + [
                            (
                                "estado",
                                "=",
                                "en_ruta",
                            ),
                        ]
                    )
                )

                # ----------------------------------------------
                # ESTADO: EN SITIO
                # ----------------------------------------------

                services_on_site = (
                    Ticket.search_count(
                        base_domain
                        + [
                            (
                                "estado",
                                "=",
                                "en_sitio",
                            ),
                        ]
                    )
                )

                # ----------------------------------------------
                # ESTADO: EN REVISIÓN
                # ----------------------------------------------

                services_in_review = (
                    Ticket.search_count(
                        base_domain
                        + [
                            (
                                "estado",
                                "=",
                                "en_revision",
                            ),
                        ]
                    )
                )

            # ====================================================
            # REPAIRS
            # ====================================================

            repair_visible = bool(
                (
                    is_technical
                    or is_head
                    or is_system
                )
                and self._can_read_model(
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

            permission_visible = bool(
                (
                    is_technical
                    or is_head
                    or is_system
                )
                and self._can_read_model(
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

            # ====================================================
            # RESPONSE
            # ====================================================

            return self._json_response(
                {
                    "success": True,

                    "user": self._serialize_user(
                        user
                    ),

                    "modules": {
                        "sales": {
                            "visible":
                                sales_visible,
                        },

                        "logistics": {
                            "visible":
                                logistics_visible,
                        },

                        "services": {
                            "visible":
                                service_visible,

                            # Total actualmente no finalizado.
                            "count":
                                services_active,

                            # Alias explícito para Flutter.
                            "unfinished":
                                services_active,

                            # Agendados para hoy.
                            "today":
                                services_today,

                            # Desglose por estado.
                            "process":
                                services_process,

                            "on_route":
                                services_on_route,

                            "on_site":
                                services_on_site,

                            "in_review":
                                services_in_review,
                        },

                        "repairs": {
                            "visible":
                                repair_visible,

                            "count":
                                repairs_active,
                        },

                        "permissions": {
                            "visible":
                                permission_visible,

                            "can_create": (
                                self._can_create_model(
                                    "mantenimiento.tecnico.ausencia"
                                )
                            ),

                            "count":
                                permission_count,

                            "pending":
                                permission_pending,
                        },

                        "profile": {
                            "visible":
                                True,
                        },
                    },
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando /api/app/home"
            )

            return self._error_response(
                exc
            )