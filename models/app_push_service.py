# -*- coding: utf-8 -*-

import logging

import requests

from odoo import api, models
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


try:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account
except ImportError:
    GoogleAuthRequest = None
    service_account = None


class AppPushService(models.AbstractModel):
    _name = "app.push.service"
    _description = "Servicio central de notificaciones Push"

    FCM_SCOPE = (
        "https://www.googleapis.com/auth/firebase.messaging"
    )

    # ============================================================
    # DEPENDENCIAS
    # ============================================================

    @api.model
    def _check_google_auth_dependency(self):
        if (
            GoogleAuthRequest is None
            or service_account is None
        ):
            raise ValidationError(
                "No está instalada la dependencia "
                "'google-auth' requerida para enviar "
                "notificaciones Firebase HTTP v1."
            )

        return True

    # ============================================================
    # CONFIGURACIÓN / TOKEN OAUTH2
    # ============================================================

    @api.model
    def _get_firebase_config(self):
        return (
            self.env["app.push.config"]
            .sudo()
            .get_active_config()
        )

    @api.model
    def _get_access_token(self):
        self._check_google_auth_dependency()

        config = self._get_firebase_config()

        credentials_info = (
            config.get_service_account_credentials()
        )

        credentials = (
            service_account.Credentials
            .from_service_account_info(
                credentials_info,
                scopes=[
                    self.FCM_SCOPE,
                ],
            )
        )

        credentials.refresh(
            GoogleAuthRequest()
        )

        if not credentials.token:
            raise ValidationError(
                "Firebase no devolvió un token "
                "OAuth2 válido."
            )

        return (
            config,
            credentials.token,
        )

    # ============================================================
    # NORMALIZAR DATA
    # ============================================================

    @api.model
    def _normalize_data(self, data):
        normalized = {}

        for key, value in (
            data or {}
        ).items():
            if value in (
                None,
                False,
            ):
                continue

            normalized[
                str(key)
            ] = str(value)

        return normalized

    # ============================================================
    # PAYLOAD FCM
    # ============================================================

    @api.model
    def _build_message(
        self,
        token,
        title,
        body,
        data=None,
    ):
        normalized_data = (
            self._normalize_data(
                data
            )
        )

        message = {
            "token": token,
            "notification": {
                "title": str(
                    title or ""
                ),
                "body": str(
                    body or ""
                ),
            },
            "data": normalized_data,
            "android": {
                "priority": "high",
                "notification": {
                    "channel_id":
                        "copier_support_high_importance",
                    "sound":
                        "default",
                },
            },
            "apns": {
                "headers": {
                    "apns-priority": "10",
                },
                "payload": {
                    "aps": {
                        "sound": "default",
                    },
                },
            },
        }

        return {
            "message": message,
        }

    # ============================================================
    # ANALIZAR ERROR FCM
    # ============================================================

    @api.model
    def _extract_fcm_error(
        self,
        response,
    ):
        try:
            payload = response.json()
        except Exception:
            payload = {}

        error = (
            payload.get("error")
            if isinstance(
                payload,
                dict,
            )
            else {}
        ) or {}

        status = str(
            error.get("status")
            or ""
        ).strip()

        message = str(
            error.get("message")
            or response.text
            or ""
        ).strip()

        fcm_error_code = ""

        details = (
            error.get("details")
            if isinstance(
                error,
                dict,
            )
            else []
        ) or []

        for detail in details:
            if not isinstance(
                detail,
                dict,
            ):
                continue

            candidate = str(
                detail.get("errorCode")
                or ""
            ).strip()

            if candidate:
                fcm_error_code = (
                    candidate
                )
                break

        return {
            "status":
                status,
            "message":
                message,
            "fcm_error_code":
                fcm_error_code,
        }

    @api.model
    def _is_invalid_token_error(
        self,
        response,
        error_info,
    ):
        fcm_error_code = str(
            error_info.get(
                "fcm_error_code"
            )
            or ""
        ).upper()

        status = str(
            error_info.get(
                "status"
            )
            or ""
        ).upper()

        message = str(
            error_info.get(
                "message"
            )
            or ""
        ).lower()

        if fcm_error_code in (
            "UNREGISTERED",
            "SENDER_ID_MISMATCH",
        ):
            return True

        if status == "NOT_FOUND":
            return True

        invalid_markers = (
            "registration token is not a valid",
            "requested entity was not found",
            "unregistered",
        )

        if response.status_code in (
            400,
            404,
        ):
            return any(
                marker in message
                for marker in invalid_markers
            )

        return False

    # ============================================================
    # ENVÍO A UN TOKEN
    # ============================================================

    @api.model
    def send_to_token(
        self,
        token,
        title,
        body,
        data=None,
    ):
        token = str(
            token or ""
        ).strip()

        if not token:
            return {
                "success": False,
                "code": "TOKEN_REQUIRED",
                "message":
                    "El token FCM está vacío.",
            }

        try:
            config, access_token = (
                self._get_access_token()
            )

            url = (
                "https://fcm.googleapis.com/"
                "v1/projects/%s/messages:send"
                % config.project_id
            )

            payload = (
                self._build_message(
                    token=token,
                    title=title,
                    body=body,
                    data=data,
                )
            )

            response = requests.post(
                url,
                headers={
                    "Authorization":
                        "Bearer %s"
                        % access_token,
                    "Content-Type":
                        "application/json; "
                        "UTF-8",
                },
                json=payload,
                timeout=15,
            )

            if (
                200
                <= response.status_code
                < 300
            ):
                try:
                    response_data = (
                        response.json()
                    )
                except Exception:
                    response_data = {}

                return {
                    "success": True,
                    "status_code":
                        response.status_code,
                    "message_id":
                        response_data.get(
                            "name"
                        )
                        or "",
                }

            error_info = (
                self._extract_fcm_error(
                    response
                )
            )

            invalid_token = (
                self._is_invalid_token_error(
                    response,
                    error_info,
                )
            )

            if invalid_token:
                (
                    self.env[
                        "app.push.device"
                    ]
                    .sudo()
                    .deactivate_token(
                        token
                    )
                )

            _logger.warning(
                "FCM rechazó notificación. "
                "HTTP=%s Status=%s "
                "FCM=%s InvalidToken=%s "
                "Mensaje=%s",
                response.status_code,
                error_info.get(
                    "status"
                ),
                error_info.get(
                    "fcm_error_code"
                ),
                invalid_token,
                error_info.get(
                    "message"
                ),
            )

            return {
                "success": False,
                "status_code":
                    response.status_code,
                "code":
                    error_info.get(
                        "fcm_error_code"
                    )
                    or error_info.get(
                        "status"
                    )
                    or "FCM_ERROR",
                "message":
                    error_info.get(
                        "message"
                    )
                    or "Firebase rechazó "
                       "la notificación.",
                "invalid_token":
                    invalid_token,
            }

        except Exception as exception:
            _logger.exception(
                "Error enviando push FCM "
                "al token."
            )

            return {
                "success": False,
                "code":
                    "FCM_SEND_EXCEPTION",
                "message":
                    str(exception),
            }

    # ============================================================
    # ENVÍO A UN USUARIO
    # ============================================================

    @api.model
    def send_to_user(
        self,
        user,
        title,
        body,
        data=None,
    ):
        if not user:
            return {
                "success": False,
                "sent": 0,
                "failed": 0,
                "results": [],
                "code":
                    "USER_REQUIRED",
            }

        devices = (
            self.env[
                "app.push.device"
            ]
            .sudo()
            .search(
                [
                    (
                        "user_id",
                        "=",
                        user.id,
                    ),
                    (
                        "active",
                        "=",
                        True,
                    ),
                    (
                        "token",
                        "!=",
                        False,
                    ),
                ]
            )
        )

        if not devices:
            return {
                "success": True,
                "sent": 0,
                "failed": 0,
                "results": [],
                "code":
                    "NO_ACTIVE_DEVICES",
            }

        results = []
        sent = 0
        failed = 0

        for device in devices:
            result = self.send_to_token(
                token=device.token,
                title=title,
                body=body,
                data=data,
            )

            result.update(
                {
                    "device_id":
                        device.id,
                    "platform":
                        device.platform,
                }
            )

            results.append(
                result
            )

            if result.get(
                "success"
            ):
                sent += 1
            else:
                failed += 1

        return {
            "success":
                sent > 0,
            "sent":
                sent,
            "failed":
                failed,
            "results":
                results,
        }

    # ============================================================
    # ENVÍO A VARIOS USUARIOS
    # ============================================================

    @api.model
    def send_to_users(
        self,
        users,
        title,
        body,
        data=None,
    ):
        users = (
            users
            or self.env[
                "res.users"
            ]
        )

        results = []
        total_sent = 0
        total_failed = 0

        for user in users:
            result = self.send_to_user(
                user=user,
                title=title,
                body=body,
                data=data,
            )

            results.append(
                {
                    "user_id":
                        user.id,
                    "result":
                        result,
                }
            )

            total_sent += int(
                result.get(
                    "sent"
                )
                or 0
            )

            total_failed += int(
                result.get(
                    "failed"
                )
                or 0
            )

        return {
            "success":
                total_sent > 0,
            "sent":
                total_sent,
            "failed":
                total_failed,
            "results":
                results,
        }

    # ============================================================
    # USUARIOS PORTAL AUTORIZADOS PARA UNA EMPRESA
    # ============================================================

    @api.model
    def get_portal_users_for_company(
        self,
        company,
    ):
        if not company:
            return self.env[
                "res.users"
            ]

        Users = self.env[
            "res.users"
        ].sudo()

        domain = [
            (
                "active",
                "=",
                True,
            ),
            (
                "share",
                "=",
                True,
            ),
        ]

        candidates = (
            Users.search(
                domain
            )
        )

        matched = (
            self.env[
                "res.users"
            ]
        )

        for user in candidates:
            partner = (
                user.partner_id
            )

            if not partner:
                continue

            main_company = (
                partner.commercial_partner_id
                or partner
            )

            allowed_ids = []

            if main_company:
                allowed_ids.append(
                    main_company.id
                )

            if (
                "whatsapp_company_ids"
                in partner._fields
            ):
                allowed_ids.extend(
                    partner
                    .whatsapp_company_ids
                    .ids
                )

            if company.id in set(
                allowed_ids
            ):
                matched |= user

        return matched

    # ============================================================
    # ENVÍO A CLIENTES PORTAL DE UNA EMPRESA
    # ============================================================

    @api.model
    def send_to_portal_company(
        self,
        company,
        notification_type,
        record_id,
        title,
        body,
        extra_data=None,
    ):
        if not company:
            return {
                "success": False,
                "sent": 0,
                "failed": 0,
                "results": [],
                "code":
                    "COMPANY_REQUIRED",
            }

        data = {
            "type":
                notification_type,
            "record_id":
                record_id,
            "company_id":
                company.id,
        }

        if extra_data:
            data.update(
                extra_data
            )

        users = (
            self.get_portal_users_for_company(
                company
            )
        )

        return self.send_to_users(
            users=users,
            title=title,
            body=body,
            data=data,
        )
