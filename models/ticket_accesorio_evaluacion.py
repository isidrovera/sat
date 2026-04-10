# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class TicketAccesorioEvaluacion(models.Model):
    _name = 'ticket.accesorio.evaluacion'
    _description = 'Evaluación de Accesorios por Ticket de Servicio'
    _order = 'ticket_id, tipo_id, id'

    ticket_id = fields.Many2one(
        'ticket.alquiler',
        string='Ticket',
        required=True,
        ondelete='cascade',
        index=True
    )

    tipo_id = fields.Many2one(
        'accesorio.tipo',
        string='Tipo de Accesorio',
        required=True,
        ondelete='restrict',
        index=True
    )

    estado_id = fields.Many2one(
        'accesorio.estado',
        string='Estado',
        required=False,
        ondelete='restrict',
        help="Estado del accesorio evaluado por el técnico en sitio."
    )

    observaciones = fields.Text(
        string='Observaciones'
    )

    _sql_constraints = [
        (
            'ticket_accesorio_unique',
            'unique(ticket_id, tipo_id)',
            'Ya existe una evaluación de este accesorio para este ticket.'
        )
    ]

    @api.model
    def create(self, vals):
        _logger.info(
            "[ticket.accesorio.evaluacion] create() ticket_id=%s tipo=%s",
            vals.get('ticket_id'),
            vals.get('tipo_id'),
        )
        record = super().create(vals)
        _logger.info(
            "[ticket.accesorio.evaluacion] creado id=%s ticket_id=%s",
            record.id,
            record.ticket_id.id if record.ticket_id else 'VACIO'
        )
        return record

    def write(self, vals):
        _logger.info(
            "[ticket.accesorio.evaluacion] write() id=%s vals=%s",
            self.ids,
            vals
        )
        return super().write(vals)