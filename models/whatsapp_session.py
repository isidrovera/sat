# -*- coding: utf-8 -*-

import json
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class WhatsappSession(models.Model):
    _name = "whatsapp.session"
    _description = "Sesión WhatsApp"
    _order = "last_message_at desc, create_date desc"

    # ==========================================================
    # Campos base
    # ==========================================================
    name = fields.Char(
        string="Referencia",
        required=True,
        default=lambda self: _("Nueva sesión"),
        copy=False,
        index=True,
    )

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contacto",
        required=True,
        index=True,
        ondelete="cascade",
    )

    active_company_id = fields.Many2one(
        comodel_name="res.partner",
        string="Empresa activa",
        domain=[("is_company", "=", True)],
        index=True,
    )

    phone = fields.Char(string="Teléfono", index=True)
    jid = fields.Char(string="JID", index=True)
    lid = fields.Char(string="LID", index=True)
    raw_jid = fields.Char(string="Raw JID")

    state = fields.Selection(
        selection=[
            ("open", "Abierta"),
            ("human", "Modo humano"),
            ("closed", "Cerrada"),
            ("expired", "Expirada"),
        ],
        string="Estado",
        default="open",
        required=True,
        index=True,
    )

    source = fields.Selection(
        selection=[
            ("whatsapp", "WhatsApp"),
            ("n8n", "n8n"),
            ("api", "API"),
            ("manual", "Manual"),
        ],
        string="Origen",
        default="whatsapp",
    )

    started_at = fields.Datetime(
        string="Inicio",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    last_message_at = fields.Datetime(
        string="Último mensaje",
        default=fields.Datetime.now,
        index=True,
    )

    closed_at = fields.Datetime(string="Cierre")

    last_intent = fields.Char(string="Última intención", index=True)
    last_user_message = fields.Text(string="Último mensaje del cliente", readonly=True)
    last_bot_message = fields.Text(string="Último mensaje del bot", readonly=True)

    message_ids = fields.One2many(
        comodel_name="whatsapp.message",
        inverse_name="session_id",
        string="Mensajes",
    )

    message_count = fields.Integer(
        string="Cantidad de mensajes",
        compute="_compute_message_count",
        store=False,
    )

    is_active = fields.Boolean(
        string="Sesión activa",
        compute="_compute_is_active",
        store=False,
    )

    note = fields.Text(string="Notas internas")

    # ==========================================================
    # Campos nuevos: Máquina de estados conversacional
    # ==========================================================
    conversation_state = fields.Selection(
        selection=[
            ("idle", "En espera"),

            # Registro
            ("awaiting_dni", "Esperando DNI"),
            ("awaiting_ruc", "Esperando RUC"),
            ("awaiting_company_selection", "Esperando selección de empresa"),

            # Flujo tóner
            ("awaiting_machine_selection_toner", "Tóner: Esperando selección de equipo"),
            ("awaiting_toner_color", "Tóner: Esperando color"),
            ("awaiting_toner_quantity", "Tóner: Esperando cantidad"),
            ("awaiting_toner_counter_bn", "Tóner: Esperando contador B/N"),
            ("awaiting_toner_counter_color", "Tóner: Esperando contador color"),
            ("awaiting_toner_observations", "Tóner: Esperando observaciones"),
            ("awaiting_toner_confirmation", "Tóner: Esperando confirmación"),

            # Flujo servicio presencial
            ("awaiting_machine_selection_onsite", "Servicio: Esperando selección de equipo"),
            ("awaiting_service_description", "Servicio: Esperando descripción"),
            ("awaiting_service_photo", "Servicio: Esperando foto opcional"),
            ("awaiting_service_confirmation", "Servicio: Esperando confirmación"),

            # Flujo remoto / AnyDesk
            ("awaiting_anydesk_code", "Remoto: Esperando código AnyDesk"),
            ("awaiting_remote_problem", "Remoto: Esperando descripción del problema"),

            # Genéricos
            ("awaiting_human", "Esperando atención humana"),
            ("awaiting_clarification", "Esperando clarificación de intención"),
        ],
        string="Estado conversación",
        default="idle",
        required=True,
        index=True,
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
        string="Flujo actual",
        default="none",
        required=True,
        index=True,
    )

    conversation_context = fields.Text(
        string="Contexto conversacional (JSON)",
        default="{}",
        help="Datos del flujo en curso: intent, machine_id, color, opciones del menú, etc.",
    )

    conversation_state_expires_at = fields.Datetime(
        string="Expira flujo en",
        index=True,
        help="Si el cliente no responde antes de esta fecha, el flujo se resetea a idle.",
    )

    flow_started_at = fields.Datetime(string="Inicio del flujo")
    flow_completed_at = fields.Datetime(string="Flujo completado")

    close_reason = fields.Selection(
        selection=[
            ("completed_toner", "Completado: Tóner"),
            ("completed_onsite", "Completado: Servicio presencial"),
            ("completed_remote", "Completado: Soporte remoto"),
            ("completed_registration", "Completado: Registro"),
            ("completed_other", "Completado: Otro"),
            ("abandoned", "Abandonado por el cliente"),
            ("expired", "Expirado por inactividad"),
            ("escalated_human", "Escalado a humano"),
            ("manual_close", "Cerrado manualmente"),
        ],
        string="Motivo de cierre",
        index=True,
    )

    conversation_state_label = fields.Char(
        string="Estado conversación (etiqueta)",
        compute="_compute_conversation_state_label",
        store=False,
    )

    # ==========================================================
    # Computes
    # ==========================================================
    @api.depends("message_ids")
    def _compute_message_count(self):
        for session in self:
            session.message_count = len(session.message_ids)

    @api.depends("state")
    def _compute_is_active(self):
        for session in self:
            session.is_active = session.state in ("open", "human")

    @api.depends("conversation_state", "current_flow")
    def _compute_conversation_state_label(self):
        for session in self:
            if session.conversation_state == "idle":
                session.conversation_state_label = "En espera"
                continue
            flow_dict = dict(session._fields["current_flow"].selection)
            state_dict = dict(session._fields["conversation_state"].selection)
            flow_label = flow_dict.get(session.current_flow, "")
            state_label = state_dict.get(session.conversation_state, "")
            session.conversation_state_label = (
                "%s · %s" % (flow_label, state_label) if flow_label else state_label
            )

    # ==========================================================
    # Constraints
    # ==========================================================
    @api.constrains("conversation_state", "current_flow")
    def _check_conversation_state_consistency(self):
        for session in self:
            if session.current_flow != "none" and session.conversation_state == "idle":
                _logger.warning(
                    "[WA-SESSION] Inconsistencia sesión %s: current_flow=%s pero conversation_state=idle",
                    session.id, session.current_flow,
                )
            if session.current_flow == "none" and session.conversation_state != "idle":
                _logger.warning(
                    "[WA-SESSION] Inconsistencia sesión %s: conversation_state=%s pero current_flow=none",
                    session.id, session.conversation_state,
                )

    # ==========================================================
    # Create
    # ==========================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Nueva sesión")) == _("Nueva sesión"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("whatsapp.session")
                    or _("Nueva sesión")
                )
            if not vals.get("conversation_context"):
                vals["conversation_context"] = "{}"
        sessions = super().create(vals_list)
        for session in sessions:
            _logger.info(
                "[WA-SESSION] Sesión creada id=%s partner=%s phone=%s state=%s",
                session.id, session.partner_id.id, session.phone, session.state,
            )
        return sessions

    # ==========================================================
    # Acciones de estado de sesión
    # ==========================================================
    def action_close(self, close_reason=False):
        for session in self:
            _logger.info(
                "[WA-SESSION] Cerrando sesión id=%s partner=%s reason=%s",
                session.id, session.partner_id.id, close_reason,
            )
            vals = {
                "state": "closed",
                "closed_at": fields.Datetime.now(),
            }
            if close_reason:
                vals["close_reason"] = close_reason
            session.write(vals)
            session._clear_conversation_internal()
        return True

    def action_expire(self):
        for session in self:
            _logger.info(
                "[WA-SESSION] Expirando sesión id=%s partner=%s",
                session.id, session.partner_id.id,
            )
            session.write({
                "state": "expired",
                "closed_at": fields.Datetime.now(),
                "close_reason": "expired",
            })
            session._clear_conversation_internal()
        return True

    def action_set_human(self):
        for session in self:
            _logger.info(
                "[WA-SESSION] Activando modo humano sesión id=%s partner=%s",
                session.id, session.partner_id.id,
            )
            session.write({
                "state": "human",
                "close_reason": "escalated_human",
            })
            session._clear_conversation_internal()
        return True

    def action_reopen(self):
        for session in self:
            _logger.info(
                "[WA-SESSION] Reabriendo sesión id=%s partner=%s",
                session.id, session.partner_id.id,
            )
            session.write({
                "state": "open",
                "closed_at": False,
                "close_reason": False,
            })
        return True

    # ==========================================================
    # Touch (mensaje recibido/enviado)
    # ==========================================================
    def touch(self, intent=False, user_message=False, bot_message=False):
        self.ensure_one()
        vals = {"last_message_at": fields.Datetime.now()}

        if intent:
            vals["last_intent"] = intent

        if user_message:
            vals["last_user_message"] = user_message

        if bot_message:
            vals["last_bot_message"] = bot_message

        if self.current_flow != "none" and self.conversation_state != "idle":
            timeout_minutes = self._get_conversation_timeout_minutes()
            vals["conversation_state_expires_at"] = (
                fields.Datetime.now() + timedelta(minutes=timeout_minutes)
            )
            _logger.debug(
                "[WA-SESSION] Extendiendo timeout flujo id=%s nuevo_expire=%s",
                self.id, vals["conversation_state_expires_at"],
            )

        self.write(vals)
        return True

    # ==========================================================
    # Helpers de contexto JSON
    # ==========================================================
    def get_context(self):
        self.ensure_one()
        if not self.conversation_context:
            return {}
        try:
            return json.loads(self.conversation_context)
        except Exception as e:
            _logger.error(
                "[WA-SESSION] Error parseando contexto sesión id=%s error=%s contexto=%r",
                self.id, str(e), self.conversation_context,
            )
            return {}

    def set_context(self, data):
        self.ensure_one()
        if not isinstance(data, dict):
            _logger.error(
                "[WA-SESSION] set_context tipo inválido id=%s tipo=%s",
                self.id, type(data).__name__,
            )
            raise ValidationError(_("El contexto debe ser un diccionario."))
        try:
            serialized = json.dumps(data, ensure_ascii=False, default=str)
        except Exception as e:
            _logger.exception(
                "[WA-SESSION] Error serializando contexto sesión id=%s error=%s",
                self.id, str(e),
            )
            raise ValidationError(_("No se pudo serializar el contexto: %s") % str(e))
        self.write({"conversation_context": serialized})
        _logger.debug(
            "[WA-SESSION] Contexto actualizado id=%s keys=%s",
            self.id, list(data.keys()),
        )
        return True

    def update_context(self, partial):
        self.ensure_one()
        if not isinstance(partial, dict):
            _logger.error(
                "[WA-SESSION] update_context tipo inválido id=%s tipo=%s",
                self.id, type(partial).__name__,
            )
            raise ValidationError(_("El contexto parcial debe ser un diccionario."))
        current = self.get_context()
        current.update(partial)
        self.set_context(current)
        _logger.debug(
            "[WA-SESSION] Contexto merge id=%s keys_added=%s",
            self.id, list(partial.keys()),
        )
        return current

    def clear_context(self):
        self.ensure_one()
        _logger.debug("[WA-SESSION] Limpiando contexto sesión id=%s", self.id)
        self.write({"conversation_context": "{}"})
        return True

    def _clear_conversation_internal(self):
        """Limpia estado conversacional sin tocar state de sesión."""
        for session in self:
            session.write({
                "conversation_state": "idle",
                "current_flow": "none",
                "conversation_context": "{}",
                "conversation_state_expires_at": False,
            })
        return True

    # ==========================================================
    # Máquina de estados: API pública
    # ==========================================================
    def _get_conversation_timeout_minutes(self):
        param = self.env["ir.config_parameter"].sudo().get_param(
            "sat.whatsapp_conversation_state_timeout_minutes", "15",
        )
        try:
            return int(param)
        except Exception:
            _logger.warning(
                "[WA-SESSION] Parámetro timeout inválido: %r, usando 15", param,
            )
            return 15

    def start_flow(self, flow_name, initial_state, context=None):
        """
        Inicia un flujo conversacional.

        :param flow_name: clave de current_flow (toner, onsite, remote, etc.)
        :param initial_state: clave de conversation_state inicial
        :param context: dict con datos iniciales del flujo
        """
        self.ensure_one()
        context = context or {}

        valid_flows = dict(self._fields["current_flow"].selection)
        valid_states = dict(self._fields["conversation_state"].selection)

        if flow_name not in valid_flows:
            _logger.error(
                "[WA-SESSION] start_flow flow_name inválido id=%s flow=%s",
                self.id, flow_name,
            )
            raise ValidationError(_("Flujo desconocido: %s") % flow_name)

        if initial_state not in valid_states:
            _logger.error(
                "[WA-SESSION] start_flow initial_state inválido id=%s state=%s",
                self.id, initial_state,
            )
            raise ValidationError(_("Estado desconocido: %s") % initial_state)

        timeout_minutes = self._get_conversation_timeout_minutes()
        now = fields.Datetime.now()

        self.write({
            "current_flow": flow_name,
            "conversation_state": initial_state,
            "conversation_context": json.dumps(context, ensure_ascii=False, default=str),
            "conversation_state_expires_at": now + timedelta(minutes=timeout_minutes),
            "flow_started_at": now,
            "flow_completed_at": False,
            "close_reason": False,
        })

        _logger.info(
            "[WA-SESSION] Flujo iniciado id=%s partner=%s flow=%s initial_state=%s context_keys=%s",
            self.id, self.partner_id.id, flow_name, initial_state, list(context.keys()),
        )
        return True

    def advance_state(self, new_state, context_update=None, extend_timeout=True):
        """
        Avanza la máquina de estados al siguiente paso del flujo activo.

        :param new_state: nuevo conversation_state
        :param context_update: dict con datos a fusionar al contexto
        :param extend_timeout: si True, extiende el timeout de expiración
        """
        self.ensure_one()

        valid_states = dict(self._fields["conversation_state"].selection)
        if new_state not in valid_states:
            _logger.error(
                "[WA-SESSION] advance_state estado inválido id=%s state=%s",
                self.id, new_state,
            )
            raise ValidationError(_("Estado desconocido: %s") % new_state)

        if self.current_flow == "none":
            _logger.warning(
                "[WA-SESSION] advance_state sin flujo activo id=%s new_state=%s",
                self.id, new_state,
            )

        vals = {"conversation_state": new_state}

        if extend_timeout:
            timeout_minutes = self._get_conversation_timeout_minutes()
            vals["conversation_state_expires_at"] = (
                fields.Datetime.now() + timedelta(minutes=timeout_minutes)
            )

        self.write(vals)

        if context_update:
            self.update_context(context_update)

        _logger.info(
            "[WA-SESSION] Estado avanzado id=%s flow=%s new_state=%s context_update_keys=%s",
            self.id, self.current_flow, new_state,
            list(context_update.keys()) if context_update else [],
        )
        return True

    def complete_flow(self, close_reason="completed_other", final_context_update=None):
        """
        Marca el flujo como completado exitosamente y vuelve a idle.

        :param close_reason: razón de cierre (debe ser uno de los valores de close_reason)
        :param final_context_update: últimos datos a guardar en el contexto antes de limpiar
        """
        self.ensure_one()
        valid_reasons = dict(self._fields["close_reason"].selection)
        if close_reason not in valid_reasons:
            _logger.warning(
                "[WA-SESSION] complete_flow close_reason inválido id=%s reason=%s, usando completed_other",
                self.id, close_reason,
            )
            close_reason = "completed_other"

        if final_context_update:
            self.update_context(final_context_update)

        _logger.info(
            "[WA-SESSION] Flujo completado id=%s flow=%s reason=%s",
            self.id, self.current_flow, close_reason,
        )

        self.write({
            "flow_completed_at": fields.Datetime.now(),
            "close_reason": close_reason,
        })

        self._clear_conversation_internal()
        return True

    def reset_conversation(self, reason="abandoned"):
        """
        Resetea el flujo (cliente abandonó, timeout, o reinicio manual).
        No cierra la sesión, solo limpia el estado conversacional.
        """
        self.ensure_one()
        _logger.info(
            "[WA-SESSION] Reseteando conversación id=%s flow=%s reason=%s",
            self.id, self.current_flow, reason,
        )
        self.write({
            "close_reason": reason if reason in dict(self._fields["close_reason"].selection) else False,
        })
        self._clear_conversation_internal()
        return True

    def is_conversation_expired(self):
        """True si el flujo activo ya superó su tiempo de expiración."""
        self.ensure_one()
        if self.current_flow == "none" or not self.conversation_state_expires_at:
            return False
        expired = fields.Datetime.now() > self.conversation_state_expires_at
        if expired:
            _logger.debug(
                "[WA-SESSION] Flujo expirado id=%s expires_at=%s",
                self.id, self.conversation_state_expires_at,
            )
        return expired

    # ==========================================================
    # Cron: expirar flujos abandonados
    # ==========================================================
    @api.model
    def cron_expire_conversations(self):
        """
        Cron que resetea flujos cuyos timeouts han vencido.
        Programar cada 5 minutos.
        """
        now = fields.Datetime.now()
        expired_sessions = self.search([
            ("current_flow", "!=", "none"),
            ("conversation_state", "!=", "idle"),
            ("conversation_state_expires_at", "!=", False),
            ("conversation_state_expires_at", "<", now),
            ("state", "in", ["open", "human"]),
        ])

        _logger.info(
            "[WA-SESSION] cron_expire_conversations: %s flujos a expirar",
            len(expired_sessions),
        )

        for session in expired_sessions:
            try:
                session.reset_conversation(reason="expired")
            except Exception as e:
                _logger.exception(
                    "[WA-SESSION] Error expirando flujo id=%s error=%s",
                    session.id, str(e),
                )

        return True