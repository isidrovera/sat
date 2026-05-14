# -*- coding: utf-8 -*-

from odoo import api, fields, models


class WhatsappTemplate(models.Model):
    _name = "whatsapp.template"
    _description = "Plantilla WhatsApp"
    _order = "category asc, name asc"

    name = fields.Char(
        string="Nombre técnico",
        required=True,
        index=True,
    )

    title = fields.Char(
        string="Título",
        required=True,
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
    )

    note = fields.Text(
        string="Notas internas",
    )

    _sql_constraints = [
        (
            "unique_whatsapp_template_name",
            "unique(name)",
            "Ya existe una plantilla WhatsApp con ese nombre técnico.",
        )
    ]

    def render_template(self, partner=False, session=False, company=False, extra=None):
        self.ensure_one()

        extra = extra or {}
        text = self.body or ""

        active_company = company
        if not active_company and partner and getattr(partner, "whatsapp_active_company_id", False):
            active_company = partner.whatsapp_active_company_id
        if not active_company and partner and partner.parent_id:
            active_company = partner.parent_id

        values = {
            "partner_name": partner.name if partner else "",
            "contact_name": partner.name if partner else "",
            "company_name": active_company.name if active_company else "",
            "company_vat": active_company.vat if active_company else "",
            "session_name": session.name if session else "",
        }
        values.update(extra)

        for key, value in values.items():
            text = text.replace("{{%s}}" % key, str(value or ""))

        return text

    @api.model
    def get_rendered(self, name, partner=False, session=False, company=False, extra=None):
        template = self.search([
            ("name", "=", name),
            ("active", "=", True),
        ], limit=1)

        if not template:
            return False

        return template.render_template(
            partner=partner,
            session=session,
            company=company,
            extra=extra,
        )