# -*- coding: utf-8 -*-

import base64
import json
import logging
import re

from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import request


_logger = logging.getLogger(__name__)


class AppAuthController(http.Controller):

    # ============================================================
    # Helpers
    # ============================================================

    def _json_response(
        self,
        data,
        status=200,
    ):
        """
        Devuelve JSON REST normal.

        No utiliza JSON-RPC para que Flutter pueda consumir
        directamente la respuesta HTTP.
        """

        return request.make_response(
            json.dumps(
                data,
                ensure_ascii=False,
            ),
            headers=[
                (
                    "Content-Type",
                    "application/json; charset=utf-8",
                ),
                (
                    "Cache-Control",
                    "no-store",
                ),
            ],
            status=status,
        )

    def _get_json_body(self):
        """
        Obtiene el JSON enviado por Flutter.

        Devuelve {} cuando:
        - no hay body
        - el JSON es inválido
        - el contenido no es un objeto
        """

        try:
            data = request.httprequest.get_json(
                silent=True,
            )

            if isinstance(data, dict):
                return data

        except Exception:
            _logger.exception(
                "No se pudo interpretar el JSON recibido."
            )

        return {}

    def _get_database(self, data=None):
        """
        Determina la base de datos de Odoo.

        Normalmente request.db ya estará determinada por:
        - dbfilter
        - dominio
        - configuración del servidor

        Se admite 'db' en el body únicamente como respaldo.
        """

        data = data or {}

        db = request.db

        if not db:
            db = request.session.db

        if not db:
            db = data.get("db")

        if db:
            db = str(db).strip()

        return db or False

    def _image_to_string(self, image):
        """
        Convierte avatar binario/base64 de Odoo a texto
        para poder incluirlo en JSON.
        """

        if not image:
            return False

        if isinstance(image, bytes):
            try:
                return image.decode("utf-8")
            except UnicodeDecodeError:
                return base64.b64encode(
                    image,
                ).decode("utf-8")

        return str(image)

    def _get_employee_data(self, user):
        """
        Devuelve los datos laborales disponibles.

        No asumimos que todos los usuarios tengan empleado.
        """

        result = {
            "id": False,
            "name": False,
            "job_title": False,
        }

        if "employee_id" not in user._fields:
            return result

        employee = user.employee_id

        if not employee:
            return result

        result["id"] = employee.id
        result["name"] = employee.name

        if "job_title" in employee._fields:
            result["job_title"] = (
                employee.job_title
                or False
            )

        return result

    def _serialize_user(self, user):
        """
        Información básica necesaria para Flutter.

        No enviamos todos los campos de res.users.
        """

        user.ensure_one()

        partner = user.partner_id
        employee = self._get_employee_data(user)

        totp_enabled = False

        if "totp_enabled" in user._fields:
            totp_enabled = bool(
                user.totp_enabled
            )

        avatar = False

        if "avatar_128" in user._fields:
            avatar = self._image_to_string(
                user.avatar_128,
            )

        phone = False

        if "phone" in partner._fields:
            phone = partner.phone or False

        mobile = False

        if "mobile" in partner._fields:
            mobile = partner.mobile or False

        email = (
            partner.email
            if "email" in partner._fields
            else False
        )

        company = user.company_id

        return {
            "id": user.id,
            "name": user.name,
            "login": user.login,
            "email": email,
            "phone": phone,
            "mobile": mobile,
            "avatar": avatar,
            "active": bool(user.active),
            "company": {
                "id": company.id,
                "name": company.name,
            },
            "employee": employee,
            "security": {
                "totp_enabled": totp_enabled,
            },
        }

    def _current_user_response(self):
        """
        Respuesta común después de una autenticación correcta.
        """

        user = request.env.user

        return {
            "success": True,
            "authenticated": True,
            "requires_2fa": False,
            "session": {
                "type": "odoo_session",
                "authenticated": True,
            },
            "user": self._serialize_user(
                user,
            ),
        }

    # ============================================================
    # LOGIN
    # ============================================================

    @http.route(
        "/api/app/auth/login",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def login(self, **kwargs):
        """
        Primer paso de autenticación.

        Flutter envía:

        {
            "login": "usuario@empresa.com",
            "password": "********"
        }

        Si el usuario NO tiene MFA:
            → queda autenticado inmediatamente.

        Si tiene TOTP:
            → Odoo crea una pre-sesión
            → devuelve requires_2fa = true
            → Flutter debe conservar session_id
            → luego llamar /api/app/auth/2fa
        """

        data = self._get_json_body()

        login = str(
            data.get("login") or ""
        ).strip()

        password = str(
            data.get("password") or ""
        )

        if not login:
            return self._json_response(
                {
                    "success": False,
                    "code": "LOGIN_REQUIRED",
                    "message": (
                        "Ingresa tu usuario "
                        "o correo."
                    ),
                },
                status=400,
            )

        if not password:
            return self._json_response(
                {
                    "success": False,
                    "code": "PASSWORD_REQUIRED",
                    "message": (
                        "Ingresa tu contraseña."
                    ),
                },
                status=400,
            )

        db = self._get_database(data)

        if not db:
            _logger.error(
                "Login móvil rechazado: "
                "no se pudo determinar la base de datos."
            )

            return self._json_response(
                {
                    "success": False,
                    "code": "DATABASE_NOT_FOUND",
                    "message": (
                        "No se pudo determinar "
                        "la base de datos de Odoo."
                    ),
                },
                status=500,
            )

        credential = {
            "login": login,
            "password": password,
            "type": "password",
        }

        try:
            auth_info = (
                request.session.authenticate(
                    db,
                    credential,
                )
            )

        except AccessDenied:
            _logger.warning(
                "Login móvil incorrecto "
                "para usuario %s.",
                login,
            )

            # No decimos si el usuario existe o no.
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_CREDENTIALS",
                    "message": (
                        "Usuario o contraseña "
                        "incorrectos."
                    ),
                },
                status=401,
            )

        except Exception:
            _logger.exception(
                "Error inesperado durante "
                "el login móvil de %s.",
                login,
            )

            return self._json_response(
                {
                    "success": False,
                    "code": "AUTHENTICATION_ERROR",
                    "message": (
                        "No fue posible iniciar "
                        "sesión en este momento."
                    ),
                },
                status=500,
            )

        # --------------------------------------------------------
        # MFA / 2FA
        # --------------------------------------------------------
        #
        # Odoo Session.authenticate():
        #
        # - guarda pre_uid cuando usuario/password son correctos
        # - si no hay MFA llama finalize()
        # - si hay MFA deja request.session.uid = None
        #
        # Por tanto no necesitamos inventar nuestra propia bandera.
        #

        if (
            request.session.pre_uid
            and not request.session.uid
        ):
            pre_uid = request.session.pre_uid

            user = (
                request.env["res.users"]
                .sudo()
                .browse(pre_uid)
                .exists()
            )

            if not user:
                request.session.logout(
                    keep_db=True,
                )

                return self._json_response(
                    {
                        "success": False,
                        "code": "USER_NOT_FOUND",
                        "message": (
                            "No fue posible "
                            "continuar con la "
                            "autenticación."
                        ),
                    },
                    status=401,
                )

            mfa_type = False

            try:
                mfa_type = (
                    user._mfa_type()
                    if hasattr(
                        user,
                        "_mfa_type",
                    )
                    else False
                )
            except Exception:
                _logger.exception(
                    "No se pudo determinar "
                    "el tipo de MFA del usuario %s.",
                    user.id,
                )

            if mfa_type != "totp":
                _logger.warning(
                    "Usuario %s requiere MFA "
                    "no compatible con la app: %s",
                    user.id,
                    mfa_type,
                )

                return self._json_response(
                    {
                        "success": False,
                        "authenticated": False,
                        "requires_2fa": True,
                        "code": "MFA_NOT_SUPPORTED",
                        "mfa_type": (
                            mfa_type
                            or "unknown"
                        ),
                        "message": (
                            "Este usuario utiliza "
                            "un método de autenticación "
                            "adicional que todavía no "
                            "es compatible con la app."
                        ),
                    },
                    status=403,
                )

            return self._json_response(
                {
                    "success": True,
                    "authenticated": False,
                    "requires_2fa": True,
                    "mfa_type": "totp",
                    "message": (
                        "Ingresa el código de "
                        "tu aplicación de "
                        "autenticación."
                    ),
                    "user": {
                        "id": user.id,
                        "name": user.name,
                    },
                },
                status=200,
            )

        # --------------------------------------------------------
        # LOGIN COMPLETO SIN MFA
        # --------------------------------------------------------

        if not request.session.uid:
            _logger.error(
                "Odoo validó credenciales "
                "pero la sesión no quedó autenticada. "
                "Auth info: %s",
                auth_info,
            )

            return self._json_response(
                {
                    "success": False,
                    "code": "SESSION_NOT_CREATED",
                    "message": (
                        "No fue posible crear "
                        "la sesión."
                    ),
                },
                status=500,
            )

        request.session.db = db
        request.session.touch()

        return self._json_response(
            self._current_user_response(),
        )

    # ============================================================
    # VERIFICAR 2FA / TOTP
    # ============================================================

    @http.route(
        "/api/app/auth/2fa",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def verify_2fa(self, **kwargs):
        """
        Segundo paso cuando el usuario tiene TOTP.

        IMPORTANTE:
        Flutter debe enviar la MISMA cookie session_id
        obtenida durante /login.

        Body:

        {
            "code": "123456"
        }
        """

        if request.session.uid:
            # Ya está autenticado.
            return self._json_response(
                self._current_user_response(),
            )

        pre_uid = request.session.pre_uid

        if not pre_uid:
            return self._json_response(
                {
                    "success": False,
                    "code": "MFA_SESSION_EXPIRED",
                    "message": (
                        "La sesión de verificación "
                        "ha expirado. Inicia sesión "
                        "nuevamente."
                    ),
                },
                status=401,
            )

        data = self._get_json_body()

        raw_code = str(
            data.get("code") or ""
        )

        code = re.sub(
            r"\s+",
            "",
            raw_code,
        )

        if not code:
            return self._json_response(
                {
                    "success": False,
                    "code": "TOTP_REQUIRED",
                    "message": (
                        "Ingresa el código "
                        "de verificación."
                    ),
                },
                status=400,
            )

        if (
            len(code) != 6
            or not code.isdigit()
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_TOTP_FORMAT",
                    "message": (
                        "El código debe contener "
                        "6 dígitos."
                    ),
                },
                status=400,
            )

        user = (
            request.env["res.users"]
            .sudo()
            .browse(pre_uid)
            .exists()
        )

        if not user:
            request.session.logout(
                keep_db=True,
            )

            return self._json_response(
                {
                    "success": False,
                    "code": "USER_NOT_FOUND",
                    "message": (
                        "No fue posible completar "
                        "la autenticación."
                    ),
                },
                status=401,
            )

        if (
            "totp_enabled" not in user._fields
            or not user.totp_enabled
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "TOTP_NOT_ENABLED",
                    "message": (
                        "El usuario no tiene "
                        "TOTP habilitado."
                    ),
                },
                status=400,
            )

        try:
            #
            # Misma lógica utilizada por
            # auth_totp/controllers/home.py
            #
            with user._assert_can_auth(
                user=user.id,
            ):
                user._totp_check(
                    int(code),
                )

        except AccessDenied:
            _logger.warning(
                "Código TOTP incorrecto "
                "para usuario %s.",
                user.id,
            )

            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_TOTP",
                    "message": (
                        "El código de verificación "
                        "es incorrecto."
                    ),
                },
                status=401,
            )

        except Exception:
            _logger.exception(
                "Error validando TOTP "
                "para usuario %s.",
                user.id,
            )

            return self._json_response(
                {
                    "success": False,
                    "code": "TOTP_ERROR",
                    "message": (
                        "No fue posible validar "
                        "el código."
                    ),
                },
                status=500,
            )

        # --------------------------------------------------------
        # CONVIERTE PRE-SESIÓN EN SESIÓN AUTENTICADA
        # --------------------------------------------------------

        try:
            request.session.finalize(
                request.env,
            )

            request.update_env(
                user=request.session.uid,
            )

            request.update_context(
                **request.session.context
            )

            request.session.touch()

        except Exception:
            _logger.exception(
                "No se pudo finalizar la sesión "
                "después de validar TOTP."
            )

            return self._json_response(
                {
                    "success": False,
                    "code": "SESSION_FINALIZE_ERROR",
                    "message": (
                        "El código fue validado, "
                        "pero no se pudo completar "
                        "la sesión."
                    ),
                },
                status=500,
            )

        return self._json_response(
            self._current_user_response(),
        )

    # ============================================================
    # VALIDAR SESIÓN / USUARIO ACTUAL
    # ============================================================

    @http.route(
        "/api/app/auth/me",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def me(self, **kwargs):
        """
        Flutter llama este endpoint al abrir la app.

        Si session_id sigue siendo válida:
            → HTTP 200
            → devuelve usuario
            → abrir Home

        Si la sesión venció:
            Odoo rechazará auth='user'.
        """

        request.session.touch()

        return self._json_response(
            self._current_user_response(),
        )

    # ============================================================
    # LOGOUT
    # ============================================================

    @http.route(
        "/api/app/auth/logout",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def logout(self, **kwargs):
        """
        Cierra la sesión actual de Odoo.

        Flutter deberá eliminar localmente
        la cookie session_id después de recibir éxito.
        """

        user_id = request.env.user.id

        request.session.logout(
            keep_db=True,
        )

        _logger.info(
            "Usuario %s cerró sesión "
            "desde la app móvil.",
            user_id,
        )

        return self._json_response(
            {
                "success": True,
                "authenticated": False,
                "message": (
                    "Sesión cerrada correctamente."
                ),
            },
        )