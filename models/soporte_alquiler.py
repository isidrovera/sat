from odoo import _, models, fields, api, exceptions

from dateutil.relativedelta import relativedelta
from odoo.http import request
from datetime import datetime, timedelta
from odoo.exceptions import UserError
import webbrowser
from datetime import datetime
from pytz import timezone
#import telegram


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
      
    


    responsable = fields.Many2one("res.users", string="Técnico", tracking=True, index=True)
    
    
    priority = fields.Selection([("0", ("Low")),("1", ("Medium")),("2", ("High")),("3", ("Very High"))],string="Prioridad",default="1")
    partner_id = fields.Many2one("res.partner", string="Empresa", tracking=True 
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
    serie_id_r = fields.Char(related='product_alquiler.serie', string="Serie")    
    marca_id_r = fields.Char(related='product_alquiler.marca', string="Marca")
    modelo_id_r  = fields.Char(related='product_alquiler.name.name',string='Modelo')
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
    
    
    def enviar_mensaje_whatsapp(self):

        msg = "*Cliente:* %s" % (self.partner_id.name)
        msg1 = "*Direccion:* %s" % (self.direccion_id_r)
        msg2 = "*Modelo:* %s" % (self.product_alquiler.name.name)
        msg3 = "*Serie:* %s" % (self.serie_id_r)
        msg4 = "*Problema:* %s" % (self.description)
        msg5 = "*Fecha de visita:* %s" % (self.agenda.strftime('%d/%m/%Y'))
        msg6 = "*Tipo de servicio:* %s" % (self.tipo_servicio_id)
        msg7 = "*Asistencia directa:* %s" % (self.asistencia_id)
        msg8 = "  %s" % (self.mensaje)
        msg9 = "*Contacto:* %s" % (self.contacto_id_r)
        msg10 = "  %s" % (self.responsable.name)
        
        #msg2 = (f'{msg}{msg1}')       

        whatsapp_iu_url = 'https://api.whatsapp.com/send?phone=%s&text=%s' %  (self.responsable.mobile_phone, (f'{msg10}%0A{msg8}%0A{msg}%0A{msg1}%0A{msg9}%0A{msg2}%0A{msg3}%0A{msg4}%0A{msg5}%0A{msg6}%0A{msg7}'))
        self.estado='proceso'
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
        return{
            'type': 'ir.actions.act_url',
		    'target': 'new',
		    'url':whatsapp_iu_url
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

      
