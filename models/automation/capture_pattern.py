# -*- coding: utf-8 -*-

import logging
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .constants import (
    SOURCE_SELECTION,
    EVENT_TYPE_SELECTION,
    PATTERN_STATE_SELECTION,
    VALUE_TYPE_SELECTION,
)

_logger = logging.getLogger(__name__)


class SatAutomationCapturePattern(models.Model):
    _name = "sat.automation.capture.pattern"
    _description = "Patrón genérico de captura SAT"
    _order = "priority_score desc, sequence, id"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10, index=True)

    state = fields.Selection(
        PATTERN_STATE_SELECTION,
        default="candidate",
        required=True,
        index=True,
        tracking=True,
    )

    source = fields.Selection(
        [("all", "Todos")] + SOURCE_SELECTION,
        default="all",
        required=True,
        index=True,
    )
    event_type = fields.Selection(EVENT_TYPE_SELECTION)

    target_key = fields.Char(
        required=True,
        help="Ej.: serial_number, meter_bn, supply_color, error_code",
    )
    regex = fields.Text(required=True)
    value_group = fields.Integer(default=1)
    value_type = fields.Selection(
        VALUE_TYPE_SELECTION,
        default="char",
        required=True,
    )

    sender_domain = fields.Char()
    partner_id = fields.Many2one("res.partner")
    case_sensitive = fields.Boolean(default=False)

    origin = fields.Selection(
        [
            ("manual", "Manual"),
            ("ai", "IA"),
            ("legacy", "Legacy"),
            ("system", "Sistema"),
        ],
        default="manual",
        required=True,
        index=True,
    )

    confidence = fields.Float(default=0.0)
    tests_count = fields.Integer(default=0, readonly=True)
    success_count = fields.Integer(default=0, readonly=True)
    failure_count = fields.Integer(default=0, readonly=True)
    last_test_at = fields.Datetime(readonly=True)
    last_success_at = fields.Datetime(readonly=True)

    success_rate = fields.Float(
        compute="_compute_metrics",
        store=True,
    )
    priority_score = fields.Float(
        compute="_compute_metrics",
        store=True,
        index=True,
    )

    created_from_event_id = fields.Many2one(
        "sat.automation.event",
        ondelete="set null",
        copy=False,
    )
    validated_by_id = fields.Many2one(
        "res.users",
        readonly=True,
        copy=False,
    )
    validated_at = fields.Datetime(readonly=True, copy=False)

    @api.depends("tests_count", "success_count", "confidence", "state")
    def _compute_metrics(self):
        for rec in self:
            rec.success_rate = (
                (rec.success_count / rec.tests_count) * 100.0
                if rec.tests_count else 0.0
            )
            state_weight = {
                "active": 100,
                "validated": 90,
                "testing": 20,
                "candidate": 10,
                "rejected": 0,
                "obsolete": 0,
            }.get(rec.state, 0)
            rec.priority_score = (
                state_weight
                + (rec.success_rate * 0.5)
                + (rec.confidence * 0.25)
            )

    @api.constrains("regex")
    def _validate_regex(self):
        for rec in self:
            try:
                re.compile(rec.regex or "")
            except re.error as exc:
                raise ValidationError(_("Regex inválida: %s") % str(exc))

    @api.constrains("confidence")
    def _check_confidence(self):
        for rec in self:
            if rec.confidence < 0 or rec.confidence > 100:
                raise ValidationError(_("Confianza debe estar entre 0 y 100."))

    def applies_to(self, event):
        self.ensure_one()

        if not self.active:
            return False
        if self.source != "all" and self.source != event.source:
            return False
        if self.event_type and self.event_type != event.event_type:
            return False
        if self.sender_domain:
            if (event.sender_domain or "").lower() != self.sender_domain.lower().lstrip("@"):
                return False
        if self.partner_id and event.partner_id != self.partner_id:
            return False
        return True

    def extract(self, text):
        self.ensure_one()
        flags = 0 if self.case_sensitive else re.I
        match = re.search(self.regex, text or "", flags)
        if not match:
            return False
        try:
            raw = match.group(self.value_group)
        except IndexError:
            _logger.error(
                "[SAT AUTOMATION][PATTERN] invalid group pattern_id=%s group=%s",
                self.id, self.value_group,
            )
            return False

        if self.value_type == "integer":
            cleaned = re.sub(r"[^\d\-]", "", str(raw or ""))
            return int(cleaned) if cleaned else 0

        if self.value_type == "float":
            txt = str(raw or "").strip().replace(",", ".")
            txt = re.sub(r"[^0-9.\-]", "", txt)
            return float(txt) if txt else 0.0

        if self.value_type == "boolean":
            return str(raw or "").strip().lower() in (
                "1", "true", "yes", "si", "sí", "y"
            )

        return str(raw or "").strip()

    @api.model
    def apply_active_patterns(self, event, text=None):
        """
        SOLO patrones validados/activos afectan el resultado operativo.
        Los candidatos se prueban por separado en shadow mode.
        """
        text = text if text is not None else (event.body_plain or "")

        patterns = self.search([
            ("active", "=", True),
            ("state", "in", ["validated", "active"]),
        ], order="priority_score desc, sequence, id")

        candidates_by_key = {}

        for pattern in patterns:
            if not pattern.applies_to(event):
                continue

            value = pattern.extract(text)
            if value is False:
                continue

            candidates_by_key.setdefault(pattern.target_key, []).append(
                (pattern, value)
            )

        result = {}
        used = []
        confidences = []

        for target_key, candidates in candidates_by_key.items():
            # Mayor score primero; si varios coinciden, se refuerza la confianza.
            candidates.sort(
                key=lambda item: item[0].priority_score,
                reverse=True,
            )
            selected_pattern, selected_value = candidates[0]

            same_value = [
                p for p, value in candidates
                if str(value).strip().lower() == str(selected_value).strip().lower()
            ]
            support_bonus = min(max(len(same_value) - 1, 0) * 2.0, 10.0)
            effective_confidence = min(
                100.0,
                float(selected_pattern.confidence or 0.0) + support_bonus,
            )

            result[target_key] = selected_value
            used.append(selected_pattern.name)
            confidences.append(effective_confidence)

            _logger.info(
                "[SAT AUTOMATION][PATTERN][ACTIVE_MATCH] event_id=%s "
                "pattern_id=%s target=%s value=%s confidence=%s support=%s",
                event.id, selected_pattern.id, target_key, selected_value,
                effective_confidence, len(same_value),
            )

        confidence = (
            sum(confidences) / len(confidences)
            if confidences else 0.0
        )

        event.write({
            "patterns_used": "\n".join(used) if used else False,
            "pattern_confidence": confidence,
        })

        event._audit(
            "active_patterns_applied",
            message="Patrones productivos evaluados.",
            data={
                "values": result,
                "patterns": used,
                "confidence": confidence,
            },
        )

        return {
            "values": result,
            "patterns": used,
            "confidence": confidence,
        }

    def action_validate(self):
        for rec in self:
            rec.write({
                "state": "validated",
                "validated_by_id": self.env.user.id,
                "validated_at": fields.Datetime.now(),
            })
        return True

    def action_activate(self):
        self.write({"state": "active", "active": True})
        return True

    def action_reject(self):
        self.write({"state": "rejected"})
        return True

    def action_obsolete(self):
        self.write({"state": "obsolete"})
        return True
