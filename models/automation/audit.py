# -*- coding: utf-8 -*-

import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SatAutomationAudit(models.Model):
    _name = "sat.automation.audit"
    _description = "Auditoría de Automatización SAT"
    _order = "create_date desc, id desc"
    _rec_name = "action"

    event_id = fields.Many2one(
        "sat.automation.event",
        string="Evento",
        required=True,
        ondelete="cascade",
        index=True,
    )
    action = fields.Char(required=True, index=True)
    level = fields.Selection(
        [
            ("debug", "Debug"),
            ("info", "Info"),
            ("warning", "Warning"),
            ("error", "Error"),
            ("critical", "Critical"),
        ],
        required=True,
        default="info",
        index=True,
    )
    message = fields.Text()
    data_json = fields.Text()
    user_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        readonly=True,
        index=True,
    )

    @api.model
    def create_log(self, event, action, level="info", message=None, data=None):
        if not event:
            return self.browse()
        try:
            rec = self.sudo().create({
                "event_id": event.id,
                "action": action,
                "level": level,
                "message": message or False,
                "data_json": json.dumps(
                    data or {}, ensure_ascii=False, default=str
                ) if data else False,
            })
            _logger.debug(
                "[SAT AUTOMATION][AUDIT] event_id=%s action=%s level=%s audit_id=%s",
                event.id, action, level, rec.id,
            )
            return rec
        except Exception:
            _logger.exception(
                "[SAT AUTOMATION][AUDIT][ERROR] event_id=%s action=%s",
                event.id if event else None, action,
            )
            return self.browse()
