# -*- coding: utf-8 -*-
"""Evidencias SAT en Microsoft 365, sin persistir nuevas imágenes en Odoo.

Flutter y los controladores actuales pueden seguir enviando `imagen_original`
y `imagen_procesada` en Base64 mediante create/write. Las lecturas de esos
campos recuperan el contenido remoto temporalmente (no ir.attachment).

Parámetros del sistema:
  sat.evidencia_microsoft_location_id: ID de una ubicación SharePoint existente
  sat.evidencia_microsoft_service_user_id: ID de usuario interno con rol editor
    en esa ubicación (obligatorio para llamadas desde Flutter/API públicas).

Las imágenes anteriores continúan en sus adjuntos originales hasta migrarlas.
"""

import base64
import binascii
import logging
import uuid
from urllib.parse import quote

import requests

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.addons.odoo_onedrive_integration.services.drive_service import DriveService
from ..services.evidencia_microsoft_service import EvidenciaMicrosoftService

_logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 20 * 1024 * 1024


class TicketEvidenciaFoto(models.Model):
    _name = 'ticket.evidencia.foto'
    _description = 'Foto de evidencia de ticket de servicio'
    _order = 'momento, timestamp_captura desc'

    ticket_id = fields.Many2one('ticket.alquiler', string='Ticket', required=True,
                                ondelete='cascade', index=True)
    momento = fields.Selection([
        ('antes', 'Antes (al llegar)'),
        ('despues', 'Después (al finalizar)'),
    ], string='Momento', required=True, index=True)

    # Compatibilidad de nombres con Flutter, controlador y vistas existentes.
    # Estos campos nunca se almacenan para registros nuevos.
    imagen_original = fields.Binary(string='Imagen original', attachment=False,
                                    compute='_compute_remote_images', readonly=True)
    imagen_original_filename = fields.Char(string='Nombre archivo original')
    imagen_procesada = fields.Binary(string='Imagen procesada', attachment=False,
                                     compute='_compute_remote_images', readonly=True)
    imagen_procesada_filename = fields.Char(string='Nombre archivo procesado')

    microsoft_location_id = fields.Many2one(
        'microsoft.storage.location', string='Ubicación Microsoft 365',
        readonly=True, copy=False, ondelete='restrict')
    microsoft_folder_id = fields.Char(string='Carpeta Microsoft', readonly=True, copy=False)
    microsoft_original_item_id = fields.Char(string='ID original Microsoft', readonly=True, copy=False)
    microsoft_original_url = fields.Char(string='URL original Microsoft', readonly=True, copy=False)
    microsoft_procesada_item_id = fields.Char(string='ID procesada Microsoft', readonly=True, copy=False)
    microsoft_procesada_url = fields.Char(string='URL procesada Microsoft', readonly=True, copy=False)

    latitud = fields.Float(string='Latitud', digits=(16, 8))
    longitud = fields.Float(string='Longitud', digits=(16, 8))
    precision_gps = fields.Float(string='Precisión GPS (m)',
                                 help='Precisión reportada por el navegador en metros')
    direccion_capturada = fields.Char(string='Dirección capturada')
    timestamp_captura = fields.Datetime(string='Fecha/hora de captura',
                                        default=fields.Datetime.now, required=True)
    user_agent = fields.Char(string='User Agent',
                             help='Navegador/dispositivo desde el que se subió')
    ip_origen = fields.Char(string='IP de origen')
    tiene_coordenadas = fields.Boolean(string='Tiene coordenadas',
                                       compute='_compute_tiene_coordenadas', store=True)
    nombre_display = fields.Char(string='Nombre', compute='_compute_nombre_display')

    @api.depends('latitud', 'longitud')
    def _compute_tiene_coordenadas(self):
        for rec in self:
            rec.tiene_coordenadas = (rec.latitud not in (False, None)
                                     and rec.longitud not in (False, None))

    @api.depends('momento', 'timestamp_captura', 'ticket_id')
    def _compute_nombre_display(self):
        selection = dict(self._fields['momento'].selection)
        for rec in self:
            label = selection.get(rec.momento, '')
            stamp = rec.timestamp_captura.strftime('%d/%m/%Y %H:%M') if rec.timestamp_captura else ''
            rec.nombre_display = '%s — %s' % (label, stamp)

    @staticmethod
    def _decode_image(value):
        if value in (False, None, ''):
            return None
        if isinstance(value, str):
            value = value.encode('ascii', errors='strict')
        if not isinstance(value, (bytes, bytearray)):
            raise UserError(_('La fotografía debe enviarse en Base64.'))
        if len(value) > (MAX_IMAGE_BYTES * 4 // 3 + 16):
            raise UserError(_('La fotografía supera el límite de 20 MB.'))
        try:
            raw = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as error:
            raise UserError(_('La fotografía no contiene Base64 válido.')) from error
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise UserError(_('La fotografía debe tener entre 1 byte y 20 MB.'))
        if not (raw.startswith(b'\xff\xd8\xff')
                or raw.startswith(b'\x89PNG\r\n\x1a\n')
                or (raw.startswith(b'RIFF') and raw[8:12] == b'WEBP')):
            raise UserError(_('Solo se admiten imágenes JPEG, PNG y WebP.'))
        return raw

    @staticmethod
    def _new_filename(raw, kind):
        extension = '.jpg' if raw.startswith(b'\xff\xd8\xff') else (
            '.png' if raw.startswith(b'\x89PNG') else '.webp')
        return '%s_%s%s' % (kind, uuid.uuid4().hex, extension)

    @api.model
    def _storage_service(self, location_id=None):
        config = self.env['ir.config_parameter'].sudo()
        raw_location = config.get_param('sat.evidencia_microsoft_location_id')
        raw_user = config.get_param('sat.evidencia_microsoft_service_user_id')
        if not raw_location or not str(raw_location).isdigit():
            raise UserError(_('Configure sat.evidencia_microsoft_location_id con el ID de la biblioteca.'))
        if not raw_user or not str(raw_user).isdigit():
            raise UserError(_('Configure sat.evidencia_microsoft_service_user_id con un usuario interno Editor.'))

        location = self.env['microsoft.storage.location'].sudo().browse(int(raw_location)).exists()
        user = self.env['res.users'].sudo().browse(int(raw_user)).exists()
        if not location or not location.active or not location.drive_id:
            raise UserError(_('La ubicación SharePoint de evidencias es inválida o está inactiva.'))
        if location_id and location.id != location_id:
            raise UserError(_('La ubicación de la evidencia no coincide con la configuración SAT.'))
        if not user or not user.active or user.share:
            raise UserError(_('El usuario técnico de evidencias debe ser interno y activo.'))
        # DriveService exige un rol apropiado también para el usuario delegado.
        location.with_user(user).check_operation('upload', user)
        return EvidenciaMicrosoftService(location.with_user(user), user=user), location, user

    def _upload_values(self, values, ticket, momento):
        vals = dict(values)
        images = {name: vals.pop(name) for name in ('imagen_original', 'imagen_procesada') if name in vals}
        if not any(value not in (False, None, '') for value in images.values()):
            return vals, None, []
        if not ticket or not ticket.exists() or momento not in ('antes', 'despues'):
            raise UserError(_('La evidencia necesita un ticket válido y un momento ANTES o DESPUÉS.'))

        service, location, _user = self._storage_service()
        folder_id = service.ensure_ticket_folder(ticket, momento)
        uploaded = []
        vals['microsoft_location_id'] = location.id
        vals['microsoft_folder_id'] = folder_id
        try:
            for field_name, kind in (('imagen_original', 'original'),
                                     ('imagen_procesada', 'procesada')):
                raw = self._decode_image(images.get(field_name))
                if raw is None:
                    continue
                name = self._new_filename(raw, kind)
                info = service.upload_image(ticket, momento, raw, name,
                                            kind=kind, parent_id=folder_id)
                uploaded.append(info)
                vals[field_name + '_filename'] = info['name']
                vals['microsoft_%s_item_id' % kind] = info['item_id']
                vals['microsoft_%s_url' % kind] = info['web_url']
        except Exception:
            self._cleanup_uploaded(service, uploaded)
            raise
        return vals, service, uploaded

    @staticmethod
    def _cleanup_uploaded(service, uploaded):
        # La limpieza solo funciona si la identidad técnica tiene permiso delete.
        # No elevar privilegios del técnico ni ignorar fallos: dejar constancia
        # de archivos huérfanos para su posterior reconciliación administrativa.
        for entry in reversed(uploaded):
            try:
                service.drive.delete_item(entry['item_id'])
            except Exception:
                _logger.exception('[SAT][EVIDENCIA] Archivo remoto pendiente de limpieza: %s',
                                  entry.get('item_id'))

    @api.model_create_multi
    def create(self, vals_list):
        cleaned = []
        completed = []
        try:
            for values in vals_list:
                ticket = self.env['ticket.alquiler'].browse(values.get('ticket_id')).exists()
                moment = values.get('momento')
                vals, service, uploaded = self._upload_values(values, ticket, moment)
                if not vals.get('microsoft_original_item_id'):
                    raise UserError(_('Se requiere una fotografía original para crear la evidencia.'))
                cleaned.append(vals)
                if service and uploaded:
                    completed.append((service, uploaded))
            return super().create(cleaned)
        except Exception:
            for service, uploaded in completed:
                self._cleanup_uploaded(service, uploaded)
            raise

    def write(self, vals):
        if not any(name in vals for name in ('imagen_original', 'imagen_procesada')):
            return super().write(vals)
        for rec in self:
            clean, service, uploaded = rec._upload_values(
                vals, rec.ticket_id, vals.get('momento') or rec.momento)
            try:
                super(TicketEvidenciaFoto, rec).write(clean)
            except Exception:
                if service and uploaded:
                    self._cleanup_uploaded(service, uploaded)
                raise
        return True

    def _legacy_image(self, field_name):
        self.ensure_one()
        attachment = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', field_name),
        ], limit=1)
        return attachment.datas if attachment else False

    def _remote_image(self, item_id):
        self.ensure_one()
        if not item_id or not self.microsoft_location_id:
            return False
        service, _location, _user = self._storage_service(self.microsoft_location_id.id)
        url, item = service.drive.get_download_url(item_id)
        url = DriveService._validate_temporary_url(url)
        if item.get('size') and int(item['size']) > MAX_IMAGE_BYTES:
            raise UserError(_('La fotografía remota supera los 20 MB.'))
        content = bytearray()
        try:
            with requests.get(url, stream=True, timeout=(10, 45), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise UserError(_('Microsoft no permitió recuperar la fotografía.'))
                for chunk in response.iter_content(chunk_size=65536):
                    content.extend(chunk)
                    if len(content) > MAX_IMAGE_BYTES:
                        raise UserError(_('La fotografía remota supera los 20 MB.'))
        except requests.RequestException as error:
            raise UserError(_('No fue posible recuperar la evidencia desde Microsoft.')) from error
        return base64.b64encode(bytes(content))

    @api.depends('microsoft_original_item_id', 'microsoft_procesada_item_id')
    def _compute_remote_images(self):
        for rec in self:
            rec.imagen_original = (rec._remote_image(rec.microsoft_original_item_id)
                                   if rec.microsoft_original_item_id
                                   else rec._legacy_image('imagen_original'))
            rec.imagen_procesada = (rec._remote_image(rec.microsoft_procesada_item_id)
                                    if rec.microsoft_procesada_item_id
                                    else rec._legacy_image('imagen_procesada'))

    def action_abrir_en_maps(self):
        self.ensure_one()
        if not self.tiene_coordenadas:
            return False
        return {'type': 'ir.actions.act_url',
                'url': 'https://www.google.com/maps?q=%s,%s' % (self.latitud, self.longitud),
                'target': 'new'}

    def action_ver_foto(self):
        self.ensure_one()
        view = self.env.ref('sat.view_ticket_evidencia_foto_form_modal', raise_if_not_found=False)
        return {'type': 'ir.actions.act_window', 'name': 'Foto de evidencia',
                'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
                'views': [(view.id, 'form')] if view else [(False, 'form')],
                'target': 'new', 'context': {'form_view_initial_mode': 'readonly'}}

    def action_abrir_foto_original(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url',
                'url': '/web/image/ticket.evidencia.foto/%s/imagen_original' % self.id,
                'target': 'new'}

    def action_descargar_foto(self):
        self.ensure_one()
        filename = quote(self.imagen_original_filename or ('evidencia_%s.jpg' % self.id), safe='')
        return {'type': 'ir.actions.act_url',
                'url': '/web/content/ticket.evidencia.foto/%s/imagen_original/%s?download=true' %
                       (self.id, filename), 'target': 'self'}


class TicketAlquilerEvidencia(models.Model):
    _inherit = 'ticket.alquiler'

    evidencia_token = fields.Char(string='Token de evidencia', readonly=True,
                                   copy=False, index=True,
                                   help='Token único usado en la URL pública para subir fotos de evidencia')
    evidencia_foto_ids = fields.One2many('ticket.evidencia.foto', 'ticket_id',
                                         string='Fotos de evidencia')
    evidencia_foto_antes_ids = fields.One2many('ticket.evidencia.foto',
                                               compute='_compute_evidencia_foto_momento_ids', string='Fotos antes')
    evidencia_foto_despues_ids = fields.One2many('ticket.evidencia.foto',
                                                 compute='_compute_evidencia_foto_momento_ids', string='Fotos después')
    evidencia_antes_count = fields.Integer(string='Fotos antes', compute='_compute_evidencia_counts')
    evidencia_despues_count = fields.Integer(string='Fotos después', compute='_compute_evidencia_counts')

    @api.depends('evidencia_foto_ids', 'evidencia_foto_ids.momento')
    def _compute_evidencia_foto_momento_ids(self):
        for rec in self:
            rec.evidencia_foto_antes_ids = rec.evidencia_foto_ids.filtered(lambda f: f.momento == 'antes')
            rec.evidencia_foto_despues_ids = rec.evidencia_foto_ids.filtered(lambda f: f.momento == 'despues')

    @api.depends('evidencia_foto_ids', 'evidencia_foto_ids.momento')
    def _compute_evidencia_counts(self):
        for rec in self:
            rec.evidencia_antes_count = len(rec.evidencia_foto_ids.filtered(lambda f: f.momento == 'antes'))
            rec.evidencia_despues_count = len(rec.evidencia_foto_ids.filtered(lambda f: f.momento == 'despues'))

    @api.model
    def create(self, vals):
        record = super().create(vals)
        if not record.evidencia_token:
            record.evidencia_token = str(uuid.uuid4())
        return record

    def _ensure_evidencia_token(self):
        for rec in self:
            if not rec.evidencia_token:
                rec.evidencia_token = str(uuid.uuid4())

    def _get_evidencia_url(self):
        self.ensure_one()
        self._ensure_evidencia_token()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return '%s/evidencia/%s' % (base_url, self.evidencia_token)

    def action_copiar_link_evidencia(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Link de evidencia'), 'message': self._get_evidencia_url(),
                           'type': 'success', 'sticky': True}}

    def action_abrir_link_evidencia(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self._get_evidencia_url(), 'target': 'new'}

    def action_enviar_link_whatsapp_tecnico(self):
        self.ensure_one()
        if not self.responsable:
            raise UserError(_('No hay técnico responsable asignado para enviar el link.'))
        if not self.responsable_mobile_clean or self.responsable_mobile_clean == 'NA':
            raise UserError(_('El técnico responsable no tiene un número de celular válido.'))
        url = self._get_evidencia_url()
        mensaje = (
            f"Hola {self.responsable.name or 'técnico'},\n\n"
            f"Link para subir las fotos de evidencia del ticket {self.name}:\n\n"
            f"📸 {url}\n\nIndicaciones:\n"
            f"1. Abrir el link desde el celular.\n"
            f"2. Permitir ubicación/GPS cuando el navegador lo solicite.\n"
            f"3. Subir fotos en ANTES al llegar y DESPUÉS al finalizar."
        )
        self.send_whatsapp_message(self.responsable_mobile_clean, mensaje)
        self.message_post(body=_('📲 Link de evidencia enviado por WhatsApp al técnico %s') %
                          self.responsable.name, message_type='notification')
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('WhatsApp enviado'),
                           'message': _('Se envió el link de evidencia al técnico.'),
                           'type': 'success', 'sticky': False}}
