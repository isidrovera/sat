# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging
import re

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
        help="Color del componente (K/C/M/Y). Vacío = componente B/N o sin color (fusor, ITB, etc.)"
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
        help=(
            "Valor del contómetro guardado al momento del cambio.\n"
            "- tipo 'bn'    → contómetro K\n"
            "- tipo 'color' → contómetro Color\n"
            "- tipo 'total' → K + Color (para fusor, ITB, faja, etc.)"
        )
    )

    tipo_contometro = fields.Selection([
        ('bn',    'B/N (Contómetro K)'),
        ('color', 'Color (Contómetro C)'),
        ('total', 'Total (K + Color)'),
    ], string='Tipo de Contómetro',
        default='bn',
        readonly=True,
        help=(
            "Indica qué contómetro se usó para este registro:\n"
            "- B/N    → repuesto de máquina monocromática o componente B/N\n"
            "- Color  → componente de color (IU, drum, etc.)\n"
            "- Total  → repuesto sin color en máquina a color (fusor, ITB, faja)"
        )
    )

    tecnico_id = fields.Many2one(
        'res.users',
        string='Técnico',
        ondelete='restrict',
        readonly=True
    )

    # ============================================================
    # DURABILIDAD CALCULADA
    # store=False → siempre se recalcula en tiempo real desde BD.
    # Esto evita el bug de store=True que guarda 0 al crear el primer
    # registro cuando aún no hay anterior en la misma transacción.
    # Contra: no se puede usar en domain/group_by de vistas.
    # ============================================================

    cambio_anterior_id = fields.Many2one(
        'ticket.repuesto.historial',
        string='Cambio anterior',
        compute='_compute_durabilidad',
        store=False
    )

    fecha_cambio_anterior = fields.Datetime(
        string='Fecha cambio anterior',
        compute='_compute_durabilidad',
        store=False
    )

    contometro_cambio_anterior = fields.Char(
        string='Contómetro en cambio anterior',
        compute='_compute_durabilidad',
        store=False
    )

    meses_duracion = fields.Integer(
        string='Duración (meses)',
        compute='_compute_durabilidad',
        store=False,
        help="Meses transcurridos desde el cambio anterior de este repuesto en este equipo"
    )

    copias_duracion = fields.Integer(
        string='Copias de duración',
        compute='_compute_durabilidad',
        store=False,
        help=(
            "Diferencia de contómetro entre este cambio y el anterior.\n"
            "Compara el mismo tipo de contómetro (bn vs bn, color vs color, total vs total)."
        )
    )

    # ============================================================
    # COMPUTES
    # ============================================================

    @api.depends('equipo_id', 'subparte_id', 'color_id', 'fecha_cambio',
                 'contometro_cambio', 'tipo_contometro')
    def _compute_durabilidad(self):
        """
        Calcula duración en meses y copias comparando con el cambio anterior
        del mismo repuesto en el mismo equipo y mismo color.

        Reglas de comparación de contómetro:
        - color_id presente  → tipo 'color', compara solo con registros del mismo color
        - color_id ausente   → tipo 'bn' o 'total', compara solo con registros sin color
        - La diferencia de copias se calcula entre contómetros del mismo tipo,
          ya que un registro anterior 'total' y uno nuevo 'total' son comparables.

        store=False garantiza que siempre se lee desde BD sin caché ORM.
        """

        def _to_int(val):
            """Convierte string de contómetro a entero ignorando separadores."""
            if not val:
                return 0
            digits = re.sub(r'[^\d]', '', str(val))
            return int(digits) if digits else 0

        _logger.debug(
            "[_compute_durabilidad] Iniciando para %s registros: ids=%s",
            len(self), self.ids
        )

        for record in self:
            if not record.equipo_id or not record.subparte_id or not record.fecha_cambio:
                _logger.debug(
                    "[_compute_durabilidad] id=%s — sin equipo/subparte/fecha, saltando",
                    record.id
                )
                record.cambio_anterior_id = False
                record.fecha_cambio_anterior = False
                record.contometro_cambio_anterior = False
                record.meses_duracion = 0
                record.copias_duracion = 0
                continue

            # Dominio base: mismo equipo, misma subparte, fecha anterior
            domain = [
                ('equipo_id', '=', record.equipo_id.id),
                ('subparte_id', '=', record.subparte_id.id),
                ('fecha_cambio', '<', record.fecha_cambio),
            ]

            # Excluir el propio registro (solo aplica cuando ya tiene id persistido)
            if record.id:
                domain.append(('id', '!=', record.id))

            # Filtrar por color: yellow vs yellow, B/N vs B/N
            if record.color_id:
                domain.append(('color_id', '=', record.color_id.id))
            else:
                domain.append(('color_id', '=', False))

            _logger.debug(
                "[_compute_durabilidad] id=%s | equipo=%s | subparte=%s | color=%s | domain=%s",
                record.id,
                record.equipo_id.serie,
                record.subparte_id.name,
                record.color_id.name if record.color_id else 'B/N',
                domain
            )

            # sudo() + search directo a BD para evitar caché ORM
            anterior = self.env['ticket.repuesto.historial'].sudo().search(
                domain, order='fecha_cambio desc', limit=1
            )

            if anterior:
                record.cambio_anterior_id = anterior.id
                record.fecha_cambio_anterior = anterior.fecha_cambio
                record.contometro_cambio_anterior = anterior.contometro_cambio

                # Duración en meses
                diff = relativedelta(record.fecha_cambio, anterior.fecha_cambio)
                record.meses_duracion = diff.months + (diff.years * 12)

                # Copias: diferencia directa entre contómetros del mismo tipo
                # (ambos bn, ambos color, o ambos total — son comparables)
                contometro_actual = _to_int(record.contometro_cambio)
                contometro_anterior = _to_int(anterior.contometro_cambio)

                if contometro_actual > contometro_anterior:
                    record.copias_duracion = contometro_actual - contometro_anterior
                else:
                    # Si el actual es menor o igual, algo está mal en los datos
                    # (ej: contómetro reseteado o error de carga). Se deja en 0.
                    record.copias_duracion = 0
                    _logger.warning(
                        "[_compute_durabilidad] id=%s — contómetro actual (%s) <= anterior (%s). "
                        "Posible reset o error de datos. copias_duracion=0",
                        record.id, contometro_actual, contometro_anterior
                    )

                _logger.info(
                    "[_compute_durabilidad] id=%s | subparte=%s | color=%s | tipo=%s | "
                    "anterior_id=%s | cont_anterior=%s | cont_actual=%s | "
                    "copias=%s | meses=%s",
                    record.id,
                    record.subparte_id.name,
                    record.color_id.name if record.color_id else 'B/N',
                    record.tipo_contometro,
                    anterior.id,
                    contometro_anterior,
                    contometro_actual,
                    record.copias_duracion,
                    record.meses_duracion,
                )
            else:
                # Primer cambio registrado para esta subparte+equipo+color
                record.cambio_anterior_id = False
                record.fecha_cambio_anterior = False
                record.contometro_cambio_anterior = False
                record.meses_duracion = 0
                record.copias_duracion = 0

                _logger.info(
                    "[_compute_durabilidad] id=%s | subparte=%s | color=%s | tipo=%s — "
                    "primer cambio registrado, sin anterior",
                    record.id,
                    record.subparte_id.name,
                    record.color_id.name if record.color_id else 'B/N',
                    record.tipo_contometro,
                )

    # ============================================================
    # CRUD
    # ============================================================

    @api.model
    def create(self, vals):
        _logger.info(
            "[ticket.repuesto.historial] create() — "
            "equipo_id=%s | subparte_id=%s | color_id=%s | "
            "contometro=%s | tipo=%s | fecha=%s",
            vals.get('equipo_id'),
            vals.get('subparte_id'),
            vals.get('color_id'),
            vals.get('contometro_cambio'),
            vals.get('tipo_contometro'),
            vals.get('fecha_cambio'),
        )

        record = super().create(vals)

        # Con store=False los campos de durabilidad se calculan en tiempo real,
        # pero logueamos los valores para verificar que el compute funciona
        # correctamente justo después del create.
        _logger.info(
            "[ticket.repuesto.historial] creado — "
            "id=%s | equipo=%s | subparte=%s | color=%s | tipo=%s | "
            "contometro=%s | anterior_id=%s | cont_anterior=%s | "
            "copias=%s | meses=%s",
            record.id,
            record.equipo_id.serie if record.equipo_id else 'NA',
            record.subparte_id.name if record.subparte_id else 'NA',
            record.color_id.name if record.color_id else 'B/N',
            record.tipo_contometro,
            record.contometro_cambio,
            record.cambio_anterior_id.id if record.cambio_anterior_id else 'ninguno',
            record.contometro_cambio_anterior or 'ninguno',
            record.copias_duracion,
            record.meses_duracion,
        )

        return record