# -*- coding: utf-8 -*-

import base64
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from .base import AppBaseController


_logger = logging.getLogger(__name__)


class AppRepairController(AppBaseController):

    REPAIR_MODEL = "reparaciones.reparaciones"
    COMPONENT_EVAL_MODEL = "reparacion.componente.evaluacion"
    ACCESSORY_EVAL_MODEL = "reparacion.accesorio.evaluacion"
    INTERVENTION_MODEL = "reparacion.intervencion"
    INTERVENTION_DETAIL_MODEL = "reparacion.intervencion.detalle"
    PHOTO_MODEL = "reparaciones.foto"

    FINAL_STATES = {"finalizado", "entregada"}

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/repairs",
            "/api/app/repairs/summary",
            "/api/app/repairs/<int:repair_id>",
            "/api/app/repairs/<int:repair_id>/state",
            "/api/app/repairs/<int:repair_id>/finalize",
            "/api/app/repairs/<int:repair_id>/checklist",
            "/api/app/repairs/<int:repair_id>/components/<int:evaluation_id>",
            "/api/app/repairs/<int:repair_id>/accessories/<int:evaluation_id>",
            "/api/app/repairs/<int:repair_id>/components/<int:evaluation_id>/subparts",
            "/api/app/repairs/<int:repair_id>/accessories/<int:evaluation_id>/subparts",
            "/api/app/repairs/<int:repair_id>/interventions",
            "/api/app/repairs/<int:repair_id>/interventions/<int:intervention_id>",
            "/api/app/repairs/<int:repair_id>/photos",
            "/api/app/repairs/<int:repair_id>/photos/<int:photo_id>",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def repair_options(
        self,
        repair_id=None,
        evaluation_id=None,
        intervention_id=None,
        photo_id=None,
        **kwargs,
    ):
        return self._options_response()

    # ============================================================
    # GENERIC HELPERS
    # ============================================================

    def _model_exists(self, model_name):
        return model_name in request.env.registry

    def _safe_value(self, record, field_name, default=False):
        if record and field_name in record._fields:
            return record[field_name]
        return default

    def _safe_text(self, value):
        if value in (None, False):
            return ""
        return str(value)

    def _many2one_or_false(self, record, field_name):
        if (
            field_name not in record._fields
            or not record[field_name]
        ):
            return False
        return self._many2one(record[field_name])

    def _record_code(self, record):
        if not record:
            return ""

        for field_name in ("code", "codigo", "default_code"):
            if (
                field_name in record._fields
                and record[field_name]
            ):
                return str(record[field_name])

        return ""

    def _selection_options(self, record, field_name):
        if field_name not in record._fields:
            return []

        selection = record._fields[field_name].selection
        if callable(selection):
            selection = selection(record)

        return [
            {"value": value, "label": label}
            for value, label in (selection or [])
        ]

    def _many2one_options(self, record, field_name):
        if field_name not in record._fields:
            return []

        field = record._fields[field_name]
        if field.type != "many2one":
            return []

        model_name = field.comodel_name
        if not model_name or not self._model_exists(model_name):
            return []

        Model = request.env[model_name]
        domain = []

        if "active" in Model._fields:
            domain.append(("active", "=", True))

        records = Model.search(domain, order="id asc")

        result = []
        for item in records:
            code = self._record_code(item)
            result.append(
                {
                    "id": item.id,
                    "name": item.display_name,
                    "code": code,
                    "requires_change": code == "requiere_cambio",
                }
            )

        return result

    # ============================================================
    # DATE HELPERS
    # Reparaciones no tiene agenda propia.
    # Hoy/mes actual/mes pasado se calculan por create_date.
    # Finalizados se calculan por fecha_finalizacion.
    # ============================================================

    def _timezone(self, user):
        try:
            return pytz.timezone(
                user.tz or "America/Lima"
            )
        except Exception:
            return pytz.timezone("America/Lima")

    def _local_range_to_utc(
        self,
        timezone,
        start_date,
        end_date,
    ):
        start_local = timezone.localize(
            datetime.combine(start_date, time.min)
        )
        end_local = timezone.localize(
            datetime.combine(end_date, time.max)
        )

        start_utc = (
            start_local.astimezone(pytz.UTC)
            .replace(tzinfo=None)
        )
        end_utc = (
            end_local.astimezone(pytz.UTC)
            .replace(tzinfo=None)
        )

        return (
            fields.Datetime.to_string(start_utc),
            fields.Datetime.to_string(end_utc),
        )

    def _today_range(self, user):
        timezone = self._timezone(user)
        today = datetime.now(timezone).date()
        return self._local_range_to_utc(
            timezone,
            today,
            today,
        )

    def _month_ranges(self, user):
        timezone = self._timezone(user)
        today = datetime.now(timezone).date()

        current_start = today.replace(day=1)

        if current_start.month == 12:
            next_start = current_start.replace(
                year=current_start.year + 1,
                month=1,
            )
        else:
            next_start = current_start.replace(
                month=current_start.month + 1,
            )

        current_end = next_start - timedelta(days=1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end.replace(day=1)

        return {
            "current": self._local_range_to_utc(
                timezone,
                current_start,
                current_end,
            ),
            "previous": self._local_range_to_utc(
                timezone,
                previous_start,
                previous_end,
            ),
        }

    # ============================================================
    # SECURITY
    # ============================================================

    def _get_repair(self, repair_id, user):
        return request.env[self.REPAIR_MODEL].search(
            [
                ("id", "=", repair_id),
                ("responsable_id", "=", user.id),
            ],
            limit=1,
        )

    def _repair_or_error(self, repair_id, user):
        repair = self._get_repair(repair_id, user)

        if repair:
            return repair, None

        return None, self._json_response(
            {
                "success": False,
                "code": "REPAIR_NOT_FOUND",
                "message": (
                    "La reparación no existe o "
                    "no está asignada al usuario."
                ),
            },
            status=404,
        )

    def _is_finalized(self, repair):
        return repair.estado_id in self.FINAL_STATES

    # ============================================================
    # SUBPARTS
    # ============================================================

    def _serialize_subpart(self, subpart):
        result = {
            "id": subpart.id,
            "name": subpart.display_name,
        }

        for field_name in (
            "default_code",
            "codigo",
            "code",
        ):
            if field_name in subpart._fields:
                result["code"] = (
                    subpart[field_name] or ""
                )
                break

        return result

    def _available_component_subparts(self, evaluation):
        if (
            "subpartes_ids" not in evaluation._fields
            or not evaluation.componente_tipo_id
        ):
            return request.env[
                evaluation._fields[
                    "subpartes_ids"
                ].comodel_name
            ].browse([]) if "subpartes_ids" in evaluation._fields else []

        model_name = (
            evaluation._fields[
                "subpartes_ids"
            ].comodel_name
        )
        Model = request.env[model_name]
        domain = []

        if "tipo_id" in Model._fields:
            domain.append(
                (
                    "tipo_id",
                    "=",
                    evaluation.componente_tipo_id.id,
                )
            )

        if (
            "color_id" in Model._fields
            and evaluation.color_id
        ):
            domain.append(
                (
                    "color_id",
                    "in",
                    [False, evaluation.color_id.id],
                )
            )

        if "active" in Model._fields:
            domain.append(("active", "=", True))

        return Model.search(domain, order="id asc")

    def _available_accessory_subparts(self, evaluation):
        if "subparte_ids" not in evaluation._fields:
            return []

        model_name = (
            evaluation._fields[
                "subparte_ids"
            ].comodel_name
        )
        Model = request.env[model_name]
        domain = []

        if "tipo_id" in Model._fields and evaluation.tipo_id:
            domain.append(
                ("tipo_id", "=", evaluation.tipo_id.id)
            )

        if "active" in Model._fields:
            domain.append(("active", "=", True))

        return Model.search(domain, order="id asc")

    # ============================================================
    # CHECKLIST SERIALIZERS
    # ============================================================

    def _serialize_component(
        self,
        item,
        include_options=False,
    ):
        state_code = (
            self._record_code(item.estado_id)
            if item.estado_id
            else ""
        )

        selected = [
            self._serialize_subpart(subpart)
            for subpart in item.subpartes_ids
        ]

        result = {
            "id": item.id,
            "component": self._many2one_or_false(
                item,
                "componente_tipo_id",
            ),
            "color": self._many2one_or_false(
                item,
                "color_id",
            ),
            "state": self._many2one_or_false(
                item,
                "estado_id",
            ),
            "state_code": state_code,
            "requires_change": (
                state_code == "requiere_cambio"
            ),
            "observations": (
                item.observaciones or ""
            ),
            "selected_subparts": selected,
        }

        if include_options:
            result["state_options"] = (
                self._many2one_options(
                    item,
                    "estado_id",
                )
            )
            result["available_subparts"] = [
                self._serialize_subpart(subpart)
                for subpart
                in self._available_component_subparts(
                    item
                )
            ]

        return result

    def _serialize_accessory(
        self,
        item,
        include_options=False,
    ):
        state_code = (
            self._record_code(item.estado_id)
            if item.estado_id
            else ""
        )

        selected = [
            self._serialize_subpart(subpart)
            for subpart in item.subparte_ids
        ]

        result = {
            "id": item.id,
            "accessory": self._many2one_or_false(
                item,
                "tipo_id",
            ),
            "state": self._many2one_or_false(
                item,
                "estado_id",
            ),
            "state_code": state_code,
            "requires_change": (
                state_code == "requiere_cambio"
            ),
            "observations": (
                item.observaciones or ""
            ),
            "selected_subparts": selected,
        }

        if include_options:
            result["state_options"] = (
                self._many2one_options(
                    item,
                    "estado_id",
                )
            )
            result["available_subparts"] = [
                self._serialize_subpart(subpart)
                for subpart
                in self._available_accessory_subparts(
                    item
                )
            ]

        return result

    # ============================================================
    # PHOTOS
    # Originales únicamente. Sin GPS, sin watermark.
    # ============================================================

    def _serialize_photo(self, photo):
        return {
            "id": photo.id,
            "name": photo.nombre_foto or "",
            "sequence": photo.sequence or 0,
            "state": photo.state or "",
            "size": photo.size or 0,
            "mimetype": photo.mimetype or "",
            "file_id": photo.file_id or "",
            "url": photo.url_foto or "",
            "public_link": photo.public_link or "",
            "thumb_url": photo.thumb_url or "",
            "created_at": (
                fields.Datetime.to_string(
                    photo.create_date
                )
                if photo.create_date
                else False
            ),
        }

    # ============================================================
    # INTERVENTIONS
    # ============================================================

    def _serialize_intervention_detail(self, detail):
        return {
            "id": detail.id,
            "subpart": self._many2one_or_false(
                detail,
                "subparte_id",
            ),
            "action": detail.accion_sub or "",
            "code": detail.codigo or "",
            "quantity": detail.cantidad or 0.0,
            "note": detail.nota or "",
        }

    def _serialize_intervention(self, item):
        return {
            "id": item.id,
            "component": item.componente or "",
            "component_code": (
                item.componente_code or ""
            ),
            "component_name": (
                item.componente_display or ""
            ),
            "action": item.accion or "",
            "observation": item.observacion or "",
            "is_replacement": bool(item.es_cambio),
            "details": [
                self._serialize_intervention_detail(
                    detail
                )
                for detail in item.detalle_ids
            ],
        }

    # ============================================================
    # REPAIR SERIALIZER
    # ============================================================

    def _serialize_repair(
        self,
        repair,
        detail=False,
    ):
        result = {
            "id": repair.id,
            "reference": repair.name or "",
            "state": repair.estado_id or "",
            "state_label": self._selection_label(
                repair,
                "estado_id",
            ),
            "finalized": self._is_finalized(repair),
            "responsible": self._many2one_or_false(
                repair,
                "responsable_id",
            ),
            "machine": self._many2one_or_false(
                repair,
                "maquina_id",
            ),
            "serial": repair.serie_id or "",
            "client": self._many2one_or_false(
                repair,
                "cliente_id",
            ),
            "priority": (
                repair.prioridad
                if "prioridad" in repair._fields
                else ""
            ) or "",
            "revision_type": (
                repair.tipo_revision
                if "tipo_revision" in repair._fields
                else ""
            ) or "",
            "location": (
                repair.ubicacion_id
                if "ubicacion_id" in repair._fields
                else ""
            ) or "",
            "meter_initial": (
                repair.contometro_inicial or ""
            ),
            "meter_current": (
                repair.contometrok_id or ""
            ),
            "created_at": (
                fields.Datetime.to_string(
                    repair.create_date
                )
                if repair.create_date
                else False
            ),
            "finish_date": (
                fields.Datetime.to_string(
                    repair.fecha_finalizacion
                )
                if (
                    "fecha_finalizacion"
                    in repair._fields
                    and repair.fecha_finalizacion
                )
                else False
            ),
            "photos_count": (
                len(repair.fotos_ids)
                if "fotos_ids" in repair._fields
                else 0
            ),
            "minimum_photos": 10,
        }

        if not detail:
            return result

        components = [
            self._serialize_component(
                item,
                include_options=True,
            )
            for item in repair.componente_eval_ids
        ]

        accessories = [
            self._serialize_accessory(
                item,
                include_options=True,
            )
            for item in repair.accesorio_eval_ids
        ]

        photos = [
            self._serialize_photo(photo)
            for photo in repair.fotos_ids.sorted(
                key=lambda photo: (
                    photo.sequence,
                    photo.id,
                )
            )
        ]

        interventions = []
        if self._model_exists(
            self.INTERVENTION_MODEL
        ):
            interventions = [
                self._serialize_intervention(item)
                for item
                in request.env[
                    self.INTERVENTION_MODEL
                ].search(
                    [
                        (
                            "reparacion_id",
                            "=",
                            repair.id,
                        )
                    ],
                    order="id desc",
                )
            ]

        result.update(
            {
                "report": repair.informe or "",
                "quality": (
                    repair.calidad_id
                    if "calidad_id"
                    in repair._fields
                    else ""
                ) or "",
                "quality_label": (
                    self._selection_label(
                        repair,
                        "calidad_id",
                    )
                    if "calidad_id"
                    in repair._fields
                    else ""
                ),
                "quality_options": (
                    self._selection_options(
                        repair,
                        "calidad_id",
                    )
                    if "calidad_id"
                    in repair._fields
                    else []
                ),
                "state_options": (
                    self._selection_options(
                        repair,
                        "estado_id",
                    )
                ),
                "components": components,
                "accessories": accessories,
                "interventions": interventions,
                "photos": photos,
                "parts_requests_count": (
                    len(repair.parts_request_ids)
                    if "parts_request_ids"
                    in repair._fields
                    else 0
                ),
                "checklist_summary": {
                    "components_total": len(components),
                    "components_completed": sum(
                        1
                        for item in components
                        if item["state"]
                    ),
                    "accessories_total": len(accessories),
                    "accessories_completed": sum(
                        1
                        for item in accessories
                        if item["state"]
                    ),
                },
                "photo_summary": {
                    "current": len(photos),
                    "minimum": 10,
                    "missing": max(
                        0,
                        10 - len(photos),
                    ),
                    "complete": len(photos) >= 10,
                },
            }
        )

        return result

    # ============================================================
    # SUMMARY
    # ============================================================

    def _build_summary(self, user):
        Repair = request.env[self.REPAIR_MODEL]

        base_domain = [
            ("responsable_id", "=", user.id)
        ]

        today_start, today_end = (
            self._today_range(user)
        )
        ranges = self._month_ranges(user)
        current_start, current_end = (
            ranges["current"]
        )
        previous_start, previous_end = (
            ranges["previous"]
        )

        def count_created(start, end):
            return Repair.search_count(
                base_domain
                + [
                    ("create_date", ">=", start),
                    ("create_date", "<=", end),
                ]
            )

        def count_finished(start, end):
            return Repair.search_count(
                base_domain
                + [
                    (
                        "fecha_finalizacion",
                        ">=",
                        start,
                    ),
                    (
                        "fecha_finalizacion",
                        "<=",
                        end,
                    ),
                ]
            )

        active = Repair.search_count(
            base_domain
            + [
                (
                    "estado_id",
                    "not in",
                    list(self.FINAL_STATES),
                )
            ]
        )

        by_state = {}
        selection = (
            Repair._fields["estado_id"].selection
        )
        if callable(selection):
            selection = selection(Repair)

        for value, label in (selection or []):
            by_state[value] = {
                "label": label,
                "count": Repair.search_count(
                    base_domain
                    + [
                        (
                            "estado_id",
                            "=",
                            value,
                        )
                    ]
                ),
            }

        return {
            "active": active,
            "created_today": count_created(
                today_start,
                today_end,
            ),
            "current_month": count_created(
                current_start,
                current_end,
            ),
            "previous_month": count_created(
                previous_start,
                previous_end,
            ),
            "finalized_today": count_finished(
                today_start,
                today_end,
            ),
            "finalized_current_month": (
                count_finished(
                    current_start,
                    current_end,
                )
            ),
            "finalized_previous_month": (
                count_finished(
                    previous_start,
                    previous_end,
                )
            ),
            "by_state": by_state,
        }

    # ============================================================
    # LIST
    # period:
    # today | current_month | previous_month | active
    # ============================================================

    @http.route(
        "/api/app/repairs",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def repairs(self, **kwargs):
        user, error = self._require_user()
        if error:
            return error

        try:
            args = request.httprequest.args

            state = args.get("state")
            search_term = (
                args.get("search") or ""
            ).strip()
            period = (
                args.get("period") or ""
            ).strip()

            domain = [
                ("responsable_id", "=", user.id)
            ]

            if state:
                domain.append(
                    ("estado_id", "=", state)
                )

            if search_term:
                domain.extend(
                    [
                        "|",
                        "|",
                        (
                            "name",
                            "ilike",
                            search_term,
                        ),
                        (
                            "serie_id",
                            "ilike",
                            search_term,
                        ),
                        (
                            "cliente_id.name",
                            "ilike",
                            search_term,
                        ),
                    ]
                )

            if period == "active":
                domain.append(
                    (
                        "estado_id",
                        "not in",
                        list(self.FINAL_STATES),
                    )
                )

            elif period == "today":
                start, end = self._today_range(
                    user
                )
                domain.extend(
                    [
                        (
                            "create_date",
                            ">=",
                            start,
                        ),
                        (
                            "create_date",
                            "<=",
                            end,
                        ),
                    ]
                )

            elif period in (
                "current_month",
                "previous_month",
            ):
                key = (
                    "current"
                    if period == "current_month"
                    else "previous"
                )
                start, end = (
                    self._month_ranges(user)[key]
                )
                domain.extend(
                    [
                        (
                            "create_date",
                            ">=",
                            start,
                        ),
                        (
                            "create_date",
                            "<=",
                            end,
                        ),
                    ]
                )

            records = request.env[
                self.REPAIR_MODEL
            ].search(
                domain,
                order="id desc",
                limit=200,
            )

            return self._json_response(
                {
                    "success": True,
                    "count": len(records),
                    "summary": self._build_summary(
                        user
                    ),
                    "items": [
                        self._serialize_repair(
                            record
                        )
                        for record in records
                    ],
                }
            )

        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # SUMMARY ENDPOINT
    # ============================================================

    @http.route(
        "/api/app/repairs/summary",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def repair_summary(self, **kwargs):
        user, error = self._require_user()
        if error:
            return error

        try:
            return self._json_response(
                {
                    "success": True,
                    "summary": self._build_summary(
                        user
                    ),
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # DETAIL
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def repair_detail(
        self,
        repair_id,
        **kwargs,
    ):
        user, error = self._require_user()
        if error:
            return error

        try:
            repair, error = (
                self._repair_or_error(
                    repair_id,
                    user,
                )
            )
            if error:
                return error

            return self._json_response(
                {
                    "success": True,
                    "repair": self._serialize_repair(
                        repair,
                        detail=True,
                    ),
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # GENERAL UPDATE
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def repair_update(
        self,
        repair_id,
        **kwargs,
    ):
        user, error = self._require_user()
        if error:
            return error

        try:
            repair, error = (
                self._repair_or_error(
                    repair_id,
                    user,
                )
            )
            if error:
                return error

            if self._is_finalized(repair):
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_READ_ONLY",
                        "message": (
                            "La reparación finalizada "
                            "es de solo lectura."
                        ),
                    },
                    status=409,
                )

            data = self._get_json_body()

            allowed = {
                "informe",
                "contometrok_id",
                "calidad_id",
            }

            vals = {}
            for field_name in allowed:
                if (
                    field_name in data
                    and field_name
                    in repair._fields
                ):
                    vals[field_name] = (
                        data[field_name]
                    )

            if not vals:
                return self._json_response(
                    {
                        "success": False,
                        "code": "NO_DATA",
                        "message": (
                            "No existen campos válidos "
                            "para actualizar."
                        ),
                    },
                    status=400,
                )

            repair.write(vals)

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Reparación actualizada "
                        "correctamente."
                    ),
                    "repair": self._serialize_repair(
                        repair,
                        detail=True,
                    ),
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # STATE UPDATE
    # Finalizado siempre usa /finalize.
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>/state",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def repair_change_state(
        self,
        repair_id,
        **kwargs,
    ):
        user, error = self._require_user()
        if error:
            return error

        try:
            repair, error = (
                self._repair_or_error(
                    repair_id,
                    user,
                )
            )
            if error:
                return error

            if self._is_finalized(repair):
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_READ_ONLY",
                        "message": (
                            "La reparación finalizada "
                            "es de solo lectura."
                        ),
                    },
                    status=409,
                )

            data = self._get_json_body()
            new_state = (
                data.get("state") or ""
            ).strip()

            valid_states = {
                item["value"]
                for item
                in self._selection_options(
                    repair,
                    "estado_id",
                )
            }

            if new_state not in valid_states:
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_STATE",
                        "message": (
                            "El estado solicitado "
                            "no es válido."
                        ),
                    },
                    status=400,
                )

            if new_state == "finalizado":
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "USE_FINALIZE_ENDPOINT"
                        ),
                        "message": (
                            "Para finalizar usa "
                            "/finalize."
                        ),
                    },
                    status=400,
                )

            repair.write(
                {"estado_id": new_state}
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Estado actualizado "
                        "correctamente."
                    ),
                    "repair": self._serialize_repair(
                        repair,
                        detail=True,
                    ),
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # CHECKLIST
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>/checklist",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def repair_checklist(
        self,
        repair_id,
        **kwargs,
    ):
        user, error = self._require_user()
        if error:
            return error

        try:
            repair, error = (
                self._repair_or_error(
                    repair_id,
                    user,
                )
            )
            if error:
                return error

            components = [
                self._serialize_component(
                    item,
                    include_options=True,
                )
                for item
                in repair.componente_eval_ids
            ]
            accessories = [
                self._serialize_accessory(
                    item,
                    include_options=True,
                )
                for item
                in repair.accesorio_eval_ids
            ]

            return self._json_response(
                {
                    "success": True,
                    "read_only": (
                        self._is_finalized(repair)
                    ),
                    "components": components,
                    "accessories": accessories,
                    "summary": {
                        "components_total": (
                            len(components)
                        ),
                        "components_completed": sum(
                            1
                            for item in components
                            if item["state"]
                        ),
                        "accessories_total": (
                            len(accessories)
                        ),
                        "accessories_completed": sum(
                            1
                            for item in accessories
                            if item["state"]
                        ),
                    },
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # COMPONENT UPDATE
    # state_id, observations, subpart_ids[]
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>/components/<int:evaluation_id>",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def repair_component_update(
        self,
        repair_id,
        evaluation_id,
        **kwargs,
    ):
        user, error = self._require_user()
        if error:
            return error

        try:
            repair, error = (
                self._repair_or_error(
                    repair_id,
                    user,
                )
            )
            if error:
                return error

            if self._is_finalized(repair):
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_READ_ONLY",
                        "message": (
                            "La reparación finalizada "
                            "es de solo lectura."
                        ),
                    },
                    status=409,
                )

            evaluation = request.env[
                self.COMPONENT_EVAL_MODEL
            ].search(
                [
                    ("id", "=", evaluation_id),
                    (
                        "reparacion_id",
                        "=",
                        repair.id,
                    ),
                ],
                limit=1,
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

            data = self._get_json_body()
            vals = {}

            if "state_id" in data:
                state_id = int(
                    data.get("state_id") or 0
                )
                vals["estado_id"] = (
                    state_id or False
                )

            if "observations" in data:
                vals["observaciones"] = (
                    data.get("observations")
                    or ""
                )

            if "subpart_ids" in data:
                ids = [
                    int(item)
                    for item in (
                        data.get("subpart_ids")
                        or []
                    )
                    if int(item) > 0
                ]

                allowed = set(
                    self._available_component_subparts(
                        evaluation
                    ).ids
                )

                if any(
                    item not in allowed
                    for item in ids
                ):
                    raise ValidationError(
                        "Hay subpartes que no "
                        "pertenecen al componente."
                    )

                vals["subpartes_ids"] = [
                    (6, 0, ids)
                ]

            if not vals:
                return self._json_response(
                    {
                        "success": False,
                        "code": "NO_DATA",
                        "message": (
                            "No existen cambios válidos."
                        ),
                    },
                    status=400,
                )

            evaluation.write(vals)

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Componente actualizado "
                        "correctamente."
                    ),
                    "item": self._serialize_component(
                        evaluation,
                        include_options=True,
                    ),
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # ACCESSORY UPDATE
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>/accessories/<int:evaluation_id>",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
        save_session=True,
    )
    def repair_accessory_update(
        self,
        repair_id,
        evaluation_id,
        **kwargs,
    ):
        user, error = self._require_user()
        if error:
            return error

        try:
            repair, error = (
                self._repair_or_error(
                    repair_id,
                    user,
                )
            )
            if error:
                return error

            if self._is_finalized(repair):
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_READ_ONLY",
                        "message": (
                            "La reparación finalizada "
                            "es de solo lectura."
                        ),
                    },
                    status=409,
                )

            evaluation = request.env[
                self.ACCESSORY_EVAL_MODEL
            ].search(
                [
                    ("id", "=", evaluation_id),
                    (
                        "reparacion_id",
                        "=",
                        repair.id,
                    ),
                ],
                limit=1,
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

            data = self._get_json_body()
            vals = {}

            if "state_id" in data:
                state_id = int(
                    data.get("state_id") or 0
                )
                vals["estado_id"] = (
                    state_id or False
                )

            if "observations" in data:
                vals["observaciones"] = (
                    data.get("observations")
                    or ""
                )

            if "subpart_ids" in data:
                ids = [
                    int(item)
                    for item in (
                        data.get("subpart_ids")
                        or []
                    )
                    if int(item) > 0
                ]

                allowed = set(
                    self._available_accessory_subparts(
                        evaluation
                    ).ids
                )

                if any(
                    item not in allowed
                    for item in ids
                ):
                    raise ValidationError(
                        "Hay subpartes que no "
                        "pertenecen al accesorio."
                    )

                vals["subparte_ids"] = [
                    (6, 0, ids)
                ]

            if not vals:
                return self._json_response(
                    {
                        "success": False,
                        "code": "NO_DATA",
                        "message": (
                            "No existen cambios válidos."
                        ),
                    },
                    status=400,
                )

            evaluation.write(vals)

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Accesorio actualizado "
                        "correctamente."
                    ),
                    "item": self._serialize_accessory(
                        evaluation,
                        include_options=True,
                    ),
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # COMPONENT SUBPARTS
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>/components/<int:evaluation_id>/subparts",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def repair_component_subparts(
        self,
        repair_id,
        evaluation_id,
        **kwargs,
    ):
        user, error = self._require_user()
        if error:
            return error

        try:
            repair, error = (
                self._repair_or_error(
                    repair_id,
                    user,
                )
            )
            if error:
                return error

            evaluation = request.env[
                self.COMPONENT_EVAL_MODEL
            ].search(
                [
                    ("id", "=", evaluation_id),
                    (
                        "reparacion_id",
                        "=",
                        repair.id,
                    ),
                ],
                limit=1,
            )

            if not evaluation:
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "COMPONENT_NOT_FOUND"
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "selected": [
                        self._serialize_subpart(item)
                        for item
                        in evaluation.subpartes_ids
                    ],
                    "available": [
                        self._serialize_subpart(item)
                        for item
                        in self._available_component_subparts(
                            evaluation
                        )
                    ],
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # ACCESSORY SUBPARTS
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>/accessories/<int:evaluation_id>/subparts",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def repair_accessory_subparts(
        self,
        repair_id,
        evaluation_id,
        **kwargs,
    ):
        user, error = self._require_user()
        if error:
            return error

        try:
            repair, error = (
                self._repair_or_error(
                    repair_id,
                    user,
                )
            )
            if error:
                return error

            evaluation = request.env[
                self.ACCESSORY_EVAL_MODEL
            ].search(
                [
                    ("id", "=", evaluation_id),
                    (
                        "reparacion_id",
                        "=",
                        repair.id,
                    ),
                ],
                limit=1,
            )

            if not evaluation:
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "ACCESSORY_NOT_FOUND"
                        ),
                    },
                    status=404,
                )

            return self._json_response(
                {
                    "success": True,
                    "selected": [
                        self._serialize_subpart(item)
                        for item
                        in evaluation.subparte_ids
                    ],
                    "available": [
                        self._serialize_subpart(item)
                        for item
                        in self._available_accessory_subparts(
                            evaluation
                        )
                    ],
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # INTERVENTIONS GET / POST
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>/interventions",
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
        save_session=True,
    )
    def repair_interventions(
        self,
        repair_id,
        **kwargs,
    ):
        user, error = self._require_user()
        if error:
            return error

        try:
            repair, error = (
                self._repair_or_error(
                    repair_id,
                    user,
                )
            )
            if error:
                return error

            Intervention = request.env[
                self.INTERVENTION_MODEL
            ]

            if request.httprequest.method == "GET":
                records = Intervention.search(
                    [
                        (
                            "reparacion_id",
                            "=",
                            repair.id,
                        )
                    ],
                    order="id desc",
                )

                return self._json_response(
                    {
                        "success": True,
                        "count": len(records),
                        "items": [
                            self._serialize_intervention(
                                item
                            )
                            for item in records
                        ],
                    }
                )

            if self._is_finalized(repair):
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_READ_ONLY",
                        "message": (
                            "La reparación finalizada "
                            "es de solo lectura."
                        ),
                    },
                    status=409,
                )

            data = self._get_json_body()

            vals = {
                "reparacion_id": repair.id,
                "componente": (
                    data.get("component")
                    or False
                ),
                "componente_code": (
                    data.get("component_code")
                    or ""
                ),
                "accion": (
                    data.get("action")
                    or "cambiado"
                ),
                "observacion": (
                    data.get("observation")
                    or ""
                ),
            }

            intervention = Intervention.create(
                vals
            )

            Detail = request.env[
                self.INTERVENTION_DETAIL_MODEL
            ]

            for detail in (
                data.get("details") or []
            ):
                subpart_id = int(
                    detail.get("subpart_id") or 0
                )
                if not subpart_id:
                    continue

                Detail.create(
                    {
                        "line_id": intervention.id,
                        "subparte_id": subpart_id,
                        "accion_sub": (
                            detail.get("action")
                            or "cambiado"
                        ),
                        "codigo": (
                            detail.get("code")
                            or ""
                        ),
                        "cantidad": float(
                            detail.get("quantity")
                            or 1.0
                        ),
                        "nota": (
                            detail.get("note")
                            or ""
                        ),
                    }
                )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Intervención registrada "
                        "correctamente."
                    ),
                    "item": self._serialize_intervention(
                        intervention
                    ),
                },
                status=201,
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # INTERVENTION PATCH / DELETE
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>/interventions/<int:intervention_id>",
        type="http",
        auth="public",
        methods=["PATCH", "DELETE"],
        csrf=False,
        save_session=True,
    )
    def repair_intervention_detail(
        self,
        repair_id,
        intervention_id,
        **kwargs,
    ):
        user, error = self._require_user()
        if error:
            return error

        try:
            repair, error = (
                self._repair_or_error(
                    repair_id,
                    user,
                )
            )
            if error:
                return error

            if self._is_finalized(repair):
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_READ_ONLY",
                        "message": (
                            "La reparación finalizada "
                            "es de solo lectura."
                        ),
                    },
                    status=409,
                )

            intervention = request.env[
                self.INTERVENTION_MODEL
            ].search(
                [
                    ("id", "=", intervention_id),
                    (
                        "reparacion_id",
                        "=",
                        repair.id,
                    ),
                ],
                limit=1,
            )

            if not intervention:
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "INTERVENTION_NOT_FOUND"
                        ),
                    },
                    status=404,
                )

            if (
                request.httprequest.method
                == "DELETE"
            ):
                intervention.unlink()
                return self._json_response(
                    {
                        "success": True,
                        "message": (
                            "Intervención eliminada "
                            "correctamente."
                        ),
                    }
                )

            data = self._get_json_body()
            vals = {}

            mapping = {
                "component": "componente",
                "component_code": (
                    "componente_code"
                ),
                "action": "accion",
                "observation": "observacion",
            }

            for api_name, field_name in (
                mapping.items()
            ):
                if api_name in data:
                    vals[field_name] = data[
                        api_name
                    ]

            if vals:
                intervention.write(vals)

            if "details" in data:
                intervention.detalle_ids.unlink()

                Detail = request.env[
                    self.INTERVENTION_DETAIL_MODEL
                ]

                for detail in (
                    data.get("details") or []
                ):
                    subpart_id = int(
                        detail.get(
                            "subpart_id"
                        ) or 0
                    )
                    if not subpart_id:
                        continue

                    Detail.create(
                        {
                            "line_id": (
                                intervention.id
                            ),
                            "subparte_id": (
                                subpart_id
                            ),
                            "accion_sub": (
                                detail.get(
                                    "action"
                                )
                                or "cambiado"
                            ),
                            "codigo": (
                                detail.get("code")
                                or ""
                            ),
                            "cantidad": float(
                                detail.get(
                                    "quantity"
                                )
                                or 1.0
                            ),
                            "nota": (
                                detail.get("note")
                                or ""
                            ),
                        }
                    )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Intervención actualizada "
                        "correctamente."
                    ),
                    "item": self._serialize_intervention(
                        intervention
                    ),
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # PHOTOS GET / POST
    # SOLO ORIGINAL.
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>/photos",
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
        save_session=True,
    )
    def repair_photos(
        self,
        repair_id,
        **kwargs,
    ):
        user, error = self._require_user()
        if error:
            return error

        try:
            repair, error = (
                self._repair_or_error(
                    repair_id,
                    user,
                )
            )
            if error:
                return error

            Photo = request.env[self.PHOTO_MODEL]

            if request.httprequest.method == "GET":
                photos = Photo.search(
                    [
                        (
                            "reparacion_id",
                            "=",
                            repair.id,
                        ),
                        ("active", "=", True),
                    ],
                    order=(
                        "sequence asc, "
                        "create_date asc"
                    ),
                )

                count = len(photos)

                return self._json_response(
                    {
                        "success": True,
                        "count": count,
                        "minimum": 10,
                        "missing": max(
                            0,
                            10 - count,
                        ),
                        "complete": count >= 10,
                        "items": [
                            self._serialize_photo(
                                photo
                            )
                            for photo in photos
                        ],
                    }
                )

            if self._is_finalized(repair):
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_READ_ONLY",
                        "message": (
                            "La reparación finalizada "
                            "es de solo lectura."
                        ),
                    },
                    status=409,
                )

            data = self._get_json_body()

            filename = (
                data.get("filename")
                or data.get("name")
                or ""
            ).strip()

            image_base64 = (
                data.get("image_base64")
                or data.get(
                    "original_image_base64"
                )
                or ""
            )

            if not filename or not image_base64:
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "PHOTO_DATA_REQUIRED"
                        ),
                        "message": (
                            "Falta el nombre o "
                            "la imagen original."
                        ),
                    },
                    status=400,
                )

            if "," in image_base64:
                image_base64 = (
                    image_base64.split(",", 1)[1]
                )

            try:
                base64.b64decode(
                    image_base64,
                    validate=True,
                )
            except Exception:
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "INVALID_PHOTO_BASE64"
                        ),
                        "message": (
                            "La imagen enviada "
                            "no es válida."
                        ),
                    },
                    status=400,
                )

            photo = Photo.create(
                {
                    "reparacion_id": repair.id,
                    "nombre_foto": filename,
                    "foto_binario": image_base64,
                }
            )

            count = Photo.search_count(
                [
                    (
                        "reparacion_id",
                        "=",
                        repair.id,
                    ),
                    ("active", "=", True),
                ]
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Foto original subida "
                        "correctamente."
                    ),
                    "photo": self._serialize_photo(
                        photo
                    ),
                    "photos_count": count,
                    "minimum": 10,
                    "missing": max(
                        0,
                        10 - count,
                    ),
                    "complete": count >= 10,
                },
                status=201,
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # PHOTO DELETE
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>/photos/<int:photo_id>",
        type="http",
        auth="public",
        methods=["DELETE"],
        csrf=False,
        save_session=True,
    )
    def repair_photo_delete(
        self,
        repair_id,
        photo_id,
        **kwargs,
    ):
        user, error = self._require_user()
        if error:
            return error

        try:
            repair, error = (
                self._repair_or_error(
                    repair_id,
                    user,
                )
            )
            if error:
                return error

            if self._is_finalized(repair):
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_READ_ONLY",
                        "message": (
                            "La reparación finalizada "
                            "es de solo lectura."
                        ),
                    },
                    status=409,
                )

            photo = request.env[
                self.PHOTO_MODEL
            ].search(
                [
                    ("id", "=", photo_id),
                    (
                        "reparacion_id",
                        "=",
                        repair.id,
                    ),
                ],
                limit=1,
            )

            if not photo:
                return self._json_response(
                    {
                        "success": False,
                        "code": "PHOTO_NOT_FOUND",
                        "message": (
                            "Foto no encontrada."
                        ),
                    },
                    status=404,
                )

            photo.unlink()

            count = request.env[
                self.PHOTO_MODEL
            ].search_count(
                [
                    (
                        "reparacion_id",
                        "=",
                        repair.id,
                    ),
                    ("active", "=", True),
                ]
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Foto eliminada "
                        "correctamente."
                    ),
                    "photos_count": count,
                    "minimum": 10,
                    "missing": max(
                        0,
                        10 - count,
                    ),
                    "complete": count >= 10,
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # FINALIZE
    # Odoo sigue siendo la autoridad.
    # ============================================================

    @http.route(
        "/api/app/repairs/<int:repair_id>/finalize",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def repair_finalize(
        self,
        repair_id,
        **kwargs,
    ):
        user, error = self._require_user()
        if error:
            return error

        try:
            repair, error = (
                self._repair_or_error(
                    repair_id,
                    user,
                )
            )
            if error:
                return error

            if repair.estado_id == "finalizado":
                return self._json_response(
                    {
                        "success": True,
                        "message": (
                            "La reparación ya está "
                            "finalizada."
                        ),
                        "repair": (
                            self._serialize_repair(
                                repair,
                                detail=True,
                            )
                        ),
                    }
                )

            method = getattr(
                repair,
                "action_finalizar_reparacion",
                None,
            )

            if not callable(method):
                raise UserError(
                    "No existe "
                    "action_finalizar_reparacion()."
                )

            result = method()

            if (
                isinstance(result, dict)
                and result.get("target") == "new"
            ):
                return self._json_response(
                    {
                        "success": False,
                        "code": (
                            "ODOO_ACTION_REQUIRED"
                        ),
                        "message": (
                            "Odoo requiere completar "
                            "una validación adicional "
                            "antes de finalizar."
                        ),
                    },
                    status=409,
                )

            repair.invalidate_recordset()

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "Reparación finalizada "
                        "correctamente."
                    ),
                    "repair": self._serialize_repair(
                        repair,
                        detail=True,
                    ),
                }
            )

        except (ValidationError, UserError) as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": (
                        "REPAIR_VALIDATION_ERROR"
                    ),
                    "message": str(exc),
                },
                status=400,
            )

        except Exception as exc:
            return self._error_response(exc)
