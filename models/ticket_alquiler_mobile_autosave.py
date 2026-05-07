# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.exceptions import UserError


class TicketAlquilerMobileAutosave(models.Model):
    _inherit = "ticket.alquiler"

    def action_guardar_cambios_movil(self):
        """
        Botón visible para técnicos.

        Nota:
        En Odoo, al presionar un botón type='object', el formulario intenta
        guardar primero los cambios del formulario actual antes de ejecutar
        el método. Este botón sirve como confirmación clara para móvil.
        """
        self.ensure_one()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Cambios guardados"),
                "message": _("Los cambios del ticket fueron guardados correctamente."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_guardar_y_volver_movil(self):
        """
        Botón propio para volver.

        No usa la flecha nativa de Odoo. Guarda y regresa a la lista/kanban
        de tickets para evitar que el técnico pierda cambios.
        """
        self.ensure_one()

        return {
            "type": "ir.actions.act_window",
            "name": _("Tickets"),
            "res_model": "ticket.alquiler",
            "view_mode": "list,kanban,form",
            "target": "current",
            "domain": [],
            "context": dict(self.env.context),
        }

    def action_enviar_informe_administracion(self):
        """
        Evita enviar el informe si no se indicó si requiere retorno.
        """
        for ticket in self:
            if not ticket.retorno_id:
                raise UserError(_(
                    "Antes de enviar el informe a Administración, "
                    "debes indicar si el ticket requiere retorno."
                ))

        return super().action_enviar_informe_administracion()