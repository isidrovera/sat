# -*- coding: utf-8 -*-

import re
import unicodedata

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ModeloMaquinaFamilia(models.Model):
    _name = 'modelo.maquina.familia'
    _description = 'Familia técnica de modelos de máquina'
    _order = 'marca_id, name'
    _rec_name = 'display_name'

    name = fields.Char(
        string='Familia',
        required=True,
        index=True,
        help=(
            'Nombre técnico o comercial de la familia. '
            'Ejemplo: MP C3004 / C6004.'
        ),
    )

    codigo_tecnico = fields.Char(
        string='Código técnico',
        required=True,
        copy=False,
        index=True,
        help=(
            'Código estable de la familia. '
            'Ejemplo: mp_cxx04.'
        ),
    )

    marca_id = fields.Many2one(
        'marca.marca',
        string='Marca',
        required=True,
        ondelete='restrict',
        index=True,
    )

    tipo_id = fields.Selection(
        [
            ('color', 'Color'),
            ('monocromatica', 'Monocromática'),
            ('mixta', 'Mixta'),
        ],
        string='Tecnología',
        default='color',
        required=True,
    )

    descripcion = fields.Text(
        string='Descripción',
    )

    notas_tecnicas = fields.Text(
        string='Notas técnicas',
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
    )

    modelo_ids = fields.One2many(
        'modelo.maquina',
        'familia_id',
        string='Modelos',
    )

    modelo_count = fields.Integer(
        string='Cantidad de modelos',
        compute='_compute_modelo_count',
    )

    display_name = fields.Char(
        string='Nombre mostrado',
        compute='_compute_display_name',
    )

    external_id_display = fields.Char(
        string='ID externo',
        compute='_compute_external_id_info',
        readonly=True,
    )

    external_id_state = fields.Selection(
        [
            ('pending', 'Pendiente'),
            ('generated', 'Generado'),
            ('conflict', 'Conflicto'),
        ],
        string='Estado ID externo',
        compute='_compute_external_id_info',
        readonly=True,
    )

    external_id_generated_date = fields.Datetime(
        string='Fecha de generación',
        readonly=True,
        copy=False,
    )

    external_id_generated_by = fields.Many2one(
        'res.users',
        string='Generado por',
        readonly=True,
        copy=False,
    )

    _sql_constraints = [
        (
            'unique_marca_codigo_familia',
            'unique(marca_id, codigo_tecnico)',
            'Ya existe una familia con este código para la marca.',
        ),
    ]

    # =========================================================
    # CAMPOS CALCULADOS
    # =========================================================

    @api.depends('marca_id', 'name')
    def _compute_display_name(self):
        for record in self:
            if record.marca_id and record.name:
                record.display_name = (
                    f'{record.marca_id.name} / {record.name}'
                )
            else:
                record.display_name = record.name or _('Nueva familia')

    @api.depends('modelo_ids')
    def _compute_modelo_count(self):
        for record in self:
            record.modelo_count = len(record.modelo_ids)

    # =========================================================
    # NORMALIZACIÓN
    # =========================================================

    @api.model
    def _normalizar_codigo(self, value):
        value = value or ''

        value = unicodedata.normalize('NFKD', value)
        value = ''.join(
            character
            for character in value
            if not unicodedata.combining(character)
        )

        value = value.lower().strip()
        value = re.sub(r'[^a-z0-9]+', '_', value)
        value = re.sub(r'_+', '_', value)
        value = value.strip('_')

        return value

    @api.onchange('name')
    def _onchange_name_codigo_tecnico(self):
        for record in self:
            if record.name and not record.codigo_tecnico:
                record.codigo_tecnico = record._normalizar_codigo(
                    record.name
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name') and not vals.get('codigo_tecnico'):
                vals['codigo_tecnico'] = self._normalizar_codigo(
                    vals['name']
                )

        return super().create(vals_list)

    @api.constrains('codigo_tecnico')
    def _check_codigo_tecnico(self):
        for record in self:
            normalizado = record._normalizar_codigo(
                record.codigo_tecnico
            )

            if not normalizado:
                raise ValidationError(
                    _('El código técnico de la familia no es válido.')
                )

            if record.codigo_tecnico != normalizado:
                raise ValidationError(
                    _(
                        'El código técnico debe utilizar únicamente '
                        'letras minúsculas, números y guion bajo.\n\n'
                        'Código sugerido: %s'
                    ) % normalizado
                )

    # =========================================================
    # ID EXTERNO
    # =========================================================

    def _get_external_id_record(self):
        self.ensure_one()

        if not self.id:
            return self.env['ir.model.data']

        IrModelData = self.env['ir.model.data'].sudo()

        external_record = IrModelData.search(
            [
                ('module', '=', 'sat'),
                ('model', '=', self._name),
                ('res_id', '=', self.id),
            ],
            limit=1,
        )

        if external_record:
            return external_record

        return IrModelData.search(
            [
                ('model', '=', self._name),
                ('res_id', '=', self.id),
            ],
            limit=1,
        )

    @api.depends('codigo_tecnico', 'marca_id.codigo_tecnico')
    def _compute_external_id_info(self):
        IrModelData = self.env['ir.model.data'].sudo()

        for record in self:
            record.external_id_display = False
            record.external_id_state = 'pending'

            if not record.id:
                continue

            external_record = record._get_external_id_record()

            if external_record:
                record.external_id_display = (
                    f'{external_record.module}.{external_record.name}'
                )
                record.external_id_state = 'generated'
                continue

            if (
                record.marca_id.codigo_tecnico
                and record.codigo_tecnico
            ):
                proposed_name = (
                    f'familia_'
                    f'{record.marca_id.codigo_tecnico}_'
                    f'{record.codigo_tecnico}'
                )

                conflict = IrModelData.search(
                    [
                        ('module', '=', 'sat'),
                        ('name', '=', proposed_name),
                    ],
                    limit=1,
                )

                if conflict and not (
                    conflict.model == record._name
                    and conflict.res_id == record.id
                ):
                    record.external_id_state = 'conflict'

    def action_generate_external_id(self):
        IrModelData = self.env['ir.model.data'].sudo()

        generated = 0
        existing = 0
        conflicts = []

        for record in self:
            if not record.marca_id:
                conflicts.append(
                    _('%s: no tiene una marca asignada.')
                    % record.name
                )
                continue

            if not record.marca_id.codigo_tecnico:
                conflicts.append(
                    _(
                        '%s: la marca %s no tiene código técnico.'
                    ) % (record.name, record.marca_id.name)
                )
                continue

            if not record.codigo_tecnico:
                record.codigo_tecnico = record._normalizar_codigo(
                    record.name
                )

            current_external = record._get_external_id_record()

            if current_external:
                existing += 1
                continue

            external_name = (
                f'familia_'
                f'{record.marca_id.codigo_tecnico}_'
                f'{record.codigo_tecnico}'
            )

            conflict = IrModelData.search(
                [
                    ('module', '=', 'sat'),
                    ('name', '=', external_name),
                ],
                limit=1,
            )

            if conflict:
                conflicts.append(
                    _(
                        '%s: el ID sat.%s ya pertenece a otro registro.'
                    ) % (record.display_name, external_name)
                )
                continue

            IrModelData.create(
                {
                    'module': 'sat',
                    'name': external_name,
                    'model': record._name,
                    'res_id': record.id,
                    'noupdate': False,
                }
            )

            record.write(
                {
                    'external_id_generated_date': fields.Datetime.now(),
                    'external_id_generated_by': self.env.user.id,
                }
            )

            generated += 1

        if conflicts:
            raise UserError(
                _('Se encontraron conflictos:\n\n%s')
                % '\n'.join(conflicts)
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('IDs externos de familias'),
                'message': _(
                    'Generados: %(generated)s\n'
                    'Ya existentes: %(existing)s'
                ) % {
                    'generated': generated,
                    'existing': existing,
                },
                'type': 'success',
                'sticky': False,
            },
        }

    # =========================================================
    # ACCIONES
    # =========================================================

    def action_view_modelos(self):
        self.ensure_one()

        return {
            'name': _('Modelos - %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'modelo.maquina',
            'view_mode': 'list,form',
            'domain': [('familia_id', '=', self.id)],
            'context': {
                'default_familia_id': self.id,
                'default_marca_id': self.marca_id.id,
            },
        }