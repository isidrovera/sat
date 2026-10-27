
# -*- coding: utf-8 -*-
"""
Tokens de confirmación de retiro - SAT
Odoo 19
Archivo: models/ticket_retiro_token.py

REGLAS:
- Un token pendiente por ticket.
- No generar múltiples enlaces por reintentos GPS.
- Expiración real de 15 minutos.
- No asumir salida física por expiración.
- No finalizar tickets automáticamente.
- Conservar fecha y motivo de confirmación.
- Control de concurrencia.
- Notificar a coordinación cuando no hay respuesta.
- Compatible con los métodos existentes.
"""

import logging
import secrets

from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


MINUTOS_EXPIRACION = 15

MOTIVOS = [
    (
        'cliente_tarde',
        'El cliente aún no llega, lo estoy esperando'
    ),
    (
        'sin_autorizacion',
        'No me autorizaron el ingreso'
    ),
    (
        'ausencia_temporal',
        'Salí momentáneamente, regreso a terminar'
    ),
    (
        'finalizado',
        'Ya finalicé el servicio'
    ),
]


class TicketRetiroToken(models.Model):

    _name = 'ticket.retiro.token'
    _description = 'Confirmación de motivo de retiro SAT'
    _order = 'create_date desc, id desc'
    _rec_name = 'ticket_id'

    # ======================================================
    # CAMPOS PRINCIPALES
    # ======================================================

    ticket_id = fields.Many2one(
        'ticket.alquiler',
        string='Ticket',
        required=True,
        ondelete='cascade',
        index=True,
    )

    token = fields.Char(
        string='Token',
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: secrets.token_urlsafe(32),
    )

    estado = fields.Selection(
        [
            ('pendiente', 'Pendiente'),
            ('respondido', 'Respondido'),
            ('expirado', 'Expirado'),
            ('cancelado', 'Cancelado'),
        ],
        string='Estado',
        default='pendiente',
        required=True,
        index=True,
    )

    motivo = fields.Selection(
        MOTIVOS,
        string='Motivo elegido',
        readonly=True,
    )

    motivo_label = fields.Char(
        string='Motivo',
        compute='_compute_motivo_label',
        store=True,
    )

    # ======================================================
    # CONTEXTO GPS
    # ======================================================

    lat_salida = fields.Float(
        string='Latitud detectada',
        digits=(10, 7),
        readonly=True,
    )

    lon_salida = fields.Float(
        string='Longitud detectada',
        digits=(10, 7),
        readonly=True,
    )

    tiempo_en_sitio_minutos = fields.Float(
        string='Tiempo en sitio al detectar retiro',
        readonly=True,
    )

    # ======================================================
    # FECHAS
    # ======================================================

    expira_en = fields.Datetime(
        string='Expira en',
        readonly=True,
        index=True,
    )

    respondido_en = fields.Datetime(
        string='Fecha de respuesta',
        readonly=True,
    )

    cancelado_en = fields.Datetime(
        string='Fecha de cancelación',
        readonly=True,
    )

    expirado_en = fields.Datetime(
        string='Fecha de procesamiento de expiración',
        readonly=True,
    )

    # ======================================================
    # DATOS RELACIONADOS
    # ======================================================

    tecnico_nombre = fields.Char(
        string='Técnico',
        related='ticket_id.responsable.name',
        store=True,
    )

    # ======================================================
    # RESTRICCIONES SQL ODOO 19
    # ======================================================

    _token_unique = models.Constraint(
        'UNIQUE(token)',
        'El token debe ser único.',
    )

    # ======================================================
    # COMPUTE
    # ======================================================

    @api.depends('motivo')
    def _compute_motivo_label(self):

        motivos_dict = dict(MOTIVOS)

        for rec in self:
            rec.motivo_label = (
                motivos_dict.get(rec.motivo, '')
                if rec.motivo
                else ''
            )

    # ======================================================
    # VALIDACIONES
    # ======================================================

    @api.constrains('tiempo_en_sitio_minutos')
    def _check_tiempo_sitio(self):

        for rec in self:
            if rec.tiempo_en_sitio_minutos < 0:
                raise ValidationError(_(
                    "El tiempo en sitio no puede ser negativo."
                ))

    @api.constrains('estado', 'motivo')
    def _check_motivo_respuesta(self):

        for rec in self:
            if rec.estado == 'respondido' and not rec.motivo:
                raise ValidationError(_(
                    "Un token respondido debe tener motivo."
                ))

    # ======================================================
    # BLOQUEO TRANSACCIONAL
    # ======================================================

    def _bloquear_ticket(self, ticket_id):
        """
        Serializa creación y respuesta de tokens
        correspondientes al mismo ticket.
        """

        self.env.cr.execute(
            """
            SELECT id
              FROM ticket_alquiler
             WHERE id = %s
             FOR UPDATE
            """,
            [ticket_id],
        )

    def _bloquear_token(self):

        self.ensure_one()

        self.env.cr.execute(
            """
            SELECT id
              FROM ticket_retiro_token
             WHERE id = %s
             FOR UPDATE
            """,
            [self.id],
        )

        self.invalidate_recordset()

    # ======================================================
    # CONTROL DE EXPIRACIÓN
    # ======================================================

    def _esta_expirado(self, ahora=None):

        self.ensure_one()

        ahora = ahora or fields.Datetime.now()

        return bool(
            not self.expira_en
            or self.expira_en <= ahora
        )

    def _expirar_si_corresponde(self, ahora=None):
        """
        Cambia el estado a expirado.

        No registra salida.
        No modifica el estado del ticket.
        """

        self.ensure_one()

        ahora = ahora or fields.Datetime.now()

        if self.estado != 'pendiente':
            return False

        if not self._esta_expirado(ahora):
            return False

        self.sudo().write({
            'estado': 'expirado',
            'expirado_en': ahora,
        })

        return True

    # ======================================================
    # CREAR TOKEN DE RETIRO
    # ======================================================

    @api.model
    def crear_token_retiro(
        self,
        ticket,
        lat=None,
        lon=None,
        tiempo_en_sitio=0,
    ):
        """
        Crea un token si no existe uno pendiente
        y vigente.

        Si ya existe, devuelve el mismo token.

        No cancela ni reemplaza un token vigente.
        """

        ticket.ensure_one()

        self._bloquear_ticket(ticket.id)

        ahora = fields.Datetime.now()

        pendientes = self.sudo().search([
            ('ticket_id', '=', ticket.id),
            ('estado', '=', 'pendiente'),
        ], order='id desc')

        vigente = self.browse()

        for anterior in pendientes:

            if anterior._esta_expirado(ahora):

                anterior.sudo().write({
                    'estado': 'expirado',
                    'expirado_en': ahora,
                })

            elif not vigente:

                vigente = anterior

            else:
                # Saneamiento de registros pendientes
                # duplicados que pudieran existir.
                anterior.sudo().write({
                    'estado': 'cancelado',
                    'cancelado_en': ahora,
                })

        if vigente:

            _logger.info(
                "[RETIRO-TOKEN] Reutilizando token "
                "vigente ticket_id=%s",
                ticket.id,
            )

            return vigente

        try:
            tiempo = float(tiempo_en_sitio or 0)
        except (ValueError, TypeError):
            raise UserError(_(
                "Tiempo en sitio inválido."
            ))

        if tiempo < 0:
            raise UserError(_(
                "El tiempo en sitio no puede ser negativo."
            ))

        def coordenada(valor, minimo, maximo):

            if valor is None or isinstance(valor, bool):
                return 0.0

            try:
                valor = float(valor)
            except (ValueError, TypeError, OverflowError):
                raise UserError(_(
                    "Coordenada GPS inválida."
                ))

            import math

            if not math.isfinite(valor):
                raise UserError(_(
                    "Coordenada GPS no finita."
                ))

            if not minimo <= valor <= maximo:
                raise UserError(_(
                    "Coordenada GPS fuera de rango."
                ))

            return valor

        expira = ahora + timedelta(
            minutes=MINUTOS_EXPIRACION
        )

        registro = self.sudo().create({
            'ticket_id': ticket.id,
            'token': secrets.token_urlsafe(32),
            'estado': 'pendiente',
            'lat_salida': coordenada(lat, -90, 90),
            'lon_salida': coordenada(lon, -180, 180),
            'tiempo_en_sitio_minutos': tiempo,
            'expira_en': expira,
        })

        _logger.info(
            "[RETIRO-TOKEN] Creado "
            "ticket_id=%s token_id=%s expira=%s",
            ticket.id,
            registro.id,
            expira,
        )

        return registro

    # ======================================================
    # BUSCAR TOKEN VÁLIDO
    # ======================================================

    @api.model
    def buscar_token_valido(self, token_str):
        """
        Devuelve únicamente tokens pendientes
        que aún no han expirado.
        """

        if not token_str or not isinstance(token_str, str):
            return self.browse()

        if len(token_str) > 256:
            return self.browse()

        ahora = fields.Datetime.now()

        registro = self.sudo().search([
            ('token', '=', token_str),
            ('estado', '=', 'pendiente'),
            ('expira_en', '>', ahora),
        ], limit=1)

        return registro

    # ======================================================
    # RESPONDER CONFIRMACIÓN
    # ======================================================

    def marcar_respondido(self, motivo):
        """
        Marca el motivo seleccionado.

        Esta función NO interpreta el motivo
        'finalizado' como autorización para
        finalizar administrativamente el ticket.

        La respuesta es una declaración del técnico,
        no una comprobación automática de la salida.

        El controlador debe verificar la autenticidad
        y el contexto de la solicitud pública.
        """

        self.ensure_one()

        motivos_validos = dict(MOTIVOS)

        if motivo not in motivos_validos:
            raise UserError(_(
                "Seleccione un motivo válido."
            ))

        self._bloquear_ticket(self.ticket_id.id)
        self._bloquear_token()

        ahora = fields.Datetime.now()

        if self.estado != 'pendiente':

            _logger.info(
                "[RETIRO-TOKEN] Respuesta ignorada "
                "token_id=%s estado=%s",
                self.id,
                self.estado,
            )

            return False

        if self._expirar_si_corresponde(ahora):

            _logger.warning(
                "[RETIRO-TOKEN] Respuesta fuera "
                "de plazo token_id=%s",
                self.id,
            )

            return False

        self.sudo().write({
            'estado': 'respondido',
            'motivo': motivo,
            'respondido_en': ahora,
        })

        _logger.info(
            "[RETIRO-TOKEN] Respondido "
            "token_id=%s ticket_id=%s motivo=%s",
            self.id,
            self.ticket_id.id,
            motivo,
        )

        # No llamar:
        # action_finalizar()
        # _registrar_finalizacion_tracking()
        # action_registrar_salida_sitio()
        #
        # La salida física exige su propia
        # validación GPS o confirmación autorizada.

        return True

    # ======================================================
    # CANCELAR TOKEN
    # ======================================================

    def cancelar(self):
        """
        Cancela una confirmación pendiente.

        El controlador o el evento GPS que invoca
        este método debe haber verificado el regreso.
        """

        self.ensure_one()

        self._bloquear_ticket(self.ticket_id.id)
        self._bloquear_token()

        if self.estado != 'pendiente':
            return False

        ahora = fields.Datetime.now()

        if self._expirar_si_corresponde(ahora):
            return False

        self.sudo().write({
            'estado': 'cancelado',
            'cancelado_en': ahora,
        })

        _logger.info(
            "[RETIRO-TOKEN] Cancelado "
            "token_id=%s ticket_id=%s",
            self.id,
            self.ticket_id.id,
        )

        return True

    # ======================================================
    # CRON - EXPIRAR TOKENS SIN RESPUESTA
    # ======================================================

    @api.model
    def cron_expirar_tokens_retiro(self):
        """
        Procesa tokens vencidos.

        Frecuencia recomendada: cada 5 minutos.

        IMPORTANTE:
        - No asume finalización.
        - No confirma salida física.
        - No desbloquea la siguiente visita.
        - Notifica a coordinación si no hubo respuesta.
        """

        ahora = fields.Datetime.now()

        expirados = self.sudo().search([
            ('estado', '=', 'pendiente'),
            ('expira_en', '<=', ahora),
        ], order='expira_en asc, id asc')

        if not expirados:
            return True

        _logger.info(
            "[RETIRO-TOKEN-CRON] %s tokens "
            "pendientes de expiración",
            len(expirados),
        )

        for token_rec in expirados:

            try:
                # Procesar cada token en un savepoint
                # para aislar fallos individuales.
                with self.env.cr.savepoint():

                    token_rec._bloquear_ticket(
                        token_rec.ticket_id.id
                    )

                    token_rec._bloquear_token()

                    if token_rec.estado != 'pendiente':
                        continue

                    if not token_rec._expirar_si_corresponde(
                        fields.Datetime.now()
                    ):
                        continue

                    ticket = token_rec.ticket_id

                    if not ticket.exists():
                        continue

                    tiempo = (
                        token_rec.tiempo_en_sitio_minutos
                    )

                    ticket._registrar_evento(
                        "⚠️ Confirmación de retiro "
                        "sin respuesta dentro de 15 minutos. "
                        "Salida física no confirmada. "
                        "Finalización administrativa sin cambios."
                    )

                    ubicacion = None

                    if (
                        token_rec.lat_salida
                        or token_rec.lon_salida
                    ):
                        ubicacion = {
                            'latitude': token_rec.lat_salida,
                            'longitude': token_rec.lon_salida,
                        }

                    # Notificación de incidencia.
                    # No modificar estado ni fechas
                    # administrativas del ticket.
                    try:

                        enviado = (
                            ticket.notificar_retiro_sin_respuesta(
                                ubicacion_actual=ubicacion,
                                tiempo_en_sitio=tiempo,
                            )
                        )

                        if not enviado:
                            _logger.error(
                                "[RETIRO-TOKEN-CRON] "
                                "Notificación no aceptada "
                                "token_id=%s ticket_id=%s",
                                token_rec.id,
                                ticket.id,
                            )

                    except Exception:
                        _logger.exception(
                            "[RETIRO-TOKEN-CRON] Error "
                            "notificando token_id=%s",
                            token_rec.id,
                        )

                    _logger.warning(
                        "[RETIRO-TOKEN-CRON] "
                        "Token expirado=%s ticket=%s "
                        "tiempo_sitio=%.1f "
                        "sin finalización automática",
                        token_rec.id,
                        ticket.id,
                        tiempo,
                    )

            except Exception:
                _logger.exception(
                    "[RETIRO-TOKEN-CRON] Error "
                    "procesando token_id=%s",
                    token_rec.id,
                )

        return True
