# -*- coding: utf-8 -*-
from odoo import models, fields, api


class Informes(models.Model):
    _name = 'informes'
    _description = 'Registro de informes proveedores'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Informe N°',
        default='/',
        copy=False,
        required=True,
        readonly=True,
        tracking=True,
    )
    proveedor_id = fields.Many2one('res.partner', string='Proveedor', tracking=True)
    importacion = fields.Char(string='Importación', tracking=True)
    invoice = fields.Char(string='Invoice', tracking=True)
    informe = fields.Text(
        string='Informe',
        default=(
            'Estimados señores,\n\n'
            'Mediante el presente documento, les entregamos el informe del estado '
            'de las máquinas fotocopiadoras.\n\n'
            ' Durante el mantenimiento realizado, se detectaron fallas y se '
            'identificaron los elementos que deben ser reemplazados para asegurar '
            'su correcto funcionamiento.\n\n'
            'A continuación, detallamos el informe de cada una de las máquinas:'
        ),
        tracking=True,
    )
    detalle_ids = fields.Many2many('fallas', tracking=True)

    state = fields.Selection(
        [('draft', 'Borrador'), ('sent', 'Enviado')],
        string='Estado',
        default='draft',
        tracking=True,
        copy=False,
    )

    # create_date es el campo automático del ORM de Odoo; se mantiene
    # la redefinición original para preservar la vista y etiqueta existentes.
    create_date = fields.Datetime(string='Fecha de Creación', readonly=True)
    sent_date = fields.Datetime(
        string='Fecha de Envío', tracking=True, copy=False, readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Genera una secuencia independiente por informe (API Odoo 19)."""
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == '/':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('informes') or '/'
                )
        return super().create(vals_list)

    def send_email(self):
        """Abre el compositor para enviar el informe al destinatario fijo."""
        self.ensure_one()
        template = self.env.ref('sat.email_template_informes')

        ctx = {
            'default_model': 'informes',
            'default_res_ids': [self.id],
            'default_use_template': True,
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
            'force_email': True,
            'mark_so_as_sent': True,
            'custom_layout': 'mail.mail_notification_light',
            'default_email_from': 'soporte@andescopiers.com.pe',
            'default_email_to': 'lincoln@corapsac.com',
            'default_partner_to': False,
        }

        # Se conserva el flujo existente. Esta marca se realiza al ABRIR
        # el compositor, no confirma el envío efectivo del correo.
        self.write({
            'state': 'sent',
            'sent_date': fields.Datetime.now(),
        })
        self.message_post(
            body='Informe enviado por correo a: lincoln@corapsac.com',
            subject=f'Envío de Informe {self.name}',
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
        """Devuelve el contacto fijo sin depender del correo del proveedor."""
        self.ensure_one()
        return {
            'name': 'Lincoln',
            'email': 'lincoln@corapsac.com',
            'lang': 'es_PE',
        }
