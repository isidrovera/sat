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
    """
    Evidencias y archivos intercambiados por WhatsApp.

    Responsabilidades:
    - conservar el payload original;
    - registrar URL/ID externo;
    - descargar el archivo a ir.attachment cuando sea necesario;
    - asociarlo a tickets, solicitudes o handoffs;
    - controlar revisión humana y estado de procesamiento.

    Esta versión mantiene el modelo y sus flujos existentes, añadiendo
    validaciones defensivas, límites configurables y logs más precisos.
    """

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

    review_note = fields.Text(
        string="Motivo / nota de revisión",
        help=(
            "Motivo por el que la evidencia requiere revisión humana. "
            "Se mantiene separado de process_error para no confundir "
            "una revisión visual con un fallo técnico."
        ),
    )

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
    def _get_download_timeout_seconds(self):
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "sat.whatsapp_media_download_timeout_seconds",
                "30",
            )
        )

        try:
            timeout = int(value)
        except Exception:
            timeout = 30

        return max(
            5,
            min(timeout, 120),
        )

    def _get_max_download_bytes(self):
        """
        Límite defensivo de descarga.

        25 MB por defecto; configurable en ir.config_parameter.
        Un valor <= 0 desactiva el límite.
        """
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "sat.whatsapp_media_max_download_mb",
                "25",
            )
        )

        try:
            max_mb = float(value)
        except Exception:
            max_mb = 25.0

        if max_mb <= 0:
            return False

        return int(
            max_mb * 1024 * 1024
        )

    def _normalize_response_mimetype(
        self,
        response=False,
    ):
        self.ensure_one()

        mimetype = (
            self.mimetype
            or (
                response.headers.get("Content-Type")
                if response
                else False
            )
            or "application/octet-stream"
        )

        return (
            str(mimetype)
            .split(";", 1)[0]
            .strip()
            or "application/octet-stream"
        )

    def download_and_create_attachment(self):
        """
        Descarga la URL externa y crea un ir.attachment.

        La operación es idempotente: si attachment_id ya existe, no vuelve
        a descargar el archivo.
        """
        self.ensure_one()

        if self.attachment_id:
            _logger.debug(
                "[WA-MEDIA] Descarga omitida; attachment existente | "
                "media_id=%s attachment_id=%s",
                self.id,
                self.attachment_id.id,
            )
            return self.attachment_id

        if not self.url:
            message = (
                "La media no tiene URL externa disponible."
            )

            _logger.warning(
                "[WA-MEDIA] Descarga sin URL | media_id=%s",
                self.id,
            )

            self.write({
                "is_processed": False,
                "process_error": message,
            })
            return False

        try:
            import requests

            timeout = (
                self._get_download_timeout_seconds()
            )
            max_bytes = (
                self._get_max_download_bytes()
            )

            _logger.info(
                "[WA-MEDIA] Iniciando descarga | "
                "media_id=%s type=%s timeout=%ss max_bytes=%s url=%s",
                self.id,
                self.media_type,
                timeout,
                max_bytes or False,
                self.url,
            )

            response = requests.get(
                self.url,
                timeout=timeout,
                stream=True,
                allow_redirects=True,
            )
            response.raise_for_status()

            content_length = (
                response.headers.get(
                    "Content-Length"
                )
                or False
            )

            if (
                max_bytes
                and content_length
            ):
                try:
                    if int(content_length) > max_bytes:
                        raise ValidationError(
                            _(
                                "El archivo supera el tamaño máximo "
                                "permitido para WhatsApp."
                            )
                        )
                except ValueError:
                    pass

            chunks = []
            total_size = 0

            for chunk in response.iter_content(
                chunk_size=64 * 1024
            ):
                if not chunk:
                    continue

                total_size += len(chunk)

                if (
                    max_bytes
                    and total_size > max_bytes
                ):
                    raise ValidationError(
                        _(
                            "El archivo supera el tamaño máximo "
                            "permitido para WhatsApp."
                        )
                    )

                chunks.append(chunk)

            content = b"".join(
                chunks
            )

            if not content:
                raise ValidationError(
                    _(
                        "La descarga no devolvió contenido."
                    )
                )

            filename = (
                self.filename
                or self._guess_filename_from_url()
                or "whatsapp_media_%s" % self.id
            )

            mimetype = (
                self._normalize_response_mimetype(
                    response
                )
            )

            attachment = (
                self.env["ir.attachment"]
                .sudo()
                .create({
                    "name": filename,
                    "datas": base64.b64encode(
                        content
                    ),
                    "mimetype": mimetype,
                    "res_model": "whatsapp.media",
                    "res_id": self.id,
                })
            )

            now = fields.Datetime.now()

            self.write({
                "attachment_id": attachment.id,
                "file_size": total_size,
                "filename": filename,
                "mimetype": mimetype,
                "is_processed": True,
                "processed_at": now,
                "process_error": False,
            })

            _logger.info(
                "[WA-MEDIA] Descarga completada | "
                "media_id=%s attachment_id=%s size=%s "
                "mimetype=%s filename=%s",
                self.id,
                attachment.id,
                total_size,
                mimetype,
                filename,
            )

            return attachment

        except Exception as exc:
            error_message = str(
                exc
            )

            _logger.exception(
                "[WA-MEDIA] Error descargando | "
                "media_id=%s url=%s error=%s",
                self.id,
                self.url,
                error_message,
            )

            self.write({
                "is_processed": False,
                "processed_at": False,
                "process_error": error_message,
            })

            return False

    def _guess_filename_from_url(self):
        self.ensure_one()

        if not self.url:
            return False

        try:
            from urllib.parse import unquote

            path = (
                urlparse(
                    self.url
                ).path
                or ""
            )

            filename = (
                path.rsplit("/", 1)[-1]
                or ""
            )

            filename = (
                unquote(filename)
                .strip()
            )

            return (
                filename
                or False
            )

        except Exception:
            _logger.exception(
                "[WA-MEDIA] Error obteniendo filename desde URL | "
                "media_id=%s url=%s",
                self.id,
                self.url,
            )
            return False

    # ==========================================================
    # Asociación con registro de negocio
    # ==========================================================
    def attach_to_record(
        self,
        model,
        res_id,
        purpose=False,
    ):
        """
        Asocia la media y, si existe, su ir.attachment al registro destino.
        """
        if not model:
            raise ValidationError(
                _("El modelo relacionado es obligatorio.")
            )

        try:
            res_id = int(
                res_id
            )
        except Exception:
            raise ValidationError(
                _("El ID del registro relacionado no es válido.")
            )

        if res_id <= 0:
            raise ValidationError(
                _("El ID del registro relacionado no es válido.")
            )

        if model not in self.env:
            raise ValidationError(
                _(
                    "El modelo relacionado no existe: %s"
                )
                % model
            )

        target = (
            self.env[model]
            .sudo()
            .browse(res_id)
            .exists()
        )

        if not target:
            raise ValidationError(
                _(
                    "El registro relacionado %s,%s no existe."
                )
                % (
                    model,
                    res_id,
                )
            )

        for media in self:
            vals = {
                "related_model": model,
                "related_res_id": res_id,
            }

            if purpose:
                valid_purposes = dict(
                    media._fields[
                        "purpose"
                    ].selection
                )

                if purpose in valid_purposes:
                    vals["purpose"] = purpose
                else:
                    _logger.warning(
                        "[WA-MEDIA] Purpose no válido; se conserva actual | "
                        "media_id=%s purpose=%s",
                        media.id,
                        purpose,
                    )

            media.write(
                vals
            )

            if media.attachment_id:
                try:
                    media.attachment_id.sudo().write({
                        "res_model": model,
                        "res_id": res_id,
                    })
                except Exception:
                    _logger.exception(
                        "[WA-MEDIA] Error vinculando attachment | "
                        "media_id=%s attachment_id=%s target=%s,%s",
                        media.id,
                        media.attachment_id.id,
                        model,
                        res_id,
                    )
                    raise

            _logger.info(
                "[WA-MEDIA] Media asociada | "
                "media_id=%s attachment_id=%s target=%s,%s purpose=%s",
                media.id,
                (
                    media.attachment_id.id
                    if media.attachment_id
                    else False
                ),
                model,
                res_id,
                vals.get("purpose")
                or media.purpose,
            )

        return True

    # ==========================================================
    # Revisión humana
    # ==========================================================
    def mark_for_human_review(self, reason=False):
        """
        Marca la evidencia para revisión humana.

        El motivo se guarda en review_note y no en process_error, porque
        solicitar revisión visual no representa un fallo de procesamiento.
        """
        for media in self:
            vals = {
                "requires_human_review": True,
                "review_status": "pending",
                "reviewed_by_id": False,
                "reviewed_at": False,
            }

            if reason:
                vals["review_note"] = reason

            media.write(
                vals
            )

            _logger.info(
                "[WA-MEDIA] Revisión humana solicitada | "
                "media_id=%s reason=%s",
                media.id,
                reason or False,
            )

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
                "[WA-MEDIA] Procesamiento completado | "
                "media_id=%s attachment_id=%s ai_summary=%s",
                media.id,
                media.attachment_id.id if media.attachment_id else False,
                bool(ai_summary),
            )
            media.write(vals)
        return True

    def mark_process_error(self, error_message):
        """Marca como fallido en procesamiento."""
        for media in self:
            _logger.warning(
                "[WA-MEDIA] Procesamiento fallido | "
                "media_id=%s attachment_id=%s error=%s",
                media.id,
                media.attachment_id.id if media.attachment_id else False,
                error_message,
            )
            media.write({
                "is_processed": False,
                "process_error": error_message or "",
            })
        return True