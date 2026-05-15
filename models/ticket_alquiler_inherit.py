# -*- coding: utf-8 -*-

import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
from pytz import timezone, UTC


_logger = logging.getLogger(__name__)


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
    # HELPERS DE ZONA HORARIA
    # ============================================================

    def _agenda_to_local(self, agenda_value):
        """
        Convierte un valor de agenda (Datetime UTC naive) al timezone del usuario.

        Odoo almacena los Datetime en UTC. Si extraemos .hour directamente
        obtenemos hora UTC, no hora local. Este helper centraliza la conversión.

        Devuelve un datetime naive en hora local lista para extraer .hour y .date().
        """
        if not agenda_value:
            return False

        user_tz = self.env.user.tz or 'America/Lima'
        local_tz = timezone(user_tz)

        agenda_utc = fields.Datetime.to_datetime(agenda_value)
        agenda_local = UTC.localize(agenda_utc).astimezone(local_tz).replace(tzinfo=None)

        return agenda_local

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
                agenda_dt = rec._agenda_to_local(rec.agenda)
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
            rec.duracion_programada_horas = linea.duracion_horas or 1.0

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

    @api.onchange('tipo_servicio_id')
    def _onchange_tipo_servicio_duracion_planificador(self):
        for rec in self:
            if rec.tipo_servicio_id == 'mantenimiento_preventivo':
                rec.duracion_programada_horas = 1.0
            elif rec.tipo_servicio_id == 'remoto':
                rec.duracion_programada_horas = 1.0
            elif not rec.duracion_programada_horas:
                rec.duracion_programada_horas = 2.0

    # ============================================================
    # HELPERS DE DURACIÓN
    # ============================================================

    def _get_duracion_planificador_ticket(self):
        """
        Duración real usada para validar cruces de agenda.

        Regla:
        - Si el ticket tiene duracion_programada_horas válida, se usa esa.
        - Mantenimiento preventivo sin duración explícita: 1 hora.
        - Remoto sin duración explícita: 1 hora.
        - Otros servicios: 2 horas.
        """
        self.ensure_one()

        if self.duracion_programada_horas and self.duracion_programada_horas > 0:
            return self.duracion_programada_horas

        if self.tipo_servicio_id == 'mantenimiento_preventivo':
            return 1.0

        if self.tipo_servicio_id == 'remoto':
            return 1.0

        return 2.0

    # ============================================================
    # VALIDACIONES
    # ============================================================

    @api.constrains(
        'agenda',
        'responsable',
        'tecnico_apoyo_ids',
        'duracion_programada_horas',
        'tipo_servicio_id',
        'estado',
    )
    def _check_tecnicos_disponibles_planificador(self):
        """
        Valida disponibilidad y cruces para mantenimientos.

        Corrección:
        Antes todo mantenimiento quedaba con duración default 2.0 horas.
        Eso hacía que:
            14:00 - 15:00
            15:00 - 16:00
        se detectara incorrectamente como cruce, porque el primer ticket se tomaba
        como 14:00 - 16:00.

        Ahora se usa la duración real del ticket:
            mantenimiento_preventivo = 1 hora si no hay duración explícita.

        Corrección de zona horaria:
        El campo agenda se almacena en UTC. Antes se extraía .hour directo y
        se comparaba contra ventanas horarias del perfil (que están en hora
        local Lima). Eso causaba un desfase de 5 horas: 09:30 Lima = 14:30 UTC
        y se rechazaba contra la ventana 9-13. Ahora se convierte primero a
        la zona horaria del usuario.
        """
        Perfil = self.env['mantenimiento.tecnico.perfil']

        for rec in self:
            _logger.warning(
                "🧭 [PLANIFICADOR VALIDACION][INICIO] ticket=%s id=%s responsable=%s agenda=%s estado=%s tipo=%s duracion=%s contexto=%s",
                rec.name,
                rec.id,
                rec.responsable.name if rec.responsable else False,
                rec.agenda,
                rec.estado,
                rec.tipo_servicio_id,
                rec.duracion_programada_horas,
                self.env.context,
            )

            if self.env.context.get('skip_planificador_validation'):
                _logger.warning(
                    "🧭 [PLANIFICADOR VALIDACION][SKIP_CONTEXT] ticket=%s",
                    rec.name,
                )
                continue

            if not rec.agenda or not rec.responsable:
                _logger.warning(
                    "🧭 [PLANIFICADOR VALIDACION][SKIP] ticket=%s sin agenda/responsable",
                    rec.name,
                )
                continue

            if rec.estado == 'finalizado':
                _logger.warning(
                    "🧭 [PLANIFICADOR VALIDACION][SKIP] ticket=%s finalizado",
                    rec.name,
                )
                continue

            if rec.tipo_servicio_id != 'mantenimiento_preventivo':
                _logger.warning(
                    "🧭 [PLANIFICADOR VALIDACION][SKIP] ticket=%s no es mantenimiento_preventivo tipo=%s",
                    rec.name,
                    rec.tipo_servicio_id,
                )
                continue

            agenda_dt = rec._agenda_to_local(rec.agenda)
            fecha = agenda_dt.date()
            hora_inicio = agenda_dt.hour + agenda_dt.minute / 60.0

            duracion = rec._get_duracion_planificador_ticket()
            hora_fin = hora_inicio + duracion
            fin_dt = agenda_dt + timedelta(hours=duracion)

            _logger.warning(
                "🧭 [PLANIFICADOR VALIDACION][RANGO_ACTUAL] ticket=%s inicio=%s fin=%s hora_inicio=%.2f hora_fin=%.2f duracion=%s",
                rec.name,
                agenda_dt,
                fin_dt,
                hora_inicio,
                hora_fin,
                duracion,
            )

            tecnicos = rec.responsable | rec.tecnico_apoyo_ids

            for tecnico in tecnicos:
                _logger.warning(
                    "🧭 [PLANIFICADOR VALIDACION][TECNICO] ticket=%s tecnico=%s tecnico_id=%s",
                    rec.name,
                    tecnico.name,
                    tecnico.id,
                )

                perfil = Perfil.search([
                    ('tecnico_id', '=', tecnico.id),
                    ('active', '=', True),
                ], limit=1)

                if not perfil:
                    _logger.error(
                        "🔴 [PLANIFICADOR VALIDACION][SIN_PERFIL] tecnico=%s ticket=%s",
                        tecnico.name,
                        rec.name,
                    )
                    raise ValidationError(
                        _("El técnico %s no tiene perfil operativo de mantenimiento.")
                        % tecnico.name
                    )

                disp = perfil.get_disponibilidad_fecha(fecha)

                _logger.warning(
                    "🧭 [PLANIFICADOR VALIDACION][DISPONIBILIDAD] tecnico=%s fecha=%s disp=%s",
                    tecnico.name,
                    fecha,
                    disp,
                )

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

                _logger.warning(
                    "🧭 [PLANIFICADOR VALIDACION][CANDIDATOS] ticket=%s tecnico=%s candidatos=%s",
                    rec.name,
                    tecnico.name,
                    tickets_cruzados.ids,
                )

                cruces = []

                for other in tickets_cruzados:
                    other_inicio = other._agenda_to_local(other.agenda)
                    other_duracion = other._get_duracion_planificador_ticket()
                    other_fin = other_inicio + timedelta(hours=other_duracion)

                    hay_cruce = other_inicio < fin_dt and other_fin > agenda_dt

                    _logger.warning(
                        "🧭 [PLANIFICADOR VALIDACION][COMPARA] actual=%s %s-%s duracion=%s | otro=%s %s-%s duracion=%s | cruce=%s",
                        rec.name,
                        agenda_dt,
                        fin_dt,
                        duracion,
                        other.name,
                        other_inicio,
                        other_fin,
                        other_duracion,
                        hay_cruce,
                    )

                    if hay_cruce:
                        cruces.append(
                            "%s\n%s - %s" % (
                                other.name or other.id,
                                other_inicio.strftime('%d/%m/%Y %H:%M'),
                                other_fin.strftime('%H:%M'),
                            )
                        )

                if cruces:
                    _logger.error(
                        "🔴 [PLANIFICADOR VALIDACION][CRUCE] ticket=%s tecnico=%s cruces=%s",
                        rec.name,
                        tecnico.name,
                        cruces,
                    )

                    raise ValidationError(
                        _(
                            "El técnico %s ya tiene programación cruzada:\n\n%s"
                        ) % (
                            tecnico.name,
                            "\n\n".join(cruces),
                        )
                    )

            _logger.warning(
                "🟢 [PLANIFICADOR VALIDACION][OK] ticket=%s sin cruces",
                rec.name,
            )

    # ============================================================
    # CREATE / WRITE
    # ============================================================

    @api.model
    def create(self, vals):
        if vals.get('tipo_servicio_id') == 'mantenimiento_preventivo':
            vals.setdefault('duracion_programada_horas', 1.0)

        ticket = super().create(vals)

        if ticket.planificador_linea_id:
            ticket._sync_linea_planificador_desde_ticket()

        return ticket

    def write(self, vals):
        if vals.get('tipo_servicio_id') == 'mantenimiento_preventivo':
            vals.setdefault('duracion_programada_horas', 1.0)

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
                agenda_dt = rec._agenda_to_local(rec.agenda)
                hora_inicio = agenda_dt.hour + agenda_dt.minute / 60.0
                duracion = rec._get_duracion_planificador_ticket()

                vals.update({
                    'fecha_programada': agenda_dt.date(),
                    'hora_inicio': hora_inicio,
                    'hora_fin': hora_inicio + duracion,
                    'duracion_horas': duracion,
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
                agenda_dt = rec._agenda_to_local(rec.agenda)
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
            fecha_base = self._agenda_to_local(self.agenda).date()
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
            agenda_dt = self._agenda_to_local(self.agenda)
            fecha_programada = agenda_dt.date()
            hora_inicio = agenda_dt.hour + agenda_dt.minute / 60.0

        duracion = self._get_duracion_planificador_ticket()

        linea = self.env['mantenimiento.planificador.linea'].create({
            'planificador_id': plan.id,
            'equipo_id': equipo.id,
            'cliente_id': self.partner_id.id if self.partner_id else equipo.cliente_id.id,
            'distrito': equipo.distrito,
            'zona_id': zona.id if zona else False,
            'fecha_ideal': fecha_ideal,
            'fecha_programada': fecha_programada,
            'hora_inicio': hora_inicio,
            'hora_fin': hora_inicio + duracion,
            'tecnico_id': self.responsable.id if self.responsable else False,
            'tecnico_apoyo_ids': [(6, 0, self.tecnico_apoyo_ids.ids)],
            'cantidad_tecnicos': 1 + len(self.tecnico_apoyo_ids),
            'duracion_horas': duracion,
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
                'duracion_programada_horas': linea.duracion_horas or 1.0,
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