import uuid
import json
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

    # El solicitante es editable — puede ser distinto al usuario que crea el registro.
    # Ejemplo: un jefe llenando la solicitud en nombre de su técnico.
    solicitante_id = fields.Many2one(
        'res.users',
        string='Solicitante',
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
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
    estado_origen_al_retirar = fields.Selection([
        ('con_problemas', 'Pasar a Con Problemas'),
        ('partes', 'Pasar a De Partes'),
    ],
        string='Estado de máquina al confirmar retiro',
        required=True,
        default='con_problemas',
        tracking=True,
        help=(
            'Define a qué estado pasará la máquina origen cuando se confirme '
            'el primer retiro real de partes.'
        )
    )

    estado_origen_aplicado_al_retirar = fields.Boolean(
        string='Estado aplicado por retiro',
        readonly=True,
        copy=False,
        tracking=True,
        help='Indica si ya se aplicó el cambio de estado de la máquina origen por retiro.'
    )

    fecha_estado_origen_aplicado = fields.Datetime(
        string='Fecha aplicación estado por retiro',
        readonly=True,
        copy=False,
        tracking=True
    )

    estado_origen_anterior_al_retirar = fields.Char(
        string='Estado anterior al retiro',
        readonly=True,
        copy=False,
        tracking=True
    )
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
    # Responsables — todos se definen al CREAR la solicitud
    # -------------------------------------------------------------------------

    # Técnico que retirará físicamente las partes de la máquina origen.
    # Se define al crear. Gerencia solo aprueba o rechaza con un clic, NO elige técnico.
    tecnico_asignado_id = fields.Many2one(
        'res.users',
        string='Técnico de Retiro',
        required=True,
        tracking=True,
        help="Técnico que realizará el retiro físico de las partes. "
             "Se define al crear la solicitud, no al aprobar."
    )
    tecnico_asignado_mobile_clean = fields.Char(
        string='Teléfono Técnico (limpio)',
        compute='_compute_tecnico_mobile_clean',
        store=True
    )

    # Responsable de reposición: quien recibirá e instalará la parte nueva.
    # A él se le envían los recordatorios automáticos si no repone en 48h.
    responsable_reposicion_id = fields.Many2one(
        'res.users',
        string='Responsable de Reposición',
        required=True,
        tracking=True,
        help="Usuario que recibirá e instalará la parte nueva. "
             "Recibirá alertas automáticas si no repone en el plazo establecido."
    )
    responsable_reposicion_mobile_clean = fields.Char(
        string='Teléfono Responsable Reposición (limpio)',
        compute='_compute_responsable_mobile_clean',
        store=True
    )

    # Quien autorizó (gerencia) — se llena automáticamente al aprobar vía token
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

    def _get_estado_maquina_label(self, estado):
        """Devuelve la etiqueta legible de un estado de alquiler."""
        estados = dict(self.env['alquiler']._fields['estado_alquiler_id'].selection)
        return estados.get(estado, estado or 'Sin estado')

    def _aplicar_estado_maquina_al_confirmar_retiro(self):
        """
        Aplica el estado seleccionado a la máquina origen cuando se confirma
        el primer retiro real de partes.

        Esta función es idempotente:
        - Si ya se aplicó una vez, no vuelve a cambiar la máquina.
        - Evita mensajes duplicados en chatter.
        - Deja trazabilidad del estado anterior y la fecha.
        """
        for record in self:
            maquina = record.maquina_origen_id

            if not maquina:
                _logger.warning(
                    "[SolicitudPartes][EstadoRetiro] Solicitud=%s sin máquina origen.",
                    record.name
                )
                continue

            if record.estado_origen_aplicado_al_retirar:
                _logger.info(
                    "[SolicitudPartes][EstadoRetiro] Estado ya aplicado. "
                    "Solicitud=%s Maquina=%s EstadoActual=%s",
                    record.name,
                    maquina.display_name,
                    maquina.estado_alquiler_id,
                )
                continue

            estado_objetivo = record.estado_origen_al_retirar

            if estado_objetivo not in ('con_problemas', 'partes'):
                raise UserError(_(
                    "Debe seleccionar un estado válido para la máquina origen "
                    "al confirmar el retiro."
                ))

            estado_actual = maquina.estado_alquiler_id

            _logger.info(
                "[SolicitudPartes][EstadoRetiro] Aplicando estado por retiro. "
                "Solicitud=%s Maquina=%s Serie=%s EstadoActual=%s EstadoObjetivo=%s",
                record.name,
                maquina.display_name,
                maquina.serie,
                estado_actual,
                estado_objetivo,
            )

            if estado_actual == 'vendida':
                raise UserError(_(
                    "No se puede cambiar automáticamente el estado de una máquina vendida."
                ))

            estado_actual_label = record._get_estado_maquina_label(estado_actual)
            estado_objetivo_label = record._get_estado_maquina_label(estado_objetivo)

            if estado_actual != estado_objetivo:
                maquina.write({
                    'estado_alquiler_id': estado_objetivo,
                })

                mensaje = _(
                    "🔄 Estado de máquina origen actualizado al confirmar retiro.<br/>"
                    "Máquina: <strong>%s</strong><br/>"
                    "Serie: <strong>%s</strong><br/>"
                    "Estado anterior: <strong>%s</strong><br/>"
                    "Estado nuevo: <strong>%s</strong>"
                ) % (
                    maquina.display_name,
                    maquina.serie or '',
                    estado_actual_label,
                    estado_objetivo_label,
                )

                _logger.info(
                    "[SolicitudPartes][EstadoRetiro] Máquina=%s Serie=%s cambió de %s a %s por solicitud=%s",
                    maquina.id,
                    maquina.serie,
                    estado_actual,
                    estado_objetivo,
                    record.name,
                )
            else:
                mensaje = _(
                    "ℹ️ Retiro confirmado. La máquina origen ya estaba en el estado seleccionado.<br/>"
                    "Máquina: <strong>%s</strong><br/>"
                    "Serie: <strong>%s</strong><br/>"
                    "Estado: <strong>%s</strong>"
                ) % (
                    maquina.display_name,
                    maquina.serie or '',
                    estado_objetivo_label,
                )

                _logger.info(
                    "[SolicitudPartes][EstadoRetiro] Máquina=%s Serie=%s ya estaba en %s. Solicitud=%s",
                    maquina.id,
                    maquina.serie,
                    estado_objetivo,
                    record.name,
                )

            record.write({
                'estado_origen_aplicado_al_retirar': True,
                'fecha_estado_origen_aplicado': fields.Datetime.now(),
                'estado_origen_anterior_al_retirar': estado_actual_label,
            })

            record.message_post(body=mensaje)

    def _enviar_email(self, template_xmlid, ctx=None):
        """
        Envía un mail.template con contexto adicional (URLs tokenizadas, etc.).
        Usa force_send=True para salida inmediata — crítico en flujos con tokens
        de un solo uso que deben llegar antes de que el token sea invalidado.
        """
        self.ensure_one()
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            _logger.warning("⚠️ Template de correo no encontrado: %s", template_xmlid)
            return
        try:
            template.with_context(**(ctx or {})).send_mail(self.id, force_send=True)
            _logger.info(
                "✅ Email enviado [%s] para solicitud %s", template_xmlid, self.name
            )
        except Exception as e:
            _logger.error(
                "❌ Error enviando email [%s] para solicitud %s: %s",
                template_xmlid, self.name, str(e)
            )

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model
    def create(self, vals):
        if vals.get('name', 'Nuevo') == 'Nuevo':
            vals['name'] = (
                self.env['ir.sequence'].next_by_code('solicitud.partes') or 'Nuevo'
            )
        # Generar ambos tokens al crear
        vals['access_token']   = uuid.uuid4().hex
        vals['token_gerencia'] = uuid.uuid4().hex
        record = super().create(vals)

        base_url = record._get_base_url()
        token    = record.token_gerencia

        # Construir URLs ANTES de cualquier escritura que pueda invalidar el token
        url_aprobar  = f"{base_url}/partes/gerencia/{token}/aprobar"
        url_rechazar = f"{base_url}/partes/gerencia/{token}/rechazar"

        # 1) WhatsApp a Gerencia — un clic aprueba directo
        record._enviar_whatsapp_gerencia(url_aprobar, url_rechazar)

        # 2) Email a Gerencia — botones de un clic en el cuerpo del correo
        record._enviar_email(
            'sat.email_template_solicitud_gerencia',
            ctx={
                'url_aprobar':  url_aprobar,
                'url_rechazar': url_rechazar,
            }
        )

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
        """Marcar como Reemplazado manualmente desde Odoo si todas las partes están repuestas."""
        self.ensure_one()
        if not self.todas_repuestas:
            raise UserError(_('Todas las partes deben estar reemplazadas.'))
        self._completar_reposicion()

    def action_forzar_reposicion(self):
        """
        Reposición forzada / manual desde Odoo (botón de administrador).

        Permite cerrar la solicitud como 'replaced' aunque no todas las líneas
        estén en estado 'reemplazado'. Útil cuando la reposición se gestionó
        fuera del sistema o se necesita forzar el cierre por excepción.

        - Marca todas las líneas pendientes como 'reemplazado' con timestamp actual.
        - Registra en el chatter quién forzó el cierre y en qué momento.
        - Envía WhatsApp y correo al responsable de reposición notificando el cierre.
        - NO valida condición de partes para el estado de la máquina origen.
        """
        self.ensure_one()

        if self.state not in ('approved', 'completed'):
            raise UserError(
                _('Solo se puede forzar la reposición en solicitudes Aprobadas o Completadas.')
            )

        ahora          = fields.Datetime.now()
        usuario_actual = self.env.user

        # Marcar todas las líneas que aún no estén reemplazadas
        lineas_pendientes = self.parte_ids.filtered(
            lambda l: l.estado != 'reemplazado'
        )
        if lineas_pendientes:
            lineas_pendientes.write({
                'estado':            'reemplazado',
                'fecha_reemplazo':   ahora,
                'reemplazado_por':   usuario_actual.id,
                'estado_reposicion': 'repuesta',
            })

        # Transición de estado
        self.write({
            'state':           'replaced',
            'reemplazado_por': usuario_actual.id,
            'fecha_reemplazo': ahora,
        })

        # Chatter — registro de auditoría
        n_forzadas = len(lineas_pendientes)
        self.message_post(
            body=(
                f"⚡ <strong>Reposición forzada</strong> por {usuario_actual.name}.<br/>"
                f"Partes cerradas forzadamente: <strong>{n_forzadas}</strong>.<br/>"
                f"Fecha: {ahora.strftime('%d/%m/%Y %H:%M')}"
            )
        )

        # Notificaciones al responsable de reposición
        if self.responsable_reposicion_id:
            self._enviar_whatsapp_reposicion_forzada()
            self._enviar_email('sat.email_template_solicitud_reposicion_forzada')

        _logger.info(
            "⚡ Reposición forzada en solicitud %s por %s. Líneas cerradas: %s.",
            self.name, usuario_actual.name, n_forzadas
        )

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Reposición Forzada'),
                'message': _(
                    'La solicitud %s fue cerrada forzadamente. '
                    '%s línea(s) marcada(s) como reemplazadas.'
                ) % (self.name, n_forzadas),
                'type':    'warning',
                'sticky':  False,
            },
        }

    # -------------------------------------------------------------------------
    # Lógica interna de transiciones
    # -------------------------------------------------------------------------

    def _rechazar(self):
        """Rechaza la solicitud e invalida token de gerencia."""
        self.ensure_one()
        self.write({
            'state':          'rejected',
            'token_gerencia': False,
        })
        self.message_post(body="❌ Solicitud rechazada.")
        _logger.info("Solicitud %s rechazada.", self.name)

    def _aprobar(self):
        """
        Aprueba la solicitud.
        El técnico de retiro y el responsable de reposición ya fueron definidos
        al crear — Gerencia solo aprueba o rechaza con un clic, sin elegir técnico.
        Llamado desde el controller HTTP (token de gerencia GET directo).
        """
        self.ensure_one()

        if self.state != 'submitted':
            raise UserError(_('Esta solicitud ya fue procesada.'))

        if not self.tecnico_asignado_id:
            raise UserError(
                _('La solicitud no tiene técnico de retiro asignado. '
                  'Contacte al solicitante para corregirlo desde Odoo.')
            )

        if not self.responsable_reposicion_id:
            raise UserError(
                _('La solicitud no tiene responsable de reposición asignado. '
                  'Contacte al solicitante para corregirlo desde Odoo.')
            )

        self.write({
            'state':              'approved',
            'autorizado_por':     self.env.ref('base.user_admin').id,
            'fecha_autorizacion': fields.Datetime.now(),
            'token_gerencia':     False,   # invalidar — uso único
        })

        base_url   = self._get_base_url()
        url_retiro = f"{base_url}/partes/retirar/{self.access_token}"

        # Notificar al solicitante — su solicitud fue aprobada
        self._enviar_whatsapp_solicitante_aprobado()
        self._enviar_email('sat.email_template_solicitud_aprobada_solicitante')

        # Notificar al técnico de retiro con link de confirmación
        self._enviar_whatsapp_tecnico_retiro(url_retiro)
        self._enviar_email(
            'sat.email_template_solicitud_retiro_tecnico',
            ctx={'url_retiro': url_retiro}
        )

        self.message_post(
            body=(
                f"✅ Solicitud aprobada por Gerencia.<br/>"
                f"Técnico de retiro: <strong>{self.tecnico_asignado_id.name}</strong><br/>"
                f"Responsable de reposición: <strong>{self.responsable_reposicion_id.name}</strong>"
            )
        )
        _logger.info(
            "Solicitud %s aprobada. Técnico retiro: %s | Responsable reposición: %s",
            self.name,
            self.tecnico_asignado_id.name,
            self.responsable_reposicion_id.name,
        )

    def _completar_retiro(self):
        """Marca la solicitud como completada (todas las partes retiradas)."""
        self.ensure_one()
        self.write({
            'state':        'completed',
            'retirado_por': self.tecnico_asignado_id.id,
            'fecha_retiro': fields.Datetime.now(),
        })
        self.maquina_origen_id.write({'estado_alquiler_id': 'con_problemas'})

        if self.responsable_reposicion_id:
            base_url    = self._get_base_url()
            url_reponer = f"{base_url}/partes/reponer/{self.access_token}"

            # Notificar al responsable de reposición
            self._enviar_whatsapp_responsable_reposicion(url_reponer)
            self._enviar_email(
                'sat.email_template_solicitud_reposicion',
                ctx={'url_reponer': url_reponer}
            )

        self.message_post(body="📦 Todas las partes retiradas. Reposición pendiente.")
        _logger.info("Solicitud %s completada — retiro total.", self.name)

    def _completar_reposicion(self):
        """
        Marca la solicitud como reemplazada cuando todas las partes fueron repuestas.

        Regla:
        - Si todas las partes están repuestas y en condición 'bueno',
          la máquina vuelve a 'alquilada'.
        - Si alguna parte quedó defectuosa, la máquina mantiene su estado actual
          ('con_problemas' o 'partes').
        """
        self.ensure_one()

        _logger.info(
            "[SolicitudPartes][CompletarReposicion] Inicio solicitud=%s state=%s todas_repuestas=%s maquina=%s estado_maquina=%s",
            self.name,
            self.state,
            self.todas_repuestas,
            self.maquina_origen_id.display_name if self.maquina_origen_id else False,
            self.maquina_origen_id.estado_alquiler_id if self.maquina_origen_id else False,
        )

        if not self.todas_repuestas:
            raise UserError(_('Todas las partes deben estar reemplazadas.'))

        self.write({
            'state':           'replaced',
            'reemplazado_por': self.env.user.id,
            'fecha_reemplazo': fields.Datetime.now(),
        })

        todas_buenas = all(l.condicion == 'bueno' for l in self.parte_ids)

        _logger.info(
            "[SolicitudPartes][CompletarReposicion] solicitud=%s todas_buenas=%s condiciones=%s",
            self.name,
            todas_buenas,
            [(l.id, l.parte, l.condicion) for l in self.parte_ids],
        )

        if todas_buenas:
            estado_anterior = self.maquina_origen_id.estado_alquiler_id
            self.maquina_origen_id.write({'estado_alquiler_id': 'alquilada'})

            self.message_post(
                body=_(
                    "✅ Todas las partes fueron repuestas en buen estado.<br/>"
                    "La máquina origen volvió a estado <strong>Alquilada</strong>.<br/>"
                    "Estado anterior: <strong>%s</strong>"
                ) % self._get_estado_maquina_label(estado_anterior)
            )

            _logger.info(
                "[SolicitudPartes][CompletarReposicion] Máquina=%s Serie=%s volvió de %s a alquilada por solicitud=%s",
                self.maquina_origen_id.id,
                self.maquina_origen_id.serie,
                estado_anterior,
                self.name,
            )
        else:
            self.message_post(
                body=_(
                    "⚠️ Todas las partes fueron repuestas, pero una o más quedaron "
                    "en condición defectuosa. La máquina mantiene su estado actual: "
                    "<strong>%s</strong>."
                ) % self._get_estado_maquina_label(
                    self.maquina_origen_id.estado_alquiler_id
                )
            )

            _logger.info(
                "[SolicitudPartes][CompletarReposicion] Máquina=%s Serie=%s mantiene estado=%s porque hay partes defectuosas. Solicitud=%s",
                self.maquina_origen_id.id,
                self.maquina_origen_id.serie,
                self.maquina_origen_id.estado_alquiler_id,
                self.name,
            )

        self.message_post(body="✅ Todas las partes repuestas.")

        _logger.info(
            "[SolicitudPartes][CompletarReposicion] Fin solicitud=%s state=%s estado_maquina=%s",
            self.name,
            self.state,
            self.maquina_origen_id.estado_alquiler_id if self.maquina_origen_id else False,
        )
    # -------------------------------------------------------------------------
    # Notificaciones WhatsApp
    # -------------------------------------------------------------------------

    def _enviar_whatsapp_gerencia(self, url_aprobar, url_rechazar):
        """
        Notifica a Gerencia al crear la solicitud.
        Recibe las URLs ya construidas para garantizar que el token
        no haya sido invalidado por ninguna escritura intermedia.

        El link APROBAR aprueba directo sin ningún formulario adicional.
        Gerencia solo ve un resumen completo y hace un clic.
        """
        self.ensure_one()

        partes_lista = "\n".join([
            f"  • {l.parte}" + (f" — {l.descripcion}" if l.descripcion else "")
            for l in self.parte_ids
        ])

        msg = (
            f"🔧 *Nueva Solicitud de Partes*\n\n"
            f"*Solicitud:* {self.name}\n"
            f"*Solicitante:* {self.solicitante_id.name}\n"
            f"*Técnico de retiro:* {self.tecnico_asignado_id.name}\n"
            f"*Responsable reposición:* {self.responsable_reposicion_id.name}\n\n"
            f"*Máquina Origen:* {self.maquina_origen_id.name.name} "
            f"(Serie: {self.maquina_origen_id.serie})\n"
        )
        if self.maquina_destino_id:
            msg += f"*Máquina Destino:* {self.maquina_destino_id.name.name}\n"

        msg += (
            f"\n*Partes solicitadas:*\n{partes_lista}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ *APROBAR (1 clic):*\n{url_aprobar}\n\n"
            f"❌ *RECHAZAR (1 clic):*\n{url_rechazar}\n"
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
            _logger.warning(
                "Solicitante %s sin teléfono móvil.", self.solicitante_id.name
            )
            return

        msg = (
            f"✅ *Solicitud Aprobada*\n\n"
            f"Tu solicitud *{self.name}* fue aprobada por Gerencia.\n\n"
            f"*Técnico de retiro:* {self.tecnico_asignado_id.name}\n"
            f"*Responsable de reposición:* {self.responsable_reposicion_id.name}\n\n"
            f"Se procederá con el retiro de las partes."
        )
        self.send_whatsapp_message(phone, msg)

    def _enviar_whatsapp_tecnico_retiro(self, url_retiro):
        """
        Notifica al técnico de retiro con link único de confirmación.
        Recibe la URL ya construida.
        """
        self.ensure_one()

        if not self.tecnico_asignado_mobile_clean:
            _logger.warning(
                "Técnico de retiro %s sin teléfono móvil.", self.tecnico_asignado_id.name
            )
            return

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

    def _enviar_whatsapp_responsable_reposicion(self, url_reponer):
        """
        Notifica al responsable de reposición con link único.
        Recibe la URL ya construida.
        """
        self.ensure_one()

        if not self.responsable_reposicion_mobile_clean:
            _logger.warning(
                "Responsable reposición %s sin teléfono móvil.",
                self.responsable_reposicion_id.name
            )
            return

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

    def _enviar_whatsapp_reposicion_forzada(self):
        """
        Notifica al responsable de reposición que la solicitud fue cerrada
        forzadamente por un administrador desde Odoo.
        """
        self.ensure_one()

        if not self.responsable_reposicion_mobile_clean:
            _logger.warning(
                "Responsable reposición %s sin teléfono (notif. forzada).",
                self.responsable_reposicion_id.name
            )
            return

        partes_lista = "\n".join([f"  • {l.parte}" for l in self.parte_ids])

        msg = (
            f"⚡ *Solicitud Cerrada Forzadamente*\n\n"
            f"Hola *{self.responsable_reposicion_id.name}*,\n\n"
            f"La solicitud *{self.name}* fue cerrada manualmente por un administrador.\n\n"
            f"*Máquina:* {self.maquina_origen_id.name.name}\n"
            f"*Serie:* {self.maquina_origen_id.serie}\n\n"
            f"*Partes involucradas:*\n{partes_lista}\n\n"
            f"⚠️ Verifica con tu supervisor el estado real de las partes."
        )
        self.send_whatsapp_message(self.responsable_reposicion_mobile_clean, msg)
        _logger.info(
            "WhatsApp de reposición forzada enviado a %s para solicitud %s.",
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
            ('estado',            '=',  'retirado'),
            ('fecha_retiro_real', '!=', False),
            ('fecha_retiro_real', '<',  limite),
            ('estado_reposicion', 'in', ['pendiente', 'notificado']),
        ])

        _logger.info(
            "CRON reposiciones: %s líneas pendientes (limite=%s)",
            len(pendientes), limite
        )

        for linea in pendientes:
            try:
                linea._enviar_recordatorio_reposicion()

                # Email recordatorio desde la solicitud padre
                solicitud = linea.solicitud_id
                if solicitud and solicitud.responsable_reposicion_id:
                    base_url    = solicitud._get_base_url()
                    url_reponer = f"{base_url}/partes/reponer/{solicitud.access_token}"
                    solicitud._enviar_email(
                        'sat.email_template_recordatorio_reposicion',
                        ctx={'url_reponer': url_reponer}
                    )

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
        """Envía mensaje WhatsApp vía API externa configurada en parámetros del sistema."""
        try:
            ICP = self.env["ir.config_parameter"].sudo()

            base_url = ICP.get_param("sat.whatsapp_gateway_base_url")
            api_key = ICP.get_param("sat.whatsapp_gateway_api_key")

            if not base_url:
                error_msg = "Falta configurar el parámetro sat.whatsapp_gateway_base_url"
                _logger.error("❌ %s", error_msg)
                return {
                    "error": error_msg,
                    "success": False,
                }

            if not api_key:
                error_msg = "Falta configurar el parámetro sat.whatsapp_gateway_api_key"
                _logger.error("❌ %s", error_msg)
                return {
                    "error": error_msg,
                    "success": False,
                }

            base_url = base_url.rstrip("/")
            url = f"{base_url}/api/send-message"

            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
            }

            data = {
                "to": phone,
                "message": message,
            }

            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=30,
            )

            try:
                response_json = response.json()
            except json.JSONDecodeError as e:
                error_msg = f"La respuesta no contiene un JSON válido: {str(e)}"
                _logger.error("❌ %s", error_msg)
                _logger.error("Respuesta raw WhatsApp API: %s", response.text)

                return {
                    "error": error_msg,
                    "success": False,
                    "status_code": response.status_code,
                }

            if response.status_code == 200 and response_json.get("success"):
                _logger.info("✅ WhatsApp enviado a %s", phone)
                return response_json

            error_msg = response_json.get("error", "Error desconocido")
            _logger.error(
                "❌ Error API WhatsApp [%s] Status [%s]: %s",
                phone,
                response.status_code,
                error_msg,
            )

            return {
                "error": error_msg,
                "success": False,
                "status_code": response.status_code,
            }

        except requests.exceptions.Timeout:
            _logger.error("❌ Timeout WhatsApp a %s", phone)

            return {
                "error": "Timeout",
                "success": False,
            }

        except requests.exceptions.RequestException as e:
            error_msg = f"Error de red WhatsApp API: {str(e)}"
            _logger.exception("❌ %s", error_msg)

            return {
                "error": error_msg,
                "success": False,
            }

        except Exception as e:
            _logger.exception(
                "❌ Excepción WhatsApp a %s: %s",
                phone,
                str(e),
            )

            return {
                "error": str(e),
                "success": False,
            }