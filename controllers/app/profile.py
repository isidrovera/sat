# -*- coding: utf-8 -*-

import base64
import binascii
import logging
import re

from odoo import http, tools
from odoo.exceptions import AccessDenied, UserError, ValidationError
from odoo.http import request

from .base import AppBaseController


_logger = logging.getLogger(__name__)


class AppProfileController(AppBaseController):

    # ============================================================
    # CONSTANTES
    # ============================================================

    MAX_AVATAR_BYTES = 10 * 1024 * 1024

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/profile",
            "/api/app/profile/photo",
            "/api/app/profile/change-password",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def profile_options(
        self,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # HELPERS
    # ============================================================

    def _current_user(
        self,
    ):
        user = request.env.user

        if not user:
            return False

        return user

    def _image_to_string(
        self,
        image,
    ):
        if not image:
            return False

        if isinstance(
            image,
            bytes,
        ):
            try:
                return image.decode(
                    "utf-8"
                )

            except UnicodeDecodeError:
                return base64.b64encode(
                    image
                ).decode(
                    "utf-8"
                )

        return str(
            image
        )

    def _get_employee_data(
        self,
        user,
    ):
        result = {
            "id": False,
            "name": False,
            "job_title": False,
        }

        if (
            "employee_id"
            not in user._fields
        ):
            return result

        employee = (
            user.employee_id
        )

        if not employee:
            return result

        result[
            "id"
        ] = employee.id

        result[
            "name"
        ] = (
            employee.name
            or False
        )

        if (
            "job_title"
            in employee._fields
        ):
            result[
                "job_title"
            ] = (
                employee.job_title
                or False
            )

        return result

    def _serialize_profile(
        self,
        user,
    ):
        user.ensure_one()

        partner = (
            user.partner_id
        )

        company = (
            user.company_id
        )

        avatar = False

        if (
            "avatar_128"
            in user._fields
        ):
            avatar = (
                self._image_to_string(
                    user.avatar_128
                )
            )

        email = (
            partner.email
            if (
                partner
                and "email"
                in partner._fields
            )
            else False
        )

        phone = (
            partner.phone
            if (
                partner
                and "phone"
                in partner._fields
            )
            else False
        )

        mobile = (
            partner.mobile
            if (
                partner
                and "mobile"
                in partner._fields
            )
            else False
        )

        totp_enabled = False

        if (
            "totp_enabled"
            in user._fields
        ):
            totp_enabled = bool(
                user.totp_enabled
            )

        return {
            "id": user.id,

            "name": (
                user.name
                or ""
            ),

            "login": (
                user.login
                or ""
            ),

            "email": (
                email
                or False
            ),

            "phone": (
                phone
                or False
            ),

            "mobile": (
                mobile
                or False
            ),

            "avatar": (
                avatar
                or False
            ),

            "company": {
                "id": (
                    company.id
                ),
                "name": (
                    company.name
                    or ""
                ),
            },

            "employee": (
                self._get_employee_data(
                    user
                )
            ),

            "security": {
                "totp_enabled": (
                    totp_enabled
                ),
                "can_change_password": True,
            },

            "editable": {
                "email": True,
                "phone": True,
                "mobile": True,
                "photo": True,
                "password": True,

                # Se mantienen controlados por Odoo.
                "name": False,
                "login": False,
                "company": False,
                "job_title": False,
            },
        }

    def _clean_text(
        self,
        value,
        max_length=255,
    ):
        if value is None:
            return False

        value = str(
            value
        ).strip()

        if not value:
            return False

        return value[
            :max_length
        ]

    def _validate_email(
        self,
        value,
    ):
        value = (
            self._clean_text(
                value,
                max_length=254,
            )
        )

        if not value:
            return False

        if not tools.single_email_re.match(
            value
        ):
            raise ValueError(
                "Ingresa un correo electrónico válido."
            )

        return value

    def _validate_phone(
        self,
        value,
        field_label,
    ):
        value = (
            self._clean_text(
                value,
                max_length=40,
            )
        )

        if not value:
            return False

        # Permitimos números internacionales:
        # +51 999 999 999
        # (01) 555-5555
        if not re.match(
            r"^[0-9+\-\s().]{6,40}$",
            value,
        ):
            raise ValueError(
                "%s no tiene un formato válido."
                % field_label
            )

        return value

    def _prepare_avatar(
        self,
        avatar_base64,
    ):
        if not avatar_base64:
            return False

        if isinstance(
            avatar_base64,
            str,
        ):
            avatar_base64 = (
                avatar_base64.strip()
            )

            if (
                avatar_base64.startswith(
                    "data:"
                )
                and ","
                in avatar_base64
            ):
                header, avatar_base64 = (
                    avatar_base64.split(
                        ",",
                        1,
                    )
                )

                if not (
                    header.startswith(
                        "data:image/"
                    )
                ):
                    raise ValueError(
                        "El archivo seleccionado debe ser una imagen."
                    )

        try:
            raw = (
                base64.b64decode(
                    avatar_base64,
                    validate=True,
                )
            )

        except (
            binascii.Error,
            ValueError,
            TypeError,
        ):
            raise ValueError(
                "La foto no contiene Base64 válido."
            )

        if not raw:
            raise ValueError(
                "La imagen está vacía."
            )

        if (
            len(raw)
            > self.MAX_AVATAR_BYTES
        ):
            raise ValueError(
                "La foto supera el tamaño máximo permitido de 10 MB."
            )

        return avatar_base64

    # ============================================================
    # GET PROFILE
    # ============================================================

    @http.route(
        "/api/app/profile",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def profile_get(
        self,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            return self._json_response(
                {
                    "success": True,
                    "profile": (
                        self._serialize_profile(
                            user
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # UPDATE PROFILE
    # ============================================================

    @http.route(
        "/api/app/profile",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def profile_update(
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

            partner_vals = {}

            if "email" in data:
                partner_vals[
                    "email"
                ] = (
                    self._validate_email(
                        data.get(
                            "email"
                        )
                    )
                )

            if "phone" in data:
                partner_vals[
                    "phone"
                ] = (
                    self._validate_phone(
                        data.get(
                            "phone"
                        ),
                        "El teléfono",
                    )
                )

            if "mobile" in data:
                partner_vals[
                    "mobile"
                ] = (
                    self._validate_phone(
                        data.get(
                            "mobile"
                        ),
                        "El celular",
                    )
                )

            if not partner_vals:
                return self._json_response(
                    {
                        "success": False,
                        "code": "NO_DATA",
                        "message": (
                            "No se recibieron datos para actualizar."
                        ),
                    },
                    status=400,
                )

            # Importante:
            # solo se modifica el partner del usuario autenticado.
            user.partner_id.sudo().write(
                partner_vals
            )

            _logger.info(
                "Perfil móvil actualizado por usuario %s.",
                user.id,
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Perfil actualizado correctamente."
                    ),
                    "profile": (
                        self._serialize_profile(
                            user
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

        except (
            ValidationError,
            UserError,
        ) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "VALIDATION_ERROR",
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
    # UPDATE PHOTO
    # ============================================================

    @http.route(
        "/api/app/profile/photo",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def profile_photo(
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

            if (
                "photo_base64"
                not in data
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "PHOTO_REQUIRED",
                        "message": (
                            "Selecciona una foto."
                        ),
                    },
                    status=400,
                )

            photo = (
                self._prepare_avatar(
                    data.get(
                        "photo_base64"
                    )
                )
            )

            if not photo:
                # Permite eliminar la foto.
                user.partner_id.sudo().write(
                    {
                        "image_1920": False,
                    }
                )

                message = (
                    "Foto eliminada correctamente."
                )

            else:
                user.partner_id.sudo().write(
                    {
                        "image_1920": photo,
                    }
                )

                message = (
                    "Foto actualizada correctamente."
                )

            _logger.info(
                "Foto de perfil móvil actualizada por usuario %s.",
                user.id,
            )

            return self._json_response(
                {
                    "success": True,
                    "message": message,
                    "profile": (
                        self._serialize_profile(
                            user
                        )
                    ),
                }
            )

        except ValueError as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_PHOTO",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except (
            ValidationError,
            UserError,
        ) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "VALIDATION_ERROR",
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
    # CHANGE PASSWORD
    # ============================================================

    @http.route(
        "/api/app/profile/change-password",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def profile_change_password(
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

            current_password = str(
                data.get(
                    "current_password"
                )
                or ""
            )

            new_password = str(
                data.get(
                    "new_password"
                )
                or ""
            )

            confirm_password = str(
                data.get(
                    "confirm_password"
                )
                or ""
            )

            if not current_password:
                return self._json_response(
                    {
                        "success": False,
                        "code": "CURRENT_PASSWORD_REQUIRED",
                        "message": (
                            "Ingresa tu contraseña actual."
                        ),
                    },
                    status=400,
                )

            if not new_password:
                return self._json_response(
                    {
                        "success": False,
                        "code": "NEW_PASSWORD_REQUIRED",
                        "message": (
                            "Ingresa la nueva contraseña."
                        ),
                    },
                    status=400,
                )

            if (
                len(new_password)
                < 8
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "PASSWORD_TOO_SHORT",
                        "message": (
                            "La nueva contraseña debe tener "
                            "al menos 8 caracteres."
                        ),
                    },
                    status=400,
                )

            if (
                new_password
                != confirm_password
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "PASSWORD_MISMATCH",
                        "message": (
                            "La confirmación de contraseña "
                            "no coincide."
                        ),
                    },
                    status=400,
                )

            if (
                current_password
                == new_password
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "PASSWORD_NOT_CHANGED",
                        "message": (
                            "La nueva contraseña debe ser "
                            "diferente de la actual."
                        ),
                    },
                    status=400,
                )

            # Método nativo de Odoo 18.
            #
            # - exige contraseña actual
            # - valida las credenciales
            # - actualiza la contraseña de env.user
            request.env[
                "res.users"
            ].change_password(
                current_password,
                new_password,
            )

            _logger.info(
                "Contraseña cambiada desde la app móvil "
                "por usuario %s.",
                user.id,
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Contraseña actualizada correctamente."
                    ),
                }
            )

        except AccessDenied:
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_CURRENT_PASSWORD",
                    "message": (
                        "La contraseña actual es incorrecta."
                    ),
                },
                status=401,
            )

        except (
            UserError,
            ValidationError,
        ) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "PASSWORD_CHANGE_ERROR",
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
