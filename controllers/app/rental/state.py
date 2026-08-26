# -*- coding: utf-8 -*-

"""
Estados de la API Flutter del módulo Alquiler.

Endpoints:
    GET  /api/app/rentals/<id>/states
    POST /api/app/rentals/<id>/state

Objetivo:
- centralizar TODO el flujo de estados del modelo `alquiler`;
- reutilizar los métodos action_estado_* reales del modelo;
- respetar las mismas condiciones funcionales de la vista Odoo;
- exigir confirmación explícita en acciones destructivas;
- reservar Aprobar instalación y Resetear estado al administrador;
- devolver siempre el detalle actualizado.

No modifica campos generales: eso pertenece a detail.py.
No gestiona el wizard de inspección: eso pertenece a related.py.
"""

import logging

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .base import RentalBaseController


_logger = logging.getLogger(__name__)


class RentalStateController(RentalBaseController):

    # ============================================================
    # TRANSICIONES
    # ============================================================

    """
    Definición única del flujo expuesto a Flutter.

    visible_states:
        estados desde los cuales el botón existe en la vista.

    system_only:
        equivale a groups="base.group_system".

    confirmation:
        Flutter debe mostrar confirmación antes de POST.

    internal:
        estado/método existente en el modelo pero que normalmente
        debe ser activado por otro proceso (p. ej. inspección).
    """

    STATE_ACTIONS = {
        "reviewed": {
            "target": "revisada",
            "method": "action_estado_revisada",
            "label": "Marcar Revisada",
            "visible_states": (
                "sin_revisar",
            ),
            "system_only": False,
            "confirmation": False,
            "confirmation_message": False,
            "internal": False,
        },
        "ready": {
            "target": "lista",
            "method": "action_estado_lista",
            "label": "Marcar Lista",
            "visible_states": (
                "revisada",
            ),
            "system_only": False,
            "confirmation": False,
            "confirmation_message": False,
            "internal": False,
        },
        "inspection": {
            "target": "inspeccion",
            "method": "action_estado_inspeccion",
            "label": "Marcar En inspección",
            "visible_states": (
                "lista",
                "inspeccion",
                "subsanacion",
            ),
            "system_only": False,
            "confirmation": False,
            "confirmation_message": False,
            # La vista principal usa action_enviar_inspeccion,
            # no este método directo.
            "internal": True,
        },
        "remediation": {
            "target": "subsanacion",
            "method": "action_estado_subsanacion",
            "label": "Esperando subsanación",
            "visible_states": (
                "inspeccion",
                "subsanacion",
            ),
            "system_only": False,
            "confirmation": False,
            "confirmation_message": False,
            # Normalmente proviene del flujo de inspección.
            "internal": True,
        },
        "approve_installation": {
            "target": "por_instalar",
            "method": "action_estado_por_instalar",
            "label": "Aprobar Instalación",
            "visible_states": (
                "inspeccion",
                "subsanacion",
            ),
            "system_only": True,
            "confirmation": True,
            "confirmation_message": (
                "¿Confirmar que el equipo queda aprobado para instalación?"
            ),
            "internal": False,
        },
        "rented": {
            "target": "alquilada",
            "method": "action_estado_alquilada",
            "label": "Marcar Alquilada",
            "visible_states": (
                "por_instalar",
            ),
            "system_only": False,
            "confirmation": True,
            "confirmation_message": (
                "¿Confirmar que el equipo ya se encuentra alquilado?"
            ),
            "internal": False,
        },
        "problem": {
            "target": "con_problemas",
            "method": "action_estado_con_problemas",
            "label": "Con Problemas",
            "hidden_states": (
                "vendida",
                "con_problemas",
            ),
            "system_only": False,
            "confirmation": True,
            "confirmation_message": (
                "¿Confirmar que el equipo debe pasar a Con Problemas?"
            ),
            "internal": False,
        },
        "parts": {
            "target": "partes",
            "method": "action_estado_partes",
            "label": "De Partes",
            "hidden_states": (
                "vendida",
                "partes",
            ),
            "system_only": False,
            "confirmation": True,
            "confirmation_message": (
                "¿Confirmar que el equipo será marcado como De Partes?"
            ),
            "internal": False,
        },
        "sold": {
            "target": "vendida",
            "method": "action_estado_vendida",
            "label": "Marcar Vendida",
            "hidden_states": (
                "vendida",
            ),
            "system_only": False,
            "confirmation": True,
            "confirmation_message": (
                "¿Está seguro de marcar este equipo como vendido?"
            ),
            "internal": False,
        },
        "reset": {
            "target": "sin_revisar",
            "method": "action_estado_sin_revisar",
            "label": "Resetear Estado",
            "hidden_states": (
                "sin_revisar",
            ),
            "system_only": True,
            "confirmation": True,
            "confirmation_message": (
                "¿Está seguro de resetear el estado del equipo?"
            ),
            "internal": False,
        },
        "external": {
            "target": "externo",
            "method": "action_estado_externo",
            "label": "Marcar Externo",
            "hidden_states": (
                "externo",
            ),
            "system_only": False,
            "confirmation": True,
            "confirmation_message": (
                "¿Confirmar que el equipo será marcado como Externo?"
            ),
            "internal": False,
        },
    }

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/rentals/<int:rental_id>/states",
            "/api/app/rentals/<int:rental_id>/state",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def rental_state_options(
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
    # CONFIG / AVAILABILITY
    # ============================================================

    def _state_action_available(
        self,
        rental,
        user,
        action_key,
        config,
        *,
        include_internal=False,
    ):
        if not rental:
            return False

        if not self._is_rental_user(
            user
        ):
            return False

        if (
            config.get(
                "system_only"
            )
            and not self._is_system_user(
                user
            )
        ):
            return False

        if (
            config.get(
                "internal"
            )
            and not include_internal
        ):
            return False

        if not (
            self._is_system_user(
                user
            )
            or self._rental_model_access(
                user
            )["write"]
        ):
            return False

        method_name = config.get(
            "method"
        )

        if not self._method_exists(
            rental,
            method_name,
        ):
            return False

        current_state = self._safe_string(
            rental,
            "estado_alquiler_id",
        )

        visible_states = config.get(
            "visible_states"
        )

        if (
            visible_states
            and current_state
            not in visible_states
        ):
            return False

        hidden_states = config.get(
            "hidden_states"
        )

        if (
            hidden_states
            and current_state
            in hidden_states
        ):
            return False

        # Requisitos adicionales para marcar alquilada.
        if (
            action_key == "rented"
            and not self._rented_required_data_complete(
                rental
            )
        ):
            return False

        return True

    def _rented_required_data_complete(
        self,
        rental,
    ):
        """
        Replica la obligatoriedad de la vista cuando el equipo queda
        en estado alquilada:
        - dirección
        - contacto
        - celular
        - correo
        """
        required = (
            "direccion",
            "contacto_id",
            "celular",
            "correo_",
        )

        for field_name in required:
            if not self._field(
                rental,
                field_name,
                False,
            ):
                return False

        return True

    def _rented_missing_fields(
        self,
        rental,
    ):
        labels = {
            "direccion": "dirección",
            "contacto_id": "contacto",
            "celular": "celular",
            "correo_": "correo",
        }

        missing = []

        for field_name, label in labels.items():
            if not self._field(
                rental,
                field_name,
                False,
            ):
                missing.append(
                    {
                        "field": field_name,
                        "label": label,
                    }
                )

        return missing

    def _serialize_state_action(
        self,
        rental,
        user,
        action_key,
        config,
    ):
        available = (
            self._state_action_available(
                rental,
                user,
                action_key,
                config,
            )
        )

        unavailable_reason = False

        if not available:
            if (
                config.get(
                    "system_only"
                )
                and not self._is_system_user(
                    user
                )
            ):
                unavailable_reason = "system_only"

            elif config.get(
                "internal"
            ):
                unavailable_reason = "internal_flow"

            elif (
                action_key == "rented"
                and not self._rented_required_data_complete(
                    rental
                )
            ):
                unavailable_reason = "missing_rental_data"

            else:
                unavailable_reason = "state_or_permission"

        return {
            "key": action_key,
            "label": config.get(
                "label"
            ),
            "target_state": config.get(
                "target"
            ),
            "target_state_label": (
                self._state_label_for_value(
                    rental,
                    config.get(
                        "target"
                    ),
                )
            ),
            "available": available,
            "system_only": bool(
                config.get(
                    "system_only"
                )
            ),
            "requires_confirmation": bool(
                config.get(
                    "confirmation"
                )
            ),
            "confirmation_message": (
                config.get(
                    "confirmation_message"
                )
                or False
            ),
            "internal": bool(
                config.get(
                    "internal"
                )
            ),
            "unavailable_reason": (
                unavailable_reason
            ),
        }

    def _state_label_for_value(
        self,
        rental,
        value,
    ):
        if not value:
            return False

        options = self._selection_options_safe(
            rental,
            "estado_alquiler_id",
        )

        for option in options:
            if option.get(
                "value"
            ) == value:
                return option.get(
                    "label"
                )

        return value

    def _state_payload(
        self,
        rental,
        user,
    ):
        current_state = self._safe_string(
            rental,
            "estado_alquiler_id",
        )

        actions = []

        for action_key, config in self.STATE_ACTIONS.items():
            # Acciones internas no se muestran como botones normales.
            if config.get(
                "internal"
            ):
                continue

            actions.append(
                self._serialize_state_action(
                    rental,
                    user,
                    action_key,
                    config,
                )
            )

        return {
            "current": {
                "value": current_state,
                "label": (
                    self._selection_label_safe(
                        rental,
                        "estado_alquiler_id",
                    )
                ),
            },
            "actions": actions,
            "rented_requirements": {
                "complete": (
                    self._rented_required_data_complete(
                        rental
                    )
                ),
                "missing": (
                    self._rented_missing_fields(
                        rental
                    )
                ),
            },
        }

    # ============================================================
    # VALIDACIÓN DE ACCIÓN
    # ============================================================

    def _get_action_config(
        self,
        action_key,
    ):
        if not action_key:
            return False

        return self.STATE_ACTIONS.get(
            str(
                action_key
            ).strip()
        )

    def _validate_state_action(
        self,
        rental,
        user,
        action_key,
        config,
        *,
        confirmed=False,
    ):
        if not config:
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_RENTAL_STATE_ACTION",
                    "message": (
                        "La acción de estado solicitada no existe."
                    ),
                },
                status=400,
            )

        # Acciones internas nunca se ejecutan desde este endpoint público.
        if config.get(
            "internal"
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_STATE_INTERNAL_ACTION",
                    "message": (
                        "Ese cambio de estado pertenece a un flujo interno "
                        "y no puede ejecutarse directamente."
                    ),
                },
                status=400,
            )

        if (
            config.get(
                "system_only"
            )
            and not self._is_system_user(
                user
            )
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "SYSTEM_USER_REQUIRED",
                    "message": (
                        "Esta acción requiere permisos de administrador."
                    ),
                },
                status=403,
            )

        write_error = self._require_rental_write_access(
            rental,
            user,
        )

        if write_error:
            return write_error

        current_state = self._safe_string(
            rental,
            "estado_alquiler_id",
        )

        visible_states = config.get(
            "visible_states"
        )

        if (
            visible_states
            and current_state
            not in visible_states
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_RENTAL_STATE_TRANSITION",
                    "message": (
                        "La acción '%s' no está disponible desde el estado actual."
                        % config.get(
                            "label"
                        )
                    ),
                    "current_state": current_state,
                    "allowed_from": list(
                        visible_states
                    ),
                },
                status=409,
            )

        hidden_states = config.get(
            "hidden_states"
        )

        if (
            hidden_states
            and current_state
            in hidden_states
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_RENTAL_STATE_TRANSITION",
                    "message": (
                        "La acción '%s' no está disponible desde el estado actual."
                        % config.get(
                            "label"
                        )
                    ),
                    "current_state": current_state,
                },
                status=409,
            )

        method_name = config.get(
            "method"
        )

        if not self._method_exists(
            rental,
            method_name,
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_STATE_METHOD_NOT_AVAILABLE",
                    "message": (
                        "La acción no está disponible en este servidor."
                    ),
                    "method": method_name,
                },
                status=501,
            )

        if (
            action_key == "rented"
            and not self._rented_required_data_complete(
                rental
            )
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_REQUIRED_DATA_MISSING",
                    "message": (
                        "Antes de marcar la máquina como alquilada "
                        "deben completarse dirección, contacto, celular y correo."
                    ),
                    "missing": (
                        self._rented_missing_fields(
                            rental
                        )
                    ),
                },
                status=400,
            )

        if (
            config.get(
                "confirmation"
            )
            and not confirmed
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "CONFIRMATION_REQUIRED",
                    "message": (
                        config.get(
                            "confirmation_message"
                        )
                        or "Esta acción requiere confirmación."
                    ),
                    "action": action_key,
                    "requires_confirmation": True,
                },
                status=409,
            )

        return False

    # ============================================================
    # EJECUCIÓN
    # ============================================================

    def _execute_state_method(
        self,
        rental,
        method_name,
    ):
        method = getattr(
            rental,
            method_name,
            None,
        )

        if not callable(
            method
        ):
            raise UserError(
                "La acción solicitada no está implementada."
            )

        return method()

    # ============================================================
    # GET STATES
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/states",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_states(
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
                    "state": (
                        self._state_payload(
                            rental,
                            user,
                        )
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando estados alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # CHANGE STATE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/state",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_change_state(
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

            data = self._json_body()

            action_key = (
                data.get(
                    "action"
                )
                or data.get(
                    "key"
                )
            )

            config = self._get_action_config(
                action_key
            )

            confirmed = self._truthy(
                data.get(
                    "confirmed"
                )
            )

            validation_error = (
                self._validate_state_action(
                    rental,
                    user,
                    action_key,
                    config,
                    confirmed=confirmed,
                )
            )

            if validation_error:
                return validation_error

            old_state = self._safe_string(
                rental,
                "estado_alquiler_id",
            )

            old_label = (
                self._selection_label_safe(
                    rental,
                    "estado_alquiler_id",
                )
            )

            method_name = config[
                "method"
            ]

            self._execute_state_method(
                rental,
                method_name,
            )

            rental.invalidate_recordset()

            new_state = self._safe_string(
                rental,
                "estado_alquiler_id",
            )

            new_label = (
                self._selection_label_safe(
                    rental,
                    "estado_alquiler_id",
                )
            )

            expected_state = config.get(
                "target"
            )

            # Validación defensiva: el método debe haber dejado el
            # estado esperado. Si el modelo cambia su lógica en el
            # futuro, Flutter recibirá una advertencia explícita.
            state_matches = (
                not expected_state
                or new_state == expected_state
            )

            if not state_matches:
                _logger.warning(
                    (
                        "Acción estado alquiler %s id=%s esperaba %s "
                        "pero terminó en %s."
                    ),
                    action_key,
                    rental.id,
                    expected_state,
                    new_state,
                )

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s ejecutó '%s'. "
                    "Estado: %s → %s."
                    % (
                        user.name,
                        config.get(
                            "label"
                        ),
                        old_label
                        or old_state
                        or "Sin estado",
                        new_label
                        or new_state
                        or "Sin estado",
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Estado actualizado correctamente."
                    ),
                    "action": action_key,
                    "transition": {
                        "from": old_state,
                        "from_label": old_label,
                        "to": new_state,
                        "to_label": new_label,
                        "expected": expected_state,
                        "matches_expected": state_matches,
                    },
                    "state": (
                        self._state_payload(
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
                    "code": "RENTAL_STATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error cambiando estado alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )
