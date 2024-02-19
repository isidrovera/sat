from odoo import http
from odoo.http import request
import json
import logging
from datetime import date
import base64
import logging
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
            'cliente': registro.cliente_id.name,
        }
        
        # Redirigir a la página con opciones, pasando los datos_registro como contexto
        return request.render('sat.pagina_con_opciones', {'datos_registro': datos_registro})
    


class PublicTicketController(http.Controller):
    # Ruta GET para mostrar el formulario
    @http.route('/ticket/reportar_incidencia', type='http', auth="public", methods=['GET'], website=True)
    def display_reportar_incidencia(self, **kw):
        id_registro = kw.get('id_registro')
        registro = request.env['alquiler'].sudo().search([('id', '=', int(id_registro))])
        values = {
            'partner_id': registro.cliente_id.id if registro.cliente_id else '',
            'direccion': registro.direccion if registro.direccion else '',
            'contacto_id': registro.contacto_id if registro.contacto_id else '',
            'celular': registro.celular if registro.celular else '',
            'correo': registro.correo_ if registro.correo_ else '',
            'product_id': registro.id,
        }
        return request.render('sat.reportar_incidencia_form', values)

    @http.route('/pagina_confirmacion', type='http', auth="public", website=True)
    def pagina_confirmacion(self, **kw):
        return request.render('sat.pagina_confirmacion')

    # Ruta POST para procesar el formulario
    @http.route('/ticket/reportar_incidencia', type='http', auth="public", methods=['POST'], website=True)
    def submit_reportar_incidencia(self, **post):
        try:
            # Manejo de la carga de archivo
            if 'problem_photo' in post:
                file_storage = post['problem_photo']
                if file_storage:
                    file_content = file_storage.read()
                    file_base64 = base64.b64encode(file_content)
                else:
                    file_base64 = None
            else:
                file_base64 = None

            ticket_vals = {
                'partner_id': int(post.get('partner_id')),
                'direccion_id_r': post.get('direccion'),
                'contacto_id_r': post.get('contacto_id'),
                'celular_id_r': post.get('celular'),
                'corre_id_r': post.get('correo'),
                'product_alquiler': int(post.get('product_id')),
                'description': post.get('description'),
                'reporter_name': post.get('reporter_name'),
                'reporter_phone': post.get('reporter_phone'),
                'problem_photo': file_base64.decode('utf-8') if file_base64 else None,
            }
            request.env['ticket.alquiler'].sudo().create(ticket_vals)
            return request.redirect('/pagina_confirmacion')
        except Exception as e:
            _logger.exception("Failed to create ticket: %s", e)
            return request.render('sat.error_page', {'error': str(e)})
        
        
class TonerRequestController(http.Controller):
    @http.route('/toner/solicitar_toner', type='http', auth="public", methods=['GET'], website=True)
    def display_toner_request_form(self, **kw):
        id_registro = kw.get('id_registro')
        registro = request.env['alquiler'].sudo().search([('id', '=', int(id_registro))])
        if not registro:
            return request.redirect('/pagina_error')

        # Preparar los valores para prellenar el formulario
        values = {
            'id_registro': registro.id,
            'cliente': registro.cliente_id.name,
            'modelo_maquina': registro.name.name,
            'serie': registro.serie,
            # ... puedes agregar más valores si es necesario
        }
        # Renderizar el formulario con los valores
        return request.render('tu_modulo.tu_template_formulario_toner', values)

    @http.route('/toner/enviar_solicitud', type='http', auth="public", methods=['POST'], website=True)
    def send_toner_request(self, **post):
        try:
            # Recopilar los datos del formulario
            datos_formulario = {
                'nombre': post.get('nombre'),
                'celular': post.get('celular'),
                'modelo_maquina': post.get('modelo_maquina'),
                'serie': post.get('serie'),
                'toner_black': post.get('toner_black'),
                'toner_cyan': post.get('toner_cyan'),
                'toner_yellow': post.get('toner_yellow'),
                'toner_magenta': post.get('toner_magenta'),
                'cantidad': post.get('cantidad'),
                # ... otros campos que hayas incluido en tu formulario
            }
            
            # Enviar correo electrónico
            template = request.env.ref('sat.email_template_pedido_toner')
            if template:
                email_values = {
                    'email_to': 'destinatario@ejemplo.com',
                    'subject': 'Solicitud de Toner',
                    # Puedes construir el cuerpo del correo aquí o en la plantilla directamente
                    'body_html': "<p>Se ha realizado una solicitud de tóner con los siguientes detalles:</p>"
                                 "<ul>"
                                 f"<li>Cliente: {datos_formulario['nombre']}</li>"
                                 # ... agregar más detalles
                                 "</ul>",
                }
                template.sudo().send_mail(1, email_values=email_values, force_send=True)

            # Redirigir a la página de confirmación
            return request.redirect('/pagina_confirmacion')
        except Exception as e:
            _logger.exception("Failed to send toner request: %s", e)
            return request.render('sat.tu_template_error', {'error': str(e)})

# Asegúrate de reemplazar 'tu_modulo.tu_template_formulario_toner', 'tu_modulo.plantilla_correo_pedido_toner', y 'tu_modulo.tu_template_error'
# con las rutas correctas de tus templates en Odoo