# -*- coding: utf-8 -*-

import logging

from odoo import api, models, _

_logger = logging.getLogger(__name__)


class SatAutomationProcessor(models.AbstractModel):
    _name = "sat.automation.processor"
    _description = "Motor central de automatización SAT"

    OPERATIONAL_KEYS = {
        "event_type",
        "event_subtype",
        "serial_number",
        "meter_bn",
        "meter_color",
        "meter_scan",
        "meter_total",
        "supply_type",
        "supply_color",
        "supply_percentage",
        "requested_quantity",
        "issue_description",
        "error_code",
        "location_detected",
    }

    @api.model
    def process(self, event):
        event.ensure_one()
        config = self.env["sat.automation.config"].get_config()

        if not config.processing_enabled:
            _logger.info(
                "[SAT AUTOMATION][PROCESSOR][DISABLED] event_id=%s",
                event.id,
            )
            return True

        if event.state in ("done", "ignored", "cancelled"):
            _logger.info(
                "[SAT AUTOMATION][PROCESSOR][SKIP] event_id=%s state=%s",
                event.id, event.state,
            )
            return True

        try:
            event.mark_processing()
            event.resolve_equipment()

            mail_filter = self._apply_mail_filter(event)
            if event.state in ("ignored", "review"):
                return True

            pattern_result = self._apply_patterns(
                event,
                mail_filter=mail_filter,
            )

            pattern_values = pattern_result.get("values") or {}
            if pattern_values:
                self._apply_values(
                    event,
                    pattern_values,
                    source="pattern",
                )

            # IA NUNCA es una dependencia obligatoria.
            ai_result = {"ok": False, "data": {}}
            ai_mode = self._resolve_ai_mode(config, mail_filter)

            if self._should_use_ai(
                event,
                config=config,
                ai_mode=ai_mode,
                pattern_result=pattern_result,
            ):
                ai_result = self.env["sat.ai.service"].analyze_event(
                    event,
                    task_type="extract_event",
                    fail_silently=True,
                )

                if ai_result.get("ok"):
                    ai_data = ai_result.get("data") or {}
                    self._apply_values(
                        event,
                        ai_data,
                        source="ai",
                    )

                    # Crear candidatos DESPUÉS de obtener resultado IA.
                    # No participan en el procesamiento actual.
                    self.env[
                        "sat.automation.pattern.learning"
                    ].register_ai_candidates(event, ai_data)

                    # Prueba shadow usando la IA como referencia.
                    self.env[
                        "sat.automation.pattern.learning"
                    ].shadow_test_candidates(event, ai_data)

                else:
                    event._audit(
                        "ai_unavailable_continue",
                        level="warning",
                        message=(
                            "IA no disponible; el flujo continúa con "
                            "reglas/patrones."
                        ),
                        data={"error": ai_result.get("error")},
                    )

            # Si IA no fue usada o falló, candidatos existentes pueden probarse
            # contra valores confiables ya obtenidos por patrones/reglas.
            if pattern_values:
                self.env[
                    "sat.automation.pattern.learning"
                ].shadow_test_candidates(event, pattern_values)

            event.resolve_equipment()

            sufficient, missing = self._has_sufficient_data(event)

            if not sufficient:
                # No bloquear jamás el flujo por aprendizaje.
                event.mark_review(
                    _(
                        "Faltan datos esenciales para procesar: %s"
                    ) % ", ".join(missing)
                )
                return True

            rules = self.env["sat.automation.rule"].find_matching_rules(event)

            if not rules:
                event.mark_review(
                    _("No existe una regla activa aplicable.")
                )
                return True

            for rule in rules:
                if rule.duplicate_window_hours:
                    duplicate = self.env[
                        "sat.automation.deduplication"
                    ].find_event_with_action(
                        event,
                        hours=rule.duplicate_window_hours,
                        event_types=[event.event_type],
                    )
                    if duplicate:
                        event.mark_review(
                            _(
                                "Existe una acción previa relacionada en evento %s."
                            ) % duplicate.display_name
                        )
                        return True

                result = rule.execute(event)

                if event.state in ("review", "ignored", "error"):
                    return True

                if rule.stop_after_match:
                    break

            if event.action_model or event.action_description:
                event.mark_done(
                    event.action_description
                    or _("Procesado correctamente.")
                )
            else:
                event.mark_review(
                    _(
                        "Las reglas fueron evaluadas pero no se confirmó "
                        "ninguna acción."
                    )
                )

            _logger.info(
                "[SAT AUTOMATION][PROCESSOR][DONE] event_id=%s state=%s "
                "action_model=%s action_id=%s",
                event.id, event.state,
                event.action_model, event.action_record_id,
            )
            return True

        except Exception as exc:
            _logger.exception(
                "[SAT AUTOMATION][PROCESSOR][ERROR] event_id=%s",
                event.id,
            )
            event.mark_error(str(exc), exception=exc)
            return False

    @api.model
    def _apply_mail_filter(self, event):
        if event.source != "email":
            return self.env["sat.automation.mail.filter"]

        rec = self.env["sat.automation.mail.filter"].evaluate_event(event)

        if not rec:
            return rec

        if rec.action == "ignore":
            event.mark_ignored(
                _("Ignorado por filtro '%s'.") % rec.name
            )
            return rec

        if rec.action == "review":
            event.mark_review(
                _("Enviado a revisión por filtro '%s'.") % rec.name
            )
            return rec

        if rec.expected_event_type and event.event_type == "unknown":
            event.write({
                "event_type": rec.expected_event_type,
                "classification_method": "filter",
            })

        return rec

    @api.model
    def _apply_patterns(self, event, mail_filter=None):
        use_patterns = True
        if mail_filter:
            use_patterns = mail_filter.use_patterns

        if not use_patterns or event.source != "email":
            return {"values": {}, "patterns": [], "confidence": 0.0}

        return self.env[
            "sat.automation.capture.pattern"
        ].apply_active_patterns(event)

    @api.model
    def _resolve_ai_mode(self, config, mail_filter=None):
        if mail_filter and mail_filter.ai_mode_override != "inherit":
            return mail_filter.ai_mode_override
        return config.ai_mode

    @api.model
    def _should_use_ai(
        self,
        event,
        config,
        ai_mode,
        pattern_result=None,
    ):
        if ai_mode == "disabled":
            return False

        if event.source == "printtracker":
            # Datos estructurados no necesitan IA salvo que sigan desconocidos.
            return event.event_type == "unknown" and ai_mode == "preferred"

        if ai_mode == "preferred":
            return True

        pattern_result = pattern_result or {}
        confidence = float(pattern_result.get("confidence") or 0.0)

        if event.event_type == "unknown":
            return True

        if not self._has_sufficient_data(event)[0]:
            return True

        return (
            bool(pattern_result.get("values"))
            and confidence < config.min_pattern_confidence
        )

    @api.model
    def _apply_values(self, event, values, source):
        if not values:
            return True

        vals = {}
        for key, value in values.items():
            if key in self.OPERATIONAL_KEYS and value is not None:
                vals[key] = value

        if vals:
            event.write(vals)

        payload = event.get_payload()
        payload.setdefault("extraction_sources", {})
        payload["extraction_sources"][source] = values
        event.set_payload(payload)

        if source == "ai":
            if event.patterns_used:
                event.classification_method = "combined"
            else:
                event.classification_method = "ai"
        elif source == "pattern":
            event.classification_method = "pattern"

        if event.event_type != "unknown":
            event.state = "classified"

        event._audit(
            "values_applied",
            message="Valores aplicados al evento.",
            data={"source": source, "values": vals},
        )

        return True

    @api.model
    def _has_sufficient_data(self, event):
        """
        Define mínimos para actuar. No obliga a IA.
        """
        missing = []

        if event.event_type == "unknown":
            missing.append("tipo de evento")
            return False, missing

        equipment_required_types = {
            "meter_reading",
            "toner_request",
            "toner_low",
            "toner_critical",
            "toner_empty",
            "toner_replaced",
            "technical_issue",
            "paper_jam",
            "device_error",
            "connectivity_issue",
            "maintenance",
            "replacement_request",
        }

        if event.event_type in equipment_required_types:
            if not event.equipment_id and not event.serial_number:
                missing.append("equipo/serie")

        if event.event_type == "meter_reading":
            if not any([
                event.meter_bn,
                event.meter_color,
                event.meter_scan,
                event.meter_total,
            ]):
                missing.append("contador")

        if event.event_type == "toner_request":
            if not event.supply_color or event.supply_color == "unknown":
                missing.append("color de tóner")

        if event.event_type in {
            "technical_issue",
            "paper_jam",
            "device_error",
            "connectivity_issue",
        }:
            if not (
                event.issue_description
                or event.error_code
                or event.event_type != "technical_issue"
            ):
                missing.append("descripción/código de incidencia")

        return not missing, missing
