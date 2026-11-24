# -*- coding: utf-8 -*-

import json
import logging
import secrets
from string import Template
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
        """Vista pública moderna, exclusivamente lectura, asociada a un token.

        No revela teléfonos, correos, DNI, decisiones internas ni tokens de
        aprobación. Presenta siempre el estado real de la solicitud en Odoo.
        """
        not_found = self._tracking_response(
            "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Seguimiento no disponible</title></head>"
            "<body><h2>Seguimiento no disponible</h2>"
            "<p>Verifique el enlace recibido.</p></body></html>",
            status=404,
        )
        if not token or len(token) < 32 or len(token) > 256:
            return not_found
        Submission = request.env["toner.counter.submission"].sudo()
        if "tracking_access_token" not in Submission._fields:
            _logger.error("[TONER][TRACKING] Falta tracking_access_token")
            return not_found
        submission = Submission.search(
            [("tracking_access_token", "=", token)], limit=1
        )
        if not submission or not secrets.compare_digest(
            submission.tracking_access_token or "", token
        ):
            return not_found

        safe = lambda value: str(escape(str(value or "")))
        labels = {
            "recibida": "Solicitud recibida",
            "evaluacion": "En evaluación",
            "pendiente_gerencia": "En evaluación",
            "aprobada_gerencia": "Solicitud aprobada",
            "rechazada_gerencia": "Solicitud no aprobada",
            "devuelta": "Pendiente de corrección",
            "confirmacion_ventas": "Confirmando disponibilidad",
            "lista_despacho": "Preparando entrega",
            "en_despacho": "En despacho",
            "entregada": "Pedido entregado",
            "cancelada": "Solicitud cancelada",
        }
        descriptions = {
            "recibida": "Hemos recibido tu solicitud de tóner y la registramos correctamente.",
            "evaluacion": "Estamos revisando la solicitud y la disponibilidad del consumible.",
            "pendiente_gerencia": "La solicitud se encuentra en proceso de evaluación y autorización.",
            "aprobada_gerencia": "La solicitud ha sido aprobada y continúa su atención.",
            "rechazada_gerencia": "La solicitud no fue aprobada. Comunícate con nuestro equipo para obtener más información.",
            "devuelta": "Se requiere una corrección antes de continuar con la atención.",
            "confirmacion_ventas": "Estamos verificando el stock para preparar el pedido.",
            "lista_despacho": "Los consumibles se encuentran en preparación para su entrega.",
            "en_despacho": "El pedido se encuentra en proceso de despacho.",
            "entregada": "El pedido ha sido registrado como entregado.",
            "cancelada": "La solicitud fue cancelada.",
        }
        stage_index = {
            "recibida": 0,
            "evaluacion": 1,
            "pendiente_gerencia": 1,
            "aprobada_gerencia": 2,
            "confirmacion_ventas": 3,
            "lista_despacho": 3,
            "en_despacho": 4,
            "entregada": 5,
        }.get(submission.state, -1)
        is_exception = submission.state in {
            "rechazada_gerencia", "devuelta", "cancelada"
        }
        # Los estados excepcionales NO se presentan como progresos completados.
        progress = int(round((stage_index + 1) * 100 / 6)) if stage_index >= 0 and not is_exception else 0

        # SVGs autocontenidos; no requiere archivos estáticos ni bibliotecas externas.
        def icon(paths):
            return (
                '<svg viewBox="0 0 24 24" width="22" height="22" '
                'fill="none" stroke="currentColor" stroke-width="1.8" '
                'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                + paths + '</svg>'
            )

        icons = {
            "document": icon('<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>'),
            "search": icon('<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>'),
            "approval": icon('<path d="M9 12l2 2 4-5"/><rect x="3" y="3" width="18" height="18" rx="4"/>'),
            "box": icon('<path d="m12 2 9 5-9 5-9-5 9-5ZM3 7v10l9 5 9-5V7M12 12v10"/>'),
            "truck": icon('<path d="M3 6h11v11H3zM14 10h4l3 4v3h-7"/><circle cx="7" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>'),
            "delivered": icon('<path d="M12 21s7-6 7-12a7 7 0 1 0-14 0c0 6 7 12 7 12Z"/><circle cx="12" cy="9" r="2.5"/>'),
            "printer": icon('<path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v8H6zM18 12h.01"/>'),
            "barcode": icon('<path d="M3 5v14M6 5v14M9 5v14M13 5v14M16 5v14M21 5v14"/>'),
            "info": icon('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>'),
            "check": icon('<path d="m5 12 5 5L20 7"/>'),
            "refresh": icon('<path d="M20 11a8 8 0 0 0-14-5L3 9M3 4v5h5M4 13a8 8 0 0 0 14 5l3-3M21 20v-5h-5"/>'),
        }
        stage_data = [
            ("Solicitud recibida", "Tu solicitud ha sido registrada en el sistema.", "document"),
            ("Evaluación", "Revisión de la solicitud y disponibilidad.", "search"),
            ("Aprobación", "Autorización para continuar con el pedido.", "approval"),
            ("Preparación", "Alistamiento de los consumibles solicitados.", "box"),
            ("Despacho", "Envío del pedido a su destino.", "truck"),
            ("Entrega", "Recepción y cierre del pedido.", "delivered"),
        ]
        stages_html = []
        for index, (name, description, icon_name) in enumerate(stage_data):
            done = not is_exception and stage_index >= index
            current = done and stage_index == index
            stage_class = "step done" if done else "step pending"
            if current:
                stage_class += " current"
            marker = icons["check"] if done else str(index + 1)
            note = '<span class="step-badge">Actual</span>' if current else ""
            stages_html.append(
                '<div class="%s"><div class="step-marker">%s</div>'
                '<div class="step-icon">%s</div><div class="step-copy">'
                '<div class="step-title">%s%s</div><p>%s</p></div></div>'
                % (stage_class, marker, icons[icon_name], safe(name), note, safe(description))
            )
        color_specs = (
            ("black", "Negro", "K"),
            ("cyan", "Cian", "C"),
            ("magenta", "Magenta", "M"),
            ("yellow", "Amarillo", "Y"),
        )
        toner_cards = []
        for key, label, initial in color_specs:
            if getattr(submission, "requiere_toner_%s" % key, False):
                qty = max(0, int(getattr(submission, "cantidad_solicitada_%s" % key, 0) or 0))
                toner_cards.append(
                    '<div class="toner-card toner-%s" aria-label="%s: %s unidades">'
                    '<div class="cartridge" aria-hidden="true"><span class="cartridge-cap"></span>'
                    '<span class="cartridge-body"><b>%s</b></span></div>'
                    '<span class="toner-label">%s <strong>(%s)</strong></span></div>'
                    % (key, safe(label), qty, safe(initial), safe(label), qty)
                )
        if not toner_cards:
            toner_cards = ['<span class="empty-toner">Sin detalle de colores registrados</span>']

        equipment = submission.equipment_id
        model = equipment.name.name if equipment and equipment.name else "Equipo no especificado"
        serial = equipment.serie if equipment else ""
        customer = submission.partner_id.name if submission.partner_id else ""
        delivery = submission.delivery_scheduled_id
        delivery_facts = []
        if delivery and delivery.tracking_number:
            delivery_facts.append(
                '<div><span>N.º de guía</span><strong>%s</strong></div>' % safe(delivery.tracking_number)
            )
        if delivery and (delivery.delivery_date_actual or delivery.delivery_date_planned):
            date_value = delivery.delivery_date_actual or delivery.delivery_date_planned
            date_title = "Fecha de entrega" if delivery.delivery_date_actual else "Entrega programada"
            date_text = date_value.strftime("%d/%m/%Y") if hasattr(date_value, "strftime") else str(date_value)
            delivery_facts.append('<div><span>%s</span><strong>%s</strong></div>' % (date_title, safe(date_text)))
        delivery_html = (
            '<div class="delivery-box"><h3>Información del despacho</h3><div class="delivery-grid">%s</div></div>'
            % "".join(delivery_facts)
        ) if delivery_facts else ""
        status_class = "exception" if is_exception else ("success" if submission.state == "entregada" else "normal")
        state_badge = "Estado de la solicitud" if is_exception else "Estado actual"
        company_row = (
            '<div class="equipment-row"><span class="equipment-icon">%s</span>'
            '<div><small>Cliente</small><strong>%s</strong></div></div>' % (icons["document"], safe(customer))
        ) if customer else ""

        page = Template(r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<meta name="robots" content="noindex,nofollow,noarchive">
<meta name="color-scheme" content="light">
<title>Seguimiento de solicitud de tóner</title>
<style>
:root{font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif;color:#102642;background:#f4f7fc;font-synthesis:none}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(150deg,#eff6ff 0,#f7f9fe 52%,#edf4fc 100%);min-height:100vh}
.site-header{background:#112b51;color:#fff;min-height:70px;display:flex;align-items:center;padding:16px max(22px,calc((100vw - 1200px)/2));gap:14px}
.brand-icon{height:40px;width:40px;display:grid;place-items:center;border-radius:12px;background:#247fe5;color:#fff}
.brand-name{font-weight:750;letter-spacing:.15px;font-size:17px}.brand-sub{margin-left:auto;font-size:13px;color:#c6d8f1}
.hero{position:relative;overflow:hidden;padding:40px 0 34px;background:linear-gradient(110deg,#f6faff,#dfeeff)}
.hero:after{content:"";position:absolute;right:-70px;top:-125px;width:430px;height:320px;border-radius:50%;background:linear-gradient(140deg,#b6d6ff90,#c6c2ff45);transform:rotate(-18deg)}
.container{width:min(1200px,calc(100% - 36px));margin:0 auto}.hero .container{position:relative;z-index:1}
.hero h1{font-size:clamp(25px,3.2vw,38px);line-height:1.17;margin:0 0 10px;letter-spacing:-.8px;border-left:5px solid #2176ec;padding-left:17px}
.hero p{color:#506783;font-size:16px;margin:0 0 0 22px}
main.container{padding:24px 0 40px}
.request-header{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:20px}
.request-number{display:flex;align-items:center;gap:14px;min-width:0}.request-number .icon-square{border-radius:15px;background:#e0edff;color:#1768d5;padding:14px;display:grid;place-items:center}
.request-number small{font-size:12px;color:#58708d}.request-number h2{font-size:clamp(24px,2.6vw,31px);margin:3px 0 0;overflow-wrap:anywhere;letter-spacing:-.4px}
.state-banner{display:flex;align-items:center;gap:13px;border-radius:16px;padding:14px 20px;background:linear-gradient(110deg,#e0edff,#cde3ff);min-width:280px;max-width:525px}
.state-banner.success{background:linear-gradient(110deg,#d5fbe8,#b9f2d5)}.state-banner.exception{background:linear-gradient(110deg,#fff0d5,#ffe0cc)}
.state-round{flex:none;width:46px;height:46px;display:grid;place-items:center;border-radius:50%;background:#247add;color:#fff}.success .state-round{background:#0c9b62}.exception .state-round{background:#c97719}
.state-banner small{font-size:12px;color:#536b82}.state-banner strong{display:block;font-size:19px;line-height:1.25;margin:3px 0}
.grid{display:grid;grid-template-columns:1fr 1.05fr;gap:20px;align-items:start}.card{background:#fff;border:1px solid #e1eaf5;border-radius:21px;padding:24px;box-shadow:0 9px 28px #1736600a}
.card h3{font-size:21px;margin:0 0 22px;display:flex;align-items:center;gap:11px}.section-icon{display:grid;place-items:center;background:#e1efff;color:#116ddd;border-radius:10px;width:41px;height:41px;flex:none}
.equipment-row{display:flex;align-items:center;gap:15px;padding:12px 0;border-bottom:1px solid #e7edf4}.equipment-row:last-child{border-bottom:0}
.equipment-icon{display:grid;place-items:center;color:#226bc1;background:#f1f6fc;width:40px;height:40px;border-radius:11px}.equipment-row small{display:block;font-size:12px;color:#6c7d93;margin-bottom:4px}.equipment-row strong{font-size:15px;overflow-wrap:anywhere}
.section-divider{border:0;border-top:1px solid #e8eef6;margin:23px 0}.toner-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.toner-card{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:13px;min-height:135px;padding:14px 5px;border-radius:14px;text-align:center;background:#f0f2f5;color:#1c2430}
.toner-black{--toner:#252a34;background:#f0f1f4}.toner-cyan{--toner:#00a6dd;background:#e5f7ff}.toner-magenta{--toner:#d81e93;background:#ffebf7}.toner-yellow{--toner:#edb500;background:#fff7d9}
.cartridge{height:47px;width:72px;position:relative;transform:rotate(-10deg);filter:drop-shadow(2px 6px 5px #0c2c4528)}
.cartridge-body{position:absolute;left:11px;top:6px;width:54px;height:34px;background:linear-gradient(165deg,#111c2b,#3c4651 50%,#0d1520);border:2px solid #485766;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#fff;box-shadow:inset 0 -5px 0 var(--toner)}
.cartridge-body b{font-size:13px;color:#fff;border:1px solid #ffffff60;border-radius:4px;padding:1px 5px}.cartridge-cap{position:absolute;left:0;top:12px;width:16px;height:23px;background:#293340;border:2px solid #5c6c7b;border-radius:4px}
.toner-label{font-size:13px;font-weight:700;white-space:nowrap}.toner-label strong{font-weight:700}.empty-toner{color:#6a778b;font-size:14px}
.progress-top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:16px}.progress-top h3{margin:0}.progress-value{color:#166acf;background:#edf5ff;border-radius:30px;padding:7px 12px;font-weight:700;font-size:14px}
.progress-track{height:9px;border-radius:50px;background:#e7edf5;overflow:hidden;margin:0 0 22px}.progress-fill{height:100%;background:linear-gradient(90deg,#1474e9,#35b5ed);border-radius:50px;width:var(--progress)}
.steps{position:relative;padding:0 0 0 6px}.steps:before{position:absolute;content:"";left:22px;top:25px;bottom:26px;width:2px;background:#d9e3ef}
.step{position:relative;display:grid;grid-template-columns:36px 45px minmax(0,1fr);column-gap:13px;align-items:center;margin:0 0 10px;min-height:64px}.step:last-child{margin-bottom:0}
.step-marker{height:36px;width:36px;display:grid;place-items:center;border:2px solid #d0dbe9;border-radius:50%;background:#fff;color:#8190a5;font-weight:700;z-index:1}.step.done .step-marker{background:#1286e8;color:#fff;border-color:#1286e8}
.step-icon{height:43px;width:43px;display:grid;place-items:center;border-radius:12px;background:#f0f3f7;color:#6a7c92}.step.done .step-icon{background:#e7f2ff;color:#1774dc}
.step-copy{border-radius:12px;padding:8px 10px}.step.current .step-copy{background:#e7f2ff}.step-title{font-size:15px;font-weight:760;color:#1d2f47;display:flex;align-items:center;flex-wrap:wrap;gap:8px}
.step p{font-size:12px;color:#697b90;margin:5px 0 0;line-height:1.4}.step-badge{background:#1975de;color:#fff;font-size:10px;border-radius:30px;padding:3px 8px}
.step.pending .step-title{color:#5c6b81}.step.done .step-title{color:#1266c0}
.notice{display:flex;gap:12px;align-items:flex-start;border:1px solid #dbe9f9;background:#ecf5ff;border-radius:17px;padding:17px 19px;margin-top:20px;color:#365777}.notice p{margin:3px 0 0;font-size:13px;line-height:1.5}
.delivery-box{margin-top:20px;padding:18px 20px;border-radius:17px;background:#fff;border:1px solid #e2eaf3}.delivery-box h3{font-size:16px;margin:0 0 12px}.delivery-grid{display:flex;gap:30px;flex-wrap:wrap}.delivery-grid div{display:flex;flex-direction:column;gap:3px}.delivery-grid span{font-size:12px;color:#6b7e94}.delivery-grid strong{font-size:15px}
.footer{padding:20px 0 30px;display:flex;gap:9px;align-items:center;justify-content:center;color:#61748c;font-size:12px;text-align:center}
@media(max-width:900px){.request-header{align-items:stretch;flex-direction:column}.state-banner{max-width:none}.grid{grid-template-columns:1fr}.hero{padding:30px 0}.brand-sub{display:none}}
@media(max-width:520px){.site-header{padding:12px 18px}.hero h1{font-size:25px}.hero p{font-size:13px;margin-left:22px}.container{width:calc(100% - 24px)}.card{padding:17px;border-radius:16px}.request-number h2{font-size:23px}.toner-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.step{grid-template-columns:32px 38px minmax(0,1fr);gap:7px}.steps:before{left:22px}.step-marker{width:32px;height:32px}.step-icon{width:37px;height:37px}.step-copy{padding:8px 5px}.state-banner{min-width:0}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
</style></head><body>
<header class="site-header"><div class="brand-icon">$printer_icon</div><div class="brand-name">Seguimiento de tóner</div><div class="brand-sub">Consulta segura de solicitudes</div></header>
<section class="hero"><div class="container"><h1>Seguimiento de solicitud de tóner</h1><p>Consulta el estado y avance de tu solicitud en cualquier momento.</p></div></section>
<main class="container"><div class="request-header"><div class="request-number"><span class="icon-square">$document_icon</span><div><small>Número de solicitud</small><h2>$sequence</h2></div></div>
<div class="state-banner $status_class"><span class="state-round">$check_icon</span><div><small>$state_badge</small><strong>$status_label</strong></div></div></div>
<div class="grid"><section class="card" aria-label="Resumen de la solicitud"><h3><span class="section-icon">$printer_icon</span>Resumen de la solicitud</h3>
$company_row
<div class="equipment-row"><span class="equipment-icon">$printer_icon</span><div><small>Equipo</small><strong>$model</strong></div></div>
<div class="equipment-row"><span class="equipment-icon">$barcode_icon</span><div><small>Serie</small><strong>$serial</strong></div></div>
<hr class="section-divider"><h3><span class="section-icon">$box_icon</span>Tóner solicitado</h3><div class="toner-grid">$toner_cards</div></section>
<section class="card" aria-label="Avance del pedido"><div class="progress-top"><h3><span class="section-icon">$refresh_icon</span>Avance del pedido</h3><span class="progress-value">$progress_label</span></div>
<div class="progress-track" role="progressbar" aria-label="Avance del pedido" aria-valuemin="0" aria-valuemax="100" aria-valuenow="$progress"><div class="progress-fill" style="--progress:$progress%;"></div></div>
<div class="steps">$steps</div></section></div>
<div class="notice">$info_icon<div><strong>$status_label</strong><p>$status_description</p></div></div>
$delivery_html
<div class="footer">$refresh_icon<span>Esta página se actualiza cada 60 segundos.</span></div>
</main></body></html>""").substitute(
            printer_icon=icons["printer"], document_icon=icons["document"],
            barcode_icon=icons["barcode"], check_icon=(icons["info"] if is_exception else icons["check"]),
            box_icon=icons["box"], refresh_icon=icons["refresh"],
            info_icon=icons["info"], sequence=safe(submission.secuencia),
            status_class=status_class, state_badge=state_badge,
            status_label=safe(labels.get(submission.state, "En proceso")),
            status_description=safe(descriptions.get(submission.state, "Consulta el avance de tu solicitud.")),
            company_row=company_row, model=safe(model), serial=safe(serial),
            toner_cards="".join(toner_cards), steps="".join(stages_html),
            progress=progress, progress_label=(str(progress) + "%") if not is_exception else "Sin avance",
            delivery_html=delivery_html,
        )
        return self._tracking_response(page)

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
