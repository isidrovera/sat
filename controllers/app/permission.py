# -*- coding: utf-8 -*-

import base64
import binascii
import calendar
import logging
from datetime import datetime

from odoo import fields, http
from odoo.http import request

from .base import AppBaseController


_logger = logging.getLogger(__name__)


class AppPermissionController(
    AppBaseController
):

    # ============================================================
    # CONSTANTES
    # ============================================================

    MODEL_NAME = (
        "mantenimiento.tecnico.ausencia"
    )

    DEFAULT_ALLOWED_TECHNICIAN_TYPES = (
        "permiso",
        "vacaciones",
        "enfermedad",
        "descanso_medico",
        "capacitacion",
    )

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/permissions",
            "/api/app/permissions/config",
            "/api/app/permissions/summary",
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
    # MODEL
    # ============================================================

    def _permission_model(
        self,
    ):
        return request.env[
            self.MODEL_NAME
        ]

    # ============================================================
    # OWN PERMISSION
    # ============================================================

    def _get_permission(
        self,
        permission_id,
        user,
    ):
        return self._permission_model().search(
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
    # SELECTION HELPERS
    # ============================================================

    def _get_selection_options(
        self,
        model,
        field_name,
    ):
        field = model._fields.get(
            field_name
        )

        if not field:
            return []

        selection = (
            field.selection
        )

        if callable(selection):
            try:
                selection = selection(
                    model
                )
            except TypeError:
                selection = selection(
                    model.env
                )

        return [
            {
                "value": value,
                "label": label,
            }
            for value, label
            in (
                selection
                or []
            )
        ]

    # ============================================================
    # ALLOWED TECHNICIAN TYPES
    # ============================================================

    def _get_allowed_technician_types(
        self,
    ):
        """
        Configurable desde:
            sat.app_permission_allowed_types

        Ejemplo:
            permiso,vacaciones,enfermedad,descanso_medico,capacitacion
        """

        ICP = request.env[
            "ir.config_parameter"
        ].sudo()

        configured = (
            ICP.get_param(
                "sat.app_permission_allowed_types"
            )
            or ""
        ).strip()

        if configured:
            values = [
                item.strip()
                for item
                in configured.split(",")
                if item.strip()
            ]

            if values:
                return tuple(
                    values
                )

        return (
            self.DEFAULT_ALLOWED_TECHNICIAN_TYPES
        )

    def _get_technician_type_options(
        self,
    ):
        Permission = (
            self._permission_model()
        )

        allowed = set(
            self._get_allowed_technician_types()
        )

        options = (
            self._get_selection_options(
                Permission,
                "tipo",
            )
        )

        return [
            item
            for item
            in options
            if item["value"]
            in allowed
        ]

    def _is_allowed_technician_type(
        self,
        permission_type,
    ):
        return (
            permission_type
            in self._get_allowed_technician_types()
        )

    # ============================================================
    # TYPE RULES
    # ============================================================

    def _get_technician_type_rules(
        self,
    ):
        """
        Obtiene las reglas desde el modelo Odoo.

        Flutter no debe inventar:
        - si permite horas
        - si fuerza día completo
        - si fecha fin es obligatoria
        - si sustento es obligatorio
        - horarios sugeridos
        """

        Permission = (
            self._permission_model()
        )

        allowed = set(
            self._get_allowed_technician_types()
        )

        if not hasattr(
            Permission,
            "get_app_permission_type_rules",
        ):
            _logger.warning(
                "[App Permisos] "
                "El modelo no tiene "
                "get_app_permission_type_rules()."
            )
            return {}

        rules = (
            Permission.get_app_permission_type_rules()
            or {}
        )

        return {
            key: value
            for key, value
            in rules.items()
            if key in allowed
        }

    # ============================================================
    # ACTIONS AVAILABLE FOR TECHNICIAN
    # ============================================================

    def _permission_actions(
        self,
        permission,
    ):
        """
        Flutter recibe acciones disponibles.

        La validación definitiva sigue
        estando en los métodos del modelo.
        """

        state = (
            permission.estado
            or ""
        )

        editable = (
            state
            in (
                "borrador",
                "rechazado",
            )
        )

        can_submit = (
            state
            in (
                "borrador",
                "rechazado",
            )
        )

        can_cancel = (
            state
            in (
                "borrador",
                "pendiente",
            )
        )

        return {
            "editable": editable,
            "read_only": (
                not editable
            ),
            "can_submit": can_submit,
            "can_cancel": can_cancel,
        }

    # ============================================================
    # RESULT VISIBLE TO TECHNICIAN
    # ============================================================

    def _technician_result(
        self,
        permission,
    ):
        result = {
            "show": False,
            "evaluation": False,
            "evaluation_label": False,
            "hours_to_recover": 0.0,
            "recovery_deadline": False,
            "recovery_detail": False,
        }

        if permission.estado not in (
            "aprobado",
            "ausente_activo",
            "cerrado",
        ):
            return result

        evaluation = (
            permission.evaluacion_administrativa
            or False
        )

        if not evaluation:
            return result

        if evaluation in (
            "pendiente",
            "no_aplica",
        ):
            return result

        result[
            "show"
        ] = True

        result[
            "evaluation"
        ] = evaluation

        result[
            "evaluation_label"
        ] = self._selection_label(
            permission,
            "evaluacion_administrativa",
        )

        if (
            evaluation
            == "recuperar_horas"
        ):
            result[
                "hours_to_recover"
            ] = (
                permission.horas_a_recuperar
                or 0.0
            )

            result[
                "recovery_deadline"
            ] = (
                permission.fecha_limite_recuperacion
                or False
            )

            result[
                "recovery_detail"
            ] = (
                permission.detalle_recuperacion
                or False
            )

        return result

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

            "hours": (
                permission.horas_permiso
                or 0.0
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

            "approved_by": (
                self._many2one(
                    permission.aprobado_por_id
                )
                if permission.aprobado_por_id
                else False
            ),

            "approval_date": (
                permission.fecha_aprobacion
                or False
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
                or False
            ),

            "rejection_reason": (
                permission.motivo_rechazo
                or False
            ),

            "result": (
                self._technician_result(
                    permission
                )
            ),

            "actions": (
                self._permission_actions(
                    permission
                )
            ),
        }

    # ============================================================
    # CONFIG
    # ============================================================

    @http.route(
        "/api/app/permissions/config",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def permission_config(
        self,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            Permission = (
                self._permission_model()
            )

            today = (
                fields.Date.context_today(
                    user
                )
            )

            return self._json_response(
                {
                    "success": True,

                    "types": (
                        self._get_technician_type_options()
                    ),

                    "type_rules": (
                        self._get_technician_type_rules()
                    ),

                    "states": (
                        self._get_selection_options(
                            Permission,
                            "estado",
                        )
                    ),

                    "defaults": {
                        "start_date": today,
                        "end_date": today,
                        "full_day": True,
                    },

                    "form": {
                        "show_type": True,
                        "show_start_date": True,
                        "show_end_date": True,
                        "show_full_day": True,
                        "show_hours_when_partial": True,
                        "show_reason": True,
                        "show_attachment": True,
                    },

                    "fields": {
                        "type": {
                            "required": True,
                        },
                        "start_date": {
                            "required": True,
                        },
                        "end_date": {
                            "required": False,
                        },
                        "full_day": {
                            "required": True,
                        },
                        "start_hour": {
                            "required": False,
                        },
                        "end_hour": {
                            "required": False,
                        },
                        "reason": {
                            "required": False,
                        },
                        "attachment": {
                            "required": False,
                        },
                    },

                    "capabilities": {
                        "can_create": True,
                        "can_view_own": True,
                        "can_view_month_summary": True,
                        "can_approve": False,
                        "can_reject": False,
                        "can_manage_administration": False,
                    },
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # MONTH RANGE
    # ============================================================

    def _get_month_range(
        self,
        month_value,
        user,
    ):
        today = (
            fields.Date.context_today(
                user
            )
        )

        if not month_value:
            year = today.year
            month = today.month

        else:
            try:
                parsed = datetime.strptime(
                    month_value,
                    "%Y-%m",
                )

                year = parsed.year
                month = parsed.month

            except ValueError:
                return False

        last_day = (
            calendar.monthrange(
                year,
                month,
            )[1]
        )

        start_date = datetime(
            year,
            month,
            1,
        ).date()

        end_date = datetime(
            year,
            month,
            last_day,
        ).date()

        return {
            "key": (
                "%04d-%02d"
                % (
                    year,
                    month,
                )
            ),
            "year": year,
            "month": month,
            "start_date": start_date,
            "end_date": end_date,
        }

    # ============================================================
    # MONTH SUMMARY
    # ============================================================

    @http.route(
        "/api/app/permissions/summary",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def permission_summary(
        self,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            month_value = (
                request.httprequest.args.get(
                    "month"
                )
            )

            month_data = (
                self._get_month_range(
                    month_value,
                    user,
                )
            )

            if not month_data:
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_MONTH",
                        "message": (
                            "El mes debe enviarse "
                            "con formato YYYY-MM."
                        ),
                    },
                    status=400,
                )

            records = (
                self._permission_model().search(
                    [
                        (
                            "tecnico_id",
                            "=",
                            user.id,
                        ),
                        (
                            "fecha_inicio",
                            "<=",
                            month_data[
                                "end_date"
                            ],
                        ),
                        "|",
                        (
                            "fecha_fin",
                            "=",
                            False,
                        ),
                        (
                            "fecha_fin",
                            ">=",
                            month_data[
                                "start_date"
                            ],
                        ),
                    ],
                    order=(
                        "fecha_inicio desc, "
                        "id desc"
                    ),
                )
            )

            counters = {
                "draft": 0,
                "pending": 0,
                "approved": 0,
                "rejected": 0,
                "active_absence": 0,
                "closed": 0,
                "cancelled": 0,
            }

            full_day_requests = 0
            partial_requests = 0

            total_hours = 0.0
            approved_hours = 0.0
            hours_to_recover = 0.0

            state_map = {
                "borrador": "draft",
                "pendiente": "pending",
                "aprobado": "approved",
                "rechazado": "rejected",
                "ausente_activo": "active_absence",
                "cerrado": "closed",
                "cancelado": "cancelled",
            }

            approved_states = {
                "aprobado",
                "ausente_activo",
                "cerrado",
            }

            for record in records:
                state = (
                    record.estado
                    or ""
                )

                counter_key = (
                    state_map.get(
                        state
                    )
                )

                if counter_key:
                    counters[
                        counter_key
                    ] += 1

                if record.dia_completo:
                    full_day_requests += 1

                else:
                    partial_requests += 1

                    hours = (
                        record.horas_permiso
                        or 0.0
                    )

                    total_hours += hours

                    if state in approved_states:
                        approved_hours += hours

                if (
                    record.evaluacion_administrativa
                    == "recuperar_horas"
                    and state in approved_states
                ):
                    hours_to_recover += (
                        record.horas_a_recuperar
                        or 0.0
                    )

            return self._json_response(
                {
                    "success": True,

                    "month": (
                        month_data[
                            "key"
                        ]
                    ),

                    "period": {
                        "start_date": (
                            month_data[
                                "start_date"
                            ]
                        ),
                        "end_date": (
                            month_data[
                                "end_date"
                            ]
                        ),
                    },

                    "summary": {
                        "total": len(
                            records
                        ),
                        **counters,
                        "full_day_requests": (
                            full_day_requests
                        ),
                        "partial_requests": (
                            partial_requests
                        ),
                        "total_hours": (
                            total_hours
                        ),
                        "approved_hours": (
                            approved_hours
                        ),
                        "hours_to_recover": (
                            hours_to_recover
                        ),
                    },
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

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

            month_value = (
                request.httprequest.args.get(
                    "month"
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

            if month_value:
                month_data = (
                    self._get_month_range(
                        month_value,
                        user,
                    )
                )

                if not month_data:
                    return self._json_response(
                        {
                            "success": False,
                            "code": "INVALID_MONTH",
                            "message": (
                                "El mes debe enviarse "
                                "con formato YYYY-MM."
                            ),
                        },
                        status=400,
                    )

                domain.extend(
                    [
                        (
                            "fecha_inicio",
                            "<=",
                            month_data[
                                "end_date"
                            ],
                        ),
                        "|",
                        (
                            "fecha_fin",
                            "=",
                            False,
                        ),
                        (
                            "fecha_fin",
                            ">=",
                            month_data[
                                "start_date"
                            ],
                        ),
                    ]
                )

            records = (
                self._permission_model().search(
                    domain,
                    order=(
                        "fecha_inicio desc, "
                        "id desc"
                    ),
                    limit=100,
                )
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
    # VALIDATE TYPE
    # ============================================================

    def _validate_permission_type(
        self,
        permission_type,
    ):
        if not permission_type:
            return (
                "TYPE_REQUIRED",
                (
                    "Selecciona el tipo "
                    "de permiso o ausencia."
                ),
            )

        if not (
            self._is_allowed_technician_type(
                permission_type
            )
        ):
            return (
                "TYPE_NOT_ALLOWED",
                (
                    "Este tipo de ausencia "
                    "no puede ser solicitado "
                    "desde la aplicación."
                ),
            )

        return False

    # ============================================================
    # ATTACHMENT
    # ============================================================

    def _prepare_attachment(
        self,
        data,
        vals,
    ):
        if (
            "attachment_base64"
            not in data
        ):
            return

        attachment_base64 = (
            data.get(
                "attachment_base64"
            )
        )

        if not attachment_base64:
            vals[
                "adjunto"
            ] = False

            vals[
                "adjunto_filename"
            ] = False

            return

        if isinstance(
            attachment_base64,
            str,
        ):
            attachment_base64 = (
                attachment_base64.strip()
            )

            if (
                attachment_base64.startswith(
                    "data:"
                )
                and ","
                in attachment_base64
            ):
                attachment_base64 = (
                    attachment_base64.split(
                        ",",
                        1,
                    )[1]
                )

        try:
            base64.b64decode(
                attachment_base64,
                validate=True,
            )

        except (
            binascii.Error,
            ValueError,
            TypeError,
        ):
            raise ValueError(
                "El archivo adjunto "
                "no contiene Base64 válido."
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
            data = (
                self._get_json_body()
            )

            permission_type = (
                str(
                    data.get(
                        "type"
                    )
                    or ""
                )
                .strip()
            )

            type_error = (
                self._validate_permission_type(
                    permission_type
                )
            )

            if type_error:
                code, message = (
                    type_error
                )

                return self._json_response(
                    {
                        "success": False,
                        "code": code,
                        "message": message,
                    },
                    status=400,
                )

            start_date = (
                data.get(
                    "start_date"
                )
            )

            if not start_date:
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "START_DATE_REQUIRED"
                        ),
                        "message": (
                            "Ingresa la fecha "
                            "de inicio."
                        ),
                    },
                    status=400,
                )

            vals = {
                "tecnico_id": (
                    user.id
                ),
                "tipo": (
                    permission_type
                ),
                "fecha_inicio": (
                    start_date
                ),
                "fecha_fin": (
                    data.get(
                        "end_date"
                    )
                    or False
                ),
                "dia_completo": (
                    data.get(
                        "full_day",
                        True,
                    )
                ),
                "motivo": (
                    data.get(
                        "reason"
                    )
                    or False
                ),
            }

            if not vals[
                "dia_completo"
            ]:
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

            self._prepare_attachment(
                data,
                vals,
            )

            record = (
                self._permission_model().create(
                    vals
                )
            )

            if (
                data.get(
                    "submit"
                )
                is True
            ):
                record.action_enviar_aprobacion()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Solicitud creada "
                        "correctamente."
                    ),
                    "permission": (
                        self._serialize_permission(
                            record
                        )
                    ),
                },
                status=201,
            )

        except ValueError as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_DATA",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # UPDATE
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
                        "code": (
                            "PERMISSION_NOT_FOUND"
                        ),
                        "message": (
                            "Solicitud no encontrada."
                        ),
                    },
                    status=404,
                )

            actions = (
                self._permission_actions(
                    record
                )
            )

            if not actions[
                "editable"
            ]:
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "PERMISSION_NOT_EDITABLE"
                        ),
                        "message": (
                            "Esta solicitud "
                            "ya no puede editarse."
                        ),
                    },
                    status=400,
                )

            data = (
                self._get_json_body()
            )

            vals = {}

            if "type" in data:
                permission_type = (
                    str(
                        data.get(
                            "type"
                        )
                        or ""
                    )
                    .strip()
                )

                type_error = (
                    self._validate_permission_type(
                        permission_type
                    )
                )

                if type_error:
                    code, message = (
                        type_error
                    )

                    return self._json_response(
                        {
                            "success": False,
                            "code": code,
                            "message": message,
                        },
                        status=400,
                    )

                vals[
                    "tipo"
                ] = permission_type

            mapping = {
                "start_date": (
                    "fecha_inicio"
                ),
                "end_date": (
                    "fecha_fin"
                ),
                "full_day": (
                    "dia_completo"
                ),
                "start_hour": (
                    "hora_inicio"
                ),
                "end_hour": (
                    "hora_fin"
                ),
                "reason": (
                    "motivo"
                ),
            }

            for (
                api_field,
                model_field,
            ) in mapping.items():

                if api_field in data:
                    vals[
                        model_field
                    ] = data[
                        api_field
                    ]

            self._prepare_attachment(
                data,
                vals,
            )

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
                        "Solicitud actualizada "
                        "correctamente."
                    ),
                    "permission": (
                        self._serialize_permission(
                            record
                        )
                    ),
                }
            )

        except ValueError as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_DATA",
                    "message": str(
                        exc
                    ),
                },
                status=400,
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
                        "code": (
                            "PERMISSION_NOT_FOUND"
                        ),
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
                        "code": (
                            "PERMISSION_NOT_FOUND"
                        ),
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
