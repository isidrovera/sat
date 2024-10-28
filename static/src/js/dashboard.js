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
        // Llamamos al método get_dashboard_data del modelo sat.dashboard
        this.orm.call("sat.dashboard", "get_dashboard_data", []).then((result) => {
            // Renderizamos los gráficos con los datos obtenidos
            this._render_charts(result);
        });
    }

    _render_charts(data) {
        // Gráfico de barras: Evaluaciones, Reparaciones, Alquileres, Máquinas en Alquiler
        var ctx1 = document.getElementById("myBarChart").getContext("2d");
        new Chart(ctx1, {
            type: 'bar',
            data: {
                labels: ['Evaluaciones', 'Reparaciones', 'Alquileres', 'Máquinas en Alquiler'],
                datasets: [{
                    label: 'Cantidad',
                    data: [data.total_evaluaciones, data.total_reparaciones, data.total_alquileres, data.total_maquinas],
                    backgroundColor: ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0'],
                }]
            },
        });

        // Gráfico circular: Costes, Ingresos, Beneficio
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

        // Gráfico de tipo Gauge: Relación entre Coste y Beneficio
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

        // Gráfico adicional de línea: Evolución de las puntuaciones de evaluaciones del personal
        var ctx4 = document.getElementById("myLineChart").getContext("2d");
        new Chart(ctx4, {
            type: 'line',
            data: {
                labels: data.puntuaciones_evaluaciones.map((_, idx) => `Evaluación ${idx + 1}`),
                datasets: [{
                    label: 'Puntuación de Evaluaciones',
                    data: data.puntuaciones_evaluaciones,
                    borderColor: '#36A2EB',
                    fill: false
                }]
            },
        });
    }
}

SatDashboard.template = "sat.DashboardTemplate";
actionRegistry.add("sat_dashboard_tag", SatDashboard);
