# -*- coding: utf-8 -*-

from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
import logging


_logger = logging.getLogger(__name__)


class EvaluacionPersonalDashboard(models.Model):
    """
    Extensión gerencial de evaluacion.personal.

    IMPORTANTE:
    Este modelo NO recalcula ni reemplaza la lógica del bono.

    Su función es transformar los resultados ya calculados por
    evaluacion.personal en información gerencial clara:

    - Meta real aplicada.
    - Producción real válida.
    - Cumplimiento según perfil.
    - Calidad.
    - Encuestas.
    - Reclamos.
    - Asistencia.
    - Bono.
    - Comparaciones históricas.
    - Evolución mensual/anual.

    No se utilizan objetivo_reparaciones + objetivo_tickets como
    productividad principal del dashboard, porque esos campos pertenecen
    a la evaluación histórica/anterior y no representan necesariamente
    la meta real mensual usada actualmente para el bono.
    """

    _inherit = 'evaluacion.personal'

    # ============================================================
    # IDENTIFICACIÓN GERENCIAL
    # ============================================================

    dashboard_tipo_operativo_texto = fields.Char(
        string='Perfil operativo',
        compute='_compute_dashboard_identificacion',
        store=True,
    )

    dashboard_periodo = fields.Char(
        string='Periodo',
        compute='_compute_dashboard_identificacion',
        store=True,
    )

    dashboard_unidad_produccion = fields.Char(
        string='Unidad de producción',
        compute='_compute_dashboard_identificacion',
        store=True,
    )

    # ============================================================
    # PRODUCCIÓN GERENCIAL
    # ============================================================

    dashboard_meta_principal = fields.Float(
        string='Meta aplicada',
        compute='_compute_dashboard_produccion',
        store=True,
        digits=(16, 2),
        help=(
            'Meta real utilizada para mostrar el cumplimiento gerencial. '
            'Para taller proviene de meta_taller_ajustada, para servicios '
            'de meta_servicios_ajustada y para mixtos representa la suma '
            'de ambas metas.'
        ),
    )

    dashboard_real_principal = fields.Float(
        string='Producción realizada',
        compute='_compute_dashboard_produccion',
        store=True,
        digits=(16, 2),
    )

    dashboard_porcentaje_produccion = fields.Float(
        string='% Producción',
        compute='_compute_dashboard_produccion',
        store=True,
        digits=(16, 2),
        help=(
            'Porcentaje oficial de producción mensual procedente de '
            'porcentaje_produccion_total.'
        ),
    )

    dashboard_diferencia_meta = fields.Float(
        string='Diferencia contra meta',
        compute='_compute_dashboard_produccion',
        store=True,
        digits=(16, 2),
    )

    dashboard_faltante_meta = fields.Float(
        string='Faltante para meta',
        compute='_compute_dashboard_produccion',
        store=True,
        digits=(16, 2),
    )

    dashboard_exceso_meta = fields.Float(
        string='Sobreproducción',
        compute='_compute_dashboard_produccion',
        store=True,
        digits=(16, 2),
    )

    dashboard_cumple_meta = fields.Boolean(
        string='Cumple meta',
        compute='_compute_dashboard_produccion',
        store=True,
    )

    dashboard_cumple_minimo_bono_produccion = fields.Boolean(
        string='Cumple mínimo 95%',
        compute='_compute_dashboard_produccion',
        store=True,
    )

    dashboard_resumen_produccion = fields.Char(
        string='Resumen producción',
        compute='_compute_dashboard_produccion',
        store=True,
    )

    dashboard_detalle_taller = fields.Char(
        string='Detalle producción taller',
        compute='_compute_dashboard_produccion',
        store=True,
    )

    dashboard_detalle_servicios = fields.Char(
        string='Detalle producción servicios',
        compute='_compute_dashboard_produccion',
        store=True,
    )

    # ============================================================
    # ENCUESTAS GERENCIALES
    # ============================================================

    dashboard_encuestas_generadas = fields.Integer(
        string='Encuestas generadas',
        compute='_compute_dashboard_encuestas',
        store=False,
    )

    dashboard_encuestas_respondidas = fields.Integer(
        string='Encuestas respondidas',
        compute='_compute_dashboard_encuestas',
        store=False,
    )

    dashboard_encuestas_no_respondidas = fields.Integer(
        string='Encuestas no respondidas',
        compute='_compute_dashboard_encuestas',
        store=False,
    )

    dashboard_encuestas_requeridas = fields.Integer(
        string='Encuestas mínimas requeridas',
        compute='_compute_dashboard_encuestas',
        store=False,
    )

    dashboard_encuestas_faltantes = fields.Integer(
        string='Encuestas faltantes',
        compute='_compute_dashboard_encuestas',
        store=False,
    )

    dashboard_porcentaje_respuesta_encuestas = fields.Float(
        string='% Respuesta de encuestas',
        compute='_compute_dashboard_encuestas',
        store=False,
        digits=(16, 2),
    )

    dashboard_porcentaje_cobertura_minima = fields.Float(
        string='% Cobertura mínima',
        compute='_compute_dashboard_encuestas',
        store=False,
        digits=(16, 2),
    )

    dashboard_encuestas_aplican = fields.Boolean(
        string='Aplican encuestas',
        compute='_compute_dashboard_encuestas',
        store=False,
    )

    dashboard_cumple_encuestas = fields.Boolean(
        string='Cumple encuestas',
        compute='_compute_dashboard_encuestas',
        store=False,
    )

    dashboard_resumen_encuestas = fields.Char(
        string='Resumen encuestas',
        compute='_compute_dashboard_encuestas',
        store=False,
    )

    # ============================================================
    # CALIDAD Y RECLAMOS
    # ============================================================

    dashboard_calidad = fields.Float(
        string='Calidad',
        compute='_compute_dashboard_calidad',
        store=True,
        digits=(16, 2),
    )

    dashboard_estado_calidad = fields.Selection(
        [
            ('sin_datos', 'Sin datos'),
            ('critica', 'Crítica'),
            ('baja', 'Baja'),
            ('aceptable', 'Aceptable'),
            ('buena', 'Buena'),
            ('excelente', 'Excelente'),
        ],
        string='Estado calidad',
        compute='_compute_dashboard_calidad',
        store=True,
    )

    dashboard_resumen_calidad = fields.Char(
        string='Resumen calidad',
        compute='_compute_dashboard_calidad',
        store=True,
    )

    dashboard_tiene_reclamos = fields.Boolean(
        string='Tiene reclamos',
        compute='_compute_dashboard_calidad',
        store=True,
    )

    # ============================================================
    # ASISTENCIA Y APOYO
    # ============================================================

    dashboard_asistencia = fields.Float(
        string='Asistencia',
        compute='_compute_dashboard_asistencia',
        store=True,
        digits=(16, 2),
    )

    dashboard_apoyo = fields.Float(
        string='Apoyo',
        compute='_compute_dashboard_asistencia',
        store=True,
        digits=(16, 2),
    )

    dashboard_resumen_asistencia = fields.Char(
        string='Resumen asistencia',
        compute='_compute_dashboard_asistencia',
        store=True,
    )

    # ============================================================
    # ACTIVIDAD Y DISPONIBILIDAD
    # ============================================================

    dashboard_dias_laborables = fields.Float(
        string='Días laborables',
        compute='_compute_dashboard_disponibilidad',
        store=True,
        digits=(16, 2),
    )

    dashboard_dias_ausencia = fields.Float(
        string='Días descontados',
        compute='_compute_dashboard_disponibilidad',
        store=True,
        digits=(16, 2),
    )

    dashboard_dias_servicio = fields.Float(
        string='Días en servicios',
        compute='_compute_dashboard_disponibilidad',
        store=True,
        digits=(16, 2),
    )

    dashboard_dias_taller = fields.Float(
        string='Días disponibles taller',
        compute='_compute_dashboard_disponibilidad',
        store=True,
        digits=(16, 2),
    )

    dashboard_horas_servicio = fields.Float(
        string='Horas de servicio',
        compute='_compute_dashboard_disponibilidad',
        store=True,
        digits=(16, 2),
    )

    dashboard_dias_con_actividad = fields.Integer(
        string='Días con actividad',
        compute='_compute_dashboard_disponibilidad',
        store=True,
    )

    dashboard_dias_sin_actividad = fields.Integer(
        string='Días sin actividad',
        compute='_compute_dashboard_disponibilidad',
        store=True,
    )

    dashboard_porcentaje_dias_activos = fields.Float(
        string='% Días activos',
        compute='_compute_dashboard_disponibilidad',
        store=True,
        digits=(16, 2),
    )

    dashboard_promedio_por_dia_activo = fields.Float(
        string='Producción promedio por día activo',
        compute='_compute_dashboard_disponibilidad',
        store=True,
        digits=(16, 2),
    )

    # ============================================================
    # BONO GERENCIAL
    # ============================================================

    dashboard_aplica_bono = fields.Boolean(
        string='Accede al bono',
        compute='_compute_dashboard_bono',
        store=True,
    )

    dashboard_bono_bloqueado = fields.Boolean(
        string='Bono bloqueado',
        compute='_compute_dashboard_bono',
        store=True,
    )

    dashboard_motivo_bono_corto = fields.Char(
        string='Motivo bono',
        compute='_compute_dashboard_bono',
        store=True,
    )

    dashboard_motivos_bloqueo_bono = fields.Text(
        string='Motivos de bloqueo',
        compute='_compute_dashboard_bono',
        store=True,
    )

    dashboard_estado_bono = fields.Selection(
        [
            ('no_aplica', 'No aplica'),
            ('bloqueado', 'Bloqueado'),
            ('sin_bono', 'Sin bono'),
            ('bono_150', 'Bono S/ 150'),
            ('bono_250', 'Bono S/ 250'),
            ('bono_350', 'Bono S/ 350'),
            ('acelerador', 'Bono + acelerador'),
        ],
        string='Estado bono',
        compute='_compute_dashboard_bono',
        store=True,
    )

    # ============================================================
    # ESTADO GENERAL GERENCIAL
    # ============================================================

    dashboard_estado = fields.Selection(
        [
            ('sin_datos', 'Sin datos'),
            ('critico', 'Crítico'),
            ('requiere_revision', 'Requiere revisión'),
            ('en_observacion', 'En observación'),
            ('estable', 'Estable'),
            ('destacado', 'Destacado'),
        ],
        string='Estado gerencial',
        compute='_compute_dashboard_estado',
        store=True,
    )

    dashboard_requiere_seguimiento = fields.Boolean(
        string='Requiere seguimiento',
        compute='_compute_dashboard_estado',
        store=True,
    )

    dashboard_prioridad = fields.Selection(
        [
            ('ninguna', 'Ninguna'),
            ('baja', 'Baja'),
            ('media', 'Media'),
            ('alta', 'Alta'),
            ('critica', 'Crítica'),
        ],
        string='Prioridad seguimiento',
        compute='_compute_dashboard_estado',
        store=True,
    )

    dashboard_alerta_principal = fields.Char(
        string='Alerta principal',
        compute='_compute_dashboard_estado',
        store=True,
    )

    dashboard_resumen_general = fields.Text(
        string='Resumen gerencial',
        compute='_compute_dashboard_estado',
        store=True,
    )

    # ============================================================
    # COLORES E ICONOS
    # ============================================================

    dashboard_color_estado = fields.Char(
        string='Color estado',
        compute='_compute_dashboard_visual',
        store=True,
    )

    dashboard_color_produccion = fields.Char(
        string='Color producción',
        compute='_compute_dashboard_visual',
        store=True,
    )

    dashboard_color_calidad = fields.Char(
        string='Color calidad',
        compute='_compute_dashboard_visual',
        store=True,
    )

    dashboard_color_bono = fields.Char(
        string='Color bono',
        compute='_compute_dashboard_visual',
        store=True,
    )

    dashboard_icono_estado = fields.Char(
        string='Icono estado',
        compute='_compute_dashboard_visual',
        store=True,
    )

    dashboard_clase_estado = fields.Char(
        string='Clase CSS estado',
        compute='_compute_dashboard_visual',
        store=True,
    )

    # ============================================================
    # COMPARACIÓN MES ANTERIOR
    # ============================================================

    dashboard_mes_anterior_id = fields.Many2one(
        'evaluacion.personal',
        string='Evaluación mes anterior',
        compute='_compute_dashboard_comparaciones',
        store=False,
    )

    dashboard_produccion_mes_anterior = fields.Float(
        string='Producción mes anterior',
        compute='_compute_dashboard_comparaciones',
        store=False,
        digits=(16, 2),
    )

    dashboard_calidad_mes_anterior = fields.Float(
        string='Calidad mes anterior',
        compute='_compute_dashboard_comparaciones',
        store=False,
        digits=(16, 2),
    )

    dashboard_bono_mes_anterior = fields.Float(
        string='Bono mes anterior',
        compute='_compute_dashboard_comparaciones',
        store=False,
    )

    dashboard_variacion_produccion_mes = fields.Float(
        string='Variación producción mensual',
        compute='_compute_dashboard_comparaciones',
        store=False,
        digits=(16, 2),
    )

    dashboard_variacion_calidad_mes = fields.Float(
        string='Variación calidad mensual',
        compute='_compute_dashboard_comparaciones',
        store=False,
        digits=(16, 2),
    )

    # ============================================================
    # COMPARACIÓN MISMO MES AÑO ANTERIOR
    # ============================================================

    dashboard_anio_anterior_id = fields.Many2one(
        'evaluacion.personal',
        string='Evaluación mismo mes año anterior',
        compute='_compute_dashboard_comparaciones',
        store=False,
    )

    dashboard_produccion_anio_anterior = fields.Float(
        string='Producción año anterior',
        compute='_compute_dashboard_comparaciones',
        store=False,
        digits=(16, 2),
    )

    dashboard_calidad_anio_anterior = fields.Float(
        string='Calidad año anterior',
        compute='_compute_dashboard_comparaciones',
        store=False,
        digits=(16, 2),
    )

    dashboard_bono_anio_anterior = fields.Float(
        string='Bono año anterior',
        compute='_compute_dashboard_comparaciones',
        store=False,
    )

    dashboard_variacion_produccion_anual = fields.Float(
        string='Variación producción anual',
        compute='_compute_dashboard_comparaciones',
        store=False,
        digits=(16, 2),
    )

    dashboard_variacion_calidad_anual = fields.Float(
        string='Variación calidad anual',
        compute='_compute_dashboard_comparaciones',
        store=False,
        digits=(16, 2),
    )

    # ============================================================
    # TENDENCIA
    # ============================================================

    dashboard_tendencia = fields.Selection(
        [
            ('sin_historial', 'Sin historial'),
            ('baja_fuerte', 'Baja fuerte'),
            ('baja', 'Baja'),
            ('estable', 'Estable'),
            ('mejora', 'Mejora'),
            ('mejora_fuerte', 'Mejora fuerte'),
        ],
        string='Tendencia',
        compute='_compute_dashboard_comparaciones',
        store=False,
    )

    dashboard_tendencia_texto = fields.Char(
        string='Tendencia',
        compute='_compute_dashboard_comparaciones',
        store=False,
    )

    # ============================================================
    # HISTORIAL PARA GRÁFICAS
    # ============================================================

    dashboard_historial_12_meses = fields.Json(
        string='Historial últimos 12 meses',
        compute='_compute_dashboard_historial',
        store=False,
    )

    dashboard_historial_anual = fields.Json(
        string='Resumen por año',
        compute='_compute_dashboard_historial',
        store=False,
    )

    # ============================================================
    # IDENTIFICACIÓN
    # ============================================================

    @api.depends(
        'tipo_operativo',
        'fecha',
        'mes',
        'anio',
    )
    def _compute_dashboard_identificacion(self):
        for record in self:
            if record.tipo_operativo == 'taller':
                tipo = 'Técnico de Taller'
                unidad = 'reparaciones'
            elif record.tipo_operativo == 'servicios':
                tipo = 'Técnico de Servicios / Alquiler'
                unidad = 'servicios'
            else:
                tipo = 'Técnico Mixto'
                unidad = 'producción ponderada'

            record.dashboard_tipo_operativo_texto = tipo
            record.dashboard_unidad_produccion = unidad

            if record.mes and record.anio:
                record.dashboard_periodo = '%s %s' % (
                    record.mes,
                    record.anio,
                )
            elif record.fecha:
                record.dashboard_periodo = record.fecha.strftime('%m/%Y')
            else:
                record.dashboard_periodo = ''

    # ============================================================
    # PRODUCCIÓN
    # ============================================================

    @api.depends(
        'tipo_operativo',
        'meta_taller_ajustada',
        'meta_servicios_ajustada',
        'reparaciones_validas_bono',
        'tickets_validos_bono',
        'porcentaje_produccion_taller',
        'porcentaje_produccion_servicios',
        'porcentaje_produccion_total',
    )
    def _compute_dashboard_produccion(self):
        for record in self:
            meta_taller = record.meta_taller_ajustada or 0.0
            meta_servicios = record.meta_servicios_ajustada or 0.0

            reparaciones = record.reparaciones_validas_bono or 0
            servicios = record.tickets_validos_bono or 0

            porcentaje = record.porcentaje_produccion_total or 0.0

            if record.tipo_operativo == 'taller':
                meta = meta_taller
                real = float(reparaciones)

            elif record.tipo_operativo == 'servicios':
                meta = meta_servicios
                real = float(servicios)

            else:
                # Para el mixto la visualización principal muestra las
                # dos metas juntas, pero el porcentaje oficial continúa
                # siendo porcentaje_produccion_total, porque está
                # ponderado correctamente por el modelo de evaluación.
                meta = meta_taller + meta_servicios
                real = float(reparaciones + servicios)

            diferencia = real - meta

            record.dashboard_meta_principal = meta
            record.dashboard_real_principal = real
            record.dashboard_porcentaje_produccion = porcentaje
            record.dashboard_diferencia_meta = diferencia

            record.dashboard_faltante_meta = (
                abs(diferencia)
                if diferencia < 0
                else 0.0
            )

            record.dashboard_exceso_meta = (
                diferencia
                if diferencia > 0
                else 0.0
            )

            record.dashboard_cumple_meta = (
                bool(meta)
                and porcentaje >= 100.0
            )

            record.dashboard_cumple_minimo_bono_produccion = (
                bool(meta)
                and porcentaje >= 95.0
            )

            record.dashboard_detalle_taller = (
                '%s / %.2f reparaciones (%.2f%%)'
                % (
                    reparaciones,
                    meta_taller,
                    record.porcentaje_produccion_taller or 0.0,
                )
            )

            record.dashboard_detalle_servicios = (
                '%s / %.2f servicios (%.2f%%)'
                % (
                    servicios,
                    meta_servicios,
                    record.porcentaje_produccion_servicios or 0.0,
                )
            )

            if not meta:
                record.dashboard_resumen_produccion = (
                    'Sin meta mensual disponible'
                )

            elif porcentaje >= 100:
                record.dashboard_resumen_produccion = (
                    'Meta superada: %.2f%% de cumplimiento'
                    % porcentaje
                )

            elif porcentaje >= 95:
                record.dashboard_resumen_produccion = (
                    'Cumple mínimo para bono: %.2f%%'
                    % porcentaje
                )

            else:
                record.dashboard_resumen_produccion = (
                    'Producción %.2f%% - por debajo del mínimo de 95%%'
                    % porcentaje
                )

    # ============================================================
    # HELPERS ENCUESTAS
    # ============================================================

    def _dashboard_get_encuestas_periodo(self):
        """
        Recupera TODAS las encuestas generadas asociadas a los servicios
        válidos del técnico durante el periodo.

        A diferencia de evaluacion_servicio_ids, este helper no limita
        únicamente a encuestas completadas.

        Esto permite que gerencia vea:

            generadas
            respondidas
            no respondidas
            cobertura
        """
        self.ensure_one()

        EvaluacionServicio = self.env['client.service.evaluation']

        if not self.usuario_id or not self.fecha:
            return EvaluacionServicio.browse()

        if self.tipo_operativo not in ('servicios', 'mixto'):
            return EvaluacionServicio.browse()

        inicio_mes, fin_mes = self._get_rango_mes_bono()

        tickets = self._get_tickets_bono(
            inicio_mes,
            fin_mes,
        )

        if not tickets:
            return EvaluacionServicio.browse()

        domain = [
            ('technician_id', '=', self.usuario_id.id),
            ('ticket_ids', 'in', tickets.ids),
        ]

        return EvaluacionServicio.search(domain)

    # ============================================================
    # ENCUESTAS
    # ============================================================

    @api.depends(
        'usuario_id',
        'fecha',
        'tipo_operativo',
        'tickets_validos_bono',
        'evaluaciones_servicio_count',
        'evaluaciones_servicio_minimas',
        'evaluaciones_servicio_faltantes',
        'cumple_minimo_evaluaciones',
        'promedio_evaluacion_servicio',
        'evaluaciones_criticas_count',
    )
    def _compute_dashboard_encuestas(self):
        for record in self:
            aplica = (
                record.tipo_operativo in ('servicios', 'mixto')
                and (record.tickets_validos_bono or 0) > 0
            )

            record.dashboard_encuestas_aplican = aplica

            if not aplica:
                record.dashboard_encuestas_generadas = 0
                record.dashboard_encuestas_respondidas = 0
                record.dashboard_encuestas_no_respondidas = 0
                record.dashboard_encuestas_requeridas = 0
                record.dashboard_encuestas_faltantes = 0
                record.dashboard_porcentaje_respuesta_encuestas = 0.0
                record.dashboard_porcentaje_cobertura_minima = 0.0
                record.dashboard_cumple_encuestas = True
                record.dashboard_resumen_encuestas = (
                    'No aplica para técnico exclusivo de taller'
                )
                continue

            todas = record._dashboard_get_encuestas_periodo()

            respondidas = todas.filtered(
                lambda ev:
                    ev.state == 'completed'
                    and bool(ev.response_date)
            )

            total_generadas = len(todas)
            total_respondidas = len(respondidas)
            no_respondidas = max(
                0,
                total_generadas - total_respondidas,
            )

            requeridas = (
                record.evaluaciones_servicio_minimas or 0
            )

            faltantes = max(
                0,
                requeridas - total_respondidas,
            )

            if total_generadas > 0:
                porcentaje_respuesta = (
                    total_respondidas
                    / total_generadas
                    * 100.0
                )
            else:
                porcentaje_respuesta = 0.0

            if requeridas > 0:
                porcentaje_cobertura = min(
                    100.0,
                    total_respondidas
                    / requeridas
                    * 100.0,
                )
            else:
                porcentaje_cobertura = 100.0

            cumple = (
                faltantes == 0
                if requeridas > 0
                else True
            )

            record.dashboard_encuestas_generadas = total_generadas
            record.dashboard_encuestas_respondidas = total_respondidas
            record.dashboard_encuestas_no_respondidas = no_respondidas
            record.dashboard_encuestas_requeridas = requeridas
            record.dashboard_encuestas_faltantes = faltantes

            record.dashboard_porcentaje_respuesta_encuestas = (
                porcentaje_respuesta
            )

            record.dashboard_porcentaje_cobertura_minima = (
                porcentaje_cobertura
            )

            record.dashboard_cumple_encuestas = cumple

            if cumple:
                record.dashboard_resumen_encuestas = (
                    '%s respondidas / %s requeridas - cumple cobertura'
                    % (
                        total_respondidas,
                        requeridas,
                    )
                )
            else:
                record.dashboard_resumen_encuestas = (
                    '%s respondidas / %s requeridas - faltan %s'
                    % (
                        total_respondidas,
                        requeridas,
                        faltantes,
                    )
                )

    # ============================================================
    # CALIDAD
    # ============================================================

    @api.depends(
        'puntaje_calidad_real',
        'reclamos_procedentes_count',
        'evaluaciones_criticas_count',
        'promedio_evaluacion_servicio',
    )
    def _compute_dashboard_calidad(self):
        for record in self:
            calidad = record.puntaje_calidad_real or 0.0
            reclamos = record.reclamos_procedentes_count or 0

            record.dashboard_calidad = calidad
            record.dashboard_tiene_reclamos = reclamos > 0

            if calidad <= 0:
                estado = 'sin_datos'
            elif calidad < 60:
                estado = 'critica'
            elif calidad < 70:
                estado = 'baja'
            elif calidad < 80:
                estado = 'aceptable'
            elif calidad < 90:
                estado = 'buena'
            else:
                estado = 'excelente'

            record.dashboard_estado_calidad = estado

            if reclamos:
                record.dashboard_resumen_calidad = (
                    'Calidad %.2f%% - %s reclamo(s) procedente(s)'
                    % (
                        calidad,
                        reclamos,
                    )
                )
            else:
                record.dashboard_resumen_calidad = (
                    'Calidad %.2f%% - sin reclamos procedentes'
                    % calidad
                )

    # ============================================================
    # ASISTENCIA
    # ============================================================

    @api.depends(
        'puntaje_asistencia_real',
        'puntaje_apoyo_real',
        'faltas_injustificadas_equivalentes',
    )
    def _compute_dashboard_asistencia(self):
        for record in self:
            asistencia = (
                record.puntaje_asistencia_real or 0.0
            )

            apoyo = (
                record.puntaje_apoyo_real or 0.0
            )

            record.dashboard_asistencia = asistencia
            record.dashboard_apoyo = apoyo

            if record.faltas_injustificadas_equivalentes:
                record.dashboard_resumen_asistencia = (
                    'Asistencia %.2f%% - %.2f falta(s) injustificada(s)'
                    % (
                        asistencia,
                        record.faltas_injustificadas_equivalentes,
                    )
                )
            else:
                record.dashboard_resumen_asistencia = (
                    'Asistencia %.2f%% - sin faltas injustificadas'
                    % asistencia
                )

    # ============================================================
    # DISPONIBILIDAD
    # ============================================================

    @api.depends(
        'dias_laborables_equivalentes',
        'dias_ausencia_equivalentes',
        'dias_servicio_equivalentes',
        'dias_taller_disponibles',
        'horas_servicio_mes',
        'total_dias_trabajados',
        'total_dias_sin_actividad',
        'reparaciones_validas_bono',
        'tickets_validos_bono',
    )
    def _compute_dashboard_disponibilidad(self):
        for record in self:
            record.dashboard_dias_laborables = (
                record.dias_laborables_equivalentes or 0.0
            )

            record.dashboard_dias_ausencia = (
                record.dias_ausencia_equivalentes or 0.0
            )

            record.dashboard_dias_servicio = (
                record.dias_servicio_equivalentes or 0.0
            )

            record.dashboard_dias_taller = (
                record.dias_taller_disponibles or 0.0
            )

            record.dashboard_horas_servicio = (
                record.horas_servicio_mes or 0.0
            )

            dias_activos = record.total_dias_trabajados or 0
            dias_sin = record.total_dias_sin_actividad or 0

            record.dashboard_dias_con_actividad = dias_activos
            record.dashboard_dias_sin_actividad = dias_sin

            total_dias = dias_activos + dias_sin

            if total_dias:
                record.dashboard_porcentaje_dias_activos = (
                    dias_activos / total_dias * 100.0
                )
            else:
                record.dashboard_porcentaje_dias_activos = 0.0

            produccion = (
                (record.reparaciones_validas_bono or 0)
                + (record.tickets_validos_bono or 0)
            )

            if dias_activos:
                record.dashboard_promedio_por_dia_activo = (
                    produccion / dias_activos
                )
            else:
                record.dashboard_promedio_por_dia_activo = 0.0

    # ============================================================
    # BONO
    # ============================================================

    @api.depends(
        'tipo_operativo',
        'bono_final',
        'bono_base',
        'monto_acelerador',
        'aplica_acelerador',
        'puntaje_total_bono',
        'porcentaje_produccion_total',
        'reclamos_procedentes_count',
        'evaluaciones_criticas_count',
        'faltas_injustificadas_equivalentes',
        'cumple_minimo_evaluaciones',
        'evaluaciones_servicio_faltantes',
        'evaluaciones_servicio_minimas',
        'tickets_validos_bono',
        'cierre_confirmado_disponible',
    )
    def _compute_dashboard_bono(self):
        for record in self:
            motivos = []

            produccion = (
                record.porcentaje_produccion_total or 0.0
            )

            # --------------------------------------------
            # Producción mínima
            # --------------------------------------------

            if produccion < 95.0:
                motivos.append(
                    'Producción %.2f%%: mínimo requerido 95%%.'
                    % produccion
                )

            # --------------------------------------------
            # Encuestas
            # --------------------------------------------

            requiere_encuestas = (
                record.tipo_operativo in ('servicios', 'mixto')
                and (record.tickets_validos_bono or 0) > 0
                and (record.evaluaciones_servicio_minimas or 0) > 0
            )

            if (
                requiere_encuestas
                and not record.cumple_minimo_evaluaciones
            ):
                motivos.append(
                    'Faltan %s encuesta(s) respondida(s) para cumplir '
                    'la cobertura mínima.'
                    % (
                        record.evaluaciones_servicio_faltantes or 0
                    )
                )

            # --------------------------------------------
            # Reclamos
            # --------------------------------------------

            if (record.reclamos_procedentes_count or 0) >= 5:
                motivos.append(
                    'Tiene %s reclamos procedentes; con 5 o más '
                    'reclamos el bono queda bloqueado.'
                    % record.reclamos_procedentes_count
                )

            # --------------------------------------------
            # Cierre mensual
            # --------------------------------------------

            if (
                record.tipo_operativo in ('taller', 'mixto')
                and not record.cierre_confirmado_disponible
            ):
                motivos.append(
                    'No existe cierre mensual confirmado con meta '
                    'asignada para el técnico.'
                )

            bloqueado = bool(motivos)

            record.dashboard_bono_bloqueado = bloqueado

            bono = record.bono_final or 0.0

            record.dashboard_aplica_bono = (
                not bloqueado
                and bono > 0
            )

            if motivos:
                record.dashboard_motivos_bloqueo_bono = '\n'.join(
                    '• %s' % motivo
                    for motivo in motivos
                )

                record.dashboard_motivo_bono_corto = motivos[0]

            elif bono > 0:
                record.dashboard_motivos_bloqueo_bono = False

                record.dashboard_motivo_bono_corto = (
                    'Cumple condiciones del bono mensual'
                )

            else:
                record.dashboard_motivos_bloqueo_bono = False

                record.dashboard_motivo_bono_corto = (
                    'Cumple condiciones obligatorias, pero el '
                    'puntaje total no alcanza una escala de bono'
                )

            if bloqueado:
                estado = 'bloqueado'

            elif record.aplica_acelerador:
                estado = 'acelerador'

            elif bono >= 350:
                estado = 'bono_350'

            elif bono >= 250:
                estado = 'bono_250'

            elif bono >= 150:
                estado = 'bono_150'

            else:
                estado = 'sin_bono'

            record.dashboard_estado_bono = estado

    # ============================================================
    # ESTADO GENERAL GERENCIAL
    # ============================================================

    @api.depends(
        'dashboard_meta_principal',
        'dashboard_porcentaje_produccion',
        'puntaje_calidad_real',
        'puntaje_asistencia_real',
        'reclamos_procedentes_count',
        'evaluaciones_criticas_count',
        'cumple_minimo_evaluaciones',
        'necesita_capacitacion',
        'bono_final',
        'dashboard_bono_bloqueado',
    )
    def _compute_dashboard_estado(self):
        for record in self:
            meta = record.dashboard_meta_principal or 0.0
            produccion = (
                record.dashboard_porcentaje_produccion or 0.0
            )
            calidad = record.puntaje_calidad_real or 0.0
            asistencia = record.puntaje_asistencia_real or 0.0
            reclamos = record.reclamos_procedentes_count or 0

            if not meta:
                estado = 'sin_datos'
                prioridad = 'ninguna'
                seguimiento = False
                alerta = 'Sin meta mensual disponible'

            elif produccion < 70 or calidad < 60:
                estado = 'critico'
                prioridad = 'critica'
                seguimiento = True
                alerta = 'Rendimiento crítico - requiere revisión inmediata'

            elif (
                produccion < 80
                or calidad < 70
                or reclamos >= 3
            ):
                estado = 'requiere_revision'
                prioridad = 'alta'
                seguimiento = True
                alerta = 'Requiere revisión gerencial'

            elif (
                produccion < 95
                or calidad < 80
                or not record.cumple_minimo_evaluaciones
                or record.necesita_capacitacion
            ):
                estado = 'en_observacion'
                prioridad = 'media'
                seguimiento = True
                alerta = 'En observación'

            elif (
                produccion >= 100
                and calidad >= 90
                and asistencia >= 90
                and reclamos == 0
                and record.cumple_minimo_evaluaciones
            ):
                estado = 'destacado'
                prioridad = 'ninguna'
                seguimiento = False
                alerta = 'Desempeño destacado'

            else:
                estado = 'estable'
                prioridad = 'baja'
                seguimiento = False
                alerta = 'Desempeño estable'

            record.dashboard_estado = estado
            record.dashboard_prioridad = prioridad
            record.dashboard_requiere_seguimiento = seguimiento
            record.dashboard_alerta_principal = alerta

            lineas = [
                'Técnico: %s'
                % (
                    record.usuario_id.name
                    if record.usuario_id
                    else 'Sin técnico'
                ),
                'Periodo: %s'
                % (record.dashboard_periodo or ''),
                'Perfil: %s'
                % (
                    record.dashboard_tipo_operativo_texto
                    or ''
                ),
                '',
                'Producción: %.2f%%.'
                % produccion,
                'Calidad: %.2f%%.'
                % calidad,
                'Asistencia: %.2f%%.'
                % asistencia,
                'Reclamos procedentes: %s.'
                % reclamos,
            ]

            if record.tipo_operativo in ('servicios', 'mixto'):
                lineas.extend([
                    'Evaluaciones respondidas: %s.'
                    % record.evaluaciones_servicio_count,
                    'Evaluaciones mínimas requeridas: %s.'
                    % record.evaluaciones_servicio_minimas,
                ])

            lineas.extend([
                'Bono final: S/ %.2f.'
                % (record.bono_final or 0.0),
                'Estado: %s.'
                % alerta,
            ])

            record.dashboard_resumen_general = '\n'.join(
                lineas
            )

    # ============================================================
    # VISUAL
    # ============================================================

    @api.depends(
        'dashboard_estado',
        'dashboard_porcentaje_produccion',
        'puntaje_calidad_real',
        'dashboard_estado_bono',
    )
    def _compute_dashboard_visual(self):
        colores_estado = {
            'sin_datos': '#6C757D',
            'critico': '#DC3545',
            'requiere_revision': '#DC3545',
            'en_observacion': '#FD7E14',
            'estable': '#0D6EFD',
            'destacado': '#198754',
        }

        iconos = {
            'sin_datos': 'fa-question-circle',
            'critico': 'fa-exclamation-circle',
            'requiere_revision': 'fa-exclamation-triangle',
            'en_observacion': 'fa-eye',
            'estable': 'fa-chart-line',
            'destacado': 'fa-trophy',
        }

        clases = {
            'sin_datos': 'o_eval_dashboard_sin_datos',
            'critico': 'o_eval_dashboard_critico',
            'requiere_revision': 'o_eval_dashboard_revision',
            'en_observacion': 'o_eval_dashboard_observacion',
            'estable': 'o_eval_dashboard_estable',
            'destacado': 'o_eval_dashboard_destacado',
        }

        for record in self:
            estado = record.dashboard_estado or 'sin_datos'

            record.dashboard_color_estado = (
                colores_estado.get(
                    estado,
                    '#6C757D',
                )
            )

            record.dashboard_icono_estado = (
                iconos.get(
                    estado,
                    'fa-question-circle',
                )
            )

            record.dashboard_clase_estado = (
                clases.get(
                    estado,
                    'o_eval_dashboard_sin_datos',
                )
            )

            produccion = (
                record.dashboard_porcentaje_produccion or 0.0
            )

            if produccion >= 100:
                record.dashboard_color_produccion = '#198754'
            elif produccion >= 95:
                record.dashboard_color_produccion = '#0D6EFD'
            elif produccion >= 80:
                record.dashboard_color_produccion = '#FD7E14'
            else:
                record.dashboard_color_produccion = '#DC3545'

            calidad = record.puntaje_calidad_real or 0.0

            if calidad >= 90:
                record.dashboard_color_calidad = '#198754'
            elif calidad >= 80:
                record.dashboard_color_calidad = '#0D6EFD'
            elif calidad >= 70:
                record.dashboard_color_calidad = '#FD7E14'
            else:
                record.dashboard_color_calidad = '#DC3545'

            if (record.bono_final or 0.0) > 0:
                record.dashboard_color_bono = '#198754'
            else:
                record.dashboard_color_bono = '#DC3545'

    # ============================================================
    # HELPER HISTÓRICO
    # ============================================================

    def _dashboard_buscar_evaluacion_periodo(
        self,
        fecha_periodo,
    ):
        self.ensure_one()

        if not self.usuario_id or not fecha_periodo:
            return self.env['evaluacion.personal']

        inicio = fecha_periodo.replace(day=1)
        fin = inicio + relativedelta(months=1)

        return self.env['evaluacion.personal'].search(
            [
                ('id', '!=', self.id),
                ('usuario_id', '=', self.usuario_id.id),
                ('fecha', '>=', inicio),
                ('fecha', '<', fin),
            ],
            order='fecha desc, id desc',
            limit=1,
        )

    # ============================================================
    # COMPARACIONES
    # ============================================================

    @api.depends(
        'usuario_id',
        'fecha',
        'porcentaje_produccion_total',
        'puntaje_calidad_real',
        'bono_final',
    )
    def _compute_dashboard_comparaciones(self):
        for record in self:
            record.dashboard_mes_anterior_id = False
            record.dashboard_produccion_mes_anterior = 0.0
            record.dashboard_calidad_mes_anterior = 0.0
            record.dashboard_bono_mes_anterior = 0.0
            record.dashboard_variacion_produccion_mes = 0.0
            record.dashboard_variacion_calidad_mes = 0.0

            record.dashboard_anio_anterior_id = False
            record.dashboard_produccion_anio_anterior = 0.0
            record.dashboard_calidad_anio_anterior = 0.0
            record.dashboard_bono_anio_anterior = 0.0
            record.dashboard_variacion_produccion_anual = 0.0
            record.dashboard_variacion_calidad_anual = 0.0

            record.dashboard_tendencia = 'sin_historial'
            record.dashboard_tendencia_texto = (
                'Sin historial suficiente'
            )

            if not record.usuario_id or not record.fecha:
                continue

            fecha_mes_anterior = (
                record.fecha.replace(day=1)
                - relativedelta(months=1)
            )

            fecha_anio_anterior = (
                record.fecha.replace(day=1)
                - relativedelta(years=1)
            )

            anterior = (
                record._dashboard_buscar_evaluacion_periodo(
                    fecha_mes_anterior
                )
            )

            anual = (
                record._dashboard_buscar_evaluacion_periodo(
                    fecha_anio_anterior
                )
            )

            actual_prod = (
                record.porcentaje_produccion_total or 0.0
            )

            actual_calidad = (
                record.puntaje_calidad_real or 0.0
            )

            if anterior:
                record.dashboard_mes_anterior_id = anterior

                prod_ant = (
                    anterior.porcentaje_produccion_total or 0.0
                )

                calidad_ant = (
                    anterior.puntaje_calidad_real or 0.0
                )

                record.dashboard_produccion_mes_anterior = (
                    prod_ant
                )

                record.dashboard_calidad_mes_anterior = (
                    calidad_ant
                )

                record.dashboard_bono_mes_anterior = (
                    anterior.bono_final or 0.0
                )

                variacion_prod = actual_prod - prod_ant
                variacion_calidad = (
                    actual_calidad - calidad_ant
                )

                record.dashboard_variacion_produccion_mes = (
                    variacion_prod
                )

                record.dashboard_variacion_calidad_mes = (
                    variacion_calidad
                )

                if variacion_prod >= 15:
                    record.dashboard_tendencia = (
                        'mejora_fuerte'
                    )
                    record.dashboard_tendencia_texto = (
                        'Mejora fuerte: +%.2f puntos vs mes anterior'
                        % variacion_prod
                    )

                elif variacion_prod >= 5:
                    record.dashboard_tendencia = 'mejora'
                    record.dashboard_tendencia_texto = (
                        'Mejora: +%.2f puntos vs mes anterior'
                        % variacion_prod
                    )

                elif variacion_prod <= -15:
                    record.dashboard_tendencia = (
                        'baja_fuerte'
                    )
                    record.dashboard_tendencia_texto = (
                        'Caída importante: %.2f puntos vs mes anterior'
                        % variacion_prod
                    )

                elif variacion_prod <= -5:
                    record.dashboard_tendencia = 'baja'
                    record.dashboard_tendencia_texto = (
                        'Retroceso: %.2f puntos vs mes anterior'
                        % variacion_prod
                    )

                else:
                    record.dashboard_tendencia = 'estable'
                    record.dashboard_tendencia_texto = (
                        'Rendimiento estable: %+.2f puntos '
                        'vs mes anterior'
                        % variacion_prod
                    )

            if anual:
                record.dashboard_anio_anterior_id = anual

                prod_anual = (
                    anual.porcentaje_produccion_total or 0.0
                )

                calidad_anual = (
                    anual.puntaje_calidad_real or 0.0
                )

                record.dashboard_produccion_anio_anterior = (
                    prod_anual
                )

                record.dashboard_calidad_anio_anterior = (
                    calidad_anual
                )

                record.dashboard_bono_anio_anterior = (
                    anual.bono_final or 0.0
                )

                record.dashboard_variacion_produccion_anual = (
                    actual_prod - prod_anual
                )

                record.dashboard_variacion_calidad_anual = (
                    actual_calidad - calidad_anual
                )

    # ============================================================
    # HISTORIAL 12 MESES
    # ============================================================

    @api.depends(
        'usuario_id',
        'fecha',
        'porcentaje_produccion_total',
        'puntaje_calidad_real',
        'bono_final',
        'reclamos_procedentes_count',
    )
    def _compute_dashboard_historial(self):
        Evaluacion = self.env['evaluacion.personal']

        for record in self:
            record.dashboard_historial_12_meses = []
            record.dashboard_historial_anual = []

            if not record.usuario_id or not record.fecha:
                continue

            inicio_actual = record.fecha.replace(day=1)
            inicio_historial = (
                inicio_actual
                - relativedelta(months=11)
            )

            fin_historial = (
                inicio_actual
                + relativedelta(months=1)
            )

            evaluaciones = Evaluacion.search(
                [
                    ('usuario_id', '=', record.usuario_id.id),
                    ('fecha', '>=', inicio_historial),
                    ('fecha', '<', fin_historial),
                ],
                order='fecha asc, id asc',
            )

            historial = []

            acumulado_anual = {}

            for evaluacion in evaluaciones:
                fecha = evaluacion.fecha

                if not fecha:
                    continue

                item = {
                    'id': evaluacion.id,
                    'fecha': fields.Date.to_string(fecha),
                    'mes': evaluacion.mes or '',
                    'anio': evaluacion.anio or '',
                    'tipo_operativo': (
                        evaluacion.tipo_operativo or ''
                    ),
                    'produccion': round(
                        evaluacion.porcentaje_produccion_total
                        or 0.0,
                        2,
                    ),
                    'meta_taller': round(
                        evaluacion.meta_taller_ajustada
                        or 0.0,
                        2,
                    ),
                    'meta_servicios': round(
                        evaluacion.meta_servicios_ajustada
                        or 0.0,
                        2,
                    ),
                    'reparaciones': (
                        evaluacion.reparaciones_validas_bono
                        or 0
                    ),
                    'servicios': (
                        evaluacion.tickets_validos_bono
                        or 0
                    ),
                    'calidad': round(
                        evaluacion.puntaje_calidad_real
                        or 0.0,
                        2,
                    ),
                    'asistencia': round(
                        evaluacion.puntaje_asistencia_real
                        or 0.0,
                        2,
                    ),
                    'reclamos': (
                        evaluacion.reclamos_procedentes_count
                        or 0
                    ),
                    'encuestas': (
                        evaluacion.evaluaciones_servicio_count
                        or 0
                    ),
                    'encuestas_requeridas': (
                        evaluacion.evaluaciones_servicio_minimas
                        or 0
                    ),
                    'bono': round(
                        evaluacion.bono_final or 0.0,
                        2,
                    ),
                    'puntaje_bono': round(
                        evaluacion.puntaje_total_bono
                        or 0.0,
                        2,
                    ),
                }

                historial.append(item)

                anio = fecha.year

                if anio not in acumulado_anual:
                    acumulado_anual[anio] = {
                        'anio': anio,
                        'meses': 0,
                        'produccion_total': 0.0,
                        'calidad_total': 0.0,
                        'bono_total': 0.0,
                        'reclamos_total': 0,
                    }

                acumulado_anual[anio]['meses'] += 1

                acumulado_anual[anio][
                    'produccion_total'
                ] += (
                    evaluacion.porcentaje_produccion_total
                    or 0.0
                )

                acumulado_anual[anio][
                    'calidad_total'
                ] += (
                    evaluacion.puntaje_calidad_real
                    or 0.0
                )

                acumulado_anual[anio][
                    'bono_total'
                ] += (
                    evaluacion.bono_final or 0.0
                )

                acumulado_anual[anio][
                    'reclamos_total'
                ] += (
                    evaluacion.reclamos_procedentes_count
                    or 0
                )

            resumen_anual = []

            for anio in sorted(acumulado_anual):
                datos = acumulado_anual[anio]

                meses = datos['meses'] or 1

                resumen_anual.append({
                    'anio': anio,
                    'meses_evaluados': datos['meses'],
                    'produccion_promedio': round(
                        datos['produccion_total']
                        / meses,
                        2,
                    ),
                    'calidad_promedio': round(
                        datos['calidad_total']
                        / meses,
                        2,
                    ),
                    'bono_total': round(
                        datos['bono_total'],
                        2,
                    ),
                    'reclamos_total': (
                        datos['reclamos_total']
                    ),
                })

            record.dashboard_historial_12_meses = historial
            record.dashboard_historial_anual = resumen_anual

    # ============================================================
    # ACCIONES: DETALLE
    # ============================================================

    def action_dashboard_ver_detalle_diario(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Detalle Diario - %s'
            % self.usuario_id.name,
            'res_model': 'evaluacion.personal.detalle.diario',
            'view_mode': 'list,form,pivot,graph',
            'domain': [
                ('evaluacion_id', '=', self.id),
            ],
            'context': {
                'create': False,
                'delete': False,
            },
        }

    # ============================================================
    # ACCIONES: RECLAMOS
    # ============================================================

    def action_dashboard_ver_reclamos(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Reclamos - %s'
            % self.usuario_id.name,
            'res_model': 'taller.incidencia',
            'view_mode': 'list,form',
            'domain': [
                ('id', 'in', self.incidencia_ids.ids),
            ],
            'context': {
                'create': False,
            },
        }

    # ============================================================
    # ACCIONES: ENCUESTAS RESPONDIDAS
    # ============================================================

    def action_dashboard_ver_encuestas_respondidas(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Encuestas respondidas - %s'
            % self.usuario_id.name,
            'res_model': 'client.service.evaluation',
            'view_mode': 'list,form',
            'domain': [
                (
                    'id',
                    'in',
                    self.evaluacion_servicio_ids.ids,
                ),
            ],
            'context': {
                'create': False,
            },
        }

    # ============================================================
    # ACCIONES: TODAS LAS ENCUESTAS
    # ============================================================

    def action_dashboard_ver_todas_encuestas(self):
        self.ensure_one()

        encuestas = self._dashboard_get_encuestas_periodo()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Encuestas del periodo - %s'
            % self.usuario_id.name,
            'res_model': 'client.service.evaluation',
            'view_mode': 'list,form',
            'domain': [
                ('id', 'in', encuestas.ids),
            ],
            'context': {
                'create': False,
            },
        }

    # ============================================================
    # ACCIONES: ENCUESTAS NO RESPONDIDAS
    # ============================================================

    def action_dashboard_ver_encuestas_no_respondidas(self):
        self.ensure_one()

        encuestas = self._dashboard_get_encuestas_periodo()

        pendientes = encuestas.filtered(
            lambda ev:
                ev.state != 'completed'
                or not ev.response_date
        )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Encuestas no respondidas - %s'
            % self.usuario_id.name,
            'res_model': 'client.service.evaluation',
            'view_mode': 'list,form',
            'domain': [
                ('id', 'in', pendientes.ids),
            ],
            'context': {
                'create': False,
            },
        }

    # ============================================================
    # ACCIONES: HISTORIAL DEL TÉCNICO
    # ============================================================

    def action_dashboard_ver_historial(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Historial - %s'
            % self.usuario_id.name,
            'res_model': 'evaluacion.personal',
            'view_mode': 'list,graph,pivot,form',
            'domain': [
                ('usuario_id', '=', self.usuario_id.id),
            ],
            'context': {
                'create': False,
                'search_default_usuario_id': self.usuario_id.id,
            },
        }

    # ============================================================
    # ACCIONES: COMPARAR MES ANTERIOR
    # ============================================================

    def action_dashboard_comparar_mes_anterior(self):
        self.ensure_one()

        ids = [self.id]

        if self.dashboard_mes_anterior_id:
            ids.append(
                self.dashboard_mes_anterior_id.id
            )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Comparación mensual - %s'
            % self.usuario_id.name,
            'res_model': 'evaluacion.personal',
            'view_mode': 'list,graph,pivot,form',
            'domain': [
                ('id', 'in', ids),
            ],
            'context': {
                'create': False,
            },
        }

    # ============================================================
    # ACCIONES: COMPARAR AÑO ANTERIOR
    # ============================================================

    def action_dashboard_comparar_anio_anterior(self):
        self.ensure_one()

        ids = [self.id]

        if self.dashboard_anio_anterior_id:
            ids.append(
                self.dashboard_anio_anterior_id.id
            )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Comparación anual - %s'
            % self.usuario_id.name,
            'res_model': 'evaluacion.personal',
            'view_mode': 'list,graph,pivot,form',
            'domain': [
                ('id', 'in', ids),
            ],
            'context': {
                'create': False,
            },
        }

    # ============================================================
    # ACTUALIZAR DASHBOARD
    # ============================================================

    def action_actualizar_dashboard(self):
        """
        Usa el proceso oficial de recalculo de la evaluación y después
        actualiza la información visual.

        La lógica del bono continúa perteneciendo a evaluacion.personal.
        """
        for record in self:
            if hasattr(record, 'action_recalcular_bono'):
                record.action_recalcular_bono()

            if hasattr(record, 'action_generar_detalle_diario'):
                record.action_generar_detalle_diario()

            record._compute_dashboard_identificacion()
            record._compute_dashboard_produccion()
            record._compute_dashboard_encuestas()
            record._compute_dashboard_calidad()
            record._compute_dashboard_asistencia()
            record._compute_dashboard_disponibilidad()
            record._compute_dashboard_bono()
            record._compute_dashboard_estado()
            record._compute_dashboard_visual()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Dashboard actualizado',
                'message': (
                    'Se actualizaron producción, calidad, encuestas, '
                    'reclamos, asistencia, bono e indicadores '
                    'gerenciales.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }


# ================================================================
# DETALLE DIARIO PARA DASHBOARD
# ================================================================


class EvaluacionPersonalDetalleDiarioDashboard(models.Model):
    """
    Extensión visual del detalle diario.

    IMPORTANTE:
    El objetivo diario histórico existente en
    evaluacion.personal.detalle.diario NO se utiliza para decidir
    el bono mensual ni la productividad gerencial principal.

    El dashboard mensual utiliza las metas ajustadas reales.
    """

    _inherit = 'evaluacion.personal.detalle.diario'

    dashboard_color_estado_dia = fields.Char(
        string='Color día',
        compute='_compute_dashboard_dia_visual',
        store=True,
    )

    dashboard_icono_estado_dia = fields.Char(
        string='Icono día',
        compute='_compute_dashboard_dia_visual',
        store=True,
    )

    dashboard_resumen_dia = fields.Char(
        string='Resumen día',
        compute='_compute_dashboard_dia_texto',
        store=True,
    )

    dashboard_actividad_dia = fields.Char(
        string='Actividad del día',
        compute='_compute_dashboard_dia_texto',
        store=True,
    )

    dashboard_alerta_dia = fields.Char(
        string='Alerta día',
        compute='_compute_dashboard_dia_texto',
        store=True,
    )

    # ============================================================
    # VISUAL DÍA
    # ============================================================

    @api.depends(
        'es_dia_laboral',
        'total_trabajos',
        'cantidad_reparaciones',
        'cantidad_tickets',
    )
    def _compute_dashboard_dia_visual(self):
        for record in self:
            if not record.es_dia_laboral:
                color = '#6C757D'
                icono = 'fa-calendar-times-o'

            elif not record.total_trabajos:
                color = '#DC3545'
                icono = 'fa-minus-circle'

            elif record.total_trabajos >= 7:
                color = '#198754'
                icono = 'fa-star'

            elif record.total_trabajos >= 4:
                color = '#0D6EFD'
                icono = 'fa-check-circle'

            else:
                color = '#FD7E14'
                icono = 'fa-exclamation-triangle'

            record.dashboard_color_estado_dia = color
            record.dashboard_icono_estado_dia = icono

    # ============================================================
    # TEXTO DÍA
    # ============================================================

    @api.depends(
        'fecha',
        'dia_semana',
        'es_dia_laboral',
        'cantidad_reparaciones',
        'cantidad_tickets',
        'total_trabajos',
        'clientes_atendidos',
        'modelos_trabajados',
    )
    def _compute_dashboard_dia_texto(self):
        for record in self:
            fecha_texto = ''

            if record.fecha:
                fecha_texto = record.fecha.strftime(
                    '%d/%m/%Y'
                )

            record.dashboard_resumen_dia = (
                '%s %s - %s trabajo(s)'
                % (
                    record.dia_semana or '',
                    fecha_texto,
                    record.total_trabajos or 0,
                )
            )

            record.dashboard_actividad_dia = (
                '%s reparación(es) / %s servicio(s)'
                % (
                    record.cantidad_reparaciones or 0,
                    record.cantidad_tickets or 0,
                )
            )

            if not record.es_dia_laboral:
                record.dashboard_alerta_dia = (
                    'Día no laboral'
                )

            elif not record.total_trabajos:
                record.dashboard_alerta_dia = (
                    'Sin actividad registrada'
                )

            else:
                record.dashboard_alerta_dia = (
                    'Actividad registrada'
                )