# sat/controllers/sat_api.py
# -*- coding: utf-8 -*-

from odoo import http, fields
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class SatApiController(http.Controller):
    """
    API JSON para check de ingreso de máquinas.

    Flujo:
    1) LOOKUP (solo validar serie y devolver datos)
       POST /sat/api/checkin
       {
         "serial": "ABC123",
         "source": "qr" | "ocr",
         "raw_value": "texto completo leído",
         "action": "lookup"
       }

    2) CONFIRM (guardar resultado de ingreso)
       POST /sat/api/checkin
       {
         "serial": "ABC123",
         "source": "qr" | "ocr",
         "raw_value": "texto completo leído",
         "action": "confirm",
         "status": "ok" | "obs",
         "observation": "texto libre (opcional si status=ok, recomendado si status=obs)"
       }
    """

    @http.route('/sat/api/checkin', type='json', auth='public', methods=['POST'], csrf=False)
    def sat_checkin(self, **kw):
        payload = request.jsonrequest or {}

        serial = (payload.get('serial') or '').strip()
        source = (payload.get('source') or 'unknown').strip()
        raw_value = (payload.get('raw_value') or serial).strip()
        action = (payload.get('action') or 'lookup').strip().lower()
        status = (payload.get('status') or '').strip().lower()  # ok | obs
        observation = (payload.get('observation') or '').strip()

        if not serial:
            return {
                'ok': False,
                'code': 'missing_serial',
                'message': 'No se recibió número de serie.'
            }

        Sat = request.env['sat.sat'].sudo()
        rec = Sat.search([('serie_id', '=', serial)], limit=1)

        if not rec:
            return {
                'ok': False,
                'code': 'not_found',
                'message': 'Serie no encontrada en el registro de máquinas.',
                'serial': serial,
                'raw_value': raw_value,
            }

        # ----- Datos básicos de la máquina -----
        record_data = {
            'id': rec.id,
            'serie': rec.serie_id,
            'modelo': rec.name.name if rec.name else '',
            'marca': rec.marca or '',
            'tipo_maquina': rec.tipo_maquina or '',
            'tipo': rec.tipo_id or '',  # color / monocromatica
            'contometro': rec.contometro or '',
            'estado_ventas': rec.estado_ventas_id or '',
            'disponibilidad': rec.disponibilidad_id or '',
            'ubicacion': rec.ubicacion_id or '',
        }

        # ====== 1) SOLO CONSULTA (LOOKUP) ======
        if action == 'lookup' or not status:
            return {
                'ok': True,
                'code': 'lookup_ok',
                'message': 'Serie encontrada.',
                'serial': serial,
                'raw_value': raw_value,
                'source': source,
                'record': record_data,
            }

        # ====== 2) CONFIRMACIÓN / REGISTRO DE INGRESO (CONFIRM) ======
        # Validaciones básicas de estado (tú puedes reforzar más lógica aquí)
        if rec.estado_ventas_id == 'entregada':
            return {
                'ok': False,
                'code': 'already_delivered',
                'message': 'La máquina ya está marcada como entregada. No se puede registrar ingreso.',
                'serial': serial,
                'record': record_data,
            }

        # Fecha/hora contextualizada según zona horaria de la compañía / usuario
        # (si quieres forzar Lima, puedes usar pytz como ya haces en el modelo)
        dt_now = fields.Datetime.now()
        dt_str = fields.Datetime.to_string(dt_now)

        # Armar texto para el chatter
        # status: ok | obs
        if status == 'ok':
            resumen = "Check de ingreso: OK"
        elif status == 'obs':
            resumen = "Check de ingreso: con observación"
        else:
            resumen = "Check de ingreso"

        detalle = f"""
<b>{resumen}</b><br/>
- Fuente: {source or '-'}<br/>
- Valor leído: {raw_value or '-'}<br/>
- Serie: {serial}<br/>
- Fecha registro: {dt_str}
"""
        if observation:
            detalle += f"<br/><b>Observación:</b> {observation}"

        # Registrar en chatter
        rec.message_post(
            body=detalle,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

        # Si quieres, guardar la observación en el campo descripcion
        # (solo si hay observation y status = 'obs')
        if status == 'obs' and observation:
            try:
                rec.write({
                    'descripcion': (rec.descripcion or '') + "\n[Check ingreso] " + observation,
                    'activador': 'si',  # para que se pinte el icono rojo
                })
            except Exception as e:
                _logger.error("Error guardando observación de ingreso en descripcion: %s", e)

        return {
            'ok': True,
            'code': 'confirm_ok',
            'message': 'Check de ingreso registrado correctamente.',
            'serial': serial,
            'raw_value': raw_value,
            'source': source,
            'status': status,
            'observation': observation,
            'record': record_data,
        }
