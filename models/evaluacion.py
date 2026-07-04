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
    # BONO MENSUAL / PRODUCCIÓN AJUSTADA
    # ============================================================

    perfil_tecnico_id = fields.Many2one(
        'mantenimiento.tecnico.perfil',
        string='Perfil técnico aplicado',
        compute='_compute_perfil_bono',
        store=True,
        readonly=True
    )

    tipo_operativo = fields.Selection([
        ('taller', 'Técnico fijo de taller'),
        ('servicios', 'Técnico exclusivo de servicios / alquiler'),
        ('mixto', 'Técnico mixto / servicios eventuales'),
    ], string='Tipo operativo aplicado', compute='_compute_perfil_bono', store=True, readonly=True)

    meta_base_taller = fields.Float(
        string='Meta base taller',
        compute='_compute_perfil_bono',
        store=True,
        readonly=True,
        help='Meta mensual base para taller. Gerencia define 50 máquinas como 100%.'
    )

    meta_base_servicios = fields.Float(
        string='Meta base servicios',
        compute='_compute_perfil_bono',
        store=True,
        readonly=True,
        help='Meta mensual base para técnicos de servicios / alquiler.'
    )

    dias_laborables_equivalentes = fields.Float(
        string='Días laborables equivalentes',
        compute='_compute_disponibilidad_bono',
        store=True
    )

    dias_ausencia_equivalentes = fields.Float(
        string='Días descontados por ausencias',
        compute='_compute_disponibilidad_bono',
        store=True
    )

    dias_servicio_equivalentes = fields.Float(
        string='Días ocupados en servicios',
        compute='_compute_disponibilidad_bono',
        store=True
    )

    dias_taller_disponibles = fields.Float(
        string='Días disponibles para taller',
        compute='_compute_disponibilidad_bono',
        store=True
    )

    dias_servicios_disponibles = fields.Float(
        string='Días disponibles para servicios',
        compute='_compute_disponibilidad_bono',
        store=True
    )

    tickets_sin_retorno_count = fields.Integer(
        string='Tickets sin retorno a taller',
        compute='_compute_disponibilidad_bono',
        store=True
    )

    horas_servicio_mes = fields.Float(
        string='Horas estimadas en servicios',
        compute='_compute_disponibilidad_bono',
        store=True
    )

    meta_taller_ajustada = fields.Float(
        string='Meta taller ajustada',
        compute='_compute_metas_bono',
        store=True
    )

    meta_servicios_ajustada = fields.Float(
        string='Meta servicios ajustada',
        compute='_compute_metas_bono',
        store=True
    )

    reparaciones_validas_bono = fields.Integer(
        string='Reparaciones válidas bono',
        compute='_compute_produccion_bono',
        store=True
    )

    tickets_validos_bono = fields.Integer(
        string='Tickets válidos bono',
        compute='_compute_produccion_bono',
        store=True
    )

    porcentaje_produccion_taller = fields.Float(
        string='% Producción taller',
        compute='_compute_produccion_bono',
        store=True
    )

    porcentaje_produccion_servicios = fields.Float(
        string='% Producción servicios',
        compute='_compute_produccion_bono',
        store=True
    )

    porcentaje_produccion_total = fields.Float(
        string='% Producción total ajustada',
        compute='_compute_produccion_bono',
        store=True,
        help='Puede superar el 100% hasta un máximo de 120% para bono.'
    )

    incidencia_ids = fields.Many2many(
        'taller.incidencia',
        'evaluacion_personal_incidencia_rel',
        'evaluacion_id',
        'incidencia_id',
        string='Reclamos que afectan',
        compute='_compute_calidad_bono',
        store=True
    )

    reclamos_procedentes_count = fields.Integer(
        string='Reclamos procedentes',
        compute='_compute_calidad_bono',
        store=True
    )

    evaluacion_servicio_ids = fields.Many2many(
        'client.service.evaluation',
        'evaluacion_personal_servicio_rel',
        'evaluacion_id',
        'servicio_eval_id',
        string='Evaluaciones de servicio',
        compute='_compute_calidad_bono',
        store=True
    )

    evaluaciones_servicio_count = fields.Integer(
        string='Evaluaciones de servicio',
        compute='_compute_calidad_bono',
        store=True
    )

    promedio_evaluacion_servicio = fields.Float(
        string='Promedio evaluación servicio',
        compute='_compute_calidad_bono',
        store=True
    )

    evaluaciones_criticas_count = fields.Integer(
        string='Evaluaciones críticas',
        compute='_compute_calidad_bono',
        store=True,
        help='Evaluaciones de servicio menores a 70%.'
    )

    puntaje_calidad_real = fields.Float(
        string='Puntaje calidad real',
        compute='_compute_calidad_bono',
        store=True
    )

    faltas_injustificadas_equivalentes = fields.Float(
        string='Faltas injustificadas equivalentes',
        compute='_compute_asistencia_bono',
        store=True
    )

    puntaje_asistencia_real = fields.Float(
        string='Puntaje asistencia real',
        compute='_compute_asistencia_bono',
        store=True
    )

    apoyo_calificacion = fields.Selection([
        ('1', 'Deficiente'),
        ('2', 'Bajo'),
        ('3', 'Aceptable'),
        ('4', 'Bueno'),
        ('5', 'Excelente'),
    ], string='Apoyo / Trabajo en equipo bono', default='4', tracking=True)

    puntaje_apoyo_real = fields.Float(
        string='Puntaje apoyo real',
        compute='_compute_apoyo_bono',
        store=True
    )

    puntaje_produccion_bono = fields.Float(
        string='Producción 45%',
        compute='_compute_resultado_bono',
        store=True
    )

    puntaje_calidad_bono = fields.Float(
        string='Calidad 30%',
        compute='_compute_resultado_bono',
        store=True
    )

    puntaje_asistencia_bono = fields.Float(
        string='Asistencia 15%',
        compute='_compute_resultado_bono',
        store=True
    )

    puntaje_apoyo_bono = fields.Float(
        string='Apoyo 10%',
        compute='_compute_resultado_bono',
        store=True
    )

    puntaje_total_bono = fields.Float(
        string='Resultado total bono',
        compute='_compute_resultado_bono',
        store=True
    )

    bono_base = fields.Float(
        string='Bono base S/',
        compute='_compute_monto_bono',
        store=True
    )

    aplica_acelerador = fields.Boolean(
        string='Aplica acelerador',
        compute='_compute_monto_bono',
        store=True
    )

    monto_acelerador = fields.Float(
        string='Acelerador S/',
        compute='_compute_monto_bono',
        store=True
    )

    bono_final = fields.Float(
        string='Bono final S/',
        compute='_compute_monto_bono',
        store=True
    )

    motivo_bono = fields.Text(
        string='Resumen cálculo bono',
        compute='_compute_monto_bono',
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
    # MÉTODOS COMPUTE - BONO MENSUAL
    # ============================================================

    @api.depends('usuario_id')
    def _compute_perfil_bono(self):
        Perfil = self.env['mantenimiento.tecnico.perfil'] if self.env.registry.get('mantenimiento.tecnico.perfil') else False
        for record in self:
            perfil = False
            if Perfil and record.usuario_id:
                perfil = Perfil.search([
                    ('tecnico_id', '=', record.usuario_id.id),
                    ('active', '=', True),
                ], limit=1)
            record.perfil_tecnico_id = perfil.id if perfil else False
            record.tipo_operativo = perfil.tipo_operativo if perfil and perfil.tipo_operativo else 'mixto'
            record.meta_base_taller = perfil.meta_mensual_taller if perfil and perfil.meta_mensual_taller else 50.0
            record.meta_base_servicios = perfil.meta_mensual_servicios if perfil and perfil.meta_mensual_servicios else 45.0

    @api.depends('usuario_id', 'fecha', 'perfil_tecnico_id', 'tipo_operativo')
    def _compute_disponibilidad_bono(self):
        for record in self:
            record.dias_laborables_equivalentes = 0.0
            record.dias_ausencia_equivalentes = 0.0
            record.dias_servicio_equivalentes = 0.0
            record.dias_taller_disponibles = 0.0
            record.dias_servicios_disponibles = 0.0
            record.tickets_sin_retorno_count = 0
            record.horas_servicio_mes = 0.0
            if not record.usuario_id or not record.fecha:
                continue
            inicio_mes, fin_mes = record._get_rango_mes_bono()
            dias_laborables = record._get_dias_laborables_equivalentes(inicio_mes, fin_mes)
            ausencias = record._get_ausencias_equivalentes(inicio_mes, fin_mes)
            servicios = record._get_servicios_equivalentes(inicio_mes, fin_mes)
            dias_base = max(0.0, dias_laborables - ausencias)
            dias_servicio = min(dias_base, servicios.get('dias_equivalentes', 0.0))
            if record.tipo_operativo == 'servicios':
                dias_taller = 0.0
                dias_servicios = dias_base
            elif record.tipo_operativo == 'taller':
                dias_taller = max(0.0, dias_base - dias_servicio)
                dias_servicios = dias_servicio
            else:
                dias_taller = max(0.0, dias_base - dias_servicio)
                dias_servicios = dias_servicio
            record.dias_laborables_equivalentes = dias_laborables
            record.dias_ausencia_equivalentes = ausencias
            record.dias_servicio_equivalentes = dias_servicio
            record.dias_taller_disponibles = dias_taller
            record.dias_servicios_disponibles = dias_servicios
            record.horas_servicio_mes = servicios.get('horas', 0.0)
            record.tickets_sin_retorno_count = servicios.get('sin_retorno', 0)

    @api.depends('dias_laborables_equivalentes', 'dias_taller_disponibles', 'dias_servicios_disponibles', 'meta_base_taller', 'meta_base_servicios', 'tipo_operativo')
    def _compute_metas_bono(self):
        for record in self:
            record.meta_taller_ajustada = 0.0
            record.meta_servicios_ajustada = 0.0
            dias_mes = record.dias_laborables_equivalentes or 0.0
            if dias_mes <= 0:
                continue
            if record.tipo_operativo in ('taller', 'mixto'):
                record.meta_taller_ajustada = (record.meta_base_taller or 50.0) * (record.dias_taller_disponibles / dias_mes)
            if record.tipo_operativo in ('servicios', 'mixto'):
                record.meta_servicios_ajustada = (record.meta_base_servicios or 45.0) * (record.dias_servicios_disponibles / dias_mes)

    @api.depends('usuario_id', 'fecha', 'tipo_operativo', 'meta_taller_ajustada', 'meta_servicios_ajustada')
    def _compute_produccion_bono(self):
        for record in self:
            record.reparaciones_validas_bono = 0
            record.tickets_validos_bono = 0
            record.porcentaje_produccion_taller = 0.0
            record.porcentaje_produccion_servicios = 0.0
            record.porcentaje_produccion_total = 0.0
            if not record.usuario_id or not record.fecha:
                continue
            inicio_mes, fin_mes = record._get_rango_mes_bono()
            reparaciones = record._get_reparaciones_bono(inicio_mes, fin_mes)
            tickets = record._get_tickets_bono(inicio_mes, fin_mes)
            record.reparaciones_validas_bono = len(reparaciones)
            record.tickets_validos_bono = len(tickets)
            pct_taller = (len(reparaciones) / record.meta_taller_ajustada * 100.0) if record.meta_taller_ajustada else 0.0
            pct_servicios = (len(tickets) / record.meta_servicios_ajustada * 100.0) if record.meta_servicios_ajustada else 0.0
            pct_taller = min(120.0, pct_taller)
            pct_servicios = min(120.0, pct_servicios)
            if record.tipo_operativo == 'taller':
                total = pct_taller
            elif record.tipo_operativo == 'servicios':
                total = pct_servicios
            else:
                peso_taller = record.meta_taller_ajustada or 0.0
                peso_servicios = record.meta_servicios_ajustada or 0.0
                peso_total = peso_taller + peso_servicios
                total = ((pct_taller * peso_taller) + (pct_servicios * peso_servicios)) / peso_total if peso_total else 0.0
            record.porcentaje_produccion_taller = pct_taller
            record.porcentaje_produccion_servicios = pct_servicios
            record.porcentaje_produccion_total = min(120.0, total)

    @api.depends('usuario_id', 'fecha')
    def _compute_calidad_bono(self):
        for record in self:
            record.incidencia_ids = [(5, 0, 0)]
            record.reclamos_procedentes_count = 0
            record.evaluacion_servicio_ids = [(5, 0, 0)]
            record.evaluaciones_servicio_count = 0
            record.promedio_evaluacion_servicio = 100.0
            record.evaluaciones_criticas_count = 0
            record.puntaje_calidad_real = 100.0
            if not record.usuario_id or not record.fecha:
                continue
            inicio_mes, fin_mes = record._get_rango_mes_bono()
            reclamos = record._get_reclamos_que_afectan(inicio_mes, fin_mes)
            evaluaciones = record._get_evaluaciones_servicio(inicio_mes, fin_mes)
            record.incidencia_ids = [(6, 0, reclamos.ids)]
            record.reclamos_procedentes_count = len(reclamos)
            record.evaluacion_servicio_ids = [(6, 0, evaluaciones.ids)]
            record.evaluaciones_servicio_count = len(evaluaciones)
            promedio_servicio = 100.0
            criticas = 0
            if evaluaciones:
                puntajes = [ev.puntaje_servicio or 0.0 for ev in evaluaciones]
                promedio_servicio = sum(puntajes) / len(puntajes) if puntajes else 100.0
                criticas = len([p for p in puntajes if p < 70.0])
            penalidad_reclamos = min(40.0, len(reclamos) * 10.0)
            calidad_base = max(0.0, 100.0 - penalidad_reclamos)
            calidad = (calidad_base * 0.60 + promedio_servicio * 0.40) if evaluaciones else calidad_base
            record.promedio_evaluacion_servicio = promedio_servicio
            record.evaluaciones_criticas_count = criticas
            record.puntaje_calidad_real = max(0.0, min(100.0, calidad))

    @api.depends('usuario_id', 'fecha')
    def _compute_asistencia_bono(self):
        for record in self:
            record.faltas_injustificadas_equivalentes = 0.0
            record.puntaje_asistencia_real = 100.0
            if not record.usuario_id or not record.fecha:
                continue
            inicio_mes, fin_mes = record._get_rango_mes_bono()
            faltas = record._get_faltas_equivalentes(inicio_mes, fin_mes)
            record.faltas_injustificadas_equivalentes = faltas
            record.puntaje_asistencia_real = max(0.0, 100.0 - (faltas * 20.0))

    @api.depends('apoyo_calificacion')
    def _compute_apoyo_bono(self):
        for record in self:
            valor = int(record.apoyo_calificacion or '4')
            record.puntaje_apoyo_real = (valor / 5.0) * 100.0

    @api.depends('porcentaje_produccion_total', 'puntaje_calidad_real', 'puntaje_asistencia_real', 'puntaje_apoyo_real')
    def _compute_resultado_bono(self):
        for record in self:
            produccion = min(120.0, record.porcentaje_produccion_total or 0.0)
            calidad = min(100.0, record.puntaje_calidad_real or 0.0)
            asistencia = min(100.0, record.puntaje_asistencia_real or 0.0)
            apoyo = min(100.0, record.puntaje_apoyo_real or 0.0)
            record.puntaje_produccion_bono = produccion * 0.45
            record.puntaje_calidad_bono = calidad * 0.30
            record.puntaje_asistencia_bono = asistencia * 0.15
            record.puntaje_apoyo_bono = apoyo * 0.10
            record.puntaje_total_bono = min(120.0, record.puntaje_produccion_bono + record.puntaje_calidad_bono + record.puntaje_asistencia_bono + record.puntaje_apoyo_bono)

    @api.depends('puntaje_total_bono', 'reclamos_procedentes_count', 'evaluaciones_criticas_count', 'faltas_injustificadas_equivalentes')
    def _compute_monto_bono(self):
        for record in self:
            resultado = record.puntaje_total_bono or 0.0
            if resultado >= 110.0:
                bono = 350.0
            elif resultado >= 100.0:
                bono = 250.0
            elif resultado >= 95.0:
                bono = 150.0
            else:
                bono = 0.0
            aplica_acelerador = (
                resultado >= 110.0 and
                record.reclamos_procedentes_count == 0 and
                record.evaluaciones_criticas_count == 0 and
                record.faltas_injustificadas_equivalentes == 0
            )
            acelerador = 100.0 if aplica_acelerador else 0.0
            resumen = [
                'Resultado total bono: %.2f%%' % resultado,
                'Bono base: S/ %.2f' % bono,
            ]
            if aplica_acelerador:
                resumen.append('Acelerador aplicado: S/ 100.00')
                resumen.append('Motivo: resultado mayor o igual a 110%, sin reclamos procedentes, sin evaluaciones críticas y sin faltas injustificadas.')
            else:
                razones = []
                if resultado < 110.0:
                    razones.append('resultado menor a 110%')
                if record.reclamos_procedentes_count > 0:
                    razones.append('reclamos procedentes')
                if record.evaluaciones_criticas_count > 0:
                    razones.append('evaluaciones críticas')
                if record.faltas_injustificadas_equivalentes > 0:
                    razones.append('faltas injustificadas')
                resumen.append('Acelerador no aplicado: %s.' % (', '.join(razones) if razones else 'no cumple condiciones'))
            record.bono_base = bono
            record.aplica_acelerador = aplica_acelerador
            record.monto_acelerador = acelerador
            record.bono_final = bono + acelerador
            record.motivo_bono = '\n'.join(resumen)

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
    # HELPERS BONO MENSUAL
    # ============================================================

    def _get_rango_mes_bono(self):
        self.ensure_one()
        inicio_mes = self.fecha.replace(day=1)
        fin_mes = inicio_mes + relativedelta(months=1)
        return inicio_mes, fin_mes

    def _model_exists(self, model_name):
        return bool(self.env.registry.get(model_name))

    def _get_dias_laborables_equivalentes(self, inicio_mes, fin_mes):
        dias = 0.0
        current = inicio_mes
        while current < fin_mes:
            if current.weekday() < 5:
                dias += 1.0
            elif current.weekday() == 5:
                dias += 0.5
            current += timedelta(days=1)
        return dias

    def _get_factor_dia_bono(self, fecha):
        if fecha.weekday() < 5:
            return 1.0
        if fecha.weekday() == 5:
            return 0.5
        return 0.0

    def _get_horas_laborales_fecha(self, fecha):
        self.ensure_one()
        if self.perfil_tecnico_id and hasattr(self.perfil_tecnico_id, 'get_disponibilidad_fecha'):
            try:
                disp = self.perfil_tecnico_id.get_disponibilidad_fecha(fecha)
                if disp and disp.get('disponible'):
                    return max(0.0, (disp.get('hora_fin') or 0.0) - (disp.get('hora_inicio') or 0.0))
            except Exception:
                _logger.warning('[BONO] No se pudo obtener disponibilidad para %s', fecha, exc_info=True)
        if fecha.weekday() == 5:
            return 4.0
        if fecha.weekday() < 5:
            return 8.0
        return 0.0

    def _get_ausencias_equivalentes(self, inicio_mes, fin_mes):
        self.ensure_one()
        if not self._model_exists('mantenimiento.tecnico.ausencia'):
            return 0.0
        ausencias = self.env['mantenimiento.tecnico.ausencia'].search([
            ('tecnico_id', '=', self.usuario_id.id),
            ('estado', 'in', ['aprobado', 'ausente_activo', 'cerrado']),
            ('tipo', 'in', ['permiso', 'vacaciones', 'enfermedad', 'descanso_medico', 'capacitacion', 'bloqueo_admin']),
            ('fecha_inicio', '<', fin_mes),
            '|',
            ('fecha_fin', '=', False),
            ('fecha_fin', '>=', inicio_mes),
        ])
        return self._sumar_dias_ausencia(ausencias, inicio_mes, fin_mes)

    def _get_faltas_equivalentes(self, inicio_mes, fin_mes):
        self.ensure_one()
        if not self._model_exists('mantenimiento.tecnico.ausencia'):
            return 0.0
        faltas = self.env['mantenimiento.tecnico.ausencia'].search([
            ('tecnico_id', '=', self.usuario_id.id),
            ('tipo', '=', 'falta'),
            ('estado', 'in', ['aprobado', 'ausente_activo', 'cerrado']),
            ('fecha_inicio', '<', fin_mes),
            '|',
            ('fecha_fin', '=', False),
            ('fecha_fin', '>=', inicio_mes),
        ])
        return self._sumar_dias_ausencia(faltas, inicio_mes, fin_mes)

    def _sumar_dias_ausencia(self, ausencias, inicio_mes, fin_mes):
        total = 0.0
        for ausencia in ausencias:
            fecha_inicio = max(ausencia.fecha_inicio, inicio_mes)
            fecha_fin = ausencia.fecha_fin or fecha_inicio
            fecha_fin = min(fecha_fin, fin_mes - timedelta(days=1))
            current = fecha_inicio
            while current <= fecha_fin:
                factor = self._get_factor_dia_bono(current)
                if factor > 0:
                    if ausencia.dia_completo:
                        total += factor
                    else:
                        horas_dia = self._get_horas_laborales_fecha(current)
                        horas_ausencia = max(0.0, (ausencia.hora_fin or 0.0) - (ausencia.hora_inicio or 0.0))
                        if horas_dia > 0:
                            total += min(factor, horas_ausencia / horas_dia)
                current += timedelta(days=1)
        return total

    def _get_reparaciones_bono(self, inicio_mes, fin_mes):
        self.ensure_one()
        if not self._model_exists('reparaciones.reparaciones'):
            return self.env['reparaciones.reparaciones']
        inicio_dt = datetime.combine(inicio_mes, time.min)
        fin_dt = datetime.combine(fin_mes, time.min)
        return self.env['reparaciones.reparaciones'].search([
            ('responsable_id', '=', self.usuario_id.id),
            ('create_date', '>=', inicio_dt),
            ('create_date', '<', fin_dt),
        ])

    def _get_tickets_bono(self, inicio_mes, fin_mes):
        self.ensure_one()
        if not self._model_exists('ticket.alquiler'):
            return self.env['ticket.alquiler']
        Ticket = self.env['ticket.alquiler']
        agenda_field = Ticket._fields.get('agenda')
        if agenda_field and agenda_field.type == 'date':
            domain_fecha = [('agenda', '>=', inicio_mes), ('agenda', '<', fin_mes)]
        else:
            domain_fecha = [('agenda', '>=', datetime.combine(inicio_mes, time.min)), ('agenda', '<', datetime.combine(fin_mes, time.min))]
        return Ticket.search([('responsable', '=', self.usuario_id.id)] + domain_fecha)

    def _get_servicios_equivalentes(self, inicio_mes, fin_mes):
        self.ensure_one()
        result = {'dias_equivalentes': 0.0, 'horas': 0.0, 'sin_retorno': 0}
        if not self._model_exists('ticket.alquiler'):
            return result
        agrupado_por_fecha = {}
        for ticket in self._get_tickets_bono(inicio_mes, fin_mes):
            fecha_ticket = self._get_ticket_fecha(ticket)
            if not fecha_ticket:
                continue
            agrupado_por_fecha.setdefault(fecha_ticket, []).append(ticket)
        for fecha_ticket, tickets in agrupado_por_fecha.items():
            horas_dia = self._get_horas_laborales_fecha(fecha_ticket)
            if horas_dia <= 0:
                continue
            horas_fecha = 0.0
            sin_retorno_fecha = False
            for ticket in tickets:
                horas_ticket = self._get_ticket_horas_estimadas(ticket, horas_dia)
                if self._ticket_sin_retorno(ticket):
                    sin_retorno_fecha = True
                    result['sin_retorno'] += 1
                    hora_agenda = self._get_ticket_hora_agenda(ticket)
                    if hora_agenda is not False and hora_agenda >= 13.0:
                        horas_ticket = max(horas_ticket, horas_dia / 2.0)
                    else:
                        horas_ticket = horas_dia
                horas_fecha += horas_ticket
            if sin_retorno_fecha:
                horas_fecha = min(horas_dia, max(horas_fecha, horas_dia))
            horas_fecha = min(horas_dia, horas_fecha)
            result['horas'] += horas_fecha
            result['dias_equivalentes'] += min(1.0, horas_fecha / horas_dia)
        return result

    def _get_ticket_fecha(self, ticket):
        if 'agenda' not in ticket._fields or not ticket.agenda:
            return False
        agenda = ticket.agenda
        if isinstance(agenda, datetime):
            return agenda.date()
        if isinstance(agenda, date):
            return agenda
        try:
            return fields.Date.to_date(agenda)
        except Exception:
            return False

    def _get_ticket_hora_agenda(self, ticket):
        if 'agenda' not in ticket._fields or not ticket.agenda:
            return False
        agenda = ticket.agenda
        if isinstance(agenda, datetime):
            return agenda.hour + (agenda.minute / 60.0)
        return False

    def _get_ticket_horas_estimadas(self, ticket, horas_dia):
        for inicio_field, fin_field in [('hora_inicio', 'hora_fin'), ('hora_inicio_servicio', 'hora_fin_servicio'), ('hora_llegada', 'hora_salida')]:
            if inicio_field in ticket._fields and fin_field in ticket._fields:
                inicio = ticket[inicio_field] or 0.0
                fin = ticket[fin_field] or 0.0
                if fin > inicio:
                    return min(horas_dia, max(0.0, fin - inicio))
        for inicio_field, fin_field in [('fecha_inicio', 'fecha_fin'), ('fecha_inicio_servicio', 'fecha_fin_servicio'), ('hora_inicio_real', 'hora_fin_real')]:
            if inicio_field in ticket._fields and fin_field in ticket._fields:
                inicio = ticket[inicio_field]
                fin = ticket[fin_field]
                if inicio and fin and isinstance(inicio, datetime) and isinstance(fin, datetime) and fin > inicio:
                    return min(horas_dia, max(0.0, (fin - inicio).total_seconds() / 3600.0))
        if self.perfil_tecnico_id and getattr(self.perfil_tecnico_id, 'duracion_servicio_horas', False):
            return min(horas_dia, self.perfil_tecnico_id.duracion_servicio_horas)
        return min(horas_dia, horas_dia / 2.0)

    def _ticket_sin_retorno(self, ticket):
        posibles_campos = ['retorno_taller', 'retorno', 'retorno_tecnico', 'regreso_taller', 'tecnico_retorno', 'retorno_al_taller', 'volvio_taller']
        for campo in posibles_campos:
            if campo not in ticket._fields:
                continue
            valor = ticket[campo]
            field = ticket._fields[campo]
            if field.type == 'boolean':
                return not bool(valor)
            if field.type == 'selection':
                return valor in ['no', 'no_retorno', 'sin_retorno', 'no_volvio', 'no_retornado']
            if field.type in ('char', 'text'):
                return (valor or '').strip().lower() in ['no', 'no retorno', 'no retornó', 'sin retorno', 'no volvio', 'no volvió']
        return False

    def _get_reclamos_que_afectan(self, inicio_mes, fin_mes):
        self.ensure_one()
        if not self._model_exists('taller.incidencia'):
            return self.env['taller.incidencia']
        return self.env['taller.incidencia'].search([
            ('tipo', '=', 'reclamo'),
            ('afecta_tecnico', '=', True),
            ('estado', 'in', ['procede', 'corregido', 'cerrado']),
            ('fecha_hora', '>=', datetime.combine(inicio_mes, time.min)),
            ('fecha_hora', '<', datetime.combine(fin_mes, time.min)),
            '|',
            ('tecnico_id', '=', self.usuario_id.id),
            ('empleado_id.user_id', '=', self.usuario_id.id),
        ])

    def _get_evaluaciones_servicio(self, inicio_mes, fin_mes):
        self.ensure_one()
        if not self._model_exists('client.service.evaluation'):
            return self.env['client.service.evaluation']
        return self.env['client.service.evaluation'].search([
            ('technician_id', '=', self.usuario_id.id),
            ('state', '=', 'completed'),
            '|',
            '&', ('visit_date', '>=', inicio_mes), ('visit_date', '<', fin_mes),
            '&', ('evaluation_date', '>=', datetime.combine(inicio_mes, time.min)), ('evaluation_date', '<', datetime.combine(fin_mes, time.min)),
        ])

    def action_recalcular_bono(self):
        for record in self:
            if record.detalle_diario_ids:
                record.detalle_diario_ids._compute_bono_detalle()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Bono recalculado',
                'message': 'Se recalculó la información de bono mensual.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_ver_reclamos_bono(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reclamos que afectan bono',
            'res_model': 'taller.incidencia',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.incidencia_ids.ids)],
            'context': {'create': False}
        }

    def action_ver_evaluaciones_servicio_bono(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Evaluaciones de servicio',
            'res_model': 'client.service.evaluation',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.evaluacion_servicio_ids.ids)],
            'context': {'create': False}
        }

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
    # BONO MENSUAL - ANÁLISIS DIARIO
    # ============================================================

    dia_equivalente_bono = fields.Float(
        string='Día equivalente bono',
        compute='_compute_bono_detalle',
        store=True
    )

    horas_servicio_dia = fields.Float(
        string='Horas servicio día',
        compute='_compute_bono_detalle',
        store=True
    )

    servicio_equivalente_dia = fields.Float(
        string='Servicio equivalente día',
        compute='_compute_bono_detalle',
        store=True
    )

    taller_disponible_dia = fields.Float(
        string='Taller disponible día',
        compute='_compute_bono_detalle',
        store=True
    )

    ticket_sin_retorno_dia = fields.Boolean(
        string='Sin retorno a taller',
        compute='_compute_bono_detalle',
        store=True
    )

    meta_taller_dia = fields.Float(
        string='Meta taller día',
        compute='_compute_bono_detalle',
        store=True
    )

    meta_servicio_dia = fields.Float(
        string='Meta servicio día',
        compute='_compute_bono_detalle',
        store=True
    )

    cumplimiento_taller_dia = fields.Float(
        string='% Taller día',
        compute='_compute_bono_detalle',
        store=True
    )

    cumplimiento_servicio_dia = fields.Float(
        string='% Servicio día',
        compute='_compute_bono_detalle',
        store=True
    )

    # ============================================================
    # MÉTODOS COMPUTE
    # ============================================================

    @api.depends(
        'fecha', 'usuario_id', 'cantidad_reparaciones', 'cantidad_tickets',
        'ticket_ids', 'evaluacion_id.tipo_operativo', 'evaluacion_id.meta_base_taller',
        'evaluacion_id.meta_base_servicios', 'evaluacion_id.dias_laborables_equivalentes'
    )
    def _compute_bono_detalle(self):
        for record in self:
            record.dia_equivalente_bono = 0.0
            record.horas_servicio_dia = 0.0
            record.servicio_equivalente_dia = 0.0
            record.taller_disponible_dia = 0.0
            record.ticket_sin_retorno_dia = False
            record.meta_taller_dia = 0.0
            record.meta_servicio_dia = 0.0
            record.cumplimiento_taller_dia = 0.0
            record.cumplimiento_servicio_dia = 0.0
            if not record.evaluacion_id or not record.fecha:
                continue
            evaluacion = record.evaluacion_id
            dia_equiv = evaluacion._get_factor_dia_bono(record.fecha)
            horas_dia = evaluacion._get_horas_laborales_fecha(record.fecha)
            if dia_equiv <= 0 or horas_dia <= 0:
                continue
            horas_servicio = 0.0
            sin_retorno = False
            for ticket in record.ticket_ids:
                horas_ticket = evaluacion._get_ticket_horas_estimadas(ticket, horas_dia)
                if evaluacion._ticket_sin_retorno(ticket):
                    sin_retorno = True
                    hora_agenda = evaluacion._get_ticket_hora_agenda(ticket)
                    if hora_agenda is not False and hora_agenda >= 13.0:
                        horas_ticket = max(horas_ticket, horas_dia / 2.0)
                    else:
                        horas_ticket = horas_dia
                horas_servicio += horas_ticket
            horas_servicio = min(horas_dia, horas_servicio)
            servicio_equiv = min(dia_equiv, horas_servicio / horas_dia) if horas_dia else 0.0
            taller_disponible = 0.0 if evaluacion.tipo_operativo == 'servicios' else max(0.0, dia_equiv - servicio_equiv)
            dias_mes = evaluacion.dias_laborables_equivalentes or 0.0
            meta_taller_dia = 0.0
            meta_servicio_dia = 0.0
            if dias_mes > 0:
                if evaluacion.tipo_operativo in ('taller', 'mixto'):
                    meta_taller_dia = ((evaluacion.meta_base_taller or 50.0) / dias_mes) * taller_disponible
                if evaluacion.tipo_operativo in ('servicios', 'mixto'):
                    meta_servicio_dia = ((evaluacion.meta_base_servicios or 45.0) / dias_mes) * servicio_equiv
            record.dia_equivalente_bono = dia_equiv
            record.horas_servicio_dia = horas_servicio
            record.servicio_equivalente_dia = servicio_equiv
            record.taller_disponible_dia = taller_disponible
            record.ticket_sin_retorno_dia = sin_retorno
            record.meta_taller_dia = meta_taller_dia
            record.meta_servicio_dia = meta_servicio_dia
            record.cumplimiento_taller_dia = min(120.0, (record.cantidad_reparaciones / meta_taller_dia * 100.0) if meta_taller_dia else 0.0)
            record.cumplimiento_servicio_dia = min(120.0, (record.cantidad_tickets / meta_servicio_dia * 100.0) if meta_servicio_dia else 0.0)

    
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
        """Genera información resumida de clientes y equipos trabajados"""
        for record in self:
            clientes = []
            modelos = []

            # ===============================
            # PROCESAR REPARACIONES
            # ===============================
            for rep in record.reparacion_ids:
                # Cliente
                if rep.cliente_id and rep.cliente_id.name:
                    if rep.cliente_id.name not in clientes:
                        clientes.append(rep.cliente_id.name)

                # Modelo y serie
                if hasattr(rep, 'modelo_id') and rep.modelo_id:
                    modelo_info = rep.modelo_id.modelo if hasattr(rep.modelo_id, 'modelo') else rep.modelo_id.display_name

                    if hasattr(rep, 'serie') and rep.serie:
                        modelo_info += f" ({rep.serie})"

                    if modelo_info not in modelos:
                        modelos.append(modelo_info)

            # ===============================
            # PROCESAR TICKETS (ticket.alquiler)
            # ===============================
            for ticket in record.ticket_ids:
                # Cliente
                if ticket.partner_id and ticket.partner_id.name:
                    if ticket.partner_id.name not in clientes:
                        clientes.append(ticket.partner_id.name)

                # Modelo / equipo (USANDO CAMPOS REALES)
                if ticket.product_alquiler:
                    # modelo_id_r es related='product_alquiler.name.name'
                    modelo_info = ticket.modelo_id_r or ticket.product_alquiler.display_name

                    # Serie (serie_id_r es Char related)
                    if ticket.serie_id_r:
                        modelo_info += f" ({ticket.serie_id_r})"

                    if modelo_info not in modelos:
                        modelos.append(modelo_info)

            # ===============================
            # ASIGNAR RESULTADOS
            # ===============================
            record.cantidad_clientes = len(clientes)

            # Clientes (máx 5 visibles)
            if clientes:
                record.clientes_atendidos = ", ".join(clientes[:5])
                if len(clientes) > 5:
                    record.clientes_atendidos += f"... (+{len(clientes) - 5} más)"
            else:
                record.clientes_atendidos = "Sin clientes"

            # Modelos / equipos (máx 3 visibles)
            if modelos:
                record.modelos_trabajados = ", ".join(modelos[:3])
                if len(modelos) > 3:
                    record.modelos_trabajados += f"... (+{len(modelos) - 3} más)"
            else:
                record.modelos_trabajados = "Sin equipos"

    
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
    
    user_ids = fields.Many2many(
        'res.users',
        'evaluacion_envio_user_rel',
        'envio_id',
        'user_id',
        string='Destinatarios Principales',
        required=True,
        help='Usuarios a los que se enviarán los reportes'
    )
    
    user_cc_ids = fields.Many2many(
        'res.users',
        'evaluacion_envio_user_cc_rel',
        'envio_id',
        'user_id',
        string='Con Copia (CC)',
        help='Usuarios que recibirán copia de los reportes'
    )
    
    subject = fields.Char(
        string='Asunto',
        default='📊 Reportes de Evaluación del Personal',
        required=True
    )
    
    body = fields.Html(
        string='Cuerpo del Mensaje',
        compute='_compute_body_html',
        readonly=False,
        store=True
    )
    
    evaluacion_ids = fields.Many2many(
        'evaluacion.personal',
        string='Evaluaciones',
        readonly=True
    )
    
    @api.depends('user_ids', 'evaluacion_ids')
    def _compute_body_html(self):
        """Genera el cuerpo HTML del correo con diseño moderno"""
        for wizard in self:
            # Obtener nombres de destinatarios
            if len(wizard.user_ids) == 1:
                user_name = wizard.user_ids[0].name
            elif len(wizard.user_ids) > 1:
                user_name = 'Estimados colaboradores'
            else:
                user_name = 'Estimado/a'
            
            num_evaluaciones = len(wizard.evaluacion_ids)
            
            # Lista de evaluaciones
            evaluaciones_list = ''
            for eval in wizard.evaluacion_ids:
                codigo = eval.name if hasattr(eval, 'name') else 'N/A'
                nombre = eval.nombre_usuario if hasattr(eval, 'nombre_usuario') else 'N/A'
                
                evaluaciones_list += f"""
                    <tr>
                        <td style="padding: 12px; border-bottom: 1px solid #e9ecef; color: #555;">
                            <strong>{codigo}</strong>
                        </td>
                        <td style="padding: 12px; border-bottom: 1px solid #e9ecef; color: #555;">
                            {nombre}
                        </td>
                    </tr>
                """
            
            wizard.body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reportes de Evaluación del Personal</title>
