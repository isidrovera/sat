
# -*- coding: utf-8 -*-
"""
SAT - Gestión de visitas físicas GPS
Odoo 19

Una visita puede contener varios tickets.

REGLAS:
1. Un técnico solo puede tener una visita física activa.
2. No inicia otra ruta sin salida confirmada de la anterior.
3. Varios equipos en una misma sede comparten desplazamiento.
4. La salida física no finaliza tickets.
5. Finalizar tickets no registra salida física.
6. Las fechas deben proceder de eventos comprobables.
7. Cada evento conserva origen, fecha y referencia.
8. No se inventan eventos históricos.
"""

import logging
import math
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

ESTADOS_ACTIVOS = (
    'en_ruta',
    'en_sitio',
    'salida_pendiente',
)

DISTANCIA_SEDE_MAXIMA = 200


class SatVisitaTecnica(models.Model):
    _name = 'sat.visita.tecnica'
    _description = 'Visita física SAT'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'agenda asc, id asc'

    name = fields.Char(
        string='Visita',
        default='Nueva visita',
        required=True,
        copy=False,
        tracking=True,
    )

    tecnico_id = fields.Many2one(
        'res.users',
        string='Técnico responsable',
        required=True,
        index=True,
        tracking=True,
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        index=True,
        tracking=True,
    )

    sede_descripcion = fields.Char(
        string='Sede de atención',
        required=True,
    )

    latitud = fields.Float(
        string='Latitud',
        digits=(10, 7),
    )

    longitud = fields.Float(
        string='Longitud',
        digits=(10, 7),
    )

    agenda = fields.Datetime(
        string='Fecha programada',
        required=True,
        index=True,
        tracking=True,
    )

    ticket_ids = fields.One2many(
        'ticket.alquiler',
        'gps_visita_id',
        string='Tickets de la visita',
    )

    estado = fields.Selection(
        [
            ('programada', 'Programada'),
            ('en_ruta', 'En ruta'),
            ('en_sitio', 'En sitio'),
            ('salida_pendiente', 'Salida pendiente'),
            ('salida_confirmada', 'Salida confirmada'),
            ('cancelada', 'Cancelada'),
        ],
        string='Estado físico',
        default='programada',
        required=True,
        tracking=True,
        index=True,
    )

    fecha_en_ruta = fields.Datetime(
        string='Inicio real de ruta',
        readonly=True,
        copy=False,
    )

    fecha_llegada = fields.Datetime(
        string='Llegada física',
        readonly=True,
        copy=False,
    )

    fecha_salida = fields.Datetime(
        string='Salida física',
        readonly=True,
        copy=False,
    )

    fuente_ruta = fields.Selection(
        [
            ('manual', 'Acción del técnico'),
            ('traccar', 'Traccar'),
        ],
        readonly=True,
        copy=False,
    )

    fuente_llegada = fields.Selection(
        [
            ('manual', 'Confirmación manual'),
            ('traccar', 'Traccar'),
        ],
        readonly=True,
        copy=False,
    )

    fuente_salida = fields.Selection(
        [
            ('manual', 'Confirmación manual'),
            ('traccar', 'Traccar'),
        ],
        readonly=True,
        copy=False,
    )

    referencia_ruta = fields.Char(
        readonly=True,
        copy=False,
    )

    referencia_llegada = fields.Char(
        readonly=True,
        copy=False,
    )

    referencia_salida = fields.Char(
        readonly=True,
        copy=False,
    )

    evento_ids = fields.One2many(
        'sat.visita.evento',
        'visita_id',
        string='Historial de tracking',
    )

    tiempo_traslado_minutos = fields.Float(
        string='Tiempo de traslado',
        compute='_compute_tiempos',
        store=True,
    )

    tiempo_en_sitio_minutos = fields.Float(
        string='Permanencia física',
        compute='_compute_tiempos',
        store=True,
    )

    # ======================================================
    # UTILIDADES
    # ======================================================

    @staticmethod
    def _distancia_metros(lat1, lon1, lat2, lon2):
        radio = 6371000.0

        a1 = math.radians(lat1)
        a2 = math.radians(lat2)

        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(a1)
            * math.cos(a2)
            * math.sin(delta_lon / 2) ** 2
        )

        return 2 * radio * math.asin(
            min(1.0, math.sqrt(a))
        )

    @staticmethod
    def _coordenadas_validas(lat, lon):
        return (
            lat is not None
            and lon is not None
            and -90 <= float(lat) <= 90
            and -180 <= float(lon) <= 180
            and not (float(lat) == 0 and float(lon) == 0)
        )

    @api.depends(
        'fecha_en_ruta',
        'fecha_llegada',
        'fecha_salida',
    )
    def _compute_tiempos(self):
        for visita in self:
            visita.tiempo_traslado_minutos = 0
            visita.tiempo_en_sitio_minutos = 0

            if (
                visita.fecha_en_ruta
                and visita.fecha_llegada
                and visita.fecha_llegada >= visita.fecha_en_ruta
            ):
                visita.tiempo_traslado_minutos = round(
                    (
                        visita.fecha_llegada
                        - visita.fecha_en_ruta
                    ).total_seconds() / 60,
                    2,
                )

            if (
                visita.fecha_llegada
                and visita.fecha_salida
                and visita.fecha_salida >= visita.fecha_llegada
            ):
                visita.tiempo_en_sitio_minutos = round(
                    (
                        visita.fecha_salida
                        - visita.fecha_llegada
                    ).total_seconds() / 60,
                    2,
                )

    # ======================================================
    # VALIDACIONES DE AGRUPACIÓN
    # ======================================================

    def _validar_tickets(self):
        self.ensure_one()

        if not self.ticket_ids:
            raise UserError(_(
                "La visita necesita al menos un ticket."
            ))

        for ticket in self.ticket_ids:
            if ticket.responsable != self.tecnico_id:
                raise UserError(_(
                    "El ticket %s tiene otro técnico."
                ) % ticket.name)

            if ticket.partner_id != self.partner_id:
                raise UserError(_(
                    "El ticket %s corresponde a otro cliente."
                ) % ticket.name)

            # No asumir que todos los equipos de una
            # empresa están en la misma dirección.
            lat = ticket.equipo_latitud
            lon = ticket.equipo_longitud

            if not (
                self._coordenadas_validas(
                    self.latitud,
                    self.longitud,
                )
                and self._coordenadas_validas(lat, lon)
            ):
                raise UserError(_(
                    "No se puede verificar la ubicación "
                    "del ticket %s.\n"
                    "Confirme primero las coordenadas "
                    "de la sede y del equipo."
                ) % ticket.name)

            distancia = self._distancia_metros(
                self.latitud,
                self.longitud,
                lat,
                lon,
            )

            if distancia > DISTANCIA_SEDE_MAXIMA:
                raise UserError(_(
                    "El ticket %s está a %.0f metros "
                    "de la ubicación de la visita.\n"
                    "Debe programarse en otra visita "
                    "o corregirse su ubicación."
                ) % (ticket.name, distancia))

    @api.constrains(
        'ticket_ids',
        'tecnico_id',
        'partner_id',
    )
    def _check_tickets(self):
        for visita in self:
            for ticket in visita.ticket_ids:
                if (
                    ticket.responsable != visita.tecnico_id
                    or ticket.partner_id != visita.partner_id
                ):
                    raise ValidationError(_(
                        "Todos los tickets de una visita "
                        "deben tener el mismo técnico "
                        "y cliente."
                    ))

    # ======================================================
    # BLOQUEO POR TÉCNICO
    # ======================================================

    def _lock_tecnico(self):
        self.ensure_one()

        self.env.cr.execute(
            """
            SELECT id
              FROM res_users
             WHERE id = %s
             FOR UPDATE
            """,
            [self.tecnico_id.id],
        )

    def _otra_visita_activa(self):
        self.ensure_one()

        return self.sudo().search([
            ('tecnico_id', '=', self.tecnico_id.id),
            ('id', '!=', self.id),
            ('estado', 'in', ESTADOS_ACTIVOS),
        ], limit=1)

    def _validar_siguiente_ruta(self):
        self.ensure_one()

        self._lock_tecnico()

        anterior = self._otra_visita_activa()

        if anterior:
            raise UserError(_(
                "No se puede iniciar otro desplazamiento.\n\n"
                "El técnico tiene la visita %s "
                "sin salida física confirmada.\n\n"
                "Debe registrar y confirmar su salida "
                "antes de iniciar otra ruta."
            ) % anterior.name)

    # ======================================================
    # AUDITORÍA
    # ======================================================

    def _registrar_evento(
        self,
        tipo,
        fuente,
        fecha_evento=False,
        referencia=False,
        detalle=False,
    ):
        self.ensure_one()

        return self.env['sat.visita.evento'].sudo().create({
            'visita_id': self.id,
            'tipo': tipo,
            'fuente': fuente,
            'fecha_evento': fecha_evento or False,
            'referencia': referencia or False,
            'detalle': detalle or False,
        })

    def _validar_fecha(self, fecha, evento):
        fecha = (
            fields.Datetime.to_datetime(fecha)
            if fecha else False
        )

        if not fecha:
            raise UserError(_(
                "%s necesita una fecha verificable."
            ) % evento)

        if fecha.tzinfo is not None:
            from datetime import timezone
            fecha = fecha.astimezone(
                timezone.utc
            ).replace(tzinfo=None)

        if fecha > fields.Datetime.now():
            raise UserError(_(
                "%s no puede tener fecha futura."
            ) % evento)

        return fecha

    def _validar_fuente(self, fuente, referencia):
        if fuente not in ('manual', 'traccar'):
            raise UserError(_("Fuente no válida."))

        if not referencia:
            raise UserError(_(
                "Se requiere referencia de evidencia."
            ))

    # ======================================================
    # INICIO DE RUTA
    # ======================================================

    def action_iniciar_ruta(self):
        for visita in self:
            visita._validar_siguiente_ruta()
            visita._validar_tickets()

            if visita.estado != 'programada':
                raise UserError(_(
                    "Solo puede iniciar una visita programada."
                ))

            ahora = fields.Datetime.now()

            visita.write({
                'estado': 'en_ruta',
                'fecha_en_ruta': ahora,
                'fuente_ruta': 'manual',
                'referencia_ruta': (
                    'odoo-user:%s' % self.env.uid
                ),
            })

            visita._registrar_evento(
                tipo='ruta',
                fuente='manual',
                fecha_evento=ahora,
                referencia='odoo-user:%s' % self.env.uid,
                detalle=(
                    "Inicio registrado mediante acción "
                    "de usuario en Odoo. No se atribuye "
                    "a un evento GPS."
                ),
            )

            for ticket in visita.ticket_ids:
                if ticket.estado == 'proceso':
                    ticket.with_context(
                        sat_gps_visita_operacion=visita.id
                    ).write({
                        'estado': 'en_ruta',
                        'fecha_en_ruta': ahora,
                    })

        return True

    # ======================================================
    # LLEGADA FÍSICA
    # ======================================================

    def registrar_llegada_verificada(
        self,
        fecha_evento,
        referencia,
        fuente='traccar',
    ):
        self.ensure_one()

        fecha = self._validar_fecha(
            fecha_evento,
            'Llegada',
        )

        self._validar_fuente(fuente, referencia)
        self._lock_tecnico()
        self._validar_tickets()

        if self.fecha_llegada:
            return False

        if self.estado not in ('en_ruta', 'programada'):
            raise UserError(_(
                "Estado incompatible con la llegada."
            ))

        anterior = self._otra_visita_activa()

        if anterior:
            raise UserError(_(
                "Otra visita sigue físicamente abierta: %s"
            ) % anterior.name)

        if (
            self.fecha_en_ruta
            and fecha < self.fecha_en_ruta
        ):
            raise UserError(_(
                "La llegada es anterior al inicio de ruta."
            ))

        self.write({
            'estado': 'en_sitio',
            'fecha_llegada': fecha,
            'fuente_llegada': fuente,
            'referencia_llegada': referencia,
        })

        self._registrar_evento(
            'llegada',
            fuente,
            fecha,
            referencia,
        )

        for ticket in self.ticket_ids:
            if ticket.estado in ('proceso', 'en_ruta'):
                ticket.with_context(
                    sat_gps_visita_operacion=self.id
                ).write({
                    'estado': 'en_sitio',
                    'fecha_llegada': fecha,
                })

        return True

    # ======================================================
    # POSIBLE SALIDA
    # ======================================================

    def registrar_salida_detectada(
        self,
        referencia=False,
    ):
        self.ensure_one()
        self._lock_tecnico()

        if self.estado == 'salida_pendiente':
            return False

        if self.estado != 'en_sitio':
            return False

        self.write({
            'estado': 'salida_pendiente',
        })

        self._registrar_evento(
            tipo='salida_detectada',
            fuente='traccar',
            referencia=referencia,
            detalle=(
                "Se detectó posible retiro. "
                "Todavía no existe salida confirmada."
            ),
        )

        return True

    # ======================================================
    # REGRESO AL SITIO
    # ======================================================

    def registrar_regreso(
        self,
        fecha_evento,
        referencia,
    ):
        self.ensure_one()

        fecha = self._validar_fecha(
            fecha_evento,
            'Regreso',
        )

        if not referencia:
            raise UserError(_(
                "El regreso necesita evidencia."
            ))

        self._lock_tecnico()

        if self.estado != 'salida_pendiente':
            return False

        self.write({
            'estado': 'en_sitio',
        })

        self._registrar_evento(
            tipo='regreso',
            fuente='traccar',
            fecha_evento=fecha,
            referencia=referencia,
        )

        return True

    # ======================================================
    # SALIDA FÍSICA CONFIRMADA
    # ======================================================

    def registrar_salida_confirmada(
        self,
        fecha_evento,
        fuente,
        referencia,
    ):
        self.ensure_one()

        fecha = self._validar_fecha(
            fecha_evento,
            'Salida física',
        )

        self._validar_fuente(fuente, referencia)
        self._lock_tecnico()

        if self.fecha_salida:
            return False

        if self.estado not in (
            'en_sitio',
            'salida_pendiente',
        ):
            raise UserError(_(
                "No existe visita en sitio "
                "para registrar la salida."
            ))

        if not self.fecha_llegada:
            raise UserError(_(
                "No existe llegada registrada. "
                "Debe investigarse la inconsistencia "
                "sin inventar una fecha."
            ))

        if fecha < self.fecha_llegada:
            raise UserError(_(
                "La salida no puede ser anterior "
                "a la llegada."
            ))

        self.write({
            'estado': 'salida_confirmada',
            'fecha_salida': fecha,
            'fuente_salida': fuente,
            'referencia_salida': referencia,
        })

        self._registrar_evento(
            tipo='salida',
            fuente=fuente,
            fecha_evento=fecha,
            referencia=referencia,
        )

        for ticket in self.ticket_ids:
            if not ticket.fecha_salida_sitio:
                ticket.with_context(
                    sat_gps_visita_operacion=self.id
                ).write({
                    'fecha_salida_sitio': fecha,
                })

        # Una notificación para todos los tickets
        # correspondientes a la misma visita.
        if self.ticket_ids:
            principal = self.ticket_ids[0]

            try:
                enviado = principal.notificar_salida_sitio(
                    tickets_grupo=self.ticket_ids
                )

                self._registrar_evento(
                    tipo='aviso',
                    fuente='whatsapp',
                    detalle=(
                        'Solicitud de envío aceptada'
                        if enviado
                        else 'Solicitud de envío fallida'
                    ),
                )
            except Exception:
                _logger.exception(
                    "[SAT-GPS] Error notificando salida "
                    "de visita %s",
                    self.name,
                )

                self._registrar_evento(
                    tipo='incidencia',
                    fuente='whatsapp',
                    detalle='Excepción durante el envío',
                )

        _logger.info(
            "[SAT-GPS] Salida física registrada "
            "visita=%s fecha=%s tickets=%s",
            self.name,
            fecha,
            self.ticket_ids.ids,
        )

        # NO finaliza tickets.
        # NO ejecuta action_finalizar().
        # NO modifica fecha_finalizacion.

        return True

    # ======================================================
    # CANCELACIÓN
    # ======================================================

    def action_cancelar(self):
        for visita in self:
            visita._lock_tecnico()

            if visita.estado != 'programada':
                raise UserError(_(
                    "No puede cancelar una visita "
                    "que ya tiene desplazamiento."
                ))

            visita.write({
                'estado': 'cancelada',
            })

            visita._registrar_evento(
                tipo='incidencia',
                fuente='manual',
                detalle='Visita cancelada antes del inicio.',
            )

        return True


