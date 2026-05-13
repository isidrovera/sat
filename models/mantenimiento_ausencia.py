# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class MantenimientoTecnicoAusencia(models.Model):
    _name = 'mantenimiento.tecnico.ausencia'
    _description = 'Ausencia / permiso del técnico'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_inicio desc, tecnico_id'

    # ============================================================
    # CAMPOS PRINCIPALES
    # ============================================================

    name = fields.Char(
        string='Referencia',
        default='Nuevo',
        copy=False,
        readonly=True,
        tracking=True,
    )

    tecnico_id = fields.Many2one(
        'res.users',
        string='Técnico',
        required=True,
        tracking=True,
        index=True,
        domain=[('share', '=', False)],
    )

    perfil_id = fields.Many2one(
        'mantenimiento.tecnico.perfil',
        string='Perfil técnico',
        compute='_compute_perfil_id',
        store=True,
        readonly=True,
    )

    tipo = fields.Selection([
        ('permiso', 'Permiso personal'),
        ('vacaciones', 'Vacaciones'),
        ('enfermedad', 'Enfermedad'),
        ('descanso_medico', 'Descanso médico'),
        ('falta', 'Falta / inasistencia'),
        ('capacitacion', 'Capacitación'),
        ('bloqueo_admin', 'Bloqueo administrativo'),
    ], string='Tipo de ausencia', required=True, default='permiso', tracking=True)

    fecha_inicio = fields.Date(
        string='Fecha inicio',
        required=True,
        tracking=True,
        index=True,
        default=fields.Date.context_today,
    )

    fecha_fin = fields.Date(
        string='Fecha fin',
        tracking=True,
        index=True,
        help='Puede quedar vacío solo en enfermedad si aún no se conoce la fecha de retorno.'
    )

    fecha_retorno_real = fields.Date(
        string='Fecha retorno real',
        tracking=True,
        help='Fecha en la que el técnico realmente retornó.'
    )

    dia_completo = fields.Boolean(
        string='Día completo',
        default=True,
        tracking=True,
    )

    hora_inicio = fields.Float(
        string='Hora inicio',
        default=0.0,
        tracking=True,
    )

    hora_fin = fields.Float(
        string='Hora fin',
        default=24.0,
        tracking=True,
    )

    motivo = fields.Text(
        string='Motivo',
        tracking=True,
    )

    adjunto = fields.Binary(
        string='Sustento / documento',
        attachment=True,
    )

    adjunto_filename = fields.Char(
        string='Nombre del archivo'
    )

    estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('pendiente', 'Pendiente de aprobación'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado'),
        ('ausente_activo', 'Ausente activo'),
        ('cerrado', 'Cerrado / Retornó'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', tracking=True, index=True)

    aprobado_por_id = fields.Many2one(
        'res.users',
        string='Aprobado por',
        readonly=True,
        tracking=True,
    )

    fecha_aprobacion = fields.Datetime(
        string='Fecha de aprobación',
        readonly=True,
        tracking=True,
    )

    rechazado_por_id = fields.Many2one(
        'res.users',
        string='Rechazado por',
        readonly=True,
        tracking=True,
    )

    fecha_rechazo = fields.Datetime(
        string='Fecha de rechazo',
        readonly=True,
        tracking=True,
    )

    motivo_rechazo = fields.Text(
        string='Motivo de rechazo',
        tracking=True,
    )

    disponibilidad_id = fields.Many2one(
        'mantenimiento.tecnico.disponibilidad',
        string='Bloqueo de disponibilidad',
        readonly=True,
        copy=False,
    )

    ticket_afectado_ids = fields.Many2many(
        'ticket.alquiler',
        'mantenimiento_ausencia_ticket_rel',
        'ausencia_id',
        'ticket_id',
        string='Tickets afectados',
        readonly=True,
    )

    ticket_afectado_count = fields.Integer(
        string='Tickets afectados',
        compute='_compute_ticket_afectado_count',
        store=False,
    )

    notificar_contabilidad = fields.Boolean(
        string='Notificar a contabilidad',
        default=True,
        tracking=True,
    )

    correo_contabilidad = fields.Char(
        string='Correo contabilidad',
        compute='_compute_correo_contabilidad',
        store=False,
    )

    es_abierta = fields.Boolean(
        string='Ausencia sin fecha fin',
        compute='_compute_es_abierta',
        store=True,
        help='Se activa solo cuando es enfermedad y no tiene fecha fin.'
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
    )

    # ============================================================
    # COMPUTES
    # ============================================================

    @api.depends('tecnico_id')
    def _compute_perfil_id(self):
        Perfil = self.env['mantenimiento.tecnico.perfil']

        for rec in self:
            if rec.tecnico_id:
                perfil = Perfil.search([
                    ('tecnico_id', '=', rec.tecnico_id.id),
                    ('active', '=', True),
                ], limit=1)

                rec.perfil_id = perfil.id if perfil else False
            else:
                rec.perfil_id = False

    @api.depends('ticket_afectado_ids')
    def _compute_ticket_afectado_count(self):
        for rec in self:
            rec.ticket_afectado_count = len(rec.ticket_afectado_ids)

    @api.depends('tipo', 'fecha_fin')
    def _compute_es_abierta(self):
        """
        Solo una enfermedad sin fecha_fin debe considerarse abierta.
        Si el formulario web manda fecha_fin, no debe marcarse como ausencia sin fecha fin.
        """
        for rec in self:
            rec.es_abierta = bool(rec.tipo == 'enfermedad' and not rec.fecha_fin)

    def _compute_correo_contabilidad(self):
        correo = self.env['ir.config_parameter'].sudo().get_param(
            'mantenimiento.correo_contabilidad',
            ''
        )

        for rec in self:
            rec.correo_contabilidad = correo

    # ============================================================
    # ONCHANGE
    # ============================================================

    @api.onchange('tipo')
    def _onchange_tipo(self):
        """
        No forzamos fecha_fin = fecha_inicio si ya existe fecha_fin.
        Esto permite que el formulario web respete el campo "Hasta".
        """
        for rec in self:
            if rec.tipo in ('permiso', 'falta'):
                rec.dia_completo = True
                rec.hora_inicio = 0.0
                rec.hora_fin = 24.0

                if rec.fecha_inicio and not rec.fecha_fin:
                    rec.fecha_fin = rec.fecha_inicio

            elif rec.tipo == 'vacaciones':
                rec.dia_completo = True
                rec.hora_inicio = 0.0
                rec.hora_fin = 24.0

                if rec.fecha_inicio and not rec.fecha_fin:
                    rec.fecha_fin = rec.fecha_inicio

            elif rec.tipo == 'enfermedad':
                rec.dia_completo = True
                rec.hora_inicio = 0.0
                rec.hora_fin = 24.0
                # Enfermedad puede quedar sin fecha_fin.

            elif rec.tipo == 'descanso_medico':
                rec.dia_completo = True
                rec.hora_inicio = 0.0
                rec.hora_fin = 24.0

                if rec.fecha_inicio and not rec.fecha_fin:
                    rec.fecha_fin = rec.fecha_inicio

            elif rec.tipo == 'capacitacion':
                rec.dia_completo = False
                if not rec.hora_inicio:
                    rec.hora_inicio = 8.0
                if not rec.hora_fin or rec.hora_fin == 24.0:
                    rec.hora_fin = 13.0

                if rec.fecha_inicio and not rec.fecha_fin:
                    rec.fecha_fin = rec.fecha_inicio

            elif rec.tipo == 'bloqueo_admin':
                if rec.fecha_inicio and not rec.fecha_fin:
                    rec.fecha_fin = rec.fecha_inicio

    @api.onchange('fecha_inicio')
    def _onchange_fecha_inicio(self):
        """
        Si no hay fecha_fin, la completamos.
        Si fecha_fin es menor, la corregimos.
        No pisamos una fecha_fin válida enviada por el usuario.
        """
        for rec in self:
            if rec.fecha_inicio:
                if not rec.fecha_fin and rec.tipo != 'enfermedad':
                    rec.fecha_fin = rec.fecha_inicio

                if rec.fecha_fin and rec.fecha_fin < rec.fecha_inicio:
                    rec.fecha_fin = rec.fecha_inicio

    @api.onchange('dia_completo')
    def _onchange_dia_completo(self):
        for rec in self:
            if rec.dia_completo:
                rec.hora_inicio = 0.0
                rec.hora_fin = 24.0
            else:
                if not rec.hora_inicio:
                    rec.hora_inicio = 8.0
                if not rec.hora_fin or rec.hora_fin == 24.0:
                    rec.hora_fin = 17.0

    # ============================================================
    # NORMALIZACIÓN
    # ============================================================

    @api.model
    def _normalize_vals(self, vals):
        """
        Normaliza datos recibidos desde backend o formulario web.
        Evita que fecha_fin quede vacía cuando no corresponde.
        Respeta fecha_fin si el usuario marcó "hasta".
        """
        vals = dict(vals or {})

        tipo = vals.get('tipo')
        fecha_inicio = vals.get('fecha_inicio')
        fecha_fin = vals.get('fecha_fin')

        # Si no viene tipo en vals, no podemos inferir aquí.
        # create/write completan usando el registro si corresponde.
        if fecha_inicio and not fecha_fin and tipo != 'enfermedad':
            vals['fecha_fin'] = fecha_inicio

        if vals.get('dia_completo') in (True, 'true', '1', 1):
            vals['hora_inicio'] = 0.0
            vals['hora_fin'] = 24.0

        return vals

    def _normalize_record_dates(self):
        """
        Corrige registros ya creados o actualizados:
        - Si no es enfermedad y no tiene fecha_fin, asigna fecha_inicio.
        - Si fecha_fin < fecha_inicio, corrige a fecha_inicio.
        - Si es día completo, normaliza horas.
        """
        for rec in self:
            vals = {}

            if rec.fecha_inicio:
                if rec.tipo != 'enfermedad' and not rec.fecha_fin:
                    vals['fecha_fin'] = rec.fecha_inicio

                if rec.fecha_fin and rec.fecha_fin < rec.fecha_inicio:
                    vals['fecha_fin'] = rec.fecha_inicio

            if rec.dia_completo and (rec.hora_inicio != 0.0 or rec.hora_fin != 24.0):
                vals['hora_inicio'] = 0.0
                vals['hora_fin'] = 24.0

            if vals:
                _logger.info(
                    "[Ausencias] Normalizando registro %s con valores: %s",
                    rec.name,
                    vals
                )
                super(MantenimientoTecnicoAusencia, rec).write(vals)

    # ============================================================
    # VALIDACIONES
    # ============================================================

    @api.constrains('fecha_inicio', 'fecha_fin', 'tipo')
    def _check_fechas(self):
        for rec in self:
            if not rec.fecha_inicio:
                raise ValidationError(_("Debe ingresar la fecha de inicio."))

            if rec.tipo != 'enfermedad' and not rec.fecha_fin:
                raise ValidationError(_("Debe ingresar la fecha fin."))

            if rec.fecha_fin and rec.fecha_fin < rec.fecha_inicio:
                raise ValidationError(_("La fecha fin no puede ser menor que la fecha inicio."))

    @api.constrains('hora_inicio', 'hora_fin', 'dia_completo')
    def _check_horas(self):
        for rec in self:
            if rec.dia_completo:
                continue

            if rec.hora_inicio < 0 or rec.hora_inicio > 24:
                raise ValidationError(_("La hora inicio debe estar entre 0 y 24."))

            if rec.hora_fin < 0 or rec.hora_fin > 24:
                raise ValidationError(_("La hora fin debe estar entre 0 y 24."))

            if rec.hora_fin <= rec.hora_inicio:
                raise ValidationError(_("La hora fin debe ser mayor que la hora inicio."))

    @api.constrains('tecnico_id', 'fecha_inicio', 'fecha_fin', 'estado')
    def _check_solapamiento_ausencias(self):
        for rec in self:
            if not rec.tecnico_id or not rec.fecha_inicio:
                continue

            if rec.estado in ('rechazado', 'cancelado', 'cerrado'):
                continue

            fecha_fin = rec.fecha_fin or rec.fecha_inicio + timedelta(days=365)

            domain = [
                ('id', '!=', rec.id),
                ('tecnico_id', '=', rec.tecnico_id.id),
                ('estado', 'not in', ['rechazado', 'cancelado', 'cerrado']),
                ('fecha_inicio', '<=', fecha_fin),
                '|',
                ('fecha_fin', '=', False),
                ('fecha_fin', '>=', rec.fecha_inicio),
            ]

            existe = self.search_count(domain)

            if existe:
                raise ValidationError(
                    _("Ya existe una ausencia activa o pendiente para este técnico en ese rango.")
                )

    # ============================================================
    # CREATE / WRITE
    # ============================================================

    @api.model
    def create(self, vals):
        _logger.info("[Ausencias] === CREANDO AUSENCIA ===")
        _logger.info("[Ausencias] Valores recibidos: %s", vals)

        vals = self._normalize_vals(vals)

        if vals.get('name', 'Nuevo') == 'Nuevo':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'mantenimiento.tecnico.ausencia'
            ) or 'AUS/NUEVO'

        rec = super().create(vals)

        rec._normalize_record_dates()

        _logger.info("[Ausencias] Ausencia creada: %s ID=%s", rec.name, rec.id)
        _logger.info("[Ausencias] Técnico: %s", rec.tecnico_id.name)
        _logger.info("[Ausencias] Tipo: %s", rec.tipo)
        _logger.info("[Ausencias] Fechas: %s - %s", rec.fecha_inicio, rec.fecha_fin)
        _logger.info("[Ausencias] Estado: %s", rec.estado)

        # Enfermedad y falta pueden bloquear inmediatamente.
        # Si quieres que falta también pase por aprobación, quita 'falta' de esta condición.
        if rec.tipo in ('enfermedad', 'falta') and rec.estado == 'borrador':
            rec.action_reportar_ausencia_inmediata()

        return rec

    def write(self, vals):
        _logger.info("[Ausencias] === ACTUALIZANDO AUSENCIA ===")
        _logger.info("[Ausencias] Registros: %s", self.ids)
        _logger.info("[Ausencias] Valores recibidos: %s", vals)

        vals = self._normalize_vals(vals)

        res = super().write(vals)

        self._normalize_record_dates()

        return res

    # ============================================================
    # HELPERS OPERATIVOS
    # ============================================================

    def _get_fecha_fin_operativa(self):
        self.ensure_one()

        if self.fecha_fin:
            return self.fecha_fin

        # Si es enfermedad abierta, bloqueamos una ventana amplia.
        return self.fecha_inicio + timedelta(days=365)

    def _iter_fechas(self):
        self.ensure_one()

        fecha = self.fecha_inicio
        fecha_fin = self._get_fecha_fin_operativa()

        while fecha <= fecha_fin:
            yield fecha
            fecha += timedelta(days=1)

    def _buscar_tickets_afectados(self):
        self.ensure_one()

        Ticket = self.env['ticket.alquiler']

        fecha_inicio_dt = datetime.combine(
            self.fecha_inicio,
            datetime.min.time()
        )

        fecha_fin = self._get_fecha_fin_operativa()
        fecha_fin_dt = datetime.combine(
            fecha_fin + timedelta(days=1),
            datetime.min.time()
        )

        tickets = Ticket.search([
            ('responsable', '=', self.tecnico_id.id),
            ('agenda', '>=', fecha_inicio_dt),
            ('agenda', '<', fecha_fin_dt),
            ('estado', 'not in', ['finalizado']),
        ])

        _logger.info(
            "[Ausencias] Tickets afectados para %s: %s",
            self.name,
            tickets.ids
        )

        return tickets

    def _crear_bloqueo_disponibilidad(self):
        self.ensure_one()

        _logger.info("[Ausencias] Creando bloqueo de disponibilidad para %s", self.name)

        if not self.perfil_id:
            raise UserError(
                _("El técnico %s no tiene perfil operativo de mantenimiento.")
                % self.tecnico_id.name
            )

        Disponibilidad = self.env['mantenimiento.tecnico.disponibilidad']

        primera_disponibilidad = False

        for fecha in self._iter_fechas():
            existente = Disponibilidad.search([
                ('perfil_id', '=', self.perfil_id.id),
                ('fecha', '=', fecha),
                ('estado', '=', 'aprobado'),
            ], limit=1)

            vals = {
                'perfil_id': self.perfil_id.id,
                'fecha': fecha,
                'disponible': False,
                'dia_completo': self.dia_completo,
                'hora_inicio': self.hora_inicio if not self.dia_completo else 0.0,
                'hora_fin': self.hora_fin if not self.dia_completo else 24.0,
                'capacidad': 0,
                'tipo': 'bloqueo',
                'estado': 'aprobado',
                'motivo': _(
                    "Bloqueo generado por ausencia %s: %s"
                ) % (
                    self.name,
                    dict(self._fields['tipo'].selection).get(self.tipo)
                ),
            }

            if existente:
                existente.write(vals)
                bloqueo = existente
                _logger.info(
                    "[Ausencias] Bloqueo actualizado fecha=%s ID=%s",
                    fecha,
                    bloqueo.id
                )
            else:
                bloqueo = Disponibilidad.create(vals)
                _logger.info(
                    "[Ausencias] Bloqueo creado fecha=%s ID=%s",
                    fecha,
                    bloqueo.id
                )

            if not primera_disponibilidad:
                primera_disponibilidad = bloqueo

        self.disponibilidad_id = primera_disponibilidad.id if primera_disponibilidad else False

    def _marcar_tickets_afectados(self):
        self.ensure_one()

        tickets = self._buscar_tickets_afectados()
        self.ticket_afectado_ids = [(6, 0, tickets.ids)]

        for ticket in tickets:
            body = _(
                "⚠️ El técnico %s no estará disponible por %s (%s - %s). "
                "Este ticket requiere revisión o reasignación."
            ) % (
                self.tecnico_id.name,
                dict(self._fields['tipo'].selection).get(self.tipo),
                self.fecha_inicio.strftime('%d/%m/%Y'),
                self.fecha_fin.strftime('%d/%m/%Y') if self.fecha_fin else 'sin fecha fin',
            )

            ticket.message_post(body=body, message_type='notification')

        return tickets

    # ============================================================
    # CORREOS
    # ============================================================

    def _send_mail_template_safe(self, xmlid, context_values=None, log_name=None):
        self.ensure_one()

        context_values = context_values or {}
        log_name = log_name or xmlid

        _logger.info("[Ausencias] Preparando envío de correo: %s", log_name)
        _logger.info("[Ausencias] Registro: %s ID=%s", self.name, self.id)

        template = self.env.ref(xmlid, raise_if_not_found=False)

        if not template:
            _logger.warning("[Ausencias] No se encontró la plantilla: %s", xmlid)
            self.message_post(
                body=_("No se encontró la plantilla de correo: %s") % xmlid,
                message_type='notification'
            )
            return False

        try:
            mail_id = template.with_context(**context_values).send_mail(
                self.id,
                force_send=True,
                raise_exception=False
            )

            _logger.info(
                "[Ausencias] Correo procesado correctamente. Template=%s MailID=%s",
                xmlid,
                mail_id
            )

            return True

        except Exception as e:
            _logger.error(
                "[Ausencias] Error enviando correo %s para %s: %s",
                xmlid,
                self.name,
                str(e),
                exc_info=True
            )

            self.message_post(
                body=_("No se pudo enviar el correo %s. Error: %s") % (xmlid, str(e)),
                message_type='notification'
            )

            return False

    def _get_correo_jefe_area(self):
        self.ensure_one()

        correo_param = self.env['ir.config_parameter'].sudo().get_param(
            'mantenimiento.correo_jefe_area',
            ''
        )

        if correo_param:
            _logger.info("[Ausencias] Correo jefe desde parámetro: %s", correo_param)
            return correo_param

        grupo = self.env.ref('sat.sat_jefes_group_user', raise_if_not_found=False)

        if grupo:
            correos = []

            for user in grupo.users:
                email = user.email or user.partner_id.email
                if email:
                    correos.append(email)

            if correos:
                correos_str = ','.join(correos)
                _logger.info("[Ausencias] Correos jefe desde grupo: %s", correos_str)
                return correos_str

        _logger.warning(
            "[Ausencias] No se encontró correo de jefe de área. "
            "Configure mantenimiento.correo_jefe_area o agregue usuarios al grupo Jefes de Área."
        )

        return False

    def _notificar_jefe_area(self):
        self.ensure_one()

        correo_jefe = self._get_correo_jefe_area()

        if not correo_jefe:
            self.message_post(
                body=_(
                    "No se envió correo al jefe de área porque no hay correo configurado. "
                    "Configure el parámetro mantenimiento.correo_jefe_area o agregue usuarios al grupo Jefes de Área."
                ),
                message_type='notification'
            )
            return False

        return self._send_mail_template_safe(
            'sat.email_template_leave_request',
            context_values={
                'correo_jefe_area': correo_jefe,
            },
            log_name='Solicitud pendiente para jefe de área'
        )

    def _notificar_contabilidad(self):
        self.ensure_one()

        if not self.notificar_contabilidad:
            _logger.info("[Ausencias] No se notifica contabilidad por configuración del registro.")
            return False

        correo = self.correo_contabilidad

        if not correo:
            _logger.warning(
                "[Ausencias] No se configuró mantenimiento.correo_contabilidad"
            )
            self.message_post(
                body=_(
                    "No se envió correo a contabilidad porque no está configurado "
                    "el parámetro mantenimiento.correo_contabilidad."
                ),
                message_type='notification'
            )
            return False

        return self._send_mail_template_safe(
            'sat.mail_template_mantenimiento_ausencia_contabilidad',
            context_values={
                'correo_contabilidad': correo,
            },
            log_name='Permiso aprobado para contabilidad / gerencia'
        )

    def _notificar_trabajador_aprobado(self):
        self.ensure_one()

        email = self.tecnico_id.email or self.tecnico_id.partner_id.email

        if not email:
            _logger.warning(
                "[Ausencias] Técnico %s no tiene correo configurado",
                self.tecnico_id.name
            )
            self.message_post(
                body=_("No se pudo notificar al trabajador porque no tiene correo configurado."),
                message_type='notification'
            )
            return False

        return self._send_mail_template_safe(
            'sat.email_template_mantenimiento_ausencia_empleado_aprobado',
            log_name='Solicitud aprobada para trabajador'
        )

    def _notificar_trabajador_rechazado(self):
        self.ensure_one()

        email = self.tecnico_id.email or self.tecnico_id.partner_id.email

        if not email:
            _logger.warning(
                "[Ausencias] Técnico %s no tiene correo configurado",
                self.tecnico_id.name
            )
            self.message_post(
                body=_("No se pudo notificar al trabajador porque no tiene correo configurado."),
                message_type='notification'
            )
            return False

        return self._send_mail_template_safe(
            'sat.email_template_mantenimiento_ausencia_empleado_rechazado',
            log_name='Solicitud rechazada para trabajador'
        )

    # ============================================================
    # ACCIONES DE FLUJO
    # ============================================================

    def action_enviar_aprobacion(self):
        for rec in self:
            if rec.estado not in ('borrador', 'rechazado'):
                raise UserError(_("Solo se pueden enviar a aprobación solicitudes en borrador o rechazadas."))

            rec._normalize_record_dates()

            rec.write({'estado': 'pendiente'})

            rec.message_post(
                body=_("Solicitud enviada para aprobación."),
                message_type='notification'
            )

            rec._notificar_jefe_area()

    def action_aprobar(self):
        for rec in self:
            if rec.estado not in ('pendiente', 'borrador'):
                raise UserError(_("Solo se pueden aprobar solicitudes pendientes o en borrador."))

            rec._normalize_record_dates()

            rec.write({
                'estado': 'aprobado',
                'aprobado_por_id': self.env.user.id,
                'fecha_aprobacion': fields.Datetime.now(),
            })

            rec._crear_bloqueo_disponibilidad()
            tickets = rec._marcar_tickets_afectados()

            rec._notificar_contabilidad()
            rec._notificar_trabajador_aprobado()

            rec.message_post(
                body=_(
                    "✅ Ausencia aprobada. Técnico bloqueado en agenda. "
                    "Tickets afectados: %s."
                ) % len(tickets),
                message_type='notification'
            )

    def action_reportar_ausencia_inmediata(self):
        """
        Para enfermedad o falta.
        Bloquea inmediatamente sin esperar aprobación porque el técnico no asistirá.
        """
        for rec in self:
            if rec.tipo not in ('enfermedad', 'falta'):
                raise UserError(_("Esta acción solo aplica para enfermedad o falta."))

            rec._normalize_record_dates()

            nuevo_estado = 'ausente_activo' if rec.tipo == 'enfermedad' else 'aprobado'

            rec.write({
                'estado': nuevo_estado,
                'aprobado_por_id': self.env.user.id,
                'fecha_aprobacion': fields.Datetime.now(),
            })

            rec._crear_bloqueo_disponibilidad()
            tickets = rec._marcar_tickets_afectados()

            rec._notificar_contabilidad()
            rec._notificar_trabajador_aprobado()

            rec.message_post(
                body=_(
                    "🚫 Ausencia reportada y técnico bloqueado automáticamente. "
                    "Tickets afectados: %s."
                ) % len(tickets),
                message_type='notification'
            )

    def action_rechazar(self):
        for rec in self:
            if rec.estado not in ('pendiente', 'borrador'):
                raise UserError(_("Solo se pueden rechazar solicitudes pendientes o en borrador."))

            rec.write({
                'estado': 'rechazado',
                'rechazado_por_id': self.env.user.id,
                'fecha_rechazo': fields.Datetime.now(),
            })

            rec._notificar_trabajador_rechazado()

            rec.message_post(
                body=_("❌ Solicitud rechazada."),
                message_type='notification'
            )

    def action_cancelar(self):
        for rec in self:
            rec.write({'estado': 'cancelado'})
            rec.message_post(
                body=_("Solicitud cancelada."),
                message_type='notification'
            )

    def action_cerrar_retorno(self):
        for rec in self:
            if rec.estado not in ('ausente_activo', 'aprobado'):
                raise UserError(_("Solo se puede cerrar una ausencia activa o aprobada."))

            if not rec.fecha_retorno_real:
                rec.fecha_retorno_real = fields.Date.context_today(rec)

            rec.write({
                'estado': 'cerrado',
                'fecha_fin': rec.fecha_retorno_real,
            })

            rec.message_post(
                body=_(
                    "✅ Ausencia cerrada. Retorno registrado el %s."
                ) % rec.fecha_retorno_real.strftime('%d/%m/%Y'),
                message_type='notification'
            )

    def action_ver_tickets_afectados(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Tickets afectados'),
            'res_model': 'ticket.alquiler',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.ticket_afectado_ids.ids)],
        }