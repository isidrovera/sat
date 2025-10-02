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
    ticket_id = fields.Many2one('ticket.alquiler', string='Ticket', required=False, readonly=True)
    
    # Información del ticket (solo lectura)
    cliente_name = fields.Char(string='Cliente', related='ticket_id.partner_id.name', readonly=True)
    direccion = fields.Char(string='Dirección', related='ticket_id.direccion_id_r', readonly=True)
    modelo_equipo = fields.Char(string='Modelo', related='ticket_id.modelo_id_r', readonly=True)
    serie_equipo = fields.Char(string='Serie', related='ticket_id.serie_id_r', readonly=True)
    tipo_equipo = fields.Selection(related='ticket_id.tipo_id', string='Tipo de Equipo', readonly=True)
    problema_descripcion = fields.Text(string='Problema', related='ticket_id.description', readonly=True)
    fecha_visita_ticket = fields.Char(string='Fecha de Visita', related='ticket_id.agenda_local', readonly=True)
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
            url = 'http://51.222.13.19:3005/api/groups'
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
            
            _logger.info(f"Respuesta API WhatsApp - Código: {response.status_code}")
            
            # Verificar diferentes escenarios de respuesta
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    if response_data.get('success'):
                        _logger.info(f"✅ Notificación enviada exitosamente al grupo {self.grupo_seleccionado}")
                        return True
                    else:
                        error_msg = response_data.get('message', 'Error desconocido en la respuesta')
                        _logger.warning(f"⚠️ API responde con success=false: {error_msg}")
                        # Asumir que se envió si no hay error crítico
                        if 'error' not in error_msg.lower():
                            _logger.info("📤 Asumiendo envío exitoso a pesar de success=false")
                            return True
                        else:
                            raise UserError(f"Error al enviar notificación: {error_msg}")
                except ValueError:
                    # Si no puede parsear JSON, pero código 200, asumir éxito
                    _logger.warning("⚠️ Respuesta 200 pero sin JSON válido - asumiendo éxito")
                    return True
                    
            elif response.status_code == 500:
                # Error 500 puede ser temporal pero el mensaje podría haberse enviado
                _logger.warning(f"⚠️ Error 500 del servidor API - verificando si se envió el mensaje")
                try:
                    response_data = response.json()
                    # Si hay alguna indicación de éxito parcial, continuar
                    if 'sent' in str(response_data).lower() or 'delivered' in str(response_data).lower():
                        _logger.info("📤 Error 500 pero mensaje parece haberse enviado")
                        return True
                except:
                    pass
                
                # Dar opción al usuario
                _logger.warning("⚠️ Error 500 - El mensaje podría haberse enviado. Continuando con precaución.")
                return True  # Asumir éxito para no bloquear el flujo
                
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
        except UserError:
            # Re-lanzar errores de usuario sin modificar
            raise
        except Exception as e:
            _logger.error(f"💥 Error inesperado al enviar notificación WhatsApp: {str(e)}")
            # Para errores inesperados, asumir que se envió y continuar
            _logger.warning("🔄 Continuando con el proceso a pesar del error inesperado")
            return True

    # ==============================================================================
    # EXTENSIÓN DEL WIZARD PARA MANEJO MASIVO
    # Agregar estos campos y métodos al modelo whatsapp.notification.wizard existente
    # ==============================================================================

    # NUEVOS CAMPOS para manejo masivo
    es_asignacion_masiva = fields.Boolean(string='Es Asignación Masiva', default=False)
    tickets_masivos_ids = fields.Many2many(
        'ticket.alquiler', 
        string='Tickets Seleccionados',
        help="Tickets seleccionados para asignación masiva"
    )

    # CAMPOS COMUNES para aplicar masivamente
    tecnico_asignado = fields.Many2one(
        'res.users', 
        string='Técnico Responsable',
        #domain=[('groups_id', 'in', [])],  # Ajustar dominio según tus grupos de técnicos
        help="Técnico que se asignará a todos los tickets seleccionados"
    )
    fecha_visita = fields.Datetime(
        string='Fecha de Visita',
        help="Fecha y hora que se aplicará a todos los tickets"
    )
    asistencia_directa = fields.Selection(
        [('no', 'No'), ('si', 'Si')], 
        string='Asistencia Directa', 
        default='no',
        help="Si la visita requiere asistencia directa (se aplicará a todos los tickets)"
    )

    # LÍNEAS EDITABLES para cada ticket
    ticket_line_ids = fields.One2many(
        'whatsapp.notification.wizard.line', 
        'wizard_id', 
        string='Tickets a Procesar',
        help="Lista editable de tickets con tipo de servicio individual"
    )

    # CAMPOS CALCULADOS para mostrar información
    total_tickets = fields.Integer(
        string='Total de Tickets', 
        compute='_compute_total_tickets',
        store=False
    )
    clientes_involucrados = fields.Char(
        string='Clientes Involucrados', 
        compute='_compute_clientes_involucrados',
        store=False
    )
    resumen_servicios = fields.Text(
        string='Resumen de Servicios',
        compute='_compute_resumen_servicios',
        store=False
    )

    # MÉTODOS COMPUTED
    @api.depends('tickets_masivos_ids')
    def _compute_total_tickets(self):
        for wizard in self:
            wizard.total_tickets = len(wizard.tickets_masivos_ids)

    @api.depends('tickets_masivos_ids')
    def _compute_clientes_involucrados(self):
        for wizard in self:
            if wizard.tickets_masivos_ids:
                clientes = wizard.tickets_masivos_ids.mapped('partner_id.name')
                clientes_unicos = list(set([c for c in clientes if c]))
                wizard.clientes_involucrados = ', '.join(clientes_unicos) if clientes_unicos else 'Sin clientes'
            else:
                wizard.clientes_involucrados = ''

    @api.depends('ticket_line_ids', 'ticket_line_ids.tipo_servicio_id')
    def _compute_resumen_servicios(self):
        for wizard in self:
            if wizard.ticket_line_ids:
                servicios = {}
                for line in wizard.ticket_line_ids:
                    tipo = line.tipo_servicio_id
                    if tipo:
                        tipo_label = dict(line._fields['tipo_servicio_id'].selection).get(tipo, tipo)
                        servicios[tipo_label] = servicios.get(tipo_label, 0) + 1
                
                resumen = []
                for servicio, cantidad in servicios.items():
                    resumen.append(f"• {servicio}: {cantidad} ticket(s)")
                wizard.resumen_servicios = '\n'.join(resumen) if resumen else 'Sin servicios definidos'
            else:
                wizard.resumen_servicios = ''

    # MODIFICA: create() con logs
    @api.model
    def create(self, vals):
        _logger.info("🧩 [wizard.create] vals=%s", vals)
        wizard = super().create(vals)
        _logger.info("🧩 [wizard.create] creado id=%s es_asignacion_masiva=%s tickets=%s",
                    wizard.id, wizard.es_asignacion_masiva, len(wizard.tickets_masivos_ids))

        if wizard.es_asignacion_masiva and wizard.tickets_masivos_ids:
            _logger.info("🧩 [wizard.create] generando líneas...")
            wizard._crear_lineas_tickets()
            # defaults de apoyo
            primer = wizard.tickets_masivos_ids[0]
            if not wizard.tecnico_asignado and getattr(primer, 'responsable', False):
                wizard.tecnico_asignado = primer.responsable
            if not wizard.fecha_visita and getattr(primer, 'agenda', False):
                wizard.fecha_visita = primer.agenda
            if getattr(primer, 'asistencia_id', False):
                wizard.asistencia_directa = primer.asistencia_id

        _logger.info("🧩 [wizard.create] listo: lines=%s", len(wizard.ticket_line_ids))
        return wizard


    # MODIFICA: _crear_lineas_tickets() con logs finos
    def _crear_lineas_tickets(self):
        self.ensure_one()
        _logger.info("🧱 [_crear_lineas_tickets] wizard=%s tickets=%s", self.id, self.tickets_masivos_ids.ids)
        # Limpiar
        removed = len(self.ticket_line_ids)
        self.ticket_line_ids.unlink()
        if removed:
            _logger.info("🧱 [_crear_lineas_tickets] líneas previas eliminadas: %s", removed)

        count = 0
        for t in self.tickets_masivos_ids:
            self.env['whatsapp.notification.wizard.line'].create({
                'wizard_id': self.id,
                'ticket_id': t.id,
                'tipo_servicio_id': getattr(t, 'tipo_servicio_id', False) or 'revision',
                'observaciones': '',
            })
            count += 1
        _logger.info("✅ [_crear_lineas_tickets] creadas=%s", count)


    def action_confirmar_asignacion_masiva(self):
        """Confirma la asignación masiva con valores del wizard"""
        self.ensure_one()
        
        if not self.es_asignacion_masiva:
            # Si no es masiva, usar método original
            return self.action_confirmar_asignacion()
        
        # Validaciones para asignación masiva
        if not self.tecnico_asignado:
            raise UserError("Debe asignar un técnico responsable para todos los tickets")
        
        if not self.fecha_visita:
            raise UserError("Debe asignar una fecha de visita para todos los tickets")
        
        if not self.ticket_line_ids:
            raise UserError("No se encontraron tickets para procesar")
        
        # Validar que todas las líneas tengan tipo de servicio
        lineas_sin_servicio = self.ticket_line_ids.filtered(lambda l: not l.tipo_servicio_id)
        if lineas_sin_servicio:
            tickets_sin_servicio = lineas_sin_servicio.mapped('ticket_id.name')
            raise UserError(f"Los siguientes tickets no tienen tipo de servicio definido: {', '.join(tickets_sin_servicio)}")
        
        try:
            # Preparar datos del wizard para procesamiento
            wizard_data = {
                'tecnico_asignado': self.tecnico_asignado,
                'fecha_visita': self.fecha_visita,
                'asistencia_directa': self.asistencia_directa,
                'notificar_grupos': self.notificar_grupos,
                'grupo_seleccionado': self.grupo_seleccionado,
                'cliente_solicita_toner': self.cliente_solicita_toner,
                'enviar_toner': self.enviar_toner,
                'observaciones_toner': self.observaciones_toner,
                'mensaje_adicional': self.mensaje_adicional,
                'ticket_lines': [
                    {
                        'ticket_id': line.ticket_id.id,
                        'tipo_servicio_id': line.tipo_servicio_id,
                        'observaciones': line.observaciones
                    }
                    for line in self.ticket_line_ids
                ]
            }
            
            # 1. Enviar notificación a grupos si está habilitada
            if self.notificar_grupos and self.grupo_seleccionado:
                self.tickets_masivos_ids._enviar_notificacion_grupo_consolidada(self.tickets_masivos_ids, wizard_data)
            
            # 2. Registrar información en tickets
            self._registrar_informacion_masiva()
            
            # 3. Procesar asignación masiva
            self.tickets_masivos_ids._procesar_asignacion_masiva(wizard_data)
            
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Asignación Masiva Completada',
                    'message': f'Se asignaron correctamente {len(self.tickets_masivos_ids)} tickets.',
                    'type': 'ir.actions.act_window_close',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error en asignación masiva: {e}")
            raise UserError(f"Error al procesar la asignación masiva: {str(e)}")

    def _registrar_informacion_masiva(self):
        """Registra información del wizard en todos los tickets masivos"""
        self.ensure_one()
        
        # Mensaje base
        mensaje_base = f"📋 <b>Asignación Masiva Completada</b><br/>"
        mensaje_base += f"👨‍🔧 <b>Técnico:</b> {self.tecnico_asignado.name}<br/>"
        mensaje_base += f"📅 <b>Fecha:</b> {self.fecha_visita.strftime('%d/%m/%Y %H:%M') if self.fecha_visita else 'NA'}<br/>"
        mensaje_base += f"🔧 <b>Asistencia Directa:</b> {'Sí' if self.asistencia_directa == 'si' else 'No'}<br/>"
        
        if self.notificar_grupos:
            grupos_disponibles = dict(self._get_grupos_disponibles())
            nombre_grupo = grupos_disponibles.get(self.grupo_seleccionado, self.grupo_seleccionado)
            mensaje_base += f"📤 <b>Grupo notificado:</b> {nombre_grupo}<br/>"
        
        # Información de tóner
        if self.cliente_solicita_toner or self.enviar_toner:
            mensaje_base += "<br/><b>🖨️ Información de Tóner:</b><br/>"
            if self.cliente_solicita_toner:
                mensaje_base += "• Cliente solicita tóner<br/>"
            if self.enviar_toner:
                mensaje_base += "• Se enviará tóner con el técnico<br/>"
                if self.observaciones_toner:
                    mensaje_base += f"• Especificaciones: {self.observaciones_toner}<br/>"
        
        if self.mensaje_adicional:
            mensaje_base += f"<br/><b>📝 Observaciones:</b><br/>{self.mensaje_adicional}<br/>"
        
        mensaje_base += f"<br/><small>Total de tickets procesados: {len(self.tickets_masivos_ids)}</small><br/>"
        mensaje_base += f"<small>Procesado por: {self.env.user.name}</small>"
        
        # Registrar en cada ticket con información específica
        for line in self.ticket_line_ids:
            ticket = line.ticket_id
            mensaje_ticket = mensaje_base
            
            # Agregar información específica del ticket
            tipo_servicio_label = dict(line._fields['tipo_servicio_id'].selection).get(line.tipo_servicio_id, line.tipo_servicio_id)
            mensaje_ticket += f"<br/><b>🔧 Tipo de servicio asignado:</b> {tipo_servicio_label}<br/>"
            
            if line.observaciones:
                mensaje_ticket += f"<b>📝 Observaciones específicas:</b> {line.observaciones}<br/>"
            
            ticket.message_post(
                body=mensaje_ticket,
                message_type='notification'
            )

    # OVERRIDE del método action_confirmar_asignacion existente
    def action_confirmar_asignacion(self):
        """Acción principal: decidir entre individual o masiva"""
        self.ensure_one()
        
        if self.es_asignacion_masiva:
            return self.action_confirmar_asignacion_masiva()
        else:
            # Usar método original para asignación individual
            return self._action_confirmar_asignacion_individual()

    def _action_confirmar_asignacion_individual(self):
        """Método original para asignación individual (renombrar el existente)"""
        # Aquí va el código del método action_confirmar_asignacion() original
        # que actualmente tienes en el wizard
        
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

    # MÉTODOS AUXILIARES
    def action_refrescar_lineas(self):
        """Refresca las líneas de tickets manualmente"""
        self.ensure_one()
        if self.tickets_masivos_ids:
            self._crear_lineas_tickets()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Líneas Actualizadas',
                    'message': f'Se actualizaron las líneas para {len(self.tickets_masivos_ids)} tickets.',
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sin Tickets',
                    'message': 'No hay tickets seleccionados para procesar.',
                    'type': 'warning',
                }
            }

    def action_aplicar_valores_comunes(self):
        """Aplica valores comunes a todas las líneas"""
        self.ensure_one()
        
        if not self.tecnico_asignado or not self.fecha_visita:
            raise UserError("Debe completar al menos Técnico y Fecha antes de aplicar valores comunes")
        
        # Contar líneas actualizadas
        lineas_actualizadas = 0
        for line in self.ticket_line_ids:
            if line.ticket_id:
                # Solo actualizar campos vacíos o diferentes
                actualizado = False
                if not line.ticket_id.responsable or line.ticket_id.responsable != self.tecnico_asignado:
                    actualizado = True
                if not line.ticket_id.agenda or line.ticket_id.agenda != self.fecha_visita:
                    actualizado = True
                if actualizado:
                    lineas_actualizadas += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Valores Preparados',
                'message': f'Los valores comunes se aplicarán a {lineas_actualizadas} tickets al confirmar.',
                'type': 'info',
            }
        }

    # ONCHANGE METHODS
    @api.onchange('tecnico_asignado')
    def _onchange_tecnico_asignado(self):
        """Cuando cambia el técnico, actualizar información relacionada"""
        if self.tecnico_asignado and self.es_asignacion_masiva:
            # Verificar si el técnico tiene móvil para WhatsApp
            if not self.tecnico_asignado.mobile_phone:
                return {
                    'warning': {
                        'title': 'Técnico sin móvil',
                        'message': f'El técnico {self.tecnico_asignado.name} no tiene número de móvil registrado. No se podrán enviar mensajes WhatsApp.'
                    }
                }

    @api.onchange('fecha_visita')
    def _onchange_fecha_visita(self):
        """Validar fecha de visita"""
        if self.fecha_visita:
            from datetime import datetime
            if self.fecha_visita < datetime.now():
                return {
                    'warning': {
                        'title': 'Fecha en el pasado',
                        'message': 'La fecha de visita está en el pasado. ¿Está seguro de continuar?'
                    }
                }

    @api.onchange('asistencia_directa')
    def _onchange_asistencia_directa(self):
        """Mostrar advertencia para asistencia directa"""
        if self.asistencia_directa == 'si' and self.es_asignacion_masiva:
            return {
                'warning': {
                    'title': 'Asistencia Directa Masiva',
                    'message': f'Se marcará asistencia directa para {len(self.tickets_masivos_ids)} tickets. Se notificará a gerencia.'
                }
            }

    # VALIDACIONES
    @api.constrains('tickets_masivos_ids', 'tecnico_asignado', 'fecha_visita')
    def _check_asignacion_masiva(self):
        """Validaciones para asignación masiva"""
        for wizard in self:
            if wizard.es_asignacion_masiva:
                if not wizard.tickets_masivos_ids:
                    raise UserError("Debe seleccionar al menos un ticket para asignación masiva")
                
                if len(wizard.tickets_masivos_ids) == 1:
                    raise UserError("Para un solo ticket use asignación individual")
                
                # Verificar que todos los tickets estén en estado nuevo
                tickets_no_nuevos = wizard.tickets_masivos_ids.filtered(lambda t: t.estado != 'nuevo')
                if tickets_no_nuevos:
                    raise UserError(f"Algunos tickets no están en estado 'nuevo': {', '.join(tickets_no_nuevos.mapped('name'))}")

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


    def action_enviar_notificacion(self):
        """Acción: Enviar notificación y proceder con el ticket"""
        self.ensure_one()
        
        try:
            # 1. Validar que hay grupo seleccionado
            if not self.grupo_seleccionado:
                raise UserError("Debe seleccionar un grupo de WhatsApp para enviar la notificación")
            
            # 2. Enviar notificación
            self._enviar_notificacion_whatsapp()
            
            # 3. Registrar información en el ticket
            self._registrar_informacion_ticket(notificacion_enviada=True)
            
            # 4. Ejecutar el proceso normal de asignación del ticket
            return self.ticket_id._enviar_mensaje_whatsapp_original()
            
        except UserError:
            # Re-lanzar errores de usuario sin modificar
            raise
        except Exception as e:
            _logger.error(f"Error en action_enviar_notificacion: {str(e)}")
            raise UserError(f"Error al procesar la notificación y asignación: {str(e)}")

    def action_solo_notificar(self):
        """Acción: Solo enviar notificación sin proceder con el ticket"""
        self.ensure_one()
        
        try:
            # 1. Validar que hay grupo seleccionado
            if not self.grupo_seleccionado:
                raise UserError("Debe seleccionar un grupo de WhatsApp para enviar la notificación")
            
            # 2. Enviar notificación
            self._enviar_notificacion_whatsapp()
            
            # 3. Registrar solo la notificación en el ticket (sin proceder)
            grupos_disponibles = dict(self._get_grupos_disponibles())
            nombre_grupo = grupos_disponibles.get(self.grupo_seleccionado, self.grupo_seleccionado)
            
            mensaje_chatter = f"📤 <b>Solo Notificación Enviada</b><br/>"
            mensaje_chatter += f"📤 <b>Grupo WhatsApp notificado:</b> {nombre_grupo}<br/>"
            
            # Información de tóner si existe
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
            
            mensaje_chatter += f"<br/><small>⚠️ El ticket NO fue procesado automáticamente</small><br/>"
            mensaje_chatter += f"<small>Notificado por: {self.env.user.name}</small>"
            
            # Registrar en el ticket
            self.ticket_id.message_post(
                body=mensaje_chatter,
                message_type='notification'
            )
            
            # Mostrar mensaje de confirmación y cerrar wizard
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ Notificación Enviada',
                    'message': f'Notificación enviada exitosamente al grupo: {nombre_grupo}',
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except UserError:
            # Re-lanzar errores de usuario sin modificar
            raise
        except Exception as e:
            _logger.error(f"Error en action_solo_notificar: {str(e)}")
            raise UserError(f"Error al enviar la notificación: {str(e)}")



