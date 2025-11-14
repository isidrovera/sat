# -*- coding: utf-8 -*-
import logging

from odoo import http, fields, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class SatApi(http.Controller):

    @http.route('/sat/api/checkin', type='http', auth='public', methods=['POST'], csrf=False)
    def sat_checkin(self, **kwargs):
        """
        Endpoint usado por el scanner externo.

        Espera JSON como:
        {
          "serial": "2RK07735",
          "source": "qr" | "ocr" | "otro",
          "raw_value": "2RK07735",
          "action": "lookup" | "confirm",
          "status": "ok" | "obs",        # solo si action == "confirm"
          "observation": "texto opcional" # solo si action == "confirm"
        }
        """
        # -------- leer JSON crudo del body --------
        try:
            payload = request.httprequest.get_json(force=True, silent=True) or {}
        except Exception:
            payload = {}

        _logger.info("sat_checkin payload: %s", payload)

        serial = (payload.get('serial') or '').strip()
        source = (payload.get('source') or '').strip().lower() or 'unknown'
        raw_value = (payload.get('raw_value') or '').strip()
        action = (payload.get('action') or 'lookup').strip().lower()
        status = (payload.get('status') or '').strip().lower()
        observation = (payload.get('observation') or '').strip()

        # -------- validaciones básicas --------
        if not serial:
            return request.make_json_response({
                "ok": False,
                "code": "missing_serial",
                "message": _("No se recibió número de serie.")
            })

        Sat = request.env['sat.sat'].sudo()
        rec = Sat.search([('serie_id', '=', serial)], limit=1)

        if not rec:
            return request.make_json_response({
                "ok": False,
                "code": "not_found",
                "message": _("No se encontró equipo con esa serie."),
                "serial": serial,
                "raw_value": raw_value,
                "source": source,
            })

        # -------- helper para armar ficha de respuesta --------
        def _record_data(r):
            return {
                "id": r.id,
                "serie": r.serie_id,
                "modelo": r.name.name if r.name else "",
                "marca": r.marca or "",
                "tipo_maquina": r.tipo_maquina or "",
                "tipo": r.tipo_id or "",
                "contometro": r.contometro or "",
                "estado_ventas": r.estado_ventas_id or "",
                "disponibilidad": r.disponibilidad_id or "",
                "ubicacion": r.ubicacion_id or "",
                "check_ingreso": bool(r.check_ingreso),
                "ingreso_estado": r.ingreso_estado or "",
                "ingreso_fecha": r.ingreso_fecha and fields.Datetime.to_string(r.ingreso_fecha) or "",
                "ingreso_fuente": r.ingreso_fuente or "",
            }

        # -------- sólo consulta (lookup) --------
        if action == 'lookup':
            return request.make_json_response({
                "ok": True,
                "code": "lookup_ok",
                "message": _("Serie encontrada."),
                "serial": serial,
                "raw_value": raw_value,
                "source": source,
                "record": _record_data(rec),
            })

        # -------- confirmación de ingreso (confirm) --------
        if action == 'confirm':
            if status not in ('ok', 'obs'):
                return request.make_json_response({
                    "ok": False,
                    "code": "invalid_status",
                    "message": _("El estado de confirmación debe ser 'ok' o 'obs'."),
                })

            vals = {
                "check_ingreso": True,
                "ingreso_estado": status,
                "ingreso_fecha": fields.Datetime.now(),
            }

            # fuente de ingreso si coincide con alguna conocida
            if source in ('qr', 'ocr', 'manual'):
                vals["ingreso_fuente"] = source

            # si viene observación y status = 'obs', la metemos en descripcion
            if status == 'obs' and observation:
                if rec.descripcion:
                    nueva_desc = "%s\n\nIngreso scanner (%s): %s" % (
                        rec.descripcion,
                        (source or 'scanner').upper(),
                        observation,
                    )
                else:
                    nueva_desc = "Ingreso scanner (%s): %s" % (
                        (source or 'scanner').upper(),
                        observation,
                    )
                vals["descripcion"] = nueva_desc

            rec.write(vals)

            # mensaje para chatter
            msg = _("Ingreso confirmado vía scanner (estado: %s).") % (status.upper(),)
            if status == 'obs' and observation:
                msg += _("<br/>Observación: %s") % observation
            rec.message_post(body=msg)

            return request.make_json_response({
                "ok": True,
                "code": "confirm_ok",
                "message": _("Ingreso registrado correctamente.") if status == 'ok'
                           else _("Ingreso registrado con observación."),
                "serial": serial,
                "raw_value": raw_value,
                "source": source,
                "record": _record_data(rec),
            })

        # -------- acción desconocida --------
        return request.make_json_response({
            "ok": False,
            "code": "invalid_action",
            "message": _("Acción no soportada: %s") % action,
        })
