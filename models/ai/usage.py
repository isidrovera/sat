# -*- coding: utf-8 -*-

from odoo import fields, models


class SatAIUsage(models.Model):
    _name = "sat.ai.usage"
    _description = "Consumo IA SAT"
    _order = "create_date desc, id desc"

    event_id = fields.Many2one(
        "sat.automation.event",
        ondelete="set null",
        index=True,
    )
    provider_id = fields.Many2one(
        "sat.ai.provider",
        required=True,
        ondelete="restrict",
        index=True,
    )
    prompt_id = fields.Many2one(
        "sat.ai.prompt",
        ondelete="set null",
    )
    model_name = fields.Char(required=True)
    task_type = fields.Char(index=True)

    input_tokens = fields.Integer(default=0)
    output_tokens = fields.Integer(default=0)
    total_cost = fields.Float(digits=(12, 8), default=0.0)

    latency_ms = fields.Integer(default=0)
    success = fields.Boolean(default=False, index=True)
    error_message = fields.Text()
