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

    has_auto_counters = fields.Boolean(
        string='Tiene contadores automáticos',
        compute='_compute_has_auto_counters',
        store=False,
        help='Indica si el equipo tiene contadores recientes provenientes de sistemas automáticos'
    )

    @api.depends('contador_bn', 'contador_color', 'fecha_ultima_actualizacion', 'pt_last_sync', 'tipo_maquina_id')
    def _compute_has_auto_counters(self):
        """Determina si el equipo tiene contadores automáticos confiables."""
        for rec in self:
            # Consideramos que hay contador si hay valor > 0
            has_bn = bool(rec.contador_bn and rec.contador_bn > 0)
            # Para monocromática no exigimos color
            if rec.tipo_maquina_id == 'color':
                has_color = bool(rec.contador_color and rec.contador_color > 0)
            else:
                has_color = True

            # Consideramos "reciente" si existe alguna de estas fechas
            has_recent_date = bool(rec.fecha_ultima_actualizacion or rec.pt_last_sync)

            rec.has_auto_counters = bool((has_bn or has_color) and has_recent_date)
    # En la clase UnidadAlquiler, agregar este método
    
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
    estado_alquiler_id = fields.Selection([
        ('sin_revisar', 'Sin revisar'),
        ('revisada', 'Revisada'),
        ('lista', 'Lista'),
        ('inspeccion', 'En inspección'),
        ('subsanacion', 'Esperando subsanación'),
        ('por_instalar', 'Por instalar'),
        ('alquilada', 'Alquilada'),
        ('con_problemas', 'Con Problemas'),
        ('partes', 'De Partes'),
        ('externo', 'Externo'),
        ('vendida', 'Vendida'),
    ], string='Estado de Maquina', default='sin_revisar', tracking=True)

    cliente_id = fields.Many2one(
        'res.partner', string='Cliente', required=False, tracking=True)
    # Agregar este campo en la clase UnidadAlquiler
    pt_entity_id = fields.Many2one(
        'printtracker.entity', 
        string='Entidad PrintTracker',
        help='Entidad PrintTracker asociada a este equipo',
        index=True
)
    pt_device_id = fields.Char(
        string='ID Dispositivo PrintTracker',
        help='ID único del dispositivo en PrintTracker Pro',
        index=True
    )

    pt_last_sync = fields.Datetime(
        string='Última Sincronización PT',
        help='Última vez que se sincronizó con PrintTracker',
        readonly=True
    )

    # Campos adicionales opcionales (si quieres más datos de PrintTracker):
    mac_address = fields.Char(string='Dirección MAC', help='MAC Address del dispositivo')
    ip_address = fields.Char(string='Dirección IP', help='IP Address del dispositivo')
    custom_location = fields.Char(string='Ubicación Personalizada', help='Ubicación en PrintTracker')
    asset_id = fields.Char(string='Asset ID', help='ID de activo en PrintTracker')
    is_managed = fields.Boolean(string='Gestionado', default=True, help='Si el equipo está gestionado en PrintTracker')
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
    inspeccion_count = fields.Integer(
        string='Inspecciones',
        compute='_compute_inspeccion_count',
    )

    @api.depends('resultado_inspeccion')
    def _compute_inspeccion_count(self):
        for rec in self:
            rec.inspeccion_count = len(rec.resultado_inspeccion)

    def action_view_inspecciones(self):
        """Abrir inspecciones del equipo."""
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Inspecciones',
            'res_model': 'inspeccion.resultado',
            'view_mode': 'list,form',
            'domain': [('alquiler_id', '=', self.id)],
            'context': {
                'default_alquiler_id': self.id,
            },
        }
        # Si solo hay una inspección, abrir directo el formulario
        if self.inspeccion_count == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.resultado_inspeccion[0].id
        return action

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
    # ═══════════════════════════════════════════════════════════════════
    #  ACCIONES MANUALES DE ESTADO DE ALQUILER
    # ═══════════════════════════════════════════════════════════════════

    def action_estado_sin_revisar(self):
        """Regresa el equipo a sin revisar."""
        for record in self:
            record.write({'estado_alquiler_id': 'sin_revisar'})
            record.message_post(
                body=_("🔄 Estado cambiado manualmente a 'Sin revisar'."),
                message_type='notification',
            )

    def action_estado_revisada(self):
        """Marca el equipo como revisado."""
        for record in self:
            record.write({'estado_alquiler_id': 'revisada'})
            record.message_post(
                body=_("🔧 Estado cambiado manualmente a 'Revisada'."),
                message_type='notification',
            )

    def action_estado_lista(self):
        """Marca el equipo como listo."""
        for record in self:
            record.write({'estado_alquiler_id': 'lista'})
            record.message_post(
                body=_("📋 Estado cambiado manualmente a 'Lista'."),
                message_type='notification',
            )

    def action_estado_inspeccion(self):
        """Marca el equipo como en inspección."""
        for record in self:
            record.write({'estado_alquiler_id': 'inspeccion'})
            record.message_post(
                body=_("🔍 Estado cambiado manualmente a 'En inspección'."),
                message_type='notification',
            )

    def action_estado_subsanacion(self):
        """Marca el equipo como esperando subsanación."""
        for record in self:
            record.write({'estado_alquiler_id': 'subsanacion'})
            record.message_post(
                body=_("⏳ Estado cambiado manualmente a 'Esperando subsanación'."),
                message_type='notification',
            )

    def action_estado_por_instalar(self):
        """Marca el equipo como por instalar."""
        for record in self:
            record.write({'estado_alquiler_id': 'por_instalar'})
            record.message_post(
                body=_("🏗️ Estado cambiado manualmente a 'Por instalar'."),
                message_type='notification',
            )

    def action_estado_alquilada(self):
        """Marca el equipo como alquilado."""
        for record in self:
            record.write({'estado_alquiler_id': 'alquilada'})
            record.message_post(
                body=_("✅ Estado cambiado manualmente a 'Alquilada'."),
                message_type='notification',
            )

    def action_estado_con_problemas(self):
        """Marca el equipo con problemas."""
        for record in self:
            record.write({'estado_alquiler_id': 'con_problemas'})
            record.message_post(
                body=_("⚠️ Estado cambiado manualmente a 'Con Problemas'."),
                message_type='notification',
            )

    def action_estado_partes(self):
        """Marca el equipo como de partes."""
        for record in self:
            record.write({'estado_alquiler_id': 'partes'})
            record.message_post(
                body=_("🔩 Estado cambiado manualmente a 'De Partes'."),
                message_type='notification',
            )

    def action_estado_externo(self):
        """Marca el equipo como externo."""
        for record in self:
            record.write({'estado_alquiler_id': 'externo'})
            record.message_post(
                body=_("🌐 Estado cambiado manualmente a 'Externo'."),
                message_type='notification',
            )

    def action_estado_vendida(self):
        """Marca el equipo como vendido."""
        for record in self:
            record.write({'estado_alquiler_id': 'vendida'})
            record.message_post(
                body=_("💰 Estado cambiado manualmente a 'Vendida'."),
                message_type='notification',
            )
    def action_enviar_inspeccion(self):
        """Enviar formulario de inspección al cliente."""
        self.ensure_one()
        estados_permitidos = ('lista', 'inspeccion', 'subsanacion')
        if self.estado_alquiler_id not in estados_permitidos:
            estado_label = dict(
                self._fields['estado_alquiler_id'].selection
            ).get(self.estado_alquiler_id, self.estado_alquiler_id)
            raise UserError(_(
                "Solo se puede enviar inspección cuando el equipo está en "
                "estado 'Lista', 'En inspección' o 'Esperando subsanación'.\n"
                "Estado actual: %s"
            ) % estado_label)

        # Cambiar estado solo si viene de 'lista' o 'subsanacion'
        if self.estado_alquiler_id in ('lista', 'subsanacion'):
            self.write({'estado_alquiler_id': 'inspeccion'})
            origen = 'subsanación' if self.estado_alquiler_id == 'subsanacion' else 'lista'
            self.message_post(
                body=_(
                    "📋 Inspección enviada al cliente. "
                    "Estado cambiado de '%s' a 'En inspección'."
                ) % origen,
                message_type='notification',
            )

        return {
            'name': 'Enviar Inspección',
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.enviar.inspeccion',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_alquiler_id': self.id},
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

    @api.model
    def get_alquiler_dashboard_values(self, domain=False):
        """Obtiene valores para el dashboard de alquiler"""
        domain = domain or []
        Alquiler = self.env['alquiler']

        domain_sin_vendidos = domain + [('estado_alquiler_id', '!=', 'vendida')]

        records = Alquiler.search(domain_sin_vendidos)
        total_equipos = len(records)

        # Mapeo de estados para conteo automático
        estados = [
            'sin_revisar', 'revisada', 'lista', 'inspeccion',
            'subsanacion', 'por_instalar', 'alquilada',
            'con_problemas', 'partes', 'externo',
        ]
        resultado = {'total_equipos': total_equipos}

        for estado in estados:
            resultado[f'total_{estado}'] = Alquiler.search_count(
                domain_sin_vendidos + [('estado_alquiler_id', '=', estado)]
            )

        # Vendidos aparte (no se excluyen del domain base)
        resultado['total_vendida'] = Alquiler.search_count(
            domain + [('estado_alquiler_id', '=', 'vendida')]
        )

        return resultado

    partes_retiradas_ids = fields.One2many(
        'solicitud.parte.tecnico.linea', 'maquina_origen_alquiler_id',
        string='Partes Retiradas', readonly=True)


    # ═══════════════════════════════════════════════════════════════════
    #  NOTIFICACIÓN POR CAMBIO DE ESTADO
    # ═══════════════════════════════════════════════════════════════════

    def write(self, vals):
        """Override para notificar por correo cualquier cambio de estado_alquiler_id."""
        # Capturar estados anteriores ANTES de escribir
        old_states = {rec.id: rec.estado_alquiler_id for rec in self}

        res = super().write(vals)

        # Solo procesar si el campo de estado fue modificado
        if 'estado_alquiler_id' in vals:
            for rec in self:
                old_state = old_states.get(rec.id)
                new_state = rec.estado_alquiler_id

                # Evitar disparos por escrituras redundantes (mismo valor)
                if old_state == new_state:
                    continue

                rec._enviar_notificacion_cambio_estado(old_state, new_state)

        return res

    def _enviar_notificacion_cambio_estado(self, old_state, new_state):
        """Envía correo a logística y contabilidad notificando el cambio de estado."""
        self.ensure_one()

        template = self.env.ref(
            'sat.mail_template_cambio_estado_alquiler',
            raise_if_not_found=False,
        )
        if not template:
            _logger.error(
                "No se encontró el template 'sat.mail_template_cambio_estado_alquiler'."
            )
            return

        # Etiquetas legibles de los estados
        estados_dict = dict(self._fields['estado_alquiler_id'].selection)
        old_label = estados_dict.get(old_state, old_state or 'Sin estado')
        new_label = estados_dict.get(new_state, new_state or 'Sin estado')

        try:
            template.with_context(
                old_state_label=old_label,
                new_state_label=new_label,
            ).send_mail(self.id, force_send=True)
        except Exception as e:
            _logger.error(
                "Error al enviar notificación de cambio de estado para equipo %s: %s",
                self.serie or self.id, str(e),
            )

    # ═══════════════════════════════════════════════════════════════════
    #  INTEGRACIÓN WHATSAPP - Selección de equipos en flujos conversacionales
    # ═══════════════════════════════════════════════════════════════════

    @api.model
    def whatsapp_get_machines_for_partner(self, partner, include_states=None,
                                          include_company_machines=True, limit=20):
        """
        Devuelve los equipos alquilados disponibles para un contacto WhatsApp.

        Busca por:
        - Equipos donde el partner es cliente directo.
        - Equipos donde el cliente es la empresa activa del partner.
        - Equipos donde el cliente es alguna de las empresas asociadas en whatsapp_company_ids.

        :param partner: recordset res.partner
        :param include_states: lista de estados de equipo a incluir.
                               Por defecto: ('alquilada', 'por_instalar').
        :param include_company_machines: si True, también busca por empresa activa.
        :param limit: máximo de equipos a devolver.
        :return: recordset de alquiler
        """
        if not partner:
            _logger.warning("[ALQUILER-WA] whatsapp_get_machines_for_partner sin partner")
            return self.browse()

        if include_states is None:
            include_states = ('alquilada', 'por_instalar')

        partner_ids = [partner.id]

        if include_company_machines:
            if partner.whatsapp_active_company_id:
                partner_ids.append(partner.whatsapp_active_company_id.id)

            if hasattr(partner, 'whatsapp_company_ids'):
                for company in partner.whatsapp_company_ids:
                    if company.id not in partner_ids:
                        partner_ids.append(company.id)

            if partner.parent_id and partner.parent_id.is_company:
                if partner.parent_id.id not in partner_ids:
                    partner_ids.append(partner.parent_id.id)

        domain = [
            ('cliente_id', 'in', partner_ids),
            ('estado_alquiler_id', 'in', list(include_states)),
        ]

        machines = self.search(domain, order='serie asc', limit=limit)

        _logger.info(
            "[ALQUILER-WA] Equipos encontrados partner=%s partner_ids=%s states=%s count=%s",
            partner.id, partner_ids, include_states, len(machines),
        )

        return machines

    @api.model
    def whatsapp_get_machines_for_company(self, company, include_states=None, limit=20):
        """
        Devuelve los equipos alquilados de una empresa específica.

        :param company: recordset res.partner (empresa)
        :param include_states: estados a incluir
        :param limit: máximo de equipos
        """
        if not company:
            _logger.warning("[ALQUILER-WA] whatsapp_get_machines_for_company sin company")
            return self.browse()

        if include_states is None:
            include_states = ('alquilada', 'por_instalar')

        domain = [
            ('cliente_id', '=', company.id),
            ('estado_alquiler_id', 'in', list(include_states)),
        ]

        machines = self.search(domain, order='serie asc', limit=limit)

        _logger.info(
            "[ALQUILER-WA] Equipos de empresa id=%s name=%s states=%s count=%s",
            company.id, company.name, include_states, len(machines),
        )

        return machines

    def whatsapp_to_menu_payload(self, position=None):
        """
        Convierte este equipo a un dict listo para mostrarse en un menú numerado
        del flujo conversacional WhatsApp.

        :param position: número de la opción en el menú (1, 2, 3...).
        :return: dict
        """
        self.ensure_one()

        modelo_name = ""
        if self.name:
            modelo_name = self.name.name if hasattr(self.name, 'name') else str(self.name)

        return {
            "machine_id": self.id,
            "position": position,
            "label": modelo_name or "Modelo desconocido",
            "serie": self.serie or "",
            "marca": self.marca or "",
            "tipo_maquina": self.tipo_maquina_id or "",
            "is_color": self.tipo_maquina_id == 'color',
            "ubicacion": self.ubicacion_instalacion or "",
            "direccion": self.direccion or "",
            "piso": dict(self._fields['ubicacion_id'].selection).get(
                self.ubicacion_id, self.ubicacion_id or ""
            ),
            "estado": self.estado_alquiler_id,
            "estado_label": dict(self._fields['estado_alquiler_id'].selection).get(
                self.estado_alquiler_id, self.estado_alquiler_id or ""
            ),
            "has_auto_counters": self.has_auto_counters,
            "contador_bn": self.contador_bn or 0,
            "contador_color": self.contador_color or 0,
            "cliente_id": self.cliente_id.id if self.cliente_id else False,
            "cliente_name": self.cliente_id.name if self.cliente_id else "",
        }

    @api.model
    def whatsapp_build_machine_menu(self, partner, intent="toner",
                                    include_states=None, limit=20):
        """
        Construye el menú de selección de equipos para el flujo conversacional.

        :param partner: contacto WhatsApp
        :param intent: 'toner', 'onsite' o 'remote' (afecta estados incluidos por defecto)
        :param include_states: si se provee, sobreescribe estados por defecto
        :param limit: máximo equipos
        :return: dict con menu_text, options, count
        """
        if not partner:
            _logger.warning("[ALQUILER-WA] whatsapp_build_machine_menu sin partner")
            return {
                "found": False,
                "count": 0,
                "options": [],
                "menu_text": "",
            }

        # Estados por defecto según intent
        if include_states is None:
            if intent == "remote":
                # Para remoto pueden ser cualquier equipo con el cliente
                include_states = ('alquilada', 'por_instalar')
            else:
                # Tóner y presencial solo en equipos en uso
                include_states = ('alquilada',)

        machines = self.whatsapp_get_machines_for_partner(
            partner=partner,
            include_states=include_states,
            limit=limit,
        )

        if not machines:
            _logger.info(
                "[ALQUILER-WA] Sin equipos para partner=%s intent=%s",
                partner.id, intent,
            )
            return {
                "found": False,
                "count": 0,
                "options": [],
                "menu_text": "",
            }

        options = []
        lines = []

        for index, machine in enumerate(machines, start=1):
            payload = machine.whatsapp_to_menu_payload(position=index)
            options.append(payload)

            label_parts = [payload["label"]]
            if payload["serie"]:
                label_parts.append("S/N: %s" % payload["serie"])
            if payload["ubicacion"]:
                label_parts.append(payload["ubicacion"])

            lines.append("%s. %s" % (index, " · ".join(label_parts)))

        menu_text = "\n".join(lines)

        _logger.info(
            "[ALQUILER-WA] Menú construido partner=%s intent=%s count=%s",
            partner.id, intent, len(options),
        )

        return {
            "found": True,
            "count": len(options),
            "options": options,
            "menu_text": menu_text,
        }

    @api.model
    def whatsapp_resolve_menu_selection(self, partner, selection_input, options):
        """
        Resuelve la respuesta del cliente ante un menú de equipos.

        :param partner: contacto WhatsApp
        :param selection_input: texto enviado por el cliente ("1", "2", etc.)
        :param options: lista de opciones tal como devolvió whatsapp_build_machine_menu
        :return: dict con machine_id o error
        """
        if not options:
            _logger.warning(
                "[ALQUILER-WA] resolve_menu_selection sin opciones partner=%s",
                partner.id if partner else False,
            )
            return {
                "valid": False,
                "error": "no_options",
                "message": "No hay opciones de equipos disponibles.",
            }

        raw = (selection_input or "").strip()

        if not raw:
            return {
                "valid": False,
                "error": "empty_input",
                "message": "No se recibió respuesta. Responde con el número de la opción.",
            }

        # Intentar como número
        try:
            position = int(re.sub(r"\D+", "", raw))
        except Exception:
            position = 0

        if position <= 0 or position > len(options):
            _logger.info(
                "[ALQUILER-WA] Selección inválida partner=%s input=%r max=%s",
                partner.id if partner else False, raw, len(options),
            )
            return {
                "valid": False,
                "error": "out_of_range",
                "message": "Opción no válida. Responde con un número entre 1 y %s." % len(options),
            }

        selected = options[position - 1]
        machine_id = selected.get("machine_id")

        machine = self.browse(machine_id).exists()
        if not machine:
            _logger.error(
                "[ALQUILER-WA] Equipo no existe id=%s partner=%s",
                machine_id, partner.id if partner else False,
            )
            return {
                "valid": False,
                "error": "machine_not_found",
                "message": "El equipo seleccionado ya no está disponible.",
            }

        _logger.info(
            "[ALQUILER-WA] Selección válida partner=%s position=%s machine_id=%s serie=%s",
            partner.id if partner else False, position, machine.id, machine.serie,
        )

        return {
            "valid": True,
            "machine_id": machine.id,
            "position": position,
            "payload": selected,
        }

    def whatsapp_get_toner_stock_info(self):
        """
        Devuelve el estado de stock de tóner del equipo para el flujo de solicitud.
        Equivalente al método _get_equipment_stock_info del controlador antiguo,
        pero en el modelo para que sea reutilizable.
        """
        self.ensure_one()

        try:
            stock_info = {
                "machine_id": self.id,
                "serie": self.serie,
                "is_color": self.tipo_maquina_id == 'color',
                "has_auto_counters": self.has_auto_counters,
                "contador_bn": self.contador_bn or 0,
                "contador_color": self.contador_color or 0,
                "gestion_automatica": self.name.gestionar_toner_automatico if self.name else True,
                "estado_stock": getattr(self, 'estado_stock_toner', False),
                "colors": {
                    "black": {
                        "stock_total": getattr(self, 'stock_total_toner_black', 0),
                        "stock_cliente": getattr(self, 'stock_cliente_toner_black', 0),
                        "instalado": getattr(self, 'toner_black_instalado', False),
                        "stock_minimo": self.name.stock_minimo_black if self.name else 1,
                    },
                },
            }

            if self.tipo_maquina_id == 'color':
                stock_info["colors"].update({
                    "cyan": {
                        "stock_total": getattr(self, 'stock_total_toner_cyan', 0),
                        "stock_cliente": getattr(self, 'stock_cliente_toner_cyan', 0),
                        "instalado": getattr(self, 'toner_cyan_instalado', False),
                        "stock_minimo": self.name.stock_minimo_cyan if self.name else 1,
                    },
                    "magenta": {
                        "stock_total": getattr(self, 'stock_total_toner_magenta', 0),
                        "stock_cliente": getattr(self, 'stock_cliente_toner_magenta', 0),
                        "instalado": getattr(self, 'toner_magenta_instalado', False),
                        "stock_minimo": self.name.stock_minimo_magenta if self.name else 1,
                    },
                    "yellow": {
                        "stock_total": getattr(self, 'stock_total_toner_yellow', 0),
                        "stock_cliente": getattr(self, 'stock_cliente_toner_yellow', 0),
                        "instalado": getattr(self, 'toner_yellow_instalado', False),
                        "stock_minimo": self.name.stock_minimo_yellow if self.name else 1,
                    },
                })

            _logger.debug(
                "[ALQUILER-WA] Stock info equipo id=%s is_color=%s",
                self.id, stock_info["is_color"],
            )

            return stock_info

        except Exception as e:
            _logger.exception(
                "[ALQUILER-WA] Error obteniendo stock info equipo id=%s error=%s",
                self.id, str(e),
            )
            return {
                "machine_id": self.id,
                "error": str(e),
                "colors": {},
            }

    def whatsapp_get_available_colors(self):
        """
        Devuelve los colores que el equipo puede usar.
        - Monocromática: solo black.
        - Color: black, cyan, magenta, yellow.
        """
        self.ensure_one()
        if self.tipo_maquina_id == 'color':
            return ['black', 'cyan', 'magenta', 'yellow']
        return ['black']

    def whatsapp_build_color_menu(self):
        """
        Construye el menú de selección de color de tóner.
        Para monocromáticas, devuelve auto-select de black.
        """
        self.ensure_one()

        labels = {
            'black': 'Negro',
            'cyan': 'Cyan',
            'magenta': 'Magenta',
            'yellow': 'Amarillo',
        }

        colors = self.whatsapp_get_available_colors()

        if len(colors) == 1:
            _logger.info(
                "[ALQUILER-WA] Equipo monocromático id=%s, auto-selección color=black",
                self.id,
            )
            return {
                "auto_select": True,
                "color": "black",
                "options": [{"position": 1, "color": "black", "label": "Negro"}],
                "menu_text": "",
            }

        options = []
        lines = []
        for index, color in enumerate(colors, start=1):
            options.append({
                "position": index,
                "color": color,
                "label": labels.get(color, color),
            })
            lines.append("%s. %s" % (index, labels.get(color, color)))

        return {
            "auto_select": False,
            "options": options,
            "menu_text": "\n".join(lines),
        }

    @api.model
    def whatsapp_resolve_color_selection(self, selection_input, options):
        """
        Resuelve la respuesta del cliente al menú de color de tóner.
        Acepta tanto número ("1") como nombre ("negro", "black").
        """
        if not options:
            return {
                "valid": False,
                "error": "no_options",
                "message": "No hay colores disponibles.",
            }

        raw = (selection_input or "").strip().lower()

        if not raw:
            return {
                "valid": False,
                "error": "empty_input",
                "message": "Responde con el número del color o su nombre.",
            }

        # Por número
        try:
            position = int(re.sub(r"\D+", "", raw))
            if 0 < position <= len(options):
                selected = options[position - 1]
                _logger.info(
                    "[ALQUILER-WA] Color seleccionado por número position=%s color=%s",
                    position, selected["color"],
                )
                return {
                    "valid": True,
                    "color": selected["color"],
                    "label": selected["label"],
                    "position": position,
                }
        except Exception:
            pass

        # Por nombre
        synonyms = {
            "negro": "black", "black": "black", "k": "black", "bn": "black", "b/n": "black",
            "cyan": "cyan", "cian": "cyan", "c": "cyan", "celeste": "cyan",
            "magenta": "magenta", "m": "magenta", "rosado": "magenta", "rosa": "magenta",
            "amarillo": "yellow", "yellow": "yellow", "y": "yellow",
        }

        for option in options:
            if raw == option["color"].lower() or raw == option["label"].lower():
                _logger.info(
                    "[ALQUILER-WA] Color seleccionado por nombre input=%r color=%s",
                    raw, option["color"],
                )
                return {
                    "valid": True,
                    "color": option["color"],
                    "label": option["label"],
                    "position": option["position"],
                }

        if raw in synonyms:
            target_color = synonyms[raw]
            for option in options:
                if option["color"] == target_color:
                    _logger.info(
                        "[ALQUILER-WA] Color seleccionado por sinónimo input=%r color=%s",
                        raw, option["color"],
                    )
                    return {
                        "valid": True,
                        "color": option["color"],
                        "label": option["label"],
                        "position": option["position"],
                    }

        _logger.info(
            "[ALQUILER-WA] Color no reconocido input=%r", raw,
        )
        return {
            "valid": False,
            "error": "color_not_found",
            "message": "No reconozco ese color. Responde con el número de la opción.",
        }

    def whatsapp_get_summary_text(self):
        """
        Devuelve un texto descriptivo breve del equipo, para usar en confirmaciones.
        Ejemplo: "Ricoh MP 4054 · S/N: ABC123 · Oficina Central"
        """
        self.ensure_one()

        modelo_name = ""
        if self.name:
            modelo_name = self.name.name if hasattr(self.name, 'name') else str(self.name)

        parts = [modelo_name or "Modelo desconocido"]
        if self.serie:
            parts.append("S/N: %s" % self.serie)
        if self.ubicacion_instalacion:
            parts.append(self.ubicacion_instalacion)

        return " · ".join(parts)