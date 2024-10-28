from odoo import _, api, fields, models, tools


class Incidencia(models.Model):
    _name = 'taller.incidencia'
    _description = 'Registro de Incidencias en el Taller'

    name = fields.Char(string='ID de Incidencia', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
    fecha_hora = fields.Datetime(string='Fecha y Hora', default=fields.Datetime.now)
    tipo = fields.Selection([
        ('reclamo', 'Reclamo'),
        ('reparacion', 'Reparación'),
        ('mantenimiento', 'Mantenimiento'),
    ], string='Tipo de Incidencia', default='reclamo')
    descripcion = fields.Text(string='Descripción')
    equipo_id = fields.Many2one('sat.sat', string='Equipo Afectado')
    cliente_id = fields.Many2one('res.partner', string='Cliente Relacionado')
    estado = fields.Selection([
        ('reportado', 'Reportado'),
        ('proceso', 'En Proceso'),
        ('resuelto', 'Resuelto'),
    ], string='Estado de la Incidencia', default='reportado')
    prioridad = fields.Selection([
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
    ], string='Prioridad', default='baja')
    empleado_id = fields.Many2one('hr.employee', string='Empleado Asignado')
    acciones = fields.Text(string='Acciones Tomadas')
    fecha_resolucion = fields.Datetime(string='Fecha de Resolución')
    comentarios_cliente = fields.Text(string='Comentarios del Cliente')
    costos = fields.Float(string='Costos Asociados')
    
    
    @api.model
    def create(self, vals):
        # We generate a standard reference
        vals['name'] = self.env['ir.sequence'].next_by_code('taller.incidencia')or '/'
        return super(Incidencia,self).create(vals) 
