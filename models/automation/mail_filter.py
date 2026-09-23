# -*- coding: utf-8 -*-

import logging
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .constants import EVENT_TYPE_SELECTION

_logger = logging.getLogger(__name__)


class SatAutomationMailFilter(models.Model):
    _name = "sat.automation.mail.filter"
    _description = "Filtro dinámico de correo SAT"
    _order = "sequence, id"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10, index=True)

    match_mode = fields.Selection(
        [("all", "Todas"), ("any", "Cualquiera")],
        default="all",
        required=True,
    )

    sender_exact = fields.Char()
    sender_domain = fields.Char()
    sender_regex = fields.Char()
    subject_contains = fields.Char()
    subject_regex = fields.Char()
    body_contains = fields.Char()
    body_regex = fields.Char()

    require_odoo_contact = fields.Boolean(default=False)
    require_company_domain = fields.Boolean(default=False)
    partner_id = fields.Many2one("res.partner")

    action = fields.Selection(
        [
            ("process", "Procesar"),
            ("ignore", "Ignorar"),
            ("review", "Revisión"),
        ],
        default="process",
        required=True,
    )

    expected_event_type = fields.Selection(EVENT_TYPE_SELECTION)

    use_patterns = fields.Boolean(default=True)
    ai_mode_override = fields.Selection(
        [
            ("inherit", "Heredar configuración"),
            ("disabled", "Nunca"),
            ("fallback", "Fallback"),
            ("preferred", "Preferida"),
        ],
        default="inherit",
        required=True,
    )

    min_pattern_confidence = fields.Float(default=0.0)
    min_ai_confidence = fields.Float(default=0.0)

    @api.constrains("sender_regex", "subject_regex", "body_regex")
    def _check_regex(self):
        for rec in self:
            for field_name in ("sender_regex", "subject_regex", "body_regex"):
                value = rec[field_name]
                if not value:
                    continue
                try:
                    re.compile(value)
                except re.error as exc:
                    raise ValidationError(
                        _("Regex inválida en %s: %s") % (field_name, str(exc))
                    )

    @api.model
    def _extract_email(self, value):
        if not value:
            return False
        txt = str(value).strip().lower()
        if "<" in txt and ">" in txt:
            txt = txt.split("<", 1)[1].split(">", 1)[0].strip()
        return txt if "@" in txt else False

    @api.model
    def _extract_domain(self, value):
        email = self._extract_email(value)
        return email.rsplit("@", 1)[1] if email else False

    def _find_odoo_contact(self, event):
        email = self._extract_email(event.sender)
        if not email:
            return self.env["res.partner"]
        return self.env["res.partner"].search(
            [("email", "=ilike", email)],
            limit=1,
        )

    def _match_company_domain(self, event):
        domain = (event.sender_domain or "").lower().strip()
        if not domain:
            return self.env["res.partner"]

        contacts = self.env["res.partner"].search([
            ("email", "!=", False),
        ])
        for partner in contacts:
            if self._extract_domain(partner.email) == domain:
                return partner.parent_id or partner
        return self.env["res.partner"]

    def matches(self, event):
        self.ensure_one()

        checks = []
        sender = (event.sender or "").strip().lower()
        domain = (event.sender_domain or "").strip().lower()
        subject = event.subject or ""
        body = event.body_plain or ""

        if self.sender_exact:
            checks.append(sender == self.sender_exact.strip().lower())
        if self.sender_domain:
            checks.append(domain == self.sender_domain.strip().lower().lstrip("@"))
        if self.sender_regex:
            checks.append(bool(re.search(self.sender_regex, sender, re.I)))
        if self.subject_contains:
            checks.append(self.subject_contains.lower() in subject.lower())
        if self.subject_regex:
            checks.append(bool(re.search(self.subject_regex, subject, re.I)))
        if self.body_contains:
            checks.append(self.body_contains.lower() in body.lower())
        if self.body_regex:
            checks.append(bool(re.search(self.body_regex, body, re.I | re.S)))
        if self.partner_id:
            checks.append(event.partner_id == self.partner_id)
        if self.require_odoo_contact:
            checks.append(bool(self._find_odoo_contact(event)))
        if self.require_company_domain:
            checks.append(bool(self._match_company_domain(event)))

        if not checks:
            return False

        return all(checks) if self.match_mode == "all" else any(checks)

    @api.model
    def evaluate_event(self, event):
        filters = self.search([("active", "=", True)], order="sequence, id")
        for rec in filters:
            if not rec.matches(event):
                continue

            _logger.info(
                "[SAT AUTOMATION][MAIL_FILTER][MATCH] event_id=%s filter_id=%s name=%s",
                event.id, rec.id, rec.name,
            )
            event._audit(
                "mail_filter_match",
                message="Filtro aplicado.",
                data={
                    "filter_id": rec.id,
                    "filter_name": rec.name,
                    "action": rec.action,
                },
            )
            return rec

        _logger.info(
            "[SAT AUTOMATION][MAIL_FILTER][NO_MATCH] event_id=%s sender=%s",
            event.id, event.sender,
        )
        return self.browse()
