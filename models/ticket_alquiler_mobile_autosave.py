# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.exceptions import UserError


class TicketAlquilerMobileAutosave(models.Model):
    _inherit = "ticket.alquiler"

    def action_guardar_cambios_movil(self):
        """
        Botón visible para móvil.

        En formularios normales de Odoo, los campos editados se guardan
        cuando el usuario presiona guardar. Este botón sirve como acción clara
        para técnicos, especialmente cuando están trabajando desde celular.
        """
        self.ensure_one()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Cambios guardados"),
                "message": _("Los cambios del ticket fueron confirmados."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_enviar_informe_administracion(self):
        """
        Evita enviar el informe si el técnico no indicó retorno.
        """
        for ticket in self:
            if not ticket.retorno_id:
                raise UserError(_(
                    "Antes de enviar el informe a Administración, "
                    "debes indicar si el ticket requiere retorno."
                ))

        return super().action_enviar_informe_administracion()