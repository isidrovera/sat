from odoo import models, api

class SatDashboard(models.Model):
    _name = 'sat.dashboard'
    _description = 'Dashboard para el módulo SAT'

    @api.model
    def get_dashboard_data(self):
        # Obtener datos de los modelos
        total_maquinas = self.env['sat.sat'].search_count([])
        total_reparaciones = self.env['reparaciones.reparaciones'].search_count([])
        total_alquileres = self.env['ticket.alquiler'].search_count([])

        # Aquí podrías agregar más datos si deseas análisis adicionales (costes, ingresos, margen, etc.)
        total_costes = 50000
        total_ingresos = 150000
        total_beneficio = total_ingresos - total_costes

        return {
            'total_maquinas': total_maquinas,
            'total_reparaciones': total_reparaciones,
            'total_alquileres': total_alquileres,
            'total_costes': total_costes,
            'total_ingresos': total_ingresos,
            'total_beneficio': total_beneficio,
        }
