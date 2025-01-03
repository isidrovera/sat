from odoo import models, fields, api
from datetime import datetime, timedelta
import pytz
import logging

_logger = logging.getLogger(__name__)

class ClientServiceEvaluation(models.Model):
    _name = 'client.service.evaluation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Evaluación de Servicio Técnico'

    name = fields.Char('Referencia', default='New', readonly=True)
    ticket_ids = fields.Many2many('ticket.alquiler', string='Tickets', tracking=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', store=True)
    technician_id = fields.Many2one('res.users', string='Técnico', store=True)
    evaluation_date = fields.Datetime('Fecha de Evaluación', default=fields.Datetime.now)
    expiration_date = fields.Datetime('Fecha de Expiración', compute='_compute_expiration_date', store=True)
    
    state = fields.Selection([
        ('draft', 'Pendiente'),
        ('sent', 'Enviada'),
        ('completed', 'Completada'),
        ('expired', 'Expirada')
    ], default='draft', tracking=True)

    # Aspectos clave del servicio
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
    # Preguntas específicas
    realizo_pruebas = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No')
    ], string='¿Realizó pruebas del equipo?')

    consulto_suministros = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No')
    ], string='¿Consultó sobre el stock de suministros?')

    consulto_problemas = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No')
    ], string='¿Preguntó si había problemas adicionales?')

    # Campos adicionales
    comentarios = fields.Text('Comentarios o Sugerencias')
    token = fields.Char('Token de Evaluación')

    # Campos calculados
    puntaje_servicio = fields.Float('Puntaje del Servicio (%)', compute='_compute_puntaje', store=True)
    nivel_atencion = fields.Selection([
        ('excelente', 'Excelente (90-100%)'),
        ('bueno', 'Bueno (80-89%)'),
        ('regular', 'Regular (70-79%)'),
        ('deficiente', 'Deficiente (<70%)')
    ], compute='_compute_niveles', store=True)

    requiere_atencion = fields.Boolean('Requiere Atención', compute='_compute_requiere_atencion', store=True)
    analisis_detallado = fields.Text('Análisis Detallado', compute='_compute_analisis', store=True)
    recomendaciones_mejora = fields.Text('Recomendaciones de Mejora', compute='_compute_recomendaciones', store=True)
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('client.service.evaluation') or 'New'
        if not vals.get('token'):
            vals['token'] = self._generate_token()
        return super(ClientServiceEvaluation, self).create(vals)

    def _generate_token(self):
        import uuid
        return str(uuid.uuid4())

    @api.depends('evaluation_date')
    def _compute_expiration_date(self):
        for record in self:
            if record.evaluation_date:
                record.expiration_date = record.evaluation_date + timedelta(days=2)
            else:
                record.expiration_date = False

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
• Protocolo de Atención:
  - Mejorar saludo inicial
  - Presentarse adecuadamente
  - Explicar el proceso a realizar""")

            if int(record.diagnostico_problema or '0') <= 3:
                recomendaciones.append("""
• Diagnóstico:
  - Realizar revisión más detallada
  - Documentar los problemas encontrados
  - Explicar el diagnóstico al cliente""")

            if int(record.solucion_problema or '0') <= 3:
                recomendaciones.append("""
• Solución Técnica:
  - Asegurar solución completa
  - Verificar funcionamiento
  - Documentar la solución aplicada""")

            if int(record.explicacion_trabajo or '0') <= 3:
                recomendaciones.append("""
• Comunicación:
  - Mejorar explicación del servicio
  - Usar lenguaje comprensible
  - Verificar entendimiento del cliente""")

            if int(record.limpieza_orden or '0') <= 3:
                recomendaciones.append("""
• Limpieza:
  - Mejorar orden del área
  - Limpiar equipo después del servicio
  - Verificar área de trabajo""")

            if record.realizo_pruebas == 'no':
                recomendaciones.append("""
• Pruebas:
  - Implementar protocolo de pruebas
  - Realizar pruebas con cliente
  - Documentar resultados""")

            if record.consulto_suministros == 'no':
                recomendaciones.append("""
• Suministros:
  - Verificar stock de consumibles
  - Registrar necesidades
  - Informar al cliente""")

            if record.consulto_problemas == 'no':
                recomendaciones.append("""
• Revisión General:
  - Consultar problemas adicionales
  - Revisar otros equipos
  - Ofrecer mantenimiento preventivo""")

            # Recomendación general basada en puntaje total
            if record.puntaje_servicio < 70:
                recomendaciones.insert(1, """
ACCIONES URGENTES:
• Capacitación inmediata en:
  - Protocolos de servicio
  - Atención al cliente
  - Habilidades técnicas
