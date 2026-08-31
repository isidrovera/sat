# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, time, timedelta


class MantenimientoTecnicoPerfil(models.Model):
    _name = 'mantenimiento.tecnico.perfil'
    _description = 'Perfil operativo del técnico'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'tecnico_id'

    tecnico_id = fields.Many2one(
        'res.users',
        string='Técnico',
        required=True,
        index=True,
        tracking=True,
        domain=[('share', '=', False)],
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
        tracking=True,
    )

    zona_preferida_ids = fields.Many2many(
        'mantenimiento.zona',
        'mantenimiento_tecnico_zona_rel',
        'perfil_id',
        'zona_id',
        string='Zonas preferidas',
        tracking=True,
        help='Zonas donde normalmente trabaja este técnico.'
    )

    capacidad_diaria = fields.Integer(
        string='Capacidad diaria',
        default=4,
        tracking=True,
        help='Cantidad referencial de mantenimientos por día completo.'
    )

    capacidad_sabado = fields.Integer(
        string='Capacidad sábado',
        default=2,
        tracking=True,
        help='Cantidad referencial de mantenimientos en sábado.'
    )

    duracion_servicio_horas = fields.Float(
        string='Duración estándar por servicio',
        default=2.0,
        tracking=True,
        help='Duración estimada estándar de un mantenimiento preventivo.'
    )
    tipo_operativo = fields.Selection([
        ('taller', 'Técnico fijo de taller'),
        ('servicios', 'Técnico exclusivo de servicios / alquiler'),
        ('mixto', 'Técnico mixto / servicios eventuales'),
    ], string='Tipo operativo aplicado', default='mixto', tracking=True)

    meta_base_taller = fields.Float(
        string='Meta base taller',
        default=50.0,
        tracking=True
    )

    meta_base_servicios = fields.Float(
        string='Meta base servicios',
        default=40.0,
        tracking=True
    )
    trabaja_lunes = fields.Boolean(string='Lunes', default=True)
    trabaja_martes = fields.Boolean(string='Martes', default=True)
    trabaja_miercoles = fields.Boolean(string='Miércoles', default=True)
    trabaja_jueves = fields.Boolean(string='Jueves', default=True)
    trabaja_viernes = fields.Boolean(string='Viernes', default=True)
    trabaja_sabado = fields.Boolean(string='Sábado', default=True)
    trabaja_domingo = fields.Boolean(string='Domingo', default=False)

    hora_inicio_lunes = fields.Float(string='Inicio lunes', default=8.5)
    hora_fin_lunes = fields.Float(string='Fin lunes', default=18.5)

    hora_inicio_martes = fields.Float(string='Inicio martes', default=8.5)
    hora_fin_martes = fields.Float(string='Fin martes', default=18.5)

    hora_inicio_miercoles = fields.Float(string='Inicio miércoles', default=8.5)
    hora_fin_miercoles = fields.Float(string='Fin miércoles', default=18.5)

    hora_inicio_jueves = fields.Float(string='Inicio jueves', default=8.5)
    hora_fin_jueves = fields.Float(string='Fin jueves', default=18.0)

    hora_inicio_viernes = fields.Float(string='Inicio viernes', default=8.5)
    hora_fin_viernes = fields.Float(string='Fin viernes', default=18.0)

    hora_inicio_sabado = fields.Float(string='Inicio sábado', default=9.0)
    hora_fin_sabado = fields.Float(string='Fin sábado', default=13.0)

    hora_inicio_domingo = fields.Float(string='Inicio domingo', default=0.0)
    hora_fin_domingo = fields.Float(string='Fin domingo', default=0.0)

    disponibilidad_ids = fields.One2many(
        'mantenimiento.tecnico.disponibilidad',
        'perfil_id',
        string='Disponibilidades / excepciones'
    )
    meta_base_taller = fields.Float(
        string='Meta base de reparaciones',
        default=60.0,
        required=True,
        tracking=True,
        help='Meta mensual del técnico con disponibilidad completa.'
    )
    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True
    )

    @api.depends('tecnico_id')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.tecnico_id.name if rec.tecnico_id else 'Perfil técnico'

    @api.constrains('tecnico_id')
    def _check_tecnico_unique(self):
        for rec in self:
            if not rec.tecnico_id:
                continue

            existe = self.search_count([
                ('id', '!=', rec.id),
                ('tecnico_id', '=', rec.tecnico_id.id),
            ])

            if existe:
                raise ValidationError(
                    _("Ya existe un perfil de mantenimiento para el técnico %s.")
                    % rec.tecnico_id.name
                )

    @api.constrains(
        'capacidad_diaria',
        'capacidad_sabado',
        'duracion_servicio_horas',
        'hora_inicio_lunes', 'hora_fin_lunes',
        'hora_inicio_martes', 'hora_fin_martes',
        'hora_inicio_miercoles', 'hora_fin_miercoles',
        'hora_inicio_jueves', 'hora_fin_jueves',
        'hora_inicio_viernes', 'hora_fin_viernes',
        'hora_inicio_sabado', 'hora_fin_sabado',
        'hora_inicio_domingo', 'hora_fin_domingo',
    )
    def _check_valores_validos(self):
        for rec in self:
            if rec.capacidad_diaria < 0:
                raise ValidationError(_("La capacidad diaria no puede ser negativa."))

            if rec.capacidad_sabado < 0:
                raise ValidationError(_("La capacidad de sábado no puede ser negativa."))

            if rec.duracion_servicio_horas <= 0:
                raise ValidationError(_("La duración estándar debe ser mayor a cero."))

            pares = [
                ('lunes', rec.hora_inicio_lunes, rec.hora_fin_lunes, rec.trabaja_lunes),
                ('martes', rec.hora_inicio_martes, rec.hora_fin_martes, rec.trabaja_martes),
                ('miércoles', rec.hora_inicio_miercoles, rec.hora_fin_miercoles, rec.trabaja_miercoles),
                ('jueves', rec.hora_inicio_jueves, rec.hora_fin_jueves, rec.trabaja_jueves),
                ('viernes', rec.hora_inicio_viernes, rec.hora_fin_viernes, rec.trabaja_viernes),
                ('sábado', rec.hora_inicio_sabado, rec.hora_fin_sabado, rec.trabaja_sabado),
                ('domingo', rec.hora_inicio_domingo, rec.hora_fin_domingo, rec.trabaja_domingo),
            ]

            for dia, inicio, fin, trabaja in pares:
                if not trabaja:
                    continue

                if inicio < 0 or inicio > 24 or fin < 0 or fin > 24:
                    raise ValidationError(
                        _("Las horas de %s deben estar entre 0 y 24.") % dia
                    )

                if fin <= inicio:
                    raise ValidationError(
                        _("La hora fin de %s debe ser mayor a la hora inicio.") % dia
                    )

    def _get_horario_base_fecha(self, fecha):
        self.ensure_one()

        if isinstance(fecha, datetime):
            fecha = fecha.date()

        weekday = fecha.weekday()

        if weekday == 0:
            return self.trabaja_lunes, self.hora_inicio_lunes, self.hora_fin_lunes
        if weekday == 1:
            return self.trabaja_martes, self.hora_inicio_martes, self.hora_fin_martes
        if weekday == 2:
            return self.trabaja_miercoles, self.hora_inicio_miercoles, self.hora_fin_miercoles
        if weekday == 3:
            return self.trabaja_jueves, self.hora_inicio_jueves, self.hora_fin_jueves
        if weekday == 4:
            return self.trabaja_viernes, self.hora_inicio_viernes, self.hora_fin_viernes
        if weekday == 5:
            return self.trabaja_sabado, self.hora_inicio_sabado, self.hora_fin_sabado

        return self.trabaja_domingo, self.hora_inicio_domingo, self.hora_fin_domingo

    def get_disponibilidad_fecha(self, fecha):
        """
        Retorna la disponibilidad final del técnico para una fecha.

        Resultado:
        {
            'disponible': True/False,
            'hora_inicio': 8.0,
            'hora_fin': 18.0,
            'capacidad': 4,
            'permite_asignaciones_multiples': True/False,
            'origen': 'base' / 'excepcion' / 'bloqueado'
        }
        """
        self.ensure_one()

        if isinstance(fecha, datetime):
            fecha = fecha.date()

        trabaja, hora_inicio, hora_fin = self._get_horario_base_fecha(fecha)

        capacidad = self.capacidad_sabado if fecha.weekday() == 5 else self.capacidad_diaria

        disponible = bool(trabaja and capacidad > 0)
        permite_asignaciones_multiples = False
        origen = 'base'

        excepcion = self.env['mantenimiento.tecnico.disponibilidad'].search([
            ('perfil_id', '=', self.id),
            ('fecha', '=', fecha),
            ('estado', '=', 'aprobado'),
        ], order='sequence desc, id desc', limit=1)

        if excepcion:
            origen = 'excepcion'
            disponible = excepcion.disponible
            hora_inicio = excepcion.hora_inicio
            hora_fin = excepcion.hora_fin
            capacidad = excepcion.capacidad
            permite_asignaciones_multiples = bool(excepcion.permite_asignaciones_multiples)

            if not excepcion.disponible:
                origen = 'bloqueado'

        return {
            'disponible': disponible,
            'hora_inicio': hora_inicio,
            'hora_fin': hora_fin,
            'capacidad': capacidad,
            'permite_asignaciones_multiples': permite_asignaciones_multiples,
            'origen': origen,
        }

    def action_ver_disponibilidades(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Disponibilidad de %s') % self.tecnico_id.name,
            'res_model': 'mantenimiento.tecnico.disponibilidad',
            'view_mode': 'list,form,calendar',
            'domain': [('perfil_id', '=', self.id)],
            'context': {
                'default_perfil_id': self.id,
                'default_tecnico_id': self.tecnico_id.id,
            }
        }


