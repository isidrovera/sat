# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class AsesoraAsignacionHistorial(models.Model):
    _name = 'asesora.asignacion.historial'
    _description = 'Historial de Asignaciones de Máquinas a Asesoras'
    _order = 'fecha_accion desc'
    _rec_name = 'display_name'

    # ============================================
    # CAMPOS PRINCIPALES
    # ============================================
    
    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
        store=True
    )
    
    maquina_id = fields.Many2one(
        'sat.sat',
        string='Máquina',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    serie_maquina = fields.Char(
        related='maquina_id.serie_id',
        string='Serie',
        store=True,
        readonly=True
    )
    
    modelo_maquina = fields.Char(
        related='maquina_id.name.name',
        string='Modelo',
        store=True,
        readonly=True
    )
    
    # ============================================
    # RELACIONES CON ASESORAS Y CLIENTES
    # ============================================
    
    asesora_id = fields.Many2one(
        'res.users',
        string='Asesora que realizó la acción',
        required=True,
        index=True
    )
    
    asesora_anterior_id = fields.Many2one(
        'res.users',
        string='Asesora anterior',
        help='En caso de transferencia de cliente'
    )
    
    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        index=True
    )
    
    cliente_anterior_id = fields.Many2one(
        'res.partner',
        string='Cliente anterior'
    )
    
    # ============================================
    # DATOS DE LA ACCIÓN
    # ============================================
    
    fecha_accion = fields.Datetime(
        string='Fecha y hora de acción',
        required=True,
        default=fields.Datetime.now,
        index=True
    )
    
    tipo_accion = fields.Selection([
        # Pre-descarga
        ('pre_asignacion', 'Pre-asignación (antes de descarga)'),
        ('ajuste_pre_descarga', 'Ajuste pre-descarga'),
        
        # Post-descarga
        ('confirmacion_descarga', 'Confirmación de descarga'),
        ('cambio_cliente', 'Cambio de cliente'),
        ('renovacion_artificial', '⚠️ Renovación artificial detectada'),
        
        # Liberaciones
        ('liberacion_automatica', '🔴 Liberación automática (plazo vencido)'),
        ('liberacion_manual', 'Liberación manual (gerencia)'),
        ('liberacion_por_cliente', 'Cliente removido por asesora'),
        
        # Transferencias
        ('transferencia_asesora', '🔄 Transferencia entre asesoras'),
        ('correccion_asesora', 'Corrección de asesora del cliente'),
        
        # Éxito
        ('venta_exitosa', '✅ Venta exitosa'),
    ], string='Tipo de acción', required=True, index=True)
    
    # ============================================
    # CONTEXTO DE LA ACCIÓN
    # ============================================
    
    dias_transcurridos = fields.Integer(
        string='Días hábiles transcurridos',
        help='Días hábiles desde la descarga al momento de esta acción'
    )
    
    estado_plazo_al_cambio = fields.Selection([
        ('pre_descarga', 'Pre-descarga'),
        ('en_tolerancia', 'En tolerancia (0-5 días)'),
        ('proxima_vencer', 'Próxima a vencer (6-7 días)'),
        ('vencida', 'Vencida (8+ días)'),
        ('vendida', 'Vendida'),
    ], string='Estado del plazo en ese momento')
    
    fecha_descarga_contexto = fields.Date(
        string='Fecha de descarga (contexto)',
        help='Fecha de descarga del contenedor en ese momento'
    )
    
    # ============================================
    # DATOS ADICIONALES
    # ============================================
    
    motivo_cambio = fields.Text(
        string='Motivo/Justificación',
        help='Justificación proporcionada por la asesora o sistema'
    )
    
    aprobado_por_id = fields.Many2one(
        'res.users',
        string='Aprobado por',
        help='Usuario que aprobó la acción (si aplica)'
    )
    
    es_renovacion_sospechosa = fields.Boolean(
        string='¿Renovación sospechosa?',
        default=False,
        help='Marcado si se detectó patrón de abuso'
    )
    
    intentos_cambio_acumulados = fields.Integer(
        string='Intentos de cambio acumulados',
        help='Cantidad de cambios de cliente al momento de esta acción'
    )
    
    # ============================================
    # CAMPOS CALCULADOS
    # ============================================
    
    @api.depends('maquina_id', 'tipo_accion', 'fecha_accion')
    def _compute_display_name(self):
        for record in self:
            if record.maquina_id and record.tipo_accion:
                tipo_dict = dict(record._fields['tipo_accion'].selection)
                tipo_texto = tipo_dict.get(record.tipo_accion, record.tipo_accion)
                fecha_str = record.fecha_accion.strftime('%d/%m/%Y %H:%M') if record.fecha_accion else ''
                record.display_name = f"{record.maquina_id.serie_id} - {tipo_texto} ({fecha_str})"
            else:
                record.display_name = 'Historial sin datos'
    
    # ============================================
    # MÉTODOS ESTÁTICOS DE CREACIÓN
    # ============================================
    
    @api.model
    def registrar_pre_asignacion(self, maquina, asesora, cliente):
        """Registra cuando una asesora asigna un cliente ANTES de la descarga"""
        return self.create({
            'maquina_id': maquina.id,
            'asesora_id': asesora.id,
            'cliente_id': cliente.id,
            'tipo_accion': 'pre_asignacion',
            'estado_plazo_al_cambio': 'pre_descarga',
            'dias_transcurridos': 0,
            'motivo_cambio': 'Asignación inicial antes de descarga del contenedor'
        })
    
    @api.model
    def registrar_confirmacion_descarga(self, maquina):
        """Registra cuando se confirma la descarga del contenedor"""
        return self.create({
            'maquina_id': maquina.id,
            'asesora_id': self.env.user.id,
            'cliente_id': maquina.cliente_id.id if maquina.cliente_id else False,
            'tipo_accion': 'confirmacion_descarga',
            'estado_plazo_al_cambio': 'en_tolerancia',
            'dias_transcurridos': 0,
            'fecha_descarga_contexto': maquina.fecha_descarga_contenedor,
            'motivo_cambio': 'Inicio del contador de 5 días hábiles'
        })
    
    @api.model
    def registrar_cambio_cliente(self, maquina, cliente_anterior, cliente_nuevo, 
                                  dias_transcurridos, es_sospechoso=False, 
                                  intentos_acumulados=0, motivo=''):
        """Registra cuando una asesora cambia el cliente de una máquina"""
        return self.create({
            'maquina_id': maquina.id,
            'asesora_id': self.env.user.id,
            'cliente_id': cliente_nuevo.id if cliente_nuevo else False,
            'cliente_anterior_id': cliente_anterior.id if cliente_anterior else False,
            'tipo_accion': 'renovacion_artificial' if es_sospechoso else 'cambio_cliente',
            'estado_plazo_al_cambio': maquina.estado_plazo_venta,
            'dias_transcurridos': dias_transcurridos,
            'fecha_descarga_contexto': maquina.fecha_descarga_contenedor,
            'es_renovacion_sospechosa': es_sospechoso,
            'intentos_cambio_acumulados': intentos_acumulados,
            'motivo_cambio': motivo or 'Cambio de cliente'
        })
    
    @api.model
    def registrar_transferencia_asesora(self, maquina, asesora_anterior, asesora_nueva, 
                                       cliente, motivo=''):
        """Registra cuando un cliente (y su máquina) se transfiere entre asesoras"""
        return self.create({
            'maquina_id': maquina.id,
            'asesora_id': asesora_nueva.id,
            'asesora_anterior_id': asesora_anterior.id,
            'cliente_id': cliente.id,
            'tipo_accion': 'transferencia_asesora',
            'estado_plazo_al_cambio': maquina.estado_plazo_venta,
            'dias_transcurridos': maquina.dias_habiles_transcurridos,
            'fecha_descarga_contexto': maquina.fecha_descarga_contenedor,
            'motivo_cambio': motivo or 'Transferencia de cliente entre asesoras'
        })
    
    @api.model
    def registrar_liberacion_automatica(self, maquina, dias_transcurridos):
        """Registra cuando el sistema libera automáticamente por plazo vencido"""
        return self.create({
            'maquina_id': maquina.id,
            'asesora_id': self.env.ref('base.user_admin').id,  # Usuario sistema
            'cliente_anterior_id': maquina.cliente_id.id if maquina.cliente_id else False,
            'tipo_accion': 'liberacion_automatica',
            'estado_plazo_al_cambio': 'vencida',
            'dias_transcurridos': dias_transcurridos,
            'fecha_descarga_contexto': maquina.fecha_descarga_contenedor,
            'motivo_cambio': f'Liberación automática por exceder plazo de {dias_transcurridos} días'
        })
    
    @api.model
    def registrar_venta_exitosa(self, maquina, dias_transcurridos):
        """Registra cuando una máquina se vende exitosamente"""
        return self.create({
            'maquina_id': maquina.id,
            'asesora_id': self.env.user.id,
            'cliente_id': maquina.cliente_id.id if maquina.cliente_id else False,
            'tipo_accion': 'venta_exitosa',
            'estado_plazo_al_cambio': 'vendida',
            'dias_transcurridos': dias_transcurridos,
            'fecha_descarga_contexto': maquina.fecha_descarga_contenedor,
            'motivo_cambio': f'Venta exitosa en {dias_transcurridos} días hábiles'
        })