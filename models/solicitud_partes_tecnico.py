import uuid
import requests
import logging
from odoo import _, http, models, fields, api
from odoo.http import request as http_request
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────
JEFE_AREA_PHONE   = '51975399303'
LOGISTICA_PHONE   = '51922541085'
GERENCIA_PHONE    = '51998319547'
WA_API_URL        = 'https://boot.andessolutioncopiers.com/api/send-message'
WA_API_KEY        = 'sk_2312cac15276b4a3ca124e66a78fdde6428c626eb7184f26d3fa62037aaae816'


def _clean_phone(phone):
    phone = str(phone).replace('+', '').replace(' ', '')
    if not phone.startswith('51'):
        phone = '51' + phone
    return phone


def _send_whatsapp(phone, message):
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': WA_API_KEY,
    }
    try:
        r = requests.post(WA_API_URL, headers=headers,
                          json={'to': phone, 'message': message}, timeout=30)
        rj = r.json()
        if r.status_code == 200 and rj.get('success'):
            _logger.info('✅ WhatsApp enviado a %s', phone)
        else:
            _logger.error('❌ WhatsApp error a %s: %s', phone, rj.get('error'))
    except Exception as e:
        _logger.error('❌ WhatsApp exception a %s: %s', phone, e)


# ══════════════════════════════════════════════════════════════════════════
# MODELO PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════

