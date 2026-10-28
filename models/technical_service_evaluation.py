from odoo import models, fields, api
from datetime import datetime, timedelta, time
import json
import pytz
import logging
import re
import requests
import uuid

_logger = logging.getLogger(__name__)


class ClientServiceEvaluation(models.Model):
    _name = 'client.service.evaluation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Evaluación de Servicio Técnico'
    _order = 'evaluation_date desc'

    # Campos de calificación que componen el puntaje.
    # Se mantienen TODOS los nombres históricos para no romper datos previos
    # ni integraciones (evaluacion.personal). Las evaluaciones nuevas solo
    # llenan 'solucion_problema' y 'explicacion_trabajo'; el puntaje promedia
    # únicamente los campos respondidos, por lo que registros antiguos y
    # nuevos conviven sin recálculos incorrectos.
    RATING_FIELDS = [
        'saludo_presentacion',      # LEGADO - ya no se pregunta
        'diagnostico_problema',     # LEGADO - fusionado en solucion_problema
        'solucion_problema',        # ACTIVO - fusión de revisión + solución
        'explicacion_trabajo',      # ACTIVO - fusión de explicación + limpieza
        'limpieza_orden',           # LEGADO - fusionado en explicacion_trabajo
        'revision_adicional',       # LEGADO - ya no se pregunta
    ]

    # ==================== CAMPOS BÁSICOS ====================
    name = fields.Char('Referencia', default='New', readonly=True, tracking=True)

    ticket_ids = fields.Many2many(
        'ticket.alquiler',
        string='Tickets',
        tracking=True
    )

    ticket_id = fields.Many2one(
        'ticket.alquiler',
        string='Ticket Principal',
        compute='_compute_ticket_id',
        store=True
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        store=True,
        tracking=True
    )

    technician_id = fields.Many2one(
        'res.users',
        string='Técnico',
        store=True,
        tracking=True
    )

    # ==================== PERSONA QUE EVALÚA / VISTO BUENO ====================
    evaluator_contact_id = fields.Many2one(
        'res.partner',
        string='Persona que dio conformidad',
        tracking=True,
        index=True,
        copy=False,
        help=(
            'Contacto de la empresa que recibió el servicio y dio conformidad. '
            'En evaluaciones nuevas se toma del visto bueno del ticket.'
        )
    )

    evaluator_name = fields.Char(
        string='Nombre del evaluador',
        tracking=True,
        copy=False
    )

    evaluator_dni = fields.Char(
        string='DNI del evaluador',
        tracking=True,
        copy=False,
        index=True
    )

    evaluator_mobile = fields.Char(
        string='Celular del evaluador',
        tracking=True,
        copy=False
    )

    evaluator_email = fields.Char(
        string='Correo del evaluador',
        tracking=True,
        copy=False
    )

    evaluation_date = fields.Datetime(
        'Fecha de Evaluación',
        default=fields.Datetime.now,
        tracking=True
    )

    expiration_date = fields.Datetime(
        'Fecha de Expiración',
        compute='_compute_expiration_date',
        store=True,
        tracking=True
    )

    visit_date = fields.Date(
        'Fecha de Visita',
        tracking=True,
        help='Fecha real de la visita técnica asociada al ticket evaluado.'
    )

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

    whatsapp_sent = fields.Boolean('WhatsApp Enviado', default=False, tracking=True)
    whatsapp_sent_date = fields.Datetime('Fecha de WhatsApp', tracking=True)
    whatsapp_delivery_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('sent', 'Enviado'),
        ('failed', 'Fallido'),
    ], string='Estado de WhatsApp', default='pending', tracking=True)
    whatsapp_error_message = fields.Text('Error de WhatsApp')
    whatsapp_reminder_count = fields.Integer(
        'Recordatorios WhatsApp',
        default=0,
        tracking=True,
    )
    last_whatsapp_reminder_date = fields.Datetime(
        'Último recordatorio WhatsApp',
    )

    # ==================== RESPUESTA DEL CLIENTE ====================
    response_date = fields.Datetime('Fecha de Respuesta', tracking=True)

    response_time = fields.Float(
        'Tiempo de Respuesta (horas)',
        compute='_compute_response_time',
        store=True
    )

    portal_access_count = fields.Integer('Accesos al Portal', default=0)
    first_portal_access = fields.Datetime('Primer Acceso')
    last_portal_access = fields.Datetime('Último Acceso')

    # ==================== AUDITORÍA ====================
    completed_by = fields.Many2one('res.users', string='Completado Por', tracking=True)

    # Contacto autenticado que realmente respondió la evaluación.
    # Se mantiene separado de evaluator_contact_id porque la persona que dio
    # conformidad al servicio puede no ser quien responda luego desde la app.
    response_contact_id = fields.Many2one(
        'res.partner',
        string='Respondido por contacto',
        tracking=True,
        index=True,
        copy=False,
    )
    response_contact_name = fields.Char(
        string='Nombre de quien respondió',
        tracking=True,
        copy=False,
    )
    response_contact_email = fields.Char(
        string='Correo de quien respondió',
        tracking=True,
        copy=False,
    )

    ip_address = fields.Char('Dirección IP')
    user_agent = fields.Char('Navegador/Dispositivo')

    completion_source = fields.Selection([
        ('portal', 'Portal Web'),
        ('app', 'App móvil'),
        ('email', 'Desde Correo'),
        ('manual', 'Manual'),
        ('system', 'Sistema')
    ], string='Fuente de Completado', tracking=True)

    # ==================== MÉTRICAS ====================
    days_to_complete = fields.Integer(
        'Días para Completar',
        compute='_compute_days_to_complete',
        store=True
    )

    is_on_time = fields.Boolean(
        'Respondió a Tiempo',
        compute='_compute_is_on_time',
        store=True
    )

    notification_channel = fields.Selection([
        ('email', 'Correo Electrónico'),
        ('whatsapp', 'WhatsApp'),
        ('sms', 'SMS'),
        ('multiple', 'Múltiples Canales')
    ], string='Canal de Notificación', default='email')

    # ==================== ASPECTOS DE EVALUACIÓN (ENCUESTA ACTIVA) ====================
    solucion_problema = fields.Selection([
        ('1', 'Malo'),
        ('2', 'Regular'),
        ('3', 'Bueno'),
        ('4', 'Muy Bueno'),
        ('5', 'Excelente')
    ], string='¿Cómo califica la solución del problema?', tracking=True,
       help='Pregunta fusionada: incluye la revisión/diagnóstico y la solución brindada.')

    explicacion_trabajo = fields.Selection([
        ('1', 'Malo'),
        ('2', 'Regular'),
        ('3', 'Bueno'),
        ('4', 'Muy Bueno'),
        ('5', 'Excelente')
    ], string='¿Cómo califica la atención brindada por el técnico? (explicación, limpieza y orden)',
       tracking=True,
       help='Pregunta fusionada: incluye la explicación del trabajo realizado y la limpieza/orden.')

    realizo_pruebas = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No')
    ], string='¿El técnico probó el equipo antes de retirarse?', tracking=True)

    consulto_suministros = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No')
    ], string='¿Le consultó si necesitaba tóner u otros suministros?', tracking=True)

    # ==================== CAMPOS LEGADO (solo historial, no se preguntan) ====================
    saludo_presentacion = fields.Selection([
        ('1', 'No saludó ni se presentó'),
        ('2', 'Saludo y presentación básica'),
        ('3', 'Saludo correcto y profesional'),
        ('4', 'Saludo profesional y actitud positiva'),
        ('5', 'Saludo excelente, mostró cortesía y empatía')
    ], string='(Legado) Saludo y presentación', tracking=True,
       help='Campo legado. Ya no forma parte de la encuesta; se conserva por historial.')

    diagnostico_problema = fields.Selection([
        ('1', 'Malo'),
        ('2', 'Regular'),
        ('3', 'Bueno'),
        ('4', 'Muy Bueno'),
        ('5', 'Excelente')
    ], string='(Legado) Revisión del problema', tracking=True,
       help='Campo legado. Fusionado con "solución del problema"; se conserva por historial.')

    limpieza_orden = fields.Selection([
        ('1', 'Malo'),
        ('2', 'Regular'),
        ('3', 'Bueno'),
        ('4', 'Muy Bueno'),
        ('5', 'Excelente')
    ], string='(Legado) Limpieza y orden', tracking=True,
       help='Campo legado. Fusionado con "cierre del servicio"; se conserva por historial.')

    revision_adicional = fields.Selection([
        ('1', 'No revisó otros equipos ni consultó sobre más impresoras'),
        ('2', 'Revisión básica - Solo preguntó si había más equipos'),
        ('3', 'Bueno - Verificó estado básico de otros equipos'),
        ('4', 'Muy Bueno - Revisó estado y funcionamiento de equipos adicionales'),
        ('5', 'Excelente - Revisión completa de todos los equipos e impresoras, verificó operatividad')
    ], string='(Legado) Revisión de equipos adicionales', tracking=True,
       help='Campo legado. Ya no forma parte de la encuesta; se conserva por historial.')

    retiro_tecnico = fields.Selection([
        ('con_visto', 'Con Visto Bueno'),
        ('sin_visto', 'Sin Visto Bueno'),
        ('sin_aviso', 'Se Retiró Sin Avisar')
    ], string='(Legado) Conformidad de Retiro', tracking=True,
       help='Campo legado. Ya no forma parte de la encuesta; el factor de penalización '
            'solo aplica a evaluaciones antiguas que lo tengan registrado.')

    consulto_problemas = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No')
    ], string='(Legado) ¿Preguntó si había problemas adicionales?', tracking=True,
       help='Campo legado. Ya no forma parte de la encuesta; se conserva por historial.')

    # ==================== CAMPOS ADICIONALES ====================
    comentarios = fields.Text('Comentarios o Sugerencias', tracking=True)
    token = fields.Char('Token de Evaluación', copy=False, index=True)

    evaluation_url = fields.Char(
        'Enlace de Evaluación',
        compute='_compute_evaluation_url',
        help='URL pública del formulario de evaluación. Es el mismo enlace que recibe el cliente por correo.'
    )

    # ==================== CAMPOS CALCULADOS ====================
    puntaje_servicio = fields.Float(
        'Puntaje del Servicio (%)',
        compute='_compute_puntaje',
        store=True,
        tracking=True
    )

    nivel_atencion = fields.Selection([
        ('excelente', 'Excelente (90-100%)'),
        ('bueno', 'Bueno (80-89%)'),
        ('regular', 'Regular (70-79%)'),
        ('deficiente', 'Deficiente (<70%)')
    ], compute='_compute_niveles', store=True, tracking=True, string='Nivel de Atención')

    requiere_atencion = fields.Boolean(
        'Requiere Atención',
        compute='_compute_requiere_atencion',
        store=True
    )

    analisis_detallado = fields.Text(
        'Análisis Detallado',
        compute='_compute_analisis',
        store=True
    )

    recomendaciones_mejora = fields.Text(
        'Recomendaciones de Mejora',
        compute='_compute_recomendaciones',
        store=True
    )

    color = fields.Integer(
        string='Índice de Color',
        compute='_compute_color',
        store=True
    )

    
    _client_service_evaluation_token_unique = models.Constraint(
        'UNIQUE(token)',
        'El token de evaluación debe ser único.',
    )


    # ==================== MÉTODOS CREATE Y WRITE ====================
    @api.model_create_multi
    def create(self, vals_list):
        normalized_vals_list = []

        for incoming_vals in vals_list:
            vals = dict(incoming_vals or {})

            # Compatibilidad con llamadas antiguas que todavía envían ticket_id.
            # ticket_id es calculado; el vínculo real se mantiene en ticket_ids.
            legacy_ticket_id = vals.pop('ticket_id', False)
            if legacy_ticket_id and not vals.get('ticket_ids'):
                vals['ticket_ids'] = [(6, 0, [legacy_ticket_id])]

            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'client.service.evaluation'
                ) or 'New'

            if not vals.get('token'):
                vals['token'] = self._generate_token()

            ticket = self._get_single_ticket_from_commands(vals.get('ticket_ids'))

            if ticket:
                if not vals.get('partner_id') and ticket.partner_id:
                    vals['partner_id'] = ticket.partner_id.id

                if not vals.get('technician_id') and ticket.responsable:
                    vals['technician_id'] = ticket.responsable.id

                if not vals.get('visit_date'):
                    vals['visit_date'] = self._get_ticket_visit_date(ticket)

                approval_vals = self._get_evaluator_snapshot_from_ticket(ticket)
                for field_name, field_value in approval_vals.items():
                    if field_name not in vals:
                        vals[field_name] = field_value

            elif not vals.get('visit_date') and vals.get('ticket_ids'):
                visit_date = self._get_visit_date_from_ticket_commands(
                    vals.get('ticket_ids')
                )
                if visit_date:
                    vals['visit_date'] = visit_date

            normalized_vals_list.append(vals)

        records = super(ClientServiceEvaluation, self).create(normalized_vals_list)

        for record in records:
            partner_name = record.partner_id.name or 'Sin cliente'
            technician_name = record.technician_id.name or 'Sin técnico'
            evaluator_name = record.evaluator_name or 'Sin persona registrada'

            evaluation_date_text = ''
            if record.evaluation_date:
                evaluation_date_text = fields.Datetime.context_timestamp(
                    record,
                    record.evaluation_date
                ).strftime('%d/%m/%Y %H:%M')

            record.message_post(
                body=f"""<p><strong>📋 Evaluación de Servicio Creada</strong></p>
                        <ul>
                            <li><strong>Cliente:</strong> {partner_name}</li>
                            <li><strong>Técnico:</strong> {technician_name}</li>
                            <li><strong>Persona evaluadora:</strong> {evaluator_name}</li>
                            <li><strong>Tickets:</strong> {len(record.ticket_ids)} ticket(s)</li>
                            <li><strong>Fecha:</strong> {evaluation_date_text}</li>
                        </ul>""",
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )

        return records

    def write(self, vals):
        old_states = {record.id: record.state for record in self}

        vals = dict(vals or {})

        result = super(ClientServiceEvaluation, self).write(vals)

        # Al completar, rellenar datos de auditoría faltantes POR REGISTRO.
        # Antes se inyectaban en 'vals' compartido y se sobreescribían valores
        # existentes en escrituras multi-registro.
        if vals.get('state') == 'completed':
            now = fields.Datetime.now()
            user_is_valid = self.env.user and not self.env.user._is_public()

            for record in self:
                fill_vals = {}

                if not record.response_date:
                    fill_vals['response_date'] = now

                if not record.completed_by and user_is_valid:
                    fill_vals['completed_by'] = self.env.user.id

                if not record.completion_source:
                    fill_vals['completion_source'] = 'portal'

                if not record.response_contact_name:
                    if record.evaluator_contact_id or record.evaluator_name:
                        fill_vals.update({
                            'response_contact_id': (
                                record.evaluator_contact_id.id
                                if record.evaluator_contact_id
                                else False
                            ),
                            'response_contact_name': (
                                record.evaluator_name
                                or (
                                    record.evaluator_contact_id.name
                                    if record.evaluator_contact_id
                                    else ''
                                )
                            ),
                            'response_contact_email': (
                                record.evaluator_email
                                or (
                                    record.evaluator_contact_id.email
                                    if record.evaluator_contact_id
                                    else ''
                                )
                            ),
                        })
                    elif record.partner_id:
                        fill_vals.update({
                            'response_contact_id': record.partner_id.id,
                            'response_contact_name': record.partner_id.name or '',
                            'response_contact_email': record._get_recipient_email() or '',
                        })

                if fill_vals:
                    super(ClientServiceEvaluation, record).write(fill_vals)

        for record in self:
            old_state = old_states.get(record.id)
            new_state = record.state

            if 'state' in vals and old_state and old_state != new_state:
                record._notify_state_change(old_state, new_state)

            if 'state' in vals and new_state == 'completed' and old_state != 'completed':
                record._notify_completion()

        return result

    # ==================== MÉTODOS COMPUTE ====================
    @api.depends('ticket_ids')
    def _compute_ticket_id(self):
        """Compute para mantener compatibilidad con la plantilla de correo"""
        for record in self:
            record.ticket_id = record.ticket_ids[:1] if record.ticket_ids else False

    @api.depends('evaluation_date', 'email_sent_date')
    def _compute_expiration_date(self):
        # Solo las evaluaciones NUEVAS usan fecha de cola de correo.
        # Históricas sin email_sent_date conservan la fecha original.
        days = self._get_expiration_days()
        for record in self:
            start = record.email_sent_date or record.evaluation_date
            record.expiration_date = start + timedelta(days=days) if start else False

    @api.depends('token')
    def _compute_evaluation_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        base_url = base_url.rstrip('/')
        for record in self:
            if record.token:
                record.evaluation_url = f"{base_url}/evaluation/submit/{record.token}"
            else:
                record.evaluation_url = False

    @api.depends('email_sent_date', 'response_date')
    def _compute_response_time(self):
        for record in self:
            if record.email_sent_date and record.response_date:
                delta = record.response_date - record.email_sent_date
                record.response_time = delta.total_seconds() / 3600
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

    def _get_answered_scores(self):
        """
        Devuelve dict {campo: puntaje int} SOLO de los campos de calificación
        respondidos. Compatible con formato antiguo (6 preguntas) y nuevo (2).
        """
        self.ensure_one()
        scores = {}
        for field_name in self.RATING_FIELDS:
            value = getattr(self, field_name)
            if value and str(value).isdigit():
                scores[field_name] = int(value)
        return scores

    @api.depends(
        'saludo_presentacion',
        'diagnostico_problema',
        'solucion_problema',
        'explicacion_trabajo',
        'limpieza_orden',
        'revision_adicional',
        'retiro_tecnico'
    )
    def _compute_puntaje(self):
        for record in self:
            scores = list(record._get_answered_scores().values())

            # Factor de penalización solo aplica a evaluaciones antiguas
            # que registraron conformidad de retiro (campo legado).
            retiro_factor = 1.0
            if record.retiro_tecnico == 'sin_visto':
                retiro_factor = 0.8
            elif record.retiro_tecnico == 'sin_aviso':
                retiro_factor = 0.5

            if scores:
                base_score = (sum(scores) / (len(scores) * 5)) * 100
                record.puntaje_servicio = base_score * retiro_factor
            else:
                record.puntaje_servicio = 0

    @api.depends('puntaje_servicio', 'state')
    def _compute_niveles(self):
        for record in self:
            # Sin respuestas y sin completar, no clasificar: evita que los
            # borradores figuren como "Deficiente" en reportes gerenciales.
            if record.state != 'completed' and not record.puntaje_servicio:
                record.nivel_atencion = False
            elif record.puntaje_servicio >= 90:
                record.nivel_atencion = 'excelente'
            elif record.puntaje_servicio >= 80:
                record.nivel_atencion = 'bueno'
            elif record.puntaje_servicio >= 70:
                record.nivel_atencion = 'regular'
            else:
                record.nivel_atencion = 'deficiente'

    @api.depends(
        'state',
        'puntaje_servicio',
        'realizo_pruebas',
        'consulto_suministros'
    )
    def _compute_requiere_atencion(self):
        for record in self:
            # Solo evaluaciones completadas pueden requerir atención:
            # evita falsas alertas por borradores con puntaje 0.
            if record.state != 'completed':
                record.requiere_atencion = False
                continue

            record.requiere_atencion = (
                record.puntaje_servicio < 70 or
                record.realizo_pruebas == 'no' or
                record.consulto_suministros == 'no'
            )

    @api.depends('state', 'nivel_atencion', 'requiere_atencion')
    def _compute_color(self):
        for record in self:
            if record.state == 'draft':
                record.color = 0
            elif record.state == 'sent':
                record.color = 4
            elif record.state == 'expired':
                record.color = 1
            elif record.state == 'completed':
                if record.nivel_atencion == 'excelente':
                    record.color = 10
                elif record.nivel_atencion == 'bueno':
                    record.color = 3
                elif record.nivel_atencion == 'regular':
                    record.color = 5
                else:
                    record.color = 1
            else:
                record.color = 0

    @api.depends(
        'saludo_presentacion',
        'diagnostico_problema',
        'solucion_problema',
        'explicacion_trabajo',
        'limpieza_orden',
        'revision_adicional',
        'realizo_pruebas',
        'consulto_suministros',
        'consulto_problemas',
        'technician_id',
        'partner_id',
        'ticket_ids',
        'retiro_tecnico',
        'puntaje_servicio',
        'response_date',
        'response_time',
        'is_on_time',
        'visit_date'
    )
    def _compute_analisis(self):
        area_labels = {
            'saludo_presentacion': 'Atención Inicial',
            'diagnostico_problema': 'Diagnóstico',
            'solucion_problema': 'Solución del Problema',
            'explicacion_trabajo': 'Cierre del Servicio',
            'limpieza_orden': 'Limpieza',
            'revision_adicional': 'Revisión Adicional',
        }

        for record in self:
            analisis = []

            analisis.append("ANÁLISIS DE SERVICIO")
            analisis.append(f"Técnico: {record.technician_id.name or 'Sin técnico'}")
            analisis.append(f"Cliente: {record.partner_id.name or 'Sin cliente'}")
            analisis.append(f"Puntaje General: {record.puntaje_servicio:.1f}%")

            if record.visit_date:
                analisis.append(f"Fecha de visita: {record.visit_date.strftime('%d/%m/%Y')}")

            analisis.append("\nEQUIPOS ATENDIDOS:")
            for ticket in record.ticket_ids:
                analisis.append(f"- Ticket: {ticket.name}")
                if hasattr(ticket, 'product_alquiler') and ticket.product_alquiler:
                    analisis.append(f"  Equipo: {ticket.product_alquiler.display_name}")
                analisis.append(
                    f"  Servicio: {ticket.tipo_servicio if hasattr(ticket, 'tipo_servicio') else 'N/A'}"
                )

            # Conformidad de retiro: solo para evaluaciones antiguas que la registraron
            if record.retiro_tecnico:
                retiro_texto = {
                    'con_visto': '✓ Se retiró con visto bueno del cliente',
                    'sin_visto': '⚠ Se retiró sin obtener visto bueno',
                    'sin_aviso': '✗ Se retiró sin avisar al cliente'
                }

                analisis.append("\nCONFORMIDAD DE RETIRO:")
                analisis.append(retiro_texto.get(record.retiro_tecnico, 'No especificado'))

                if record.retiro_tecnico == 'sin_visto':
                    analisis.append(
                        "⚠ La calificación fue reducida en 20% por falta de visto bueno del cliente"
                    )
                elif record.retiro_tecnico == 'sin_aviso':
                    analisis.append(
                        "⚠ La calificación fue reducida en 50% por retiro sin aviso"
                    )

            # Desglose solo de áreas efectivamente respondidas
            answered_scores = record._get_answered_scores()

            if answered_scores:
                analisis.append("\nDESGLOSE POR ÁREAS:")
                for field_name, puntaje in answered_scores.items():
                    porcentaje = (puntaje / 5) * 100
                    nivel = (
                        "✓ Excelente" if porcentaje >= 90 else
                        "✓ Bueno" if porcentaje >= 80 else
                        "⚠ Regular" if porcentaje >= 70 else
                        "✗ Deficiente"
                    )
                    analisis.append(f"{area_labels.get(field_name, field_name)}: {porcentaje:.1f}% - {nivel}")

            # Protocolo: solo preguntas respondidas
            protocolos = []
            if record.realizo_pruebas:
                protocolos.append(('Pruebas del equipo antes de retirarse', record.realizo_pruebas == 'si'))
            if record.consulto_suministros:
                protocolos.append(('Consulta de tóner/suministros', record.consulto_suministros == 'si'))
            if record.consulto_problemas:
                protocolos.append(('Consulta de problemas adicionales (legado)', record.consulto_problemas == 'si'))

            if protocolos:
                analisis.append("\nCUMPLIMIENTO DE PROTOCOLO:")
                for protocolo, cumplido in protocolos:
                    analisis.append(f"{'✓' if cumplido else '✗'} {protocolo}")

            if record.response_date:
                analisis.append("\nTIEMPO DE RESPUESTA:")
                analisis.append(f"Respondió en: {record.response_time:.1f} horas")
                analisis.append(f"{'✓ A tiempo' if record.is_on_time else '✗ Fuera de tiempo'}")

            record.analisis_detallado = '\n'.join(analisis)

    @api.depends(
        'puntaje_servicio',
        'solucion_problema',
        'explicacion_trabajo',
        'realizo_pruebas',
        'consulto_suministros',
        'state'
    )
    def _compute_recomendaciones(self):
        for record in self:
            # Solo generar recomendaciones sobre preguntas respondidas:
            # antes, un campo vacío ('0' <= 3) generaba recomendaciones falsas.
            if record.state != 'completed':
                record.recomendaciones_mejora = False
                continue

            recomendaciones = ["RECOMENDACIONES DE MEJORA:"]

            if record.solucion_problema and int(record.solucion_problema) <= 3:
                recomendaciones.append("""
- Diagnóstico y Solución:
  - Realizar revisión más detallada del problema
  - Asegurar solución completa y verificar funcionamiento
  - Documentar el diagnóstico y la solución aplicada""")

            if record.explicacion_trabajo and int(record.explicacion_trabajo) <= 3:
                recomendaciones.append("""
- Cierre del Servicio:
  - Explicar el trabajo realizado en lenguaje comprensible
  - Verificar entendimiento del cliente
  - Dejar el área y el equipo limpios y ordenados""")

            if record.realizo_pruebas == 'no':
                recomendaciones.append("""
- Pruebas:
  - Implementar protocolo de pruebas antes de retirarse
  - Realizar pruebas con el cliente presente
  - Documentar resultados""")

            if record.consulto_suministros == 'no':
                recomendaciones.append("""
- Suministros:
  - Consultar stock de tóner y consumibles
  - Registrar necesidades detectadas
  - Informar al cliente""")

            if record.puntaje_servicio < 70:
                recomendaciones.insert(1, """
ACCIONES URGENTES:
- Capacitación inmediata en:
  - Protocolos de servicio
  - Atención al cliente
  - Habilidades técnicas
- Seguimiento semanal
- Supervisión directa""")

            if len(recomendaciones) == 1:
                recomendaciones.append("\nSin observaciones. El servicio cumplió con los estándares esperados.")

            record.recomendaciones_mejora = '\n'.join(recomendaciones)

    # ==================== MÉTODOS AUXILIARES ====================
    def _generate_token(self):
        """Genera un token único para la evaluación"""
        return str(uuid.uuid4())

    def _get_lima_today(self):
        tz = pytz.timezone('America/Lima')
        return datetime.now(tz).date()

    def _get_lima_datetime_range_utc_naive(self, date_value):
        """
        Devuelve inicio y fin del día en America/Lima convertidos a UTC naive,
        que es el formato usual de Datetime en Odoo.
        """
        tz = pytz.timezone('America/Lima')

        start_local = tz.localize(datetime.combine(date_value, time.min))
        end_local = tz.localize(datetime.combine(date_value, time.max))

        start_utc = start_local.astimezone(pytz.utc).replace(tzinfo=None)
        end_utc = end_local.astimezone(pytz.utc).replace(tzinfo=None)

        return start_utc, end_utc

    def _get_ticket_visit_date(self, ticket):
        """
        Obtiene la fecha de visita desde ticket.agenda.
        Si no existe agenda, usa la fecha actual de Lima.
        """
        if ticket and hasattr(ticket, 'agenda') and ticket.agenda:
            agenda_dt = fields.Datetime.context_timestamp(self, ticket.agenda)
            return agenda_dt.date()

        return self._get_lima_today()

    def _get_single_ticket_from_commands(self, commands):
        """
        Devuelve el primer ticket presente en comandos many2many.

        Las evaluaciones nuevas se crean con un solo ticket, pero se conserva
        ticket_ids para compatibilidad con el historial existente.
        """
        ticket_ids = []

        if not commands:
            return False

        for command in commands:
            if isinstance(command, (list, tuple)) and len(command) >= 2:
                if command[0] == 6 and len(command) >= 3:
                    ticket_ids.extend(command[2])
                elif command[0] == 4:
                    ticket_ids.append(command[1])

        if not ticket_ids:
            return False

        return self.env['ticket.alquiler'].browse(ticket_ids[:1]).exists()

    def _get_evaluator_snapshot_from_ticket(self, ticket):
        """
        Obtiene la persona que dio conformidad desde el ticket.

        Durante desarrollo la conformidad NO es obligatoria. Si el ticket no
        tiene visto bueno completo, devuelve valores vacíos y el envío utiliza
        el correo histórico de partner_id como fallback.
        """
        if not ticket:
            return {}

        if 'conformidad_registrada' not in ticket._fields:
            return {}

        if not ticket.conformidad_registrada:
            return {}

        return {
            'evaluator_contact_id': (
                ticket.conformidad_contacto_id.id
                if ticket.conformidad_contacto_id
                else False
            ),
            'evaluator_name': ticket.conformidad_nombre or False,
            'evaluator_dni': ticket.conformidad_dni or False,
            'evaluator_mobile': ticket.conformidad_celular or False,
            'evaluator_email': ticket.conformidad_correo or False,
        }

    def _get_recipient_email(self):
        """
        Destinatario real de la encuesta.

        Prioridad:
        1. Correo snapshot de quien firmó el ticket.
        2. Correo actual del contacto de conformidad.
        3. Correo histórico del equipo, que era el flujo anterior.
        4. Correo de partner_id, para tickets antiguos o sin visto bueno.
        """
        self.ensure_one()

        if self.evaluator_email:
            return self.evaluator_email.strip()

        if self.evaluator_contact_id and self.evaluator_contact_id.email:
            return self.evaluator_contact_id.email.strip()

        ticket = self.ticket_id or self.ticket_ids[:1]
        equipment = ticket.product_alquiler if ticket and ticket.product_alquiler else False

        if (
            equipment
            and 'correo_' in equipment._fields
            and equipment.correo_
        ):
            return equipment.correo_.strip()

        if self.partner_id and self.partner_id.email:
            return self.partner_id.email.strip()

        return False

    def _get_mail_email_values(self):
        self.ensure_one()
        recipient = self._get_recipient_email()
        return {'email_to': recipient} if recipient else {}

    def _get_recipient_name(self):
        """Nombre usado en correo y WhatsApp."""
        self.ensure_one()

        if self.evaluator_name:
            return self.evaluator_name.strip()

        if self.evaluator_contact_id and self.evaluator_contact_id.name:
            return self.evaluator_contact_id.name.strip()

        if self.partner_id and self.partner_id.name:
            return self.partner_id.name.strip()

        return 'cliente'

    def _clean_whatsapp_phone(self, phone):
        """Normaliza celulares peruanos al formato 51XXXXXXXXX."""
        digits = re.sub(r'\D', '', str(phone or ''))

        if digits.startswith('00'):
            digits = digits[2:]

        if len(digits) == 9 and digits.startswith('9'):
            digits = '51' + digits

        if len(digits) != 11 or not digits.startswith('519'):
            return False

        return digits

    def _get_recipient_mobile(self):
        """
        Devuelve exclusivamente el celular de quien dio el visto bueno.

        WhatsApp no usa el celular general del ticket, del equipo ni del
        cliente. Si no existe una conformidad registrada, el flujo histórico
        continúa únicamente por correo.
        """
        self.ensure_one()

        ticket = self.ticket_id or self.ticket_ids[:1]

        if (
            not ticket
            or 'conformidad_registrada' not in ticket._fields
            or not ticket.conformidad_registrada
        ):
            return False

        candidates = []

        if self.evaluator_mobile:
            candidates.append(self.evaluator_mobile)

        if self.evaluator_contact_id:
            candidates.extend([
                self.evaluator_contact_id.mobile,
                self.evaluator_contact_id.phone,
            ])

        # Compatibilidad con evaluaciones creadas antes de guardar el snapshot:
        # solo se leen datos del propio visto bueno ya validado arriba.
        if 'conformidad_celular' in ticket._fields:
            candidates.append(ticket.conformidad_celular)

        if (
            'conformidad_contacto_id' in ticket._fields
            and ticket.conformidad_contacto_id
        ):
            candidates.extend([
                ticket.conformidad_contacto_id.mobile,
                ticket.conformidad_contacto_id.phone,
            ])

        for candidate in candidates:
            clean_phone = self._clean_whatsapp_phone(candidate)
            if clean_phone:
                return clean_phone

        return False

    def _format_expiration_lima(self):
        self.ensure_one()

        if not self.expiration_date:
            return ''

        expiration = fields.Datetime.context_timestamp(
            self.with_context(tz='America/Lima'),
            self.expiration_date,
        )
        return expiration.strftime('%d/%m/%Y a las %H:%M')

    def _build_whatsapp_evaluation_message(self, reminder=False):
        self.ensure_one()

        recipient_name = self._get_recipient_name()
        expiration = self._format_expiration_lima()

        if reminder:
            return (
                f"Hola, {recipient_name}. Tu evaluación del servicio vence "
                f"pronto. Responder toma menos de un minuto y nos ayuda a "
                f"seguir mejorando:\n{self.evaluation_url}"
            )

        expiration_text = (
            f" Disponible hasta el {expiration}."
            if expiration
            else ''
        )

        return (
            f"Hola, {recipient_name}. Queremos conocer tu opinión sobre el "
            f"servicio técnico recibido. Tu respuesta nos ayuda a mejorar: "
            f"\n{self.evaluation_url}{expiration_text}"
        )

    def _send_whatsapp_message(self, phone, message):
        """Envía texto usando el mismo gateway WhatsApp del módulo SAT."""
        ICP = self.env['ir.config_parameter'].sudo()
        base_url = (ICP.get_param('sat.whatsapp_gateway_base_url') or '').rstrip('/')
        api_key = ICP.get_param('sat.whatsapp_gateway_api_key') or ''

        if not base_url:
            return {'success': False, 'error': 'Falta configurar sat.whatsapp_gateway_base_url'}

        if not api_key:
            return {'success': False, 'error': 'Falta configurar sat.whatsapp_gateway_api_key'}

        try:
            response = requests.post(
                f"{base_url}/api/send-message",
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': api_key,
                },
                json={
                    'to': phone,
                    'message': message,
                },
                timeout=30,
            )

            try:
                response_data = response.json()
            except json.JSONDecodeError:
                response_data = {}

            if 200 <= response.status_code < 300 and response_data.get('success'):
                return {'success': True, 'response': response_data}

            return {
                'success': False,
                'error': response_data.get('error') or f'HTTP {response.status_code}',
            }

        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Tiempo de espera agotado al enviar WhatsApp'}
        except requests.exceptions.RequestException as exc:
            return {'success': False, 'error': f'Error de red: {exc}'}
        except Exception as exc:
            _logger.exception(
                "Error inesperado enviando WhatsApp de evaluación %s",
                self.name,
            )
            return {'success': False, 'error': str(exc)}

    def _send_whatsapp_evaluation(self, reminder=False):
        self.ensure_one()

        phone = self._get_recipient_mobile()

        if not phone:
            return {
                'success': False,
                'skipped': True,
                'error': (
                    'WhatsApp omitido: el ticket no tiene visto bueno o la '
                    'persona que dio la conformidad no tiene un celular válido'
                ),
            }

        result = self._send_whatsapp_message(
            phone,
            self._build_whatsapp_evaluation_message(reminder=reminder),
        )
        now = fields.Datetime.now()

        if result.get('success'):
            values = {
                'whatsapp_delivery_status': 'sent',
                'whatsapp_error_message': False,
            }

            if reminder:
                values.update({
                    'whatsapp_reminder_count': self.whatsapp_reminder_count + 1,
                    'last_whatsapp_reminder_date': now,
                })
            else:
                values.update({
                    'whatsapp_sent': True,
                    'whatsapp_sent_date': now,
                })

            self.write(values)
        else:
            self.write({
                'whatsapp_delivery_status': 'failed',
                'whatsapp_error_message': result.get('error') or 'Error desconocido',
            })

        result['phone'] = phone
        return result

    def _set_notification_channel_from_results(self, email_ok, whatsapp_ok):
        self.ensure_one()

        if email_ok and whatsapp_ok:
            channel = 'multiple'
        elif whatsapp_ok:
            channel = 'whatsapp'
        else:
            channel = 'email'

        self.write({'notification_channel': channel})

    def _get_visit_date_from_ticket_commands(self, commands):
        """
        Intenta obtener visit_date desde comandos many2many.
        Soporta [(6, 0, ids)] y [(4, id)] / [(4, id, 0)].
        """
        ticket_ids = []

        if not commands:
            return False

        for command in commands:
            if isinstance(command, (list, tuple)) and len(command) >= 2:
                if command[0] == 6 and len(command) >= 3:
                    ticket_ids.extend(command[2])
                elif command[0] == 4:
                    ticket_ids.append(command[1])

        if not ticket_ids:
            return False

        ticket = self.env['ticket.alquiler'].browse(ticket_ids[:1])
        return self._get_ticket_visit_date(ticket)

    def _get_evaluation_window_days(self):
        """
        Días hacia atrás para buscar tickets finalizados pendientes de evaluación.
        Sirve para casos donde la visita fue hoy, pero el ticket se finalizó después.
        """
        days = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'sat.service_evaluation_window_days',
                default='7'
            )
        )
        return max(days, 1)

    def _get_expiration_days(self):
        """
        Días de vigencia de la evaluación antes de expirar.
        Configurable vía ir.config_parameter (default: 2, comportamiento original).
        """
        days = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'sat.service_evaluation_expiration_days',
                default='2'
            )
        )
        return max(days, 1)

    def _get_existing_evaluation_for_group(self, partner_id, technician_id, visit_date):
        """
        Busca una evaluación existente para el mismo cliente, técnico y fecha de visita.
        """
        domain = [
            ('partner_id', '=', partner_id),
            ('technician_id', '=', technician_id),
            ('visit_date', '=', visit_date),
            ('state', 'in', ['draft', 'sent', 'completed', 'expired'])
        ]
        return self.search(domain, limit=1)

    def _get_tickets_already_in_evaluations(self, tickets):
        """
        Devuelve IDs de tickets que ya están vinculados a alguna evaluación.
        Evita reenviar evaluación por tickets ya evaluados.
        """
        if not tickets:
            return []

        evaluations = self.search([
            ('ticket_ids', 'in', tickets.ids),
            ('state', 'in', ['draft', 'sent', 'completed', 'expired'])
        ])

        return evaluations.mapped('ticket_ids').ids

    def _notify_state_change(self, old_state, new_state):
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

        nivel_label = dict(self._fields['nivel_atencion'].selection).get(self.nivel_atencion)

        message = f"""<p>✅ <strong>Evaluación Completada</strong></p>
                     <ul>
                         <li><strong>Respondió:</strong> {self.response_contact_name or self._get_recipient_name()}</li>
                         <li><strong>Puntaje:</strong> {self.puntaje_servicio:.1f}%</li>
                         <li><strong>Nivel:</strong> 
                             <span class="badge badge-{nivel_colors.get(self.nivel_atencion, 'secondary')}">
                                 {nivel_icons.get(self.nivel_atencion, '')} {nivel_label or ''}
                             </span>
                         </li>
                         <li><strong>Tiempo de respuesta:</strong> {self.response_time:.1f} horas</li>
                         <li><strong>Plazo:</strong> {'✓ A tiempo' if self.is_on_time else '✗ Fuera de tiempo'}</li>
                     </ul>"""

        if self.comentarios:
            message += f"<p><strong>Comentarios del cliente:</strong><br/>{self.comentarios}</p>"

        self.message_post(
            body=message,
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )

        if self.technician_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=self.technician_id.id,
                summary=f'Tu evaluación de servicio ha sido completada - {self.puntaje_servicio:.1f}%',
                note=f"""{self.response_contact_name or self._get_recipient_name()} completó la evaluación de servicio del cliente {self.partner_id.name or 'Sin cliente'}.
                        Puntaje obtenido: {self.puntaje_servicio:.1f}%
                        Nivel: {nivel_label or ''}"""
            )

        if self.requiere_atencion:
            self._notify_supervisor_attention()

    def _notify_supervisor_attention(self):
        self.ensure_one()

        supervisor_group = self.env.ref('sat.group_sat_supervisor', raise_if_not_found=False)
        if not supervisor_group:
            return

        # Construir motivos dinámicamente: evita líneas vacías en la nota
        motivos = []
        if self.puntaje_servicio < 70:
            motivos.append('- Puntaje bajo (<70%)')
        if self.realizo_pruebas == 'no':
            motivos.append('- No probó el equipo antes de retirarse')
        if self.consulto_suministros == 'no':
            motivos.append('- No consultó sobre tóner/suministros')

        motivos_texto = '\n                            '.join(motivos) or '- Revisar evaluación'

        for supervisor in supervisor_group.users:
            self.activity_schedule(
                'mail.mail_activity_data_warning',
                user_id=supervisor.id,
                summary=f'⚠️ Evaluación deficiente requiere atención - {self.technician_id.name or "Sin técnico"}',
                note=f"""Una evaluación de servicio requiere atención inmediata:
                        
                        Técnico: {self.technician_id.name or 'Sin técnico'}
                        Cliente: {self.partner_id.name or 'Sin cliente'}
                        Puntaje: {self.puntaje_servicio:.1f}%
                        
                        Motivos de alerta:
                        {motivos_texto}"""
            )

    def _register_portal_access(self, request=None):
        self.ensure_one()

        current_time = fields.Datetime.now()
        previous_count = self.portal_access_count

        vals = {
            'portal_access_count': previous_count + 1,
            'last_portal_access': current_time
        }

        if not self.first_portal_access:
            vals['first_portal_access'] = current_time

        if request:
            vals['ip_address'] = request.httprequest.environ.get('REMOTE_ADDR')
            vals['user_agent'] = request.httprequest.environ.get('HTTP_USER_AGENT')

        self.write(vals)

        message = f"""<p>👁️ <strong>Acceso al Portal</strong></p>
                     <ul>
                         <li><strong>Acceso #{previous_count + 1}</strong></li>
                         <li><strong>Fecha:</strong> {fields.Datetime.context_timestamp(self, current_time).strftime('%d/%m/%Y %H:%M')}</li>
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
        return {
            'type': 'ir.actions.act_url',
            'url': '/my/evaluations/%s' % self.id,
            'target': 'self',
            'res_id': self.id,
        }

    def action_mark_as_completed(self):
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

    def action_complete_from_portal(self, vals=None, request=None):
        """
        Método recomendado para usar desde el controlador del portal.
        Guarda respuestas, IP, navegador y fecha real de respuesta del cliente.
        """
        self.ensure_one()

        vals = dict(vals or {})

        vals.update({
            'state': 'completed',
            'response_date': fields.Datetime.now(),
            'completion_source': 'portal',
        })

        # El enlace público es personal y se envía al destinatario elegido.
        # Si proviene del visto bueno, se registra a esa persona como quien
        # respondió. En tickets antiguos se conserva el cliente como respaldo.
        if not vals.get('response_contact_name'):
            if self.evaluator_contact_id or self.evaluator_name:
                vals.update({
                    'response_contact_id': (
                        self.evaluator_contact_id.id
                        if self.evaluator_contact_id
                        else False
                    ),
                    'response_contact_name': (
                        self.evaluator_name
                        or (
                            self.evaluator_contact_id.name
                            if self.evaluator_contact_id
                            else ''
                        )
                        or ''
                    ),
                    'response_contact_email': (
                        self.evaluator_email
                        or (
                            self.evaluator_contact_id.email
                            if self.evaluator_contact_id
                            else ''
                        )
                        or ''
                    ),
                })
            elif self.partner_id:
                vals.update({
                    'response_contact_id': self.partner_id.id,
                    'response_contact_name': self.partner_id.name or '',
                    'response_contact_email': self._get_recipient_email() or '',
                })

        if not self.completed_by and self.env.user and not self.env.user._is_public():
            vals['completed_by'] = self.env.user.id

        if request:
            vals['ip_address'] = request.httprequest.environ.get('REMOTE_ADDR')
            vals['user_agent'] = request.httprequest.environ.get('HTTP_USER_AGENT')

        self.write(vals)

        return True

    def action_complete_from_app(self, vals=None, request=None, contact=None):
        """
        Completa una evaluación desde la app móvil.

        El cliente/empresa no se recibe desde Flutter: el controlador valida
        previamente que la evaluación pertenezca al commercial_partner_id del
        usuario portal autenticado. Aquí solo se guarda la auditoría de quién
        respondió y las respuestas de la encuesta.
        """
        self.ensure_one()

        vals = dict(vals or {})
        now = fields.Datetime.now()

        vals.update({
            'state': 'completed',
            'response_date': now,
            'completion_source': 'app',
        })

        if self.env.user and not self.env.user._is_public():
            vals['completed_by'] = self.env.user.id

        if contact:
            vals.update({
                'response_contact_id': contact.id,
                'response_contact_name': contact.name or '',
                'response_contact_email': contact.email or '',
            })

        if request:
            forwarded_for = request.httprequest.headers.get('X-Forwarded-For', '')
            remote_addr = request.httprequest.environ.get('REMOTE_ADDR') or ''
            vals['ip_address'] = (forwarded_for.split(',')[0].strip() if forwarded_for else remote_addr)
            vals['user_agent'] = request.httprequest.environ.get('HTTP_USER_AGENT') or ''

        self.write(vals)
        return True

    def action_reset_to_draft(self):
        self.ensure_one()

        self.write({'state': 'draft'})

        self.message_post(
            body="<p>🔄 <strong>Evaluación regresada a borrador</strong></p>",
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )

        return True

    def _has_answered_evaluation(self):
        """Protege respuestas antiguas y nuevas aunque su estado haya quedado 'sent'."""
        self.ensure_one()
        if self.state == 'completed' or self.response_date:
            return True
        return any(
            bool(getattr(self, field_name, False))
            for field_name in self.RATING_FIELDS + [
                'realizo_pruebas', 'consulto_suministros', 'consulto_problemas'
            ]
        )

    def _get_initial_notification_date(self):
        """Fecha del primer envío realmente registrado; no usa evaluation_date."""
        self.ensure_one()
        dates = [
            value for value in (self.email_sent_date, self.whatsapp_sent_date)
            if value
        ]
        return min(dates) if dates else False

    def _queue_evaluation_email(self, template_xmlid, is_reminder=False):
        """Encola dentro de la transacción: nunca entrega antes del commit.

        mail.mail se crea por send_mail(force_send=False). Si la transacción
        revierte, se revierten tanto la evaluación como el correo.
        """
        self.ensure_one()
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        recipient = self._get_recipient_email()
        if not template or not recipient:
            return False
        mail_id = template.send_mail(
            self.id, force_send=False,
            email_values={'email_to': recipient},
        )
        return mail_id or False

    def action_send_reminder(self):
        """Un recordatorio máximo, por correo y 24 h tras el primer correo."""
        self.ensure_one()
        now = fields.Datetime.now()
        today = self._get_lima_today()
        if (
            self.state != 'sent'
            or self._has_answered_evaluation()
            or self.reminder_count != 0 or self.last_reminder_date
            or not self.email_sent or not self.email_sent_date
            or self.email_sent_date > now - timedelta(hours=24)
            or self.email_sent_date < now - timedelta(days=3)
            or not self.visit_date
            or self.visit_date < today - timedelta(days=2)
            or self.visit_date > today
            or not self.expiration_date or self.expiration_date <= now
        ):
            return False
        # Bloquear concurrencia entre cron y reintentos sin esperar.
        self.env.cr.execute(
            'SELECT id FROM client_service_evaluation WHERE id = %s FOR UPDATE',
            (self.id,),
        )
        self.invalidate_recordset()
        if self.state != 'sent' or self._has_answered_evaluation() or self.reminder_count or self.last_reminder_date:
            return False
        mail_id = self._queue_evaluation_email(
            'sat.email_template_service_evaluation_reminder', is_reminder=True,
        )
        if not mail_id:
            return False
        self.write({'reminder_count': 1, 'last_reminder_date': now})
        _logger.info('[EVALUACION] Recordatorio ENCOLADO evaluación=%s mail=%s', self.id, mail_id)
        return True

    def action_resend_evaluation(self):
        """Reenvío manual de invitación vigente, en cola y solo por correo."""
        self.ensure_one()
        now = fields.Datetime.now()
        if (
            self.state != 'sent' or self._has_answered_evaluation()
            or self.reminder_count or self.last_reminder_date
            or not self.visit_date
            or self.visit_date < self._get_lima_today() - timedelta(days=2)
            or self.visit_date > self._get_lima_today()
            or not self.expiration_date or self.expiration_date <= now
        ):
            return False
        mail_id = self._queue_evaluation_email('sat.email_template_service_evaluation')
        if not mail_id:
            return False
        _logger.info('[EVALUACION] Reenvío ENCOLADO evaluación=%s mail=%s', self.id, mail_id)
        return True

    # ==================== CRON JOBS ====================
    @api.model
    def _cron_check_expired_evaluations(self):
        _logger.info("🕐 Verificando evaluaciones expiradas...")

        try:
            current_datetime = fields.Datetime.now()

            domain = [
                ('state', '=', 'sent'),
                ('response_date', '=', False),
                ('expiration_date', '<', current_datetime)
            ]

            expired_evaluations = self.search(domain)

            if expired_evaluations:
                for evaluation in expired_evaluations:
                    if evaluation._has_answered_evaluation():
                        _logger.info(
                            "[EVALUACION] No expirar %s: contiene respuestas",
                            evaluation.name,
                        )
                        continue
                    evaluation.write({'state': 'expired'})

                    expiration_text = ''
                    if evaluation.expiration_date:
                        expiration_text = fields.Datetime.context_timestamp(
                            evaluation,
                            evaluation.expiration_date
                        ).strftime('%d/%m/%Y %H:%M')

                    evaluation.message_post(
                        body=f"""<p>⏰ <strong>Evaluación Expirada</strong></p>
                                <ul>
                                    <li><strong>Fecha de expiración:</strong> {expiration_text}</li>
                                    <li><strong>Accesos al portal:</strong> {evaluation.portal_access_count}</li>
                                    <li><strong>Recordatorios enviados:</strong> {evaluation.reminder_count}</li>
                                </ul>""",
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )

                    if evaluation.technician_id:
                        evaluation.activity_schedule(
                            'mail.mail_activity_data_todo',
                            user_id=evaluation.technician_id.id,
                            summary='Evaluación de servicio expirada',
                            note=f"""La evaluación del cliente {evaluation.partner_id.name or 'Sin cliente'} ha expirado sin ser completada.
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
        """Una encuesta por empresa + técnico + día de visita.

        Ventana estricta: ayer; hoy después de las 18:00 (Lima).
        Usa únicamente la cola mail.mail transaccional, sin SMTP directo.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        if (ICP.get_param('sat.service_evaluation_notifications_enabled', 'True') or '').lower() in ('false', '0', 'no'):
            _logger.warning('[EVALUACION] Envíos deshabilitados por configuración')
            return True

        lima_tz = pytz.timezone('America/Lima')
        now_local = fields.Datetime.now().replace(tzinfo=pytz.utc).astimezone(lima_tz)
        today = now_local.date()
        earliest_day = today - timedelta(days=1)
        cutoff_day = today if now_local.hour >= 18 else earliest_day
        start_dt, _ = self._get_lima_datetime_range_utc_naive(earliest_day)
        _, end_dt = self._get_lima_datetime_range_utc_naive(cutoff_day)

        tickets = self.env['ticket.alquiler'].search([
            ('estado', '=', 'finalizado'),
            ('agenda', '>=', start_dt), ('agenda', '<=', end_dt),
            ('partner_id', '!=', False), ('responsable', '!=', False),
        ])
        already_linked = set(self._get_tickets_already_in_evaluations(tickets))
        groups = {}
        for ticket in tickets:
            if not ticket.agenda:
                continue
            visit_day = pytz.utc.localize(ticket.agenda).astimezone(lima_tz).date()
            if not earliest_day <= visit_day <= cutoff_day:
                continue
            partner = ticket.partner_id.commercial_partner_id or ticket.partner_id
            key = (partner.id, ticket.responsable.id, visit_day)
            groups.setdefault(key, self.env['ticket.alquiler'])
            groups[key] |= ticket

        created = linked = queued = skipped = 0
        for (partner_id, tech_id, visit_day), group_tickets in groups.items():
            try:
                # SAVEPOINT permite continuar con otros grupos ante un error.
                # La transacción completa la confirma Odoo al terminar el cron.
                with self.env.cr.savepoint():
                    candidates = self.search([
                        ('technician_id', '=', tech_id),
                        ('visit_date', '=', visit_day),
                    ], order='id asc')
                    existing = candidates.filtered(
                        lambda e: e.partner_id and
                        e.partner_id.commercial_partner_id.id == partner_id
                    )[:1]
                    if existing:
                        extra_ids = [t.id for t in group_tickets if t.id not in already_linked]
                        if extra_ids:
                            existing.write({'ticket_ids': [(4, id_) for id_ in extra_ids]})
                            linked += len(extra_ids)
                        continue

                    eligible = group_tickets.filtered(lambda t: t.id not in already_linked)
                    if not eligible:
                        continue
                    evaluation = self.create({
                        'ticket_ids': [(6, 0, eligible.ids)],
                        'partner_id': partner_id,
                        'technician_id': tech_id,
                        'visit_date': visit_day,
                        'state': 'draft',
                    })
                    created += 1
                    if not evaluation._get_recipient_email():
                        evaluation.write({
                            'email_delivery_status': 'failed',
                            'email_error_message': 'Sin correo de destinatario',
                        })
                        skipped += 1
                        continue
                    # El estado y la fecha se confirman junto al correo en cola.
                    # No usar force_send=True: SMTP debe ejecutarse después del commit.
                    now = fields.Datetime.now()
                    evaluation.write({
                        'state': 'sent',
                        'email_sent': True,
                        'email_sent_date': now,
                        'email_delivery_status': 'pending',
                        'notification_channel': 'email',
                    })
                    mail_id = evaluation._queue_evaluation_email(
                        'sat.email_template_service_evaluation'
                    )
                    if not mail_id:
                        evaluation.write({
                            'state': 'draft',
                            'email_sent': False,
                            'email_sent_date': False,
                            'email_delivery_status': 'failed',
                            'email_error_message': 'No se pudo preparar el mensaje en cola',
                        })
                        skipped += 1
                        continue
                    queued += 1
                    _logger.info(
                        '[EVALUACION] Grupo ENCOLADO id=%s mail=%s cliente=%s tecnico=%s fecha=%s tickets=%s',
                        evaluation.id, mail_id, partner_id, tech_id, visit_day, eligible.ids,
                    )
            except Exception:
                skipped += len(group_tickets)
                _logger.exception(
                    '[EVALUACION] Falló grupo cliente=%s tecnico=%s fecha=%s',
                    partner_id, tech_id, visit_day,
                )
        _logger.info(
            '[EVALUACION] Resumen creadas=%s vinculadas=%s en_cola=%s omitidas=%s',
            created, linked, queued, skipped,
        )
        return True

    @api.model
    def _cron_send_pending_reminders(self):
        """Solo un recordatorio de grupos recientes con correo inicial."""
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('sat.service_evaluation_notifications_enabled', 'True').lower() in ('false', '0', 'no'):
            return True
        now = fields.Datetime.now()
        today = self._get_lima_today()
        evaluations = self.search([
            ('state', '=', 'sent'),
            ('email_sent', '=', True),
            ('email_sent_date', '>=', now - timedelta(days=3)),
            ('email_sent_date', '<=', now - timedelta(hours=24)),
            ('visit_date', '>=', today - timedelta(days=2)),
            ('visit_date', '<=', today),
            ('response_date', '=', False),
            ('reminder_count', '=', 0),
            ('last_reminder_date', '=', False),
            ('expiration_date', '>', now),
        ])
        sent = 0
        for evaluation in evaluations:
            try:
                with self.env.cr.savepoint():
                    if evaluation.action_send_reminder():
                        sent += 1
            except Exception:
                _logger.exception('[EVALUACION] Error recordatorio id=%s', evaluation.id)
        _logger.info('[EVALUACION] Recordatorios enviados=%s candidatos=%s', sent, len(evaluations))
        return True
