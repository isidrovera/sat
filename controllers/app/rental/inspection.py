# -*- coding: utf-8 -*-

"""
Inspección previa a instalación para Flutter - módulo Alquiler.

Endpoints:
    GET    /api/app/rentals/<id>/inspection
    POST   /api/app/rentals/<id>/inspection/send
    POST   /api/app/rentals/<id>/inspection/recalculate

    GET    /api/app/rentals/<id>/inspection/results
    GET    /api/app/rentals/<id>/inspection/results/<result_id>
    PATCH  /api/app/rentals/<id>/inspection/results/<result_id>

    GET    /api/app/rentals/<id>/inspection/link

Objetivos:
- exponer el flujo real de inspección existente en Odoo;
- reutilizar `action_enviar_inspeccion()` del modelo alquiler;
- reutilizar `wizard.enviar.inspeccion.action_enviar()`;
- NO duplicar el mecanismo de correo;
- listar y consultar `inspeccion.resultado`;
- permitir correcciones administrativas de resultados respetando ACL;
- recalcular el estado de instalación usando `_compute_apto()`;
- devolver siempre el estado actualizado del equipo.

MODELOS / MÉTODOS REALES
========================
alquiler:
    resultado_inspeccion -> One2many('inspeccion.resultado', 'alquiler_id')
    token
    _generar_url_inspeccion()
    _compute_apto()
    action_view_inspecciones()
    action_enviar_inspeccion()

wizard.enviar.inspeccion:
    correo
    alquiler_id
    action_enviar()

ESTADO DE INSTALACIÓN
=====================
    pendiente
    apto
    requiere_adecuacion
    no_apto

La lógica de aptitud se mantiene en el modelo `alquiler`; este controlador
no vuelve a implementar los criterios.

SEGURIDAD
=========
- Solo usuarios del módulo Alquiler pueden acceder.
- Las escrituras respetan ACL/record rules.
- El resultado no se elimina desde esta API.
- Campos relacionales críticos no se pueden reasignar por PATCH.
- No se expone ninguna configuración interna de correo.
"""

import logging
import re

from odoo import fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .base import RentalBaseController


_logger = logging.getLogger(__name__)


