# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, date, time, timedelta
from dateutil.relativedelta import relativedelta
from pytz import timezone, UTC
import calendar
import logging

_logger = logging.getLogger(__name__)


class MantenimientoPlanificador(models.Model):
    _name = 'mantenimiento.planificador'
    _description = 'Planificador inteligente de mantenimientos'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_inicio desc, name'

    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True,
        default='Planificación mensual'
    )

    fecha_inicio = fields.Date(
        string='Fecha inicio',
        required=True,
        tracking=True,
        default=fields.Date.context_today
    )

    fecha_fin = fields.Date(
        string='Fecha fin',
        required=True,
        tracking=True
    )

    estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('generado', 'Generado'),
        ('en_proceso', 'En proceso'),
        ('finalizado', 'Finalizado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', tracking=True)

    tecnico_ids = fields.Many2many(
        'res.users',
        'mantenimiento_planificador_tecnico_rel',
        'planificador_id',
        'user_id',
        string='Técnicos disponibles para planificación',
        domain=[('share', '=', False)],
        tracking=True
    )

    zona_ids = fields.Many2many(
        'mantenimiento.zona',
        'mantenimiento_planificador_zona_rel',
        'planificador_id',
        'zona_id',
        string='Zonas incluidas',
        tracking=True
    )

    line_ids = fields.One2many(
        'mantenimiento.planificador.linea',
        'planificador_id',
        string='Líneas de planificación'
    )

    total_maquinas = fields.Integer(
        string='Máquinas',
        compute='_compute_totales',
        store=False
    )

    total_pendientes = fields.Integer(
        string='Pendientes',
        compute='_compute_totales',
        store=False
    )

    total_confirmadas = fields.Integer(
        string='Confirmadas',
        compute='_compute_totales',
        store=False
    )

    total_programadas = fields.Integer(
        string='Programadas',
        compute='_compute_totales',
        store=False
    )

    total_sin_cupo = fields.Integer(
        string='Sin cupo',
        compute='_compute_totales',
        store=False
    )

    total_reasignar = fields.Integer(
        string='Por reasignar',
        compute='_compute_totales',
        store=False
    )

    resumen_html = fields.Html(
        string='Resumen',
        compute='_compute_resumen_html',
        sanitize=False
    )

    observacion = fields.Text(
        string='Observaciones'
    )

    # ============================================================
    # DEFAULTS / ONCHANGE
    # ============================================================

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)

        today = fields.Date.context_today(self)
        inicio = today.replace(day=1)
        ultimo_dia = calendar.monthrange(inicio.year, inicio.month)[1]
        fin = inicio.replace(day=ultimo_dia)

        vals.setdefault('fecha_inicio', inicio)
        vals.setdefault('fecha_fin', fin)
        vals.setdefault('name', 'Planificación %s/%s' % (
            str(inicio.month).zfill(2),
            inicio.year
        ))

        return vals

    @api.onchange('fecha_inicio')
    def _onchange_fecha_inicio(self):
        for rec in self:
            if rec.fecha_inicio and not rec.fecha_fin:
                ultimo_dia = calendar.monthrange(
                    rec.fecha_inicio.year,
                    rec.fecha_inicio.month
                )[1]
                rec.fecha_fin = rec.fecha_inicio.replace(day=ultimo_dia)

            if rec.fecha_inicio:
                rec.name = 'Planificación %s/%s' % (
                    str(rec.fecha_inicio.month).zfill(2),
                    rec.fecha_inicio.year
                )

    # ============================================================
    # COMPUTES
    # ============================================================

    @api.depends('line_ids.estado')
    def _compute_totales(self):
        for rec in self:
            rec.total_maquinas = len(rec.line_ids)
            rec.total_pendientes = len(rec.line_ids.filtered(lambda l: l.estado == 'pendiente'))
            rec.total_confirmadas = len(rec.line_ids.filtered(lambda l: l.estado == 'confirmado'))
            rec.total_programadas = len(rec.line_ids.filtered(lambda l: l.estado == 'programado'))
            rec.total_sin_cupo = len(rec.line_ids.filtered(lambda l: l.estado == 'sin_cupo'))
            rec.total_reasignar = len(rec.line_ids.filtered(lambda l: l.estado == 'reasignar'))

    @api.depends(
        'total_maquinas',
        'total_pendientes',
        'total_confirmadas',
        'total_programadas',
        'total_sin_cupo',
        'total_reasignar',
    )
    def _compute_resumen_html(self):
        for rec in self:
            rec.resumen_html = """
                <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:12px;">
                    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:14px;">
                        <div style="color:#6b7280;font-size:12px;">Máquinas</div>
                        <div style="font-size:26px;font-weight:700;">%s</div>
                    </div>
                    <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:14px;padding:14px;">
                        <div style="color:#9a3412;font-size:12px;">Pendientes</div>
                        <div style="font-size:26px;font-weight:700;">%s</div>
                    </div>
                    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:14px;padding:14px;">
                        <div style="color:#1d4ed8;font-size:12px;">Confirmadas</div>
                        <div style="font-size:26px;font-weight:700;">%s</div>
                    </div>
                    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:14px;padding:14px;">
                        <div style="color:#166534;font-size:12px;">Programadas</div>
                        <div style="font-size:26px;font-weight:700;">%s</div>
                    </div>
                    <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:14px;padding:14px;">
                        <div style="color:#991b1b;font-size:12px;">Sin cupo</div>
                        <div style="font-size:26px;font-weight:700;">%s</div>
                    </div>
                    <div style="background:#faf5ff;border:1px solid #e9d5ff;border-radius:14px;padding:14px;">
                        <div style="color:#7e22ce;font-size:12px;">Reasignar</div>
                        <div style="font-size:26px;font-weight:700;">%s</div>
                    </div>
                </div>
            """ % (
                rec.total_maquinas,
                rec.total_pendientes,
                rec.total_confirmadas,
                rec.total_programadas,
                rec.total_sin_cupo,
                rec.total_reasignar,
            )

    # ============================================================
    # VALIDACIONES
    # ============================================================

    @api.constrains('fecha_inicio', 'fecha_fin')
    def _check_fechas(self):
        for rec in self:
            if rec.fecha_inicio and rec.fecha_fin and rec.fecha_fin < rec.fecha_inicio:
                raise ValidationError(_("La fecha fin no puede ser menor que la fecha inicio."))

    # ============================================================
    # HELPERS DE ZONA HORARIA
    # ============================================================

    def _agenda_to_local_dt(self, agenda_value):
        """
        Convierte un Datetime UTC (como se almacena en la BD) al timezone del usuario.

        Devuelve un datetime naive en hora local, listo para comparar con
        horas locales (hora_inicio, hora_fin del perfil del técnico) y para
        cálculos con timedelta.
        """
        if not agenda_value:
            return False

        user_tz = self.env.user.tz or 'America/Lima'
        local_tz = timezone(user_tz)

        agenda_utc = fields.Datetime.to_datetime(agenda_value)
        return UTC.localize(agenda_utc).astimezone(local_tz).replace(tzinfo=None)

    # ============================================================
    # HELPERS GENERALES
    # ============================================================

    def _get_zona_por_distrito(self, distrito):
        if not distrito:
            return False

        distrito = distrito.strip()
        ZonaDistrito = self.env['mantenimiento.zona.distrito']

        exacto = ZonaDistrito.search([
            ('name', '=ilike', distrito),
            ('active', '=', True),
            ('zona_id.active', '=', True),
        ], limit=1)

        if exacto:
            return exacto.zona_id

        candidatos = ZonaDistrito.search([
            ('active', '=', True),
            ('zona_id.active', '=', True),
            ('alias', '!=', False),
        ])

        distrito_lower = distrito.lower()

        for item in candidatos:
            alias_list = []
            if item.alias:
                alias_list = [a.strip().lower() for a in item.alias.split(',') if a.strip()]
            if distrito_lower in alias_list:
                return item.zona_id

        return False

    def _get_perfiles_tecnicos(self):
        self.ensure_one()

        Perfil = self.env['mantenimiento.tecnico.perfil']

        domain = [('active', '=', True)]

        if self.tecnico_ids:
            domain.append(('tecnico_id', 'in', self.tecnico_ids.ids))

        return Perfil.search(domain)

    def _float_to_time(self, value):
        value = value or 0.0
        hours = int(value)
        minutes = int(round((value - hours) * 60))

        if minutes >= 60:
            hours += 1
            minutes -= 60

        hours = min(max(hours, 0), 23)
        minutes = min(max(minutes, 0), 59)

        return time(hour=hours, minute=minutes)

    def _make_datetime(self, fecha, hora_float):
        """
        Construye un datetime local (naive) a partir de una fecha y una hora float.

        El resultado se compara contra los datetimes locales devueltos por
        _agenda_to_local_dt, por lo que ambos deben estar en la misma escala
        (hora local naive).
        """
        return datetime.combine(fecha, self._float_to_time(hora_float))

    def _ticket_ocupa_tecnico(self, tecnico_id, inicio_dt, fin_dt, excluir_ticket_id=False):
        """
        Verifica si el técnico tiene tickets que se cruzan con el rango dado.

        inicio_dt y fin_dt deben venir en hora local naive. Los tickets en BD
        tienen agenda en UTC, así que se convierten a hora local antes de
        comparar.
        """
        domain = [
            ('responsable', '=', tecnico_id),
            ('agenda', '!=', False),
            ('estado', 'not in', ['finalizado']),
        ]

        if excluir_ticket_id:
            domain.append(('id', '!=', excluir_ticket_id))

        tickets = self.env['ticket.alquiler'].search(domain)

        for ticket in tickets:
            ticket_inicio = self._agenda_to_local_dt(ticket.agenda)
            if not ticket_inicio:
                continue
            ticket_fin = ticket_inicio + timedelta(hours=2)

            if ticket_inicio < fin_dt and ticket_fin > inicio_dt:
                return True

        return False

    def _contar_tickets_tecnico_fecha(self, tecnico_id, fecha):
        """
        Cuenta tickets del técnico en una fecha local específica.

        Como agenda se almacena en UTC, hay que considerar la conversión:
        un ticket a las 23:00 hora Lima (= 04:00 UTC del día siguiente) debe
        contarse en el día Lima correcto. Se construye el rango UTC equivalente
        al día local.
        """
        user_tz = self.env.user.tz or 'America/Lima'
        local_tz = timezone(user_tz)

        inicio_local = local_tz.localize(datetime.combine(fecha, time.min))
        fin_local = local_tz.localize(datetime.combine(fecha + timedelta(days=1), time.min))

        inicio_utc = inicio_local.astimezone(UTC).replace(tzinfo=None)
        fin_utc = fin_local.astimezone(UTC).replace(tzinfo=None)

        return self.env['ticket.alquiler'].search_count([
            ('responsable', '=', tecnico_id),
            ('agenda', '>=', inicio_utc),
            ('agenda', '<', fin_utc),
            ('estado', 'not in', ['finalizado']),
        ])

    def _get_horas_ocupadas_lineas(self, tecnico_id, fecha):
        lineas = self.env['mantenimiento.planificador.linea'].search([
            ('tecnico_id', '=', tecnico_id),
            ('fecha_programada', '=', fecha),
            ('estado', 'in', ['programado', 'confirmado']),
            ('hora_inicio', '!=', False),
            ('hora_fin', '!=', False),
        ])

        return lineas

    def _linea_ocupa_tecnico(self, tecnico_id, fecha, hora_inicio, hora_fin):
        lineas = self._get_horas_ocupadas_lineas(tecnico_id, fecha)

        for linea in lineas:
            if linea.hora_inicio < hora_fin and linea.hora_fin > hora_inicio:
                return True

        return False

    def _perfil_compatible_zona(self, perfil, zona, permitir_flexible=True):
        if not zona:
            return True

        if zona in perfil.zona_preferida_ids:
            return True

        if permitir_flexible and zona.flexible:
            return True

        return False

    def _buscar_tecnicos_disponibles(
        self,
        fecha,
        hora_inicio,
        duracion_horas,
        zona=False,
        cantidad=1,
        ignorar_zona=False,
        excluir_ticket_id=False,
    ):
        self.ensure_one()

        perfiles = self._get_perfiles_tecnicos()
        candidatos = []

        hora_fin = hora_inicio + duracion_horas
        inicio_dt = self._make_datetime(fecha, hora_inicio)
        fin_dt = self._make_datetime(fecha, hora_fin)

        for perfil in perfiles:
            tecnico = perfil.tecnico_id

            disp = perfil.get_disponibilidad_fecha(fecha)

            # Si el técnico está bloqueado/no disponible, nunca se asigna.
            if not disp.get('disponible'):
                continue

            permite_asignaciones_multiples = bool(
                disp.get('permite_asignaciones_multiples')
            )

            # Si NO está activado el modo múltiple, se respeta el horario normal.
            # Si está activado, se permite asignar incluso fuera del rango horario,
            # siempre que la disponibilidad de ese día esté aprobada y disponible=True.
            if not permite_asignaciones_multiples:
                if hora_inicio < disp.get('hora_inicio') or hora_fin > disp.get('hora_fin'):
                    continue

            # Validación de zona.
            # El modo múltiple no debe saltarse la zona, salvo que ignorar_zona=True.
            if not ignorar_zona:
                if not self._perfil_compatible_zona(perfil, zona, permitir_flexible=True):
                    continue

            ocupados_dia = self._contar_tickets_tecnico_fecha(tecnico.id, fecha)
            ocupados_lineas = len(self._get_horas_ocupadas_lineas(tecnico.id, fecha))

            capacidad = disp.get('capacidad') or 0
            total_ocupados = ocupados_dia + ocupados_lineas

            # En modo normal se valida capacidad y cruces.
            # En modo múltiple se permite varias asignaciones el mismo día/hora.
            if not permite_asignaciones_multiples:
                if total_ocupados >= capacidad:
                    continue

                if self._ticket_ocupa_tecnico(
                    tecnico.id,
                    inicio_dt,
                    fin_dt,
                    excluir_ticket_id=excluir_ticket_id
                ):
                    continue

                if self._linea_ocupa_tecnico(
                    tecnico.id,
                    fecha,
                    hora_inicio,
                    hora_fin
                ):
                    continue

            score = 0

            if zona and zona in perfil.zona_preferida_ids:
                score += 50

            if permite_asignaciones_multiples:
                # Se prioriza al técnico que tiene la excepción manual activa.
                score += 1000
            else:
                score += max(0, capacidad - total_ocupados) * 10
                score -= total_ocupados * 5

            candidatos.append({
                'perfil': perfil,
                'tecnico': tecnico,
                'score': score,
                'capacidad': capacidad,
                'ocupados': total_ocupados,
                'permite_asignaciones_multiples': permite_asignaciones_multiples,
            })

        candidatos = sorted(candidatos, key=lambda x: x['score'], reverse=True)

        if len(candidatos) < cantidad:
            return []

        return candidatos[:cantidad]

    def _buscar_horario_disponible(
        self,
        fecha,
        zona=False,
        cantidad_tecnicos=1,
        duracion_horas=2.0,
        hora_preferida=False,
        ignorar_zona=False,
    ):
        self.ensure_one()

        if hora_preferida:
            tecnicos = self._buscar_tecnicos_disponibles(
                fecha=fecha,
                hora_inicio=hora_preferida,
                duracion_horas=duracion_horas,
                zona=zona,
                cantidad=cantidad_tecnicos,
                ignorar_zona=ignorar_zona,
            )
            if tecnicos:
                return {
                    'fecha': fecha,
                    'hora_inicio': hora_preferida,
                    'hora_fin': hora_preferida + duracion_horas,
                    'tecnicos': tecnicos,
                }

        bloques = [
            8.0,
            10.0,
            12.0,
            14.0,
            16.0,
        ]

        for hora in bloques:
            tecnicos = self._buscar_tecnicos_disponibles(
                fecha=fecha,
                hora_inicio=hora,
                duracion_horas=duracion_horas,
                zona=zona,
                cantidad=cantidad_tecnicos,
                ignorar_zona=ignorar_zona,
            )
            if tecnicos:
                return {
                    'fecha': fecha,
                    'hora_inicio': hora,
                    'hora_fin': hora + duracion_horas,
                    'tecnicos': tecnicos,
                }

        return False

    def _buscar_slot_desde_fecha(
        self,
        fecha_base,
        zona=False,
        cantidad_tecnicos=1,
        duracion_horas=2.0,
        hora_preferida=False,
        ignorar_zona=False,
        dias_busqueda=20,
    ):
        self.ensure_one()

        if not fecha_base:
            fecha_base = fields.Date.context_today(self)

        for offset in range(0, dias_busqueda + 1):
            fecha = fecha_base + timedelta(days=offset)

            if fecha < self.fecha_inicio or fecha > self.fecha_fin:
                continue

            slot = self._buscar_horario_disponible(
                fecha=fecha,
                zona=zona,
                cantidad_tecnicos=cantidad_tecnicos,
                duracion_horas=duracion_horas,
                hora_preferida=hora_preferida if offset == 0 else False,
                ignorar_zona=ignorar_zona,
            )

            if slot:
                return slot

        return False

    # ============================================================
    # GENERACIÓN DE LÍNEAS
    # ============================================================

    def action_generar_lineas(self):
        for rec in self:
            if rec.estado not in ('borrador', 'generado'):
                raise UserError(_("Solo puede generar líneas en estado borrador o generado."))

            rec.line_ids.unlink()

            domain = [
                ('control_mantenimiento', '=', True),
                ('estado_alquiler_id', '=', 'alquilada'),
                ('fecha_recurrente', '>=', rec.fecha_inicio),
                ('fecha_recurrente', '<=', rec.fecha_fin),
            ]

            equipos = self.env['alquiler'].search(domain, order='distrito, cliente_id, serie')

            creadas = 0

            for equipo in equipos:
                zona = rec._get_zona_por_distrito(equipo.distrito)

                if rec.zona_ids and zona and zona not in rec.zona_ids:
                    continue

                self.env['mantenimiento.planificador.linea'].create({
                    'planificador_id': rec.id,
                    'equipo_id': equipo.id,
                    'cliente_id': equipo.cliente_id.id if equipo.cliente_id else False,
                    'distrito': equipo.distrito,
                    'zona_id': zona.id if zona else False,
                    'fecha_ideal': equipo.fecha_recurrente,
                    'estado': 'pendiente',
                    'cantidad_tecnicos': 1,
                    'duracion_horas': 2.0,
                })
                creadas += 1

            rec.estado = 'generado'

            rec.message_post(
                body=_("Se generaron %s líneas de planificación.") % creadas,
                message_type='notification'
            )

    def action_auto_asignar(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Primero debe generar las líneas de planificación."))

            lineas = rec.line_ids.filtered(lambda l: l.estado in ('pendiente', 'confirmado', 'reasignar'))

            asignadas = 0
            sin_cupo = 0

            for linea in lineas.sorted(lambda l: (
                l.fecha_confirmada or l.fecha_ideal or rec.fecha_inicio,
                l.zona_id.name or '',
                l.distrito or '',
            )):
                ok = linea.action_buscar_y_asignar_slot(silent=True)
                if ok:
                    asignadas += 1
                else:
                    sin_cupo += 1

            rec.estado = 'en_proceso'

            rec.message_post(
                body=_(
                    "Auto-asignación finalizada.<br/>"
                    "Programadas: %s<br/>"
                    "Sin cupo: %s"
                ) % (asignadas, sin_cupo),
                message_type='notification'
            )

    def action_ver_lineas_sin_cupo(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Líneas sin cupo'),
            'res_model': 'mantenimiento.planificador.linea',
            'view_mode': 'list,form',
            'domain': [
                ('planificador_id', '=', self.id),
                ('estado', '=', 'sin_cupo'),
            ],
        }

    def action_ver_lineas_reasignar(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Líneas por reasignar'),
            'res_model': 'mantenimiento.planificador.linea',
            'view_mode': 'list,form',
            'domain': [
                ('planificador_id', '=', self.id),
                ('estado', '=', 'reasignar'),
            ],
        }


class MantenimientoPlanificadorLinea(models.Model):
    _name = 'mantenimiento.planificador.linea'
    _description = 'Línea de planificación de mantenimiento'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_programada asc, zona_id, distrito, cliente_id'

    planificador_id = fields.Many2one(
        'mantenimiento.planificador',
        string='Planificador',
        required=True,
        ondelete='cascade',
        index=True
    )

    equipo_id = fields.Many2one(
        'alquiler',
        string='Máquina',
        required=True,
        index=True,
        tracking=True
    )

    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        tracking=True,
        index=True
    )

    distrito = fields.Char(
        string='Distrito',
        tracking=True,
        index=True
    )

    zona_id = fields.Many2one(
        'mantenimiento.zona',
        string='Zona',
        tracking=True,
        index=True
    )

    fecha_ideal = fields.Date(
        string='Fecha ideal',
        tracking=True,
        index=True
    )

    fecha_confirmada = fields.Date(
        string='Fecha confirmada por cliente',
        tracking=True,
        index=True
    )

    hora_confirmada = fields.Float(
        string='Hora confirmada',
        tracking=True,
        help='Hora confirmada por el cliente. Ej: 14.0 = 2:00 pm.'
    )

    fecha_programada = fields.Date(
        string='Fecha programada',
        tracking=True,
        index=True
    )

    hora_inicio = fields.Float(
        string='Hora inicio',
        tracking=True
    )

    hora_fin = fields.Float(
        string='Hora fin',
        tracking=True
    )

    tecnico_id = fields.Many2one(
        'res.users',
        string='Técnico principal',
        tracking=True,
        index=True
    )

    tecnico_apoyo_ids = fields.Many2many(
        'res.users',
        'mantenimiento_planificador_linea_apoyo_rel',
        'linea_id',
        'user_id',
        string='Técnicos de apoyo',
        tracking=True
    )

    cantidad_tecnicos = fields.Integer(
        string='Cantidad de técnicos requeridos',
        default=1,
        tracking=True
    )

    duracion_horas = fields.Float(
        string='Duración estimada',
        default=2.0,
        tracking=True
    )

    ignorar_zona = fields.Boolean(
        string='Ignorar zona',
        default=False,
        tracking=True,
        help='Si está activo, puede asignarse cualquier técnico disponible sin priorizar zona.'
    )

    prioridad = fields.Selection([
        ('0', 'Baja'),
        ('1', 'Normal'),
        ('2', 'Alta'),
        ('3', 'Crítica'),
    ], string='Prioridad', default='1', tracking=True)

    estado = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('confirmado', 'Confirmado sin asignar'),
        ('programado', 'Programado'),
        ('sin_cupo', 'Sin cupo'),
        ('reasignar', 'Requiere reasignación'),
        ('ticket_creado', 'Ticket creado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='pendiente', tracking=True, index=True)

    ticket_id = fields.Many2one(
        'ticket.alquiler',
        string='Ticket generado',
        readonly=True,
        copy=False
    )

    nota = fields.Text(
        string='Notas'
    )

    resumen = fields.Char(
        string='Resumen',
        compute='_compute_resumen',
        store=True
    )

    @api.depends('equipo_id', 'cliente_id', 'distrito', 'fecha_programada', 'tecnico_id')
    def _compute_resumen(self):
        for rec in self:
            partes = []
            if rec.equipo_id:
                partes.append(rec.equipo_id.serie or rec.equipo_id.display_name)
            if rec.cliente_id:
                partes.append(rec.cliente_id.name)
            if rec.distrito:
                partes.append(rec.distrito)
            if rec.fecha_programada:
                partes.append(rec.fecha_programada.strftime('%d/%m/%Y'))
            if rec.tecnico_id:
                partes.append(rec.tecnico_id.name)
            rec.resumen = ' · '.join(partes)

    @api.onchange('equipo_id')
    def _onchange_equipo_id(self):
        for rec in self:
            if rec.equipo_id:
                rec.cliente_id = rec.equipo_id.cliente_id.id if rec.equipo_id.cliente_id else False
                rec.distrito = rec.equipo_id.distrito
                rec.fecha_ideal = rec.equipo_id.fecha_recurrente

                zona = rec.planificador_id._get_zona_por_distrito(rec.equipo_id.distrito) if rec.planificador_id else False
                rec.zona_id = zona.id if zona else False

    @api.constrains('cantidad_tecnicos', 'duracion_horas')
    def _check_valores(self):
        for rec in self:
            if rec.cantidad_tecnicos < 1:
                raise ValidationError(_("La cantidad de técnicos debe ser mínimo 1."))

            if rec.duracion_horas <= 0:
                raise ValidationError(_("La duración debe ser mayor a 0."))

    def action_confirmar_cliente(self):
        for rec in self:
            rec.estado = 'confirmado'
            rec.message_post(
                body=_("Cliente confirmado. Pendiente de asignar técnico."),
                message_type='notification'
            )

    def action_marcar_reasignar(self):
        for rec in self:
            rec.estado = 'reasignar'
            rec.message_post(
                body=_("Marcado para reasignación."),
                message_type='notification'
            )

    def action_buscar_y_asignar_slot(self, silent=False):
        self.ensure_one()

        plan = self.planificador_id

        fecha_base = self.fecha_confirmada or self.fecha_ideal or plan.fecha_inicio

        slot = plan._buscar_slot_desde_fecha(
            fecha_base=fecha_base,
            zona=self.zona_id,
            cantidad_tecnicos=self.cantidad_tecnicos,
            duracion_horas=self.duracion_horas,
            hora_preferida=self.hora_confirmada if self.fecha_confirmada else False,
            ignorar_zona=self.ignorar_zona,
            dias_busqueda=30,
        )

        if not slot:
            self.write({
                'estado': 'sin_cupo',
                'nota': _("No se encontró disponibilidad para la fecha/hora solicitada."),
            })

            if not silent:
                raise UserError(_("No se encontró cupo disponible para esta línea."))

            return False

        tecnicos = slot['tecnicos']
        tecnico_principal = tecnicos[0]['tecnico']
        tecnicos_apoyo = [t['tecnico'].id for t in tecnicos[1:]]

        self.write({
            'fecha_programada': slot['fecha'],
            'hora_inicio': slot['hora_inicio'],
            'hora_fin': slot['hora_fin'],
            'tecnico_id': tecnico_principal.id,
            'tecnico_apoyo_ids': [(6, 0, tecnicos_apoyo)],
            'estado': 'programado',
            'nota': False,
        })

        if not silent:
            self.message_post(
                body=_(
                    "✅ Slot asignado: %s de %.2f a %.2f con técnico %s."
                ) % (
                    slot['fecha'].strftime('%d/%m/%Y'),
                    slot['hora_inicio'],
                    slot['hora_fin'],
                    tecnico_principal.name,
                ),
                message_type='notification'
            )

        return True

    def _get_agenda_datetime(self):
        """
        Construye el valor Datetime (UTC) para asignar al campo agenda del ticket.

        La línea guarda hora_inicio en hora local. Para que Odoo almacene
        correctamente en UTC, primero localizamos el datetime en el tz del
        usuario y luego convertimos a UTC naive (que es lo que espera Odoo
        al escribir en un Datetime).
        """
        self.ensure_one()

        if not self.fecha_programada:
            return False

        hora = self.hora_inicio or 8.0
        hours = int(hora)
        minutes = int(round((hora - hours) * 60))

        dt_local_naive = datetime.combine(
            self.fecha_programada,
            time(hour=hours, minute=minutes)
        )

        user_tz = self.env.user.tz or 'America/Lima'
        local_tz = timezone(user_tz)

        dt_local = local_tz.localize(dt_local_naive)
        dt_utc = dt_local.astimezone(UTC).replace(tzinfo=None)

        return dt_utc

    def action_crear_ticket(self):
        for rec in self:
            if rec.ticket_id:
                continue

            if rec.estado != 'programado':
                raise UserError(_("Solo se puede crear ticket para líneas programadas."))

            if not rec.tecnico_id:
                raise UserError(_("Debe tener técnico asignado."))

            agenda_dt = rec._get_agenda_datetime()

            ticket_vals = {
                'partner_id': rec.cliente_id.id if rec.cliente_id else False,
                'product_alquiler': rec.equipo_id.id,
                'tipo_servicio_id': 'mantenimiento_preventivo',
                'estado': 'nuevo',
                'description': _(
                    "Mantenimiento preventivo programado desde planificador %s."
                ) % rec.planificador_id.name,
                'direccion_id_r': rec.equipo_id.direccion,
                'contacto_id_r': rec.equipo_id.contacto_id,
                'celular_id_r': rec.equipo_id.celular,
                'corre_id_r': rec.equipo_id.correo_,
                'responsable': rec.tecnico_id.id,
                'agenda': agenda_dt,
            }

            ticket = self.env['ticket.alquiler'].create(ticket_vals)

            if hasattr(ticket, 'crear_evento_calendario'):
                ticket.crear_evento_calendario()

            rec.write({
                'ticket_id': ticket.id,
                'estado': 'ticket_creado',
            })

            rec.equipo_id.write({
                'estado_programacion': 'confirmado',
                'fecha_confirmacion': fields.Datetime.now(),
                'fecha_programada_mantenimiento': rec.fecha_programada,
                'tecnico_mantenimiento_id': rec.tecnico_id.id,
            })

            rec.message_post(
                body=_("🎫 Ticket creado: %s") % ticket.name,
                message_type='notification'
            )

    def action_ver_ticket(self):
        self.ensure_one()

        if not self.ticket_id:
            raise UserError(_("Esta línea aún no tiene ticket."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Ticket de mantenimiento'),
            'res_model': 'ticket.alquiler',
            'res_id': self.ticket_id.id,
            'view_mode': 'form',
            'target': 'current',
        }