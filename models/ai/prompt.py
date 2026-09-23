# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SatAIPrompt(models.Model):
    _name = "sat.ai.prompt"
    _description = "Prompt IA SAT"
    _order = "task_type, sequence, id"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    task_type = fields.Selection(
        [
            ("extract_event", "Extraer/clasificar evento"),
            ("suggest_patterns", "Proponer patrones"),
            ("generic", "Genérico"),
        ],
        required=True,
        index=True,
    )

    version = fields.Char(required=True, default="1")
    system_prompt = fields.Text(required=True)
    user_template = fields.Text(required=True)
    expected_json_schema = fields.Text()

    @api.model
    def get_active_prompt(self, task_type):
        prompt = self.search([
            ("active", "=", True),
            ("task_type", "=", task_type),
        ], order="sequence, id", limit=1)

        if not prompt:
            raise ValidationError(
                _("No existe prompt activo para '%s'.") % task_type
            )
        return prompt
