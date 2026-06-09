from odoo import models, fields, api
from datetime import datetime, timedelta, time
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
        help='Fecha real de la visita técnica. Sirve para agrupar varios tickets en una sola evaluación.'
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
    ip_address = fields.Char('Dirección IP')
    user_agent = fields.Char('Navegador/Dispositivo')

    completion_source = fields.Selection([
        ('portal', 'Portal Web'),
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
    token = fields.Char('Token de Evaluación', copy=False, index=True)

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

    _sql_constraints = [
        (
            'client_service_evaluation_token_unique',
            'unique(token)',
            'El token de evaluación debe ser único.'
        ),
    ]

    # ==================== MÉTODOS CREATE Y WRITE ====================
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('client.service.evaluation') or 'New'

        if not vals.get('token'):
            vals['token'] = self._generate_token()

        if not vals.get('visit_date') and vals.get('ticket_ids'):
            visit_date = self._get_visit_date_from_ticket_commands(vals.get('ticket_ids'))
            if visit_date:
                vals['visit_date'] = visit_date

        record = super(ClientServiceEvaluation, self).create(vals)

        partner_name = record.partner_id.name or 'Sin cliente'
        technician_name = record.technician_id.name or 'Sin técnico'

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
                        <li><strong>Tickets:</strong> {len(record.ticket_ids)} ticket(s)</li>
                        <li><strong>Fecha:</strong> {evaluation_date_text}</li>
                    </ul>""",
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )

        return record

    def write(self, vals):
        old_states = {record.id: record.state for record in self}

        vals = dict(vals or {})

        if vals.get('state') == 'completed':
            if not vals.get('response_date'):
                records_without_response = self.filtered(lambda rec: not rec.response_date)
                if records_without_response:
                    vals['response_date'] = fields.Datetime.now()

            if not vals.get('completed_by'):
                records_without_completed_by = self.filtered(lambda rec: not rec.completed_by)
                if records_without_completed_by:
                    vals['completed_by'] = self.env.user.id

            if not vals.get('completion_source'):
                records_without_source = self.filtered(lambda rec: not rec.completion_source)
                if records_without_source:
                    vals['completion_source'] = 'portal'

        result = super(ClientServiceEvaluation, self).write(vals)

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
            scores = []
            fields_to_evaluate = [
                'saludo_presentacion',
                'diagnostico_problema',
                'solucion_problema',
                'explicacion_trabajo',
                'limpieza_orden',
                'revision_adicional'
            ]

            for field_name in fields_to_evaluate:
                value = getattr(record, field_name)
                if value and str(value).isdigit():
                    scores.append(int(value))

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

    @api.depends(
        'puntaje_servicio',
        'realizo_pruebas',
        'consulto_suministros',
        'consulto_problemas'
    )
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
        'is_on_time'
    )
    def _compute_analisis(self):
        for record in self:
            analisis = []

            areas = {
                'Atención Inicial': int(record.saludo_presentacion or '0'),
                'Diagnóstico': int(record.diagnostico_problema or '0'),
                'Solución': int(record.solucion_problema or '0'),
                'Explicación': int(record.explicacion_trabajo or '0'),
                'Limpieza': int(record.limpieza_orden or '0'),
                'Revisión Adicional': int(record.revision_adicional or '0')
            }

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

            retiro_texto = {
                'con_visto': '✓ Se retiró con visto bueno del cliente',
                'sin_visto': '⚠ Se retiró sin obtener visto bueno',
                'sin_aviso': '✗ Se retiró sin avisar al cliente'
            }

            analisis.append("\nCONFORMIDAD DE RETIRO:")
            analisis.append(retiro_texto.get(record.retiro_tecnico, 'No especificado'))

            if record.retiro_tecnico in ['sin_visto', 'sin_aviso']:
                analisis.append(
                    "⚠ El puntaje ha sido ajustado debido a la falta de conformidad en el retiro"
                )

            analisis.append("\nDESGLOSE POR ÁREAS:")
            for area, puntaje in areas.items():
                porcentaje = (puntaje / 5) * 100 if puntaje else 0
                nivel = (
                    "✓ Excelente" if porcentaje >= 90 else
                    "✓ Bueno" if porcentaje >= 80 else
                    "⚠ Regular" if porcentaje >= 70 else
                    "✗ Deficiente"
                )
                analisis.append(f"{area}: {porcentaje:.1f}% - {nivel}")

            analisis.append("\nCUMPLIMIENTO DE PROTOCOLO:")
            protocolos = {
                'Pruebas del equipo': record.realizo_pruebas == 'si',
                'Verificación de suministros': record.consulto_suministros == 'si',
                'Consulta de problemas adicionales': record.consulto_problemas == 'si'
            }

            for protocolo, cumplido in protocolos.items():
                analisis.append(f"{'✓' if cumplido else '✗'} {protocolo}")

            if record.response_date:
                analisis.append("\nTIEMPO DE RESPUESTA:")
                analisis.append(f"Respondió en: {record.response_time:.1f} horas")
                analisis.append(f"{'✓ A tiempo' if record.is_on_time else '✗ Fuera de tiempo'}")

            if record.retiro_tecnico == 'sin_visto':
                analisis.append(
                    "\nNOTA: La calificación final ha sido reducida en 20% por falta de visto bueno del cliente"
                )
            elif record.retiro_tecnico == 'sin_aviso':
                analisis.append(
                    "\nNOTA: La calificación final ha sido reducida en 50% por retiro sin aviso"
                )

            record.analisis_detallado = '\n'.join(analisis)

    @api.depends(
        'analisis_detallado',
        'puntaje_servicio',
        'nivel_atencion',
        'saludo_presentacion',
        'diagnostico_problema',
        'solucion_problema',
        'explicacion_trabajo',
        'limpieza_orden',
        'revision_adicional',
        'realizo_pruebas',
        'consulto_suministros',
        'consulto_problemas',
        'retiro_tecnico'
    )
    def _compute_recomendaciones(self):
        for record in self:
            recomendaciones = ["RECOMENDACIONES DE MEJORA:"]

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

            if int(record.revision_adicional or '0') <= 3:
                recomendaciones.append("""
- Revisión adicional:
  - Revisar equipos adicionales cuando corresponda
  - Consultar al cliente si existen otras impresoras con problemas
  - Registrar observaciones preventivas""")

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

            if record.retiro_tecnico == 'sin_visto':
                recomendaciones.append("""
- Retiro del técnico:
  - Solicitar visto bueno antes de retirarse
  - Confirmar conformidad del cliente
  - Registrar observaciones finales""")

            if record.retiro_tecnico == 'sin_aviso':
                recomendaciones.append("""
- Retiro del técnico:
  - No retirarse sin avisar al cliente
  - Confirmar cierre del servicio
  - Solicitar conformidad antes de finalizar""")

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

    def _get_visit_date_from_ticket_commands(self, commands):
        """
        Intenta obtener visit_date desde comandos many2many.
        Soporta principalmente [(6, 0, ids)].
        """
        ticket_ids = []

        if not commands:
            return False

        for command in commands:
            if isinstance(command, (list, tuple)) and len(command) >= 3:
                if command[0] == 6:
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
                         <li><strong>Puntaje:</strong> {self.puntaje_servicio:.1f}%</li>
                         <li><strong>Nivel:</strong> 
                             <span class="badge badge-{nivel_colors.get(self.nivel_atencion, 'secondary')}">
                                 {nivel_icons.get(self.nivel_atencion, '')} {nivel_label or ''}
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

        if self.technician_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=self.technician_id.id,
                summary=f'Tu evaluación de servicio ha sido completada - {self.puntaje_servicio:.1f}%',
                note=f"""El cliente {self.partner_id.name or 'Sin cliente'} ha completado tu evaluación de servicio.
                        Puntaje obtenido: {self.puntaje_servicio:.1f}%
                        Nivel: {nivel_label or ''}"""
            )

        if self.requiere_atencion:
            self._notify_supervisor_attention()

    def _notify_supervisor_attention(self):
        self.ensure_one()

        supervisor_group = self.env.ref('sat.group_sat_supervisor', raise_if_not_found=False)
        if supervisor_group:
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
                            - {'Puntaje bajo (<70%)' if self.puntaje_servicio < 70 else ''}
                            - {'No realizó pruebas' if self.realizo_pruebas == 'no' else ''}
                            - {'No consultó suministros' if self.consulto_suministros == 'no' else ''}
                            - {'No consultó problemas adicionales' if self.consulto_problemas == 'no' else ''}"""
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

        if not self.completed_by and self.env.user and not self.env.user._is_public():
            vals['completed_by'] = self.env.user.id

        if request:
            vals['ip_address'] = request.httprequest.environ.get('REMOTE_ADDR')
            vals['user_agent'] = request.httprequest.environ.get('HTTP_USER_AGENT')

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

    def action_send_reminder(self):
        self.ensure_one()

        template = self.env.ref('sat.email_template_service_evaluation_reminder', False)
        if template:
            try:
                template.send_mail(self.id, force_send=True)

                old_count = self.reminder_count

                self.write({
                    'reminder_count': old_count + 1,
                    'last_reminder_date': fields.Datetime.now()
                })

                self.message_post(
                    body=f"""<p>🔔 <strong>Recordatorio Enviado</strong></p>
                            <ul>
                                <li><strong>Recordatorio #{old_count + 1}</strong></li>
                                <li><strong>Enviado a:</strong> {self.partner_id.email or 'Sin correo'}</li>
                                <li><strong>Fecha:</strong> {fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M')}</li>
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
        self.ensure_one()

        template = self.env.ref('sat.email_template_service_evaluation', False)
        if template:
            try:
                template.send_mail(self.id, force_send=True)

                self.write({
                    'email_sent': True,
                    'email_sent_date': fields.Datetime.now(),
                    'email_delivery_status': 'sent',
                    'state': 'sent'
                })

                self.message_post(
                    body=f"""<p>📧 <strong>Evaluación Reenviada</strong></p>
                            <ul>
                                <li><strong>Enviado a:</strong> {self.partner_id.email or 'Sin correo'}</li>
                                <li><strong>Fecha:</strong> {fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M')}</li>
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
        """
        Cron para enviar evaluaciones.

        Mejora aplicada:
        - Ya no depende solo de tickets cuya agenda sea hoy.
        - Busca tickets finalizados dentro de una ventana configurable.
        - Si la visita fue hoy pero el ticket se finalizó después, igual puede generar evaluación.
        - Agrupa por cliente + técnico + fecha de visita.
        - Envía una sola evaluación aunque existan 2, 3, 4 o más tickets/máquinas en esa visita.
        """
        _logger.info("📧 Iniciando envío de evaluaciones de servicio...")

        try:
            today = self._get_lima_today()
            window_days = self._get_evaluation_window_days()

            start_date = today - timedelta(days=window_days)
            start_dt, _ = self._get_lima_datetime_range_utc_naive(start_date)
            _, end_dt = self._get_lima_datetime_range_utc_naive(today)

            domain = [
                ('estado', '=', 'finalizado'),
                ('agenda', '>=', start_dt),
                ('agenda', '<=', end_dt),
                ('partner_id', '!=', False),
                ('responsable', '!=', False)
            ]

            tickets = self.env['ticket.alquiler'].search(domain)
            _logger.info(f"🎫 Se encontraron {len(tickets)} tickets finalizados dentro de la ventana de evaluación")

            if not tickets:
                _logger.info("✅ No hay tickets para evaluar")
                return True

            already_evaluated_ticket_ids = self._get_tickets_already_in_evaluations(tickets)
            pending_tickets = tickets.filtered(lambda ticket: ticket.id not in already_evaluated_ticket_ids)

            _logger.info(
                f"🎫 Tickets pendientes de evaluación: {len(pending_tickets)} "
                f"de {len(tickets)} encontrados"
            )

            grouped_tickets = {}

            for ticket in pending_tickets:
                visit_date = self._get_ticket_visit_date(ticket)
                key = (ticket.partner_id.id, ticket.responsable.id, visit_date)

                if key not in grouped_tickets:
                    grouped_tickets[key] = []

                grouped_tickets[key].append(ticket.id)

            sent_count = 0
            error_count = 0
            updated_count = 0

            for (partner_id, technician_id, visit_date), ticket_ids in grouped_tickets.items():
                try:
                    partner = self.env['res.partner'].browse(partner_id)
                    technician = self.env['res.users'].browse(technician_id)

                    existing_eval = self._get_existing_evaluation_for_group(
                        partner_id,
                        technician_id,
                        visit_date
                    )

                    if existing_eval:
                        new_ticket_ids = list(set(existing_eval.ticket_ids.ids + ticket_ids))

                        existing_eval.write({
                            'ticket_ids': [(6, 0, new_ticket_ids)],
                        })

                        existing_eval.message_post(
                            body=f"""<p>➕ <strong>Tickets agregados a evaluación existente</strong></p>
                                    <ul>
                                        <li><strong>Cliente:</strong> {partner.name}</li>
                                        <li><strong>Técnico:</strong> {technician.name}</li>
                                        <li><strong>Fecha de visita:</strong> {visit_date.strftime('%d/%m/%Y')}</li>
                                        <li><strong>Total tickets:</strong> {len(new_ticket_ids)}</li>
                                    </ul>""",
                            message_type='notification',
                            subtype_xmlid='mail.mt_note'
                        )

                        updated_count += 1

                        _logger.info(
                            f"⏭️ Evaluación existente actualizada: {existing_eval.name} - "
                            f"Cliente: {partner.name}, Técnico: {technician.name}, "
                            f"Visita: {visit_date}, Tickets: {len(new_ticket_ids)}"
                        )

                        continue

                    evaluation = self.create({
                        'ticket_ids': [(6, 0, ticket_ids)],
                        'partner_id': partner_id,
                        'technician_id': technician_id,
                        'visit_date': visit_date,
                        'state': 'draft',
                        'retiro_tecnico': 'con_visto',
                    })

                    _logger.info(
                        f"📋 Evaluación creada #{evaluation.name} - "
                        f"Cliente: {partner.name}, "
                        f"Técnico: {technician.name}, "
                        f"Visita: {visit_date}, "
                        f"Tickets: {len(ticket_ids)}"
                    )

                    evaluation.message_post(
                        body=f"""<p>🤖 <strong>Evaluación Creada Automáticamente</strong></p>
                                <ul>
                                    <li><strong>Cliente:</strong> {partner.name}</li>
                                    <li><strong>Técnico:</strong> {technician.name}</li>
                                    <li><strong>Fecha de visita:</strong> {visit_date.strftime('%d/%m/%Y')}</li>
                                    <li><strong>Tickets procesados:</strong> {len(ticket_ids)}</li>
                                    <li><strong>Fecha de creación:</strong> {fields.Datetime.context_timestamp(evaluation, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M')}</li>
                                </ul>""",
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )

                    template = self.env.ref('sat.email_template_service_evaluation', False)

                    if template:
                        try:
                            template.send_mail(evaluation.id, force_send=True)

                            evaluation.write({
                                'state': 'sent',
                                'email_sent': True,
                                'email_sent_date': fields.Datetime.now(),
                                'email_delivery_status': 'sent'
                            })

                            evaluation.message_post(
                                body=f"""<p>✅ <strong>Correo Enviado Exitosamente</strong></p>
                                        <ul>
                                            <li><strong>Destinatario:</strong> {partner.email or 'Sin correo'}</li>
                                            <li><strong>Fecha de envío:</strong> {fields.Datetime.context_timestamp(evaluation, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M')}</li>
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

                            evaluation.message_post(
                                body=f"""<p>❌ <strong>Error al Enviar Correo</strong></p>
                                        <ul>
                                            <li><strong>Error:</strong> {error_msg}</li>
                                            <li><strong>Fecha:</strong> {fields.Datetime.context_timestamp(evaluation, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M')}</li>
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

                    self.env.cr.commit()

                except Exception as e:
                    error_msg = str(e)
                    self.env.cr.rollback()

                    _logger.error(
                        f"❌ Error al procesar evaluación - "
                        f"Cliente: {partner_id}, "
                        f"Técnico: {technician_id}, "
                        f"Visita: {visit_date}: {error_msg}"
                    )

                    error_count += 1

            _logger.info(
                f"📊 Resumen de envío: "
                f"Enviadas: {sent_count}, "
                f"Actualizadas: {updated_count}, "
                f"Errores: {error_count}, "
                f"Total grupos procesados: {len(grouped_tickets)}"
            )

            return True

        except Exception as e:
            self.env.cr.rollback()
            _logger.error(f"❌ Error general en el cron de evaluaciones: {str(e)}")
            raise

    @api.model
    def _cron_send_pending_reminders(self):
        _logger.info("🔔 Iniciando envío de recordatorios automáticos...")

        try:
            yesterday = fields.Datetime.now() - timedelta(hours=24)

            domain = [
                ('state', '=', 'sent'),
                ('email_sent_date', '<=', yesterday),
                ('reminder_count', '<', 2),
                ('expiration_date', '>', fields.Datetime.now())
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

            _logger.info(
                f"✅ Se enviaron {sent_count} recordatorios de {len(pending_evaluations)} evaluaciones pendientes"
            )

        except Exception as e:
            _logger.error(f"❌ Error en cron de recordatorios: {str(e)}")
            raise