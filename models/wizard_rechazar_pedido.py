# -*- coding: utf-8 -*-
# ================================================================
# ARCHIVO: models/wizard_rechazar_pedido.py  (archivo nuevo)
# ================================================================

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class WizardRechazarPedido(models.TransientModel):
    _name = 'wizard.rechazar.pedido'
    _description = 'Wizard: Rechazar Pedido de Repuestos'

    pedido_id = fields.Many2one(
        'ticket.repuesto.pedido',
        string='Pedido',
        required=True,
        readonly=True
    )

    motivo = fields.Text(
        string='Motivo del rechazo',
        required=True,
        help="El técnico recibirá este motivo por correo."
    )

    def action_confirmar(self):
        self.ensure_one()
        if not self.motivo or not self.motivo.strip():
            raise UserError(_("Debe ingresar un motivo para rechazar el pedido."))

        _logger.info(
            "[wizard.rechazar.pedido] pedido=%s | motivo=%s",
            self.pedido_id.name, self.motivo[:50]
        )

        self.pedido_id.action_rechazar_gerencia(
            motivo=self.motivo.strip(),
            desde_token=False  # viene desde Odoo — usuario conocido
        )

        return {'type': 'ir.actions.act_window_close'}


