# -*- coding: utf-8 -*-

"""
Planificador de mantenimiento para Flutter - módulo Alquiler.

Endpoints principales:
    GET   /api/app/rentals/<id>/planner
    PATCH /api/app/rentals/<id>/planner
    POST  /api/app/rentals/<id>/planner/detect-zone
    POST  /api/app/rentals/<id>/planner/create-line
    POST  /api/app/rentals/<id>/planner/auto-schedule

    GET   /api/app/rentals/<id>/planner/lines
    GET   /api/app/rentals/<id>/planner/lines/<line_id>
    POST  /api/app/rentals/<id>/planner/lines/<line_id>/action

Objetivos:
- reutilizar la lógica real del modelo `alquiler`;
- no duplicar el algoritmo de disponibilidad;
- crear/reutilizar la línea del planificador activo;
- ejecutar auto-programación;
- exponer historial de líneas;
- exponer de forma defensiva los datos de cada línea;
- permitir acciones conocidas de la línea solo si existen realmente;
- mantener toda la autorización en Odoo.

Métodos reales confirmados en `alquiler`:
    action_detectar_zona_mantenimiento()
    action_crear_linea_planificador_activo()
    action_auto_programar_mantenimiento()
    action_ver_planificaciones_mantenimiento()

La auto-programación real termina llamando:
    mantenimiento.planificador.linea.action_buscar_y_asignar_slot()

Este controlador NO reemplaza esos métodos. Solo los expone de forma
segura para Flutter.
"""

import logging

from odoo import fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .base import RentalBaseController


_logger = logging.getLogger(__name__)


