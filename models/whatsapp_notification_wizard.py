# =============================================================================
# WIZARD PARA NOTIFICACIÓN A GRUPOS DE WHATSAPP - TICKETS
# =============================================================================

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class WhatsappNotificationWizard(models.TransientModel):
    _name = 'whatsapp.notification.wizard'
    _description = 'Wizard para Notificar Grupos WhatsApp'

    # Campos principales
    ticket_id = fields.Many2one('ticket.alquiler', string='Ticket', required=True, readonly=True)
    
    # Información del ticket (solo lectura)
    cliente_name = fields.Char(string='Cliente', related='ticket_id.partner_id.name', readonly=True)
    direccion = fields.Char(string='Dirección', related='ticket_id.direccion_id_r', readonly=True)
    modelo_equipo = fields.Char(string='Modelo', related='ticket_id.modelo_id_r', readonly=True)
    serie_equipo = fields.Char(string='Serie', related='ticket_id.serie_id_r', readonly=True)
    tipo_equipo = fields.Selection(related='ticket_id.tipo_id', string='Tipo de Equipo', readonly=True)
    problema_descripcion = fields.Text(string='Problema', related='ticket_id.description', readonly=True)
    fecha_visita = fields.Char(string='Fecha de Visita', related='ticket_id.agenda_local', readonly=True)
    tecnico_name = fields.Char(string='Técnico', related='ticket_id.responsable.name', readonly=True)
    
    # Configuración de notificación
    notificar_grupos = fields.Boolean(string='Notificar a Grupos de WhatsApp', default=True)
    grupo_seleccionado = fields.Selection(
        selection='_get_grupos_whatsapp',
        string='Grupo de WhatsApp',
        help="Seleccionar el grupo que será notificado sobre la visita técnica"
    )
    
    # Gestión de tóner
    cliente_solicita_toner = fields.Boolean(
        string='Cliente solicita tóner',
        help="Marcar si el cliente ha reportado que necesita tóner"
    )
    enviar_toner = fields.Boolean(
        string='Enviar tóner con el técnico',
        help="Marcar si se debe enviar tóner con el técnico"
    )
    observaciones_toner = fields.Text(
        string='Observaciones sobre tóner',
        help="Especificar qué tipo de tóner o cantidades"
    )
    
    # Mensaje personalizado
    mensaje_adicional = fields.Text(
        string='Mensaje adicional',
        help="Información adicional para incluir en la notificación"
    )

    @api.model
    def _get_grupos_whatsapp(self):
        """Obtiene la lista de grupos de WhatsApp desde la API"""
        try:
            url = 'http://149.56.117.184:3005/api/groups'
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    grupos = []
                    for grupo in data['data']:
                        grupos.append((grupo['id'], grupo['name']))
                    return grupos
            
            _logger.warning("No se pudieron obtener los grupos de WhatsApp")
            return [('', 'No hay grupos disponibles')]
            
        except Exception as e:
            _logger.error(f"Error al obtener grupos de WhatsApp: {str(e)}")
            return [('', 'Error al cargar grupos')]

    @api.onchange('cliente_solicita_toner')
    def _onchange_cliente_solicita_toner(self):
        """Auto-marcar enviar_toner si el cliente lo solicita"""
        if self.cliente_solicita_toner:
            self.enviar_toner = True
            # Sugerir observaciones basadas en el tipo de equipo
            if self.tipo_equipo == 'color':
                self.observaciones_toner = "Tóner completo: Negro, Cyan, Magenta, Amarillo"
            else:
                self.observaciones_toner = "Tóner negro"
        else:
            self.enviar_toner = False
            self.observaciones_toner = ""

    def _generar_mensaje_notificacion(self):
        """Genera el mensaje de notificación para WhatsApp"""
        self.ensure_one()
        
        # Encabezado del mensaje
        mensaje = f"""🔧 *VISITA TÉCNICA PROGRAMADA* 🔧

*INFORMACIÓN DEL TICKET*
- Ticket #: {self.ticket_id.name}
- Cliente: {self.cliente_name or 'No especificado'}
- Dirección: {self.direccion or 'No especificada'}
- Fecha y hora: {self.fecha_visita or 'No programada'}
- Técnico: {self.tecnico_name or 'No asignado'}

*EQUIPO*
- Modelo: {self.modelo_equipo or 'No especificado'}
- Serie: {self.serie_equipo or 'No especificada'}
- Tipo: {'Color' if self.tipo_equipo == 'color' else 'Monocromática' if self.tipo_equipo == 'monocromatica' else 'No especificado'}

*PROBLEMA REPORTADO*
{self.problema_descripcion or 'No especificado'}
"""

        # Información sobre tóner
        if self.cliente_solicita_toner or self.enviar_toner:
            mensaje += "\n*TÓNER*\n"
            
            if self.cliente_solicita_toner:
                mensaje += "✅ Cliente solicita tóner\n"
            
            if self.enviar_toner:
                mensaje += "📦 Se enviará tóner con el técnico\n"
                if self.observaciones_toner:
                    mensaje += f"• Especificaciones: {self.observaciones_toner}\n"
            else:
                mensaje += "❌ No se enviará tóner\n"

        # Mensaje adicional
        if self.mensaje_adicional:
            mensaje += f"\n*OBSERVACIONES ADICIONALES*\n{self.mensaje_adicional}\n"

        # Pie del mensaje
        mensaje += "\n⚠️ *Por favor, evalúen si es necesario enviar suministros adicionales con el técnico.*"
        
        return mensaje

    def _enviar_notificacion_whatsapp(self):
        """Envía la notificación al grupo de WhatsApp seleccionado"""
        if not self.grupo_seleccionado:
            raise UserError("Debe seleccionar un grupo de WhatsApp")
        
        mensaje = self._generar_mensaje_notificacion()
        
        try:
            url = 'https://whatsapp.andessolutioncopiers.com/api/message'
            data = {
                'phone': self.grupo_seleccionado,
                'message': mensaje,
                'type': 'text'
            }
            headers = {'Content-Type': 'application/json'}
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('success'):
                    _logger.info(f"Notificación enviada exitosamente al grupo {self.grupo_seleccionado}")
                    return True
                else:
                    error_msg = response_data.get('message', 'Error desconocido')
                    _logger.error(f"Error en API WhatsApp: {error_msg}")
                    raise UserError(f"Error al enviar notificación: {error_msg}")
            else:
                _logger.error(f"Error HTTP al enviar notificación: {response.status_code}")
                raise UserError(f"Error de conexión: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error de red al enviar notificación WhatsApp: {str(e)}")
            raise UserError(f"Error de conexión: {str(e)}")
        except Exception as e:
            _logger.error(f"Error inesperado al enviar notificación WhatsApp: {str(e)}")
            raise UserError(f"Error inesperado: {str(e)}")

    def action_enviar_notificacion(self):
        """Acción para enviar la notificación y proceder con el ticket"""
        self.ensure_one()
        
        try:
            # Enviar notificación si está habilitada
            if self.notificar_grupos and self.grupo_seleccionado:
                self._enviar_notificacion_whatsapp()
                
                # Registrar la notificación en el ticket
                self.ticket_id.message_post(
                    body=f"📤 <b>Notificación enviada a grupo WhatsApp</b><br/>"
                         f"Grupo: {dict(self._get_grupos_whatsapp()).get(self.grupo_seleccionado, self.grupo_seleccionado)}<br/>"
                         f"Tóner solicitado: {'Sí' if self.cliente_solicita_toner else 'No'}<br/>"
                         f"Enviar tóner: {'Sí' if self.enviar_toner else 'No'}",
                    message_type='notification'
                )
            
            # Actualizar campos del ticket con la información del tóner
            vals_to_update = {}
            if self.cliente_solicita_toner or self.enviar_toner or self.observaciones_toner:
                # Agregar la información al campo mensaje del ticket
                mensaje_actual = self.ticket_id.mensaje or ''
                info_toner = []
                
                if self.cliente_solicita_toner:
                    info_toner.append("• Cliente solicita tóner")
                if self.enviar_toner:
                    info_toner.append("• Se enviará tóner con el técnico")
                if self.observaciones_toner:
                    info_toner.append(f"• Especificaciones tóner: {self.observaciones_toner}")
                
                if info_toner:
                    mensaje_toner = "\n\nINFORMACIÓN DE TÓNER:\n" + "\n".join(info_toner)
                    vals_to_update['mensaje'] = mensaje_actual + mensaje_toner
            
            if vals_to_update:
                self.ticket_id.write(vals_to_update)
            
            # Ejecutar el método original de envío de WhatsApp del ticket
            return self.ticket_id._enviar_mensaje_whatsapp_original()
            
        except Exception as e:
            _logger.error(f"Error en wizard de notificación: {str(e)}")
            raise UserError(f"Error al procesar la notificación: {str(e)}")

    def action_cancelar(self):
        """Cancelar el wizard y proceder directamente con el envío original"""
        return self.ticket_id._enviar_mensaje_whatsapp_original()

    def action_solo_notificar(self):
        """Solo enviar la notificación sin proceder con el ticket"""
        self.ensure_one()
        
        if not self.notificar_grupos:
            raise UserError("Debe habilitar la notificación a grupos")
        
        if not self.grupo_seleccionado:
            raise UserError("Debe seleccionar un grupo de WhatsApp")
        
        try:
            self._enviar_notificacion_whatsapp()
            
            # Registrar en el ticket
            self.ticket_id.message_post(
                body=f"📤 <b>Notificación manual enviada a grupo WhatsApp</b><br/>"
                     f"Grupo: {dict(self._get_grupos_whatsapp()).get(self.grupo_seleccionado, self.grupo_seleccionado)}<br/>"
                     f"Usuario: {self.env.user.name}",
                message_type='notification'
            )
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Notificación enviada',
                    'message': 'La notificación ha sido enviada exitosamente al grupo de WhatsApp',
                    'type': 'success',
                }
            }
            
        except Exception as e:
            raise UserError(f"Error al enviar notificación: {str(e)}")