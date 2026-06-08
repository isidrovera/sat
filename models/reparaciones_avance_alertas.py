# -*- coding: utf-8 -*-

import logging
import uuid
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ReparacionAvanceOpcion(models.Model):
    _name = 'reparacion.avance.opcion'
    _description = 'Opción de Avance de Reparación'
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
    _description = 'Avance de Reparación'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Referencia',
        default=lambda self: _('Nuevo avance'),
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
        string='Opciones de avance',
    )

    detalle = fields.Text(
        string='Detalle adicional',
    )

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'reparacion_avance_ir_attachment_rel',
        'avance_id',
        'attachment_id',
        string='Fotos / Adjuntos',
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
            if record.name == _('Nuevo avance'):
                record.name = _('Avance %s') % record.id

            try:
                record.reparacion_id._after_avance_registrado(record)
            except Exception as e:
                _logger.exception(
                    "[AVANCE REPARACIÓN] Error actualizando reparación después de registrar avance %s: %s",
                    record.id,
                    e,
                )

            if record.notificar_asesora:
                try:
                    record.action_notificar_asesora()
                except Exception as e:
                    _logger.exception(
                        "[AVANCE REPARACIÓN] Error notificando asesora desde avance %s: %s",
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
        gallery_url = reparacion._get_gallery_url() if hasattr(reparacion, '_get_gallery_url') else ''
        record_url = reparacion._get_action_record_url() if hasattr(reparacion, '_get_action_record_url') else ''

        cliente = reparacion.cliente_id.name if reparacion.cliente_id else 'NA'
        tecnico = reparacion.responsable_id.name if reparacion.responsable_id else 'NA'
        modelo = reparacion.nombre_maquina or 'NA'
        serie = reparacion.serie_id or 'NA'

        opciones = self._get_option_texts()
        opciones_txt = "\n".join([f"- {item}" for item in opciones]) if opciones else "- Avance registrado"

        detalle = self.detalle or 'Sin detalle adicional.'

        msg = f"""*Avance de reparación*

*Cliente:* {cliente}
*Modelo:* {modelo}
*Serie:* {serie}
*Técnico:* {tecnico}
*Estado actual:* En revisión

*Avance reportado:*
{opciones_txt}

*Detalle:*
{detalle}

*Enlaces:*
Fotos: {gallery_url}
Registro: {record_url}
"""

        return msg

    def action_notificar_asesora(self):
        """
        Notifica el avance a la asesora.
        Esta acción se ejecuta cuando el jefe o usuario autorizado decide informar.
        """
        for record in self:
            reparacion = record.reparacion_id

            if not reparacion:
                continue

            if not hasattr(reparacion, 'send_whatsapp_message'):
                raise UserError(_("No se encontró el método send_whatsapp_message en reparaciones."))

            if not reparacion.asesora_mobile_clean:
                record.write({
                    'estado': 'error',
                    'error_notificacion': _('La asesora no tiene número móvil configurado.'),
                })
                reparacion.message_post(
                    body=_(
                        "⚠️ No se notificó el avance a la asesora porque no tiene número móvil configurado."
                    )
                )
                continue

            msg = record._build_msg_asesora()
            result = reparacion.send_whatsapp_message(reparacion.asesora_mobile_clean, msg)

            if result.get('success'):
                record.write({
                    'asesora_notificada': True,
                    'fecha_notificacion_asesora': fields.Datetime.now(),
                    'estado': 'notificado',
                    'error_notificacion': False,
                })

                reparacion.message_post(
                    body=_(
                        "✅ Avance notificado a la asesora por WhatsApp.<br/>"
                        "<b>Avance:</b> %(avance)s"
                    ) % {
                        'avance': record.display_name,
                    }
                )
            else:
                error = result.get('error', 'Error desconocido')
                record.write({
                    'estado': 'error',
                    'error_notificacion': error,
                })

                reparacion.message_post(
                    body=_(
                        "⚠️ No se pudo notificar el avance a la asesora.<br/>"
                        "<b>Error:</b> %(error)s"
                    ) % {
                        'error': error,
                    }
                )


class ReparacionAvanceLinea(models.Model):
    _name = 'reparacion.avance.linea'
    _description = 'Línea de Avance de Reparación'
    _order = 'id'

    avance_id = fields.Many2one(
        'reparacion.avance',
        string='Avance',
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
        string='Avances',
    )

    avance_count = fields.Integer(
        string='Cantidad de avances',
        compute='_compute_avance_count',
    )

    avance_token = fields.Char(
        string='Token de avance',
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
        string='Último avance',
        copy=False,
        tracking=True,
    )

    fecha_proxima_alerta_avance = fields.Datetime(
        string='Próxima alerta de avance',
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
        string='Alertas de avance activas',
        default=True,
        copy=False,
    )

    avance_estado_alerta = fields.Selection(
        [
            ('sin_alerta', 'Sin alerta'),
            ('pendiente', 'Pendiente de avance'),
            ('alertado_jefe', 'Jefe alertado'),
            ('con_avance', 'Con avance'),
            ('cerrado', 'Cerrado'),
        ],
        string='Estado alerta de avance',
        default='sin_alerta',
        copy=False,
        tracking=True,
    )

    jefe_area_user_id = fields.Many2one(
        'res.users',
        string='Jefe de área para alertas',
        copy=False,
        help='Si se configura, se usará su móvil/partner para enviar alertas. Si está vacío, se usará el parámetro del sistema.',
    )

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
            if phone and not phone.startswith('51'):
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
        Prepara control de avance cuando una reparación entra en revisión.
        No cambia tu lógica de reparación; solo registra fechas para alertas.
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
    # REGISTRO DE AVANCE
    # -------------------------------------------------------------------------

    def _after_avance_registrado(self, avance):
        """
        Se ejecuta después de registrar un avance.
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
        options_html = "<br/>".join(["- %s" % item for item in option_texts]) if option_texts else _("Avance registrado")

        self.message_post(
            body=_(
                "📝 <b>Avance registrado</b><br/>"
                "%(options)s<br/>"
                "<br/>"
                "<b>Detalle:</b><br/>%(detalle)s"
            ) % {
                'options': options_html,
                'detalle': avance.detalle or _('Sin detalle adicional.'),
            }
        )

    def create_avance_rapido(self, option_data=None, detalle=False, attachment_ids=None, notificar_asesora=False):
        """
        Método helper para que el controller cree avances rápido.

        option_data esperado:
        [
            {
                'opcion_id': 1,
                'color': 'black',
                'parte': 'Fusor',
                'detalle': '...'
            }
        ]
        """
        self.ensure_one()

        option_data = option_data or []
        attachment_ids = attachment_ids or []

        line_vals = []

        for item in option_data:
            opcion_id = item.get('opcion_id')
            if not opcion_id:
                continue

            line_vals.append((0, 0, {
                'opcion_id': opcion_id,
                'color': item.get('color') or False,
                'parte': item.get('parte') or False,
                'detalle': item.get('detalle') or False,
            }))

        avance = self.env['reparacion.avance'].sudo().create({
            'reparacion_id': self.id,
            'detalle': detalle or False,
            'line_ids': line_vals,
            'attachment_ids': [(6, 0, attachment_ids)] if attachment_ids else False,
            'notificar_asesora': bool(notificar_asesora),
        })

        return avance

    # -------------------------------------------------------------------------
    # MENSAJE AL JEFE DE ÁREA
    # -------------------------------------------------------------------------

    def _build_msg_alerta_jefe_avance(self):
        self.ensure_one()

        avance_url = self._get_avance_url()
        gallery_url = self._get_gallery_url() if hasattr(self, '_get_gallery_url') else ''

        cliente = self.cliente_id.name if self.cliente_id else 'NA'
        tecnico = self.responsable_id.name if self.responsable_id else 'NA'
        modelo = self.nombre_maquina or 'NA'
        serie = self.serie_id or 'NA'

        alertas = self.cantidad_alertas_avance_jefe + 1

        msg = f"""*Alerta de avance pendiente*

La reparación continúa en revisión y requiere actualización de avance.

*Cliente:* {cliente}
*Modelo:* {modelo}
*Serie:* {serie}
*Técnico:* {tecnico}
*Reparación:* {self.name or 'NA'}
*Alerta N°:* {alertas}

El jefe de área debe registrar el avance o decidir qué informar a la asesora.

*Registrar avance:*
{avance_url}

*Fotos actuales:*
{gallery_url}
"""

        return msg

    def _send_alerta_avance_jefe(self):
        """
        Envía alerta al jefe de área.
        No notifica directamente a la asesora.
        """
        for record in self:
            if record.estado_id != 'en_revision':
                continue

            if not hasattr(record, 'send_whatsapp_message'):
                _logger.error(
                    "[AVANCE REPARACIÓN] No existe send_whatsapp_message en reparación ID %s",
                    record.id,
                )
                continue

            phone = record._get_jefe_area_phone()
            if not phone:
                record.message_post(
                    body=_(
                        "⚠️ No se pudo enviar alerta de avance porque no hay teléfono configurado para el jefe de área.<br/>"
                        "Configure sat.reparaciones_avance_jefe_phone o sat.reparaciones_avance_jefe_user_id."
                    )
                )
                continue

            msg = record._build_msg_alerta_jefe_avance()
            result = record.send_whatsapp_message(phone, msg)

            if result.get('success'):
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
                        "⏰ Alerta de avance enviada al jefe de área.<br/>"
                        "<b>Número:</b> %(phone)s<br/>"
                        "<b>Próxima alerta:</b> %(next)s"
                    ) % {
                        'phone': phone,
                        'next': record.fecha_proxima_alerta_avance,
                    }
                )
            else:
                record.message_post(
                    body=_(
                        "⚠️ No se pudo enviar alerta de avance al jefe de área.<br/>"
                        "<b>Número:</b> %(phone)s<br/>"
                        "<b>Error:</b> %(error)s"
                    ) % {
                        'phone': phone,
                        'error': result.get('error', 'Error desconocido'),
                    }
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
            "[AVANCE REPARACIÓN] Cron encontró %s reparaciones en revisión con alerta vencida",
            len(reparaciones),
        )

        for reparacion in reparaciones:
            try:
                reparacion._send_alerta_avance_jefe()
            except Exception as e:
                _logger.exception(
                    "[AVANCE REPARACIÓN] Error procesando alerta para reparación ID %s: %s",
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
            'name': _('Avances de reparación'),
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
                "🔗 URL de avance generada:<br/>"
                "<a href='%(url)s' target='_blank'>%(url)s</a>"
            ) % {
                'url': url,
            }
        )

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }