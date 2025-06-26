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

    control_mantenimiento = fields.Boolean(
        string="Mantenimiento mensual", default=True)

    marca = fields.Char(related='name.marca_id.name',
                        readonly=True, store=True, string='Marca')

    serie = fields.Char(string='Serie', required=True, tracking=True)

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

    @api.model
    def send_maintenance_reminders(self):
        """Envía recordatorios de mantenimiento a los clientes con equipos programados."""
        today = fields.Date.today()
        target_date = today + timedelta(days=3)
        _logger.info(
            f"Buscando registros con fecha_recurrente entre {target_date} y {target_date + timedelta(days=1)}")

        # Buscar registros con fecha_recurrente dentro del rango
        records = self.search([
            ('fecha_recurrente', '>=', target_date),
            ('fecha_recurrente', '<', target_date + timedelta(days=1)),
            ('control_mantenimiento', '=', True)
        ])
        _logger.info(
            f"Registros encontrados para enviar recordatorios: {len(records)}")

        if not records:
            _logger.warning(
                "No se encontraron registros para enviar recordatorios.")
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
        mail_template = self.env.ref(
            'sat.mail_template_maintenance_notification')
        for client_data in grouped_records.values():
            correo = client_data['correo']
            if not correo:
                _logger.warning(
                    f"Cliente {client_data['cliente'].name} no tiene correo. Saltando...")
                continue

            primer_equipo = client_data['equipos'][0]
            try:
                mail_template.with_context(
                    equipos=client_data['equipos'],
                    fecha_mantenimiento=target_date
                ).send_mail(primer_equipo.id, force_send=True)
                _logger.info(
                    f"Correo enviado a {correo} para cliente {client_data['cliente'].name}")
            except Exception as e:
                _logger.error(
                    f"Error al enviar correo a {correo} para cliente {client_data['cliente'].name}: {e}")

    def button_send_test_mail(self):
        """Función para probar el envío de correo desde la interfaz"""
        self.ensure_one()
        # Buscar todos los equipos del mismo cliente
        equipos_cliente = self.search([
            ('cliente_id', '=', self.cliente_id.id),
            ('control_mantenimiento', '=', True)
        ])

        mail_template = self.env.ref(
            'sat.mail_template_maintenance_notification')
        mail_template.with_context(
            equipos=equipos_cliente,
            fecha_mantenimiento=self.fecha_recurrente
        ).send_mail(self.id, force_send=True)
    # En la clase UnidadAlquiler, agregar este método
    def write(self, vals):
        """Sobrescribir write para sincronizar estado de bloqueo entre equipos del mismo cliente"""
        
        # Ejecutar el write original primero
        res = super(UnidadAlquiler, self).write(vals)
        
        # Sincronizar estado de bloqueo entre equipos del mismo cliente
        if 'estado_bloqueo' in vals:
            for record in self:
                if record.cliente_id:
                    # Buscar otros equipos del mismo cliente (excluyendo el actual)
                    otros_equipos = self.search([
                        ('id', '!=', record.id),
                        ('cliente_id', '=', record.cliente_id.id),
                        ('estado_alquiler_id', '=', 'alquilada')  # Solo equipos alquilados
                    ])
                    
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
                        
                        # Actualizar usando SQL directo para evitar recursión infinita
                        placeholders = ', '.join([f"{key} = %s" for key in update_vals.keys()])
                        query = f"""
                            UPDATE alquiler 
                            SET {placeholders}
                            WHERE id = ANY(%s)
                        """
                        
                        self.env.cr.execute(query, list(update_vals.values()) + [list(otros_equipos.ids)])
                        
                        # Invalidar cache para reflejar cambios
                        otros_equipos.invalidate_cache()
                        
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
        
        return res
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
     # Campos originales de fechas
    fecha_inicio = fields.Date(
        string='Fecha de mantenimiento inicial',
        required=True,
        tracking=True,
        default=fields.Date.today,  # ← AGREGAR ESTA LÍNEA
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
    patron_recurrencia = fields.Selection([
        ('fecha_exacta', 'Día específico del mes'),
        ('semana_dia', 'Día específico de la semana')
    ], string='Patrón de recurrencia',
        default='fecha_exacta',
        required=True,
        tracking=True,
        help="Determina cómo se calculará la próxima fecha de mantenimiento"
    )

    semana_mes = fields.Selection([
        ('1', 'Primera'),
        ('2', 'Segunda'),
        ('3', 'Tercera'),
        ('4', 'Cuarta'),
        ('-1', 'Última'),
        ('-2', 'Penúltima'),
        ('-3', 'Antepenúltima')
    ], string='Posición en el mes',
        tracking=True,
        help="Posición específica del día de la semana en el mes (ej. primer lunes, último viernes, etc.)"
    )

    dia_semana = fields.Selection([
        ('0', 'Lunes'),
        ('1', 'Martes'),
        ('2', 'Miércoles'),
        ('3', 'Jueves'),
        ('4', 'Viernes'),
        ('5', 'Sábado'),
        ('6', 'Domingo')
    ], string='Día de la semana',
        tracking=True,
        help="Qué día de la semana debe programarse el mantenimiento"
    )

    fecha_recurrente = fields.Date(
        string='Próxima fecha de mantenimiento',
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
    usar_fecha_recurrente_como_base = fields.Boolean(
        string='Usar fecha recurrente como base',
        default=False,
        help="Si está activado, usará la fecha recurrente como base para calcular la próxima fecha. Si no, usará la fecha inicial."
    )

    @api.onchange('fecha_inicio', 'patron_recurrencia')
    def _onchange_fecha_inicio(self):
        """
        Cuando el usuario selecciona una fecha y el patrón 'día específico de la semana',
        este método detecta automáticamente qué día de la semana es y qué posición
        ocupa en el mes (primera, segunda, última, etc.)
        """
        if self.fecha_inicio and self.patron_recurrencia == 'semana_dia':
            # Detectar día de la semana (0-6 donde 0 es lunes)
            dia_semana = self.fecha_inicio.weekday()
            self.dia_semana = str(dia_semana)

            # Obtener todas las ocurrencias de este día de la semana en el mes
            ocurrencias = []
            year, month = self.fecha_inicio.year, self.fecha_inicio.month
            ultimo_dia = calendar.monthrange(year, month)[1]

            for dia in range(1, ultimo_dia + 1):
                fecha = datetime(year, month, dia).date()
                if fecha.weekday() == dia_semana:
                    ocurrencias.append(dia)

            # Encontrar la posición de la fecha actual en las ocurrencias
            posicion = None
            for i, dia in enumerate(ocurrencias):
                if dia == self.fecha_inicio.day:
                    posicion = i
                    break

            if posicion is not None:
                total_ocurrencias = len(ocurrencias)

                # Determinar si es mejor expresar desde el inicio o desde el final
                posicion_desde_final = -1 * (total_ocurrencias - posicion)

                # Si es una de las últimas 3 posiciones, usar expresión desde el final
                if posicion_desde_final >= -3:  # Última, penúltima o antepenúltima
                    self.semana_mes = str(posicion_desde_final)  # -1, -2 o -3
                else:
                    # Es mejor expresarlo desde el inicio
                    # +1 porque la posición empieza en 0
                    self.semana_mes = str(posicion + 1)

                # Loguear para depuración
                _logger.info(
                    f"DETECCIÓN DE PATRÓN: Fecha={self.fecha_inicio}, "
                    f"Día semana={dia_semana} ({['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'][dia_semana]}), "
                    f"Ocurrencias en mes={ocurrencias}, "
                    f"Posición={posicion+1} de {total_ocurrencias}, "
                    f"Posición asignada={self.semana_mes}"
                )

    @api.depends('fecha_inicio', 'intervalo_meses', 'patron_recurrencia', 'semana_mes', 'dia_semana', 'usar_fecha_recurrente_como_base')
    def _compute_fecha_recurrente(self):
        """
        Calcula la próxima fecha de mantenimiento basada en el patrón seleccionado,
        manteniendo la posición relativa correcta de los días en el mes.
        """
        for record in self:
            if not record.fecha_inicio:
                record.fecha_recurrente = False
                continue

            # Guardar fecha anterior para comparación
            fecha_anterior = record.fecha_recurrente

            # DETECCIÓN DE PROBLEMAS: Imprimir valores involucrados en el cálculo
            _logger.info(f"VALORES DE ENTRADA: fecha_inicio={record.fecha_inicio}, "
                         f"fecha_recurrente={record.fecha_recurrente}, "
                         f"intervalo_meses={record.intervalo_meses}, "
                         f"patron_recurrencia={record.patron_recurrencia}, "
                         f"semana_mes={record.semana_mes}, "
                         f"dia_semana={record.dia_semana}, "
                         f"usar_fecha_recurrente_como_base={record.usar_fecha_recurrente_como_base}")

            # Determinar la fecha base para el cálculo - MODIFICADO
            # Solo usar fecha_recurrente si el campo usar_fecha_recurrente_como_base está activado
            if record.usar_fecha_recurrente_como_base and record.fecha_recurrente and record.fecha_recurrente > fields.Date.today():
                base_date = record.fecha_recurrente
            else:
                base_date = record.fecha_inicio

            # Asegurarse que intervalo_meses sea un valor válido - IMPORTANTE
            intervalo_str = record.intervalo_meses or '1'
            try:
                meses = int(intervalo_str)
                # Verificación adicional para valores no válidos
                if meses <= 0 or meses > 12:
                    meses = 1  # Valor predeterminado seguro
                    _logger.warning(
                        f"Valor de intervalo no válido: {intervalo_str}, usando predeterminado: 1")
            except (ValueError, TypeError):
                meses = 1  # Valor predeterminado si hay error de conversión
                _logger.warning(
                    f"Error al convertir intervalo: {intervalo_str}, usando predeterminado: 1")

            # Determinar el mes objetivo sumando exactamente el número de meses del intervalo
            target_date = base_date + relativedelta(months=meses)
            target_year = target_date.year
            target_month = target_date.month

            # Calcular la nueva fecha según el patrón elegido
            if record.patron_recurrencia == 'fecha_exacta' or not record.patron_recurrencia:
                # Mantener el mismo día del mes
                day_of_month = base_date.day

                # Ajustar si el día no existe en el mes destino
                last_day = calendar.monthrange(target_year, target_month)[1]
                if day_of_month > last_day:
                    day_of_month = last_day

                siguiente_fecha = datetime(
                    target_year, target_month, day_of_month).date()
                record.fecha_recurrente = siguiente_fecha

            elif record.patron_recurrencia == 'semana_dia' and record.semana_mes and record.dia_semana:
                try:
                    weekday = int(record.dia_semana)  # 0=Lunes, 6=Domingo
                    # Posición (puede ser desde inicio o final)
                    position_str = record.semana_mes

                    # Encontrar todas las ocurrencias del día de la semana en el mes objetivo
                    ocurrencias = []
                    last_day = calendar.monthrange(
                        target_year, target_month)[1]

                    for dia in range(1, last_day + 1):
                        fecha = datetime(target_year, target_month, dia).date()
                        if fecha.weekday() == weekday:
                            ocurrencias.append(fecha)

                    # No hay ocurrencias de este día de la semana (raro, pero posible en teoría)
                    if not ocurrencias:
                        record.fecha_recurrente = base_date + \
                            relativedelta(months=meses)
                        _logger.warning(
                            f"No se encontraron ocurrencias de día {weekday} en {target_month}/{target_year}")
                        continue

                    # Determinar qué ocurrencia usar según la posición
                    position = int(position_str)
                    if position < 0:  # Posición desde el final (-1, -2, -3)
                        # Asegurarnos de que el índice esté dentro del rango
                        index = position
                        if abs(position) > len(ocurrencias):
                            # Usar la primera ocurrencia si no hay suficientes
                            index = -len(ocurrencias)
                        siguiente_fecha = ocurrencias[index]
                    else:  # Posición desde el inicio (1, 2, 3, 4)
                        # Ajustar el índice (position es 1-based, el índice es 0-based)
                        index = position - 1
                        if index >= len(ocurrencias):
                            # Usar la última si no hay suficientes
                            index = len(ocurrencias) - 1
                        siguiente_fecha = ocurrencias[index]

                    record.fecha_recurrente = siguiente_fecha

                except Exception as e:
                    # Si hay cualquier error en el cálculo, usar un método simple como fallback
                    _logger.error(
                        f"Error en cálculo de fecha recurrente: {str(e)}")
                    record.fecha_recurrente = base_date + \
                        relativedelta(months=meses)
            else:
                # Fallback simple
                record.fecha_recurrente = base_date + \
                    relativedelta(months=meses)

            # Log para depuración detallada
            dia_nombre = ['Lunes', 'Martes', 'Miércoles',
                          'Jueves', 'Viernes', 'Sábado', 'Domingo']
            dia_semana_nombre = ""
            if record.dia_semana:
                try:
                    dia_semana_nombre = dia_nombre[int(record.dia_semana)]
                except (IndexError, ValueError):
                    dia_semana_nombre = f"Día {record.dia_semana}"

            _logger.info(
                f"CÁLCULO FECHA: Base={base_date}, "
                f"Intervalo={meses} meses, "
                f"Mes objetivo={target_month}/{target_year}, "
                f"Patrón={record.patron_recurrencia}, "
                f"Posición={record.semana_mes}, "
                f"Día={dia_semana_nombre}, "
                f"Resultado={record.fecha_recurrente}"
            )

            # Verificación adicional del resultado
            diferencia_meses = (record.fecha_recurrente.year - base_date.year) * \
                12 + (record.fecha_recurrente.month - base_date.month)
            if diferencia_meses != meses:
                _logger.warning(
                    f"ALERTA: La diferencia de meses ({diferencia_meses}) no coincide con el intervalo ({meses}). "
                    f"Base={base_date}, Resultado={record.fecha_recurrente}"
                )

            # Actualizar estado si la fecha cambió
            if fecha_anterior and record.fecha_recurrente != fecha_anterior:
                if record.estado_programacion in ['confirmado', 'reprogramado']:
                    record.estado_programacion = 'pendiente'
                    record.message_post(
                        body=f"⚠️ Nueva fecha de mantenimiento calculada: {record.fecha_recurrente.strftime('%d/%m/%Y')}",
                        message_type='notification'
                    )

    # Agregar este nuevo método para activar el cálculo recurrente
    def iniciar_calculo_recurrente(self):
        """
        Activa el cálculo recurrente para calcular fechas futuras
        a partir de la fecha recurrente actual en vez de la fecha de inicio.
        """
        self.ensure_one()
        self.usar_fecha_recurrente_como_base = True
        self.message_post(
            body="🔄 Se ha iniciado el cálculo recurrente. Las próximas fechas se calcularán a partir de la fecha recurrente actual.",
            message_type='notification'
        )
        return True

    # Agregar este método para reiniciar la configuración
    def reiniciar_configuracion(self):
        """
        Reinicia la configuración para volver a calcular la fecha recurrente
        a partir de la fecha de inicio original.
        """
        self.ensure_one()
        self.usar_fecha_recurrente_como_base = False
        self._compute_fecha_recurrente()  # Forzar recálculo
        self.message_post(
            body="🔄 Configuración reiniciada. La fecha recurrente se calculará a partir de la fecha de inicio.",
            message_type='notification'
        )
        return True

    # Corrección para update_fecha_recurrente

    @api.model
    def update_fecha_recurrente(self):
        """
        Actualiza la fecha de mantenimiento recurrente para registros con fechas pasadas.
        """
        today = fields.Date.today()
        records = self.search([
            ('fecha_recurrente', '<=', today),
            ('estado_programacion', 'in', ['confirmado', 'pendiente']),
            ('control_mantenimiento', '=', True)
        ])

        for record in records:
            # Simplemente activar el cálculo del compute
            record.write({
                'estado_programacion': 'pendiente',
                'fecha_confirmacion': False
            })

            # Forzar recálculo de la fecha recurrente
            record._compute_fecha_recurrente()

            record.message_post(
                body=f"🔄 Mantenimiento actualizado para: {record.fecha_recurrente.strftime('%d/%m/%Y')}",
                message_type='notification'
            )

    def aplicar_configuracion_a_todos(self):
        """
        Aplica la configuración de mantenimiento del registro actual a todos
        los otros equipos del mismo cliente.
        """
        self.ensure_one()

        # Verificar que haya un cliente asignado
        if not self.cliente_id:
            raise UserError(
                _("Debe seleccionar un cliente antes de aplicar la configuración a todos los equipos."))

        # Verificar que la configuración de mantenimiento esté completa
        if not self.fecha_inicio or not self.intervalo_meses:
            raise UserError(
                _("Complete la configuración de mantenimiento antes de aplicarla a otros equipos."))

        # Buscar todos los otros equipos del mismo cliente que tienen mantenimiento activado
        otros_equipos = self.search([
            ('id', '!=', self.id),
            ('cliente_id', '=', self.cliente_id.id),
            ('control_mantenimiento', '=', True)
        ])

        if not otros_equipos:
            raise UserError(
                _("No se encontraron otros equipos con mantenimiento activado para este cliente."))

        # Valores a copiar
        valores = {
            'fecha_inicio': self.fecha_inicio,
            'intervalo_meses': self.intervalo_meses,
            'patron_recurrencia': self.patron_recurrencia,
            'usar_fecha_recurrente_como_base': self.usar_fecha_recurrente_como_base
        }

        # Si el patrón es "día específico de la semana", también copiar estos campos
        if self.patron_recurrencia == 'semana_dia':
            valores.update({
                'semana_mes': self.semana_mes,
                'dia_semana': self.dia_semana
            })

        # Aplicar la configuración a todos los otros equipos
        otros_equipos.write(valores)

        # Forzar el recálculo de la fecha recurrente en todos los equipos actualizados
        for equipo in otros_equipos:
            equipo._compute_fecha_recurrente()

        # Mostrar mensaje de confirmación
        message = _(
            f"Configuración de mantenimiento aplicada a {len(otros_equipos)} equipo(s) del cliente {self.cliente_id.name}.")

        # Registrar la acción en el historial
        self.message_post(
            body=f"✅ {message}",
            message_type='notification'
        )

        # Mostrar mensaje al usuario
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuración aplicada'),
                'message': message,
                'sticky': False,
                'type': 'success',
            }
        }

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

            # ✅ CORREGIDO: Actualizar TODOS los equipos
            equipos.write({
                'estado_programacion': 'confirmado',
                'fecha_confirmacion': fields.Datetime.now()
            })

            # ✅ Opcional: enviar email solo una vez
            template = self.env.ref(
                'sat.mail_template_maintenance_confirmation')
            template.send_mail(self.id, force_send=True)

            # ✅ Opcional: log solo en el primer equipo
            self.message_post(
                body=f"✅ Mantenimiento confirmado para {self.fecha_recurrente.strftime('%d/%m/%Y')}",
                message_type='notification'
            )

            return True
        except Exception as e:
            _logger.error(
                "Error al crear tickets de mantenimiento: %s", str(e))
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
            _logger.error(
                "Error al enviar solicitud de reprogramación: %s", str(e))
            return False

    def process_maintenance_response(self, response_type):
        """Procesa la respuesta del cliente desde el correo"""
        self.ensure_one()
        # Validaciones
        if self.estado_programacion == 'confirmado' and response_type == 'confirm':
            raise ValidationError(_("Este mantenimiento ya está confirmado"))
        if self.estado_programacion == 'reprogramado' and response_type == 'confirm':
            raise ValidationError(
                _("Este mantenimiento está pendiente de reprogramación"))

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


   
class SolicitudPartes(models.Model):
    _name = 'solicitud.partes'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Solicitud de Partes'
    _order = 'fecha_solicitud desc, id desc'

    name = fields.Char(string='Número de Solicitud',
                       readonly=True, copy=False, default='Nuevo')

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

    fecha_solicitud = fields.Datetime(
        string='Fecha de Solicitud', default=fields.Datetime.now, tracking=True, readonly=True)
    solicitante_id = fields.Many2one('res.users', string='Solicitante',
                                     default=lambda self: self.env.user, tracking=True, readonly=True)

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('submitted', 'Enviado'),
        ('approved', 'Aprobado'),
        ('completed', 'Completado'),
        ('replaced', 'Reemplazado'),
        ('rejected', 'Rechazado')
    ], string='Estado', default='draft', tracking=True)

    # Campos de autorización
    autorizado_por = fields.Many2one(
        'res.users', string='Autorizado por', tracking=True, readonly=False)
    fecha_autorizacion = fields.Datetime(
        string='Fecha de Autorización', tracking=True, readonly=False)

    # Campos de retiro
    retirado_por = fields.Many2one(
        'res.users', string='Retirado por', tracking=True, readonly=False)
    fecha_retiro = fields.Datetime(
        string='Fecha de Retiro', tracking=True, readonly=False)

    # Campos de reemplazo
    reemplazado_por = fields.Many2one(
        'res.users', string='Reemplazado por', tracking=True, readonly=False)
    fecha_reemplazo = fields.Datetime(
        string='Fecha de Reemplazo', tracking=True, readonly=False)

    parte_ids = fields.One2many(
        'solicitud.partes.linea', 'solicitud_id', string='Partes Solicitadas')
    access_token = fields.Char('Token de Acceso', copy=False, readonly=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'Nuevo') == 'Nuevo':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'solicitud.partes') or 'Nuevo'
        vals['access_token'] = uuid.uuid4().hex
        return super().create(vals)

    def action_submit(self):
        self.ensure_one()
        if not self.parte_ids:
            raise UserError(
                _('Debe agregar al menos una parte antes de enviar la solicitud.'))
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
            raise UserError(
                _('Todas las partes deben estar retiradas o reemplazadas.'))
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

    @api.model
    def approve_from_token(self, token):
        solicitud = self.search([
            ('access_token', '=', token),
            ('state', '=', 'submitted')
        ], limit=1)

        if solicitud:
            try:
                solicitud.action_approve()
                return {'success': True}
            except Exception as e:
                return {'error': str(e)}
        return {'error': 'Token inválido o solicitud no encontrada'}


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

    # Relación con máquina origen a través de solicitud
    maquina_origen_id = fields.Many2one(
        'alquiler',
        string='Máquina Origen',
        related='solicitud_id.maquina_origen_id',
        store=True
    )

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
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'inspeccion.resultado') or 'Nuevo'
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
    servidor_email_propio = fields.Char(
        'Servidor SMTP propio', help='Solo si usará su propio servidor de correo')

    # Espacio Físico y Acceso
    piso = fields.Integer('Número de piso')
    ascensor = fields.Boolean('Tiene ascensor')
    espacio = fields.Float('Espacio disponible (m²)')
    ancho_pasillo = fields.Float('Ancho de pasillo (m)')
    tiene_estacionamiento = fields.Boolean(
        '¿Tiene estacionamiento para camión?')
    observaciones_estacionamiento = fields.Text(
        'Observaciones de estacionamiento')

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
                raise ValidationError(
                    "Debe haber al menos una computadora conectada (Windows, Mac o Linux).")

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
                problemas.append(
                    "Espacio insuficiente: mínimo 2m² y pasillo de 1m de ancho.")

            total_pcs = record.cantidad_windows + record.cantidad_mac + record.cantidad_linux
            if total_pcs <= 0:
                problemas.append("No hay computadoras conectadas.")

            nuevo_estado = 'aprobado' if not problemas else 'rechazado' if any(
                "Requiere" in p or "No tiene" in p for p in problemas) else 'requiere_cambios'
            nuevo_requisitos = '\n'.join(problemas) if problemas else False

            self.env.cr.execute("""
                UPDATE inspeccion_resultado 
                SET estado = %s, requisitos_pendientes = %s 
                WHERE id = %s
            """, (nuevo_estado, nuevo_requisitos, record.id))

    @api.onchange('punto_corriente', 'punto_red', 'wifi', 'espacio', 'ancho_pasillo', 'cantidad_windows', 'cantidad_mac', 'cantidad_linux')
    def _onchange_estado(self):
        self._update_estado()
