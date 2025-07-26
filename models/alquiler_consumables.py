import calendar
import requests
import uuid
from urllib.parse import urlencode
from odoo.exceptions import UserError, ValidationError
import io
import qrcode
import re
import base64
from io import BytesIO
import xlwt
from odoo import _, models, fields, api
from dateutil.relativedelta import relativedelta
from datetime import datetime
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)

class UnidadAlquiler(models.Model):
    _inherit = 'alquiler'
    
    estado_stock_toner = fields.Selection([
        ('critico', 'Crítico'),
        ('bajo', 'Bajo'),
        ('normal', 'Normal'),
        ('alto', 'Alto')
    ], string='Estado Stock Tóner', default='normal',
       compute='_compute_estado_stock_toner',
       help='Estado general del stock de tóner')

    # Stock físico que tiene el cliente guardado
    stock_cliente_toner_black = fields.Integer(
        string='Stock Cliente - Tóner Negro',
        default=0,
        tracking=True,
        help='Cantidad de tóner negro que tiene el cliente en stock (sin instalar)'
    )

    stock_cliente_toner_cyan = fields.Integer(
        string='Stock Cliente - Tóner Cian',
        default=0,
        tracking=True,
        help='Cantidad de tóner cian que tiene el cliente en stock (sin instalar)'
    )

    stock_cliente_toner_magenta = fields.Integer(
        string='Stock Cliente - Tóner Magenta',
        default=0,
        tracking=True,
        help='Cantidad de tóner magenta que tiene el cliente en stock (sin instalar)'
    )

    stock_cliente_toner_yellow = fields.Integer(
        string='Stock Cliente - Tóner Amarillo',
        default=0,
        tracking=True,
        help='Cantidad de tóner amarillo que tiene el cliente en stock (sin instalar)'
    )

    # Tóner instalado actualmente en la máquina
    toner_black_instalado = fields.Boolean(
        string='Tóner Negro Instalado',
        default=True,
        tracking=True,
        help='¿Hay tóner negro instalado en la máquina?'
    )

    toner_cyan_instalado = fields.Boolean(
        string='Tóner Cian Instalado',
        default=True,
        tracking=True,
        help='¿Hay tóner cian instalado en la máquina?'
    )

    toner_magenta_instalado = fields.Boolean(
        string='Tóner Magenta Instalado',
        default=True,
        tracking=True,
        help='¿Hay tóner magenta instalado en la máquina?'
    )

    toner_yellow_instalado = fields.Boolean(
        string='Tóner Amarillo Instalado',
        default=True,
        tracking=True,
        help='¿Hay tóner amarillo instalado en la máquina?'
    )

    # Fechas de instalación
    fecha_instalacion_toner_black = fields.Date(
        string='Fecha Instalación Tóner Negro',
        tracking=True,
        help='Cuándo se instaló el tóner negro actual'
    )

    fecha_instalacion_toner_cyan = fields.Date(
        string='Fecha Instalación Tóner Cian',
        tracking=True,
        help='Cuándo se instaló el tóner cian actual'
    )

    fecha_instalacion_toner_magenta = fields.Date(
        string='Fecha Instalación Tóner Magenta',
        tracking=True,
        help='Cuándo se instaló el tóner magenta actual'
    )

    fecha_instalacion_toner_yellow = fields.Date(
        string='Fecha Instalación Tóner Amarillo',
        tracking=True,
        help='Cuándo se instaló el tóner amarillo actual'
    )

    # Contadores al momento de instalación
    contador_instalacion_toner_black = fields.Integer(
        string='Contador al Instalar Tóner Negro',
        default=0,
        tracking=True,
        help='Lectura del contador cuando se instaló el tóner negro'
    )

    contador_instalacion_toner_cyan = fields.Integer(
        string='Contador al Instalar Tóner Cian',
        default=0,
        tracking=True,
        help='Lectura del contador color cuando se instaló el tóner cian'
    )

    contador_instalacion_toner_magenta = fields.Integer(
        string='Contador al Instalar Tóner Magenta',
        default=0,
        tracking=True,
        help='Lectura del contador color cuando se instaló el tóner magenta'
    )

    contador_instalacion_toner_yellow = fields.Integer(
        string='Contador al Instalar Tóner Amarillo',
        default=0,
        tracking=True,
        help='Lectura del contador color cuando se instaló el tóner amarillo'
    )

    # Contadores actuales
    contador_actual_black = fields.Integer(
        string='Contador Actual B/N',
        default=0,
        tracking=True,
        help='Última lectura del contador blanco y negro'
    )

    contador_actual_color = fields.Integer(
        string='Contador Actual Color',
        default=0,
        tracking=True,
        help='Última lectura del contador color'
    )

    fecha_ultima_lectura = fields.Datetime(
        string='Fecha Última Lectura',
        tracking=True,
        help='Cuándo se tomó la última lectura de contadores'
    )

    # Campos calculados de páginas usadas
    paginas_usadas_toner_black = fields.Integer(
        string='Páginas Usadas Tóner Negro',
        compute='_compute_paginas_usadas_toner',
        store=True,
        help='Páginas que ha impreso el tóner negro instalado'
    )

    paginas_usadas_toner_cyan = fields.Integer(
        string='Páginas Usadas Tóner Cian',
        compute='_compute_paginas_usadas_toner',
        store=True,
        help='Páginas que ha impreso el tóner cian instalado'
    )

    paginas_usadas_toner_magenta = fields.Integer(
        string='Páginas Usadas Tóner Magenta',
        compute='_compute_paginas_usadas_toner',
        store=True,
        help='Páginas que ha impreso el tóner magenta instalado'
    )

    paginas_usadas_toner_yellow = fields.Integer(
        string='Páginas Usadas Tóner Amarillo',
        compute='_compute_paginas_usadas_toner',
        store=True,
        help='Páginas que ha impreso el tóner amarillo instalado'
    )

    # Páginas restantes
    paginas_restantes_toner_black = fields.Integer(
        string='Páginas Restantes Tóner Negro',
        compute='_compute_paginas_restantes_toner',
        help='Páginas estimadas que le quedan al tóner negro instalado'
    )

    paginas_restantes_toner_cyan = fields.Integer(
        string='Páginas Restantes Tóner Cian',
        compute='_compute_paginas_restantes_toner',
        help='Páginas estimadas que le quedan al tóner cian instalado'
    )

    paginas_restantes_toner_magenta = fields.Integer(
        string='Páginas Restantes Tóner Magenta',
        compute='_compute_paginas_restantes_toner',
        help='Páginas estimadas que le quedan al tóner magenta instalado'
    )

    paginas_restantes_toner_yellow = fields.Integer(
        string='Páginas Restantes Tóner Amarillo',
        compute='_compute_paginas_restantes_toner',
        help='Páginas estimadas que le quedan al tóner amarillo instalado'
    )

    # Nivel de tóner (porcentaje)
    nivel_toner_black = fields.Float(
        string='Nivel Tóner Negro (%)',
        compute='_compute_nivel_toner',
        help='Porcentaje restante del tóner negro instalado'
    )

    nivel_toner_cyan = fields.Float(
        string='Nivel Tóner Cian (%)',
        compute='_compute_nivel_toner',
        help='Porcentaje restante del tóner cian instalado'
    )

    nivel_toner_magenta = fields.Float(
        string='Nivel Tóner Magenta (%)',
        compute='_compute_nivel_toner',
        help='Porcentaje restante del tóner magenta instalado'
    )

    nivel_toner_yellow = fields.Float(
        string='Nivel Tóner Amarillo (%)',
        compute='_compute_nivel_toner',
        help='Porcentaje restante del tóner amarillo instalado'
    )

    # Stock total disponible (instalado + en stock)
    stock_total_toner_black = fields.Integer(
        string='Stock Total Tóner Negro',
        compute='_compute_stock_total_toner',
        help='Total de tóner negro disponible (instalado + en stock)'
    )

    stock_total_toner_cyan = fields.Integer(
        string='Stock Total Tóner Cian',
        compute='_compute_stock_total_toner',
        help='Total de tóner cian disponible (instalado + en stock)'
    )

    stock_total_toner_magenta = fields.Integer(
        string='Stock Total Tóner Magenta',
        compute='_compute_stock_total_toner',
        help='Total de tóner magenta disponible (instalado + en stock)'
    )

    stock_total_toner_yellow = fields.Integer(
        string='Stock Total Tóner Amarillo',
        compute='_compute_stock_total_toner',
        help='Total de tóner amarillo disponible (instalado + en stock)'
    )

    # Contadores para reportes y entregas de tóner
    toner_reports_count = fields.Integer(
        string='Reportes de Tóner',
        compute='_compute_toner_counts'
    )

    toner_deliveries_count = fields.Integer(
        string='Entregas de Tóner',
        compute='_compute_toner_counts'
    )

    # ==========================================
    # MÉTODOS COMPUTE PARA TÓNER
    # ==========================================

    @api.depends('contador_actual_black', 'contador_actual_color', 
                'contador_instalacion_toner_black', 'contador_instalacion_toner_cyan',
                'contador_instalacion_toner_magenta', 'contador_instalacion_toner_yellow')
    def _compute_paginas_usadas_toner(self):
        """Calcula páginas usadas por cada tóner instalado"""
        for record in self:
            # Tóner Negro
            if record.toner_black_instalado and record.contador_instalacion_toner_black:
                record.paginas_usadas_toner_black = max(0, 
                    record.contador_actual_black - record.contador_instalacion_toner_black)
            else:
                record.paginas_usadas_toner_black = 0
            
            # Para tóners color, dividir el consumo color entre 3 (aprox)
            consumo_color_total = max(0, record.contador_actual_color - 
                                    min(record.contador_instalacion_toner_cyan or record.contador_actual_color,
                                        record.contador_instalacion_toner_magenta or record.contador_actual_color,
                                        record.contador_instalacion_toner_yellow or record.contador_actual_color))
            
            consumo_color_por_toner = consumo_color_total // 3 if consumo_color_total > 0 else 0
            
            record.paginas_usadas_toner_cyan = consumo_color_por_toner if record.toner_cyan_instalado else 0
            record.paginas_usadas_toner_magenta = consumo_color_por_toner if record.toner_magenta_instalado else 0
            record.paginas_usadas_toner_yellow = consumo_color_por_toner if record.toner_yellow_instalado else 0

    @api.depends('paginas_usadas_toner_black', 'paginas_usadas_toner_cyan',
                'paginas_usadas_toner_magenta', 'paginas_usadas_toner_yellow',
                'name.durabilidad_toner_black', 'name.durabilidad_toner_cyan',
                'name.durabilidad_toner_magenta', 'name.durabilidad_toner_yellow')
    def _compute_paginas_restantes_toner(self):
        """Calcula páginas restantes de cada tóner"""
        for record in self:
            if record.name:  # Si tiene modelo asociado
                record.paginas_restantes_toner_black = max(0,
                    (record.name.durabilidad_toner_black or 0) - record.paginas_usadas_toner_black)
                record.paginas_restantes_toner_cyan = max(0,
                    (record.name.durabilidad_toner_cyan or 0) - record.paginas_usadas_toner_cyan)
                record.paginas_restantes_toner_magenta = max(0,
                    (record.name.durabilidad_toner_magenta or 0) - record.paginas_usadas_toner_magenta)
                record.paginas_restantes_toner_yellow = max(0,
                    (record.name.durabilidad_toner_yellow or 0) - record.paginas_usadas_toner_yellow)
            else:
                record.paginas_restantes_toner_black = 0
                record.paginas_restantes_toner_cyan = 0
                record.paginas_restantes_toner_magenta = 0
                record.paginas_restantes_toner_yellow = 0

    @api.depends('paginas_restantes_toner_black', 'paginas_restantes_toner_cyan',
                'paginas_restantes_toner_magenta', 'paginas_restantes_toner_yellow',
                'name.durabilidad_toner_black', 'name.durabilidad_toner_cyan',
                'name.durabilidad_toner_magenta', 'name.durabilidad_toner_yellow')
    def _compute_nivel_toner(self):
        """Calcula el porcentaje restante de cada tóner"""
        for record in self:
            if record.name:  # Si tiene modelo asociado
                # Tóner Negro
                if record.name.durabilidad_toner_black and record.name.durabilidad_toner_black > 0:
                    record.nivel_toner_black = (record.paginas_restantes_toner_black / 
                                            record.name.durabilidad_toner_black) * 100
                else:
                    record.nivel_toner_black = 0
                
                # Tóner Cian
                if record.name.durabilidad_toner_cyan and record.name.durabilidad_toner_cyan > 0:
                    record.nivel_toner_cyan = (record.paginas_restantes_toner_cyan / 
                                            record.name.durabilidad_toner_cyan) * 100
                else:
                    record.nivel_toner_cyan = 0
                
                # Tóner Magenta
                if record.name.durabilidad_toner_magenta and record.name.durabilidad_toner_magenta > 0:
                    record.nivel_toner_magenta = (record.paginas_restantes_toner_magenta / 
                                                record.name.durabilidad_toner_magenta) * 100
                else:
                    record.nivel_toner_magenta = 0
                
                # Tóner Amarillo
                if record.name.durabilidad_toner_yellow and record.name.durabilidad_toner_yellow > 0:
                    record.nivel_toner_yellow = (record.paginas_restantes_toner_yellow / 
                                            record.name.durabilidad_toner_yellow) * 100
                else:
                    record.nivel_toner_yellow = 0
            else:
                record.nivel_toner_black = 0
                record.nivel_toner_cyan = 0
                record.nivel_toner_magenta = 0
                record.nivel_toner_yellow = 0

    @api.depends('stock_cliente_toner_black', 'stock_cliente_toner_cyan',
                'stock_cliente_toner_magenta', 'stock_cliente_toner_yellow',
                'toner_black_instalado', 'toner_cyan_instalado',
                'toner_magenta_instalado', 'toner_yellow_instalado')
    def _compute_stock_total_toner(self):
        """Calcula stock total disponible (instalado + en stock del cliente)"""
        for record in self:
            record.stock_total_toner_black = record.stock_cliente_toner_black + (1 if record.toner_black_instalado else 0)
            record.stock_total_toner_cyan = record.stock_cliente_toner_cyan + (1 if record.toner_cyan_instalado else 0)
            record.stock_total_toner_magenta = record.stock_cliente_toner_magenta + (1 if record.toner_magenta_instalado else 0)
            record.stock_total_toner_yellow = record.stock_cliente_toner_yellow + (1 if record.toner_yellow_instalado else 0)

    @api.depends('stock_total_toner_black', 'stock_total_toner_cyan',
                'stock_total_toner_magenta', 'stock_total_toner_yellow',
                'name.stock_minimo_black', 'name.stock_minimo_cyan',
                'name.stock_minimo_magenta', 'name.stock_minimo_yellow')
    def _compute_estado_stock_toner(self):
        """Calcula estado general del stock de tóner"""
        for record in self:
            if not record.name:
                record.estado_stock_toner = 'normal'
                continue
            
            estados = []
            
            # Evaluar cada tóner según el tipo de máquina
            if record.tipo_maquina_id == 'monocromatica':
                # Solo evaluar tóner negro
                stock_min = record.name.stock_minimo_black or 1
                if record.stock_total_toner_black == 0:
                    estados.append('critico')
                elif record.stock_total_toner_black < stock_min:
                    estados.append('bajo')
                elif record.stock_total_toner_black > stock_min * 2:
                    estados.append('alto')
                else:
                    estados.append('normal')
            
            elif record.tipo_maquina_id == 'color':
                # Evaluar todos los tóners
                toners = [
                    (record.stock_total_toner_black, record.name.stock_minimo_black or 1),
                    (record.stock_total_toner_cyan, record.name.stock_minimo_cyan or 1),
                    (record.stock_total_toner_magenta, record.name.stock_minimo_magenta or 1),
                    (record.stock_total_toner_yellow, record.name.stock_minimo_yellow or 1),
                ]
                
                for stock_actual, stock_min in toners:
                    if stock_actual == 0:
                        estados.append('critico')
                    elif stock_actual < stock_min:
                        estados.append('bajo')
                    elif stock_actual > stock_min * 2:
                        estados.append('alto')
                    else:
                        estados.append('normal')
            
            # Determinar estado general (el más crítico)
            if 'critico' in estados:
                record.estado_stock_toner = 'critico'
            elif 'bajo' in estados:
                record.estado_stock_toner = 'bajo'
            elif all(estado == 'alto' for estado in estados):
                record.estado_stock_toner = 'alto'
            else:
                record.estado_stock_toner = 'normal'

    @api.depends()
    def _compute_toner_counts(self):
        """Calcula contadores de reportes y entregas de tóner"""
        for record in self:
            # Por ahora retornar 0, se actualizará cuando se creen los modelos
            record.toner_reports_count = 0
            record.toner_deliveries_count = 0

    # ==========================================
    # MÉTODOS DE ACCIÓN PARA TÓNER (SIMPLIFICADOS)
    # ==========================================

    def action_view_toner_reports(self):
        """Temporal - Mostrar mensaje hasta crear modelo"""
        raise UserError("El sistema de reportes de tóner está en desarrollo.")

    def action_view_toner_deliveries(self):
        """Temporal - Mostrar mensaje hasta crear modelo"""
        raise UserError("El sistema de entregas de tóner está en desarrollo.")

    def action_create_manual_delivery(self):
        """Temporal - Mostrar mensaje hasta crear modelo"""
        raise UserError("La programación de entregas está en desarrollo.")

    def action_view_model_toner_config(self):
        """Abre la configuración de tóner del modelo"""
        self.ensure_one()
        
        if not self.name:
            raise UserError("Este equipo no tiene un modelo asignado.")
        
        return {
            'name': f'Configuración Tóner - {self.name.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'modelo.maquina',
            'res_id': self.name.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_update_toner_stock(self):
        """Temporal - Mostrar mensaje hasta crear wizard"""
        raise UserError("El wizard de actualización de stock está en desarrollo.")

    def action_install_new_toner(self):
        """Temporal - Mostrar mensaje hasta crear wizard"""
        raise UserError("El wizard de instalación de tóner está en desarrollo.")

    def action_send_stock_reminder(self):
        """Envía recordatorio de stock al cliente"""
        self.ensure_one()
        
        if not self.cliente_id:
            raise UserError("No hay cliente asignado a este equipo.")
        
        if not self.correo_:
            raise UserError("No hay email configurado para este equipo.")
        
        # Por ahora solo mostrar mensaje de confirmación
        self.message_post(
            body=f"📧 Recordatorio de stock programado para {self.correo_}",
            message_type='notification'
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Recordatorio Programado',
                'message': f'Recordatorio de stock programado para {self.correo_}',
                'type': 'success',
                'sticky': False,
            }
        }
   



    # AGREGAR ESTOS MÉTODOS AL FINAL DE LA CLASE alquiler (UnidadAlquiler)

    def _calcular_dias_restantes_toner(self):
        """
        Calcula días estimados restantes para el tóner negro basado en consumo promedio
        """
        self.ensure_one()
        
        try:
            # Buscar reportes recientes para calcular consumo promedio
            reportes_recientes = self.env['toner.counter.submission'].search([
                ('equipment_id', '=', self.id),
                ('state', 'in', ['approved', 'processed'])
            ], order='submission_date desc', limit=5)
            
            if len(reportes_recientes) < 2:
                # No hay suficientes datos, usar valores por defecto conservadores
                return self.name.tiempo_entrega_dias + self.name.margen_seguridad_dias if self.name else 7
            
            # Calcular consumo promedio por día
            total_dias = 0
            total_consumo_bn = 0
            
            for i in range(len(reportes_recientes) - 1):
                reporte_actual = reportes_recientes[i]
                reporte_anterior = reportes_recientes[i + 1]
                
                dias_entre_reportes = (reporte_actual.submission_date.date() - reporte_anterior.submission_date.date()).days
                if dias_entre_reportes > 0:
                    consumo_periodo = reporte_actual.copies_bn_period
                    total_dias += dias_entre_reportes
                    total_consumo_bn += consumo_periodo
            
            if total_dias == 0:
                return 30  # Fallback: 30 días
            
            consumo_promedio_diario = total_consumo_bn / total_dias
            
            if consumo_promedio_diario <= 0:
                return 30  # Si no hay consumo, asumir 30 días
            
            # Calcular días restantes basado en páginas restantes del tóner negro
            if self.paginas_restantes_toner_black > 0:
                dias_restantes = self.paginas_restantes_toner_black / consumo_promedio_diario
                return max(1, int(dias_restantes))
            
            return 1  # Tóner agotado
            
        except Exception as e:
            _logger.exception("Error calculando días restantes de tóner: %s", str(e))
            return 7  # Fallback conservador

    def _crear_alerta_toner_preventiva(self):
        """
        Crea alerta preventiva cuando el tóner se agotará pronto
        """
        self.ensure_one()
        
        try:
            dias_restantes = self._calcular_dias_restantes_toner()
            tiempo_critico = self.name.tiempo_total_prevencion if self.name else 7
            
            if dias_restantes <= tiempo_critico:
                # Verificar si ya existe una entrega programada reciente
                entrega_existente = self.env['toner.delivery.schedule'].search([
                    ('equipment_id', '=', self.id),
                    ('state', 'in', ['programado', 'confirmado', 'preparando', 'enviado']),
                    ('toner_black_qty', '>', 0)
                ], limit=1)
                
                if entrega_existente:
                    _logger.info(f"Ya existe entrega programada para equipo {self.serie}")
                    return False
                
                # Crear programación automática
                delivery_vals = {
                    'equipment_id': self.id,
                    'delivery_date_planned': fields.Date.today() + timedelta(days=2),
                    'toner_black_qty': max(1, (self.name.stock_minimo_black or 1) - self.stock_total_toner_black + 1),
                    'toner_cyan_qty': 0,
                    'toner_magenta_qty': 0,
                    'toner_yellow_qty': 0,
                    'calculation_basis': 'consumo_automatico',
                    'priority': 'alta' if dias_restantes <= 3 else 'normal',
                    'notes': f"Entrega preventiva automática - Se agotará en {dias_restantes} días"
                }
                
                # Para máquinas color, evaluar también tóners color
                if self.tipo_maquina_id == 'color':
                    if self.stock_total_toner_cyan <= (self.name.stock_minimo_cyan or 1):
                        delivery_vals['toner_cyan_qty'] = max(1, (self.name.stock_minimo_cyan or 1) - self.stock_total_toner_cyan + 1)
                    if self.stock_total_toner_magenta <= (self.name.stock_minimo_magenta or 1):
                        delivery_vals['toner_magenta_qty'] = max(1, (self.name.stock_minimo_magenta or 1) - self.stock_total_toner_magenta + 1)
                    if self.stock_total_toner_yellow <= (self.name.stock_minimo_yellow or 1):
                        delivery_vals['toner_yellow_qty'] = max(1, (self.name.stock_minimo_yellow or 1) - self.stock_total_toner_yellow + 1)
                
                delivery = self.env['toner.delivery.schedule'].create(delivery_vals)
                
                self.message_post(
                    body=f"🔔 Alerta preventiva: Entrega automática programada ({delivery.secuencia}) - Tóner se agotará en {dias_restantes} días",
                    message_type='notification'
                )
                
                return True
                
        except Exception as e:
            _logger.exception("Error creando alerta preventiva: %s", str(e))
            return False

    @api.model
    def check_toner_alerts(self):
        """
        Método cron para evaluar equipos que necesitan tóner preventivamente
        """
        equipos = self.search([
            ('estado_alquiler_id', '=', 'alquilada'),
            ('name.gestionar_toner_automatico', '=', True)
        ])
        
        alertas_creadas = 0
        
        for equipo in equipos:
            try:
                if equipo._crear_alerta_toner_preventiva():
                    alertas_creadas += 1
            except Exception as e:
                _logger.error(f"Error evaluando equipo {equipo.serie}: {str(e)}")
        
        _logger.info(f"Alertas preventivas creadas: {alertas_creadas} de {len(equipos)} equipos evaluados")
        return alertas_creadas

    @api.model
    def get_toner_dashboard_data(self):
        """Dashboard centralizado de estado de tóner"""
        base_domain = [('estado_alquiler_id', '=', 'alquilada')]
        
        return {
            'equipos_criticos': self.search_count(base_domain + [('estado_stock_toner', '=', 'critico')]),
            'equipos_bajo_stock': self.search_count(base_domain + [('estado_stock_toner', '=', 'bajo')]),
            'entregas_pendientes': self.env['toner.delivery.schedule'].search_count([
                ('state', 'in', ['programado', 'confirmado'])
            ]),
            'reportes_pendientes': self.env['toner.counter.submission'].search_count([
                ('state', '=', 'pending')
            ]),
            'total_alquilados': self.search_count(base_domain),
            'gestion_automatica_activa': self.search_count(base_domain + [('name.gestionar_toner_automatico', '=', True)])
        }
