# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SatReservaSolicitudWizard(models.TransientModel):
    _name = 'sat.reserva.solicitud.wizard'
    _description = 'Solicitar autorización comercial a gerencia'

    maquina_ids = fields.Many2many(
        'sat.sat',
        string='Máquinas',
        required=True,
    )

    cantidad_maquinas = fields.Integer(
        string='Cantidad',
        compute='_compute_cantidad',
    )

    tipo_solicitud = fields.Selection(
        [
            ('reservar', 'Reserva especial'),
            ('extender', 'Extender separación'),
            ('reducir', 'Reducir separación'),
            ('cambiar_fecha', 'Cambiar fecha límite'),
            ('cambiar_cliente', 'Cambiar cliente'),
            ('cambiar_asesora', 'Cambiar asesora'),
            ('liberar', 'Liberar máquinas'),
        ],
        string='Acción solicitada',
        required=True,
        default='reservar',
    )

    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente destino',
    )

    asesora_destino_id = fields.Many2one(
        'res.users',
        string='Asesora destino',
        default=lambda self: self.env.user,
    )

    motivo = fields.Selection(
        [
            ('pago', 'Cliente pagó'),
            ('adelanto', 'Cliente dejó adelanto'),
            ('confirmacion', 'Cliente confirmó compra'),
            ('orden_compra', 'Orden de compra recibida'),
            ('empresa_interna', 'Empresa interna'),
            ('espera_recojo', 'Esperando recojo'),
            ('espera_documentacion', 'Esperando documentación'),
            ('espera_revision', 'Esperando revisión técnica'),
            ('espera_reparacion', 'Esperando reparación'),
            ('cambio_cliente', 'Cambio de cliente solicitado'),
            ('cambio_asesora', 'Cambio de asesora solicitado'),
            ('otro', 'Otro'),
        ],
        string='Motivo',
        required=True,
    )

    detalle_motivo = fields.Text(
        string='Detalle / sustento',
        required=True,
    )

    modalidad_plazo = fields.Selection(
        [
            ('fecha', 'Hasta una fecha'),
            ('dias', 'Cantidad de días'),
            ('mantener', 'Mantener vencimiento actual'),
        ],
        string='Definir plazo por',
        default='fecha',
    )

    fecha_solicitada = fields.Date(
        string='Fecha solicitada',
    )

    dias_solicitados = fields.Integer(
        string='Días solicitados',
    )

    @api.depends('maquina_ids')
    def _compute_cantidad(self):
        for record in self:
            record.cantidad_maquinas = len(record.maquina_ids)

    @api.onchange('tipo_solicitud')
    def _onchange_tipo_solicitud(self):
        if self.tipo_solicitud in ('liberar', 'cambiar_asesora'):
            self.modalidad_plazo = False
            self.fecha_solicitada = False
            self.dias_solicitados = 0

        elif self.tipo_solicitud == 'cambiar_cliente':
            self.motivo = 'cambio_cliente'
            self.modalidad_plazo = 'mantener'
            self.fecha_solicitada = False
            self.dias_solicitados = 0

        elif self.tipo_solicitud == 'cambiar_fecha':
            self.modalidad_plazo = 'fecha'

        elif not self.modalidad_plazo:
            self.modalidad_plazo = 'fecha'

        if self.tipo_solicitud == 'cambiar_asesora':
            self.motivo = 'cambio_asesora'

    @api.onchange('modalidad_plazo')
    def _onchange_modalidad_plazo(self):
        if self.modalidad_plazo == 'fecha':
            self.dias_solicitados = 0

        elif self.modalidad_plazo == 'dias':
            self.fecha_solicitada = False

        elif self.modalidad_plazo == 'mantener':
            self.fecha_solicitada = False
            self.dias_solicitados = 0

    def _validar(self):
        self.ensure_one()

        if not self.maquina_ids:
            raise ValidationError(
                _('Debe seleccionar al menos una máquina.')
            )

        if self.tipo_solicitud == 'cambiar_cliente' and not self.cliente_id:
            raise ValidationError(
                _('Debe seleccionar el nuevo cliente.')
            )

        if self.tipo_solicitud == 'cambiar_asesora' and not self.asesora_destino_id:
            raise ValidationError(
                _('Debe seleccionar la nueva asesora.')
            )

        requiere_plazo = self.tipo_solicitud in (
            'reservar',
            'extender',
            'reducir',
            'cambiar_fecha',
            'cambiar_cliente',
        )

        if requiere_plazo:
            if self.modalidad_plazo == 'fecha':
                if not self.fecha_solicitada:
                    raise ValidationError(
                        _('Debe indicar la fecha solicitada.')
                    )

                if self.fecha_solicitada < fields.Date.context_today(self):
                    raise ValidationError(
                        _('La fecha solicitada no puede ser anterior a hoy.')
                    )

            elif self.modalidad_plazo == 'dias':
                if self.dias_solicitados <= 0:
                    raise ValidationError(
                        _('Los días solicitados deben ser mayores a cero.')
                    )

            elif self.modalidad_plazo == 'mantener':
                if self.tipo_solicitud != 'cambiar_cliente':
                    raise ValidationError(
                        _('Mantener vencimiento actual solo se usa para cambio de cliente.')
                    )

                sin_vencimiento = self.maquina_ids.filtered(
                    lambda machine: not machine.reserva_fecha_limite
                )

                if sin_vencimiento:
                    raise ValidationError(
                        _(
                            'Estas máquinas no tienen un vencimiento actual que conservar: %s'
                        )
                        % ', '.join(
                            sin_vencimiento.mapped('serie_id')
                        )
                    )

            else:
                raise ValidationError(
                    _('Debe definir el plazo solicitado.')
                )

        if self.tipo_solicitud in (
            'extender',
            'reducir',
            'cambiar_fecha',
        ):
            sin_vencimiento = self.maquina_ids.filtered(
                lambda machine: not machine.reserva_fecha_limite
            )

            if sin_vencimiento:
                raise ValidationError(
                    _(
                        'Estas máquinas no tienen una reserva con vencimiento: %s'
                    )
                    % ', '.join(
                        sin_vencimiento.mapped('serie_id')
                    )
                )

        entregadas = self.maquina_ids.filtered(
            lambda machine: machine.estado_ventas_id == 'entregada'
        )

        if entregadas:
            raise ValidationError(
                _(
                    'No puede incluir máquinas entregadas: %s'
                )
                % ', '.join(
                    entregadas.mapped('serie_id')
                )
            )

        pendientes = self.maquina_ids.filtered(
            lambda machine: machine.reserva_solicitud_pendiente_id
        )

        if pendientes:
            raise ValidationError(
                _(
                    'Estas máquinas ya tienen una solicitud pendiente: %s'
                )
                % ', '.join(
                    pendientes.mapped('serie_id')
                )
            )

        return True

    def action_crear_solicitud(self):
        self.ensure_one()
        self._validar()

        line_commands = []

        for machine in self.maquina_ids:
            line_commands.append(
                (
                    0,
                    0,
                    {
                        'maquina_id': machine.id,
                        'seleccionada': True,
                        'cliente_actual_id': (
                            machine.cliente_id.id
                            if machine.cliente_id
                            else False
                        ),
                        'asesora_actual_id': (
                            machine.reserva_asesora_id.id
                            if machine.reserva_asesora_id
                            else False
                        ),
                        'estado_reserva_anterior': machine.reserva_estado,
                        'fecha_limite_anterior': machine.reserva_fecha_limite,
                    },
                )
            )

        request_vals = {
            'cliente_id': (
                self.cliente_id.id
                if self.cliente_id
                else False
            ),
            'asesora_destino_id': (
                self.asesora_destino_id.id
                if self.asesora_destino_id
                else False
            ),
            'tipo_solicitud': self.tipo_solicitud,
            'motivo': self.motivo,
            'detalle_motivo': self.detalle_motivo,
            'modalidad_solicitada': self.modalidad_plazo or False,
            'fecha_solicitada': (
                self.fecha_solicitada
                if self.modalidad_plazo == 'fecha'
                else False
            ),
            'dias_solicitados': (
                self.dias_solicitados
                if self.modalidad_plazo == 'dias'
                else 0
            ),
            'line_ids': line_commands,
        }

        request = self.env[
            'sat.reserva.solicitud'
        ].create(
            request_vals
        )

        if not request.line_ids:
            raise ValidationError(
                _(
                    'No se pudieron crear las líneas de máquinas de la solicitud. '
                    'La operación fue cancelada para evitar una solicitud incompleta.'
                )
            )

        request.action_enviar_gerencia()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitud de autorización'),
            'res_model': 'sat.reserva.solicitud',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }
