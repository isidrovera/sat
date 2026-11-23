# -*- coding: utf-8 -*-
"""Sincronización de entregas REALES con el kardex de tóner del cliente.

Sustituye íntegramente el archivo existente que define
TonerDeliveryScheduleStockIntegration. No crea modelos ni depende de n8n.
Compatible con los modelos toner.delivery.schedule,
toner.delivery.confirmation y toner.stock.movement suministrados.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class TonerDeliveryScheduleStockIntegration(models.Model):
    _inherit = "toner.delivery.schedule"

    _DELIVERY_COLOR_FIELDS = {
        "black": "toner_black_delivered",
        "cyan": "toner_cyan_delivered",
        "magenta": "toner_magenta_delivered",
        "yellow": "toner_yellow_delivered",
    }
    _COLOR_NAMES = {
        "black": "Negro",
        "cyan": "Cian",
        "magenta": "Magenta",
        "yellow": "Amarillo",
    }

    stock_movements_created = fields.Boolean(
        string="Stock cliente actualizado",
        compute="_compute_stock_movements_created",
        store=False,
    )
    stock_movement_count = fields.Integer(
        string="Movimientos de stock",
        compute="_compute_stock_movement_count",
    )
    stock_last_sync_date = fields.Datetime(
        string="Última sincronización de stock",
        readonly=True,
        copy=False,
    )
    stock_sync_error = fields.Text(
        string="Error de sincronización de stock",
        readonly=True,
        copy=False,
    )

    def _compute_stock_movements_created(self):
        Movement = self.env["toner.stock.movement"].sudo()
        for delivery in self:
            if not delivery.id or not delivery.confirmation_id:
                delivery.stock_movements_created = False
                continue
            quantities = delivery._get_confirmed_toner_quantities(strict=False)
            if not quantities:
                delivery.stock_movements_created = False
                continue
            movements = Movement.search([
                ("delivery_id", "=", delivery.id),
                ("movement_type", "=", "delivery"),
                ("state", "=", "posted"),
            ])
            by_color = {m.color: m.quantity for m in movements}
            delivery.stock_movements_created = all(
                by_color.get(color) == qty
                for color, qty in quantities.items() if qty > 0
            ) and not any(
                color not in quantities or quantities[color] != qty
                for color, qty in by_color.items()
            )

    def _compute_stock_movement_count(self):
        Movement = self.env["toner.stock.movement"].sudo()
        for delivery in self:
            delivery.stock_movement_count = (
                Movement.search_count([("delivery_id", "=", delivery.id)])
                if delivery.id else 0
            )

    def _get_confirmed_toner_quantities(self, strict=True):
        """Cantidad realmente recibida, NUNCA cantidad programada.

        El formulario de confirmación original primero escribe el estado
        'entregado' en la programación y después enlaza confirmation_id.
        Por eso la sincronización se difiere hasta existir el enlace.
        """
        self.ensure_one()
        confirmation = self.confirmation_id
        if not confirmation:
            if strict:
                raise UserError(_(
                    "No se puede actualizar el stock: falta la confirmación "
                    "de recepción de la entrega %s."
                ) % self.display_name)
            return {}
        if confirmation.schedule_id != self:
            raise ValidationError(_(
                "La confirmación de entrega no corresponde a esta programación."
            ))
        if confirmation.state not in ("confirmed", "processed"):
            if strict:
                raise UserError(_(
                    "La recepción debe estar confirmada antes de registrar "
                    "el stock del cliente."
                ))
            return {}
        quantities = {}
        for color, field_name in self._DELIVERY_COLOR_FIELDS.items():
            qty = int(getattr(confirmation, field_name, 0) or 0)
            if qty < 0:
                raise ValidationError(_(
                    "No se permiten cantidades entregadas negativas: %s."
                ) % self._COLOR_NAMES[color])
            quantities[color] = qty
        if strict and not any(quantities.values()):
            raise UserError(_(
                "La confirmación no registra ninguna unidad realmente recibida."
            ))
        return quantities

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for delivery in records:
            if delivery.state == "entregado" and delivery.confirmation_id:
                delivery._sync_client_toner_stock()
        return records

    def write(self, vals):
        old_states = {delivery.id: delivery.state for delivery in self}
        result = super().write(vals)
        # La implementación previa del formulario hace:
        # schedule.state = 'entregado'; schedule.confirmation_id = confirmation.id.
        # Sincronizamos también en la segunda escritura, no solo al cambiar state.
        relevant = bool({"state", "confirmation_id"} & set(vals))
        if relevant and not self.env.context.get("skip_toner_stock_sync"):
            for delivery in self:
                if delivery.state != "entregado" or not delivery.confirmation_id:
                    continue
                # Una edición posterior de confirmation_id también permite
                # detectar discrepancias, pero la idempotencia impide duplicados.
                if old_states.get(delivery.id) != "entregado" or "confirmation_id" in vals:
                    delivery._sync_client_toner_stock()
        return result

    def _sync_client_toner_stock(self):
        """Aplica al kardex SOLO unidades recibidas y confirmadas.

        Una entrega/color se registra una única vez con una clave estable.
        Si alguien cambia una confirmación después de contabilizarla, NO
        se reescribe el movimiento histórico: se requiere corrección.
        """
        self.ensure_one()
        if self.state != "entregado":
            raise UserError(_(
                "Solo es posible sincronizar una entrega en estado Entregado."
            ))
        quantities = self._get_confirmed_toner_quantities(strict=True)
        if not self.equipment_id:
            raise ValidationError(_("La programación no tiene equipo asociado."))

        Movement = self.env["toner.stock.movement"].sudo()
        existing = Movement.search([
            ("delivery_id", "=", self.id),
            ("movement_type", "=", "delivery"),
        ])
        # Rechazar cualquier discrepancia antes de crear movimientos parciales.
        for mov in existing:
            expected_qty = quantities.get(mov.color, 0)
            if mov.state == "posted" and mov.quantity != expected_qty:
                raise UserError(_(
                    "La entrega %(delivery)s ya tiene un movimiento histórico "
                    "de %(color)s por %(original)s unidad(es), pero la "
                    "confirmación ahora indica %(new)s. No se modifica el "
                    "kardex anterior: registre un ajuste/corrección controlado."
                ) % {
                    "delivery": self.secuencia,
                    "color": self._COLOR_NAMES.get(mov.color, mov.color),
                    "original": mov.quantity,
                    "new": expected_qty,
                })
            if mov.state != "posted":
                raise UserError(_(
                    "Existe un movimiento anulado asociado a esta entrega. "
                    "Revise el historial antes de sincronizar nuevamente."
                ))

        result = Movement.browse()
        existing_by_color = {mov.color: mov for mov in existing}
        submission = self.submission_id if self.submission_id else False
        confirmation = self.confirmation_id
        event_date = confirmation.delivery_date or fields.Date.today()
        for color, qty in quantities.items():
            if qty <= 0:
                continue
            prior = existing_by_color.get(color)
            if prior:
                result |= prior
                continue
            toner_brand = False
            brand_field = "toner_brand_%s_id" % color
            if submission and brand_field in submission._fields:
                toner_brand = getattr(submission, brand_field)
            movement = Movement.create_stock_movement(
                equipment=self.equipment_id,
                color=color,
                quantity=qty,
                movement_type="delivery",
                source="delivery",
                movement_date=event_date,
                external_key="delivery:%s:%s" % (self.id, color),
                submission=submission,
                delivery=self,
                toner_brand=toner_brand,
                notes=_(
                    "Recepción física confirmada %(confirmation)s; "
                    "cantidad realmente entregada: %(quantity)s."
                ) % {
                    "confirmation": confirmation.secuencia or confirmation.id,
                    "quantity": qty,
                },
                prevent_negative=True,
            )
            if movement.quantity != qty or movement.state != "posted":
                raise UserError(_(
                    "Movimiento de %(color)s incongruente con la entrega "
                    "confirmada. Revise el kardex antes de continuar."
                ) % {"color": self._COLOR_NAMES[color]})
            result |= movement

        # Este super evita volver a invocar nuestra propia lógica write().
        super(TonerDeliveryScheduleStockIntegration, self).write({
            "stock_last_sync_date": fields.Datetime.now(),
            "stock_sync_error": False,
        })
        _logger.info(
            "[TONER STOCK] Entrega=%s confirmación=%s cantidades=%s movements=%s",
            self.id, confirmation.id, quantities, result.ids,
        )
        # Sin mensajes ni notificaciones por esta actualización automática.
        # El cliente consultará el único enlace de seguimiento cuando
        # el controlador correspondiente quede implementado.
        return result

    def action_sync_client_toner_stock(self):
        """Reintento manual idempotente, sin inventar recepciones."""
        movements = self.env["toner.stock.movement"]
        for delivery in self:
            movements |= delivery._sync_client_toner_stock()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Stock de tóner"),
                "message": _("Sincronización comprobada: %s movimientos.") % len(movements),
                "type": "success",
                "sticky": False,
            },
        }

    def action_view_stock_movements(self):
        self.ensure_one()
        result = {
            "name": _("Movimientos de stock de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.stock.movement",
            "view_mode": "list,form",
            "domain": [("delivery_id", "=", self.id)],
            "context": {
                "default_equipment_id": self.equipment_id.id or False,
                "default_delivery_id": self.id,
            },
            "target": "current",
        }
        records = self.env["toner.stock.movement"].sudo().search([
            ("delivery_id", "=", self.id),
        ])
        if len(records) == 1:
            result.update({"view_mode": "form", "res_id": records.id, "domain": []})
        return result

    def get_client_toner_stock_summary(self):
        self.ensure_one()
        if not self.equipment_id:
            return dict.fromkeys(self._DELIVERY_COLOR_FIELDS, 0)
        return self.env["toner.stock.movement"].sudo().get_stock_summary(
            self.equipment_id
        )
