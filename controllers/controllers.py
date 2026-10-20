# -*- coding: utf-8 -*-
"""Controladores SAT con trazabilidad operacional para Odoo 19."""
import base64
import json
import logging
import time
import uuid

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _trace():
    return uuid.uuid4().hex[:10]


def _elapsed(start):
    return round((time.monotonic() - start) * 1000, 2)


def _request_info():
    """Información básica del HTTP request, sin parámetros ni datos personales."""
    try:
        req = request.httprequest
        return 'method=%s path=%s' % (req.method, req.path)
    except Exception:
        return 'request=unavailable'


class AlquilerQRController(http.Controller):

    @http.route('/api/escanear_qr', auth='public', type='http', methods=['GET'], website=True)
    def escanear_qr(self, id_registro=None):
        trace = _trace()
        start = time.monotonic()
        _logger.info('[SAT-QR][%s] INICIO %s id_registro=%s', trace, _request_info(), id_registro)
        if not id_registro or not str(id_registro).isdigit():
            _logger.warning('[SAT-QR][%s] REDIRECT /pagina_error razon=id_registro_invalido duracion_ms=%s', trace, _elapsed(start))
            return request.redirect('/pagina_error')

        try:
            registro = request.env['alquiler'].sudo().search(
                [('id', '=', int(id_registro))], limit=1
            )
            if not registro:
                _logger.warning('[SAT-QR][%s] REDIRECT /pagina_error razon=alquiler_inexistente alquiler_id=%s duracion_ms=%s', trace, id_registro, _elapsed(start))
                return request.redirect('/pagina_error')

            datos_registro = {
                'id': registro.id,
                'modelo_maquina': registro.name.name,
                'serie': registro.serie,
                'ubicacion_instlacion': registro.ubicacion_instalacion,
                'cliente': registro.cliente_id.name,
            }
            _logger.info('[SAT-QR][%s] RENDER template=sat.pagina_con_opciones alquiler_id=%s duracion_ms=%s', trace, registro.id, _elapsed(start))
            return request.render('sat.pagina_con_opciones', {'datos_registro': datos_registro})
        except Exception:
            _logger.exception('[SAT-QR][%s] ERROR alquiler_id=%s duracion_ms=%s', trace, id_registro, _elapsed(start))
            raise


