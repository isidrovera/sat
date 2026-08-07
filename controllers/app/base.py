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


class AppBaseController(http.Controller):

    # ============================================================
    # CORS
    # ============================================================

    def _is_allowed_origin(
        self,
        origin,
    ):
        if not origin:
            return False

        if origin in _ALLOWED_ORIGINS:
            return True

        if re.match(
            r"^https?://localhost(?::\d+)?$",
            origin,
        ):
            return True

        if re.match(
            r"^https?://127\.0\.0\.1(?::\d+)?$",
            origin,
        ):
            return True

        return False

    def _cors_headers(
        self,
    ):
        origin = (
            request.httprequest
            .headers
            .get("Origin")
        )

        headers = [
            (
                "Access-Control-Allow-Methods",
                "GET, POST, PATCH, PUT, DELETE, OPTIONS",
            ),
            (
                "Access-Control-Allow-Headers",
                "Content-Type, Accept, Authorization",
            ),
            (
                "Access-Control-Allow-Credentials",
                "true",
            ),
            (
                "Access-Control-Max-Age",
                "86400",
            ),
        ]

        if (
            origin
            and self._is_allowed_origin(
                origin
            )
        ):
            headers.extend(
                [
                    (
                        "Access-Control-Allow-Origin",
                        origin,
                    ),
                    (
                        "Vary",
                        "Origin",
                    ),
                ]
            )

        return headers

    def _options_response(
        self,
    ):
        origin = (
            request.httprequest
            .headers
            .get("Origin")
        )

        if (
            origin
            and not self._is_allowed_origin(
                origin
            )
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "ORIGIN_NOT_ALLOWED",
                    "message": (
                        "El origen de la solicitud "
                        "no está autorizado."
                    ),
                },
                status=403,
            )

        return request.make_response(
            "",
            headers=self._cors_headers(),
            status=204,
        )

    # ============================================================
    # JSON
    # ============================================================

    def _json_response(
        self,
        data,
        status=200,
    ):
        headers = [
            (
                "Content-Type",
                "application/json; charset=utf-8",
            ),
            (
                "Cache-Control",
                "no-store",
            ),
        ]

        headers.extend(
            self._cors_headers()
        )

        return request.make_response(
            json.dumps(
                data,
                ensure_ascii=False,
                default=self._json_default,
            ),
            headers=headers,
            status=status,
        )

    def _json_default(
        self,
        value,
    ):
        if isinstance(
            value,
            (datetime, date),
        ):
            return value.isoformat()

        return str(value)

    def _get_json_body(
        self,
    ):
        try:
            data = (
                request.httprequest
                .get_json(
                    silent=True,
                )
            )

            if isinstance(
                data,
                dict,
            ):
                return data

        except Exception:
            _logger.exception(
                "No se pudo interpretar "
                "el JSON recibido."
            )

        return {}

    # ============================================================
    # SESSION / AUTH
    # ============================================================

    def _require_user(
        self,
    ):
        """
        Valida manualmente la sesión Odoo.

        Devuelve:

            (user, None)

        cuando la sesión es válida.

        Devuelve:

            (None, response)

        cuando la sesión no existe o expiró.
        """

        uid = request.session.uid

        if not uid:
            return (
                None,
                self._json_response(
                    {
                        "success": False,
                        "authenticated": False,
                        "code": "SESSION_EXPIRED",
                        "message": (
                            "La sesión ha expirado "
                            "o no existe una sesión activa."
                        ),
                    },
                    status=401,
                ),
            )

        user = (
            request.env[
                "res.users"
            ]
            .sudo()
            .browse(
                uid
            )
            .exists()
        )

        if (
            not user
            or not user.active
        ):
            request.session.logout(
                keep_db=True,
            )

            return (
                None,
                self._json_response(
                    {
                        "success": False,
                        "authenticated": False,
                        "code": "INVALID_SESSION",
                        "message": (
                            "La sesión ya no es válida."
                        ),
                    },
                    status=401,
                ),
            )

        request.update_env(
            user=uid,
        )

        request.session.touch()

        return (
            request.env.user,
            None,
        )

    # ============================================================
    # MODEL ACCESS
    # ============================================================

    def _can_read_model(
        self,
        model_name,
    ):
        try:
            model = request.env[
                model_name
            ]

            return bool(
                model.check_access_rights(
                    "read",
                    raise_exception=False,
                )
            )

        except Exception:
            return False

    def _can_create_model(
        self,
        model_name,
    ):
        try:
            model = request.env[
                model_name
            ]

            return bool(
                model.check_access_rights(
                    "create",
                    raise_exception=False,
                )
            )

        except Exception:
            return False

    def _can_write_model(
        self,
        model_name,
    ):
        try:
            model = request.env[
                model_name
            ]

            return bool(
                model.check_access_rights(
                    "write",
                    raise_exception=False,
                )
            )

        except Exception:
            return False

    def _can_unlink_model(
        self,
        model_name,
    ):
        try:
            model = request.env[
                model_name
            ]

            return bool(
                model.check_access_rights(
                    "unlink",
                    raise_exception=False,
                )
            )

        except Exception:
            return False

    # ============================================================
    # RECORD HELPERS
    # ============================================================

    def _many2one(
        self,
        record,
    ):
        if not record:
            return False

        return {
            "id": record.id,
            "name": (
                record.display_name
                or record.name
                or ""
            ),
        }

    def _selection_label(
        self,
        record,
        field_name,
    ):
        if not record:
            return False

        if (
            field_name
            not in record._fields
        ):
            return False

        value = record[
            field_name
        ]

        if value in (
            False,
            None,
            "",
        ):
            return False

        field = record._fields[
            field_name
        ]

        selection = field.selection

        if callable(
            selection
        ):
            try:
                selection = selection(
                    record.env
                )
            except TypeError:
                selection = selection(
                    record
                )

        try:
            return dict(
                selection
                or []
            ).get(
                value,
                value,
            )

        except Exception:
            return value

    def _safe_value(
        self,
        record,
        field_name,
        default=False,
    ):
        if not record:
            return default

        if (
            field_name
            not in record._fields
        ):
            return default

        value = record[
            field_name
        ]

        if hasattr(
            value,
            "ids",
        ):
            if not value:
                return False

            if len(value) == 1:
                return self._many2one(
                    value
                )

            return [
                self._many2one(
                    item
                )
                for item
                in value
            ]

        return value

    # ============================================================
    # PAGINATION
    # ============================================================

    def _get_pagination(
        self,
        default_limit=50,
        max_limit=100,
    ):
        try:
            limit = int(
                request.httprequest
                .args
                .get(
                    "limit",
                    default_limit,
                )
            )
        except Exception:
            limit = default_limit

        try:
            offset = int(
                request.httprequest
                .args
                .get(
                    "offset",
                    0,
                )
            )
        except Exception:
            offset = 0

        limit = max(
            1,
            min(
                limit,
                max_limit,
            ),
        )

        offset = max(
            0,
            offset,
        )

        return (
            limit,
            offset,
        )

    # ============================================================
    # STANDARD ERRORS
    # ============================================================

    def _error_response(
        self,
        exception,
    ):
        if isinstance(
            exception,
            AccessDenied,
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "ACCESS_DENIED",
                    "message": (
                        "No tienes autorización "
                        "para realizar esta operación."
                    ),
                },
                status=403,
            )

        if isinstance(
            exception,
            AccessError,
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "ACCESS_ERROR",
                    "message": (
                        "No tienes permisos para "
                        "acceder a este registro."
                    ),
                },
                status=403,
            )

        if isinstance(
            exception,
            ValidationError,
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "VALIDATION_ERROR",
                    "message": str(
                        exception
                    ),
                },
                status=400,
            )

        if isinstance(
            exception,
            UserError,
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "USER_ERROR",
                    "message": str(
                        exception
                    ),
                },
                status=400,
            )

        _logger.exception(
            "Error inesperado "
            "en API móvil: %s",
            exception,
        )

        return self._json_response(
            {
                "success": False,
                "code": "SERVER_ERROR",
                "message": (
                    "Ocurrió un error inesperado "
                    "procesando la solicitud."
                ),
            },
            status=500,
        )