from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ReparacionAccesorioEvaluacion(models.Model):
    _name = 'reparacion.accesorio.evaluacion'
    _description = 'Evaluación de Accesorios en Reparación'
    _order = 'reparacion_id, tipo_id'

    reparacion_id = fields.Many2one(
        'reparaciones.reparaciones', 
        string='Reparación',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    tipo_id = fields.Many2one(
        'accesorio.tipo',
        string='Tipo de Accesorio',
        required=True,
        ondelete='restrict'
    )
    
    estado_id = fields.Many2one(
        'accesorio.estado',
        string='Estado',
        required=True,
        ondelete='restrict'
    )
    
    subpartes_ids = fields.Many2many(
        'accesorio.subparte',
        'rep_acc_eval_subparte_rel',
        'eval_id', 'subparte_id',
        string='Subpartes Específicas',
        domain="[('tipo_id', '=', tipo_id)]",
        help="Subpartes específicas de este accesorio que fueron intervenidas"
    )
    
    observaciones = fields.Text('Observaciones')

    _sql_constraints = [
        ('reparacion_tipo_unique', 'unique(reparacion_id, tipo_id)',
         'Ya existe una evaluación de este accesorio para esta reparación.')
    ]

    @api.model
    def create(self, vals):
        _logger.info(f"ReparacionAccesorioEvaluacion.create() recibió: {vals}")
        
        if 'reparacion_id' not in vals:
            _logger.error("ERROR: reparacion_id no está en vals")
        else:
            _logger.info(f"reparacion_id en vals: {vals['reparacion_id']}")
        
        record = super().create(vals)
        
        _logger.info(f"Registro creado - ID: {record.id}, reparacion_id: {record.reparacion_id.id if record.reparacion_id else 'VACIO'}")
        
        return record

    def write(self, vals):
        _logger.info(f"ReparacionAccesorioEvaluacion.write() ID: {self.id}, vals: {vals}")
        result = super().write(vals)
        _logger.info(f"Después de write - reparacion_id: {self.reparacion_id.id if self.reparacion_id else 'VACIO'}")
        return result