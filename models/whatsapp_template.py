# -*- coding: utf-8 -*-

import logging
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class WhatsappTemplate(models.Model):
    """
    Plantillas reutilizables para respuestas WhatsApp.

    El motor usa variables simples con sintaxis ``{{variable}}``.
    Las variables ausentes se sustituyen por cadena vacía para no romper
    la conversación.

    Las plantillas pueden recibir valores base desde partner/session/company
    y valores adicionales mediante ``extra``.
    """

    _name = "whatsapp.template"
    _description = "Plantilla WhatsApp"
    _order = "category asc, name asc"

    # ==========================================================
    # Campos base
    # ==========================================================
    name = fields.Char(
        string="Nombre técnico",
        required=True,
        index=True,
        help="Identificador único usado desde código (ej. ask_dni, toner_color_menu).",
    )

    title = fields.Char(
        string="Título",
        required=True,
        help="Título descriptivo para la interfaz de administración.",
    )

    active = fields.Boolean(
        string="Activo",
        default=True,
        index=True,
    )

    category = fields.Selection(
        selection=[
            ("greeting", "Saludo"),
            ("registration", "Registro"),
            ("dni", "DNI"),
            ("ruc", "RUC"),
            ("blocked", "Bloqueado"),
            ("human", "Modo humano"),
            ("after_hours", "Fuera de horario"),
            ("company", "Empresa"),
            ("service", "Servicio técnico"),
            ("toner", "Tóner"),
            ("scanner", "Escáner"),
            ("billing", "Facturación"),
            ("sales", "Ventas"),
            ("onsite", "Servicio presencial"),
            ("remote", "Soporte remoto"),
            ("anydesk", "AnyDesk"),
            ("machine_menu", "Menú de equipos"),
            ("confirmation", "Confirmación"),
            ("rejection", "Rechazo"),
            ("error", "Error"),
            ("timeout", "Timeout"),
            ("fallback", "General"),
        ],
        string="Categoría",
        default="fallback",
        required=True,
        index=True,
    )

    body = fields.Text(
        string="Mensaje",
        required=True,
        help="Texto de la plantilla. Variables con formato {{nombre_variable}}.",
    )

    note = fields.Text(string="Notas internas")

    # ==========================================================
    # Campos nuevos
    # ==========================================================
    available_variables = fields.Text(
        string="Variables disponibles",
        compute="_compute_available_variables",
        store=False,
        help="Variables {{...}} detectadas en el cuerpo del mensaje.",
    )

    description = fields.Text(
        string="Descripción de uso",
        help="Cuándo y cómo se usa esta plantilla (para el admin).",
    )

    fallback_template_name = fields.Char(
        string="Plantilla de fallback",
        help="Nombre de otra plantilla a usar si esta falla al renderizar.",
    )

    usage_count = fields.Integer(
        string="Veces usada",
        default=0,
        readonly=True,
        help="Contador de cuántas veces se ha renderizado esta plantilla.",
    )

    last_used_at = fields.Datetime(
        string="Última vez usada",
        readonly=True,
    )

    requires_partner = fields.Boolean(
        string="Requiere contacto",
        default=False,
        help="Si True, la plantilla no se renderiza si no hay partner.",
    )

    requires_company = fields.Boolean(
        string="Requiere empresa",
        default=False,
        help="Si True, la plantilla no se renderiza si no hay empresa activa.",
    )

    # ==========================================================
    # SQL constraints
    # ==========================================================
    _sql_constraints = [
        (
            "unique_whatsapp_template_name",
            "unique(name)",
            "Ya existe una plantilla WhatsApp con ese nombre técnico.",
        )
    ]

    # ==========================================================
    # Constraints
    # ==========================================================
    @api.constrains("name")
    def _check_name_format(self):
        for tpl in self:
            if not tpl.name:
                continue
            if not re.match(r"^[a-z0-9_]+$", tpl.name):
                _logger.error(
                    "[WA-TEMPLATE] Nombre técnico inválido id=%s name=%r",
                    tpl.id, tpl.name,
                )
                raise ValidationError(_(
                    "El nombre técnico solo puede contener letras minúsculas, "
                    "números y guiones bajos. Recibido: %s"
                ) % tpl.name)

    # ==========================================================
    # Computes
    # ==========================================================
    @api.depends("body")
    def _compute_available_variables(self):
        pattern = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
        for tpl in self:
            if not tpl.body:
                tpl.available_variables = ""
                continue
            found = pattern.findall(tpl.body)
            unique_vars = sorted(set(found))
            tpl.available_variables = ", ".join("{{%s}}" % v for v in unique_vars)

    # ==========================================================
    # Create / Write
    # ==========================================================
    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        for tpl in templates:
            _logger.info(
                "[WA-TEMPLATE] Plantilla creada id=%s name=%s category=%s",
                tpl.id, tpl.name, tpl.category,
            )
        return templates

    def write(self, vals):
        result = super().write(vals)
        if "body" in vals or "active" in vals or "name" in vals:
            for tpl in self:
                _logger.info(
                    "[WA-TEMPLATE] Plantilla modificada id=%s name=%s active=%s",
                    tpl.id, tpl.name, tpl.active,
                )
        return result

    # ==========================================================
    # Helpers de render
    # ==========================================================
    def _safe_template_value(self, value):
        """
        Convierte valores de plantilla a texto de forma segura.

        Evita que recordsets, listas o dicts provoquen representaciones
        técnicas inesperadas en WhatsApp.
        """
        if value is None or value is False:
            return ""

        if isinstance(value, (str, int, float)):
            return str(value)

        if isinstance(value, bool):
            return "Sí" if value else "No"

        if isinstance(value, (list, tuple, set)):
            return ", ".join(
                self._safe_template_value(item)
                for item in value
                if item not in (None, False, "")
            )

        if isinstance(value, dict):
            return ", ".join(
                "%s: %s" % (
                    key,
                    self._safe_template_value(val),
                )
                for key, val in value.items()
            )

        if hasattr(value, "display_name"):
            return value.display_name or ""

        return str(value)

    def _build_template_values(
        self,
        partner=False,
        session=False,
        company=False,
        extra=None,
    ):
        active_company = company

        if (
            not active_company
            and partner
            and getattr(
                partner,
                "whatsapp_active_company_id",
                False,
            )
        ):
            active_company = (
                partner.whatsapp_active_company_id
            )

        if (
            not active_company
            and partner
            and partner.parent_id
        ):
            active_company = partner.parent_id

        values = {
            "partner_name": (
                partner.name
                if partner
                else ""
            ),
            "contact_name": (
                partner.name
                if partner
                else ""
            ),
            "first_name": (
                self._get_first_name(partner)
                if partner
                else ""
            ),
            "company_name": (
                active_company.name
                if active_company
                else ""
            ),
            "company_vat": (
                active_company.vat
                if active_company
                else ""
            ),
            "partner_vat": (
                partner.vat
                if partner and partner.vat
                else ""
            ),
            "session_name": (
                session.name
                if session
                else ""
            ),
            "session_id": (
                str(session.id)
                if session
                else ""
            ),
            "phone": (
                (
                    getattr(
                        partner,
                        "whatsapp_number",
                        False,
                    )
                    or partner.mobile
                    or partner.phone
                    or ""
                )
                if partner
                else ""
            ),
        }

        if isinstance(extra, dict):
            values.update(extra)

        return values, active_company

    def _replace_template_variables(
        self,
        text,
        values,
        template_name=False,
    ):
        text = text or ""
        values = values or {}

        variable_pattern = re.compile(
            r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}"
        )

        used_variables = set(
            variable_pattern.findall(text)
        )

        missing_variables = sorted([
            name
            for name in used_variables
            if name not in values
        ])

        if missing_variables:
            _logger.warning(
                "[WA-TEMPLATE] Variables no suministradas | "
                "template=%s vars=%s",
                template_name or False,
                missing_variables,
            )

        def replace_var(match):
            var_name = match.group(1).strip()
            return self._safe_template_value(
                values.get(var_name, "")
            )

        try:
            return variable_pattern.sub(
                replace_var,
                text,
            )
        except Exception:
            _logger.exception(
                "[WA-TEMPLATE] Error sustituyendo variables | "
                "template=%s",
                template_name or False,
            )
            return text

    # ==========================================================
    # Render
    # ==========================================================
    def render_template(
        self,
        partner=False,
        session=False,
        company=False,
        extra=None,
        _fallback_chain=None,
    ):
        """
        Renderiza la plantilla activa usando variables base + ``extra``.

        Variables desconocidas:
            se sustituyen por cadena vacía y dejan warning en log.

        Fallback:
            se protege contra referencias circulares.
        """
        self.ensure_one()

        extra = (
            extra
            if isinstance(extra, dict)
            else {}
        )

        fallback_chain = list(
            _fallback_chain or []
        )

        if self.name in fallback_chain:
            _logger.error(
                "[WA-TEMPLATE] Ciclo de fallback detectado | "
                "chain=%s current=%s",
                fallback_chain,
                self.name,
            )
            return self.body or ""

        fallback_chain.append(
            self.name
        )

        values, active_company = (
            self._build_template_values(
                partner=partner,
                session=session,
                company=company,
                extra=extra,
            )
        )

        if self.requires_partner and not partner:
            _logger.warning(
                "[WA-TEMPLATE] Requiere partner | template=%s",
                self.name,
            )
            return self._render_fallback(
                partner,
                session,
                company,
                extra,
                fallback_chain=fallback_chain,
            )

        if (
            self.requires_company
            and not active_company
        ):
            _logger.warning(
                "[WA-TEMPLATE] Requiere empresa | template=%s",
                self.name,
            )
            return self._render_fallback(
                partner,
                session,
                company,
                extra,
                fallback_chain=fallback_chain,
            )

        text = self._replace_template_variables(
            self.body or "",
            values,
            template_name=self.name,
        )

        try:
            self.sudo().write({
                "usage_count": (
                    self.usage_count + 1
                ),
                "last_used_at": fields.Datetime.now(),
            })
        except Exception:
            _logger.exception(
                "[WA-TEMPLATE] No se pudo actualizar uso | "
                "template=%s",
                self.name,
            )

        _logger.debug(
            "[WA-TEMPLATE] Render completado | "
            "template=%s partner=%s company=%s "
            "session=%s len=%s extra_keys=%s",
            self.name,
            partner.id if partner else False,
            (
                active_company.id
                if active_company
                else False
            ),
            session.id if session else False,
            len(text),
            sorted(extra.keys()),
        )

        return text

    def _get_first_name(self, partner):
        if not partner or not partner.name:
            return ""
        return partner.name.split()[0]

    def _render_fallback(
        self,
        partner,
        session,
        company,
        extra,
        fallback_chain=None,
    ):
        self.ensure_one()

        fallback_chain = list(
            fallback_chain or []
        )

        if not self.fallback_template_name:
            _logger.warning(
                "[WA-TEMPLATE] Sin fallback configurado | template=%s",
                self.name,
            )

            values, _active_company = (
                self._build_template_values(
                    partner=partner,
                    session=session,
                    company=company,
                    extra=extra,
                )
            )

            return self._replace_template_variables(
                self.body or "",
                values,
                template_name=self.name,
            )

        if (
            self.fallback_template_name
            in fallback_chain
        ):
            _logger.error(
                "[WA-TEMPLATE] Fallback circular bloqueado | "
                "template=%s fallback=%s chain=%s",
                self.name,
                self.fallback_template_name,
                fallback_chain,
            )
            return ""

        fallback = self.search([
            (
                "name",
                "=",
                self.fallback_template_name,
            ),
            ("active", "=", True),
        ], limit=1)

        if not fallback:
            _logger.warning(
                "[WA-TEMPLATE] Fallback no encontrado | "
                "template=%s fallback=%s",
                self.name,
                self.fallback_template_name,
            )

            values, _active_company = (
                self._build_template_values(
                    partner=partner,
                    session=session,
                    company=company,
                    extra=extra,
                )
            )

            return self._replace_template_variables(
                self.body or "",
                values,
                template_name=self.name,
            )

        _logger.info(
            "[WA-TEMPLATE] Aplicando fallback | "
            "template=%s fallback=%s",
            self.name,
            self.fallback_template_name,
        )

        return fallback.render_template(
            partner=partner,
            session=session,
            company=company,
            extra=extra,
            _fallback_chain=fallback_chain,
        )

    # ==========================================================
    # API pública
    # ==========================================================
    @api.model
    def get_rendered(
        self,
        name,
        partner=False,
        session=False,
        company=False,
        extra=None,
    ):
        """
        API pública principal usada por controllers y respuestas automáticas.
        """
        name = (
            str(name or "")
            .strip()
        )

        if not name:
            _logger.error(
                "[WA-TEMPLATE] get_rendered sin nombre"
            )
            return False

        template = self.search([
            ("name", "=", name),
            ("active", "=", True),
        ], limit=1)

        if not template:
            _logger.warning(
                "[WA-TEMPLATE] Plantilla inexistente/inactiva | "
                "template=%s",
                name,
            )
            return False

        try:
            return template.render_template(
                partner=partner,
                session=session,
                company=company,
                extra=(
                    extra
                    if isinstance(extra, dict)
                    else {}
                ),
            )

        except Exception:
            _logger.exception(
                "[WA-TEMPLATE] Falló get_rendered | "
                "template=%s partner=%s session=%s",
                name,
                partner.id if partner else False,
                session.id if session else False,
            )
            return False

    @api.model
    def render_with_fallback(
        self,
        name,
        fallback_text,
        partner=False,
        session=False,
        company=False,
        extra=None,
    ):
        """
        Renderiza por nombre y, si no existe/falla, procesa fallback_text
        con exactamente el mismo motor de variables.
        """
        rendered = self.get_rendered(
            name=name,
            partner=partner,
            session=session,
            company=company,
            extra=extra,
        )

        if rendered:
            return rendered

        _logger.info(
            "[WA-TEMPLATE] Usando fallback inline | template=%s",
            name or False,
        )

        values, _active_company = (
            self._build_template_values(
                partner=partner,
                session=session,
                company=company,
                extra=(
                    extra
                    if isinstance(extra, dict)
                    else {}
                ),
            )
        )

        return self._replace_template_variables(
            fallback_text or "",
            values,
            template_name=(
                "%s:inline_fallback"
                % (name or "unnamed")
            ),
        )

    # ==========================================================
    # Acciones del backend
    # ==========================================================
    def action_preview(self):
        """Acción para previsualizar el renderizado de la plantilla."""
        self.ensure_one()
        preview = self.render_template(extra={
            "partner_name": "Juan Pérez",
            "contact_name": "Juan Pérez",
            "first_name": "Juan",
            "company_name": "Empresa Demo S.A.C.",
            "company_vat": "20123456789",
            "anydesk_code": "123456789",
            "remote_problem": "No puedo imprimir.",
            "business_reason": "Fuera de horario",
            "business_message": "La atención continuará al retomar el horario.",
            "display_hours": "Lunes a viernes 08:30 - 18:00",
        })
        _logger.info(
            "[WA-TEMPLATE] Preview generado name=%s", self.name,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Vista previa: %s") % self.title,
                "message": preview,
                "type": "info",
                "sticky": True,
            },
        }

    def action_reset_usage_count(self):
        for tpl in self:
            _logger.info(
                "[WA-TEMPLATE] Resetando usage_count id=%s name=%s previo=%s",
                tpl.id, tpl.name, tpl.usage_count,
            )
            tpl.write({
                "usage_count": 0,
                "last_used_at": False,
            })
        return True