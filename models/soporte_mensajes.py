from odoo import _, models, fields, api, exceptions
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError
from odoo.http import request
from datetime import datetime, timedelta
from odoo.exceptions import UserError
from pytz import timezone, UTC
import requests
import json
import logging

_logger = logging.getLogger(__name__)

class SoporteMensajes(models.Model):
    _inherit = 'ticket.alquiler'
    _description = 'Mensajes de Soporte'

    def _enviar_whatsapp_consolidado(self, tickets, cliente, tecnico):
        """
        Envía un solo mensaje WhatsApp consolidado por grupo
        """
        try:
            # Mensaje consolidado para el técnico
            if tecnico and tickets[0].responsable_mobile_clean and tickets[0].responsable_mobile_clean != 'NA':
                msg_tecnico = self._generar_mensaje_tecnico_consolidado(tickets, tecnico)
                tickets[0].send_whatsapp_message(tickets[0].responsable_mobile_clean, msg_tecnico)
                _logger.info(f"✅ WhatsApp consolidado enviado al técnico {tecnico.name}")
            
            # Mensaje consolidado para el cliente
            if cliente and tickets[0].cliente_phones_clean and tickets[0].cliente_phones_clean != 'NA':
                msg_cliente = self._generar_mensaje_cliente_consolidado(tickets, cliente, tecnico)
                phone_numbers = tickets[0].cliente_phones_clean.split(',')
                for phone_number in phone_numbers:
                    tickets[0].send_whatsapp_message(phone_number, msg_cliente)
                _logger.info(f"✅ WhatsApp consolidado enviado al cliente {cliente.name}")
                
        except Exception as e:
            _logger.error(f"❌ Error enviando WhatsApp consolidado: {e}")

    def _generar_mensaje_tecnico_consolidado(self, tickets, tecnico):
        """
        Genera un mensaje consolidado para el técnico con todos sus tickets.
        Incluye el link público de evidencia fotográfica por cada ticket.
        """
        cantidad = len(tickets)
        tecnico_name = tecnico.name if tecnico else 'NA'

        servicios_agrupados = {}

        for ticket in tickets:
            tipo_servicio = dict(ticket._fields['tipo_servicio_id'].selection).get(
                ticket.tipo_servicio_id,
                'NA'
            )
            if tipo_servicio not in servicios_agrupados:
                servicios_agrupados[tipo_servicio] = []
            servicios_agrupados[tipo_servicio].append(ticket)

        mensaje = f"Hola *{tecnico_name}*,\n\n"

        if cantidad == 1:
            mensaje += "Se le ha asignado un Ticket de servicio:"
        else:
            mensaje += f"Se le han asignado *{cantidad} Tickets* de servicio:"

        mensaje += "\n\n"

        if len(servicios_agrupados) > 1:
            mensaje += "*RESUMEN POR TIPO DE SERVICIO:*\n"
            for tipo, tickets_tipo in servicios_agrupados.items():
                mensaje += f"• {tipo}: {len(tickets_tipo)} ticket(s)\n"
            mensaje += "\n"

        clientes_agrupados = {}

        for ticket in tickets:
            cliente_name = ticket.partner_id.name if ticket.partner_id else 'Sin cliente'
            if cliente_name not in clientes_agrupados:
                clientes_agrupados[cliente_name] = []
            clientes_agrupados[cliente_name].append(ticket)

        for cliente_name, tickets_cliente in clientes_agrupados.items():
            mensaje += f"*CLIENTE: {cliente_name}*\n"

            primer_ticket = tickets_cliente[0]

            mensaje += f"📍 Dirección: {primer_ticket.direccion_id_r or 'NA'}\n"
            mensaje += f"📞 Contacto: {primer_ticket.contacto_id_r or 'NA'}\n"
            mensaje += f"📱 Celular: {primer_ticket.product_alquiler.celular if primer_ticket.product_alquiler else 'NA'}\n"
            mensaje += f"📅 Fecha de visita: {primer_ticket.agenda_local or 'NA'}\n"

            tickets_directos = [t for t in tickets_cliente if t.asistencia_id == 'si']

            if tickets_directos:
                mensaje += "⚠️ *ASISTENCIA DIRECTA*\n"

            mensaje += "\n*EQUIPOS A ATENDER:*\n"

            for i, ticket in enumerate(tickets_cliente, 1):
                tipo_servicio = dict(ticket._fields['tipo_servicio_id'].selection).get(
                    ticket.tipo_servicio_id,
                    'NA'
                )

                evidencia_url = ticket._get_evidencia_url()

                mensaje += f"  {i}. *{ticket.name}* - {tipo_servicio}\n"
                mensaje += f"     Modelo: {ticket.product_alquiler.name.name if ticket.product_alquiler and ticket.product_alquiler.name else 'NA'}\n"
                mensaje += f"     Serie: {ticket.serie_id_r or 'NA'}\n"
                mensaje += f"     Problema: {ticket.description or 'NA'}\n"
                mensaje += f"     URL Ticket: {ticket.url}\n"
                mensaje += f"     📸 Fotos evidencia: {evidencia_url}\n\n"

            mensaje += "---\n\n"

        if cantidad > 1:
            mensaje += f"*TOTAL DE TICKETS: {cantidad}*\n"
            mensaje += "Revise cada ticket en Odoo para detalles completos.\n\n"

        mensaje += (
            "Lea atentamente todos los detalles del servicio.\n\n"
            "*Importante:* use el link de fotos de evidencia para subir imágenes "
            "ANTES al llegar y DESPUÉS al finalizar."
        )

        return mensaje
    def _generar_mensaje_cliente_consolidado(self, tickets, cliente, tecnico):
        """
        Genera un mensaje consolidado para el cliente con todos sus tickets
        """
        cantidad = len(tickets)
        cliente_name = cliente.name if cliente else 'NA'
        tecnico_name = tecnico.name if tecnico else 'NA'
        tecnico_dni = tecnico.vat if tecnico else 'NA'
        
        # Usar fecha del primer ticket (deberían ser del mismo día)
        fecha_visita = tickets[0].agenda_local if tickets else 'NA'
        direccion = tickets[0].direccion_id_r if tickets else 'NA'
        
        mensaje = f"Estimado/a *{cliente_name}*,\n\n"
        
        if cantidad == 1:
            mensaje += "Le informamos que hemos programado una visita técnica para atender su requerimiento:"
        else:
            mensaje += f"Le informamos que hemos programado una visita técnica para atender *{cantidad} requerimientos*:"
        
        mensaje += "\n\n"
        mensaje += f"*INFORMACIÓN DE LA VISITA*\n"
        mensaje += f"📅 Fecha de Visita: {fecha_visita}\n"
        mensaje += f"📍 Dirección: {direccion}\n"
        mensaje += f"👨‍🔧 Técnico: {tecnico_name}\n"
        mensaje += f"🆔 DNI: {tecnico_dni}\n\n"
        
        # Agrupar por tipo de servicio
        servicios_agrupados = {}
        for ticket in tickets:
            tipo_servicio = dict(ticket._fields['tipo_servicio_id'].selection).get(ticket.tipo_servicio_id, 'NA')
            if tipo_servicio not in servicios_agrupados:
                servicios_agrupados[tipo_servicio] = []
            servicios_agrupados[tipo_servicio].append(ticket)
        
        # Mostrar resumen de servicios
        mensaje += f"*SERVICIOS PROGRAMADOS ({cantidad}):*\n"
        for tipo_servicio, tickets_tipo in servicios_agrupados.items():
            mensaje += f"• {tipo_servicio}: {len(tickets_tipo)} equipo(s)\n"
        mensaje += "\n"
        
        # Detalles de cada equipo
        mensaje += f"*EQUIPOS A ATENDER:*\n"
        for i, ticket in enumerate(tickets, 1):
            tipo_servicio = dict(ticket._fields['tipo_servicio_id'].selection).get(ticket.tipo_servicio_id, 'NA')
            mensaje += f"*EQUIPO #{i} - TICKET {ticket.name}*\n"
            mensaje += f"🔧 Servicio: {tipo_servicio}\n"
            mensaje += f"🏭 Marca: {ticket.marca_id_r or 'NA'}\n"
            mensaje += f"📱 Modelo: {ticket.product_alquiler.name.name if ticket.product_alquiler and ticket.product_alquiler.name else 'NA'}\n"
            mensaje += f"🔢 Serie: {ticket.serie_id_r or 'NA'}\n"
            mensaje += f"⚠️ Problema: {ticket.description or 'NA'}\n\n"
        
        mensaje += f"*IMPORTANTE:*\n"
        mensaje += f"1. Dar autorización para el ingreso de nuestro personal a sus oficinas.\n"
        mensaje += f"2. Disponibilidad de espacio y tiempo para el desarrollo del trabajo.\n"
        
        if cantidad > 1:
            mensaje += f"3. Los {cantidad} equipos serán atendidos en la misma visita.\n"
        
        mensaje += f"\nGracias por su atención."
        
        return mensaje

    def _enviar_correos_consolidados(self, tickets, cliente, tecnico):
        """
        Envía correos consolidados usando las nuevas plantillas
        """
        try:
            contexto_consolidado = {
                'tickets_grupo': tickets,
                'cantidad_tickets': len(tickets),
                'cliente_principal': cliente,
                'tecnico_principal': tecnico,
                'es_asignacion_masiva': True,
                'tickets_por_tipo_servicio': self._agrupar_tickets_por_tipo_servicio(tickets),
            }
            
            primer_ticket = tickets[0]
            
            # Correo consolidado al cliente
            template_cliente = self.env.ref('sat.email_template_ticket_cliente_consolidado')
            template_cliente.with_context(**contexto_consolidado).send_mail(primer_ticket.id, force_send=True)
            
            # Correo consolidado al técnico
            template_tecnico = self.env.ref('sat.email_template_ticket_tecnico_consolidado')
            template_tecnico.with_context(**contexto_consolidado).send_mail(primer_ticket.id, force_send=True)
            
            # Correo consolidado de asistencia directa si aplica
            tickets_directos = tickets.filtered(lambda t: t.asistencia_id == 'si')
            if tickets_directos:
                contexto_directo = contexto_consolidado.copy()
                contexto_directo['tickets_asistencia_directa'] = tickets_directos
                template_directo = self.env.ref('sat.mail_template_asistencia_directa_consolidado')
                template_directo.with_context(**contexto_directo).send_mail(primer_ticket.id, force_send=True)
            
        except Exception as e:
            _logger.error(f"Error enviando correos consolidados: {e}")
    def _notificar_gerente_asistencia_directa_consolidada(self, tickets_directos):
        """
        Notifica al gerente sobre tickets con asistencia directa (mensaje consolidado)
        """
        try:
            if not tickets_directos:
                return
            
            cantidad = len(tickets_directos)
            tecnico = tickets_directos[0].responsable
            cliente = tickets_directos[0].partner_id
            
            mensaje = f"⚠️ *VISITAS TÉCNICAS DIRECTAS* ⚠️\n\n"
            mensaje += f"👨‍🔧 Técnico: {tecnico.name if tecnico else 'NA'}\n"
            mensaje += f"👥 Cliente: {cliente.name if cliente else 'NA'}\n"
            mensaje += f"📊 Cantidad de visitas: {cantidad}\n\n"
            
            mensaje += f"*TICKETS CON ASISTENCIA DIRECTA:*\n"
            for ticket in tickets_directos:
                mensaje += f"• {ticket.name} - {ticket.product_alquiler.name.name if ticket.product_alquiler and ticket.product_alquiler.name else 'NA'}\n"
                mensaje += f"  📅 {ticket.agenda_local or 'NA'}\n"
                if ticket.direccion_id_r:
                    mensaje += f"  📍 {ticket.direccion_id_r}\n"
            
            mensaje += f"\n⚠️ Se ha programado asistencia directa para todos estos equipos."
            
            # Enviar al gerente
            tickets_directos[0].send_whatsapp_message('17862826794', mensaje)
            _logger.info(f"✅ Notificación consolidada de asistencia directa enviada al gerente para {cantidad} tickets")
            
        except Exception as e:
            _logger.error(f"❌ Error notificando al gerente de forma consolidada: {e}")

    def _enviar_notificacion_grupo_consolidada(self, tickets, wizard_data):
        """
        Envía una notificación consolidada al grupo de WhatsApp
        """
        try:
            cantidad = len(tickets)
            cliente = tickets[0].partner_id
            tecnico = tickets[0].responsable
            fecha_visita = tickets[0].agenda_local
            
            # Generar mensaje consolidado para el grupo
            mensaje = f"🔧 *VISITAS TÉCNICAS PROGRAMADAS* 🔧\n\n"
            mensaje += f"👥 Cliente: {cliente.name if cliente else 'NA'}\n"
            mensaje += f"👨‍🔧 Técnico: {tecnico.name if tecnico else 'NA'}\n"
            mensaje += f"📅 Fecha: {fecha_visita or 'NA'}\n"
            mensaje += f"📊 Cantidad de equipos: {cantidad}\n\n"
            
            # Agrupar por tipo de servicio
            servicios_agrupados = self._agrupar_tickets_por_tipo_servicio(tickets)
            mensaje += f"*SERVICIOS PROGRAMADOS:*\n"
            for tipo_servicio, tickets_tipo in servicios_agrupados.items():
                tipo_label = dict(tickets[0]._fields['tipo_servicio_id'].selection).get(tipo_servicio, tipo_servicio)
                mensaje += f"• {tipo_label}: {len(tickets_tipo)} equipo(s)\n"
            
            mensaje += f"\n*EQUIPOS:*\n"
            for i, ticket in enumerate(tickets, 1):
                mensaje += f"{i}. {ticket.name} - {ticket.product_alquiler.name.name if ticket.product_alquiler and ticket.product_alquiler.name else 'NA'}\n"
                mensaje += f"   Serie: {ticket.serie_id_r or 'NA'}\n"
            
            # Información de tóner si existe
            if wizard_data.get('cliente_solicita_toner') or wizard_data.get('enviar_toner'):
                mensaje += f"\n*GESTIÓN DE TÓNER:*\n"
                if wizard_data.get('cliente_solicita_toner'):
                    mensaje += f"✅ Cliente solicita tóner\n"
                if wizard_data.get('enviar_toner'):
                    mensaje += f"📦 Se enviará tóner con el técnico\n"
                    if wizard_data.get('observaciones_toner'):
                        mensaje += f"• Especificaciones: {wizard_data.get('observaciones_toner')}\n"
            
            # Mensaje adicional
            if wizard_data.get('mensaje_adicional'):
                mensaje += f"\n*OBSERVACIONES:*\n{wizard_data.get('mensaje_adicional')}\n"
            
            mensaje += f"\n⚠️ *Evalúen si es necesario enviar suministros adicionales.*"
            
            # Enviar al grupo
            grupo_id = wizard_data.get('grupo_seleccionado')
            if grupo_id:
                tickets[0].send_whatsapp_message(grupo_id, mensaje)
                _logger.info(f"✅ Notificación consolidada enviada al grupo {grupo_id} para {cantidad} tickets")
            
        except Exception as e:
            _logger.error(f"❌ Error enviando notificación consolidada al grupo: {e}")
    def enviar_mensaje_whatsapp_reporter(self):
        """Enviar mensaje de WhatsApp con los datos proporcionados por el cliente."""
        if self.reporter_phone:
            # Datos del reporte del cliente
            message = (
                f"Estimado/a {self.reporter_name},\n\n"
                "Hemos recibido su reporte de incidente y agradecemos la información proporcionada. "
                "A continuación, detallamos los datos registrados:\n\n"
                f"Cliente: {self.partner_id.name if self.partner_id else 'No especificado'}\n"
                f"Dirección: {self.direccion_id_r if self.direccion_id_r else 'No especificada'}\n"
                f"Modelo: {self.modelo_id_r if self.modelo_id_r else 'No especificada'}\n"
                f"Serie: {self.serie_id_r if self.serie_id_r else 'No especificada'}\n"
                f"Descripción del problema: {self.description if self.description else 'No proporcionada'}\n"
            )

            if self.problem_photo:
                message += "Foto del problema: Se adjuntará en un correo."

            message += (
                "\nNuestro equipo de soporte programará la asistencia técnica en función de la disponibilidad. "
                "Nos pondremos en contacto con usted para confirmar la fecha y hora."
            )

            # Enviar mensaje de WhatsApp con los detalles del cliente
            self.send_whatsapp_message(self.reporter_phone, message)


    def _enviar_notificacion_pendientes(self, tecnico, tickets):
        """
        Envía notificación por WhatsApp al técnico sobre sus tickets pendientes.
        
        Args:
            tecnico: objeto res.users del técnico
            tickets: lista de tickets pendientes
        """
        if not tecnico or not tickets:
            return False
            
        # Verificar si el técnico tiene número de teléfono limpio
        phone_number = None
        for ticket in tickets:
            if ticket.responsable_mobile_clean and ticket.responsable_mobile_clean != 'NA':
                phone_number = ticket.responsable_mobile_clean
                break
                
        if not phone_number:
            _logger.warning(f"No se encontró número de teléfono válido para el técnico {tecnico.name}")
            return False
            
        # Construir mensaje
        cantidad_tickets = len(tickets)
        lista_tickets = "\n".join([
            f"• Ticket: {t.name} - Cliente: {t.partner_id.name or 'NA'} - Fecha: {t.agenda_local or 'NA'}"
            for t in tickets[:5]  # Mostrar máximo 5 tickets para no hacer el mensaje muy largo
        ])
        
        if cantidad_tickets > 5:
            lista_tickets += f"\n... y {cantidad_tickets - 5} tickets más."
        
        mensaje = f"""
⚠️ *ALERTA DE TICKETS PENDIENTES* ⚠️

Hola *{tecnico.name}*,

Tienes *{cantidad_tickets} tickets* en proceso que necesitan ser finalizados:

{lista_tickets}

Por favor, finaliza estos tickets lo antes posible. 
        
*IMPORTANTE:* Si no cierras estos tickets a tiempo, se notificará a gerencia y no podrás solicitar movilidad hasta regularizar tu situación.

Para finalizar rápidamente un ticket, ingresa a Odoo y usa la opción "Finalizar".
"""
        
        # Enviar mensaje por WhatsApp
        try:
            for ticket in tickets:
                # Usar el primer ticket para enviar el mensaje
                resultado = ticket.send_whatsapp_message(phone_number, mensaje)
                # Registrar la notificación en el log de los tickets
                for t in tickets:
                    t.write({'last_pending_notification': fields.Datetime.now()})
                    t.message_post(
                        body=f"Notificación automática enviada al técnico sobre tickets pendientes por finalizar. "
                             f"Total: {cantidad_tickets} ticket(s)."
                    )
                
                _logger.info(f"Mensaje de alerta enviado al técnico {tecnico.name} sobre {cantidad_tickets} tickets pendientes")
                break
                
            return True
        except Exception as e:
            _logger.error(f"Error al enviar notificación de tickets pendientes: {str(e)}")
            return False

    def send_whatsapp_message(self, phone, message, file_url=None):
        """Envía un mensaje de WhatsApp con o sin archivo adjunto utilizando la API externa."""
        _logger.debug(f"Enviando mensaje a {phone} con contenido: {message} y archivo: {file_url}")
        
        try:
            # Si hay archivo, usar endpoint de media
            if file_url:
                url = 'https://boot.andessolutioncopiers.com/api/send-media'
                data = {
                    'to': phone,
                    'caption': message,
                    'url': file_url
                }
            else:
                # Sin archivo, usar endpoint de texto
                url = 'https://boot.andessolutioncopiers.com/api/send-message'
                data = {
                    'to': phone,
                    'message': message
                }
            
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': 'wg_fc215093f007df7ff4a32c04c7d8170d11960583e3a1b43a695037f5a627d3e3'
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            _logger.debug(f"Código de estado: {response.status_code}")
            _logger.debug(f"Respuesta de la API: {response.text}")
            
            try:
                response_json = response.json()
                _logger.debug(f"Respuesta JSON: {response_json}")
                
                # Validar respuesta exitosa
                if response.status_code == 200 and response_json.get('success'):
                    _logger.info(f"✅ Mensaje enviado exitosamente a {phone}")
                    return response_json
                else:
                    error_msg = response_json.get('error', 'Error desconocido')
                    _logger.error(f"❌ Error en API: {error_msg}")
                    return {"error": error_msg, "success": False}
                    
            except json.JSONDecodeError as e:
                error_msg = f"La respuesta no contiene un JSON válido: {str(e)}"
                _logger.error(error_msg)
                _logger.error(f"Respuesta raw: {response.text}")
                return {"error": error_msg, "success": False}
                
        except requests.exceptions.Timeout:
            error_msg = f"Timeout al enviar mensaje a {phone}"
            _logger.error(f"❌ {error_msg}")
            return {"error": error_msg, "success": False}
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Error de red al enviar mensaje: {str(e)}"
            _logger.error(f"❌ {error_msg}")
            return {"error": error_msg, "success": False}
            
        except Exception as e:
            error_msg = f"Error inesperado: {str(e)}"
            _logger.error(f"❌ {error_msg}")
            return {"error": error_msg, "success": False}


    

    def enviar_mensaje_whatsapp_finalizacion(self):
        msg_cliente_finalizacion = "Hola, estimado cliente.\n\nQueremos informarle que hemos completado satisfactoriamente nuestra visita técnica programada. A continuación, le detallamos el trabajo realizado durante la visita:\n\n*Ticket #:* {}\n*Fecha de Visita:* {}\n*Tipo de servicio:* {}\n*Dirección:* {}\n*Técnico Asignado:* {}\n*DNI:* {}\n\n*ESPECIFICACIONES DEL EQUIPO*\n*Marca:* {}\n*Modelo:* {}\n*Serie:* {}\n*Contómetro K:* {}\n*Contómetro color:* {}\n*Contómetro scanner:* {}\n\n*PROBLEMA REPORTADO*\n{}\n\n*INFORME TÉCNICO*\n{}\n\nAgradecemos su confianza en nuestros servicios y productos. Si necesita más asistencia o tiene cualquier requerimiento adicional, no dude en comunicarse con nosotros.".format(
            self.name if self.name else 'NA',
            self.agenda.strftime('%d/%m/%Y') if self.agenda else 'NA',
            self.tipo_servicio_id if self.tipo_servicio_id else 'NA',
            self.direccion_id_r if self.direccion_id_r else 'NA',
            self.responsable.name if self.responsable and self.responsable.name else 'NA',
            self.responsable.vat if self.responsable and self.responsable.vat else 'NA',
            self.marca_id_r if self.marca_id_r else 'NA',
            self.product_alquiler.name.name if self.product_alquiler.name and self.product_alquiler.name.name else 'NA',
            self.serie_id_r if self.serie_id_r else 'NA',
            self.contometrok_id if self.contometrok_id else 'NA',
            self.contometroc_id if self.contometroc_id else 'NA',
            self.contometros_id if self.contometros_id else 'NA',
            self.description if self.description else 'NA',
            self.informe_id if self.informe_id else 'NA'
        )

        # Generar URL del informe
        file_url = self._generate_report_url()

        # Enviar mensaje al cliente
        if self.cliente_phones_clean:
            phone_numbers = self.cliente_phones_clean.split(',')
            for phone_number in phone_numbers:
                self.send_whatsapp_message(phone_number, msg_cliente_finalizacion, file_url)

        # Enviando el correo de finalización al cliente
        template4 = self.env.ref('sat.email_template_ticket_cliente_finalizacion')
        template4.send_mail(self.id, force_send=True)
        # Verificar el valor de asistencia_id
        if self.retorno_id == 'no':
            # Enviar el correo de retorno si asistencia_id es 'no'
            template5 = self.env.ref('sat.ticket_alquiler')
            template5.send_mail(self.id, force_send=True)



    def _enviar_mensaje_whatsapp_original(self):
        """
        Método original con tu código actual de envío de WhatsApp
        (Copia EXACTAMENTE tu método enviar_mensaje_whatsapp actual aquí)
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        _logger.info("Iniciando el proceso de envío de mensaje de WhatsApp para el registro ID: %s", self.id)

        # Crear evento en calendario
        try:
            _logger.info("Intentando crear un evento en el calendario...")
            evento_creado = self.crear_evento_calendario()
            if not evento_creado:
                _logger.warning("No se pudo crear el evento en el calendario para el registro ID: %s", self.id)
                self.message_post(body="No se pudo crear el evento en el calendario.")
            else:
                _logger.info("Evento creado/actualizado exitosamente para el registro ID: %s", self.id)
        except Exception as e:
            _logger.error("Error al intentar crear el evento en el calendario para el registro ID: %s. Detalles: %s", self.id, str(e))
            self.message_post(body=f"Error al intentar crear el evento en el calendario: {str(e)}")

        # Obtener etiquetas de selección
        try:
            selection_labels = self.get_selection_labels()
            _logger.debug("Etiquetas de selección obtenidas: %s", selection_labels)
        except Exception as e:
            _logger.error("Error al obtener etiquetas de selección para el registro ID: %s. Detalles: %s", self.id, str(e))
            selection_labels = {}

        # Mensaje para el técnico
        try:
            evidencia_url = self._get_evidencia_url()

            msg_tecnico = (
                f"Hola *{self.responsable.name if self.responsable and self.responsable.name else 'NA'}*,\n\n"
                "Se le ha asignado un Ticket de servicio. Lea atentamente los detalles del servicio:\n\n"
                f"*Cliente:* {self.partner_id.name if self.partner_id and self.partner_id.name else 'NA'}\n"
                f"*Dirección:* {self.direccion_id_r if self.direccion_id_r else 'NA'}\n"
                f"*Contacto:* {self.contacto_id_r if self.contacto_id_r else 'NA'}\n"
                f"*Modelo:* {self.product_alquiler.name.name if self.product_alquiler.name and self.product_alquiler.name.name else 'NA'}\n"
                f"*Serie:* {self.serie_id_r if self.serie_id_r else 'NA'}\n"
                f"*Problema:* {self.description if self.description else 'NA'}\n"
                f"*Fecha de visita:* {self.agenda_local if self.agenda_local else 'NA'}\n"
                f"*Tipo de servicio:* {dict(self._fields['tipo_servicio_id'].selection).get(self.tipo_servicio_id, 'NA')}\n"
                f"*Asistencia directa:* {dict(self._fields['asistencia_id'].selection).get(self.asistencia_id, 'NA')}\n\n"
                f"*URL del Ticket:* {self.url}\n"
                f"*📸 Fotos de evidencia:* {evidencia_url}\n\n"
                f"*Indicaciones de evidencia:*\n"
                f"1. Abrir el link desde el celular.\n"
                f"2. Permitir ubicación/GPS.\n"
                f"3. Subir fotos en ANTES al llegar.\n"
                f"4. Subir fotos en DESPUÉS al finalizar."
            )
            _logger.debug("Mensaje para técnico generado: %s", msg_tecnico)
        except Exception as e:
            _logger.error("Error al generar mensaje para el técnico. Detalles: %s", str(e))
            msg_tecnico = ""

        # Mensaje para el cliente
        try:
            msg_cliente = "Estimado/a *{}*,\n\nLe informamos que hemos programado una visita técnica para atender su requerimiento. A continuación, le detallamos la información correspondiente:\n\n*Ticket #:* {}\n*Fecha de Visita:* {}\n*Tipo de servicio:* {}\n*Dirección:* {}\n*Técnico:* {}\n*DNI:* {}\n\n*ESPECIFICACIONES DEL EQUIPO*\n*Marca:* {}\n*Modelo:* {}\n*Serie:* {}\n\n*PROBLEMA REPORTADO*\n{}\n\n1. Dar autorización para el ingreso de nuestro personal a sus oficinas o el espacio donde se encuentre nuestro equipo.\n2. Disponibilidad de espacio y tiempo para que nuestro personal pueda desarrollar su labor.\n\nGracias por su atención.".format(
                self.partner_id.name if self.partner_id and self.partner_id.name else 'NA',
                self.name if self.name else 'NA',
                self.agenda_local if self.agenda_local else 'NA',
                selection_labels.get('tipo_servicio_id', 'NA'),
                self.direccion_id_r if self.direccion_id_r else 'NA',
                self.responsable.name if self.responsable and self.responsable.name else 'NA',
                self.responsable.vat if self.responsable and self.responsable.vat else 'NA',
                self.marca_id_r if self.marca_id_r else 'NA',
                self.product_alquiler.name.name if self.product_alquiler.name and self.product_alquiler.name.name else 'NA',
                self.serie_id_r if self.serie_id_r else 'NA',
                self.description if self.description else 'NA'
            )
            _logger.debug("Mensaje para cliente generado: %s", msg_cliente)
        except Exception as e:
            _logger.error("Error al generar mensaje para el cliente. Detalles: %s", str(e))
            msg_cliente = ""

        # Enviar mensaje al técnico
        if self.responsable and self.responsable_mobile_clean:
            try:
                phone_number = self.responsable_mobile_clean
                _logger.info("Enviando mensaje de WhatsApp al técnico: %s", phone_number)
                self.send_whatsapp_message(phone_number, msg_tecnico)
            except Exception as e:
                _logger.error("Error al enviar mensaje de WhatsApp al técnico. Detalles: %s", str(e))

        # Enviar mensaje al cliente
        if self.cliente_phones_clean:
            try:
                phone_numbers = self.cliente_phones_clean.split(',')
                for phone_number in phone_numbers:
                    _logger.info("Enviando mensaje de WhatsApp al cliente: %s", phone_number)
                    self.send_whatsapp_message(phone_number, msg_cliente)
            except Exception as e:
                _logger.error("Error al enviar mensaje de WhatsApp al cliente. Detalles: %s", str(e))
                
        # Añadir notificación al gerente si es asistencia directa
        if self.asistencia_id == 'si':
            msg_gerente = (
                f"⚠️ *VISITA TÉCNICA DIRECTA*\n\n"
                f"Técnico: {self.responsable.name if self.responsable and self.responsable.name else 'NA'}\n"
                f"Cliente: {self.partner_id.name if self.partner_id and self.partner_id.name else 'NA'}\n"
                f"Fecha y hora: {self.agenda_local if self.agenda_local else 'NA'}\n"
                f"Dirección: {self.direccion_id_r if self.direccion_id_r else 'NA'}"
            )
            try:
                _logger.info("Enviando notificación de visita directa al gerente")
                self.send_whatsapp_message('17862826794', msg_gerente)
            except Exception as e:
                _logger.error("Error al enviar mensaje al gerente. Detalles: %s", str(e))

        # Enviar correos electrónicos
        try:
            template1 = self.env.ref('sat.email_template_ticket_cliente')
            template1.with_context(selection_labels=selection_labels).send_mail(self.id, force_send=True)
            _logger.info("Correo enviado al cliente.")
            
            template2 = self.env.ref('sat.email_template_ticket_tecnico')
            template2.with_context(selection_labels=selection_labels).send_mail(self.id, force_send=True)
            _logger.info("Correo enviado al técnico.")
            
            if self.asistencia_id == 'si':
                template3 = self.env.ref('sat.mail_template_asistencia_directa')
                template3.with_context(selection_labels=selection_labels).send_mail(self.id, force_send=True)
                _logger.info("Correo adicional enviado por asistencia directa.")
        except Exception as e:
            _logger.error("Error al enviar correos electrónicos. Detalles: %s", str(e))

        # Cambiar estado
        self.estado = 'proceso'
        _logger.info("Estado del registro ID: %s cambiado a 'proceso'.", self.id)

        return {
            'type': 'ir.actions.act_window_close'
        }
