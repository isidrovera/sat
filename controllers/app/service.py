# -*- coding: utf-8 -*-

import base64
import logging
import math
import mimetypes
from datetime import timedelta

import requests

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request

from .base import AppBaseController


_logger = logging.getLogger(__name__)


class AppServiceController(AppBaseController):

    # ============================================================
    # CONSTANTS
    # ============================================================

    COUNTER_WORK_STATES = (
        "proceso",
        "en_ruta",
        "en_sitio",
        "en_revision",
    )

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/services",
            "/api/app/services/<int:service_id>",
            "/api/app/services/<int:service_id>/state",
            "/api/app/services/<int:service_id>/finalize",

            (
                "/api/app/services/<int:service_id>"
                "/counters/auto-load"
            ),

            (
                "/api/app/services/<int:service_id>"
                "/checklist/options"
            ),

            (
                "/api/app/services/<int:service_id>"
                "/components/<int:evaluation_id>"
            ),

            (
                "/api/app/services/<int:service_id>"
                "/accessories/<int:evaluation_id>"
            ),

            (
                "/api/app/services/<int:service_id>"
                "/checklist/subparts"
            ),

            (
                "/api/app/services/<int:service_id>"
                "/evidences"
            ),

            (
                "/api/app/services/<int:service_id>"
                "/evidences/geocode"
            ),

            (
                "/api/app/services/<int:service_id>"
                "/evidences/logo"
            ),

            (
                "/api/app/services/<int:service_id>"
                "/evidences/<int:photo_id>"
            ),

            (
                "/api/app/services/<int:service_id>"
                "/evidences/<int:photo_id>/image"
            ),
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def service_options(
        self,
        service_id=None,
        evaluation_id=None,
        photo_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # BASIC HELPERS
    # ============================================================

    def _service_get_service(
        self,
        service_id,
        user,
    ):
        """
        Devuelve solamente servicios asignados
        al usuario autenticado.
        """

        return request.env[
            "ticket.alquiler"
        ].search(
            [
                (
                    "id",
                    "=",
                    service_id,
                ),
                (
                    "responsable",
                    "=",
                    user.id,
                ),
            ],
            limit=1,
        )

    def _service_not_found_response(
        self,
    ):
        return self._json_response(
            {
                "success": False,
                "code": "SERVICE_NOT_FOUND",
                "message": (
                    "El servicio no existe "
                    "o no está asignado "
                    "a este usuario."
                ),
            },
            status=404,
        )

    def _service_safe_float(
        self,
        value,
        default=0.0,
    ):
        try:
            if value in (
                None,
                "",
                False,
            ):
                return default

            return float(
                value
            )

        except Exception:
            return default

    def _service_safe_int(
        self,
        value,
        default=0,
    ):
        try:
            if value in (
                None,
                "",
                False,
            ):
                return default

            return int(
                value
            )

        except Exception:
            return default

    def _service_safe_base64(
        self,
        value,
    ):
        """
        Devuelve:
        (
            base64_limpio,
            bytes_decodificados
        )
        """

        if not value:
            return False, False

        value = str(
            value
        ).strip()

        if "," in value:
            value = value.split(
                ",",
                1,
            )[1]

        try:
            decoded = base64.b64decode(
                value,
                validate=True,
            )

            return value, decoded

        except Exception:
            return False, False

    def _service_selection_values(
        self,
        record,
        field_name,
    ):
        if field_name not in record._fields:
            return []

        field = record._fields[
            field_name
        ]

        selection = (
            field.selection
        )

        if callable(
            selection
        ):
            try:
                selection = selection(
                    record
                )
            except TypeError:
                selection = selection(
                    record.env
                )

        return selection or []

    def _service_selection_options(
        self,
        record,
        field_name,
    ):
        return [
            {
                "value": value,
                "label": label,
            }
            for (
                value,
                label,
            )
            in self._service_selection_values(
                record,
                field_name,
            )
        ]

    def _service_many2one_with_code(
        self,
        record,
    ):
        if not record:
            return False

        result = (
            self._many2one(
                record
            )
        )

        if not isinstance(
            result,
            dict,
        ):
            result = {
                "id": record.id,
                "name": (
                    record.display_name
                ),
            }

        if "code" in record._fields:
            result[
                "code"
            ] = (
                record.code
                or False
            )

        return result

    # ============================================================
    # COUNTER HELPERS
    # ============================================================

    def _service_counter_preview(
        self,
        ticket,
    ):
        """
        Consulta si la misma lógica utilizada por
        action_cargar_contadores tiene información
        válida para cargar.

        No modifica el ticket.
        """

        result = {
            "available": False,
            "source": False,
            "reading_date": False,
            "black": False,
            "color": False,
            "scanner": False,
        }

        if (
            ticket.estado
            not in self.COUNTER_WORK_STATES
        ):
            return result

        if not ticket.product_alquiler:
            return result

        if not ticket.agenda:
            return result

        equipment = (
            ticket.product_alquiler
        )

        series = (
            getattr(
                equipment,
                "serie",
                False,
            )
        )

        if not series:
            return result

        if not hasattr(
            ticket,
            "_buscar_contadores_con_limite_fecha",
        ):
            return result

        try:
            agenda_date = (
                ticket.agenda.date()
            )

            minimum_date = (
                agenda_date
                - timedelta(
                    days=3,
                )
            )

            (
                counters,
                source,
                counter_date,
            ) = (
                ticket
                ._buscar_contadores_con_limite_fecha(
                    series,
                    agenda_date,
                    minimum_date,
                )
            )

            if not counters:
                return result

            black = (
                counters.get(
                    "contador_bn",
                    0,
                )
                or 0
            )

            color = (
                counters.get(
                    "contador_color",
                    0,
                )
                or 0
            )

            scanner = (
                counters.get(
                    "contador_scan",
                    0,
                )
                or 0
            )

            if not any(
                (
                    black,
                    color,
                    scanner,
                )
            ):
                return result

            result.update(
                {
                    "available": True,
                    "source": (
                        source
                        or False
                    ),
                    "reading_date": (
                        counter_date.isoformat()
                        if counter_date
                        else False
                    ),
                    "black": (
                        black
                        if black > 0
                        else False
                    ),
                    "color": (
                        color
                        if color > 0
                        else False
                    ),
                    "scanner": (
                        scanner
                        if scanner > 0
                        else False
                    ),
                }
            )

            return result

        except Exception:
            _logger.exception(
                "[APP SERVICES] "
                "Error consultando "
                "disponibilidad de contadores."
            )

            return result

    # ============================================================
    # COMPONENT CODES
    # ============================================================

    def _service_component_code_from_evaluation(
        self,
        evaluation,
    ):
        component_type = (
            evaluation
            .componente_tipo_id
        )

        if not component_type:
            return False

        base_code = (
            f"t{component_type.id}"
        )

        is_color_sensitive = bool(
            getattr(
                component_type,
                "is_color_sensitive",
                False,
            )
        )

        if not is_color_sensitive:
            return base_code

        color = (
            evaluation.color_id
        )

        if not color:
            return base_code

        color_code = (
            color.code
            if (
                "code"
                in color._fields
            )
            else False
        )

        if not color_code:
            return base_code

        return (
            f"{base_code}_"
            f"{str(color_code).lower()}"
        )

    def _service_accessory_code_from_evaluation(
        self,
        evaluation,
    ):
        if not evaluation.tipo_id:
            return False

        return (
            f"a{evaluation.tipo_id.id}"
        )

    # ============================================================
    # SERIALIZERS
    # ============================================================

    def _service_serialize_service_short(
        self,
        ticket,
    ):
        return {
            "id": (
                ticket.id
            ),

            "reference": (
                ticket.name
                or ""
            ),

            "state": (
                ticket.estado
                or False
            ),

            "state_label": (
                self._selection_label(
                    ticket,
                    "estado",
                )
            ),

            "priority": (
                ticket.priority
                or False
            ),

            "priority_label": (
                self._selection_label(
                    ticket,
                    "priority",
                )
            ),

            "service_type": (
                ticket.tipo_servicio_id
                or False
            ),

            "service_type_label": (
                self._selection_label(
                    ticket,
                    "tipo_servicio_id",
                )
            ),

            "schedule": (
                ticket.agenda
                or False
            ),

            "schedule_local": (
                ticket.agenda_local
                if (
                    "agenda_local"
                    in ticket._fields
                )
                else False
            ),

            "client": (
                self._many2one(
                    ticket.partner_id
                )
                if ticket.partner_id
                else False
            ),

            "client_name": (
                ticket.nombre_cliente
                if (
                    "nombre_cliente"
                    in ticket._fields
                )
                else False
            ),

            "machine": (
                self._many2one(
                    ticket.product_alquiler
                )
                if ticket.product_alquiler
                else False
            ),

            "model": (
                ticket.modelo_id_r
                or False
            ),

            "brand": (
                ticket.marca_id_r
                or False
            ),

            "serial": (
                ticket.serie_id_r
                or False
            ),

            "address": (
                ticket.direccion_id_r
                or False
            ),

            # ----------------------------------------------------
            # VISITA
            # ----------------------------------------------------

            "direct_visit": (
                ticket.asistencia_id
                if (
                    "asistencia_id"
                    in ticket._fields
                )
                else False
            ),

            "direct_visit_label": (
                self._selection_label(
                    ticket,
                    "asistencia_id",
                )
                if (
                    "asistencia_id"
                    in ticket._fields
                )
                else False
            ),

            "return_visit": (
                ticket.retorno_id
                if (
                    "retorno_id"
                    in ticket._fields
                )
                else False
            ),

            "return_visit_label": (
                self._selection_label(
                    ticket,
                    "retorno_id",
                )
                if (
                    "retorno_id"
                    in ticket._fields
                )
                else False
            ),

            "special_order": (
                bool(
                    ticket.pedido_especial
                )
                if (
                    "pedido_especial"
                    in ticket._fields
                )
                else False
            ),

            "source_parts_order": (
                self._many2one(
                    ticket.pedido_origen_id
                )
                if (
                    "pedido_origen_id"
                    in ticket._fields
                    and
                    ticket.pedido_origen_id
                )
                else False
            ),
        }

    def _service_serialize_component(
        self,
        item,
    ):
        state = (
            item.estado_id
            if (
                "estado_id"
                in item._fields
                and item.estado_id
            )
            else False
        )

        return {
            "id": item.id,

            "component": (
                self._many2one(
                    item.componente_tipo_id
                )
                if (
                    item.componente_tipo_id
                )
                else False
            ),

            "color": (
                self._service_many2one_with_code(
                    item.color_id
                )
                if (
                    "color_id"
                    in item._fields
                    and item.color_id
                )
                else False
            ),

            "state": (
                self._service_many2one_with_code(
                    state
                )
                if state
                else False
            ),

            "state_code": (
                state.code
                if (
                    state
                    and
                    "code"
                    in state._fields
                )
                else False
            ),

            "requires_change": (
                bool(
                    state
                    and
                    "code"
                    in state._fields
                    and
                    state.code
                    == "requiere_cambio"
                )
            ),

            "observations": (
                item.observaciones
                or ""
            ),

            "component_code": (
                self._service_component_code_from_evaluation(
                    item
                )
            ),
        }

    def _service_serialize_accessory(
        self,
        item,
    ):
        state = (
            item.estado_id
            if (
                "estado_id"
                in item._fields
                and item.estado_id
            )
            else False
        )

        return {
            "id": (
                item.id
            ),

            "accessory": (
                self._many2one(
                    item.tipo_id
                )
                if item.tipo_id
                else False
            ),

            "state": (
                self._service_many2one_with_code(
                    state
                )
                if state
                else False
            ),

            "state_code": (
                state.code
                if (
                    state
                    and
                    "code"
                    in state._fields
                )
                else False
            ),

            "requires_change": (
                bool(
                    state
                    and
                    "code"
                    in state._fields
                    and
                    state.code
                    == "requiere_cambio"
                )
            ),

            "observations": (
                item.observaciones
                or ""
            ),

            "component_code": (
                self._service_accessory_code_from_evaluation(
                    item
                )
            ),
        }

    def _service_serialize_evidence(
        self,
        photo,
        service_id,
    ):
        return {
            "id": (
                photo.id
            ),

            "moment": (
                photo.momento
            ),

            "moment_label": (
                self._selection_label(
                    photo,
                    "momento",
                )
            ),

            "captured_at": (
                photo.timestamp_captura
                or False
            ),

            "latitude": (
                photo.latitud
                if photo.latitud
                else False
            ),

            "longitude": (
                photo.longitud
                if photo.longitud
                else False
            ),

            "gps_accuracy": (
                photo.precision_gps
                or 0
            ),

            "address": (
                photo.direccion_capturada
                or False
            ),

            "has_coordinates": (
                bool(
                    photo.tiene_coordenadas
                )
            ),

            "original_filename": (
                photo.imagen_original_filename
                or False
            ),

            "processed_filename": (
                photo.imagen_procesada_filename
                or False
            ),

            "has_original": (
                bool(
                    photo.imagen_original
                )
            ),

            "has_processed": (
                bool(
                    photo.imagen_procesada
                )
            ),

            "original_image_url": (
                "/api/app/services/"
                f"{service_id}"
                "/evidences/"
                f"{photo.id}"
                "/image?variant=original"
            ),

            "processed_image_url": (
                "/api/app/services/"
                f"{service_id}"
                "/evidences/"
                f"{photo.id}"
                "/image?variant=processed"
            ),
        }

    def _service_serialize_service_detail(
        self,
        ticket,
    ):
        result = (
            self._service_serialize_service_short(
                ticket
            )
        )

        if (
            "evidencia_foto_ids"
            in ticket._fields
        ):
            evidence_before = (
                ticket
                .evidencia_foto_ids
                .filtered(
                    lambda photo: (
                        photo.momento
                        == "antes"
                    )
                )
            )

            evidence_after = (
                ticket
                .evidencia_foto_ids
                .filtered(
                    lambda photo: (
                        photo.momento
                        == "despues"
                    )
                )
            )

        else:
            Evidence = request.env[
                "ticket.evidencia.foto"
            ]

            evidence_before = (
                Evidence.search(
                    [
                        (
                            "ticket_id",
                            "=",
                            ticket.id,
                        ),
                        (
                            "momento",
                            "=",
                            "antes",
                        ),
                    ]
                )
            )

            evidence_after = (
                Evidence.search(
                    [
                        (
                            "ticket_id",
                            "=",
                            ticket.id,
                        ),
                        (
                            "momento",
                            "=",
                            "despues",
                        ),
                    ]
                )
            )

        counter_preview = (
            self._service_counter_preview(
                ticket
            )
        )

        result.update(
            {
                # ------------------------------------------------
                # PROBLEMA REPORTADO
                # ------------------------------------------------

                "description": (
                    ticket.description
                    or False
                ),

                "description_readonly": (
                    True
                ),

                # ------------------------------------------------
                # INFORME TÉCNICO HTML
                # ------------------------------------------------

                "technical_report": (
                    ticket.informe_id
                    or False
                ),

                "technical_report_html": (
                    True
                ),

                # ------------------------------------------------
                # DATOS DE QUIEN REPORTÓ
                # ------------------------------------------------

                "reporter": {
                    "name": (
                        ticket.reporter_name
                        if (
                            "reporter_name"
                            in ticket._fields
                        )
                        else False
                    ),

                    "phone": (
                        ticket.reporter_phone
                        if (
                            "reporter_phone"
                            in ticket._fields
                        )
                        else False
                    ),
                },

                # ------------------------------------------------
                # CONTACTO
                # ------------------------------------------------

                "contact": {
                    "name": (
                        ticket.contacto_id_r
                        or False
                    ),

                    "phone": (
                        ticket.celular_id_r
                        or False
                    ),

                    "email": (
                        ticket.corre_id_r
                        or False
                    ),

                    "floor": (
                        ticket.piso_id_r
                        or False
                    ),

                    "office": (
                        ticket.oficina_id_r
                        or False
                    ),

                    "area": (
                        ticket.area_id_r
                        or False
                    ),
                },

                # ------------------------------------------------
                # CONTADORES
                # ------------------------------------------------

                "meters": {
                    "black": (
                        ticket.contometrok_id
                        or False
                    ),

                    "color": (
                        ticket.contometroc_id
                        or False
                    ),

                    "scanner": (
                        ticket.contometros_id
                        or False
                    ),

                    "total": (
                        ticket.total_copias_id
                        or False
                    ),

                    "auto_load_available": (
                        counter_preview[
                            "available"
                        ]
                    ),

                    "auto_load_source": (
                        counter_preview[
                            "source"
                        ]
                    ),

                    "auto_load_reading_date": (
                        counter_preview[
                            "reading_date"
                        ]
                    ),

                    "auto_load_preview": {
                        "black": (
                            counter_preview[
                                "black"
                            ]
                        ),

                        "color": (
                            counter_preview[
                                "color"
                            ]
                        ),

                        "scanner": (
                            counter_preview[
                                "scanner"
                            ]
                        ),
                    },
                },

                # ------------------------------------------------
                # CALIDAD
                # ------------------------------------------------

                "quality": (
                    ticket.calidad_id
                    or False
                ),

                "quality_label": (
                    self._selection_label(
                        ticket,
                        "calidad_id",
                    )
                ),

                "quality_options": (
                    self._service_selection_options(
                        ticket,
                        "calidad_id",
                    )
                ),

                # ------------------------------------------------
                # RETORNO
                # ------------------------------------------------

                "return_options": (
                    self._service_selection_options(
                        ticket,
                        "retorno_id",
                    )
                    if (
                        "retorno_id"
                        in ticket._fields
                    )
                    else []
                ),

                # ------------------------------------------------
                # CHECKLIST
                # ------------------------------------------------

                "components": [
                    self._service_serialize_component(
                        item
                    )
                    for item
                    in (
                        ticket
                        .ticket_componente_eval_ids
                    )
                ],

                "accessories": [
                    self._service_serialize_accessory(
                        item
                    )
                    for item
                    in (
                        ticket
                        .ticket_accesorio_eval_ids
                    )
                ],

                # ------------------------------------------------
                # PEDIDOS
                # ------------------------------------------------

                "parts_requests_count": (
                    ticket.ticket_pedido_count
                    if (
                        "ticket_pedido_count"
                        in ticket._fields
                    )
                    else 0
                ),

                "special_order": (
                    bool(
                        ticket.pedido_especial
                    )
                    if (
                        "pedido_especial"
                        in ticket._fields
                    )
                    else False
                ),

                "source_parts_order": (
                    self._many2one(
                        ticket.pedido_origen_id
                    )
                    if (
                        "pedido_origen_id"
                        in ticket._fields
                        and
                        ticket.pedido_origen_id
                    )
                    else False
                ),

                # ------------------------------------------------
                # EVIDENCIAS
                # ------------------------------------------------

                "evidences": {
                    "before_count": (
                        len(
                            evidence_before
                        )
                    ),

                    "after_count": (
                        len(
                            evidence_after
                        )
                    ),

                    "minimum_before": (
                        3
                    ),

                    "minimum_after": (
                        3
                    ),

                    "before_complete": (
                        len(
                            evidence_before
                        )
                        >= 3
                    ),

                    "after_complete": (
                        len(
                            evidence_after
                        )
                        >= 3
                    ),

                    "complete": (
                        len(
                            evidence_before
                        )
                        >= 3
                        and
                        len(
                            evidence_after
                        )
                        >= 3
                    ),
                },
            }
        )

        return result

    # ============================================================
    # LIST SERVICES
    # ============================================================

    @http.route(
        "/api/app/services",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def services(
        self,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            state = (
                request
                .httprequest
                .args
                .get(
                    "state"
                )
            )

            search_term = (
                request
                .httprequest
                .args
                .get(
                    "search"
                )
                or ""
            ).strip()

            try:
                limit = min(
                    max(
                        int(
                            request
                            .httprequest
                            .args
                            .get(
                                "limit",
                                50,
                            )
                        ),
                        1,
                    ),
                    100,
                )

            except Exception:
                limit = 50

            domain = [
                (
                    "responsable",
                    "=",
                    user.id,
                ),
            ]

            if state:
                domain.append(
                    (
                        "estado",
                        "=",
                        state,
                    )
                )

            if search_term:
                domain.extend(
                    [
                        "|",
                        "|",
                        "|",

                        (
                            "name",
                            "ilike",
                            search_term,
                        ),

                        (
                            "nombre_cliente",
                            "ilike",
                            search_term,
                        ),

                        (
                            "serie_id_r",
                            "ilike",
                            search_term,
                        ),

                        (
                            "modelo_id_r",
                            "ilike",
                            search_term,
                        ),
                    ]
                )

            tickets = (
                request.env[
                    "ticket.alquiler"
                ].search(
                    domain,
                    order=(
                        "agenda asc, "
                        "priority desc, "
                        "id desc"
                    ),
                    limit=limit,
                )
            )

            return self._json_response(
                {
                    "success": True,

                    "count": (
                        len(
                            tickets
                        )
                    ),

                    "items": [
                        self._service_serialize_service_short(
                            ticket
                        )
                        for ticket
                        in tickets
                    ],
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # SERVICE DETAIL
    # ============================================================

    @http.route(
        "/api/app/services/<int:service_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def service_detail(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            return self._json_response(
                {
                    "success": True,

                    "service": (
                        self._service_serialize_service_detail(
                            ticket
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # UPDATE SERVICE
    # ============================================================

    @http.route(
        "/api/app/services/<int:service_id>",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def service_update(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            if (
                ticket.estado
                == "finalizado"
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_FINALIZED",
                        "message": (
                            "El servicio está "
                            "finalizado y ya no "
                            "puede modificarse."
                        ),
                    },
                    status=400,
                )

            data = (
                self._get_json_body()
            )

            # ----------------------------------------------------
            # description NO está permitido.
            # Es el problema reportado por el cliente.
            # ----------------------------------------------------

            allowed = {
                "informe_id",
                "contometros_id",
                "contometrok_id",
                "contometroc_id",
                "calidad_id",
                "retorno_id",
                "pedido_especial",
            }

            vals = {}

            for field_name in allowed:
                if (
                    field_name
                    in data
                    and
                    field_name
                    in ticket._fields
                ):
                    vals[
                        field_name
                    ] = (
                        data[
                            field_name
                        ]
                    )

            if not vals:
                return self._json_response(
                    {
                        "success": False,
                        "code": "NO_DATA",
                        "message": (
                            "No se recibieron "
                            "campos válidos "
                            "para actualizar."
                        ),
                    },
                    status=400,
                )

            # ----------------------------------------------------
            # VALIDAR CALIDAD
            # ----------------------------------------------------

            if (
                "calidad_id"
                in vals
                and
                vals[
                    "calidad_id"
                ]
            ):
                valid_quality = {
                    value
                    for (
                        value,
                        label,
                    )
                    in (
                        self._service_selection_values(
                            ticket,
                            "calidad_id",
                        )
                    )
                }

                if (
                    vals[
                        "calidad_id"
                    ]
                    not in valid_quality
                ):
                    return self._json_response(
                        {
                            "success": False,
                            "code": (
                                "INVALID_QUALITY"
                            ),
                            "message": (
                                "El valor de "
                                "calidad no es válido."
                            ),
                        },
                        status=400,
                    )

            # ----------------------------------------------------
            # VALIDAR RETORNO
            # ----------------------------------------------------

            if (
                "retorno_id"
                in vals
            ):
                valid_return_values = {
                    value
                    for (
                        value,
                        label,
                    )
                    in (
                        self._service_selection_values(
                            ticket,
                            "retorno_id",
                        )
                    )
                }

                if (
                    vals[
                        "retorno_id"
                    ]
                    not in valid_return_values
                ):
                    return self._json_response(
                        {
                            "success": False,
                            "code": (
                                "INVALID_RETURN_VALUE"
                            ),
                            "message": (
                                "El valor de "
                                "retorno no es válido."
                            ),
                        },
                        status=400,
                    )

            # ----------------------------------------------------
            # VALIDAR PEDIDO ESPECIAL
            # ----------------------------------------------------

            if (
                "pedido_especial"
                in vals
            ):
                if not isinstance(
                    vals[
                        "pedido_especial"
                    ],
                    bool,
                ):
                    return self._json_response(
                        {
                            "success": False,
                            "code": (
                                "INVALID_SPECIAL_ORDER_VALUE"
                            ),
                            "message": (
                                "Pedido especial "
                                "debe ser verdadero "
                                "o falso."
                            ),
                        },
                        status=400,
                    )

            ticket.write(
                vals
            )

            return self._json_response(
                {
                    "success": True,

                    "message": (
                        "Servicio actualizado "
                        "correctamente."
                    ),

                    "service": (
                        self._service_serialize_service_detail(
                            ticket
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # AUTO LOAD COUNTERS
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/counters/auto-load"
        ),
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def service_auto_load_counters(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            if (
                ticket.estado
                == "finalizado"
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_FINALIZED",
                        "message": (
                            "No se pueden cargar "
                            "contadores en un "
                            "servicio finalizado."
                        ),
                    },
                    status=400,
                )

            if (
                ticket.estado
                not in self.COUNTER_WORK_STATES
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "INVALID_COUNTER_STATE"
                        ),
                        "message": (
                            "La carga automática "
                            "de contadores no está "
                            "disponible en el "
                            "estado actual."
                        ),
                    },
                    status=400,
                )

            if not hasattr(
                ticket,
                "action_cargar_contadores",
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "COUNTER_METHOD_NOT_AVAILABLE"
                        ),
                        "message": (
                            "La instalación de Odoo "
                            "no dispone del método "
                            "action_cargar_contadores."
                        ),
                    },
                    status=500,
                )

            preview_before = (
                self._service_counter_preview(
                    ticket
                )
            )

            if not preview_before[
                "available"
            ]:
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "COUNTERS_NOT_AVAILABLE"
                        ),
                        "message": (
                            "No existen contadores "
                            "válidos dentro del rango "
                            "permitido de 3 días."
                        ),
                    },
                    status=400,
                )

            ticket.action_cargar_contadores()

            try:
                ticket.invalidate_recordset()
            except Exception:
                pass

            return self._json_response(
                {
                    "success": True,

                    "message": (
                        "Contadores cargados "
                        "automáticamente."
                    ),

                    "source": (
                        preview_before[
                            "source"
                        ]
                    ),

                    "reading_date": (
                        preview_before[
                            "reading_date"
                        ]
                    ),

                    "meters": {
                        "black": (
                            ticket.contometrok_id
                            or False
                        ),

                        "color": (
                            ticket.contometroc_id
                            or False
                        ),

                        "scanner": (
                            ticket.contometros_id
                            or False
                        ),

                        "total": (
                            ticket.total_copias_id
                            or False
                        ),
                    },

                    "service": (
                        self._service_serialize_service_detail(
                            ticket
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # CHECKLIST OPTIONS
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/checklist/options"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def checklist_options(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            component_states = (
                request.env[
                    "componente.estado"
                ].search(
                    [],
                    order="id asc",
                )
            )

            accessory_states = (
                request.env[
                    "accesorio.estado"
                ].search(
                    [],
                    order="id asc",
                )
            )

            return self._json_response(
                {
                    "success": True,

                    "component_states": [
                        self._service_many2one_with_code(
                            item
                        )
                        for item
                        in component_states
                    ],

                    "accessory_states": [
                        self._service_many2one_with_code(
                            item
                        )
                        for item
                        in accessory_states
                    ],
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # UPDATE COMPONENT
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/components/<int:evaluation_id>"
        ),
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def service_component_update(
        self,
        service_id,
        evaluation_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            if (
                ticket.estado
                == "finalizado"
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_FINALIZED",
                        "message": (
                            "No se puede modificar "
                            "el checklist de un "
                            "servicio finalizado."
                        ),
                    },
                    status=400,
                )

            evaluation = (
                request.env[
                    "ticket.componente.evaluacion"
                ].search(
                    [
                        (
                            "id",
                            "=",
                            evaluation_id,
                        ),
                        (
                            "ticket_id",
                            "=",
                            ticket.id,
                        ),
                    ],
                    limit=1,
                )
            )

            if not evaluation:
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "COMPONENT_NOT_FOUND"
                        ),
                        "message": (
                            "La evaluación del "
                            "componente no existe."
                        ),
                    },
                    status=404,
                )

            data = (
                self._get_json_body()
            )

            vals = {}

            if "state_id" in data:
                state_id = (
                    self._service_safe_int(
                        data.get(
                            "state_id"
                        )
                    )
                )

                state = (
                    request.env[
                        "componente.estado"
                    ].browse(
                        state_id
                    )
                )

                if not state.exists():
                    return self._json_response(
                        {
                            "success": False,
                            "code": (
                                "INVALID_COMPONENT_STATE"
                            ),
                            "message": (
                                "El estado del "
                                "componente no existe."
                            ),
                        },
                        status=400,
                    )

                vals[
                    "estado_id"
                ] = (
                    state.id
                )

            if (
                "observations"
                in data
            ):
                vals[
                    "observaciones"
                ] = (
                    data.get(
                        "observations"
                    )
                    or ""
                )

            if not vals:
                return self._json_response(
                    {
                        "success": False,
                        "code": "NO_DATA",
                        "message": (
                            "No se recibieron "
                            "datos para actualizar."
                        ),
                    },
                    status=400,
                )

            evaluation.write(
                vals
            )

            return self._json_response(
                {
                    "success": True,

                    "message": (
                        "Componente actualizado "
                        "correctamente."
                    ),

                    "component": (
                        self._service_serialize_component(
                            evaluation
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # UPDATE ACCESSORY
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/accessories/<int:evaluation_id>"
        ),
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def service_accessory_update(
        self,
        service_id,
        evaluation_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            if (
                ticket.estado
                == "finalizado"
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_FINALIZED",
                        "message": (
                            "No se puede modificar "
                            "el checklist de un "
                            "servicio finalizado."
                        ),
                    },
                    status=400,
                )

            evaluation = (
                request.env[
                    "ticket.accesorio.evaluacion"
                ].search(
                    [
                        (
                            "id",
                            "=",
                            evaluation_id,
                        ),
                        (
                            "ticket_id",
                            "=",
                            ticket.id,
                        ),
                    ],
                    limit=1,
                )
            )

            if not evaluation:
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "ACCESSORY_NOT_FOUND"
                        ),
                        "message": (
                            "La evaluación del "
                            "accesorio no existe."
                        ),
                    },
                    status=404,
                )

            data = (
                self._get_json_body()
            )

            vals = {}

            if "state_id" in data:
                state_id = (
                    self._service_safe_int(
                        data.get(
                            "state_id"
                        )
                    )
                )

                state = (
                    request.env[
                        "accesorio.estado"
                    ].browse(
                        state_id
                    )
                )

                if not state.exists():
                    return self._json_response(
                        {
                            "success": False,
                            "code": (
                                "INVALID_ACCESSORY_STATE"
                            ),
                            "message": (
                                "El estado del "
                                "accesorio no existe."
                            ),
                        },
                        status=400,
                    )

                vals[
                    "estado_id"
                ] = (
                    state.id
                )

            if (
                "observations"
                in data
            ):
                vals[
                    "observaciones"
                ] = (
                    data.get(
                        "observations"
                    )
                    or ""
                )

            if not vals:
                return self._json_response(
                    {
                        "success": False,
                        "code": "NO_DATA",
                        "message": (
                            "No se recibieron "
                            "datos para actualizar."
                        ),
                    },
                    status=400,
                )

            evaluation.write(
                vals
            )

            return self._json_response(
                {
                    "success": True,

                    "message": (
                        "Accesorio actualizado "
                        "correctamente."
                    ),

                    "accessory": (
                        self._service_serialize_accessory(
                            evaluation
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # SUBPART HELPERS
    # ============================================================

    def _service_get_component_evaluation(
        self,
        ticket,
        evaluation_id,
    ):
        return request.env[
            "ticket.componente.evaluacion"
        ].search(
            [
                (
                    "id",
                    "=",
                    evaluation_id,
                ),
                (
                    "ticket_id",
                    "=",
                    ticket.id,
                ),
            ],
            limit=1,
        )

    def _service_get_accessory_evaluation(
        self,
        ticket,
        evaluation_id,
    ):
        return request.env[
            "ticket.accesorio.evaluacion"
        ].search(
            [
                (
                    "id",
                    "=",
                    evaluation_id,
                ),
                (
                    "ticket_id",
                    "=",
                    ticket.id,
                ),
            ],
            limit=1,
        )

    def _service_available_component_subparts(
        self,
        ticket,
        evaluation,
    ):
        """
        Replica la búsqueda que hace el wizard:
        modelo + tipo + color.
        """

        if not ticket.product_alquiler:
            return []

        model = (
            getattr(
                ticket.product_alquiler,
                "name",
                False,
            )
        )

        if not model:
            return []

        component_type = (
            evaluation
            .componente_tipo_id
        )

        if not component_type:
            return []

        ComponentModel = (
            request.env[
                "modelo.maquina.componente"
            ]
        )

        fields_map = (
            ComponentModel._fields
        )

        domain = [
            (
                "modelo_id",
                "=",
                model.id,
            ),
            (
                "tipo_id",
                "=",
                component_type.id,
            ),
        ]

        if (
            evaluation.color_id
            and
            "color_id"
            in fields_map
        ):
            domain.append(
                (
                    "color_id",
                    "=",
                    evaluation.color_id.id,
                )
            )

        records = (
            ComponentModel.search(
                domain
            )
        )

        if not records:
            records = (
                ComponentModel.search(
                    [
                        (
                            "modelo_id",
                            "=",
                            model.id,
                        ),
                        (
                            "tipo_id",
                            "=",
                            component_type.id,
                        ),
                    ]
                )
            )

        if not records:
            records = (
                ComponentModel.search(
                    [
                        (
                            "tipo_id",
                            "=",
                            component_type.id,
                        ),
                    ]
                )
            )

        subparts = {}

        for record in records:
            details = (
                getattr(
                    record,
                    "detalle_ids",
                    []
                )
            )

            for detail in details:
                if not detail.subparte_id:
                    continue

                subparts[
                    detail.subparte_id.id
                ] = {
                    "record": (
                        detail.subparte_id
                    ),

                    "default_quantity": (
                        detail.cantidad
                        or 1.0
                    ),
                }

        return list(
            subparts.values()
        )

    def _service_available_accessory_subparts(
        self,
        evaluation,
    ):
        if not evaluation.tipo_id:
            return []

        Subpart = (
            request.env[
                "componente.subparte"
            ]
        )

        if (
            "tipo_id"
            not in Subpart._fields
        ):
            return []

        records = (
            Subpart.search(
                [
                    (
                        "tipo_id",
                        "=",
                        evaluation.tipo_id.id,
                    ),
                ],
                order="name asc",
            )
        )

        return [
            {
                "record": (
                    record
                ),
                "default_quantity": (
                    1.0
                ),
            }
            for record
            in records
        ]

    def _service_get_or_create_intervention(
        self,
        ticket,
        component_code,
    ):
        Intervention = (
            request.env[
                "ticket.componente.intervencion"
            ]
        )

        intervention = (
            Intervention.search(
                [
                    (
                        "ticket_id",
                        "=",
                        ticket.id,
                    ),
                    (
                        "componente_code",
                        "=",
                        component_code,
                    ),
                ],
                limit=1,
            )
        )

        if not intervention:
            intervention = (
                Intervention.create(
                    {
                        "ticket_id": (
                            ticket.id
                        ),
                        "componente_code": (
                            component_code
                        ),
                    }
                )
            )

        return intervention

    # ============================================================
    # GET SUBPARTS
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/checklist/subparts"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def service_subparts(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            evaluation_type = (
                request
                .httprequest
                .args
                .get(
                    "type"
                )
                or ""
            ).strip()

            evaluation_id = (
                self._service_safe_int(
                    request
                    .httprequest
                    .args
                    .get(
                        "evaluation_id"
                    )
                )
            )

            if evaluation_type not in (
                "component",
                "accessory",
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_TYPE",
                        "message": (
                            "El tipo debe ser "
                            "component o accessory."
                        ),
                    },
                    status=400,
                )

            if not evaluation_id:
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "EVALUATION_REQUIRED"
                        ),
                        "message": (
                            "Debe indicar "
                            "evaluation_id."
                        ),
                    },
                    status=400,
                )

            if (
                evaluation_type
                == "component"
            ):
                evaluation = (
                    self._service_get_component_evaluation(
                        ticket,
                        evaluation_id,
                    )
                )

                if not evaluation:
                    return self._json_response(
                        {
                            "success": False,
                            "code": (
                                "COMPONENT_NOT_FOUND"
                            ),
                            "message": (
                                "Componente no encontrado."
                            ),
                        },
                        status=404,
                    )

                component_code = (
                    self._service_component_code_from_evaluation(
                        evaluation
                    )
                )

                available = (
                    self._service_available_component_subparts(
                        ticket,
                        evaluation,
                    )
                )

            else:
                evaluation = (
                    self._service_get_accessory_evaluation(
                        ticket,
                        evaluation_id,
                    )
                )

                if not evaluation:
                    return self._json_response(
                        {
                            "success": False,
                            "code": (
                                "ACCESSORY_NOT_FOUND"
                            ),
                            "message": (
                                "Accesorio no encontrado."
                            ),
                        },
                        status=404,
                    )

                component_code = (
                    self._service_accessory_code_from_evaluation(
                        evaluation
                    )
                )

                available = (
                    self._service_available_accessory_subparts(
                        evaluation
                    )
                )

            Intervention = (
                request.env[
                    "ticket.componente.intervencion"
                ]
            )

            intervention = (
                Intervention.search(
                    [
                        (
                            "ticket_id",
                            "=",
                            ticket.id,
                        ),
                        (
                            "componente_code",
                            "=",
                            component_code,
                        ),
                    ],
                    limit=1,
                )
            )

            selected_map = {}

            if intervention:
                for detail in (
                    intervention.detalle_ids
                ):
                    if not detail.subparte_id:
                        continue

                    selected_map[
                        detail.subparte_id.id
                    ] = (
                        detail
                    )

            items = []

            for item in available:
                subpart = (
                    item[
                        "record"
                    ]
                )

                selected_detail = (
                    selected_map.get(
                        subpart.id
                    )
                )

                items.append(
                    {
                        "id": (
                            subpart.id
                        ),

                        "name": (
                            subpart.display_name
                        ),

                        "selected": (
                            bool(
                                selected_detail
                            )
                        ),

                        "quantity": (
                            selected_detail.cantidad
                            if selected_detail
                            else item[
                                "default_quantity"
                            ]
                        ),

                        "observation": (
                            selected_detail.observacion
                            if selected_detail
                            else ""
                        ),
                    }
                )

            return self._json_response(
                {
                    "success": True,

                    "type": (
                        evaluation_type
                    ),

                    "evaluation_id": (
                        evaluation_id
                    ),

                    "component_code": (
                        component_code
                    ),

                    "items": (
                        items
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # SAVE SUBPARTS
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/checklist/subparts"
        ),
        type="http",
        auth="public",
        methods=["PUT"],
        csrf=False,
        save_session=True,
    )
    def service_subparts_save(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            if (
                ticket.estado
                == "finalizado"
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_FINALIZED",
                        "message": (
                            "No se pueden modificar "
                            "subpartes después de "
                            "finalizar el servicio."
                        ),
                    },
                    status=400,
                )

            data = (
                self._get_json_body()
            )

            evaluation_type = (
                str(
                    data.get(
                        "type"
                    )
                    or ""
                ).strip()
            )

            evaluation_id = (
                self._service_safe_int(
                    data.get(
                        "evaluation_id"
                    )
                )
            )

            raw_items = (
                data.get(
                    "items"
                )
                or []
            )

            if evaluation_type not in (
                "component",
                "accessory",
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_TYPE",
                        "message": (
                            "El tipo debe ser "
                            "component o accessory."
                        ),
                    },
                    status=400,
                )

            if (
                evaluation_type
                == "component"
            ):
                evaluation = (
                    self._service_get_component_evaluation(
                        ticket,
                        evaluation_id,
                    )
                )

                if not evaluation:
                    return self._json_response(
                        {
                            "success": False,
                            "code": (
                                "COMPONENT_NOT_FOUND"
                            ),
                            "message": (
                                "Componente no encontrado."
                            ),
                        },
                        status=404,
                    )

                component_code = (
                    self._service_component_code_from_evaluation(
                        evaluation
                    )
                )

                available = (
                    self._service_available_component_subparts(
                        ticket,
                        evaluation,
                    )
                )

            else:
                evaluation = (
                    self._service_get_accessory_evaluation(
                        ticket,
                        evaluation_id,
                    )
                )

                if not evaluation:
                    return self._json_response(
                        {
                            "success": False,
                            "code": (
                                "ACCESSORY_NOT_FOUND"
                            ),
                            "message": (
                                "Accesorio no encontrado."
                            ),
                        },
                        status=404,
                    )

                component_code = (
                    self._service_accessory_code_from_evaluation(
                        evaluation
                    )
                )

                available = (
                    self._service_available_accessory_subparts(
                        evaluation
                    )
                )

            available_ids = {
                item[
                    "record"
                ].id
                for item
                in available
            }

            intervention = (
                self._service_get_or_create_intervention(
                    ticket,
                    component_code,
                )
            )

            Detail = (
                request.env[
                    "ticket.componente.intervencion.detalle"
                ]
            )

            selected_ids = set()

            for raw in raw_items:
                if not isinstance(
                    raw,
                    dict,
                ):
                    continue

                if not raw.get(
                    "selected"
                ):
                    continue

                subpart_id = (
                    self._service_safe_int(
                        raw.get(
                            "subpart_id"
                        )
                        or
                        raw.get(
                            "id"
                        )
                    )
                )

                if (
                    not subpart_id
                    or
                    subpart_id
                    not in available_ids
                ):
                    continue

                selected_ids.add(
                    subpart_id
                )

                existing = (
                    Detail.search(
                        [
                            (
                                "intervencion_id",
                                "=",
                                intervention.id,
                            ),
                            (
                                "subparte_id",
                                "=",
                                subpart_id,
                            ),
                        ],
                        limit=1,
                    )
                )

                quantity = (
                    self._service_safe_float(
                        raw.get(
                            "quantity"
                        ),
                        default=1.0,
                    )
                )

                if quantity <= 0:
                    quantity = 1.0

                observation = (
                    raw.get(
                        "observation"
                    )
                    or ""
                )

                vals = {
                    "cantidad": (
                        quantity
                    ),

                    "observacion": (
                        observation
                    ),
                }

                if existing:
                    existing.write(
                        vals
                    )

                else:
                    vals.update(
                        {
                            "intervencion_id": (
                                intervention.id
                            ),

                            "subparte_id": (
                                subpart_id
                            ),
                        }
                    )

                    Detail.create(
                        vals
                    )

            for detail in (
                intervention.detalle_ids
            ):
                if (
                    detail.subparte_id.id
                    not in selected_ids
                ):
                    detail.unlink()

            return self._json_response(
                {
                    "success": True,

                    "message": (
                        "Subpartes actualizadas "
                        "correctamente."
                    ),

                    "selected_count": (
                        len(
                            selected_ids
                        )
                    ),

                    "component_code": (
                        component_code
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # EVIDENCE LIST
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/evidences"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def service_evidences(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            photos = (
                request.env[
                    "ticket.evidencia.foto"
                ].search(
                    [
                        (
                            "ticket_id",
                            "=",
                            ticket.id,
                        ),
                    ],
                    order=(
                        "momento asc, "
                        "timestamp_captura desc, "
                        "id desc"
                    ),
                )
            )

            before = (
                photos.filtered(
                    lambda photo: (
                        photo.momento
                        == "antes"
                    )
                )
            )

            after = (
                photos.filtered(
                    lambda photo: (
                        photo.momento
                        == "despues"
                    )
                )
            )

            return self._json_response(
                {
                    "success": True,

                    "before_count": (
                        len(
                            before
                        )
                    ),

                    "after_count": (
                        len(
                            after
                        )
                    ),

                    "minimum_before": (
                        3
                    ),

                    "minimum_after": (
                        3
                    ),

                    "complete": (
                        len(
                            before
                        )
                        >= 3
                        and
                        len(
                            after
                        )
                        >= 3
                    ),

                    "items": [
                        self._service_serialize_evidence(
                            photo,
                            ticket.id,
                        )
                        for photo
                        in photos
                    ],
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # EVIDENCE UPLOAD
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/evidences"
        ),
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def service_evidence_upload(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            if (
                ticket.estado
                == "finalizado"
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_FINALIZED",
                        "message": (
                            "El servicio está finalizado. "
                            "No se aceptan más evidencias."
                        ),
                    },
                    status=400,
                )

            data = (
                self._get_json_body()
            )

            moment = (
                str(
                    data.get(
                        "moment"
                    )
                    or
                    data.get(
                        "momento"
                    )
                    or ""
                ).strip()
            )

            if moment not in (
                "antes",
                "despues",
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_MOMENT",
                        "message": (
                            "La evidencia debe ser "
                            "antes o despues."
                        ),
                    },
                    status=400,
                )

            original_value = (
                data.get(
                    "original_image"
                )
                or
                data.get(
                    "imagen_original"
                )
            )

            processed_value = (
                data.get(
                    "processed_image"
                )
                or
                data.get(
                    "imagen_procesada"
                )
            )

            (
                original_base64,
                original_bytes,
            ) = (
                self._service_safe_base64(
                    original_value
                )
            )

            if not original_base64:
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "INVALID_ORIGINAL_IMAGE"
                        ),
                        "message": (
                            "No se recibió una "
                            "imagen original válida."
                        ),
                    },
                    status=400,
                )

            processed_base64 = False
            processed_bytes = False

            if processed_value:
                (
                    processed_base64,
                    processed_bytes,
                ) = (
                    self._service_safe_base64(
                        processed_value
                    )
                )

                if not processed_base64:
                    return self._json_response(
                        {
                            "success": False,
                            "code": (
                                "INVALID_PROCESSED_IMAGE"
                            ),
                            "message": (
                                "La imagen procesada "
                                "no es válida."
                            ),
                        },
                        status=400,
                    )

            max_size = (
                10
                * 1024
                * 1024
            )

            if (
                len(
                    original_bytes
                )
                > max_size
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "ORIGINAL_TOO_LARGE"
                        ),
                        "message": (
                            "La imagen original "
                            "supera los 10 MB."
                        ),
                    },
                    status=400,
                )

            if (
                processed_bytes
                and
                len(
                    processed_bytes
                )
                > max_size
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "PROCESSED_TOO_LARGE"
                        ),
                        "message": (
                            "La imagen procesada "
                            "supera los 10 MB."
                        ),
                    },
                    status=400,
                )

            latitude = (
                self._service_safe_float(
                    data.get(
                        "latitude"
                    )
                    or
                    data.get(
                        "latitud"
                    )
                )
            )

            longitude = (
                self._service_safe_float(
                    data.get(
                        "longitude"
                    )
                    or
                    data.get(
                        "longitud"
                    )
                )
            )

            gps_accuracy = (
                self._service_safe_float(
                    data.get(
                        "gps_accuracy"
                    )
                    or
                    data.get(
                        "precision_gps"
                    )
                    or
                    data.get(
                        "precision"
                    )
                )
            )

            address = (
                data.get(
                    "address"
                )
                or
                data.get(
                    "direccion_capturada"
                )
                or
                data.get(
                    "direccion"
                )
                or
                False
            )

            original_filename = (
                data.get(
                    "original_filename"
                )
                or
                "evidencia_original.jpg"
            )

            processed_filename = (
                data.get(
                    "processed_filename"
                )
                or
                "evidencia_procesada.jpg"
            )

            vals = {
                "ticket_id": (
                    ticket.id
                ),

                "momento": (
                    moment
                ),

                "imagen_original": (
                    original_base64
                ),

                "imagen_original_filename": (
                    original_filename
                ),

                "latitud": (
                    latitude
                ),

                "longitud": (
                    longitude
                ),

                "precision_gps": (
                    gps_accuracy
                ),

                "direccion_capturada": (
                    address
                ),

                "timestamp_captura": (
                    fields.Datetime.now()
                ),

                "user_agent": (
                    request
                    .httprequest
                    .headers
                    .get(
                        "User-Agent",
                        "",
                    )
                ),

                "ip_origen": (
                    request
                    .httprequest
                    .remote_addr
                ),
            }

            if processed_base64:
                vals.update(
                    {
                        "imagen_procesada": (
                            processed_base64
                        ),

                        "imagen_procesada_filename": (
                            processed_filename
                        ),
                    }
                )

            photo = (
                request.env[
                    "ticket.evidencia.foto"
                ].create(
                    vals
                )
            )

            ticket.message_post(
                body=(
                    "📸 Evidencia subida "
                    "desde Copier OS App.<br/>"
                    f"Momento: {moment}<br/>"
                    f"Foto ID: {photo.id}<br/>"
                    f"GPS: {latitude}, "
                    f"{longitude}<br/>"
                    f"Precisión: "
                    f"{gps_accuracy} m"
                ),
                message_type=(
                    "notification"
                ),
            )

            return self._json_response(
                {
                    "success": True,

                    "message": (
                        "Evidencia guardada "
                        "correctamente."
                    ),

                    "photo": (
                        self._service_serialize_evidence(
                            photo,
                            ticket.id,
                        )
                    ),
                },
                status=201,
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # DELETE EVIDENCE
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/evidences/<int:photo_id>"
        ),
        type="http",
        auth="public",
        methods=["DELETE"],
        csrf=False,
        save_session=True,
    )
    def service_evidence_delete(
        self,
        service_id,
        photo_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            if (
                ticket.estado
                == "finalizado"
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": "SERVICE_FINALIZED",
                        "message": (
                            "No se puede eliminar "
                            "evidencia de un "
                            "servicio finalizado."
                        ),
                    },
                    status=400,
                )

            photo = (
                request.env[
                    "ticket.evidencia.foto"
                ].search(
                    [
                        (
                            "id",
                            "=",
                            photo_id,
                        ),
                        (
                            "ticket_id",
                            "=",
                            ticket.id,
                        ),
                    ],
                    limit=1,
                )
            )

            if not photo:
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "EVIDENCE_NOT_FOUND"
                        ),
                        "message": (
                            "La evidencia no existe."
                        ),
                    },
                    status=404,
                )

            photo.unlink()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Evidencia eliminada."
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # EVIDENCE IMAGE
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/evidences/<int:photo_id>/image"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def service_evidence_image(
        self,
        service_id,
        photo_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        ticket = (
            self._service_get_service(
                service_id,
                user,
            )
        )

        if not ticket:
            return request.not_found()

        photo = (
            request.env[
                "ticket.evidencia.foto"
            ].search(
                [
                    (
                        "id",
                        "=",
                        photo_id,
                    ),
                    (
                        "ticket_id",
                        "=",
                        ticket.id,
                    ),
                ],
                limit=1,
            )
        )

        if not photo:
            return request.not_found()

        variant = (
            request
            .httprequest
            .args
            .get(
                "variant"
            )
            or
            "processed"
        )

        if variant == "original":
            image_value = (
                photo.imagen_original
            )

            filename = (
                photo.imagen_original_filename
                or
                "evidencia.jpg"
            )

        else:
            image_value = (
                photo.imagen_procesada
                or
                photo.imagen_original
            )

            filename = (
                photo.imagen_procesada_filename
                or
                photo.imagen_original_filename
                or
                "evidencia.jpg"
            )

        if not image_value:
            return request.not_found()

        try:
            image_bytes = (
                base64.b64decode(
                    image_value
                )
            )

        except Exception:
            return request.not_found()

        mimetype = (
            mimetypes.guess_type(
                filename
            )[0]
            or
            "image/jpeg"
        )

        return request.make_response(
            image_bytes,
            headers=[
                (
                    "Content-Type",
                    mimetype,
                ),
                (
                    "Content-Disposition",
                    (
                        'inline; filename="'
                        + filename
                        + '"'
                    ),
                ),
                (
                    "Cache-Control",
                    (
                        "private, "
                        "max-age=300"
                    ),
                ),
            ],
        )

    # ============================================================
    # COMPANY LOGO
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/evidences/logo"
        ),
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def service_evidence_logo(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        ticket = (
            self._service_get_service(
                service_id,
                user,
            )
        )

        if not ticket:
            return request.not_found()

        company = (
            ticket.company_id
            if (
                "company_id"
                in ticket._fields
                and
                ticket.company_id
            )
            else
            request.env.company
        )

        logo = False

        if (
            "logo"
            in company._fields
            and
            company.logo
        ):
            logo = (
                company.logo
            )

        elif (
            "logo_web"
            in company._fields
            and
            company.logo_web
        ):
            logo = (
                company.logo_web
            )

        if not logo:
            return request.not_found()

        try:
            image_bytes = (
                base64.b64decode(
                    logo
                )
            )

        except Exception:
            return request.not_found()

        return request.make_response(
            image_bytes,
            headers=[
                (
                    "Content-Type",
                    "image/png",
                ),
                (
                    "Content-Disposition",
                    (
                        'inline; filename="'
                        'company_logo.png"'
                    ),
                ),
                (
                    "Cache-Control",
                    (
                        "private, "
                        "max-age=3600"
                    ),
                ),
            ],
        )

    # ============================================================
    # GEOCODE HELPERS
    # ============================================================

    def _service_normalize_address(
        self,
        address,
    ):
        if not address:
            return False

        address = (
            str(
                address
            )
            .replace(
                "\n",
                " ",
            )
            .strip()
        )

        parts = [
            item.strip()
            for item
            in address.split(
                ","
            )
            if (
                item
                and
                item.strip()
            )
        ]

        clean = []

        for item in parts:
            if (
                item.isdigit()
                and
                len(
                    item
                )
                >= 5
            ):
                continue

            if item not in clean:
                clean.append(
                    item
                )

        if clean:
            return (
                ", ".join(
                    clean[:6]
                )
            )

        return address[
            :180
        ]

    def _service_distance_meters(
        self,
        lat1,
        lon1,
        lat2,
        lon2,
    ):
        radius = (
            6371000
        )

        phi1 = (
            math.radians(
                float(
                    lat1
                )
            )
        )

        phi2 = (
            math.radians(
                float(
                    lat2
                )
            )
        )

        delta_phi = (
            math.radians(
                float(
                    lat2
                )
                -
                float(
                    lat1
                )
            )
        )

        delta_lambda = (
            math.radians(
                float(
                    lon2
                )
                -
                float(
                    lon1
                )
            )
        )

        value = (
            math.sin(
                delta_phi
                / 2
            ) ** 2
            +
            math.cos(
                phi1
            )
            *
            math.cos(
                phi2
            )
            *
            math.sin(
                delta_lambda
                / 2
            ) ** 2
        )

        return (
            radius
            * 2
            * math.atan2(
                math.sqrt(
                    value
                ),
                math.sqrt(
                    1
                    -
                    value
                ),
            )
        )

    def _service_traccar_address(
        self,
        latitude,
        longitude,
    ):
        ICP = (
            request.env[
                "ir.config_parameter"
            ].sudo()
        )

        url = (
            ICP.get_param(
                "traccar.url",
                (
                    "https://"
                    "gps.andessolutioncopiers.com"
                ),
            )
            or ""
        ).rstrip(
            "/"
        )

        email = (
            ICP.get_param(
                "traccar.email"
            )
        )

        password = (
            ICP.get_param(
                "traccar.password"
            )
        )

        try:
            timeout = int(
                ICP.get_param(
                    "traccar.timeout",
                    "10",
                )
                or
                10
            )

        except Exception:
            timeout = 10

        if (
            not url
            or
            not email
            or
            not password
        ):
            return False

        try:
            session = (
                requests.Session()
            )

            login_response = (
                session.post(
                    (
                        f"{url}"
                        "/api/session"
                    ),
                    data={
                        "email": email,
                        "password": (
                            password
                        ),
                    },
                    timeout=(
                        timeout
                    ),
                )
            )

            if (
                login_response.status_code
                != 200
            ):
                return False

            positions_response = (
                session.get(
                    (
                        f"{url}"
                        "/api/positions"
                    ),
                    timeout=(
                        timeout
                    ),
                )
            )

            if (
                positions_response.status_code
                != 200
            ):
                return False

            positions = (
                positions_response.json()
                or []
            )

            best = False
            best_distance = False

            for position in positions:
                lat = (
                    position.get(
                        "latitude"
                    )
                )

                lng = (
                    position.get(
                        "longitude"
                    )
                )

                address = (
                    position.get(
                        "address"
                    )
                )

                if (
                    not lat
                    or
                    not lng
                    or
                    not address
                ):
                    continue

                distance = (
                    self._service_distance_meters(
                        latitude,
                        longitude,
                        lat,
                        lng,
                    )
                )

                if (
                    best is False
                    or
                    distance
                    < best_distance
                ):
                    best = (
                        position
                    )

                    best_distance = (
                        distance
                    )

            if (
                best
                and
                best_distance
                is not False
                and
                best_distance
                <= 250
            ):
                return (
                    self._service_normalize_address(
                        best.get(
                            "address"
                        )
                    )
                )

            return False

        except Exception:
            _logger.exception(
                "[APP EVIDENCE] "
                "Error consultando Traccar."
            )

            return False

    def _service_nominatim_address(
        self,
        latitude,
        longitude,
    ):
        try:
            response = (
                requests.get(
                    (
                        "https://"
                        "nominatim.openstreetmap.org"
                        "/reverse"
                    ),
                    params={
                        "format": "jsonv2",
                        "lat": latitude,
                        "lon": longitude,
                        "zoom": 18,
                        "addressdetails": 1,
                        "accept-language": (
                            "es"
                        ),
                    },
                    headers={
                        "User-Agent": (
                            "AndesSolutionCopiers-"
                            "CopierOS-App/1.0"
                        ),
                    },
                    timeout=8,
                )
            )

            if (
                response.status_code
                != 200
            ):
                return False

            data = (
                response.json()
                or {}
            )

            return (
                self._service_normalize_address(
                    data.get(
                        "display_name"
                    )
                )
            )

        except Exception:
            _logger.exception(
                "[APP EVIDENCE] "
                "Error consultando Nominatim."
            )

            return False

    # ============================================================
    # GEOCODE
    # ============================================================

    @http.route(
        (
            "/api/app/services/<int:service_id>"
            "/evidences/geocode"
        ),
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def service_evidence_geocode(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            data = (
                self._get_json_body()
            )

            latitude = (
                self._service_safe_float(
                    data.get(
                        "latitude"
                    )
                    or
                    data.get(
                        "lat"
                    )
                )
            )

            longitude = (
                self._service_safe_float(
                    data.get(
                        "longitude"
                    )
                    or
                    data.get(
                        "lng"
                    )
                )
            )

            if (
                not latitude
                or
                not longitude
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "INVALID_COORDINATES"
                        ),
                        "message": (
                            "Las coordenadas "
                            "no son válidas."
                        ),
                    },
                    status=400,
                )

            address = (
                self._service_traccar_address(
                    latitude,
                    longitude,
                )
            )

            provider = (
                "traccar_positions"
                if address
                else False
            )

            if not address:
                address = (
                    self._service_nominatim_address(
                        latitude,
                        longitude,
                    )
                )

                if address:
                    provider = (
                        "nominatim"
                    )

            if not address:
                address = (
                    "Lat: "
                    f"{latitude:.6f}, "
                    "Lng: "
                    f"{longitude:.6f}"
                )

                provider = (
                    "fallback_coords"
                )

            return self._json_response(
                {
                    "success": True,

                    "provider": (
                        provider
                    ),

                    "address": (
                        address
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # CHANGE STATE
    # ============================================================

    @http.route(
        "/api/app/services/<int:service_id>/state",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def service_state(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            data = (
                self._get_json_body()
            )

            new_state = (
                str(
                    data.get(
                        "state"
                    )
                    or ""
                ).strip()
            )

            transitions = {
                "proceso": {
                    "en_ruta",
                },

                "en_ruta": {
                    "en_sitio",
                },

                "en_sitio": {
                    "en_revision",
                },
            }

            allowed_next = (
                transitions.get(
                    ticket.estado,
                    set(),
                )
            )

            if (
                new_state
                not in allowed_next
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "INVALID_STATE_TRANSITION"
                        ),
                        "message": (
                            "No se puede cambiar "
                            f"de {ticket.estado} "
                            f"a {new_state}."
                        ),
                    },
                    status=400,
                )

            ticket.write(
                {
                    "estado": (
                        new_state
                    ),
                }
            )

            ticket.message_post(
                body=(
                    "Estado actualizado desde "
                    "Copier OS App: "
                    f"{self._selection_label(ticket, 'estado')}"
                ),
                message_type=(
                    "notification"
                ),
            )

            return self._json_response(
                {
                    "success": True,

                    "state": (
                        ticket.estado
                    ),

                    "state_label": (
                        self._selection_label(
                            ticket,
                            "estado",
                        )
                    ),

                    "service": (
                        self._service_serialize_service_detail(
                            ticket
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )

    # ============================================================
    # FINALIZE
    # ============================================================

    @http.route(
        "/api/app/services/<int:service_id>/finalize",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def service_finalize(
        self,
        service_id,
        **kwargs,
    ):
        user, error = (
            self._require_user()
        )

        if error:
            return error

        try:
            ticket = (
                self._service_get_service(
                    service_id,
                    user,
                )
            )

            if not ticket:
                return (
                    self._service_not_found_response()
                )

            if (
                ticket.estado
                == "finalizado"
            ):
                return self._json_response(
                    {
                        "success": True,

                        "message": (
                            "El servicio ya se "
                            "encuentra finalizado."
                        ),

                        "service": (
                            self._service_serialize_service_detail(
                                ticket
                            )
                        ),
                    }
                )

            # ----------------------------------------------------
            # EVITAR QUE ODOO DEVUELVA UN WIZARD
            # QUE FLUTTER NO PUEDE MOSTRAR
            # ----------------------------------------------------

            if hasattr(
                ticket,
                (
                    "_get_componentes_"
                    "requieren_cambio_"
                    "sin_subpartes"
                ),
            ):
                pending = (
                    ticket
                    ._get_componentes_requieren_cambio_sin_subpartes()
                )

                if pending:
                    return self._json_response(
                        {
                            "success": False,

                            "code": (
                                "SUBPARTS_REQUIRED"
                            ),

                            "message": (
                                "Hay componentes "
                                "o accesorios que "
                                "requieren cambio "
                                "y todavía no tienen "
                                "subpartes seleccionadas."
                            ),

                            "pending": (
                                pending
                            ),
                        },
                        status=400,
                    )

            if not hasattr(
                ticket,
                "action_finalizar",
            ):
                raise UserError(
                    "El modelo no dispone "
                    "de action_finalizar()."
                )

            ticket.action_finalizar()

            try:
                ticket.invalidate_recordset()
            except Exception:
                pass

            if (
                ticket.estado
                != "finalizado"
            ):
                return self._json_response(
                    {
                        "success": False,

                        "code": (
                            "SERVICE_NOT_FINALIZED"
                        ),

                        "message": (
                            "Odoo ejecutó la "
                            "validación pero el "
                            "servicio todavía no "
                            "quedó finalizado."
                        ),

                        "service": (
                            self._service_serialize_service_detail(
                                ticket
                            )
                        ),
                    },
                    status=400,
                )

            return self._json_response(
                {
                    "success": True,

                    "message": (
                        "Servicio finalizado "
                        "correctamente."
                    ),

                    "service": (
                        self._service_serialize_service_detail(
                            ticket
                        )
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(
                exc
            )