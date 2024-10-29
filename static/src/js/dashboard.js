/**@odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted } from "@odoo/owl";

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
        this.dashboardData = null;

        // Usar onMounted para asegurarnos que el DOM está listo
        onMounted(() => {
            console.log('Componente montado, iniciando fetch de datos...');
            this._fetch_data();
        });
    }

    async _fetch_data() {
        console.log('Iniciando fetch de datos del dashboard...');
        try {
            await loadChartDataLabelsPlugin();
            console.log('Realizando llamada ORM a get_dashboard_data...');
            const result = await this.orm.call("sat.dashboard", "get_dashboard_data", []);
            console.log('Datos recibidos del servidor:', result);
            
            this.dashboardData = result;
            this._render_tiles();
            this._render_charts();
        } catch (error) {
            console.error("Error cargando datos para el dashboard: ", error);
        }
    }

    _updateElementContent(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = value;
            console.log(`Actualizado elemento ${elementId} con valor ${value}`);
        } else {
            console.warn(`Elemento no encontrado: ${elementId}`);
        }
    }

    _render_tiles() {
        console.log('Iniciando renderizado de tiles...');
        if (!this.dashboardData) {
            console.error('No hay datos disponibles para renderizar las tiles');
            return;
        }

        const elements = [
            { id: 'total_maquinas', value: this.dashboardData.total_maquinas },
            { id: 'maquinas_disponibles', value: this.dashboardData.maquinas_disponibles },
            { id: 'maquinas_separadas', value: this.dashboardData.maquinas_separadas },
            { id: 'maquinas_no_disponibles', value: this.dashboardData.maquinas_no_disponibles },
            { id: 'maquinas_sin_revisar', value: this.dashboardData.maquinas_sin_revisar },
            { id: 'maquinas_en_revision', value: this.dashboardData.maquinas_en_revision },
            { id: 'maquinas_finalizadas', value: this.dashboardData.maquinas_finalizadas },
            { id: 'total_reparaciones', value: this.dashboardData.total_reparaciones },
            { id: 'reparaciones_en_revision', value: this.dashboardData.reparaciones_en_revision },
            { id: 'reparaciones_hoy', value: this.dashboardData.reparaciones_hoy },
            { id: 'reparaciones_mes', value: this.dashboardData.reparaciones_mes },
            { id: 'reparaciones_ano', value: this.dashboardData.reparaciones_ano }
        ];

        let successCount = 0;
        elements.forEach(({ id, value }) => {
            try {
                this._updateElementContent(id, value);
                successCount++;
            } catch (error) {
                console.error(`Error actualizando elemento ${id}:`, error);
            }
        });

        console.log(`Tiles renderizadas: ${successCount} de ${elements.length}`);
    }

    _getChartContext(canvasId) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas no encontrado: ${canvasId}`);
            return null;
        }
        return canvas.getContext("2d");
    }

    _render_charts() {
        console.log('Iniciando renderizado de gráficos...');
        if (!this.dashboardData) {
            console.error('No hay datos disponibles para renderizar los gráficos');
            return;
        }

        try {
            // Gráfico de disponibilidad
            const disponibilidadCtx = this._getChartContext("disponibilidadChart");
            if (disponibilidadCtx) {
                console.log('Renderizando gráfico de disponibilidad...');
                new Chart(disponibilidadCtx, {
                    type: 'bar',
                    plugins: [ChartDataLabels],
                    data: {
                        labels: ['Disponibles', 'Separadas', 'No disponibles'],
                        datasets: [{
                            label: 'Máquinas',
                            data: [
                                this.dashboardData.maquinas_disponibles,
                                this.dashboardData.maquinas_separadas,
                                this.dashboardData.maquinas_no_disponibles
                            ],
                            backgroundColor: ['#4BC0C0', '#FFCE56', '#FF6384'],
                        }]
                    },
                    options: {
                        plugins: {
                            legend: {
                                display: true,
                                position: 'top'
                            },
                            datalabels: {
                                display: true,
                                color: '#FFFFFF',
                                anchor: 'center', // Centra la etiqueta en la barra
                                align: 'center',  // Alinea el texto al centro
                                font: {
                                    weight: 'bold',
                                    size: 14
                                },
                                formatter: function(value) {
                                    return value; // Muestra el valor numérico
                                },
                                padding: 6
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true
                            }
                        }
                    }
                });
                console.log('Gráfico de disponibilidad renderizado exitosamente');
            }
            
           // Gráfico de estado
            const estadoCtx = this._getChartContext("estadoChart");
            if (estadoCtx) {
                console.log('Renderizando gráfico de estado...');
                new Chart(estadoCtx, {
                    type: 'pie',
                    plugins: [ChartDataLabels],
                    data: {
                        labels: ['Sin Revisar', 'En Revisión', 'Finalizadas', 'Problemas'],
                        datasets: [{
                            label: 'Máquinas por Estado',
                            data: [
                                this.dashboardData.maquinas_sin_revisar,
                                this.dashboardData.maquinas_en_revision,
                                this.dashboardData.maquinas_finalizadas,
                                this.dashboardData.maquinas_problemas
                            ],
                            backgroundColor: [
                                '#36A2EB',  // Sin Revisar (Azul claro)
                                '#FFCE56',  // En Revisión (Amarillo)
                                '#4BC0C0',  // Finalizadas (Verde)
                                '#FF6384'   // Problemas (Rojo)
                            ],
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        layout: {
                            padding: 20,
                        },
                        plugins: {
                            legend: {
                                display: true,
                                position: 'right',
                                labels: {
                                    boxWidth: 20,
                                }
                            },
                            datalabels: {
                                display: true, // Muestra los datos en las secciones
                                color: 'white',
                                font: {
                                    size: 16,
                                    weight: 'bold'
                                },
                                formatter: (value) => value, // Muestra el valor numérico
                                anchor: 'center', // Posiciona la etiqueta en el centro de cada sección
                                align: 'center'  // Centra el texto dentro de cada sección
                            }
                        }
                    },
                    plugins: [{
                        beforeDraw: function(chart) {
                            const width = chart.width;
                            const height = chart.height;
                            const ctx = chart.ctx;
                            ctx.restore();
                            const fontSize = 16;
                            ctx.font = fontSize + "px Arial";
                            ctx.textBaseline = "middle";
                            const text = "Máquinas por Estado";
                            const textX = Math.round((width - ctx.measureText(text).width) / 2);
                            const textY = Math.round((height + chart.chartArea.top) / 2);
                            ctx.fillText(text, textX, textY);
                            ctx.save();
                        }
                    }]
                });
                console.log('Gráfico de estado renderizado exitosamente');
            }

            // Gráfico de técnicos
            const tecnicosCtx = this._getChartContext("tecnicosChart");
            if (tecnicosCtx) {
                console.log('Renderizando gráfico de técnicos...');
                const tecnicosLabels = Object.keys(this.dashboardData.tecnicos_totales);
                const tecnicosData = Object.values(this.dashboardData.tecnicos_totales);
                console.log('Datos de técnicos:', { labels: tecnicosLabels, data: tecnicosData });

                // Array de colores para cada barra
                const barColors = [
                    '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40',
                    '#E7E9ED', '#71B37C', '#FF6384', '#36A2EB'
                ];

                new Chart(tecnicosCtx, {
                    type: 'bar',
                    plugins: [ChartDataLabels],
                    data: {
                        labels: tecnicosLabels,
                        datasets: [{
                            label: 'Reparaciones',
                            data: tecnicosData,
                            backgroundColor: barColors.slice(0, tecnicosData.length), // Asignar colores según la cantidad de barras
                        }]
                    },
                    options: {
                        plugins: {
                            legend: {
                                display: true,
                                position: 'top'
                            },
                            datalabels: {
                                display: true,
                                color: '#FFFFFF',
                                anchor: 'center', // Centra la etiqueta en la barra
                                align: 'center',  // Alinea el texto al centro
                                font: {
                                    weight: 'bold',
                                    size: 14
                                },
                                formatter: function(value) {
                                    return value; // Muestra el valor numérico
                                },
                                padding: 6
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true
                            },
                            x: {
                                ticks: {
                                    autoSkip: false,
                                }
                            }
                        }
                    }
                });
                console.log('Gráfico de técnicos renderizado exitosamente');
            }


            // Gráfico de asesoras
            const asesoraCtx = this._getChartContext("asesoraChart");
            if (asesoraCtx) {
                console.log('Renderizando gráfico de asesoras...');
                const asesoraLabels = Object.keys(this.dashboardData.asesora_totales);
                const asesoraData = Object.values(this.dashboardData.asesora_totales);
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
                console.log('Gráfico de asesoras renderizado exitosamente');
            }
        } catch (error) {
            console.error('Error al renderizar gráficos:', error);
        }
    }
}

SatDashboard.template = "sat.DashboardTemplate";
actionRegistry.add("sat_dashboard_tag", SatDashboard);