import json
import uuid
import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Contactos fijos
# ─────────────────────────────────────────────
GERENCIA_PHONE    = '51922541085'
GERENCIA_EMAIL    = 'campuero@corapsac.com'
LOGISTICA_PHONE   = '51999332773'
LOGISTICA_EMAIL   = 'logistica@corapsac.com'


class CopierPartsRequest(models.Model):
    _name        = 'copier.parts.request'
    _description = 'Solicitud de Partes de Fotocopiadora'
    _inherit     = ['mail.thread', 'mail.activity.mixin']
    _order       = 'fecha desc'

    # ─────────────────────────────────────────
    # Identificación
    # ─────────────────────────────────────────

    name = fields.Char(
        'Solicitud N°',
        default=lambda self: _('New'),
        readonly=True,
        required=True,
        copy=False,
        tracking=True,
    )
    fecha = fields.Date(
        'Fecha de Solicitud',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )

    # ─────────────────────────────────────────
    # Máquina
    # ─────────────────────────────────────────

    maquina_id = fields.Many2one(
        'sat.sat',
        string='Máquina',
        required=True,
        tracking=True,
    )
    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones',
        string='Reparación',
        domain="[('maquina_id', '=', maquina_id)]",
        tracking=True,
    )

    # Campos relacionados — store=True para búsquedas e historial
    proveedor   = fields.Char(related='maquina_id.proveedor_id.name', readonly=True, store=True)
    importacion = fields.Char(related='maquina_id.importacion',        readonly=True, store=True)
    marca       = fields.Char(related='maquina_id.marca',              readonly=True, store=True)
    modelo      = fields.Char(related='maquina_id.name.name',          readonly=True, store=True)
    serie       = fields.Char(related='maquina_id.serie_id',           readonly=True, store=True)
    contometro  = fields.Char(related='maquina_id.contometro',         readonly=True, store=True)

    # ─────────────────────────────────────────
    # Solicitante
    # ─────────────────────────────────────────

    solicitante_id = fields.Many2one(
        'res.users',
        string='Solicitante',
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )

    # ─────────────────────────────────────────
    # Partes solicitadas
    # ─────────────────────────────────────────

    disco_duro_requerido = fields.Boolean('Requiere Disco Duro', tracking=True)
    motivo_disco = fields.Selection([
        ('sin_disco', 'Llegó sin Disco'),
        ('malogrado', 'Disco Malogrado'),
    ], string='Motivo Solicitud Disco', tracking=True)

    ruedas_requeridas = fields.Boolean('Requiere Ruedas', tracking=True)
    cantidad_ruedas   = fields.Integer('Cantidad de Ruedas', default=4, readonly=True)

    cable_poder_requerido = fields.Boolean('Requiere Cable de Poder', tracking=True)
    motivo_cable = fields.Selection([
        ('sin_cable',  'Llegó sin Cable'),
        ('danado',     'Cable Dañado'),
        ('extraviado', 'Cable Extraviado'),
    ], string='Motivo Solicitud Cable', tracking=True)

    motivo_cable_display = fields.Char(
        string='Motivo Cable Display',
        compute='_compute_motivo_cable_display',
        store=True,
    )

    # ─────────────────────────────────────────
    # Estado
    # ─────────────────────────────────────────

    state = fields.Selection([
        ('draft',     'Pendiente'),
        ('approved',  'Aprobado'),
        ('delivered', 'Entregado'),
        ('rejected',  'Rechazado'),
    ], string='Estado', default='draft', tracking=True)

    # ─────────────────────────────────────────
    # Tokens de un solo uso
    # ─────────────────────────────────────────

    access_token = fields.Char(
        'Token de Acceso',
        copy=False,
        readonly=True,
        help="Token general del registro.",
    )
    token_gerencia = fields.Char(
        'Token Gerencia',
        copy=False,
        readonly=True,
        help="Token de un solo uso para aprobar/rechazar. Se invalida al usarse.",
    )
    token_logistica = fields.Char(
        'Token Logística',
        copy=False,
        readonly=True,
        help="Token de un solo uso para confirmar entrega. Se invalida al usarse.",
    )

    # ─────────────────────────────────────────
    # Trazabilidad
    # ─────────────────────────────────────────

    aprobado_fecha   = fields.Datetime('Fecha Aprobación',  readonly=True, tracking=True)
    entregado_fecha  = fields.Datetime('Fecha Entrega',     readonly=True, tracking=True)
    rechazado_fecha  = fields.Datetime('Fecha Rechazo',     readonly=True, tracking=True)

    # ─────────────────────────────────────────
    # Compute
    # ─────────────────────────────────────────

    @api.depends('motivo_cable')
    def _compute_motivo_cable_display(self):
        for record in self:
            record.motivo_cable_display = dict(
                self._fields['motivo_cable'].selection
            ).get(record.motivo_cable, '')

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    @staticmethod
    def _limpiar_telefono(phone):
        """
        Normaliza teléfono peruano a formato internacional sin '+'.
        Elimina cualquier carácter no numérico (guiones, paréntesis, espacios, etc.)
        antes de validar el prefijo de país.
        """
        if not phone:
            return ''
        import re
        phone = re.sub(r'\D', '', phone)   # solo dígitos
        if not phone.startswith('51'):
            phone = '51' + phone
        return phone

    def _get_phone_solicitante(self):
        """
        Obtiene el móvil del solicitante desde res.partner.
        El campo correcto en res.partner es 'mobile' (no mobile_phone,
        que pertenece a hr.employee).
        Fallback a 'phone' si 'mobile' está vacío.
        """
        self.ensure_one()
        if not self.solicitante_id:
            _logger.warning("Solicitud %s sin solicitante asignado.", self.name)
            return ''
        partner = self.solicitante_id.partner_id
        raw = partner.mobile or partner.phone or False
        _logger.debug(
            "Teléfono solicitante %s — mobile: %s | phone: %s | raw usado: %s",
            self.solicitante_id.name,
            partner.mobile,
            partner.phone,
            raw,
        )
        return self._limpiar_telefono(raw) if raw else ''

    def _get_base_url(self):
        return self.env['ir.config_parameter'].sudo().get_param('web.base.url')

    def _get_odoo_url(self):
        """URL directa al formulario en Odoo."""
        base_url = self._get_base_url()
        try:
            action_id = self.env.ref('sat.action_copier_parts_request').id
            return f"{base_url}/web#id={self.id}&view_type=form&model=copier.parts.request&action={action_id}"
        except Exception:
            return f"{base_url}/web#id={self.id}&view_type=form&model=copier.parts.request"

    def _get_partes_texto(self):
        """Retorna texto con las partes solicitadas para mensajes."""
        partes = []
        if self.disco_duro_requerido:
            motivo = self.get_motivo_disco_display()
            partes.append(f"  • Disco Duro ({motivo})" if motivo else "  • Disco Duro")
        if self.ruedas_requeridas:
            partes.append(f"  • Ruedas ({self.cantidad_ruedas} unidades)")
        if self.cable_poder_requerido:
            motivo = self.motivo_cable_display
            partes.append(f"  • Cable de Poder ({motivo})" if motivo else "  • Cable de Poder")
        return "\n".join(partes) if partes else "  (sin partes especificadas)"

    def get_motivo_disco_display(self):
        """Obtiene el texto del motivo de solicitud de disco."""
        return dict(self._fields['motivo_disco'].selection).get(self.motivo_disco, '')

    # ─────────────────────────────────────────
    # CRUD
    # ─────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('copier.parts.request')
                    or _('New')
                )
            # Generar los 3 tokens al crear
            vals['access_token']    = str(uuid.uuid4())
            vals['token_gerencia']  = str(uuid.uuid4())
            vals['token_logistica'] = str(uuid.uuid4())

        records = super().create(vals_list)

        for record in records:
            _logger.info(
                "Solicitud de partes creada: %s | solicitante: %s | máquina: %s",
                record.name,
                record.solicitante_id.name,
                record.maquina_id.name,
            )

            # Actualizar falla en reparación si aplica
            if record.disco_duro_requerido or record.cable_poder_requerido:
                record._actualizar_falla_proveedor()

            # Notificar a Gerencia (WhatsApp + Email)
            record._enviar_notificaciones_gerencia()

        return records

    # ─────────────────────────────────────────
    # Lógica interna de transiciones
    # ─────────────────────────────────────────

    def _aprobar(self):
        """
        Aprueba la solicitud.
        Llamado desde el controller HTTP con token de gerencia o desde botón en Odoo.

        Flujo al aprobar:
          1. Notifica a Logística para que aliste y entregue las partes.
          2. Notifica al técnico solicitante para que pase a recogerlas.
        """
        self.ensure_one()

        if self.state != 'draft':
            raise UserError(_('Esta solicitud ya fue procesada.'))

        self.write({
            'state':           'approved',
            'aprobado_fecha':  fields.Datetime.now(),
            'token_gerencia':  False,   # invalidar — uso único
        })

        _logger.info(
            "Solicitud %s aprobada. Notificando a Logística y al técnico solicitante.",
            self.name,
        )

        # 1. Notificar a Logística (WhatsApp + Email)
        self._enviar_notificaciones_logistica()

        # 2. Notificar al técnico solicitante que puede pasar a recoger
        self._enviar_notificaciones_tecnico_aprobacion()

        self.message_post(
            body=(
                "✅ Solicitud aprobada por Gerencia. "
                "Logística notificada para alistar las partes. "
                "Técnico notificado para pasar a recogerlas."
            )
        )
        _logger.info("Solicitud %s — notificaciones de aprobación enviadas.", self.name)

    def _rechazar(self):
        """
        Rechaza la solicitud.
        Llamado desde el controller HTTP con token de gerencia o desde botón en Odoo.
        """
        self.ensure_one()

        if self.state != 'draft':
            raise UserError(_('Esta solicitud ya fue procesada.'))

        self.write({
            'state':           'rejected',
            'rechazado_fecha': fields.Datetime.now(),
            'token_gerencia':  False,   # invalidar — uso único
        })

        _logger.info(
            "Solicitud %s rechazada. Notificando al técnico solicitante.",
            self.name,
        )

        # Notificar al técnico solicitante (WhatsApp + Email)
        self._enviar_notificaciones_rechazo()

        self.message_post(body="❌ Solicitud rechazada por Gerencia.")
        _logger.info("Solicitud %s — notificación de rechazo enviada.", self.name)

    def _confirmar_entrega(self):
        """
        Confirma la entrega física de las partes por parte de Logística.
        Llamado desde el controller HTTP con token de logística o desde botón en Odoo.

        En este paso NO se notifica al técnico porque ya fue avisado al momento
        de la aprobación. Solo se registra la confirmación en el chatter.
        """
        self.ensure_one()

        if self.state != 'approved':
            raise UserError(_('La solicitud debe estar aprobada para confirmar entrega.'))

        self.write({
            'state':           'delivered',
            'entregado_fecha': fields.Datetime.now(),
            'token_logistica': False,   # invalidar — uso único
        })

        self.message_post(
            body="📦 Logística confirmó la entrega física de las partes."
        )
        _logger.info(
            "Solicitud %s — entrega física confirmada por Logística.",
            self.name,
        )

    # ─────────────────────────────────────────
    # Falla proveedor
    # ─────────────────────────────────────────

    def _actualizar_falla_proveedor(self):
        """Actualiza el campo falla_proveedor en la reparación asociada."""
        self.ensure_one()
        fallas = []

        if self.disco_duro_requerido:
            descripcion_disco = (
                'Llegó sin disco duro'
                if self.motivo_disco == 'sin_disco'
                else 'Disco duro malogrado'
            )
            fallas.append(descripcion_disco)

        if self.cable_poder_requerido:
            motivos_cable = {
                'sin_cable':  'Llegó sin cable de poder',
                'danado':     'Cable de poder dañado',
                'extraviado': 'Cable de poder extraviado',
            }
            descripcion_cable = motivos_cable.get(self.motivo_cable, '')
            if descripcion_cable:
                fallas.append(descripcion_cable)

        if not fallas:
            return

        # Usar reparacion_id directo; fallback solo si existe exactamente una
        # reparación activa para no actualizar el registro equivocado
        reparacion = self.reparacion_id
        if not reparacion:
            reparaciones = self.env['reparaciones.reparaciones'].search([
                ('maquina_id', '=', self.maquina_id.id),
                ('state',      'not in', ['done', 'cancel']),
            ], limit=2)
            # Solo usar fallback si hay una única reparación activa
            if len(reparaciones) == 1:
                reparacion = reparaciones

        if reparacion:
            fallas_html = ''.join(f'<p>{falla}</p>' for falla in fallas)
            reparacion.write({'falla_proveedor': fallas_html})
            _logger.info(
                "falla_proveedor actualizado en reparación %s: %s",
                reparacion.name,
                fallas,
            )
        else:
            _logger.warning(
                "Solicitud %s: no se encontró reparación activa para actualizar falla_proveedor.",
                self.name,
            )

    # ─────────────────────────────────────────
    # Notificaciones — WhatsApp
    # ─────────────────────────────────────────

    def _enviar_whatsapp_gerencia(self):
        """WhatsApp a Gerencia con links aprobar/rechazar."""
        self.ensure_one()
        base_url = self._get_base_url()
        url_aprobar  = f"{base_url}/parts/gerencia/{self.token_gerencia}/aprobar"
        url_rechazar = f"{base_url}/parts/gerencia/{self.token_gerencia}/rechazar"

        msg = (
            f"🖨️ *Nueva Solicitud de Partes*\n\n"
            f"*Solicitud:* {self.name}\n"
            f"*Solicitante:* {self.solicitante_id.name}\n\n"
            f"*Máquina:* {self.marca} {self.modelo}\n"
            f"*Serie:* {self.serie}\n\n"
            f"*Partes solicitadas:*\n{self._get_partes_texto()}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ *APROBAR:*\n{url_aprobar}\n\n"
            f"❌ *RECHAZAR:*\n{url_rechazar}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ Cada link es de uso único."
        )
        _logger.info(
            "Enviando WhatsApp a Gerencia (%s) para solicitud %s.",
            GERENCIA_PHONE, self.name,
        )
        self.send_whatsapp_message(GERENCIA_PHONE, msg)

    def _enviar_whatsapp_logistica(self):
        """WhatsApp a Logística con link confirmar entrega."""
        self.ensure_one()
        base_url = self._get_base_url()
        url_entrega = f"{base_url}/parts/logistica/{self.token_logistica}/entregar"

        msg = (
            f"📦 *Solicitud de Partes Aprobada*\n\n"
            f"*Solicitud:* {self.name}\n"
            f"*Solicitante:* {self.solicitante_id.name}\n\n"
            f"*Máquina:* {self.marca} {self.modelo}\n"
            f"*Serie:* {self.serie}\n\n"
            f"*Partes a alistar y entregar:*\n{self._get_partes_texto()}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📬 *CONFIRMAR ENTREGA:*\n{url_entrega}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ Este link es de uso único."
        )
        _logger.info(
            "Enviando WhatsApp a Logística (%s) para solicitud %s.",
            LOGISTICA_PHONE, self.name,
        )
        self.send_whatsapp_message(LOGISTICA_PHONE, msg)

    def _enviar_whatsapp_tecnico_aprobacion(self):
        """
        WhatsApp al técnico solicitante cuando Gerencia aprueba la solicitud.
        Le indica que puede pasar a recoger las partes al área de Logística.
        """
        self.ensure_one()
        phone = self._get_phone_solicitante()
        if not phone:
            _logger.warning(
                "Solicitud %s: solicitante %s sin teléfono móvil. "
                "No se pudo enviar WhatsApp de aprobación al técnico.",
                self.name,
                self.solicitante_id.name,
            )
            self.message_post(
                body=(
                    f"⚠️ No se pudo notificar por WhatsApp a "
                    f"<b>{self.solicitante_id.name}</b>: "
                    f"no tiene teléfono móvil registrado en su contacto."
                )
            )
            return

        msg = (
            f"✅ *Solicitud de Partes Aprobada*\n\n"
            f"Hola *{self.solicitante_id.name}*,\n\n"
            f"Tu solicitud *{self.name}* fue *aprobada* por Gerencia.\n\n"
            f"*Partes aprobadas:*\n{self._get_partes_texto()}\n\n"
            f"*Máquina:* {self.marca} {self.modelo}\n"
            f"*Serie:* {self.serie}\n\n"
            f"Puedes pasar a recogerlas al área de *Logística*. 🏪"
        )
        _logger.info(
            "Enviando WhatsApp de aprobación al técnico %s (%s) para solicitud %s.",
            self.solicitante_id.name, phone, self.name,
        )
        self.send_whatsapp_message(phone, msg)

    def _enviar_whatsapp_tecnico_rechazo(self):
        """WhatsApp al técnico solicitante cuando la solicitud es rechazada."""
        self.ensure_one()
        phone = self._get_phone_solicitante()
        if not phone:
            _logger.warning(
                "Solicitud %s: solicitante %s sin teléfono móvil. "
                "No se pudo enviar WhatsApp de rechazo al técnico.",
                self.name,
                self.solicitante_id.name,
            )
            self.message_post(
                body=(
                    f"⚠️ No se pudo notificar por WhatsApp a "
                    f"<b>{self.solicitante_id.name}</b>: "
                    f"no tiene teléfono móvil registrado en su contacto."
                )
            )
            return

        msg = (
            f"❌ *Solicitud de Partes Rechazada*\n\n"
            f"Hola *{self.solicitante_id.name}*,\n\n"
            f"Tu solicitud *{self.name}* fue *rechazada* por Gerencia.\n\n"
            f"*Máquina:* {self.marca} {self.modelo}\n"
            f"*Serie:* {self.serie}\n\n"
            f"Comunícate con tu supervisor para más información."
        )
        _logger.info(
            "Enviando WhatsApp de rechazo al técnico %s (%s) para solicitud %s.",
            self.solicitante_id.name, phone, self.name,
        )
        self.send_whatsapp_message(phone, msg)

    # ─────────────────────────────────────────
    # Notificaciones — Email
    # ─────────────────────────────────────────

    def _enviar_email(self, template_xml_id, ctx=None):
        """Envía email usando un mail.template existente."""
        self.ensure_one()
        try:
            template = self.env.ref(template_xml_id, raise_if_not_found=False)
            if not template:
                _logger.warning(
                    "Template de email %s no encontrado. Email no enviado.",
                    template_xml_id,
                )
                return
            template.with_context(**(ctx or {})).send_mail(
                self.id,
                force_send=True,
                raise_exception=False,
            )
            _logger.info(
                "Email [%s] enviado para solicitud %s.",
                template_xml_id, self.name,
            )
        except Exception as e:
            _logger.error(
                "Error enviando email [%s] para solicitud %s: %s",
                template_xml_id, self.name, e,
            )

    # ─────────────────────────────────────────
    # Notificaciones — combinadas (WhatsApp + Email)
    # ─────────────────────────────────────────

    def _enviar_notificaciones_gerencia(self):
        """Notifica a Gerencia al crear la solicitud."""
        self.ensure_one()
        _logger.info("Notificando a Gerencia — solicitud %s.", self.name)
        base_url = self._get_base_url()
        self._enviar_whatsapp_gerencia()
        self._enviar_email(
            'sat.email_template_copier_parts_gerencia',
            ctx={
                'url_aprobar':  f"{base_url}/parts/gerencia/{self.token_gerencia}/aprobar",
                'url_rechazar': f"{base_url}/parts/gerencia/{self.token_gerencia}/rechazar",
            }
        )

    def _enviar_notificaciones_logistica(self):
        """Notifica a Logística cuando Gerencia aprueba."""
        self.ensure_one()
        _logger.info("Notificando a Logística — solicitud %s.", self.name)
        base_url = self._get_base_url()
        self._enviar_whatsapp_logistica()
        self._enviar_email(
            'sat.email_template_copier_parts_logistica',
            ctx={
                'url_entrega': f"{base_url}/parts/logistica/{self.token_logistica}/entregar",
            }
        )

    def _enviar_notificaciones_tecnico_aprobacion(self):
        """
        Notifica al técnico cuando Gerencia aprueba su solicitud.
        Le avisa que puede pasar a recoger las partes a Logística.
        """
        self.ensure_one()
        _logger.info(
            "Notificando al técnico %s — solicitud %s aprobada.",
            self.solicitante_id.name, self.name,
        )
        self._enviar_whatsapp_tecnico_aprobacion()
        self._enviar_email('sat.email_template_copier_parts_tecnico_aprobacion')

    def _enviar_notificaciones_rechazo(self):
        """Notifica al técnico cuando Gerencia rechaza su solicitud."""
        self.ensure_one()
        _logger.info(
            "Notificando al técnico %s — solicitud %s rechazada.",
            self.solicitante_id.name, self.name,
        )
        self._enviar_whatsapp_tecnico_rechazo()
        self._enviar_email('sat.email_template_copier_parts_rechazo')

    # ─────────────────────────────────────────
    # API WhatsApp
    # ─────────────────────────────────────────

    def send_whatsapp_message(self, phone, message):
        """Envía mensaje WhatsApp via API externa."""
        url = 'https://boot.andessolutioncopiers.com/api/send-message'
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': 'sk_2312cac15276b4a3ca124e66a78fdde6428c626eb7184f26d3fa62037aaae816',
        }
        data = {'to': phone, 'message': message}

        _logger.info("WhatsApp → enviando a %s...", phone)

        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            _logger.info(
                "WhatsApp ← status %s para %s.", response.status_code, phone,
            )

            try:
                response_json = response.json()
                if response.status_code == 200 and response_json.get('success'):
                    _logger.info("✅ WhatsApp enviado correctamente a %s.", phone)
                    return response_json
                error_msg = response_json.get('error', 'Error desconocido')
                _logger.error(
                    "❌ API WhatsApp respondió con error para %s: %s", phone, error_msg,
                )
                return {'error': error_msg, 'success': False}

            except json.JSONDecodeError as e:
                _logger.error(
                    "❌ WhatsApp respuesta no-JSON para %s: %s", phone, response.text,
                )
                return {'error': str(e), 'success': False}

        except requests.exceptions.Timeout:
            _logger.error("❌ Timeout al enviar WhatsApp a %s.", phone)
            return {'error': 'Timeout', 'success': False}

        except requests.exceptions.RequestException as e:
            _logger.error("❌ Error de red al enviar WhatsApp a %s: %s", phone, str(e))
            return {'error': str(e), 'success': False}

        except Exception as e:
            _logger.error("❌ Excepción inesperada al enviar WhatsApp a %s: %s", phone, str(e))
            return {'error': str(e), 'success': False}

    # ─────────────────────────────────────────
    # Acciones desde Odoo (botones)
    # ─────────────────────────────────────────

    def action_approve(self):
        """Aprobar desde Odoo (botón) — sin token, solo usuario autorizado."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Esta solicitud ya fue procesada.'))
        self._aprobar()

    def action_deliver(self):
        """Confirmar entrega desde Odoo (botón) — sin token, solo usuario autorizado."""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('La solicitud debe estar aprobada para confirmar entrega.'))
        self._confirmar_entrega()

    def action_reject(self):
        """Rechazar desde Odoo (botón)."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Esta solicitud ya fue procesada.'))
        self._rechazar()


