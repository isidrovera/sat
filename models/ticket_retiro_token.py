# -*- coding: utf-8 -*-
"""
Tokens de un solo uso para confirmación de motivo de retiro
============================================================
Archivo: models/ticket_retiro_token.py

Cuando el GPS detecta que el técnico salió de la geocerca sin terminar,
se crea un token vinculado al ticket. El técnico recibe un link por
WhatsApp que abre una página donde elige el motivo del retiro.

Estados del token:
  - pendiente  : enviado, esperando respuesta
  - respondido : técnico eligió un motivo
  - expirado   : pasaron 15 min sin respuesta (procesado por cron)
  - cancelado  : técnico regresó a la geocerca antes de responder
"""
import secrets
import logging
from datetime import timedelta

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

MOTIVOS = [
    ('cliente_tarde',    'El cliente aún no llega, lo estoy esperando'),
    ('sin_autorizacion', 'No me autorizaron el ingreso'),
    ('ausencia_temporal','Salí momentáneamente, regreso a terminar'),
    ('finalizado',       'Ya finalicé el servicio'),
]

MINUTOS_EXPIRACION = 15


class TicketRetiroToken(models.Model):
    _name        = 'ticket.retiro.token'
    _description = 'Token de confirmación de motivo de retiro'
    _order       = 'create_date desc'
    _rec_name    = 'token'

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
        index=True,
        readonly=True,
        default=lambda self: secrets.token_urlsafe(32),
    )
    estado = fields.Selection([
        ('pendiente',  'Pendiente'),
        ('respondido', 'Respondido'),
        ('expirado',   'Expirado'),
        ('cancelado',  'Cancelado'),
    ], string='Estado', default='pendiente', required=True, index=True)

    motivo = fields.Selection(
        MOTIVOS,
        string='Motivo elegido',
    )
    motivo_label = fields.Char(
        string='Motivo (texto)',
        compute='_compute_motivo_label',
        store=True,
    )

    # Datos de contexto al momento de crear el token
    lat_salida    = fields.Float(string='Latitud al salir',  digits=(10, 7))
    lon_salida    = fields.Float(string='Longitud al salir', digits=(10, 7))
    tiempo_en_sitio_minutos = fields.Float(string='Minutos en sitio al salir')

    # Control de expiración
    expira_en = fields.Datetime(string='Expira en', readonly=True)
    respondido_en = fields.Datetime(string='Respondido en', readonly=True)

    # Datos del técnico para el mensaje
    tecnico_nombre = fields.Char(
        string='Técnico',
        related='ticket_id.responsable.name',
        store=True,
    )

    _sql_constraints = [
        ('token_unique', 'unique(token)', 'El token debe ser único.'),
    ]

    # ═══════════════════════════════════════════════════════════════
    #  COMPUTE
    # ═══════════════════════════════════════════════════════════════

    @api.depends('motivo')
    def _compute_motivo_label(self):
        motivos_dict = dict(MOTIVOS)
        for rec in self:
            rec.motivo_label = motivos_dict.get(rec.motivo, '') if rec.motivo else ''

    # ═══════════════════════════════════════════════════════════════
    #  MÉTODOS
    # ═══════════════════════════════════════════════════════════════

    @api.model
    def crear_token_retiro(self, ticket, lat=None, lon=None, tiempo_en_sitio=0):
        """
        Crea un token nuevo para el ticket dado.
        Cancela cualquier token pendiente anterior del mismo ticket.
        Retorna el token creado.
        """
        # Cancelar tokens pendientes anteriores del mismo ticket
        tokens_anteriores = self.sudo().search([
            ('ticket_id', '=', ticket.id),
            ('estado', '=', 'pendiente'),
        ])
        if tokens_anteriores:
            tokens_anteriores.sudo().write({'estado': 'cancelado'})
            _logger.info(
                "[RETIRO-TOKEN] Cancelados %d tokens anteriores para ticket %s",
                len(tokens_anteriores), ticket.name,
            )

        ahora    = fields.Datetime.now()
        expira   = ahora + timedelta(minutes=MINUTOS_EXPIRACION)
        token_rec = self.sudo().create({
            'ticket_id':              ticket.id,
            'estado':                 'pendiente',
            'lat_salida':             lat or 0.0,
            'lon_salida':             lon or 0.0,
            'tiempo_en_sitio_minutos': tiempo_en_sitio,
            'expira_en':              expira,
        })
        _logger.info(
            "[RETIRO-TOKEN] Token creado para ticket %s | expira: %s",
            ticket.name, expira,
        )
        return token_rec

    def marcar_respondido(self, motivo):
        """
        Marca el token como respondido con el motivo elegido.
        Retorna True si se procesó, False si ya no es válido.
        """
        self.ensure_one()
        if self.estado != 'pendiente':
            _logger.warning(
                "[RETIRO-TOKEN] Token %s ya no es pendiente (estado: %s)",
                self.token, self.estado,
            )
            return False
        self.sudo().write({
            'estado':        'respondido',
            'motivo':        motivo,
            'respondido_en': fields.Datetime.now(),
        })
        _logger.info(
            "[RETIRO-TOKEN] Token %s respondido con motivo: %s",
            self.token, motivo,
        )
        return True

    def cancelar(self):
        """Cancela el token (técnico regresó a geocerca)."""
        self.ensure_one()
        if self.estado == 'pendiente':
            self.sudo().write({'estado': 'cancelado'})
            _logger.info("[RETIRO-TOKEN] Token %s cancelado (regresó a geocerca)", self.token)

    @api.model
    def buscar_token_valido(self, token_str):
        """
        Busca un token pendiente y no expirado por su string.
        Retorna el record o None.
        """
        ahora = fields.Datetime.now()
        token_rec = self.sudo().search([
            ('token',  '=', token_str),
            ('estado', '=', 'pendiente'),
            ('expira_en', '>', ahora),
        ], limit=1)
        return token_rec or None

    # ═══════════════════════════════════════════════════════════════
    #  CRON: expirar tokens sin respuesta
    # ═══════════════════════════════════════════════════════════════

    @api.model
    def cron_expirar_tokens_retiro(self):
        """
        Procesa tokens pendientes que superaron su tiempo de expiración.
        Frecuencia: cada 5 minutos.

        Lógica según tiempo en sitio al momento de salir:
          - >= 60 min en sitio → asumir finalizado, cerrar ticket
          - <  60 min en sitio → registrar abandono sin motivo, notificar coordinación
        """
        ahora    = fields.Datetime.now()
        expirados = self.sudo().search([
            ('estado',    '=', 'pendiente'),
            ('expira_en', '<=', ahora),
        ])
        if not expirados:
            return

        _logger.info(
            "[RETIRO-TOKEN-CRON] Procesando %d tokens expirados", len(expirados)
        )

        for token_rec in expirados:
            try:
                token_rec.sudo().write({'estado': 'expirado'})
                ticket = token_rec.ticket_id

                if not ticket or ticket.estado in ('finalizado', 'nuevo'):
                    continue

                tiempo = token_rec.tiempo_en_sitio_minutos
                ubicacion_actual = {
                    'latitude':  token_rec.lat_salida or None,
                    'longitude': token_rec.lon_salida or None,
                }

                if tiempo >= 60:
                    # Asumir finalizado
                    _logger.info(
                        "[RETIRO-TOKEN-CRON] Ticket %s — %d min en sitio → asumiendo finalizado",
                        ticket.name, tiempo,
                    )
                    ticket._registrar_evento(
                        f"Retiro sin respuesta — {tiempo:.0f}min en sitio → asumido finalizado"
                    )
                    ticket.sudo()._registrar_finalizacion_tracking()
                else:
                    # Abandono sin motivo, notificar coordinación
                    _logger.warning(
                        "[RETIRO-TOKEN-CRON] Ticket %s — %d min en sitio → abandono sin motivo",
                        ticket.name, tiempo,
                    )
                    ticket._registrar_evento(
                        f"⚠️ Técnico abandonó ubicación sin confirmar motivo "
                        f"({tiempo:.0f}min en sitio)"
                    )
                    try:
                        ticket.notificar_retiro_sin_respuesta(
                            ubicacion_actual=ubicacion_actual,
                            tiempo_en_sitio=tiempo,
                        )
                    except Exception as e:
                        _logger.error(
                            "[RETIRO-TOKEN-CRON] Error notificando abandono %s: %s",
                            ticket.name, e,
                        )

            except Exception as e:
                _logger.error(
                    "[RETIRO-TOKEN-CRON] Error procesando token %s: %s",
                    token_rec.token, e,
                )