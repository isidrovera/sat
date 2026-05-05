# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import timedelta
from odoo.exceptions import UserError


class AlquilerMantenimientoPlanificador(models.Model):
    _inherit = 'alquiler'

    # ============================================================
    # CAMPOS DE PLANIFICACIÓN INTELIGENTE
    # ============================================================

    zona_mantenimiento_id = fields.Many2one(
        'mantenimiento.zona',
        string='Zona de mantenimiento',
        tracking=True,
        help='Zona operativa asignada para planificar mantenimientos.'
    )

    tecnico_mantenimiento_id = fields.Many2one(
        'res.users',
        string='Técnico de mantenimiento',
        tracking=True,
        domain=[('share', '=', False)],
        help='Técnico asignado o preferido para el mantenimiento de esta máquina.'
    )

    fecha_programada_mantenimiento = fields.Date(
        string='Fecha programada de mantenimiento',
        tracking=True,
        help='Fecha real asignada por el planificador. Puede ser diferente a la fecha recurrente ideal.'
    )

    hora_programada_mantenimiento = fields.Float(
        string='Hora programada',
        tracking=True,
        help='Hora real asignada por el planificador. Ejemplo: 14.0 = 2:00 pm.'
    )

    duracion_mantenimiento_horas = fields.Float(
        string='Duración estimada mantenimiento',
        default=2.0,
        tracking=True,
        help='Duración estimada del mantenimiento preventivo.'
    )

    cantidad_tecnicos_mantenimiento = fields.Integer(
        string='Técnicos requeridos',
        default=1,
        tracking=True,
        help='Cantidad de técnicos requeridos para este mantenimiento.'
    )

    ignorar_zona_mantenimiento = fields.Boolean(
        string='Ignorar zona al asignar',
        default=False,
        tracking=True,
        help='Permite asignar cualquier técnico disponible sin filtrar por zona.'
    )

    planificador_linea_ids = fields.One2many(
        'mantenimiento.planificador.linea',
        'equipo_id',
        string='Líneas de planificación',
        readonly=True
    )

    planificador_linea_count = fields.Integer(
        string='Planificaciones',
        compute='_compute_planificador_linea_count',
        store=False
    )

    ultima_linea_planificador_id = fields.Many2one(
        'mantenimiento.planificador.linea',
        string='Última planificación',
        compute='_compute_ultima_linea_planificador',
        store=False
    )

    estado_planificacion_mantenimiento = fields.Selection([
        ('sin_planificar', 'Sin planificar'),
        ('pendiente', 'Pendiente'),
        ('confirmado', 'Confirmado sin asignar'),
        ('programado', 'Programado'),
        ('sin_cupo', 'Sin cupo'),
        ('reasignar', 'Requiere reasignación'),
        ('ticket_creado', 'Ticket creado'),
    ], string='Estado planificación',
        compute='_compute_estado_planificacion_mantenimiento',
        store=False
    )

    dias_disponibles_mantenimiento = fields.Html(
        string='Disponibilidad sugerida',
        compute='_compute_dias_disponibles_mantenimiento',
        sanitize=False
    )

    # ============================================================
    # COMPUTES
    # ============================================================

    @api.depends('planificador_linea_ids')
    def _compute_planificador_linea_count(self):
        for rec in self:
            rec.planificador_linea_count = len(rec.planificador_linea_ids)

    @api.depends('planificador_linea_ids', 'planificador_linea_ids.create_date')
    def _compute_ultima_linea_planificador(self):
        for rec in self:
            linea = rec.planificador_linea_ids.sorted(
                lambda l: l.create_date or fields.Datetime.now(),
                reverse=True
            )[:1]
            rec.ultima_linea_planificador_id = linea.id if linea else False

    @api.depends(
        'ultima_linea_planificador_id',
        'ultima_linea_planificador_id.estado'
    )
    def _compute_estado_planificacion_mantenimiento(self):
        for rec in self:
            if rec.ultima_linea_planificador_id:
                rec.estado_planificacion_mantenimiento = rec.ultima_linea_planificador_id.estado
            else:
                rec.estado_planificacion_mantenimiento = 'sin_planificar'

    @api.depends(
        'fecha_recurrente',
        'zona_mantenimiento_id',
        'duracion_mantenimiento_horas',
        'cantidad_tecnicos_mantenimiento',
        'ignorar_zona_mantenimiento'
    )
    def _compute_dias_disponibles_mantenimiento(self):
        Planificador = self.env['mantenimiento.planificador']

        for rec in self:
            if not rec.fecha_recurrente:
                rec.dias_disponibles_mantenimiento = """
                    <div style="color:#6b7280;">
                        No hay fecha recurrente calculada.
                    </div>
                """
                continue

            # Buscar planificador activo que contenga la fecha recurrente
            plan = Planificador.search([
                ('fecha_inicio', '<=', rec.fecha_recurrente),
                ('fecha_fin', '>=', rec.fecha_recurrente),
                ('estado', 'in', ['borrador', 'generado', 'en_proceso']),
            ], order='fecha_inicio desc, id desc', limit=1)

            if not plan:
                rec.dias_disponibles_mantenimiento = """
                    <div style="color:#92400e;background:#fef3c7;
                                border:1px solid #fde68a;border-radius:10px;
                                padding:10px;">
                        No existe un planificador activo para esta fecha.
                    </div>
                """
                continue

            zona = rec.zona_mantenimiento_id
            if not zona and rec.distrito:
                zona = plan._get_zona_por_distrito(rec.distrito)

            sugerencias = []
            fecha_base = rec.fecha_recurrente

            for offset in range(0, 10):
                fecha = fecha_base + fields.Date.to_date('1970-01-01').__class__.resolution * 0
                fecha = fecha_base
                break

            # Búsqueda simple de próximos 10 días usando helper del planificador
            fecha_actual = fecha_base
            encontrados = 0
            intentos = 0

            while encontrados < 5 and intentos < 15:
                slot = plan._buscar_horario_disponible(
                    fecha=fecha_actual,
                    zona=zona,
                    cantidad_tecnicos=rec.cantidad_tecnicos_mantenimiento or 1,
                    duracion_horas=rec.duracion_mantenimiento_horas or 2.0,
                    hora_preferida=False,
                    ignorar_zona=rec.ignorar_zona_mantenimiento,
                )

                if slot:
                    tecnicos = ', '.join([
                        item['tecnico'].name for item in slot.get('tecnicos', [])
                    ])
                    sugerencias.append("""
                        <div style="background:#f0fdf4;border:1px solid #bbf7d0;
                                    border-radius:10px;padding:10px;margin-bottom:8px;">
                            <strong>%s</strong><br/>
                            <span>Horario: %.2f - %.2f</span><br/>
                            <span>Técnicos: %s</span>
                        </div>
                    """ % (
                        fecha_actual.strftime('%d/%m/%Y'),
                        slot.get('hora_inicio'),
                        slot.get('hora_fin'),
                        tecnicos or 'Sin técnico',
                    ))
                    encontrados += 1

                fecha_actual = fecha_actual + timedelta(days=1)
                intentos += 1

            if sugerencias:
                rec.dias_disponibles_mantenimiento = ''.join(sugerencias)
            else:
                rec.dias_disponibles_mantenimiento = """
                    <div style="color:#991b1b;background:#fef2f2;
                                border:1px solid #fecaca;border-radius:10px;
                                padding:10px;">
                        No se encontraron cupos disponibles próximos.
                    </div>
                """

    # ============================================================
    # ONCHANGE
    # ============================================================

    @api.onchange('distrito')
    def _onchange_distrito_detectar_zona(self):
        for rec in self:
            if not rec.distrito:
                continue

            zona = rec._buscar_zona_por_distrito_local(rec.distrito)
            if zona:
                rec.zona_mantenimiento_id = zona.id

    @api.onchange('zona_mantenimiento_id')
    def _onchange_zona_mantenimiento_id(self):
        for rec in self:
            if rec.zona_mantenimiento_id and rec.zona_mantenimiento_id.tecnico_ids:
                if not rec.tecnico_mantenimiento_id:
                    rec.tecnico_mantenimiento_id = rec.zona_mantenimiento_id.tecnico_ids[0].id

    # ============================================================
    # HELPERS
    # ============================================================

    def _buscar_zona_por_distrito_local(self, distrito):
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
            alias_list = [
                a.strip().lower()
                for a in (item.alias or '').split(',')
                if a.strip()
            ]

            if distrito_lower in alias_list:
                return item.zona_id

        return False

    def _preparar_valores_linea_planificador(self, planificador):
        self.ensure_one()

        zona = self.zona_mantenimiento_id
        if not zona and self.distrito:
            zona = planificador._get_zona_por_distrito(self.distrito)

        return {
            'planificador_id': planificador.id,
            'equipo_id': self.id,
            'cliente_id': self.cliente_id.id if self.cliente_id else False,
            'distrito': self.distrito,
            'zona_id': zona.id if zona else False,
            'fecha_ideal': self.fecha_recurrente,
            'estado': 'pendiente',
            'cantidad_tecnicos': self.cantidad_tecnicos_mantenimiento or 1,
            'duracion_horas': self.duracion_mantenimiento_horas or 2.0,
            'ignorar_zona': self.ignorar_zona_mantenimiento,
        }

    # ============================================================
    # ACCIONES
    # ============================================================

    def action_detectar_zona_mantenimiento(self):
        for rec in self:
            if not rec.distrito:
                raise UserError(
                    _("La máquina %s no tiene distrito definido.")
                    % (rec.serie or rec.display_name)
                )

            zona = rec._buscar_zona_por_distrito_local(rec.distrito)

            if not zona:
                raise UserError(
                    _("No se encontró zona configurada para el distrito '%s'.")
                    % rec.distrito
                )

            rec.write({
                'zona_mantenimiento_id': zona.id,
            })

            rec.message_post(
                body=_(
                    "📍 Zona de mantenimiento detectada automáticamente: %s"
                ) % zona.name,
                message_type='notification'
            )

        return True

    def action_crear_linea_planificador_activo(self):
        Planificador = self.env['mantenimiento.planificador']
        Linea = self.env['mantenimiento.planificador.linea']

        for rec in self:
            if not rec.control_mantenimiento:
                raise UserError(
                    _("La máquina %s no tiene mantenimiento mensual activo.")
                    % (rec.serie or rec.display_name)
                )

            if not rec.fecha_recurrente:
                raise UserError(
                    _("La máquina %s no tiene fecha recurrente calculada.")
                    % (rec.serie or rec.display_name)
                )

            plan = Planificador.search([
                ('fecha_inicio', '<=', rec.fecha_recurrente),
                ('fecha_fin', '>=', rec.fecha_recurrente),
                ('estado', 'in', ['borrador', 'generado', 'en_proceso']),
            ], order='fecha_inicio desc, id desc', limit=1)

            if not plan:
                raise UserError(
                    _("No existe un planificador activo para la fecha %s.")
                    % rec.fecha_recurrente.strftime('%d/%m/%Y')
                )

            existente = Linea.search([
                ('planificador_id', '=', plan.id),
                ('equipo_id', '=', rec.id),
                ('estado', '!=', 'cancelado'),
            ], limit=1)

            if existente:
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Línea de planificación'),
                    'res_model': 'mantenimiento.planificador.linea',
                    'res_id': existente.id,
                    'view_mode': 'form',
                    'target': 'current',
                }

            linea = Linea.create(
                rec._preparar_valores_linea_planificador(plan)
            )

            return {
                'type': 'ir.actions.act_window',
                'name': _('Línea de planificación'),
                'res_model': 'mantenimiento.planificador.linea',
                'res_id': linea.id,
                'view_mode': 'form',
                'target': 'current',
            }

        return True

    def action_auto_programar_mantenimiento(self):
        for rec in self:
            action = rec.action_crear_linea_planificador_activo()

            if isinstance(action, dict) and action.get('res_id'):
                linea = self.env['mantenimiento.planificador.linea'].browse(action['res_id'])
                linea.action_buscar_y_asignar_slot()
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Mantenimiento programado'),
                    'res_model': 'mantenimiento.planificador.linea',
                    'res_id': linea.id,
                    'view_mode': 'form',
                    'target': 'current',
                }

        return True

    def action_ver_planificaciones_mantenimiento(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Planificaciones de mantenimiento'),
            'res_model': 'mantenimiento.planificador.linea',
            'view_mode': 'list,form,calendar',
            'domain': [('equipo_id', '=', self.id)],
            'context': {
                'default_equipo_id': self.id,
                'default_cliente_id': self.cliente_id.id if self.cliente_id else False,
                'default_distrito': self.distrito,
                'default_zona_id': self.zona_mantenimiento_id.id if self.zona_mantenimiento_id else False,
            }
        }