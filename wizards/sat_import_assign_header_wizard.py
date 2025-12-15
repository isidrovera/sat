# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SatImportAssignHeaderWizard(models.TransientModel):
    _name = "sat.import.assign.header.wizard"
    _description = "Wizard para asignar Importación/Invoice/Proveedor a líneas staging"

    importacion = fields.Char(string="Importación", required=True)
    invoice = fields.Char(string="Invoice", required=True)
    proveedor_id = fields.Many2one("res.partner", string="Proveedor", required=True)

    def action_apply(self):
        self.ensure_one()
        active_ids = self.env.context.get("active_ids", [])
        if not active_ids:
            raise UserError(_("No hay registros seleccionados."))

        lines = self.env["sat.import.line"].browse(active_ids).exists()
        if not lines:
            raise UserError(_("No se encontraron registros válidos."))

        # Aplica a todos
        vals = {
            "importacion": self.importacion,
            "invoice": self.invoice,
            "proveedor_id": self.proveedor_id.id,
            "error_msg": False,
        }
        lines.write(vals)

        # Pasa a ready si ya quedó completo (sin tocar done/cancel)
        for l in lines:
            if l.state in ("draft", "error") and l.importacion and l.invoice and l.proveedor_id:
                l.state = "ready"

        return {"type": "ir.actions.act_window_close"}
