# -*- coding: utf-8 -*-
import uuid
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TicketAlquilerEvidencia(models.Model):
    _inherit = 'ticket.alquiler'

    # ─── Token público para subida de evidencia ──────────────────────
    evidencia_token = fields.Char(
        string='Token de evidencia',
        readonly=True,
        copy=False,
        index=True,
        help='Token único usado en la URL pública para subir fotos de evidencia',
    )

    # ─── Fotos de evidencia ──────────────────────────────────────────
    evidencia_foto_ids = fields.One2many(
        'ticket.evidencia.foto',
        'ticket_id',
        string='Fotos de evidencia',
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
    def _compute_evidencia_counts(self):
        for rec in self:
            rec.evidencia_antes_count = len(rec.evidencia_foto_ids.filtered(
                lambda f: f.momento == 'antes'
            ))
            rec.evidencia_despues_count = len(rec.evidencia_foto_ids.filtered(
                lambda f: f.momento == 'despues'
            ))

    # ─── Generación del token al crear el ticket ─────────────────────
    @api.model
    def create(self, vals):
        record = super().create(vals)
        if not record.evidencia_token:
            record.evidencia_token = str(uuid.uuid4())
        return record

    def _ensure_evidencia_token(self):
        """Garantiza que el ticket tenga token. Útil para tickets antiguos."""
        for rec in self:
            if not rec.evidencia_token:
                rec.evidencia_token = str(uuid.uuid4())

    def _get_evidencia_url(self):
        """Devuelve la URL pública para subir evidencia."""
        self.ensure_one()
        self._ensure_evidencia_token()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/evidencia/{self.evidencia_token}"

    # ─── Acciones desde el form del ticket ───────────────────────────
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
        """Envía el link al técnico responsable por WhatsApp."""
        self.ensure_one()
        if not self.responsable:
            raise UserError(_(
                "No hay técnico responsable asignado para enviar el link."
            ))
        if not self.responsable_mobile_clean or self.responsable_mobile_clean == 'NA':
            raise UserError(_(
                "El técnico responsable no tiene un número de celular válido."
            ))

        url = self._get_evidencia_url()
        mensaje = (
            f"Hola {self.responsable.name or 'técnico'},\n\n"
            f"Aquí está el link para subir las fotos de evidencia del ticket {self.name}:\n"
            f"Cliente: {self.partner_id.name or 'N/A'}\n"
            f"Equipo: {self.modelo_id_r or 'N/A'} (Serie: {self.serie_id_r or 'N/A'})\n\n"
            f"📸 {url}\n\n"
            f"Recuerda: el navegador te pedirá permiso de ubicación, debes aceptarlo."
        )

        # Abre WhatsApp Web/app con el mensaje pre-cargado
        whatsapp_url = (
            f"https://wa.me/{self.responsable_mobile_clean}"
            f"?text={mensaje}"
        )
        # URL-encode del texto
        from urllib.parse import quote
        whatsapp_url = (
            f"https://wa.me/{self.responsable_mobile_clean}"
            f"?text={quote(mensaje)}"
        )

        self.message_post(
            body=_("📲 Link de evidencia enviado por WhatsApp al técnico %s") % (
                self.responsable.name
            ),
            message_type='notification',
        )

        return {
            'type': 'ir.actions.act_url',
            'url': whatsapp_url,
            'target': 'new',
        }