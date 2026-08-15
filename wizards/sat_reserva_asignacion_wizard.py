# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SatReservaAsignacionWizard(models.TransientModel):
    _name = 'sat.reserva.asignacion.wizard'
    _description = 'Asignación masiva de máquinas a asesoras'

    maquina_ids = fields.Many2many(
        'sat.sat',
        string='Máquinas',
        required=True,
    )

    cantidad_maquinas = fields.Integer(
        string='Cantidad',
        compute='_compute_cantidad',
    )

    modo = fields.Selection(
        [
            ('una', 'Asignar todas a una asesora'),
            ('repartir', 'Repartir entre varias asesoras'),
        ],
        string='Modo',
        required=True,
        default='una',
    )

    asesora_id = fields.Many2one(
        'res.users',
        string='Asesora',
        default=lambda self: self.env.user,
    )

    asesora_ids = fields.Many2many(
        'res.users',
        'sat_reserva_asignacion_wizard_user_rel',
        'wizard_id',
        'user_id',
        string='Asesoras',
    )

    observacion = fields.Text(
        string='Observación',
    )

    @api.depends('maquina_ids')
    def _compute_cantidad(self):
        for record in self:
            record.cantidad_maquinas = len(record.maquina_ids)

    @api.constrains('modo', 'asesora_id', 'asesora_ids')
    def _check_asignacion(self):
        for record in self:
            if record.modo == 'una' and not record.asesora_id:
                raise ValidationError(
                    _('Debe seleccionar una asesora.')
                )

            if record.modo == 'repartir' and not record.asesora_ids:
                raise ValidationError(
                    _('Debe seleccionar al menos una asesora para repartir.')
                )

    def action_asignar(self):
        self.ensure_one()

        if not self.maquina_ids:
            raise ValidationError(
                _('Debe seleccionar al menos una máquina.')
            )

        delivered = self.maquina_ids.filtered(
            lambda machine: machine.estado_ventas_id == 'entregada'
        )

        if delivered:
            raise ValidationError(
                _(
                    'No puede asignar máquinas entregadas: %s'
                )
                % ', '.join(delivered.mapped('serie_id'))
            )

        occupied = self.maquina_ids.filtered(
            lambda machine:
                machine._reserva_esta_vigente()
                and machine.reserva_asesora_id
                and (
                    self.modo == 'repartir'
                    or machine.reserva_asesora_id != self.asesora_id
                )
        )

        if occupied:
            detail = '\n'.join(
                '%s → %s hasta %s'
                % (
                    machine.serie_id or machine.display_name,
                    machine.reserva_asesora_id.name,
                    machine.reserva_fecha_limite or '',
                )
                for machine in occupied
            )

            raise ValidationError(
                _(
                    'Algunas máquinas ya tienen una asesora vigente:\n\n%s'
                )
                % detail
            )

        machines = self.maquina_ids.sorted(
            key=lambda machine: (machine.importacion or '', machine.id)
        )

        if self.modo == 'una':
            for machine in machines:
                machine._reserva_asignar_asesora(
                    self.asesora_id,
                    cliente=machine.cliente_id or False,
                )

        else:
            advisors = self.asesora_ids.sorted(
                key=lambda user: user.id
            )

            if not advisors:
                raise ValidationError(
                    _('Debe seleccionar asesoras.')
                )

            advisor_list = list(advisors)

            for index, machine in enumerate(machines):
                advisor = advisor_list[index % len(advisor_list)]

                machine._reserva_asignar_asesora(
                    advisor,
                    cliente=machine.cliente_id or False,
                )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Asignación comercial'),
                'message': _(
                    '%s máquinas fueron asignadas correctamente.'
                )
                % len(machines),
                'type': 'success',
                'sticky': False,
            },
        }
