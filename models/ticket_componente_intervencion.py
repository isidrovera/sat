# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class TicketComponenteIntervencion(models.Model):
    _name = 'ticket.componente.intervencion'
    _description = 'Intervención de Componente o Accesorio en Ticket'
    _order = 'ticket_id, id'

    ticket_id = fields.Many2one(
        'ticket.alquiler',
        string='Ticket',
        required=True,
        ondelete='cascade',
        index=True
    )

    # Código dinámico: t<TIPO_ID> / t<TIPO_ID>_<k|c|m|y> para componentes
    #                  a<TIPO_ID> para accesorios
    componente_code = fields.Char(
        string='Código de Componente',
        required=True,
        index=True,
        help="Formato: t<ID> o t<ID>_<k|c|m|y> para componentes, a<ID> para accesorios"
    )

    componente_display = fields.Char(
        string='Componente',
        compute='_compute_componente_display',
        store=True
    )

    detalle_ids = fields.One2many(
        'ticket.componente.intervencion.detalle',
        'intervencion_id',
        string='Subpartes'
    )

    _sql_constraints = [
        (
            'ticket_componente_code_unique',
            'unique(ticket_id, componente_code)',
            'Ya existe una intervención para este componente en este ticket.'
        )
    ]

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

    @api.model
    def create(self, vals):
        _logger.info(
            "[ticket.componente.intervencion] create() ticket_id=%s code=%s",
            vals.get('ticket_id'),
            vals.get('componente_code'),
        )
        return super().create(vals)


class TicketComponenteIntervencionDetalle(models.Model):
    _name = 'ticket.componente.intervencion.detalle'
    _description = 'Detalle de Subparte Intervenida en Ticket'
    _order = 'intervencion_id, id'

    intervencion_id = fields.Many2one(
        'ticket.componente.intervencion',
        string='Intervención',
        required=True,
        ondelete='cascade',
        index=True
    )

    ticket_id = fields.Many2one(
        related='intervencion_id.ticket_id',
        string='Ticket',
        store=True,
        readonly=True
    )

    subparte_id = fields.Many2one(
        'componente.subparte',
        string='Subparte',
        required=True,
        ondelete='restrict'
    )

    cantidad = fields.Float(
        string='Cantidad',
        default=1.0
    )

    observacion = fields.Char(
        string='Observación'
    )

    _sql_constraints = [
        (
            'intervencion_subparte_unique',
            'unique(intervencion_id, subparte_id)',
            'Esta subparte ya está registrada para esta intervención.'
        )
    ]

    @api.model
    def create(self, vals):
        _logger.info(
            "[ticket.componente.intervencion.detalle] create() intervencion_id=%s subparte_id=%s cantidad=%s",
            vals.get('intervencion_id'),
            vals.get('subparte_id'),
            vals.get('cantidad'),
        )
        return super().create(vals)