class SolicitudParteTecnico(models.Model):
    _name        = 'solicitud.parte.tecnico'
    _description = 'Solicitud de Parte por Técnico'
    _inherit     = ['mail.thread', 'mail.activity.mixin']
    _order       = 'fecha_solicitud desc, id desc'

    # ── Identificación ────────────────────────────────────────────────────
    name = fields.Char(
        string='Número', readonly=True, copy=False,
        default='Nuevo', tracking=True)

    access_token = fields.Char(
        string='Token', copy=False, readonly=True, index=True)

    # ── Relaciones ────────────────────────────────────────────────────────
    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones', string='Reparación',
        required=True, tracking=True, ondelete='restrict')

    maquina_id = fields.Many2one(
        'sat.sat', related='reparacion_id.maquina_id',
        string='Máquina', store=True, readonly=True)

    marca  = fields.Char(related='maquina_id.marca',     readonly=True, store=True)
    modelo = fields.Char(related='maquina_id.name.name', readonly=True, store=True)
    serie  = fields.Char(related='maquina_id.serie_id',  readonly=True, store=True)

    tecnico_id = fields.Many2one(
        'res.users', string='Técnico',
        default=lambda self: self.env.user,
        required=True, tracking=True)

    fecha_solicitud = fields.Datetime(
        string='Fecha', default=fields.Datetime.now, readonly=True)

    # ── Estado ────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('enviada',              'Enviada'),
        ('en_gestion',           'En Gestión'),
        ('pendiente_aprobacion', 'Pendiente Aprobación'),
        ('por_conseguir',        'Por Conseguir'),
        ('aprobada',             'Aprobada'),
        ('completada',           'Completada'),
        ('cancelada',            'Cancelada'),
    ], string='Estado', default='enviada', tracking=True)

    # ── Líneas ────────────────────────────────────────────────────────────
    linea_ids = fields.One2many(
        'solicitud.parte.tecnico.linea', 'solicitud_id', string='Partes')

    # ── Resumen ───────────────────────────────────────────────────────────
    total_partes         = fields.Integer(compute='_compute_resumen', store=True)
    partes_encontradas   = fields.Integer(compute='_compute_resumen', store=True)
    partes_por_conseguir = fields.Integer(compute='_compute_resumen', store=True)
    partes_pendientes    = fields.Integer(compute='_compute_resumen', store=True)

    @api.depends('linea_ids.state')
    def _compute_resumen(self):
        for rec in self:
            rec.total_partes         = len(rec.linea_ids)
            rec.partes_encontradas   = len(rec.linea_ids.filtered(lambda l: l.state == 'encontrada'))
            rec.partes_por_conseguir = len(rec.linea_ids.filtered(lambda l: l.state == 'por_conseguir'))
            rec.partes_pendientes    = len(rec.linea_ids.filtered(lambda l: l.state == 'buscando'))

    # ── Crear ─────────────────────────────────────────────────────────────
    @api.model
    def create(self, vals):
        if vals.get('name', 'Nuevo') == 'Nuevo':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'solicitud.parte.tecnico') or 'Nuevo'
        if not vals.get('access_token'):
            vals['access_token'] = str(uuid.uuid4())
        return super().create(vals)

    # ── URLs token ────────────────────────────────────────────────────────
    def _get_base_url(self):
        return self.env['ir.config_parameter'].sudo().get_param('web.base.url')

    def _url_aprobar_gerencia(self):
        return f"{self._get_base_url()}/solicitud-parte/aprobar/{self.access_token}"

    def _url_confirmar_retiro(self):
        return f"{self._get_base_url()}/solicitud-parte/confirmar/{self.access_token}"

    def _url_odoo(self):
        try:
            action_id = self.env.ref('sat.action_solicitud_parte_tecnico').id
            return (f"{self._get_base_url()}/web#id={self.id}"
                    f"&view_type=form&model=solicitud.parte.tecnico&action={action_id}")
        except Exception:
            return (f"{self._get_base_url()}/web#id={self.id}"
                    f"&view_type=form&model=solicitud.parte.tecnico")

    # ── Enviar template de correo ─────────────────────────────────────────
    def _enviar_template(self, xml_id, email_to_override=None):
        """Envía un mail.template. Si email_to_override se pasa, sobreescribe el destinatario."""
        self.ensure_one()
        try:
            template = self.env.ref(xml_id)
            if email_to_override:
                template = template.with_context(
                    default_email_to=email_to_override)
            template.send_mail(self.id, force_send=True)
            _logger.info('✅ Email template %s enviado para solicitud %s', xml_id, self.name)
        except Exception as e:
            _logger.error('❌ Error enviando template %s: %s', xml_id, e)

    # ══════════════════════════════════════════════════════════════════════
    # PASO 1: Técnico crea → notifica Jefe de Área
    # ══════════════════════════════════════════════════════════════════════
    def _notificar_jefe_nueva_solicitud(self):
        self.ensure_one()
        partes_wa = "\n".join([
            f"  • {l.parte}" + (f": {l.descripcion}" if l.descripcion else "")
            for l in self.linea_ids
        ])
        msg_wa = (
            f"🔧 *Nueva Solicitud de Parte*\n\n"
            f"*Solicitud:* {self.name}\n"
            f"*Técnico:* {self.tecnico_id.name}\n"
            f"*Reparación:* {self.reparacion_id.name}\n"
            f"*Máquina:* {self.marca or ''} {self.modelo or ''}\n"
            f"*Serie:* {self.serie or ''}\n\n"
            f"*Partes solicitadas:*\n{partes_wa}\n\n"
            f"⚠️ Gestiona la disponibilidad de cada parte en Odoo:\n"
            f"👉 {self._url_odoo()}"
        )
        _send_whatsapp(JEFE_AREA_PHONE, msg_wa)

        # Email via template
        self._enviar_template('sat.email_template_solicitud_parte_nueva')

    # ══════════════════════════════════════════════════════════════════════
    # PASO 2A: Jefe gestiona → hay partes → pide aprobación a Gerencia
    # ══════════════════════════════════════════════════════════════════════
    def _notificar_gerencia_aprobacion(self):
        self.ensure_one()
        encontradas = self.linea_ids.filtered(lambda l: l.state == 'encontrada')
        partes_wa = "\n".join([
            f"  • {l.parte} → {l._get_origen_display()}" for l in encontradas])

        msg_wa = (
            f"✅ *Aprobación Requerida - Solicitud de Parte*\n\n"
            f"*Solicitud:* {self.name}\n"
            f"*Técnico:* {self.tecnico_id.name}\n"
            f"*Máquina:* {self.marca or ''} {self.modelo or ''}\n"
            f"*Serie:* {self.serie or ''}\n\n"
            f"*Partes listas para retirar:*\n{partes_wa}\n\n"
            f"👉 *APROBAR RETIRO:*\n{self._url_aprobar_gerencia()}"
        )
        _send_whatsapp(GERENCIA_PHONE, msg_wa)
        _send_whatsapp(LOGISTICA_PHONE, msg_wa)

        # Email via template
        self._enviar_template('sat.email_template_solicitud_parte_aprobacion')

    # ══════════════════════════════════════════════════════════════════════
    # PASO 2B: Jefe gestiona → NO hay partes → notifica Gerencia para compra
    # ══════════════════════════════════════════════════════════════════════
    def _notificar_gerencia_por_conseguir(self):
        self.ensure_one()
        por_conseguir = self.linea_ids.filtered(lambda l: l.state == 'por_conseguir')
        partes_wa = "\n".join([f"  • {l.parte}" for l in por_conseguir])

        msg_wa = (
            f"⏳ *Partes por Conseguir/Comprar*\n\n"
            f"*Solicitud:* {self.name}\n"
            f"*Técnico:* {self.tecnico_id.name}\n"
            f"*Máquina:* {self.marca or ''} {self.modelo or ''}\n"
            f"*Serie:* {self.serie or ''}\n\n"
            f"*Partes que NO están disponibles:*\n{partes_wa}\n\n"
            f"⚠️ Se requiere gestionar la compra/consecución de estas partes."
        )
        _send_whatsapp(GERENCIA_PHONE, msg_wa)
        _send_whatsapp(LOGISTICA_PHONE, msg_wa)

        # Email via template
        self._enviar_template('sat.email_template_solicitud_parte_por_conseguir')

    # ══════════════════════════════════════════════════════════════════════
    # PASO 3: Gerencia aprueba (desde link token o botón Odoo)
    # ══════════════════════════════════════════════════════════════════════
    def action_aprobar(self):
        self.ensure_one()
        if self.state != 'pendiente_aprobacion':
            raise UserError(
                _('Solo se pueden aprobar solicitudes en estado Pendiente de Aprobación.'))
        self.write({'state': 'aprobada'})
        self.message_post(
            body=f"✅ <b>Aprobada por Gerencia.</b><br/>Usuario: {self.env.user.name}"
        )
        self._notificar_tecnico_retiro()

    def _notificar_tecnico_retiro(self):
        self.ensure_one()
        encontradas = self.linea_ids.filtered(lambda l: l.state == 'encontrada')
        partes_wa = "\n".join([
            f"  • {l.parte} → {l._get_origen_display()}" for l in encontradas])

        msg_wa = (
            f"✅ *¡Solicitud Aprobada! Puedes retirar las partes*\n\n"
            f"*Solicitud:* {self.name}\n"
            f"*Reparación:* {self.reparacion_id.name}\n\n"
            f"*Partes a retirar:*\n{partes_wa}\n\n"
            f"Una vez retiradas confirma aquí:\n"
            f"👉 {self._url_confirmar_retiro()}"
        )
        # WhatsApp al técnico
        if self.tecnico_id.mobile_phone:
            _send_whatsapp(_clean_phone(self.tecnico_id.mobile_phone), msg_wa)
        # WhatsApp al jefe también para que sepa
        _send_whatsapp(JEFE_AREA_PHONE, msg_wa)

        # Email al técnico via template (sobreescribir destinatario)
        email_tecnico = self.tecnico_id.email
        if email_tecnico:
            self._enviar_template(
                'sat.email_template_solicitud_parte_tecnico_retiro',
                email_to_override=email_tecnico)

    # ══════════════════════════════════════════════════════════════════════
    # PASO 4: Técnico confirma retiro (desde link token)
    # ══════════════════════════════════════════════════════════════════════
    def action_confirmar_retiro(self):
        self.ensure_one()
        if self.state != 'aprobada':
            raise UserError(_('Solo se pueden confirmar solicitudes aprobadas.'))

        self.write({'state': 'completada'})

        # Registrar en máquinas origen y marcar líneas como entregadas
        for linea in self.linea_ids.filtered(lambda l: l.state == 'encontrada'):
            linea._registrar_en_maquina_origen()
            linea.write({'state': 'entregada'})

        self.message_post(
            body=f"📦 <b>Retiro confirmado</b><br/>Confirmado por: {self.env.user.name}"
        )

        self._notificar_completada()

    def _notificar_completada(self):
        self.ensure_one()
        msg_wa = (
            f"📦 *Solicitud Completada*\n\n"
            f"*Solicitud:* {self.name}\n"
            f"*Técnico:* {self.tecnico_id.name}\n"
            f"*Reparación:* {self.reparacion_id.name}\n"
            f"*Máquina:* {self.marca or ''} {self.modelo or ''}\n\n"
            f"✅ El técnico confirmó el retiro de todas las partes."
        )
        _send_whatsapp(JEFE_AREA_PHONE, msg_wa)
        _send_whatsapp(GERENCIA_PHONE, msg_wa)

    # ══════════════════════════════════════════════════════════════════════
    # Lógica de avance de estado tras gestión del jefe
    # ══════════════════════════════════════════════════════════════════════
    def _check_avanzar_estado(self):
        """
        Se llama después de que el jefe gestiona cada línea.
        Solo avanza cuando NO quedan líneas en estado 'buscando'.
        """
        self.ensure_one()
        # Aún hay líneas sin gestionar → no avanzar
        if self.linea_ids.filtered(lambda l: l.state == 'buscando'):
            return

        encontradas   = self.linea_ids.filtered(lambda l: l.state == 'encontrada')
        por_conseguir = self.linea_ids.filtered(lambda l: l.state == 'por_conseguir')

        if encontradas and not por_conseguir:
            # Todo encontrado → pedir aprobación gerencia
            self.write({'state': 'pendiente_aprobacion'})
            self.message_post(
                body="📋 Todas las partes encontradas. Esperando aprobación de Gerencia.")
            self._notificar_gerencia_aprobacion()

        elif por_conseguir and not encontradas:
            # Nada en stock → gestionar compra
            self.write({'state': 'por_conseguir'})
            self.message_post(
                body="⏳ No hay partes disponibles. Gerencia notificada para gestionar compra.")
            self._notificar_gerencia_por_conseguir()

        else:
            # Mezcla: algunas encontradas + otras por conseguir
            self.write({'state': 'pendiente_aprobacion'})
            self.message_post(
                body=(
                    f"📋 Gestión mixta: {len(encontradas)} encontrada(s), "
                    f"{len(por_conseguir)} por conseguir.<br/>"
                    f"Gerencia notificada de ambas situaciones."
                )
            )
            self._notificar_gerencia_aprobacion()
            self._notificar_gerencia_por_conseguir()

    def action_cancelar(self):
        self.ensure_one()
        self.write({'state': 'cancelada'})
        self.message_post(body=f"❌ Cancelada por {self.env.user.name}")


