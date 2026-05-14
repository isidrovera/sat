# -*- coding: utf-8 -*-

from odoo import fields, models


class WhatsappMedia(models.Model):
    _name = "whatsapp.media"
    _description = "Media WhatsApp"
    _order = "create_date desc, id desc"

    name = fields.Char(
        string="Nombre",
        required=True,
        default="Media WhatsApp",
        index=True,
    )

    message_id = fields.Many2one(
        comodel_name="whatsapp.message",
        string="Mensaje",
        index=True,
        ondelete="cascade",
    )

    session_id = fields.Many2one(
        comodel_name="whatsapp.session",
        string="Sesión",
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

    media_type = fields.Selection(
        selection=[
            ("image", "Imagen"),
            ("audio", "Audio"),
            ("video", "Video"),
            ("document", "Documento"),
            ("location", "Ubicación"),
            ("contact", "Contacto"),
            ("other", "Otro"),
        ],
        string="Tipo",
        default="other",
        required=True,
        index=True,
    )

    filename = fields.Char(
        string="Nombre archivo",
    )

    mimetype = fields.Char(
        string="Mimetype",
    )

    url = fields.Char(
        string="URL externa",
        help="URL enviada por Baileys/n8n si la media vive fuera de Odoo.",
    )

    attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="Adjunto Odoo",
        ondelete="set null",
    )

    external_media_id = fields.Char(
        string="ID externo",
        index=True,
    )

    caption = fields.Text(
        string="Descripción",
    )

    ai_summary = fields.Text(
        string="Resumen IA",
    )

    raw_payload = fields.Json(
        string="Payload original",
    )

    is_processed = fields.Boolean(
        string="Procesado",
        default=False,
        index=True,
    )

    process_error = fields.Text(
        string="Error procesamiento",
    )