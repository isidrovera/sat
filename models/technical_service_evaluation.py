from odoo import models, fields, api
from datetime import datetime, timedelta
import pytz
import logging
import uuid

_logger = logging.getLogger(__name__)

class ClientServiceEvaluation(models.Model):
    _name = 'client.service.evaluation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Evaluación de Servicio Técnico'
    _order = 'evaluation_date desc'

    # ==================== CAMPOS BÁSICOS ====================
    name = fields.Char('Referencia', default='New', readonly=True, tracking=True)
    ticket_ids = fields.Many2many('ticket.alquiler', string='Tickets', tracking=True)
    ticket_id = fields.Many2one('ticket.alquiler', string='Ticket Principal', 
                                compute='_compute_ticket_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', store=True, tracking=True)
    technician_id = fields.Many2one('res.users', string='Técnico', store=True, tracking=True)
    evaluation_date = fields.Datetime('Fecha de Evaluación', default=fields.Datetime.now, tracking=True)
    expiration_date = fields.Datetime('Fecha de Expiración', compute='_compute_expiration_date', 
                                     store=True, tracking=True)
    
    state = fields.Selection([
        ('draft', 'Pendiente'),
        ('sent', 'Enviada'),
        ('completed', 'Completada'),
        ('expired', 'Expirada')
    ], default='draft', tracking=True, string='Estado')

    # ==================== CONTROL DE ENVÍO ====================
    email_sent = fields.Boolean('Correo Enviado', default=False, tracking=True)
    email_sent_date = fields.Datetime('Fecha de Envío', tracking=True)
    email_delivery_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('sent', 'Enviado'),
        ('delivered', 'Entregado'),
        ('failed', 'Fallido'),
        ('bounced', 'Rebotado')
    ], string='Estado de Entrega', default='pending', tracking=True)
    email_error_message = fields.Text('Mensaje de Error')
    reminder_count = fields.Integer('Recordatorios Enviados', default=0, tracking=True)
    last_reminder_date = fields.Datetime('Último Recordatorio')
    
    # ==================== RESPUESTA DEL CLIENTE ====================
    response_date = fields.Datetime('Fecha de Respuesta', tracking=True)
    response_time = fields.Float('Tiempo de Respuesta (horas)', 
                                 compute='_compute_response_time', store=True)
    portal_access_count = fields.Integer('Accesos al Portal', default=0)
    first_portal_access = fields.Datetime('Primer Acceso')
    last_portal_access = fields.Datetime('Último Acceso')
    
    # ==================== AUDITORÍA ====================
    completed_by = fields.Many2one('res.users', string='Completado Por', tracking=True)
    ip_address = fields.Char('Dirección IP')
    user_agent = fields.Char('Navegador/Dispositivo')
    completion_source = fields.Selection([
        ('portal', 'Portal Web'),
        ('email', 'Desde Correo'),
        ('manual', 'Manual'),
        ('system', 'Sistema')
    ], string='Fuente de Completado', tracking=True)
    
    # ==================== MÉTRICAS ====================
    days_to_complete = fields.Integer('Días para Completar', 
                                      compute='_compute_days_to_complete', store=True)
    is_on_time = fields.Boolean('Respondió a Tiempo', 
                                compute='_compute_is_on_time', store=True)
    notification_channel = fields.Selection([
        ('email', 'Correo Electrónico'),
        ('whatsapp', 'WhatsApp'),
        ('sms', 'SMS'),
        ('multiple', 'Múltiples Canales')
    ], string='Canal de Notificación', default='email')

    # ==================== ASPECTOS DE EVALUACIÓN ====================
    saludo_presentacion = fields.Selection([
        ('1', 'No saludó ni se presentó'),
        ('2', 'Saludo y presentación básica'),
        ('3', 'Saludo correcto y profesional'),
        ('4', 'Saludo profesional y actitud positiva'),
        ('5', 'Saludo excelente, mostró cortesía y empatía')
    ], string='¿Cómo califica el saludo y presentación del técnico?', tracking=True)

    diagnostico_problema = fields.Selection([
        ('1', 'Malo'),
        ('2', 'Regular'),
        ('3', 'Bueno'),
        ('4', 'Muy Bueno'),
        ('5', 'Excelente')
    ], string='¿Cómo califica la revisión del problema?', tracking=True)

    solucion_problema = fields.Selection([
        ('1', 'Malo'),
        ('2', 'Regular'),
        ('3', 'Bueno'),
        ('4', 'Muy Bueno'),
        ('5', 'Excelente')
    ], string='¿Cómo califica la solución brindada?', tracking=True)

    explicacion_trabajo = fields.Selection([
        ('1', 'Malo'),
        ('2', 'Regular'),
        ('3', 'Bueno'),
        ('4', 'Muy Bueno'),
        ('5', 'Excelente')
    ], string='¿Cómo califica la explicación del trabajo realizado?', tracking=True)

    limpieza_orden = fields.Selection([
        ('1', 'Malo'),
        ('2', 'Regular'),
        ('3', 'Bueno'),
        ('4', 'Muy Bueno'),
        ('5', 'Excelente')
    ], string='¿Cómo califica la limpieza y orden después del servicio?', tracking=True)

    revision_adicional = fields.Selection([
        ('1', 'No revisó otros equipos ni consultó sobre más impresoras'),
        ('2', 'Revisión básica - Solo preguntó si había más equipos'),
        ('3', 'Bueno - Verificó estado básico de otros equipos'),
        ('4', 'Muy Bueno - Revisó estado y funcionamiento de equipos adicionales'),
        ('5', 'Excelente - Revisión completa de todos los equipos e impresoras, verificó operatividad')
    ], string='¿Realizó revisión de equipos adicionales?', tracking=True)
    
    retiro_tecnico = fields.Selection([
        ('con_visto', 'Con Visto Bueno'),
        ('sin_visto', 'Sin Visto Bueno'),
        ('sin_aviso', 'Se Retiró Sin Avisar')
    ], string='Conformidad de Retiro', tracking=True, required=True)
    
    # ==================== PREGUNTAS ESPECÍFICAS ====================
    realizo_pruebas = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No')
    ], string='¿Realizó pruebas del equipo?', tracking=True)

    consulto_suministros = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No')
    ], string='¿Consultó sobre el stock de suministros?', tracking=True)

    consulto_problemas = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No')
    ], string='¿Preguntó si había problemas adicionales?', tracking=True)

    # ==================== CAMPOS ADICIONALES ====================
    comentarios = fields.Text('Comentarios o Sugerencias', tracking=True)
    token = fields.Char('Token de Evaluación', copy=False)

    # ==================== CAMPOS CALCULADOS ====================
    puntaje_servicio = fields.Float('Puntaje del Servicio (%)', 
                                    compute='_compute_puntaje', store=True, tracking=True)
    nivel_atencion = fields.Selection([
        ('excelente', 'Excelente (90-100%)'),
        ('bueno', 'Bueno (80-89%)'),
        ('regular', 'Regular (70-79%)'),
        ('deficiente', 'Deficiente (<70%)')
    ], compute='_compute_niveles', store=True, tracking=True, string='Nivel de Atención')

    requiere_atencion = fields.Boolean('Requiere Atención', 
                                       compute='_compute_requiere_atencion', store=True)
    analisis_detallado = fields.Text('Análisis Detallado', compute='_compute_analisis', store=True)
    recomendaciones_mejora = fields.Text('Recomendaciones de Mejora', 
                                         compute='_compute_recomendaciones', store=True)
    
    color = fields.Integer(string='Índice de Color', compute='_compute_color', store=True)

    # ==================== MÉTODOS CREATE Y WRITE ====================
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('client.service.evaluation') or 'New'
        if not vals.get('token'):
            vals['token'] = self._generate_token()
        
        record = super(ClientServiceEvaluation, self).create(vals)
        
        # Mensaje de creación en el chatter
        record.message_post(
            body=f"""<p><strong>📋 Evaluación de Servicio Creada</strong></p>
                    <ul>
                        <li><strong>Cliente:</strong> {record.partner_id.name}</li>
                        <li><strong>Técnico:</strong> {record.technician_id.name}</li>
                        <li><strong>Tickets:</strong> {len(record.ticket_ids)} ticket(s)</li>
                        <li><strong>Fecha:</strong> {record.evaluation_date.strftime('%d/%m/%Y %H:%M')}</li>
                    </ul>""",
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )
        
        return record

    def write(self, vals):
        # Registrar cambios importantes en el chatter
        for record in self:
            old_state = record.state
            
            result = super(ClientServiceEvaluation, self).write(vals)
            
            # Notificar cambio de estado
            if 'state' in vals and vals['state'] != old_state:
                record._notify_state_change(old_state, vals['state'])
            
            # Notificar cuando se completa
            if 'state' in vals and vals['state'] == 'completed':
                record._notify_completion()
            
            return result
        
        return super(ClientServiceEvaluation, self).write(vals)

    # ==================== MÉTODOS COMPUTE ====================
    @api.depends('ticket_ids')
    def _compute_ticket_id(self):
        """Compute para mantener compatibilidad con la plantilla de correo"""
        for record in self:
            record.ticket_id = record.ticket_ids[0] if record.ticket_ids else False

    @api.depends('evaluation_date')
    def _compute_expiration_date(self):
        for record in self:
            if record.evaluation_date:
                record.expiration_date = record.evaluation_date + timedelta(days=2)
            else:
                record.expiration_date = False

    @api.depends('email_sent_date', 'response_date')
    def _compute_response_time(self):
        for record in self:
            if record.email_sent_date and record.response_date:
                delta = record.response_date - record.email_sent_date
                record.response_time = delta.total_seconds() / 3600  # Convertir a horas
            else:
                record.response_time = 0.0

    @api.depends('evaluation_date', 'response_date')
    def _compute_days_to_complete(self):
        for record in self:
            if record.evaluation_date and record.response_date:
                delta = record.response_date - record.evaluation_date
                record.days_to_complete = delta.days
            else:
                record.days_to_complete = 0

    @api.depends('response_date', 'expiration_date')
    def _compute_is_on_time(self):
        for record in self:
            if record.response_date and record.expiration_date:
                record.is_on_time = record.response_date <= record.expiration_date
            else:
                record.is_on_time = False

    @api.depends('saludo_presentacion', 'diagnostico_problema', 'solucion_problema',
            'explicacion_trabajo', 'limpieza_orden', 'revision_adicional', 'retiro_tecnico')
    def _compute_puntaje(self):
        for record in self:
            scores = []
            fields_to_evaluate = [
                'saludo_presentacion', 'diagnostico_problema', 'solucion_problema',
                'explicacion_trabajo', 'limpieza_orden', 'revision_adicional'
            ]
            
            # Calcular puntos de aspectos evaluados
            for field in fields_to_evaluate:
                value = getattr(record, field)
                if value and value.isdigit():
                    scores.append(int(value))
            
            # Factor de ajuste según el tipo de retiro
            retiro_factor = 1.0
            if record.retiro_tecnico == 'sin_visto':
                retiro_factor = 0.8  # Reduce 20% si no obtuvo visto bueno
            elif record.retiro_tecnico == 'sin_aviso':
                retiro_factor = 0.5  # Reduce 50% si se retiró sin avisar
            
            if scores:
                base_score = (sum(scores) / (len(scores) * 5)) * 100
                record.puntaje_servicio = base_score * retiro_factor
            else:
                record.puntaje_servicio = 0

    @api.depends('puntaje_servicio')
    def _compute_niveles(self):
        for record in self:
            if record.puntaje_servicio >= 90:
                record.nivel_atencion = 'excelente'
            elif record.puntaje_servicio >= 80:
                record.nivel_atencion = 'bueno'
            elif record.puntaje_servicio >= 70:
                record.nivel_atencion = 'regular'
            else:
                record.nivel_atencion = 'deficiente'

    @api.depends('puntaje_servicio', 'realizo_pruebas', 'consulto_suministros', 'consulto_problemas')
    def _compute_requiere_atencion(self):
        for record in self:
            record.requiere_atencion = (
                record.puntaje_servicio < 70 or
                record.realizo_pruebas == 'no' or
                record.consulto_suministros == 'no' or
                record.consulto_problemas == 'no'
            )

    @api.depends('state', 'nivel_atencion', 'requiere_atencion')
    def _compute_color(self):
        """Calcula el color de la evaluación basado en su estado y puntaje"""
        for record in self:
            if record.state == 'draft':
                record.color = 0  # Gris - Borrador
            elif record.state == 'sent':
                record.color = 4  # Azul - Enviada
            elif record.state == 'expired':
                record.color = 1  # Rojo - Expirada
            elif record.state == 'completed':
                if record.nivel_atencion == 'excelente':
                    record.color = 10  # Verde - Excelente
                elif record.nivel_atencion == 'bueno':
                    record.color = 3  # Amarillo - Bueno
                elif record.nivel_atencion == 'regular':
                    record.color = 5  # Naranja - Regular
                else:
                    record.color = 1  # Rojo - Deficiente
            else:
                record.color = 0

    @api.depends('saludo_presentacion', 'diagnostico_problema', 'solucion_problema',
            'explicacion_trabajo', 'limpieza_orden', 'revision_adicional',
            'realizo_pruebas', 'consulto_suministros', 'consulto_problemas',
            'technician_id', 'ticket_ids', 'retiro_tecnico')
    def _compute_analisis(self):
        for record in self:
            analisis = []
            
            # Análisis por área
            areas = {
                'Atención Inicial': int(record.saludo_presentacion or '0'),
                'Diagnóstico': int(record.diagnostico_problema or '0'),
                'Solución': int(record.solucion_problema or '0'),
                'Explicación': int(record.explicacion_trabajo or '0'),
                'Limpieza': int(record.limpieza_orden or '0'),
                'Revisión Adicional': int(record.revision_adicional or '0')
            }

            # Encabezado con información del técnico y tickets
            analisis.append(f"ANÁLISIS DE SERVICIO")
            analisis.append(f"Técnico: {record.technician_id.name}")
            analisis.append(f"Cliente: {record.partner_id.name}")
            analisis.append(f"Puntaje General: {record.puntaje_servicio:.1f}%")
            
            # Detalle de tickets atendidos
            analisis.append("\nEQUIPOS ATENDIDOS:")
            for ticket in record.ticket_ids:
                analisis.append(f"- Ticket: {ticket.name}")
                if hasattr(ticket, 'product_alquiler') and ticket.product_alquiler:
                    analisis.append(f"  Equipo: {ticket.product_alquiler.display_name}")
                analisis.append(f"  Servicio: {ticket.tipo_servicio if hasattr(ticket, 'tipo_servicio') else 'N/A'}")

            # Información de retiro del técnico
            retiro_texto = {
                'con_visto': '✓ Se retiró con visto bueno del cliente',
                'sin_visto': '⚠ Se retiró sin obtener visto bueno',
                'sin_aviso': '✗ Se retiró sin avisar al cliente'
            }
            analisis.append(f"\nCONFORMIDAD DE RETIRO:")
            analisis.append(retiro_texto.get(record.retiro_tecnico, 'No especificado'))
            
            if record.retiro_tecnico in ['sin_visto', 'sin_aviso']:
                analisis.append("⚠ El puntaje ha sido ajustado debido a la falta de conformidad en el retiro")

            analisis.append("\nDESGLOSE POR ÁREAS:")
            for area, puntaje in areas.items():
                porcentaje = (puntaje / 5) * 100
                nivel = "✓ Excelente" if porcentaje >= 90 else \
                    "✓ Bueno" if porcentaje >= 80 else \
                    "⚠ Regular" if porcentaje >= 70 else \
                    "✗ Deficiente"
                analisis.append(f"{area}: {porcentaje:.1f}% - {nivel}")

            analisis.append("\nCUMPLIMIENTO DE PROTOCOLO:")
            protocolos = {
                'Pruebas del equipo': record.realizo_pruebas == 'si',
                'Verificación de suministros': record.consulto_suministros == 'si',
                'Consulta de problemas adicionales': record.consulto_problemas == 'si'
            }

            for protocolo, cumplido in protocolos.items():
                analisis.append(f"{'✓' if cumplido else '✗'} {protocolo}")

            # Información de respuesta
            if record.response_date:
                analisis.append(f"\nTIEMPO DE RESPUESTA:")
                analisis.append(f"Respondió en: {record.response_time:.1f} horas")
                analisis.append(f"{'✓ A tiempo' if record.is_on_time else '✗ Fuera de tiempo'}")

            # Nota adicional sobre el impacto en la calificación
            if record.retiro_tecnico == 'sin_visto':
                analisis.append("\nNOTA: La calificación final ha sido reducida en 20% por falta de visto bueno del cliente")
            elif record.retiro_tecnico == 'sin_aviso':
                analisis.append("\nNOTA: La calificación final ha sido reducida en 50% por retiro sin aviso")

            record.analisis_detallado = '\n'.join(analisis)

    @api.depends('analisis_detallado', 'puntaje_servicio', 'nivel_atencion')
    def _compute_recomendaciones(self):
        for record in self:
            recomendaciones = ["RECOMENDACIONES DE MEJORA:"]

            # Recomendaciones específicas según puntuación
            if int(record.saludo_presentacion or '0') <= 3:
                recomendaciones.append("""
- Protocolo de Atención:
  - Mejorar saludo inicial
  - Presentarse adecuadamente
  - Explicar el proceso a realizar""")

            if int(record.diagnostico_problema or '0') <= 3:
                recomendaciones.append("""
- Diagnóstico:
  - Realizar revisión más detallada
  - Documentar los problemas encontrados
  - Explicar el diagnóstico al cliente""")

            if int(record.solucion_problema or '0') <= 3:
                recomendaciones.append("""
- Solución Técnica:
  - Asegurar solución completa
  - Verificar funcionamiento
  - Documentar la solución aplicada""")

            if int(record.explicacion_trabajo or '0') <= 3:
                recomendaciones.append("""
- Comunicación:
  - Mejorar explicación del servicio
  - Usar lenguaje comprensible
  - Verificar entendimiento del cliente""")

            if int(record.limpieza_orden or '0') <= 3:
                recomendaciones.append("""
- Limpieza:
  - Mejorar orden del área
  - Limpiar equipo después del servicio
  - Verificar área de trabajo""")

            if record.realizo_pruebas == 'no':
                recomendaciones.append("""
- Pruebas:
  - Implementar protocolo de pruebas
  - Realizar pruebas con cliente
  - Documentar resultados""")

            if record.consulto_suministros == 'no':
                recomendaciones.append("""
- Suministros:
  - Verificar stock de consumibles
  - Registrar necesidades
  - Informar al cliente""")

            if record.consulto_problemas == 'no':
                recomendaciones.append("""
- Revisión General:
  - Consultar problemas adicionales
  - Revisar otros equipos
  - Ofrecer mantenimiento preventivo""")

            # Recomendación general basada en puntaje total
            if record.puntaje_servicio < 70:
                recomendaciones.insert(1, """
ACCIONES URGENTES:
- Capacitación inmediata en:
  - Protocolos de servicio
  - Atención al cliente
  - Habilidades técnicas
- Seguimiento semanal
- Supervisión directa""")

            record.recomendaciones_mejora = '\n'.join(recomendaciones)

    # ==================== MÉTODOS AUXILIARES ====================
    def _generate_token(self):
        """Genera un token único para la evaluación"""
        return str(uuid.uuid4())

    def _notify_state_change(self, old_state, new_state):
        """Notifica cambios de estado en el chatter"""
        self.ensure_one()
        
        state_labels = {
            'draft': 'Pendiente',
            'sent': 'Enviada',
            'completed': 'Completada',
            'expired': 'Expirada'
        }
        
        state_icons = {
            'draft': '📝',
            'sent': '📧',
            'completed': '✅',
            'expired': '⏰'
        }
        
        message = f"""<p>{state_icons.get(new_state, '📋')} <strong>Estado Actualizado</strong></p>
                     <p>De: <span class="badge badge-info">{state_labels.get(old_state, old_state)}</span> 
                     → A: <span class="badge badge-success">{state_labels.get(new_state, new_state)}</span></p>"""
        
        self.message_post(
            body=message,
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )

    def _notify_completion(self):
        """Notifica cuando se completa la evaluación"""
        self.ensure_one()
        
        nivel_colors = {
            'excelente': 'success',
            'bueno': 'info',
            'regular': 'warning',
            'deficiente': 'danger'
        }
        
        nivel_icons = {
            'excelente': '🌟',
            'bueno': '👍',
            'regular': '⚠️',
            'deficiente': '❌'
        }
        
        message = f"""<p>✅ <strong>Evaluación Completada</strong></p>
                     <ul>
                         <li><strong>Puntaje:</strong> {self.puntaje_servicio:.1f}%</li>
                         <li><strong>Nivel:</strong> 
                             <span class="badge badge-{nivel_colors.get(self.nivel_atencion, 'secondary')}">
                                 {nivel_icons.get(self.nivel_atencion, '')} {dict(self._fields['nivel_atencion'].selection).get(self.nivel_atencion)}
                             </span>
                         </li>
                         <li><strong>Tiempo de respuesta:</strong> {self.response_time:.1f} horas</li>
                         <li><strong>Respondió:</strong> {'✓ A tiempo' if self.is_on_time else '✗ Fuera de tiempo'}</li>
                     </ul>"""
        
        if self.comentarios:
            message += f"<p><strong>Comentarios del cliente:</strong><br/>{self.comentarios}</p>"
        
        self.message_post(
            body=message,
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )
        
        # Notificar al técnico sobre su evaluación
        if self.technician_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=self.technician_id.id,
                summary=f'Tu evaluación de servicio ha sido completada - {self.puntaje_servicio:.1f}%',
                note=f"""El cliente {self.partner_id.name} ha completado tu evaluación de servicio.
                        Puntaje obtenido: {self.puntaje_servicio:.1f}%
                        Nivel: {dict(self._fields['nivel_atencion'].selection).get(self.nivel_atencion)}"""
            )
        
        # Alertar a supervisión si requiere atención
        if self.requiere_atencion:
            self._notify_supervisor_attention()

    def _notify_supervisor_attention(self):
        """Notifica al supervisor cuando una evaluación requiere atención"""
        self.ensure_one()
        
        # Buscar usuarios del grupo de supervisores (ajustar según tu configuración)
        supervisor_group = self.env.ref('sat.group_sat_supervisor', raise_if_not_found=False)
        if supervisor_group:
            for supervisor in supervisor_group.users:
                self.activity_schedule(
                    'mail.mail_activity_data_warning',
                    user_id=supervisor.id,
                    summary=f'⚠️ Evaluación deficiente requiere atención - {self.technician_id.name}',
                    note=f"""Una evaluación de servicio requiere atención inmediata:
                            
                            Técnico: {self.technician_id.name}
                            Cliente: {self.partner_id.name}
                            Puntaje: {self.puntaje_servicio:.1f}%
                            
                            Motivos de alerta:
                            - {'Puntaje bajo (<70%)' if self.puntaje_servicio < 70 else ''}
                            - {'No realizó pruebas' if self.realizo_pruebas == 'no' else ''}
                            - {'No consultó suministros' if self.consulto_suministros == 'no' else ''}
                            - {'No consultó problemas adicionales' if self.consulto_problemas == 'no' else ''}"""
                )

    def _register_portal_access(self, request=None):
        """Registra el acceso al portal por parte del cliente"""
        self.ensure_one()
        
        current_time = fields.Datetime.now()
        vals = {
            'portal_access_count': self.portal_access_count + 1,
            'last_portal_access': current_time
        }
        
        if not self.first_portal_access:
            vals['first_portal_access'] = current_time
        
        # Capturar información de la solicitud si está disponible
        if request:
            vals['ip_address'] = request.httprequest.environ.get('REMOTE_ADDR')
            vals['user_agent'] = request.httprequest.environ.get('HTTP_USER_AGENT')
        
        self.write(vals)
        
        # Registrar en el chatter
        access_number = self.portal_access_count
        message = f"""<p>👁️ <strong>Acceso al Portal</strong></p>
                     <ul>
                         <li><strong>Acceso #{access_number}</strong></li>
                         <li><strong>Fecha:</strong> {current_time.strftime('%d/%m/%Y %H:%M')}</li>
                     </ul>"""
        
        if self.ip_address:
            message += f"<ul><li><strong>IP:</strong> {self.ip_address}</li></ul>"
        
        self.message_post(
            body=message,
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )

    # ==================== ACCIONES ====================
    def action_view_tickets(self):
        """Método para ver los tickets relacionados"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tickets',
            'view_mode': 'list,form',
            'res_model': 'ticket.alquiler',
            'domain': [('id', 'in', self.ticket_ids.ids)],
            'target': 'current',
        }

    def _get_portal_return_action(self):
        """Método para retornar la acción del portal"""
        return {
            'type': 'ir.actions.act_url',
            'url': '/my/evaluations/%s' % self.id,
            'target': 'self',
            'res_id': self.id,
        }

    def action_mark_as_completed(self):
        """Método para marcar como completada la evaluación"""
        self.ensure_one()
        
        vals = {
            'state': 'completed',
            'response_date': fields.Datetime.now()
        }
        
        if not self.completed_by:
            vals['completed_by'] = self.env.user.id
        
        if not self.completion_source:
            vals['completion_source'] = 'manual'
        
        self.write(vals)
        
        return True

    def action_reset_to_draft(self):
        """Método para regresar a borrador la evaluación"""
        self.ensure_one()
        
        self.write({'state': 'draft'})
        
        self.message_post(
            body="<p>🔄 <strong>Evaluación regresada a borrador</strong></p>",
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )
        
        return True

    def action_send_reminder(self):
        """Método para enviar recordatorio de evaluación"""
        self.ensure_one()
        
        template = self.env.ref('sat.email_template_service_evaluation_reminder', False)
        if template:
            try:
                template.send_mail(self.id, force_send=True)
                
                # Actualizar contadores y fechas
                self.write({
                    'reminder_count': self.reminder_count + 1,
                    'last_reminder_date': fields.Datetime.now()
                })
                
                # Registrar en el chatter
                self.message_post(
                    body=f"""<p>🔔 <strong>Recordatorio Enviado</strong></p>
                            <ul>
                                <li><strong>Recordatorio #{self.reminder_count}</strong></li>
                                <li><strong>Enviado a:</strong> {self.partner_id.email}</li>
                                <li><strong>Fecha:</strong> {fields.Datetime.now().strftime('%d/%m/%Y %H:%M')}</li>
                            </ul>""",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
                
                return True
            except Exception as e:
                _logger.error(f"Error al enviar recordatorio para evaluación {self.name}: {str(e)}")
                
                self.message_post(
                    body=f"""<p>❌ <strong>Error al Enviar Recordatorio</strong></p>
                            <p>Error: {str(e)}</p>""",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
                
                return False
        
        return False

    def action_resend_evaluation(self):
        """Método para reenviar la evaluación"""
        self.ensure_one()
        
        template = self.env.ref('sat.email_template_service_evaluation', False)
        if template:
            try:
                template.send_mail(self.id, force_send=True)
                
                # Actualizar campos de envío
                self.write({
                    'email_sent': True,
                    'email_sent_date': fields.Datetime.now(),
                    'email_delivery_status': 'sent',
                    'state': 'sent'
                })
                
                # Registrar en el chatter
                self.message_post(
                    body=f"""<p>📧 <strong>Evaluación Reenviada</strong></p>
                            <ul>
                                <li><strong>Enviado a:</strong> {self.partner_id.email}</li>
                                <li><strong>Fecha:</strong> {fields.Datetime.now().strftime('%d/%m/%Y %H:%M')}</li>
                            </ul>""",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
                
                return True
            except Exception as e:
                _logger.error(f"Error al reenviar evaluación {self.name}: {str(e)}")
                
                self.write({
                    'email_delivery_status': 'failed',
                    'email_error_message': str(e)
                })
                
                self.message_post(
                    body=f"""<p>❌ <strong>Error al Reenviar Evaluación</strong></p>
                            <p>Error: {str(e)}</p>""",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
                
                return False
        
        return False

    # ==================== CRON JOBS ====================
    @api.model
    def _cron_check_expired_evaluations(self):
        """Cron para marcar evaluaciones expiradas"""
        _logger.info("🕐 Verificando evaluaciones expiradas...")
        
        try:
            current_datetime = fields.Datetime.now()
            domain = [
                ('state', '=', 'sent'),
                ('expiration_date', '<', current_datetime)
            ]
            
            expired_evaluations = self.search(domain)
            
            if expired_evaluations:
                for evaluation in expired_evaluations:
                    evaluation.write({'state': 'expired'})
                    
                    # Notificar en el chatter
                    evaluation.message_post(
                        body=f"""<p>⏰ <strong>Evaluación Expirada</strong></p>
                                <ul>
                                    <li><strong>Fecha de expiración:</strong> {evaluation.expiration_date.strftime('%d/%m/%Y %H:%M')}</li>
                                    <li><strong>Accesos al portal:</strong> {evaluation.portal_access_count}</li>
                                    <li><strong>Recordatorios enviados:</strong> {evaluation.reminder_count}</li>
                                </ul>""",
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )
                    
                    # Notificar al técnico
                    if evaluation.technician_id:
                        evaluation.activity_schedule(
                            'mail.mail_activity_data_todo',
                            user_id=evaluation.technician_id.id,
                            summary='Evaluación de servicio expirada',
                            note=f"""La evaluación del cliente {evaluation.partner_id.name} ha expirado sin ser completada.
                                    Se recomienda hacer seguimiento directo con el cliente."""
                        )
                
                _logger.info(f"✅ Se marcaron {len(expired_evaluations)} evaluaciones como expiradas")
            else:
                _logger.info("✅ No hay evaluaciones expiradas")
                
        except Exception as e:
            _logger.error(f"❌ Error en cron de evaluaciones expiradas: {str(e)}")
            raise

    @api.model
    def _cron_send_service_evaluations(self):
        """Cron para enviar evaluaciones a las 8 PM"""
        _logger.info("📧 Iniciando envío de evaluaciones de servicio...")
        
        try:
            tz = pytz.timezone('America/Lima')
            now = datetime.now(tz)
            today = now.date()
            
            # Buscar tickets finalizados con agenda de hoy
            domain = [
                ('estado', '=', 'finalizado'),
                ('agenda', '>=', datetime.combine(today, datetime.min.time())),
                ('agenda', '<=', datetime.combine(today, datetime.max.time())),
                ('partner_id', '!=', False),
                ('responsable', '!=', False)
            ]
            
            tickets = self.env['ticket.alquiler'].search(domain)
            _logger.info(f"🎫 Se encontraron {len(tickets)} tickets para evaluar")

            # Agrupar tickets por técnico y cliente
            grouped_tickets = {}
            for ticket in tickets:
                key = (ticket.partner_id.id, ticket.responsable.id)
                if key not in grouped_tickets:
                    grouped_tickets[key] = []
                grouped_tickets[key].append(ticket.id)

            sent_count = 0
            error_count = 0

            # Procesar cada grupo (técnico-cliente) una sola vez
            for (partner_id, technician_id), ticket_ids in grouped_tickets.items():
                # Verificar si ya existe una evaluación para este técnico y cliente hoy
                existing_eval = self.search([
                    ('partner_id', '=', partner_id),
                    ('technician_id', '=', technician_id),
                    ('evaluation_date', '>=', datetime.combine(today, datetime.min.time())),
                    ('evaluation_date', '<=', datetime.combine(today, datetime.max.time()))
                ], limit=1)

                if not existing_eval:
                    try:
                        partner = self.env['res.partner'].browse(partner_id)
                        technician = self.env['res.users'].browse(technician_id)
                        
                        # Crear una única evaluación por técnico y cliente
                        evaluation = self.create({
                            'ticket_ids': [(6, 0, ticket_ids)],
                            'partner_id': partner_id,
                            'technician_id': technician_id,
                            'state': 'draft',
                            'retiro_tecnico': 'con_visto',
                        })
                        
                        _logger.info(
                            f"📋 Evaluación creada #{evaluation.name} - "
                            f"Cliente: {partner.name}, "
                            f"Técnico: {technician.name}, "
                            f"Tickets: {len(ticket_ids)}"
                        )
                        
                        # Registrar en el chatter la creación
                        evaluation.message_post(
                            body=f"""<p>🤖 <strong>Evaluación Creada Automáticamente</strong></p>
                                    <ul>
                                        <li><strong>Cliente:</strong> {partner.name}</li>
                                        <li><strong>Técnico:</strong> {technician.name}</li>
                                        <li><strong>Tickets procesados:</strong> {len(ticket_ids)}</li>
                                        <li><strong>Fecha:</strong> {now.strftime('%d/%m/%Y %H:%M')}</li>
                                    </ul>""",
                            message_type='notification',
                            subtype_xmlid='mail.mt_note'
                        )
                        
                        # Enviar correo
                        template = self.env.ref('sat.email_template_service_evaluation', False)
                        if template:
                            try:
                                template.send_mail(evaluation.id, force_send=True)
                                
                                # Actualizar estado y campos de envío
                                evaluation.write({
                                    'state': 'sent',
                                    'email_sent': True,
                                    'email_sent_date': fields.Datetime.now(),
                                    'email_delivery_status': 'sent'
                                })
                                
                                # Registrar envío exitoso en el chatter
                                evaluation.message_post(
                                    body=f"""<p>✅ <strong>Correo Enviado Exitosamente</strong></p>
                                            <ul>
                                                <li><strong>Destinatario:</strong> {partner.email}</li>
                                                <li><strong>Fecha de envío:</strong> {fields.Datetime.now().strftime('%d/%m/%Y %H:%M')}</li>
                                                <li><strong>Estado:</strong> Enviado</li>
                                            </ul>""",
                                    message_type='notification',
                                    subtype_xmlid='mail.mt_note'
                                )
                                
                                _logger.info(f"✅ Correo enviado exitosamente para evaluación: {evaluation.name}")
                                sent_count += 1
                                
                            except Exception as email_error:
                                error_msg = str(email_error)
                                _logger.error(f"❌ Error al enviar correo para {evaluation.name}: {error_msg}")
                                
                                evaluation.write({
                                    'email_delivery_status': 'failed',
                                    'email_error_message': error_msg
                                })
                                
                                # Registrar error en el chatter
                                evaluation.message_post(
                                    body=f"""<p>❌ <strong>Error al Enviar Correo</strong></p>
                                            <ul>
                                                <li><strong>Error:</strong> {error_msg}</li>
                                                <li><strong>Fecha:</strong> {fields.Datetime.now().strftime('%d/%m/%Y %H:%M')}</li>
                                            </ul>""",
                                    message_type='notification',
                                    subtype_xmlid='mail.mt_note'
                                )
                                error_count += 1
                        else:
                            _logger.warning("⚠️ No se encontró la plantilla de correo para evaluación")
                            evaluation.write({
                                'email_delivery_status': 'failed',
                                'email_error_message': 'Plantilla de correo no encontrada'
                            })
                            error_count += 1
                            
                        self.env.cr.commit()  # Commit después de cada evaluación
                        
                    except Exception as e:
                        error_msg = str(e)
                        self.env.cr.rollback()
                        _logger.error(
                            f"❌ Error al procesar evaluación - "
                            f"Cliente: {partner_id}, "
                            f"Técnico: {technician_id}: {error_msg}"
                        )
                        error_count += 1
                else:
                    _logger.info(
                        f"⏭️ Ya existe evaluación para Cliente: {partner_id}, "
                        f"Técnico: {technician_id} hoy"
                    )
            
            _logger.info(
                f"📊 Resumen de envío: "
                f"Enviadas: {sent_count}, "
                f"Errores: {error_count}, "
                f"Total grupos procesados: {len(grouped_tickets)}"
            )
            
        except Exception as e:
            self.env.cr.rollback()
            _logger.error(f"❌ Error general en el cron de evaluaciones: {str(e)}")
            raise

    @api.model
    def _cron_send_pending_reminders(self):
        """Cron para enviar recordatorios automáticos de evaluaciones pendientes"""
        _logger.info("🔔 Iniciando envío de recordatorios automáticos...")
        
        try:
            # Buscar evaluaciones enviadas hace 24 horas que no han sido completadas
            yesterday = fields.Datetime.now() - timedelta(hours=24)
            domain = [
                ('state', '=', 'sent'),
                ('email_sent_date', '<=', yesterday),
                ('reminder_count', '<', 2),  # Máximo 2 recordatorios
                ('expiration_date', '>', fields.Datetime.now())  # No expiradas
            ]
            
            pending_evaluations = self.search(domain)
            
            sent_count = 0
            for evaluation in pending_evaluations:
                try:
                    if evaluation.action_send_reminder():
                        sent_count += 1
                    self.env.cr.commit()
                except Exception as e:
                    self.env.cr.rollback()
                    _logger.error(f"Error al enviar recordatorio para {evaluation.name}: {str(e)}")
            
            _logger.info(f"✅ Se enviaron {sent_count} recordatorios de {len(pending_evaluations)} evaluaciones pendientes")
            
        except Exception as e:
            _logger.error(f"❌ Error en cron de recordatorios: {str(e)}")
            raise