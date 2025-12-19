# -*- coding: utf-8 -*-
import json
import logging
import traceback
import time

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
        t0 = time.time()

        # ---------- parse payload ----------
        try:
            payload = request.httprequest.get_json(force=True, silent=True) or {}
        except Exception as e:
            _logger.warning("[CHECKIN][PAYLOAD] JSON parse failed: %s", e)
            payload = {}

        # ---------- request context ----------
        dbname = getattr(request.env.cr, "dbname", "unknown_db")
        uid = request.env.user.id
        ip = request.httprequest.remote_addr
        ua = request.httprequest.headers.get("User-Agent", "-")
        origin = request.httprequest.headers.get("Origin", "-")
        referer = request.httprequest.headers.get("Referer", "-")

        _logger.info(
            "[CHECKIN][IN] db=%s uid=%s ip=%s origin=%s referer=%s ua=%s payload=%s",
            dbname, uid, ip, origin, referer, ua, payload
        )

        serial = (payload.get("serial") or "").strip()
        source = (payload.get("source") or "qr").strip().lower()
        raw_value = (payload.get("raw_value") or "").strip()
        action = (payload.get("action") or "lookup").strip().lower()
        search_mode = (payload.get("search_mode") or "exact").strip().lower()

        _logger.info(
            "[CHECKIN][ARGS] action=%s serial=%s search_mode=%s source=%s raw_value=%s",
            action, serial, search_mode, source, raw_value
        )

        Sat = request.env["sat.sat"].sudo()
        _logger.info("[CHECKIN][MODEL] model=sat.sat sudo=True")

        # ✅ PENDIENTES: sin_revisar + para_revision y aún no marcado
        def _domain_validos():
            d = [
                ("estado_ventas_id", "in", ["sin_revisar", "para_revision"]),
                ("check_ingreso", "=", False),
            ]
            return d

        def _pendientes_count():
            d = _domain_validos()
            t = time.time()
            try:
                c = Sat.search_count(d)
                _logger.info("[CHECKIN][COUNT] domain=%s -> %s (%.1fms)", d, c, (time.time() - t) * 1000)
                return c
            except Exception as e:
                _logger.exception("[CHECKIN][COUNT][ERR] domain=%s err=%s", d, e)
                raise

        def _serialize_record(record):
            ingreso_fuente_display = ""
            if "ingreso_fuente" in record._fields and record._fields["ingreso_fuente"].selection:
                ingreso_fuente_selection = dict(record._fields["ingreso_fuente"].selection)
                ingreso_fuente_display = ingreso_fuente_selection.get(record.ingreso_fuente, "")

            data = {
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
            return data

        # ✅ NUEVA FUNCIÓN: Búsqueda inteligente por últimos 4 dígitos
        def _search_by_last_digits(digits):
            """
            Busca equipos donde serie_id termine con los dígitos especificados.
            Usa SQL directo para mayor eficiencia con RIGHT() o similar.
            """
            if not digits:
                return Sat.browse()
            
            # Validar que sean solo dígitos
            if not digits.isdigit():
                _logger.warning("[CHECKIN][SEARCH] digits not numeric: %s", digits)
                return Sat.browse()
            
            domain_base = _domain_validos()
            
            # Opción 1: PostgreSQL con RIGHT() - más eficiente
            try:
                query = """
                    SELECT id 
                    FROM sat_sat 
                    WHERE RIGHT(serie_id, %s) = %s
                      AND estado_ventas_id IN ('sin_revisar', 'para_revision')
                      AND (check_ingreso IS NULL OR check_ingreso = FALSE)
                    ORDER BY write_date DESC, id DESC
                    LIMIT 50
                """
                request.env.cr.execute(query, (len(digits), digits))
                ids = [row[0] for row in request.env.cr.fetchall()]
                
                _logger.info(
                    "[CHECKIN][SEARCH][SQL] RIGHT(serie_id,%s)=%s found=%s ids=%s",
                    len(digits), digits, len(ids), ids[:10]
                )
                
                return Sat.browse(ids)
                
            except Exception as e:
                _logger.warning("[CHECKIN][SEARCH][SQL] error: %s, fallback to domain", e)
                
                # Opción 2: Fallback con domain LIKE (menos preciso pero funciona)
                # Busca series que contengan los dígitos
                domain = domain_base + [("serie_id", "like", "%%%s" % digits)]
                records = Sat.search(domain, limit=50)
                
                # Filtrar manualmente por últimos N dígitos
                filtered = Sat.browse()
                for rec in records:
                    serie = (rec.serie_id or "").strip()
                    if serie and serie.endswith(digits):
                        filtered |= rec
                
                _logger.info(
                    "[CHECKIN][SEARCH][FALLBACK] digits=%s found=%s filtered=%s",
                    digits, len(records), len(filtered)
                )
                
                return filtered

        try:
            # ===== COUNT (solo contador) =====
            if action == "count":
                _logger.info("[CHECKIN][ACTION] count")
                c = _pendientes_count()
                dt = (time.time() - t0) * 1000
                _logger.info("[CHECKIN][OUT] action=count ok=True pendientes_count=%s (%.1fms)", c, dt)
                return _json_response(
                    {"ok": True, "code": "count_ok", "pendientes_count": c},
                    status=200,
                )

            # ===== LIST PENDING (lista ligera: modelo + serie) =====
            if action == "list_pending":
                _logger.info("[CHECKIN][ACTION] list_pending")

                try:
                    limit = int(payload.get("limit") or 200)
                except Exception:
                    limit = 200
                try:
                    offset = int(payload.get("offset") or 0)
                except Exception:
                    offset = 0

                order = payload.get("order") or "write_date desc, id desc"

                d = _domain_validos()
                _logger.info("[CHECKIN][LIST] domain=%s limit=%s offset=%s order=%s", d, limit, offset, order)

                t = time.time()
                rows = Sat.search_read(
                    d,
                    fields=["serie_id", "name"],
                    limit=limit,
                    offset=offset,
                    order=order,
                )
                _logger.info("[CHECKIN][LIST] search_read rows=%s (%.1fms)", len(rows), (time.time() - t) * 1000)

                items = []
                for r in rows:
                    name_val = r.get("name")
                    # Many2one en search_read viene como [id, display_name]
                    modelo = name_val[1] if isinstance(name_val, (list, tuple)) and len(name_val) >= 2 else (name_val or "")
                    items.append(
                        {
                            "id": r.get("id"),
                            "serie": r.get("serie_id") or "",
                            "modelo": modelo or "",
                        }
                    )

                c = _pendientes_count()
                dt = (time.time() - t0) * 1000
                _logger.info(
                    "[CHECKIN][OUT] action=list_pending ok=True pendientes_count=%s items=%s limit=%s offset=%s (%.1fms)",
                    c, len(items), limit, offset, dt
                )

                return _json_response(
                    {
                        "ok": True,
                        "code": "list_pending_ok",
                        "pendientes_count": c,
                        "count": len(items),
                        "limit": limit,
                        "offset": offset,
                        "items": items,
                    },
                    status=200,
                )

            # ===== Para lookup/confirm exigimos serie =====
            if not serial:
                _logger.warning("[CHECKIN][VALIDATION] missing_serial action=%s payload=%s", action, payload)
                return _json_response(
                    {"ok": False, "code": "missing_serial", "message": "No se recibió número de serie."},
                    status=400,
                )

            # ===== LOOKUP =====
            if action == "lookup":
                # ✅ LÓGICA MEJORADA: detectar si son 1-4 dígitos numéricos
                is_numeric_short = serial.isdigit() and 1 <= len(serial) <= 4
                is_partial = (search_mode == "partial") or is_numeric_short
                
                _logger.info(
                    "[CHECKIN][ACTION] lookup serial=%s len=%s is_numeric=%s is_numeric_short=%s is_partial=%s",
                    serial, len(serial), serial.isdigit(), is_numeric_short, is_partial
                )

                if is_partial:
                    # ✅ Usar búsqueda por últimos N dígitos
                    t = time.time()
                    records = _search_by_last_digits(serial)
                    _logger.info(
                        "[CHECKIN][LOOKUP][PARTIAL] serial=%s (last %s digits) found=%s (%.1fms)",
                        serial, len(serial), len(records), (time.time() - t) * 1000
                    )

                    if not records:
                        c = _pendientes_count()
                        dt = (time.time() - t0) * 1000
                        _logger.info("[CHECKIN][OUT] lookup_partial not_found pendientes_count=%s (%.1fms)", c, dt)
                        return _json_response(
                            {
                                "ok": False,
                                "code": "serial_not_found",
                                "message": f"No se encontraron equipos pendientes que terminen con '{serial}'.",
                                "serial": serial,
                                "raw_value": raw_value,
                                "source": source,
                                "search_mode": "partial",
                                "pendientes_count": c,
                            },
                            status=200,
                        )

                    c = _pendientes_count()
                    dt = (time.time() - t0) * 1000
                    _logger.info("[CHECKIN][OUT] lookup_partial ok count=%s pendientes_count=%s (%.1fms)", len(records), c, dt)
                    return _json_response(
                        {
                            "ok": True,
                            "code": "lookup_partial_ok",
                            "message": f"Equipos pendientes encontrados (terminan con '{serial}').",
                            "serial": serial,
                            "raw_value": raw_value,
                            "source": source,
                            "search_mode": "partial",
                            "pendientes_count": c,
                            "count": len(records),
                            "records": [_serialize_record(r) for r in records],
                        },
                        status=200,
                    )

                # ✅ BÚSQUEDA EXACTA (serie completa)
                domain = _domain_validos() + [("serie_id", "=", serial)]
                _logger.info("[CHECKIN][LOOKUP][EXACT] domain=%s", domain)

                t = time.time()
                record = Sat.search(domain, limit=1)
                _logger.info(
                    "[CHECKIN][LOOKUP][EXACT] serial=%s found=%s id=%s (%.1fms)",
                    serial, bool(record), record.id if record else None, (time.time() - t) * 1000
                )

                if not record:
                    c = _pendientes_count()
                    dt = (time.time() - t0) * 1000
                    _logger.info("[CHECKIN][OUT] lookup_exact not_found pendientes_count=%s (%.1fms)", c, dt)
                    return _json_response(
                        {
                            "ok": False,
                            "code": "serial_not_found",
                            "message": "Serie no encontrada (o ya revisada / ya marcada).",
                            "serial": serial,
                            "raw_value": raw_value,
                            "source": source,
                            "pendientes_count": c,
                        },
                        status=200,
                    )

                c = _pendientes_count()
                dt = (time.time() - t0) * 1000
                _logger.info("[CHECKIN][OUT] lookup_exact ok id=%s pendientes_count=%s (%.1fms)", record.id, c, dt)
                return _json_response(
                    {
                        "ok": True,
                        "code": "lookup_ok",
                        "message": "Serie encontrada (pendiente).",
                        "serial": serial,
                        "raw_value": raw_value,
                        "source": source,
                        "pendientes_count": c,
                        "record": _serialize_record(record),
                    },
                    status=200,
                )

            # ===== CONFIRM =====
            if action == "confirm":
                _logger.info("[CHECKIN][ACTION] confirm")

                domain = _domain_validos() + [("serie_id", "=", serial)]
                _logger.info("[CHECKIN][CONFIRM] domain=%s", domain)

                t = time.time()
                record = Sat.search(domain, limit=1)
                _logger.info(
                    "[CHECKIN][CONFIRM] serial=%s found=%s id=%s (%.1fms)",
                    serial, bool(record), record.id if record else None, (time.time() - t) * 1000
                )

                if not record:
                    c = _pendientes_count()
                    dt = (time.time() - t0) * 1000
                    _logger.info("[CHECKIN][OUT] confirm not_found pendientes_count=%s (%.1fms)", c, dt)
                    return _json_response(
                        {
                            "ok": False,
                            "code": "serial_not_found",
                            "message": "Serie no encontrada para confirmar (o ya revisada / ya marcada).",
                            "serial": serial,
                            "raw_value": raw_value,
                            "source": source,
                            "pendientes_count": c,
                        },
                        status=200,
                    )

                status_flag = (payload.get("status") or "ok").strip().lower()
                observation = (payload.get("observation") or "").strip()

                _logger.info(
                    "[CHECKIN][CONFIRM][INPUT] status_flag=%s observation_len=%s",
                    status_flag, len(observation or "")
                )

                vals = {
                    "check_ingreso": True,
                    "ingreso_fecha": fields.Datetime.now(),
                }

                if "ingreso_fuente" in record._fields and source in ("qr", "ocr", "manual"):
                    vals["ingreso_fuente"] = source

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

                t = time.time()
                record.write(vals)
                _logger.info("[CHECKIN][CONFIRM][WRITE] done (%.1fms)", (time.time() - t) * 1000)

                record2 = Sat.browse(record.id)
                _logger.info("[CHECKIN][CONFIRM][VERIFY] id=%s check_ingreso=%s", record2.id, bool(record2.check_ingreso))

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

                c = _pendientes_count()
                dt = (time.time() - t0) * 1000
                _logger.info("[CHECKIN][OUT] confirm ok id=%s pendientes_count=%s (%.1fms)", record2.id, c, dt)
                return _json_response(
                    {
                        "ok": True,
                        "code": "confirm_ok",
                        "message": "Check de ingreso registrado correctamente.",
                        "serial": serial,
                        "raw_value": raw_value,
                        "source": source,
                        "pendientes_count": c,
                        "record": _serialize_record(record2),
                    },
                    status=200,
                )

            # ===== invalid action =====
            _logger.warning("[CHECKIN][VALIDATION] invalid_action=%s payload=%s", action, payload)
            return _json_response(
                {
                    "ok": False,
                    "code": "invalid_action",
                    "message": "Acción no soportada. Usa 'lookup', 'confirm', 'count' o 'list_pending'.",
                },
                status=400,
            )

        except Exception as e:
            dt = (time.time() - t0) * 1000
            _logger.exception("[CHECKIN][FATAL] (%.1fms) error=%s payload=%s", dt, e, payload)
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