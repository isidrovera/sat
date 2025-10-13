from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ModeloMaquinaAccesorio(models.Model):
    _name = 'modelo.maquina.accesorio'
    _description = 'Plantilla de accesorios por modelo de máquina'
    _order = 'tipo_id'
    _rec_name = 'display_name'

    modelo_id = fields.Many2one(
        'modelo.maquina', 
        required=True, 
        ondelete='cascade', 
        index=True,
        string='Modelo'
    )
    tipo_id = fields.Many2one(
        'accesorio.tipo', 
        required=True, 
        ondelete='restrict', 
        index=True,
        string='Tipo de accesorio'
    )
    estado_predeterminado_id = fields.Many2one(
        'accesorio.estado', 
        string='Estado predeterminado', 
        ondelete='restrict'
    )
    obligatorio = fields.Boolean(
        string='Obligatorio en este modelo', 
        default=False
    )
    nota = fields.Char(string='Nota')
    
    display_name = fields.Char(
        compute='_compute_display_name',
        store=False
    )

    @api.depends('tipo_id', 'modelo_id')
    def _compute_display_name(self):
        for rec in self:
            tipo = rec.tipo_id.name if rec.tipo_id else '—'
            modelo = rec.modelo_id.name if rec.modelo_id else ''
            rec.display_name = f"{tipo} ({modelo})" if modelo else tipo

    _sql_constraints = [
        ('uniq_modelo_accesorio', 'unique(modelo_id, tipo_id)', 
         'Este accesorio ya está definido para el modelo.')
    ]


class ModelosMaquin(models.Model):
    _inherit = 'modelo.maquina'
    
    accesorio_line_ids = fields.One2many(
        'modelo.maquina.accesorio', 
        'modelo_id', 
        string='Accesorios del modelo'
    )