# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


LIMA_TZ = pytz.timezone('America/Lima')


class EvaluacionCierreMensual(models.Model):
    _name = 'evaluacion.cierre.mensual'
    _description = 'Cierre mensual de producción técnica'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_inicio desc, id desc'

    # ============================================================
    # DATOS PRINCIPALES
    # ============================================================

    name = fields.Char(
        string='Cierre',
        default='Nuevo',
        copy=False,
        readonly=True,
        tracking=True,
    )

    fecha_inicio = fields.Date(
        string='Inicio del mes',
        required=True,
        tracking=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )

    fecha_fin = fields.Date(
        string='Fin del mes',
        compute='_compute_fecha_fin',
        store=True,
        readonly=True,
    )

    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('calculado', 'Calculado'),
        ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='borrador', required=True, tracking=True)

    fecha_calculo = fields.Datetime(
        string='Fecha del último cálculo',
        readonly=True,
        copy=False,
        tracking=True,
    )

    calculado_por_id = fields.Many2one(
        'res.users',
        string='Calculado por',
        readonly=True,
        copy=False,
        tracking=True,
    )

    fecha_confirmacion = fields.Datetime(
        string='Fecha de confirmación',
        readonly=True,
        copy=False,
        tracking=True,
    )

    confirmado_por_id = fields.Many2one(
        'res.users',
        string='Confirmado por',
        readonly=True,
        copy=False,
        tracking=True,
    )

    observaciones = fields.Text(
        string='Observaciones de gerencia',
        tracking=True,
    )

    # ============================================================
    # LÍNEAS
    # ============================================================

    maquina_line_ids = fields.One2many(
        'evaluacion.cierre.mensual.maquina',
        'cierre_id',
        string='Máquinas del cierre',
        copy=False,
    )

    tecnico_line_ids = fields.One2many(
        'evaluacion.cierre.mensual.tecnico',
        'cierre_id',
        string='Metas por técnico',
        copy=False,
    )

    descarga_contenedor_ids = fields.One2many(
        'evaluacion.cierre.mensual.descarga',
        'cierre_id',
        string='Descargas de contenedores',
        copy=False,
        help=(
            'Registra cada llegada de contenedor, su duración y los técnicos '
            'que participaron en la descarga.'
        ),
    )

    # ============================================================
    # RESUMEN DEL POOL
    # ============================================================

    meta_base_taller = fields.Float(
        string='Meta base mensual del taller',
        default=60.0,
        required=True,
        tracking=True,
        digits=(16, 2),
        help=(
            'Meta mensual definida por gerencia. Se ajusta según la '
            'disponibilidad real del equipo y nunca supera el pool exigible.'
        ),
    )

    meta_total_taller_ajustada = fields.Float(
        string='Meta total ajustada del taller',
        readonly=True,
        copy=False,
        tracking=True,
        digits=(16, 2),
        help=(
            'Meta base de 60 máquinas ajustada por la disponibilidad real '
            'del taller y limitada al pool exigible del periodo.'
        ),
    )

    factor_disponibilidad_taller = fields.Float(
        string='Factor de disponibilidad del taller',
        readonly=True,
        copy=False,
        digits=(16, 4),
        help=(
            'Relación entre las horas reales disponibles de taller y las '
            'horas programadas de los técnicos que participan en producción.'
        ),
    )

    contenedores_recibidos = fields.Integer(
        string='Contenedores recibidos',
        compute='_compute_resumen',
        store=True,
    )

    horas_descarga_contenedores = fields.Float(
        string='Horas de descarga de contenedores',
        compute='_compute_resumen',
        store=True,
        digits=(16, 2),
        help='Suma de la duración total registrada para las descargas del mes.',
    )

    horas_hombre_descarga_contenedores = fields.Float(
        string='Horas-hombre en descargas',
        compute='_compute_resumen',
        store=True,
        digits=(16, 2),
        help=(
            'Duración de cada descarga multiplicada por la cantidad de '
            'técnicos participantes.'
        ),
    )

    maquinas_descargadas_mes = fields.Integer(
        string='Descargadas en el mes',
        compute='_compute_resumen',
        store=True,
    )

    maquinas_backlog_inicial = fields.Integer(
        string='Backlog inicial',
        compute='_compute_resumen',
        store=True,
    )

    maquinas_reactivadas = fields.Integer(
        string='Reactivadas',
        compute='_compute_resumen',
        store=True,
    )

    maquinas_excluidas = fields.Integer(
        string='Excluidas',
        compute='_compute_resumen',
        store=True,
    )

    maquinas_entregadas_sin_revision = fields.Integer(
        string='Entregadas sin revisión',
        compute='_compute_resumen',
        store=True,
    )

    maquinas_finalizadas_mes = fields.Integer(
        string='Finalizadas en el mes',
        compute='_compute_resumen',
        store=True,
    )

    maquinas_pendientes_cierre = fields.Integer(
        string='Pendientes al cierre',
        compute='_compute_resumen',
        store=True,
    )

    pool_total_exigible = fields.Integer(
        string='Pool total exigible',
        compute='_compute_resumen',
        store=True,
        help=(
            'Cantidad de máquinas válidas para repartir entre los técnicos. '
            'Incluye backlog válido, descargas del mes y reactivaciones. '
            'No incluye máquinas con problemas, de partes ni entregadas sin revisión.'
        ),
    )

    capacidad_total_taller_horas = fields.Float(
        string='Capacidad total de taller (horas)',
        compute='_compute_resumen',
        store=True,
        digits=(16, 2),
    )

    resumen_gerencia = fields.Html(
        string='Resumen para gerencia',
        compute='_compute_resumen_gerencia',
        store=True,
        sanitize=False,
    )

    # ============================================================
    # VALIDACIONES
    # ============================================================

    _sql_constraints = [
        (
            'evaluacion_cierre_mensual_periodo_unique',
            'unique(fecha_inicio)',
            'Ya existe un cierre mensual para este periodo.',
        ),
    ]

    @api.constrains('fecha_inicio')
    def _check_fecha_inicio(self):
        for rec in self:
            if rec.fecha_inicio and rec.fecha_inicio.day != 1:
                raise ValidationError(
                    _('La fecha de inicio debe ser el primer día del mes.')
                )

    @api.depends('fecha_inicio')
    def _compute_fecha_fin(self):
        for rec in self:
            if not rec.fecha_inicio:
                rec.fecha_fin = False
                continue

            siguiente_mes = fields.Date.add(rec.fecha_inicio, months=1)
            rec.fecha_fin = fields.Date.subtract(siguiente_mes, days=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                fecha_inicio = fields.Date.to_date(
                    vals.get('fecha_inicio')
                    or fields.Date.context_today(self).replace(day=1)
                )
                vals['name'] = 'CIERRE/%s' % fecha_inicio.strftime('%Y-%m')

        return super().create(vals_list)

    def write(self, vals):
        campos_bloqueados = {
            'fecha_inicio',
            'maquina_line_ids',
            'tecnico_line_ids',
            'descarga_contenedor_ids',
            'meta_base_taller',
        }

        if campos_bloqueados.intersection(vals):
            confirmados = self.filtered(lambda rec: rec.state == 'confirmado')
            if confirmados:
                raise UserError(
                    _('No se puede modificar el contenido de un cierre confirmado.')
                )

        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda rec: rec.state == 'confirmado'):
            raise UserError(_('No se puede eliminar un cierre confirmado.'))
        return super().unlink()

    # ============================================================
    # ZONA HORARIA
    # ============================================================

    @api.model
    def _fecha_lima_a_utc_naive(self, fecha, hora_valor=time.min):
        fecha = fields.Date.to_date(fecha)
        local_dt = LIMA_TZ.localize(datetime.combine(fecha, hora_valor))
        return local_dt.astimezone(pytz.utc).replace(tzinfo=None)

    def _get_rango_utc(self):
        self.ensure_one()
        fecha_fin_exclusiva = fields.Date.add(self.fecha_fin, days=1)
        return (
            self._fecha_lima_a_utc_naive(self.fecha_inicio),
            self._fecha_lima_a_utc_naive(fecha_fin_exclusiva),
        )

    # ============================================================
    # HELPERS DE REPARACIONES
    # ============================================================

    @api.model
    def _get_campo_responsable_reparacion(self):
        Reparacion = self.env['reparaciones.reparaciones']
        for campo in ('responsable_id', 'tecnico_id', 'usuario_id'):
            if campo in Reparacion._fields:
                return campo
        return False

    @api.model
    def _get_usuario_reparacion(self, reparacion):
        """
        Convierte el responsable de la reparación a res.users sin asumir
        si el campo apunta directamente a res.users o a hr.employee.
        """
        campo = self._get_campo_responsable_reparacion()
        if not campo or not reparacion:
            return self.env['res.users']

        responsable = reparacion[campo]
        if not responsable:
            return self.env['res.users']

        if responsable._name == 'res.users':
            return responsable

        if responsable._name == 'hr.employee':
            if 'user_id' in responsable._fields and responsable.user_id:
                return responsable.user_id

        return self.env['res.users']

    @api.model
    def _get_fecha_finalizacion_reparacion(self, reparacion):
        if not reparacion:
            return False

        for campo in (
            'fecha_finalizacion',
            'fecha_fin',
            'fecha_cierre',
            'write_date',
        ):
            if campo in reparacion._fields and reparacion[campo]:
                return reparacion[campo]

        return False

    @api.model
    def _get_reparaciones_maquina(self, maquina):
        if 'reparaciones_ids' in maquina._fields:
            return maquina.reparaciones_ids

        return self.env['reparaciones.reparaciones'].search([
            ('maquina_id', '=', maquina.id),
        ])

    def _get_reparacion_finalizada_mes(self, maquina, inicio_utc, fin_utc):
        reparaciones = self._get_reparaciones_maquina(maquina)
        if not reparaciones:
            return self.env['reparaciones.reparaciones']

        candidatas = self.env['reparaciones.reparaciones']

        for reparacion in reparaciones:
            fecha_finalizacion = self._get_fecha_finalizacion_reparacion(reparacion)
            if not fecha_finalizacion:
                continue

            fecha_dt = fields.Datetime.to_datetime(fecha_finalizacion)
            if inicio_utc <= fecha_dt < fin_utc:
                candidatas |= reparacion

        if not candidatas:
            return candidatas

        return candidatas.sorted(
            key=lambda rep: self._get_fecha_finalizacion_reparacion(rep),
            reverse=True,
        )[:1]

    def _get_reparacion_finalizada_antes(self, maquina, inicio_utc):
        reparaciones = self._get_reparaciones_maquina(maquina)
        candidatas = self.env['reparaciones.reparaciones']

        for reparacion in reparaciones:
            fecha_finalizacion = self._get_fecha_finalizacion_reparacion(reparacion)
            if not fecha_finalizacion:
                continue

            if fields.Datetime.to_datetime(fecha_finalizacion) < inicio_utc:
                candidatas |= reparacion

        if not candidatas:
            return candidatas

        return candidatas.sorted(
            key=lambda rep: self._get_fecha_finalizacion_reparacion(rep),
            reverse=True,
        )[:1]

    # ============================================================
    # CÁLCULO DE MÁQUINAS
    # ============================================================

    def _get_maquinas_candidatas(self):
        self.ensure_one()

        inicio_utc, fin_utc = self._get_rango_utc()

        Sat = self.env['sat.sat']
        Reparacion = self.env['reparaciones.reparaciones']

        # ============================================================
        # 1. MÁQUINAS INGRESADAS DURANTE EL MES
        # ============================================================
        maquinas_ingresadas_mes = Sat.search([
            ('check_ingreso', '=', True),
            ('ingreso_fecha', '>=', inicio_utc),
            ('ingreso_fecha', '<', fin_utc),
        ])

        # ============================================================
        # 2. BACKLOG ACTIVO DE MESES ANTERIORES
        # Solo máquinas que siguen pendientes de revisión.
        # No se incluyen entregadas, con problemas ni de partes.
        # ============================================================
        maquinas_backlog = Sat.search([
            ('check_ingreso', '=', True),
            ('ingreso_fecha', '!=', False),
            ('ingreso_fecha', '<', inicio_utc),
            ('estado_ventas_id', 'in', [
                'sin_revisar',
                'para_revision',
                'en_revision',
                'finalizado',
            ]),
        ])

        # ============================================================
        # 3. MÁQUINAS ENTREGADAS DURANTE EL MES
        # Se incluyen solamente para comprobar si fueron entregadas
        # sin una reparación finalizada.
        # ============================================================
        maquinas_entregadas_mes = Sat.browse()

        if 'fecha_entrega' in Sat._fields:
            maquinas_entregadas_mes = Sat.search([
                ('check_ingreso', '=', True),
                ('estado_ventas_id', '=', 'entregada'),
                ('fecha_entrega', '>=', self.fecha_inicio),
                ('fecha_entrega', '<=', self.fecha_fin),
            ])

        # ============================================================
        # 4. MÁQUINAS CON REPARACIÓN FINALIZADA DURANTE EL MES
        # Aunque actualmente estén entregadas, deben contar como
        # producción del periodo en que fueron finalizadas.
        # ============================================================
        maquinas_finalizadas_mes = Sat.browse()

        if (
            'fecha_finalizacion' in Reparacion._fields
            and 'maquina_id' in Reparacion._fields
        ):
            reparaciones_mes = Reparacion.search([
                ('fecha_finalizacion', '>=', inicio_utc),
                ('fecha_finalizacion', '<', fin_utc),
                ('maquina_id', '!=', False),
            ])

            maquinas_finalizadas_mes = reparaciones_mes.mapped('maquina_id')

        # La unión de recordsets elimina duplicados automáticamente.
        maquinas = (
            maquinas_ingresadas_mes
            | maquinas_backlog
            | maquinas_entregadas_mes
            | maquinas_finalizadas_mes
        )

        return maquinas.sorted(
            key=lambda maquina: (
                maquina.ingreso_fecha or fields.Datetime.from_string(
                    '1970-01-01 00:00:00'
                ),
                maquina.id,
            )
        )
    def _clasificar_maquina(self, maquina, inicio_utc, fin_utc):
        reparaciones = self._get_reparaciones_maquina(maquina)

        reparacion_mes = self._get_reparacion_finalizada_mes(
            maquina,
            inicio_utc,
            fin_utc,
        )

        reparacion_anterior = self._get_reparacion_finalizada_antes(
            maquina,
            inicio_utc,
        )

        estado = maquina.estado_ventas_id or 'sin_revisar'
        ingreso_fecha = fields.Datetime.to_datetime(maquina.ingreso_fecha)

        es_ingreso_mes = bool(
            ingreso_fecha
            and inicio_utc <= ingreso_fecha < fin_utc
        )

        es_ingreso_anterior = bool(
            ingreso_fecha
            and ingreso_fecha < inicio_utc
        )

        fecha_entrega = False
        entrega_en_mes = False

        if 'fecha_entrega' in maquina._fields and maquina.fecha_entrega:
            fecha_entrega = fields.Date.to_date(maquina.fecha_entrega)

            entrega_en_mes = bool(
                self.fecha_inicio
                <= fecha_entrega
                <= self.fecha_fin
            )

        valores = {
            'maquina_id': maquina.id,
            'ingreso_fecha': maquina.ingreso_fecha,
            'estado_cierre': estado,
            'origen_pool': (
                'ingreso_mes'
                if es_ingreso_mes
                else 'backlog'
            ),
            'incluida_pool': False,
            'excluida': False,
            'motivo_exclusion': False,
            'finalizada_mes': False,
            'pendiente_cierre': False,
            'reparacion_id': False,
            'tecnico_id': False,
            'fecha_finalizacion': False,
        }

        # ============================================================
        # 1. FINALIZADA DURANTE EL MES
        # Siempre cuenta como producción del mes de finalización.
        # ============================================================
        if reparacion_mes:
            usuario = self._get_usuario_reparacion(reparacion_mes)

            valores.update({
                'incluida_pool': True,
                'finalizada_mes': True,
                'pendiente_cierre': False,
                'reparacion_id': reparacion_mes.id,
                'tecnico_id': usuario.id if usuario else False,
                'fecha_finalizacion':
                    self._get_fecha_finalizacion_reparacion(reparacion_mes),
            })

            return valores

        # ============================================================
        # 2. YA HABÍA FINALIZADO ANTES DEL MES
        # No pertenece al cierre actual.
        # ============================================================
        if reparacion_anterior:
            return False

        # ============================================================
        # 3. ENTREGADA SIN REPARACIÓN FINALIZADA
        #
        # Solo se registra cuando:
        # - ingresó durante el mes, o
        # - su fecha de entrega pertenece al mes.
        #
        # Así se evita traer entregas históricas.
        # ============================================================
        if estado == 'entregada':
            if not es_ingreso_mes and not entrega_en_mes:
                return False

            valores.update({
                'excluida': True,
                'motivo_exclusion': (
                    'entregada_sin_reparacion'
                    if not reparaciones
                    else 'entregada_sin_finalizacion'
                ),
            })

            return valores

        # ============================================================
        # 4. CON PROBLEMAS O DE PARTES
        #
        # Si ingresaron durante el mes, se muestran como exclusión.
        # Las históricas no se arrastran indefinidamente al cierre.
        # ============================================================
        if estado == 'con_problemas':
            if not es_ingreso_mes:
                return False

            valores.update({
                'excluida': True,
                'motivo_exclusion': 'con_problemas',
            })

            return valores

        if estado == 'de_partes':
            if not es_ingreso_mes:
                return False

            valores.update({
                'excluida': True,
                'motivo_exclusion': 'de_partes',
            })

            return valores

        # ============================================================
        # 5. MÁQUINAS ACTIVAS DEL POOL
        # ============================================================
        if estado in (
            'sin_revisar',
            'para_revision',
            'en_revision',
            'finalizado',
        ):
            valores.update({
                'incluida_pool': True,
                'pendiente_cierre': True,
                'origen_pool': (
                    'ingreso_mes'
                    if es_ingreso_mes
                    else 'backlog'
                ),
            })

            return valores

        # Cualquier estado no reconocido queda fuera del cierre.
        return False

    def _calcular_lineas_maquinas(self):
        self.ensure_one()

        inicio_utc, fin_utc = self._get_rango_utc()
        comandos = [(5, 0, 0)]

        for maquina in self._get_maquinas_candidatas():
            valores = self._clasificar_maquina(
                maquina,
                inicio_utc,
                fin_utc,
            )
            if valores:
                comandos.append((0, 0, valores))

        self.write({'maquina_line_ids': comandos})

    # ============================================================
    # CAPACIDAD DE TÉCNICOS
    # ============================================================

    @api.model
    def _get_horas_programadas_dia(self, perfil, fecha):
        trabaja, hora_inicio, hora_fin = perfil._get_horario_base_fecha(fecha)

        if not trabaja or hora_fin <= hora_inicio:
            return 0.0

        return max(0.0, hora_fin - hora_inicio)

    def _get_horas_programadas_mes(self, perfil):
        self.ensure_one()

        total = 0.0
        fecha = self.fecha_inicio

        while fecha <= self.fecha_fin:
            total += self._get_horas_programadas_dia(perfil, fecha)
            fecha += timedelta(days=1)

        return total

    def _get_horas_ausencia_reduce_meta(self, perfil):
        self.ensure_one()

        Ausencia = self.env['mantenimiento.tecnico.ausencia']

        ausencias = Ausencia.search([
            ('tecnico_id', '=', perfil.tecnico_id.id),
            ('impacto_evaluacion', '=', 'reduce_meta'),
            ('estado', 'in', ['aprobado', 'ausente_activo', 'cerrado']),
            ('fecha_inicio', '<=', self.fecha_fin),
            '|',
            ('fecha_fin', '=', False),
            ('fecha_fin', '>=', self.fecha_inicio),
        ])

        horas_por_fecha = defaultdict(float)

        for ausencia in ausencias:
            fecha_inicio = max(ausencia.fecha_inicio, self.fecha_inicio)
            fecha_fin = min(
                ausencia.fecha_fin or self.fecha_fin,
                self.fecha_fin,
            )

            fecha = fecha_inicio
            while fecha <= fecha_fin:
                horas_dia = self._get_horas_programadas_dia(perfil, fecha)

                if horas_dia > 0:
                    if ausencia.dia_completo:
                        horas_ausencia = horas_dia
                    else:
                        horas_ausencia = min(
                            horas_dia,
                            max(
                                0.0,
                                (ausencia.hora_fin or 0.0)
                                - (ausencia.hora_inicio or 0.0),
                            ),
                        )

                    horas_por_fecha[fecha] = min(
                        horas_dia,
                        horas_por_fecha[fecha] + horas_ausencia,
                    )

                fecha += timedelta(days=1)

        return sum(horas_por_fecha.values())

    def _get_horas_tickets(self, perfil):
        self.ensure_one()

        inicio_utc, fin_utc = self._get_rango_utc()

        tickets = self.env['ticket.alquiler'].search([
            ('responsable', '=', perfil.tecnico_id.id),
            ('estado', '=', 'finalizado'),
            ('agenda', '>=', inicio_utc),
            ('agenda', '<', fin_utc),
        ])

        horas_por_fecha = defaultdict(float)
        tickets_sin_retorno = 0

        for ticket in tickets:
            agenda_lima = fields.Datetime.context_timestamp(
                self.with_context(tz='America/Lima'),
                ticket.agenda,
            )
            fecha = agenda_lima.date()
            horas_dia = self._get_horas_programadas_dia(perfil, fecha)

            if horas_dia <= 0:
                continue

            if ticket.retorno_id == 'no':
                tickets_sin_retorno += 1
                trabaja, hora_inicio, hora_fin = perfil._get_horario_base_fecha(fecha)
                hora_agenda = agenda_lima.hour + agenda_lima.minute / 60.0
                horas_ticket = max(
                    perfil.duracion_servicio_horas or 0.0,
                    hora_fin - max(hora_inicio, hora_agenda),
                )
            else:
                horas_ticket = perfil.duracion_servicio_horas or 0.0

            horas_por_fecha[fecha] = min(
                horas_dia,
                horas_por_fecha[fecha] + max(0.0, horas_ticket),
            )

        return {
            'horas': sum(horas_por_fecha.values()),
            'cantidad': len(tickets),
            'sin_retorno': tickets_sin_retorno,
        }

    def _get_produccion_tecnico(self, usuario):
        self.ensure_one()
        return len(
            self.maquina_line_ids.filtered(
                lambda line: (
                    line.finalizada_mes
                    and line.tecnico_id.id == usuario.id
                )
            )
        )

    def _get_horas_descarga_tecnico(self, usuario):
        """Devuelve las horas de descarga asignadas al técnico en el cierre."""
        self.ensure_one()

        if not usuario:
            return 0.0

        total = 0.0
        for descarga in self.descarga_contenedor_ids:
            if usuario in descarga.tecnico_ids:
                total += descarga.horas_totales or 0.0

        return total

    def _preparar_tecnicos(self):
        self.ensure_one()

        perfiles = self.env['mantenimiento.tecnico.perfil'].search([
            ('active', '=', True),
        ], order='tecnico_id asc')

        datos = []
        capacidad_total = 0.0
        capacidad_programada_taller = 0.0

        for perfil in perfiles:
            horas_programadas = self._get_horas_programadas_mes(perfil)
            horas_ausencia = min(
                horas_programadas,
                self._get_horas_ausencia_reduce_meta(perfil),
            )
            tickets = self._get_horas_tickets(perfil)
            horas_descarga = self._get_horas_descarga_tecnico(
                perfil.tecnico_id
            )

            horas_base = max(0.0, horas_programadas - horas_ausencia)

            if perfil.tipo_operativo == 'servicios':
                horas_taller = 0.0
            else:
                horas_no_productivas = min(
                    horas_base,
                    (tickets['horas'] or 0.0) + (horas_descarga or 0.0),
                )
                horas_taller = max(0.0, horas_base - horas_no_productivas)

            if perfil.tipo_operativo in ('taller', 'mixto'):
                capacidad_programada_taller += horas_programadas
                capacidad_total += horas_taller

            datos.append({
                'perfil': perfil,
                'horas_programadas': horas_programadas,
                'horas_ausencia': horas_ausencia,
                'horas_tickets': tickets['horas'],
                'horas_descarga': horas_descarga,
                'tickets_count': tickets['cantidad'],
                'tickets_sin_retorno': tickets['sin_retorno'],
                'horas_taller': horas_taller,
            })

        return datos, capacidad_total, capacidad_programada_taller

    def _calcular_lineas_tecnicos(self):
        self.ensure_one()

        (
            datos,
            capacidad_total,
            capacidad_programada_taller,
        ) = self._preparar_tecnicos()

        pool = self.pool_total_exigible or 0.0
        factor_disponibilidad = (
            capacidad_total / capacidad_programada_taller
            if capacidad_programada_taller > 0
            else 0.0
        )
        factor_disponibilidad = max(0.0, min(1.0, factor_disponibilidad))

        meta_base_ajustada = (
            (self.meta_base_taller or 60.0) * factor_disponibilidad
        )
        meta_total = min(pool, meta_base_ajustada)

        self.write({
            'factor_disponibilidad_taller': factor_disponibilidad,
            'meta_total_taller_ajustada': meta_total,
        })

        comandos = [(5, 0, 0)]

        for item in datos:
            perfil = item['perfil']
            participa = bool(
                perfil.tipo_operativo in ('taller', 'mixto')
                and item['horas_taller'] > 0
            )

            porcentaje = (
                item['horas_taller'] / capacidad_total * 100.0
                if participa and capacidad_total > 0
                else 0.0
            )

            meta = (
                meta_total * item['horas_taller'] / capacidad_total
                if participa and capacidad_total > 0
                else 0.0
            )

            produccion = self._get_produccion_tecnico(perfil.tecnico_id)
            cumplimiento = (
                produccion / meta * 100.0
                if meta > 0
                else 0.0
            )

            motivo = []

            if perfil.tipo_operativo == 'servicios':
                motivo.append(
                    'No participa en el pool de taller porque es técnico exclusivo de servicios.'
                )
            elif not participa:
                motivo.append(
                    'No tiene horas disponibles de taller en el periodo.'
                )
            else:
                motivo.append(
                    'Participa según sus horas reales disponibles de taller.'
                )

            if item['horas_ausencia']:
                motivo.append(
                    'Se descontaron %.2f horas por vacaciones, enfermedad, '
                    'descanso médico o capacitación.'
                    % item['horas_ausencia']
                )

            if item['horas_tickets']:
                motivo.append(
                    'Se descontaron %.2f horas por %s ticket(s) finalizado(s).'
                    % (item['horas_tickets'], item['tickets_count'])
                )

            if item['horas_descarga']:
                motivo.append(
                    'Se descontaron %.2f horas por participación en la '
                    'descarga de contenedores.'
                    % item['horas_descarga']
                )

            if participa:
                motivo.append(
                    'La meta individual se calculó sobre una meta total '
                    'ajustada de %.2f máquinas, proveniente de una meta base '
                    'gerencial de %.2f y limitada por un pool exigible de %s.'
                    % (meta_total, self.meta_base_taller, self.pool_total_exigible)
                )

            if item['tickets_sin_retorno']:
                motivo.append(
                    '%s ticket(s) fueron registrados sin retorno al taller.'
                    % item['tickets_sin_retorno']
                )

            comandos.append((0, 0, {
                'perfil_id': perfil.id,
                'tecnico_id': perfil.tecnico_id.id,
                'tipo_operativo': perfil.tipo_operativo,
                'participa_pool': participa,
                'horas_programadas': item['horas_programadas'],
                'horas_ausencia_reduce_meta': item['horas_ausencia'],
                'horas_tickets': item['horas_tickets'],
                'horas_descarga_contenedores': item['horas_descarga'],
                'tickets_finalizados': item['tickets_count'],
                'tickets_sin_retorno': item['tickets_sin_retorno'],
                'horas_taller_disponibles': item['horas_taller'],
                'porcentaje_participacion': porcentaje,
                'meta_asignada': meta,
                'produccion_finalizada': produccion,
                'porcentaje_cumplimiento': min(120.0, cumplimiento),
                'motivo_calculo': ' '.join(motivo),
            }))

        self.write({'tecnico_line_ids': comandos})

    # ============================================================
    # RESÚMENES
    # ============================================================

    @api.depends(
        'maquina_line_ids.incluida_pool',
        'maquina_line_ids.excluida',
        'maquina_line_ids.origen_pool',
        'maquina_line_ids.motivo_exclusion',
        'maquina_line_ids.finalizada_mes',
        'maquina_line_ids.pendiente_cierre',
        'tecnico_line_ids.horas_taller_disponibles',
        'descarga_contenedor_ids.cantidad_contenedores',
        'descarga_contenedor_ids.horas_totales',
        'descarga_contenedor_ids.tecnico_ids',
    )
    def _compute_resumen(self):
        for rec in self:
            lineas = rec.maquina_line_ids
            descargas = rec.descarga_contenedor_ids

            rec.contenedores_recibidos = sum(
                descargas.mapped('cantidad_contenedores')
            )
            rec.horas_descarga_contenedores = sum(
                descargas.mapped('horas_totales')
            )
            rec.horas_hombre_descarga_contenedores = sum(
                (descarga.horas_totales or 0.0) * len(descarga.tecnico_ids)
                for descarga in descargas
            )

            rec.maquinas_descargadas_mes = len(
                lineas.filtered(lambda line: line.origen_pool == 'ingreso_mes')
            )
            rec.maquinas_backlog_inicial = len(
                lineas.filtered(lambda line: line.origen_pool == 'backlog')
            )
            rec.maquinas_reactivadas = len(
                lineas.filtered(lambda line: line.origen_pool == 'reactivada')
            )
            rec.maquinas_excluidas = len(
                lineas.filtered('excluida')
            )
            rec.maquinas_entregadas_sin_revision = len(
                lineas.filtered(
                    lambda line: line.motivo_exclusion in (
                        'entregada_sin_reparacion',
                        'entregada_sin_finalizacion',
                    )
                )
            )
            rec.maquinas_finalizadas_mes = len(
                lineas.filtered('finalizada_mes')
            )
            rec.maquinas_pendientes_cierre = len(
                lineas.filtered('pendiente_cierre')
            )
            rec.pool_total_exigible = len(
                lineas.filtered('incluida_pool')
            )
            rec.capacidad_total_taller_horas = sum(
                rec.tecnico_line_ids.mapped('horas_taller_disponibles')
            )

    @api.depends(
        'state',
        'fecha_inicio',
        'fecha_fin',
        'pool_total_exigible',
        'meta_base_taller',
        'meta_total_taller_ajustada',
        'factor_disponibilidad_taller',
        'contenedores_recibidos',
        'horas_descarga_contenedores',
        'horas_hombre_descarga_contenedores',
        'maquinas_descargadas_mes',
        'maquinas_backlog_inicial',
        'maquinas_reactivadas',
        'maquinas_excluidas',
        'maquinas_entregadas_sin_revision',
        'maquinas_finalizadas_mes',
        'maquinas_pendientes_cierre',
        'capacidad_total_taller_horas',
        'tecnico_line_ids.tecnico_id',
        'tecnico_line_ids.tipo_operativo',
        'tecnico_line_ids.meta_asignada',
        'tecnico_line_ids.horas_descarga_contenedores',
        'tecnico_line_ids.produccion_finalizada',
        'tecnico_line_ids.porcentaje_cumplimiento',
        'tecnico_line_ids.motivo_calculo',
    )
    def _compute_resumen_gerencia(self):
        for rec in self:
            if not rec.fecha_inicio or not rec.fecha_fin:
                rec.resumen_gerencia = False
                continue

            filas = []

            for linea in rec.tecnico_line_ids.sorted(
                key=lambda line: line.tecnico_id.name or ''
            ):
                filas.append(
                    '<tr>'
                    '<td>%s</td>'
                    '<td>%s</td>'
                    '<td style="text-align:right;">%.2f</td>'
                    '<td style="text-align:right;">%.2f</td>'
                    '<td style="text-align:right;">%.2f</td>'
                    '<td style="text-align:right;">%s</td>'
                    '<td style="text-align:right;">%.2f%%</td>'
                    '<td>%s</td>'
                    '</tr>'
                    % (
                        linea.tecnico_id.name or '',
                        dict(
                            linea._fields['tipo_operativo'].selection
                        ).get(linea.tipo_operativo, ''),
                        linea.horas_taller_disponibles,
                        linea.horas_descarga_contenedores,
                        linea.meta_asignada,
                        linea.produccion_finalizada,
                        linea.porcentaje_cumplimiento,
                        linea.motivo_calculo or '',
                    )
                )

            rec.resumen_gerencia = (
                '<div>'
                '<h3>Resumen del cierre mensual</h3>'
                '<p><strong>Periodo:</strong> %s al %s</p>'
                '<p>'
                '<strong>Pool exigible:</strong> %s máquinas. '
                'Está compuesto por %s descargas del mes, %s máquinas de backlog '
                'y %s reactivaciones. Se excluyeron %s máquinas, de las cuales '
                '%s fueron entregadas sin una revisión finalizada registrada.'
                '</p>'
                '<p>'
                '<strong>Contenedores recibidos:</strong> %s. '
                'Las descargas ocuparon %.2f horas de operación y %.2f horas-hombre. '
                'Este tiempo se descuenta únicamente a los técnicos registrados '
                'como participantes, porque durante la descarga no pueden dedicarse '
                'a la revisión y reparación de máquinas.'
                '</p>'
                '<p>'
                '<strong>Meta gerencial:</strong> %.2f máquinas. '
                'La meta total ajustada fue %.2f máquinas, con un factor de '
                'disponibilidad de %.2f%%. La meta se limita al pool real para no '
                'exigir producción sobre máquinas que no estuvieron disponibles.'
                '</p>'
                '<p>'
                '<strong>Resultado:</strong> %s máquinas fueron finalizadas durante '
                'el mes y %s quedaron pendientes para el siguiente periodo.'
                '</p>'
                '<p>'
                '<strong>Capacidad total de taller:</strong> %.2f horas. '
                'La meta se reparte proporcionalmente entre técnicos de taller y '
                'mixtos según sus horas disponibles, después de descontar únicamente '
                'ausencias que reducen meta y tiempo dedicado a tickets.'
                '</p>'
                '<table class="table table-sm table-bordered">'
                '<thead><tr>'
                '<th>Técnico</th>'
                '<th>Perfil</th>'
                '<th>Horas taller</th>'
                '<th>Horas descarga</th>'
                '<th>Meta asignada</th>'
                '<th>Finalizadas</th>'
                '<th>Cumplimiento</th>'
                '<th>Explicación</th>'
                '</tr></thead>'
                '<tbody>%s</tbody>'
                '</table>'
                '</div>'
                % (
                    rec.fecha_inicio.strftime('%d/%m/%Y'),
                    rec.fecha_fin.strftime('%d/%m/%Y'),
                    rec.pool_total_exigible,
                    rec.maquinas_descargadas_mes,
                    rec.maquinas_backlog_inicial,
                    rec.maquinas_reactivadas,
                    rec.maquinas_excluidas,
                    rec.maquinas_entregadas_sin_revision,
                    rec.contenedores_recibidos,
                    rec.horas_descarga_contenedores,
                    rec.horas_hombre_descarga_contenedores,
                    rec.meta_base_taller,
                    rec.meta_total_taller_ajustada,
                    rec.factor_disponibilidad_taller * 100.0,
                    rec.maquinas_finalizadas_mes,
                    rec.maquinas_pendientes_cierre,
                    rec.capacidad_total_taller_horas,
                    ''.join(filas),
                )
            )

    # ============================================================
    # ACCIONES
    # ============================================================

    def action_calcular(self):
        for rec in self:
            if rec.state == 'confirmado':
                raise UserError(
                    _('No se puede recalcular un cierre confirmado.')
                )

            if not rec.fecha_inicio or not rec.fecha_fin:
                raise UserError(_('Debe definir correctamente el periodo.'))

            rec._calcular_lineas_maquinas()
            rec._calcular_lineas_tecnicos()

            rec.write({
                'state': 'calculado',
                'fecha_calculo': fields.Datetime.now(),
                'calculado_por_id': self.env.user.id,
            })

            rec.message_post(
                body=_(
                    'Cierre calculado. Pool exigible: %s máquinas. '
                    'Finalizadas: %s. Pendientes: %s. Meta ajustada: %.2f. '
                    'Contenedores recibidos: %s. Técnicos participantes: %s.'
                ) % (
                    rec.pool_total_exigible,
                    rec.maquinas_finalizadas_mes,
                    rec.maquinas_pendientes_cierre,
                    rec.meta_total_taller_ajustada,
                    rec.contenedores_recibidos,
                    len(rec.tecnico_line_ids.filtered('participa_pool')),
                )
            )

        return True

    def action_confirmar(self):
        for rec in self:
            if rec.state != 'calculado':
                raise UserError(
                    _('Primero debe calcular el cierre mensual.')
                )

            if not rec.tecnico_line_ids:
                raise UserError(
                    _('El cierre no tiene técnicos calculados.')
                )

            if rec.pool_total_exigible and not rec.tecnico_line_ids.filtered(
                'participa_pool'
            ):
                raise UserError(
                    _(
                        'Existe un pool exigible, pero ningún técnico tiene '
                        'capacidad disponible de taller.'
                    )
                )

            rec.write({
                'state': 'confirmado',
                'fecha_confirmacion': fields.Datetime.now(),
                'confirmado_por_id': self.env.user.id,
            })

            rec.message_post(
                body=_(
                    'Cierre mensual confirmado por %s. Los datos quedaron congelados.'
                ) % self.env.user.name
            )

        return True

    def action_volver_borrador(self):
        for rec in self:
            if rec.state == 'confirmado':
                raise UserError(
                    _(
                        'Un cierre confirmado no puede volver a borrador. '
                        'Debe mantenerse como evidencia del cálculo aprobado.'
                    )
                )

            rec.write({'state': 'borrador'})

        return True

    def action_cancelar(self):
        for rec in self:
            if rec.state == 'confirmado':
                raise UserError(
                    _('No se puede cancelar un cierre confirmado.')
                )

            rec.write({'state': 'cancelado'})

        return True


