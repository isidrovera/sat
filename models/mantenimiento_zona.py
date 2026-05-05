# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MantenimientoZona(models.Model):
    _name = 'mantenimiento.zona'
    _description = 'Zona operativa de mantenimiento'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(
        string='Zona',
        required=True,
        tracking=True,
        help='Nombre de la zona operativa. Ej: Lima Norte, Lima Centro, Callao.'
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10,
        help='Orden de visualización de la zona.'
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
        tracking=True
    )

    color = fields.Integer(
        string='Color',
        default=0
    )

    descripcion = fields.Text(
        string='Descripción',
        help='Notas internas sobre esta zona.'
    )

    distrito_ids = fields.One2many(
        'mantenimiento.zona.distrito',
        'zona_id',
        string='Distritos'
    )

    tecnico_ids = fields.Many2many(
        'res.users',
        'mantenimiento_zona_res_users_rel',
        'zona_id',
        'user_id',
        string='Técnicos preferidos',
        tracking=True,
        help='Técnicos recomendados para atender esta zona.'
    )

    flexible = fields.Boolean(
        string='Zona flexible',
        default=False,
        tracking=True,
        help='Si está activo, el planificador puede asignar técnicos de otras zonas cuando no haya disponibilidad.'
    )

    distrito_count = fields.Integer(
        string='Cantidad de distritos',
        compute='_compute_counts',
        store=False
    )

    equipo_count = fields.Integer(
        string='Máquinas',
        compute='_compute_counts',
        store=False
    )

    tecnico_count = fields.Integer(
        string='Técnicos',
        compute='_compute_counts',
        store=False
    )

    @api.depends('distrito_ids', 'tecnico_ids')
    def _compute_counts(self):
        Alquiler = self.env['alquiler']
        for rec in self:
            rec.distrito_count = len(rec.distrito_ids)
            rec.tecnico_count = len(rec.tecnico_ids)

            distritos = rec.distrito_ids.mapped('name')
            if distritos:
                rec.equipo_count = Alquiler.search_count([
                    ('distrito', 'in', distritos),
                    ('control_mantenimiento', '=', True),
                    ('estado_alquiler_id', '=', 'alquilada'),
                ])
            else:
                rec.equipo_count = 0

    @api.constrains('name')
    def _check_name_unique(self):
        for rec in self:
            if not rec.name:
                continue

            existe = self.search_count([
                ('id', '!=', rec.id),
                ('name', '=ilike', rec.name.strip()),
            ])

            if existe:
                raise ValidationError(
                    _("Ya existe una zona con el nombre '%s'.") % rec.name
                )

    def action_ver_maquinas(self):
        self.ensure_one()

        distritos = self.distrito_ids.mapped('name')

        domain = [
            ('control_mantenimiento', '=', True),
            ('estado_alquiler_id', '=', 'alquilada'),
        ]

        if distritos:
            domain.append(('distrito', 'in', distritos))
        else:
            domain.append(('id', '=', 0))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Máquinas de %s') % self.name,
            'res_model': 'alquiler',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'default_control_mantenimiento': True,
            }
        }

    def action_ver_distritos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Distritos de %s') % self.name,
            'res_model': 'mantenimiento.zona.distrito',
            'view_mode': 'list,form',
            'domain': [('zona_id', '=', self.id)],
            'context': {
                'default_zona_id': self.id,
            }
        }


class MantenimientoZonaDistrito(models.Model):
    _name = 'mantenimiento.zona.distrito'
    _description = 'Distrito asociado a zona de mantenimiento'
    _order = 'zona_id, name'

    name = fields.Char(
        string='Distrito',
        required=True,
        index=True,
        help='Nombre del distrito tal como se usará para relacionarlo con las máquinas.'
    )

    zona_id = fields.Many2one(
        'mantenimiento.zona',
        string='Zona',
        required=True,
        ondelete='cascade',
        index=True
    )

    active = fields.Boolean(
        string='Activo',
        default=True
    )

    alias = fields.Char(
        string='Alias / variaciones',
        help='Variaciones posibles del nombre del distrito separadas por coma. Ej: Surco, Santiago de Surco, Distrito de Santiago de Surco.'
    )

    provincia = fields.Char(
        string='Provincia',
        default='Lima'
    )

    departamento = fields.Char(
        string='Departamento',
        default='Lima'
    )

    pais = fields.Char(
        string='País',
        default='Perú'
    )

    sequence = fields.Integer(
        string='Secuencia',
        default=10
    )

    equipo_count = fields.Integer(
        string='Máquinas',
        compute='_compute_equipo_count',
        store=False
    )

    @api.depends('name', 'alias')
    def _compute_equipo_count(self):
        Alquiler = self.env['alquiler']
        for rec in self:
            nombres = rec._get_nombres_busqueda()
            rec.equipo_count = Alquiler.search_count([
                ('distrito', 'in', nombres),
                ('control_mantenimiento', '=', True),
                ('estado_alquiler_id', '=', 'alquilada'),
            ])

    def _get_nombres_busqueda(self):
        self.ensure_one()

        nombres = []

        if rec_name := self.name:
            nombres.append(rec_name.strip())

        if self.alias:
            for alias in self.alias.split(','):
                alias = alias.strip()
                if alias:
                    nombres.append(alias)

        return list(set(nombres))

    @api.constrains('name', 'zona_id')
    def _check_distrito_unique(self):
        for rec in self:
            if not rec.name:
                continue

            existe = self.search_count([
                ('id', '!=', rec.id),
                ('name', '=ilike', rec.name.strip()),
                ('zona_id', '=', rec.zona_id.id),
            ])

            if existe:
                raise ValidationError(
                    _("El distrito '%s' ya está registrado en esta zona.") % rec.name
                )

    def action_ver_maquinas(self):
        self.ensure_one()

        nombres = self._get_nombres_busqueda()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Máquinas en %s') % self.name,
            'res_model': 'alquiler',
            'view_mode': 'list,form',
            'domain': [
                ('distrito', 'in', nombres),
                ('control_mantenimiento', '=', True),
                ('estado_alquiler_id', '=', 'alquilada'),
            ],
        }