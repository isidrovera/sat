# -*- coding: utf-8 -*-

import logging
from datetime import timedelta, datetime, date
from odoo import models, fields, api
import requests
import json
import pytz
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)

class TonerDeliverySchedule(models.Model):
    """Modelo para programar entregas de tóner"""
    _name = 'toner.delivery.schedule'
    _description = 'Programación de Entregas de Tóner'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'delivery_date_planned desc'
    _rec_name = 'display_name'

    # ==========================================
    # CAMPO DISPLAY NAME
    # ==========================================
    
    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
        store=True
    )

    @api.depends('equipment_id', 'delivery_date_planned', 'state')
    def _compute_display_name(self):
        """Calcula el nombre a mostrar del registro"""
        for record in self:
            try:
                equipment_name = record.equipment_id.name.name if record.equipment_id and record.equipment_id.name.name else 'Sin equipo'
                date_str = record.delivery_date_planned.strftime('%d/%m/%Y') if record.delivery_date_planned else 'Sin fecha'
                state_display = dict(record._fields['state'].selection).get(record.state, 'Desconocido')
                
                record.display_name = f"{equipment_name} - {date_str} ({state_display})"
            except Exception:
                record.display_name = f"Entrega Tóner {record.id or 'Nueva'}"

    # ==========================================
    # CAMPOS BÁSICOS
    # ==========================================
    
    equipment_id = fields.Many2one(
        'alquiler',
        string='Equipo',
        required=True,
        tracking=True,
        domain=[('estado_alquiler_id', '=', 'alquilada')],
        help='Equipo para el cual se programa la entrega'
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        related='equipment_id.cliente_id',
        store=True,
        readonly=True
    )
    
    secuencia = fields.Char(
        string='Número de Programación',
        default='New',
        copy=False,
        required=True,
        readonly=True
    )

    # ==========================================
    # FECHAS Y PROGRAMACIÓN
    # ==========================================
    
    delivery_date_planned = fields.Date(
        string='Fecha Programada',
        required=True,
        tracking=True,
        help='Fecha en que se planifica entregar el tóner'
    )
    
    delivery_date_confirmed = fields.Date(
        string='Fecha Confirmada',
        tracking=True,
        help='Fecha confirmada de entrega (puede diferir de la programada)'
    )
    
    delivery_date_actual = fields.Date(
        string='Fecha Real de Entrega',
        tracking=True,
        help='Fecha en que realmente se entregó'
    )

    creation_date = fields.Datetime(
        string='Fecha de Creación',
        default=fields.Datetime.now,
        readonly=True
    )

    # ==========================================
    # CANTIDADES PROGRAMADAS
    # ==========================================
    
    toner_black_qty = fields.Integer(
        string='Cantidad Tóner Negro',
        default=0,
        tracking=True,
        help='Cantidad de tóner negro a entregar'
    )
    
    toner_cyan_qty = fields.Integer(
        string='Cantidad Tóner Cian',
        default=0,
        tracking=True,
        help='Cantidad de tóner cian a entregar'
    )
    
    toner_magenta_qty = fields.Integer(
        string='Cantidad Tóner Magenta',
        default=0,
        tracking=True,
        help='Cantidad de tóner magenta a entregar'
    )
    
    toner_yellow_qty = fields.Integer(
        string='Cantidad Tóner Amarillo',
        default=0,
        tracking=True,
        help='Cantidad de tóner amarillo a entregar'
    )

    # Total de unidades
    total_units = fields.Integer(
        string='Total Unidades',
        compute='_compute_total_units',
        store=True,
        help='Total de unidades de tóner a entregar'
    )

    # ==========================================
    # ORIGEN Y MÉTODO DE CÁLCULO
    # ==========================================
    
    calculation_basis = fields.Selection([
        ('reporte_cliente', 'Reporte de Cliente'),
        ('consumo_automatico', 'Cálculo Automático por Consumo'),
        ('stock_minimo', 'Stock Mínimo Alcanzado'),
        ('solicitud_urgente', 'Solicitud Urgente'),
        ('mantenimiento', 'Mantenimiento Programado'),
        ('manual', 'Creación Manual')
    ], string='Base de Cálculo', required=True, tracking=True,
       help='Método usado para determinar esta entrega')
    
    submission_id = fields.Many2one(
        'toner.counter.submission',
        string='Reporte Origen',
        help='Reporte de contadores que originó esta programación'
    )

    created_by_user = fields.Many2one(
        'res.users',
        string='Creado por',
        default=lambda self: self.env.user,
        readonly=True
    )

    # ==========================================
    # ESTADO Y PRIORIDAD
    # ==========================================
    
    state = fields.Selection([
        ('programado', 'Programado'),
        ('confirmado', 'Confirmado'),
        ('preparando', 'Preparando'),
        ('enviado', 'Enviado'),
        ('entregado', 'Entregado'),
        ('reprogramado', 'Reprogramado'),
        ('cancelado', 'Cancelado')
    ], string='Estado', default='programado', tracking=True)
    
    priority = fields.Selection([
        ('baja', 'Baja'),
        ('normal', 'Normal'),
        ('alta', 'Alta'),
        ('urgente', 'Urgente')
    ], string='Prioridad', default='normal', tracking=True)
    
    urgente = fields.Boolean(
        string='Entrega Urgente',
        tracking=True,
        help='Marcado como entrega urgente'
    )

    # ==========================================
    # INFORMACIÓN DE ENTREGA
    # ==========================================
    
    delivery_method = fields.Selection([
        ('mensajeria', 'Mensajería'),
        ('tecnico', 'Técnico'),
        ('cliente_recoge', 'Cliente Recoge'),
        ('otro', 'Otro')
    ], string='Método de Entrega', default='mensajeria', tracking=True)
    
    delivery_address = fields.Text(
        string='Dirección de Entrega',
        related='equipment_id.direccion',
        help='Dirección donde se realizará la entrega'
    )
    
    contact_person = fields.Char(
        string='Persona de Contacto',
        related='equipment_id.contacto_id',
        help='Persona que recibe la entrega'
    )
    
    contact_phone = fields.Char(
        string='Teléfono de Contacto',
        related='equipment_id.celular',
        help='Teléfono para coordinar entrega'
    )

    # ==========================================
    # RESPONSABLES
    # ==========================================
    
    assigned_user = fields.Many2one(
        'res.users',
        string='Responsable',
        tracking=True,
        help='Usuario responsable de la entrega'
    )
    
    delivery_company = fields.Char(
        string='Empresa de Entrega',
        help='Nombre de la empresa que realizará la entrega'
    )
    
    tracking_number = fields.Char(
        string='Número de Seguimiento',
        help='Número de guía o seguimiento de la entrega'
    )

    # ==========================================
    # CAMPOS DE ANÁLISIS
    # ==========================================
    
    days_until_delivery = fields.Integer(
        string='Días Hasta Entrega',
        compute='_compute_days_until_delivery',
        help='Días restantes hasta la fecha programada'
    )
    
    is_overdue = fields.Boolean(
        string='Entrega Atrasada',
        compute='_compute_is_overdue',
        help='La entrega está atrasada'
    )
    
    delivery_status = fields.Selection([
        ('a_tiempo', 'A Tiempo'),
        ('proximo', 'Próximo (2 días)'),
        ('hoy', 'Hoy'),
        ('atrasado', 'Atrasado')
    ], string='Estado de Entrega', compute='_compute_delivery_status')

    # ==========================================
    # OBSERVACIONES Y NOTAS
    # ==========================================
    
    notes = fields.Text(
        string='Observaciones',
        help='Observaciones adicionales sobre la entrega'
    )
    
    internal_notes = fields.Text(
        string='Notas Internas',
        help='Notas internas del equipo (no visible para cliente)'
    )
    
    cancellation_reason = fields.Text(
        string='Motivo de Cancelación',
        help='Razón por la cual se canceló la entrega'
    )

    # ==========================================
    # RELACIONES
    # ==========================================
    
    confirmation_id = fields.Many2one(
        'toner.delivery.confirmation',
        string='Confirmación de Entrega',
        readonly=True,
        help='Registro de confirmación cuando se entrega'
    )

    # ==========================================
    # MÉTODOS COMPUTE
    # ==========================================

    @api.depends('toner_black_qty', 'toner_cyan_qty', 'toner_magenta_qty', 'toner_yellow_qty')
    def _compute_total_units(self):
        """Calcula el total de unidades a entregar"""
        for record in self:
            record.total_units = (record.toner_black_qty + record.toner_cyan_qty + 
                                record.toner_magenta_qty + record.toner_yellow_qty)

    @api.depends('delivery_date_planned')
    def _compute_days_until_delivery(self):
        """Calcula días hasta la fecha de entrega"""
        today = fields.Date.today()
        for record in self:
            if record.delivery_date_planned:
                delta = record.delivery_date_planned - today
                record.days_until_delivery = delta.days
            else:
                record.days_until_delivery = 0

    @api.depends('delivery_date_planned', 'state')
    def _compute_is_overdue(self):
        """Determina si la entrega está atrasada"""
        today = fields.Date.today()
        for record in self:
            delivery_date = record.delivery_date_planned
            if isinstance(delivery_date, date):
                record.is_overdue = (delivery_date < today and
                                    record.state not in ['entregado', 'cancelado'])
            else:
                record.is_overdue = False

    @api.depends('days_until_delivery', 'is_overdue', 'state')
    def _compute_delivery_status(self):
        """Calcula el estado de la entrega"""
        for record in self:
            if record.state in ['entregado', 'cancelado']:
                record.delivery_status = 'a_tiempo'  # Completado
            elif record.is_overdue:
                record.delivery_status = 'atrasado'
            elif record.days_until_delivery == 0:
                record.delivery_status = 'hoy'
            elif record.days_until_delivery <= 2:
                record.delivery_status = 'proximo'
            else:
                record.delivery_status = 'a_tiempo'

    # ==========================================
    # MÉTODOS CREATE Y OVERRIDE
    # ==========================================

    @api.model
    def create(self, vals):
        """Sobrescribe create para asignar secuencia y configurar prioridad"""
        if vals.get('secuencia', 'New') == 'New':
            vals['secuencia'] = self.env['ir.sequence'].next_by_code('toner.delivery.schedule') or 'TDS/001'
        
        # Configurar prioridad automáticamente
        if 'priority' not in vals:
            if vals.get('urgente'):
                vals['priority'] = 'urgente'
            elif vals.get('calculation_basis') == 'solicitud_urgente':
                vals['priority'] = 'alta'
            elif vals.get('calculation_basis') == 'stock_minimo':
                vals['priority'] = 'alta'
        
        result = super(TonerDeliverySchedule, self).create(vals)
        
        # Crear nota en el chatter
        try:
            result._create_chatter_note()
        except Exception as e:
            _logger.error("Error creando nota en chatter: %s", str(e))
        
        # Crear actividad para el responsable
        try:
            result._create_delivery_activity()
        except Exception as e:
            _logger.error("Error creando actividad de entrega: %s", str(e))
        
        return result

    def _create_chatter_note(self):
        """Crea nota informativa en el chatter"""
        self.ensure_one()
        
        # Construir lista de tóners a entregar
        toners_list = []
        if self.toner_black_qty > 0:
            toners_list.append(f"Negro: {self.toner_black_qty}")
        if self.toner_cyan_qty > 0:
            toners_list.append(f"Cian: {self.toner_cyan_qty}")
        if self.toner_magenta_qty > 0:
            toners_list.append(f"Magenta: {self.toner_magenta_qty}")
        if self.toner_yellow_qty > 0:
            toners_list.append(f"Amarillo: {self.toner_yellow_qty}")
        
        toners_text = ", ".join(toners_list) if toners_list else "Ninguno"
        
        # Información del origen
        origen_text = dict(self._fields['calculation_basis'].selection).get(self.calculation_basis, 'Desconocido')
        if self.submission_id:
            origen_text += f" (Reporte: {self.submission_id.secuencia})"
        
        body = f"""
        🚚 <b>Nueva Entrega Programada</b><br/><br/>
        
        <b>📋 Información del Equipo:</b><br/>
        • <b>Equipo:</b> {self.equipment_id.name.name if self.equipment_id.name.name else 'Sin nombre'}<br/>
        • <b>Serie:</b> {self.equipment_id.serie or 'Sin serie'}<br/>
        • <b>Cliente:</b> {self.partner_id.name if self.partner_id else 'Sin cliente'}<br/><br/>
        
        <b>📅 Programación:</b><br/>
        • <b>Fecha Programada:</b> {self.delivery_date_planned.strftime('%d/%m/%Y') if self.delivery_date_planned else 'No definida'}<br/>
        • <b>Prioridad:</b> {dict(self._fields['priority'].selection).get(self.priority, 'No definida')}<br/>
        • <b>Método:</b> {dict(self._fields['delivery_method'].selection).get(self.delivery_method, 'No definido')}<br/><br/>
        
        <b>📦 Tóners a Entregar:</b><br/>
        {toners_text}<br/>
        <b>Total:</b> {self.total_units} unidad(es)<br/><br/>
        
        <b>🔍 Origen:</b> {origen_text}<br/>
        
        <b>📍 Entrega:</b><br/>
        • <b>Dirección:</b> {self.delivery_address or 'No especificada'}<br/>
        • <b>Contacto:</b> {self.contact_person or 'No especificado'}<br/>
        • <b>Teléfono:</b> {self.contact_phone or 'No especificado'}<br/>
        
        {f'<br/><b>📝 Observaciones:</b><br/>{self.notes}' if self.notes else ''}
        """
        
        self.message_post(
            body=body,
            message_type='notification'
        )

    def _create_delivery_activity(self):
        """Crea actividad para el responsable de la entrega"""
        try:
            # Determinar responsable
            if self.assigned_user:
                assignee = self.assigned_user
            else:
                # Buscar grupo de logística o similar
                logistics_group = self.env.ref('stock.group_stock_user', False)
                if logistics_group and logistics_group.users:
                    assignee = logistics_group.users[0]
                else:
                    assignee = self.env.user
            
            # Configurar fecha límite basada en prioridad
            if self.priority == 'urgente':
                deadline_days = 0  # Hoy
            elif self.priority == 'alta':
                deadline_days = 1  # Mañana
            else:
                deadline_days = 2  # En 2 días
            
            activity_vals = {
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'summary': f'Preparar Entrega Tóner - {self.secuencia}',
                'note': f'''
                    🚚 <b>Entrega de Tóner Programada</b><br/><br/>
                    
                    <b>Cliente:</b> {self.partner_id.name if self.partner_id else 'Sin cliente'}<br/>
                    <b>Equipo:</b> {self.equipment_id.name.name if self.equipment_id.name.name else 'Sin nombre'}<br/>
                    <b>Serie:</b> {self.equipment_id.serie or 'Sin serie'}<br/><br/>
                    
                    <b>Fecha Programada:</b> {self.delivery_date_planned.strftime('%d/%m/%Y') if self.delivery_date_planned else 'No definida'}<br/>
                    <b>Prioridad:</b> {dict(self._fields['priority'].selection).get(self.priority, 'Normal')}<br/><br/>
                    
                    <b>Tóners a Preparar:</b><br/>
                    • Negro: {self.toner_black_qty}<br/>
                    • Cian: {self.toner_cyan_qty}<br/>
                    • Magenta: {self.toner_magenta_qty}<br/>
                    • Amarillo: {self.toner_yellow_qty}<br/>
                    <b>Total:</b> {self.total_units} unidad(es)<br/><br/>
                    
                    <b>Dirección:</b> {self.delivery_address or 'No especificada'}<br/>
                    <b>Contacto:</b> {self.contact_person or 'No especificado'}<br/>
                    <b>Teléfono:</b> {self.contact_phone or 'No especificado'}<br/><br/>
                    
                    Por favor, preparar y coordinar la entrega.
                ''',
                'user_id': assignee.id,
                'res_id': self.id,
                'res_model_id': self.env['ir.model']._get('toner.delivery.schedule').id,
                'date_deadline': fields.Date.today() + timedelta(days=deadline_days)
            }
            
            self.env['mail.activity'].create(activity_vals)
            
        except Exception as e:
            _logger.exception("Error en _create_delivery_activity: %s", str(e))
            raise

    # ==========================================
    # MÉTODOS DE VALIDACIÓN
    # ==========================================

    @api.constrains('toner_black_qty', 'toner_cyan_qty', 'toner_magenta_qty', 'toner_yellow_qty')
    def _check_quantities(self):
        """Valida que las cantidades sean válidas"""
        for record in self:
            if record.toner_black_qty < 0:
                raise ValidationError("La cantidad de tóner negro no puede ser negativa.")
            if record.toner_cyan_qty < 0:
                raise ValidationError("La cantidad de tóner cian no puede ser negativa.")
            if record.toner_magenta_qty < 0:
                raise ValidationError("La cantidad de tóner magenta no puede ser negativa.")
            if record.toner_yellow_qty < 0:
                raise ValidationError("La cantidad de tóner amarillo no puede ser negativa.")
            
            # Verificar que al menos haya una cantidad > 0
            if record.total_units == 0:
                raise ValidationError("Debe especificar al menos una cantidad de tóner a entregar.")

    @api.constrains('delivery_date_planned')
    def _check_delivery_date(self):
        """Valida que la fecha de entrega sea válida"""
        for record in self:
            if record.delivery_date_planned:
                # No permitir fechas muy lejanas (más de 6 meses)
                max_date = fields.Date.today() + timedelta(days=180)
                if record.delivery_date_planned > max_date:
                    raise ValidationError("La fecha de entrega no puede ser superior a 6 meses.")

    @api.constrains('equipment_id', 'toner_cyan_qty', 'toner_magenta_qty', 'toner_yellow_qty')
    def _check_color_toners_for_mono(self):
        """Valida que no se programen tóners color para máquinas monocromáticas"""
        for record in self:
            if (record.equipment_id and 
                record.equipment_id.tipo_maquina_id == 'monocromatica' and
                (record.toner_cyan_qty > 0 or record.toner_magenta_qty > 0 or record.toner_yellow_qty > 0)):
                raise ValidationError("No se pueden programar tóners de color para máquinas monocromáticas.")
    @api.constrains('equipment_id', 'toner_black_qty', 'toner_cyan_qty', 'toner_magenta_qty', 'toner_yellow_qty')
    def _validate_toner_necessity(self):
        """Valida que la entrega sea realmente necesaria basada en stock actual"""
        for record in self:
            if record.calculation_basis == 'manual':
                continue  # No validar entregas manuales
                
            if not record.equipment_id or not record.equipment_id.name:
                continue
                
            equipment = record.equipment_id
            modelo = equipment.name
            
            # Solo validar si la gestión automática está activada
            if not modelo.gestionar_toner_automatico:
                continue
            
            validation_errors = []
            
            # Validar tóner negro
            if record.toner_black_qty > 0:
                if equipment.stock_total_toner_black >= modelo.stock_minimo_black + 1:
                    validation_errors.append(
                        f"Tóner Negro: Stock actual ({equipment.stock_total_toner_black}) supera el mínimo ({modelo.stock_minimo_black})"
                    )
            
            # Validar tóners color para máquinas color
            if equipment.tipo_maquina_id == 'color':
                if record.toner_cyan_qty > 0:
                    if equipment.stock_total_toner_cyan >= (modelo.stock_minimo_cyan or 1) + 1:
                        validation_errors.append(
                            f"Tóner Cian: Stock actual ({equipment.stock_total_toner_cyan}) supera el mínimo ({modelo.stock_minimo_cyan or 1})"
                        )
                
                if record.toner_magenta_qty > 0:
                    if equipment.stock_total_toner_magenta >= (modelo.stock_minimo_magenta or 1) + 1:
                        validation_errors.append(
                            f"Tóner Magenta: Stock actual ({equipment.stock_total_toner_magenta}) supera el mínimo ({modelo.stock_minimo_magenta or 1})"
                        )
                
                if record.toner_yellow_qty > 0:
                    if equipment.stock_total_toner_yellow >= (modelo.stock_minimo_yellow or 1) + 1:
                        validation_errors.append(
                            f"Tóner Amarillo: Stock actual ({equipment.stock_total_toner_yellow}) supera el mínimo ({modelo.stock_minimo_yellow or 1})"
                        )
            
            if validation_errors:
                raise ValidationError(
                    f"La entrega programada para {equipment.serie} puede ser innecesaria:\n\n" + 
                    "\n".join([f"• {error}" for error in validation_errors]) +
                    f"\n\nSi desea proceder de todos modos, cambie la 'Base de Cálculo' a 'Creación Manual'."
                )
    # ==========================================
    # MÉTODOS DE ACCIÓN - CAMBIO DE ESTADO
    # ==========================================

    def action_confirm(self):
        """Confirma la programación de entrega"""
        for record in self:
            if record.state != 'programado':
                raise UserError("Solo se pueden confirmar entregas en estado 'Programado'.")
            
            record.write({
                'state': 'confirmado',
                'delivery_date_confirmed': record.delivery_date_planned
            })
            
            record.message_post(
                body=f"✅ Entrega confirmada por {self.env.user.name}",
                message_type='notification'
            )

    def action_prepare(self):
        """Marca como preparando"""
        for record in self:
            if record.state not in ['confirmado', 'programado']:
                raise UserError("Solo se pueden preparar entregas confirmadas o programadas.")
            
            record.write({'state': 'preparando'})
            
            record.message_post(
                body=f"📦 Preparación iniciada por {self.env.user.name}",
                message_type='notification'
            )

    def action_send(self):
        """Marca como enviado"""
        for record in self:
            if record.state != 'preparando':
                raise UserError("Solo se pueden enviar entregas en preparación.")
            
            record.write({
                'state': 'enviado',
                'delivery_date_actual': fields.Date.today()
            })
            
            record.message_post(
                body=f"🚚 Entrega enviada por {self.env.user.name}",
                message_type='notification'
            )
            
            # Enviar notificación al cliente
            try:
                record.send_shipping_notification()
            except Exception as e:
                _logger.error("Error enviando notificación de envío: %s", str(e))

    def action_deliver(self):
        """Marca como entregado y abre formulario de confirmación"""
        self.ensure_one()
        
        if self.state not in ['enviado', 'preparando']:
            raise UserError("Solo se pueden entregar envíos en estado 'Enviado' o 'Preparando'.")
        
        # Crear confirmación de entrega
        confirmation_vals = {
            'schedule_id': self.id,
            'equipment_id': self.equipment_id.id,
            'delivery_date': fields.Date.today(),
            'toner_black_delivered': self.toner_black_qty,
            'toner_cyan_delivered': self.toner_cyan_qty,
            'toner_magenta_delivered': self.toner_magenta_qty,
            'toner_yellow_delivered': self.toner_yellow_qty,
            'delivered_by_user': self.env.user.id
        }
        
        confirmation = self.env['toner.delivery.confirmation'].create(confirmation_vals)
        self.confirmation_id = confirmation.id
        
        return {
            'name': 'Confirmar Entrega',
            'view_mode': 'form',
            'res_model': 'toner.delivery.confirmation',
            'res_id': confirmation.id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {'default_schedule_id': self.id}
        }

    def action_reschedule(self):
        """Reprograma la entrega"""
        self.ensure_one()
        
        if self.state in ['entregado', 'cancelado']:
            raise UserError("No se pueden reprogramar entregas entregadas o canceladas.")
        
        return {
            'name': 'Reprogramar Entrega',
            'type': 'ir.actions.act_window',
            'res_model': 'toner.delivery.schedule',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'form_view_initial_mode': 'edit',
                'force_detailed_view': True
            }
        }

    def action_cancel(self):
        """Cancela la entrega"""
        for record in self:
            if record.state == 'entregado':
                raise UserError("No se pueden cancelar entregas ya entregadas.")
            
            record.write({'state': 'cancelado'})
            record.message_post(
                body=f"❌ Entrega cancelada por {self.env.user.name}",
                message_type='notification'
            )

    def action_duplicate_delivery(self):
        """Duplica la programación para crear una nueva entrega"""
        self.ensure_one()
        
        new_delivery = self.copy({
            'delivery_date_planned': fields.Date.today() + timedelta(days=7),
            'state': 'programado',
            'delivery_date_confirmed': False,
            'delivery_date_actual': False,
            'confirmation_id': False,
            'tracking_number': False,
            'calculation_basis': 'manual',
            'notes': f"Duplicado desde {self.secuencia}\n\n{self.notes or ''}"
        })
        
        return {
            'name': 'Nueva Entrega',
            'view_mode': 'form',
            'res_model': 'toner.delivery.schedule',
            'res_id': new_delivery.id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    # ==========================================
    # MÉTODOS DE NOTIFICACIÓN
    # ==========================================

    def send_whatsapp_message(self, phone, message):
        """Envía mensaje de WhatsApp usando la API corporativa"""
        try:
            url = 'https://boot.andessolutioncopiers.com/api/send-message'
            data = {
                'to': phone,
                'message': message
            }
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': 'sk_2312cac15276b4a3ca124e66a78fdde6428c626eb7184f26d3fa62037aaae816'
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            _logger.info("WhatsApp API - Código de estado: %s", response.status_code)
            
            try:
                response_json = response.json()
                
                # Validar respuesta exitosa
                if response.status_code == 200 and response_json.get('success'):
                    _logger.info("✅ Mensaje WhatsApp enviado exitosamente a %s", phone)
                    return response_json
                else:
                    error_msg = response_json.get('error', 'Error desconocido')
                    _logger.error("❌ Error en API WhatsApp: %s", error_msg)
                    return {"error": error_msg, "success": False}
                    
            except json.JSONDecodeError as e:
                error_msg = f"La respuesta no contiene un JSON válido: {str(e)}"
                _logger.error(error_msg)
                _logger.error("Respuesta raw: %s", response.text)
                return {"error": error_msg, "success": False}
                
        except requests.exceptions.Timeout:
            error_msg = f"Timeout al enviar mensaje WhatsApp a {phone}"
            _logger.error("❌ %s", error_msg)
            return {"error": error_msg, "success": False}
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Error de red en WhatsApp API: {str(e)}"
            _logger.exception("❌ %s", error_msg)
            return {"error": error_msg, "success": False}
            
        except Exception as e:
            _logger.exception("❌ Error inesperado enviando mensaje WhatsApp: %s", str(e))
            return {"error": str(e), "success": False}

    def send_shipping_notification(self):
        """Envía notificación de envío al cliente"""
        self.ensure_one()
        
        # Limpiar número de teléfono
        phone = self.contact_phone
        if not phone:
            _logger.warning("No hay teléfono para notificar envío - Entrega: %s", self.secuencia)
            return False
        
        # Limpiar número
        phone = phone.replace('+', '').replace(' ', '').replace('-', '')
        phone = ''.join(filter(str.isdigit, phone))
        
        if not phone.startswith('51') and len(phone) == 9:
            phone = '51' + phone
        
        try:
            # Construir lista de tóners
            toners_list = []
            if self.toner_black_qty > 0:
                toners_list.append(f"{self.toner_black_qty} tóner(es) negro")
            if self.toner_cyan_qty > 0:
                toners_list.append(f"{self.toner_cyan_qty} tóner(es) cian")
            if self.toner_magenta_qty > 0:
                toners_list.append(f"{self.toner_magenta_qty} tóner(es) magenta")
            if self.toner_yellow_qty > 0:
                toners_list.append(f"{self.toner_yellow_qty} tóner(es) amarillo")
            
            toners_text = ", ".join(toners_list) if toners_list else "tóner"
            
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

            # Construir mensaje
            equipment_name = self.equipment_id.name.name if self.equipment_id and self.equipment_id.name.name else 'su equipo'
            
            message = (
                f"*🏢 Soporte*\n\n"
                f"{saludo}!\n\n"
                f"Le informamos que su pedido de tóner ha sido enviado:\n\n"
                f"📋 *Orden:* {self.secuencia}\n"
                f"🖨️ *Equipo:* {equipment_name}\n"
                f"📦 *Contenido:* {toners_text}\n"
                f"📅 *Fecha de envío:* {fields.Date.today().strftime('%d/%m/%Y')}\n"
                f"📍 *Dirección:* {self.delivery_address or 'Dirección registrada'}\n"
            )
            
            if self.tracking_number:
                message += f"🔍 *Número de seguimiento:* {self.tracking_number}\n"
            
            if self.delivery_method == 'mensajeria':
                message += f"\n📞 *El mensajero se comunicará con usted para coordinar la entrega.*\n"
            elif self.delivery_method == 'tecnico':
                message += f"\n👨‍🔧 *Nuestro técnico se comunicará para coordinar la entrega.*\n"
            
            message += (
                f"\nSi tiene alguna consulta, no dude en contactarnos.\n\n"
                
            )

            # Enviar mensaje
            response = self.send_whatsapp_message(phone, message)
            
            if response and not response.get('error'):
                self.message_post(
                    body=f"✅ Notificación de envío enviada a {phone}",
                    message_type='notification'
                )
                _logger.info("WhatsApp de envío enviado exitosamente - Entrega: %s, Teléfono: %s", 
                           self.secuencia, phone)
                return True
            else:
                error_msg = response.get('error', 'Error desconocido') if response else 'Sin respuesta'
                self.message_post(
                    body=f"❌ Error enviando notificación a {phone}: {error_msg}",
                    message_type='notification'
                )
                _logger.error("Error enviando WhatsApp - Entrega: %s, Error: %s", self.secuencia, error_msg)
                return False
                
        except Exception as e:
            _logger.exception("Error en send_shipping_notification - Entrega: %s", self.secuencia)
            self.message_post(
                body=f"❌ Excepción enviando notificación: {str(e)}",
                message_type='notification'
            )
            return False

    def send_delivery_reminder(self):
        """Envía recordatorio de entrega próxima"""
        self.ensure_one()
        
        phone = self.contact_phone
        if not phone:
            return False
        
        # Limpiar número
        phone = phone.replace('+', '').replace(' ', '').replace('-', '')
        phone = ''.join(filter(str.isdigit, phone))
        
        if not phone.startswith('51') and len(phone) == 9:
            phone = '51' + phone
        
        try:
            # Construir mensaje de recordatorio
            equipment_name = self.equipment_id.name.name if self.equipment_id and self.equipment_id.name.name else 'su equipo'
            
            message = (
                f"*🏢 Soporte*\n\n"
                f"👋 Recordatorio de entrega de tóner:\n\n"
                f"📋 *Orden:* {self.secuencia}\n"
                f"🖨️ *Equipo:* {equipment_name}\n"
                f"📅 *Fecha programada:* {self.delivery_date_planned.strftime('%d/%m/%Y')}\n"
                f"📍 *Dirección:* {self.delivery_address or 'Dirección registrada'}\n\n"
                f"Por favor, asegúrese de que haya alguien disponible para recibir la entrega.\n\n"
                f"Si necesita reprogramar, contáctenos:\n"
               
            )

            response = self.send_whatsapp_message(phone, message)
            
            if response and not response.get('error'):
                self.message_post(
                    body=f"🔔 Recordatorio enviado a {phone}",
                    message_type='notification'
                )
                return True
            else:
                return False
                
        except Exception as e:
            _logger.exception("Error enviando recordatorio - Entrega: %s", self.secuencia)
            return False

    # ==========================================
    # MÉTODOS DE REPORTE Y ANÁLISIS
    # ==========================================

    @api.model
    def get_pending_deliveries_count(self):
        """Obtiene contador de entregas pendientes"""
        return self.search_count([
            ('state', 'in', ['programado', 'confirmado', 'preparando', 'enviado']),
            ('delivery_date_planned', '<=', fields.Date.today() + timedelta(days=7))
        ])

    @api.model
    def get_overdue_deliveries(self):
        """Obtiene entregas atrasadas"""
        return self.search([
            ('is_overdue', '=', True),
            ('state', 'not in', ['entregado', 'cancelado'])
        ])

    @api.model
    def get_today_deliveries(self):
        """Obtiene entregas programadas para hoy"""
        return self.search([
            ('delivery_date_planned', '=', fields.Date.today()),
            ('state', 'not in', ['entregado', 'cancelado'])
        ])

    def get_delivery_summary(self):
        """Obtiene resumen de la entrega"""
        self.ensure_one()
        
        # Estado visual
        status_icons = {
            'programado': '📅',
            'confirmado': '✅',
            'preparando': '📦',
            'enviado': '🚚',
            'entregado': '✅',
            'reprogramado': '🔄',
            'cancelado': '❌'
        }
        
        priority_icons = {
            'baja': '🟢',
            'normal': '🟡',
            'alta': '🟠',
            'urgente': '🔴'
        }
        
        return {
            'secuencia': self.secuencia,
            'equipment_name': self.equipment_id.name.name if self.equipment_id.name.name else 'Sin nombre',
            'client_name': self.partner_id.name if self.partner_id else 'Sin cliente',
            'delivery_date': self.delivery_date_planned.strftime('%d/%m/%Y') if self.delivery_date_planned else 'Sin fecha',
            'total_units': self.total_units,
            'state_display': f"{status_icons.get(self.state, '❓')} {dict(self._fields['state'].selection).get(self.state, 'Desconocido')}",
            'priority_display': f"{priority_icons.get(self.priority, '❓')} {dict(self._fields['priority'].selection).get(self.priority, 'Normal')}",
            'days_until': self.days_until_delivery,
            'is_overdue': self.is_overdue,
            'urgente': self.urgente,
        }

    # ==========================================
    # MÉTODOS AUTOMÁTICOS Y CRON
    # ==========================================

    @api.model
    def send_daily_delivery_reminders(self):
        """Envía recordatorios diarios de entregas próximas (para cron)"""
        tomorrow = fields.Date.today() + timedelta(days=1)
        
        # Buscar entregas para mañana
        deliveries = self.search([
            ('delivery_date_planned', '=', tomorrow),
            ('state', 'in', ['confirmado', 'preparando']),
        ])
        
        sent_count = 0
        for delivery in deliveries:
            try:
                if delivery.send_delivery_reminder():
                    sent_count += 1
            except Exception as e:
                _logger.error("Error enviando recordatorio para entrega %s: %s", delivery.secuencia, str(e))
        
        _logger.info("Recordatorios de entrega enviados: %d de %d", sent_count, len(deliveries))
        return sent_count

    @api.model
    def auto_create_delivery_from_low_stock(self):
        """Crea entregas automáticas basadas en stock bajo (para cron)"""
        # Buscar equipos con stock bajo
        equipos_bajo_stock = self.env['alquiler'].search([
            ('estado_alquiler_id', '=', 'alquilada'),
            ('estado_stock_toner', 'in', ['critico', 'bajo']),
            ('name.gestionar_toner_automatico', '=', True)
        ])
        
        created_count = 0
        for equipo in equipos_bajo_stock:
            # Verificar si ya tiene una entrega programada pendiente
            existing_delivery = self.search([
                ('equipment_id', '=', equipo.id),
                ('state', 'in', ['programado', 'confirmado', 'preparando', 'enviado']),
            ], limit=1)
            
            if existing_delivery:
                continue  # Ya tiene entrega pendiente
            
            try:
                # Crear entrega automática
                delivery_vals = self._prepare_auto_delivery_values(equipo)
                if delivery_vals:
                    self.create(delivery_vals)
                    created_count += 1
            except Exception as e:
                _logger.error("Error creando entrega automática para equipo %s: %s", equipo.serie, str(e))
        
        _logger.info("Entregas automáticas creadas: %d", created_count)
        return created_count

    @api.model
    def _prepare_auto_delivery_values(self, equipo):
        """Prepara valores para entrega automática"""
        if not equipo.name:
            return False
        
        modelo = equipo.name
        
        # Calcular fecha de entrega
        delivery_date = fields.Date.today() + timedelta(days=(modelo.tiempo_entrega_dias or 2))
        
        # Determinar cantidades necesarias
        qty_black = max(1, (modelo.stock_minimo_black or 1) - equipo.stock_total_toner_black + 1) if equipo.stock_total_toner_black <= (modelo.stock_minimo_black or 1) else 0
        qty_cyan = max(1, (modelo.stock_minimo_cyan or 1) - equipo.stock_total_toner_cyan + 1) if equipo.tipo_maquina_id == 'color' and equipo.stock_total_toner_cyan <= (modelo.stock_minimo_cyan or 1) else 0
        qty_magenta = max(1, (modelo.stock_minimo_magenta or 1) - equipo.stock_total_toner_magenta + 1) if equipo.tipo_maquina_id == 'color' and equipo.stock_total_toner_magenta <= (modelo.stock_minimo_magenta or 1) else 0
        qty_yellow = max(1, (modelo.stock_minimo_yellow or 1) - equipo.stock_total_toner_yellow + 1) if equipo.tipo_maquina_id == 'color' and equipo.stock_total_toner_yellow <= (modelo.stock_minimo_yellow or 1) else 0
        
        # Verificar que haya algo que entregar
        if qty_black + qty_cyan + qty_magenta + qty_yellow == 0:
            return False
        
        return {
            'equipment_id': equipo.id,
            'delivery_date_planned': delivery_date,
            'toner_black_qty': qty_black,
            'toner_cyan_qty': qty_cyan,
            'toner_magenta_qty': qty_magenta,
            'toner_yellow_qty': qty_yellow,
            'calculation_basis': 'stock_minimo',
            'priority': 'alta' if equipo.estado_stock_toner == 'critico' else 'normal',
            'notes': f"Entrega automática generada por stock {equipo.estado_stock_toner}"
        }


    def action_view_equipment(self):
        """Muestra el equipo relacionado"""
        self.ensure_one()
        return {
            'name': 'Equipo',
            'view_mode': 'form',
            'res_model': 'alquiler',
            'res_id': self.equipment_id.id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    def action_view_submission(self):
        """Muestra el reporte origen relacionado"""
        self.ensure_one()
        return {
            'name': 'Reporte de Tóner',
            'view_mode': 'form',
            'res_model': 'toner.counter.submission',
            'res_id': self.submission_id.id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    def action_view_confirmation(self):
        """Muestra la confirmación de entrega"""
        self.ensure_one()
        return {
            'name': 'Confirmación de Entrega',
            'view_mode': 'form',
            'res_model': 'toner.delivery.confirmation',
            'res_id': self.confirmation_id.id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }