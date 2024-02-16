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
        # Genera una referencia estándar
        vals['name'] = self.env['ir.sequence'].next_by_code(
            'reparaciones.reparaciones') or '/'
        
        # Crear el registro sin enviar correos electrónicos
        record = super().create(vals)
        
        return record


    maquina_id = fields.Many2one('sat.sat', string='Maquina',  tracking=True

    )

    marca = fields.Char(string='Marca', related='maquina_id.marca', readonly=True, store=True
                        )
    importacion = fields.Char(string='Importación',
                              related='maquina_id.importacion')
    nombre_proveedor = fields.Char(
        related='maquina_id.proveedor_id.name', string="Proveedor")
    nombre_maquina = fields.Char(related='maquina_id.name.name')

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

    tipo_revision = fields.Selection(related='maquina_id.tipo_revision',
                                     readonly=True,
                                     store=True
                                     )
    ubicacion_id = fields.Selection(related='maquina_id.ubicacion_id',
                                    readonly=True,
                                    store=True
                                    )
    prioridad = fields.Selection(related='maquina_id.prioridad',
                                 readonly=True,
                                 store=True
                                 )

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


    estado_id = fields.Selection([('sin_revisar', 'Sin revisar'), ('en_revision', 'En revisión'), ('finalizado', 'Finalizado'), ('con_problemas', 'Con problemas'), ('de_partes', 'De partes'), ('entregada', 'Entregada')],
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

    def enviar_mensaje_whatsapp_reparaciones(self):
        template = self.env.ref('sat.email_template_reparaciones')
        template.send_mail(self.id, force_send=True)

        additional_template = self.env.ref('sat.email_template_reparacion_creada')
        additional_template.send_mail(self.id, force_send=True)


        msg =  "*Cliente:* %s" % (self.cliente_id.name)
        msg1 = "*Tipo de equipo:* %s" % (self.tipo_machine)
        msg2 = "*Marca:* %s" % (self.marca)
        msg3 = "*Modelo:* %s" % (self.maquina_id.name.name)
        msg4 = "*Serie:* %s" % (self.serie_id)
        msg5 = "*Estado:* %s" % (self.obtener_estado_legible())
        msg6 = "*Tipo de revisión:* %s" % (self.obtener_tipo_revision_legible())
        msg7 = "*Prioridad:* %s" % (self.obtener_prioridad_legible())
        msg8 = "*Ubicación:* %s" % (self.obtener_ubicacion_legible())       
        msg9 = "*Asesora:* %s" % (self.maquina_id.asesora_id)
        msg10 = "*REPARACION N°:* %s" % (self.name)
        msg11 = "%s" % ('Hola;')
        msg12 = "%s" % (self.responsable_id.name)
        msg13 = "%s" % ('Se te ha asignado la inspección y elaboración del informe de la máquina que se encuentra en el taller. Por favor, verifica detalladamente la máquina, toma fotografías de su estado actual y documenta cualquier daño o problema que encuentres durante la inspección.')
        
        #msg2 = (f'{msg}{msg1}')       

        whatsapp_iu_url = 'https://api.whatsapp.com/send?phone=%s&text=%s' %  (self.responsable_id.mobile_phone, (f'{msg11}%0A{msg12}%0A{msg13}%0A{msg10}%0A{msg}%0A{msg1}%0A{msg2}%0A{msg3}%0A{msg4}%0A{msg5}%0A{msg6}%0A{msg7}%0A{msg8}%0A{msg9}'))
        self.estado_id='en_revision'       
        return{
            'type': 'ir.actions.act_url',
		    'target': 'new',
		    'url':whatsapp_iu_url
        }
    
    
    def write(self, vals):
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
                    existing_record.write({
                        'descripcion': rec.falla_proveedor,
                    })
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