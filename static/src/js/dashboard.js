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
            // Actualizamos los valores en los gráficos
            this._render_charts(result);
        });
    }

    _render_charts(data) {
        // Gráfico de barras (máquinas, reparaciones, alquileres)
        var ctx1 = document.getElementById("myBarChart").getContext("2d");
        new Chart(ctx1, {
            type: 'bar',
            data: {
                labels: ['Máquinas', 'Reparaciones', 'Alquileres'],
                datasets: [{
                    label: 'Cantidad',
                    data: [data.total_maquinas, data.total_reparaciones, data.total_alquileres],
                    backgroundColor: ['#36A2EB', '#FF6384', '#FFCE56'],
                }]
            },
        });

        // Gráfico circular (Costes, Ingresos, Beneficio)
        var ctx2 = document.getElementById("myPieChart").getContext("2d");
        new Chart(ctx2, {
            type: 'pie',
            data: {
                labels: ['Costes', 'Ingresos', 'Beneficio'],
                datasets: [{
                    data: [data.total_costes, data.total_ingresos, data.total_beneficio],
                    backgroundColor: ['#FF6384', '#36A2EB', '#FFCE56'],
                }]
            },
        });

        // Gráfico de tipo "Gauge" o medidor para representar el beneficio sobre el coste
        var ctx3 = document.getElementById("myGaugeChart").getContext("2d");
        new Chart(ctx3, {
            type: 'doughnut',
            data: {
                labels: ['Coste', 'Beneficio'],
                datasets: [{
                    data: [data.total_costes, data.total_beneficio],
                    backgroundColor: ['#FF6384', '#36A2EB'],
                    hoverOffset: 4
                }]
            },
            options: {
                circumference: Math.PI,
                rotation: Math.PI,
                cutout: '70%',
                plugins: {
                    legend: { display: false }
                }
            }
        });
    }
}

SatDashboard.template = "sat.DashboardTemplate";
actionRegistry.add("sat_dashboard_tag", SatDashboard);
