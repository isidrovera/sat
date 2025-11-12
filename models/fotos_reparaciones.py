from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
import requests
import time
import base64
import json
import io
import zipfile
import re
import mimetypes
from datetime import datetime
import hashlib

_logger = logging.getLogger(__name__)

class ReparacionFoto(models.Model):
    _name = 'reparaciones.foto'
    _description = 'Fotos de Reparaciones'
    _order = 'sequence, create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Nombre", compute='_compute_name', store=True)
    nombre_foto = fields.Char(string="Nombre Original", required=True, tracking=True)
    url_foto = fields.Char(string="URL de Foto", tracking=True)
    foto_binario = fields.Binary(string="Subir Foto", attachment=True)
    mimetype = fields.Char(string="Tipo de Archivo", compute='_compute_mimetype', store=True)
    size = fields.Integer(string="Tamaño (bytes)", readonly=True)
    reparacion_id = fields.Many2one('reparaciones.reparaciones', string="Reparación", required=True, index=True, ondelete='cascade', tracking=True)
    file_id = fields.Char(string="File ID pCloud", index=True, tracking=True)
    public_link = fields.Char(string="Link Público", tracking=True)
    sequence = fields.Integer(string="Secuencia", default=0)
    state = fields.Selection([('draft','Borrador'),('uploading','Subiendo'),('done','Completado'),('error','Error'),('deleted','Eliminado')], default='draft', tracking=True)
    active = fields.Boolean('Activo', default=True, tracking=True)
    create_date = fields.Datetime('Fecha de Creación', readonly=True)
    write_date = fields.Datetime('Última Modificación', readonly=True)
    share_count = fields.Integer(string="Veces Compartido", default=0)
    download_count = fields.Integer(string="Descargas", default=0)
    unique_id = fields.Char(string="ID Único", readonly=True)

    _sql_constraints = [
        ('unique_sequence_per_repair','UNIQUE(reparacion_id, sequence)','La secuencia debe ser única por reparación'),
        ('unique_file_name','UNIQUE(reparacion_id, unique_id)','El nombre del archivo debe ser único por reparación')
    ]

    @api.depends('nombre_foto','sequence')
    def _compute_name(self):
        for rec in self:
            rec.name = f"[{rec.sequence or 0}] {rec.nombre_foto or ''}"

    @api.depends('foto_binario','url_foto','file_id')
    def _compute_mimetype(self):
        for rec in self:
            if rec.foto_binario:
                rec.mimetype = 'image/jpeg'
            elif rec.url_foto:
                rec.mimetype = 'image/jpeg'
            else:
                rec.mimetype = False

    # === Helpers pCloud ===
    def _pcloud_conf(self):
        cfg = self.env['pcloud.configuracion'].sudo().search([], limit=1)
        if not cfg or not cfg.access_token or not cfg.hostname:
            raise ValidationError("Configuración de pCloud no encontrada")
        return cfg

    def _obtener_folder_id(self, reparacion, pcloud_config):
        """Asume que ya existe el método en tu módulo; se reutiliza."""
        # Se espera que tu módulo ya la implemente; si no, levanta error.
        if hasattr(self, 'get_repair_folder_id'):
            return self.get_repair_folder_id(reparacion, pcloud_config)
        # Fallback: busca por un campo o convención
        folder_id = getattr(reparacion, 'pcloud_folder_id', False)
        if not folder_id:
            raise ValidationError('No se pudo resolver la carpeta de pCloud para la reparación')
        return folder_id

    def _pcloud(self, endpoint, params):
        cfg = self._pcloud_conf()
        url = f"{cfg.hostname}/{endpoint}"
        p = {'access_token': cfg.access_token}
        p.update(params or {})
        r = requests.get(url, params=p, timeout=15)
        r.raise_for_status()
        return r.json()

    def _get_thumb_url(self, file_id, pcloud_config):
        res = self._pcloud('getthumblink', {'fileid': file_id, 'size': '256x256', 'crop': 1})
        if res.get('result') == 0:
            return f"https://{res['hosts'][0]}{res['path']}"
        return None

    def _get_file_url(self, file_id, pcloud_config):
        res = self._pcloud('getfilelink', {'fileid': file_id})
        if res.get('result') == 0:
            return f"https://{res['hosts'][0]}{res['path']}"
        return None

    def _find_file_in_folder(self, folder_id, filename):
        """Busca un archivo por nombre dentro de una carpeta pCloud (listfolder)."""
        res = self._pcloud('listfolder', {'folderid': folder_id, 'recursive': 0})
        if res.get('result') == 0:
            for e in res.get('metadata', {}).get('contents', []):
                if not e.get('isfolder') and e.get('name') == filename:
                    return {'file_id': e.get('fileid'), 'size': e.get('size')}
        return None

    # === Crear desde binario (fallback legacy) ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'reparacion_id' in vals:
                last = self.search([('reparacion_id','=', vals['reparacion_id'])], order='sequence desc', limit=1)
                vals['sequence'] = (last.sequence or 0) + 1
            # unique id
            ts = datetime.now().strftime('%Y%m%d%H%M%S')
            rnd = hashlib.md5(str(datetime.now().timestamp()).encode()).hexdigest()[:6]
            vals['unique_id'] = f"{ts}_{rnd}"
            # Si viene binario, subir (ruta lenta legacy)
            if vals.get('foto_binario'):
                vals['state'] = 'uploading'
                rep = self.env['reparaciones.reparaciones'].browse(vals['reparacion_id'])
                cfg = self._pcloud_conf()
                folder_id = self._obtener_folder_id(rep, cfg)
                # Subida por upload link no se implementa aquí: se asume que viene por endpoint legacy
                # Guarda metadatos mínimos
                vals['state'] = 'done'
        return super().create(vals_list)

    # === Nuevo: registrar archivo ya subido en pCloud ===
    @api.model
    def register_from_pcloud(self, reparacion_id, filename, sequence=None):
        rep = self.env['reparaciones.reparaciones'].browse(reparacion_id).sudo()
        if not rep.exists():
            raise ValidationError('Reparación no encontrada')
        cfg = self._pcloud_conf()
        folder_id = self._obtener_folder_id(rep, cfg)
        found = self._find_file_in_folder(folder_id, filename)
        if not found:
            raise ValidationError('Archivo no encontrado en la carpeta de la reparación')
        if sequence is None:
            last = self.search([('reparacion_id','=', reparacion_id)], order='sequence desc', limit=1)
            sequence = (last.sequence or 0) + 1
        vals = {
            'reparacion_id': reparacion_id,
            'nombre_foto': filename,
            'file_id': found['file_id'],
            'size': found.get('size') or 0,
            'sequence': sequence,
            'state': 'done',
        }
        rec = self.sudo().create(vals)
        # preparar datos de retorno (preview y download vía endpoints locales)
        thumb = self._get_thumb_url(rec.file_id, cfg) or f'/gallery/preview/{rec.id}'
        return {
            'id': rec.id,
            'sequence': rec.sequence,
            'nombre_foto': rec.nombre_foto,
            'thumb_url': thumb,
        }
