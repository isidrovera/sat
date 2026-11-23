# -*- coding: utf-8 -*-

import json
import logging
import secrets
from markupsafe import escape

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
        """Obtiene los contadores efectivos de la solicitud.

        Si el cliente envía un valor, se utiliza ese valor y posteriormente el
        modelo valida que sea > 0 y que nunca sea menor al último contador
        conocido. Si el formulario no envía contador, solamente se reutiliza el
        contador almacenado cuando ``has_auto_counters`` confirma que su lectura
        tiene como máximo 3 días de antigüedad.
        """
        raw_bn = post.get("contometro_black")
        raw_color = post.get("contometro_color")
        has_recent_auto = bool(equipment.has_auto_counters)

        if raw_bn not in (None, ""):
            counter_bn = self._safe_int(raw_bn)
            source_bn = "cliente"
        elif has_recent_auto:
            counter_bn = int(equipment.contador_bn or 0)
            source_bn = "automatico"
        else:
            counter_bn = 0
            source_bn = "sin_lectura_vigente"

        if equipment.tipo_maquina_id == "color":
            if raw_color not in (None, ""):
                counter_color = self._safe_int(raw_color)
                source_color = "cliente"
            elif has_recent_auto:
                counter_color = int(equipment.contador_color or 0)
                source_color = "automatico"
            else:
                counter_color = 0
                source_color = "sin_lectura_vigente"
        else:
            counter_color = 0
            source_color = "no_aplica"

        _logger.info(
            "[TONER-PORTAL] Contadores efectivos equipo=%s serie=%s "
            "bn=%s fuente_bn=%s color=%s fuente_color=%s auto_vigente=%s",
            equipment.id,
            equipment.serie,
            counter_bn,
            source_bn,
            counter_color,
            source_color,
            has_recent_auto,
        )

        return counter_bn, counter_color

    def _requested_toners(self, post):
        return {
            "black": bool(post.get("toner_black")),
            "cyan": bool(post.get("toner_cyan")),
            "magenta": bool(post.get("toner_magenta")),
            "yellow": bool(post.get("toner_yellow")),
        }

    # -------------------------------------------------------------------------
    # Seguimiento público de una solicitud — solamente lectura
    # -------------------------------------------------------------------------

    def _tracking_enabled(self):
        value = request.env["ir.config_parameter"].sudo().get_param(
            "sat.toner_tracking_enabled", "False"
        )
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _tracking_response(self, content, status=200):
        return request.make_response(
            content,
            status=status,
            headers=[
                ("Content-Type", "text/html; charset=utf-8"),
                ("Cache-Control", "no-store, no-cache, must-revalidate, private"),
                ("Pragma", "no-cache"),
                ("X-Robots-Tag", "noindex, nofollow, noarchive"),
                ("Referrer-Policy", "no-referrer"),
                ("X-Content-Type-Options", "nosniff"),
            ],
        )

    @http.route(
        "/toner/seguimiento/<string:token>",
        type="http", auth="public", website=False,
        methods=["GET"], sitemap=False, csrf=False,
    )
    def toner_customer_tracking(self, token, **kwargs):
        """La posesión del token da acceso SOLO al estado de esta solicitud.

        No se muestra contacto, correo, DNI, IP, evaluación interna ni token
        gerencial. La página se refresca sola y consulta siempre datos Odoo.
        """
        not_found = self._tracking_response(
            "<!doctype html><html lang='es'><meta charset='utf-8'>"
            "<title>Seguimiento no disponible</title>"
            "<body><h2>Seguimiento no disponible</h2>"
            "<p>Verifique el enlace recibido.</p></body></html>",
            status=404,
        )
        if not token or len(token) < 32 or len(token) > 256:
            return not_found
        # El token no es un ID secuencial y no debe confundirse con el
        # management_access_token usado para aprobar o rechazar solicitudes.
        Submission = request.env["toner.counter.submission"].sudo()
        if "tracking_access_token" not in Submission._fields:
            _logger.error("[TONER][TRACKING] Falta tracking_access_token en modelo")
            return not_found
        submission = Submission.search([
            ("tracking_access_token", "=", token)
        ], limit=1)
        if not submission or not secrets.compare_digest(
            submission.tracking_access_token or "", token
        ):
            return not_found

        labels = {
            "recibida": "Solicitud recibida",
            "evaluacion": "En evaluación",
            "pendiente_gerencia": "En evaluación",
            "aprobada_gerencia": "Aprobada",
            "rechazada_gerencia": "No aprobada",
            "devuelta": "Pendiente de corrección",
            "confirmacion_ventas": "Confirmando disponibilidad",
            "lista_despacho": "Preparando entrega",
            "en_despacho": "En despacho",
            "entregada": "Entregada",
            "cancelada": "Cancelada",
        }
        status_label = labels.get(submission.state, "En proceso")
        steps = [
            ("recibida", "Solicitud recibida"),
            ("evaluacion", "Evaluación"),
            ("aprobada_gerencia", "Aprobación"),
            ("lista_despacho", "Preparación"),
            ("en_despacho", "Despacho"),
            ("entregada", "Entrega"),
        ]
        stage_index = {
            "recibida": 0, "evaluacion": 1, "pendiente_gerencia": 1,
            "aprobada_gerencia": 2, "confirmacion_ventas": 3,
            "lista_despacho": 3, "en_despacho": 4, "entregada": 5,
        }.get(submission.state, -1)
        terminal = submission.state in (
            "rechazada_gerencia", "devuelta", "cancelada"
        )
        step_list = "".join(
            '<li class="%s"><span class="dot">%s</span>%s</li>' % (
                "complete" if not terminal and i <= stage_index else "",
                i + 1, escape(title),
            )
            for i, (_, title) in enumerate(steps)
        )
        colors = [
            ("black", "Negro"), ("cyan", "Cian"),
            ("magenta", "Magenta"), ("yellow", "Amarillo"),
        ]
        color_info = []
        for key, label in colors:
            if getattr(submission, "requiere_toner_%s" % key, False):
                requested = max(0, int(getattr(
                    submission, "cantidad_solicitada_%s" % key, 0
                ) or 0))
                color_info.append("%s (%s)" % (label, requested))
        delivery = submission.delivery_scheduled_id
        tracking_number = ""
        delivery_date = ""
        if delivery:
            tracking_number = delivery.tracking_number or ""
            when = delivery.delivery_date_actual or delivery.delivery_date_planned
            delivery_date = str(when) if when else ""
        equipment = submission.equipment_id
        model = equipment.name.name if equipment and equipment.name else "Equipo"
        serial = equipment.serie if equipment else ""
        safe = lambda x: str(escape(str(x or "")))
        body = """<!doctype html><html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>Seguimiento de tóner</title><style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#203040;background:#f4f6f9}
body{margin:0;padding:24px 12px}main{max-width:650px;margin:auto;background:#fff;border-radius:16px;padding:24px;box-shadow:0 3px 22px #13263b12}
h1{font-size:24px;margin:0 0 8px}h2{font-size:18px;margin:18px 0 8px}
small{color:#617184}p{line-height:1.5}ul{padding-left:0;list-style:none}
li{padding:10px;border-left:3px solid #d6dee8;margin-left:12px;color:#607184}
li.complete{border-color:#1c925f;color:#1b6747;font-weight:600}
.dot{display:inline-block;width:24px;color:#718096}.complete .dot{color:#1c925f}
.state{background:#e8f1fd;border-radius:8px;padding:12px 14px;font-weight:700}
.detail{border-top:1px solid #e5eaf0;padding-top:12px;margin-top:12px}
strong{color:#263b50}</style></head><body><main>
<h1>COPIER COMPANY S.A.C.</h1><small>Seguimiento de solicitud de tóner</small>
<h2>Solicitud %s</h2><div class="state">%s</div>
<div class="detail"><p><strong>Equipo:</strong> %s</p>
<p><strong>Serie:</strong> %s</p><p><strong>Tóner solicitado:</strong> %s</p></div>
<h2>Avance del pedido</h2><ul>%s</ul>
%s%s
<p><small>Información actualizada directamente desde Odoo. Esta página se refresca cada 60 segundos.</small></p>
</main></body></html>""" % (
            safe(submission.secuencia), safe(status_label),
            safe(model), safe(serial), safe(", ".join(color_info) or "Sin detalle"),
            step_list,
            "<p><strong>Guía:</strong> %s</p>" % safe(tracking_number) if tracking_number else "",
            "<p><strong>Fecha prevista/real:</strong> %s</p>" % safe(delivery_date) if delivery_date else "",
        )
        return self._tracking_response(body)

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
                        user.partner_id.phone
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
                # Solo precargar como "actual" un contador automático vigente.
                # Si la lectura tiene más de 3 días se envía 0 para obligar a
                # registrar una lectura actual en el formulario.
                "contador_actual_bn": (
                    equipment.contador_bn if equipment.has_auto_counters else 0
                ),
                "contador_actual_color": (
                    equipment.contador_color
                    if equipment.has_auto_counters
                    and equipment.tipo_maquina_id == "color"
                    else 0
                ),
                "ultimo_contador_conocido_bn": equipment.contador_bn or 0,
                "ultimo_contador_conocido_color": equipment.contador_color or 0,
                # La fecha mostrada debe corresponder al contador guardado.
                # pt_last_sync no se usa porque una sincronización puede ser
                # reciente aunque los contadores sean antiguos.
                "fecha_ultimo_contador": equipment.fecha_ultima_actualizacion or False,
                "counter_max_age_days": 3,
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
        if not self._tracking_enabled():
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
        if not self._tracking_enabled():
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

    # -------------------------------------------------------------------------
    # API privada de n8n + IA (sobre el controlador existente)
    # -------------------------------------------------------------------------

    def _n8n_json(self, payload, status=200):
        response = self._json_response(payload, status=status)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def _n8n_authenticate(self):
        """Misma clave configurada para el webhook saliente.

        La clave se envía exclusivamente en Authorization: Bearer ... o
        x-api-key, nunca en un query string.
        """
        ICP = request.env["ir.config_parameter"].sudo()
        configured = (ICP.get_param("sat.toner_n8n_api_key") or "").strip()
        if not configured or len(configured) < 24:
            return False
        header = request.httprequest.headers.get("Authorization", "")
        presented = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if not presented:
            presented = request.httprequest.headers.get("X-API-Key", "").strip()
        return bool(presented and secrets.compare_digest(configured, presented))

    def _n8n_enabled(self):
        ICP = request.env["ir.config_parameter"].sudo()
        return (ICP.get_param("sat.toner_control_engine", "odoo") or "odoo").strip().lower() == "n8n"

    @http.route(
        "/toner/n8n/health", type="http", auth="public",
        methods=["GET"], csrf=False, website=False, sitemap=False,
    )
    def toner_n8n_health(self, **kwargs):
        """Permite comprobar credenciales y modo, sin filtrar datos."""
        if not self._n8n_authenticate():
            return self._n8n_json({"success": False, "error": "unauthorized"}, 401)
        return self._n8n_json({
            "success": True,
            "engine": "n8n" if self._n8n_enabled() else "odoo",
            "n8n_active": self._n8n_enabled(),
            "schema_version": 1,
        })

    @http.route(
        "/toner/n8n/context/<int:event_id>", type="http", auth="public",
        methods=["GET"], csrf=False, website=False, sitemap=False,
    )
    def toner_n8n_context(self, event_id, **kwargs):
        """Contexto de solo lectura para una evaluación de IA.

        Los movimientos de stock y la autorización nunca se delegan a n8n.
        """
        if not self._n8n_authenticate():
            return self._n8n_json({"success": False, "error": "unauthorized"}, 401)
        if not self._n8n_enabled():
            return self._n8n_json({"success": False, "error": "n8n_not_selected"}, 409)
        Event = request.env["toner.monitoring.event"].sudo()
        event = Event.browse(event_id).exists()
        if not event:
            return self._n8n_json({"success": False, "error": "not_found"}, 404)
        equipment = event.equipment_id
        if not equipment or event.color not in ("black", "cyan", "magenta", "yellow"):
            return self._n8n_json({"success": False, "error": "invalid_event"}, 422)
        # _reserve_snapshot proviene del modelo de monitoreo actualizado;
        # en versiones anteriores, no se debe adivinar el stock.
        if not hasattr(event, "_reserve_snapshot"):
            return self._n8n_json({"success": False, "error": "missing_stock_engine"}, 503)
        stock = event._reserve_snapshot()
        Submission = request.env["toner.counter.submission"].sudo()
        open_requests = Submission.search([
            ("equipment_id", "=", equipment.id),
            ("state", "in", Submission.OPEN_STATES),
            ("requiere_toner_%s" % event.color, "=", True),
        ], order="submission_date desc, id desc", limit=20)
        data = {
            "schema_version": 1,
            "event_id": event.id,
            "event_type": event.event_type,
            "source": event.source,
            "event_date": str(event.event_date or ""),
            "color": event.color,
            "level_available": bool(event.level_available),
            "level_percent": float(event.level_percent or 0) if event.level_available else None,
            "counter_bn": int(event.counter_bn or 0) if event.counter_bn_available else None,
            "counter_color": int(event.counter_color or 0) if event.counter_color_available else None,
            "physical_replacement_confirmed": bool(event.physical_replacement_confirmed),
            "equipment": {"id": equipment.id, "serial": equipment.serie or "", "model": equipment.name.name if equipment.name else ""},
            "stock": stock,
            "open_requests": [{"id": r.id, "sequence": r.secuencia, "state": r.state} for r in open_requests],
            "allowed_decisions": ["create_request", "ignore", "review"],
        }
        return self._n8n_json({"success": True, "context": data})

    @http.route(
        "/toner/n8n/submission/<int:submission_id>", type="http",
        auth="public", methods=["GET"], csrf=False, website=False,
        sitemap=False,
    )
    def toner_n8n_submission_status(self, submission_id, **kwargs):
        """Estado interno mínimo para correlación con los flujos n8n."""
        if not self._n8n_authenticate():
            return self._n8n_json({"success": False, "error": "unauthorized"}, 401)
        if not self._n8n_enabled():
            return self._n8n_json({"success": False, "error": "n8n_not_selected"}, 409)
        submission = request.env["toner.counter.submission"].sudo().browse(submission_id).exists()
        if not submission:
            return self._n8n_json({"success": False, "error": "not_found"}, 404)
        return self._n8n_json({
            "success": True,
            "submission_id": submission.id,
            "sequence": submission.secuencia,
            "state": submission.state,
            "engine": submission.control_engine if "control_engine" in submission._fields else "odoo",
            "delivery_state": submission.delivery_scheduled_id.state if submission.delivery_scheduled_id else None,
        })
