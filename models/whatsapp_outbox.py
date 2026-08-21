# -*- coding: utf-8 -*-

import json
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class WhatsappOutbox(models.Model):
    """
    Cola persistente de salida hacia n8n / Baileys.

    Objetivos:
    - conservar trazabilidad del mensaje;
    - soportar reintentos controlados;
    - hacer idempotentes los ACK de envío/entrega/lectura;
    - evitar que una lectura repetida de /outbox/pending entregue
      inmediatamente el mismo registro varias veces.

    El estado ``queued`` funciona como una reserva temporal (lease).
    Si n8n obtiene un mensaje y cae antes de confirmar el envío, el
    registro puede volver a quedar disponible al vencer ese lease.
    """

    _name = "whatsapp.outbox"
    _description = "Cola de salida WhatsApp"
    _order = "scheduled_at asc, create_date asc"
    _rec_name = "name"

    # ==========================================================
    # Identificación
    # ==========================================================
    name = fields.Char(
        string="Referencia",
        default="Mensaje WhatsApp",
        required=True,
        index=True,
    )

    # ==========================================================
    # Relaciones
    # ==========================================================
    session_id = fields.Many2one(
        comodel_name="whatsapp.session",
        string="Sesión",
        index=True,
        ondelete="set null",
    )

    message_id = fields.Many2one(
        comodel_name="whatsapp.message",
        string="Mensaje relacionado",
        index=True,
        ondelete="set null",
    )

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contacto",
        index=True,
        ondelete="set null",
    )

    company_id = fields.Many2one(
        comodel_name="res.partner",
        string="Empresa",
        domain=[("is_company", "=", True)],
        index=True,
        ondelete="set null",
    )

    media_id = fields.Many2one(
        comodel_name="whatsapp.media",
        string="Media",
        ondelete="set null",
    )

    # ==========================================================
    # Identificadores
    # ==========================================================
    phone = fields.Char(string="Teléfono", index=True)
    jid = fields.Char(string="JID", index=True)
    lid = fields.Char(string="LID", index=True)

    # ==========================================================
    # Contenido
    # ==========================================================
    message_type = fields.Selection(
        selection=[
            ("text", "Texto"),
            ("image", "Imagen"),
            ("audio", "Audio"),
            ("video", "Video"),
            ("document", "Documento"),
            ("location", "Ubicación"),
            ("contact", "Contacto"),
            ("other", "Otro"),
        ],
        string="Tipo",
        default="text",
        required=True,
    )

    content = fields.Text(string="Contenido")

    template_used = fields.Char(
        string="Plantilla usada",
        index=True,
        help="Nombre de la plantilla whatsapp.template que originó este mensaje.",
    )

    # ==========================================================
    # Flujo conversacional (snapshot)
    # ==========================================================
    current_flow = fields.Selection(
        selection=[
            ("none", "Sin flujo"),
            ("registration", "Registro"),
            ("toner", "Solicitud de tóner"),
            ("onsite", "Servicio presencial"),
            ("remote", "Soporte remoto"),
            ("greeting", "Saludo"),
            ("other", "Otro"),
        ],
        string="Flujo activo",
        default="none",
        index=True,
    )

    flow_step = fields.Char(
        string="Paso del flujo",
        index=True,
        help="conversation_state activo cuando se encoló este mensaje.",
    )

    # ==========================================================
    # Estado y prioridad
    # ==========================================================
    state = fields.Selection(
        selection=[
            ("pending", "Pendiente"),
            ("queued", "En cola"),
            ("sending", "Enviando"),
            ("sent", "Enviado"),
            ("delivered", "Entregado"),
            ("read", "Leído"),
            ("failed", "Fallido"),
            ("cancelled", "Cancelado"),
        ],
        string="Estado",
        default="pending",
        required=True,
        index=True,
    )

    priority = fields.Selection(
        selection=[
            ("0", "Baja"),
            ("1", "Normal"),
            ("2", "Alta"),
            ("3", "Crítica"),
        ],
        string="Prioridad",
        default="1",
        index=True,
    )

    # ==========================================================
    # Programación / envío
    # ==========================================================
    scheduled_at = fields.Datetime(
        string="Programado para",
        default=fields.Datetime.now,
        index=True,
    )

    queued_at = fields.Datetime(string="Encolado el")
    sending_at = fields.Datetime(string="Enviando desde")
    sent_at = fields.Datetime(string="Enviado el", index=True)
    delivered_at = fields.Datetime(string="Entregado el")
    read_at = fields.Datetime(string="Leído el")

    external_message_id = fields.Char(string="ID mensaje externo", index=True)

    # ==========================================================
    # Reintentos
    # ==========================================================
    retry_count = fields.Integer(string="Reintentos", default=0)
    max_retries = fields.Integer(string="Máximo reintentos", default=3)
    next_retry_at = fields.Datetime(string="Próximo reintento", index=True)
    last_retry_at = fields.Datetime(string="Último reintento")

    error_message = fields.Text(string="Error")
    error_code = fields.Char(string="Código de error", index=True)

    # ==========================================================
    # Payload
    # ==========================================================
    raw_payload = fields.Text(
        string="Payload (JSON)",
        default="{}",
    )

    # ==========================================================
    # Computes
    # ==========================================================
    can_retry = fields.Boolean(
        string="Puede reintentarse",
        compute="_compute_can_retry",
        store=False,
    )

    is_ready_to_send = fields.Boolean(
        string="Listo para enviar",
        compute="_compute_is_ready_to_send",
        store=False,
        search="_search_is_ready_to_send",
    )

    @api.depends("state", "retry_count", "max_retries")
    def _compute_can_retry(self):
        for rec in self:
            rec.can_retry = (
                rec.state in ("failed", "pending")
                and rec.retry_count < rec.max_retries
            )

    @api.depends("state", "scheduled_at", "next_retry_at")
    def _compute_is_ready_to_send(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.state not in ("pending", "queued"):
                rec.is_ready_to_send = False
                continue
            ref_time = rec.next_retry_at or rec.scheduled_at
            rec.is_ready_to_send = not ref_time or ref_time <= now

    def _search_is_ready_to_send(self, operator, value):
        now = fields.Datetime.now()
        if operator == "=" and value:
            return [
                ("state", "in", ["pending", "queued"]),
                "|",
                ("next_retry_at", "<=", now),
                "&", ("next_retry_at", "=", False), ("scheduled_at", "<=", now),
            ]
        return [("id", "in", [])]

    # ==========================================================
    # Create / Write
    # ==========================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("raw_payload"):
                vals["raw_payload"] = "{}"
            if isinstance(vals.get("raw_payload"), dict):
                try:
                    vals["raw_payload"] = json.dumps(
                        vals["raw_payload"], ensure_ascii=False, default=str,
                    )
                except Exception as e:
                    _logger.error(
                        "[WA-OUTBOX] No se pudo serializar raw_payload: %s", str(e),
                    )
                    vals["raw_payload"] = "{}"

        records = super().create(vals_list)

        for rec in records:
            _logger.info(
                "[WA-OUTBOX] Outbox creado id=%s session=%s partner=%s type=%s state=%s priority=%s scheduled=%s",
                rec.id, rec.session_id.id if rec.session_id else False,
                rec.partner_id.id if rec.partner_id else False,
                rec.message_type, rec.state, rec.priority, rec.scheduled_at,
            )

        return records

    # ==========================================================
    # Helpers raw_payload
    # ==========================================================
    def get_raw_payload(self):
        self.ensure_one()
        if not self.raw_payload:
            return {}
        try:
            return json.loads(self.raw_payload)
        except Exception as e:
            _logger.error(
                "[WA-OUTBOX] Error parseando raw_payload id=%s error=%s",
                self.id, str(e),
            )
            return {}

    def set_raw_payload(self, data):
        self.ensure_one()
        if not isinstance(data, dict):
            _logger.error(
                "[WA-OUTBOX] set_raw_payload tipo inválido id=%s tipo=%s",
                self.id, type(data).__name__,
            )
            raise ValidationError(_("raw_payload debe ser un diccionario."))
        try:
            serialized = json.dumps(data, ensure_ascii=False, default=str)
        except Exception as e:
            _logger.exception(
                "[WA-OUTBOX] Error serializando raw_payload id=%s error=%s",
                self.id, str(e),
            )
            raise ValidationError(_("No se pudo serializar raw_payload: %s") % str(e))
        self.write({"raw_payload": serialized})
        return True

    # ==========================================================
    # Helpers de envío / reintento
    # ==========================================================
    def _get_queue_lease_minutes(self):
        """
        Tiempo durante el cual un mensaje marcado queued queda reservado.

        Esto evita que dos lecturas consecutivas de /outbox/pending
        devuelvan inmediatamente el mismo registro.
        """
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "sat.whatsapp_outbox_queue_lease_minutes",
                "5",
            )
        )

        try:
            minutes = int(value)
        except Exception:
            minutes = 5

        return max(minutes, 1)

    def _get_retry_backoff_minutes(self, retry_count):
        """
        Backoff conservador:
        1er fallo -> 1 min
        2do fallo -> 5 min
        3er fallo -> 15 min
        posteriores -> máximo 120 min
        """
        schedule = [1, 5, 15, 30, 60, 120]

        try:
            retry_count = int(retry_count or 1)
        except Exception:
            retry_count = 1

        index = max(retry_count - 1, 0)

        if index < len(schedule):
            return schedule[index]

        return 120

    def _is_terminal_delivery_state(self):
        self.ensure_one()
        return self.state in (
            "sent",
            "delivered",
            "read",
            "cancelled",
        )

    # ==========================================================
    # Acciones de estado
    # ==========================================================
    def action_mark_queued(self):
        """
        Reserva temporalmente el registro para que n8n/Baileys lo procese.

        Se mantiene el estado queued, pero next_retry_at se utiliza como
        vencimiento del lease. Mientras no venza, el endpoint actual de
        pendientes no volverá a devolver el mismo registro.
        """
        lease_minutes = self._get_queue_lease_minutes()
        now = fields.Datetime.now()

        for rec in self:
            if rec.state not in ("pending", "failed"):
                _logger.warning(
                    "[WA-OUTBOX] mark_queued ignorado | "
                    "id=%s state=%s",
                    rec.id,
                    rec.state,
                )
                continue

            lease_until = now + timedelta(
                minutes=lease_minutes
            )

            _logger.info(
                "[WA-OUTBOX] Reservando para envío | "
                "id=%s from_state=%s lease_minutes=%s lease_until=%s",
                rec.id,
                rec.state,
                lease_minutes,
                lease_until,
            )

            rec.write({
                "state": "queued",
                "queued_at": now,
                "next_retry_at": lease_until,
            })

        return True

    def action_mark_sending(self):
        """
        Marca como enviando.

        No permite retroceder un mensaje que ya fue enviado, entregado,
        leído o cancelado.
        """
        for rec in self:
            if rec._is_terminal_delivery_state():
                _logger.warning(
                    "[WA-OUTBOX] mark_sending ignorado en estado terminal | "
                    "id=%s state=%s",
                    rec.id,
                    rec.state,
                )
                continue

            if rec.state not in (
                "pending",
                "queued",
                "failed",
                "sending",
            ):
                _logger.warning(
                    "[WA-OUTBOX] mark_sending estado inesperado | "
                    "id=%s state=%s",
                    rec.id,
                    rec.state,
                )
                continue

            if rec.state == "sending":
                _logger.debug(
                    "[WA-OUTBOX] mark_sending idempotente | id=%s",
                    rec.id,
                )
                continue

            _logger.info(
                "[WA-OUTBOX] Marcando como enviando | "
                "id=%s from_state=%s",
                rec.id,
                rec.state,
            )

            rec.write({
                "state": "sending",
                "sending_at": fields.Datetime.now(),
            })

        return True

    def action_mark_sent(
        self,
        external_message_id=False,
    ):
        """
        Confirma envío exitoso desde n8n/Baileys.

        Es idempotente: repetir el mismo ACK no vuelve a tocar la sesión ni
        degrada estados delivered/read.
        """
        for rec in self:
            if rec.state in ("delivered", "read"):
                if (
                    external_message_id
                    and not rec.external_message_id
                ):
                    rec.write({
                        "external_message_id": external_message_id,
                    })

                _logger.info(
                    "[WA-OUTBOX] ACK sent tardío ignorado | "
                    "id=%s state=%s external_id=%s",
                    rec.id,
                    rec.state,
                    external_message_id or rec.external_message_id,
                )
                continue

            if rec.state == "cancelled":
                _logger.warning(
                    "[WA-OUTBOX] ACK sent recibido para cancelado | "
                    "id=%s external_id=%s",
                    rec.id,
                    external_message_id,
                )
                continue

            if rec.state == "sent":
                vals = {}

                if (
                    external_message_id
                    and not rec.external_message_id
                ):
                    vals["external_message_id"] = external_message_id

                if vals:
                    rec.write(vals)

                _logger.info(
                    "[WA-OUTBOX] ACK sent idempotente | "
                    "id=%s external_id=%s",
                    rec.id,
                    external_message_id or rec.external_message_id,
                )
                continue

            vals = {
                "state": "sent",
                "sent_at": fields.Datetime.now(),
                "next_retry_at": False,
                "error_message": False,
                "error_code": False,
            }

            if external_message_id:
                vals["external_message_id"] = (
                    external_message_id
                )

            _logger.info(
                "[WA-OUTBOX] Envío confirmado | "
                "id=%s from_state=%s external_id=%s retry=%s/%s",
                rec.id,
                rec.state,
                external_message_id,
                rec.retry_count,
                rec.max_retries,
            )

            rec.write(vals)

            # Actualizar actividad solo en la primera confirmación real.
            try:
                if rec.session_id:
                    rec.session_id.sudo().touch(
                        bot_message=rec.content or False,
                    )
            except Exception:
                _logger.exception(
                    "[WA-OUTBOX] Error actualizando sesión al confirmar envío | "
                    "outbox_id=%s session_id=%s",
                    rec.id,
                    rec.session_id.id if rec.session_id else False,
                )

            if rec.message_id and external_message_id:
                try:
                    rec.message_id.sudo().write({
                        "external_message_id": (
                            external_message_id
                        ),
                    })
                except Exception:
                    _logger.exception(
                        "[WA-OUTBOX] Error propagando external_message_id | "
                        "outbox_id=%s message_id=%s",
                        rec.id,
                        rec.message_id.id,
                    )

        return True

    def action_mark_delivered(self):
        """Marca como entregado sin degradar un mensaje ya leído."""
        for rec in self:
            if rec.state == "read":
                _logger.debug(
                    "[WA-OUTBOX] ACK delivered ignorado porque ya está read | "
                    "id=%s",
                    rec.id,
                )
                continue

            if rec.state == "cancelled":
                _logger.warning(
                    "[WA-OUTBOX] ACK delivered para cancelado | id=%s",
                    rec.id,
                )
                continue

            if rec.state == "delivered":
                _logger.debug(
                    "[WA-OUTBOX] ACK delivered idempotente | id=%s",
                    rec.id,
                )
                continue

            rec.write({
                "state": "delivered",
                "delivered_at": (
                    rec.delivered_at
                    or fields.Datetime.now()
                ),
                "next_retry_at": False,
            })

            _logger.info(
                "[WA-OUTBOX] Entrega confirmada | id=%s",
                rec.id,
            )

        return True

    def action_mark_read(self):
        """Marca como leído de forma idempotente."""
        for rec in self:
            if rec.state == "cancelled":
                _logger.warning(
                    "[WA-OUTBOX] ACK read para cancelado | id=%s",
                    rec.id,
                )
                continue

            if rec.state == "read":
                _logger.debug(
                    "[WA-OUTBOX] ACK read idempotente | id=%s",
                    rec.id,
                )
                continue

            now = fields.Datetime.now()

            rec.write({
                "state": "read",
                "delivered_at": (
                    rec.delivered_at
                    or now
                ),
                "read_at": rec.read_at or now,
                "next_retry_at": False,
            })

            _logger.info(
                "[WA-OUTBOX] Lectura confirmada | id=%s",
                rec.id,
            )

        return True

    def action_mark_failed(
        self,
        error_message=False,
        error_code=False,
        schedule_retry=True,
    ):
        """
        Marca un intento como fallido y programa reintento con backoff.

        Un fallo tardío nunca debe sobrescribir un mensaje ya confirmado
        como sent/delivered/read ni uno cancelado.
        """
        for rec in self:
            if rec._is_terminal_delivery_state():
                _logger.warning(
                    "[WA-OUTBOX] mark_failed ignorado en estado terminal | "
                    "id=%s state=%s error=%s",
                    rec.id,
                    rec.state,
                    error_message,
                )
                continue

            new_retry_count = rec.retry_count + 1
            now = fields.Datetime.now()

            vals = {
                "state": "failed",
                "retry_count": new_retry_count,
                "last_retry_at": now,
                "sending_at": False,
                "error_message": (
                    error_message
                    or "Error enviando mensaje WhatsApp"
                ),
                "error_code": error_code or False,
                "next_retry_at": False,
            }

            if (
                schedule_retry
                and new_retry_count < rec.max_retries
            ):
                backoff_minutes = (
                    self._get_retry_backoff_minutes(
                        new_retry_count
                    )
                )

                vals["next_retry_at"] = (
                    now
                    + timedelta(
                        minutes=backoff_minutes
                    )
                )

                _logger.warning(
                    "[WA-OUTBOX] Envío fallido; reintento programado | "
                    "id=%s retry=%s/%s backoff_min=%s next_retry=%s "
                    "error_code=%s error=%s",
                    rec.id,
                    new_retry_count,
                    rec.max_retries,
                    backoff_minutes,
                    vals["next_retry_at"],
                    error_code or False,
                    error_message,
                )
            else:
                _logger.error(
                    "[WA-OUTBOX] Envío fallido sin más reintentos | "
                    "id=%s retry=%s/%s schedule_retry=%s "
                    "error_code=%s error=%s",
                    rec.id,
                    new_retry_count,
                    rec.max_retries,
                    bool(schedule_retry),
                    error_code or False,
                    error_message,
                )

            rec.write(vals)

        return True

    def action_cancel(self, reason=False):
        """Cancela un mensaje que todavía no fue entregado."""
        for rec in self:
            if rec.state in (
                "sent",
                "delivered",
                "read",
            ):
                raise UserError(
                    _(
                        "No se puede cancelar un mensaje que ya fue "
                        "enviado o entregado."
                    )
                )

            if rec.state == "cancelled":
                continue

            _logger.info(
                "[WA-OUTBOX] Cancelando | id=%s state=%s reason=%s",
                rec.id,
                rec.state,
                reason,
            )

            rec.write({
                "state": "cancelled",
                "next_retry_at": False,
                "error_message": (
                    reason
                    or "Cancelado manualmente"
                ),
            })

        return True

    def action_retry(self):
        """
        Fuerza reintento manual únicamente desde estado failed.

        Si se desea reutilizar un registro que agotó los reintentos,
        primero debe ejecutarse action_reset_retries().
        """
        for rec in self:
            if rec.state != "failed":
                raise UserError(
                    _(
                        "Solo los mensajes fallidos pueden reintentarse "
                        "manualmente. Estado actual: %s"
                    )
                    % rec.state
                )

            if rec.retry_count >= rec.max_retries:
                raise UserError(
                    _(
                        "El mensaje agotó sus reintentos (%s/%s). "
                        "Restablece el contador antes de reintentarlo."
                    )
                    % (
                        rec.retry_count,
                        rec.max_retries,
                    )
                )

            _logger.info(
                "[WA-OUTBOX] Reintento manual | "
                "id=%s retry=%s/%s",
                rec.id,
                rec.retry_count,
                rec.max_retries,
            )

            rec.write({
                "state": "pending",
                "next_retry_at": False,
                "sending_at": False,
                "error_message": False,
                "error_code": False,
            })

        return True

    def action_reset_retries(self):
        """Resetea el contador de reintentos."""
        for rec in self:
            _logger.info(
                "[WA-OUTBOX] Reset de reintentos id=%s previo=%s",
                rec.id, rec.retry_count,
            )
            rec.write({
                "retry_count": 0,
                "next_retry_at": False,
                "last_retry_at": False,
            })
        return True

    # ==========================================================
    # Consulta para n8n
    # ==========================================================
    @api.model
    def get_pending_payload(
        self,
        limit=20,
        partner_id=False,
    ):
        """
        Obtiene mensajes listos y los reserva antes de devolverlos.

        El controlador histórico /outbox/pending realiza una búsqueda
        equivalente y llama action_mark_queued(). Por compatibilidad se
        conserva el formato de salida.
        """
        try:
            limit = int(limit or 20)
        except Exception:
            limit = 20

        limit = max(
            1,
            min(limit, 100),
        )

        domain = [
            ("is_ready_to_send", "=", True),
        ]

        if partner_id:
            domain.append(
                ("partner_id", "=", partner_id)
            )

        outbox_records = self.search(
            domain,
            order=(
                "priority desc, "
                "scheduled_at asc, "
                "id asc"
            ),
            limit=limit,
        )

        _logger.info(
            "[WA-OUTBOX] Pendientes encontrados | "
            "limit=%s partner=%s found=%s",
            limit,
            partner_id,
            len(outbox_records),
        )

        items = []

        for rec in outbox_records:
            rec.action_mark_queued()
            items.append(
                rec.to_n8n_payload()
            )

        return items

    def to_n8n_payload(self):
        """Convierte el outbox a payload listo para n8n/Baileys."""
        self.ensure_one()
        return {
            "outbox_id": self.id,
            "name": self.name,
            "session_id": self.session_id.id if self.session_id else False,
            "partner_id": self.partner_id.id if self.partner_id else False,
            "phone": self.phone,
            "jid": self.jid,
            "lid": self.lid,
            "message_type": self.message_type,
            "content": self.content or "",
            "template_used": self.template_used,
            "current_flow": self.current_flow,
            "flow_step": self.flow_step,
            "priority": self.priority,
            "state": self.state,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "scheduled_at": (
                self.scheduled_at.isoformat()
                if self.scheduled_at
                else False
            ),
            "queued_at": (
                self.queued_at.isoformat()
                if self.queued_at
                else False
            ),
            "lease_until": (
                self.next_retry_at.isoformat()
                if self.state == "queued"
                and self.next_retry_at
                else False
            ),
            "external_message_id": (
                self.external_message_id
                or False
            ),
            "media": {
                "id": self.media_id.id if self.media_id else False,
                "type": self.media_id.media_type if self.media_id else False,
                "url": self.media_id.url if self.media_id else False,
                "filename": self.media_id.filename if self.media_id else False,
                "mimetype": self.media_id.mimetype if self.media_id else False,
                "caption": self.media_id.caption if self.media_id else False,
            } if self.media_id else False,
        }

    # ==========================================================
    # Cron de reintentos
    # ==========================================================
    @api.model
    def cron_retry_failed(self):
        """
        Cron que busca mensajes fallidos con next_retry_at vencido y los pasa a pending
        para que vuelvan a ser tomados por n8n.
        """
        now = fields.Datetime.now()
        domain = [
            ("state", "=", "failed"),
            ("next_retry_at", "!=", False),
            ("next_retry_at", "<=", now),
        ]

        failed_records = self.search(domain)

        _logger.info(
            "[WA-OUTBOX] cron_retry_failed: %s mensajes a reintentar",
            len(failed_records),
        )

        for rec in failed_records:
            try:
                if rec.retry_count >= rec.max_retries:
                    continue
                _logger.info(
                    "[WA-OUTBOX] Reintentando automáticamente id=%s retry=%s/%s",
                    rec.id, rec.retry_count, rec.max_retries,
                )
                rec.write({
                    "state": "pending",
                    "next_retry_at": False,
                })
            except Exception as e:
                _logger.exception(
                    "[WA-OUTBOX] Error en reintento automático id=%s error=%s",
                    rec.id, str(e),
                )

        return True

    @api.model
    def cron_recover_stale_processing(self):
        """
        Recupera mensajes queued/sending abandonados por una caída de n8n.

        queued:
            vuelve a pending cuando venció su lease.

        sending:
            se considera intento fallido si permanece demasiado tiempo sin
            ACK. El límite es configurable.
        """
        now = fields.Datetime.now()

        queued = self.search([
            ("state", "=", "queued"),
            ("next_retry_at", "!=", False),
            ("next_retry_at", "<=", now),
        ])

        for rec in queued:
            try:
                _logger.warning(
                    "[WA-OUTBOX] Lease queued vencido; recuperando | "
                    "id=%s queued_at=%s lease_until=%s",
                    rec.id,
                    rec.queued_at,
                    rec.next_retry_at,
                )

                rec.write({
                    "state": "pending",
                    "next_retry_at": False,
                })
            except Exception:
                _logger.exception(
                    "[WA-OUTBOX] Error recuperando queued | id=%s",
                    rec.id,
                )

        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "sat.whatsapp_outbox_sending_timeout_minutes",
                "10",
            )
        )

        try:
            sending_timeout = max(
                int(value),
                1,
            )
        except Exception:
            sending_timeout = 10

        cutoff = now - timedelta(
            minutes=sending_timeout
        )

        sending = self.search([
            ("state", "=", "sending"),
            ("sending_at", "!=", False),
            ("sending_at", "<=", cutoff),
        ])

        for rec in sending:
            try:
                rec.action_mark_failed(
                    error_message=(
                        "Tiempo de espera agotado sin ACK "
                        "de n8n/Baileys."
                    ),
                    error_code="SEND_ACK_TIMEOUT",
                    schedule_retry=True,
                )
            except Exception:
                _logger.exception(
                    "[WA-OUTBOX] Error recuperando sending | id=%s",
                    rec.id,
                )

        _logger.info(
            "[WA-OUTBOX] Recuperación de procesamiento | "
            "queued=%s sending=%s",
            len(queued),
            len(sending),
        )

        return True

    @api.model
    def cron_cleanup_old(self, days=30):
        """
        Cron de limpieza: elimina outbox enviados/cancelados antiguos.
        """
        try:
            days = int(days or 30)
        except Exception:
            days = 30

        cutoff = fields.Datetime.now() - timedelta(days=days)

        old_records = self.search([
            ("state", "in", ["sent", "delivered", "read", "cancelled"]),
            ("create_date", "<", cutoff),
        ])

        _logger.info(
            "[WA-OUTBOX] cron_cleanup_old: %s registros antiguos a eliminar (>%s días)",
            len(old_records), days,
        )

        try:
            old_records.unlink()
        except Exception as e:
            _logger.exception(
                "[WA-OUTBOX] Error eliminando outbox antiguos: %s", str(e),
            )

        return True