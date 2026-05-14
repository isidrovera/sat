# -*- coding: utf-8 -*-

import logging
import re

from odoo import http
from odoo.http import request
from odoo.exceptions import UserError, ValidationError

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
    - POST /sat/whatsapp/register/dni
    - POST /sat/whatsapp/register/ruc
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

    def _json_error(self, message, code="ERROR", status=200, extra=None):
        data = {
            "ok": False,
            "code": code,
            "status": status,
            "message": message,
        }
        if extra:
            data.update(extra)
        return data

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
    def _only_digits(self, value):
        return re.sub(r"\D+", "", str(value or ""))

    def _clean_phone(self, value):
        value = value or ""
        value = str(value).strip()

        if not value:
            return ""

        lowered = value.lower()

        if "@lid" in lowered:
            return ""

        if "@s.whatsapp.net" in lowered or "@c.us" in lowered:
            value = value.split("@", 1)[0]

        digits = re.sub(r"\D+", "", value)

        if not digits:
            return ""

        digits = digits.lstrip("0")

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
        phone = (
            payload.get("phone")
            or payload.get("whatsapp_number")
            or payload.get("number")
        )

        incoming_from = (
            payload.get("from")
            or payload.get("remoteJid")
            or payload.get("remote_jid")
        )

        jid = payload.get("jid") or payload.get("remote_jid")
        lid = payload.get("lid") or payload.get("remote_lid")
        raw_jid = payload.get("raw_jid") or incoming_from or jid or lid

        if incoming_from and self._is_normal_whatsapp_jid(incoming_from):
            jid = jid or incoming_from
            phone = phone or incoming_from

        if incoming_from and self._is_lid(incoming_from):
            lid = lid or incoming_from

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

    def _has_any_identifier(self, identifiers):
        return bool(
            identifiers.get("phone")
            or identifiers.get("jid")
            or identifiers.get("lid")
            or identifiers.get("raw_jid")
        )

    # ==========================================================
    # Helpers documento DNI/RUC
    # ==========================================================
    def _get_latam_doc_type(self, code=None, name=None):
        DocType = request.env["l10n_latam.identification.type"].sudo()

        if code:
            doc_type = DocType.search([("l10n_pe_vat_code", "=", code)], limit=1)
            if doc_type:
                return doc_type

        if name:
            doc_type = DocType.search([("name", "=", name)], limit=1)
            if doc_type:
                return doc_type

        return DocType

    def _get_dni_type(self):
        return self._get_latam_doc_type(code="1", name="DNI")

    def _get_ruc_type(self):
        return self._get_latam_doc_type(code="6", name="RUC")

    def _run_partner_document_autoload(self, partner):
        """
        Usa la lógica existente del módulo SUNAT/DNI en res.partner.

        Ese módulo carga datos desde _doc_number_change(), que llama:
        - ConsultarDNI para DNI
        - ValidarRUC / ConsultarRUC / CheckGoodTaxpayer / CheckRetentionAgent para RUC
        """
        if hasattr(partner, "_doc_number_change"):
            partner._doc_number_change()
            return True
        return False

    def _prepare_partner_whatsapp_values(self, identifiers):
        vals = {}

        phone = identifiers.get("phone")
        jid = identifiers.get("jid")
        lid = identifiers.get("lid")
        raw_jid = identifiers.get("raw_jid")

        if phone:
            vals["mobile"] = "+%s" % phone if not str(phone).startswith("+") else phone
            vals["whatsapp_number"] = phone

        if jid:
            vals["whatsapp_jid"] = jid

        if lid:
            vals["whatsapp_lid"] = lid

        if raw_jid:
            vals["whatsapp_last_raw_jid"] = raw_jid

        return vals

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

        for partner in candidates:
            numbers = [
                partner.whatsapp_number,
                partner.mobile,
                partner.phone,
            ]

            for number in numbers:
                if self._clean_phone(number) == clean_phone:
                    return partner

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

        if clean_phone:
            partner = self._find_partner_by_phone(clean_phone)
            if partner:
                return partner

        if clean_jid:
            partner = Partner.search([("whatsapp_jid", "=", clean_jid)], limit=1)
            if partner:
                return partner

        if clean_lid:
            partner = Partner.search([("whatsapp_lid", "=", clean_lid)], limit=1)
            if partner:
                return partner

        if raw_jid and self._is_lid(raw_jid):
            partner = Partner.search([("whatsapp_lid", "=", raw_jid)], limit=1)
            if partner:
                return partner

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

        if not self._has_any_identifier(identifiers):
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

        if not self._has_any_identifier(identifiers):
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

        if not self._has_any_identifier(identifiers):
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

        if not self._has_any_identifier(identifiers):
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

        if not self._has_any_identifier(identifiers):
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

    # ==========================================================
    # 6) Registrar / actualizar contacto por DNI
    # ==========================================================
    @http.route(
        "/sat/whatsapp/register/dni",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_register_dni(self, **kwargs):
        if not self._check_token():
            return self._json_error("No autorizado", "UNAUTHORIZED", 401)

        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        dni = self._only_digits(
            payload.get("dni")
            or payload.get("vat")
            or payload.get("document_number")
        )

        if len(dni) != 8:
            return self._json_error(
                "DNI inválido. Debe tener 8 dígitos.",
                "INVALID_DNI",
                400,
            )

        if not self._has_any_identifier(identifiers):
            return self._json_error(
                "Número, JID o LID requerido",
                "IDENTIFIER_REQUIRED",
                400,
            )

        Partner = request.env["res.partner"].sudo()
        dni_type = self._get_dni_type()

        if not dni_type:
            return self._json_error(
                "No se encontró tipo de documento DNI en Odoo.",
                "DNI_TYPE_NOT_FOUND",
                500,
            )

        partner_by_identifier = self._find_partner_by_identifiers(identifiers)

        partner_by_dni = Partner.search([
            ("vat", "=", dni),
            ("l10n_latam_identification_type_id", "=", dni_type.id),
        ], limit=1)

        if partner_by_identifier and partner_by_dni and partner_by_identifier.id != partner_by_dni.id:
            return self._json_error(
                "El DNI ya está asociado a otro contacto.",
                "DNI_ALREADY_LINKED",
                409,
                extra={
                    "existing_partner_id": partner_by_dni.id,
                    "identifier_partner_id": partner_by_identifier.id,
                },
            )

        partner = partner_by_identifier or partner_by_dni

        if partner and partner.vat and partner.vat != dni:
            return self._json_error(
                "El contacto encontrado ya tiene otro documento registrado.",
                "DOCUMENT_CONFLICT",
                409,
                extra={
                    "partner_id": partner.id,
                    "current_vat": partner.vat,
                    "received_dni": dni,
                },
            )

        vals = self._prepare_partner_whatsapp_values(identifiers)
        vals.update({
            "company_type": "person",
            "is_company": False,
            "l10n_latam_identification_type_id": dni_type.id,
            "vat": dni,
            "whatsapp_enabled": True,
            "whatsapp_registration_state": "waiting_ruc",
        })

        try:
            if not partner:
                vals.setdefault("name", "DNI %s" % dni)
                partner = Partner.create(vals)
            else:
                partner.write(vals)

            self._update_partner_identifiers(partner, identifiers)

            try:
                self._run_partner_document_autoload(partner)
            except Exception as e:
                _logger.exception("[SAT-WHATSAPP-API] Error cargando datos DNI")
                partner.write({"whatsapp_registration_state": "manual_review"})
                return self._json_error(
                    "No se pudo consultar o cargar el DNI automáticamente.",
                    "DNI_AUTOLOAD_ERROR",
                    400,
                    extra={
                        "detail": str(e),
                        "partner_id": partner.id,
                        "profile": partner.get_whatsapp_profile_payload(),
                    },
                )

            partner.write({"whatsapp_registration_state": "waiting_ruc"})

            return {
                "ok": True,
                "found": True,
                "registered_dni": True,
                "next_step": "waiting_ruc",
                "message": "DNI registrado correctamente. Solicitar RUC.",
                "phone": identifiers.get("phone"),
                "jid": identifiers.get("jid"),
                "lid": identifiers.get("lid"),
                "partner_id": partner.id,
                "profile": partner.get_whatsapp_profile_payload(),
            }

        except Exception as e:
            _logger.exception("[SAT-WHATSAPP-API] Error registrando DNI")
            return self._json_error(
                str(e),
                "DNI_REGISTER_ERROR",
                500,
            )

    # ==========================================================
    # 7) Registrar / buscar empresa por RUC y asociar al contacto
    # ==========================================================
    @http.route(
        "/sat/whatsapp/register/ruc",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def whatsapp_register_ruc(self, **kwargs):
        if not self._check_token():
            return self._json_error("No autorizado", "UNAUTHORIZED", 401)

        payload = self._get_json_payload()
        identifiers = self._extract_identifiers(payload)

        ruc = self._only_digits(
            payload.get("ruc")
            or payload.get("vat")
            or payload.get("document_number")
        )

        if len(ruc) != 11:
            return self._json_error(
                "RUC inválido. Debe tener 11 dígitos.",
                "INVALID_RUC",
                400,
            )

        if not self._has_any_identifier(identifiers):
            return self._json_error(
                "Número, JID o LID requerido",
                "IDENTIFIER_REQUIRED",
                400,
            )

        Partner = request.env["res.partner"].sudo()
        ruc_type = self._get_ruc_type()

        if not ruc_type:
            return self._json_error(
                "No se encontró tipo de documento RUC en Odoo.",
                "RUC_TYPE_NOT_FOUND",
                500,
            )

        contact = self._find_partner_by_identifiers(identifiers)

        if not contact:
            return self._json_error(
                "Primero debe registrarse el contacto con DNI.",
                "CONTACT_NOT_FOUND",
                404,
            )

        self._update_partner_identifiers(contact, identifiers)

        company = Partner.search([
            ("vat", "=", ruc),
            ("l10n_latam_identification_type_id", "=", ruc_type.id),
            ("is_company", "=", True),
        ], limit=1)

        company_created = False

        try:
            if not company:
                company = Partner.create({
                    "name": "RUC %s" % ruc,
                    "is_company": True,
                    "company_type": "company",
                    "l10n_latam_identification_type_id": ruc_type.id,
                    "vat": ruc,
                    "whatsapp_enabled": True,
                    "whatsapp_registration_state": "registered",
                })
                company_created = True
            else:
                company.write({
                    "is_company": True,
                    "company_type": "company",
                    "l10n_latam_identification_type_id": ruc_type.id,
                    "vat": ruc,
                    "whatsapp_enabled": True,
                })

            try:
                self._run_partner_document_autoload(company)
            except Exception as e:
                _logger.exception("[SAT-WHATSAPP-API] Error cargando datos RUC")
                company.write({"whatsapp_registration_state": "manual_review"})
                return self._json_error(
                    "No se pudo consultar o cargar el RUC automáticamente.",
                    "RUC_AUTOLOAD_ERROR",
                    400,
                    extra={
                        "detail": str(e),
                        "company_id": company.id,
                        "contact_id": contact.id,
                        "company_created": company_created,
                        "profile": contact.get_whatsapp_profile_payload(),
                    },
                )

            contact.write({
                "whatsapp_company_ids": [(4, company.id)],
                "whatsapp_active_company_id": company.id,
                "whatsapp_registration_state": "registered",
            })

            company.write({
                "whatsapp_registration_state": "registered",
            })

            return {
                "ok": True,
                "found": True,
                "registered_ruc": True,
                "company_created": company_created,
                "next_step": "registered",
                "message": "RUC registrado correctamente. Contacto asociado a empresa.",
                "phone": identifiers.get("phone"),
                "jid": identifiers.get("jid"),
                "lid": identifiers.get("lid"),
                "partner_id": contact.id,
                "company_id": company.id,
                "company_name": company.name,
                "profile": contact.get_whatsapp_profile_payload(),
            }

        except Exception as e:
            _logger.exception("[SAT-WHATSAPP-API] Error registrando RUC")
            return self._json_error(
                str(e),
                "RUC_REGISTER_ERROR",
                500,
            )