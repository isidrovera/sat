# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class WhatsappSession(models.Model):
    _name = "whatsapp.session"
    _description = "Sesión WhatsApp"
    _order = "last_message_at desc, create_date desc"

    name = fields.Char(
        string="Referencia",
        required=True,
        default=lambda self: _("Nueva sesión"),
        copy=False,
        index=True,
    )

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contacto",
        required=True,
        index=True,
        ondelete="cascade",
    )

    active_company_id = fields.Many2one(
        comodel_name="res.partner",
        string="Empresa activa",
        domain=[("is_company", "=", True)],
        index=True,
    )

    phone = fields.Char(
        string="Teléfono",
        index=True,
    )

    jid = fields.Char(
        string="JID",
        index=True,
    )

    lid = fields.Char(
        string="LID",
        index=True,
    )

    raw_jid = fields.Char(
        string="Raw JID",
    )

    state = fields.Selection(
        selection=[
            ("open", "Abierta"),
            ("human", "Modo humano"),
            ("closed", "Cerrada"),
            ("expired", "Expirada"),
        ],
        string="Estado",
        default="open",
        required=True,
        index=True,
    )

    source = fields.Selection(
        selection=[
            ("whatsapp", "WhatsApp"),
            ("n8n", "n8n"),
            ("api", "API"),
            ("manual", "Manual"),
        ],
        string="Origen",
        default="whatsapp",
    )

    started_at = fields.Datetime(
        string="Inicio",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    last_message_at = fields.Datetime(
        string="Último mensaje",
        default=fields.Datetime.now,
        index=True,
    )

    closed_at = fields.Datetime(
        string="Cierre",
    )

    last_intent = fields.Char(
        string="Última intención",
        index=True,
    )

    last_user_message = fields.Text(
        string="Último mensaje del cliente",
        readonly=True,
    )

    last_bot_message = fields.Text(
        string="Último mensaje del bot",
        readonly=True,
    )

    message_ids = fields.One2many(
        comodel_name="whatsapp.message",
        inverse_name="session_id",
        string="Mensajes",
    )

    message_count = fields.Integer(
        string="Cantidad de mensajes",
        compute="_compute_message_count",
        store=False,
    )

    is_active = fields.Boolean(
        string="Sesión activa",
        compute="_compute_is_active",
        store=False,
    )

    note = fields.Text(
        string="Notas internas",
    )

    @api.depends("message_ids")
    def _compute_message_count(self):
        for session in self:
            session.message_count = len(session.message_ids)

    @api.depends("state")
    def _compute_is_active(self):
        for session in self:
            session.is_active = session.state in ("open", "human")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Nueva sesión")) == _("Nueva sesión"):
                vals["name"] = self.env["ir.sequence"].next_by_code("whatsapp.session") or _("Nueva sesión")
        return super().create(vals_list)

    def action_close(self):
        for session in self:
            session.write({
                "state": "closed",
                "closed_at": fields.Datetime.now(),
            })

    def action_expire(self):
        for session in self:
            session.write({
                "state": "expired",
                "closed_at": fields.Datetime.now(),
            })

    def action_set_human(self):
        for session in self:
            session.write({
                "state": "human",
            })

    def action_reopen(self):
        for session in self:
            session.write({
                "state": "open",
                "closed_at": False,
            })

    def touch(self, intent=False, user_message=False, bot_message=False):
        vals = {
            "last_message_at": fields.Datetime.now(),
        }

        if intent:
            vals["last_intent"] = intent

        if user_message:
            vals["last_user_message"] = user_message

        if bot_message:
            vals["last_bot_message"] = bot_message

        self.write(vals)
        return True