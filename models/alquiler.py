from odoo import _, models, fields, api
from dateutil.relativedelta import relativedelta
from datetime import datetime
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)
import xlwt
from io import BytesIO
import base64
import re
import qrcode
import io
from odoo.exceptions import ValidationError
from urllib.parse import urlencode
import uuid



class UnidadAlquiler(models.Model):

    _name = 'alquiler'
    _description = 'Maquina en alquiler'

    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Many2one('modelo.maquina', string='Modelo',
                           required=True
                           )
    
    tipo_maquina = fields.Char(related='name.tipo_maquina_id.name', readonly=True, store=True,
                               string='Tipo de maquina')
    tipo_maquina_id = fields.Selection([('color', 'Color'), ('monocromatica', 'Monocromatica')],
                                       string="Tipo de Equipo", related='name.tipo_id')

    precio_venta = fields.Float(string='Precio de venta', tracking=True)
    precio_compra = fields.Float(string='Precio de compra', tracking=True)

    @api.model
    def _default_currency_id(self):
        value = self.env['res.currency'].search(
            [('name', '=', 'USD')], limit=1)
        return value and value.id or False
    currency_id = fields.Many2one(
        'res.currency', string='Currency', default=_default_currency_id)
    factura_compra = fields.Char(string='Factura de compra #', tracking=True)
    fecha_compra = fields.Date(string='Fecha de compra', tracking=True)
    factura_venta = fields.Char(string='Factura de venta', tracking=True)
    fecha_venta = fields.Date(string='Fecha de venta', tracking=True)
    garantia = fields.Html(string="Descripción de garantia")
    contometro_venta = fields.Integer(
        string='Contometro de venta', tracking=True)

    control_mantenimiento = fields.Boolean(string="Mantenimiento mensual", default=True)
    

    marca = fields.Char(related='name.marca_id.name', readonly=True, store=True, string='Marca')

    serie = fields.Char(string='Serie', required=True, tracking=True)

    @api.constrains('serie')
    def unique_field_serie(self):
        for item in self:
            # Busca otros registros con la misma serie y un ID diferente
            items = self.search(
                [('serie', '=', item.serie), ('id', '!=', item.id)]
            )
            if items:  # Si encuentra al menos un registro duplicado
                raise ValidationError("La serie ingresada ya está en uso. Por favor, ingrese una serie única.")

    contacto_id = fields.Char(string='Contacto', tracking=True)
    celular = fields.Char(string='Celular', tracking=True)
    correo_ = fields.Char(string='Correo', tracking=True)    
    cargo = fields.Char(string='Cargo', tracking=True)
    ubicacion_instalacion  = fields.Char(string="Área de instalacion")
    observaciones  = fields.Html(string="Observaciones")
    direccion = fields.Text(string='Dirección y Distrito', tracking=True)
    ubicacion_id = fields.Selection([('primer_piso', 'Primer piso'), ('tercer_piso', 'Tercer piso'), ('segundo_local', 'Segundo local'), ('covida', 'Covida')],
                                    default='primer_piso', tracking=True,
                                    )
    estado_alquiler_id = fields.Selection([('sin_revisar', 'Sin revisar'), ('revisada', 'Revisada'), ('lista', 'Lista'), ('alquilada', 'Alquilada'), ('con_problemas', 'Con Problemas'), ('partes', 'De Partes'), ('externo', 'Externo'), ('vendida', 'Vendida')],
                                          string='Estado de Maquina',
                                          default='sin_revisar', tracking=True)

    cliente_id = fields.Many2one(
        'res.partner', string='Cliente', required=False, tracking=True)

    ticket_count = fields.Integer(string='Ticket Count', compute='_compute_counts')

    @api.depends()
    def _compute_counts(self):
        """Compute all counts in a single method to improve performance"""
        for record in self:
            # Tickets count
            record.ticket_count = self.env['ticket.alquiler'].search_count([
                ('product_alquiler', '=', record.id)
            ])
            
            # Pedidos count
            pedidos = self.env['sale.order'].search_count([
                ('equipo_id', '=', record.id),
                ('estado_entrega', '=', 'sin_entregar')
            ])
            record.pedidos_count = pedidos
            record.has_pending_orders = bool(pedidos)
            
            # Repuestos count
            record.repuestos_count = self.env['repuestos.alquiler'].search_count([
                ('modelo_id', '=', record.id)
            ])

    def get_ticket(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tickets',
            'view_mode': 'list,form',
            'res_model': 'ticket.alquiler',
            'domain': [('product_alquiler', '=', self.id)],
            'context': "{'create': True}"
        }
    pedidos_count = fields.Integer(compute='compute_count_pedidos')

    has_pending_orders = fields.Boolean(compute='compute_count_pedidos', store=False)

    def compute_count_pedidos(self):
        for record in self:
            pedidos_count = self.env['sale.order'].search_count(
                [('equipo_id', '=', record.id), ('estado_entrega', '=', 'sin_entregar')])
            record.pedidos_count = pedidos_count
            record.has_pending_orders = bool(pedidos_count)

    def get_pedidos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pedidos',
            'view_mode': 'list,form',
            'res_model': 'sale.order',
            'domain': [('equipo_id', '=', self.id)],
            'context': "{'create': True}"
        }

    def create_sale_order(self):
        sale_order = self.env['sale.order']
        order_id = sale_order.create({
            'partner_id': self.cliente_id.id,
            'equipo_id': self.id,

        })
        return {
            'name': 'Nuevo Registro',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'sale.order',
            'res_id': order_id.id,
            'type': 'ir.actions.act_window',
            'target': 'current',

        }

    def create_ticket(self):
        ticket = self.env['ticket.alquiler']
        ticket_id = ticket.create({
            'partner_id': self.cliente_id.id,
            'direccion_id_r': self.direccion,
            'contacto_id_r': self.contacto_id,
            'celular_id_r': self.celular,
            'corre_id_r': self.correo_,
            'product_alquiler': self.id,

        })
        return {
            'name': 'Registro',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'ticket.alquiler',
            'res_id': ticket_id.id,
            'type': 'ir.actions.act_window',
            'target': 'current',

        }

    

    repuestos_count = fields.Integer(compute='compute_count_repuestos')

    def compute_count_repuestos(self):
        for record in self:
            record.repuestos_count = self.env['repuestos.alquiler'].search_count(
                [('modelo_id', '=', self.id)])

    def get_repuestos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Repuestos',
            'view_mode': 'list,form',
            'res_model': 'repuestos.alquiler',
            'domain': [('modelo_id', '=', self.id)],
            'context': "{'create': False}"
        }

    @api.model
    def send_maintenance_reminders(self):
        """Envía recordatorios de mantenimiento a los clientes con equipos programados."""
        today = fields.Date.today()
        target_date = today + timedelta(days=3)
        _logger.info(f"Buscando registros con fecha_recurrente entre {target_date} y {target_date + timedelta(days=1)}")

        # Buscar registros con fecha_recurrente dentro del rango
        records = self.search([
            ('fecha_recurrente', '>=', target_date),
            ('fecha_recurrente', '<', target_date + timedelta(days=1)),
            ('control_mantenimiento', '=', True)
        ])
        _logger.info(f"Registros encontrados para enviar recordatorios: {len(records)}")

        if not records:
            _logger.warning("No se encontraron registros para enviar recordatorios.")
            return

        # Agrupar registros por cliente
        grouped_records = {}
        for record in records:
            if record.cliente_id:
                cliente_id = record.cliente_id.id
                if cliente_id not in grouped_records:
                    grouped_records[cliente_id] = {
                        'cliente': record.cliente_id,
                        'correo': record.correo_,
                        'equipos': []
                    }
                grouped_records[cliente_id]['equipos'].append(record)

        # Enviar correos agrupados por cliente
        mail_template = self.env.ref('sat.mail_template_maintenance_notification')
        for client_data in grouped_records.values():
            correo = client_data['correo']
            if not correo:
                _logger.warning(f"Cliente {client_data['cliente'].name} no tiene correo. Saltando...")
                continue

            primer_equipo = client_data['equipos'][0]
            try:
                mail_template.with_context(
                    equipos=client_data['equipos'],
                    fecha_mantenimiento=target_date
                ).send_mail(primer_equipo.id, force_send=True)
                _logger.info(f"Correo enviado a {correo} para cliente {client_data['cliente'].name}")
            except Exception as e:
                _logger.error(f"Error al enviar correo a {correo} para cliente {client_data['cliente'].name}: {e}")

    def button_send_test_mail(self):
        """Función para probar el envío de correo desde la interfaz"""
        self.ensure_one()
        # Buscar todos los equipos del mismo cliente
        equipos_cliente = self.search([
            ('cliente_id', '=', self.cliente_id.id),
            ('control_mantenimiento', '=', True)
        ])
        
        mail_template = self.env.ref('sat.mail_template_maintenance_notification')
        mail_template.with_context(
            equipos=equipos_cliente,
            fecha_mantenimiento=self.fecha_recurrente
        ).send_mail(self.id, force_send=True)
    
    qr_image = fields.Binary("Código QR", attachment=True)

    def generate_qr_code(self):
        # Obtener la URL base de la configuración de Odoo
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        qr_url = f"{base_url}/api/escanear_qr?id_registro={self.id}"  # Construir la URL completa

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_url)  # Añade la URL completa al QR
        qr.make(fit=True)

        img = qr.make_image(fill='black', back_color='white')
        temp = BytesIO()
        img.save(temp, format="PNG")
        qr_img = base64.b64encode(temp.getvalue())
        self.write({'qr_image': qr_img})




     # Campos originales de fechas
    fecha_inicio = fields.Date(
        string='Fecha de mantenimiento', 
        required=True,
        tracking=True,
        help="Fecha inicial del mantenimiento"
    )

    intervalo_meses = fields.Selection([
        ('1', 'Mensual'),
        ('2', 'Cada 2 meses'),
        ('3', 'Cada 3 meses'),
        ('6', 'Cada 6 meses'),
        ('12', 'Anual')
    ], string='Intervalo de mantenimiento', 
       default='1', 
       required=True,
       tracking=True,
       help="Frecuencia de mantenimiento"
    )

    fecha_recurrente = fields.Date(
        string='Fecha recurrente',
        compute='_compute_fecha_recurrente',
        store=True,
        tracking=True,
        help="Próxima fecha de mantenimiento"
    )

    # Campo de estado de programación
    estado_programacion = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('confirmado', 'Confirmado'),
        ('reprogramado', 'Por Reprogramar')
    ], string='Estado de Programación', 
       default='pendiente', 
       tracking=True,
       help="Estado actual de la programación del mantenimiento"
    )

    # Campos adicionales para tracking
    fecha_confirmacion = fields.Datetime(
        string='Fecha de Confirmación',
        tracking=True,
        readonly=True,
        help="Fecha cuando se confirmó el mantenimiento"
    )

    motivo_reprogramacion = fields.Text(
        string='Motivo de Reprogramación',
        tracking=True,
        help="Razón por la que se solicita reprogramación"
    )

    @api.depends('fecha_inicio', 'intervalo_meses')
    def _compute_fecha_recurrente(self):
        for record in self:
            if record.fecha_inicio:
                # Guardar fecha anterior para comparación
                fecha_anterior = record.fecha_recurrente
                
                # Obtener día de la semana y número de semana del día inicial
                dia_semana = record.fecha_inicio.weekday()
                semana_mes = (record.fecha_inicio.day - 1) // 7 + 1

                # Calcular siguiente fecha según intervalo
                meses = int(record.intervalo_meses)
                siguiente_fecha = record.fecha_inicio + relativedelta(months=meses, day=1)
                
                # Encontrar el mismo día de la semana en la misma semana del mes
                contador_semana = 0
                while True:
                    if siguiente_fecha.weekday() == dia_semana:
                        contador_semana += 1
                        if contador_semana == semana_mes:
                            break
                    siguiente_fecha += relativedelta(days=1)
                    if siguiente_fecha.month != (record.fecha_inicio + relativedelta(months=meses)).month:
                        siguiente_fecha = record.fecha_inicio + relativedelta(months=meses, day=1)
                        break

                record.fecha_recurrente = siguiente_fecha

                # Actualizar estado si la fecha cambió
                if fecha_anterior and siguiente_fecha != fecha_anterior:
                    if record.estado_programacion in ['confirmado', 'reprogramado']:
                        record.estado_programacion = 'pendiente'
                        record.message_post(
                            body=f"⚠️ Nueva fecha de mantenimiento calculada: {siguiente_fecha.strftime('%d/%m/%Y')}",
                            message_type='notification'
                        )
            else:
                record.fecha_recurrente = False

    @api.model
    def update_fecha_recurrente(self):
        today = fields.Date.today()
        records = self.search([
            ('fecha_recurrente', '<=', today),
            ('estado_programacion', 'in', ['confirmado', 'pendiente']),
            ('control_mantenimiento', '=', True)
        ])
        
        for record in records:
            if record.fecha_recurrente:
                dia_semana = record.fecha_inicio.weekday()
                semana_mes = (record.fecha_inicio.day - 1) // 7 + 1
                
                siguiente_fecha = record.fecha_recurrente + relativedelta(months=int(record.intervalo_meses), day=1)
                
                contador_semana = 0
                while True:
                    if siguiente_fecha.weekday() == dia_semana:
                        contador_semana += 1
                        if contador_semana == semana_mes:
                            break
                    siguiente_fecha += relativedelta(days=1)
                    if siguiente_fecha.month != (record.fecha_recurrente + relativedelta(months=int(record.intervalo_meses))).month:
                        siguiente_fecha = record.fecha_recurrente + relativedelta(months=int(record.intervalo_meses), day=1)
                        break

                record.write({
                    'fecha_recurrente': siguiente_fecha,
                    'estado_programacion': 'pendiente',
                    'fecha_confirmacion': False
                })
                record.message_post(
                    body=f"🔄 Mantenimiento actualizado para: {siguiente_fecha.strftime('%d/%m/%Y')}",
                    message_type='notification'
                )

    def _create_maintenance_tickets(self):
        """Crear tickets de mantenimiento para todos los equipos del cliente"""
        try:
            equipos = self.search([
                ('cliente_id', '=', self.cliente_id.id),
                ('fecha_recurrente', '=', self.fecha_recurrente),
                ('control_mantenimiento', '=', True)
            ])
            
            for equipo in equipos:
                self.env['ticket.alquiler'].create({
                    'partner_id': equipo.cliente_id.id,
                    'product_alquiler': equipo.id,
                    'tipo_servicio_id': 'mantenimiento_preventivo',
                    'estado': 'nuevo',
                    'description': 'Mantenimiento preventivo programado',
                    'direccion_id_r': equipo.direccion,
                    'contacto_id_r': equipo.contacto_id,
                    'celular_id_r': equipo.celular,
                    'corre_id_r': equipo.correo_,
                })
            
            self.write({
                'estado_programacion': 'confirmado',
                'fecha_confirmacion': fields.Datetime.now()
            })
            template = self.env.ref('sat.mail_template_maintenance_confirmation')
            template.send_mail(self.id, force_send=True)
            
            self.message_post(
                body=f"✅ Mantenimiento confirmado para {self.fecha_recurrente.strftime('%d/%m/%Y')}",
                message_type='notification'
            )
            
            return True
        except Exception as e:
            _logger.error("Error al crear tickets de mantenimiento: %s", str(e))
            return False

    def _send_reschedule_request(self):
        """Enviar solicitud de reprogramación"""
        try:
            self.write({
                'estado_programacion': 'reprogramado',
                'fecha_confirmacion': False
            })
            template = self.env.ref('sat.mail_template_maintenance_reschedule')
            template.send_mail(self.id, force_send=True)
            
            self.message_post(
                body="🔄 Solicitud de reprogramación recibida",
                message_type='notification'
            )
            
            return True
        except Exception as e:
            _logger.error("Error al enviar solicitud de reprogramación: %s", str(e))
            return False

    def process_maintenance_response(self, response_type):
        """Procesa la respuesta del cliente desde el correo"""
        self.ensure_one()
        # Validaciones
        if self.estado_programacion == 'confirmado' and response_type == 'confirm':
            raise ValidationError(_("Este mantenimiento ya está confirmado"))
        if self.estado_programacion == 'reprogramado' and response_type == 'confirm':
            raise ValidationError(_("Este mantenimiento está pendiente de reprogramación"))

        if response_type == 'confirm':
            return self._create_maintenance_tickets()
        elif response_type == 'reschedule':
            return self._send_reschedule_request()
        return False

    resultado_inspeccion = fields.One2many(
        'inspeccion.resultado', 
        'alquiler_id', 
        string='Resultados de inspección'
    )

    token = fields.Char('Token de inspección', readonly=True, copy=False, store=True)

    def _generar_url_inspeccion(self):
        self.ensure_one()
        if not self.token:
            self.token = str(uuid.uuid4())
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/inspeccion/{self.token}"
    apto_instalacion = fields.Boolean(
        'Apto para instalación',
        compute='_compute_apto',
        store=True
    )
    estado_instalacion = fields.Selection([
        ('pendiente', 'Pendiente de inspección'),
        ('apto', 'Apto para instalación'),
        ('requiere_adecuacion', 'Requiere adecuación'),
        ('no_apto', 'No apto')
    ], string='Estado de instalación', compute='_compute_apto', store=True)
    requiere_adecuacion = fields.Boolean(
        'Requiere adecuación',
        compute='_compute_apto',
        store=True
    )
    notas_adecuacion = fields.Text(
        'Notas de adecuación',
        compute='_compute_apto',
        store=True
    )

    @api.depends('resultado_inspeccion')
    def _compute_apto(self):
        for rec in self:
            if not rec.resultado_inspeccion:
                rec.apto_instalacion = False
                rec.requiere_adecuacion = False
                rec.estado_instalacion = 'pendiente'
                rec.notas_adecuacion = False
                continue

            # Usar la inspección más reciente
            resultado = rec.resultado_inspeccion.sorted('fecha', reverse=True)[0]
            notas = []

            # Validar espacio físico
            espacio_ok = resultado.espacio >= 2.0 and resultado.ancho_pasillo >= 1.0
            if not espacio_ok:
                notas.append("- Espacio insuficiente: requiere mínimo 2m² y pasillo de 1m de ancho.")

            # Validar instalación eléctrica
            if resultado.punto_corriente == 'pendiente':
                notas.append("- Requiere instalación de punto eléctrico.")
            elif resultado.punto_corriente == 'no':
                notas.append("- No cuenta con punto eléctrico.")

            # Validar red
            if resultado.punto_red == 'pendiente':
                notas.append("- Requiere instalación de punto de red.")
            elif resultado.punto_red == 'no' and resultado.wifi == 'no':
                notas.append("- No cuenta con punto de red ni señal WiFi disponible.")

            # Validar entorno de PCs
            total_pcs = resultado.cantidad_windows + resultado.cantidad_mac + resultado.cantidad_linux
            if total_pcs <= 0:
                notas.append("- Debe haber al menos una computadora conectada (Windows, Mac o Linux).")

            # Determinar estado final
            if not notas:
                rec.estado_instalacion = 'apto'
            elif any("No cuenta" in nota or "Requiere instalación" in nota for nota in notas):
                rec.estado_instalacion = 'no_apto'
            else:
                rec.estado_instalacion = 'requiere_adecuacion'

            rec.apto_instalacion = rec.estado_instalacion == 'apto'
            rec.requiere_adecuacion = rec.estado_instalacion == 'requiere_adecuacion'
            rec.notas_adecuacion = '\n'.join(notas) if notas else False


    def action_enviar_inspeccion(self):
        self.ensure_one()
        return {
            'name': 'Enviar Inspección',
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.enviar.inspeccion',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_alquiler_id': self.id}
        }
     # Añadir contador de partes solicitadas
    partes_solicitadas_count = fields.Integer(
        string='Partes Solicitadas', 
        compute='_compute_partes_count'
    )

    partes_ids = fields.One2many(
        'solicitud.partes.linea',
        'maquina_origen_id',
        string='Partes',
        readonly=True
    )

    @api.depends()
    def _compute_partes_count(self):
        for record in self:
            # Contar solicitudes como origen
            origen_count = self.env['solicitud.partes'].search_count([
                ('maquina_origen_id', '=', record.id)
            ])
            # Contar solicitudes como destino
            destino_count = self.env['solicitud.partes'].search_count([
                ('maquina_destino_id', '=', record.id)
            ])
            record.partes_solicitadas_count = origen_count + destino_count

    def action_view_partes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Solicitudes de Partes',
            'view_mode': 'list,form',
            'res_model': 'solicitud.partes',
            'domain': [
                '|',
                ('maquina_origen_id', '=', self.id),
                ('maquina_destino_id', '=', self.id)
            ],
            'context': {
                'default_maquina_origen_id': self.id,
            }
        }
    def action_solicitar_partes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Solicitar Partes',
            'view_mode': 'form',
            'res_model': 'solicitud.partes',
            'context': {
                'default_maquina_origen_id': self.id,
                'form_view_initial_mode': 'edit',
            },
            'target': 'current',
        }