# ==========================================================
# HISTORIAL DE AUDITORÍA
# ==========================================================

class SatVisitaEvento(models.Model):
    _name = 'sat.visita.evento'
    _description = 'Auditoría de visitas SAT'
    _order = 'id desc'

    visita_id = fields.Many2one(
        'sat.visita.tecnica',
        required=True,
        ondelete='restrict',
        index=True,
    )

    tipo = fields.Selection(
        [
            ('ruta', 'Inicio de ruta'),
            ('llegada', 'Llegada'),
            ('salida_detectada', 'Salida detectada'),
            ('salida', 'Salida confirmada'),
            ('regreso', 'Regreso al sitio'),
            ('aviso', 'Notificación'),
            ('incidencia', 'Incidencia'),
        ],
        required=True,
    )

    fuente = fields.Char(
        string='Fuente',
        required=True,
    )

    fecha_evento = fields.Datetime(
        string='Fecha real del evento',
        readonly=True,
    )

    fecha_recepcion = fields.Datetime(
        string='Registrado en Odoo',
        default=fields.Datetime.now,
        required=True,
        readonly=True,
    )

    referencia = fields.Char(
        string='Referencia',
        readonly=True,
    )

    detalle = fields.Text(
        string='Detalle',
        readonly=True,
    )

    usuario_id = fields.Many2one(
        'res.users',
        default=lambda self: self.env.user,
        readonly=True,
    )

    def write(self, vals):
        raise UserError(_(
            "El historial no puede modificarse. "
            "Debe registrarse un evento correctivo."
        ))

    def unlink(self):
        raise UserError(_(
            "No se pueden eliminar eventos de auditoría."
        ))


