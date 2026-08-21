# -*- coding: utf-8 -*-

import logging
import re

from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppPartnerMixin:
    """
    Identificación, registro y selección de empresa para WhatsApp.

    Se conserva la lógica existente de:
    - normalización de teléfono, JID y LID;
    - búsqueda y actualización de res.partner;
    - registro mediante DNI y RUC;
    - asociación de empresas;
    - empresa activa.

    Las mejoras de esta versión se concentran en presentación,
    navegación y recuperación segura dentro de la selección de empresa.
    """

    # ==========================================================
    # Teléfono / JID / LID
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

    def _phone_from_jid(self, value):
        value = (value or "").strip()
        if not value:
            return ""

        lowered = value.lower()

        if "@lid" in lowered:
            return ""

        if "@s.whatsapp.net" in lowered or "@c.us" in lowered:
            value = value.split("@", 1)[0]

        return self._clean_phone(value)

    def _resolve_identifier_phone(self, identifiers, partner=False):
        identifiers = identifiers or {}

        phone = self._clean_phone(identifiers.get("phone"))
        if phone:
            return phone

        phone = self._phone_from_jid(identifiers.get("jid"))
        if phone:
            return phone

        phone = self._phone_from_jid(identifiers.get("raw_jid"))
        if phone:
            return phone

        if partner:
            phone = self._clean_phone(getattr(partner, "whatsapp_number", False))
            if phone:
                return phone

            phone = self._phone_from_jid(getattr(partner, "whatsapp_jid", False))
            if phone:
                return phone

            phone = self._clean_phone(getattr(partner, "mobile", False))
            if phone:
                return phone

            phone = self._clean_phone(getattr(partner, "phone", False))
            if phone:
                return phone

        return ""

    def _resolve_identifier_jid(self, identifiers, partner=False):
        identifiers = identifiers or {}

        jid = identifiers.get("jid")
        if jid and self._is_normal_whatsapp_jid(jid):
            return self._normalize_jid(jid)

        raw_jid = identifiers.get("raw_jid")
        if raw_jid and self._is_normal_whatsapp_jid(raw_jid):
            return self._normalize_jid(raw_jid)

        if partner and getattr(partner, "whatsapp_jid", False):
            return self._normalize_jid(partner.whatsapp_jid)

        return ""

    def _resolve_identifier_lid(self, identifiers, partner=False):
        identifiers = identifiers or {}

        lid = identifiers.get("lid")
        if lid and self._is_lid(lid):
            return self._normalize_jid(lid)

        raw_jid = identifiers.get("raw_jid")
        if raw_jid and self._is_lid(raw_jid):
            return self._normalize_jid(raw_jid)

        if partner and getattr(partner, "whatsapp_lid", False):
            return self._normalize_jid(partner.whatsapp_lid)

        return ""

    def _resolve_identifier_raw_jid(self, identifiers, partner=False):
        identifiers = identifiers or {}

        raw_jid = identifiers.get("raw_jid")
        if raw_jid:
            return self._normalize_jid(raw_jid)

        jid = self._resolve_identifier_jid(identifiers, partner=partner)
        if jid:
            return jid

        lid = self._resolve_identifier_lid(identifiers, partner=partner)
        if lid:
            return lid

        if partner and getattr(partner, "whatsapp_last_raw_jid", False):
            return self._normalize_jid(partner.whatsapp_last_raw_jid)

        return ""

    def _extract_identifiers(self, payload):
        payload = payload or {}

        phone = (
            payload.get("phone")
            or payload.get("whatsapp_number")
            or payload.get("number")
        )

        incoming_from = (
            payload.get("from")
            or payload.get("remoteJid")
            or payload.get("remote_jid")
            or payload.get("raw_jid")
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

        if raw_jid and self._is_normal_whatsapp_jid(raw_jid):
            jid = jid or raw_jid
            phone = phone or raw_jid

        if raw_jid and self._is_lid(raw_jid):
            lid = lid or raw_jid

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
    # DNI / RUC
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
        if hasattr(partner, "_doc_number_change"):
            partner._doc_number_change()
            return True
        return False

    def _prepare_partner_whatsapp_values(self, identifiers, partner=False):
        identifiers = identifiers or {}
        vals = {}

        phone = self._resolve_identifier_phone(identifiers, partner=partner)
        jid = self._resolve_identifier_jid(identifiers, partner=partner)
        lid = self._resolve_identifier_lid(identifiers, partner=partner)
        raw_jid = self._resolve_identifier_raw_jid(identifiers, partner=partner)

        if phone:
            vals["whatsapp_number"] = phone

            formatted_phone = "+%s" % phone if not str(phone).startswith("+") else phone

            if "phone" in request.env["res.partner"]._fields:
                if not partner or not getattr(partner, "phone", False):
                    vals["phone"] = formatted_phone

            if "mobile" in request.env["res.partner"]._fields:
                if not partner or not getattr(partner, "mobile", False):
                    vals["mobile"] = formatted_phone

        if jid:
            vals["whatsapp_jid"] = jid

        if lid:
            vals["whatsapp_lid"] = lid

        if raw_jid:
            vals["whatsapp_last_raw_jid"] = raw_jid

        return vals

    # ==========================================================
    # Buscar contacto
    # ==========================================================
    def _find_partner_by_phone(self, clean_phone):
        Partner = request.env["res.partner"].sudo().with_context(active_test=False)

        clean_phone = self._clean_phone(clean_phone)

        if not clean_phone:
            return Partner

        last9 = clean_phone[-9:] if len(clean_phone) >= 9 else clean_phone

        _logger.info(
            "[WA-PARTNER] Buscando partner por teléfono normalizado SQL | clean_phone=%s last9=%s",
            clean_phone,
            last9,
        )

        # ======================================================
        # 1) Búsqueda exacta por campos WhatsApp sin formato
        # ======================================================
        partner = Partner.search([
            "|", "|",
            ("whatsapp_number", "=", clean_phone),
            ("whatsapp_jid", "=", "%s@s.whatsapp.net" % clean_phone),
            ("whatsapp_jid", "ilike", clean_phone),
        ], limit=1)

        if partner:
            _logger.info(
                "[WA-PARTNER] Partner encontrado por campos WhatsApp | partner_id=%s name=%s",
                partner.id,
                partner.name,
            )
            return partner

        # ======================================================
        # 2) Búsqueda SQL normalizando phone, mobile y whatsapp_number.
        #
        # Esto permite encontrar:
        # +51 924 894 829
        # 51 924 894 829
        # 924 894 829
        # 924-894-829
        # (924) 894829
        #
        # Comparando contra:
        # 51924894829
        # 924894829
        # ======================================================
        query = """
            SELECT id
            FROM res_partner
            WHERE
                (
                    regexp_replace(coalesce(phone, ''), '\\D', '', 'g') = %s
                    OR regexp_replace(coalesce(mobile, ''), '\\D', '', 'g') = %s
                    OR regexp_replace(coalesce(whatsapp_number, ''), '\\D', '', 'g') = %s

                    OR right(regexp_replace(coalesce(phone, ''), '\\D', '', 'g'), 9) = %s
                    OR right(regexp_replace(coalesce(mobile, ''), '\\D', '', 'g'), 9) = %s
                    OR right(regexp_replace(coalesce(whatsapp_number, ''), '\\D', '', 'g'), 9) = %s

                    OR whatsapp_jid ILIKE %s
                )
            ORDER BY
                CASE
                    WHEN regexp_replace(coalesce(whatsapp_number, ''), '\\D', '', 'g') = %s THEN 1
                    WHEN right(regexp_replace(coalesce(whatsapp_number, ''), '\\D', '', 'g'), 9) = %s THEN 2
                    WHEN regexp_replace(coalesce(mobile, ''), '\\D', '', 'g') = %s THEN 3
                    WHEN right(regexp_replace(coalesce(mobile, ''), '\\D', '', 'g'), 9) = %s THEN 4
                    WHEN regexp_replace(coalesce(phone, ''), '\\D', '', 'g') = %s THEN 5
                    WHEN right(regexp_replace(coalesce(phone, ''), '\\D', '', 'g'), 9) = %s THEN 6
                    ELSE 99
                END,
                active DESC,
                id ASC
            LIMIT 1
        """

        params = (
            clean_phone,
            clean_phone,
            clean_phone,
            last9,
            last9,
            last9,
            "%" + clean_phone + "%",
            clean_phone,
            last9,
            clean_phone,
            last9,
            clean_phone,
            last9,
        )

        try:
            request.env.cr.execute(query, params)
            row = request.env.cr.fetchone()
        except Exception:
            _logger.exception(
                "[WA-PARTNER] Error buscando partner por teléfono SQL | clean_phone=%s last9=%s",
                clean_phone,
                last9,
            )
            row = False

        if row:
            partner = Partner.browse(row[0]).exists()
            if partner:
                _logger.info(
                    "[WA-PARTNER] Partner encontrado por teléfono SQL normalizado | partner_id=%s name=%s phone=%s mobile=%s whatsapp_number=%s",
                    partner.id,
                    partner.name,
                    partner.phone,
                    partner.mobile,
                    partner.whatsapp_number,
                )
                return partner

        _logger.warning(
            "[WA-PARTNER] No se encontró partner por teléfono SQL normalizado | clean_phone=%s last9=%s",
            clean_phone,
            last9,
        )

        return Partner

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

        identifiers = identifiers or {}

        vals = self._prepare_partner_whatsapp_values(
            identifiers,
            partner=partner,
        )

        safe_vals = {}
        for key, value in vals.items():
            if value:
                safe_vals[key] = value

        if safe_vals:
            try:
                partner.sudo().write(safe_vals)
            except Exception:
                _logger.exception(
                    "[SAT-WHATSAPP-API] No se pudo actualizar identificadores WhatsApp partner=%s vals=%s",
                    partner.id,
                    safe_vals,
                )

        if hasattr(partner, "whatsapp_update_identifiers"):
            try:
                partner.whatsapp_update_identifiers(
                    phone=self._resolve_identifier_phone(identifiers, partner=partner),
                    jid=self._resolve_identifier_jid(identifiers, partner=partner),
                    lid=self._resolve_identifier_lid(identifiers, partner=partner),
                    raw_jid=self._resolve_identifier_raw_jid(identifiers, partner=partner),
                )
            except TypeError:
                partner.whatsapp_update_identifiers(
                    jid=self._resolve_identifier_jid(identifiers, partner=partner),
                    lid=self._resolve_identifier_lid(identifiers, partner=partner),
                    raw_jid=self._resolve_identifier_raw_jid(identifiers, partner=partner),
                )

    # ==========================================================
    # Registro inline para /process
    # ==========================================================
    def _register_dni_inline(self, identifiers, dni, payload=False):
        Partner = request.env["res.partner"].sudo()
        partner = self._find_partner_by_identifiers(identifiers)

        vals = self._prepare_partner_whatsapp_values(identifiers, partner=partner)
        vals["vat"] = dni
        vals["whatsapp_registration_state"] = "waiting_ruc"

        dni_type = self._get_dni_type()
        if dni_type and "l10n_latam_identification_type_id" in Partner._fields:
            vals["l10n_latam_identification_type_id"] = dni_type.id

        if not partner:
            vals.setdefault("name", "DNI %s" % dni)
            partner = Partner.create(vals)
        else:
            partner.write(vals)

        self._update_partner_identifiers(partner, identifiers)

        try:
            self._run_partner_document_autoload(partner)
        except Exception:
            _logger.exception("[SAT-WHATSAPP-API] Error cargando datos DNI")
            partner.write({"whatsapp_registration_state": "manual_review"})

        session = self._get_or_create_session(partner, identifiers, intent="dni")

        message = self._render_template(
            "ask_ruc",
            partner=partner,
            session=session,
            fallback=(
                "Gracias. ✅\n\n"
                "Ahora envíanos el *RUC de 11 dígitos* de la empresa "
                "con la que deseas realizar la atención.\n\n"
                "🏠 Escribe *MENU* para volver al menú principal."
            ),
        )

        return partner, session, message

    def _register_ruc_inline(self, contact, identifiers, ruc, payload=False):
        Partner = request.env["res.partner"].sudo()

        company = Partner.search([("vat", "=", ruc), ("is_company", "=", True)], limit=1)
        company_created = False

        if not company:
            vals = {
                "name": "RUC %s" % ruc,
                "vat": ruc,
                "is_company": True,
                "company_type": "company",
                "whatsapp_registration_state": "registered",
            }

            ruc_type = self._get_ruc_type()
            if ruc_type and "l10n_latam_identification_type_id" in Partner._fields:
                vals["l10n_latam_identification_type_id"] = ruc_type.id

            company = Partner.create(vals)
            company_created = True

            try:
                self._run_partner_document_autoload(company)
            except Exception:
                _logger.exception("[SAT-WHATSAPP-API] Error cargando datos RUC")

        contact.write({
            "whatsapp_company_ids": [(4, company.id)],
            "whatsapp_active_company_id": company.id,
            "whatsapp_registration_state": "registered",
        })

        company.write({
            "whatsapp_registration_state": "registered",
        })

        session = self._get_or_create_session(contact, identifiers, intent="ruc")
        session.write({"active_company_id": company.id})

        message = self._render_template(
            "registration_completed",
            partner=contact,
            session=session,
            company=company,
            fallback=(
                "✅ *Registro completado correctamente*\n\n"
                "La empresa quedó asociada a tu contacto.\n\n"
                "Escribe *MENU* para ver las opciones disponibles."
            ),
        )

        return company, session, message, company_created

    # ==========================================================
    # Selección de empresa
    # ==========================================================
    def _company_selection_message(self, partner, session=False):
        """
        Construye la selección de empresa sin modificar la lógica de
        asociación existente.

        Si existe una sola empresa, se mantiene la selección automática.
        Si existen varias, se inicia el flujo registration /
        awaiting_company_selection.
        """
        if not partner:
            return (
                "⚠️ No pude identificar el contacto asociado a esta "
                "conversación.\n\n"
                "Escribe *MENU* para iniciar nuevamente."
            )

        partner_name = (
            partner.name.split()[0]
            if partner.name
            else "cliente"
        )

        companies = partner.whatsapp_company_ids

        # ------------------------------------------------------
        # Sin empresas asociadas
        # ------------------------------------------------------
        if not companies:
            return self._render_template(
                "ask_ruc",
                partner=partner,
                session=session,
                fallback=(
                    "🏢 *Registro de empresa*\n\n"
                    "No encontré una empresa asociada a tu contacto. "
                    "Para continuar, envíanos el *RUC de 11 dígitos*.\n\n"
                    "🏠 Escribe *MENU* para volver al menú principal."
                ),
            )

        # ------------------------------------------------------
        # Una sola empresa: selección automática
        # ------------------------------------------------------
        if len(companies) == 1:
            company = companies[0]

            try:
                partner.whatsapp_set_active_company(
                    company
                )
            except Exception:
                _logger.exception(
                    "[WA-COMPANY] Error asignando empresa única | "
                    "partner_id=%s company_id=%s",
                    partner.id if partner else False,
                    company.id if company else False,
                )

            if session:
                try:
                    session.write({
                        "active_company_id": company.id,
                    })
                    session.reset_conversation(
                        reason="company_selected"
                    )
                except Exception:
                    _logger.exception(
                        "[WA-COMPANY] Error actualizando sesión "
                        "para empresa única | session_id=%s "
                        "company_id=%s",
                        session.id if session else False,
                        company.id if company else False,
                    )

            return (
                "✅ *Empresa activa*\n\n"
                "🏢 *%s*\n"
                "%s\n\n"
                "%s"
            ) % (
                company.name or "Empresa",
                (
                    "RUC: %s" % company.vat
                    if company.vat
                    else ""
                ),
                self._build_main_menu_text(
                    partner=partner,
                    session=session,
                ),
            )

        # ------------------------------------------------------
        # Varias empresas
        # ------------------------------------------------------
        options = []

        lines = [
            "🏢 *Seleccionar empresa*",
            "",
            "Hola, %s. 👋" % partner_name,
            "",
            "Estas son las empresas asociadas a tu contacto:",
            "",
        ]

        active_company_id = (
            partner.whatsapp_active_company_id.id
            if partner.whatsapp_active_company_id
            else False
        )

        for idx, company in enumerate(
            companies,
            start=1,
        ):
            is_active = bool(
                active_company_id
                and company.id == active_company_id
            )

            options.append({
                "id": company.id,
                "name": company.name or "",
                "vat": company.vat or "",
            })

            active_label = (
                " ✅ Actual"
                if is_active
                else ""
            )

            lines.append(
                "*%s* 🏢 %s%s"
                % (
                    idx,
                    company.name
                    or "Empresa sin nombre",
                    active_label,
                )
            )

            if company.vat:
                lines.append(
                    "RUC: %s"
                    % company.vat
                )

            lines.append("")

        lines.extend([
            "Responde con el *número* de la empresa que deseas utilizar.",
            "",
            "La empresa seleccionada se utilizará para las solicitudes "
            "de tóner, servicio técnico y demás gestiones realizadas "
            "por este chat.",
            "",
            "↩️ Escribe *ATRÁS* para regresar.",
            "🏠 Escribe *MENU* para volver al menú principal.",
            "❌ Escribe *CANCELAR* para cancelar la selección.",
        ])

        if session:
            try:
                session.start_flow(
                    "registration",
                    "awaiting_company_selection",
                    context={
                        "intent": "select_company",
                        "company_options": options,
                    },
                )

                _logger.info(
                    "[WA-COMPANY] Flujo de selección iniciado | "
                    "partner_id=%s session_id=%s options=%s "
                    "active_company_id=%s",
                    partner.id if partner else False,
                    session.id if session else False,
                    len(options),
                    active_company_id,
                )

            except Exception:
                _logger.exception(
                    "[WA-COMPANY] Error iniciando flujo selección | "
                    "partner_id=%s session_id=%s",
                    partner.id if partner else False,
                    session.id if session else False,
                )

        return "\n".join(lines)

    def _continue_company_selection(
        self,
        partner,
        session,
        text,
    ):
        """
        Continúa el flujo de selección de empresa.

        MENU, CANCELAR y ATRÁS son compatibles aquí de forma defensiva.
        Normalmente los comandos globales son interceptados previamente por
        whatsapp_flow_mixin.py.
        """
        if not partner:
            _logger.warning(
                "[WA-COMPANY] Continuación sin partner"
            )
            return (
                "⚠️ No pude identificar el contacto asociado a esta "
                "conversación.\n\n"
                "Escribe *MENU* para comenzar nuevamente."
            )

        if not session:
            _logger.warning(
                "[WA-COMPANY] Continuación sin session | "
                "partner_id=%s",
                partner.id,
            )
            return (
                "⚠️ No pude recuperar la sesión activa.\n\n"
                "Escribe *MENU* para comenzar nuevamente."
            )

        text_clean = (
            text
            or ""
        ).strip()

        text_lower = text_clean.lower()

        _logger.info(
            "[WA-COMPANY] Continuando selección | "
            "partner_id=%s session_id=%s text=%s",
            partner.id if partner else False,
            session.id if session else False,
            text_clean[:200],
        )

        # ------------------------------------------------------
        # ATRÁS
        # ------------------------------------------------------
        if text_lower in [
            "atras",
            "atrás",
            "volver",
            "regresar",
            "retroceder",
        ]:
            try:
                session.reset_conversation(
                    reason="company_selection_back"
                )
            except Exception:
                _logger.exception(
                    "[WA-COMPANY] Error procesando ATRÁS | "
                    "session_id=%s",
                    session.id if session else False,
                )

            return self._build_main_menu_text(
                partner=partner,
                session=session,
            )

        # ------------------------------------------------------
        # MENU
        # ------------------------------------------------------
        if text_lower in [
            "menu",
            "menú",
            "inicio",
            "ayuda",
            "opciones",
        ]:
            try:
                session.reset_conversation(
                    reason="company_selection_menu"
                )
            except Exception:
                _logger.exception(
                    "[WA-COMPANY] Error reseteando por MENU | "
                    "session_id=%s",
                    session.id if session else False,
                )

            return self._build_main_menu_text(
                partner=partner,
                session=session,
            )

        # ------------------------------------------------------
        # CANCELAR
        # ------------------------------------------------------
        if text_lower in [
            "cancelar",
            "cancela",
            "salir",
            "terminar",
            "anular",
        ]:
            try:
                session.reset_conversation(
                    reason="company_selection_cancelled"
                )
            except Exception:
                _logger.exception(
                    "[WA-COMPANY] Error cancelando selección | "
                    "session_id=%s",
                    session.id if session else False,
                )

            return (
                "✅ *Selección de empresa cancelada*\n\n"
                "No se realizó ningún cambio en la empresa activa.\n\n"
                "%s"
            ) % self._build_main_menu_text(
                partner=partner,
                session=session,
            )

        # ------------------------------------------------------
        # Contexto y opciones
        # ------------------------------------------------------
        try:
            context = session.get_context()
            if not isinstance(
                context,
                dict,
            ):
                context = {}
        except Exception:
            _logger.exception(
                "[WA-COMPANY] Error leyendo contexto | "
                "session_id=%s",
                session.id if session else False,
            )
            context = {}

        options = (
            context.get("company_options")
            or []
        )

        index = self._parse_menu_index(
            text_clean
        )

        if not options:
            _logger.warning(
                "[WA-COMPANY] Sin company_options | "
                "partner_id=%s session_id=%s context=%s",
                partner.id if partner else False,
                session.id if session else False,
                context,
            )

            return self._company_selection_message(
                partner,
                session=session,
            )

        # ------------------------------------------------------
        # Opción inválida
        # ------------------------------------------------------
        if (
            not index
            or index < 1
            or index > len(options)
        ):
            _logger.info(
                "[WA-COMPANY] Índice inválido | "
                "partner_id=%s session_id=%s index=%s total=%s",
                partner.id if partner else False,
                session.id if session else False,
                index,
                len(options),
            )

            return (
                "⚠️ *Opción no válida*\n\n"
                "No pude relacionar tu respuesta con una de las empresas "
                "mostradas.\n\n"
                "Responde con el *número* correspondiente a la empresa "
                "que deseas utilizar.\n\n"
                "↩️ Escribe *ATRÁS* para regresar.\n"
                "🏠 Escribe *MENU* para volver al menú principal.\n"
                "❌ Escribe *CANCELAR* para cancelar la selección."
            )

        selected = options[
            index - 1
        ]

        company_id = selected.get(
            "id"
        )

        company = (
            request.env["res.partner"]
            .sudo()
            .browse(int(company_id))
            .exists()
            if company_id
            else False
        )

        if not company:
            _logger.warning(
                "[WA-COMPANY] Empresa seleccionada no existe | "
                "partner_id=%s session_id=%s selected=%s",
                partner.id if partner else False,
                session.id if session else False,
                selected,
            )

            return (
                "⚠️ La empresa seleccionada ya no se encuentra "
                "disponible.\n\n"
                "Selecciona otra empresa de la lista o escribe *MENU* "
                "para volver al menú principal."
            )

        # ------------------------------------------------------
        # Aplicar empresa activa
        # ------------------------------------------------------
        try:
            partner.whatsapp_set_active_company(
                company
            )
        except Exception:
            _logger.exception(
                "[WA-COMPANY] Error asignando empresa activa | "
                "partner_id=%s company_id=%s",
                partner.id if partner else False,
                company.id if company else False,
            )

            return (
                "⚠️ *No pudimos cambiar la empresa activa*\n\n"
                "Ocurrió un inconveniente al aplicar la selección. "
                "Inténtalo nuevamente.\n\n"
                "Si el inconveniente continúa, escribe *MENU* para "
                "volver al inicio."
            )

        try:
            session.write({
                "active_company_id": company.id,
            })
        except Exception:
            _logger.exception(
                "[WA-COMPANY] Error actualizando active_company_id | "
                "session_id=%s company_id=%s",
                session.id if session else False,
                company.id if company else False,
            )

        try:
            session.reset_conversation(
                reason="company_selected"
            )
        except Exception:
            _logger.exception(
                "[WA-COMPANY] Error reseteando flujo después de selección | "
                "session_id=%s",
                session.id if session else False,
            )

        _logger.info(
            "[WA-COMPANY] Empresa activa actualizada | "
            "partner_id=%s company_id=%s session_id=%s",
            partner.id if partner else False,
            company.id if company else False,
            session.id if session else False,
        )

        return (
            "✅ *Empresa seleccionada correctamente*\n\n"
            "🏢 *%s*\n"
            "%s\n\n"
            "Esta empresa será utilizada para las siguientes gestiones "
            "realizadas por este chat.\n\n"
            "%s"
        ) % (
            company.name
            or "Empresa",
            (
                "RUC: %s" % company.vat
                if company.vat
                else ""
            ),
            self._build_main_menu_text(
                partner=partner,
                session=session,
            ),
        )
