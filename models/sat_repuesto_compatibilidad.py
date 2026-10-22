# -*- coding: utf-8 -*-
"""Biblioteca técnica independiente del SAT operativo. Odoo 19.

No altera los modelos maestros existentes ni maneja inventario.
Los archivos de imagen residen exclusivamente en SharePoint.
"""
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class SatRepuestoCompatibilidad(models.Model):
    _name = 'sat.repuesto.compatibilidad'
    _description = 'Biblioteca de compatibilidades de repuestos y consumibles'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'write_date desc, id desc'

    name = fields.Char(
        string='Referencia interna',
        required=False,
        default='Nuevo',
        readonly=True,
        copy=False,
        tracking=True,
        index=True,
        help='Numeración automática REP-000001. El nombre técnico se consulta desde la subparte o el tóner.',
    )
    active = fields.Boolean(default=True)
    tipo_registro = fields.Selection([
        ('repuesto', 'Repuesto / subparte'),
        ('toner', 'Tóner'),
    ], required=True, default='repuesto', tracking=True, index=True)

    componente_id = fields.Many2one('componente.tipo', string='Componente',
                                    ondelete='restrict', tracking=True, index=True)
    subparte_id = fields.Many2one('componente.subparte', string='Subparte',
                                  ondelete='restrict', tracking=True, index=True)
    # La relación real comprobada en los archivos de SAT pasa por las plantillas
    # modelo.maquina.componente -> modelo.maquina.componente.subparte.
    subparte_permitida_ids = fields.Many2many(
        'componente.subparte', compute='_compute_subparte_permitida_ids',
        string='Subpartes que figuran en plantillas del componente', compute_sudo=False)
    toner_id = fields.Many2one('modelo.toner', string='Tóner del catálogo existente',
                               ondelete='restrict', tracking=True, index=True)

    codigo_parte = fields.Char(string='Código de parte', tracking=True, index=True)
    codigos_alternativos = fields.Text(string='Otros códigos / sinónimos')
    marca_id = fields.Many2one('marca.marca', string='Marca', ondelete='restrict', index=True)
    color = fields.Selection([
        ('k', 'Negro (K)'), ('c', 'Cian (C)'),
        ('m', 'Magenta (M)'), ('y', 'Amarillo (Y)'),
        ('na', 'Sin color específico'),
        ('multiple', 'Varios colores'),
    ], string='Color aplicable', default='na', tracking=True)

    modelo_maquina_ids = fields.Many2many(
        'modelo.maquina', 'sat_repuesto_compatibilidad_maquina_rel',
        'compatibilidad_id', 'modelo_id', string='Modelos compatibles',
        tracking=True, help='Relación de compatibilidad mantenida por el personal técnico; no altera la configuración SAT.')
    modelo_count = fields.Integer(compute='_compute_counts', string='Modelos compatibles')
    modelos_resumen = fields.Char(string='Modelos compatibles (resumen)', compute='_compute_modelos_resumen')
    foto_ids = fields.One2many('sat.repuesto.foto', 'compatibilidad_id', string='Fotografías SharePoint')
    foto_count = fields.Integer(compute='_compute_counts', string='Fotografías')

    estado = fields.Selection([
        ('borrador', 'En preparación'), ('pendiente', 'Pendiente de verificar'),
        ('verificado', 'Verificado'), ('descartado', 'No compatible / descartado'),
    ], default='borrador', required=True, tracking=True, index=True)
    observaciones = fields.Text(string='Observaciones técnicas')
    condiciones = fields.Text(string='Condiciones y restricciones de compatibilidad',
                              help='Serie, revisión, región, kit o adaptación necesaria.')
    fuente = fields.Selection([
        ('manual', 'Manual técnico'), ('fabricante', 'Fabricante'),
        ('proveedor', 'Proveedor'), ('prueba', 'Comprobación en taller'),
        ('otra', 'Otra'),
    ], string='Origen de verificación')
    referencia_documental = fields.Char(string='Enlace al documento / fuente')
    verificado_por_id = fields.Many2one('res.users', readonly=True, copy=False)
    fecha_verificacion = fields.Datetime(readonly=True, copy=False)

    def _check_solapamiento_compatibilidades(self):
        """Una subparte (o tóner) no puede repetirse en el mismo modelo activo.

        La comprobación es deliberadamente independiente del código de parte,
        estado y marca: el catálogo asigna una sola ficha por subparte/modelo.
        Un bloqueo transaccional evita inserciones simultáneas del mismo par.
        """
        for record in self:
            if not record.active or not record.modelo_maquina_ids:
                continue
            if record.tipo_registro == 'repuesto':
                if not record.subparte_id:
                    continue
                category = 'repuesto'
                value_id = record.subparte_id.id
                scope = _('subparte %(parte)s') % {
                    'parte': record.subparte_id.display_name,
                }
                domain_base = [
                    ('tipo_registro', '=', 'repuesto'),
                    ('subparte_id', '=', value_id),
                ]
            else:
                if not record.toner_id:
                    continue
                category = 'toner'
                value_id = record.toner_id.id
                scope = _('tóner %(toner)s') % {
                    'toner': record.toner_id.display_name,
                }
                domain_base = [
                    ('tipo_registro', '=', 'toner'),
                    ('toner_id', '=', value_id),
                ]

            # Dos sesiones creando la misma subparte esperan el mismo candado.
            # Bloqueo acotado a la transacción actual y en un espacio propio.
            self.env.cr.execute(
                'SELECT pg_advisory_xact_lock(%s, hashtext(%s))',
                (76439012, '%s:%s' % (category, value_id)),
            )

            conflicts = self.with_context(active_test=False).search(
                domain_base + [
                    ('active', '=', True),
                    ('id', '!=', record.id),
                    ('modelo_maquina_ids', 'in', record.modelo_maquina_ids.ids),
                ],
                order='id',
            )
            if not conflicts:
                continue

            lines = []
            for other in conflicts:
                repeated = record.modelo_maquina_ids & other.modelo_maquina_ids
                models = ', '.join(sorted(repeated.mapped('name'), key=str.casefold))
                lines.append('%s: %s' % (other.name or other.id, models))

            _logger.warning(
                '[BIBLIOTECA][DUPLICADOS] referencia=%s parte=%s conflictos=%s',
                record.name, scope, lines,
            )
            raise ValidationError(_(
                'Ya existe una compatibilidad para la %(parte)s en los mismos '
                'modelos de máquina.\n\n%(detalles)s\n\n'
                'Abra la ficha existente y agregue allí los modelos que faltan. '
                'No cree otra ficha para la misma subparte y modelo.'
            ) % {'parte': scope, 'detalles': '\n'.join(lines)})

    @api.constrains(
        'tipo_registro', 'subparte_id', 'toner_id',
        'modelo_maquina_ids', 'active',
    )
    def _constrain_solapamiento_compatibilidades(self):
        self._check_solapamiento_compatibilidades()

    @api.model_create_multi
    def create(self, vals_list):
        preparados = []
        for original in vals_list:
            vals = dict(original)
            # Nunca se permite al cliente elegir o duplicar el identificador.
            referencia = self.env['ir.sequence'].next_by_code(
                'sat.repuesto.compatibilidad'
            )
            if not referencia:
                raise UserError(_(
                    'No se encontró la secuencia sat.repuesto.compatibilidad. '
                    'Compruebe que data/sat_repuesto_sequence.xml esté en el manifiesto '
                    'y actualice el módulo SAT.'
                ))
            vals['name'] = referencia
            preparados.append(vals)
        records = super().create(preparados)
        records._check_solapamiento_compatibilidades()
        return records

    @api.depends('componente_id')
    def _compute_subparte_permitida_ids(self):
        Line = self.env['modelo.maquina.componente.subparte']
        for rec in self:
            if not rec.componente_id:
                rec.subparte_permitida_ids = False
                continue
            lineas = Line.search([('componente_id.tipo_id', '=', rec.componente_id.id)])
            rec.subparte_permitida_ids = lineas.mapped('subparte_id')

    @api.depends('modelo_maquina_ids', 'modelo_maquina_ids.name')
    def _compute_modelos_resumen(self):
        for rec in self:
            nombres = sorted(rec.modelo_maquina_ids.mapped('name'), key=str.casefold)
            primeros = nombres[:6]
            texto = ', '.join(primeros)
            if len(nombres) > 6:
                texto += ' (+%s más)' % (len(nombres) - 6)
            rec.modelos_resumen = texto or 'Sin modelos asociados'

    def action_asignar_referencia(self):
        """Asignar REP únicamente a registros previos que quedaron sin referencia."""
        for rec in self:
            if rec.name and rec.name.strip() not in ('Nuevo', '/'):
                continue
            nuevo = self.env['ir.sequence'].next_by_code('sat.repuesto.compatibilidad')
            if not nuevo:
                raise UserError(_('La secuencia REP no está configurada. Actualice SAT.'))
            super(SatRepuestoCompatibilidad, rec).write({'name': nuevo})
            _logger.info('[BIBLIOTECA][SECUENCIA] ficha=%s referencia=%s', rec.id, nuevo)
        return True

    @api.depends('modelo_maquina_ids', 'foto_ids')
    def _compute_counts(self):
        for rec in self:
            rec.modelo_count = len(rec.modelo_maquina_ids)
            rec.foto_count = len(rec.foto_ids)

    @api.onchange('componente_id')
    def _onchange_componente_id(self):
        for rec in self:
            if rec.subparte_id and rec.subparte_id not in rec.subparte_permitida_ids:
                rec.subparte_id = False

    @api.onchange('tipo_registro')
    def _onchange_tipo_registro(self):
        for rec in self:
            if rec.tipo_registro == 'toner':
                rec.componente_id = False
                rec.subparte_id = False
            else:
                rec.toner_id = False

    @api.constrains('tipo_registro', 'componente_id', 'subparte_id', 'toner_id')
    def _check_catalogo_origen(self):
        for rec in self:
            if rec.tipo_registro == 'repuesto':
                if not rec.componente_id or not rec.subparte_id:
                    raise ValidationError(_('Un repuesto debe tener componente y subparte.'))
                if rec.toner_id:
                    raise ValidationError(_('La ficha de repuesto no debe vincular un tóner.'))
                # No forzamos coincidencia con plantillas: se permite documentar
                # una subparte nueva cuya plantilla aún no haya sido configurada.
            else:
                if not rec.toner_id:
                    raise ValidationError(_('La ficha de tóner debe apuntar a modelo.toner.'))
                if rec.componente_id or rec.subparte_id:
                    raise ValidationError(_('Una ficha de tóner no debe tener componente o subparte.'))

    @api.constrains('estado', 'modelo_maquina_ids')
    def _check_verificacion(self):
        for rec in self:
            if rec.estado == 'verificado' and not rec.modelo_maquina_ids:
                raise ValidationError(_('No puedes verificar una ficha sin modelos compatibles.'))

    def action_subir_foto(self):
        self.ensure_one()
        if not self.id:
            raise UserError(_('Guarde primero la ficha.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Subir fotografía a SharePoint'),
            'res_model': 'sat.repuesto.foto.upload.wizard',
            'view_mode': 'form', 'target': 'new',
            'context': {'default_compatibilidad_id': self.id},
        }

    def action_marcar_pendiente(self):
        self.write({'estado': 'pendiente', 'verificado_por_id': False,
                    'fecha_verificacion': False})
        return True

    def action_verificar(self):
        for rec in self:
            if not rec.modelo_maquina_ids:
                raise UserError(_('Primero selecciona los modelos compatibles.'))
            rec.write({'estado': 'verificado',
                       'verificado_por_id': self.env.user.id,
                       'fecha_verificacion': fields.Datetime.now()})
            _logger.info('[BIBLIOTECA][VALIDACION] ficha=%s usuario=%s modelos=%s',
                         rec.id, self.env.user.id, rec.modelo_maquina_ids.ids)
        return True

    def action_desvalidar(self):
        self.write({'estado': 'pendiente', 'verificado_por_id': False,
                    'fecha_verificacion': False})
        return True

    def write(self, vals):
        vals = dict(vals)
        # El consecutivo es inmutable, incluso desde importaciones o RPC.
        vals.pop('name', None)
        campos_criticos = {
            'tipo_registro', 'componente_id', 'subparte_id', 'toner_id',
            'codigo_parte', 'marca_id', 'color', 'modelo_maquina_ids', 'condiciones',
        }
        if campos_criticos.intersection(vals) and 'estado' not in vals:
            for rec in self.filtered(lambda r: r.estado == 'verificado'):
                super(SatRepuestoCompatibilidad, rec).write({
                    'estado': 'pendiente',
                    'verificado_por_id': False,
                    'fecha_verificacion': False,
                })
        result = super().write(vals)
        if {'tipo_registro', 'subparte_id', 'toner_id', 'modelo_maquina_ids', 'active'} & set(vals):
            self._check_solapamiento_compatibilidades()
        return result