</head>
<body style="margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif; line-height: 1.6; color: #2d3748; background-color: #f4f4f4;">
    <!-- Contenedor Principal con tabla para compatibilidad -->
    <table width="100%" border="0" cellspacing="0" cellpadding="0" bgcolor="#f4f4f4">
        <tr>
            <td align="center" style="padding: 20px;">
                <table width="800" border="0" cellspacing="0" cellpadding="0" style="max-width: 800px;">
                    
                    <!-- Encabezado -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%); padding: 30px 20px; text-align: center; border-radius: 8px 8px 0 0;">
                            <div style="color: #ffffff; font-size: 28px; font-weight: bold; margin: 0;">
                                📊 Reportes de Evaluación del Personal
                            </div>
                            <div style="color: #ffffff; font-size: 16px; margin: 10px 0 0 0; opacity: 0.9;">
                                Jefatura de Área Técnica
                            </div>
                        </td>
                    </tr>
                    
                    <!-- Contenido Principal -->
                    <tr>
                        <td style="background-color: #ffffff; padding: 30px; border: 1px solid #e2e8f0; border-top: none;">
                            
                            <!-- Saludo -->
                            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="padding-bottom: 25px;">
                                        <p style="font-size: 16px; color: #2c3e50; margin: 0 0 15px 0;">
                                            <strong>{user_name}:</strong>
                                        </p>
                                        <p style="color: #555; margin: 0 0 10px 0;">
                                            Por medio de la presente, hago llegar los reportes de evaluación del personal. Los documentos adjuntos contienen información detallada sobre el desempeño y competencias de cada colaborador durante el período evaluado.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Resumen de Evaluaciones -->
                            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 25px;">
                                <tr>
                                    <td style="background: #e8f4fd; border: 1px solid #3498db; border-left: 4px solid #3498db; padding: 15px; border-radius: 6px;">
                                        <strong style="color: #2c3e50;">📋 Resumen:</strong> 
                                        Se adjuntan <strong>{num_evaluaciones}</strong> reporte(s) de evaluación en formato PDF.
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Contenido de las Evaluaciones -->
                            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 25px 0;">
                                <tr>
                                    <td>
                                        <div style="color: #2c3e50; font-size: 20px; margin: 0 0 15px 0; border-bottom: 2px solid #3498db; padding-bottom: 8px; font-weight: bold;">
                                            📑 Contenido de los Reportes
                                        </div>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="background: #f8f9fa; padding: 20px; border-radius: 6px;">
                                        <p style="margin: 0 0 10px 0; color: #2c3e50; font-weight: 600;">Cada reporte incluye:</p>
                                        <ul style="margin: 10px 0; padding-left: 20px; color: #555;">
                                            <li style="margin: 8px 0;">📈 <strong>Métricas de productividad</strong></li>
                                            <li style="margin: 8px 0;">📅 <strong>Análisis de actividades</strong></li>
                                            <li style="margin: 8px 0;">🔧 <strong>Evaluación de competencias técnicas</strong></li>
                                            <li style="margin: 8px 0;">😊 <strong>Evaluación de actitudes</strong></li>
                                            <li style="margin: 8px 0;">👥 <strong>Evaluación de atención al cliente</strong></li>
                                            <li style="margin: 8px 0;">💡 <strong>Retroalimentación</strong></li>
                                        </ul>
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Lista de Evaluaciones Adjuntas -->
                            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 25px 0;">
                                <tr>
                                    <td>
                                        <div style="color: #2c3e50; font-size: 20px; margin: 0 0 15px 0; border-bottom: 2px solid #3498db; padding-bottom: 8px; font-weight: bold;">
                                            📎 Evaluaciones Adjuntas
                                        </div>
                                    </td>
                                </tr>
                                <tr>
                                    <td>
                                        <table cellspacing="0" cellpadding="0" style="width: 100%; border-collapse: collapse; margin: 20px 0; background: #ffffff; border-radius: 6px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border: 1px solid #e2e8f0;">
                                            <thead>
                                                <tr style="background: #f8f9fa;">
                                                    <th style="color: #2c3e50; font-weight: 600; padding: 15px; text-align: left; border-bottom: 2px solid #e9ecef;">
                                                        Código
                                                    </th>
                                                    <th style="color: #2c3e50; font-weight: 600; padding: 15px; text-align: left; border-bottom: 2px solid #e9ecef;">
                                                        Colaborador
                                                    </th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {evaluaciones_list}
                                            </tbody>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Disponibilidad -->
                            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 25px 0;">
                                <tr>
                                    <td>
                                        <p style="color: #555; margin: 0 0 10px 0;">
                                            Quedo a su disposición para cualquier consulta o aclaración.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Pie de mensaje -->
                            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
                                <tr>
                                    <td>
                                        <p style="margin: 5px 0; color: #555;">Saludos cordiales,</p>
                                        <p style="margin: 5px 0;"><strong style="color: #2c3e50;">Jefe de Área Técnica</strong></p>
                                    </td>
                                </tr>
                            </table>
                            
                        </td>
                    </tr>
                    
                    <!-- Pie de página -->
                    <tr>
                        <td style="background: #2c3e50; color: white; padding: 20px; text-align: center; font-size: 14px; border-radius: 0 0 8px 8px;">
                            <div style="margin: 5px 0; opacity: 0.9;">
                                <strong>Sistema de Evaluación del Personal</strong>
                            </div>
                        </td>
                    </tr>
                    
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
            """
    
    @api.model
    def default_get(self, fields_list):
        """Establece valores por defecto del wizard"""
        _logger.info("🔧 Iniciando default_get en EvaluacionPersonalEnvioMasivo")
        
        res = super(EvaluacionPersonalEnvioMasivo, self).default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        
        if active_ids:
            _logger.info(f"✅ Active IDs encontrados: {active_ids}")
            res['evaluacion_ids'] = [(6, 0, active_ids)]
            res['user_ids'] = [(6, 0, [self.env.user.id])]
            _logger.info(f"👤 Usuario actual: {self.env.user.name}")
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
        
        if not self.user_ids:
            raise ValidationError("Debe especificar al menos un destinatario")
        
        # Obtener emails de destinatarios
        emails_to = [user.email for user in self.user_ids if user.email]
        if not emails_to:
            raise ValidationError("Ninguno de los destinatarios tiene un correo electrónico válido")
        
        emails_cc = [user.email for user in self.user_cc_ids if user.email]
        
        _logger.info(f"📊 Preparando envío para {len(self.evaluacion_ids)} evaluaciones")
        _logger.info(f"📧 Destinatarios: {', '.join(emails_to)}")
        if emails_cc:
            _logger.info(f"📧 Con copia: {', '.join(emails_cc)}")
        
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
                'email_to': ', '.join(emails_to),
                'attachment_ids': [(6, 0, attachment_ids)],
                'mail_server_id': mail_server.id,
                'auto_delete': False,
            }
            
            # Añadir CC si existe
            if emails_cc:
                mail_values['email_cc'] = ', '.join(emails_cc)
            
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
                
                # Mensaje de confirmación
                user_names = ', '.join([u.name for u in self.user_ids])
                mensaje = f'Se enviaron {len(attachments)} reportes a: {user_names}'
                if self.user_cc_ids:
                    cc_names = ', '.join([u.name for u in self.user_cc_ids])
                    mensaje += f' (CC: {cc_names})'
                mensaje += ' y se actualizaron los estados.'
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '✅ Envío Exitoso',
                        'message': mensaje,
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
