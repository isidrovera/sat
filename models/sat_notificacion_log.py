# -*- coding: utf-8 -*-

import json
import logging
from datetime import datetime, date, time, timedelta

import pytz
import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SatNotificacionLog(models.Model):
    _name = 'sat.notificacion.log'
    _description = 'Registro de Notificaciones SAT'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    # ==========================================================
    # CAMPOS PRINCIPALES
    # ==========================================================

    name = fields.Char(
        string='Referencia',
        default=lambda self: _('Nueva notificación'),
        copy=False,
        readonly=True,
        tracking=True,
    )

    event_type = fields.Selection(
        [
            ('para_revision', 'Máquina para revisión'),
            ('revision_iniciada', 'Revisión iniciada'),
            ('demora_jefe', 'Alerta demora al jefe'),
            ('demora_asesora', 'Demora notificada a asesora'),
            ('foto_demora', 'Foto de demora'),
            ('finalizacion', 'Finalización de reparación'),
            ('copia_comercial', 'Copia comercial'),
            ('otro', 'Otro'),
        ],
        string='Evento',
        required=True,
        index=True,
        tracking=True,
    )

    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('pending', 'Pendiente'),
            ('pending_out_of_hours', 'Pendiente fuera de horario'),
            ('sending', 'Enviando'),
            ('sent', 'Enviado'),
            ('error', 'Error'),
            ('cancelled', 'Cancelado'),
            ('skipped_duplicate', 'Duplicado omitido'),
        ],
        string='Estado',
        default='draft',
        required=True,
        index=True,
        tracking=True,
    )

    # ==========================================================
    # RELACIONES
    # ==========================================================

    maquina_id = fields.Many2one(
        'sat.sat',
        string='Máquina',
        index=True,
        ondelete='set null',
    )

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones',
        string='Reparación',
        index=True,
        ondelete='set null',
    )

    avance_id = fields.Many2one(
        'reparacion.avance',
        string='Demora / Avance',
        index=True,
        ondelete='set null',
    )

    avance_linea_id = fields.Many2one(
        'reparacion.avance.linea',
        string='Línea de demora',
        index=True,
        ondelete='set null',
    )

    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        index=True,
        ondelete='set null',
    )

    asesora_user_id = fields.Many2one(
        'res.users',
        string='Asesora',
        index=True,
        ondelete='set null',
    )

    user_id = fields.Many2one(
        'res.users',
        string='Usuario que generó',
        default=lambda self: self.env.user,
        readonly=True,
        index=True,
    )

    # ==========================================================
    # DESTINATARIO
    # ==========================================================

    recipient_type = fields.Selection(
        [
            ('asesora', 'Asesora'),
            ('jefe_area', 'Jefe de área'),
            ('copia_comercial', 'Copia comercial'),
            ('tecnico', 'Técnico'),
            ('interno', 'Interno'),
            ('otro', 'Otro'),
        ],
        string='Tipo de destinatario',
        default='otro',
        required=True,
        index=True,
    )

    recipient_name = fields.Char(
        string='Nombre destinatario',
        tracking=True,
    )

    phone = fields.Char(
        string='Teléfono',
        required=True,
        index=True,
        tracking=True,
    )

    phone_clean = fields.Char(
        string='Teléfono limpio',
        compute='_compute_phone_clean',
        store=True,
        index=True,
    )

    # ==========================================================
    # MENSAJE / MEDIA
    # ==========================================================

    message = fields.Text(
        string='Mensaje',
    )

    is_media = fields.Boolean(
        string='Es media',
        default=False,
        help='Si está activo, se enviará attachment_id como imagen/media.',
    )

    attachment_id = fields.Many2one(
        'ir.attachment',
        string='Adjunto',
        ondelete='set null',
    )

    caption = fields.Text(
        string='Caption',
        help='Texto opcional para enviar junto con la imagen/media.',
    )

    # ==========================================================
    # HORARIO / PROGRAMACIÓN
    # ==========================================================

    respect_business_hours = fields.Boolean(
        string='Respetar horario laboral',
        default=True,
        help='Si está activo, se enviará solo dentro del horario laboral Perú/Lima.',
    )

    force_send = fields.Boolean(
        string='Forzar envío inmediato',
        default=False,
        help='Si está activo, ignora horario laboral.',
    )

    scheduled_date = fields.Datetime(
        string='Fecha programada',
        index=True,
        tracking=True,
    )

    sent_date = fields.Datetime(
        string='Fecha enviada',
        readonly=True,
        index=True,
        tracking=True,
    )

    lima_scheduled_text = fields.Char(
        string='Programado Lima',
        compute='_compute_lima_texts',
    )

    lima_sent_text = fields.Char(
        string='Enviado Lima',
        compute='_compute_lima_texts',
    )

    business_status = fields.Char(
        string='Estado horario al crear',
        readonly=True,
    )

    business_reason = fields.Char(
        string='Motivo horario',
        readonly=True,
    )

    # ==========================================================
    # RESPUESTA GATEWAY
    # ==========================================================

    gateway_status_code = fields.Integer(
        string='Código HTTP',
        readonly=True,
    )

    gateway_response = fields.Text(
        string='Respuesta gateway',
        readonly=True,
    )

    error_message = fields.Text(
        string='Error',
        readonly=True,
        tracking=True,
    )

    retry_count = fields.Integer(
        string='Reintentos',
        default=0,
        readonly=True,
    )

    max_retries = fields.Integer(
        string='Máximo reintentos',
        default=3,
    )

    last_attempt_date = fields.Datetime(
        string='Último intento',
        readonly=True,
    )

    # ==========================================================
    # ORIGEN TÉCNICO
    # ==========================================================

    source_model = fields.Char(
        string='Modelo origen',
        index=True,
    )

    source_res_id = fields.Integer(
        string='ID origen',
        index=True,
    )

    unique_key = fields.Char(
        string='Clave única',
        index=True,
        copy=False,
        help='Sirve para evitar duplicados en eventos que solo deben enviarse una vez.',
    )

    note = fields.Text(
        string='Notas internas',
    )

    _sql_constraints = [
        (
            'unique_sat_notification_unique_key',
            'unique(unique_key)',
            'Ya existe una notificación con esta clave única.'
        )
    ]

    # ==========================================================
    # COMPUTES
    # ==========================================================

    @api.depends('phone')
    def _compute_phone_clean(self):
        for record in self:
            record.phone_clean = record._clean_phone(record.phone)

    @api.depends('scheduled_date', 'sent_date')
    def _compute_lima_texts(self):
        for record in self:
            record.lima_scheduled_text = record._datetime_utc_to_lima_text(record.scheduled_date)
            record.lima_sent_text = record._datetime_utc_to_lima_text(record.sent_date)

    # ==========================================================
    # CREATE
    # ==========================================================

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()

        for vals in vals_list:
            if vals.get('name', _('Nueva notificación')) == _('Nueva notificación'):
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'sat.notificacion.log'
                ) or _('Nueva notificación')

            if not vals.get('scheduled_date'):
                vals['scheduled_date'] = now

            if not vals.get('state') or vals.get('state') == 'draft':
                vals['state'] = 'pending'

            if vals.get('phone'):
                vals['phone'] = str(vals.get('phone')).strip()

            asesora_user_id = vals.get('asesora_user_id')
            if asesora_user_id and not self.env['res.users'].sudo().browse(asesora_user_id).exists():
                _logger.warning(
                    "[SAT NOTIF] asesora_user_id inválido en create: %s. Se guardará vacío.",
                    asesora_user_id,
                )
                vals['asesora_user_id'] = False

        records = super().create(vals_list)

        for record in records:
            try:
                with record.env.cr.savepoint():
                    record._evaluate_initial_schedule()
            except Exception as e:
                _logger.exception(
                    "[SAT NOTIF] Error evaluando horario inicial log ID %s: %s",
                    record.id,
                    e,
                )

        return records

    # ==========================================================
    # HELPERS TELÉFONO
    # ==========================================================

    def _clean_phone(self, phone):
        if not phone:
            return ''

        phone = str(phone).replace('+', '')
        phone = ''.join(phone.split())
        phone = phone.replace('(', '').replace(')', '').replace('-', '')

        # Perú: si son 9 dígitos, agregamos 51.
        # Si ya viene con 51 o 1 u otro código internacional, lo dejamos.
        if phone and len(phone) == 9 and not phone.startswith('51'):
            phone = '51' + phone

        return phone

    # ==========================================================
    # HELPERS FECHA / LIMA
    # ==========================================================

    def _get_lima_tz(self):
        return pytz.timezone('America/Lima')

    def _now_lima(self):
        return fields.Datetime.now().replace(tzinfo=pytz.utc).astimezone(self._get_lima_tz())

    def _utc_naive_to_lima(self, dt_value):
        if not dt_value:
            return False

        if isinstance(dt_value, str):
            dt_value = fields.Datetime.from_string(dt_value)

        if not dt_value:
            return False

        utc_dt = pytz.utc.localize(dt_value) if dt_value.tzinfo is None else dt_value.astimezone(pytz.utc)
        return utc_dt.astimezone(self._get_lima_tz())

    def _lima_to_utc_naive(self, lima_dt):
        if not lima_dt:
            return False

        lima_tz = self._get_lima_tz()

        if lima_dt.tzinfo is None:
            lima_dt = lima_tz.localize(lima_dt)

        utc_dt = lima_dt.astimezone(pytz.utc)
        return utc_dt.replace(tzinfo=None)

    def _datetime_utc_to_lima_text(self, dt_value):
        lima_dt = self._utc_naive_to_lima(dt_value)
        if not lima_dt:
            return ''
        return lima_dt.strftime('%d/%m/%Y %H:%M')

    def _float_hour_to_time(self, float_hour):
        hour = int(float_hour)
        minute = int(round((float_hour - hour) * 60))

        if minute == 60:
            hour += 1
            minute = 0

        hour = max(0, min(hour, 23))
        minute = max(0, min(minute, 59))

        return time(hour, minute, 0)

    def _datetime_to_float_hour(self, dt_value):
        return dt_value.hour + (dt_value.minute / 60.0) + (dt_value.second / 3600.0)

    # ==========================================================
    # HORARIO LABORAL
    # ==========================================================

    @api.model
    def _get_business_status_lima(self, lima_dt=False):
        """
        Evalúa si una fecha/hora Lima está dentro del horario laboral.

        Prioridad:
        1. Calendario especial whatsapp.calendar.event
        2. Horario normal whatsapp.business.hours

        Retorna:
        {
            is_open: bool,
            reason: str,
            reason_label: str,
            message: str/False,
            display_hours: str,
            source: calendar/business/default
        }
        """
        lima_dt = lima_dt or self._now_lima()

        current_date = lima_dt.date()
        current_hour_float = self._datetime_to_float_hour(lima_dt)

        CalendarEvent = self.env['whatsapp.calendar.event'].sudo()
        BusinessHours = self.env['whatsapp.business.hours'].sudo()

        # 1) Eventos especiales del día
        event = CalendarEvent.search([
            ('event_date', '=', current_date),
            ('active', '=', True),
        ], order='event_type asc, id asc', limit=1)

        if event:
            status = event.evaluate_status(current_hour_float)
            status['source'] = 'calendar'
            return status

        # 2) Horario normal
        day = str(lima_dt.weekday())
        hours = BusinessHours.search([
            ('day_of_week', '=', day),
            ('active', '=', True),
        ], limit=1)

        if hours:
            status = hours.evaluate_status(current_hour_float)
            status['source'] = 'business_hours'
            return status

        # 3) Fallback si no hay configuración
        return {
            'is_open': True,
            'reason': 'no_business_hours_config',
            'reason_label': 'Sin horario configurado',
            'message': False,
            'template_name': False,
            'display_hours': '',
            'period': 'unknown',
            'source': 'default',
        }

    @api.model
    def _get_next_business_datetime_lima(self, start_lima_dt=False):
        """
        Busca la siguiente fecha/hora laboral en Lima.

        Recorre hasta 14 días para evitar bucles.
        Usa la apertura configurada del día si existe.
        """
        start_lima_dt = start_lima_dt or self._now_lima()

        # Empezar un minuto después para evitar quedar en la misma hora cerrada
        candidate = start_lima_dt + timedelta(minutes=1)

        BusinessHours = self.env['whatsapp.business.hours'].sudo()
        CalendarEvent = self.env['whatsapp.calendar.event'].sudo()

        for day_offset in range(0, 14):
            current_day = candidate.date() + timedelta(days=day_offset)

            # Si hay evento cerrado todo el día, saltar
            closed_event = CalendarEvent.search([
                ('event_date', '=', current_day),
                ('active', '=', True),
                ('is_closed', '=', True),
            ], limit=1)

            if closed_event:
                continue

            weekday = str(current_day.weekday())
            hours = BusinessHours.search([
                ('day_of_week', '=', weekday),
                ('active', '=', True),
            ], limit=1)

            if not hours:
                # Si no existe horario configurado, usar 08:30
                open_dt = datetime.combine(current_day, time(8, 30))
                lima_open_dt = self._get_lima_tz().localize(open_dt)
                status = self._get_business_status_lima(lima_open_dt)
                if status.get('is_open'):
                    return lima_open_dt
                continue

            if not hours.is_workday:
                continue

            open_time = self._float_hour_to_time(hours.open_time)
            close_time = self._float_hour_to_time(hours.close_time)

            open_dt = self._get_lima_tz().localize(datetime.combine(current_day, open_time))
            close_dt = self._get_lima_tz().localize(datetime.combine(current_day, close_time))

            # Si es el mismo día y aún estamos dentro del horario, usar candidate
            if current_day == candidate.date():
                if open_dt <= candidate <= close_dt:
                    status = self._get_business_status_lima(candidate)
                    if status.get('is_open'):
                        return candidate

                # Si todavía no abre, usar hora de apertura
                if candidate < open_dt:
                    status = self._get_business_status_lima(open_dt)
                    if status.get('is_open'):
                        return open_dt

            else:
                status = self._get_business_status_lima(open_dt)
                if status.get('is_open'):
                    return open_dt

        # Fallback extremo: siguiente día 08:30 Lima
        fallback = start_lima_dt + timedelta(days=1)
        fallback_dt = datetime.combine(fallback.date(), time(8, 30))
        return self._get_lima_tz().localize(fallback_dt)

    def _evaluate_initial_schedule(self):
        """
        Si respeta horario y está fuera de horario, deja pendiente.
        Si está en horario o force_send, queda pending para envío inmediato.
        """
        for record in self:
            if record.state not in ('pending', 'draft'):
                continue

            if record.force_send or not record.respect_business_hours:
                record.write({
                    'state': 'pending',
                    'business_status': 'Envío inmediato',
                    'business_reason': 'force_send' if record.force_send else 'no_respect_business_hours',
                })
                continue

            now_lima = record._now_lima()
            status = record._get_business_status_lima(now_lima)

            vals = {
                'business_status': status.get('reason_label') or status.get('reason'),
                'business_reason': status.get('reason'),
            }

            if status.get('is_open'):
                vals['state'] = 'pending'
                vals['scheduled_date'] = fields.Datetime.now()
            else:
                next_lima = record._get_next_business_datetime_lima(now_lima)
                vals['state'] = 'pending_out_of_hours'
                vals['scheduled_date'] = record._lima_to_utc_naive(next_lima)

            record.write(vals)

    # ==========================================================
    # CONFIG GATEWAY
    # ==========================================================

    @api.model
    def _get_gateway_config(self):
        ICP = self.env['ir.config_parameter'].sudo()

        base_url = ICP.get_param('sat.whatsapp_gateway_base_url')
        api_key = ICP.get_param('sat.whatsapp_gateway_api_key')
        text_endpoint = ICP.get_param('sat.whatsapp_gateway_text_endpoint', '/api/send-message')
        media_endpoint = ICP.get_param('sat.whatsapp_gateway_media_endpoint', '/api/send-media')

        if not base_url:
            raise UserError(_("Falta configurar sat.whatsapp_gateway_base_url"))

        if not api_key:
            raise UserError(_("Falta configurar sat.whatsapp_gateway_api_key"))

        base_url = base_url.rstrip('/')

        if not text_endpoint.startswith('/'):
            text_endpoint = '/' + text_endpoint

        if not media_endpoint.startswith('/'):
            media_endpoint = '/' + media_endpoint

        return {
            'base_url': base_url,
            'api_key': api_key,
            'text_url': f'{base_url}{text_endpoint}',
            'media_url': f'{base_url}{media_endpoint}',
        }

    # ==========================================================
    # ENVÍO
    # ==========================================================

    def _send_text_message(self):
        self.ensure_one()

        config = self._get_gateway_config()

        payload = {
            'to': self.phone_clean,
            'message': self.message or '',
        }

        headers = {
            'Content-Type': 'application/json',
            'x-api-key': config['api_key'],
        }

        response = requests.post(
            config['text_url'],
            headers=headers,
            json=payload,
            timeout=30,
        )

        return self._process_gateway_response(response)

    def _send_media_message(self):
        self.ensure_one()

        if not self.attachment_id:
            return {
                'success': False,
                'error': 'No hay adjunto para enviar.',
            }

        if not self.attachment_id.datas:
            return {
                'success': False,
                'error': 'El adjunto no tiene datos.',
            }

        config = self._get_gateway_config()

        datas = self.attachment_id.datas
        if isinstance(datas, bytes):
            datas = datas.decode()

        payload = {
            'to': self.phone_clean,
            'caption': self.caption or self.message or '',
            'filename': self.attachment_id.name or 'archivo.jpg',
            'mimetype': self.attachment_id.mimetype or 'image/jpeg',
            'mediaBase64': datas,
        }

        headers = {
            'Content-Type': 'application/json',
            'x-api-key': config['api_key'],
        }

        response = requests.post(
            config['media_url'],
            headers=headers,
            json=payload,
            timeout=60,
        )

        return self._process_gateway_response(response)

    def _process_gateway_response(self, response):
        try:
            response_json = response.json()
        except Exception:
            return {
                'success': False,
                'status_code': response.status_code,
                'raw_response': response.text,
                'error': 'La respuesta del gateway no contiene JSON válido.',
            }

        success = response.status_code == 200 and bool(response_json.get('success'))

        return {
            'success': success,
            'status_code': response.status_code,
            'response': response_json,
            'error': response_json.get('error') or response_json.get('message') or 'Error desconocido',
        }

    def action_send_now(self):
        for record in self:
            record._send_one()
        return True

    def _send_one(self):
        self.ensure_one()

        if self.state in ('sent', 'cancelled', 'skipped_duplicate'):
            return False

        if not self.phone_clean:
            self.write({
                'state': 'error',
                'error_message': 'No hay teléfono limpio para enviar.',
                'last_attempt_date': fields.Datetime.now(),
                'retry_count': self.retry_count + 1,
            })
            return False

        if self.respect_business_hours and not self.force_send:
            now_lima = self._now_lima()
            status = self._get_business_status_lima(now_lima)

            if not status.get('is_open'):
                next_lima = self._get_next_business_datetime_lima(now_lima)
                self.write({
                    'state': 'pending_out_of_hours',
                    'scheduled_date': self._lima_to_utc_naive(next_lima),
                    'business_status': status.get('reason_label') or status.get('reason'),
                    'business_reason': status.get('reason'),
                })
                return False

        self.write({
            'state': 'sending',
            'last_attempt_date': fields.Datetime.now(),
        })

        try:
            if self.is_media:
                result = self._send_media_message()
            else:
                result = self._send_text_message()

            vals = {
                'gateway_status_code': result.get('status_code'),
                'gateway_response': json.dumps(
                    result.get('response') or result.get('raw_response') or result,
                    ensure_ascii=False,
                    indent=2,
                ),
                'last_attempt_date': fields.Datetime.now(),
            }

            if result.get('success'):
                vals.update({
                    'state': 'sent',
                    'sent_date': fields.Datetime.now(),
                    'error_message': False,
                })
            else:
                vals.update({
                    'state': 'error',
                    'retry_count': self.retry_count + 1,
                    'error_message': result.get('error') or 'Error desconocido',
                })

            self.write(vals)
            self._post_log_to_related_record()

            return result.get('success')

        except Exception as e:
            _logger.exception("[SAT NOTIF] Error enviando log ID %s: %s", self.id, e)

            self.write({
                'state': 'error',
                'retry_count': self.retry_count + 1,
                'error_message': str(e),
                'last_attempt_date': fields.Datetime.now(),
            })

            self._post_log_to_related_record()
            return False

    # ==========================================================
    # CHATTER
    # ==========================================================

    def _get_related_record_for_chatter(self):
        self.ensure_one()

        if self.reparacion_id:
            return self.reparacion_id

        if self.maquina_id:
            return self.maquina_id

        if self.avance_id:
            return self.avance_id

        return False

    def _post_log_to_related_record(self):
        self.ensure_one()

        record = self._get_related_record_for_chatter()
        if not record:
            return False

        if self.state == 'sent':
            icon = '✅'
            title = _('WhatsApp enviado')
        elif self.state == 'pending_out_of_hours':
            icon = '⏳'
            title = _('WhatsApp pendiente por fuera de horario')
        elif self.state == 'error':
            icon = '⚠️'
            title = _('Error enviando WhatsApp')
        else:
            icon = 'ℹ️'
            title = _('Notificación WhatsApp')

        body = _(
            "%(icon)s <b>%(title)s</b><br/>"
            "<b>Evento:</b> %(event)s<br/>"
            "<b>Destinatario:</b> %(recipient)s<br/>"
            "<b>Teléfono:</b> %(phone)s<br/>"
            "<b>Estado:</b> %(state)s<br/>"
            "<b>Programado Lima:</b> %(scheduled)s<br/>"
            "<b>Enviado Lima:</b> %(sent)s"
        ) % {
            'icon': icon,
            'title': title,
            'event': dict(self._fields['event_type'].selection).get(self.event_type, self.event_type),
            'recipient': self.recipient_name or self.recipient_type,
            'phone': self.phone_clean or self.phone,
            'state': dict(self._fields['state'].selection).get(self.state, self.state),
            'scheduled': self.lima_scheduled_text or '',
            'sent': self.lima_sent_text or '',
        }

        if self.error_message:
            body += _("<br/><b>Error:</b> %s") % self.error_message

        try:
            record.message_post(body=body, subtype_xmlid='mail.mt_note')
        except Exception as e:
            _logger.warning(
                "[SAT NOTIF] No se pudo publicar chatter para log ID %s: %s",
                self.id,
                e,
            )

        return True

    # ==========================================================
    # CREACIÓN CENTRALIZADA
    # ==========================================================

    def _resolve_asesora_user(self, asesora_user=False):
        """
        Normaliza la asesora a res.users.
        Algunos flujos envían el contacto res.partner; el log necesita usuario.
        """
        if not asesora_user:
            return False

        if getattr(asesora_user, '_name', '') == 'res.users':
            return asesora_user if asesora_user.exists() else False

        if getattr(asesora_user, '_name', '') == 'res.partner':
            user = self.env['res.users'].sudo().search([
                ('partner_id', '=', asesora_user.id),
            ], limit=1)
            if user:
                return user

            _logger.warning(
                "[SAT NOTIF] asesora partner ID %s (%s) no tiene usuario asociado.",
                asesora_user.id,
                asesora_user.display_name,
            )
            return False

        partner = getattr(asesora_user, 'partner_id', False)
        if partner:
            user = self.env['res.users'].sudo().search([
                ('partner_id', '=', partner.id),
            ], limit=1)
            if user:
                return user

        return False

    @api.model
    def create_notification(
        self,
        event_type,
        phone,
        message=False,
        recipient_type='otro',
        recipient_name=False,
        maquina=False,
        reparacion=False,
        avance=False,
        avance_linea=False,
        cliente=False,
        asesora_user=False,
        is_media=False,
        attachment=False,
        caption=False,
        respect_business_hours=True,
        force_send=False,
        unique_key=False,
        source_record=False,
        send_immediately=True,
        note=False,
    ):
        """
        Crea una notificación y, opcionalmente, intenta enviarla.

        Si está fuera de horario y respect_business_hours=True,
        quedará como pending_out_of_hours.
        """
        asesora_user = self._resolve_asesora_user(asesora_user)

        vals = {
            'event_type': event_type,
            'phone': phone,
            'message': message or False,
            'recipient_type': recipient_type,
            'recipient_name': recipient_name or False,
            'maquina_id': maquina.id if maquina else False,
            'reparacion_id': reparacion.id if reparacion else False,
            'avance_id': avance.id if avance else False,
            'avance_linea_id': avance_linea.id if avance_linea else False,
            'cliente_id': cliente.id if cliente else False,
            'asesora_user_id': asesora_user.id if asesora_user else False,
            'is_media': bool(is_media),
            'attachment_id': attachment.id if attachment else False,
            'caption': caption or False,
            'respect_business_hours': bool(respect_business_hours),
            'force_send': bool(force_send),
            'unique_key': unique_key or False,
            'note': note or False,
            'state': 'pending',
        }

        if source_record:
            vals.update({
                'source_model': source_record._name,
                'source_res_id': source_record.id,
            })

        try:
            with self.env.cr.savepoint():
                log = self.sudo().create(vals)
        except Exception as e:
            # Si falla por unique_key duplicado, registramos omitido solo en logger.
            _logger.warning(
                "[SAT NOTIF] No se pudo crear notificación event=%s phone=%s unique=%s error=%s",
                event_type,
                phone,
                unique_key,
                e,
            )
            return False

        if send_immediately:
            try:
                with self.env.cr.savepoint():
                    log._send_one()
            except Exception as e:
                _logger.warning(
                    "[SAT NOTIF] No se pudo enviar notificación log ID %s: %s",
                    log.id,
                    e,
                    exc_info=True,
                )

        return log

    # ==========================================================
    # CRON
    # ==========================================================

    @api.model
    def cron_send_pending_notifications(self, limit=100):
        """
        Envía notificaciones pendientes.

        - pending: intenta enviar si scheduled_date <= now
        - pending_out_of_hours: intenta solo si ya volvió el horario laboral
        - error: reintenta si retry_count < max_retries
        """
        now = fields.Datetime.now()

        logs = self.search([
            ('state', 'in', ['pending', 'pending_out_of_hours', 'error']),
            ('scheduled_date', '<=', now),
        ], order='scheduled_date asc, id asc', limit=limit)

        logs = logs.filtered(lambda log: log.retry_count < log.max_retries)

        _logger.info("[SAT NOTIF] Cron encontró %s notificaciones pendientes", len(logs))

        for log in logs:
            try:
                log._send_one()
            except Exception as e:
                _logger.exception(
                    "[SAT NOTIF] Error cron enviando log ID %s: %s",
                    log.id,
                    e,
                )

        return True

    # ==========================================================
    # ACCIONES
    # ==========================================================

    def action_cancel(self):
        for record in self:
            if record.state not in ('sent', 'cancelled'):
                record.write({'state': 'cancelled'})
        return True

    def action_reset_to_pending(self):
        for record in self:
            record.write({
                'state': 'pending',
                'error_message': False,
                'gateway_response': False,
                'gateway_status_code': False,
            })
        return True

class SatSatNotificacionLog(models.Model):
    _inherit = 'sat.sat'

    notificacion_log_ids = fields.One2many(
        'sat.notificacion.log',
        'maquina_id',
        string='Notificaciones WhatsApp',
        readonly=True,
    )

    notificacion_log_count = fields.Integer(
        string='Notificaciones',
        compute='_compute_notificacion_log_count',
    )

    def _compute_notificacion_log_count(self):
        for record in self:
            record.notificacion_log_count = len(record.notificacion_log_ids)

    def action_open_notificacion_logs(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Notificaciones WhatsApp'),
            'res_model': 'sat.notificacion.log',
            'view_mode': 'list,form',
            'domain': [('maquina_id', '=', self.id)],
            'context': {
                'default_maquina_id': self.id,
                'default_cliente_id': self.cliente_id.id if self.cliente_id else False,
            },
        }
