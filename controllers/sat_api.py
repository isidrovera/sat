# -*- coding: utf-8 -*-

import json
import logging

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


def _json_response(payload, status=200):
    """Helper para devolver JSON plano (sin jsonrpc)."""
    body = json.dumps(payload, ensure_ascii=False)
    return request.make_response(
        body,
        headers=[("Content-Type", "application/json")],
        status=status,
    )


class SatApiController(http.Controller):

    @http.route(
        "/sat/api/checkin",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def sat_checkin(self, **kwargs):
        """
        Endpoint de check de ingreso para el scanner.

        Espera un JSON en el body, por ejemplo:

        LOOKUP:
        {
          "serial": "2RK07735",
          "source": "qr" | "ocr" | "manual",
          "raw_value": "2RK07735",
          "action": "lookup"
        }

        CONFIRM:
        {
          "serial": "2RK07735",
          "source": "qr" | "ocr" | "manual",
          "raw_value": "2RK07735",
          "action": "confirm",
          "status": "ok" | "obs" | "rechazado",
          "observation": "texto opcional"
        }
        """
        # ---------------- Leer JSON del body ----------------
        try:
            payload = request.httprequest.get_json(force=True, silent=True) or {}
        except Exception:
            payload = {}

        _logger.info("sat_checkin payload: %s", payload)

        serial = (payload.get("serial") or "").strip()
        source = (payload.get("source") or "qr").strip().lower()
        raw_value = (payload.get("raw_value") or "").strip()
        action = (payload.get("action") or "lookup").strip().lower()

        if not serial:
            return _json_response(
                {
                    "ok": False,
                    "code": "missing_serial",
                    "message": "No se recibió número de serie.",
                },
                status=400,
            )

        # ---------------- Buscar máquina por serie ----------------
        Sat = request.env["sat.sat"].sudo()
        record = Sat.search([("serie_id", "=", serial)], limit=1)

        if not record:
            return _json_response(
                {
                    "ok": False,
                    "code": "serial_not_found",
                    "message": "Serie no encontrada.",
                    "serial": serial,
                    "raw_value": raw_value,
                    "source": source,
                },
                status=200,
            )

        # Mapeo de selección para mostrar texto legible
        ingreso_fuente_selection = dict(record._fields["ingreso_fuente"].selection)
        ingreso_fuente_display = ingreso_fuente_selection.get(record.ingreso_fuente, "")

        # Info básica del registro para devolver al frontend
        record_data = {
            "id": record.id,
            "serie": record.serie_id,
            "modelo": record.name.name if record.name else "",
            "marca": record.marca or "",
            "tipo_maquina": record.tipo_maquina or "",
            "tipo": record.tipo_id or "",
            "contometro": record.contometro or "",
            "estado_ventas": record.estado_ventas_id or "",
            "disponibilidad": record.disponibilidad_id or "",
            "ubicacion": record.ubicacion_id or "",
            # nuevos campos de ingreso
            "check_ingreso": bool(record.check_ingreso),
            "ingreso_estado": record.ingreso_estado or "",
            "ingreso_fecha": record.ingreso_fecha
            and fields.Datetime.to_string(record.ingreso_fecha)
            or "",
            "ingreso_fuente": record.ingreso_fuente or "",
            "ingreso_fuente_display": ingreso_fuente_display,
        }

        # ---------------- Acción: solo consulta (lookup) ----------------
        if action == "lookup":
            return _json_response(
                {
                    "ok": True,
                    "code": "lookup_ok",
                    "message": "Serie encontrada.",
                    "serial": serial,
                    "raw_value": raw_value,
                    "source": source,
                    "record": record_data,
                },
                status=200,
            )

        # ---------------- Acción: confirmación de ingreso ----------------
        if action == "confirm":
            status_flag = (payload.get("status") or "ok").strip().lower()
            observation = (payload.get("observation") or "").strip()

            vals = {
                "check_ingreso": True,
                "ingreso_fecha": fields.Datetime.now(),
            }

            # Asignar ingreso_fuente usando SIEMPRE el valor técnico de la selección
            # permitidos: 'qr', 'ocr', 'manual'
            if source in ("qr", "ocr", "manual"):
                vals["ingreso_fuente"] = source

            # 1) OK sin observaciones
            if status_flag == "ok" and not observation:
                vals["ingreso_estado"] = "ok_no_obs"

            # 2) OK con observaciones (status=ok u obs + texto)
            elif status_flag in ("ok", "obs") and observation:
                vals["ingreso_estado"] = "ok_obs"

                # Armamos una sola línea limpia para anexar a descripción
                tz_dt = fields.Datetime.context_timestamp(
                    record, fields.Datetime.now()
                )
                stamp = tz_dt.strftime("%d/%m/%Y %H:%M")
                prefix = f"[Ingreso scanner {source.upper()} {stamp}] "
                new_line = prefix + observation

                desc_old = (record.descripcion or "").strip()
                if desc_old:
                    desc_new = desc_old + "\n\n" + new_line
                else:
                    desc_new = new_line

                vals["descripcion"] = desc_new

            # 3) Posible futuro estado “rechazado” u otro
            else:
                vals["ingreso_estado"] = "rechazado"

            # Guardamos cambios
            record.write(vals)

            # Recalcular display de ingreso_fuente después del write
            ingreso_fuente_display = ingreso_fuente_selection.get(
                record.ingreso_fuente, ""
            )

            # refrescamos algunos campos en el dict de respuesta
            record_data.update(
                {
                    "check_ingreso": bool(record.check_ingreso),
                    "ingreso_estado": record.ingreso_estado or "",
                    "ingreso_fecha": record.ingreso_fecha
                    and fields.Datetime.to_string(record.ingreso_fecha)
                    or "",
                    "ingreso_fuente": record.ingreso_fuente or "",
                    "ingreso_fuente_display": ingreso_fuente_display,
                    "descripcion": record.descripcion or "",
                }
            )

            return _json_response(
                {
                    "ok": True,
                    "code": "confirm_ok",
                    "message": "Check de ingreso registrado correctamente.",
                    "serial": serial,
                    "raw_value": raw_value,
                    "source": source,
                    "record": record_data,
                },
                status=200,
            )

        # ---------------- Acción desconocida ----------------
        return _json_response(
            {
                "ok": False,
                "code": "invalid_action",
                "message": "Acción no soportada. Usa 'lookup' o 'confirm'.",
            },
            status=400,
        )
