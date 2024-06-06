from odoo import _, models, fields, api, exceptions

from dateutil.relativedelta import relativedelta
from odoo.http import request
from datetime import datetime, timedelta
from odoo.exceptions import UserError
import webbrowser
from datetime import datetime
from pytz import timezone, UTC
from datetime import datetime
#import telegram
import requests
import json
import logging

_logger = logging.getLogger(__name__)

class ticket_alquiler(models.Model):

    _name = 'ticket.alquiler'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _inherit_id='web.assets_backend'

    name = fields.Char( 'TICKET N°', default='New',
        copy=False,
        required=True,
        readonly=True)
    
    @api.model
    def create(self, vals):
        # We generate a standard reference
        vals['name'] = self.env['ir.sequence'].next_by_code('ticket.alquiler')or '/'
        return super(ticket_alquiler,self).create(vals) 
      
    

    reporter_name = fields.Char(string="Nombre de quien reporta")
    reporter_phone = fields.Char(string="Numero de quien reporto")
    problem_photo = fields.Binary(string="Foto del problema")

    responsable = fields.Many2one("res.users", string="Técnico", tracking=True, index=True)
    nombre_responsable = fields.Char(string="Nombre del Técnico", related="responsable.name", store=True)
    
    priority = fields.Selection([("0", ("Low")),("1", ("Medium")),("2", ("High")),("3", ("Very High"))],string="Prioridad",default="1")
    partner_id = fields.Many2one("res.partner", string="Empresa", tracking=True 
    )
    nombre_cliente  = fields.Char(related='partner_id.name', 
    string='Nombre de cliente', store=True
    )
    
    
    description = fields.Text(tracking=True
    )
    informe_id = fields.Html(string='Notas de reparación', tracking=True)   

    estado = fields.Selection(string='Estado', selection=[('nuevo', 'Nuevo'),
    ('proceso','En Proceso'),('finalizado','Finalizado')],  tracking=True,
    default='nuevo'
    )
    codigo_id = fields.Many2one('sale.order', string="Código")

    product_alquiler = fields.Many2one('alquiler', string='Maquina a reparar', tracking=True)
    
    tipo_id = fields.Selection([('color', 'Color'),('monocromatica','Monocromatica')], 
     string='Tipo de maquina', related='product_alquiler.tipo_maquina_id')
    serie_id_r = fields.Char(related='product_alquiler.serie', string="Serie", store=True)    
    marca_id_r = fields.Char(related='product_alquiler.marca', string="Marca", store=True)
    modelo_id_r  = fields.Char(related='product_alquiler.name.name',string='Modelo', store=True)
    direccion_id_r = fields.Char(string="Dirección")
    contacto_id_r = fields.Char(string="Contacto")
    celular_id_r = fields.Char(string="Celular")
    corre_id_r = fields.Char(string="Correo")
    piso_id_r = fields.Char(string="Piso")
    oficina_id_r = fields.Char(string="Oficina")
    area_id_r = fields.Char(string="Área")
    estern_id_r = fields.Boolean( string="Cliente externo", tracking=True)
    tray_id = fields.Char("Caseteras N°", tracking=True)
    adf_simple_id = fields.Selection([("si", "Si"), ("no", "No")], string="ADF Simple", tracking=True)
    transformador_id = fields.Selection([("si", "Si"), ("no", "No")], string="Transformador", tracking=True)
    estabilizador = fields.Selection([("si", "Si"), ("no", "No")], string="Estabilizador", tracking=True)
    adf_dual_id = fields.Selection([("si", "Si"), ("no", "No")], string="ADF Dual scan", tracking=True)
    finalizador_interno_id = fields.Selection([("si", "Si"), ("no", "No")], string="Finalizador Interno", tracking=True)
    finalizador_externo_id = fields.Selection([("si", "Si"), ("no", "No")], string="Finalizador Externo", tracking=True)
    mueble_id = fields.Selection([("si", "Si"), ("no", "No")], string="Mueble", tracking=True)
    panel_smart_id = fields.Selection([("si", "Si"), ("no", "No")], string="Panel Smart", tracking=True)
    panel_normal_id = fields.Selection([("si", "Si"), ("no", "No")], string="Panel Normal", tracking=True)
    wi_fi_id = fields.Selection([("si", "Si"), ("no", "No")], string="Wi-Fi", tracking=True)
    bluetooth_id = fields.Selection([("si", "Si"), ("no", "No")], string="Bluetooth", tracking=True)
    cable_usb_id = fields.Selection([("si", "Si"), ("no", "No")], string="Cable USB de impresión", tracking=True)
    cable_red_id = fields.Selection([("si", "Si"), ("no", "No")], string="Cable de red", tracking=True)
    toner_black_id = fields.Selection(
        [("nuevo", "Nuevo"), ("regular", "Regular"), ("vacio", "Vacío"), ("sin_stock", "Sin stock"),("no_aplica","No aplica")],
        string="Toner Black", tracking=True)
    toner_black_id = fields.Selection(
        [("nuevo", "Nuevo"), ("regular", "Regular"), ("vacio", "Vacío"), ("sin_stock", "Sin stock")],
        string="Toner Black", tracking=True)
    toner_magenta_id = fields.Selection(
        [("nuevo", "Nuevo"), ("regular", "Regular"), ("vacio", "Vacío"), ("sin_stock", "Sin stock"),("no_aplica","No aplica")],
        string="Toner Magenta", tracking=True)
    toner_cyan_id = fields.Selection(
        [("nuevo", "Nuevo"), ("regular", "Regular"), ("vacio", "Vacío"), ("sin_stock", "Sin stock"),("no_aplica","No aplica")],
        string="Toner Cyan", tracking=True)
    toner_yellow_id = fields.Selection(
        [("nuevo", "Nuevo"), ("regular", "Regular"), ("vacio", "Vacío"), ("sin_stock", "Sin stock"),("no_aplica","No aplica")],
        string="Toner Yellow", tracking=True)
    copia_id = fields.Selection([("correcto", "Correcto"), ("observacion", "Observación"), ("regular", "Regulación")],
                                string="Copia", tracking=True)
    impresion_id = fields.Selection(
        [("correcto", "Correcto"), ("observacion", "Observación"), ("sin_probar", "Sin probar")],
        string="Impresión", tracking=True)
    impresion_usb_id = fields.Selection(
        [("correcto", "Correcto"), ("observacion", "Observación"), ("sin_probar", "Sin probar")],
        string="Impresión USB", tracking=True)
    scaner_smb_id = fields.Selection(
        [("correcto", "Correcto"), ("observacion", "Observación"), ("sin_probar", "Sin probar")],
        string="Scanner SMB", tracking=True)
    scaner_usb_id = fields.Selection(
        [("correcto", "Correcto"), ("observacion", "Observación"), ("sin_probar", "Sin probar")],
        string="Scanner USB", tracking=True)
    scaner_ftp_id = fields.Selection(
        [("correcto", "Correcto"), ("observacion", "Observación"), ("sin_probar", "Sin probar"),("no_aplica","No aplica")],
        string="Scanner FTP", tracking=True)
    scaner_mail_id = fields.Selection(
        [("correcto", "Correcto"), ("observacion", "Observación"), ("sin_probar", "Sin probar"),("no_aplica","No aplica")],
        string="Scanner Mail", tracking=True)
    adf_id = fields.Selection(
        [("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
         ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado")],
        string="ADF", tracking=True)
    tray1_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                 ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado")],
                                string="Tray 1", tracking=True)
    tray2_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                 ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado"),("no_aplica","No aplica")],
                                string="Tray 2", tracking=True)
    tray3_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                 ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado"),("no_aplica","No aplica")],
                                string="Tray 3", tracking=True)
    tray4_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                 ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado"),("no_aplica","No aplica")],
                                string="Tray 4", tracking=True)
    bypass_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                  ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado")],
                                 string="Bypass", tracking=True)
    finalizador_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                       ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado"),("no_aplica","No aplica")],
                                      string="Finalizador", tracking=True)

    tacho_id = fields.Selection(
        [("sin_revisar", "Sin revisar"), ("se_cambio", "Se cambio"), ("se_boto_contenido", "Se boto contenido"),("no_aplica","No aplica"),
        ("revisado", "Revisado")],
        string="Tacho residual", tracking=True)
    fusora_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                  ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado")],
                                 string="Unidad Fusora", tracking=True)
    transfer_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                    ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado"),("no_aplica","No aplica")],
                                   string="Faja de Transferencia", tracking=True)
    optico_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                  ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado")],
                                 string="Unidad Optica", tracking=True)
    black_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                 ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado")],
                                string="Unidad Imagen Black", tracking=True)
    magenta_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                   ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado"),("no_aplica","No aplica")],
                                  string="Unidad Imagen Magenta", tracking=True)
    cyan_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado"),("no_aplica","No aplica")],
                               string="Unidad Imagen Cyan", tracking=True)
    yellow_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                  ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado"),("no_aplica","No aplica")],
                                 string="Unidad Imagen Yellow", tracking=True) 
    contometrok_id = fields.Integer(string="Contometro K", tracking=True) 
    codigo_id  = fields.Char(string='Referencia id') 

    contometroc_id = fields.Integer(string="Contometro Color", tracking=True)
    contometros_id = fields.Integer(string="Contometro Scanner", tracking=True)
    @api.model
    def sumar_field(self):
        self.total_copias_id = self.contometrok_id + self.contometroc_id
    total_copias_id = fields.Integer(string="Contometro Total P+C", compute=sumar_field)
    tipo_servicio_id = fields.Selection([("instalacion", "Instalación"), ("retiro", "Retiro de maquina"),
                                         ("mantenimiento_preventivo", "Mantenimeinto preventivo"), (
                                             "mantenimiento_correctivo", "Mantenimiento correctivo"),
                                         ("cambio_repuestos", "Cambio de repuestos"), ("remoto", "Asistencia remoto"),
                                         ("revision", "Revisión"), ("dejar_toner", "Dejar Toner")],
                                        string="Tipo de servicio", default="revision", tracking=True)
    retorno_id = fields.Selection([("si", "Si"), ("no", "No")], string="Retorno", default="si", tracking=True)

    asistencia_id = fields.Selection([("no", "No"), ("si", "Si")], string="Asistencia Directa", default="no", tracking=True)
    calidad_id = fields.Selection([("buena", "Buena"), ("regular", "Regular"), ("mala", "Mala")], string="Calidad", tracking=True)
    agenda = fields.Datetime(string='Fecha de visita', tracking=True)
    agenda_local = fields.Char(string='Fecha y Hora Local', compute='_compute_agenda_local')

    @api.depends('agenda')
    def _compute_agenda_local(self):
        user_tz = self.env.user.tz or 'UTC'
        local_tz = timezone(user_tz)
        for record in self:
            if record.agenda:
                utc_dt = UTC.localize(record.agenda)
                local_dt = utc_dt.astimezone(local_tz)
                record.agenda_local = local_dt.strftime('%d/%m/%Y %I:%M:%S %p')
            else:
                record.agenda_local = ''
    mensaje  = fields.Text(
    default='Se le asigno un Ticket de  servicio, lea atentamente se le indica todos los detalles del servicio.'
    )

    pedidos_count = fields.Integer(compute='compute_count_pedidos')
    def compute_count_pedidos(self):
        for record in self:
            record.pedidos_count = self.env['sale.order'].search_count(
                [('equipo_id', '=', self.product_alquiler.id)])

    def get_pedidos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pedidos',
            'view_mode': 'tree,form',
            'res_model': 'sale.order',
            'domain': [('equipo_id', '=', self.product_alquiler.id)],
            'context': "{'create': True}"
        }

    def create_sale_order(self):
        sale_order = self.env['sale.order']
        order_id = sale_order.create({
            'partner_id':self.partner_id.id,
            'equipo_id' :self.product_alquiler.id,
            'ticket_id' :self.id,
            'solicitante_id':self.responsable.id,
            
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
   
    def action_finalizar(self):
        self.estado='finalizado'
        # Enviando el segundo correo con la segunda plantilla
        template4 = self.env.ref('sat.email_template_ticket_cliente_finalizacion')
        template4.send_mail(self.id, force_send=True)
        # Verificar el valor de asistencia_id
        if self.retorno_id == 'no':
            # Enviar el tercer correo si asistencia_id es 'si'
            template5 = self.env.ref('sat.mail_template_retorno')
            template5.send_mail(self.id, force_send=True)
        
        # Llamar a la función para enviar mensaje de finalización al cliente
        #self.enviar_mensaje_whatsapp_finalizacion()

    

    def create_ticket_wizard(self):
        return {
            'name': 'Crear ticket',
            'type': 'ir.actions.act_window',
            'res_model': 'ticket.alquiler',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(self.env.ref('sat.view_ticket_wizard').id, 'form')],
            'target': 'new',
        }
    
    
    responsable_mobile_clean = fields.Char(
        string='Número de celular (limpio)',
        compute='_compute_responsable_mobile_clean',
        store=True
    )

    cliente_phones_clean = fields.Char(
        string='Números de contacto limpios',
        compute='_compute_cliente_phones_clean',
        store=True
    )

    @api.depends('responsable.mobile_phone')
    def _compute_responsable_mobile_clean(self):
        for record in self:
            if record.responsable.mobile_phone:
                phone = record.responsable.mobile_phone.replace('+', '')
                phone = ''.join(phone.split())
                if not phone.startswith('51'):
                    phone = '51' + phone
                record.responsable_mobile_clean = phone
            else:
                record.responsable_mobile_clean = 'NA'

    @api.depends('product_alquiler.celular')
    def _compute_cliente_phones_clean(self):
        for record in self:
            if record.product_alquiler.celular:
                phones = record.product_alquiler.celular.split('/')
                cleaned_phones = []
                for phone in phones:
                    phone = ''.join(phone.split())
                    if not phone.startswith('51'):
                        phone = '51' + phone
                    cleaned_phones.append(phone)
                record.cliente_phones_clean = ','.join(cleaned_phones)
            else:
                record.cliente_phones_clean = 'NA'

    def send_whatsapp_message(self, phone, message, file_url=None):
        """Envía un mensaje de WhatsApp con o sin archivo adjunto utilizando la API externa."""
        _logger.debug(f"Enviando mensaje a {phone} con contenido: {message} y archivo: {file_url}")
        
        url = 'https://copierconnectremote.com/lead'
        data = {
            'phone': phone,
            'message': message
        }
        if file_url:
            data['file_url'] = file_url
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, json=data)

        _logger.debug(f"Código de estado: {response.status_code}")
        _logger.debug(f"Respuesta de la API: {response.text}")

        try:
            response_json = response.json()
            _logger.debug(f"Respuesta JSON: {response_json}")
            return response_json
        except json.JSONDecodeError as e:
            error_msg = f"La respuesta no contiene un JSON válido: {str(e)}"
            _logger.error(error_msg)
            return {"error": error_msg}

    

    def enviar_mensaje_whatsapp_finalizacion(self):
        msg_cliente_finalizacion = "Hola, estimado cliente.\n\nQueremos informarle que hemos completado satisfactoriamente nuestra visita técnica programada. A continuación, le detallamos el trabajo realizado durante la visita:\n\n*Ticket #:* {}\n*Fecha de Visita:* {}\n*Tipo de servicio:* {}\n*Dirección:* {}\n*Técnico Asignado:* {}\n*DNI:* {}\n\n*ESPECIFICACIONES DEL EQUIPO*\n*Marca:* {}\n*Modelo:* {}\n*Serie:* {}\n*Contómetro K:* {}\n*Contómetro color:* {}\n*Contómetro scanner:* {}\n\n*PROBLEMA REPORTADO*\n{}\n\n*INFORME TÉCNICO*\n{}\n\nAgradecemos su confianza en nuestros servicios y productos. Si necesita más asistencia o tiene cualquier requerimiento adicional, no dude en comunicarse con nosotros.".format(
            self.name if self.name else 'NA',
            self.agenda.strftime('%d/%m/%Y') if self.agenda else 'NA',
            self.tipo_servicio_id if self.tipo_servicio_id else 'NA',
            self.direccion_id_r if self.direccion_id_r else 'NA',
            self.responsable.name if self.responsable and self.responsable.name else 'NA',
            self.responsable.vat if self.responsable and self.responsable.vat else 'NA',
            self.marca_id_r if self.marca_id_r else 'NA',
            self.product_alquiler.name.name if self.product_alquiler.name and self.product_alquiler.name.name else 'NA',
            self.serie_id_r if self.serie_id_r else 'NA',
            self.contometrok_id if self.contometrok_id else 'NA',
            self.contometroc_id if self.contometroc_id else 'NA',
            self.contometros_id if self.contometros_id else 'NA',
            self.description if self.description else 'NA',
            self.informe_id if self.informe_id else 'NA'
        )

        # Generar URL del informe
        file_url = self._generate_report_url()

        # Enviar mensaje al cliente
        if self.cliente_phones_clean:
            phone_numbers = self.cliente_phones_clean.split(',')
            for phone_number in phone_numbers:
                self.send_whatsapp_message(phone_number, msg_cliente_finalizacion, file_url)

        # Enviando el correo de finalización al cliente
        template4 = self.env.ref('sat.email_template_ticket_cliente_finalizacion')
        template4.send_mail(self.id, force_send=True)
        # Verificar el valor de asistencia_id
        if self.retorno_id == 'no':
            # Enviar el correo de retorno si asistencia_id es 'no'
            template5 = self.env.ref('sat.ticket_alquiler')
            template5.send_mail(self.id, force_send=True)

    def _generate_report_url(self):
        """Genera la URL del informe técnico en formato PDF."""
        report = self.env.ref('sat.report_template_id')
        pdf_content, _ = report.sudo().render_qweb_pdf([self.id])
        report_name = 'Informe_Tecnico_{}.pdf'.format(self.name)
        attachment = self.env['ir.attachment'].create({
            'name': report_name,
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'store_fname': report_name,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf'
        })
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return '{}/web/content/{}?download=true'.format(base_url, attachment.id)

    
         
    repuestos_count_ticket = fields.Integer(compute='compute_count_repuestos_ticket')

    def compute_count_repuestos_ticket(self):
         for record in self:
            record.repuestos_count_ticket = self.env['repuestos.alquiler'].search_count(
                [('modelo_id', '=', self.product_alquiler.id)])

    def get_repuestos_ticket(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Repuestos_ticket',
            'view_mode': 'tree,form',
            'res_model': 'repuestos.alquiler',
            'domain': [('modelo_id', '=', self.product_alquiler.id)],
            'context': "{'create': False}"
        }  

    repuestos_count_ticket = fields.Integer(compute='compute_count_repuestos_ticket')

    def compute_count_repuestos_ticket(self):
         for record in self:
            record.repuestos_count_ticket = self.env['repuestos.alquiler'].search_count(
                [('modelo_id', '=', self.product_alquiler.id)])

    def get_repuestos_ticket(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Repuestos_ticket',
            'view_mode': 'tree,form',
            'res_model': 'repuestos.alquiler',
            'domain': [('modelo_id', '=', self.product_alquiler.id)],
            'context': "{'create': False}"
        }  

      
    month_year = fields.Char(string='Mes y Año', compute='_compute_month_year', store=True)

    def _compute_month_year(self):
        for record in self:
            if record.agenda:
                # Formatear la fecha para que el año aparezca primero, lo cual facilita el ordenamiento
                record.month_year = record.agenda.strftime('%Y-%m')
            else:
                record.month_year = ''

    @api.model
    def update_month_year(self, *args, **kwargs):
        """Método para forzar la actualización del campo en todos los registros existentes."""
        records = self.search([])
        for record in records:
            record._compute_month_year()
    def get_selection_labels(self):
        selection_labels = {}
        for field_name, field in self._fields.items():
            if field.type == 'selection' and hasattr(self, field_name):
                value = getattr(self, field_name)
                if value:
                    for option_value, option_label in field.selection:
                        if option_value == value:
                            selection_labels[field_name] = option_label
                            break
                else:
                    selection_labels[field_name] = 'NA'
        return selection_labels        
    def enviar_mensaje_whatsapp(self):
        selection_labels = self.get_selection_labels()
        msg_tecnico = "Hola *{}*,\n\nSe le ha asignado un Ticket de servicio. Lea atentamente los detalles del servicio:\n\n*Cliente:* {}\n*Direccion:* {}\n*Contacto:* {}\n*Modelo:* {}\n*Serie:* {}\n*Problema:* {}\n*Fecha de visita:* {}\n*Tipo de servicio:* {}\n*Asistencia directa:* {}\n".format(
            self.responsable.name if self.responsable and self.responsable.name else 'NA',
            self.partner_id.name if self.partner_id and self.partner_id.name else 'NA',
            self.direccion_id_r if self.direccion_id_r else 'NA',
            self.contacto_id_r if self.contacto_id_r else 'NA',
            self.product_alquiler.name.name if self.product_alquiler.name and self.product_alquiler.name.name else 'NA',
            self.serie_id_r if self.serie_id_r else 'NA',
            self.description if self.description else 'NA',
            self.agenda_local if self.agenda_local else 'NA',
            self.tipo_servicio_id if self.tipo_servicio_id else 'NA',
            self.asistencia_id if self.asistencia_id else 'NA'
        )

        msg_cliente = "Estimado/a *{}*,\n\nLe informamos que hemos programado una visita técnica para atender su requerimiento. A continuación, le detallamos la información correspondiente:\n\n*Ticket #:* {}\n*Fecha de Visita:* {}\n*Tipo de servicio:* {}\n*Dirección:* {}\n*Técnico Asignado:* {}\n*DNI:* {}\n\n*ESPECIFICACIONES DEL EQUIPO*\n*Marca:* {}\n*Modelo:* {}\n*Serie:* {}\n\n*PROBLEMA REPORTADO*\n{}\n\nPor favor, notifíquenos sobre su stock de toner para garantizarles el total abastecimiento. Además, le solicitamos reportar cualquier inconveniente adicional que presente al técnico en su visita para solventar la totalidad de sus dudas. Para finalizar, solicitamos su apoyo en:\n\n1. Dar autorización para el ingreso de nuestro personal a sus oficinas o el espacio donde se encuentre nuestro equipo.\n2. Disponibilidad de espacio y tiempo para que nuestro personal pueda desarrollar su labor.\n\nGracias por su atención.".format(
            self.partner_id.name if self.partner_id and self.partner_id.name else 'NA',
            self.name if self.name else 'NA',
            self.agenda_local if self.agenda_local else 'NA',
            self.tipo_servicio_id if self.tipo_servicio_id else 'NA',
            self.direccion_id_r if self.direccion_id_r else 'NA',
            self.responsable.name if self.responsable and self.responsable.name else 'NA',
            self.responsable.vat if self.responsable and self.responsable.vat else 'NA',
            self.marca_id_r if self.marca_id_r else 'NA',
            self.product_alquiler.name.name if self.product_alquiler.name and self.product_alquiler.name.name else 'NA',
            self.serie_id_r if self.serie_id_r else 'NA',
            self.description if self.description else 'NA'
        )

        # Enviar mensaje al técnico
        if self.responsable and self.responsable_mobile_clean:
            phone_number = self.responsable_mobile_clean
            self.send_whatsapp_message(phone_number, msg_tecnico)

        # Enviar mensaje al cliente
        if self.cliente_phones_clean:
            phone_numbers = self.cliente_phones_clean.split(',')
            for phone_number in phone_numbers:
                self.send_whatsapp_message(phone_number, msg_cliente)

        # Enviando el primer correo con la primera plantilla
        template1 = self.env.ref('sat.email_template_ticket_cliente')
        template1.send_mail(self.id, force_send=True)
        # Enviando el segundo correo con la segunda plantilla
        template2 = self.env.ref('sat.email_template_ticket_tecnico')
        template2.send_mail(self.id, force_send=True)
        # Verificar el valor de asistencia_id
        if self.asistencia_id == 'si':
            # Enviar el tercer correo si asistencia_id es 'si'
            template3 = self.env.ref('sat.mail_template_asistencia_directa')
            template3.send_mail(self.id, force_send=True)

        self.estado = 'proceso'
        return {
            'type': 'ir.actions.act_window_close'  # Cerrar ventana tras completar la acción
        }
