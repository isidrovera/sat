# -*- coding: utf-8 -*-

import json
import logging
import time
import traceback

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SatAutomationConfig(models.Model):
    _name = "sat.automation.config"
    _description = "Configuración de Automatización SAT"
    _rec_name = "name"

    name = fields.Char(
        default="Configuración SAT",
        required=True,
    )

    active = fields.Boolean(
        default=True,
    )

    # ============================================================
    # MOTOR DE AUTOMATIZACIÓN
    # ============================================================

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

    # ============================================================
    # APRENDIZAJE
    # ============================================================

    learning_enabled = fields.Boolean(
        string="Aprendizaje de patrones",
        default=True,
    )

    learning_shadow_mode = fields.Boolean(
        string="Probar candidatos en shadow mode",
        default=True,
        help=(
            "Los candidatos se evalúan pero nunca afectan "
            "el resultado operativo."
        ),
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

    # ============================================================
    # DIAGNÓSTICO DEL SISTEMA
    # ============================================================

    diagnostic_status = fields.Selection(
        [
            ("never", "Sin probar"),
            ("ok", "Correcto"),
            ("warning", "Con advertencias"),
            ("error", "Con errores"),
        ],
        string="Estado del diagnóstico",
        default="never",
        readonly=True,
        copy=False,
    )

    diagnostic_date = fields.Datetime(
        string="Última prueba",
        readonly=True,
        copy=False,
    )

    diagnostic_total = fields.Integer(
        string="Pruebas ejecutadas",
        readonly=True,
        copy=False,
    )

    diagnostic_ok = fields.Integer(
        string="Correctas",
        readonly=True,
        copy=False,
    )

    diagnostic_warnings = fields.Integer(
        string="Advertencias",
        readonly=True,
        copy=False,
    )

    diagnostic_errors = fields.Integer(
        string="Errores",
        readonly=True,
        copy=False,
    )

    diagnostic_duration = fields.Float(
        string="Duración (s)",
        digits=(10, 3),
        readonly=True,
        copy=False,
    )

    diagnostic_ai_provider = fields.Char(
        string="Proveedor IA probado",
        readonly=True,
        copy=False,
    )

    diagnostic_ai_model = fields.Char(
        string="Modelo IA probado",
        readonly=True,
        copy=False,
    )

    diagnostic_event_id = fields.Many2one(
        "sat.automation.event",
        string="Evento de diagnóstico",
        readonly=True,
        copy=False,
        ondelete="set null",
    )

    diagnostic_log = fields.Text(
        string="Log del diagnóstico",
        readonly=True,
        copy=False,
    )

    # ============================================================
    # VALIDACIONES
    # ============================================================

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
                        _("%s debe estar entre 0 y 100.")
                        % field_name
                    )

    @api.constrains(
        "learning_min_tests",
        "learning_reject_after_failures",
        "stuck_processing_hours",
    )
    def _check_positive_numbers(self):
        for rec in self:
            if rec.learning_min_tests < 1:
                raise ValidationError(
                    _("Pruebas mínimas debe ser >= 1.")
                )

            if rec.learning_reject_after_failures < 1:
                raise ValidationError(
                    _("Fallos para rechazar debe ser >= 1.")
                )

            if rec.stuck_processing_hours < 1:
                raise ValidationError(
                    _("Horas de bloqueo debe ser >= 1.")
                )

    # ============================================================
    # CONFIGURACIÓN ACTIVA
    # ============================================================

    @api.model
    def get_config(self):
        config = self.search(
            [("active", "=", True)],
            order="id",
            limit=1,
        )

        if not config:
            config = self.create({
                "name": "Configuración SAT",
            })

            _logger.warning(
                "[SAT AUTOMATION][CONFIG] "
                "No había configuración activa; creada id=%s",
                config.id,
            )

        return config

    # ============================================================
    # DIAGNÓSTICO
    # ============================================================

    def action_test_full_system(self):
        """
        Ejecuta un diagnóstico integral del motor SAT.

        IMPORTANTE:
        - NO ejecuta acciones productivas.
        - NO crea tickets.
        - NO crea solicitudes de tóner.
        - NO modifica contadores de equipos.
        - NO mueve stock.

        Sí realiza:
        - creación de evento de diagnóstico;
        - prueba de patrones;
        - llamada REAL al proveedor IA;
        - validación de prompts;
        - validación de reglas;
        - validación de modelos/métodos destino;
        - comprobación de auditoría;
        - comprobación del motor.
        """
        self.ensure_one()

        started = time.time()

        lines = []
        total = 0
        ok_count = 0
        warning_count = 0
        error_count = 0

        diagnostic_event = False
        ai_provider_name = False
        ai_model_name = False

        def add_ok(message):
            nonlocal total, ok_count
            total += 1
            ok_count += 1

            line = "[OK] %s" % message
            lines.append(line)

            _logger.info(
                "[SAT AUTOMATION][DIAGNOSTIC] %s",
                line,
            )

        def add_warning(message):
            nonlocal total, warning_count
            total += 1
            warning_count += 1

            line = "[WARNING] %s" % message
            lines.append(line)

            _logger.warning(
                "[SAT AUTOMATION][DIAGNOSTIC] %s",
                line,
            )

        def add_error(message):
            nonlocal total, error_count
            total += 1
            error_count += 1

            line = "[ERROR] %s" % message
            lines.append(line)

            _logger.error(
                "[SAT AUTOMATION][DIAGNOSTIC] %s",
                line,
            )

        lines.append(
            "============================================================"
        )
        lines.append(
            "DIAGNÓSTICO COMPLETO - AUTOMATIZACIÓN SAT"
        )
        lines.append(
            "============================================================"
        )
        lines.append("")

        try:
            # ====================================================
            # 1. CONFIGURACIÓN
            # ====================================================

            lines.append("=== 1. CONFIGURACIÓN ===")

            if self.active:
                add_ok(
                    "Configuración activa: %s"
                    % self.display_name
                )
            else:
                add_warning(
                    "Esta configuración está inactiva."
                )

            if self.processing_enabled:
                add_ok(
                    "Procesamiento automático habilitado."
                )
            else:
                add_warning(
                    "Procesamiento automático deshabilitado."
                )

            add_ok(
                "Modo IA configurado: %s"
                % (
                    dict(
                        self._fields["ai_mode"].selection
                    ).get(
                        self.ai_mode,
                        self.ai_mode,
                    )
                )
            )

            if self.learning_enabled:
                add_ok(
                    "Aprendizaje de patrones habilitado."
                )
            else:
                add_warning(
                    "Aprendizaje de patrones deshabilitado."
                )

            if self.learning_shadow_mode:
                add_ok(
                    "Shadow mode habilitado."
                )
            else:
                add_warning(
                    "Shadow mode deshabilitado."
                )

            lines.append("")

            # ====================================================
            # 2. MODELOS PRINCIPALES
            # ====================================================

            lines.append("=== 2. MODELOS DEL MOTOR ===")

            required_models = [
                "sat.automation.event",
                "sat.automation.audit",
                "sat.automation.config",
                "sat.automation.mail.filter",
                "sat.automation.capture.pattern",
                "sat.automation.pattern.learning",
                "sat.automation.rule",
                "sat.automation.processor",
                "sat.ai.provider",
                "sat.ai.prompt",
                "sat.ai.usage",
                "sat.ai.service",
            ]

            for model_name in required_models:
                if model_name in self.env:
                    add_ok(
                        "Modelo disponible: %s"
                        % model_name
                    )
                else:
                    add_error(
                        "Modelo NO disponible: %s"
                        % model_name
                    )

            lines.append("")

            # ====================================================
            # 3. EVENTO DE DIAGNÓSTICO
            # ====================================================

            lines.append("=== 3. EVENTO DE DIAGNÓSTICO ===")

            diagnostic_text = (
                "Prueba automática SAT. "
                "Serie TESTSAT98765. "
                "Contador B/N: 125430. "
                "Contador Color: 45670. "
                "El equipo presenta atasco de papel."
            )

            diagnostic_event = (
                self.env["sat.automation.event"]
                .sudo()
                .create({
                    "source": "system",
                    "source_subtype": "diagnostic",
                    "event_type": "unknown",
                    "sender": "diagnostico@sat.local",
                    "subject": (
                        "Prueba de diagnóstico SAT - "
                        "atasco de papel"
                    ),
                    "body_plain": diagnostic_text,
                    "body_original": diagnostic_text,
                    "payload_json": json.dumps(
                        {
                            "diagnostic": True,
                            "safe_mode": True,
                        },
                        ensure_ascii=False,
                    ),
                    "raw_payload_json": json.dumps(
                        {
                            "source": "diagnostic",
                        },
                        ensure_ascii=False,
                    ),
                })
            )

            if diagnostic_event:
                add_ok(
                    "Evento de diagnóstico creado: %s"
                    % diagnostic_event.display_name
                )
            else:
                add_error(
                    "No se pudo crear evento de diagnóstico."
                )

            lines.append("")

            # ====================================================
            # 4. AUDITORÍA
            # ====================================================

            lines.append("=== 4. AUDITORÍA ===")

            try:
                diagnostic_event._audit(
                    "system_diagnostic",
                    message=(
                        "Inicio del diagnóstico integral "
                        "del motor SAT."
                    ),
                    data={
                        "config_id": self.id,
                        "safe_mode": True,
                    },
                )

                audit_count = (
                    self.env["sat.automation.audit"]
                    .sudo()
                    .search_count([
                        (
                            "event_id",
                            "=",
                            diagnostic_event.id,
                        ),
                    ])
                )

                if audit_count:
                    add_ok(
                        "Auditoría funcionando. "
                        "Registros generados: %s"
                        % audit_count
                    )
                else:
                    add_warning(
                        "La llamada de auditoría no produjo "
                        "un registro visible."
                    )

            except Exception as exc:
                add_error(
                    "Error en auditoría: %s"
                    % exc
                )

            lines.append("")

            # ====================================================
            # 5. PROMPT IA
            # ====================================================

            lines.append("=== 5. PROMPT IA ===")

            try:
                prompt = (
                    self.env["sat.ai.prompt"]
                    .sudo()
                    .get_active_prompt(
                        "extract_event"
                    )
                )

                if prompt:
                    add_ok(
                        "Prompt activo encontrado: %s "
                        "(versión %s)"
                        % (
                            prompt.name,
                            prompt.version,
                        )
                    )
                else:
                    add_error(
                        "No se encontró prompt activo "
                        "extract_event."
                    )

            except Exception as exc:
                prompt = False

                add_error(
                    "Error buscando prompt extract_event: %s"
                    % exc
                )

            lines.append("")

            # ====================================================
            # 6. PROVEEDORES IA
            # ====================================================

            lines.append("=== 6. PROVEEDORES IA ===")

            providers = (
                self.env["sat.ai.provider"]
                .sudo()
                .search(
                    [("active", "=", True)],
                    order="sequence, id",
                )
            )

            if providers:
                add_ok(
                    "Proveedores IA activos encontrados: %s"
                    % len(providers)
                )

                for provider in providers:
                    add_ok(
                        "Proveedor: %s | tipo=%s | modelo=%s"
                        % (
                            provider.name,
                            provider.provider_type,
                            provider.model_name,
                        )
                    )

                    if provider.api_key:
                        add_ok(
                            "API key configurada para %s."
                            % provider.name
                        )
                    else:
                        add_error(
                            "Proveedor %s sin API key."
                            % provider.name
                        )

            else:
                add_error(
                    "No existen proveedores IA activos."
                )

            lines.append("")

            # ====================================================
            # 7. PATRONES PRODUCTIVOS
            # ====================================================

            lines.append("=== 7. PATRONES ===")

            try:
                pattern_model = self.env[
                    "sat.automation.capture.pattern"
                ].sudo()

                active_patterns = pattern_model.search([
                    ("active", "=", True),
                    (
                        "state",
                        "in",
                        [
                            "validated",
                            "active",
                        ],
                    ),
                ])

                add_ok(
                    "Patrones productivos disponibles: %s"
                    % len(active_patterns)
                )

                invalid_regex = []

                for pattern in active_patterns:
                    try:
                        pattern._validate_regex()
                    except Exception as exc:
                        invalid_regex.append(
                            "%s: %s"
                            % (
                                pattern.name,
                                exc,
                            )
                        )

                if invalid_regex:
                    for error in invalid_regex:
                        add_error(
                            "Regex inválido: %s"
                            % error
                        )
                else:
                    add_ok(
                        "Todos los patrones activos "
                        "tienen regex válido."
                    )

                pattern_result = (
                    pattern_model
                    .apply_active_patterns(
                        diagnostic_event,
                        text=diagnostic_text,
                    )
                )

                values = (
                    pattern_result.get("values")
                    if isinstance(
                        pattern_result,
                        dict,
                    )
                    else {}
                )

                confidence = (
                    pattern_result.get(
                        "confidence",
                        0.0,
                    )
                    if isinstance(
                        pattern_result,
                        dict,
                    )
                    else 0.0
                )

                if values:
                    add_ok(
                        "Patrones extrajeron datos: %s"
                        % json.dumps(
                            values,
                            ensure_ascii=False,
                            default=str,
                        )
                    )

                    add_ok(
                        "Confianza de patrones: %.2f%%"
                        % confidence
                    )
                else:
                    add_warning(
                        "Ningún patrón productivo coincidió "
                        "con el texto de diagnóstico. "
                        "Esto no impide probar la IA."
                    )

            except Exception as exc:
                add_error(
                    "Error probando patrones: %s"
                    % exc
                )

                _logger.exception(
                    "[SAT AUTOMATION][DIAGNOSTIC] "
                    "Error en prueba de patrones"
                )

            lines.append("")

            # ====================================================
            # 8. IA REAL
            # ====================================================

            lines.append("=== 8. INTELIGENCIA ARTIFICIAL ===")

            if self.ai_mode == "disabled":
                add_warning(
                    "IA desactivada en configuración. "
                    "No se realizó llamada externa."
                )

            else:
                try:
                    ai_result = (
                        self.env["sat.ai.service"]
                        .sudo()
                        .analyze_event(
                            diagnostic_event,
                            task_type="extract_event",
                            fail_silently=True,
                        )
                    )

                    if ai_result.get("ok"):
                        provider = ai_result.get(
                            "provider"
                        )

                        ai_provider_name = (
                            provider.name
                            if provider
                            else diagnostic_event.ai_provider_name
                        )

                        ai_model_name = (
                            provider.model_name
                            if provider
                            else diagnostic_event.ai_model_name
                        )

                        add_ok(
                            "IA respondió correctamente."
                        )

                        add_ok(
                            "Proveedor utilizado: %s"
                            % (
                                ai_provider_name
                                or "No identificado"
                            )
                        )

                        add_ok(
                            "Modelo utilizado: %s"
                            % (
                                ai_model_name
                                or "No identificado"
                            )
                        )

                        add_ok(
                            "Confianza IA: %.2f%%"
                            % (
                                diagnostic_event.ai_confidence
                                or 0.0
                            )
                        )

                        ai_data = (
                            ai_result.get("data")
                            or {}
                        )

                        if ai_data:
                            add_ok(
                                "JSON IA válido recibido."
                            )

                            lines.append(
                                json.dumps(
                                    ai_data,
                                    ensure_ascii=False,
                                    indent=2,
                                    default=str,
                                )
                            )
                        else:
                            add_warning(
                                "IA respondió OK pero sin "
                                "datos estructurados."
                            )

                        # Verificaciones útiles sobre esta prueba.
                        detected_serial = (
                            ai_data.get(
                                "serial_number"
                            )
                            if isinstance(
                                ai_data,
                                dict,
                            )
                            else False
                        )

                        if detected_serial:
                            add_ok(
                                "IA detectó serie: %s"
                                % detected_serial
                            )
                        else:
                            add_warning(
                                "IA no detectó la serie "
                                "TESTSAT98765."
                            )

                        detected_bn = (
                            ai_data.get("meter_bn")
                            if isinstance(
                                ai_data,
                                dict,
                            )
                            else False
                        )

                        if detected_bn:
                            add_ok(
                                "IA detectó contador B/N: %s"
                                % detected_bn
                            )
                        else:
                            add_warning(
                                "IA no devolvió meter_bn."
                            )

                        detected_type = (
                            ai_data.get("event_type")
                            if isinstance(
                                ai_data,
                                dict,
                            )
                            else False
                        )

                        if detected_type:
                            add_ok(
                                "IA clasificó evento como: %s"
                                % detected_type
                            )
                        else:
                            add_warning(
                                "IA no devolvió event_type."
                            )

                    else:
                        add_error(
                            "La prueba IA falló: %s"
                            % (
                                ai_result.get("error")
                                or "Error desconocido"
                            )
                        )

                except Exception as exc:
                    add_error(
                        "Excepción probando IA: %s"
                        % exc
                    )

                    _logger.exception(
                        "[SAT AUTOMATION][DIAGNOSTIC] "
                        "Error en prueba IA"
                    )

            lines.append("")

            # ====================================================
            # 9. REGLAS
            # ====================================================

            lines.append("=== 9. REGLAS ===")

            try:
                rules = (
                    self.env["sat.automation.rule"]
                    .sudo()
                    .search(
                        [("active", "=", True)],
                        order="sequence, id",
                    )
                )

                if rules:
                    add_ok(
                        "Reglas activas encontradas: %s"
                        % len(rules)
                    )
                else:
                    add_warning(
                        "No existen reglas activas."
                    )

                target_errors = 0

                for rule in rules:
                    if rule.action_mode != "model_method":
                        continue

                    if rule.target_model not in self.env:
                        target_errors += 1

                        add_error(
                            "Regla '%s': modelo destino "
                            "'%s' no existe."
                            % (
                                rule.name,
                                rule.target_model,
                            )
                        )

                        continue

                    method = getattr(
                        self.env[rule.target_model],
                        rule.target_method,
                        None,
                    )

                    if not method or not callable(method):
                        target_errors += 1

                        add_error(
                            "Regla '%s': método %s.%s "
                            "no existe."
                            % (
                                rule.name,
                                rule.target_model,
                                rule.target_method,
                            )
                        )
                    else:
                        add_ok(
                            "Destino válido: %s.%s"
                            % (
                                rule.target_model,
                                rule.target_method,
                            )
                        )

                if not target_errors:
                    add_ok(
                        "Todos los métodos destino "
                        "de reglas son válidos."
                    )

            except Exception as exc:
                add_error(
                    "Error validando reglas: %s"
                    % exc
                )

            lines.append("")

            # ====================================================
            # 10. MATCHING DE REGLAS EN MODO SEGURO
            # ====================================================

            lines.append(
                "=== 10. MATCHING DE REGLAS - SIN EJECUTAR ==="
            )

            try:
                # Utilizamos la clasificación devuelta por IA
                # solamente para comprobar matching.
                if diagnostic_event.ai_raw_response:
                    pass

                if (
                    diagnostic_event.ai_used
                    and diagnostic_event.ai_confidence
                ):
                    diagnostic_event.write({
                        "classification_method": "ai",
                    })

                matching_rules = (
                    self.env["sat.automation.rule"]
                    .sudo()
                    .find_matching_rules(
                        diagnostic_event
                    )
                )

                if matching_rules:
                    add_ok(
                        "Reglas compatibles encontradas: %s"
                        % ", ".join(
                            matching_rules.mapped(
                                "name"
                            )
                        )
                    )
                else:
                    add_warning(
                        "El evento de diagnóstico no "
                        "coincidió con ninguna regla. "
                        "No se ejecutó ninguna acción."
                    )

                add_ok(
                    "Modo seguro confirmado: "
                    "ninguna regla fue ejecutada."
                )

            except Exception as exc:
                add_error(
                    "Error comprobando matching: %s"
                    % exc
                )

            lines.append("")

            # ====================================================
            # 11. USO IA
            # ====================================================

            lines.append("=== 11. REGISTRO DE CONSUMO IA ===")

            try:
                usage_count = (
                    self.env["sat.ai.usage"]
                    .sudo()
                    .search_count([
                        (
                            "event_id",
                            "=",
                            diagnostic_event.id,
                        ),
                    ])
                )

                if (
                    self.ai_mode != "disabled"
                    and usage_count
                ):
                    add_ok(
                        "Consumo IA registrado: %s "
                        "llamada(s)."
                        % usage_count
                    )

                elif self.ai_mode == "disabled":
                    add_warning(
                        "No hay consumo IA porque está "
                        "desactivada."
                    )

                else:
                    add_warning(
                        "No se encontró registro "
                        "sat.ai.usage para la prueba."
                    )

            except Exception as exc:
                add_error(
                    "Error verificando consumo IA: %s"
                    % exc
                )

            lines.append("")

            # ====================================================
            # 12. CRON / RECUPERACIÓN
            # ====================================================

            lines.append("=== 12. RECUPERACIÓN DE EVENTOS ===")

            try:
                cron_method = getattr(
                    self.env["sat.automation.event"],
                    "cron_recover_stuck_events",
                    None,
                )

                if cron_method and callable(cron_method):
                    add_ok(
                        "Método cron_recover_stuck_events "
                        "disponible."
                    )
                else:
                    add_error(
                        "Método cron_recover_stuck_events "
                        "no disponible."
                    )

            except Exception as exc:
                add_error(
                    "Error comprobando cron: %s"
                    % exc
                )

        except Exception as exc:
            add_error(
                "ERROR CRÍTICO DEL DIAGNÓSTICO: %s"
                % exc
            )

            lines.append("")
            lines.append(traceback.format_exc())

            _logger.exception(
                "[SAT AUTOMATION][DIAGNOSTIC] "
                "Error crítico"
            )

        # ========================================================
        # RESULTADO FINAL
        # ========================================================

        duration = time.time() - started

        if error_count:
            status = "error"
        elif warning_count:
            status = "warning"
        else:
            status = "ok"

        lines.append("")
        lines.append(
            "============================================================"
        )
        lines.append("RESULTADO FINAL")
        lines.append(
            "============================================================"
        )
        lines.append(
            "Pruebas ejecutadas: %s"
            % total
        )
        lines.append(
            "Correctas: %s"
            % ok_count
        )
        lines.append(
            "Advertencias: %s"
            % warning_count
        )
        lines.append(
            "Errores: %s"
            % error_count
        )
        lines.append(
            "Duración: %.3f segundos"
            % duration
        )

        if diagnostic_event:
            lines.append(
                "Evento diagnóstico: %s (ID %s)"
                % (
                    diagnostic_event.display_name,
                    diagnostic_event.id,
                )
            )

        self.write({
            "diagnostic_status": status,
            "diagnostic_date": fields.Datetime.now(),
            "diagnostic_total": total,
            "diagnostic_ok": ok_count,
            "diagnostic_warnings": warning_count,
            "diagnostic_errors": error_count,
            "diagnostic_duration": duration,
            "diagnostic_ai_provider": (
                ai_provider_name
                or (
                    diagnostic_event.ai_provider_name
                    if diagnostic_event
                    else False
                )
            ),
            "diagnostic_ai_model": (
                ai_model_name
                or (
                    diagnostic_event.ai_model_name
                    if diagnostic_event
                    else False
                )
            ),
            "diagnostic_event_id": (
                diagnostic_event.id
                if diagnostic_event
                else False
            ),
            "diagnostic_log": "\n".join(lines),
        })

        _logger.info(
            "[SAT AUTOMATION][DIAGNOSTIC][END] "
            "config=%s status=%s total=%s ok=%s "
            "warnings=%s errors=%s duration=%.3fs",
            self.id,
            status,
            total,
            ok_count,
            warning_count,
            error_count,
            duration,
        )

        notification_type = {
            "ok": "success",
            "warning": "warning",
            "error": "danger",
        }.get(
            status,
            "info",
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _(
                    "Diagnóstico de Automatización SAT"
                ),
                "message": _(
                    "%s correctas, %s advertencias, "
                    "%s errores. Revise la pestaña "
                    "Diagnóstico para ver el detalle."
                )
                % (
                    ok_count,
                    warning_count,
                    error_count,
                ),
                "type": notification_type,
                "sticky": error_count > 0,
                "next": {
                    "type": "ir.actions.act_window",
                    "res_model": "sat.automation.config",
                    "res_id": self.id,
                    "view_mode": "form",
                    "target": "current",
                },
            },
        }

    # ============================================================
    # ABRIR EVENTO DE DIAGNÓSTICO
    # ============================================================

    def action_open_diagnostic_event(self):
        self.ensure_one()

        if not self.diagnostic_event_id:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Diagnóstico"),
                    "message": _(
                        "Todavía no existe un evento "
                        "de diagnóstico."
                    ),
                    "type": "warning",
                    "sticky": False,
                },
            }

        return {
            "type": "ir.actions.act_window",
            "name": _("Evento de diagnóstico"),
            "res_model": "sat.automation.event",
            "res_id": self.diagnostic_event_id.id,
            "view_mode": "form",
            "target": "current",
        }