class SolicitudPartes(models.Model):
    _name = 'solicitud.partes'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Solicitud de Partes'
    _order = 'fecha_solicitud desc, id desc'

    name = fields.Char(string='Número de Solicitud', readonly=True, copy=False, default='Nuevo')
    
    maquina_origen_id = fields.Many2one(
        'alquiler', 
        string='Máquina Origen', 
        required=True, 
        tracking=True,
        domain="[('estado_alquiler_id', 'not in', ['vendida', 'partes'])]"
    )
    maquina_destino_id = fields.Many2one(
        'alquiler', 
        string='Máquina Destino', 
        tracking=True,
        domain="[('id', '!=', maquina_origen_id), ('estado_alquiler_id', 'not in', ['vendida'])]"
    )
    
    fecha_solicitud = fields.Datetime(string='Fecha de Solicitud', default=fields.Datetime.now, tracking=True, readonly=True)
    solicitante_id = fields.Many2one('res.users', string='Solicitante', default=lambda self: self.env.user, tracking=True, readonly=True)
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('submitted', 'Enviado'),
        ('approved', 'Aprobado'),
        ('completed', 'Completado'),
        ('replaced', 'Reemplazado'),
        ('rejected', 'Rechazado')
    ], string='Estado', default='draft', tracking=True)
    
    # Campos de autorización
    autorizado_por = fields.Many2one('res.users', string='Autorizado por', tracking=True, readonly=True)
    fecha_autorizacion = fields.Datetime(string='Fecha de Autorización', tracking=True, readonly=True)
    
    # Campos de retiro
    retirado_por = fields.Many2one('res.users', string='Retirado por', tracking=True, readonly=True)
    fecha_retiro = fields.Datetime(string='Fecha de Retiro', tracking=True, readonly=True)

    # Campos de reemplazo
    reemplazado_por = fields.Many2one('res.users', string='Reemplazado por', tracking=True, readonly=True)
    fecha_reemplazo = fields.Datetime(string='Fecha de Reemplazo', tracking=True, readonly=True)
    
    parte_ids = fields.One2many('solicitud.partes.linea', 'solicitud_id', string='Partes Solicitadas')
    access_token = fields.Char('Token de Acceso', copy=False, readonly=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'Nuevo') == 'Nuevo':
            vals['name'] = self.env['ir.sequence'].next_by_code('solicitud.partes') or 'Nuevo'
        vals['access_token'] = uuid.uuid4().hex
        return super().create(vals)

    def action_submit(self):
        self.ensure_one()
        if not self.parte_ids:
            raise UserError(_('Debe agregar al menos una parte antes de enviar la solicitud.'))
        self.write({'state': 'submitted'})
        template = self.env.ref('sat.email_template_solicitud_partes_alquiler')
        template.send_mail(self.id, force_send=True)

    def action_approve(self):
        self.ensure_one()
        self.write({
            'state': 'approved',
            'autorizado_por': self.env.user.id,
            'fecha_autorizacion': fields.Datetime.now()
        })

    def action_complete(self):
        self.ensure_one()
        if not all(line.estado in ['retirado', 'reemplazado'] for line in self.parte_ids):
            raise UserError(_('Todas las partes deben estar retiradas o reemplazadas.'))
        self.write({
            'state': 'completed',
            'retirado_por': self.env.user.id,
            'fecha_retiro': fields.Datetime.now()
        })
        self.maquina_origen_id.write({'estado_alquiler_id': 'con_problemas'})

    def action_replace(self):
        self.ensure_one()
        if not all(line.estado == 'reemplazado' for line in self.parte_ids):
            raise UserError(_('Todas las partes deben estar reemplazadas.'))
        self.write({
            'state': 'replaced',
            'reemplazado_por': self.env.user.id,
            'fecha_reemplazo': fields.Datetime.now()
        })
        # Si todas las partes están en buen estado, restaurar estado de la máquina
        if all(line.condicion == 'bueno' for line in self.parte_ids):
            self.maquina_origen_id.write({'estado_alquiler_id': 'alquilada'})

    def action_reject(self):
        self.write({'state': 'rejected'})

