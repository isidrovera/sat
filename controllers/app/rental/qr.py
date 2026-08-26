# -*- coding: utf-8 -*-

"""
Código QR para Flutter - módulo Alquiler.

Endpoints:
    GET  /api/app/rentals/<id>/qr
    POST /api/app/rentals/<id>/qr/generate
    GET  /api/app/rentals/<id>/qr/image
    GET  /api/app/rentals/<id>/qr/target
    GET  /api/app/rentals/<id>/qr/download-info

Objetivos:
- consultar el QR actual del equipo;
- generar/regenerar el QR usando `alquiler.generate_qr_code()`;
- obtener una URL segura de imagen usando `get_qr_image_url()`;
- devolver la URL objetivo codificada dentro del QR;
- entregar la imagen binaria directamente a Flutter cuando se requiera;
- no duplicar la generación QR en el controlador;
- no manipular attachments manualmente desde Flutter.

LÓGICA REAL DEL MODELO
======================
El modelo `alquiler` ya contiene:

    qr_image = fields.Binary(..., attachment=True)
    qr_image_filename
    generate_qr_code()
    get_qr_image_url()
    _get_qr_download_name()
    limpiar_attachments_qr_huerfanos()

El QR generado apunta a:

    {web.base.url}/api/escanear_qr?id_registro=<alquiler.id>

Este controlador reutiliza esos métodos.

SEGURIDAD
=========
- Solo usuarios autorizados del módulo Alquiler pueden consultar el QR.
- Generar/regenerar exige permiso de escritura.
- No se expone una ruta arbitraria de attachments.
- La imagen se lee exclusivamente desde el campo `qr_image` del registro
  que el usuario ya tiene permitido consultar.
- La limpieza global de attachments huérfanos NO se expone por API Flutter,
  porque es una tarea administrativa global y no una acción de equipo.
"""

import base64
import logging
import re

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .base import RentalBaseController


_logger = logging.getLogger(__name__)