class RentalInspectionController(RentalBaseController):

    # ============================================================
    # MODELOS
    # ============================================================

    RESULT_MODEL = "inspeccion.resultado"
    WIZARD_MODEL = "wizard.enviar.inspeccion"

    ALLOWED_RENTAL_STATES_TO_SEND = (
        "lista",
        "inspeccion",
        "subsanacion",
    )

    # ============================================================
    # CAMPOS DE RESULTADO EDITABLES
    # ============================================================

    """
    La instalación ha tenido distintas versiones del modelo
    inspeccion.resultado. En vez de asumir que todos estos campos
    siempre existen, solo se permite escribir los que realmente estén
    presentes en `_fields`.

    No se permite modificar:
        alquiler_id
        create_uid
        write_uid
        create_date
        write_date
        id
    """

    RESULT_EDITABLE_FIELD_CANDIDATES = {
        # Fecha / identificación
        "fecha",

        # Espacio físico
        "espacio",
        "ancho_pasillo",
        "altura",
        "ubicacion",
        "ubicacion_equipo",
        "observaciones_espacio",

        # Electricidad
        "punto_corriente",
        "voltaje",
        "tipo_tomacorriente",
        "tiene_estabilizador",
        "tiene_ups",
        "observaciones_electricas",

        # Red
        "punto_red",
        "wifi",
        "tipo_red",
        "ip_fija",
        "ip",
        "gateway",
        "mascara",
        "dns",
        "nombre_red",
        "ssid",
        "observaciones_red",

        # PCs
        "cantidad_windows",
        "cantidad_mac",
        "cantidad_linux",
        "version_windows",
        "version_mac",
        "version_linux",

        # Contactos
        "contacto",
        "contacto_responsable",
        "telefono",
        "celular",
        "correo",
        "email",
        "cargo",

        # Otros
        "observaciones",
        "comentarios",
        "notas",
        "responsable",
        "firma",
    }

    PROTECTED_RESULT_FIELDS = {
        "id",
        "alquiler_id",
        "create_uid",
        "write_uid",
        "create_date",
        "write_date",
    }

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/rentals/<int:rental_id>/inspection",
            "/api/app/rentals/<int:rental_id>/inspection/send",
            "/api/app/rentals/<int:rental_id>/inspection/recalculate",
            "/api/app/rentals/<int:rental_id>/inspection/results",
            "/api/app/rentals/<int:rental_id>/inspection/results/<int:result_id>",
            "/api/app/rentals/<int:rental_id>/inspection/link",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def rental_inspection_options(
        self,
        rental_id=None,
        result_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # GENERIC HELPERS
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

    def _result_model(self):
        if not self._model_available(
            self.RESULT_MODEL
        ):
            raise UserError(
                "El modelo de resultados de inspección "
                "no está disponible."
            )

        return request.env[
            self.RESULT_MODEL
        ]

    def _wizard_model(self):
        if not self._model_available(
            self.WIZARD_MODEL
        ):
            raise UserError(
                "El wizard de envío de inspección "
                "no está disponible."
            )

        return request.env[
            self.WIZARD_MODEL
        ]

    # ============================================================
    # EMAIL VALIDATION
    # ============================================================

    def _normalize_email(
        self,
        value,
    ):
        if value in (
            None,
            False,
            "",
        ):
            return False

        email = str(
            value
        ).strip()

        if len(
            email
        ) > 320:
            raise UserError(
                "El correo electrónico es demasiado largo."
            )

        # Validación simple para evitar errores obvios.
        if not re.match(
            r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
            email,
        ):
            raise UserError(
                "El correo electrónico no tiene un formato válido."
            )

        return email

    # ============================================================
    # RESULT ACCESS
    # ============================================================

    def _get_result(
        self,
        rental,
        result_id,
        *,
        require_write=False,
    ):
        Result = self._result_model()

        try:
            result = Result.browse(
                int(
                    result_id
                )
            ).exists()

            if not result:
                return Result.browse()

            if (
                "alquiler_id"
                not in result._fields
                or not result.alquiler_id
                or result.alquiler_id.id
                != rental.id
            ):
                return Result.browse()

            if hasattr(
                result,
                "check_access",
            ):
                result.check_access(
                    "write"
                    if require_write
                    else "read"
                )

            return result

        except (
            AccessError,
            ValueError,
            TypeError,
        ):
            return Result.browse()

    # ============================================================
    # GENERIC FIELD SERIALIZATION
    # ============================================================

    def _serialize_value(
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
            "many2many",
            "one2many",
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
    # RESULT SERIALIZER
    # ============================================================

    def _serialize_result(
        self,
        result,
        user,
        *,
        full=False,
    ):
        if not result:
            return False

        data = {
            "id": result.id,
            "display_name": (
                result.display_name
                or ""
            ),
        }

        preferred_fields = (
            "alquiler_id",
            "fecha",

            "espacio",
            "ancho_pasillo",
            "altura",
            "ubicacion",
            "ubicacion_equipo",

            "punto_corriente",
            "voltaje",
            "tipo_tomacorriente",
            "tiene_estabilizador",
            "tiene_ups",

            "punto_red",
            "wifi",
            "tipo_red",
            "ip_fija",
            "ip",
            "gateway",
            "mascara",
            "dns",
            "nombre_red",
            "ssid",

            "cantidad_windows",
            "cantidad_mac",
            "cantidad_linux",

            "contacto",
            "contacto_responsable",
            "telefono",
            "celular",
            "correo",
            "email",
            "cargo",

            "observaciones",
            "comentarios",
            "notas",

            "create_date",
            "write_date",
        )

        for field_name in preferred_fields:
            if field_name not in result._fields:
                continue

            try:
                data[
                    field_name
                ] = self._serialize_value(
                    result,
                    field_name,
                )

                if (
                    getattr(
                        result._fields[
                            field_name
                        ],
                        "type",
                        False,
                    )
                    == "selection"
                ):
                    data[
                        "%s_label"
                        % field_name
                    ] = self._selection_label_safe(
                        result,
                        field_name,
                    )
            except Exception:
                continue

        if full:
            extras = {}

            excluded = set(
                preferred_fields
            )

            excluded.update(
                {
                    "__last_update",
                    "message_ids",
                    "message_follower_ids",
                    "activity_ids",
                    "message_partner_ids",
                }
            )

            for field_name, field in result._fields.items():
                if (
                    field_name in excluded
                    or field_name.startswith(
                        "message_"
                    )
                    or field_name.startswith(
                        "activity_"
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
                    extras[
                        field_name
                    ] = self._serialize_value(
                        result,
                        field_name,
                    )

                    if field_type == "selection":
                        extras[
                            "%s_label"
                            % field_name
                        ] = self._selection_label_safe(
                            result,
                            field_name,
                        )

                except Exception:
                    continue

            data[
                "extra"
            ] = extras

        data[
            "field_permissions"
        ] = self._result_field_permissions(
            result,
            user,
        )

        return data

    # ============================================================
    # RESULT FIELD PERMISSIONS
    # ============================================================

    def _result_field_permissions(
        self,
        result,
        user,
    ):
        can_write = bool(
            self._is_system_user(
                user
            )
            or self._model_has_access(
                self.RESULT_MODEL,
                "write",
            )
        )

        result_permissions = {}

        for field_name in sorted(
            self.RESULT_EDITABLE_FIELD_CANDIDATES
        ):
            if field_name not in result._fields:
                continue

            field = result._fields[
                field_name
            ]

            readonly = bool(
                getattr(
                    field,
                    "readonly",
                    False,
                )
            )

            computed = bool(
                getattr(
                    field,
                    "compute",
                    False,
                )
            )

            editable = bool(
                can_write
                and not readonly
                and not computed
            )

            result_permissions[
                field_name
            ] = {
                "editable": editable,
                "type": getattr(
                    field,
                    "type",
                    False,
                ),
                "readonly": readonly,
                "computed": computed,
            }

        return result_permissions

    # ============================================================
    # RESULT NORMALIZATION
    # ============================================================

    def _normalize_result_field(
        self,
        result,
        field_name,
        value,
    ):
        field = result._fields.get(
            field_name
        )

        if not field:
            raise UserError(
                "El campo %s no existe."
                % field_name
            )

        if (
            getattr(
                field,
                "readonly",
                False,
            )
            or getattr(
                field,
                "compute",
                False,
            )
        ):
            raise UserError(
                "El campo %s no se puede modificar."
                % field_name
            )

        field_type = getattr(
            field,
            "type",
            False,
        )

        if field_type == "boolean":
            return self._truthy(
                value
            )

        if field_type == "integer":
            if value in (
                None,
                "",
                False,
            ):
                return 0

            try:
                number = int(
                    value
                )
            except Exception:
                raise UserError(
                    "El campo %s debe ser un entero."
                    % field_name
                )

            if (
                field_name.startswith(
                    "cantidad_"
                )
                and number < 0
            ):
                raise UserError(
                    "Las cantidades no pueden ser negativas."
                )

            return number

        if field_type in (
            "float",
            "monetary",
        ):
            if value in (
                None,
                "",
                False,
            ):
                return 0.0

            try:
                number = float(
                    value
                )
            except Exception:
                raise UserError(
                    "El campo %s debe ser numérico."
                    % field_name
                )

            if (
                field_name
                in (
                    "espacio",
                    "ancho_pasillo",
                    "altura",
                )
                and number < 0
            ):
                raise UserError(
                    "%s no puede ser negativo."
                    % field_name
                )

            return number

        if field_type == "date":
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
                    "La fecha no es válida."
                )

        if field_type == "datetime":
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
                    "La fecha/hora no es válida."
                )

        if field_type == "selection":
            if value in (
                None,
                "",
                False,
            ):
                return False

            options = self._selection_options_safe(
                result,
                field_name,
            )

            valid = {
                item[
                    "value"
                ]
                for item in options
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

        if field_type in (
            "char",
            "text",
            "html",
        ):
            if value in (
                None,
                False,
            ):
                return False

            return str(
                value
            )

        # No habilitamos edición de relaciones desde este endpoint.
        if field_type in (
            "many2one",
            "many2many",
            "one2many",
        ):
            raise UserError(
                "El campo relacional %s no puede editarse "
                "desde esta operación."
                % field_name
            )

        return value

    def _prepare_result_values(
        self,
        result,
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

        for field_name, raw_value in data.items():
            if (
                field_name
                in self.PROTECTED_RESULT_FIELDS
            ):
                continue

            if (
                field_name
                not in self.RESULT_EDITABLE_FIELD_CANDIDATES
            ):
                continue

            if field_name not in result._fields:
                continue

            values[
                field_name
            ] = self._normalize_result_field(
                result,
                field_name,
                raw_value,
            )

        return values

    # ============================================================
    # RECALCULATE
    # ============================================================

    def _recalculate_installation(
        self,
        rental,
    ):
        method = getattr(
            rental,
            "_compute_apto",
            None,
        )

        if not callable(
            method
        ):
            raise UserError(
                "La evaluación de aptitud para instalación "
                "no está disponible."
            )

        method()

        rental.invalidate_recordset()

        return {
            "fit": self._safe_bool(
                rental,
                "apto_instalacion",
            ),
            "state": self._safe_string(
                rental,
                "estado_instalacion",
                "pendiente",
            ),
            "state_label": self._selection_label_safe(
                rental,
                "estado_instalacion",
            ),
            "requires_adaptation": self._safe_bool(
                rental,
                "requiere_adecuacion",
            ),
            "notes": self._safe_string(
                rental,
                "notas_adecuacion",
            ),
        }

    # ============================================================
    # INSPECTION URL
    # ============================================================

    def _inspection_url(
        self,
        rental,
        *,
        create_token=False,
    ):
        if create_token:
            generator = getattr(
                rental,
                "_generar_url_inspeccion",
                None,
            )

            if not callable(
                generator
            ):
                raise UserError(
                    "La generación del enlace de inspección "
                    "no está disponible."
                )

            return generator()

        token = self._safe_string(
            rental,
            "token",
        )

        if not token:
            return False

        base_url = request.env[
            "ir.config_parameter"
        ].sudo().get_param(
            "web.base.url"
        )

        if not base_url:
            return False

        return "%s/inspeccion/%s" % (
            base_url.rstrip(
                "/"
            ),
            token,
        )

    # ============================================================
    # RESULTS
    # ============================================================

    def _inspection_results(
        self,
        rental,
        *,
        limit=200,
    ):
        Result = self._result_model()

        if "alquiler_id" not in Result._fields:
            return Result.browse()

        domain = [
            (
                "alquiler_id",
                "=",
                rental.id,
            )
        ]

        order = []

        if "fecha" in Result._fields:
            order.append(
                "fecha desc"
            )

        if "create_date" in Result._fields:
            order.append(
                "create_date desc"
            )

        order.append(
            "id desc"
        )

        return Result.search(
            domain,
            order=", ".join(
                order
            ),
            limit=limit,
        )

    def _latest_result(
        self,
        rental,
    ):
        results = self._inspection_results(
            rental,
            limit=1,
        )

        return (
            results[
                0
            ]
            if results
            else False
        )

    # ============================================================
    # ACTIONS / PAYLOAD
    # ============================================================

    def _inspection_actions(
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

        rental_state = self._safe_string(
            rental,
            "estado_alquiler_id",
        )

        result_model_available = self._model_available(
            self.RESULT_MODEL
        )

        wizard_available = self._model_available(
            self.WIZARD_MODEL
        )

        return {
            "send": bool(
                can_write
                and rental_state
                in self.ALLOWED_RENTAL_STATES_TO_SEND
                and wizard_available
                and self._method_exists(
                    rental,
                    "action_enviar_inspeccion",
                )
            ),
            "view_results": result_model_available,
            "recalculate": bool(
                can_write
                and self._method_exists(
                    rental,
                    "_compute_apto",
                )
            ),
            "generate_link": bool(
                can_write
                and self._method_exists(
                    rental,
                    "_generar_url_inspeccion",
                )
            ),
            # La aprobación para instalar sigue perteneciendo a state.py
            # y continúa siendo solo base.group_system.
            "approve_installation": bool(
                self._is_system_user(
                    user
                )
                and rental_state
                in (
                    "inspeccion",
                    "subsanacion",
                )
                and self._method_exists(
                    rental,
                    "action_estado_por_instalar",
                )
            ),
        }

    def _inspection_payload(
        self,
        rental,
        user,
    ):
        latest = False

        if self._model_available(
            self.RESULT_MODEL
        ):
            try:
                latest = self._latest_result(
                    rental
                )
            except Exception:
                latest = False

        return {
            "equipment_state": {
                "value": self._safe_string(
                    rental,
                    "estado_alquiler_id",
                ),
                "label": self._selection_label_safe(
                    rental,
                    "estado_alquiler_id",
                ),
            },
            "installation": {
                "fit": self._safe_bool(
                    rental,
                    "apto_instalacion",
                ),
                "state": self._safe_string(
                    rental,
                    "estado_instalacion",
                    "pendiente",
                ),
                "state_label": self._selection_label_safe(
                    rental,
                    "estado_instalacion",
                ),
                "requires_adaptation": self._safe_bool(
                    rental,
                    "requiere_adecuacion",
                ),
                "adaptation_notes": self._safe_string(
                    rental,
                    "notas_adecuacion",
                ),
            },
            "inspection_count": self._safe_int(
                rental,
                "inspeccion_count",
            ),
            "token_exists": bool(
                self._safe_string(
                    rental,
                    "token",
                )
            ),
            "url": self._inspection_url(
                rental,
                create_token=False,
            ),
            "latest_result": (
                self._serialize_result(
                    latest,
                    user,
                    full=True,
                )
                if latest
                else False
            ),
            "actions": self._inspection_actions(
                rental,
                user,
            ),
            "installation_state_options": (
                self._selection_options_safe(
                    rental,
                    "estado_instalacion",
                )
            ),
        }

    # ============================================================
    # GET MAIN
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/inspection",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_inspection_get(
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
                    "inspection": self._inspection_payload(
                        rental,
                        user,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando inspección alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # SEND
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/inspection/send",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_inspection_send(
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

            current_state = self._safe_string(
                rental,
                "estado_alquiler_id",
            )

            if current_state not in self.ALLOWED_RENTAL_STATES_TO_SEND:
                raise UserError(
                    "Solo se puede enviar inspección cuando el equipo "
                    "está Lista, En inspección o Esperando subsanación."
                )

            if not self._method_exists(
                rental,
                "action_enviar_inspeccion",
            ):
                raise UserError(
                    "El flujo de envío de inspección no está disponible."
                )

            data = self._json_body()

            email = self._normalize_email(
                (
                    data.get(
                        "email"
                    )
                    or data.get(
                        "correo"
                    )
                    or self._safe_string(
                        rental,
                        "correo_",
                    )
                )
            )

            if not email:
                raise UserError(
                    "Debe indicar un correo para enviar la inspección."
                )

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
                            "¿Enviar la inspección a %s?"
                            % email
                        ),
                        "requires_confirmation": True,
                        "email": email,
                    },
                    status=409,
                )

            # 1) Ejecutar el método real del equipo.
            # Este método valida el estado y, cuando corresponde,
            # cambia lista/subsanacion -> inspeccion.
            action = rental.action_enviar_inspeccion()

            rental.invalidate_recordset()

            # 2) Confirmar que el método realmente abrió el wizard esperado.
            if (
                not isinstance(
                    action,
                    dict,
                )
                or action.get(
                    "res_model"
                )
                != self.WIZARD_MODEL
            ):
                raise UserError(
                    "Odoo no devolvió el wizard esperado "
                    "para enviar la inspección."
                )

            Wizard = self._wizard_model()

            wizard_values = {
                "alquiler_id": rental.id,
                "correo": email,
            }

            # Mantener solo campos reales.
            wizard_values = {
                key: value
                for key, value
                in wizard_values.items()
                if key in Wizard._fields
            }

            if (
                "alquiler_id"
                not in wizard_values
                or "correo"
                not in wizard_values
            ):
                raise UserError(
                    "El wizard de inspección no tiene "
                    "los campos esperados."
                )

            wizard = Wizard.create(
                wizard_values
            )

            send_method = getattr(
                wizard,
                "action_enviar",
                None,
            )

            if not callable(
                send_method
            ):
                raise UserError(
                    "El wizard no implementa action_enviar()."
                )

            result = send_method()

            rental.invalidate_recordset()

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s envió "
                    "la inspección a %s."
                    % (
                        user.name,
                        email,
                    )
                ),
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Inspección enviada correctamente."
                    ),
                    "email": email,
                    "url": self._inspection_url(
                        rental,
                        create_token=False,
                    ),
                    "model_result": bool(
                        result
                    ),
                    "inspection": self._inspection_payload(
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
                    "code": "RENTAL_INSPECTION_SEND_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error enviando inspección alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # LINK
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/inspection/link",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_inspection_link(
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

            create = self._truthy(
                self._query_arg(
                    "create",
                    False,
                )
            )

            if create:
                write_rental = self._get_rental(
                    rental_id,
                    user,
                    require_write=True,
                )

                if not write_rental:
                    return self._rental_not_found_response()

                write_error = self._require_rental_write_access(
                    write_rental,
                    user,
                )

                if write_error:
                    return write_error

                rental = write_rental

            url = self._inspection_url(
                rental,
                create_token=create,
            )

            if not url:
                return self._json_response(
                    {
                        "success": False,
                        "code": "INSPECTION_LINK_NOT_GENERATED",
                        "message": (
                            "El equipo todavía no tiene un enlace "
                            "de inspección generado."
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "url": url,
                    "token_exists": True,
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
                    "code": "RENTAL_INSPECTION_LINK_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error enlace inspección alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # RECALCULATE
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/inspection/recalculate",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def rental_inspection_recalculate(
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

            installation = self._recalculate_installation(
                rental
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Estado de instalación recalculado."
                    ),
                    "installation": installation,
                    "inspection": self._inspection_payload(
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
                    "code": "RENTAL_INSPECTION_RECALCULATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                "Error recalculando inspección alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # RESULT LIST
    # ============================================================

    @http.route(
        "/api/app/rentals/<int:rental_id>/inspection/results",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_inspection_results(
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

            results = self._inspection_results(
                rental,
                limit=limit,
            )

            return self._json_response(
                {
                    "success": True,
                    "count": len(
                        results
                    ),
                    "installation": {
                        "fit": self._safe_bool(
                            rental,
                            "apto_instalacion",
                        ),
                        "state": self._safe_string(
                            rental,
                            "estado_instalacion",
                            "pendiente",
                        ),
                        "state_label": (
                            self._selection_label_safe(
                                rental,
                                "estado_instalacion",
                            )
                        ),
                        "requires_adaptation": self._safe_bool(
                            rental,
                            "requiere_adecuacion",
                        ),
                        "adaptation_notes": self._safe_string(
                            rental,
                            "notas_adecuacion",
                        ),
                    },
                    "items": [
                        self._serialize_result(
                            item,
                            user,
                        )
                        for item in results
                    ],
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error listando inspecciones alquiler id=%s.",
                rental_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # RESULT DETAIL
    # ============================================================

    @http.route(
        (
            "/api/app/rentals/<int:rental_id>"
            "/inspection/results/<int:result_id>"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_inspection_result_detail(
        self,
        rental_id,
        result_id,
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

            result = self._get_result(
                rental,
                result_id,
            )

            if not result:
                return self._json_response(
                    {
                        "success": False,
                        "code": "INSPECTION_RESULT_NOT_FOUND",
                        "message": (
                            "La inspección no existe o no pertenece "
                            "a esta máquina."
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "result": self._serialize_result(
                        result,
                        user,
                        full=True,
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                (
                    "Error detalle inspección "
                    "rental=%s result=%s."
                ),
                rental_id,
                result_id,
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # RESULT UPDATE
    # ============================================================

    @http.route(
        (
            "/api/app/rentals/<int:rental_id>"
            "/inspection/results/<int:result_id>"
        ),
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def rental_inspection_result_update(
        self,
        rental_id,
        result_id,
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

            result = self._get_result(
                rental,
                result_id,
                require_write=True,
            )

            if not result:
                return self._json_response(
                    {
                        "success": False,
                        "code": "INSPECTION_RESULT_NOT_FOUND",
                        "message": (
                            "La inspección no existe o no pertenece "
                            "a esta máquina."
                        ),
                    },
                    status=404,
                )

            data = self._json_body()

            values = self._prepare_result_values(
                result,
                data,
            )

            if not values:
                return self._json_response(
                    {
                        "success": True,
                        "message": (
                            "No se recibieron cambios válidos."
                        ),
                        "result": self._serialize_result(
                            result,
                            user,
                            full=True,
                        ),
                    }
                )

            result.write(
                values
            )

            result.invalidate_recordset()

            installation = self._recalculate_installation(
                rental
            )

            self._post_app_message(
                rental,
                (
                    "📱 Flutter Alquiler: %s corrigió "
                    "la inspección #%s (%s)."
                    % (
                        user.name,
                        result.id,
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
                        "Resultado de inspección actualizado."
                    ),
                    "changed_fields": sorted(
                        values.keys()
                    ),
                    "result": self._serialize_result(
                        result,
                        user,
                        full=True,
                    ),
                    "installation": installation,
                    "inspection": self._inspection_payload(
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
                    "code": "RENTAL_INSPECTION_RESULT_UPDATE_ERROR",
                    "message": str(
                        exc
                    ),
                },
                status=400,
            )

        except Exception as exc:
            _logger.exception(
                (
                    "Error actualizando inspección "
                    "rental=%s result=%s."
                ),
                rental_id,
                result_id,
            )

            return self._error_response(
                exc
            )
