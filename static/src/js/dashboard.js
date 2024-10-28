/**@odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";

// Cargar Chart.js globalmente desde el CDN
const loadChartDataLabelsPlugin = () => {
    return new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels";
        script.onload = () => resolve();
        script.onerror = () => reject(new Error("No se pudo cargar ChartDataLabels"));
        document.head.appendChild(script);
    });
};

const actionRegistry = registry.category("actions");

class SatDashboard extends Component {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.filter = null;  // Filtro global para aplicar a los gráficos
        this._fetch_data();
    }

    async _fetch_data() {
        try {
            await loadChartDataLabelsPlugin(); // Cargar el plugin
            const result = await this.orm.call("sat.dashboard", "get_dashboard_data", [this.filter]);
            this._render_tiles(result);
            this._render_charts(result);
        } catch (error) {
            console.error("Error cargando ChartDataLabels: ", error);
        }
    }

    _render_tiles(data) {
        // Mostrar el número de registros en las tiles
        const evaluacionesTile = document.getElementById('total_evaluaciones');
        const reparacionesTile = document.getElementById('total_reparaciones');
        const alquileresTile = document.getElementById('total_alquileres');
        const maquinasTile = document.getElementById('total_maquinas');
    
        evaluacionesTile.textContent = data.total_evaluaciones;
        reparacionesTile.textContent = data.total_reparaciones;
        alquileresTile.textContent = data.total_alquileres;
        maquinasTile.textContent = data.total_maquinas;
    
        // Agregar eventos de clic para aplicar filtros y redirigir
        evaluacionesTile.addEventListener('click', () => this.applyFilter('evaluaciones'));
        reparacionesTile.addEventListener('click', () => this.applyFilter('reparaciones'));
        alquileresTile.addEventListener('click', () => this.applyFilter('alquileres'));
        maquinasTile.addEventListener('click', () => this.applyFilter('maquinas'));
    }
    
    applyFilter(filter) {
        // Actualizar el filtro global y recargar los datos
        this.filter = filter;
        this._fetch_data();  // Volver a cargar los datos con el filtro aplicado
    }

    _render_charts(data) {
        // Gráfico de barras: Evaluaciones, Reparaciones, Alquileres, Máquinas en Alquiler
        var ctx1 = document.getElementById("myBarChart").getContext("2d");
        var myBarChart = new Chart(ctx1, {
            type: 'bar',
            plugins: [ChartDataLabels],
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
                        var label = myBarChart.data.labels[index];
                        this.applyFilter(label.toLowerCase());  // Aplicar filtro basado en la etiqueta clickeada
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
