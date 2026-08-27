# -*- coding: utf-8 -*-

import logging

from odoo import http
from odoo.http import request

from .base import RepairAdminBaseController


_logger = logging.getLogger(__name__)


class RepairAdminQueueController(RepairAdminBaseController):

    @http.route(
        [
            "/api/app/repairs/admin/queue",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def repair_admin_queue_options(self, **kwargs):
        return self._options_response()

    def _ra_serialize_queue_machine(self, machine, position):
        existing = self._ra_get_existing_repair(machine)

        return {
            "id": machine.id,
            "model": (
                machine.name.display_name
                if machine.name
                else machine.display_name
            ),
            "brand": self._ra_safe_value(machine, "marca", "") or "",
            "serial": self._ra_safe_value(machine, "serie_id", "") or "",
            "client": self._ra_many2one(machine, "cliente_id"),
            "queue_date": self._ra_datetime(
                self._ra_safe_value(
                    machine,
                    "fecha_para_revision",
                    False,
                )
            ),
            "queue_date_lima": self._ra_datetime_lima(
                self._ra_safe_value(
                    machine,
                    "fecha_para_revision",
                    False,
                )
            ),
            "queue_position": position,
            "technical_state": (
                self._ra_safe_value(
                    machine,
                    "estado_ventas_id",
                    "",
                )
                or ""
            ),
            "technical_state_label": self._ra_selection_label(
                machine,
                "estado_ventas_id",
            ),
            "existing_repair": (
                self._ra_serialize_repair_short(existing)
                if existing
                else False
            ),
            "can_create_repair": not bool(existing),
        }

    @http.route(
        "/api/app/repairs/admin/queue",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def repair_admin_queue(self, **kwargs):
        user, error = self._ra_require_admin()
        if error:
            return error

        try:
            args = request.httprequest.args
            search_term = (args.get("search") or "").strip()
            limit = self._ra_limit(
                args.get("limit"),
                default=200,
                maximum=300,
            )
            offset = self._ra_offset(args.get("offset"))

            Machine = request.env[self.MACHINE_MODEL].sudo()

            domain = [
                ("estado_ventas_id", "=", "para_revision"),
            ]

            if "fecha_para_revision" in Machine._fields:
                domain.append(
                    ("fecha_para_revision", "!=", False)
                )

            if search_term:
                domain += [
                    "|",
                    "|",
                    "|",
                    ("serie_id", "ilike", search_term),
                    ("name.name", "ilike", search_term),
                    ("marca", "ilike", search_term),
                    ("cliente_id.name", "ilike", search_term),
                ]

            total = Machine.search_count(domain)

            records = Machine.search(
                domain,
                order="fecha_para_revision asc, id asc",
                limit=limit,
                offset=offset,
            )

            # La posición se calcula contra TODA la cola, no solo la página.
            all_queue_ids = Machine.search(
                [
                    ("estado_ventas_id", "=", "para_revision"),
                    ("fecha_para_revision", "!=", False),
                ],
                order="fecha_para_revision asc, id asc",
            ).ids

            positions = {
                machine_id: index
                for index, machine_id in enumerate(
                    all_queue_ids,
                    start=1,
                )
            }

            items = [
                self._ra_serialize_queue_machine(
                    machine,
                    positions.get(machine.id, 0),
                )
                for machine in records
            ]

            return self._json_response(
                {
                    "success": True,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "items": items,
                }
            )

        except Exception as exc:
            return self._error_response(exc)
