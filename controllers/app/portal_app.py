# -*- coding: utf-8 -*-

import base64
import json
import logging
import re
from datetime import timedelta

from odoo import fields, http
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

    def _get_evaluation_for_company(
        self,
        evaluation_id,
        company,
    ):
        try:
            evaluation_id = int(
                evaluation_id
            )
        except (
            TypeError,
            ValueError,
        ):
            return False

        evaluation = (
            request.env[
                "client.service.evaluation"
            ]
            .sudo()
            .browse(
                evaluation_id
            )
            .exists()
        )

        if not evaluation:
            return False

        if (
            not evaluation.partner_id
            or evaluation.partner_id.id
            != company.id
        ):
            return False

        return evaluation

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

    def _get_counter_freshness(
        self,
        equipment,
        max_age_days=5,
    ):
        """
        Determina si los contadores guardados pueden utilizarse
        directamente para una solicitud de tóner.

        Regla:
        - 5 días o menos: contador vigente.
        - Más de 5 días: pedir lectura manual.
        - Sin fecha conocida: pedir lectura manual.

        Se usa únicamente fecha_ultima_actualizacion, porque representa
        la fecha real de actualización de los contadores.
        """

        raw_value = (
            equipment.fecha_ultima_actualizacion
            if (
                "fecha_ultima_actualizacion"
                in equipment._fields
            )
            else False
        )

        try:
            last_update = (
                fields.Datetime.to_datetime(
                    raw_value
                )
                if raw_value
                else False
            )
        except Exception:
            last_update = False

        if not last_update:
            return {
                "last_update": False,
                "age_days": False,
                "max_age_days": max_age_days,
                "is_fresh": False,
                "requires_manual_counter": True,
                "reason": "missing_date",
                "message": (
                    "No existe una fecha reciente de contador. "
                    "Ingresa el contador actual para continuar."
                ),
            }

        now = fields.Datetime.now()

        age_seconds = max(
            0,
            (
                now
                - last_update
            ).total_seconds(),
        )

        age_days = int(
            age_seconds // 86400
        )

        requires_manual = (
            age_seconds
            > (
                max_age_days
                * 86400
            )
        )

        return {
            "last_update": last_update,
            "age_days": age_days,
            "max_age_days": max_age_days,
            "is_fresh": not requires_manual,
            "requires_manual_counter": (
                requires_manual
            ),
            "reason": (
                "stale"
                if requires_manual
                else "fresh"
            ),
            "message": (
                (
                    "El contador registrado tiene más de "
                    f"{max_age_days} días. Ingresa el contador "
                    "actual para continuar."
                )
                if requires_manual
                else (
                    "El contador registrado está vigente."
                )
            ),
        }

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
            "counter_freshness": (
                self._get_counter_freshness(
                    equipment,
                    max_age_days=5,
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
            },
            "colors": colors,
        }

    def _serialize_delivery_confirmation(
        self,
        confirmation,
    ):
        """
        Información de confirmación visible para el cliente.

        No expone notas internas ni datos de gestión que no correspondan
        al seguimiento de la entrega.
        """

        if not confirmation:
            return False

        delivered_by = ""

        if (
            "delivered_by_user"
            in confirmation._fields
            and confirmation.delivered_by_user
        ):
            delivered_by = (
                confirmation.delivered_by_user.name
                or ""
            )

        return {
            "id": confirmation.id,
            "number": (
                self._field_value(
                    confirmation,
                    "secuencia",
                    "",
                )
                or ""
            ),
            "state": (
                self._field_value(
                    confirmation,
                    "state",
                    "",
                )
                or ""
            ),
            "state_label": (
                self._selection_label(
                    confirmation,
                    "state",
                )
                if "state"
                in confirmation._fields
                else ""
            ),
            "validation_status": (
                self._field_value(
                    confirmation,
                    "validation_status",
                    "",
                )
                or ""
            ),
            "validation_status_label": (
                self._selection_label(
                    confirmation,
                    "validation_status",
                )
                if "validation_status"
                in confirmation._fields
                else ""
            ),
            "delivery_date": (
                self._field_value(
                    confirmation,
                    "delivery_date",
                    False,
                )
            ),
            "delivery_time": (
                self._field_value(
                    confirmation,
                    "delivery_time",
                    0,
                )
                or 0
            ),
            "delivered_by": delivered_by,
            "received_by": {
                "name": (
                    self._field_value(
                        confirmation,
                        "received_by_name",
                        "",
                    )
                    or ""
                ),
                "position": (
                    self._field_value(
                        confirmation,
                        "received_by_position",
                        "",
                    )
                    or ""
                ),
                "dni": (
                    self._field_value(
                        confirmation,
                        "received_by_dni",
                        "",
                    )
                    or ""
                ),
            },
            "delivered_toners": {
                "black": self._int_field(
                    confirmation,
                    "toner_black_delivered",
                ),
                "cyan": self._int_field(
                    confirmation,
                    "toner_cyan_delivered",
                ),
                "magenta": self._int_field(
                    confirmation,
                    "toner_magenta_delivered",
                ),
                "yellow": self._int_field(
                    confirmation,
                    "toner_yellow_delivered",
                ),
            },
            "total_delivered": self._int_field(
                confirmation,
                "total_delivered",
            ),
            "delivery_notes": (
                self._field_value(
                    confirmation,
                    "delivery_notes",
                    "",
                )
                or ""
            ),
            "storage_location": (
                self._field_value(
                    confirmation,
                    "storage_location",
                    "",
                )
                or ""
            ),
            "installation_required": (
                self._bool_field(
                    confirmation,
                    "installation_required",
                )
            ),
            "installation_notes": (
                self._field_value(
                    confirmation,
                    "installation_notes",
                    "",
                )
                or ""
            ),
            "has_delivery_photo": bool(
                self._field_value(
                    confirmation,
                    "delivery_photo",
                    False,
                )
            ),
            "has_client_signature": bool(
                self._field_value(
                    confirmation,
                    "client_signature",
                    False,
                )
            ),
        }


    def _serialize_delivery_schedule(
        self,
        schedule,
    ):
        """
        Seguimiento de despacho visible para el cliente.

        Importante:
        - NO devuelve internal_notes.
        - NO devuelve usuarios internos salvo el nombre de quien entrega
          dentro de la confirmación final.
        """

        if not schedule:
            return False

        confirmation = (
            schedule.confirmation_id
            if (
                "confirmation_id"
                in schedule._fields
                and schedule.confirmation_id
            )
            else False
        )

        return {
            "id": schedule.id,
            "number": (
                self._field_value(
                    schedule,
                    "secuencia",
                    "",
                )
                or ""
            ),
            "state": (
                self._field_value(
                    schedule,
                    "state",
                    "",
                )
                or ""
            ),
            "state_label": (
                self._selection_label(
                    schedule,
                    "state",
                )
                if "state"
                in schedule._fields
                else ""
            ),
            "planned_date": (
                self._field_value(
                    schedule,
                    "delivery_date_planned",
                    False,
                )
            ),
            "confirmed_date": (
                self._field_value(
                    schedule,
                    "delivery_date_confirmed",
                    False,
                )
            ),
            "actual_date": (
                self._field_value(
                    schedule,
                    "delivery_date_actual",
                    False,
                )
            ),
            "priority": (
                self._field_value(
                    schedule,
                    "priority",
                    "",
                )
                or ""
            ),
            "priority_label": (
                self._selection_label(
                    schedule,
                    "priority",
                )
                if "priority"
                in schedule._fields
                else ""
            ),
            "urgent": self._bool_field(
                schedule,
                "urgente",
            ),
            "delivery_method": (
                self._field_value(
                    schedule,
                    "delivery_method",
                    "",
                )
                or ""
            ),
            "delivery_method_label": (
                self._selection_label(
                    schedule,
                    "delivery_method",
                )
                if "delivery_method"
                in schedule._fields
                else ""
            ),
            "delivery_address": (
                self._field_value(
                    schedule,
                    "delivery_address",
                    "",
                )
                or ""
            ),
            "contact": {
                "name": (
                    self._field_value(
                        schedule,
                        "contact_person",
                        "",
                    )
                    or ""
                ),
                "phone": (
                    self._field_value(
                        schedule,
                        "contact_phone",
                        "",
                    )
                    or ""
                ),
            },
            "delivery_company": (
                self._field_value(
                    schedule,
                    "delivery_company",
                    "",
                )
                or ""
            ),
            "tracking_number": (
                self._field_value(
                    schedule,
                    "tracking_number",
                    "",
                )
                or ""
            ),
            "delivery_status": (
                self._field_value(
                    schedule,
                    "delivery_status",
                    "",
                )
                or ""
            ),
            "delivery_status_label": (
                self._selection_label(
                    schedule,
                    "delivery_status",
                )
                if "delivery_status"
                in schedule._fields
                else ""
            ),
            "days_until_delivery": self._int_field(
                schedule,
                "days_until_delivery",
            ),
            "is_overdue": self._bool_field(
                schedule,
                "is_overdue",
            ),
            "toners": {
                "black": self._int_field(
                    schedule,
                    "toner_black_qty",
                ),
                "cyan": self._int_field(
                    schedule,
                    "toner_cyan_qty",
                ),
                "magenta": self._int_field(
                    schedule,
                    "toner_magenta_qty",
                ),
                "yellow": self._int_field(
                    schedule,
                    "toner_yellow_qty",
                ),
            },
            "total_units": self._int_field(
                schedule,
                "total_units",
            ),
            "confirmation": (
                self._serialize_delivery_confirmation(
                    confirmation
                )
                if confirmation
                else False
            ),
        }


    def _serialize_toner_workflow(
        self,
        submission,
    ):
        """
        Progreso simplificado para Flutter.

        Mantiene el estado real de Odoo, pero agrupa el flujo en pasos
        comprensibles para el cliente.
        """

        state = (
            self._field_value(
                submission,
                "state",
                "",
            )
            or ""
        )

        terminal_status = ""

        if state == "rechazada_gerencia":
            terminal_status = "rejected"
        elif state == "cancelada":
            terminal_status = "cancelled"
        elif state == "devuelta":
            terminal_status = "correction_required"

        state_rank = {
            "recibida": 0,
            "evaluacion": 1,
            "pendiente_gerencia": 2,
            "aprobada_gerencia": 3,
            "confirmacion_ventas": 4,
            "lista_despacho": 5,
            "en_despacho": 6,
            "entregada": 7,
            "rechazada_gerencia": 2,
            "devuelta": 1,
            "cancelada": 0,
        }

        rank = state_rank.get(
            state,
            0,
        )

        steps = [
            {
                "key": "received",
                "label": "Solicitud recibida",
                "completed": rank >= 0,
                "active": state == "recibida",
            },
            {
                "key": "evaluation",
                "label": "En evaluación",
                "completed": rank >= 1,
                "active": state in (
                    "evaluacion",
                    "devuelta",
                ),
            },
            {
                "key": "approval",
                "label": "Aprobación",
                "completed": rank >= 3,
                "active": state in (
                    "pendiente_gerencia",
                    "aprobada_gerencia",
                    "rechazada_gerencia",
                ),
            },
            {
                "key": "stock",
                "label": "Confirmación de stock",
                "completed": rank >= 5,
                "active": state == "confirmacion_ventas",
            },
            {
                "key": "dispatch",
                "label": "Despacho",
                "completed": rank >= 6,
                "active": state in (
                    "lista_despacho",
                    "en_despacho",
                ),
            },
            {
                "key": "delivered",
                "label": "Entregada",
                "completed": state == "entregada",
                "active": state == "entregada",
            },
        ]

        return {
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
            "terminal_status": terminal_status,
            "steps": steps,
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

        delivery = (
            submission.delivery_scheduled_id
            if (
                "delivery_scheduled_id"
                in submission._fields
                and submission.delivery_scheduled_id
            )
            else False
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
            "workflow": (
                self._serialize_toner_workflow(
                    submission
                )
            ),
            "delivery": (
                self._serialize_delivery_schedule(
                    delivery
                )
                if delivery
                else False
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

    def _serialize_portal_evaluation(
        self,
        evaluation,
        include_questions=False,
    ):
        now = fields.Datetime.now()
        expiration = (
            evaluation.expiration_date
            or False
        )

        seconds_remaining = False
        hours_remaining = False
        days_remaining = False
        expires_soon = False

        if expiration:
            seconds_remaining = max(
                0,
                int(
                    (
                        expiration
                        - now
                    ).total_seconds()
                ),
            )
            hours_remaining = int(
                seconds_remaining // 3600
            )
            days_remaining = int(
                seconds_remaining // 86400
            )
            expires_soon = (
                0
                < seconds_remaining
                <= (48 * 3600)
            )

        tickets = []

        for ticket in evaluation.ticket_ids:
            equipment = (
                ticket.product_alquiler
                if (
                    "product_alquiler"
                    in ticket._fields
                    and ticket.product_alquiler
                )
                else False
            )

            tickets.append({
                "id": ticket.id,
                "number": (
                    ticket.name
                    or ""
                ),
                "equipment": {
                    "id": (
                        equipment.id
                        if equipment
                        else False
                    ),
                    "model": (
                        (
                            equipment.name.name
                            if hasattr(equipment.name, "name")
                            else str(equipment.name)
                        )
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
                    ),
                },
            })

        result = {
            "id": evaluation.id,
            "reference": (
                evaluation.name
                or ""
            ),
            "state": (
                evaluation.state
                or ""
            ),
            "state_label": (
                self._selection_label(
                    evaluation,
                    "state",
                )
            ),
            "evaluation_date": (
                evaluation.evaluation_date
                or False
            ),
            "expiration_date": (
                expiration
            ),
            "visit_date": (
                evaluation.visit_date
                or False
            ),
            "technician": {
                "id": (
                    evaluation.technician_id.id
                    if evaluation.technician_id
                    else False
                ),
                "name": (
                    evaluation.technician_id.name
                    if evaluation.technician_id
                    else ""
                ),
            },
            "tickets": tickets,
            "pending": (
                evaluation.state
                in ("draft", "sent")
            ),
            "hours_remaining": (
                hours_remaining
            ),
            "days_remaining": (
                days_remaining
            ),
            "expires_soon": (
                expires_soon
            ),
        }

        if include_questions:
            result["questions"] = [
                {
                    "key": "solucion_problema",
                    "type": "rating",
                    "required": True,
                    "label": (
                        evaluation._fields[
                            "solucion_problema"
                        ].string
                    ),
                    "options": [
                        {"value": "1", "label": "Malo"},
                        {"value": "2", "label": "Regular"},
                        {"value": "3", "label": "Bueno"},
                        {"value": "4", "label": "Muy Bueno"},
                        {"value": "5", "label": "Excelente"},
                    ],
                },
                {
                    "key": "explicacion_trabajo",
                    "type": "rating",
                    "required": True,
                    "label": (
                        evaluation._fields[
                            "explicacion_trabajo"
                        ].string
                    ),
                    "options": [
                        {"value": "1", "label": "Malo"},
                        {"value": "2", "label": "Regular"},
                        {"value": "3", "label": "Bueno"},
                        {"value": "4", "label": "Muy Bueno"},
                        {"value": "5", "label": "Excelente"},
                    ],
                },
                {
                    "key": "realizo_pruebas",
                    "type": "boolean",
                    "required": True,
                    "label": (
                        evaluation._fields[
                            "realizo_pruebas"
                        ].string
                    ),
                    "options": [
                        {"value": "si", "label": "Sí"},
                        {"value": "no", "label": "No"},
                    ],
                },
                {
                    "key": "consulto_suministros",
                    "type": "boolean",
                    "required": True,
                    "label": (
                        evaluation._fields[
                            "consulto_suministros"
                        ].string
                    ),
                    "options": [
                        {"value": "si", "label": "Sí"},
                        {"value": "no", "label": "No"},
                    ],
                },
            ]
            result["comments"] = (
                evaluation.comentarios
                or ""
            )

        return result

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

        Evaluation = request.env[
            "client.service.evaluation"
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

        evaluation_domain = [
            (
                "partner_id",
                "=",
                company.id,
            ),
            (
                "state",
                "in",
                ["draft", "sent"],
            ),
            (
                "expiration_date",
                ">=",
                fields.Datetime.now(),
            ),
        ]

        expiring_evaluation_domain = (
            evaluation_domain
            + [
                (
                    "expiration_date",
                    "<=",
                    (fields.Datetime.now() + timedelta(hours=48)),
                ),
            ]
        )

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

        pending_evaluation_count = (
            Evaluation.search_count(
                evaluation_domain
            )
        )

        expiring_evaluation_count = (
            Evaluation.search_count(
                expiring_evaluation_domain
            )
        )

        pending_evaluations = (
            Evaluation.search(
                evaluation_domain,
                order="expiration_date asc, id asc",
                limit=3,
            )
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
                    "pending_evaluations": (
                        pending_evaluation_count
                    ),
                    "expiring_evaluations": (
                        expiring_evaluation_count
                    ),
                },
                "pending_evaluations": [
                    self._serialize_portal_evaluation(
                        item
                    )
                    for item
                    in pending_evaluations
                ],
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

        counter_freshness = (
            self._get_counter_freshness(
                equipment,
                max_age_days=5,
            )
        )

        requires_manual_counter = bool(
            counter_freshness.get(
                "requires_manual_counter"
            )
        )

        def read_counter(
            key,
            current_value,
            required=False,
            label="contador",
        ):
            raw = data.get(
                key
            )

            if raw in (
                None,
                "",
            ):
                if required:
                    raise ValueError(
                        f"Ingresa el {label} actual "
                        "para continuar."
                    )

                return int(
                    current_value
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
                    f"El {label} enviado no es válido."
                )

            if value < 0:
                raise ValueError(
                    f"El {label} no puede ser negativo."
                )

            stored_value = int(
                current_value
                or 0
            )

            if (
                stored_value > 0
                and value < stored_value
            ):
                raise ValueError(
                    f"El {label} actual ({value}) no puede "
                    f"ser menor al último registrado "
                    f"({stored_value})."
                )

            return value

        try:
            counter_bn = read_counter(
                "counter_bn",
                equipment.contador_bn,
                required=(
                    requires_manual_counter
                ),
                label="contador B/N",
            )

            counter_color = (
                read_counter(
                    "counter_color",
                    equipment.contador_color,
                    required=(
                        requires_manual_counter
                    ),
                    label="contador color",
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
                    "code": (
                        "COUNTER_UPDATE_REQUIRED"
                        if requires_manual_counter
                        else "INVALID_COUNTER"
                    ),
                    "message": str(
                        error
                    ),
                    "counter_freshness": (
                        counter_freshness
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

        # Si la lectura anterior estaba vencida o no tenía fecha,
        # los valores enviados por el cliente pasan a ser la nueva
        # lectura vigente del equipo.
        #
        # No actualizamos la fecha cuando el contador ya era reciente,
        # porque Flutter puede reenviar el mismo valor almacenado y eso
        # falsearía la antigüedad real de la lectura.
        if requires_manual_counter:
            counter_vals = {
                "contador_bn": (
                    counter_bn
                ),
                "fecha_ultima_actualizacion": (
                    fields.Datetime.now()
                ),
            }

            if (
                equipment.tipo_maquina_id
                == "color"
            ):
                counter_vals[
                    "contador_color"
                ] = counter_color

            try:
                equipment.sudo().write(
                    counter_vals
                )

                _logger.info(
                    "[APP PORTAL] Contadores actualizados "
                    "desde solicitud de tóner equipment=%s "
                    "bn=%s color=%s",
                    equipment.id,
                    counter_bn,
                    counter_color,
                )

            except Exception:
                _logger.exception(
                    "[APP PORTAL] La solicitud de tóner se creó, "
                    "pero no se pudo actualizar el contador del "
                    "equipo=%s",
                    equipment.id,
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
                "counter_freshness": (
                    self._get_counter_freshness(
                        equipment,
                        max_age_days=5,
                    )
                ),
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
    # EVALUACIONES DEL CLIENTE
    # ============================================================

    @http.route(
        "/api/app/portal/evaluations",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def portal_evaluation_list(
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
        now = fields.Datetime.now()

        evaluations = (
            request.env[
                "client.service.evaluation"
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
                        "state",
                        "in",
                        ["draft", "sent"],
                    ),
                    (
                        "expiration_date",
                        ">=",
                        now,
                    ),
                ],
                order="expiration_date asc, id asc",
            )
        )

        return self._json_response(
            {
                "success": True,
                "count": len(
                    evaluations
                ),
                "evaluations": [
                    self._serialize_portal_evaluation(
                        evaluation
                    )
                    for evaluation
                    in evaluations
                ],
            }
        )

    @http.route(
        "/api/app/portal/evaluations/<int:evaluation_id>",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def portal_evaluation_detail(
        self,
        evaluation_id,
        **kwargs,
    ):
        context, error = (
            self._portal_required()
        )

        if error:
            return error

        evaluation = (
            self._get_evaluation_for_company(
                evaluation_id,
                context["company"],
            )
        )

        if not evaluation:
            return self._json_response(
                {
                    "success": False,
                    "code": "EVALUATION_NOT_FOUND",
                    "message": (
                        "La evaluación no existe o "
                        "no pertenece a tu empresa."
                    ),
                },
                status=404,
            )

        if evaluation.state == "completed":
            return self._json_response(
                {
                    "success": False,
                    "code": "EVALUATION_ALREADY_COMPLETED",
                    "message": (
                        "Esta evaluación ya fue respondida."
                    ),
                },
                status=409,
            )

        now = fields.Datetime.now()
        if (
            evaluation.state == "expired"
            or (
                evaluation.expiration_date
                and evaluation.expiration_date < now
            )
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "EVALUATION_EXPIRED",
                    "message": (
                        "El plazo para responder esta evaluación terminó."
                    ),
                },
                status=410,
            )

        return self._json_response(
            {
                "success": True,
                "evaluation": (
                    self._serialize_portal_evaluation(
                        evaluation,
                        include_questions=True,
                    )
                ),
            }
        )

    @http.route(
        "/api/app/portal/evaluations/<int:evaluation_id>/submit",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def portal_evaluation_submit(
        self,
        evaluation_id,
        **kwargs,
    ):
        context, error = (
            self._portal_required()
        )

        if error:
            return error

        evaluation = (
            self._get_evaluation_for_company(
                evaluation_id,
                context["company"],
            )
        )

        if not evaluation:
            return self._json_response(
                {
                    "success": False,
                    "code": "EVALUATION_NOT_FOUND",
                    "message": (
                        "La evaluación no existe o "
                        "no pertenece a tu empresa."
                    ),
                },
                status=404,
            )

        if evaluation.state == "completed":
            return self._json_response(
                {
                    "success": False,
                    "code": "EVALUATION_ALREADY_COMPLETED",
                    "message": (
                        "Esta evaluación ya fue respondida."
                    ),
                },
                status=409,
            )

        now = fields.Datetime.now()
        if (
            evaluation.state == "expired"
            or (
                evaluation.expiration_date
                and evaluation.expiration_date < now
            )
        ):
            if evaluation.state != "expired":
                evaluation.sudo().write({
                    "state": "expired",
                })

            return self._json_response(
                {
                    "success": False,
                    "code": "EVALUATION_EXPIRED",
                    "message": (
                        "El plazo para responder esta evaluación terminó."
                    ),
                },
                status=410,
            )

        data = self._get_json_body()

        rating_values = {"1", "2", "3", "4", "5"}
        boolean_values = {"si", "no"}

        answers = {
            "solucion_problema": str(
                data.get("solucion_problema")
                or ""
            ).strip(),
            "explicacion_trabajo": str(
                data.get("explicacion_trabajo")
                or ""
            ).strip(),
            "realizo_pruebas": str(
                data.get("realizo_pruebas")
                or ""
            ).strip().lower(),
            "consulto_suministros": str(
                data.get("consulto_suministros")
                or ""
            ).strip().lower(),
        }

        if (
            answers["solucion_problema"]
            not in rating_values
            or answers["explicacion_trabajo"]
            not in rating_values
            or answers["realizo_pruebas"]
            not in boolean_values
            or answers["consulto_suministros"]
            not in boolean_values
        ):
            return self._json_response(
                {
                    "success": False,
                    "code": "INVALID_EVALUATION_ANSWERS",
                    "message": (
                        "Completa todas las preguntas antes de enviar la evaluación."
                    ),
                },
                status=400,
            )

        comments = str(
            data.get("comentarios")
            or ""
        ).strip()

        vals = dict(
            answers
        )
        vals["comentarios"] = comments

        try:
            evaluation.action_complete_from_app(
                vals=vals,
                request=request,
                contact=context["contact"],
            )
        except Exception:
            _logger.exception(
                "[APP PORTAL] Error completando evaluación=%s company=%s contact=%s",
                evaluation.id,
                context["company"].id,
                context["contact"].id,
            )
            return self._json_response(
                {
                    "success": False,
                    "code": "EVALUATION_SAVE_ERROR",
                    "message": (
                        "No fue posible guardar la evaluación."
                    ),
                },
                status=500,
            )

        _logger.info(
            "[APP PORTAL] Evaluación completada desde app evaluation=%s company=%s contact=%s user=%s",
            evaluation.id,
            context["company"].id,
            context["contact"].id,
            context["user"].id,
        )

        return self._json_response(
            {
                "success": True,
                "message": (
                    "Gracias. Tu evaluación fue registrada correctamente."
                ),
                "evaluation_id": evaluation.id,
            }
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

            report_sudo = (
                report.sudo()
            )

            pdf_content, _report_type = (
                report_sudo._render_qweb_pdf(
                    report_sudo.report_name,
                    [
                        ticket.id
                    ],
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
