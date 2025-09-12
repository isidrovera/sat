# models/checklist_map.py
from odoo import models, fields

class ChecklistComponenteMap(models.Model):
    _name = 'checklist.componente.map'
    _description = 'Mapea un campo del ticket a un tipo de componente (+ color)'

    field_name = fields.Char(required=True, help="Ej: 'adf_id', 'tray1_id', 'black_id', 'fusora_id'")
    tipo_id = fields.Many2one('componente.tipo', required=True)
    color = fields.Selection([('k','K'),('c','C'),('m','M'),('y','Y')], string='Color')
    # Si marcar 'no' o 'cambio' en este campo puede dejar no operativo
    is_blocking = fields.Boolean(default=False)
    # Para bandejas, mantener una etiqueta bonita
    label = fields.Char(help="Etiqueta amigable (Tray 1, ADF, etc.)")
