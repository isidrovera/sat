# -*- coding: utf-8 -*-
from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
from datetime import datetime
import babel


class EvaluacionPersonal(models.Model):
    _name = 'evaluacion.personal'
    _inherit = ['mail.thread']
    _description = 'En este modelo se crean evaluaciones del personl técnico'
    name = fields.Char( 'EVALUACIÓN N°', default='New',
        copy=False,
        required=True,
        readonly=True)
    
    @api.model
    def create(self, vals):
        # We generate a standard reference
        vals['name'] = self.env['ir.sequence'].next_by_code('evaluacion.personal')or '/'
        return super(EvaluacionPersonal,self).create(vals) 

    
    observacion  = fields.Text(string='Observacioes')
    fecha = fields.Date(string='Fecha de evaluación',default=fields.Date.today())
    
    # Campos existentes en el modelo evaluacion.personal
    usuario_id = fields.Many2one('res.users', string='Técnico')

    # Nuevo campo para contar las reparaciones en el modelo reparaciones.reparaciones
    cantidad_reparaciones = fields.Integer(string="Reparaciones",compute='_compute_reparaciones', store=True, compute_sudo=True)

    # Nuevo campo para contar las reparaciones en el modelo ticket.alquiler
    cantidad_alquileres = fields.Integer(string="Servicios", compute='_compute_ticket_count', store=True, compute_sudo=True)

    @api.depends('usuario_id', 'fecha')
    def _compute_reparaciones(self):
        Reparaciones = self.env['reparaciones.reparaciones']
        for evaluacion in self:
            inicio_mes = evaluacion.fecha.replace(day=1)
            fin_mes = inicio_mes + relativedelta(months=1)
            domain = [
                ('responsable_id', '=', evaluacion.usuario_id.id),
                ('create_date', '>=', inicio_mes),
                ('create_date', '<', fin_mes),
            ]
            reparaciones_count = Reparaciones.search_count(domain)
            evaluacion.cantidad_reparaciones = reparaciones_count

    @api.depends('usuario_id', 'fecha')
    def _compute_ticket_count(self):
        TicketAlquiler = self.env['ticket.alquiler']
        for evaluacion in self:
            inicio_mes = evaluacion.fecha.replace(day=1)
            fin_mes = inicio_mes + relativedelta(months=1)
            domain = [
                ('responsable', '=', evaluacion.usuario_id.id),
                ('agenda', '>=', inicio_mes),
                ('agenda', '<', fin_mes),
            ]
            ticket_count = TicketAlquiler.search_count(domain)
            evaluacion.cantidad_alquileres = ticket_count

    
    productividad = fields.Selection(string='Productividad', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    productividad_1 = fields.Selection(string='Cumple con los plazos y objetivos', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    productividad_2 = fields.Selection(string='Demuestra iniciativa y proactividad', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    eficiencia = fields.Selection(string='Utiliza eficientemente los recursos asignados', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    eficiencia_1 = fields.Selection(string='Realiza las tareas asignadas de manera oportuna y precisa', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    eficiencia_2 = fields.Selection(string='Propone y aplica mejoras en los procesos de trabajo', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    habilidades = fields.Selection(string='Demuestra habilidades técnicas y conocimientos adecuados para el puesto', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    habilidades_1 = fields.Selection(string='Aplica conocimientos y habilidades para resolver problemas y desafíos', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    habilidades_2 = fields.Selection(string='Actualiza y mejora constantemente sus habilidades y conocimientos', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    aprendizaje = fields.Selection(string='Demuestra capacidad de aprendizaje y adaptación', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    aprendizaje_1 = fields.Selection(string='Asume nuevos desafíos y responsabilidades de manera efectiva', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    aprendizaje_2 = fields.Selection(string='Aprovecha las oportunidades de desarrollo y capacitación', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    comunicacion = fields.Selection(string='Comunica de manera clara y efectiva', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    comunicacion_1 = fields.Selection(string='Escucha activamente y busca entender las perspectivas de los demás', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    comunicacion_2 = fields.Selection(string='Colabora y trabaja efectivamente en equipo', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    relaciones = fields.Selection(string='Cultiva relaciones positivas y constructivas', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    relaciones_1 = fields.Selection(string='Colabora y trabaja efectivamente en equipo', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    relaciones_2 = fields.Selection(string='Cultiva relaciones positivas y constructivas', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    asistencia = fields.Selection(string='Frecuentemente llega temprano al trabajo', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    asistencia_1 = fields.Selection(string='Cumple con el horario de trabajo establecido', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    asistencia_2 = fields.Selection(string='Informa con anticipación sobre ausencias o retrasos', selection=[('1', 'Muy debajo de las Expectativas'), ('2', 'Debajo de las Expectativas'), ('3', 'Alcanza Expectativas'), ('4', 'Mejora Expectativas'), ('5', 'Sobresaliente')])
    
    total_score = fields.Integer('Puntuacion total')
    worker_level = fields.Selection(
        [('muy_debajo', 'Muy Debajo del Nivel Esperado'),
         ('debajo', 'Debajo del Nivel Esperado'),
         ('alcanza', 'Alcanza el Nivel Esperado'),
         ('mejora', 'Necesita Mejorar para Alcanzar el Nivel Esperado'),
         ('sobresaliente', 'Sobresaliente')],
        string='Nivel de Trabajador', compute='_compute_worker_level', store=True)

    @api.depends('usuario_id')
    def _compute_cantidad_reparaciones(self):
        for evaluation in self:
            if evaluation.usuario_id:
                reparaciones = self.env['reparaciones.reparaciones'].search([
                    ('responsable_id', '=', evaluation.usuario_id.id)
                ])
                evaluation.cantidad_reparaciones = len(reparaciones)
            else:
                evaluation.cantidad_reparaciones = 0

    @api.depends('usuario_id')
    def _compute_cantidad_alquileres(self):
        for evaluation in self:
            if evaluation.usuario_id:
                alquileres = self.env['ticket.alquiler'].search([
                    ('responsable', '=', evaluation.usuario_id.id)
                ])
                evaluation.cantidad_alquileres = len(alquileres)
            else:
                evaluation.cantidad_alquileres = 0

    @api.depends('total_score')
    def _compute_worker_level(self):
        for evaluation in self:
            if evaluation.total_score and 5 <= evaluation.total_score <= 20:
                evaluation.worker_level = 'muy_debajo'
            elif evaluation.total_score and 21 <= evaluation.total_score <= 40:
                evaluation.worker_level = 'debajo'
            elif evaluation.total_score and 41 <= evaluation.total_score <= 60:
                evaluation.worker_level = 'alcanza'
            elif evaluation.total_score and 61 <= evaluation.total_score <= 80:
                evaluation.worker_level = 'mejora'
            elif evaluation.total_score and 81 <= evaluation.total_score <= 150:
                evaluation.worker_level = 'sobresaliente'
            else:
                evaluation.worker_level = False

    fields_to_improve = fields.Char(string='Campos a Mejorar', compute='_compute_fields_to_improve')

    @api.onchange('productividad', 'productividad_1', 'productividad_2', 'eficiencia', 'eficiencia_1', 'eficiencia_2', 'habilidades', 'habilidades_1', 'habilidades_2', 'aprendizaje', 'aprendizaje_1', 'aprendizaje_2', 'comunicacion', 'comunicacion_1', 'comunicacion_2', 'relaciones', 'relaciones_1', 'relaciones_2', 'asistencia', 'asistencia_1', 'asistencia_2')
    def _compute_total_score(self):
        for evaluation in self:
            fields_to_sum = ['productividad', 'productividad_1', 'productividad_2', 'eficiencia', 'eficiencia_1', 'eficiencia_2', 'habilidades', 'habilidades_1', 'habilidades_2', 'aprendizaje', 'aprendizaje_1', 'aprendizaje_2', 'comunicacion', 'comunicacion_1', 'comunicacion_2', 'relaciones', 'relaciones_1', 'relaciones_2', 'asistencia', 'asistencia_1', 'asistencia_2']
            total_score = sum(int(getattr(evaluation, field)) for field in fields_to_sum)
            evaluation.total_score = total_score

    @api.depends('productividad', 'productividad_1', 'productividad_2', 'eficiencia', 'eficiencia_1', 'eficiencia_2', 'habilidades', 'habilidades_1', 'habilidades_2', 'aprendizaje', 'aprendizaje_1', 'aprendizaje_2', 'comunicacion', 'comunicacion_1', 'comunicacion_2', 'relaciones', 'relaciones_1', 'relaciones_2', 'asistencia', 'asistencia_1', 'asistencia_2')
    def _compute_fields_to_improve(self):
        for evaluation in self:
            evaluation.fields_to_improve = None  # Reiniciar el campo antes de cada evaluación
            field_groups = {
                'productividad': ['Productividad'],
                'eficiencia': ['Eficiencia'],
                'habilidades': ['Habilidades'],
                'aprendizaje': ['Aprendizaje'],
                'comunicacion': ['Comunicación'],
                'relaciones': ['Relaciones'],
                'asistencia': ['Asistencia']
            }
            fields_to_improve = []

            for field_group, field_labels in field_groups.items():
                fields_to_check = [
                    evaluation[field_group],
                    evaluation[f'{field_group}_1'],
                    evaluation[f'{field_group}_2']
                ]
                
                if any(value and int(value) <= 3 for value in fields_to_check):
                    fields_to_improve.extend(field_labels)

            if fields_to_improve:
                evaluation.fields_to_improve = ', '.join(fields_to_improve)
    total_score_color = fields.Char(string='Total Score Color', compute='_compute_color_flags', store=True)
    is_red = fields.Boolean(compute='_compute_color_flags')
    is_yellow = fields.Boolean(compute='_compute_color_flags')
    is_green = fields.Boolean(compute='_compute_color_flags')

    @api.depends('total_score')
    def _compute_color_flags(self):
        for record in self:
            record.is_red = record.total_score < 50
            record.is_yellow = 50 <= record.total_score < 80
            record.is_green = record.total_score >= 80
    
    mes = fields.Char(string='Mes', compute='_compute_mes_anio', store=True)
    anio = fields.Char(string='Año', compute='_compute_mes_anio', store=True)

    @api.depends('fecha')
    def _compute_mes_anio(self):
        for record in self:
            if record.fecha:
                locale = self.env.context.get('lang') or 'es_ES'
                record.mes = babel.dates.format_date(record.fecha, format='MMMM', locale=locale).capitalize()
                record.anio = record.fecha.strftime('%Y')
            else:
                record.mes, record.anio = False, False