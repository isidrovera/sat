# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

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

    # Imagen original tal como la subió el técnico (sin watermark)
    imagen_original = fields.Binary(
        string='Imagen original',
        attachment=True,
        required=True,
    )
    imagen_original_filename = fields.Char(string='Nombre archivo original')

    # Imagen procesada con logo + mapa + texto (se rellena en Fase 2)
    imagen_procesada = fields.Binary(
        string='Imagen procesada',
        attachment=True,
    )
    imagen_procesada_filename = fields.Char(string='Nombre archivo procesado')

    # Geolocalización capturada por el navegador del técnico
    latitud = fields.Float(string='Latitud', digits=(16, 8))
    longitud = fields.Float(string='Longitud', digits=(16, 8))
    precision_gps = fields.Float(
        string='Precisión GPS (m)',
        help='Precisión reportada por el navegador en metros',
    )

    # Dirección obtenida por reverse geocoding (se rellena en Fase 2)
    direccion_capturada = fields.Char(string='Dirección capturada')

    # Metadata
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

    # Computados
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
        self.ensure_one()

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/image/ticket.evidencia.foto/%s/imagen_original' % self.id,
            'target': 'new',
        }


    def action_descargar_foto(self):
        self.ensure_one()

        filename = self.imagen_original_filename or ('evidencia_%s.jpg' % self.id)

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/ticket.evidencia.foto/%s/imagen_original/%s?download=true' % (
                self.id,
                filename,
            ),
            'target': 'self',
        }