# ══════════════════════════════════════════════════════════════════════════
# LÍNEAS
# ══════════════════════════════════════════════════════════════════════════

class SolicitudParteTecnicoLinea(models.Model):
    _name        = 'solicitud.parte.tecnico.linea'
    _description = 'Línea de Solicitud de Parte'

    solicitud_id = fields.Many2one(
        'solicitud.parte.tecnico', required=True, ondelete='cascade')

    parte       = fields.Char(string='Parte/Componente', required=True)
    descripcion = fields.Text(string='Descripción')
    foto_referencia          = fields.Binary(string='Foto Referencia', attachment=True)
    foto_referencia_filename = fields.Char()

    state = fields.Selection([
        ('buscando',      'Buscando'),
        ('encontrada',    'Encontrada'),
        ('por_conseguir', 'Por Conseguir'),
        ('entregada',     'Entregada'),
    ], string='Estado', default='buscando', tracking=True)

    tipo_origen = fields.Selection([
        ('alquiler', 'Máquina de Alquiler'),
        ('sat',      'Máquina SAT'),
        ('compra',   'Compra/Conseguir'),
    ], string='Origen')

    maquina_origen_alquiler_id = fields.Many2one(
        'alquiler', string='Máquina Alquiler Origen')
    maquina_origen_sat_id = fields.Many2one(
        'sat.sat', string='Máquina SAT Origen')

    notas_jefe    = fields.Text(string='Notas')
    fecha_gestion = fields.Datetime(string='Fecha Gestión', readonly=True)
    gestionado_por = fields.Many2one(
        'res.users', string='Gestionado por', readonly=True)

    def _get_origen_display(self):
        self.ensure_one()
        if self.tipo_origen == 'alquiler' and self.maquina_origen_alquiler_id:
            m = self.maquina_origen_alquiler_id
            return f"Alquiler: {m.marca} {m.name.name} (Serie: {m.serie})"
        elif self.tipo_origen == 'sat' and self.maquina_origen_sat_id:
            m = self.maquina_origen_sat_id
            return f"SAT: {m.marca} {m.name.name} (Serie: {m.serie_id})"
        elif self.tipo_origen == 'compra':
            return "Por comprar/conseguir"
        return "Sin definir"

    def action_gestionar(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      f'Gestionar: {self.parte}',
            'res_model': 'solicitud.parte.gestionar.wizard',
            'view_mode': 'form',
            'target':    'new',
            'context':   {'default_linea_id': self.id},
        }

    def _registrar_en_maquina_origen(self):
        self.ensure_one()
        msg = (
            f"🔧 <b>Parte retirada:</b> {self.parte}<br/>"
            f"Solicitud: {self.solicitud_id.name}<br/>"
            f"Reparación: {self.solicitud_id.reparacion_id.name}<br/>"
            f"Técnico: {self.solicitud_id.tecnico_id.name}"
            + (f"<br/>Descripción: {self.descripcion}" if self.descripcion else "")
        )
        if self.tipo_origen == 'alquiler' and self.maquina_origen_alquiler_id:
            self.maquina_origen_alquiler_id.write({'estado_alquiler_id': 'con_problemas'})
            self.maquina_origen_alquiler_id.message_post(body=msg)
        elif self.tipo_origen == 'sat' and self.maquina_origen_sat_id:
            self.maquina_origen_sat_id.message_post(body=msg)


