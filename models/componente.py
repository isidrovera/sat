# models/componente.py
from odoo import models, fields

class ComponenteTipo(models.Model):
    _name = 'componente.tipo'
    _description = 'Tipo de Componente (IU, Fusora, Faja, ADF, Tray, etc.)'

    name = fields.Char(required=True)
    code = fields.Char(required=True, help="Clave corta: IU, FUSORA, FAJA, ADF, TRAY, OPTICO, FINISHER, RED, ESCANER ...")
    is_color_sensitive = fields.Boolean(string="Difiere por color (K/C/M/Y)", default=False)
    is_critical = fields.Boolean(string="Crítico (puede dejar no operativo)", default=True)
    sequence = fields.Integer(default=10)

class ComponenteSubparte(models.Model):
    _name = 'componente.subparte'
    _description = 'Subparte técnica del componente (ej. Tambor, Cuchilla, Rodillo presión)'
    _order = 'tipo_id, name'
    _rec_name = 'display_name'

    name = fields.Char(required=True)
    code = fields.Char(string='Código', index=True, copy=False)         # ← lo que usas en XML/vistas
    tipo_id = fields.Many2one('componente.tipo', required=True,           # ← lo que usas en XML/vistas
                              ondelete='restrict', index=True)
    active = fields.Boolean(default=True)

    display_name = fields.Char(compute='_compute_display_name', store=True)

    # Si el código debe ser único globalmente:
    _sql_constraints = [
        ('codigo_uniq', 'unique(codigo)', 'El código debe ser único.')
    ]
    # Si el mismo "codigo" puede repetirse por tipo, usa esto en vez de lo anterior:
    # _sql_constraints = [
    #     ('codigo_tipo_uniq', 'unique(codigo, tipo_id)', 'Código repetido para este tipo.')
    # ]

    @api.depends('codigo', 'name', 'tipo_id')
    def _compute_display_name(self):
        for rec in self:
            parts = []
            if rec.codigo:
                parts.append(rec.codigo)
            if rec.name:
                parts.append(rec.name)
            if rec.tipo_id:
                parts.append(f'[{rec.tipo_id.display_name}]')
            rec.display_name = ' - '.join(parts) if parts else rec.name
