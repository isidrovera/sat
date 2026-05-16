# -*- coding: utf-8 -*-

import logging
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class WhatsappIntentRule(models.Model):
    _name = "whatsapp.intent.rule"
    _description = "Regla de intención WhatsApp"
    _order = "priority desc, sequence asc, name asc"

    # ==========================================================
    # Identificación
    # ==========================================================
    name = fields.Char(
        string="Nombre",
        required=True,
        index=True,
    )

    active = fields.Boolean(
        string="Activo",
        default=True,
        index=True,
    )

    sequence = fields.Integer(
        string="Secuencia",
        default=10,
    )

    priority = fields.Integer(
        string="Prioridad",
        default=10,
        help="Mayor prioridad se evalúa primero.",
    )

    # ==========================================================
    # Intención y acción
    # ==========================================================
    intent = fields.Selection(
        selection=[
            ("greeting", "Saludo"),
            ("service", "Servicio técnico general"),
            ("onsite_service", "Servicio presencial"),
            ("remote_service", "Soporte remoto"),
            ("anydesk", "AnyDesk / conexión remota"),
            ("toner", "Tóner / suministros"),
            ("scanner", "Escáner / configuración"),
            ("printer_issue", "Problema impresión"),
            ("billing", "Facturación"),
            ("sales", "Ventas"),
            ("rental", "Alquiler"),
            ("human", "Solicita humano"),
            ("thanks", "Agradecimiento"),
            ("goodbye", "Despedida"),
            ("confirmation", "Confirmación (sí/ok)"),
            ("negation", "Negación (no)"),
            ("cancel", "Cancelar flujo"),
            ("menu_option", "Opción de menú"),
            ("dni", "DNI"),
            ("ruc", "RUC"),
            ("company_selection", "Selección de empresa"),
            ("urgent", "Urgente"),
            ("unknown", "Desconocido"),
        ],
        string="Intención",
        required=True,
        default="unknown",
        index=True,
    )

    action = fields.Selection(
        selection=[
            ("reply", "Responder"),
            ("start_flow_toner", "Iniciar flujo tóner"),
            ("start_flow_onsite", "Iniciar flujo servicio presencial"),
            ("start_flow_remote", "Iniciar flujo soporte remoto"),
            ("ask_dni", "Pedir DNI"),
            ("ask_ruc", "Pedir RUC"),
            ("select_company", "Seleccionar empresa"),
            ("create_ticket", "Crear ticket"),
            ("send_service_link", "Enviar link de servicio"),
            ("handoff", "Derivar a humano"),
            ("cancel_flow", "Cancelar flujo activo"),
            ("ai", "Usar IA"),
            ("ignore", "Ignorar"),
        ],
        string="Acción sugerida",
        default="ai",
        required=True,
        index=True,
    )

    target_flow = fields.Selection(
        selection=[
            ("none", "Ninguno"),
            ("registration", "Registro"),
            ("toner", "Solicitud de tóner"),
            ("onsite", "Servicio presencial"),
            ("remote", "Soporte remoto"),
            ("greeting", "Saludo"),
            ("other", "Otro"),
        ],
        string="Flujo destino",
        default="none",
        index=True,
        help="Si la acción inicia un flujo, qué flujo arrancar.",
    )

    response_template = fields.Char(
        string="Plantilla de respuesta",
        help="Nombre técnico de whatsapp.template a usar si action=reply.",
    )

    # ==========================================================
    # Coincidencia
    # ==========================================================
    match_type = fields.Selection(
        selection=[
            ("exact", "Exacto"),
            ("contains", "Contiene"),
            ("starts_with", "Empieza con"),
            ("ends_with", "Termina con"),
            ("regex", "Regex"),
            ("word", "Palabra completa"),
        ],
        string="Tipo coincidencia",
        default="contains",
        required=True,
    )

    pattern = fields.Char(
        string="Patrón",
        required=True,
        help="Texto, palabra clave o expresión regular según el tipo de coincidencia.",
    )

    case_sensitive = fields.Boolean(
        string="Sensible a mayúsculas",
        default=False,
    )

    min_message_length = fields.Integer(
        string="Largo mínimo mensaje",
        default=0,
        help="Si > 0, el mensaje debe tener al menos esa longitud para evaluar la regla.",
    )

    max_message_length = fields.Integer(
        string="Largo máximo mensaje",
        default=0,
        help="Si > 0, el mensaje no debe superar esa longitud.",
    )

    confidence_score = fields.Float(
        string="Score de confianza",
        default=1.0,
        digits=(3, 2),
        help="Confianza asignada cuando esta regla matchea (0.00 a 1.00).",
    )

    # ==========================================================
    # Aplicabilidad
    # ==========================================================
    applies_to = fields.Selection(
        selection=[
            ("all", "Todos"),
            ("new", "Contactos nuevos"),
            ("registered", "Registrados"),
            ("blocked", "Bloqueados"),
            ("human", "Modo humano"),
            ("after_hours", "Fuera de horario"),
        ],
        string="Aplica a",
        default="all",
        required=True,
        index=True,
    )

    requires_registered = fields.Boolean(
        string="Requiere registrado",
        default=False,
    )

    requires_company = fields.Boolean(
        string="Requiere empresa activa",
        default=False,
    )

    only_during_business_hours = fields.Boolean(
        string="Solo en horario laboral",
        default=False,
    )

    only_during_idle = fields.Boolean(
        string="Solo si no hay flujo activo",
        default=False,
        help="Si True, la regla solo se evalúa cuando el cliente no está en medio de un flujo conversacional.",
    )

    applies_to_flows = fields.Char(
        string="Aplica a flujos",
        help="Lista de flujos separados por coma donde esta regla aplica (toner,onsite,remote). Vacío = todos.",
    )

    # ==========================================================
    # Control de flujo
    # ==========================================================
    stop_flow = fields.Boolean(
        string="Cortar flujo",
        default=False,
    )

    allow_ai_after = fields.Boolean(
        string="Permitir IA después",
        default=True,
    )

    cancels_active_flow = fields.Boolean(
        string="Cancela flujo activo",
        default=False,
        help="Si True, al matchear esta regla se cancela el flujo conversacional activo.",
    )

    # ==========================================================
    # Notas y métricas
    # ==========================================================
    note = fields.Text(string="Notas internas")

    description = fields.Text(
        string="Descripción",
        help="Para qué sirve esta regla (visible para administradores).",
    )

    last_used_at = fields.Datetime(
        string="Último uso",
        readonly=True,
    )

    use_count = fields.Integer(
        string="Cantidad de usos",
        default=0,
        readonly=True,
    )

    last_matched_message = fields.Text(
        string="Último mensaje que matcheó",
        readonly=True,
    )

    # ==========================================================
    # SQL constraints
    # ==========================================================
    _sql_constraints = [
        (
            "unique_intent_rule_name",
            "unique(name)",
            "Ya existe una regla de intención con ese nombre.",
        ),
    ]

    # ==========================================================
    # Constraints
    # ==========================================================
    @api.constrains("match_type", "pattern")
    def _check_pattern_validity(self):
        for rule in self:
            if rule.match_type == "regex":
                try:
                    re.compile(rule.pattern or "")
                except re.error as e:
                    _logger.error(
                        "[WA-INTENT] Regex inválido en regla id=%s pattern=%r error=%s",
                        rule.id, rule.pattern, str(e),
                    )
                    raise ValidationError(_(
                        "El patrón regex no es válido en la regla '%s': %s"
                    ) % (rule.name, str(e)))

    @api.constrains("confidence_score")
    def _check_confidence_score(self):
        for rule in self:
            if rule.confidence_score < 0 or rule.confidence_score > 1:
                raise ValidationError(_(
                    "El score de confianza debe estar entre 0.00 y 1.00 (regla: %s)."
                ) % rule.name)

    @api.constrains("min_message_length", "max_message_length")
    def _check_message_length_bounds(self):
        for rule in self:
            if rule.max_message_length > 0 and rule.min_message_length > rule.max_message_length:
                raise ValidationError(_(
                    "El largo mínimo no puede ser mayor al largo máximo (regla: %s)."
                ) % rule.name)

    # ==========================================================
    # Helpers
    # ==========================================================
    def _normalize_text(self, text):
        return (text or "").strip().lower()

    def _get_applies_to_flows_list(self):
        self.ensure_one()
        if not self.applies_to_flows:
            return []
        return [f.strip().lower() for f in self.applies_to_flows.split(",") if f.strip()]

    def _match_text(self, message):
        self.ensure_one()

        if not message:
            return False

        # Validar longitud del mensaje
        msg_len = len(message)
        if self.min_message_length > 0 and msg_len < self.min_message_length:
            return False
        if self.max_message_length > 0 and msg_len > self.max_message_length:
            return False

        if self.case_sensitive:
            message_cmp = (message or "").strip()
            pattern_cmp = (self.pattern or "").strip()
            regex_flags = 0
        else:
            message_cmp = self._normalize_text(message)
            pattern_cmp = self._normalize_text(self.pattern)
            regex_flags = re.IGNORECASE

        if not message_cmp or not pattern_cmp:
            return False

        try:
            if self.match_type == "exact":
                return message_cmp == pattern_cmp

            if self.match_type == "contains":
                return pattern_cmp in message_cmp

            if self.match_type == "starts_with":
                return message_cmp.startswith(pattern_cmp)

            if self.match_type == "ends_with":
                return message_cmp.endswith(pattern_cmp)

            if self.match_type == "word":
                # Palabra completa con límites
                pattern_escaped = re.escape(pattern_cmp)
                return bool(re.search(
                    r"\b" + pattern_escaped + r"\b",
                    message_cmp,
                    flags=regex_flags,
                ))

            if self.match_type == "regex":
                return bool(re.search(self.pattern, message or "", flags=regex_flags))

        except Exception as e:
            _logger.exception(
                "[WA-INTENT] Error matcheando regla id=%s name=%s error=%s",
                self.id, self.name, str(e),
            )
            return False

        return False

    def _is_applicable(self, applies_to=False, is_after_hours=False, current_flow=False):
        """Verifica si la regla aplica al contexto actual."""
        self.ensure_one()

        # Filtro por applies_to
        if applies_to and self.applies_to not in ("all", applies_to):
            return False

        # Solo en horario laboral
        if self.only_during_business_hours and is_after_hours:
            return False

        # Solo en idle
        if self.only_during_idle and current_flow and current_flow != "none":
            return False

        # Filtro por flujos específicos
        if current_flow and current_flow != "none":
            flows_filter = self._get_applies_to_flows_list()
            if flows_filter and current_flow.lower() not in flows_filter:
                return False

        return True

    # ==========================================================
    # Create / Write
    # ==========================================================
    @api.model_create_multi
    def create(self, vals_list):
        rules = super().create(vals_list)
        for rule in rules:
            _logger.info(
                "[WA-INTENT] Regla creada id=%s name=%s intent=%s action=%s pattern=%r",
                rule.id, rule.name, rule.intent, rule.action, rule.pattern,
            )
        return rules

    def write(self, vals):
        result = super().write(vals)
        if any(k in vals for k in ("pattern", "match_type", "intent", "action", "active")):
            for rule in self:
                _logger.info(
                    "[WA-INTENT] Regla modificada id=%s name=%s intent=%s action=%s active=%s",
                    rule.id, rule.name, rule.intent, rule.action, rule.active,
                )
        return result

    # ==========================================================
    # Detección de intent
    # ==========================================================
    @api.model
    def detect_intent(self, message, partner=False, applies_to=False, is_after_hours=False, current_flow=False):
        if not message:
            _logger.debug("[WA-INTENT] detect_intent sin mensaje")
            return {
                "found": False,
                "intent": "unknown",
                "action": "ai",
                "confidence_score": 0.0,
            }

        _logger.debug(
            "[WA-INTENT] detect_intent message=%r applies_to=%s after_hours=%s flow=%s",
            (message[:80] + "...") if len(message) > 80 else message,
            applies_to, is_after_hours, current_flow,
        )

        domain = [("active", "=", True)]

        rules = self.search(domain, order="priority desc, sequence asc, name asc")

        _logger.debug("[WA-INTENT] Evaluando %s reglas activas", len(rules))

        for rule in rules:
            try:
                if not rule._is_applicable(
                    applies_to=applies_to,
                    is_after_hours=is_after_hours,
                    current_flow=current_flow,
                ):
                    continue

                if not rule._match_text(message):
                    continue

                # Match encontrado
                try:
                    rule.sudo().write({
                        "last_used_at": fields.Datetime.now(),
                        "use_count": rule.use_count + 1,
                        "last_matched_message": (message[:500] if message else False),
                    })
                except Exception as e:
                    _logger.warning(
                        "[WA-INTENT] No se pudo actualizar métricas regla id=%s error=%s",
                        rule.id, str(e),
                    )

                _logger.info(
                    "[WA-INTENT] Match: regla=%s intent=%s action=%s score=%s",
                    rule.name, rule.intent, rule.action, rule.confidence_score,
                )

                return {
                    "found": True,
                    "rule_id": rule.id,
                    "name": rule.name,
                    "intent": rule.intent,
                    "action": rule.action,
                    "target_flow": rule.target_flow,
                    "response_template": rule.response_template or False,
                    "requires_registered": rule.requires_registered,
                    "requires_company": rule.requires_company,
                    "stop_flow": rule.stop_flow,
                    "allow_ai_after": rule.allow_ai_after,
                    "cancels_active_flow": rule.cancels_active_flow,
                    "confidence_score": rule.confidence_score,
                }

            except Exception as e:
                _logger.exception(
                    "[WA-INTENT] Error evaluando regla id=%s name=%s error=%s",
                    rule.id, rule.name, str(e),
                )
                continue

        _logger.info(
            "[WA-INTENT] Sin match para message=%r",
            (message[:80] + "...") if len(message) > 80 else message,
        )

        return {
            "found": False,
            "intent": "unknown",
            "action": "ai",
            "confidence_score": 0.0,
        }

    @api.model
    def detect_intent_with_alternatives(self, message, partner=False, applies_to=False,
                                        is_after_hours=False, current_flow=False, max_alternatives=3):
        """
        Devuelve la mejor match y alternativas (útil para Gemini como árbitro).
        """
        if not message:
            return {"found": False, "matches": []}

        domain = [("active", "=", True)]
        rules = self.search(domain, order="priority desc, sequence asc, name asc")

        matches = []

        for rule in rules:
            try:
                if not rule._is_applicable(
                    applies_to=applies_to,
                    is_after_hours=is_after_hours,
                    current_flow=current_flow,
                ):
                    continue

                if not rule._match_text(message):
                    continue

                matches.append({
                    "rule_id": rule.id,
                    "name": rule.name,
                    "intent": rule.intent,
                    "action": rule.action,
                    "target_flow": rule.target_flow,
                    "confidence_score": rule.confidence_score,
                    "priority": rule.priority,
                })

                if len(matches) >= max_alternatives:
                    break

            except Exception as e:
                _logger.exception(
                    "[WA-INTENT] Error en alternatives regla id=%s error=%s",
                    rule.id, str(e),
                )

        _logger.info(
            "[WA-INTENT] detect_intent_with_alternatives: %s matches",
            len(matches),
        )

        return {
            "found": bool(matches),
            "matches": matches,
        }

    # ==========================================================
    # Acciones backend
    # ==========================================================
    def action_test_pattern(self):
        """Acción manual para probar el patrón contra un texto de ejemplo."""
        self.ensure_one()
        _logger.info(
            "[WA-INTENT] Test manual de regla id=%s name=%s",
            self.id, self.name,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Regla: %s") % self.name,
                "message": _(
                    "Patrón: %s\nTipo: %s\nIntent: %s\nAcción: %s\n\n"
                    "Para probar contra un texto, usa el método detect_intent desde la API."
                ) % (self.pattern, self.match_type, self.intent, self.action),
                "type": "info",
                "sticky": True,
            },
        }

    def action_reset_use_count(self):
        for rule in self:
            _logger.info(
                "[WA-INTENT] Reset use_count regla id=%s previo=%s",
                rule.id, rule.use_count,
            )
            rule.write({
                "use_count": 0,
                "last_used_at": False,
                "last_matched_message": False,
            })
        return True

    def action_toggle_active(self):
        for rule in self:
            rule.active = not rule.active
            _logger.info(
                "[WA-INTENT] Toggle active regla id=%s name=%s active=%s",
                rule.id, rule.name, rule.active,
            )
        return True