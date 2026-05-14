# -*- coding: utf-8 -*-

from odoo import fields, models


class WhatsappMessage(models.Model):
    _name = "whatsapp.message"
    _description = "Mensaje WhatsApp"
    _order = "message_date asc, id asc"

    session_id = fields.Many2one(
        comodel_name="whatsapp.session",
        string="Sesión",
        required=True,
        index=True,
        ondelete="cascade",
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

    role = fields.Selection(
        selection=[
            ("user", "Cliente"),
            ("assistant", "Bot"),
            ("human", "Humano"),
            ("system", "Sistema"),
        ],
        string="Rol",
        required=True,
        default="user",
        index=True,
    )

    direction = fields.Selection(
        selection=[
            ("in", "Entrante"),
            ("out", "Saliente"),
        ],
        string="Dirección",
        required=True,
        default="in",
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
        index=True,
    )

    content = fields.Text(
        string="Contenido",
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

    external_message_id = fields.Char(
        string="ID mensaje externo",
        index=True,
        help="ID del mensaje de Baileys/WhatsApp/n8n para evitar duplicados.",
    )

    intent = fields.Char(
        string="Intención",
        index=True,
    )

    media_url = fields.Char(
        string="URL de media",
    )

    media_mimetype = fields.Char(
        string="Mimetype",
    )

    raw_payload = fields.Json(
        string="Payload original",
    )

    message_date = fields.Datetime(
        string="Fecha mensaje",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    is_error = fields.Boolean(
        string="Con error",
        default=False,
    )

    error_message = fields.Text(
        string="Mensaje de error",
    )