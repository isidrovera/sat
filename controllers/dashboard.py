
# -*- coding: utf-8 -*-

from odoo import http
from odoo.addons.web.controllers.report import ReportController


class DashboardController(http.Controller):

    @http.route(
        '/dashboard/data',
        auth='user',
        type='jsonrpc',
        methods=['POST'],
    )
    def get_dashboard_data(self, **kw):
        """
        Obtiene estadísticas de servicios agrupadas por
        técnico responsable y tipo de servicio.
        Compatible con Odoo 19.
        """
        env = http.request.env

        start_date = kw.get('start_date')
        end_date = kw.get('end_date')

        domain = []

        if start_date:
            domain.append(
                ('agenda', '>=', start_date)
            )

        if end_date:
            domain.append(
                ('agenda', '<=', end_date)
            )

        data = env['ticket.alquiler'].read_group(
            domain,
            ['responsable', 'tipo_servicio_id'],
            ['responsable', 'tipo_servicio_id'],
            lazy=False,
        )

        results = {}

        for record in data:
            responsable = record.get('responsable')
            tipo_servicio = record.get('tipo_servicio_id')

            if not responsable or not tipo_servicio:
                continue

            tech = (
                responsable[1]
                if isinstance(responsable, (list, tuple))
                else str(responsable)
            )

            service_type = (
                tipo_servicio[1]
                if isinstance(tipo_servicio, (list, tuple))
                else str(tipo_servicio)
            )

            if tech not in results:
                results[tech] = {}

            count = record.get(
                '__count',
                record.get(
                    'tipo_servicio_id_count',
                    0,
                ),
            )

            results[tech][service_type] = (
                results[tech].get(service_type, 0)
                + count
            )

        return results


class EquipmentVisitReportController(ReportController):

    @http.route(
        ['/report/pdf/sat.report_equipment_visit/<int:id>'],
        type='http',
        auth='user',
        methods=['GET'],
    )
    def report_equipment_visit_pdf(self, id, **kwargs):
        """
        Genera las imágenes de gráficos antes de
        renderizar el informe PDF.
        Compatible con Odoo 19.
        """
        report = http.request.env[
            'equipment.visit.report'
        ].browse(id).exists()

        if not report:
            return http.request.not_found()

        report.generate_chart_images()

        return super().report_routes(
            reportname='sat.report_equipment_visit',
            docids=str(report.id),
            converter='pdf',
            **kwargs
        )
