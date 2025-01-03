from odoo import http

class DashboardController(http.Controller):
    @http.route('/dashboard/data', auth='public', type='json')
    def get_dashboard_data(self, **kw):
        env = http.request.env
        start_date = kw.get('start_date')
        end_date = kw.get('end_date')
        domain = []
        if start_date and end_date:
            domain.append(('agenda', '>=', start_date))
            domain.append(('agenda', '<=', end_date))

        # Asegúrate de usar env para acceder a los modelos
        data = env['ticket.alquiler'].read_group(
            domain,
            ['responsable', 'tipo_servicio_id'],
            ['responsable', 'tipo_servicio_id'],
            lazy=False
        )

        results = {}
        for record in data:
            tech = record['responsable'][1]
            if tech not in results:
                results[tech] = {}
            service_type = record['tipo_servicio_id'][1]
            results[tech][service_type] = record['tipo_servicio_id_count']

        return results
