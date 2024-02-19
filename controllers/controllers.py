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
        registro = request.env['alquiler'].sudo().search([('id', '=', int(id_registro))], limit=1)
        if registro:
            values = {
                'id_registro': registro.id,
                'cliente': registro.cliente_id.name if registro.cliente_id else "",
                'modelo_maquina': registro.name.name if registro.name else "",
                'serie': registro.serie if registro else "",
                # ... otros campos según sea necesario
            }
            return request.render('sat.solicitar_toner_form_template', {'values': values})
        else:
            return request.redirect('/pagina_error')
    @http.route('/pagina_confirmacion_toner', type='http', auth="public", website=True)
    def pagina_confirmacion(self, **kw):
        return request.render('sat.pagina_confirmacion_toner')

    @http.route('/toner/enviar_solicitud', type='http', auth="public", methods=['POST'], website=True)
    def send_toner_request(self, **post):
        try:
            # Recopilar los datos del formulario
            datos_formulario = {
                'cliente': post.get('cliente'),
                'nombre': post.get('nombre'),
                'celular': post.get('celular'),
                'modelo_maquina': post.get('modelo_maquina'),
                'serie': post.get('serie'),
                'toner_black': post.get('toner_black'),
                'toner_cyan': post.get('toner_cyan'),
                'toner_yellow': post.get('toner_yellow'),
                'toner_magenta': post.get('toner_magenta'),
                'contometro_black': post.get('contometro_black'),
                'contometro_color': post.get('contometro_color'),
                # ... otros campos que hayas incluido en tu formulario
            }
            
            # Construir el cuerpo del correo electrónico
            toners = [
                {'name': 'Tóner Black', 'qty': datos_formulario.get('toner_black')},
                {'name': 'Tóner Cyan', 'qty': datos_formulario.get('toner_cyan')},
                {'name': 'Tóner Yellow', 'qty': datos_formulario.get('toner_yellow')},
                {'name': 'Tóner Magenta', 'qty': datos_formulario.get('toner_magenta')},
            ]

            toner_lines = ""
            for toner in toners:
                if toner['qty'] and int(toner['qty']) > 0:  # Asegúrate de que la cantidad es un número y es mayor que cero
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
                'subject': "Solicitud de Toner - {0}".format(datos_formulario['modelo_maquina']),
                'body_html': body_html,
                'email_to': 'jamilet.roggero@andescopiers.com.pe',  # Reemplaza por el correo del destinatario real
                'email_cc': 'comercial@andescopiers.com.pe, alquiler@andescopiers.com.pe',  # Agrega aquí la dirección de correo que recibirá la copia
            }


            # Crear y enviar el correo electrónico
            mail_id = request.env['mail.mail'].sudo().create(mail_values)
            request.env['mail.mail'].sudo().send([mail_id])

            # Redirigir a la página de confirmación
            return request.redirect('/pagina_confirmacion_toner')
        except Exception as e:
            _logger.exception("Failed to send toner request: %s", e)
            return request.redirect('/pagina_error')  # Asegúrate de tener una vista de error definida.
        
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