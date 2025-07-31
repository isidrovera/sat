import json
import logging
import requests
from odoo import http, _
from odoo.http import request
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class TonerRequestController(http.Controller):

    def clean_phone_number(self, phone):
        """Limpia el número de teléfono eliminando el sufijo '@c.us' y agregando el prefijo '51' si es necesario."""
        if phone:
            phone = phone.replace('@c.us', '')  # Eliminar el sufijo '@c.us'
            phone = ''.join(phone.split())  # Eliminar cualquier espacio en blanco
            if not phone.startswith('51'):
                phone = '51' + phone  # Agregar el prefijo '51' si no está presente
        return phone

    def _get_office_mail_server(self):
        """Obtiene el servidor de correo 'office'"""
        try:
            # Buscar el servidor de correo específico por nombre
            mail_server = request.env['ir.mail_server'].sudo().search([
                ('name', '=', 'office')
            ], limit=1)
            
            if mail_server:
                _logger.info(f"Servidor de correo 'office' encontrado con ID: {mail_server.id}")
                return mail_server
            else:
                _logger.warning("Servidor de correo 'office' no encontrado")
                # Fallback: usar cualquier servidor disponible
                fallback_server = request.env['ir.mail_server'].sudo().search([], limit=1)
                if fallback_server:
                    _logger.info(f"Usando servidor fallback: {fallback_server.name}")
                    return fallback_server
                return False
                
        except Exception as e:
            _logger.exception(f"Error obteniendo servidor de correo 'office': {str(e)}")
            return False

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

            # ✅ NUEVA FUNCIONALIDAD: Obtener estado actual del stock
            stock_info = self._get_equipment_stock_info(registro)

            values = {
                'id_registro': registro.id,
                'cliente': registro.cliente_id.name if registro.cliente_id else "",
                'modelo_maquina': registro.name.name if registro.name else "",
                'serie': registro.serie if registro else "",
                'nombre': user_name or "",  # Puede venir precargado desde WhatsApp
                'celular': phone_number,
                'ubicacion_instalacion': registro.ubicacion_instalacion,
                'tipo_maquina_id': registro.tipo_maquina_id,
                'stock_info': stock_info,  # ✅ NUEVO: Info del stock actual
                'contador_actual_bn': registro.contador_actual_black or 0,
                'contador_actual_color': registro.contador_actual_color or 0,
                'gestion_automatica': stock_info.get('gestion_automatica', True),
            }

            _logger.info(f"Formulario de tóner preparado con los siguientes valores: {values}")
            return request.render('sat.solicitar_toner_form_template', {'values': values})
        
        except Exception as e:
            _logger.exception(f"Error al mostrar el formulario de solicitud de tóner: {str(e)}")
            return request.redirect('/pagina_error')

    def _get_equipment_stock_info(self, equipment):
        """Obtiene información del stock actual del equipo"""
        try:
            stock_info = {
                'black': {
                    'stock_total': equipment.stock_total_toner_black,
                    'stock_cliente': equipment.stock_cliente_toner_black,
                    'instalado': equipment.toner_black_instalado,
                    'stock_minimo': equipment.name.stock_minimo_black if equipment.name else 1,
                },
                'has_color': equipment.tipo_maquina_id == 'color',
                'gestion_automatica': equipment.name.gestionar_toner_automatico if equipment.name else True,
                'estado_stock': equipment.estado_stock_toner,
            }
            
            if equipment.tipo_maquina_id == 'color':
                stock_info.update({
                    'cyan': {
                        'stock_total': equipment.stock_total_toner_cyan,
                        'stock_cliente': equipment.stock_cliente_toner_cyan,
                        'instalado': equipment.toner_cyan_instalado,
                        'stock_minimo': equipment.name.stock_minimo_cyan if equipment.name else 1,
                    },
                    'magenta': {
                        'stock_total': equipment.stock_total_toner_magenta,
                        'stock_cliente': equipment.stock_cliente_toner_magenta,
                        'instalado': equipment.toner_magenta_instalado,
                        'stock_minimo': equipment.name.stock_minimo_magenta if equipment.name else 1,
                    },
                    'yellow': {
                        'stock_total': equipment.stock_total_toner_yellow,
                        'stock_cliente': equipment.stock_cliente_toner_yellow,
                        'instalado': equipment.toner_yellow_instalado,
                        'stock_minimo': equipment.name.stock_minimo_yellow if equipment.name else 1,
                    }
                })
            
            return stock_info
            
        except Exception as e:
            _logger.exception(f"Error obteniendo info de stock: {str(e)}")
            return {}

    @http.route('/toner/validate_request_http', type='http', auth="public", methods=['POST'], csrf=False)
    def validate_toner_request_http(self, **post):
        """
        Ruta HTTP alternativa para validación de tóner
        """
        try:
            _logger.info("=== VALIDACIÓN HTTP INICIADA ===")
            _logger.info(f"POST data: {post}")
            
            equipment_id = post.get('equipment_id')
            if not equipment_id:
                return json.dumps({'valid': False, 'message': 'Equipo no especificado'})
            
            # Preparar datos
            requested_toners = {
                'black': post.get('toner_black') == 'true',
                'cyan': post.get('toner_cyan') == 'true',
                'magenta': post.get('toner_magenta') == 'true',
                'yellow': post.get('toner_yellow') == 'true',
            }
            
            _logger.info(f"Tóners solicitados (HTTP): {requested_toners}")
            
            # Validar
            validation_result = request.env['toner.counter.submission'].sudo().validate_web_toner_request(
                equipment_id=int(equipment_id),
                requested_toners=requested_toners,
                current_counters={
                    'bn': int(post.get('counter_bn', 0)),
                    'color': int(post.get('counter_color', 0))
                }
            )
            
            _logger.info(f"Resultado validación HTTP: {validation_result}")
            
            # Retornar JSON
            response = request.make_response(
                json.dumps(validation_result),
                headers={'Content-Type': 'application/json'}
            )
            return response
            
        except Exception as e:
            _logger.exception(f"Error en validación HTTP: {str(e)}")
            error_response = {'valid': False, 'message': f'Error: {str(e)}'}
            return request.make_response(
                json.dumps(error_response),
                headers={'Content-Type': 'application/json'}
            )

    @http.route('/toner/enviar_solicitud', type='http', auth="public", methods=['POST'], website=True)
    def send_toner_request(self, **post):
        try:
            _logger.info(f"=== INICIANDO PROCESAMIENTO DE SOLICITUD DE TÓNER ===")
            _logger.info(f"Datos recibidos: {post}")
            
            # Validar campos obligatorios básicos
            required_fields = ['id_registro', 'cliente', 'nombre', 'celular', 'contometro_black']
            missing_fields = [field for field in required_fields if not post.get(field)]
            
            if missing_fields:
                _logger.error(f"Campos obligatorios faltantes: {missing_fields}")
                return request.redirect('/pagina_error')
            
            # Verificar que al menos un tóner esté solicitado
            toners_solicitados = any([
                post.get('toner_black'),
                post.get('toner_cyan'),
                post.get('toner_magenta'),
                post.get('toner_yellow')
            ])
            
            if not toners_solicitados:
                _logger.error("No se solicitó ningún tóner")
                return self._handle_no_toner_selected(post)
            
            # ✅ VALIDACIÓN INTELIGENTE
            validation_data = {
                'equipment_id': post.get('id_registro'),
                'toner_black': bool(post.get('toner_black')),
                'toner_cyan': bool(post.get('toner_cyan')),
                'toner_magenta': bool(post.get('toner_magenta')),
                'toner_yellow': bool(post.get('toner_yellow')),
                'counter_bn': int(post.get('contometro_black', 0)),
                'counter_color': int(post.get('contometro_color', 0)),
            }
            
            # Validar la solicitud
            validation_result = request.env['toner.counter.submission'].sudo().validate_web_toner_request(
                equipment_id=int(validation_data['equipment_id']),
                requested_toners={
                    'black': validation_data['toner_black'],
                    'cyan': validation_data['toner_cyan'],
                    'magenta': validation_data['toner_magenta'],
                    'yellow': validation_data['toner_yellow'],
                },
                current_counters={
                    'bn': validation_data['counter_bn'],
                    'color': validation_data['counter_color']
                }
            )

            _logger.info(f"Resultado de validación: {validation_result}")

            # ✅ SI LA VALIDACIÓN FALLA, ENVIAR A PÁGINA DE RECHAZO
            if not validation_result['valid'] and validation_result['reason'] != 'Gestión manual':
                _logger.info("Solicitud rechazada por validación")
                return self._handle_rejected_request(post, validation_result)
            
            # ✅ SI LA VALIDACIÓN PASA, CREAR REPORTE EN EL SISTEMA
            _logger.info("Solicitud aprobada - creando reporte en sistema")
            return self._process_approved_request(post, validation_result)
            
        except Exception as e:
            _logger.exception(f"Error al enviar la solicitud de tóner: {str(e)}")
            return request.redirect('/pagina_error')

    def _handle_no_toner_selected(self, post_data):
        """Maneja cuando no se seleccionó ningún tóner"""
        try:
            datos_formulario = {
                'cliente': post_data.get('cliente'),
                'nombre': post_data.get('nombre'),
                'celular': self.clean_phone_number(post_data.get('celular')),
                'modelo_maquina': post_data.get('modelo_maquina'),
                'serie': post_data.get('serie'),
            }
            
            # Enviar notificación de error al cliente
            mensaje = f"""*🏢 Soporte*

⚠️ *Error en Solicitud de Tóner*

Estimado/a {datos_formulario['nombre']},

Su solicitud no pudo ser procesada porque no seleccionó ningún tóner.

📋 *Equipo:* {datos_formulario['modelo_maquina']}
🔢 *Serie:* {datos_formulario['serie']}

Por favor, vuelva a llenar el formulario seleccionando al menos un tipo de tóner.

📞 Tel: +51924894829
📧 soporte@andescopiers.com.pe

Atentamente,
Andes Copier"""
            
            self.send_whatsapp_message_toner(datos_formulario['celular'], mensaje)
            
            return request.render('sat.solicitud_toner_sin_seleccion', {
                'datos_formulario': datos_formulario
            })
            
        except Exception as e:
            _logger.exception(f"Error manejando solicitud sin tóner: {str(e)}")
            return request.redirect('/pagina_error')

    def _handle_rejected_request(self, post_data, validation_result):
        """Maneja solicitudes rechazadas por validación"""
        try:
            _logger.info("=== MANEJANDO SOLICITUD RECHAZADA ===")
            
            # Recopilar datos para mostrar al cliente
            datos_formulario = {
                'cliente': post_data.get('cliente'),
                'nombre': post_data.get('nombre'),
                'celular': self.clean_phone_number(post_data.get('celular')),
                'modelo_maquina': post_data.get('modelo_maquina'),
                'serie': post_data.get('serie'),
            }
            
            # ✅ ENVIAR NOTIFICACIÓN DE RECHAZO AL CLIENTE
            mensaje_rechazo = self._build_rejection_message(datos_formulario, validation_result)
            self.send_whatsapp_message_toner(datos_formulario['celular'], mensaje_rechazo)
            
            # ✅ NOTIFICAR AL EQUIPO INTERNO SOBRE SOLICITUD INNECESARIA
            self._notify_internal_team_rejection(datos_formulario, validation_result)
            
            # Redirigir a página de rechazo con información
            return request.render('sat.solicitud_toner_rechazada', {
                'validation_result': validation_result,
                'datos_formulario': datos_formulario
            })
            
        except Exception as e:
            _logger.exception(f"Error manejando solicitud rechazada: {str(e)}")
            return request.redirect('/pagina_error')

    def _process_approved_request(self, post_data, validation_result):
        """Procesa solicitudes aprobadas"""
        try:
            _logger.info("=== PROCESANDO SOLICITUD APROBADA ===")
            
            # Preparar datos para crear reporte en el sistema
            web_data = {
                'equipment_id': int(post_data.get('id_registro')),
                'client_name': post_data.get('nombre'),
                'client_email': post_data.get('email', 'soporte@andescopiers.com.pe'),  # Email por defecto
                'client_phone': self.clean_phone_number(post_data.get('celular')),
                'counter_bn': int(post_data.get('contometro_black', 0)),
                'counter_color': int(post_data.get('contometro_color', 0)),
                'requires_black': bool(post_data.get('toner_black')),
                'requires_cyan': bool(post_data.get('toner_cyan')),
                'requires_magenta': bool(post_data.get('toner_magenta')),
                'requires_yellow': bool(post_data.get('toner_yellow')),
                'notes': f"Solicitud web - Validada automáticamente\nObservaciones: {post_data.get('observaciones', 'Sin observaciones')}"
            }
            
            _logger.info(f"Datos para crear reporte: {web_data}")
            
            # ✅ CREAR REPORTE EN EL SISTEMA INTELIGENTE
            creation_result = request.env['toner.counter.submission'].sudo().create_from_web_request(web_data)
            
            _logger.info(f"Resultado de creación: {creation_result}")
            
            if creation_result['success']:
                # Enviar confirmación al cliente
                self._send_approval_notification(post_data, creation_result)
                
                # Notificar al equipo interno
                self._notify_internal_team_approval(post_data, creation_result)
                
                # Redirigir a página de confirmación exitosa
                return request.render('sat.solicitud_toner_aprobada', {
                    'creation_result': creation_result,
                    'datos_formulario': post_data
                })
            else:
                raise ValidationError(f"Error creando reporte: {creation_result.get('error')}")
                
        except Exception as e:
            _logger.exception(f"Error procesando solicitud aprobada: {str(e)}")
            return request.redirect('/pagina_error')

    def _build_rejection_message(self, datos_formulario, validation_result):
        """Construye mensaje de rechazo para WhatsApp"""
        blocked_info = ""
        if validation_result.get('blocked_toners'):
            blocked_list = []
            for blocked in validation_result['blocked_toners']:
                blocked_list.append(f"• {blocked['color'].title()}: {blocked['reason']}")
            blocked_info = "\n\n🚫 *Tóners no necesarios:*\n" + "\n".join(blocked_list)
        
        mensaje = f"""*🏢 Soporte*

🚨 *Solicitud de Tóner No Aprobada*

Estimado/a {datos_formulario['nombre']},

Su solicitud de tóner ha sido evaluada automáticamente por nuestro sistema:

📋 *Equipo:* {datos_formulario['modelo_maquina']}
🔢 *Serie:* {datos_formulario['serie']}

❌ *Motivo del rechazo:*
{validation_result['message']}{blocked_info}

✅ *Su equipo actualmente tiene stock suficiente*

Si considera que hay un error o tiene una situación especial, puede contactarnos directamente:

📞 Tel: +51924894829
📧 Email: soporte@andescopiers.com.pe

Atentamente,
Soporte"""
        
        return mensaje

    def _send_approval_notification(self, post_data, creation_result):
        """Envía notificación de aprobación al cliente"""
        try:
            datos_formulario = {
                'nombre': post_data.get('nombre'),
                'celular': self.clean_phone_number(post_data.get('celular')),
                'modelo_maquina': post_data.get('modelo_maquina'),
                'serie': post_data.get('serie'),
            }
            
            # Construir lista de tóners aprobados
            summary = creation_result.get('validation_details', {})
            toners_aprobados = summary.get('requested_toners', [])
            
            mensaje = f"""*🏢 Soporte*

✅ *Solicitud de Tóner Aprobada*

Estimado/a {datos_formulario['nombre']},

Su solicitud ha sido aprobada y registrada en nuestro sistema:

📋 *Número de Reporte:* {creation_result['secuencia']}
🖨️ *Equipo:* {datos_formulario['modelo_maquina']}
🔢 *Serie:* {datos_formulario['serie']}
📦 *Tóners aprobados:* {', '.join(toners_aprobados) if toners_aprobados else 'Ninguno'}

{'🚚 *Entrega programada automáticamente*' if creation_result['requires_automatic_delivery'] else '📋 *Será revisado por nuestro equipo*'}

Recibirá confirmación de la fecha de entrega.

📞 Tel: +51924894829
📧 soporte@andescopiers.com.pe"""
            
            self.send_whatsapp_message_toner(datos_formulario['celular'], mensaje)
            
        except Exception as e:
            _logger.exception(f"Error enviando notificación de aprobación: {str(e)}")

    def _notify_internal_team_rejection(self, datos_formulario, validation_result):
        """Notifica al equipo interno sobre solicitud rechazada"""
            mail_server = self._get_office_mail_server()
        try:
            # Email interno sobre rechazo
            body_html = f"""
            <h3>🚫 Solicitud de Tóner Rechazada Automáticamente</h3>
            <p><strong>Cliente:</strong> {datos_formulario['cliente']}</p>
            <p><strong>Solicitante:</strong> {datos_formulario['nombre']}</p>
            <p><strong>Equipo:</strong> {datos_formulario['modelo_maquina']}</p>
            <p><strong>Serie:</strong> {datos_formulario['serie']}</p>
            <p><strong>Motivo:</strong> {validation_result['message']}</p>
            
            <h4>Detalles del rechazo:</h4>
            <ul>
            """
            
            for blocked in validation_result.get('blocked_toners', []):
                body_html += f"<li><strong>{blocked['color'].title()}:</strong> {blocked['reason']}</li>"
            
            body_html += "</ul><p><em>Esta solicitud fue rechazada automáticamente por el sistema de validación inteligente.</em></p>"
            
            mail_values = {
                'subject': f"🚫 Solicitud Tóner Rechazada - {datos_formulario['modelo_maquina']}",
                'body_html': body_html,
                'email_from': 'soporte@andescopiers.com.pe',
                'email_to': 'jamilet.roggero@andescopiers.com.pe',
                'mail_server_id': mail_server.id if mail_server else False,
            }
            
            request.env['mail.mail'].sudo().create(mail_values)
            
        except Exception as e:
            _logger.exception(f"Error notificando rechazo al equipo: {str(e)}")

    def _notify_internal_team_approval(self, datos_formulario, creation_result):
        """Notifica al equipo interno sobre solicitud aprobada"""
        try:
            # Usar el método existente pero con información del sistema
            summary = creation_result.get('validation_details', {})
            mail_server = self._get_office_mail_server()
            body_html = f"""
            <h3>✅ Nueva Solicitud de Tóner Aprobada</h3>
            <p><strong>Número de Reporte:</strong> {creation_result['secuencia']}</p>
            <p><strong>Cliente:</strong> {datos_formulario.get('cliente')}</p>
            <p><strong>Equipo:</strong> {summary.get('equipment_name', 'Sin nombre')}</p>
            <p><strong>Tóners solicitados:</strong> {', '.join(summary.get('requested_toners', []))}</p>
            <p><strong>Entrega automática:</strong> {'✅ Sí' if creation_result['requires_automatic_delivery'] else '❌ No'}</p>
            <p><em>Esta solicitud fue validada y aprobada automáticamente por el sistema inteligente.</em></p>
            """
            
            mail_values = {
                'subject': f"✅ Solicitud Tóner Aprobada - {creation_result['secuencia']}",
                'body_html': body_html,
                'email_from': 'soporte@andescopiers.com.pe',
                'email_to': 'jamilet.roggero@andescopiers.com.pe',
                'email_cc': 'comercial@andescopiers.com.pe, alquiler@andescopiers.com.pe',
                'mail_server_id': mail_server.id if mail_server else False,
            }
            
            request.env['mail.mail'].sudo().create(mail_values)
            
        except Exception as e:
            _logger.exception(f"Error notificando aprobación al equipo: {str(e)}")

    @http.route('/pagina_confirmacion_toner', type='http', auth="public", website=True)
    def pagina_confirmacion(self, **kw):
        try:
            _logger.info("Mostrando la página de confirmación de tóner.")
            return request.render('sat.pagina_confirmacion_toner')
        except Exception as e:
            _logger.exception(f"Error al mostrar la página de confirmación de tóner: {str(e)}")
            return request.redirect('/pagina_error')

    def send_whatsapp_message_toner(self, phone, message):
        """Envia un mensaje de WhatsApp relacionado con la solicitud de tóner."""
        try:
            _logger.debug(f"Enviando mensaje de WhatsApp para tóner a {phone} con contenido: {message}")
            
            url = 'https://whatsapp.andessolutioncopiers.com/api/message'
            data = {
                'phone': phone,
                'message': message,
                'type': 'text'  # ✅ AGREGAR tipo de mensaje
            }
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, json=data, timeout=30)

            _logger.debug(f"Código de estado: {response.status_code}")
            _logger.debug(f"Respuesta de la API: {response.text}")
            
            return response.status_code == 200
            
        except Exception as e:
            _logger.error(f"Error enviando mensaje de WhatsApp para tóner: {str(e)}")
            return False


