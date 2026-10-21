# -*- coding: utf-8 -*-
"""Visto bueno SAT: firma en SharePoint, metadatos en Odoo.

Conserva la interfaz conformidad_firma en Base64 utilizada por Copier OS.
No crea ir.attachment para firmas nuevas. Las firmas antiguas permanecen
accesibles en ir.attachment hasta migrarlas.
"""
import base64
import binascii
import logging
import uuid

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from ..services.evidencia_microsoft_service import EvidenciaMicrosoftService

_logger = logging.getLogger(__name__)
MAX_SIGNATURE_BYTES = 3 * 1024 * 1024


class TicketServiceApproval(models.Model):
    _inherit = 'ticket.alquiler'

    conformidad_contacto_id = fields.Many2one(
        'res.partner', string='Contacto que dio conformidad', tracking=True,
        copy=False, index=True,
        help='Contacto de la empresa que recibió el servicio y dio su visto bueno.',
    )
    conformidad_nombre = fields.Char(string='Nombre de quien dio conformidad', tracking=True, copy=False)
    conformidad_dni = fields.Char(string='DNI de quien dio conformidad', tracking=True, copy=False, index=True)
    conformidad_celular = fields.Char(string='Celular de quien dio conformidad', tracking=True, copy=False)
    conformidad_correo = fields.Char(string='Correo de quien dio conformidad', tracking=True, copy=False)

    # El controlador de Flutter sigue escribiendo/leyendo este mismo campo.
    # Sin store y sin attachment: no se guarda su contenido en PostgreSQL/filestore.
    conformidad_firma = fields.Binary(
        string='Firma de conformidad', compute='_compute_conformidad_firma',
        attachment=False, copy=False,
        help='Firma obtenida bajo demanda desde Microsoft 365.',
    )
    conformidad_firma_filename = fields.Char(string='Nombre archivo firma', copy=False)
    conformidad_firma_location_id = fields.Many2one(
        'microsoft.storage.location', string='Ubicación SharePoint de firma',
        copy=False, readonly=True, ondelete='restrict',
    )
    conformidad_firma_item_id = fields.Char(string='ID Microsoft de firma', copy=False, readonly=True)
    conformidad_firma_folder_id = fields.Char(string='Carpeta Microsoft de firma', copy=False, readonly=True)
    conformidad_firma_url = fields.Char(string='URL Microsoft de firma', copy=False, readonly=True)

    conformidad_fecha = fields.Datetime(string='Fecha y hora de conformidad', tracking=True,
                                        copy=False, readonly=True)
    conformidad_tecnico_id = fields.Many2one('res.users', string='Técnico que obtuvo la conformidad',
                                             tracking=True, copy=False, readonly=True, index=True)
    conformidad_registrada = fields.Boolean(
        string='Conformidad registrada', compute='_compute_conformidad_registrada',
        store=True, index=True, help='Datos mínimos y firma registrados.',
    )

    @staticmethod
    def _decode_signature(value):
        if value in (None, False, '', b''):
            return None
        if isinstance(value, str):
            if value.startswith('data:') and ',' in value:
                value = value.split(',', 1)[1]
            try:
                value = value.encode('ascii')
            except UnicodeEncodeError as exc:
                raise UserError(_('La firma debe enviarse en Base64.')) from exc
        if not isinstance(value, (bytes, bytearray)) or len(value) > MAX_SIGNATURE_BYTES * 4 // 3 + 16:
            raise UserError(_('La firma tiene un formato o tamaño inválido.'))
        try:
            raw = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise UserError(_('La firma Base64 no es válida.')) from exc
        if not raw or len(raw) > MAX_SIGNATURE_BYTES:
            raise UserError(_('La firma no puede superar 3 MB.'))
        if raw.startswith(b'\x89PNG\r\n\x1a\n'):
            extension = '.png'
        elif raw.startswith(b'\xff\xd8\xff'):
            extension = '.jpg'
        else:
            raise UserError(_('Solo se admiten firmas PNG o JPEG.'))
        return raw, extension

    def _firma_legacy_attachment(self):
        self.ensure_one()
        return self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'conformidad_firma'),
        ], limit=1)

    def _firma_storage_service(self):
        """Usa exclusivamente la ubicación y usuario técnico configurados en SAT."""
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        location_value = icp.get_param('sat.evidencia_microsoft_location_id')
        user_value = icp.get_param('sat.evidencia_microsoft_service_user_id')
        if not location_value or not str(location_value).isdigit():
            raise UserError(_('Configure sat.evidencia_microsoft_location_id.'))
        if not user_value or not str(user_value).isdigit():
            raise UserError(_('Configure sat.evidencia_microsoft_service_user_id.'))
        location = self.env['microsoft.storage.location'].sudo().browse(int(location_value)).exists()
        user = self.env['res.users'].sudo().browse(int(user_value)).exists()
        if not location or not location.active or not location.drive_id:
            raise UserError(_('La biblioteca SharePoint de SAT no está disponible.'))
        if not user or not user.active or user.share:
            raise UserError(_('El usuario técnico SAT debe ser interno y estar activo.'))
        location.with_user(user).check_operation('upload', user)
        service = EvidenciaMicrosoftService(location.with_user(user), user=user)
        return service, location

    def _firma_folder(self, service):
        """SAT/Evidencias/AÑO/Ticket-ID/CONFORMIDAD en la biblioteca configurada."""
        self.ensure_one()
        year = fields.Datetime.to_datetime(fields.Datetime.now()).year
        parts = ('SAT', 'Evidencias', str(year), 'Ticket-%s' % self.id, 'CONFORMIDAD')
        parent_id = None
        for name in parts:
            parent_id = service._ensure_folder(parent_id, name)
        return parent_id

    def _save_signature_microsoft(self, value):
        self.ensure_one()
        decoded = self._decode_signature(value)
        if decoded is None:
            return {
                'conformidad_firma_location_id': False,
                'conformidad_firma_folder_id': False,
                'conformidad_firma_item_id': False,
                'conformidad_firma_url': False,
            }
        raw, extension = decoded
        service, location = self._firma_storage_service()
        folder_id = self._firma_folder(service)
        filename = 'firma_conformidad_%s_%s%s' % (self.id, uuid.uuid4().hex, extension)
        # upload_file valida permiso de subida y confirma el ID de Microsoft.
        result = service.drive.upload_file(filename, raw, parent_id=folder_id)
        if not isinstance(result, dict) or not result.get('id'):
            raise UserError(_('Microsoft no confirmó la subida de la firma.'))
        _logger.info('[SAT][CONFORMIDAD] Firma en SharePoint ticket=%s item=%s',
                     self.id, result['id'])
        return {
            'conformidad_firma_location_id': location.id,
            'conformidad_firma_folder_id': folder_id,
            'conformidad_firma_item_id': result['id'],
            'conformidad_firma_url': result.get('webUrl') or False,
            'conformidad_firma_filename': result.get('name') or filename,
        }

    def _read_signature_microsoft(self):
        self.ensure_one()
        if not self.conformidad_firma_item_id:
            return False
        service, location = self._firma_storage_service()
        if location.id != self.conformidad_firma_location_id.id:
            raise UserError(_('La ubicación de la firma no coincide con SharePoint SAT.'))
        url, item = service.drive.get_download_url(self.conformidad_firma_item_id)
        if item.get('size') and int(item['size']) > MAX_SIGNATURE_BYTES:
            raise UserError(_('La firma supera el límite de visualización.'))
        # URL temporal validada por DriveService; sin reenviar tokens Graph.
        with requests.get(url, stream=True, timeout=45, allow_redirects=False) as response:
            if response.status_code != 200:
                raise UserError(_('No se pudo recuperar la firma desde Microsoft 365.'))
            chunks = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                chunks.extend(chunk)
                if len(chunks) > MAX_SIGNATURE_BYTES:
                    raise UserError(_('La firma descargada supera 3 MB.'))
        return base64.b64encode(bytes(chunks))

    @api.depends('conformidad_firma_item_id')
    def _compute_conformidad_firma(self):
        for ticket in self:
            if ticket.conformidad_firma_item_id:
                ticket.conformidad_firma = ticket._read_signature_microsoft()
            else:
                attachment = ticket._firma_legacy_attachment() if ticket.id else False
                ticket.conformidad_firma = attachment.datas if attachment else False

    @api.depends('conformidad_nombre', 'conformidad_dni', 'conformidad_celular',
                 'conformidad_correo', 'conformidad_firma_item_id', 'conformidad_fecha')
    def _compute_conformidad_registrada(self):
        for ticket in self:
            has_signature = bool(ticket.conformidad_firma_item_id)
            if not has_signature and ticket.id:
                has_signature = bool(ticket._firma_legacy_attachment())
            ticket.conformidad_registrada = bool(
                ticket.conformidad_nombre and ticket.conformidad_dni
                and ticket.conformidad_celular and ticket.conformidad_correo
                and has_signature and ticket.conformidad_fecha
            )

    @api.model_create_multi
    def create(self, vals_list):
        pending = []
        clean = []
        for vals in vals_list:
            vals = dict(vals)
            if 'conformidad_firma' in vals:
                pending.append((len(clean), vals.pop('conformidad_firma')))
            clean.append(vals)
        records = super().create(clean)
        for index, signature in pending:
            records[index].write({'conformidad_firma': signature})
        return records

    def write(self, vals):
        if 'conformidad_firma' not in vals:
            return super().write(vals)
        clean = dict(vals)
        signature = clean.pop('conformidad_firma')
        # La limpieza no elimina el archivo remoto: conservar auditoría histórica.
        for ticket in self:
            values = dict(clean)
            values.update(ticket._save_signature_microsoft(signature))
            super(TicketServiceApproval, ticket).write(values)
        return True

    @api.constrains('conformidad_dni')
    def _check_conformidad_dni(self):
        for ticket in self:
            if ticket.conformidad_dni:
                dni = ''.join(c for c in str(ticket.conformidad_dni) if c.isdigit())
                if len(dni) != 8:
                    raise ValidationError(_('El DNI de quien da conformidad debe contener exactamente 8 dígitos.'))

    @api.constrains('conformidad_correo')
    def _check_conformidad_correo(self):
        for ticket in self:
            if ticket.conformidad_correo:
                email = ticket.conformidad_correo.strip()
                if '@' not in email or '.' not in email.split('@')[-1]:
                    raise ValidationError(_('El correo de quien da conformidad no tiene un formato válido.'))

    def action_limpiar_conformidad(self):
        for ticket in self:
            if ticket.estado == 'finalizado':
                raise ValidationError(_('No se puede eliminar la conformidad de un ticket ya finalizado.'))
            ticket.write({
                'conformidad_contacto_id': False,
                'conformidad_nombre': False,
                'conformidad_dni': False,
                'conformidad_celular': False,
                'conformidad_correo': False,
                'conformidad_firma': False,
                'conformidad_firma_filename': False,
                'conformidad_fecha': False,
                'conformidad_tecnico_id': False,
            })
        return True