class SolicitudPartesLinea(models.Model):
    _name = 'solicitud.partes.linea'
    _description = 'Línea de Solicitud de Partes'
    
    solicitud_id = fields.Many2one('solicitud.partes', string='Solicitud')
    parte = fields.Char(string='Parte/Unidad', required=True)
    descripcion = fields.Text(string='Descripción')
    estado = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('retirado', 'Retirado'),
        ('reemplazado', 'Reemplazado')
    ], string='Estado', default='pendiente')
    
    # Campos de reemplazo
    fecha_reemplazo = fields.Datetime(string='Fecha Reemplazo')
    reemplazado_por = fields.Many2one('res.users', string='Reemplazado por')
    condicion = fields.Selection([
        ('bueno', 'Buen Estado'),
        ('defectuoso', 'Defectuoso')
    ], string='Condición')
    
    @api.depends('solicitud_id.state')
    def _compute_estado_editable(self):
        for record in self:
            record.estado_editable = record.solicitud_id.state in ['approved', 'completed']

    def action_retirar(self):
        self.write({'estado': 'retirado'})
        
    def action_reemplazar(self):
        self.write({
            'estado': 'reemplazado',
            'fecha_reemplazo': fields.Datetime.now(),
            'reemplazado_por': self.env.user.id
        })

    def action_registrar_condicion(self):
        return {
            'name': 'Registrar Condición',
            'type': 'ir.actions.act_window',
            'res_model': 'registro.condicion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_parte_id': self.id}
        }

