# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class TicketRepuestoPedido(models.Model):
    _name = 'ticket.repuesto.pedido'
    _description = 'Pedido de Repuestos generado desde Ticket de Servicio'
    _order = 'fecha desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Pedido N°',
        default=lambda self: _('New'),
        copy=False,
        readonly=True,
        required=True,
        tracking=True
    )

    # ============================================================
    # RELACIÓN CON TICKET
    # ============================================================

    ticket_id = fields.Many2one(
        'ticket.alquiler',
        string='Ticket',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True
    )

    # ============================================================
    # DATOS DEL CONTEXTO (relacionados desde ticket)
    # ============================================================

    cliente_id = fields.Many2one(
        related='ticket_id.partner_id',
        string='Cliente',
        store=True,
        readonly=True
    )

    equipo_id = fields.Many2one(
        related='ticket_id.product_alquiler',
        string='Equipo',
        store=True,
        readonly=True
    )

    modelo_nombre = fields.Char(
        related='ticket_id.modelo_id_r',
        string='Modelo',
        store=True,
        readonly=True
    )

    serie = fields.Char(
        related='ticket_id.serie_id_r',
        string='Serie',
        store=True,
        readonly=True
    )

    tecnico_id = fields.Many2one(
        related='ticket_id.responsable',
        string='Técnico',
        store=True,
        readonly=True
    )

    contometro_actual = fields.Char(
        related='ticket_id.contometrok_id',
        string='Contómetro actual',
        store=True,
        readonly=True
    )

    # ============================================================
    # ESTADO Y FECHAS
    # ============================================================

    estado = fields.Selection([
        ('pendiente', 'Pendiente de Aprobación'),
        ('aprobado', 'Aprobado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='pendiente', required=True, tracking=True)

    fecha = fields.Datetime(
        string='Fecha de creación',
        default=fields.Datetime.now,
        readonly=True
    )

    fecha_aprobacion = fields.Datetime(
        string='Fecha de aprobación',
        readonly=True,
        tracking=True
    )

    aprobado_por = fields.Many2one(
        'res.users',
        string='Aprobado por',
        readonly=True,
        tracking=True
    )

    observaciones = fields.Text(
        string='Observaciones',
        tracking=True
    )

    # ============================================================
    # LÍNEAS
    # ============================================================

    linea_ids = fields.One2many(
        'ticket.repuesto.pedido.linea',
        'pedido_id',
        string='Repuestos solicitados'
    )

    total_lineas = fields.Integer(
        string='Total de líneas',
        compute='_compute_total_lineas',
        store=True
    )

    # ============================================================
    # COMPUTES
    # ============================================================

    @api.depends('linea_ids')
    def _compute_total_lineas(self):
        for record in self:
            record.total_lineas = len(record.linea_ids)

    # ============================================================
    # CRUD
    # ============================================================

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                'ticket.repuesto.pedido'
            ) or '/'
        _logger.info(
            "[ticket.repuesto.pedido] create() ticket_id=%s name=%s",
            vals.get('ticket_id'),
            vals.get('name'),
        )
        return super().create(vals)

    # ============================================================
    # ACCIONES
    # ============================================================

    def action_aprobar(self):
        self.ensure_one()
        if self.estado != 'pendiente':
            raise UserError(_("Solo se pueden aprobar pedidos en estado 'Pendiente de Aprobación'."))

        if not self.linea_ids:
            raise UserError(_("No se puede aprobar un pedido sin líneas de repuestos."))

        self.write({
            'estado': 'aprobado',
            'fecha_aprobacion': fields.Datetime.now(),
            'aprobado_por': self.env.user.id,
        })

        # Registrar en historial de durabilidad
        self._registrar_historial()

        self.message_post(
            body=_(
                "✅ <b>Pedido aprobado</b> por %s<br/>"
                "Fecha: %s<br/>"
                "Repuestos aprobados: %s"
            ) % (
                self.env.user.name,
                fields.Datetime.now(),
                len(self.linea_ids)
            )
        )

        _logger.info(
            "[ticket.repuesto.pedido] aprobado id=%s por user=%s",
            self.id,
            self.env.user.name
        )

    def action_cancelar(self):
        self.ensure_one()
        if self.estado == 'aprobado':
            raise UserError(_("No se puede cancelar un pedido ya aprobado."))

        self.write({'estado': 'cancelado'})

        self.message_post(
            body=_("❌ <b>Pedido cancelado</b> por %s") % self.env.user.name
        )

        _logger.info(
            "[ticket.repuesto.pedido] cancelado id=%s por user=%s",
            self.id,
            self.env.user.name
        )

    def action_volver_pendiente(self):
        """Permite devolver a pendiente un pedido cancelado para corregirlo."""
        self.ensure_one()
        if self.estado != 'cancelado':
            raise UserError(_("Solo se puede reactivar un pedido cancelado."))

        self.write({'estado': 'pendiente'})

        self.message_post(
            body=_("🔄 <b>Pedido reactivado</b> a pendiente por %s") % self.env.user.name
        )

    def _registrar_historial(self):
        """Crea registros en ticket.repuesto.historial al aprobar el pedido."""
        self.ensure_one()
        Historial = self.env['ticket.repuesto.historial']

        for linea in self.linea_ids:
            Historial.create({
                'pedido_id': self.id,
                'ticket_id': self.ticket_id.id,
                'equipo_id': self.equipo_id.id if self.equipo_id else False,
                'subparte_id': linea.subparte_id.id,
                'color_id': linea.color_id.id if linea.color_id else False,
                'cantidad': linea.cantidad,
                'contometro_cambio': self.contometro_actual or '0',
                'tecnico_id': self.tecnico_id.id if self.tecnico_id else False,
                'fecha_cambio': fields.Datetime.now(),
            })

        _logger.info(
            "[ticket.repuesto.pedido] historial registrado — pedido=%s lineas=%s",
            self.id,
            len(self.linea_ids)
        )


class TicketRepuestoPedidoLinea(models.Model):
    _name = 'ticket.repuesto.pedido.linea'
    _description = 'Línea de Pedido de Repuestos de Ticket'
    _order = 'pedido_id, id'

    pedido_id = fields.Many2one(
        'ticket.repuesto.pedido',
        string='Pedido',
        required=True,
        ondelete='cascade',
        index=True
    )

    # ============================================================
    # COMPONENTE AL QUE PERTENECE ESTA SUBPARTE
    # ============================================================

    componente_code = fields.Char(
        string='Código de Componente',
        help="Referencia al componente o accesorio que requiere este repuesto"
    )

    componente_display = fields.Char(
        string='Componente',
        compute='_compute_componente_display',
        store=True
    )

    color_id = fields.Many2one(
        'color.tipo',
        string='Color',
        ondelete='restrict'
    )

    # ============================================================
    # SUBPARTE
    # ============================================================

    subparte_id = fields.Many2one(
        'componente.subparte',
        string='Subparte / Repuesto',
        required=True,
        ondelete='restrict'
    )

    cantidad = fields.Float(
        string='Cantidad',
        default=1.0,
        required=True
    )

    observacion = fields.Char(
        string='Observación'
    )

    # ============================================================
    # HISTORIAL: último cambio de esta subparte en este equipo
    # ============================================================

    ultimo_cambio_fecha = fields.Datetime(
        string='Último cambio',
        compute='_compute_ultimo_cambio',
        store=False
    )

    ultimo_cambio_contometro = fields.Char(
        string='Contómetro en último cambio',
        compute='_compute_ultimo_cambio',
        store=False
    )

    meses_desde_ultimo_cambio = fields.Integer(
        string='Meses desde último cambio',
        compute='_compute_ultimo_cambio',
        store=False
    )

    # ============================================================
    # COMPUTES
    # ============================================================

    @api.depends('componente_code')
    def _compute_componente_display(self):
        import re
        color_map = {'k': 'Black', 'c': 'Cyan', 'm': 'Magenta', 'y': 'Yellow'}

        for record in self:
            code = record.componente_code or ''

            m = re.match(r'^t(\d+)(?:_([kcmy]))?$', code)
            if m:
                tipo = self.env['componente.tipo'].browse(int(m.group(1)))
                nombre = tipo.name if tipo.exists() else f"Componente {m.group(1)}"
                if m.group(2):
                    nombre = f"{nombre} ({color_map.get(m.group(2), m.group(2).upper())})"
                record.componente_display = nombre
                continue

            m2 = re.match(r'^a(\d+)$', code)
            if m2:
                tipo = self.env['accesorio.tipo'].browse(int(m2.group(1)))
                record.componente_display = tipo.name if tipo.exists() else f"Accesorio {m2.group(1)}"
                continue

            record.componente_display = code

    @api.depends('subparte_id', 'color_id', 'pedido_id.equipo_id')
    def _compute_ultimo_cambio(self):
        """Busca el último cambio aprobado de esta subparte en este equipo."""
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

        for record in self:
            equipo_id = record.pedido_id.equipo_id.id if record.pedido_id.equipo_id else False

            if not equipo_id or not record.subparte_id:
                record.ultimo_cambio_fecha = False
                record.ultimo_cambio_contometro = False
                record.meses_desde_ultimo_cambio = 0
                continue

            domain = [
                ('equipo_id', '=', equipo_id),
                ('subparte_id', '=', record.subparte_id.id),
            ]
            if record.color_id:
                domain.append(('color_id', '=', record.color_id.id))

            ultimo = self.env['ticket.repuesto.historial'].search(
                domain,
                order='fecha_cambio desc',
                limit=1
            )

            if ultimo:
                record.ultimo_cambio_fecha = ultimo.fecha_cambio
                record.ultimo_cambio_contometro = ultimo.contometro_cambio

                if ultimo.fecha_cambio:
                    diff = relativedelta(datetime.now(), ultimo.fecha_cambio)
                    record.meses_desde_ultimo_cambio = diff.months + (diff.years * 12)
                else:
                    record.meses_desde_ultimo_cambio = 0
            else:
                record.ultimo_cambio_fecha = False
                record.ultimo_cambio_contometro = False
                record.meses_desde_ultimo_cambio = 0

    @api.model
    def create(self, vals):
        _logger.info(
            "[ticket.repuesto.pedido.linea] create() pedido_id=%s subparte_id=%s cantidad=%s",
            vals.get('pedido_id'),
            vals.get('subparte_id'),
            vals.get('cantidad'),
        )
        return super().create(vals)