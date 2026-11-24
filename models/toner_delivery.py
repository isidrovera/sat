# -*- coding: utf-8 -*-
"""Programación de entregas de tóner — archivo completo Odoo 19.

Se conserva el modelo y su API actual. No crea módulos nuevos.
El único origen de movimientos positivos de stock es la RECEPCIÓN
confirmada, a través de toner.delivery.confirmation y la integración
stock de toner.delivery.schedule.
"""

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

    @api.model
    def _toner_tracking_only_enabled(self):
        """Una sola notificación inicial cuando el portal esté habilitado.

        Flag compartido con toner.counter.submission. No se fuerza a True
        mientras no exista la ruta pública segura de seguimiento.
        """
        value = self.env['ir.config_parameter'].sudo().get_param(
            'sat.toner_tracking_enabled', 'False'
        )
        return str(value).strip().lower() in ('true', '1', 'yes', 'on')

    @api.model
    def _clean_delivery_phone(self, value):
        value = ''.join(char for char in str(value or '') if char.isdigit())
        return ('51' + value) if len(value) == 9 and not value.startswith('51') else value


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

    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Crea una o varias programaciones de entrega de tóner.

        Compatible con Odoo 19.

        Mantiene:
        - Generación automática de secuencia.
        - Asignación automática de prioridad.
        - Nota informativa en el chatter.
        - Actividad para el responsable.
        """

        # Compatibilidad defensiva si se recibe un diccionario.
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        prepared_vals_list = []

        for vals in vals_list:
            vals = dict(vals)

            # Generar secuencia cuando no fue proporcionada.
            if vals.get("secuencia", "New") == "New":
                vals["secuencia"] = (
                    self.env["ir.sequence"].next_by_code(
                        "toner.delivery.schedule"
                    )
                    or "TDS/001"
                )

            # Configurar prioridad automáticamente.
            if "priority" not in vals:
                if vals.get("urgente"):
                    vals["priority"] = "urgente"

                elif vals.get("calculation_basis") == "solicitud_urgente":
                    vals["priority"] = "alta"

                elif vals.get("calculation_basis") == "stock_minimo":
                    vals["priority"] = "alta"

            prepared_vals_list.append(vals)

        # Crear todos los registros mediante el ORM de Odoo 19.
        records = super(
            TonerDeliverySchedule, self
        ).create(prepared_vals_list)

        # Ejecutar las acciones posteriores por cada entrega.
        for record in records:

            # Crear nota informativa en el chatter.
            try:
                record._create_chatter_note()

            except Exception:
                _logger.exception(
                    "[TONER][DELIVERY][CREATE] "
                    "Error creando nota en chatter. "
                    "Entrega ID=%s",
                    record.id,
                )

            # Crear actividad para el responsable.
            try:
                record._create_delivery_activity()

            except Exception:
                _logger.exception(
                    "[TONER][DELIVERY][CREATE] "
                    "Error creando actividad de entrega. "
                    "Entrega ID=%s",
                    record.id,
                )

        _logger.info(
            "[TONER][DELIVERY][CREATE] "
            "Programaciones creadas correctamente: %s",
            records.ids,
        )

        return records


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
        """El valor real de tipo_maquina_id en alquiler es 'color'."""
        for record in self:
            if (record.equipment_id
                    and record.equipment_id.tipo_maquina_id != 'color'
                    and any((record.toner_cyan_qty, record.toner_magenta_qty,
                             record.toner_yellow_qty))):
                raise ValidationError(
                    'No se pueden programar tóneres de color para una máquina B/N.'
                )

    @api.constrains('equipment_id', 'calculation_basis', 'submission_id',
                    'toner_black_qty', 'toner_cyan_qty', 'toner_magenta_qty', 'toner_yellow_qty')
    def _validate_toner_necessity(self):
        """Impide generar despachos preventivos DIRECTOS con respaldo suficiente.

        El control de necesidad comercial ya se realiza al aprobar una solicitud
        y puede contener excepciones (falla, provincia, stock adicional). No
        corresponde reabrir esa evaluación al crear el despacho aprobado.
        """
        for record in self:
            if not record.equipment_id or not record.equipment_id.name:
                continue
            if record.submission_id:
                if record.submission_id.equipment_id != record.equipment_id:
                    raise ValidationError(
                        'La solicitud aprobada y la entrega deben pertenecer al mismo equipo.'
                    )
                continue
            if record.calculation_basis != 'stock_minimo':
                continue
            # Política general: stock mínimo de 1 repuesto disponible. Llegar
            # a 1 NO crea una nueva entrega; la reposición se evalúa al llegar
            # a 0, y debe pasar por la solicitud y aprobación habituales.
            raise ValidationError(
                'No está permitido crear directamente un despacho por stock mínimo '
                'sin una solicitud aprobada. Genere primero la solicitud de tóner '
                'mediante el motor seleccionado (Odoo o n8n + IA).'
            )

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
        """Despacha sin dar por recibidos los consumibles ni enviar mensajes dobles."""
        for record in self:
            if record.state != 'preparando':
                raise UserError("Solo se pueden enviar entregas en preparación.")
            record.write({'state': 'enviado'})
            record.message_post(
                body='🚚 Entrega enviada por %s' % self.env.user.name,
                message_type='notification', subtype_xmlid='mail.mt_note'
            )
            # Modo enlace único: la notificación inicial sale de la solicitud,
            # y el portal muestra el estado actualizado al abrir ese enlace.
            if not record._toner_tracking_only_enabled():
                try:
                    record.send_shipping_notification()
                except Exception:
                    _logger.exception('Error notificando despacho %s', record.secuencia)

    def action_deliver(self):
        """Abre UNA confirmación editable; todavía NO registra stock."""
        self.ensure_one()
        if self.state not in ('enviado', 'preparando'):
            raise UserError(
                "Solo se pueden confirmar envíos en estado 'Enviado' o 'Preparando'."
            )
        if self.confirmation_id and self.confirmation_id.exists():
            confirmation = self.confirmation_id
            if confirmation.state == 'processed':
                raise UserError('Esta entrega ya fue recibida y contabilizada.')
        else:
            # Las cantidades programadas son una SUGERENCIA editable: solo las
            # entregadas y confirmadas se contabilizan en el kardex.
            confirmation = self.env['toner.delivery.confirmation'].create({
                'schedule_id': self.id,
                'delivery_date': fields.Date.today(),
                'toner_black_delivered': self.toner_black_qty,
                'toner_cyan_delivered': self.toner_cyan_qty,
                'toner_magenta_delivered': self.toner_magenta_qty,
                'toner_yellow_delivered': self.toner_yellow_qty,
                'delivered_by_user': self.env.user.id,
            })
            self.write({'confirmation_id': confirmation.id})
        return {
            'name': 'Confirmar Entrega',
            'view_mode': 'form',
            'res_model': 'toner.delivery.confirmation',
            'res_id': confirmation.id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {'default_schedule_id': self.id},
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
        """Envía mensaje de WhatsApp usando la API corporativa desde parámetros del sistema."""
        try:
            ICP = self.env["ir.config_parameter"].sudo()

            base_url = ICP.get_param("sat.whatsapp_gateway_base_url")
            api_key = ICP.get_param("sat.whatsapp_gateway_api_key")

            if not base_url:
                error_msg = "Falta configurar el parámetro sat.whatsapp_gateway_base_url"
                _logger.error("❌ %s", error_msg)
                return {
                    "error": error_msg,
                    "success": False,
                }

            if not api_key:
                error_msg = "Falta configurar el parámetro sat.whatsapp_gateway_api_key"
                _logger.error("❌ %s", error_msg)
                return {
                    "error": error_msg,
                    "success": False,
                }

            base_url = base_url.rstrip("/")
            url = f"{base_url}/api/send-message"

            data = {
                "to": phone,
                "message": message,
            }

            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
            }

            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=30,
            )

            _logger.info(
                "WhatsApp API - Código de estado: %s",
                response.status_code,
            )

            try:
                response_json = response.json()

                if response.status_code == 200 and response_json.get("success"):
                    _logger.info(
                        "✅ Mensaje WhatsApp enviado exitosamente a %s",
                        phone,
                    )
                    return response_json

                error_msg = response_json.get("error", "Error desconocido")
                _logger.error("❌ Error en API WhatsApp: %s", error_msg)

                return {
                    "error": error_msg,
                    "success": False,
                    "status_code": response.status_code,
                }

            except json.JSONDecodeError as e:
                error_msg = f"La respuesta no contiene un JSON válido: {str(e)}"
                _logger.error(error_msg)
                _logger.error("Respuesta raw: %s", response.text)

                return {
                    "error": error_msg,
                    "success": False,
                    "status_code": response.status_code,
                }

        except requests.exceptions.Timeout:
            error_msg = f"Timeout al enviar mensaje WhatsApp a {phone}"
            _logger.error("❌ %s", error_msg)

            return {
                "error": error_msg,
                "success": False,
            }

        except requests.exceptions.RequestException as e:
            error_msg = f"Error de red en WhatsApp API: {str(e)}"
            _logger.exception("❌ %s", error_msg)

            return {
                "error": error_msg,
                "success": False,
            }

        except Exception as e:
            _logger.exception(
                "❌ Error inesperado enviando mensaje WhatsApp: %s",
                str(e),
            )

            return {
                "error": str(e),
                "success": False,
            }
    def _get_delivery_customer_recipient(self):
        """Nombre del destinatario para mensajes de logística (no el remitente).

        Priorizamos la persona de contacto del equipo, porque los avisos se envían
        a ese teléfono. Si falta, usamos al solicitante y luego al cliente.
        """
        self.ensure_one()
        contact = (self.contact_person or '').strip()
        requester = (
            (self.submission_id.client_name or '').strip()
            if self.submission_id else ''
        )
        company = (self.partner_id.name or '').strip() if self.partner_id else ''
        return contact or requester or company or 'cliente', company

    def send_shipping_notification(self):
        """Aviso de despacho solo en modo legado; nunca duplicar enlace único."""
        self.ensure_one()
        if self._toner_tracking_only_enabled():
            return False
        phone = self._clean_delivery_phone(self.contact_phone)
        if not phone:
            return False
        recipient, company = self._get_delivery_customer_recipient()
        toners = [
            '%s %s' % (getattr(self, 'toner_%s_qty' % c), label)
            for c, label in (
                ('black', 'negro'), ('cyan', 'cian'),
                ('magenta', 'magenta'), ('yellow', 'amarillo')
            ) if getattr(self, 'toner_%s_qty' % c) > 0
        ]
        message = (
            'Estimado/a *%s*,\n\n'
            'Su entrega de tóner *%s* ha sido despachada.\n'
            '%s'
            'Equipo: %s\nContenido: %s\n'
        ) % (
            recipient,
            self.secuencia,
            'Empresa: %s\n' % company if company else '',
            self.equipment_id.name.name if self.equipment_id.name else 'Equipo',
            ', '.join(toners),
        )
        if self.tracking_number:
            message += 'Guía: %s\n' % self.tracking_number        
        response = self.send_whatsapp_message(phone, message)
        return bool(response and response.get('success') and not response.get('error'))

    def send_delivery_reminder(self):
        """Aviso de programación solo en modo legado, sin enlaces duplicados."""
        self.ensure_one()
        if self._toner_tracking_only_enabled():
            return False
        phone = self._clean_delivery_phone(self.contact_phone)
        if not phone:
            return False
        recipient, company = self._get_delivery_customer_recipient()
        message = (
            'Estimado/a *%s*,\n\n'
            'Le recordamos que la entrega *%s* está programada para *%s*.\n'
            '%s'
            'Equipo: %s\n\n'            
        ) % (
            recipient,
            self.secuencia,
            self.delivery_date_planned or 'fecha pendiente',
            'Empresa: %s\n' % company if company else '',
            self.equipment_id.name.name if self.equipment_id.name else 'Equipo',
        )
        response = self.send_whatsapp_message(phone, message)
        return bool(response and response.get('success') and not response.get('error'))

    @api.model
    def get_pending_deliveries_count(self):
        """Obtiene contador de entregas pendientes"""
        return self.search_count([
            ('state', 'in', ['programado', 'confirmado', 'preparando', 'enviado']),
            ('delivery_date_planned', '<=', fields.Date.today() + timedelta(days=7))
        ])

    @api.model
    def get_overdue_deliveries(self):
        """Buscar por fecha almacenada, no por campo compute no almacenado."""
        return self.search([
            ('delivery_date_planned', '<', fields.Date.today()),
            ('state', 'not in', ['entregado', 'cancelado']),
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
        """Cron legado: sin mensajes repetidos si seguimiento está activado."""
        if self._toner_tracking_only_enabled():
            return 0
        tomorrow = fields.Date.today() + timedelta(days=1)
        deliveries = self.search([
            ('delivery_date_planned', '=', tomorrow),
            ('state', 'in', ['confirmado', 'preparando']),
        ])
        sent_count = 0
        for delivery in deliveries:
            try:
                if delivery.send_delivery_reminder():
                    sent_count += 1
            except Exception:
                _logger.exception('Error recordatorio entrega %s', delivery.secuencia)
        return sent_count

    @api.model
    def auto_create_delivery_from_low_stock(self):
        """Desactiva SOLO el atajo inseguro de despacho automático antiguo.

        La reposición automática sigue entrando por toner.monitoring.event y
        toner.counter.submission, conservando evaluación/gerencia. El cron
        anterior intentaba crear entregas directamente, usando un campo
        computado no almacenado y sin respetar solicitudes ni aprobación.
        Nunca se debe registrar una entrega para un cliente sin autorización.
        """
        _logger.info(
            '[TONER] Cron legado de despacho directo omitido: '
            'la reposición debe pasar por solicitud y aprobación.'
        )
        return 0

    @api.model
    def _prepare_auto_delivery_values(self, equipo):
        """Prepara una propuesta NO ejecutable para el antiguo cron.

        Se conserva la firma pública por compatibilidad, pero nunca crea
        despachos sin el proceso de solicitud. El mínimo físico es 1 unidad
        de respaldo; no se solicita si permanece al menos una.
        """
        if not equipo or equipo.estado_alquiler_id != 'alquilada' or not equipo.name:
            return False
        if 'get_current_stock' not in dir(self.env['toner.stock.movement']):
            return False
        Movement = self.env['toner.stock.movement'].sudo()
        qty = {}
        for color in ('black', 'cyan', 'magenta', 'yellow'):
            if color != 'black' and equipo.tipo_maquina_id != 'color':
                continue
            available = Movement.get_current_stock(equipo, color)
            if available <= 0:
                qty['toner_%s_qty' % color] = 1
        if not qty:
            return False
        days = int(getattr(equipo.name, 'tiempo_entrega_dias', 2) or 2)
        vals = {
            'equipment_id': equipo.id,
            'delivery_date_planned': fields.Date.today() + timedelta(days=max(days, 0)),
            'calculation_basis': 'stock_minimo',
            'notes': 'Propuesta preliminar: requiere solicitud y aprobación.',
        }
        vals.update(qty)
        return vals

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