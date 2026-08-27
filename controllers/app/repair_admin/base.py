# -*- coding: utf-8 -*-

import logging

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from ..base import AppBaseController


_logger = logging.getLogger(__name__)


class RepairAdminBaseController(AppBaseController):
    """
    Base común de la administración móvil de Reparaciones.

    IMPORTANTE:
    - No reemplaza controllers/app/repair.py.
    - repair.py continúa siendo la API del técnico asignado.
    - Este paquete cubre exclusivamente acciones administrativas.
    """

    MACHINE_MODEL = "sat.sat"
    REPAIR_MODEL = "reparaciones.reparaciones"
    USER_MODEL = "res.users"

    TECH_GROUP = "sat.sat_tecnica_group_user"
    HEAD_GROUP = "sat.sat_jefes_group_user"

    FINAL_STATES = {"finalizado", "entregada"}

    def _ra_model_exists(self, model_name):
        return model_name in request.env.registry

    def _ra_has_group(self, user, xmlid):
        try:
            return bool(user.has_group(xmlid))
        except Exception:
            return False

    def _ra_is_admin(self, user):
        if request.env.is_superuser():
            return True

        return bool(
            self._ra_has_group(user, "base.group_system")
            or self._ra_has_group(user, self.HEAD_GROUP)
        )

    def _ra_require_admin(self):
        user, error = self._require_user()
        if error:
            return user, error

        if not self._ra_is_admin(user):
            return user, self._json_response(
                {
                    "success": False,
                    "code": "REPAIR_ADMIN_REQUIRED",
                    "message": (
                        "Esta operación requiere permisos de "
                        "Administrador o Jefe de Taller."
                    ),
                },
                status=403,
            )

        return user, False

    def _ra_safe_value(self, record, field_name, default=False):
        if not record or not hasattr(record, "_fields"):
            return default
        if field_name not in record._fields:
            return default
        try:
            return record[field_name]
        except Exception:
            return default

    def _ra_safe_int(self, value, default=0):
        try:
            if value in (None, False, ""):
                return default
            return int(value)
        except Exception:
            return default

    def _ra_limit(self, value, default=100, maximum=300):
        value = self._ra_safe_int(value, default)
        if value <= 0:
            value = default
        return min(value, maximum)

    def _ra_offset(self, value):
        return max(0, self._ra_safe_int(value, 0))

    def _ra_datetime(self, value):
        if not value:
            return False
        try:
            return fields.Datetime.to_string(value)
        except Exception:
            return str(value)

    def _ra_datetime_lima(self, value):
        if not value:
            return False

        try:
            value = fields.Datetime.to_datetime(value)
            local = fields.Datetime.context_timestamp(
                request.env.user.with_context(tz="America/Lima"),
                value,
            )
            return local.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return self._ra_datetime(value)

    def _ra_many2one(self, record, field_name):
        value = self._ra_safe_value(record, field_name, False)
        if not value:
            return False

        return {
            "id": value.id,
            "name": value.display_name or value.name or "",
        }

    def _ra_selection_label(self, record, field_name):
        if (
            not record
            or not hasattr(record, "_fields")
            or field_name not in record._fields
        ):
            return ""

        value = record[field_name]
        if value in (None, False, ""):
            return ""

        field = record._fields[field_name]

        try:
            selection = field._description_selection(record.env)
            return dict(selection or []).get(value, str(value))
        except Exception:
            try:
                selection = field.selection
                if callable(selection):
                    selection = selection(record)
                return dict(selection or []).get(value, str(value))
            except Exception:
                return str(value)

    def _ra_selection_options(self, record, field_name):
        if (
            not record
            or not hasattr(record, "_fields")
            or field_name not in record._fields
        ):
            return []

        field = record._fields[field_name]

        try:
            selection = field._description_selection(record.env)
        except Exception:
            selection = field.selection
            if callable(selection):
                selection = selection(record)

        return [
            {"value": value, "label": label}
            for value, label in (selection or [])
        ]

    def _ra_get_machine(self, machine_id):
        return request.env[self.MACHINE_MODEL].sudo().search(
            [("id", "=", machine_id)],
            limit=1,
        )

    def _ra_get_repair(self, repair_id):
        return request.env[self.REPAIR_MODEL].sudo().search(
            [("id", "=", repair_id)],
            limit=1,
        )

    def _ra_get_existing_repair(self, machine):
        if not machine:
            return False

        return request.env[self.REPAIR_MODEL].sudo().search(
            [("maquina_id", "=", machine.id)],
            order="create_date desc, id desc",
            limit=1,
        )

    def _ra_machine_not_found(self):
        return self._json_response(
            {
                "success": False,
                "code": "MACHINE_NOT_FOUND",
                "message": "La máquina solicitada no existe.",
            },
            status=404,
        )

    def _ra_repair_not_found(self):
        return self._json_response(
            {
                "success": False,
                "code": "REPAIR_NOT_FOUND",
                "message": "La reparación solicitada no existe.",
            },
            status=404,
        )

    def _ra_group_users(self, xmlid):
        group = request.env.ref(xmlid, raise_if_not_found=False)
        if not group:
            return request.env[self.USER_MODEL].sudo().browse()

        if "user_ids" in group._fields:
            users = group.user_ids
        elif "users" in group._fields:
            users = group.users
        else:
            users = request.env[self.USER_MODEL].sudo().browse()

        return users.sudo()

    def _ra_is_valid_technician(self, user):
        if not user or not user.exists():
            return False

        if not user.active or user.share:
            return False

        return self._ra_has_group(user, self.TECH_GROUP)

    def _ra_technician_available(self, user):
        if not self._ra_is_valid_technician(user):
            return False

        Repair = request.env[self.REPAIR_MODEL].sudo()
        method = getattr(
            Repair,
            "_validar_disponibilidad_tecnico_reparacion",
            None,
        )

        if not callable(method):
            return True

        try:
            return bool(
                method(
                    tecnico=user,
                    fecha_hora=fields.Datetime.now(),
                    raise_error=False,
                )
            )
        except Exception:
            _logger.exception(
                "No se pudo validar disponibilidad del técnico %s.",
                user.id,
            )
            return False

    def _ra_serialize_repair_short(self, repair):
        if not repair:
            return False

        machine = self._ra_safe_value(repair, "maquina_id", False)

        return {
            "id": repair.id,
            "reference": self._ra_safe_value(repair, "name", "") or "",
            "state": self._ra_safe_value(repair, "estado_id", "") or "",
            "state_label": self._ra_selection_label(repair, "estado_id"),
            "responsible": self._ra_many2one(repair, "responsable_id"),
            "machine": self._ra_many2one(repair, "maquina_id"),
            "model": (
                machine.name.display_name
                if machine and machine.name
                else ""
            ),
            "brand": (
                self._ra_safe_value(machine, "marca", "") or ""
                if machine
                else ""
            ),
            "serial": self._ra_safe_value(repair, "serie_id", "") or "",
            "client": self._ra_many2one(repair, "cliente_id"),
            "created_at": self._ra_datetime(
                self._ra_safe_value(repair, "create_date", False)
            ),
            "created_at_lima": self._ra_datetime_lima(
                self._ra_safe_value(repair, "create_date", False)
            ),
            "finish_date": self._ra_datetime(
                self._ra_safe_value(repair, "fecha_finalizacion", False)
            ),
            "finalized": (
                self._ra_safe_value(repair, "estado_id", "")
                in self.FINAL_STATES
            ),
        }

    def _ra_serialize_repair_detail(self, repair):
        result = self._ra_serialize_repair_short(repair)
        if not result:
            return False

        machine = self._ra_safe_value(repair, "maquina_id", False)

        result.update(
            {
                "state_options": self._ra_selection_options(
                    repair,
                    "estado_id",
                ),
                "queue_date": (
                    self._ra_datetime(
                        self._ra_safe_value(
                            machine,
                            "fecha_para_revision",
                            False,
                        )
                    )
                    if machine
                    else False
                ),
                "queue_date_lima": (
                    self._ra_datetime_lima(
                        self._ra_safe_value(
                            machine,
                            "fecha_para_revision",
                            False,
                        )
                    )
                    if machine
                    else False
                ),
                "queue_position": (
                    self._ra_safe_int(
                        self._ra_safe_value(
                            machine,
                            "posicion_cola",
                            0,
                        )
                    )
                    if machine
                    else 0
                ),
                "photos_count": (
                    len(repair.fotos_ids)
                    if "fotos_ids" in repair._fields
                    else 0
                ),
                "actions": {
                    "can_reassign": (
                        self._ra_safe_value(repair, "estado_id", "")
                        not in self.FINAL_STATES
                    ),
                    "can_change_state": (
                        self._ra_safe_value(repair, "estado_id", "")
                        not in self.FINAL_STATES
                    ),
                    "can_finalize": (
                        self._ra_safe_value(repair, "estado_id", "")
                        not in self.FINAL_STATES
                    ),
                },
            }
        )

        return result
