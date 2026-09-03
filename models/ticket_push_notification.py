# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from odoo import api, fields, models


_logger = logging.getLogger(__name__)


# ============================================================================
# TICKET.ALQUILER
# - Mantiene push existente al técnico: type=service
# - Agrega push al cliente portal: type=portal_ticket
# ============================================================================


class TicketAlquilerPushNotification(models.Model):
    _inherit = "ticket.alquiler"

    # ------------------------------------------------------------------------
    # FECHA / HORA
    # ------------------------------------------------------------------------

    def _push_format_agenda_timezone(
        self,
        timezone_name,
    ):
        self.ensure_one()

        if not self.agenda:
            return ""

        try:
            timezone_name = (
                timezone_name
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

    def _push_format_agenda(
        self,
        user,
    ):
        self.ensure_one()

        timezone_name = (
            user.tz
            if user and user.tz
            else "America/Lima"
        )

        return self._push_format_agenda_timezone(
            timezone_name
        )

    def _push_format_portal_agenda(self):
        self.ensure_one()

        timezone_name = "America/Lima"

        if (
            self.partner_id
            and "tz" in self.partner_id._fields
            and self.partner_id.tz
        ):
            timezone_name = (
                self.partner_id.tz
            )

        return self._push_format_agenda_timezone(
            timezone_name
        )

    # ------------------------------------------------------------------------
    # CUERPO - TÉCNICO
    # ------------------------------------------------------------------------

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

    # ------------------------------------------------------------------------
    # CUERPO - CLIENTE
    # ------------------------------------------------------------------------

    def _push_portal_ticket_body(self):
        self.ensure_one()

        parts = []

        if self.name:
            parts.append(
                self.name
            )

        agenda_text = (
            self._push_format_portal_agenda()
        )

        if agenda_text:
            parts.append(
                agenda_text
            )

        return " • ".join(
            parts
        )

    # ------------------------------------------------------------------------
    # PUSH - TÉCNICO
    # ------------------------------------------------------------------------

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
                self.env[
                    "app.push.service"
                ]
                .sudo()
                .send_to_user(
                    user=user,
                    title=title,
                    body=self._push_service_body(
                        user
                    ),
                    data={
                        "type":
                            "service",
                        "action":
                            action,
                        "model":
                            "ticket.alquiler",
                        "record_id":
                            self.id,
                        "service_id":
                            self.id,
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
            # Firebase jamás debe impedir guardar
            # o asignar un ticket.
            _logger.exception(
                "Error enviando push de servicio | "
                "ticket=%s | usuario=%s",
                self.id,
                user.id,
            )

            return False

    # ------------------------------------------------------------------------
    # PUSH - CLIENTE PORTAL
    # ------------------------------------------------------------------------

    def _send_portal_ticket_push(
        self,
        title,
        action,
    ):
        self.ensure_one()

        if not self.partner_id:
            return False

        try:
            result = (
                self.env[
                    "app.push.service"
                ]
                .sudo()
                .send_to_portal_company(
                    company=self.partner_id,
                    notification_type=(
                        "portal_ticket"
                    ),
                    record_id=self.id,
                    title=title,
                    body=(
                        self
                        ._push_portal_ticket_body()
                    ),
                    extra_data={
                        "action":
                            action,
                        "model":
                            "ticket.alquiler",
                    },
                )
            )

            _logger.info(
                "Push portal ticket %s | "
                "ticket=%s | "
                "empresa=%s | "
                "sent=%s | "
                "failed=%s",
                action,
                self.id,
                self.partner_id.id,
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
                "Error enviando push portal ticket | "
                "ticket=%s | empresa=%s",
                self.id,
                (
                    self.partner_id.id
                    if self.partner_id
                    else False
                ),
            )

            return False

    # ------------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------------

    @api.model_create_multi
    def create(
        self,
        vals_list,
    ):
        records = super().create(
            vals_list
        )

        for record in records:

            # Técnico.
            if record.responsable:
                record._send_service_push(
                    user=record.responsable,
                    title=(
                        "Nuevo servicio asignado"
                    ),
                    action="assigned",
                )

            # Cliente.
            if (
                record.partner_id
                and record.estado
                == "finalizado"
            ):
                record._send_portal_ticket_push(
                    title=(
                        "Servicio finalizado"
                    ),
                    action="finished",
                )

            elif (
                record.partner_id
                and record.estado
                == "en_ruta"
            ):
                record._send_portal_ticket_push(
                    title="Técnico en ruta",
                    action=(
                        "technician_en_route"
                    ),
                )

            elif (
                record.partner_id
                and record.agenda
            ):
                record._send_portal_ticket_push(
                    title="Visita programada",
                    action="scheduled",
                )

        return records

    # ------------------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------------------

    def write(
        self,
        vals,
    ):
        relevant_change = (
            "responsable" in vals
            or "agenda" in vals
            or "estado" in vals
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
                "estado":
                    record.estado,
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

            old_state = (
                previous.get(
                    "estado"
                )
            )

            new_state = (
                record.estado
            )

            responsible_changed = (
                old_user_id
                != new_user_id
            )

            agenda_changed = (
                old_agenda
                != new_agenda
            )

            state_changed = (
                old_state
                != new_state
            )

            # ================================================================
            # TÉCNICO
            # ================================================================

            technician_notification_sent = (
                False
            )

            if (
                responsible_changed
                and record.responsable
            ):
                if old_user_id:
                    title = (
                        "Servicio reasignado"
                    )
                    action = "reassigned"
                else:
                    title = (
                        "Nuevo servicio asignado"
                    )
                    action = "assigned"

                record._send_service_push(
                    user=record.responsable,
                    title=title,
                    action=action,
                )

                technician_notification_sent = (
                    True
                )

            # Si técnico y agenda cambiaron juntos,
            # mantenemos una sola notificación técnica.
            if (
                not technician_notification_sent
                and agenda_changed
                and record.responsable
            ):
                record._send_service_push(
                    user=record.responsable,
                    title=(
                        "Cambio de fecha "
                        "del servicio"
                    ),
                    action="rescheduled",
                )

            # ================================================================
            # CLIENTE
            #
            # Máximo un push portal por write().
            # Prioridad:
            #   1. finalizado
            #   2. en_ruta
            #   3. agenda
            # ================================================================

            if (
                state_changed
                and new_state
                == "finalizado"
            ):
                record._send_portal_ticket_push(
                    title=(
                        "Servicio finalizado"
                    ),
                    action="finished",
                )

            elif (
                state_changed
                and new_state
                == "en_ruta"
            ):
                record._send_portal_ticket_push(
                    title="Técnico en ruta",
                    action=(
                        "technician_en_route"
                    ),
                )

            elif agenda_changed:
                if old_agenda:
                    title = (
                        "Visita reprogramada"
                    )
                    action = "rescheduled"
                else:
                    title = (
                        "Visita programada"
                    )
                    action = "scheduled"

                record._send_portal_ticket_push(
                    title=title,
                    action=action,
                )

        return result


# ============================================================================
# CLIENT.SERVICE.EVALUATION
# - Push al quedar disponible/enviada
# - Push próximo a vencer <= 48 horas
# - Reutiliza el cron/recordatorio que ya existe en el modelo
# ============================================================================


class ClientServiceEvaluationPushNotification(
    models.Model
):
    _inherit = "client.service.evaluation"

    push_near_expiry_sent = fields.Boolean(
        string=(
            "Push próximo a vencer enviado"
        ),
        default=False,
        copy=False,
        readonly=True,
    )

    # ------------------------------------------------------------------------
    # CUERPO
    # ------------------------------------------------------------------------

    def _push_evaluation_body(self):
        self.ensure_one()

        parts = []

        if self.name:
            parts.append(
                self.name
            )

        if self.expiration_date:
            try:
                expiration_local = (
                    fields.Datetime
                    .context_timestamp(
                        self.with_context(
                            tz="America/Lima"
                        ),
                        self.expiration_date,
                    )
                )

                parts.append(
                    "Vence "
                    + expiration_local.strftime(
                        "%d/%m/%Y %H:%M"
                    )
                )

            except Exception:
                parts.append(
                    "Vence "
                    + fields.Datetime.to_string(
                        self.expiration_date
                    )
                )

        return " • ".join(
            parts
        )

    # ------------------------------------------------------------------------
    # PUSH
    # ------------------------------------------------------------------------

    def _send_portal_evaluation_push(
        self,
        title,
        action,
    ):
        self.ensure_one()

        if not self.partner_id:
            return False

        try:
            result = (
                self.env[
                    "app.push.service"
                ]
                .sudo()
                .send_to_portal_company(
                    company=self.partner_id,
                    notification_type=(
                        "portal_evaluation"
                    ),
                    record_id=self.id,
                    title=title,
                    body=(
                        self
                        ._push_evaluation_body()
                    ),
                    extra_data={
                        "action":
                            action,
                        "model":
                            (
                                "client."
                                "service."
                                "evaluation"
                            ),
                    },
                )
            )

            _logger.info(
                "Push portal evaluación %s | "
                "evaluacion=%s | "
                "empresa=%s | "
                "sent=%s | "
                "failed=%s",
                action,
                self.id,
                self.partner_id.id,
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
                "Error enviando push evaluación | "
                "evaluacion=%s | empresa=%s",
                self.id,
                (
                    self.partner_id.id
                    if self.partner_id
                    else False
                ),
            )

            return False

    # ------------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------------

    @api.model_create_multi
    def create(
        self,
        vals_list,
    ):
        records = super().create(
            vals_list
        )

        # Normalmente la evaluación nace draft y el modelo
        # actual después la pasa a sent.
        # Si alguna evaluación nace directamente sent,
        # también se notifica.
        for record in records:
            if (
                record.state == "sent"
                and record.partner_id
            ):
                record._send_portal_evaluation_push(
                    title=(
                        "Evaluación pendiente"
                    ),
                    action="pending",
                )

        return records

    # ------------------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------------------

    def write(
        self,
        vals,
    ):
        previous_states = {
            record.id:
                record.state
            for record in self
        }

        result = super().write(
            vals
        )

        if "state" not in vals:
            return result

        for record in self:
            old_state = (
                previous_states.get(
                    record.id
                )
            )

            new_state = (
                record.state
            )

            # Solo al pasar a sent.
            if (
                old_state != "sent"
                and new_state == "sent"
            ):
                record._send_portal_evaluation_push(
                    title=(
                        "Evaluación pendiente"
                    ),
                    action="pending",
                )

        return result

    # ------------------------------------------------------------------------
    # RECORDATORIO EXISTENTE
    # ------------------------------------------------------------------------

    def action_send_reminder(self):
        self.ensure_one()

        result = super().action_send_reminder()

        if not result:
            return result

        if (
            self.state != "sent"
            or not self.expiration_date
            or self.push_near_expiry_sent
        ):
            return result

        now = fields.Datetime.now()
        limit_48h = (
            now
            + timedelta(
                hours=48
            )
        )

        if (
            self.expiration_date > now
            and self.expiration_date
            <= limit_48h
        ):
            push_result = (
                self
                ._send_portal_evaluation_push(
                    title=(
                        "Evaluación próxima "
                        "a vencer"
                    ),
                    action="near_expiry",
                )
            )

            # Marcamos enviado únicamente si hubo
            # al menos un dispositivo destinatario.
            if (
                isinstance(
                    push_result,
                    dict,
                )
                and (
                    push_result.get(
                        "sent",
                        0,
                    )
                    > 0
                )
            ):
                super(
                    ClientServiceEvaluationPushNotification,
                    self,
                ).write(
                    {
                        "push_near_expiry_sent":
                            True,
                    }
                )

        return result


# ============================================================================
# TONER.COUNTER.SUBMISSION
# - Solo estados relevantes al cliente:
#   aprobada_gerencia
#   en_despacho
#   entregada
# ============================================================================


class TonerCounterSubmissionPushNotification(
    models.Model
):
    _inherit = "toner.counter.submission"

    PORTAL_PUSH_STATES = {
        "aprobada_gerencia": {
            "title":
                "Solicitud de tóner aprobada",
            "action":
                "approved",
        },
        "en_despacho": {
            "title":
                "Tóner en despacho",
            "action":
                "dispatch",
        },
        "entregada": {
            "title":
                "Tóner entregado",
            "action":
                "delivered",
        },
    }

    # ------------------------------------------------------------------------
    # CUERPO
    # ------------------------------------------------------------------------

    def _push_toner_body(self):
        self.ensure_one()

        parts = []

        if self.display_name:
            parts.append(
                self.display_name
            )

        if (
            "equipment_id"
            in self._fields
            and self.equipment_id
        ):
            parts.append(
                self.equipment_id.display_name
            )

        return " • ".join(
            parts
        )

    # ------------------------------------------------------------------------
    # PUSH
    # ------------------------------------------------------------------------

    def _send_portal_toner_push(
        self,
        title,
        action,
    ):
        self.ensure_one()

        if not self.partner_id:
            return False

        try:
            result = (
                self.env[
                    "app.push.service"
                ]
                .sudo()
                .send_to_portal_company(
                    company=self.partner_id,
                    notification_type=(
                        "portal_toner"
                    ),
                    record_id=self.id,
                    title=title,
                    body=self._push_toner_body(),
                    extra_data={
                        "action":
                            action,
                        "model":
                            (
                                "toner."
                                "counter."
                                "submission"
                            ),
                        "state":
                            self.state,
                    },
                )
            )

            _logger.info(
                "Push portal tóner %s | "
                "solicitud=%s | "
                "empresa=%s | "
                "sent=%s | "
                "failed=%s",
                action,
                self.id,
                self.partner_id.id,
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
                "Error enviando push tóner | "
                "solicitud=%s | empresa=%s",
                self.id,
                (
                    self.partner_id.id
                    if self.partner_id
                    else False
                ),
            )

            return False

    # ------------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------------

    @api.model_create_multi
    def create(
        self,
        vals_list,
    ):
        records = super().create(
            vals_list
        )

        # Normalmente nace en recibida, que NO genera push.
        # Esto cubre únicamente una creación manual excepcional
        # directamente en un estado notificable.
        for record in records:
            config = (
                self.PORTAL_PUSH_STATES.get(
                    record.state
                )
            )

            if (
                config
                and record.partner_id
            ):
                record._send_portal_toner_push(
                    title=config[
                        "title"
                    ],
                    action=config[
                        "action"
                    ],
                )

        return records

    # ------------------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------------------

    def write(
        self,
        vals,
    ):
        if "state" not in vals:
            return super().write(
                vals
            )

        previous_states = {
            record.id:
                record.state
            for record in self
        }

        result = super().write(
            vals
        )

        for record in self:
            old_state = (
                previous_states.get(
                    record.id
                )
            )

            new_state = (
                record.state
            )

            if old_state == new_state:
                continue

            config = (
                self.PORTAL_PUSH_STATES.get(
                    new_state
                )
            )

            if not config:
                continue

            record._send_portal_toner_push(
                title=config[
                    "title"
                ],
                action=config[
                    "action"
                ],
            )

        return result
