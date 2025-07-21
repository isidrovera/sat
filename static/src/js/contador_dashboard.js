/** @odoo-module **/
import { Component, onWillStart, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Dashboard Widget para Contadores
 * Muestra estadísticas y lista de equipos en tiempo real
 */
class ContadorDashboardWidget extends Component {
    static template = "contador.DashboardWidget";
    
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        
        this.state = useState({
            loading: true,
            error: null,
            stats: {
                equipos_unicos_hoy: 0,
                equipos_unicos_semana: 0,
                total_equipos_sistema: 0,
                eficiencia_sistema: 0,
                total_registros_semana: 0,
                estado_sistema: 'optimo'
            },
            equipos: [],
            filtros: {
                search: '',
                tipo: 'todos',
                estado: 'todos'
            }
        });
        
        onWillStart(() => this.loadData());
        onMounted(() => this.setupAutoRefresh());
    }
    
    /**
     * Carga datos iniciales del dashboard
     */
    async loadData() {
        try {
            this.state.loading = true;
            this.state.error = null;
            
            // Cargar estadísticas
            const stats = await this.orm.call("contador.automatico", "obtener_estadisticas_dashboard", []);
            this.state.stats = { ...this.state.stats, ...stats };
            
            // Cargar lista de equipos
            const equipos = await this.orm.call("contador.automatico", "obtener_lista_equipos_dashboard", [100]);
            this.state.equipos = equipos;
            
            this.state.loading = false;
            
        } catch (error) {
            console.error("Error cargando datos del dashboard:", error);
            this.state.error = error.message || "Error cargando datos";
            this.state.loading = false;
            
            this.notification.add("Error cargando dashboard", {
                type: "danger"
            });
        }
    }
    
    /**
     * Configura auto-refresh cada 5 minutos
     */
    setupAutoRefresh() {
        this.refreshInterval = setInterval(() => {
            this.loadData();
        }, 5 * 60 * 1000); // 5 minutos
    }
    
    /**
     * Limpia interval al destruir componente
     */
    willUnmount() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }
    
    /**
     * Refresca datos manualmente
     */
    async refreshData() {
        try {
            await this.loadData();
            this.notification.add("Dashboard actualizado", {
                type: "success"
            });
        } catch (error) {
            this.notification.add("Error actualizando dashboard", {
                type: "danger"
            });
        }
    }
    
    /**
     * Obtiene clase CSS según el estado del sistema
     */
    getEstadoClass(estado) {
        const clases = {
            'optimo': 'bg-success',
            'atencion': 'bg-warning', 
            'critico': 'bg-danger'
        };
        return clases[estado] || 'bg-secondary';
    }
    
    /**
     * Obtiene texto del estado del sistema
     */
    getEstadoTexto(estado) {
        const textos = {
            'optimo': 'Óptimo',
            'atencion': 'Atención',
            'critico': 'Crítico'
        };
        return textos[estado] || 'Desconocido';
    }
    
    /**
     * Formatea número con separadores de miles
     */
    formatNumber(numero) {
        return new Intl.NumberFormat().format(numero || 0);
    }
    
    /**
     * Formatea fecha de forma legible
     */
    formatFecha(fechaStr) {
        if (!fechaStr) return 'Sin fecha';
        
        try {
            const fecha = new Date(fechaStr);
            return fecha.toLocaleDateString('es-ES', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch {
            return fechaStr;
        }
    }
    
    /**
     * Filtra equipos según criterios seleccionados
     */
    get equiposFiltrados() {
        let equipos = this.state.equipos;
        
        // Filtro por búsqueda
        if (this.state.filtros.search) {
            const busqueda = this.state.filtros.search.toLowerCase();
            equipos = equipos.filter(equipo => 
                (equipo.serie_detectada || '').toLowerCase().includes(busqueda) ||
                (equipo.cliente_detectado || '').toLowerCase().includes(busqueda)
            );
        }
        
        // Filtro por tipo
        if (this.state.filtros.tipo !== 'todos') {
            equipos = equipos.filter(equipo => 
                equipo.tipo_equipo_detectado === this.state.filtros.tipo
            );
        }
        
        // Filtro por estado
        if (this.state.filtros.estado !== 'todos') {
            equipos = equipos.filter(equipo => 
                equipo.estado_ultimo === this.state.filtros.estado
            );
        }
        
        return equipos;
    }
    
    /**
     * Actualiza filtro de búsqueda
     */
    onSearchChange(event) {
        this.state.filtros.search = event.target.value;
    }
    
    /**
     * Actualiza filtro de tipo
     */
    onTipoChange(event) {
        this.state.filtros.tipo = event.target.value;
    }
    
    /**
     * Actualiza filtro de estado
     */
    onEstadoChange(event) {
        this.state.filtros.estado = event.target.value;
    }
    
    /**
     * Muestra detalle de un equipo
     */
    async verDetalle(equipoId) {
        try {
            const detalle = await this.orm.call("contador.automatico", "obtener_detalle_equipo", [equipoId]);
            
            // Aquí podrías abrir un modal o navegar a vista detalle
            console.log("Detalle del equipo:", detalle);
            
            // Por ahora, mostrar notificación
            this.notification.add(`Detalle del equipo ${detalle.serie_detectada}`, {
                type: "info"
            });
            
        } catch (error) {
            this.notification.add("Error obteniendo detalle del equipo", {
                type: "danger"
            });
        }
    }
    
    /**
     * Obtiene clase CSS para el estado del equipo
     */
    getEstadoEquipoClass(estado) {
        const clases = {
            'procesado': 'badge-success',
            'pendiente': 'badge-warning',
            'error': 'badge-danger',
            'manual': 'badge-info'
        };
        return clases[estado] || 'badge-secondary';
    }
    
    /**
     * Obtiene icono para el tipo de equipo
     */
    getTipoEquipoIcon(tipo) {
        const iconos = {
            'color': 'fa-palette',
            'monocromatica': 'fa-circle'
        };
        return iconos[tipo] || 'fa-printer';
    }
}

/**
 * Template del dashboard
 */
ContadorDashboardWidget.template = `
<div class="o_dashboard_container">
    <!-- Encabezado -->
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h2 class="mb-0">Dashboard de Contadores</h2>
        <div>
            <button class="btn btn-primary" t-on-click="refreshData">
                <i class="fa fa-refresh"></i> Actualizar
            </button>
        </div>
    </div>
    
    <!-- Loading -->
    <div t-if="state.loading" class="text-center p-5">
        <i class="fa fa-spinner fa-spin fa-2x"></i>
        <p class="mt-2">Cargando dashboard...</p>
    </div>
    
    <!-- Error -->
    <div t-elif="state.error" class="alert alert-danger">
        <i class="fa fa-exclamation-triangle"></i>
        Error: <t t-esc="state.error"/>
    </div>
    
    <!-- Dashboard principal -->
    <div t-else="">
        <!-- Tarjetas de estadísticas -->
        <div class="row mb-4">
            <div class="col-md-3">
                <div class="card bg-primary text-white">
                    <div class="card-body">
                        <div class="d-flex justify-content-between">
                            <div>
                                <h4 class="mb-0" t-esc="formatNumber(state.stats.equipos_unicos_hoy)"/>
                                <p class="mb-0">Equipos Hoy</p>
                            </div>
                            <div class="align-self-center">
                                <i class="fa fa-calendar-day fa-2x"></i>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="col-md-3">
                <div class="card bg-success text-white">
                    <div class="card-body">
                        <div class="d-flex justify-content-between">
                            <div>
                                <h4 class="mb-0" t-esc="formatNumber(state.stats.equipos_unicos_semana)"/>
                                <p class="mb-0">Equipos Esta Semana</p>
                            </div>
                            <div class="align-self-center">
                                <i class="fa fa-calendar-week fa-2x"></i>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="col-md-3">
                <div class="card bg-info text-white">
                    <div class="card-body">
                        <div class="d-flex justify-content-between">
                            <div>
                                <h4 class="mb-0" t-esc="formatNumber(state.stats.total_equipos_sistema)"/>
                                <p class="mb-0">Total Equipos</p>
                            </div>
                            <div class="align-self-center">
                                <i class="fa fa-printer fa-2x"></i>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="col-md-3">
                <div t-attf-class="card text-white {{getEstadoClass(state.stats.estado_sistema)}}">
                    <div class="card-body">
                        <div class="d-flex justify-content-between">
                            <div>
                                <h4 class="mb-0" t-esc="state.stats.eficiencia_sistema"/>%</h4>
                                <p class="mb-0" t-esc="getEstadoTexto(state.stats.estado_sistema)"/>
                            </div>
                            <div class="align-self-center">
                                <i class="fa fa-chart-line fa-2x"></i>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Filtros -->
        <div class="card mb-4">
            <div class="card-body">
                <div class="row">
                    <div class="col-md-4">
                        <label>Buscar:</label>
                        <input type="text" class="form-control" placeholder="Serie o cliente..." 
                               t-model="state.filtros.search" t-on-input="onSearchChange"/>
                    </div>
                    <div class="col-md-4">
                        <label>Tipo:</label>
                        <select class="form-control" t-model="state.filtros.tipo" t-on-change="onTipoChange">
                            <option value="todos">Todos</option>
                            <option value="color">Color</option>
                            <option value="monocromatica">Monocromática</option>
                        </select>
                    </div>
                    <div class="col-md-4">
                        <label>Estado:</label>
                        <select class="form-control" t-model="state.filtros.estado" t-on-change="onEstadoChange">
                            <option value="todos">Todos</option>
                            <option value="procesado">Procesado</option>
                            <option value="pendiente">Pendiente</option>
                            <option value="manual">Manual</option>
                            <option value="error">Error</option>
                        </select>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Lista de equipos -->
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0">Equipos Detectados (<t t-esc="equiposFiltrados.length"/>)</h5>
            </div>
            <div class="card-body p-0">
                <div t-if="equiposFiltrados.length === 0" class="text-center p-4 text-muted">
                    <i class="fa fa-search fa-3x mb-3"></i>
                    <p>No se encontraron equipos con los filtros aplicados</p>
                </div>
                
                <div t-else="" class="table-responsive">
                    <table class="table table-hover mb-0">
                        <thead class="thead-light">
                            <tr>
                                <th>Serie</th>
                                <th>Cliente</th>
                                <th>Tipo</th>
                                <th>Contador B/N</th>
                                <th>Contador Color</th>
                                <th>Total</th>
                                <th>Última Actualización</th>
                                <th>Estado</th>
                                <th>Acciones</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr t-foreach="equiposFiltrados" t-as="equipo" t-key="equipo.id">
                                <td>
                                    <strong t-esc="equipo.serie_detectada"/>
                                </td>
                                <td>
                                    <t t-esc="equipo.cliente_detectado"/>
                                </td>
                                <td>
                                    <i t-attf-class="fa {{getTipoEquipoIcon(equipo.tipo_equipo_detectado)}} mr-1"></i>
                                    <t t-esc="equipo.tipo_equipo_detectado"/>
                                </td>
                                <td class="text-right">
                                    <t t-esc="formatNumber(equipo.contador_bn_actual)"/>
                                </td>
                                <td class="text-right">
                                    <t t-esc="formatNumber(equipo.contador_color_actual)"/>
                                </td>
                                <td class="text-right">
                                    <strong t-esc="formatNumber(equipo.contador_total_actual)"/>
                                </td>
                                <td>
                                    <small t-esc="formatFecha(equipo.ultima_actualizacion)"/>
                                </td>
                                <td>
                                    <span t-attf-class="badge {{getEstadoEquipoClass(equipo.estado_ultimo)}}"
                                          t-esc="equipo.estado_ultimo"/>
                                </td>
                                <td>
                                    <button class="btn btn-sm btn-outline-primary" 
                                            t-on-click="() => this.verDetalle(equipo.id)"
                                            title="Ver detalle">
                                        <i class="fa fa-eye"></i>
                                    </button>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>
`;

// Registrar el componente como una acción
registry.category("actions").add("contador_dashboard_widget", ContadorDashboardWidget);