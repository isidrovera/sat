# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class EvaluacionPersonalDashboard(models.Model):
    _inherit = 'evaluacion.personal'

    # ============================================================
    # CAMPOS RESUMEN PARA DASHBOARD
    # ============================================================

    total_trabajos_mes = fields.Integer(
        string='Total Trabajos',
        compute='_compute_dashboard_productividad',
        store=True,
        help='Suma de reparaciones y tickets atendidos en el periodo evaluado.'
    )

    objetivo_total_trabajos = fields.Integer(
        string='Objetivo Total',
        compute='_compute_dashboard_productividad',
        store=True,
        help='Suma del objetivo de reparaciones y el objetivo de tickets.'
    )

    porcentaje_productividad_total = fields.Float(
        string='% Productividad Total',
        compute='_compute_dashboard_productividad',
        store=True,
        help='Cumplimiento general considerando reparaciones + tickets.'
    )

    promedio_diario_total = fields.Float(
        string='Promedio Diario Total',
        compute='_compute_dashboard_productividad',
        store=True,
        digits=(16, 2),
        help='Promedio diario de trabajos totales realizados.'
    )

    diferencia_objetivo_total = fields.Integer(
        string='Diferencia vs Objetivo',
        compute='_compute_dashboard_productividad',
        store=True,
        help='Trabajos faltantes o excedentes frente al objetivo total.'
    )

    porcentaje_reparaciones_real = fields.Float(
        string='% Reparaciones Real',
        compute='_compute_dashboard_productividad',
        store=True,
        help='Porcentaje real de reparaciones, sin limitar visualmente a 100.'
    )

    porcentaje_tickets_real = fields.Float(
        string='% Tickets Real',
        compute='_compute_dashboard_productividad',
        store=True,
        help='Porcentaje real de tickets, sin limitar visualmente a 100.'
    )

    porcentaje_productividad_real = fields.Float(
        string='% Productividad Real',
        compute='_compute_dashboard_productividad',
        store=True,
        help='Porcentaje real de productividad total, sin limitar a 100.'
    )

    # ============================================================
    # ESTADOS VISUALES
    # ============================================================

    estado_productividad = fields.Selection([
        ('sin_datos', 'Sin Datos'),
        ('critico', 'Crítico'),
        ('bajo', 'Bajo'),
        ('aceptable', 'Aceptable'),
        ('bueno', 'Bueno'),
        ('excelente', 'Excelente'),
    ], string='Estado Productividad',
        compute='_compute_dashboard_estado',
        store=True
    )

    estado_dashboard = fields.Selection([
        ('sin_datos', 'Sin Datos'),
        ('requiere_revision', 'Requiere Revisión'),
        ('en_observacion', 'En Observación'),
        ('estable', 'Estable'),
        ('destacado', 'Destacado'),
    ], string='Estado Dashboard',
        compute='_compute_dashboard_estado',
        store=True
    )

    requiere_seguimiento = fields.Boolean(
        string='Requiere Seguimiento',
        compute='_compute_dashboard_estado',
        store=True
    )

    prioridad_seguimiento = fields.Selection([
        ('ninguna', 'Ninguna'),
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
        ('critica', 'Crítica'),
    ], string='Prioridad Seguimiento',
        compute='_compute_dashboard_estado',
        store=True
    )

    # ============================================================
    # COLORES Y CLASES CSS
    # ============================================================

    color_nivel_dashboard = fields.Char(
        string='Color Nivel Dashboard',
        compute='_compute_dashboard_colores',
        store=True
    )

    color_productividad_dashboard = fields.Char(
        string='Color Productividad Dashboard',
        compute='_compute_dashboard_colores',
        store=True
    )

    color_estado_dashboard = fields.Char(
        string='Color Estado Dashboard',
        compute='_compute_dashboard_colores',
        store=True
    )

    clase_css_nivel = fields.Char(
        string='Clase CSS Nivel',
        compute='_compute_dashboard_colores',
        store=True
    )

    clase_css_productividad = fields.Char(
        string='Clase CSS Productividad',
        compute='_compute_dashboard_colores',
        store=True
    )

    clase_css_estado_dashboard = fields.Char(
        string='Clase CSS Estado Dashboard',
        compute='_compute_dashboard_colores',
        store=True
    )

    icono_dashboard = fields.Char(
        string='Icono Dashboard',
        compute='_compute_dashboard_colores',
        store=True
    )

    # ============================================================
    # TEXTOS PARA KANBAN / DASHBOARD
    # ============================================================

    resumen_dashboard = fields.Char(
        string='Resumen Dashboard',
        compute='_compute_dashboard_textos',
        store=True
    )

    alerta_dashboard = fields.Char(
        string='Alerta Dashboard',
        compute='_compute_dashboard_textos',
        store=True
    )

    indicador_actividad = fields.Char(
        string='Indicador Actividad',
        compute='_compute_dashboard_textos',
        store=True
    )

    resumen_productividad = fields.Char(
        string='Resumen Productividad',
        compute='_compute_dashboard_textos',
        store=True
    )

    resumen_puntaje = fields.Char(
        string='Resumen Puntaje',
        compute='_compute_dashboard_textos',
        store=True
    )

    resumen_objetivo = fields.Char(
        string='Resumen Objetivo',
        compute='_compute_dashboard_textos',
        store=True
    )

    # ============================================================
    # DÍAS Y ACTIVIDAD
    # ============================================================

    porcentaje_dias_activos = fields.Float(
        string='% Días Activos',
        compute='_compute_dashboard_dias',
        store=True
    )

    porcentaje_dias_sin_actividad = fields.Float(
        string='% Días sin Actividad',
        compute='_compute_dashboard_dias',
        store=True
    )

    total_dias_laborales_dashboard = fields.Integer(
        string='Días Laborales Dashboard',
        compute='_compute_dashboard_dias',
        store=True
    )

    actividad_promedio_por_dia_activo = fields.Float(
        string='Promedio por Día Activo',
        compute='_compute_dashboard_dias',
        store=True,
        digits=(16, 2)
    )

    # ============================================================
    # COMPUTES PRINCIPALES
    # ============================================================

    @api.depends(
        'cantidad_reparaciones',
        'cantidad_tickets',
        'objetivo_reparaciones',
        'objetivo_tickets',
        'dias_evaluados'
    )
    def _compute_dashboard_productividad(self):
        """
        Calcula indicadores generales para dashboard.

        Importante:
        - No cambia porcentaje_reparaciones.
        - No cambia porcentaje_tickets.
        - No cambia puntaje_total.
        - Solo agrega una lectura general de productividad.
        """
        for record in self:
            cantidad_reparaciones = record.cantidad_reparaciones or 0
            cantidad_tickets = record.cantidad_tickets or 0
            objetivo_reparaciones = record.objetivo_reparaciones or 0
            objetivo_tickets = record.objetivo_tickets or 0

            total_trabajos = cantidad_reparaciones + cantidad_tickets
            objetivo_total = objetivo_reparaciones + objetivo_tickets

            record.total_trabajos_mes = total_trabajos
            record.objetivo_total_trabajos = objetivo_total
            record.diferencia_objetivo_total = total_trabajos - objetivo_total

            if objetivo_reparaciones > 0:
                record.porcentaje_reparaciones_real = (
                    cantidad_reparaciones / objetivo_reparaciones
                ) * 100
            else:
                record.porcentaje_reparaciones_real = 0

            if objetivo_tickets > 0:
                record.porcentaje_tickets_real = (
                    cantidad_tickets / objetivo_tickets
                ) * 100
            else:
                record.porcentaje_tickets_real = 0

            if objetivo_total > 0:
                productividad_real = (total_trabajos / objetivo_total) * 100
                record.porcentaje_productividad_real = productividad_real
                record.porcentaje_productividad_total = min(100, productividad_real)
            else:
                record.porcentaje_productividad_real = 0
                record.porcentaje_productividad_total = 0

            if record.dias_evaluados and record.dias_evaluados > 0:
                record.promedio_diario_total = total_trabajos / record.dias_evaluados
            else:
                record.promedio_diario_total = 0

    @api.depends(
        'porcentaje_productividad_total',
        'porcentaje_productividad_real',
        'puntaje_total',
        'nivel_desempeno',
        'necesita_capacitacion',
        'objetivo_total_trabajos',
        'total_trabajos_mes',
        'total_dias_sin_actividad'
    )
    def _compute_dashboard_estado(self):
        """
        Clasifica la productividad visual para dashboard.
        """
        for record in self:
            productividad = record.porcentaje_productividad_total or 0
            puntaje = record.puntaje_total or 0
            dias_sin_actividad = record.total_dias_sin_actividad or 0

            # Estado de productividad
            if not record.objetivo_total_trabajos:
                record.estado_productividad = 'sin_datos'
            elif productividad >= 100:
                record.estado_productividad = 'excelente'
            elif productividad >= 85:
                record.estado_productividad = 'bueno'
            elif productividad >= 70:
                record.estado_productividad = 'aceptable'
            elif productividad >= 50:
                record.estado_productividad = 'bajo'
            else:
                record.estado_productividad = 'critico'

            # Seguimiento
            requiere = bool(
                productividad < 70
                or puntaje < 70
                or record.necesita_capacitacion
                or dias_sin_actividad >= 5
            )
            record.requiere_seguimiento = requiere

            # Estado general dashboard
            if not record.objetivo_total_trabajos:
                record.estado_dashboard = 'sin_datos'
            elif productividad < 50 or puntaje < 60:
                record.estado_dashboard = 'requiere_revision'
            elif productividad < 70 or puntaje < 70 or record.necesita_capacitacion:
                record.estado_dashboard = 'en_observacion'
            elif productividad >= 90 and puntaje >= 85:
                record.estado_dashboard = 'destacado'
            else:
                record.estado_dashboard = 'estable'

            # Prioridad
            if productividad < 40 or puntaje < 50:
                record.prioridad_seguimiento = 'critica'
            elif productividad < 50 or puntaje < 60:
                record.prioridad_seguimiento = 'alta'
            elif productividad < 70 or puntaje < 70:
                record.prioridad_seguimiento = 'media'
            elif record.necesita_capacitacion:
                record.prioridad_seguimiento = 'baja'
            else:
                record.prioridad_seguimiento = 'ninguna'

    @api.depends(
        'nivel_desempeno',
        'estado_productividad',
        'estado_dashboard',
        'porcentaje_productividad_total',
        'puntaje_total',
        'requiere_seguimiento'
    )
    def _compute_dashboard_colores(self):
        """
        Define colores, clases CSS e íconos para tarjetas kanban/dashboard.
        """
        colores_nivel = {
            'deficiente': '#dc3545',
            'regular': '#fd7e14',
            'bueno': '#0d6efd',
            'muy_bueno': '#6f42c1',
            'excelente': '#198754',
        }

        clases_nivel = {
            'deficiente': 'o_eval_nivel_deficiente',
            'regular': 'o_eval_nivel_regular',
            'bueno': 'o_eval_nivel_bueno',
            'muy_bueno': 'o_eval_nivel_muy_bueno',
            'excelente': 'o_eval_nivel_excelente',
        }

        colores_productividad = {
            'sin_datos': '#6c757d',
            'critico': '#dc3545',
            'bajo': '#fd7e14',
            'aceptable': '#ffc107',
            'bueno': '#0d6efd',
            'excelente': '#198754',
        }

        clases_productividad = {
            'sin_datos': 'o_eval_prod_sin_datos',
            'critico': 'o_eval_prod_critico',
            'bajo': 'o_eval_prod_bajo',
            'aceptable': 'o_eval_prod_aceptable',
            'bueno': 'o_eval_prod_bueno',
            'excelente': 'o_eval_prod_excelente',
        }

        colores_estado = {
            'sin_datos': '#6c757d',
            'requiere_revision': '#dc3545',
            'en_observacion': '#fd7e14',
            'estable': '#0d6efd',
            'destacado': '#198754',
        }

        clases_estado = {
            'sin_datos': 'o_eval_estado_sin_datos',
            'requiere_revision': 'o_eval_estado_revision',
            'en_observacion': 'o_eval_estado_observacion',
            'estable': 'o_eval_estado_estable',
            'destacado': 'o_eval_estado_destacado',
        }

        iconos_estado = {
            'sin_datos': 'fa-question-circle',
            'requiere_revision': 'fa-exclamation-triangle',
            'en_observacion': 'fa-eye',
            'estable': 'fa-check-circle',
            'destacado': 'fa-star',
        }

        for record in self:
            record.color_nivel_dashboard = colores_nivel.get(
                record.nivel_desempeno,
                '#6c757d'
            )
            record.clase_css_nivel = clases_nivel.get(
                record.nivel_desempeno,
                'o_eval_nivel_sin_datos'
            )

            record.color_productividad_dashboard = colores_productividad.get(
                record.estado_productividad,
                '#6c757d'
            )
            record.clase_css_productividad = clases_productividad.get(
                record.estado_productividad,
                'o_eval_prod_sin_datos'
            )

            record.color_estado_dashboard = colores_estado.get(
                record.estado_dashboard,
                '#6c757d'
            )
            record.clase_css_estado_dashboard = clases_estado.get(
                record.estado_dashboard,
                'o_eval_estado_sin_datos'
            )

            record.icono_dashboard = iconos_estado.get(
                record.estado_dashboard,
                'fa-question-circle'
            )

    @api.depends(
        'total_dias_trabajados',
        'total_dias_sin_actividad',
        'total_trabajos_mes'
    )
    def _compute_dashboard_dias(self):
        """
        Calcula porcentajes de actividad por días.
        """
        for record in self:
            dias_trabajados = record.total_dias_trabajados or 0
            dias_sin_actividad = record.total_dias_sin_actividad or 0
            total_dias = dias_trabajados + dias_sin_actividad

            record.total_dias_laborales_dashboard = total_dias

            if total_dias > 0:
                record.porcentaje_dias_activos = (dias_trabajados / total_dias) * 100
                record.porcentaje_dias_sin_actividad = (dias_sin_actividad / total_dias) * 100
            else:
                record.porcentaje_dias_activos = 0
                record.porcentaje_dias_sin_actividad = 0

            if dias_trabajados > 0:
                record.actividad_promedio_por_dia_activo = (
                    (record.total_trabajos_mes or 0) / dias_trabajados
                )
            else:
                record.actividad_promedio_por_dia_activo = 0

    @api.depends(
        'nombre_usuario',
        'cantidad_reparaciones',
        'cantidad_tickets',
        'objetivo_reparaciones',
        'objetivo_tickets',
        'total_trabajos_mes',
        'objetivo_total_trabajos',
        'porcentaje_productividad_total',
        'porcentaje_productividad_real',
        'puntaje_total',
        'nivel_desempeno',
        'estado_productividad',
        'estado_dashboard',
        'requiere_seguimiento',
        'prioridad_seguimiento',
        'total_dias_trabajados',
        'total_dias_sin_actividad',
        'promedio_diario_total',
        'diferencia_objetivo_total'
    )
    def _compute_dashboard_textos(self):
        """
        Genera textos cortos para mostrar en kanban o dashboard.
        """
        nivel_labels = dict(self._fields['nivel_desempeno'].selection)
        estado_productividad_labels = dict(self._fields['estado_productividad'].selection)
        estado_dashboard_labels = dict(self._fields['estado_dashboard'].selection)
        prioridad_labels = dict(self._fields['prioridad_seguimiento'].selection)

        for record in self:
            nivel = nivel_labels.get(record.nivel_desempeno, 'Sin nivel')
            estado_productividad = estado_productividad_labels.get(
                record.estado_productividad,
                'Sin datos'
            )
            estado_dashboard = estado_dashboard_labels.get(
                record.estado_dashboard,
                'Sin datos'
            )
            prioridad = prioridad_labels.get(
                record.prioridad_seguimiento,
                'Ninguna'
            )

            record.resumen_dashboard = (
                f"{record.total_trabajos_mes or 0} trabajos / "
                f"{record.objetivo_total_trabajos or 0} objetivo "
                f"({record.porcentaje_productividad_total or 0:.1f}%)"
            )

            record.resumen_productividad = (
                f"Productividad: {record.porcentaje_productividad_total or 0:.1f}% "
                f"({estado_productividad})"
            )

            record.resumen_puntaje = (
                f"Puntaje: {record.puntaje_total or 0:.1f}% - {nivel}"
            )

            diferencia = record.diferencia_objetivo_total or 0
            if diferencia >= 0:
                record.resumen_objetivo = (
                    f"Supera el objetivo por {diferencia} trabajo(s)"
                )
            else:
                record.resumen_objetivo = (
                    f"Faltan {abs(diferencia)} trabajo(s) para el objetivo"
                )

            if record.requiere_seguimiento:
                record.alerta_dashboard = (
                    f"Requiere seguimiento - Prioridad {prioridad}"
                )
            else:
                record.alerta_dashboard = (
                    f"Estado {estado_dashboard} - Sin alertas críticas"
                )

            record.indicador_actividad = (
                f"{record.total_dias_trabajados or 0} días activos / "
                f"{record.total_dias_sin_actividad or 0} sin actividad"
            )

    # ============================================================
    # ACCIONES DASHBOARD
    # ============================================================

    def action_ver_dashboard_detalle_diario(self):
        """
        Abre el detalle diario filtrado de esta evaluación.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Detalle Diario - {self.nombre_usuario}',
            'res_model': 'evaluacion.personal.detalle.diario',
            'view_mode': 'list,form,pivot,graph',
            'domain': [('evaluacion_id', '=', self.id)],
            'context': {
                'create': False,
                'delete': False,
                'search_default_evaluacion_id': self.id,
            }
        }

    def action_ver_trabajos_dashboard(self):
        """
        Acción rápida para abrir el detalle diario.
        """
        self.ensure_one()
        return self.action_ver_dashboard_detalle_diario()

    def action_actualizar_dashboard(self):
        """
        Regenera el detalle diario y actualiza indicadores visuales.

        No cambia la fórmula original.
        """
        for record in self:
            record.action_generar_detalle_diario()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Dashboard actualizado',
                'message': 'Se actualizaron los indicadores de productividad.',
                'type': 'success',
                'sticky': False,
            }
        }


class EvaluacionPersonalDetalleDiarioDashboard(models.Model):
    _inherit = 'evaluacion.personal.detalle.diario'

    # ============================================================
    # CAMPOS VISUALES PARA DASHBOARD DIARIO
    # ============================================================

    color_estado_dia = fields.Char(
        string='Color Estado Día',
        compute='_compute_dashboard_dia_colores',
        store=True
    )

    clase_css_estado_dia = fields.Char(
        string='Clase CSS Estado Día',
        compute='_compute_dashboard_dia_colores',
        store=True
    )

    icono_estado_dia = fields.Char(
        string='Icono Estado Día',
        compute='_compute_dashboard_dia_colores',
        store=True
    )

    resumen_dia_dashboard = fields.Char(
        string='Resumen Día Dashboard',
        compute='_compute_dashboard_dia_textos',
        store=True
    )

    productividad_dia_texto = fields.Char(
        string='Productividad Día',
        compute='_compute_dashboard_dia_textos',
        store=True
    )

    alerta_dia_dashboard = fields.Char(
        string='Alerta Día Dashboard',
        compute='_compute_dashboard_dia_textos',
        store=True
    )

    @api.depends('estado_dia')
    def _compute_dashboard_dia_colores(self):
        colores = {
            'sin_actividad': '#6c757d',
            'bajo': '#dc3545',
            'aceptable': '#ffc107',
            'bueno': '#0d6efd',
            'excelente': '#198754',
        }

        clases = {
            'sin_actividad': 'o_eval_dia_sin_actividad',
            'bajo': 'o_eval_dia_bajo',
            'aceptable': 'o_eval_dia_aceptable',
            'bueno': 'o_eval_dia_bueno',
            'excelente': 'o_eval_dia_excelente',
        }

        iconos = {
            'sin_actividad': 'fa-minus-circle',
            'bajo': 'fa-exclamation-triangle',
            'aceptable': 'fa-adjust',
            'bueno': 'fa-check-circle',
            'excelente': 'fa-star',
        }

        for record in self:
            record.color_estado_dia = colores.get(record.estado_dia, '#6c757d')
            record.clase_css_estado_dia = clases.get(
                record.estado_dia,
                'o_eval_dia_sin_datos'
            )
            record.icono_estado_dia = iconos.get(
                record.estado_dia,
                'fa-question-circle'
            )

    @api.depends(
        'fecha',
        'dia_semana',
        'cantidad_reparaciones',
        'cantidad_tickets',
        'total_trabajos',
        'objetivo_dia',
        'porcentaje_cumplimiento',
        'estado_dia',
        'clientes_atendidos',
        'modelos_trabajados'
    )
    def _compute_dashboard_dia_textos(self):
        estado_labels = dict(self._fields['estado_dia'].selection)

        for record in self:
            estado = estado_labels.get(record.estado_dia, 'Sin datos')

            if record.fecha:
                fecha_texto = record.fecha.strftime('%d/%m/%Y')
            else:
                fecha_texto = ''

            record.resumen_dia_dashboard = (
                f"{record.dia_semana or ''} {fecha_texto} - "
                f"{record.total_trabajos or 0} trabajo(s)"
            )

            record.productividad_dia_texto = (
                f"{record.total_trabajos or 0}/{record.objetivo_dia or 0} "
                f"({record.porcentaje_cumplimiento or 0:.1f}%) - {estado}"
            )

            if not record.es_dia_laboral:
                record.alerta_dia_dashboard = 'Día no laboral'
            elif record.total_trabajos == 0:
                record.alerta_dia_dashboard = 'Sin actividad registrada'
            elif record.cumple_objetivo:
                record.alerta_dia_dashboard = 'Cumple objetivo diario'
            elif record.porcentaje_cumplimiento >= 70:
                record.alerta_dia_dashboard = 'Cerca del objetivo diario'
            else:
                record.alerta_dia_dashboard = 'Bajo rendimiento diario'