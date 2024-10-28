from odoo import models, api

class SatDashboard(models.Model):
    _name = 'sat.dashboard'
    _description = 'Dashboard para el módulo SAT'

    @api.model
    def get_dashboard_data(self):
        # Obtener datos de los modelos
        total_maquinas = self.env['sat.sat'].search_count([])
        total_reparaciones = self.env['reparaciones.reparaciones'].search_count([])
        total_alquileres = self.env['sat.alquiler'].search_count([])

        return {
            'total_maquinas': total_maquinas,
            'total_reparaciones': total_reparaciones,
            'total_alquileres': total_alquileres,
        }
