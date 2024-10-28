from odoo import models, fields, api

class SatDashboard(models.Model):
    _name = 'sat.dashboard'
    _description = 'Dashboard de análisis'

    @api.model
    def get_dashboard_data(self):
        # Contar el número de evaluaciones del personal
        total_evaluaciones = self.env['evaluacion.personal'].search_count([])

        # Contar el número de reparaciones
        total_reparaciones = self.env['reparaciones.reparaciones'].search_count([])

        # Contar el número de tickets de alquiler
        total_alquileres = self.env['ticket.alquiler'].search_count([])

        # Contar el número de máquinas en alquiler
        total_maquinas = self.env['alquiler'].search_count([])

        # Obtener las puntuaciones de las evaluaciones
        puntuaciones_evaluaciones = self.env['evaluacion.personal'].read_group(
            [('total_score', '!=', False)], ['total_score'], ['total_score']
        )

        # Suponiendo que tienes una lógica para calcular los costos, ingresos y beneficios
        total_costes = 50000  # Calcula el total de costes (puede ser dinámico)
        total_ingresos = 120000  # Calcula el total de ingresos (puede ser dinámico)
        total_beneficio = total_ingresos - total_costes  # Beneficio como la diferencia

        return {
            'total_evaluaciones': total_evaluaciones,
            'total_reparaciones': total_reparaciones,
            'total_alquileres': total_alquileres,
            'total_maquinas': total_maquinas,
            'total_costes': total_costes,
            'total_ingresos': total_ingresos,
            'total_beneficio': total_beneficio,
            'puntuaciones_evaluaciones': [p['total_score'] for p in puntuaciones_evaluaciones]
        }
