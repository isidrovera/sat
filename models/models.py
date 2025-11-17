# -*- coding: utf-8 -*-

from odoo import _, models, fields, api
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)
import xlwt
from io import BytesIO
import base64
import re
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
import tempfile
import os
import io
import pytz
import qrcode
import requests
class SatSat(models.Model):
    _name = 'sat.sat'
    _description = 'Registro de maquina'
    
    _inherit = ['mail.thread', 'mail.activity.mixin', 'product.catalog.mixin']

    name = fields.Many2one('modelo.maquina', string='Modelo', required=True, tracking=True, 
     )
       

    @api.constrains('serie_id')
    def unique_field_serie_id(self):
        for item in self:
            items = self.search(
                [('serie_id', '=', item.serie_id), ('id', '!=', item.id)])
            if len(items) >= 1:
                raise ValidationError(_("El número de serie debe ser único."))


    reparaciones_count = fields.Integer(string='Reparaciones', compute='_compute_reparaciones_count')

    reparaciones_ids = fields.One2many('reparaciones.reparaciones', 'maquina_id')

    def _compute_reparaciones_count(self):
        for record in self:
            record.reparaciones_count = len(self.reparaciones_ids)

    def view_reparaciones_ids(self):
        self.ensure_one()
        # Buscar un registro de reparaciones que cumpla con el dominio
        reparacion = self.env["reparaciones.reparaciones"].search([("maquina_id", "=", self.id)], limit=1)
        
        return {
            "type": "ir.actions.act_window",
            "name": "Reparaciones",
            "view_mode": "form",
            "res_model": "reparaciones.reparaciones",
            "res_id": reparacion.id if reparacion else False,  # ID del registro a mostrar en el formulario
            "domain": [("maquina_id", "=", self.id)],
            "context": {'create': True},
        }

    autorizacion_cambio_digitos = fields.Boolean(string="Autorización de Modificación", default=False)
    

    @api.model
    def _default_currency_id(self):
        value = self.env['res.currency'].search(
            [('name', '=', 'USD')], limit=1)
        return value and value.id or False
    currency_id = fields.Many2one('res.currency', string='Currency', default=_default_currency_id)
    trabajadores_id = fields.Many2one('hr.employee', string='Trabajadores', tracking=True,  default=1)

    def obtener_estado_ventas_display(self, estado_ventas_id):
        """Obtener el texto legible para el estado de ventas"""
        field = self._fields['estado_ventas_id']
        return dict(field.selection).get(estado_ventas_id)
    # Campos existentes en tu modelo sat.sat
    
    # Método para obtener registros filtrados
    def get_filtered_records(self):
        domain = [('disponibilidad_id', '=', 'no_disponible'), ('estado_ventas_id', '!=', 'entregada')]
        records = self.search(domain)
        return records
    
    # Método para enviar registros filtrados por correo
    def send_records_by_email(self):
        records = self.get_filtered_records()
        table_html = self.generate_html_table(records)
        excel_file = self.generate_excel_file(records)  # Nuevo método para generar el archivo Excel
        self.send_email(table_html, excel_file)  # Se pasa el archivo Excel como parámetro
        
    def generate_excel_file(self, records):
        from openpyxl import Workbook
        from openpyxl.utils import get_column_letter

        workbook = Workbook()
        worksheet = workbook.active

        # Agregar encabezados
        headers = ['Importación', 'Proveedor', 'Marca', 'Nombre', 'Serie', 'Contómetro', 'Descripción','Estado']
        for col_num, header in enumerate(headers, 1):
            col_letter = get_column_letter(col_num)
            worksheet[f'{col_letter}1'] = header

        # Agregar datos de los registros
        for row_num, record in enumerate(records, 2):
            worksheet[f'A{row_num}'] = record.importacion
            worksheet[f'B{row_num}'] = record.proveedor_id.name
            worksheet[f'C{row_num}'] = record.marca
            worksheet[f'D{row_num}'] = record.name.name
            worksheet[f'E{row_num}'] = record.serie_id
            worksheet[f'F{row_num}'] = record.contometro
            worksheet[f'G{row_num}'] = record.descripcion
            worksheet[f'H{row_num}'] = self.obtener_estado_ventas_display(record.estado_ventas_id)

        excel_buffer = BytesIO()
        workbook.save(excel_buffer)
        excel_buffer.seek(0)

        return excel_buffer

    
    # Método para generar tabla HTML
    def generate_html_table(self, records):
        table_html = '<table style="border-collapse: collapse; width: 100%;">'
        table_html += '<tr>'
        table_html += '<th style="border: 1px solid black; padding: 8px;">Importación</th>'
        table_html += '<th style="border: 1px solid black; padding: 8px;">Proveedor</th>'
        table_html += '<th style="border: 1px solid black; padding: 8px;">Marca</th>'
        table_html += '<th style="border: 1px solid black; padding: 8px;">Nombre</th>'
        table_html += '<th style="border: 1px solid black; padding: 8px;">Serie</th>'
        table_html += '<th style="border: 1px solid black; padding: 8px;">Contómetro</th>'
        table_html += '<th style="border: 1px solid black; padding: 8px;">Descripción</th>'
        table_html += '<th style="border: 1px solid black; padding: 8px;">Estado</th>'
        table_html += '</tr>'

        for record in records:
            table_html += '<tr>'
            table_html += f'<td style="border: 1px solid black; padding: 8px;">{record.importacion}</td>'
            table_html += f'<td style="border: 1px solid black; padding: 8px;">{record.proveedor_id.name}</td>'
            table_html += f'<td style="border: 1px solid black; padding: 8px;">{record.marca}</td>'
            table_html += f'<td style="border: 1px solid black; padding: 8px;">{record.name.name}</td>'
            table_html += f'<td style="border: 1px solid black; padding: 8px;">{record.serie_id}</td>'
            table_html += f'<td style="border: 1px solid black; padding: 8px;">{record.contometro}</td>'
            table_html += f'<td style="border: 1px solid black; padding: 8px;">{record.descripcion}</td>'
            table_html += f'<td style="border: 1px solid black; padding: 8px;">{self.obtener_estado_ventas_display(record.estado_ventas_id)}</td>'
            table_html += '</tr>'

        table_html += '</table>'
        return table_html

    # Método para enviar correo
    def send_email(self, table_html, excel_file):
        Attachment = self.env['ir.attachment']
        data = {
            'name': 'Maquinas con problemas.xlsx',
            'datas': base64.b64encode(excel_file.getvalue()),
            'res_model': 'sat.sat',
            'res_id': self.id,
        }
        attachment = Attachment.create(data)

        template = self.env.ref('sat.email_maquinas_id')

        # Elimina los adjuntos existentes
        template.attachment_ids.unlink()

        full_html = template.body_html
        # Elimina cualquier tabla existente en el contenido del correo
        full_html = re.sub(r'<table.*?</table>', '', full_html, flags=re.DOTALL)
        # Agrega la nueva tabla al contenido del correo
        full_html += table_html

        template.write({
            'body_html': full_html,
            'attachment_ids': [(4, attachment.id)]
        })
        template.send_mail(self.id, force_send=True)



    
    @api.model
    def execute_task(self):
        weekday = datetime.today().weekday()  # 0 is Monday, 6 is Sunday
        if 0 <= weekday < 5:  # Only run on weekdays
            records = self.get_filtered_records()
            table_html = self.generate_html_table(records)
            excel_file = self.generate_excel_file(records)
            self.send_email(table_html, excel_file)
        else:
            _logger.info("Skipping execution because it's a weekend.")

    nextcall = fields.Datetime('Next Call')

    def get_next_call(self):
        today = datetime.today()
        days_ahead = 7 - today.weekday() if today.weekday() < 5 else 2
        next_date = today + timedelta(days=days_ahead)
        return next_date.strftime('%Y-%m-%d') + ' 13:00:00'



    
    reparacion_id = fields.Many2one('reparaciones.reparaciones',string='Reparacion', )  

    fecha_separacion = fields.Date(string="Fecha de separado")

    serie_id = fields.Char(string='Serie', tracking=True, required=True )

    estado_ventas_id = fields.Selection([('sin_revisar', 'Sin revisar'),('para_revision', 'Para revision'),('en_revision', 'En revisión'), ('finalizado', 'Finalizado'), ('con_problemas', 'Con problemas'), ('de_partes', 'De partes'), ('entregada', 'Entregada')],
                                        string='Estado de revisión',
                                        default='sin_revisar', tracking=True
                                        )
    #_sql_constraints = [("unique_serie_id", "unique (serie_id)",
                        # "El numero de serie que intenta agregar ya existe")]

    tipo_revision = fields.Selection([('paso_papel', 'Paso papel'), (
        'regular', 'Regular'), ('cliente_final', 'Cliente final')], tracking=True)
    prioridad = fields.Selection(
        [('bajaubicacion', 'Baja'), ('alta', 'Alta')], tracking=True)
    disponibilidad_id = fields.Selection([('disponible', 'Disponible'),
                                         ('separada', 'Separada'),
                                         ('no_disponible', 'No disponible')],
                                         default='disponible', tracking=True,
                                         readonly=True, compute='_compute_disponibilidad_id', store=True
                                         )
    ubicacion_id = fields.Selection([('primer_piso', 'Primer piso'), ('tercer_piso', 'Tercer piso'), ('segundo_local', 'Segundo local'), ('covida', 'Covida')],
                                    default='primer_piso', tracking=True,
                                    )
    importacion = fields.Char('Importación', required=True, tracking=True)
    invoice = fields.Char('Invoice', required=True, tracking=True)

    precio_compra = fields.Float('Precio de compra', tracking=True)
    proveedor_id = fields.Many2one('res.partner', string='Proveedor', tracking=True, required=True
                                   )
    cliente_id = fields.Many2one('res.partner', string='Cliente', tracking=True)
    cliente_nombre = fields.Char(related='cliente_id.name', string='Cliente', size=10)
    asesora_id = fields.Char(related='cliente_id.asesora_id.name', readonly=True, store=True,  string='Asesora de ventas'
                             )
    
    factura_venta = fields.Char('Factura N°', tracking=True)
    fecha_entrega = fields.Date('Fecha de entrega', tracking=True)
    activador = fields.Selection([('si', 'Si'), ('no', 'No')],
                                 string=' ',
                                 default='no', tracking=True
                                 )
    descripcion = fields.Text(string='Descripción', tracking=True)
    check_ingreso = fields.Boolean(
        string='Ingreso registrado',
        help='Indica si el equipo ya fue ingresado/descargado mediante el scanner.'
    )

    ingreso_estado = fields.Selection([
        ('none', 'Sin check'),
        ('ok_no_obs', 'OK (sin observaciones)'),
        ('ok_obs', 'OK (con observaciones)'),
        ('rechazado', 'Rechazado'),
    ], string='Estado de ingreso', default='none', tracking=True)


    ingreso_fecha = fields.Datetime(
        string='Fecha de ingreso',
        tracking=True,
        help='Fecha y hora en que se confirmó el ingreso mediante el scanner.'
    )

    ingreso_fuente = fields.Selection(
        [
            ('qr', 'QR / Código de barras'),
            ('ocr', 'OCR (foto)'),
            ('manual', 'Manual'),
        ],
        string='Fuente de ingreso',
        tracking=True,
        help='Origen del registro de ingreso (QR, OCR o manual).'
    )
    @api.onchange('descripcion')
    def _onchange_descripcion(self):
        _logger.debug('Onchange Description for Record IDs: %s', self.ids)
        # Verifica cada registro en el conjunto
        for record in self:
            if record.descripcion:
                record.activador = 'si'
            else:
                record.activador = 'no'
        # Registra el estado final después de evaluar la descripción
        _logger.debug('Activador set to: %s', ', '.join([rec.activador for rec in self]))

    contometro = fields.Char(string='Contometro', required=True, tracking=True,)
    ultima_actualizacion_snmp = fields.Datetime(
        string='Última Actualización SNMP',
        readonly=True,
        help='Fecha y hora de la última vez que SNMP actualizó el contador',
        copy=False
    )

    contador_antes_snmp = fields.Char(
        string='Contador Previo a SNMP',
        readonly=True,
        help='Valor del contador antes de la última actualización SNMP',
        copy=False
    )

    total_actualizaciones_snmp = fields.Integer(
        string='Total Actualizaciones SNMP',
        readonly=True,
        default=0,
        help='Cantidad de veces que SNMP ha actualizado esta máquina',
        copy=False
    )

    ultima_fuente_actualizacion = fields.Selection([
        ('manual', 'Manual'),
        ('snmp', 'SNMP'),
        ('reparacion', 'Reparación'),
    ], string='Última Fuente', readonly=True, default='manual', copy=False)
    marca = fields.Char(string='Marca', related='name.marca_id.name', readonly=True, store=True, tracking=True
                        )
    precio_venta = fields.Float(string='Precio de venta', related='name.precio_venta', readonly=True, tracking=True)
    tipo_id = fields.Selection([('color', 'Color'), ('monocromatica', 'Monocromatica')],
                               string='Tipo de maquina', related='name.tipo_id', readonly=True, tracking=True)
    
    tipo_maquina = fields.Char(related='name.tipo_maquina_id.name', readonly=True, string='Tipo de maquina', tracking=True)

    asesora_mobile_clean = fields.Char(
    string='Número de celular asesora (limpio)',
    compute='_compute_asesora_mobile_clean',
    store=True
)
    foto_problema = fields.Binary(
        string='Foto problema',
    )
    
    @api.depends('cliente_id.asesora_id.mobile')
    def _compute_asesora_mobile_clean(self):
        for record in self:
            if record.cliente_id.asesora_id.mobile:
                phone = record.cliente_id.asesora_id.mobile.replace('+', '')
                phone = ''.join(phone.split())
                if not phone.startswith('51'):
                    phone = '51' + phone
                record.asesora_mobile_clean = phone
            else:
                record.asesora_mobile_clean = ''

    



    
    @api.depends('cliente_id', 'estado_ventas_id')
    def _compute_disponibilidad_id(self):
        for record in self:
            old_disponibilidad = record.disponibilidad_id
            _logger.debug('Computing Disponibilidad para ID: %s', record.id)

            if record.estado_ventas_id in ['sin_revisar', 'en_revision', 'finalizado', 'para_revision'] and record.cliente_id:
                _logger.debug('Estado requiere separación, actualizando disponibilidad a separada para ID: %s', record.id)
                record.disponibilidad_id = 'separada'

                if old_disponibilidad != 'separada':
                    record.fecha_separacion = fields.Date.today()
                    _logger.info(f"[TOKEN AUTO] Máquina ID {record.id} separada. Fecha separacion: {record.fecha_separacion}")

                    # 🚨 Generar token si está en ubicación que lo requiere
                    if record.ubicacion_id in ['segundo_local', 'covida'] and not record.location_change_token:
                        _logger.info(f"[TOKEN AUTO] Generando token automáticamente para ID {record.id} en ubicación {record.ubicacion_id}")
                        record.generate_location_change_token()

            elif record.estado_ventas_id in ['sin_revisar', 'en_revision', 'finalizado', 'para_revision'] and not record.cliente_id:
                _logger.debug('Cliente no asignado, disponibilidad = disponible para ID: %s', record.id)
                record.disponibilidad_id = 'disponible'
                record.fecha_separacion = False

            else:
                _logger.debug('Estado fuera de revisión. Disponibilidad = no_disponible para ID: %s', record.id)
                record.disponibilidad_id = 'no_disponible'
                record.fecha_separacion = False

            _logger.debug('Disponibilidad ID final: %s para ID: %s', record.disponibilidad_id, record.id)


    @api.onchange('factura_venta')
    def onchange_factura_venta(self):
        if self.factura_venta:
            self.estado_ventas_id = 'entregada'
            
            
    
    def generate_record_url(self, record):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action_id = self.env.ref('sat.action_window').id
        menu_id = self.env.ref('sat.stock_maquinas').id
        url = "{}/web#id={}&view_type=form&model=sat.sat&action={}&menu_id={}".format(base_url, record.id, action_id, menu_id)
        return url
    qr_image = fields.Binary("QR Image", compute="generate_qr_code", attachment=True, store=True)


    @api.depends('estado_ventas_id')  # Suponiendo que quieras codificar un campo específico, reemplaza 'nombre_del_campo_a_codificar' con el campo relevante.
    def generate_qr_code(self):
        for record in self:
            # Generar la URL del registro
            url = self.generate_record_url(record)
            
            if not url:
                continue
            
            # Crear un objeto de código QR
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            
            # Generar la imagen del código QR
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Guardar la imagen en un buffer en memoria
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            
            # Codificar la imagen en base64
            img_base64 = base64.b64encode(buffer.read())
            
            # Guardar la imagen codificada en el campo qr_image
            record.qr_image = img_base64
    icono_rojo = fields.Html(compute='_compute_icono_rojo', string=' ')

    @api.depends('activador')  # Reemplaza con el campo real que afecta la condición
    def _compute_icono_rojo(self):
        for record in self:
            # Aquí va la lógica para determinar cuándo el ícono debe ser rojo
            if record.activador:  # Reemplaza con tu condición real
                record.icono_rojo = '<i class="fa fa-exclamation-circle icono-grande" style="color: red;"></i>'
            else:
                record.icono_rojo = False

    def action_primer(self):
        self.ubicacion_id = 'primer_piso'

    def action_tercero(self):
        self.ubicacion_id = 'tercer_piso'

    def action_segundo(self):
        self.ubicacion_id = 'segundo_local'

    def create_reparacion(self):
        self.ensure_one()  # Asegurarse de que se trabaja con un único registro.
        return {
            'name': 'Crear Reparación',
            'type': 'ir.actions.act_window',
            'res_model': 'reparaciones.reparaciones',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_maquina_id': self.id,
                
            },
        }

    fecha_para_revision = fields.Datetime(string="Fecha para Revisión", readonly=True, traking=True, store=True)


    def get_isidro_partner_id(self):
        isidro_user = self.env['res.users'].search([('name', '=', 'Isidro Vera Polo')], limit=1)
        if isidro_user:
            return isidro_user.partner_id.id
        return False

    def _get_peru_datetime(self):
        """Obtiene la fecha y hora actual en la zona horaria de Lima/Perú"""
        peru_tz = pytz.timezone('America/Lima')
        utc_now = pytz.utc.localize(datetime.utcnow())
        return utc_now.astimezone(peru_tz)

    def write(self, vals):
        estados_permitidos_para_cambio = ['sin_revisar', 'para_revision']
        estados_problema = ['con_problemas', 'de_partes']
        estado_final_no_notificar = 'entregada'

        tipo_revision_modificado = 'tipo_revision' in vals
        prioridad_modificada = 'prioridad' in vals

        isidro_partner_id = self.get_isidro_partner_id()

        # 📌 Snapshot ANTES de escribir, para detectar cambios de modelo/tipo/contómetro
        cambios_previos = {}
        for record in self:
            cambios_previos[record.id] = {
                'modelo_anterior': record.name.name if record.name else '',
                'tipo_anterior': record.tipo_id,
                'contometro_anterior': record.contometro or '0',
            }

        for record in self:
            estado_actual = record.estado_ventas_id
            nuevo_estado = vals.get('estado_ventas_id', estado_actual)

            _logger.debug(
                f"Inicio de write para ID {record.id}. "
                f"Estado actual: {estado_actual}, Nuevo estado: {nuevo_estado}, Valores: {vals}"
            )

            # Primera parte: Manejo de tipo_revision y prioridad
            if estado_actual in estados_permitidos_para_cambio:
                if tipo_revision_modificado or prioridad_modificada:
                    if vals.get('tipo_revision') or vals.get('prioridad'):
                        vals['estado_ventas_id'] = 'para_revision'
                        # Convertir la hora UTC a hora de Perú al guardar
                        utc_now = datetime.utcnow()
                        peru_tz = pytz.timezone('America/Lima')
                        peru_dt = pytz.utc.localize(utc_now).astimezone(peru_tz)
                        vals['fecha_para_revision'] = peru_dt.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')

                        _logger.info(
                            f"Estado cambiado a 'para_revision' para ID {record.id} "
                            f"por modificación en tipo_revision o prioridad."
                        )

                        if isidro_partner_id:
                            user_name = self.env.user.name
                            record_name = record.name.name
                            serie = record.serie_id
                            message = f"""Se ha colocado una nueva máquina para revisión.

Detalles del equipo:
- Nombre: {record_name}
- Serie: {serie}
- Fecha de registro: {peru_dt.strftime('%Y-%m-%d %H:%M:%S')} (hora Lima)

Modificado por: {user_name}"""
                            record.message_post(
                                body=message,
                                partner_ids=[isidro_partner_id],
                                subtype='mail.mt_comment',
                            )
                    else:
                        vals['estado_ventas_id'] = 'sin_revisar'
                        vals['fecha_para_revision'] = None
                        _logger.info(
                            f"Estado regresado a 'sin_revisar' para ID {record.id}."
                        )

            # Segunda parte: Manejo de estados de problema y notificaciones
            if 'estado_ventas_id' in vals:
                nuevo_estado = vals['estado_ventas_id']

                # Si cambia a estado de problema
                if nuevo_estado in estados_problema:
                    _logger.debug(
                        f"Cambiando a estado de problema para ID {record.id}. "
                        f"Ejecutando super().write()."
                    )
                    result = super(SatSat, self).write(vals)

                    try:
                        record.enviar_mensaje_problema_asesora()
                        _logger.info(
                            f"Notificación de problema enviada para ID {record.id}."
                        )
                    except Exception as e:
                        _logger.error(
                            f"Error al enviar notificaciones para ID {record.id}: {e}"
                        )

                    return result

                # Si cambia de un estado problemático a otro no problemático
                elif estado_actual in estados_problema and nuevo_estado not in estados_problema:
                    _logger.debug(
                        f"Saliendo de estado de problema para ID {record.id}. "
                        f"Limpiando descripción."
                    )
                    vals['descripcion'] = False
                    vals['activador'] = 'no'
                    message = _(
                        "Se limpió la descripción al cambiar el estado de '%s' a '%s'"
                    ) % (estado_actual, nuevo_estado)
                    record.message_post(body=message)

                # Nueva lógica: Enviar notificación de disponibilidad si aplica
                if estado_actual in estados_problema and nuevo_estado != estado_final_no_notificar:
                    _logger.debug(
                        f"Enviando notificación de disponibilidad para ID {record.id}."
                    )
                    try:
                        record.enviar_notificacion_disponibilidad()
                        _logger.info(
                            f"Notificación de disponibilidad enviada para ID {record.id}."
                        )
                    except Exception as e:
                        _logger.error(
                            f"Error al enviar notificación de disponibilidad para ID {record.id}: {e}"
                        )

        # Ejecutar la escritura final después de todas las validaciones y notificaciones
        _logger.debug(f"Finalizando write para registros {self.ids} con valores: {vals}")
        result = super(SatSat, self).write(vals)

        # 🔍 Después de escribir, revisar anomalías de modelo y contómetro
        for record in self:
            prev = cambios_previos.get(record.id) or {}
            modelo_anterior = prev.get('modelo_anterior', '')
            tipo_anterior = prev.get('tipo_anterior')
            contometro_anterior = prev.get('contometro_anterior', '0')

            modelo_nuevo = record.name.name if record.name else ''
            tipo_nuevo = record.tipo_id
            contometro_nuevo = record.contometro or '0'

            # 1) Cambios raros de modelo (velocidad / color)
            self._check_model_anomalies(
                record,
                modelo_anterior,
                modelo_nuevo,
                tipo_anterior,
                tipo_nuevo,
            )

            # 2) Saltos raros de contómetro
            self._check_counter_anomalies(
                record,
                contometro_anterior,
                contometro_nuevo,
            )

        return result
    
    def _check_model_anomalies(self, record, modelo_anterior, modelo_nuevo, tipo_anterior, tipo_nuevo):
        """
        Detecta casos como:
        - Canon 4525  -> 4525/4535 (cambio de velocidad dentro misma familia)
        - bizhub 364e -> bizhub C364e (cambio de mono a color)
        y avisa por chatter/correo (a Isidro).
        """
        # Si no cambió el modelo, no hacemos nada
        if not modelo_anterior or not modelo_nuevo or modelo_anterior == modelo_nuevo:
            return

        # Extraer último bloque numérico de cada modelo (núcleo de velocidad)
        def _get_core_digits(text):
            nums = re.findall(r'\d+', text or '')
            return nums[-1] if nums else None

        core_old = _get_core_digits(modelo_anterior)
        core_new = _get_core_digits(modelo_nuevo)

        posible_cambio_velocidad = False
        detalle_velocidad = ""

        if core_old and core_new and core_old != core_new:
            # Caso típico: 4525 -> 4535 (mismo largo y primeros dígitos iguales)
            try:
                if len(core_old) == len(core_new):
                    if len(core_old) == 4 and core_old[:2] == core_new[:2]:
                        posible_cambio_velocidad = True
                        detalle_velocidad = f"{core_old[-2:]} → {core_new[-2:]}"
                    else:
                        # fallback: cualquier cambio de núcleo con mismo largo
                        posible_cambio_velocidad = True
                        detalle_velocidad = f"{core_old} → {core_new}"
            except Exception:
                pass

        # Cambio de tipo (color/mono)
        cambio_tipo = False
        if tipo_anterior and tipo_nuevo and tipo_anterior != tipo_nuevo:
            cambio_tipo = True

        # Si no hay nada relevante, salir
        if not posible_cambio_velocidad and not cambio_tipo:
            return

        isidro_partner_id = record.get_isidro_partner_id()
        url = record.generate_record_url(record)

        lineas = [
            "Se detectó una actualización relevante del modelo (posiblemente por SNMP o edición manual):",
            f"• Modelo anterior: <b>{modelo_anterior}</b>",
            f"• Modelo nuevo: <b>{modelo_nuevo}</b>",
        ]

        if posible_cambio_velocidad:
            lineas.append(f"• Posible cambio de velocidad (núcleo): <b>{detalle_velocidad}</b>")

        if cambio_tipo:
            sel_tipo = dict(record._fields['tipo_id'].selection)
            txt_old = sel_tipo.get(tipo_anterior, tipo_anterior)
            txt_new = sel_tipo.get(tipo_nuevo, tipo_nuevo)
            lineas.append(f"• Cambio de tipo: <b>{txt_old}</b> → <b>{txt_new}</b>")

        lineas.append(f"• Equipo: <b>{record.name.name if record.name else ''}</b> / Serie: <b>{record.serie_id}</b>")
        lineas.append(f"• Enlace al equipo: {url}")

        body = "<br/>".join(lineas)

        record.message_post(
            body=body,
            subtype_xmlid='mail.mt_note',
            partner_ids=[isidro_partner_id] if isidro_partner_id else None,
        )

    def _check_counter_anomalies(self, record, contometro_anterior, contometro_nuevo):
        """
        Detecta variaciones sospechosas en el contómetro, por ejemplo:
        - 2,000  → 20,000  (x10)
        - 2,000  → 2,000,000 (muchos más dígitos)
        y NO molesta si es algo normal, como:
        - 40,000 → 42,000
        """

        # Limpiar a solo dígitos
        old_digits = re.sub(r'[^\d]', '', contometro_anterior or '') or '0'
        new_digits = re.sub(r'[^\d]', '', contometro_nuevo or '') or '0'

        try:
            old_val = int(old_digits)
            new_val = int(new_digits)
        except Exception:
            return

        # Si alguno es cero o el nuevo es menor, no analizamos aquí (ya tienes lógica SNMP aparte)
        if old_val <= 0 or new_val <= 0 or new_val <= old_val:
            return

        digit_diff = abs(len(str(old_val)) - len(str(new_val)))
        ratio = new_val / float(old_val) if old_val else 0.0

        # Reglas:
        # - muchos más dígitos (ej: 4 -> 7)
        # - o incremento >= x10 del valor anterior
        if digit_diff < 2 and ratio < 10.0:
            # incremento normal, no avisamos
            return

        incremento = new_val - old_val
        isidro_partner_id = record.get_isidro_partner_id()
        url = record.generate_record_url(record)

        lineas = [
            "⚠️ Se detectó una variación inusual en el contómetro:",
            f"• Valor anterior: <b>{old_val:,}</b>",
            f"• Valor nuevo: <b>{new_val:,}</b>",
            f"• Incremento: <b>{incremento:,}</b>",
            f"• Multiplicador aproximado: <b>x{ratio:.1f}</b>",
            f"• Equipo: <b>{record.name.name if record.name else ''}</b> / Serie: <b>{record.serie_id}</b>",
            f"• Enlace al equipo: {url}",
        ]

        body = "<br/>".join(lineas)

        record.message_post(
            body=body,
            subtype_xmlid='mail.mt_note',
            partner_ids=[isidro_partner_id] if isidro_partner_id else None,
        )
        # =========================
    #  NOTIFICACIONES SNMP
    # =========================

    def _send_snmp_mail(self, template_xmlid, extra_context=None):
        """
        Helper para enviar correos de SNMP usando plantillas.
        - template_xmlid: ej. 'sat.email_template_snmp_counter_anomaly'
        - extra_context: dict con datos adicionales para usar en la plantilla (ctx)
        """
        self.ensure_one()
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            _logger.warning("No se encontró la plantilla de correo SNMP: %s", template_xmlid)
            return False

        ctx = dict(self.env.context or {})
        if extra_context:
            ctx.update(extra_context)

        try:
            template.with_context(ctx).sudo().send_mail(self.id, force_send=True)
            _logger.info("Correo SNMP enviado usando plantilla %s para equipo ID %s", template_xmlid, self.id)
            return True
        except Exception as e:
            _logger.error("Error enviando correo SNMP con plantilla %s: %s", template_xmlid, e)
            return False

    def notify_snmp_counter_anomaly(self, old_counter, new_counter, reason=None):
        """
        Notifica cuando hay algo raro en el contómetro:
        - reason = 'decremento'   -> contador bajó
        - reason = 'salto_grande' -> salto muy grande (ej. 2,000 -> 200,000)
        """
        self.ensure_one()

        if reason == 'decremento':
            title = "⚠️ Contador decreció por SNMP"
        else:
            title = "⚠️ Posible inconsistencia en el contador SNMP"

        body = _(
            "%(title)s<br/>Anterior: <b>%(old)s</b><br/>Nuevo: <b>%(new)s</b>"
        ) % {
            'title': title,
            'old': f"{old_counter:,}",
            'new': f"{new_counter:,}",
        }

        # Mensaje en chatter
        self.message_post(body=body)

        # Correo por plantilla (ajusta el XMLID a tus plantillas reales)
        self._send_snmp_mail(
            'sat.email_template_snmp_counter_anomaly',
            {
                'snmp_old_counter': old_counter,
                'snmp_new_counter': new_counter,
                'snmp_reason': reason or '',
            }
        )

    def notify_snmp_model_mismatch(self, snmp_model, current_model):
        """
        Notifica cuando el modelo detectado por SNMP NO coincide con el registrado.
        Ej: MP 3055 vs MP 4055, 4525 vs 4535, etc.
        """
        self.ensure_one()

        body = _(
            "⚠️ <b>Diferencia de modelo detectada por SNMP</b><br/>"
            "Modelo actual: <b>%(cur)s</b><br/>"
            "Modelo SNMP: <b>%(snmp)s</b>"
        ) % {
            'cur': current_model or '—',
            'snmp': snmp_model or '—',
        }

        self.message_post(body=body)

        self._send_snmp_mail(
            'sat.email_template_snmp_model_change',
            {
                'snmp_current_model': current_model,
                'snmp_detected_model': snmp_model,
            }
        )

    def notify_snmp_model_suggestion(self, snmp_model):
        """
        Notifica cuando SNMP sugiere un modelo que no existe aún
        o no se pudo asignar automáticamente.
        """
        self.ensure_one()

        body = _(
            "💡 <b>Sugerencia de modelo detectada por SNMP</b><br/>"
            "Modelo sugerido: <b>%s</b>"
        ) % (snmp_model or '—')

        self.message_post(body=body)

        self._send_snmp_mail(
            'sat.email_template_snmp_model_suggestion',
            {
                'snmp_suggested_model': snmp_model,
            }
        )


    def enviar_mensaje_problema_asesora(self):
        """Envía mensaje WhatsApp (si hay cliente y asesora) y siempre intenta enviar correo electrónico."""
        
        url = self.generate_record_url(self)
        estado_actual = dict(self._fields['estado_ventas_id'].selection).get(self.estado_ventas_id)

        mensaje = f"""*¡Atención! Máquina con problemas*
        *Cliente:* {self.cliente_id.name if self.cliente_id else 'No asignado'}
        *Marca:* {self.marca}
        *Modelo:* {self.name.name}
        *Serie:* {self.serie_id}
        *Estado:* {estado_actual}
        *Descripción:* {self.descripcion or 'Sin descripción'}

        Para ver más detalles, ingrese al siguiente enlace:
        {url}"""

        # Enviar mensaje por WhatsApp si hay cliente y asesora
        if self.cliente_id and self.asesora_mobile_clean:
            try:
                self.enviar_mensaje_whatsapp(self.asesora_mobile_clean, mensaje)
                self.message_post(
                    body=f"Se envió notificación WhatsApp a la asesora {self.cliente_id.asesora_id.name}",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
            except Exception as e:
                _logger.error(f"Error al enviar WhatsApp: {str(e)}")
        else:
            _logger.warning(f"No se envió WhatsApp porque no hay cliente o asesora para ID {self.id}")

        # Enviar correo electrónico siempre
        template = self.env.ref('sat.email_template_maquinas_problema', raise_if_not_found=False)
        if template:
            try:
                template.sudo().send_mail(self.id, force_send=True)
                self.message_post(
                    body="Correo electrónico enviado notificando problema en la máquina.",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
            except Exception as e:
                _logger.error(f"Error al enviar correo electrónico: {str(e)}")
        else:
            _logger.warning(f"No se encontró la plantilla de correo para ID {self.id}")

        return True
    location_change_token = fields.Char(string="Token de cambio de ubicación", copy=False, readonly=True)
    def generate_location_change_token(self, force=False):
        """Genera un token nuevo si no existe, o si se forza regeneración."""
        import secrets
        for record in self:
            if record.location_change_token and not force:
                _logger.info(f"[TOKEN AUTO] Token ya existe para ID {record.id}, no se regenera: {record.location_change_token}")
                continue

            token = secrets.token_urlsafe(16)
            record.sudo().write({'location_change_token': token})
            token_verificado = self.env['sat.sat'].sudo().browse(record.id).location_change_token

            if token_verificado == token:
                _logger.info(f"[TOKEN AUTO] Token generado y verificado correctamente para ID {record.id}: {token}")
            else:
                _logger.error(f"[TOKEN AUTO] FALLO al guardar token para ID {record.id}. Esperado: {token}, Leído: {token_verificado}")


    def enviar_notificacion_disponibilidad(self):
        """Envía notificación de disponibilidad cuando se resuelve un problema de la máquina."""
        # Generar la URL del registro
        url = self.generate_record_url(self)
        estado_actual = dict(self._fields['estado_ventas_id'].selection).get(self.estado_ventas_id)

        # Construcción del mensaje de WhatsApp
        mensaje = f"""*¡Notificación! Problema resuelto en la máquina*
        *Cliente:* {self.cliente_id.name if self.cliente_id else 'No asignado'}
        *Marca:* {self.marca}
        *Modelo:* {self.name.name}
        *Serie:* {self.serie_id}
        *Estado anterior:* {estado_actual}
        *Nuevo estado:* {estado_actual}

        Para ver más detalles, ingrese al siguiente enlace:
        {url}"""

        # Enviar mensaje por WhatsApp solo si hay cliente y asesora
        if self.cliente_id and self.asesora_mobile_clean:
            try:
                self.enviar_mensaje_whatsapp(self.asesora_mobile_clean, mensaje)
                self.message_post(
                    body="Notificación enviada por WhatsApp indicando que se corrigió el problema.",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
            except Exception as e:
                self.message_post(
                    body=f"Error al enviar WhatsApp: {str(e)}.",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
        else:
            _logger.warning(f"No se envió WhatsApp porque no hay cliente o asesora para ID {self.id}")

        # Enviar correo electrónico siempre, incluso si no hay cliente
        template = self.env.ref('sat.email_template_maquinas_disponible', raise_if_not_found=False)
        if template:
            try:
                template.sudo().send_mail(self.id, force_send=True)
                self.message_post(
                    body="Correo electrónico enviado indicando que se corrigió el problema.",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
            except Exception as e:
                _logger.error(f"Error al enviar correo electrónico: {str(e)}")
                self.message_post(
                    body=f"Error al enviar correo electrónico: {str(e)}.",
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )
        else:
            _logger.warning(f"No se encontró la plantilla de correo para ID {self.id}")

        return True

    @api.onchange('disponibilidad_id', 'ubicacion_id')
    def _onchange_disponibilidad_ubicacion(self):
        if self.disponibilidad_id == 'separada' and self.ubicacion_id in ['segundo_local', 'covida']:
            # Solo enviamos el mensaje, no cambiamos la ubicación
            self.enviar_mensaje_transportistas()
            return self._notify_vendedora()

    def enviar_mensaje_transportistas(self):
        transportista_numeros = ['51924894872']
        mensaje = f"""Estimado transportista,

Por favor, traer la siguiente máquina:

Modelo: {self.name.name}
Serie: {self.serie_id}
Ubicación actual: {self.ubicacion_id}

Para registrar el cambio de ubicación a primer piso cuando llegue la máquina, 
haga clic en el siguiente enlace: 📍 {self.crear_url_cambio_ubicacion(self)}"""

        _logger.debug(f"Enviando mensaje a transportistas: {mensaje}")

        for numero in transportista_numeros:
            self.enviar_mensaje_whatsapp(numero, mensaje)

    def enviar_mensaje_whatsapp(self, phone, message):
        url = 'https://whatsapp.andessolutioncopiers.com/api/message'
        data = {
            'phone': phone,
            'message': message
        }
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            response.raise_for_status()
            _logger.info(f"Mensaje enviado exitosamente a {phone}")
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error al enviar mensaje de WhatsApp a {phone}: {e}")

    def crear_url_cambio_ubicacion(self, record):
        import secrets
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        _logger.info(f"[TOKEN] Iniciando generación de token para ID {record.id}")

        # Asegurarse de que no sea un NewId
        if isinstance(record.id, models.NewId):
            # Buscar por serie_id como referencia
            record = self.env['sat.sat'].sudo().search([('serie_id', '=', record.serie_id)], limit=1)
            if not record:
                _logger.error(f"[TOKEN] No se encontró el registro real para NewId: {record.id}")
                return None

        # Continuar con el ID real
        if record.location_change_token:
            token = record.location_change_token
            _logger.info(f"[TOKEN] Ya existe token para ID {record.id}: {token}")
        else:
            token = secrets.token_urlsafe(16)
            record.sudo().write({'location_change_token': token})
            token_verificado = self.env['sat.sat'].sudo().browse(record.id).location_change_token
            if token_verificado != token:
                _logger.error(f"[TOKEN] FALLO al guardar token para ID {record.id}. Esperado: {token}, Leído: {token_verificado}")
                return None
            _logger.info(f"[TOKEN] Token generado correctamente para ID {record.id}: {token}")

        url = f"{base_url}/sat/change_location/{record.id}?token={token}"
        _logger.info(f"[TOKEN] URL final generada: {url}")
        return url



    def invalidar_token_ubicacion(self):
        """Invalida el token de cambio de ubicación después de su uso"""
        try:
            self.write({'location_change_token': False})
            _logger.info(f"Token invalidado para el registro {self.id}")
            return True
        except Exception as e:
            _logger.error(f"Error al invalidar token para el registro {self.id}: {e}")
            return False

    @api.model
    def limpiar_tokens_antiguos(self):
        """Limpia tokens de cambio de ubicación más antiguos de 24 horas"""
        try:
            from datetime import datetime, timedelta
            yesterday = datetime.now() - timedelta(hours=24)
            
            registros_antiguos = self.search([
                ('location_change_token', '!=', False),
                ('write_date', '<', yesterday)
            ])
            
            if registros_antiguos:
                registros_antiguos.write({'location_change_token': False})
                _logger.info(f"Se limpiaron {len(registros_antiguos)} tokens antiguos")
                
        except Exception as e:
            _logger.error(f"Error al limpiar tokens antiguos: {e}")
    def _notify_vendedora(self):
        return {
            'warning': {
                'title': "Notificación",
                'message': "Estimada vendedora, ya se está notificando a transporte que traigan el equipo.",
                'type': 'notification'
            }
        }
    @api.model
    def cron_evaluador_diario(self):
        _logger.debug("Iniciando cron_evaluador_diario")
        self.evaluar_registros_diarios()

    def evaluar_registros_diarios(self):
        registros_primer_piso = self.search([('ubicacion_id', '=', 'primer_piso'), ('estado_ventas_id', '=', 'sin_revisar')])
        registros_tercer_piso = self.search([('ubicacion_id', '=', 'tercer_piso'), ('estado_ventas_id', '=', 'sin_revisar')])

        if not registros_primer_piso and not registros_tercer_piso:
            registros_a_traer = self.search([
                ('ubicacion_id', 'in', ['segundo_local', 'covida']),
                ('estado_ventas_id', '=', 'sin_revisar')
            ], limit=8)
            
            _logger.debug(f"Máquinas a traer: {registros_a_traer}")
            
            if registros_a_traer:
                transportista_numeros = ['51924894872']
                for registro in registros_a_traer:
                    mensaje = f"""Estimado transportista,

Por favor, traer la siguiente máquina:

Modelo: {registro.name.name}
Serie: {registro.serie_id}
Ubicación actual: {registro.ubicacion_id}

Para registrar el cambio de ubicación a primer piso cuando llegue la máquina, 
haga clic en el siguiente enlace: 📍 {self.crear_url_cambio_ubicacion(registro)}"""

                    _logger.debug(f"Enviando mensaje para la máquina {registro.name.name} con serie {registro.serie_id}")

                    for numero in transportista_numeros:
                        self.enviar_mensaje_whatsapp(numero, mensaje)
                    
                    _logger.info(f"Mensaje enviado para la máquina {registro.name.name} con serie {registro.serie_id}")
    def action_crear_reparaciones(self):
        """ Crea una reparación para cada registro seleccionado en el modelo 'sat.sat'. """
        
        reparacion_model = self.env['reparaciones.reparaciones']
        
        for record in self:
            # Crear la reparación para cada registro seleccionado
            reparacion_model.create({
                'maquina_id': record.id,  # Relaciona la reparación con el registro actual de 'sat.sat'
                # Agrega otros campos necesarios en el modelo 'reparaciones.reparaciones'
            })
            _logger.info(f"Reparación creada para la máquina {record.name.name} con serie {record.serie_id}")
        
        # Mostrar una notificación de éxito
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reparaciones creadas'),
                'message': _('Se han creado las reparaciones para las máquinas seleccionadas.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def _get_main_reparacion(self):
        """Devuelve la reparación principal para esta máquina.
           Prioriza `reparacion_id` y si no, la última reparación creada."""
        self.ensure_one()
        reparacion = self.reparacion_id
        if not reparacion and self.reparaciones_ids:
            # Tomar la última reparación (por create_date)
            reparacion = self.reparaciones_ids.sorted(lambda r: r.create_date or r.id, reverse=True)[0]
        return reparacion

    def action_print_reparacion_pdf(self):
        """Imprimir / descargar el PDF de la reparación desde la máquina."""
        self.ensure_one()
        reparacion = self._get_main_reparacion()
        if not reparacion:
            raise UserError(_("Esta máquina no tiene ninguna reparación registrada."))

        try:
            report = self.env.ref('sat.action_report_reparaciones_ventas')
        except ValueError:
            raise UserError(_("No se encontró la acción de reporte 'sat.action_report_reparaciones_ventas'."))

        # Imprime el PDF de esa reparación
        return report.report_action(reparacion)

    def action_open_reparacion_gallery(self):
        """Abrir directamente la galería de fotos de la reparación desde la máquina."""
        self.ensure_one()
        reparacion = self._get_main_reparacion()
        if not reparacion:
            raise UserError(_("Esta máquina no tiene ninguna reparación registrada."))

        # Reusa la acción ya definida en reparaciones.reparaciones
        return reparacion.action_open_gallery()