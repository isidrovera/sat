# models/reparacion_componente_evaluacion.py
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ReparacionComponenteEvaluacion(models.Model):
    _name = 'reparacion.componente.evaluacion'
    _description = 'Evaluación de Componentes en Reparación'
    _order = 'reparacion_id, componente_tipo_id, color_id, id'

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones', ondelete='cascade', index=True, string='Reparación'
    )
    componente_tipo_id = fields.Many2one(
        'componente.tipo', ondelete='restrict', index=True, string='Tipo de Componente'
    )
    color_id = fields.Many2one('color.tipo', ondelete='restrict', string='Color')  # k/c/m/y si aplica
    estado_id = fields.Many2one('componente.estado', ondelete='restrict', string='Estado')
    subpartes_ids = fields.Many2many(
        'componente.subparte',
        'rep_comp_eval_subparte_rel',  # nombre de tabla M2M
        'eval_id', 'subparte_id',
        string='Subpartes'
    )
    observaciones = fields.Text(string='Observaciones')

    @api.model
    def create(self, vals):
        _logger.info(f"ReparacionComponenteEvaluacion.create() recibió: {vals}")
        
        # Verificar que reparacion_id esté en vals
        if 'reparacion_id' not in vals:
            _logger.error("ERROR: reparacion_id no está en vals")
        else:
            _logger.info(f"reparacion_id en vals: {vals['reparacion_id']}")
            
        # Crear el registro
        record = super().create(vals)
        
        # Verificar que se creó correctamente
        _logger.info(f"Registro creado - ID: {record.id}, reparacion_id: {record.reparacion_id.id if record.reparacion_id else 'VACIO'}")
        
        return record

    def write(self, vals):
        _logger.info(f"ReparacionComponenteEvaluacion.write() ID: {self.id}, vals: {vals}")
        result = super().write(vals)
        _logger.info(f"Después de write - reparacion_id: {self.reparacion_id.id if self.reparacion_id else 'VACIO'}")
        return result