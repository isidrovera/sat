from odoo import models, fields, api

class SatDashboard(models.Model):
    _name = 'sat.dashboard'

    @api.model
    def get_dashboard_data(self):
        total_evaluaciones = self.env['evaluacion.personal'].search_count([])
        total_reparaciones = self.env['reparaciones.reparaciones'].search_count([])
        total_alquileres = self.env['ticket.alquiler'].search_count([])
        total_maquinas_alquiler = self.env['alquiler'].search_count([('estado_alquiler_id', '=', 'alquilada')])
        
        # Datos adicionales para hoy
        today = fields.Date.today()
        total_reparaciones_hoy = self.env['reparaciones.reparaciones'].search_count([('create_date', '=', today)])
        total_alquileres_hoy = self.env['ticket.alquiler'].search_count([('agenda', '=', today)])

        return {
            'total_evaluaciones': total_evaluaciones,
            'total_reparaciones': total_reparaciones,
            'total_alquileres': total_alquileres,
            'total_maquinas_alquiler': total_maquinas_alquiler,
            'total_reparaciones_hoy': total_reparaciones_hoy,
            'total_alquileres_hoy': total_alquileres_hoy,
            # Campos de coste/ingreso/beneficio si decides implementarlos más adelante
            'total_costes': 0,
            'total_ingresos': 0,
            'total_beneficio': 0,
        }
