# -*- coding: utf-8 -*-

"""
Detalle / edición general de la API Flutter del módulo Alquiler.

Endpoints:
    GET   /api/app/rentals/<id>
    PATCH /api/app/rentals/<id>
    POST  /api/app/rentals/<id>

Responsabilidades:
- devolver detalle completo;
- editar campos generales permitidos;
- soportar autoguardado desde Flutter;
- validar Many2one;
- normalizar fechas/números/textos;
- devolver siempre la máquina actualizada;
- no ejecutar cambios de estado ni acciones especiales.

Los cambios de estado pertenecen a state.py.
Las acciones de mantenimiento pertenecen a maintenance.py.
Las acciones de geolocalización pertenecen a geo.py.
Las acciones de bloqueo pertenecen a blocking.py.
"""

import logging

from odoo import fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .base import RentalBaseController


_logger = logging.getLogger(__name__)


class RentalDetailController(RentalBaseController):

    # ============================================================
    # CAMPOS EDITABLES
    # ============================================================

    """
    No se permite write arbitrario.

    Cada campo que Flutter pueda modificar debe estar listado aquí.
    Esto evita que un cliente manipulado intente escribir campos
    técnicos o de seguridad que no corresponden al formulario.
    """

    EDITABLE_FIELDS = {
        # Cliente / instalación
        "cliente_id",
        "direccion",
        "contacto_id",
        "celular",
        "correo_",
        "cargo",
        "ubicacion_instalacion",
        "ubicacion_id",
        "observaciones",

        # Equipo / operación
        "tipo_maquina_id",
        "contador_bn",
        "contador_color",
        "contador_scan",

        # Compra / venta
        "precio_venta",
        "precio_compra",
        "factura_compra",
        "fecha_compra",
        "factura_venta",
        "fecha_venta",
        "contometro_venta",
        "garantia",

        # PrintTracker / red
        "pt_entity_id",
        "pt_device_id",
        "mac_address",
        "ip_address",
        "custom_location",
        "asset_id",
        "is_managed",

        # Instalación
        "estado_instalacion",
        "ubicacion_instalacion",
        "notas_adecuacion",

        # Mantenimiento - configuración simple
        "control_mantenimiento",
        "fecha_inicio",
        "intervalo_meses",
        "patron_recurrencia",
        "semana_mes",
        "dia_semana",
        "motivo_reprogramacion",

        # Planificador - configuración
        "zona_mantenimiento_id",
        "tecnico_mantenimiento_id",
        "fecha_programada_mantenimiento",
        "hora_programada_mantenimiento",
        "duracion_mantenimiento_horas",
        "cantidad_tecnicos_mantenimiento",
        "ignorar_zona_mantenimiento",

        # Geo - datos manuales
        "direccion_calle",
        "direccion_referencia",
        "nombre_establecimiento",
        "distrito",
        "provincia",
        "departamento",
        "codigo_postal",
        "pais",
        "latitud",
        "longitud",
        "google_place_id",
        "ubicacion_manual",

        # Bloqueo - datos auxiliares
        "motivo_bloqueo",
        "acceso_remoto_disponible",
        "ip_equipo",
        "asesor_ventas_id",
        "soporte_tecnico_id",
        "observaciones_bloqueo",
        "grupo_notificaciones_id",
        "grupo_asesor_ventas_id",
    }

    # Campos reservados únicamente al administrador.
    SYSTEM_ONLY_FIELDS = {
        "precio_compra",
        "factura_compra",
        "fecha_compra",
        "precio_venta",
        "factura_venta",
        "fecha_venta",
        "contometro_venta",
        "garantia",
        "pt_entity_id",
        "pt_device_id",
        "asset_id",
        "is_managed",
    }

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/rentals/<int:rental_id>",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def rental_detail_options(
        self,
        rental_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # JSON BODY
    # ============================================================

    def _json_body(self):
        """
        Reutiliza parser del AppBaseController si existe.
        Si no, intenta leer JSON directamente.
        """
        parser = getattr(
            self,
            "_get_json_data",
            None,
        )

        if callable(
            parser
        ):
            try:
                data = parser()
                if isinstance(
                    data,
                    dict,
                ):
                    return data
            except Exception:
                pass

        parser = getattr(
            self,
            "_json_data",
            None,
        )

        if callable(
            parser
        ):
            try:
                data = parser()
                if isinstance(
                    data,
                    dict,
                ):
                    return data
            except Exception:
                pass

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

    # ============================================================
    # FIELD META
    # ============================================================

    def _field_type(
        self,
        rental,
        field_name,
    ):
        field = rental._fields.get(
            field_name
        )

        if not field:
            return False

        return getattr(
            field,
            "type",
            False,
        )

    # ============================================================
    # NORMALIZERS
    # ============================================================

    def _normalize_boolean(
        self,
        value,
    ):
        if isinstance(
            value,
            bool,
        ):
            return value

        if value in (
            None,
            False,
            "",
        ):
            return False

        text = str(
            value
        ).strip().lower()

        return text in (
            "1",
            "true",
            "yes",
            "si",
            "sí",
            "on",
        )

    def _normalize_integer(
        self,
        value,
        *,
        allow_false=True,
    ):
        if value in (
            None,
            "",
            False,
        ):
            return (
                False
                if allow_false
                else 0
            )

        try:
            return int(
                value
            )
        except Exception:
            raise UserError(
                "Se recibió un valor entero inválido."
            )

    def _normalize_float(
        self,
        value,
        *,
        allow_false=True,
    ):
        if value in (
            None,
            "",
            False,
        ):
            return (
                False
                if allow_false
                else 0.0
            )

        try:
            return float(
                value
            )
        except Exception:
            raise UserError(
                "Se recibió un valor numérico inválido."
            )

    def _normalize_date(
        self,
        value,
    ):
        if value in (
            None,
            "",
            False,
        ):
            return False

        try:
            return fields.Date.to_date(
                value
            )
        except Exception:
            raise UserError(
                "Se recibió una fecha inválida."
            )

    def _normalize_datetime(
        self,
        value,
    ):
        if value in (
            None,
            "",
            False,
        ):
            return False

        try:
            return fields.Datetime.to_datetime(
                value
            )
        except Exception:
            raise UserError(
                "Se recibió una fecha/hora inválida."
            )

    def _normalize_many2one(
        self,
        rental,
        field_name,
        value,
    ):
        if value in (
            None,
            "",
            False,
            0,
            "0",
        ):
            return False

        try:
            record_id = int(
                value
            )
        except Exception:
            raise UserError(
                "El identificador recibido para %s no es válido."
                % field_name
            )

        field = rental._fields.get(
            field_name
        )

        if not field:
            raise UserError(
                "El campo %s no existe."
                % field_name
            )

        comodel_name = getattr(
            field,
            "comodel_name",
            False,
        )

        if not comodel_name:
            return record_id

        related = request.env[
            comodel_name
        ].browse(
            record_id
        ).exists()

        if not related:
            raise UserError(
                "El registro seleccionado para %s no existe."
                % field_name
            )

        # Fuerza ACL/read record rules con usuario real.
        try:
            if hasattr(
                related,
                "check_access",
            ):
                related.check_access(
                    "read"
                )
        except AccessError:
            raise UserError(
                "No tienes acceso al registro seleccionado para %s."
                % field_name
            )

        return related.id

    def _normalize_selection(
        self,
        rental,
        field_name,
        value,
    ):
        if value in (
            None,
            "",
            False,
        ):
            return False

        valid_values = {
            item["value"]
            for item in self._selection_options_safe(
                rental,
                field_name,
            )
        }

        if valid_values and value not in valid_values:
            raise UserError(
                "El valor '%s' no es válido para %s."
                % (
                    value,
                    field_name,
                )
            )

        return value

    def _normalize_text(
        self,
        value,
    ):
        if value in (
            None,
            False,
        ):
            return False

        return str(
            value
        )

    # ============================================================
    # NORMALIZE FIELD
    # ============================================================

    def _normalize_field_value(
        self,
        rental,
        field_name,
        value,
    ):
        field_type = self._field_type(
            rental,
            field_name,
        )

        if field_type == "many2one":
            return self._normalize_many2one(
                rental,
                field_name,
                value,
            )

        if field_type == "selection":
            return self._normalize_selection(
                rental,
                field_name,
                value,
            )

        if field_type == "boolean":
            return self._normalize_boolean(
                value
            )

        if field_type == "integer":
            return self._normalize_integer(
                value
            )

        if field_type in (
            "float",
            "monetary",
        ):
            return self._normalize_float(
                value
            )

        if field_type == "date":
            return self._normalize_date(
                value
            )

        if field_type == "datetime":
            return self._normalize_datetime(
                value
            )

        if field_type in (
            "char",
            "text",
            "html",
        ):
            return self._normalize_text(
                value
            )

        # Para tipos no contemplados explícitamente.
        return value

    # ============================================================
    # PER-FIELD BUSINESS VALIDATIONS
    # ============================================================

    def _validate_write_values(
        self,
        rental,
        user,
        values,
    ):
        """
        Reglas de negocio ligeras del formulario general.

        Las acciones de estado y procesos complejos NO se validan aquí.
        """
        if not values:
            return

        # Contadores nunca negativos.
        for name in (
            "contador_bn",
            "contador_color",
            "contador_scan",
            "contometro_venta",
        ):
            if (
                name in values
                and values[name] not in (
                    False,
                    None,
                )
                and values[name] < 0
            ):
                raise UserError(
                    "Los contadores no pueden ser negativos."
                )

        # Duración y cantidad de técnicos.
        if (
            "duracion_mantenimiento_horas"
            in values
            and values[
                "duracion_mantenimiento_horas"
            ] not in (
                False,
                None,
            )
            and values[
                "duracion_mantenimiento_horas"
            ] <= 0
        ):
            raise UserError(
                "La duración del mantenimiento debe ser mayor a 0."
            )

        if (
            "cantidad_tecnicos_mantenimiento"
            in values
            and values[
                "cantidad_tecnicos_mantenimiento"
            ] not in (
                False,
                None,
            )
            and values[
                "cantidad_tecnicos_mantenimiento"
            ] <= 0
        ):
            raise UserError(
                "La cantidad de técnicos debe ser mayor a 0."
            )

        # Coordenadas.
        if (
            "latitud"
            in values
            and values[
                "latitud"
            ] not in (
                False,
                None,
            )
        ):
            latitude = values[
                "latitud"
            ]

            if not (
                -90
                <= latitude
                <= 90
            ):
                raise UserError(
                    "La latitud debe estar entre -90 y 90."
                )

        if (
            "longitud"
            in values
            and values[
                "longitud"
            ] not in (
                False,
                None,
            )
        ):
            longitude = values[
                "longitud"
            ]

            if not (
                -180
                <= longitude
                <= 180
            ):
                raise UserError(
                    "La longitud debe estar entre -180 y 180."
                )

        # Si se marca alquilada por otra ruta, la vista exige datos
        # de ubicación/contacto. El cambio de estado normal irá por
        # state.py, pero mantenemos esta validación defensiva.
        future_state = values.get(
            "estado_alquiler_id",
            self._safe_string(
                rental,
                "estado_alquiler_id",
            ),
        )

        if future_state == "alquilada":
            prospective = {
                "direccion": values.get(
                    "direccion",
                    self._field(
                        rental,
                        "direccion",
                        False,
                    ),
                ),
                "contacto_id": values.get(
                    "contacto_id",
                    self._field(
                        rental,
                        "contacto_id",
                        False,
                    ),
                ),
                "celular": values.get(
                    "celular",
                    self._field(
                        rental,
                        "celular",
                        False,
                    ),
                ),
                "correo_": values.get(
                    "correo_",
                    self._field(
                        rental,
                        "correo_",
                        False,
                    ),
                ),
            }

            missing = [
                key
                for key, value
                in prospective.items()
                if not value
            ]

            if missing:
                raise UserError(
                    "Para una máquina alquilada deben estar completos "
                    "dirección, contacto, celular y correo."
                )

    # ============================================================
    # BUILD WRITE VALUES
    # ============================================================

    def _prepare_write_values(
        self,
        rental,
        user,
        data,
    ):
        if not isinstance(
            data,
            dict,
        ):
            return {}

        values = {}

        for field_name, raw_value in data.items():
            if field_name not in self.EDITABLE_FIELDS:
                continue

            if field_name not in rental._fields:
                continue

            if (
                field_name in self.SYSTEM_ONLY_FIELDS
                and not self._is_system_user(
                    user
                )
            ):
                raise UserError(
                    "El campo '%s' solo puede modificarlo el administrador."
                    % field_name
                )

            values[
                field_name
            ] = self._normalize_field_value(
                rental,
                field_name,
                raw_value,
            )

        self._validate_write_values(
            rental,
            user,
            values,
        )

        return values

    # ============================================================
    # FIELD PERMISSIONS FOR FLUTTER
    # ============================================================

    def _field_permissions(
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

        result = {}

        for field_name in sorted(
            self.EDITABLE_FIELDS
        ):
            if field_name not in rental._fields:
                continue

            editable = can_write

            reason = False

            if (
                field_name in self.SYSTEM_ONLY_FIELDS
                and not self._is_system_user(
                    user
                )
            ):
                editable = False
                reason = "system_only"

            result[
                field_name
            ] = {
                "editable": editable,
                "reason": reason,
                "type": self._field_type(
                    rental,
                    field_name,
                ),
            }

        return result

    # ============================================================
    # DETAIL
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_detail(
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
                    "rental": (
                        self._serialize_rental_detail(
                            rental,
                            user,
                        )
                    ),
                    "field_permissions": (
                        self._field_permissions(
                            rental,
                            user,
                        )
                    ),
                    "options": (
                        self._serialize_rental_options()
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando detalle alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # UPDATE / AUTOSAVE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>",
        type="http",
        auth="public",
        methods=[
            "PATCH",
            "POST",
        ],
        csrf=False,
        save_session=True,
    )
    def rental_update(
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

            data = self._json_body()

            if (
                "values"
                in data
                and isinstance(
                    data["values"],
                    dict,
                )
            ):
                data = data[
                    "values"
                ]

            values = self._prepare_write_values(
                rental,
                user,
                data,
            )

            if not values:
                return self._json_response(
                    {
                        "success": True,
                        "message": (
                            "No se recibieron cambios válidos."
                        ),
                        "rental": (
                            self._serialize_rental_detail(
                                rental,
                                user,
                            )
                        ),
                        "field_permissions": (
                            self._field_permissions(
                                rental,
                                user,
                            )
                        ),
                    }
                )

            before_write_date = self._safe_date_field(
                rental,
                "write_date",
            )

            rental.write(
                values
            )

            # Releer después de writes/computes/onchange server-side.
            rental.invalidate_recordset()

            changed_fields = sorted(
                values.keys()
            )

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: se actualizaron "
                    "los campos %s por %s."
                    % (
                        ", ".join(
                            changed_fields
                        ),
                        user.name,
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Cambios guardados correctamente."
                    ),
                    "changed_fields": changed_fields,
                    "previous_write_date": before_write_date,
                    "rental": (
                        self._serialize_rental_detail(
                            rental,
                            user,
                        )
                    ),
                    "field_permissions": (
                        self._field_permissions(
                            rental,
                            user,
                        )
                    ),
                }
            )

        except (
            UserError,
            ValidationError,
            AccessError,
        ) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_UPDATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error actualizando alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )
