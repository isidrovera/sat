# -*- coding: utf-8 -*-

import json
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class WhatsappHandoff(models.Model):
    _name = "whatsapp.handoff"
    _description = "Derivación humana WhatsApp"
    _order = "taken_at desc, id desc"

    name = fields.Char(
        string="Referencia",
        default="Derivación WhatsApp",
        required=True,
        index=True,
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
        required=True,
        index=True,
        ondelete="cascade",
    )

    company_id = fields.Many2one(
        comodel_name="res.partner",
        string="Empresa",
        domain=[("is_company", "=", True)],
        index=True,
        ondelete="set null",
    )

    # ==========================================================
    # Estado y prioridad
    # ==========================================================
    state = fields.Selection(
        selection=[
            ("pending", "Pendiente"),
            ("assigned", "Asignado"),
            ("open", "Activo"),
            ("released", "Liberado"),
            ("cancelled", "Cancelado"),
            ("escalated", "Escalado"),
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

    handoff_type = fields.Selection(
        selection=[
            ("remote_support", "Soporte remoto / AnyDesk"),
            ("onsite_support", "Soporte presencial"),
            ("unknown_intent", "Intención no reconocida"),
            ("complex_inquiry", "Consulta compleja"),
            ("complaint", "Reclamo"),
            ("vip", "Cliente VIP"),
            ("manual", "Manual"),
            ("other", "Otro"),
        ],
        string="Tipo de derivación",
        default="manual",
        required=True,
        index=True,
    )

    # ==========================================================
    # Asignación
    # ==========================================================
    taken_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Tomado por",
        ondelete="set null",
    )

    taken_by_name = fields.Char(string="Tomado por nombre")
    taken_at = fields.Datetime(
        string="Tomado el",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    assigned_to_id = fields.Many2one(
        comodel_name="res.users",
        string="Asignado a",
        index=True,
        ondelete="set null",
    )

    assigned_at = fields.Datetime(string="Asignado el")

    released_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Liberado por",
        ondelete="set null",
    )

    released_by_name = fields.Char(string="Liberado por nombre")
    released_at = fields.Datetime(string="Liberado el", index=True)

    # ==========================================================
    # Contexto y motivo
    # ==========================================================
    reason = fields.Text(string="Motivo")
    note = fields.Text(string="Notas internas")

    initial_message = fields.Text(
        string="Mensaje inicial",
        help="Mensaje del cliente que disparó la derivación.",
    )

    context_data = fields.Text(
        string="Datos de contexto (JSON)",
        default="{}",
        help="Snapshot del contexto conversacional al momento del handoff (machine_id, anydesk_code, etc.).",
    )

    machine_id = fields.Many2one(
        comodel_name="alquiler",
        string="Equipo relacionado",
        ondelete="set null",
        index=True,
    )

    anydesk_code = fields.Char(
        string="Código AnyDesk",
        index=True,
        help="Si la derivación es por soporte remoto, código AnyDesk del cliente.",
    )

    media_ids = fields.Many2many(
        comodel_name="whatsapp.media",
        relation="whatsapp_handoff_media_rel",
        column1="handoff_id",
        column2="media_id",
        string="Archivos adjuntos",
    )

    # ==========================================================
    # Métricas
    # ==========================================================
    response_time_seconds = fields.Integer(
        string="Tiempo de respuesta (seg)",
        compute="_compute_durations",
        store=True,
    )

    resolution_time_seconds = fields.Integer(
        string="Tiempo de resolución (seg)",
        compute="_compute_durations",
        store=True,
    )

    response_time_minutes = fields.Float(
        string="Tiempo de respuesta (min)",
        compute="_compute_durations",
        store=True,
    )

    resolution_time_minutes = fields.Float(
        string="Tiempo de resolución (min)",
        compute="_compute_durations",
        store=True,
    )

    related_ticket_id = fields.Many2one(
        comodel_name="ticket.alquiler",
        string="Ticket relacionado",
        ondelete="set null",
        help="Si la derivación generó un ticket, referencia aquí.",
    )

    # ==========================================================
    # Computes
    # ==========================================================
    @api.depends("taken_at", "assigned_at", "released_at")
    def _compute_durations(self):
        for rec in self:
            response_seconds = 0
            resolution_seconds = 0

            if rec.taken_at and rec.assigned_at:
                response_seconds = int(
                    (rec.assigned_at - rec.taken_at).total_seconds()
                )

            if rec.taken_at and rec.released_at:
                resolution_seconds = int(
                    (rec.released_at - rec.taken_at).total_seconds()
                )

            rec.response_time_seconds = max(response_seconds, 0)
            rec.resolution_time_seconds = max(resolution_seconds, 0)
            rec.response_time_minutes = rec.response_time_seconds / 60.0
            rec.resolution_time_minutes = rec.resolution_time_seconds / 60.0

    # ==========================================================
    # Helpers JSON
    # ==========================================================
    def get_context_data(self):
        self.ensure_one()
        if not self.context_data:
            return {}
        try:
            return json.loads(self.context_data)
        except Exception as e:
            _logger.error(
                "[WA-HANDOFF] Error parseando context_data id=%s error=%s",
                self.id, str(e),
            )
            return {}

    def set_context_data(self, data):
        self.ensure_one()
        if not isinstance(data, dict):
            raise ValidationError(_("context_data debe ser un diccionario."))
        try:
            serialized = json.dumps(data, ensure_ascii=False, default=str)
        except Exception as e:
            _logger.exception(
                "[WA-HANDOFF] Error serializando context_data id=%s error=%s",
                self.id, str(e),
            )
            raise ValidationError(_("No se pudo serializar el contexto: %s") % str(e))
        self.write({"context_data": serialized})
        return True

    # ==========================================================
    # Create con logs
    # ==========================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("context_data"):
                vals["context_data"] = "{}"
            if isinstance(vals.get("context_data"), dict):
                try:
                    vals["context_data"] = json.dumps(
                        vals["context_data"], ensure_ascii=False, default=str,
                    )
                except Exception as e:
                    _logger.error(
                        "[WA-HANDOFF] No se pudo serializar context_data: %s", str(e),
                    )
                    vals["context_data"] = "{}"

        records = super().create(vals_list)

        for rec in records:
            _logger.info(
                "[WA-HANDOFF] Creado id=%s partner=%s session=%s type=%s priority=%s reason=%r",
                rec.id, rec.partner_id.id,
                rec.session_id.id if rec.session_id else False,
                rec.handoff_type, rec.priority, rec.reason,
            )

        return records

    # ==========================================================
    # Acciones de estado
    # ==========================================================
    def action_assign(self, user_id=False):
        """Asigna el handoff a un usuario (técnico/agente)."""
        user_id = user_id or self.env.user.id
        for handoff in self:
            _logger.info(
                "[WA-HANDOFF] Asignando id=%s user=%s",
                handoff.id, user_id,
            )
            handoff.write({
                "state": "assigned",
                "assigned_to_id": user_id,
                "assigned_at": fields.Datetime.now(),
            })
        return True

    def action_take(self):
        """Un usuario toma el handoff (se asigna a sí mismo y pasa a open)."""
        for handoff in self:
            _logger.info(
                "[WA-HANDOFF] Tomado id=%s user=%s",
                handoff.id, self.env.user.id,
            )
            handoff.write({
                "state": "open",
                "assigned_to_id": self.env.user.id,
                "assigned_at": fields.Datetime.now(),
                "taken_by_id": self.env.user.id,
                "taken_by_name": self.env.user.name,
            })
        return True

    def action_release(self):
        for handoff in self:
            if handoff.state in ("released", "cancelled"):
                _logger.warning(
                    "[WA-HANDOFF] Intento de liberar handoff ya cerrado id=%s state=%s",
                    handoff.id, handoff.state,
                )
                continue
            _logger.info(
                "[WA-HANDOFF] Liberado id=%s user=%s",
                handoff.id, self.env.user.id,
            )
            handoff.write({
                "state": "released",
                "released_at": fields.Datetime.now(),
                "released_by_id": self.env.user.id,
                "released_by_name": self.env.user.name,
            })
        return True

    def action_cancel(self, reason=False):
        for handoff in self:
            _logger.info(
                "[WA-HANDOFF] Cancelado id=%s user=%s reason=%s",
                handoff.id, self.env.user.id, reason,
            )
            vals = {
                "state": "cancelled",
                "released_at": fields.Datetime.now(),
                "released_by_id": self.env.user.id,
                "released_by_name": self.env.user.name,
            }
            if reason:
                vals["reason"] = (handoff.reason or "") + "\n[Cancelación] " + reason
            handoff.write(vals)
        return True

    def action_escalate(self, reason=False):
        """Escala el handoff (cambia state a escalated y sube prioridad)."""
        for handoff in self:
            new_priority = str(min(int(handoff.priority or "1") + 1, 3))
            _logger.warning(
                "[WA-HANDOFF] Escalado id=%s nueva_prioridad=%s reason=%s",
                handoff.id, new_priority, reason,
            )
            handoff.write({
                "state": "escalated",
                "priority": new_priority,
                "note": (handoff.note or "") + "\n[Escalado] " + (reason or "Sin motivo"),
            })
        return True

    # ==========================================================
    # Helpers de creación rápida
    # ==========================================================
    @api.model
    def create_remote_support_handoff(self, partner, session=False, machine=False,
                                       anydesk_code=False, initial_message=False,
                                       media=False, context=None):
        """Crea handoff para soporte remoto con código AnyDesk."""
        context = context or {}
        if anydesk_code:
            context["anydesk_code"] = anydesk_code

        _logger.info(
            "[WA-HANDOFF] Creando remote_support partner=%s machine=%s anydesk=%s",
            partner.id if partner else False,
            machine.id if machine else False,
            anydesk_code,
        )

        vals = {
            "partner_id": partner.id if partner else False,
            "session_id": session.id if session else False,
            "company_id": partner.whatsapp_active_company_id.id if partner and partner.whatsapp_active_company_id else False,
            "machine_id": machine.id if machine else False,
            "anydesk_code": anydesk_code or False,
            "handoff_type": "remote_support",
            "priority": "2",
            "state": "pending",
            "initial_message": initial_message or False,
            "context_data": json.dumps(context, ensure_ascii=False, default=str),
            "reason": "Soporte remoto solicitado por cliente.",
        }

        handoff = self.create(vals)

        if media:
            try:
                handoff.write({"media_ids": [(4, m.id) for m in media]})
            except Exception as e:
                _logger.warning(
                    "[WA-HANDOFF] No se pudo vincular media id=%s error=%s",
                    handoff.id, str(e),
                )

        return handoff

    @api.model
    def create_unknown_intent_handoff(self, partner, session=False,
                                      initial_message=False, context=None):
        """Crea handoff cuando no se detectó intención."""
        context = context or {}

        _logger.info(
            "[WA-HANDOFF] Creando unknown_intent partner=%s message=%r",
            partner.id if partner else False,
            (initial_message[:80] + "...") if initial_message and len(initial_message) > 80 else initial_message,
        )

        return self.create({
            "partner_id": partner.id if partner else False,
            "session_id": session.id if session else False,
            "company_id": partner.whatsapp_active_company_id.id if partner and partner.whatsapp_active_company_id else False,
            "handoff_type": "unknown_intent",
            "priority": "1",
            "state": "pending",
            "initial_message": initial_message or False,
            "context_data": json.dumps(context, ensure_ascii=False, default=str),
            "reason": "Intención no reconocida automáticamente.",
        })

    @api.model
    def create_onsite_handoff(self, partner, session=False, machine=False,
                              initial_message=False, media=False, context=None):
        """Crea handoff para servicio presencial."""
        context = context or {}

        _logger.info(
            "[WA-HANDOFF] Creando onsite_support partner=%s machine=%s",
            partner.id if partner else False,
            machine.id if machine else False,
        )

        vals = {
            "partner_id": partner.id if partner else False,
            "session_id": session.id if session else False,
            "company_id": partner.whatsapp_active_company_id.id if partner and partner.whatsapp_active_company_id else False,
            "machine_id": machine.id if machine else False,
            "handoff_type": "onsite_support",
            "priority": "1",
            "state": "pending",
            "initial_message": initial_message or False,
            "context_data": json.dumps(context, ensure_ascii=False, default=str),
            "reason": "Servicio presencial solicitado por cliente.",
        }

        handoff = self.create(vals)

        if media:
            try:
                handoff.write({"media_ids": [(4, m.id) for m in media]})
            except Exception as e:
                _logger.warning(
                    "[WA-HANDOFF] No se pudo vincular media id=%s error=%s",
                    handoff.id, str(e),
                )

        return handoff

    # ==========================================================
    # Consulta para dashboards / n8n
    # ==========================================================
    @api.model
    def get_pending_handoffs(self, limit=50, handoff_type=False):
        """Devuelve handoffs pendientes para notificar a técnicos."""
        domain = [("state", "in", ["pending", "assigned"])]
        if handoff_type:
            domain.append(("handoff_type", "=", handoff_type))

        records = self.search(
            domain,
            order="priority desc, taken_at asc",
            limit=limit,
        )

        _logger.info(
            "[WA-HANDOFF] get_pending_handoffs found=%s type=%s",
            len(records), handoff_type,
        )

        return [rec.to_payload() for rec in records]

    def to_payload(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "partner_id": self.partner_id.id if self.partner_id else False,
            "partner_name": self.partner_id.name if self.partner_id else False,
            "company_id": self.company_id.id if self.company_id else False,
            "company_name": self.company_id.name if self.company_id else False,
            "machine_id": self.machine_id.id if self.machine_id else False,
            "machine_serie": self.machine_id.serie if self.machine_id else False,
            "handoff_type": self.handoff_type,
            "state": self.state,
            "priority": self.priority,
            "anydesk_code": self.anydesk_code,
            "initial_message": self.initial_message,
            "reason": self.reason,
            "taken_at": self.taken_at.isoformat() if self.taken_at else False,
            "assigned_to_id": self.assigned_to_id.id if self.assigned_to_id else False,
            "assigned_to_name": self.assigned_to_id.name if self.assigned_to_id else False,
            "context": self.get_context_data(),
        }