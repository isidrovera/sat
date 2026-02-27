import requests
import logging
from odoo import _, models, fields, api
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

JEFE_AREA_PHONE = '51975399303'


def _clean_phone(phone):
    phone = phone.replace('+', '').replace(' ', '')
    if not phone.startswith('51'):
        phone = '51' + phone
    return phone


# ══════════════════════════════════════════════════════════════════════════
# MODELO PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════

class SolicitudParteTecnico(models.Model):
    _name = 'solicitud.parte.tecnico'
    _description = 'Solicitud de Parte por Técnico'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_solicitud desc, id desc'

    name = fields.Char(
        string='Número', readonly=True, copy=False,
        default='Nuevo', tracking=True
    )
    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones',
        string='Reparación',
        required=True,
        tracking=True,
        ondelete='restrict'
    )
    maquina_id = fields.Many2one(
        'sat.sat',
        related='reparacion_id.maquina_id',
        string='Máquina',
        store=True,
        readonly=True
    )
    marca = fields.Char(related='maquina_id.marca', readonly=True, store=True)
    modelo = fields.Char(related='maquina_id.name.name', readonly=True, store=True)
    serie = fields.Char(related='maquina_id.serie_id', readonly=True, store=True)

    tecnico_id = fields.Many2one(
        'res.users',
        string='Técnico',
        default=lambda self: self.env.user,
        required=True,
        tracking=True
    )
    fecha_solicitud = fields.Datetime(
        string='Fecha',
        default=fields.Datetime.now,
        readonly=True
    )
    state = fields.Selection([
        ('enviada', 'Enviada'),
        ('en_gestion', 'En Gestión'),
        ('completada', 'Completada'),
        ('cancelada', 'Cancelada'),
    ], string='Estado', default='enviada', tracking=True)

    linea_ids = fields.One2many(
        'solicitud.parte.tecnico.linea',
        'solicitud_id',
        string='Partes'
    )

    total_partes = fields.Integer(compute='_compute_resumen', store=True)
    partes_encontradas = fields.Integer(compute='_compute_resumen', store=True)
    partes_por_conseguir = fields.Integer(compute='_compute_resumen', store=True)
    partes_pendientes = fields.Integer(compute='_compute_resumen', store=True)

    @api.depends('linea_ids.state')
    def _compute_resumen(self):
        for rec in self:
            rec.total_partes = len(rec.linea_ids)
            rec.partes_encontradas = len(
                rec.linea_ids.filtered(lambda l: l.state == 'encontrada'))
            rec.partes_por_conseguir = len(
                rec.linea_ids.filtered(lambda l: l.state == 'por_conseguir'))
            rec.partes_pendientes = len(
                rec.linea_ids.filtered(lambda l: l.state == 'buscando'))

    @api.model
    def create(self, vals):
        if vals.get('name', 'Nuevo') == 'Nuevo':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'solicitud.parte.tecnico') or 'Nuevo'
        return super().create(vals)

    def action_cancelar(self):
        self.ensure_one()
        self.write({'state': 'cancelada'})
        self.message_post(body=f"❌ Cancelada por {self.env.user.name}")

    # ── WhatsApp ──────────────────────────────────────────────────────────

    def _enviar_whatsapp_jefe(self):
        """Notifica al jefe de área al crear la solicitud"""
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        try:
            action_id = self.env.ref('sat.action_solicitud_parte_tecnico').id
            url = (f"{base_url}/web#id={self.id}&view_type=form"
                   f"&model=solicitud.parte.tecnico&action={action_id}")
        except Exception:
            url = (f"{base_url}/web#id={self.id}"
                   f"&view_type=form&model=solicitud.parte.tecnico")

        partes = "\n".join([
            f"  • {l.parte}" + (f": {l.descripcion}" if l.descripcion else "")
            for l in self.linea_ids
        ])

        msg = (
            f"🔧 *Nueva Solicitud de Parte*\n\n"
            f"*Solicitud:* {self.name}\n"
            f"*Técnico:* {self.tecnico_id.name}\n"
            f"*Reparación:* {self.reparacion_id.name}\n"
            f"*Máquina:* {self.marca or ''} {self.modelo or ''}\n"
            f"*Serie:* {self.serie or ''}\n\n"
            f"*Partes solicitadas:*\n{partes}\n\n"
            f"⚠️ Debes buscar disponibilidad y gestionar cada parte.\n\n"
            f"👉 *VER SOLICITUD:*\n{url}"
        )
        self._send_whatsapp(JEFE_AREA_PHONE, msg)

    def _enviar_whatsapp_tecnico_completada(self):
        """Notifica al técnico cuando toda la solicitud fue gestionada"""
        self.ensure_one()
        if not self.tecnico_id.mobile_phone:
            return
        phone = _clean_phone(self.tecnico_id.mobile_phone)

        encontradas = self.linea_ids.filtered(lambda l: l.state == 'encontrada')
        por_conseguir = self.linea_ids.filtered(lambda l: l.state == 'por_conseguir')

        msg = (
            f"✅ *Solicitud de Partes Gestionada*\n\n"
            f"*Solicitud:* {self.name}\n"
            f"*Máquina:* {self.marca or ''} {self.modelo or ''}\n"
        )
        if encontradas:
            msg += f"\n✅ *Disponibles ({len(encontradas)}):*\n"
            for l in encontradas:
                msg += f"  • {l.parte} → {l._get_origen_display()}\n"
        if por_conseguir:
            msg += f"\n⏳ *Por conseguir ({len(por_conseguir)}):*\n"
            for l in por_conseguir:
                msg += f"  • {l.parte}\n"

        self._send_whatsapp(phone, msg)

    def _send_whatsapp(self, phone, message):
        url = 'https://boot.andessolutioncopiers.com/api/send-message'
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': 'sk_2312cac15276b4a3ca124e66a78fdde6428c626eb7184f26d3fa62037aaae816'
        }
        try:
            r = requests.post(url, headers=headers,
                              json={'to': phone, 'message': message},
                              timeout=30)
            rj = r.json()
            if r.status_code == 200 and rj.get('success'):
                _logger.info("✅ WhatsApp enviado a %s", phone)
            else:
                _logger.error("❌ WhatsApp error: %s", rj.get('error'))
        except Exception as e:
            _logger.error("❌ WhatsApp exception: %s", e)


