# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class TicketComponenteEvaluacion(models.Model):
    _name = 'ticket.componente.evaluacion'
    _description = 'Evaluación de Componentes por Ticket de Servicio'
    _order = 'ticket_id, componente_tipo_id, color_id, id'

    ticket_id = fields.Many2one(
        'ticket.alquiler',
        string='Ticket',
        required=True,
        ondelete='cascade',
        index=True
    )

    componente_tipo_id = fields.Many2one(
        'componente.tipo',
        string='Tipo de Componente',
        required=True,
        ondelete='restrict',
        index=True
    )

    color_id = fields.Many2one(
        'color.tipo',
        string='Color',
        ondelete='restrict'
    )

    estado_id = fields.Many2one(
        'componente.estado',
        string='Estado',
        required=False,
        ondelete='restrict',
        help="Estado del componente evaluado por el técnico en sitio."
    )

    observaciones = fields.Text(
        string='Observaciones'
    )

    _sql_constraints = [
        (
            'ticket_componente_color_unique',
            'unique(ticket_id, componente_tipo_id, color_id)',
            'Ya existe una evaluación de este componente y color para este ticket.'
        )
    ]

    @api.model
    def create(self, vals):
        _logger.info(
            "[ticket.componente.evaluacion] create() ticket_id=%s tipo=%s color=%s",
            vals.get('ticket_id'),
            vals.get('componente_tipo_id'),
            vals.get('color_id'),
        )
        record = super().create(vals)
        _logger.info(
            "[ticket.componente.evaluacion] creado id=%s ticket_id=%s",
            record.id,
            record.ticket_id.id if record.ticket_id else 'VACIO'
        )
        return record

    def write(self, vals):
        _logger.info(
            "[ticket.componente.evaluacion] write() id=%s vals=%s",
            self.ids,
            vals
        )
        return super().write(vals)