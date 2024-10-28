/**@odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";

// Cargar Chart.js desde el CDN y el plugin de etiquetas de datos
const loadChartDataLabelsPlugin = () => {
    console.log('Iniciando carga del plugin ChartDataLabels...');
    return new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels";
        script.onload = () => {
            console.log('Plugin ChartDataLabels cargado exitosamente');
            resolve();
        };
        script.onerror = (error) => {
            console.error('Error al cargar el plugin ChartDataLabels:', error);
            reject(new Error("No se pudo cargar ChartDataLabels"));
        };
        document.head.appendChild(script);
    });
};

const actionRegistry = registry.category("actions");

class SatDashboard extends Component {
    setup() {
        console.log('Iniciando setup del componente SatDashboard');
        super.setup();
        this.orm = useService("orm");
        console.log('Servicio ORM inicializado');
        this._fetch_data();
    }

    async _fetch_data() {
        console.log('Iniciando fetch de datos del dashboard...');
        try {
            await loadChartDataLabelsPlugin();
            console.log('Realizando llamada ORM a get_dashboard_data...');
            const result = await this.orm.call("sat.dashboard", "get_dashboard_data", []);
            console.log('Datos recibidos del servidor:', result);
            
            this._render_tiles(result);
            this._render_charts(result);
        } catch (error) {
            console.error("Error cargando datos para el dashboard: ", error);
        }
    }

    _render_tiles(data) {
        console.log('Iniciando renderizado de tiles con datos:', data);
        try {
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
            
            console.log('Tiles renderizadas exitosamente');
        } catch (error) {
            console.error('Error al renderizar tiles:', error);
        }
    }

    _render_charts(data) {
        console.log('Iniciando renderizado de gráficos...');

        try {
            // Gráfico de barras para máquinas por disponibilidad
            console.log('Renderizando gráfico de disponibilidad...');
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
            console.log('Gráfico de disponibilidad renderizado');

            // Gráfico de pastel para máquinas por estado
            console.log('Renderizando gráfico de estado...');
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
            console.log('Gráfico de estado renderizado');

            // Gráfico de barras para reparaciones por técnico
            console.log('Renderizando gráfico de técnicos...');
            const tecnicosCtx = document.getElementById("tecnicosChart").getContext("2d");
            const tecnicosLabels = Object.keys(data.tecnicos_totales);
            const tecnicosData = Object.values(data.tecnicos_totales);
            console.log('Datos de técnicos:', { labels: tecnicosLabels, data: tecnicosData });

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
            console.log('Gráfico de técnicos renderizado');

            // Gráfico de pastel para máquinas por asesora
            console.log('Renderizando gráfico de asesoras...');
            const asesoraCtx = document.getElementById("asesoraChart").getContext("2d");
            const asesoraLabels = Object.keys(data.asesora_totales);
            const asesoraData = Object.values(data.asesora_totales);
            console.log('Datos de asesoras:', { labels: asesoraLabels, data: asesoraData });

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
            console.log('Gráfico de asesoras renderizado');
            console.log('Todos los gráficos han sido renderizados exitosamente');
        } catch (error) {
            console.error('Error al renderizar gráficos:', error);
        }
    }
}

SatDashboard.template = "sat.DashboardTemplate";
actionRegistry.add("sat_dashboard_tag", SatDashboard);