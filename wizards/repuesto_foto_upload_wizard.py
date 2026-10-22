# -*- coding: utf-8 -*-
"""Carga de archivos de compatibilidades directamente en SharePoint.

Mantiene el nombre técnico del campo `imagen` para no romper la vista actual.
El binario temporal no utiliza ir.attachment (attachment=False).
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
    _description = 'Subir archivo de repuesto a SharePoint'

    compatibilidad_id = fields.Many2one(
        'sat.repuesto.compatibilidad', string='Ficha de compatibilidad',
        required=True, readonly=True, ondelete='cascade',
    )
    location_id = fields.Many2one(
        'microsoft.storage.location', string='Biblioteca SharePoint',
        required=True, domain=[('active', '=', True)],
    )
    imagen = fields.Binary(
        string='Archivo', required=True, attachment=False,
        help='Archivo temporal para enviar directamente a SharePoint.',
    )
    imagen_filename = fields.Char(string='Nombre del archivo')
    principal = fields.Boolean(string='Fotografía principal', default=False)
    notas = fields.Char(string='Descripción del archivo')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if 'location_id' in fields_list and not values.get('location_id'):
            locations = self.env['microsoft.storage.location'].search(
                [('active', '=', True), ('drive_id', '!=', False)], limit=2,
            )
            if len(locations) == 1:
                values['location_id'] = locations.id
        return values

    def action_upload(self):
        self.ensure_one()
        ficha = self.compatibilidad_id.exists()
        if not ficha:
            raise UserError(_('La ficha de compatibilidad ya no existe.'))
        ficha.check_access('write')
        self.env['sat.repuesto.foto'].check_access('create')
        if not self.location_id or not self.location_id.active or not self.location_id.drive_id:
            raise UserError(_('Seleccione una biblioteca SharePoint activa.'))
        if not self.imagen or not self.imagen_filename:
            raise UserError(_('Seleccione un archivo con su nombre original.'))
        try:
            data = base64.b64decode(self.imagen, validate=True)
        except (binascii.Error, ValueError, TypeError) as error:
            raise UserError(_('No se pudo interpretar el archivo seleccionado.')) from error

        service = RepuestoMicrosoftService(self.location_id, user=self.env.user)
        # Validar antes de cualquier solicitud remota.
        validated_data, safe_filename, mime_type = service.validate_file(
            data, self.imagen_filename
        )
        if self.principal and not mime_type.startswith('image/'):
            raise UserError(_('Solo una imagen puede marcarse como fotografía principal.'))

        _logger.info(
            '[BIBLIOTECA][ARCHIVO][INICIO] ficha=%s usuario=%s archivo=%s bytes=%s',
            ficha.id, self.env.user.id, self.imagen_filename, len(data),
        )
        info = service.upload(ficha, validated_data, safe_filename)
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
                # Limpiar principales anteriores antes de asignar la nueva,
                # respetando la restricción del modelo sat.repuesto.foto.
                old_main = ficha.foto_ids.filtered(
                    lambda item: item.id != photo.id and item.principal
                )
                if old_main:
                    old_main.write({'principal': False})
                photo.write({'principal': True})
        except Exception:
            _logger.exception(
                '[BIBLIOTECA][ARCHIVO][REGISTRO_ERROR] Archivo remoto pendiente '
                'de conciliación ficha=%s drive=%s item=%s',
                ficha.id, info.get('drive_id'), info.get('item_id'),
            )
            raise

        # NO vaciar `imagen`: es required=True. El asistente temporal será
        # limpiado por el mecanismo de mantenimiento de TransientModel.
        _logger.info(
            '[BIBLIOTECA][ARCHIVO][OK] ficha=%s archivo_id=%s drive=%s item=%s',
            ficha.id, photo.id, info['drive_id'], info['item_id'],
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ficha de compatibilidad'),
            'res_model': 'sat.repuesto.compatibilidad',
            'res_id': ficha.id,
            'view_mode': 'form',
            'target': 'current',
        }
