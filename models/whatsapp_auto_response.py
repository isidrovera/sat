# -*- coding: utf-8 -*-

import logging
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


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
            ("in_break", "Refrigerio"),
            ("registration", "Registro"),
            ("dni", "DNI"),
            ("ruc", "RUC"),
            ("service", "Servicio técnico"),
            ("toner", "Tóner / suministros"),
            ("onsite", "Servicio presencial"),
            ("remote", "Asistencia remota"),
            ("human", "Humano"),
            ("thanks", "Agradecimiento"),
            ("goodbye", "Despedida"),
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
            ("starts_with", "Empieza con"),
            ("word", "Palabra completa"),
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

    template_name = fields.Char(
        string="Plantilla (opcional)",
        help="Si se provee, se renderiza whatsapp.template con este nombre en vez del campo response.",
    )

    stop_flow = fields.Boolean(
        string="Cortar flujo",
        default=True,
    )

    allow_ai_after = fields.Boolean(
        string="Permitir IA después",
        default=False,
    )

    only_business_hours = fields.Boolean(
        string="Solo horario laboral",
        default=False,
    )

    only_after_hours = fields.Boolean(
        string="Solo fuera de horario",
        default=False,
    )

    only_during_idle = fields.Boolean(
        string="Solo si no hay flujo activo",
        default=True,
        help="Si True, no se dispara cuando el cliente está en medio de un flujo conversacional.",
    )

    use_partner_name = fields.Boolean(
        string="Usar nombre del contacto",
        default=True,
        help="Permite reemplazar {{partner_name}} en la respuesta.",
    )

    min_message_length = fields.Integer(
        string="Largo mínimo mensaje",
        default=0,
    )

    note = fields.Text(string="Notas internas")
    description = fields.Text(string="Descripción de uso")

    last_used_at = fields.Datetime(string="Último uso", readonly=True)
    use_count = fields.Integer(string="Cantidad de usos", default=0, readonly=True)
    last_matched_message = fields.Text(string="Último mensaje matcheado", readonly=True)

    _sql_constraints = [
        (
            "unique_whatsapp_auto_response_name",
            "unique(name)",
            "Ya existe una respuesta automática con ese nombre.",
        ),
    ]

    # ==========================================================
    # Constraints
    # ==========================================================
    @api.constrains("match_type", "trigger")
    def _check_pattern_validity(self):
        for rec in self:
            if rec.match_type == "regex":
                try:
                    re.compile(rec.trigger or "")
                except re.error as e:
                    _logger.error(
                        "[WA-AUTO] Regex inválido id=%s trigger=%r error=%s",
                        rec.id, rec.trigger, str(e),
                    )
                    raise ValidationError(_(
                        "El patrón regex no es válido en la respuesta '%s': %s"
                    ) % (rec.name, str(e)))

    # ==========================================================
    # Helpers
    # ==========================================================
    def _normalize_text(self, text):
        return (text or "").strip().lower()

    def _match_text(self, message):
        self.ensure_one()

        if not message:
            return False

        if self.min_message_length > 0 and len(message) < self.min_message_length:
            return False

        message_norm = self._normalize_text(message)
        trigger_norm = self._normalize_text(self.trigger)

        if not message_norm or not trigger_norm:
            return False

        try:
            if self.match_type == "exact":
                return message_norm == trigger_norm

            if self.match_type == "contains":
                return trigger_norm in message_norm

            if self.match_type == "starts_with":
                return message_norm.startswith(trigger_norm)

            if self.match_type == "word":
                pattern_escaped = re.escape(trigger_norm)
                return bool(re.search(
                    r"\b" + pattern_escaped + r"\b",
                    message_norm,
                    flags=re.IGNORECASE,
                ))

            if self.match_type == "regex":
                return bool(re.search(self.trigger, message or "", flags=re.IGNORECASE))

        except Exception as e:
            _logger.exception(
                "[WA-AUTO] Error matcheando id=%s error=%s", self.id, str(e),
            )
            return False

        return False

    def _render_response(self, partner=False, extra=None, session=False):
        self.ensure_one()
        extra = extra or {}

        # Si tiene plantilla asociada, intentar renderizar desde whatsapp.template
        if self.template_name:
            try:
                rendered = self.env["whatsapp.template"].sudo().get_rendered(
                    name=self.template_name,
                    partner=partner if partner else False,
                    session=session if session else False,
                    extra=extra,
                )
                if rendered:
                    _logger.debug(
                        "[WA-AUTO] Renderizado desde template name=%s",
                        self.template_name,
                    )
                    return rendered
            except Exception as e:
                _logger.warning(
                    "[WA-AUTO] Error renderizando template %s, usando response: %s",
                    self.template_name, str(e),
                )

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
            "first_name": partner_name.split()[0] if partner_name else "",
            "company_name": company_name,
        }
        values.update(extra)

        try:
            def replace_var(match):
                var_name = match.group(1).strip()
                return str(values.get(var_name, "") or "")
            text = re.sub(
                r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}",
                replace_var, text,
            )
        except Exception:
            _logger.exception(
                "[WA-AUTO] Error sustituyendo variables id=%s", self.id,
            )

        return text

    # ==========================================================
    # Create / Write con logs
    # ==========================================================
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            _logger.info(
                "[WA-AUTO] Creada id=%s name=%s category=%s trigger=%r",
                rec.id, rec.name, rec.category, rec.trigger,
            )
        return records

    # ==========================================================
    # API pública
    # ==========================================================
    @api.model
    def find_response(self, message, partner=False, applies_to=False,
                      is_after_hours=False, extra=None, session=False, current_flow=False):
        """
        Busca la primera respuesta automática que coincida.
        """
        if not message:
            return {"found": False, "response": False}

        _logger.debug(
            "[WA-AUTO] find_response message=%r applies_to=%s after_hours=%s flow=%s",
            (message[:80] + "...") if len(message) > 80 else message,
            applies_to, is_after_hours, current_flow,
        )

        domain = [("active", "=", True)]

        if applies_to:
            domain += [("applies_to", "in", ["all", applies_to])]

        rules = self.search(domain, order="priority desc, sequence asc, name asc")

        _logger.debug("[WA-AUTO] Evaluando %s respuestas activas", len(rules))

        for rule in rules:
            try:
                if rule.only_business_hours and is_after_hours:
                    continue

                if rule.only_after_hours and not is_after_hours:
                    continue

                if rule.only_during_idle and current_flow and current_flow != "none":
                    continue

                if not rule._match_text(message):
                    continue

                try:
                    rule.sudo().write({
                        "last_used_at": fields.Datetime.now(),
                        "use_count": rule.use_count + 1,
                        "last_matched_message": (message[:500] if message else False),
                    })
                except Exception as e:
                    _logger.warning(
                        "[WA-AUTO] No se pudo actualizar métricas id=%s error=%s",
                        rule.id, str(e),
                    )

                _logger.info(
                    "[WA-AUTO] Match: id=%s name=%s category=%s",
                    rule.id, rule.name, rule.category,
                )

                return {
                    "found": True,
                    "response_id": rule.id,
                    "name": rule.name,
                    "category": rule.category,
                    "response": rule._render_response(
                        partner=partner, extra=extra, session=session,
                    ),
                    "stop_flow": rule.stop_flow,
                    "allow_ai_after": rule.allow_ai_after,
                    "applies_to": rule.applies_to,
                    "template_name": rule.template_name or False,
                }

            except Exception as e:
                _logger.exception(
                    "[WA-AUTO] Error evaluando id=%s error=%s",
                    rule.id, str(e),
                )
                continue

        _logger.debug("[WA-AUTO] Sin match para mensaje")

        return {
            "found": False,
            "response": False,
        }

    def action_reset_use_count(self):
        for rec in self:
            _logger.info(
                "[WA-AUTO] Reset use_count id=%s previo=%s",
                rec.id, rec.use_count,
            )
            rec.write({
                "use_count": 0,
                "last_used_at": False,
                "last_matched_message": False,
            })
        return True