# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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
    # WhatsApp / Baileys IDs
    # ==========================================================
    whatsapp_jid = fields.Char(
        string="WhatsApp JID",
        index=True,
        help="JID normal de WhatsApp. Ejemplo: 51999999999@s.whatsapp.net",
    )

    whatsapp_lid = fields.Char(
        string="WhatsApp LID",
        index=True,
        help="Identificador LID de WhatsApp/Baileys cuando no llega el número real.",
    )

    whatsapp_last_raw_jid = fields.Char(
        string="Último JID recibido",
        readonly=True,
        help="Último identificador bruto recibido desde Baileys.",
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
    # Permisos base
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

    whatsapp_human_by_name = fields.Char(
        string="Tomado por nombre",
        readonly=True,
        help="Nombre externo enviado por n8n/API cuando el modo humano se activa desde fuera de Odoo.",
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
    # Multiempresa WhatsApp
    # ==========================================================
    whatsapp_company_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="res_partner_whatsapp_company_rel",
        column1="contact_id",
        column2="company_id",
        string="Empresas WhatsApp asociadas",
        domain=[("is_company", "=", True)],
        help="Empresas para las que este contacto puede gestionar solicitudes por WhatsApp.",
    )

    whatsapp_active_company_id = fields.Many2one(
        comodel_name="res.partner",
        string="Empresa activa WhatsApp",
        domain=[("is_company", "=", True)],
        help="Empresa que se usará por defecto en la atención WhatsApp.",
    )

    # ==========================================================
    # Campos calculados para API / lógica
    # ==========================================================
    whatsapp_can_bot_respond = fields.Boolean(
        string="Bot puede responder",
        compute="_compute_whatsapp_effective_state",
        store=False,
    )

    whatsapp_can_use_ai_effective = fields.Boolean(
        string="Puede usar IA efectivo",
        compute="_compute_whatsapp_effective_state",
        store=False,
    )

    whatsapp_can_auto_response_effective = fields.Boolean(
        string="Puede usar autorespuesta efectivo",
        compute="_compute_whatsapp_effective_state",
        store=False,
    )

    whatsapp_can_create_ticket_effective = fields.Boolean(
        string="Puede crear ticket efectivo",
        compute="_compute_whatsapp_effective_state",
        store=False,
    )

    whatsapp_status_label = fields.Char(
        string="Estado WhatsApp",
        compute="_compute_whatsapp_effective_state",
        store=False,
    )

    whatsapp_requires_company_selection = fields.Boolean(
        string="Requiere seleccionar empresa",
        compute="_compute_whatsapp_company_context",
        store=False,
    )

    whatsapp_company_count = fields.Integer(
        string="Cantidad empresas WhatsApp",
        compute="_compute_whatsapp_company_context",
        store=False,
    )

    # ==========================================================
    # Computes
    # ==========================================================
    @api.depends(
        "whatsapp_enabled",
        "whatsapp_blocked",
        "whatsapp_access_level",
        "whatsapp_human_mode",
        "whatsapp_allow_ai",
        "whatsapp_allow_auto_response",
        "whatsapp_allow_ticket",
        "whatsapp_allow_odoo_lookup",
        "whatsapp_allow_human_transfer",
    )
    def _compute_whatsapp_effective_state(self):
        for partner in self:
            enabled = bool(partner.whatsapp_enabled)
            blocked = bool(partner.whatsapp_blocked) or partner.whatsapp_access_level == "blocked"
            human_mode = bool(partner.whatsapp_human_mode)

            can_bot_respond = enabled and not blocked and not human_mode

            partner.whatsapp_can_bot_respond = can_bot_respond

            partner.whatsapp_can_use_ai_effective = (
                can_bot_respond
                and bool(partner.whatsapp_allow_ai)
                and partner.whatsapp_access_level in ("standard", "vip", "info_only")
            )

            partner.whatsapp_can_auto_response_effective = (
                can_bot_respond
                and bool(partner.whatsapp_allow_auto_response)
                and partner.whatsapp_access_level in ("restricted", "info_only", "standard", "vip")
            )

            partner.whatsapp_can_create_ticket_effective = (
                can_bot_respond
                and bool(partner.whatsapp_allow_ticket)
                and partner.whatsapp_access_level in ("standard", "vip")
            )

            if not enabled:
                partner.whatsapp_status_label = "WhatsApp deshabilitado"
            elif blocked:
                partner.whatsapp_status_label = "Bloqueado"
            elif human_mode:
                partner.whatsapp_status_label = "Modo humano"
            elif partner.whatsapp_access_level == "restricted":
                partner.whatsapp_status_label = "Restringido"
            elif partner.whatsapp_access_level == "info_only":
                partner.whatsapp_status_label = "Solo información"
            elif partner.whatsapp_access_level == "vip":
                partner.whatsapp_status_label = "VIP"
            else:
                partner.whatsapp_status_label = "Activo"

    @api.depends("whatsapp_company_ids", "whatsapp_active_company_id", "is_company", "parent_id")
    def _compute_whatsapp_company_context(self):
        for partner in self:
            companies = partner._get_whatsapp_available_companies()
            partner.whatsapp_company_count = len(companies)
            partner.whatsapp_requires_company_selection = (
                not partner.is_company
                and len(companies) > 1
                and not partner.whatsapp_active_company_id
            )

    # ==========================================================
    # Onchange
    # ==========================================================
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

    @api.onchange("whatsapp_blocked")
    def _onchange_whatsapp_blocked(self):
        for partner in self:
            if partner.whatsapp_blocked:
                partner.whatsapp_access_level = "blocked"
                partner.whatsapp_allow_ai = False
                partner.whatsapp_allow_ticket = False
                partner.whatsapp_allow_odoo_lookup = False
                partner.whatsapp_allow_human_transfer = False
                partner.whatsapp_allow_auto_response = True
            elif partner.whatsapp_access_level == "blocked":
                partner.whatsapp_access_level = "standard"
                partner.whatsapp_block_reason = False
                partner.whatsapp_allow_ai = True
                partner.whatsapp_allow_auto_response = True
                partner.whatsapp_allow_ticket = True
                partner.whatsapp_allow_odoo_lookup = True
                partner.whatsapp_allow_human_transfer = True

    @api.onchange("whatsapp_access_level")
    def _onchange_whatsapp_access_level(self):
        for partner in self:
            if partner.whatsapp_access_level == "blocked":
                partner.whatsapp_blocked = True
                partner.whatsapp_allow_ai = False
                partner.whatsapp_allow_ticket = False
                partner.whatsapp_allow_odoo_lookup = False
                partner.whatsapp_allow_human_transfer = False
                partner.whatsapp_allow_auto_response = True

            elif partner.whatsapp_access_level == "restricted":
                partner.whatsapp_blocked = False
                partner.whatsapp_block_reason = False
                partner.whatsapp_allow_ai = False
                partner.whatsapp_allow_ticket = False
                partner.whatsapp_allow_odoo_lookup = False
                partner.whatsapp_allow_human_transfer = False
                partner.whatsapp_allow_auto_response = True

            elif partner.whatsapp_access_level == "info_only":
                partner.whatsapp_blocked = False
                partner.whatsapp_block_reason = False
                partner.whatsapp_allow_ai = True
                partner.whatsapp_allow_ticket = False
                partner.whatsapp_allow_odoo_lookup = True
                partner.whatsapp_allow_human_transfer = False
                partner.whatsapp_allow_auto_response = True

            elif partner.whatsapp_access_level == "standard":
                partner.whatsapp_blocked = False
                partner.whatsapp_block_reason = False
                partner.whatsapp_allow_ai = True
                partner.whatsapp_allow_auto_response = True
                partner.whatsapp_allow_ticket = True
                partner.whatsapp_allow_odoo_lookup = True
                partner.whatsapp_allow_human_transfer = True

            elif partner.whatsapp_access_level == "vip":
                partner.whatsapp_blocked = False
                partner.whatsapp_block_reason = False
                partner.whatsapp_allow_ai = True
                partner.whatsapp_allow_auto_response = True
                partner.whatsapp_allow_ticket = True
                partner.whatsapp_allow_odoo_lookup = True
                partner.whatsapp_allow_human_transfer = True

    @api.onchange("whatsapp_company_ids")
    def _onchange_whatsapp_company_ids(self):
        for partner in self:
            companies = partner._get_whatsapp_available_companies()

            if partner.whatsapp_active_company_id and partner.whatsapp_active_company_id not in companies:
                partner.whatsapp_active_company_id = False

            if not partner.whatsapp_active_company_id and len(companies) == 1:
                partner.whatsapp_active_company_id = companies[0]

    # ==========================================================
    # Constraints
    # ==========================================================
    @api.constrains("whatsapp_session_timeout_minutes")
    def _check_whatsapp_session_timeout_minutes(self):
        for partner in self:
            if partner.whatsapp_session_timeout_minutes < 1:
                raise ValidationError(_("El tiempo de nueva sesión debe ser mayor a 0 minutos."))

    @api.constrains("whatsapp_active_company_id", "whatsapp_company_ids", "parent_id", "is_company")
    def _check_whatsapp_active_company_id(self):
        for partner in self:
            active_company = partner.whatsapp_active_company_id
            if not active_company:
                continue

            if not active_company.is_company:
                raise ValidationError(_("La empresa activa WhatsApp debe ser un contacto marcado como empresa."))

            available_companies = partner._get_whatsapp_available_companies()
            if active_company not in available_companies:
                raise ValidationError(
                    _("La empresa activa debe estar asociada al contacto para WhatsApp o ser su empresa padre.")
                )

    # ==========================================================
    # Create / Write
    # ==========================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._prepare_whatsapp_vals(vals)

        partners = super().create(vals_list)
        partners._ensure_whatsapp_consistency()
        return partners

    def write(self, vals):
        vals = dict(vals or {})

        if self.env.context.get("skip_whatsapp_consistency"):
            return super().write(vals)

        self._prepare_whatsapp_vals(vals)

        result = super().write(vals)
        self._ensure_whatsapp_consistency()
        return result

    def _prepare_whatsapp_vals(self, vals):
        if not vals:
            return vals

        if vals.get("mobile") and not vals.get("whatsapp_number"):
            vals.setdefault("whatsapp_number", vals.get("mobile"))

        if vals.get("phone") and not vals.get("whatsapp_number"):
            vals.setdefault("whatsapp_number", vals.get("phone"))

        if vals.get("whatsapp_blocked"):
            vals["whatsapp_access_level"] = "blocked"
            vals["whatsapp_allow_ai"] = False
            vals["whatsapp_allow_ticket"] = False
            vals["whatsapp_allow_odoo_lookup"] = False
            vals["whatsapp_allow_human_transfer"] = False
            vals.setdefault("whatsapp_allow_auto_response", True)

        if vals.get("whatsapp_access_level") == "blocked":
            vals["whatsapp_blocked"] = True
            vals["whatsapp_allow_ai"] = False
            vals["whatsapp_allow_ticket"] = False
            vals["whatsapp_allow_odoo_lookup"] = False
            vals["whatsapp_allow_human_transfer"] = False
            vals.setdefault("whatsapp_allow_auto_response", True)

        if vals.get("whatsapp_access_level") in ("restricted", "info_only", "standard", "vip"):
            vals.setdefault("whatsapp_blocked", False)

        return vals

    def _ensure_whatsapp_consistency(self):
        for partner in self:
            patch = {}

            if partner.whatsapp_blocked and partner.whatsapp_access_level != "blocked":
                patch["whatsapp_access_level"] = "blocked"

            if partner.whatsapp_access_level == "blocked" and not partner.whatsapp_blocked:
                patch["whatsapp_blocked"] = True

            if partner.whatsapp_blocked:
                if partner.whatsapp_allow_ai:
                    patch["whatsapp_allow_ai"] = False
                if partner.whatsapp_allow_ticket:
                    patch["whatsapp_allow_ticket"] = False
                if partner.whatsapp_allow_odoo_lookup:
                    patch["whatsapp_allow_odoo_lookup"] = False
                if partner.whatsapp_allow_human_transfer:
                    patch["whatsapp_allow_human_transfer"] = False

            if not partner.whatsapp_blocked and partner.whatsapp_access_level != "blocked":
                if partner.whatsapp_block_reason:
                    patch["whatsapp_block_reason"] = False

            companies = partner._get_whatsapp_available_companies()

            if partner.whatsapp_active_company_id and partner.whatsapp_active_company_id not in companies:
                patch["whatsapp_active_company_id"] = False

            if not partner.is_company and not partner.whatsapp_active_company_id and len(companies) == 1:
                patch["whatsapp_active_company_id"] = companies.id

            if patch:
                partner.with_context(skip_whatsapp_consistency=True).write(patch)

    # ==========================================================
    # Acciones
    # ==========================================================
    def action_whatsapp_enable_human_mode(self):
        for partner in self:
            partner.write({
                "whatsapp_human_mode": True,
                "whatsapp_human_since": fields.Datetime.now(),
                "whatsapp_human_by_id": self.env.user.id,
                "whatsapp_human_by_name": self.env.user.name,
            })

    def action_whatsapp_release_human_mode(self):
        for partner in self:
            partner.write({
                "whatsapp_human_mode": False,
                "whatsapp_human_since": False,
                "whatsapp_human_by_id": False,
                "whatsapp_human_by_name": False,
            })

    def action_whatsapp_block(self):
        for partner in self:
            partner.write({
                "whatsapp_blocked": True,
                "whatsapp_access_level": "blocked",
            })

    def action_whatsapp_unblock(self):
        for partner in self:
            partner.write({
                "whatsapp_blocked": False,
                "whatsapp_block_reason": False,
                "whatsapp_access_level": "standard",
                "whatsapp_allow_ai": True,
                "whatsapp_allow_auto_response": True,
                "whatsapp_allow_ticket": True,
                "whatsapp_allow_odoo_lookup": True,
                "whatsapp_allow_human_transfer": True,
            })

    def whatsapp_enable_human_mode_api(self, taken_by_name=False):
        for partner in self:
            partner.write({
                "whatsapp_human_mode": True,
                "whatsapp_human_since": fields.Datetime.now(),
                "whatsapp_human_by_id": False,
                "whatsapp_human_by_name": taken_by_name or "API / n8n",
            })

    def whatsapp_release_human_mode_api(self):
        for partner in self:
            partner.write({
                "whatsapp_human_mode": False,
                "whatsapp_human_since": False,
                "whatsapp_human_by_id": False,
                "whatsapp_human_by_name": False,
            })

    # ==========================================================
    # Identificadores WhatsApp / Baileys
    # ==========================================================
    def whatsapp_update_identifiers(self, jid=False, lid=False, raw_jid=False):
        for partner in self:
            vals = {}

            if jid and partner.whatsapp_jid != jid:
                vals["whatsapp_jid"] = jid

            if lid and partner.whatsapp_lid != lid:
                vals["whatsapp_lid"] = lid

            if raw_jid:
                vals["whatsapp_last_raw_jid"] = raw_jid

            if vals:
                partner.write(vals)

        return True

    # ==========================================================
    # Helpers empresas
    # ==========================================================
    def _get_whatsapp_available_companies(self):
        self.ensure_one()

        companies = self.env["res.partner"]

        if self.is_company:
            companies |= self

        if self.parent_id and self.parent_id.is_company:
            companies |= self.parent_id

        companies |= self.whatsapp_company_ids.filtered(lambda partner: partner.is_company)

        return companies

    def whatsapp_set_active_company(self, company):
        self.ensure_one()

        if not company:
            self.whatsapp_active_company_id = False
            return True

        if not company.is_company:
            raise ValidationError(_("La empresa seleccionada no está marcada como empresa."))

        available_companies = self._get_whatsapp_available_companies()

        if company not in available_companies:
            raise ValidationError(_("La empresa seleccionada no está asociada a este contacto para WhatsApp."))

        self.whatsapp_active_company_id = company.id
        return True

    # ==========================================================
    # Sesión / conversación
    # ==========================================================
    def whatsapp_touch_message(self, intent=False, force_new_session=False):
        now = fields.Datetime.now()

        for partner in self:
            vals = {
                "whatsapp_last_message_at": now,
            }

            if intent:
                vals["whatsapp_last_intent"] = intent

            if force_new_session or partner._whatsapp_is_session_expired(now):
                vals["whatsapp_last_session_at"] = now

            partner.write(vals)

    def _whatsapp_is_session_expired(self, now=None):
        self.ensure_one()

        if not self.whatsapp_last_message_at:
            return True

        now_dt = fields.Datetime.to_datetime(now or fields.Datetime.now())
        last_dt = fields.Datetime.to_datetime(self.whatsapp_last_message_at)

        diff_seconds = (now_dt - last_dt).total_seconds()
        timeout_seconds = max(self.whatsapp_session_timeout_minutes or 480, 1) * 60

        return diff_seconds > timeout_seconds

    # ==========================================================
    # Payload API / n8n
    # ==========================================================
    def get_whatsapp_profile_payload(self):
        self.ensure_one()

        companies = self._get_whatsapp_available_companies()
        active_company = self.whatsapp_active_company_id

        payload_companies = []
        for company in companies:
            payload_companies.append({
                "id": company.id,
                "name": company.name,
                "vat": company.vat,
                "phone": company.phone,
                "mobile": company.mobile,
                "email": company.email,
                "is_company": company.is_company,
            })

        human_user_name = False
        if self.whatsapp_human_by_id:
            human_user_name = self.whatsapp_human_by_id.name
        elif self.whatsapp_human_by_name:
            human_user_name = self.whatsapp_human_by_name

        block_reason = self.whatsapp_block_reason if self.whatsapp_blocked else False

        return {
            "partner_id": self.id,
            "name": self.name,
            "is_company": self.is_company,
            "company_type": self.company_type,
            "vat": self.vat,
            "phone": self.phone,
            "mobile": self.mobile,
            "email": self.email,

            "whatsapp": {
                "number": self.whatsapp_number,
                "jid": self.whatsapp_jid,
                "lid": self.whatsapp_lid,
                "last_raw_jid": self.whatsapp_last_raw_jid,
                "enabled": self.whatsapp_enabled,
                "verified": self.whatsapp_verified,
                "blocked": self.whatsapp_blocked,
                "block_reason": block_reason,
                "access_level": self.whatsapp_access_level,
                "status_label": self.whatsapp_status_label,
            },

            "permissions": {
                "allow_ai": self.whatsapp_allow_ai,
                "allow_auto_response": self.whatsapp_allow_auto_response,
                "allow_ticket": self.whatsapp_allow_ticket,
                "allow_odoo_lookup": self.whatsapp_allow_odoo_lookup,
                "allow_human_transfer": self.whatsapp_allow_human_transfer,
                "can_bot_respond": self.whatsapp_can_bot_respond,
                "can_use_ai": self.whatsapp_can_use_ai_effective,
                "can_auto_response": self.whatsapp_can_auto_response_effective,
                "can_create_ticket": self.whatsapp_can_create_ticket_effective,
            },

            "human_mode": {
                "active": self.whatsapp_human_mode,
                "since": self.whatsapp_human_since,
                "user_id": self.whatsapp_human_by_id.id if self.whatsapp_human_by_id else False,
                "user_name": human_user_name,
            },

            "conversation": {
                "last_message_at": self.whatsapp_last_message_at,
                "last_session_at": self.whatsapp_last_session_at,
                "last_intent": self.whatsapp_last_intent,
                "session_timeout_minutes": self.whatsapp_session_timeout_minutes,
                "is_new_session": self._whatsapp_is_session_expired(),
            },

            "companies": {
                "count": len(companies),
                "requires_selection": self.whatsapp_requires_company_selection,
                "active_company_id": active_company.id if active_company else False,
                "active_company_name": active_company.name if active_company else False,
                "items": payload_companies,
            },
        }