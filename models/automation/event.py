# -*- coding: utf-8 -*-

import hashlib
import json
import logging
import traceback
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .constants import (
    SOURCE_SELECTION,
    EVENT_TYPE_SELECTION,
    EVENT_STATE_SELECTION,
    ACTION_TYPE_SELECTION,
)

_logger = logging.getLogger(__name__)


class SatAutomationEvent(models.Model):
    _name = "sat.automation.event"
    _description = "Evento de Automatización SAT"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "event_datetime desc, id desc"
    _rec_name = "name"

    name = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _("Nuevo"),
        tracking=True,
    )
    event_uuid = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: str(uuid.uuid4()),
    )
    fingerprint = fields.Char(readonly=True, copy=False, index=True)
    external_id = fields.Char(copy=False, index=True)

    source = fields.Selection(
        SOURCE_SELECTION,
        required=True,
        default="system",
        tracking=True,
        index=True,
    )
    source_subtype = fields.Char(index=True)
    source_model = fields.Char(index=True, copy=False)
    source_record_id = fields.Integer(index=True, copy=False)

    event_type = fields.Selection(
        EVENT_TYPE_SELECTION,
        required=True,
        default="unknown",
        tracking=True,
        index=True,
    )
    event_subtype = fields.Char(index=True)

    state = fields.Selection(
        EVENT_STATE_SELECTION,
        default="new",
        required=True,
        tracking=True,
        index=True,
    )
    requires_review = fields.Boolean(default=False, tracking=True, index=True)
    review_reason = fields.Text(tracking=True)

    event_datetime = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    received_datetime = fields.Datetime(
        default=fields.Datetime.now,
        readonly=True,
        copy=False,
        index=True,
    )
    processing_started_at = fields.Datetime(readonly=True, copy=False)
    processed_at = fields.Datetime(readonly=True, copy=False, index=True)

    serial_number = fields.Char(index=True, tracking=True)
    equipment_id = fields.Many2one(
        "alquiler",
        string="Equipo",
        index=True,
        tracking=True,
        ondelete="set null",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Cliente",
        index=True,
        tracking=True,
        ondelete="set null",
    )
    contact_id = fields.Many2one(
        "res.partner",
        string="Contacto",
        index=True,
        tracking=True,
        ondelete="set null",
    )

    sender = fields.Char(index=True)
    sender_domain = fields.Char(index=True)
    subject = fields.Char(index=True)
    email_message_id = fields.Char(index=True, copy=False)
    original_mail_message_id = fields.Many2one(
        "mail.message",
        ondelete="set null",
        index=True,
        copy=False,
    )
    body_original = fields.Html(sanitize=False)
    body_plain = fields.Text()

    meter_bn = fields.Integer()
    meter_color = fields.Integer()
    meter_scan = fields.Integer()
    meter_total = fields.Integer()

    supply_type = fields.Selection(
        [
            ("toner", "Tóner"),
            ("ink", "Tinta"),
            ("drum", "Drum"),
            ("fuser", "Fusor"),
            ("transfer", "Transferencia"),
            ("waste", "Residuos"),
            ("maintenance", "Kit mantenimiento"),
            ("other", "Otro"),
        ]
    )
    supply_color = fields.Selection(
        [
            ("black", "Negro"),
            ("cyan", "Cian"),
            ("magenta", "Magenta"),
            ("yellow", "Amarillo"),
            ("color", "Color"),
            ("colorless", "Sin color"),
            ("unknown", "No identificado"),
        ]
    )
    supply_percentage = fields.Float()
    requested_quantity = fields.Integer(default=0)

    issue_description = fields.Text()
    error_code = fields.Char(index=True)
    location_detected = fields.Char()

    classification_method = fields.Selection(
        [
            ("none", "Sin clasificar"),
            ("filter", "Filtro"),
            ("pattern", "Patrón"),
            ("rule", "Regla"),
            ("ai", "Inteligencia Artificial"),
            ("combined", "Combinado"),
            ("manual", "Manual"),
        ],
        default="none",
        tracking=True,
    )
    pattern_confidence = fields.Float(default=0.0)
    patterns_used = fields.Text()

    ai_used = fields.Boolean(default=False, readonly=True, copy=False)
    ai_provider_name = fields.Char(readonly=True, copy=False)
    ai_model_name = fields.Char(readonly=True, copy=False)
    ai_confidence = fields.Float(default=0.0, readonly=True, copy=False)
    ai_prompt_version = fields.Char(readonly=True, copy=False)
    ai_input_tokens = fields.Integer(readonly=True, copy=False)
    ai_output_tokens = fields.Integer(readonly=True, copy=False)
    ai_cost = fields.Float(digits=(12, 8), readonly=True, copy=False)
    ai_raw_response = fields.Text(readonly=True, copy=False)

    payload_json = fields.Text(copy=False)
    raw_payload_json = fields.Text(copy=False)

    action_type = fields.Selection(
        ACTION_TYPE_SELECTION,
        default="none",
        tracking=True,
    )
    action_model = fields.Char(index=True, copy=False)
    action_record_id = fields.Integer(index=True, copy=False)
    action_description = fields.Text(copy=False)

    retry_count = fields.Integer(default=0, readonly=True, copy=False)
    last_retry_at = fields.Datetime(readonly=True, copy=False)
    error_message = fields.Text(readonly=True, copy=False, tracking=True)
    error_traceback = fields.Text(readonly=True, copy=False)

    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("sat_automation_event_uuid_unique", "unique(event_uuid)", "UUID duplicado."),
        ("sat_automation_fingerprint_unique", "unique(fingerprint)", "Evento duplicado."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            if not vals.get("name") or vals.get("name") == _("Nuevo"):
                vals["name"] = self._generate_event_name(vals)
            vals.setdefault("event_uuid", str(uuid.uuid4()))
            vals["sender_domain"] = self._extract_sender_domain(vals.get("sender"))
            vals.setdefault("fingerprint", self._generate_fingerprint(vals))
            self._validate_json(vals.get("payload_json"), "payload_json")
            self._validate_json(vals.get("raw_payload_json"), "raw_payload_json")
            prepared.append(vals)

        records = super().create(prepared)

        for record in records:
            _logger.info(
                "[SAT AUTOMATION][EVENT][CREATE] id=%s source=%s type=%s "
                "source_model=%s source_record_id=%s fingerprint=%s",
                record.id, record.source, record.event_type,
                record.source_model, record.source_record_id, record.fingerprint,
            )
            record._audit(
                "event_created",
                message="Evento creado.",
                data={
                    "source": record.source,
                    "event_type": record.event_type,
                    "source_model": record.source_model,
                    "source_record_id": record.source_record_id,
                },
            )
        return records

    @api.model
    def _generate_event_name(self, vals):
        return "%s/%s/%s" % (
            (vals.get("source") or "system").upper(),
            (vals.get("event_type") or "unknown").upper(),
            fields.Datetime.now().strftime("%Y%m%d-%H%M%S-%f"),
        )

    @api.model
    def _extract_sender_domain(self, sender):
        if not sender:
            return False
        value = str(sender).strip().lower()
        if "<" in value and ">" in value:
            value = value.split("<", 1)[1].split(">", 1)[0].strip()
        if "@" not in value:
            return False
        return value.rsplit("@", 1)[1].strip() or False

    @api.model
    def _norm(self, value):
        if value is None:
            return ""
        return str(value).strip().lower()

    @api.model
    def _generate_fingerprint(self, vals):
        source = self._norm(vals.get("source") or "system")
        external_id = self._norm(vals.get("external_id"))
        if external_id:
            raw = "|".join([source, "external", external_id])
            return hashlib.sha256(raw.encode()).hexdigest()

        message_id = self._norm(vals.get("email_message_id"))
        if message_id:
            raw = "|".join([source, "mail", message_id])
            return hashlib.sha256(raw.encode()).hexdigest()

        source_model = self._norm(vals.get("source_model"))
        source_record_id = self._norm(vals.get("source_record_id"))
        if source_model and source_record_id:
            raw = "|".join([source, "odoo", source_model, source_record_id])
            return hashlib.sha256(raw.encode()).hexdigest()

        parts = [
            source,
            self._norm(vals.get("event_type")),
            self._norm(vals.get("serial_number")),
            self._norm(vals.get("sender")),
            self._norm(vals.get("subject")),
            self._norm(vals.get("event_datetime")),
            self._norm(vals.get("meter_bn")),
            self._norm(vals.get("meter_color")),
            self._norm(vals.get("meter_scan")),
            self._norm(vals.get("error_code")),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    @api.model
    def _validate_json(self, value, field_name):
        if not value or isinstance(value, (dict, list)):
            return True
        try:
            json.loads(value)
        except Exception as exc:
            raise ValidationError(
                _("JSON inválido en %s: %s") % (field_name, str(exc))
            )
        return True

    def get_payload(self):
        self.ensure_one()
        if not self.payload_json:
            return {}
        try:
            return json.loads(self.payload_json)
        except Exception:
            _logger.exception(
                "[SAT AUTOMATION][EVENT][JSON] event_id=%s payload inválido",
                self.id,
            )
            return {}

    def set_payload(self, payload):
        for event in self:
            event.payload_json = json.dumps(
                payload or {}, ensure_ascii=False, default=str
            )
        return True

    @api.model
    def create_from_source(self, values, auto_process=False):
        values = dict(values or {})
        fingerprint = values.get("fingerprint") or self._generate_fingerprint(values)
        existing = self.search([("fingerprint", "=", fingerprint)], limit=1)

        if existing:
            _logger.info(
                "[SAT AUTOMATION][EVENT][DUPLICATE] fingerprint=%s event_id=%s",
                fingerprint, existing.id,
            )
            existing._audit(
                "duplicate_received",
                level="warning",
                message="Evento duplicado recibido.",
            )
            return existing, False

        values["fingerprint"] = fingerprint

        try:
            event = self.create(values)
        except Exception:
            existing = self.search([("fingerprint", "=", fingerprint)], limit=1)
            if existing:
                return existing, False
            raise

        if auto_process:
            event.process_event()

        return event, True

    def resolve_equipment(self):
        for event in self:
            if event.equipment_id or not event.serial_number:
                continue

            serial = (event.serial_number or "").strip()
            equipment = self.env["alquiler"].search(
                [("serie", "=ilike", serial)],
                limit=2,
            )

            if len(equipment) == 1:
                vals = {"equipment_id": equipment.id}
                if "cliente_id" in equipment._fields and equipment.cliente_id:
                    vals["partner_id"] = equipment.cliente_id.id
                event.write(vals)
                event._audit(
                    "equipment_resolved",
                    message="Equipo relacionado por serie.",
                    data={"serial": serial, "equipment_id": equipment.id},
                )
                _logger.info(
                    "[SAT AUTOMATION][EVENT][EQUIPMENT] event_id=%s serial=%s equipment_id=%s",
                    event.id, serial, equipment.id,
                )
            elif len(equipment) > 1:
                event.mark_review(
                    _("Existe más de un equipo con la serie %s.") % serial
                )
        return True

    def mark_processing(self):
        for event in self:
            event.write({
                "state": "processing",
                "processing_started_at": fields.Datetime.now(),
                "error_message": False,
                "error_traceback": False,
            })
            event._audit("processing_started", message="Procesamiento iniciado.")
        return True

    def mark_done(self, description=None):
        for event in self:
            event.write({
                "state": "done",
                "requires_review": False,
                "processed_at": fields.Datetime.now(),
                "error_message": False,
                "error_traceback": False,
                "action_description": description or event.action_description,
            })
            event._audit(
                "processing_done",
                message=description or "Procesamiento completado.",
            )
        return True

    def mark_review(self, reason):
        for event in self:
            event.write({
                "state": "review",
                "requires_review": True,
                "review_reason": reason or _("Revisión requerida."),
            })
            event._audit(
                "manual_review",
                level="warning",
                message=reason or "Revisión requerida.",
            )
        return True

    def mark_ignored(self, reason=None):
        for event in self:
            event.write({
                "state": "ignored",
                "requires_review": False,
                "processed_at": fields.Datetime.now(),
                "action_description": reason or event.action_description,
            })
            event._audit("ignored", message=reason or "Evento ignorado.")
        return True

    def mark_error(self, message, exception=None):
        for event in self:
            tb = traceback.format_exc() if exception else False
            event.write({
                "state": "error",
                "error_message": str(message or ""),
                "error_traceback": tb,
            })
            event._audit(
                "processing_error",
                level="error",
                message=str(message or ""),
                data={"traceback": tb} if tb else {},
            )
            _logger.error(
                "[SAT AUTOMATION][EVENT][ERROR] event_id=%s message=%s",
                event.id, message,
            )
        return True

    def register_ai_result(
        self,
        provider_name,
        model_name,
        result=None,
        confidence=0.0,
        input_tokens=0,
        output_tokens=0,
        cost=0.0,
        prompt_version=None,
        raw_response=None,
    ):
        result = result or {}
        for event in self:
            vals = {
                "ai_used": True,
                "ai_provider_name": provider_name,
                "ai_model_name": model_name,
                "ai_confidence": float(confidence or 0.0),
                "ai_input_tokens": int(input_tokens or 0),
                "ai_output_tokens": int(output_tokens or 0),
                "ai_cost": float(cost or 0.0),
            }
            if prompt_version:
                vals["ai_prompt_version"] = prompt_version
            if raw_response is not None:
                vals["ai_raw_response"] = (
                    json.dumps(raw_response, ensure_ascii=False, default=str)
                    if isinstance(raw_response, (dict, list))
                    else str(raw_response)
                )
            event.write(vals)
            event._audit(
                "ai_result_registered",
                message="Resultado IA registrado.",
                data={
                    "provider": provider_name,
                    "model": model_name,
                    "confidence": confidence,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": cost,
                },
            )
        return True

    def link_action(self, record, action_type=None, description=None):
        self.ensure_one()
        if not record or not record.exists():
            raise UserError(_("No se puede relacionar un registro inexistente."))

        vals = {
            "action_model": record._name,
            "action_record_id": record.id,
        }
        if action_type:
            vals["action_type"] = action_type
        if description:
            vals["action_description"] = description
        self.write(vals)
        self._audit(
            "action_linked",
            message="Registro resultado relacionado.",
            data={
                "model": record._name,
                "record_id": record.id,
                "action_type": action_type,
            },
        )
        return True

    def action_retry(self):
        for event in self:
            event.write({
                "retry_count": event.retry_count + 1,
                "last_retry_at": fields.Datetime.now(),
                "state": "new",
                "requires_review": False,
                "review_reason": False,
                "error_message": False,
                "error_traceback": False,
                "processing_started_at": False,
                "processed_at": False,
            })
            event._audit(
                "retry_registered",
                level="warning",
                message="Evento preparado para reproceso.",
            )
            event.process_event()
        return True

    def action_ignore(self):
        return self.mark_ignored(_("Evento ignorado manualmente."))

    def action_cancel(self):
        for event in self:
            event.write({
                "state": "cancelled",
                "processed_at": fields.Datetime.now(),
            })
            event._audit(
                "cancelled",
                level="warning",
                message="Evento cancelado manualmente.",
            )
        return True

    @api.model
    def cron_recover_stuck_events(self):
        config = self.env["sat.automation.config"].get_config()
        cutoff = fields.Datetime.subtract(
            fields.Datetime.now(),
            hours=config.stuck_processing_hours or 2,
        )
        events = self.search([
            ("state", "=", "processing"),
            ("processing_started_at", "<=", cutoff),
        ])
        for event in events:
            event.mark_review(
                _("Evento bloqueado durante más de %s horas.")
                % (config.stuck_processing_hours or 2)
            )
        if events:
            _logger.warning(
                "[SAT AUTOMATION][EVENT][STUCK] ids=%s", events.ids
            )
        return True

    def _audit(self, action, level="info", message=None, data=None):
        for event in self:
            self.env["sat.automation.audit"].sudo().create_log(
                event=event,
                action=action,
                level=level,
                message=message,
                data=data or {},
            )
        return True

    def process_event(self):
        for event in self:
            self.env["sat.automation.processor"].process(event)
        return True
