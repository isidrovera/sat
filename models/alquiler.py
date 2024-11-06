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

class UnidadAlquiler(models.Model):

    _name = 'alquiler'
    _description = 'Maquina en alquiler'

    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Many2one('modelo.maquina', string='Modelo de maquina',
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
    garantia = fields.Html(string="Descripción de garantia", tracking=True)
    contometro_venta = fields.Integer(
        string='Contometro de venta', tracking=True)

    control_mantenimiento = fields.Boolean(string="Mantenimiento mensual", default=True)
    def action_stock(self):
        self.write({'estado_alquiler_id': 'sin_revisar', 'direccion': '', 'contacto_id': '', 'celular': '',
                   'correo_': '', 'cliente_id': 1, 'fecha_inicio': ''})

    marca = fields.Char(related='name.marca_id.name', readonly=True, store=True, string='Marca')

    serie = fields.Char(string='Serie', required=True, tracking=True)

    @api.constrains('serie')
    def unique_field_serie(self):
        for item in self:
            items = self.search(
                [('serie', '=', item.serie), ('id', '!=', item.id)])
            if len(items) >= 1:
                raise ()

    contacto_id = fields.Char(string='Contacto', tracking=True)
    celular = fields.Char(string='Celular', tracking=True)
    correo_ = fields.Char(string='Correo', tracking=True)    
    cargo = fields.Char(string='Cargo', tracking=True)
    ubicacion_instalacion  = fields.Char(string="Área de instalacion")
    observaciones  = fields.Html(string="Observaciones", tracking=True)
    direccion = fields.Text(string='Dirección y Distrito', tracking=True)
    ubicacion_id = fields.Selection([('primer_piso', 'Primer piso'), ('tercer_piso', 'Tercer piso'), ('segundo_local', 'Segundo local'), ('covida', 'Covida')],
                                    default='primer_piso', tracking=True,
                                    )
    estado_alquiler_id = fields.Selection([('sin_revisar', 'Sin revisar'), ('revisada', 'Revisada'), ('lista', 'Lista'), ('alquilada', 'Alquilada'), ('con_problemas', 'Con Problemas'), ('partes', 'De Partes'), ('externo', 'Externo'), ('vendida', 'Vendida')],
                                          string='Estado de Maquina',
                                          default='sin_revisar', tracking=True)

    cliente_id = fields.Many2one(
        'res.partner', string='Cliente', required=True, tracking=True)

    ticket_count = fields.Integer(compute='compute_count')

    def compute_count(self):
        for record in self:
            record.ticket_count = self.env['ticket.alquiler'].search_count(
                [('product_alquiler', '=', self.id)])

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

    fecha_inicio = fields.Date(string='Fecha de mantenimiento')
    fecha_recurrente = fields.Date(string='Fecha recurrente', compute='_compute_fecha_recurrente', store=True)

    @api.depends('fecha_inicio')
    def _compute_fecha_recurrente(self):
        for record in self:
            if record.fecha_inicio:
                dia_elegido = record.fecha_inicio.weekday()

                # Calculamos qué ocurrencia del día de la semana es la fecha_inicio.
                week_num = (record.fecha_inicio.day - 1) // 7 + 1

                fecha_next_month = record.fecha_inicio + relativedelta(months=1, day=1)

                # Contador para la semana del mes
                contador_semana = 0

                # Buscar el día elegido del mes siguiente en la misma semana del mes
                while True:
                    if fecha_next_month.weekday() == dia_elegido:
                        contador_semana += 1
                    if contador_semana == week_num:
                        break
                    fecha_next_month += relativedelta(days=1)

                record.fecha_recurrente = fecha_next_month
            else:
                record.fecha_recurrente = False

    @api.model
    def update_fecha_recurrente(self):
        from math import ceil
        today = fields.Date.today()
        records = self.search([('fecha_recurrente', '<=', today)])

        for record in records:
            if record.fecha_recurrente:
                dia_elegido = record.fecha_recurrente.weekday()

                # Determinar qué semana del mes es
                semana_del_mes = ceil(record.fecha_recurrente.day/7.0)

                # Primer día del mes siguiente
                fecha_next_month = record.fecha_recurrente + relativedelta(months=1, day=1)

                # Contador para la semana del mes
                contador_semana = 0

                # Buscar el día elegido del mes siguiente en la misma semana del mes
                while True:
                    if fecha_next_month.weekday() == dia_elegido:
                        contador_semana += 1
                    if contador_semana == semana_del_mes:
                        break
                    fecha_next_month += relativedelta(days=1)

                record.write({'fecha_recurrente': fecha_next_month})


    @api.model
    def enviar_correo(self):
        registros = self.search(
            [('fecha_recurrente', '=', datetime.now().date() + timedelta(days=3))])
        for registro in registros:
            template = self.env.ref('sat.email_template_id')
            template.send_mail(registro.id, force_send=True)

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
            'view_mode': 'tree,form',
            'res_model': 'repuestos.alquiler',
            'domain': [('modelo_id', '=', self.id)],
            'context': "{'create': False}"
        }

    @api.model
    def send_maintenance_reminders(self):
        today = fields.Date.today()
        target_date = today + relativedelta(days=3)
        records = self.search([('fecha_recurrente', '=', target_date)])

        grouped_records = {}
        for record in records:
            key = (record.cliente_id.id, record.fecha_recurrente)
            if key not in grouped_records:
                grouped_records[key] = []
            grouped_records[key].append(record)

        mail_template = self.env.ref('sat.mail_template_maintenance_notification')
        for key, records_group in grouped_records.items():
            if records_group:
                mail_template.send_mail(records_group[0].id, force_send=True, email_values={'body_html': self._prepare_mail_body(records_group)})
                
    def _prepare_mail_body(self, records_group):
        base_template = """
            <p>Estimado(a) %s,</p>
            <p>Le informamos que tiene programado un mantenimiento preventivo para sus equipos el día <strong>%s</strong>.</p>
            <p>Detalles de los equipos:</p>
            %s
            <p>Por favor, confirme si la fecha propuesta es adecuada o informe si hay algún problema o cambio que debamos considerar.</p>
            <p>Quedamos a su disposición para cualquier consulta.</p>
            <p>Atentamente,</p>
            <p>Isidro vera polo</p>  <!-- Aquí está el cambio. Puedes reemplazar "Tu Empresa" con el nombre que desees -->
        """

        equipment_details = "<table border='1'><thead><tr><th>Marca</th><th>Modelo</th><th>Número de Serie</th></tr></thead><tbody>"
        for record in records_group:
            equipment_details += "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (record.marca, record.name.name, record.serie)
        equipment_details += "</tbody></table>"

        return base_template % (records_group[0].cliente_id.name, records_group[0].fecha_recurrente, equipment_details)
    def button_send_test_mail(self):
        mail_template = self.env.ref('sat.mail_template_maintenance_notification')
        for record in self:
            related_records = self.search([('cliente_id', '=', record.cliente_id.id)])
            mail_template.send_mail(record.id, force_send=True, email_values={'body_html': record._prepare_mail_body(related_records)})

    
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


    