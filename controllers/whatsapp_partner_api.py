# -*- coding: utf-8 -*-

import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WhatsAppPartnerApiController(http.Controller):
    """
    API para que n8n / servicio WhatsApp consulte y actualice datos WhatsApp en Odoo.

    Rutas:
    - POST /sat/whatsapp/profile
    - POST /sat/whatsapp/touch
    - POST /sat/whatsapp/human/take
    - POST /sat/whatsapp/human/release
    - POST /sat/whatsapp/company/select
    """

    # ==========================================================
    # Helpers base
    # ==========================================================
    def _get_json_payload(self):
        try:
            if hasattr(request, "get_json_data"):
                return request.get_json_data() or {}
        except Exception:
            pass

        try:
            return request.jsonrequest or {}
        except Exception:
            return {}

    def _json_error(self, message, code="ERROR", status=200):
        return {
            "ok": False,
            "code": code,
            "status": status,
            "message": message,
        }

    def _check_token(self):
        token = request.env["ir.config_parameter"].sudo().get_param(
            "sat.whatsapp_api_token"
        )

        if not token:
            _logger.warning(
                "[SAT-WHATSAPP-API] Falta configurar ir.config_parameter: sat.whatsapp_api_token"
            )
            return False

        auth_header = request.httprequest.headers.get("Authorization", "")
        expected = "Bearer %s" % token

        if auth_header != expected:
            _logger.warning("[SAT-WHATSAPP-API] Token inválido o ausente")
            return False

        return True

    # ==========================================================
    # Helpers teléfono / JID / LID
    # ==========================================================
    def _clean_phone(self, value):
        value = value or ""
        value = str(value).strip()

        if not value:
            return ""

        lowered = value.lower()

        # Si es LID puro, no lo tratamos como teléfono.
        if "@lid" in lowered:
            return ""

        # Si es JID normal, extraer parte antes de @.
        if "@s.whatsapp.net" in lowered or "@c.us" in lowered:
            value = value.split("@", 1)[0]

        digits = re.sub(r"\D+", "", value)

        if not digits:
            return ""

        digits = digits.lstrip("0")

        # Perú: si llega 9 dígitos, agregar 51.
        if len(digits) == 9:
            digits = "51" + digits

        return digits

    def _normalize_jid(self, value):
        value = (value or "").strip()
        return value or ""

    def _is_lid(self, value):
        value = (value or "").lower().strip()
        return "@lid" in value or value.endswith(".lid")

    def _is_normal_whatsapp_jid(self, value):
        value = (value or "").lower().strip()
        return "@s.whatsapp.net" in value or "@c.us" in value

    def _extract_identifiers(self, payload):
        """
        Acepta payloads como:
        {
            "phone": "51999999999",
            "jid": "51999999999@s.whatsapp.net",
            "lid": "123456789@lid",
            "raw_jid": "..."
        }

        También soporta:
        {
            "from": "51999999999@s.whatsapp.net"
        }

        o:
        {
            "from": "123456789@lid"
        }
        """
        phone = (
            payload.get("phone")
            or payload.get("whatsapp_number")
            or payload.get("number")
        )

        incoming_from = payload.get("from") or payload.get("remoteJid") or payload.get("remote_jid")
        jid = payload.get("jid") or payload.get("remote_jid")
        lid = payload.get("lid") or payload.get("remote_lid")
        raw_jid = payload.get("raw_jid") or incoming_from or jid or lid

        # Si "from" viene como jid normal.
        if incoming_from and self._is_normal_whatsapp_jid(incoming_from):
            jid = jid or incoming_from
            phone = phone or incoming_from

        # Si "from" viene como lid.
        if incoming_from and self._is_lid(incoming_from):
            lid = lid or incoming_from

        # Si jid en realidad es lid.
        if jid and self._is_lid(jid):
            lid = lid or jid
            jid = False

        clean_phone = self._clean_phone(phone)
        clean_jid = self._normalize_jid(jid)
        clean_lid = self._normalize_jid(lid)
        clean_raw_jid = self._normalize_jid(raw_jid)

        return {
            "phone": clean_phone,
            "jid": clean_jid,
            "lid": clean_lid,
            "raw_jid": clean_raw_jid,
        }

    # ==========================================================
    # Buscar partner
    # ==========================================================
    def _find_partner_by_phone(self, clean_phone):
        Partner = request.env["res.partner"].sudo()

        if not clean_phone:
            return Partner

        last9 = clean_phone[-9:]

        candidates = Partner.search([
            "|", "|", "|",
            ("whatsapp_number", "ilike", last9),
            ("mobile", "ilike", last9),
            ("phone", "ilike", last9),
            ("whatsapp_jid", "ilike", clean_phone),
        ], limit=50)

        if not candidates:
            return Partner

        # Prioridad 1: coincidencia exacta normalizada.
        for partner in candidates:
            numbers = [
                partner.whatsapp_number,
                partner.mobile,
                partner.phone,
            ]

            for number in numbers:
                if self._clean_phone(number) == clean_phone:
                    return partner

        # Prioridad 2: JID contiene teléfono exacto.
        for partner in candidates:
            if partner.whatsapp_jid and clean_phone in partner.whatsapp_jid:
                return partner

        return candidates[:1]

    def _find_partner_by_identifiers(self, identifiers):
        Partner = request.env["res.partner"].sudo()

        clean_phone = identifiers.get("phone")
        clean_jid = identifiers.get("jid")
        clean_lid = identifiers.get("lid")
        raw_jid = identifiers.get("raw_jid")

        # 1) Buscar por teléfono.
        if clean_phone:
            partner = self._find_partner_by_phone(clean_phone)
            if partner:
                return partner

        # 2) Buscar por JID normal.
        if clean_jid:
            partner = Partner.search([("whatsapp_jid", "=", clean_jid)], limit=1)
            if partner:
                return partner

        # 3) Buscar por LID.
        if clean_lid:
            partner = Partner.search([("whatsapp_lid", "=", clean_lid)], limit=1)
            if partner:
                return partner

        # 4) Si raw_jid es lid, buscar por whatsapp_lid.
        if raw_jid and self._is_lid(raw_jid):
            partner = Partner.search([("whatsapp_lid", "=", raw_jid)], limit=1)
            if partner:
                return partner

        # 5) Si raw_jid es jid normal, buscar por whatsapp_jid.
        if raw_jid and self._is_normal_whatsapp_jid(raw_jid):
            partner = Partner.search([("whatsapp_jid", "=", raw_jid)], limit=1)
            if partner:
                return partner

        return Partner

    def _update_partner_identifiers(self, partner, identifiers):
        if not partner:
            return

        partner.whatsapp_update_identifiers(
            jid=identifiers.get("jid"),
            lid=identifiers.get("lid"),
            raw_jid=identifiers.get("raw_jid"),
        )

    # ==========================================================
    # 1) Consultar perfil WhatsApp por número / JID / LID
    # ==========================================================
    @http.route(
        "/sat/whatsapp/profile",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_profile(self, **kwargs):
        if not self._check_token():
            return self._json_error("No autorizado", "UNAUTHORIZED", 401)

        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not identifiers.get("phone") and not identifiers.get("jid") and not identifiers.get("lid") and not identifiers.get("raw_jid"):
            return self._json_error(
                "Número, JID o LID requerido",
                "IDENTIFIER_REQUIRED",
                400,
            )

        partner = self._find_partner_by_identifiers(identifiers)

        if not partner:
            return {
                "ok": True,
                "found": False,
                "phone": identifiers.get("phone"),
                "jid": identifiers.get("jid"),
                "lid": identifiers.get("lid"),
                "raw_jid": identifiers.get("raw_jid"),
                "profile": None,
                "message": "Contacto no encontrado",
            }

        self._update_partner_identifiers(partner, identifiers)

        return {
            "ok": True,
            "found": True,
            "phone": identifiers.get("phone"),
            "jid": identifiers.get("jid"),
            "lid": identifiers.get("lid"),
            "raw_jid": identifiers.get("raw_jid"),
            "partner_id": partner.id,
            "profile": partner.get_whatsapp_profile_payload(),
        }

    # ==========================================================
    # 2) Actualizar última actividad / sesión
    # ==========================================================
    @http.route(
        "/sat/whatsapp/touch",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_touch(self, **kwargs):
        if not self._check_token():
            return self._json_error("No autorizado", "UNAUTHORIZED", 401)

        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        intent = payload.get("intent") or False
        force_new_session = bool(payload.get("force_new_session"))

        if not identifiers.get("phone") and not identifiers.get("jid") and not identifiers.get("lid") and not identifiers.get("raw_jid"):
            return self._json_error(
                "Número, JID o LID requerido",
                "IDENTIFIER_REQUIRED",
                400,
            )

        partner = self._find_partner_by_identifiers(identifiers)

        if not partner:
            return {
                "ok": True,
                "found": False,
                "phone": identifiers.get("phone"),
                "jid": identifiers.get("jid"),
                "lid": identifiers.get("lid"),
                "message": "Contacto no encontrado. No se actualizó sesión.",
            }

        self._update_partner_identifiers(partner, identifiers)

        partner.whatsapp_touch_message(
            intent=intent,
            force_new_session=force_new_session,
        )

        return {
            "ok": True,
            "found": True,
            "phone": identifiers.get("phone"),
            "jid": identifiers.get("jid"),
            "lid": identifiers.get("lid"),
            "partner_id": partner.id,
            "profile": partner.get_whatsapp_profile_payload(),
        }

    # ==========================================================
    # 3) Tomar chat humano
    # ==========================================================
    @http.route(
        "/sat/whatsapp/human/take",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_human_take(self, **kwargs):
        if not self._check_token():
            return self._json_error("No autorizado", "UNAUTHORIZED", 401)

        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)
        taken_by_name = payload.get("taken_by_name") or payload.get("agent_name") or "API / n8n"

        if not identifiers.get("phone") and not identifiers.get("jid") and not identifiers.get("lid") and not identifiers.get("raw_jid"):
            return self._json_error(
                "Número, JID o LID requerido",
                "IDENTIFIER_REQUIRED",
                400,
            )

        partner = self._find_partner_by_identifiers(identifiers)

        if not partner:
            return {
                "ok": True,
                "found": False,
                "phone": identifiers.get("phone"),
                "jid": identifiers.get("jid"),
                "lid": identifiers.get("lid"),
                "message": "Contacto no encontrado. No se activó modo humano.",
            }

        self._update_partner_identifiers(partner, identifiers)

        partner.whatsapp_enable_human_mode_api(
            taken_by_name=taken_by_name,
        )

        return {
            "ok": True,
            "found": True,
            "phone": identifiers.get("phone"),
            "jid": identifiers.get("jid"),
            "lid": identifiers.get("lid"),
            "partner_id": partner.id,
            "profile": partner.get_whatsapp_profile_payload(),
        }

    # ==========================================================
    # 4) Liberar bot
    # ==========================================================
    @http.route(
        "/sat/whatsapp/human/release",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_human_release(self, **kwargs):
        if not self._check_token():
            return self._json_error("No autorizado", "UNAUTHORIZED", 401)

        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        if not identifiers.get("phone") and not identifiers.get("jid") and not identifiers.get("lid") and not identifiers.get("raw_jid"):
            return self._json_error(
                "Número, JID o LID requerido",
                "IDENTIFIER_REQUIRED",
                400,
            )

        partner = self._find_partner_by_identifiers(identifiers)

        if not partner:
            return {
                "ok": True,
                "found": False,
                "phone": identifiers.get("phone"),
                "jid": identifiers.get("jid"),
                "lid": identifiers.get("lid"),
                "message": "Contacto no encontrado. No se liberó modo humano.",
            }

        self._update_partner_identifiers(partner, identifiers)

        partner.whatsapp_release_human_mode_api()

        return {
            "ok": True,
            "found": True,
            "phone": identifiers.get("phone"),
            "jid": identifiers.get("jid"),
            "lid": identifiers.get("lid"),
            "partner_id": partner.id,
            "profile": partner.get_whatsapp_profile_payload(),
        }

    # ==========================================================
    # 5) Seleccionar empresa activa
    # ==========================================================
    @http.route(
        "/sat/whatsapp/company/select",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_company_select(self, **kwargs):
        if not self._check_token():
            return self._json_error("No autorizado", "UNAUTHORIZED", 401)

        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        company_id = payload.get("company_id")

        if not identifiers.get("phone") and not identifiers.get("jid") and not identifiers.get("lid") and not identifiers.get("raw_jid"):
            return self._json_error(
                "Número, JID o LID requerido",
                "IDENTIFIER_REQUIRED",
                400,
            )

        if not company_id:
            return self._json_error(
                "company_id requerido",
                "COMPANY_REQUIRED",
                400,
            )

        partner = self._find_partner_by_identifiers(identifiers)

        if not partner:
            return {
                "ok": True,
                "found": False,
                "phone": identifiers.get("phone"),
                "jid": identifiers.get("jid"),
                "lid": identifiers.get("lid"),
                "message": "Contacto no encontrado. No se seleccionó empresa.",
            }

        self._update_partner_identifiers(partner, identifiers)

        try:
            company_id = int(company_id)
        except Exception:
            return self._json_error(
                "company_id inválido",
                "COMPANY_INVALID",
                400,
            )

        company = request.env["res.partner"].sudo().browse(company_id).exists()

        if not company:
            return self._json_error(
                "Empresa no encontrada",
                "COMPANY_NOT_FOUND",
                404,
            )

        try:
            partner.whatsapp_set_active_company(company)
        except Exception as e:
            _logger.exception("[SAT-WHATSAPP-API] Error seleccionando empresa activa")
            return self._json_error(
                str(e),
                "COMPANY_SELECTION_ERROR",
                400,
            )

        return {
            "ok": True,
            "found": True,
            "phone": identifiers.get("phone"),
            "jid": identifiers.get("jid"),
            "lid": identifiers.get("lid"),
            "partner_id": partner.id,
            "active_company_id": company.id,
            "active_company_name": company.name,
            "profile": partner.get_whatsapp_profile_payload(),
        }