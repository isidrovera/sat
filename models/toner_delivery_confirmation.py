import logging
from datetime import timedelta, datetime
from odoo import models, fields, api
import requests
import json
import pytz
import base64
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)

class TonerDeliveryConfirmation(models.Model):
    """Modelo para confirmar entregas de tóner y actualizar stock"""
    _name = 'toner.delivery.confirmation'
    _description = 'Confirmación de Entregas de Tóner'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'delivery_date desc'
    _rec_name = 'display_name'

    # ==========================================
    # CAMPO DISPLAY NAME
    # ==========================================
    
    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
        store=True
    )

    @api.depends('schedule_id', 'delivery_date', 'equipment_id')
    def _compute_display_name(self):
        """Calcula el nombre a mostrar del registro"""
        for record in self:
            try:
                if record.schedule_id:
                    base_name = f"Confirmación {record.schedule_id.secuencia}"
                else:
                    equipment_name = record.equipment_id.name.name if record.equipment_id and record.equipment_id.name.name else 'Sin equipo'
                    base_name = f"Entrega {equipment_name}"
                
                date_str = record.delivery_date.strftime('%d/%m/%Y') if record.delivery_date else 'Sin fecha'
                record.display_name = f"{base_name} - {date_str}"
            except Exception:
                record.display_name = f"Confirmación {record.id or 'Nueva'}"

    # ==========================================
    # CAMPOS BÁSICOS
    # ==========================================
    
    schedule_id = fields.Many2one(
        'toner.delivery.schedule',
        string='Entrega Programada',
        required=True,
        tracking=True,
        help='Entrega programada que se está confirmando'
    )
    
    equipment_id = fields.Many2one(
        'alquiler',
        string='Equipo',
        related='schedule_id.equipment_id',
        store=True,
        readonly=True
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        related='equipment_id.cliente_id',
        store=True,
        readonly=True
    )
    
    secuencia = fields.Char(
        string='Número de Confirmación',
        default='New',
        copy=False,
        required=True,
        readonly=True
    )

    # ==========================================
    # INFORMACIÓN DE ENTREGA
    # ==========================================
    
    delivery_date = fields.Date(
        string='Fecha de Entrega',
        required=True,
        default=fields.Date.today,
        tracking=True,
        help='Fecha real en que se realizó la entrega'
    )
    
    delivery_time = fields.Float(
        string='Hora de Entrega',
        help='Hora en que se realizó la entrega (formato 24h)'
    )
    
    delivered_by_user = fields.Many2one(
        'res.users',
        string='Entregado por',
        default=lambda self: self.env.user,
        required=True,
        tracking=True
    )
    
    received_by_name = fields.Char(
        string='Recibido por',
        required=False,  # ✅ CORRECCIÓN: No obligatorio al crear
        tracking=True,
        help='Nombre completo de quien recibió la entrega'
    )
    
    received_by_position = fields.Char(
        string='Cargo del Receptor',
        help='Cargo o posición de quien recibió'
    )
    
    received_by_dni = fields.Char(
        string='DNI del Receptor',
        help='Documento de identidad de quien recibió'
    )

    # ==========================================
    # CANTIDADES ENTREGADAS
    # ==========================================
    
    toner_black_delivered = fields.Integer(
        string='Tóner Negro Entregado',
        default=0,
        tracking=True,
        help='Cantidad real de tóner negro entregado'
    )
    
    toner_cyan_delivered = fields.Integer(
        string='Tóner Cian Entregado',
        default=0,
        tracking=True,
        help='Cantidad real de tóner cian entregado'
    )
    
    toner_magenta_delivered = fields.Integer(
        string='Tóner Magenta Entregado',
        default=0,
        tracking=True,
        help='Cantidad real de tóner magenta entregado'
    )
    
    toner_yellow_delivered = fields.Integer(
        string='Tóner Amarillo Entregado',
        default=0,
        tracking=True,
        help='Cantidad real de tóner amarillo entregado'
    )

    # Total entregado
    total_delivered = fields.Integer(
        string='Total Entregado',
        compute='_compute_total_delivered',
        store=True,
        help='Total de unidades entregadas'
    )

    # ==========================================
    # COMPARACIÓN CON LO PROGRAMADO
    # ==========================================
    
    # Cantidades programadas (para comparación)
    toner_black_planned = fields.Integer(
        string='Tóner Negro Programado',
        related='schedule_id.toner_black_qty',
        readonly=True
    )
    
    toner_cyan_planned = fields.Integer(
        string='Tóner Cian Programado',
        related='schedule_id.toner_cyan_qty',
        readonly=True
    )
    
    toner_magenta_planned = fields.Integer(
        string='Tóner Magenta Programado',
        related='schedule_id.toner_magenta_qty',
        readonly=True
    )
    
    toner_yellow_planned = fields.Integer(
        string='Tóner Amarillo Programado',
        related='schedule_id.toner_yellow_qty',
        readonly=True
    )

    # Diferencias
    difference_black = fields.Integer(
        string='Diferencia Negro',
        compute='_compute_differences',
        store=True,
        help='Diferencia entre entregado y programado (negro)'
    )
    
    difference_cyan = fields.Integer(
        string='Diferencia Cian',
        compute='_compute_differences',
        store=True,
        help='Diferencia entre entregado y programado (cian)'
    )
    
    difference_magenta = fields.Integer(
        string='Diferencia Magenta',
        compute='_compute_differences',
        store=True,
        help='Diferencia entre entregado y programado (magenta)'
    )
    
    difference_yellow = fields.Integer(
        string='Diferencia Amarillo',
        compute='_compute_differences',
        store=True,
        help='Diferencia entre entregado y programado (amarillo)'
    )

    has_differences = fields.Boolean(
        string='Tiene Diferencias',
        compute='_compute_has_differences',
        store=True,
        help='Indica si hay diferencias entre lo programado y entregado'
    )

    # ==========================================
    # EVIDENCIA DE ENTREGA
    # ==========================================
    
    delivery_photo = fields.Binary(
        string='Foto de Entrega',
        help='Foto de evidencia de la entrega'
    )
    
    delivery_photo_filename = fields.Char(
        string='Nombre Archivo Foto'
    )
    
    client_signature = fields.Binary(
        string='Firma del Cliente',
        help='Firma digital del cliente confirmando recepción'
    )
    
    client_signature_filename = fields.Char(
        string='Nombre Archivo Firma'
    )
    
    delivery_notes = fields.Text(
        string='Observaciones de Entrega',
        help='Observaciones sobre la entrega realizada'
    )

    # ==========================================
    # UBICACIÓN DE ALMACENAMIENTO
    # ==========================================
    
    storage_location = fields.Text(
        string='Ubicación de Almacenamiento',
        help='Dónde el cliente almacenará el tóner entregado'
    )
    
    installation_required = fields.Boolean(
        string='Requiere Instalación',
        help='¿Algún tóner requiere instalación inmediata?'
    )
    
    installation_notes = fields.Text(
        string='Notas de Instalación',
        help='Observaciones sobre instalación de tóner'
    )

    # ==========================================
    # ESTADO Y VALIDACIÓN
    # ==========================================
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmado'),
        ('processed', 'Procesado')
    ], string='Estado', default='draft', tracking=True)
    
    validation_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('validated', 'Validado'),
        ('rejected', 'Rechazado')
    ], string='Estado de Validación', default='pending', tracking=True)
    
    validated_by = fields.Many2one(
        'res.users',
        string='Validado por',
        tracking=True
    )
    
    validation_date = fields.Datetime(
        string='Fecha de Validación',
        tracking=True
    )
    
    validation_notes = fields.Text(
        string='Notas de Validación'
    )

    # ==========================================
    # STOCK ANTES Y DESPUÉS
    # ==========================================
    
    # Stock antes de la entrega
    stock_before_black = fields.Integer(
        string='Stock Anterior Negro',
        help='Stock que tenía el cliente antes de esta entrega'
    )
    
    stock_before_cyan = fields.Integer(
        string='Stock Anterior Cian',
        help='Stock que tenía el cliente antes de esta entrega'
    )
    
    stock_before_magenta = fields.Integer(
        string='Stock Anterior Magenta',
        help='Stock que tenía el cliente antes de esta entrega'
    )
    
    stock_before_yellow = fields.Integer(
        string='Stock Anterior Amarillo',
        help='Stock que tenía el cliente antes de esta entrega'
    )

    # Stock después de la entrega (calculado)
    stock_after_black = fields.Integer(
        string='Stock Resultante Negro',
        compute='_compute_stock_after',
        store=True,
        help='Stock que tendrá el cliente después de esta entrega'
    )
    
    stock_after_cyan = fields.Integer(
        string='Stock Resultante Cian',
        compute='_compute_stock_after',
        store=True,
        help='Stock que tendrá el cliente después de esta entrega'
    )
    
    stock_after_magenta = fields.Integer(
        string='Stock Resultante Magenta',
        compute='_compute_stock_after',
        store=True,
        help='Stock que tendrá el cliente después de esta entrega'
    )
    
    stock_after_yellow = fields.Integer(
        string='Stock Resultante Amarillo',
        compute='_compute_stock_after',
        store=True,
        help='Stock que tendrá el cliente después de esta entrega'
    )

    # ==========================================
    # MÉTODOS COMPUTE
    # ==========================================

    @api.depends('toner_black_delivered', 'toner_cyan_delivered', 
                 'toner_magenta_delivered', 'toner_yellow_delivered')
    def _compute_total_delivered(self):
        """Calcula el total de unidades entregadas"""
        for record in self:
            record.total_delivered = (record.toner_black_delivered + record.toner_cyan_delivered + 
                                    record.toner_magenta_delivered + record.toner_yellow_delivered)

    @api.depends('toner_black_delivered', 'toner_cyan_delivered', 
                 'toner_magenta_delivered', 'toner_yellow_delivered',
                 'toner_black_planned', 'toner_cyan_planned',
                 'toner_magenta_planned', 'toner_yellow_planned')
    def _compute_differences(self):
        """Calcula diferencias entre entregado y programado"""
        for record in self:
            record.difference_black = record.toner_black_delivered - record.toner_black_planned
            record.difference_cyan = record.toner_cyan_delivered - record.toner_cyan_planned
            record.difference_magenta = record.toner_magenta_delivered - record.toner_magenta_planned
            record.difference_yellow = record.toner_yellow_delivered - record.toner_yellow_planned

    @api.depends('difference_black', 'difference_cyan', 'difference_magenta', 'difference_yellow')
    def _compute_has_differences(self):
        """Determina si hay diferencias"""
        for record in self:
            record.has_differences = (record.difference_black != 0 or record.difference_cyan != 0 or
                                    record.difference_magenta != 0 or record.difference_yellow != 0)

    @api.depends('stock_before_black', 'stock_before_cyan', 'stock_before_magenta', 'stock_before_yellow',
                 'toner_black_delivered', 'toner_cyan_delivered', 'toner_magenta_delivered', 'toner_yellow_delivered')
    def _compute_stock_after(self):
        """Calcula el stock resultante después de la entrega"""
        for record in self:
            record.stock_after_black = record.stock_before_black + record.toner_black_delivered
            record.stock_after_cyan = record.stock_before_cyan + record.toner_cyan_delivered
            record.stock_after_magenta = record.stock_before_magenta + record.toner_magenta_delivered
            record.stock_after_yellow = record.stock_before_yellow + record.toner_yellow_delivered

    # ==========================================
    # MÉTODOS CREATE Y OVERRIDE
    # ==========================================

    @api.model
    def create(self, vals):
        """Sobrescribe create para asignar secuencia y capturar stock anterior"""
        if vals.get('secuencia', 'New') == 'New':
            vals['secuencia'] = self.env['ir.sequence'].next_by_code('toner.delivery.confirmation') or 'TDC/001'
        
        # Capturar stock actual del equipo antes de crear
        if vals.get('equipment_id'):
            equipment = self.env['alquiler'].browse(vals['equipment_id'])
            vals.update({
                'stock_before_black': equipment.stock_cliente_toner_black,
                'stock_before_cyan': equipment.stock_cliente_toner_cyan,
                'stock_before_magenta': equipment.stock_cliente_toner_magenta,
                'stock_before_yellow': equipment.stock_cliente_toner_yellow,
            })
        
        result = super(TonerDeliveryConfirmation, self).create(vals)
        
        # Crear nota en el chatter
        try:
            result._create_chatter_note()
        except Exception as e:
            _logger.error("Error creando nota en chatter: %s", str(e))
        
        return result

    def _create_chatter_note(self):
        """Crea nota informativa en el chatter"""
        self.ensure_one()
        
        # Construir lista de tóners entregados
        toners_list = []
        if self.toner_black_delivered > 0:
            toners_list.append(f"Negro: {self.toner_black_delivered}")
        if self.toner_cyan_delivered > 0:
            toners_list.append(f"Cian: {self.toner_cyan_delivered}")
        if self.toner_magenta_delivered > 0:
            toners_list.append(f"Magenta: {self.toner_magenta_delivered}")
        if self.toner_yellow_delivered > 0:
            toners_list.append(f"Amarillo: {self.toner_yellow_delivered}")
        
        toners_text = ", ".join(toners_list) if toners_list else "Ninguno"
        
        # Información de diferencias
        diff_info = ""
        if self.has_differences:
            diff_list = []
            if self.difference_black != 0:
                diff_list.append(f"Negro: {self.difference_black:+d}")
            if self.difference_cyan != 0:
                diff_list.append(f"Cian: {self.difference_cyan:+d}")
            if self.difference_magenta != 0:
                diff_list.append(f"Magenta: {self.difference_magenta:+d}")
            if self.difference_yellow != 0:
                diff_list.append(f"Amarillo: {self.difference_yellow:+d}")
            
            diff_info = f"<br/><br/><b>⚠️ Diferencias vs Programado:</b><br/>{', '.join(diff_list)}"
        
        body = f"""
        ✅ <b>Entrega Confirmada</b><br/><br/>
        
        <b>📋 Información:</b><br/>
        • <b>Programación:</b> {self.schedule_id.secuencia if self.schedule_id else 'Sin programación'}<br/>
        • <b>Equipo:</b> {self.equipment_id.name.name if self.equipment_id.name.name else 'Sin nombre'}<br/>
        • <b>Cliente:</b> {self.partner_id.name if self.partner_id else 'Sin cliente'}<br/><br/>
        
        <b>📅 Detalles de Entrega:</b><br/>
        • <b>Fecha:</b> {self.delivery_date.strftime('%d/%m/%Y') if self.delivery_date else 'No especificada'}<br/>
        • <b>Entregado por:</b> {self.delivered_by_user.name}<br/>
        • <b>Recibido por:</b> {self.received_by_name}<br/>
        • <b>Cargo:</b> {self.received_by_position or 'No especificado'}<br/><br/>
        
        <b>📦 Tóners Entregados:</b><br/>
        {toners_text}<br/>
        <b>Total:</b> {self.total_delivered} unidad(es)<br/>
        {diff_info}
        
        <b>📊 Stock Resultante:</b><br/>
        • Negro: {self.stock_before_black} → {self.stock_after_black}<br/>
        • Cian: {self.stock_before_cyan} → {self.stock_after_cyan}<br/>
        • Magenta: {self.stock_before_magenta} → {self.stock_after_magenta}<br/>
        • Amarillo: {self.stock_before_yellow} → {self.stock_after_yellow}<br/>
        
        {f'<br/><b>📝 Observaciones:</b><br/>{self.delivery_notes}' if self.delivery_notes else ''}
        """
        
        self.message_post(
            body=body,
            message_type='notification'
        )

    # ==========================================
    # MÉTODOS DE ACCIÓN
    # ==========================================

    def action_confirm(self):
        """Confirma la entrega"""
        self.ensure_one()
        
        # Validaciones básicas
        if self.total_delivered == 0:
            raise UserError("Debe entregar al menos una unidad de tóner.")
        
        if not self.received_by_name:
            raise UserError("Debe especificar quién recibió la entrega.")
        
        self.state = 'confirmed'
        self.message_post(
            body="✅ Entrega confirmada - Lista para procesar",
            message_type='notification'
        )
        
        return True

    def action_process(self):
        """Procesa y actualiza stock del equipo"""
        self.ensure_one()
        
        if self.state != 'confirmed':
            raise UserError("Solo se pueden procesar entregas confirmadas.")
        
        # Actualizar stock en el equipo
        self._update_equipment_stock()
        
        # Marcar programación como entregada
        if self.schedule_id:
            self.schedule_id.state = 'delivered'
            self.schedule_id.delivery_confirmation_id = self.id
        
        self.state = 'processed'
        self.message_post(
            body="🔄 Entrega procesada - Stock del equipo actualizado",
            message_type='notification'
        )
        
        return True

    def action_validate(self):
        """Valida la entrega"""
        self.ensure_one()
        
        self.validation_status = 'validated'
        self.validated_by = self.env.user
        self.validation_date = fields.Datetime.now()
        
        self.message_post(
            body=f"✅ Entrega validada por {self.env.user.name}",
            message_type='notification'
        )
        
        return True

    def action_reject(self):
        """Rechaza la entrega"""
        self.ensure_one()
        
        self.validation_status = 'rejected'
        self.validated_by = self.env.user
        self.validation_date = fields.Datetime.now()
        
        self.message_post(
            body=f"❌ Entrega rechazada por {self.env.user.name}",
            message_type='notification'
        )
        
        return True

    def action_reset_to_draft(self):
        """Regresa a estado borrador"""
        self.ensure_one()
        
        if self.state == 'processed':
            raise UserError("No se puede regresar a borrador una entrega ya procesada.")
        
        self.state = 'draft'
        self.validation_status = 'pending'
        self.validated_by = False
        self.validation_date = False
        self.validation_notes = False
        
        self.message_post(
            body="🔄 Entrega regresada a estado borrador",
            message_type='notification'
        )
        
        return True

    def _update_equipment_stock(self):
        """Actualiza el stock de tóner en el equipo"""
        self.ensure_one()
        
        if not self.equipment_id:
            return
        
        # Calcular nuevo stock
        new_stock_black = self.stock_before_black + self.toner_black_delivered
        new_stock_cyan = self.stock_before_cyan + self.toner_cyan_delivered
        new_stock_magenta = self.stock_before_magenta + self.toner_magenta_delivered
        new_stock_yellow = self.stock_before_yellow + self.toner_yellow_delivered
        
        # Actualizar el equipo
        self.equipment_id.write({
            'stock_cliente_toner_black': new_stock_black,
            'stock_cliente_toner_cyan': new_stock_cyan,
            'stock_cliente_toner_magenta': new_stock_magenta,
            'stock_cliente_toner_yellow': new_stock_yellow,
            # ✅ ELIMINAR ESTA LÍNEA: 'fecha_ultima_entrega_toner': self.delivery_date,
        })
        
        _logger.info(
            "Stock actualizado para equipo %s: Negro=%d, Cian=%d, Magenta=%d, Amarillo=%d",
            self.equipment_id.serie or self.equipment_id.id,
            new_stock_black, new_stock_cyan, new_stock_magenta, new_stock_yellow
        )
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

    def action_view_schedule(self):
        """Muestra la programación relacionada"""
        self.ensure_one()
        return {
            'name': 'Programación de Entrega',
            'view_mode': 'form',
            'res_model': 'toner.delivery.schedule',
            'res_id': self.schedule_id.id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    def action_print_delivery_receipt(self):
        """Imprime comprobante de entrega"""
        self.ensure_one()
        # Por ahora solo mostrar mensaje, después se puede implementar el reporte
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Comprobante de entrega {self.secuencia} - Funcionalidad en desarrollo',
                'type': 'info',
                'sticky': False,
            }
        }