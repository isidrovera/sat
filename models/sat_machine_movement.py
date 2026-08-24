# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SatMachineMovement(models.Model):
    _name = 'sat.machine.movement'
    _description = 'Historial de movimientos de máquina'
    _order = 'event_date desc, id desc'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    machine_id = fields.Many2one(
        'sat.sat',
        string='Máquina',
        required=True,
        index=True,
        ondelete='cascade',
        tracking=True,
    )

    movement_type = fields.Selection(
        [
            ('download', 'Descarga / Ingreso'),
            ('location', 'Cambio de ubicación'),
            ('delivery', 'Entrega'),
            ('delivery_return', 'Regreso de entrega'),
        ],
        string='Tipo de movimiento',
        required=True,
        index=True,
        tracking=True,
    )

    event_date = fields.Datetime(
        string='Fecha y hora',
        required=True,
        default=fields.Datetime.now,
        index=True,
        tracking=True,
    )

    user_id = fields.Many2one(
        'res.users',
        string='Registrado por',
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
        index=True,
        tracking=True,
    )

    customer_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        index=True,
        tracking=True,
    )

    invoice_number = fields.Char(
        string='Factura de venta',
        tracking=True,
    )

    delivery_date = fields.Date(
        string='Fecha de entrega',
        tracking=True,
    )

    previous_technical_state = fields.Char(string='Estado técnico anterior', readonly=True)
    new_technical_state = fields.Char(string='Estado técnico nuevo', readonly=True)

    previous_availability = fields.Char(string='Disponibilidad anterior', readonly=True)
    new_availability = fields.Char(string='Disponibilidad nueva', readonly=True)

    previous_location = fields.Char(string='Ubicación anterior', readonly=True)
    new_location = fields.Char(string='Ubicación nueva', readonly=True)

    previous_technical_state_label = fields.Char(
        string='Estado técnico anterior (texto)',
        readonly=True,
    )
    new_technical_state_label = fields.Char(
        string='Estado técnico nuevo (texto)',
        readonly=True,
    )

    previous_availability_label = fields.Char(
        string='Disponibilidad anterior (texto)',
        readonly=True,
    )
    new_availability_label = fields.Char(
        string='Disponibilidad nueva (texto)',
        readonly=True,
    )

    previous_location_label = fields.Char(
        string='Ubicación anterior (texto)',
        readonly=True,
    )
    new_location_label = fields.Char(
        string='Ubicación nueva (texto)',
        readonly=True,
    )

    ingress_state = fields.Char(
        string='Estado de ingreso',
        readonly=True,
    )

    ingress_source = fields.Char(
        string='Fuente de ingreso',
        readonly=True,
    )

    observation = fields.Text(
        string='Observación / motivo',
        tracking=True,
    )

    reference = fields.Char(
        string='Referencia',
        tracking=True,
        help='Referencia externa opcional: guía, documento, orden u otro identificador.',
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
    )

    display_name = fields.Char(
        string='Movimiento',
        compute='_compute_display_name',
        store=True,
    )

    @api.depends(
        'movement_type',
        'machine_id',
        'machine_id.serie_id',
        'event_date',
    )
    def _compute_display_name(self):
        labels = dict(self._fields['movement_type'].selection)

        for record in self:
            movement_label = labels.get(
                record.movement_type,
                record.movement_type or 'Movimiento',
            )
            serial = record.machine_id.serie_id if record.machine_id else ''

            record.display_name = (
                '%s - %s' % (movement_label, serial)
                if serial
                else movement_label
            )

    @api.model
    def _selection_label(self, record, field_name):
        if not record or field_name not in record._fields:
            return ''

        value = record[field_name]
        if not value:
            return ''

        field = record._fields[field_name]

        try:
            selection = field._description_selection(record.env)
            return dict(selection or []).get(value, value)
        except Exception:
            return str(value)

    @api.model
    def _value_label(self, record, field_name, value):
        if not record or not value or field_name not in record._fields:
            return ''

        field = record._fields[field_name]

        try:
            selection = field._description_selection(record.env)
            return dict(selection or []).get(value, value)
        except Exception:
            return str(value)

    @api.model
    def create_from_machine(
        self,
        machine,
        movement_type,
        *,
        event_date=None,
        customer=None,
        invoice_number=None,
        delivery_date=None,
        previous_technical_state=None,
        previous_availability=None,
        previous_location=None,
        observation=None,
        reference=None,
    ):
        """
        Crea una fotografía auditable del movimiento DESPUÉS de que la operación
        principal sobre sat.sat haya sido realizada.

        Los valores previous_* se capturan antes de modificar la máquina.
        Los valores new_* se leen de la máquina ya actualizada.
        """
        if not machine:
            return False

        machine.ensure_one()

        current_technical_state = (
            machine.estado_ventas_id
            if 'estado_ventas_id' in machine._fields
            else False
        )
        current_availability = (
            machine.disponibilidad_id
            if 'disponibilidad_id' in machine._fields
            else False
        )
        current_location = (
            machine.ubicacion_id
            if 'ubicacion_id' in machine._fields
            else False
        )

        vals = {
            'machine_id': machine.id,
            'movement_type': movement_type,
            'event_date': event_date or fields.Datetime.now(),
            'user_id': self.env.user.id,
            'customer_id': (
                customer.id
                if customer
                else (
                    machine.cliente_id.id
                    if 'cliente_id' in machine._fields and machine.cliente_id
                    else False
                )
            ),
            'invoice_number': (
                invoice_number
                if invoice_number is not None
                else (
                    machine.factura_venta
                    if 'factura_venta' in machine._fields
                    else False
                )
            ),
            'delivery_date': (
                delivery_date
                if delivery_date is not None
                else (
                    machine.fecha_entrega
                    if 'fecha_entrega' in machine._fields
                    else False
                )
            ),
            'previous_technical_state': previous_technical_state or False,
            'new_technical_state': current_technical_state or False,
            'previous_availability': previous_availability or False,
            'new_availability': current_availability or False,
            'previous_location': previous_location or False,
            'new_location': current_location or False,
            'previous_technical_state_label': self._value_label(
                machine,
                'estado_ventas_id',
                previous_technical_state,
            ),
            'new_technical_state_label': self._selection_label(
                machine,
                'estado_ventas_id',
            ),
            'previous_availability_label': self._value_label(
                machine,
                'disponibilidad_id',
                previous_availability,
            ),
            'new_availability_label': self._selection_label(
                machine,
                'disponibilidad_id',
            ),
            'previous_location_label': self._value_label(
                machine,
                'ubicacion_id',
                previous_location,
            ),
            'new_location_label': self._selection_label(
                machine,
                'ubicacion_id',
            ),
            'ingress_state': (
                machine.ingreso_estado
                if 'ingreso_estado' in machine._fields
                else False
            ),
            'ingress_source': (
                machine.ingreso_fuente
                if 'ingreso_fuente' in machine._fields
                else False
            ),
            'observation': observation or False,
            'reference': reference or False,
        }

        return self.create(vals)
