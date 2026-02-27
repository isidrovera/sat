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
                domain: [['estado_ventas_id', '!=', 'entregada']], 
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
                action_id: 'sat.action_window', 
                domain: [['disponibilidad_id', '=', 'separada']], 
                search_view_id: 'sat.Sat_search_view' 
            },
            { 
                id: 'maquinas_para_revision', 
                value: this.dashboardData.maquinas_para_revision, 
                res_model: 'sat.sat', 
                action_id: 'sat.action_window', 
                domain: [['estado_ventas_id', '=', 'para_revision']], 
                search_view_id: 'sat.Sat_search_view' 
            },
            { 
                id: 'maquinas_sin_revisar', 
                value: this.dashboardData.maquinas_sin_revisar, 
                res_model: 'sat.sat', 
                action_id: 'sat.action_window', 
                domain: [['estado_ventas_id', '=', 'sin_revisar']], 
                search_view_id: 'sat.Sat_search_view' 
            },
            { 
                id: 'maquinas_con_problemas', 
                value: this.dashboardData.maquinas_con_problemas, 
                res_model: 'sat.sat', 
                action_id: 'sat.action_window', 
                domain: [['estado_ventas_id', '=', 'con_problemas']], 
                search_view_id: 'sat.Sat_search_view' 
            },
            { 
                id: 'maquinas_de_partes', 
                value: this.dashboardData.maquinas_de_partes, 
                res_model: 'sat.sat', 
                action_id: 'sat.action_window', 
                domain: [['estado_ventas_id', '=', 'de_partes']], 
                search_view_id: 'sat.Sat_search_view' 
            },


            { 
                id: 'total_maquinas_alquiler', 
                value: this.dashboardData.total_maquinas_alquiler, 
                res_model: 'alquiler', 
                action_id: 'sat.action_alquiler_window', 
                domain: [], 
                search_view_id: 'alquiler_andes_search_view' 
            },
            { 
                id: 'alquiler_alquilada', 
                value: this.dashboardData.alquiler_alquilada, 
                res_model: 'alquiler', 
                action_id: 'sat.action_alquiler_window', 
                domain: [['estado_alquiler_id', '=', 'alquilada']], 
                search_view_id: 'alquiler_andes_search_view' 
            },
            { 
                id: 'alquiler_sin_revisar', 
                value: this.dashboardData.alquiler_sin_revisar, 
                res_model: 'alquiler', 
                action_id: 'sat.action_alquiler_window', 
                domain: [['estado_alquiler_id', '=', 'sin_revisar']], 
                search_view_id: 'alquiler_andes_search_view' 
            },
            { 
                id: 'alquiler_revisada', 
                value: this.dashboardData.alquiler_revisada, 
                res_model: 'alquiler', 
                action_id: 'sat.action_alquiler_window', 
                domain: [['estado_alquiler_id', '=', 'revisada']], 
                search_view_id: 'alquiler_andes_search_view' 
            },
            { 
                id: 'alquiler_lista', 
                value: this.dashboardData.alquiler_lista, 
                res_model: 'alquiler', 
                action_id: 'sat.action_alquiler_window', 
                domain: [['estado_alquiler_id', '=', 'lista']], 
                search_view_id: 'alquiler_andes_search_view' 
            },
            { 
                id: 'alquiler_con_problemas', 
                value: this.dashboardData.alquiler_con_problemas, 
                res_model: 'alquiler', 
                action_id: 'sat.action_alquiler_window', 
                domain: [['estado_alquiler_id', '=', 'con_problemas']], 
                search_view_id: 'alquiler_andes_search_view' 
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
                id: 'reparaciones_finalizado', 
                value: this.dashboardData.reparaciones_finalizado, 
                res_model: 'reparaciones.reparaciones', 
                action_id: 'sat.action_reparaciones_window', 
                domain: [['estado_id', '=', 'finalizado']], 
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
            },
            { 
                id: 'total_tickets', 
                value: this.dashboardData.total_tickets, 
                res_model: 'ticket.alquiler', 
                action_id: 'sat.action_soporte_window', 
                domain: [], 
                search_view_id: 'ticket_search' 
            },
            { 
                id: 'tickets_nuevos', 
                value: this.dashboardData.tickets_nuevos, 
                res_model: 'ticket.alquiler', 
                action_id: 'sat.action_soporte_window', 
                domain: [['estado', '=', 'nuevo']], 
                search_view_id: 'ticket_search' 
            },
            { 
                id: 'tickets_proceso', 
                value: this.dashboardData.tickets_proceso, 
                res_model: 'ticket.alquiler', 
                action_id: 'sat.action_soporte_window', 
                domain: [['estado', '=', 'proceso']], 
                search_view_id: 'ticket_search' 
            },
            { 
                id: 'tickets_en_ruta', 
                value: this.dashboardData.tickets_en_ruta, 
                res_model: 'ticket.alquiler', 
                action_id: 'sat.action_soporte_window', 
                domain: [['estado', '=', 'en_ruta']], 
                search_view_id: 'ticket_search' 
            },
            { 
                id: 'tickets_en_sitio', 
                value: this.dashboardData.tickets_en_sitio, 
                res_model: 'ticket.alquiler', 
                action_id: 'sat.action_soporte_window', 
                domain: [['estado', '=', 'en_sitio']], 
                search_view_id: 'ticket_search' 
            },
            { 
                id: 'tickets_en_revision', 
                value: this.dashboardData.tickets_en_revision, 
                res_model: 'ticket.alquiler', 
                action_id: 'sat.action_soporte_window', 
                domain: [['estado', '=', 'en_revision']], 
                search_view_id: 'ticket_search' 
            },
            { 
                id: 'tickets_finalizado', 
                value: this.dashboardData.tickets_finalizado, 
                res_model: 'ticket.alquiler', 
                action_id: 'sat.action_soporte_window', 
                domain: [['estado', '=', 'finalizado']], 
                search_view_id: 'ticket_search' 
            },
            { 
                id: 'equipos_activos', 
                value: this.dashboardData.equipos_activos, 
                res_model: 'alquiler', 
                action_id: 'sat.action_alquiler_window', 
                domain: [['estado_alquiler_id', '=', 'alquilada'], ['estado_bloqueo', '=', 'activo']], 
                search_view_id: 'alquiler_andes_search_view' 
            },
            { 
                id: 'equipos_suspendidos', 
                value: this.dashboardData.equipos_suspendidos, 
                res_model: 'alquiler', 
                action_id: 'sat.action_alquiler_window', 
                domain: [['estado_alquiler_id', '=', 'alquilada'], ['estado_bloqueo', '=', 'suspendido']], 
                search_view_id: 'alquiler_andes_search_view' 
            },
            { 
                id: 'equipos_bloqueados', 
                value: this.dashboardData.equipos_bloqueados, 
                res_model: 'alquiler', 
                action_id: 'sat.action_alquiler_window', 
                domain: [['estado_alquiler_id', '=', 'alquilada'], ['estado_bloqueo', '=', 'bloqueado']], 
                search_view_id: 'alquiler_andes_search_view' 
            },
            { 
                id: 'equipos_no_accesibles', 
                value: this.dashboardData.equipos_no_accesibles, 
                res_model: 'alquiler', 
                action_id: 'sat.action_alquiler_window', 
                domain: [['estado_alquiler_id', '=', 'alquilada'], ['estado_bloqueo', '=', 'no_accesible']], 
                search_view_id: 'alquiler_andes_search_view' 
            },
            { 
                id: 'equipos_pendiente_bloqueo', 
                value: this.dashboardData.equipos_pendiente_bloqueo, 
                res_model: 'alquiler', 
                action_id: 'sat.action_alquiler_window', 
                domain: [['estado_alquiler_id', '=', 'alquilada'], ['estado_bloqueo', '=', 'pendiente_bloqueo']], 
                search_view_id: 'alquiler_andes_search_view' 
            },
            { 
                id: 'equipos_pendiente_desbloqueo', 
                value: this.dashboardData.equipos_pendiente_desbloqueo, 
                res_model: 'alquiler', 
                action_id: 'sat.action_alquiler_window', 
                domain: [['estado_alquiler_id', '=', 'alquilada'], ['estado_bloqueo', '=', 'pendiente_desbloqueo']], 
                search_view_id: 'alquiler_andes_search_view' 
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
        this._renderEquiposAtencion();
        this._setupSistemaBloqueoButton();
    }
    // NUEVOS MÉTODOS - AGREGAR DESPUÉS DE _render_tiles()
    _renderEquiposAtencion() {
        const equiposAtencionContainer = document.getElementById('equiposAtencionList');
        if (!equiposAtencionContainer || !this.dashboardData.equipos_atencion) return;

        if (this.dashboardData.equipos_atencion.length === 0) {
            equiposAtencionContainer.innerHTML = '<p class="text-success">✅ No hay equipos que requieran atención</p>';
            return;
        }

        let html = '';
        this.dashboardData.equipos_atencion.forEach(equipo => {
            const badgeClass = this._getEstadoBadgeClass(equipo.estado_bloqueo);
            html += `
                <div class="alert alert-warning alert-sm mb-2" role="alert">
                    <strong>${equipo.serie}</strong> - ${equipo.cliente}<br>
                    <small class="text-muted">${equipo.modelo}</small><br>
                    <span class="badge ${badgeClass}">${equipo.estado_label}</span>
                    ${equipo.motivo ? `<br><small>${equipo.motivo}</small>` : ''}
                    ${equipo.fecha_bloqueo ? `<br><small class="text-muted">${equipo.fecha_bloqueo}</small>` : ''}
                </div>
            `;
        });
        equiposAtencionContainer.innerHTML = html;
    }

    _getEstadoBadgeClass(estado) {
        const classes = {
            'pendiente_bloqueo': 'badge-info',
            'pendiente_desbloqueo': 'badge-primary', 
            'no_accesible': 'badge-secondary'
        };
        return classes[estado] || 'badge-warning';
    }

    _setupSistemaBloqueoButton() {
        const btnSistemaBloqueo = document.getElementById('btnSistemaBloqueo');
        if (btnSistemaBloqueo) {
            btnSistemaBloqueo.onclick = () => {
                // Abrir vista de alquileres filtrada
                this._openFilteredView('sat.action_alquiler_window', 'alquiler', [['estado_alquiler_id', '=', 'alquilada']], 'alquiler_andes_search_view');
            };
        }
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

                const option = {
                    backgroundColor: '#fff',
                    tooltip: {
                        trigger: 'item',
                        formatter: '{b}: {c}'
                    },
                    series: [{
                        name: 'Estado de Máquinas',
                        type: 'pie',
                        radius: [50, 120],
                        center: ['50%', '50%'],
                        roseType: 'radius',
                        itemStyle: {
                            borderRadius: 8,
                            borderColor: '#fff',
                            borderWidth: 2
                        },
                        label: {
                            show: true,
                            position: 'outside',
                            alignTo: 'edge',
                            margin: 20,
                            formatter: '{b}: {c}',
                            fontSize: 12,
                            color: '#666',
                            overflow: 'break'
                        },
                        labelLine: {
                            show: true,
                            length: 15,
                            length2: 20,
                            smooth: true,
                            lineStyle: {
                                width: 1,
                                type: 'solid'
                            }
                        },
                        data: [
                            { 
                                value: this.dashboardData.maquinas_sin_revisar, 
                                name: 'Sin Revisar', 
                                itemStyle: { color: '#36A2EB' }
                            },
                            { 
                                value: this.dashboardData.maquinas_en_revision, 
                                name: 'En Revisión', 
                                itemStyle: { color: '#06d6c5' }
                            },
                            { 
                                value: this.dashboardData.maquinas_finalizadas, 
                                name: 'Finalizadas', 
                                itemStyle: { color: '#06d63a' }
                            },
                            { 
                                value: this.dashboardData.maquinas_con_problemas, 
                                name: 'Problemas', 
                                itemStyle: { color: '#ff7f08' }
                            },
                            { 
                                value: this.dashboardData.maquinas_de_partes, 
                                name: 'Partes', 
                                itemStyle: { color: '#ed0505' }
                            }
                        ],
                        emphasis: {
                            itemStyle: {
                                shadowBlur: 10,
                                shadowOffsetX: 0,
                                shadowColor: 'rgba(0, 0, 0, 0.5)'
                            }
                        }
                    }]
                };

                // Configurar el gráfico
                estadoChart.setOption(option);
                
                // Hacer el gráfico responsive
                window.addEventListener('resize', () => {
                    estadoChart.resize();
                });
            }

            // Gráfico de Estados de Bloqueo - Agregar después del gráfico de estado
