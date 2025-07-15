from odoo import http
from odoo.http import request
import json
import logging
from datetime import date
import base64
import urllib.parse
import logging
import requests
_logger = logging.getLogger(__name__)



class AlquilerQRController(http.Controller):
    @http.route('/api/escanear_qr', auth='public', type='http', methods=['GET'], website=True)
    def escanear_qr(self, id_registro=None):
        if not id_registro:
            return request.redirect('/pagina_error')
        
        registro = request.env['alquiler'].sudo().search([('id', '=', int(id_registro))])
        if not registro:
            return request.redirect('/pagina_error')

        # Aquí se podrían agregar más datos según sea necesario
        datos_registro = {
            'id': registro.id,
            'modelo_maquina': registro.name.name,
            'serie': registro.serie,
            'ubicacion_instlacion': registro.ubicacion_instalacion,
            'cliente': registro.cliente_id.name,
        }
        
        # Redirigir a la página con opciones, pasando los datos_registro como contexto
        return request.render('sat.pagina_con_opciones', {'datos_registro': datos_registro})
    


class PublicTicketController(http.Controller):
    @http.route('/ticket/reportar_incidencia', type='http', auth="public", methods=['GET'], website=True)
    def display_reportar_incidencia(self, **kw):
        id_registro = kw.get('id_registro')
        user_name = kw.get('user_name')
        phone_number = kw.get('phone_number')
        
        registro = request.env['alquiler'].sudo().search([('id', '=', int(id_registro))])
        
        # Determinar si es un escaneo QR o desde WhatsApp
        is_qr_scan = not (user_name or phone_number)
        
        values = {
            'partner_id': registro.cliente_id.id if registro.cliente_id else '',
            'direccion': registro.direccion if registro.direccion else '',
            'correo': registro.correo_ if registro.correo_ else '',
            'product_id': registro.id,
            'is_qr_scan': is_qr_scan,
        }
        
        if not is_qr_scan:
            # Si viene de WhatsApp, prellenamos los campos
            values.update({
                'contacto_id': user_name or '',
                'celular': phone_number.replace('@c.us', '') if phone_number else '',
            })
        else:
            # Si es escaneo QR, dejamos los campos en blanco
            values.update({
                'contacto_id': '',
                'celular': '',
            })
        
        return request.render('sat.reportar_incidencia_form', values)

    @http.route('/pagina_confirmacion', type='http', auth="public", website=True)
    def pagina_confirmacion(self, **kw):
        response = http.Response(template='sat.pagina_confirmacion')
        return response.render()

    @http.route('/ticket/reportar_incidencia', type='http', auth="public", methods=['POST'], website=True)
    def submit_reportar_incidencia(self, **post):
        try:
            # Procesar la foto del problema, si existe
            if 'problem_photo' in request.httprequest.files:
                file = request.httprequest.files['problem_photo']
                file_content = file.read()
                file_base64 = base64.b64encode(file_content).decode('utf-8')
            else:
                file_base64 = None

            # Valores del ticket enviados por el cliente
            ticket_vals = {
                'partner_id': int(post.get('partner_id')),
                'direccion_id_r': post.get('direccion'),
                'reporter_name': post.get('reporter_name'),
                'reporter_phone': post.get('reporter_phone'),
                'corre_id_r': post.get('correo'),
                'product_alquiler': int(post.get('product_id')),
                'description': post.get('description'),
                'problem_photo': file_base64,
            }

            # Crear el ticket en la base de datos
            ticket = request.env['ticket.alquiler'].sudo().create(ticket_vals)
            
            # Llamar a la función para enviar el mensaje de WhatsApp al reportero
            ticket.enviar_mensaje_whatsapp_reporter()

            # Redirigir a la página de confirmación
            return request.redirect('/pagina_confirmacion')
        
        except Exception as e:
            _logger.exception("Failed to create ticket: %s", e)
            return request.render('sat.error_page', {'error': str(e)})



class RepuestosAlquilerController(http.Controller):
    @http.route('/alquiler/repuestos/<int:id_alquiler>', type='http', auth='user', website=True)
    def listar_repuestos(self, id_alquiler, search='', **kw):
        domain = [('modelo_id', '=', id_alquiler)]
        if search:
            domain.append(('name', 'ilike', search))
        repuestos = request.env['repuestos.alquiler'].sudo().search(domain, order='create_date DESC')

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

            return request.make_response(json.dumps(repuestos_data), headers={'Content-Type': 'application/json'})

        # Manejo normal sin AJAX
        return request.render('sat.repuestos_alquiler_list', {
            'repuestos': repuestos,
            'alquiler': request.env['alquiler'].sudo().browse(id_alquiler),
        })
        

class MiModeloOnboardingController(http.Controller):

    @http.route('/sat/onboarding', type='http', auth='user', website=True)
    def render_onboarding_text(self, **kwargs):
        # Solo renderiza el texto simple en el template
        return request.render('sat.onboarding_text_template', {})