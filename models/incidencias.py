# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, date


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

    descripcion = fields.Text(
        string='Descripción del Reclamo',
        tracking=True
    )

    prioridad = fields.Selection([
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
        ('critica', 'Crítica'),
    ], string='Prioridad', default='baja', tracking=True)

    active = fields.Boolean(
        string='Activo',
        default=True
    )

    # ============================================================
    # EQUIPO / SERIE
    # ============================================================

    equipo_id = fields.Many2one(
        'sat.sat',
        string='Serie / Equipo Afectado',
        required=True,
        tracking=True,
        help='Seleccionar la máquina afectada. Luego se cargará automáticamente la reparación relacionada.'
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

    factura_venta = fields.Char(
        string='Factura de Venta',
        related='equipo_id.factura_venta',
        store=True,
        readonly=True
    )

    # ============================================================
    # REPARACIÓN RELACIONADA
    # ============================================================

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones',
        string='Reparación Relacionada',
        tracking=True,
        help='Última reparación encontrada para la máquina seleccionada.'
    )

    tecnico_id = fields.Many2one(
        'res.users',
        string='Técnico Responsable',
        tracking=True,
        help='Técnico responsable de la reparación relacionada.'
    )

    empleado_id = fields.Many2one(
        'hr.employee',
        string='Empleado Asignado',
        tracking=True,
        help='Campo original. Puede usarse para asignar seguimiento operativo.'
    )

    fecha_entrega = fields.Date(
        string='Fecha de Entrega',
        tracking=True,
        help='Fecha de entrega de la máquina. Se usa para calcular el plazo de 10 días.'
    )

    fecha_finalizacion_reparacion = fields.Datetime(
        string='Fecha Finalización Reparación',
        readonly=True,
        tracking=True
    )

    dias_desde_entrega = fields.Integer(
        string='Días desde Entrega',
        compute='_compute_plazo',
        store=True
    )

    dentro_plazo = fields.Boolean(
        string='Dentro de Plazo',
        compute='_compute_plazo',
        store=True
    )

    plazo_maximo_dias = fields.Integer(
        string='Plazo Máximo de Reclamo',
        default=10,
        required=True,
        help='Plazo máximo después de la entrega para que un reclamo pueda afectar al técnico.'
    )

    informe_tecnico = fields.Text(
        string='Informe Técnico Relacionado',
        readonly=True
    )

    calidad_reparacion = fields.Char(
        string='Calidad Reparación',
        readonly=True
    )

    estado_reparacion = fields.Char(
        string='Estado Reparación',
        readonly=True
    )

    observaciones_reparacion = fields.Text(
        string='Observaciones de Reparación',
        readonly=True
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

    motivo_no_afecta = fields.Text(
        string='Motivo por el que no afecta al Técnico',
        tracking=True
    )

    observacion_validacion = fields.Text(
        string='Observación de Validación',
        tracking=True
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

    acciones = fields.Text(
        string='Acciones Tomadas',
        tracking=True
    )

    fecha_resolucion = fields.Datetime(
        string='Fecha de Resolución',
        tracking=True
    )

    comentarios_cliente = fields.Text(
        string='Comentarios del Cliente',
        tracking=True
    )

    costos = fields.Float(
        string='Costos Asociados',
        tracking=True
    )

    evidencia_ids = fields.Many2many(
        'ir.attachment',
        'taller_incidencia_ir_attachment_rel',
        'incidencia_id',
        'attachment_id',
        string='Evidencias'
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

            if not record.fecha_entrega:
                continue

            fecha_reclamo = record._to_date(record.fecha_hora or fields.Datetime.now())
            fecha_entrega = record._to_date(record.fecha_entrega)

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

    # ============================================================
    # ONCHANGE
    # ============================================================

    @api.onchange('equipo_id')
    def _onchange_equipo_id(self):
        for record in self:
            if record.equipo_id:
                record._cargar_datos_desde_equipo()

    @api.onchange('fecha_entrega', 'fecha_hora', 'plazo_maximo_dias')
    def _onchange_plazo(self):
        for record in self:
            if record.tipo == 'reclamo':
                record._actualizar_estado_por_plazo()

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
                    'El reclamo corresponde a suministros, botellas de tóner o accesorios no entregados. '
                    'Debe validarse contra el informe técnico y el proceso de asesora, almacén o despacho. '
                    'No afecta al técnico salvo que la revisión determine responsabilidad técnica directa.'
                )

    # ============================================================
    # VALIDACIONES
    # ============================================================

    @api.constrains('tipo', 'equipo_id')
    def _check_equipo_obligatorio(self):
        for record in self:
            if record.tipo == 'reclamo' and not record.equipo_id:
                raise ValidationError(
                    'Para registrar un reclamo es obligatorio seleccionar la serie/equipo afectado.'
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
                    'El reclamo está fuera del plazo permitido. Puede ser enviado a gerencia, '
                    'pero no debe afectar al técnico.'
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

        record.message_post(
            body=record._get_mensaje_creacion(),
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )

        return record

    def write(self, vals):
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

        return result

    # ============================================================
    # ACCIONES DE FLUJO
    # ============================================================

    def action_enviar_revision(self):
        for record in self:
            if record.tipo != 'reclamo':
                record.estado = 'en_revision'
                continue

            if not record.equipo_id:
                raise UserError('Debe seleccionar la serie/equipo afectado.')

            if not record.fecha_entrega:
                raise UserError(
                    'No se encontró fecha de entrega. Debe completarse antes de enviar a revisión.'
                )

            if record.dentro_plazo:
                record.estado = 'en_revision'
            else:
                record.write({
                    'estado': 'fuera_plazo',
                    'responsable_determinado': 'gerencia',
                    'motivo_no_afecta': (
                        'Reclamo registrado fuera del plazo de 10 días posteriores a la entrega. '
                        'Se deriva a gerencia para análisis, sin afectar al técnico.'
                    )
                })

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
                        'El reclamo está fuera del plazo permitido. Gerencia puede analizarlo, '
                        'pero no afecta al técnico.'
                    )
                })
                continue

            if record.responsable_determinado in [False, 'pendiente']:
                raise UserError(
                    'Debe seleccionar el responsable determinado antes de marcar que procede.'
                )

            vals = {
                'estado': 'procede',
                'procede': 'si',
                'revisado_por_id': self.env.user.id,
                'fecha_revision': fields.Datetime.now(),
            }

            if record.responsable_determinado != 'tecnico':
                vals['motivo_no_afecta'] = record._generar_motivo_no_afecta()

            record.write(vals)

    def action_marcar_no_procede(self):
        for record in self:
            record.write({
                'estado': 'no_procede',
                'procede': 'no',
                'responsable_determinado': record.responsable_determinado or 'no_aplica',
                'revisado_por_id': self.env.user.id,
                'fecha_revision': fields.Datetime.now(),
                'motivo_no_afecta': record.motivo_no_afecta or (
                    'El reclamo fue revisado y no procede técnicamente. No afecta al técnico.'
                )
            })

    def action_enviar_gerencia(self):
        for record in self:
            record.write({
                'estado': 'gerencia',
                'responsable_determinado': 'gerencia',
                'motivo_no_afecta': record.motivo_no_afecta or (
                    'Caso enviado a gerencia para análisis. No afecta al técnico.'
                )
            })

    def action_marcar_corregido(self):
        for record in self:
            record.write({
                'estado': 'corregido',
                'fecha_resolucion': fields.Datetime.now(),
            })

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
                    'Solo se pueden cerrar incidencias revisadas, corregidas, fuera de plazo o derivadas a gerencia.'
                )

            record.write({
                'estado': 'cerrado',
                'fecha_resolucion': record.fecha_resolucion or fields.Datetime.now(),
            })

    def action_reabrir(self):
        for record in self:
            record.write({
                'estado': 'en_revision',
                'procede': 'pendiente',
                'fecha_resolucion': False,
            })

    def action_recargar_reparacion(self):
        for record in self:
            if not record.equipo_id:
                raise UserError('Debe seleccionar una serie/equipo.')

            record._cargar_datos_desde_equipo(write_record=True)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Datos actualizados',
                'message': 'Se cargó la reparación relacionada y los datos del equipo.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_ver_reparacion(self):
        self.ensure_one()
        if not self.reparacion_id:
            raise UserError('No hay reparación relacionada.')

        return {
            'type': 'ir.actions.act_window',
            'name': 'Reparación Relacionada',
            'res_model': 'reparaciones.reparaciones',
            'view_mode': 'form',
            'res_id': self.reparacion_id.id,
            'target': 'current',
        }

    def action_ver_equipo(self):
        self.ensure_one()
        if not self.equipo_id:
            raise UserError('No hay equipo relacionado.')

        return {
            'type': 'ir.actions.act_window',
            'name': 'Equipo Relacionado',
            'res_model': 'sat.sat',
            'view_mode': 'form',
            'res_id': self.equipo_id.id,
            'target': 'current',
        }

    # ============================================================
    # CARGA AUTOMÁTICA DE DATOS
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

                if reparacion.responsable_id:
                    vals['tecnico_id'] = reparacion.responsable_id.id

                if hasattr(reparacion, 'cliente_id') and reparacion.cliente_id:
                    vals['cliente_id'] = reparacion.cliente_id.id

                if hasattr(reparacion, 'fecha_finalizacion') and reparacion.fecha_finalizacion:
                    vals['fecha_finalizacion_reparacion'] = reparacion.fecha_finalizacion

                if hasattr(reparacion, 'informe') and reparacion.informe:
                    vals['informe_tecnico'] = reparacion.informe

                if hasattr(reparacion, 'calidad_id') and reparacion.calidad_id:
                    vals['calidad_reparacion'] = reparacion.calidad_id.display_name

                if hasattr(reparacion, 'estado_id') and reparacion.estado_id:
                    vals['estado_reparacion'] = dict(reparacion._fields['estado_id'].selection).get(
                        reparacion.estado_id,
                        reparacion.estado_id
                    )

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

        # 1. Prioriza la reparación vinculada directamente en sat.sat
        if equipo.reparacion_id:
            return equipo.reparacion_id

        # 2. Luego busca la última reparación por maquina_id
        reparacion = Reparacion.search([
            ('maquina_id', '=', equipo.id)
        ], order='fecha_finalizacion desc, write_date desc, create_date desc, id desc', limit=1)

        if reparacion:
            return reparacion

        # 3. Respaldo por serie_id
        if equipo.serie_id:
            reparacion = Reparacion.search([
                ('serie_id', '=', equipo.serie_id)
            ], order='fecha_finalizacion desc, write_date desc, create_date desc, id desc', limit=1)

        return reparacion or False

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
            if hasattr(reparacion, campo) and reparacion[campo]:
                label = reparacion._fields[campo].string or campo
                textos.append('%s: %s' % (label, reparacion[campo]))

        return '\n\n'.join(textos) if textos else False

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
                        'Reclamo registrado fuera del plazo de 10 días posteriores a la entrega. '
                        'Se registra para análisis de gerencia, pero no afecta al técnico.'
                    )
                })

            if vals:
                if write_record:
                    record.with_context(skip_incidencia_auto_state=True).write(vals)
                else:
                    for key, value in vals.items():
                        record[key] = value

    # ============================================================
    # UTILITARIOS
    # ============================================================

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

    def _generar_motivo_no_afecta(self):
        self.ensure_one()

        if not self.dentro_plazo:
            return (
                'El reclamo está fuera del plazo permitido de 10 días. '
                'Se analiza solo por gerencia y no afecta al técnico.'
            )

        if self.procede == 'no':
            return (
                'El reclamo fue revisado y no procede técnicamente. '
                'No afecta al técnico.'
            )

        responsables = {
            'asesora': 'La responsabilidad fue determinada como proceso de asesora.',
            'almacen': 'La responsabilidad fue determinada como proceso de almacén.',
            'despacho': 'La responsabilidad fue determinada como despacho o transporte.',
            'cliente': 'La causa corresponde al uso o manipulación del cliente.',
            'comercial': 'La responsabilidad fue determinada como proceso comercial.',
            'gerencia': 'El caso fue derivado para análisis de gerencia.',
            'no_aplica': 'No aplica responsabilidad técnica.',
            'pendiente': 'La responsabilidad aún no ha sido determinada.',
        }

        return responsables.get(
            self.responsable_determinado,
            'El reclamo no corresponde a responsabilidad técnica.'
        )

    def _get_mensaje_creacion(self):
        self.ensure_one()

        return """
            <p><strong>Incidencia registrada</strong></p>
            <ul>
                <li><strong>Tipo:</strong> %s</li>
                <li><strong>Serie:</strong> %s</li>
                <li><strong>Cliente:</strong> %s</li>
                <li><strong>Equipo:</strong> %s</li>
                <li><strong>Reparación:</strong> %s</li>
                <li><strong>Técnico:</strong> %s</li>
                <li><strong>Fecha de entrega:</strong> %s</li>
                <li><strong>Días desde entrega:</strong> %s</li>
                <li><strong>Dentro de plazo:</strong> %s</li>
                <li><strong>Estado:</strong> %s</li>
            </ul>
        """ % (
            dict(self._fields['tipo'].selection).get(self.tipo, ''),
            self.serie or '',
            self.cliente_id.display_name or '',
            self.equipo_id.display_name or '',
            self.reparacion_id.display_name or self.reparacion_id.name or '',
            self.tecnico_id.name or '',
            self.fecha_entrega or '',
            self.dias_desde_entrega or 0,
            'Sí' if self.dentro_plazo else 'No',
            dict(self._fields['estado'].selection).get(self.estado, ''),
        )