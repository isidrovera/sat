# -*- coding: utf-8 -*-

import re
import unicodedata

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class MarcaMaquina(models.Model):
    _name = 'marca.marca'
    _description = 'Marca de máquina'
    _order = 'name'

    name = fields.Char(
        string='Marca de máquina',
        required=True,
        index=True,
    )

    codigo_tecnico = fields.Char(
        string='Código técnico',
        copy=False,
        index=True,
        help=(
            'Código estable utilizado para generar IDs externos. '
            'Ejemplo: ricoh, konica_minolta, canon.'
        ),
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

    active = fields.Boolean(
        string='Activo',
        default=True,
    )

    
    _unique_name = models.Constraint(
        'UNIQUE(name)',
        'La marca que intenta agregar ya existe.',
    )

    _unique_codigo_tecnico = models.Constraint(
        'UNIQUE(codigo_tecnico)',
        'El código técnico de la marca ya está siendo utilizado.',
    )

    # =========================================================
    # NORMALIZACIÓN
    # =========================================================

    @api.model
    def _normalizar_codigo(self, value):
        """
        Convierte un texto en un código técnico estable.

        Ejemplos:
            Konica Minolta -> konica_minolta
            RICOH          -> ricoh
            Kyocera-Mita   -> kyocera_mita
        """
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
        """
        Propone el código técnico mientras el usuario edita la marca.

        No reemplaza un código que ya haya sido ingresado manualmente.
        """
        for record in self:
            if record.name and not record.codigo_tecnico:
                record.codigo_tecnico = record._normalizar_codigo(record.name)

    @api.model_create_multi
    def create(self, vals_list):
        """
        Genera el código técnico al crear la marca si no fue informado.
        """
        for vals in vals_list:
            if vals.get('name') and not vals.get('codigo_tecnico'):
                vals['codigo_tecnico'] = self._normalizar_codigo(
                    vals['name']
                )

        return super().create(vals_list)

    @api.constrains('codigo_tecnico')
    def _check_codigo_tecnico(self):
        for record in self:
            if not record.codigo_tecnico:
                continue

            normalizado = record._normalizar_codigo(
                record.codigo_tecnico
            )

            if not normalizado:
                raise ValidationError(
                    _('El código técnico de la marca no es válido.')
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
        """
        Obtiene el registro ir.model.data relacionado con la marca.

        Primero busca uno perteneciente al módulo sat.
        """
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

    @api.depends('name', 'codigo_tecnico')
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

            if record.codigo_tecnico:
                proposed_name = f'marca_{record.codigo_tecnico}'

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
        """
        Genera el ID externo real de la marca en ir.model.data.

        Ejemplo:
            sat.marca_ricoh
        """
        IrModelData = self.env['ir.model.data'].sudo()

        generated = 0
        existing = 0
        conflicts = []

        for record in self:
            if not record.codigo_tecnico:
                record.codigo_tecnico = record._normalizar_codigo(
                    record.name
                )

            if not record.codigo_tecnico:
                conflicts.append(
                    _('%s: no se pudo generar el código técnico.')
                    % (record.name or record.id)
                )
                continue

            current_external = record._get_external_id_record()

            if current_external:
                existing += 1
                continue

            external_name = f'marca_{record.codigo_tecnico}'

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
                    ) % (record.name, external_name)
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
                _(
                    'Se encontraron conflictos:\n\n%s'
                ) % '\n'.join(conflicts)
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('IDs externos de marcas'),
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