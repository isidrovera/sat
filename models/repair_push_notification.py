# -*- coding: utf-8 -*-

import logging

from odoo import api, models


_logger = logging.getLogger(__name__)


class RepairPushNotification(models.Model):
    _inherit = "reparaciones.reparaciones"

    # ============================================================
    # CUERPO DE LA NOTIFICACIÓN
    # ============================================================

    def _push_repair_body(self):
        self.ensure_one()

        parts = []

        if self.name:
            parts.append(
                self.name
            )

        if self.nombre_maquina:
            parts.append(
                self.nombre_maquina
            )

        if self.serie_id:
            parts.append(
                f"Serie {self.serie_id}"
            )

        if self.cliente_id:
            parts.append(
                self.cliente_id.name
            )

        return " • ".join(
            parts
        )

    # ============================================================
    # ENVIAR PUSH
    # ============================================================

    def _send_repair_push(
        self,
        user,
        title,
        action,
    ):
        self.ensure_one()

        if not user:
            return False

        try:
            result = (
                self.env["app.push.service"]
                .sudo()
                .send_to_user(
                    user=user,
                    title=title,
                    body=self._push_repair_body(),
                    data={
                        "type": "repair",
                        "action": action,
                        "model":
                            "reparaciones.reparaciones",
                        "record_id": self.id,
                        "repair_id": self.id,
                    },
                )
            )

            _logger.info(
                "Push reparación %s | "
                "reparacion=%s | "
                "usuario=%s | "
                "sent=%s | "
                "failed=%s",
                action,
                self.id,
                user.id,
                result.get(
                    "sent",
                    0,
                ),
                result.get(
                    "failed",
                    0,
                ),
            )

            return result

        except Exception:
            _logger.exception(
                "Error enviando push de reparación | "
                "reparacion=%s | usuario=%s",
                self.id,
                user.id,
            )

            return False

    # ============================================================
    # CREACIÓN
    # ============================================================

    @api.model_create_multi
    def create(
        self,
        vals_list,
    ):
        records = super().create(
            vals_list
        )

        for record in records:
            if not record.responsable_id:
                continue

            record._send_repair_push(
                user=record.responsable_id,
                title="Nueva reparación asignada",
                action="assigned",
            )

        return records

    # ============================================================
    # CAMBIO DE RESPONSABLE
    # ============================================================

    def write(
        self,
        vals,
    ):
        if "responsable_id" not in vals:
            return super().write(
                vals
            )

        previous_users = {}

        for record in self:
            previous_users[
                record.id
            ] = (
                record.responsable_id.id
                if record.responsable_id
                else False
            )

        result = super().write(
            vals
        )

        for record in self:
            old_user_id = (
                previous_users.get(
                    record.id
                )
            )

            new_user_id = (
                record.responsable_id.id
                if record.responsable_id
                else False
            )

            if (
                old_user_id
                == new_user_id
            ):
                continue

            if not record.responsable_id:
                continue

            if old_user_id:
                title = (
                    "Reparación reasignada"
                )
                action = (
                    "reassigned"
                )
            else:
                title = (
                    "Nueva reparación asignada"
                )
                action = (
                    "assigned"
                )

            record._send_repair_push(
                user=record.responsable_id,
                title=title,
                action=action,
            )

        return result