class MantenimientoTecnicoDisponibilidad(models.Model):
    _name = 'mantenimiento.tecnico.disponibilidad'
    _description = 'Disponibilidad excepcional del técnico'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc, tecnico_id'

    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True
    )

    sequence = fields.Integer(
        string='Prioridad',
        default=10,
        help='Si hay más de una regla para el mismo día, se toma la de mayor prioridad.'
    )

    perfil_id = fields.Many2one(
        'mantenimiento.tecnico.perfil',
        string='Perfil técnico',
        required=True,
        ondelete='cascade',
        tracking=True,
        index=True
    )

    tecnico_id = fields.Many2one(
        'res.users',
        string='Técnico',
        related='perfil_id.tecnico_id',
        store=True,
        readonly=True,
        index=True
    )

    fecha = fields.Date(
        string='Fecha',
        required=True,
        tracking=True,
        index=True
    )

    disponible = fields.Boolean(
        string='Disponible',
        default=True,
        tracking=True,
        help='Si está desactivado, el técnico no estará disponible ese día.'
    )

    dia_completo = fields.Boolean(
        string='Día completo',
        default=True,
        tracking=True
    )

    hora_inicio = fields.Float(
        string='Hora inicio',
        default=8.0,
        tracking=True
    )

    hora_fin = fields.Float(
        string='Hora fin',
        default=18.0,
        tracking=True
    )

    capacidad = fields.Integer(
        string='Capacidad',
        default=4,
        tracking=True,
        help='Cantidad máxima de servicios que puede atender en esta fecha.'
    )

    permite_asignaciones_multiples = fields.Boolean(
        string='Permitir asignaciones múltiples este día',
        default=False,
        tracking=True,
        help=(
            'Si está activo, el planificador podrá asignar varias órdenes al técnico '
            'en esta misma fecha, incluso con el mismo horario, sin validar capacidad '
            'ni cruces de horario. Solo aplica a esta disponibilidad aprobada.'
        )
    )

    tipo = fields.Selection([
        ('normal', 'Disponibilidad especial'),
        ('sabado_extra', 'Sábado excepcional'),
        ('bloqueo', 'Bloqueo manual'),
        ('capacitacion', 'Capacitación'),
        ('apoyo', 'Apoyo especial'),
    ], string='Tipo', default='normal', tracking=True)

    estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('pendiente', 'Pendiente de aprobación'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', tracking=True)

    motivo = fields.Text(
        string='Motivo / Nota'
    )

    aprobado_por_id = fields.Many2one(
        'res.users',
        string='Aprobado por',
        readonly=True
    )

    fecha_aprobacion = fields.Datetime(
        string='Fecha de aprobación',
        readonly=True
    )

    @api.depends('tecnico_id', 'fecha', 'disponible', 'hora_inicio', 'hora_fin')
    def _compute_name(self):
        for rec in self:
            tecnico = rec.tecnico_id.name if rec.tecnico_id else 'Técnico'
            fecha = rec.fecha.strftime('%d/%m/%Y') if rec.fecha else 'Sin fecha'
            estado = 'Disponible' if rec.disponible else 'No disponible'
            rec.name = f"{tecnico} - {fecha} - {estado}"

    @api.onchange('dia_completo', 'disponible')
    def _onchange_dia_completo(self):
        for rec in self:
            if rec.dia_completo and not rec.disponible:
                rec.hora_inicio = 0.0
                rec.hora_fin = 24.0
                rec.capacidad = 0
                rec.permite_asignaciones_multiples = False

    @api.constrains('fecha', 'perfil_id', 'estado')
    def _check_fecha_perfil_aprobado_unico(self):
        for rec in self:
            if rec.estado != 'aprobado':
                continue

            existe = self.search_count([
                ('id', '!=', rec.id),
                ('perfil_id', '=', rec.perfil_id.id),
                ('fecha', '=', rec.fecha),
                ('estado', '=', 'aprobado'),
            ])

            if existe:
                raise ValidationError(
                    _("Ya existe una disponibilidad aprobada para este técnico en esa fecha.")
                )

    @api.constrains('hora_inicio', 'hora_fin', 'capacidad', 'disponible', 'permite_asignaciones_multiples')
    def _check_horas_y_capacidad(self):
        for rec in self:
            if rec.hora_inicio < 0 or rec.hora_inicio > 24:
                raise ValidationError(_("La hora de inicio debe estar entre 0 y 24."))

            if rec.hora_fin < 0 or rec.hora_fin > 24:
                raise ValidationError(_("La hora de fin debe estar entre 0 y 24."))

            if rec.disponible and rec.hora_fin <= rec.hora_inicio:
                raise ValidationError(_("La hora fin debe ser mayor a la hora inicio."))

            if rec.capacidad < 0:
                raise ValidationError(_("La capacidad no puede ser negativa."))

            if not rec.disponible and rec.capacidad != 0:
                raise ValidationError(
                    _("Si el técnico no está disponible, la capacidad debe ser 0.")
                )

            if not rec.disponible and rec.permite_asignaciones_multiples:
                raise ValidationError(
                    _("No puede permitir asignaciones múltiples si el técnico no está disponible.")
                )

    def action_enviar_aprobacion(self):
        for rec in self:
            rec.estado = 'pendiente'
            rec.message_post(
                body=_("Disponibilidad enviada para aprobación."),
                message_type='notification'
            )

    def action_aprobar(self):
        for rec in self:
            rec.write({
                'estado': 'aprobado',
                'aprobado_por_id': self.env.user.id,
                'fecha_aprobacion': fields.Datetime.now(),
            })

            rec.message_post(
                body=_("Disponibilidad aprobada."),
                message_type='notification'
            )

    def action_rechazar(self):
        for rec in self:
            rec.write({
                'estado': 'rechazado',
            })

            rec.message_post(
                body=_("Disponibilidad rechazada."),
                message_type='notification'
            )

    def action_cancelar(self):
        for rec in self:
            rec.write({
                'estado': 'cancelado',
            })

            rec.message_post(
                body=_("Disponibilidad cancelada."),
                message_type='notification'
            )