class PublicTicketController(http.Controller):
    """Formulario público de incidencias: GET y POST en una ruta."""

    @http.route(
        '/ticket/reportar_incidencia',
        type='http', auth='public', methods=['GET', 'POST'], website=True,
    )
    def reportar_incidencia(self, **kwargs):
        trace = _trace()
        start = time.monotonic()
        method = request.httprequest.method
        _logger.info(
            '[TICKET-PORTAL][%s] ENTRADA_ROUTE %s db=%s user_id=%s parametros=%s archivos=%s',
            trace, _request_info(), request.db, request.env.user.id,
            sorted(kwargs.keys()), sorted(request.httprequest.files.keys()),
        )
        try:
            if method == 'POST':
                _logger.info('[TICKET-PORTAL][%s] DISPATCH_POST', trace)
                result = self.submit_reportar_incidencia(_trace_id=trace, **kwargs)
            else:
                _logger.info('[TICKET-PORTAL][%s] DISPATCH_GET', trace)
                result = self.display_reportar_incidencia(_trace_id=trace, **kwargs)
            _logger.info('[TICKET-PORTAL][%s] SALIDA_ROUTE method=%s duracion_ms=%s', trace, method, _elapsed(start))
            return result
        except Exception:
            _logger.exception('[TICKET-PORTAL][%s] ERROR_NO_CONTROLADO_ROUTE method=%s duracion_ms=%s', trace, method, _elapsed(start))
            raise

    def display_reportar_incidencia(self, _trace_id=None, **kw):
        trace = _trace_id or _trace()
        start = time.monotonic()
        id_registro = kw.get('id_registro')
        user_name = kw.get('user_name')
        phone_number = kw.get('phone_number')
        _logger.info('[TICKET-PORTAL][%s] GET_VALIDACION id_registro=%s whatsapp_context=%s', trace, id_registro, bool(user_name or phone_number))

        if not id_registro or not str(id_registro).isdigit():
            _logger.warning('[TICKET-PORTAL][%s] GET_REDIRECT /pagina_error razon=id_registro_invalido duracion_ms=%s', trace, _elapsed(start))
            return request.redirect('/pagina_error')

        registro = request.env['alquiler'].sudo().search(
            [('id', '=', int(id_registro))], limit=1
        )
        if not registro:
            _logger.warning('[TICKET-PORTAL][%s] GET_REDIRECT /pagina_error razon=alquiler_inexistente id=%s duracion_ms=%s', trace, id_registro, _elapsed(start))
            return request.redirect('/pagina_error')

        is_whatsapp = bool(user_name or phone_number)
        is_logged_user = bool(request.env.user and not request.env.user._is_public())
        is_qr_scan = not is_whatsapp and not is_logged_user

        values = {
            'partner_id': registro.cliente_id.id if registro.cliente_id else '',
            'direccion': registro.direccion or '',
            'correo': registro.correo_ or '',
            'product_id': registro.id,
            'is_qr_scan': is_qr_scan,
        }

        if is_whatsapp:
            values.update({
                'contacto_id': user_name or '',
                'celular': phone_number.replace('@c.us', '') if phone_number else '',
            })
        elif is_logged_user:
            partner = request.env.user.partner_id
            values.update({
                'contacto_id': partner.name or '',
                'celular': partner.phone or '',
            })
        else:
            values.update({'contacto_id': '', 'celular': ''})

        _logger.info(
            '[TICKET-PORTAL][%s] GET_RENDER template=sat.reportar_incidencia_form alquiler_id=%s partner_id=%s origen=%s duracion_ms=%s',
            trace, registro.id, values['partner_id'],
            'whatsapp' if is_whatsapp else ('usuario' if is_logged_user else 'qr'), _elapsed(start),
        )
        return request.render('sat.reportar_incidencia_form', values)

    @http.route('/pagina_confirmacion', type='http', auth='public', website=True)
    def pagina_confirmacion(self, **kw):
        trace = _trace()
        start = time.monotonic()
        _logger.info('[TICKET-PORTAL][%s] CONFIRMACION_INICIO %s', trace, _request_info())
        try:
            response = http.Response(template='sat.pagina_confirmacion')
            result = response.render()
            _logger.info('[TICKET-PORTAL][%s] CONFIRMACION_RENDER_OK duracion_ms=%s', trace, _elapsed(start))
            return result
        except Exception:
            _logger.exception('[TICKET-PORTAL][%s] CONFIRMACION_ERROR template=sat.pagina_confirmacion duracion_ms=%s', trace, _elapsed(start))
            raise

    def submit_reportar_incidencia(self, _trace_id=None, **post):
        """Mantiene la creación y WhatsApp existentes con trazabilidad por etapas."""
        trace = _trace_id or _trace()
        start = time.monotonic()
        _logger.info(
            '[TICKET-PORTAL][%s] POST_INICIO alquiler_id=%s partner_id=%s campos=%s',
            trace, post.get('product_id'), post.get('partner_id'), sorted(post.keys()),
        )
        try:
            file_base64 = None
            if 'problem_photo' in request.httprequest.files:
                file = request.httprequest.files['problem_photo']
                _logger.info(
                    '[TICKET-PORTAL][%s] POST_ADJUNTO_PRESENTE filename_extension=%s mimetype=%s',
                    trace, (file.filename or '').rsplit('.', 1)[-1].lower() if '.' in (file.filename or '') else '',
                    getattr(file, 'mimetype', None),
                )
                raw_file = file.read()
                _logger.info('[TICKET-PORTAL][%s] POST_ADJUNTO_LEIDO bytes=%s', trace, len(raw_file))
                file_base64 = base64.b64encode(raw_file).decode('utf-8')
            else:
                _logger.info('[TICKET-PORTAL][%s] POST_SIN_ADJUNTO', trace)

            ticket_vals = {
                'partner_id': int(post.get('partner_id')) if post.get('partner_id') else False,
                'direccion_id_r': post.get('direccion'),
                'reporter_name': post.get('reporter_name'),
                'reporter_phone': post.get('reporter_phone'),
                'corre_id_r': post.get('correo'),
                'product_alquiler': int(post.get('product_id')) if post.get('product_id') else False,
                'description': post.get('description'),
                'problem_photo': file_base64,
            }
            _logger.info(
                '[TICKET-PORTAL][%s] POST_VALS_PREPARADOS modelo=ticket.alquiler campos=%s alquiler_id=%s partner_id=%s descripcion_presente=%s foto_presente=%s',
                trace, sorted(ticket_vals.keys()), ticket_vals['product_alquiler'],
                ticket_vals['partner_id'], bool(ticket_vals['description']), bool(file_base64),
            )
            _logger.info('[TICKET-PORTAL][%s] POST_CREATE_INICIO modelo=ticket.alquiler', trace)
            ticket = request.env['ticket.alquiler'].sudo().create(ticket_vals)
            _logger.info(
                '[TICKET-PORTAL][%s] POST_CREATE_OK ticket_id=%s alquiler_id=%s duracion_ms=%s',
                trace, ticket.id, ticket_vals['product_alquiler'], _elapsed(start),
            )
        except Exception:
            _logger.exception(
                '[TICKET-PORTAL][%s] POST_CREATE_ERROR alquiler_id=%s duracion_ms=%s',
                trace, post.get('product_id'), _elapsed(start),
            )
            # Se conserva la plantilla de error. Evitar exponer detalles internos al público.
            try:
                _logger.info('[TICKET-PORTAL][%s] POST_ERROR_RENDER template=sat.error_page', trace)
                return request.render('sat.error_page', {
                    'error': 'No se pudo registrar el reporte. Contacte a soporte técnico.',
                })
            except Exception:
                _logger.exception('[TICKET-PORTAL][%s] POST_ERROR_RENDER_FALLO', trace)
                raise

        try:
            _logger.info('[TICKET-PORTAL][%s] POST_WHATSAPP_INICIO ticket_id=%s', trace, ticket.id)
            ticket.enviar_mensaje_whatsapp_reporter()
            _logger.info('[TICKET-PORTAL][%s] POST_WHATSAPP_OK ticket_id=%s', trace, ticket.id)
        except Exception:
            _logger.exception('[TICKET-PORTAL][%s] POST_WHATSAPP_ERROR ticket_id=%s ticket_ya_creado=True', trace, ticket.id)

        _logger.info('[TICKET-PORTAL][%s] POST_REDIRECT destino=/pagina_confirmacion ticket_id=%s duracion_ms=%s', trace, ticket.id, _elapsed(start))
        return request.redirect('/pagina_confirmacion')


class RepuestosAlquilerController(http.Controller):

    @http.route('/alquiler/repuestos/<int:id_alquiler>', type='http', auth='user', website=True)
    def listar_repuestos(self, id_alquiler, search='', **kw):
        trace = _trace()
        start = time.monotonic()
        _logger.info('[SAT-REPUESTOS][%s] LISTADO_INICIO alquiler_id=%s busqueda=%s ajax=%s', trace, id_alquiler, bool(search), request.httprequest.headers.get('X-Requested-With') == 'XMLHttpRequest')
        try:
            domain = [('modelo_id', '=', id_alquiler)]
            if search:
                domain.append(('name', 'ilike', search))

            repuestos = request.env['repuestos.alquiler'].sudo().search(
                domain, order='create_date DESC'
            )
            _logger.info('[SAT-REPUESTOS][%s] LISTADO_CONSULTA_OK alquiler_id=%s cantidad=%s', trace, id_alquiler, len(repuestos))
            if request.httprequest.headers.get('X-Requested-With') == 'XMLHttpRequest':
                repuestos_data = [{
                    'fecha': repuesto.create_date.strftime('%Y-%m-%d') if repuesto.create_date else '',
                    'pedido': repuesto.referencia_reparacion_id,
                    'descripcion': repuesto.name,
                    'cantidad': repuesto.cantidad,
                    'contometro_ultimo': repuesto.contometro_ultimo,
                    'contometro_actual': repuesto.contometro_actual,
                    'rendimiento': repuesto.rendimiento,
                    'solicitante': repuesto.solicitante_id,
                    'serie': repuesto.serie_id,
                } for repuesto in repuestos]
                _logger.info('[SAT-REPUESTOS][%s] LISTADO_AJAX_RESPUESTA registros=%s duracion_ms=%s', trace, len(repuestos_data), _elapsed(start))
                return request.make_response(
                    json.dumps(repuestos_data),
                    headers={'Content-Type': 'application/json'},
                )

            _logger.info('[SAT-REPUESTOS][%s] LISTADO_RENDER alquiler_id=%s duracion_ms=%s', trace, id_alquiler, _elapsed(start))
            return request.render('sat.repuestos_alquiler_list', {
                'repuestos': repuestos,
                'alquiler': request.env['alquiler'].sudo().browse(id_alquiler),
            })
        except Exception:
            _logger.exception('[SAT-REPUESTOS][%s] LISTADO_ERROR alquiler_id=%s', trace, id_alquiler)
            raise

    @http.route('/partes/reponer/<string:token>', type='http', auth='public', website=True, csrf=False)
    def reponer_parte_publico(self, token, **kwargs):
        trace = _trace()
        start = time.monotonic()
        _logger.info('[SAT-PARTES][%s] REPOSICION_PUBLICA_INICIO token_presente=%s', trace, bool(token))
        try:
            linea = request.env['solicitud.partes.linea'].sudo().search([
                ('access_token_linea', '=', token),
                ('estado', '=', 'retirado'),
            ], limit=1)
            if not linea:
                _logger.warning('[SAT-PARTES][%s] REPOSICION_PUBLICA_NO_ENCONTRADA duracion_ms=%s', trace, _elapsed(start))
                return request.render('sat.partes_error_template_alquiler', {
                    'error_message': 'Parte no encontrada o ya fue repuesta',
                })
            _logger.info('[SAT-PARTES][%s] REPOSICION_PUBLICA_RENDER linea_id=%s duracion_ms=%s', trace, linea.id, _elapsed(start))
            return request.render('sat.partes_reposicion_publica_template', {
                'linea': linea, 'token': token,
            })
        except Exception:
            _logger.exception('[SAT-PARTES][%s] REPOSICION_PUBLICA_ERROR duracion_ms=%s', trace, _elapsed(start))
            return request.render('sat.partes_error_template_alquiler', {
                'error_message': 'Error al cargar el formulario',
            })

    @http.route('/partes/reponer/submit', type='http', auth='public', website=True, methods=['POST'], csrf=False)
    def reponer_parte_submit(self, token, condicion, foto, observaciones='', **kwargs):
        trace = _trace()
        start = time.monotonic()
        _logger.info('[SAT-PARTES][%s] REPOSICION_SUBMIT_INICIO token_presente=%s foto_presente=%s observaciones_presentes=%s', trace, bool(token), bool(foto), bool(observaciones))
        try:
            linea = request.env['solicitud.partes.linea'].sudo().search([
                ('access_token_linea', '=', token),
                ('estado', '=', 'retirado'),
            ], limit=1)
            if not linea:
                _logger.warning('[SAT-PARTES][%s] REPOSICION_SUBMIT_NO_ENCONTRADA', trace)
                return request.render('sat.partes_error_template_alquiler', {
                    'error_message': 'Parte no encontrada',
                })
            if not foto or not hasattr(foto, 'read'):
                _logger.warning('[SAT-PARTES][%s] REPOSICION_SUBMIT_SIN_FOTO linea_id=%s', trace, linea.id)
                return request.render('sat.partes_error_template_alquiler', {
                    'error_message': 'Debe adjuntar una foto',
                })
            foto_data = base64.b64encode(foto.read())
            foto_filename = foto.filename if hasattr(foto, 'filename') else 'reposicion.jpg'
            _logger.info('[SAT-PARTES][%s] REPOSICION_CONFIRMAR_INICIO linea_id=%s bytes_base64=%s', trace, linea.id, len(foto_data))
            linea._confirmar_reposicion(condicion, foto_data, foto_filename, observaciones)
            _logger.info('[SAT-PARTES][%s] REPOSICION_CONFIRMAR_OK linea_id=%s duracion_ms=%s', trace, linea.id, _elapsed(start))
            return request.render('sat.partes_reposicion_exitosa_template', {
                'linea': linea,
                'message': f'Reposición de "{linea.parte}" confirmada exitosamente',
            })
        except Exception as exc:
            _logger.exception('[SAT-PARTES][%s] REPOSICION_SUBMIT_ERROR duracion_ms=%s', trace, _elapsed(start))
            return request.render('sat.partes_error_template_alquiler', {
                'error_message': f'Error al procesar: {str(exc)}',
            })


class MiModeloOnboardingController(http.Controller):

    @http.route('/sat/onboarding', type='http', auth='user', website=True)
    def render_onboarding_text(self, **kwargs):
        trace = _trace()
        _logger.info('[SAT-ONBOARDING][%s] RENDER_INICIO %s user_id=%s', trace, _request_info(), request.env.user.id)
        try:
            result = request.render('sat.onboarding_text_template', {})
            _logger.info('[SAT-ONBOARDING][%s] RENDER_OK', trace)
            return result
        except Exception:
            _logger.exception('[SAT-ONBOARDING][%s] RENDER_ERROR', trace)
            raise
