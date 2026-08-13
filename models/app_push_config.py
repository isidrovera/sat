# -*- coding: utf-8 -*-

import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AppPushConfig(models.Model):
    _name = "app.push.config"
    _description = "Configuración Push Firebase"
    _order = "active desc, id desc"

    name = fields.Char(
        string="Nombre",
        required=True,
        default="Firebase Copier Support",
    )

    active = fields.Boolean(
        string="Activo",
        default=True,
        index=True,
    )

    project_id = fields.Char(
        string="Firebase Project ID",
        readonly=True,
    )

    client_email = fields.Char(
        string="Cuenta de servicio",
        readonly=True,
    )

    private_key_id = fields.Char(
        string="Private Key ID",
        readonly=True,
    )

    private_key = fields.Text(
        string="Clave privada Firebase",
        copy=False,
        readonly=True,
        groups="base.group_system",
    )

    service_account_json = fields.Text(
        string="JSON de cuenta de servicio",
        copy=False,
        groups="base.group_system",
        help=(
            "Pega aquí temporalmente el contenido completo "
            "del archivo JSON descargado desde Firebase. "
            "Después de cargarlo, este campo se limpia."
        ),
    )

    credentials_loaded = fields.Boolean(
        string="Credenciales cargadas",
        compute="_compute_credentials_loaded",
    )

    last_credentials_update = fields.Datetime(
        string="Última actualización de credenciales",
        readonly=True,
    )

    # ============================================================
    # ESTADO DE CREDENCIALES
    # ============================================================

    @api.depends(
        "project_id",
        "client_email",
        "private_key",
    )
    def _compute_credentials_loaded(self):
        for record in self:
            record.credentials_loaded = bool(
                record.project_id
                and record.client_email
                and record.private_key
            )

    # ============================================================
    # CARGAR JSON DE FIREBASE
    # ============================================================

    def set_service_account_json(
        self,
        credentials_json,
    ):
        self.ensure_one()

        if not credentials_json:
            raise ValidationError(
                "Debes proporcionar las credenciales "
                "de Firebase."
            )

        try:
            if isinstance(
                credentials_json,
                str,
            ):
                data = json.loads(
                    credentials_json
                )

            elif isinstance(
                credentials_json,
                dict,
            ):
                data = credentials_json

            else:
                raise ValueError(
                    "Formato de credenciales no válido."
                )

        except Exception as exc:
            raise ValidationError(
                "El JSON de credenciales Firebase "
                "no es válido."
            ) from exc

        required_fields = [
            "project_id",
            "client_email",
            "private_key",
        ]

        missing = [
            field_name
            for field_name in required_fields
            if not data.get(field_name)
        ]

        if missing:
            raise ValidationError(
                "Faltan campos obligatorios en las "
                "credenciales Firebase: %s"
                % ", ".join(missing)
            )

        self.write(
            {
                "project_id":
                    data["project_id"],
                "client_email":
                    data["client_email"],
                "private_key_id":
                    data.get(
                        "private_key_id"
                    )
                    or False,
                "private_key":
                    data["private_key"],
                "service_account_json":
                    False,
                "last_credentials_update":
                    fields.Datetime.now(),
            }
        )

        return True

    # ============================================================
    # BOTÓN CARGAR CREDENCIALES
    # ============================================================

    def action_load_service_account_json(self):
        self.ensure_one()

        if not self.service_account_json:
            raise ValidationError(
                "Pega primero el JSON de la "
                "cuenta de servicio Firebase."
            )

        self.set_service_account_json(
            self.service_account_json
        )

        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    # ============================================================
    # CREDENCIALES PARA GOOGLE / FCM
    # ============================================================

    def get_service_account_credentials(self):
        self.ensure_one()

        if not self.credentials_loaded:
            raise ValidationError(
                "Las credenciales Firebase "
                "no están configuradas."
            )

        return {
            "type": "service_account",
            "project_id":
                self.project_id,
            "private_key_id":
                self.private_key_id
                or "",
            "private_key":
                self.private_key,
            "client_email":
                self.client_email,
            "token_uri":
                "https://oauth2.googleapis.com/token",
        }

    # ============================================================
    # CONFIGURACIÓN ACTIVA
    # ============================================================

    @api.model
    def get_active_config(self):
        config = self.sudo().search(
            [
                ("active", "=", True),
            ],
            limit=1,
        )

        if not config:
            raise ValidationError(
                "No existe una configuración "
                "Firebase activa."
            )

        return config

    # ============================================================
    # VALIDACIÓN
    # ============================================================

    @api.constrains(
        "active",
    )
    def _check_single_active_config(self):
        for record in self:
            if not record.active:
                continue

            another = self.search_count(
                [
                    ("active", "=", True),
                    ("id", "!=", record.id),
                ]
            )

            if another:
                raise ValidationError(
                    "Solo puede existir una "
                    "configuración Firebase activa."
                )