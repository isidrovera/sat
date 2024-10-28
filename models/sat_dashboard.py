from odoo import models, fields, api
from datetime import datetime

class SatDashboard(models.Model):
    _name = 'sat.dashboard'

    def _get_data_por_mes(self, model_name, date_field, year):
        """Obtiene el total de registros por mes en un año específico para un modelo dado."""
        query = """
            SELECT extract(month from {date_field}) as mes, COUNT(id) as total
            FROM {table}
            WHERE extract(year from {date_field}) = %s
            GROUP BY mes
            ORDER BY mes
        """.format(date_field=date_field, table=self.env[model_name]._table)
        self.env.cr.execute(query, (year,))
        result = dict(self.env.cr.fetchall())
        # Asegurar que se devuelvan todos los meses, incluso si no tienen datos
        return {str(i): result.get(i, 0) for i in range(1, 13)}

    def _get_reparaciones_por_tecnico(self):
        """Obtiene el total de reparaciones asignadas a cada técnico."""
        query = """
            SELECT res_users.name as tecnico, COUNT(reparaciones_reparaciones.id) as total
            FROM reparaciones_reparaciones
            JOIN res_users ON reparaciones_reparaciones.responsable_id = res_users.id
            GROUP BY res_users.name
        """
        self.env.cr.execute(query)
        return dict(self.env.cr.fetchall())

    def _get_tickets_por_tecnico(self):
        """Obtiene el total de tickets asignados a cada técnico."""
        query = """
            SELECT res_users.name as tecnico, COUNT(ticket_alquiler.id) as total
            FROM ticket_alquiler
            JOIN res_users ON ticket_alquiler.responsable = res_users.id
            GROUP BY res_users.name
        """
        self.env.cr.execute(query)
        return dict(self.env.cr.fetchall())

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
