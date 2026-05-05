# -*- coding: utf-8 -*-

import uuid
import logging
from urllib.parse import quote

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TicketEvidenciaFoto(models.Model):
    _name = 'ticket.evidencia.foto'
    _description = 'Foto de evidencia de ticket de servicio'
    _order = 'momento, timestamp_captura desc'

    ticket_id = fields.Many2one(
        'ticket.alquiler',
        string='Ticket',
        required=True,
        ondelete='cascade',
        index=True,
    )

    momento = fields.Selection([
        ('antes', 'Antes (al llegar)'),
        ('despues', 'Después (al finalizar)'),
    ], string='Momento', required=True, index=True)

    imagen_original = fields.Binary(
        string='Imagen original',
        attachment=True,
        required=True,
    )
    imagen_original_filename = fields.Char(string='Nombre archivo original')

    imagen_procesada = fields.Binary(
        string='Imagen procesada',
        attachment=True,
    )
    imagen_procesada_filename = fields.Char(string='Nombre archivo procesado')

    latitud = fields.Float(string='Latitud', digits=(16, 8))
    longitud = fields.Float(string='Longitud', digits=(16, 8))
    precision_gps = fields.Float(
        string='Precisión GPS (m)',
        help='Precisión reportada por el navegador en metros',
    )

    direccion_capturada = fields.Char(string='Dirección capturada')

    timestamp_captura = fields.Datetime(
        string='Fecha/hora de captura',
        default=fields.Datetime.now,
        required=True,
    )

    user_agent = fields.Char(
        string='User Agent',
        help='Navegador/dispositivo desde el que se subió',
    )
    ip_origen = fields.Char(string='IP de origen')

    tiene_coordenadas = fields.Boolean(
        string='Tiene coordenadas',
        compute='_compute_tiene_coordenadas',
        store=True,
    )

    nombre_display = fields.Char(
        string='Nombre',
        compute='_compute_nombre_display',
    )

    @api.depends('latitud', 'longitud')
    def _compute_tiene_coordenadas(self):
        for rec in self:
            rec.tiene_coordenadas = bool(rec.latitud and rec.longitud)

    @api.depends('momento', 'timestamp_captura', 'ticket_id')
    def _compute_nombre_display(self):
        for rec in self:
            momento_label = dict(rec._fields['momento'].selection).get(rec.momento, '')
            ts = rec.timestamp_captura.strftime('%d/%m/%Y %H:%M') if rec.timestamp_captura else ''
            rec.nombre_display = f"{momento_label} — {ts}"

    def action_abrir_en_maps(self):
        """Abre las coordenadas en Google Maps."""
        self.ensure_one()

        if not self.tiene_coordenadas:
            return False

        url = f"https://www.google.com/maps?q={self.latitud},{self.longitud}"

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_ver_foto(self):
        """Abre la foto como modal interno de Odoo."""
        self.ensure_one()

        view = self.env.ref(
            'sat.view_ticket_evidencia_foto_form_modal',
            raise_if_not_found=False
        )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Foto de evidencia',
            'res_model': 'ticket.evidencia.foto',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')] if view else [(False, 'form')],
            'target': 'new',
            'context': {
                'form_view_initial_mode': 'readonly',
            },
        }

    def action_abrir_foto_original(self):
        """Abre la imagen original en una pestaña nueva."""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/image/ticket.evidencia.foto/%s/imagen_original' % self.id,
            'target': 'new',
        }

    def action_descargar_foto(self):
        """Descarga la foto original."""
        self.ensure_one()

        filename = self.imagen_original_filename or ('evidencia_%s.jpg' % self.id)
        filename = quote(filename)

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/ticket.evidencia.foto/%s/imagen_original/%s?download=true' % (
                self.id,
                filename,
            ),
            'target': 'self',
        }


