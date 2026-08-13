# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models


_logger = logging.getLogger(__name__)


class TicketAlquilerPushNotification(models.Model):
    _inherit = "ticket.alquiler"

    # ============================================================
    # FORMATEAR FECHA PARA EL TÉCNICO
    # ============================================================

    def _push_format_agenda(
        self,
        user,
    ):
        self.ensure_one()

        if not self.agenda:
            return ""

        try:
            timezone_name = (
                user.tz
                or "America/Lima"
            )

            local_datetime = (
                fields.Datetime.context_timestamp(
                    self.with_context(
                        tz=timezone_name,
                    ),
                    self.agenda,
                )
            )

            return local_datetime.strftime(
                "%d/%m/%Y %H:%M"
            )

        except Exception:
            return fields.Datetime.to_string(
                self.agenda
            )

    # ============================================================
    # CUERPO DE LA NOTIFICACIÓN
    # ============================================================

    def _push_service_body(
        self,
        user,
    ):
        self.ensure_one()

        parts = []

        if self.name:
            parts.append(
                self.name
            )

        if self.partner_id:
            parts.append(
                self.partner_id.name
            )

        agenda_text = (
            self._push_format_agenda(
                user
            )
        )

        if agenda_text:
            parts.append(
                agenda_text
            )

        return " • ".join(
            parts
        )

    # ============================================================
    # ENVIAR PUSH
    # ============================================================

    def _send_service_push(
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
                    body=self._push_service_body(
                        user
                    ),
                    data={
                        "type": "service",
                        "action": action,
                        "model": "ticket.alquiler",
                        "record_id": self.id,
                        "service_id": self.id,
                    },
                )
            )

            _logger.info(
                "Push servicio %s | "
                "ticket=%s | "
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
            # Un fallo de Firebase nunca debe impedir
            # guardar o asignar el ticket.
            _logger.exception(
                "Error enviando push de servicio | "
                "ticket=%s | usuario=%s",
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
            if not record.responsable:
                continue

            record._send_service_push(
                user=record.responsable,
                title="Nuevo servicio asignado",
                action="assigned",
            )

        return records

    # ============================================================
    # MODIFICACIÓN
    # ============================================================

    def write(
        self,
        vals,
    ):
        relevant_change = (
            "responsable" in vals
            or "agenda" in vals
        )

        if not relevant_change:
            return super().write(
                vals
            )

        previous_values = {}

        for record in self:
            previous_values[
                record.id
            ] = {
                "responsable_id":
                    record.responsable.id
                    if record.responsable
                    else False,
                "agenda":
                    record.agenda,
            }

        result = super().write(
            vals
        )

        for record in self:
            previous = (
                previous_values.get(
                    record.id,
                    {},
                )
            )

            old_user_id = (
                previous.get(
                    "responsable_id"
                )
            )

            new_user_id = (
                record.responsable.id
                if record.responsable
                else False
            )

            old_agenda = (
                previous.get(
                    "agenda"
                )
            )

            new_agenda = (
                record.agenda
            )

            responsible_changed = (
                old_user_id
                != new_user_id
            )

            agenda_changed = (
                old_agenda
                != new_agenda
            )

            # ----------------------------------------------------
            # ASIGNACIÓN / REASIGNACIÓN
            # ----------------------------------------------------

            if (
                responsible_changed
                and record.responsable
            ):
                if old_user_id:
                    title = (
                        "Servicio reasignado"
                    )
                    action = (
                        "reassigned"
                    )
                else:
                    title = (
                        "Nuevo servicio asignado"
                    )
                    action = (
                        "assigned"
                    )

                record._send_service_push(
                    user=record.responsable,
                    title=title,
                    action=action,
                )

                # Si cambió técnico y agenda al mismo tiempo,
                # enviamos una sola notificación.
                continue

            # ----------------------------------------------------
            # CAMBIO DE FECHA / HORA
            # ----------------------------------------------------

            if (
                agenda_changed
                and record.responsable
            ):
                record._send_service_push(
                    user=record.responsable,
                    title=(
                        "Cambio de fecha del servicio"
                    ),
                    action="rescheduled",
                )

        return result