# models/reparacion_componente_evaluacion.py
from odoo import models, fields

class ReparacionComponenteEvaluacion(models.Model):
    _name = 'reparacion.componente.evaluacion'
    _description = 'Evaluación de Componentes en Reparación'
    _order = 'reparacion_id, componente_tipo_id, color_id, id'

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones', required=True, ondelete='cascade', index=True
    )
    componente_tipo_id = fields.Many2one(
        'componente.tipo', required=True, ondelete='restrict', index=True
    )
    color_id = fields.Many2one('color.tipo', ondelete='restrict')  # k/c/m/y si aplica
    estado_id = fields.Many2one('componente.estado', ondelete='restrict')
    subpartes_ids = fields.Many2many(
        'componente.subparte',
        'rep_comp_eval_subparte_rel',  # nombre de tabla M2M
        'eval_id', 'subparte_id',
        string='Subpartes'
    )
    observaciones = fields.Text()
