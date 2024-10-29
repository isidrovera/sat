/**@odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted } from "@odoo/owl";

// Cargar ECharts desde el CDN
const loadECharts = () => {
    console.log('Iniciando carga de Apache ECharts...');
    return new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "https://cdn.jsdelivr.net/npm/echarts/dist/echarts.min.js";
        script.onload = () => {
            console.log('ECharts cargado exitosamente');
            resolve();
        };
        script.onerror = (error) => {
            console.error('Error al cargar ECharts:', error);
            reject(new Error("No se pudo cargar ECharts"));
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
            await loadECharts();  // Cargar ECharts en lugar de Chart.js
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

    _getChartElement(elementId) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`Elemento de gráfico no encontrado: ${elementId}`);
            return null;
        }
        console.log(`Elemento de gráfico encontrado: ${elementId}`);
        return element;
    }

    _render_charts() {
        console.log('Iniciando renderizado de gráficos...');
        if (!this.dashboardData) {
            console.error('No hay datos disponibles para renderizar los gráficos');
            return;
        }

        try {
            // Gráfico de disponibilidad
            const disponibilidadElement = this._getChartElement("disponibilidadChart");
            if (disponibilidadElement) {
                console.log('Renderizando gráfico de disponibilidad...');
                const disponibilidadChart = echarts.init(disponibilidadElement);

                disponibilidadChart.setOption({
                    title: { 
                        text: 'Disponibilidad de Máquinas',
                        left: 'center',
                        textStyle: {
                            fontSize: 16,
                            fontWeight: 'bold',
                        }
                    },
                    tooltip: {
                        trigger: 'axis',
                        axisPointer: { type: 'shadow' }
                    },
                    xAxis: {
                        type: 'category',
                        data: ['Disponibles', 'Separadas', 'No Disponibles'],
                        axisLabel: {
                            fontSize: 12,
                            fontWeight: 'bold',
                        }
                    },
                    yAxis: {
                        type: 'value',
                        axisLabel: {
                            fontSize: 12,
                        }
                    },
                    series: [{
                        name: 'Máquinas',
                        type: 'bar',
                        data: [
                            this.dashboardData.maquinas_disponibles,
                            this.dashboardData.maquinas_separadas,
                            this.dashboardData.maquinas_no_disponibles
                        ],
                        itemStyle: {
                            color: '#4BC0C0' // Color personalizado para las barras
                        },
                        label: {
                            show: true,
                            position: 'top',
                            fontSize: 12,
                            fontWeight: 'bold',
                            color: '#333',
                            formatter: '{c}', // Muestra el valor numérico
                        },
                        emphasis: {
                            focus: 'series'
                        },
                        animationDuration: 1000,
                        animationEasing: 'cubicInOut'
                    }],
                    grid: {
                        left: '3%',
                        right: '4%',
                        bottom: '3%',
                        containLabel: true
                    }
                });

                console.log('Gráfico de disponibilidad renderizado exitosamente');
            }

            // Gráfico de estado
            const estadoElement = this._getChartElement("estadoChart");
            if (estadoElement) {
                console.log('Renderizando gráfico de estado...');
                const estadoChart = echarts.init(estadoElement);
                estadoChart.setOption({
                    title: { text: 'Estado de Máquinas' },
                    tooltip: { trigger: 'item' },
                    series: [{
                        name: 'Estado',
                        type: 'pie',
                        data: [
                            { value: this.dashboardData.maquinas_sin_revisar, name: 'Sin Revisar' },
                            { value: this.dashboardData.maquinas_en_revision, name: 'En Revisión' },
                            { value: this.dashboardData.maquinas_finalizadas, name: 'Finalizadas' },
                            { value: this.dashboardData.maquinas_problemas, name: 'Problemas' }
                        ]
                    }]
                });
                console.log('Gráfico de estado renderizado exitosamente');
            }

            // Gráfico de técnicos
            const tecnicosElement = this._getChartElement("tecnicosChart");
            if (tecnicosElement) {
                console.log('Renderizando gráfico de técnicos...');
                const tecnicosChart = echarts.init(tecnicosElement);
                const tecnicosLabels = Object.keys(this.dashboardData.tecnicos_totales);
                const tecnicosData = Object.values(this.dashboardData.tecnicos_totales);
                tecnicosChart.setOption({
                    title: { text: 'Reparaciones por Técnico' },
                    tooltip: {},
                    xAxis: { type: 'category', data: tecnicosLabels },
                    yAxis: {},
                    series: [{
                        type: 'bar',
                        data: tecnicosData
                    }]
                });
                console.log('Gráfico de técnicos renderizado exitosamente');
            }

            // Gráfico de asesoras
            const asesoraElement = this._getChartElement("asesoraChart");
            if (asesoraElement) {
                console.log('Renderizando gráfico de asesoras...');
                const asesoraChart = echarts.init(asesoraElement);
                const asesoraLabels = Object.keys(this.dashboardData.asesora_totales);
                const asesoraData = Object.values(this.dashboardData.asesora_totales);
                asesoraChart.setOption({
                    title: { text: 'Máquinas por Asesora' },
                    tooltip: { trigger: 'item' },
                    series: [{
                        type: 'pie',
                        data: asesoraLabels.map((label, index) => ({ value: asesoraData[index], name: label }))
                    }]
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
