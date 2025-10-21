# models/componente.py
from odoo import models, fields, api
class ComponenteTipo(models.Model):
    _name = 'componente.tipo'
    _description = 'Tipo de Componente (IU, Fusora, Faja, ADF, Tray, etc.)'

    name = fields.Char(required=True)
    code = fields.Char(required=True, help="Clave corta: IU, FUSORA, FAJA, ADF, TRAY, OPTICO, FINISHER, RED, ESCANER ...")
    is_color_sensitive = fields.Boolean(string="Difiere por color (K/C/M/Y)", default=False)
    is_critical = fields.Boolean(string="Crítico (puede dejar no operativo)", default=True)
    sequence = fields.Integer(default=10)

    # Habilita archivar/desarchivar
    active = fields.Boolean(default=True)


class ComponenteSubparte(models.Model):
    _name = 'componente.subparte'
    _description = 'Subparte técnica del componente (ej. Tambor, Cuchilla, Rodillo presión)'
    _order = 'tipo_id, name'
    _rec_name = 'display_name'

    name = fields.Char(required=True)
    code = fields.Char(string='Código', index=True, copy=False)
    tipo_id = fields.Many2one('componente.tipo', required=True, ondelete='restrict', index=True)
    color_id = fields.Many2one('componente.color', string='Color', ondelete='restrict')
    active = fields.Boolean(default=True)

    display_name = fields.Char(compute='_compute_display_name', store=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'El código debe ser único.'),
    ]
    # Si quieres unicidad por tipo:
    # _sql_constraints = [
    #     ('code_tipo_uniq', 'unique(code, tipo_id)', 'Código repetido para este tipo.'),
    # ]

    @api.depends('code', 'name', 'tipo_id', 'color_id')
    def _compute_display_name(self):
        for rec in self:
            parts = []
            if rec.code:
                parts.append(rec.code)
            if rec.name:
                parts.append(rec.name)
            if rec.tipo_id:
                parts.append(f'[{rec.tipo_id.display_name}]')
            if rec.color_id:
                parts.append(rec.color_id.display_name)
            rec.display_name = ' - '.join(parts) if parts else (rec.name or '')
