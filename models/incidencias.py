# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, date
import logging

_logger = logging.getLogger(__name__)


class Incidencia(models.Model):
    _name = 'taller.incidencia'
    _description = 'Registro de Incidencias en el Taller'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_hora desc, id desc'

    # ============================================================
    # DATOS GENERALES
    # ============================================================

    name = fields.Char(
        string='ID de Incidencia',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New'),
        tracking=True
    )

    active = fields.Boolean(
        string='Activo',
        default=True
    )

    fecha_hora = fields.Datetime(
        string='Fecha y Hora del Reclamo',
        default=fields.Datetime.now,
        required=True,
        tracking=True
    )

    tipo = fields.Selection([
        ('reclamo', 'Reclamo'),
        ('reparacion', 'Reparación'),
        ('mantenimiento', 'Mantenimiento'),
    ], string='Tipo de Incidencia', default='reclamo', required=True, tracking=True)

    prioridad = fields.Selection([
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
        ('critica', 'Crítica'),
    ], string='Prioridad', default='baja', tracking=True)

    descripcion = fields.Text(
        string='Descripción del Reclamo',
        tracking=True
    )

    comentarios_cliente = fields.Text(
        string='Comentarios del Cliente',
        tracking=True
    )

    # ============================================================
    # EQUIPO / CLIENTE / ASESORA
    # ============================================================

    equipo_id = fields.Many2one(
        'sat.sat',
        string='Serie / Equipo Afectado',
        required=True,
        tracking=True,
        help='Seleccionar la máquina afectada. Al seleccionar el equipo se cargará automáticamente cliente, asesora, reparación y técnico.'
    )

    serie = fields.Char(
        string='Serie',
        related='equipo_id.serie_id',
        store=True,
        readonly=True,
        tracking=True
    )

    modelo_equipo = fields.Char(
        string='Modelo',
        compute='_compute_datos_equipo',
        store=True
    )

    marca = fields.Char(
        string='Marca',
        related='equipo_id.marca',
        store=True,
        readonly=True
    )

    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente Relacionado',
        tracking=True
    )

    asesora_nombre = fields.Char(
        string='Asesora',
        related='equipo_id.asesora_id',
        store=True,
        readonly=True,
        tracking=True
    )

    factura_venta = fields.Char(
        string='Factura de Venta',
        related='equipo_id.factura_venta',
        store=True,
        readonly=True
    )

    fecha_entrega = fields.Date(
        string='Fecha de Entrega',
        tracking=True,
        help='Fecha de entrega de la máquina. Desde esta fecha se calculan los 10 días permitidos para reclamo que puede afectar al técnico.'
    )

    # ============================================================
    # REPARACIÓN RELACIONADA
    # ============================================================

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones',
        string='Reparación Relacionada',
        tracking=True,
        help='Última reparación relacionada a la máquina seleccionada.'
    )

    tecnico_id = fields.Many2one(
        'res.users',
        string='Técnico Responsable',
        tracking=True,
        help='Usuario técnico responsable, cuando la reparación usa res.users.'
    )

    tecnico_empleado_id = fields.Many2one(
        'hr.employee',
        string='Técnico Empleado',
        tracking=True,
        help='Empleado técnico responsable, cuando la reparación usa hr.employee.'
    )

    tecnico_nombre = fields.Char(
        string='Nombre del Técnico',
        tracking=True,
        readonly=True
    )

    empleado_id = fields.Many2one(
        'hr.employee',
        string='Empleado Asignado',
        tracking=True,
        help='Responsable operativo para seguimiento de la incidencia.'
    )

    fecha_finalizacion_reparacion = fields.Datetime(
        string='Fecha Finalización Reparación',
        readonly=True,
        tracking=True
    )

    estado_reparacion = fields.Char(
        string='Estado Reparación',
        readonly=True
    )

    calidad_reparacion = fields.Char(
        string='Calidad Reparación',
        readonly=True
    )

    informe_tecnico = fields.Html(
        string='Informe Técnico Relacionado',
        readonly=True,
        sanitize=False
    )

    observaciones_reparacion = fields.Html(
        string='Observaciones de Reparación',
        readonly=True,
        sanitize=False
    )

    # ============================================================
    # PLAZO
    # ============================================================

    plazo_maximo_dias = fields.Integer(
        string='Plazo Máximo de Reclamo',
        default=10,
        required=True,
        tracking=True,
        help='Cantidad máxima de días después de la entrega para que un reclamo pueda afectar al técnico.'
    )

    dias_desde_entrega = fields.Integer(
        string='Días desde Entrega',
        compute='_compute_plazo',
        store=True
    )

    dentro_plazo = fields.Boolean(
        string='Dentro de Plazo',
        compute='_compute_plazo',
        store=True,
        tracking=True
    )

    fecha_limite_reclamo = fields.Date(
        string='Fecha Límite de Reclamo',
        compute='_compute_plazo',
        store=True
    )

    # ============================================================
    # CLASIFICACIÓN DEL RECLAMO
    # ============================================================

    tipo_reclamo = fields.Selection([
        ('misma_falla', 'Misma falla después de reparación'),
        ('falla_diferente', 'Falla diferente'),
        ('equipo_no_probado', 'Equipo no probado correctamente'),
        ('falta_informe', 'Falta de informe técnico'),
        ('demora_sin_aviso', 'Demora sin aviso'),
        ('suministro_no_entregado', 'Suministro / tóner no entregado'),
        ('botellas_toner_no_entregadas', 'Botellas de tóner no entregadas'),
        ('accesorio_no_entregado', 'Accesorio no entregado'),
        ('error_informacion_cliente', 'Error de información al cliente'),
        ('danio_traslado', 'Daño en traslado'),
        ('mala_manipulacion_cliente', 'Mala manipulación del cliente'),
        ('otro', 'Otro'),
    ], string='Tipo de Reclamo', tracking=True)

    responsable_determinado = fields.Selection([
        ('pendiente', 'Pendiente de Determinar'),
        ('tecnico', 'Técnico'),
        ('asesora', 'Asesora'),
        ('almacen', 'Almacén'),
        ('despacho', 'Despacho / Transporte'),
        ('cliente', 'Cliente'),
        ('comercial', 'Comercial'),
        ('gerencia', 'Gerencia'),
        ('no_aplica', 'No Aplica'),
    ], string='Responsable Determinado', default='pendiente', tracking=True)

    procede = fields.Selection([
        ('pendiente', 'Pendiente de Revisión'),
        ('si', 'Procede'),
        ('no', 'No Procede'),
    ], string='Resultado de Revisión', default='pendiente', tracking=True)

    afecta_tecnico = fields.Boolean(
        string='Afecta al Técnico',
        compute='_compute_afecta_tecnico',
        store=True,
        tracking=True
    )

    motivo_no_afecta = fields.Html(
        string='Motivo por el que no afecta al Técnico',
        tracking=True,
        sanitize=False
    )

    observacion_validacion = fields.Html(
        string='Observación de Validación',
        tracking=True,
        sanitize=False
    )

    acciones = fields.Html(
        string='Acciones Tomadas',
        tracking=True,
        sanitize=False
    )

    # ============================================================
    # ESTADOS
    # ============================================================

    estado = fields.Selection([
        ('reportado', 'Reportado'),
        ('en_revision', 'En Revisión Técnica'),
        ('fuera_plazo', 'Fuera de Plazo'),
        ('gerencia', 'En Análisis de Gerencia'),
        ('procede', 'Procede'),
        ('no_procede', 'No Procede'),
        ('corregido', 'Corregido'),
        ('cerrado', 'Cerrado'),
    ], string='Estado de la Incidencia', default='reportado', tracking=True)

    revisado_por_id = fields.Many2one(
        'res.users',
        string='Revisado Por',
        tracking=True
    )

    fecha_revision = fields.Datetime(
        string='Fecha de Revisión',
        tracking=True
    )

    fecha_resolucion = fields.Datetime(
        string='Fecha de Resolución',
        tracking=True
    )

    cerrado_por_id = fields.Many2one(
        'res.users',
        string='Cerrado Por',
        tracking=True
    )

    # ============================================================
    # INDICADORES VISUALES
    # ============================================================

    color = fields.Integer(
        string='Color',
        compute='_compute_indicadores',
        store=True
    )

    alerta_nivel = fields.Selection([
        ('info', 'Informativo'),
        ('ok', 'Correcto'),
        ('warning', 'Advertencia'),
        ('danger', 'Crítico'),
    ], string='Nivel de Alerta', compute='_compute_indicadores', store=True)

    alerta_titulo = fields.Char(
        string='Título de Alerta',
        compute='_compute_indicadores',
        store=True
    )

    alerta_resumen = fields.Html(
        string='Resumen de Alerta',
        compute='_compute_indicadores',
        store=True,
        sanitize=False
    )

    indicador_plazo = fields.Selection([
        ('sin_fecha', 'Sin Fecha de Entrega'),
        ('dentro', 'Dentro de Plazo'),
        ('fuera', 'Fuera de Plazo'),
    ], string='Indicador de Plazo', compute='_compute_indicadores', store=True)

    indicador_impacto = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('afecta_tecnico', 'Afecta Técnico'),
        ('no_afecta_tecnico', 'No Afecta Técnico'),
        ('gerencia', 'Gerencia'),
    ], string='Indicador de Impacto', compute='_compute_indicadores', store=True)

    semaforo = fields.Char(
        string='Semáforo',
        compute='_compute_indicadores',
        store=True
    )

    resumen_estado = fields.Char(
        string='Resumen Estado',
        compute='_compute_indicadores',
        store=True
    )

    # ============================================================
    # EVIDENCIAS Y COSTOS
    # ============================================================

    evidencia_ids = fields.Many2many(
        'ir.attachment',
        'taller_incidencia_ir_attachment_rel',
        'incidencia_id',
        'attachment_id',
        string='Evidencias'
    )

    costos = fields.Float(
        string='Costos Asociados',
        tracking=True
    )

    # ============================================================
    # CORREOS / PLANTILLAS XML
    # ============================================================

    email_creacion_enviado = fields.Boolean(
        string='Correo de Creación Enviado',
        default=False,
        copy=False,
        tracking=True
    )

    email_revision_enviado = fields.Boolean(
        string='Correo de Revisión Enviado',
        default=False,
        copy=False,
        tracking=True
    )

    email_procede_enviado = fields.Boolean(
        string='Correo Procede Enviado',
        default=False,
        copy=False,
        tracking=True
    )

    email_no_procede_enviado = fields.Boolean(
        string='Correo No Procede Enviado',
        default=False,
        copy=False,
        tracking=True
    )

    email_gerencia_enviado = fields.Boolean(
        string='Correo Gerencia Enviado',
        default=False,
        copy=False,
        tracking=True
    )

    email_cierre_enviado = fields.Boolean(
        string='Correo Cierre Enviado',
        default=False,
        copy=False,
        tracking=True
    )

    ultimo_correo_fecha = fields.Datetime(
        string='Último Correo Enviado',
        readonly=True,
        copy=False
    )

    ultimo_correo_template = fields.Char(
        string='Última Plantilla Enviada',
        readonly=True,
        copy=False
    )

    correo_error = fields.Text(
        string='Error de Correo',
        readonly=True,
        copy=False
    )

    # ============================================================
    # INTEGRACIÓN FUTURA CON EVALUACIÓN
    # ============================================================

    aplica_evaluacion = fields.Boolean(
        string='Aplica a Evaluación',
        compute='_compute_aplica_evaluacion',
        store=True,
        tracking=True,
        help='Se activa cuando la incidencia debe ser considerada en la evaluación del técnico.'
    )

    evaluacion_periodo = fields.Char(
        string='Periodo Evaluación',
        compute='_compute_aplica_evaluacion',
        store=True
    )

    # ============================================================
    # COMPUTES
    # ============================================================

    @api.depends('equipo_id', 'equipo_id.name')
    def _compute_datos_equipo(self):
        for record in self:
            record.modelo_equipo = ''
            if record.equipo_id and record.equipo_id.name:
                record.modelo_equipo = record.equipo_id.name.name or record.equipo_id.name.display_name

    @api.depends('fecha_entrega', 'fecha_hora', 'plazo_maximo_dias')
    def _compute_plazo(self):
        for record in self:
            record.dias_desde_entrega = 0
            record.dentro_plazo = False
            record.fecha_limite_reclamo = False

            if not record.fecha_entrega:
                continue

            fecha_entrega = record._to_date(record.fecha_entrega)
            fecha_reclamo = record._to_date(record.fecha_hora or fields.Datetime.now())

            if fecha_entrega:
                record.fecha_limite_reclamo = fields.Date.add(
                    fecha_entrega,
                    days=record.plazo_maximo_dias or 10
                )

            if fecha_reclamo and fecha_entrega:
                dias = (fecha_reclamo - fecha_entrega).days
                record.dias_desde_entrega = dias
                record.dentro_plazo = dias <= (record.plazo_maximo_dias or 10)

    @api.depends('tipo', 'dentro_plazo', 'procede', 'responsable_determinado', 'estado')
    def _compute_afecta_tecnico(self):
        for record in self:
            record.afecta_tecnico = (
                record.tipo == 'reclamo'
                and record.dentro_plazo
                and record.procede == 'si'
                and record.responsable_determinado == 'tecnico'
                and record.estado in ['procede', 'corregido']
            )

    @api.depends(
        'estado',
        'dentro_plazo',
        'fecha_entrega',
        'afecta_tecnico',
        'procede',
        'responsable_determinado',
        'tipo_reclamo',
        'dias_desde_entrega'
    )
    def _compute_indicadores(self):
        for record in self:
            color = 0
            alerta_nivel = 'info'
            alerta_titulo = 'Incidencia registrada'
            indicador_plazo = 'sin_fecha'
            indicador_impacto = 'pendiente'
            semaforo = '⚪'
            resumen_estado = 'Pendiente de revisión'
            resumen = []

            if not record.fecha_entrega:
                color = 4
                alerta_nivel = 'warning'
                alerta_titulo = 'Sin fecha de entrega'
                indicador_plazo = 'sin_fecha'
                semaforo = '🟡'
                resumen_estado = 'No se puede calcular plazo'
                resumen.append('No se encontró fecha de entrega. Complete o valide la información antes de definir si afecta al técnico.')

            elif record.dentro_plazo:
                color = 3
                alerta_nivel = 'info'
                alerta_titulo = 'Dentro de plazo'
                indicador_plazo = 'dentro'
                semaforo = '🔵'
                resumen_estado = 'Puede pasar a revisión técnica'
                resumen.append('El reclamo está dentro del plazo permitido de 10 días desde la entrega.')

            else:
                color = 4
                alerta_nivel = 'warning'
                alerta_titulo = 'Fuera de plazo'
                indicador_plazo = 'fuera'
                indicador_impacto = 'gerencia'
                semaforo = '🟡'
                resumen_estado = 'Gerencia analiza / no afecta técnico'
                resumen.append('El reclamo está fuera del plazo de 10 días. Se registra para análisis de gerencia y no afecta al técnico.')

            if record.estado == 'procede' and record.afecta_tecnico:
                color = 1
                alerta_nivel = 'danger'
                alerta_titulo = 'Procede y afecta al técnico'
                indicador_impacto = 'afecta_tecnico'
                semaforo = '🔴'
                resumen_estado = 'Impacta evaluación técnica'
                resumen.append('La incidencia procede, está dentro del plazo y la responsabilidad fue determinada como técnica.')

            elif record.estado in ['procede', 'corregido'] and not record.afecta_tecnico:
                color = 10
                alerta_nivel = 'ok'
                alerta_titulo = 'Procede pero no afecta técnico'
                indicador_impacto = 'no_afecta_tecnico'
                semaforo = '🟢'
                resumen_estado = 'No impacta al técnico'
                resumen.append('La incidencia procede, pero la responsabilidad no corresponde al técnico.')

            elif record.estado == 'no_procede':
                color = 10
                alerta_nivel = 'ok'
                alerta_titulo = 'No procede'
                indicador_impacto = 'no_afecta_tecnico'
                semaforo = '🟢'
                resumen_estado = 'No afecta al técnico'
                resumen.append('El reclamo fue revisado y no procede técnicamente.')

            elif record.estado == 'gerencia':
                color = 4
                alerta_nivel = 'warning'
                alerta_titulo = 'En análisis de gerencia'
                indicador_impacto = 'gerencia'
                semaforo = '🟡'
                resumen_estado = 'Gerencia evalúa'
                resumen.append('El caso está en análisis de gerencia. No afecta al técnico mientras no exista validación formal.')

            elif record.estado == 'cerrado':
                color = 2
                alerta_nivel = 'ok'
                alerta_titulo = 'Incidencia cerrada'
                semaforo = '✅'
                resumen_estado = 'Cerrado'

            if record.tipo_reclamo in [
                'suministro_no_entregado',
                'botellas_toner_no_entregadas',
                'accesorio_no_entregado',
            ]:
                resumen.append('El tipo de reclamo corresponde a suministros, tóner o accesorios. Validar contra informe técnico y proceso de asesora/almacén/despacho.')

            record.color = color
            record.alerta_nivel = alerta_nivel
            record.alerta_titulo = alerta_titulo
            record.indicador_plazo = indicador_plazo
            record.indicador_impacto = indicador_impacto
            record.semaforo = semaforo
            record.resumen_estado = resumen_estado
            record.alerta_resumen = '<br/>'.join(resumen) if resumen else ''

    @api.depends('afecta_tecnico', 'fecha_revision', 'fecha_hora')
    def _compute_aplica_evaluacion(self):
        for record in self:
            record.aplica_evaluacion = bool(record.afecta_tecnico)

            fecha_base = record.fecha_revision or record.fecha_hora
            if fecha_base:
                fecha = record._to_date(fecha_base)
                record.evaluacion_periodo = fecha.strftime('%Y-%m') if fecha else False
            else:
                record.evaluacion_periodo = False

    # ============================================================
    # ONCHANGE
    # ============================================================

    @api.onchange('equipo_id')
    def _onchange_equipo_id(self):
        for record in self:
            if not record.equipo_id:
                continue

            record._cargar_datos_desde_equipo()
            record._actualizar_estado_por_plazo()

            return record._get_warning_onchange_equipo()

    @api.onchange('fecha_entrega', 'fecha_hora', 'plazo_maximo_dias')
    def _onchange_plazo(self):
        for record in self:
            if record.tipo == 'reclamo':
                record._actualizar_estado_por_plazo()
                return record._get_warning_plazo()

    @api.onchange('tipo_reclamo')
    def _onchange_tipo_reclamo(self):
        for record in self:
            if record.tipo_reclamo in [
                'suministro_no_entregado',
                'botellas_toner_no_entregadas',
                'accesorio_no_entregado',
            ]:
                if record.responsable_determinado in [False, 'pendiente']:
                    record.responsable_determinado = 'asesora'

                record.motivo_no_afecta = (
                    '<p>El reclamo corresponde a suministros, botellas de tóner o accesorios no entregados.</p>'
                    '<p>Debe validarse contra el informe técnico y el proceso de asesora, almacén o despacho.</p>'
                    '<p>No afecta al técnico salvo que la revisión determine responsabilidad técnica directa.</p>'
                )

                return {
                    'warning': {
                        'title': _('Reclamo normalmente no técnico'),
                        'message': _(
                            'Este reclamo normalmente corresponde a asesora, almacén o despacho. '
                            'Validar si el informe técnico ya indicaba la falta de tóner, botellas o accesorios.'
                        ),
                    }
                }

    # ============================================================
    # VALIDACIONES
    # ============================================================

    @api.constrains('tipo', 'equipo_id')
    def _check_equipo_obligatorio(self):
        for record in self:
            if record.tipo == 'reclamo' and not record.equipo_id:
                raise ValidationError(
                    _('Para registrar un reclamo es obligatorio seleccionar la serie/equipo afectado.')
                )

    @api.constrains('responsable_determinado', 'procede', 'dentro_plazo')
    def _check_fuera_plazo_no_afecta_tecnico(self):
        for record in self:
            if (
                record.responsable_determinado == 'tecnico'
                and record.procede == 'si'
                and not record.dentro_plazo
            ):
                raise ValidationError(
                    _(
                        'El reclamo está fuera del plazo permitido. Puede ser enviado a gerencia, '
                        'pero no debe afectar al técnico.'
                    )
                )

    # ============================================================
    # CREATE / WRITE
    # ============================================================

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('taller.incidencia') or '/'

        record = super(Incidencia, self).create(vals)

        if record.equipo_id and not self.env.context.get('skip_incidencia_auto_load'):
            record._cargar_datos_desde_equipo(write_record=True)

        if record.tipo == 'reclamo' and not self.env.context.get('skip_incidencia_auto_state'):
            record._actualizar_estado_por_plazo(write_record=True)

        record._post_event_message('creada')
        record._send_event_email('creada')

        return record

    def write(self, vals):
        old_states = {rec.id: rec.estado for rec in self}
        result = super(Incidencia, self).write(vals)

        if self.env.context.get('skip_incidencia_auto_load') or self.env.context.get('skip_incidencia_auto_state'):
            return result

        for record in self:
            if 'equipo_id' in vals and record.equipo_id:
                record._cargar_datos_desde_equipo(write_record=True)

            if any(campo in vals for campo in [
                'fecha_entrega',
                'fecha_hora',
                'plazo_maximo_dias',
                'tipo',
            ]):
                if record.tipo == 'reclamo':
                    record._actualizar_estado_por_plazo(write_record=True)

            if 'estado' in vals:
                old_state = old_states.get(record.id)
                if old_state and old_state != record.estado:
                    record._post_event_message('cambio_estado')

        return result

    # ============================================================
    # ACCIONES DE FLUJO
    # ============================================================

    def action_recargar_reparacion(self):
        for record in self:
            if not record.equipo_id:
                raise UserError(_('Debe seleccionar una serie/equipo.'))

            record._cargar_datos_desde_equipo(write_record=True)
            record._post_event_message('datos_recargados')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Datos actualizados'),
                'message': _('Se cargó la reparación relacionada y los datos del equipo.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_enviar_revision(self):
        for record in self:
            if record.tipo != 'reclamo':
                record.estado = 'en_revision'
                continue

            if not record.equipo_id:
                raise UserError(_('Debe seleccionar la serie/equipo afectado.'))

            if not record.fecha_entrega:
                raise UserError(_('No se encontró fecha de entrega. Debe completarse antes de enviar a revisión.'))

            if record.dentro_plazo:
                record.write({'estado': 'en_revision'})
                record._send_event_email('revision')
            else:
                record.write({
                    'estado': 'fuera_plazo',
                    'responsable_determinado': 'gerencia',
                    'motivo_no_afecta': (
                        '<p>Reclamo registrado fuera del plazo de 10 días posteriores a la entrega.</p>'
                        '<p>Se deriva a gerencia para análisis, sin afectar al técnico.</p>'
                    )
                })
                record._send_event_email('fuera_plazo')

        return True

    def action_marcar_procede(self):
        for record in self:
            if not record.dentro_plazo:
                record.write({
                    'estado': 'gerencia',
                    'procede': 'pendiente',
                    'responsable_determinado': 'gerencia',
                    'revisado_por_id': self.env.user.id,
                    'fecha_revision': fields.Datetime.now(),
                    'motivo_no_afecta': (
                        '<p>El reclamo está fuera del plazo permitido.</p>'
                        '<p>Gerencia puede analizarlo, pero no afecta al técnico.</p>'
                    )
                })
                record._send_event_email('gerencia')
                continue

            if record.responsable_determinado in [False, 'pendiente']:
                raise UserError(_('Debe seleccionar el responsable determinado antes de marcar que procede.'))

            vals = {
                'estado': 'procede',
                'procede': 'si',
                'revisado_por_id': self.env.user.id,
                'fecha_revision': fields.Datetime.now(),
            }

            if record.responsable_determinado != 'tecnico':
                vals['motivo_no_afecta'] = record._generar_motivo_no_afecta()

            record.write(vals)
            record._send_event_email('procede')

        return True

    def action_marcar_no_procede(self):
        for record in self:
            record.write({
                'estado': 'no_procede',
                'procede': 'no',
                'responsable_determinado': record.responsable_determinado or 'no_aplica',
                'revisado_por_id': self.env.user.id,
                'fecha_revision': fields.Datetime.now(),
                'motivo_no_afecta': record.motivo_no_afecta or (
                    '<p>El reclamo fue revisado y no procede técnicamente.</p>'
                    '<p>No afecta al técnico.</p>'
                )
            })
            record._send_event_email('no_procede')

        return True

    def action_enviar_gerencia(self):
        for record in self:
            record.write({
                'estado': 'gerencia',
                'responsable_determinado': 'gerencia',
                'motivo_no_afecta': record.motivo_no_afecta or (
                    '<p>Caso enviado a gerencia para análisis.</p>'
                    '<p>No afecta al técnico mientras no exista una validación formal.</p>'
                )
            })
            record._send_event_email('gerencia')

        return True

    def action_marcar_corregido(self):
        for record in self:
            record.write({
                'estado': 'corregido',
                'fecha_resolucion': fields.Datetime.now(),
            })
            record._send_event_email('corregido')

        return True

    def action_cerrar(self):
        for record in self:
            if record.estado not in [
                'procede',
                'no_procede',
                'corregido',
                'gerencia',
                'fuera_plazo',
            ]:
                raise UserError(
                    _('Solo se pueden cerrar incidencias revisadas, corregidas, fuera de plazo o derivadas a gerencia.')
                )

            record.write({
                'estado': 'cerrado',
                'fecha_resolucion': record.fecha_resolucion or fields.Datetime.now(),
                'cerrado_por_id': self.env.user.id,
            })
            record._send_event_email('cerrado')

        return True

    def action_reabrir(self):
        for record in self:
            record.write({
                'estado': 'en_revision',
                'procede': 'pendiente',
                'fecha_resolucion': False,
                'cerrado_por_id': False,
            })
            record._send_event_email('revision')

        return True

    def action_ver_reparacion(self):
        self.ensure_one()
        if not self.reparacion_id:
            raise UserError(_('No hay reparación relacionada.'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Reparación Relacionada'),
            'res_model': 'reparaciones.reparaciones',
            'view_mode': 'form',
            'res_id': self.reparacion_id.id,
            'target': 'current',
        }

    def action_ver_equipo(self):
        self.ensure_one()
        if not self.equipo_id:
            raise UserError(_('No hay equipo relacionado.'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Equipo Relacionado'),
            'res_model': 'sat.sat',
            'view_mode': 'form',
            'res_id': self.equipo_id.id,
            'target': 'current',
        }

    # ============================================================
    # CARGA AUTOMÁTICA
    # ============================================================

    def _cargar_datos_desde_equipo(self, write_record=False):
        for record in self:
            if not record.equipo_id:
                continue

            equipo = record.equipo_id
            vals = {}

            if equipo.cliente_id:
                vals['cliente_id'] = equipo.cliente_id.id

            if equipo.fecha_entrega:
                vals['fecha_entrega'] = equipo.fecha_entrega

            reparacion = record._buscar_reparacion_relacionada(equipo)

            if reparacion:
                vals['reparacion_id'] = reparacion.id

                tecnico_vals = record._get_tecnico_vals_from_reparacion(reparacion)
                vals.update(tecnico_vals)

                if 'cliente_id' in reparacion._fields and reparacion.cliente_id:
                    vals['cliente_id'] = reparacion.cliente_id.id

                if 'fecha_finalizacion' in reparacion._fields and reparacion.fecha_finalizacion:
                    vals['fecha_finalizacion_reparacion'] = reparacion.fecha_finalizacion

                if 'informe' in reparacion._fields and reparacion.informe:
                    vals['informe_tecnico'] = reparacion.informe

                if 'calidad_id' in reparacion._fields and reparacion.calidad_id:
                    vals['calidad_reparacion'] = record._get_valor_campo_legible(reparacion, 'calidad_id')

                if 'estado_id' in reparacion._fields and reparacion.estado_id:
                    vals['estado_reparacion'] = record._get_valor_campo_legible(reparacion, 'estado_id')

                observaciones = record._obtener_observaciones_reparacion(reparacion)
                if observaciones:
                    vals['observaciones_reparacion'] = observaciones

            if write_record and vals:
                record.with_context(skip_incidencia_auto_load=True).write(vals)
                record._actualizar_estado_por_plazo(write_record=True)
            else:
                for key, value in vals.items():
                    record[key] = value

    def _buscar_reparacion_relacionada(self, equipo):
        self.ensure_one()

        Reparacion = self.env['reparaciones.reparaciones']

        if equipo.reparacion_id:
            return equipo.reparacion_id

        reparacion = Reparacion.search([
            ('maquina_id', '=', equipo.id)
        ], order='fecha_finalizacion desc, write_date desc, create_date desc, id desc', limit=1)

        if reparacion:
            return reparacion

        if equipo.serie_id:
            reparacion = Reparacion.search([
                ('serie_id', '=', equipo.serie_id)
            ], order='fecha_finalizacion desc, write_date desc, create_date desc, id desc', limit=1)

        return reparacion or False

    def _get_tecnico_vals_from_reparacion(self, reparacion):
        vals = {
            'tecnico_id': False,
            'tecnico_empleado_id': False,
            'tecnico_nombre': False,
        }

        if 'responsable_id' not in reparacion._fields or not reparacion.responsable_id:
            return vals

        responsable = reparacion.responsable_id
        vals['tecnico_nombre'] = responsable.display_name or responsable.name

        if responsable._name == 'res.users':
            vals['tecnico_id'] = responsable.id
            empleado = self.env['hr.employee'].search([('user_id', '=', responsable.id)], limit=1)
            if empleado:
                vals['tecnico_empleado_id'] = empleado.id

        elif responsable._name == 'hr.employee':
            vals['tecnico_empleado_id'] = responsable.id
            if responsable.user_id:
                vals['tecnico_id'] = responsable.user_id.id

        return vals

    def _obtener_observaciones_reparacion(self, reparacion):
        textos = []

        campos = [
            'observaciones',
            'comentarios',
            'descripcion',
            'description',
            'falla_proveedor',
        ]

        for campo in campos:
            if campo in reparacion._fields and reparacion[campo]:
                label = reparacion._fields[campo].string or campo
                valor = reparacion[campo]
                textos.append(
                    '<p><strong>%s:</strong><br/>%s</p>' % (
                        label,
                        valor
                    )
                )

        return ''.join(textos) if textos else False

    # ============================================================
    # ESTADO POR PLAZO
    # ============================================================

    def _actualizar_estado_por_plazo(self, write_record=False):
        for record in self:
            if record.tipo != 'reclamo':
                continue

            vals = {}

            if not record.fecha_entrega:
                vals['estado'] = record.estado or 'reportado'

            elif record.dentro_plazo:
                if record.estado in ['reportado', 'fuera_plazo', 'gerencia']:
                    vals['estado'] = 'en_revision'

            else:
                vals.update({
                    'estado': 'fuera_plazo',
                    'responsable_determinado': 'gerencia',
                    'motivo_no_afecta': (
                        '<p>Reclamo registrado fuera del plazo de 10 días posteriores a la entrega.</p>'
                        '<p>Se registra para análisis de gerencia, pero no afecta al técnico.</p>'
                    )
                })

            if vals:
                if write_record:
                    record.with_context(skip_incidencia_auto_state=True).write(vals)
                else:
                    for key, value in vals.items():
                        record[key] = value

    # ============================================================
    # CORREOS POR PLANTILLA XML
    # ============================================================

    def _send_event_email(self, evento):
        """
        Envía correos usando plantillas XML.
        No define cuerpo de correo en Python.
        Las plantillas deben existir en XML.
        """
        template_map = {
            'creada': ('sat.email_template_taller_incidencia_creada', 'email_creacion_enviado'),
            'revision': ('sat.email_template_taller_incidencia_revision', 'email_revision_enviado'),
            'fuera_plazo': ('sat.email_template_taller_incidencia_fuera_plazo', 'email_gerencia_enviado'),
            'procede': ('sat.email_template_taller_incidencia_procede', 'email_procede_enviado'),
            'no_procede': ('sat.email_template_taller_incidencia_no_procede', 'email_no_procede_enviado'),
            'gerencia': ('sat.email_template_taller_incidencia_gerencia', 'email_gerencia_enviado'),
            'corregido': ('sat.email_template_taller_incidencia_corregida', False),
            'cerrado': ('sat.email_template_taller_incidencia_cerrada', 'email_cierre_enviado'),
        }

        for record in self:
            config = template_map.get(evento)
            if not config:
                continue

            template_xmlid, flag_field = config

            if flag_field and record[flag_field]:
                continue

            template = self.env.ref(template_xmlid, raise_if_not_found=False)

            if not template:
                record.write({
                    'correo_error': 'No se encontró la plantilla XML: %s' % template_xmlid
                })
                _logger.warning('[INCIDENCIA] No se encontró plantilla XML: %s', template_xmlid)
                continue

            try:
                template.with_context(
                    incidencia_evento=evento,
                    incidencia_url=record._get_record_url(),
                ).send_mail(record.id, force_send=True)

                vals = {
                    'ultimo_correo_fecha': fields.Datetime.now(),
                    'ultimo_correo_template': template_xmlid,
                    'correo_error': False,
                }

                if flag_field:
                    vals[flag_field] = True

                record.with_context(
                    skip_incidencia_auto_load=True,
                    skip_incidencia_auto_state=True
                ).write(vals)

            except Exception as e:
                _logger.error(
                    '[INCIDENCIA] Error enviando plantilla %s para incidencia %s: %s',
                    template_xmlid,
                    record.name,
                    e,
                    exc_info=True
                )
                record.with_context(
                    skip_incidencia_auto_load=True,
                    skip_incidencia_auto_state=True
                ).write({
                    'correo_error': str(e),
                })

    def action_reenviar_correo_estado(self):
        for record in self:
            evento = 'creada'

            if record.estado == 'en_revision':
                evento = 'revision'
            elif record.estado == 'fuera_plazo':
                evento = 'fuera_plazo'
            elif record.estado == 'procede':
                evento = 'procede'
            elif record.estado == 'no_procede':
                evento = 'no_procede'
            elif record.estado == 'gerencia':
                evento = 'gerencia'
            elif record.estado == 'corregido':
                evento = 'corregido'
            elif record.estado == 'cerrado':
                evento = 'cerrado'

            record._send_event_email(evento)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Correo procesado'),
                'message': _('Se intentó enviar el correo correspondiente al estado actual.'),
                'type': 'success',
                'sticky': False,
            }
        }

    # ============================================================
    # MENSAJES CHATTER
    # ============================================================

    def _post_event_message(self, evento):
        for record in self:
            if evento == 'creada':
                body = _(
                    '<p><strong>Incidencia registrada</strong></p>'
                    '<p>La incidencia fue creada y quedó pendiente de revisión.</p>'
                )
            elif evento == 'datos_recargados':
                body = _(
                    '<p><strong>Datos recargados</strong></p>'
                    '<p>Se actualizó la información del equipo y reparación relacionada.</p>'
                )
            elif evento == 'cambio_estado':
                body = _(
                    '<p><strong>Estado actualizado</strong></p>'
                    '<p>Nuevo estado: <strong>%s</strong></p>'
                ) % (dict(record._fields['estado'].selection).get(record.estado, record.estado))
            else:
                body = _('<p><strong>Incidencia actualizada</strong></p>')

            record.message_post(
                body=body,
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )

    # ============================================================
    # ALERTAS ONCHANGE
    # ============================================================

    def _get_warning_onchange_equipo(self):
        self.ensure_one()

        if not self.reparacion_id:
            return {
                'warning': {
                    'title': _('Sin reparación relacionada'),
                    'message': _(
                        'No se encontró una reparación relacionada para esta máquina. '
                        'La incidencia puede registrarse, pero debe validarse manualmente.'
                    ),
                }
            }

        if not self.fecha_entrega:
            return {
                'warning': {
                    'title': _('Sin fecha de entrega'),
                    'message': _(
                        'La máquina tiene reparación relacionada, pero no tiene fecha de entrega. '
                        'No se puede calcular si el reclamo está dentro de los 10 días.'
                    ),
                }
            }

        if self.dentro_plazo:
            return {
                'warning': {
                    'title': _('Reclamo dentro de plazo'),
                    'message': _(
                        'El reclamo está dentro del plazo permitido de 10 días. '
                        'Puede pasar a revisión técnica y solo afectará al técnico si procede.'
                    ),
                }
            }

        return {
            'warning': {
                'title': _('Reclamo fuera de plazo'),
                'message': _(
                    'El reclamo está fuera del plazo de 10 días posteriores a la entrega. '
                    'Se registra para análisis de gerencia, pero no afecta al técnico.'
                ),
            }
        }

    def _get_warning_plazo(self):
        self.ensure_one()

        if not self.fecha_entrega:
            return {
                'warning': {
                    'title': _('Sin fecha de entrega'),
                    'message': _('No se puede calcular el plazo del reclamo.'),
                }
            }

        if not self.dentro_plazo:
            return {
                'warning': {
                    'title': _('Fuera de plazo'),
                    'message': _('El reclamo queda para análisis de gerencia y no afecta al técnico.'),
                }
            }

        return False

    # ============================================================
    # UTILITARIOS
    # ============================================================

    def _get_record_url(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return '%s/web#id=%s&model=taller.incidencia&view_type=form' % (base_url, self.id)

    def _to_date(self, value):
        if not value:
            return False

        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        if isinstance(value, str):
            try:
                return fields.Datetime.from_string(value).date()
            except Exception:
                try:
                    return fields.Date.from_string(value)
                except Exception:
                    return False

        return False

    def _get_valor_campo_legible(self, record, campo):
        if not record or campo not in record._fields:
            return ''

        valor = record[campo]

        if not valor:
            return ''

        field = record._fields[campo]

        if field.type == 'many2one':
            return valor.display_name or ''

        if field.type == 'selection':
            selection = field.selection

            if callable(selection):
                selection = selection(record.env[record._name])

            return dict(selection or []).get(valor, valor)

        return str(valor)

    def _generar_motivo_no_afecta(self):
        self.ensure_one()

        if not self.dentro_plazo:
            return (
                '<p>El reclamo está fuera del plazo permitido de 10 días.</p>'
                '<p>Se analiza solo por gerencia y no afecta al técnico.</p>'
            )

        if self.procede == 'no':
            return (
                '<p>El reclamo fue revisado y no procede técnicamente.</p>'
                '<p>No afecta al técnico.</p>'
            )

        responsables = {
            'asesora': '<p>La responsabilidad fue determinada como proceso de asesora.</p>',
            'almacen': '<p>La responsabilidad fue determinada como proceso de almacén.</p>',
            'despacho': '<p>La responsabilidad fue determinada como despacho o transporte.</p>',
            'cliente': '<p>La causa corresponde al uso o manipulación del cliente.</p>',
            'comercial': '<p>La responsabilidad fue determinada como proceso comercial.</p>',
            'gerencia': '<p>El caso fue derivado para análisis de gerencia.</p>',
            'no_aplica': '<p>No aplica responsabilidad técnica.</p>',
            'pendiente': '<p>La responsabilidad aún no ha sido determinada.</p>',
        }

        return responsables.get(
            self.responsable_determinado,
            '<p>El reclamo no corresponde a responsabilidad técnica.</p>'
        )