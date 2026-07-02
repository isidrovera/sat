# -*- coding: utf-8 -*-

import logging
import uuid
from datetime import timedelta

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ReparacionAvanceOpcion(models.Model):
    _name = 'reparacion.avance.opcion'
    _description = 'Opción de Demora de Reparación'
    _order = 'sequence, category, name'

    name = fields.Char(
        string='Opción',
        required=True,
        translate=True,
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )

    category = fields.Selection(
        [
            ('diagnostico', 'Diagnóstico'),
            ('trabajo', 'Trabajo en proceso'),
            ('toner_revelado', 'Tóner / revelado'),
            ('papel', 'Alimentación de papel'),
            ('limpieza', 'Limpieza / mantenimiento'),
            ('imagen', 'Imagen / calidad'),
            ('fusor', 'Fusor'),
            ('partes', 'Partes / repuestos'),
            ('sistema', 'Sistema / software'),
            ('accesorios', 'Finalizador / accesorios'),
            ('otro', 'Otro'),
        ],
        string='Categoría',
        default='diagnostico',
        required=True,
    )

    message_text = fields.Char(
        string='Texto para mensaje',
        help='Texto corto que se usará en el WhatsApp. Si se deja vacío, se usará el nombre de la opción.',
    )

    require_detail = fields.Boolean(
        string='Requiere detalle',
        default=False,
        help='Si está activo, al seleccionar esta opción se debería pedir un detalle adicional.',
    )

    allow_color = fields.Boolean(
        string='Permite indicar color',
        default=False,
        help='Útil para opciones como "No alimenta tóner".',
    )

    allow_part_detail = fields.Boolean(
        string='Permite indicar parte',
        default=False,
        help='Útil para opciones como "Buscando partes".',
    )

    notes = fields.Text(
        string='Notas internas',
    )


class ReparacionAvance(models.Model):
    _name = 'reparacion.avance'
    _description = 'Demora de Reparación'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Referencia',
        default=lambda self: _('Nueva demora'),
        copy=False,
        readonly=True,
    )

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones',
        string='Reparación',
        required=True,
        ondelete='cascade',
        index=True,
    )

    maquina_id = fields.Many2one(
        related='reparacion_id.maquina_id',
        string='Máquina',
        store=True,
        readonly=True,
    )

    cliente_id = fields.Many2one(
        related='reparacion_id.cliente_id',
        string='Cliente',
        store=True,
        readonly=True,
    )

    responsable_id = fields.Many2one(
        related='reparacion_id.responsable_id',
        string='Técnico',
        store=True,
        readonly=True,
    )

    user_id = fields.Many2one(
        'res.users',
        string='Registrado por',
        default=lambda self: self.env.user,
        readonly=True,
    )

    line_ids = fields.One2many(
        'reparacion.avance.linea',
        'avance_id',
        string='Motivos de demora',
    )

    detalle = fields.Text(
        string='Detalle adicional',
    )

    # Se mantiene por compatibilidad con registros antiguos.
    # Las fotos nuevas se guardan en reparacion.avance.linea.attachment_ids.
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'reparacion_avance_ir_attachment_rel',
        'avance_id',
        'attachment_id',
        string='Fotos / Adjuntos antiguos',
    )

    notificar_asesora = fields.Boolean(
        string='Notificar a asesora',
        default=False,
        tracking=True,
    )

    asesora_notificada = fields.Boolean(
        string='Asesora notificada',
        default=False,
        readonly=True,
        tracking=True,
    )

    fecha_notificacion_asesora = fields.Datetime(
        string='Fecha notificación asesora',
        readonly=True,
    )

    estado = fields.Selection(
        [
            ('borrador', 'Borrador'),
            ('registrado', 'Registrado'),
            ('notificado', 'Notificado a asesora'),
            ('error', 'Error de notificación'),
        ],
        string='Estado',
        default='registrado',
        tracking=True,
    )

    error_notificacion = fields.Text(
        string='Error de notificación',
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        for record in records:
            if record.name == _('Nueva demora'):
                record.name = _('Demora %s') % record.id

            try:
                record.reparacion_id._after_avance_registrado(record)
            except Exception as e:
                _logger.exception(
                    "[DEMORA REPARACIÓN] Error actualizando reparación después de registrar demora %s: %s",
                    record.id,
                    e,
                )

            if record.notificar_asesora:
                try:
                    record.action_notificar_asesora()
                except Exception as e:
                    _logger.exception(
                        "[DEMORA REPARACIÓN] Error notificando asesora desde demora %s: %s",
                        record.id,
                        e,
                    )

        return records

    def _get_option_texts(self):
        self.ensure_one()

        texts = []
        for line in self.line_ids:
            text = line._get_display_text()
            if text:
                texts.append(text)

        return texts

    def _build_msg_asesora(self):
        self.ensure_one()

        reparacion = self.reparacion_id

        cliente = reparacion.cliente_id.name if reparacion.cliente_id else 'NA'
        asesora_user = self._get_asesora_user()
        asesora = asesora_user.name if asesora_user else 'NA'
        modelo = reparacion.nombre_maquina or 'NA'
        serie = reparacion.serie_id or 'NA'

        opciones = self._get_option_texts()
        motivo = "; ".join(opciones) if opciones else 'Demora registrada'

        if self.detalle:
            motivo = "%s - %s" % (motivo, self.detalle)

        if len(motivo) > 450:
            motivo = motivo[:447] + '...'

        msg = f"""*Demora de reparación*

*Cliente:* {cliente}
*Asesora:* {asesora}
*Modelo:* {modelo}
*Serie:* {serie}

*Motivo:* {motivo}
*Estado:* Continúa en revisión.
"""

        return msg

    def _get_line_attachments(self):
        self.ensure_one()

        attachments = self.env['ir.attachment'].sudo().browse()

        for line in self.line_ids:
            attachments |= line.attachment_ids

        return attachments

    def _get_asesora_user(self):
        self.ensure_one()

        reparacion = self.reparacion_id

        try:
            if reparacion.maquina_id and reparacion.maquina_id.cliente_id:
                return reparacion.maquina_id.cliente_id.asesora_id
        except Exception:
            pass

        try:
            if reparacion.cliente_id:
                return reparacion.cliente_id.asesora_id
        except Exception:
            pass

        return False

    def _get_copia_comercial_phone(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return ICP.get_param(
            'sat.notificaciones_comerciales_copia_phone',
            '19373717674'
        ) or ''

    def action_notificar_asesora(self):
        """
        Notifica la demora usando sat.notificacion.log.

        Condición obligatoria para notificar a asesora y copia comercial:
        1. La reparación/máquina debe tener cliente.
        2. El cliente debe tener asesora.
        3. La asesora debe tener celular.

        Si falta cualquiera de esos datos, NO se notifica ni a asesora ni a copia comercial.

        El jefe de área es independiente y sí puede recibir alerta interna aunque no exista asesora.
        """
        Log = self.env['sat.notificacion.log'].sudo()

        for record in self:
            reparacion = record.reparacion_id

            if not reparacion:
                continue

            asesora_phone = reparacion.asesora_mobile_clean or ''
            copia_phone = record._get_copia_comercial_phone()

            asesora_user = record._get_asesora_user()
            cliente = reparacion.cliente_id if reparacion.cliente_id else False
            maquina = reparacion.maquina_id if reparacion.maquina_id else False

            created_logs = self.env['sat.notificacion.log'].sudo().browse()

            # ------------------------------------------------------
            # VALIDACIONES OBLIGATORIAS
            # ------------------------------------------------------
            if not cliente:
                record.write({
                    'estado': 'registrado',
                    'error_notificacion': False,
                })

                reparacion.message_post(
                    body=_(
                        "ℹ️ No se notificó la demora a asesora ni copia comercial "
                        "porque la reparación no tiene cliente asignado."
                    ),
                    subtype_xmlid='mail.mt_note',
                )
                continue

            if not asesora_user:
                record.write({
                    'estado': 'registrado',
                    'error_notificacion': False,
                })

                reparacion.message_post(
                    body=_(
                        "ℹ️ No se notificó la demora a asesora ni copia comercial "
                        "porque el cliente no tiene asesora asignada."
                    ),
                    subtype_xmlid='mail.mt_note',
                )
                continue

            if not asesora_phone:
                record.write({
                    'estado': 'error',
                    'error_notificacion': _('La asesora no tiene número móvil configurado.'),
                })

                reparacion.message_post(
                    body=_(
                        "ℹ️ No se notificó la demora a asesora ni copia comercial "
                        "porque la asesora no tiene celular configurado."
                    ),
                    subtype_xmlid='mail.mt_note',
                )
                continue

            msg = record._build_msg_asesora()
            attachments = record._get_line_attachments()

            asesora_text_log = False

            # ------------------------------------------------------
            # 1) Texto a asesora
            # ------------------------------------------------------
            asesora_text_log = Log.create_notification(
                event_type='demora_asesora',
                phone=asesora_phone,
                message=msg,
                recipient_type='asesora',
                recipient_name=asesora_user.name,
                maquina=maquina,
                reparacion=reparacion,
                avance=record,
                cliente=cliente,
                asesora_user=asesora_user,
                respect_business_hours=True,
                force_send=False,
                unique_key='demora_asesora:avance:%s:text:%s' % (
                    record.id,
                    asesora_phone,
                ),
                source_record=record,
                send_immediately=True,
                note='Notificación de demora enviada a asesora.',
            )

            if asesora_text_log:
                created_logs |= asesora_text_log

            # ------------------------------------------------------
            # 2) Fotos a asesora
            # ------------------------------------------------------
            for attachment in attachments:
                mimetype = attachment.mimetype or ''

                if not mimetype.startswith('image/'):
                    continue

                log = Log.create_notification(
                    event_type='foto_demora',
                    phone=asesora_phone,
                    message=False,
                    caption='Evidencia de demora',
                    recipient_type='asesora',
                    recipient_name=asesora_user.name,
                    maquina=maquina,
                    reparacion=reparacion,
                    avance=record,
                    cliente=cliente,
                    asesora_user=asesora_user,
                    is_media=True,
                    attachment=attachment,
                    respect_business_hours=True,
                    force_send=False,
                    unique_key='foto_demora:avance:%s:asesora:%s:att:%s' % (
                        record.id,
                        asesora_phone,
                        attachment.id,
                    ),
                    source_record=record,
                    send_immediately=True,
                    note='Foto de demora enviada a asesora.',
                )

                if log:
                    created_logs |= log

            # ------------------------------------------------------
            # 3) Texto copia comercial
            # Solo se crea si también existe cliente + asesora + celular.
            # ------------------------------------------------------
            if copia_phone and copia_phone != asesora_phone:
                log = Log.create_notification(
                    event_type='copia_comercial',
                    phone=copia_phone,
                    message=msg,
                    recipient_type='copia_comercial',
                    recipient_name='Copia comercial',
                    maquina=maquina,
                    reparacion=reparacion,
                    avance=record,
                    cliente=cliente,
                    asesora_user=asesora_user,
                    respect_business_hours=True,
                    force_send=False,
                    unique_key='demora_asesora:avance:%s:copia:%s' % (
                        record.id,
                        copia_phone,
                    ),
                    source_record=record,
                    send_immediately=True,
                    note='Copia comercial de demora de reparación.',
                )

                if log:
                    created_logs |= log

                # --------------------------------------------------
                # 4) Fotos copia comercial
                # --------------------------------------------------
                for attachment in attachments:
                    mimetype = attachment.mimetype or ''

                    if not mimetype.startswith('image/'):
                        continue

                    log = Log.create_notification(
                        event_type='foto_demora',
                        phone=copia_phone,
                        message=False,
                        caption='Evidencia de demora',
                        recipient_type='copia_comercial',
                        recipient_name='Copia comercial',
                        maquina=maquina,
                        reparacion=reparacion,
                        avance=record,
                        cliente=cliente,
                        asesora_user=asesora_user,
                        is_media=True,
                        attachment=attachment,
                        respect_business_hours=True,
                        force_send=False,
                        unique_key='foto_demora:avance:%s:copia:%s:att:%s' % (
                            record.id,
                            copia_phone,
                            attachment.id,
                        ),
                        source_record=record,
                        send_immediately=True,
                        note='Copia comercial de foto de demora.',
                    )

                    if log:
                        created_logs |= log

            # ------------------------------------------------------
            # Estado de la demora
            # ------------------------------------------------------
            error_logs = created_logs.filtered(lambda l: l.state == 'error')
            pending_logs = created_logs.filtered(
                lambda l: l.state in ('pending', 'pending_out_of_hours', 'sending')
            )

            sent_text = bool(asesora_text_log and asesora_text_log.state == 'sent')
            pending_text = bool(
                asesora_text_log
                and asesora_text_log.state in ('pending', 'pending_out_of_hours', 'sending')
            )

            if error_logs:
                record.write({
                    'estado': 'error',
                    'error_notificacion': '\n'.join(
                        [msg for msg in error_logs.mapped('error_message') if msg]
                    ) or _('Error enviando notificación de demora.'),
                })

            elif sent_text:
                record.write({
                    'asesora_notificada': True,
                    'fecha_notificacion_asesora': fields.Datetime.now(),
                    'estado': 'notificado',
                    'error_notificacion': False,
                })

            elif pending_text or pending_logs:
                record.write({
                    'estado': 'registrado',
                    'error_notificacion': False,
                })

            else:
                record.write({
                    'estado': 'registrado',
                    'error_notificacion': False,
                })

            # ------------------------------------------------------
            # Chatter resumen
            # ------------------------------------------------------
            reparacion.message_post(
                body=_(
                    "📲 <b>Notificaciones de demora generadas</b><br/>"
                    "<b>Demora:</b> %(avance)s<br/>"
                    "<b>Cliente:</b> %(cliente)s<br/>"
                    "<b>Asesora:</b> %(asesora_name)s<br/>"
                    "<b>Celular asesora:</b> %(asesora_phone)s<br/>"
                    "<b>Copia comercial:</b> %(copia)s<br/>"
                    "<b>Fotos:</b> %(fotos)s<br/>"
                    "<b>Registros creados:</b> %(count)s"
                ) % {
                    'avance': record.name or record.id,
                    'cliente': cliente.name if cliente else '',
                    'asesora_name': asesora_user.name if asesora_user else '',
                    'asesora_phone': asesora_phone or '',
                    'copia': copia_phone or 'Sin número',
                    'fotos': len(attachments),
                    'count': len(created_logs),
                },
                subtype_xmlid='mail.mt_note',
            )


class ReparacionAvanceLinea(models.Model):
    _name = 'reparacion.avance.linea'
    _description = 'Línea de Demora de Reparación'
    _order = 'id'

    avance_id = fields.Many2one(
        'reparacion.avance',
        string='Demora',
        required=True,
        ondelete='cascade',
    )

    opcion_id = fields.Many2one(
        'reparacion.avance.opcion',
        string='Opción',
        required=True,
        domain=[('active', '=', True)],
    )

    category = fields.Selection(
        related='opcion_id.category',
        string='Categoría',
        store=True,
        readonly=True,
    )

    color = fields.Selection(
        [
            ('black', 'Negro'),
            ('cyan', 'Cyan'),
            ('magenta', 'Magenta'),
            ('yellow', 'Yellow'),
            ('varios', 'Varios colores'),
        ],
        string='Color afectado',
    )

    parte = fields.Char(
        string='Parte / repuesto',
        help='Ejemplo: fusor, cilindro, developer, faja de transferencia, rodillos, sensor, tarjeta, fuente, panel.',
    )

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'reparacion_avance_linea_ir_attachment_rel',
        'linea_id',
        'attachment_id',
        string='Fotos',
    )

    detalle = fields.Char(
        string='Detalle',
    )

    def _get_display_text(self):
        self.ensure_one()

        option = self.opcion_id
        if not option:
            return ''

        text = option.message_text or option.name

        extra = []

        if self.color:
            color_label = dict(self._fields['color'].selection).get(self.color)
            if color_label:
                extra.append(_("Color: %s") % color_label)

        if self.parte:
            extra.append(_("Parte: %s") % self.parte)

        if self.detalle:
            extra.append(self.detalle)

        if extra:
            text = "%s (%s)" % (text, " / ".join(extra))

        return text


class ReparacionesAvanceAlertas(models.Model):
    _inherit = 'reparaciones.reparaciones'

    avance_ids = fields.One2many(
        'reparacion.avance',
        'reparacion_id',
        string='Demoras',
    )

    avance_count = fields.Integer(
        string='Cantidad de demoras',
        compute='_compute_avance_count',
    )

    avance_token = fields.Char(
        string='Token de demora',
        copy=False,
        readonly=True,
        index=True,
    )

    fecha_inicio_revision = fields.Datetime(
        string='Inicio de revisión',
        copy=False,
        tracking=True,
    )

    fecha_ultimo_avance = fields.Datetime(
        string='Última demora',
        copy=False,
        tracking=True,
    )

    fecha_proxima_alerta_avance = fields.Datetime(
        string='Próxima alerta de demora',
        copy=False,
        tracking=True,
    )

    ultima_alerta_avance_jefe = fields.Datetime(
        string='Última alerta al jefe',
        copy=False,
        tracking=True,
    )

    cantidad_alertas_avance_jefe = fields.Integer(
        string='Alertas enviadas al jefe',
        default=0,
        copy=False,
        tracking=True,
    )

    avance_alertas_activas = fields.Boolean(
        string='Alertas de demora activas',
        default=True,
        copy=False,
    )

    avance_estado_alerta = fields.Selection(
        [
            ('sin_alerta', 'Sin alerta'),
            ('pendiente', 'Pendiente de demora'),
            ('alertado_jefe', 'Jefe alertado'),
            ('con_avance', 'Con demora registrada'),
            ('cerrado', 'Cerrado'),
        ],
        string='Estado alerta de demora',
        default='sin_alerta',
        copy=False,
        tracking=True,
    )

    jefe_area_user_id = fields.Many2one(
        'res.users',
        string='Jefe de área para alertas',
        default=lambda self: self._default_jefe_area_user_id(),
        copy=False,
        help='Si se configura, se usará su móvil/partner para enviar alertas. Si está vacío, se usará el parámetro del sistema.',
    )

    @api.model
    def _default_jefe_area_user_id(self):
        """
        Usuario por defecto para jefe de área.

        Prioridad:
        1. Parámetro sat.reparaciones_avance_jefe_user_id
        2. Usuario con nombre ISIDRO VERA POLO
        """
        ICP = self.env['ir.config_parameter'].sudo()
        user_id = ICP.get_param('sat.reparaciones_avance_jefe_user_id')

        if user_id:
            try:
                user = self.env['res.users'].sudo().browse(int(user_id))
                if user.exists():
                    return user.id
            except Exception:
                pass

        user = self.env['res.users'].sudo().search([
            ('name', '=ilike', 'ISIDRO VERA POLO')
        ], limit=1)

        return user.id if user else False

    @api.depends('avance_ids')
    def _compute_avance_count(self):
        for record in self:
            record.avance_count = len(record.avance_ids)

    # -------------------------------------------------------------------------
    # CONFIGURACIÓN
    # -------------------------------------------------------------------------

    def _get_avance_interval_hours(self):
        """
        Intervalo de alerta en horas.
        Parámetro opcional:
        sat.reparaciones_avance_interval_hours

        Por defecto: 1 hora.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        value = ICP.get_param('sat.reparaciones_avance_interval_hours', '1')

        try:
            value = float(value)
        except Exception:
            value = 1.0

        if value <= 0:
            value = 1.0

        return value

    def _get_jefe_area_phone(self):
        """
        Obtiene el teléfono del jefe de área.

        Prioridad:
        1. jefe_area_user_id del registro.
        2. parámetro sat.reparaciones_avance_jefe_user_id.
        3. parámetro sat.reparaciones_avance_jefe_phone.
        """
        self.ensure_one()

        phone = ''

        user = self.jefe_area_user_id

        if not user:
            ICP = self.env['ir.config_parameter'].sudo()
            jefe_user_id = ICP.get_param('sat.reparaciones_avance_jefe_user_id')
            if jefe_user_id:
                try:
                    user = self.env['res.users'].sudo().browse(int(jefe_user_id))
                    if not user.exists():
                        user = False
                except Exception:
                    user = False

        if user and user.partner_id:
            phone = user.partner_id.mobile or user.partner_id.phone or ''

        if not phone:
            ICP = self.env['ir.config_parameter'].sudo()
            phone = ICP.get_param('sat.reparaciones_avance_jefe_phone') or ''

        if hasattr(self, '_whatsapp_clean_phone'):
            phone = self._whatsapp_clean_phone(phone)
        else:
            phone = str(phone).replace('+', '')
            phone = ''.join(phone.split())
            if phone and not phone.startswith('51') and len(phone) == 9:
                phone = '51' + phone

        return phone

    # -------------------------------------------------------------------------
    # TOKEN / URL
    # -------------------------------------------------------------------------

    def _ensure_avance_token(self):
        for record in self:
            if not record.avance_token:
                record.sudo().write({
                    'avance_token': str(uuid.uuid4()),
                })

    def _get_avance_url(self):
        self.ensure_one()

        self._ensure_avance_token()

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/reparacion/avance/{self.avance_token}"

    # -------------------------------------------------------------------------
    # CONTROL DE ESTADO EN REVISIÓN
    # -------------------------------------------------------------------------

    def _prepare_avance_tracking_on_revision(self):
        """
        Prepara control de demoras cuando una reparación entra en revisión.
        """
        now = fields.Datetime.now()
        interval = self._get_avance_interval_hours()

        for record in self:
            vals = {}

            if not record.fecha_inicio_revision:
                vals['fecha_inicio_revision'] = now

            if not record.fecha_proxima_alerta_avance:
                vals['fecha_proxima_alerta_avance'] = now + timedelta(hours=interval)

            if record.avance_estado_alerta in (False, 'sin_alerta', 'cerrado'):
                vals['avance_estado_alerta'] = 'pendiente'

            if not record.avance_token:
                vals['avance_token'] = str(uuid.uuid4())

            if vals:
                record.sudo().write(vals)

    def _close_avance_tracking(self):
        """
        Cierra alertas cuando la reparación deja de estar en revisión.
        """
        for record in self:
            record.sudo().write({
                'avance_estado_alerta': 'cerrado',
                'fecha_proxima_alerta_avance': False,
                'avance_alertas_activas': False,
            })

    def write(self, vals):
        res = super().write(vals)

        if 'estado_id' in vals:
            for record in self:
                if record.estado_id == 'en_revision':
                    record._prepare_avance_tracking_on_revision()
                elif record.avance_estado_alerta != 'cerrado':
                    record._close_avance_tracking()

        return res

    # -------------------------------------------------------------------------
    # REGISTRO DE DEMORA
    # -------------------------------------------------------------------------

    def _after_avance_registrado(self, avance):
        """
        Se ejecuta después de registrar una demora.
        Reinicia la alerta para una hora después.
        """
        self.ensure_one()

        interval = self._get_avance_interval_hours()
        now = fields.Datetime.now()

        self.sudo().write({
            'fecha_ultimo_avance': now,
            'fecha_proxima_alerta_avance': now + timedelta(hours=interval),
            'avance_estado_alerta': 'con_avance',
            'avance_alertas_activas': True if self.estado_id == 'en_revision' else False,
        })

        option_texts = avance._get_option_texts()
        options_html = "<br/>".join(["- %s" % item for item in option_texts]) if option_texts else _("Demora registrada")

        self.message_post(
            body=_(
                "📝 <b>Demora registrada</b><br/>"
                "%(options)s<br/>"
                "<br/>"
                "<b>Detalle:</b><br/>%(detalle)s"
            ) % {
                'options': options_html,
                'detalle': avance.detalle or _('Sin detalle adicional.'),
            },
            subtype_xmlid='mail.mt_note',
        )

    def create_avance_rapido(
        self,
        option_data=None,
        detalle=False,
        attachment_ids=None,
        file_values=None,
        notificar_asesora=False
    ):
        """
        Crea demora rápida.

        Las fotos se guardan en las líneas.
        No se guardan en reparaciones.foto.

        file_values esperado:
        [
            {
                'name': 'foto.jpg',
                'datas': base64,
                'mimetype': 'image/jpeg',
            }
        ]
        """
        self.ensure_one()

        option_data = option_data or []
        attachment_ids = attachment_ids or []
        file_values = file_values or []

        avance = self.env['reparacion.avance'].sudo().create({
            'reparacion_id': self.id,
            'detalle': detalle or False,
            'notificar_asesora': False,
        })

        created_lines = self.env['reparacion.avance.linea'].sudo().browse()

        for item in option_data:
            opcion_id = item.get('opcion_id')
            if not opcion_id:
                continue

            line = self.env['reparacion.avance.linea'].sudo().create({
                'avance_id': avance.id,
                'opcion_id': opcion_id,
                'color': item.get('color') or False,
                'parte': item.get('parte') or False,
                'detalle': item.get('detalle') or False,
            })

            created_lines |= line

        if not created_lines and detalle:
            opcion = self.env.ref('sat.avance_opcion_otro', raise_if_not_found=False)
            if opcion:
                line = self.env['reparacion.avance.linea'].sudo().create({
                    'avance_id': avance.id,
                    'opcion_id': opcion.id,
                    'detalle': detalle,
                })
                created_lines |= line

        Attachment = self.env['ir.attachment'].sudo()

        # Si el formulario tiene una sola carga general de fotos,
        # las guardamos en la primera línea para evitar duplicados.
        target_line = created_lines[:1]

        if target_line:
            line_attachment_ids = []

            for attach_id in attachment_ids:
                attachment = Attachment.browse(attach_id)
                if attachment.exists():
                    attachment.write({
                        'res_model': 'reparacion.avance.linea',
                        'res_id': target_line.id,
                    })
                    line_attachment_ids.append(attachment.id)

            for file_data in file_values:
                attachment = Attachment.create({
                    'name': file_data.get('name') or 'foto_demora.jpg',
                    'type': 'binary',
                    'datas': file_data.get('datas'),
                    'res_model': 'reparacion.avance.linea',
                    'res_id': target_line.id,
                    'mimetype': file_data.get('mimetype') or 'image/jpeg',
                })
                line_attachment_ids.append(attachment.id)

            if line_attachment_ids:
                target_line.write({
                    'attachment_ids': [(6, 0, line_attachment_ids)],
                })

        if notificar_asesora:
            avance.write({
                'notificar_asesora': True,
            })
            avance.action_notificar_asesora()

        return avance

    # -------------------------------------------------------------------------
    # MENSAJE AL JEFE DE ÁREA
    # -------------------------------------------------------------------------

    def _build_msg_alerta_jefe_avance(self):
        self.ensure_one()

        avance_url = self._get_avance_url()

        cliente = self.cliente_id.name if self.cliente_id else 'NA'
        asesora = 'NA'
        try:
            if self.maquina_id and self.maquina_id.cliente_id and self.maquina_id.cliente_id.asesora_id:
                asesora = self.maquina_id.cliente_id.asesora_id.name
            elif self.cliente_id and self.cliente_id.asesora_id:
                asesora = self.cliente_id.asesora_id.name
        except Exception:
            asesora = 'NA'
        tecnico = self.responsable_id.name if self.responsable_id else 'NA'
        modelo = self.nombre_maquina or 'NA'
        serie = self.serie_id or 'NA'

        alertas = self.cantidad_alertas_avance_jefe + 1
        

        msg = f"""*Alerta de demora pendiente*

La reparación continúa en revisión y requiere registrar motivo de demora.

*Cliente:* {cliente}
*Asesora:* {asesora}
*Modelo:* {modelo}
*Serie:* {serie}
*Técnico:* {tecnico}
*Reparación:* {self.name or 'NA'}
*Alerta N°:* {alertas}

*Registrar demora:*
{avance_url}
"""

        return msg
    def _avance_get_current_lima(self):
        """
        Devuelve fecha/hora actual en zona horaria Perú.
        """
        now_utc = fields.Datetime.now()
        return fields.Datetime.context_timestamp(
            self.with_context(tz='America/Lima'),
            now_utc
        )


    def _avance_is_business_time(self):
        """
        Valida horario laboral usando:
        1. whatsapp.calendar.event para feriados/cierres/horarios especiales.
        2. whatsapp.business.hours para horario semanal normal.
        """
        self.ensure_one()

        now_lima = self._avance_get_current_lima()
        current_date = now_lima.date()
        current_hour_float = now_lima.hour + (now_lima.minute / 60.0)

        Calendar = self.env['whatsapp.calendar.event'].sudo()
        Hours = self.env['whatsapp.business.hours'].sudo()

        # 1) Primero validar calendario especial / feriados / cierres manuales
        calendar_event = Calendar.search([
            ('active', '=', True),
            ('event_date', '=', current_date),
        ], limit=1)

        if calendar_event:
            status = calendar_event.evaluate_status(current_hour_float)
            return bool(status.get('is_open'))

        # 2) Luego validar horario laboral normal
        day_of_week = str(now_lima.weekday())  # 0 lunes, 6 domingo

        business_hour = Hours.search([
            ('active', '=', True),
            ('day_of_week', '=', day_of_week),
        ], limit=1)

        if not business_hour:
            return False

        status = business_hour.evaluate_status(current_hour_float)
        return bool(status.get('is_open'))

    def _send_alerta_avance_jefe(self):
        """
        Envía alerta al jefe de área usando sat.notificacion.log.

        Condiciones:
        1. Solo alerta si la reparación está en revisión.
        2. No alerta si la reparación no tiene cliente.
        3. No alerta fuera del horario laboral configurado.
        4. No fuerza el envío fuera de horario.
        """
        Log = self.env['sat.notificacion.log'].sudo()

        for record in self:
            # ------------------------------------------------------
            # 1) Solo alertar si está en revisión
            # ------------------------------------------------------
            if record.estado_id != 'en_revision':
                continue

            # ------------------------------------------------------
            # 2) No alertar si no tiene cliente
            # ------------------------------------------------------
            if not record.cliente_id:
                record.message_post(
                    body=_(
                        "ℹ️ No se envió alerta de demora al jefe porque la reparación no tiene cliente asignado."
                    ),
                    subtype_xmlid='mail.mt_note',
                )
                continue

            # ------------------------------------------------------
            # 3) No alertar fuera de horario laboral
            # ------------------------------------------------------
            if not record._avance_is_business_time():
                _logger.info(
                    "[DEMORA REPARACIÓN] No se envía alerta ID %s porque está fuera de horario laboral.",
                    record.id,
                )
                continue

            # ------------------------------------------------------
            # 4) Validar teléfono del jefe de área
            # ------------------------------------------------------
            phone = record._get_jefe_area_phone()

            if not phone:
                record.message_post(
                    body=_(
                        "⚠️ No se pudo crear alerta de demora porque no hay teléfono configurado "
                        "para el jefe de área.<br/>"
                        "Configure sat.reparaciones_avance_jefe_phone o sat.reparaciones_avance_jefe_user_id."
                    ),
                    subtype_xmlid='mail.mt_note',
                )
                continue

            msg = record._build_msg_alerta_jefe_avance()
            alerta_num = record.cantidad_alertas_avance_jefe + 1

            # ------------------------------------------------------
            # 5) Crear notificación respetando horario laboral
            # ------------------------------------------------------
            log = Log.create_notification(
                event_type='demora_jefe',
                phone=phone,
                message=msg,
                recipient_type='jefe_area',
                recipient_name=record.jefe_area_user_id.name if record.jefe_area_user_id else 'Jefe de área',
                maquina=record.maquina_id if record.maquina_id else False,
                reparacion=record,
                cliente=record.cliente_id if record.cliente_id else False,
                respect_business_hours=True,
                force_send=False,
                unique_key='demora_jefe:reparacion:%s:alerta:%s' % (
                    record.id,
                    alerta_num,
                ),
                source_record=record,
                send_immediately=True,
                note='Alerta interna de demora enviada al jefe de área.',
            )

            # ------------------------------------------------------
            # 6) Si se envió correctamente, programar próxima alerta
            # ------------------------------------------------------
            if log and log.state == 'sent':
                interval = record._get_avance_interval_hours()
                now = fields.Datetime.now()

                record.sudo().write({
                    'ultima_alerta_avance_jefe': now,
                    'cantidad_alertas_avance_jefe': record.cantidad_alertas_avance_jefe + 1,
                    'fecha_proxima_alerta_avance': now + timedelta(hours=interval),
                    'avance_estado_alerta': 'alertado_jefe',
                    'avance_alertas_activas': True,
                })

                record.message_post(
                    body=_(
                        "⏰ Alerta de demora enviada al jefe de área.<br/>"
                        "<b>Número:</b> %(phone)s<br/>"
                        "<b>Próxima alerta:</b> %(next)s"
                    ) % {
                        'phone': phone,
                        'next': record.fecha_proxima_alerta_avance,
                    },
                    subtype_xmlid='mail.mt_note',
                )

            # ------------------------------------------------------
            # 7) Si se creó pero quedó pendiente o con error
            # ------------------------------------------------------
            elif log:
                record.message_post(
                    body=_(
                        "⚠️ Se creó la alerta de demora al jefe, pero no quedó enviada.<br/>"
                        "<b>Estado:</b> %(state)s<br/>"
                        "<b>Error:</b> %(error)s"
                    ) % {
                        'state': log.state,
                        'error': log.error_message or '',
                    },
                    subtype_xmlid='mail.mt_note',
                )

            # ------------------------------------------------------
            # 8) Si no se pudo crear el log
            # ------------------------------------------------------
            else:
                record.message_post(
                    body=_(
                        "⚠️ No se pudo crear el registro de alerta de demora al jefe."
                    ),
                    subtype_xmlid='mail.mt_note',
                )

    # -------------------------------------------------------------------------
    # CRON
    # -------------------------------------------------------------------------

    @api.model
    def _cron_alertar_reparaciones_en_revision(self):
        """
        Cron:
        Busca reparaciones en revisión cuya próxima alerta ya venció.
        Envía WhatsApp al jefe de área cada intervalo configurado.
        """
        now = fields.Datetime.now()

        domain = [
            ('estado_id', '=', 'en_revision'),
            ('avance_alertas_activas', '=', True),
            ('fecha_proxima_alerta_avance', '!=', False),
            ('fecha_proxima_alerta_avance', '<=', now),
        ]

        reparaciones = self.search(domain, limit=100)

        _logger.info(
            "[DEMORA REPARACIÓN] Cron encontró %s reparaciones en revisión con alerta vencida",
            len(reparaciones),
        )

        for reparacion in reparaciones:
            try:
                reparacion._send_alerta_avance_jefe()
            except Exception as e:
                _logger.exception(
                    "[DEMORA REPARACIÓN] Error procesando alerta para reparación ID %s: %s",
                    reparacion.id,
                    e,
                )

        return True

    # -------------------------------------------------------------------------
    # ACCIONES UI
    # -------------------------------------------------------------------------

    def action_open_avances(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Demoras de reparación'),
            'res_model': 'reparacion.avance',
            'view_mode': 'list,form',
            'domain': [('reparacion_id', '=', self.id)],
            'context': {
                'default_reparacion_id': self.id,
            },
        }

    def action_generar_url_avance(self):
        self.ensure_one()

        url = self._get_avance_url()

        self.message_post(
            body=_(
                "🔗 URL para registrar demora generada:<br/>"
                "<a href='%(url)s' target='_blank'>%(url)s</a>"
            ) % {
                'url': url,
            },
            subtype_xmlid='mail.mt_note',
        )

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }