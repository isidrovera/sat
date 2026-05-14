# -*- coding: utf-8 -*-

import re

from odoo import api, fields, models


class WhatsappIntentRule(models.Model):
    _name = "whatsapp.intent.rule"
    _description = "Regla de intención WhatsApp"
    _order = "priority desc, sequence asc, name asc"

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

    intent = fields.Selection(
        selection=[
            ("greeting", "Saludo"),
            ("service", "Servicio técnico"),
            ("toner", "Tóner / suministros"),
            ("scanner", "Escáner / configuración"),
            ("billing", "Facturación"),
            ("sales", "Ventas"),
            ("rental", "Alquiler"),
            ("human", "Solicita humano"),
            ("thanks", "Agradecimiento"),
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
            ("ask_dni", "Pedir DNI"),
            ("ask_ruc", "Pedir RUC"),
            ("select_company", "Seleccionar empresa"),
            ("create_ticket", "Crear ticket"),
            ("send_service_link", "Enviar link de servicio"),
            ("handoff", "Derivar a humano"),
            ("ai", "Usar IA"),
            ("ignore", "Ignorar"),
        ],
        string="Acción sugerida",
        default="ai",
        required=True,
        index=True,
    )

    match_type = fields.Selection(
        selection=[
            ("exact", "Exacto"),
            ("contains", "Contiene"),
            ("regex", "Regex"),
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

    stop_flow = fields.Boolean(
        string="Cortar flujo",
        default=False,
    )

    allow_ai_after = fields.Boolean(
        string="Permitir IA después",
        default=True,
    )

    note = fields.Text(
        string="Notas internas",
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

    def _normalize_text(self, text):
        return (text or "").strip().lower()

    def _match_text(self, message):
        self.ensure_one()

        message_norm = self._normalize_text(message)
        pattern_norm = self._normalize_text(self.pattern)

        if not message_norm or not pattern_norm:
            return False

        if self.match_type == "exact":
            return message_norm == pattern_norm

        if self.match_type == "contains":
            return pattern_norm in message_norm

        if self.match_type == "regex":
            try:
                return bool(re.search(self.pattern, message or "", flags=re.IGNORECASE))
            except Exception:
                return False

        return False

    @api.model
    def detect_intent(self, message, partner=False, applies_to=False, is_after_hours=False):
        domain = [("active", "=", True)]

        if applies_to:
            domain += [("applies_to", "in", ["all", applies_to])]

        rules = self.search(domain, order="priority desc, sequence asc, name asc")

        for rule in rules:
            if not rule._match_text(message):
                continue

            rule.sudo().write({
                "last_used_at": fields.Datetime.now(),
                "use_count": rule.use_count + 1,
            })

            return {
                "found": True,
                "rule_id": rule.id,
                "name": rule.name,
                "intent": rule.intent,
                "action": rule.action,
                "requires_registered": rule.requires_registered,
                "requires_company": rule.requires_company,
                "stop_flow": rule.stop_flow,
                "allow_ai_after": rule.allow_ai_after,
            }

        return {
            "found": False,
            "intent": "unknown",
            "action": "ai",
        }