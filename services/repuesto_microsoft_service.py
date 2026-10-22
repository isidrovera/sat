# -*- coding: utf-8 -*-
"""Almacenamiento de archivos de la Biblioteca SAT en SharePoint.

Reutiliza DriveService; no crea ir.attachment y no modifica evidencias SAT.
"""
import logging
import mimetypes
import re
import uuid
from pathlib import PurePath

from odoo import _
from odoo.exceptions import UserError
from odoo.addons.odoo_onedrive_integration.services.drive_service import DriveService

_logger = logging.getLogger(__name__)


class RepuestoMicrosoftService:
    ROOT_PATH = ('SAT', 'Biblioteca Repuestos')
    MAX_NAME_LENGTH = 160
    # No se fija límite de bytes. Los límites reales dependen del servidor,
    # de Odoo y del mecanismo de carga de DriveService / Microsoft Graph.
    DANGEROUS_EXTENSIONS = {
        '.exe', '.dll', '.bat', '.cmd', '.com', '.msi', '.msp',
        '.ps1', '.psm1', '.vbs', '.vbe', '.js', '.jse', '.wsf',
        '.wsh', '.scr', '.pif', '.hta', '.jar', '.sh', '.php',
        '.py', '.pl', '.rb', '.reg', '.lnk', '.iso', '.img',
    }

    def __init__(self, location, user=None):
        location.ensure_one()
        if location._name != 'microsoft.storage.location':
            raise UserError(_('La ubicación de Microsoft 365 no es válida.'))
        if not location.active or not location.drive_id:
            raise UserError(_('Seleccione una biblioteca SharePoint activa con Drive ID.'))
        self.location = location
        self.user = user or location.env.user
        self.drive = DriveService(location, user=self.user)

    @classmethod
    def _safe_filename(cls, filename):
        filename = str(filename or '').replace('\\', '/').split('/')[-1]
        filename = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '-', filename)
        filename = re.sub(r'\s+', ' ', filename).strip(' .')
        if not filename or '.' not in filename:
            raise UserError(_('Seleccione un archivo con nombre y extensión válidos.'))
        stem, dot, extension = filename.rpartition('.')
        extension = '.' + extension.lower()
        if not stem.strip(' .') or not re.fullmatch(r'\.[a-z0-9]{1,15}', extension):
            raise UserError(_('La extensión del archivo no es válida.'))
        if extension in cls.DANGEROUS_EXTENSIONS:
            raise UserError(_('Este tipo de archivo ejecutable no está permitido.'))
        # Rechazar dobles extensiones que encubran un ejecutable.
        if any(part.lower() in cls.DANGEROUS_EXTENSIONS for part in PurePath(stem).suffixes):
            raise UserError(_('El nombre contiene una extensión ejecutable no permitida.'))
        available = cls.MAX_NAME_LENGTH - len(extension)
        return stem[:available].rstrip(' .') + extension

    @classmethod
    def validate_file(cls, data, filename):
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise UserError(_('No se recibió un archivo binario válido.'))
        safe = cls._safe_filename(filename)
        content = bytes(data)
        guessed = mimetypes.guess_type(safe)[0] or 'application/octet-stream'
        ext = '.' + safe.rsplit('.', 1)[-1].lower()
        # Confirmar cabeceras cuando la firma es reconocible. No convertir
        # una comprobación superficial en garantía de seguridad del archivo.
        signature_mime = None
        if content.startswith(b'\xff\xd8\xff'):
            signature_mime = 'image/jpeg'
        elif content.startswith(b'\x89PNG\r\n\x1a\n'):
            signature_mime = 'image/png'
        elif content.startswith(b'RIFF') and content[8:12] == b'WEBP':
            signature_mime = 'image/webp'
        elif content.startswith(b'%PDF-'):
            signature_mime = 'application/pdf'
        expected = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.webp': 'image/webp',
            '.pdf': 'application/pdf',
        }.get(ext)
        if expected and signature_mime != expected:
            raise UserError(_('El contenido no coincide con el tipo de archivo indicado.'))
        return content, safe, expected or guessed

    def _find_folder(self, parent_id, name):
        listing = self.drive.list_children(parent_id) if parent_id else self.drive.list_root()
        if not isinstance(listing, dict):
            raise UserError(_('SharePoint devolvió una respuesta de carpetas inválida.'))
        for item in listing.get('value') or []:
            if (item.get('name') == name and isinstance(item.get('folder'), dict)
                    and item.get('id')):
                return item['id']
        return False

    def _ensure_folder(self, parent_id, name):
        existing = self._find_folder(parent_id, name)
        if existing:
            return existing
        created = self.drive.create_folder(name, parent_id)
        if not isinstance(created, dict) or not created.get('id'):
            raise UserError(_('SharePoint no confirmó la carpeta %s.') % name)
        if created.get('name') == name and isinstance(created.get('folder'), dict):
            return created['id']
        existing = self._find_folder(parent_id, name)
        if existing:
            return existing
        raise UserError(_('SharePoint creó una carpeta con nombre inesperado.'))

    def ensure_folder(self, compatibilidad):
        compatibilidad.ensure_one()
        if compatibilidad._name != 'sat.repuesto.compatibilidad' or not compatibilidad.id:
            raise UserError(_('Guarde primero una ficha de compatibilidad válida.'))
        parent_id = None
        for name in (*self.ROOT_PATH, 'Referencia-%s' % compatibilidad.id):
            parent_id = self._ensure_folder(parent_id, name)
        return parent_id

    def upload(self, compatibilidad, data, filename):
        compatibilidad.ensure_one()
        content, safe_name, mime_type = self.validate_file(data, filename)
        folder_id = self.ensure_folder(compatibilidad)
        stem, extension = safe_name.rsplit('.', 1)
        suffix = '-' + uuid.uuid4().hex[:12]
        allowed = self.MAX_NAME_LENGTH - len(suffix) - len(extension) - 1
        unique_name = stem[:allowed].rstrip(' .') + suffix + '.' + extension
        _logger.info(
            '[BIBLIOTECA][SHAREPOINT][UPLOAD] Inicio ficha=%s archivo=%s bytes=%s',
            compatibilidad.id, unique_name, len(content),
        )
        try:
            result = self.drive.upload_file(unique_name, content, parent_id=folder_id)
        except Exception:
            _logger.exception(
                '[BIBLIOTECA][SHAREPOINT][UPLOAD] Error ficha=%s archivo=%s',
                compatibilidad.id, unique_name,
            )
            raise
        if not isinstance(result, dict) or not result.get('id'):
            raise UserError(_('SharePoint no confirmó la subida del archivo.'))
        _logger.info(
            '[BIBLIOTECA][SHAREPOINT][UPLOAD] OK ficha=%s item=%s bytes=%s',
            compatibilidad.id, result['id'], len(content),
        )
        return {
            'item_id': result['id'],
            'drive_id': self.location.drive_id,
            'folder_id': folder_id,
            'name': result.get('name') or unique_name,
            'web_url': result.get('webUrl') or False,
            'mime_type': mime_type,
            'size': result.get('size') or len(content),
        }
