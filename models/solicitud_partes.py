import uuid
import requests
from datetime import timedelta
from odoo import _, models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

# Número de gerencia fijo
GERENCIA_PHONE = '51922541085'


class SolicitudPartes(models.Model):
    _name = 'solicitud.partes'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Solicitud de Partes'
    _order = 'fecha_solicitud desc, id desc'

    # -------------------------------------------------------------------------
    # Campos básicos
    # -------------------------------------------------------------------------

    name = fields.Char(
        string='Número de Solicitud',
        readonly=True,
        copy=False,
        default='Nuevo'
    )

    maquina_origen_id = fields.Many2one(
        'alquiler',
        string='Máquina Origen',
        required=True,
        tracking=True,
        domain="[('estado_alquiler_id', 'not in', ['vendida', 'partes'])]"
    )
    maquina_destino_id = fields.Many2one(
        'alquiler',
        string='Máquina Destino',
        tracking=True,
        domain="[('id', '!=', maquina_origen_id), ('estado_alquiler_id', 'not in', ['vendida'])]"
    )

    fecha_solicitud = fields.Datetime(
        string='Fecha de Solicitud',
        default=fields.Datetime.now,
        tracking=True,
        readonly=True
    )
    solicitante_id = fields.Many2one(
        'res.users',
        string='Solicitante',
        default=lambda self: self.env.user,
        tracking=True,
        readonly=True
    )

    # -------------------------------------------------------------------------
    # Estado
    # -------------------------------------------------------------------------

    state = fields.Selection([
        ('draft',     'Borrador'),
        ('submitted', 'Enviado'),
        ('approved',  'Aprobado'),
        ('completed', 'Completado'),
        ('replaced',  'Reemplazado'),
        ('rejected',  'Rechazado'),
    ], string='Estado', default='draft', tracking=True)

    # -------------------------------------------------------------------------
    # Tokens — uso único
    # -------------------------------------------------------------------------

    access_token = fields.Char(
        string='Token de Acceso',
        copy=False,
        readonly=True,
        help="Token para retiro y reposición. Se genera al crear."
    )
    token_gerencia = fields.Char(
        string='Token Gerencia',
        copy=False,
        readonly=True,
        help="Token de un solo uso para aprobación/rechazo por Gerencia. "
             "Se invalida al ser usado."
    )

    # -------------------------------------------------------------------------
    # Responsables
    # -------------------------------------------------------------------------

    # Quien aprueba (gerencia)
    autorizado_por = fields.Many2one(
        'res.users',
        string='Autorizado por',
        tracking=True,
        readonly=True
    )
    fecha_autorizacion = fields.Datetime(
        string='Fecha de Autorización',
        tracking=True,
        readonly=True
    )

    # Técnico asignado para retirar (lo elige gerencia al aprobar)
    tecnico_asignado_id = fields.Many2one(
        'res.users',
        string='Técnico Asignado para Retiro',
        tracking=True,
        help="Técnico que realizará el retiro físico de las partes."
    )
    tecnico_asignado_mobile_clean = fields.Char(
        string='Teléfono Técnico (limpio)',
        compute='_compute_tecnico_mobile_clean',
        store=True
    )

    # Responsable de reposición (campo fijo en la solicitud)
    responsable_reposicion_id = fields.Many2one(
        'res.users',
        string='Responsable de Reposición',
        tracking=True,
        help="Usuario que recibirá e instalará la parte nueva."
    )
    responsable_reposicion_mobile_clean = fields.Char(
        string='Teléfono Responsable Reposición (limpio)',
        compute='_compute_responsable_mobile_clean',
        store=True
    )

    # Campos de retiro (cabecera)
    retirado_por = fields.Many2one(
        'res.users',
        string='Retirado por',
        tracking=True,
        readonly=True
    )
    fecha_retiro = fields.Datetime(
        string='Fecha de Retiro',
        tracking=True,
        readonly=True
    )

    # Campos de reemplazo (cabecera)
    reemplazado_por = fields.Many2one(
        'res.users',
        string='Reemplazado por',
        tracking=True,
        readonly=True
    )
    fecha_reemplazo = fields.Datetime(
        string='Fecha de Reemplazo',
        tracking=True,
        readonly=True
    )

    # -------------------------------------------------------------------------
    # Líneas
    # -------------------------------------------------------------------------

    parte_ids = fields.One2many(
        'solicitud.partes.linea',
        'solicitud_id',
        string='Partes Solicitadas'
    )

    # -------------------------------------------------------------------------
    # Computed: estados agregados de líneas
    # -------------------------------------------------------------------------

    todas_retiradas = fields.Boolean(
        string='Todas Retiradas',
        compute='_compute_estado_partes',
        store=True
    )
    todas_repuestas = fields.Boolean(
        string='Todas Repuestas',
        compute='_compute_estado_partes',
        store=True
    )

    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------

    @api.depends('tecnico_asignado_id.mobile_phone')
    def _compute_tecnico_mobile_clean(self):
        for record in self:
            record.tecnico_asignado_mobile_clean = self._limpiar_telefono(
                record.tecnico_asignado_id.mobile_phone
                if record.tecnico_asignado_id else False
            )

    @api.depends('responsable_reposicion_id.mobile_phone')
    def _compute_responsable_mobile_clean(self):
        for record in self:
            record.responsable_reposicion_mobile_clean = self._limpiar_telefono(
                record.responsable_reposicion_id.mobile_phone
                if record.responsable_reposicion_id else False
            )

    @api.depends('parte_ids.estado')
    def _compute_estado_partes(self):
        for record in self:
            if not record.parte_ids:
                record.todas_retiradas = False
                record.todas_repuestas = False
                continue
            record.todas_retiradas = all(
                l.estado in ['retirado', 'reemplazado'] for l in record.parte_ids
            )
            record.todas_repuestas = all(
                l.estado == 'reemplazado' for l in record.parte_ids
            )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _limpiar_telefono(phone):
        """Normaliza teléfono peruano a formato internacional sin '+'."""
        if not phone:
            return ''
        phone = phone.replace('+', '').replace(' ', '').strip()
        if not phone.startswith('51'):
            phone = '51' + phone
        return phone

    def _get_base_url(self):
        return self.env['ir.config_parameter'].sudo().get_param('web.base.url')

    def _get_odoo_url(self):
        """URL directa al formulario en Odoo."""
        base_url = self._get_base_url()
        action_id = self.env.ref('sat.action_solicitud_partes').id
        return f"{base_url}/web#id={self.id}&view_type=form&model=solicitud.partes&action={action_id}"

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model
    def create(self, vals):
        if vals.get('name', 'Nuevo') == 'Nuevo':
            vals['name'] = self.env['ir.sequence'].next_by_code('solicitud.partes') or 'Nuevo'
        # Generar ambos tokens al crear
        vals['access_token']   = uuid.uuid4().hex
        vals['token_gerencia'] = uuid.uuid4().hex
        record = super().create(vals)
        # Notificar a gerencia inmediatamente
        record._enviar_whatsapp_gerencia()
        record.write({'state': 'submitted'})
        return record

    # -------------------------------------------------------------------------
    # Acciones desde Odoo (botones)
    # -------------------------------------------------------------------------

    def action_reject(self):
        """Rechazar desde Odoo (botón)."""
        self.ensure_one()
        self._rechazar()

    def action_complete(self):
        """Completar manualmente desde Odoo si todas las partes están retiradas."""
        self.ensure_one()
        if not self.todas_retiradas:
            raise UserError(_('Todas las partes deben estar retiradas o reemplazadas.'))
        self._completar_retiro()

    def action_replace(self):
        """Marcar como Reemplazado manualmente desde Odoo."""
        self.ensure_one()
        if not self.todas_repuestas:
            raise UserError(_('Todas las partes deben estar reemplazadas.'))
        self._completar_reposicion()

    # -------------------------------------------------------------------------
    # Lógica interna de transiciones
    # -------------------------------------------------------------------------

    def _rechazar(self):
        """Rechaza la solicitud e invalida token de gerencia."""
        self.ensure_one()
        self.write({
            'state':          'rejected',
            'token_gerencia': False,  # invalidar token
        })
        self.message_post(body="❌ Solicitud rechazada.")
        _logger.info("Solicitud %s rechazada.", self.name)

    def _aprobar(self, tecnico_asignado_id):
        """
        Aprueba la solicitud asignando el técnico que retirará.
        Llamado desde el controller HTTP (token de gerencia).
        """
        self.ensure_one()

        if self.state != 'submitted':
            raise UserError(_('Esta solicitud ya fue procesada.'))

        self.write({
            'state':               'approved',
            'autorizado_por':      self.env.ref('base.user_admin').id,
            'fecha_autorizacion':  fields.Datetime.now(),
            'tecnico_asignado_id': tecnico_asignado_id,
            'token_gerencia':      False,  # invalidar token — uso único
        })

        # Notificar al solicitante
        self._enviar_whatsapp_solicitante_aprobado()

        # Notificar al técnico asignado con link de retiro
        self._enviar_whatsapp_tecnico_retiro()

        self.message_post(
            body=(
                f"✅ Solicitud aprobada. "
                f"Técnico asignado para retiro: {self.tecnico_asignado_id.name}"
            )
        )
        _logger.info("Solicitud %s aprobada. Técnico: %s", self.name, self.tecnico_asignado_id.name)

    def _completar_retiro(self):
        """Marca la solicitud como completada (todas las partes retiradas)."""
        self.ensure_one()
        self.write({
            'state':        'completed',
            'retirado_por': self.tecnico_asignado_id.id,
            'fecha_retiro': fields.Datetime.now(),
        })
        self.maquina_origen_id.write({'estado_alquiler_id': 'con_problemas'})

        # Notificar al responsable de reposición
        if self.responsable_reposicion_id:
            self._enviar_whatsapp_responsable_reposicion()

        self.message_post(body="📦 Todas las partes retiradas. Reposición pendiente.")
        _logger.info("Solicitud %s completada — retiro total.", self.name)

    def _completar_reposicion(self):
        """Marca la solicitud como reemplazada (todas las partes repuestas)."""
        self.ensure_one()
        self.write({
            'state':           'replaced',
            'reemplazado_por': self.env.user.id,
            'fecha_reemplazo': fields.Datetime.now(),
        })
        if all(l.condicion == 'bueno' for l in self.parte_ids):
            self.maquina_origen_id.write({'estado_alquiler_id': 'alquilada'})

        self.message_post(body="✅ Todas las partes repuestas.")
        _logger.info("Solicitud %s — reposición completa.", self.name)

    # -------------------------------------------------------------------------
    # Notificaciones WhatsApp
    # -------------------------------------------------------------------------

    def _enviar_whatsapp_gerencia(self):
        """Notifica a Gerencia al crear la solicitud con links aprobar/rechazar."""
        self.ensure_one()

        base_url = self._get_base_url()
        url_aprobar  = f"{base_url}/partes/gerencia/{self.token_gerencia}/aprobar"
        url_rechazar = f"{base_url}/partes/gerencia/{self.token_gerencia}/rechazar"

        partes_lista = "\n".join([
            f"  • {l.parte}" + (f" — {l.descripcion}" if l.descripcion else "")
            for l in self.parte_ids
        ])

        msg = (
            f"🔧 *Nueva Solicitud de Partes*\n\n"
            f"*Solicitud:* {self.name}\n"
            f"*Solicitante:* {self.solicitante_id.name}\n\n"
            f"*Máquina Origen:* {self.maquina_origen_id.name.name} "
            f"(Serie: {self.maquina_origen_id.serie})\n"
        )
        if self.maquina_destino_id:
            msg += f"*Máquina Destino:* {self.maquina_destino_id.name.name}\n"

        msg += (
            f"\n*Partes solicitadas:*\n{partes_lista}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ *APROBAR:*\n{url_aprobar}\n\n"
            f"❌ *RECHAZAR:*\n{url_rechazar}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ Cada link es de uso único."
        )

        self.send_whatsapp_message(GERENCIA_PHONE, msg)
        _logger.info("WhatsApp enviado a Gerencia para solicitud %s.", self.name)

    def _enviar_whatsapp_solicitante_aprobado(self):
        """Notifica al solicitante que su solicitud fue aprobada."""
        self.ensure_one()

        phone = self._limpiar_telefono(
            self.solicitante_id.mobile_phone if self.solicitante_id else False
        )
        if not phone:
            _logger.warning("Solicitante %s sin teléfono.", self.solicitante_id.name)
            return

        msg = (
            f"✅ *Solicitud Aprobada*\n\n"
            f"Tu solicitud *{self.name}* fue aprobada por Gerencia.\n\n"
            f"*Técnico asignado para retiro:* {self.tecnico_asignado_id.name}\n\n"
            f"Se procederá con el retiro de las partes."
        )
        self.send_whatsapp_message(phone, msg)

    def _enviar_whatsapp_tecnico_retiro(self):
        """Notifica al técnico asignado con link único de retiro."""
        self.ensure_one()

        if not self.tecnico_asignado_mobile_clean:
            _logger.warning(
                "Técnico asignado %s sin teléfono.", self.tecnico_asignado_id.name
            )
            return

        base_url = self._get_base_url()
        url_retiro = f"{base_url}/partes/retirar/{self.access_token}"

        partes_lista = "\n".join([f"  • {l.parte}" for l in self.parte_ids])

        msg = (
            f"🔧 *Retiro de Partes Autorizado*\n\n"
            f"Hola *{self.tecnico_asignado_id.name}*,\n\n"
            f"Debes retirar las siguientes partes:\n\n"
            f"*Solicitud:* {self.name}\n"
            f"*Máquina:* {self.maquina_origen_id.name.name}\n"
            f"*Serie:* {self.maquina_origen_id.serie}\n"
            f"*Marca:* {self.maquina_origen_id.marca}\n\n"
            f"*Partes a retirar:*\n{partes_lista}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👉 *CONFIRMAR RETIRO:*\n{url_retiro}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        self.send_whatsapp_message(self.tecnico_asignado_mobile_clean, msg)
        _logger.info(
            "WhatsApp de retiro enviado a %s para solicitud %s.",
            self.tecnico_asignado_id.name, self.name
        )

    def _enviar_whatsapp_responsable_reposicion(self):
        """Notifica al responsable de reposición con link único."""
        self.ensure_one()

        if not self.responsable_reposicion_mobile_clean:
            _logger.warning(
                "Responsable reposición %s sin teléfono.",
                self.responsable_reposicion_id.name
            )
            return

        base_url = self._get_base_url()
        url_reponer = f"{base_url}/partes/reponer/{self.access_token}"

        partes_lista = "\n".join([f"  • {l.parte}" for l in self.parte_ids])

        msg = (
            f"📦 *Partes Listas para Reponer*\n\n"
            f"Hola *{self.responsable_reposicion_id.name}*,\n\n"
            f"Las siguientes partes fueron retiradas y deben ser repuestas:\n\n"
            f"*Solicitud:* {self.name}\n"
            f"*Máquina:* {self.maquina_origen_id.name.name}\n"
            f"*Serie:* {self.maquina_origen_id.serie}\n\n"
            f"*Partes a reponer:*\n{partes_lista}\n\n"
            f"⚠️ Debes reponer cada parte con foto como evidencia.\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👉 *REPONER PARTES:*\n{url_reponer}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        self.send_whatsapp_message(self.responsable_reposicion_mobile_clean, msg)
        _logger.info(
            "WhatsApp de reposición enviado a %s para solicitud %s.",
            self.responsable_reposicion_id.name, self.name
        )

    # -------------------------------------------------------------------------
    # Cron: recordatorio de reposiciones pendientes
    # -------------------------------------------------------------------------

    def action_check_reposiciones_pendientes(self):
        """Cron job: recuerda al responsable las reposiciones pendientes > 48h."""
        _logger.info("CRON reposiciones: inicio")
        limite = fields.Datetime.now() - timedelta(hours=48)

        Line = self.env['solicitud.partes.linea'].sudo()
        pendientes = Line.search([
            ('estado',              '=',  'retirado'),
            ('fecha_retiro_real',   '!=', False),
            ('fecha_retiro_real',   '<',  limite),
            ('estado_reposicion',   'in', ['pendiente', 'notificado']),
        ])

        _logger.info(
            "CRON reposiciones: %s líneas pendientes (limite=%s)",
            len(pendientes), limite
        )

        for linea in pendientes:
            try:
                linea._enviar_recordatorio_reposicion()
            except Exception as e:
                _logger.exception(
                    "CRON reposiciones: error notificando línea %s: %s", linea.id, e
                )

        _logger.info("CRON reposiciones: fin")
        return True

    # -------------------------------------------------------------------------
    # API WhatsApp
    # -------------------------------------------------------------------------

    def send_whatsapp_message(self, phone, message):
        """Envía mensaje WhatsApp via API externa."""
        url = 'https://boot.andessolutioncopiers.com/api/send-message'
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': 'sk_2312cac15276b4a3ca124e66a78fdde6428c626eb7184f26d3fa62037aaae816',
        }
        data = {'to': phone, 'message': message}

        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response_json = response.json()

            if response.status_code == 200 and response_json.get('success'):
                _logger.info("✅ WhatsApp enviado a %s", phone)
                return response_json

            error_msg = response_json.get('error', 'Error desconocido')
            _logger.error("❌ Error API WhatsApp [%s]: %s", phone, error_msg)
            return {'error': error_msg, 'success': False}

        except requests.exceptions.Timeout:
            _logger.error("❌ Timeout WhatsApp a %s", phone)
            return {'error': 'Timeout', 'success': False}

        except Exception as e:
            _logger.error("❌ Excepción WhatsApp a %s: %s", phone, str(e))
            return {'error': str(e), 'success': False}