const estadosBloqueoElement = this._getChartElement("estadosBloqueoChart");
if (estadosBloqueoElement) {
    console.log('Renderizando gráfico de estados de bloqueo...');
    const estadosBloqueoChart = echarts.init(estadosBloqueoElement);

    // Datos para el gráfico de estados de bloqueo
    const estadosBloqueoData = [
        { 
            value: this.dashboardData.equipos_activos || 0, 
            name: 'Activos', 
            itemStyle: { color: '#27ae60' } // Verde
        },
        { 
            value: this.dashboardData.equipos_suspendidos || 0, 
            name: 'Suspendidos', 
            itemStyle: { color: '#f39c12' } // Naranja
        },
        { 
            value: this.dashboardData.equipos_bloqueados || 0, 
            name: 'Bloqueados', 
            itemStyle: { color: '#e74c3c' } // Rojo
        },
        { 
            value: this.dashboardData.equipos_no_accesibles || 0, 
            name: 'No Accesibles', 
            itemStyle: { color: '#95a5a6' } // Gris
        },
        { 
            value: this.dashboardData.equipos_pendiente_bloqueo || 0, 
            name: 'Pend. Bloqueo', 
            itemStyle: { color: '#3498db' } // Azul
        },
        { 
            value: this.dashboardData.equipos_pendiente_desbloqueo || 0, 
            name: 'Pend. Desbloqueo', 
            itemStyle: { color: '#5dade2' } // Azul claro
        }
    ];

    const estadosBloqueoOption = {
        backgroundColor: '#fff',
        tooltip: {
            trigger: 'item',
            formatter: function(params) {
                return `<strong>${params.name}</strong><br/>
                        Cantidad: ${params.value}<br/>
                        Porcentaje: ${params.percent}%`;
            }
        },
        legend: {
            orient: 'vertical',
            left: 'left',
            top: 'middle',
            textStyle: {
                fontSize: 12
            },
            formatter: function(name) {
                // Limitar la longitud del texto en la leyenda
                return name.length > 12 ? name.substring(0, 12) + '...' : name;
            }
        },
        series: [{
            name: 'Estados de Equipos',
            type: 'pie',
            radius: ['40%', '70%'], // Donut chart
            center: ['60%', '50%'], // Mover el gráfico a la derecha para dar espacio a la leyenda
            avoidLabelOverlap: false,
            itemStyle: {
                borderRadius: 6,
                borderColor: '#fff',
                borderWidth: 2
            },
            label: {
                show: false, // Ocultar etiquetas en el gráfico para evitar saturación
                position: 'center'
            },
            emphasis: {
                label: {
                    show: true,
                    fontSize: 16,
                    fontWeight: 'bold',
                    formatter: function(params) {
                        return `${params.name}\n${params.value}`;
                    }
                },
                itemStyle: {
                    shadowBlur: 10,
                    shadowOffsetX: 0,
                    shadowColor: 'rgba(0, 0, 0, 0.5)'
                }
            },
            labelLine: {
                show: false
            },
            data: estadosBloqueoData,
            animationType: 'scale',
            animationEasing: 'elasticOut',
            animationDelay: function (idx) {
                return Math.random() * 200;
            }
        }]
    };

    // Configurar el gráfico
    estadosBloqueoChart.setOption(estadosBloqueoOption);
    
    // Hacer el gráfico responsive
    const handleEstadosBloqueoResize = () => {
        const parentElement = estadosBloqueoElement.parentElement;
        if (parentElement) {
            estadosBloqueoChart.resize({
                width: parentElement.offsetWidth,
                height: parentElement.offsetHeight
            });
        }
    };

    window.addEventListener('resize', handleEstadosBloqueoResize);
    
    // Forzar un resize inicial
    setTimeout(() => {
        handleEstadosBloqueoResize();
    }, 300);

    console.log('Gráfico de estados de bloqueo renderizado exitosamente');
} else {
    console.error('Elemento estadosBloqueoChart no encontrado');
}

            // Gráfico de técnicos            
            const tecnicosElement = this._getChartElement("tecnicosChart");

            if (tecnicosElement) {
                console.log('Renderizando gráfico de técnicos...');
                
                // Hacer que el contenedor sea responsive
                tecnicosElement.style.width = '100%';
                tecnicosElement.style.position = 'relative';
                tecnicosElement.style.overflow = 'hidden';

                const renderTecnicosChart = (filteredData = null, titleText = 'Reparaciones por Técnico') => {
                    // Obtener datos
                    const dataToUse = filteredData || this.dashboardData.tecnicos_totales || {};
                    const tecnicosLabels = Object.keys(dataToUse);
                    const tecnicosData = Object.values(dataToUse);

                    console.log('Datos después de aplicar el filtro:', filteredData);
                    console.log('Etiquetas de técnicos:', tecnicosLabels);
                    console.log('Datos de reparaciones:', tecnicosData);

                    // Validar datos de colores en visualMap
                    const minDataValue = tecnicosData.length ? Math.min(...tecnicosData) : 0;
                    const maxDataValue = tecnicosData.length ? Math.max(...tecnicosData) : 1;

                    // Crear y configurar el gráfico
                    const tecnicosChart = echarts.init(tecnicosElement);

                    tecnicosChart.setOption({
                        
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
                            data: tecnicosLabels,
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
                                color: ['#FFE7BA', '#FFB366']
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
                            barWidth: '40%',
                            barMaxWidth: 60
                        }]
                    });

                    // Manejar el redimensionamiento
                    const handleResize = () => {
                        const parentElement = tecnicosElement.parentElement;
                        if (parentElement) {
                            tecnicosChart.resize({
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
                    
                    return tecnicosChart;
                };

                const applyDateFilter = () => {
                    const startDateInput = document.getElementById("startDateTecnicos");
                    const endDateInput = document.getElementById("endDateTecnicos");
                
                    console.log("Aplicando filtro de fecha...");
                    console.log("Fecha de inicio:", startDateInput.value);
                    console.log("Fecha de fin:", endDateInput.value);
                
                    if (!startDateInput.value || !endDateInput.value) {
                        alert("Por favor, selecciona ambas fechas para aplicar el filtro");
                        return;
                    }
                
                    const formatDate = (dateString) => {
                        const date = new Date(dateString);
                        return date.toISOString().split('T')[0];
                    };
                
                    const startDate = formatDate(startDateInput.value);
                    const endDate = formatDate(endDateInput.value);
                
                    console.log("Fecha inicio (formateada):", startDate);
                    console.log("Fecha fin (formateada):", endDate);
                
                    const filteredData = {};
                    let hayDatos = false;
                
                    // Inicializar todos los técnicos con 0
                    if (this.dashboardData.tecnicos_totales) {
                        Object.keys(this.dashboardData.tecnicos_totales).forEach(tecnico => {
                            filteredData[tecnico] = 0;
                        });
                    }
                
                    // Verificar si tenemos datos de reparaciones por fecha
                    if (!this.dashboardData.reparaciones_por_fecha) {
                        console.warn("No hay datos de reparaciones_por_fecha disponibles");
                        const titleText = `Reparaciones por Técnico (${new Date(startDate).toLocaleDateString()} - ${new Date(endDate).toLocaleDateString()})`;
                        renderTecnicosChart(filteredData, titleText);
                        return;
                    }
                
                    // Filtrar los datos según el rango de fechas
                    Object.entries(this.dashboardData.reparaciones_por_fecha).forEach(([fecha, reparaciones]) => {
                        if (fecha >= startDate && fecha <= endDate) {
                            reparaciones.forEach(reparacion => {
                                if (reparacion.tecnico_nombre) {
                                    filteredData[reparacion.tecnico_nombre] = (filteredData[reparacion.tecnico_nombre] || 0) + 1;
                                    hayDatos = true;
                                }
                            });
                        }
                    });
                
                    console.log("Datos después del filtrado:", filteredData);
                
                    if (!hayDatos) {
                        console.log("No se encontraron reparaciones en el rango de fechas seleccionado");
                    }
                
                    const titleText = `Reparaciones por Técnico (${new Date(startDate).toLocaleDateString()} - ${new Date(endDate).toLocaleDateString()})`;
                    renderTecnicosChart(filteredData, titleText);
                };
                
                // Configurar el event listener para el botón de filtro
                const filterButton = document.getElementById("applyFilterTecnicos");
                if (filterButton) {
                    filterButton.removeEventListener("click", applyDateFilter);
                    filterButton.addEventListener("click", applyDateFilter);
                }

                // Renderizar el gráfico inicial
                const chart = renderTecnicosChart();
                
                // Forzar un reflow después de la carga inicial
                setTimeout(() => {
                    chart.resize();
                }, 300);

            } else {
                console.error('No se encontró el elemento del gráfico en el DOM');
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
                
                    // Si no hay fechas seleccionadas, mostrar mensaje
                    if (!startDateInput.value || !endDateInput.value) {
                        alert("Por favor, selecciona ambas fechas para aplicar el filtro");
                        return;
                    }
                
                    // Formatear fechas para comparación consistente
                    const formatDate = (dateString) => {
                        const date = new Date(dateString);
                        return date.toISOString().split('T')[0];
                    };
                
                    const startDate = formatDate(startDateInput.value);
                    const endDate = formatDate(endDateInput.value);
                
                    console.log("Fecha inicio (formateada):", startDate);
                    console.log("Fecha fin (formateada):", endDate);
                
                    const filteredData = {};
                    let hayDatos = false;
                
                    // Inicializar todos los técnicos con 0
                    if (this.dashboardData.tecnicos_totales_tickets) {
                        Object.keys(this.dashboardData.tecnicos_totales_tickets).forEach(tecnico => {
                            filteredData[tecnico] = 0;
                        });
                    }
                
                    // Verificar si tenemos datos de tickets por fecha
                    if (!this.dashboardData.tickets_por_fecha) {
                        console.warn("No hay datos de tickets_por_fecha disponibles");
                        const titleText = `Tickets por Técnico (${new Date(startDate).toLocaleDateString()} - ${new Date(endDate).toLocaleDateString()})`;
                        renderTicketsTecnicoChart(filteredData, titleText);
                        return;
                    }
                
                    // Filtrar los datos según el rango de fechas
                    Object.entries(this.dashboardData.tickets_por_fecha).forEach(([fecha, tickets]) => {
                        if (fecha >= startDate && fecha <= endDate) {
                            tickets.forEach(ticket => {
                                if (ticket.tecnico_nombre) {
                                    filteredData[ticket.tecnico_nombre] = (filteredData[ticket.tecnico_nombre] || 0) + 1;
                                    hayDatos = true;
                                }
                            });
                        }
                    });
                
                    console.log("Datos después del filtrado:", filteredData);
                
                    // Si no hay datos en el rango seleccionado, mostrar mensaje
                    if (!hayDatos) {
                        console.log("No se encontraron tickets en el rango de fechas seleccionado");
                    }
                
                    // Actualizar el gráfico con los datos filtrados
                    const titleText = `Tickets por Técnico (${new Date(startDate).toLocaleDateString()} - ${new Date(endDate).toLocaleDateString()})`;
                    renderTicketsTecnicoChart(filteredData, titleText);
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




            // Gráfico de Alquileres por Cliente
            const alquileresClienteElement = this._getChartElement("alquileresClienteChart");

            if (alquileresClienteElement) {
                const clientesData = this.dashboardData?.clientes_totales_alquiler || {};
                const clientes = Object.keys(clientesData);
                const datosAlquileres = clientes.map(cliente => clientesData[cliente]);

                const alturaFija = 500; // Aumentada para dar más espacio a las etiquetas
                alquileresClienteElement.style.height = `${alturaFija}px`;
                alquileresClienteElement.style.width = '100%';
                alquileresClienteElement.style.position = 'relative';

                try {
                    const alquileresClienteChart = echarts.init(alquileresClienteElement);
                    
                    const opcion = {
                        title: {
                            text: 'Alquileres por Cliente',
                            left: 'center',
                            top: '2%',
                            textStyle: {
                                fontSize: 14,
                                fontWeight: 'bold'
                            }
                        },
                        tooltip: {
                            trigger: 'axis',
                            axisPointer: { type: 'shadow' }
                        },
                        grid: {
                            left: '5%',
                            right: '5%',
                            bottom: '20%', // Aumentado para dar espacio a las etiquetas
                            top: '10%',
                            containLabel: true
                        },
                        dataZoom: [{
                            type: 'slider',
                            show: true,
                            xAxisIndex: [0],
                            start: 0,
                            end: 50, // Mostrar solo 50% de los datos inicialmente
                            height: 20,
                            bottom: 0,
                            borderColor: 'transparent',
                            backgroundColor: '#e2e2e2',
                            fillerColor: '#bbd7ff',
                            handleStyle: { color: '#4ECDC4' }
                        }, {
                            type: 'inside',
                            xAxisIndex: [0]
                        }],
                        xAxis: {
                            type: 'category',
                            data: clientes,
                            axisLabel: {
                                interval: 0,
                                rotate: 45,
                                fontSize: 12,
                                margin: 15,
                                align: 'right',
                                verticalAlign: 'middle',
                                formatter: function(value) {
                                    return value.length > 20 ? value.substring(0, 20) + '...' : value;
                                }
                            }
                        },
                        yAxis: {
                            type: 'value',
                            name: 'Alquileres',
                            minInterval: 1,
                            axisLabel: {
                                fontSize: 12
                            }
                        },
                        series: [{
                            name: 'Alquileres',
                            type: 'bar',
                            data: datosAlquileres,
                            itemStyle: {
                                color: '#4ECDC4',
                                borderRadius: [4, 4, 0, 0]
                            },
                            label: {
                                show: true,
                                position: 'top',
                                fontSize: 12
                            },
                            barWidth: '40%'
                        }]
                    };

                    alquileresClienteChart.setOption(opcion);

                    // Manejo del redimensionamiento
                    const handleResize = () => {
                        const parentElementCliente = alquileresClienteElement.parentElement;
                        if (parentElementCliente) {
                            alquileresClienteChart.resize({
                                width: parentElementCliente.offsetWidth,
                                height: alturaFija
                            });
                        }
                    };

                    window.addEventListener('resize', () => {
                        clearTimeout(window.resizeTimer);
                        window.resizeTimer = setTimeout(handleResize, 250);
                    });

                    handleResize();

                } catch (error) {
                    console.error('Error al renderizar el gráfico:', error);
                }
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
