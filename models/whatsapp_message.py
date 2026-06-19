# -*- coding: utf-8 -*-

import json
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class WhatsappMessage(models.Model):
    _name = "whatsapp.message"
    _description = "Mensaje WhatsApp"
    _order = "message_date asc, id asc"
    _rec_name = "display_name"

    # ==========================================================
    # Relaciones
    # ==========================================================
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

    media_ids = fields.One2many(
        comodel_name="whatsapp.media",
        inverse_name="message_id",
        string="Archivos adjuntos",
    )

    media_count = fields.Integer(
        string="Cantidad de adjuntos",
        compute="_compute_media_count",
        store=False,
    )

    # ==========================================================
    # Clasificación del mensaje
    # ==========================================================
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

    content = fields.Text(string="Contenido")

    # ==========================================================
    # Identificadores
    # ==========================================================
    phone = fields.Char(string="Teléfono", index=True)
    jid = fields.Char(string="JID", index=True)
    lid = fields.Char(string="LID", index=True)
    raw_jid = fields.Char(string="Raw JID")

    external_message_id = fields.Char(
        string="ID mensaje externo",
        index=True,
        help="ID del mensaje de Baileys/WhatsApp/n8n para evitar duplicados.",
    )

    # ==========================================================
    # Intención y flujo
    # ==========================================================
    intent = fields.Char(string="Intención", index=True)

    confidence_score = fields.Float(
        string="Confianza intención",
        digits=(3, 2),
        help="Score de confianza de la detección de intención (0.00 a 1.00).",
    )

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
        help="Flujo conversacional activo al generarse este mensaje (snapshot).",
    )

    flow_step = fields.Char(
        string="Paso del flujo",
        index=True,
        help="Conversation_state activo cuando se generó este mensaje (ej. awaiting_toner_color).",
    )

    is_menu_response = fields.Boolean(
        string="Respuesta a menú",
        default=False,
        help="True si el mensaje del cliente fue respuesta a un menú numerado.",
    )

    menu_option_selected = fields.Char(
        string="Opción de menú elegida",
        help="Snapshot textual de la opción del menú seleccionada por el cliente.",
    )

    template_used = fields.Char(
        string="Plantilla usada",
        index=True,
        help="Nombre de la plantilla whatsapp.template empleada para generar este mensaje saliente.",
    )

    from_human_agent_name = fields.Char(
        string="Agente humano",
        help="Nombre del agente que escribió este mensaje saliente (cuando role=human).",
    )

    # ==========================================================
    # Media / payload
    # ==========================================================
    media_url = fields.Char(string="URL de media")
    media_mimetype = fields.Char(string="Mimetype")

    raw_payload = fields.Text(
        string="Payload original (JSON)",
        default="{}",
        help="Payload completo del webhook/API que originó el mensaje.",
    )

    # ==========================================================
    # Fechas y procesamiento
    # ==========================================================
    message_date = fields.Datetime(
        string="Fecha mensaje",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    processing_status = fields.Selection(
        selection=[
            ("received", "Recibido"),
            ("processing", "Procesando"),
            ("processed", "Procesado"),
            ("failed", "Fallido"),
            ("ignored", "Ignorado"),
        ],
        string="Procesamiento",
        default="received",
        required=True,
        index=True,
    )

    processed_at = fields.Datetime(
        string="Procesado en",
        index=True,
        help="Cuándo terminó el bot de procesar este mensaje.",
    )

    is_error = fields.Boolean(string="Con error", default=False)
    error_message = fields.Text(string="Mensaje de error")

    # ==========================================================
    # Display
    # ==========================================================
    display_name = fields.Char(
        string="Nombre",
        compute="_compute_display_name",
        store=False,
    )

    # ==========================================================
    # SQL constraints / índices
    # ==========================================================
    _sql_constraints = [
        (
            "uniq_external_message_session",
            "UNIQUE(session_id, external_message_id)",
            "Ya existe un mensaje con este external_message_id en la sesión (idempotencia).",
        ),
    ]

    def init(self):
        """Crear índice compuesto para acelerar búsqueda de duplicados."""
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS whatsapp_message_external_session_idx
            ON whatsapp_message (external_message_id, session_id)
            WHERE external_message_id IS NOT NULL
        """)

    # ==========================================================
    # Computes
    # ==========================================================
    @api.depends("media_ids")
    def _compute_media_count(self):
        for msg in self:
            msg.media_count = len(msg.media_ids)

    @api.depends("role", "direction", "content", "message_type")
    def _compute_display_name(self):
        role_dict = dict(self._fields["role"].selection)
        for msg in self:
            role_label = role_dict.get(msg.role, msg.role or "")
            arrow = "→" if msg.direction == "out" else "←"
            preview = (msg.content or "").strip().replace("\n", " ")
            if len(preview) > 60:
                preview = preview[:60] + "…"
            if not preview and msg.message_type != "text":
                preview = "[%s]" % msg.message_type
            msg.display_name = "%s %s %s" % (role_label, arrow, preview or "(vacío)")

   
    # ==========================================================
    # Create
    # ==========================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("raw_payload"):
                vals["raw_payload"] = "{}"

            # Si raw_payload viene como dict (legacy), serializarlo
            if isinstance(vals.get("raw_payload"), dict):
                try:
                    vals["raw_payload"] = json.dumps(
                        vals["raw_payload"],
                        ensure_ascii=False,
                        default=str,
                    )
                except Exception as e:
                    _logger.error(
                        "[WA-MESSAGE] No se pudo serializar raw_payload dict: %s",
                        str(e),
                    )
                    vals["raw_payload"] = "{}"

        messages = super().create(vals_list)

        for msg in messages:
            _logger.info(
                "[WA-MESSAGE] Mensaje creado id=%s session=%s direction=%s role=%s type=%s intent=%s flow=%s step=%s",
                msg.id,
                msg.session_id.id if msg.session_id else False,
                msg.direction,
                msg.role,
                msg.message_type,
                msg.intent,
                msg.current_flow,
                msg.flow_step,
            )

            # --------------------------------------------------
            # Actualizar actividad de sesión
            # --------------------------------------------------
            # Esto es clave para liberar modo humano 60 minutos
            # después de la última actividad real.
            try:
                if msg.session_id:
                    touch_vals = {}

                    if msg.intent:
                        touch_vals["intent"] = msg.intent

                    if msg.direction == "in" and msg.role == "user":
                        touch_vals["user_message"] = msg.content or False

                    elif msg.direction == "out":
                        touch_vals["bot_message"] = msg.content or False

                    msg.session_id.sudo().touch(**touch_vals)

            except Exception:
                _logger.exception(
                    "[WA-MESSAGE] No se pudo actualizar actividad de sesión message=%s session=%s",
                    msg.id,
                    msg.session_id.id if msg.session_id else False,
                )

        return messages

    # ==========================================================
    # Helpers raw_payload
    # ==========================================================
    def get_raw_payload(self):
        """Devuelve raw_payload como dict."""
        self.ensure_one()
        if not self.raw_payload:
            return {}
        try:
            return json.loads(self.raw_payload)
        except Exception as e:
            _logger.error(
                "[WA-MESSAGE] Error parseando raw_payload id=%s error=%s",
                self.id, str(e),
            )
            return {}

    def set_raw_payload(self, data):
        """Guarda dict como JSON en raw_payload."""
        self.ensure_one()
        if not isinstance(data, dict):
            _logger.error(
                "[WA-MESSAGE] set_raw_payload tipo inválido id=%s tipo=%s",
                self.id, type(data).__name__,
            )
            raise ValidationError(_("raw_payload debe ser un diccionario."))
        try:
            serialized = json.dumps(data, ensure_ascii=False, default=str)
        except Exception as e:
            _logger.exception(
                "[WA-MESSAGE] Error serializando raw_payload id=%s error=%s",
                self.id, str(e),
            )
            raise ValidationError(_("No se pudo serializar raw_payload: %s") % str(e))
        self.write({"raw_payload": serialized})
        return True

    # ==========================================================
    # Métodos de procesamiento
    # ==========================================================
    def mark_processing(self):
        """Marca el mensaje como en procesamiento."""
        for msg in self:
            _logger.debug(
                "[WA-MESSAGE] Marcando como procesando id=%s", msg.id,
            )
            msg.write({"processing_status": "processing"})
        return True

    def mark_processed(self, intent=False, flow_step=False, current_flow=False, confidence_score=False):
        """
        Marca el mensaje como procesado correctamente.

        :param intent: si se detectó intent, guardarlo
        :param flow_step: paso del flujo al momento de procesarlo
        :param current_flow: flujo activo al procesarlo
        :param confidence_score: score de confianza de la detección
        """
        for msg in self:
            vals = {
                "processing_status": "processed",
                "processed_at": fields.Datetime.now(),
            }
            if intent:
                vals["intent"] = intent
            if flow_step:
                vals["flow_step"] = flow_step
            if current_flow:
                vals["current_flow"] = current_flow
            if confidence_score is not False and confidence_score is not None:
                vals["confidence_score"] = confidence_score

            _logger.info(
                "[WA-MESSAGE] Mensaje procesado id=%s intent=%s flow=%s step=%s score=%s",
                msg.id, intent, current_flow, flow_step, confidence_score,
            )
            msg.write(vals)
        return True

    def mark_failed(self, error_message=False):
        """Marca el mensaje como fallido."""
        for msg in self:
            _logger.warning(
                "[WA-MESSAGE] Mensaje fallido id=%s error=%s",
                msg.id, error_message,
            )
            msg.write({
                "processing_status": "failed",
                "processed_at": fields.Datetime.now(),
                "is_error": True,
                "error_message": error_message or "",
            })
        return True

    def mark_ignored(self, reason=False):
        """Marca el mensaje como ignorado (duplicado, sin partner, etc.)."""
        for msg in self:
            _logger.info(
                "[WA-MESSAGE] Mensaje ignorado id=%s reason=%s",
                msg.id, reason,
            )
            msg.write({
                "processing_status": "ignored",
                "processed_at": fields.Datetime.now(),
                "error_message": reason or "",
            })
        return True

    # ==========================================================
    # Idempotencia
    # ==========================================================
    @api.model
    def find_duplicate(self, external_message_id, session_id=False):
        """
        Busca un mensaje duplicado por external_message_id.
        Si session_id se provee, restringe la búsqueda a esa sesión.

        :return: recordset (vacío si no hay duplicado)
        """
        if not external_message_id:
            return self.browse()

        domain = [("external_message_id", "=", external_message_id)]
        if session_id:
            domain.append(("session_id", "=", session_id))

        existing = self.search(domain, limit=1)

        if existing:
            _logger.info(
                "[WA-MESSAGE] Duplicado detectado external_id=%s session=%s existing_id=%s",
                external_message_id, session_id, existing.id,
            )

        return existing

    # ==========================================================
    # Helpers de menú
    # ==========================================================
    def mark_as_menu_response(self, option_selected):
        """
        Marca este mensaje del cliente como respuesta a un menú numerado.

        :param option_selected: texto de la opción elegida (ej. "1. MP 4054 - S/N XXX")
        """
        for msg in self:
            _logger.debug(
                "[WA-MESSAGE] Marcando como respuesta de menú id=%s option=%r",
                msg.id, option_selected,
            )
            msg.write({
                "is_menu_response": True,
                "menu_option_selected": option_selected or "",
            })
        return True