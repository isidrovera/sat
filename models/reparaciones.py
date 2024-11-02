from odoo import _, models, fields, api, exceptions, _
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
from odoo.tools import config
from odoo.exceptions import UserError


class Reparaciones(models.Model):

    _name = 'reparaciones.reparaciones'
    _description = 'Reparaciones Ventas'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Reparacion N°', default='New',
                       copy=False,
                       required=True,
                       readonly=True)

        
    @api.model
    def create(self, vals):
        # Genera un número secuencial único para el campo 'name'
        #vals['name'] = self.env['ir.sequence'].next_by_code('reparaciones.reparaciones') or '/'

        # Asigna el valor inicial del contómetro al campo 'contometro_inicial' si 'contometrok_id' tiene un valor
        if 'contometrok_id' in vals:
            vals['contometro_inicial'] = vals['contometrok_id']

        # Crea el registro
        record = super(Reparaciones, self).create(vals)
        _logger.info("Record created with ID: %s", record.id)
        
        # Genera el código QR
        record.generate_qr_code()
        
        return record
    



    @api.model
    def default_get(self, fields):
        _logger.info("Inicio del método default_get en el modelo reparaciones.reparaciones")

        res = super(Reparaciones, self).default_get(fields)

        # Verificar si el usuario pertenece al grupo que necesita autenticación
        try:
            grupo_validacion = self.env.ref('sat.sat_tecnica_group_user')
            _logger.info(f"Grupo de validación encontrado: {grupo_validacion}")

            if grupo_validacion in self.env.user.groups_id:
                _logger.info("El usuario pertenece al grupo de validación, redirigiendo al wizard de autenticación")

                # Redirigir al wizard de autenticación
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'reparacion.autenticacion.wizard',
                    'view_mode': 'form',
                    'view_id': self.env.ref('sat.view_reparacion_autenticacion_wizard_form').id,
                    'target': 'new',
                    'context': {'default_active_id': self.id},
                }
            else:
                _logger.info("El usuario no pertenece al grupo de validación, se abrirá el formulario de reparación normalmente")

        except Exception as e:
            _logger.error(f"Error en default_get: {str(e)}")
        
        return res

      
    maquina_id = fields.Many2one('sat.sat', string='Maquina',  tracking=True )
     # Restricción SQL para evitar duplicados de serie_id
    _sql_constraints = [
        ('unique_serie_id', 'unique(serie_id)', 'El número de serie ya existe.')
    ]

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

    


    def action_con_problemas_reparacion(self):
        self.estado_id = "con_problemas"

    tipo_revision = fields.Selection(related='maquina_id.tipo_revision', readonly=True,store=True)
    ubicacion_id = fields.Selection(related='maquina_id.ubicacion_id', readonly=True, store=True)
    prioridad = fields.Selection(related='maquina_id.prioridad',readonly=True,store=True)

    estado_id = fields.Selection([('sin_revisar', 'Sin revisar'),('para_revision', 'Para revision'),('asignado','Asignado'),('en_revision', 'En revisión'), ('finalizado', 'Finalizado'), ('con_problemas', 'Con problemas'), ('de_partes', 'De partes'), ('entregada', 'Entregada')],
                                 string='Estado de revisión',
                                 related='maquina_id.estado_ventas_id',
                                 readonly=False,
                                         store=True,                                         
                                 )
    serie_id = fields.Char(string='Serie',
                           related='maquina_id.serie_id',
                           readonly=False,
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
    informe = fields.Html(string='Descripción')
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
                                 store=True,  tracking=True
                                 

                                 )

    contometro_inicial = fields.Char(
        string="Contometro Inicial",
        readonly=True,
        tracking=True
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
    cliente_id = fields.Many2one('res.partner', string='Cliente', related='maquina_id.cliente_id', readonly=True,
        store=True, tracking=True
    )

    falla_proveedor = fields.Html(string="Descripción")
    
    falla_ventas = fields.Text(string='Descripción',related='maquina_id.descripcion',readonly=False, store=True

    )
  
    
    responsable_mobile_clean = fields.Char(string='Número de celular (limpio)', compute='_compute_responsable_mobile_clean',
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
        url = 'https://whatsapp.andessolutioncopiers.com/lead'
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
    def get_selection_labels(self):
        selection_labels = {}
        for field_name, field in self._fields.items():
            if field.type == 'selection' and hasattr(self, field_name):
                value = getattr(self, field_name)
                if value:
                    selection = field.selection
                    if callable(selection):
                        selection = selection(self)
                    for option_value, option_label in selection:
                        if option_value == value:
                            selection_labels[field_name] = option_label
                            break
                else:
                    selection_labels[field_name] = 'NA'
        return selection_labels
    def enviar_mensaje_whatsapp_reparaciones(self):
       
        selection_labels = self.get_selection_labels()
        # Contexto para las plantillas de correo
        # Contexto para las plantillas de correo
        context = dict(self.env.context or {})
        context.update({
            'selection_labels': selection_labels
        })
        # Lógica para enviar correos
        template = self.env.ref('sat.email_template_reparaciones')
        template.with_context(**context).send_mail(self.id, force_send=True)


        additional_template = self.env.ref('sat.email_template_reparacion_creada')
        additional_template.with_context(**context).send_mail(self.id, force_send=True)

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
            selection_labels.get('estado_id', 'NA'),
            selection_labels.get('tipo_revision', 'NA'),
            selection_labels.get('prioridad', 'NA'),
            selection_labels.get('ubicacion_id', 'NA'),        
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
   
    asesora_mobile_clean = fields.Char(
        string='Número de celular asesora (limpio)',
        compute='_compute_asesora_mobile_clean',
        store=True
    )

   
    @api.depends('maquina_id.cliente_id.asesora_id.mobile')
    def _compute_asesora_mobile_clean(self):
        for record in self:
            if record.maquina_id.cliente_id.asesora_id.mobile:
                phone = record.maquina_id.cliente_id.asesora_id.mobile.replace('+', '')
                phone = ''.join(phone.split())
                if not phone.startswith('51'):
                    phone = '51' + phone
                record.asesora_mobile_clean = phone
            else:
                record.asesora_mobile_clean = ''


    qr_code_ventas = fields.Binary(string='QR Code Relacionado', related='maquina_id.qr_image', readonly=True)
    

    qr_image = fields.Binary("QR Image", compute="generate_qr_code", attachment=True, store=True)
    qr_url = fields.Char("QR URL", compute="generate_qr_code", store=True)

    @api.depends('name')
    def generate_qr_code(self):
        for record in self:
            try:
                _logger.info("Generating QR code for record ID: %s", record.id)
                url = self.generate_record_url(record)
                _logger.info("Generated URL for record ID %s: %s", record.id, url)
                record.qr_url = url

                if not url:
                    _logger.error("No URL generated for record %s", record.id)
                    continue

                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4
                )
                qr.add_data(url)
                qr.make(fit=True)

                img = qr.make_image(fill_color="black", back_color="white")
                temp = BytesIO()
                img.save(temp, format="PNG")
                temp.seek(0)
                qr_base64 = base64.b64encode(temp.read()).decode('utf-8')
                record.qr_image = qr_base64

                _logger.info("QR code generated and stored for record %s", record.id)

            except Exception as e:
                _logger.error("Error generating QR code for record %s: %s", record.id, str(e))

    @api.model
    def generate_record_url(self, record):
        try:
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            action_id = self.env.ref('sat.action_reparaciones_window').id
            menu_id = self.env.ref('sat.reparaciones').id
            url = "{}/web#id={}&view_type=form&model=reparaciones.reparaciones&action={}&menu_id={}".format(base_url, record.id, action_id, menu_id)
            _logger.info("Generated URL: %s", url)
            return url
        except Exception as e:
            _logger.error("Error generating URL: %s", str(e))
            return ""

    def action_generate_qr_for_all(self):
        all_records = self.search([])
        for record in all_records:
            record.generate_qr_code()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
          
                
    
            
    def write(self, vals):
        finalizado = vals.get('estado_id') == 'finalizado'
        if finalizado:
            for rec in self:
                if rec.estado_id == 'en_revision':
                    vals['fecha_finalizacion'] = fields.Datetime.now()

        res = super(Reparaciones, self).write(vals)

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

        return res        
    def _create_next_reparacion(self):
        # Verificar si el técnico tiene algún registro en estado 'en_revision'
        if self.env['reparaciones.reparaciones'].search_count([('responsable_id', '=', self.responsable_id.id), ('estado_id', '=', 'en_revision')]) > 0:
            return

        # Buscar la siguiente máquina en estado 'para_revision'
        next_maquina = self.env['sat.sat'].search([
            ('estado_ventas_id', '=', 'para_revision')
        ], order='fecha_para_revision asc', limit=1)

        if not next_maquina:
            next_maquina = self.env['sat.sat'].search([
                ('estado_ventas_id', '=', 'sin_revisar'),
                ('disponibilidad_id', '=', 'disponible'),
                ('ubicacion_id', 'in', ['primer_piso', 'tercer_piso'])
            ], order='create_date asc', limit=1)

        if next_maquina:
            # Verificación del valor de contometro
            if not next_maquina.contometro or int(next_maquina.contometro) == 0:
                raise ValidationError("La máquina seleccionada no tiene un valor de contómetro válido.")

            empleado = self.env['hr.employee'].search([('user_id', '=', self.responsable_id.id)], limit=1)
            if empleado:
                next_maquina.write({
                    'estado_ventas_id': 'en_revision',
                    'trabajadores_id': empleado.id
                })
                nueva_reparacion = self.env['reparaciones.reparaciones'].create({
                    'maquina_id': next_maquina.id,
                    'responsable_id': self.responsable_id.id,
                    'contometro_inicial': next_maquina.contometro  # Contómetro inicial
                    
                })
                nueva_reparacion.enviar_mensaje_whatsapp_reparaciones()
            else:
                raise ValidationError("El responsable asignado no está vinculado a ningún empleado. Por favor, revise la configuración.")
  
    def generate_pdf_report_url(self):
        # Obtener el reporte
        report = self.env.ref('sat.report_reparaciones_ventas')
        
        if not report:
            raise UserError("No se encontró el reporte especificado.")
        
        # Obtener la URL base
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        
        # Generar la URL del PDF
        pdf_url = f"{base_url}/report/pdf/sat.report_reparaciones_ventas/{self.id}?cid=1"

        return pdf_url


    def enviar_mensaje_finalizacion_asesora(self):
        pdf_url = self.generate_pdf_report_url()
        msg = "*Reparación Finalizada*\n*Cliente:* {}\n*Marca:* {}\n*Modelo:* {}\n*Serie:* {}\n*Contómetro:* {}\n*Estado:* {}\n*Técnico:* {}\n\nPor favor, ingrese al siguiente enlace para revisar todos los detalles: {}".format(
            self.cliente_id.name if self.cliente_id.name else 'NA',
            self.marca if self.marca else 'NA',
            self.nombre_maquina if self.nombre_maquina else 'NA',
            self.serie_id if self.serie_id else 'NA',
            self.contometrok_id if self.contometrok_id else 'NA',
            self.obtener_estado_legible() if self.obtener_estado_legible() else 'NA',
            self.responsable_id.name if self.responsable_id.name else 'NA',
            pdf_url
        )

        if self.asesora_mobile_clean:
            phone_number = self.asesora_mobile_clean
            self.send_whatsapp_message(phone_number, msg)
    

    autorizacion_cambio_digitos = fields.Boolean(related='maquina_id.autorizacion_cambio_digitos',readonly=False, string="Autorización de Modificación")
            
    
    autenticacion_correcta = fields.Boolean(string="Autenticación Correcta", default=False)




    def action_finalizar_reparacion(self):
        # Verificar si la autenticación ya fue realizada
        #if not self.autenticacion_correcta:
            # Verificar si el usuario pertenece al grupo que necesita autenticación
         #   grupo_validacion = self.env.ref('sat.sat_tecnica_group_user')  # Reemplaza con el grupo correcto
          #  if grupo_validacion in self.env.user.groups_id:
                # Llamar al wizard de autenticación
           #     return {
                 #   'type': 'ir.actions.act_window',
                #    'res_model': 'reparacion.autenticacion.wizard',
               #     'view_mode': 'form',
              #      'target': 'new',
             #       'context': {'default_reparacion_id': self.id},
            #    }
        _logger.info(f"Iniciando proceso de finalización para reparación ID: {self.id}")
        
        # Verificar que contometrok_id y contometro_inicial sean cadenas y no estén vacíos
        if not self.contometrok_id or not self.contometro_inicial:
            _logger.error("Los datos del contómetro no están configurados correctamente.")
            raise UserError(_("❗ <b>Error en el Contómetro</b>: Los valores del contómetro no están configurados correctamente. Verifique e intente nuevamente."))

        # Verificar si el contómetro fue actualizado
        if self.contometrok_id == self.contometro_inicial:
            _logger.warning("El contómetro no ha sido actualizado.")
            raise UserError(_("❗ Error en el Contómetro El contómetro no ha sido actualizado. Debe ser diferente del valor inicial."))

        # Validar la cantidad de dígitos
        if len(self.contometrok_id) != len(self.contometro_inicial):
            if not self.autorizacion_cambio_digitos:
                _logger.warning("Diferencia en la cantidad de dígitos del contómetro y sin autorización.")
                raise UserError(_("❗ Error en el Número de Dígitos: La cantidad de dígitos del contómetro actual no coincide con el inicial. Contacte al administrador para obtener autorización de cambio."))

        # Continuar con el proceso de finalización
        _logger.info(f"Generando reporte para reparación ID: {self.id}")
        pdf_report = self.env.ref('sat.action_report_qr_codes_reparaciones_template').report_action(self.ids)

        try:
            _logger.info(f"Enviando mensaje a la asesora para reparación ID: {self.id}")
            self.enviar_mensaje_finalizacion_asesora()
        except Exception as e:
            _logger.error(f"Error enviando el mensaje a la asesora: {e}")

        _logger.info(f"Creando siguiente reparación para ID actual: {self.id}")
        self._create_next_reparacion()

        try:
            _logger.info(f"Enviando correo de finalización para reparación ID: {self.id}")
            template_id = self.env.ref('sat.email_template_finalizacion_reparacion')
            template_id.send_mail(self.id, force_send=True)
        except Exception as e:
            _logger.error(f"Error enviando el correo: {e}")

        _logger.info(f"Cambiando estado a 'finalizado' para reparación ID: {self.id}")
        self.estado_id = "finalizado"
        _logger.info(f"Estado cambiado a 'finalizado' para reparación ID: {self.id}")

        _logger.info(f"Proceso de finalización completado para reparación ID: {self.id}")
        return pdf_report
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
    @api.depends('estado_id')
    def obtener_estado_legible(self):
        estado_legible = ""
        selection = self._fields['estado_id'].selection
        if callable(selection):
            selection = selection(self)
        estado_legible = dict(selection).get(self.estado_id)
        return estado_legible
class ReportReparacionView(models.AbstractModel):
    _name = 'report.sat.report_reparaciones_ventas'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['reparaciones.reparaciones'].browse(docids)
        selection_labels = {}
        for doc in docs:
            selection_labels[doc.id] = doc.get_selection_labels() if doc else {}
        return {
            'doc_ids': docids,
            'doc_model': 'reparaciones.reparaciones',
            'docs': docs,
            'selection_labels': selection_labels,
        }
