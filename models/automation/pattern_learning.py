# -*- coding: utf-8 -*-

import logging
import re

from odoo import api, fields, models, _

from .constants import SOURCE_SELECTION, EVENT_TYPE_SELECTION, VALUE_TYPE_SELECTION

_logger = logging.getLogger(__name__)


class SatAutomationPatternLearning(models.Model):
    _name = "sat.automation.pattern.learning"
    _description = "Aprendizaje de patrones SAT"
    _order = "create_date desc, id desc"

    event_id = fields.Many2one(
        "sat.automation.event",
        required=True,
        ondelete="cascade",
        index=True,
    )
    pattern_id = fields.Many2one(
        "sat.automation.capture.pattern",
        ondelete="set null",
        index=True,
    )

    source = fields.Selection(SOURCE_SELECTION, required=True, index=True)
    event_type = fields.Selection(EVENT_TYPE_SELECTION, required=True, index=True)
    target_key = fields.Char(required=True, index=True)
    expected_value = fields.Char()
    extracted_value = fields.Char()

    result = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("success", "Acierto"),
            ("failure", "Fallo"),
            ("no_match", "Sin coincidencia"),
        ],
        default="pending",
        required=True,
        index=True,
    )

    notes = fields.Text()

    @api.model
    def register_ai_candidates(self, event, ai_result):
        """
        La IA puede devolver:
        {
          ...
          "learned_patterns": [
            {
              "name": "...",
              "target_key": "meter_bn",
              "regex": "...",
              "value_group": 1,
              "value_type": "integer",
              "confidence": 96,
              "sender_domain": "cliente.com"
            }
          ]
        }

        Los patrones SIEMPRE nacen como candidate.
        """
        config = self.env["sat.automation.config"].get_config()
        if not config.learning_enabled:
            return self.env["sat.automation.capture.pattern"]

        proposals = (ai_result or {}).get("learned_patterns") or []
        created = self.env["sat.automation.capture.pattern"]

        for proposal in proposals:
            regex = (proposal.get("regex") or "").strip()
            target_key = (proposal.get("target_key") or "").strip()

            if not regex or not target_key:
                continue

            # Rechazar patrones excesivamente genéricos conocidos.
            if self._is_dangerously_generic(regex, target_key):
                _logger.warning(
                    "[SAT AUTOMATION][LEARNING][REJECT_GENERIC] event_id=%s target=%s regex=%s",
                    event.id, target_key, regex,
                )
                event._audit(
                    "learning_pattern_rejected_generic",
                    level="warning",
                    message="Patrón candidato rechazado por ser demasiado genérico.",
                    data={"target_key": target_key, "regex": regex},
                )
                continue

            existing = self.env["sat.automation.capture.pattern"].search([
                ("target_key", "=", target_key),
                ("regex", "=", regex),
                ("source", "in", ["all", event.source]),
                ("state", "not in", ["rejected", "obsolete"]),
            ], limit=1)

            if existing:
                _logger.info(
                    "[SAT AUTOMATION][LEARNING][EXISTS] event_id=%s pattern_id=%s",
                    event.id, existing.id,
                )
                continue

            vals = {
                "name": proposal.get("name") or (
                    "IA %s - %s" % (target_key, event.id)
                ),
                "state": "candidate",
                "source": event.source,
                "event_type": (
                    event.event_type if event.event_type != "unknown" else False
                ),
                "target_key": target_key,
                "regex": regex,
                "value_group": int(proposal.get("value_group") or 1),
                "value_type": proposal.get("value_type") or "char",
                "sender_domain": (
                    proposal.get("sender_domain")
                    or event.sender_domain
                    or False
                ),
                "partner_id": event.partner_id.id if event.partner_id else False,
                "origin": "ai",
                "confidence": float(proposal.get("confidence") or 0.0),
                "created_from_event_id": event.id,
                "sequence": 50,
            }

            try:
                pattern = self.env["sat.automation.capture.pattern"].create(vals)
            except Exception:
                _logger.exception(
                    "[SAT AUTOMATION][LEARNING][CREATE_ERROR] event_id=%s proposal=%s",
                    event.id, proposal,
                )
                continue

            created |= pattern
            event._audit(
                "learning_pattern_candidate_created",
                message="Patrón candidato creado por IA.",
                data={
                    "pattern_id": pattern.id,
                    "target_key": target_key,
                    "regex": regex,
                },
            )

        return created

    @api.model
    def shadow_test_candidates(self, event, reference_values=None):
        """
        Evalúa candidatos sin afectar NUNCA el resultado operativo.
        reference_values proviene de:
          - resultado IA confiable,
          - extracción validada,
          - corrección manual.
        """
        config = self.env["sat.automation.config"].get_config()
        if not config.learning_enabled or not config.learning_shadow_mode:
            return True

        reference_values = reference_values or {}
        text = event.body_plain or ""

        patterns = self.env["sat.automation.capture.pattern"].search([
            ("active", "=", True),
            ("state", "in", ["candidate", "testing"]),
        ])

        for pattern in patterns:
            if not pattern.applies_to(event):
                continue
            if pattern.target_key not in reference_values:
                continue

            expected = reference_values.get(pattern.target_key)
            extracted = pattern.extract(text)

            if extracted is False:
                result = "no_match"
                success = False
            else:
                success = self._values_equal(extracted, expected)
                result = "success" if success else "failure"

            self.create({
                "event_id": event.id,
                "pattern_id": pattern.id,
                "source": event.source,
                "event_type": event.event_type,
                "target_key": pattern.target_key,
                "expected_value": str(expected),
                "extracted_value": (
                    str(extracted) if extracted is not False else False
                ),
                "result": result,
            })

            vals = {
                "tests_count": pattern.tests_count + 1,
                "last_test_at": fields.Datetime.now(),
            }
            if success:
                vals["success_count"] = pattern.success_count + 1
                vals["last_success_at"] = fields.Datetime.now()
            elif result == "failure":
                vals["failure_count"] = pattern.failure_count + 1

            if pattern.state == "candidate":
                vals["state"] = "testing"

            pattern.write(vals)

            _logger.info(
                "[SAT AUTOMATION][LEARNING][SHADOW] event_id=%s pattern_id=%s "
                "target=%s expected=%s extracted=%s result=%s",
                event.id, pattern.id, pattern.target_key,
                expected, extracted, result,
            )

            self._evaluate_promotion(pattern, config)

        return True

    @api.model
    def learn_from_manual_correction(self, event, corrected_values):
        """
        Registra corrección manual como verdad de referencia.
        No inventa regex automáticamente. Primero prueba candidatos existentes.
        La creación de nuevos candidatos puede hacerla IA en una ejecución posterior.
        """
        if not corrected_values:
            return True

        event._audit(
            "manual_correction_registered",
            message="Corrección manual registrada como referencia de aprendizaje.",
            data={"values": corrected_values},
        )
        self.shadow_test_candidates(event, corrected_values)
        return True

    @api.model
    def _evaluate_promotion(self, pattern, config):
        pattern.invalidate_recordset(
            ["tests_count", "success_count", "failure_count", "success_rate"]
        )

        tests = pattern.tests_count
        success_rate = (
            (pattern.success_count / tests) * 100.0
            if tests else 0.0
        )

        if (
            pattern.failure_count >= config.learning_reject_after_failures
            and success_rate < config.learning_min_success_rate
        ):
            pattern.write({"state": "rejected"})
            _logger.warning(
                "[SAT AUTOMATION][LEARNING][REJECT] pattern_id=%s tests=%s success_rate=%.2f failures=%s",
                pattern.id, tests, success_rate, pattern.failure_count,
            )
            return True

        if (
            config.learning_auto_promote
            and tests >= config.learning_min_tests
            and success_rate >= config.learning_min_success_rate
        ):
            pattern.write({
                "state": "active",
                "validated_at": fields.Datetime.now(),
            })
            _logger.info(
                "[SAT AUTOMATION][LEARNING][PROMOTE] pattern_id=%s tests=%s success_rate=%.2f",
                pattern.id, tests, success_rate,
            )
        return True

    @api.model
    def _values_equal(self, a, b):
        return str(a).strip().lower() == str(b).strip().lower()

    @api.model
    def _is_dangerously_generic(self, regex, target_key):
        normalized = re.sub(r"\s+", "", regex or "")

        dangerous = {
            r"(\d{4,9})",
            r"(\d+)",
            r"\b([A-Z0-9]{5,15})\b",
            r"([A-Z0-9]{5,15})",
        }

        if normalized in {re.sub(r"\s+", "", x) for x in dangerous}:
            return True

        # Para serie debe existir contexto literal suficiente.
        if target_key == "serial_number":
            literal_chars = re.sub(r"[\[\]\(\)\\\^\$\.\*\+\?\{\}\|]", "", regex or "")
            if len(literal_chars.strip()) < 4:
                return True

        return False
