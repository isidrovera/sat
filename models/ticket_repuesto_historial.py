# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class TicketRepuestoHistorial(models.Model):
    _name = 'ticket.repuesto.historial'
    _description = 'Historial de Durabilidad de Repuestos por Equipo'
    _order = 'fecha_cambio desc, id desc'

    # ============================================================
    # ORIGEN
    # ============================================================

    pedido_id = fields.Many2one(
        'ticket.repuesto.pedido',
        string='Pedido de origen',
        ondelete='restrict',
        readonly=True,
        index=True
    )

    ticket_id = fields.Many2one(
        'ticket.alquiler',
        string='Ticket de origen',
        ondelete='restrict',
        readonly=True,
        index=True
    )

    # ============================================================
    # EQUIPO
    # ============================================================

    equipo_id = fields.Many2one(
        'alquiler',
        string='Equipo',
        required=True,
        ondelete='restrict',
        index=True
    )

    modelo_nombre = fields.Char(
        related='equipo_id.name.name',
        string='Modelo',
        store=True,
        readonly=True
    )

    serie = fields.Char(
        related='equipo_id.serie',
        string='Serie',
        store=True,
        readonly=True
    )

    cliente_id = fields.Many2one(
        related='equipo_id.cliente_id',
        string='Cliente',
        store=True,
        readonly=True
    )

    # ============================================================
    # REPUESTO
    # ============================================================

    subparte_id = fields.Many2one(
        'componente.subparte',
        string='Subparte / Repuesto',
        required=True,
        ondelete='restrict',
        index=True
    )

    color_id = fields.Many2one(
        'color.tipo',
        string='Color',
        ondelete='restrict',
        help="Color del componente al que pertenece este repuesto (K/C/M/Y)"
    )

    cantidad = fields.Float(
        string='Cantidad cambiada',
        default=1.0,
        readonly=True
    )

    # ============================================================
    # DATOS DEL CAMBIO
    # ============================================================

    fecha_cambio = fields.Datetime(
        string='Fecha de cambio',
        required=True,
        readonly=True,
        index=True
    )

    contometro_cambio = fields.Char(
        string='Contómetro al momento del cambio',
        readonly=True,
        help="Valor del contómetro K cuando se aprobó el pedido"
    )

    tecnico_id = fields.Many2one(
        'res.users',
        string='Técnico',
        ondelete='restrict',
        readonly=True
    )

    # ============================================================
    # DURABILIDAD CALCULADA
    # ============================================================

    cambio_anterior_id = fields.Many2one(
        'ticket.repuesto.historial',
        string='Cambio anterior',
        compute='_compute_durabilidad',
        store=True
    )

    fecha_cambio_anterior = fields.Datetime(
        string='Fecha cambio anterior',
        compute='_compute_durabilidad',
        store=True
    )

    contometro_cambio_anterior = fields.Char(
        string='Contómetro en cambio anterior',
        compute='_compute_durabilidad',
        store=True
    )

    meses_duracion = fields.Integer(
        string='Duración (meses)',
        compute='_compute_durabilidad',
        store=True,
        help="Meses transcurridos desde el cambio anterior de este repuesto en este equipo"
    )

    copias_duracion = fields.Integer(
        string='Copias de duración',
        compute='_compute_durabilidad',
        store=True,
        help="Diferencia de contómetro entre este cambio y el anterior"
    )

    # ============================================================
    # COMPUTES
    # ============================================================

    @api.depends('equipo_id', 'subparte_id', 'color_id', 'fecha_cambio', 'contometro_cambio')
    def _compute_durabilidad(self):
        from datetime import datetime
        from dateutil.relativedelta import relativedelta
        import re

        for record in self:
            if not record.equipo_id or not record.subparte_id or not record.fecha_cambio:
                record.cambio_anterior_id = False
                record.fecha_cambio_anterior = False
                record.contometro_cambio_anterior = False
                record.meses_duracion = 0
                record.copias_duracion = 0
                continue

            # Buscar el cambio anterior de esta misma subparte en este mismo equipo
            domain = [
                ('equipo_id', '=', record.equipo_id.id),
                ('subparte_id', '=', record.subparte_id.id),
                ('fecha_cambio', '<', record.fecha_cambio),
                ('id', '!=', record.id),
            ]
            if record.color_id:
                domain.append(('color_id', '=', record.color_id.id))
            else:
                domain.append(('color_id', '=', False))

            anterior = self.search(domain, order='fecha_cambio desc', limit=1)

            if anterior:
                record.cambio_anterior_id = anterior.id
                record.fecha_cambio_anterior = anterior.fecha_cambio
                record.contometro_cambio_anterior = anterior.contometro_cambio

                # Calcular meses de duración
                diff = relativedelta(record.fecha_cambio, anterior.fecha_cambio)
                record.meses_duracion = diff.months + (diff.years * 12)

                # Calcular copias de duración
                def _to_int(val):
                    if not val:
                        return 0
                    digits = re.sub(r'[^\d]', '', str(val))
                    return int(digits) if digits else 0

                contometro_actual = _to_int(record.contometro_cambio)
                contometro_anterior = _to_int(anterior.contometro_cambio)

                if contometro_actual > contometro_anterior:
                    record.copias_duracion = contometro_actual - contometro_anterior
                else:
                    record.copias_duracion = 0
            else:
                record.cambio_anterior_id = False
                record.fecha_cambio_anterior = False
                record.contometro_cambio_anterior = False
                record.meses_duracion = 0
                record.copias_duracion = 0

    # ============================================================
    # CRUD
    # ============================================================

    @api.model
    def create(self, vals):
        _logger.info(
            "[ticket.repuesto.historial] create() equipo_id=%s subparte_id=%s "
            "color_id=%s contometro=%s fecha=%s",
            vals.get('equipo_id'),
            vals.get('subparte_id'),
            vals.get('color_id'),
            vals.get('contometro_cambio'),
            vals.get('fecha_cambio'),
        )
        record = super().create(vals)
        _logger.info(
            "[ticket.repuesto.historial] creado id=%s equipo=%s subparte=%s meses=%s copias=%s",
            record.id,
            record.equipo_id.serie if record.equipo_id else 'NA',
            record.subparte_id.name if record.subparte_id else 'NA',
            record.meses_duracion,
            record.copias_duracion,
        )
        return record