# ==========================================================
# VÍNCULO CON TICKET.ALQUILER
# ==========================================================

class TicketAlquilerVisita(models.Model):
    _inherit = 'ticket.alquiler'

    gps_visita_id = fields.Many2one(
        'sat.visita.tecnica',
        string='Visita física GPS',
        ondelete='restrict',
        copy=False,
        index=True,
        tracking=True,
    )

    # ==========================================================
    # VINCULACIÓN AUTOMÁTICA: UNA VISITA POR SEDE Y HORARIO
    # ==========================================================

    @api.model
    def _gps_ticket_elegible_para_visita(self, ticket):
        """No agrupar tickets históricos, sin programación o sin ubicación."""
        return bool(
            ticket
            and not ticket.gps_visita_id
            and ticket.responsable
            and ticket.partner_id
            and ticket.agenda
            and ticket.estado in ('proceso', 'en_ruta', 'en_sitio', 'en_revision')
            and self.env['sat.visita.tecnica']._coordenadas_validas(
                ticket.equipo_latitud, ticket.equipo_longitud
            )
        )

    def _gps_vincular_visita_si_corresponde(self):
        """Vincula sin cambiar estado ni crear fecha GPS para el ticket."""
        Visita = self.env['sat.visita.tecnica'].sudo()
        for ticket in self.sudo():
            if not self._gps_ticket_elegible_para_visita(ticket):
                continue

            # Serializa la selección + creación para un mismo técnico.
            # En particular evita dos visitas duplicadas en concurrencia.
            self.env.cr.execute(
                'SELECT id FROM res_users WHERE id = %s FOR UPDATE',
                [ticket.responsable.id],
            )
            ticket.invalidate_recordset(['gps_visita_id'])
            if ticket.gps_visita_id:
                continue

            desde = ticket.agenda - timedelta(minutes=30)
            hasta = ticket.agenda + timedelta(minutes=30)
            candidatas = Visita.search([
                ('tecnico_id', '=', ticket.responsable.id),
                ('partner_id', '=', ticket.partner_id.id),
                ('agenda', '>=', desde),
                ('agenda', '<=', hasta),
                ('estado', 'in', ['programada', 'en_ruta', 'en_sitio']),
            ], order='agenda asc, id asc')

            visita = False
            for candidata in candidatas:
                if not Visita._coordenadas_validas(candidata.latitud, candidata.longitud):
                    continue
                distancia = Visita._distancia_metros(
                    candidata.latitud, candidata.longitud,
                    ticket.equipo_latitud, ticket.equipo_longitud,
                )
                if distancia <= DISTANCIA_SEDE_MAXIMA:
                    visita = candidata
                    break

            if not visita:
                visita = Visita.create({
                    'name': 'Visita %s - %s' % (
                        ticket.name or ticket.id,
                        ticket.partner_id.display_name or 'Cliente',
                    ),
                    'tecnico_id': ticket.responsable.id,
                    'partner_id': ticket.partner_id.id,
                    'sede_descripcion': ticket.partner_id.display_name or 'Sede por verificar',
                    'latitud': ticket.equipo_latitud,
                    'longitud': ticket.equipo_longitud,
                    'agenda': ticket.agenda,
                    'estado': 'programada',
                })
                visita._registrar_evento(
                    tipo='incidencia',
                    fuente='odoo',
                    detalle=(
                        'Visita agrupadora creada a partir del ticket %s. '
                        'No se reconstruyen ni presumen llegadas o rutas pasadas.'
                    ) % ticket.name,
                )

            ticket.with_context(sat_gps_vinculacion_interna=True).write({
                'gps_visita_id': visita.id,
            })
            _logger.info(
                '[SAT-GPS-VINCULO] ticket=%s visita=%s tecnico=%s estado_ticket=%s',
                ticket.name, visita.id, ticket.responsable.id, ticket.estado,
            )
        return True

    @api.model
    def action_vincular_visitas_gps_pendientes(self):
        """Reparación explícita de los tickets de HOY sin visita.

        Se ejecuta a demanda desde odoo shell o una acción de servidor,
        sin alterar estado, fecha_llegada ni fecha_en_ruta de los tickets.
        """
        from datetime import datetime, time, timezone
        from zoneinfo import ZoneInfo
        hoy = datetime.now(ZoneInfo('America/Lima')).date()
        desde = datetime.combine(hoy, time.min, tzinfo=ZoneInfo('America/Lima')).astimezone(timezone.utc).replace(tzinfo=None)
        hasta = datetime.combine(hoy, time.max, tzinfo=ZoneInfo('America/Lima')).astimezone(timezone.utc).replace(tzinfo=None)
        tickets = self.sudo().search([
            ('gps_visita_id', '=', False),
            ('agenda', '>=', desde),
            ('agenda', '<=', hasta),
            ('estado', 'in', ['proceso', 'en_ruta', 'en_sitio', 'en_revision']),
        ], order='responsable, partner_id, agenda, id')
        previos = len(tickets)
        tickets._gps_vincular_visita_si_corresponde()
        vinculados = len(tickets.filtered(lambda t: t.gps_visita_id))
        _logger.info('[SAT-GPS-VINCULO] Pendientes hoy=%s vinculados=%s', previos, vinculados)
        return {'candidatos': previos, 'vinculados': vinculados,
                'omitidos': previos - vinculados}

    @api.model_create_multi
    def create(self, vals_list):
        tickets = super().create(vals_list)
        if not self.env.context.get('sat_gps_vinculacion_interna'):
            tickets._gps_vincular_visita_si_corresponde()
        return tickets

    @api.constrains(
        'gps_visita_id',
        'responsable',
        'partner_id',
    )
    def _check_gps_visita(self):
        for ticket in self:
            visita = ticket.gps_visita_id

            if not visita:
                continue

            if ticket.responsable != visita.tecnico_id:
                raise ValidationError(_(
                    "El técnico del ticket no coincide "
                    "con la visita física."
                ))

            if ticket.partner_id != visita.partner_id:
                raise ValidationError(_(
                    "El cliente del ticket no coincide "
                    "con la visita física."
                ))

    def write(self, vals):
        if vals.get('estado') == 'en_ruta':
            for ticket in self:
                visita = ticket.gps_visita_id

                if not visita:
                    raise UserError(_(
                        "Debe asignar una visita física "
                        "antes de marcar En ruta."
                    ))

                visita._lock_tecnico()

                if visita.estado != 'en_ruta':
                    raise UserError(_(
                        "Primero debe iniciar la ruta "
                        "desde la visita física."
                    ))

                anterior = visita._otra_visita_activa()

                if anterior:
                    raise UserError(_(
                        "No puede iniciar ruta. "
                        "La visita anterior %s "
                        "no tiene salida confirmada."
                    ) % anterior.name)

        result = super().write(vals)
        if (not self.env.context.get('sat_gps_vinculacion_interna')
                and any(clave in vals for clave in (
                    'responsable', 'partner_id', 'agenda', 'estado',
                    'equipo_latitud', 'equipo_longitud',
                ))):
            self._gps_vincular_visita_si_corresponde()
        return result
