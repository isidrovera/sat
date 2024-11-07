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
            { 
                id: 'total_maquinas', 
                value: this.dashboardData.total_maquinas, 
                res_model: 'sat.sat', 
                action_id: 'sat.action_window', 
                domain: [], 
                search_view_id: 'sat.Sat_search_view' 
            },
            { 
                id: 'maquinas_disponibles', 
                value: this.dashboardData.maquinas_disponibles, 
                res_model: 'sat.sat', 
                action_id: 'sat.action_window', 
                domain: [['disponibilidad_id', '=', 'disponible']], 
                search_view_id: 'sat.Sat_search_view' 
            },
            { 
                id: 'maquinas_separadas', 
                value: this.dashboardData.maquinas_separadas, 
                res_model: 'sat.sat', 
                action_id: 'your_module.action_sat_sat_view', 
                domain: [['estado', '=', 'separada']], 
                search_view_id: 'sat.Sat_search_view' 
            },
            { 
                id: 'maquinas_no_disponibles', 
                value: this.dashboardData.maquinas_no_disponibles, 
                res_model: 'sat.sat', 
                action_id: 'your_module.action_sat_sat_view', 
                domain: [['estado', '=', 'no_disponible']], 
                search_view_id: 'sat.Sat_search_view' 
            },
            { 
                id: 'total_reparaciones', 
                value: this.dashboardData.total_reparaciones, 
                res_model: 'reparaciones.reparaciones', 
                action_id: 'sat.action_reparaciones_window', 
                domain: [], 
                search_view_id: 'sat.reparaciones_search_view' 
            },
            { 
                id: 'reparaciones_en_revision', 
                value: this.dashboardData.reparaciones_en_revision, 
                res_model: 'reparaciones.reparaciones', 
                action_id: 'sat.action_reparaciones_window', 
                domain: [['estado_id', '=', 'en_revision']], 
                search_view_id: 'sat.reparaciones_search_view' 
            },
            { 
                id: 'reparaciones_hoy', 
                value: this.dashboardData.reparaciones_hoy, 
                res_model: 'reparaciones.reparaciones', 
                action_id: 'sat.action_reparaciones_window', 
                domain: [['fecha', '=', new Date().toISOString().split('T')[0]]], 
                search_view_id: 'sat.reparaciones_search_view' 
            },
            { 
                id: 'reparaciones_mes', 
                value: this.dashboardData.reparaciones_mes, 
                res_model: 'reparaciones.reparaciones', 
                action_id: 'sat.action_reparaciones_window', 
                domain: [['mes', '=', new Date().getMonth() + 1]], 
                search_view_id: 'sat.reparaciones_search_view' 
            },
            { 
                id: 'reparaciones_ano', 
                value: this.dashboardData.reparaciones_ano, 
                res_model: 'reparaciones.reparaciones', 
                action_id: 'sat.action_reparaciones_window', 
                domain: [['ano', '=', new Date().getFullYear()]], 
                search_view_id: 'sat.reparaciones_search_view' 
            }
        ];
    
        elements.forEach(({ id, value, res_model, action_id, domain, search_view_id }) => {
            console.log(`Configurando tile: ${id}`);
            console.log(` - Valor: ${value}`);
            console.log(` - Modelo: ${res_model}`);
            console.log(` - Acción ID: ${action_id}`);
            console.log(` - Dominio: ${JSON.stringify(domain)}`);
            console.log(` - Search View ID: ${search_view_id}`);
    
            this._updateElementContent(id, value);
            const element = document.getElementById(`tile_${id}`); // Selecciona el contenedor del "tile"
    
            if (element) {
                element.onclick = () => {
                    console.log(`Tile ${id} clickeado, abriendo vista...`);
                    this._openFilteredView(action_id, res_model, domain, search_view_id);
                };
            } else {
                console.warn(`Elemento no encontrado para tile: ${id}`);
            }
        });
    }
    
    async _openFilteredView(action_id, res_model, domain, search_view_id = null) {
        console.log(`Ejecutando _openFilteredView`);
        console.log(` - Acción ID: ${action_id}`);
        console.log(` - Modelo: ${res_model}`);
        console.log(` - Dominio: ${JSON.stringify(domain)}`);
        console.log(` - Search View ID: ${search_view_id}`);
    
        try {
            if (action_id) {
                await this.action.doAction({
                    type: 'ir.actions.act_window',
                    res_model: res_model,
                    view_mode: 'list,form',
                    views: [[false, 'list'], [false, 'form']],
                    target: 'current',
                    domain: domain,
                    context: {
                        search_view_id: search_view_id // ID de la vista de búsqueda específica
                    }
                });
                console.log("Vista abierta correctamente");
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

                      
            // Gráfico de tickets por técnico            
            const ticketsTecnicoElement = this._getChartElement("ticketsTecnicoChart");

            if (ticketsTecnicoElement) {
                console.log('Renderizando gráfico de tickets por técnico...');
                
                // Hacer que el contenedor sea responsive
                ticketsTecnicoElement.style.width = '100%';
                ticketsTecnicoElement.style.position = 'relative';
                ticketsTecnicoElement.style.overflow = 'hidden';

                const renderTicketsTecnicoChart = (filteredData = null, titleText = 'Tickets por Técnico') => {
                    // Obtener datos
                    const dataToUse = filteredData || this.dashboardData.tecnicos_totales_tickets || {};
                    const ticketsTecnicoLabels = Object.keys(dataToUse);
                    const ticketsTecnicoData = Object.values(dataToUse);

                    console.log('Datos después de aplicar el filtro:', filteredData);
                    console.log('Etiquetas de técnicos:', ticketsTecnicoLabels);
                    console.log('Datos de tickets:', ticketsTecnicoData);

                    // Validar datos de colores en visualMap
                    const minDataValue = ticketsTecnicoData.length ? Math.min(...ticketsTecnicoData) : 0;
                    const maxDataValue = ticketsTecnicoData.length ? Math.max(...ticketsTecnicoData) : 1;

                    // Crear y configurar el gráfico
                    const ticketsTecnicoChart = echarts.init(ticketsTecnicoElement);

                    const option = {
                        title: {
                            text: titleText,
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
                            bottom: '15%',    
                            left: '3%',      
                            right: '5%',      
                            containLabel: true,
                            height: '70%'     
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
                            data: ticketsTecnicoLabels,
                            axisLabel: {
                                interval: 0,
                                width: 150,
                                overflow: 'break',
                                fontSize: 12,
                                formatter: function(value) {
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
                            min: minDataValue,
                            max: maxDataValue,
                            text: ['High Score', 'Low Score'],
                            dimension: 0,
                            inRange: {
                                color: ['#8fccf2', '#6687ff']
                            },
                            itemWidth: 15,
                            itemHeight: 200
                        },
                        series: [{
                            name: 'Tickets',
                            type: 'bar',
                            data: ticketsTecnicoData,
                            label: {
                                show: true,
                                position: 'right',
                                formatter: '{c}',
                                fontSize: 12,
                                fontWeight: 'bold',
                                distance: 5
                            },
                            barWidth: '40%',
                            barMaxWidth: 60
                        }]
                    };

                    ticketsTecnicoChart.setOption(option, true);

                    // Manejar el redimensionamiento
                    const handleResize = () => {
                        const parentElement = ticketsTecnicoElement.parentElement;
                        if (parentElement) {
                            ticketsTecnicoChart.resize({
                                width: parentElement.offsetWidth,
                                height: parentElement.offsetHeight
                            });
                        }
                    };

                    // Limpiar listener anterior y agregar el nuevo
                    window.removeEventListener('resize', handleResize);
                    window.addEventListener('resize', handleResize);
                    
                    // Forzar un resize inicial
                    handleResize();
                    
                    return ticketsTecnicoChart;
                };

                const applyDateFilter = () => {
                    const startDateInput = document.getElementById("startDate");
                    const endDateInput = document.getElementById("endDate");
                
                    console.log("Aplicando filtro de fecha...");
                    console.log("Fecha de inicio:", startDateInput.value);
                    console.log("Fecha de fin:", endDateInput.value);
                
                    // Si no hay fechas seleccionadas, mostrar todos los datos
                    if (!startDateInput.value && !endDateInput.value) {
                        console.log("Mostrando todos los datos sin filtros");
                        renderTicketsTecnicoChart(null, 'Tickets por Técnico');
                        return;
                    }
                
                    // Validar que ambas fechas estén presentes
                    if (!startDateInput.value || !endDateInput.value) {
                        alert("Por favor, selecciona ambas fechas para aplicar el filtro");
                        return;
                    }
                
                    const startDate = new Date(startDateInput.value);
                    startDate.setHours(0, 0, 0, 0);
                    const endDate = new Date(endDateInput.value);
                    endDate.setHours(23, 59, 59, 999);
                
                    console.log(`Aplicando filtro - Desde: ${startDate.toISOString()} hasta: ${endDate.toISOString()}`);
                
                    // Filtrar datos según las fechas seleccionadas
                    const filteredData = {};
                    let hayDatos = false;
                    
                    if (this.dashboardData.tickets_por_fecha) {
                        Object.entries(this.dashboardData.tickets_por_fecha).forEach(([fecha, tickets]) => {
                            const ticketDate = new Date(fecha);
                            if (ticketDate >= startDate && ticketDate <= endDate) {
                                tickets.forEach(ticket => {
                                    if (ticket && ticket.tecnico) {
                                        filteredData[ticket.tecnico] = (filteredData[ticket.tecnico] || 0) + 1;
                                        hayDatos = true;
                                    }
                                });
                            }
                        });
                
                        // Si no hay datos en el rango seleccionado
                        if (!hayDatos) {
                            alert("No se encontraron tickets en el rango de fechas seleccionado");
                            // Renderizar gráfico vacío o con datos en 0
                            const emptyData = {};
                            Object.keys(this.dashboardData.tecnicos_totales_tickets || {}).forEach(tecnico => {
                                emptyData[tecnico] = 0;
                            });
                            const titleText = `Tickets por Técnico (${startDate.toLocaleDateString()} - ${endDate.toLocaleDateString()})`;
                            renderTicketsTecnicoChart(emptyData, titleText);
                            return;
                        }
                
                        console.log("Datos filtrados:", filteredData);
                
                        // Actualizar el gráfico con los datos filtrados
                        const titleText = `Tickets por Técnico (${startDate.toLocaleDateString()} - ${endDate.toLocaleDateString()})`;
                        renderTicketsTecnicoChart(filteredData, titleText);
                    }
                };

                // Configurar el event listener para el botón de filtro
                const filterButton = document.getElementById("applyFilter");
                if (filterButton) {
                    filterButton.removeEventListener("click", applyDateFilter);
                    filterButton.addEventListener("click", applyDateFilter);
                }

                // Renderizar el gráfico inicial
                const chart = renderTicketsTecnicoChart();
                
                // Forzar un reflow después de la carga inicial
                setTimeout(() => {
                    chart.resize();
                }, 300);

            } else {
                console.error('No se encontró el elemento del gráfico en el DOM');
            }
            // Gráfico de Tickets por Mes
            const ticketsMesElement = this._getChartElement("ticketsMesChart");
            console.log('Iniciando renderización del gráfico de Tickets por Mes...', ticketsMesElement);

            if (ticketsMesElement) {
                // Establecer estilo inicial del contenedor
                ticketsMesElement.style.height = '250px';
                ticketsMesElement.style.width = '100%';
                ticketsMesElement.style.position = 'relative';
                console.log('Dimensiones establecidas del contenedor:', {
                    height: ticketsMesElement.style.height,
                    width: ticketsMesElement.style.width
                });

                // Obtener fechas y definir los meses del año hasta el mes actual
                const añoActual = new Date().getFullYear();
                const mesActual = new Date().getMonth(); // Mes actual (0 = Enero, 11 = Diciembre)
                console.log('Fecha actual:', { año: añoActual, mes: mesActual });

                const mesesDelAño = [
                    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
                ].slice(0, mesActual + 1); // Solo mostrar meses hasta el actual
                console.log('Meses a mostrar en el gráfico:', mesesDelAño);

                // Inicializar datos de tickets con ceros para cada mes hasta el actual
                let datosTickets = new Array(mesActual + 1).fill(0);
                console.log('Datos inicializados de Tickets (relleno con ceros):', datosTickets);

                // Procesar datos recibidos de `dashboardData.tickets_por_mes`
                if (this.dashboardData && this.dashboardData.tickets_por_mes) {
                    console.log('Estado inicial de dashboardData:', {
                        completo: this.dashboardData,
                        tickets_por_mes: this.dashboardData.tickets_por_mes,
                        tipo: typeof this.dashboardData.tickets_por_mes
                    });

                    // Cargar valores de `tickets_por_mes` en `datosTickets`
                    mesesDelAño.forEach((mes, index) => {
                        const mesNumero = index + 1; // Convertir índice a mes numérico (1 = Enero, 12 = Diciembre)
                        const valor = this.dashboardData.tickets_por_mes[mesNumero] || 0;
                        datosTickets[index] = valor;
                        console.log(`Mes ${mes} (índice ${index}): valor encontrado = ${valor}`);
                    });
                } else {
                    console.log('No se encontraron datos válidos en `tickets_por_mes` dentro de dashboardData.');
                }

                console.log('Datos procesados finales para el gráfico:', datosTickets);

                try {
                    // Inicializar el gráfico
                    const ticketsMesChart = echarts.init(ticketsMesElement);
                    console.log('Gráfico de Tickets por Mes inicializado');

                    // Configuración del gráfico
                    const opcion = {
                        title: {
                            text: `Tickets por Mes ${añoActual}`,
                            left: 'center',
                            top: '2%',
                            textStyle: {
                                fontSize: 14,
                                fontWeight: 'bold'
                            }
                        },
                        tooltip: {
                            trigger: 'axis',
                            axisPointer: {
                                type: 'shadow'
                            },
                            formatter: '{b}: {c} tickets'
                        },
                        grid: {
                            left: '5%',
                            right: '5%',
                            bottom: '10%',
                            top: '15%',
                            containLabel: true
                        },
                        xAxis: {
                            type: 'category',
                            data: mesesDelAño,
                            axisLabel: {
                                interval: 0,
                                rotate: 30,
                                fontSize: 11
                            }
                        },
                        yAxis: {
                            type: 'value',
                            name: 'Tickets',
                            nameTextStyle: {
                                fontSize: 11
                            },
                            minInterval: 1,
                            min: 0,
                            axisLabel: {
                                formatter: '{value}',
                                fontSize: 11
                            }
                        },
                        series: [{
                            name: 'Tickets',
                            type: 'bar',
                            data: datosTickets,
                            itemStyle: {
                                color: '#4ECDC4',
                                borderRadius: [4, 4, 0, 0]
                            },
                            label: {
                                show: true,
                                position: 'top',
                                formatter: '{c}',
                                fontSize: 11
                            },
                            barWidth: '40%'
                        }]
                    };

                    console.log('Configuración del gráfico:', opcion);
                    ticketsMesChart.setOption(opcion);

                    // Redimensionamiento responsivo con logs detallados
                    const parentElementMes = ticketsMesElement.parentElement;
                    if (parentElementMes) {
                        console.log('Dimensiones del contenedor padre:', {
                            width: parentElementMes.offsetWidth,
                            height: parentElementMes.offsetHeight
                        });

                        parentElementMes.style.height = '250px';
                        parentElementMes.style.marginBottom = '20px';

                        ticketsMesChart.resize({
                            width: parentElementMes.offsetWidth,
                            height: 250
                        });
                    }

                    // Listener para redimensionar el gráfico al cambiar tamaño de ventana
                    let resizeTimeout;
                    window.addEventListener('resize', () => {
                        clearTimeout(resizeTimeout);
                        resizeTimeout = setTimeout(() => {
                            if (parentElementMes) {
                                console.log('Redimensionando gráfico:', {
                                    width: parentElementMes.offsetWidth,
                                    height: 250
                                });
                                ticketsMesChart.resize({
                                    width: parentElementMes.offsetWidth,
                                    height: 250
                                });
                            }
                        }, 250);
                    });

                    console.log('Gráfico de Tickets por Mes renderizado exitosamente');
                } catch (error) {
                    console.error('Error al renderizar el gráfico:', error);
                }
            } else {
                console.error('Error: No se encontró el elemento ticketsMesChart');
            }


            
            // Gráfico de Tickets por Año
            const ticketsAnoElement = this._getChartElement("ticketsAnoChart");
            console.log('Iniciando renderización del gráfico de Tickets por Año...', ticketsAnoElement);

            if (ticketsAnoElement) {
                // Establecer estilo inicial del contenedor
                ticketsAnoElement.style.height = '250px';
                ticketsAnoElement.style.width = '100%';
                ticketsAnoElement.style.position = 'relative';
                console.log('Dimensiones establecidas del contenedor:', {
                    height: ticketsAnoElement.style.height,
                    width: ticketsAnoElement.style.width
                });

                // Obtener el año actual y definir los últimos 5 años (o más si lo deseas)
                const añoActual = new Date().getFullYear();
                const añosAMostrar = Array.from({ length: 5 }, (_, i) => añoActual - i).reverse();
                console.log('Años a mostrar en el gráfico:', añosAMostrar);

                // Inicializar datos de tickets con ceros para cada año
                let datosTicketsAno = new Array(añosAMostrar.length).fill(0);
                console.log('Datos inicializados de Tickets por Año (relleno con ceros):', datosTicketsAno);

                // Procesar datos recibidos de `dashboardData.tickets_por_año`
                if (this.dashboardData && this.dashboardData.tickets_por_año) {
                    console.log('Estado inicial de dashboardData:', {
                        completo: this.dashboardData,
                        tickets_por_año: this.dashboardData.tickets_por_año,
                        tipo: typeof this.dashboardData.tickets_por_año
                    });

                    // Cargar valores de `tickets_por_año` en `datosTicketsAno`
                    añosAMostrar.forEach((año, index) => {
                        const valor = this.dashboardData.tickets_por_año[año] || 0;
                        datosTicketsAno[index] = valor;
                        console.log(`Año ${año} (índice ${index}): valor encontrado = ${valor}`);
                    });
                } else {
                    console.log('No se encontraron datos válidos en `tickets_por_año` dentro de dashboardData.');
                }

                console.log('Datos procesados finales para el gráfico de Tickets por Año:', datosTicketsAno);

                try {
                    // Inicializar el gráfico
                    const ticketsAnoChart = echarts.init(ticketsAnoElement);
                    console.log('Gráfico de Tickets por Año inicializado');

                    // Configuración del gráfico
                    const opcionAno = {
                        title: {
                            text: 'Tickets por Año',
                            left: 'center',
                            top: '2%',
                            textStyle: {
                                fontSize: 14,
                                fontWeight: 'bold'
                            }
                        },
                        tooltip: {
                            trigger: 'axis',
                            axisPointer: {
                                type: 'shadow'
                            },
                            formatter: '{b}: {c} tickets'
                        },
                        grid: {
                            left: '5%',
                            right: '5%',
                            bottom: '10%',
                            top: '15%',
                            containLabel: true
                        },
                        xAxis: {
                            type: 'category',
                            data: añosAMostrar,
                            axisLabel: {
                                interval: 0,
                                rotate: 30,
                                fontSize: 11
                            }
                        },
                        yAxis: {
                            type: 'value',
                            name: 'Tickets',
                            nameTextStyle: {
                                fontSize: 11
                            },
                            minInterval: 1,
                            min: 0,
                            axisLabel: {
                                formatter: '{value}',
                                fontSize: 11
                            }
                        },
                        series: [{
                            name: 'Tickets',
                            type: 'bar',
                            data: datosTicketsAno,
                            itemStyle: {
                                color: '#FF6B6B',
                                borderRadius: [4, 4, 0, 0]
                            },
                            label: {
                                show: true,
                                position: 'top',
                                formatter: '{c}',
                                fontSize: 11
                            },
                            barWidth: '40%'
                        }]
                    };

                    console.log('Configuración del gráfico de Tickets por Año:', opcionAno);
                    ticketsAnoChart.setOption(opcionAno);

                    // Redimensionamiento responsivo con logs detallados
                    const parentElementAno = ticketsAnoElement.parentElement;
                    if (parentElementAno) {
                        console.log('Dimensiones del contenedor padre:', {
                            width: parentElementAno.offsetWidth,
                            height: parentElementAno.offsetHeight
                        });

                        parentElementAno.style.height = '250px';
                        parentElementAno.style.marginBottom = '20px';

                        ticketsAnoChart.resize({
                            width: parentElementAno.offsetWidth,
                            height: 250
                        });
                    }

                    // Listener para redimensionar el gráfico al cambiar tamaño de ventana
                    let resizeTimeout;
                    window.addEventListener('resize', () => {
                        clearTimeout(resizeTimeout);
                        resizeTimeout = setTimeout(() => {
                            if (parentElementAno) {
                                console.log('Redimensionando gráfico de Tickets por Año:', {
                                    width: parentElementAno.offsetWidth,
                                    height: 250
                                });
                                ticketsAnoChart.resize({
                                    width: parentElementAno.offsetWidth,
                                    height: 250
                                });
                            }
                        }, 250);
                    });

                    console.log('Gráfico de Tickets por Año renderizado exitosamente');
                } catch (error) {
                    console.error('Error al renderizar el gráfico de Tickets por Año:', error);
                }
            } else {
                console.error('Error: No se encontró el elemento ticketsAnoChart');
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
