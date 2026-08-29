# -*- coding: utf-8 -*-

"""
Listado / dashboard de la API Flutter del módulo Alquiler.

Este archivo expone únicamente endpoints de lectura:

    GET /api/app/rentals
    GET /api/app/rentals/dashboard
    GET /api/app/rentals/config

Responsabilidades:
- búsqueda incremental;
- filtros;
- paginación;
- ordenamiento seguro;
- conteos globales;
- conteos por estado;
- resumen de mantenimiento;
- resumen de bloqueo;
- resumen de tóner;
- filtros disponibles;
- clientes con equipos;
- técnicos de mantenimiento disponibles;
- configuración inicial para Flutter.

NO debe contener:
- detalle completo de una máquina;
- modificación de campos;
- cambio de estado;
- acciones de mantenimiento;
- acciones de bloqueo;
- acciones de tóner.

Esas responsabilidades pertenecen a los demás archivos del paquete rental.
"""

import logging

from odoo import fields, http
from odoo.http import request

from .base import RentalBaseController


_logger = logging.getLogger(__name__)


class RentalListController(RentalBaseController):

    # ============================================================
    # CONSTANTES
    # ============================================================

    DEFAULT_LIMIT = 30
    MAX_LIMIT = 100

    ALLOWED_SORTS = {
        "recent": "write_date desc, id desc",
        "oldest": "write_date asc, id asc",
        "serial": "serie asc, id asc",
        "serial_desc": "serie desc, id desc",
        "model": "name asc, serie asc, id asc",
        "client": "cliente_id asc, serie asc, id asc",
        "state": "estado_alquiler_id asc, serie asc, id asc",
        "maintenance": "fecha_recurrente asc, serie asc, id asc",
    }

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/rentals",
            "/api/app/rentals/dashboard",
            "/api/app/rentals/config",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def rental_list_options(
        self,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # HELPERS DE QUERY
    # ============================================================

    def _bool_query(
        self,
        name,
        default=None,
    ):
        raw = self._query_arg(
            name,
            None,
        )

        if raw is None:
            return default

        value = str(
            raw
        ).strip().lower()

        if value in (
            "1",
            "true",
            "yes",
            "si",
            "sí",
            "on",
        ):
            return True

        if value in (
            "0",
            "false",
            "no",
            "off",
        ):
            return False

        return default

    def _csv_query(
        self,
        name,
    ):
        raw = self._query_arg(
            name,
            "",
        )

        if not raw:
            return []

        result = []

        for part in str(
            raw
        ).split(","):
            value = part.strip()

            if (
                value
                and value not in result
            ):
                result.append(
                    value
                )

        return result

    def _int_query(
        self,
        name,
        default=None,
    ):
        raw = self._query_arg(
            name,
            None,
        )

        if raw in (
            None,
            "",
        ):
            return default

        try:
            return int(
                raw
            )
        except Exception:
            return default

    # ============================================================
    # DOMAIN BASE
    # ============================================================

    def _base_domain(
        self,
        user,
    ):
        """
        El módulo Alquiler no se filtra por responsable.

        Administrador y Área alquiler trabajan sobre el inventario
        completo que sus ACL / record rules de Odoo les permitan ver.
        """
        return []

    # ============================================================
    # SEARCH DOMAIN
    # ============================================================

    def _search_domain(
        self,
        search,
    ):
        """
        Búsqueda incremental por los datos más usados en taller/alquiler.

        Campos contemplados cuando existen:
        - serie
        - marca
        - modelo (name)
        - cliente
        - dirección
        - ubicación de instalación
        - IP
        - MAC
        - factura venta/compra
        """
        if not search:
            return []

        Rental = self._rental_model()

        candidates = []

        if "serie" in Rental._fields:
            candidates.append(
                ("serie", "ilike", search)
            )

        if "marca" in Rental._fields:
            candidates.append(
                ("marca", "ilike", search)
            )

        if "name" in Rental._fields:
            candidates.append(
                ("name", "ilike", search)
            )

        if "cliente_id" in Rental._fields:
            candidates.append(
                ("cliente_id", "ilike", search)
            )

        if "direccion" in Rental._fields:
            candidates.append(
                ("direccion", "ilike", search)
            )

        if "direccion_completa" in Rental._fields:
            candidates.append(
                ("direccion_completa", "ilike", search)
            )

        if "ubicacion_instalacion" in Rental._fields:
            candidates.append(
                (
                    "ubicacion_instalacion",
                    "ilike",
                    search,
                )
            )

        if "ip_address" in Rental._fields:
            candidates.append(
                ("ip_address", "ilike", search)
            )

        if "ip_equipo" in Rental._fields:
            candidates.append(
                ("ip_equipo", "ilike", search)
            )

        if "mac_address" in Rental._fields:
            candidates.append(
                ("mac_address", "ilike", search)
            )

        if "factura_venta" in Rental._fields:
            candidates.append(
                ("factura_venta", "ilike", search)
            )

        if "factura_compra" in Rental._fields:
            candidates.append(
                ("factura_compra", "ilike", search)
            )

        if not candidates:
            return []

        if len(
            candidates
        ) == 1:
            return candidates

        # OR n-ario Odoo:
        # para N condiciones se requieren N-1 operadores '|'
        return (
            ["|"]
            * (
                len(candidates)
                - 1
            )
            + candidates
        )

    # ============================================================
    # CAPACIDADES DE CAMPOS
    # ============================================================

    def _field_supports_domain(
        self,
        model,
        field_name,
    ):
        """
        Indica si un campo puede usarse directamente en un dominio SQL.

        - Los campos almacenados siempre son buscables.
        - Un campo compute no almacenado también puede ser buscable si
          declara un método ``search=...``.
        """
        field = model._fields.get(
            field_name
        )

        if not field:
            return False

        if getattr(
            field,
            "store",
            False,
        ):
            return True

        return bool(
            getattr(
                field,
                "search",
                False,
            )
        )

    def _pending_orders_filter_value(
        self,
    ):
        return self._bool_query(
            "has_pending_orders",
            None,
        )

    def _filter_nonstored_pending_orders(
        self,
        records,
        expected,
    ):
        if expected is None:
            return records

        return records.filtered(
            lambda rental: (
                bool(
                    rental.has_pending_orders
                )
                == expected
            )
        )

    # ============================================================
    # FILTER DOMAIN
    # ============================================================

    def _filter_domain(
        self,
    ):
        Rental = self._rental_model()

        domain = []

        states = self._csv_query(
            "state"
        )

        if (
            states
            and "estado_alquiler_id"
            in Rental._fields
        ):
            domain.append(
                (
                    "estado_alquiler_id",
                    "in",
                    states,
                )
            )

        exclude_states = self._csv_query(
            "exclude_state"
        )

        if (
            exclude_states
            and "estado_alquiler_id"
            in Rental._fields
        ):
            domain.append(
                (
                    "estado_alquiler_id",
                    "not in",
                    exclude_states,
                )
            )

        client_id = self._int_query(
            "client_id"
        )

        if (
            client_id
            and "cliente_id"
            in Rental._fields
        ):
            domain.append(
                (
                    "cliente_id",
                    "=",
                    client_id,
                )
            )

        model_id = self._int_query(
            "model_id"
        )

        if (
            model_id
            and "name"
            in Rental._fields
        ):
            domain.append(
                (
                    "name",
                    "=",
                    model_id,
                )
            )

        machine_type = self._query_arg(
            "machine_type",
            None,
        )

        if (
            machine_type
            and "tipo_maquina_id"
            in Rental._fields
        ):
            domain.append(
                (
                    "tipo_maquina_id",
                    "=",
                    machine_type,
                )
            )

        internal_location = self._query_arg(
            "internal_location",
            None,
        )

        if (
            internal_location
            and "ubicacion_id"
            in Rental._fields
        ):
            domain.append(
                (
                    "ubicacion_id",
                    "=",
                    internal_location,
                )
            )

        blocking_state = self._csv_query(
            "blocking_state"
        )

        if (
            blocking_state
            and "estado_bloqueo"
            in Rental._fields
        ):
            domain.append(
                (
                    "estado_bloqueo",
                    "in",
                    blocking_state,
                )
            )

        maintenance_state = self._csv_query(
            "maintenance_state"
        )

        if (
            maintenance_state
            and "estado_programacion"
            in Rental._fields
        ):
            domain.append(
                (
                    "estado_programacion",
                    "in",
                    maintenance_state,
                )
            )

        planning_state = self._csv_query(
            "planning_state"
        )

        if (
            planning_state
            and "estado_planificacion_mantenimiento"
            in Rental._fields
        ):
            domain.append(
                (
                    "estado_planificacion_mantenimiento",
                    "in",
                    planning_state,
                )
            )

        toner_state = self._csv_query(
            "toner_state"
        )

        if (
            toner_state
            and "estado_stock_toner"
            in Rental._fields
        ):
            domain.append(
                (
                    "estado_stock_toner",
                    "in",
                    toner_state,
                )
            )

        maintenance_enabled = self._bool_query(
            "maintenance_enabled",
            None,
        )

        if (
            maintenance_enabled is not None
            and "control_mantenimiento"
            in Rental._fields
        ):
            domain.append(
                (
                    "control_mantenimiento",
                    "=",
                    maintenance_enabled,
                )
            )

        with_client = self._bool_query(
            "with_client",
            None,
        )

        if (
            with_client is not None
            and "cliente_id"
            in Rental._fields
        ):
            domain.append(
                (
                    "cliente_id",
                    "!="
                    if with_client
                    else "=",
                    False,
                )
            )

        with_coordinates = self._bool_query(
            "with_coordinates",
            None,
        )

        if (
            with_coordinates is not None
            and "tiene_coordenadas"
            in Rental._fields
        ):
            domain.append(
                (
                    "tiene_coordenadas",
                    "=",
                    with_coordinates,
                )
            )

        has_pending_orders = (
            self._pending_orders_filter_value()
        )

        if (
            has_pending_orders is not None
            and "has_pending_orders"
            in Rental._fields
            and self._field_supports_domain(
                Rental,
                "has_pending_orders",
            )
        ):
            domain.append(
                (
                    "has_pending_orders",
                    "=",
                    has_pending_orders,
                )
            )

        active_only = self._bool_query(
            "active_only",
            False,
        )

        if (
            active_only
            and "estado_alquiler_id"
            in Rental._fields
        ):
            domain.append(
                (
                    "estado_alquiler_id",
                    "not in",
                    list(
                        self.NON_OPERATIONAL_STATES
                    ),
                )
            )

        return domain

    # ============================================================
    # SORT
    # ============================================================

    def _sort_order(
        self,
    ):
        key = self._query_arg(
            "sort",
            "recent",
        )

        return self.ALLOWED_SORTS.get(
            key,
            self.ALLOWED_SORTS["recent"],
        )

    # ============================================================
    # READ GROUP HELPERS
    # ============================================================

    def _count_by_selection(
        self,
        field_name,
        base_domain=None,
    ):
        Rental = self._rental_model()

        if field_name not in Rental._fields:
            return []

        domain = list(
            base_domain
            or []
        )

        try:
            groups = Rental.read_group(
                domain,
                [field_name],
                [field_name],
                lazy=False,
            )
        except Exception:
            _logger.exception(
                "No se pudo agrupar alquiler por %s.",
                field_name,
            )
            return []

        labels = {
            item["value"]: item["label"]
            for item in self._selection_options_safe(
                Rental,
                field_name,
            )
        }

        count_key = (
            "%s_count"
            % field_name
        )

        result = []

        for group in groups:
            raw_value = group.get(
                field_name
            )

            if isinstance(
                raw_value,
                (list, tuple),
            ):
                value = (
                    raw_value[0]
                    if raw_value
                    else False
                )

                label = (
                    raw_value[1]
                    if len(raw_value) > 1
                    else str(value)
                )
            else:
                value = raw_value

                label = labels.get(
                    value,
                    value or "Sin definir",
                )

            count = (
                group.get(
                    count_key
                )
                or group.get(
                    "__count"
                )
                or 0
            )

            result.append(
                {
                    "value": value or False,
                    "label": label or "Sin definir",
                    "count": int(
                        count
                    ),
                }
            )

        result.sort(
            key=lambda item: (
                -item["count"],
                str(
                    item["label"]
                ).lower(),
            )
        )

        return result

    def _count_by_many2one(
        self,
        field_name,
        base_domain=None,
        *,
        limit=None,
    ):
        Rental = self._rental_model()

        if field_name not in Rental._fields:
            return []

        domain = list(
            base_domain
            or []
        )

        try:
            groups = Rental.read_group(
                domain,
                [field_name],
                [field_name],
                lazy=False,
            )
        except Exception:
            _logger.exception(
                "No se pudo agrupar alquiler por %s.",
                field_name,
            )
            return []

        count_key = (
            "%s_count"
            % field_name
        )

        result = []

        for group in groups:
            raw = group.get(
                field_name
            )

            if not raw:
                continue

            if isinstance(
                raw,
                (list, tuple),
            ):
                record_id = (
                    raw[0]
                    if raw
                    else False
                )

                name = (
                    raw[1]
                    if len(raw) > 1
                    else ""
                )
            else:
                record_id = raw
                name = str(
                    raw
                )

            if not record_id:
                continue

            count = (
                group.get(
                    count_key
                )
                or group.get(
                    "__count"
                )
                or 0
            )

            result.append(
                {
                    "id": int(
                        record_id
                    ),
                    "name": name or "",
                    "count": int(
                        count
                    ),
                }
            )

        result.sort(
            key=lambda item: (
                -item["count"],
                item["name"].lower(),
            )
        )

        if limit:
            result = result[
                :limit
            ]

        return result

    # ============================================================
    # DASHBOARD
    # ============================================================

    def _dashboard_payload(
        self,
        user,
    ):
        Rental = self._rental_model()

        base_domain = self._base_domain(
            user
        )

        total = Rental.search_count(
            base_domain
        )

        active = total

        if "estado_alquiler_id" in Rental._fields:
            active = Rental.search_count(
                base_domain
                + [
                    (
                        "estado_alquiler_id",
                        "not in",
                        list(
                            self.NON_OPERATIONAL_STATES
                        ),
                    ),
                ]
            )

        with_client = 0
        without_client = 0

        if "cliente_id" in Rental._fields:
            with_client = Rental.search_count(
                base_domain
                + [
                    (
                        "cliente_id",
                        "!=",
                        False,
                    )
                ]
            )

            without_client = Rental.search_count(
                base_domain
                + [
                    (
                        "cliente_id",
                        "=",
                        False,
                    )
                ]
            )

        maintenance_enabled = 0
        maintenance_pending = 0
        maintenance_due_or_overdue = 0

        today = fields.Date.context_today(
            user
        )

        if "control_mantenimiento" in Rental._fields:
            maintenance_enabled = Rental.search_count(
                base_domain
                + [
                    (
                        "control_mantenimiento",
                        "=",
                        True,
                    )
                ]
            )

        if "estado_programacion" in Rental._fields:
            maintenance_pending = Rental.search_count(
                base_domain
                + [
                    (
                        "estado_programacion",
                        "in",
                        [
                            "pendiente",
                            "reprogramado",
                        ],
                    )
                ]
            )

        if "fecha_recurrente" in Rental._fields:
            maintenance_due_or_overdue = Rental.search_count(
                base_domain
                + [
                    (
                        "control_mantenimiento",
                        "=",
                        True,
                    )
                    if "control_mantenimiento"
                    in Rental._fields
                    else (
                        "id",
                        "!=",
                        0,
                    ),
                    (
                        "fecha_recurrente",
                        "!=",
                        False,
                    ),
                    (
                        "fecha_recurrente",
                        "<=",
                        today,
                    ),
                ]
            )

        blocked_or_suspended = 0
        pending_block_actions = 0

        if "estado_bloqueo" in Rental._fields:
            blocked_or_suspended = Rental.search_count(
                base_domain
                + [
                    (
                        "estado_bloqueo",
                        "in",
                        [
                            "suspendido",
                            "bloqueado",
                            "no_accesible",
                        ],
                    )
                ]
            )

            pending_block_actions = Rental.search_count(
                base_domain
                + [
                    (
                        "estado_bloqueo",
                        "in",
                        [
                            "pendiente_bloqueo",
                            "pendiente_desbloqueo",
                        ],
                    )
                ]
            )

        toner_alerts = 0

        if "estado_stock_toner" in Rental._fields:
            toner_alerts = Rental.search_count(
                base_domain
                + [
                    (
                        "estado_stock_toner",
                        "in",
                        [
                            "critico",
                            "bajo",
                        ],
                    )
                ]
            )

        pending_orders = 0

        if "has_pending_orders" in Rental._fields:
            if self._field_supports_domain(
                Rental,
                "has_pending_orders",
            ):
                pending_orders = Rental.search_count(
                    base_domain
                    + [
                        (
                            "has_pending_orders",
                            "=",
                            True,
                        )
                    ]
                )
            else:
                pending_orders = sum(
                    1
                    for rental in Rental.search(
                        base_domain
                    )
                    if rental.has_pending_orders
                )

        with_coordinates = 0

        if "tiene_coordenadas" in Rental._fields:
            with_coordinates = Rental.search_count(
                base_domain
                + [
                    (
                        "tiene_coordenadas",
                        "=",
                        True,
                    )
                ]
            )

        return {
            "totals": {
                "all": total,
                "active": active,
                "with_client": with_client,
                "without_client": without_client,
                "with_coordinates": with_coordinates,
                "maintenance_enabled": maintenance_enabled,
                "maintenance_pending": maintenance_pending,
                "maintenance_due_or_overdue": (
                    maintenance_due_or_overdue
                ),
                "blocked_or_suspended": blocked_or_suspended,
                "pending_block_actions": pending_block_actions,
                "toner_alerts": toner_alerts,
                "pending_orders": pending_orders,
            },
            "by_state": self._count_by_selection(
                "estado_alquiler_id",
                base_domain,
            ),
            "by_blocking_state": self._count_by_selection(
                "estado_bloqueo",
                base_domain,
            ),
            "by_maintenance_state": self._count_by_selection(
                "estado_programacion",
                base_domain,
            ),
            "by_planning_state": self._count_by_selection(
                "estado_planificacion_mantenimiento",
                base_domain,
            ),
            "by_toner_state": self._count_by_selection(
                "estado_stock_toner",
                base_domain,
            ),
            "top_clients": self._count_by_many2one(
                "cliente_id",
                base_domain,
                limit=15,
            ),
        }

    # ============================================================
    # FILTER CATALOGS
    # ============================================================

    def _client_filters(
        self,
        user,
        limit=250,
    ):
        Rental = self._rental_model()

        if "cliente_id" not in Rental._fields:
            return []

        domain = self._base_domain(
            user
        )

        items = self._count_by_many2one(
            "cliente_id",
            domain,
        )

        return items[
            :limit
        ]

    def _model_filters(
        self,
        user,
        limit=250,
    ):
        Rental = self._rental_model()

        if "name" not in Rental._fields:
            return []

        items = self._count_by_many2one(
            "name",
            self._base_domain(
                user
            ),
        )

        return items[
            :limit
        ]

    def _maintenance_technicians(
        self,
        user,
        limit=250,
    ):
        """
        Catálogo para filtros/asignación visual.

        No decide disponibilidad real del planificador; eso corresponde
        a planner.py.
        """
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

        # Priorizar técnicos/jefes. Si por seguridad/grupos no existen,
        # se devuelve la lista de usuarios internos accesibles.
        technical_group = request.env.ref(
            self.TECHNICAL_GROUP,
            raise_if_not_found=False,
        )

        head_group = request.env.ref(
            self.HEAD_GROUP,
            raise_if_not_found=False,
        )

        group_ids = []

        if technical_group:
            group_ids.append(
                technical_group.id
            )

        if head_group:
            group_ids.append(
                head_group.id
            )

        if group_ids:
            domain.append(
                (
                    "groups_id",
                    "in",
                    group_ids,
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
                "No se pudieron cargar técnicos para alquiler."
            )
            return []

        result = []

        for item in users:
            result.append(
                {
                    "id": item.id,
                    "name": item.name or "",
                    "login": item.login or "",
                }
            )

        return result

    # ============================================================
    # LIST
    # ============================================================

    @http.route(
        "/api/app/rentals",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_list(
        self,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            Rental = self._rental_model()

            page, limit, offset = self._page_params(
                default_limit=self.DEFAULT_LIMIT,
                max_limit=self.MAX_LIMIT,
            )

            search = self._clean_search(
                self._query_arg(
                    "q",
                    "",
                )
                or self._query_arg(
                    "search",
                    "",
                )
            )

            domain = []

            domain.extend(
                self._base_domain(
                    user
                )
            )

            domain.extend(
                self._filter_domain()
            )

            domain.extend(
                self._search_domain(
                    search
                )
            )

            pending_orders_filter = (
                self._pending_orders_filter_value()
            )

            pending_orders_python_filter = bool(
                pending_orders_filter is not None
                and "has_pending_orders"
                in Rental._fields
                and not self._field_supports_domain(
                    Rental,
                    "has_pending_orders",
                )
            )

            if pending_orders_python_filter:
                all_records = Rental.search(
                    domain,
                    order=self._sort_order(),
                )

                filtered_records = (
                    self._filter_nonstored_pending_orders(
                        all_records,
                        pending_orders_filter,
                    )
                )

                total = len(
                    filtered_records
                )

                records = filtered_records[
                    offset:offset + limit
                ]
            else:
                total = Rental.search_count(
                    domain
                )

                records = Rental.search(
                    domain,
                    order=self._sort_order(),
                    limit=limit,
                    offset=offset,
                )

            items = [
                self._serialize_rental_short(
                    rental,
                    user,
                )
                for rental in records
            ]

            pages = (
                (
                    total
                    + limit
                    - 1
                )
                // limit
                if limit
                else 1
            )

            return self._json_response(
                {
                    "success": True,
                    "scope": (
                        self._rental_access_scope(
                            user
                        )
                    ),
                    "query": {
                        "search": search,
                        "sort": self._query_arg(
                            "sort",
                            "recent",
                        ),
                    },
                    "pagination": {
                        "page": page,
                        "limit": limit,
                        "offset": offset,
                        "total": total,
                        "pages": pages,
                        "has_previous": (
                            page > 1
                        ),
                        "has_next": (
                            page < pages
                        ),
                    },
                    "items": items,
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando listado de alquileres."
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # DASHBOARD ROUTE
    # ============================================================

    @http.route(
        "/api/app/rentals/dashboard",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_dashboard(
        self,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            return self._json_response(
                {
                    "success": True,
                    "scope": (
                        self._rental_access_scope(
                            user
                        )
                    ),
                    "dashboard": (
                        self._dashboard_payload(
                            user
                        )
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando dashboard de alquiler."
            )

            return self._error_response(
                exc
            )

    # ============================================================
    # CONFIG ROUTE
    # ============================================================

    @http.route(
        "/api/app/rentals/config",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def rental_config(
        self,
        **kwargs,
    ):
        user, error = self._require_rental_user()

        if error:
            return error

        try:
            return self._json_response(
                {
                    "success": True,
                    "user": (
                        self._serialize_rental_user_context(
                            user
                        )
                    ),
                    "options": (
                        self._serialize_rental_options()
                    ),
                    "filters": {
                        "clients": self._client_filters(
                            user
                        ),
                        "models": self._model_filters(
                            user
                        ),
                        "maintenance_technicians": (
                            self._maintenance_technicians(
                                user
                            )
                        ),
                        "sorts": [
                            {
                                "value": "recent",
                                "label": "Actualizados recientemente",
                            },
                            {
                                "value": "oldest",
                                "label": "Actualizados más antiguos",
                            },
                            {
                                "value": "serial",
                                "label": "Serie A-Z",
                            },
                            {
                                "value": "serial_desc",
                                "label": "Serie Z-A",
                            },
                            {
                                "value": "model",
                                "label": "Modelo",
                            },
                            {
                                "value": "client",
                                "label": "Cliente",
                            },
                            {
                                "value": "state",
                                "label": "Estado",
                            },
                            {
                                "value": "maintenance",
                                "label": "Próximo mantenimiento",
                            },
                        ],
                    },
                    "dashboard": (
                        self._dashboard_payload(
                            user
                        )
                    ),
                }
            )

        except Exception as exc:
            _logger.exception(
                "Error cargando configuración de alquiler."
            )

            return self._error_response(
                exc
            )
