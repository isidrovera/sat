
# -*- coding: utf-8 -*-
"""Previsualización autenticada de medios SharePoint de Biblioteca SAT.

Usa exclusivamente los métodos reales de DriveService:
- get_thumbnail_url(item_id, size)
- get_download_url(item_id)

Los archivos siguen almacenados en SharePoint,
no en ir.attachment.
"""

import logging

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from werkzeug.exceptions import (
    Forbidden,
    NotFound,
    ServiceUnavailable,
)
from werkzeug.utils import redirect

from odoo.addons.odoo_onedrive_integration.services.drive_service import DriveService


_logger = logging.getLogger(__name__)


class SatRepuestoMediaController(http.Controller):

    @http.route(
        '/sat/repuestos/media/<int:foto_id>',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def show_media(self, foto_id, **kwargs):
        """Obtiene una miniatura o descarga temporal autorizada.

        Comprueba permisos de Odoo y Microsoft 365 antes
        de redirigir al archivo almacenado en SharePoint.
        """

        foto = request.env[
            'sat.repuesto.foto'
        ].browse(foto_id).exists()

        if not foto or not foto.compatibilidad_id.exists():
            raise NotFound()

        # =====================================================
        # PERMISOS DEL REGISTRO
        # =====================================================

        try:
            foto.check_access('read')
            foto.compatibilidad_id.check_access('read')

        except AccessError:
            raise Forbidden()

        # =====================================================
        # IDENTIFICAR TIPO DE ARCHIVO
        # =====================================================

        mime = (
            (foto.mime_type or '')
            .split(';', 1)[0]
            .strip()
            .lower()
        )

        es_imagen = (
            mime.startswith('image/')
            and mime != 'image/svg+xml'
        )

        es_video = mime.startswith('video/')
        es_pdf = mime == 'application/pdf'

        if not (es_imagen or es_video or es_pdf):
            raise NotFound()

        if (
            not foto.sharepoint_drive_id
            or not foto.sharepoint_item_id
        ):
            raise NotFound()

        # =====================================================
        # UBICACIÓN SHAREPOINT
        # =====================================================

        location = request.env[
            'microsoft.storage.location'
        ].search(
            [
                ('active', '=', True),
                (
                    'drive_id',
                    '=',
                    foto.sharepoint_drive_id,
                ),
            ],
            limit=1,
        )

        if not location:

            _logger.warning(
                '[BIBLIOTECA][MEDIA] '
                'Sin ubicación accesible '
                'foto_id=%s drive_id=%s',
                foto.id,
                foto.sharepoint_drive_id,
            )

            raise Forbidden()

        # =====================================================
        # TAMAÑO DE MINIATURA
        # =====================================================

        size = kwargs.get('size', 'medium')

        if size not in (
            'small',
            'medium',
            'large',
        ):
            size = 'medium'

        # =====================================================
        # OBTENER ARCHIVO DESDE MICROSOFT
        # =====================================================

        try:

            drive = DriveService(
                location,
                user=request.env.user,
            )

            url = None
            es_miniatura = False

            # Intentar miniatura para imágenes.

            if es_imagen:

                try:

                    url = drive.get_thumbnail_url(
                        foto.sharepoint_item_id,
                        size=size,
                    )

                    es_miniatura = bool(url)

                except AccessError:
                    raise

                except (UserError, ValueError):

                    _logger.info(
                        '[BIBLIOTECA][MEDIA] '
                        'Miniatura no disponible '
                        'foto_id=%s. '
                        'Intentando descarga temporal.',
                        foto.id,
                    )

            # Si no hay miniatura, usar la URL temporal.

            if not url:

                url, item = drive.get_download_url(
                    foto.sharepoint_item_id
                )

                if (
                    not isinstance(item, dict)
                    or item.get('folder') is not None
                ):
                    raise NotFound()

            # =================================================
            # RESPUESTA HTTP
            # =================================================

            _logger.debug(
                '[BIBLIOTECA][MEDIA] '
                'Archivo autorizado '
                'foto_id=%s usuario=%s '
                'mime=%s miniatura=%s',
                foto.id,
                request.env.user.id,
                mime,
                es_miniatura,
            )

            response = redirect(
                url,
                code=302,
            )

            response.headers[
                'Cache-Control'
            ] = 'private, no-store'

            response.headers[
                'Referrer-Policy'
            ] = 'no-referrer'

            response.headers[
                'X-Content-Type-Options'
            ] = 'nosniff'

            return response

        # =====================================================
        # CONTROL DE ERRORES
        # =====================================================

        except AccessError:

            _logger.warning(
                '[BIBLIOTECA][MEDIA] '
                'Acceso denegado '
                'foto_id=%s usuario=%s',
                foto.id,
                request.env.user.id,
            )

            raise Forbidden()

        except NotFound:
            raise

        except (UserError, ValueError):

            _logger.exception(
                '[BIBLIOTECA][MEDIA] '
                'SharePoint no entregó el archivo '
                'foto_id=%s',
                foto.id,
            )

            raise ServiceUnavailable(
                'No se pudo obtener la vista previa de SharePoint.'
            )
