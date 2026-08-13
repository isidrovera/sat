# -*- coding: utf-8 -*-

import logging

from odoo import http
from odoo.http import request

from .base import AppBaseController


_logger = logging.getLogger(__name__)


class AppPushController(AppBaseController):

    @http.route(
        "/api/app/push/device",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def register_push_device(
        self,
        **kwargs,
    ):
        user, error = self._require_user()

        if error:
            return error

        data = self._get_json_body()

        token = str(
            data.get("token")
            or ""
        ).strip()

        if not token:
            return self._json_response(
                {
                    "success": False,
                    "code": "FCM_TOKEN_REQUIRED",
                    "message": (
                        "El token FCM es obligatorio."
                    ),
                },
                status=400,
            )

        platform = str(
            data.get("platform")
            or "android"
        ).strip().lower()

        if platform not in (
            "android",
            "ios",
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_PLATFORM",
                    "message": (
                        "La plataforma debe ser "
                        "android o ios."
                    ),
                },
                status=400,
            )

        device_id = str(
            data.get("device_id")
            or ""
        ).strip() or False

        device_name = str(
            data.get("device_name")
            or ""
        ).strip() or False

        app_version = str(
            data.get("app_version")
            or ""
        ).strip() or False

        try:
            device = (
                request.env[
                    "app.push.device"
                ]
                .sudo()
                .register_device(
                    user=user,
                    token=token,
                    platform=platform,
                    device_id=device_id,
                    device_name=device_name,
                    app_version=app_version,
                )
            )

            if not device:
                return self._json_response(
                    {
                        "success": False,
                        "code": "DEVICE_NOT_REGISTERED",
                        "message": (
                            "No se pudo registrar "
                            "el dispositivo."
                        ),
                    },
                    status=500,
                )

            _logger.info(
                "Dispositivo push registrado. "
                "Usuario=%s Dispositivo=%s Plataforma=%s",
                user.id,
                device.id,
                platform,
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Dispositivo registrado "
                        "correctamente."
                    ),
                    "device": {
                        "id": device.id,
                        "platform": device.platform,
                        "active": device.active,
                    },
                }
            )

        except Exception as exception:
            return self._error_response(
                exception
            )