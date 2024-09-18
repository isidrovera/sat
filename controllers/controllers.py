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

class TonerRequestController(http.Controller):

    def clean_phone_number(self, phone):
        """Limpia el número de teléfono eliminando el sufijo '@c.us' y agregando el prefijo '51' si es necesario."""
        if phone:
            phone = phone.replace('@c.us', '')  # Eliminar el sufijo '@c.us'
            phone = ''.join(phone.split())  # Eliminar cualquier espacio en blanco
            if not phone.startswith('51'):
                phone = '51' + phone  # Agregar el prefijo '51' si no está presente
        return phone

    @http.route('/toner/solicitar_toner', type='http', auth="public", methods=['GET'], website=True)
    def display_toner_request_form(self, **kw):
        try:
            id_registro = kw.get('id_registro')
            user_name = kw.get('user_name')
            phone_number = kw.get('phone_number')

            _logger.info(f"Solicitud de formulario de tóner recibida. id_registro={id_registro}, user_name={user_name}, phone_number={phone_number}")

            registro = request.env['alquiler'].sudo().search([('id', '=', int(id_registro))], limit=1)
            if not registro:
                _logger.error(f"No se encontró registro con id {id_registro}")
                return request.redirect('/pagina_error')

            # Limpiar y agregar el prefijo '51' si no está
            if phone_number:
                phone_number = self.clean_phone_number(phone_number)
            else:
                # Si el acceso es por QR, phone_number será vacío y el usuario debe ingresar manualmente
                phone_number = ''

            values = {
                'id_registro': registro.id,
                'cliente': registro.cliente_id.name if registro.cliente_id else "",
                'modelo_maquina': registro.name.name if registro.name else "",
                'serie': registro.serie if registro else "",
                'nombre': user_name or "",  # Puede venir precargado desde WhatsApp
                'celular': phone_number,
                'ubicacion_instalacion': registro.ubicacion_instalacion,
                # Si viene desde WhatsApp, lo normalizamos
                'tipo_maquina_id': registro.tipo_maquina_id
            }

            _logger.info(f"Formulario de tóner preparado con los siguientes valores: {values}")
            return request.render('sat.solicitar_toner_form_template', {'values': values})
        
        except Exception as e:
            _logger.exception(f"Error al mostrar el formulario de solicitud de tóner: {str(e)}")
            return request.redirect('/pagina_error')

    @http.route('/pagina_confirmacion_toner', type='http', auth="public", website=True)
    def pagina_confirmacion(self, **kw):
        try:
            _logger.info("Mostrando la página de confirmación de tóner.")
            return request.render('sat.pagina_confirmacion_toner')
        except Exception as e:
            _logger.exception(f"Error al mostrar la página de confirmación de tóner: {str(e)}")
            return request.redirect('/pagina_error')

    @http.route('/toner/enviar_solicitud', type='http', auth="public", methods=['POST'], website=True)
    def send_toner_request(self, **post):
        try:
            # Recopilar los datos del formulario
            datos_formulario = {
                'cliente': post.get('cliente'),
                'nombre': post.get('nombre'),
                'celular': self.clean_phone_number(post.get('celular')),  # Limpiar número antes de usar
                'modelo_maquina': post.get('modelo_maquina'),
                'serie': post.get('serie'),
                'toner_black': post.get('toner_black'),
                'toner_cyan': post.get('toner_cyan'),
                'toner_yellow': post.get('toner_yellow'),
                'toner_magenta': post.get('toner_magenta'),
                'contometro_black': post.get('contometro_black'),
                'contometro_color': post.get('contometro_color'),
            }

            _logger.info(f"Datos recibidos del formulario de solicitud de tóner: {datos_formulario}")

            # Validar campos obligatorios
            if not all([datos_formulario['cliente'], datos_formulario['nombre'], datos_formulario['celular'], datos_formulario['modelo_maquina'], datos_formulario['serie']]):
                _logger.error("Faltan campos obligatorios en el formulario.")
                return request.redirect('/pagina_error')

            # Generar el mensaje
            mensaje_toner = f"Estimado/a {datos_formulario['nombre']},\n\nSu solicitud de tóner ha sido recibida:\n"
            mensaje_toner += f"Cliente: {datos_formulario['cliente']}\n"
            mensaje_toner += f"Modelo: {datos_formulario['modelo_maquina']}\n"
            mensaje_toner += f"Serie: {datos_formulario['serie']}\n"
           

            #if datos_formulario['contometro_color']:
                #mensaje_toner += f"Contometro Color: {datos_formulario['contometro_color']}\n"

            # Enviar el mensaje de WhatsApp
            self.send_whatsapp_message_toner(datos_formulario['celular'], mensaje_toner)

            # Construir el cuerpo del correo electrónico
            toners = [
                {'name': 'Tóner Black', 'qty': datos_formulario.get('toner_black')},
                {'name': 'Tóner Cyan', 'qty': datos_formulario.get('toner_cyan')},
                {'name': 'Tóner Yellow', 'qty': datos_formulario.get('toner_yellow')},
                {'name': 'Tóner Magenta', 'qty': datos_formulario.get('toner_magenta')},
            ]

            toner_lines = ""
            for toner in toners:
                if toner['qty'] and int(toner['qty']) > 0:
                    toner_lines += f"<tr><td>{toner['name']}</td><td>{toner['qty']}</td></tr>"

            body_html = f"""
            <html>
            <head>
            <style>
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }}
            th {{
                background-color: #f2f2f2;
            }}
            </style>
            </head>
            <body>
            <p>Hola,</p>
            <p>Se ha realizado una solicitud de tóner con los siguientes detalles:</p>
            <ul>
                <li>Cliente: {datos_formulario['cliente']}</li>
                <li>Nombre del Solicitante: {datos_formulario['nombre']}</li>
                <li>Celular del Solicitante: {datos_formulario['celular']}</li>
                <li>Modelo de Máquina: {datos_formulario['modelo_maquina']}</li>
                <li>Serie: {datos_formulario['serie']}</li>
                <li>Contometro Black: {datos_formulario['contometro_black']}</li>
                <li>Contometro Color: {datos_formulario['contometro_color']}</li>
            </ul>
            <p>Los toners solicitados son:</p>
            <table>
            <thead>
                <tr>
                <th>Tipo de Tóner</th>
                <th>Cantidad</th>
                </tr>
            </thead>
            <tbody>
                {toner_lines}
            </tbody>
            </table>
            <p>Por favor, proceda con la preparación y envío del tóner.</p>
            <p>Gracias,</p>
            </body>
            </html>
            """

            # Configurar los valores del correo electrónico
            mail_values = {
                'subject': f"Solicitud de Tóner - {datos_formulario['modelo_maquina']}",
                'body_html': body_html,
                'email_from': 'soporte@andescopiers.com.pe',
                'email_to': 'jamilet.roggero@andescopiers.com.pe',
                'email_cc': 'comercial@andescopiers.com.pe, alquiler@andescopiers.com.pe',
                'mail_server_id': 1,
            }

            _logger.info(f"Enviando correo con los valores: {mail_values}")

            # Crear y enviar el correo electrónico
            mail_id = request.env['mail.mail'].sudo().create(mail_values)
            request.env['mail.mail'].sudo().send([mail_id])

            _logger.info("Correo enviado exitosamente.")

            # Redirigir a la página de confirmación
            return request.redirect('/pagina_confirmacion_toner')
        except Exception as e:
            _logger.exception(f"Error al enviar la solicitud de tóner: {str(e)}")
            return request.redirect('/pagina_error')

    def send_whatsapp_message_toner(self, phone, message):
        """Envia un mensaje de WhatsApp relacionado con la solicitud de tóner."""
        try:
            _logger.debug(f"Enviando mensaje de WhatsApp para tóner a {phone} con contenido: {message}")
            
            url = 'https://whatsapp.copiercompanysac.com/lead'
            data = {
                'phone': phone,
                'message': message
            }
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, json=data)

            _logger.debug(f"Código de estado: {response.status_code}")
            _logger.debug(f"Respuesta de la API: {response.text}")
        except Exception as e:
            _logger.error(f"Error enviando mensaje de WhatsApp para tóner: {str(e)}")

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
        

