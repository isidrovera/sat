from odoo import models, fields

class ComponenteEstado(models.Model):
    _name = 'componente.estado'
    _description = 'Estados posibles de componentes'
    _order = 'prioridad, name'

    name = fields.Char('Estado', required=True)
    code = fields.Char('Código', required=True, index=True)  # ej: requiere_cambio, regular, nuevo...
    color = fields.Integer('Color (Kanban)')
    prioridad = fields.Integer('Prioridad', default=2, help='1=Crítico, 2=Medio, 3=Bajo')
    descripcion = fields.Text('Descripción')

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Código de estado duplicado.'),
    ]
