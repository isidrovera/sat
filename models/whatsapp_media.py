# -*- coding: utf-8 -*-

import base64
import json
import logging
import mimetypes
from urllib.parse import urlparse

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class WhatsappMedia(models.Model):
    _name = "whatsapp.media"
    _description = "Media WhatsApp"
    _order = "create_date desc, id desc"
    _rec_name = "display_name"

    # ==========================================================
    # Identificación y relaciones
    # ==========================================================
    name = fields.Char(
        string="Nombre",
        required=True,
        default="Media WhatsApp",
        index=True,
    )

    display_name = fields.Char(
        string="Nombre mostrado",
        compute="_compute_display_name",
        store=False,
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

    # ==========================================================
    # Clasificación
    # ==========================================================
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

    direction = fields.Selection(
        selection=[
            ("in", "Entrante"),
            ("out", "Saliente"),
        ],
        string="Dirección",
        default="in",
        index=True,
        help="Si el archivo lo envió el cliente (in) o el bot (out).",
    )

    purpose = fields.Selection(
        selection=[
            ("none", "Sin clasificar"),
            ("anydesk_code", "Código AnyDesk"),
            ("service_issue", "Problema servicio presencial"),
            ("toner_proof", "Evidencia tóner"),
            ("identification", "Documento identidad"),
            ("invoice", "Factura"),
            ("other", "Otro"),
        ],
        string="Propósito",
        default="none",
        index=True,
        help="Para qué se está usando este archivo en el flujo conversacional.",
    )

    # ==========================================================
    # Archivo
    # ==========================================================
    filename = fields.Char(string="Nombre archivo")
    mimetype = fields.Char(string="Mimetype")
    file_size = fields.Integer(string="Tamaño (bytes)")

    url = fields.Char(
        string="URL externa",
        help="URL enviada por Baileys/n8n si la media vive fuera de Odoo.",
    )

    attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="Adjunto Odoo",
        ondelete="set null",
    )

    external_media_id = fields.Char(string="ID externo", index=True)

    caption = fields.Text(string="Descripción")
    ai_summary = fields.Text(string="Resumen IA")

    # ==========================================================
    # Asociación con registros de negocio
    # ==========================================================
    related_model = fields.Char(
        string="Modelo relacionado",
        index=True,
        help="Modelo del registro de negocio al que se asoció esta media (ej. toner.counter.submission).",
    )

    related_res_id = fields.Integer(
        string="ID registro relacionado",
        index=True,
    )

    # ==========================================================
    # Procesamiento
    # ==========================================================
    raw_payload = fields.Text(
        string="Payload original (JSON)",
        default="{}",
    )

    is_processed = fields.Boolean(
        string="Procesado",
        default=False,
        index=True,
    )

    processed_at = fields.Datetime(string="Procesado en")

    process_error = fields.Text(string="Error procesamiento")

    requires_human_review = fields.Boolean(
        string="Requiere revisión humana",
        default=False,
        index=True,
        help="True si el archivo necesita revisión visual de un agente (ej. foto de código AnyDesk).",
    )

    review_status = fields.Selection(
        selection=[
            ("pending", "Pendiente"),
            ("reviewed", "Revisada"),
            ("rejected", "Rechazada"),
            ("not_required", "No requiere"),
        ],
        string="Estado revisión",
        default="not_required",
        index=True,
    )

    reviewed_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Revisada por",
    )

    reviewed_at = fields.Datetime(string="Revisada en")

    # ==========================================================
    # Computes
    # ==========================================================
    @api.depends("name", "media_type", "filename", "purpose")
    def _compute_display_name(self):
        purpose_dict = dict(self._fields["purpose"].selection)
        type_dict = dict(self._fields["media_type"].selection)
        for media in self:
            label_purpose = purpose_dict.get(media.purpose, "")
            label_type = type_dict.get(media.media_type, "")
            base = media.filename or media.name or "Media WhatsApp"
            if media.purpose and media.purpose != "none":
                media.display_name = "[%s] %s" % (label_purpose, base)
            else:
                media.display_name = "[%s] %s" % (label_type, base)

    # ==========================================================
    # Create
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
                        "[WA-MEDIA] No se pudo serializar raw_payload dict: %s", str(e),
                    )
                    vals["raw_payload"] = "{}"

            if not vals.get("mimetype") and vals.get("filename"):
                guessed, _enc = mimetypes.guess_type(vals["filename"])
                if guessed:
                    vals["mimetype"] = guessed

        records = super().create(vals_list)

        for media in records:
            _logger.info(
                "[WA-MEDIA] Media creada id=%s type=%s purpose=%s session=%s message=%s url=%s",
                media.id, media.media_type, media.purpose,
                media.session_id.id if media.session_id else False,
                media.message_id.id if media.message_id else False,
                media.url,
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
                "[WA-MEDIA] Error parseando raw_payload id=%s error=%s",
                self.id, str(e),
            )
            return {}

    def set_raw_payload(self, data):
        self.ensure_one()
        if not isinstance(data, dict):
            _logger.error(
                "[WA-MEDIA] set_raw_payload tipo inválido id=%s tipo=%s",
                self.id, type(data).__name__,
            )
            raise ValidationError(_("raw_payload debe ser un diccionario."))
        try:
            serialized = json.dumps(data, ensure_ascii=False, default=str)
        except Exception as e:
            _logger.exception(
                "[WA-MEDIA] Error serializando raw_payload id=%s error=%s",
                self.id, str(e),
            )
            raise ValidationError(_("No se pudo serializar raw_payload: %s") % str(e))
        self.write({"raw_payload": serialized})
        return True

    # ==========================================================
    # Descarga / conversión a attachment
    # ==========================================================
    def download_and_create_attachment(self):
        """
        Descarga el archivo desde la URL externa y lo guarda como ir.attachment.
        Se llama típicamente desde n8n después de recibir el archivo de Baileys.
        """
        self.ensure_one()

        if self.attachment_id:
            _logger.debug(
                "[WA-MEDIA] Media id=%s ya tiene attachment id=%s, omitiendo descarga",
                self.id, self.attachment_id.id,
            )
            return self.attachment_id

        if not self.url:
            _logger.warning(
                "[WA-MEDIA] download_and_create_attachment sin URL id=%s", self.id,
            )
            return False

        try:
            import requests
            _logger.info(
                "[WA-MEDIA] Descargando archivo id=%s url=%s", self.id, self.url,
            )
            response = requests.get(self.url, timeout=30)
            response.raise_for_status()

            content = response.content
            filename = self.filename or self._guess_filename_from_url()
            mimetype = self.mimetype or response.headers.get(
                "Content-Type", "application/octet-stream",
            )

            attachment = self.env["ir.attachment"].sudo().create({
                "name": filename or "whatsapp_media_%s" % self.id,
                "datas": base64.b64encode(content),
                "mimetype": mimetype,
                "res_model": "whatsapp.media",
                "res_id": self.id,
            })

            self.write({
                "attachment_id": attachment.id,
                "file_size": len(content),
                "filename": filename,
                "mimetype": mimetype,
                "is_processed": True,
                "processed_at": fields.Datetime.now(),
                "process_error": False,
            })

            _logger.info(
                "[WA-MEDIA] Archivo descargado id=%s attachment=%s size=%s",
                self.id, attachment.id, len(content),
            )

            return attachment

        except Exception as e:
            _logger.exception(
                "[WA-MEDIA] Error descargando archivo id=%s url=%s error=%s",
                self.id, self.url, str(e),
            )
            self.write({
                "is_processed": False,
                "process_error": str(e),
            })
            return False

    def _guess_filename_from_url(self):
        self.ensure_one()
        if not self.url:
            return False
        try:
            path = urlparse(self.url).path
            filename = path.rsplit("/", 1)[-1]
            return filename or False
        except Exception:
            return False

    # ==========================================================
    # Asociación con registro de negocio
    # ==========================================================
    def attach_to_record(self, model, res_id, purpose=False):
        """
        Asocia esta media a un registro de negocio (ticket, solicitud, handoff, etc.).
        Si tiene attachment, también lo re-vincula al registro destino.

        :param model: nombre del modelo (ej. 'toner.counter.submission')
        :param res_id: id del registro
        :param purpose: propósito opcional (anydesk_code, service_issue, etc.)
        """
        for media in self:
            vals = {
                "related_model": model,
                "related_res_id": res_id,
            }
            if purpose:
                valid_purposes = dict(media._fields["purpose"].selection)
                if purpose in valid_purposes:
                    vals["purpose"] = purpose
                else:
                    _logger.warning(
                        "[WA-MEDIA] purpose inválido id=%s purpose=%s",
                        media.id, purpose,
                    )

            _logger.info(
                "[WA-MEDIA] Asociando media id=%s a %s,%s purpose=%s",
                media.id, model, res_id, purpose,
            )

            media.write(vals)

            # Re-vincular el attachment si existe
            if media.attachment_id:
                try:
                    media.attachment_id.sudo().write({
                        "res_model": model,
                        "res_id": res_id,
                    })
                    _logger.debug(
                        "[WA-MEDIA] Attachment id=%s re-vinculado a %s,%s",
                        media.attachment_id.id, model, res_id,
                    )
                except Exception as e:
                    _logger.exception(
                        "[WA-MEDIA] Error re-vinculando attachment media_id=%s error=%s",
                        media.id, str(e),
                    )

        return True

    # ==========================================================
    # Revisión humana
    # ==========================================================
    def mark_for_human_review(self, reason=False):
        """Marca esta media para que un agente la revise."""
        for media in self:
            _logger.info(
                "[WA-MEDIA] Marcando para revisión humana id=%s reason=%s",
                media.id, reason,
            )
            media.write({
                "requires_human_review": True,
                "review_status": "pending",
            })
            if reason:
                media.write({"process_error": reason})
        return True

    def action_mark_reviewed(self):
        """Marca como revisada por el usuario actual."""
        for media in self:
            _logger.info(
                "[WA-MEDIA] Media revisada id=%s user=%s",
                media.id, self.env.user.id,
            )
            media.write({
                "review_status": "reviewed",
                "reviewed_by_id": self.env.user.id,
                "reviewed_at": fields.Datetime.now(),
            })
        return True

    def action_mark_rejected(self):
        """Marca como rechazada por el usuario actual."""
        for media in self:
            _logger.info(
                "[WA-MEDIA] Media rechazada id=%s user=%s",
                media.id, self.env.user.id,
            )
            media.write({
                "review_status": "rejected",
                "reviewed_by_id": self.env.user.id,
                "reviewed_at": fields.Datetime.now(),
            })
        return True

    # ==========================================================
    # Procesamiento
    # ==========================================================
    def mark_processed(self, ai_summary=False):
        """Marca como procesado, opcionalmente con resumen IA."""
        for media in self:
            vals = {
                "is_processed": True,
                "processed_at": fields.Datetime.now(),
                "process_error": False,
            }
            if ai_summary:
                vals["ai_summary"] = ai_summary
            _logger.info(
                "[WA-MEDIA] Media procesada id=%s ai_summary=%s",
                media.id, bool(ai_summary),
            )
            media.write(vals)
        return True

    def mark_process_error(self, error_message):
        """Marca como fallido en procesamiento."""
        for media in self:
            _logger.warning(
                "[WA-MEDIA] Error procesando media id=%s error=%s",
                media.id, error_message,
            )
            media.write({
                "is_processed": False,
                "process_error": error_message or "",
            })
        return True