class EvaluacionCierreMensualDescarga(models.Model):
    _name = 'evaluacion.cierre.mensual.descarga'
    _description = 'Descarga de contenedor del cierre mensual'
    _order = 'fecha asc, id asc'

    cierre_id = fields.Many2one(
        'evaluacion.cierre.mensual',
        string='Cierre mensual',
        required=True,
        ondelete='cascade',
        index=True,
    )

    fecha = fields.Date(
        string='Fecha de descarga',
        required=True,
        default=fields.Date.context_today,
    )

    cantidad_contenedores = fields.Integer(
        string='Cantidad de contenedores',
        required=True,
        default=1,
        help='Cantidad de contenedores recibidos en esta descarga.',
    )

    horas_por_contenedor = fields.Float(
        string='Horas por contenedor',
        required=True,
        default=4.0,
        digits=(16, 2),
        help='Medio día equivale normalmente a 4 horas por contenedor.',
    )

    horas_totales = fields.Float(
        string='Duración total de descarga',
        compute='_compute_horas_totales',
        store=True,
        digits=(16, 2),
    )

    tecnico_ids = fields.Many2many(
        'res.users',
        'evaluacion_cierre_descarga_tecnico_rel',
        'descarga_id',
        'tecnico_id',
        string='Técnicos participantes',
        required=True,
        help=(
            'Solo estos técnicos recibirán el descuento de horas por la '
            'descarga del contenedor.'
        ),
    )

    observaciones = fields.Text(
        string='Observaciones',
    )

    @api.depends('cantidad_contenedores', 'horas_por_contenedor')
    def _compute_horas_totales(self):
        for rec in self:
            rec.horas_totales = max(
                0.0,
                float(rec.cantidad_contenedores or 0)
                * (rec.horas_por_contenedor or 0.0),
            )

    @api.constrains('fecha', 'cantidad_contenedores', 'horas_por_contenedor')
    def _check_datos_descarga(self):
        for rec in self:
            if rec.cantidad_contenedores <= 0:
                raise ValidationError(
                    _('La cantidad de contenedores debe ser mayor que cero.')
                )
            if rec.horas_por_contenedor <= 0:
                raise ValidationError(
                    _('Las horas por contenedor deben ser mayores que cero.')
                )
            if (
                rec.cierre_id
                and rec.fecha
                and not (
                    rec.cierre_id.fecha_inicio
                    <= rec.fecha
                    <= rec.cierre_id.fecha_fin
                )
            ):
                raise ValidationError(
                    _('La fecha de descarga debe pertenecer al periodo del cierre.')
                )