class SatRepuestoFoto(models.Model):
    _name = 'sat.repuesto.foto'
    _description = 'Fotografía de repuesto almacenada en SharePoint'
    _order = 'principal desc, sequence, id'

    sequence = fields.Integer(default=10)
    compatibilidad_id = fields.Many2one('sat.repuesto.compatibilidad', required=True,
                                        ondelete='cascade', index=True)
    name = fields.Char(string='Descripción / nombre de archivo', required=True)
    principal = fields.Boolean(default=False)
    # Solo metadatos de SharePoint. No se declaran fields.Binary ni ir.attachment.
    sharepoint_drive_id = fields.Char(string='Identificador de unidad SharePoint', required=True)
    sharepoint_item_id = fields.Char(string='Identificador de archivo SharePoint', required=True)
    sharepoint_web_url = fields.Char(string='Enlace web de SharePoint')
    mime_type = fields.Char(string='Tipo MIME')
    notas = fields.Char(string='Detalle de fotografía')

    _uniq_sharepoint_item = models.Constraint(
        'UNIQUE(sharepoint_drive_id, sharepoint_item_id)',
        'Esta fotografía de SharePoint ya está registrada.')

    @api.constrains('principal', 'compatibilidad_id')
    def _check_foto_principal(self):
        for rec in self.filtered('principal'):
            other = self.search_count([
                ('compatibilidad_id', '=', rec.compatibilidad_id.id),
                ('principal', '=', True), ('id', '!=', rec.id)])
            if other:
                raise ValidationError(_('Solo puede existir una fotografía principal por ficha.'))

    def action_abrir_sharepoint(self):
        self.ensure_one()
        if not self.sharepoint_web_url:
            raise UserError(_('No se registró un enlace web a SharePoint.'))
        if not self.sharepoint_web_url.startswith('https://'):
            raise UserError(_('El enlace a SharePoint debe ser HTTPS.'))
        return {'type': 'ir.actions.act_url', 'url': self.sharepoint_web_url,
                'target': 'new'}
