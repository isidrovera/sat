# -*- coding: utf-8 -*-

"""
Geolocalización para Flutter - módulo Alquiler.

Endpoints:
    GET   /api/app/rentals/<id>/geo
    PATCH /api/app/rentals/<id>/geo

    POST  /api/app/rentals/<id>/geo/geocode
    POST  /api/app/rentals/<id>/geo/reverse-geocode
    POST  /api/app/rentals/<id>/geo/place
    POST  /api/app/rentals/<id>/geo/manual-coordinates
    GET   /api/app/rentals/<id>/geo/maps-url

Objetivos:
- editar los campos geográficos del equipo;
- utilizar los métodos reales del modelo `alquiler`;
- geocodificar dirección -> coordenadas;
- reverse geocoding -> dirección;
- aplicar un Place seleccionado;
- aplicar coordenadas marcadas manualmente;
- devolver URL de Google Maps sin depender de ir.actions.act_url;
- NO exponer la API Key de Google Maps a Flutter.

Métodos reales confirmados en `alquiler`:
    action_geocodificar_direccion()
    action_geocodificar_inverso()
    action_abrir_en_google_maps()
    action_aplicar_place_data(place_data)
    action_aplicar_coordenadas_manuales(lat, lng)

La API Key continúa almacenada y utilizada en Odoo mediante:
    alquiler_geo.google_maps_api_key

No existe endpoint Flutter para obtener dicha clave.
"""

import logging
from urllib.parse import quote

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .base import RentalBaseController


_logger = logging.getLogger(__name__)


