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
        this.action = useService("action"); 
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
            { id: 'total_maquinas', value: this.dashboardData.total_maquinas, res_model: 'sat.sat', action_id: 'sat.sat.action_window', domain: [] },
            { id: 'maquinas_disponibles', value: this.dashboardData.maquinas_disponibles, res_model: 'sat.sat', action_id: 'your_module.action_sat_sat_view', domain: [['estado', '=', 'disponible']] },
            { id: 'maquinas_separadas', value: this.dashboardData.maquinas_separadas, res_model: 'sat.sat', action_id: 'your_module.action_sat_sat_view', domain: [['estado', '=', 'separada']] },
            { id: 'maquinas_no_disponibles', value: this.dashboardData.maquinas_no_disponibles, res_model: 'sat.sat', action_id: 'your_module.action_sat_sat_view', domain: [['estado', '=', 'no_disponible']] },
            { id: 'total_reparaciones', value: this.dashboardData.total_reparaciones, res_model: 'reparaciones.reparaciones', action_id: 'your_module.action_reparaciones_reparaciones_view', domain: [] },
            { id: 'reparaciones_en_revision', value: this.dashboardData.reparaciones_en_revision, res_model: 'reparaciones.reparaciones', action_id: 'your_module.action_reparaciones_reparaciones_view', domain: [['estado', '=', 'en_revision']] },
            { id: 'reparaciones_hoy', value: this.dashboardData.reparaciones_hoy, res_model: 'reparaciones.reparaciones', action_id: 'your_module.action_reparaciones_reparaciones_view', domain: [['fecha', '=', new Date().toISOString().split('T')[0]]] },
            { id: 'reparaciones_mes', value: this.dashboardData.reparaciones_mes, res_model: 'reparaciones.reparaciones', action_id: 'your_module.action_reparaciones_reparaciones_view', domain: [['mes', '=', new Date().getMonth() + 1]] },
            { id: 'reparaciones_ano', value: this.dashboardData.reparaciones_ano, res_model: 'reparaciones.reparaciones', action_id: 'your_module.action_reparaciones_reparaciones_view', domain: [['ano', '=', new Date().getFullYear()]] }
        ];
    
        elements.forEach(({ id, value, res_model, action_id, domain }) => {
            this._updateElementContent(id, value);
            const element = document.getElementById(`tile_${id}`); // Selecciona el contenedor del "tile"
    
            if (element) {
                element.onclick = () => {
                    this._openFilteredView(action_id, res_model, domain);
                };
            }
        });
    }
    

    async _openFilteredView(action_id, res_model, domain) {
        try {
            if (action_id) {
                await this.action.doAction(action_id, {
                    additional_context: { domain: domain }
                });
            } else {
                console.error("action_id no definido para _openFilteredView");
            }
        } catch (error) {
            console.error("Error en _openFilteredView:", error);
        }
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
                            interval: 0, // Mostrar todas las etiquetas en el eje X
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
                            {
                                value: this.dashboardData.maquinas_disponibles,
                                itemStyle: { color: '#4CAF50' } // Verde para "Disponibles"
                            },
                            {
                                value: this.dashboardData.maquinas_separadas,
                                itemStyle: { color: '#FF9800' } // Naranja para "Separadas"
                            },
                            {
                                value: this.dashboardData.maquinas_no_disponibles,
                                itemStyle: { color: '#F44336' } // Rojo para "No Disponibles"
                            }
                        ],
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
                        bottom: '10%', // Ajustar el margen inferior para evitar la superposición
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
                    title: { 
                        text: 'Estado de Máquinas',
                        left: 'center',
                        top: '0%', // Mueve el título más arriba
                        textStyle: {
                            fontSize: 14,
                            fontWeight: 'bold',
                        }
                    },
                    tooltip: { 
                        trigger: 'item',
                        formatter: '{b}: {c} ({d}%)'
                    },
                    legend: {
                        show: false // Oculta la leyenda
                    },
                    series: [{
                        name: 'Estado',
                        type: 'pie',
                        radius: ['40%', '70%'], // Gráfico de dona
                        center: ['50%', '55%'], // Centra el gráfico en el eje vertical
                        data: [
                            { value: this.dashboardData.maquinas_sin_revisar, name: 'Sin Revisar', itemStyle: { color: '#42A5F5' } },
                            { value: this.dashboardData.maquinas_en_revision, name: 'En Revisión', itemStyle: { color: '#66BB6A' } },
                            { value: this.dashboardData.maquinas_finalizadas, name: 'Finalizadas', itemStyle: { color: '#FFCA28' } },
                            { value: this.dashboardData.maquinas_problemas, name: 'Problemas', itemStyle: { color: '#EF5350' } }
                        ],
                        emphasis: {
                            itemStyle: {
                                shadowBlur: 10,
                                shadowOffsetX: 0,
                                shadowColor: 'rgba(0, 0, 0, 0.5)'
                            }
                        },
                        label: {
                            show: true,
                            position: 'outside',
                            formatter: '{b}: {c} ({d}%)', // Muestra nombres completos, valores y porcentajes
                            fontSize: 12,
                            color: '#333',
                            overflow: 'break', // Intenta evitar el recorte
                        },
                        labelLine: {
                            show: true,
                            length: 20, // Aumenta la longitud de las líneas de etiquetas
                            length2: 15,
                            smooth: true,
                            lineStyle: {
                                width: 1,
                                type: 'solid'
                            }
                        }
                    }],
                    animationDuration: 1000,
                    animationEasing: 'cubicInOut'
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
                    title: {
                        text: 'Reparaciones por Técnico',
                        left: 'center',
                        top: '2%',
                        textStyle: {
                            fontSize: 16,
                            fontWeight: 'bold'
                        }
                    },
                    tooltip: {
                        trigger: 'axis',
                        axisPointer: {
                            type: 'shadow'
                        }
                    },
                    grid: {
                        top: '15%',
                        bottom: '15%',    // Aumentado para dar espacio al visualMap
                        left: '3%',       // Reducido para usar más espacio horizontal
                        right: '5%',      // Reducido para usar más espacio horizontal
                        containLabel: true,
                        height: '70%'     // Controla la altura del área del gráfico
                    },
                    xAxis: {
                        type: 'value',
                        splitLine: {
                            show: true,
                            lineStyle: {
                                type: 'dashed'
                            }
                        },
                        axisLabel: {
                            fontSize: 12
                        }
                    },
                    yAxis: {
                        type: 'category',
                        data: tecnicosLabels,
                        axisLabel: {
                            interval: 0,
                            width: 150,      // Aumentado para nombres más largos
                            overflow: 'break',
                            fontSize: 12,
                            formatter: function(value) {
                                // Manejar nombres largos en múltiples líneas si es necesario
                                const maxLength = 30;
                                if (value.length > maxLength) {
                                    return value.substring(0, maxLength) + '...';
                                }
                                return value;
                            }
                        }
                    },
                    visualMap: {
                        orient: 'horizontal',
                        left: 'center',
                        bottom: '2%',
                        min: Math.min(...tecnicosData),
                        max: Math.max(...tecnicosData),
                        text: ['High Score', 'Low Score'],
                        dimension: 0,
                        inRange: {
                            color: ['#FFE7BA', '#FFB366']  // Tonos amarillos como en tu imagen
                        },
                        itemWidth: 15,
                        itemHeight: 200
                    },
                    series: [{
                        name: 'Reparaciones',
                        type: 'bar',
                        data: tecnicosData,
                        label: {
                            show: true,
                            position: 'right',
                            formatter: '{c}',
                            fontSize: 12,
                            fontWeight: 'bold',
                            distance: 5
                        },
                        barWidth: '40%',    // Ajustado para mejor proporción
                        barMaxWidth: 60     // Máximo ancho de las barras
                    }]
                });
                
                // Asegurar que el gráfico ocupe todo el espacio disponible
                const parentElement = tecnicosElement.parentElement;
                if (parentElement) {
                    tecnicosChart.resize({
                        width: parentElement.offsetWidth,
                        height: parentElement.offsetHeight
                    });
                }
                
                // Manejar el redimensionamiento de la ventana
                window.addEventListener('resize', () => {
                    tecnicosChart.resize({
                        width: parentElement?.offsetWidth,
                        height: parentElement?.offsetHeight
                    });
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
