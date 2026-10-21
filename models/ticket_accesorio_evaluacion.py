# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

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
        index=True,
    )

    tipo_id = fields.Many2one(
        'accesorio.tipo',
        string='Tipo de Accesorio',
        required=True,
        ondelete='restrict',
        index=True,
    )

    estado_id = fields.Many2one(
        'accesorio.estado',
        string='Estado',
        required=False,
        ondelete='restrict',
        help='Estado del accesorio evaluado por el técnico en sitio.',
    )

    observaciones = fields.Text(string='Observaciones')

    _ticket_accesorio_unique = models.Constraint(
        'UNIQUE(ticket_id, tipo_id)',
        'Ya existe una evaluación de este accesorio para este ticket.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Crear una o varias evaluaciones, compatible con Odoo 19."""
        _logger.info(
            '[ACCESORIO EVAL][CREATE][INICIO] cantidad=%s',
            len(vals_list),
        )

        for vals in vals_list:
            _logger.info(
                '[ACCESORIO EVAL][CREATE] ticket_id=%s tipo_id=%s estado_id=%s',
                vals.get('ticket_id'),
                vals.get('tipo_id'),
                vals.get('estado_id'),
            )

        records = super().create(vals_list)

        for record in records:
            _logger.info(
                '[ACCESORIO EVAL][CREATE][OK] id=%s ticket=%s accesorio=%s estado=%s',
                record.id,
                record.ticket_id.id if record.ticket_id else False,
                record.tipo_id.name if record.tipo_id else 'SIN TIPO',
                record.estado_id.name if record.estado_id else 'SIN ESTADO',
            )

        _logger.info(
            '[ACCESORIO EVAL][CREATE][FIN] creados=%s ids=%s',
            len(records),
            records.ids,
        )
        return records

    def write(self, vals):
        _logger.info(
            '[ACCESORIO EVAL][WRITE][INICIO] ids=%s campos=%s',
            self.ids,
            list(vals.keys()),
        )
        result = super().write(vals)
        _logger.info('[ACCESORIO EVAL][WRITE][OK] ids=%s', self.ids)
        return result