class RentalPlannerController(RentalBaseController):

    # ============================================================
    # MODELOS
    # ============================================================

    PLANNER_MODEL = "mantenimiento.planificador"
    LINE_MODEL = "mantenimiento.planificador.linea"
    ZONE_MODEL = "mantenimiento.zona"

    # ============================================================
    # CAMPOS EDITABLES DEL EQUIPO
    # ============================================================

    EDITABLE_FIELDS = (
        "zona_mantenimiento_id",
        "tecnico_mantenimiento_id",
        "fecha_programada_mantenimiento",
        "hora_programada_mantenimiento",
        "duracion_mantenimiento_horas",
        "cantidad_tecnicos_mantenimiento",
        "ignorar_zona_mantenimiento",
    )

    # ============================================================
    # ACCIONES CONOCIDAS DE LA LÍNEA
    # ============================================================

    """
    No se acepta un nombre de método arbitrario enviado por Flutter.

    Estas claves se traducen a métodos conocidos. Si una versión del
    modelo no tiene el método, la acción simplemente aparece como no
    disponible.

    Esto permite que el controlador sobreviva a diferencias entre
    versiones del planificador sin abrir una ejecución RPC genérica.
    """

    LINE_ACTION_METHODS = {
        "find_slot": (
            "action_buscar_y_asignar_slot",
        ),
        "confirm": (
            "action_confirmar",
            "action_confirm",
        ),
        "reassign": (
            "action_reasignar",
            "action_buscar_y_asignar_slot",
        ),
        "create_ticket": (
            "action_crear_ticket",
            "action_create_ticket",
        ),
        "cancel": (
            "action_cancelar",
            "action_cancel",
        ),
        "reset": (
            "action_reiniciar",
            "action_reset",
        ),
    }

    DESTRUCTIVE_LINE_ACTIONS = {
        "reassign",
        "create_ticket",
        "cancel",
        "reset",
    }

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/rentals/<int:rental_id>/planner",
            "/api/app/rentals/<int:rental_id>/planner/detect-zone",
            "/api/app/rentals/<int:rental_id>/planner/create-line",
            "/api/app/rentals/<int:rental_id>/planner/auto-schedule",
            "/api/app/rentals/<int:rental_id>/planner/lines",
            "/api/app/rentals/<int:rental_id>/planner/lines/<int:line_id>",
            "/api/app/rentals/<int:rental_id>/planner/lines/<int:line_id>/action",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def rental_planner_options(
        self,
        rental_id=None,
        line_id=None,
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
                "confirmed",
                "confirm",
            )
        )

    # ============================================================
    # MODELOS EXISTENTES
    # ============================================================

    def _model_available(
        self,
        model_name,
    ):
        try:
            request.env[
                model_name
            ]
            return True
        except Exception:
            return False

    def _planner_model(self):
        if not self._model_available(
            self.PLANNER_MODEL
        ):
            raise UserError(
                "El modelo de planificador de mantenimiento "
                "no está disponible."
            )

        return request.env[
            self.PLANNER_MODEL
        ]

    def _planner_line_model(self):
        if not self._model_available(
            self.LINE_MODEL
        ):
            raise UserError(
                "El modelo de líneas del planificador "
                "no está disponible."
            )

        return request.env[
            self.LINE_MODEL
        ]

    # ============================================================
    # NORMALIZACIÓN
    # ============================================================

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
                "El identificador de %s no es válido."
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
                "La fecha programada no es válida."
            )

    def _normalize_float(
        self,
        value,
        label,
    ):
        if value in (
            None,
            "",
            False,
        ):
            return False

        try:
            return float(
                value
            )
        except Exception:
            raise UserError(
                "%s debe ser un número."
                % label
            )

    def _normalize_int(
        self,
        value,
        label,
    ):
        if value in (
            None,
            "",
            False,
        ):
            return False

        try:
            return int(
                value
            )
        except Exception:
            raise UserError(
                "%s debe ser un número entero."
                % label
            )

    def _prepare_planner_values(
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

        if "zona_mantenimiento_id" in data:
            values[
                "zona_mantenimiento_id"
            ] = self._normalize_many2one(
                rental,
                "zona_mantenimiento_id",
                data.get(
                    "zona_mantenimiento_id"
                ),
            )

        if "tecnico_mantenimiento_id" in data:
            values[
                "tecnico_mantenimiento_id"
            ] = self._normalize_many2one(
                rental,
                "tecnico_mantenimiento_id",
                data.get(
                    "tecnico_mantenimiento_id"
                ),
            )

        if "fecha_programada_mantenimiento" in data:
            values[
                "fecha_programada_mantenimiento"
            ] = self._normalize_date(
                data.get(
                    "fecha_programada_mantenimiento"
                )
            )

        if "hora_programada_mantenimiento" in data:
            value = self._normalize_float(
                data.get(
                    "hora_programada_mantenimiento"
                ),
                "La hora programada",
            )

            if (
                value is not False
                and not (
                    0.0
                    <= value
                    < 24.0
                )
            ):
                raise UserError(
                    "La hora programada debe estar entre 0 y 23.99."
                )

            values[
                "hora_programada_mantenimiento"
            ] = value

        if "duracion_mantenimiento_horas" in data:
            value = self._normalize_float(
                data.get(
                    "duracion_mantenimiento_horas"
                ),
                "La duración",
            )

            if (
                value is not False
                and value <= 0
            ):
                raise UserError(
                    "La duración debe ser mayor a 0 horas."
                )

            values[
                "duracion_mantenimiento_horas"
            ] = value

        if "cantidad_tecnicos_mantenimiento" in data:
            value = self._normalize_int(
                data.get(
                    "cantidad_tecnicos_mantenimiento"
                ),
                "La cantidad de técnicos",
            )

            if (
                value is not False
                and value <= 0
            ):
                raise UserError(
                    "La cantidad de técnicos debe ser mayor a 0."
                )

            values[
                "cantidad_tecnicos_mantenimiento"
            ] = value

        if "ignorar_zona_mantenimiento" in data:
            values[
                "ignorar_zona_mantenimiento"
            ] = self._truthy(
                data.get(
                    "ignorar_zona_mantenimiento"
                )
            )

        return values

    # ============================================================
    # ZONAS / TÉCNICOS
    # ============================================================

    def _serialize_zone(
        self,
        zone,
    ):
        if not zone:
            return False

        result = {
            "id": zone.id,
            "name": (
                zone.display_name
                or zone.name
                or ""
            ),
        }

        for field_name in (
            "active",
            "description",
            "descripcion",
            "color",
        ):
            if field_name in zone._fields:
                value = zone[
                    field_name
                ]

                if field_name == "active":
                    result[
                        field_name
                    ] = bool(
                        value
                    )
                else:
                    result[
                        field_name
                    ] = value or False

        if "tecnico_ids" in zone._fields:
            result[
                "technicians"
            ] = [
                {
                    "id": user.id,
                    "name": user.name or "",
                    "login": user.login or "",
                }
                for user in zone.tecnico_ids
                if user.active
            ]

        return result

    def _planner_zones(
        self,
    ):
        if not self._model_available(
            self.ZONE_MODEL
        ):
            return []

        Zone = request.env[
            self.ZONE_MODEL
        ]

        domain = []

        if "active" in Zone._fields:
            domain.append(
                (
                    "active",
                    "=",
                    True,
                )
            )

        try:
            zones = Zone.search(
                domain,
                order="name asc, id asc",
            )
        except Exception:
            _logger.exception(
                "No se pudieron cargar zonas de mantenimiento."
            )
            return []

        return [
            self._serialize_zone(
                zone
            )
            for zone in zones
        ]

    def _planner_technicians(
        self,
        rental,
    ):
        User = request.env[
            "res.users"
        ]

        domain = [
            (
                "share",
                "=",
                False,
            ),
            (
                "active",
                "=",
                True,
            ),
        ]

        zone = self._field(
            rental,
            "zona_mantenimiento_id",
            False,
        )

        ignore_zone = self._safe_bool(
            rental,
            "ignorar_zona_mantenimiento",
        )

        if (
            zone
            and not ignore_zone
            and "tecnico_ids"
            in zone._fields
        ):
            users = zone.tecnico_ids.filtered(
                lambda item: (
                    item.active
                    and not item.share
                )
            )
        else:
            technical = request.env.ref(
                self.TECHNICAL_GROUP,
                raise_if_not_found=False,
            )

            head = request.env.ref(
                self.HEAD_GROUP,
                raise_if_not_found=False,
            )

            group_ids = [
                item.id
                for item in (
                    technical,
                    head,
                )
                if item
            ]

            if group_ids:
                domain.append(
                    (
                        "groups_id",
                        "in",
                        group_ids,
                    )
                )

            users = User.search(
                domain,
                order="name asc",
            )

        return [
            {
                "id": item.id,
                "name": item.name or "",
                "login": item.login or "",
            }
            for item in users
        ]

    # ============================================================
    # ACTIVE PLAN
    # ============================================================

    def _find_active_plan(
        self,
        rental,
    ):
        target_date = self._field(
            rental,
            "fecha_recurrente",
            False,
        )

        if not target_date:
            return self._planner_model().browse()

        Plan = self._planner_model()

        domain = []

        if "fecha_inicio" in Plan._fields:
            domain.append(
                (
                    "fecha_inicio",
                    "<=",
                    target_date,
                )
            )

        if "fecha_fin" in Plan._fields:
            domain.append(
                (
                    "fecha_fin",
                    ">=",
                    target_date,
                )
            )

        if "estado" in Plan._fields:
            domain.append(
                (
                    "estado",
                    "in",
                    [
                        "borrador",
                        "generado",
                        "en_proceso",
                    ],
                )
            )

        return Plan.search(
            domain,
            order="fecha_inicio desc, id desc",
            limit=1,
        )

    def _serialize_plan(
        self,
        plan,
    ):
        if not plan:
            return False

        result = {
            "id": plan.id,
            "name": (
                plan.display_name
                or (
                    plan.name
                    if "name" in plan._fields
                    else ""
                )
                or ""
            ),
        }

        field_map = {
            "fecha_inicio": "start_date",
            "fecha_fin": "end_date",
            "estado": "state",
            "create_date": "created_at",
            "write_date": "updated_at",
        }

        for field_name, key in field_map.items():
            if field_name not in plan._fields:
                continue

            value = plan[
                field_name
            ]

            if field_name in (
                "fecha_inicio",
                "fecha_fin",
            ):
                result[
                    key
                ] = self._safe_date_value(
                    value
                )
            elif field_name in (
                "create_date",
                "write_date",
            ):
                result[
                    key
                ] = self._safe_date_value(
                    value
                )
            else:
                result[
                    key
                ] = value or False

        if "estado" in plan._fields:
            result[
                "state_label"
            ] = self._selection_label_safe(
                plan,
                "estado",
            )

        return result

    # ============================================================
    # LINE ACCESS
    # ============================================================

    def _get_line(
        self,
        rental,
        line_id,
        *,
        require_write=False,
    ):
        Line = self._planner_line_model()

        try:
            line = Line.browse(
                int(
                    line_id
                )
            ).exists()

            if not line:
                return Line.browse()

            if (
                "equipo_id"
                in line._fields
                and line.equipo_id
                and line.equipo_id.id
                != rental.id
            ):
                return Line.browse()

            if hasattr(
                line,
                "check_access",
            ):
                line.check_access(
                    "write"
                    if require_write
                    else "read"
                )

            return line

        except (
            AccessError,
            ValueError,
            TypeError,
        ):
            return Line.browse()

    # ============================================================
    # GENERIC FIELD SERIALIZATION
    # ============================================================

    def _serialize_generic_value(
        self,
        record,
        field_name,
    ):
        if field_name not in record._fields:
            return False

        field = record._fields[
            field_name
        ]

        value = record[
            field_name
        ]

        field_type = getattr(
            field,
            "type",
            False,
        )

        if field_type == "many2one":
            return (
                self._many2one(
                    value
                )
                if value
                else False
            )

        if field_type in (
            "one2many",
            "many2many",
        ):
            return [
                self._many2one(
                    item
                )
                for item in value
            ]

        if field_type in (
            "date",
            "datetime",
        ):
            return self._safe_date_value(
                value
            )

        if field_type == "boolean":
            return bool(
                value
            )

        if field_type in (
            "integer",
            "float",
            "monetary",
        ):
            return value or 0

        return value or False

    # ============================================================
    # LINE ACTIONS
    # ============================================================

    def _resolve_line_action_method(
        self,
        line,
        action_key,
    ):
        candidates = self.LINE_ACTION_METHODS.get(
            action_key,
            ()
        )

        for method_name in candidates:
            if callable(
                getattr(
                    line,
                    method_name,
                    None,
                )
            ):
                return method_name

        return False

    def _line_actions(
        self,
        line,
        user,
    ):
        can_write = bool(
            self._is_system_user(
                user
            )
            or self._model_has_access(
                self.LINE_MODEL,
                "write",
            )
        )

        state = (
            line.estado
            if (
                line
                and "estado"
                in line._fields
            )
            else False
        )

        result = {}

        for action_key in self.LINE_ACTION_METHODS:
            method_name = self._resolve_line_action_method(
                line,
                action_key,
            )

            available = bool(
                can_write
                and method_name
            )

            # Evitar acciones evidentemente inconsistentes.
            if action_key == "cancel":
                available = bool(
                    available
                    and state != "cancelado"
                )

            if action_key == "find_slot":
                available = bool(
                    available
                    and state
                    not in (
                        "cancelado",
                        "ticket_creado",
                    )
                )

            if action_key == "create_ticket":
                available = bool(
                    available
                    and state
                    not in (
                        "cancelado",
                        "ticket_creado",
                    )
                )

            result[
                action_key
            ] = {
                "available": available,
                "method": (
                    method_name
                    or False
                ),
                "requires_confirmation": (
                    action_key
                    in self.DESTRUCTIVE_LINE_ACTIONS
                ),
            }

        return result

    # ============================================================
    # LINE SERIALIZER
    # ============================================================

    def _serialize_line(
        self,
        line,
        user,
        *,
        full=False,
    ):
        if not line:
            return False

        result = {
            "id": line.id,
            "display_name": (
                line.display_name
                or ""
            ),
        }

        common_fields = (
            "planificador_id",
            "equipo_id",
            "cliente_id",
            "distrito",
            "zona_id",
            "fecha_ideal",
            "fecha_programada",
            "fecha",
            "hora_inicio",
            "hora_fin",
            "hora_programada",
            "cantidad_tecnicos",
            "duracion_horas",
            "ignorar_zona",
            "tecnico_id",
            "tecnico_ids",
            "responsable_id",
            "estado",
            "motivo",
            "observaciones",
            "ticket_id",
            "create_date",
            "write_date",
        )

        for field_name in common_fields:
            if field_name not in line._fields:
                continue

            result[
                field_name
            ] = self._serialize_generic_value(
                line,
                field_name,
            )

        if "estado" in line._fields:
            result[
                "state_label"
            ] = self._selection_label_safe(
                line,
                "estado",
            )

        if full:
            extra = {}

            # Se devuelven campos escalares adicionales para no perder
            # información si el modelo de línea tiene extensiones.
            for field_name, field in line._fields.items():
                if (
                    field_name
                    in result
                    or field_name
                    in common_fields
                    or field_name
                    in (
                        "__last_update",
                        "message_ids",
                        "message_follower_ids",
                        "activity_ids",
                    )
                ):
                    continue

                field_type = getattr(
                    field,
                    "type",
                    False,
                )

                if field_type not in (
                    "char",
                    "text",
                    "html",
                    "boolean",
                    "integer",
                    "float",
                    "monetary",
                    "date",
                    "datetime",
                    "selection",
                    "many2one",
                ):
                    continue

                try:
                    extra[
                        field_name
                    ] = self._serialize_generic_value(
                        line,
                        field_name,
                    )
                except Exception:
                    continue

            result[
                "extra"
            ] = extra

        result[
            "actions"
        ] = self._line_actions(
            line,
            user,
        )

        return result

    # ============================================================
    # LIST LINES
    # ============================================================

    def _planner_lines(
        self,
        rental,
        *,
        limit=200,
    ):
        Line = self._planner_line_model()

        domain = []

        if "equipo_id" in Line._fields:
            domain.append(
                (
                    "equipo_id",
                    "=",
                    rental.id,
                )
            )
        else:
            return Line.browse()

        order_parts = []

        for field_name in (
            "fecha_programada",
            "fecha_ideal",
            "create_date",
        ):
            if field_name in Line._fields:
                order_parts.append(
                    "%s desc"
                    % field_name
                )

        order_parts.append(
            "id desc"
        )

        return Line.search(
            domain,
            order=", ".join(
                order_parts
            ),
            limit=limit,
        )

    # ============================================================
    # PLANNER ACTIONS
    # ============================================================

    def _planner_actions(
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

        maintenance_enabled = self._safe_bool(
            rental,
            "control_mantenimiento",
        )

        has_date = bool(
            self._field(
                rental,
                "fecha_recurrente",
                False,
            )
        )

        has_district = bool(
            self._safe_string(
                rental,
                "distrito",
            )
        )

        active_plan = self._find_active_plan(
            rental
        ) if has_date else False

        return {
            "edit": can_write,
            "detect_zone": bool(
                can_write
                and has_district
                and self._method_exists(
                    rental,
                    "action_detectar_zona_mantenimiento",
                )
            ),
            "create_line": bool(
                can_write
                and maintenance_enabled
                and has_date
                and active_plan
                and self._method_exists(
                    rental,
                    "action_crear_linea_planificador_activo",
                )
            ),
            "auto_schedule": bool(
                can_write
                and maintenance_enabled
                and has_date
                and active_plan
                and self._method_exists(
                    rental,
                    "action_auto_programar_mantenimiento",
                )
            ),
            "view_lines": self._model_available(
                self.LINE_MODEL
            ),
        }

    # ============================================================
    # MAIN PAYLOAD
    # ============================================================

    def _planner_payload(
        self,
        rental,
        user,
    ):
        active_plan = False

        if self._field(
            rental,
            "fecha_recurrente",
            False,
        ):
            try:
                active_plan = self._find_active_plan(
                    rental
                )
            except Exception:
                active_plan = False

        latest_line = self._field(
            rental,
            "ultima_linea_planificador_id",
            False,
        )

        return {
            **self._serialize_rental_planner(
                rental
            ),
            "maintenance_enabled": self._safe_bool(
                rental,
                "control_mantenimiento",
            ),
            "ideal_date": self._safe_date_field(
                rental,
                "fecha_recurrente",
            ),
            "district": self._safe_string(
                rental,
                "distrito",
            ),
            "active_plan": self._serialize_plan(
                active_plan
            ),
            "latest_line": (
                self._serialize_line(
                    latest_line,
                    user,
                    full=True,
                )
                if latest_line
                else False
            ),
            "actions": self._planner_actions(
                rental,
                user,
            ),
            "catalogs": {
                "zones": self._planner_zones(),
                "technicians": self._planner_technicians(
                    rental
                ),
            },
        }

    # ============================================================
    # GET PLANNER
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/planner",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_planner_get(
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
                    "planner": self._planner_payload(
                        rental,
                        user,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando planificador alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # UPDATE SETTINGS
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/planner",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def rental_planner_update(
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

            write_error = self._require_rental_write_access(
                rental,
                user,
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

            values = self._prepare_planner_values(
                rental,
                data,
            )

            if not values:
                return self._json_response(
                    {
                        "success": True,
                        "message": (
                            "No se recibieron cambios del planificador."
                        ),
                        "planner": self._planner_payload(
                            rental,
                            user,
                        ),
                    }
                )

            rental.write(
                values
            )

            rental.invalidate_recordset()

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s actualizó "
                    "la configuración del planificador (%s)."
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
                        "Configuración del planificador guardada."
                    ),
                    "changed_fields": sorted(
                        values.keys()
                    ),
                    "planner": self._planner_payload(
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
                    "code": "RENTAL_PLANNER_UPDATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error actualizando planificador alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # DETECT ZONE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/planner/detect-zone",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_planner_detect_zone(
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

            write_error = self._require_rental_write_access(
                rental,
                user,
            )

            if write_error:
                return write_error

            if not self._method_exists(
                rental,
                "action_detectar_zona_mantenimiento",
            ):
                raise UserError(
                    "La detección automática de zona no está disponible."
                )

            if not self._safe_string(
                rental,
                "distrito",
            ):
                raise UserError(
                    "La máquina no tiene distrito definido."
                )

            rental.action_detectar_zona_mantenimiento()

            rental.invalidate_recordset()

            zone = self._field(
                rental,
                "zona_mantenimiento_id",
                False,
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Zona de mantenimiento detectada."
                    ),
                    "zone": self._serialize_zone(
                        zone
                    ),
                    "planner": self._planner_payload(
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
                    "code": "RENTAL_PLANNER_ZONE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error detectando zona alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # CREATE / REUSE LINE
    # ============================================================

    def _extract_action_res_id(
        self,
        action,
    ):
        if (
            isinstance(
                action,
                dict,
            )
            and action.get(
                "res_id"
            )
        ):
            try:
                return int(
                    action[
                        "res_id"
                    ]
                )
            except Exception:
                return False

        return False

    @http.route(
        "/api/app/rentals/<int:rental_id>/planner/create-line",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_planner_create_line(
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

            write_error = self._require_rental_write_access(
                rental,
                user,
            )

            if write_error:
                return write_error

            if not self._method_exists(
                rental,
                "action_crear_linea_planificador_activo",
            ):
                raise UserError(
                    "La creación de línea del planificador "
                    "no está disponible."
                )

            action = rental.action_crear_linea_planificador_activo()

            line_id = self._extract_action_res_id(
                action
            )

            line = (
                self._get_line(
                    rental,
                    line_id,
                )
                if line_id
                else False
            )

            rental.invalidate_recordset()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Línea de planificación preparada."
                    ),
                    "line": (
                        self._serialize_line(
                            line,
                            user,
                            full=True,
                        )
                        if line
                        else False
                    ),
                    "planner": self._planner_payload(
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
                    "code": "RENTAL_PLANNER_CREATE_LINE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error creando línea planificador alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # AUTO SCHEDULE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/planner/auto-schedule",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_planner_auto_schedule(
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

            write_error = self._require_rental_write_access(
                rental,
                user,
            )

            if write_error:
                return write_error

            if not self._method_exists(
                rental,
                "action_auto_programar_mantenimiento",
            ):
                raise UserError(
                    "La auto-programación no está disponible."
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
                            "¿Buscar automáticamente un horario y "
                            "asignar técnicos disponibles?"
                        ),
                        "requires_confirmation": True,
                    },
                    status=409,
                )

            action = rental.action_auto_programar_mantenimiento()

            line_id = self._extract_action_res_id(
                action
            )

            line = (
                self._get_line(
                    rental,
                    line_id,
                )
                if line_id
                else self._field(
                    rental,
                    "ultima_linea_planificador_id",
                    False,
                )
            )

            rental.invalidate_recordset()

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s ejecutó "
                    "auto-programación de mantenimiento."
                    % user.name
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Auto-programación ejecutada."
                    ),
                    "line": (
                        self._serialize_line(
                            line,
                            user,
                            full=True,
                        )
                        if line
                        else False
                    ),
                    "planner": self._planner_payload(
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
                    "code": "RENTAL_PLANNER_AUTO_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error auto-programando alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # LINES LIST
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/planner/lines",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_planner_lines(
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

            limit = self._positive_int(
                self._query_arg(
                    "limit",
                    200,
                ),
                200,
                minimum=1,
                maximum=500,
            )

            lines = self._planner_lines(
                rental,
                limit=limit,
            )

            return self._json_response(
                {
                    "success": True,
                    "total": len(
                        lines
                    ),
                    "items": [
                        self._serialize_line(
                            line,
                            user,
                        )
                        for line in lines
                    ],
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error listando líneas planificador alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # LINE DETAIL
    # ============================================================

    @http.route(
        (
            "/api/app/rentals/<int:rental_id>"
            "/planner/lines/<int:line_id>"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_planner_line_detail(
        self,
        rental_id,
        line_id,
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

            line = self._get_line(
                rental,
                line_id,
            )

            if not line:
                return self._json_response(
                    {
                        "success": False,
                        "code": "PLANNER_LINE_NOT_FOUND",
                        "message": (
                            "La línea de planificación no existe "
                            "o no pertenece a esta máquina."
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "line": self._serialize_line(
                        line,
                        user,
                        full=True,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                (
                    "Error cargando línea planificador "
                    "rental=%s line=%s."
                ),
                rental_id,
                line_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # LINE ACTION
    # ============================================================

    @http.route(
        (
            "/api/app/rentals/<int:rental_id>"
            "/planner/lines/<int:line_id>/action"
        ),
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_planner_line_action(
        self,
        rental_id,
        line_id,
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

            write_error = self._require_rental_write_access(
                rental,
                user,
            )

            if write_error:
                return write_error

            line = self._get_line(
                rental,
                line_id,
                require_write=True,
            )

            if not line:
                return self._json_response(
                    {
                        "success": False,
                        "code": "PLANNER_LINE_NOT_FOUND",
                        "message": (
                            "La línea de planificación no existe "
                            "o no pertenece a esta máquina."
                        ),
                    },
                    status=404,
                )

            data = self._json_body()

            action_key = str(
                data.get(
                    "action"
                )
                or ""
            ).strip()

            if action_key not in self.LINE_ACTION_METHODS:
                raise UserError(
                    "La acción solicitada no está permitida."
                )

            method_name = self._resolve_line_action_method(
                line,
                action_key,
            )

            if not method_name:
                return self._json_response(
                    {
                        "success": False,
                        "code": "PLANNER_LINE_ACTION_UNAVAILABLE",
                        "message": (
                            "La acción no está implementada "
                            "en esta versión del planificador."
                        ),
                        "action": action_key,
                    },
                    status=501,
                )

            actions = self._line_actions(
                line,
                user,
            )

            if not actions.get(
                action_key,
                {}
            ).get(
                "available"
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "PLANNER_LINE_ACTION_NOT_ALLOWED",
                        "message": (
                            "La acción no está disponible "
                            "para el estado actual de la planificación."
                        ),
                        "action": action_key,
                    },
                    status=409,
                )

            if (
                action_key
                in self.DESTRUCTIVE_LINE_ACTIONS
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
                            "¿Confirmar la acción '%s' "
                            "sobre esta planificación?"
                            % action_key
                        ),
                        "action": action_key,
                        "requires_confirmation": True,
                    },
                    status=409,
                )

            method = getattr(
                line,
                method_name
            )

            result = method()

            line.invalidate_recordset()
            rental.invalidate_recordset()

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s ejecutó "
                    "la acción de planificación '%s' "
                    "sobre la línea %s."
                    % (
                        user.name,
                        action_key,
                        line.id,
                    )
                ),
            )

            action_res_id = self._extract_action_res_id(
                result
            )

            related_line = False

            if action_res_id:
                related_line = self._get_line(
                    rental,
                    action_res_id,
                )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Acción del planificador ejecutada."
                    ),
                    "action": action_key,
                    "line": self._serialize_line(
                        line,
                        user,
                        full=True,
                    ),
                    "related_line": (
                        self._serialize_line(
                            related_line,
                            user,
                            full=True,
                        )
                        if related_line
                        and related_line.id
                        != line.id
                        else False
                    ),
                    "planner": self._planner_payload(
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
                    "code": "RENTAL_PLANNER_LINE_ACTION_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                (
                    "Error acción línea planificador "
                    "rental=%s line=%s."
                ),
                rental_id,
                line_id,
            )

            return self._error_response(
                exc
            )
