# -*- coding: utf-8 -*-

"""
Bloqueo / suspensión para Flutter - módulo Alquiler.

Endpoints:
    GET   /api/app/rentals/blocking/dashboard
    GET   /api/app/rentals/<id>/blocking
    PATCH /api/app/rentals/<id>/blocking

    GET   /api/app/rentals/<id>/blocking/impact
    POST  /api/app/rentals/<id>/blocking/action

    GET   /api/app/rentals/<id>/blocking/groups
    POST  /api/app/rentals/<id>/blocking/groups/refresh

Responsabilidades:
- exponer el estado real del sistema de bloqueo;
- editar configuración auxiliar;
- ejecutar exactamente las acciones reales del modelo `alquiler`;
- exigir confirmación en acciones sensibles;
- advertir del impacto sobre los demás equipos del mismo cliente;
- verificar acceso remoto usando el método existente;
- devolver grupos WhatsApp sin exponer API keys;
- ofrecer dashboard global de bloqueo para Flutter.

ESTADOS REALES:
    activo
    suspendido
    bloqueado
    no_accesible
    pendiente_bloqueo
    pendiente_desbloqueo

ACCIONES REALES:
    action_suspender_servicio(motivo=None, usuario_id=None)
    action_bloquear_equipo(motivo=None, usuario_id=None)
    action_desbloquear_equipo(motivo=None, usuario_id=None)
    action_marcar_pendiente_bloqueo()
    action_marcar_pendiente_desbloqueo()
    action_marcar_no_accesible()
    action_reactivar_servicio()
    action_verificar_acceso_remoto()
    action_refresh_grupos()

NOTA IMPORTANTE:
El modelo actual sobreescribe write() y, cuando cambia estado_bloqueo,
sincroniza el estado con otros equipos ALQUILADOS del mismo cliente.

Este controlador NO duplica esa sincronización.
Solo informa a Flutter qué equipos pueden quedar afectados y luego llama
la acción real del modelo.

No se expone:
- sat.whatsapp_gateway_api_key
- sat.whatsapp_gateway_base_url

No se permite ejecutar métodos arbitrarios enviados por Flutter.
"""

import logging

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .base import RentalBaseController


_logger = logging.getLogger(__name__)


