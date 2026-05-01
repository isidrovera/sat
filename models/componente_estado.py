from odoo import models, fields

class ComponenteEstado(models.Model):
    _name = 'componente.estado'
    _description = 'Estados posibles de componentes'
    _order = 'prioridad, name'

    name = fields.Char('Estado', required=True)
    code = fields.Char('Código', required=True, index=True)
    color = fields.Integer('Color (Kanban)')
    prioridad = fields.Integer('Prioridad', default=2, help='1=Crítico, 2=Medio, 3=Bajo')
    descripcion = fields.Text('Descripción')

    # ===== NUEVO CAMPO =====
    componente_tipo_ids = fields.Many2many(
        'componente.tipo',
        'componente_estado_tipo_rel',
        'estado_id',
        'tipo_id',
        string='Aplica a componentes',
        help='Tipos de componente a los que aplica este estado. '
             'Si está vacío, aplica a todos los componentes.'
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Código de estado duplicado.'),
    ]