from odoo import http, fields
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class SatApiController(http.Controller):

    @http.route('/sat/api/checkin', type='json', auth='public', methods=['POST'], csrf=False)
    def sat_checkin(self, **kw):
        payload = request.jsonrequest or {}

        serial = (payload.get('serial') or '').strip()
        source = (payload.get('source') or 'unknown').strip()
        raw_value = (payload.get('raw_value') or serial).strip()
        action = (payload.get('action') or 'lookup').strip().lower()
        status = (payload.get('status') or '').strip().lower()
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

        record_data = {
            'id': rec.id,
            'serie': rec.serie_id,
            'modelo': rec.name.name if rec.name else '',
            'marca': rec.marca or '',
            'tipo_maquina': rec.tipo_maquina or '',
            'tipo': rec.tipo_id or '',
            'contometro': rec.contometro or '',
            'estado_ventas': rec.estado_ventas_id or '',
            'disponibilidad': rec.disponibilidad_id or '',
            'ubicacion': rec.ubicacion_id or '',
        }

        # Solo lookup (consulta)
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

        # --- confirmación (aquí va la lógica de check-in) ---
        dt_now = fields.Datetime.now()
        dt_str = fields.Datetime.to_string(dt_now)

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

        rec.message_post(
            body=detalle,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

        if status == 'obs' and observation:
            try:
                rec.sudo().write({
                    'descripcion': (rec.descripcion or '') + "\n[Check ingreso] " + observation,
                    'activador': 'si',
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
