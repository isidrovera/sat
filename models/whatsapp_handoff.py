# -*- coding: utf-8 -*-

from odoo import fields, models


class WhatsappHandoff(models.Model):
    _name = "whatsapp.handoff"
    _description = "Derivación humana WhatsApp"
    _order = "taken_at desc, id desc"

    name = fields.Char(
        string="Referencia",
        default="Derivación WhatsApp",
        required=True,
        index=True,
    )

    session_id = fields.Many2one(
        comodel_name="whatsapp.session",
        string="Sesión",
        index=True,
        ondelete="set null",
    )

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contacto",
        required=True,
        index=True,
        ondelete="cascade",
    )

    company_id = fields.Many2one(
        comodel_name="res.partner",
        string="Empresa",
        domain=[("is_company", "=", True)],
        index=True,
        ondelete="set null",
    )

    state = fields.Selection(
        selection=[
            ("open", "Activo"),
            ("released", "Liberado"),
            ("cancelled", "Cancelado"),
        ],
        string="Estado",
        default="open",
        required=True,
        index=True,
    )

    taken_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Tomado por",
        ondelete="set null",
    )

    taken_by_name = fields.Char(
        string="Tomado por nombre",
    )

    taken_at = fields.Datetime(
        string="Tomado el",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    released_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Liberado por",
        ondelete="set null",
    )

    released_by_name = fields.Char(
        string="Liberado por nombre",
    )

    released_at = fields.Datetime(
        string="Liberado el",
        index=True,
    )

    reason = fields.Text(
        string="Motivo",
    )

    note = fields.Text(
        string="Notas internas",
    )

    def action_release(self):
        for handoff in self:
            handoff.write({
                "state": "released",
                "released_at": fields.Datetime.now(),
                "released_by_id": self.env.user.id,
                "released_by_name": self.env.user.name,
            })

    def action_cancel(self):
        for handoff in self:
            handoff.write({
                "state": "cancelled",
                "released_at": fields.Datetime.now(),
                "released_by_id": self.env.user.id,
                "released_by_name": self.env.user.name,
            })