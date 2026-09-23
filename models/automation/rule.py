# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

from .constants import SOURCE_SELECTION, EVENT_TYPE_SELECTION, ACTION_TYPE_SELECTION

_logger = logging.getLogger(__name__)


class SatAutomationRule(models.Model):
    _name = "sat.automation.rule"
    _description = "Regla de automatización SAT"
    _order = "sequence, id"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10, index=True)

    source = fields.Selection([("all", "Todos")] + SOURCE_SELECTION, default="all")
    event_type = fields.Selection(EVENT_TYPE_SELECTION)
    partner_id = fields.Many2one("res.partner")

    require_equipment = fields.Boolean(default=False)
    require_partner = fields.Boolean(default=False)
    min_confidence = fields.Float(default=0.0)
    duplicate_window_hours = fields.Integer(default=24)

    action_mode = fields.Selection(
        [
            ("none", "Sin acción"),
            ("review", "Revisión"),
            ("ignore", "Ignorar"),
            ("model_method", "Método Odoo"),
        ],
        default="none",
        required=True,
    )
    target_model = fields.Char()
    target_method = fields.Char(
        help=(
            "Por seguridad debe comenzar con 'automation_'. "
            "El método recibe un sat.automation.event."
        )
    )
    action_type = fields.Selection(ACTION_TYPE_SELECTION, default="custom")
    stop_after_match = fields.Boolean(default=True)

    @api.constrains("action_mode", "target_model", "target_method")
    def _check_target(self):
        for rec in self:
            if rec.action_mode != "model_method":
                continue
            if not rec.target_model or not rec.target_method:
                raise ValidationError(
                    _("Debe indicar modelo y método destino.")
                )
            if not rec.target_method.startswith("automation_"):
                raise ValidationError(
                    _("El método destino debe comenzar con 'automation_'.")
                )

    def matches(self, event):
        self.ensure_one()

        if self.source != "all" and self.source != event.source:
            return False
        if self.event_type and self.event_type != event.event_type:
            return False
        if self.partner_id and self.partner_id != event.partner_id:
            return False
        if self.require_equipment and not event.equipment_id:
            return False
        if self.require_partner and not event.partner_id:
            return False

        confidence = max(
            event.pattern_confidence or 0.0,
            event.ai_confidence or 0.0,
        )
        if confidence < (self.min_confidence or 0.0):
            return False

        return True

    def execute(self, event):
        self.ensure_one()

        event._audit(
            "rule_execute",
            message="Ejecutando regla.",
            data={"rule_id": self.id, "name": self.name},
        )

        if self.action_mode == "none":
            return {"status": "no_action"}

        if self.action_mode == "review":
            event.mark_review(_("Regla '%s' requiere revisión.") % self.name)
            return {"status": "review"}

        if self.action_mode == "ignore":
            event.mark_ignored(_("Ignorado por regla '%s'.") % self.name)
            return {"status": "ignored"}

        if self.target_model not in self.env:
            raise UserError(
                _("Modelo destino '%s' no existe.") % self.target_model
            )

        method = getattr(
            self.env[self.target_model],
            self.target_method,
            None,
        )
        if not method or not callable(method):
            raise UserError(
                _("Método '%s' no existe en '%s'.")
                % (self.target_method, self.target_model)
            )

        _logger.info(
            "[SAT AUTOMATION][RULE][CALL] rule_id=%s event_id=%s target=%s.%s",
            self.id, event.id, self.target_model, self.target_method,
        )

        result = method(event)

        record = False
        description = False

        if hasattr(result, "_name"):
            record = result
        elif isinstance(result, dict):
            model_name = result.get("model")
            record_id = result.get("record_id")
            description = result.get("description")
            if model_name and record_id and model_name in self.env:
                record = self.env[model_name].browse(record_id)
        elif result is True:
            description = _("Acción ejecutada correctamente.")

        if record and record.exists():
            event.link_action(
                record,
                action_type=self.action_type or "custom",
                description=description or _("Acción ejecutada."),
            )
        elif description:
            event.write({
                "action_type": self.action_type or "custom",
                "action_description": description,
            })

        return {
            "status": "executed",
            "record": record,
            "raw_result": result,
        }

    @api.model
    def find_matching_rules(self, event):
        rules = self.search([("active", "=", True)], order="sequence, id")
        matching = rules.filtered(lambda r: r.matches(event))
        _logger.info(
            "[SAT AUTOMATION][RULE][MATCH] event_id=%s rule_ids=%s",
            event.id, matching.ids,
        )
        return matching
