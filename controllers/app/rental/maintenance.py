# -*- coding: utf-8 -*-

"""
Mantenimiento preventivo de la API Flutter del módulo Alquiler.

Endpoints:
    GET   /api/app/rentals/<id>/maintenance
    PATCH /api/app/rentals/<id>/maintenance

    POST  /api/app/rentals/<id>/maintenance/recalculate
    POST  /api/app/rentals/<id>/maintenance/reset
    POST  /api/app/rentals/<id>/maintenance/correct-pattern
    POST  /api/app/rentals/<id>/maintenance/complete
    POST  /api/app/rentals/<id>/maintenance/response
    POST  /api/app/rentals/<id>/maintenance/test-mail

    GET   /api/app/rentals/<id>/maintenance/apply-client-preview
    POST  /api/app/rentals/<id>/maintenance/apply-client

Objetivos:
- replicar la lógica real del modelo `alquiler`;
- no reimplementar en Flutter cálculos de recurrencia;
- permitir autoguardado de la configuración;
- recalcular siempre en Odoo;
- manejar confirmación y reprogramación;
- completar mantenimientos;
- aplicar configuración a todos los equipos del mismo cliente;
- devolver datos actualizados después de cada acción.

IMPORTANTE:
El modelo actual ya contiene los métodos:
    iniciar_calculo_recurrente()
    corregir_patron_manualmente()
    reiniciar_configuracion()
    confirmar_mantenimiento_completado()
    button_send_test_mail()
    aplicar_configuracion_a_todos()
    process_maintenance_response()

Este controlador los reutiliza. No duplica su lógica de negocio.
"""

import logging

from odoo import fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .base import RentalBaseController


_logger = logging.getLogger(__name__)


