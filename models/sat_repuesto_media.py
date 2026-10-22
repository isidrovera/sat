
# -*- coding: utf-8 -*-
"""Visualización de archivos SharePoint en la biblioteca SAT.

Amplía los modelos existentes sin crear tablas nuevas.
Los archivos originales permanecen en SharePoint.
"""

from odoo import api, fields, models


class SatRepuestoCompatibilidadMedia(models.Model):
    _inherit = 'sat.repuesto.compatibilidad'

    foto_principal_url = fields.Char(
        string='Vista previa principal',
        compute='_compute_foto_principal_url',
        compute_sudo=False,
    )

    @api.depends(
        'foto_ids',
        'foto_ids.principal',
        'foto_ids.mime_type',
        'foto_ids.sharepoint_item_id',
    )
    def _compute_foto_principal_url(self):
        for record in self:
            imagenes = record.foto_ids.filtered(
                lambda foto: (
                    bool(foto.sharepoint_item_id)
                    and (foto.mime_type or '')
                    .lower()
                    .startswith('image/')
                    and (foto.mime_type or '').lower()
                    != 'image/svg+xml'
                )
            )

            principal = (
                imagenes.filtered('principal')[:1]
                or imagenes[:1]
            )

            record.foto_principal_url = (
                '/sat/repuestos/media/%s?size=medium'
                % principal.id
                if principal
                else False
            )


class SatRepuestoFotoMedia(models.Model):
    _inherit = 'sat.repuesto.foto'

    media_url = fields.Char(
        string='URL de visualización',
        compute='_compute_media_info',
        compute_sudo=False,
    )

    media_tipo = fields.Selection(
        [
            ('imagen', 'Imagen'),
            ('video', 'Video'),
            ('pdf', 'PDF'),
            ('otro', 'Otro documento'),
        ],
        string='Tipo de archivo',
        compute='_compute_media_info',
        compute_sudo=False,
    )

    @api.depends(
        'mime_type',
        'sharepoint_item_id',
    )
    def _compute_media_info(self):
        for record in self:
            mime = (
                (record.mime_type or '')
                .split(';', 1)[0]
                .strip()
                .lower()
            )

            if (
                mime.startswith('image/')
                and mime != 'image/svg+xml'
            ):
                record.media_tipo = 'imagen'

            elif mime.startswith('video/'):
                record.media_tipo = 'video'

            elif mime == 'application/pdf':
                record.media_tipo = 'pdf'

            else:
                record.media_tipo = 'otro'

            record.media_url = (
                '/sat/repuestos/media/%s' % record.id
                if record.id and record.sharepoint_item_id
                else False
            )
