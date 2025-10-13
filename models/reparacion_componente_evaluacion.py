# models/reparacion_componente_evaluacion.py
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ReparacionComponenteEvaluacion(models.Model):
    _name = 'reparacion.componente.evaluacion'
    _description = 'Evaluación de Componentes en Reparación'
    _order = 'reparacion_id, componente_tipo_id, color_id, id'

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones', 
        ondelete='cascade', 
        index=True, 
        string='Reparación',
        required=True
    )
    
    componente_tipo_id = fields.Many2one(
        'componente.tipo', 
        ondelete='restrict', 
        index=True, 
        string='Tipo de Componente',
        required=True
    )
    
    color_id = fields.Many2one(
        'color.tipo', 
        ondelete='restrict', 
        string='Color'
    )
    
    estado_id = fields.Many2one(
        'componente.estado', 
        ondelete='restrict', 
        string='Estado',
        required=False,  # ✅ CAMBIO CLAVE: Permitir que esté vacío inicialmente
        help="Estado del componente. Debe ser completado por el técnico."
    )
    
    subpartes_ids = fields.Many2many(
        'componente.subparte',
        'rep_comp_eval_subparte_rel',
        'eval_id', 'subparte_id',
        string='Subpartes Específicas',
        domain="[('tipo_id', '=', componente_tipo_id)]",
        help="Subpartes específicas de este componente que fueron intervenidas"
    )
    
    observaciones = fields.Text(string='Observaciones')

    _sql_constraints = [
        ('reparacion_componente_color_unique', 
         'unique(reparacion_id, componente_tipo_id, color_id)',
         'Ya existe una evaluación de este componente y color para esta reparación.')
    ]

    @api.model
    def create(self, vals):
        _logger.info(f"ReparacionComponenteEvaluacion.create() recibió: {vals}")
        
        if 'reparacion_id' not in vals:
            _logger.error("ERROR: reparacion_id no está en vals")
        else:
            _logger.info(f"reparacion_id en vals: {vals['reparacion_id']}")
            
        record = super().create(vals)
        
        _logger.info(f"Registro creado - ID: {record.id}, reparacion_id: {record.reparacion_id.id if record.reparacion_id else 'VACIO'}")
        
        return record

    def write(self, vals):
        _logger.info(f"ReparacionComponenteEvaluacion.write() ID: {self.id}, vals: {vals}")
        result = super().write(vals)
        _logger.info(f"Después de write - reparacion_id: {self.reparacion_id.id if self.reparacion_id else 'VACIO'}")
        return result


    