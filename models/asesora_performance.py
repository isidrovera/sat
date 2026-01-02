# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class AsesoraPerformance(models.Model):
    _name = 'asesora.performance'
    _description = 'Performance y Scoring de Asesoras'
    _rec_name = 'asesora_id'

    # ============================================
    # CAMPO PRINCIPAL
    # ============================================
    
    asesora_id = fields.Many2one(
        'res.users',
        string='Asesora',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    # ============================================
    # MÉTRICAS DE ASIGNACIONES
    # ============================================
    
    total_asignaciones = fields.Integer(
        string='Total asignaciones',
        compute='_compute_metricas',
        store=True,
        help='Total de máquinas asignadas históricamente'
    )
    
    total_ventas = fields.Integer(
        string='Total ventas',
        compute='_compute_metricas',
        store=True,
        help='Total de máquinas vendidas exitosamente'
    )
    
    total_liberaciones_forzadas = fields.Integer(
        string='Liberaciones forzadas',
        compute='_compute_metricas',
        store=True,
        help='Máquinas liberadas automáticamente por plazo vencido'
    )
    
    total_renovaciones_artificiales = fields.Integer(
        string='Renovaciones artificiales',
        compute='_compute_metricas',
        store=True,
        help='Intentos detectados de renovación para no ceder máquina'
    )
    
    # ============================================
    # MÉTRICAS DE TIEMPO
    # ============================================
    
    promedio_dias_venta = fields.Float(
        string='Promedio días venta',
        compute='_compute_metricas',
        store=True,
        digits=(5, 1),
        help='Promedio de días hábiles para cerrar ventas'
    )
    
    mejor_tiempo_venta = fields.Integer(
        string='Mejor tiempo (días)',
        compute='_compute_metricas',
        store=True,
        help='Venta más rápida en días hábiles'
    )
    
    peor_tiempo_venta = fields.Integer(
        string='Peor tiempo (días)',
        compute='_compute_metricas',
        store=True,
        help='Venta más lenta en días hábiles'
    )
    
    # ============================================
    # ESTADO ACTUAL
    # ============================================
    
    maquinas_actuales = fields.Integer(
        string='Máquinas en poder',
        compute='_compute_maquinas_actuales',
        help='Máquinas actualmente asignadas'
    )
    
    maquinas_en_plazo = fields.Integer(
        string='En plazo (0-5 días)',
        compute='_compute_maquinas_actuales'
    )
    
    maquinas_proximas_vencer = fields.Integer(
        string='Próximas vencer (6-7 días)',
        compute='_compute_maquinas_actuales'
    )
    
    maquinas_vencidas = fields.Integer(
        string='Vencidas (8+ días)',
        compute='_compute_maquinas_actuales'
    )
    
    # ============================================
    # LÍMITES Y CONFIGURACIÓN
    # ============================================
    
    limite_maquinas = fields.Integer(
        string='Límite de máquinas',
        default=10,
        help='Máximo de máquinas que puede tener asignadas simultáneamente'
    )
    
    dias_extension_otorgados = fields.Integer(
        string='Días de extensión otorgados',
        default=0,
        help='Días adicionales otorgados por gerencia'
    )
    
    # ============================================
    # SCORING
    # ============================================
    
    score_asignacion = fields.Float(
        string='Score',
        compute='_compute_score',
        store=True,
        digits=(5, 1),
        help='Score de 0 a 100 basado en rendimiento'
    )
    
    tasa_conversion = fields.Float(
        string='Tasa de conversión (%)',
        compute='_compute_metricas',
        store=True,
        digits=(5, 1),
        help='Porcentaje de ventas exitosas vs asignaciones'
    )
    
    # ============================================
    # ALERTAS Y ESTADO
    # ============================================
    
    estado_performance = fields.Selection([
        ('excelente', '🟢 Excelente (90-100)'),
        ('bueno', '🟡 Bueno (70-89)'),
        ('regular', '🟠 Regular (50-69)'),
        ('bajo', '🔴 Bajo (< 50)'),
    ], string='Estado', compute='_compute_score', store=True)
    
    requiere_revision = fields.Boolean(
        string='Requiere revisión gerencial',
        compute='_compute_score',
        store=True,
        help='Se activa si score < 50 por 2 semanas consecutivas'
    )
    
    # ============================================
    # PENALIZACIONES
    # ============================================
    
    penalizacion_ids = fields.One2many(
        'asesora.penalizacion',
        'asesora_performance_id',
        string='Historial de penalizaciones'
    )
    
    total_penalizaciones = fields.Integer(
        string='Total penalizaciones',
        compute='_compute_penalizaciones',
        store=True
    )
    
    # ============================================
    # MÉTODOS COMPUTE
    # ============================================
    
    @api.depends('asesora_id')
    def _compute_metricas(self):
        """Calcula todas las métricas históricas de la asesora"""
        for record in self:
            if not record.asesora_id:
                continue
            
            Historial = self.env['asesora.asignacion.historial']
            
            # Total de asignaciones (pre + post descarga)
            asignaciones = Historial.search([
                ('asesora_id', '=', record.asesora_id.id),
                ('tipo_accion', 'in', ['pre_asignacion', 'confirmacion_descarga'])
            ])
            record.total_asignaciones = len(asignaciones)
            
            # Total de ventas exitosas
            ventas = Historial.search([
                ('asesora_id', '=', record.asesora_id.id),
                ('tipo_accion', '=', 'venta_exitosa')
            ])
            record.total_ventas = len(ventas)
            
            # Liberaciones forzadas
            liberaciones = Historial.search([
                ('asesora_id', '=', record.asesora_id.id),
                ('tipo_accion', '=', 'liberacion_automatica')
            ])
            record.total_liberaciones_forzadas = len(liberaciones)
            
            # Renovaciones artificiales
            renovaciones = Historial.search([
                ('asesora_id', '=', record.asesora_id.id),
                ('tipo_accion', '=', 'renovacion_artificial')
            ])
            record.total_renovaciones_artificiales = len(renovaciones)
            
            # Tasa de conversión
            if record.total_asignaciones > 0:
                record.tasa_conversion = (record.total_ventas / record.total_asignaciones) * 100
            else:
                record.tasa_conversion = 0.0
            
            # Promedios de tiempo
            if ventas:
                dias_list = [v.dias_transcurridos for v in ventas if v.dias_transcurridos]
                if dias_list:
                    record.promedio_dias_venta = sum(dias_list) / len(dias_list)
                    record.mejor_tiempo_venta = min(dias_list)
                    record.peor_tiempo_venta = max(dias_list)
                else:
                    record.promedio_dias_venta = 0.0
                    record.mejor_tiempo_venta = 0
                    record.peor_tiempo_venta = 0
            else:
                record.promedio_dias_venta = 0.0
                record.mejor_tiempo_venta = 0
                record.peor_tiempo_venta = 0
    
    @api.depends('asesora_id')
    def _compute_maquinas_actuales(self):
        """Calcula máquinas actualmente en poder de la asesora"""
        for record in self:
            if not record.asesora_id:
                continue
            
            # Buscar partner asociado al usuario asesora
            asesora_partner = record.asesora_id.partner_id
            
            # Máquinas donde el cliente tiene a esta asesora
            SatSat = self.env['sat.sat']
            
            maquinas_actuales = SatSat.search([
                ('cliente_id.asesora_id', '=', asesora_partner.id),
                ('disponibilidad_id', '=', 'separada'),
                ('estado_ventas_id', '!=', 'entregada'),
                ('fecha_descarga_contenedor', '!=', False)  # Solo post-descarga
            ])
            
            record.maquinas_actuales = len(maquinas_actuales)
            
            # Clasificar por estado de plazo
            record.maquinas_en_plazo = len(maquinas_actuales.filtered(
                lambda m: m.estado_plazo_venta == 'en_tolerancia'
            ))
            record.maquinas_proximas_vencer = len(maquinas_actuales.filtered(
                lambda m: m.estado_plazo_venta == 'proxima_vencer'
            ))
            record.maquinas_vencidas = len(maquinas_actuales.filtered(
                lambda m: m.estado_plazo_venta == 'vencida'
            ))
    
    @api.depends('total_asignaciones', 'total_ventas', 'total_liberaciones_forzadas',
                 'total_renovaciones_artificiales', 'promedio_dias_venta', 'tasa_conversion')
    def _compute_score(self):
        """Calcula el score de performance de la asesora"""
        for record in self:
            score = 100.0
            
            # Penalización por liberaciones forzadas (-10 puntos c/u)
            score -= (record.total_liberaciones_forzadas * 10)
            
            # Penalización por renovaciones artificiales (-5 puntos c/u)
            score -= (record.total_renovaciones_artificiales * 5)
            
            # Bonus por tasa de conversión (+20 puntos máximo)
            score += (record.tasa_conversion / 100) * 20
            
            # Penalización por días promedio > 3
            if record.promedio_dias_venta > 3:
                exceso_dias = record.promedio_dias_venta - 3
                score -= (exceso_dias * 2)
            
            # Bonus si promedio < 3 días
            elif record.promedio_dias_venta > 0 and record.promedio_dias_venta < 3:
                bonus_rapidez = (3 - record.promedio_dias_venta) * 3
                score += bonus_rapidez
            
            # Limitar score entre 0 y 100
            score = max(0.0, min(100.0, score))
            
            record.score_asignacion = score
            
            # Asignar estado
            if score >= 90:
                record.estado_performance = 'excelente'
            elif score >= 70:
                record.estado_performance = 'bueno'
            elif score >= 50:
                record.estado_performance = 'regular'
            else:
                record.estado_performance = 'bajo'
            
            # Requiere revisión si score < 50
            record.requiere_revision = score < 50
    
    @api.depends('penalizacion_ids')
    def _compute_penalizaciones(self):
        for record in self:
            record.total_penalizaciones = len(record.penalizacion_ids)
    
    # ============================================
    # MÉTODOS PÚBLICOS
    # ============================================
    
    def aplicar_penalizacion(self, tipo, puntos, motivo):
        """Aplica una penalización a la asesora"""
        self.ensure_one()
        Penalizacion = self.env['asesora.penalizacion']
        return Penalizacion.create({
            'asesora_performance_id': self.id,
            'tipo': tipo,
            'puntos': puntos,
            'motivo': motivo,
            'fecha': fields.Datetime.now()
        })
    
    def recalcular_metricas(self):
        """Fuerza recálculo de todas las métricas"""
        self._compute_metricas()
        self._compute_maquinas_actuales()
        self._compute_score()
    
    @api.model
    def get_or_create_performance(self, asesora_id):
        """Obtiene o crea el registro de performance para una asesora"""
        performance = self.search([('asesora_id', '=', asesora_id)], limit=1)
        if not performance:
            performance = self.create({'asesora_id': asesora_id})
        return performance


class AsesoraPenalizacion(models.Model):
    _name = 'asesora.penalizacion'
    _description = 'Penalizaciones de Asesoras'
    _order = 'fecha desc'

    asesora_performance_id = fields.Many2one(
        'asesora.performance',
        string='Performance',
        required=True,
        ondelete='cascade'
    )
    
    fecha = fields.Datetime(
        string='Fecha',
        required=True,
        default=fields.Datetime.now
    )
    
    tipo = fields.Selection([
        ('liberacion_automatica', 'Liberación automática'),
        ('renovacion_artificial', 'Renovación artificial'),
        ('incumplimiento_meta', 'Incumplimiento de meta'),
        ('revision_gerencial', 'Revisión gerencial'),
    ], string='Tipo', required=True)
    
    puntos = fields.Integer(
        string='Puntos descontados',
        required=True
    )
    
    motivo = fields.Text(
        string='Motivo',
        required=True
    )