class EvaluacionCierreMensualMaquina(models.Model):
    _name = 'evaluacion.cierre.mensual.maquina'
    _description = 'Detalle de máquinas del cierre mensual'
    _order = 'ingreso_fecha asc, id asc'

    cierre_id = fields.Many2one(
        'evaluacion.cierre.mensual',
        string='Cierre mensual',
        required=True,
        ondelete='cascade',
        index=True,
    )

    maquina_id = fields.Many2one(
        'sat.sat',
        string='Máquina',
        required=True,
        readonly=True,
        index=True,
    )

    serie = fields.Char(
        string='Serie',
        related='maquina_id.serie_id',
        store=True,
        readonly=True,
    )

    modelo = fields.Char(
        string='Modelo',
        related='maquina_id.name.name',
        store=True,
        readonly=True,
    )

    ingreso_fecha = fields.Datetime(
        string='Fecha de descarga',
        readonly=True,
    )

    estado_cierre = fields.Selection([
        ('sin_revisar', 'Sin revisar'),
        ('para_revision', 'Para revisión'),
        ('en_revision', 'En revisión'),
        ('finalizado', 'Finalizado'),
        ('con_problemas', 'Con problemas'),
        ('de_partes', 'De partes'),
        ('entregada', 'Entregada'),
    ], string='Estado al calcular', readonly=True)

    origen_pool = fields.Selection([
        ('ingreso_mes', 'Descargada en el mes'),
        ('backlog', 'Backlog anterior'),
        ('reactivada', 'Reactivada'),
    ], string='Origen', readonly=True)

    incluida_pool = fields.Boolean(
        string='Incluida en el pool',
        readonly=True,
    )

    excluida = fields.Boolean(
        string='Excluida',
        readonly=True,
    )

    motivo_exclusion = fields.Selection([
        ('con_problemas', 'Con problemas'),
        ('de_partes', 'De partes'),
        ('entregada_sin_reparacion', 'Entregada sin reparación'),
        ('entregada_sin_finalizacion', 'Entregada sin finalización'),
        ('estado_no_exigible', 'Estado no exigible'),
    ], string='Motivo de exclusión', readonly=True)

    finalizada_mes = fields.Boolean(
        string='Finalizada en el mes',
        readonly=True,
    )

    pendiente_cierre = fields.Boolean(
        string='Pendiente al cierre',
        readonly=True,
    )

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones',
        string='Reparación finalizada',
        readonly=True,
    )

    tecnico_id = fields.Many2one(
        'res.users',
        string='Técnico responsable',
        readonly=True,
    )

    fecha_finalizacion = fields.Datetime(
        string='Fecha de finalización',
        readonly=True,
    )

    explicacion = fields.Char(
        string='Explicación',
        compute='_compute_explicacion',
        store=True,
    )

    @api.depends(
        'incluida_pool',
        'excluida',
        'motivo_exclusion',
        'finalizada_mes',
        'pendiente_cierre',
        'origen_pool',
    )
    def _compute_explicacion(self):
        motivos = dict(self._fields['motivo_exclusion'].selection)
        origenes = dict(self._fields['origen_pool'].selection)

        for rec in self:
            if rec.excluida:
                rec.explicacion = 'Excluida: %s.' % (
                    motivos.get(rec.motivo_exclusion, 'motivo no definido')
                )
            elif rec.finalizada_mes:
                rec.explicacion = (
                    'Incluida y contabilizada como producción del mes.'
                )
            elif rec.pendiente_cierre:
                rec.explicacion = (
                    'Incluida en el pool y pendiente para el siguiente periodo.'
                )
            else:
                rec.explicacion = 'Origen: %s.' % (
                    origenes.get(rec.origen_pool, 'no definido')
                )


