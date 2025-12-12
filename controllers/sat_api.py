# -*- coding: utf-8 -*-
import json
import logging
import traceback

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


def _json_response(payload, status=200):
    body = json.dumps(payload, ensure_ascii=False, default=str)
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
        try:
            payload = request.httprequest.get_json(force=True, silent=True) or {}
        except Exception:
            payload = {}

        dbname = getattr(request.env.cr, "dbname", "unknown_db")
        uid = request.env.user.id
        ip = request.httprequest.remote_addr

        _logger.info("[CHECKIN] db=%s uid=%s ip=%s payload=%s", dbname, uid, ip, payload)

        serial = (payload.get("serial") or "").strip()
        source = (payload.get("source") or "qr").strip().lower()
        raw_value = (payload.get("raw_value") or "").strip()
        action = (payload.get("action") or "lookup").strip().lower()
        search_mode = (payload.get("search_mode") or "exact").strip().lower()

        if not serial:
            return _json_response(
                {"ok": False, "code": "missing_serial", "message": "No se recibió número de serie."},
                status=400,
            )

        Sat = request.env["sat.sat"].sudo()

        # ✅ SOLO “SIN REVISAR” y AÚN NO MARCADO
        def _domain_validos():
            return [
                ("estado_ventas_id", "=", "sin_revisar"),
                ("check_ingreso", "=", False),
            ]

        def _serialize_record(record):
            ingreso_fuente_display = ""
            if "ingreso_fuente" in record._fields and record._fields["ingreso_fuente"].selection:
                ingreso_fuente_selection = dict(record._fields["ingreso_fuente"].selection)
                ingreso_fuente_display = ingreso_fuente_selection.get(record.ingreso_fuente, "")

            return {
                "id": record.id,
                "serie": getattr(record, "serie_id", "") or "",
                "modelo": record.name.name if getattr(record, "name", False) else "",
                "marca": getattr(record, "marca", "") or "",
                "contometro": getattr(record, "contometro", "") or "",
                "estado_ventas": getattr(record, "estado_ventas_id", "") or "",
                "disponibilidad": getattr(record, "disponibilidad_id", "") or "",
                "ubicacion": getattr(record, "ubicacion_id", "") or "",
                "check_ingreso": bool(getattr(record, "check_ingreso", False)),
                "ingreso_estado": getattr(record, "ingreso_estado", "") or "",
                "ingreso_fecha": record.ingreso_fecha and fields.Datetime.to_string(record.ingreso_fecha) or "",
                "ingreso_fuente": getattr(record, "ingreso_fuente", "") or "",
                "ingreso_fuente_display": ingreso_fuente_display,
                "descripcion": getattr(record, "descripcion", "") or "",
                "write_date": record.write_date and fields.Datetime.to_string(record.write_date) or "",
            }

        try:
            # ===== LOOKUP =====
            if action == "lookup":
                is_partial = (search_mode == "partial") or (len(serial) <= 4)

                if is_partial:
                    domain = _domain_validos() + [
                        ("serie_id", "like", "%%%s" % serial),
                    ]
                    records = Sat.search(domain, limit=50)
                    _logger.info("[CHECKIN][LOOKUP][PARTIAL] serial=%s count=%s", serial, len(records))

                    if not records:
                        return _json_response(
                            {
                                "ok": False,
                                "code": "serial_not_found",
                                "message": "No se encontraron equipos SIN REVISAR pendientes con esos dígitos.",
                                "serial": serial,
                                "raw_value": raw_value,
                                "source": source,
                                "search_mode": "partial",
                            },
                            status=200,
                        )

                    return _json_response(
                        {
                            "ok": True,
                            "code": "lookup_partial_ok",
                            "message": "Equipos SIN REVISAR pendientes encontrados por búsqueda parcial.",
                            "serial": serial,
                            "raw_value": raw_value,
                            "source": source,
                            "search_mode": "partial",
                            "count": len(records),
                            "records": [_serialize_record(r) for r in records],
                        },
                        status=200,
                    )

                # exact
                domain = _domain_validos() + [("serie_id", "=", serial)]
                record = Sat.search(domain, limit=1)
                _logger.info("[CHECKIN][LOOKUP][EXACT] serial=%s found=%s id=%s", serial, bool(record), record.id if record else None)

                if not record:
                    return _json_response(
                        {
                            "ok": False,
                            "code": "serial_not_found",
                            "message": "Serie no encontrada (o ya revisada / ya marcada).",
                            "serial": serial,
                            "raw_value": raw_value,
                            "source": source,
                        },
                        status=200,
                    )

                return _json_response(
                    {
                        "ok": True,
                        "code": "lookup_ok",
                        "message": "Serie encontrada (SIN REVISAR pendiente).",
                        "serial": serial,
                        "raw_value": raw_value,
                        "source": source,
                        "record": _serialize_record(record),
                    },
                    status=200,
                )

            # ===== CONFIRM =====
            if action == "confirm":
                domain = _domain_validos() + [("serie_id", "=", serial)]
                record = Sat.search(domain, limit=1)
                _logger.info("[CHECKIN][CONFIRM] serial=%s found=%s id=%s", serial, bool(record), record.id if record else None)

                if not record:
                    return _json_response(
                        {
                            "ok": False,
                            "code": "serial_not_found",
                            "message": "Serie no encontrada para confirmar (o ya revisada / ya marcada).",
                            "serial": serial,
                            "raw_value": raw_value,
                            "source": source,
                        },
                        status=200,
                    )

                status_flag = (payload.get("status") or "ok").strip().lower()
                observation = (payload.get("observation") or "").strip()

                vals = {
                    "check_ingreso": True,
                    "ingreso_fecha": fields.Datetime.now(),
                }

                if "ingreso_fuente" in record._fields and source in ("qr", "ocr", "manual"):
                    vals["ingreso_fuente"] = source

                # si hay observación -> ok_obs, si no -> ok_no_obs
                if observation:
                    vals["ingreso_estado"] = "ok_obs" if status_flag in ("ok", "obs") else "rechazado"

                    tz_dt = fields.Datetime.context_timestamp(record, fields.Datetime.now())
                    stamp = tz_dt.strftime("%d/%m/%Y %H:%M")
                    prefix = f"[Ingreso scanner {source.upper()} {stamp}] "
                    new_line = prefix + observation

                    if "descripcion" in record._fields:
                        desc_old = (record.descripcion or "").strip()
                        vals["descripcion"] = (desc_old + "\n\n" + new_line) if desc_old else new_line
                else:
                    vals["ingreso_estado"] = "ok_no_obs" if status_flag in ("ok", "obs", "") else "rechazado"

                _logger.info("[CHECKIN][CONFIRM][WRITE] id=%s vals=%s", record.id, vals)

                record.write(vals)

                record2 = Sat.browse(record.id)
                if not record2.check_ingreso:
                    _logger.error("[CHECKIN][CONFIRM] WRITE NO EFECTIVO id=%s serial=%s", record.id, serial)
                    return _json_response(
                        {
                            "ok": False,
                            "code": "write_not_effective",
                            "message": "No se pudo registrar el check (write no efectivo).",
                            "serial": serial,
                            "record": _serialize_record(record2),
                        },
                        status=500,
                    )

                return _json_response(
                    {
                        "ok": True,
                        "code": "confirm_ok",
                        "message": "Check de ingreso registrado correctamente.",
                        "serial": serial,
                        "raw_value": raw_value,
                        "source": source,
                        "record": _serialize_record(record2),
                    },
                    status=200,
                )

            return _json_response(
                {"ok": False, "code": "invalid_action", "message": "Acción no soportada. Usa 'lookup' o 'confirm'."},
                status=400,
            )

        except Exception as e:
            _logger.exception("[CHECKIN][FATAL] error=%s", e)
            return _json_response(
                {
                    "ok": False,
                    "code": "server_error",
                    "message": "Error interno en /sat/api/checkin",
                    "error": str(e),
                    "trace": traceback.format_exc()[:4000],
                },
                status=500,
            )
