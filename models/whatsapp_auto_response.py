# -*- coding: utf-8 -*-

import logging
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class WhatsappAutoResponse(models.Model):
    """
    Respuestas automáticas simples previas/complementarias a la IA.

    La coincidencia textual y el contexto se evalúan por separado:

    - ``applies_to`` describe el tipo funcional del contacto;
    - ``is_after_hours`` describe disponibilidad horaria;
    - ``current_flow`` describe el flujo conversacional activo.

    Se conserva compatibilidad con reglas antiguas configuradas con
    ``applies_to='after_hours'`` sin volver a mezclar ese valor con el
    contexto real del contacto.
    """

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

    def _is_context_applicable(
        self,
        applies_to=False,
        is_after_hours=False,
        current_flow=False,
    ):
        """
        Valida contexto sin mezclar estado de contacto y horario.

        Compatibilidad:
        una regla legacy con applies_to='after_hours' únicamente aplica
        cuando is_after_hours=True.
        """
        self.ensure_one()

        current_flow = current_flow or "none"
        contact_scope = applies_to or False

        if self.applies_to == "after_hours":
            if not is_after_hours:
                return False
        elif contact_scope and self.applies_to not in (
            "all",
            contact_scope,
        ):
            return False

        if (
            self.only_business_hours
            and is_after_hours
        ):
            return False

        if (
            self.only_after_hours
            and not is_after_hours
        ):
            return False

        if (
            self.only_during_idle
            and current_flow
            and current_flow != "none"
        ):
            return False

        return True

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

    def _render_response(
        self,
        partner=False,
        extra=None,
        session=False,
    ):
        """
        Renderiza usando whatsapp.template cuando existe template_name.

        El fallback inline usa el mismo motor de variables del modelo
        whatsapp.template para mantener comportamiento consistente.
        """
        self.ensure_one()

        extra = (
            extra
            if isinstance(extra, dict)
            else {}
        )

        Template = self.env[
            "whatsapp.template"
        ].sudo()

        if self.template_name:
            rendered = Template.render_with_fallback(
                name=self.template_name,
                fallback_text=self.response or "",
                partner=partner if partner else False,
                session=session if session else False,
                company=(
                    partner.whatsapp_active_company_id
                    if partner
                    and getattr(
                        partner,
                        "whatsapp_active_company_id",
                        False,
                    )
                    else False
                ),
                extra=extra,
            )

            if rendered:
                _logger.debug(
                    "[WA-AUTO] Respuesta renderizada con template | "
                    "rule_id=%s template=%s",
                    self.id,
                    self.template_name,
                )
                return rendered

        # Aunque no exista template_name, utilizar el mismo motor
        # compartido para sustituir variables del texto inline.
        values, _active_company = (
            Template._build_template_values(
                partner=partner if partner else False,
                session=session if session else False,
                company=False,
                extra=extra,
            )
        )

        return Template._replace_template_variables(
            self.response or "",
            values,
            template_name=(
                "auto_response:%s"
                % (self.name or self.id)
            ),
        )

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

    def write(self, vals):
        result = super().write(vals)

        tracked = {
            "active",
            "trigger",
            "match_type",
            "applies_to",
            "only_business_hours",
            "only_after_hours",
            "only_during_idle",
            "response",
            "template_name",
            "priority",
            "sequence",
        }

        if tracked.intersection(vals.keys()):
            for rec in self:
                _logger.info(
                    "[WA-AUTO] Modificada | "
                    "id=%s name=%s active=%s applies_to=%s "
                    "match_type=%s priority=%s sequence=%s",
                    rec.id,
                    rec.name,
                    rec.active,
                    rec.applies_to,
                    rec.match_type,
                    rec.priority,
                    rec.sequence,
                )

        return result

    # ==========================================================
    # API pública
    # ==========================================================
    @api.model
    def find_response(
        self,
        message,
        partner=False,
        applies_to=False,
        is_after_hours=False,
        extra=None,
        session=False,
        current_flow=False,
    ):
        """
        Busca la primera respuesta automática aplicable.

        Orden conservado:
            priority desc, sequence asc, name asc
        """
        message_clean = (
            str(message or "")
            .strip()
        )

        if not message_clean:
            return {
                "found": False,
                "response": False,
            }

        current_flow = (
            current_flow
            or (
                session.current_flow
                if session
                else "none"
            )
            or "none"
        )

        _logger.debug(
            "[WA-AUTO] Buscando respuesta | "
            "message=%r applies_to=%s after_hours=%s "
            "flow=%s partner=%s",
            (
                message_clean[:80] + "..."
                if len(message_clean) > 80
                else message_clean
            ),
            applies_to or False,
            bool(is_after_hours),
            current_flow,
            partner.id if partner else False,
        )

        # No filtramos applies_to desde SQL porque necesitamos conservar
        # compatibilidad con reglas legacy applies_to='after_hours' mientras
        # el contacto real puede seguir siendo registered.
        rules = self.search(
            [("active", "=", True)],
            order=(
                "priority desc, "
                "sequence asc, "
                "name asc"
            ),
        )

        _logger.debug(
            "[WA-AUTO] Evaluando reglas | count=%s",
            len(rules),
        )

        for rule in rules:
            try:
                if not rule._is_context_applicable(
                    applies_to=applies_to,
                    is_after_hours=is_after_hours,
                    current_flow=current_flow,
                ):
                    _logger.debug(
                        "[WA-AUTO] Regla descartada por contexto | "
                        "id=%s name=%s rule_scope=%s contact_scope=%s "
                        "after_hours=%s flow=%s",
                        rule.id,
                        rule.name,
                        rule.applies_to,
                        applies_to or False,
                        bool(is_after_hours),
                        current_flow,
                    )
                    continue

                if not rule._match_text(
                    message_clean
                ):
                    continue

                try:
                    rule.sudo().write({
                        "last_used_at": (
                            fields.Datetime.now()
                        ),
                        "use_count": (
                            rule.use_count + 1
                        ),
                        "last_matched_message": (
                            message_clean[:500]
                        ),
                    })
                except Exception:
                    _logger.exception(
                        "[WA-AUTO] Error actualizando métricas | "
                        "id=%s name=%s",
                        rule.id,
                        rule.name,
                    )

                response_text = (
                    rule._render_response(
                        partner=partner,
                        extra=extra,
                        session=session,
                    )
                )

                _logger.info(
                    "[WA-AUTO] Match | "
                    "id=%s name=%s category=%s applies_to=%s "
                    "after_hours=%s flow=%s template=%s",
                    rule.id,
                    rule.name,
                    rule.category,
                    rule.applies_to,
                    bool(is_after_hours),
                    current_flow,
                    rule.template_name or False,
                )

                return {
                    "found": True,
                    "response_id": rule.id,
                    "name": rule.name,
                    "category": rule.category,
                    "response": response_text,
                    "stop_flow": rule.stop_flow,
                    "allow_ai_after": (
                        rule.allow_ai_after
                    ),
                    "applies_to": rule.applies_to,
                    "template_name": (
                        rule.template_name
                        or False
                    ),
                }

            except Exception:
                _logger.exception(
                    "[WA-AUTO] Error evaluando regla | "
                    "id=%s name=%s",
                    rule.id,
                    rule.name,
                )
                continue

        _logger.debug(
            "[WA-AUTO] Sin coincidencia | "
            "applies_to=%s after_hours=%s flow=%s",
            applies_to or False,
            bool(is_after_hours),
            current_flow,
        )

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