class EvaluacionCierreMensualTecnico(models.Model):
    _name = 'evaluacion.cierre.mensual.tecnico'
    _description = 'Meta técnica del cierre mensual'
    _order = 'tecnico_id asc'

    cierre_id = fields.Many2one(
        'evaluacion.cierre.mensual',
        string='Cierre mensual',
        required=True,
        ondelete='cascade',
        index=True,
    )

    perfil_id = fields.Many2one(
        'mantenimiento.tecnico.perfil',
        string='Perfil operativo',
        required=True,
        readonly=True,
    )

    tecnico_id = fields.Many2one(
        'res.users',
        string='Técnico',
        required=True,
        readonly=True,
        index=True,
    )

    tipo_operativo = fields.Selection([
        ('taller', 'Técnico fijo de taller'),
        ('servicios', 'Técnico exclusivo de servicios / alquiler'),
        ('mixto', 'Técnico mixto / servicios eventuales'),
    ], string='Tipo operativo', readonly=True)

    participa_pool = fields.Boolean(
        string='Participa en el pool',
        readonly=True,
    )

    horas_programadas = fields.Float(
        string='Horas programadas',
        readonly=True,
        digits=(16, 2),
    )

    horas_ausencia_reduce_meta = fields.Float(
        string='Horas descontadas por ausencias',
        readonly=True,
        digits=(16, 2),
    )

    horas_tickets = fields.Float(
        string='Horas en tickets',
        readonly=True,
        digits=(16, 2),
    )

    horas_descarga_contenedores = fields.Float(
        string='Horas en descarga de contenedores',
        readonly=True,
        digits=(16, 2),
        help=(
            'Horas descontadas por participación del técnico en descargas '
            'de contenedores durante el periodo.'
        ),
    )

    tickets_finalizados = fields.Integer(
        string='Tickets finalizados',
        readonly=True,
    )

    tickets_sin_retorno = fields.Integer(
        string='Tickets sin retorno',
        readonly=True,
    )

    horas_taller_disponibles = fields.Float(
        string='Horas disponibles de taller',
        readonly=True,
        digits=(16, 2),
    )

    porcentaje_participacion = fields.Float(
        string='% participación',
        readonly=True,
        digits=(16, 2),
    )

    meta_asignada = fields.Float(
        string='Meta asignada',
        readonly=True,
        digits=(16, 2),
    )

    produccion_finalizada = fields.Integer(
        string='Producción finalizada',
        readonly=True,
    )

    porcentaje_cumplimiento = fields.Float(
        string='% cumplimiento',
        readonly=True,
        digits=(16, 2),
    )

    motivo_calculo = fields.Text(
        string='Explicación para gerencia',
        readonly=True,
    )

    _sql_constraints = [
        (
            'evaluacion_cierre_tecnico_unique',
            'unique(cierre_id, tecnico_id)',
            'El técnico ya fue incluido en este cierre mensual.....',
        ),
    ]
