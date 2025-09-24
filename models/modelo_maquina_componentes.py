# models/modelo_maquina_componentes.py
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ModeloMaquinaComponente(models.Model):
    _name = 'modelo.maquina.componente'
    _description = 'Plantilla de componentes por modelo de máquina'
    _order = 'prioridad, tipo_id, color'
    _rec_name = 'display_name'

    # Relaciones principales
    modelo_id = fields.Many2one(
        'modelo.maquina',
        required=True,
        ondelete='cascade',
        index=True,
        string='Modelo'
    )
    tipo_id = fields.Many2one(
        'componente.tipo',
        required=True,
        ondelete='restrict',
        index=True,
        string='Tipo de componente'
    )

    # Atributos
    color = fields.Selection(
        [('k', 'K'), ('c', 'C'), ('m', 'M'), ('y', 'Y')],
        string='Color'
    )
    estado_sugerido_id = fields.Many2one(
        'componente.estado',
        string='Estado sugerido',
        ondelete='restrict'
    )

    # vida útil / prioridad / frases
    vida_util_paginas = fields.Integer(string='Vida útil (pág.)')
    vida_util_meses = fields.Integer(string='Vida útil (meses)')
    prioridad = fields.Selection(
        [('1', 'Crítico'), ('2', 'Medio'), ('3', 'Bajo')],
        default='1',
        string='Prioridad',
        required=True,
        index=True
    )
    frase_desgaste = fields.Char(string='Frase de desgaste (opcional)')
    frase_cambio = fields.Char(string='Frase de cambio (opcional)')

    # Subpartes sugeridas (líneas hijas)
    detalle_ids = fields.One2many(
        'modelo.maquina.componente.subparte',  # comodel correcto
        'componente_id',                       # inverse_name correcto
        string='Subpartes sugeridas'
    )

    # utilidades UI
    display_name = fields.Char(
        compute='_compute_display_name',
        store=False
    )

    # --------- Computados / Onchange / Reglas ---------
    @api.depends('tipo_id', 'color')
    def _compute_display_name(self):
        for rec in self:
            name = rec.tipo_id.name if rec.tipo_id else ''
            # Si el tipo es sensible a color y se estableció color, lo mostramos
            if rec.tipo_id and getattr(rec.tipo_id, 'is_color_sensitive', False) and rec.color:
                name = f"{name} ({rec.color.upper()})"
            rec.display_name = name or '—'

    @api.onchange('tipo_id')
    def _onchange_tipo_color(self):
        """Si el tipo NO es sensible a color, limpiamos el campo en UI."""
        for rec in self:
            if rec.tipo_id and not getattr(rec.tipo_id, 'is_color_sensitive', False):
                rec.color = False

    @api.constrains('tipo_id', 'color')
    def _check_color_requirement(self):
        """Validar (no mutar) coherencia color/tipo."""
        for rec in self:
            sensitive = bool(rec.tipo_id and getattr(rec.tipo_id, 'is_color_sensitive', False))
            if sensitive and not rec.color:
                raise ValidationError("Este tipo de componente requiere color (K/C/M/Y).")

    # Refuerzos de integridad en create/write (para importaciones/RPC)
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tipo = None
            if 'tipo_id' in vals and vals['tipo_id']:
                tipo = self.env['componente.tipo'].browse(vals['tipo_id'])
            # Si el tipo no es sensible a color, aseguremos color = False
            if tipo and not getattr(tipo, 'is_color_sensitive', False):
                vals['color'] = False
        records = super().create(vals_list)
        # Validación post-crear (caerá si falta color en sensibles)
        records._check_color_requirement()
        return records

    def write(self, vals):
        res = super().write(vals)
        # Releer tipo/color para cada registro afectado y limpiar si aplica
        for rec in self:
            if rec.tipo_id and not getattr(rec.tipo_id, 'is_color_sensitive', False) and rec.color:
                super(ModeloMaquinaComponente, rec).write({'color': False})
        # Validación post-write
        self._check_color_requirement()
        return res

    _sql_constraints = [
        (
            'uniq_modelo_tipo_color',
            'unique(modelo_id, tipo_id, color)',
            'Ya existe este tipo/color de componente para el modelo.'
        )
    ]


class ModeloMaquinaComponenteSubparte(models.Model):
    _name = 'modelo.maquina.componente.subparte'
    _description = 'Subparte sugerida para un componente de modelo'
    _order = 'subparte_id'

    # Inverso correcto hacia el padre
    componente_id = fields.Many2one(
        'modelo.maquina.componente',
        required=True,
        ondelete='cascade',
        index=True,
        string='Componente'
    )

    # Subparte del catálogo
    subparte_id = fields.Many2one(
        'componente.subparte',
        required=True,
        ondelete='restrict',
        index=True,
        string='Subparte'
    )

    cantidad = fields.Float(string='Cantidad', default=1.0)
    nota = fields.Char(string='Nota')

    _sql_constraints = [
        (
            'uniq_componente_subparte',
            'unique(componente_id, subparte_id)',
            'La subparte ya está listada para este componente.'
        )
    ]


class ModelosMaquin(models.Model):
    _inherit = 'modelo.maquina'

    componente_line_ids = fields.One2many(
        'modelo.maquina.componente',
        'modelo_id',
        string='Componentes del modelo'
    )