class RentalMaintenanceController(RentalBaseController):

    # ============================================================
    # CAMPOS DE CONFIGURACIÓN
    # ============================================================

    MAINTENANCE_EDITABLE_FIELDS = (
        "control_mantenimiento",
        "fecha_inicio",
        "intervalo_meses",
        "patron_recurrencia",
        "semana_mes",
        "dia_semana",
        "motivo_reprogramacion",
    )

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/rentals/<int:rental_id>/maintenance",
            "/api/app/rentals/<int:rental_id>/maintenance/recalculate",
            "/api/app/rentals/<int:rental_id>/maintenance/reset",
            "/api/app/rentals/<int:rental_id>/maintenance/correct-pattern",
            "/api/app/rentals/<int:rental_id>/maintenance/complete",
            "/api/app/rentals/<int:rental_id>/maintenance/response",
            "/api/app/rentals/<int:rental_id>/maintenance/test-mail",
            "/api/app/rentals/<int:rental_id>/maintenance/apply-client-preview",
            "/api/app/rentals/<int:rental_id>/maintenance/apply-client",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def rental_maintenance_options(
        self,
        rental_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # JSON / VALUES
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
                "confirm",
                "confirmed",
            )
        )

    # ============================================================
    # FIELD NORMALIZATION
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
            )
        )

    def _normalize_date(
        self,
        value,
    ):
        if value in (
            None,
            False,
            "",
        ):
            return False

        try:
            return fields.Date.to_date(
                value
            )
        except Exception:
            raise UserError(
                "La fecha de inicio no es válida."
            )

    def _normalize_selection(
        self,
        rental,
        field_name,
        value,
    ):
        if value in (
            None,
            False,
            "",
        ):
            return False

        options = self._selection_options_safe(
            rental,
            field_name,
        )

        valid = {
            option["value"]
            for option in options
        }

        if (
            valid
            and value not in valid
        ):
            raise UserError(
                "El valor seleccionado para %s no es válido."
                % field_name
            )

        return value

    def _prepare_maintenance_values(
        self,
        rental,
        data,
    ):
        values = {}

        if not isinstance(
            data,
            dict,
        ):
            return values

        if "control_mantenimiento" in data:
            values[
                "control_mantenimiento"
            ] = self._normalize_boolean(
                data.get(
                    "control_mantenimiento"
                )
            )

        if "fecha_inicio" in data:
            values[
                "fecha_inicio"
            ] = self._normalize_date(
                data.get(
                    "fecha_inicio"
                )
            )

        for field_name in (
            "intervalo_meses",
            "patron_recurrencia",
            "semana_mes",
            "dia_semana",
        ):
            if field_name in data:
                values[
                    field_name
                ] = self._normalize_selection(
                    rental,
                    field_name,
                    data.get(
                        field_name
                    ),
                )

        if "motivo_reprogramacion" in data:
            value = data.get(
                "motivo_reprogramacion"
            )

            values[
                "motivo_reprogramacion"
            ] = (
                str(
                    value
                )
                if value
                else False
            )

        return values

    # ============================================================
    # VALIDACIÓN CONFIGURACIÓN
    # ============================================================

    def _validate_maintenance_values(
        self,
        rental,
        values,
    ):
        enabled = values.get(
            "control_mantenimiento",
            self._safe_bool(
                rental,
                "control_mantenimiento",
            ),
        )

        if not enabled:
            return

        start_date = values.get(
            "fecha_inicio",
            self._field(
                rental,
                "fecha_inicio",
                False,
            ),
        )

        interval = values.get(
            "intervalo_meses",
            self._safe_string(
                rental,
                "intervalo_meses",
            ),
        )

        pattern = values.get(
            "patron_recurrencia",
            self._safe_string(
                rental,
                "patron_recurrencia",
            ),
        )

        week = values.get(
            "semana_mes",
            self._safe_string(
                rental,
                "semana_mes",
            ),
        )

        weekday = values.get(
            "dia_semana",
            self._safe_string(
                rental,
                "dia_semana",
            ),
        )

        if not start_date:
            raise UserError(
                "Debe indicar la fecha inicial del mantenimiento."
            )

        if not interval:
            raise UserError(
                "Debe indicar el intervalo de mantenimiento."
            )

        if not pattern:
            raise UserError(
                "Debe indicar el patrón de recurrencia."
            )

        if (
            pattern == "semana_dia"
            and (
                not week
                or weekday in (
                    None,
                    False,
                    "",
                )
            )
        ):
            raise UserError(
                "Para el patrón por día de semana debe indicar "
                "la posición en el mes y el día de la semana."
            )

    # ============================================================
    # RECALCULO
    # ============================================================

    def _force_recalculate(
        self,
        rental,
    ):
        method = getattr(
            rental,
            "_compute_fecha_recurrente",
            None,
        )

        if not callable(
            method
        ):
            raise UserError(
                "El cálculo de mantenimiento no está disponible."
            )

        method()

        rental.invalidate_recordset()

    # ============================================================
    # ACCIONES DISPONIBLES
    # ============================================================

    def _maintenance_actions(
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

        enabled = self._safe_bool(
            rental,
            "control_mantenimiento",
        )

        has_client = bool(
            self._field(
                rental,
                "cliente_id",
                False,
            )
        )

        has_date = bool(
            self._field(
                rental,
                "fecha_recurrente",
                False,
            )
        )

        state = self._safe_string(
            rental,
            "estado_programacion",
            "pendiente",
        )

        blocking_state = self._safe_string(
            rental,
            "estado_bloqueo",
            "activo",
        )

        operational = (
            blocking_state
            not in (
                "suspendido",
                "bloqueado",
                "no_accesible",
            )
        )

        return {
            "edit": can_write,
            "recalculate": bool(
                can_write
                and enabled
                and self._method_exists(
                    rental,
                    "_compute_fecha_recurrente",
                )
            ),
            "restart_schedule": bool(
                can_write
                and enabled
                and self._method_exists(
                    rental,
                    "iniciar_calculo_recurrente",
                )
            ),
            "reset_configuration": bool(
                can_write
                and enabled
                and self._method_exists(
                    rental,
                    "reiniciar_configuracion",
                )
            ),
            "correct_pattern": bool(
                can_write
                and enabled
                and self._method_exists(
                    rental,
                    "corregir_patron_manualmente",
                )
            ),
            "complete": bool(
                can_write
                and enabled
                and has_date
                and self._method_exists(
                    rental,
                    "confirmar_mantenimiento_completado",
                )
            ),
            "confirm": bool(
                can_write
                and enabled
                and has_client
                and has_date
                and state
                not in (
                    "confirmado",
                    "reprogramado",
                )
                and self._method_exists(
                    rental,
                    "process_maintenance_response",
                )
            ),
            "request_reschedule": bool(
                can_write
                and enabled
                and has_client
                and has_date
                and self._method_exists(
                    rental,
                    "process_maintenance_response",
                )
            ),
            "test_mail": bool(
                can_write
                and enabled
                and operational
                and has_client
                and self._method_exists(
                    rental,
                    "button_send_test_mail",
                )
            ),
            "apply_to_client": bool(
                can_write
                and enabled
                and has_client
                and bool(
                    self._field(
                        rental,
                        "fecha_inicio",
                        False,
                    )
                )
                and bool(
                    self._safe_string(
                        rental,
                        "intervalo_meses",
                    )
                )
                and self._method_exists(
                    rental,
                    "aplicar_configuracion_a_todos",
                )
            ),
        }

    # ============================================================
    # SERIALIZER
    # ============================================================

    def _maintenance_payload(
        self,
        rental,
        user,
    ):
        data = self._serialize_rental_maintenance(
            rental
        )

        data.update(
            {
                "actions": self._maintenance_actions(
                    rental,
                    user,
                ),
                "options": {
                    "intervals": (
                        self._selection_options_safe(
                            rental,
                            "intervalo_meses",
                        )
                    ),
                    "patterns": (
                        self._selection_options_safe(
                            rental,
                            "patron_recurrencia",
                        )
                    ),
                    "week_positions": (
                        self._selection_options_safe(
                            rental,
                            "semana_mes",
                        )
                    ),
                    "weekdays": (
                        self._selection_options_safe(
                            rental,
                            "dia_semana",
                        )
                    ),
                    "states": (
                        self._selection_options_safe(
                            rental,
                            "estado_programacion",
                        )
                    ),
                },
                "configuration_complete": (
                    self._maintenance_configuration_complete(
                        rental
                    )
                ),
                "client_scope": (
                    self._maintenance_client_scope(
                        rental
                    )
                ),
            }
        )

        return data

    def _maintenance_configuration_complete(
        self,
        rental,
    ):
        if not self._safe_bool(
            rental,
            "control_mantenimiento",
        ):
            return False

        if not self._field(
            rental,
            "fecha_inicio",
            False,
        ):
            return False

        if not self._safe_string(
            rental,
            "intervalo_meses",
        ):
            return False

        pattern = self._safe_string(
            rental,
            "patron_recurrencia",
        )

        if not pattern:
            return False

        if pattern == "semana_dia":
            if not self._safe_string(
                rental,
                "semana_mes",
            ):
                return False

            weekday = self._safe_string(
                rental,
                "dia_semana",
            )

            if weekday in (
                None,
                False,
                "",
            ):
                return False

        return True

    # ============================================================
    # CLIENT SCOPE
    # ============================================================

    def _client_maintenance_records(
        self,
        rental,
        *,
        include_source=True,
    ):
        client = self._field(
            rental,
            "cliente_id",
            False,
        )

        if not client:
            return self._rental_model().browse()

        domain = [
            (
                "cliente_id",
                "=",
                client.id,
            ),
            (
                "control_mantenimiento",
                "=",
                True,
            ),
        ]

        if not include_source:
            domain.append(
                (
                    "id",
                    "!=",
                    rental.id,
                )
            )

        return self._rental_model().search(
            domain,
            order="serie asc, id asc",
        )

    def _maintenance_client_scope(
        self,
        rental,
    ):
        client = self._safe_many2one(
            rental,
            "cliente_id",
        )

        if not client:
            return {
                "client": False,
                "maintenance_equipment_count": 0,
                "other_equipment_count": 0,
            }

        all_records = self._client_maintenance_records(
            rental,
            include_source=True,
        )

        return {
            "client": client,
            "maintenance_equipment_count": len(
                all_records
            ),
            "other_equipment_count": max(
                0,
                len(
                    all_records
                )
                - 1,
            ),
        }

    # ============================================================
    # PREVIEW APPLY CLIENT
    # ============================================================

    def _apply_client_preview_payload(
        self,
        rental,
        user,
    ):
        if not self._field(
            rental,
            "cliente_id",
            False,
        ):
            return {
                "can_apply": False,
                "reason": "missing_client",
                "client": False,
                "source": self._serialize_rental_short(
                    rental,
                    user,
                ),
                "targets": [],
                "total_targets": 0,
                "configuration": (
                    self._serialize_rental_maintenance(
                        rental
                    )
                ),
            }

        targets = self._client_maintenance_records(
            rental,
            include_source=False,
        )

        serialized_targets = [
            {
                "id": item.id,
                "model": self._safe_many2one(
                    item,
                    "name",
                ),
                "brand": self._safe_string(
                    item,
                    "marca",
                ),
                "serial": self._safe_string(
                    item,
                    "serie",
                ),
                "state": self._safe_string(
                    item,
                    "estado_alquiler_id",
                ),
                "state_label": (
                    self._selection_label_safe(
                        item,
                        "estado_alquiler_id",
                    )
                ),
                "current_maintenance": (
                    self._serialize_rental_maintenance(
                        item
                    )
                ),
            }
            for item in targets
        ]

        complete = (
            self._maintenance_configuration_complete(
                rental
            )
        )

        return {
            "can_apply": bool(
                complete
                and targets
                and self._maintenance_actions(
                    rental,
                    user,
                )["apply_to_client"]
            ),
            "reason": (
                False
                if (
                    complete
                    and targets
                )
                else (
                    "incomplete_configuration"
                    if not complete
                    else "no_other_equipment"
                )
            ),
            "client": self._safe_many2one(
                rental,
                "cliente_id",
            ),
            "source": self._serialize_rental_short(
                rental,
                user,
            ),
            "configuration": (
                self._serialize_rental_maintenance(
                    rental
                )
            ),
            "targets": serialized_targets,
            "total_targets": len(
                serialized_targets
            ),
        }

    # ============================================================
    # GET
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/maintenance",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_maintenance_get(
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
                    "maintenance": (
                        self._maintenance_payload(
                            rental,
                            user,
                        )
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando mantenimiento alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # PATCH CONFIG / AUTOSAVE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/maintenance",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def rental_maintenance_update(
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

            values = self._prepare_maintenance_values(
                rental,
                data,
            )

            self._validate_maintenance_values(
                rental,
                values,
            )

            if not values:
                return self._json_response(
                    {
                        "success": True,
                        "message": (
                            "No se recibieron cambios de mantenimiento."
                        ),
                        "maintenance": (
                            self._maintenance_payload(
                                rental,
                                user,
                            )
                        ),
                    }
                )

            rental.write(
                values
            )

            # Los campos de recurrencia son @api.depends, pero se fuerza
            # el recálculo para que la respuesta Flutter nunca quede con
            # un valor anterior en el mismo request.
            if self._safe_bool(
                rental,
                "control_mantenimiento",
            ):
                self._force_recalculate(
                    rental
                )

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s actualizó la "
                    "configuración de mantenimiento (%s)."
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
                        "Configuración de mantenimiento guardada."
                    ),
                    "changed_fields": sorted(
                        values.keys()
                    ),
                    "maintenance": (
                        self._maintenance_payload(
                            rental,
                            user,
                        )
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
                    "code": "RENTAL_MAINTENANCE_UPDATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error actualizando mantenimiento alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # RECALCULATE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/maintenance/recalculate",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_maintenance_recalculate(
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

            if not self._safe_bool(
                rental,
                "control_mantenimiento",
            ):
                raise UserError(
                    "El control de mantenimiento está desactivado."
                )

            if not self._maintenance_configuration_complete(
                rental
            ):
                raise UserError(
                    "Complete la configuración de mantenimiento "
                    "antes de recalcular."
                )

            previous_date = self._safe_date_field(
                rental,
                "fecha_recurrente",
            )

            self._force_recalculate(
                rental
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Fecha de mantenimiento recalculada."
                    ),
                    "previous_date": previous_date,
                    "next_date": self._safe_date_field(
                        rental,
                        "fecha_recurrente",
                    ),
                    "maintenance": (
                        self._maintenance_payload(
                            rental,
                            user,
                        )
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
                    "code": "RENTAL_MAINTENANCE_RECALCULATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error recalculando mantenimiento alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # RESET / RESTART
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/maintenance/reset",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_maintenance_reset(
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

            confirmed = self._truthy(
                data.get(
                    "confirmed"
                )
            )

            if not confirmed:
                return self._json_response(
                    {
                        "success": False,
                        "code": "CONFIRMATION_REQUIRED",
                        "message": (
                            "¿Confirmar que desea reiniciar el cronograma "
                            "manteniendo la configuración actual?"
                        ),
                        "requires_confirmation": True,
                    },
                    status=409,
                )

            if self._method_exists(
                rental,
                "reiniciar_configuracion",
            ):
                rental.reiniciar_configuracion()

            elif self._method_exists(
                rental,
                "iniciar_calculo_recurrente",
            ):
                rental.iniciar_calculo_recurrente()
                self._force_recalculate(
                    rental
                )

            else:
                raise UserError(
                    "La acción para reiniciar el mantenimiento "
                    "no está disponible."
                )

            rental.invalidate_recordset()

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s reinició el "
                    "cronograma de mantenimiento."
                    % user.name
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Cronograma de mantenimiento reiniciado."
                    ),
                    "maintenance": (
                        self._maintenance_payload(
                            rental,
                            user,
                        )
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
                    "code": "RENTAL_MAINTENANCE_RESET_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error reiniciando mantenimiento alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # CORRECT PATTERN
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/maintenance/correct-pattern",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_maintenance_correct_pattern(
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
                "corregir_patron_manualmente",
            ):
                raise UserError(
                    "La corrección manual del patrón no está disponible."
                )

            data = self._json_body()

            weekday = data.get(
                "weekday"
            )

            week_position = data.get(
                "week_position"
            )

            if (
                weekday in (
                    None,
                    "",
                    False,
                )
                and week_position in (
                    None,
                    "",
                    False,
                )
            ):
                raise UserError(
                    "Debe indicar el día de la semana, "
                    "la posición en el mes o ambos."
                )

            if weekday not in (
                None,
                "",
                False,
            ):
                weekday = self._normalize_selection(
                    rental,
                    "dia_semana",
                    str(
                        weekday
                    ),
                )

            if week_position not in (
                None,
                "",
                False,
            ):
                week_position = self._normalize_selection(
                    rental,
                    "semana_mes",
                    str(
                        week_position
                    ),
                )

            rental.corregir_patron_manualmente(
                nuevo_dia_semana=weekday,
                nueva_posicion=week_position,
            )

            rental.invalidate_recordset()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Patrón de mantenimiento corregido."
                    ),
                    "maintenance": (
                        self._maintenance_payload(
                            rental,
                            user,
                        )
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
                    "code": "RENTAL_MAINTENANCE_PATTERN_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error corrigiendo patrón alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # COMPLETE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/maintenance/complete",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_maintenance_complete(
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
                "confirmar_mantenimiento_completado",
            ):
                raise UserError(
                    "La confirmación de mantenimiento completado "
                    "no está disponible."
                )

            data = self._json_body()

            if not self._truthy(
                data.get(
                    "confirmed"
                )
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "CONFIRMATION_REQUIRED",
                        "message": (
                            "¿Confirmar que este mantenimiento ya fue realizado?"
                        ),
                        "requires_confirmation": True,
                    },
                    status=409,
                )

            completed_date = self._safe_date_field(
                rental,
                "fecha_recurrente",
            )

            rental.confirmar_mantenimiento_completado()

            rental.invalidate_recordset()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Mantenimiento marcado como completado."
                    ),
                    "completed_date": completed_date,
                    "next_date": self._safe_date_field(
                        rental,
                        "fecha_recurrente",
                    ),
                    "maintenance": (
                        self._maintenance_payload(
                            rental,
                            user,
                        )
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
                    "code": "RENTAL_MAINTENANCE_COMPLETE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error completando mantenimiento alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # CLIENT RESPONSE: CONFIRM / RESCHEDULE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/maintenance/response",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_maintenance_response(
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
                "process_maintenance_response",
            ):
                raise UserError(
                    "El procesamiento de respuesta de mantenimiento "
                    "no está disponible."
                )

            data = self._json_body()

            response_type = (
                data.get(
                    "response"
                )
                or data.get(
                    "type"
                )
            )

            if response_type not in (
                "confirm",
                "reschedule",
            ):
                raise UserError(
                    "La respuesta debe ser 'confirm' o 'reschedule'."
                )

            if not self._truthy(
                data.get(
                    "confirmed"
                )
            ):
                message = (
                    "¿Confirmar el mantenimiento y crear los tickets "
                    "preventivos correspondientes?"
                    if response_type == "confirm"
                    else (
                        "¿Confirmar que se solicitará la reprogramación "
                        "del mantenimiento?"
                    )
                )

                return self._json_response(
                    {
                        "success": False,
                        "code": "CONFIRMATION_REQUIRED",
                        "message": message,
                        "response": response_type,
                        "requires_confirmation": True,
                    },
                    status=409,
                )

            if response_type == "reschedule":
                reason = data.get(
                    "reason"
                )

                if reason is not None:
                    rental.write(
                        {
                            "motivo_reprogramacion": (
                                str(
                                    reason
                                ).strip()
                                or False
                            )
                        }
                    )

            before_ticket_ids = set()

            Ticket = request.env[
                "ticket.alquiler"
            ]

            if (
                response_type == "confirm"
                and self._field(
                    rental,
                    "cliente_id",
                    False,
                )
                and self._field(
                    rental,
                    "fecha_recurrente",
                    False,
                )
            ):
                # Se usa solo para informar a Flutter cuántos tickets
                # fueron creados por la acción.
                before = Ticket.search(
                    [
                        (
                            "partner_id",
                            "=",
                            rental.cliente_id.id,
                        ),
                        (
                            "tipo_servicio_id",
                            "=",
                            "mantenimiento_preventivo",
                        ),
                    ]
                )

                before_ticket_ids = set(
                    before.ids
                )

            result = rental.process_maintenance_response(
                response_type
            )

            if result is False:
                raise UserError(
                    "No fue posible procesar la respuesta de mantenimiento."
                )

            rental.invalidate_recordset()

            created_tickets = []

            if response_type == "confirm":
                after = Ticket.search(
                    [
                        (
                            "partner_id",
                            "=",
                            rental.cliente_id.id,
                        ),
                        (
                            "tipo_servicio_id",
                            "=",
                            "mantenimiento_preventivo",
                        ),
                    ],
                    order="id desc",
                )

                for ticket in after:
                    if ticket.id in before_ticket_ids:
                        continue

                    created_tickets.append(
                        {
                            "id": ticket.id,
                            "reference": (
                                ticket.name
                                or ""
                            ),
                            "machine": (
                                self._safe_many2one(
                                    ticket,
                                    "product_alquiler",
                                )
                            ),
                            "state": (
                                ticket.estado
                                if "estado"
                                in ticket._fields
                                else False
                            ),
                        }
                    )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Mantenimiento confirmado."
                        if response_type == "confirm"
                        else (
                            "Solicitud de reprogramación registrada."
                        )
                    ),
                    "response": response_type,
                    "created_tickets": created_tickets,
                    "created_ticket_count": len(
                        created_tickets
                    ),
                    "maintenance": (
                        self._maintenance_payload(
                            rental,
                            user,
                        )
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
                    "code": "RENTAL_MAINTENANCE_RESPONSE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error procesando respuesta mantenimiento alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # TEST MAIL
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/maintenance/test-mail",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_maintenance_test_mail(
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
                "button_send_test_mail",
            ):
                raise UserError(
                    "El envío de correo de mantenimiento "
                    "no está disponible."
                )

            if not self._field(
                rental,
                "cliente_id",
                False,
            ):
                raise UserError(
                    "La máquina no tiene cliente asignado."
                )

            if not self._field(
                rental,
                "fecha_recurrente",
                False,
            ):
                raise UserError(
                    "No existe una fecha de mantenimiento programada."
                )

            blocking_state = self._safe_string(
                rental,
                "estado_bloqueo",
                "activo",
            )

            if blocking_state in (
                "suspendido",
                "bloqueado",
                "no_accesible",
            ):
                raise UserError(
                    "No se puede enviar el aviso mientras el servicio "
                    "se encuentre suspendido, bloqueado o no accesible."
                )

            data = self._json_body()

            if not self._truthy(
                data.get(
                    "confirmed"
                )
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "CONFIRMATION_REQUIRED",
                        "message": (
                            "¿Enviar ahora el correo de mantenimiento "
                            "al cliente?"
                        ),
                        "requires_confirmation": True,
                    },
                    status=409,
                )

            rental.button_send_test_mail()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Correo de mantenimiento enviado."
                    ),
                    "maintenance": (
                        self._maintenance_payload(
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
                    "code": "RENTAL_MAINTENANCE_MAIL_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error enviando correo mantenimiento alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # APPLY CLIENT PREVIEW
    # ============================================================

    @http.route(
        (
            "/api/app/rentals/<int:rental_id>"
            "/maintenance/apply-client-preview"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_maintenance_apply_client_preview(
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
                    "preview": (
                        self._apply_client_preview_payload(
                            rental,
                            user,
                        )
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error preview mantenimiento cliente alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # APPLY CLIENT
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/maintenance/apply-client",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_maintenance_apply_client(
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
                "aplicar_configuracion_a_todos",
            ):
                raise UserError(
                    "La aplicación masiva de mantenimiento "
                    "no está disponible."
                )

            preview = self._apply_client_preview_payload(
                rental,
                user,
            )

            if not preview[
                "can_apply"
            ]:
                reason = preview.get(
                    "reason"
                )

                if reason == "missing_client":
                    raise UserError(
                        "Debe seleccionar un cliente antes de aplicar "
                        "la configuración."
                    )

                if reason == "incomplete_configuration":
                    raise UserError(
                        "Complete la configuración de mantenimiento "
                        "antes de aplicarla."
                    )

                if reason == "no_other_equipment":
                    raise UserError(
                        "No se encontraron otros equipos del cliente "
                        "con mantenimiento activado."
                    )

                raise UserError(
                    "La configuración no puede aplicarse actualmente."
                )

            data = self._json_body()

            if not self._truthy(
                data.get(
                    "confirmed"
                )
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "CONFIRMATION_REQUIRED",
                        "message": (
                            "La configuración se aplicará a %s equipo(s) "
                            "del cliente %s. ¿Desea continuar?"
                            % (
                                preview[
                                    "total_targets"
                                ],
                                (
                                    preview[
                                        "client"
                                    ][
                                        "name"
                                    ]
                                    if preview.get(
                                        "client"
                                    )
                                    else ""
                                ),
                            )
                        ),
                        "requires_confirmation": True,
                        "preview": preview,
                    },
                    status=409,
                )

            target_ids = [
                item["id"]
                for item in preview[
                    "targets"
                ]
            ]

            rental.aplicar_configuracion_a_todos()

            rental.invalidate_recordset()

            targets = self._rental_model().browse(
                target_ids
            ).exists()

            updated_targets = [
                {
                    "id": item.id,
                    "model": self._safe_many2one(
                        item,
                        "name",
                    ),
                    "serial": self._safe_string(
                        item,
                        "serie",
                    ),
                    "maintenance": (
                        self._serialize_rental_maintenance(
                            item
                        )
                    ),
                }
                for item in targets
            ]

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s aplicó la configuración "
                    "de mantenimiento a %s equipo(s) del cliente."
                    % (
                        user.name,
                        len(
                            updated_targets
                        ),
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Configuración aplicada a los equipos del cliente."
                    ),
                    "updated_count": len(
                        updated_targets
                    ),
                    "updated_targets": updated_targets,
                    "maintenance": (
                        self._maintenance_payload(
                            rental,
                            user,
                        )
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
                    "code": "RENTAL_MAINTENANCE_APPLY_CLIENT_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error aplicando mantenimiento cliente alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )
