# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json
import logging
import base64

_logger = logging.getLogger(__name__)


class AlquilerQRController(http.Controller):

    @http.route('/api/escanear_qr', auth='public', type='http', methods=['GET'], website=True)
    def escanear_qr(self, id_registro=None):
        if not id_registro or not str(id_registro).isdigit():
            return request.redirect('/pagina_error')

        registro = request.env['alquiler'].sudo().search(
            [('id', '=', int(id_registro))], limit=1
        )
        if not registro:
            return request.redirect('/pagina_error')

        datos_registro = {
            'id': registro.id,
            'modelo_maquina': registro.name.name,
            'serie': registro.serie,
            'ubicacion_instlacion': registro.ubicacion_instalacion,
            'cliente': registro.cliente_id.name,
        }
        return request.render('sat.pagina_con_opciones', {'datos_registro': datos_registro})


class PublicTicketController(http.Controller):
    """Formulario público de incidencias: misma ruta para GET y POST."""

    @http.route(
        '/ticket/reportar_incidencia',
        type='http', auth='public', methods=['GET', 'POST'], website=True,
    )
    def reportar_incidencia(self, **kwargs):
        if request.httprequest.method == 'POST':
            return self.submit_reportar_incidencia(**kwargs)
        return self.display_reportar_incidencia(**kwargs)

    def display_reportar_incidencia(self, **kw):
        id_registro = kw.get('id_registro')
        user_name = kw.get('user_name')
        phone_number = kw.get('phone_number')

        if not id_registro or not str(id_registro).isdigit():
            _logger.warning('[TICKET-PORTAL] GET sin id_registro valido; parametros=%s', list(kw))
            return request.redirect('/pagina_error')

        registro = request.env['alquiler'].sudo().search(
            [('id', '=', int(id_registro))], limit=1
        )
        if not registro:
            _logger.warning('[TICKET-PORTAL] GET alquiler inexistente id=%s', id_registro)
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

        _logger.info('[TICKET-PORTAL] GET formulario alquiler=%s', registro.id)
        return request.render('sat.reportar_incidencia_form', values)

    @http.route('/pagina_confirmacion', type='http', auth='public', website=True)
    def pagina_confirmacion(self, **kw):
        response = http.Response(template='sat.pagina_confirmacion')
        return response.render()

    def submit_reportar_incidencia(self, **post):
        """Mantiene los campos del ticket; el WhatsApp no debe ocultar un ticket creado."""
        _logger.info(
            '[TICKET-PORTAL] POST recibido product_id=%s partner_id=%s',
            post.get('product_id'), post.get('partner_id'),
        )
        try:
            file_base64 = None
            if 'problem_photo' in request.httprequest.files:
                file = request.httprequest.files['problem_photo']
                file_base64 = base64.b64encode(file.read()).decode('utf-8')

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
            ticket = request.env['ticket.alquiler'].sudo().create(ticket_vals)
            _logger.info('[TICKET-PORTAL] Ticket creado id=%s alquiler=%s', ticket.id, post.get('product_id'))
        except Exception as exc:
            _logger.exception('[TICKET-PORTAL] Error al crear ticket alquiler=%s', post.get('product_id'))
            return request.render('sat.error_page', {'error': str(exc)})

        try:
            ticket.enviar_mensaje_whatsapp_reporter()
        except Exception:
            _logger.exception(
                '[TICKET-PORTAL] Ticket id=%s creado, pero fallo WhatsApp al reportante', ticket.id
            )

        return request.redirect('/pagina_confirmacion')


class RepuestosAlquilerController(http.Controller):

    @http.route('/alquiler/repuestos/<int:id_alquiler>', type='http', auth='user', website=True)
    def listar_repuestos(self, id_alquiler, search='', **kw):
        domain = [('modelo_id', '=', id_alquiler)]
        if search:
            domain.append(('name', 'ilike', search))

        repuestos = request.env['repuestos.alquiler'].sudo().search(
            domain, order='create_date DESC'
        )
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
            return request.make_response(
                json.dumps(repuestos_data),
                headers={'Content-Type': 'application/json'},
            )

        return request.render('sat.repuestos_alquiler_list', {
            'repuestos': repuestos,
            'alquiler': request.env['alquiler'].sudo().browse(id_alquiler),
        })

    @http.route('/partes/reponer/<string:token>', type='http', auth='public', website=True, csrf=False)
    def reponer_parte_publico(self, token, **kwargs):
        try:
            linea = request.env['solicitud.partes.linea'].sudo().search([
                ('access_token_linea', '=', token),
                ('estado', '=', 'retirado'),
            ], limit=1)
            if not linea:
                return request.render('sat.partes_error_template_alquiler', {
                    'error_message': 'Parte no encontrada o ya fue repuesta',
                })
            return request.render('sat.partes_reposicion_publica_template', {
                'linea': linea, 'token': token,
            })
        except Exception as exc:
            _logger.error('Error en reponer_parte_publico: %s', exc)
            return request.render('sat.partes_error_template_alquiler', {
                'error_message': 'Error al cargar el formulario',
            })

    @http.route('/partes/reponer/submit', type='http', auth='public', website=True, methods=['POST'], csrf=False)
    def reponer_parte_submit(self, token, condicion, foto, observaciones='', **kwargs):
        try:
            linea = request.env['solicitud.partes.linea'].sudo().search([
                ('access_token_linea', '=', token),
                ('estado', '=', 'retirado'),
            ], limit=1)
            if not linea:
                return request.render('sat.partes_error_template_alquiler', {
                    'error_message': 'Parte no encontrada',
                })
            if not foto or not hasattr(foto, 'read'):
                return request.render('sat.partes_error_template_alquiler', {
                    'error_message': 'Debe adjuntar una foto',
                })
            foto_data = base64.b64encode(foto.read())
            foto_filename = foto.filename if hasattr(foto, 'filename') else 'reposicion.jpg'
            linea._confirmar_reposicion(condicion, foto_data, foto_filename, observaciones)
            return request.render('sat.partes_reposicion_exitosa_template', {
                'linea': linea,
                'message': f'Reposición de "{linea.parte}" confirmada exitosamente',
            })
        except Exception as exc:
            _logger.error('Error en reponer_parte_submit: %s', exc)
            return request.render('sat.partes_error_template_alquiler', {
                'error_message': f'Error al procesar: {exc}',
            })


class MiModeloOnboardingController(http.Controller):

    @http.route('/sat/onboarding', type='http', auth='user', website=True)
    def render_onboarding_text(self, **kwargs):
        return request.render('sat.onboarding_text_template', {})
