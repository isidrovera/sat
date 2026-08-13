# -*- coding: utf-8 -*-

import logging

import requests

from google.auth.transport.requests import Request
from google.oauth2 import service_account

from odoo import api, models


_logger = logging.getLogger(__name__)


class AppPushService(models.AbstractModel):
    _name = "app.push.service"
    _description = "Servicio Push Firebase Cloud Messaging"

    FCM_SCOPE = (
        "https://www.googleapis.com/auth/firebase.messaging"
    )

    # ============================================================
    # CONFIGURACIÓN FIREBASE
    # ============================================================

    @api.model
    def _get_firebase_config(self):
        return (
            self.env["app.push.config"]
            .sudo()
            .get_active_config()
        )

    # ============================================================
    # CREDENCIAL GOOGLE OAUTH2
    # ============================================================

    @api.model
    def _get_access_token(self):
        config = self._get_firebase_config()

        credentials_info = (
            config.get_service_account_credentials()
        )

        credentials = (
            service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=[
                    self.FCM_SCOPE,
                ],
            )
        )

        credentials.refresh(
            Request()
        )

        return (
            credentials.token,
            config.project_id,
        )

    # ============================================================
    # URL FCM HTTP V1
    # ============================================================

    @api.model
    def _get_fcm_url(self, project_id):
        return (
            "https://fcm.googleapis.com/v1/"
            f"projects/{project_id}/messages:send"
        )

    # ============================================================
    # NORMALIZAR DATA
    # Firebase exige strings dentro de message.data
    # ============================================================

    @api.model
    def _normalize_data(self, data):
        if not data:
            return {}

        normalized = {}

        for key, value in data.items():
            if value is None:
                continue

            if isinstance(value, bool):
                normalized[str(key)] = (
                    "true"
                    if value
                    else "false"
                )
                continue

            normalized[str(key)] = str(value)

        return normalized

    # ============================================================
    # CONSTRUIR MENSAJE
    # ============================================================

    @api.model
    def _build_message(
        self,
        token,
        title,
        body,
        data=None,
    ):
        return {
            "message": {
                "token": token,
                "notification": {
                    "title": title,
                    "body": body,
                },
                "data": self._normalize_data(
                    data
                ),
                "android": {
                    "priority": "high",
                    "notification": {
                        "channel_id":
                            "copier_support_high_importance",
                        "sound": "default",
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
        }

    # ============================================================
    # DETECTAR TOKEN INVÁLIDO
    # ============================================================

    @api.model
    def _is_invalid_token_response(
        self,
        response,
    ):
        if response.status_code not in (
            400,
            404,
        ):
            return False

        try:
            response_data = response.json()
        except Exception:
            return False

        error = (
            response_data.get("error")
            or {}
        )

        status = str(
            error.get("status")
            or ""
        ).upper()

        if status == "UNREGISTERED":
            return True

        details = (
            error.get("details")
            or []
        )

        for detail in details:
            error_code = str(
                detail.get("errorCode")
                or ""
            ).upper()

            if error_code in (
                "UNREGISTERED",
            ):
                return True

        return False

    # ============================================================
    # DESACTIVAR TOKEN
    # ============================================================

    @api.model
    def _deactivate_token(self, token):
        try:
            (
                self.env["app.push.device"]
                .sudo()
                .deactivate_token(
                    token
                )
            )

            _logger.info(
                "Token FCM desactivado por Firebase."
            )

        except Exception:
            _logger.exception(
                "No se pudo desactivar "
                "el token FCM inválido."
            )

    # ============================================================
    # ENVIAR A UN TOKEN
    # ============================================================

    @api.model
    def send_to_token(
        self,
        token,
        title,
        body,
        data=None,
    ):
        if not token:
            return {
                "success": False,
                "code": "TOKEN_REQUIRED",
            }

        try:
            access_token, project_id = (
                self._get_access_token()
            )

            url = self._get_fcm_url(
                project_id
            )

            payload = self._build_message(
                token=token,
                title=title,
                body=body,
                data=data,
            )

            response = requests.post(
                url,
                headers={
                    "Authorization":
                        f"Bearer {access_token}",
                    "Content-Type":
                        "application/json",
                },
                json=payload,
                timeout=20,
            )

            if (
                response.status_code >= 200
                and response.status_code < 300
            ):
                try:
                    firebase_response = (
                        response.json()
                    )
                except Exception:
                    firebase_response = {}

                _logger.info(
                    "Push FCM enviado correctamente."
                )

                return {
                    "success": True,
                    "status_code":
                        response.status_code,
                    "firebase_response":
                        firebase_response,
                }

            if self._is_invalid_token_response(
                response
            ):
                self._deactivate_token(
                    token
                )

            try:
                error_response = (
                    response.json()
                )
            except Exception:
                error_response = {
                    "text": response.text,
                }

            _logger.warning(
                "Error FCM HTTP %s: %s",
                response.status_code,
                error_response,
            )

            return {
                "success": False,
                "status_code":
                    response.status_code,
                "firebase_response":
                    error_response,
            }

        except Exception as exception:
            _logger.exception(
                "Error enviando notificación FCM."
            )

            return {
                "success": False,
                "code": "FCM_SEND_ERROR",
                "message": str(
                    exception
                ),
            }

    # ============================================================
    # ENVIAR A USUARIO
    # Soporta varios celulares/dispositivos por usuario
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
            }

        tokens = (
            self.env["app.push.device"]
            .sudo()
            .get_active_tokens(
                user
            )
        )

        if not tokens:
            _logger.info(
                "Usuario %s no tiene "
                "dispositivos push activos.",
                user.id,
            )

            return {
                "success": True,
                "sent": 0,
                "failed": 0,
                "results": [],
            }

        results = []
        sent = 0
        failed = 0

        for token in tokens:
            result = self.send_to_token(
                token=token,
                title=title,
                body=body,
                data=data,
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
            "success": failed == 0,
            "sent": sent,
            "failed": failed,
            "results": results,
        }