
# -*- coding: utf-8 -*-
"""Servicio SharePoint para Biblioteca de Compatibilidades SAT.

Reutiliza DriveService de odoo_onedrive_integration.

No modifica evidencias ni firmas existentes.
No crea archivos en ir.attachment.
No establece un límite fijo de peso para fotografías.

Los límites efectivos de transferencia dependen de Odoo,
del proxy HTTP, del servidor y de Microsoft Graph.
"""

import logging
import re
import uuid

from odoo import _
from odoo.exceptions import UserError

from odoo.addons.odoo_onedrive_integration.services.drive_service import DriveService


_logger = logging.getLogger(__name__)


class RepuestoMicrosoftService:

    ROOT_PATH = (
        'SAT',
        'Biblioteca Repuestos',
    )

    VALID_IMAGES = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
    }

    MAX_NAME_LENGTH = 160

    # =========================================================
    # INICIALIZACIÓN
    # =========================================================

    def __init__(self, location, user=None):

        location.ensure_one()

        if location._name != 'microsoft.storage.location':
            raise UserError(
                _('La ubicación de Microsoft 365 no es válida.')
            )

        if not location.active or not location.drive_id:
            raise UserError(
                _(
                    'Seleccione una biblioteca SharePoint activa '
                    'con Drive ID.'
                )
            )

        self.location = location
        self.user = user or location.env.user

        self.drive = DriveService(
            location,
            user=self.user,
        )

        _logger.info(
            '[BIBLIOTECA][SHAREPOINT][INIT] '
            'Servicio inicializado location_id=%s '
            'drive_id=%s user_id=%s',
            location.id,
            location.drive_id,
            self.user.id,
        )

    # =========================================================
    # NORMALIZACIÓN DE NOMBRES
    # =========================================================

    @staticmethod
    def _safe_name(value, fallback='foto'):

        value = str(value or '').strip()

        value = re.sub(
            r'[\\/:*?"<>|\x00-\x1f]+',
            '-',
            value,
        )

        value = re.sub(
            r'\s+',
            ' ',
            value,
        )

        value = value.strip(' .')

        return value or fallback

    @classmethod
    def _safe_filename(cls, filename):

        filename = cls._safe_name(
            filename,
            'fotografia.jpg',
        )

        stem, dot, extension = filename.rpartition('.')

        if not dot:
            raise UserError(
                _('La fotografía debe tener una extensión válida.')
            )

        extension = '.' + extension.lower()

        if extension not in cls.VALID_IMAGES:
            raise UserError(
                _(
                    'Formato no permitido. '
                    'Utilice JPG, JPEG, PNG o WebP.'
                )
            )

        max_stem_length = (
            cls.MAX_NAME_LENGTH - len(extension)
        )

        stem = stem[:max_stem_length].rstrip(' .')

        if not stem:
            stem = 'fotografia'

        return stem + extension

    # =========================================================
    # VALIDACIÓN DE IMÁGENES
    # =========================================================

    @classmethod
    def validate_image(cls, data, filename):
        """Valida el tipo de imagen sin imponer límite de peso."""

        if not isinstance(data, (bytes, bytearray)):
            raise UserError(
                _('No se recibió una fotografía binaria válida.')
            )

        if not data:
            raise UserError(
                _('La fotografía está vacía.')
            )

        content = bytes(data)

        safe_name = cls._safe_filename(filename)

        extension = (
            '.' + safe_name.rsplit('.', 1)[-1].lower()
        )

        header = content[:12]

        if header.startswith(b'\xff\xd8\xff'):
            detected_mime = 'image/jpeg'

        elif header.startswith(b'\x89PNG\r\n\x1a\n'):
            detected_mime = 'image/png'

        elif (
            header.startswith(b'RIFF')
            and header[8:12] == b'WEBP'
        ):
            detected_mime = 'image/webp'

        else:
            raise UserError(
                _(
                    'El contenido del archivo no corresponde '
                    'a una imagen JPG, PNG o WebP válida.'
                )
            )

        expected_mime = cls.VALID_IMAGES[extension]

        if expected_mime != detected_mime:
            raise UserError(
                _(
                    'La extensión de la fotografía '
                    'no coincide con su contenido.'
                )
            )

        _logger.debug(
            '[BIBLIOTECA][SHAREPOINT][VALIDATE] '
            'Archivo validado nombre=%s mime=%s bytes=%s',
            safe_name,
            detected_mime,
            len(content),
        )

        return content, safe_name, detected_mime

    # =========================================================
    # BÚSQUEDA DE CARPETAS
    # =========================================================

    def _find_folder(self, parent_id, folder_name):

        if parent_id:
            listing = self.drive.list_children(
                parent_id
            )
        else:
            listing = self.drive.list_root()

        if not isinstance(listing, dict):
            raise UserError(
                _('SharePoint devolvió una respuesta no válida.')
            )

        for item in listing.get('value') or []:

            if (
                item.get('name') == folder_name
                and isinstance(item.get('folder'), dict)
                and item.get('id')
            ):
                return item['id']

        return False

    # =========================================================
    # CREACIÓN DE CARPETAS
    # =========================================================

    def _ensure_folder(self, parent_id, folder_name):

        folder_name = self._safe_name(
            folder_name,
            'Carpeta',
        )

        existing = self._find_folder(
            parent_id,
            folder_name,
        )

        if existing:

            _logger.debug(
                '[BIBLIOTECA][SHAREPOINT][FOLDER] '
                'Carpeta existente nombre=%s id=%s',
                folder_name,
                existing,
            )

            return existing

        _logger.info(
            '[BIBLIOTECA][SHAREPOINT][FOLDER] '
            'Creando carpeta nombre=%s parent_id=%s',
            folder_name,
            parent_id,
        )

        created = self.drive.create_folder(
            folder_name,
            parent_id,
        )

        if (
            not isinstance(created, dict)
            or not created.get('id')
        ):
            raise UserError(
                _(
                    'Microsoft no confirmó la creación '
                    'de la carpeta %s.'
                ) % folder_name
            )

        if (
            created.get('name') == folder_name
            and isinstance(created.get('folder'), dict)
        ):

            _logger.info(
                '[BIBLIOTECA][SHAREPOINT][FOLDER] '
                'Carpeta creada nombre=%s id=%s',
                folder_name,
                created['id'],
            )

            return created['id']

        existing = self._find_folder(
            parent_id,
            folder_name,
        )

        if existing:

            _logger.warning(
                '[BIBLIOTECA][SHAREPOINT][FOLDER] '
                'Posible creación concurrente '
                'nombre=%s creada=%s reutilizada=%s',
                folder_name,
                created.get('id'),
                existing,
            )

            return existing

        raise UserError(
            _(
                'SharePoint creó una carpeta con un nombre '
                'inesperado. Revise la biblioteca.'
            )
        )

    # =========================================================
    # CARPETA DE REFERENCIA
    # =========================================================

    def ensure_folder(self, compatibilidad):
        """Crea SAT/Biblioteca Repuestos/Referencia-ID."""

        compatibilidad.ensure_one()

        if (
            compatibilidad._name != 'sat.repuesto.compatibilidad'
            or not compatibilidad.id
        ):
            raise UserError(
                _(
                    'Primero debe guardar una ficha '
                    'de compatibilidad válida.'
                )
            )

        segments = (
            *self.ROOT_PATH,
            'Referencia-%s' % compatibilidad.id,
        )

        parent_id = None

        for segment in segments:

            parent_id = self._ensure_folder(
                parent_id,
                segment,
            )

        _logger.info(
            '[BIBLIOTECA][SHAREPOINT][FOLDER] '
            'Carpeta referencia_id=%s folder_id=%s',
            compatibilidad.id,
            parent_id,
        )

        return parent_id

    # =========================================================
    # GENERACIÓN DE NOMBRE ÚNICO
    # =========================================================

    @classmethod
    def _unique_filename(cls, filename):

        filename = cls._safe_filename(filename)

        stem, extension = filename.rsplit('.', 1)

        identifier = uuid.uuid4().hex[:12]

        suffix = '-%s.%s' % (
            identifier,
            extension,
        )

        allowed_length = (
            cls.MAX_NAME_LENGTH - len(suffix)
        )

        stem = stem[:allowed_length].rstrip(' .')

        return (stem or 'fotografia') + suffix

    # =========================================================
    # SUBIDA DE FOTOGRAFÍA
    # =========================================================

    def upload(self, compatibilidad, data, filename):
        """Sube la fotografía directamente a SharePoint.

        No crea registros ir.attachment.

        Devuelve metadatos para registrar en sat.repuesto.foto.
        """

        compatibilidad.ensure_one()

        if compatibilidad._name != 'sat.repuesto.compatibilidad':
            raise UserError(
                _('El registro de compatibilidad no es válido.')
            )

        if not compatibilidad.id:
            raise UserError(
                _('Guarde la ficha antes de agregar fotografías.')
            )

        content, safe_name, mime_type = (
            self.validate_image(
                data,
                filename,
            )
        )

        folder_id = self.ensure_folder(
            compatibilidad
        )

        unique_name = self._unique_filename(
            safe_name
        )

        _logger.info(
            '[BIBLIOTECA][SHAREPOINT][UPLOAD] '
            'Iniciando subida '
            'referencia_id=%s '
            'archivo=%s '
            'bytes=%s '
            'folder_id=%s',
            compatibilidad.id,
            unique_name,
            len(content),
            folder_id,
        )

        try:

            result = self.drive.upload_file(
                unique_name,
                content,
                parent_id=folder_id,
            )

        except Exception:

            _logger.exception(
                '[BIBLIOTECA][SHAREPOINT][UPLOAD] '
                'Error subiendo fotografía '
                'referencia_id=%s archivo=%s',
                compatibilidad.id,
                unique_name,
            )

            raise

        if (
            not isinstance(result, dict)
            or not result.get('id')
        ):

            _logger.error(
                '[BIBLIOTECA][SHAREPOINT][UPLOAD] '
                'Respuesta inválida referencia_id=%s',
                compatibilidad.id,
            )

            raise UserError(
                _(
                    'Microsoft SharePoint no confirmó '
                    'la subida de la fotografía.'
                )
            )

        item_id = result['id']

        _logger.info(
            '[BIBLIOTECA][SHAREPOINT][UPLOAD] '
            'Fotografía subida correctamente '
            'referencia_id=%s '
            'item_id=%s '
            'drive_id=%s '
            'archivo=%s '
            'bytes=%s',
            compatibilidad.id,
            item_id,
            self.location.drive_id,
            result.get('name') or unique_name,
            len(content),
        )

        return {
            'item_id': item_id,
            'drive_id': self.location.drive_id,
            'folder_id': folder_id,
            'name': result.get('name') or unique_name,
            'web_url': result.get('webUrl') or False,
            'mime_type': mime_type,
            'size': result.get('size') or len(content),
        }
