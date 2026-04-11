# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class TicketSubpartesWizard(models.TransientModel):
    _name = 'ticket.subpartes.wizard'
    _description = 'Wizard: Selección de Subpartes para Ticket de Servicio'

    ticket_id = fields.Many2one(
        'ticket.alquiler',
        string='Ticket',
        required=True,
        readonly=True
    )

    line_ids = fields.One2many(
        'ticket.subpartes.wizard.linea',
        'wizard_id',
        string='Subpartes'
    )

    componentes_info = fields.Html(
        string='Componentes pendientes',
        compute='_compute_componentes_info'
    )

    @api.depends('line_ids')
    def _compute_componentes_info(self):
        for record in self:
            if not record.line_ids:
                record.componentes_info = ""
                continue

            componentes = record.line_ids.mapped('componente_display')
            componentes_unicos = list(set(componentes))
            info = "<p><strong>Componentes y accesorios que requieren especificación de subpartes:</strong><br/>"
            info += "<br/>".join(f"• {comp}" for comp in componentes_unicos)
            info += "</p>"
            record.componentes_info = info

    def action_confirmar(self):
        self.ensure_one()

        seleccionadas = self.line_ids.filtered('selected')
        if not seleccionadas:
            raise UserError(_("Debe seleccionar al menos una subparte antes de confirmar."))

        # Agrupar por intervención — limpiar detalles solo una vez por intervención
        intervenciones_procesadas = set()

        for linea in seleccionadas:
            # Usar intervencion_id si está disponible, si no buscar/crear
            intervencion = linea.intervencion_id
            if not intervencion:
                intervencion = self.env['ticket.componente.intervencion'].search([
                    ('ticket_id', '=', self.ticket_id.id),
                    ('componente_code', '=', linea.componente_code),
                ], limit=1)
                if not intervencion:
                    intervencion = self.env['ticket.componente.intervencion'].create({
                        'ticket_id': self.ticket_id.id,
                        'componente_code': linea.componente_code,
                    })

            # Limpiar detalles solo la primera vez que procesamos esta intervención
            if intervencion.id not in intervenciones_procesadas:
                intervencion.detalle_ids.unlink()
                intervenciones_procesadas.add(intervencion.id)

            self.env['ticket.componente.intervencion.detalle'].create({
                'intervencion_id': intervencion.id,
                'subparte_id': linea.subparte_id.id,
                'cantidad': linea.cantidad,
                'observacion': linea.observacion or '',
            })

        _logger.info(
            "[ticket.subpartes.wizard] Subpartes confirmadas para ticket_id=%s — %s intervenciones procesadas",
            self.ticket_id.id,
            len(intervenciones_procesadas)
        )

        return {'type': 'ir.actions.act_window_close'}


class TicketSubpartesWizardLinea(models.TransientModel):
    _name = 'ticket.subpartes.wizard.linea'
    _description = 'Línea de Subpartes Wizard Ticket'

    wizard_id = fields.Many2one(
        'ticket.subpartes.wizard',
        required=True,
        ondelete='cascade'
    )

    # Código dinámico del componente o accesorio
    componente_code = fields.Char(
        string='Código componente',
        required=True,
        help="Código interno: t<TIPO_ID> o t<TIPO_ID>_<k|c|m|y> para componentes, a<TIPO_ID> para accesorios"
    )

    # Nombre legible calculado para mostrar en el wizard
    componente_display = fields.Char(
        string='Componente',
        compute='_compute_componente_display',
        store=True
    )

    # Referencia a la intervención — se usa en action_confirmar para saber dónde guardar
    intervencion_id = fields.Many2one(
        'ticket.componente.intervencion',
        string='Intervención',
        ondelete='cascade'
    )

    subparte_id = fields.Many2one(
        'componente.subparte',
        string='Subparte',
        required=True
    )

    selected = fields.Boolean(
        string='Seleccionar',
        default=False
    )

    cantidad = fields.Float(
        string='Cantidad',
        default=1.0
    )

    observacion = fields.Char(
        string='Observación'
    )

    @api.depends('componente_code')
    def _compute_componente_display(self):
        import re
        color_map = {'k': 'Black', 'c': 'Cyan', 'm': 'Magenta', 'y': 'Yellow'}

        for record in self:
            code = record.componente_code or ''

            # Componente: t<ID> o t<ID>_<color>
            m = re.match(r'^t(\d+)(?:_([kcmy]))?$', code)
            if m:
                tipo = self.env['componente.tipo'].browse(int(m.group(1)))
                nombre = tipo.name if tipo.exists() else f"Componente {m.group(1)}"
                if m.group(2):
                    nombre = f"{nombre} ({color_map.get(m.group(2), m.group(2).upper())})"
                record.componente_display = nombre
                continue

            # Accesorio: a<ID>
            m2 = re.match(r'^a(\d+)$', code)
            if m2:
                tipo = self.env['accesorio.tipo'].browse(int(m2.group(1)))
                record.componente_display = tipo.name if tipo.exists() else f"Accesorio {m2.group(1)}"
                continue

            record.componente_display = code