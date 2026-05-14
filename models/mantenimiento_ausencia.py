# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta
import logging
import requests
import json
import re

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
        for rec in self:
            rec.es_abierta = bool(rec.tipo == 'enfermedad' and not rec.fecha_fin)

    # ============================================================
    # ONCHANGE
    # ============================================================

    @api.onchange('tipo')
    def _onchange_tipo(self):
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
        vals = dict(vals or {})

        tipo = vals.get('tipo')
        fecha_inicio = vals.get('fecha_inicio')
        fecha_fin = vals.get('fecha_fin')

        if fecha_inicio and not fecha_fin and tipo != 'enfermedad':
            vals['fecha_fin'] = fecha_inicio

        if vals.get('dia_completo') in (True, 'true', '1', 1):
            vals['hora_inicio'] = 0.0
            vals['hora_fin'] = 24.0

        return vals

    def _normalize_record_dates(self):
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

    def _notificar_jefe_area(self):
        self.ensure_one()

        return self._send_mail_template_safe(
            'sat.email_template_leave_request',
            context_values={},
            log_name='Solicitud pendiente para jefe de área'
        )

    def _notificar_contabilidad(self):
        self.ensure_one()

        if not self.notificar_contabilidad:
            _logger.info("[Ausencias] No se notifica contabilidad por configuración del registro.")
            return False

        return self._send_mail_template_safe(
            'sat.mail_template_mantenimiento_ausencia_contabilidad',
            context_values={},
            log_name='Permiso aprobado para contabilidad / gerencia'
        )

    def _notificar_trabajador_aprobado(self):
        self.ensure_one()

        return self._send_mail_template_safe(
            'sat.email_template_mantenimiento_ausencia_empleado_aprobado',
            context_values={},
            log_name='Solicitud aprobada para trabajador'
        )

    def _notificar_trabajador_rechazado(self):
        self.ensure_one()

        return self._send_mail_template_safe(
            'sat.email_template_mantenimiento_ausencia_empleado_rechazado',
            context_values={},
            log_name='Solicitud rechazada para trabajador'
        )

    # ============================================================
    # WHATSAPP - HELPERS
    # ============================================================

    def _whatsapp_get_api_key(self):
        """
        IMPORTANTE:
        No se coloca la API KEY quemada en el modelo.
        Configúrala en Parámetros del sistema:

            whatsapp.api_key

        Esto evita exponer la clave en el código.
        """
        return self.env['ir.config_parameter'].sudo().get_param('whatsapp.api_key', '').strip()

    def _whatsapp_get_base_url(self):
        """
        Si no configuras nada, usa el endpoint actual que ya tienes funcionando.
        Opcionalmente puedes crear:

            whatsapp.base_url = https://boot.andessolutioncopiers.com
        """
        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'whatsapp.base_url',
            'https://boot.andessolutioncopiers.com'
        )
        return (base_url or '').rstrip('/')

    def _whatsapp_clean_phone(self, phone):
        if not phone:
            return False

        phone = str(phone).strip()

        if not phone or phone.upper() == 'NA':
            return False

        if '@g.us' in phone:
            return phone

        phone = re.sub(r'[^0-9]', '', phone)

        if not phone:
            return False

        if len(phone) == 9:
            phone = '51%s' % phone

        return phone

    def _whatsapp_get_user_phone(self, user):
        if not user:
            return False

        partner = user.partner_id

        possible_numbers = [
            getattr(user, 'mobile', False),
            getattr(user, 'phone', False),
            partner.mobile if partner else False,
            partner.phone if partner else False,
        ]

        for phone in possible_numbers:
            phone_clean = self._whatsapp_clean_phone(phone)
            if phone_clean:
                return phone_clean

        return False

    def _whatsapp_get_jefes_area_users(self):
        """
        No usa parámetro.
        Toma usuarios del grupo sat.sat_jefes_group_user.
        Si ese grupo no existe o no tiene usuarios, no bloquea el flujo.
        """
        grupo = self.env.ref('sat.sat_jefes_group_user', raise_if_not_found=False)

        if not grupo:
            _logger.warning("[Ausencias][WhatsApp] No existe el grupo sat.sat_jefes_group_user")
            return self.env['res.users']

        users = grupo.users.filtered(lambda u: u.active and not u.share)

        _logger.info(
            "[Ausencias][WhatsApp] Usuarios jefes encontrados: %s",
            users.mapped('name')
        )

        return users

    def _send_whatsapp_message(self, phone, message, file_url=None):
        self.ensure_one()

        phone = self._whatsapp_clean_phone(phone)

        if not phone:
            _logger.warning("[Ausencias][WhatsApp] Teléfono vacío o inválido.")
            return {
                'success': False,
                'error': 'Teléfono vacío o inválido',
            }

        api_key = self._whatsapp_get_api_key()

        if not api_key:
            _logger.warning(
                "[Ausencias][WhatsApp] No se envió mensaje porque falta whatsapp.api_key"
            )
            self.message_post(
                body=_(
                    "No se pudo enviar WhatsApp porque no está configurado "
                    "el parámetro whatsapp.api_key."
                ),
                message_type='notification'
            )
            return {
                'success': False,
                'error': 'Falta whatsapp.api_key',
            }

        base_url = self._whatsapp_get_base_url()

        try:
            if file_url:
                url = '%s/api/send-media' % base_url
                data = {
                    'to': phone,
                    'caption': message,
                    'url': file_url,
                }
            else:
                url = '%s/api/send-message' % base_url
                data = {
                    'to': phone,
                    'message': message,
                }

            headers = {
                'Content-Type': 'application/json',
                'x-api-key': api_key,
            }

            _logger.info("[Ausencias][WhatsApp] Enviando WhatsApp a %s", phone)
            _logger.debug("[Ausencias][WhatsApp] URL: %s", url)
            _logger.debug("[Ausencias][WhatsApp] Payload: %s", data)

            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=30
            )

            _logger.info(
                "[Ausencias][WhatsApp] Status=%s Response=%s",
                response.status_code,
                response.text
            )

            try:
                response_json = response.json()
            except json.JSONDecodeError:
                response_json = {
                    'success': False,
                    'error': 'Respuesta no JSON',
                    'raw': response.text,
                }

            if response.status_code == 200 and response_json.get('success'):
                _logger.info("[Ausencias][WhatsApp] ✅ Mensaje enviado a %s", phone)
                return response_json

            error_msg = response_json.get('error') or response.text or 'Error desconocido'

            _logger.error(
                "[Ausencias][WhatsApp] ❌ Error API WhatsApp para %s: %s",
                phone,
                error_msg
            )

            return {
                'success': False,
                'error': error_msg,
                'response': response_json,
            }

        except requests.exceptions.Timeout:
            error_msg = _("Timeout al enviar WhatsApp a %s") % phone
            _logger.error("[Ausencias][WhatsApp] %s", error_msg)
            return {
                'success': False,
                'error': error_msg,
            }

        except Exception as e:
            _logger.error(
                "[Ausencias][WhatsApp] Error enviando WhatsApp a %s: %s",
                phone,
                str(e),
                exc_info=True
            )
            return {
                'success': False,
                'error': str(e),
            }

    # ============================================================
    # WHATSAPP - MENSAJES
    # ============================================================

    def _format_fecha_whatsapp(self, fecha):
        if not fecha:
            return 'No definida'

        try:
            return fecha.strftime('%d/%m/%Y')
        except Exception:
            return str(fecha)

    def _format_horario_whatsapp(self):
        self.ensure_one()

        if self.dia_completo:
            return 'Día completo'

        return 'Por horas %.2f - %.2f' % (
            self.hora_inicio or 0.0,
            self.hora_fin or 0.0,
        )

    def _get_url_registro(self):
        self.ensure_one()

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        base_url = (base_url or '').rstrip('/')

        if not base_url:
            return ''

        return '%s/web#id=%s&model=mantenimiento.tecnico.ausencia&view_type=form' % (
            base_url,
            self.id,
        )

    def _get_tipo_label(self):
        self.ensure_one()
        return dict(self._fields['tipo'].selection).get(self.tipo) or self.tipo or 'No definido'

    def _get_estado_label(self):
        self.ensure_one()
        return dict(self._fields['estado'].selection).get(self.estado) or self.estado or 'No definido'

    def _build_whatsapp_solicitud_recibida(self):
        self.ensure_one()

        url = self._get_url_registro()

        mensaje = (
            "📌 *NUEVA SOLICITUD DE PERMISO*\n\n"
            "Se recibió una nueva solicitud pendiente de aprobación.\n\n"
            "👤 *Trabajador:* %s\n"
            "🧾 *Referencia:* %s\n"
            "📋 *Tipo:* %s\n"
            "📅 *Inicio:* %s\n"
            "📅 *Fin:* %s\n"
            "🕒 *Jornada:* %s\n"
            "📝 *Motivo:* %s\n"
            "📌 *Estado:* %s\n"
        ) % (
            self.tecnico_id.name or 'No definido',
            self.name or 'No definido',
            self._get_tipo_label(),
            self._format_fecha_whatsapp(self.fecha_inicio),
            self._format_fecha_whatsapp(self.fecha_fin),
            self._format_horario_whatsapp(),
            self.motivo or 'Sin motivo registrado',
            self._get_estado_label(),
        )

        if url:
            mensaje += "\n🔗 Revisar en Odoo:\n%s" % url

        return mensaje

    def _build_whatsapp_aprobado(self):
        self.ensure_one()

        mensaje = (
            "✅ *SOLICITUD DE PERMISO APROBADA*\n\n"
            "Hola *%s*, tu solicitud fue aprobada.\n\n"
            "🧾 *Referencia:* %s\n"
            "📋 *Tipo:* %s\n"
            "📅 *Inicio:* %s\n"
            "📅 *Fin:* %s\n"
            "🕒 *Jornada:* %s\n"
            "👤 *Aprobado por:* %s\n"
        ) % (
            self.tecnico_id.name or 'Trabajador',
            self.name or 'No definido',
            self._get_tipo_label(),
            self._format_fecha_whatsapp(self.fecha_inicio),
            self._format_fecha_whatsapp(self.fecha_fin),
            self._format_horario_whatsapp(),
            self.aprobado_por_id.name or self.env.user.name or 'No definido',
        )

        if self.motivo:
            mensaje += "\n📝 *Motivo:* %s" % self.motivo

        return mensaje

    def _build_whatsapp_rechazado(self):
        self.ensure_one()

        mensaje = (
            "❌ *SOLICITUD DE PERMISO RECHAZADA*\n\n"
            "Hola *%s*, tu solicitud fue rechazada.\n\n"
            "🧾 *Referencia:* %s\n"
            "📋 *Tipo:* %s\n"
            "📅 *Inicio:* %s\n"
            "📅 *Fin:* %s\n"
            "🕒 *Jornada:* %s\n"
            "👤 *Rechazado por:* %s\n"
        ) % (
            self.tecnico_id.name or 'Trabajador',
            self.name or 'No definido',
            self._get_tipo_label(),
            self._format_fecha_whatsapp(self.fecha_inicio),
            self._format_fecha_whatsapp(self.fecha_fin),
            self._format_horario_whatsapp(),
            self.rechazado_por_id.name or self.env.user.name or 'No definido',
        )

        if self.motivo_rechazo:
            mensaje += "\n📝 *Motivo de rechazo:* %s" % self.motivo_rechazo

        return mensaje

    def _whatsapp_notificar_jefes_solicitud(self):
        self.ensure_one()

        users = self._whatsapp_get_jefes_area_users()

        if not users:
            _logger.warning("[Ausencias][WhatsApp] No hay jefes para notificar.")
            self.message_post(
                body=_("No se envió WhatsApp de solicitud porque no hay usuarios en el grupo de jefes."),
                message_type='notification'
            )
            return False

        mensaje = self._build_whatsapp_solicitud_recibida()
        enviados = 0
        errores = []

        for user in users:
            phone = self._whatsapp_get_user_phone(user)

            if not phone:
                _logger.warning(
                    "[Ausencias][WhatsApp] Jefe %s sin teléfono/móvil.",
                    user.name
                )
                errores.append('%s sin teléfono' % user.name)
                continue

            result = self._send_whatsapp_message(phone, mensaje)

            if result.get('success'):
                enviados += 1
            else:
                errores.append('%s: %s' % (user.name, result.get('error')))

        self.message_post(
            body=_(
                "WhatsApp de solicitud enviado a jefes. Enviados: %s. Errores: %s"
            ) % (
                enviados,
                ', '.join(errores) if errores else 'Ninguno',
            ),
            message_type='notification'
        )

        return bool(enviados)

    def _whatsapp_notificar_trabajador_aprobado(self):
        self.ensure_one()

        phone = self._whatsapp_get_user_phone(self.tecnico_id)

        if not phone:
            _logger.warning(
                "[Ausencias][WhatsApp] Técnico %s sin teléfono/móvil.",
                self.tecnico_id.name
            )
            self.message_post(
                body=_("No se envió WhatsApp de aprobación porque el trabajador no tiene teléfono/móvil."),
                message_type='notification'
            )
            return False

        result = self._send_whatsapp_message(
            phone,
            self._build_whatsapp_aprobado()
        )

        if result.get('success'):
            self.message_post(
                body=_("WhatsApp de aprobación enviado al trabajador."),
                message_type='notification'
            )
            return True

        self.message_post(
            body=_("No se pudo enviar WhatsApp de aprobación. Error: %s") % result.get('error'),
            message_type='notification'
        )
        return False

    def _whatsapp_notificar_trabajador_rechazado(self):
        self.ensure_one()

        phone = self._whatsapp_get_user_phone(self.tecnico_id)

        if not phone:
            _logger.warning(
                "[Ausencias][WhatsApp] Técnico %s sin teléfono/móvil.",
                self.tecnico_id.name
            )
            self.message_post(
                body=_("No se envió WhatsApp de rechazo porque el trabajador no tiene teléfono/móvil."),
                message_type='notification'
            )
            return False

        result = self._send_whatsapp_message(
            phone,
            self._build_whatsapp_rechazado()
        )

        if result.get('success'):
            self.message_post(
                body=_("WhatsApp de rechazo enviado al trabajador."),
                message_type='notification'
            )
            return True

        self.message_post(
            body=_("No se pudo enviar WhatsApp de rechazo. Error: %s") % result.get('error'),
            message_type='notification'
        )
        return False

    # ============================================================
    # ACCIONES DE FLUJO
    # ============================================================

    def action_enviar_aprobacion(self):
        for rec in self:
            if rec.estado not in ('borrador', 'rechazado'):
                raise UserError(_("Solo se pueden enviar a aprobación solicitudes en borrador o rechazadas."))

            rec._normalize_record_dates()

            rec.write({
                'estado': 'pendiente',
            })

            rec.message_post(
                body=_("Solicitud enviada para aprobación."),
                message_type='notification'
            )

            rec._notificar_jefe_area()
            rec._whatsapp_notificar_jefes_solicitud()

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
            rec._whatsapp_notificar_trabajador_aprobado()

            rec.message_post(
                body=_(
                    "✅ Ausencia aprobada. Técnico bloqueado en agenda. "
                    "Tickets afectados: %s."
                ) % len(tickets),
                message_type='notification'
            )

    def action_reportar_ausencia_inmediata(self):
        for rec in self:
            if rec.tipo not in ('enfermedad', 'falta'):
                raise UserError(_("Esta acción solo aplica para enfermedad o falta."))

            if rec.estado not in ('borrador', 'pendiente'):
                raise UserError(_("Esta ausencia ya fue procesada y no puede reportarse nuevamente."))

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
            rec._whatsapp_notificar_trabajador_aprobado()

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
            rec._whatsapp_notificar_trabajador_rechazado()

            rec.message_post(
                body=_("❌ Solicitud rechazada."),
                message_type='notification'
            )

    def action_cancelar(self):
        for rec in self:
            if rec.estado not in ('borrador', 'pendiente'):
                raise UserError(
                    _("Solo se pueden cancelar solicitudes en borrador o pendientes.")
                )

            rec.write({
                'estado': 'cancelado',
            })

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