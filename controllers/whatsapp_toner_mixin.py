# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from odoo import fields
from odoo.http import request


_logger = logging.getLogger(__name__)


class WhatsAppTonerMixin:
    """
    Flujo conversacional para solicitudes de tóner.

    La lógica de negocio existente se conserva:
    - selección de equipo;
    - selección de color;
    - cantidad;
    - lectura automática/manual de contadores;
    - observaciones;
    - confirmación;
    - creación de toner.counter.submission.

    Este mixin también presenta cada paso con mensajes consistentes
    y navegación clara para WhatsApp.
    """

    # ==========================================================
    # Presentación / navegación
    # ==========================================================
    def _toner_navigation_footer(self, include_back=True):
        if hasattr(self, "_flow_navigation_footer"):
            try:
                return self._flow_navigation_footer(
                    include_back=include_back
                )
            except Exception:
                pass

        lines = []
        if include_back:
            lines.append("↩️ Escribe *ATRÁS* para regresar al paso anterior.")
        lines.append("🏠 Escribe *MENU* para volver al menú principal.")
        lines.append("❌ Escribe *CANCELAR* para cancelar la solicitud.")
        return "\n".join(lines)

    def _toner_business_status_safe(self):
        try:
            status = self._compute_business_status()
            return status if isinstance(status, dict) else {}
        except Exception:
            _logger.exception(
                "[WA-TONER] No se pudo evaluar horario para derivación"
            )
            return {}

    def _toner_create_handoff_safe(
        self,
        partner,
        session,
        initial_message,
        reason,
        context=None,
    ):
        """
        Crea el handoff de respaldo sin prometer atención inmediata
        cuando estamos en refrigerio o fuera de horario.

        En horario abierto conserva el comportamiento existente:
        activa modo humano y sesión humana.

        Fuera de horario deja la solicitud pendiente para revisión y
        no activa una conversación humana inmediata.
        """
        context = context if isinstance(context, dict) else {}
        business_status = self._toner_business_status_safe()
        realtime_available = bool(business_status.get("is_open"))

        handoff = False
        try:
            handoff = (
                request.env["whatsapp.handoff"]
                .sudo()
                .create_unknown_intent_handoff(
                    partner,
                    session=session,
                    initial_message=initial_message or "",
                    context={
                        "reason": reason,
                        "flow_context": context,
                        "business_status": business_status,
                        "pending_until_business_hours": not realtime_available,
                    },
                )
            )
        except Exception:
            _logger.exception(
                "[WA-TONER] Error creando handoff de respaldo | "
                "partner_id=%s session_id=%s reason=%s",
                partner.id if partner else False,
                session.id if session else False,
                reason,
            )

        if realtime_available:
            try:
                partner.whatsapp_enable_human_mode_api(
                    taken_by_name="Bot WhatsApp"
                )
                session.action_set_human()
            except Exception:
                _logger.exception(
                    "[WA-TONER] Error activando modo humano | "
                    "partner_id=%s session_id=%s",
                    partner.id if partner else False,
                    session.id if session else False,
                )

            return handoff, True, business_status

        # No dejamos un flujo roto esperando una respuesta humana
        # que no puede llegar inmediatamente.
        try:
            if session and session.current_flow != "none":
                session.reset_conversation(
                    reason="toner_pending_handoff_after_hours"
                )
        except Exception:
            _logger.exception(
                "[WA-TONER] No se pudo cerrar flujo pendiente fuera de horario | "
                "session_id=%s",
                session.id if session else False,
            )

        return handoff, False, business_status

    # ==========================================================
    # Tóner WhatsApp: helpers de máquina, color y contadores
    # ==========================================================
    def _toner_is_color_machine(self, machine):
        """True si el equipo es color."""
        try:
            return bool(machine and getattr(machine, "tipo_maquina_id", False) == "color")
        except Exception:
            return False

    def _toner_counter_valid_hours(self):
        """Ventana fija aceptada para contadores automáticos."""
        return 48

    def _toner_get_machine_counter_date(self, machine):
        """
        Devuelve la fecha más confiable de actualización de contadores.
        Prioridad:
        1) fecha_ultima_actualizacion
        2) pt_last_sync
        """
        if not machine:
            return False

        date_value = False

        try:
            if "fecha_ultima_actualizacion" in machine._fields and machine.fecha_ultima_actualizacion:
                date_value = machine.fecha_ultima_actualizacion
        except Exception:
            date_value = False

        try:
            if not date_value and "pt_last_sync" in machine._fields and machine.pt_last_sync:
                date_value = machine.pt_last_sync
        except Exception:
            pass

        return date_value

    def _toner_format_datetime(self, value):
        if not value:
            return "sin fecha"

        try:
            return fields.Datetime.to_string(value)
        except Exception:
            return str(value)

    def _toner_get_machine_counters(self, machine):
        """
        Obtiene los contadores actuales desde alquiler.
        En el modelo alquiler estos campos son los actuales del equipo:
        - contador_bn
        - contador_color
        """
        if not machine:
            return {
                "counter_bn": 0,
                "counter_color": 0,
                "counter_date": False,
                "counter_date_text": "sin fecha",
            }

        counter_bn = 0
        counter_color = 0

        try:
            counter_bn = int(machine.contador_bn or 0)
        except Exception:
            counter_bn = 0

        try:
            counter_color = int(machine.contador_color or 0)
        except Exception:
            counter_color = 0

        counter_date = self._toner_get_machine_counter_date(machine)

        return {
            "counter_bn": counter_bn,
            "counter_color": counter_color,
            "counter_date": counter_date,
            "counter_date_text": self._toner_format_datetime(counter_date),
        }

    def _toner_has_recent_counters(self, machine):
        """
        Contadores válidos si:
        - La fecha está dentro de las últimas 48 horas.
        - Monocromática: contador_bn > 0.
        - Color: contador_bn > 0 y contador_color > 0.
        """
        if not machine:
            return False, "machine_not_found"

        is_color = self._toner_is_color_machine(machine)
        data = self._toner_get_machine_counters(machine)
        counter_date = data.get("counter_date")

        if not counter_date:
            return False, "counter_date_missing"

        try:
            now = fields.Datetime.now()
            age = now - counter_date
            max_age = timedelta(hours=self._toner_counter_valid_hours())
            if age > max_age:
                return False, "counter_date_expired"
        except Exception:
            _logger.exception(
                "[WA-TONER] Error validando fecha de contadores machine=%s",
                machine.id if machine else False,
            )
            return False, "counter_date_error"

        if not data.get("counter_bn"):
            return False, "counter_bn_missing"

        if is_color and not data.get("counter_color"):
            return False, "counter_color_missing"

        return True, "recent"

    def _toner_counter_reference_text(self, machine):
        """Texto para mostrar al cliente los contadores actuales cargados desde alquiler."""
        if not machine:
            return ""

        data = self._toner_get_machine_counters(machine)
        is_color = self._toner_is_color_machine(machine)
        recent, reason = self._toner_has_recent_counters(machine)

        lines = [
            "📊 *Contadores registrados del equipo*",
            "",
            "• B/N: *%s*" % (data.get("counter_bn") or 0),
        ]

        if is_color:
            lines.append(
                "• Color: *%s*" % (data.get("counter_color") or 0)
            )

        lines.append(
            "• Última actualización: %s"
            % (data.get("counter_date_text") or "sin fecha")
        )
        lines.append("")

        if recent:
            lines.append(
                "Estos contadores se encuentran dentro de la ventana "
                "de actualización de 48 horas y serán utilizados "
                "automáticamente."
            )
        else:
            lines.append(
                "Los contadores no están suficientemente actualizados "
                "o se encuentran incompletos. Por seguridad te solicitaré "
                "la lectura actual."
            )

        return "\n".join(lines)

    def _toner_get_selected_machine_from_context(self, context):
        machine = self._get_context_machine(context)
        if not machine:
            _logger.warning("[WA-TONER] No se pudo obtener máquina desde context=%s", context)
        return machine

    def _toner_build_color_menu(self, machine):
        """
        Menú de colores.
        Monocromática: auto negro.
        Color: negro, cyan, magenta, yellow, kit completo, otro.
        """
        is_color = self._toner_is_color_machine(machine)

        if not is_color:
            return {
                "auto_select": True,
                "options": [
                    {
                        "position": 1,
                        "code": "black",
                        "label": "Negro",
                        "colors": ["black"],
                    }
                ],
                "menu_text": "",
            }

        options = [
            {
                "position": 1,
                "code": "black",
                "label": "Negro",
                "colors": ["black"],
            },
            {
                "position": 2,
                "code": "cyan",
                "label": "Cyan",
                "colors": ["cyan"],
            },
            {
                "position": 3,
                "code": "magenta",
                "label": "Magenta",
                "colors": ["magenta"],
            },
            {
                "position": 4,
                "code": "yellow",
                "label": "Yellow",
                "colors": ["yellow"],
            },
            {
                "position": 5,
                "code": "cmyk",
                "label": "Kit completo CMYK / los 4 colores",
                "colors": ["black", "cyan", "magenta", "yellow"],
            },
            {
                "position": 6,
                "code": "other",
                "label": "Otro / no estoy seguro",
                "colors": [],
            },
        ]

        lines = [
            "🎨 *Selecciona el tóner o color que necesitas*",
            "",
        ]
        for option in options:
            lines.append(
                "*%s* %s" % (
                    option["position"],
                    option["label"],
                )
            )

        lines.extend([
            "",
            "Responde con el *número* de una opción.",
        ])

        return {
            "auto_select": False,
            "options": options,
            "menu_text": "\n".join(lines),
        }

    def _toner_resolve_color_selection(self, text, options):
        raw = (text or "").strip().lower()
        digits = self._only_digits(raw)

        if digits:
            try:
                position = int(digits)
                for option in options:
                    if option.get("position") == position:
                        return {
                            "valid": True,
                            "option": option,
                        }
            except Exception:
                pass

        synonyms = {
            "negro": "black",
            "black": "black",
            "k": "black",
            "bn": "black",
            "b/n": "black",

            "cyan": "cyan",
            "cian": "cyan",
            "c": "cyan",
            "celeste": "cyan",

            "magenta": "magenta",
            "m": "magenta",
            "rosa": "magenta",
            "rosado": "magenta",

            "yellow": "yellow",
            "amarillo": "yellow",
            "y": "yellow",

            "kit": "cmyk",
            "kit completo": "cmyk",
            "cmyk": "cmyk",
            "los 4": "cmyk",
            "los cuatro": "cmyk",
            "todos": "cmyk",
            "todo": "cmyk",
            "4 colores": "cmyk",
            "cuatro colores": "cmyk",

            "otro": "other",
            "no se": "other",
            "no sé": "other",
            "no estoy seguro": "other",
        }

        target = synonyms.get(raw)
        if not target:
            for key, value in synonyms.items():
                if key in raw:
                    target = value
                    break

        if target:
            for option in options:
                if option.get("code") == target:
                    return {
                        "valid": True,
                        "option": option,
                    }

        for option in options:
            label = (option.get("label") or "").strip().lower()
            code = (option.get("code") or "").strip().lower()
            if raw == label or raw == code:
                return {
                    "valid": True,
                    "option": option,
                }

        return {
            "valid": False,
            "message": (
                "⚠️ *Opción no válida*\n\n"
                "No pude relacionar tu respuesta con los colores disponibles. "
                "Responde con el *número* de una opción."
            ),
        }

    def _toner_colors_label(self, colors, fallback_label=False):
        labels = {
            "black": "Negro",
            "cyan": "Cyan",
            "magenta": "Magenta",
            "yellow": "Yellow",
        }

        colors = colors or []

        if colors:
            return ", ".join([labels.get(color, color) for color in colors])

        return fallback_label or "Otro / no estoy seguro"

    def _toner_next_counter_or_observation(self, session, machine, context_update=None):
        """
        Luego de cantidad:
        - Si contadores recientes: cargar automáticamente y pasar a observaciones.
        - Si no recientes: pedir B/N.
        """
        context_update = context_update or {}
        recent, reason = self._toner_has_recent_counters(machine)
        counters = self._toner_get_machine_counters(machine)
        is_color = self._toner_is_color_machine(machine)

        _logger.info(
            "[WA-TONER] Evaluando contadores machine=%s is_color=%s recent=%s reason=%s bn=%s color=%s date=%s",
            machine.id if machine else False,
            is_color,
            recent,
            reason,
            counters.get("counter_bn"),
            counters.get("counter_color"),
            counters.get("counter_date_text"),
        )

        if recent:
            vals = dict(context_update)
            vals.update({
                "counter_recent": True,
                "counter_recent_reason": reason,
                "counter_bn": str(counters.get("counter_bn") or 0),
                "counter_color": str(counters.get("counter_color") or 0) if is_color else "0",
                "counter_source": "alquiler",
                "counter_date_text": counters.get("counter_date_text") or "",
            })
            session.advance_state("awaiting_toner_observations", vals)

            msg = [
                "📊 *Contadores verificados*",
                "",
                "Utilizaré los contadores registrados recientemente:",
                "• B/N: *%s*" % vals["counter_bn"],
            ]
            if is_color:
                msg.append(
                    "• Color: *%s*" % vals["counter_color"]
                )
            msg.append(
                "• Actualización: %s"
                % (vals.get("counter_date_text") or "sin fecha")
            )
            msg.extend([
                "",
                "📝 *Observaciones*",
                "¿Deseas agregar alguna observación a la solicitud?",
                "Si no deseas agregar ninguna, responde *NO*.",
                "",
                self._toner_navigation_footer(include_back=True),
            ])
            return "\n".join(msg)

        vals = dict(context_update)
        vals.update({
            "counter_recent": False,
            "counter_recent_reason": reason,
            "counter_source": "manual_whatsapp",
        })
        session.advance_state("awaiting_toner_counter_bn", vals)

        reference = self._toner_counter_reference_text(machine)
        return (
            "%s\n\n"
            "🧮 *Contador B/N*\n\n"
            "Envíame el contador B/N actual del equipo utilizando solo números.\n\n"
            "%s"
        ) % (
            reference,
            self._toner_navigation_footer(include_back=True),
        )

    def _toner_build_confirmation_summary(self, context):
        is_color = bool(context.get("machine_is_color"))
        colors_label = context.get("toner_color_label") or self._toner_colors_label(
            context.get("toner_colors") or [],
            fallback_label=context.get("toner_color") or "",
        )

        lines = [
            "✅ *Confirma tu solicitud de tóner*",
            "",
            "🖨️ Equipo: *%s*" % (context.get("machine_label") or ""),
            "⚙️ Tipo: %s" % ("Color" if is_color else "Monocromático"),
            "🎨 Tóner solicitado: *%s*" % colors_label,
            "📦 Cantidad: *%s*" % (context.get("toner_quantity") or "1"),
            "📊 Contador B/N: *%s*" % (context.get("counter_bn") or ""),
        ]

        if is_color:
            lines.append(
                "📊 Contador color: *%s*"
                % (context.get("counter_color") or "")
            )

        if context.get("counter_source") == "alquiler":
            lines.append("🔄 Contadores cargados automáticamente: Sí")
            if context.get("counter_date_text"):
                lines.append(
                    "🕒 Fecha de lectura: %s"
                    % context.get("counter_date_text")
                )

        lines.extend([
            "📝 Observaciones: %s"
            % (context.get("observations") or "Sin observaciones"),
            "",
            "Responde:",
            "*SI* — registrar la solicitud",
            "*ATRÁS* — modificar el paso anterior",
            "*CANCELAR* — cancelar la solicitud",
        ])

        return "\n".join(lines)

    def _create_toner_request(self, partner, session, context):
        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False
        machine = self._get_context_machine(context)

        if not machine:
            _logger.error("[WA-TONER] No se encontró machine en context=%s", context)
            return False, "No se encontró equipo seleccionado en el contexto."

        is_color = self._toner_is_color_machine(machine)

        try:
            quantity = int(context.get("toner_quantity") or 1)
        except Exception:
            quantity = 1

        toner_colors = context.get("toner_colors") or []
        toner_color_label = context.get("toner_color_label") or context.get("toner_color") or ""

        if isinstance(toner_colors, str):
            toner_colors = [toner_colors]

        if not is_color:
            toner_colors = ["black"]
            toner_color_label = "Negro"

        counter_bn_raw = context.get("counter_bn")
        counter_color_raw = context.get("counter_color")

        counter_bn = int(self._only_digits(counter_bn_raw) or 0)
        counter_color = 0

        if is_color:
            counter_color = int(self._only_digits(counter_color_raw) or 0)

        _logger.info(
            "[WA-TONER] Creando solicitud partner=%s company=%s machine=%s serie=%s is_color=%s colors=%s qty=%s counter_bn=%s counter_color=%s counter_source=%s",
            partner.id if partner else False,
            company.id if company else False,
            machine.id,
            machine.serie or "",
            is_color,
            toner_colors,
            quantity,
            counter_bn,
            counter_color,
            context.get("counter_source") or "",
        )

        vals = {
            "equipment_id": machine.id,
            "client_name": partner.name or "Cliente WhatsApp",
            "client_email": partner.email or "sin-correo@whatsapp.local",
            "client_phone": partner.whatsapp_number or partner.mobile or partner.phone or "",
            "counter_bn": counter_bn,
            "counter_color": counter_color if is_color else 0,
            "notes": context.get("observations") or "Solicitud generada desde WhatsApp",
            "urgente": True,
        }

        if "black" in toner_colors:
            vals["requiere_toner_black"] = True
            vals["stock_reportado_black"] = 0

        if is_color and "cyan" in toner_colors:
            vals["requiere_toner_cyan"] = True
            vals["stock_reportado_cyan"] = 0

        if is_color and "magenta" in toner_colors:
            vals["requiere_toner_magenta"] = True
            vals["stock_reportado_magenta"] = 0

        if is_color and "yellow" in toner_colors:
            vals["requiere_toner_yellow"] = True
            vals["stock_reportado_yellow"] = 0

        if not toner_colors:
            vals["notes"] = "%s\nColor solicitado: %s\nCantidad: %s" % (
                vals["notes"],
                toner_color_label or "Otro / no estoy seguro",
                quantity,
            )

        if quantity and quantity > 1:
            vals["notes"] = "%s\nCantidad solicitada: %s" % (
                vals["notes"],
                quantity,
            )

        if context.get("counter_source") == "alquiler":
            vals["notes"] = "%s\nContadores cargados automáticamente desde alquiler. Fecha: %s" % (
                vals["notes"],
                context.get("counter_date_text") or "sin fecha",
            )

        try:
            rec = request.env["toner.counter.submission"].sudo().create(vals)

            _logger.info(
                "[WA-TONER] Solicitud creada correctamente rec=%s display=%s vals=%s",
                rec.id,
                rec.display_name,
                vals,
            )

            return rec, False

        except Exception as e:
            _logger.exception(
                "[WA-TONER] Error creando toner.counter.submission vals=%s",
                vals,
            )
            return False, str(e)

    # ==========================================================
    # Flujo tóner: iniciar
    # ==========================================================
    def _start_toner_flow(self, partner, session, identifiers, payload=False):
        company = partner.whatsapp_active_company_id if partner and partner.whatsapp_active_company_id else False
        machines = self._get_partner_machines(partner)

        _logger.info(
            "[WA-TONER] Iniciando flujo toner partner=%s company=%s machines=%s",
            partner.id if partner else False,
            company.id if company else False,
            len(machines) if machines else 0,
        )

        if not machines:
            initial_message = (
                (payload or {}).get("message")
                or (payload or {}).get("text")
                or ""
            )

            handoff, human_active, business_status = (
                self._toner_create_handoff_safe(
                    partner=partner,
                    session=session,
                    initial_message=initial_message,
                    reason=(
                        "No se encontraron equipos alquilados "
                        "para la solicitud de tóner."
                    ),
                    context={
                        "company_id": company.id if company else False,
                    },
                )
            )

            _logger.warning(
                "[WA-TONER] Sin máquinas | partner=%s company=%s "
                "handoff_id=%s human_active=%s business_reason=%s",
                partner.id if partner else False,
                company.id if company else False,
                handoff.id if handoff else False,
                human_active,
                business_status.get("reason") if business_status else False,
            )

            if human_active:
                return (
                    "🖨️ *Solicitud de tóner*\n\n"
                    "No encontré equipos alquilados asociados a la empresa "
                    "activa. He derivado el caso a nuestro equipo para que "
                    "pueda ayudarte a identificar el equipo y continuar "
                    "la solicitud.\n\n"
                    "Por favor mantente atento(a) a este chat."
                )

            return (
                "🖨️ *Solicitud de tóner*\n\n"
                "No encontré equipos alquilados asociados a la empresa "
                "activa. Dejé el caso registrado para revisión de nuestro "
                "equipo al retomar el horario de atención.\n\n"
                "🏠 Escribe *MENU* para volver al menú principal."
            )

        options = []

        for machine in machines:
            counters = self._toner_get_machine_counters(machine)
            recent, reason = self._toner_has_recent_counters(machine)

            machine_link = self._get_toner_url(
                partner=partner,
                company=company,
                machine=machine,
            )

            options.append({
                "id": machine.id,
                "label": self._get_machine_label(machine),
                "is_color": self._toner_is_color_machine(machine),
                "tipo_maquina_id": machine.tipo_maquina_id or "",
                "counter_recent": recent,
                "counter_recent_reason": reason,
                "counter_bn": counters.get("counter_bn") or 0,
                "counter_color": counters.get("counter_color") or 0,
                "counter_date_text": counters.get("counter_date_text") or "",
                "form_url": machine_link,
            })

            _logger.info(
                "[WA-TONER] Opción máquina id=%s serie=%s is_color=%s counter_recent=%s reason=%s bn=%s color=%s date=%s link=%s",
                machine.id,
                machine.serie or "",
                self._toner_is_color_machine(machine),
                recent,
                reason,
                counters.get("counter_bn"),
                counters.get("counter_color"),
                counters.get("counter_date_text"),
                machine_link,
            )

        session.start_flow(
            "toner",
            "awaiting_machine_selection_toner",
            context={
                "intent": "toner",
                "machine_options": options,
                "form_url": False,
            },
        )

        return self._build_machine_menu(
            machines,
            (
                "🖨️ *Solicitud de tóner · Paso 1*\n\n"
                "Selecciona el equipo para el cual necesitas tóner.\n"
                "Responde con el *número* correspondiente:"
            ),
            footer=(
                "Después de seleccionar el equipo continuaremos con el "
                "tipo de tóner, cantidad y contadores.\n\n"
                + self._toner_navigation_footer(include_back=True)
            ),
            include_link=False,
            link=False,
        )

    # ==========================================================
    # Flujo tóner: continuación
    # ==========================================================
    def _continue_toner_flow(self, partner, session, identifiers, text, payload=False):
        context = session.get_context()
        text_clean = (text or "").strip()
        state = session.conversation_state

        _logger.info(
            "[WA-TONER] Continuando flujo partner=%s session=%s state=%s text=%r context=%s",
            partner.id if partner else False,
            session.id if session else False,
            state,
            text_clean,
            context,
        )

        # ==========================================================
        # LINK / FORMULARIO
        # ==========================================================
        if text_clean.lower() in ["link", "enlace", "url", "formulario"]:
            link = context.get("form_url")

            if not link:
                return (
                    "ℹ️ Primero selecciona el equipo de la lista. "
                    "Después podré enviarte el enlace correcto del formulario "
                    "de tóner.\n\n"
                    + self._toner_navigation_footer(include_back=True)
                )

            _logger.info(
                "[WA-TONER] Cliente pidió link session=%s link=%s",
                session.id,
                link,
            )
            return (
                "🔗 *Formulario de solicitud de tóner*\n\n"
                "%s\n\n"
                "%s"
            ) % (
                link,
                self._toner_navigation_footer(include_back=True),
            )

        # ==========================================================
        # CANCELAR FLUJO
        # ==========================================================
        if self._is_no(text_clean) and state not in [
            "awaiting_toner_counter_bn",
            "awaiting_toner_counter_color",
            "awaiting_toner_observations",
            "awaiting_toner_confirmation",
        ]:
            session.reset_conversation(reason="abandoned")
            return (
                "✅ *Solicitud de tóner cancelada*\n\n"
                "La operación actual fue cancelada.\n\n"
                "Escribe *MENU* para volver al menú principal."
            )

        # ==========================================================
        # 1) SELECCIÓN DE EQUIPO
        # ==========================================================
        if state == "awaiting_machine_selection_toner":
            index = self._parse_menu_index(text_clean)
            options = context.get("machine_options") or []

            if not index or index < 1 or index > len(options):
                _logger.info(
                    "[WA-TONER] Selección inválida de equipo input=%r index=%s total=%s session=%s",
                    text_clean,
                    index,
                    len(options),
                    session.id,
                )
                return (
                    "⚠️ *No pude identificar ese equipo*\n\n"
                    "Responde con el *número* de uno de los equipos mostrados.\n\n"
                    + self._toner_navigation_footer(include_back=True)
                )

            selected = options[index - 1]
            machine = request.env["alquiler"].sudo().browse(int(selected.get("id"))).exists()

            if not machine:
                _logger.warning(
                    "[WA-TONER] Máquina seleccionada no existe selected=%s session=%s",
                    selected,
                    session.id,
                )
                return (
                    "⚠️ El equipo seleccionado ya no se encuentra disponible. "
                    "Selecciona nuevamente uno de los equipos de la lista.\n\n"
                    + self._toner_navigation_footer(include_back=True)
                )

            machine_label = selected.get("label") or self._get_machine_label(machine)
            is_color = bool(selected.get("is_color"))

            form_url = selected.get("form_url") or self._get_toner_url(
                partner=partner,
                company=partner.whatsapp_active_company_id if partner else False,
                machine=machine,
            )

            color_menu = self._toner_build_color_menu(machine)

            context_update = {
                "machine_id": machine.id,
                "machine_label": machine_label,
                "machine_is_color": is_color,
                "form_url": form_url,
            }

            if color_menu.get("auto_select"):
                option = color_menu["options"][0]

                context_update.update({
                    "toner_color": option.get("code"),
                    "toner_colors": option.get("colors") or [],
                    "toner_color_label": option.get("label") or "Negro",
                })

                session.advance_state(
                    "awaiting_toner_quantity",
                    context_update,
                )

                _logger.info(
                    "[WA-TONER] Máquina monocromática seleccionada machine=%s session=%s",
                    machine.id,
                    session.id,
                )

                return (
                    "✅ *Equipo seleccionado*\n"
                    "%s\n\n"
                    "⚫ Este equipo es monocromático, por lo que se "
                    "seleccionó automáticamente *tóner negro*.\n\n"
                    "📦 *Solicitud de tóner · Cantidad*\n"
                    "¿Cuántos tóner necesitas? Responde únicamente con un número.\n\n"
                    "%s"
                ) % (
                    machine_label,
                    self._toner_navigation_footer(include_back=True),
                )

            context_update.update({
                "toner_color_options": color_menu.get("options") or [],
            })

            session.advance_state(
                "awaiting_toner_color",
                context_update,
            )

            _logger.info(
                "[WA-TONER] Máquina color seleccionada machine=%s session=%s",
                machine.id,
                session.id,
            )

            return (
                "✅ *Equipo seleccionado*\n"
                "%s\n\n"
                "%s\n\n"
                "%s"
            ) % (
                machine_label,
                color_menu.get("menu_text")
                or "¿Qué color de tóner necesitas?",
                self._toner_navigation_footer(include_back=True),
            )

        # ==========================================================
        # 2) COLOR
        # ==========================================================
        if state == "awaiting_toner_color":
            options = context.get("toner_color_options") or []
            result = self._toner_resolve_color_selection(text_clean, options)

            if not result.get("valid"):
                return (
                    result.get("message")
                    or "⚠️ No pude identificar ese color."
                ) + "\n\n" + self._toner_navigation_footer(include_back=True)

            option = result.get("option") or {}
            colors = option.get("colors") or []
            color_label = self._toner_colors_label(
                colors,
                fallback_label=option.get("label") or text_clean,
            )

            session.advance_state(
                "awaiting_toner_quantity",
                {
                    "toner_color": option.get("code") or text_clean,
                    "toner_colors": colors,
                    "toner_color_label": color_label,
                },
            )

            _logger.info(
                "[WA-TONER] Color seleccionado session=%s option=%s colors=%s",
                session.id,
                option,
                colors,
            )

            return (
                "✅ Tóner seleccionado: *%s*\n\n"
                "📦 *Solicitud de tóner · Cantidad*\n"
                "¿Cuántos tóner necesitas? Responde únicamente con un número.\n\n"
                "%s"
            ) % (
                color_label,
                self._toner_navigation_footer(include_back=True),
            )

        # ==========================================================
        # 3) CANTIDAD
        # ==========================================================
        if state == "awaiting_toner_quantity":
            qty_raw = self._only_digits(text_clean)

            if not qty_raw:
                return (
                    "⚠️ *Cantidad no válida*\n\n"
                    "Indica la cantidad utilizando solo números. "
                    "Ejemplo: *1*.\n\n"
                    + self._toner_navigation_footer(include_back=True)
                )

            try:
                qty = int(qty_raw)
            except Exception:
                qty = 0

            if qty <= 0:
                return (
                    "⚠️ La cantidad debe ser mayor a cero. "
                    "Indica nuevamente la cantidad en números.\n\n"
                    + self._toner_navigation_footer(include_back=True)
                )

            if qty > 10:
                return (
                    "⚠️ *Cantidad fuera del rango habitual*\n\n"
                    "La cantidad indicada es mayor a 10 unidades. "
                    "Revisa el dato e ingresa nuevamente una cantidad válida.\n\n"
                    + self._toner_navigation_footer(include_back=True)
                )

            machine = self._toner_get_selected_machine_from_context(context)

            if not machine:
                handoff, human_active, business_status = (
                    self._toner_create_handoff_safe(
                        partner=partner,
                        session=session,
                        initial_message=text_clean,
                        reason=(
                            "No se encontró la máquina seleccionada "
                            "al solicitar la cantidad de tóner."
                        ),
                        context=context,
                    )
                )

                _logger.warning(
                    "[WA-TONER] Equipo perdido durante flujo | "
                    "session=%s handoff_id=%s human_active=%s reason=%s",
                    session.id if session else False,
                    handoff.id if handoff else False,
                    human_active,
                    business_status.get("reason") if business_status else False,
                )

                if human_active:
                    return (
                        "⚠️ No pude recuperar el equipo seleccionado. "
                        "He derivado la conversación a nuestro equipo para "
                        "continuar la solicitud."
                    )

                return (
                    "⚠️ No pude recuperar el equipo seleccionado. "
                    "El caso quedó registrado para revisión al retomar el "
                    "horario de atención.\n\n"
                    "Escribe *MENU* para iniciar una nueva gestión."
                )

            _logger.info(
                "[WA-TONER] Cantidad recibida qty=%s machine=%s session=%s",
                qty,
                machine.id,
                session.id,
            )

            return self._toner_next_counter_or_observation(
                session,
                machine,
                context_update={
                    "toner_quantity": str(qty),
                },
            )

        # ==========================================================
        # 4) CONTADOR B/N
        # ==========================================================
        if state == "awaiting_toner_counter_bn":
            value = self._only_digits(text_clean)

            if not value:
                return (
                    "⚠️ *Contador B/N no válido*\n\n"
                    "Envía la lectura actual utilizando solo números. "
                    "Este dato es obligatorio.\n\n"
                    + self._toner_navigation_footer(include_back=True)
                )

            machine = self._toner_get_selected_machine_from_context(context)
            is_color = self._toner_is_color_machine(machine)

            if is_color:
                session.advance_state(
                    "awaiting_toner_counter_color",
                    {
                        "counter_bn": value,
                        "counter_source": "manual_whatsapp",
                    },
                )

                _logger.info(
                    "[WA-TONER] Contador BN recibido para equipo color bn=%s session=%s",
                    value,
                    session.id,
                )

                return (
                    "✅ Contador B/N recibido.\n\n"
                    "🎨 *Contador color*\n"
                    "Ahora envía el contador color actual utilizando solo números. "
                    "Este dato es obligatorio para equipos color.\n\n"
                    + self._toner_navigation_footer(include_back=True)
                )

            session.advance_state(
                "awaiting_toner_observations",
                {
                    "counter_bn": value,
                    "counter_color": "0",
                    "counter_source": "manual_whatsapp",
                },
            )

            _logger.info(
                "[WA-TONER] Contador BN recibido para monocromática bn=%s session=%s",
                value,
                session.id,
            )

            return (
                "📝 *Observaciones*\n\n"
                "¿Deseas agregar alguna observación a la solicitud? "
                "Si no deseas agregar ninguna, responde *NO*.\n\n"
                + self._toner_navigation_footer(include_back=True)
            )

        # ==========================================================
        # 5) CONTADOR COLOR
        # ==========================================================
        if state == "awaiting_toner_counter_color":
            value = self._only_digits(text_clean)

            if not value:
                _logger.info(
                    "[WA-TONER] Contador color inválido input=%r session=%s",
                    text_clean,
                    session.id,
                )
                return (
                    "⚠️ *Contador color no válido*\n\n"
                    "Envía la lectura actual utilizando solo números. "
                    "Este dato es obligatorio para equipos color.\n\n"
                    + self._toner_navigation_footer(include_back=True)
                )

            session.advance_state(
                "awaiting_toner_observations",
                {
                    "counter_color": value,
                    "counter_source": "manual_whatsapp",
                },
            )

            _logger.info(
                "[WA-TONER] Contador color recibido color=%s session=%s",
                value,
                session.id,
            )

            return (
                "📝 *Observaciones*\n\n"
                "¿Deseas agregar alguna observación a la solicitud? "
                "Si no deseas agregar ninguna, responde *NO*.\n\n"
                + self._toner_navigation_footer(include_back=True)
            )

        # ==========================================================
        # 6) OBSERVACIONES
        # ==========================================================
        if state == "awaiting_toner_observations":
            observations = "" if self._is_no(text_clean) else text_clean

            context = session.update_context({
                "observations": observations,
            })

            summary = self._toner_build_confirmation_summary(context)

            session.advance_state("awaiting_toner_confirmation")

            _logger.info(
                "[WA-TONER] Resumen generado session=%s context=%s",
                session.id,
                context,
            )

            return summary

        # ==========================================================
        # 7) CONFIRMACIÓN FINAL
        # ==========================================================
        if state == "awaiting_toner_confirmation":
            if not self._is_yes(text_clean):
                if self._is_no(text_clean):
                    session.reset_conversation(reason="abandoned")
                    _logger.info(
                        "[WA-TONER] Confirmación cancelada session=%s",
                        session.id,
                    )
                    return (
                        "✅ *Solicitud de tóner cancelada*\n\n"
                        "No se registró ninguna solicitud.\n\n"
                        "Escribe *MENU* para volver al menú principal."
                    )

                return (
                    "⚠️ Para finalizar, responde *SI* para registrar la solicitud, "
                    "*ATRÁS* para modificarla o *CANCELAR* para salir."
                )

            context = session.get_context()
            rec, error = self._create_toner_request(partner, session, context)

            if rec:
                session.complete_flow(close_reason="completed_toner")

                _logger.info(
                    "[WA-TONER] Flujo completado session=%s rec=%s",
                    session.id,
                    rec.id,
                )

                return (
                    "✅ *Solicitud de tóner registrada correctamente*\n\n"
                    "Número de referencia: *%s*\n\n"
                    "Nuestro equipo continuará con la gestión de acuerdo "
                    "con el proceso de atención correspondiente.\n\n"
                    "Escribe *MENU* si deseas realizar otra gestión."
                ) % (rec.display_name or rec.id)

            handoff, human_active, business_status = (
                self._toner_create_handoff_safe(
                    partner=partner,
                    session=session,
                    initial_message=text_clean,
                    reason=(
                        "No se pudo crear la solicitud de tóner "
                        "automáticamente."
                    ),
                    context={
                        "error": error,
                        "flow_context": context,
                    },
                )
            )

            _logger.error(
                "[WA-TONER] No se pudo crear solicitud | "
                "session=%s error=%s handoff_id=%s human_active=%s "
                "business_reason=%s context=%s",
                session.id,
                error,
                handoff.id if handoff else False,
                human_active,
                business_status.get("reason") if business_status else False,
                context,
            )

            if human_active:
                return (
                    "⚠️ *No pudimos completar el registro automáticamente*\n\n"
                    "Recibimos toda la información de la solicitud y el caso "
                    "fue derivado a nuestro equipo para completarlo.\n\n"
                    "Por favor mantente atento(a) a este chat."
                )

            return (
                "⚠️ *No pudimos completar el registro automáticamente*\n\n"
                "Recibimos la información y dejamos el caso pendiente para "
                "revisión de nuestro equipo al retomar el horario de atención.\n\n"
                "Escribe *MENU* si deseas realizar otra gestión."
            )

        # ==========================================================
        # ESTADO DESCONOCIDO
        # ==========================================================
        _logger.warning(
            "[WA-TONER] Estado no reconocido state=%s session=%s",
            state,
            session.id if session else False,
        )

        return (
            "⚠️ No pude determinar en qué paso de la solicitud te encuentras.\n\n"
            "Para continuar de forma segura, escribe *MENU* y selecciona "
            "nuevamente la opción de tóner."
        )