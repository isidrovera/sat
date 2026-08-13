# -*- coding: utf-8 -*-

import json
import os

from cryptography.fernet import Fernet, InvalidToken

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

    private_key_encrypted = fields.Text(
        string="Clave privada cifrada",
        copy=False,
        readonly=True,
        groups="base.group_system",
    )

    service_account_json = fields.Text(
        string="JSON de cuenta de servicio",
        copy=False,
        groups="base.group_system",
        help=(
            "Pegue temporalmente aquí el contenido completo "
            "del JSON descargado desde Firebase. "
            "Al cargarlo, la clave privada será cifrada "
            "y este campo quedará vacío."
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

    @api.depends(
        "private_key_encrypted",
    )
    def _compute_credentials_loaded(self):
        for record in self:
            record.credentials_loaded = bool(
                record.private_key_encrypted
            )

    # ============================================================
    # CLAVE MAESTRA
    # ============================================================

    @api.model
    def _get_encryption_key(self):
        key = os.getenv(
            "COPIER_SUPPORT_PUSH_ENCRYPTION_KEY",
            "",
        ).strip()

        if not key:
            raise ValidationError(
                "No está configurada la variable de entorno "
                "COPIER_SUPPORT_PUSH_ENCRYPTION_KEY."
            )

        return key.encode("utf-8")

    @api.model
    def _get_fernet(self):
        try:
            return Fernet(
                self._get_encryption_key()
            )
        except Exception as exc:
            raise ValidationError(
                "COPIER_SUPPORT_PUSH_ENCRYPTION_KEY "
                "no contiene una clave Fernet válida."
            ) from exc

    # ============================================================
    # CIFRADO / DESCIFRADO
    # ============================================================

    @api.model
    def _encrypt_private_key(
        self,
        private_key,
    ):
        if not private_key:
            raise ValidationError(
                "La clave privada de Firebase está vacía."
            )

        return (
            self._get_fernet()
            .encrypt(
                private_key.encode("utf-8")
            )
            .decode("utf-8")
        )

    def _decrypt_private_key(self):
        self.ensure_one()

        if not self.private_key_encrypted:
            raise ValidationError(
                "No existen credenciales Firebase cargadas."
            )

        try:
            return (
                self._get_fernet()
                .decrypt(
                    self.private_key_encrypted.encode(
                        "utf-8"
                    )
                )
                .decode(
                    "utf-8"
                )
            )

        except InvalidToken as exc:
            raise ValidationError(
                "No fue posible descifrar la clave privada. "
                "Verifica la clave maestra configurada "
                "en el servidor."
            ) from exc

    # ============================================================
    # PROCESAR SERVICE ACCOUNT
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

        encrypted_private_key = (
            self._encrypt_private_key(
                data["private_key"]
            )
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
                "private_key_encrypted":
                    encrypted_private_key,
                "service_account_json":
                    False,
                "last_credentials_update":
                    fields.Datetime.now(),
            }
        )

        return True

    # ============================================================
    # BOTÓN DE LA VISTA
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
    # CREDENCIALES PARA FCM
    # ============================================================

    def get_service_account_credentials(self):
        self.ensure_one()

        return {
            "type": "service_account",
            "project_id":
                self.project_id,
            "private_key_id":
                self.private_key_id
                or "",
            "private_key":
                self._decrypt_private_key(),
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
    # VALIDACIONES
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