from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # ==========================================================
    # WhatsApp - configuración básica
    # ==========================================================
    whatsapp_enabled = fields.Boolean(
        string="WhatsApp habilitado",
        default=True,
        help="Permite que este contacto o empresa sea atendido por WhatsApp.",
    )

    whatsapp_number = fields.Char(
        string="Número WhatsApp",
        help="Número principal usado para atención por WhatsApp.",
    )

    whatsapp_verified = fields.Boolean(
        string="WhatsApp verificado",
        default=False,
        help="Indica si el número WhatsApp fue validado.",
    )

    whatsapp_notes = fields.Text(
        string="Notas WhatsApp",
        help="Notas internas para la atención por WhatsApp.",
    )

    # ==========================================================
    # Bloqueo / acceso
    # ==========================================================
    whatsapp_blocked = fields.Boolean(
        string="Bloqueado en WhatsApp",
        default=False,
        help="Si está activo, el bot no debe atender normalmente a este contacto.",
    )

    whatsapp_block_reason = fields.Text(
        string="Motivo de bloqueo",
    )

    whatsapp_access_level = fields.Selection(
        selection=[
            ("blocked", "Bloqueado"),
            ("restricted", "Restringido"),
            ("info_only", "Solo información"),
            ("standard", "Estándar"),
            ("vip", "VIP"),
        ],
        string="Nivel de acceso WhatsApp",
        default="standard",
        required=True,
    )

    # ==========================================================
    # Permisos
    # ==========================================================
    whatsapp_allow_ai = fields.Boolean(
        string="Permitir IA",
        default=True,
    )

    whatsapp_allow_auto_response = fields.Boolean(
        string="Permitir respuestas automáticas",
        default=True,
    )

    whatsapp_allow_ticket = fields.Boolean(
        string="Permitir crear tickets",
        default=True,
    )

    whatsapp_allow_odoo_lookup = fields.Boolean(
        string="Permitir consulta en Odoo",
        default=True,
    )

    whatsapp_allow_human_transfer = fields.Boolean(
        string="Permitir derivar a humano",
        default=True,
    )

    # ==========================================================
    # Modo humano
    # ==========================================================
    whatsapp_human_mode = fields.Boolean(
        string="Modo humano activo",
        default=False,
        help="Cuando está activo, el bot no debe responder automáticamente.",
    )

    whatsapp_human_since = fields.Datetime(
        string="Modo humano desde",
        readonly=True,
    )

    whatsapp_human_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Tomado por",
        readonly=True,
    )

    # ==========================================================
    # Contexto conversacional
    # ==========================================================
    whatsapp_last_message_at = fields.Datetime(
        string="Último mensaje WhatsApp",
        readonly=True,
    )

    whatsapp_last_session_at = fields.Datetime(
        string="Inicio última sesión",
        readonly=True,
    )

    whatsapp_last_intent = fields.Char(
        string="Última intención detectada",
        readonly=True,
    )

    whatsapp_session_timeout_minutes = fields.Integer(
        string="Tiempo nueva sesión (min)",
        default=480,
        help="Minutos de inactividad para considerar una nueva conversación. 480 = 8 horas.",
    )

    # ==========================================================
    # Multiempresa para contactos/personas
    # ==========================================================
    whatsapp_company_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="res_partner_whatsapp_company_rel",
        column1="contact_id",
        column2="company_id",
        string="Empresas WhatsApp asociadas",
        domain=[("company_type", "=", "company")],
        help="Empresas para las que este contacto puede gestionar solicitudes por WhatsApp.",
    )

    whatsapp_active_company_id = fields.Many2one(
        comodel_name="res.partner",
        string="Empresa activa WhatsApp",
        domain=[("company_type", "=", "company")],
        help="Empresa que se usará por defecto en la atención WhatsApp.",
    )

    # ==========================================================
    # Helpers
    # ==========================================================
    def action_whatsapp_enable_human_mode(self):
        for partner in self:
            partner.write({
                "whatsapp_human_mode": True,
                "whatsapp_human_since": fields.Datetime.now(),
                "whatsapp_human_by_id": self.env.user.id,
            })

    def action_whatsapp_release_human_mode(self):
        for partner in self:
            partner.write({
                "whatsapp_human_mode": False,
                "whatsapp_human_since": False,
                "whatsapp_human_by_id": False,
            })

    @api.onchange("mobile")
    def _onchange_mobile_set_whatsapp_number(self):
        for partner in self:
            if partner.mobile and not partner.whatsapp_number:
                partner.whatsapp_number = partner.mobile

    @api.onchange("phone")
    def _onchange_phone_set_whatsapp_number(self):
        for partner in self:
            if partner.phone and not partner.whatsapp_number:
                partner.whatsapp_number = partner.phone

    def get_whatsapp_profile_payload(self):
        self.ensure_one()

        return {
            "partner_id": self.id,
            "name": self.name,
            "company_type": self.company_type,
            "vat": self.vat,
            "phone": self.phone,
            "mobile": self.mobile,
            "whatsapp_number": self.whatsapp_number,
            "whatsapp_enabled": self.whatsapp_enabled,
            "whatsapp_verified": self.whatsapp_verified,
            "whatsapp_blocked": self.whatsapp_blocked,
            "whatsapp_block_reason": self.whatsapp_block_reason,
            "whatsapp_access_level": self.whatsapp_access_level,
            "whatsapp_allow_ai": self.whatsapp_allow_ai,
            "whatsapp_allow_auto_response": self.whatsapp_allow_auto_response,
            "whatsapp_allow_ticket": self.whatsapp_allow_ticket,
            "whatsapp_allow_odoo_lookup": self.whatsapp_allow_odoo_lookup,
            "whatsapp_allow_human_transfer": self.whatsapp_allow_human_transfer,
            "whatsapp_human_mode": self.whatsapp_human_mode,
            "whatsapp_human_since": self.whatsapp_human_since,
            "whatsapp_human_by_id": self.whatsapp_human_by_id.id if self.whatsapp_human_by_id else False,
            "whatsapp_last_message_at": self.whatsapp_last_message_at,
            "whatsapp_last_session_at": self.whatsapp_last_session_at,
            "whatsapp_last_intent": self.whatsapp_last_intent,
            "whatsapp_session_timeout_minutes": self.whatsapp_session_timeout_minutes,
            "whatsapp_active_company_id": self.whatsapp_active_company_id.id if self.whatsapp_active_company_id else False,
            "whatsapp_company_ids": self.whatsapp_company_ids.ids,
        }