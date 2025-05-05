# -*- coding: utf-8 -*-
from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
import logging
from datetime import datetime, date, timedelta, time
import calendar
import babel
import base64
import traceback

_logger = logging.getLogger(__name__)




class EvaluacionPersonal(models.Model):
    _name = 'evaluacion.personal'
    _inherit = ['mail.thread']
    _description = 'Evaluación Integral del Personal Técnico'
    _order = 'fecha desc, id desc'
    
    # CAMPOS BÁSICOS
    name = fields.Char('EVALUACIÓN N°', 
        default='New',
        copy=False,
        required=True,
        readonly=True,
        tracking=True
    )
    
    fecha = fields.Date(
        string='Fecha de evaluación',
        default=fields.Date.today(),
        required=True,
        tracking=True
    )
    
    usuario_id = fields.Many2one(
        'res.users', 
        string='Técnico', 
        required=True,
        tracking=True
    )
    
    nombre_usuario = fields.Char(
        related='usuario_id.name',
        string='Nombre de usuario',
        store=True
    )
    
    evaluador_id = fields.Many2one(
        'res.users',
        string='Evaluador',
        default=lambda self: self.env.user,
        required=True,
        tracking=True
    )
    
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('enviado', 'Enviado')
    ], default='borrador', tracking=True, string='Estado')

    # Relación con otros modelos
   

    @api.depends('usuario_id', 'fecha')
    def _compute_reparaciones(self):
        for record in self:
            if record.usuario_id and record.fecha:
                inicio_mes = record.fecha.replace(day=1)
                fin_mes = inicio_mes + relativedelta(months=1)
                reparaciones = self.env['reparaciones.reparaciones'].search_count([
                    ('responsable_id', '=', record.usuario_id.id),
                    ('create_date', '>=', inicio_mes),
                    ('create_date', '<', fin_mes),
                ])
                record.cantidad_reparaciones = reparaciones
            else:
                record.cantidad_reparaciones = 0
    @api.depends('usuario_id', 'fecha')
    def _compute_tickets(self):
        for record in self:
            if record.usuario_id and record.fecha:
                inicio_mes = record.fecha.replace(day=1)
                fin_mes = inicio_mes + relativedelta(months=1)
                tickets = self.env['ticket.alquiler'].search_count([
                    ('responsable', '=', record.usuario_id.id),
                    ('agenda', '>=', inicio_mes),
                    ('agenda', '<', fin_mes),
                ])
                record.cantidad_tickets = tickets
            else:
                record.cantidad_tickets = 0

    # EVALUACIÓN DE DESEMPEÑO TÉCNICO
    calidad_trabajo = fields.Selection([
        ('1', 'Trabajo con múltiples errores graves'),
        ('2', 'Trabajo con errores frecuentes'),
        ('3', 'Trabajo aceptable con errores menores'),
        ('4', 'Trabajo de buena calidad'),
        ('5', 'Trabajo de excelente calidad')
    ], string='Calidad del Trabajo', tracking=True)
    
    conocimiento_tecnico = fields.Selection([
        ('1', 'Conocimiento muy limitado'),
        ('2', 'Conocimiento básico'),
        ('3', 'Conocimiento adecuado'),
        ('4', 'Buen conocimiento'),
        ('5', 'Excelente dominio técnico')
    ], string='Conocimiento Técnico', tracking=True)
    
    resolucion_problemas = fields.Selection([
        ('1', 'No resuelve problemas básicos'),
        ('2', 'Resuelve con mucha ayuda'),
        ('3', 'Resuelve con apoyo ocasional'),
        ('4', 'Resuelve independientemente'),
        ('5', 'Resuelve y previene problemas')
    ], string='Resolución de Problemas', tracking=True)

    uso_herramientas = fields.Selection([
        ('1', 'Uso inadecuado de herramientas'),
        ('2', 'Uso básico de herramientas'),
        ('3', 'Uso correcto de herramientas'),
        ('4', 'Buen manejo de herramientas'),
        ('5', 'Excelente manejo de herramientas')
    ], string='Uso de Herramientas', tracking=True)

    # EVALUACIÓN ACTITUDINAL
    puntualidad = fields.Selection([
        ('1', 'Frecuentes llegadas tarde'),
        ('2', 'Ocasionalmente tarde'),
        ('3', 'Generalmente puntual'),
        ('4', 'Siempre puntual'),
        ('5', 'Llega antes de tiempo')
    ], string='Puntualidad', tracking=True)

    compromiso = fields.Selection([
        ('1', 'Muy poco comprometido'),
        ('2', 'Poco comprometido'),
        ('3', 'Compromiso aceptable'),
        ('4', 'Buen compromiso'),
        ('5', 'Altamente comprometido')
    ], string='Compromiso', tracking=True)

    trabajo_equipo = fields.Selection([
        ('1', 'No trabaja en equipo'),
        ('2', 'Dificultad para integrarse'),
        ('3', 'Trabaja en equipo cuando necesario'),
        ('4', 'Buen trabajo en equipo'),
        ('5', 'Excelente integración y liderazgo')
    ], string='Trabajo en Equipo', tracking=True)

    # ATENCIÓN AL CLIENTE
    trato_cliente = fields.Selection([
        ('1', 'Maltrato al cliente'),
        ('2', 'Trato deficiente'),
        ('3', 'Trato correcto'),
        ('4', 'Buen trato'),
        ('5', 'Excelente atención')
    ], string='Trato al Cliente', tracking=True)

    comunicacion_cliente = fields.Selection([
        ('1', 'No explica procedimientos'),
        ('2', 'Explicaciones confusas'),
        ('3', 'Explicaciones básicas'),
        ('4', 'Buenas explicaciones'),
        ('5', 'Explicaciones excelentes')
    ], string='Comunicación con Cliente', tracking=True)

    manejo_conflictos = fields.Selection([
        ('1', 'No maneja conflictos'),
        ('2', 'Manejo deficiente'),
        ('3', 'Manejo aceptable'),
        ('4', 'Buen manejo'),
        ('5', 'Excelente resolución')
    ], string='Manejo de Conflictos', tracking=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('evaluacion.personal') or 'New'
        return super(EvaluacionPersonal, self).create(vals)

    

    def ver_reparaciones(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reparaciones',
            'view_mode': 'list,form',
            'res_model': 'reparaciones.reparaciones',
            'domain': [('responsable_id', '=', self.usuario_id.id)],
            'context': "{'create': False}"
        }

    def ver_tickets(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tickets',
            'view_mode': 'list,form',
            'res_model': 'ticket.alquiler',
            'domain': [('responsable', '=', self.usuario_id.id)],
            'context': "{'create': False}"
        }

     # MÉTRICAS OBJETIVAS
    cantidad_reparaciones = fields.Integer(
        string="Reparaciones Realizadas",
        compute='_compute_reparaciones',
        store=True
    )
    
    objetivo_reparaciones = fields.Integer(
        string="Objetivo de Reparaciones",
        compute='_compute_objetivos',
        store=True
    )
    
    porcentaje_reparaciones = fields.Float(
        string="% Cumplimiento Reparaciones",
        compute='_compute_porcentajes',
        store=True
    )
    
    cantidad_tickets = fields.Integer(
        string="Tickets Atendidos",
        compute='_compute_tickets',
        store=True
    )
    
    objetivo_tickets = fields.Integer(
        string="Objetivo de Tickets",
        compute='_compute_objetivos',
        store=True
    )
    
    porcentaje_tickets = fields.Float(
        string="% Cumplimiento Tickets",
        compute='_compute_porcentajes',
        store=True
    )

    # CAMPOS DE RESULTADOS
    puntaje_objetivos = fields.Float(
        string="Puntaje Objetivos (50%)",
        compute='_compute_puntajes',
        store=True
    )
    
    puntaje_desempeno = fields.Float(
        string="Puntaje Desempeño (50%)",
        compute='_compute_puntajes',
        store=True
    )
    
    puntaje_total = fields.Float(
        string="Puntaje Total",
        compute='_compute_puntaje_total',
        store=True
    )
    
    nivel_desempeno = fields.Selection([
        ('deficiente', 'Deficiente (0-60)'),
        ('regular', 'Regular (61-70)'),
        ('bueno', 'Bueno (71-80)'),
        ('muy_bueno', 'Muy Bueno (81-90)'),
        ('excelente', 'Excelente (91-100)')
    ], string='Nivel de Desempeño', compute='_compute_nivel', store=True)

    # CAMPOS INFORMATIVOS
    mes = fields.Char(string='Mes', compute='_compute_mes_anio', store=True)
    anio = fields.Char(string='Año', compute='_compute_mes_anio', store=True)
    dias_evaluados = fields.Integer('Días Evaluados', compute='_compute_dias_evaluados')
    promedio_diario_reparaciones = fields.Float('Promedio Diario Reparaciones', compute='_compute_promedios')
    promedio_diario_tickets = fields.Float('Promedio Diario Tickets', compute='_compute_promedios')

    @api.depends('fecha')
    def _compute_mes_anio(self):
        for record in self:
            if record.fecha:
                locale = self.env.context.get('lang') or 'es_ES'
                record.mes = babel.dates.format_date(record.fecha, format='MMMM', locale=locale).capitalize()
                record.anio = record.fecha.strftime('%Y')
            else:
                record.mes = False
                record.anio = False

    @api.depends('fecha')
    def _compute_dias_evaluados(self):
        for record in self:
            if record.fecha:
                inicio_mes = record.fecha.replace(day=1)
                fin_mes = inicio_mes + relativedelta(months=1)
                dias = 0
                current = inicio_mes
                while current < fin_mes:
                    if current.weekday() < 5:  # Lunes a Viernes
                        dias += 1
                    elif current.weekday() == 5:  # Sábado
                        dias += 0.5
                    current += relativedelta(days=1)
                record.dias_evaluados = dias
            else:
                record.dias_evaluados = 0

    @api.depends('cantidad_reparaciones', 'objetivo_reparaciones',
            'cantidad_tickets', 'objetivo_tickets')

    def _compute_porcentajes(self):
        for record in self:
            # Calcular porcentaje de reparaciones
            if record.objetivo_reparaciones:
                record.porcentaje_reparaciones = min(100, (record.cantidad_reparaciones / record.objetivo_reparaciones) * 100)
            else:
                record.porcentaje_reparaciones = 0
                
            # Calcular porcentaje de tickets
            if record.objetivo_tickets:
                record.porcentaje_tickets = min(100, (record.cantidad_tickets / record.objetivo_tickets) * 100)
            else:
                record.porcentaje_tickets = 0
    @api.depends('porcentaje_reparaciones', 'porcentaje_tickets',
            'calidad_trabajo', 'conocimiento_tecnico', 'resolucion_problemas',
            'uso_herramientas', 'puntualidad', 'compromiso', 'trabajo_equipo',
            'trato_cliente', 'comunicacion_cliente', 'manejo_conflictos')
    def _compute_puntajes(self):
        for record in self:
            # Puntaje de métricas objetivas (40%)
            puntaje_reparaciones = (record.porcentaje_reparaciones * 0.20)  # 20%
            puntaje_tickets = (record.porcentaje_tickets * 0.20)            # 20%
            
            # Puntaje desempeño técnico (25%)
            campos_tecnicos = [
                'calidad_trabajo', 'conocimiento_tecnico', 
                'resolucion_problemas', 'uso_herramientas'
            ]
            puntaje_tecnico = self._calcular_promedio_campos(campos_tecnicos) * 0.25
            
            # Puntaje actitudinal (20%)
            campos_actitud = [
                'puntualidad', 'compromiso', 'trabajo_equipo'
            ]
            puntaje_actitud = self._calcular_promedio_campos(campos_actitud) * 0.20
            
            # Puntaje atención cliente (15%)
            campos_cliente = [
                'trato_cliente', 'comunicacion_cliente', 'manejo_conflictos'
            ]
            puntaje_cliente = self._calcular_promedio_campos(campos_cliente) * 0.15
            
            # Asignar puntajes
            record.puntaje_objetivos = puntaje_reparaciones + puntaje_tickets
            record.puntaje_desempeno = puntaje_tecnico + puntaje_actitud + puntaje_cliente
    def _calcular_promedio_campos(self, campos):
                """Método auxiliar para calcular promedio de campos de evaluación"""
                suma = 0
                count = 0
                for campo in campos:
                    valor = self[campo]
                    if valor:
                        suma += int(valor)
                        count += 1
                return (suma / count / 5 * 100) if count > 0 else 0       

    @api.depends('puntaje_objetivos', 'puntaje_desempeno')
    def _compute_puntaje_total(self):
        for record in self:
            record.puntaje_total = record.puntaje_objetivos + record.puntaje_desempeno
    def _compute_promedios(self):
        for record in self:
            if record.dias_evaluados:
                record.promedio_diario_reparaciones = record.cantidad_reparaciones / record.dias_evaluados
                record.promedio_diario_tickets = record.cantidad_tickets / record.dias_evaluados
            else:
                record.promedio_diario_reparaciones = 0
                record.promedio_diario_tickets = 0



    # CAMPOS DE RETROALIMENTACIÓN
    fortalezas = fields.Text(
        string='Fortalezas Identificadas',
        compute='_compute_retroalimentacion',
        store=True
    )
    
    areas_mejora = fields.Text(
        string='Áreas de Mejora',
        compute='_compute_retroalimentacion',
        store=True
    )
    
    plan_accion = fields.Text(
        string='Plan de Acción',
        compute='_compute_retroalimentacion',
        store=True
    )
    
    comentarios = fields.Text(
        string='Comentarios Adicionales',
        tracking=True
    )
    
    # CAMPOS DE SEGUIMIENTO
    proxima_evaluacion = fields.Date(
        string='Fecha Próxima Evaluación',
        compute='_compute_proxima_evaluacion',
        store=True
    )
    
    objetivos_proximos = fields.Text(
        string='Objetivos para Próximo Periodo',
        compute='_compute_objetivos_proximos',
        store=True
    )
    
    necesita_capacitacion = fields.Boolean(
        string='Necesita Capacitación',
        compute='_compute_necesidades',
        store=True
    )
    
    temas_capacitacion = fields.Text(
        string='Temas de Capacitación Requeridos',
        compute='_compute_necesidades',
        store=True
    )

    @api.depends('puntaje_total', 'nivel_desempeno', 'porcentaje_reparaciones', 
                'porcentaje_tickets', 'calidad_trabajo', 'conocimiento_tecnico',
                'resolucion_problemas', 'uso_herramientas', 'puntualidad',
                'compromiso', 'trabajo_equipo', 'trato_cliente',
                'comunicacion_cliente', 'manejo_conflictos')
    def _compute_retroalimentacion(self):
        for record in self:
            # Analizar fortalezas
            fortalezas = []
            if record.porcentaje_reparaciones >= 90:
                fortalezas.append("- Excelente rendimiento en reparaciones")
            if record.porcentaje_tickets >= 90:
                fortalezas.append("- Alto nivel de atención en tickets")
            if int(record.calidad_trabajo or '0') >= 4:
                fortalezas.append("- Alta calidad en el trabajo")
            if int(record.conocimiento_tecnico or '0') >= 4:
                fortalezas.append("- Buen dominio técnico")
            if int(record.trato_cliente or '0') >= 4:
                fortalezas.append("- Excelente atención al cliente")
            
            # Analizar áreas de mejora
            areas_mejora = []
            if record.porcentaje_reparaciones < 70:
                areas_mejora.append("- Mejorar productividad en reparaciones")
            if record.porcentaje_tickets < 70:
                areas_mejora.append("- Incrementar atención de tickets")
            if int(record.calidad_trabajo or '0') <= 3:
                areas_mejora.append("- Mejorar calidad del trabajo")
            if int(record.conocimiento_tecnico or '0') <= 3:
                areas_mejora.append("- Fortalecer conocimientos técnicos")
            if int(record.puntualidad or '0') <= 3:
                areas_mejora.append("- Mejorar puntualidad")
            
            # Generar plan de acción
            plan_accion = []
            if record.porcentaje_reparaciones < 70:
                plan_accion.append("1. Establecer metas diarias de reparaciones")
                plan_accion.append("2. Revisar y optimizar procesos de reparación")
            if record.porcentaje_tickets < 70:
                plan_accion.append("3. Mejorar gestión y priorización de tickets")
            if int(record.conocimiento_tecnico or '0') <= 3:
                plan_accion.append("4. Programar capacitaciones técnicas específicas")
            if int(record.calidad_trabajo or '0') <= 3:
                plan_accion.append("5. Implementar checklist de calidad")
            
            record.fortalezas = "\n".join(fortalezas) if fortalezas else "No se identificaron fortalezas destacadas"
            record.areas_mejora = "\n".join(areas_mejora) if areas_mejora else "No se identificaron áreas críticas de mejora"
            record.plan_accion = "\n".join(plan_accion) if plan_accion else "No se requiere plan de acción específico"

    @api.depends('fecha', 'state')
    def _compute_proxima_evaluacion(self):
        for record in self:
            if record.fecha and record.state == 'finalizado':
                record.proxima_evaluacion = record.fecha + relativedelta(months=1)
            else:
                record.proxima_evaluacion = False

    @api.depends('puntaje_total', 'areas_mejora', 'porcentaje_reparaciones', 'porcentaje_tickets')
    def _compute_objetivos_proximos(self):
        for record in self:
            objetivos = []
            
            # Objetivos de reparaciones
            if record.porcentaje_reparaciones < 100:
                mejora_necesaria = 100 - record.porcentaje_reparaciones
                objetivos.append(f"- Incrementar productividad en reparaciones en {mejora_necesaria:.1f}%")
            
            # Objetivos de tickets
            if record.porcentaje_tickets < 100:
                mejora_necesaria = 100 - record.porcentaje_tickets
                objetivos.append(f"- Mejorar atención de tickets en {mejora_necesaria:.1f}%")
            
            # Objetivos basados en áreas de mejora
            if int(record.calidad_trabajo or '0') <= 3:
                objetivos.append("- Reducir errores en reparaciones")
            if int(record.conocimiento_tecnico or '0') <= 3:
                objetivos.append("- Completar capacitaciones técnicas programadas")
            if int(record.trato_cliente or '0') <= 3:
                objetivos.append("- Mejorar satisfacción del cliente")
            
            record.objetivos_proximos = "\n".join(objetivos) if objetivos else "Mantener el nivel actual de desempeño"

    @api.depends('calidad_trabajo', 'conocimiento_tecnico', 'resolucion_problemas',
                'puntaje_total', 'nivel_desempeno')
    def _compute_necesidades(self):
        for record in self:
            necesita_capacitacion = False
            temas = []
            
            # Evaluar necesidades de capacitación
            if int(record.conocimiento_tecnico or '0') <= 3:
                necesita_capacitacion = True
                temas.append("- Actualización en conocimientos técnicos")
            
            if int(record.resolucion_problemas or '0') <= 3:
                necesita_capacitacion = True
                temas.append("- Resolución de problemas técnicos")
            
            if int(record.calidad_trabajo or '0') <= 3:
                necesita_capacitacion = True
                temas.append("- Procedimientos y estándares de calidad")
            
            if record.porcentaje_reparaciones < 70:
                necesita_capacitacion = True
                temas.append("- Optimización de procesos de reparación")
            
            if int(record.trato_cliente or '0') <= 3:
                necesita_capacitacion = True
                temas.append("- Atención al cliente y manejo de situaciones difíciles")
            
            record.necesita_capacitacion = necesita_capacitacion
            record.temas_capacitacion = "\n".join(temas) if temas else "No se requieren capacitaciones específicas"

    def programar_siguiente_evaluacion(self):
        self.proxima_evaluacion = self.fecha + relativedelta(months=1)
        
    def generar_reporte_evaluacion(self):
        return {
            'type': 'ir.actions.report',
            'report_name': 'evaluacion.personal.report',
            'report_type': 'qweb-pdf',
            'data': {'id': self.id}
        }

    def enviar_recordatorio_evaluacion(self):
        template = self.env.ref('evaluacion_personal.email_template_recordatorio_evaluacion')
        for record in self:
            template.send_mail(record.id, force_send=True)

    def actualizar_estado_evaluacion(self):
        for record in self:
            if record.puntaje_total >= 90:
                record.write({'state': 'finalizado'})
            elif record.puntaje_total >= 70:
                record.write({'state': 'aprobado'})
            else:
                record.write({'state': 'en_revision'})

    def action_programar_capacitacion(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Programar Capacitación',
            'res_model': 'wizard.programar.capacitacion',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_evaluacion_id': self.id}
        }


    @api.depends('fecha', 'dias_evaluados')
    def _compute_objetivos(self):
        for record in self:
            if record.dias_evaluados:
                dias_completos = int(record.dias_evaluados)
                medios_dias = (record.dias_evaluados - dias_completos) * 2
                
                # 4 reparaciones por día completo, 2 por medio día
                record.objetivo_reparaciones = int((dias_completos * 4) + (medios_dias * 2))
                # 3 tickets por día completo, 1.5 por medio día
                record.objetivo_tickets = int((dias_completos * 3) + (medios_dias * 1.5))
            else:
                record.objetivo_reparaciones = 0
                record.objetivo_tickets = 0

    @api.depends('puntaje_total')
    def _compute_nivel(self):
        for record in self:
            if record.puntaje_total >= 91:
                record.nivel_desempeno = 'excelente'
            elif record.puntaje_total >= 81:
                record.nivel_desempeno = 'muy_bueno'
            elif record.puntaje_total >= 71:
                record.nivel_desempeno = 'bueno'
            elif record.puntaje_total >= 61:
                record.nivel_desempeno = 'regular'
            else:
                record.nivel_desempeno = 'deficiente'

    def action_duplicar_abril(self):
        """
        Acción manual para duplicar evaluaciones que evaluaron Marzo,
        útil para ejecutar manualmente en mayo si no se hizo automáticamente.
        Se puede ejecutar sobre varios registros a la vez.
        """
        _logger.info("📌 Acción manual: Duplicar Evaluaciones de Abril (basadas en Marzo)")

        hoy = fields.Date.today()
        inicio_abril = date(2025, 4, 1)
        fin_abril = date(2025, 4, 30)

        # Buscar todas las evaluaciones con mes marzo y año 2025 (no solo las seleccionadas)
        evaluaciones = self.env['evaluacion.personal'].search([
            ('mes', '=', 'Marzo'),
            ('anio', '=', '2025'),
            ('state', '=', 'enviado')
        ])

        _logger.info("🔍 Evaluaciones encontradas para duplicar: %s", len(evaluaciones))

        duplicadas = 0
        omitidas = 0

        for eval in evaluaciones:
            ya_existe = self.search_count([
                ('usuario_id', '=', eval.usuario_id.id),
                ('fecha', '>=', inicio_abril),
                ('fecha', '<=', fin_abril),
            ])
            if ya_existe:
                _logger.info("⏭️ Ya existe evaluación de abril para %s. Se omite.", eval.usuario_id.name)
                omitidas += 1
                continue

            nueva = eval.copy({
                'name': 'New',
                'fecha': hoy,
                'state': 'borrador',
                'cantidad_reparaciones': False,
                'cantidad_tickets': False,
                'porcentaje_reparaciones': False,
                'porcentaje_tickets': False,
                'puntaje_objetivos': False,
                'puntaje_desempeno': False,
                'puntaje_total': False,
                'nivel_desempeno': False,
                'fortalezas': False,
                'areas_mejora': False,
                'plan_accion': False
            })

            _logger.info("✅ Evaluación duplicada para %s", eval.usuario_id.name)
            self._notificar_evaluador(nueva)
            duplicadas += 1

        message = f"Se duplicaron {duplicadas} evaluaciones. Omitidas: {omitidas}."
        _logger.info(message)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Evaluaciones Duplicadas',
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }


    @api.model
    def _cron_duplicar_evaluaciones_mensuales(self):
        """
        Cron que se ejecuta el último día de cada mes.
        Duplica evaluaciones del mes anterior (basado en campos 'mes' y 'anio'),
        solo si el técnico aún no tiene evaluación este mes.
        """
        hoy = fields.Date.today()
        ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]

        _logger.info("🗓️ Hoy: %s | Último día del mes: %s", hoy, ultimo_dia)

        if hoy.day != ultimo_dia:
            _logger.info("⏸️ No es el último día del mes. El cron no hace nada.")
            return

        _logger.info("⏳ [CRON] Iniciando duplicación automática de evaluaciones mensuales")

        try:
            inicio_mes_actual = hoy.replace(day=1)
            mes_anterior = inicio_mes_actual - relativedelta(months=1)

            mes_nombre = babel.dates.format_date(mes_anterior, format='MMMM', locale='es_ES').capitalize()
            anio_texto = mes_anterior.strftime('%Y')

            _logger.info("📆 Buscando evaluaciones con mes='%s', año='%s'", mes_nombre, anio_texto)

            evaluaciones = self.search([
                ('mes', '=', mes_nombre),
                ('anio', '=', anio_texto),
                ('state', '=', 'enviado')
            ])

            _logger.info("🔍 Evaluaciones encontradas: %s", len(evaluaciones))

            duplicadas = 0
            omitidas = 0

            for eval in evaluaciones:
                existe = self.search_count([
                    ('usuario_id', '=', eval.usuario_id.id),
                    ('fecha', '>=', inicio_mes_actual),
                ])

                if existe:
                    _logger.info("⏭️ Ya existe evaluación este mes para %s. Se omite.", eval.usuario_id.name)
                    omitidas += 1
                    continue

                nueva = eval.copy({
                    'name': 'New',
                    'fecha': hoy,
                    'state': 'borrador',
                    'cantidad_reparaciones': False,
                    'cantidad_tickets': False,
                    'porcentaje_reparaciones': False,
                    'porcentaje_tickets': False,
                    'puntaje_objetivos': False,
                    'puntaje_desempeno': False,
                    'puntaje_total': False,
                    'nivel_desempeno': False,
                    'fortalezas': False,
                    'areas_mejora': False,
                    'plan_accion': False
                })

                _logger.info("✅ Duplicada evaluación para %s", eval.usuario_id.name)
                self._notificar_evaluador(nueva)
                duplicadas += 1

            _logger.info("🟢 Finalizado. Duplicadas: %s | Omitidas: %s", duplicadas, omitidas)

        except Exception as e:
            _logger.error("❌ Error en cron duplicación: %s", str(e))
            _logger.error(traceback.format_exc())

        
    def _notificar_evaluador(self, evaluacion):
        """Notifica al evaluador sobre la nueva evaluación pendiente"""
        template = self.env.ref('evaluacion_personal.email_template_nueva_evaluacion', False)
        if template:
            template.send_mail(evaluacion.id, force_send=True)
    def action_enviar_reportes_masivo(self):
        """Acción para abrir el asistente de envío masivo de reportes"""
        return {
            'name': 'Enviar Reportes por Correo',
            'type': 'ir.actions.act_window',
            'res_model': 'evaluacion.personal.envio.masivo',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_ids': self.ids,
            }
        }


class EvaluacionPersonalEnvioMasivo(models.TransientModel):
    _name = 'evaluacion.personal.envio.masivo'
    _description = 'Asistente para Envío Masivo de Reportes'
    
    email = fields.Char(string='Correo Electrónico', required=True)
    subject = fields.Char(string='Asunto', default='Reportes de Evaluación del Personal', required=True)
    body = fields.Html(
       string='Cuerpo del Mensaje',
        default="""
            <p>Lincoln:</p>
            <p>Por medio de la presente,  hago llegar los reportes de evaluación del personal. Los documentos adjuntos contienen información detallada sobre el desempeño, competencias y resultados de cada colaborador durante el período evaluado.</p>
            <p>Saludos cordiales,</p>            
        """,
        required=True
    )
    evaluacion_ids = fields.Many2many('evaluacion.personal', string='Evaluaciones', readonly=True)
    
    @api.model
    def default_get(self, fields_list):
        _logger.info("Iniciando default_get en EvaluacionPersonalEnvioMasivo")
        res = super(EvaluacionPersonalEnvioMasivo, self).default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            _logger.info(f"Active IDs encontrados: {active_ids}")
            res['evaluacion_ids'] = [(6, 0, active_ids)]
            res['email'] = self.env.user.email
            _logger.info(f"Email del usuario actual: {self.env.user.email}")
        else:
            _logger.warning("No se encontraron IDs activos en el contexto")
        return res
    
    def action_enviar_reportes(self):
        _logger.info("Iniciando action_enviar_reportes")
        self.ensure_one()
        
        if not self.evaluacion_ids:
            _logger.warning("No hay evaluaciones seleccionadas para enviar")
            return {'type': 'ir.actions.act_window_close'}
        
        _logger.info(f"Preparando envío para {len(self.evaluacion_ids)} evaluaciones")
        
        # Lista para almacenar los adjuntos
        attachments = []
        
        # Obtener el reporte para las evaluaciones
        _logger.info("Buscando reporte PDF para evaluaciones")
        report = self.env['ir.actions.report'].search([
            ('model', '=', 'evaluacion.personal'),
            ('report_type', '=', 'qweb-pdf')
        ], limit=1)
        
        if not report:
            _logger.error("No se encontró un reporte PDF para evaluaciones")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'No se encontró un reporte PDF para evaluaciones',
                    'type': 'danger',
                    'sticky': True,
                }
            }
        
        _logger.info(f"Reporte encontrado: {report.name}, report_name: {report.report_name}")
        
        # Generar reportes PDF para cada evaluación seleccionada
        for evaluacion in self.evaluacion_ids:
            # Generar nombre de archivo
            filename = f"Evaluacion_{evaluacion.name}_{evaluacion.nombre_usuario}.pdf"
            _logger.info(f"Procesando evaluación {evaluacion.name}, generando archivo: {filename}")
            
            try:
                # Usar correctamente el método render del reporte
                _logger.info(f"Intentando generar PDF para evaluación ID: {evaluacion.id}")
                pdf_content, report_format = report.sudo()._render(report.report_name, res_ids=[evaluacion.id])
                _logger.info(f"PDF generado exitosamente para {evaluacion.name}, tamaño: {len(pdf_content)} bytes, formato: {report_format}")
                
                # Crear adjunto
                attachment_vals = {
                    'name': filename,
                    'datas': base64.b64encode(pdf_content),
                    'res_model': 'evaluacion.personal',
                    'res_id': evaluacion.id,
                    'type': 'binary',
                }
                attachment = self.env['ir.attachment'].create(attachment_vals)
                _logger.info(f"Adjunto creado con ID: {attachment.id}")
                attachments.append((filename, pdf_content))
            except Exception as e:
                _logger.error(f"Error al generar el PDF para {evaluacion.name}: {str(e)}")
                _logger.error(f"Detalles del error: {traceback.format_exc()}")
        
        if not attachments:
            _logger.error("No se pudo generar ningún reporte PDF")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'No se pudo generar ningún reporte PDF',
                    'type': 'danger',
                    'sticky': True,
                }
            }
        
        _logger.info(f"Se generaron {len(attachments)} adjuntos correctamente")
        
        # Enviar correo con todos los reportes adjuntos
        try:
            _logger.info(f"Preparando envío de correo a: {self.email}")
            
            # Verificar servidor de correo saliente
            mail_server = self.env['ir.mail_server'].search([], limit=1)
            if not mail_server:
                _logger.warning("No se encontró un servidor de correo saliente configurado")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Advertencia',
                        'message': 'No hay un servidor de correo saliente configurado en el sistema. Por favor, configúrelo en Ajustes > Técnico > Correo electrónico > Servidores de correo saliente.',
                        'type': 'warning',
                        'sticky': True,
                    }
                }
            _logger.info(f"Usando servidor de correo: {mail_server.name}")
            
            # Crear los adjuntos de manera adecuada para mail.mail
            attachment_ids = []
            for filename, content in attachments:
                _logger.info(f"Creando adjunto para correo: {filename}")
                attachment_data = {
                    'name': filename,
                    'datas': base64.b64encode(content),
                    'res_model': 'mail.mail',
                    'res_id': False,
                    'type': 'binary',
                }
                attachment = self.env['ir.attachment'].create(attachment_data)
                attachment_ids.append(attachment.id)
                _logger.info(f"Adjunto para correo creado con ID: {attachment.id}")
            
            mail_values = {
                'subject': self.subject,
                'body_html': self.body,
                'email_to': self.email,
                'attachment_ids': [(6, 0, attachment_ids)],
                'mail_server_id': mail_server.id,
                'auto_delete': False,
            }
            
            _logger.info("Creando objeto mail.mail")
            mail = self.env['mail.mail'].create(mail_values)
            _logger.info(f"Enviando correo con ID: {mail.id}")
            
            # Usar el método send que incluye más logs
            try:
                _logger.info("Iniciando envío de correo...")
                mail.send(raise_exception=True)
                _logger.info(f"Estado del correo después del envío: {mail.state}")
                
                if mail.state == 'sent':
                    _logger.info("Correo enviado exitosamente")
                    
                    # NUEVA LÓGICA: Actualizar estado de evaluaciones a "enviado"
                    _logger.info("Actualizando estado de evaluaciones a 'enviado'")
                    for evaluacion in self.evaluacion_ids:
                        evaluacion.write({'state': 'enviado'})
                        _logger.info(f"Evaluación {evaluacion.name} actualizada a estado 'enviado'")
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Éxito',
                            'message': f'Se han enviado {len(attachments)} reportes al correo {self.email} y se actualizaron los estados a "enviado"',
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                else:
                    _logger.warning(f"El correo no se envió correctamente. Estado: {mail.state}, Detalles: {mail.failure_reason}")
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Advertencia',
                            'message': f'El correo no pudo enviarse correctamente. Por favor, revise la configuración del servidor de correo. Detalles: {mail.failure_reason or "Sin detalles disponibles"}',
                            'type': 'warning',
                            'sticky': True,
                        }
                    }
            except Exception as email_error:
                _logger.error(f"Error durante el envío del correo: {str(email_error)}")
                _logger.error(f"Detalles del error: {traceback.format_exc()}")
                
                # Verificar si hay problemas con la configuración del servidor
                if "Connection refused" in str(email_error) or "could not connect" in str(email_error):
                    error_message = f"No se pudo conectar al servidor de correo. Verifique la configuración (host, puerto, SSL/TLS). Detalles: {str(email_error)}"
                elif "Authentication failed" in str(email_error) or "authentication" in str(email_error):
                    error_message = f"Fallo de autenticación en el servidor de correo. Verifique el usuario y contraseña. Detalles: {str(email_error)}"
                else:
                    error_message = f"Error al enviar el correo: {str(email_error)}"
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': error_message,
                        'type': 'danger',
                        'sticky': True,
                    }
                }
            
        except Exception as e:
            _logger.error(f"Error al enviar correo: {str(e)}")
            _logger.error(f"Detalles del error: {traceback.format_exc()}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Error al enviar el correo: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }