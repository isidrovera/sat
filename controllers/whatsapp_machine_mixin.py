# -*- coding: utf-8 -*-

import logging

from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppMachineMixin:
    # ==========================================================
    # Enlaces configurables
    # ==========================================================
    def _get_base_url(self):
        return request.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")

    def _get_toner_url(self, partner=False, company=False, machine=False):
        """
        Genera el enlace correcto para el formulario web de tóner.

        El formulario existente usa:
            /toner/solicitar_toner?id_registro=...&user_name=...&phone_number=...
        """
        ICP = request.env["ir.config_parameter"].sudo()
        base = self._get_base_url()

        url = ICP.get_param("sat.whatsapp_toner_url") or "%s/toner/solicitar_toner" % base

        params = []

        if machine:
            params.append("id_registro=%s" % machine.id)

        if partner:
            user_name = partner.name or ""
            user_name = str(user_name).strip().replace(" ", "%20")
            if user_name:
                params.append("user_name=%s" % user_name)

            phone = (
                getattr(partner, "whatsapp_number", False)
                or getattr(partner, "mobile", False)
                or getattr(partner, "phone", False)
                or ""
            )
            phone = str(phone or "").replace("+", "").replace(" ", "").strip()
            if phone:
                params.append("phone_number=%s" % phone)

        if params:
            joiner = "&" if "?" in url else "?"
            url = "%s%s%s" % (url, joiner, "&".join(params))

        return url

    def _get_service_url(self, partner=False, company=False, machine=False):
        """
        Genera el enlace correcto para el formulario web de servicio presencial.

        El formulario existente usa:
            /ticket/reportar_incidencia?id_registro=...&user_name=...&phone_number=...
        """
        ICP = request.env["ir.config_parameter"].sudo()
        base = self._get_base_url()

        url = ICP.get_param("sat.whatsapp_service_url") or "%s/ticket/reportar_incidencia" % base

        params = []

        if machine:
            params.append("id_registro=%s" % machine.id)

        if partner:
            user_name = str(partner.name or "").strip().replace(" ", "%20")
            if user_name:
                params.append("user_name=%s" % user_name)

            phone = (
                getattr(partner, "whatsapp_number", False)
                or getattr(partner, "mobile", False)
                or getattr(partner, "phone", False)
                or ""
            )
            phone = str(phone or "").replace("+", "").replace(" ", "").replace("@c.us", "").strip()
            if phone:
                params.append("phone_number=%s" % phone)

        if params:
            joiner = "&" if "?" in url else "?"
            url = "%s%s%s" % (url, joiner, "&".join(params))

        return url

    # ==========================================================
    # Máquinas alquiladas
    # ==========================================================
    def _field_exists(self, model, field_name):
        return field_name in model._fields

    def _get_machine_label(self, machine):
        name = machine.display_name or machine.name or "Equipo"

        model_name = ""
        for field in ["modelo_id", "model_id", "modelo", "model", "equipo_modelo_id"]:
            if field in machine._fields:
                value = machine[field]
                if value:
                    model_name = value.display_name if hasattr(value, "display_name") else str(value)
                    break

        serie = ""
        for field in ["serie", "serial", "serial_number", "numero_serie", "nro_serie", "codigo_serie"]:
            if field in machine._fields and machine[field]:
                serie = machine[field]
                break

        ubicacion = ""
        for field in ["ubicacion", "location", "direccion", "address", "oficina", "area"]:
            if field in machine._fields and machine[field]:
                value = machine[field]
                ubicacion = value.display_name if hasattr(value, "display_name") else str(value)
                break

        parts = []
        if model_name:
            parts.append(model_name)
        else:
            parts.append(name)

        if serie:
            parts.append("Serie: %s" % serie)

        if ubicacion:
            parts.append("Ubicación: %s" % ubicacion)

        return " | ".join(parts)

    def _record_matches_partner_company(self, rec, partner=False, company=False):
        partner_ids = set()
        partner_names = set()
        partner_vats = set()

        if partner:
            partner_ids.add(partner.id)
            if partner.name:
                partner_names.add(partner.name.strip().lower())
            if partner.vat:
                partner_vats.add(str(partner.vat).strip())

        if company:
            partner_ids.add(company.id)
            if company.name:
                partner_names.add(company.name.strip().lower())
            if company.vat:
                partner_vats.add(str(company.vat).strip())

        if not partner_ids and not partner_names and not partner_vats:
            return False

        candidate_fields = [
            "partner_id",
            "cliente_id",
            "customer_id",
            "empresa_id",
            "company_partner_id",
            "res_partner_id",
            "contacto_id",
            "titular_id",
            "cliente",
            "empresa",
            "razon_social",
            "ruc",
            "vat",
        ]

        for field in candidate_fields:
            if field not in rec._fields:
                continue

            value = rec[field]

            if not value:
                continue

            if hasattr(value, "id"):
                if value.id in partner_ids:
                    return True

                if getattr(value, "name", False):
                    if value.name.strip().lower() in partner_names:
                        return True

                if getattr(value, "vat", False):
                    if str(value.vat).strip() in partner_vats:
                        return True

                continue

            value_text = str(value).strip()
            value_lower = value_text.lower()

            if value_lower in partner_names:
                return True

            if value_text in partner_vats:
                return True

        return False

    def _get_partner_machines(self, partner, limit=20):
        if "alquiler" not in request.env or not partner:
            return request.env["ir.model"].sudo().browse()

        Machine = request.env["alquiler"].sudo()
        company = partner.whatsapp_active_company_id if partner.whatsapp_active_company_id else False

        partner_ids = []

        if partner:
            partner_ids.append(partner.id)

        if company:
            partner_ids.append(company.id)

        if partner.commercial_partner_id:
            partner_ids.append(partner.commercial_partner_id.id)

        if company and company.commercial_partner_id:
            partner_ids.append(company.commercial_partner_id.id)

        partner_ids = list(set([pid for pid in partner_ids if pid]))

        if not partner_ids:
            return Machine.browse()

        excluded_states = [
            "cancel",
            "cancelado",
            "baja",
            "retirado",
            "finalizado",
            "closed",
        ]

        direct_domains = []

        if "cliente_id" in Machine._fields:
            direct_domains.append([("cliente_id", "in", partner_ids)])

        for field_name in [
            "partner_id",
            "customer_id",
            "empresa_id",
            "company_partner_id",
            "res_partner_id",
            "contacto_id",
            "titular_id",
        ]:
            if field_name in Machine._fields:
                direct_domains.append([(field_name, "in", partner_ids)])

        result = Machine.browse()

        for domain in direct_domains:
            search_domain = list(domain)

            if "estado_alquiler_id" in Machine._fields:
                search_domain.append(("estado_alquiler_id", "not in", excluded_states))
            elif "state" in Machine._fields:
                search_domain.append(("state", "not in", excluded_states))
            elif "estado" in Machine._fields:
                search_domain.append(("estado", "not in", excluded_states))
            elif "status" in Machine._fields:
                search_domain.append(("status", "not in", excluded_states))

            records = Machine.search(search_domain, order="id desc", limit=limit)
            result |= records

            if len(result) >= limit:
                break

        if not result:
            records = Machine.search([], order="id desc", limit=2000)
            for rec in records:
                if self._record_matches_partner_company(rec, partner=partner, company=company):
                    result |= rec

                if len(result) >= limit:
                    break

        return result[:limit]

    def _build_machine_menu(self, machines, title, footer=None, include_link=False, link=False):
        lines = [title, ""]
        index = 1

        for machine in machines:
            lines.append("%s. %s" % (index, self._get_machine_label(machine)))
            index += 1

        if include_link and link:
            lines.append("")
            lines.append("También puedes usar este formulario:")
            lines.append(link)

        if footer:
            lines.append("")
            lines.append(footer)

        return "\n".join(lines)

    def _get_context_machine(self, context):
        machine_id = context.get("machine_id")

        if not machine_id or "alquiler" not in request.env:
            return False

        return request.env["alquiler"].sudo().browse(int(machine_id)).exists()

    # ==========================================================
    # Conversación: lectura básica
    # ==========================================================
    def _parse_menu_index(self, text):
        digits = self._only_digits(text)

        if not digits:
            return False

        try:
            return int(digits)
        except Exception:
            return False

    def _is_yes(self, text):
        text = (text or "").strip().lower()
        return text in [
            "si",
            "sí",
            "ok",
            "okay",
            "confirmo",
            "confirmar",
            "correcto",
            "dale",
            "ya",
        ]

    def _is_no(self, text):
        text = (text or "").strip().lower()
        return text in [
            "no",
            "cancelar",
            "cancela",
            "anular",
            "salir",
        ]

    def _looks_like_dni(self, text):
        digits = self._only_digits(text)
        return len(digits) == 8

    def _looks_like_ruc(self, text):
        digits = self._only_digits(text)
        return len(digits) == 11 and digits.startswith(("10", "20"))

    def _looks_like_anydesk(self, text):
        digits = self._only_digits(text)
        return len(digits) >= 6 and len(digits) <= 12

    # ==========================================================
    # Creación genérica de documentos
    # ==========================================================
    def _safe_model_create(self, model_name, preferred_vals):
        if model_name not in request.env:
            return False, "Modelo no encontrado: %s" % model_name

        Model = request.env[model_name].sudo()
        vals = {}

        for key, value in preferred_vals.items():
            if key in Model._fields:
                vals[key] = value

        try:
            rec = Model.create(vals)
            return rec, False
        except Exception as e:
            _logger.exception(
                "[SAT-WHATSAPP-API] Error creando %s vals=%s",
                model_name,
                vals,
            )
            return False, str(e)