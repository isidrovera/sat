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
        // Gráfico de barras (Evaluaciones, Reparaciones, Alquileres)
        var ctx1 = document.getElementById("myBarChart").getContext("2d");
        new Chart(ctx1, {
            type: 'bar',
            data: {
                labels: ['Evaluaciones', 'Reparaciones', 'Alquileres', 'Máquinas en Alquiler'],
                datasets: [{
                    label: 'Cantidad',
                    data: [data.total_evaluaciones, data.total_reparaciones, data.total_alquileres, data.total_maquinas_alquiler],
                    backgroundColor: ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0'],
                }]
            },
            options: {
                plugins: {
                    datalabels: {
                        display: true,  // Mostrar etiquetas
                        color: 'black', // Color de las etiquetas
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
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
            options: {
                plugins: {
                    datalabels: {
                        display: true,  // Mostrar etiquetas en el gráfico circular
                        color: 'black'
                    }
                }
            }
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
                    legend: { display: false },
                    datalabels: {
                        display: true,
                        color: 'black'
                    }
                }
            }
        });
    }
}

SatDashboard.template = "sat.DashboardTemplate";
actionRegistry.add("sat_dashboard_tag", SatDashboard);
