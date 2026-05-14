# -*- coding: utf-8 -*-

import re

from odoo import api, fields, models


class WhatsappAutoResponse(models.Model):
    _name = "whatsapp.auto.response"
    _description = "Respuesta automática WhatsApp"
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

    category = fields.Selection(
        selection=[
            ("greeting", "Saludo"),
            ("blocked", "Bloqueado"),
            ("after_hours", "Fuera de horario"),
            ("registration", "Registro"),
            ("dni", "DNI"),
            ("ruc", "RUC"),
            ("service", "Servicio técnico"),
            ("toner", "Tóner / suministros"),
            ("remote", "Asistencia remota"),
            ("human", "Humano"),
            ("thanks", "Agradecimiento"),
            ("fallback", "Respuesta general"),
        ],
        string="Categoría",
        default="fallback",
        required=True,
        index=True,
    )

    trigger = fields.Char(
        string="Disparador",
        required=True,
        help="Texto, palabra clave o expresión regular según el tipo de coincidencia.",
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

    response = fields.Text(
        string="Respuesta",
        required=True,
    )

    stop_flow = fields.Boolean(
        string="Cortar flujo",
        default=True,
        help="Si está activo, n8n no debe continuar con IA después de esta respuesta.",
    )

    allow_ai_after = fields.Boolean(
        string="Permitir IA después",
        default=False,
        help="Si está activo, n8n puede continuar con IA luego de esta respuesta.",
    )

    only_business_hours = fields.Boolean(
        string="Solo horario laboral",
        default=False,
    )

    only_after_hours = fields.Boolean(
        string="Solo fuera de horario",
        default=False,
    )

    use_partner_name = fields.Boolean(
        string="Usar nombre del contacto",
        default=True,
        help="Permite reemplazar {{partner_name}} en la respuesta.",
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

    # ==========================================================
    # Helpers
    # ==========================================================
    def _normalize_text(self, text):
        return (text or "").strip().lower()

    def _match_text(self, message):
        self.ensure_one()

        message_norm = self._normalize_text(message)
        trigger_norm = self._normalize_text(self.trigger)

        if not message_norm or not trigger_norm:
            return False

        if self.match_type == "exact":
            return message_norm == trigger_norm

        if self.match_type == "contains":
            return trigger_norm in message_norm

        if self.match_type == "regex":
            try:
                return bool(re.search(self.trigger, message or "", flags=re.IGNORECASE))
            except Exception:
                return False

        return False

    def _render_response(self, partner=False, extra=None):
        self.ensure_one()

        extra = extra or {}
        text = self.response or ""

        partner_name = partner.name if partner else ""
        company_name = ""

        if partner:
            active_company = getattr(partner, "whatsapp_active_company_id", False)
            if active_company:
                company_name = active_company.name or ""
            elif partner.parent_id:
                company_name = partner.parent_id.name or ""

        values = {
            "partner_name": partner_name,
            "contact_name": partner_name,
            "company_name": company_name,
        }
        values.update(extra)

        for key, value in values.items():
            text = text.replace("{{%s}}" % key, str(value or ""))

        return text

    @api.model
    def find_response(
        self,
        message,
        partner=False,
        applies_to=False,
        is_after_hours=False,
        extra=None,
    ):
        """
        Busca la primera respuesta automática que coincida.

        Retorna:
        {
            "found": bool,
            "response_id": id,
            "category": "...",
            "response": "...",
            "stop_flow": bool,
            "allow_ai_after": bool
        }
        """
        domain = [("active", "=", True)]

        if applies_to:
            domain += [("applies_to", "in", ["all", applies_to])]

        rules = self.search(domain, order="priority desc, sequence asc, name asc")

        for rule in rules:
            if rule.only_business_hours and is_after_hours:
                continue

            if rule.only_after_hours and not is_after_hours:
                continue

            if not rule._match_text(message):
                continue

            rule.sudo().write({
                "last_used_at": fields.Datetime.now(),
                "use_count": rule.use_count + 1,
            })

            return {
                "found": True,
                "response_id": rule.id,
                "name": rule.name,
                "category": rule.category,
                "response": rule._render_response(partner=partner, extra=extra),
                "stop_flow": rule.stop_flow,
                "allow_ai_after": rule.allow_ai_after,
                "applies_to": rule.applies_to,
            }

        return {
            "found": False,
            "response": False,
        }