class RentalQrController(RentalBaseController):

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/rentals/<int:rental_id>/qr",
            "/api/app/rentals/<int:rental_id>/qr/generate",
            "/api/app/rentals/<int:rental_id>/qr/image",
            "/api/app/rentals/<int:rental_id>/qr/target",
            "/api/app/rentals/<int:rental_id>/qr/download-info",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def rental_qr_options(
        self,
        rental_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # HELPERS
    # ============================================================

    def _json_body(self):
        try:
            data = request.httprequest.get_json(
                silent=True
            )

            if isinstance(
                data,
                dict,
            ):
                return data
        except Exception:
            pass

        return {}

    def _truthy(
        self,
        value,
    ):
        if value is True:
            return True

        if value in (
            None,
            False,
            "",
        ):
            return False

        return (
            str(
                value
            )
            .strip()
            .lower()
            in (
                "1",
                "true",
                "yes",
                "si",
                "sí",
                "on",
                "confirm",
                "confirmed",
            )
        )

    # ============================================================
    # TARGET URL
    # ============================================================

    def _qr_target_url(
        self,
        rental,
    ):
        base_url = request.env[
            "ir.config_parameter"
        ].sudo().get_param(
            "web.base.url"
        )

        if not base_url:
            return False

        return (
            "%s/api/escanear_qr?id_registro=%s"
            % (
                base_url.rstrip(
                    "/"
                ),
                rental.id,
            )
        )

    # ============================================================
    # FILENAME
    # ============================================================

    def _fallback_filename(
        self,
        rental,
    ):
        serie = self._safe_string(
            rental,
            "serie",
        )

        if serie:
            clean = re.sub(
                r"[^\w\-_\.]",
                "_",
                serie,
            )

            return (
                "qr_code_%s_%s.png"
                % (
                    clean,
                    rental.id,
                )
            )

        return (
            "qr_code_%s.png"
            % rental.id
        )

    def _qr_filename(
        self,
        rental,
    ):
        method = getattr(
            rental,
            "_get_qr_download_name",
            None,
        )

        if callable(
            method
        ):
            try:
                value = method()

                if value:
                    return str(
                        value
                    )
            except Exception:
                _logger.exception(
                    (
                        "No se pudo obtener nombre de descarga QR "
                        "para alquiler %s."
                    ),
                    rental.id,
                )

        filename = self._safe_string(
            rental,
            "qr_image_filename",
        )

        if filename:
            return filename

        return self._fallback_filename(
            rental
        )

    # ============================================================
    # IMAGE URL
    # ============================================================

    def _qr_image_url(
        self,
        rental,
    ):
        if not self._field(
            rental,
            "qr_image",
            False,
        ):
            return False

        method = getattr(
            rental,
            "get_qr_image_url",
            None,
        )

        if callable(
            method
        ):
            try:
                return method() or False
            except Exception:
                _logger.exception(
                    (
                        "No se pudo obtener get_qr_image_url "
                        "para alquiler %s."
                    ),
                    rental.id,
                )

        # Fallback equivalente a la ruta estándar de web/image.
        base_url = request.env[
            "ir.config_parameter"
        ].sudo().get_param(
            "web.base.url"
        )

        if not base_url:
            return False

        return (
            "%s/web/image/alquiler/%s/qr_image/%s"
            % (
                base_url.rstrip(
                    "/"
                ),
                rental.id,
                self._qr_filename(
                    rental
                ),
            )
        )

    # ============================================================
    # BINARY
    # ============================================================

    def _qr_bytes(
        self,
        rental,
    ):
        raw = self._field(
            rental,
            "qr_image",
            False,
        )

        if not raw:
            return False

        try:
            if isinstance(
                raw,
                str,
            ):
                raw = raw.encode(
                    "ascii"
                )

            return base64.b64decode(
                raw,
                validate=False,
            )
        except Exception as exc:
            _logger.exception(
                "No se pudo decodificar QR alquiler %s.",
                rental.id,
            )

            raise UserError(
                "La imagen QR almacenada no es válida."
            ) from exc

    # ============================================================
    # PERMISSIONS
    # ============================================================

    def _qr_actions(
        self,
        rental,
        user,
    ):
        can_write = bool(
            self._is_system_user(
                user
            )
            or self._rental_model_access(
                user
            )["write"]
        )

        has_qr = bool(
            self._field(
                rental,
                "qr_image",
                False,
            )
        )

        return {
            "generate": bool(
                can_write
                and self._method_exists(
                    rental,
                    "generate_qr_code",
                )
            ),
            "regenerate": bool(
                can_write
                and has_qr
                and self._method_exists(
                    rental,
                    "generate_qr_code",
                )
            ),
            "view_image": has_qr,
            "download_image": has_qr,
            "open_target": bool(
                self._qr_target_url(
                    rental
                )
            ),
        }

    # ============================================================
    # PAYLOAD
    # ============================================================

    def _qr_payload(
        self,
        rental,
        user,
    ):
        base = self._serialize_rental_qr(
            rental
        )

        has_qr = bool(
            self._field(
                rental,
                "qr_image",
                False,
            )
        )

        base.update(
            {
                "available": has_qr,
                "filename": self._qr_filename(
                    rental
                ),
                "image_url": self._qr_image_url(
                    rental
                ),
                "target_url": self._qr_target_url(
                    rental
                ),
                "mime_type": (
                    "image/png"
                    if has_qr
                    else False
                ),
                "actions": self._qr_actions(
                    rental,
                    user,
                ),
            }
        )

        # Compatibilidad con el serializer base anterior.
        base[
            "url"
        ] = base.get(
            "image_url"
        )

        return base

    # ============================================================
    # GET QR
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/qr",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_qr_get(
        self,
        rental_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
            )

            if not rental:
                return self._rental_not_found_response()

            return self._json_response(
                {
                    "success": True,
                    "qr": self._qr_payload(
                        rental,
                        user,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando QR alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # GENERATE / REGENERATE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/qr/generate",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_qr_generate(
        self,
        rental_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
                require_write=True,
            )

            if not rental:
                return self._rental_not_found_response()

            write_error = (
                self._require_rental_write_access(
                    rental,
                    user,
                )
            )

            if write_error:
                return write_error

            if not self._method_exists(
                rental,
                "generate_qr_code",
            ):
                raise UserError(
                    "La generación de QR no está disponible."
                )

            data = self._json_body()

            already_exists = bool(
                self._field(
                    rental,
                    "qr_image",
                    False,
                )
            )

            # Primera generación no necesita confirmación.
            # Regenerar reemplaza la imagen existente, por eso sí.
            if (
                already_exists
                and not self._truthy(
                    data.get(
                        "confirmed"
                    )
                )
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "CONFIRMATION_REQUIRED",
                        "message": (
                            "El equipo ya tiene un QR generado. "
                            "¿Desea regenerarlo?"
                        ),
                        "requires_confirmation": True,
                        "qr": self._qr_payload(
                            rental,
                            user,
                        ),
                    },
                    status=409,
                )

            previous_filename = (
                self._qr_filename(
                    rental
                )
                if already_exists
                else False
            )

            result = rental.generate_qr_code()

            rental.invalidate_recordset()

            if not self._field(
                rental,
                "qr_image",
                False,
            ):
                raise UserError(
                    "El método de generación terminó sin "
                    "almacenar una imagen QR."
                )

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s %s el código QR "
                    "del equipo."
                    % (
                        user.name,
                        (
                            "regeneró"
                            if already_exists
                            else "generó"
                        ),
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Código QR regenerado correctamente."
                        if already_exists
                        else "Código QR generado correctamente."
                    ),
                    "regenerated": already_exists,
                    "previous_filename": previous_filename,
                    "model_result": bool(
                        result
                    ),
                    "qr": self._qr_payload(
                        rental,
                        user,
                    ),
                    "rental": (
                        self._serialize_rental_detail(
                            rental,
                            user,
                        )
                    ),
                },
                status=200,
            )

        except (
            UserError,
            ValidationError,
            AccessError,
        ) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_QR_GENERATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error generando QR alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # RAW IMAGE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/qr/image",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_qr_image(
        self,
        rental_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
            )

            if not rental:
                return self._rental_not_found_response()

            image = self._qr_bytes(
                rental
            )

            if not image:
                return self._json_response(
                    {
                        "success": False,
                        "code": "RENTAL_QR_NOT_GENERATED",
                        "message": (
                            "El equipo todavía no tiene "
                            "un código QR generado."
                        ),
                    },
                    status=404,
                )

            filename = self._qr_filename(
                rental
            )

            # inline por defecto para que Flutter/Web pueda mostrarlo.
            # download=1 fuerza Content-Disposition attachment.
            download = self._truthy(
                self._query_arg(
                    "download",
                    False,
                )
            )

            disposition = (
                "attachment"
                if download
                else "inline"
            )

            response = request.make_response(
                image,
                headers=[
                    (
                        "Content-Type",
                        "image/png",
                    ),
                    (
                        "Content-Length",
                        str(
                            len(
                                image
                            )
                        ),
                    ),
                    (
                        "Content-Disposition",
                        '%s; filename="%s"'
                        % (
                            disposition,
                            filename.replace(
                                '"',
                                "",
                            ),
                        ),
                    ),
                    (
                        "Cache-Control",
                        "private, max-age=300",
                    ),
                    (
                        "X-Content-Type-Options",
                        "nosniff",
                    ),
                ],
            )

            return response

        except (
            UserError,
            ValidationError,
            AccessError,
        ) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_QR_IMAGE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error entregando imagen QR alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # TARGET URL
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/qr/target",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_qr_target(
        self,
        rental_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
            )

            if not rental:
                return self._rental_not_found_response()

            target = self._qr_target_url(
                rental
            )

            if not target:
                return self._json_response(
                    {
                        "success": False,
                        "code": "WEB_BASE_URL_MISSING",
                        "message": (
                            "No está configurada web.base.url."
                        ),
                    },
                    status=500,
                )

            return self._json_response(
                {
                    "success": True,
                    "target_url": target,
                    "equipment": {
                        "id": rental.id,
                        "serial": self._safe_string(
                            rental,
                            "serie",
                        ),
                        "model": self._safe_many2one(
                            rental,
                            "name",
                        ),
                    },
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error obteniendo target QR alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # DOWNLOAD INFO
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/qr/download-info",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_qr_download_info(
        self,
        rental_id,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            rental = self._get_rental(
                rental_id,
                user,
            )

            if not rental:
                return self._rental_not_found_response()

            has_qr = bool(
                self._field(
                    rental,
                    "qr_image",
                    False,
                )
            )

            if not has_qr:
                return self._json_response(
                    {
                        "success": False,
                        "code": "RENTAL_QR_NOT_GENERATED",
                        "message": (
                            "El equipo todavía no tiene "
                            "un código QR generado."
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "download": {
                        "filename": self._qr_filename(
                            rental
                        ),
                        "mime_type": "image/png",
                        "image_url": self._qr_image_url(
                            rental
                        ),
                        "api_image_path": (
                            "/api/app/rentals/%s/qr/image?download=1"
                            % rental.id
                        ),
                    },
                    "qr": self._qr_payload(
                        rental,
                        user,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error download info QR alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )
