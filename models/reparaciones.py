from odoo import _, models, fields, api
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)
import xlwt
from io import BytesIO
import base64
import re
import qrcode
from odoo.exceptions import ValidationError
import requests
import json

class reparaciones(models.Model):

    _name = 'reparaciones.reparaciones'
    _description = 'Reparaciones Ventas'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Reparacion N°', default='New',
                       copy=False,
                       required=True,
                       readonly=True)

        
    @api.model
    def create(self, vals):
        vals['name'] = self.env['ir.sequence'].next_by_code('reparaciones.reparaciones') or '/'
        record = super(reparaciones, self).create(vals)
        record.enviar_mensaje_whatsapp_reparaciones()
        return record

      
    maquina_id = fields.Many2one('sat.sat', string='Maquina',  tracking=True )

    marca = fields.Char(string='Marca', related='maquina_id.marca', readonly=True, store=True)
    importacion = fields.Char(string='Importación',
                              related='maquina_id.importacion')
    nombre_proveedor = fields.Char(
        related='maquina_id.proveedor_id.name', string="Proveedor")
    nombre_maquina = fields.Char(related='maquina_id.name.name', store=True)

    tapas_id = fields.Selection([('blancas', 'Blancas'), ('amarillas', 'Amarillas'), ('rotas', 'Rotas'), ('le_faltan', 'Le faltan'),
                                 ('no_aplica', 'No aplica')],
                                string='Tapas', tracking=True
                                )
    panel_id = fields.Selection(
        [('blanco', 'Blanco'), ('amarillo', 'Amarillo'), ('no_aplica', 'No aplica')],
        string='Panel', tracking=True
    )
    lct_id = fields.Selection([('si', 'Si'), ('no', 'No')],
                              string='LCT', tracking=True
                              )
    tipo_machine = fields.Char(string='Tipo de maquina', related='maquina_id.tipo_maquina',
                               readonly=True

                               )

    def action_finalizar_reparacion(self):
        self.estado_id = "finalizado"

        # Enviar el correo
        template_id = self.env.ref('sat.email_template_finalizacion_reparacion')
        template_id.send_mail(self.id, force_send=True)
        return self.env.ref('sat.report_reparaciones_qr').report_action(self)


    def action_con_problemas_reparacion(self):
        self.estado_id = "con_problemas"

    tipo_revision = fields.Selection(related='maquina_id.tipo_revision', readonly=True,store=True)
    ubicacion_id = fields.Selection(related='maquina_id.ubicacion_id', readonly=True, store=True)
    prioridad = fields.Selection(related='maquina_id.prioridad',readonly=True,store=True)

    @api.depends('tipo_revision')
    def obtener_tipo_revision_legible(self):
        tipo_revision_legible = ""
        selection = self._fields['tipo_revision'].selection
        if callable(selection):
            selection = selection(self)
        tipo_revision_legible = dict(selection).get(self.tipo_revision)
        return tipo_revision_legible

    @api.depends('ubicacion_id')
    def obtener_ubicacion_legible(self):
        ubicacion_legible = ""
        selection = self._fields['ubicacion_id'].selection
        if callable(selection):
            selection = selection(self)
        ubicacion_legible = dict(selection).get(self.ubicacion_id)
        return ubicacion_legible

    @api.depends('prioridad')
    def obtener_prioridad_legible(self):
        prioridad_legible = ""
        selection = self._fields['prioridad'].selection
        if callable(selection):
            selection = selection(self)
        prioridad_legible = dict(selection).get(self.prioridad)
        return prioridad_legible


    estado_id = fields.Selection([('sin_revisar', 'Sin revisar'),('para_revision', 'Para revision'),('asignado','Asignado'),('en_revision', 'En revisión'), ('finalizado', 'Finalizado'), ('con_problemas', 'Con problemas'), ('de_partes', 'De partes'), ('entregada', 'Entregada')],
                                 string='Estado de revisión',
                                 related='maquina_id.estado_ventas_id',
                                 readonly=False,
                                         store=True,                                         
                                 )
    serie_id = fields.Char(string='Serie',
                           related='maquina_id.serie_id',
                           readonly=True,
                           store=True
                           )
    ot_id = fields.Selection([('si', 'Si'), ('no', 'No')],
                             string='Bandeja de salida OT', tracking=True
                             )
    hdd_id = fields.Selection([('si', 'Si'), ('no', 'No')],
                              string='Disco duro', tracking=True
                              )
    tipo_id = fields.Selection([('color', 'Color'), ('monocromatica', 'Monocromatica')
                                ],
                               string='Tipo de MFP',  related='maquina_id.tipo_id', readonly=True)
    informe = fields.Html(string='Descripción', tracking=True)
    tray_id = fields.Char("Caseteras N°", tracking=True
                          )
    adf_simple_id = fields.Selection(
        [("si", "Si"), ("no", "No")], string="ADF Simple", tracking=True)
    adf_dual_id = fields.Selection(
        [("si", "Si"), ("no", "No")], string="ADF Dual scan", tracking=True)
    finalizador_interno_id = fields.Selection(
        [("si", "Si"), ("no", "No")], string="Finalizador Interno", tracking=True)
    finalizador_externo_id = fields.Selection(
        [("si", "Si"), ("no", "No")], string="Finalizador Externo", tracking=True)
    mueble_id = fields.Selection(
        [("si", "Si"), ("no", "No")], string="Mueble", tracking=True)
    panel_smart_id = fields.Selection(
        [("si", "Si"), ("no", "No")], string="Panel Smart", tracking=True)
    panel_normal_id = fields.Selection(
        [("si", "Si"), ("no", "No")], string="Panel Normal", tracking=True)
    wi_fi_id = fields.Selection(
        [("si", "Si"), ("no", "No")], string="Wi-Fi", tracking=True)

    cable_poder_id = fields.Selection(
        [("si", "Si"), ("no", "No")], string="Cable de poder", tracking=True)

    toner_black_id = fields.Selection(
        [("nuevo", "Nuevo"), ("regular", "Regular"),
         ("vacio", "Vacío"), ("sin_botella", "Sin botella")],
        string="Toner Black", tracking=True)
    toner_magenta_id = fields.Selection(
        [("nuevo", "Nuevo"), ("regular", "Regular"), ("vacio", "Vacío"),
         ("sin_botella", "Sin botella"), ("no_aplica", "No aplica")],
        string="Toner Magenta", tracking=True)
    toner_cyan_id = fields.Selection(
        [("nuevo", "Nuevo"), ("regular", "Regular"), ("vacio", "Vacío"),
         ("sin_botella", "Sin botella"), ("no_aplica", "No aplica")],
        string="Toner Cyan", tracking=True)
    toner_yellow_id = fields.Selection(
        [("nuevo", "Nuevo"), ("regular", "Regular"), ("vacio", "Vacío"),
         ("sin_botella", "Sin botella"), ("no_aplica", "No aplica")],
        string="Toner Yellow", tracking=True)
    copia_id = fields.Selection([("correcto", "Correcto"), ("sin_probar", "Sin probar"), ("falla", "Falla")],
                                string="Copia", tracking=True)
    impresion_id = fields.Selection(
        [("correcto", "Correcto"), ("sin_probar", "Sin probar"),
         ("falla", "Falla"), ("no_aplica", "No aplica")],
        string="Impresión", tracking=True)
    impresion_usb_id = fields.Selection(
        [("correcto", "Correcto"), ("sin_probar", "Sin probar"),
         ("falla", "Falla"), ("no_aplica", "No aplica")],
        string="Impresión USB", tracking=True)
    scaner_smb_id = fields.Selection(
        [("correcto", "Correcto"), ("sin_probar", "Sin probar"),
         ("falla", "Falla"), ("no_aplica", "No aplica")],
        string="Scanner SMB", tracking=True)
    scaner_usb_id = fields.Selection(
        [("correcto", "Correcto"), ("sin_probar", "Sin probar"),
         ("falla", "Falla"), ("no_aplica", "No aplica")],
        string="Scanner USB", tracking=True)
    scaner_ftp_id = fields.Selection(
        [("correcto", "Correcto"), ("sin_probar", "Sin probar"),
         ("falla", "Falla"), ("no_aplica", "No aplica")],
        string="Scanner FTP", tracking=True)
    scaner_mail_id = fields.Selection(
        [("correcto", "Correcto"), ("sin_probar", "Sin probar"),
         ("falla", "Falla"), ("no_aplica", "No aplica")],
        string="Scanner Mail", tracking=True)
    adf_id = fields.Selection(
        [("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
         ("cambio_de_repuestos", "Cambio de repuestos"), ("revisado", "Revisado"), ("no_aplica", "No aplica")],
        string="ADF", tracking=True)
    tray1_id = fields.Selection([("sin_revisar", "Sin revisar"),
                                 ("revisado", "Revisado")],
                                string="Tray 1", tracking=True)
    tray2_id = fields.Selection([("sin_revisar", "Sin revisar"), ("revisado", "Revisado"), ("no_aplica", "No aplica")],
                                string="Tray 2", tracking=True)
    tray3_id = fields.Selection([("sin_revisar", "Sin revisar"), ("revisado", "Revisado"), ("no_aplica", "No aplica")],
                                string="Tray 3", tracking=True)
    tray4_id = fields.Selection([("sin_revisar", "Sin revisar"), ("revisado", "Revisado"), ("no_aplica", "No aplica")],
                                string="Tray 4", tracking=True)
    bypass_id = fields.Selection([("sin_revisar", "Sin revisar"), ("revisado", "Revisado"), ("no_aplica", "No aplica")],
                                 string="Bypass", tracking=True)
    finalizador_id = fields.Selection([("sin_revisar", "Sin revisar"), ("revisado", "Revisado"), ("no_aplica", "No aplica")],
                                      string="Finalizador", tracking=True)

    tacho_id = fields.Selection(
        [("si", "Si"), ("no", "No"), ("no_aplica", "No aplica")],
        string="Tacho residual", tracking=True)
    fusora_id = fields.Selection([('requiere_cambio', 'Requiere cambio'), ('nuevo', 'Nuevo'), ('regular', 'Regular'), ('gastada_pero_puede_trabajar', 'Gastada pero puede trabajar'), ("no_aplica", "No aplica")],
                                 string="Faja fusora", tracking=True)
    rodillo_id = fields.Selection([('requiere_cambio', 'Requiere cambio'), ('nuevo', 'Nuevo'), ('regular', 'Regular'), (
        'gastada_pero_puede_trabajar', 'Gastada pero puede trabajar'), ("no_aplica", "No aplica")], string="Rodillo de presión", tracking=True)
    calor_id = fields.Selection([('requiere_cambio', 'Requiere cambio'), ("no_aplica", "No aplica"), ('nuevo', 'Nuevo'), ('regular', 'Regular'), ('gastada_pero_puede_trabajar', 'Gastada pero puede trabajar')],
                                string="Rodillo de calor",
                                tracking=True)

    transfer_id = fields.Selection([('requiere_cambio', 'Requiere cambio'), ("no_aplica", "No aplica"), ('nuevo', 'Nuevo'), ('regular', 'Regular'), ('gastada_pero_puede_trabajar', 'Gastada pero puede trabajar')
                                    ],
                                   string="Faja de Transferencia", tracking=True)
    optico_id = fields.Selection([("sin_revisar", "Sin revisar"), ("mantenimiento", "Mantenimiento"),
                                  ("revisado", "Revisado")],
                                 string="Unidad Optica", tracking=True)
    black_id = fields.Selection([('requiere_cambio', 'Requiere cambio'), ('nuevo', 'Nuevo'), ('regular', 'Regular'), ('gastada_pero_puede_trabajar', 'Gastada pero puede trabajar')
                                 ],
                                string="Unidad Imagen Black", tracking=True)
    developerk_id = fields.Selection([('requiere_cambio', 'Requiere cambio'), ('nuevo', 'Nuevo'), ('regular', 'Regular'), ('gastada_pero_puede_trabajar', 'Gastada pero puede trabajar')
                                      ],
                                     string="Developer Black", tracking=True)
    magenta_id = fields.Selection([('requiere_cambio', 'Requiere cambio'), ("no_aplica", "No aplica"), ('nuevo', 'Nuevo'), ('regular', 'Regular'), ('gastada_pero_puede_trabajar', 'Gastada pero puede trabajar')],
                                  string="Unidad Imagen Magenta", tracking=True)
    developerm_id = fields.Selection([('requiere_cambio', 'Requiere cambio'), ("no_aplica", "No aplica"), ('nuevo', 'Nuevo'), ('regular', 'Regular'), ('gastada_pero_puede_trabajar', 'Gastada pero puede trabajar')],
                                     string="Developer Magenta", tracking=True)
    cyan_id = fields.Selection([('requiere_cambio', 'Requiere cambio'), ("no_aplica", "No aplica"), ('nuevo', 'Nuevo'), ('regular', 'Regular'), ('gastada_pero_puede_trabajar', 'Gastada pero puede trabajar')],
                               string="Unidad Imagen Cyan", tracking=True)
    developerc_id = fields.Selection([('requiere_cambio', 'Requiere cambio'), ("no_aplica", "No aplica"),
                                      ('nuevo', 'Nuevo'), ('regular', 'Regular'), ('gastada_pero_puede_trabajar', 'Gastada pero puede trabajar')],
                                     string="Developer Cyan", tracking=True)
    yellow_id = fields.Selection([('requiere_cambio', 'Requiere cambio'), ("no_aplica", "No aplica"), ('nuevo', 'Nuevo'), ('regular', 'Regular'), ('gastada_pero_puede_trabajar', 'Gastada pero puede trabajar')],
                                 string="Unidad Imagen Yellow", tracking=True)
    developery_id = fields.Selection([('requiere_cambio', 'Requiere cambio'), ("no_aplica", "No aplica"), ('nuevo', 'Nuevo'), ('regular', 'Regular'), ('gastada_pero_puede_trabajar', 'Gastada pero puede trabajar')],
                                     string="Developer Yellow", tracking=True)
    contometrok_id = fields.Char(string="Contometro",
                                 related='maquina_id.contometro',
                                 readonly=False,
                                 store=True,  tracking=True,
                                 required=True

                                 )

    calidad_id = fields.Selection(
        [("buena", "Buena"), ("regular", "Regular"), ("mala", "Mala")], string="Calidad", tracking=True)
    responsable_id = fields.Many2one(
        'res.users',
        string='Responsable', tracking=True
    )
    nombre_responsable  = fields.Char(related='responsable_id.name', 
    string='Nombre responsable',store=True
    )
    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        related='maquina_id.cliente_id',
        readonly=True,
        store=True, tracking=True

    )

    falla_proveedor = fields.Html(string="Descripción", tracking=True)
    
    falla_ventas = fields.Text(
        string='Descripción',
        related='maquina_id.descripcion',
        readonly=False,
        store=True, tracking=True

    )
    
    
    @api.depends('estado_id')
    def obtener_estado_legible(self):
        estado_legible = ""
        selection = self._fields['estado_id'].selection
        if callable(selection):
            selection = selection(self)
        estado_legible = dict(selection).get(self.estado_id)
        return estado_legible
    responsable_mobile_clean = fields.Char(
        string='Número de celular (limpio)',
        compute='_compute_responsable_mobile_clean',
        store=True
    )

    @api.depends('responsable_id.mobile_phone')
    def _compute_responsable_mobile_clean(self):
        for record in self:
            if record.responsable_id.mobile_phone:
                # Remove '+' and all types of spaces
                phone = record.responsable_id.mobile_phone.replace('+', '')
                phone = ''.join(phone.split())
                # Ensure phone starts with '51'
                if not phone.startswith('51'):
                    phone = '51' + phone
                record.responsable_mobile_clean = phone
            else:
                record.responsable_mobile_clean = ''
                record.responsable_mobile_clean = ''


    def send_whatsapp_message(self, phone, message):
        """Envía un mensaje de WhatsApp utilizando la API externa."""
        url = 'https://copierconnectremote.com/lead'
        data = {
            'phone': phone,
            'message': message
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, json=data)

        print("Código de estado:", response.status_code)
        print("Respuesta de la API:", response.text)

        # Verificar si la respuesta contiene un cuerpo JSON válido
        try:
            response_json = response.json()
            print("Respuesta JSON:", response_json)
            return response_json
        except json.JSONDecodeError as e:
            error_msg = f"La respuesta no contiene un JSON válido: {str(e)}"
            print(error_msg)
            return {"error": error_msg}  # Devuelve un diccionario con la clave 'error' y el mensaje de error como valor

    def enviar_mensaje_whatsapp_reparaciones(self):
        # Lógica para enviar correos
        template = self.env.ref('sat.email_template_reparaciones')
        template.send_mail(self.id, force_send=True)

        additional_template = self.env.ref('sat.email_template_reparacion_creada')
        additional_template.send_mail(self.id, force_send=True)

        # Construir y enviar el mensaje de WhatsApp
        msg = "Hola;\n*{}*\nSe te ha asignado la inspección y elaboración del informe de la máquina que se encuentra en el taller. Por favor, verifica detalladamente la máquina, toma fotografías de su estado actual y documenta cualquier daño o problema que encuentres durante la inspección.\n*REPARACION N°:* {}\n*Cliente:* {}\n*Importación:* {}\n*Tipo de equipo:* {}\n*Marca:* {}\n*Modelo:* {}\n*Serie:* {}\n*Estado:* {}\n*Tipo de revisión:* {}\n*Prioridad:* {}\n*Ubicación:* {}\n*Asesora:* {}".format(
            self.responsable_id.name if self.responsable_id.name else 'NA',
            self.name if self.name else 'NA',
            self.cliente_id.name if self.cliente_id.name else 'NA',
            self.importacion if self.importacion else 'NA',
            self.tipo_machine if self.tipo_machine else 'NA',
            self.marca if self.marca else 'NA',
            self.maquina_id.name.name if self.maquina_id.name and self.maquina_id.name.name else 'NA',
            self.serie_id if self.serie_id else 'NA',
            self.obtener_estado_legible() if self.obtener_estado_legible() else 'NA',
            self.obtener_tipo_revision_legible() if self.obtener_tipo_revision_legible() else 'NA',
            self.obtener_prioridad_legible() if self.obtener_prioridad_legible() else 'NA',
            self.obtener_ubicacion_legible() if self.obtener_ubicacion_legible() else 'NA',
            self.maquina_id.asesora_id if self.maquina_id.asesora_id else 'NA'
        )

        if self.responsable_id and self.responsable_mobile_clean:
            phone_number = self.responsable_mobile_clean
            self.send_whatsapp_message(phone_number, msg)

        # Actualizar estado de la reparación
        self.estado_id = 'en_revision'
        return {
            'type': 'ir.actions.act_window_close'  # Cerrar ventana tras completar la acción
        }





    fecha_finalizacion = fields.Datetime(string='Fecha de Finalización', readonly=True, store=True)

    
    def _create_next_reparacion(self):
        next_maquina = self.env['sat.sat'].search([('estado_ventas_id', '=', 'para_revision')], order='fecha_para_revision asc', limit=1)
        if next_maquina:
            next_maquina.write({'estado_ventas_id': 'en_revision', 'trabajadores_id': self.responsable_id.id})
            reparacion = self.env['reparaciones.reparaciones'].create({
                'maquina_id': next_maquina.id,
                'responsable_id': self.responsable_id.id,
            })
            reparacion._send_notifications()

    def _send_notifications(self):
        self.enviar_mensaje_whatsapp_reparaciones()
        self.estado_id = 'en_revision'

    def write(self, vals):
        finalizado = vals.get('estado_id') == 'finalizado'
        
        if finalizado:
            for rec in self:
                if rec.estado_id == 'en_revision':
                    vals['fecha_finalizacion'] = fields.Datetime.now()

        res = super(reparaciones, self).write(vals)
        
        if 'falla_proveedor' in vals:
            for rec in self:
                existing_record = rec.env['fallas'].search([
                    ('name', '=', rec.maquina_id.invoice),
                    ('modelo_id', '=', rec.maquina_id.name.name),
                    ('importacion', '=', rec.maquina_id.importacion),
                    ('proveedor_id', '=', rec.maquina_id.proveedor_id.name),
                    ('marca', '=', rec.maquina_id.marca),
                    ('serie', '=', rec.maquina_id.serie_id),
                    ('usuario_id', '=', rec.responsable_id.name),
                ], limit=1)
                if existing_record:
                    existing_record.write({'descripcion': rec.falla_proveedor})
                else:
                    rec.env['fallas'].create({
                        'descripcion': rec.falla_proveedor,
                        'name': rec.maquina_id.invoice,
                        'modelo_id': rec.maquina_id.name.name,
                        'importacion': rec.maquina_id.importacion,
                        'proveedor_id': rec.maquina_id.proveedor_id.name,
                        'marca': rec.maquina_id.marca,
                        'serie': rec.maquina_id.serie_id,
                        'usuario_id': rec.responsable_id.name,
                    })
        
        if finalizado:
            self._create_next_reparacion()

        return res

    


    qr_code_ventas = fields.Binary(string='QR Code Relacionado', related='maquina_id.qr_image', readonly=True)
    

    def generate_record_url(self, record):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action_id = self.env.ref('sat.action_reparaciones_window').id  # Debes cambiar 'sat.action_id' al ID de acción correcto para tu modelo sat.sat
        menu_id = self.env.ref('sat.reparaciones').id  # Cambia 'sat.menu_id' al ID de menú correcto
        url = "{}/web#id={}&view_type=form&model=reparaciones.reparaciones&action={}&menu_id={}".format(base_url, record.id, action_id, menu_id)
        return url
    qr_image = fields.Binary("QR Image", compute="_generate_qr_code", attachment=True, store=True)


    @api.depends('serie_id')  # Suponiendo que quieras codificar un campo específico, reemplaza 'nombre_del_campo_a_codificar' con el campo relevante.
    def _generate_qr_code(self):
        import qrcode
        from io import BytesIO
        import base64
        for record in self:
            url = self.generate_record_url(record)
            
            qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
            qr.add_data(url)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            temp = BytesIO()
            img.save(temp, format="PNG")
            temp.seek(0)
            record.qr_image = base64.b64encode(temp.read())
            
            
                
    month_year = fields.Char(string='Mes y Año', compute='_compute_month_year', store=True)

    def _compute_month_year(self):
        for record in self:
            if record.create_date:
                # Formatear la fecha para que el año aparezca primero, lo cual facilita el ordenamiento
                record.month_year = record.create_date.strftime('%Y-%m')
            else:
                record.month_year = ''

    @api.model
    def update_month_year(self, *args, **kwargs):
        """Método para forzar la actualización del campo en todos los registros existentes."""
        records = self.search([])
        for record in records:
            record._compute_month_year()