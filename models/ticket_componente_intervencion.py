
# -*- coding: utf-8 -*-
import logging
import re

from odoo import models, fields, api

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

    # Código dinámico:
    # t<TIPO_ID> / t<TIPO_ID>_<k|c|m|y> para componentes
    # a<TIPO_ID> para accesorios
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

    _ticket_componente_code_unique = models.Constraint(
        'UNIQUE(ticket_id, componente_code)',
        'Ya existe una intervención para este componente en este ticket.',
    )

    @api.depends('componente_code')
    def _compute_componente_display(self):
        color_map = {
            'k': 'Black',
            'c': 'Cyan',
            'm': 'Magenta',
            'y': 'Yellow',
        }

        for record in self:
            code = record.componente_code or ''

            # Componente: t<ID> o t<ID>_<color>
            match = re.match(r'^t(\d+)(?:_([kcmy]))?$', code)

            if match:
                tipo = self.env['componente.tipo'].browse(
                    int(match.group(1))
                )

                nombre = (
                    tipo.name
                    if tipo.exists()
                    else f"Componente {match.group(1)}"
                )

                if match.group(2):
                    color = color_map.get(
                        match.group(2),
                        match.group(2).upper()
                    )
                    nombre = f"{nombre} ({color})"

                record.componente_display = nombre
                continue

            # Accesorio: a<ID>
            match = re.match(r'^a(\d+)$', code)

            if match:
                tipo = self.env['accesorio.tipo'].browse(
                    int(match.group(1))
                )

                record.componente_display = (
                    tipo.name
                    if tipo.exists()
                    else f"Accesorio {match.group(1)}"
                )
                continue

            record.componente_display = code

    @api.model_create_multi
    def create(self, vals_list):
        _logger.info(
            "[INTERVENCION][CREATE][INICIO] "
            "cantidad_registros=%s",
            len(vals_list)
        )

        for vals in vals_list:
            _logger.info(
                "[INTERVENCION][CREATE][VALORES] "
                "ticket_id=%s componente_code=%s",
                vals.get('ticket_id'),
                vals.get('componente_code')
            )

        records = super().create(vals_list)

        _logger.info(
            "[INTERVENCION][CREATE][OK] "
            "ids=%s cantidad=%s",
            records.ids,
            len(records)
        )

        return records


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

    _intervencion_subparte_unique = models.Constraint(
        'UNIQUE(intervencion_id, subparte_id)',
        'Esta subparte ya está registrada para esta intervención.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        _logger.info(
            "[INTERVENCION DETALLE][CREATE][INICIO] "
            "cantidad_registros=%s",
            len(vals_list)
        )

        for vals in vals_list:
            _logger.info(
                "[INTERVENCION DETALLE][CREATE][VALORES] "
                "intervencion_id=%s subparte_id=%s "
                "cantidad=%s observacion=%s",
                vals.get('intervencion_id'),
                vals.get('subparte_id'),
                vals.get('cantidad'),
                vals.get('observacion')
            )

        records = super().create(vals_list)

        _logger.info(
            "[INTERVENCION DETALLE][CREATE][OK] "
            "ids=%s cantidad=%s",
            records.ids,
            len(records)
        )

        return records
