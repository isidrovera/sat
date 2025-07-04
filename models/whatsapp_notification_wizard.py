# =============================================================================
# WIZARD COMPLETO PARA NOTIFICACIÓN A GRUPOS DE WHATSAPP - TICKETS
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
    notificar_grupos = fields.Boolean(
        string='¿Notificar a Grupos de WhatsApp?', 
        default=False,
        help="Marcar si desea notificar a un grupo de WhatsApp sobre esta visita técnica"
    )
    grupo_seleccionado = fields.Selection(
        selection='_get_grupos_disponibles',
        string='Seleccionar Grupo de WhatsApp',
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
        string='Mensaje adicional (opcional)',
        help="Información adicional para incluir en la notificación"
    )

    @api.model
    def _get_grupos_disponibles(self):
        """Obtiene todos los grupos disponibles desde la API"""
        grupos = []
        
        try:
            url = 'http://149.56.117.184:3005/api/groups'
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    for grupo in data['data']:
                        grupos.append((grupo['id'], grupo['name']))
                    
                    # Ordenar alfabéticamente por nombre
                    grupos.sort(key=lambda x: x[1])
                    
                    _logger.info(f"Grupos obtenidos: {len(grupos)}")
                    return grupos
            
            _logger.warning("No se pudieron obtener los grupos de WhatsApp desde la API")
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

    @api.onchange('notificar_grupos')
    def _onchange_notificar_grupos(self):
        """Limpiar grupo seleccionado si se desmarca la notificación"""
        if not self.notificar_grupos:
            self.grupo_seleccionado = False

    def _generar_mensaje_notificacion(self):
        """Genera el mensaje de notificación para WhatsApp"""
        self.ensure_one()
        
        # Encabezado del mensaje
        mensaje = f"""🔧 *VISITA TÉCNICA PROGRAMADA* 🔧

*INFORMACIÓN DEL TICKET*
• Ticket #: {self.ticket_id.name}
• Cliente: {self.cliente_name or 'No especificado'}
• Dirección: {self.direccion or 'No especificada'}
• Fecha y hora: {self.fecha_visita or 'No programada'}
• Técnico: {self.tecnico_name or 'No asignado'}

*EQUIPO*
• Modelo: {self.modelo_equipo or 'No especificado'}
• Serie: {self.serie_equipo or 'No especificada'}
• Tipo: {'Color' if self.tipo_equipo == 'color' else 'Monocromática' if self.tipo_equipo == 'monocromatica' else 'No especificado'}

*PROBLEMA REPORTADO*
{self.problema_descripcion or 'No especificado'}
"""

        # Información sobre tóner
        if self.cliente_solicita_toner or self.enviar_toner:
            mensaje += "\n*GESTIÓN DE TÓNER*\n"
            
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
            
            _logger.info(f"Enviando notificación WhatsApp al grupo: {self.grupo_seleccionado}")
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('success'):
                    _logger.info(f"✅ Notificación enviada exitosamente al grupo {self.grupo_seleccionado}")
                    return True
                else:
                    error_msg = response_data.get('message', 'Error desconocido en la respuesta')
                    _logger.error(f"❌ Error en respuesta API WhatsApp: {error_msg}")
                    raise UserError(f"Error al enviar notificación: {error_msg}")
            else:
                _logger.error(f"❌ Error HTTP al enviar notificación: {response.status_code}")
                raise UserError(f"Error de conexión HTTP: {response.status_code}")
                
        except requests.exceptions.Timeout:
            _logger.error("⏰ Timeout al enviar notificación WhatsApp")
            raise UserError("Tiempo de espera agotado al enviar la notificación")
        except requests.exceptions.ConnectionError:
            _logger.error("🌐 Error de conexión al enviar notificación WhatsApp")
            raise UserError("Error de conexión con el servicio de WhatsApp")
        except requests.exceptions.RequestException as e:
            _logger.error(f"🔌 Error de red al enviar notificación WhatsApp: {str(e)}")
            raise UserError(f"Error de red: {str(e)}")
        except Exception as e:
            _logger.error(f"💥 Error inesperado al enviar notificación WhatsApp: {str(e)}")
            raise UserError(f"Error inesperado: {str(e)}")

    def action_confirmar_asignacion(self):
        """Acción principal: enviar notificación (si está habilitada) y proceder con la asignación"""
        self.ensure_one()
        
        try:
            # 1. Enviar notificación si está habilitada
            notificacion_enviada = False
            if self.notificar_grupos:
                if not self.grupo_seleccionado:
                    raise UserError("Debe seleccionar un grupo de WhatsApp para enviar la notificación")
                
                self._enviar_notificacion_whatsapp()
                notificacion_enviada = True
            
            # 2. Registrar información en el ticket
            self._registrar_informacion_ticket(notificacion_enviada)
            
            # 3. Ejecutar el proceso normal de asignación
            return self.ticket_id._enviar_mensaje_whatsapp_original()
            
        except UserError:
            # Re-lanzar errores de usuario sin modificar
            raise
        except Exception as e:
            _logger.error(f"Error en confirmación de asignación: {str(e)}")
            raise UserError(f"Error al procesar la asignación: {str(e)}")

    def _registrar_informacion_ticket(self, notificacion_enviada):
        """Registra la información del wizard en el ticket"""
        self.ensure_one()
        
        # Mensaje en el chatter del ticket
        mensaje_chatter = "📋 <b>Proceso de Asignación Completado</b><br/>"
        
        if notificacion_enviada:
            # Obtener nombre del grupo
            grupos_disponibles = dict(self._get_grupos_disponibles())
            nombre_grupo = grupos_disponibles.get(self.grupo_seleccionado, self.grupo_seleccionado)
            
            mensaje_chatter += f"📤 <b>Notificación enviada a grupo WhatsApp:</b> {nombre_grupo}<br/>"
        else:
            mensaje_chatter += "📤 <b>No se envió notificación a grupos de WhatsApp</b><br/>"
        
        # Información de tóner
        if self.cliente_solicita_toner or self.enviar_toner:
            mensaje_chatter += "<br/><b>🖨️ Información de Tóner:</b><br/>"
            if self.cliente_solicita_toner:
                mensaje_chatter += "• Cliente solicita tóner<br/>"
            if self.enviar_toner:
                mensaje_chatter += "• Se enviará tóner con el técnico<br/>"
                if self.observaciones_toner:
                    mensaje_chatter += f"• Especificaciones: {self.observaciones_toner}<br/>"
        
        # Mensaje adicional
        if self.mensaje_adicional:
            mensaje_chatter += f"<br/><b>📝 Observaciones adicionales:</b><br/>{self.mensaje_adicional}<br/>"
        
        mensaje_chatter += f"<br/><small>Procesado por: {self.env.user.name}</small>"
        
        # Registrar en el ticket
        self.ticket_id.message_post(
            body=mensaje_chatter,
            message_type='notification'
        )
        
        # Actualizar campo mensaje del ticket si hay información de tóner
        if self.cliente_solicita_toner or self.enviar_toner or self.observaciones_toner:
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
                self.ticket_id.write({'mensaje': mensaje_actual + mensaje_toner})

    def action_cancelar(self):
        """Cancelar el wizard y proceder directamente con la asignación"""
        self.ensure_one()
        
        # Registrar que se canceló el wizard
        self.ticket_id.message_post(
            body=f"❌ <b>Asignación directa</b><br/>El usuario canceló el wizard de notificación.<br/>"
                 f"<small>Procesado por: {self.env.user.name}</small>",
            message_type='notification'
        )
        
        # Ejecutar asignación directa
        return self.ticket_id._enviar_mensaje_whatsapp_original()

    def action_refrescar_grupos(self):
        """Refrescar la lista de grupos disponibles"""
        self.ensure_one()
        
        try:
            # Forzar recarga de grupos
            grupos = self._get_grupos_disponibles()
            
            if grupos and grupos != [('', 'No hay grupos disponibles')]:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Grupos actualizados',
                        'message': f'Se encontraron {len(grupos)} grupos disponibles',
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Sin grupos',
                        'message': 'No se encontraron grupos disponibles',
                        'type': 'warning',
                    }
                }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Error al actualizar grupos: {str(e)}',
                    'type': 'danger',
                }
            }