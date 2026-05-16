# -*- coding: utf-8 -*-

import json
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class WhatsappOutbox(models.Model):
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
    # Acciones de estado
    # ==========================================================
    def action_mark_queued(self):
        """Marca como en cola, listo para que n8n lo recoja."""
        for rec in self:
            if rec.state not in ("pending", "failed"):
                _logger.warning(
                    "[WA-OUTBOX] mark_queued estado inválido id=%s state=%s",
                    rec.id, rec.state,
                )
                continue
            _logger.info(
                "[WA-OUTBOX] Marcando como en cola id=%s", rec.id,
            )
            rec.write({
                "state": "queued",
                "queued_at": fields.Datetime.now(),
            })
        return True

    def action_mark_sending(self):
        """Marca como en proceso de envío (n8n lo está procesando)."""
        for rec in self:
            _logger.info(
                "[WA-OUTBOX] Marcando como enviando id=%s", rec.id,
            )
            rec.write({
                "state": "sending",
                "sending_at": fields.Datetime.now(),
            })
        return True

    def action_mark_sent(self, external_message_id=False):
        """Marca como enviado. Confirma envío exitoso desde Baileys."""
        for rec in self:
            vals = {
                "state": "sent",
                "sent_at": fields.Datetime.now(),
                "error_message": False,
                "error_code": False,
            }
            if external_message_id:
                vals["external_message_id"] = external_message_id

            _logger.info(
                "[WA-OUTBOX] Marcando como enviado id=%s external_id=%s",
                rec.id, external_message_id,
            )
            rec.write(vals)

            # Propagar al mensaje relacionado si existe
            if rec.message_id and external_message_id:
                try:
                    rec.message_id.sudo().write({
                        "external_message_id": external_message_id,
                    })
                except Exception as e:
                    _logger.warning(
                        "[WA-OUTBOX] No se pudo propagar external_id al mensaje id=%s error=%s",
                        rec.id, str(e),
                    )
        return True

    def action_mark_delivered(self):
        """Marca como entregado al dispositivo del destinatario."""
        for rec in self:
            _logger.info(
                "[WA-OUTBOX] Marcando como entregado id=%s", rec.id,
            )
            rec.write({
                "state": "delivered",
                "delivered_at": fields.Datetime.now(),
            })
        return True

    def action_mark_read(self):
        """Marca como leído por el destinatario."""
        for rec in self:
            _logger.info(
                "[WA-OUTBOX] Marcando como leído id=%s", rec.id,
            )
            rec.write({
                "state": "read",
                "read_at": fields.Datetime.now(),
            })
        return True

    def action_mark_failed(self, error_message=False, error_code=False, schedule_retry=True):
        """
        Marca como fallido. Si schedule_retry y aún hay reintentos, programa próximo intento
        con backoff exponencial.
        """
        for rec in self:
            new_retry_count = rec.retry_count + 1
            vals = {
                "state": "failed",
                "retry_count": new_retry_count,
                "last_retry_at": fields.Datetime.now(),
                "error_message": error_message or "Error enviando mensaje WhatsApp",
                "error_code": error_code or False,
            }

            # Backoff exponencial: 1min, 5min, 15min...
            if schedule_retry and new_retry_count < rec.max_retries:
                backoff_minutes = 5 ** new_retry_count
                if backoff_minutes < 1:
                    backoff_minutes = 1
                if backoff_minutes > 120:
                    backoff_minutes = 120
                vals["next_retry_at"] = fields.Datetime.now() + timedelta(minutes=backoff_minutes)

                _logger.warning(
                    "[WA-OUTBOX] Mensaje fallido id=%s retry=%s/%s next_retry=%s error=%s",
                    rec.id, new_retry_count, rec.max_retries,
                    vals["next_retry_at"], error_message,
                )
            else:
                _logger.error(
                    "[WA-OUTBOX] Mensaje fallido sin más reintentos id=%s retry=%s/%s error=%s",
                    rec.id, new_retry_count, rec.max_retries, error_message,
                )

            rec.write(vals)
        return True

    def action_cancel(self, reason=False):
        """Cancela el mensaje. No se reintentará."""
        for rec in self:
            _logger.info(
                "[WA-OUTBOX] Cancelando id=%s reason=%s",
                rec.id, reason,
            )
            rec.write({
                "state": "cancelled",
                "error_message": reason or "Cancelado manualmente",
            })
        return True

    def action_retry(self):
        """Forzar reintento manual. Resetea state a pending."""
        for rec in self:
            if not rec.can_retry and rec.state != "cancelled":
                raise UserError(_("Este mensaje no puede reintentarse: estado=%s reintentos=%s/%s") % (
                    rec.state, rec.retry_count, rec.max_retries,
                ))
            _logger.info(
                "[WA-OUTBOX] Reintento manual id=%s estado_previo=%s",
                rec.id, rec.state,
            )
            rec.write({
                "state": "pending",
                "next_retry_at": False,
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
            })
        return True

    # ==========================================================
    # Consulta para n8n
    # ==========================================================
    @api.model
    def get_pending_payload(self, limit=20, partner_id=False):
        """
        Devuelve mensajes listos para enviar, en formato listo para n8n.

        :param limit: máximo de mensajes a devolver
        :param partner_id: opcional, filtrar por contacto
        :return: lista de dicts
        """
        try:
            limit = int(limit or 20)
        except Exception:
            limit = 20

        if limit > 100:
            limit = 100

        domain = [("is_ready_to_send", "=", True)]
        if partner_id:
            domain.append(("partner_id", "=", partner_id))

        outbox_records = self.search(
            domain,
            order="priority desc, scheduled_at asc, id asc",
            limit=limit,
        )

        _logger.info(
            "[WA-OUTBOX] get_pending_payload limit=%s partner=%s found=%s",
            limit, partner_id, len(outbox_records),
        )

        items = []
        for rec in outbox_records:
            items.append(rec.to_n8n_payload())

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
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else False,
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
            ("retry_count", "<", 3),
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