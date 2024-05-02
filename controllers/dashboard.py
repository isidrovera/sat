from odoo import http
from datetime import datetime

class DashboardController(http.Controller):
    @http.route('/dashboard/data', auth='user', type='json')
    def get_dashboard_data(self, start_date=None, end_date=None):
        domain = []
        if start_date and end_date:
            domain.append(('agenda', '>=', start_date))
            domain.append(('agenda', '<=', end_date))

        # Agregación de datos por técnico y tipo de servicio
        data = self.env['ticket.alquiler'].read_group(
            domain,
            ['responsable', 'tipo_servicio_id'],
            ['responsable', 'tipo_servicio_id'],
            lazy=False
        )

        # Convertir resultados a un formato más amigable para el frontend
        results = {}
        for record in data:
            tech = record['responsable'][1]  # Nombre del técnico
            if tech not in results:
                results[tech] = {}
            service_type = record['tipo_servicio_id'][1]  # Tipo de servicio
            results[tech][service_type] = record['tipo_servicio_id_count']

        return results