class WizardEnviarInspeccion(models.TransientModel):
    _name = 'wizard.enviar.inspeccion'
    _description = 'Asistente para enviar inspección'

    correo = fields.Char(string='Correo electrónico', required=True)
    alquiler_id = fields.Many2one('alquiler', string='Alquiler', required=True)

    def action_enviar(self):
        self.ensure_one()
        url = self.alquiler_id._generar_url_inspeccion()
        template = self.env.ref('sat.mail_template_inspeccion')
        template.with_context(url_inspeccion=url).send_mail(
            self.alquiler_id.id,
            email_values={'email_to': self.correo},
            force_send=True
        )
        return {'type': 'ir.actions.act_window_close'}

class InspeccionResultado(models.Model):
    _name = 'inspeccion.resultado'
    _description = 'Resultado de inspección de sitio'
    _inherit = ['mail.thread', 'mail.activity.mixin'] 


    name = fields.Char('Número', readonly=True, copy=False, default='Nuevo')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('inspeccion.resultado') or 'Nuevo'
        records = super().create(vals_list)
        for record in records:
            record._update_estado()
            if record.alquiler_id:
                record.alquiler_id._compute_apto()
        return records

    def write(self, vals):
        res = super(InspeccionResultado, self).write(vals)
        self._update_estado()
        if any(field in vals for field in ['punto_corriente', 'punto_red', 'espacio']):
            for record in self:
                if record.alquiler_id:
                    record.alquiler_id._compute_apto()
        return res
    alquiler_id = fields.Many2one('alquiler', required=True)
    fecha = fields.Datetime('Fecha de inspección', default=fields.Datetime.now)
    
    # Instalación Eléctrica
    punto_corriente = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No'),
        ('pendiente', 'Requiere instalación')
    ], string='Punto eléctrico', required=True)
    voltaje = fields.Float('Voltaje medido (V)')
    
    # Infraestructura de Red
    punto_red = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No'),
        ('pendiente', 'Requiere instalación')
    ], string='Punto de red', required=True)
    wifi = fields.Selection([
        ('si', 'Sí'),
        ('no', 'No')
    ], string='Señal WiFi')
    area_sistemas = fields.Boolean('¿Cuenta con área de sistemas?')
    contacto_sistemas = fields.Char('Contacto del área de sistemas')
    
    # Control de Impresión
    control_impresion = fields.Boolean('¿Requiere control de impresión?')
    tipo_control = fields.Selection([
        ('usuario', 'Por usuario'),
        ('departamento', 'Por departamento'),
        ('proyecto', 'Por proyecto')
    ], string='Tipo de control')
    cantidad_usuarios = fields.Integer('Cantidad de usuarios')
    requiere_reportes = fields.Boolean('¿Requiere reportes de uso?')
    frecuencia_reportes = fields.Selection([
        ('diario', 'Diario'),
        ('semanal', 'Semanal'),
        ('mensual', 'Mensual')
    ], string='Frecuencia de reportes')
    
    # Entorno de PCs
    cantidad_windows = fields.Integer('Cantidad de PCs Windows')
    cantidad_mac = fields.Integer('Cantidad de PCs Mac')
    cantidad_linux = fields.Integer('Cantidad de PCs Linux')
    
    # Configuración de Escaneo
    usar_smb = fields.Boolean('¿Usará escaneo a carpeta compartida (SMB)?')
    usar_ftp = fields.Boolean('¿Usará escaneo a FTP?')
    usar_email = fields.Boolean('¿Usará escaneo a email?')
    tipo_servidor_email = fields.Selection([
        ('propio', 'Servidor de correo propio'),
        ('proveedor', 'Servidor del proveedor')
    ], string='Tipo de servidor email')
    servidor_email_propio = fields.Char('Servidor SMTP propio', help='Solo si usará su propio servidor de correo')
    
    # Espacio Físico y Acceso
    piso = fields.Integer('Número de piso')
    ascensor = fields.Boolean('Tiene ascensor')
    espacio = fields.Float('Espacio disponible (m²)')
    ancho_pasillo = fields.Float('Ancho de pasillo (m)')
    tiene_estacionamiento = fields.Boolean('¿Tiene estacionamiento para camión?')
    observaciones_estacionamiento = fields.Text('Observaciones de estacionamiento')
    
    # Estado y Observaciones
    estado = fields.Selection([
        ('pendiente', 'Pendiente de revisión'),
        ('aprobado', 'Aprobado'),
        ('requiere_cambios', 'Requiere cambios'),
        ('rechazado', 'No viable')
    ], string='Estado', default='pendiente')
    observaciones = fields.Text('Observaciones')
    requisitos_pendientes = fields.Text('Requisitos pendientes')
    puede_reenviar = fields.Boolean('Puede reenviar formulario', default=True)

    @api.onchange('usar_email')
    def _onchange_usar_email(self):
        if not self.usar_email:
            self.tipo_servidor_email = False
            self.servidor_email_propio = False

    @api.onchange('tipo_servidor_email')
    def _onchange_tipo_servidor_email(self):
        if self.tipo_servidor_email == 'proveedor':
            self.servidor_email_propio = False

    @api.onchange('estado')
    def _onchange_estado(self):
        if self.estado in ['requiere_cambios', 'rechazado']:
            self.puede_reenviar = True
        else:
            self.puede_reenviar = False

    @api.onchange('control_impresion')
    def _onchange_control_impresion(self):
        if not self.control_impresion:
            self.tipo_control = False
            self.cantidad_usuarios = 0
            self.requiere_reportes = False
            self.frecuencia_reportes = False


    def action_view_alquiler(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Alquiler',
            'res_model': 'alquiler',
            'res_id': self.alquiler_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.constrains('cantidad_windows', 'cantidad_mac', 'cantidad_linux')
    def _check_total_pcs(self):
        for rec in self:
            total_pcs = rec.cantidad_windows + rec.cantidad_mac + rec.cantidad_linux
            if total_pcs <= 0:
                raise ValidationError("Debe haber al menos una computadora conectada (Windows, Mac o Linux).")
    def _update_estado(self):
        for record in self:
            problemas = []
            if record.punto_corriente == 'no':
                problemas.append("No tiene punto de corriente.")
            elif record.punto_corriente == 'pendiente':
                problemas.append("Requiere instalación de punto de corriente.")

            if record.punto_red == 'no' and record.wifi == 'no':
                problemas.append("No tiene conexión a red ni WiFi.")
            elif record.punto_red == 'pendiente':
                problemas.append("Requiere instalación de punto de red.")

            if record.espacio < 2.0 or record.ancho_pasillo < 1.0:
                problemas.append("Espacio insuficiente: mínimo 2m² y pasillo de 1m de ancho.")

            total_pcs = record.cantidad_windows + record.cantidad_mac + record.cantidad_linux
            if total_pcs <= 0:
                problemas.append("No hay computadoras conectadas.")

            nuevo_estado = 'aprobado' if not problemas else 'rechazado' if any("Requiere" in p or "No tiene" in p for p in problemas) else 'requiere_cambios'
            nuevo_requisitos = '\n'.join(problemas) if problemas else False

            self.env.cr.execute("""
                UPDATE inspeccion_resultado 
                SET estado = %s, requisitos_pendientes = %s 
                WHERE id = %s
            """, (nuevo_estado, nuevo_requisitos, record.id))

    @api.onchange('punto_corriente', 'punto_red', 'wifi', 'espacio', 'ancho_pasillo', 'cantidad_windows', 'cantidad_mac', 'cantidad_linux')
    def _onchange_estado(self):
        self._update_estado()

   