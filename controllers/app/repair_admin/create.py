# -*- coding: utf-8 -*-
# REPAIR_ADMIN_CREATE_V5_ODOO_MODEL_WORKFLOW_MULTICHANNEL

import logging

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from .base import RepairAdminBaseController


_logger = logging.getLogger(__name__)


class RepairAdminCreateController(RepairAdminBaseController):

    @http.route(
        "/api/app/repairs/admin/technicians",
        type="http",
        auth="public",
        methods=["GET", "OPTIONS"],
        csrf=False,
        readonly=True,
        save_session=True,
    )
    def repair_admin_technicians(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return self._options_response()

        user, error = self._ra_require_admin()
        if error:
            return error

        try:
            search_term = (
                request.httprequest.args.get("search") or ""
            ).strip().lower()

            users = self._ra_group_users(self.TECH_GROUP).filtered(
                lambda item: item.active and not item.share
            )

            if search_term:
                users = users.filtered(
                    lambda item: (
                        search_term in (
                            item.display_name or item.name or ""
                        ).lower()
                        or search_term in (item.login or "").lower()
                    )
                )

            users = users.sorted(
                key=lambda item: (
                    item.display_name or item.name or ""
                ).lower()
            )

            items = []
            for technician in users:
                available = self._ra_technician_available(technician)
                items.append({
                    "id": technician.id,
                    "name": technician.display_name or technician.name or "",
                    "available": available,
                    "can_assign": available,
                })

            return self._json_response({
                "success": True,
                "total": len(items),
                "items": items,
            })

        except Exception as exc:
            return self._error_response(exc)

    @http.route(
        "/api/app/repairs/admin/create",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
        save_session=True,
    )
    def repair_admin_create(self, **kwargs):
        if request.httprequest.method == "OPTIONS":
            return self._options_response()

        user, error = self._ra_require_admin()
        if error:
            return error

        try:
            data = self._get_json_body()
            machine_id = self._ra_safe_int(data.get("machine_id"), 0)
            technician_id = self._ra_safe_int(
                data.get("technician_id") or data.get("responsible_id"),
                0,
            )

            if machine_id <= 0:
                return self._json_response({
                    "success": False,
                    "code": "MACHINE_REQUIRED",
                    "message": "Debe seleccionar una máquina.",
                }, status=400)

            if technician_id <= 0:
                return self._json_response({
                    "success": False,
                    "code": "TECHNICIAN_REQUIRED",
                    "message": "Debe seleccionar un técnico.",
                }, status=400)

            machine = self._ra_get_machine(machine_id)
            if not machine:
                return self._ra_machine_not_found()

            if self._ra_safe_value(machine, "estado_ventas_id", "") != "para_revision":
                return self._json_response({
                    "success": False,
                    "code": "MACHINE_NOT_IN_REVIEW_QUEUE",
                    "message": (
                        "Solo se puede crear la reparación de una máquina "
                        "que esté en 'Para revisión'."
                    ),
                }, status=409)

            existing = self._ra_get_existing_repair(machine)
            if existing:
                return self._json_response({
                    "success": False,
                    "code": "REPAIR_ALREADY_EXISTS",
                    "message": "La máquina ya tiene una reparación registrada.",
                    "repair": self._ra_serialize_repair_short(existing),
                }, status=409)

            technician = request.env[self.USER_MODEL].sudo().browse(
                technician_id
            ).exists()
            if not technician or not self._ra_is_valid_technician(technician):
                return self._json_response({
                    "success": False,
                    "code": "INVALID_TECHNICIAN",
                    "message": "El usuario seleccionado no es un técnico válido.",
                }, status=400)

            if not self._ra_technician_available(technician):
                return self._json_response({
                    "success": False,
                    "code": "TECHNICIAN_UNAVAILABLE",
                    "message": (
                        "El técnico seleccionado tiene una ausencia o permiso "
                        "activo y no puede recibir la reparación."
                    ),
                }, status=409)

            # res.users.id y hr.employee.id NO son equivalentes.
            # El estado de revisión de la máquina usa trabajadores_id.
            employee = request.env["hr.employee"].sudo().search([
                ("user_id", "=", technician.id),
            ], limit=1)
            if not employee:
                return self._json_response({
                    "success": False,
                    "code": "TECHNICIAN_WITHOUT_EMPLOYEE",
                    "message": (
                        "El técnico seleccionado no tiene un empleado "
                        "asociado en Odoo."
                    ),
                }, status=400)

            Repair = request.env[self.REPAIR_MODEL].sudo()

            # Este create() del modelo ejecuta la lógica original:
            # secuencia, validaciones, prueba, carpeta pCloud por máquina,
            # código QR y evaluaciones. No duplicar esas funciones aquí.
            # El cambio de estado se hace dentro de la misma transacción.
            with request.env.cr.savepoint():
                repair = Repair.create({
                    "maquina_id": machine.id,
                    "responsable_id": technician.id,
                })

                # El modelo no cambia automáticamente para_revision a
                # en_revision: esta operación reproduce la asignación de
                # _create_next_reparacion() para la creación desde Flutter.
                machine.sudo().write({
                    "estado_ventas_id": "en_revision",
                    "trabajadores_id": employee.id,
                })

                # Evitar confirmar un resultado incompleto si la carpeta
                # obligatoria no quedó asociada al registro.
                if not repair.pcloud_folder_id:
                    raise UserError(
                        "La reparación no tiene una carpeta pCloud asociada. "
                        "Revise la configuración de almacenamiento."
                    )

            _logger.info(
                "Reparación %s creada desde Flutter: máquina=%s, "
                "técnico_user=%s, empleado=%s, carpeta=%s",
                repair.id, machine.id, technician.id, employee.id,
                repair.pcloud_folder_id,
            )

            # El proceso de autoasignación de Odoo invoca este mismo método
            # después de crear la reparación. create() no lo llama solo.
            # Un error de WhatsApp no debe borrar la reparación ya preparada.
            whatsapp_attempted = False
            whatsapp_warning = False
            notify_method = getattr(
                repair, "enviar_mensaje_whatsapp_reparaciones", None
            )
            if callable(notify_method):
                try:
                    notify_method()
                    whatsapp_attempted = True
                except Exception:
                    whatsapp_warning = True
                    _logger.exception(
                        "Fallo al solicitar notificación WhatsApp de "
                        "reparación %s al técnico %s",
                        repair.id, technician.id,
                    )
            else:
                whatsapp_warning = True
                _logger.warning(
                    "El modelo reparaciones.reparaciones no expone "
                    "enviar_mensaje_whatsapp_reparaciones() para reparación %s",
                    repair.id,
                )

            # Push es independiente del envío por WhatsApp. El servicio
            # distribuye la alerta a TODOS los tokens FCM activos del técnico.
            # No se cancela la reparación si no hay equipos o Firebase falla.
            push_result = {
                "success": False,
                "sent": 0,
                "failed": 0,
                "code": "PUSH_NOT_ATTEMPTED",
            }
            try:
                push_result = request.env["app.push.service"].sudo().send_to_user(
                    user=technician,
                    title="Nueva reparación asignada",
                    body=(
                        "Se te asignó la reparación %s. "
                        "Ingresa a Copier Support para revisarla."
                    ) % (repair.name or repair.id),
                    data={
                        "type": "repair_assignment",
                        "repair_id": str(repair.id),
                        "machine_id": str(machine.id),
                    },
                )
                _logger.info(
                    "Push reparación %s: enviados=%s, fallidos=%s, código=%s",
                    repair.id,
                    push_result.get("sent", 0),
                    push_result.get("failed", 0),
                    push_result.get("code", ""),
                )
            except Exception:
                _logger.exception(
                    "Error al solicitar notificación FCM para reparación %s",
                    repair.id,
                )
                push_result = {
                    "success": False,
                    "sent": 0,
                    "failed": 0,
                    "code": "PUSH_EXCEPTION",
                }

            return self._json_response({
                "success": True,
                "code": "REPAIR_CREATED",
                "message": "Reparación creada y asignada correctamente.",
                "repair": self._ra_serialize_repair_detail(repair),
                "pcloud_folder_id": repair.pcloud_folder_id,
                "whatsapp_attempted": whatsapp_attempted,
                "whatsapp_warning": whatsapp_warning,
                "push": {
                    "success": bool(push_result.get("success")),
                    "sent": int(push_result.get("sent") or 0),
                    "failed": int(push_result.get("failed") or 0),
                    "code": push_result.get("code") or "",
                },
            }, status=201)

        except (ValidationError, UserError) as exc:
            return self._json_response({
                "success": False,
                "code": "REPAIR_VALIDATION_ERROR",
                "message": str(exc),
            }, status=400)

        except Exception as exc:
            return self._error_response(exc)
