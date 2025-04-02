from odoo import models, fields, api
from odoo.exceptions import UserError

class Informes(models.Model):
    _name = 'informes'
    _description = 'Registro de informes proveedores'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string="Informe N°",
        default='/',
        copy=False, 
        required=True,
        readonly=True,
        tracking=True
    )
    proveedor_id = fields.Many2one('res.partner', string='Proveedor', tracking=True)
    importacion = fields.Char(string="Importación", tracking=True)
    invoice = fields.Char(string="Invoice", tracking=True)
    informe = fields.Text(
        string="Informe", 
        default='Estimados señores,\n\nMediante el presente documento, les entregamos el informe del estado de las máquinas fotocopiadoras.\n\n Durante el mantenimiento realizado, se detectaron fallas y se identificaron los elementos que deben ser reemplazados para asegurar su correcto funcionamiento.\n\nA continuación, detallamos el informe de cada una de las máquinas:',
        tracking=True
    )
    detalle_ids = fields.Many2many('fallas', tracking=True)
    
    # Campo de estado simplificado (solo borrador y enviado)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('sent', 'Enviado')
    ], string='Estado', default='draft', tracking=True, copy=False)
    
    # Fechas de creación y envío
    create_date = fields.Datetime(string='Fecha de Creación', readonly=True)
    sent_date = fields.Datetime(string='Fecha de Envío', tracking=True, copy=False, readonly=True)

    @api.model
    def create(self, vals):
        if not vals.get('name') or vals['name'] == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('informes')
        return super(Informes, self).create(vals)

    def send_email(self):
        """Abre el wizard de composición de correo para enviar el informe"""
        self.ensure_one()
        
        template = self.env.ref('sat.email_template_informes')
        
        # No necesitamos verificar el email del proveedor ya que usamos uno predefinido
        ctx = {
            'default_model': 'informes',
            'default_res_ids': [self.id],
            'default_use_template': True,
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
            'force_email': True,
            'mark_so_as_sent': True,
            'custom_layout': "mail.mail_notification_light",
            # Forzamos el uso del email predefinido
            'default_email_from': 'soporte@andescopiers.com.pe',
            'default_email_to': 'lincoln@corapsac.com',
            'default_partner_to': False  # Evita que busque el partner del proveedor
        }
        
        # Actualizar el estado a enviado después de abrir el compositor de correo
        self.write({
            'state': 'sent',
            'sent_date': fields.Datetime.now()
        })
        
        # Registrar en el chatter que se ha enviado el correo
        self.message_post(
            body=f"Informe enviado por correo a: lincoln@corapsac.com",
            subject=f"Envío de Informe {self.name}"
        )
        
        return {
            'name': 'Enviar Informe por Correo',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'target': 'new',
            'context': ctx,
        }

    def _get_customer_information(self):
        """Override del método para evitar la dependencia del email del proveedor"""
        self.ensure_one()
        return {
            'name': 'Lincoln',  # Nombre fijo
            'email': 'lincoln@corapsac.com',  # Email fijo
            'lang': 'es_PE',  # Idioma por defecto
        }