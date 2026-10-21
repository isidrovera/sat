
# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models

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
        index=True,
    )

    componente_tipo_id = fields.Many2one(
        'componente.tipo',
        string='Tipo de Componente',
        required=True,
        ondelete='restrict',
        index=True,
    )

    color_id = fields.Many2one(
        'color.tipo',
        string='Color',
        ondelete='restrict',
    )

    estado_id = fields.Many2one(
        'componente.estado',
        string='Estado',
        required=False,
        ondelete='restrict',
        help='Estado del componente evaluado por el técnico en sitio.',
    )

    observaciones = fields.Text(
        string='Observaciones',
    )

    _ticket_componente_color_unique = models.Constraint(
        'UNIQUE(ticket_id, componente_tipo_id, color_id)',
        'Ya existe una evaluación de este componente y color para este ticket.',
    )

    # ============================================================
    # CREATE - COMPATIBLE CON ODOO 19
    # ============================================================

    @api.model_create_multi
    def create(self, vals_list):
        """Crear una o varias evaluaciones de componentes."""

        _logger.info(
            '[COMPONENTE EVAL][CREATE][INICIO] cantidad=%s',
            len(vals_list),
        )

        for vals in vals_list:
            _logger.info(
                '[COMPONENTE EVAL][CREATE] '
                'ticket_id=%s tipo_id=%s color_id=%s estado_id=%s',
                vals.get('ticket_id'),
                vals.get('componente_tipo_id'),
                vals.get('color_id'),
                vals.get('estado_id'),
            )

        records = super().create(vals_list)

        for record in records:
            _logger.info(
                '[COMPONENTE EVAL][CREATE][OK] '
                'id=%s ticket=%s componente=%s color=%s',
                record.id,
                record.ticket_id.id,
                record.componente_tipo_id.name,
                record.color_id.name if record.color_id else 'SIN COLOR',
            )

        _logger.info(
            '[COMPONENTE EVAL][CREATE][FIN] creados=%s',
            len(records),
        )

        return records

    # ============================================================
    # WRITE
    # ============================================================

    def write(self, vals):
        _logger.info(
            '[COMPONENTE EVAL][WRITE][INICIO] '
            'ids=%s campos=%s',
            self.ids,
            list(vals.keys()),
        )

        result = super().write(vals)

        _logger.info(
            '[COMPONENTE EVAL][WRITE][OK] ids=%s',
            self.ids,
        )

        return result
