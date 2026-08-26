# -*- coding: utf-8 -*-

"""
Base común para la API Flutter del módulo de Alquiler.

IMPORTANTE
==========
Este archivo NO expone rutas HTTP.

Su responsabilidad es centralizar, una sola vez:

- seguridad del módulo Alquiler;
- detección de administrador de sistema;
- detección del grupo Área alquiler;
- acceso al modelo `alquiler`;
- validaciones reutilizables;
- helpers seguros para campos opcionales;
- opciones Selection;
- permisos/capacidades de cada máquina;
- serialización completa de una máquina.

Los controladores de:
    list.py
    detail.py
    state.py
    maintenance.py
    planner.py
    geo.py
    toner.py
    blocking.py
    related.py
    qr.py

deben heredar de RentalBaseController y reutilizar esta lógica.

No duplicar permisos ni serializadores comunes en otros archivos.
"""

import logging
from datetime import date, datetime

from markupsafe import Markup

from odoo import fields
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request

from ..base import AppBaseController


_logger = logging.getLogger(__name__)


class RentalBaseController(AppBaseController):
    """Base común de todos los endpoints Flutter de Alquiler."""

    # ============================================================
    # MODELO / GRUPOS
    # ============================================================

    RENTAL_MODEL = "alquiler"

    SYSTEM_GROUP = "base.group_system"
    RENTAL_GROUP = "sat.sat_alquiler_group_user"

    TECHNICAL_GROUP = "sat.sat_tecnica_group_user"
    HEAD_GROUP = "sat.sat_jefes_group_user"
    LOGISTICS_GROUP = "sat.sat_logistica_group_user"
    SALES_GROUP = "sat.Sat_ventas_group_user"

    # ============================================================
    # ESTADOS DEL EQUIPO
    # ============================================================

    RENTAL_STATES = (
        "sin_revisar",
        "revisada",
        "lista",
        "inspeccion",
        "subsanacion",
        "por_instalar",
        "alquilada",
        "con_problemas",
        "partes",
        "externo",
        "vendida",
    )

    BLOCKING_STATES = (
        "activo",
        "suspendido",
        "bloqueado",
        "no_accesible",
        "pendiente_bloqueo",
        "pendiente_desbloqueo",
    )

    MAINTENANCE_STATES = (
        "pendiente",
        "confirmado",
        "reprogramado",
    )

    PLANNING_STATES = (
        "sin_planificar",
        "pendiente",
        "confirmado",
        "programado",
        "sin_cupo",
        "reasignar",
        "ticket_creado",
    )

    # Estados considerados fuera de operación normal.
    NON_OPERATIONAL_STATES = (
        "externo",
        "vendida",
    )

    # ============================================================
    # SEGURIDAD
    # ============================================================

    def _has_group(self, user, xmlid):
        """Comprueba un grupo sin provocar error por XMLID inexistente."""
        if not user or not xmlid:
            return False

        try:
            return bool(user.has_group(xmlid))
        except Exception:
            _logger.exception(
                "No se pudo comprobar el grupo %s para usuario %s.",
                xmlid,
                user.id if user else False,
            )
            return False

    def _is_system_user(self, user):
        """
        Administrador total de Flutter.

        base.group_system siempre tiene alcance global dentro
        del módulo Alquiler de la app.
        """
        if not user:
            return False

        try:
            if request.env.is_superuser():
                return True
        except Exception:
            pass

        return self._has_group(
            user,
            self.SYSTEM_GROUP,
        )

    def _is_rental_group_user(self, user):
        """Usuario perteneciente específicamente al Área alquiler."""
        return self._has_group(
            user,
            self.RENTAL_GROUP,
        )

    def _is_rental_user(self, user):
        """
        Usuario autorizado para entrar al módulo Alquiler de Flutter.

        Alcance actual:
        - Administrador del sistema.
        - Grupo Área alquiler.

        No se concede acceso únicamente por ser usuario interno,
        técnico, ventas o logística.
        """
        return bool(
            self._is_system_user(user)
            or self._is_rental_group_user(user)
        )

    def _rental_access_scope(self, user):
        """Devuelve el alcance funcional que Flutter puede mostrar."""
        if self._is_system_user(user):
            return "system"

        if self._is_rental_group_user(user):
            return "rental"

        return "none"

    def _require_rental_user(self):
        """
        Valida sesión + pertenencia al módulo Alquiler.

        Devuelve:
            (user, False)
        o:
            (user/None, response_error)
        """
        user, error = self._require_user()

        if error:
            return user, error

        if not self._is_rental_user(user):
            return (
                user,
                self._json_response(
                    {
                        "success": False,
                        "code": "RENTAL_ACCESS_DENIED",
                        "message": (
                            "El usuario no tiene acceso al área de Alquiler."
                        ),
                    },
                    status=403,
                ),
            )

        return user, False

    # ============================================================
    # MODELO / RIGHTS
    # ============================================================

    def _rental_model(self):
        """Obtiene el modelo alquiler con el usuario actual."""
        return request.env[
            self.RENTAL_MODEL
        ]

    def _model_has_access(self, model_name, operation):
        """
        Comprueba ACL del modelo sin sudo.

        operation:
            read / write / create / unlink
        """
        try:
            model = request.env[
                model_name
            ]

            return bool(
                model.check_access_rights(
                    operation,
                    raise_exception=False,
                )
            )
        except Exception:
            _logger.exception(
                "No se pudo comprobar acceso %s sobre %s.",
                operation,
                model_name,
            )
            return False

    def _rental_model_access(self, user):
        """
        Capacidades CRUD generales del modelo.

        El administrador conserva alcance funcional total, pero
        se reportan también los ACL reales para diagnóstico/UI.
        """
        is_system = self._is_system_user(user)

        return {
            "read": (
                True
                if is_system
                else self._model_has_access(
                    self.RENTAL_MODEL,
                    "read",
                )
            ),
            "write": (
                True
                if is_system
                else self._model_has_access(
                    self.RENTAL_MODEL,
                    "write",
                )
            ),
            "create": (
                True
                if is_system
                else self._model_has_access(
                    self.RENTAL_MODEL,
                    "create",
                )
            ),
            "unlink": (
                True
                if is_system
                else self._model_has_access(
                    self.RENTAL_MODEL,
                    "unlink",
                )
            ),
        }

    def _get_rental(
        self,
        rental_id,
        user,
        *,
        require_write=False,
    ):
        """
        Obtiene una máquina de alquiler respetando ACL/record rules.

        No utiliza sudo para saltarse seguridad.

        base.group_system tendrá el alcance que ya tenga configurado
        Odoo y, además, el controlador reconoce su rol administrativo.
        """
        if not self._is_rental_user(user):
            return self._rental_model().browse()

        Rental = self._rental_model()

        operation = (
            "write"
            if require_write
            else "read"
        )

        if (
            not self._is_system_user(user)
            and not self._model_has_access(
                self.RENTAL_MODEL,
                operation,
            )
        ):
            return Rental.browse()

        try:
            record = Rental.browse(
                int(rental_id)
            ).exists()

            if not record:
                return Rental.browse()

            # Fuerza lectura bajo el usuario real y sus record rules.
            if hasattr(record, "check_access"):
                record.check_access(
                    operation
                )

            return record

        except (
            AccessError,
            MissingError,
        ):
            return Rental.browse()

        except Exception:
            _logger.exception(
                "Error obteniendo alquiler id=%s usuario=%s.",
                rental_id,
                user.id if user else False,
            )
            return Rental.browse()

    def _rental_not_found_response(self):
        """
        Respuesta indistinguible entre inexistente y sin acceso.

        Evita revelar IDs de registros fuera del alcance.
        """
        return self._json_response(
            {
                "success": False,
                "code": "RENTAL_NOT_FOUND",
                "message": (
                    "La máquina no existe o no tienes acceso a ella."
                ),
            },
            status=404,
        )

    # ============================================================
    # HELPERS DE CAMPOS
    # ============================================================

    def _field_exists(
        self,
        record,
        field_name,
    ):
        return bool(
            record
            and field_name
            and field_name in record._fields
        )

    def _field(
        self,
        record,
        field_name,
        default=False,
    ):
        """
        Lee un campo solo si existe.

        Es fundamental porque `alquiler` está extendido por varios
        archivos y algunas instalaciones pueden no tener todos los
        submódulos cargados temporalmente.
        """
        if not self._field_exists(
            record,
            field_name,
        ):
            return default

        try:
            value = record[
                field_name
            ]

            return (
                value
                if value is not None
                else default
            )
        except Exception:
            return default

    def _safe_bool(
        self,
        record,
        field_name,
        default=False,
    ):
        return bool(
            self._field(
                record,
                field_name,
                default,
            )
        )

    def _safe_int(
        self,
        record,
        field_name,
        default=0,
    ):
        value = self._field(
            record,
            field_name,
            default,
        )

        try:
            return int(
                value or 0
            )
        except Exception:
            return default

    def _safe_float(
        self,
        record,
        field_name,
        default=0.0,
    ):
        value = self._field(
            record,
            field_name,
            default,
        )

        try:
            return float(
                value or 0.0
            )
        except Exception:
            return default

    def _safe_string(
        self,
        record,
        field_name,
        default=False,
    ):
        value = self._field(
            record,
            field_name,
            default,
        )

        if value in (
            None,
            False,
        ):
            return default

        try:
            text = str(
                value
            ).strip()

            return (
                text
                if text
                else default
            )
        except Exception:
            return default

    def _safe_date_value(self, value):
        """Normaliza Date/Datetime a valor serializable por JSON."""
        if not value:
            return False

        if isinstance(
            value,
            datetime,
        ):
            return fields.Datetime.to_string(
                value
            )

        if isinstance(
            value,
            date,
        ):
            return fields.Date.to_string(
                value
            )

        return str(
            value
        )

    def _safe_date_field(
        self,
        record,
        field_name,
    ):
        return self._safe_date_value(
            self._field(
                record,
                field_name,
                False,
            )
        )

    def _safe_many2one(
        self,
        record,
        field_name,
    ):
        value = self._field(
            record,
            field_name,
            False,
        )

        if not value:
            return False

        try:
            return self._many2one(
                value
            )
        except Exception:
            try:
                return {
                    "id": value.id,
                    "name": (
                        value.display_name
                        or value.name
                        or ""
                    ),
                }
            except Exception:
                return False

    def _safe_many2many(
        self,
        record,
        field_name,
    ):
        value = self._field(
            record,
            field_name,
            False,
        )

        if not value:
            return []

        result = []

        try:
            for item in value:
                result.append(
                    self._many2one(
                        item
                    )
                )
        except Exception:
            return []

        return result

    def _selection_label_safe(
        self,
        record,
        field_name,
    ):
        if not self._field_exists(
            record,
            field_name,
        ):
            return False

        try:
            return self._selection_label(
                record,
                field_name,
            )
        except Exception:
            value = self._field(
                record,
                field_name,
                False,
            )

            return value or False

    def _selection_options_safe(
        self,
        model_or_record,
        field_name,
    ):
        """
        Devuelve:
        [
            {"value": "...", "label": "..."},
            ...
        ]

        Compatible con selection estático o callable.
        """
        try:
            field = model_or_record._fields.get(
                field_name
            )

            if not field:
                return []

            selection = field.selection

            if callable(selection):
                selection = selection(
                    model_or_record
                )

            if not selection:
                return []

            return [
                {
                    "value": value,
                    "label": label,
                }
                for value, label in selection
            ]
        except Exception:
            _logger.exception(
                "Error obteniendo opciones %s.%s.",
                getattr(
                    model_or_record,
                    "_name",
                    self.RENTAL_MODEL,
                ),
                field_name,
            )
            return []

    def _method_exists(
        self,
        record,
        method_name,
    ):
        return bool(
            record
            and method_name
            and callable(
                getattr(
                    record,
                    method_name,
                    None,
                )
            )
        )

    # ============================================================
    # HELPERS DE HTML
    # ============================================================

    def _html_json_value(
        self,
        value,
    ):
        """
        Convierte Markup/HTML a string sin alterar su contenido.

        Flutter decidirá si lo representa como HTML o texto.
        """
        if not value:
            return False

        if isinstance(
            value,
            Markup,
        ):
            return str(
                value
            )

        return str(
            value
        )

    # ============================================================
    # USER CONTEXT
    # ============================================================

    def _serialize_rental_user_context(
        self,
        user,
    ):
        access = self._rental_model_access(
            user
        )

        return {
            "id": user.id,
            "name": user.name,
            "login": user.login,
            "scope": self._rental_access_scope(
                user
            ),
            "is_system": self._is_system_user(
                user
            ),
            "is_rental_user": self._is_rental_group_user(
                user
            ),
            "model_access": access,
        }

    # ============================================================
    # IDENTIDAD / RESUMEN
    # ============================================================

    def _serialize_rental_identity(
        self,
        rental,
    ):
        model = self._safe_many2one(
            rental,
            "name",
        )

        return {
            "id": rental.id,
            "display_name": (
                rental.display_name
                or ""
            ),
            "model": model,
            "model_name": (
                model.get("name")
                if model
                else False
            ),
            "brand": self._safe_string(
                rental,
                "marca",
            ),
            "serial": self._safe_string(
                rental,
                "serie",
            ),
            "machine_type": self._safe_string(
                rental,
                "tipo_maquina",
            ),
            "machine_type_code": self._safe_string(
                rental,
                "tipo_maquina_id",
            ),
            "machine_type_label": (
                self._selection_label_safe(
                    rental,
                    "tipo_maquina_id",
                )
            ),
            "state": self._safe_string(
                rental,
                "estado_alquiler_id",
            ),
            "state_label": (
                self._selection_label_safe(
                    rental,
                    "estado_alquiler_id",
                )
            ),
            "client": self._safe_many2one(
                rental,
                "cliente_id",
            ),
            "write_date": self._safe_date_field(
                rental,
                "write_date",
            ),
        }

    # ============================================================
    # CLIENTE / CONTACTO
    # ============================================================

    def _serialize_rental_client(
        self,
        rental,
    ):
        return {
            "client": self._safe_many2one(
                rental,
                "cliente_id",
            ),
            "contact": self._safe_string(
                rental,
                "contacto_id",
            ),
            "mobile": self._safe_string(
                rental,
                "celular",
            ),
            "email": self._safe_string(
                rental,
                "correo_",
            ),
            "job_title": self._safe_string(
                rental,
                "cargo",
            ),
            "installation_area": self._safe_string(
                rental,
                "ubicacion_instalacion",
            ),
            "legacy_address": self._safe_string(
                rental,
                "direccion",
            ),
            "internal_location": self._safe_string(
                rental,
                "ubicacion_id",
            ),
            "internal_location_label": (
                self._selection_label_safe(
                    rental,
                    "ubicacion_id",
                )
            ),
            "observations_html": self._html_json_value(
                self._field(
                    rental,
                    "observaciones",
                    False,
                )
            ),
        }

    # ============================================================
    # CONTADORES
    # ============================================================

    def _serialize_rental_counters(
        self,
        rental,
    ):
        bn = self._safe_int(
            rental,
            "contador_bn",
        )

        color = self._safe_int(
            rental,
            "contador_color",
        )

        scan = self._safe_int(
            rental,
            "contador_scan",
        )

        return {
            "black": bn,
            "color": color,
            "scan": scan,
            "print_total": (
                bn + color
            ),
            "last_update": self._safe_date_field(
                rental,
                "fecha_ultima_actualizacion",
            ),
            "has_auto_counters": self._safe_bool(
                rental,
                "has_auto_counters",
            ),
            "printtracker_last_sync": self._safe_date_field(
                rental,
                "pt_last_sync",
            ),
        }

    # ============================================================
    # COMPRA / VENTA
    # ============================================================

    def _serialize_rental_commercial(
        self,
        rental,
    ):
        return {
            "sale_price": self._safe_float(
                rental,
                "precio_venta",
            ),
            "purchase_price": self._safe_float(
                rental,
                "precio_compra",
            ),
            "currency": self._safe_many2one(
                rental,
                "currency_id",
            ),
            "purchase_invoice": self._safe_string(
                rental,
                "factura_compra",
            ),
            "purchase_date": self._safe_date_field(
                rental,
                "fecha_compra",
            ),
            "sale_invoice": self._safe_string(
                rental,
                "factura_venta",
            ),
            "sale_date": self._safe_date_field(
                rental,
                "fecha_venta",
            ),
            "sale_meter": self._safe_int(
                rental,
                "contometro_venta",
            ),
            "warranty_html": self._html_json_value(
                self._field(
                    rental,
                    "garantia",
                    False,
                )
            ),
        }

    # ============================================================
    # PRINTTRACKER / RED
    # ============================================================

    def _serialize_rental_monitoring(
        self,
        rental,
    ):
        return {
            "printtracker_entity": self._safe_many2one(
                rental,
                "pt_entity_id",
            ),
            "printtracker_device_id": self._safe_string(
                rental,
                "pt_device_id",
            ),
            "printtracker_last_sync": self._safe_date_field(
                rental,
                "pt_last_sync",
            ),
            "mac_address": self._safe_string(
                rental,
                "mac_address",
            ),
            "ip_address": self._safe_string(
                rental,
                "ip_address",
            ),
            "custom_location": self._safe_string(
                rental,
                "custom_location",
            ),
            "asset_id": self._safe_string(
                rental,
                "asset_id",
            ),
            "managed": self._safe_bool(
                rental,
                "is_managed",
                True,
            ),
        }

    # ============================================================
    # INSTALACIÓN / INSPECCIÓN
    # ============================================================

    def _serialize_rental_installation(
        self,
        rental,
    ):
        return {
            "state": self._safe_string(
                rental,
                "estado_instalacion",
            ),
            "state_label": (
                self._selection_label_safe(
                    rental,
                    "estado_instalacion",
                )
            ),
            "fit_for_installation": self._safe_bool(
                rental,
                "apto_instalacion",
            ),
            "requires_adaptation": self._safe_bool(
                rental,
                "requiere_adecuacion",
            ),
            "adaptation_notes": self._safe_string(
                rental,
                "notas_adecuacion",
            ),
            "inspection_count": self._safe_int(
                rental,
                "inspeccion_count",
            ),
        }

    # ============================================================
    # MANTENIMIENTO
    # ============================================================

    def _serialize_rental_maintenance(
        self,
        rental,
    ):
        return {
            "enabled": self._safe_bool(
                rental,
                "control_mantenimiento",
            ),
            "start_date": self._safe_date_field(
                rental,
                "fecha_inicio",
            ),
            "interval_months": self._safe_string(
                rental,
                "intervalo_meses",
            ),
            "interval_label": (
                self._selection_label_safe(
                    rental,
                    "intervalo_meses",
                )
            ),
            "recurrence_pattern": self._safe_string(
                rental,
                "patron_recurrencia",
            ),
            "recurrence_pattern_label": (
                self._selection_label_safe(
                    rental,
                    "patron_recurrencia",
                )
            ),
            "week_of_month": self._safe_string(
                rental,
                "semana_mes",
            ),
            "week_of_month_label": (
                self._selection_label_safe(
                    rental,
                    "semana_mes",
                )
            ),
            "weekday": self._safe_string(
                rental,
                "dia_semana",
            ),
            "weekday_label": (
                self._selection_label_safe(
                    rental,
                    "dia_semana",
                )
            ),
            "next_date": self._safe_date_field(
                rental,
                "fecha_recurrente",
            ),
            "program_state": self._safe_string(
                rental,
                "estado_programacion",
            ),
            "program_state_label": (
                self._selection_label_safe(
                    rental,
                    "estado_programacion",
                )
            ),
            "confirmation_date": self._safe_date_field(
                rental,
                "fecha_confirmacion",
            ),
            "reschedule_reason": self._safe_string(
                rental,
                "motivo_reprogramacion",
            ),
            "use_recurrent_date_as_base": self._safe_bool(
                rental,
                "usar_fecha_recurrente_como_base",
            ),
            "last_maintenance_date": self._safe_date_field(
                rental,
                "fecha_ultimo_mantenimiento",
            ),
        }

    # ============================================================
    # PLANIFICADOR
    # ============================================================

    def _serialize_rental_planner(
        self,
        rental,
    ):
        last_line = self._safe_many2one(
            rental,
            "ultima_linea_planificador_id",
        )

        return {
            "zone": self._safe_many2one(
                rental,
                "zona_mantenimiento_id",
            ),
            "preferred_technician": self._safe_many2one(
                rental,
                "tecnico_mantenimiento_id",
            ),
            "scheduled_date": self._safe_date_field(
                rental,
                "fecha_programada_mantenimiento",
            ),
            "scheduled_hour": self._safe_float(
                rental,
                "hora_programada_mantenimiento",
            ),
            "estimated_duration_hours": self._safe_float(
                rental,
                "duracion_mantenimiento_horas",
                2.0,
            ),
            "technicians_required": self._safe_int(
                rental,
                "cantidad_tecnicos_mantenimiento",
                1,
            ),
            "ignore_zone": self._safe_bool(
                rental,
                "ignorar_zona_mantenimiento",
            ),
            "planning_count": self._safe_int(
                rental,
                "planificador_linea_count",
            ),
            "last_planning": last_line,
            "state": self._safe_string(
                rental,
                "estado_planificacion_mantenimiento",
            ),
            "state_label": (
                self._selection_label_safe(
                    rental,
                    "estado_planificacion_mantenimiento",
                )
            ),
            "availability_html": self._html_json_value(
                self._field(
                    rental,
                    "dias_disponibles_mantenimiento",
                    False,
                )
            ),
        }

    # ============================================================
    # GEOLOCALIZACIÓN
    # ============================================================

    def _serialize_rental_geo(
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

        has_coordinates = self._safe_bool(
            rental,
            "tiene_coordenadas",
        )

        if not self._field_exists(
            rental,
            "tiene_coordenadas",
        ):
            has_coordinates = bool(
                latitude
                and longitude
            )

        return {
            "street": self._safe_string(
                rental,
                "direccion_calle",
            ),
            "reference": self._safe_string(
                rental,
                "direccion_referencia",
            ),
            "establishment_name": self._safe_string(
                rental,
                "nombre_establecimiento",
            ),
            "district": self._safe_string(
                rental,
                "distrito",
            ),
            "province": self._safe_string(
                rental,
                "provincia",
            ),
            "department": self._safe_string(
                rental,
                "departamento",
            ),
            "postal_code": self._safe_string(
                rental,
                "codigo_postal",
            ),
            "country": self._safe_string(
                rental,
                "pais",
            ),
            "latitude": latitude,
            "longitude": longitude,
            "google_place_id": self._safe_string(
                rental,
                "google_place_id",
            ),
            "manual_location": self._safe_bool(
                rental,
                "ubicacion_manual",
            ),
            "full_address": self._safe_string(
                rental,
                "direccion_completa",
            ),
            "has_coordinates": has_coordinates,
        }

    # ============================================================
    # TÓNER
    # ============================================================

    def _serialize_toner_color(
        self,
        rental,
        color,
    ):
        installed_counter_field = {
            "black": "contador_instalacion_toner_black",
            "cyan": "contador_instalacion_toner_cyan",
            "magenta": "contador_instalacion_toner_magenta",
            "yellow": "contador_instalacion_toner_yellow",
        }.get(
            color
        )

        current_counter_field = (
            "contador_actual_black"
            if color == "black"
            else "contador_actual_color"
        )

        return {
            "client_stock": self._safe_int(
                rental,
                "stock_cliente_toner_%s" % color,
            ),
            "installed": self._safe_bool(
                rental,
                "toner_%s_instalado" % color,
            ),
            "installation_date": self._safe_date_field(
                rental,
                "fecha_instalacion_toner_%s" % color,
            ),
            "installation_counter": (
                self._safe_int(
                    rental,
                    installed_counter_field,
                )
                if installed_counter_field
                else 0
            ),
            "current_counter": self._safe_int(
                rental,
                current_counter_field,
            ),
            "used_pages": self._safe_int(
                rental,
                "paginas_usadas_toner_%s" % color,
            ),
            "remaining_pages": self._safe_int(
                rental,
                "paginas_restantes_toner_%s" % color,
            ),
            "level_percent": self._safe_float(
                rental,
                "nivel_toner_%s" % color,
            ),
            "total_stock": self._safe_int(
                rental,
                "stock_total_toner_%s" % color,
            ),
        }

    def _serialize_rental_toner(
        self,
        rental,
    ):
        is_color = (
            self._safe_string(
                rental,
                "tipo_maquina_id",
            )
            == "color"
        )

        colors = {
            "black": self._serialize_toner_color(
                rental,
                "black",
            ),
        }

        if is_color:
            colors.update(
                {
                    "cyan": self._serialize_toner_color(
                        rental,
                        "cyan",
                    ),
                    "magenta": self._serialize_toner_color(
                        rental,
                        "magenta",
                    ),
                    "yellow": self._serialize_toner_color(
                        rental,
                        "yellow",
                    ),
                }
            )

        return {
            "is_color": is_color,
            "stock_state": self._safe_string(
                rental,
                "estado_stock_toner",
            ),
            "stock_state_label": (
                self._selection_label_safe(
                    rental,
                    "estado_stock_toner",
                )
            ),
            "last_counter_reading": self._safe_date_field(
                rental,
                "fecha_ultima_lectura",
            ),
            "report_count": self._safe_int(
                rental,
                "toner_reports_count",
            ),
            "delivery_count": self._safe_int(
                rental,
                "toner_deliveries_count",
            ),
            "colors": colors,
        }

    # ============================================================
    # BLOQUEO / SUSPENSIÓN
    # ============================================================

    def _serialize_rental_blocking(
        self,
        rental,
    ):
        return {
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
            "unblocked_at": self._safe_date_field(
                rental,
                "fecha_desbloqueo",
            ),
            "blocked_by": self._safe_many2one(
                rental,
                "usuario_bloqueo",
            ),
            "remote_access_available": self._safe_bool(
                rental,
                "acceso_remoto_disponible",
                True,
            ),
            "device_ip": self._safe_string(
                rental,
                "ip_equipo",
            ),
            "block_notified": self._safe_bool(
                rental,
                "notificado_bloqueo",
            ),
            "unblock_notified": self._safe_bool(
                rental,
                "notificado_desbloqueo",
            ),
            "sales_advisor": self._safe_many2one(
                rental,
                "asesor_ventas_id",
            ),
            "technical_support": self._safe_many2one(
                rental,
                "soporte_tecnico_id",
            ),
            "notes": self._safe_string(
                rental,
                "observaciones_bloqueo",
            ),
            "notification_group": self._safe_string(
                rental,
                "grupo_notificaciones_id",
            ),
            "sales_group": self._safe_string(
                rental,
                "grupo_asesor_ventas_id",
            ),
        }

    # ============================================================
    # RELACIONADOS
    # ============================================================

    def _serialize_rental_related_counts(
        self,
        rental,
    ):
        return {
            "tickets": self._safe_int(
                rental,
                "ticket_count",
            ),
            "pending_orders": self._safe_int(
                rental,
                "pedidos_count",
            ),
            "has_pending_orders": self._safe_bool(
                rental,
                "has_pending_orders",
            ),
            "parts": self._safe_int(
                rental,
                "repuestos_count",
            ),
            "inspections": self._safe_int(
                rental,
                "inspeccion_count",
            ),
            "automatic_counters": self._safe_int(
                rental,
                "contadores_count",
            ),
            "toner_reports": self._safe_int(
                rental,
                "toner_reports_count",
            ),
            "toner_deliveries": self._safe_int(
                rental,
                "toner_deliveries_count",
            ),
            "planning_lines": self._safe_int(
                rental,
                "planificador_linea_count",
            ),
        }

    # ============================================================
    # QR
    # ============================================================

    def _serialize_rental_qr(
        self,
        rental,
    ):
        has_qr = bool(
            self._field(
                rental,
                "qr_image",
                False,
            )
        )

        qr_url = False

        if (
            has_qr
            and self._method_exists(
                rental,
                "get_qr_image_url",
            )
        ):
            try:
                qr_url = rental.get_qr_image_url()
            except Exception:
                _logger.exception(
                    "No se pudo obtener URL QR para alquiler %s.",
                    rental.id,
                )

        return {
            "available": has_qr,
            "filename": self._safe_string(
                rental,
                "qr_image_filename",
            ),
            "url": qr_url or False,
        }

    # ============================================================
    # ACTION AVAILABILITY
    # ============================================================

    def _rental_action_permissions(
        self,
        rental,
        user,
    ):
        """
        Única fuente de verdad para botones Flutter.

        Los controladores específicos todavía deben validar nuevamente
        el permiso antes de ejecutar una operación. Flutter nunca debe
        considerarse una barrera de seguridad.
        """
        is_system = self._is_system_user(
            user
        )

        is_rental = self._is_rental_group_user(
            user
        )

        can_use_module = bool(
            is_system
            or is_rental
        )

        model_access = self._rental_model_access(
            user
        )

        can_write = bool(
            can_use_module
            and (
                is_system
                or model_access["write"]
            )
        )

        state = self._safe_string(
            rental,
            "estado_alquiler_id",
        )

        blocking_state = self._safe_string(
            rental,
            "estado_bloqueo",
            "activo",
        )

        maintenance_enabled = self._safe_bool(
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

        has_coordinates = self._safe_bool(
            rental,
            "tiene_coordenadas",
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

        service_operational = (
            blocking_state
            not in (
                "suspendido",
                "bloqueado",
                "no_accesible",
            )
        )

        actions = {
            # ----------------------------------------------------
            # GENERALES
            # ----------------------------------------------------
            "edit": can_write,
            "delete": bool(
                is_system
                and model_access["unlink"]
            ),
            "create": bool(
                can_use_module
                and (
                    is_system
                    or model_access["create"]
                )
            ),

            # ----------------------------------------------------
            # ESTADOS DE ALQUILER
            # ----------------------------------------------------
            "mark_reviewed": bool(
                can_write
                and state == "sin_revisar"
                and self._method_exists(
                    rental,
                    "action_estado_revisada",
                )
            ),
            "mark_ready": bool(
                can_write
                and state == "revisada"
                and self._method_exists(
                    rental,
                    "action_estado_lista",
                )
            ),
            "send_inspection": bool(
                can_write
                and state
                in (
                    "lista",
                    "inspeccion",
                    "subsanacion",
                )
                and self._method_exists(
                    rental,
                    "action_enviar_inspeccion",
                )
            ),
            # En la vista Odoo esta aprobación es base.group_system.
            "approve_installation": bool(
                is_system
                and state
                in (
                    "inspeccion",
                    "subsanacion",
                )
                and self._method_exists(
                    rental,
                    "action_estado_por_instalar",
                )
            ),
            "mark_rented": bool(
                can_write
                and state == "por_instalar"
                and self._method_exists(
                    rental,
                    "action_estado_alquilada",
                )
            ),
            "mark_problem": bool(
                can_write
                and state
                not in (
                    "vendida",
                    "externo",
                )
                and self._method_exists(
                    rental,
                    "action_estado_con_problemas",
                )
            ),
            "mark_parts": bool(
                can_write
                and state
                not in (
                    "vendida",
                    "externo",
                )
                and self._method_exists(
                    rental,
                    "action_estado_partes",
                )
            ),
            "mark_external": bool(
                can_write
                and state != "externo"
                and self._method_exists(
                    rental,
                    "action_estado_externo",
                )
            ),
            "mark_sold": bool(
                can_write
                and state != "vendida"
                and self._method_exists(
                    rental,
                    "action_estado_vendida",
                )
            ),
            # En la vista Odoo esta acción es base.group_system.
            "reset_state": bool(
                is_system
                and state != "sin_revisar"
                and self._method_exists(
                    rental,
                    "action_estado_sin_revisar",
                )
            ),

            # ----------------------------------------------------
            # RELACIONADOS
            # ----------------------------------------------------
            "view_tickets": bool(
                can_use_module
                and self._method_exists(
                    rental,
                    "get_ticket",
                )
            ),
            "create_ticket": bool(
                can_write
                and has_client
                and service_operational
                and self._method_exists(
                    rental,
                    "create_ticket",
                )
            ),
            "view_orders": bool(
                can_use_module
                and self._method_exists(
                    rental,
                    "get_pedidos",
                )
            ),
            "create_order": bool(
                can_write
                and has_client
                and self._method_exists(
                    rental,
                    "create_sale_order",
                )
            ),
            "view_parts": bool(
                can_use_module
                and self._method_exists(
                    rental,
                    "get_repuestos",
                )
            ),
            "request_parts": bool(
                can_write
                and service_operational
                and self._method_exists(
                    rental,
                    "action_solicitar_partes",
                )
            ),
            "view_inspections": bool(
                can_use_module
                and self._method_exists(
                    rental,
                    "action_view_inspecciones",
                )
            ),

            # ----------------------------------------------------
            # MANTENIMIENTO
            # ----------------------------------------------------
            "manage_maintenance": bool(
                can_write
                and self._field_exists(
                    rental,
                    "control_mantenimiento",
                )
            ),
            "send_maintenance_test_mail": bool(
                can_write
                and service_operational
                and self._method_exists(
                    rental,
                    "button_send_test_mail",
                )
            ),
            "apply_maintenance_to_client": bool(
                can_write
                and maintenance_enabled
                and has_client
                and self._method_exists(
                    rental,
                    "aplicar_configuracion_a_todos",
                )
            ),
            "complete_maintenance": bool(
                can_write
                and maintenance_enabled
                and self._method_exists(
                    rental,
                    "action_mantenimiento_completado",
                )
            ),
            "confirm_maintenance": bool(
                can_write
                and maintenance_enabled
                and self._method_exists(
                    rental,
                    "process_maintenance_response",
                )
            ),
            "reschedule_maintenance": bool(
                can_write
                and maintenance_enabled
                and self._method_exists(
                    rental,
                    "process_maintenance_response",
                )
            ),

            # ----------------------------------------------------
            # PLANIFICADOR
            # ----------------------------------------------------
            "manage_planner": bool(
                can_write
                and self._field_exists(
                    rental,
                    "estado_planificacion_mantenimiento",
                )
            ),
            "auto_schedule": bool(
                can_write
                and self._method_exists(
                    rental,
                    "action_auto_programar_mantenimiento",
                )
            ),
            "view_planning": bool(
                can_use_module
                and (
                    self._method_exists(
                        rental,
                        "action_ver_planificaciones",
                    )
                    or self._method_exists(
                        rental,
                        "action_view_planificaciones",
                    )
                )
            ),

            # ----------------------------------------------------
            # GEO
            # ----------------------------------------------------
            "edit_location": can_write,
            "geocode_address": bool(
                can_write
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
            "open_maps": bool(
                has_coordinates
                and self._method_exists(
                    rental,
                    "action_abrir_en_google_maps",
                )
            ),

            # ----------------------------------------------------
            # TÓNER
            # ----------------------------------------------------
            "view_toner": bool(
                can_use_module
                and self._field_exists(
                    rental,
                    "estado_stock_toner",
                )
            ),
            "view_toner_reports": bool(
                can_use_module
                and state == "alquilada"
                and self._method_exists(
                    rental,
                    "action_view_toner_reports",
                )
            ),
            "view_toner_deliveries": bool(
                can_use_module
                and state == "alquilada"
                and self._method_exists(
                    rental,
                    "action_view_toner_deliveries",
                )
            ),
            "create_toner_delivery": bool(
                can_write
                and state == "alquilada"
                and self._method_exists(
                    rental,
                    "action_create_manual_delivery",
                )
            ),
            "update_toner_stock": bool(
                can_write
                and self._method_exists(
                    rental,
                    "action_update_toner_stock",
                )
            ),
            "install_toner": bool(
                can_write
                and self._method_exists(
                    rental,
                    "action_install_new_toner",
                )
            ),
            "send_toner_stock_reminder": bool(
                can_write
                and has_client
                and bool(
                    self._safe_string(
                        rental,
                        "correo_",
                    )
                )
                and self._method_exists(
                    rental,
                    "action_send_stock_reminder",
                )
            ),

            # ----------------------------------------------------
            # BLOQUEO
            # ----------------------------------------------------
            "manage_blocking": bool(
                can_write
                and self._field_exists(
                    rental,
                    "estado_bloqueo",
                )
            ),
            "suspend_service": bool(
                can_write
                and blocking_state != "suspendido"
                and self._method_exists(
                    rental,
                    "action_suspender_servicio",
                )
            ),
            "block_machine": bool(
                can_write
                and blocking_state != "bloqueado"
                and self._method_exists(
                    rental,
                    "action_bloquear_equipo",
                )
            ),
            "unblock_machine": bool(
                can_write
                and blocking_state
                in (
                    "bloqueado",
                    "suspendido",
                )
                and self._method_exists(
                    rental,
                    "action_desbloquear_equipo",
                )
            ),
            "mark_pending_block": bool(
                can_write
                and blocking_state
                not in (
                    "bloqueado",
                    "pendiente_bloqueo",
                )
                and self._method_exists(
                    rental,
                    "action_marcar_pendiente_bloqueo",
                )
            ),
            "mark_pending_unblock": bool(
                can_write
                and blocking_state == "bloqueado"
                and self._method_exists(
                    rental,
                    "action_marcar_pendiente_desbloqueo",
                )
            ),
            "mark_not_accessible": bool(
                can_write
                and self._method_exists(
                    rental,
                    "action_marcar_no_accesible",
                )
            ),
            "reactivate_service": bool(
                can_write
                and blocking_state != "activo"
                and (
                    self._method_exists(
                        rental,
                        "action_reactivar_servicio",
                    )
                    or self._method_exists(
                        rental,
                        "action_desbloquear_equipo",
                    )
                )
            ),
            "verify_remote_access": bool(
                can_write
                and (
                    self._method_exists(
                        rental,
                        "action_verificar_acceso_remoto",
                    )
                    or self._method_exists(
                        rental,
                        "_ejecutar_bloqueo_remoto",
                    )
                )
            ),

            # ----------------------------------------------------
            # QR
            # ----------------------------------------------------
            "view_qr": bool(
                can_use_module
                and bool(
                    self._field(
                        rental,
                        "qr_image",
                        False,
                    )
                )
            ),
            "generate_qr": bool(
                can_write
                and self._method_exists(
                    rental,
                    "generate_qr_code",
                )
            ),
        }

        return actions

    # ============================================================
    # CONFIG DEL FORMULARIO
    # ============================================================

    def _serialize_rental_options(
        self,
    ):
        Rental = self._rental_model()

        return {
            "states": self._selection_options_safe(
                Rental,
                "estado_alquiler_id",
            ),
            "machine_types": self._selection_options_safe(
                Rental,
                "tipo_maquina_id",
            ),
            "internal_locations": self._selection_options_safe(
                Rental,
                "ubicacion_id",
            ),
            "installation_states": self._selection_options_safe(
                Rental,
                "estado_instalacion",
            ),
            "maintenance_intervals": self._selection_options_safe(
                Rental,
                "intervalo_meses",
            ),
            "maintenance_patterns": self._selection_options_safe(
                Rental,
                "patron_recurrencia",
            ),
            "maintenance_week_positions": self._selection_options_safe(
                Rental,
                "semana_mes",
            ),
            "maintenance_weekdays": self._selection_options_safe(
                Rental,
                "dia_semana",
            ),
            "maintenance_states": self._selection_options_safe(
                Rental,
                "estado_programacion",
            ),
            "planning_states": self._selection_options_safe(
                Rental,
                "estado_planificacion_mantenimiento",
            ),
            "blocking_states": self._selection_options_safe(
                Rental,
                "estado_bloqueo",
            ),
            "toner_stock_states": self._selection_options_safe(
                Rental,
                "estado_stock_toner",
            ),
        }

    # ============================================================
    # SERIALIZADOR CORTO
    # ============================================================

    def _serialize_rental_short(
        self,
        rental,
        user=None,
    ):
        """
        Payload para listados.

        Evita enviar los bloques pesados de mantenimiento,
        tóner, planner, etc. en cada fila.
        """
        identity = self._serialize_rental_identity(
            rental
        )

        counters = self._serialize_rental_counters(
            rental
        )

        blocking = self._serialize_rental_blocking(
            rental
        )

        result = {
            **identity,
            "contact": {
                "client": self._safe_many2one(
                    rental,
                    "cliente_id",
                ),
                "installation_area": self._safe_string(
                    rental,
                    "ubicacion_instalacion",
                ),
                "district": self._safe_string(
                    rental,
                    "distrito",
                ),
                "full_address": (
                    self._safe_string(
                        rental,
                        "direccion_completa",
                    )
                    or self._safe_string(
                        rental,
                        "direccion",
                    )
                ),
            },
            "counters": counters,
            "blocking": {
                "state": blocking["state"],
                "state_label": blocking[
                    "state_label"
                ],
            },
            "maintenance": {
                "enabled": self._safe_bool(
                    rental,
                    "control_mantenimiento",
                ),
                "next_date": self._safe_date_field(
                    rental,
                    "fecha_recurrente",
                ),
                "program_state": self._safe_string(
                    rental,
                    "estado_programacion",
                ),
            },
            "related": self._serialize_rental_related_counts(
                rental
            ),
        }

        if user:
            result["actions"] = (
                self._rental_action_permissions(
                    rental,
                    user,
                )
            )

        return result

    # ============================================================
    # SERIALIZADOR COMPLETO
    # ============================================================

    def _serialize_rental_detail(
        self,
        rental,
        user,
    ):
        """
        Payload canónico del detalle de una máquina.

        Los demás controladores deben devolver esta misma estructura
        después de modificar una máquina, siempre que sea razonable.
        De esta manera Flutter puede refrescar el estado local con una
        única estructura consistente.
        """
        return {
            "identity": self._serialize_rental_identity(
                rental
            ),
            "client": self._serialize_rental_client(
                rental
            ),
            "counters": self._serialize_rental_counters(
                rental
            ),
            "commercial": self._serialize_rental_commercial(
                rental
            ),
            "monitoring": self._serialize_rental_monitoring(
                rental
            ),
            "installation": self._serialize_rental_installation(
                rental
            ),
            "maintenance": self._serialize_rental_maintenance(
                rental
            ),
            "planner": self._serialize_rental_planner(
                rental
            ),
            "geo": self._serialize_rental_geo(
                rental
            ),
            "toner": self._serialize_rental_toner(
                rental
            ),
            "blocking": self._serialize_rental_blocking(
                rental
            ),
            "related": self._serialize_rental_related_counts(
                rental
            ),
            "qr": self._serialize_rental_qr(
                rental
            ),
            "actions": self._rental_action_permissions(
                rental,
                user,
            ),
            "meta": {
                "id": rental.id,
                "create_date": self._safe_date_field(
                    rental,
                    "create_date",
                ),
                "write_date": self._safe_date_field(
                    rental,
                    "write_date",
                ),
                "access_scope": self._rental_access_scope(
                    user
                ),
                "is_system": self._is_system_user(
                    user
                ),
            },
        }

    # ============================================================
    # VALIDACIONES COMUNES PARA ESCRITURA
    # ============================================================

    def _require_rental_write_access(
        self,
        rental,
        user,
    ):
        """
        Validación común que deben llamar las rutas de escritura.

        Devuelve False si puede escribir; de lo contrario devuelve
        una respuesta HTTP JSON.
        """
        if not rental:
            return self._rental_not_found_response()

        if not self._is_rental_user(
            user
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_ACCESS_DENIED",
                    "message": (
                        "El usuario no tiene acceso al área de Alquiler."
                    ),
                },
                status=403,
            )

        if self._is_system_user(
            user
        ):
            return False

        if not self._model_has_access(
            self.RENTAL_MODEL,
            "write",
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "RENTAL_WRITE_DENIED",
                    "message": (
                        "No tienes permisos para modificar esta máquina."
                    ),
                },
                status=403,
            )

        return False

    def _require_action(
        self,
        rental,
        user,
        action_key,
    ):
        """
        Valida una capacidad específica antes de ejecutar una acción.

        Uso:
            error = self._require_action(
                rental,
                user,
                "generate_qr",
            )
            if error:
                return error
        """
        permissions = (
            self._rental_action_permissions(
                rental,
                user,
            )
        )

        if permissions.get(
            action_key
        ):
            return False

        return self._json_response(
            {
                "success": False,
                "code": "RENTAL_ACTION_NOT_ALLOWED",
                "action": action_key,
                "message": (
                    "Esta acción no está disponible "
                    "para el usuario o para el estado actual de la máquina."
                ),
            },
            status=403,
        )

    # ============================================================
    # HELPERS DE RESPUESTA
    # ============================================================

    def _rental_success_response(
        self,
        rental,
        user,
        *,
        message=False,
        extra=None,
        status=200,
    ):
        """
        Respuesta estándar tras una operación exitosa.

        Devuelve siempre la máquina actualizada para evitar que
        Flutter mantenga valores obsoletos después de una acción.
        """
        data = {
            "success": True,
            "rental": self._serialize_rental_detail(
                rental,
                user,
            ),
        }

        if message:
            data["message"] = message

        if extra:
            data.update(
                extra
            )

        return self._json_response(
            data,
            status=status,
        )

    # ============================================================
    # HELPERS DE PARÁMETROS
    # ============================================================

    def _query_arg(
        self,
        name,
        default=None,
    ):
        try:
            return request.httprequest.args.get(
                name,
                default,
            )
        except Exception:
            return default

    def _positive_int(
        self,
        value,
        default,
        *,
        minimum=1,
        maximum=None,
    ):
        try:
            number = int(
                value
            )
        except Exception:
            number = default

        if number < minimum:
            number = minimum

        if (
            maximum is not None
            and number > maximum
        ):
            number = maximum

        return number

    def _page_params(
        self,
        *,
        default_limit=30,
        max_limit=100,
    ):
        page = self._positive_int(
            self._query_arg(
                "page",
                1,
            ),
            1,
            minimum=1,
        )

        limit = self._positive_int(
            self._query_arg(
                "limit",
                default_limit,
            ),
            default_limit,
            minimum=1,
            maximum=max_limit,
        )

        offset = (
            (page - 1)
            * limit
        )

        return (
            page,
            limit,
            offset,
        )

    def _clean_search(
        self,
        value,
        max_length=120,
    ):
        if value is None:
            return ""

        text = str(
            value
        ).strip()

        if len(
            text
        ) > max_length:
            text = text[
                :max_length
            ]

        return text

    # ============================================================
    # CHANGELOG / CHATTER
    # ============================================================

    def _post_app_message(
        self,
        rental,
        body,
    ):
        """
        Registra acciones relevantes realizadas desde Flutter.

        Los endpoints pueden utilizarlo después de operaciones
        administrativas importantes.
        """
        if not rental or not body:
            return False

        try:
            rental.message_post(
                body=body,
                message_type="notification",
            )
            return True
        except Exception:
            _logger.exception(
                "No se pudo registrar mensaje app en alquiler %s.",
                rental.id if rental else False,
            )
            return False
