/**@odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";
const actionRegistry = registry.category("actions");

class SatDashboard extends Component {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this._fetch_data();
    }

    _fetch_data() {
        this.orm.call("sat.dashboard", "get_dashboard_data", []).then((result) => {
            // Actualizamos los gráficos con los datos
            this._render_charts(result);
        });
    }

    _render_charts(data) {
        // Gráfico de barras para reparaciones y tickets por mes
        var ctx1 = document.getElementById("barChartMes").getContext("2d");
        new Chart(ctx1, {
            type: 'bar',
            data: {
                labels: ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'],
                datasets: [{
                    label: 'Reparaciones',
                    data: Object.values(data.reparaciones_por_mes),
                    backgroundColor: '#36A2EB',
                }, {
                    label: 'Tickets de Alquiler',
                    data: Object.values(data.tickets_por_mes),
                    backgroundColor: '#FF6384',
                }]
            },
        });

        // Gráfico circular para reparaciones por técnico
        var ctx2 = document.getElementById("pieReparaciones").getContext("2d");
        new Chart(ctx2, {
            type: 'pie',
            data: {
                labels: Object.keys(data.reparaciones_por_tecnico),
                datasets: [{
                    data: Object.values(data.reparaciones_por_tecnico),
                    backgroundColor: ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0'],
                }]
            }
        });

        // Indicadores de reparaciones y tickets para hoy
        document.getElementById('reparacionesHoy').textContent = data.reparaciones_hoy;
        document.getElementById('ticketsHoy').textContent = data.tickets_hoy;
    }
}

SatDashboard.template = "sat.DashboardTemplate";
actionRegistry.add("sat_dashboard_tag", SatDashboard);
