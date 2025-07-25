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

    _name = 'alquiler'
    _description = 'Maquina en alquiler'

    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Many2one('modelo.maquina', string='Modelo',
                           required=True
                           )
    serie = fields.Char(string='Serie', required=True, tracking=True)
    tipo_maquina = fields.Char(related='name.tipo_maquina_id.name', readonly=True, store=True,
                               string='Tipo de maquina')
    tipo_maquina_id = fields.Selection([('color', 'Color'), ('monocromatica', 'Monocromatica')],
                                       string="Tipo de Equipo", related='name.tipo_id')

    precio_venta = fields.Float(string='Precio de venta', tracking=True)
    precio_compra = fields.Float(string='Precio de compra', tracking=True)
    contador_bn = fields.Integer(string="Contador B/N", tracking=True)
    contador_color = fields.Integer(string="Contador Color", tracking=True)
    contador_scan = fields.Integer(string="Contador Escáner", tracking=True)
    fecha_ultima_actualizacion = fields.Datetime(string="Fecha de última actualización")
    # En la clase UnidadAlquiler, agregar este método
    def write(self, vals):
        """Sobrescribir write para sincronizar estado de bloqueo entre equipos del mismo cliente"""
        
        # Ejecutar el write original primero
        res = super(UnidadAlquiler, self).write(vals)
        
        # Sincronizar estado de bloqueo entre equipos del mismo cliente
        if 'estado_bloqueo' in vals:
            for record in self:
                if record.cliente_id:
                    # Log para debugging
                    _logger.info(f"SINCRONIZACIÓN INICIADA para equipo {record.serie} del cliente {record.cliente_id.name}")
                    
                    # Buscar otros equipos del mismo cliente (excluyendo el actual)
                    otros_equipos = self.search([
                        ('id', '!=', record.id),
                        ('cliente_id', '=', record.cliente_id.id),
                        ('estado_alquiler_id', '=', 'alquilada')  # Solo equipos alquilados
                    ])
                    
                    _logger.info(f"Equipos encontrados para sincronizar: {len(otros_equipos)} - Series: {otros_equipos.mapped('serie')}")
                    
                    if otros_equipos:
                        # Preparar valores para actualización
                        update_vals = {
                            'estado_bloqueo': vals.get('estado_bloqueo'),
                            'notificado_bloqueo': False,
                            'notificado_desbloqueo': False
                        }
                        
                        # Agregar campos adicionales según el estado
                        if vals.get('estado_bloqueo') in ['suspendido', 'bloqueado']:
                            update_vals.update({
                                'motivo_bloqueo': vals.get('motivo_bloqueo', record.motivo_bloqueo),
                                'fecha_bloqueo': vals.get('fecha_bloqueo', record.fecha_bloqueo),
                                'usuario_bloqueo': vals.get('usuario_bloqueo', record.usuario_bloqueo),
                            })
                        elif vals.get('estado_bloqueo') == 'activo':
                            update_vals.update({
                                'fecha_desbloqueo': vals.get('fecha_desbloqueo', record.fecha_desbloqueo),
                                'motivo_bloqueo': False,
                                'observaciones_bloqueo': False,
                                'acceso_remoto_disponible': True,
                            })
                        
                        # Log de valores que se van a actualizar
                        _logger.info(f"Valores a actualizar: {update_vals}")
                        
                        try:
                            # OPCIÓN 1: Usar write() normal (recomendado para mantener consistencia)
                            # Temporalmente desactivar la sincronización para evitar recursión
                            context_sin_sync = dict(self.env.context, skip_sync=True)
                            otros_equipos.with_context(context_sin_sync).write(update_vals)
                            
                            # Invalidar cache para reflejar cambios
                            otros_equipos.invalidate_cache()
                            
                            _logger.info(f"✅ ÉXITO: Actualización completada para {len(otros_equipos)} equipos")
                            
                            # Log para auditoría en el equipo original
                            estado_nombre = dict(self._fields['estado_bloqueo'].selection).get(vals.get('estado_bloqueo'))
                            record.message_post(
                                body=f"🔄 <b>Sincronización automática:</b><br/>"
                                    f"Estado '{estado_nombre}' aplicado automáticamente a {len(otros_equipos)} equipos adicionales del cliente <b>{record.cliente_id.name}</b><br/>"
                                    f"<small>Series afectadas: {', '.join(otros_equipos.mapped('serie'))}</small>",
                                message_type='notification'
                            )
                            
                            # Log en cada equipo sincronizado
                            for equipo in otros_equipos:
                                equipo.message_post(
                                    body=f"🔄 <b>Estado sincronizado automáticamente</b><br/>"
                                        f"Nuevo estado: <span class='badge badge-info'>{estado_nombre}</span><br/>"
                                        f"Origen: Equipo {record.serie} del mismo cliente<br/>"
                                        f"Usuario: {self.env.user.name}",
                                    message_type='notification'
                                )
                                
                        except Exception as e:
                            _logger.error(f"❌ ERROR en sincronización: {str(e)}")
                            # Continuar con el proceso aunque falle la sincronización
                            record.message_post(
                                body=f"⚠️ <b>Error en sincronización automática:</b><br/>"
                                    f"No se pudo sincronizar con otros equipos del cliente.<br/>"
                                    f"Error: {str(e)}",
                                message_type='notification'
                            )
                    else:
                        _logger.info("No se encontraron otros equipos para sincronizar")
        
        return res
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

    

    marca = fields.Char(related='name.marca_id.name',
                        readonly=True, store=True, string='Marca')

    

    @api.constrains('serie')
    def unique_field_serie(self):
        for item in self:
            # Busca otros registros con la misma serie y un ID diferente
            items = self.search(
                [('serie', '=', item.serie), ('id', '!=', item.id)]
            )
            if items:  # Si encuentra al menos un registro duplicado
                raise ValidationError(
                    "La serie ingresada ya está en uso. Por favor, ingrese una serie única.")

    contacto_id = fields.Char(string='Contacto', tracking=True)
    celular = fields.Char(string='Celular', tracking=True)
    correo_ = fields.Char(string='Correo', tracking=True)
    cargo = fields.Char(string='Cargo', tracking=True)
    ubicacion_instalacion = fields.Char(string="Área de instalacion")
    observaciones = fields.Html(string="Observaciones")
    direccion = fields.Text(string='Dirección y Distrito', tracking=True)
    ubicacion_id = fields.Selection([('primer_piso', 'Primer piso'), ('tercer_piso', 'Tercer piso'), ('segundo_local', 'Segundo local'), ('covida', 'Covida')],
                                    default='primer_piso', tracking=True,
                                    )
    estado_alquiler_id = fields.Selection([('sin_revisar', 'Sin revisar'), ('revisada', 'Revisada'), ('lista', 'Lista'), ('alquilada', 'Alquilada'), ('con_problemas', 'Con Problemas'), ('partes', 'De Partes'), ('externo', 'Externo'), ('vendida', 'Vendida')],
                                          string='Estado de Maquina',
                                          default='sin_revisar', tracking=True)

    cliente_id = fields.Many2one(
        'res.partner', string='Cliente', required=False, tracking=True)

    ticket_count = fields.Integer(
        string='Ticket Count', compute='_compute_counts')

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

    has_pending_orders = fields.Boolean(
        compute='compute_count_pedidos', store=False)

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
            'tipo_pedido': 'delivery',

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

    
    
    
    qr_image = fields.Binary("Código QR", attachment=True)
    qr_image_filename = fields.Char("Nombre archivo QR", compute='_compute_qr_filename', store=True)
    @api.depends('serie', 'name')
    def _compute_qr_filename(self):
        for record in self:
            if record.serie and record.name:
                # Asegurar que el nombre sea una cadena válida
                modelo_name = record.name.name if hasattr(record.name, 'name') else str(record.name)
                record.qr_image_filename = f"qr_{record.serie}_{modelo_name}.png"
            else:
                record.qr_image_filename = f"qr_code_{record.id}.png"
    def generate_qr_code(self):
        """Genera código QR para el equipo"""
        try:
            # Obtener la URL base de la configuración de Odoo
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            # Construir la URL completa
            qr_url = f"{base_url}/api/escanear_qr?id_registro={self.id}"

            # Crear el código QR
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_url)
            qr.make(fit=True)

            # Generar la imagen
            img = qr.make_image(fill='black', back_color='white')
            temp = BytesIO()
            img.save(temp, format="PNG")
            qr_img = base64.b64encode(temp.getvalue())

            # Generar nombre de archivo único y válido
            serie_clean = re.sub(r'[^\w\-_\.]', '_', self.serie or '') if self.serie else 'sin_serie'
            filename = f"qr_code_{serie_clean}_{self.id}.png"

            # Actualizar los campos - IMPORTANTE: usar write() para evitar problemas
            self.write({
                'qr_image': qr_img,
                'qr_image_filename': filename
            })

            # Mensaje de éxito
            self.message_post(
                body=f"✅ Código QR generado exitosamente: {filename}",
                message_type='notification'
            )

        except Exception as e:
            # Log del error y mensaje al usuario
            _logger.error(f"Error al generar QR para equipo {self.id}: {str(e)}")
            self.message_post(
                body=f"❌ Error al generar código QR: {str(e)}",
                message_type='notification'
            )
            raise UserError(f"Error al generar código QR: {str(e)}")


    def get_qr_image_url(self):
        """Obtiene la URL segura para mostrar la imagen QR"""
        self.ensure_one()
        if not self.qr_image:
            return False
        
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/web/image/alquiler/{self.id}/qr_image/{self.qr_image_filename or 'qr_code.png'}"


    # Agregar este método a tu clase UnidadAlquiler
    def _get_qr_download_name(self):
        """Asegura que el nombre de descarga sea siempre una cadena"""
        self.ensure_one()
        if self.qr_image_filename:
            return self.qr_image_filename
        elif self.serie:
            return f"qr_code_{self.serie}.png"
        else:
            return f"qr_code_{self.id}.png"
    @api.model
    def limpiar_attachments_qr_huerfanos(self):
        """Limpia attachments de QR que puedan estar causando problemas"""
        attachments_problematicos = self.env['ir.attachment'].search([
            ('res_model', '=', 'alquiler'),
            ('res_field', '=', 'qr_image'),
            ('name', '=', False)  # Attachments sin nombre
        ])
        
        for attachment in attachments_problematicos:
            # Asignar un nombre válido
            record = self.browse(attachment.res_id)
            if record.exists():
                attachment.name = f"qr_code_{record.serie or record.id}.png"
            else:
                # El registro ya no existe, eliminar attachment
                attachment.unlink()
     

    resultado_inspeccion = fields.One2many(
        'inspeccion.resultado',
        'alquiler_id',
        string='Resultados de inspección'
    )

    token = fields.Char('Token de inspección',
                        readonly=True, copy=False, store=True)

    def _generar_url_inspeccion(self):
        self.ensure_one()
        if not self.token:
            self.token = str(uuid.uuid4())
        base_url = self.env['ir.config_parameter'].sudo(
        ).get_param('web.base.url')
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
            resultado = rec.resultado_inspeccion.sorted(
                'fecha', reverse=True)[0]
            notas = []

            # Validar espacio físico
            espacio_ok = resultado.espacio >= 2.0 and resultado.ancho_pasillo >= 1.0
            if not espacio_ok:
                notas.append(
                    "- Espacio insuficiente: requiere mínimo 2m² y pasillo de 1m de ancho.")

            # Validar instalación eléctrica
            if resultado.punto_corriente == 'pendiente':
                notas.append("- Requiere instalación de punto eléctrico.")
            elif resultado.punto_corriente == 'no':
                notas.append("- No cuenta con punto eléctrico.")

            # Validar red
            if resultado.punto_red == 'pendiente':
                notas.append("- Requiere instalación de punto de red.")
            elif resultado.punto_red == 'no' and resultado.wifi == 'no':
                notas.append(
                    "- No cuenta con punto de red ni señal WiFi disponible.")

            # Validar entorno de PCs
            total_pcs = resultado.cantidad_windows + \
                resultado.cantidad_mac + resultado.cantidad_linux
            if total_pcs <= 0:
                notas.append(
                    "- Debe haber al menos una computadora conectada (Windows, Mac o Linux).")

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


    # CAMPOS PARA SISTEMA DE BLOQUEO
    estado_bloqueo = fields.Selection([
        ('activo', 'Activo'),
        ('suspendido', 'Suspendido por Mora'),
        ('bloqueado', 'Bloqueado Remotamente'),
        ('no_accesible', 'No Accesible para Bloqueo'),
        ('pendiente_bloqueo', 'Pendiente de Bloqueo'),
        ('pendiente_desbloqueo', 'Pendiente de Desbloqueo')
    ], string='Estado de Servicio', default='activo', tracking=True)

    motivo_bloqueo = fields.Text(string='Motivo del Bloqueo/Suspensión', tracking=True)
    fecha_bloqueo = fields.Datetime(string='Fecha de Bloqueo', readonly=True, tracking=True)
    fecha_desbloqueo = fields.Datetime(string='Fecha de Desbloqueo', readonly=True, tracking=True)
    usuario_bloqueo = fields.Many2one('res.users', string='Usuario que Bloqueó', readonly=True)

    acceso_remoto_disponible = fields.Boolean(
        string='Acceso Remoto Disponible', 
        default=True,
        help="Indica si el equipo puede ser bloqueado/desbloqueado remotamente"
    )

    ip_equipo = fields.Char(string='IP del Equipo', tracking=True)

    notificado_bloqueo = fields.Boolean(string='Notificado Bloqueo', default=False)
    notificado_desbloqueo = fields.Boolean(string='Notificado Desbloqueo', default=False)

    asesor_ventas_id = fields.Many2one('res.users', string='Asesor de Ventas', tracking=True)
    soporte_tecnico_id = fields.Many2one('res.users', string='Soporte Técnico Asignado', tracking=True)

    observaciones_bloqueo = fields.Text(string='Observaciones de Bloqueo')

    def action_suspender_servicio(self, motivo=None, usuario_id=None):
        self.ensure_one()
        if self.estado_bloqueo == 'suspendido':
            raise UserError("El servicio ya está suspendido")
        self.write({
            'estado_bloqueo': 'suspendido',
            'motivo_bloqueo': motivo or 'Suspendido por mora de pagos',
            'fecha_bloqueo': fields.Datetime.now(),
            'usuario_bloqueo': usuario_id or self.env.user.id,
            'notificado_bloqueo': False
        })
        self._enviar_notificacion_suspension()
        self.message_post(
            body=f"⚠️ Servicio suspendido: {motivo or 'Mora de pagos'}",
            message_type='notification'
        )
        return True

    def action_bloquear_equipo(self, motivo=None, usuario_id=None):
        self.ensure_one()
        if self.estado_bloqueo == 'bloqueado':
            raise UserError("El equipo ya está bloqueado")
        
        # Bloquear directamente sin verificar acceso remoto
        self.write({
            'estado_bloqueo': 'bloqueado',
            'fecha_bloqueo': fields.Datetime.now(),
            'motivo_bloqueo': motivo or 'Bloqueo remoto por suspensión de servicio',
            'usuario_bloqueo': usuario_id or self.env.user.id,
            'notificado_bloqueo': False
        })
        
        # Siempre enviar notificación de bloqueo exitoso
        self._enviar_notificacion_bloqueo_exitoso()
        
        self.message_post(
            body=f"🔒 Equipo bloqueado: {motivo or 'Bloqueo remoto por suspensión de servicio'}",
            message_type='notification'
        )
        
        return {'success': True, 'message': 'Equipo bloqueado exitosamente'}

    def action_desbloquear_equipo(self, motivo=None, usuario_id=None):
        self.ensure_one()
        if self.estado_bloqueo not in ['bloqueado', 'suspendido']:
            raise UserError("El equipo no está bloqueado")
        
        # Desbloquear directamente sin verificar acceso remoto
        self.write({
            'estado_bloqueo': 'activo',
            'fecha_desbloqueo': fields.Datetime.now(),
            'motivo_bloqueo': False,
            'observaciones_bloqueo': False,
            'usuario_bloqueo': usuario_id or self.env.user.id,
            'notificado_desbloqueo': False
        })
        
        # Siempre enviar notificación de desbloqueo exitoso
        self._enviar_notificacion_desbloqueo_exitoso()
        
        self.message_post(
            body="🔓 Equipo desbloqueado exitosamente",
            message_type='notification'
        )
        
        return {'success': True, 'message': 'Equipo desbloqueado exitosamente'}

    def _ejecutar_bloqueo_remoto(self):
        try:
            if not self.ip_equipo:
                return {'success': False, 'error': 'IP del equipo no configurada'}
            url = f"http://{self.ip_equipo}/api/block"
            response = requests.post(url, timeout=30, json={
                'action': 'block',
                'reason': self.motivo_bloqueo
            })
            if response.status_code == 200:
                return {'success': True}
            else:
                return {'success': False, 'error': f'Error HTTP: {response.status_code}'}
        except Exception as e:
            _logger.error(f"Error al bloquear equipo {self.serie}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _ejecutar_desbloqueo_remoto(self):
        try:
            if not self.ip_equipo:
                return {'success': False, 'error': 'IP del equipo no configurada'}
            url = f"http://{self.ip_equipo}/api/unblock"
            response = requests.post(url, timeout=30, json={'action': 'unblock'})
            if response.status_code == 200:
                return {'success': True}
            else:
                return {'success': False, 'error': f'Error HTTP: {response.status_code}'}
        except Exception as e:
            _logger.error(f"Error al desbloquear equipo {self.serie}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _enviar_notificacion_suspension(self):
        """Envía notificación de suspensión a grupos y contactos"""
        mensaje = """⚠️ *SERVICIO SUSPENDIDO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Motivo: {}
    Dirección: {}

    Se ha suspendido el servicio técnico.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            self.motivo_bloqueo,
            self.direccion
        )
        
        # Usar el método que maneja grupos Y usuarios
        self._enviar_a_contactos_responsables(mensaje)
    def _enviar_notificacion_bloqueo_exitoso(self):
        mensaje = """🔒 *EQUIPO BLOQUEADO EXITOSAMENTE*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Fecha: {}
    IP: {}

    El equipo ha sido bloqueado remotamente.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            fields.Datetime.now().strftime('%d/%m/%Y %H:%M'),
            self.ip_equipo or 'No configurada'
        )
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_notificacion_bloqueo_fallido(self):
        mensaje = """❌ *ERROR AL BLOQUEAR EQUIPO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Error: {}

    Se requiere bloqueo manual del equipo.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            self.motivo_bloqueo
        )
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_notificacion_desbloqueo_exitoso(self):
        mensaje = """🔓 *EQUIPO DESBLOQUEADO EXITOSAMENTE*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Fecha: {}

    El equipo ha sido desbloqueado. Se puede usar normal.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            fields.Datetime.now().strftime('%d/%m/%Y %H:%M')
        )
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_notificacion_desbloqueo_fallido(self):
        mensaje = """❌ *ERROR AL DESBLOQUEAR EQUIPO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Error: {}

    Se requiere desbloqueo manual del equipo.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            self.motivo_bloqueo
        )
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_notificacion_no_accesible(self):
        mensaje = """⚠️ *EQUIPO NO ACCESIBLE PARA BLOQUEO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Estado: NO ACCESIBLE

    Se requiere intervención manual para suspender el servicio.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie
        )
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_a_contactos_responsables(self, mensaje):
        """Envía mensaje a grupos y contactos responsables con logging detallado"""
        _logger.info(f"========== INICIO ENVÍO NOTIFICACIONES - Equipo: {self.serie} ==========")
        _logger.info(f"Grupo Notificaciones ID: {self.grupo_notificaciones_id}")
        _logger.info(f"Grupo Asesor ID: {self.grupo_asesor_ventas_id}")
        _logger.info(f"Asesor Ventas: {self.asesor_ventas_id.name if self.asesor_ventas_id else 'No asignado'}")
        
        enviados = []
        errores = []
        
        # 1. Enviar a grupo de notificaciones principal
        if self.grupo_notificaciones_id:
            _logger.info(f"Intentando enviar a grupo notificaciones: {self.grupo_notificaciones_id}")
            try:
                resultado = self._send_whatsapp_notification(self.grupo_notificaciones_id, mensaje)
                if resultado:
                    enviados.append(f"Grupo Notificaciones: {self.grupo_notificaciones_id}")
                    _logger.info(f"✅ ÉXITO: Enviado a grupo notificaciones {self.grupo_notificaciones_id}")
                else:
                    errores.append(f"Grupo Notificaciones: {self.grupo_notificaciones_id}")
                    _logger.error(f"❌ ERROR: No se pudo enviar a grupo notificaciones {self.grupo_notificaciones_id}")
            except Exception as e:
                errores.append(f"Grupo Notificaciones: {self.grupo_notificaciones_id} - Error: {str(e)}")
                _logger.error(f"❌ EXCEPCIÓN al enviar a grupo notificaciones: {str(e)}")
        else:
            _logger.warning("⚠️ No hay grupo de notificaciones configurado")
        
        # 2. Enviar a grupo del asesor de ventas
        if self.grupo_asesor_ventas_id:
            _logger.info(f"Intentando enviar a grupo asesor: {self.grupo_asesor_ventas_id}")
            try:
                resultado = self._send_whatsapp_notification(self.grupo_asesor_ventas_id, mensaje)
                if resultado:
                    enviados.append(f"Grupo Asesor: {self.grupo_asesor_ventas_id}")
                    _logger.info(f"✅ ÉXITO: Enviado a grupo asesor {self.grupo_asesor_ventas_id}")
                else:
                    errores.append(f"Grupo Asesor: {self.grupo_asesor_ventas_id}")
                    _logger.error(f"❌ ERROR: No se pudo enviar a grupo asesor {self.grupo_asesor_ventas_id}")
            except Exception as e:
                errores.append(f"Grupo Asesor: {self.grupo_asesor_ventas_id} - Error: {str(e)}")
                _logger.error(f"❌ EXCEPCIÓN al enviar a grupo asesor: {str(e)}")
        else:
            _logger.warning("⚠️ No hay grupo de asesor configurado")
        
        # 3. Enviar al número del asesor (solo si no hay grupos configurados)
        if not self.grupo_notificaciones_id and not self.grupo_asesor_ventas_id:
            _logger.info("No hay grupos configurados, intentando enviar directamente al asesor")
            if self.asesor_ventas_id and self.asesor_ventas_id.mobile_phone:
                phone_asesor = self._clean_phone_number(self.asesor_ventas_id.mobile_phone)
                _logger.info(f"Teléfono asesor limpio: {phone_asesor}")
                try:
                    resultado = self._send_whatsapp_notification(phone_asesor, mensaje)
                    if resultado:
                        enviados.append(f"Asesor directo: {self.asesor_ventas_id.name} ({phone_asesor})")
                        _logger.info(f"✅ ÉXITO: Enviado a asesor {self.asesor_ventas_id.name}")
                    else:
                        errores.append(f"Asesor directo: {self.asesor_ventas_id.name}")
                        _logger.error(f"❌ ERROR: No se pudo enviar a asesor {self.asesor_ventas_id.name}")
                except Exception as e:
                    errores.append(f"Asesor directo: {self.asesor_ventas_id.name} - Error: {str(e)}")
                    _logger.error(f"❌ EXCEPCIÓN al enviar a asesor: {str(e)}")
            else:
                _logger.warning("⚠️ No hay asesor con teléfono configurado")
        else:
            _logger.info("Hay grupos configurados, no se envía al asesor directamente")
        
        # Resumen final
        _logger.info("========== RESUMEN DE ENVÍOS ==========")
        if enviados:
            _logger.info(f"✅ Enviados exitosamente: {len(enviados)}")
            for enviado in enviados:
                _logger.info(f"  - {enviado}")
        else:
            _logger.error("❌ No se enviaron notificaciones exitosamente")
        
        if errores:
            _logger.error(f"❌ Errores en envíos: {len(errores)}")
            for error in errores:
                _logger.error(f"  - {error}")
        
        _logger.info(f"========== FIN ENVÍO NOTIFICACIONES ==========\n")
        
        # Registrar en el chatter del equipo
        if enviados or errores:
            resumen = "📤 <b>Notificaciones enviadas:</b><br/>"
            if enviados:
                resumen += "✅ Exitosos:<br/>" + "<br/>".join([f"• {e}" for e in enviados])
            if errores:
                resumen += "<br/>❌ Fallidos:<br/>" + "<br/>".join([f"• {e}" for e in errores])
            
            self.message_post(body=resumen, message_type='notification')

    def _clean_phone_number(self, phone):
        if not phone:
            return None
        phone = phone.replace('+', '').replace(' ', '').replace('-', '')
        if not phone.startswith('51'):
            phone = '51' + phone
        return phone

    def _send_whatsapp_notification(self, phone, message):
        """Envía notificación a WhatsApp (grupos o números individuales)"""
        if not phone:
            _logger.warning("Teléfono/grupo no especificado")
            return False
            
        try:
            url = 'https://whatsapp.andessolutioncopiers.com/api/message'
            data = {
                'phone': phone,  # Funciona para ambos: "51999999999" o "51990649502-1484267115@g.us"
                'message': message,
                'type': 'text'  # ✅ AGREGAR este campo
            }
            headers = {'Content-Type': 'application/json'}
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                response_data = response.json()
                # ✅ VERIFICAR respuesta de tu API
                if response_data.get('success'):
                    _logger.info(f"Notificación enviada exitosamente a {phone}")
                    return True
                else:
                    _logger.error(f"Error en API: {response_data.get('message')} para {phone}")
                    return False
            else:
                _logger.error(f"Error HTTP al enviar a {phone}: {response.status_code}")
                return False
                
        except Exception as e:
            _logger.error(f"Error al enviar notificación WhatsApp: {str(e)}")
            return False
     # Reemplazar los campos Char por estos:

    grupo_notificaciones_id = fields.Selection(
        selection='_get_grupos_whatsapp',
        string='Grupo de Notificaciones',
        help="Grupo de WhatsApp para notificaciones de bloqueo/desbloqueo"
    )

    grupo_asesor_ventas_id = fields.Selection(
        selection='_get_grupos_whatsapp', 
        string='Grupo Asesor de Ventas',
        help="Grupo de WhatsApp del asesor de ventas"
    )
    @api.model
    def _get_grupos_whatsapp(self):
        """Obtiene la lista de grupos de WhatsApp desde la API"""
        try:
            url = 'http://149.56.117.184:3005/api/groups'
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    grupos = []
                    for grupo in data['data']:
                        # CLAVE: (ID, NOMBRE) - Guarda ID pero muestra NOMBRE
                        grupos.append((grupo['id'], grupo['name']))
                    return grupos
            
            _logger.warning("No se pudieron obtener los grupos de WhatsApp")
            return [('', 'No hay grupos disponibles')]
            
        except Exception as e:
            _logger.error(f"Error al obtener grupos de WhatsApp: {str(e)}")
            return [('', 'Error al cargar grupos')]
    def action_refresh_grupos(self):
        """Refresca la lista de grupos disponibles"""
        # Forzar recálculo del selection
        self._fields['grupo_notificaciones_id'].selection = self._get_grupos_whatsapp()
        self._fields['grupo_asesor_ventas_id'].selection = self._get_grupos_whatsapp()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Grupos actualizados',
                'message': 'Lista de grupos de WhatsApp actualizada',
                'type': 'success',
            }
        }

    # ============================================
    # MÉTODOS PARA AGREGAR AL MODELO EXISTENTE
    # ============================================

    def action_marcar_pendiente_bloqueo(self):
        """Marca el equipo como pendiente de bloqueo"""
        self.ensure_one()
        if self.estado_bloqueo == 'pendiente_bloqueo':
            raise UserError("El equipo ya está marcado como pendiente de bloqueo")
        
        self.write({
            'estado_bloqueo': 'pendiente_bloqueo',
            'motivo_bloqueo': self.motivo_bloqueo or 'Pendiente de bloqueo - Requiere acción',
            'fecha_bloqueo': fields.Datetime.now(),
            'usuario_bloqueo': self.env.user.id,
            'notificado_bloqueo': False
        })
        
        # Llamar notificación
        self._enviar_notificacion_pendiente_bloqueo()
        
        self.message_post(
            body="⏳ Equipo marcado como pendiente de bloqueo",
            message_type='notification'
        )
        return True

    def action_marcar_pendiente_desbloqueo(self):
        """Marca el equipo como pendiente de desbloqueo"""
        self.ensure_one()
        if self.estado_bloqueo != 'bloqueado':
            raise UserError("Solo se puede marcar como pendiente de desbloqueo un equipo bloqueado")
        
        self.write({
            'estado_bloqueo': 'pendiente_desbloqueo',
            'observaciones_bloqueo': self.observaciones_bloqueo or 'Pendiente de desbloqueo - Pago procesándose',
            'usuario_bloqueo': self.env.user.id,
            'notificado_desbloqueo': False
        })
        
        # Llamar notificación
        self._enviar_notificacion_pendiente_desbloqueo()
        
        self.message_post(
            body="⏳ Equipo marcado como pendiente de desbloqueo",
            message_type='notification'
        )
        return True

    def action_marcar_no_accesible(self):
        """Marca el equipo como no accesible para bloqueo remoto"""
        self.ensure_one()
        
        self.write({
            'estado_bloqueo': 'no_accesible',
            'acceso_remoto_disponible': False,
            'motivo_bloqueo': 'Equipo no accesible para bloqueo remoto',
            'fecha_bloqueo': fields.Datetime.now(),
            'usuario_bloqueo': self.env.user.id,
            'notificado_bloqueo': False
        })
        
        # Ya tienes esta notificación
        self._enviar_notificacion_no_accesible()
        
        self.message_post(
            body="❌ Equipo marcado como NO ACCESIBLE para bloqueo remoto",
            message_type='notification'
        )
        return True

    def action_reactivar_servicio(self):
        """Reactiva el servicio desde cualquier estado"""
        self.ensure_one()
        if self.estado_bloqueo == 'activo':
            raise UserError("El servicio ya está activo")
        
        estado_anterior = self.estado_bloqueo
        
        self.write({
            'estado_bloqueo': 'activo',
            'fecha_desbloqueo': fields.Datetime.now(),
            'motivo_bloqueo': False,
            'observaciones_bloqueo': False,
            'acceso_remoto_disponible': True,
            'usuario_bloqueo': self.env.user.id,
            'notificado_bloqueo': False,
            'notificado_desbloqueo': False
        })
        
        # Llamar notificación de reactivación
        self._enviar_notificacion_reactivacion(estado_anterior)
        
        self.message_post(
            body=f"✅ Servicio reactivado (estado anterior: {estado_anterior})",
            message_type='notification'
        )
        return True

    def action_verificar_acceso_remoto(self):
        """Verifica si el equipo tiene acceso remoto disponible"""
        self.ensure_one()
        
        if not self.ip_equipo:
            raise UserError("No hay IP configurada para este equipo")
        
        try:
            # Intentar conexión de prueba
            url = f"http://{self.ip_equipo}/api/status"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                self.write({
                    'acceso_remoto_disponible': True
                })
                mensaje = "✅ Acceso remoto verificado exitosamente"
            else:
                self.write({
                    'acceso_remoto_disponible': False
                })
                mensaje = "❌ No se pudo verificar el acceso remoto"
                
        except:
            self.write({
                'acceso_remoto_disponible': False
            })
            mensaje = "❌ Error al verificar acceso remoto"
        
        self.message_post(body=mensaje, message_type='notification')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Verificación completada',
                'message': mensaje,
                'type': 'success' if self.acceso_remoto_disponible else 'warning',
            }
        }

    # ============================================
    # NOTIFICACIONES FALTANTES
    # ============================================

    def _enviar_notificacion_pendiente_bloqueo(self):
        """Notificación para estado pendiente_bloqueo"""
        mensaje = """⏳ *EQUIPO PENDIENTE DE BLOQUEO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Estado: PENDIENTE DE BLOQUEO
    Motivo: {}
    Fecha: {}

    ⚠️ Se requiere acción para proceder con el bloqueo remoto.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            self.motivo_bloqueo or 'Pendiente de bloqueo por mora',
            fields.Datetime.now().strftime('%d/%m/%Y %H:%M')
        )
        
        # Solo enviar usando _enviar_a_contactos_responsables
        self._enviar_a_contactos_responsables(mensaje)

    def _enviar_notificacion_pendiente_desbloqueo(self):
        """Notificación para estado pendiente_desbloqueo"""
        mensaje = """⏳ *EQUIPO PENDIENTE DE DESBLOQUEO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Estado: PENDIENTE DE DESBLOQUEO
    Observaciones: {}
    Fecha: {}

    💰 Pago en proceso de verificación. Se desbloqueará una vez confirmado.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            self.observaciones_bloqueo or 'Pago pendiente de confirmación',
            fields.Datetime.now().strftime('%d/%m/%Y %H:%M')
        )
        
        # Solo enviar usando _enviar_a_contactos_responsables
        self._enviar_a_contactos_responsables(mensaje)


    def _enviar_notificacion_reactivacion(self, estado_anterior):
        """Notificación cuando se reactiva el servicio desde cualquier estado"""
        mensaje = """✅ *SERVICIO REACTIVADO*

    Cliente: *{}*
    Equipo: {} - Serie: {}
    Estado anterior: {}
    Estado actual: ACTIVO
    Fecha: {}

    ✔️ El servicio ha sido reactivado completamente.
    El equipo está operativo.""".format(
            self.cliente_id.name,
            self.name.name,
            self.serie,
            dict(self._fields['estado_bloqueo'].selection).get(estado_anterior, estado_anterior).upper(),
            fields.Datetime.now().strftime('%d/%m/%Y %H:%M')
        )
        
        # Solo enviar usando _enviar_a_contactos_responsables
        self._enviar_a_contactos_responsables(mensaje)
    @api.model
    def get_dashboard_data(self):
        data = {
            'equipos_activos': self.search_count([('estado_bloqueo', '=', 'activo')]),
            'equipos_suspendidos': self.search_count([('estado_bloqueo', '=', 'suspendido')]),
            'equipos_bloqueados': self.search_count([('estado_bloqueo', '=', 'bloqueado')]),
            'equipos_no_accesibles': self.search_count([('estado_bloqueo', '=', 'no_accesible')]),
            'pendientes_bloqueo': self.search_count([('estado_bloqueo', '=', 'pendiente_bloqueo')]),
            'pendientes_desbloqueo': self.search_count([('estado_bloqueo', '=', 'pendiente_desbloqueo')])
        }
        equipos_atencion = self.search([
            ('estado_bloqueo', 'in', ['pendiente_bloqueo', 'pendiente_desbloqueo', 'no_accesible'])
        ], limit=10)
        data['equipos_atencion'] = [{
            'id': eq.id,
            'cliente': eq.cliente_id.name,
            'serie': eq.serie,
            'modelo': eq.name.name,
            'estado': eq.estado_bloqueo,
            'motivo': eq.motivo_bloqueo
        } for eq in equipos_atencion]
        return data

    @api.model
    def buscar_equipos_web(self, busqueda):
        domain = ['|', '|', '|',
                ('serie', 'ilike', busqueda),
                ('cliente_id.name', 'ilike', busqueda),
                ('name.name', 'ilike', busqueda),
                ('marca', 'ilike', busqueda)]
        equipos = self.search(domain, limit=50)
        resultado = []
        for equipo in equipos:
            resultado.append({
                'id': equipo.id,
                'serie': equipo.serie,
                'cliente': equipo.cliente_id.name if equipo.cliente_id else '',
                'modelo': equipo.name.name if equipo.name else '',
                'marca': equipo.marca,
                'estado_bloqueo': equipo.estado_bloqueo,
                'estado_label': dict(equipo._fields['estado_bloqueo'].selection)[equipo.estado_bloqueo],
                'direccion': equipo.direccion,
                'acceso_remoto': equipo.acceso_remoto_disponible,
                'ip_equipo': equipo.ip_equipo,
                'motivo_bloqueo': equipo.motivo_bloqueo,
                'fecha_bloqueo': equipo.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if equipo.fecha_bloqueo else '',
                'puede_suspender': equipo.estado_bloqueo == 'activo',
                'puede_bloquear': equipo.estado_bloqueo in ['activo', 'suspendido'],
                'puede_desbloquear': equipo.estado_bloqueo in ['bloqueado', 'suspendido']
            })
        return resultado




    # Agregar estos métodos al modelo UnidadAlquiler en tu archivo principal

    @api.model
    def get_dashboard_data_alquilados(self):
        """Obtiene datos del dashboard solo para equipos alquilados"""
        base_domain = [('estado_alquiler_id', '=', 'alquilada')]
        
        data = {
            'equipos_activos': self.search_count(base_domain + [('estado_bloqueo', '=', 'activo')]),
            'equipos_suspendidos': self.search_count(base_domain + [('estado_bloqueo', '=', 'suspendido')]),
            'equipos_bloqueados': self.search_count(base_domain + [('estado_bloqueo', '=', 'bloqueado')]),
            'equipos_no_accesibles': self.search_count(base_domain + [('estado_bloqueo', '=', 'no_accesible')]),
            'pendientes_bloqueo': self.search_count(base_domain + [('estado_bloqueo', '=', 'pendiente_bloqueo')]),
            'pendientes_desbloqueo': self.search_count(base_domain + [('estado_bloqueo', '=', 'pendiente_desbloqueo')]),
            'total_alquilados': self.search_count(base_domain)
        }
        
        # Obtener equipos que requieren atención (solo alquilados)
        equipos_atencion = self.search(
            base_domain + [('estado_bloqueo', 'in', ['pendiente_bloqueo', 'pendiente_desbloqueo', 'no_accesible'])],
            limit=10,
            order='fecha_bloqueo desc'
        )
        
        data['equipos_atencion'] = [{
            'id': eq.id,
            'cliente': eq.cliente_id.name,
            'serie': eq.serie,
            'modelo': eq.name.name,
            'estado': eq.estado_bloqueo,
            'estado_label': dict(eq._fields['estado_bloqueo'].selection)[eq.estado_bloqueo],
            'motivo': eq.motivo_bloqueo,
            'fecha_bloqueo': eq.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if eq.fecha_bloqueo else ''
        } for eq in equipos_atencion]
        
        return data

    @api.model
    def get_equipos_alquilados_inicial(self, limit=50):
        """Obtiene lista inicial de equipos alquilados para mostrar al cargar la página"""
        equipos = self.search([
            ('estado_alquiler_id', '=', 'alquilada')
        ], limit=limit, order='serie asc')
        
        resultado = []
        for equipo in equipos:
            resultado.append({
                'id': equipo.id,
                'serie': equipo.serie,
                'cliente': equipo.cliente_id.name if equipo.cliente_id else '',
                'modelo': equipo.name.name if equipo.name else '',
                'marca': equipo.marca,
                'estado_bloqueo': equipo.estado_bloqueo,
                'estado_label': dict(equipo._fields['estado_bloqueo'].selection)[equipo.estado_bloqueo],
                'direccion': equipo.direccion,
                'acceso_remoto': equipo.acceso_remoto_disponible,
                'ip_equipo': equipo.ip_equipo,
                'motivo_bloqueo': equipo.motivo_bloqueo,
                'fecha_bloqueo': equipo.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if equipo.fecha_bloqueo else '',
                'puede_suspender': equipo.estado_bloqueo == 'activo',
                'puede_bloquear': equipo.estado_bloqueo in ['activo', 'suspendido'],
                'puede_desbloquear': equipo.estado_bloqueo in ['bloqueado', 'suspendido'],
                'contacto': equipo.contacto_id,
                'celular': equipo.celular,
                'correo': equipo.correo_
            })
        
        return resultado

    @api.model
    def buscar_equipos_alquilados_web(self, busqueda, estado_filtro=''):
        """Busca equipos solo en estado alquilada"""
        base_domain = [('estado_alquiler_id', '=', 'alquilada')]
        
        # Agregar filtro de búsqueda por texto
        if busqueda:
            search_domain = ['|', '|', '|',
                            ('serie', 'ilike', busqueda),
                            ('cliente_id.name', 'ilike', busqueda),
                            ('name.name', 'ilike', busqueda),
                            ('marca', 'ilike', busqueda)]
            base_domain = base_domain + search_domain
        
        # Agregar filtro por estado de bloqueo
        if estado_filtro:
            base_domain.append(('estado_bloqueo', '=', estado_filtro))
        
        equipos = self.search(base_domain, limit=100, order='serie asc')
        
        resultado = []
        for equipo in equipos:
            resultado.append({
                'id': equipo.id,
                'serie': equipo.serie,
                'cliente': equipo.cliente_id.name if equipo.cliente_id else '',
                'modelo': equipo.name.name if equipo.name else '',
                'marca': equipo.marca,
                'estado_bloqueo': equipo.estado_bloqueo,
                'estado_label': dict(equipo._fields['estado_bloqueo'].selection)[equipo.estado_bloqueo],
                'direccion': equipo.direccion,
                'acceso_remoto': equipo.acceso_remoto_disponible,
                'ip_equipo': equipo.ip_equipo,
                'motivo_bloqueo': equipo.motivo_bloqueo,
                'fecha_bloqueo': equipo.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if equipo.fecha_bloqueo else '',
                'puede_suspender': equipo.estado_bloqueo == 'activo',
                'puede_bloquear': equipo.estado_bloqueo in ['activo', 'suspendido'],
                'puede_desbloquear': equipo.estado_bloqueo in ['bloqueado', 'suspendido'],
                'contacto': equipo.contacto_id,
                'celular': equipo.celular,
                'correo': equipo.correo_
            })
        
        return resultado

    @api.model
    def filtrar_equipos_por_estado_bloqueo(self, estado_bloqueo):
        """Filtra equipos alquilados por estado de bloqueo específico"""
        domain = [
            ('estado_alquiler_id', '=', 'alquilada'),
            ('estado_bloqueo', '=', estado_bloqueo)
        ]
        
        equipos = self.search(domain, limit=100, order='serie asc')
        
        resultado = []
        for equipo in equipos:
            resultado.append({
                'id': equipo.id,
                'serie': equipo.serie,
                'cliente': equipo.cliente_id.name if equipo.cliente_id else '',
                'modelo': equipo.name.name if equipo.name else '',
                'marca': equipo.marca,
                'estado_bloqueo': equipo.estado_bloqueo,
                'estado_label': dict(equipo._fields['estado_bloqueo'].selection)[equipo.estado_bloqueo],
                'direccion': equipo.direccion,
                'acceso_remoto': equipo.acceso_remoto_disponible,
                'ip_equipo': equipo.ip_equipo,
                'motivo_bloqueo': equipo.motivo_bloqueo,
                'fecha_bloqueo': equipo.fecha_bloqueo.strftime('%d/%m/%Y %H:%M') if equipo.fecha_bloqueo else '',
                'puede_suspender': equipo.estado_bloqueo == 'activo',
                'puede_bloquear': equipo.estado_bloqueo in ['activo', 'suspendido'],
                'puede_desbloquear': equipo.estado_bloqueo in ['bloqueado', 'suspendido'],
                'contacto': equipo.contacto_id,
                'celular': equipo.celular,
                'correo': equipo.correo_
            })
        
        return resultado

    # ==========================================
    # CAMPOS DE TÓNER COMPLETOS - AGREGAR AL MODELO ALQUILER
    # ==========================================
    
    # Estado general del stock
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


    
    contadores_count = fields.Integer(
        string='Contadores',
        compute='_compute_contadores_count',
        store=False,
        help='Número de registros de contador generados para este equipo'
    )

    @api.depends()
    def _compute_contadores_count(self):
        for rec in self:
            rec.contadores_count = self.env['contador.automatico'].search_count([
                ('equipo_id', '=', rec.id)
            ])

    def action_open_contadores(self):
        self.ensure_one()
        return {
            'name': 'Contadores',
            'res_model': 'contador.automatico',
            'view_mode': 'list,form',
            'type': 'ir.actions.act_window',
            'domain': [('equipo_id', '=', self.id)],
        }