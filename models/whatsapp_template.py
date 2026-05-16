# -*- coding: utf-8 -*-

import logging
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class WhatsappTemplate(models.Model):
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
    # Render
    # ==========================================================
    def render_template(self, partner=False, session=False, company=False, extra=None):
        self.ensure_one()
        extra = extra or {}

        # Validar precondiciones
        if self.requires_partner and not partner:
            _logger.warning(
                "[WA-TEMPLATE] Plantilla requiere partner pero no se proveyó name=%s",
                self.name,
            )
            return self._render_fallback(partner, session, company, extra)

        active_company = company
        if not active_company and partner and getattr(partner, "whatsapp_active_company_id", False):
            active_company = partner.whatsapp_active_company_id
        if not active_company and partner and partner.parent_id:
            active_company = partner.parent_id

        if self.requires_company and not active_company:
            _logger.warning(
                "[WA-TEMPLATE] Plantilla requiere empresa pero no se proveyó name=%s",
                self.name,
            )
            return self._render_fallback(partner, session, company, extra)

        text = self.body or ""

        # Variables base
        values = {
            "partner_name": partner.name if partner else "",
            "contact_name": partner.name if partner else "",
            "first_name": self._get_first_name(partner) if partner else "",
            "company_name": active_company.name if active_company else "",
            "company_vat": active_company.vat if active_company else "",
            "partner_vat": partner.vat if partner and partner.vat else "",
            "session_name": session.name if session else "",
            "session_id": str(session.id) if session else "",
            "phone": (partner.whatsapp_number or partner.mobile or partner.phone) if partner else "",
        }

        # Override con extra
        values.update(extra)

        # Reemplazo robusto con regex (acepta espacios alrededor del nombre)
        def replace_var(match):
            var_name = match.group(1).strip()
            return str(values.get(var_name, "") or "")

        try:
            text = re.sub(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}", replace_var, text)
        except Exception as e:
            _logger.exception(
                "[WA-TEMPLATE] Error renderizando plantilla name=%s error=%s",
                self.name, str(e),
            )
            return self._render_fallback(partner, session, company, extra)

        # Actualizar métricas de uso
        try:
            self.sudo().write({
                "usage_count": self.usage_count + 1,
                "last_used_at": fields.Datetime.now(),
            })
        except Exception:
            _logger.exception(
                "[WA-TEMPLATE] No se pudo actualizar usage_count name=%s",
                self.name,
            )

        _logger.debug(
            "[WA-TEMPLATE] Renderizada name=%s partner=%s company=%s len=%s",
            self.name,
            partner.id if partner else False,
            active_company.id if active_company else False,
            len(text),
        )

        return text

    def _get_first_name(self, partner):
        if not partner or not partner.name:
            return ""
        return partner.name.split()[0]

    def _render_fallback(self, partner, session, company, extra):
        self.ensure_one()
        if not self.fallback_template_name:
            _logger.warning(
                "[WA-TEMPLATE] Sin fallback configurado, devolviendo body crudo name=%s",
                self.name,
            )
            return self.body or ""

        fallback = self.search([
            ("name", "=", self.fallback_template_name),
            ("active", "=", True),
        ], limit=1)

        if not fallback:
            _logger.warning(
                "[WA-TEMPLATE] Fallback no encontrado name=%s fallback=%s",
                self.name, self.fallback_template_name,
            )
            return self.body or ""

        _logger.info(
            "[WA-TEMPLATE] Usando fallback name=%s -> %s",
            self.name, self.fallback_template_name,
        )

        return fallback.render_template(
            partner=partner,
            session=session,
            company=company,
            extra=extra,
        )

    # ==========================================================
    # API pública
    # ==========================================================
    @api.model
    def get_rendered(self, name, partner=False, session=False, company=False, extra=None):
        if not name:
            _logger.error("[WA-TEMPLATE] get_rendered llamado sin name")
            return False

        template = self.search([
            ("name", "=", name),
            ("active", "=", True),
        ], limit=1)

        if not template:
            _logger.warning(
                "[WA-TEMPLATE] Plantilla no encontrada o inactiva name=%s", name,
            )
            return False

        try:
            return template.render_template(
                partner=partner,
                session=session,
                company=company,
                extra=extra,
            )
        except Exception as e:
            _logger.exception(
                "[WA-TEMPLATE] Error en get_rendered name=%s error=%s",
                name, str(e),
            )
            return False

    @api.model
    def render_with_fallback(self, name, fallback_text, partner=False, session=False, company=False, extra=None):
        """
        Renderiza una plantilla y si no existe o falla, devuelve fallback_text
        con sustitución básica de variables.
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
            "[WA-TEMPLATE] Usando fallback_text inline name=%s", name,
        )

        # Aplicar sustitución básica al fallback
        text = fallback_text or ""
        if not text:
            return ""

        values = {
            "partner_name": partner.name if partner else "",
            "contact_name": partner.name if partner else "",
            "first_name": partner.name.split()[0] if (partner and partner.name) else "",
            "company_name": company.name if company else "",
        }
        if extra:
            values.update(extra)

        try:
            def replace_var(match):
                var_name = match.group(1).strip()
                return str(values.get(var_name, "") or "")
            text = re.sub(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}", replace_var, text)
        except Exception:
            _logger.exception(
                "[WA-TEMPLATE] Error sustituyendo variables en fallback_text name=%s",
                name,
            )

        return text

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