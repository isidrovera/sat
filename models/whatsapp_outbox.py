# -*- coding: utf-8 -*-

from odoo import fields, models


class WhatsappOutbox(models.Model):
    _name = "whatsapp.outbox"
    _description = "Cola de salida WhatsApp"
    _order = "scheduled_at asc, create_date asc"

    name = fields.Char(
        string="Referencia",
        default="Mensaje WhatsApp",
        required=True,
        index=True,
    )

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

    phone = fields.Char(
        string="Teléfono",
        index=True,
    )

    jid = fields.Char(
        string="JID",
        index=True,
    )

    lid = fields.Char(
        string="LID",
        index=True,
    )

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

    content = fields.Text(
        string="Contenido",
    )

    media_id = fields.Many2one(
        comodel_name="whatsapp.media",
        string="Media",
        ondelete="set null",
    )

    state = fields.Selection(
        selection=[
            ("pending", "Pendiente"),
            ("sent", "Enviado"),
            ("failed", "Fallido"),
            ("cancelled", "Cancelado"),
        ],
        string="Estado",
        default="pending",
        required=True,
        index=True,
    )

    scheduled_at = fields.Datetime(
        string="Programado para",
        default=fields.Datetime.now,
        index=True,
    )

    sent_at = fields.Datetime(
        string="Enviado el",
        index=True,
    )

    external_message_id = fields.Char(
        string="ID mensaje externo",
        index=True,
    )

    retry_count = fields.Integer(
        string="Reintentos",
        default=0,
    )

    max_retries = fields.Integer(
        string="Máximo reintentos",
        default=3,
    )

    error_message = fields.Text(
        string="Error",
    )

    raw_payload = fields.Json(
        string="Payload",
    )

    def action_mark_sent(self, external_message_id=False):
        for rec in self:
            vals = {
                "state": "sent",
                "sent_at": fields.Datetime.now(),
                "error_message": False,
            }
            if external_message_id:
                vals["external_message_id"] = external_message_id
            rec.write(vals)

    def action_mark_failed(self, error_message=False):
        for rec in self:
            rec.write({
                "state": "failed",
                "retry_count": rec.retry_count + 1,
                "error_message": error_message or "Error enviando mensaje WhatsApp",
            })

    def action_cancel(self):
        for rec in self:
            rec.write({
                "state": "cancelled",
            })