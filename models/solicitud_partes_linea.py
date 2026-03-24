import uuid
from datetime import timedelta
from odoo import _, models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SolicitudPartesLinea(models.Model):
    _name = 'solicitud.partes.linea'
    _description = 'Línea de Solicitud de Partes'

    # -------------------------------------------------------------------------
    # Campos básicos
    # -------------------------------------------------------------------------

    solicitud_id = fields.Many2one(
        'solicitud.partes',
        string='Solicitud',
        ondelete='cascade'
    )
    parte = fields.Char(string='Parte/Unidad', required=True)
    descripcion = fields.Text(string='Descripción')

    # -------------------------------------------------------------------------
    # Estado de la línea
    # -------------------------------------------------------------------------

    estado = fields.Selection([
        ('pendiente',   'Pendiente'),
        ('retirado',    'Retirado'),
        ('reemplazado', 'Reemplazado'),
    ], string='Estado', default='pendiente', tracking=True)

    estado_reposicion = fields.Selection([
        ('pendiente',  'Pendiente'),
        ('notificado', 'Notificado'),
        ('repuesta',   'Repuesta'),
    ], string='Estado Reposición', default='pendiente', tracking=True)

    # -------------------------------------------------------------------------
    # Relación con máquina origen (via cabecera)
    # -------------------------------------------------------------------------

    maquina_origen_id = fields.Many2one(
        'alquiler',
        string='Máquina Origen',
        related='solicitud_id.maquina_origen_id',
        store=True
    )

    # -------------------------------------------------------------------------
    # Retiro
    # -------------------------------------------------------------------------

    fecha_retiro_real = fields.Datetime(
        string='Fecha Retiro',
        tracking=True,
        readonly=True
    )

    # -------------------------------------------------------------------------
    # Reposición
    # -------------------------------------------------------------------------

    reemplazado_por = fields.Many2one(
        'res.users',
        string='Repuesto por',
        tracking=True,
        readonly=True
    )
    fecha_reemplazo = fields.Datetime(
        string='Fecha Reposición',
        tracking=True,
        readonly=True
    )
    condicion = fields.Selection([
        ('bueno',       'Buen Estado'),
        ('defectuoso',  'Defectuoso'),
    ], string='Condición')

    foto_reposicion = fields.Binary(
        string='Foto Reposición',
        attachment=True
    )
    foto_reposicion_filename = fields.Char(string='Nombre Foto')
    observaciones_instalacion = fields.Text(string='Observaciones')

    # -------------------------------------------------------------------------
    # Token de acceso por línea (no se usa directamente — el retiro/reposición
    # usa el access_token de la cabecera). Se conserva para compatibilidad.
    # -------------------------------------------------------------------------

    access_token_linea = fields.Char(
        string='Token Acceso Línea',
        default=lambda self: uuid.uuid4().hex,
        copy=False,
        readonly=True
    )

    # -------------------------------------------------------------------------
    # Lógica de retiro (llamada desde el controller)
    # -------------------------------------------------------------------------

    def _confirmar_retiro(self):
        """
        Confirma el retiro de esta línea.
        Solo puede llamarse si la solicitud está en estado 'approved'.
        """
        self.ensure_one()

        if self.estado != 'pendiente':
            # Ya fue procesada, no hacer nada (idempotente)
            return

        self.write({
            'estado':          'retirado',
            'fecha_retiro_real': fields.Datetime.now(),
        })

        _logger.info(
            "Línea %s (%s) marcada como retirada — solicitud %s.",
            self.id, self.parte, self.solicitud_id.name
        )

    # -------------------------------------------------------------------------
    # Lógica de reposición (llamada desde el controller)
    # -------------------------------------------------------------------------

    def _confirmar_reposicion(self, condicion, foto, foto_filename, observaciones=None):
        """
        Confirma la reposición de esta línea con foto obligatoria.
        Solo puede llamarse si estado == 'retirado'.
        """
        self.ensure_one()

        if self.estado == 'reemplazado':
            # Ya fue repuesta, idempotente
            return

        if self.estado != 'retirado':
            raise UserError(
                _('La parte "%s" no está en estado Retirado.') % self.parte
            )

        if not foto:
            raise UserError(_('Debe adjuntar foto de la reposición.'))

        self.write({
            'estado':                  'reemplazado',
            'fecha_reemplazo':         fields.Datetime.now(),
            'reemplazado_por':         self.env.user.id,
            'condicion':               condicion,
            'estado_reposicion':       'repuesta',
            'foto_reposicion':         foto,
            'foto_reposicion_filename': foto_filename,
            'observaciones_instalacion': observaciones,
        })

        self.solicitud_id.message_post(
            body=(
                f"✅ Parte repuesta: *{self.parte}* — "
                f"{dict(self._fields['condicion'].selection).get(condicion, condicion)}"
            )
        )

        _logger.info(
            "Línea %s (%s) repuesta — solicitud %s.",
            self.id, self.parte, self.solicitud_id.name
        )

        # Verificar si todas las líneas ya están repuestas → completar solicitud
        self._verificar_completar_reposicion()

    def _verificar_completar_reposicion(self):
        """Si todas las líneas están reemplazadas, cierra la solicitud."""
        solicitud = self.solicitud_id
        if solicitud.todas_repuestas:
            solicitud._completar_reposicion()

    # -------------------------------------------------------------------------
    # Recordatorio cron
    # -------------------------------------------------------------------------

    def _enviar_recordatorio_reposicion(self):
        """
        Envía recordatorio al responsable de reposición si la parte lleva
        más de 48h retirada sin ser repuesta.
        Solo envía una vez por día.
        """
        self.ensure_one()

        solicitud = self.solicitud_id
        responsable = solicitud.responsable_reposicion_id

        if not responsable:
            _logger.warning(
                "Línea %s sin responsable de reposición.", self.id
            )
            return

        phone = solicitud.responsable_reposicion_mobile_clean
        if not phone:
            _logger.warning(
                "Responsable %s sin teléfono — línea %s.",
                responsable.name, self.id
            )
            return

        # Guardia: no enviar más de una vez al día
        if (
            self.estado_reposicion == 'notificado'
            and self.write_date
            and self.write_date.date() == fields.Date.today()
        ):
            return

        dias = (fields.Datetime.now() - self.fecha_retiro_real).days
        base_url = solicitud._get_base_url()
        url_reponer = f"{base_url}/partes/reponer/{solicitud.access_token}"

        msg = (
            f"⚠️ *RECORDATORIO: Reposición Pendiente*\n\n"
            f"Hola *{responsable.name}*,\n\n"
            f"La siguiente parte lleva *{dias} día(s)* pendiente de reposición:\n\n"
            f"*Solicitud:* {solicitud.name}\n"
            f"*Parte:* {self.parte}\n"
            f"*Máquina:* {solicitud.maquina_origen_id.name.name}\n\n"
            f"⚠️ *ACCIÓN REQUERIDA*\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👉 *REPONER AHORA:*\n{url_reponer}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )

        solicitud.send_whatsapp_message(phone, msg)
        self.write({'estado_reposicion': 'notificado'})

        _logger.info(
            "Recordatorio reposición enviado — línea %s / solicitud %s.",
            self.id, solicitud.name
        )