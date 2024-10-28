/**@odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";

// Cargar Chart.js desde el CDN y el plugin de etiquetas de datos
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
        this._fetch_data();
    }

    async _fetch_data() {
        try {
            await loadChartDataLabelsPlugin(); // Cargar el plugin para etiquetas de datos
            const result = await this.orm.call("sat.dashboard", "get_dashboard_data", []);
            this._render_tiles(result);
            this._render_charts(result);
        } catch (error) {
            console.error("Error cargando datos para el dashboard: ", error);
        }
    }

    _render_tiles(data) {
        // Mostrar el número de registros en las tiles
        document.getElementById('total_maquinas').textContent = data.total_maquinas;
        document.getElementById('maquinas_disponibles').textContent = data.maquinas_disponibles;
        document.getElementById('maquinas_separadas').textContent = data.maquinas_separadas;
        document.getElementById('maquinas_no_disponibles').textContent = data.maquinas_no_disponibles;
        
        document.getElementById('maquinas_sin_revisar').textContent = data.maquinas_sin_revisar;
        document.getElementById('maquinas_en_revision').textContent = data.maquinas_en_revision;
        document.getElementById('maquinas_finalizadas').textContent = data.maquinas_finalizadas;
        
        document.getElementById('total_reparaciones').textContent = data.total_reparaciones;
        document.getElementById('reparaciones_hoy').textContent = data.reparaciones_hoy;
        document.getElementById('reparaciones_mes').textContent = data.reparaciones_mes;
        document.getElementById('reparaciones_ano').textContent = data.reparaciones_ano;
    }

    _render_charts(data) {
        // Gráfico de barras para máquinas por disponibilidad
        const disponibilidadCtx = document.getElementById("disponibilidadChart").getContext("2d");
        new Chart(disponibilidadCtx, {
            type: 'bar',
            plugins: [ChartDataLabels],
            data: {
                labels: ['Disponibles', 'Separadas', 'No disponibles'],
                datasets: [{
                    label: 'Máquinas',
                    data: [
                        data.maquinas_disponibles,
                        data.maquinas_separadas,
                        data.maquinas_no_disponibles
                    ],
                    backgroundColor: ['#4BC0C0', '#FFCE56', '#FF6384'],
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
                }
            }
        });

        // Gráfico de pastel para máquinas por estado
        const estadoCtx = document.getElementById("estadoChart").getContext("2d");
        new Chart(estadoCtx, {
            type: 'pie',
            plugins: [ChartDataLabels],
            data: {
                labels: ['Sin Revisar', 'En Revisión', 'Finalizadas'],
                datasets: [{
                    label: 'Máquinas por Estado',
                    data: [
                        data.maquinas_sin_revisar,
                        data.maquinas_en_revision,
                        data.maquinas_finalizadas
                    ],
                    backgroundColor: ['#36A2EB', '#FFCE56', '#4BC0C0'],
                }]
            },
            options: {
                plugins: {
                    datalabels: {
                        color: '#FFFFFF',
                        font: {
                            weight: 'bold'
                        }
                    }
                }
            }
        });

        // Gráfico de barras para reparaciones por técnico
        const tecnicosCtx = document.getElementById("tecnicosChart").getContext("2d");
        const tecnicosLabels = Object.keys(data.tecnicos_totales);
        const tecnicosData = Object.values(data.tecnicos_totales);

        new Chart(tecnicosCtx, {
            type: 'bar',
            plugins: [ChartDataLabels],
            data: {
                labels: tecnicosLabels,
                datasets: [{
                    label: 'Reparaciones',
                    data: tecnicosData,
                    backgroundColor: '#FF6384',
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
                scales: {
                    x: {
                        ticks: {
                            autoSkip: false,
                        }
                    }
                }
            }
        });

        // Gráfico de pastel para máquinas por asesora
        const asesoraCtx = document.getElementById("asesoraChart").getContext("2d");
        const asesoraLabels = Object.keys(data.asesora_totales);
        const asesoraData = Object.values(data.asesora_totales);

        new Chart(asesoraCtx, {
            type: 'pie',
            plugins: [ChartDataLabels],
            data: {
                labels: asesoraLabels,
                datasets: [{
                    label: 'Máquinas por Asesora',
                    data: asesoraData,
                    backgroundColor: ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF'],
                }]
            },
            options: {
                plugins: {
                    datalabels: {
                        color: '#FFFFFF',
                        font: {
                            weight: 'bold'
                        }
                    }
                }
            }
        });
    }
}

SatDashboard.template = "sat.DashboardTemplate";
actionRegistry.add("sat_dashboard_tag", SatDashboard);
