# -*- coding: utf-8 -*-

import json
import logging

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


def _json_response(payload, status=200):
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
        try:
            payload = request.httprequest.get_json(force=True, silent=True) or {}
        except Exception:
            payload = {}

        serial = (payload.get("serial") or "").strip()
        source = (payload.get("source") or "qr").strip().lower()
        raw_value = (payload.get("raw_value") or "").strip()
        action = (payload.get("action") or "lookup").strip().lower()
        search_mode = (payload.get("search_mode") or "exact").strip().lower()

        _logger.info(
            "[SAT_CHECKIN] action=%s source=%s serial=%s raw=%s search_mode=%s db=%s uid=%s ip=%s",
            action, source, serial, raw_value, search_mode,
            request.env.cr.dbname, request.env.uid,
            request.httprequest.remote_addr,
        )

        if not serial:
            return _json_response(
                {"ok": False, "code": "missing_serial", "message": "No se recibió número de serie."},
                status=400,
            )

        Sat = request.env["sat.sat"].sudo()

        def _serialize_record(record):
            ingreso_fuente_selection = dict(record._fields["ingreso_fuente"].selection)
            ingreso_fuente_display = ingreso_fuente_selection.get(record.ingreso_fuente, "")

            return {
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
                "check_ingreso": bool(record.check_ingreso),
                "ingreso_estado": record.ingreso_estado or "",
                "ingreso_fecha": record.ingreso_fecha and fields.Datetime.to_string(record.ingreso_fecha) or "",
                "ingreso_fuente": record.ingreso_fuente or "",
                "ingreso_fuente_display": ingreso_fuente_display,
            }

        # =========================
        # LOOKUP
        # =========================
        if action == "lookup":
            # partial si lo piden o si son 4 dígitos (solo dígitos)
            is_partial = (search_mode == "partial") or (serial.isdigit() and len(serial) <= 4)

            if is_partial:
                domain = [
                    ("serie_id", "=ilike", f"%{serial}"),
                    ("check_ingreso", "=", False),
                    ("estado_ventas_id", "!=", "entregada"),
                ]
                records = Sat.search(domain, limit=50)
                _logger.info("[SAT_CHECKIN][LOOKUP_PARTIAL] digits=%s found=%s", serial, len(records))

                if not records:
                    return _json_response(
                        {
                            "ok": False,
                            "code": "serial_not_found",
                            "message": "No se encontraron equipos con esos dígitos.",
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
                        "message": "Equipos encontrados por búsqueda parcial.",
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
            record = Sat.search([("serie_id", "=", serial)], limit=1)
            _logger.info("[SAT_CHECKIN][LOOKUP_EXACT] serial=%s found=%s", serial, bool(record))

            if not record:
                return _json_response(
                    {
                        "ok": False,
                        "code": "serial_not_found",
                        "message": "Serie no encontrada.",
                        "serial": serial,
                        "raw_value": raw_value,
                        "source": source,
                        "search_mode": "exact",
                    },
                    status=200,
                )

            return _json_response(
                {
                    "ok": True,
                    "code": "lookup_ok",
                    "message": "Serie encontrada.",
                    "serial": serial,
                    "raw_value": raw_value,
                    "source": source,
                    "search_mode": "exact",
                    "record": _serialize_record(record),
                },
                status=200,
            )

        # =========================
        # CONFIRM
        # =========================
        if action == "confirm":
            record = Sat.search([("serie_id", "=", serial)], limit=1)
            _logger.info("[SAT_CHECKIN][CONFIRM] serial=%s found=%s", serial, bool(record))

            if not record:
                return _json_response(
                    {
                        "ok": False,
                        "code": "serial_not_found",
                        "message": "Serie no encontrada para confirmar ingreso.",
                        "serial": serial,
                        "raw_value": raw_value,
                        "source": source,
                    },
                    status=200,
                )

            status_flag = (payload.get("status") or "ok").strip().lower()
            observation = (payload.get("observation") or "").strip()

            _logger.info(
                "[SAT_CHECKIN][CONFIRM] id=%s pre check_ingreso=%s ingreso_estado=%s ingreso_fuente=%s",
                record.id, record.check_ingreso, record.ingreso_estado, record.ingreso_fuente
            )

            vals = {
                "check_ingreso": True,
                "ingreso_fecha": fields.Datetime.now(),
            }

            if source in ("qr", "ocr", "manual"):
                vals["ingreso_fuente"] = source

            if status_flag == "ok" and not observation:
                vals["ingreso_estado"] = "ok_no_obs"
            elif status_flag in ("ok", "obs") and observation:
                vals["ingreso_estado"] = "ok_obs"

                tz_dt = fields.Datetime.context_timestamp(record, fields.Datetime.now())
                stamp = tz_dt.strftime("%d/%m/%Y %H:%M")
                prefix = f"[Ingreso scanner {source.upper()} {stamp}] "
                new_line = prefix + observation

                desc_old = (record.descripcion or "").strip()
                vals["descripcion"] = (desc_old + "\n\n" + new_line).strip() if desc_old else new_line
            else:
                vals["ingreso_estado"] = "rechazado"

            _logger.info("[SAT_CHECKIN][CONFIRM] write vals=%s", vals)

            try:
                record.write(vals)
                # Forzar persistencia visible inmediatamente (útil cuando pruebas en vivo)
                request.env.cr.flush()
                request.env.cr.commit()
            except Exception as e:
                _logger.exception("[SAT_CHECKIN][CONFIRM] ERROR write/commit: %s", e)
                return _json_response(
                    {"ok": False, "code": "confirm_error", "message": f"Error al registrar ingreso: {e}"},
                    status=500,
                )

            record.invalidate_cache()
            record = Sat.browse(record.id)

            _logger.info(
                "[SAT_CHECKIN][CONFIRM] post check_ingreso=%s ingreso_estado=%s ingreso_fuente=%s ingreso_fecha=%s",
                record.check_ingreso, record.ingreso_estado, record.ingreso_fuente, record.ingreso_fecha
            )

            out = _serialize_record(record)
            out["descripcion"] = record.descripcion or ""

            return _json_response(
                {
                    "ok": True,
                    "code": "confirm_ok",
                    "message": "Check de ingreso registrado correctamente.",
                    "serial": serial,
                    "raw_value": raw_value,
                    "source": source,
                    "record": out,
                },
                status=200,
            )

        return _json_response(
            {"ok": False, "code": "invalid_action", "message": "Acción no soportada. Usa 'lookup' o 'confirm'."},
            status=400,
        )
