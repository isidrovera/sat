# -*- coding: utf-8 -*-

import logging

from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppOnsiteMixin:
    """
    Flujo conversacional para registrar servicio técnico presencial.

    Se conserva la lógica funcional existente:
    - obtener equipos asociados al cliente/empresa;
    - seleccionar equipo;
    - registrar descripción del problema;
    - recibir foto opcional;
    - crear ticket.alquiler;
    - adjuntar evidencia;
    - completar el flujo;
    - crear handoff de respaldo si la automatización no puede continuar.

    Las mejoras de este archivo se concentran en:
    - mensajes más claros y profesionales;
    - navegación consistente;
    - mejor trazabilidad en logs;
    - evitar activar atención humana inmediata fuera de horario.
    """

    # ==========================================================
    # Presentación / navegación
    # ==========================================================
    def _onsite_navigation_footer(self, include_back=True):
        """
        Devuelve las opciones estándar de navegación.

        Reutiliza el helper global del flow mixin cuando está disponible.
        """
        if hasattr(self, "_flow_navigation_footer"):
            try:
                return self._flow_navigation_footer(
                    include_back=include_back
                )
            except Exception:
                pass

        lines = []

        if include_back:
            lines.append(
                "↩️ Escribe *ATRÁS* para regresar al paso anterior."
            )

        lines.append(
            "🏠 Escribe *MENU* para volver al menú principal."
        )
        lines.append(
            "❌ Escribe *CANCELAR* para cancelar la solicitud."
        )

        return "\n".join(lines)

    # ==========================================================
    # Horario / derivación segura
    # ==========================================================
    def _onsite_business_status_safe(self):
        """
        Obtiene el estado horario sin permitir que un error en calendario
        rompa el registro del servicio.
        """
        try:
            status = self._compute_business_status()
            return status if isinstance(status, dict) else {}
        except Exception:
            _logger.exception(
                "[WA-ONSITE] Error evaluando horario para handoff"
            )
            return {}

    def _onsite_create_handoff_safe(
        self,
        partner,
        session,
        machine=False,
        initial_message=False,
        media=False,
        reason=False,
        context=None,
    ):
        """
        Crea el handoff de respaldo respetando disponibilidad horaria.

        En horario abierto:
        - crea handoff;
        - activa modo humano;
        - cambia la sesión a human.

        En refrigerio / fuera de horario:
        - crea el handoff pendiente;
        - NO activa modo humano inmediato;
        - cierra el flujo que ya no puede continuar automáticamente.

        Esto evita prometer atención inmediata cuando no hay un técnico
        disponible, pero mantiene trazabilidad para que el caso no se pierda.
        """
        context = context if isinstance(context, dict) else {}

        business_status = self._onsite_business_status_safe()
        realtime_available = bool(
            business_status.get("is_open")
        )

        handoff = False

        try:
            handoff = (
                request.env["whatsapp.handoff"]
                .sudo()
                .create_onsite_handoff(
                    partner,
                    session=session,
                    machine=machine if machine else False,
                    initial_message=initial_message or "",
                    media=media if media else False,
                    context={
                        "reason": (
                            reason
                            or "Servicio técnico requiere revisión manual."
                        ),
                        "flow_context": context,
                        "business_status": business_status,
                        "pending_until_business_hours": (
                            not realtime_available
                        ),
                    },
                )
            )

            _logger.info(
                "[WA-ONSITE] Handoff creado | "
                "handoff_id=%s partner_id=%s session_id=%s "
                "machine_id=%s realtime_available=%s reason=%s",
                handoff.id if handoff else False,
                partner.id if partner else False,
                session.id if session else False,
                machine.id if machine else False,
                realtime_available,
                reason or False,
            )

        except Exception:
            _logger.exception(
                "[WA-ONSITE] Error creando handoff | "
                "partner_id=%s session_id=%s machine_id=%s",
                partner.id if partner else False,
                session.id if session else False,
                machine.id if machine else False,
            )

        if realtime_available:
            try:
                partner.whatsapp_enable_human_mode_api(
                    taken_by_name="Bot WhatsApp"
                )
                session.action_set_human()

                _logger.info(
                    "[WA-ONSITE] Modo humano activado | "
                    "partner_id=%s session_id=%s handoff_id=%s",
                    partner.id if partner else False,
                    session.id if session else False,
                    handoff.id if handoff else False,
                )

            except Exception:
                _logger.exception(
                    "[WA-ONSITE] Error activando modo humano | "
                    "partner_id=%s session_id=%s",
                    partner.id if partner else False,
                    session.id if session else False,
                )

            return handoff, True, business_status

        # Fuera de horario no debe quedar un flujo esperando a un humano.
        try:
            if session and session.current_flow != "none":
                session.reset_conversation(
                    reason="onsite_pending_handoff_after_hours"
                )
        except Exception:
            _logger.exception(
                "[WA-ONSITE] Error cerrando flujo pendiente fuera de horario | "
                "session_id=%s",
                session.id if session else False,
            )

        return handoff, False, business_status

    # ==========================================================
    # Crear ticket servicio presencial
    # ==========================================================
    def _get_service_problem_photo_binary(self, context):
        """
        Devuelve la imagen en base64 para llenar
        ticket.alquiler.problem_photo.

        El flujo presencial guarda media_id en context cuando el cliente
        envía una foto.

        whatsapp.media puede tener:
        - attachment_id ya creado;
        - URL externa pendiente de descargar.
        """
        context = context or {}

        media_id = context.get("media_id")
        if not media_id:
            return False

        try:
            media = (
                request.env["whatsapp.media"]
                .sudo()
                .browse(int(media_id))
                .exists()
            )
        except Exception:
            media = request.env["whatsapp.media"].sudo()

        if not media:
            return False

        if (
            media.media_type
            and media.media_type != "image"
        ):
            _logger.info(
                "[WA-ONSITE] Media no es imagen; "
                "no se copia a problem_photo | "
                "media_id=%s type=%s",
                media.id,
                media.media_type,
            )
            return False

        attachment = media.attachment_id

        if not attachment:
            try:
                attachment = (
                    media.download_and_create_attachment()
                )
            except Exception:
                _logger.exception(
                    "[WA-ONSITE] No se pudo descargar media "
                    "para problem_photo | media_id=%s url=%s",
                    media.id,
                    media.url,
                )
                attachment = False

        if not attachment or not attachment.datas:
            _logger.warning(
                "[WA-ONSITE] Media sin attachment/datas "
                "para problem_photo | media_id=%s",
                media.id,
            )
            return False

        return attachment.datas

    def _create_service_ticket(
        self,
        partner,
        session,
        context,
        payload=False,
    ):
        """
        Crea ticket.alquiler utilizando la misma estructura funcional
        existente.

        No se altera el modelo de destino ni el mapeo de campos.
        """
        company = (
            partner.whatsapp_active_company_id
            if partner
            and partner.whatsapp_active_company_id
            else False
        )

        machine = self._get_context_machine(context)
        payload = payload or {}

        description = (
            context.get("service_description")
            or payload.get("message")
            or payload.get("text")
            or ""
        )

        problem_photo = (
            self._get_service_problem_photo_binary(
                context
            )
        )

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
            "partner_id": (
                company.id
                if company
                else partner.id
                if partner
                else False
            ),

            # Contacto que reporta
            "cliente_id": (
                partner.id
                if partner
                else False
            ),
            "reporter_name": (
                partner.name
                if partner
                else False
            ),
            "reporter_phone": (
                partner.whatsapp_number
                or partner.mobile
                or partner.phone
                or ""
                if partner
                else ""
            ),

            # Empresa / compatibilidad
            "company_id": (
                company.id
                if company
                else False
            ),
            "empresa_id": (
                company.id
                if company
                else False
            ),

            # Campo real de equipo en ticket.alquiler
            "product_alquiler": (
                machine.id
                if machine
                else False
            ),

            # Fallbacks por si alguna herencia los usa
            "alquiler_id": (
                machine.id
                if machine
                else False
            ),
            "machine_id": (
                machine.id
                if machine
                else False
            ),
            "equipo_id": (
                machine.id
                if machine
                else False
            ),

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

            # Foto del problema enviada por WhatsApp
            "problem_photo": (
                problem_photo
                or False
            ),

            "observaciones": description,

            # Tipo de servicio
            "tipo_servicio_id": "revision",

            # Trazabilidad
            "origen": "whatsapp",
            "source": "whatsapp",
            "whatsapp_session_id": (
                session.id
                if session
                else False
            ),
        }

        _logger.info(
            "[WA-ONSITE] Creando ticket | "
            "partner_id=%s company_id=%s machine_id=%s "
            "session_id=%s has_photo=%s description=%r",
            partner.id if partner else False,
            company.id if company else False,
            machine.id if machine else False,
            session.id if session else False,
            bool(problem_photo),
            description[:200] if description else "",
        )

        rec, error = self._safe_model_create(
            "ticket.alquiler",
            preferred_vals,
        )

        return rec, error

    # ==========================================================
    # Flujo servicio presencial: iniciar
    # ==========================================================
    def _start_onsite_flow(
        self,
        partner,
        session,
        identifiers,
        payload=False,
    ):
        company = (
            partner.whatsapp_active_company_id
            if partner
            and partner.whatsapp_active_company_id
            else False
        )

        machines = self._get_partner_machines(
            partner
        )

        # ------------------------------------------------------
        # Sin equipos asociados
        # ------------------------------------------------------
        if not machines:
            initial_message = (
                (payload or {}).get("message")
                or (payload or {}).get("text")
                or ""
            )

            handoff, human_active, business_status = (
                self._onsite_create_handoff_safe(
                    partner=partner,
                    session=session,
                    machine=False,
                    initial_message=initial_message,
                    reason=(
                        "No se encontraron equipos alquilados "
                        "para registrar servicio técnico."
                    ),
                    context={
                        "company_id": (
                            company.id
                            if company
                            else False
                        ),
                    },
                )
            )

            _logger.warning(
                "[WA-ONSITE] Sin equipos asociados | "
                "partner_id=%s company_id=%s handoff_id=%s "
                "human_active=%s business_reason=%s",
                partner.id if partner else False,
                company.id if company else False,
                handoff.id if handoff else False,
                human_active,
                (
                    business_status.get("reason")
                    if business_status
                    else False
                ),
            )

            if human_active:
                return (
                    "🛠️ *Servicio técnico*\n\n"
                    "No encontré equipos alquilados asociados a la "
                    "empresa activa.\n\n"
                    "He derivado el caso a nuestro equipo para que pueda "
                    "identificar el equipo y continuar con el registro.\n\n"
                    "Por favor mantente atento(a) a este chat."
                )

            return (
                "🛠️ *Servicio técnico*\n\n"
                "No encontré equipos alquilados asociados a la "
                "empresa activa.\n\n"
                "El caso quedó registrado para revisión de nuestro "
                "equipo al retomar el horario de atención.\n\n"
                "🏠 Escribe *MENU* para volver al menú principal."
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
                "label": self._get_machine_label(
                    machine
                ),
                "form_url": machine_link,
            })

            _logger.info(
                "[WA-ONSITE] Opción de equipo | "
                "machine_id=%s serie=%s link=%s",
                machine.id,
                getattr(machine, "serie", "") or "",
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
            (
                "🛠️ *Servicio técnico · Paso 1*\n\n"
                "Selecciona el equipo que presenta el inconveniente.\n"
                "Responde con el *número* correspondiente:"
            ),
            footer=(
                "Después de seleccionar el equipo te solicitaré una "
                "breve descripción del problema.\n\n"
                + self._onsite_navigation_footer(
                    include_back=True
                )
            ),
            include_link=False,
            link=False,
        )

    # ==========================================================
    # Flujo servicio presencial: continuación
    # ==========================================================
    def _continue_onsite_flow(
        self,
        partner,
        session,
        identifiers,
        text,
        payload=False,
    ):
        context = session.get_context()
        text_clean = (text or "").strip()
        state = session.conversation_state

        _logger.info(
            "[WA-ONSITE] Continuando flujo | "
            "partner_id=%s session_id=%s state=%s "
            "text=%r context_keys=%s",
            partner.id if partner else False,
            session.id if session else False,
            state,
            text_clean[:200],
            list(context.keys())
            if isinstance(context, dict)
            else [],
        )

        # ------------------------------------------------------
        # LINK / FORMULARIO
        # ------------------------------------------------------
        if text_clean.lower() in [
            "link",
            "enlace",
            "url",
            "formulario",
        ]:
            link = context.get("form_url")

            if not link:
                return (
                    "ℹ️ Primero selecciona uno de los equipos "
                    "de la lista. Después podré enviarte el enlace "
                    "correcto del formulario de servicio.\n\n"
                    + self._onsite_navigation_footer(
                        include_back=True
                    )
                )

            return (
                "🔗 *Formulario de servicio técnico*\n\n"
                "%s\n\n"
                "Puedes utilizar el formulario o continuar "
                "directamente por este chat.\n\n"
                "%s"
            ) % (
                link,
                self._onsite_navigation_footer(
                    include_back=True
                ),
            )

        # ------------------------------------------------------
        # Compatibilidad con NO en pasos iniciales
        #
        # La navegación global CANCELAR/MENU/ATRÁS se procesa antes
        # en whatsapp_flow_mixin.py.
        # ------------------------------------------------------
        if (
            self._is_no(text_clean)
            and state not in [
                "awaiting_service_description",
                "awaiting_service_photo",
            ]
        ):
            session.reset_conversation(
                reason="abandoned"
            )

            return (
                "✅ *Solicitud de servicio cancelada*\n\n"
                "No se registró ningún servicio técnico.\n\n"
                "Escribe *MENU* para volver al menú principal."
            )

        # ======================================================
        # PASO 1: SELECCIÓN DE EQUIPO
        # ======================================================
        if state == "awaiting_machine_selection_onsite":
            index = self._parse_menu_index(
                text_clean
            )

            options = (
                context.get("machine_options")
                or []
            )

            if (
                not index
                or index < 1
                or index > len(options)
            ):
                return (
                    "⚠️ *No pude identificar ese equipo*\n\n"
                    "Responde con el *número* de uno de los equipos "
                    "mostrados en la lista.\n\n"
                    + self._onsite_navigation_footer(
                        include_back=True
                    )
                )

            selected = options[index - 1]

            machine = (
                request.env["alquiler"]
                .sudo()
                .browse(int(selected.get("id")))
                .exists()
            )

            if not machine:
                _logger.warning(
                    "[WA-ONSITE] Equipo seleccionado no existe | "
                    "session_id=%s selected=%s",
                    session.id if session else False,
                    selected,
                )

                return (
                    "⚠️ El equipo seleccionado ya no se encuentra "
                    "disponible.\n\n"
                    "Escribe *ATRÁS* para volver a la selección de "
                    "equipos o *MENU* para iniciar nuevamente."
                )

            link = (
                selected.get("form_url")
                or self._get_service_url(
                    partner=partner,
                    company=(
                        partner.whatsapp_active_company_id
                        if partner
                        else False
                    ),
                    machine=machine,
                )
            )

            machine_label = self._get_machine_label(
                machine
            )

            session.advance_state(
                "awaiting_service_description",
                {
                    "machine_id": machine.id,
                    "machine_label": machine_label,
                    "form_url": link,
                },
            )

            _logger.info(
                "[WA-ONSITE] Equipo seleccionado | "
                "partner_id=%s session_id=%s machine_id=%s",
                partner.id if partner else False,
                session.id if session else False,
                machine.id,
            )

            return (
                "✅ *Equipo seleccionado*\n"
                "%s\n\n"
                "🛠️ *Servicio técnico · Paso 2*\n\n"
                "Describe brevemente el problema que presenta el equipo.\n\n"
                "Ejemplo: “No imprime y muestra atasco de papel”.\n\n"
                "Si prefieres utilizar el formulario web, escribe *LINK*.\n\n"
                "%s"
            ) % (
                machine_label,
                self._onsite_navigation_footer(
                    include_back=True
                ),
            )

        # ======================================================
        # PASO 2: DESCRIPCIÓN DEL PROBLEMA
        # ======================================================
        if state == "awaiting_service_description":
            if len(text_clean) < 4:
                return (
                    "⚠️ *Necesito un poco más de información*\n\n"
                    "Describe brevemente qué problema presenta el equipo. "
                    "Por ejemplo: “No imprime”, “atasca papel” o "
                    "“muestra un código de error”.\n\n"
                    + self._onsite_navigation_footer(
                        include_back=True
                    )
                )

            session.advance_state(
                "awaiting_service_photo",
                {
                    "service_description": (
                        text_clean
                    ),
                },
            )

            _logger.info(
                "[WA-ONSITE] Descripción recibida | "
                "partner_id=%s session_id=%s description=%r",
                partner.id if partner else False,
                session.id if session else False,
                text_clean[:250],
            )

            return (
                "✅ *Descripción registrada*\n\n"
                "📷 *Servicio técnico · Paso 3*\n\n"
                "Si tienes una foto del problema o del mensaje que "
                "aparece en el equipo, envíala ahora.\n\n"
                "La foto es opcional. Si no deseas adjuntar una, "
                "responde *NO* y registraré el servicio con la "
                "información proporcionada.\n\n"
                "%s"
            ) % self._onsite_navigation_footer(
                include_back=True
            )

        # ======================================================
        # PASO 3: FOTO OPCIONAL + CREACIÓN DEL TICKET
        # ======================================================
        if state == "awaiting_service_photo":
            media = self._create_media_from_payload(
                session=session,
                partner=partner,
                message=False,
                payload=payload or {},
            )

            context_update = {}

            if media:
                context_update["media_id"] = (
                    media.id
                )

                try:
                    media.mark_for_human_review(
                        reason=(
                            "Foto enviada para "
                            "servicio presencial."
                        )
                    )
                except Exception:
                    _logger.exception(
                        "[WA-ONSITE] No se pudo marcar media "
                        "para revisión | media_id=%s",
                        media.id,
                    )

                _logger.info(
                    "[WA-ONSITE] Foto recibida | "
                    "partner_id=%s session_id=%s media_id=%s",
                    partner.id if partner else False,
                    session.id if session else False,
                    media.id,
                )

            elif not self._is_no(text_clean):
                # Mantiene el comportamiento funcional: el ticket puede
                # registrarse sin foto. Solo informamos cuando el mensaje
                # no contiene una evidencia reconocible.
                _logger.info(
                    "[WA-ONSITE] Paso foto sin media reconocida | "
                    "session_id=%s text=%r",
                    session.id if session else False,
                    text_clean[:160],
                )

            context = session.update_context(
                context_update
            )

            ticket, error = (
                self._create_service_ticket(
                    partner,
                    session,
                    context,
                    payload=payload,
                )
            )

            # --------------------------------------------------
            # Ticket creado correctamente
            # --------------------------------------------------
            if ticket:
                if media:
                    try:
                        media.attach_to_record(
                            "ticket.alquiler",
                            ticket.id,
                            purpose="service_issue",
                        )
                    except Exception:
                        _logger.exception(
                            "[WA-ONSITE] No se pudo adjuntar media "
                            "al ticket | ticket_id=%s media_id=%s",
                            ticket.id,
                            media.id,
                        )

                session.complete_flow(
                    close_reason="completed_onsite"
                )

                _logger.info(
                    "[WA-ONSITE] Servicio registrado | "
                    "partner_id=%s session_id=%s ticket_id=%s "
                    "reference=%s media_id=%s",
                    partner.id if partner else False,
                    session.id if session else False,
                    ticket.id,
                    ticket.display_name or ticket.id,
                    media.id if media else False,
                )

                return (
                    "✅ *Servicio técnico registrado correctamente*\n\n"
                    "Referencia: *%s*\n\n"
                    "Nuestro equipo revisará la solicitud y continuará "
                    "la atención de acuerdo con el proceso correspondiente.\n\n"
                    "Escribe *MENU* si deseas realizar otra gestión."
                ) % (
                    ticket.display_name
                    or ticket.id
                )

            # --------------------------------------------------
            # Error creando ticket: handoff seguro
            # --------------------------------------------------
            machine = self._get_context_machine(
                context
            )

            handoff, human_active, business_status = (
                self._onsite_create_handoff_safe(
                    partner=partner,
                    session=session,
                    machine=machine,
                    initial_message=(
                        context.get(
                            "service_description"
                        )
                        or text_clean
                    ),
                    media=media if media else False,
                    reason=(
                        "No se pudo crear ticket.alquiler "
                        "automáticamente."
                    ),
                    context={
                        "error": error,
                        "flow_context": context,
                    },
                )
            )

            _logger.error(
                "[WA-ONSITE] No se pudo crear ticket | "
                "partner_id=%s session_id=%s machine_id=%s "
                "error=%s handoff_id=%s human_active=%s "
                "business_reason=%s",
                partner.id if partner else False,
                session.id if session else False,
                machine.id if machine else False,
                error,
                handoff.id if handoff else False,
                human_active,
                (
                    business_status.get("reason")
                    if business_status
                    else False
                ),
            )

            if human_active:
                return (
                    "⚠️ *No pudimos completar el registro automáticamente*\n\n"
                    "Recibimos la información del servicio y el caso fue "
                    "derivado a nuestro equipo para completar el registro.\n\n"
                    "Por favor mantente atento(a) a este chat."
                )

            return (
                "⚠️ *No pudimos completar el registro automáticamente*\n\n"
                "Recibimos la información y dejamos el caso pendiente "
                "para revisión de nuestro equipo al retomar el horario "
                "de atención.\n\n"
                "🏠 Escribe *MENU* si deseas realizar otra gestión."
            )

        # ======================================================
        # Estado desconocido: recuperación segura
        # ======================================================
        _logger.warning(
            "[WA-ONSITE] Estado no reconocido | "
            "partner_id=%s session_id=%s state=%s",
            partner.id if partner else False,
            session.id if session else False,
            state,
        )

        return (
            "⚠️ No pude determinar en qué paso de la solicitud "
            "te encuentras.\n\n"
            "Escribe *MENU* y selecciona nuevamente la opción "
            "de servicio técnico para continuar de forma segura."
        )
