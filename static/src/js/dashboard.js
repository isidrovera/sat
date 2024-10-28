/**@odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";
import Chart from 'chart.js/auto';
import ChartDataLabels from 'chartjs-plugin-datalabels'; // Asegúrate de incluir este plugin en tus assets

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
            // Renderizamos las tiles y los gráficos con los datos obtenidos
            this._render_tiles(result);
            this._render_charts(result);
        });
    }

    _render_tiles(data) {
        // Mostrar el número de registros en las tiles
        document.getElementById('total_evaluaciones').textContent = data.total_evaluaciones;
        document.getElementById('total_reparaciones').textContent = data.total_reparaciones;
        document.getElementById('total_alquileres').textContent = data.total_alquileres;
        document.getElementById('total_maquinas').textContent = data.total_maquinas;
    }

    _render_charts(data) {
        // Gráfico de barras: Evaluaciones, Reparaciones, Alquileres, Máquinas en Alquiler
        var ctx1 = document.getElementById("myBarChart").getContext("2d");
        var myBarChart = new Chart(ctx1, {
            type: 'bar',
            plugins: [ChartDataLabels], // Incluir el plugin para mostrar las etiquetas
            data: {
                labels: ['Evaluaciones', 'Reparaciones', 'Alquileres', 'Máquinas en Alquiler'],
                datasets: [{
                    label: 'Cantidad',
                    data: [data.total_evaluaciones, data.total_reparaciones, data.total_alquileres, data.total_maquinas],
                    backgroundColor: ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0'],
                }]
            },
            options: {
                plugins: {
                    datalabels: {
                        color: '#FFFFFF',
                        anchor: 'end',
                        align: 'top',
                        font: {
                            weight: 'bold'
                        }
                    }
                },
                onClick: (event, elements) => {
                    if (elements.length > 0) {
                        var index = elements[0].index;
                        var label = this.chart.data.labels[index];
                        this.navigateToDetails(label);
                    }
                }
            }
        });
    }

    navigateToDetails(label) {
        // Redireccionar basado en la etiqueta
        switch (label) {
            case 'Evaluaciones':
                window.location.href = '/web#action=your_action_id_for_evaluaciones&model=evaluacion.personal&view_type=list';
                break;
            case 'Reparaciones':
                window.location.href = '/web#action=sat.action_reparaciones_window&model=reparaciones.reparaciones&view_type=list';
                break;
            case 'Alquileres':
                window.location.href = '/web#action=your_action_id_for_alquileres&model=ticket.alquiler&view_type=list';
                break;
            case 'Máquinas en Alquiler':
                window.location.href = '/web#action=your_action_id_for_maquinas&model=alquiler&view_type=list';
                break;
            default:
                console.log('No action defined for this category');
        }
    }
}

SatDashboard.template = "sat.DashboardTemplate";
actionRegistry.add("sat_dashboard_tag", SatDashboard);