class RentalGeoController(RentalBaseController):

    # ============================================================
    # CAMPOS
    # ============================================================

    GEO_EDITABLE_FIELDS = (
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
    )

    # google_place_id y ubicacion_manual no se editan directamente
    # por PATCH. Los actualizan los métodos específicos del modelo.

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/rentals/<int:rental_id>/geo",
            "/api/app/rentals/<int:rental_id>/geo/geocode",
            "/api/app/rentals/<int:rental_id>/geo/reverse-geocode",
            "/api/app/rentals/<int:rental_id>/geo/place",
            "/api/app/rentals/<int:rental_id>/geo/manual-coordinates",
            "/api/app/rentals/<int:rental_id>/geo/maps-url",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def rental_geo_options(
        self,
        rental_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # JSON
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

    # ============================================================
    # NORMALIZADORES
    # ============================================================

    def _normalize_text(
        self,
        value,
        *,
        max_length=None,
    ):
        if value in (
            None,
            False,
        ):
            return False

        text = str(
            value
        ).strip()

        if not text:
            return False

        if (
            max_length
            and len(
                text
            ) > max_length
        ):
            text = text[
                :max_length
            ]

        return text

    def _normalize_coordinate(
        self,
        value,
        *,
        coordinate,
    ):
        if value in (
            None,
            "",
            False,
        ):
            return False

        try:
            number = float(
                value
            )
        except Exception:
            raise UserError(
                "%s debe ser un número válido."
                % (
                    "La latitud"
                    if coordinate == "lat"
                    else "La longitud"
                )
            )

        if coordinate == "lat":
            if not (
                -90.0
                <= number
                <= 90.0
            ):
                raise UserError(
                    "La latitud debe estar entre -90 y 90."
                )

        elif coordinate == "lng":
            if not (
                -180.0
                <= number
                <= 180.0
            ):
                raise UserError(
                    "La longitud debe estar entre -180 y 180."
                )

        return number

    # ============================================================
    # PATCH VALUES
    # ============================================================

    def _prepare_geo_values(
        self,
        rental,
        data,
    ):
        if not isinstance(
            data,
            dict,
        ):
            return {}

        values = {}

        text_fields = (
            "direccion_calle",
            "direccion_referencia",
            "nombre_establecimiento",
            "distrito",
            "provincia",
            "departamento",
            "codigo_postal",
            "pais",
        )

        for field_name in text_fields:
            if (
                field_name in data
                and field_name in rental._fields
            ):
                values[
                    field_name
                ] = self._normalize_text(
                    data.get(
                        field_name
                    ),
                    max_length=500,
                )

        if (
            "latitud" in data
            and "latitud"
            in rental._fields
        ):
            values[
                "latitud"
            ] = self._normalize_coordinate(
                data.get(
                    "latitud"
                ),
                coordinate="lat",
            )

        if (
            "longitud" in data
            and "longitud"
            in rental._fields
        ):
            values[
                "longitud"
            ] = self._normalize_coordinate(
                data.get(
                    "longitud"
                ),
                coordinate="lng",
            )

        return values

    # ============================================================
    # MAPS URL
    # ============================================================

    def _maps_url(
        self,
        rental,
    ):
        latitude = self._safe_float(
            rental,
            "latitud",
        )

        longitude = self._safe_float(
            rental,
            "longitud",
        )

        if (
            latitude
            and longitude
        ):
            return (
                "https://www.google.com/maps?q=%s,%s"
                % (
                    latitude,
                    longitude,
                )
            )

        address = (
            self._safe_string(
                rental,
                "direccion_completa",
            )
            or self._safe_string(
                rental,
                "direccion_calle",
            )
            or self._safe_string(
                rental,
                "direccion",
            )
        )

        if address:
            return (
                "https://www.google.com/maps/search/?api=1&query=%s"
                % quote(
                    address
                )
            )

        return False

    # ============================================================
    # ACTIONS
    # ============================================================

    def _geo_actions(
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

        has_coordinates = bool(
            self._safe_bool(
                rental,
                "tiene_coordenadas",
            )
        )

        if not self._field_exists(
            rental,
            "tiene_coordenadas",
        ):
            has_coordinates = bool(
                self._safe_float(
                    rental,
                    "latitud",
                )
                and self._safe_float(
                    rental,
                    "longitud",
                )
            )

        has_address = bool(
            self._safe_string(
                rental,
                "direccion_completa",
            )
            or self._safe_string(
                rental,
                "direccion_calle",
            )
            or self._safe_string(
                rental,
                "direccion",
            )
        )

        return {
            "edit": can_write,
            "geocode": bool(
                can_write
                and has_address
                and self._method_exists(
                    rental,
                    "action_geocodificar_direccion",
                )
            ),
            "reverse_geocode": bool(
                can_write
                and has_coordinates
                and self._method_exists(
                    rental,
                    "action_geocodificar_inverso",
                )
            ),
            "apply_place": bool(
                can_write
                and self._method_exists(
                    rental,
                    "action_aplicar_place_data",
                )
            ),
            "manual_coordinates": bool(
                can_write
                and self._method_exists(
                    rental,
                    "action_aplicar_coordenadas_manuales",
                )
            ),
            "open_maps": bool(
                has_coordinates
                or has_address
            ),
        }

    # ============================================================
    # PAYLOAD
    # ============================================================

    def _geo_payload(
        self,
        rental,
        user,
    ):
        geo = self._serialize_rental_geo(
            rental
        )

        geo[
            "maps_url"
        ] = self._maps_url(
            rental
        )

        geo[
            "actions"
        ] = self._geo_actions(
            rental,
            user,
        )

        # Información explícita para Flutter:
        # la clave no se entrega desde esta API.
        geo[
            "google_maps"
        ] = {
            "server_geocoding": bool(
                self._method_exists(
                    rental,
                    "action_geocodificar_direccion",
                )
                and self._method_exists(
                    rental,
                    "action_geocodificar_inverso",
                )
            ),
            "api_key_exposed": False,
            "place_data_supported": self._method_exists(
                rental,
                "action_aplicar_place_data",
            ),
            "manual_pin_supported": self._method_exists(
                rental,
                "action_aplicar_coordenadas_manuales",
            ),
        }

        return geo

    # ============================================================
    # GET
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/geo",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_geo_get(
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
                    "geo": self._geo_payload(
                        rental,
                        user,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando geo alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # PATCH MANUAL FIELDS
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/geo",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def rental_geo_update(
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
                    data[
                        "values"
                    ],
                    dict,
                )
            ):
                data = data[
                    "values"
                ]

            values = self._prepare_geo_values(
                rental,
                data,
            )

            if not values:
                return self._json_response(
                    {
                        "success": True,
                        "message": (
                            "No se recibieron cambios de ubicación."
                        ),
                        "geo": self._geo_payload(
                            rental,
                            user,
                        ),
                    }
                )

            coordinate_changed = bool(
                "latitud" in values
                or "longitud" in values
            )

            if coordinate_changed:
                # Si la modificación es manual, ambas coordenadas deben
                # estar presentes o ya existir en el registro.
                latitude = values.get(
                    "latitud",
                    self._safe_float(
                        rental,
                        "latitud",
                    ),
                )

                longitude = values.get(
                    "longitud",
                    self._safe_float(
                        rental,
                        "longitud",
                    ),
                )

                if bool(
                    latitude
                ) != bool(
                    longitude
                ):
                    raise UserError(
                        "Debe registrar latitud y longitud juntas."
                    )

            rental.write(
                values
            )

            if (
                coordinate_changed
                and "ubicacion_manual"
                in rental._fields
            ):
                rental.write(
                    {
                        "ubicacion_manual": True,
                    }
                )

            rental.invalidate_recordset()

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s actualizó "
                    "los datos de ubicación (%s)."
                    % (
                        user.name,
                        ", ".join(
                            sorted(
                                values.keys()
                            )
                        ),
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Ubicación actualizada."
                    ),
                    "changed_fields": sorted(
                        values.keys()
                    ),
                    "geo": self._geo_payload(
                        rental,
                        user,
                    ),
                    "rental": (
                        self._serialize_rental_detail(
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
                    "code": "RENTAL_GEO_UPDATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error actualizando geo alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # GEOCODE ADDRESS
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/geo/geocode",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_geo_geocode(
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
                "action_geocodificar_direccion",
            ):
                raise UserError(
                    "La geocodificación por dirección "
                    "no está disponible."
                )

            address = (
                self._safe_string(
                    rental,
                    "direccion_completa",
                )
                or self._safe_string(
                    rental,
                    "direccion_calle",
                )
                or self._safe_string(
                    rental,
                    "direccion",
                )
            )

            if not address:
                raise UserError(
                    "No hay una dirección para geocodificar."
                )

            rental.action_geocodificar_direccion()

            rental.invalidate_recordset()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Dirección geocodificada correctamente."
                    ),
                    "geo": self._geo_payload(
                        rental,
                        user,
                    ),
                    "rental": (
                        self._serialize_rental_detail(
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
                    "code": "RENTAL_GEO_GEOCODE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error geocodificando alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # REVERSE GEOCODE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/geo/reverse-geocode",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_geo_reverse_geocode(
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
                "action_geocodificar_inverso",
            ):
                raise UserError(
                    "La geocodificación inversa no está disponible."
                )

            latitude = self._safe_float(
                rental,
                "latitud",
            )

            longitude = self._safe_float(
                rental,
                "longitud",
            )

            if not (
                latitude
                and longitude
            ):
                raise UserError(
                    "No hay coordenadas para buscar la dirección."
                )

            rental.action_geocodificar_inverso()

            rental.invalidate_recordset()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Dirección obtenida desde las coordenadas."
                    ),
                    "geo": self._geo_payload(
                        rental,
                        user,
                    ),
                    "rental": (
                        self._serialize_rental_detail(
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
                    "code": "RENTAL_GEO_REVERSE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error reverse geocode alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # PLACE DATA
    # ============================================================

    def _normalize_address_components(
        self,
        components,
    ):
        if not isinstance(
            components,
            list,
        ):
            return []

        result = []

        for component in components[
            :100
        ]:
            if not isinstance(
                component,
                dict,
            ):
                continue

            long_name = self._normalize_text(
                component.get(
                    "long_name"
                ),
                max_length=300,
            )

            short_name = self._normalize_text(
                component.get(
                    "short_name"
                ),
                max_length=100,
            )

            types = component.get(
                "types"
            )

            if not isinstance(
                types,
                list,
            ):
                types = []

            clean_types = [
                self._normalize_text(
                    item,
                    max_length=100,
                )
                for item in types[
                    :20
                ]
                if item
            ]

            result.append(
                {
                    "long_name": long_name or "",
                    "short_name": short_name or "",
                    "types": clean_types,
                }
            )

        return result

    def _prepare_place_data(
        self,
        data,
    ):
        place = data.get(
            "place"
        )

        if isinstance(
            place,
            dict,
        ):
            data = place

        if not isinstance(
            data,
            dict,
        ):
            raise UserError(
                "Los datos del lugar no son válidos."
            )

        latitude = self._normalize_coordinate(
            data.get(
                "lat"
            ),
            coordinate="lat",
        )

        longitude = self._normalize_coordinate(
            data.get(
                "lng"
            ),
            coordinate="lng",
        )

        if (
            latitude is False
            or longitude is False
        ):
            raise UserError(
                "El lugar seleccionado debe incluir "
                "latitud y longitud."
            )

        formatted_address = self._normalize_text(
            data.get(
                "formatted_address"
            ),
            max_length=1000,
        )

        if not formatted_address:
            raise UserError(
                "El lugar seleccionado no incluye "
                "una dirección formateada."
            )

        return {
            "name": (
                self._normalize_text(
                    data.get(
                        "name"
                    ),
                    max_length=500,
                )
                or ""
            ),
            "formatted_address": formatted_address,
            "lat": latitude,
            "lng": longitude,
            "place_id": (
                self._normalize_text(
                    data.get(
                        "place_id"
                    ),
                    max_length=500,
                )
                or ""
            ),
            "address_components": (
                self._normalize_address_components(
                    data.get(
                        "address_components"
                    )
                )
            ),
        }

    @http.route(
        "/api/app/rentals/<int:rental_id>/geo/place",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_geo_apply_place(
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
                "action_aplicar_place_data",
            ):
                raise UserError(
                    "La aplicación de datos de Google Place "
                    "no está disponible."
                )

            data = self._json_body()

            place_data = self._prepare_place_data(
                data
            )

            rental.action_aplicar_place_data(
                place_data
            )

            rental.invalidate_recordset()

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s seleccionó "
                    "una ubicación de Google Places."
                    % user.name
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Ubicación seleccionada correctamente."
                    ),
                    "geo": self._geo_payload(
                        rental,
                        user,
                    ),
                    "rental": (
                        self._serialize_rental_detail(
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
                    "code": "RENTAL_GEO_PLACE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error aplicando Place alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # MANUAL COORDINATES
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/geo/manual-coordinates",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_geo_manual_coordinates(
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
                "action_aplicar_coordenadas_manuales",
            ):
                raise UserError(
                    "El registro de coordenadas manuales "
                    "no está disponible."
                )

            data = self._json_body()

            latitude = self._normalize_coordinate(
                (
                    data.get(
                        "lat"
                    )
                    if "lat"
                    in data
                    else data.get(
                        "latitude"
                    )
                ),
                coordinate="lat",
            )

            longitude = self._normalize_coordinate(
                (
                    data.get(
                        "lng"
                    )
                    if "lng"
                    in data
                    else data.get(
                        "longitude"
                    )
                ),
                coordinate="lng",
            )

            if (
                latitude is False
                or longitude is False
            ):
                raise UserError(
                    "Debe indicar latitud y longitud."
                )

            rental.action_aplicar_coordenadas_manuales(
                latitude,
                longitude,
            )

            rental.invalidate_recordset()

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s marcó manualmente "
                    "las coordenadas del equipo."
                    % user.name
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Coordenadas registradas correctamente."
                    ),
                    "geo": self._geo_payload(
                        rental,
                        user,
                    ),
                    "rental": (
                        self._serialize_rental_detail(
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
                    "code": "RENTAL_GEO_MANUAL_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error coordenadas manuales alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # MAPS URL
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/geo/maps-url",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_geo_maps_url(
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

            url = self._maps_url(
                rental
            )

            if not url:
                return self._json_response(
                    {
                        "success": False,
                        "code": "RENTAL_GEO_LOCATION_MISSING",
                        "message": (
                            "La máquina no tiene coordenadas "
                            "ni una dirección disponible."
                        ),
                    },
                    status=400,
                )

            # Si existe el método original, se consulta para conservar
            # su comportamiento/URL actual, pero nunca se devuelve
            # directamente el ir.actions.act_url a Flutter.
            if self._method_exists(
                rental,
                "action_abrir_en_google_maps",
            ):
                try:
                    action = rental.action_abrir_en_google_maps()

                    if (
                        isinstance(
                            action,
                            dict,
                        )
                        and action.get(
                            "url"
                        )
                    ):
                        url = action[
                            "url"
                        ]
                except UserError:
                    # Si no hay coordenadas pero sí dirección, mantenemos
                    # la URL de búsqueda construida por el controlador.
                    pass

            return self._json_response(
                {
                    "success": True,
                    "url": url,
                    "geo": self._geo_payload(
                        rental,
                        user,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error obteniendo Google Maps URL alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )
