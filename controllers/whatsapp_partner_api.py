# -*- coding: utf-8 -*-
import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WhatsAppPartnerApiController(http.Controller):
    """
    API para que n8n / servicio WhatsApp consulte datos de res.partner.

    Este controlador NO maneja Baileys.
    Solo consulta y actualiza datos WhatsApp en Odoo.
    """

    # ==========================================================
    # Helpers
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

    def _clean_phone(self, value):
        value = value or ""
        digits = re.sub(r"\D+", "", str(value))

        if not digits:
            return ""

        digits = digits.lstrip("0")

        # Perú: si llega 9 dígitos, agregar 51
        if len(digits) == 9:
            digits = "51" + digits

        return digits

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

    def _find_partner_by_phone(self, phone):
        clean = self._clean_phone(phone)
        Partner = request.env["res.partner"].sudo()

        if not clean:
            return Partner

        last9 = clean[-9:]

        candidates = Partner.search([
            "|", "|",
            ("whatsapp_number", "ilike", last9),
            ("mobile", "ilike", last9),
            ("phone", "ilike", last9),
        ], limit=30)

        if not candidates:
            return Partner

        # Priorizar coincidencia exacta por dígitos normalizados
        for partner in candidates:
            for number in [partner.whatsapp_number, partner.mobile, partner.phone]:
                if self._clean_phone(number) == clean:
                    return partner

        return candidates[:1]

    # ==========================================================
    # 1) Consultar perfil WhatsApp por número
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
        phone = (
            payload.get("phone")
            or payload.get("whatsapp_number")
            or payload.get("from")
        )

        clean_phone = self._clean_phone(phone)

        if not clean_phone:
            return self._json_error(
                "Número WhatsApp requerido",
                "PHONE_REQUIRED",
                400,
            )

        partner = self._find_partner_by_phone(clean_phone)

        if not partner:
            return {
                "ok": True,
                "found": False,
                "phone": clean_phone,
                "profile": None,
                "message": "Contacto no encontrado",
            }

        return {
            "ok": True,
            "found": True,
            "phone": clean_phone,
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
        phone = (
            payload.get("phone")
            or payload.get("whatsapp_number")
            or payload.get("from")
        )
        intent = payload.get("intent") or False
        force_new_session = bool(payload.get("force_new_session"))

        clean_phone = self._clean_phone(phone)

        if not clean_phone:
            return self._json_error(
                "Número WhatsApp requerido",
                "PHONE_REQUIRED",
                400,
            )

        partner = self._find_partner_by_phone(clean_phone)

        if not partner:
            return {
                "ok": True,
                "found": False,
                "phone": clean_phone,
                "message": "Contacto no encontrado. No se actualizó sesión.",
            }

        partner.whatsapp_touch_message(
            intent=intent,
            force_new_session=force_new_session,
        )

        return {
            "ok": True,
            "found": True,
            "phone": clean_phone,
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
        phone = (
            payload.get("phone")
            or payload.get("whatsapp_number")
            or payload.get("from")
        )

        clean_phone = self._clean_phone(phone)

        if not clean_phone:
            return self._json_error(
                "Número WhatsApp requerido",
                "PHONE_REQUIRED",
                400,
            )

        partner = self._find_partner_by_phone(clean_phone)

        if not partner:
            return {
                "ok": True,
                "found": False,
                "phone": clean_phone,
                "message": "Contacto no encontrado. No se activó modo humano.",
            }

        partner.action_whatsapp_enable_human_mode()

        return {
            "ok": True,
            "found": True,
            "phone": clean_phone,
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
        phone = (
            payload.get("phone")
            or payload.get("whatsapp_number")
            or payload.get("from")
        )

        clean_phone = self._clean_phone(phone)

        if not clean_phone:
            return self._json_error(
                "Número WhatsApp requerido",
                "PHONE_REQUIRED",
                400,
            )

        partner = self._find_partner_by_phone(clean_phone)

        if not partner:
            return {
                "ok": True,
                "found": False,
                "phone": clean_phone,
                "message": "Contacto no encontrado. No se liberó modo humano.",
            }

        partner.action_whatsapp_release_human_mode()

        return {
            "ok": True,
            "found": True,
            "phone": clean_phone,
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
        phone = (
            payload.get("phone")
            or payload.get("whatsapp_number")
            or payload.get("from")
        )
        company_id = payload.get("company_id")

        clean_phone = self._clean_phone(phone)

        if not clean_phone:
            return self._json_error(
                "Número WhatsApp requerido",
                "PHONE_REQUIRED",
                400,
            )

        if not company_id:
            return self._json_error(
                "company_id requerido",
                "COMPANY_REQUIRED",
                400,
            )

        partner = self._find_partner_by_phone(clean_phone)

        if not partner:
            return {
                "ok": True,
                "found": False,
                "phone": clean_phone,
                "message": "Contacto no encontrado. No se seleccionó empresa.",
            }

        company = request.env["res.partner"].sudo().browse(int(company_id)).exists()

        if not company:
            return self._json_error(
                "Empresa no encontrada",
                "COMPANY_NOT_FOUND",
                404,
            )

        partner.whatsapp_set_active_company(company)

        return {
            "ok": True,
            "found": True,
            "phone": clean_phone,
            "partner_id": partner.id,
            "active_company_id": company.id,
            "active_company_name": company.name,
            "profile": partner.get_whatsapp_profile_payload(),
        }