# ══════════════════════════════════════════════════════════════════════════
# LÍNEAS
# ══════════════════════════════════════════════════════════════════════════

class SolicitudParteTecnicoLinea(models.Model):
    _name = 'solicitud.parte.tecnico.linea'
    _description = 'Línea de Solicitud de Parte'

    solicitud_id = fields.Many2one(
        'solicitud.parte.tecnico',
        required=True,
        ondelete='cascade'
    )
    parte = fields.Char(string='Parte/Componente', required=True)
    descripcion = fields.Text(string='Descripción')
    foto_referencia = fields.Binary(string='Foto Referencia', attachment=True)
    foto_referencia_filename = fields.Char()

    state = fields.Selection([
        ('buscando', 'Buscando'),
        ('encontrada', 'Encontrada'),
        ('por_conseguir', 'Por Conseguir'),
        ('entregada', 'Entregada'),
    ], string='Estado', default='buscando', tracking=True)

    tipo_origen = fields.Selection([
        ('alquiler', 'Máquina de Alquiler'),
        ('sat', 'Máquina SAT'),
        ('compra', 'Compra/Conseguir'),
    ], string='Origen')

    maquina_origen_alquiler_id = fields.Many2one(
        'alquiler', string='Máquina Alquiler Origen')
    maquina_origen_sat_id = fields.Many2one(
        'sat.sat', string='Máquina SAT Origen')

    notas_jefe = fields.Text(string='Notas')
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
        """Jefe gestiona disponibilidad de esta parte"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Gestionar: {self.parte}',
            'res_model': 'solicitud.parte.gestionar.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_linea_id': self.id}
        }

    def action_marcar_entregada(self):
        """Marcar parte como entregada al técnico"""
        self.ensure_one()
        if self.state not in ['encontrada', 'por_conseguir']:
            raise UserError(
                _('Solo se puede entregar partes encontradas o gestionadas.'))
        self.write({'state': 'entregada'})
        self.solicitud_id.message_post(
            body=(f"📦 <b>Parte entregada:</b> {self.parte} "
                  f"→ {self.solicitud_id.tecnico_id.name}")
        )
        self._check_completar_solicitud()

    def _registrar_en_maquina_origen(self):
        """Chatter + estado en la máquina de donde se saca la parte"""
        self.ensure_one()
        msg = (
            f"🔧 <b>Parte retirada:</b> {self.parte}<br/>"
            f"Solicitud: {self.solicitud_id.name}<br/>"
            f"Reparación: {self.solicitud_id.reparacion_id.name}<br/>"
            f"Técnico: {self.solicitud_id.tecnico_id.name}"
            + (f"<br/>Descripción: {self.descripcion}" if self.descripcion else "")
        )
        if self.tipo_origen == 'alquiler' and self.maquina_origen_alquiler_id:
            self.maquina_origen_alquiler_id.write(
                {'estado_alquiler_id': 'con_problemas'})
            self.maquina_origen_alquiler_id.message_post(body=msg)
        elif self.tipo_origen == 'sat' and self.maquina_origen_sat_id:
            self.maquina_origen_sat_id.message_post(body=msg)

    def _check_completar_solicitud(self):
        """Si no quedan líneas en buscando → completar solicitud"""
        solicitud = self.solicitud_id
        if not solicitud.linea_ids.filtered(lambda l: l.state == 'buscando'):
            solicitud.write({'state': 'completada'})
            solicitud._enviar_whatsapp_tecnico_completada()


# ══════════════════════════════════════════════════════════════════════════
# WIZARD JEFE - Gestionar una línea
# ══════════════════════════════════════════════════════════════════════════

class SolicitudParteGestionarWizard(models.TransientModel):
    _name = 'solicitud.parte.gestionar.wizard'
    _description = 'Gestionar disponibilidad de parte'

    linea_id = fields.Many2one(
        'solicitud.parte.tecnico.linea', required=True)
    parte = fields.Char(related='linea_id.parte', readonly=True)
    descripcion = fields.Text(related='linea_id.descripcion', readonly=True)

    resultado = fields.Selection([
        ('encontrada', 'Encontrada - hay disponible'),
        ('por_conseguir', 'No hay - hay que conseguir/comprar'),
    ], string='Resultado', required=True)

    tipo_origen = fields.Selection([
        ('alquiler', 'Máquina de Alquiler'),
        ('sat', 'Máquina SAT'),
    ], string='Sacar de')

    maquina_origen_alquiler_id = fields.Many2one(
        'alquiler', string='Máquina Alquiler',
        domain="[('estado_alquiler_id', 'not in', ['vendida', 'partes'])]"
    )
    maquina_origen_sat_id = fields.Many2one(
        'sat.sat', string='Máquina SAT')
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
                    raise ValidationError(
                        _('Debe indicar de dónde se saca la parte.'))
                if rec.tipo_origen == 'alquiler' and not rec.maquina_origen_alquiler_id:
                    raise ValidationError(
                        _('Seleccione la máquina de alquiler origen.'))
                if rec.tipo_origen == 'sat' and not rec.maquina_origen_sat_id:
                    raise ValidationError(
                        _('Seleccione la máquina SAT origen.'))

    def action_confirmar(self):
        self.ensure_one()
        linea = self.linea_id

        linea.write({
            'state': self.resultado,
            'notas_jefe': self.notas,
            'fecha_gestion': fields.Datetime.now(),
            'gestionado_por': self.env.user.id,
            'tipo_origen': (
                self.tipo_origen if self.resultado == 'encontrada' else 'compra'),
            'maquina_origen_alquiler_id': (
                self.maquina_origen_alquiler_id.id
                if self.resultado == 'encontrada' else False),
            'maquina_origen_sat_id': (
                self.maquina_origen_sat_id.id
                if self.resultado == 'encontrada' else False),
        })

        # Registrar en máquina origen
        if self.resultado == 'encontrada':
            linea._registrar_en_maquina_origen()

        # Chatter
        emoji = '✅' if self.resultado == 'encontrada' else '⏳'
        estado_label = dict(linea._fields['state'].selection).get(
            self.resultado, '')
        linea.solicitud_id.message_post(
            body=(
                f"{emoji} <b>{linea.parte}</b>: {estado_label}"
                f" → {linea._get_origen_display()}"
                + (f"<br/>Notas: {self.notas}" if self.notas else "")
            )
        )

        # WhatsApp al técnico
        self._notificar_tecnico(linea)

        # Actualizar estado solicitud
        solicitud = linea.solicitud_id
        if solicitud.state == 'enviada':
            solicitud.write({'state': 'en_gestion'})

        linea._check_completar_solicitud()

        return {'type': 'ir.actions.act_window_close'}

    def _notificar_tecnico(self, linea):
        tecnico = linea.solicitud_id.tecnico_id
        if not tecnico.mobile_phone:
            return
        phone = _clean_phone(tecnico.mobile_phone)

        if self.resultado == 'encontrada':
            emoji, estado = '✅', 'ENCONTRADA'
            detalle = f"📍 Origen: {linea._get_origen_display()}"
        else:
            emoji, estado = '⏳', 'POR CONSEGUIR'
            detalle = "Se está gestionando la compra."

        msg = (
            f"{emoji} *Parte {estado}*\n\n"
            f"*Solicitud:* {linea.solicitud_id.name}\n"
            f"*Parte:* {linea.parte}\n"
            f"{detalle}\n"
            + (f"*Notas:* {self.notas}\n" if self.notas else "")
            + f"\n*Gestionado por:* {self.env.user.name}"
        )
        linea.solicitud_id._send_whatsapp(phone, msg)


# ══════════════════════════════════════════════════════════════════════════
# WIZARD TÉCNICO - Lanzado desde el botón en reparaciones
# ══════════════════════════════════════════════════════════════════════════

class SolicitudParteTecnicoWizard(models.TransientModel):
    _name = 'solicitud.parte.tecnico.wizard'
    _description = 'Solicitar Parte desde Reparación'

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones', required=True, readonly=True)
    maquina_id = fields.Many2one(
        'sat.sat', related='reparacion_id.maquina_id',
        readonly=True, string='Máquina')
    marca = fields.Char(related='maquina_id.marca', readonly=True)
    modelo = fields.Char(related='maquina_id.name.name', readonly=True)
    serie = fields.Char(related='maquina_id.serie_id', readonly=True)

    linea_ids = fields.One2many(
        'solicitud.parte.tecnico.wizard.linea',
        'wizard_id',
        string='Partes a Solicitar'
    )

    def action_crear_solicitud(self):
        self.ensure_one()
        if not self.linea_ids:
            raise UserError(_('Agregue al menos una parte.'))

        solicitud = self.env['solicitud.parte.tecnico'].create({
            'reparacion_id': self.reparacion_id.id,
            'tecnico_id': self.env.user.id,
        })
        for l in self.linea_ids:
            self.env['solicitud.parte.tecnico.linea'].create({
                'solicitud_id': solicitud.id,
                'parte': l.parte,
                'descripcion': l.descripcion,
                'foto_referencia': l.foto_referencia,
                'foto_referencia_filename': l.foto_referencia_filename,
            })

        # Notificar al jefe
        solicitud._enviar_whatsapp_jefe()

        # Chatter en reparación
        partes_txt = ', '.join(self.linea_ids.mapped('parte'))
        self.reparacion_id.message_post(
            body=(
                f"🔧 <b>Solicitud de parte creada:</b> "
                f"<a href='/web#id={solicitud.id}&view_type=form"
                f"&model=solicitud.parte.tecnico'>{solicitud.name}</a><br/>"
                f"Partes: {partes_txt}"
            )
        )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Solicitud de Parte',
            'res_model': 'solicitud.parte.tecnico',
            'res_id': solicitud.id,
            'view_mode': 'form',
            'target': 'current',
        }


class SolicitudParteTecnicoWizardLinea(models.TransientModel):
    _name = 'solicitud.parte.tecnico.wizard.linea'
    _description = 'Línea del Wizard de Solicitud de Parte'

    wizard_id = fields.Many2one(
        'solicitud.parte.tecnico.wizard',
        required=True, ondelete='cascade')
    parte = fields.Char(string='Parte/Componente', required=True)
    descripcion = fields.Text(string='Descripción')
    foto_referencia = fields.Binary(string='Foto Referencia', attachment=True)
    foto_referencia_filename = fields.Char()