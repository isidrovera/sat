# -*- coding: utf-8 -*-

import json
import logging
import re
import time
import traceback
from uuid import uuid4

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


class SatAutomationConfig(models.Model):
    _name = "sat.automation.config"
    _description = "Configuración de Automatización SAT"
    _rec_name = "name"

    # ============================================================
    # CONFIGURACIÓN GENERAL
    # ============================================================

    name = fields.Char(
        string="Nombre",
        default="Configuración SAT",
        required=True,
    )

    active = fields.Boolean(
        string="Activo",
        default=True,
    )

    processing_enabled = fields.Boolean(
        string="Procesamiento automático",
        default=True,
    )

    # ============================================================
    # INTELIGENCIA ARTIFICIAL
    # ============================================================

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
    # DIAGNÓSTICO
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
    # HELPERS DE DIAGNÓSTICO
    # ============================================================

    @api.model
    def _diagnostic_selection_values(self, model, field_name):
        """
        Devuelve los valores internos disponibles en un Selection.

        Se usa únicamente para hacer el diagnóstico tolerante a cambios
        en las selecciones del modelo.
        """
        field = model._fields.get(field_name)

        if not field:
            return []

        selection = getattr(field, "selection", None)

        if not selection:
            return []

        try:
            if callable(selection):
                selection = selection(model)
        except Exception:
            _logger.exception(
                "[SAT AUTOMATION][DIAGNOSTIC] "
                "No se pudo resolver selection del campo %s.%s",
                model._name,
                field_name,
            )
            return []

        try:
            return [
                item[0]
                for item in selection
                if isinstance(item, (list, tuple))
                and len(item) >= 2
            ]
        except Exception:
            return []

    @api.model
    def _diagnostic_safe_value(
        self,
        model,
        field_name,
        preferred,
        fallback=None,
    ):
        """
        Devuelve preferred si es válido para un Selection.

        Si el campo no es Selection, devuelve preferred.
        """
        field = model._fields.get(field_name)

        if not field:
            return False

        if getattr(field, "type", None) != "selection":
            return preferred

        values = self._diagnostic_selection_values(
            model,
            field_name,
        )

        if preferred in values:
            return preferred

        if fallback and fallback in values:
            return fallback

        if values:
            return values[0]

        return False

    @api.model
    def _diagnostic_model_available(self, model_name):
        try:
            return model_name in self.env
        except Exception:
            return False

    # ============================================================
    # DIAGNÓSTICO COMPLETO
    # ============================================================

    def action_test_full_system(self):
        """
        Diagnóstico integral del sistema SAT Automation.

        La prueba está diseñada para ser SEGURA:

        - No crea tickets reales.
        - No crea solicitudes reales de tóner.
        - No modifica contadores de equipos.
        - No mueve stock.
        - No ejecuta métodos destino de las reglas.

        Sí prueba:

        - configuración;
        - modelos instalados;
        - creación de evento;
        - fingerprint/deduplicación;
        - auditoría;
        - prompts;
        - proveedores IA;
        - llamada real a IA;
        - patrones;
        - reglas;
        - existencia de métodos destino;
        - consumo IA;
        - cron/recuperación.
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

        # --------------------------------------------------------
        # Helpers de salida
        # --------------------------------------------------------

        def add_ok(message):
            nonlocal total
            nonlocal ok_count

            total += 1
            ok_count += 1

            line = "[OK] %s" % message
            lines.append(line)

            _logger.info(
                "[SAT AUTOMATION][DIAGNOSTIC] %s",
                line,
            )

        def add_warning(message):
            nonlocal total
            nonlocal warning_count

            total += 1
            warning_count += 1

            line = "[WARNING] %s" % message
            lines.append(line)

            _logger.warning(
                "[SAT AUTOMATION][DIAGNOSTIC] %s",
                line,
            )

        def add_error(message):
            nonlocal total
            nonlocal error_count

            total += 1
            error_count += 1

            line = "[ERROR] %s" % message
            lines.append(line)

            _logger.error(
                "[SAT AUTOMATION][DIAGNOSTIC] %s",
                line,
            )

        # --------------------------------------------------------
        # Inicio
        # --------------------------------------------------------

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

        _logger.info(
            "[SAT AUTOMATION][DIAGNOSTIC][START] "
            "config_id=%s",
            self.id,
        )

        # ========================================================
        # 1. CONFIGURACIÓN
        # ========================================================

        lines.append("=== 1. CONFIGURACIÓN ===")

        if self.active:
            add_ok(
                "Configuración activa: %s"
                % self.display_name
            )
        else:
            add_warning(
                "La configuración está inactiva."
            )

        if self.processing_enabled:
            add_ok(
                "Procesamiento automático habilitado."
            )
        else:
            add_warning(
                "Procesamiento automático deshabilitado."
            )

        ai_label = dict(
            self._fields["ai_mode"].selection
        ).get(
            self.ai_mode,
            self.ai_mode,
        )

        add_ok(
            "Modo IA configurado: %s"
            % ai_label
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

        # ========================================================
        # 2. MODELOS
        # ========================================================

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

        missing_models = []

        for model_name in required_models:
            if self._diagnostic_model_available(
                model_name
            ):
                add_ok(
                    "Modelo disponible: %s"
                    % model_name
                )
            else:
                missing_models.append(model_name)

                add_error(
                    "Modelo NO disponible: %s"
                    % model_name
                )

        lines.append("")

        # ========================================================
        # 3. EVENTO DE DIAGNÓSTICO
        # ========================================================

        lines.append(
            "=== 3. EVENTO DE DIAGNÓSTICO ==="
        )

        if "sat.automation.event" not in self.env:
            add_error(
                "No es posible continuar con el evento "
                "porque sat.automation.event no está disponible."
            )

        else:
            Event = self.env[
                "sat.automation.event"
            ].sudo()

            # NUEVO:
            # cada ejecución utiliza un token distinto.
            # Esto evita volver a generar el mismo fingerprint.
            diagnostic_token = uuid4().hex

            diagnostic_text = (
                "Prueba automática SAT. "
                "Token diagnóstico: %s. "
                "Serie TESTSAT98765. "
                "Contador B/N: 125430. "
                "Contador Color: 45670. "
                "El equipo presenta atasco de papel."
            ) % diagnostic_token

            event_vals = {}

            # ----------------------------------------------------
            # Solo escribir campos que realmente existan.
            # ----------------------------------------------------

            if "source" in Event._fields:
                source_value = self._diagnostic_safe_value(
                    Event,
                    "source",
                    "manual",
                    "api",
                )

                if source_value:
                    event_vals["source"] = source_value

            if "source_subtype" in Event._fields:
                event_vals[
                    "source_subtype"
                ] = "diagnostic"

            if "external_id" in Event._fields:
                event_vals[
                    "external_id"
                ] = (
                    "SAT-DIAGNOSTIC-%s"
                    % diagnostic_token
                )

            if "source_uid" in Event._fields:
                event_vals[
                    "source_uid"
                ] = (
                    "SAT-DIAGNOSTIC-%s"
                    % diagnostic_token
                )

            if "event_type" in Event._fields:
                event_type_value = (
                    self._diagnostic_safe_value(
                        Event,
                        "event_type",
                        "unknown",
                        "notification",
                    )
                )

                if event_type_value:
                    event_vals[
                        "event_type"
                    ] = event_type_value

            if "sender" in Event._fields:
                event_vals[
                    "sender"
                ] = "diagnostico@sat.local"

            if "subject" in Event._fields:
                event_vals["subject"] = (
                    "Prueba diagnóstico SAT - %s"
                    % diagnostic_token
                )

            if "body_plain" in Event._fields:
                event_vals[
                    "body_plain"
                ] = diagnostic_text

            if "body_original" in Event._fields:
                event_vals[
                    "body_original"
                ] = diagnostic_text

            if "event_datetime" in Event._fields:
                event_vals[
                    "event_datetime"
                ] = fields.Datetime.now()

            payload = {
                "diagnostic": True,
                "safe_mode": True,
                "diagnostic_token": diagnostic_token,
                "test_serial": "TESTSAT98765",
                "test_meter_bn": 125430,
                "test_meter_color": 45670,
                "test_issue": "atasco de papel",
            }

            if "payload_json" in Event._fields:
                event_vals[
                    "payload_json"
                ] = json.dumps(
                    payload,
                    ensure_ascii=False,
                )

            if "raw_payload_json" in Event._fields:
                event_vals[
                    "raw_payload_json"
                ] = json.dumps(
                    payload,
                    ensure_ascii=False,
                )

            try:
                # MUY IMPORTANTE:
                #
                # Si PostgreSQL lanza cualquier error durante
                # create(), el savepoint evita que toda la
                # transacción quede en estado abortado.
                with self.env.cr.savepoint():
                    diagnostic_event = (
                        Event.with_context(
                            sat_automation_diagnostic=True,
                            automation_diagnostic=True,
                            skip_automation_processing=True,
                            skip_auto_process=True,
                        )
                        .create(event_vals)
                    )

                if diagnostic_event:
                    add_ok(
                        "Evento de diagnóstico creado: "
                        "%s (ID %s)"
                        % (
                            diagnostic_event.display_name,
                            diagnostic_event.id,
                        )
                    )

                    add_ok(
                        "Token único de diagnóstico: %s"
                        % diagnostic_token
                    )

                    if (
                        "fingerprint"
                        in diagnostic_event._fields
                    ):
                        add_ok(
                            "Fingerprint generado: %s"
                            % (
                                diagnostic_event.fingerprint
                                or "vacío"
                            )
                        )

            except Exception as exc:
                diagnostic_event = False

                add_error(
                    "No se pudo crear el evento "
                    "de diagnóstico: %s"
                    % exc
                )

                _logger.exception(
                    "[SAT AUTOMATION][DIAGNOSTIC] "
                    "Error creando evento diagnóstico"
                )

        lines.append("")

        # ========================================================
        # 4. AUDITORÍA
        # ========================================================

        lines.append("=== 4. AUDITORÍA ===")

        if not diagnostic_event:
            add_warning(
                "Prueba de auditoría omitida porque "
                "no existe evento de diagnóstico."
            )

        elif "sat.automation.audit" not in self.env:
            add_error(
                "Modelo sat.automation.audit "
                "no disponible."
            )

        else:
            audit_done = False

            # ----------------------------------------------------
            # Primera posibilidad: método del evento
            # ----------------------------------------------------

            audit_method = getattr(
                diagnostic_event,
                "_audit",
                None,
            )

            if callable(audit_method):
                try:
                    with self.env.cr.savepoint():
                        try:
                            audit_method(
                                "system_diagnostic",
                                message=(
                                    "Prueba integral del "
                                    "motor SAT."
                                ),
                                data={
                                    "safe_mode": True,
                                    "config_id": self.id,
                                },
                            )
                        except TypeError:
                            audit_method(
                                "system_diagnostic"
                            )

                    audit_done = True

                    add_ok(
                        "Auditoría mediante "
                        "sat.automation.event._audit()."
                    )

                except Exception as exc:
                    add_warning(
                        "_audit() existe pero la prueba "
                        "no pudo completarse: %s"
                        % exc
                    )

            # ----------------------------------------------------
            # Segunda posibilidad: modelo de auditoría
            # ----------------------------------------------------

            if not audit_done:
                Audit = self.env[
                    "sat.automation.audit"
                ].sudo()

                create_log = getattr(
                    Audit,
                    "create_log",
                    None,
                )

                if callable(create_log):
                    try:
                        with self.env.cr.savepoint():
                            try:
                                create_log(
                                    event=diagnostic_event,
                                    action="system_diagnostic",
                                    message=(
                                        "Prueba integral SAT."
                                    ),
                                )
                            except TypeError:
                                try:
                                    create_log(
                                        diagnostic_event,
                                        "system_diagnostic",
                                        "Prueba integral SAT.",
                                    )
                                except TypeError:
                                    create_log(
                                        diagnostic_event
                                    )

                        audit_done = True

                        add_ok(
                            "Auditoría mediante "
                            "sat.automation.audit.create_log()."
                        )

                    except Exception as exc:
                        add_warning(
                            "create_log() existe pero no "
                            "aceptó la llamada de prueba: %s"
                            % exc
                        )

            if not audit_done:
                add_warning(
                    "No se encontró un método público "
                    "de auditoría compatible para "
                    "ejecutar la prueba."
                )

        lines.append("")

        # ========================================================
        # 5. PROMPTS
        # ========================================================

        lines.append("=== 5. PROMPTS IA ===")

        prompt = False

        if "sat.ai.prompt" not in self.env:
            add_error(
                "Modelo sat.ai.prompt no disponible."
            )

        else:
            Prompt = self.env[
                "sat.ai.prompt"
            ].sudo()

            try:
                domain = []

                if "active" in Prompt._fields:
                    domain.append(
                        ("active", "=", True)
                    )

                if "task_type" in Prompt._fields:
                    domain.append(
                        (
                            "task_type",
                            "=",
                            "extract_event",
                        )
                    )

                prompt = Prompt.search(
                    domain,
                    order="id",
                    limit=1,
                )

                if prompt:
                    version = (
                        prompt.version
                        if "version" in prompt._fields
                        else ""
                    )

                    add_ok(
                        "Prompt activo encontrado: "
                        "%s%s"
                        % (
                            prompt.display_name,
                            (
                                " | versión %s"
                                % version
                            )
                            if version
                            else "",
                        )
                    )

                    if (
                        "system_prompt"
                        in prompt._fields
                        and prompt.system_prompt
                    ):
                        add_ok(
                            "System prompt configurado."
                        )
                    else:
                        add_warning(
                            "System prompt vacío "
                            "o no disponible."
                        )

                    if (
                        "user_template"
                        in prompt._fields
                        and prompt.user_template
                    ):
                        add_ok(
                            "User template configurado."
                        )
                    else:
                        add_warning(
                            "User template vacío "
                            "o no disponible."
                        )

                else:
                    add_error(
                        "No se encontró un prompt activo "
                        "para extract_event."
                    )

            except Exception as exc:
                add_error(
                    "Error comprobando prompts: %s"
                    % exc
                )

                _logger.exception(
                    "[SAT AUTOMATION][DIAGNOSTIC] "
                    "Error comprobando prompts"
                )

        lines.append("")

        # ========================================================
        # 6. PROVEEDORES IA
        # ========================================================

        lines.append("=== 6. PROVEEDORES IA ===")

        providers = False

        if "sat.ai.provider" not in self.env:
            add_error(
                "Modelo sat.ai.provider no disponible."
            )

        else:
            Provider = self.env[
                "sat.ai.provider"
            ].sudo()

            try:
                domain = []

                if "active" in Provider._fields:
                    domain.append(
                        ("active", "=", True)
                    )

                order_parts = []

                if "sequence" in Provider._fields:
                    order_parts.append("sequence")

                order_parts.append("id")

                providers = Provider.search(
                    domain,
                    order=", ".join(order_parts),
                )

                if not providers:
                    if self.ai_mode == "disabled":
                        add_warning(
                            "No existen proveedores IA "
                            "activos, pero la IA está "
                            "desactivada."
                        )
                    else:
                        add_error(
                            "No existen proveedores IA "
                            "activos."
                        )

                else:
                    add_ok(
                        "Proveedores IA activos: %s"
                        % len(providers)
                    )

                    for provider in providers:
                        provider_type = (
                            provider.provider_type
                            if "provider_type"
                            in provider._fields
                            else ""
                        )

                        model_name = (
                            provider.model_name
                            if "model_name"
                            in provider._fields
                            else ""
                        )

                        add_ok(
                            "Proveedor: %s | tipo=%s "
                            "| modelo=%s"
                            % (
                                provider.display_name,
                                provider_type or "-",
                                model_name or "-",
                            )
                        )

                        if "api_key" in provider._fields:
                            if provider.api_key:
                                add_ok(
                                    "API key configurada "
                                    "para %s."
                                    % provider.display_name
                                )
                            else:
                                add_error(
                                    "Proveedor %s "
                                    "sin API key."
                                    % provider.display_name
                                )

            except Exception as exc:
                add_error(
                    "Error comprobando proveedores IA: %s"
                    % exc
                )

                _logger.exception(
                    "[SAT AUTOMATION][DIAGNOSTIC] "
                    "Error comprobando proveedores"
                )

        lines.append("")

        # ========================================================
        # 7. PATRONES
        # ========================================================

        lines.append("=== 7. PATRONES ===")

        if (
            "sat.automation.capture.pattern"
            not in self.env
        ):
            add_error(
                "Modelo sat.automation.capture.pattern "
                "no disponible."
            )

        else:
            Pattern = self.env[
                "sat.automation.capture.pattern"
            ].sudo()

            try:
                pattern_domain = []

                if "active" in Pattern._fields:
                    pattern_domain.append(
                        ("active", "=", True)
                    )

                active_patterns = Pattern.search(
                    pattern_domain
                )

                add_ok(
                    "Patrones activos encontrados: %s"
                    % len(active_patterns)
                )

                invalid_patterns = []

                for pattern in active_patterns:
                    regex_value = False

                    for regex_field in (
                        "regex",
                        "pattern_regex",
                        "patron_regex",
                        "pattern",
                    ):
                        if (
                            regex_field
                            in pattern._fields
                        ):
                            regex_value = (
                                pattern[
                                    regex_field
                                ]
                            )

                            if regex_value:
                                break

                    if not regex_value:
                        continue

                    try:
                        re.compile(regex_value)
                    except Exception as exc:
                        invalid_patterns.append(
                            "%s: %s"
                            % (
                                pattern.display_name,
                                exc,
                            )
                        )

                if invalid_patterns:
                    for item in invalid_patterns:
                        add_error(
                            "Regex inválido: %s"
                            % item
                        )
                else:
                    add_ok(
                        "Los regex disponibles "
                        "compilan correctamente."
                    )

                # -----------------------------------------------
                # Probar motor real de patrones si existe.
                # -----------------------------------------------

                apply_patterns = getattr(
                    Pattern,
                    "apply_active_patterns",
                    None,
                )

                if (
                    diagnostic_event
                    and callable(apply_patterns)
                ):
                    try:
                        with self.env.cr.savepoint():
                            try:
                                pattern_result = (
                                    apply_patterns(
                                        diagnostic_event,
                                        text=(
                                            diagnostic_event.body_plain
                                            if (
                                                "body_plain"
                                                in diagnostic_event._fields
                                            )
                                            else ""
                                        ),
                                    )
                                )
                            except TypeError:
                                pattern_result = (
                                    apply_patterns(
                                        diagnostic_event
                                    )
                                )

                        if pattern_result:
                            add_ok(
                                "Motor de patrones respondió."
                            )

                            lines.append(
                                "Resultado patrones: %s"
                                % json.dumps(
                                    pattern_result,
                                    ensure_ascii=False,
                                    default=str,
                                )
                            )
                        else:
                            add_warning(
                                "Motor de patrones respondió "
                                "sin coincidencias."
                            )

                    except Exception as exc:
                        add_warning(
                            "No se pudo ejecutar "
                            "apply_active_patterns(): %s"
                            % exc
                        )

                else:
                    add_warning(
                        "No existe método "
                        "apply_active_patterns() "
                        "o no existe evento de prueba."
                    )

            except Exception as exc:
                add_error(
                    "Error comprobando patrones: %s"
                    % exc
                )

                _logger.exception(
                    "[SAT AUTOMATION][DIAGNOSTIC] "
                    "Error comprobando patrones"
                )

        lines.append("")

        # ========================================================
        # 8. PRUEBA REAL DE IA
        # ========================================================

        lines.append(
            "=== 8. INTELIGENCIA ARTIFICIAL ==="
        )

        ai_data = {}

        if self.ai_mode == "disabled":
            add_warning(
                "La IA está desactivada. "
                "No se realizó llamada externa."
            )

        elif not diagnostic_event:
            add_error(
                "No se puede probar IA porque "
                "no existe evento de diagnóstico."
            )

        elif "sat.ai.service" not in self.env:
            add_error(
                "Modelo sat.ai.service no disponible."
            )

        else:
            AIService = self.env[
                "sat.ai.service"
            ].sudo()

            analyze_event = getattr(
                AIService,
                "analyze_event",
                None,
            )

            if not callable(analyze_event):
                add_error(
                    "sat.ai.service no tiene "
                    "método analyze_event()."
                )

            else:
                try:
                    with self.env.cr.savepoint():
                        # Primera firma esperada.
                        try:
                            ai_result = analyze_event(
                                diagnostic_event,
                                task_type="extract_event",
                                fail_silently=True,
                            )

                        # Fallback si el servicio tiene
                        # una firma más simple.
                        except TypeError:
                            try:
                                ai_result = analyze_event(
                                    diagnostic_event,
                                    task_type="extract_event",
                                )

                            except TypeError:
                                ai_result = analyze_event(
                                    diagnostic_event
                                )

                    if not ai_result:
                        add_error(
                            "La IA no devolvió resultado."
                        )

                    elif isinstance(
                        ai_result,
                        dict,
                    ):
                        # ---------------------------------------
                        # Diferentes servicios pueden devolver:
                        #
                        # {ok: True, data: {...}}
                        # o directamente {...}
                        # ---------------------------------------

                        if (
                            "ok" in ai_result
                            and not ai_result.get("ok")
                        ):
                            add_error(
                                "La IA reportó error: %s"
                                % (
                                    ai_result.get("error")
                                    or "sin detalle"
                                )
                            )

                        else:
                            add_ok(
                                "La IA respondió "
                                "correctamente."
                            )

                            ai_data = (
                                ai_result.get("data")
                                if isinstance(
                                    ai_result.get("data"),
                                    dict,
                                )
                                else ai_result
                            )

                            provider_obj = (
                                ai_result.get(
                                    "provider"
                                )
                            )

                            if (
                                provider_obj
                                and hasattr(
                                    provider_obj,
                                    "display_name",
                                )
                            ):
                                ai_provider_name = (
                                    provider_obj.display_name
                                )

                                if (
                                    "model_name"
                                    in provider_obj._fields
                                ):
                                    ai_model_name = (
                                        provider_obj.model_name
                                    )

                            if (
                                not ai_provider_name
                                and diagnostic_event
                            ):
                                if (
                                    "ai_provider_name"
                                    in diagnostic_event._fields
                                ):
                                    ai_provider_name = (
                                        diagnostic_event.ai_provider_name
                                    )

                                if (
                                    "ai_model_name"
                                    in diagnostic_event._fields
                                ):
                                    ai_model_name = (
                                        diagnostic_event.ai_model_name
                                    )

                            if ai_provider_name:
                                add_ok(
                                    "Proveedor utilizado: %s"
                                    % ai_provider_name
                                )

                            if ai_model_name:
                                add_ok(
                                    "Modelo utilizado: %s"
                                    % ai_model_name
                                )

                            lines.append(
                                "Respuesta IA:"
                            )

                            lines.append(
                                json.dumps(
                                    ai_data,
                                    ensure_ascii=False,
                                    indent=2,
                                    default=str,
                                )
                            )

                            # -----------------------------------
                            # Comprobar datos esperados.
                            # -----------------------------------

                            if isinstance(
                                ai_data,
                                dict,
                            ):
                                serial = (
                                    ai_data.get(
                                        "serial_number"
                                    )
                                )

                                meter_bn = (
                                    ai_data.get(
                                        "meter_bn"
                                    )
                                )

                                event_type = (
                                    ai_data.get(
                                        "event_type"
                                    )
                                )

                                if serial:
                                    add_ok(
                                        "IA detectó serie: %s"
                                        % serial
                                    )
                                else:
                                    add_warning(
                                        "IA no devolvió "
                                        "serial_number."
                                    )

                                if meter_bn not in (
                                    None,
                                    False,
                                    "",
                                ):
                                    add_ok(
                                        "IA detectó B/N: %s"
                                        % meter_bn
                                    )
                                else:
                                    add_warning(
                                        "IA no devolvió "
                                        "meter_bn."
                                    )

                                if event_type:
                                    add_ok(
                                        "IA clasificó como: %s"
                                        % event_type
                                    )
                                else:
                                    add_warning(
                                        "IA no devolvió "
                                        "event_type."
                                    )

                                # -------------------------------
                                # Copiar SOLAMENTE al evento
                                # diagnóstico.
                                #
                                # Esto permite posteriormente
                                # probar matching de reglas.
                                # -------------------------------

                                event_updates = {}

                                safe_ai_fields = (
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
                                )

                                for key in safe_ai_fields:
                                    if (
                                        key
                                        in diagnostic_event._fields
                                        and key in ai_data
                                        and ai_data[key]
                                        is not None
                                    ):
                                        event_updates[
                                            key
                                        ] = ai_data[key]

                                if (
                                    event_type
                                    and "event_type"
                                    in diagnostic_event._fields
                                ):
                                    valid_types = (
                                        self._diagnostic_selection_values(
                                            diagnostic_event,
                                            "event_type",
                                        )
                                    )

                                    if (
                                        not valid_types
                                        or event_type
                                        in valid_types
                                    ):
                                        event_updates[
                                            "event_type"
                                        ] = event_type

                                if event_updates:
                                    with self.env.cr.savepoint():
                                        diagnostic_event.write(
                                            event_updates
                                        )

                                    add_ok(
                                        "Resultado IA aplicado "
                                        "al evento de diagnóstico."
                                    )

                    else:
                        add_warning(
                            "La IA respondió con un tipo "
                            "no esperado: %s"
                            % type(ai_result).__name__
                        )

                except Exception as exc:
                    add_error(
                        "Excepción durante prueba IA: %s"
                        % exc
                    )

                    _logger.exception(
                        "[SAT AUTOMATION][DIAGNOSTIC] "
                        "Error probando IA"
                    )

        lines.append("")

        # ========================================================
        # 9. REGLAS
        # ========================================================

        lines.append("=== 9. REGLAS ===")

        if "sat.automation.rule" not in self.env:
            add_error(
                "Modelo sat.automation.rule "
                "no disponible."
            )

        else:
            Rule = self.env[
                "sat.automation.rule"
            ].sudo()

            try:
                rule_domain = []

                if "active" in Rule._fields:
                    rule_domain.append(
                        ("active", "=", True)
                    )

                order = (
                    "sequence, id"
                    if "sequence" in Rule._fields
                    else "id"
                )

                rules = Rule.search(
                    rule_domain,
                    order=order,
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
                checked_targets = 0

                for rule in rules:
                    action_mode = (
                        rule.action_mode
                        if "action_mode"
                        in rule._fields
                        else False
                    )

                    if (
                        action_mode
                        and action_mode
                        != "model_method"
                    ):
                        continue

                    target_model = (
                        rule.target_model
                        if "target_model"
                        in rule._fields
                        else False
                    )

                    target_method = (
                        rule.target_method
                        if "target_method"
                        in rule._fields
                        else False
                    )

                    if (
                        not target_model
                        or not target_method
                    ):
                        continue

                    checked_targets += 1

                    if target_model not in self.env:
                        target_errors += 1

                        add_error(
                            "Regla '%s': modelo "
                            "destino '%s' no existe."
                            % (
                                rule.display_name,
                                target_model,
                            )
                        )

                        continue

                    method = getattr(
                        self.env[target_model],
                        target_method,
                        None,
                    )

                    if not callable(method):
                        target_errors += 1

                        add_error(
                            "Regla '%s': método "
                            "%s.%s no existe."
                            % (
                                rule.display_name,
                                target_model,
                                target_method,
                            )
                        )

                    else:
                        add_ok(
                            "Destino válido: %s.%s"
                            % (
                                target_model,
                                target_method,
                            )
                        )

                if (
                    checked_targets
                    and not target_errors
                ):
                    add_ok(
                        "Todos los métodos destino "
                        "revisados existen."
                    )

            except Exception as exc:
                add_error(
                    "Error validando reglas: %s"
                    % exc
                )

                _logger.exception(
                    "[SAT AUTOMATION][DIAGNOSTIC] "
                    "Error validando reglas"
                )

        lines.append("")

        # ========================================================
        # 10. MATCHING DE REGLAS
        # ========================================================

        lines.append(
            "=== 10. MATCHING DE REGLAS "
            "(SIN EJECUTAR ACCIONES) ==="
        )

        if not diagnostic_event:
            add_warning(
                "Matching omitido porque no existe "
                "evento de diagnóstico."
            )

        elif "sat.automation.rule" not in self.env:
            add_warning(
                "Matching omitido porque el modelo "
                "de reglas no está disponible."
            )

        else:
            Rule = self.env[
                "sat.automation.rule"
            ].sudo()

            find_matching_rules = getattr(
                Rule,
                "find_matching_rules",
                None,
            )

            if not callable(find_matching_rules):
                add_warning(
                    "sat.automation.rule no tiene "
                    "find_matching_rules()."
                )

            else:
                try:
                    with self.env.cr.savepoint():
                        matching_rules = (
                            find_matching_rules(
                                diagnostic_event
                            )
                        )

                    if matching_rules:
                        try:
                            names = ", ".join(
                                matching_rules.mapped(
                                    "name"
                                )
                            )
                        except Exception:
                            names = str(
                                matching_rules
                            )

                        add_ok(
                            "Reglas compatibles: %s"
                            % names
                        )

                    else:
                        add_warning(
                            "El evento de prueba no "
                            "coincidió con ninguna regla."
                        )

                    # IMPORTANTE:
                    # NO ejecutar reglas aquí.
                    add_ok(
                        "Modo seguro confirmado: "
                        "ninguna acción productiva "
                        "fue ejecutada."
                    )

                except Exception as exc:
                    add_error(
                        "Error comprobando matching: %s"
                        % exc
                    )

        lines.append("")

        # ========================================================
        # 11. CONSUMO IA
        # ========================================================

        lines.append(
            "=== 11. REGISTRO DE CONSUMO IA ==="
        )

        if "sat.ai.usage" not in self.env:
            add_error(
                "Modelo sat.ai.usage no disponible."
            )

        elif not diagnostic_event:
            add_warning(
                "No se puede verificar consumo "
                "porque no existe evento."
            )

        else:
            Usage = self.env[
                "sat.ai.usage"
            ].sudo()

            try:
                usage_domain = []

                if "event_id" in Usage._fields:
                    usage_domain.append(
                        (
                            "event_id",
                            "=",
                            diagnostic_event.id,
                        )
                    )

                if not usage_domain:
                    add_warning(
                        "sat.ai.usage no tiene event_id; "
                        "no se puede relacionar la prueba "
                        "de forma segura."
                    )

                else:
                    usage_count = (
                        Usage.search_count(
                            usage_domain
                        )
                    )

                    if usage_count:
                        add_ok(
                            "Consumo IA registrado: %s"
                            % usage_count
                        )

                    elif self.ai_mode == "disabled":
                        add_warning(
                            "Sin consumo porque IA "
                            "está desactivada."
                        )

                    else:
                        add_warning(
                            "No se encontró consumo IA "
                            "asociado al evento."
                        )

            except Exception as exc:
                add_error(
                    "Error comprobando consumo IA: %s"
                    % exc
                )

        lines.append("")

        # ========================================================
        # 12. CRON / RECUPERACIÓN
        # ========================================================

        lines.append(
            "=== 12. RECUPERACIÓN DE EVENTOS ==="
        )

        if "sat.automation.event" not in self.env:
            add_error(
                "No se puede revisar cron porque "
                "sat.automation.event no existe."
            )

        else:
            Event = self.env[
                "sat.automation.event"
            ]

            possible_cron_methods = [
                "cron_recover_stuck_events",
                "_cron_recover_stuck_events",
                "cron_recover_stuck",
            ]

            found_cron_method = False

            for method_name in possible_cron_methods:
                method = getattr(
                    Event,
                    method_name,
                    None,
                )

                if callable(method):
                    found_cron_method = method_name
                    break

            if found_cron_method:
                add_ok(
                    "Método de recuperación disponible: %s"
                    % found_cron_method
                )
            else:
                add_warning(
                    "No se encontró un método de "
                    "recuperación conocido en "
                    "sat.automation.event."
                )

        lines.append("")

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

            if (
                "fingerprint"
                in diagnostic_event._fields
            ):
                lines.append(
                    "Fingerprint: %s"
                    % (
                        diagnostic_event.fingerprint
                        or "-"
                    )
                )

        lines.append("")
        lines.append(
            "IMPORTANTE:"
        )
        lines.append(
            "El diagnóstico NO ejecutó acciones "
            "productivas de reglas."
        )

        # ========================================================
        # GUARDAR DIAGNÓSTICO
        # ========================================================

        try:
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
                    or False
                ),
                "diagnostic_ai_model": (
                    ai_model_name
                    or False
                ),
                "diagnostic_event_id": (
                    diagnostic_event.id
                    if diagnostic_event
                    else False
                ),
                "diagnostic_log": "\n".join(
                    lines
                ),
            })

        except Exception:
            _logger.exception(
                "[SAT AUTOMATION][DIAGNOSTIC] "
                "No se pudo guardar resultado final"
            )

            raise

        _logger.info(
            "[SAT AUTOMATION][DIAGNOSTIC][END] "
            "config=%s status=%s total=%s "
            "ok=%s warnings=%s errors=%s "
            "duration=%.3fs",
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

        # ========================================================
        # IMPORTANTE ODOO 18
        #
        # NO usar "next" aquí.
        #
        # El anterior "next" dentro de display_notification
        # provocaba:
        #
        # Cannot read properties of undefined (reading 'map')
        #
        # porque el cliente web intentaba preprocesar una acción
        # anidada incompleta.
        # ========================================================

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _(
                    "Diagnóstico de Automatización SAT"
                ),
                "message": _(
                    "%s correctas, "
                    "%s advertencias, "
                    "%s errores. "
                    "Revise la pestaña Diagnóstico."
                )
                % (
                    ok_count,
                    warning_count,
                    error_count,
                ),
                "type": notification_type,
                "sticky": (
                    error_count > 0
                ),
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

            # Odoo 18:
            # usamos views explícitamente.
            "views": [
                (False, "form"),
            ],

            "target": "current",
        }