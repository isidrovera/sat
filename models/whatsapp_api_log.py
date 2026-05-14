# -*- coding: utf-8 -*-

from odoo import fields, models


class WhatsappApiLog(models.Model):
    _name = "whatsapp.api.log"
    _description = "Log API WhatsApp"
    _order = "request_date desc, id desc"

    name = fields.Char(
        string="Referencia",
        default="API WhatsApp",
        required=True,
        index=True,
    )

    endpoint = fields.Char(
        string="Endpoint",
        index=True,
    )

    method = fields.Char(
        string="Método HTTP",
        default="POST",
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

    raw_jid = fields.Char(
        string="Raw JID",
    )

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contacto",
        index=True,
        ondelete="set null",
    )

    session_id = fields.Many2one(
        comodel_name="whatsapp.session",
        string="Sesión",
        index=True,
        ondelete="set null",
    )

    request_payload = fields.Json(
        string="Payload recibido",
    )

    response_payload = fields.Json(
        string="Respuesta enviada",
    )

    status = fields.Selection(
        selection=[
            ("success", "Correcto"),
            ("error", "Error"),
            ("unauthorized", "No autorizado"),
            ("not_found", "No encontrado"),
        ],
        string="Estado",
        default="success",
        index=True,
    )

    error_code = fields.Char(
        string="Código error",
        index=True,
    )

    error_message = fields.Text(
        string="Mensaje error",
    )

    duration_ms = fields.Integer(
        string="Duración ms",
    )

    request_date = fields.Datetime(
        string="Fecha solicitud",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    source = fields.Selection(
        selection=[
            ("baileys", "Baileys"),
            ("n8n", "n8n"),
            ("manual", "Manual"),
            ("api", "API"),
        ],
        string="Origen",
        default="api",
        index=True,
    )