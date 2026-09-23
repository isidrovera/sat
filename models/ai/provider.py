# -*- coding: utf-8 -*-

import json
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SatAIProvider(models.Model):
    _name = "sat.ai.provider"
    _description = "Proveedor IA SAT"
    _order = "sequence, id"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10, index=True)

    provider_type = fields.Selection(
        [
            ("openai", "OpenAI"),
            ("openai_compatible", "OpenAI Compatible"),
            ("gemini", "Google Gemini"),
            ("anthropic", "Anthropic"),
            ("custom_http", "HTTP Personalizado"),
        ],
        required=True,
        default="openai_compatible",
    )

    base_url = fields.Char()
    api_key = fields.Char(groups="base.group_system")
    model_name = fields.Char(required=True)

    timeout_seconds = fields.Integer(default=45)
    max_retries = fields.Integer(default=2)
    retry_delay_seconds = fields.Integer(default=2)
    temperature = fields.Float(default=0.1)
    max_output_tokens = fields.Integer(default=1500)

    supports_json = fields.Boolean(default=True)
    extra_headers_json = fields.Text()

    input_cost_per_million = fields.Float(digits=(12, 6), default=0.0)
    output_cost_per_million = fields.Float(digits=(12, 6), default=0.0)

    @api.constrains(
        "timeout_seconds",
        "max_retries",
        "retry_delay_seconds",
        "max_output_tokens",
    )
    def _check_numbers(self):
        for rec in self:
            if rec.timeout_seconds <= 0:
                raise ValidationError(_("Timeout debe ser > 0."))
            if rec.max_retries < 0 or rec.retry_delay_seconds < 0:
                raise ValidationError(_("Reintentos/delay no pueden ser negativos."))
            if rec.max_output_tokens <= 0:
                raise ValidationError(_("Máximo de tokens debe ser > 0."))

    @api.constrains("extra_headers_json")
    def _check_headers_json(self):
        for rec in self:
            if not rec.extra_headers_json:
                continue
            try:
                value = json.loads(rec.extra_headers_json)
                if not isinstance(value, dict):
                    raise ValueError("Debe ser objeto JSON.")
            except Exception as exc:
                raise ValidationError(
                    _("Headers JSON inválidos: %s") % str(exc)
                )

    def get_extra_headers(self):
        self.ensure_one()
        return json.loads(self.extra_headers_json) if self.extra_headers_json else {}

    def calculate_cost(self, input_tokens=0, output_tokens=0):
        self.ensure_one()
        return (
            (float(input_tokens or 0) / 1_000_000.0)
            * (self.input_cost_per_million or 0.0)
            +
            (float(output_tokens or 0) / 1_000_000.0)
            * (self.output_cost_per_million or 0.0)
        )
