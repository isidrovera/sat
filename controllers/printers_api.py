# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
import json
import re
import logging

_logger = logging.getLogger(__name__)

# ========= Helpers =========

def _auth_ok(req) -> bool:
    """
    Valida Authorization: Bearer <token> contra ir.config_parameter 'snmp.api.token'
    """
    auth = req.httprequest.headers.get('Authorization', '')
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == 'bearer':
        token = parts[1]
        sys_token = request.env['ir.config_parameter'].sudo().get_param('snmp.api.token')
        return bool(sys_token) and token == sys_token
    return False

_DIGITS_RE = re.compile(r'[^\d]')
def _digits_only(v) -> str:
    """
    Convierte cualquier valor a string y deja solo dígitos (para contómetro).
    """
    if v is None:
        return ''
    return _DIGITS_RE.sub('', str(v))

def _json_response(payload: dict, status: int = 200):
    return http.Response(
        json.dumps(payload, ensure_ascii=False),
        status=status,
        mimetype='application/json'
    )

# ========= Controller =========

class PrintersAPI(http.Controller):

    @http.route('/api/printers/upsert', type='json', auth='public', csrf=False, methods=['POST'])
    def upsert(self, **kwargs):
        """
        Cuerpo esperado (JSON):
        {
          "serial": "XXXXXX",             # requerido
          "model": "Canon iR-ADV C5535",  # opcional pero recomendado
          "brand": "Canon",               # opcional (no se escribe, solo se registra discrepancia)
          "total_counter": 123456,        # requerido
          "ip": "192.168.1.50"            # opcional
        }
        """
        # --- auth ---
        if not _auth_ok(request):
            return _json_response({"ok": False, "error": "unauthorized"}, status=401)

        payload = request.jsonrequest or {}
        serial = (payload.get('serial') or '').strip()
        model_txt = (payload.get('model') or '').strip()
        brand_txt = (payload.get('brand') or '').strip()
        total = payload.get('total_counter')
        ip = (payload.get('ip') or '').strip()

        if not serial:
            return _json_response({"ok": False, "error": "serial es obligatorio"}, status=400)
        if total is None:
            return _json_response({"ok": False, "error": "total_counter es obligatorio"}, status=400)

        Sat = request.env['sat.sat'].sudo()
        Modelo = request.env['modelo.maquina'].sudo()

        # --- localizar máquina por serie ---
        machine = Sat.search([('serie_id', '=', serial)], limit=1)
        if not machine:
            # Política: NO crear. Todo se basa en la serie que debe existir en Odoo.
            return _json_response({"ok": False, "error": f"Serie {serial} no existe en Odoo"}, status=404)

        updated_fields = []
        warnings = []

        # --- contometro (char) como dígitos puros ---
        total_str = _digits_only(total)
        if not total_str:
            return _json_response({"ok": False, "error": "total_counter inválido (debe contener dígitos)"}, status=400)

        if (machine.contometro or '') != total_str:
            try:
                machine.write({'contometro': total_str})
                updated_fields.append('contometro')
            except Exception as e:
                _logger.exception("Error actualizando contometro para serie %s", serial)
                return _json_response({"ok": False, "error": f"no se pudo actualizar contometro: {e}"}, status=500)

        # --- modelo Many2one (machine.name) si difiere del texto recibido ---
        if model_txt:
            try:
                # Si el Many2one ya apunta a un modelo con nombre igual (case-insensitive), no cambiar
                current_name = machine.name and machine.name.name or ''
                if not current_name or current_name.strip().lower() != model_txt.lower():
                    mm = Modelo.search([('name', '=ilike', model_txt)], limit=1)
                    if mm and (not machine.name or machine.name.id != mm.id):
                        machine.write({'name': mm.id})
                        updated_fields.append('name')
                    elif not mm:
                        warnings.append(f"Modelo '{model_txt}' no existe en 'modelo.maquina' (no se cambió).")
            except Exception as e:
                _logger.exception("Error ajustando modelo para serie %s", serial)
                warnings.append(f"No se pudo ajustar modelo: {e}")

        # --- IP si el campo existe ---
        try:
            if ip and 'ip_equipo' in Sat._fields:
                current_ip = getattr(machine, 'ip_equipo', '') or ''
                if current_ip != ip:
                    machine.write({'ip_equipo': ip})
                    updated_fields.append('ip_equipo')
        except Exception as e:
            _logger.exception("Error actualizando IP para serie %s", serial)
            warnings.append(f"No se pudo actualizar IP: {e}")

        # --- marca: solo verificación (no se escribe porque es related) ---
        try:
            if brand_txt:
                current_brand = (machine.marca or '').strip()
                if current_brand and current_brand.lower() != brand_txt.lower():
                    msg = f"Marca recibida '{brand_txt}' difiere de la actual '{current_brand}' para serie {serial}"
                    _logger.info(msg)
                    warnings.append(msg)
        except Exception:
            pass

        return _json_response({
            "ok": True,
            "serie": serial,
            "updated_fields": updated_fields,
            "warnings": warnings
        }, status=200)

    @http.route('/api/printers/health', type='http', auth='public', csrf=False, methods=['GET'])
    def health(self, **kwargs):
        """
        Endpoint simple de salud para monitoreo (no requiere token).
        """
        return _json_response({"status": "ok"})
