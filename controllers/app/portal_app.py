# -*- coding: utf-8 -*-

import base64
import json
import logging
import re

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class AppPortalController(http.Controller):

    # ============================================================
    # HELPERS
    # ============================================================

    def _json_response(
        self,
        data,
        status=200,
    ):
        return request.make_response(
            json.dumps(
                data,
                ensure_ascii=False,
                default=str,
            ),
            headers=[
                (
                    "Content-Type",
                    "application/json; charset=utf-8",
                ),
                (
                    "Cache-Control",
                    "no-store",
                ),
            ],
            status=status,
        )

    def _get_json_body(
        self,
    ):
        try:
            data = request.httprequest.get_json(
                silent=True,
            )

            if isinstance(
                data,
                dict,
            ):
                return data

        except Exception:
            _logger.exception(
                "[APP PORTAL] No se pudo interpretar JSON."
            )

        return {}

    def _portal_context(
        self,
    ):
        """
        Devuelve usuario, contacto y empresa comercial.

        Esta API está destinada únicamente a usuarios Portal.
        Nunca acepta partner_id enviado desde Flutter para decidir
        qué empresa puede consultar.
        """

        user = request.env.user

        if not user:
            return False

        if user._is_public():
            return False

        is_portal = user.has_group(
            "base.group_portal"
        )

        is_internal = user.has_group(
            "base.group_user"
        )

        if (
            not is_portal
            or is_internal
        ):
            return False

        contact = user.partner_id

        if not contact:
            return False

        company = (
            contact.commercial_partner_id
            or contact
        )

        if not company:
            return False

        return {
            "user": user,
            "contact": contact,
            "company": company,
        }

    def _portal_required(
        self,
    ):
        context = self._portal_context()

        if context:
            return context, False

        return False, self._json_response(
            {
                "success": False,
                "code": "PORTAL_ACCESS_REQUIRED",
                "message": (
                    "Esta función está disponible "
                    "únicamente para usuarios portal."
                ),
            },
            status=403,
        )

    def _get_equipment_for_company(
        self,
        equipment_id,
        company,
    ):
        try:
            equipment_id = int(
                equipment_id
            )
        except (
            TypeError,
            ValueError,
        ):
            return False

        equipment = (
            request.env[
                "alquiler"
            ]
            .sudo()
            .browse(
                equipment_id
            )
            .exists()
        )

        if not equipment:
            return False

        if (
            not equipment.cliente_id
            or equipment.cliente_id.id
            != company.id
        ):
            return False

        return equipment

    def _get_ticket_for_company(
        self,
        ticket_id,
        company,
    ):
        try:
            ticket_id = int(
                ticket_id
            )
        except (
            TypeError,
            ValueError,
        ):
            return False

        ticket = (
            request.env[
                "ticket.alquiler"
            ]
            .sudo()
            .browse(
                ticket_id
            )
            .exists()
        )

        if not ticket:
            return False

        if (
            not ticket.partner_id
            or ticket.partner_id.id
            != company.id
        ):
            return False

        return ticket

    def _selection_label(
        self,
        record,
        field_name,
    ):
        field = record._fields.get(
            field_name
        )

        if not field:
            return ""

        value = getattr(
            record,
            field_name,
            False,
        )

        if not value:
            return ""

        selection = field.selection

        if isinstance(
            selection,
            str,
        ):
            method = getattr(
                record,
                selection,
                False,
            )

            selection = (
                method()
                if method
                else []
            )

        elif callable(
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

        for key, label in (
            selection
            or []
        ):
            if key == value:
                return label

        return str(
            value
        )

    def _clean_html_text(
        self,
        value,
    ):
        """
        Convierte HTML simple del informe técnico a texto
        adecuado para mostrar en Flutter.

        No altera el contenido almacenado en Odoo.
        """

        if not value:
            return ""

        text = str(
            value
        )

        text = re.sub(
            r"<br\s*/?>",
            "\n",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"</p\s*>",
            "\n",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"<[^>]+>",
            "",
            text,
        )

        replacements = {
            "&nbsp;": " ",
            "&amp;": "&",
            "&lt;": "<",
            "&gt;": ">",
            "&quot;": '"',
            "&#39;": "'",
        }

        for source, target in (
            replacements.items()
        ):
            text = text.replace(
                source,
                target,
            )

        lines = [
            line.strip()
            for line in text.splitlines()
        ]

        return "\n".join(
            line
            for line in lines
            if line
        )

    def _field_value(
        self,
        record,
        field_name,
        default=False,
    ):
        if (
            not record
            or field_name
            not in record._fields
        ):
            return default

        value = getattr(
            record,
            field_name,
            default,
        )

        return (
            value
            if value not in (
                None,
                False,
            )
            else default
        )

    def _bool_field(
        self,
        record,
        field_name,
    ):
        return bool(
            self._field_value(
                record,
                field_name,
                False,
            )
        )

    def _int_field(
        self,
        record,
        field_name,
    ):
        value = self._field_value(
            record,
            field_name,
            0,
        )

        try:
            return int(
                value
                or 0
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0

    def _clean_phone(
        self,
        value,
    ):
        phone = str(
            value
            or ""
        ).replace(
            "@c.us",
            "",
        )

        digits = "".join(
            character
            for character in phone
            if character.isdigit()
        )

        if (
            digits
            and not digits.startswith(
                "51"
            )
            and len(
                digits
            ) == 9
        ):
            digits = (
                "51"
                + digits
            )

        return digits

    def _get_toner_stock_info(
        self,
        equipment,
    ):
        is_color = (
            equipment.tipo_maquina_id
            == "color"
        )

        model = (
            equipment.name
            if equipment.name
            else False
        )

        def model_int(
            field_name,
            default=1,
        ):
            if (
                not model
                or field_name
                not in model._fields
            ):
                return default

            try:
                return int(
                    getattr(
                        model,
                        field_name,
                        default,
                    )
                    or default
                )
            except (
                TypeError,
                ValueError,
            ):
                return default

        colors = {
            "black": {
                "available": True,
                "stock_total": self._int_field(
                    equipment,
                    "stock_total_toner_black",
                ),
                "stock_customer": self._int_field(
                    equipment,
                    "stock_cliente_toner_black",
                ),
                "installed": self._bool_field(
                    equipment,
                    "toner_black_instalado",
                ),
                "minimum_stock": model_int(
                    "stock_minimo_black",
                    1,
                ),
            },
            "cyan": {
                "available": is_color,
                "stock_total": self._int_field(
                    equipment,
                    "stock_total_toner_cyan",
                ),
                "stock_customer": self._int_field(
                    equipment,
                    "stock_cliente_toner_cyan",
                ),
                "installed": self._bool_field(
                    equipment,
                    "toner_cyan_instalado",
                ),
                "minimum_stock": model_int(
                    "stock_minimo_cyan",
                    1,
                ),
            },
            "magenta": {
                "available": is_color,
                "stock_total": self._int_field(
                    equipment,
                    "stock_total_toner_magenta",
                ),
                "stock_customer": self._int_field(
                    equipment,
                    "stock_cliente_toner_magenta",
                ),
                "installed": self._bool_field(
                    equipment,
                    "toner_magenta_instalado",
                ),
                "minimum_stock": model_int(
                    "stock_minimo_magenta",
                    1,
                ),
            },
            "yellow": {
                "available": is_color,
                "stock_total": self._int_field(
                    equipment,
                    "stock_total_toner_yellow",
                ),
                "stock_customer": self._int_field(
                    equipment,
                    "stock_cliente_toner_yellow",
                ),
                "installed": self._bool_field(
                    equipment,
                    "toner_yellow_instalado",
                ),
                "minimum_stock": model_int(
                    "stock_minimo_yellow",
                    1,
                ),
            },
        }

        automatic_management = True

        if (
            model
            and "gestionar_toner_automatico"
            in model._fields
        ):
            automatic_management = bool(
                model.gestionar_toner_automatico
            )

        return {
            "is_color": is_color,
            "automatic_management": (
                automatic_management
            ),
            "stock_status": (
                self._field_value(
                    equipment,
                    "estado_stock_toner",
                    "",
                )
                or ""
            ),
            "has_auto_counters": bool(
                equipment.has_auto_counters
            ),
            "counters": {
                "black": (
                    equipment.contador_bn
                    or 0
                ),
                "color": (
                    equipment.contador_color
                    or 0
                ),
            },
            "colors": colors,
        }

    def _serialize_toner_request(
        self,
        submission,
    ):
        equipment = (
            submission.equipment_id
            if (
                "equipment_id"
                in submission._fields
                and submission.equipment_id
            )
            else False
        )

        requested = {}

        color_fields = {
            "black": (
                "requiere_toner_black",
                "cantidad_solicitada_black",
                "cantidad_aprobada_black",
            ),
            "cyan": (
                "requiere_toner_cyan",
                "cantidad_solicitada_cyan",
                "cantidad_aprobada_cyan",
            ),
            "magenta": (
                "requiere_toner_magenta",
                "cantidad_solicitada_magenta",
                "cantidad_aprobada_magenta",
            ),
            "yellow": (
                "requiere_toner_yellow",
                "cantidad_solicitada_yellow",
                "cantidad_aprobada_yellow",
            ),
        }

        for color, fields in (
            color_fields.items()
        ):
            flag_field, qty_field, approved_field = (
                fields
            )

            selected = self._bool_field(
                submission,
                flag_field,
            )

            requested[
                color
            ] = {
                "requested": selected,
                "quantity": (
                    self._int_field(
                        submission,
                        qty_field,
                    )
                    if qty_field
                    in submission._fields
                    else (
                        1
                        if selected
                        else 0
                    )
                ),
                "approved_quantity": (
                    self._int_field(
                        submission,
                        approved_field,
                    )
                    if approved_field
                    in submission._fields
                    else 0
                ),
            }

        state = (
            self._field_value(
                submission,
                "state",
                "",
            )
            or ""
        )

        return {
            "id": submission.id,
            "number": (
                self._field_value(
                    submission,
                    "secuencia",
                    "",
                )
                or ""
            ),
            "state": state,
            "state_label": (
                self._selection_label(
                    submission,
                    "state",
                )
                if "state"
                in submission._fields
                else state
            ),
            "date": (
                self._field_value(
                    submission,
                    "submission_date",
                    False,
                )
            ),
            "requester": {
                "name": (
                    self._field_value(
                        submission,
                        "client_name",
                        "",
                    )
                    or ""
                ),
                "phone": (
                    self._field_value(
                        submission,
                        "client_phone",
                        "",
                    )
                    or ""
                ),
                "email": (
                    self._field_value(
                        submission,
                        "client_email",
                        "",
                    )
                    or ""
                ),
            },
            "equipment": {
                "id": (
                    equipment.id
                    if equipment
                    else False
                ),
                "brand": (
                    equipment.marca
                    if equipment
                    else ""
                ) or "",
                "model": (
                    equipment.name.name
                    if (
                        equipment
                        and equipment.name
                    )
                    else ""
                ),
                "serial": (
                    equipment.serie
                    if equipment
                    else ""
                ) or "",
                "location": (
                    equipment.ubicacion_instalacion
                    if equipment
                    else ""
                ) or "",
            },
            "counters": {
                "black": self._int_field(
                    submission,
                    "counter_bn",
                ),
                "color": self._int_field(
                    submission,
                    "counter_color",
                ),
            },
            "requested_toners": requested,
            "requires_evidence": (
                self._bool_field(
                    submission,
                    "requires_evidence",
                )
            ),
            "analysis_result": (
                self._field_value(
                    submission,
                    "analysis_result",
                    "",
                )
                or ""
            ),
            "analysis_summary": (
                self._field_value(
                    submission,
                    "analysis_summary",
                    "",
                )
                or ""
            ),
            "notes": (
                self._field_value(
                    submission,
                    "notes",
                    "",
                )
                or ""
            ),
        }

    def _serialize_equipment(
        self,
        equipment,
    ):
        model_name = ""

        if equipment.name:
            model_name = (
                equipment.name.name
                if hasattr(
                    equipment.name,
                    "name",
                )
                else str(
                    equipment.name
                )
            )

        return {
            "id": equipment.id,
            "brand": (
                equipment.marca
                or ""
            ),
            "model": (
                model_name
                or ""
            ),
            "serial": (
                equipment.serie
                or ""
            ),
            "machine_type": (
                equipment.tipo_maquina_id
                or ""
            ),
            "machine_type_label": (
                self._selection_label(
                    equipment,
                    "tipo_maquina_id",
                )
            ),
            "location": (
                equipment.ubicacion_instalacion
                or ""
            ),
            "address": (
                equipment.direccion
                or ""
            ),
            "status": (
                equipment.estado_alquiler_id
                or ""
            ),
            "status_label": (
                self._selection_label(
                    equipment,
                    "estado_alquiler_id",
                )
            ),
            "counters": {
                "black": (
                    equipment.contador_bn
                    or 0
                ),
                "color": (
                    equipment.contador_color
                    or 0
                ),
                "scanner": (
                    equipment.contador_scan
                    or 0
                ),
                "last_update": (
                    equipment.fecha_ultima_actualizacion
                    or False
                ),
                "automatic": bool(
                    equipment.has_auto_counters
                ),
            },
            # Próximo mantenimiento.
            #
            # Prioridad:
            # 1) fecha_programada_mantenimiento:
            #    fecha real asignada por el planificador.
            # 2) fecha_recurrente:
            #    fecha ideal calculada por la recurrencia.
            #
            # Los campos se leen de forma defensiva porque pertenecen
            # a extensiones del modelo alquiler.
            "next_maintenance_date": (
                self._field_value(
                    equipment,
                    "fecha_programada_mantenimiento",
                    False,
                )
                or self._field_value(
                    equipment,
                    "fecha_recurrente",
                    False,
                )
                or False
            ),
            "maintenance": {
                "scheduled_date": (
                    self._field_value(
                        equipment,
                        "fecha_programada_mantenimiento",
                        False,
                    )
                ),
                "ideal_date": (
                    self._field_value(
                        equipment,
                        "fecha_recurrente",
                        False,
                    )
                ),
                "scheduled_hour": (
                    self._field_value(
                        equipment,
                        "hora_programada_mantenimiento",
                        False,
                    )
                ),
                "duration_hours": (
                    self._field_value(
                        equipment,
                        "duracion_mantenimiento_horas",
                        False,
                    )
                ),
                "status": (
                    self._field_value(
                        equipment,
                        "estado_planificacion_mantenimiento",
                        "",
                    )
                    or ""
                ),
                "status_label": (
                    self._selection_label(
                        equipment,
                        "estado_planificacion_mantenimiento",
                    )
                    if (
                        "estado_planificacion_mantenimiento"
                        in equipment._fields
                    )
                    else ""
                ),
                "technician": (
                    equipment.tecnico_mantenimiento_id.name
                    if (
                        "tecnico_mantenimiento_id"
                        in equipment._fields
                        and equipment.tecnico_mantenimiento_id
                    )
                    else ""
                ),
                "zone": (
                    equipment.zona_mantenimiento_id.name
                    if (
                        "zona_mantenimiento_id"
                        in equipment._fields
                        and equipment.zona_mantenimiento_id
                    )
                    else ""
                ),
                "technicians_required": (
                    self._int_field(
                        equipment,
                        "cantidad_tecnicos_mantenimiento",
                    )
                    if (
                        "cantidad_tecnicos_mantenimiento"
                        in equipment._fields
                    )
                    else 0
                ),
            },
        }

    def _serialize_ticket_summary(
        self,
        ticket,
    ):
        equipment = (
            ticket.product_alquiler
            if ticket.product_alquiler
            else False
        )

        return {
            "id": ticket.id,
            "number": (
                ticket.name
                or ""
            ),
            "status": (
                ticket.estado
                or ""
            ),
            "status_label": (
                self._selection_label(
                    ticket,
                    "estado",
                )
            ),
            "service_type": (
                ticket.tipo_servicio_id
                or ""
            ),
            "service_type_label": (
                self._selection_label(
                    ticket,
                    "tipo_servicio_id",
                )
            ),
            "created_at": (
                ticket.create_date
                or False
            ),
            "scheduled_at": (
                ticket.agenda
                or False
            ),
            "technician": (
                ticket.nombre_responsable
                or ""
            ),
            "description": (
                ticket.description
                or ""
            ),
            "equipment": {
                "id": (
                    equipment.id
                    if equipment
                    else False
                ),
                "brand": (
                    ticket.marca_id_r
                    or ""
                ),
                "model": (
                    ticket.modelo_id_r
                    or ""
                ),
                "serial": (
                    ticket.serie_id_r
                    or ""
                ),
                "location": (
                    equipment.ubicacion_instalacion
                    if equipment
                    else ""
                ) or "",
            },
            "report_available": (
                ticket.estado
                == "finalizado"
            ),
        }

    def _serialize_ticket_detail(
        self,
        ticket,
    ):
        result = (
            self._serialize_ticket_summary(
                ticket
            )
        )

        result.update(
            {
                "company": (
                    ticket.nombre_cliente
                    or ""
                ),
                "reporter": {
                    "name": (
                        ticket.reporter_name
                        or ticket.contacto_id_r
                        or ""
                    ),
                    "phone": (
                        ticket.reporter_phone
                        or ticket.celular_id_r
                        or ""
                    ),
                    "email": (
                        ticket.corre_id_r
                        or ""
                    ),
                },
                "address": (
                    ticket.direccion_id_r
                    or ""
                ),
                "technical_report": (
                    self._clean_html_text(
                        ticket.informe_id
                    )
                ),
                "counters": {
                    "black": (
                        ticket.contometrok_id
                        or ""
                    ),
                    "color": (
                        ticket.contometroc_id
                        or ""
                    ),
                    "scanner": (
                        ticket.contometros_id
                        or ""
                    ),
                    "total": (
                        ticket.total_copias_id
                        or ""
                    ),
                },
                "approval": {
                    "registered": False,
                    "name": "",
                    "dni": "",
                    "phone": "",
                    "email": "",
                    "date": False,
                },
            }
        )

        if (
            "conformidad_registrada"
            in ticket._fields
        ):
            result[
                "approval"
            ][
                "registered"
            ] = bool(
                ticket.conformidad_registrada
            )

        optional_approval_fields = {
            "conformidad_nombre": "name",
            "conformidad_dni": "dni",
            "conformidad_celular": "phone",
            "conformidad_correo": "email",
            "conformidad_fecha": "date",
        }

        for field_name, target in (
            optional_approval_fields.items()
        ):
            if field_name in ticket._fields:
                result[
                    "approval"
                ][
                    target
                ] = (
                    getattr(
                        ticket,
                        field_name,
                        False,
                    )
                    or (
                        False
                        if target == "date"
                        else ""
                    )
                )

        return result

    def _decode_problem_photo(
        self,
        value,
    ):
        if not value:
            return False

        raw = str(
            value
        ).strip()

        if not raw:
            return False

        if raw.startswith(
            "data:"
        ):
            if "," not in raw:
                raise ValueError(
                    "La imagen enviada no es válida."
                )

            raw = raw.split(
                ",",
                1,
            )[1]

        try:
            decoded = base64.b64decode(
                raw,
                validate=True,
            )
        except Exception as error:
            raise ValueError(
                "La fotografía enviada no tiene "
                "un formato Base64 válido."
            ) from error

        max_size = (
            8
            * 1024
            * 1024
        )

        if len(
            decoded
        ) > max_size:
            raise ValueError(
                "La fotografía supera el límite "
                "de 8 MB."
            )

        return base64.b64encode(
            decoded
        ).decode(
            "utf-8"
        )

    # ============================================================
    # HOME PORTAL
    # ============================================================

    @http.route(
        "/api/app/portal/home",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def portal_home(
        self,
        **kwargs,
    ):
        context, error = (
            self._portal_required()
        )

        if error:
            return error

        company = context[
            "company"
        ]

        Equipment = request.env[
            "alquiler"
        ].sudo()

        Ticket = request.env[
            "ticket.alquiler"
        ].sudo()

        Toner = request.env[
            "toner.counter.submission"
        ].sudo()

        equipment_domain = [
            (
                "cliente_id",
                "=",
                company.id,
            ),
            (
                "estado_alquiler_id",
                "=",
                "alquilada",
            ),
        ]

        ticket_domain = [
            (
                "partner_id",
                "=",
                company.id,
            ),
        ]

        open_ticket_domain = (
            ticket_domain
            + [
                (
                    "estado",
                    "!=",
                    "finalizado",
                ),
            ]
        )

        toner_domain = [
            (
                "partner_id",
                "=",
                company.id,
            ),
        ]

        open_toner_domain = list(
            toner_domain
        )

        open_states = getattr(
            Toner,
            "OPEN_STATES",
            False,
        )

        if open_states:
            open_toner_domain.append(
                (
                    "state",
                    "in",
                    list(
                        open_states
                    ),
                )
            )

        equipment_count = (
            Equipment.search_count(
                equipment_domain
            )
        )

        ticket_count = (
            Ticket.search_count(
                ticket_domain
            )
        )

        open_ticket_count = (
            Ticket.search_count(
                open_ticket_domain
            )
        )

        toner_count = (
            Toner.search_count(
                toner_domain
            )
        )

        open_toner_count = (
            Toner.search_count(
                open_toner_domain
            )
            if open_states
            else 0
        )

        recent_tickets = (
            Ticket.search(
                ticket_domain,
                order="create_date desc",
                limit=5,
            )
        )

        recent_toner = (
            Toner.search(
                toner_domain,
                order="submission_date desc, id desc",
                limit=5,
            )
        )

        return self._json_response(
            {
                "success": True,
                "user": {
                    "id": (
                        context[
                            "user"
                        ].id
                    ),
                    "name": (
                        context[
                            "user"
                        ].name
                        or ""
                    ),
                },
                "contact": {
                    "id": (
                        context[
                            "contact"
                        ].id
                    ),
                    "name": (
                        context[
                            "contact"
                        ].name
                        or ""
                    ),
                },
                "company": {
                    "id": company.id,
                    "name": (
                        company.name
                        or ""
                    ),
                },
                "summary": {
                    "equipment": (
                        equipment_count
                    ),
                    "tickets": (
                        ticket_count
                    ),
                    "open_tickets": (
                        open_ticket_count
                    ),
                    "toner_requests": (
                        toner_count
                    ),
                    "open_toner_requests": (
                        open_toner_count
                    ),
                },
                "recent_tickets": [
                    self._serialize_ticket_summary(
                        item
                    )
                    for item
                    in recent_tickets
                ],
                "recent_toner_requests": [
                    self._serialize_toner_request(
                        item
                    )
                    for item
                    in recent_toner
                ],
            }
        )

    # ============================================================
    # EQUIPOS
    # ============================================================

    @http.route(
        "/api/app/portal/equipment",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def portal_equipment_list(
        self,
        **kwargs,
    ):
        context, error = (
            self._portal_required()
        )

        if error:
            return error

        company = context[
            "company"
        ]

        equipment = (
            request.env[
                "alquiler"
            ]
            .sudo()
            .search(
                [
                    (
                        "cliente_id",
                        "=",
                        company.id,
                    ),
                    (
                        "estado_alquiler_id",
                        "=",
                        "alquilada",
                    ),
                ],
                order=(
                    "ubicacion_instalacion asc, "
                    "serie asc"
                ),
            )
        )

        return self._json_response(
            {
                "success": True,
                "company": {
                    "id": company.id,
                    "name": (
                        company.name
                        or ""
                    ),
                },
                "count": len(
                    equipment
                ),
                "equipment": [
                    self._serialize_equipment(
                        item
                    )
                    for item in equipment
                ],
            }
        )

    @http.route(
        "/api/app/portal/equipment/<int:equipment_id>",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def portal_equipment_detail(
        self,
        equipment_id,
        **kwargs,
    ):
        context, error = (
            self._portal_required()
        )

        if error:
            return error

        company = context[
            "company"
        ]

        equipment = (
            self._get_equipment_for_company(
                equipment_id,
                company,
            )
        )

        if not equipment:
            return self._json_response(
                {
                    "success": False,
                    "code": "EQUIPMENT_NOT_FOUND",
                    "message": (
                        "El equipo no existe o "
                        "no pertenece a tu empresa."
                    ),
                },
                status=404,
            )

        recent_tickets = (
            request.env[
                "ticket.alquiler"
            ]
            .sudo()
            .search(
                [
                    (
                        "partner_id",
                        "=",
                        company.id,
                    ),
                    (
                        "product_alquiler",
                        "=",
                        equipment.id,
                    ),
                ],
                order="create_date desc",
                limit=10,
            )
        )

        return self._json_response(
            {
                "success": True,
                "equipment": (
                    self._serialize_equipment(
                        equipment
                    )
                ),
                "recent_tickets": [
                    self._serialize_ticket_summary(
                        ticket
                    )
                    for ticket in recent_tickets
                ],
            }
        )

    # ============================================================
    # TICKETS / HISTORIAL
    # ============================================================

    @http.route(
        "/api/app/portal/tickets",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def portal_ticket_list(
        self,
        **kwargs,
    ):
        context, error = (
            self._portal_required()
        )

        if error:
            return error

        company = context[
            "company"
        ]

        status = (
            request.httprequest.args.get(
                "status"
            )
            or ""
        ).strip()

        equipment_id = (
            request.httprequest.args.get(
                "equipment_id"
            )
            or ""
        ).strip()

        domain = [
            (
                "partner_id",
                "=",
                company.id,
            ),
        ]

        if status:
            allowed_statuses = {
                key
                for key, _label
                in (
                    request.env[
                        "ticket.alquiler"
                    ]
                    ._fields[
                        "estado"
                    ]
                    .selection
                )
            }

            if status in allowed_statuses:
                domain.append(
                    (
                        "estado",
                        "=",
                        status,
                    )
                )

        if equipment_id:
            equipment = (
                self._get_equipment_for_company(
                    equipment_id,
                    company,
                )
            )

            if not equipment:
                return self._json_response(
                    {
                        "success": False,
                        "code": "EQUIPMENT_NOT_FOUND",
                        "message": (
                            "El equipo indicado "
                            "no pertenece a tu empresa."
                        ),
                    },
                    status=404,
                )

            domain.append(
                (
                    "product_alquiler",
                    "=",
                    equipment.id,
                )
            )

        tickets = (
            request.env[
                "ticket.alquiler"
            ]
            .sudo()
            .search(
                domain,
                order="create_date desc",
            )
        )

        return self._json_response(
            {
                "success": True,
                "count": len(
                    tickets
                ),
                "tickets": [
                    self._serialize_ticket_summary(
                        ticket
                    )
                    for ticket in tickets
                ],
            }
        )

    @http.route(
        "/api/app/portal/tickets/<int:ticket_id>",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def portal_ticket_detail(
        self,
        ticket_id,
        **kwargs,
    ):
        context, error = (
            self._portal_required()
        )

        if error:
            return error

        ticket = (
            self._get_ticket_for_company(
                ticket_id,
                context[
                    "company"
                ],
            )
        )

        if not ticket:
            return self._json_response(
                {
                    "success": False,
                    "code": "TICKET_NOT_FOUND",
                    "message": (
                        "El ticket no existe o "
                        "no pertenece a tu empresa."
                    ),
                },
                status=404,
            )

        return self._json_response(
            {
                "success": True,
                "ticket": (
                    self._serialize_ticket_detail(
                        ticket
                    )
                ),
            }
        )

    # ============================================================
    # CREAR SOLICITUD DE SERVICIO
    # ============================================================

    @http.route(
        "/api/app/portal/equipment/<int:equipment_id>/service-request",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def portal_create_service_request(
        self,
        equipment_id,
        **kwargs,
    ):
        context, error = (
            self._portal_required()
        )

        if error:
            return error

        company = context[
            "company"
        ]

        contact = context[
            "contact"
        ]

        equipment = (
            self._get_equipment_for_company(
                equipment_id,
                company,
            )
        )

        if not equipment:
            return self._json_response(
                {
                    "success": False,
                    "code": "EQUIPMENT_NOT_FOUND",
                    "message": (
                        "El equipo no existe o "
                        "no pertenece a tu empresa."
                    ),
                },
                status=404,
            )

        data = (
            self._get_json_body()
        )

        description = str(
            data.get(
                "description"
            )
            or ""
        ).strip()

        if not description:
            return self._json_response(
                {
                    "success": False,
                    "code": "DESCRIPTION_REQUIRED",
                    "message": (
                        "Describe el problema "
                        "o motivo del servicio."
                    ),
                },
                status=400,
            )

        try:
            problem_photo = (
                self._decode_problem_photo(
                    data.get(
                        "problem_photo"
                    )
                )
            )
        except ValueError as error:
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_PHOTO",
                    "message": str(
                        error
                    ),
                },
                status=400,
            )

        phone = (
            contact.mobile
            or contact.phone
            or ""
        )

        email = (
            contact.email
            or ""
        )

        ticket_vals = {
            "partner_id": company.id,
            "direccion_id_r": (
                equipment.direccion
                or ""
            ),
            "contacto_id_r": (
                contact.name
                or ""
            ),
            "celular_id_r": phone,
            "corre_id_r": email,
            "reporter_name": (
                contact.name
                or ""
            ),
            "reporter_phone": phone,
            "product_alquiler": (
                equipment.id
            ),
            "description": description,
        }

        if problem_photo:
            ticket_vals[
                "problem_photo"
            ] = problem_photo

        try:
            ticket = (
                request.env[
                    "ticket.alquiler"
                ]
                .sudo()
                .create(
                    ticket_vals
                )
            )

            try:
                ticket.enviar_mensaje_whatsapp_reporter()
            except Exception:
                _logger.exception(
                    "[APP PORTAL] Ticket %s creado, "
                    "pero falló WhatsApp al reportante.",
                    ticket.id,
                )

        except Exception as error:
            _logger.exception(
                "[APP PORTAL] Error creando ticket "
                "para equipo=%s empresa=%s",
                equipment.id,
                company.id,
            )

            return self._json_response(
                {
                    "success": False,
                    "code": "TICKET_CREATE_ERROR",
                    "message": str(
                        error
                    ),
                },
                status=500,
            )

        _logger.info(
            "[APP PORTAL] Ticket creado "
            "ticket=%s equipment=%s company=%s contact=%s",
            ticket.id,
            equipment.id,
            company.id,
            contact.id,
        )

        return self._json_response(
            {
                "success": True,
                "message": (
                    "La solicitud de servicio "
                    "fue registrada correctamente."
                ),
                "ticket": (
                    self._serialize_ticket_detail(
                        ticket
                    )
                ),
            },
            status=201,
        )

    # ============================================================
    # TÓNER
    # ============================================================

    @http.route(
        "/api/app/portal/toner-requests",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def portal_toner_request_list(
        self,
        **kwargs,
    ):
        context, error = (
            self._portal_required()
        )

        if error:
            return error

        company = context[
            "company"
        ]

        equipment_id = (
            request.httprequest.args.get(
                "equipment_id"
            )
            or ""
        ).strip()

        state = (
            request.httprequest.args.get(
                "state"
            )
            or ""
        ).strip()

        domain = [
            (
                "partner_id",
                "=",
                company.id,
            ),
        ]

        if equipment_id:
            equipment = (
                self._get_equipment_for_company(
                    equipment_id,
                    company,
                )
            )

            if not equipment:
                return self._json_response(
                    {
                        "success": False,
                        "code": "EQUIPMENT_NOT_FOUND",
                        "message": (
                            "El equipo indicado no "
                            "pertenece a tu empresa."
                        ),
                    },
                    status=404,
                )

            domain.append(
                (
                    "equipment_id",
                    "=",
                    equipment.id,
                )
            )

        if state:
            TonerModel = request.env[
                "toner.counter.submission"
            ]

            field = (
                TonerModel._fields.get(
                    "state"
                )
            )

            allowed = set()

            if field:
                selection = field.selection

                if isinstance(
                    selection,
                    list,
                ):
                    allowed = {
                        key
                        for key, _label
                        in selection
                    }

            if (
                not allowed
                or state in allowed
            ):
                domain.append(
                    (
                        "state",
                        "=",
                        state,
                    )
                )

        submissions = (
            request.env[
                "toner.counter.submission"
            ]
            .sudo()
            .search(
                domain,
                order=(
                    "submission_date desc, "
                    "id desc"
                ),
            )
        )

        return self._json_response(
            {
                "success": True,
                "count": len(
                    submissions
                ),
                "requests": [
                    self._serialize_toner_request(
                        item
                    )
                    for item
                    in submissions
                ],
            }
        )

    @http.route(
        "/api/app/portal/toner-requests/<int:submission_id>",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def portal_toner_request_detail(
        self,
        submission_id,
        **kwargs,
    ):
        context, error = (
            self._portal_required()
        )

        if error:
            return error

        company = context[
            "company"
        ]

        submission = (
            request.env[
                "toner.counter.submission"
            ]
            .sudo()
            .browse(
                submission_id
            )
            .exists()
        )

        if (
            not submission
            or not submission.partner_id
            or submission.partner_id.id
            != company.id
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "TONER_REQUEST_NOT_FOUND",
                    "message": (
                        "La solicitud de tóner no "
                        "existe o no pertenece a "
                        "tu empresa."
                    ),
                },
                status=404,
            )

        return self._json_response(
            {
                "success": True,
                "request": (
                    self._serialize_toner_request(
                        submission
                    )
                ),
            }
        )

    @http.route(
        "/api/app/portal/equipment/<int:equipment_id>/toner",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def portal_equipment_toner_info(
        self,
        equipment_id,
        **kwargs,
    ):
        context, error = (
            self._portal_required()
        )

        if error:
            return error

        company = context[
            "company"
        ]

        equipment = (
            self._get_equipment_for_company(
                equipment_id,
                company,
            )
        )

        if not equipment:
            return self._json_response(
                {
                    "success": False,
                    "code": "EQUIPMENT_NOT_FOUND",
                    "message": (
                        "El equipo no existe o "
                        "no pertenece a tu empresa."
                    ),
                },
                status=404,
            )

        Toner = request.env[
            "toner.counter.submission"
        ].sudo()

        open_states = getattr(
            Toner,
            "OPEN_STATES",
            False,
        )

        active_domain = [
            (
                "equipment_id",
                "=",
                equipment.id,
            ),
            (
                "partner_id",
                "=",
                company.id,
            ),
        ]

        if open_states:
            active_domain.append(
                (
                    "state",
                    "in",
                    list(
                        open_states
                    ),
                )
            )

        active_request = (
            Toner.search(
                active_domain,
                order=(
                    "submission_date desc, "
                    "id desc"
                ),
                limit=1,
            )
            if open_states
            else False
        )

        return self._json_response(
            {
                "success": True,
                "equipment": (
                    self._serialize_equipment(
                        equipment
                    )
                ),
                "toner": (
                    self._get_toner_stock_info(
                        equipment
                    )
                ),
                "active_request": (
                    self._serialize_toner_request(
                        active_request
                    )
                    if active_request
                    else False
                ),
            }
        )

    @http.route(
        "/api/app/portal/equipment/<int:equipment_id>/toner-request",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def portal_create_toner_request(
        self,
        equipment_id,
        **kwargs,
    ):
        context, error = (
            self._portal_required()
        )

        if error:
            return error

        company = context[
            "company"
        ]

        contact = context[
            "contact"
        ]

        equipment = (
            self._get_equipment_for_company(
                equipment_id,
                company,
            )
        )

        if not equipment:
            return self._json_response(
                {
                    "success": False,
                    "code": "EQUIPMENT_NOT_FOUND",
                    "message": (
                        "El equipo no existe o "
                        "no pertenece a tu empresa."
                    ),
                },
                status=404,
            )

        data = self._get_json_body()

        requested = {
            "black": bool(
                data.get(
                    "black"
                )
            ),
            "cyan": bool(
                data.get(
                    "cyan"
                )
            ),
            "magenta": bool(
                data.get(
                    "magenta"
                )
            ),
            "yellow": bool(
                data.get(
                    "yellow"
                )
            ),
        }

        if (
            equipment.tipo_maquina_id
            != "color"
        ):
            requested[
                "cyan"
            ] = False
            requested[
                "magenta"
            ] = False
            requested[
                "yellow"
            ] = False

        if not any(
            requested.values()
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "TONER_REQUIRED",
                    "message": (
                        "Selecciona al menos un "
                        "tóner para registrar "
                        "la solicitud."
                    ),
                },
                status=400,
            )

        def optional_counter(
            key,
            fallback,
        ):
            raw = data.get(
                key
            )

            if raw in (
                None,
                "",
            ):
                return int(
                    fallback
                    or 0
                )

            try:
                value = int(
                    raw
                )
            except (
                TypeError,
                ValueError,
            ):
                raise ValueError(
                    "El contador enviado "
                    "no es válido."
                )

            if value < 0:
                raise ValueError(
                    "El contador no puede "
                    "ser negativo."
                )

            return value

        try:
            counter_bn = optional_counter(
                "counter_bn",
                equipment.contador_bn,
            )

            counter_color = (
                optional_counter(
                    "counter_color",
                    equipment.contador_color,
                )
                if (
                    equipment.tipo_maquina_id
                    == "color"
                )
                else 0
            )

        except ValueError as error:
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_COUNTER",
                    "message": str(
                        error
                    ),
                },
                status=400,
            )

        Toner = request.env[
            "toner.counter.submission"
        ].sudo()

        try:
            validation = (
                Toner.validate_web_toner_request(
                    equipment_id=(
                        equipment.id
                    ),
                    requested_toners=(
                        requested
                    ),
                    current_counters={
                        "bn": (
                            counter_bn
                        ),
                        "color": (
                            counter_color
                        ),
                    },
                )
            )

        except Exception as error:
            _logger.exception(
                "[APP PORTAL] Error validando tóner "
                "equipment=%s company=%s",
                equipment.id,
                company.id,
            )

            return self._json_response(
                {
                    "success": False,
                    "code": "TONER_VALIDATION_ERROR",
                    "message": str(
                        error
                    ),
                },
                status=500,
            )

        if not validation.get(
            "can_create"
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": (
                        "TONER_REQUEST_BLOCKED"
                    ),
                    "message": (
                        validation.get(
                            "message"
                        )
                        or (
                            "La solicitud de tóner "
                            "no puede registrarse."
                        )
                    ),
                    "validation": (
                        validation
                    ),
                },
                status=409,
            )

        email = (
            contact.email
            or (
                company.email
                if company
                else ""
            )
            or "soporte@andescopiers.com.pe"
        )

        phone = self._clean_phone(
            contact.mobile
            or contact.phone
            or ""
        )

        notes = str(
            data.get(
                "notes"
            )
            or ""
        ).strip()

        web_data = {
            "equipment_id": (
                equipment.id
            ),
            "client_name": (
                contact.name
                or ""
            ),
            "client_email": email,
            "client_phone": phone,
            "counter_bn": (
                counter_bn
            ),
            "counter_color": (
                counter_color
            ),
            "requires_black": (
                requested[
                    "black"
                ]
            ),
            "requires_cyan": (
                requested[
                    "cyan"
                ]
            ),
            "requires_magenta": (
                requested[
                    "magenta"
                ]
            ),
            "requires_yellow": (
                requested[
                    "yellow"
                ]
            ),
            "notes": (
                "Solicitud desde app portal.\n"
                "Observaciones: %s"
                % (
                    notes
                    or "Sin observaciones"
                )
            ),
        }

        try:
            result = (
                Toner.create_from_web_request(
                    web_data
                )
            )

        except Exception as error:
            _logger.exception(
                "[APP PORTAL] Excepción creando "
                "solicitud de tóner equipment=%s",
                equipment.id,
            )

            return self._json_response(
                {
                    "success": False,
                    "code": "TONER_CREATE_ERROR",
                    "message": str(
                        error
                    ),
                },
                status=500,
            )

        if not result.get(
            "success"
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "TONER_CREATE_ERROR",
                    "message": (
                        result.get(
                            "error"
                        )
                        or (
                            "No fue posible registrar "
                            "la solicitud de tóner."
                        )
                    ),
                    "result": result,
                },
                status=500,
            )

        submission_id = (
            result.get(
                "submission_id"
            )
        )

        submission = (
            Toner.browse(
                submission_id
            ).exists()
            if submission_id
            else False
        )

        _logger.info(
            "[APP PORTAL] Solicitud de tóner "
            "creada submission=%s equipment=%s "
            "company=%s contact=%s",
            (
                submission.id
                if submission
                else submission_id
            ),
            equipment.id,
            company.id,
            contact.id,
        )

        return self._json_response(
            {
                "success": True,
                "message": (
                    "La solicitud de tóner fue "
                    "registrada correctamente."
                ),
                "validation": validation,
                "request": (
                    self._serialize_toner_request(
                        submission
                    )
                    if submission
                    else {
                        "id": (
                            submission_id
                            or False
                        ),
                        "number": (
                            result.get(
                                "secuencia"
                            )
                            or ""
                        ),
                    }
                ),
            },
            status=201,
        )

    # ============================================================
    # REPORTE PDF DEL TICKET
    # ============================================================

    @http.route(
        "/api/app/portal/tickets/<int:ticket_id>/report",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        save_session=True,
    )
    def portal_ticket_report(
        self,
        ticket_id,
        **kwargs,
    ):
        context, error = (
            self._portal_required()
        )

        if error:
            return error

        ticket = (
            self._get_ticket_for_company(
                ticket_id,
                context[
                    "company"
                ],
            )
        )

        if not ticket:
            return self._json_response(
                {
                    "success": False,
                    "code": "TICKET_NOT_FOUND",
                    "message": (
                        "El ticket no existe o "
                        "no pertenece a tu empresa."
                    ),
                },
                status=404,
            )

        if (
            ticket.estado
            != "finalizado"
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "REPORT_NOT_AVAILABLE",
                    "message": (
                        "El reporte estará disponible "
                        "cuando el servicio esté finalizado."
                    ),
                },
                status=409,
            )

        try:
            report = (
                request.env.ref(
                    "sat.action_ticket_alquiler"
                )
            )

            pdf_content, _report_type = (
                report.sudo().render_qweb_pdf(
                    [
                        ticket.id
                    ]
                )
            )

        except Exception:
            _logger.exception(
                "[APP PORTAL] Error generando PDF "
                "ticket=%s",
                ticket.id,
            )

            return self._json_response(
                {
                    "success": False,
                    "code": "REPORT_GENERATION_ERROR",
                    "message": (
                        "No fue posible generar "
                        "el reporte del servicio."
                    ),
                },
                status=500,
            )

        filename = (
            "Informe_Tecnico_%s.pdf"
            % (
                ticket.name
                or ticket.id
            )
        )

        return request.make_response(
            pdf_content,
            headers=[
                (
                    "Content-Type",
                    "application/pdf",
                ),
                (
                    "Content-Disposition",
                    (
                        'inline; filename="%s"'
                        % filename
                    ),
                ),
                (
                    "Cache-Control",
                    "private, no-store",
                ),
            ],
            status=200,
        )
