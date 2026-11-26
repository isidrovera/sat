# -*- coding: utf-8 -*-
import hashlib
import hmac
import logging
from datetime import datetime

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class MaintenanceController(http.Controller):

    def _render_privado(self, template, values):
        response = request.render(template, values)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response

    def _error(self, message):
        return self._render_privado('sat.maintenance_error_template', {
            'error_message': message,
        })

    def _firma_valida(self, alquiler, accion, ciclo, cliente, firma):
        secreto = request.env['ir.config_parameter'].sudo().get_param('database.secret')
        if not secreto or not isinstance(firma, str):
            return False
        if ciclo != str(alquiler.fecha_recurrente) or cliente != str(alquiler.cliente_id.id):
            return False
        mensaje = f'mantenimiento:v1:{accion}:{alquiler.id}:{cliente}:{ciclo}'
        esperada = hmac.new(secreto.encode('utf-8'), mensaje.encode('utf-8'), hashlib.sha256).hexdigest()
        return hmac.compare_digest(esperada, firma)

    def _procesar(self, alquiler_id, accion, ciclo=None, cliente=None, firma=None):
        try:
            with request.env.cr.savepoint():
                alquiler = request.env['alquiler'].sudo().browse(alquiler_id).exists()
                if not alquiler or not self._firma_valida(alquiler, accion, ciclo, cliente, firma):
                    return self._error('El enlace de mantenimiento no es válido o ya no corresponde al ciclo actual.')

                if (not alquiler.control_mantenimiento or alquiler.estado_alquiler_id != 'alquilada'
                        or not alquiler.cliente_id or not alquiler.fecha_recurrente):
                    return self._error('Este equipo ya no tiene un mantenimiento activo.')

                # GET no modifica registros: evita confirmaciones por escáneres de correo.
                if request.httprequest.method == 'GET':
                    etiqueta = 'Confirmar mantenimiento' if accion == 'confirm' else 'Solicitar reprogramación'
                    ruta = 'confirmar' if accion == 'confirm' else 'reprogramar'
                    return self._render_privado('sat.maintenance_action_template', {
                        'action_label': etiqueta,
                        'action_kind': accion,
                        'action_url': f'/mantenimiento/{ruta}/{alquiler.id}',
                        'customer_name': alquiler.cliente_id.name,
                        'visit_date': alquiler.fecha_recurrente,
                        'csrf_token': request.csrf_token(),
                        'ciclo': ciclo,
                        'cliente': cliente,
                        'firma': firma,
                    })

                # Bloquear el grupo en el mismo orden que el modelo integrado.
                equipos = alquiler._equipos_ciclo_cliente()
                for equipo in equipos:
                    request.env.cr.execute('SELECT id FROM alquiler WHERE id = %s FOR UPDATE', (equipo.id,))
                equipos.invalidate_recordset()
                alquiler.invalidate_recordset()
                if not self._firma_valida(alquiler, accion, ciclo, cliente, firma):
                    return self._error('El ciclo de mantenimiento ha cambiado.')
                if alquiler not in equipos or not alquiler.control_mantenimiento or alquiler.estado_alquiler_id != 'alquilada':
                    return self._error('Este equipo ya no tiene un mantenimiento activo.')
                if any(e.cliente_id.id != alquiler.cliente_id.id or str(e.fecha_recurrente) != ciclo or not e.control_mantenimiento or e.estado_alquiler_id != 'alquilada' for e in equipos):
                    return self._error('La programación ha cambiado. Solicite un enlace actualizado.')

                if accion == 'confirm':
                    if any(e.estado_programacion == 'reprogramado' for e in equipos):
                        return self._error('Existe una solicitud de reprogramación pendiente.')
                    if all(e.estado_programacion == 'confirmado' for e in equipos):
                        resultado = True
                    else:
                        # El modelo confirma el ciclo; el planificador crea los tickets.
                        resultado = alquiler._create_maintenance_tickets()
                    if resultado:
                        return self._render_privado('sat.maintenance_confirmation_template', {
                            'message': 'Gracias por confirmar la fecha de mantenimiento. Nuestro equipo coordinará la asignación técnica.',
                            'visit_date': alquiler.fecha_recurrente,
                            'datetime': datetime,
                        })
                else:
                    resultado = all(e.estado_programacion == 'reprogramado' for e in equipos) or alquiler._send_reschedule_request()
                    if resultado:
                        return self._render_privado('sat.maintenance_reschedule_template', {
                            'message': 'Su solicitud de reprogramación ha sido recibida. Nos pondremos en contacto con usted pronto.',
                        })
                raise UserError('No se pudo procesar la solicitud de mantenimiento.')
        except (UserError, ValidationError):
            _logger.warning('Solicitud de mantenimiento rechazada: equipo=%s accion=%s', alquiler_id, accion)
            return self._error('No se pudo procesar la solicitud. Comuníquese con nuestro equipo.')
        except Exception:
            _logger.exception('Error de mantenimiento: equipo=%s accion=%s', alquiler_id, accion)
            return self._error('Ocurrió un error al procesar su solicitud.')

    @http.route('/mantenimiento/confirmar/<int:alquiler_id>', type='http', auth='public', website=True, methods=['GET', 'POST'], csrf=True)
    def confirm_maintenance(self, alquiler_id, ciclo=None, cliente=None, firma=None, **kwargs):
        return self._procesar(alquiler_id, 'confirm', ciclo, cliente, firma)

    @http.route('/mantenimiento/reprogramar/<int:alquiler_id>', type='http', auth='public', website=True, methods=['GET', 'POST'], csrf=True)
    def request_reschedule(self, alquiler_id, ciclo=None, cliente=None, firma=None, **kwargs):
        return self._procesar(alquiler_id, 'reschedule', ciclo, cliente, firma)
