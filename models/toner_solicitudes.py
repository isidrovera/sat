# Agregar este nuevo modelo al archivo models.py

import logging
from datetime import timedelta, datetime
from odoo import models, fields, api
import requests
import json
import pytz
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)

class TonerCounterSubmission(models.Model):
    """Modelo para reportes de contadores y estado de tóner por clientes"""
    _name = 'toner.counter.submission'
    _description = 'Reportes de Contadores y Tóner por Clientes'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'submission_date desc'
    _rec_name = 'display_name'

    # ==========================================
    # CAMPO DISPLAY NAME
    # ==========================================
    
    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
        store=True
    )

    @api.depends('equipment_id', 'submission_date', 'client_name')
    def _compute_display_name(self):
        """Calcula el nombre a mostrar del registro"""
        for record in self:
            try:
                equipment_name = record.equipment_id.name.name if record.equipment_id and record.equipment_id.name.name else 'Sin equipo'
                date_str = record.submission_date.strftime('%d/%m/%Y') if record.submission_date else 'Sin fecha'
                client_name = record.client_name or 'Sin cliente'
                
                record.display_name = f"{equipment_name} - {client_name} ({date_str})"
            except Exception:
                record.display_name = f"Reporte Tóner {record.id or 'Nuevo'}"

    # ==========================================
    # CAMPOS BÁSICOS
    # ==========================================
    
    equipment_id = fields.Many2one(
            'alquiler',
            string='Equipo',
            required=True,
            tracking=True,
            domain=[('estado_alquiler_id', '=', 'alquilada')],
            help='Equipo para el cual se reportan los contadores y estado de tóner'
        )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        related='equipment_id.cliente_id',
        store=True,
        readonly=True
    )
    
    submission_date = fields.Datetime(
        string='Fecha de Reporte',
        default=fields.Datetime.now,
        required=True,
        tracking=True
    )
    
    secuencia = fields.Char(
        string='Número de Reporte',
        default='New',
        copy=False,
        required=True,
        readonly=True
    )

    # ==========================================
    # INFORMACIÓN DEL CONTACTO
    # ==========================================
    
    client_name = fields.Char(
        string='Nombre del Reportante',
        required=True,
        tracking=True,
        help='Nombre completo de la persona que reporta'
    )
    
    client_email = fields.Char(
        string='Email del Reportante',
        required=True,
        tracking=True,
        help='Email de la persona que reporta'
    )
    
    client_phone = fields.Char(
        string='Teléfono del Reportante',
        tracking=True,
        help='Teléfono de contacto'
    )

    client_phone_clean = fields.Char(
        string='Teléfono Limpio',
        compute='_compute_client_phone_clean',
        store=True,
        help='Número de teléfono formateado para WhatsApp'
    )

    # ==========================================
    # CONTADORES REPORTADOS
    # ==========================================
    
    counter_bn = fields.Integer(
        string='Contador Blanco y Negro',
        required=True,
        tracking=True,
        help='Lectura actual del contador de copias en blanco y negro'
    )
    
    counter_color = fields.Integer(
        string='Contador Color',
        default=0,
        tracking=True,
        help='Lectura actual del contador de copias a color'
    )
    
    # Contadores anteriores (calculados)
    previous_counter_bn = fields.Integer(
        string='Contador B/N Anterior',
        compute='_compute_previous_counters',
        store=True,
        help='Último contador B/N registrado'
    )
    
    previous_counter_color = fields.Integer(
        string='Contador Color Anterior',
        compute='_compute_previous_counters',
        store=True,
        help='Último contador Color registrado'
    )
    
    # Copias del período
    copies_bn_period = fields.Integer(
        string='Copias B/N del Período',
        compute='_compute_period_copies',
        store=True,
        help='Copias B/N realizadas en este período'
    )
    
    copies_color_period = fields.Integer(
        string='Copias Color del Período',
        compute='_compute_period_copies',
        store=True,
        help='Copias Color realizadas en este período'
    )

    total_copies_period = fields.Integer(
        string='Total Copias del Período',
        compute='_compute_total_copies_period',
        store=True,
        help='Total de copias del período (B/N + Color)'
    )

    # ==========================================
    # STOCK DE TÓNER REPORTADO POR CLIENTE
    # ==========================================
    
    stock_reportado_black = fields.Integer(
        string='Stock Tóner Negro',
        default=0,
        help='Cantidad de tóner negro que tiene el cliente en stock (sin instalar)'
    )
    
    stock_reportado_cyan = fields.Integer(
        string='Stock Tóner Cian',
        default=0,
        help='Cantidad de tóner cian que tiene el cliente en stock (sin instalar)'
    )
    
    stock_reportado_magenta = fields.Integer(
        string='Stock Tóner Magenta',
        default=0,
        help='Cantidad de tóner magenta que tiene el cliente en stock (sin instalar)'
    )
    
    stock_reportado_yellow = fields.Integer(
        string='Stock Tóner Amarillo',
        default=0,
        help='Cantidad de tóner amarillo que tiene el cliente en stock (sin instalar)'
    )

    # ==========================================
    # NIVEL DE TÓNER INSTALADO
    # ==========================================
    
    nivel_toner_black = fields.Selection([
        ('lleno', '🟢 Lleno (75-100%)'),
        ('medio', '🟡 Medio (50-74%)'),
        ('bajo', '🟠 Bajo (25-49%)'),
        ('critico', '🔴 Crítico (0-24%)'),
        ('agotado', '⚫ Agotado (0%)')
    ], string='Nivel Tóner Negro', help='Nivel del tóner negro instalado')
    
    nivel_toner_cyan = fields.Selection([
        ('lleno', '🟢 Lleno (75-100%)'),
        ('medio', '🟡 Medio (50-74%)'),
        ('bajo', '🟠 Bajo (25-49%)'),
        ('critico', '🔴 Crítico (0-24%)'),
        ('agotado', '⚫ Agotado (0%)')
    ], string='Nivel Tóner Cian', help='Nivel del tóner cian instalado')
    
    nivel_toner_magenta = fields.Selection([
        ('lleno', '🟢 Lleno (75-100%)'),
        ('medio', '🟡 Medio (50-74%)'),
        ('bajo', '🟠 Bajo (25-49%)'),
        ('critico', '🔴 Crítico (0-24%)'),
        ('agotado', '⚫ Agotado (0%)')
    ], string='Nivel Tóner Magenta', help='Nivel del tóner magenta instalado')
    
    nivel_toner_yellow = fields.Selection([
        ('lleno', '🟢 Lleno (75-100%)'),
        ('medio', '🟡 Medio (50-74%)'),
        ('bajo', '🟠 Bajo (25-49%)'),
        ('critico', '🔴 Crítico (0-24%)'),
        ('agotado', '⚫ Agotado (0%)')
    ], string='Nivel Tóner Amarillo', help='Nivel del tóner amarillo instalado')

    # ==========================================
    # SOLICITUDES URGENTES
    # ==========================================
    
    requiere_toner_black = fields.Boolean(
        string='Necesita Tóner Negro',
        help='Cliente solicita tóner negro urgente'
    )
    
    requiere_toner_cyan = fields.Boolean(
        string='Necesita Tóner Cian',
        help='Cliente solicita tóner cian urgente'
    )
    
    requiere_toner_magenta = fields.Boolean(
        string='Necesita Tóner Magenta',
        help='Cliente solicita tóner magenta urgente'
    )
    
    requiere_toner_yellow = fields.Boolean(
        string='Necesita Tóner Amarillo',
        help='Cliente solicita tóner amarillo urgente'
    )

    urgente = fields.Boolean(
        string='Solicitud Urgente',
        help='¿Es una solicitud urgente de tóner?'
    )

    # ==========================================
    # CAMPOS CALCULADOS DE ANÁLISIS
    # ==========================================
    
    # Stock total disponible (reportado + instalado)
    stock_total_black = fields.Integer(
        string='Stock Total Negro',
        compute='_compute_stock_total',
        help='Stock reportado + tóner instalado (si existe)'
    )
    
    stock_total_cyan = fields.Integer(
        string='Stock Total Cian',
        compute='_compute_stock_total',
        help='Stock reportado + tóner instalado (si existe)'
    )
    
    stock_total_magenta = fields.Integer(
        string='Stock Total Magenta',
        compute='_compute_stock_total',
        help='Stock reportado + tóner instalado (si existe)'
    )
    
    stock_total_yellow = fields.Integer(
        string='Stock Total Amarillo',
        compute='_compute_stock_total',
        help='Stock reportado + tóner instalado (si existe)'
    )

    # Análisis de necesidad de tóner
    requiere_entrega_automatica = fields.Boolean(
        string='Requiere Entrega Automática',
        compute='_compute_requiere_entrega',
        store=True,
        help='Sistema determina si requiere entrega basado en stock y configuración'
    )

    fecha_estimada_agotamiento_black = fields.Date(
        string='Fecha Estimada Agotamiento Negro',
        compute='_compute_fecha_agotamiento',
        help='Fecha estimada en que se agotará el tóner negro'
    )

    fecha_sugerida_entrega = fields.Date(
        string='Fecha Sugerida de Entrega',
        compute='_compute_fecha_sugerida_entrega',
        help='Fecha sugerida para entregar tóner'
    )

    # ==========================================
    # INFORMACIÓN ADICIONAL
    # ==========================================
    
    notes = fields.Text(
        string='Observaciones del Cliente',
        help='Observaciones adicionales sobre los contadores o tóner'
    )
    
    photo_counter = fields.Binary(
        string='Foto del Contador',
        help='Foto de la pantalla del contador como evidencia'
    )
    
    photo_counter_filename = fields.Char(
        string='Nombre Archivo Contador'
    )
    
    photo_toner = fields.Binary(
        string='Foto del Tóner',
        help='Foto del estado del tóner como evidencia'
    )
    
    photo_toner_filename = fields.Char(
        string='Nombre Archivo Tóner'
    )

    # ==========================================
    # ESTADO Y GESTIÓN
    # ==========================================
    
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('reviewed', 'Revisado'),
        ('approved', 'Aprobado'),
        ('processed', 'Procesado'),
        ('rejected', 'Rechazado')
    ], string='Estado', default='pending', tracking=True)
    
    reviewer_id = fields.Many2one(
        'res.users',
        string='Revisado por',
        tracking=True,
        help='Usuario que revisó el reporte'
    )
    
    review_date = fields.Datetime(
        string='Fecha de Revisión',
        tracking=True
    )
    
    review_notes = fields.Text(
        string='Notas de Revisión',
        help='Notas del técnico que revisó'
    )

    # Relaciones con otros modelos
    delivery_scheduled_id = fields.Many2one(
        'toner.delivery.schedule',
        string='Entrega Programada',
        readonly=True,
        help='Entrega de tóner programada a partir de este reporte'
    )

    # ==========================================
    # MÉTODOS COMPUTE
    # ==========================================

    @api.depends('client_phone')
    def _compute_client_phone_clean(self):
        """Formatea el número de teléfono para WhatsApp"""
        for record in self:
            if record.client_phone:
                phone = record.client_phone.replace('+', '').replace(' ', '').replace('-', '')
                phone = ''.join(filter(str.isdigit, phone))
                
                if not phone.startswith('51') and len(phone) == 9:
                    phone = '51' + phone
                record.client_phone_clean = phone
            else:
                record.client_phone_clean = ''

    @api.depends('equipment_id')
    def _compute_previous_counters(self):
        """Calcula los contadores anteriores basado en la última lectura del equipo"""
        for record in self:
            if record.equipment_id:
                record.previous_counter_bn = record.equipment_id.contador_actual_black or 0
                record.previous_counter_color = record.equipment_id.contador_actual_color or 0
            else:
                record.previous_counter_bn = 0
                record.previous_counter_color = 0

    @api.depends('counter_bn', 'counter_color', 'previous_counter_bn', 'previous_counter_color')
    def _compute_period_copies(self):
        """Calcula las copias del período"""
        for record in self:
            record.copies_bn_period = max(0, record.counter_bn - record.previous_counter_bn)
            record.copies_color_period = max(0, record.counter_color - record.previous_counter_color)

    @api.depends('copies_bn_period', 'copies_color_period')
    def _compute_total_copies_period(self):
        """Calcula el total de copias del período"""
        for record in self:
            record.total_copies_period = record.copies_bn_period + record.copies_color_period

    @api.depends('stock_reportado_black', 'stock_reportado_cyan', 
                 'stock_reportado_magenta', 'stock_reportado_yellow',
                 'nivel_toner_black', 'nivel_toner_cyan',
                 'nivel_toner_magenta', 'nivel_toner_yellow')
    def _compute_stock_total(self):
        """Calcula stock total disponible (reportado + instalado)"""
        for record in self:
            # Tóner negro
            instalado_black = 1 if record.nivel_toner_black and record.nivel_toner_black != 'agotado' else 0
            record.stock_total_black = record.stock_reportado_black + instalado_black
            
            # Tóner cian
            instalado_cyan = 1 if record.nivel_toner_cyan and record.nivel_toner_cyan != 'agotado' else 0
            record.stock_total_cyan = record.stock_reportado_cyan + instalado_cyan
            
            # Tóner magenta
            instalado_magenta = 1 if record.nivel_toner_magenta and record.nivel_toner_magenta != 'agotado' else 0
            record.stock_total_magenta = record.stock_reportado_magenta + instalado_magenta
            
            # Tóner amarillo
            instalado_yellow = 1 if record.nivel_toner_yellow and record.nivel_toner_yellow != 'agotado' else 0
            record.stock_total_yellow = record.stock_reportado_yellow + instalado_yellow

    @api.depends('stock_total_black', 'stock_total_cyan', 'stock_total_magenta', 'stock_total_yellow',
                 'equipment_id.name.stock_minimo_black', 'equipment_id.name.stock_minimo_cyan',
                 'equipment_id.name.stock_minimo_magenta', 'equipment_id.name.stock_minimo_yellow',
                 'requiere_toner_black', 'requiere_toner_cyan', 'requiere_toner_magenta', 'requiere_toner_yellow',
                 'nivel_toner_black', 'nivel_toner_cyan', 'nivel_toner_magenta', 'nivel_toner_yellow')
    def _compute_requiere_entrega(self):
        """Determina si requiere entrega automática basado en stock y configuración"""
        for record in self:
            requiere = False
            
            if record.equipment_id and record.equipment_id.name.name:
                modelo = record.equipment_id.name.name
                
                # Verificar solicitudes urgentes del cliente
                if (record.requiere_toner_black or record.requiere_toner_cyan or 
                    record.requiere_toner_magenta or record.requiere_toner_yellow):
                    requiere = True
                
                # Verificar stock mínimo - Tóner Negro
                if record.stock_total_black <= (modelo.stock_minimo_black or 1):
                    requiere = True
                
                # Verificar niveles críticos
                if record.nivel_toner_black in ['critico', 'agotado']:
                    requiere = True
                
                # Para máquinas color, verificar tóners color
                if record.equipment_id.tipo_maquina_id == 'color':
                    if (record.stock_total_cyan <= (modelo.stock_minimo_cyan or 1) or
                        record.stock_total_magenta <= (modelo.stock_minimo_magenta or 1) or
                        record.stock_total_yellow <= (modelo.stock_minimo_yellow or 1)):
                        requiere = True
                    
                    if (record.nivel_toner_cyan in ['critico', 'agotado'] or
                        record.nivel_toner_magenta in ['critico', 'agotado'] or
                        record.nivel_toner_yellow in ['critico', 'agotado']):
                        requiere = True
            
            record.requiere_entrega_automatica = requiere

    @api.depends('copies_bn_period', 'equipment_id.name.durabilidad_toner_black', 'nivel_toner_black')
    def _compute_fecha_agotamiento(self):
        """Calcula fecha estimada de agotamiento del tóner negro"""
        for record in self:
            # Por ahora retornamos None, se implementará con historial de consumo
            record.fecha_estimada_agotamiento_black = False

    @api.depends('fecha_estimada_agotamiento_black', 'equipment_id.name.tiempo_entrega_dias', 'equipment_id.name.margen_seguridad_dias')
    def _compute_fecha_sugerida_entrega(self):
        """Calcula fecha sugerida de entrega"""
        for record in self:
            if record.fecha_estimada_agotamiento_black and record.equipment_id and record.equipment_id.name.name:
                modelo = record.equipment_id.name.name
                dias_previos = (modelo.tiempo_entrega_dias or 2) + (modelo.margen_seguridad_dias or 3)
                record.fecha_sugerida_entrega = record.fecha_estimada_agotamiento_black - timedelta(days=dias_previos)
            else:
                record.fecha_sugerida_entrega = False

    # ==========================================
    # MÉTODOS CREATE Y OVERRIDE
    # ==========================================

    @api.model
    def create(self, vals):
        """Sobrescribe create para asignar secuencia y enviar confirmación"""
        if vals.get('secuencia', 'New') == 'New':
            vals['secuencia'] = self.env['ir.sequence'].next_by_code('toner.counter.submission') or 'TCS/001'
        
        result = super(TonerCounterSubmission, self).create(vals)
        
        # Crear nota en el chatter
        try:
            result._create_chatter_note()
        except Exception as e:
            _logger.error("Error creando nota en chatter: %s", str(e))
        
        # Enviar confirmación WhatsApp al cliente
        try:
            result.send_whatsapp_confirmation()
        except Exception as e:
            _logger.error("Error enviando confirmación WhatsApp: %s", str(e))
        
        return result

    def _create_chatter_note(self):
        """Crea nota informativa en el chatter"""
        self.ensure_one()
        
        # Construir información de stock
        stock_info = f"• Negro: {self.stock_reportado_black} en stock"
        if self.equipment_id.tipo_maquina_id == 'color':
            stock_info += f"<br/>• Cian: {self.stock_reportado_cyan} en stock"
            stock_info += f"<br/>• Magenta: {self.stock_reportado_magenta} en stock"
            stock_info += f"<br/>• Amarillo: {self.stock_reportado_yellow} en stock"
        
        # Construir información de niveles
        nivel_info = f"• Negro: {dict(self._fields['nivel_toner_black'].selection).get(self.nivel_toner_black, 'No reportado')}"
        if self.equipment_id.tipo_maquina_id == 'color':
            nivel_info += f"<br/>• Cian: {dict(self._fields['nivel_toner_cyan'].selection).get(self.nivel_toner_cyan, 'No reportado')}"
            nivel_info += f"<br/>• Magenta: {dict(self._fields['nivel_toner_magenta'].selection).get(self.nivel_toner_magenta, 'No reportado')}"
            nivel_info += f"<br/>• Amarillo: {dict(self._fields['nivel_toner_yellow'].selection).get(self.nivel_toner_yellow, 'No reportado')}"
        
        # Solicitudes urgentes
        urgentes = []
        if self.requiere_toner_black: urgentes.append("Negro")
        if self.requiere_toner_cyan: urgentes.append("Cian")
        if self.requiere_toner_magenta: urgentes.append("Magenta")
        if self.requiere_toner_yellow: urgentes.append("Amarillo")
        
        urgente_info = f"Tóners solicitados: {', '.join(urgentes)}" if urgentes else "Ninguno"
        
        body = f"""
        📊 <b>Nuevo Reporte de Contadores y Tóner</b><br/><br/>
        
        <b>📋 Información del Equipo:</b><br/>
        • <b>Equipo:</b> {self.equipment_id.name.name if self.equipment_id.name.name else 'Sin nombre'}<br/>
        • <b>Serie:</b> {self.equipment_id.serie or 'Sin serie'}<br/>
        • <b>Cliente:</b> {self.partner_id.name if self.partner_id else 'Sin cliente'}<br/><br/>
        
        <b>👤 Reportado por:</b><br/>
        • <b>Nombre:</b> {self.client_name}<br/>
        • <b>Email:</b> {self.client_email}<br/>
        • <b>Teléfono:</b> {self.client_phone or 'No proporcionado'}<br/><br/>
        
        <b>📊 Contadores:</b><br/>
        • <b>B/N:</b> {self.counter_bn:,} (Período: {self.copies_bn_period:,})<br/>
        • <b>Color:</b> {self.counter_color:,} (Período: {self.copies_color_period:,})<br/><br/>
        
        <b>📦 Stock Reportado:</b><br/>
        {stock_info}<br/><br/>
        
        <b>🎨 Nivel de Tóner Instalado:</b><br/>
        {nivel_info}<br/><br/>
        
        <b>🚨 Solicitudes Urgentes:</b><br/>
        {urgente_info}<br/><br/>
        
        <b>🔄 Requiere Entrega Automática:</b> {'✅ Sí' if self.requiere_entrega_automatica else '❌ No'}<br/>
        
        {f'<br/><b>📝 Observaciones:</b><br/>{self.notes}' if self.notes else ''}
        """
        
        self.message_post(
            body=body,
            message_type='notification'
        )

    # ==========================================
    # MÉTODOS DE VALIDACIÓN
    # ==========================================

    @api.constrains('counter_bn', 'counter_color')
    def _check_counters(self):
        """Valida que los contadores sean válidos"""
        for record in self:
            if record.counter_bn < 0:
                raise ValidationError("El contador de blanco y negro no puede ser negativo.")
            
            if record.counter_color < 0:
                raise ValidationError("El contador de color no puede ser negativo.")
            
            # Validar que los contadores no sean menores a los anteriores
            if record.counter_bn < record.previous_counter_bn:
                raise ValidationError(
                    f"El contador B/N ({record.counter_bn:,}) no puede ser menor "
                    f"al contador anterior ({record.previous_counter_bn:,})."
                )
            
            if record.counter_color < record.previous_counter_color:
                raise ValidationError(
                    f"El contador Color ({record.counter_color:,}) no puede ser menor "
                    f"al contador anterior ({record.previous_counter_color:,})."
                )

    @api.constrains('client_email')
    def _check_client_email(self):
        """Valida el formato del email"""
        for record in self:
            if record.client_email:
                import re
                email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                if not re.match(email_pattern, record.client_email):
                    raise ValidationError(f"El email '{record.client_email}' no tiene un formato válido.")

    @api.constrains('stock_reportado_black', 'stock_reportado_cyan', 
                    'stock_reportado_magenta', 'stock_reportado_yellow')
    def _check_stock_reportado(self):
        """Valida que el stock reportado sea válido"""
        for record in self:
            if record.stock_reportado_black < 0:
                raise ValidationError("El stock de tóner negro no puede ser negativo.")
            if record.stock_reportado_cyan < 0:
                raise ValidationError("El stock de tóner cian no puede ser negativo.")
            if record.stock_reportado_magenta < 0:
                raise ValidationError("El stock de tóner magenta no puede ser negativo.")
            if record.stock_reportado_yellow < 0:
                raise ValidationError("El stock de tóner amarillo no puede ser negativo.")

    # ==========================================
    # MÉTODOS DE ACCIÓN
    # ==========================================

    def action_review(self):
        """Marca como revisado"""
        self.ensure_one()
        self.state = 'reviewed'
        self.reviewer_id = self.env.user
        self.review_date = fields.Datetime.now()
        self.message_post(
            body=f"👀 Reporte revisado por {self.env.user.name}",
            message_type='notification'
        )

    def action_approve(self):
        """Aprueba el reporte y actualiza el equipo"""
        self.ensure_one()
        self.state = 'approved'
        if not self.reviewer_id:
            self.reviewer_id = self.env.user
            self.review_date = fields.Datetime.now()
        
        # Actualizar contadores en el equipo
        self._update_equipment_counters()
        
        # Actualizar stock de tóner en el equipo
        self._update_equipment_toner_stock()
        
        self.message_post(
            body=f"✅ Reporte aprobado por {self.env.user.name}. Datos sincronizados con el equipo.",
            message_type='notification'
        )

    def action_process_delivery(self):
        """Procesa y crea programación de entrega si es necesario"""
        self.ensure_one()
        
        if self.state != 'approved':
            raise UserError("Solo se pueden procesar reportes aprobados.")
        
        if self.delivery_scheduled_id:
            raise UserError("Ya existe una entrega programada para este reporte.")
        
        if not self.requiere_entrega_automatica:
            raise UserError("Este reporte no requiere entrega automática según el análisis.")
        
        # Crear programación de entrega
        delivery_vals = self._prepare_delivery_values()
        
        try:
            delivery = self.env['toner.delivery.schedule'].create(delivery_vals)
            self.delivery_scheduled_id = delivery.id
            self.state = 'processed'
            
            # ✅ LÍNEA CORREGIDA - USAR display_name
            self.message_post(
                body=f"🚚 Entrega programada creada: {delivery.display_name}",
                message_type='notification'
            )
            
            return {
                'name': 'Entrega Programada',
                'view_mode': 'form',
                'res_model': 'toner.delivery.schedule',
                'res_id': delivery.id,
                'type': 'ir.actions.act_window',
                'target': 'current',
            }
        except Exception as e:
            _logger.exception("Error creando programación de entrega: %s", str(e))
            raise UserError(f"Error al crear la programación de entrega: {str(e)}")
    def action_reject(self):
        """Rechaza el reporte"""
        self.ensure_one()
        self.state = 'rejected'
        if not self.reviewer_id:
            self.reviewer_id = self.env.user
            self.review_date = fields.Datetime.now()
        self.message_post(
            body=f"❌ Reporte rechazado por {self.env.user.name}",
            message_type='notification'
        )

    def action_reset_to_pending(self):
        """Regresa a estado pendiente"""
        self.ensure_one()
        self.state = 'pending'
        self.reviewer_id = False
        self.review_date = False
        self.review_notes = False
        self.message_post(
            body="🔄 Reporte regresado a estado pendiente",
            message_type='notification'
        )

    # ==========================================
    # MÉTODOS DE ACTUALIZACIÓN DE EQUIPO
    # ==========================================

    def _update_equipment_counters(self):
        """Actualiza los contadores en el equipo"""
        self.ensure_one()
        if self.equipment_id:
            self.equipment_id.write({
                'contador_actual_black': self.counter_bn,
                'contador_actual_color': self.counter_color,
                'fecha_ultima_lectura': self.submission_date
            })

    def _update_equipment_toner_stock(self):
        """Actualiza el stock de tóner en el equipo"""
        self.ensure_one()
        if self.equipment_id:
            update_vals = {
                'stock_cliente_toner_black': self.stock_reportado_black,
                'stock_cliente_toner_cyan': self.stock_reportado_cyan,
                'stock_cliente_toner_magenta': self.stock_reportado_magenta,
                'stock_cliente_toner_yellow': self.stock_reportado_yellow,
            }
            
            # Actualizar estado de tóner instalado basado en niveles reportados
            if self.nivel_toner_black == 'agotado':
                update_vals['toner_black_instalado'] = False
            elif self.nivel_toner_black and self.nivel_toner_black != 'agotado':
                update_vals['toner_black_instalado'] = True
            
            if self.equipment_id.tipo_maquina_id == 'color':
                if self.nivel_toner_cyan == 'agotado':
                    update_vals['toner_cyan_instalado'] = False
                elif self.nivel_toner_cyan and self.nivel_toner_cyan != 'agotado':
                    update_vals['toner_cyan_instalado'] = True
                
                if self.nivel_toner_magenta == 'agotado':
                    update_vals['toner_magenta_instalado'] = False
                elif self.nivel_toner_magenta and self.nivel_toner_magenta != 'agotado':
                    update_vals['toner_magenta_instalado'] = True
                
                if self.nivel_toner_yellow == 'agotado':
                    update_vals['toner_yellow_instalado'] = False
                elif self.nivel_toner_yellow and self.nivel_toner_yellow != 'agotado':
                    update_vals['toner_yellow_instalado'] = True
            
            self.equipment_id.write(update_vals)

    def _prepare_delivery_values(self):
        """Prepara valores para crear programación de entrega"""
        self.ensure_one()
        
        # Calcular fecha de entrega sugerida
        if self.fecha_sugerida_entrega:
            delivery_date = self.fecha_sugerida_entrega
        else:
            # Fallback: entrega en 2 días
            delivery_date = fields.Date.today() + timedelta(days=2)
        
        # Determinar cantidades a entregar
        modelo = self.equipment_id.name.name
        qty_black = 0
        qty_cyan = 0
        qty_magenta = 0
        qty_yellow = 0
        
        # Tóner Negro
        if (self.requiere_toner_black or 
            self.stock_total_black <= (modelo.stock_minimo_black or 1) or
            self.nivel_toner_black in ['critico', 'agotado']):
            qty_black = max(1, (modelo.stock_minimo_black or 1) - self.stock_total_black + 1)
        
        # Tóners Color (solo para máquinas color)
        if self.equipment_id.tipo_maquina_id == 'color':
            if (self.requiere_toner_cyan or 
                self.stock_total_cyan <= (modelo.stock_minimo_cyan or 1) or
                self.nivel_toner_cyan in ['critico', 'agotado']):
                qty_cyan = max(1, (modelo.stock_minimo_cyan or 1) - self.stock_total_cyan + 1)
            
            if (self.requiere_toner_magenta or 
                self.stock_total_magenta <= (modelo.stock_minimo_magenta or 1) or
                self.nivel_toner_magenta in ['critico', 'agotado']):
                qty_magenta = max(1, (modelo.stock_minimo_magenta or 1) - self.stock_total_magenta + 1)
            
            if (self.requiere_toner_yellow or 
                self.stock_total_yellow <= (modelo.stock_minimo_yellow or 1) or
                self.nivel_toner_yellow in ['critico', 'agotado']):
                qty_yellow = max(1, (modelo.stock_minimo_yellow or 1) - self.stock_total_yellow + 1)
        
        return {
            'equipment_id': self.equipment_id.id,
            'submission_id': self.id,
            'delivery_date_planned': delivery_date,
            'toner_black_qty': qty_black,
            'toner_cyan_qty': qty_cyan,
            'toner_magenta_qty': qty_magenta,
            'toner_yellow_qty': qty_yellow,
            'urgente': self.urgente,
            'calculation_basis': 'reporte_cliente',
            'notes': f"Generado automáticamente desde reporte {self.secuencia}\n\nObservaciones del cliente:\n{self.notes or 'Sin observaciones'}"
        }

    # ==========================================
    # MÉTODOS DE WHATSAPP
    # ==========================================

    def send_whatsapp_message(self, phone, message):
        """Envía mensaje de WhatsApp usando la API corporativa"""
        try:
            url = 'https://whatsappapi.copiercompanysac.com/api/message'
            data = {
                'phone': phone,
                'message': message
            }
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, json=data)
            
            _logger.info("WhatsApp API - Código de estado: %s", response.status_code)
            _logger.info("WhatsApp API - Respuesta: %s", response.text)
            
            try:
                response_json = response.json()
                _logger.info("WhatsApp API - Respuesta JSON: %s", response_json)
                return response_json
            except json.JSONDecodeError as e:
                error_msg = f"La respuesta no contiene un JSON válido: {str(e)}"
                _logger.error(error_msg)
                return {"error": error_msg}
                
        except Exception as e:
            _logger.exception("Error enviando mensaje WhatsApp: %s", str(e))
            return {"error": str(e)}

    def send_whatsapp_confirmation(self):
        """Envía confirmación por WhatsApp al cliente"""
        self.ensure_one()
        
        if not self.client_phone_clean:
            _logger.warning("No hay número de teléfono válido para enviar WhatsApp - Reporte: %s", self.secuencia)
            return False
        
        try:
            # Determinar saludo según la hora
            lima_tz = pytz.timezone('America/Lima')
            current_time = datetime.now(lima_tz)
            current_hour = current_time.hour

            if 5 <= current_hour < 12:
                saludo = "👋 Buenos días"
            elif 12 <= current_hour < 18:
                saludo = "👋 Buenas tardes"
            else:
                saludo = "👋 Buenas noches"

            # Construir mensaje de confirmación
            equipment_name = self.equipment_id.name.name if self.equipment_id and self.equipment_id.name.name else 'Sin especificar'
            serie = self.equipment_id.serie or 'Sin serie'

            # Resumen de stock reportado
            stock_summary = f"Negro: {self.stock_reportado_black}"
            if self.equipment_id.tipo_maquina_id == 'color':
                stock_summary += f", Cian: {self.stock_reportado_cyan}, Magenta: {self.stock_reportado_magenta}, Amarillo: {self.stock_reportado_yellow}"

            # Información de entrega
            entrega_info = ""
            if self.requiere_entrega_automatica:
                entrega_info = "\n\n🚚 *Entrega Programada:*\nSe ha programado una entrega de tóner basada en su reporte. Recibirá confirmación de la fecha de entrega."
            else:
                entrega_info = "\n\n✅ *Stock Suficiente:*\nSu stock actual es suficiente según nuestros parámetros."

            message = (
                f"*🏢 Copier Company*\n\n"
                f"{saludo}, {self.client_name}.\n\n"
                f"Hemos recibido exitosamente su reporte de contadores y tóner:\n\n"
                f"📋 *Número de Reporte:* {self.secuencia}\n"
                f"🖨️ *Equipo:* {equipment_name}\n"
                f"🔢 *Serie:* {serie}\n"
                f"📊 *Contador B/N:* {self.counter_bn:,}\n"
                f"📊 *Contador Color:* {self.counter_color:,}\n"
                f"📈 *Copias del Período:* {self.total_copies_period:,}\n"
                f"📦 *Stock Reportado:* {stock_summary}\n"
                f"{entrega_info}\n\n"
                f"Su reporte será revisado por nuestro equipo administrativo.\n\n"
                f"Recibirá confirmación de la validación en: {self.client_email}\n\n"
                f"Gracias por confiar en Copier Company.\n\n"
                f"Atentamente,\n"
                f"📞 Administración Copier Company\n"
                f"☎️ Tel: +51975399303\n"
                f"📧 Email: info@copiercompanysac.com"
            )

            # Enviar mensaje
            response = self.send_whatsapp_message(self.client_phone_clean, message)
            
            if response and not response.get('error'):
                self.message_post(
                    body=f"✅ Confirmación WhatsApp enviada a {self.client_phone_clean}",
                    message_type='notification'
                )
                _logger.info("WhatsApp de confirmación enviado exitosamente - Reporte: %s, Teléfono: %s", 
                           self.secuencia, self.client_phone_clean)
                return True
            else:
                error_msg = response.get('error', 'Error desconocido') if response else 'Sin respuesta'
                self.message_post(
                    body=f"❌ Error enviando WhatsApp a {self.client_phone_clean}: {error_msg}",
                    message_type='notification'
                )
                _logger.error("Error enviando WhatsApp - Reporte: %s, Error: %s", self.secuencia, error_msg)
                return False
                
        except Exception as e:
            _logger.exception("Error en send_whatsapp_confirmation - Reporte: %s", self.secuencia)
            self.message_post(
                body=f"❌ Excepción enviando WhatsApp: {str(e)}",
                message_type='notification'
            )
            return False

    # ==========================================
    # MÉTODOS ESTÁTICOS Y DE UTILIDAD
    # ==========================================

    @api.model
    def create_from_public_form(self, vals):
        """Método específico para crear desde formulario público"""
        _logger.info("=== INICIANDO create_from_public_form para tóner ===")
        _logger.info("Valores del formulario: %s", vals)
        
        try:
            # Validaciones
            required_fields = ['equipment_id', 'client_name', 'client_email', 'counter_bn']
            missing_fields = [field for field in required_fields if not vals.get(field)]
            
            if missing_fields:
                error_msg = f"Campos requeridos faltantes: {', '.join(missing_fields)}"
                raise ValidationError(error_msg)
            
            # Crear el reporte
            submission = self.create(vals)
            
            # Crear actividad para el equipo administrativo
            try:
                self._create_admin_activity(submission)
            except Exception as e:
                _logger.error("Error creando actividad administrativa: %s", str(e))
            
            return submission
            
        except Exception as e:
            _logger.exception("Error en create_from_public_form: %s", str(e))
            raise

    def _create_admin_activity(self, submission):
        """Crea una actividad para el equipo administrativo"""
        try:
            # Buscar usuarios del grupo administrativo
            admin_group = self.env.ref('account.group_account_user', False)
            if admin_group and admin_group.users:
                assignee = admin_group.users[0]
            else:
                assignee = self.env.user
            
            activity_vals = {
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'summary': f'Revisar Reporte Tóner - {submission.secuencia}',
                'note': f'''
                    📊 <b>Nuevo Reporte de Contadores y Tóner</b><br/><br/>
                    
                    <b>Equipo:</b> {submission.equipment_id.name if submission.equipment_id.name else 'Sin nombre'}<br/>
                    <b>Serie:</b> {submission.equipment_id.serie or 'Sin serie'}<br/>
                    <b>Cliente:</b> {submission.partner_id.name if submission.partner_id else 'Sin cliente'}<br/><br/>
                    
                    <b>Reportado por:</b> {submission.client_name}<br/>
                    <b>Email:</b> {submission.client_email}<br/>
                    <b>Teléfono:</b> {submission.client_phone or 'No proporcionado'}<br/><br/>
                    
                    <b>Contadores:</b><br/>
                    • B/N: {submission.counter_bn:,} (Período: {submission.copies_bn_period:,})<br/>
                    • Color: {submission.counter_color:,} (Período: {submission.copies_color_period:,})<br/><br/>
                    
                    <b>Stock Reportado:</b><br/>
                    • Negro: {submission.stock_reportado_black}<br/>
                    • Cian: {submission.stock_reportado_cyan}<br/>
                    • Magenta: {submission.stock_reportado_magenta}<br/>
                    • Amarillo: {submission.stock_reportado_yellow}<br/><br/>
                    
                    <b>Requiere Entrega:</b> {'✅ Sí' if submission.requiere_entrega_automatica else '❌ No'}<br/><br/>
                    
                    {'<b>Observaciones:</b><br/>' + submission.notes + '<br/><br/>' if submission.notes else ''}
                    
                    Por favor, revisar y aprobar el reporte para actualizar el equipo.
                ''',
                'user_id': assignee.id,
                'res_id': submission.id,
                'res_model_id': self.env['ir.model']._get('toner.counter.submission').id,
                'date_deadline': fields.Date.today() + timedelta(days=1)
            }
            
            self.env['mail.activity'].create(activity_vals)
            
        except Exception as e:
            _logger.exception("Error en _create_admin_activity: %s", str(e))
            raise

    def get_summary_data(self):
        """Obtiene datos de resumen para dashboard"""
        self.ensure_one()
        return {
            'equipment_name': self.equipment_id.name.name if self.equipment_id.name.name else 'Sin nombre',
            'client_name': self.client_name,
            'submission_date': self.submission_date.strftime('%d/%m/%Y %H:%M'),
            'copies_total': self.total_copies_period,
            'requires_delivery': self.requiere_entrega_automatica,
            'state_display': dict(self._fields['state'].selection).get(self.state, 'Desconocido'),
            'urgente': self.urgente,
        }


    