class RentalBlockingController(RentalBaseController):

    # ============================================================
    # ESTADOS
    # ============================================================

    BLOCKING_STATES = (
        "activo",
        "suspendido",
        "bloqueado",
        "no_accesible",
        "pendiente_bloqueo",
        "pendiente_desbloqueo",
    )

    ATTENTION_STATES = (
        "pendiente_bloqueo",
        "pendiente_desbloqueo",
        "no_accesible",
    )

    # ============================================================
    # ACCIONES
    # ============================================================

    ACTIONS = {
        "suspend": {
            "method": "action_suspender_servicio",
            "label": "Suspender servicio",
            "target": "suspendido",
            "allowed_states": (
                "activo",
                "no_accesible",
                "pendiente_bloqueo",
                "pendiente_desbloqueo",
            ),
            "confirmation": True,
            "requires_reason": False,
            "reason_default": "Suspendido por mora de pagos",
            "affects_client": True,
        },
        "block": {
            "method": "action_bloquear_equipo",
            "label": "Bloquear equipo",
            "target": "bloqueado",
            "allowed_states": (
                "activo",
                "suspendido",
                "pendiente_bloqueo",
                "pendiente_desbloqueo",
            ),
            "confirmation": True,
            "requires_reason": False,
            "reason_default": (
                "Bloqueo remoto por suspensión de servicio"
            ),
            "affects_client": True,
        },
        "unblock": {
            "method": "action_desbloquear_equipo",
            "label": "Desbloquear equipo",
            "target": "activo",
            # La vista muestra pendiente_desbloqueo, aunque una versión
            # antigua del método solo acepta bloqueado/suspendido.
            # El endpoint detecta esta diferencia y usa reactivar como
            # fallback seguro cuando corresponde.
            "allowed_states": (
                "bloqueado",
                "suspendido",
                "pendiente_desbloqueo",
            ),
            "confirmation": True,
            "requires_reason": False,
            "reason_default": False,
            "affects_client": True,
        },
        "pending_block": {
            "method": "action_marcar_pendiente_bloqueo",
            "label": "Pendiente de bloqueo",
            "target": "pendiente_bloqueo",
            "disallowed_states": (
                "bloqueado",
                "pendiente_bloqueo",
            ),
            "confirmation": False,
            "requires_reason": False,
            "reason_default": (
                "Pendiente de bloqueo - Requiere acción"
            ),
            "affects_client": True,
        },
        "pending_unblock": {
            "method": "action_marcar_pendiente_desbloqueo",
            "label": "Pendiente de desbloqueo",
            "target": "pendiente_desbloqueo",
            "allowed_states": (
                "bloqueado",
            ),
            "confirmation": False,
            "requires_reason": False,
            "reason_default": False,
            "affects_client": True,
        },
        "not_accessible": {
            "method": "action_marcar_no_accesible",
            "label": "No accesible",
            "target": "no_accesible",
            "disallowed_states": (
                "bloqueado",
                "no_accesible",
            ),
            "confirmation": True,
            "requires_reason": False,
            "reason_default": (
                "Equipo no accesible para bloqueo remoto"
            ),
            "affects_client": True,
        },
        "reactivate": {
            "method": "action_reactivar_servicio",
            "label": "Reactivar servicio",
            "target": "activo",
            "disallowed_states": (
                "activo",
            ),
            "confirmation": True,
            "requires_reason": False,
            "reason_default": False,
            "affects_client": True,
        },
        "verify_remote": {
            "method": "action_verificar_acceso_remoto",
            "label": "Verificar acceso remoto",
            "target": False,
            "confirmation": False,
            "requires_reason": False,
            "reason_default": False,
            "affects_client": False,
        },
    }

    # ============================================================
    # EDITABLE CONFIG
    # ============================================================

    EDITABLE_FIELDS = (
        "motivo_bloqueo",
        "acceso_remoto_disponible",
        "ip_equipo",
        "asesor_ventas_id",
        "soporte_tecnico_id",
        "observaciones_bloqueo",
        "grupo_notificaciones_id",
        "grupo_asesor_ventas_id",
    )

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/rentals/blocking/dashboard",
            "/api/app/rentals/<int:rental_id>/blocking",
            "/api/app/rentals/<int:rental_id>/blocking/impact",
            "/api/app/rentals/<int:rental_id>/blocking/action",
            "/api/app/rentals/<int:rental_id>/blocking/groups",
            "/api/app/rentals/<int:rental_id>/blocking/groups/refresh",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def rental_blocking_options(
        self,
        rental_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # JSON HELPERS
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

    def _text(
        self,
        value,
        *,
        max_length=2000,
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

        if len(
            text
        ) > max_length:
            text = text[
                :max_length
            ]

        return text

    # ============================================================
    # MANY2ONE
    # ============================================================

    def _normalize_many2one(
        self,
        rental,
        field_name,
        value,
    ):
        if value in (
            None,
            False,
            "",
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

        comodel = getattr(
            field,
            "comodel_name",
            False,
        )

        if not comodel:
            return record_id

        related = request.env[
            comodel
        ].browse(
            record_id
        ).exists()

        if not related:
            raise UserError(
                "El registro seleccionado para %s no existe."
                % field_name
            )

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
                "No tienes acceso al valor seleccionado para %s."
                % field_name
            )

        return related.id

    # ============================================================
    # WHATSAPP GROUP OPTIONS
    # ============================================================

    def _whatsapp_groups(
        self,
        rental,
    ):
        """
        Usa el método existente del modelo.
        El resultado contiene únicamente id + etiqueta.
        Nunca devuelve configuración/API key.
        """
        method = getattr(
            rental,
            "_get_grupos_whatsapp",
            None,
        )

        if not callable(
            method
        ):
            return []

        try:
            raw = method()
        except Exception:
            _logger.exception(
                "Error cargando grupos WhatsApp para alquiler %s.",
                rental.id,
            )
            return []

        result = []

        if not isinstance(
            raw,
            (list, tuple),
        ):
            return result

        for item in raw:
            if not isinstance(
                item,
                (list, tuple),
            ):
                continue

            if len(
                item
            ) < 2:
                continue

            value = item[0]
            label = item[1]

            if not value:
                continue

            result.append(
                {
                    "value": str(
                        value
                    ),
                    "label": str(
                        label
                        or value
                    ),
                }
            )

        return result

    def _group_selection_valid(
        self,
        rental,
        value,
    ):
        if not value:
            return False

        groups = self._whatsapp_groups(
            rental
        )

        valid = {
            item[
                "value"
            ]
            for item in groups
        }

        # Si el gateway está temporalmente caído, no bloquear el
        # autoguardado de un valor ya configurado en el registro.
        if not valid:
            return str(
                value
            )

        if str(
            value
        ) not in valid:
            raise UserError(
                "El grupo de WhatsApp seleccionado ya no "
                "está disponible."
            )

        return str(
            value
        )

    # ============================================================
    # PREPARE CONFIG VALUES
    # ============================================================

    def _prepare_config_values(
        self,
        rental,
        data,
    ):
        if not isinstance(
            data,
            dict,
        ):
            return {}

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

        values = {}

        for field_name in (
            "motivo_bloqueo",
            "ip_equipo",
            "observaciones_bloqueo",
        ):
            if (
                field_name in data
                and field_name
                in rental._fields
            ):
                values[
                    field_name
                ] = self._text(
                    data.get(
                        field_name
                    )
                )

        if (
            "acceso_remoto_disponible"
            in data
            and "acceso_remoto_disponible"
            in rental._fields
        ):
            values[
                "acceso_remoto_disponible"
            ] = self._truthy(
                data.get(
                    "acceso_remoto_disponible"
                )
            )

        for field_name in (
            "asesor_ventas_id",
            "soporte_tecnico_id",
        ):
            if (
                field_name in data
                and field_name
                in rental._fields
            ):
                values[
                    field_name
                ] = self._normalize_many2one(
                    rental,
                    field_name,
                    data.get(
                        field_name
                    ),
                )

        for field_name in (
            "grupo_notificaciones_id",
            "grupo_asesor_ventas_id",
        ):
            if (
                field_name in data
                and field_name
                in rental._fields
            ):
                raw = data.get(
                    field_name
                )

                values[
                    field_name
                ] = (
                    self._group_selection_valid(
                        rental,
                        raw,
                    )
                    if raw
                    else False
                )

        return values

    # ============================================================
    # USER CATALOGS
    # ============================================================

    def _internal_users(
        self,
        *,
        technical_only=False,
        limit=500,
    ):
        User = request.env[
            "res.users"
        ]

        domain = [
            (
                "active",
                "=",
                True,
            ),
            (
                "share",
                "=",
                False,
            ),
        ]

        if technical_only:
            groups = []

            for xmlid in (
                self.TECHNICAL_GROUP,
                self.HEAD_GROUP,
            ):
                group = request.env.ref(
                    xmlid,
                    raise_if_not_found=False,
                )

                if group:
                    groups.append(
                        group.id
                    )

            if groups:
                domain.append(
                    (
                        "groups_id",
                        "in",
                        groups,
                    )
                )

        try:
            users = User.search(
                domain,
                order="name asc",
                limit=limit,
            )
        except Exception:
            _logger.exception(
                "No se pudieron cargar usuarios para bloqueo."
            )
            return []

        return [
            {
                "id": item.id,
                "name": item.name or "",
                "login": item.login or "",
            }
            for item in users
        ]

    # ============================================================
    # CLIENT IMPACT
    # ============================================================

    def _client_rented_equipment(
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

        Rental = self._rental_model()

        if not client:
            return Rental.browse()

        domain = [
            (
                "cliente_id",
                "=",
                client.id,
            )
        ]

        if "estado_alquiler_id" in Rental._fields:
            domain.append(
                (
                    "estado_alquiler_id",
                    "=",
                    "alquilada",
                )
            )

        if not include_source:
            domain.append(
                (
                    "id",
                    "!=",
                    rental.id,
                )
            )

        return Rental.search(
            domain,
            order="serie asc, id asc",
        )

    def _impact_payload(
        self,
        rental,
        user,
        *,
        action_key=False,
    ):
        client = self._safe_many2one(
            rental,
            "cliente_id",
        )

        equipment = self._client_rented_equipment(
            rental,
            include_source=True,
        )

        other_items = []

        for item in equipment:
            if item.id == rental.id:
                continue

            other_items.append(
                {
                    "id": item.id,
                    "serial": self._safe_string(
                        item,
                        "serie",
                    ),
                    "model": self._safe_many2one(
                        item,
                        "name",
                    ),
                    "brand": self._safe_string(
                        item,
                        "marca",
                    ),
                    "blocking_state": self._safe_string(
                        item,
                        "estado_bloqueo",
                        "activo",
                    ),
                    "blocking_state_label": (
                        self._selection_label_safe(
                            item,
                            "estado_bloqueo",
                        )
                    ),
                }
            )

        config = (
            self.ACTIONS.get(
                action_key
            )
            if action_key
            else False
        )

        will_sync = bool(
            client
            and other_items
            and (
                not config
                or config.get(
                    "affects_client"
                )
            )
        )

        return {
            "client": client,
            "source_equipment": {
                "id": rental.id,
                "serial": self._safe_string(
                    rental,
                    "serie",
                ),
                "model": self._safe_many2one(
                    rental,
                    "name",
                ),
                "blocking_state": self._safe_string(
                    rental,
                    "estado_bloqueo",
                    "activo",
                ),
            },
            "action": action_key or False,
            "synchronization_enabled_in_model": True,
            "will_affect_other_equipment": will_sync,
            "other_equipment_count": len(
                other_items
            ),
            "other_equipment": other_items,
        }

    # ============================================================
    # ACTION AVAILABILITY
    # ============================================================

    def _action_state_allowed(
        self,
        current_state,
        config,
    ):
        allowed = config.get(
            "allowed_states"
        )

        if (
            allowed
            and current_state
            not in allowed
        ):
            return False

        disallowed = config.get(
            "disallowed_states"
        )

        if (
            disallowed
            and current_state
            in disallowed
        ):
            return False

        return True

    def _action_available(
        self,
        rental,
        user,
        action_key,
        config,
    ):
        if not config:
            return False

        can_write = bool(
            self._is_system_user(
                user
            )
            or self._rental_model_access(
                user
            )["write"]
        )

        if not can_write:
            return False

        current_state = self._safe_string(
            rental,
            "estado_bloqueo",
            "activo",
        )

        if not self._action_state_allowed(
            current_state,
            config,
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

        if (
            action_key == "verify_remote"
            and not self._safe_string(
                rental,
                "ip_equipo",
            )
        ):
            return False

        return True

    def _actions_payload(
        self,
        rental,
        user,
    ):
        result = {}

        current_state = self._safe_string(
            rental,
            "estado_bloqueo",
            "activo",
        )

        for action_key, config in self.ACTIONS.items():
            available = self._action_available(
                rental,
                user,
                action_key,
                config,
            )

            reason = False

            if not available:
                if not self._method_exists(
                    rental,
                    config.get(
                        "method"
                    ),
                ):
                    reason = "method_unavailable"

                elif (
                    action_key == "verify_remote"
                    and not self._safe_string(
                        rental,
                        "ip_equipo",
                    )
                ):
                    reason = "missing_ip"

                elif not self._action_state_allowed(
                    current_state,
                    config,
                ):
                    reason = "state"

                else:
                    reason = "permission"

            result[
                action_key
            ] = {
                "label": config.get(
                    "label"
                ),
                "available": available,
                "target_state": config.get(
                    "target"
                )
                or False,
                "target_state_label": (
                    self._state_label(
                        rental,
                        config.get(
                            "target"
                        ),
                    )
                    if config.get(
                        "target"
                    )
                    else False
                ),
                "requires_confirmation": bool(
                    config.get(
                        "confirmation"
                    )
                ),
                "affects_client_equipment": bool(
                    config.get(
                        "affects_client"
                    )
                ),
                "unavailable_reason": reason,
            }

        return result

    def _state_label(
        self,
        rental,
        value,
    ):
        if not value:
            return False

        for option in self._selection_options_safe(
            rental,
            "estado_bloqueo",
        ):
            if option.get(
                "value"
            ) == value:
                return option.get(
                    "label"
                )

        return value

    # ============================================================
    # BLOCKING PAYLOAD
    # ============================================================

    def _blocking_payload(
        self,
        rental,
        user,
        *,
        include_catalogs=True,
    ):
        payload = self._serialize_rental_blocking(
            rental
        )

        payload[
            "actions"
        ] = self._actions_payload(
            rental,
            user,
        )

        payload[
            "impact"
        ] = self._impact_payload(
            rental,
            user,
        )

        payload[
            "state_options"
        ] = self._selection_options_safe(
            rental,
            "estado_bloqueo",
        )

        if include_catalogs:
            payload[
                "catalogs"
            ] = {
                "sales_advisors": self._internal_users(
                    technical_only=False,
                ),
                "technical_support": self._internal_users(
                    technical_only=True,
                ),
                "whatsapp_groups": self._whatsapp_groups(
                    rental
                ),
            }

        return payload

    # ============================================================
    # GET BLOCKING
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/blocking",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_blocking_get(
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
                    "blocking": self._blocking_payload(
                        rental,
                        user,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando bloqueo alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # PATCH CONFIG
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/blocking",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def rental_blocking_update(
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

            values = self._prepare_config_values(
                rental,
                data,
            )

            if not values:
                return self._json_response(
                    {
                        "success": True,
                        "message": (
                            "No se recibieron cambios de configuración."
                        ),
                        "blocking": self._blocking_payload(
                            rental,
                            user,
                        ),
                    }
                )

            # Nunca se permite modificar estado_bloqueo por PATCH.
            # Debe pasar por /blocking/action.
            rental.write(
                values
            )

            rental.invalidate_recordset()

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s actualizó "
                    "configuración de bloqueo (%s)."
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
                        "Configuración de bloqueo actualizada."
                    ),
                    "changed_fields": sorted(
                        values.keys()
                    ),
                    "blocking": self._blocking_payload(
                        rental,
                        user,
                    ),
                    "rental": self._serialize_rental_detail(
                        rental,
                        user,
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
                    "code": "RENTAL_BLOCKING_UPDATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error actualizando bloqueo alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # IMPACT PREVIEW
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/blocking/impact",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_blocking_impact(
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

            action_key = self._query_arg(
                "action",
                "",
            )

            if (
                action_key
                and action_key
                not in self.ACTIONS
            ):
                raise UserError(
                    "La acción indicada no existe."
                )

            return self._json_response(
                {
                    "success": True,
                    "impact": self._impact_payload(
                        rental,
                        user,
                        action_key=(
                            action_key
                            or False
                        ),
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
                    "code": "RENTAL_BLOCKING_IMPACT_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error impacto bloqueo alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # ACTION VALIDATION
    # ============================================================

    def _validate_action(
        self,
        rental,
        user,
        action_key,
        config,
        data,
    ):
        if not config:
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_BLOCKING_ACTION",
                    "message": (
                        "La acción de bloqueo solicitada no existe."
                    ),
                },
                status=400,
            )

        write_error = self._require_rental_write_access(
            rental,
            user,
        )

        if write_error:
            return write_error

        if not self._action_available(
            rental,
            user,
            action_key,
            config,
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "BLOCKING_ACTION_NOT_AVAILABLE",
                    "message": (
                        "La acción '%s' no está disponible "
                        "para el estado actual."
                        % config.get(
                            "label"
                        )
                    ),
                    "current_state": self._safe_string(
                        rental,
                        "estado_bloqueo",
                        "activo",
                    ),
                    "action": action_key,
                },
                status=409,
            )

        if (
            config.get(
                "confirmation"
            )
            and not self._truthy(
                data.get(
                    "confirmed"
                )
            )
        ):
            impact = self._impact_payload(
                rental,
                user,
                action_key=action_key,
            )

            message = (
                "¿Confirmar la acción '%s'?"
                % config.get(
                    "label"
                )
            )

            if impact[
                "will_affect_other_equipment"
            ]:
                message += (
                    " El modelo puede sincronizar el estado "
                    "con %s equipo(s) alquilado(s) adicional(es) "
                    "del mismo cliente."
                    % impact[
                        "other_equipment_count"
                    ]
                )

            return self._json_response(
                {
                    "success": False,
                    "code": "CONFIRMATION_REQUIRED",
                    "message": message,
                    "action": action_key,
                    "requires_confirmation": True,
                    "impact": impact,
                },
                status=409,
            )

        reason = self._text(
            data.get(
                "reason"
            )
        )

        if (
            config.get(
                "requires_reason"
            )
            and not reason
        ):
            raise UserError(
                "Debe indicar un motivo."
            )

        return False

    # ============================================================
    # ACTION EXECUTION
    # ============================================================

    def _execute_action(
        self,
        rental,
        user,
        action_key,
        config,
        data,
    ):
        method_name = config[
            "method"
        ]

        current_state = self._safe_string(
            rental,
            "estado_bloqueo",
            "activo",
        )

        reason = (
            self._text(
                data.get(
                    "reason"
                )
            )
            or config.get(
                "reason_default"
            )
            or False
        )

        # --------------------------------------------------------
        # Acciones que reciben motivo / usuario
        # --------------------------------------------------------
        if action_key in (
            "suspend",
            "block",
        ):
            method = getattr(
                rental,
                method_name
            )

            return method(
                motivo=reason,
                usuario_id=user.id,
            )

        # --------------------------------------------------------
        # Desbloqueo
        # --------------------------------------------------------
        if action_key == "unblock":
            # En la versión revisada action_desbloquear_equipo()
            # acepta bloqueado/suspendido. La vista también muestra el
            # botón en pendiente_desbloqueo. Para ese estado usamos la
            # acción general de reactivación si está implementada.
            if (
                current_state
                == "pendiente_desbloqueo"
                and self._method_exists(
                    rental,
                    "action_reactivar_servicio",
                )
            ):
                return rental.action_reactivar_servicio()

            method = getattr(
                rental,
                method_name
            )

            return method(
                motivo=reason,
                usuario_id=user.id,
            )

        # --------------------------------------------------------
        # Resto
        # --------------------------------------------------------
        method = getattr(
            rental,
            method_name
        )

        return method()

    # ============================================================
    # ACTION ENDPOINT
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/blocking/action",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_blocking_action(
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

            action_key = str(
                data.get(
                    "action"
                )
                or ""
            ).strip()

            config = self.ACTIONS.get(
                action_key
            )

            validation_error = self._validate_action(
                rental,
                user,
                action_key,
                config,
                data,
            )

            if validation_error:
                return validation_error

            old_state = self._safe_string(
                rental,
                "estado_bloqueo",
                "activo",
            )

            old_label = self._selection_label_safe(
                rental,
                "estado_bloqueo",
            )

            impact_before = self._impact_payload(
                rental,
                user,
                action_key=action_key,
            )

            result = self._execute_action(
                rental,
                user,
                action_key,
                config,
                data,
            )

            rental.invalidate_recordset()

            new_state = self._safe_string(
                rental,
                "estado_bloqueo",
                "activo",
            )

            new_label = self._selection_label_safe(
                rental,
                "estado_bloqueo",
            )

            expected = config.get(
                "target"
            )

            matches_expected = bool(
                not expected
                or new_state == expected
            )

            affected_after = []

            if config.get(
                "affects_client"
            ):
                synced = self._client_rented_equipment(
                    rental,
                    include_source=True,
                )

                for item in synced:
                    affected_after.append(
                        {
                            "id": item.id,
                            "serial": self._safe_string(
                                item,
                                "serie",
                            ),
                            "state": self._safe_string(
                                item,
                                "estado_bloqueo",
                                "activo",
                            ),
                            "state_label": (
                                self._selection_label_safe(
                                    item,
                                    "estado_bloqueo",
                                )
                            ),
                        }
                    )

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s ejecutó '%s'. "
                    "Estado de servicio: %s → %s."
                    % (
                        user.name,
                        config.get(
                            "label"
                        ),
                        old_label
                        or old_state,
                        new_label
                        or new_state,
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Acción de bloqueo ejecutada correctamente."
                    ),
                    "action": action_key,
                    "transition": {
                        "from": old_state,
                        "from_label": old_label,
                        "to": new_state,
                        "to_label": new_label,
                        "expected": expected,
                        "matches_expected": matches_expected,
                    },
                    "impact_before": impact_before,
                    "affected_equipment_after": affected_after,
                    "model_result": (
                        result
                        if isinstance(
                            result,
                            (
                                bool,
                                int,
                                float,
                                str,
                                dict,
                                list,
                                tuple,
                            ),
                        )
                        else bool(
                            result
                        )
                    ),
                    "blocking": self._blocking_payload(
                        rental,
                        user,
                    ),
                    "rental": self._serialize_rental_detail(
                        rental,
                        user,
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
                    "code": "RENTAL_BLOCKING_ACTION_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error acción bloqueo alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # GROUPS
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/blocking/groups",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_blocking_groups(
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
                    "groups": self._whatsapp_groups(
                        rental
                    ),
                    "selected": {
                        "notifications": self._safe_string(
                            rental,
                            "grupo_notificaciones_id",
                        ),
                        "sales": self._safe_string(
                            rental,
                            "grupo_asesor_ventas_id",
                        ),
                    },
                    "gateway_secrets_exposed": False,
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando grupos bloqueo alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    @http.route(
        "/api/app/rentals/<int:rental_id>/blocking/groups/refresh",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_blocking_groups_refresh(
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

            method = getattr(
                rental,
                "action_refresh_grupos",
                None,
            )

            if callable(
                method
            ):
                try:
                    method()
                except Exception:
                    # El método solo refresca selection metadata.
                    # Aunque falle, intentamos obtener la lista real.
                    _logger.exception(
                        "action_refresh_grupos falló para alquiler %s.",
                        rental.id,
                    )

            groups = self._whatsapp_groups(
                rental
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Lista de grupos actualizada."
                    ),
                    "groups": groups,
                    "count": len(
                        groups
                    ),
                    "gateway_secrets_exposed": False,
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
                    "code": "RENTAL_BLOCKING_GROUPS_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error refrescando grupos bloqueo alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # DASHBOARD
    # ============================================================

    @http.route(
        "/api/app/rentals/blocking/dashboard",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_blocking_dashboard(
        self,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            Rental = self._rental_model()

            base_domain = []

            # El dashboard de bloqueo operativo trabaja sobre equipos
            # alquilados, igual que get_dashboard_data_alquilados().
            if "estado_alquiler_id" in Rental._fields:
                base_domain.append(
                    (
                        "estado_alquiler_id",
                        "=",
                        "alquilada",
                    )
                )

            totals = {
                "total": Rental.search_count(
                    base_domain
                )
            }

            state_counts = []

            for value in self.BLOCKING_STATES:
                count = Rental.search_count(
                    base_domain
                    + [
                        (
                            "estado_bloqueo",
                            "=",
                            value,
                        )
                    ]
                )

                totals[
                    value
                ] = count

                state_counts.append(
                    {
                        "value": value,
                        "label": self._state_label(
                            Rental,
                            value,
                        ),
                        "count": count,
                    }
                )

            attention_limit = self._positive_int(
                self._query_arg(
                    "limit",
                    30,
                ),
                30,
                minimum=1,
                maximum=200,
            )

            attention = Rental.search(
                base_domain
                + [
                    (
                        "estado_bloqueo",
                        "in",
                        list(
                            self.ATTENTION_STATES
                        ),
                    )
                ],
                order=(
                    "fecha_bloqueo desc, id desc"
                    if "fecha_bloqueo"
                    in Rental._fields
                    else "id desc"
                ),
                limit=attention_limit,
            )

            items = []

            for rental in attention:
                items.append(
                    {
                        "id": rental.id,
                        "serial": self._safe_string(
                            rental,
                            "serie",
                        ),
                        "brand": self._safe_string(
                            rental,
                            "marca",
                        ),
                        "model": self._safe_many2one(
                            rental,
                            "name",
                        ),
                        "client": self._safe_many2one(
                            rental,
                            "cliente_id",
                        ),
                        "state": self._safe_string(
                            rental,
                            "estado_bloqueo",
                            "activo",
                        ),
                        "state_label": (
                            self._selection_label_safe(
                                rental,
                                "estado_bloqueo",
                            )
                        ),
                        "reason": self._safe_string(
                            rental,
                            "motivo_bloqueo",
                        ),
                        "blocked_at": self._safe_date_field(
                            rental,
                            "fecha_bloqueo",
                        ),
                        "address": self._safe_string(
                            rental,
                            "direccion",
                        ),
                        "device_ip": self._safe_string(
                            rental,
                            "ip_equipo",
                        ),
                        "remote_access_available": self._safe_bool(
                            rental,
                            "acceso_remoto_disponible",
                            True,
                        ),
                        "actions": self._actions_payload(
                            rental,
                            user,
                        ),
                    }
                )

            return self._json_response(
                {
                    "success": True,
                    "dashboard": {
                        "totals": totals,
                        "by_state": state_counts,
                        "attention_count": len(
                            items
                        ),
                        "attention": items,
                    },
                    "state_options": self._selection_options_safe(
                        Rental,
                        "estado_bloqueo",
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando dashboard de bloqueo."
            )

            return self._error_response(
                exc
            )