# ─────────────────────────────────────────────────────────────────────────────
# WIZARD
# ─────────────────────────────────────────────────────────────────────────────

class PartsRequestWizard(models.TransientModel):
    _name        = 'copier.parts.request.wizard'
    _description = 'Asistente de Solicitud de Partes'

    # Máquina (readonly — viene del contexto)
    reparacion_id = fields.Many2one('reparaciones.reparaciones', string='Reparación', readonly=True)
    maquina_id    = fields.Many2one('sat.sat', string='Máquina', required=True, readonly=True)
    proveedor     = fields.Char(related='maquina_id.proveedor_id.name', readonly=True)
    importacion   = fields.Char(related='maquina_id.importacion',       readonly=True)
    marca         = fields.Char(related='maquina_id.marca',             readonly=True)
    modelo        = fields.Char(related='maquina_id.name.name',         readonly=True)
    serie         = fields.Char(related='maquina_id.serie_id',          readonly=True)
    contometro    = fields.Char(related='maquina_id.contometro',        readonly=True)

    # Partes
    disco_duro_requerido = fields.Boolean('Requiere Disco Duro')
    motivo_disco = fields.Selection([
        ('sin_disco', 'Llegó sin Disco'),
        ('malogrado', 'Disco Malogrado'),
    ], string='Motivo Solicitud Disco')

    ruedas_requeridas = fields.Boolean('Requiere Ruedas')
    cantidad_ruedas   = fields.Integer('Cantidad de Ruedas', default=4)

    cable_poder_requerido = fields.Boolean('Requiere Cable de Poder')
    motivo_cable = fields.Selection([
        ('sin_cable',  'Llegó sin Cable'),
        ('danado',     'Cable Dañado'),
        ('extraviado', 'Cable Extraviado'),
    ], string='Motivo Solicitud Cable')

    notas = fields.Text('Notas Adicionales')

    # ─────────────────────────────────────────
    # Onchange
    # ─────────────────────────────────────────

    @api.onchange('disco_duro_requerido')
    def _onchange_disco_duro(self):
        if not self.disco_duro_requerido:
            self.motivo_disco = False

    @api.onchange('ruedas_requeridas')
    def _onchange_ruedas(self):
        if not self.ruedas_requeridas:
            self.cantidad_ruedas = 0
        else:
            self.cantidad_ruedas = 4

    @api.onchange('cable_poder_requerido')
    def _onchange_cable_poder(self):
        if not self.cable_poder_requerido:
            self.motivo_cable = False

    # ─────────────────────────────────────────
    # Validaciones
    # ─────────────────────────────────────────

    @api.constrains(
        'disco_duro_requerido', 'ruedas_requeridas',
        'cable_poder_requerido', 'motivo_disco', 'motivo_cable'
    )
    def _check_required_fields(self):
        for record in self:
            if not any([
                record.disco_duro_requerido,
                record.ruedas_requeridas,
                record.cable_poder_requerido,
            ]):
                raise ValidationError(
                    _('Debe seleccionar al menos una parte: Disco Duro, Ruedas o Cable de Poder.')
                )
            if record.disco_duro_requerido and not record.motivo_disco:
                raise ValidationError(
                    _('Debe seleccionar el motivo de la solicitud del Disco Duro.')
                )
            if record.cable_poder_requerido and not record.motivo_cable:
                raise ValidationError(
                    _('Debe seleccionar el motivo de la solicitud del Cable de Poder.')
                )

    # ─────────────────────────────────────────
    # Acción
    # ─────────────────────────────────────────

    def action_create_request(self):
        self.ensure_one()

        vals = {
            'maquina_id':             self.maquina_id.id,
            'reparacion_id':          self.reparacion_id.id if self.reparacion_id else False,
            'disco_duro_requerido':   self.disco_duro_requerido,
            'motivo_disco':           self.motivo_disco,
            'ruedas_requeridas':      self.ruedas_requeridas,
            'cantidad_ruedas':        self.cantidad_ruedas if self.ruedas_requeridas else 0,
            'cable_poder_requerido':  self.cable_poder_requerido,
            'motivo_cable':           self.motivo_cable,
        }

        record = self.env['copier.parts.request'].create(vals)

        # Mensaje en el chatter de la reparación
        if self.reparacion_id:
            msg = "<b>Solicitud de Partes Creada:</b><br/>"
            if self.disco_duro_requerido:
                msg += (
                    f"- Disco Duro: "
                    f"{dict(self._fields['motivo_disco'].selection).get(self.motivo_disco, '')}<br/>"
                )
            if self.ruedas_requeridas:
                msg += f"- Ruedas: {self.cantidad_ruedas}<br/>"
            if self.cable_poder_requerido:
                msg += (
                    f"- Cable de Poder: "
                    f"{dict(self._fields['motivo_cable'].selection).get(self.motivo_cable, '')}<br/>"
                )
            if self.notas:
                msg += f"<b>Notas:</b><br/>{self.notas}"
            self.reparacion_id.message_post(body=msg)
            _logger.info(
                "Mensaje de solicitud de partes posteado en reparación %s.",
                self.reparacion_id.name,
            )

        return {
            'type':      'ir.actions.act_window',
            'res_model': 'copier.parts.request',
            'res_id':    record.id,
            'view_mode': 'form',
            'target':    'current',
        }