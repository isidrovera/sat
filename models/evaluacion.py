# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
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
    
    # ============================================================
    # CAMPOS BÁSICOS
    # ============================================================
    
    name = fields.Char(
        'EVALUACIÓN N°', 
        default='New',
        copy=False,
        required=True,
        readonly=True,
        tracking=True
    )
    
    fecha = fields.Date(
        string='Fecha de evaluación',
        default=fields.Date.today,
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
        ('en_revision', 'En Revisión'),
        ('aprobado', 'Aprobado'),
        ('enviado', 'Enviado'),
        ('finalizado', 'Finalizado')
    ], default='borrador', tracking=True, string='Estado', required=True)

    # ============================================================
    # ANÁLISIS DIARIO (NUEVO)
    # ============================================================
    
    detalle_diario_ids = fields.One2many(
        'evaluacion.personal.detalle.diario',
        'evaluacion_id',
        string='Análisis Diario',
        help='Desglose día por día de reparaciones y tickets realizados'
    )
    
    tiene_detalle_diario = fields.Boolean(
        string='Tiene Detalle Generado',
        compute='_compute_tiene_detalle',
        store=True
    )
    
    total_dias_trabajados = fields.Integer(
        string='Días con Actividad',
        compute='_compute_estadisticas_diarias',
        store=True
    )
    
    total_dias_sin_actividad = fields.Integer(
        string='Días sin Actividad',
        compute='_compute_estadisticas_diarias',
        store=True
    )
    
    mejor_dia_fecha = fields.Date(
        string='Mejor Día',
        compute='_compute_estadisticas_diarias',
        store=True
    )
    
    mejor_dia_total = fields.Integer(
        string='Trabajos en Mejor Día',
        compute='_compute_estadisticas_diarias',
        store=True
    )
    
    peor_dia_fecha = fields.Date(
        string='Día Más Bajo',
        compute='_compute_estadisticas_diarias',
        store=True
    )
    
    peor_dia_total = fields.Integer(
        string='Trabajos en Día Más Bajo',
        compute='_compute_estadisticas_diarias',
        store=True
    )

    # ============================================================
    # MÉTRICAS OBJETIVAS
    # ============================================================
    
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

    # ============================================================
    # EVALUACIÓN DE DESEMPEÑO TÉCNICO
    # ============================================================
    
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

    # ============================================================
    # EVALUACIÓN ACTITUDINAL
    # ============================================================
    
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

    # ============================================================
    # ATENCIÓN AL CLIENTE
    # ============================================================
    
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

    # ============================================================
    # CAMPOS DE RESULTADOS
    # ============================================================
    
    puntaje_objetivos = fields.Float(
        string="Puntaje Objetivos (40%)",
        compute='_compute_puntajes',
        store=True
    )
    
    puntaje_desempeno = fields.Float(
        string="Puntaje Desempeño (60%)",
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

    # ============================================================
    # CAMPOS INFORMATIVOS
    # ============================================================
    
    mes = fields.Char(
        string='Mes',
        compute='_compute_mes_anio',
        store=True
    )
    
    anio = fields.Char(
        string='Año',
        compute='_compute_mes_anio',
        store=True
    )
    
    dias_evaluados = fields.Integer(
        'Días Evaluados',
        compute='_compute_dias_evaluados',
        store=True
    )
    
    promedio_diario_reparaciones = fields.Float(
        'Promedio Diario Reparaciones',
        compute='_compute_promedios',
        store=True
    )
    
    promedio_diario_tickets = fields.Float(
        'Promedio Diario Tickets',
        compute='_compute_promedios',
        store=True
    )

    # ============================================================
    # CAMPOS DE RETROALIMENTACIÓN
    # ============================================================
    
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
    
    # ============================================================
    # CAMPOS DE SEGUIMIENTO
    # ============================================================
    
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

    # ============================================================
    # CONSTRAINTS Y VALIDACIONES
    # ============================================================
    
    @api.constrains('fecha')
    def _check_fecha(self):
        """Valida que la fecha de evaluación no sea futura"""
        for record in self:
            if record.fecha and record.fecha > fields.Date.today():
                raise ValidationError(
                    "La fecha de evaluación no puede ser futura. "
                    "Por favor, seleccione una fecha válida."
                )

    @api.constrains('usuario_id', 'fecha')
    def _check_evaluacion_duplicada(self):
        """Previene evaluaciones duplicadas para el mismo técnico en el mismo mes"""
        for record in self:
            if record.usuario_id and record.fecha:
                inicio_mes = record.fecha.replace(day=1)
                fin_mes = inicio_mes + relativedelta(months=1)
                
                duplicado = self.search_count([
                    ('id', '!=', record.id),
                    ('usuario_id', '=', record.usuario_id.id),
                    ('fecha', '>=', inicio_mes),
                    ('fecha', '<', fin_mes)
                ])
                
                if duplicado:
                    raise ValidationError(
                        f"Ya existe una evaluación para {record.usuario_id.name} "
                        f"en el mes de {record.mes} {record.anio}."
                    )

    # ============================================================
    # MÉTODOS COMPUTE - ANÁLISIS DIARIO (NUEVO)
    # ============================================================
    
    @api.depends('detalle_diario_ids')
    def _compute_tiene_detalle(self):
        """Verifica si ya se generó el detalle diario"""
        for record in self:
            record.tiene_detalle_diario = bool(record.detalle_diario_ids)
    
    @api.depends('detalle_diario_ids.total_trabajos', 'detalle_diario_ids.es_dia_laboral')
    def _compute_estadisticas_diarias(self):
        """Calcula estadísticas del análisis diario"""
        for record in self:
            detalles_laborales = record.detalle_diario_ids.filtered('es_dia_laboral')
            
            if detalles_laborales:
                # Días con y sin actividad
                record.total_dias_trabajados = len(detalles_laborales.filtered(lambda d: d.total_trabajos > 0))
                record.total_dias_sin_actividad = len(detalles_laborales.filtered(lambda d: d.total_trabajos == 0))
                
                # Mejor día
                mejor_dia = max(detalles_laborales, key=lambda d: d.total_trabajos, default=None)
                if mejor_dia:
                    record.mejor_dia_fecha = mejor_dia.fecha
                    record.mejor_dia_total = mejor_dia.total_trabajos
                else:
                    record.mejor_dia_fecha = False
                    record.mejor_dia_total = 0
                
                # Peor día (solo días con actividad)
                dias_con_actividad = detalles_laborales.filtered(lambda d: d.total_trabajos > 0)
                peor_dia = min(dias_con_actividad, key=lambda d: d.total_trabajos, default=None)
                if peor_dia:
                    record.peor_dia_fecha = peor_dia.fecha
                    record.peor_dia_total = peor_dia.total_trabajos
                else:
                    record.peor_dia_fecha = False
                    record.peor_dia_total = 0
            else:
                record.total_dias_trabajados = 0
                record.total_dias_sin_actividad = 0
                record.mejor_dia_fecha = False
                record.mejor_dia_total = 0
                record.peor_dia_fecha = False
                record.peor_dia_total = 0

    # ============================================================
    # MÉTODOS COMPUTE - MÉTRICAS BÁSICAS
    # ============================================================
    
    @api.depends('usuario_id', 'fecha')
    def _compute_reparaciones(self):
        """Calcula la cantidad de reparaciones realizadas en el mes"""
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
        """Calcula la cantidad de tickets atendidos en el mes"""
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

    @api.depends('fecha')
    def _compute_mes_anio(self):
        """Calcula el mes y año en formato texto"""
        for record in self:
            if record.fecha:
                locale = self.env.context.get('lang') or 'es_ES'
                record.mes = babel.dates.format_date(
                    record.fecha, 
                    format='MMMM', 
                    locale=locale
                ).capitalize()
                record.anio = record.fecha.strftime('%Y')
            else:
                record.mes = False
                record.anio = False

    @api.depends('fecha')
    def _compute_dias_evaluados(self):
        """Calcula los días laborables del mes (L-V completos, Sábados 0.5)"""
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
                    # Domingo no cuenta (weekday() == 6)
                    current += relativedelta(days=1)
                    
                record.dias_evaluados = dias
            else:
                record.dias_evaluados = 0

    @api.depends('fecha', 'dias_evaluados')
    def _compute_objetivos(self):
        """
        Calcula objetivos basados en días laborables:
        - 4 reparaciones por día completo
        - 3 tickets por día completo
        - Ajustado proporcionalmente para medios días
        """
        for record in self:
            if record.dias_evaluados > 0:
                dias_completos = int(record.dias_evaluados)
                medios_dias = (record.dias_evaluados - dias_completos) * 2
                
                # 4 reparaciones por día completo, 2 por medio día
                record.objetivo_reparaciones = int((dias_completos * 4) + (medios_dias * 2))
                
                # 3 tickets por día completo, 1.5 por medio día
                record.objetivo_tickets = int((dias_completos * 3) + (medios_dias * 1.5))
            else:
                # Objetivos mínimos por seguridad
                record.objetivo_reparaciones = 1
                record.objetivo_tickets = 1

    @api.depends('cantidad_reparaciones', 'objetivo_reparaciones',
                 'cantidad_tickets', 'objetivo_tickets')
    def _compute_porcentajes(self):
        """Calcula porcentajes de cumplimiento (máximo 100%)"""
        for record in self:
            # Porcentaje de reparaciones
            if record.objetivo_reparaciones > 0:
                porcentaje_rep = (record.cantidad_reparaciones / record.objetivo_reparaciones) * 100
                record.porcentaje_reparaciones = min(100, porcentaje_rep)
            else:
                record.porcentaje_reparaciones = 0
                
            # Porcentaje de tickets
            if record.objetivo_tickets > 0:
                porcentaje_tic = (record.cantidad_tickets / record.objetivo_tickets) * 100
                record.porcentaje_tickets = min(100, porcentaje_tic)
            else:
                record.porcentaje_tickets = 0

    @api.depends('dias_evaluados', 'cantidad_reparaciones', 'cantidad_tickets')
    def _compute_promedios(self):
        """Calcula promedios diarios de productividad"""
        for record in self:
            if record.dias_evaluados > 0:
                record.promedio_diario_reparaciones = record.cantidad_reparaciones / record.dias_evaluados
                record.promedio_diario_tickets = record.cantidad_tickets / record.dias_evaluados
            else:
                record.promedio_diario_reparaciones = 0
                record.promedio_diario_tickets = 0

    @api.depends('porcentaje_reparaciones', 'porcentaje_tickets',
                 'calidad_trabajo', 'conocimiento_tecnico', 'resolucion_problemas',
                 'uso_herramientas', 'puntualidad', 'compromiso', 'trabajo_equipo',
                 'trato_cliente', 'comunicacion_cliente', 'manejo_conflictos')
    def _compute_puntajes(self):
        """
        Calcula puntajes ponderados:
        - Objetivos (40%): Reparaciones 20% + Tickets 20%
        - Desempeño (60%): Técnico 25% + Actitud 20% + Cliente 15%
        """
        for record in self:
            # === PUNTAJE DE MÉTRICAS OBJETIVAS (40%) ===
            puntaje_reparaciones = record.porcentaje_reparaciones * 0.20  # 20%
            puntaje_tickets = record.porcentaje_tickets * 0.20            # 20%
            
            # === PUNTAJE DESEMPEÑO TÉCNICO (25%) ===
            campos_tecnicos = [
                'calidad_trabajo', 'conocimiento_tecnico', 
                'resolucion_problemas', 'uso_herramientas'
            ]
            puntaje_tecnico = record._calcular_promedio_campos(campos_tecnicos) * 0.25
            
            # === PUNTAJE ACTITUDINAL (20%) ===
            campos_actitud = [
                'puntualidad', 'compromiso', 'trabajo_equipo'
            ]
            puntaje_actitud = record._calcular_promedio_campos(campos_actitud) * 0.20
            
            # === PUNTAJE ATENCIÓN CLIENTE (15%) ===
            campos_cliente = [
                'trato_cliente', 'comunicacion_cliente', 'manejo_conflictos'
            ]
            puntaje_cliente = record._calcular_promedio_campos(campos_cliente) * 0.15
            
            # === ASIGNAR PUNTAJES ===
            record.puntaje_objetivos = puntaje_reparaciones + puntaje_tickets
            record.puntaje_desempeno = puntaje_tecnico + puntaje_actitud + puntaje_cliente

    @api.depends('puntaje_objetivos', 'puntaje_desempeno')
    def _compute_puntaje_total(self):
        """Suma los puntajes parciales para obtener el total"""
        for record in self:
            record.puntaje_total = record.puntaje_objetivos + record.puntaje_desempeno

    @api.depends('puntaje_total')
    def _compute_nivel(self):
        """Clasifica el nivel de desempeño según puntaje total"""
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

    @api.depends('puntaje_total', 'nivel_desempeno', 'porcentaje_reparaciones', 
                 'porcentaje_tickets', 'calidad_trabajo', 'conocimiento_tecnico',
                 'resolucion_problemas', 'uso_herramientas', 'puntualidad',
                 'compromiso', 'trabajo_equipo', 'trato_cliente',
                 'comunicacion_cliente', 'manejo_conflictos')
    def _compute_retroalimentacion(self):
        """Genera retroalimentación inteligente basada en el desempeño"""
        for record in self:
            # === ANALIZAR FORTALEZAS ===
            fortalezas = []
            
            if record.porcentaje_reparaciones >= 90:
                fortalezas.append("• Excelente rendimiento en reparaciones")
            if record.porcentaje_tickets >= 90:
                fortalezas.append("• Alto nivel de atención en tickets")
            if int(record.calidad_trabajo or '0') >= 4:
                fortalezas.append("• Alta calidad en el trabajo")
            if int(record.conocimiento_tecnico or '0') >= 4:
                fortalezas.append("• Buen dominio técnico")
            if int(record.trato_cliente or '0') >= 4:
                fortalezas.append("• Excelente atención al cliente")
            if int(record.resolucion_problemas or '0') >= 4:
                fortalezas.append("• Capacidad destacada para resolver problemas")
            if int(record.puntualidad or '0') >= 4:
                fortalezas.append("• Excelente puntualidad")
            if int(record.trabajo_equipo or '0') >= 4:
                fortalezas.append("• Gran capacidad de trabajo en equipo")
            
            # === ANALIZAR ÁREAS DE MEJORA ===
            areas_mejora = []
            
            if record.porcentaje_reparaciones < 70:
                areas_mejora.append("• Mejorar productividad en reparaciones")
            if record.porcentaje_tickets < 70:
                areas_mejora.append("• Incrementar atención de tickets")
            if int(record.calidad_trabajo or '0') <= 3:
                areas_mejora.append("• Mejorar calidad del trabajo")
            if int(record.conocimiento_tecnico or '0') <= 3:
                areas_mejora.append("• Fortalecer conocimientos técnicos")
            if int(record.puntualidad or '0') <= 3:
                areas_mejora.append("• Mejorar puntualidad")
            if int(record.resolucion_problemas or '0') <= 3:
                areas_mejora.append("• Desarrollar capacidad de resolución de problemas")
            if int(record.trato_cliente or '0') <= 3:
                areas_mejora.append("• Mejorar atención y trato al cliente")
            if int(record.comunicacion_cliente or '0') <= 3:
                areas_mejora.append("• Fortalecer comunicación con clientes")
            
            # === GENERAR PLAN DE ACCIÓN ===
            plan_accion = []
            contador = 1
            
            if record.porcentaje_reparaciones < 70:
                plan_accion.append(f"{contador}. Establecer metas diarias de reparaciones")
                contador += 1
                plan_accion.append(f"{contador}. Revisar y optimizar procesos de reparación")
                contador += 1
            
            if record.porcentaje_tickets < 70:
                plan_accion.append(f"{contador}. Mejorar gestión y priorización de tickets")
                contador += 1
            
            if int(record.conocimiento_tecnico or '0') <= 3:
                plan_accion.append(f"{contador}. Programar capacitaciones técnicas específicas")
                contador += 1
            
            if int(record.calidad_trabajo or '0') <= 3:
                plan_accion.append(f"{contador}. Implementar checklist de calidad")
                contador += 1
            
            if int(record.puntualidad or '0') <= 3:
                plan_accion.append(f"{contador}. Establecer recordatorios y plan de puntualidad")
                contador += 1
            
            if int(record.trato_cliente or '0') <= 3 or int(record.comunicacion_cliente or '0') <= 3:
                plan_accion.append(f"{contador}. Capacitación en servicio al cliente")
                contador += 1
            
            # === ASIGNAR RETROALIMENTACIÓN ===
            record.fortalezas = "\n".join(fortalezas) if fortalezas else "Se recomienda continuar desarrollando habilidades en todas las áreas evaluadas."
            record.areas_mejora = "\n".join(areas_mejora) if areas_mejora else "No se identificaron áreas críticas de mejora. Mantener el nivel actual."
            record.plan_accion = "\n".join(plan_accion) if plan_accion else "Continuar con el desempeño actual. Próxima evaluación para seguimiento."

    @api.depends('fecha', 'state')
    def _compute_proxima_evaluacion(self):
        """Calcula la fecha de la próxima evaluación (mensual)"""
        for record in self:
            if record.fecha and record.state in ['enviado', 'finalizado']:
                record.proxima_evaluacion = record.fecha + relativedelta(months=1)
            else:
                record.proxima_evaluacion = False

    @api.depends('puntaje_total', 'areas_mejora', 'porcentaje_reparaciones', 'porcentaje_tickets')
    def _compute_objetivos_proximos(self):
        """Define objetivos inteligentes para el próximo periodo"""
        for record in self:
            objetivos = []
            
            # === OBJETIVOS DE PRODUCTIVIDAD ===
            if record.porcentaje_reparaciones < 100:
                mejora_necesaria = 100 - record.porcentaje_reparaciones
                objetivos.append(f"• Incrementar productividad en reparaciones en {mejora_necesaria:.1f}%")
            
            if record.porcentaje_tickets < 100:
                mejora_necesaria = 100 - record.porcentaje_tickets
                objetivos.append(f"• Mejorar atención de tickets en {mejora_necesaria:.1f}%")
            
            # === OBJETIVOS DE CALIDAD ===
            if int(record.calidad_trabajo or '0') <= 3:
                objetivos.append("• Reducir errores y mejorar calidad en reparaciones")
            
            if int(record.conocimiento_tecnico or '0') <= 3:
                objetivos.append("• Completar capacitaciones técnicas programadas")
            
            # === OBJETIVOS DE SERVICIO ===
            if int(record.trato_cliente or '0') <= 3:
                objetivos.append("• Mejorar satisfacción del cliente")
            
            if int(record.comunicacion_cliente or '0') <= 3:
                objetivos.append("• Fortalecer habilidades de comunicación con clientes")
            
            # === OBJETIVOS ACTITUDINALES ===
            if int(record.puntualidad or '0') <= 3:
                objetivos.append("• Mejorar puntualidad y asistencia")
            
            if int(record.compromiso or '0') <= 3:
                objetivos.append("• Incrementar compromiso con las tareas asignadas")
            
            record.objetivos_proximos = "\n".join(objetivos) if objetivos else "Mantener el excelente nivel de desempeño actual y buscar oportunidades de mejora continua."

    @api.depends('calidad_trabajo', 'conocimiento_tecnico', 'resolucion_problemas',
                 'puntaje_total', 'nivel_desempeno', 'trato_cliente', 'porcentaje_reparaciones')
    def _compute_necesidades(self):
        """Identifica necesidades de capacitación de forma inteligente"""
        for record in self:
            necesita_capacitacion = False
            temas = []
            
            # === CAPACITACIÓN TÉCNICA ===
            if int(record.conocimiento_tecnico or '0') <= 3:
                necesita_capacitacion = True
                temas.append("• Actualización en conocimientos técnicos y nuevas tecnologías")
            
            if int(record.resolucion_problemas or '0') <= 3:
                necesita_capacitacion = True
                temas.append("• Metodologías de diagnóstico y resolución de problemas técnicos")
            
            if int(record.calidad_trabajo or '0') <= 3:
                necesita_capacitacion = True
                temas.append("• Procedimientos, estándares de calidad y control de errores")
            
            if int(record.uso_herramientas or '0') <= 3:
                necesita_capacitacion = True
                temas.append("• Manejo adecuado de herramientas y equipos técnicos")
            
            # === CAPACITACIÓN EN PRODUCTIVIDAD ===
            if record.porcentaje_reparaciones < 70:
                necesita_capacitacion = True
                temas.append("• Optimización de procesos y gestión del tiempo en reparaciones")
            
            if record.porcentaje_tickets < 70:
                necesita_capacitacion = True
                temas.append("• Gestión eficiente de tickets y priorización de tareas")
            
            # === CAPACITACIÓN EN SERVICIO AL CLIENTE ===
            if int(record.trato_cliente or '0') <= 3:
                necesita_capacitacion = True
                temas.append("• Atención al cliente y manejo de situaciones difíciles")
            
            if int(record.comunicacion_cliente or '0') <= 3:
                necesita_capacitacion = True
                temas.append("• Comunicación efectiva y explicación de procedimientos técnicos")
            
            if int(record.manejo_conflictos or '0') <= 3:
                necesita_capacitacion = True
                temas.append("• Resolución de conflictos y negociación con clientes")
            
            # === CAPACITACIÓN EN HABILIDADES BLANDAS ===
            if int(record.trabajo_equipo or '0') <= 3:
                necesita_capacitacion = True
                temas.append("• Trabajo en equipo y colaboración efectiva")
            
            if int(record.compromiso or '0') <= 3:
                necesita_capacitacion = True
                temas.append("• Desarrollo de compromiso y responsabilidad laboral")
            
            # === ASIGNAR RESULTADOS ===
            record.necesita_capacitacion = necesita_capacitacion
            record.temas_capacitacion = "\n".join(temas) if temas else "No se requieren capacitaciones específicas en este momento. Continuar con el desarrollo profesional regular."

    # ============================================================
    # MÉTODOS AUXILIARES
    # ============================================================
    
    def _calcular_promedio_campos(self, campos):
        """
        Calcula el promedio de campos de evaluación (1-5) y lo convierte a porcentaje
        
        Args:
            campos (list): Lista de nombres de campos a promediar
            
        Returns:
            float: Promedio en escala 0-100
        """
        self.ensure_one()
        
        suma = 0
        count = 0
        
        for campo in campos:
            valor = self[campo]
            if valor:
                suma += int(valor)
                count += 1
        
        if count > 0:
            promedio = suma / count  # Promedio en escala 1-5
            return (promedio / 5) * 100  # Convertir a escala 0-100
        else:
            return 0

    def _notificar_evaluador(self, evaluacion):
        """
        Notifica al evaluador sobre una nueva evaluación pendiente
        
        Args:
            evaluacion (recordset): Evaluación a notificar
        """
        try:
            template = self.env.ref('evaluacion_personal.email_template_nueva_evaluacion', raise_if_not_found=False)
            if template:
                template.send_mail(evaluacion.id, force_send=True)
                _logger.info(f"✉️ Notificación enviada a {evaluacion.evaluador_id.name} para evaluación {evaluacion.name}")
            else:
                _logger.warning("⚠️ No se encontró la plantilla de correo para nuevas evaluaciones")
        except Exception as e:
            _logger.error(f"❌ Error al notificar evaluador: {str(e)}")

    # ============================================================
    # MÉTODOS CRUD
    # ============================================================
    
    @api.model
    def create(self, vals):
        """Genera secuencia automática y crea detalle diario"""
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('evaluacion.personal') or 'New'
        
        evaluacion = super(EvaluacionPersonal, self).create(vals)
        
        # Generar detalle diario automáticamente
        evaluacion.action_generar_detalle_diario()
        
        return evaluacion

    def write(self, vals):
        """Actualiza y regenera detalle diario si cambia usuario o fecha"""
        result = super(EvaluacionPersonal, self).write(vals)
        
        # Si cambió el usuario o la fecha, regenerar detalle
        if 'usuario_id' in vals or 'fecha' in vals:
            self.action_regenerar_detalle_diario()
        
        return result

    # ============================================================
    # ACCIONES DE BOTONES
    # ============================================================
    
    def ver_reparaciones(self):
        """Abre vista de reparaciones del técnico evaluado"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Reparaciones - {self.nombre_usuario}',
            'view_mode': 'tree,form',
            'res_model': 'reparaciones.reparaciones',
            'domain': [('responsable_id', '=', self.usuario_id.id)],
            'context': {'create': False}
        }

    def ver_tickets(self):
        """Abre vista de tickets del técnico evaluado"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Tickets - {self.nombre_usuario}',
            'view_mode': 'tree,form',
            'res_model': 'ticket.alquiler',
            'domain': [('responsable', '=', self.usuario_id.id)],
            'context': {'create': False}
        }

    def programar_siguiente_evaluacion(self):
        """Programa la siguiente evaluación mensual"""
        self.ensure_one()
        if self.fecha:
            self.proxima_evaluacion = self.fecha + relativedelta(months=1)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Evaluación Programada',
                    'message': f'Próxima evaluación programada para {self.proxima_evaluacion.strftime("%d/%m/%Y")}',
                    'type': 'success',
                    'sticky': False,
                }
            }

    def generar_reporte_evaluacion(self):
        """Genera reporte PDF de la evaluación"""
        self.ensure_one()
        return {
            'type': 'ir.actions.report',
            'report_name': 'evaluacion_personal.report_evaluacion_personal',
            'report_type': 'qweb-pdf',
            'data': {'id': self.id}
        }

    def enviar_recordatorio_evaluacion(self):
        """Envía recordatorio por correo sobre evaluación pendiente"""
        self.ensure_one()
        try:
            template = self.env.ref('evaluacion_personal.email_template_recordatorio_evaluacion', raise_if_not_found=False)
            if template:
                template.send_mail(self.id, force_send=True)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Recordatorio Enviado',
                        'message': f'Se envió recordatorio a {self.evaluador_id.name}',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Advertencia',
                        'message': 'No se encontró la plantilla de recordatorio',
                        'type': 'warning',
                        'sticky': False,
                    }
                }
        except Exception as e:
            _logger.error(f"Error al enviar recordatorio: {str(e)}")
            raise ValidationError(f"No se pudo enviar el recordatorio: {str(e)}")

    def actualizar_estado_evaluacion(self):
        """Actualiza el estado de la evaluación según su puntaje"""
        for record in self:
            if record.puntaje_total >= 90:
                record.write({'state': 'finalizado'})
            elif record.puntaje_total >= 70:
                record.write({'state': 'aprobado'})
            else:
                record.write({'state': 'en_revision'})

    def action_programar_capacitacion(self):
        """Abre wizard para programar capacitación"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Programar Capacitación',
            'res_model': 'wizard.programar.capacitacion',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_evaluacion_id': self.id}
        }

    def action_enviar_reportes_masivo(self):
        """Abre wizard para envío masivo de reportes por correo"""
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

    def action_duplicar_mes_anterior(self):
        """
        Duplica evaluaciones del mes anterior para el mes actual.
        Útil para ejecutar manualmente si el cron automático falló.
        Puede ejecutarse sobre varios registros a la vez.
        """
        _logger.info("📌 Acción manual: Duplicar Evaluaciones del Mes Anterior")

        hoy = fields.Date.today()
        inicio_mes_actual = hoy.replace(day=1)
        fin_mes_actual = inicio_mes_actual + relativedelta(months=1)
        
        mes_anterior = inicio_mes_actual - relativedelta(months=1)
        mes_nombre = babel.dates.format_date(mes_anterior, format='MMMM', locale='es_ES').capitalize()
        anio_texto = mes_anterior.strftime('%Y')

        # Buscar todas las evaluaciones del mes anterior enviadas
        evaluaciones = self.search([
            ('mes', '=', mes_nombre),
            ('anio', '=', anio_texto),
            ('state', '=', 'enviado')
        ])

        _logger.info(f"🔍 Evaluaciones encontradas para duplicar: {len(evaluaciones)} ({mes_nombre} {anio_texto})")

        duplicadas = 0
        omitidas = 0

        for eval in evaluaciones:
            # Verificar si ya existe evaluación este mes
            ya_existe = self.search_count([
                ('usuario_id', '=', eval.usuario_id.id),
                ('fecha', '>=', inicio_mes_actual),
                ('fecha', '<', fin_mes_actual),
            ])
            
            if ya_existe:
                _logger.info(f"⏭️ Ya existe evaluación de {mes_nombre} para {eval.usuario_id.name}. Se omite.")
                omitidas += 1
                continue

            # Duplicar evaluación
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
                'plan_accion': False,
                'comentarios': False,
            })

            _logger.info(f"✅ Evaluación duplicada para {eval.usuario_id.name} - {nueva.name}")
            self._notificar_evaluador(nueva)
            duplicadas += 1

        message = f"Se duplicaron {duplicadas} evaluaciones del mes de {mes_nombre}. Omitidas: {omitidas}."
        _logger.info(f"✅ {message}")

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

    # ============================================================
    # ACCIONES ANÁLISIS DIARIO (NUEVO)
    # ============================================================
    
    def action_generar_detalle_diario(self):
        """
        Genera el análisis diario de productividad
        Se ejecuta automáticamente al crear/actualizar la evaluación
        """
        for record in self:
            if not record.usuario_id or not record.fecha:
                continue
            
            _logger.info(f"📊 Generando análisis diario para {record.nombre_usuario} - {record.mes} {record.anio}")
            
            # Eliminar detalles existentes
            record.detalle_diario_ids.unlink()
            
            # Calcular rango del mes
            inicio_mes = record.fecha.replace(day=1)
            fin_mes = inicio_mes + relativedelta(months=1)
            
            # Iterar cada día del mes
            current_date = inicio_mes
            detalles_creados = 0
            
            while current_date < fin_mes:
                # Crear detalle para este día
                detalle_vals = {
                    'evaluacion_id': record.id,
                    'fecha': current_date,
                }
                
                self.env['evaluacion.personal.detalle.diario'].create(detalle_vals)
                detalles_creados += 1
                
                # Siguiente día
                current_date += relativedelta(days=1)
            
            _logger.info(f"✅ Análisis diario generado: {detalles_creados} días procesados")
    
    def action_regenerar_detalle_diario(self):
        """
        Botón manual para regenerar el análisis diario
        Útil si los datos cambiaron
        """
        self.ensure_one()
        
        self.action_generar_detalle_diario()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Análisis Actualizado',
                'message': f'Se regeneró el análisis diario con {len(self.detalle_diario_ids)} días',
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_ver_dia_detalle(self):
        """Abre vista de un día específico con todos sus trabajos"""
        self.ensure_one()
        
        # Esta acción se llamará desde el detalle diario
        # Por ahora retorna la vista tree de detalles
        return {
            'type': 'ir.actions.act_window',
            'name': f'Análisis Diario - {self.nombre_usuario}',
            'view_mode': 'tree,form',
            'res_model': 'evaluacion.personal.detalle.diario',
            'domain': [('evaluacion_id', '=', self.id)],
            'context': {'create': False, 'delete': False}
        }

    # ============================================================
    # CRON JOBS
    # ============================================================
    
    @api.model
    def _cron_duplicar_evaluaciones_mensuales(self):
        """
        Cron que se ejecuta el último día de cada mes a las 23:59.
        Duplica evaluaciones del mes anterior para crear borradores del mes actual.
        Solo duplica si el técnico no tiene evaluación este mes.
        """
        hoy = fields.Date.today()
        ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]

        _logger.info(f"🗓️ [CRON EVALUACIONES] Ejecutando - Fecha: {hoy} | Último día del mes: {ultimo_dia}")

        # Verificar si es el último día del mes
        if hoy.day != ultimo_dia:
            _logger.info("⏸️ No es el último día del mes. El cron no hace nada.")
            return

        _logger.info("⏳ [CRON] Iniciando duplicación automática de evaluaciones mensuales")

        try:
            # Calcular mes anterior
            inicio_mes_actual = hoy.replace(day=1)
            mes_anterior = inicio_mes_actual - relativedelta(months=1)

            mes_nombre = babel.dates.format_date(mes_anterior, format='MMMM', locale='es_ES').capitalize()
            anio_texto = mes_anterior.strftime('%Y')

            _logger.info(f"📆 Buscando evaluaciones con mes='{mes_nombre}', año='{anio_texto}', state='enviado'")

            # Buscar evaluaciones del mes anterior
            evaluaciones = self.search([
                ('mes', '=', mes_nombre),
                ('anio', '=', anio_texto),
                ('state', '=', 'enviado')
            ])

            _logger.info(f"🔍 Evaluaciones encontradas: {len(evaluaciones)}")

            duplicadas = 0
            omitidas = 0

            for eval in evaluaciones:
                # Verificar si ya existe evaluación este mes
                existe = self.search_count([
                    ('usuario_id', '=', eval.usuario_id.id),
                    ('fecha', '>=', inicio_mes_actual),
                ])

                if existe:
                    _logger.info(f"⏭️ Ya existe evaluación este mes para {eval.usuario_id.name}. Se omite.")
                    omitidas += 1
                    continue

                # Duplicar evaluación
                nueva = eval.copy({
                    'name': 'New',
                    'fecha': hoy,
                    'state': 'borrador',
                    'evaluador_id': eval.evaluador_id.id,
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
                    'plan_accion': False,
                    'comentarios': False,
                })

                _logger.info(f"✅ Duplicada evaluación para {eval.usuario_id.name} - {nueva.name}")
                self._notificar_evaluador(nueva)
                duplicadas += 1

            _logger.info(f"🟢 [CRON] Finalizado. Duplicadas: {duplicadas} | Omitidas: {omitidas}")

        except Exception as e:
            _logger.error(f"❌ Error en cron duplicación: {str(e)}")
            _logger.error(traceback.format_exc())


# ============================================================
# MODELO DE DETALLE DIARIO (NUEVO)
# ============================================================

class EvaluacionPersonalDetalleDiario(models.Model):
    _name = 'evaluacion.personal.detalle.diario'
    _description = 'Detalle Diario de Productividad por Técnico'
    _order = 'fecha asc'
    _rec_name = 'fecha'
    
    # ============================================================
    # CAMPOS BÁSICOS
    # ============================================================
    
    evaluacion_id = fields.Many2one(
        'evaluacion.personal',
        string='Evaluación',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    usuario_id = fields.Many2one(
        related='evaluacion_id.usuario_id',
        string='Técnico',
        store=True,
        readonly=True
    )
    
    fecha = fields.Date(
        string='Fecha',
        required=True,
        index=True
    )
    
    dia_semana = fields.Char(
        string='Día',
        compute='_compute_info_dia',
        store=True
    )
    
    numero_dia = fields.Integer(
        string='Día del Mes',
        compute='_compute_info_dia',
        store=True
    )
    
    es_dia_laboral = fields.Boolean(
        string='Es Día Laboral',
        compute='_compute_info_dia',
        store=True,
        help='Lunes a Viernes completos, Sábado medio día'
    )
    
    es_sabado = fields.Boolean(
        string='Es Sábado',
        compute='_compute_info_dia',
        store=True
    )
    
    # ============================================================
    # CONTADORES DE TRABAJOS
    # ============================================================
    
    cantidad_reparaciones = fields.Integer(
        string='Reparaciones',
        compute='_compute_cantidades',
        store=True
    )
    
    cantidad_tickets = fields.Integer(
        string='Tickets',
        compute='_compute_cantidades',
        store=True
    )
    
    total_trabajos = fields.Integer(
        string='Total Trabajos',
        compute='_compute_total',
        store=True
    )
    
    # ============================================================
    # RELACIONES CON TRABAJOS
    # ============================================================
    
    reparacion_ids = fields.Many2many(
        'reparaciones.reparaciones',
        'eval_detalle_reparacion_rel',  # Nombre corto de tabla (27 caracteres)
        'detalle_id',
        'reparacion_id',
        string='Reparaciones del Día',
        compute='_compute_trabajos',
        store=True
    )
    
    ticket_ids = fields.Many2many(
        'ticket.alquiler',
        'eval_detalle_ticket_rel',      # Nombre corto de tabla (24 caracteres)
        'detalle_id',
        'ticket_id',
        string='Tickets del Día',
        compute='_compute_trabajos',
        store=True
    )
    # ============================================================
    # ANÁLISIS Y OBJETIVOS
    # ============================================================
    
    objetivo_dia = fields.Integer(
        string='Objetivo del Día',
        compute='_compute_objetivo',
        store=True,
        help='Objetivo: 4 reparaciones + 3 tickets = 7 trabajos/día'
    )
    
    porcentaje_cumplimiento = fields.Float(
        string='% Cumplimiento',
        compute='_compute_cumplimiento',
        store=True
    )
    
    cumple_objetivo = fields.Boolean(
        string='Cumple Objetivo',
        compute='_compute_cumplimiento',
        store=True
    )
    
    estado_dia = fields.Selection([
        ('sin_actividad', 'Sin Actividad'),
        ('bajo', 'Bajo Rendimiento'),
        ('aceptable', 'Aceptable'),
        ('bueno', 'Buen Rendimiento'),
        ('excelente', 'Excelente')
    ], string='Estado del Día', compute='_compute_estado', store=True)
    
    # ============================================================
    # INFORMACIÓN DE CLIENTES Y EQUIPOS
    # ============================================================
    
    clientes_atendidos = fields.Text(
        string='Clientes Atendidos',
        compute='_compute_info_trabajos',
        store=True
    )
    
    modelos_trabajados = fields.Text(
        string='Modelos/Equipos',
        compute='_compute_info_trabajos',
        store=True
    )
    
    cantidad_clientes = fields.Integer(
        string='Nº Clientes',
        compute='_compute_info_trabajos',
        store=True
    )
    
    # ============================================================
    # MÉTODOS COMPUTE
    # ============================================================
    
    @api.depends('fecha')
    def _compute_info_dia(self):
        """Calcula información del día (nombre, si es laboral, etc.)"""
        for record in self:
            if record.fecha:
                # Día de la semana (0=Lunes, 6=Domingo)
                weekday = record.fecha.weekday()
                
                # Nombres de días en español
                dias_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
                record.dia_semana = dias_semana[weekday]
                record.numero_dia = record.fecha.day
                
                # Sábado (medio día laboral)
                record.es_sabado = (weekday == 5)
                
                # Días laborales: Lunes a Sábado (0-5)
                record.es_dia_laboral = (weekday < 6)
            else:
                record.dia_semana = ''
                record.numero_dia = 0
                record.es_sabado = False
                record.es_dia_laboral = False
    
    @api.depends('usuario_id', 'fecha')
    def _compute_trabajos(self):
        """Busca las reparaciones y tickets realizados este día"""
        for record in self:
            if record.usuario_id and record.fecha:
                # Inicio y fin del día
                inicio_dia = datetime.combine(record.fecha, time.min)
                fin_dia = datetime.combine(record.fecha, time.max)
                
                # Buscar reparaciones creadas este día
                reparaciones = self.env['reparaciones.reparaciones'].search([
                    ('responsable_id', '=', record.usuario_id.id),
                    ('create_date', '>=', inicio_dia),
                    ('create_date', '<=', fin_dia)
                ])
                record.reparacion_ids = [(6, 0, reparaciones.ids)]
                
                # Buscar tickets agendados para este día
                tickets = self.env['ticket.alquiler'].search([
                    ('responsable', '=', record.usuario_id.id),
                    ('agenda', '>=', record.fecha),
                    ('agenda', '<=', record.fecha)
                ])
                record.ticket_ids = [(6, 0, tickets.ids)]
            else:
                record.reparacion_ids = [(5, 0, 0)]
                record.ticket_ids = [(5, 0, 0)]
    
    @api.depends('reparacion_ids', 'ticket_ids')
    def _compute_cantidades(self):
        """Cuenta la cantidad de trabajos"""
        for record in self:
            record.cantidad_reparaciones = len(record.reparacion_ids)
            record.cantidad_tickets = len(record.ticket_ids)
    
    @api.depends('cantidad_reparaciones', 'cantidad_tickets')
    def _compute_total(self):
        """Calcula el total de trabajos del día"""
        for record in self:
            record.total_trabajos = record.cantidad_reparaciones + record.cantidad_tickets
    
    @api.depends('es_dia_laboral', 'es_sabado')
    def _compute_objetivo(self):
        """Calcula el objetivo del día según tipo de día"""
        for record in self:
            if record.es_sabado:
                # Sábado: medio día (2 rep + 1.5 tickets ≈ 4 trabajos)
                record.objetivo_dia = 4
            elif record.es_dia_laboral:
                # Lunes a Viernes: día completo (4 rep + 3 tickets = 7 trabajos)
                record.objetivo_dia = 7
            else:
                # Domingo: no hay objetivo
                record.objetivo_dia = 0
    
    @api.depends('total_trabajos', 'objetivo_dia')
    def _compute_cumplimiento(self):
        """Calcula el porcentaje de cumplimiento del objetivo"""
        for record in self:
            if record.objetivo_dia > 0:
                record.porcentaje_cumplimiento = (record.total_trabajos / record.objetivo_dia) * 100
                record.cumple_objetivo = (record.total_trabajos >= record.objetivo_dia)
            else:
                record.porcentaje_cumplimiento = 0
                record.cumple_objetivo = False
    
    @api.depends('total_trabajos', 'objetivo_dia', 'es_dia_laboral')
    def _compute_estado(self):
        """Clasifica el estado del día según productividad"""
        for record in self:
            if not record.es_dia_laboral:
                record.estado_dia = 'sin_actividad'
            elif record.total_trabajos == 0:
                record.estado_dia = 'sin_actividad'
            elif record.porcentaje_cumplimiento >= 120:
                record.estado_dia = 'excelente'
            elif record.porcentaje_cumplimiento >= 100:
                record.estado_dia = 'bueno'
            elif record.porcentaje_cumplimiento >= 70:
                record.estado_dia = 'aceptable'
            else:
                record.estado_dia = 'bajo'
    
    @api.depends('reparacion_ids', 'ticket_ids')
    def _compute_info_trabajos(self):
        """Genera información resumida de clientes y equipos"""
        for record in self:
            clientes = []
            modelos = []
            
            # Procesar reparaciones
            for rep in record.reparacion_ids:
                # Cliente
                if rep.partner_id and rep.partner_id.name not in clientes:
                    clientes.append(rep.partner_id.name)
                
                # Modelo y serie
                if rep.modelo_id:
                    modelo_info = f"{rep.modelo_id.modelo}"
                    if rep.serie:
                        modelo_info += f" ({rep.serie})"
                    if modelo_info not in modelos:
                        modelos.append(modelo_info)
            
            # Procesar tickets
            for ticket in record.ticket_ids:
                # Cliente
                if ticket.partner_id and ticket.partner_id.name not in clientes:
                    clientes.append(ticket.partner_id.name)
                
                # Modelo y serie
                if ticket.modelo_id:
                    modelo_info = f"{ticket.modelo_id.modelo}"
                    if ticket.serie:
                        modelo_info += f" ({ticket.serie})"
                    if modelo_info not in modelos:
                        modelos.append(modelo_info)
            
            # Asignar valores
            record.cantidad_clientes = len(clientes)
            record.clientes_atendidos = ", ".join(clientes[:5]) if clientes else "Sin clientes"
            if len(clientes) > 5:
                record.clientes_atendidos += f"... (+{len(clientes)-5} más)"
            
            record.modelos_trabajados = ", ".join(modelos[:3]) if modelos else "Sin equipos"
            if len(modelos) > 3:
                record.modelos_trabajados += f"... (+{len(modelos)-3} más)"
    
    # ============================================================
    # ACCIONES
    # ============================================================
    
    def action_ver_reparaciones_dia(self):
        """Abre las reparaciones específicas de este día"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Reparaciones del {self.fecha.strftime("%d/%m/%Y")}',
            'view_mode': 'tree,form',
            'res_model': 'reparaciones.reparaciones',
            'domain': [('id', 'in', self.reparacion_ids.ids)],
            'context': {'create': False}
        }
    
    def action_ver_tickets_dia(self):
        """Abre los tickets específicos de este día"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Tickets del {self.fecha.strftime("%d/%m/%Y")}',
            'view_mode': 'tree,form',
            'res_model': 'ticket.alquiler',
            'domain': [('id', 'in', self.ticket_ids.ids)],
            'context': {'create': False}
        }


# ============================================================
# WIZARD DE ENVÍO MASIVO
# ============================================================

class EvaluacionPersonalEnvioMasivo(models.TransientModel):
    _name = 'evaluacion.personal.envio.masivo'
    _description = 'Asistente para Envío Masivo de Reportes'
    
    email = fields.Char(
        string='Correo Electrónico',
        required=True,
        help='Dirección de correo donde se enviarán los reportes'
    )
    
    subject = fields.Char(
        string='Asunto',
        default='Reportes de Evaluación del Personal',
        required=True
    )
    
    body = fields.Html(
        string='Cuerpo del Mensaje',
        default="""
            <p>Estimado/a:</p>
            <p>Por medio de la presente, hago llegar los reportes de evaluación del personal. Los documentos adjuntos contienen información detallada sobre el desempeño, competencias y resultados de cada colaborador durante el período evaluado.</p>
            <p>Los reportes incluyen:</p>
            <ul>
                <li>Métricas objetivas de productividad</li>
                <li>Análisis diario de actividades</li>
                <li>Evaluación de competencias técnicas</li>
                <li>Evaluación de actitudes y comportamientos</li>
                <li>Evaluación de atención al cliente</li>
                <li>Retroalimentación y plan de acción</li>
            </ul>
            <p>Quedo a su disposición para cualquier consulta o aclaración.</p>
            <p>Saludos cordiales,</p>
        """,
        required=True
    )
    
    evaluacion_ids = fields.Many2many(
        'evaluacion.personal',
        string='Evaluaciones',
        readonly=True
    )
    
    @api.model
    def default_get(self, fields_list):
        """Establece valores por defecto del wizard"""
        _logger.info("🔧 Iniciando default_get en EvaluacionPersonalEnvioMasivo")
        
        res = super(EvaluacionPersonalEnvioMasivo, self).default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        
        if active_ids:
            _logger.info(f"✅ Active IDs encontrados: {active_ids}")
            res['evaluacion_ids'] = [(6, 0, active_ids)]
            res['email'] = self.env.user.email or ''
            _logger.info(f"📧 Email del usuario actual: {res['email']}")
        else:
            _logger.warning("⚠️ No se encontraron IDs activos en el contexto")
        
        return res
    
    def action_enviar_reportes(self):
        """Genera PDFs de las evaluaciones y los envía por correo"""
        _logger.info("📤 Iniciando action_enviar_reportes")
        self.ensure_one()
        
        if not self.evaluacion_ids:
            _logger.warning("⚠️ No hay evaluaciones seleccionadas para enviar")
            return {'type': 'ir.actions.act_window_close'}
        
        if not self.email:
            raise ValidationError("Debe especificar un correo electrónico válido")
        
        _logger.info(f"📊 Preparando envío para {len(self.evaluacion_ids)} evaluaciones")
        
        # Buscar reporte PDF
        _logger.info("🔍 Buscando reporte PDF para evaluaciones")
        report = self.env['ir.actions.report'].search([
            ('model', '=', 'evaluacion.personal'),
            ('report_type', '=', 'qweb-pdf')
        ], limit=1)
        
        if not report:
            _logger.error("❌ No se encontró un reporte PDF para evaluaciones")
            raise ValidationError(
                "No se encontró un reporte PDF configurado para evaluaciones. "
                "Por favor, configure el reporte en Ajustes > Técnico > Informes."
            )
        
        _logger.info(f"✅ Reporte encontrado: {report.name}")
        
        # Generar PDFs y crear adjuntos
        attachments = []
        attachment_ids = []
        
        for evaluacion in self.evaluacion_ids:
            filename = f"Evaluacion_{evaluacion.name}_{evaluacion.nombre_usuario.replace(' ', '_')}.pdf"
            _logger.info(f"📄 Generando PDF: {filename}")
            
            try:
                # Generar PDF
                pdf_content, report_format = report.sudo()._render(
                    report.report_name,
                    res_ids=[evaluacion.id]
                )
                _logger.info(f"✅ PDF generado - Tamaño: {len(pdf_content)} bytes")
                
                # Crear adjunto
                attachment_data = {
                    'name': filename,
                    'datas': base64.b64encode(pdf_content),
                    'res_model': 'mail.mail',
                    'res_id': False,
                    'type': 'binary',
                }
                attachment = self.env['ir.attachment'].create(attachment_data)
                attachment_ids.append(attachment.id)
                attachments.append((filename, pdf_content))
                
                _logger.info(f"📎 Adjunto creado - ID: {attachment.id}")
                
            except Exception as e:
                _logger.error(f"❌ Error al generar PDF para {evaluacion.name}: {str(e)}")
                _logger.error(traceback.format_exc())
        
        if not attachments:
            _logger.error("❌ No se pudo generar ningún reporte PDF")
            raise ValidationError("No se pudo generar ningún reporte PDF. Revise los logs para más detalles.")
        
        _logger.info(f"✅ Se generaron {len(attachments)} PDFs correctamente")
        
        # Enviar correo
        try:
            _logger.info(f"📧 Preparando envío de correo a: {self.email}")
            
            # Verificar servidor de correo
            mail_server = self.env['ir.mail_server'].sudo().search([], limit=1)
            if not mail_server:
                _logger.warning("⚠️ No se encontró un servidor de correo saliente configurado")
                raise ValidationError(
                    "No hay un servidor de correo saliente configurado en el sistema. "
                    "Por favor, configúrelo en Ajustes > Técnico > Correo electrónico > Servidores de correo saliente."
                )
            
            _logger.info(f"📬 Usando servidor: {mail_server.name} ({mail_server.smtp_host}:{mail_server.smtp_port})")
            
            # Crear correo
            mail_values = {
                'subject': self.subject,
                'body_html': self.body,
                'email_to': self.email,
                'attachment_ids': [(6, 0, attachment_ids)],
                'mail_server_id': mail_server.id,
                'auto_delete': False,
            }
            
            mail = self.env['mail.mail'].sudo().create(mail_values)
            _logger.info(f"✉️ Correo creado - ID: {mail.id}")
            
            # Enviar
            _logger.info("📤 Enviando correo...")
            mail.send(raise_exception=True)
            
            if mail.state == 'sent':
                _logger.info("✅ Correo enviado exitosamente")
                
                # Actualizar estado de evaluaciones a "enviado"
                _logger.info("🔄 Actualizando estado de evaluaciones a 'enviado'")
                for evaluacion in self.evaluacion_ids:
                    evaluacion.write({'state': 'enviado'})
                    _logger.info(f"✅ Evaluación {evaluacion.name} → estado 'enviado'")
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '✅ Envío Exitoso',
                        'message': f'Se enviaron {len(attachments)} reportes a {self.email} y se actualizaron los estados.',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                _logger.warning(f"⚠️ Estado del correo: {mail.state} - {mail.failure_reason}")
                raise ValidationError(
                    f"El correo no pudo enviarse correctamente.\n"
                    f"Estado: {mail.state}\n"
                    f"Detalles: {mail.failure_reason or 'Sin detalles disponibles'}"
                )
                
        except Exception as e:
            _logger.error(f"❌ Error al enviar correo: {str(e)}")
            _logger.error(traceback.format_exc())
            
            # Mensajes de error específicos
            error_msg = str(e)
            if "Connection refused" in error_msg or "could not connect" in error_msg:
                raise ValidationError(
                    f"No se pudo conectar al servidor de correo.\n"
                    f"Verifique la configuración (host, puerto, SSL/TLS).\n"
                    f"Detalles: {error_msg}"
                )
            elif "Authentication failed" in error_msg or "authentication" in error_msg.lower():
                raise ValidationError(
                    f"Fallo de autenticación en el servidor de correo.\n"
                    f"Verifique el usuario y contraseña.\n"
                    f"Detalles: {error_msg}"
                )
            else:
                raise ValidationError(f"Error al enviar el correo:\n{error_msg}")