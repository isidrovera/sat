# -*- coding: utf-8 -*-

import logging

from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppOnsiteMixin:
    # ==========================================================
    # Crear ticket servicio presencial
    # ==========================================================
    def _create_service_ticket(self, partner, session, context, payload=False):
        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False
        machine = self._get_context_machine(context)
        payload = payload or {}

        description = context.get("service_description") or payload.get("message") or payload.get("text") or ""

        def _get_machine_value(field_names):
            if not machine:
                return False

            for field_name in field_names:
                if field_name in machine._fields:
                    value = machine[field_name]

                    if not value:
                        continue

                    if hasattr(value, "display_name"):
                        return value.display_name

                    return str(value)

            return False

        direccion = _get_machine_value([
            "direccion",
            "direccion_id",
            "address",
            "ubicacion",
            "location",
        ])

        contacto = _get_machine_value([
            "contacto_id",
            "contacto",
            "contact_name",
            "responsable_cliente",
        ])

        celular = _get_machine_value([
            "celular",
            "telefono",
            "phone",
            "mobile",
            "contact_phone",
        ])

        correo = _get_machine_value([
            "correo_",
            "correo",
            "email",
            "contact_email",
        ])

        piso = _get_machine_value([
            "piso",
            "piso_id",
            "floor",
        ])

        oficina = _get_machine_value([
            "oficina",
            "oficina_id",
            "office",
            "area_oficina",
        ])

        area = _get_machine_value([
            "area",
            "area_id",
            "department",
        ])

        preferred_vals = {
            "name": "Servicio presencial WhatsApp",

            # En ticket.alquiler partner_id es Empresa
            "partner_id": company.id if company else partner.id if partner else False,

            # Contacto que reporta
            "cliente_id": partner.id if partner else False,
            "reporter_name": partner.name if partner else False,
            "reporter_phone": partner.whatsapp_number or partner.mobile or partner.phone or "",

            # Empresa / compatibilidad
            "company_id": company.id if company else False,
            "empresa_id": company.id if company else False,

            # Campo real de equipo en ticket.alquiler
            "product_alquiler": machine.id if machine else False,

            # Fallbacks por si alguna herencia los usa
            "alquiler_id": machine.id if machine else False,
            "machine_id": machine.id if machine else False,
            "equipo_id": machine.id if machine else False,

            # Datos de ubicación/contacto copiados desde alquiler
            "direccion_id_r": direccion or "",
            "contacto_id_r": contacto or "",
            "celular_id_r": celular or "",
            "corre_id_r": correo or "",
            "piso_id_r": piso or "",
            "oficina_id_r": oficina or "",
            "area_id_r": area or "",

            # Descripción del problema
            "description": description,
            "descripcion": description,
            "problema": description,
            "falla_reportada": description,
            "observaciones": description,
            "informe_id": description,

            # Tipo de servicio
            "tipo_servicio_id": "mantenimiento_correctivo",

            # Trazabilidad
            "origen": "whatsapp",
            "source": "whatsapp",
            "whatsapp_session_id": session.id if session else False,
        }

        rec, error = self._safe_model_create("ticket.alquiler", preferred_vals)
        return rec, error

    # ==========================================================
    # Flujo servicio presencial: iniciar
    # ==========================================================
    def _start_onsite_flow(self, partner, session, identifiers, payload=False):
        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False
        machines = self._get_partner_machines(partner)

        if not machines:
            request.env["whatsapp.handoff"].sudo().create_onsite_handoff(
                partner,
                session=session,
                initial_message=(payload or {}).get("message") or (payload or {}).get("text") or "",
                context={"reason": "No se encontraron equipos alquilados para servicio presencial."},
            )
            partner.whatsapp_enable_human_mode_api(taken_by_name="Bot WhatsApp")
            session.action_set_human()
            return (
                "No encontré equipos alquilados asociados a tu empresa. "
                "Voy a derivarte con un asesor para registrar tu servicio."
            )

        options = []

        for machine in machines:
            machine_link = self._get_service_url(
                partner=partner,
                company=company,
                machine=machine,
            )

            options.append({
                "id": machine.id,
                "label": self._get_machine_label(machine),
                "form_url": machine_link,
            })

            _logger.info(
                "[WA-ONSITE] Opción máquina id=%s serie=%s link=%s",
                machine.id,
                machine.serie or "",
                machine_link,
            )

        session.start_flow(
            "onsite",
            "awaiting_machine_selection_onsite",
            context={
                "intent": "onsite_service",
                "machine_options": options,
                "form_url": False,
            },
        )

        return self._build_machine_menu(
            machines,
            "De acuerdo. Selecciona el equipo para el servicio presencial:",
            footer="Luego de seleccionar el equipo podré enviarte el enlace del formulario si lo necesitas.",
            include_link=False,
            link=False,
        )

    # ==========================================================
    # Flujo servicio presencial: continuación
    # ==========================================================
    def _continue_onsite_flow(self, partner, session, identifiers, text, payload=False):
        context = session.get_context()
        text_clean = (text or "").strip()
        state = session.conversation_state

        if text_clean.lower() in ["link", "enlace", "url", "formulario"]:
            link = context.get("form_url")

            if not link:
                return (
                    "Primero selecciona el equipo de la lista. "
                    "Luego podré enviarte el enlace correcto del formulario de servicio."
                )

            return "Puedes registrar tu servicio presencial aquí:\n%s" % link

        if self._is_no(text_clean) and state not in [
            "awaiting_service_description",
            "awaiting_service_photo",
        ]:
            session.reset_conversation(reason="abandoned")
            return "Listo, cancelé la solicitud de servicio presencial."

        if state == "awaiting_machine_selection_onsite":
            index = self._parse_menu_index(text_clean)
            options = context.get("machine_options") or []

            if not index or index < 1 or index > len(options):
                return "Por favor responde con el número del equipo de la lista."

            selected = options[index - 1]
            machine = request.env["alquiler"].sudo().browse(int(selected.get("id"))).exists()

            if not machine:
                return "No pude encontrar ese equipo. Por favor inicia nuevamente la solicitud."

            link = selected.get("form_url") or self._get_service_url(
                partner=partner,
                company=partner.whatsapp_active_company_id if partner else False,
                machine=machine,
            )

            session.advance_state(
                "awaiting_service_description",
                {
                    "machine_id": machine.id,
                    "machine_label": self._get_machine_label(machine),
                    "form_url": link,
                },
            )

            return (
                "Equipo seleccionado:\n%s\n\n"
                "Puedes registrar tu servicio presencial aquí:\n%s\n\n"
                "O descríbenos brevemente el problema del equipo."
            ) % (self._get_machine_label(machine), link)

        if state == "awaiting_service_description":
            if len(text_clean) < 4:
                return "Por favor detalla un poco más el problema del equipo."

            session.advance_state(
                "awaiting_service_photo",
                {"service_description": text_clean},
            )

            return (
                "Gracias. Si tienes una foto del problema, envíala ahora. "
                "Si no tienes foto, escribe NO para registrar el servicio."
            )

        if state == "awaiting_service_photo":
            media = self._create_media_from_payload(
                session=session,
                partner=partner,
                message=False,
                payload=payload or {},
            )

            context_update = {}
            if media:
                context_update["media_id"] = media.id
                try:
                    media.mark_for_human_review(reason="Foto enviada para servicio presencial.")
                except Exception:
                    pass

            context = session.update_context(context_update)

            ticket, error = self._create_service_ticket(partner, session, context, payload=payload)

            if ticket:
                if media:
                    try:
                        media.attach_to_record("ticket.alquiler", ticket.id, purpose="service_issue")
                    except Exception:
                        pass

                session.complete_flow(close_reason="completed_onsite")
                return (
                    "Servicio presencial registrado correctamente.\n"
                    "Referencia: %s"
                ) % (ticket.display_name or ticket.id)

            request.env["whatsapp.handoff"].sudo().create_onsite_handoff(
                partner,
                session=session,
                machine=self._get_context_machine(context),
                initial_message=context.get("service_description") or text_clean,
                media=media if media else False,
                context={
                    "reason": "No se pudo crear ticket.alquiler automáticamente.",
                    "error": error,
                    "flow_context": context,
                },
            )
            partner.whatsapp_enable_human_mode_api(taken_by_name="Bot WhatsApp")
            session.action_set_human()

            return (
                "Recibí la información del servicio, pero no pude crear el ticket automáticamente. "
                "Te estoy derivando con un asesor."
            )

        return "Estoy procesando tu solicitud de servicio. Por favor continúa con la información solicitada."