# ══════════════════════════════════════════════════════════════════════════
# WIZARD JEFE — Gestionar disponibilidad de una línea
# ══════════════════════════════════════════════════════════════════════════

class SolicitudParteGestionarWizard(models.TransientModel):
    _name        = 'solicitud.parte.gestionar.wizard'
    _description = 'Gestionar disponibilidad de parte'

    linea_id    = fields.Many2one('solicitud.parte.tecnico.linea', required=True)
    parte       = fields.Char(related='linea_id.parte',       readonly=True)
    descripcion = fields.Text(related='linea_id.descripcion', readonly=True)

    resultado = fields.Selection([
        ('encontrada',    'Encontrada — hay disponible'),
        ('por_conseguir', 'No hay — hay que conseguir/comprar'),
    ], string='Resultado', required=True)

    tipo_origen = fields.Selection([
        ('alquiler', 'Máquina de Alquiler'),
        ('sat',      'Máquina SAT'),
    ], string='Sacar de')

    maquina_origen_alquiler_id = fields.Many2one(
        'alquiler',
        string='Máquina Alquiler',
        domain="[('estado_alquiler_id', 'not in', ['vendida','externo','alquilada'])]"
    )
    maquina_origen_sat_id = fields.Many2one('sat.sat', string='Máquina SAT')
    notas = fields.Text(string='Notas')

    @api.onchange('resultado')
    def _onchange_resultado(self):
        if self.resultado == 'por_conseguir':
            self.tipo_origen = False
            self.maquina_origen_alquiler_id = False
            self.maquina_origen_sat_id = False

    @api.constrains('resultado', 'tipo_origen',
                    'maquina_origen_alquiler_id', 'maquina_origen_sat_id')
    def _check_origen(self):
        for rec in self:
            if rec.resultado == 'encontrada':
                if not rec.tipo_origen:
                    raise ValidationError(_('Debe indicar de dónde se saca la parte.'))
                if rec.tipo_origen == 'alquiler' and not rec.maquina_origen_alquiler_id:
                    raise ValidationError(_('Seleccione la máquina de alquiler origen.'))
                if rec.tipo_origen == 'sat' and not rec.maquina_origen_sat_id:
                    raise ValidationError(_('Seleccione la máquina SAT origen.'))

    def action_confirmar(self):
        self.ensure_one()
        linea = self.linea_id

        linea.write({
            'state':                    self.resultado,
            'notas_jefe':               self.notas,
            'fecha_gestion':            fields.Datetime.now(),
            'gestionado_por':           self.env.user.id,
            'tipo_origen':              self.tipo_origen if self.resultado == 'encontrada' else 'compra',
            'maquina_origen_alquiler_id': (
                self.maquina_origen_alquiler_id.id
                if self.resultado == 'encontrada' else False),
            'maquina_origen_sat_id': (
                self.maquina_origen_sat_id.id
                if self.resultado == 'encontrada' else False),
        })

        # Chatter en solicitud
        emoji        = '✅' if self.resultado == 'encontrada' else '⏳'
        estado_label = dict(linea._fields['state'].selection).get(self.resultado, '')
        linea.solicitud_id.message_post(
            body=(
                f"{emoji} <b>{linea.parte}</b>: {estado_label}"
                f" → {linea._get_origen_display()}<br/>"
                f"Gestionado por: {self.env.user.name}"
            )
        )

        # Avanzar solicitud a en_gestion si es la primera línea gestionada
        solicitud = linea.solicitud_id

        # Si estaba enviada o por_conseguir vuelve a gestionarse
        if solicitud.state in ['enviada', 'por_conseguir']:
            solicitud.write({'state': 'en_gestion'})

        # Verificar si ya se gestionaron todas las líneas
        solicitud._check_avanzar_estado()

        return {'type': 'ir.actions.act_window_close'}


