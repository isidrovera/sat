
# -*- coding: utf-8 -*-
"""Asistente para subir fotos de referencias de repuestos a SharePoint.

Los binarios viven temporalmente en el TransientModel (attachment=False),
no en ir.attachment. El archivo final se conserva en SharePoint.
"""

import base64
import binascii
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..services.repuesto_microsoft_service import RepuestoMicrosoftService

_logger = logging.getLogger(__name__)


class SatRepuestoFotoUploadWizard(models.TransientModel):
    _name = 'sat.repuesto.foto.upload.wizard'
    _description = 'Subir fotografía de repuesto a SharePoint'

    compatibilidad_id = fields.Many2one(
        'sat.repuesto.compatibilidad',
        string='Ficha de compatibilidad',
        required=True,
        readonly=True,
        ondelete='cascade',
    )

    location_id = fields.Many2one(
        'microsoft.storage.location',
        string='Biblioteca SharePoint',
        required=True,
        domain=[('active', '=', True)],
        help='Biblioteca de Microsoft 365 donde se almacenará la fotografía.',
    )

    imagen = fields.Binary(
        string='Fotografía',
        required=True,
        attachment=False,
        help='Archivo temporal para enviarlo a SharePoint. No se guarda en ir.attachment.',
    )

    imagen_filename = fields.Char(string='Nombre del archivo')
    principal = fields.Boolean(string='Fotografía principal', default=False)
    notas = fields.Char(string='Descripción de la fotografía')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)

        if 'location_id' in fields_list and not values.get('location_id'):
            locations = self.env['microsoft.storage.location'].search(
                [('active', '=', True), ('drive_id', '!=', False)],
                limit=2,
            )

            if len(locations) == 1:
                values['location_id'] = locations.id

        return values

    def action_upload(self):
        self.ensure_one()

        ficha = self.compatibilidad_id.exists()

        if not ficha:
            raise UserError(
                _('La ficha de compatibilidad ya no existe.')
            )

        ficha.check_access('write')
        self.env['sat.repuesto.foto'].check_access('create')

        if (
            not self.location_id
            or not self.location_id.active
            or not self.location_id.drive_id
        ):
            raise UserError(
                _('Seleccione una biblioteca SharePoint activa.')
            )

        if not self.imagen:
            raise UserError(
                _('Seleccione la fotografía que desea subir.')
            )

        filename = self.imagen_filename or 'fotografia.jpg'

        try:
            image_data = base64.b64decode(
                self.imagen,
                validate=True,
            )
        except (binascii.Error, ValueError, TypeError) as error:
            raise UserError(
                _('No se pudo interpretar el contenido de la fotografía.')
            ) from error

        service = RepuestoMicrosoftService(
            self.location_id,
            user=self.env.user,
        )

        _logger.info(
            '[BIBLIOTECA][FOTO][INICIO] '
            'ficha=%s usuario=%s biblioteca=%s archivo=%s bytes=%s',
            ficha.id,
            self.env.user.id,
            self.location_id.id,
            filename,
            len(image_data),
        )

        info = service.upload(
            ficha,
            image_data,
            filename,
        )

        try:
            photo = self.env['sat.repuesto.foto'].create({
                'compatibilidad_id': ficha.id,
                'name': info['name'],
                'principal': False,
                'notas': self.notas or False,
                'sharepoint_drive_id': info['drive_id'],
                'sharepoint_item_id': info['item_id'],
                'sharepoint_web_url': info.get('web_url') or False,
                'mime_type': info.get('mime_type') or False,
            })

            if self.principal:
                other_main_photos = ficha.foto_ids.filtered(
                    lambda photo_record: (
                        photo_record.id != photo.id
                        and photo_record.principal
                    )
                )

                if other_main_photos:
                    other_main_photos.write({
                        'principal': False,
                    })

                photo.write({
                    'principal': True,
                })

        except Exception:
            _logger.exception(
                '[BIBLIOTECA][FOTO][ERROR_REGISTRO] '
                'Archivo remoto posiblemente huérfano '
                'ficha=%s drive=%s item=%s',
                ficha.id,
                info.get('drive_id'),
                info.get('item_id'),
            )
            raise

        self.write({
            'imagen': False,
        })

        _logger.info(
            '[BIBLIOTECA][FOTO][OK] '
            'ficha=%s foto=%s drive=%s item=%s principal=%s',
            ficha.id,
            photo.id,
            info['drive_id'],
            info['item_id'],
            self.principal,
        )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Ficha de compatibilidad'),
            'res_model': 'sat.repuesto.compatibilidad',
            'res_id': ficha.id,
            'view_mode': 'form',
            'target': 'current',
        }
