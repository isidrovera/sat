# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AppPushDevice(models.Model):
    _name = "app.push.device"
    _description = "Dispositivo Push Copier Support"
    _order = "write_date desc, id desc"

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Usuario",
        required=True,
        index=True,
        ondelete="cascade",
    )

    token = fields.Char(
        string="Token FCM",
        required=True,
        index=True,
        copy=False,
    )

    device_id = fields.Char(
        string="ID del dispositivo",
        index=True,
        copy=False,
    )

    device_name = fields.Char(
        string="Nombre del dispositivo",
    )

    platform = fields.Selection(
        selection=[
            ("android", "Android"),
            ("ios", "iOS"),
        ],
        string="Plataforma",
        required=True,
        default="android",
        index=True,
    )

    app_version = fields.Char(
        string="Versión de la aplicación",
    )

    active = fields.Boolean(
        string="Activo",
        default=True,
        index=True,
    )

    last_seen_at = fields.Datetime(
        string="Última actividad",
        default=fields.Datetime.now,
        index=True,
    )

    token_updated_at = fields.Datetime(
        string="Última actualización del token",
        default=fields.Datetime.now,
    )

    _sql_constraints = [
        (
            "app_push_device_token_unique",
            "unique(token)",
            "Este token FCM ya está registrado.",
        ),
    ]

    @api.model
    def register_device(
        self,
        user,
        token,
        platform="android",
        device_id=False,
        device_name=False,
        app_version=False,
    ):
        if not user or not token:
            return False

        now = fields.Datetime.now()

        device = self.sudo().search(
            [
                ("token", "=", token),
            ],
            limit=1,
        )

        values = {
            "user_id": user.id,
            "token": token,
            "platform": platform or "android",
            "device_id": device_id or False,
            "device_name": device_name or False,
            "app_version": app_version or False,
            "active": True,
            "last_seen_at": now,
        }

        if device:
            token_changed_owner = (
                device.user_id.id != user.id
            )

            if token_changed_owner:
                values["token_updated_at"] = now

            device.write(values)

            return device

        values["token_updated_at"] = now

        return self.sudo().create(values)

    def deactivate_device(self):
        self.sudo().write(
            {
                "active": False,
                "last_seen_at": fields.Datetime.now(),
            }
        )

        return True

    @api.model
    def deactivate_token(
        self,
        token,
        user=False,
    ):
        if not token:
            return False

        domain = [
            ("token", "=", token),
            ("active", "=", True),
        ]

        if user:
            domain.append(
                (
                    "user_id",
                    "=",
                    user.id,
                )
            )

        devices = self.sudo().search(domain)

        if not devices:
            return False

        devices.write(
            {
                "active": False,
                "last_seen_at": fields.Datetime.now(),
            }
        )

        return True

    @api.model
    def get_active_tokens(
        self,
        user,
    ):
        if not user:
            return []

        devices = self.sudo().search(
            [
                ("user_id", "=", user.id),
                ("active", "=", True),
                ("token", "!=", False),
            ]
        )

        return devices.mapped("token")