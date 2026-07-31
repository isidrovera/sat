# -*- coding: utf-8 -*-

import json
import logging

import requests

from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class TonerRequestController(http.Controller):

    # -------------------------------------------------------------------------
    # Utilidades
    # -------------------------------------------------------------------------

    def clean_phone_number(self, phone):
        phone = (phone or "").replace("@c.us", "")
        phone = "".join(character for character in phone if character.isdigit())
        if phone and not phone.startswith("51") and len(phone) == 9:
            phone = "51" + phone
        return phone

    def _safe_int(self, value, default=0):
        try:
            return int(value or default)
        except (TypeError, ValueError):
            return int(default)

    def _json_response(self, payload, status=200):
        return request.make_response(
            json.dumps(payload, ensure_ascii=False, default=str),
            status=status,
            headers=[("Content-Type", "application/json; charset=utf-8")],
        )

    def _get_office_mail_server(self):
        try:
            server = request.env["ir.mail_server"].sudo().search(
                [("name", "=", "office")],
                limit=1,
            )
            if not server:
                server = request.env["ir.mail_server"].sudo().search([], limit=1)
            return server
        except Exception:
            _logger.exception("[TONER-PORTAL] Error buscando servidor de correo")
            return False

    def _get_effective_counters(self, equipment, post):
        raw_bn = post.get("contometro_black")
        raw_color = post.get("contometro_color")

        counter_bn = (
            self._safe_int(raw_bn)
            if raw_bn not in (None, "")
            else int(equipment.contador_bn or 0)
        )

        if equipment.tipo_maquina_id == "color":
            counter_color = (
                self._safe_int(raw_color)
                if raw_color not in (None, "")
                else int(equipment.contador_color or 0)
            )
        else:
            counter_color = 0

        return counter_bn, counter_color

    def _requested_toners(self, post):
        return {
            "black": bool(post.get("toner_black")),
            "cyan": bool(post.get("toner_cyan")),
            "magenta": bool(post.get("toner_magenta")),
            "yellow": bool(post.get("toner_yellow")),
        }

    # -------------------------------------------------------------------------
    # Formulario
    # -------------------------------------------------------------------------

    @http.route(
        "/toner/solicitar_toner",
        type="http",
        auth="public",
        methods=["GET"],
        website=True,
    )
    def display_toner_request_form(self, **kw):
        try:
            equipment_id = self._safe_int(kw.get("id_registro"))
            if not equipment_id:
                _logger.warning("[TONER-PORTAL] Solicitud sin id_registro")
                return request.redirect("/pagina_error")

            equipment = request.env["alquiler"].sudo().browse(
                equipment_id
            ).exists()
            if not equipment:
                _logger.warning(
                    "[TONER-PORTAL] Equipo inexistente id=%s",
                    equipment_id,
                )
                return request.redirect("/pagina_error")

            phone = self.clean_phone_number(kw.get("phone_number"))
            user_name = kw.get("user_name") or ""
            preloaded_name = user_name
            preloaded_phone = phone

            if request.session.uid:
                user = request.env["res.users"].sudo().browse(
                    request.session.uid
                ).exists()
                if user and user.partner_id:
                    preloaded_name = user.partner_id.name or preloaded_name
                    preloaded_phone = self.clean_phone_number(
                        user.partner_id.mobile
                        or user.partner_id.phone
                        or preloaded_phone
                    )

            stock_info = self._get_equipment_stock_info(equipment)
            duplicate_info = request.env[
                "toner.counter.submission"
            ].sudo().search(
                [
                    ("equipment_id", "=", equipment.id),
                    (
                        "state",
                        "in",
                        request.env[
                            "toner.counter.submission"
                        ].OPEN_STATES,
                    ),
                ],
                order="submission_date desc",
                limit=1,
            )

            values = {
                "id_registro": equipment.id,
                "cliente": equipment.cliente_id.name
                if equipment.cliente_id
                else "",
                "modelo_maquina": equipment.name.name
                if equipment.name
                else "",
                "serie": equipment.serie or "",
                "nombre": preloaded_name,
                "celular": preloaded_phone,
                "ubicacion_instalacion": equipment.ubicacion_instalacion or "",
                "tipo_maquina_id": equipment.tipo_maquina_id,
                "stock_info": stock_info,
                "contador_actual_bn": equipment.contador_bn or 0,
                "contador_actual_color": equipment.contador_color or 0,
                "gestion_automatica": stock_info.get(
                    "gestion_automatica",
                    True,
                ),
                "has_auto_counters": equipment.has_auto_counters,
                "active_request": {
                    "exists": bool(duplicate_info),
                    "sequence": duplicate_info.secuencia
                    if duplicate_info
                    else "",
                    "state": duplicate_info.state
                    if duplicate_info
                    else "",
                },
            }

            _logger.info(
                "[TONER-PORTAL] Formulario preparado equipo=%s serie=%s "
                "auto=%s contador_bn=%s contador_color=%s active=%s",
                equipment.id,
                equipment.serie,
                equipment.has_auto_counters,
                equipment.contador_bn,
                equipment.contador_color,
                duplicate_info.secuencia if duplicate_info else False,
            )

            return request.render(
                "sat.solicitar_toner_form_template",
                {"values": values},
            )
        except Exception:
            _logger.exception(
                "[TONER-PORTAL] Error mostrando formulario kw=%s",
                kw,
            )
            return request.redirect("/pagina_error")

    def _get_equipment_stock_info(self, equipment):
        try:
            result = {
                "black": {
                    "stock_total": equipment.stock_total_toner_black,
                    "stock_cliente": equipment.stock_cliente_toner_black,
                    "instalado": equipment.toner_black_instalado,
                    "stock_minimo": equipment.name.stock_minimo_black
                    if equipment.name
                    else 1,
                },
                "has_color": equipment.tipo_maquina_id == "color",
                "gestion_automatica": (
                    equipment.name.gestionar_toner_automatico
                    if equipment.name
                    else True
                ),
                "estado_stock": equipment.estado_stock_toner,
            }

            if equipment.tipo_maquina_id == "color":
                result.update(
                    {
                        "cyan": {
                            "stock_total": equipment.stock_total_toner_cyan,
                            "stock_cliente": equipment.stock_cliente_toner_cyan,
                            "instalado": equipment.toner_cyan_instalado,
                            "stock_minimo": equipment.name.stock_minimo_cyan
                            if equipment.name
                            else 1,
                        },
                        "magenta": {
                            "stock_total": equipment.stock_total_toner_magenta,
                            "stock_cliente": equipment.stock_cliente_toner_magenta,
                            "instalado": equipment.toner_magenta_instalado,
                            "stock_minimo": equipment.name.stock_minimo_magenta
                            if equipment.name
                            else 1,
                        },
                        "yellow": {
                            "stock_total": equipment.stock_total_toner_yellow,
                            "stock_cliente": equipment.stock_cliente_toner_yellow,
                            "instalado": equipment.toner_yellow_instalado,
                            "stock_minimo": equipment.name.stock_minimo_yellow
                            if equipment.name
                            else 1,
                        },
                    }
                )
            return result
        except Exception:
            _logger.exception(
                "[TONER-PORTAL] Error obteniendo stock equipo=%s",
                equipment.id,
            )
            return {}

    # -------------------------------------------------------------------------
    # Validación previa opcional
    # -------------------------------------------------------------------------

    @http.route(
        "/toner/validate_request_http",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def validate_toner_request_http(self, **post):
        try:
            equipment_id = self._safe_int(post.get("equipment_id"))
            equipment = request.env["alquiler"].sudo().browse(
                equipment_id
            ).exists()
            if not equipment:
                return self._json_response(
                    {
                        "valid": False,
                        "can_create": False,
                        "message": _("Equipo no encontrado."),
                    },
                    status=404,
                )

            counter_bn, counter_color = self._get_effective_counters(
                equipment,
                {
                    "contometro_black": post.get("counter_bn"),
                    "contometro_color": post.get("counter_color"),
                },
            )

            result = request.env[
                "toner.counter.submission"
            ].sudo().validate_web_toner_request(
                equipment_id=equipment.id,
                requested_toners={
                    "black": post.get("toner_black") == "true",
                    "cyan": post.get("toner_cyan") == "true",
                    "magenta": post.get("toner_magenta") == "true",
                    "yellow": post.get("toner_yellow") == "true",
                },
                current_counters={
                    "bn": counter_bn,
                    "color": counter_color,
                },
            )

            _logger.info(
                "[TONER-PORTAL] Validación previa equipo=%s result=%s",
                equipment.id,
                result,
            )
            return self._json_response(result)
        except Exception as error:
            _logger.exception(
                "[TONER-PORTAL] Error en validación previa post=%s",
                post,
            )
            return self._json_response(
                {
                    "valid": False,
                    "can_create": False,
                    "message": str(error),
                },
                status=500,
            )

    # -------------------------------------------------------------------------
    # Registro de solicitud
    # -------------------------------------------------------------------------

    @http.route(
        "/toner/enviar_solicitud",
        type="http",
        auth="public",
        methods=["POST"],
        website=True,
    )
    def send_toner_request(self, **post):
        try:
            required = ["id_registro", "cliente", "nombre", "celular"]
            missing = [field for field in required if not post.get(field)]
            if missing:
                _logger.warning(
                    "[TONER-PORTAL] Campos faltantes=%s post=%s",
                    missing,
                    post,
                )
                return request.redirect("/pagina_error")

            equipment = request.env["alquiler"].sudo().browse(
                self._safe_int(post.get("id_registro"))
            ).exists()
            if not equipment:
                _logger.warning("[TONER-PORTAL] Equipo no encontrado")
                return request.redirect("/pagina_error")

            requested = self._requested_toners(post)
            if not any(requested.values()):
                return self._handle_no_toner_selected(post)

            counter_bn, counter_color = self._get_effective_counters(
                equipment,
                post,
            )

            validation = request.env[
                "toner.counter.submission"
            ].sudo().validate_web_toner_request(
                equipment_id=equipment.id,
                requested_toners=requested,
                current_counters={
                    "bn": counter_bn,
                    "color": counter_color,
                },
            )

            _logger.info(
                "[TONER-PORTAL] Validación final equipo=%s counters=(%s,%s) "
                "requested=%s validation=%s",
                equipment.id,
                counter_bn,
                counter_color,
                requested,
                validation,
            )

            if not validation.get("can_create"):
                return self._handle_blocked_request(
                    post,
                    validation,
                )

            return self._create_received_request(
                post_data=post,
                equipment=equipment,
                counter_bn=counter_bn,
                counter_color=counter_color,
                validation=validation,
            )
        except Exception:
            _logger.exception(
                "[TONER-PORTAL] Error procesando solicitud post=%s",
                post,
            )
            return request.redirect("/pagina_error")

    def _create_received_request(
        self,
        post_data,
        equipment,
        counter_bn,
        counter_color,
        validation,
    ):
        web_data = {
            "equipment_id": equipment.id,
            "client_name": post_data.get("nombre"),
            "client_email": post_data.get(
                "email",
                "soporte@andescopiers.com.pe",
            ),
            "client_phone": self.clean_phone_number(
                post_data.get("celular")
            ),
            "counter_bn": counter_bn,
            "counter_color": counter_color,
            "requires_black": bool(post_data.get("toner_black")),
            "requires_cyan": bool(post_data.get("toner_cyan")),
            "requires_magenta": bool(post_data.get("toner_magenta")),
            "requires_yellow": bool(post_data.get("toner_yellow")),
            "notes": (
                "Solicitud web recibida.\nObservaciones: %s"
                % (
                    post_data.get("observaciones")
                    or "Sin observaciones"
                )
            ),
        }

        result = request.env[
            "toner.counter.submission"
        ].sudo().create_from_web_request(web_data)

        if not result.get("success"):
            if result.get("blocked"):
                return self._handle_blocked_request(
                    post_data,
                    result.get("validation") or validation,
                )
            _logger.error(
                "[TONER-PORTAL] No se pudo crear solicitud result=%s",
                result,
            )
            return request.redirect("/pagina_error")

        self._notify_internal_team_received(
            post_data,
            equipment,
            result,
        )

        values = {
            "creation_result": result,
            "datos_formulario": post_data,
            "validation_result": validation,
        }

        _logger.info(
            "[TONER-PORTAL] Solicitud recibida secuencia=%s equipo=%s",
            result.get("secuencia"),
            equipment.id,
        )

        # Este template debe reemplazar al antiguo
        # sat.solicitud_toner_aprobada, porque todavía no hay aprobación.
        return request.render(
            "sat.solicitud_toner_recibida",
            values,
        )

    # -------------------------------------------------------------------------
    # Respuestas bloqueadas
    # -------------------------------------------------------------------------

    def _handle_no_toner_selected(self, post_data):
        data = self._form_data(post_data)
        message = (
            "*🏢 Soporte*\n\n"
            "⚠️ *Solicitud incompleta*\n\n"
            "No se registró la solicitud porque no se seleccionó ningún tóner.\n"
        )
        self.send_whatsapp_message_toner(data["celular"], message)
        return request.render(
            "sat.solicitud_toner_sin_seleccion",
            {"datos_formulario": data},
        )

    def _handle_blocked_request(self, post_data, validation):
        data = self._form_data(post_data)
        reason = validation.get(
            "message",
            _("La solicitud no puede registrarse."),
        )

        if validation.get("reason") == "duplicate":
            heading = _("Ya existe una solicitud activa")
        else:
            heading = _("La solicitud requiere corrección")

        message = (
            "*🏢 Soporte*\n\n"
            "⚠️ *%s*\n\n"
            "%s\n\n"
            "🖨️ *Equipo:* %s\n"
            "🔢 *Serie:* %s\n"
        ) % (
            heading,
            reason,
            data["modelo_maquina"],
            data["serie"],
        )
        self.send_whatsapp_message_toner(data["celular"], message)

        self._notify_internal_team_blocked(data, validation)

        return request.render(
            "sat.solicitud_toner_rechazada",
            {
                "validation_result": validation,
                "datos_formulario": data,
            },
        )

    def _form_data(self, post_data):
        return {
            "cliente": post_data.get("cliente") or "",
            "nombre": post_data.get("nombre") or "",
            "celular": self.clean_phone_number(
                post_data.get("celular")
            ),
            "modelo_maquina": post_data.get("modelo_maquina") or "",
            "serie": post_data.get("serie") or "",
        }

    # -------------------------------------------------------------------------
    # Notificaciones internas
    # -------------------------------------------------------------------------

    def _notify_internal_team_received(
        self,
        post_data,
        equipment,
        creation_result,
    ):
        server = self._get_office_mail_server()
        try:
            body = """
                <h3>Nueva solicitud de tóner recibida</h3>
                <p><strong>Solicitud:</strong> %s</p>
                <p><strong>Cliente:</strong> %s</p>
                <p><strong>Solicitante:</strong> %s</p>
                <p><strong>Equipo:</strong> %s</p>
                <p><strong>Serie:</strong> %s</p>
                <p><strong>Estado:</strong> Recibida, pendiente de evaluación</p>
                <p><strong>Requiere evidencia:</strong> %s</p>
            """ % (
                creation_result.get("secuencia"),
                post_data.get("cliente"),
                post_data.get("nombre"),
                equipment.name.name if equipment.name else "Sin modelo",
                equipment.serie or "Sin serie",
                "Sí"
                if creation_result.get("requires_evidence")
                else "No",
            )

            request.env["mail.mail"].sudo().create(
                {
                    "subject": "Nueva solicitud de tóner - %s"
                    % creation_result.get("secuencia"),
                    "body_html": body,
                    "email_from": "soporte@andescopiers.com.pe",
                    "email_to": "comercial01@andescopiers.com.pe",
                    "email_cc": "comercial@andescopiers.com.pe",
                    "mail_server_id": server.id if server else False,
                }
            ).send()
        except Exception:
            _logger.exception(
                "[TONER-PORTAL] Error notificando solicitud recibida"
            )

    def _notify_internal_team_blocked(self, data, validation):
        server = self._get_office_mail_server()
        try:
            body = """
                <h3>Intento de solicitud de tóner bloqueado</h3>
                <p><strong>Cliente:</strong> %s</p>
                <p><strong>Solicitante:</strong> %s</p>
                <p><strong>Equipo:</strong> %s</p>
                <p><strong>Serie:</strong> %s</p>
                <p><strong>Motivo:</strong> %s</p>
            """ % (
                data["cliente"],
                data["nombre"],
                data["modelo_maquina"],
                data["serie"],
                validation.get("message"),
            )
            request.env["mail.mail"].sudo().create(
                {
                    "subject": "Solicitud de tóner bloqueada - %s"
                    % data["serie"],
                    "body_html": body,
                    "email_from": "soporte@andescopiers.com.pe",
                    "email_to": "comercial01@andescopiers.com.pe",
                    "email_cc": "comercial@andescopiers.com.pe",
                    "mail_server_id": server.id if server else False,
                }
            ).send()
        except Exception:
            _logger.exception(
                "[TONER-PORTAL] Error notificando bloqueo"
            )

    # -------------------------------------------------------------------------
    # WhatsApp
    # -------------------------------------------------------------------------

    def send_whatsapp_message_toner(self, phone, message):
        phone = self.clean_phone_number(phone)
        if not phone:
            return False

        try:
            parameters = request.env[
                "ir.config_parameter"
            ].sudo()
            base_url = parameters.get_param(
                "sat.whatsapp_gateway_base_url"
            )
            api_key = parameters.get_param(
                "sat.whatsapp_gateway_api_key"
            )
            if not base_url or not api_key:
                _logger.error(
                    "[TONER-PORTAL] Configuración WhatsApp incompleta"
                )
                return False

            response = requests.post(
                "%s/api/send-message" % base_url.rstrip("/"),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                },
                json={"to": phone, "message": message},
                timeout=30,
            )
            data = response.json()
            if response.status_code == 200 and data.get("success"):
                _logger.info(
                    "[TONER-PORTAL] WhatsApp enviado teléfono=%s",
                    phone,
                )
                return True

            _logger.error(
                "[TONER-PORTAL] Error WhatsApp status=%s response=%s",
                response.status_code,
                response.text[:500],
            )
            return False
        except Exception:
            _logger.exception(
                "[TONER-PORTAL] Excepción enviando WhatsApp"
            )
            return False


    # -------------------------------------------------------------------------
    # Decisión segura de gerencia
    # -------------------------------------------------------------------------

    @http.route(
        "/toner/management/<string:token>/<string:decision>",
        type="http",
        auth="public",
        methods=["GET"],
        website=True,
        csrf=False,
        sitemap=False,
    )
    def toner_management_decision_page(
        self,
        token,
        decision,
        **kwargs,
    ):
        submission = request.env[
            "toner.counter.submission"
        ].sudo().search(
            [("management_access_token", "=", token)],
            limit=1,
        )

        values = {
            "submission": submission,
            "token": token,
            "decision": decision,
            "error": False,
        }

        if not submission:
            values["error"] = _(
                "El enlace no corresponde a una solicitud válida."
            )
        else:
            try:
                submission._ensure_management_token_valid(token)
                if decision not in {
                    "approve",
                    "request_information",
                    "reject",
                    "cancel",
                }:
                    values["error"] = _(
                        "La acción indicada no es válida."
                    )
            except Exception as error:
                values["error"] = str(error)

        return request.render(
            "sat.toner_management_decision_page",
            values,
        )

    @http.route(
        "/toner/management/confirm",
        type="http",
        auth="public",
        methods=["POST"],
        website=True,
        csrf=True,
        sitemap=False,
    )
    def toner_management_decision_confirm(self, **post):
        token = post.get("token")
        decision = post.get("decision")
        decision_name = post.get("decision_name")
        notes = post.get("notes")

        submission = request.env[
            "toner.counter.submission"
        ].sudo().search(
            [("management_access_token", "=", token)],
            limit=1,
        )

        values = {
            "submission": submission,
            "decision": decision,
            "success": False,
            "error": False,
        }

        if not submission:
            values["error"] = _(
                "El enlace no corresponde a una solicitud válida."
            )
        else:
            try:
                forwarded_for = request.httprequest.headers.get(
                    "X-Forwarded-For",
                    "",
                )
                remote_ip = (
                    forwarded_for.split(",")[0].strip()
                    if forwarded_for
                    else request.httprequest.remote_addr
                )

                submission.register_management_decision(
                    token=token,
                    decision=decision,
                    decision_name=decision_name,
                    notes=notes,
                    remote_ip=remote_ip,
                )
                values["success"] = True
            except Exception as error:
                _logger.exception(
                    "[TONER-MANAGEMENT] Error decisión "
                    "solicitud=%s decision=%s",
                    submission.id,
                    decision,
                )
                values["error"] = str(error)

        return request.render(
            "sat.toner_management_decision_result",
            values,
        )

    # -------------------------------------------------------------------------
    # Confirmación antigua
    # -------------------------------------------------------------------------

    @http.route(
        "/pagina_confirmacion_toner",
        type="http",
        auth="public",
        website=True,
    )
    def pagina_confirmacion(self, **kw):
        return request.render("sat.pagina_confirmacion_toner")
