from odoo import models, fields, api

class SatDashboard(models.Model):
    _name = 'sat.dashboard'

    @api.model
    def get_dashboard_data(self):
        current_year = fields.Date.today().year
        today = fields.Date.today()

        # Total de reparaciones por mes para el año actual
        reparaciones_por_mes = self._get_data_por_mes('reparaciones.reparaciones', 'create_date', current_year)
        
        # Total de tickets por mes para el año actual
        tickets_por_mes = self._get_data_por_mes('ticket.alquiler', 'agenda', current_year)
        
        # Reparaciones programadas para hoy
        reparaciones_hoy = self.env['reparaciones.reparaciones'].search_count([('create_date', '=', today)])
        
        # Tickets programados para hoy
        tickets_hoy = self.env['ticket.alquiler'].search_count([('agenda', '=', today)])
        
        # Evaluaciones de personal para el año actual
        total_evaluaciones = self.env['evaluacion.personal'].search_count([('fecha', '>=', f'{current_year}-01-01'), ('fecha', '<=', f'{current_year}-12-31')])

        # Reparaciones y tickets por técnico
        reparaciones_por_tecnico = self._get_reparaciones_por_tecnico()
        tickets_por_tecnico = self._get_tickets_por_tecnico()

        return {
            'reparaciones_por_mes': reparaciones_por_mes,
            'tickets_por_mes': tickets_por_mes,
            'reparaciones_hoy': reparaciones_hoy,
            'tickets_hoy': tickets_hoy,
            'total_evaluaciones': total_evaluaciones,
            'reparaciones_por_tecnico': reparaciones_por_tecnico,
            'tickets_por_tecnico': tickets_por_tecnico,
        }

    def _get_data_por_mes(self, model, date_field, year):
        query = f"""
            SELECT EXTRACT(MONTH FROM {date_field}) as mes, COUNT(id)
            FROM {self.env[model]._table}
            WHERE EXTRACT(YEAR FROM {date_field}) = %s
            GROUP BY mes
        """
        self.env.cr.execute(query, (year,))
        return dict(self.env.cr.fetchall())

    def _get_reparaciones_por_tecnico(self):
        query = """
            SELECT res_users.name, COUNT(reparaciones_reparaciones.id)
            FROM reparaciones_reparaciones
            JOIN res_users ON reparaciones_reparaciones.responsable_id = res_users.id
            GROUP BY res_users.name
        """
        self.env.cr.execute(query)
        return dict(self.env.cr.fetchall())

    def _get_tickets_por_tecnico(self):
        query = """
            SELECT res_users.name, COUNT(ticket_alquiler.id)
            FROM ticket_alquiler
            JOIN res_users ON ticket_alquiler.responsable = res_users.id
            GROUP BY res_users.name
        """
        self.env.cr.execute(query)
        return dict(self.env.cr.fetchall())
