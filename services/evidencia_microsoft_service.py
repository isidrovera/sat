# -*- coding: utf-8 -*-
"""Servicio de almacenamiento de fotografías SAT en Microsoft 365.

Reutiliza DriveService del módulo odoo_onedrive_integration sin modificarlo.
No guarda archivos en ir.attachment ni cambia las rutas de Flutter.

La autorización sobre el ticket corresponde al modelo/controlador SAT. La
identidad técnica de este servicio debe contar con los permisos mínimos de
lectura, creación de carpetas y carga en la ubicación de evidencias.
"""

import logging
import re
from datetime import datetime

from odoo import fields, _
from odoo.exceptions import UserError

from odoo.addons.odoo_onedrive_integration.services.drive_service import DriveService

_logger = logging.getLogger(__name__)


class EvidenciaMicrosoftService:
    ROOT_PATH = ("SAT", "Evidencias")
    VALID_MOMENTS = {"antes": "ANTES", "despues": "DESPUES"}
    VALID_IMAGES = {".jpg", ".jpeg", ".png", ".webp"}
    MAX_NAME_LENGTH = 160
    MAX_IMAGE_BYTES = 20 * 1024 * 1024

    def __init__(self, location, user=None):
        location.ensure_one()
        if location._name != "microsoft.storage.location":
            raise UserError(_("La ubicación de Microsoft 365 no es válida."))
        if not location.active or not location.drive_id:
            raise UserError(_("Seleccione una biblioteca SharePoint activa con Drive ID."))

        self.location = location
        self.user = user or location.env.user
        # DriveService mantiene las comprobaciones de autorización por operación.
        self.drive = DriveService(location, user=self.user)

    @staticmethod
    def _safe_part(value, fallback):
        value = str(value or "").strip()
        value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", value)
        value = re.sub(r"\s+", " ", value).strip(" .")
        return value[:100].rstrip(" .") or fallback

    @classmethod
    def _safe_filename(cls, filename, default):
        filename = cls._safe_part(filename, default)
        if len(filename) > cls.MAX_NAME_LENGTH:
            stem, dot, ext = filename.rpartition(".")
            if dot:
                filename = stem[: cls.MAX_NAME_LENGTH - len(ext) - 1].rstrip(" .") + "." + ext
            else:
                filename = filename[:cls.MAX_NAME_LENGTH]
        extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in cls.VALID_IMAGES:
            raise UserError(_("La evidencia debe ser una imagen JPG, PNG o WebP."))
        return filename

    @classmethod
    def _ensure_image(cls, data, filename):
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise UserError(_("No se recibió una fotografía binaria válida."))
        data = bytes(data)
        if len(data) > cls.MAX_IMAGE_BYTES:
            raise UserError(_("La fotografía supera el límite de 20 MB."))
        if data.startswith(b"\xff\xd8\xff"):
            actual_ext = {".jpg", ".jpeg"}
        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
            actual_ext = {".png"}
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            actual_ext = {".webp"}
        else:
            raise UserError(_("El contenido no corresponde a una imagen admitida."))
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        if ext not in actual_ext:
            raise UserError(_("La extensión de la fotografía no coincide con su contenido."))
        return data

    def _find_folder(self, parent_id, folder_name):
        listing = self.drive.list_children(parent_id) if parent_id else self.drive.list_root()
        for item in listing.get("value") or []:
            if (item.get("name") == folder_name
                    and isinstance(item.get("folder"), dict)
                    and item.get("id")):
                return item["id"]
        return False

    def _ensure_folder(self, parent_id, folder_name):
        folder_name = self._safe_part(folder_name, "Carpeta")
        existing = self._find_folder(parent_id, folder_name)
        if existing:
            return existing

        # DriveService utiliza conflictBehavior=rename. Si hay una carrera,
        # comprobamos de nuevo la carpeta con el nombre esperado.
        created = self.drive.create_folder(folder_name, parent_id)
        if not isinstance(created, dict) or not created.get("id"):
            raise UserError(_("Microsoft no confirmó la creación de la carpeta %s.") % folder_name)
        if created.get("name") == folder_name and isinstance(created.get("folder"), dict):
            return created["id"]

        existing = self._find_folder(parent_id, folder_name)
        if existing:
            _logger.warning(
                "[SAT][EVIDENCIA] Carpeta duplicada por concurrencia: parent=%s "
                "solicitada=%s creada=%s; se reutiliza=%s",
                parent_id, folder_name, created.get("id"), existing,
            )
            return existing
        raise UserError(_("Microsoft creó una carpeta con un nombre inesperado; revise la biblioteca."))

    def ensure_ticket_folder(self, ticket, momento):
        """Devuelve el ID de SAT/Evidencias/AÑO/Ticket-ID/ANTES|DESPUES."""
        ticket.ensure_one()
        if ticket._name != "ticket.alquiler" or not ticket.id:
            raise UserError(_("La evidencia requiere un ticket SAT guardado."))
        if momento not in self.VALID_MOMENTS:
            raise UserError(_("El momento de la evidencia debe ser ANTES o DESPUÉS."))

        capture_date = fields.Datetime.to_datetime(fields.Datetime.now())
        year = str(capture_date.year if isinstance(capture_date, datetime)
                   else datetime.utcnow().year)
        segments = (
            *self.ROOT_PATH,
            year,
            "Ticket-%s" % ticket.id,
            self.VALID_MOMENTS[momento],
        )
        parent_id = None
        for segment in segments:
            parent_id = self._ensure_folder(parent_id, segment)
        return parent_id

    def upload_image(self, ticket, momento, image_data, filename, *,
                     kind="original", parent_id=None):
        """Sube una fotografía; devuelve referencias Graph, no crea adjuntos."""
        ticket.ensure_one()
        if kind not in ("original", "procesada"):
            raise UserError(_("Tipo de fotografía no reconocido."))
        if momento not in self.VALID_MOMENTS:
            raise UserError(_("Momento de evidencia inválido."))

        safe_name = self._safe_filename(filename, "%s.jpg" % kind)
        content = self._ensure_image(image_data, safe_name)
        folder_id = parent_id or self.ensure_ticket_folder(ticket, momento)
        result = self.drive.upload_file(safe_name, content, parent_id=folder_id)
        if not isinstance(result, dict) or not result.get("id"):
            raise UserError(_("Microsoft no confirmó la subida de la fotografía."))

        _logger.info(
            "[SAT][EVIDENCIA][MICROSOFT] Subida confirmada "
            "ticket_id=%s momento=%s tipo=%s item_id=%s tamaño=%s",
            ticket.id, momento, kind, result["id"], len(content),
        )
        return {
            "item_id": result["id"],
            "drive_id": self.location.drive_id,
            "folder_id": folder_id,
            "name": result.get("name") or safe_name,
            "web_url": result.get("webUrl") or False,
            "size": result.get("size") or len(content),
        }

    def upload_evidence(self, ticket, momento, *, original, original_filename,
                        procesada=None, procesada_filename=None):
        """Sube original y procesada, con intento de compensación ante fallo.

        El borrado de compensación depende de permisos Microsoft. Si no se puede
        borrar, el archivo huérfano se registra en logs para reconciliación.
        """
        folder_id = self.ensure_ticket_folder(ticket, momento)
        uploaded = []
        try:
            original_info = self.upload_image(
                ticket, momento, original, original_filename,
                kind="original", parent_id=folder_id,
            )
            uploaded.append(original_info)
            processed_info = False
            if procesada is not None:
                processed_info = self.upload_image(
                    ticket, momento, procesada,
                    procesada_filename or "procesada.jpg",
                    kind="procesada", parent_id=folder_id,
                )
                uploaded.append(processed_info)
            return {
                "folder_id": folder_id,
                "original": original_info,
                "procesada": processed_info,
            }
        except Exception:
            for entry in reversed(uploaded):
                try:
                    self.drive.delete_item(entry["item_id"])
                except Exception:
                    _logger.exception(
                        "[SAT][EVIDENCIA] Archivo remoto pendiente de limpieza "
                        "ticket_id=%s item_id=%s", ticket.id, entry["item_id"],
                    )
            raise
