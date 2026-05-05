# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta


class TicketAlquilerMantenimientoPlanificador(models.Model):
    _inherit = 'ticket.alquiler'

    # ============================================================
    # CAMPOS DE PLANIFICADOR
    # ============================================================

    planificador_linea_id = fields.Many2one(
        'mantenimiento.planificador.linea',
        string='Línea de planificación',
        tracking=True,
        copy=False,
        index=True,
        help='Línea del planificador inteligente que originó este ticket.'
    )

    planificador_id = fields.Many2one(
        'mantenimiento.planificador',
        string='Planificador',
        related='planificador_linea_id.planificador_id',
        store=True,
        readonly=True,
        index=True
    )

    es_mantenimiento_programado = fields.Boolean(
        string='Mantenimiento programado',
        compute='_compute_es_mantenimiento_programado',
        store=True,
        help='Indica si el ticket corresponde a un mantenimiento preventivo programado.'
    )

    tecnico_apoyo_ids = fields.Many2many(
        'res.users',
        'ticket_alquiler_tecnico_apoyo_rel',
        'ticket_id',
        'user_id',
        string='Técnicos de apoyo',
        tracking=True,
        domain=[('share', '=', False)],
        help='Técnicos adicionales asignados al mantenimiento.'
    )

    requiere_reasignacion = fields.Boolean(
        string='Requiere reasignación',
        default=False,
        tracking=True,
        copy=False,
        help='Se activa cuando el técnico asignado ya no está disponible.'
    )

    motivo_reasignacion = fields.Text(
        string='Motivo de reasignación',
        tracking=True,
        copy=False
    )

    fecha_programada_mantenimiento = fields.Date(
        string='Fecha programada mantenimiento',
        compute='_compute_fecha_programada_mantenimiento',
        store=True
    )

    hora_programada_mantenimiento = fields.Float(
        string='Hora programada mantenimiento',
        compute='_compute_fecha_programada_mantenimiento',
        store=True
    )

    duracion_programada_horas = fields.Float(
        string='Duración programada',
        default=2.0,
        tracking=True,
        help='Duración estimada de este ticket.'
    )

    zona_mantenimiento_id = fields.Many2one(
        'mantenimiento.zona',
        string='Zona de mantenimiento',
        compute='_compute_zona_mantenimiento_id',
        store=True,
        readonly=False
    )

    distrito_mantenimiento = fields.Char(
        string='Distrito mantenimiento',
        compute='_compute_distrito_mantenimiento',
        store=True,
        readonly=False
    )

    # ============================================================
    # COMPUTES
    # ============================================================

    @api.depends('tipo_servicio_id', 'planificador_linea_id')
    def _compute_es_mantenimiento_programado(self):
        for rec in self:
            rec.es_mantenimiento_programado = bool(
                rec.tipo_servicio_id == 'mantenimiento_preventivo'
                and rec.planificador_linea_id
            )

    @api.depends('agenda')
    def _compute_fecha_programada_mantenimiento(self):
        for rec in self:
            if rec.agenda:
                agenda_dt = fields.Datetime.to_datetime(rec.agenda)
                rec.fecha_programada_mantenimiento = agenda_dt.date()
                rec.hora_programada_mantenimiento = (
                    agenda_dt.hour + agenda_dt.minute / 60.0
                )
            else:
                rec.fecha_programada_mantenimiento = False
                rec.hora_programada_mantenimiento = 0.0

    @api.depends(
        'product_alquiler',
        'product_alquiler.zona_mantenimiento_id',
        'planificador_linea_id',
        'planificador_linea_id.zona_id'
    )
    def _compute_zona_mantenimiento_id(self):
        for rec in self:
            if rec.planificador_linea_id and rec.planificador_linea_id.zona_id:
                rec.zona_mantenimiento_id = rec.planificador_linea_id.zona_id.id
            elif rec.product_alquiler and rec.product_alquiler.zona_mantenimiento_id:
                rec.zona_mantenimiento_id = rec.product_alquiler.zona_mantenimiento_id.id
            else:
                rec.zona_mantenimiento_id = False

    @api.depends(
        'product_alquiler',
        'product_alquiler.distrito',
        'planificador_linea_id',
        'planificador_linea_id.distrito'
    )
    def _compute_distrito_mantenimiento(self):
        for rec in self:
            if rec.planificador_linea_id and rec.planificador_linea_id.distrito:
                rec.distrito_mantenimiento = rec.planificador_linea_id.distrito
            elif rec.product_alquiler and rec.product_alquiler.distrito:
                rec.distrito_mantenimiento = rec.product_alquiler.distrito
            else:
                rec.distrito_mantenimiento = False

    # ============================================================
    # ONCHANGE
    # ============================================================

    @api.onchange('planificador_linea_id')
    def _onchange_planificador_linea_id(self):
        for rec in self:
            linea = rec.planificador_linea_id
            if not linea:
                continue

            rec.product_alquiler = linea.equipo_id.id
            rec.partner_id = linea.cliente_id.id if linea.cliente_id else False
            rec.responsable = linea.tecnico_id.id if linea.tecnico_id else False
            rec.tecnico_apoyo_ids = [(6, 0, linea.tecnico_apoyo_ids.ids)]
            rec.tipo_servicio_id = 'mantenimiento_preventivo'
            rec.duracion_programada_horas = linea.duracion_horas or 2.0

            agenda_dt = linea._get_agenda_datetime()
            if agenda_dt:
                rec.agenda = agenda_dt

    @api.onchange('product_alquiler')
    def _onchange_product_alquiler_planificador(self):
        for rec in self:
            if not rec.product_alquiler:
                continue

            if rec.tipo_servicio_id == 'mantenimiento_preventivo':
                rec.zona_mantenimiento_id = rec.product_alquiler.zona_mantenimiento_id.id
                rec.distrito_mantenimiento = rec.product_alquiler.distrito

    # ============================================================
    # VALIDACIONES
    # ============================================================

    @api.constrains('agenda', 'responsable', 'tecnico_apoyo_ids', 'duracion_programada_horas')
    def _check_tecnicos_disponibles_planificador(self):
        Perfil = self.env['mantenimiento.tecnico.perfil']

        for rec in self:
            if not rec.agenda or not rec.responsable:
                continue

            if rec.tipo_servicio_id != 'mantenimiento_preventivo':
                continue

            if self.env.context.get('skip_planificador_validation'):
                continue

            agenda_dt = fields.Datetime.to_datetime(rec.agenda)
            fecha = agenda_dt.date()
            hora_inicio = agenda_dt.hour + agenda_dt.minute / 60.0
            duracion = rec.duracion_programada_horas or 2.0
            hora_fin = hora_inicio + duracion
            fin_dt = agenda_dt + timedelta(hours=duracion)

            tecnicos = rec.responsable | rec.tecnico_apoyo_ids

            for tecnico in tecnicos:
                perfil = Perfil.search([
                    ('tecnico_id', '=', tecnico.id),
                    ('active', '=', True),
                ], limit=1)

                if not perfil:
                    raise ValidationError(
                        _("El técnico %s no tiene perfil operativo de mantenimiento.")
                        % tecnico.name
                    )

                disp = perfil.get_disponibilidad_fecha(fecha)

                if not disp.get('disponible'):
                    raise ValidationError(
                        _("El técnico %s no está disponible el %s.")
                        % (tecnico.name, fecha.strftime('%d/%m/%Y'))
                    )

                if hora_inicio < disp.get('hora_inicio') or hora_fin > disp.get('hora_fin'):
                    raise ValidationError(
                        _("El técnico %s no está disponible en el horario %.2f - %.2f.")
                        % (tecnico.name, hora_inicio, hora_fin)
                    )

                tickets_cruzados = self.search([
                    ('id', '!=', rec.id),
                    ('agenda', '!=', False),
                    ('estado', 'not in', ['finalizado']),
                    '|',
                    ('responsable', '=', tecnico.id),
                    ('tecnico_apoyo_ids', 'in', tecnico.id),
                ])

                for other in tickets_cruzados:
                    other_inicio = fields.Datetime.to_datetime(other.agenda)
                    other_duracion = other.duracion_programada_horas or 2.0
                    other_fin = other_inicio + timedelta(hours=other_duracion)

                    if other_inicio < fin_dt and other_fin > agenda_dt:
                        raise ValidationError(
                            _(
                                "El técnico %s ya tiene programación cruzada:\n"
                                "%s\n"
                                "%s - %s"
                            ) % (
                                tecnico.name,
                                other.name,
                                other_inicio.strftime('%d/%m/%Y %H:%M'),
                                other_fin.strftime('%H:%M'),
                            )
                        )

    # ============================================================
    # CREATE / WRITE
    # ============================================================

    @api.model
    def create(self, vals):
        ticket = super().create(vals)

        if ticket.planificador_linea_id:
            ticket._sync_linea_planificador_desde_ticket()

        return ticket

    def write(self, vals):
        res = super().write(vals)

        campos_sync = {
            'agenda',
            'responsable',
            'tecnico_apoyo_ids',
            'estado',
            'duracion_programada_horas',
            'requiere_reasignacion',
        }

        if campos_sync.intersection(vals.keys()):
            for rec in self:
                if rec.planificador_linea_id:
                    rec._sync_linea_planificador_desde_ticket()

        return res

    # ============================================================
    # HELPERS
    # ============================================================

    def _sync_linea_planificador_desde_ticket(self):
        for rec in self:
            linea = rec.planificador_linea_id
            if not linea:
                continue

            vals = {}

            if rec.agenda:
                agenda_dt = fields.Datetime.to_datetime(rec.agenda)
                vals.update({
                    'fecha_programada': agenda_dt.date(),
                    'hora_inicio': agenda_dt.hour + agenda_dt.minute / 60.0,
                    'hora_fin': (
                        agenda_dt.hour + agenda_dt.minute / 60.0
                        + (rec.duracion_programada_horas or 2.0)
                    ),
                })

            if rec.responsable:
                vals['tecnico_id'] = rec.responsable.id

            vals['tecnico_apoyo_ids'] = [(6, 0, rec.tecnico_apoyo_ids.ids)]

            if rec.requiere_reasignacion:
                vals['estado'] = 'reasignar'
            elif rec.estado == 'finalizado':
                vals['estado'] = 'ticket_creado'
            elif rec.agenda and rec.responsable and linea.estado not in ('ticket_creado',):
                vals['estado'] = 'programado'

            if vals:
                linea.with_context(skip_ticket_sync=True).write(vals)

            if rec.product_alquiler and rec.agenda:
                agenda_dt = fields.Datetime.to_datetime(rec.agenda)
                rec.product_alquiler.write({
                    'fecha_programada_mantenimiento': agenda_dt.date(),
                    'hora_programada_mantenimiento': agenda_dt.hour + agenda_dt.minute / 60.0,
                    'tecnico_mantenimiento_id': rec.responsable.id if rec.responsable else False,
                    'zona_mantenimiento_id': rec.zona_mantenimiento_id.id if rec.zona_mantenimiento_id else False,
                })

    def _buscar_planificador_activo_para_ticket(self):
        self.ensure_one()

        fecha_base = False

        if self.agenda:
            fecha_base = fields.Datetime.to_datetime(self.agenda).date()
        elif self.product_alquiler and self.product_alquiler.fecha_recurrente:
            fecha_base = self.product_alquiler.fecha_recurrente

        if not fecha_base:
            return False

        return self.env['mantenimiento.planificador'].search([
            ('fecha_inicio', '<=', fecha_base),
            ('fecha_fin', '>=', fecha_base),
            ('estado', 'in', ['borrador', 'generado', 'en_proceso']),
        ], order='fecha_inicio desc, id desc', limit=1)

    def _crear_linea_planificador_desde_ticket(self):
        self.ensure_one()

        if self.planificador_linea_id:
            return self.planificador_linea_id

        if self.tipo_servicio_id != 'mantenimiento_preventivo':
            raise UserError(_("Solo aplica para mantenimiento preventivo."))

        if not self.product_alquiler:
            raise UserError(_("El ticket no tiene máquina asignada."))

        plan = self._buscar_planificador_activo_para_ticket()

        if not plan:
            raise UserError(_("No se encontró planificador activo para este ticket."))

        equipo = self.product_alquiler
        zona = self.zona_mantenimiento_id or equipo.zona_mantenimiento_id

        if not zona and equipo.distrito:
            zona = plan._get_zona_por_distrito(equipo.distrito)

        fecha_ideal = equipo.fecha_recurrente
        fecha_programada = False
        hora_inicio = 0.0

        if self.agenda:
            agenda_dt = fields.Datetime.to_datetime(self.agenda)
            fecha_programada = agenda_dt.date()
            hora_inicio = agenda_dt.hour + agenda_dt.minute / 60.0

        linea = self.env['mantenimiento.planificador.linea'].create({
            'planificador_id': plan.id,
            'equipo_id': equipo.id,
            'cliente_id': self.partner_id.id if self.partner_id else equipo.cliente_id.id,
            'distrito': equipo.distrito,
            'zona_id': zona.id if zona else False,
            'fecha_ideal': fecha_ideal,
            'fecha_programada': fecha_programada,
            'hora_inicio': hora_inicio,
            'hora_fin': hora_inicio + (self.duracion_programada_horas or 2.0),
            'tecnico_id': self.responsable.id if self.responsable else False,
            'tecnico_apoyo_ids': [(6, 0, self.tecnico_apoyo_ids.ids)],
            'cantidad_tecnicos': 1 + len(self.tecnico_apoyo_ids),
            'duracion_horas': self.duracion_programada_horas or 2.0,
            'estado': 'programado' if self.agenda and self.responsable else 'pendiente',
            'ticket_id': self.id,
        })

        self.planificador_linea_id = linea.id

        return linea

    # ============================================================
    # ACCIONES
    # ============================================================

    def action_crear_linea_planificador(self):
        self.ensure_one()
        linea = self._crear_linea_planificador_desde_ticket()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Línea de planificación'),
            'res_model': 'mantenimiento.planificador.linea',
            'res_id': linea.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_marcar_requiere_reasignacion(self):
        for rec in self:
            rec.write({
                'requiere_reasignacion': True,
                'motivo_reasignacion': rec.motivo_reasignacion or _(
                    "Marcado manualmente para reasignación."
                )
            })

            if rec.planificador_linea_id:
                rec.planificador_linea_id.action_marcar_reasignar()

            rec.message_post(
                body=_("⚠️ Ticket marcado para reasignación."),
                message_type='notification'
            )

    def action_reasignar_automaticamente(self):
        for rec in self:
            linea = rec.planificador_linea_id or rec._crear_linea_planificador_desde_ticket()

            linea.estado = 'reasignar'
            linea.action_buscar_y_asignar_slot()

            if not linea.tecnico_id or not linea.fecha_programada:
                raise UserError(_("No se pudo reasignar automáticamente."))

            agenda_dt = linea._get_agenda_datetime()

            rec.with_context(skip_planificador_validation=True).write({
                'responsable': linea.tecnico_id.id,
                'tecnico_apoyo_ids': [(6, 0, linea.tecnico_apoyo_ids.ids)],
                'agenda': agenda_dt,
                'requiere_reasignacion': False,
                'motivo_reasignacion': False,
            })

            if hasattr(rec, 'crear_evento_calendario'):
                rec.crear_evento_calendario()

            rec.message_post(
                body=_(
                    "✅ Ticket reasignado automáticamente a %s para el %s."
                ) % (
                    linea.tecnico_id.name,
                    linea.fecha_programada.strftime('%d/%m/%Y'),
                ),
                message_type='notification'
            )

    def action_ver_linea_planificador(self):
        self.ensure_one()

        if not self.planificador_linea_id:
            raise UserError(_("Este ticket no tiene línea de planificación."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Línea de planificación'),
            'res_model': 'mantenimiento.planificador.linea',
            'res_id': self.planificador_linea_id.id,
            'view_mode': 'form',
            'target': 'current',
        }