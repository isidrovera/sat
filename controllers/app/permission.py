# -*- coding: utf-8 -*-

import base64
import logging

from odoo import http
from odoo.http import request

from .base import AppBaseController


_logger = logging.getLogger(__name__)


class AppPermissionController(
    AppBaseController
):

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/permissions",
            "/api/app/permissions/<int:permission_id>",
            "/api/app/permissions/<int:permission_id>/submit",
            "/api/app/permissions/<int:permission_id>/cancel",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def permission_options(
        self,
        permission_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # OWN PERMISSION
    # ============================================================

    def _get_permission(
        self,
        permission_id,
        user,
    ):
        return request.env[
            "mantenimiento.tecnico.ausencia"
        ].search(
            [
                (
                    "id",
                    "=",
                    permission_id,
                ),
                (
                    "tecnico_id",
                    "=",
                    user.id,
                ),
            ],
            limit=1,
        )

    # ============================================================
    # SERIALIZER
    # ============================================================

    def _serialize_permission(
        self,
        permission,
    ):
        return {
            "id": permission.id,
            "reference": (
                permission.name
                or ""
            ),
            "type": (
                permission.tipo
            ),
            "type_label": (
                self._selection_label(
                    permission,
                    "tipo",
                )
            ),
            "state": (
                permission.estado
            ),
            "state_label": (
                self._selection_label(
                    permission,
                    "estado",
                )
            ),
            "start_date": (
                permission.fecha_inicio
            ),
            "end_date": (
                permission.fecha_fin
            ),
            "full_day": (
                permission.dia_completo
            ),
            "start_hour": (
                permission.hora_inicio
            ),
            "end_hour": (
                permission.hora_fin
            ),
            "reason": (
                permission.motivo
                or False
            ),
            "attachment": bool(
                permission.adjunto
            ),
            "attachment_filename": (
                permission.adjunto_filename
                or False
            ),
            "administrative_evaluation": (
                permission.evaluacion_administrativa
            ),
            "administrative_evaluation_label": (
                self._selection_label(
                    permission,
                    "evaluacion_administrativa",
                )
            ),
            "hours": (
                permission.horas_permiso
            ),
            "hours_to_recover": (
                permission.horas_a_recuperar
            ),
            "recovery_deadline": (
                permission.fecha_limite_recuperacion
            ),
            "recovery_detail": (
                permission.detalle_recuperacion
                or False
            ),
            "approved_by": (
                self._many2one(
                    permission.aprobado_por_id
                )
                if permission.aprobado_por_id
                else False
            ),
            "approval_date": (
                permission.fecha_aprobacion
            ),
            "rejected_by": (
                self._many2one(
                    permission.rechazado_por_id
                )
                if permission.rechazado_por_id
                else False
            ),
            "rejection_date": (
                permission.fecha_rechazo
            ),
            "rejection_reason": (
                permission.motivo_rechazo
                or False
            ),
        }

    # ============================================================
    # LIST
    # ============================================================

    @http.route(
        "/api/app/permissions",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def permissions(
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

            domain = [
                (
                    "tecnico_id",
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

            records = request.env[
                "mantenimiento.tecnico.ausencia"
            ].search(
                domain,
                order=(
                    "fecha_inicio desc, "
                    "id desc"
                ),
                limit=100,
            )

            return self._json_response(
                {
                    "success": True,
                    "count": len(
                        records
                    ),
                    "items": [
                        self._serialize_permission(
                            item
                        )
                        for item
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
        "/api/app/permissions/<int:permission_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def permission_detail(
        self,
        permission_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            record = (
                self._get_permission(
                    permission_id,
                    user,
                )
            )

            if not record:
                return self._json_response(
                    {
                        "success": False,
                        "code": "PERMISSION_NOT_FOUND",
                        "message": (
                            "La solicitud no existe."
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "permission": (
                        self._serialize_permission(
                            record
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # CREATE
    # ============================================================

    @http.route(
        "/api/app/permissions",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def permission_create(
        self,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            data = self._get_json_body()

            permission_type = (
                str(
                    data.get("type")
                    or ""
                )
                .strip()
            )

            start_date = (
                data.get("start_date")
            )

            if not permission_type:
                return self._json_response(
                    {
                        "success": False,
                        "code": "TYPE_REQUIRED",
                        "message": (
                            "Selecciona el tipo "
                            "de permiso o ausencia."
                        ),
                    },
                    status=400,
                )

            if not start_date:
                return self._json_response(
                    {
                        "success": False,
                        "code": "START_DATE_REQUIRED",
                        "message": (
                            "Ingresa la fecha de inicio."
                        ),
                    },
                    status=400,
                )

            vals = {
                # Nunca aceptamos tecnico_id
                # enviado desde Flutter.
                "tecnico_id": user.id,
                "tipo": permission_type,
                "fecha_inicio": start_date,
                "fecha_fin": (
                    data.get("end_date")
                    or False
                ),
                "dia_completo": (
                    data.get(
                        "full_day",
                        True,
                    )
                ),
                "motivo": (
                    data.get("reason")
                    or False
                ),
            }

            if (
                not vals[
                    "dia_completo"
                ]
            ):
                vals[
                    "hora_inicio"
                ] = float(
                    data.get(
                        "start_hour",
                        0,
                    )
                )

                vals[
                    "hora_fin"
                ] = float(
                    data.get(
                        "end_hour",
                        0,
                    )
                )

            # ----------------------------------------------------
            # OPTIONAL ATTACHMENT
            # ----------------------------------------------------

            attachment_base64 = (
                data.get(
                    "attachment_base64"
                )
            )

            if attachment_base64:
                # Verifica que sea Base64 válido.
                base64.b64decode(
                    attachment_base64,
                    validate=True,
                )

                vals[
                    "adjunto"
                ] = attachment_base64

                vals[
                    "adjunto_filename"
                ] = (
                    data.get(
                        "attachment_filename"
                    )
                    or "documento"
                )

            Permission = request.env[
                "mantenimiento.tecnico.ausencia"
            ]

            record = Permission.create(
                vals
            )

            # ----------------------------------------------------
            # OPTIONAL IMMEDIATE SUBMIT
            # ----------------------------------------------------

            if (
                data.get("submit")
                is True
            ):
                record.action_enviar_aprobacion()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Solicitud creada correctamente."
                    ),
                    "permission": (
                        self._serialize_permission(
                            record
                        )
                    ),
                },
                status=201,
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # UPDATE DRAFT
    # ============================================================

    @http.route(
        "/api/app/permissions/<int:permission_id>",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def permission_update(
        self,
        permission_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            record = (
                self._get_permission(
                    permission_id,
                    user,
                )
            )

            if not record:
                return self._json_response(
                    {
                        "success": False,
                        "code": "PERMISSION_NOT_FOUND",
                        "message": (
                            "Solicitud no encontrada."
                        ),
                    },
                    status=404,
                )

            if record.estado not in (
                "borrador",
                "rechazado",
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "PERMISSION_NOT_EDITABLE",
                        "message": (
                            "Solo puedes editar "
                            "solicitudes en borrador "
                            "o rechazadas."
                        ),
                    },
                    status=400,
                )

            data = self._get_json_body()

            mapping = {
                "type": "tipo",
                "start_date": "fecha_inicio",
                "end_date": "fecha_fin",
                "full_day": "dia_completo",
                "start_hour": "hora_inicio",
                "end_hour": "hora_fin",
                "reason": "motivo",
            }

            vals = {}

            for api_field, model_field in mapping.items():
                if api_field in data:
                    vals[
                        model_field
                    ] = data[
                        api_field
                    ]

            if not vals:
                return self._json_response(
                    {
                        "success": False,
                        "code": "NO_DATA",
                        "message": (
                            "No se recibieron cambios."
                        ),
                    },
                    status=400,
                )

            record.write(
                vals
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Solicitud actualizada correctamente."
                    ),
                    "permission": (
                        self._serialize_permission(
                            record
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # SUBMIT
    # ============================================================

    @http.route(
        "/api/app/permissions/<int:permission_id>/submit",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def permission_submit(
        self,
        permission_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            record = (
                self._get_permission(
                    permission_id,
                    user,
                )
            )

            if not record:
                return self._json_response(
                    {
                        "success": False,
                        "code": "PERMISSION_NOT_FOUND",
                        "message": (
                            "Solicitud no encontrada."
                        ),
                    },
                    status=404,
                )

            record.action_enviar_aprobacion()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Solicitud enviada "
                        "para aprobación."
                    ),
                    "permission": (
                        self._serialize_permission(
                            record
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # CANCEL
    # ============================================================

    @http.route(
        "/api/app/permissions/<int:permission_id>/cancel",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def permission_cancel(
        self,
        permission_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            record = (
                self._get_permission(
                    permission_id,
                    user,
                )
            )

            if not record:
                return self._json_response(
                    {
                        "success": False,
                        "code": "PERMISSION_NOT_FOUND",
                        "message": (
                            "Solicitud no encontrada."
                        ),
                    },
                    status=404,
                )

            record.action_cancelar()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Solicitud cancelada."
                    ),
                    "permission": (
                        self._serialize_permission(
                            record
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )