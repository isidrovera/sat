# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class TonerDeliveryScheduleStockIntegration(models.Model):
    """
    Integra toner.delivery.schedule con el kardex histórico
    toner.stock.movement.

    PRINCIPIO
    =========

    El stock físico del cliente aumenta ÚNICAMENTE cuando el despacho
    realmente queda en estado:

        entregado

    No aumenta cuando:
        - gerencia aprueba;
        - ventas confirma stock;
        - se crea el despacho;
        - se prepara;
        - se envía.

    Esto evita registrar como stock del cliente material que todavía
    se encuentra en almacén, preparación o tránsito.

    La integración se realiza sobre write() y create() para cubrir
    cualquier flujo que cambie el estado del despacho, aunque el cambio
    provenga de:
        - action_deliver;
        - una confirmación;
        - una automatización;
        - una importación;
        - otro método del módulo.

    toner.stock.movement ya garantiza idempotencia mediante claves:

        delivery:<delivery_id>:<color>

    Por lo tanto, volver a sincronizar una entrega no duplica stock.
    """

    _inherit = "toner.delivery.schedule"

    # ============================================================
    # CAMPOS DE INTEGRACIÓN
    # ============================================================

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

    # ============================================================
    # COMPUTES
    # ============================================================

    def _compute_stock_movements_created(self):
        Movement = self.env[
            "toner.stock.movement"
        ].sudo()

        for delivery in self:
            if not delivery.id:
                delivery.stock_movements_created = False
                continue

            count = Movement.search_count(
                [
                    ("delivery_id", "=", delivery.id),
                    ("movement_type", "=", "delivery"),
                    ("state", "=", "posted"),
                ]
            )

            delivery.stock_movements_created = bool(count)

    def _compute_stock_movement_count(self):
        Movement = self.env[
            "toner.stock.movement"
        ].sudo()

        for delivery in self:
            if not delivery.id:
                delivery.stock_movement_count = 0
                continue

            delivery.stock_movement_count = Movement.search_count(
                [
                    ("delivery_id", "=", delivery.id),
                ]
            )

    # ============================================================
    # CREATE
    # ============================================================

    @api.model_create_multi
    def create(self, vals_list):
        """
        También cubre casos excepcionales donde una entrega sea creada
        directamente como entregada.
        """
        records = super().create(vals_list)

        for delivery in records:
            if delivery.state == "entregado":
                delivery._sync_client_toner_stock()

        return records

    # ============================================================
    # WRITE
    # ============================================================

    def write(self, vals):
        """
        Detecta transición real hacia 'entregado'.

        Guardamos el estado anterior antes de super().write() para no
        registrar dos veces por escrituras posteriores sobre una entrega
        que ya estaba entregada.
        """
        previous_states = {
            record.id: record.state
            for record in self
        }

        result = super().write(vals)

        if "state" in vals:
            for delivery in self:
                previous_state = previous_states.get(
                    delivery.id
                )

                if (
                    delivery.state == "entregado"
                    and previous_state != "entregado"
                ):
                    delivery._sync_client_toner_stock()

        return result

    # ============================================================
    # SINCRONIZACIÓN PRINCIPAL
    # ============================================================

    def _sync_client_toner_stock(self):
        """
        Crea movimientos +N para cada color realmente entregado.

        Es seguro ejecutar este método varias veces porque
        toner.stock.movement.create_delivery_movements() utiliza una
        external_key única por entrega/color.
        """
        self.ensure_one()

        if self.state != "entregado":
            raise UserError(
                _(
                    "El stock del cliente solo puede actualizarse "
                    "cuando la entrega está en estado Entregado."
                )
            )

        try:
            movements = self.env[
                "toner.stock.movement"
            ].sudo().create_delivery_movements(
                self
            )

            # Escribir campos técnicos evitando que nuestra lógica vuelva
            # a ejecutarse: no estamos cambiando state.
            super(
                TonerDeliveryScheduleStockIntegration,
                self,
            ).write(
                {
                    "stock_last_sync_date": fields.Datetime.now(),
                    "stock_sync_error": False,
                }
            )

            if movements:
                details = []

                for movement in movements:
                    color_label = dict(
                        movement.COLOR_SELECTION
                    ).get(
                        movement.color,
                        movement.color,
                    )

                    details.append(
                        "%s: +%s (stock %s → %s)"
                        % (
                            color_label,
                            movement.quantity,
                            movement.stock_before,
                            movement.stock_after,
                        )
                    )

                self.message_post(
                    body=_(
                        "<b>Stock de tóner del cliente actualizado</b>"
                        "<br/>%s"
                    )
                    % "<br/>".join(details),
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )

            else:
                self.message_post(
                    body=_(
                        "La entrega fue confirmada, pero no contiene "
                        "cantidades de tóner mayores a cero para "
                        "registrar en el stock del cliente."
                    ),
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )

            _logger.info(
                "[TONER DELIVERY STOCK] Entrega sincronizada "
                "delivery=%s equipment=%s movements=%s",
                self.id,
                self.equipment_id.id if self.equipment_id else False,
                movements.ids if movements else [],
            )

            return movements

        except Exception as error:
            _logger.exception(
                "[TONER DELIVERY STOCK] Error sincronizando "
                "delivery=%s",
                self.id,
            )

            super(
                TonerDeliveryScheduleStockIntegration,
                self,
            ).write(
                {
                    "stock_sync_error": str(error),
                }
            )

            # No ocultamos el error porque el stock es parte crítica
            # de la confirmación de entrega.
            raise

    # ============================================================
    # ACCIÓN MANUAL DE REINTENTO
    # ============================================================

    def action_sync_client_toner_stock(self):
        """
        Permite sincronizar manualmente:

        - entregas históricas;
        - entregas que quedaron con error;
        - pruebas de implementación.

        La idempotencia impide duplicar movimientos ya existentes.
        """
        total_movements = self.env[
            "toner.stock.movement"
        ]

        for delivery in self:
            if delivery.state != "entregado":
                raise UserError(
                    _(
                        "La entrega %s todavía no está entregada."
                    )
                    % delivery.display_name
                )

            movements = delivery._sync_client_toner_stock()
            total_movements |= movements

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Stock de tóner"),
                "message": _(
                    "Sincronización completada. "
                    "%s movimiento(s) encontrados/registrados."
                )
                % len(total_movements),
                "type": "success",
                "sticky": False,
            },
        }

    # ============================================================
    # VER MOVIMIENTOS
    # ============================================================

    def action_view_stock_movements(self):
        self.ensure_one()

        action = {
            "name": _("Movimientos de stock de tóner"),
            "type": "ir.actions.act_window",
            "res_model": "toner.stock.movement",
            "view_mode": "list,form",
            "domain": [
                ("delivery_id", "=", self.id),
            ],
            "context": {
                "default_equipment_id": (
                    self.equipment_id.id
                    if self.equipment_id
                    else False
                ),
                "default_delivery_id": self.id,
            },
            "target": "current",
        }

        movements = self.env[
            "toner.stock.movement"
        ].sudo().search(
            [
                ("delivery_id", "=", self.id),
            ]
        )

        if len(movements) == 1:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": movements.id,
                    "domain": [],
                }
            )

        return action

    # ============================================================
    # UTILIDAD: RESUMEN DEL STOCK DESPUÉS DE ENTREGA
    # ============================================================

    def get_client_toner_stock_summary(self):
        """
        Devuelve el saldo actual K/C/M/Y del equipo de esta entrega.

        Útil para vistas, informes o mensajes posteriores.
        """
        self.ensure_one()

        if not self.equipment_id:
            return {
                "black": 0,
                "cyan": 0,
                "magenta": 0,
                "yellow": 0,
            }

        return self.env[
            "toner.stock.movement"
        ].sudo().get_stock_summary(
            self.equipment_id
        )