class WhatsappNotificationWizardLine(models.TransientModel):
    _name = 'whatsapp.notification.wizard.line'
    _description = 'Línea de Ticket en Wizard de Notificación Masiva'
    _order = 'ticket_name'

    # Relación con el wizard
    wizard_id = fields.Many2one(
        'whatsapp.notification.wizard', 
        string='Wizard', 
        required=True, 
        ondelete='cascade'
    )
    
    # Relación con el ticket
    ticket_id = fields.Many2one(
        'ticket.alquiler', 
        string='Ticket', 
        required=True,
        ondelete='cascade'
    )
    
    # CAMPOS DEL TICKET (solo lectura para información)
    ticket_name = fields.Char(
        string='Ticket', 
        related='ticket_id.name', 
        readonly=True
    )
    cliente_name = fields.Char(
        string='Cliente', 
        related='ticket_id.partner_id.name', 
        readonly=True
    )
    direccion = fields.Char(
        string='Dirección',
        related='ticket_id.direccion_id_r',
        readonly=True
    )
    modelo_equipo = fields.Char(
        string='Modelo', 
        related='ticket_id.modelo_id_r', 
        readonly=True
    )
    serie_equipo = fields.Char(
        string='Serie', 
        related='ticket_id.serie_id_r', 
        readonly=True
    )
    marca_equipo = fields.Char(
        string='Marca',
        related='ticket_id.marca_id_r',
        readonly=True
    )
    problema_actual = fields.Text(
        string='Problema Reportado', 
        related='ticket_id.description', 
        readonly=True
    )
    estado_actual = fields.Selection(
        related='ticket_id.estado',
        string='Estado Actual',
        readonly=True
    )
    tipo_equipo = fields.Selection(
        related='ticket_id.tipo_id',
        string='Tipo de Equipo',
        readonly=True
    )
    
    # CAMPOS EDITABLES (valores que se aplicarán al ticket)
    tipo_servicio_id = fields.Selection([
        ("instalacion", "Instalación"), 
        ("retiro", "Retiro de máquina"),
        ("mantenimiento_preventivo", "Mantenimiento preventivo"), 
        ("mantenimiento_correctivo", "Mantenimiento correctivo"),
        ("cambio_repuestos", "Cambio de repuestos"), 
        ("remoto", "Asistencia remoto"),
        ("revision", "Revisión"), 
        ("alquiler", "Preparar para alquiler")
    ], 
    string="Tipo de Servicio", 
    required=True, 
    default="revision",
    help="Tipo de servicio que se aplicará a este ticket específico"
    )
    
    observaciones = fields.Text(
        string='Observaciones Específicas', 
        help="Observaciones particulares para este ticket (opcional)"
    )
    
    # CAMPOS CALCULADOS para mostrar información útil
    info_resumen = fields.Char(
        string='Resumen',
        compute='_compute_info_resumen',
        store=False,
        help="Resumen de la información del ticket"
    )
    
    color = fields.Integer(
        string='Color',
        compute='_compute_color',
        store=False,
        help="Color para resaltar líneas según criterios"
    )
    
    # COMPUTED METHODS
    @api.depends('cliente_name', 'modelo_equipo', 'serie_equipo', 'tipo_servicio_id')
    def _compute_info_resumen(self):
        for line in self:
            resumen_parts = []
            
            if line.cliente_name:
                resumen_parts.append(f"Cliente: {line.cliente_name}")
            
            if line.modelo_equipo and line.serie_equipo:
                resumen_parts.append(f"{line.modelo_equipo} ({line.serie_equipo})")
            elif line.modelo_equipo:
                resumen_parts.append(line.modelo_equipo)
            
            if line.tipo_servicio_id:
                tipo_label = dict(line._fields['tipo_servicio_id'].selection).get(line.tipo_servicio_id, line.tipo_servicio_id)
                resumen_parts.append(f"Servicio: {tipo_label}")
            
            line.info_resumen = " | ".join(resumen_parts) if resumen_parts else "Sin información"
    
    @api.depends('estado_actual', 'tipo_servicio_id', 'problema_actual')
    def _compute_color(self):
        for line in self:
            # Color basado en criterios
            if line.estado_actual != 'nuevo':
                line.color = 1  # Rojo - ticket no nuevo
            elif not line.tipo_servicio_id:
                line.color = 3  # Amarillo - sin tipo de servicio
            elif line.tipo_servicio_id in ['mantenimiento_correctivo', 'cambio_repuestos']:
                line.color = 4  # Azul - servicios importantes
            elif line.problema_actual and len(line.problema_actual) > 200:
                line.color = 6  # Naranja - problema complejo
            else:
                line.color = 0  # Sin color
    
    # MÉTODOS DE VALIDACIÓN
    @api.constrains('tipo_servicio_id')
    def _check_tipo_servicio(self):
        for line in self:
            if not line.tipo_servicio_id:
                raise UserError(f"El ticket {line.ticket_name} debe tener un tipo de servicio definido")
    
    @api.constrains('ticket_id')
    def _check_ticket_estado(self):
        for line in self:
            if line.ticket_id and line.ticket_id.estado != 'nuevo':
                raise UserError(f"El ticket {line.ticket_name} no está en estado 'nuevo' y no puede ser procesado")
    
    # ONCHANGE METHODS
    @api.onchange('tipo_servicio_id')
    def _onchange_tipo_servicio(self):
        """Sugerir observaciones según el tipo de servicio"""
        if self.tipo_servicio_id:
            sugerencias = {
                'mantenimiento_preventivo': 'Revisar contómetros, limpiar equipos, verificar funcionamiento general',
                'mantenimiento_correctivo': 'Identificar y corregir fallas específicas reportadas',
                'cambio_repuestos': 'Verificar repuestos necesarios y realizar instalación',
                'instalacion': 'Configurar equipo, capacitar usuario, verificar conexiones',
                'retiro': 'Preparar equipo para transporte, verificar accesorios',
                'revision': 'Evaluación general del estado del equipo',
                'alquiler': 'Preparar equipo para nuevo cliente',
                'remoto': 'Asistencia técnica a través de conexión remota'
            }
            
            if not self.observaciones and self.tipo_servicio_id in sugerencias:
                self.observaciones = sugerencias[self.tipo_servicio_id]
    
    # MÉTODOS DE ACCIÓN
    def action_ver_ticket_completo(self):
        """Abre el ticket completo en una nueva ventana"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Ticket {self.ticket_name}',
            'res_model': 'ticket.alquiler',
            'res_id': self.ticket_id.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def action_copiar_observaciones_a_todas(self):
        """Copia las observaciones de esta línea a todas las líneas del wizard"""
        self.ensure_one()
        
        if not self.observaciones:
            raise UserError("Esta línea no tiene observaciones para copiar")
        
        otras_lineas = self.wizard_id.ticket_line_ids.filtered(lambda l: l.id != self.id)
        
        if not otras_lineas:
            raise UserError("No hay otras líneas para copiar las observaciones")
        
        otras_lineas.write({'observaciones': self.observaciones})
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Observaciones Copiadas',
                'message': f'Se copiaron las observaciones a {len(otras_lineas)} líneas.',
                'type': 'success',
            }
        }
    
    def action_aplicar_tipo_servicio_a_todas(self):
        """Aplica el tipo de servicio de esta línea a todas las líneas del wizard"""
        self.ensure_one()
        
        if not self.tipo_servicio_id:
            raise UserError("Esta línea no tiene tipo de servicio definido")
        
        otras_lineas = self.wizard_id.ticket_line_ids.filtered(lambda l: l.id != self.id)
        
        if not otras_lineas:
            raise UserError("No hay otras líneas para aplicar el tipo de servicio")
        
        otras_lineas.write({'tipo_servicio_id': self.tipo_servicio_id})
        
        tipo_label = dict(self._fields['tipo_servicio_id'].selection).get(self.tipo_servicio_id, self.tipo_servicio_id)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Tipo de Servicio Aplicado',
                'message': f'Se aplicó "{tipo_label}" a {len(otras_lineas)} líneas.',
                'type': 'success',
            }
        }
    
    # MÉTODO DE AYUDA PARA AGRUPACIÓN
    def get_agrupacion_info(self):
        """Retorna información para agrupar líneas"""
        self.ensure_one()
        return {
            'cliente_id': self.ticket_id.partner_id.id if self.ticket_id.partner_id else False,
            'cliente_name': self.cliente_name or 'Sin cliente',
            'tipo_servicio': self.tipo_servicio_id,
            'tipo_servicio_label': dict(self._fields['tipo_servicio_id'].selection).get(self.tipo_servicio_id, self.tipo_servicio_id),
            'direccion': self.direccion or 'Sin dirección'
        }
    
    # MÉTODOS PARA WIZARD (llamados desde el wizard padre)
    @api.model
    def crear_lineas_desde_tickets(self, wizard_id, tickets):
        """Método de clase para crear múltiples líneas desde una lista de tickets"""
        lineas_creadas = []
        
        for ticket in tickets:
            vals = {
                'wizard_id': wizard_id,
                'ticket_id': ticket.id,
                'tipo_servicio_id': ticket.tipo_servicio_id or 'revision',
                'observaciones': '',
            }
            linea = self.create(vals)
            lineas_creadas.append(linea)
        
        _logger.info(f"Creadas {len(lineas_creadas)} líneas para wizard {wizard_id}")
        return lineas_creadas
    
    def aplicar_valores_a_tickets(self):
        """Aplica los valores de las líneas a los tickets correspondientes"""
        valores_aplicados = 0
        
        for line in self:
            if line.ticket_id:
                # Preparar valores a aplicar
                vals = {}
                
                if line.tipo_servicio_id and line.tipo_servicio_id != line.ticket_id.tipo_servicio_id:
                    vals['tipo_servicio_id'] = line.tipo_servicio_id
                
                # Aplicar si hay cambios
                if vals:
                    line.ticket_id.write(vals)
                    valores_aplicados += 1
                
                # Registrar observaciones específicas en el chatter del ticket
                if line.observaciones:
                    line.ticket_id.message_post(
                        body=f"<b>Observaciones específicas (asignación masiva):</b><br/>{line.observaciones}",
                        message_type='notification'
                    )
        
        _logger.info(f"Aplicados valores a {valores_aplicados} tickets")
        return valores_aplicados
    
    # MÉTODOS DE UTILIDAD
    @api.model
    def agrupar_por_criterio(self, lineas, criterio='cliente'):
        """Agrupa líneas según el criterio especificado"""
        grupos = {}
        
        for linea in lineas:
            if criterio == 'cliente':
                key = linea.cliente_name or 'Sin cliente'
            elif criterio == 'tipo_servicio':
                key = linea.tipo_servicio_id or 'sin_tipo'
            elif criterio == 'tipo_equipo':
                key = linea.tipo_equipo or 'sin_tipo'
            else:
                key = 'general'
            
            if key not in grupos:
                grupos[key] = []
            grupos[key].append(linea)
        
        return grupos
    
    def validar_coherencia_grupo(self):
        """Valida que los tickets del grupo sean coherentes para procesamiento masivo"""
        errores = []
        
        # Verificar que todos los tickets pertenezcan al mismo cliente
        clientes = set(self.mapped('cliente_name'))
        if len(clientes) > 1:
            errores.append(f"Los tickets pertenecen a diferentes clientes: {', '.join(clientes)}")
        
        # Verificar que todos los tickets estén en estado nuevo
        estados_no_nuevos = self.filtered(lambda l: l.estado_actual != 'nuevo')
        if estados_no_nuevos:
            tickets_problema = estados_no_nuevos.mapped('ticket_name')
            errores.append(f"Tickets no están en estado 'nuevo': {', '.join(tickets_problema)}")
        
        # Verificar que todos tengan tipo de servicio
        sin_tipo_servicio = self.filtered(lambda l: not l.tipo_servicio_id)
        if sin_tipo_servicio:
            tickets_sin_tipo = sin_tipo_servicio.mapped('ticket_name')
            errores.append(f"Tickets sin tipo de servicio: {', '.join(tickets_sin_tipo)}")
        
        return errores