# ══════════════════════════════════════════════════════════════════════════
# WIZARD TÉCNICO — Solicitar parte desde reparación
# ══════════════════════════════════════════════════════════════════════════

class SolicitudParteTecnicoWizard(models.TransientModel):
    _name        = 'solicitud.parte.tecnico.wizard'
    _description = 'Solicitar Parte desde Reparación'

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones', required=True, readonly=True)
    maquina_id = fields.Many2one(
        'sat.sat', related='reparacion_id.maquina_id', readonly=True)
    marca  = fields.Char(related='maquina_id.marca',     readonly=True)
    modelo = fields.Char(related='maquina_id.name.name', readonly=True)
    serie  = fields.Char(related='maquina_id.serie_id',  readonly=True)

    linea_ids = fields.One2many(
        'solicitud.parte.tecnico.wizard.linea', 'wizard_id',
        string='Partes a Solicitar')

    def action_crear_solicitud(self):
        self.ensure_one()
        if not self.linea_ids:
            raise UserError(_('Agregue al menos una parte.'))

        solicitud = self.env['solicitud.parte.tecnico'].create({
            'reparacion_id': self.reparacion_id.id,
            'tecnico_id':    self.env.user.id,
        })
        for l in self.linea_ids:
            self.env['solicitud.parte.tecnico.linea'].create({
                'solicitud_id':             solicitud.id,
                'parte':                    l.parte,
                'descripcion':              l.descripcion,
                'foto_referencia':          l.foto_referencia,
                'foto_referencia_filename': l.foto_referencia_filename,
            })

        # Notificar al jefe de área (WhatsApp + email template)
        solicitud._notificar_jefe_nueva_solicitud()

        # Chatter en reparación
        partes_txt = ', '.join(self.linea_ids.mapped('parte'))
        self.reparacion_id.message_post(
            body=(
                f"🔧 <b>Solicitud de parte creada:</b> "
                f"<a href='{solicitud._url_odoo()}'>{solicitud.name}</a><br/>"
                f"Partes: {partes_txt}"
            )
        )

        return {
            'type':      'ir.actions.act_window',
            'name':      'Solicitud de Parte',
            'res_model': 'solicitud.parte.tecnico',
            'res_id':    solicitud.id,
            'view_mode': 'form',
            'target':    'current',
        }


class SolicitudParteTecnicoWizardLinea(models.TransientModel):
    _name        = 'solicitud.parte.tecnico.wizard.linea'
    _description = 'Línea del Wizard de Solicitud de Parte'

    wizard_id   = fields.Many2one(
        'solicitud.parte.tecnico.wizard', required=True, ondelete='cascade')
    parte       = fields.Char(string='Parte/Componente', required=True)
    descripcion = fields.Text(string='Descripción')
    foto_referencia          = fields.Binary(string='Foto Referencia', attachment=True)
    foto_referencia_filename = fields.Char()

