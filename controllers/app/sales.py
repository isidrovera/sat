# -*- coding: utf-8 -*-

import base64
import logging

from odoo import fields, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from .base import AppBaseController


_logger = logging.getLogger(__name__)


class AppSalesController(AppBaseController):
    """API móvil del área comercial.

    Odoo mantiene toda la autoridad de reglas de negocio. Este controlador
    únicamente expone esas reglas a Flutter y ofrece lectura técnica para
    Ventas. Firebase/FCM sigue siendo responsabilidad del sistema push ya
    existente; aquí no se duplica el envío de notificaciones.
    """

    MACHINE_MODEL = "sat.sat"
    REQUEST_MODEL = "sat.reserva.solicitud"
    REQUEST_WIZARD_MODEL = "sat.reserva.solicitud.wizard"
    REPAIR_MODEL = "reparaciones.reparaciones"
    PHOTO_MODEL = "reparaciones.foto"
    TEST_MODEL = "sat.prueba.maquina"
    PART_MODEL = "solicitud.parte.tecnico.linea"
    INTERVENTION_MODEL = "reparacion.intervencion"

    SALES_GROUP = "sat.Sat_ventas_group_user"
    MANAGER_GROUP = "sat.group_reserva_comercial_autorizado"
    HEAD_GROUP = "sat.sat_jefes_group_user"

    ACTIVE_RESERVATION_STATES = ("separada", "especial", "confirmada")
    PROBLEM_STATES = ("con_problemas", "de_partes")
    DELIVERED_STATE = "entregada"

    # ============================================================
    # OPTIONS
    # ============================================================

    @http.route(
        [
            "/api/app/sales/summary",
            "/api/app/sales/alerts",
            "/api/app/sales/customers",
            "/api/app/sales/machines",
            "/api/app/sales/machines/<int:machine_id>",
            "/api/app/sales/machines/<int:machine_id>/reserve",
            "/api/app/sales/machines/<int:machine_id>/customer",
            "/api/app/sales/machines/<int:machine_id>/release",
            "/api/app/sales/machines/<int:machine_id>/review",
            "/api/app/sales/machines/<int:machine_id>/review/remove",
            "/api/app/sales/requests",
            "/api/app/sales/requests/<int:request_id>",
            "/api/app/sales/requests/<int:request_id>/cancel",
            "/api/app/sales/requests/<int:request_id>/decision",
            "/api/app/sales/machines/<int:machine_id>/repair",
            "/api/app/sales/machines/<int:machine_id>/repair/checklist",
            "/api/app/sales/machines/<int:machine_id>/repair/photos",
            "/api/app/sales/machines/<int:machine_id>/repair/parts",
            "/api/app/sales/machines/<int:machine_id>/repair/tests",
            "/api/app/sales/machines/<int:machine_id>/repair/report",
            "/api/app/sales/photos/<int:photo_id>/image",
        ],
        type="http",
        auth="none",
        methods=["OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def sales_options(self, **kwargs):
        return self._options_response()

    # ============================================================
    # BASIC HELPERS
    # ============================================================

    def _model_exists(self, model_name):
        return model_name in request.env.registry

    def _field(self, record, name, default=False):
        if not record or name not in record._fields:
            return default
        try:
            return record[name]
        except Exception:
            return default

    def _safe_int(self, value, default=0):
        try:
            if value in (None, False, ""):
                return default
            return int(value)
        except Exception:
            return default

    def _safe_float(self, value, default=0.0):
        try:
            if value in (None, False, ""):
                return default
            return float(value)
        except Exception:
            return default

    def _date(self, value):
        if not value:
            return False
        try:
            return fields.Date.to_string(value)
        except Exception:
            return str(value)

    def _datetime(self, value):
        if not value:
            return False
        try:
            return fields.Datetime.to_string(value)
        except Exception:
            return str(value)

    def _m2o(self, record, field_name):
        value = self._field(record, field_name, False)
        if not value:
            return False
        try:
            return self._many2one(value)
        except Exception:
            return {"id": value.id, "name": value.display_name}

    def _selection(self, record, field_name):
        """
        Serializa de forma segura un campo Selection.

        No utiliza AppBaseController._selection_label() porque en Odoo 18
        algunos campos Selection convierten internamente `selection` en un
        callable que espera un recordset/modelo, no un Environment. Pasar
        record.env directamente a ese callable provoca:

            AttributeError: 'Environment' object has no attribute 'env'

        `_description_selection(record.env)` es la API adecuada del propio
        campo para obtener las opciones traducidas en el entorno actual.
        """
        value = self._field(record, field_name, False)

        if not value:
            return {
                "value": False,
                "label": "",
            }

        label = str(value)

        try:
            field = record._fields.get(field_name)

            if field:
                selection = field._description_selection(
                    record.env
                )

                label = dict(
                    selection or []
                ).get(
                    value,
                    str(value),
                )

        except Exception:
            _logger.exception(
                "No se pudo obtener la etiqueta Selection "
                "del campo %s en %s(%s).",
                field_name,
                record._name,
                record.id,
            )

        return {
            "value": value,
            "label": label or "",
        }

    def _limit(self, value, default=50, maximum=200):
        value = self._safe_int(value, default)
        if value <= 0:
            value = default
        return min(value, maximum)

    def _offset(self, value):
        return max(0, self._safe_int(value, 0))

    # ============================================================
    # SECURITY
    # ============================================================

    def _has_group(self, user, xmlid):
        try:
            return bool(user.has_group(xmlid))
        except Exception:
            return False

    def _is_manager(self, user):
        if request.env.is_superuser():
            return True
        return (
            self._has_group(user, "base.group_system")
            or self._has_group(user, self.MANAGER_GROUP)
        )

    def _is_sales_user(self, user):
        return (
            self._is_manager(user)
            or self._has_group(user, self.SALES_GROUP)
            or self._has_group(user, self.HEAD_GROUP)
        )

    def _require_sales_user(self):
        user, error = self._require_user()
        if error:
            return user, error
        if not self._is_sales_user(user):
            return user, self._json_response(
                {
                    "success": False,
                    "code": "SALES_ACCESS_DENIED",
                    "message": "El usuario no tiene acceso al área de Ventas.",
                },
                status=403,
            )
        return user, False

    def _require_manager(self):
        user, error = self._require_sales_user()
        if error:
            return user, error
        if not self._is_manager(user):
            return user, self._json_response(
                {
                    "success": False,
                    "code": "MANAGER_REQUIRED",
                    "message": "Esta operación requiere autorización de gerencia.",
                },
                status=403,
            )
        return user, False

    def _ensure_owner(self, machine, user, allow_free=False):
        if self._is_manager(user):
            return True

        advisor = self._field(machine, "reserva_asesora_id", False)
        state = self._field(machine, "reserva_estado", "libre")

        if allow_free and (not advisor or state == "libre"):
            return True
        if advisor and advisor.id == user.id:
            return True

        raise AccessError("Esta máquina está asignada a otra asesora comercial.")

    # ============================================================
    # RECORD HELPERS
    # ============================================================

    def _get_machine(self, machine_id, sudo_read=False):
        Model = request.env[self.MACHINE_MODEL]
        if sudo_read:
            Model = Model.sudo()
        return Model.search([("id", "=", machine_id)], limit=1)

    def _machine_not_found(self):
        return self._json_response(
            {
                "success": False,
                "code": "MACHINE_NOT_FOUND",
                "message": "La máquina solicitada no existe.",
            },
            status=404,
        )

    def _get_commercial_request(self, request_id, sudo_read=False):
        Model = request.env[self.REQUEST_MODEL]
        if sudo_read:
            Model = Model.sudo()
        return Model.search([("id", "=", request_id)], limit=1)

    def _request_not_found(self):
        return self._json_response(
            {
                "success": False,
                "code": "REQUEST_NOT_FOUND",
                "message": "La solicitud comercial no existe.",
            },
            status=404,
        )

    def _get_main_repair(self, machine):
        if not self._model_exists(self.REPAIR_MODEL):
            return False
        return request.env[self.REPAIR_MODEL].sudo().search(
            [("maquina_id", "=", machine.id)],
            order="create_date desc, id desc",
            limit=1,
        )

    # ============================================================
    # CUSTOMER
    # ============================================================

    def _serialize_customer(self, partner):
        if not partner:
            return False
        advisor = False
        if "asesora_id" in partner._fields and partner.asesora_id:
            try:
                advisor = self._many2one(partner.asesora_id)
            except Exception:
                advisor = {
                    "id": partner.asesora_id.id,
                    "name": partner.asesora_id.display_name,
                }
        return {
            "id": partner.id,
            "name": partner.display_name or partner.name or "",
            "vat": self._field(partner, "vat", False),
            "phone": self._field(partner, "phone", False),
            "mobile": self._field(partner, "mobile", False),
            "email": self._field(partner, "email", False),
            "advisor": advisor,
        }

    # ============================================================
    # RESERVATION / MACHINE
    # ============================================================

    def _serialize_reservation(self, machine):
        pending = self._field(machine, "reserva_solicitud_pendiente_id", False)
        approved = self._field(machine, "reserva_solicitud_id", False)
        rule = self._field(machine, "reserva_regla_id", False)
        state = self._selection(machine, "reserva_estado")

        return {
            "state": state["value"],
            "state_label": state["label"],
            "advisor": self._m2o(machine, "reserva_asesora_id"),
            "customer": self._m2o(machine, "reserva_cliente_id"),
            "start": self._datetime(self._field(machine, "reserva_inicio", False)),
            "base_date": self._date(self._field(machine, "reserva_fecha_base", False)),
            "deadline": self._date(self._field(machine, "reserva_fecha_limite", False)),
            "days_granted": self._safe_int(self._field(machine, "reserva_dias", 0)),
            "days_remaining": self._safe_int(
                self._field(machine, "reserva_dias_restantes", 0)
            ),
            "expired": bool(self._field(machine, "reserva_vencida", False)),
            "cycle": self._safe_int(self._field(machine, "reserva_ciclo", 0)),
            "origin": self._field(machine, "reserva_origen", False),
            "origin_label": (
                self._selection_label(machine, "reserva_origen")
                if self._field(machine, "reserva_origen", False)
                else ""
            ),
            "rule": (
                {
                    "id": rule.id,
                    "name": rule.display_name,
                    "days": self._safe_int(self._field(rule, "dias_separacion", 0)),
                }
                if rule
                else False
            ),
            "authorization": (
                {"id": approved.id, "name": approved.display_name}
                if approved
                else False
            ),
            "pending_request": (
                {
                    "id": pending.id,
                    "name": pending.display_name,
                    "state": self._field(pending, "state", False),
                }
                if pending
                else False
            ),
        }

    def _machine_permissions(self, machine, user):
        manager = self._is_manager(user)
        advisor = self._field(machine, "reserva_asesora_id", False)
        reservation_state = self._field(machine, "reserva_estado", "libre")
        pending = self._field(machine, "reserva_solicitud_pendiente_id", False)
        delivered = self._field(machine, "estado_ventas_id", False) == self.DELIVERED_STATE
        owned = bool(advisor and advisor.id == user.id)
        free = reservation_state == "libre" or not advisor

        return {
            "is_manager": manager,
            "owned_by_me": owned,
            "free": free,
            "can_reserve": bool(not delivered and (free or owned or manager)),
            "can_assign_customer": bool(not delivered and (free or owned or manager)),
            "can_request_authorization": bool(
                not delivered and not pending and (free or owned or manager)
            ),
            "can_release_direct": bool(
                manager and not delivered and reservation_state in self.ACTIVE_RESERVATION_STATES
            ),
            "can_view_repair": True,
            "can_edit_repair": False,
            "can_edit_tests": False,
            "can_edit_parts": False,
            "can_delete_repair_photos": False,
        }

    def _serialize_repair_short(self, repair):
        if not repair:
            return False
        state = self._selection(repair, "estado_id")
        return {
            "id": repair.id,
            "reference": self._field(repair, "name", "") or "",
            "state": state["value"],
            "state_label": state["label"],
            "responsible": self._m2o(repair, "responsable_id"),
            "serial": self._field(repair, "serie_id", "") or "",
            "priority": self._field(repair, "prioridad", "") or "",
            "created_at": self._datetime(self._field(repair, "create_date", False)),
            "finish_date": self._datetime(
                self._field(repair, "fecha_finalizacion", False)
            ),
            "photos_count": (
                len(repair.fotos_ids) if "fotos_ids" in repair._fields else 0
            ),
        }

    def _serialize_machine(self, machine, user, detail=False):
        model = self._field(machine, "name", False)
        customer = self._field(machine, "cliente_id", False)
        technical = self._selection(machine, "estado_ventas_id")
        availability = self._selection(machine, "disponibilidad_id")
        location = self._selection(machine, "ubicacion_id")
        machine_type = self._selection(machine, "tipo_id")
        repair = self._get_main_repair(machine)

        result = {
            "id": machine.id,
            "model": model.display_name if model else machine.display_name,
            "brand": self._field(machine, "marca", "") or "",
            "serial": self._field(machine, "serie_id", "") or "",
            "type": machine_type["value"],
            "type_label": machine_type["label"],
            "machine_type": self._field(machine, "tipo_maquina", "") or "",
            "importation": self._field(machine, "importacion", "") or "",
            "meter": self._field(machine, "contometro", "") or "",
            "sale_price": self._safe_float(self._field(machine, "precio_venta", 0.0)),
            "customer": self._serialize_customer(customer) if customer else False,
            "technical_state": technical["value"],
            "technical_state_label": technical["label"],
            "availability": availability["value"],
            "availability_label": availability["label"],
            "location": location["value"],
            "location_label": location["label"],
            "reservation": self._serialize_reservation(machine),
            "repair": self._serialize_repair_short(repair),
            "permissions": self._machine_permissions(machine, user),
        }

        if detail:
            result.update(
                {
                    "invoice": self._field(machine, "invoice", "") or "",
                    "supplier": self._m2o(machine, "proveedor_id"),
                    "sales_invoice": self._field(machine, "factura_venta", "") or "",
                    "delivery_date": self._date(
                        self._field(machine, "fecha_entrega", False)
                    ),
                    "separation_date": self._date(
                        self._field(machine, "fecha_separacion", False)
                    ),
                    "description": self._field(machine, "descripcion", "") or "",
                    "ingress": {
                        "checked": bool(self._field(machine, "check_ingreso", False)),
                        "state": self._field(machine, "ingreso_estado", False),
                        "state_label": (
                            self._selection_label(machine, "ingreso_estado")
                            if self._field(machine, "ingreso_estado", False)
                            else ""
                        ),
                        "date": self._datetime(
                            self._field(machine, "ingreso_fecha", False)
                        ),
                        "source": self._field(machine, "ingreso_fuente", False),
                    },
                    "repair_count": self._safe_int(
                        self._field(machine, "reparaciones_count", 0)
                    ),
                    "test_count": (
                        len(machine.prueba_ids) if "prueba_ids" in machine._fields else 0
                    ),
                    "removed_parts_count": (
                        len(machine.partes_retiradas_ids)
                        if "partes_retiradas_ids" in machine._fields
                        else 0
                    ),
                }
            )

        return result

    # ============================================================
    # REPAIR READ-ONLY SERIALIZERS
    # ============================================================

    def _record_code(self, rec):
        if not rec:
            return ""
        for name in ("code", "codigo", "default_code"):
            if name in rec._fields and rec[name]:
                return str(rec[name])
        return ""

    def _serialize_subpart(self, rec):
        if not rec:
            return False
        return {"id": rec.id, "name": rec.display_name, "code": self._record_code(rec)}

    def _serialize_component(self, item):
        state = self._field(item, "estado_id", False)
        selected = []
        if "subpartes_ids" in item._fields:
            selected = [self._serialize_subpart(x) for x in item.subpartes_ids]
        return {
            "id": item.id,
            "component": self._m2o(item, "componente_tipo_id"),
            "color": self._m2o(item, "color_id"),
            "state": self._m2o(item, "estado_id"),
            "state_code": self._record_code(state),
            "requires_change": self._record_code(state) == "requiere_cambio",
            "observations": self._field(item, "observaciones", "") or "",
            "selected_subparts": selected,
        }

    def _serialize_accessory(self, item):
        state = self._field(item, "estado_id", False)
        selected = []
        if "subparte_ids" in item._fields:
            selected = [self._serialize_subpart(x) for x in item.subparte_ids]
        return {
            "id": item.id,
            "accessory": self._m2o(item, "tipo_id"),
            "state": self._m2o(item, "estado_id"),
            "state_code": self._record_code(state),
            "requires_change": self._record_code(state) == "requiere_cambio",
            "observations": self._field(item, "observaciones", "") or "",
            "selected_subparts": selected,
        }

    def _serialize_photo(self, photo):
        return {
            "id": photo.id,
            "name": self._field(photo, "nombre_foto", "") or "",
            "sequence": self._safe_int(self._field(photo, "sequence", 0)),
            "state": self._field(photo, "state", "") or "",
            "size": self._safe_int(self._field(photo, "size", 0)),
            "mimetype": self._field(photo, "mimetype", "") or "",
            "file_id": self._field(photo, "file_id", "") or "",
            "url": self._field(photo, "url_foto", "") or "",
            "public_link": self._field(photo, "public_link", "") or "",
            "thumb_url": self._field(photo, "thumb_url", "") or "",
            "content_url": "/api/app/sales/photos/%s/image" % photo.id,
            "created_at": self._datetime(self._field(photo, "create_date", False)),
        }

    def _serialize_intervention_detail(self, detail):
        return {
            "id": detail.id,
            "subpart": self._m2o(detail, "subparte_id"),
            "action": self._field(detail, "accion_sub", "") or "",
            "code": self._field(detail, "codigo", "") or "",
            "quantity": self._safe_float(self._field(detail, "cantidad", 0.0)),
            "note": self._field(detail, "nota", "") or "",
        }

    def _serialize_intervention(self, item):
        details = []
        if "detalle_ids" in item._fields:
            details = [self._serialize_intervention_detail(x) for x in item.detalle_ids]
        return {
            "id": item.id,
            "component": self._field(item, "componente", "") or "",
            "component_code": self._field(item, "componente_code", "") or "",
            "component_name": self._field(item, "componente_display", "") or "",
            "action": self._field(item, "accion", "") or "",
            "observation": self._field(item, "observacion", "") or "",
            "is_replacement": bool(self._field(item, "es_cambio", False)),
            "details": details,
        }

    def _serialize_repair_detail(self, repair):
        result = self._serialize_repair_short(repair)
        if not result:
            return False

        components = (
            [self._serialize_component(x) for x in repair.componente_eval_ids]
            if "componente_eval_ids" in repair._fields
            else []
        )
        accessories = (
            [self._serialize_accessory(x) for x in repair.accesorio_eval_ids]
            if "accesorio_eval_ids" in repair._fields
            else []
        )
        photos = (
            [
                self._serialize_photo(x)
                for x in repair.fotos_ids.sorted(
                    key=lambda p: (self._safe_int(self._field(p, "sequence", 0)), p.id)
                )
            ]
            if "fotos_ids" in repair._fields
            else []
        )
        interventions = []
        if self._model_exists(self.INTERVENTION_MODEL):
            interventions = [
                self._serialize_intervention(x)
                for x in request.env[self.INTERVENTION_MODEL].sudo().search(
                    [("reparacion_id", "=", repair.id)], order="id desc"
                )
            ]

        result.update(
            {
                "client": self._m2o(repair, "cliente_id"),
                "machine": self._m2o(repair, "maquina_id"),
                "revision_type": self._field(repair, "tipo_revision", "") or "",
                "location": self._field(repair, "ubicacion_id", "") or "",
                "meter_initial": self._field(repair, "contometro_inicial", "") or "",
                "meter_current": self._field(repair, "contometrok_id", "") or "",
                "quality": self._field(repair, "calidad_id", "") or "",
                "quality_label": (
                    self._selection_label(repair, "calidad_id")
                    if self._field(repair, "calidad_id", False)
                    else ""
                ),
                "report": self._field(repair, "informe", "") or "",
                "observations": self._field(repair, "observaciones", "") or "",
                "components": components,
                "accessories": accessories,
                "interventions": interventions,
                "photos": photos,
                "checklist_summary": {
                    "components_total": len(components),
                    "components_completed": sum(1 for x in components if x["state"]),
                    "accessories_total": len(accessories),
                    "accessories_completed": sum(1 for x in accessories if x["state"]),
                },
                "photo_summary": {
                    "current": len(photos),
                    "minimum": 10,
                    "missing": max(0, 10 - len(photos)),
                    "complete": len(photos) >= 10,
                },
                "readonly": True,
            }
        )
        return result

    # ============================================================
    # TEST / PART SERIALIZERS
    # ============================================================

    def _serialize_test(self, test, detail=True):
        state = self._selection(test, "estado_prueba")
        level = self._selection(test, "nivel_prueba")
        result = {
            "id": test.id,
            "repair": self._m2o(test, "reparacion_id"),
            "technician": self._m2o(test, "tecnico_id"),
            "start_date": self._datetime(self._field(test, "fecha_inicio", False)),
            "last_update": self._datetime(
                self._field(test, "fecha_ultima_actualizacion", False)
            ),
            "origin": self._field(test, "origen", "") or "",
            "state": state["value"],
            "state_label": state["label"],
            "level": level["value"],
            "level_label": level["label"],
            "has_snmp_alerts": bool(self._field(test, "tiene_alertas_snmp", False)),
            "snmp_alerts_count": self._safe_int(
                self._field(test, "cantidad_alertas_snmp", 0)
            ),
            "validations": {
                "print": bool(self._field(test, "prueba_impresion_ok", False)),
                "copy": bool(self._field(test, "prueba_copia_ok", False)),
                "scanner": bool(self._field(test, "prueba_scanner_ok", False)),
                "color": bool(self._field(test, "prueba_color_ok", False)),
                "black_white": bool(self._field(test, "prueba_bn_ok", False)),
                "duplex": bool(self._field(test, "prueba_duplex_ok", False)),
                "copy_black_white": bool(self._field(test, "prueba_copia_bn_ok", False)),
                "copy_color": bool(self._field(test, "prueba_copia_color_ok", False)),
                "print_black_white": bool(
                    self._field(test, "prueba_impresion_bn_ok", False)
                ),
                "print_color": bool(
                    self._field(test, "prueba_impresion_color_ok", False)
                ),
            },
        }
        if detail:
            result["snmp"] = {
                "ip": self._field(test, "snmp_ip", "") or "",
                "serial": self._field(test, "snmp_serie", "") or "",
                "brand": self._field(test, "snmp_marca", "") or "",
                "model": self._field(test, "snmp_modelo", "") or "",
            }
            result["counters"] = {
                "initial_total": self._safe_int(self._field(test, "contador_inicial_total", 0)),
                "initial_black_white": self._safe_int(self._field(test, "contador_inicial_bn", 0)),
                "initial_color": self._safe_int(self._field(test, "contador_inicial_color", 0)),
                "current_total": self._safe_int(self._field(test, "contador_actual_total", 0)),
                "current_black_white": self._safe_int(self._field(test, "contador_actual_bn", 0)),
                "current_color": self._safe_int(self._field(test, "contador_actual_color", 0)),
                "delta_total": self._safe_int(self._field(test, "delta_total", 0)),
                "delta_black_white": self._safe_int(self._field(test, "delta_bn", 0)),
                "delta_color": self._safe_int(self._field(test, "delta_color", 0)),
            }
        return result

    def _serialize_part(self, line):
        solicitation = self._field(line, "solicitud_id", False)
        return {
            "id": line.id,
            "part": self._field(line, "parte", "") or "",
            "description": self._field(line, "descripcion", "") or "",
            "state": self._field(line, "state", "") or "",
            "state_label": (
                self._selection_label(line, "state")
                if self._field(line, "state", False)
                else ""
            ),
            "request": (
                {"id": solicitation.id, "name": solicitation.display_name}
                if solicitation
                else False
            ),
            "request_date": (
                self._datetime(self._field(solicitation, "fecha_solicitud", False))
                if solicitation
                else False
            ),
            "technician": self._m2o(solicitation, "tecnico_id") if solicitation else False,
            "destination_machine": (
                self._m2o(solicitation, "maquina_id") if solicitation else False
            ),
            "notes": self._field(line, "notas", "") or "",
        }

    # ============================================================
    # COMMERCIAL REQUEST SERIALIZERS
    # ============================================================

    def _serialize_request_line(self, line):
        result = self._selection(line, "resultado")
        return {
            "id": line.id,
            "machine": self._m2o(line, "maquina_id"),
            "serial": self._field(line, "serie", "") or "",
            "importation": self._field(line, "importacion", "") or "",
            "selected": bool(self._field(line, "seleccionada", False)),
            "result": result["value"],
            "result_label": result["label"],
            "current_customer": self._m2o(line, "cliente_actual_id"),
            "current_advisor": self._m2o(line, "asesora_actual_id"),
            "previous_reservation_state": self._field(
                line, "estado_reserva_anterior", ""
            )
            or "",
            "previous_deadline": self._date(
                self._field(line, "fecha_limite_anterior", False)
            ),
            "approved_deadline": self._date(
                self._field(line, "fecha_aprobada", False)
            ),
            "management_comment": self._field(line, "comentario_gerencia", "") or "",
        }

    def _serialize_request(self, rec, detail=False):
        state = self._selection(rec, "state")
        req_type = self._selection(rec, "tipo_solicitud")
        motive = self._selection(rec, "motivo")
        data = {
            "id": rec.id,
            "reference": self._field(rec, "name", "") or "",
            "state": state["value"],
            "state_label": state["label"],
            "requester": self._m2o(rec, "solicitante_id"),
            "customer": self._m2o(rec, "cliente_id"),
            "target_advisor": self._m2o(rec, "asesora_destino_id"),
            "type": req_type["value"],
            "type_label": req_type["label"],
            "motive": motive["value"],
            "motive_label": motive["label"],
            "detail": self._field(rec, "detalle_motivo", "") or "",
            "requested_modality": self._field(rec, "modalidad_solicitada", False),
            "requested_date": self._date(self._field(rec, "fecha_solicitada", False)),
            "requested_days": self._safe_int(self._field(rec, "dias_solicitados", 0)),
            "approved_modality": self._field(rec, "modalidad_aprobacion", False),
            "approved_date": self._date(self._field(rec, "fecha_aprobada", False)),
            "approved_days": self._safe_int(self._field(rec, "dias_aprobados", 0)),
            "management_comment": self._field(rec, "comentario_gerencia", "") or "",
            "processed_by": self._m2o(rec, "procesado_por_id"),
            "processed_at": self._datetime(self._field(rec, "fecha_procesamiento", False)),
            "created_at": self._datetime(self._field(rec, "create_date", False)),
            "machines_count": self._safe_int(self._field(rec, "cantidad_maquinas", 0)),
        }
        if detail:
            data["lines"] = [self._serialize_request_line(x) for x in rec.line_ids]
        return data

    # ============================================================
    # SUMMARY + ALERTS
    # ============================================================

    def _own_active_machines(self, user):
        return request.env[self.MACHINE_MODEL].sudo().search(
            [
                ("reserva_asesora_id", "=", user.id),
                ("reserva_estado", "in", list(self.ACTIVE_RESERVATION_STATES)),
                ("estado_ventas_id", "!=", self.DELIVERED_STATE),
            ]
        )

    def _build_summary(self, user):
        Machine = request.env[self.MACHINE_MODEL].sudo()
        RequestModel = request.env[self.REQUEST_MODEL].sudo()
        own = self._own_active_machines(user)

        expiring = expired = in_repair = problems = test_alerts = 0
        for machine in own:
            days = self._safe_int(self._field(machine, "reserva_dias_restantes", 0))
            is_expired = bool(self._field(machine, "reserva_vencida", False))
            deadline = self._field(machine, "reserva_fecha_limite", False)
            if is_expired:
                expired += 1
            elif deadline and 0 <= days <= 2:
                expiring += 1

            tech_state = self._field(machine, "estado_ventas_id", False)
            if tech_state == "en_revision":
                in_repair += 1
            if tech_state in self.PROBLEM_STATES:
                problems += 1

            if "prueba_ids" in machine._fields and machine.prueba_ids:
                latest = machine.prueba_ids.sorted(
                    key=lambda x: self._field(x, "fecha_ultima_actualizacion", False)
                    or self._field(x, "create_date", False)
                    or fields.Datetime.now(),
                    reverse=True,
                )[:1]
                if latest and self._field(latest, "tiene_alertas_snmp", False):
                    test_alerts += 1

        pending = RequestModel.search_count(
            [
                ("solicitante_id", "=", user.id),
                ("state", "in", ["draft", "pending", "partial"]),
            ]
        )
        available = Machine.search_count(
            [
                ("estado_ventas_id", "!=", self.DELIVERED_STATE),
                ("reserva_estado", "=", "libre"),
            ]
        )
        delivered = Machine.search_count(
            [
                ("estado_ventas_id", "=", self.DELIVERED_STATE),
                ("reserva_asesora_id", "=", user.id),
            ]
        )
        return {
            "my_reservations": len(own),
            "available": available,
            "expiring": expiring,
            "expired": expired,
            "in_repair": in_repair,
            "technical_problems": problems,
            "tests_with_alerts": test_alerts,
            "pending_requests": pending,
            "delivered": delivered,
            "attention_count": expiring + expired + problems + test_alerts + pending,
        }

    @http.route(
        "/api/app/sales/summary",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_summary(self, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            return self._json_response(
                {
                    "success": True,
                    "summary": self._build_summary(user),
                    "role": {"sales": True, "manager": self._is_manager(user)},
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/alerts",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_alerts(self, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            Machine = request.env[self.MACHINE_MODEL].sudo()
            RequestModel = request.env[self.REQUEST_MODEL].sudo()
            domain = [("estado_ventas_id", "!=", self.DELIVERED_STATE)]
            if not self._is_manager(user):
                domain.append(("reserva_asesora_id", "=", user.id))

            alerts = []
            for machine in Machine.search(domain, order="write_date desc, id desc"):
                rstate = self._field(machine, "reserva_estado", "libre")
                deadline = self._field(machine, "reserva_fecha_limite", False)
                days = self._safe_int(self._field(machine, "reserva_dias_restantes", 0))
                expired = bool(self._field(machine, "reserva_vencida", False))
                serial = self._field(machine, "serie_id", machine.display_name)

                if rstate in self.ACTIVE_RESERVATION_STATES and deadline:
                    if expired:
                        alerts.append(
                            {
                                "key": "reservation_expired:%s" % machine.id,
                                "type": "reservation_expired",
                                "severity": "danger",
                                "title": "Reserva vencida",
                                "message": "La separación de %s ya venció." % serial,
                                "machine_id": machine.id,
                                "request_id": False,
                                "days_remaining": days,
                            }
                        )
                    elif 0 <= days <= 2:
                        alerts.append(
                            {
                                "key": "reservation_expiring:%s:%s" % (machine.id, days),
                                "type": "reservation_expiring",
                                "severity": "danger" if days == 0 else "warning",
                                "title": "Reserva por vencer",
                                "message": "%s: quedan %s día(s)." % (serial, days),
                                "machine_id": machine.id,
                                "request_id": False,
                                "days_remaining": days,
                            }
                        )

                tech = self._field(machine, "estado_ventas_id", False)
                if tech in self.PROBLEM_STATES:
                    alerts.append(
                        {
                            "key": "technical_problem:%s:%s" % (machine.id, tech),
                            "type": "technical_problem",
                            "severity": "danger",
                            "title": "Equipo con observación técnica",
                            "message": "%s está en estado %s."
                            % (serial, self._selection_label(machine, "estado_ventas_id")),
                            "machine_id": machine.id,
                            "request_id": False,
                        }
                    )

                if "prueba_ids" in machine._fields and machine.prueba_ids:
                    latest = machine.prueba_ids.sorted(
                        key=lambda x: self._field(x, "fecha_ultima_actualizacion", False)
                        or self._field(x, "create_date", False)
                        or fields.Datetime.now(),
                        reverse=True,
                    )[:1]
                    if latest and self._field(latest, "tiene_alertas_snmp", False):
                        alerts.append(
                            {
                                "key": "test_alert:%s:%s" % (machine.id, latest.id),
                                "type": "test_alert",
                                "severity": "warning",
                                "title": "Prueba con alertas",
                                "message": "%s tiene %s alerta(s) en la última prueba."
                                % (
                                    serial,
                                    self._safe_int(
                                        self._field(latest, "cantidad_alertas_snmp", 0)
                                    ),
                                ),
                                "machine_id": machine.id,
                                "request_id": False,
                            }
                        )

            request_domain = [("state", "in", ["draft", "pending", "partial"])]
            if not self._is_manager(user):
                request_domain.append(("solicitante_id", "=", user.id))
            for rec in RequestModel.search(request_domain, order="create_date desc, id desc"):
                alerts.append(
                    {
                        "key": "commercial_request:%s" % rec.id,
                        "type": "commercial_request",
                        "severity": "info",
                        "title": "Solicitud comercial pendiente",
                        "message": "%s - %s"
                        % (rec.display_name, self._selection_label(rec, "tipo_solicitud")),
                        "machine_id": False,
                        "request_id": rec.id,
                    }
                )

            severity = {"danger": 0, "warning": 1, "info": 2, "success": 3}
            alerts.sort(key=lambda x: (severity.get(x.get("severity"), 99), x.get("title", "")))
            return self._json_response(
                {"success": True, "count": len(alerts), "alerts": alerts}
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # CUSTOMERS
    # ============================================================

    @http.route(
        "/api/app/sales/customers",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_customers(self, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            args = request.httprequest.args
            search = (args.get("search", "") or "").strip()
            limit = self._limit(args.get("limit"), default=50, maximum=100)
            offset = self._offset(args.get("offset"))
            Partner = request.env["res.partner"].sudo()
            domain = [("active", "=", True), ("is_company", "=", True)]
            if search:
                domain += [
                    "|",
                    "|",
                    "|",
                    ("name", "ilike", search),
                    ("vat", "ilike", search),
                    ("phone", "ilike", search),
                    ("email", "ilike", search),
                ]
            total = Partner.search_count(domain)
            records = Partner.search(
                domain, order="name asc, id asc", limit=limit, offset=offset
            )
            return self._json_response(
                {
                    "success": True,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "items": [self._serialize_customer(x) for x in records],
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # MACHINES
    # ============================================================

    def _machine_domain(self, user, scope, search, tech, reservation, availability):
        domain = []
        if scope != "delivered":
            domain.append(("estado_ventas_id", "!=", self.DELIVERED_STATE))

        if scope == "mine":
            domain.append(("reserva_asesora_id", "=", user.id))
        elif scope == "available":
            domain.append(("reserva_estado", "=", "libre"))
        elif scope in ("reserved", "expiring"):
            if not self._is_manager(user):
                domain.append(("reserva_asesora_id", "=", user.id))
            domain.append(("reserva_estado", "in", list(self.ACTIVE_RESERVATION_STATES)))
            if scope == "expiring":
                domain.append(("reserva_fecha_limite", "!=", False))
        elif scope == "problems":
            if not self._is_manager(user):
                domain.append(("reserva_asesora_id", "=", user.id))
            domain.append(("estado_ventas_id", "in", list(self.PROBLEM_STATES)))
        elif scope == "delivered":
            domain.append(("estado_ventas_id", "=", self.DELIVERED_STATE))
            if not self._is_manager(user):
                domain.append(("reserva_asesora_id", "=", user.id))
        elif scope != "all":
            domain.append(("reserva_asesora_id", "=", user.id))

        if tech:
            domain.append(("estado_ventas_id", "=", tech))
        if reservation:
            domain.append(("reserva_estado", "=", reservation))
        if availability:
            domain.append(("disponibilidad_id", "=", availability))
        if search:
            domain += [
                "|",
                "|",
                "|",
                ("serie_id", "ilike", search),
                ("importacion", "ilike", search),
                ("cliente_id.name", "ilike", search),
                ("name.name", "ilike", search),
            ]
        return domain

    @http.route(
        "/api/app/sales/machines",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_machines(self, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            args = request.httprequest.args
            scope = (args.get("scope", "mine") or "mine").strip()
            search = (args.get("search", "") or "").strip()
            tech = (args.get("technical_state", "") or "").strip()
            reservation = (args.get("reservation_state", "") or "").strip()
            availability = (args.get("availability", "") or "").strip()
            limit = self._limit(args.get("limit"))
            offset = self._offset(args.get("offset"))

            domain = self._machine_domain(
                user, scope, search, tech, reservation, availability
            )
            Machine = request.env[self.MACHINE_MODEL].sudo()
            total = Machine.search_count(domain)
            records = Machine.search(
                domain,
                order="reserva_fecha_limite asc, write_date desc, id desc",
                limit=limit,
                offset=offset,
            )
            items = [self._serialize_machine(x, user, detail=False) for x in records]

            if scope == "expiring":
                items = [
                    x
                    for x in items
                    if x["reservation"]["deadline"]
                    and (
                        x["reservation"]["expired"]
                        or 0 <= x["reservation"]["days_remaining"] <= 2
                    )
                ]
                total = len(items)

            return self._json_response(
                {
                    "success": True,
                    "scope": scope,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "items": items,
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/machines/<int:machine_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_machine_detail(self, machine_id, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            machine = self._get_machine(machine_id, sudo_read=True)
            if not machine:
                return self._machine_not_found()

            latest_test = False
            if "prueba_ids" in machine._fields and machine.prueba_ids:
                latest_test = machine.prueba_ids.sorted(
                    key=lambda x: self._field(x, "fecha_ultima_actualizacion", False)
                    or self._field(x, "create_date", False)
                    or fields.Datetime.now(),
                    reverse=True,
                )[:1]

            return self._json_response(
                {
                    "success": True,
                    "machine": self._serialize_machine(machine, user, detail=True),
                    "test_summary": (
                        self._serialize_test(latest_test, detail=False)
                        if latest_test
                        else False
                    ),
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # COMMERCIAL ACTIONS
    # ============================================================

    @http.route(
        "/api/app/sales/machines/<int:machine_id>/reserve",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def sales_machine_reserve(self, machine_id, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            machine = self._get_machine(machine_id, sudo_read=False)
            if not machine:
                return self._machine_not_found()
            self._ensure_owner(machine, user, allow_free=True)

            data = self._get_json_body()
            customer_id = self._safe_int(data.get("customer_id"), 0)
            customer = False
            if customer_id:
                customer = request.env["res.partner"].search(
                    [("id", "=", customer_id), ("active", "=", True)], limit=1
                )
                if not customer:
                    return self._json_response(
                        {
                            "success": False,
                            "code": "CUSTOMER_NOT_FOUND",
                            "message": "El cliente seleccionado no existe.",
                        },
                        status=404,
                    )

            machine._reserva_asignar_asesora(user, cliente=customer)

            # cliente_id sigue siendo el cliente operativo de sat.sat.
            # Su propio write aplica las validaciones comerciales existentes.
            if customer and (not machine.cliente_id or machine.cliente_id.id != customer.id):
                machine.write({"cliente_id": customer.id})

            refreshed = self._get_machine(machine.id, sudo_read=True)
            return self._json_response(
                {
                    "success": True,
                    "message": "La máquina fue separada correctamente.",
                    "machine": self._serialize_machine(refreshed, user, detail=True),
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/machines/<int:machine_id>/customer",
        type="http",
        auth="public",
        methods=["POST", "PATCH"],
        csrf=False,
        save_session=True,
    )
    def sales_machine_customer(self, machine_id, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            machine = self._get_machine(machine_id, sudo_read=False)
            if not machine:
                return self._machine_not_found()
            self._ensure_owner(machine, user, allow_free=True)

            data = self._get_json_body()
            customer_id = self._safe_int(data.get("customer_id"), 0)
            if not customer_id:
                return self._json_response(
                    {
                        "success": False,
                        "code": "CUSTOMER_REQUIRED",
                        "message": "Debe seleccionar un cliente.",
                    },
                    status=400,
                )

            customer = request.env["res.partner"].search(
                [("id", "=", customer_id), ("active", "=", True)], limit=1
            )
            if not customer:
                return self._json_response(
                    {
                        "success": False,
                        "code": "CUSTOMER_NOT_FOUND",
                        "message": "El cliente seleccionado no existe.",
                    },
                    status=404,
                )

            if self._field(machine, "reserva_estado", "libre") == "libre":
                machine._reserva_asignar_asesora(user, cliente=customer)
            machine.write({"cliente_id": customer.id})

            refreshed = self._get_machine(machine.id, sudo_read=True)
            return self._json_response(
                {
                    "success": True,
                    "message": "Cliente asignado correctamente.",
                    "machine": self._serialize_machine(refreshed, user, detail=True),
                }
            )
        except ValidationError as exc:
            return self._json_response(
                {
                    "success": False,
                    "code": "AUTHORIZATION_REQUIRED",
                    "message": str(exc),
                    "suggested_request_type": "cambiar_cliente",
                },
                status=409,
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/machines/<int:machine_id>/release",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def sales_machine_release(self, machine_id, **kwargs):
        user, error = self._require_manager()
        if error:
            return error
        try:
            machine = self._get_machine(machine_id, sudo_read=False)
            if not machine:
                return self._machine_not_found()
            data = self._get_json_body()
            motive = (
                data.get("motive")
                or data.get("reason")
                or "Liberación manual desde la app de Ventas"
            )
            machine._reserva_liberar(tipo="manual", motivo=motive)
            refreshed = self._get_machine(machine.id, sudo_read=True)
            return self._json_response(
                {
                    "success": True,
                    "message": "La máquina fue liberada correctamente.",
                    "machine": self._serialize_machine(refreshed, user, detail=True),
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/machines/<int:machine_id>/review",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def sales_machine_review(self, machine_id, **kwargs):
        """
        Coloca la máquina en la cola de revisión usando la lógica
        existente del modelo sat.sat.

        No escribe estado_ventas_id directamente: se llama
        action_colocar_en_revision() para conservar fecha, puesto
        de cola, chatter y demás efectos del modelo.
        """
        user, error = self._require_sales_user()
        if error:
            return error

        try:
            machine = self._get_machine(
                machine_id,
                sudo_read=False,
            )

            if not machine:
                return self._machine_not_found()

            current_state = self._field(
                machine,
                "estado_ventas_id",
                "",
            )

            if current_state != "sin_revisar":
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_TECHNICAL_STATE",
                        "message": (
                            "Solo una máquina en estado "
                            "'Sin revisar' puede colocarse en revisión."
                        ),
                    },
                    status=409,
                )

            machine.action_colocar_en_revision()

            refreshed = self._get_machine(
                machine.id,
                sudo_read=True,
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "La máquina fue colocada en la cola "
                        "de revisión correctamente."
                    ),
                    "machine": self._serialize_machine(
                        refreshed,
                        user,
                        detail=True,
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/machines/<int:machine_id>/review/remove",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def sales_machine_review_remove(self, machine_id, **kwargs):
        """
        Retira la máquina de la cola de revisión usando
        action_quitar_de_revision() del modelo sat.sat.
        """
        user, error = self._require_sales_user()
        if error:
            return error

        try:
            machine = self._get_machine(
                machine_id,
                sudo_read=False,
            )

            if not machine:
                return self._machine_not_found()

            current_state = self._field(
                machine,
                "estado_ventas_id",
                "",
            )

            if current_state != "para_revision":
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_TECHNICAL_STATE",
                        "message": (
                            "Solo una máquina en estado "
                            "'Para revisión' puede retirarse de la cola."
                        ),
                    },
                    status=409,
                )

            machine.action_quitar_de_revision()

            refreshed = self._get_machine(
                machine.id,
                sudo_read=True,
            )

            return self._json_response(
                {
                    "success": True,
                    "message": (
                        "La máquina fue retirada de la cola "
                        "de revisión correctamente."
                    ),
                    "machine": self._serialize_machine(
                        refreshed,
                        user,
                        detail=True,
                    ),
                }
            )

        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # COMMERCIAL REQUESTS
    # ============================================================

    @http.route(
        "/api/app/sales/requests",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_requests(self, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            args = request.httprequest.args
            scope = (args.get("scope", "mine") or "mine").strip()
            state = (args.get("state", "") or "").strip()
            limit = self._limit(args.get("limit"))
            offset = self._offset(args.get("offset"))

            domain = []
            if not self._is_manager(user) or scope == "mine":
                domain.append(("solicitante_id", "=", user.id))
            if scope == "pending":
                domain.append(("state", "in", ["draft", "pending", "partial"]))
            if state:
                domain.append(("state", "=", state))

            Model = request.env[self.REQUEST_MODEL].sudo()
            total = Model.search_count(domain)
            records = Model.search(
                domain,
                order="create_date desc, id desc",
                limit=limit,
                offset=offset,
            )
            return self._json_response(
                {
                    "success": True,
                    "scope": scope,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "items": [self._serialize_request(x) for x in records],
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/requests",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def sales_request_create(self, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            data = self._get_json_body()
            machine_ids = data.get("machine_ids") or []
            if not machine_ids:
                one = self._safe_int(data.get("machine_id"), 0)
                if one:
                    machine_ids = [one]
            machine_ids = list(
                dict.fromkeys(
                    self._safe_int(x, 0)
                    for x in machine_ids
                    if self._safe_int(x, 0)
                )
            )
            if not machine_ids:
                return self._json_response(
                    {
                        "success": False,
                        "code": "MACHINES_REQUIRED",
                        "message": "Debe seleccionar al menos una máquina.",
                    },
                    status=400,
                )

            machines = request.env[self.MACHINE_MODEL].search([("id", "in", machine_ids)])
            if len(machines) != len(machine_ids):
                return self._machine_not_found()

            req_type = (data.get("type") or data.get("request_type") or "").strip()
            motive = (data.get("motive") or data.get("reason") or "").strip()
            detail = (data.get("detail") or data.get("detail_motive") or "").strip()
            valid_types = {
                "reservar",
                "extender",
                "reducir",
                "cambiar_fecha",
                "cambiar_cliente",
                "cambiar_asesora",
                "liberar",
            }
            if req_type not in valid_types:
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_REQUEST_TYPE",
                        "message": "El tipo de solicitud no es válido.",
                    },
                    status=400,
                )
            if not motive or not detail:
                return self._json_response(
                    {
                        "success": False,
                        "code": "REQUEST_JUSTIFICATION_REQUIRED",
                        "message": "Debe indicar motivo y detalle/sustento.",
                    },
                    status=400,
                )

            for machine in machines:
                self._ensure_owner(machine, user, allow_free=req_type == "reservar")

            customer_id = self._safe_int(data.get("customer_id"), 0)
            advisor_id = self._safe_int(data.get("advisor_id"), user.id)
            modality = (data.get("modality") or data.get("deadline_mode") or "").strip()
            requested_date = data.get("requested_date") or data.get("date") or False
            requested_days = self._safe_int(
                data.get("requested_days") or data.get("days"), 0
            )

            if req_type in ("liberar", "cambiar_asesora"):
                modality = False
                requested_date = False
                requested_days = 0
            elif req_type == "cambiar_cliente" and not modality:
                modality = "mantener"
            elif not modality:
                modality = "fecha"

            vals = {
                "maquina_ids": [(6, 0, machine_ids)],
                "tipo_solicitud": req_type,
                "asesora_destino_id": advisor_id,
                "motivo": motive,
                "detalle_motivo": detail,
                "modalidad_plazo": modality or False,
                "fecha_solicitada": requested_date if modality == "fecha" else False,
                "dias_solicitados": requested_days if modality == "dias" else 0,
            }
            if customer_id:
                vals["cliente_id"] = customer_id

            wizard = request.env[self.REQUEST_WIZARD_MODEL].create(vals)
            action = wizard.action_crear_solicitud()
            created_id = action.get("res_id") if isinstance(action, dict) else False
            rec = (
                self._get_commercial_request(created_id, sudo_read=True)
                if created_id
                else False
            )
            return self._json_response(
                {
                    "success": True,
                    "message": "La solicitud fue enviada a gerencia.",
                    "request": self._serialize_request(rec, detail=True) if rec else False,
                },
                status=201,
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/requests/<int:request_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_request_detail(self, request_id, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            rec = self._get_commercial_request(request_id, sudo_read=True)
            if not rec:
                return self._request_not_found()
            if not self._is_manager(user) and rec.solicitante_id.id != user.id:
                return self._json_response(
                    {
                        "success": False,
                        "code": "REQUEST_ACCESS_DENIED",
                        "message": "No tiene acceso a esta solicitud.",
                    },
                    status=403,
                )
            return self._json_response(
                {"success": True, "request": self._serialize_request(rec, detail=True)}
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/requests/<int:request_id>/cancel",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def sales_request_cancel(self, request_id, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            rec = self._get_commercial_request(request_id, sudo_read=False)
            if not rec:
                return self._request_not_found()
            if not self._is_manager(user) and rec.solicitante_id.id != user.id:
                return self._json_response(
                    {
                        "success": False,
                        "code": "REQUEST_ACCESS_DENIED",
                        "message": "Solo puede cancelar sus propias solicitudes.",
                    },
                    status=403,
                )
            rec.action_cancelar()
            refreshed = self._get_commercial_request(request_id, sudo_read=True)
            return self._json_response(
                {
                    "success": True,
                    "message": "La solicitud fue cancelada.",
                    "request": self._serialize_request(refreshed, detail=True),
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/requests/<int:request_id>/decision",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=True,
    )
    def sales_request_decision(self, request_id, **kwargs):
        user, error = self._require_manager()
        if error:
            return error
        try:
            rec = self._get_commercial_request(request_id, sudo_read=False)
            if not rec:
                return self._request_not_found()

            data = self._get_json_body()
            decision = (data.get("decision") or data.get("action") or "").strip()
            if decision not in ("approve", "reject"):
                return self._json_response(
                    {
                        "success": False,
                        "code": "INVALID_DECISION",
                        "message": "La decisión debe ser 'approve' o 'reject'.",
                    },
                    status=400,
                )

            line_ids = [
                self._safe_int(x, 0)
                for x in (data.get("line_ids") or [])
                if self._safe_int(x, 0)
            ]
            if line_ids:
                rec.line_ids.with_context(sat_reserva_internal_line_write=True).write(
                    {"seleccionada": False}
                )
                selected = rec.line_ids.filtered(
                    lambda line: line.id in line_ids and line.resultado == "pending"
                )
                if not selected:
                    return self._json_response(
                        {
                            "success": False,
                            "code": "NO_PENDING_LINES",
                            "message": "No hay máquinas pendientes seleccionadas.",
                        },
                        status=400,
                    )
                selected.with_context(sat_reserva_internal_line_write=True).write(
                    {"seleccionada": True}
                )

            vals = {
                "comentario_gerencia": data.get("comment")
                or data.get("management_comment")
                or ""
            }
            if data.get("approved_modality"):
                vals["modalidad_aprobacion"] = data.get("approved_modality")
            if "approved_date" in data:
                vals["fecha_aprobada"] = data.get("approved_date") or False
            if "approved_days" in data:
                vals["dias_aprobados"] = self._safe_int(data.get("approved_days"), 0)
            rec.write(vals)

            if decision == "approve":
                rec.action_aprobar_seleccionadas()
                message = "Las máquinas seleccionadas fueron aprobadas."
            else:
                rec.action_rechazar_seleccionadas()
                message = "Las máquinas seleccionadas fueron rechazadas."

            refreshed = self._get_commercial_request(request_id, sudo_read=True)
            return self._json_response(
                {
                    "success": True,
                    "message": message,
                    "request": self._serialize_request(refreshed, detail=True),
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    # ============================================================
    # REPAIR READ-ONLY ENDPOINTS FOR SALES
    # ============================================================

    def _machine_and_repair(self, machine_id):
        machine = self._get_machine(machine_id, sudo_read=True)
        if not machine:
            return False, False
        return machine, self._get_main_repair(machine)

    @http.route(
        "/api/app/sales/machines/<int:machine_id>/repair",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_repair(self, machine_id, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            machine, repair = self._machine_and_repair(machine_id)
            if not machine:
                return self._machine_not_found()
            return self._json_response(
                {
                    "success": True,
                    "repair": self._serialize_repair_detail(repair) if repair else False,
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/machines/<int:machine_id>/repair/checklist",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_repair_checklist(self, machine_id, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            machine, repair = self._machine_and_repair(machine_id)
            if not machine:
                return self._machine_not_found()
            components = (
                [self._serialize_component(x) for x in repair.componente_eval_ids]
                if repair and "componente_eval_ids" in repair._fields
                else []
            )
            accessories = (
                [self._serialize_accessory(x) for x in repair.accesorio_eval_ids]
                if repair and "accesorio_eval_ids" in repair._fields
                else []
            )
            return self._json_response(
                {
                    "success": True,
                    "repair_id": repair.id if repair else False,
                    "components": components,
                    "accessories": accessories,
                    "readonly": True,
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/machines/<int:machine_id>/repair/photos",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_repair_photos(self, machine_id, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            machine, repair = self._machine_and_repair(machine_id)
            if not machine:
                return self._machine_not_found()
            photos = []
            if repair and "fotos_ids" in repair._fields:
                photos = [
                    self._serialize_photo(x)
                    for x in repair.fotos_ids.sorted(
                        key=lambda p: (self._safe_int(self._field(p, "sequence", 0)), p.id)
                    )
                ]
            return self._json_response(
                {
                    "success": True,
                    "repair_id": repair.id if repair else False,
                    "count": len(photos),
                    "items": photos,
                    "readonly": True,
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/photos/<int:photo_id>/image",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_photo_image(self, photo_id, **kwargs):
        """
        Sirve la fotografía directamente a la app.

        Importante:
        No redirigir a public_link/url_foto. Algunos public_link de pCloud
        se almacenan como /publink/show?... y al redirigirlos Odoo los
        interpreta como una ruta local, provocando 404.

        Se reutiliza get_download_content() del modelo reparaciones.foto,
        que ya es la lógica usada por /gallery/download/<foto_id>.
        """
        user, error = self._require_sales_user()
        if error:
            return error

        try:
            if not self._model_exists(self.PHOTO_MODEL):
                return self._json_response(
                    {
                        "success": False,
                        "code": "PHOTO_MODEL_NOT_FOUND",
                    },
                    status=404,
                )

            photo = (
                request.env[self.PHOTO_MODEL]
                .sudo()
                .search(
                    [("id", "=", photo_id)],
                    limit=1,
                )
            )

            if not photo:
                return self._json_response(
                    {
                        "success": False,
                        "code": "PHOTO_NOT_FOUND",
                        "message": "La fotografía no existe.",
                    },
                    status=404,
                )

            # ----------------------------------------------------
            # 1) MISMA LÓGICA QUE USA LA GALERÍA EXISTENTE
            # ----------------------------------------------------
            if hasattr(photo, "get_download_content"):
                try:
                    data = photo.get_download_content()

                    if (
                        data
                        and data.get("content")
                    ):
                        raw = data.get("content")

                        if isinstance(raw, str):
                            raw = raw.encode("ascii")

                        content = base64.b64decode(raw)

                        if content:
                            mimetype = (
                                data.get("content_type")
                                or self._field(
                                    photo,
                                    "mimetype",
                                    False,
                                )
                                or "image/jpeg"
                            )

                            filename = (
                                data.get("filename")
                                or self._field(
                                    photo,
                                    "nombre_foto",
                                    False,
                                )
                                or "repair_photo_%s.jpg"
                                % photo.id
                            )

                            return request.make_response(
                                content,
                                headers=[
                                    (
                                        "Content-Type",
                                        mimetype,
                                    ),
                                    (
                                        "Content-Disposition",
                                        'inline; filename="%s"'
                                        % filename.replace(
                                            '"',
                                            "",
                                        ),
                                    ),
                                    (
                                        "Cache-Control",
                                        "private, max-age=300",
                                    ),
                                    (
                                        "X-Content-Type-Options",
                                        "nosniff",
                                    ),
                                ],
                            )

                except Exception:
                    _logger.exception(
                        "No se pudo obtener la foto %s "
                        "mediante get_download_content().",
                        photo.id,
                    )

            # ----------------------------------------------------
            # 2) FALLBACK: BINARIO LOCAL SI EXISTE
            # ----------------------------------------------------
            raw = self._field(
                photo,
                "foto_binario",
                False,
            )

            if raw:
                if isinstance(raw, str):
                    raw = raw.encode("ascii")

                try:
                    content = base64.b64decode(raw)
                except Exception:
                    content = False

                if content:
                    mimetype = (
                        self._field(
                            photo,
                            "mimetype",
                            False,
                        )
                        or "image/jpeg"
                    )

                    filename = (
                        self._field(
                            photo,
                            "nombre_foto",
                            False,
                        )
                        or "repair_photo_%s.jpg"
                        % photo.id
                    )

                    return request.make_response(
                        content,
                        headers=[
                            (
                                "Content-Type",
                                mimetype,
                            ),
                            (
                                "Content-Disposition",
                                'inline; filename="%s"'
                                % filename.replace(
                                    '"',
                                    "",
                                ),
                            ),
                            (
                                "Cache-Control",
                                "private, max-age=300",
                            ),
                            (
                                "X-Content-Type-Options",
                                "nosniff",
                            ),
                        ],
                    )

            return self._json_response(
                {
                    "success": False,
                    "code": "PHOTO_CONTENT_NOT_AVAILABLE",
                    "message": (
                        "No fue posible obtener el contenido "
                        "de la fotografía."
                    ),
                },
                status=404,
            )

        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/machines/<int:machine_id>/repair/parts",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_repair_parts(self, machine_id, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            machine = self._get_machine(machine_id, sudo_read=True)
            if not machine:
                return self._machine_not_found()
            if "partes_retiradas_ids" in machine._fields:
                lines = machine.partes_retiradas_ids
            elif self._model_exists(self.PART_MODEL):
                lines = request.env[self.PART_MODEL].sudo().search(
                    [("maquina_origen_sat_id", "=", machine.id)], order="id desc"
                )
            else:
                lines = []
            items = [self._serialize_part(x) for x in lines]
            return self._json_response(
                {
                    "success": True,
                    "machine_id": machine.id,
                    "count": len(items),
                    "items": items,
                    "readonly": True,
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/machines/<int:machine_id>/repair/tests",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_repair_tests(self, machine_id, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            machine = self._get_machine(machine_id, sudo_read=True)
            if not machine:
                return self._machine_not_found()
            if "prueba_ids" in machine._fields:
                tests = machine.prueba_ids.sorted(
                    key=lambda x: self._field(x, "fecha_ultima_actualizacion", False)
                    or self._field(x, "create_date", False)
                    or fields.Datetime.now(),
                    reverse=True,
                )
            elif self._model_exists(self.TEST_MODEL):
                tests = request.env[self.TEST_MODEL].sudo().search(
                    [("maquina_id", "=", machine.id)],
                    order="fecha_ultima_actualizacion desc, id desc",
                )
            else:
                tests = []
            items = [self._serialize_test(x, detail=True) for x in tests]
            return self._json_response(
                {
                    "success": True,
                    "machine_id": machine.id,
                    "count": len(items),
                    "items": items,
                    "latest": items[0] if items else False,
                    "readonly": True,
                }
            )
        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/sales/machines/<int:machine_id>/repair/report",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def sales_repair_report(self, machine_id, **kwargs):
        user, error = self._require_sales_user()
        if error:
            return error
        try:
            machine, repair = self._machine_and_repair(machine_id)
            if not machine:
                return self._machine_not_found()
            if not repair:
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_NOT_FOUND",
                        "message": "La máquina no tiene una reparación registrada.",
                    },
                    status=404,
                )

            report = request.env.ref(
                "sat.action_report_reparaciones_ventas", raise_if_not_found=False
            )
            if not report:
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_REPORT_NOT_FOUND",
                        "message": "No se encontró el reporte de reparaciones para Ventas.",
                    },
                    status=404,
                )

            report_name = (
                report.report_name
                if "report_name" in report._fields
                else False
            )
            if not report_name:
                return self._json_response(
                    {
                        "success": False,
                        "code": "REPAIR_REPORT_NOT_CONFIGURED",
                        "message": "El reporte no tiene report_name configurado.",
                    },
                    status=404,
                )

            pdf, _ = request.env["ir.actions.report"].sudo()._render_qweb_pdf(
                report_name,
                res_ids=[repair.id],
            )
            filename = "reparacion_%s.pdf" % (
                self._field(repair, "name", repair.id) or repair.id
            )
            encoded = base64.b64encode(
                pdf
            ).decode(
                "ascii"
            )

            return self._json_response(
                {
                    "success": True,
                    "filename": filename,
                    "mimetype": "application/pdf",
                    "content_base64": encoded,
                }
            )
        except Exception as exc:
            _logger.exception(
                "Error generando reporte de reparación para Ventas. machine_id=%s",
                machine_id,
            )
            return self._error_response(exc)