class TicketAlquilerEvidencia(models.Model):
    _inherit = 'ticket.alquiler'

    evidencia_token = fields.Char(
        string='Token de evidencia',
        readonly=True,
        copy=False,
        index=True,
        help='Token único usado en la URL pública para subir fotos de evidencia',
    )

    evidencia_foto_ids = fields.One2many(
        'ticket.evidencia.foto',
        'ticket_id',
        string='Fotos de evidencia',
    )

    evidencia_foto_antes_ids = fields.One2many(
        'ticket.evidencia.foto',
        compute='_compute_evidencia_foto_momento_ids',
        string='Fotos antes',
    )

    evidencia_foto_despues_ids = fields.One2many(
        'ticket.evidencia.foto',
        compute='_compute_evidencia_foto_momento_ids',
        string='Fotos después',
    )

    evidencia_antes_count = fields.Integer(
        string='Fotos antes',
        compute='_compute_evidencia_counts',
    )

    evidencia_despues_count = fields.Integer(
        string='Fotos después',
        compute='_compute_evidencia_counts',
    )

    @api.depends('evidencia_foto_ids', 'evidencia_foto_ids.momento')
    def _compute_evidencia_foto_momento_ids(self):
        for rec in self:
            rec.evidencia_foto_antes_ids = rec.evidencia_foto_ids.filtered(
                lambda f: f.momento == 'antes'
            )
            rec.evidencia_foto_despues_ids = rec.evidencia_foto_ids.filtered(
                lambda f: f.momento == 'despues'
            )

    @api.depends('evidencia_foto_ids', 'evidencia_foto_ids.momento')
    def _compute_evidencia_counts(self):
        for rec in self:
            rec.evidencia_antes_count = len(rec.evidencia_foto_ids.filtered(
                lambda f: f.momento == 'antes'
            ))
            rec.evidencia_despues_count = len(rec.evidencia_foto_ids.filtered(
                lambda f: f.momento == 'despues'
            ))

    @api.model
    def create(self, vals):
        record = super().create(vals)

        if not record.evidencia_token:
            record.evidencia_token = str(uuid.uuid4())

        return record

    def _ensure_evidencia_token(self):
        """Garantiza que el ticket tenga token."""
        for rec in self:
            if not rec.evidencia_token:
                rec.evidencia_token = str(uuid.uuid4())

    def _get_evidencia_url(self):
        """Devuelve la URL pública para subir evidencia."""
        self.ensure_one()
        self._ensure_evidencia_token()

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        return f"{base_url}/evidencia/{self.evidencia_token}"

    def action_copiar_link_evidencia(self):
        """Muestra el link al usuario para que lo copie manualmente."""
        self.ensure_one()

        url = self._get_evidencia_url()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Link de evidencia'),
                'message': url,
                'type': 'success',
                'sticky': True,
            }
        }

    def action_abrir_link_evidencia(self):
        """Abre el link de evidencia en pestaña nueva."""
        self.ensure_one()

        url = self._get_evidencia_url()

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_enviar_link_whatsapp_tecnico(self):
        """Envía/reenvía solo el link de evidencia al técnico responsable por WhatsApp."""
        self.ensure_one()

        if not self.responsable:
            raise UserError(_("No hay técnico responsable asignado para enviar el link."))

        if not self.responsable_mobile_clean or self.responsable_mobile_clean == 'NA':
            raise UserError(_("El técnico responsable no tiene un número de celular válido."))

        url = self._get_evidencia_url()

        mensaje = (
            f"Hola {self.responsable.name or 'técnico'},\n\n"
            f"Link para subir las fotos de evidencia del ticket {self.name}:\n\n"
            f"📸 {url}\n\n"
            f"Indicaciones:\n"
            f"1. Abrir el link desde el celular.\n"
            f"2. Permitir ubicación/GPS cuando el navegador lo solicite.\n"
            f"3. Subir fotos en ANTES al llegar y DESPUÉS al finalizar."
        )

        self.send_whatsapp_message(self.responsable_mobile_clean, mensaje)

        self.message_post(
            body=_("📲 Link de evidencia enviado por WhatsApp al técnico %s") % (
                self.responsable.name
            ),
            message_type='notification',
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('WhatsApp enviado'),
                'message': _('Se envió el link de evidencia al técnico.'),
                'type': 'success',
                'sticky': False,
            }
        }