• Seguimiento semanal
• Supervisión directa""")

            record.recomendaciones_mejora = '\n'.join(recomendaciones)
    @api.model
    def _cron_check_expired_evaluations(self):
        """Cron para marcar evaluaciones expiradas"""
        _logger.info("Verificando evaluaciones expiradas...")
        current_datetime = fields.Datetime.now()
        domain = [
            ('state', '=', 'sent'),
            ('evaluation_date', '<', current_datetime - timedelta(days=2))
        ]
        expired_evaluations = self.search(domain)
        if expired_evaluations:
            expired_evaluations.write({'state': 'expired'})
            _logger.info(f"Se marcaron {len(expired_evaluations)} evaluaciones como expiradas")

    @api.model
    def _cron_send_service_evaluations(self):
        """Cron para enviar evaluaciones a las 8 PM"""
        _logger.info("Iniciando envío de evaluaciones de servicio...")
        
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
            _logger.info(f"Se encontraron {len(tickets)} tickets para evaluar")

            # Agrupar tickets por técnico y cliente
            grouped_tickets = {}
            for ticket in tickets:
                key = (ticket.partner_id.id, ticket.responsable.id)
                if key not in grouped_tickets:
                    grouped_tickets[key] = []
                grouped_tickets[key].append(ticket.id)

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
                        # Crear una única evaluación por técnico y cliente
                        evaluation = self.create({
                            'ticket_ids': [(6, 0, ticket_ids)],
                            'partner_id': partner_id,
                            'technician_id': technician_id,
                            'state': 'sent',
                            'retiro_tecnico': 'con_visto',  # Valor por defecto para el nuevo campo
                        })
                        _logger.info(
                            f"Evaluación creada - Cliente: {partner_id}, "
                            f"Técnico: {technician_id}, "
                            f"Tickets: {len(ticket_ids)}"
                        )
                        
                        # Enviar correo
                        template = self.env.ref('sat.email_template_service_evaluation')
                        if template:
                            template.send_mail(evaluation.id, force_send=True)
                            _logger.info(f"Correo enviado para la evaluación: {evaluation.name}")
                        else:
                            _logger.warning("No se encontró la plantilla de correo para evaluación")
                            
                        self.env.cr.commit()  # Commit después de cada evaluación exitosa
                    except Exception as e:
                        self.env.cr.rollback()  # Rollback en caso de error
                        _logger.error(
                            f"Error al procesar evaluación - Cliente: {partner_id}, "
                            f"Técnico: {technician_id}: {str(e)}"
                        )
        except Exception as e:
            self.env.cr.rollback()
            _logger.error(f"Error general en el cron de evaluaciones: {str(e)}")
            raise
                    
    # Agregar este campo junto con los otros campos al inicio del modelo
    ticket_id = fields.Many2one('ticket.alquiler', string='Ticket Principal', compute='_compute_ticket_id', store=True)

    # Agregar este método compute junto con los otros métodos compute
    @api.depends('ticket_ids')
    def _compute_ticket_id(self):
        """Compute para mantener compatibilidad con la plantilla de correo"""
        for record in self:
            record.ticket_id = record.ticket_ids[0] if record.ticket_ids else False

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
        """ Método para retornar la acción del portal """
        return {
            'type': 'ir.actions.act_url',
            'url': '/my/evaluations/%s' % self.id,
            'target': 'self',
            'res_id': self.id,
        }

    def action_mark_as_completed(self):
        """Método para marcar como completada la evaluación"""
        self.ensure_one()
        self.write({'state': 'completed'})

    def action_reset_to_draft(self):
        """Método para regresar a borrador la evaluación"""
        self.ensure_one()
        self.write({'state': 'draft'})

    def action_send_reminder(self):
        """Método para enviar recordatorio de evaluación"""
        self.ensure_one()
        template = self.env.ref('sat.email_template_service_evaluation_reminder', False)
        if template:
            template.send_mail(self.id, force_send=True)
            return True
        return False 
            
            
    color = fields.Integer(string='Índice de Color', default=0)
    
    @api.depends('estado')
    def _compute_color(self):
        """Calcula el color del ticket basado en su estado"""
        for record in self:
            if record.estado == 'borrador':
                record.color = 0  # Gris - Para tickets en borrador
            elif record.estado == 'asignado':
                record.color = 4  # Azul - Para tickets asignados
            elif record.estado == 'en_proceso':
                record.color = 3  # Amarillo - Para tickets en proceso
            elif record.estado == 'finalizado':
                record.color = 10  # Verde - Para tickets finalizados
            elif record.estado == 'cancelado':
                record.color = 1  # Rojo - Para tickets cancelados
            else:
                record.color = 0  # Color por defecto