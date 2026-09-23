# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SatAutomationConfig(models.Model):
    _name = "sat.automation.config"
    _description = "Configuración de Automatización SAT"
    _rec_name = "name"

    name = fields.Char(default="Configuración SAT", required=True)
    active = fields.Boolean(default=True)

    processing_enabled = fields.Boolean(
        string="Procesamiento automático",
        default=True,
    )

    ai_mode = fields.Selection(
        [
            ("disabled", "Desactivada"),
            ("fallback", "Fallback"),
            ("preferred", "Preferida"),
        ],
        string="Modo IA",
        default="fallback",
        required=True,
        help=(
            "Desactivada: nunca usa IA. "
            "Fallback: usa IA solo cuando reglas/patrones no bastan. "
            "Preferida: usa IA para enriquecer incluso si hay patrones."
        ),
    )

    ai_failure_policy = fields.Selection(
        [
            ("continue", "Continuar si hay datos suficientes"),
            ("review", "Enviar a revisión si faltan datos"),
        ],
        string="Si IA falla",
        default="continue",
        required=True,
    )

    min_pattern_confidence = fields.Float(
        string="Confianza mínima de patrones (%)",
        default=90.0,
    )
    min_ai_confidence = fields.Float(
        string="Confianza mínima IA (%)",
        default=85.0,
    )

    learning_enabled = fields.Boolean(
        string="Aprendizaje de patrones",
        default=True,
    )
    learning_shadow_mode = fields.Boolean(
        string="Probar candidatos en shadow mode",
        default=True,
        help="Los candidatos se evalúan pero nunca afectan el resultado operativo.",
    )
    learning_auto_promote = fields.Boolean(
        string="Promover patrones automáticamente",
        default=True,
    )
    learning_min_tests = fields.Integer(
        string="Pruebas mínimas para promover",
        default=5,
    )
    learning_min_success_rate = fields.Float(
        string="Tasa mínima para promover (%)",
        default=95.0,
    )
    learning_reject_after_failures = fields.Integer(
        string="Fallos para rechazar candidato",
        default=5,
    )

    stuck_processing_hours = fields.Integer(
        string="Horas para considerar evento bloqueado",
        default=2,
    )

    @api.constrains(
        "min_pattern_confidence",
        "min_ai_confidence",
        "learning_min_success_rate",
    )
    def _check_percentages(self):
        for rec in self:
            for field_name in (
                "min_pattern_confidence",
                "min_ai_confidence",
                "learning_min_success_rate",
            ):
                value = rec[field_name]
                if value < 0 or value > 100:
                    raise ValidationError(
                        _("%s debe estar entre 0 y 100.") % field_name
                    )

    @api.constrains(
        "learning_min_tests",
        "learning_reject_after_failures",
        "stuck_processing_hours",
    )
    def _check_positive_numbers(self):
        for rec in self:
            if rec.learning_min_tests < 1:
                raise ValidationError(_("Pruebas mínimas debe ser >= 1."))
            if rec.learning_reject_after_failures < 1:
                raise ValidationError(_("Fallos para rechazar debe ser >= 1."))
            if rec.stuck_processing_hours < 1:
                raise ValidationError(_("Horas de bloqueo debe ser >= 1."))

    @api.model
    def get_config(self):
        config = self.search([("active", "=", True)], order="id", limit=1)
        if not config:
            config = self.create({"name": "Configuración SAT"})
            _logger.warning(
                "[SAT AUTOMATION][CONFIG] No había configuración activa; creada id=%s",
                config.id,
            )
        return config
