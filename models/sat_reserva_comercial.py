# -*- coding: utf-8 -*-

from datetime import date, timedelta
import logging

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


_logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS DE PERMISOS
# =============================================================================

class SatReservaSecurityMixin(models.AbstractModel):
    _name = 'sat.reserva.security.mixin'
    _description = 'Helper de seguridad para reservas comerciales'

    def _reserva_usuario_es_gerencia(self):
        user = self.env.user

        if self.env.is_superuser() or user.has_group('base.group_system'):
            return True

        group = self.env.ref(
            'sat.group_reserva_comercial_autorizado',
            raise_if_not_found=False,
        )
        return bool(group and user in group.users)

    def _reserva_exigir_gerencia(self):
        if not self._reserva_usuario_es_gerencia():
            raise AccessError(
                _(
                    'Esta operación requiere autorización de gerencia.'
                )
            )
        return True


# =============================================================================
# REGLAS COMERCIALES
# =============================================================================

class SatReservaRegla(models.Model):
    _name = 'sat.reserva.regla'
    _description = 'Regla de separación comercial'
    _inherit = [
        'mail.thread',
        'mail.activity.mixin',
        'sat.reserva.security.mixin',
    ]
    _order = 'prioridad desc, id desc'

    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True,
    )

    active = fields.Boolean(
        string='Activa',
        default=True,
        tracking=True,
    )

    prioridad = fields.Integer(
        string='Prioridad',
        default=10,
        tracking=True,
        help='Si coinciden varias reglas, se usa la más específica y luego la de mayor prioridad.',
    )

    tipo_aplicacion = fields.Selection(
        [
            ('general', 'Regla general'),
            ('cliente', 'Cliente'),
            ('cliente_importacion', 'Cliente + importación'),
        ],
        string='Aplicar a',
        required=True,
        default='general',
        tracking=True,
    )

    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        tracking=True,
        ondelete='cascade',
    )

    importacion = fields.Char(
        string='Importación',
        tracking=True,
    )

    dias_separacion = fields.Integer(
        string='Días de separación',
        required=True,
        default=6,
        tracking=True,
    )

    fecha_inicio = fields.Date(
        string='Vigente desde',
        tracking=True,
    )

    fecha_fin = fields.Date(
        string='Vigente hasta',
        tracking=True,
        help='Vacío significa que la regla continúa vigente hasta que gerencia la desactive.',
    )

    observacion = fields.Text(
        string='Observación',
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        self._reserva_exigir_gerencia()
        return super().create(vals_list)

    def write(self, vals):
        self._reserva_exigir_gerencia()
        return super().write(vals)

    def unlink(self):
        self._reserva_exigir_gerencia()
        return super().unlink()

    @api.constrains('dias_separacion')
    def _check_dias_separacion(self):
        for record in self:
            if record.dias_separacion <= 0:
                raise ValidationError(
                    _('Los días de separación deben ser mayores a cero.')
                )

    @api.constrains('fecha_inicio', 'fecha_fin')
    def _check_fechas(self):
        for record in self:
            if (
                record.fecha_inicio
                and record.fecha_fin
                and record.fecha_fin < record.fecha_inicio
            ):
                raise ValidationError(
                    _('La fecha final no puede ser menor que la fecha inicial.')
                )

    @api.constrains(
        'tipo_aplicacion',
        'cliente_id',
        'importacion',
    )
    def _check_alcance(self):
        for record in self:
            if record.tipo_aplicacion == 'general':
                if record.cliente_id or record.importacion:
                    raise ValidationError(
                        _('La regla general no debe tener cliente ni importación.')
                    )

            elif record.tipo_aplicacion == 'cliente':
                if not record.cliente_id:
                    raise ValidationError(
                        _('Debe seleccionar un cliente.')
                    )
                if record.importacion:
                    raise ValidationError(
                        _('Una regla de cliente no debe tener importación.')
                    )

            elif record.tipo_aplicacion == 'cliente_importacion':
                if not record.cliente_id or not record.importacion:
                    raise ValidationError(
                        _('Debe seleccionar cliente e indicar importación.')
                    )

    @api.constrains(
        'active',
        'tipo_aplicacion',
        'cliente_id',
        'importacion',
        'fecha_inicio',
        'fecha_fin',
    )
    def _check_solapamiento(self):
        for record in self:
            if not record.active:
                continue

            domain = [
                ('id', '!=', record.id),
                ('active', '=', True),
                ('tipo_aplicacion', '=', record.tipo_aplicacion),
            ]

            if record.tipo_aplicacion in ('cliente', 'cliente_importacion'):
                domain.append(('cliente_id', '=', record.cliente_id.id))

            if record.tipo_aplicacion == 'cliente_importacion':
                domain.append(('importacion', '=', record.importacion))

            others = self.search(domain)

            start_a = record.fecha_inicio or date.min
            end_a = record.fecha_fin or date.max

            for other in others:
                start_b = other.fecha_inicio or date.min
                end_b = other.fecha_fin or date.max

                if start_a <= end_b and start_b <= end_a:
                    raise ValidationError(
                        _(
                            'La regla "%(actual)s" se cruza con la regla activa "%(otra)s". '
                            'No debe haber dos reglas del mismo alcance vigentes al mismo tiempo.'
                        )
                        % {
                            'actual': record.display_name,
                            'otra': other.display_name,
                        }
                    )


# =============================================================================
# SOLICITUDES A GERENCIA
# =============================================================================

class SatReservaSolicitud(models.Model):
    _name = 'sat.reserva.solicitud'
    _description = 'Solicitud de autorización comercial'
    _inherit = [
        'mail.thread',
        'mail.activity.mixin',
        'sat.reserva.security.mixin',
    ]
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Solicitud',
        default='Nueva',
        readonly=True,
        copy=False,
        tracking=True,
    )

    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('pending', 'Pendiente de gerencia'),
            ('partial', 'Procesada parcialmente'),
            ('approved', 'Aprobada'),
            ('rejected', 'Rechazada'),
            ('done', 'Finalizada'),
            ('cancelled', 'Cancelada'),
        ],
        string='Estado',
        default='draft',
        required=True,
        tracking=True,
        index=True,
    )

    solicitante_id = fields.Many2one(
        'res.users',
        string='Solicitado por',
        default=lambda self: self.env.user,
        required=True,
        readonly=True,
        tracking=True,
    )

    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente destino',
        tracking=True,
    )

    asesora_destino_id = fields.Many2one(
        'res.users',
        string='Asesora destino',
        tracking=True,
    )

    tipo_solicitud = fields.Selection(
        [
            ('reservar', 'Reserva especial'),
            ('extender', 'Extender separación'),
            ('reducir', 'Reducir separación'),
            ('cambiar_fecha', 'Cambiar fecha límite'),
            ('cambiar_cliente', 'Cambiar cliente'),
            ('cambiar_asesora', 'Cambiar asesora'),
            ('liberar', 'Liberar máquinas'),
        ],
        string='Solicitud',
        required=True,
        default='reservar',
        tracking=True,
    )

    motivo = fields.Selection(
        [
            ('pago', 'Cliente pagó'),
            ('adelanto', 'Cliente dejó adelanto'),
            ('confirmacion', 'Cliente confirmó compra'),
            ('orden_compra', 'Orden de compra recibida'),
            ('empresa_interna', 'Empresa interna'),
            ('espera_recojo', 'Esperando recojo'),
            ('espera_documentacion', 'Esperando documentación'),
            ('espera_revision', 'Esperando revisión técnica'),
            ('espera_reparacion', 'Esperando reparación'),
            ('cambio_cliente', 'Cambio de cliente solicitado'),
            ('cambio_asesora', 'Cambio de asesora solicitado'),
            ('otro', 'Otro'),
        ],
        string='Motivo',
        required=True,
        tracking=True,
    )

    detalle_motivo = fields.Text(
        string='Detalle / sustento',
        required=True,
        tracking=True,
    )

    modalidad_solicitada = fields.Selection(
        [
            ('fecha', 'Hasta una fecha'),
            ('dias', 'Cantidad de días'),
            ('mantener', 'Mantener vencimiento actual'),
        ],
        string='Plazo solicitado por',
        tracking=True,
    )

    fecha_solicitada = fields.Date(
        string='Fecha solicitada',
        tracking=True,
    )

    dias_solicitados = fields.Integer(
        string='Días solicitados',
        tracking=True,
    )

    modalidad_aprobacion = fields.Selection(
        [
            ('fecha', 'Hasta una fecha'),
            ('dias', 'Cantidad de días'),
            ('mantener', 'Mantener vencimiento actual'),
        ],
        string='Gerencia aprueba por',
        tracking=True,
    )

    fecha_aprobada = fields.Date(
        string='Fecha aprobada',
        tracking=True,
    )

    dias_aprobados = fields.Integer(
        string='Días aprobados',
        tracking=True,
    )

    comentario_gerencia = fields.Text(
        string='Comentario de gerencia',
        tracking=True,
    )

    line_ids = fields.One2many(
        'sat.reserva.solicitud.linea',
        'solicitud_id',
        string='Máquinas',
        copy=False,
    )

    cantidad_maquinas = fields.Integer(
        string='Máquinas',
        compute='_compute_cantidad_maquinas',
    )

    procesado_por_id = fields.Many2one(
        'res.users',
        string='Procesado por',
        readonly=True,
        tracking=True,
    )

    fecha_procesamiento = fields.Datetime(
        string='Fecha de procesamiento',
        readonly=True,
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self._reserva_usuario_es_gerencia():
            for vals in vals_list:
                if vals.get('solicitante_id') and vals.get('solicitante_id') != self.env.user.id:
                    raise AccessError(_('No puede crear solicitudes a nombre de otro usuario.'))
                if vals.get('state') not in (False, 'draft'):
                    raise AccessError(_('Un usuario normal no puede crear una solicitud ya aprobada o procesada.'))
                if any(vals.get(field) for field in (
                    'modalidad_aprobacion',
                    'fecha_aprobada',
                    'dias_aprobados',
                    'comentario_gerencia',
                    'procesado_por_id',
                    'fecha_procesamiento',
                )):
                    raise AccessError(_('Los datos de aprobación solo pueden ser definidos por un usuario autorizado.'))
        records = super().create(vals_list)

        for record in records:
            if not record.name or record.name == 'Nueva':
                record.name = 'RES-%06d' % record.id

        return records

    def write(self, vals):
        vals = dict(vals or {})
        sensitive_fields = {
            'state',
            'modalidad_aprobacion',
            'fecha_aprobada',
            'dias_aprobados',
            'comentario_gerencia',
            'procesado_por_id',
            'fecha_procesamiento',
        }
        if (
            sensitive_fields.intersection(vals)
            and not self.env.context.get('sat_reserva_internal_request_write')
            and not self._reserva_usuario_es_gerencia()
        ):
            raise AccessError(
                _('Solo un usuario autorizado puede modificar la aprobación o el estado procesado de la solicitud.')
            )
        return super().write(vals)

    def unlink(self):
        for record in self:
            if record.state != 'draft' or record.line_ids:
                raise ValidationError(
                    _('Las solicitudes con trazabilidad no se eliminan. Debe cancelarlas para conservar el historial.')
                )
        return super().unlink()

    @api.depends('line_ids')
    def _compute_cantidad_maquinas(self):
        for record in self:
            record.cantidad_maquinas = len(record.line_ids)

    @api.constrains(
        'tipo_solicitud',
        'cliente_id',
        'asesora_destino_id',
        'modalidad_solicitada',
        'fecha_solicitada',
        'dias_solicitados',
    )
    def _check_solicitud(self):
        today = fields.Date.context_today(self)

        for record in self:
            if record.tipo_solicitud == 'cambiar_cliente' and not record.cliente_id:
                raise ValidationError(
                    _('Debe indicar el nuevo cliente.')
                )

            if record.tipo_solicitud == 'cambiar_asesora' and not record.asesora_destino_id:
                raise ValidationError(
                    _('Debe indicar la nueva asesora.')
                )

            requiere_plazo = record.tipo_solicitud in (
                'reservar',
                'extender',
                'reducir',
                'cambiar_fecha',
            )

            if requiere_plazo or record.tipo_solicitud == 'cambiar_cliente':
                if record.modalidad_solicitada == 'mantener':
                    if record.tipo_solicitud != 'cambiar_cliente':
                        raise ValidationError(
                            _('Mantener vencimiento solo aplica al cambio de cliente.')
                        )
                elif record.modalidad_solicitada == 'fecha':
                    if not record.fecha_solicitada:
                        raise ValidationError(
                            _('Debe indicar la fecha solicitada.')
                        )
                    if record.fecha_solicitada < today:
                        raise ValidationError(
                            _('La fecha solicitada no puede ser anterior a hoy.')
                        )

                elif record.modalidad_solicitada == 'dias':
                    if record.dias_solicitados <= 0:
                        raise ValidationError(
                            _('Los días solicitados deben ser mayores a cero.')
                        )

                else:
                    raise ValidationError(
                        _('Debe indicar si solicita una fecha o una cantidad de días.')
                    )

    # -------------------------------------------------------------------------
    # CORREOS Y ENLACES DE SOLICITUDES
    # -------------------------------------------------------------------------

    def _reserva_get_backend_url(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        return '%s/web#id=%s&model=sat.reserva.solicitud&view_type=form' % (
            base_url.rstrip('/'),
            self.id,
        )

    def _reserva_selection_label(self, field_name, value=None):
        self.ensure_one()
        field = self._fields.get(field_name)
        if not field or not getattr(field, 'selection', None):
            return value or ''
        current_value = getattr(self, field_name) if value is None else value
        selection = field.selection
        if callable(selection):
            selection = selection(self.env[self._name])
        return dict(selection).get(current_value, current_value or '')

    def _reserva_line_resultado_label(self, line):
        self.ensure_one()
        selection = line._fields['resultado'].selection
        if callable(selection):
            selection = selection(line)
        return dict(selection).get(line.resultado, line.resultado or '')

    def _reserva_emails_autorizados(self):
        self.ensure_one()
        group = self.env.ref(
            'sat.group_reserva_comercial_autorizado',
            raise_if_not_found=False,
        )
        if not group:
            return []
        users = group.users.filtered(lambda user: user.active and user.email)
        emails = []
        seen = set()
        for user in users:
            email = (user.email or '').strip()
            key = email.lower()
            if email and key not in seen:
                seen.add(key)
                emails.append(email)
        return emails

    def _reserva_enviar_template(self, template_xmlid, email_to, contexto=None):
        self.ensure_one()
        if not email_to:
            return False
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            _logger.error(
                'Reservas comerciales: no existe la plantilla %s para %s',
                template_xmlid,
                self.display_name,
            )
            self.message_post(
                body=_(
                    'No se pudo preparar el correo porque no existe la plantilla %s.'
                ) % template_xmlid,
                subtype_xmlid='mail.mt_note',
            )
            return False
        try:
            mail_id = template.with_context(**(contexto or {})).send_mail(
                self.id,
                force_send=True,
                raise_exception=False,
                email_values={
                    'email_to': email_to,
                },
            )
            return bool(mail_id)
        except Exception:
            _logger.exception(
                'Reservas comerciales: error enviando plantilla %s para solicitud %s',
                template_xmlid,
                self.display_name,
            )
            self.message_post(
                body=_(
                    'La solicitud se procesó correctamente, pero ocurrió un error al intentar enviar el correo automático.'
                ),
                subtype_xmlid='mail.mt_note',
            )
            return False

    def _reserva_notificar_gerencia(self):
        self.ensure_one()
        emails = self._reserva_emails_autorizados()
        if not emails:
            raise ValidationError(
                _(
                    'No hay usuarios activos con correo en el grupo "Autorizados Reservas Comerciales". '
                    'Configure al menos un usuario autorizado con dirección de correo antes de enviar la solicitud.'
                )
            )
        sent = self._reserva_enviar_template(
            'sat.mail_template_reserva_solicitud_gerencia',
            ','.join(emails),
        )
        if sent:
            self.message_post(
                body=_(
                    'Solicitud enviada por correo a los usuarios autorizados: %s'
                ) % ', '.join(emails),
                subtype_xmlid='mail.mt_note',
            )
        return sent

    def _reserva_tipo_resultado_correo(self):
        self.ensure_one()
        lines = self.line_ids
        pending = lines.filtered(lambda line: line.resultado == 'pending')
        rejected = lines.filtered(lambda line: line.resultado == 'rejected')
        accepted = lines.filtered(
            lambda line: line.resultado in ('approved', 'released', 'done')
        )
        if pending or (rejected and accepted):
            return 'partial'
        if rejected and not accepted:
            return 'rejected'
        return 'approved'

    def _reserva_notificar_solicitante_resultado(self):
        self.ensure_one()
        email = (self.solicitante_id.email or '').strip()
        if not email:
            self.message_post(
                body=_(
                    'No se envió el correo de resultado porque el solicitante %s no tiene correo configurado.'
                ) % self.solicitante_id.display_name,
                subtype_xmlid='mail.mt_note',
            )
            return False
        result_type = self._reserva_tipo_resultado_correo()
        template_xmlid = {
            'approved': 'sat.mail_template_reserva_aprobada',
            'rejected': 'sat.mail_template_reserva_rechazada',
            'partial': 'sat.mail_template_reserva_parcial',
        }[result_type]
        sent = self._reserva_enviar_template(template_xmlid, email)
        if sent:
            self.message_post(
                body=_(
                    'Resultado de la solicitud enviado por correo a %s.'
                ) % email,
                subtype_xmlid='mail.mt_note',
            )
        return sent

    def action_enviar_gerencia(self):
        for record in self:
            if record.state != 'draft':
                continue

            if not record.line_ids:
                raise ValidationError(
                    _('Debe incluir al menos una máquina.')
                )

            # Antes de cambiar el estado, validar que exista al menos un destinatario autorizado.
            if not record._reserva_emails_autorizados():
                raise ValidationError(
                    _(
                        'No hay usuarios activos con correo en el grupo "Autorizados Reservas Comerciales". '
                        'Configure al menos un usuario autorizado con dirección de correo antes de enviar la solicitud.'
                    )
                )

            pending_lines = record.line_ids.filtered(lambda item: item.resultado == 'pending')
            for line in pending_lines:
                machine = line.maquina_id
                if machine.estado_ventas_id == 'entregada':
                    raise ValidationError(
                        _('La máquina %s ya está entregada y no puede enviarse a autorización.')
                        % (machine.serie_id or machine.display_name)
                    )
                if (
                    machine.reserva_solicitud_pendiente_id
                    and machine.reserva_solicitud_pendiente_id != record
                ):
                    raise ValidationError(
                        _('La máquina %(serie)s ya tiene la solicitud pendiente %(solicitud)s.')
                        % {
                            'serie': machine.serie_id or machine.display_name,
                            'solicitud': machine.reserva_solicitud_pendiente_id.display_name,
                        }
                    )

            record.with_context(
                sat_reserva_internal_request_write=True,
            ).write({'state': 'pending'})

            for line in pending_lines:
                machine = line.maquina_id
                machine.with_context(
                    sat_reserva_internal_write=True,
                ).write({
                    'reserva_solicitud_pendiente_id': record.id,
                })

                machine._reserva_crear_historial(
                    tipo_evento='solicitud',
                    cliente=record.cliente_id or machine.reserva_cliente_id or machine.cliente_id,
                    asesora=record.asesora_destino_id or machine.reserva_asesora_id,
                    solicitud=record,
                    fecha_anterior=machine.reserva_fecha_limite,
                    motivo=dict(record._fields['motivo'].selection).get(record.motivo, record.motivo),
                    observacion=record.detalle_motivo,
                )

            record._reserva_notificar_gerencia()

        return True

    def action_cancelar(self):
        for record in self:
            if record.state not in ('draft', 'pending', 'partial'):
                raise ValidationError(
                    _('Esta solicitud ya fue procesada y no puede cancelarse.')
                )

            if (
                record.solicitante_id != self.env.user
                and not record._reserva_usuario_es_gerencia()
            ):
                raise AccessError(
                    _('Solo el solicitante o gerencia pueden cancelar esta solicitud.')
                )

            pending_lines = record.line_ids.filtered(lambda line: line.resultado == 'pending')

            for line in pending_lines:
                machine = line.maquina_id

                if machine.reserva_solicitud_pendiente_id == record:
                    machine.with_context(
                        sat_reserva_internal_write=True,
                    ).write({
                        'reserva_solicitud_pendiente_id': False,
                    })

                line.with_context(
                    sat_reserva_internal_line_write=True,
                ).write({
                    'resultado': 'cancelled',
                    'seleccionada': False,
                })

                machine._reserva_crear_historial(
                    tipo_evento='cancelacion',
                    cliente=machine.reserva_cliente_id or machine.cliente_id,
                    asesora=machine.reserva_asesora_id,
                    solicitud=record,
                    fecha_anterior=machine.reserva_fecha_limite,
                    motivo='Solicitud cancelada',
                    observacion=record.detalle_motivo,
                )

            record.with_context(
                sat_reserva_internal_request_write=True,
            ).write({'state': 'cancelled'})

        return True

    def action_seleccionar_pendientes(self):
        self._reserva_exigir_gerencia()

        for record in self:
            record.line_ids.filtered(
                lambda line: line.resultado == 'pending'
            ).with_context(
                sat_reserva_internal_line_write=True,
            ).write({
                'seleccionada': True,
            })

        return True

    def action_quitar_seleccion(self):
        self._reserva_exigir_gerencia()

        for record in self:
            record.line_ids.with_context(
                sat_reserva_internal_line_write=True,
            ).write({
                'seleccionada': False,
            })

        return True

    def _get_lineas_seleccionadas(self, resultados=None):
        self.ensure_one()

        resultados = resultados or ['pending']

        lines = self.line_ids.filtered(
            lambda line:
                line.seleccionada
                and line.resultado in resultados
        )

        if not lines:
            raise ValidationError(
                _('No hay máquinas seleccionadas para procesar.')
            )

        return lines

    def _get_plazo_aprobado(self):
        self.ensure_one()

        modalidad = self.modalidad_aprobacion or self.modalidad_solicitada
        if self.tipo_solicitud == 'cambiar_cliente' and not modalidad:
            modalidad = 'mantener'

        if modalidad == 'fecha':
            fecha = self.fecha_aprobada or self.fecha_solicitada

            if not fecha:
                raise ValidationError(
                    _('Gerencia debe indicar la fecha aprobada.')
                )

            return {
                'modalidad': 'fecha',
                'fecha': fecha,
                'dias': 0,
            }

        if modalidad == 'mantener':
            return {
                'modalidad': 'mantener',
                'fecha': False,
                'dias': 0,
            }

        if modalidad == 'dias':
            dias = self.dias_aprobados or self.dias_solicitados

            if not dias or dias <= 0:
                raise ValidationError(
                    _('Gerencia debe indicar una cantidad de días mayor a cero.')
                )

            return {
                'modalidad': 'dias',
                'fecha': False,
                'dias': dias,
            }

        return {
            'modalidad': False,
            'fecha': False,
            'dias': 0,
        }

    def _calcular_fecha_para_maquina(self, machine):
        self.ensure_one()
        machine.ensure_one()

        if self.tipo_solicitud in ('liberar', 'cambiar_asesora'):
            return machine.reserva_fecha_limite

        plazo = self._get_plazo_aprobado()
        today = fields.Date.context_today(self)

        if plazo['modalidad'] == 'mantener':
            if not machine.reserva_fecha_limite:
                raise ValidationError(
                    _('La máquina %s no tiene un vencimiento vigente que conservar.')
                    % (machine.serie_id or machine.display_name)
                )
            result = machine.reserva_fecha_limite

        elif plazo['modalidad'] == 'fecha':
            result = plazo['fecha']

        elif self.tipo_solicitud == 'extender':
            base = machine.reserva_fecha_limite or today
            if base < today:
                base = today
            result = machine._reserva_sumar_dias_comerciales(base, plazo['dias'])

        elif self.tipo_solicitud == 'reducir':
            if not machine.reserva_fecha_limite:
                raise ValidationError(
                    _(
                        'La máquina %(serie)s no tiene vencimiento que reducir.'
                    )
                    % {
                        'serie': machine.serie_id or machine.display_name,
                    }
                )

            result = machine._reserva_restar_dias_comerciales(machine.reserva_fecha_limite, plazo['dias'])

            if result < today:
                result = today

        else:
            result = machine._reserva_sumar_dias_comerciales(today, plazo['dias'])

        if result and result < today:
            raise ValidationError(
                _('La fecha resultante no puede ser anterior a hoy.')
            )

        return result

    def _motivo_es_confirmacion(self):
        self.ensure_one()

        return self.motivo in (
            'pago',
            'adelanto',
            'confirmacion',
            'orden_compra',
        )

    def action_aprobar_seleccionadas(self):
        self._reserva_exigir_gerencia()

        for request in self:
            if request.state not in ('pending', 'partial'):
                raise ValidationError(
                    _('Solo se pueden aprobar solicitudes pendientes.')
                )

            lines = request._get_lineas_seleccionadas(['pending'])

            for line in lines:
                machine = line.maquina_id

                if machine.estado_ventas_id == 'entregada':
                    line.with_context(sat_reserva_internal_line_write=True).write({
                        'resultado': 'done',
                        'seleccionada': False,
                        'comentario_gerencia': 'La máquina ya estaba entregada.',
                    })

                    if machine.reserva_solicitud_pendiente_id == request:
                        machine.with_context(
                            sat_reserva_internal_write=True,
                        ).write({
                            'reserva_solicitud_pendiente_id': False,
                        })
                    continue

                if request.tipo_solicitud == 'liberar':
                    machine._reserva_liberar(
                        tipo='manual',
                        motivo=request.comentario_gerencia or request.detalle_motivo,
                        solicitud=request,
                    )
                    line.with_context(sat_reserva_internal_line_write=True).write({
                        'resultado': 'released',
                        'seleccionada': False,
                    })
                    continue

                fecha_nueva = request._calcular_fecha_para_maquina(machine)

                if request.tipo_solicitud == 'cambiar_asesora':
                    new_advisor = request.asesora_destino_id

                    machine._reserva_cambiar_asesora_autorizada(
                        new_advisor,
                        solicitud=request,
                        observacion=request.comentario_gerencia or request.detalle_motivo,
                    )

                    line.with_context(sat_reserva_internal_line_write=True).write({
                        'resultado': 'approved',
                        'seleccionada': False,
                        'fecha_aprobada': machine.reserva_fecha_limite,
                    })
                    continue

                new_client = (
                    request.cliente_id
                    if request.tipo_solicitud in ('reservar', 'cambiar_cliente')
                    else machine.reserva_cliente_id or machine.cliente_id or request.cliente_id
                )

                new_advisor = (
                    request.asesora_destino_id
                    or machine.reserva_asesora_id
                    or machine._reserva_resolver_asesora_cliente(new_client)
                    or request.solicitante_id
                )

                machine._reserva_aplicar_autorizacion(
                    cliente=new_client,
                    asesora=new_advisor,
                    fecha_limite=fecha_nueva,
                    confirmada=request._motivo_es_confirmacion(),
                    solicitud=request,
                    motivo=dict(request._fields['motivo'].selection).get(request.motivo, request.motivo),
                    observacion=request.comentario_gerencia or request.detalle_motivo,
                    cambiar_cliente=request.tipo_solicitud in ('reservar', 'cambiar_cliente'),
                )

                line.with_context(sat_reserva_internal_line_write=True).write({
                    'resultado': 'approved',
                    'seleccionada': False,
                    'fecha_aprobada': fecha_nueva,
                })

            request.write({
                'procesado_por_id': self.env.user.id,
                'fecha_procesamiento': fields.Datetime.now(),
            })
            request._actualizar_estado_solicitud()
            request._reserva_notificar_solicitante_resultado()

        return True

    def action_rechazar_seleccionadas(self):
        self._reserva_exigir_gerencia()

        for request in self:
            if request.state not in ('pending', 'partial'):
                raise ValidationError(
                    _('Solo se pueden rechazar solicitudes pendientes.')
                )

            lines = request._get_lineas_seleccionadas(['pending'])

            for line in lines:
                machine = line.maquina_id

                line.with_context(sat_reserva_internal_line_write=True).write({
                    'resultado': 'rejected',
                    'seleccionada': False,
                    'comentario_gerencia': request.comentario_gerencia,
                })

                if machine.reserva_solicitud_pendiente_id == request:
                    machine.with_context(
                        sat_reserva_internal_write=True,
                    ).write({
                        'reserva_solicitud_pendiente_id': False,
                    })

                machine._reserva_crear_historial(
                    tipo_evento='rechazo',
                    cliente=machine.reserva_cliente_id or machine.cliente_id,
                    asesora=machine.reserva_asesora_id,
                    solicitud=request,
                    fecha_anterior=machine.reserva_fecha_limite,
                    motivo='Solicitud rechazada por gerencia',
                    observacion=request.comentario_gerencia or request.detalle_motivo,
                )

            request.write({
                'procesado_por_id': self.env.user.id,
                'fecha_procesamiento': fields.Datetime.now(),
            })
            request._actualizar_estado_solicitud()
            request._reserva_notificar_solicitante_resultado()

        return True

    def _actualizar_estado_solicitud(self):
        for record in self:
            lines = record.line_ids

            if not lines:
                continue

            pending = lines.filtered(lambda line: line.resultado == 'pending')
            approved = lines.filtered(lambda line: line.resultado == 'approved')
            rejected = lines.filtered(lambda line: line.resultado == 'rejected')
            released = lines.filtered(lambda line: line.resultado == 'released')
            cancelled = lines.filtered(lambda line: line.resultado == 'cancelled')
            done = lines.filtered(lambda line: line.resultado == 'done')

            if pending:
                new_state = (
                    'partial'
                    if approved or rejected or released or cancelled or done
                    else 'pending'
                )
            elif approved and not rejected and not released and not cancelled:
                new_state = 'approved'
            elif rejected and not approved and not released:
                new_state = 'rejected'
            else:
                new_state = 'done'

            if record.state != new_state:
                record.with_context(
                    sat_reserva_internal_request_write=True,
                ).write({'state': new_state})


class SatReservaSolicitudLinea(models.Model):
    _name = 'sat.reserva.solicitud.linea'
    _description = 'Máquina de solicitud de autorización'
    _order = 'id'

    solicitud_id = fields.Many2one(
        'sat.reserva.solicitud',
        string='Solicitud',
        required=True,
        ondelete='cascade',
        index=True,
    )

    maquina_id = fields.Many2one(
        'sat.sat',
        string='Máquina',
        required=True,
        ondelete='cascade',
        index=True,
    )

    seleccionada = fields.Boolean(
        string='Aplicar',
        default=True,
    )

    resultado = fields.Selection(
        [
            ('pending', 'Pendiente'),
            ('approved', 'Aprobada'),
            ('rejected', 'Rechazada'),
            ('released', 'Liberada'),
            ('done', 'Finalizada'),
            ('cancelled', 'Cancelada'),
        ],
        string='Resultado',
        default='pending',
        readonly=True,
        index=True,
    )

    serie = fields.Char(
        related='maquina_id.serie_id',
        string='Serie',
        readonly=True,
    )

    importacion = fields.Char(
        related='maquina_id.importacion',
        string='Importación',
        readonly=True,
    )

    cliente_actual_id = fields.Many2one(
        'res.partner',
        string='Cliente actual',
        readonly=True,
    )

    asesora_actual_id = fields.Many2one(
        'res.users',
        string='Asesora actual',
        readonly=True,
    )

    estado_reserva_anterior = fields.Selection(
        [
            ('libre', 'Libre'),
            ('separada', 'Separada'),
            ('especial', 'Reserva especial'),
            ('confirmada', 'Confirmada'),
            ('entregada', 'Entregada'),
        ],
        string='Estado anterior',
        readonly=True,
    )

    fecha_limite_anterior = fields.Date(
        string='Vencimiento anterior',
        readonly=True,
    )

    fecha_aprobada = fields.Date(
        string='Vencimiento aprobado',
        readonly=True,
    )

    comentario_gerencia = fields.Char(
        string='Comentario',
    )

    _sql_constraints = [
        (
            'solicitud_maquina_unique',
            'unique(solicitud_id, maquina_id)',
            'La máquina ya está incluida en esta solicitud.',
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('sat_reserva_internal_line_write'):
            for vals in vals_list:
                request = self.env['sat.reserva.solicitud'].browse(vals.get('solicitud_id')).exists()
                if request and (
                    request.solicitante_id != self.env.user
                    and not request._reserva_usuario_es_gerencia()
                ):
                    raise AccessError(
                        _('No puede agregar máquinas a una solicitud de otro usuario.')
                    )
        return super().create(vals_list)

    def write(self, vals):
        protected = {'resultado', 'seleccionada', 'fecha_aprobada', 'comentario_gerencia'}
        if (
            protected.intersection(vals or {})
            and not self.env.context.get('sat_reserva_internal_line_write')
        ):
            authorized = all(
                line.solicitud_id._reserva_usuario_es_gerencia()
                for line in self
            )
            if not authorized:
                raise AccessError(
                    _('Solo un usuario autorizado puede procesar líneas de una solicitud.')
                )
        return super().write(vals)

    def unlink(self):
        raise ValidationError(
            _('Las líneas de solicitudes no se eliminan para conservar la trazabilidad.')
        )


# =============================================================================
# HISTORIAL
# =============================================================================

class SatReservaHistorial(models.Model):
    _name = 'sat.reserva.historial'
    _description = 'Historial de separación comercial'
    _order = 'fecha_evento desc, id desc'

    maquina_id = fields.Many2one(
        'sat.sat',
        string='Máquina',
        required=True,
        ondelete='cascade',
        index=True,
    )

    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        index=True,
    )

    asesora_id = fields.Many2one(
        'res.users',
        string='Asesora',
        index=True,
    )

    solicitud_id = fields.Many2one(
        'sat.reserva.solicitud',
        string='Solicitud',
        ondelete='set null',
        index=True,
    )

    regla_id = fields.Many2one(
        'sat.reserva.regla',
        string='Regla aplicada',
        ondelete='set null',
    )

    tipo_evento = fields.Selection(
        [
            ('asignacion_asesora', 'Asignación de asesora'),
            ('separacion', 'Separación'),
            ('cliente_asignado', 'Cliente asignado'),
            ('cambio_cliente', 'Cambio de cliente'),
            ('cambio_asesora', 'Cambio de asesora'),
            ('solicitud', 'Solicitud enviada'),
            ('aprobacion', 'Aprobación gerencial'),
            ('rechazo', 'Rechazo'),
            ('extension', 'Extensión'),
            ('reduccion', 'Reducción'),
            ('liberacion_manual', 'Liberación manual'),
            ('liberacion_automatica', 'Liberación automática'),
            ('entregada', 'Entregada'),
            ('cancelacion', 'Cancelación'),
        ],
        string='Evento',
        required=True,
        index=True,
    )

    fecha_evento = fields.Datetime(
        string='Fecha',
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    fecha_base = fields.Date(
        string='Fecha base del ciclo',
    )

    fecha_vencimiento_anterior = fields.Date(
        string='Vencimiento anterior',
    )

    fecha_vencimiento_nueva = fields.Date(
        string='Nuevo vencimiento',
    )

    ciclo = fields.Integer(
        string='Ciclo',
    )

    usuario_id = fields.Many2one(
        'res.users',
        string='Usuario que ejecutó',
        default=lambda self: self.env.user,
    )

    motivo = fields.Char(
        string='Motivo',
    )

    observacion = fields.Text(
        string='Observación',
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('sat_reserva_historial_internal'):
            user = self.env.user
            group = self.env.ref(
                'sat.group_reserva_comercial_autorizado',
                raise_if_not_found=False,
            )
            if not (self.env.is_superuser() or user.has_group('base.group_system') or (group and user in group.users)):
                raise AccessError(_('El historial comercial solo puede generarse desde el flujo de reservas.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.is_superuser():
            raise AccessError(_('El historial comercial es inmutable.'))
        return super().write(vals)

    def unlink(self):
        raise ValidationError(_('El historial comercial no se elimina.'))


# =============================================================================
# HERENCIA DE SAT.SAT
# =============================================================================

class SatSatReservaComercial(models.Model):
    _inherit = 'sat.sat'

    def _reserva_usuario_es_gerencia(self):
        user = self.env.user
        if self.env.is_superuser() or user.has_group('base.group_system'):
            return True
        group = self.env.ref(
            'sat.group_reserva_comercial_autorizado',
            raise_if_not_found=False,
        )
        return bool(group and user in group.users)

    def _reserva_exigir_gerencia(self):
        if not self._reserva_usuario_es_gerencia():
            raise AccessError(
                _('Esta operación requiere autorización de reservas comerciales.')
            )
        return True

    reserva_estado = fields.Selection(
        [
            ('libre', 'Libre'),
            ('separada', 'Separada'),
            ('especial', 'Reserva especial'),
            ('confirmada', 'Confirmada'),
            ('entregada', 'Entregada'),
        ],
        string='Estado comercial',
        default='libre',
        tracking=True,
        copy=False,
        index=True,
    )

    reserva_asesora_id = fields.Many2one(
        'res.users',
        string='Asesora que tiene la máquina',
        tracking=True,
        copy=False,
        index=True,
    )

    reserva_cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente de la reserva',
        tracking=True,
        copy=False,
        index=True,
    )

    reserva_inicio = fields.Datetime(
        string='Inicio de la separación',
        tracking=True,
        copy=False,
    )

    reserva_fecha_base = fields.Date(
        string='Fecha base del ciclo',
        tracking=True,
        copy=False,
        help=(
            'En el primer ciclo corresponde a la descarga. '
            'Después de una liberación corresponde a la nueva asignación.'
        ),
    )

    reserva_fecha_limite = fields.Date(
        string='Vencimiento de separación',
        tracking=True,
        copy=False,
        index=True,
    )

    reserva_dias = fields.Integer(
        string='Días otorgados',
        tracking=True,
        copy=False,
    )

    reserva_ciclo = fields.Integer(
        string='Ciclo comercial',
        default=0,
        readonly=True,
        copy=False,
        index=True,
    )

    reserva_origen = fields.Selection(
        [
            ('general', 'Regla general'),
            ('cliente', 'Regla del cliente'),
            ('cliente_importacion', 'Cliente + importación'),
            ('gerencia', 'Autorización de gerencia'),
        ],
        string='Origen del plazo',
        tracking=True,
        copy=False,
    )

    reserva_regla_id = fields.Many2one(
        'sat.reserva.regla',
        string='Regla aplicada',
        tracking=True,
        copy=False,
        ondelete='set null',
    )

    reserva_solicitud_id = fields.Many2one(
        'sat.reserva.solicitud',
        string='Autorización vigente',
        tracking=True,
        copy=False,
        ondelete='set null',
    )

    reserva_solicitud_pendiente_id = fields.Many2one(
        'sat.reserva.solicitud',
        string='Solicitud pendiente',
        tracking=True,
        copy=False,
        ondelete='set null',
    )

    reserva_dias_restantes = fields.Integer(
        string='Días restantes',
        compute='_compute_reserva_dias_restantes',
    )

    reserva_vencida = fields.Boolean(
        string='Reserva vencida',
        compute='_compute_reserva_dias_restantes',
    )

    reserva_ultimo_aviso_fecha = fields.Date(
        string='Último aviso de vencimiento',
        copy=False,
        readonly=True,
    )

    reserva_ultimo_aviso_dias = fields.Integer(
        string='Días restantes del último aviso',
        copy=False,
        readonly=True,
    )

    reserva_historial_ids = fields.One2many(
        'sat.reserva.historial',
        'maquina_id',
        string='Historial comercial',
    )

    @api.depends('reserva_fecha_limite', 'reserva_estado')
    def _compute_reserva_dias_restantes(self):
        today = fields.Date.context_today(self)

        for record in self:
            if (
                not record.reserva_fecha_limite
                or record.reserva_estado in ('libre', 'entregada')
            ):
                record.reserva_dias_restantes = 0
                record.reserva_vencida = False
                continue

            diff = (record.reserva_fecha_limite - today).days
            record.reserva_dias_restantes = diff
            record.reserva_vencida = diff < 0

    # -------------------------------------------------------------------------
    # Helpers de asesora
    # -------------------------------------------------------------------------

    def _reserva_resolver_asesora_cliente(self, cliente):
        self.ensure_one()

        if not cliente:
            return self.env['res.users']

        field = cliente._fields.get('asesora_id')

        if not field:
            return self.env['res.users']

        advisor = cliente.asesora_id

        if not advisor:
            return self.env['res.users']

        if field.type == 'many2one' and field.comodel_name == 'res.users':
            return advisor

        if field.type == 'many2one':
            if 'user_id' in advisor._fields and advisor.user_id:
                return advisor.user_id

            if 'user_ids' in advisor._fields and advisor.user_ids:
                return advisor.user_ids[:1]

        return self.env['res.users']

    # -------------------------------------------------------------------------
    # Regla aplicable
    # -------------------------------------------------------------------------

    def _reserva_buscar_regla(self, cliente=False, fecha=False):
        self.ensure_one()

        Rule = self.env['sat.reserva.regla']
        fecha = fecha or fields.Date.context_today(self)

        valid_domain = [
            ('active', '=', True),
            '|',
            ('fecha_inicio', '=', False),
            ('fecha_inicio', '<=', fecha),
            '|',
            ('fecha_fin', '=', False),
            ('fecha_fin', '>=', fecha),
        ]

        if cliente and self.importacion:
            rule = Rule.search(
                valid_domain
                + [
                    ('tipo_aplicacion', '=', 'cliente_importacion'),
                    ('cliente_id', '=', cliente.id),
                    ('importacion', '=', self.importacion),
                ],
                order='prioridad desc, id desc',
                limit=1,
            )
            if rule:
                return rule

        if cliente:
            rule = Rule.search(
                valid_domain
                + [
                    ('tipo_aplicacion', '=', 'cliente'),
                    ('cliente_id', '=', cliente.id),
                ],
                order='prioridad desc, id desc',
                limit=1,
            )
            if rule:
                return rule

        return Rule.search(
            valid_domain + [('tipo_aplicacion', '=', 'general')],
            order='prioridad desc, id desc',
            limit=1,
        )

    def _reserva_obtener_fecha_base(self):
        self.ensure_one()

        if self.reserva_fecha_base:
            return self.reserva_fecha_base

        today = fields.Date.context_today(self)

        if self.reserva_ciclo == 0:
            source = self.ingreso_fecha or self.create_date
            return fields.Date.to_date(source) if source else today

        return today

    # -------------------------------------------------------------------------
    # Calendario comercial compartido
    # -------------------------------------------------------------------------

    def _reserva_fecha_es_dia_comercial(self, fecha):
        """
        Para reservas comerciales:
        - lunes a sábado cuentan como día completo;
        - domingo no cuenta;
        - feriado o cierre manual activo en whatsapp.calendar.event no cuenta.
        """
        self.ensure_one()

        if not fecha:
            return False

        fecha = fields.Date.to_date(fecha)

        if fecha.weekday() == 6:
            return False

        calendario = self.env['whatsapp.calendar.event']
        return not calendario.is_closed_date(fecha)

    def _reserva_sumar_dias_comerciales(self, fecha_base, dias):
        """Suma días comerciales sin consumir la fecha base."""
        self.ensure_one()

        fecha = fields.Date.to_date(fecha_base)
        dias = int(dias or 0)

        if not fecha or dias <= 0:
            return fecha

        acumulados = 0
        cursor = fecha

        while acumulados < dias:
            cursor += timedelta(days=1)

            if self._reserva_fecha_es_dia_comercial(cursor):
                acumulados += 1

        return cursor

    def _reserva_restar_dias_comerciales(self, fecha_base, dias):
        """Resta días comerciales sin consumir la fecha base."""
        self.ensure_one()

        fecha = fields.Date.to_date(fecha_base)
        dias = int(dias or 0)

        if not fecha or dias <= 0:
            return fecha

        acumulados = 0
        cursor = fecha

        while acumulados < dias:
            cursor -= timedelta(days=1)

            if self._reserva_fecha_es_dia_comercial(cursor):
                acumulados += 1

        return cursor

    def _reserva_calcular_plazo(self, cliente=False):
        self.ensure_one()

        base = self._reserva_obtener_fecha_base()
        rule = self._reserva_buscar_regla(cliente=cliente, fecha=base)
        days = rule.dias_separacion if rule else 6

        return {
            'fecha_base': base,
            'fecha_limite': self._reserva_sumar_dias_comerciales(base, days),
            'dias': days,
            'regla': rule,
            'origen': rule.tipo_aplicacion if rule else 'general',
        }

    def _reserva_esta_vigente(self):
        self.ensure_one()

        if self.reserva_estado not in ('separada', 'especial', 'confirmada'):
            return False

        if not self.reserva_fecha_limite:
            return False

        today = fields.Date.context_today(self)
        return self.reserva_fecha_limite > today

    # -------------------------------------------------------------------------
    # Historial
    # -------------------------------------------------------------------------

    def _reserva_crear_historial(
        self,
        tipo_evento,
        cliente=False,
        asesora=False,
        regla=False,
        solicitud=False,
        fecha_base=False,
        fecha_anterior=False,
        fecha_nueva=False,
        motivo=False,
        observacion=False,
    ):
        self.ensure_one()

        return self.env['sat.reserva.historial'].with_context(
            sat_reserva_historial_internal=True,
        ).create({
            'maquina_id': self.id,
            'cliente_id': (
                (cliente or self.reserva_cliente_id or self.cliente_id).id
                if (cliente or self.reserva_cliente_id or self.cliente_id)
                else False
            ),
            'asesora_id': (
                (asesora or self.reserva_asesora_id).id
                if (asesora or self.reserva_asesora_id)
                else False
            ),
            'solicitud_id': solicitud.id if solicitud else False,
            'regla_id': regla.id if regla else False,
            'tipo_evento': tipo_evento,
            'fecha_base': fecha_base or self.reserva_fecha_base,
            'fecha_vencimiento_anterior': fecha_anterior,
            'fecha_vencimiento_nueva': fecha_nueva,
            'ciclo': self.reserva_ciclo,
            'usuario_id': self.env.user.id,
            'motivo': motivo,
            'observacion': observacion,
        })

    # -------------------------------------------------------------------------
    # Asignación normal a asesora
    # -------------------------------------------------------------------------

    def _reserva_asignar_asesora(self, asesora, cliente=False):
        self.ensure_one()

        if not asesora:
            raise ValidationError(
                _('Debe indicar una asesora.')
            )

        if self.estado_ventas_id == 'entregada':
            raise ValidationError(
                _('No puede separar una máquina ya entregada.')
            )

        if self._reserva_esta_vigente() and self.reserva_asesora_id:
            if self.reserva_asesora_id != asesora:
                raise ValidationError(
                    _(
                        'La máquina %(serie)s ya está separada para %(asesora)s hasta %(fecha)s.'
                    )
                    % {
                        'serie': self.serie_id or self.display_name,
                        'asesora': self.reserva_asesora_id.name,
                        'fecha': self.reserva_fecha_limite,
                    }
                )
            return True

        base = self._reserva_obtener_fecha_base()

        self.with_context(
            sat_reserva_internal_write=True,
        ).write({
            'reserva_asesora_id': asesora.id,
            'reserva_cliente_id': cliente.id if cliente else False,
            'reserva_inicio': fields.Datetime.now(),
            'reserva_fecha_base': base,
            'reserva_estado': 'separada',
            'reserva_ultimo_aviso_fecha': False,
            'reserva_ultimo_aviso_dias': 0,
        })

        plan = self._reserva_calcular_plazo(cliente=cliente)

        self.with_context(
            sat_reserva_internal_write=True,
        ).write({
            'reserva_fecha_limite': plan['fecha_limite'],
            'reserva_dias': plan['dias'],
            'reserva_origen': plan['origen'],
            'reserva_regla_id': plan['regla'].id if plan['regla'] else False,
            'reserva_solicitud_id': False,
        })

        self._reserva_crear_historial(
            tipo_evento='asignacion_asesora',
            cliente=cliente,
            asesora=asesora,
            regla=plan['regla'],
            fecha_base=plan['fecha_base'],
            fecha_nueva=plan['fecha_limite'],
            motivo='Asignación comercial',
        )

        today = fields.Date.context_today(self)

        if plan['fecha_limite'] < today:
            self._reserva_liberar(
                tipo='automatica',
                motivo='El plazo desde la fecha base ya había vencido.',
            )

        return True

    # -------------------------------------------------------------------------
    # Cliente asignado dentro del mismo ciclo
    # -------------------------------------------------------------------------

    def _reserva_aplicar_cliente_en_ciclo(self, cliente, asesora=False):
        self.ensure_one()

        if not cliente:
            return False

        advisor = (
            asesora
            or self.reserva_asesora_id
            or self._reserva_resolver_asesora_cliente(cliente)
            or self.env.user
        )

        if self.reserva_estado == 'libre':
            return self._reserva_asignar_asesora(
                advisor,
                cliente=cliente,
            )

        previous_deadline = self.reserva_fecha_limite

        plan = self._reserva_calcular_plazo(
            cliente=cliente,
        )

        self.with_context(
            sat_reserva_internal_write=True,
        ).write({
            'reserva_asesora_id': advisor.id,
            'reserva_cliente_id': cliente.id,
            'reserva_fecha_limite': plan['fecha_limite'],
            'reserva_dias': plan['dias'],
            'reserva_origen': plan['origen'],
            'reserva_regla_id': plan['regla'].id if plan['regla'] else False,
            'reserva_estado': 'separada',
        })

        self._reserva_crear_historial(
            tipo_evento='cliente_asignado',
            cliente=cliente,
            asesora=advisor,
            regla=plan['regla'],
            fecha_base=plan['fecha_base'],
            fecha_anterior=previous_deadline,
            fecha_nueva=plan['fecha_limite'],
            motivo='Cliente asignado dentro del mismo ciclo comercial',
        )

        today = fields.Date.context_today(self)

        if plan['fecha_limite'] < today:
            self._reserva_liberar(
                tipo='automatica',
                motivo='La regla aplicable al cliente ya se encontraba vencida.',
            )

        return True

    # -------------------------------------------------------------------------
    # Autorización de gerencia
    # -------------------------------------------------------------------------

    def _reserva_aplicar_autorizacion(
        self,
        cliente,
        asesora,
        fecha_limite,
        confirmada=False,
        solicitud=False,
        motivo=False,
        observacion=False,
        cambiar_cliente=False,
    ):
        self.ensure_one()
        self._reserva_exigir_gerencia()


        if not fecha_limite:
            raise ValidationError(
                _('Gerencia debe indicar una fecha límite.')
            )

        today = fields.Date.context_today(self)

        if fecha_limite < today:
            raise ValidationError(
                _('La fecha autorizada no puede ser anterior a hoy.')
            )

        previous_client = self.cliente_id
        previous_deadline = self.reserva_fecha_limite
        previous_advisor = self.reserva_asesora_id

        values = {
            'reserva_estado': 'confirmada' if confirmada else 'especial',
            'reserva_asesora_id': asesora.id if asesora else False,
            'reserva_cliente_id': cliente.id if cliente else False,
            'reserva_fecha_limite': fecha_limite,
            'reserva_dias': max((fecha_limite - today).days, 0),
            'reserva_origen': 'gerencia',
            'reserva_regla_id': False,
            'reserva_solicitud_id': solicitud.id if solicitud else False,
            'reserva_solicitud_pendiente_id': False,
            'reserva_ultimo_aviso_fecha': False,
            'reserva_ultimo_aviso_dias': 0,
        }

        if not self.reserva_inicio:
            values['reserva_inicio'] = fields.Datetime.now()

        if not self.reserva_fecha_base:
            values['reserva_fecha_base'] = self._reserva_obtener_fecha_base()

        self.with_context(
            sat_reserva_internal_write=True,
            sat_reserva_gerencia=True,
        ).write(values)

        if cambiar_cliente and self.cliente_id != cliente:
            self.with_context(
                sat_reserva_internal_write=True,
                sat_reserva_gerencia=True,
            ).write({
                'cliente_id': cliente.id if cliente else False,
            })

        event = 'aprobacion'

        if solicitud:
            if solicitud.tipo_solicitud == 'extender':
                event = 'extension'
            elif solicitud.tipo_solicitud == 'reducir':
                event = 'reduccion'
            elif solicitud.tipo_solicitud == 'cambiar_cliente':
                event = 'cambio_cliente'

        self._reserva_crear_historial(
            tipo_evento=event,
            cliente=cliente,
            asesora=asesora,
            solicitud=solicitud,
            fecha_anterior=previous_deadline,
            fecha_nueva=fecha_limite,
            motivo=motivo or 'Autorización de gerencia',
            observacion=observacion,
        )

        if cambiar_cliente and previous_client != cliente:
            self.message_post(
                body=_(
                    'Gerencia autorizó cambio de cliente.<br/>'
                    '<b>Cliente anterior:</b> %(anterior)s<br/>'
                    '<b>Cliente nuevo:</b> %(nuevo)s<br/>'
                    '<b>Válido hasta:</b> %(fecha)s'
                )
                % {
                    'anterior': previous_client.display_name if previous_client else 'Sin cliente',
                    'nuevo': cliente.display_name if cliente else 'Sin cliente',
                    'fecha': fecha_limite,
                },
                subtype_xmlid='mail.mt_note',
            )

        if previous_advisor != asesora:
            self.message_post(
                body=_(
                    'Asesora comercial de la reserva: %(asesora)s.'
                )
                % {
                    'asesora': asesora.name if asesora else 'Sin asesora',
                },
                subtype_xmlid='mail.mt_note',
            )

        return True

    def _reserva_cambiar_asesora_autorizada(
        self,
        asesora,
        solicitud=False,
        observacion=False,
    ):
        self.ensure_one()
        self._reserva_exigir_gerencia()


        if not asesora:
            raise ValidationError(
                _('Debe indicar la nueva asesora.')
            )

        previous = self.reserva_asesora_id

        self.with_context(
            sat_reserva_internal_write=True,
            sat_reserva_gerencia=True,
        ).write({
            'reserva_asesora_id': asesora.id,
            'reserva_solicitud_pendiente_id': False,
        })

        self._reserva_crear_historial(
            tipo_evento='cambio_asesora',
            cliente=self.reserva_cliente_id or self.cliente_id,
            asesora=asesora,
            solicitud=solicitud,
            fecha_anterior=self.reserva_fecha_limite,
            fecha_nueva=self.reserva_fecha_limite,
            motivo='Cambio de asesora autorizado por gerencia',
            observacion=(
                '%s%s'
                % (
                    ('Anterior: %s. ' % previous.name) if previous else '',
                    observacion or '',
                )
            ),
        )

        return True

    # -------------------------------------------------------------------------
    # Liberación
    # -------------------------------------------------------------------------

    def _reserva_liberar(
        self,
        tipo='automatica',
        motivo=False,
        solicitud=False,
    ):
        self.ensure_one()

        if tipo == 'manual':
            self._reserva_exigir_gerencia()

        if self.estado_ventas_id == 'entregada':
            return False

        previous_client = self.reserva_cliente_id or self.cliente_id
        previous_advisor = self.reserva_asesora_id
        previous_deadline = self.reserva_fecha_limite
        previous_rule = self.reserva_regla_id
        pending_request = self.reserva_solicitud_pendiente_id

        if pending_request:
            pending_lines = pending_request.line_ids.filtered(
                lambda line:
                    line.maquina_id == self
                    and line.resultado == 'pending'
            )

            if pending_lines:
                pending_lines.with_context(sat_reserva_internal_line_write=True).write({
                    'resultado': 'released',
                    'seleccionada': False,
                })

            pending_request._actualizar_estado_solicitud()

        self.with_context(
            sat_reserva_internal_write=True,
            sat_reserva_gerencia=True,
        ).write({
            'reserva_estado': 'libre',
            'reserva_asesora_id': False,
            'reserva_cliente_id': False,
            'reserva_inicio': False,
            'reserva_fecha_base': False,
            'reserva_fecha_limite': False,
            'reserva_dias': 0,
            'reserva_origen': False,
            'reserva_regla_id': False,
            'reserva_solicitud_id': False,
            'reserva_solicitud_pendiente_id': False,
            'reserva_ciclo': self.reserva_ciclo + 1,
            'cliente_id': False,
        })

        self._reserva_crear_historial(
            tipo_evento=(
                'liberacion_manual'
                if tipo == 'manual'
                else 'liberacion_automatica'
            ),
            cliente=previous_client,
            asesora=previous_advisor,
            regla=previous_rule,
            solicitud=solicitud,
            fecha_anterior=previous_deadline,
            motivo=motivo or 'Plazo de separación vencido',
        )

        self.message_post(
            body=_(
                'La máquina fue liberada.<br/>'
                '<b>Cliente anterior:</b> %(cliente)s<br/>'
                '<b>Asesora anterior:</b> %(asesora)s<br/>'
                '<b>Vencimiento:</b> %(fecha)s<br/>'
                '<b>Motivo:</b> %(motivo)s'
            )
            % {
                'cliente': previous_client.display_name if previous_client else 'Sin cliente',
                'asesora': previous_advisor.name if previous_advisor else 'Sin asesora',
                'fecha': previous_deadline or '',
                'motivo': motivo or 'Plazo vencido',
            },
            subtype_xmlid='mail.mt_note',
        )

        return True

    # -------------------------------------------------------------------------
    # Entrega
    # -------------------------------------------------------------------------

    def _reserva_cerrar_por_entrega(self):
        self.ensure_one()

        previous_client = self.reserva_cliente_id or self.cliente_id
        previous_advisor = self.reserva_asesora_id
        previous_deadline = self.reserva_fecha_limite
        previous_rule = self.reserva_regla_id
        pending_request = self.reserva_solicitud_pendiente_id

        if pending_request:
            pending_lines = pending_request.line_ids.filtered(
                lambda line:
                    line.maquina_id == self
                    and line.resultado == 'pending'
            )

            if pending_lines:
                pending_lines.with_context(sat_reserva_internal_line_write=True).write({
                    'resultado': 'done',
                    'seleccionada': False,
                })

            pending_request._actualizar_estado_solicitud()

        self.with_context(
            sat_reserva_internal_write=True,
        ).write({
            'reserva_estado': 'entregada',
            'reserva_cliente_id': previous_client.id if previous_client else False,
            'reserva_fecha_limite': False,
            'reserva_dias': 0,
            'reserva_origen': False,
            'reserva_regla_id': False,
            'reserva_solicitud_id': False,
            'reserva_solicitud_pendiente_id': False,
        })

        self._reserva_crear_historial(
            tipo_evento='entregada',
            cliente=previous_client,
            asesora=previous_advisor,
            regla=previous_rule,
            fecha_anterior=previous_deadline,
            motivo='Reserva cerrada por entrega de la máquina',
        )

        return True

    # -------------------------------------------------------------------------
    # Recalcular primer ciclo si recién se registra la descarga
    # -------------------------------------------------------------------------

    def _reserva_recalcular_por_ingreso(self):
        self.ensure_one()

        if (
            self.reserva_ciclo != 0
            or self.reserva_estado not in ('separada',)
            or not self.reserva_asesora_id
        ):
            return False

        base = (
            fields.Date.to_date(self.ingreso_fecha)
            if self.ingreso_fecha
            else self._reserva_obtener_fecha_base()
        )

        self.with_context(
            sat_reserva_internal_write=True,
        ).write({
            'reserva_fecha_base': base,
        })

        plan = self._reserva_calcular_plazo(
            cliente=self.reserva_cliente_id or self.cliente_id,
        )

        self.with_context(
            sat_reserva_internal_write=True,
        ).write({
            'reserva_fecha_limite': plan['fecha_limite'],
            'reserva_dias': plan['dias'],
            'reserva_origen': plan['origen'],
            'reserva_regla_id': plan['regla'].id if plan['regla'] else False,
        })

        if plan['fecha_limite'] < fields.Date.context_today(self):
            self._reserva_liberar(
                tipo='automatica',
                motivo='El plazo desde la fecha real de descarga ya venció.',
            )

        return True

    # -------------------------------------------------------------------------
    # Validaciones del write
    # -------------------------------------------------------------------------

    def _reserva_validar_cambio_cliente(self, nuevo_cliente_id):
        self.ensure_one()

        if (
            self.env.context.get('sat_reserva_internal_write')
            or self.env.context.get('sat_reserva_gerencia')
        ):
            return True

        old_client_id = self.cliente_id.id if self.cliente_id else False
        new_client_id = int(nuevo_cliente_id) if nuevo_cliente_id else False

        if old_client_id == new_client_id:
            return True

        if not self._reserva_esta_vigente():
            return True

        # Si aún no tenía cliente, solo la asesora dueña o gerencia puede colocarlo.
        if not old_client_id and new_client_id:
            if (
                self.reserva_asesora_id
                and self.reserva_asesora_id != self.env.user
                and not self._reserva_usuario_es_gerencia()
            ):
                raise ValidationError(
                    _(
                        'Esta máquina está asignada a %(asesora)s hasta %(fecha)s. '
                        'Otra asesora no puede colocarle cliente.'
                    )
                    % {
                        'asesora': self.reserva_asesora_id.name,
                        'fecha': self.reserva_fecha_limite,
                    }
                )
            return True

        raise ValidationError(
            _(
                'No puede cambiar ni retirar el cliente de la máquina %(serie)s '
                'porque la separación está vigente hasta %(fecha)s. '
                'Debe enviar una solicitud a gerencia.'
            )
            % {
                'serie': self.serie_id or self.display_name,
                'fecha': self.reserva_fecha_limite,
            }
        )

    def write(self, vals):
        vals = dict(vals or {})

        if self.env.context.get('sat_reserva_internal_write'):
            return super().write(vals)

        snapshot = {
            record.id: {
                'cliente_id': record.cliente_id.id if record.cliente_id else False,
                'estado_ventas_id': record.estado_ventas_id,
                'ingreso_fecha': record.ingreso_fecha,
            }
            for record in self
        }

        if 'cliente_id' in vals:
            for record in self:
                record._reserva_validar_cambio_cliente(
                    vals.get('cliente_id')
                )

        result = super().write(vals)

        for record in self:
            before = snapshot.get(record.id, {})

            # Entregada cierra toda política de reserva, pero conserva cliente.
            if (
                record.estado_ventas_id == 'entregada'
                and before.get('estado_ventas_id') != 'entregada'
            ):
                record._reserva_cerrar_por_entrega()
                continue

            # Si recién quedó registrada la fecha de descarga, corregir el ciclo inicial.
            if (
                'ingreso_fecha' in vals
                and record.ingreso_fecha
                and record.ingreso_fecha != before.get('ingreso_fecha')
            ):
                record._reserva_recalcular_por_ingreso()

            if 'cliente_id' not in vals:
                continue

            old_client_id = before.get('cliente_id')
            new_client = record.cliente_id

            # Cliente colocado por primera vez.
            if not old_client_id and new_client:
                advisor = (
                    record.reserva_asesora_id
                    or record._reserva_resolver_asesora_cliente(new_client)
                    or self.env.user
                )

                record._reserva_aplicar_cliente_en_ciclo(
                    new_client,
                    asesora=advisor,
                )

        return result

    # -------------------------------------------------------------------------
    # Acciones para los wizards
    # -------------------------------------------------------------------------

    def action_asignar_reserva_asesora(self):
        if not self:
            raise ValidationError(
                _('Debe seleccionar al menos una máquina.')
            )

        delivered = self.filtered(
            lambda record: record.estado_ventas_id == 'entregada'
        )

        if delivered:
            raise ValidationError(
                _(
                    'No puede incluir máquinas entregadas: %s'
                )
                % ', '.join(delivered.mapped('serie_id'))
            )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Asignar máquinas a ventas'),
            'res_model': 'sat.reserva.asignacion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_maquina_ids': [(6, 0, self.ids)],
            },
        }

    def action_solicitar_reserva_comercial(self):
        if not self:
            raise ValidationError(
                _('Debe seleccionar al menos una máquina.')
            )

        delivered = self.filtered(
            lambda record: record.estado_ventas_id == 'entregada'
        )

        if delivered:
            raise ValidationError(
                _(
                    'No puede incluir máquinas entregadas: %s'
                )
                % ', '.join(delivered.mapped('serie_id'))
            )

        with_pending = self.filtered(
            lambda record: record.reserva_solicitud_pendiente_id
        )

        if with_pending:
            raise ValidationError(
                _(
                    'Estas máquinas ya tienen una solicitud pendiente: %s'
                )
                % ', '.join(with_pending.mapped('serie_id'))
            )

        clients = self.mapped('cliente_id')
        default_client = clients.id if len(clients) == 1 else False

        advisors = self.mapped('reserva_asesora_id')
        default_advisor = advisors.id if len(advisors) == 1 else self.env.user.id

        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitar autorización comercial'),
            'res_model': 'sat.reserva.solicitud.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_maquina_ids': [(6, 0, self.ids)],
                'default_cliente_id': default_client,
                'default_asesora_destino_id': default_advisor,
            },
        }

    # -------------------------------------------------------------------------
    # Cron
    # -------------------------------------------------------------------------

    @api.model
    def _cron_notificar_reservas_por_vencer(self):
        today = fields.Date.context_today(self)
        machines = self.search([
            ('reserva_estado', 'in', ['separada', 'especial', 'confirmada']),
            ('reserva_fecha_limite', '!=', False),
            ('reserva_fecha_limite', '>', today),
            ('estado_ventas_id', '!=', 'entregada'),
        ])

        count = 0
        group = self.env.ref(
            'sat.group_reserva_comercial_autorizado',
            raise_if_not_found=False,
        )
        managers = group.users.filtered(lambda user: user.active) if group else self.env['res.users']
        activity_type = self.env.ref(
            'mail.mail_activity_data_todo',
            raise_if_not_found=False,
        )

        for machine in machines:
            days = (machine.reserva_fecha_limite - today).days
            if days not in (1, 2):
                continue
            if (
                machine.reserva_ultimo_aviso_fecha == today
                and machine.reserva_ultimo_aviso_dias == days
            ):
                continue

            recipients = (machine.reserva_asesora_id | managers).filtered(lambda user: user.active)
            body = _(
                'Reserva comercial próxima a vencer.<br/>'
                '<b>Serie:</b> %(serie)s<br/>'
                '<b>Cliente:</b> %(cliente)s<br/>'
                '<b>Asesora:</b> %(asesora)s<br/>'
                '<b>Fecha límite:</b> %(fecha)s<br/>'
                '<b>Días restantes:</b> %(dias)s'
            ) % {
                'serie': machine.serie_id or machine.display_name,
                'cliente': (machine.reserva_cliente_id or machine.cliente_id).display_name if (machine.reserva_cliente_id or machine.cliente_id) else 'Sin cliente',
                'asesora': machine.reserva_asesora_id.name if machine.reserva_asesora_id else 'Sin asesora',
                'fecha': machine.reserva_fecha_limite,
                'dias': days,
            }
            machine.message_post(
                body=body,
                partner_ids=list(set(recipients.mapped('partner_id').ids)),
                subtype_xmlid='mail.mt_note',
            )

            if activity_type:
                for user in recipients:
                    existing = self.env['mail.activity'].search([
                        ('res_model_id', '=', self.env['ir.model']._get_id('sat.sat')),
                        ('res_id', '=', machine.id),
                        ('activity_type_id', '=', activity_type.id),
                        ('user_id', '=', user.id),
                        ('summary', '=', 'Reserva comercial por vencer'),
                    ], limit=1)
                    vals = {
                        'activity_type_id': activity_type.id,
                        'summary': 'Reserva comercial por vencer',
                        'note': body,
                        'date_deadline': today,
                        'user_id': user.id,
                        'res_model_id': self.env['ir.model']._get_id('sat.sat'),
                        'res_id': machine.id,
                    }
                    if existing:
                        existing.write({
                            'note': body,
                            'date_deadline': today,
                        })
                    else:
                        self.env['mail.activity'].create(vals)

            machine.with_context(sat_reserva_internal_write=True).write({
                'reserva_ultimo_aviso_fecha': today,
                'reserva_ultimo_aviso_dias': days,
            })
            count += 1

        return count

    @api.model
    def _cron_liberar_reservas_vencidas(self):
        today = fields.Date.context_today(self)
        machines = self.search([
            ('reserva_estado', 'in', ['separada', 'especial', 'confirmada']),
            ('reserva_fecha_limite', '!=', False),
            ('reserva_fecha_limite', '<', today),
            ('estado_ventas_id', '!=', 'entregada'),
        ])

        count = 0
        for machine in machines:
            with self.env.cr.savepoint():
                machine._reserva_liberar(
                    tipo='automatica',
                    motivo='Se superó la fecha límite de separación.',
                )
                count += 1
        return count

    @api.model
    def _cron_reconciliar_solicitudes_reserva(self):
        requests = self.env['sat.reserva.solicitud'].search([
            ('state', 'in', ['pending', 'partial']),
        ])
        processed = 0

        for request in requests:
            changed = False
            with self.env.cr.savepoint():
                pending_lines = request.line_ids.filtered(
                    lambda line: line.resultado == 'pending'
                )
                for line in pending_lines:
                    machine = line.maquina_id
                    if not machine.exists():
                        line.with_context(sat_reserva_internal_line_write=True).write({
                            'resultado': 'cancelled',
                            'seleccionada': False,
                            'comentario_gerencia': 'La máquina ya no existe.',
                        })
                        changed = True
                        continue

                    if machine.estado_ventas_id == 'entregada':
                        line.with_context(sat_reserva_internal_line_write=True).write({
                            'resultado': 'done',
                            'seleccionada': False,
                            'comentario_gerencia': 'Cerrada automáticamente porque la máquina fue entregada.',
                        })
                        if machine.reserva_solicitud_pendiente_id == request:
                            machine.with_context(sat_reserva_internal_write=True).write({
                                'reserva_solicitud_pendiente_id': False,
                            })
                        machine._reserva_crear_historial(
                            tipo_evento='cancelacion',
                            cliente=machine.reserva_cliente_id or machine.cliente_id,
                            asesora=machine.reserva_asesora_id,
                            solicitud=request,
                            fecha_anterior=machine.reserva_fecha_limite,
                            motivo='Solicitud cerrada automáticamente por entrega',
                        )
                        changed = True
                        continue

                    if machine.reserva_solicitud_pendiente_id != request:
                        line.with_context(sat_reserva_internal_line_write=True).write({
                            'resultado': 'cancelled',
                            'seleccionada': False,
                            'comentario_gerencia': 'La solicitud dejó de ser la solicitud pendiente vigente de esta máquina.',
                        })
                        machine._reserva_crear_historial(
                            tipo_evento='cancelacion',
                            cliente=machine.reserva_cliente_id or machine.cliente_id,
                            asesora=machine.reserva_asesora_id,
                            solicitud=request,
                            fecha_anterior=machine.reserva_fecha_limite,
                            motivo='Solicitud reconciliada automáticamente',
                        )
                        changed = True

                old_state = request.state
                request._actualizar_estado_solicitud()
                if changed or request.state != old_state:
                    request.message_post(
                        body=_(
                            'La solicitud comercial fue revisada automáticamente. Estado actual: <b>%s</b>.'
                        ) % dict(request._fields['state'].selection).get(request.state, request.state),
                        subtype_xmlid='mail.mt_note',
                    )
                    processed += 1

        return processed
