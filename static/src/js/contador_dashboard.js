/** @odoo-module **/
import { Component, onWillStart, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ContadorDashboardWidget extends Component {
    static template = "contador.DashboardTemplate";
    
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        
        this.state = useState({
            loading: true,
            estadisticas: {
                equipos_unicos_hoy: 0,
                equipos_unicos_semana: 0,
                total_equipos_sistema: 0,
                eficiencia_sistema: 0
            },
            equipos: []
        });
        
        onWillStart(this.loadData);
        onMounted(this.setupDOM);
    }
    
    async loadData() {
        try {
            this.state.loading = true;
            
            // Cargar estadísticas
            const stats = await this.orm.call("contador.automatico", "obtener_estadisticas_dashboard", []);
            this.state.estadisticas = stats;
            
            // Cargar equipos
            const equipos = await this.orm.call("contador.automatico", "obtener_lista_equipos_dashboard", [50]);
            this.state.equipos = equipos;
            
        } catch (error) {
            console.error("Error cargando dashboard:", error);
            this.notification.add("Error cargando datos", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }
    
    setupDOM() {
        // Actualizar elementos del DOM cuando esté listo
        setTimeout(() => {
            this.updateStatsDisplay();
            this.renderEquiposList();
        }, 100);
    }
    
    updateStatsDisplay() {
        const stats = this.state.estadisticas;
        
        this.updateElement('equipos_hoy', this.formatNumber(stats.equipos_unicos_hoy || 0));
        this.updateElement('equipos_semana', this.formatNumber(stats.equipos_unicos_semana || 0));
        this.updateElement('total_equipos', this.formatNumber(stats.total_equipos_sistema || 0));
        this.updateElement('eficiencia', `${stats.eficiencia_sistema || 0}%`);
        this.updateElement('last_update', this.formatDateTime(new Date()));
    }
    
    renderEquiposList() {
        const tbody = document.getElementById('machines_tbody');
        if (!tbody || !this.state.equipos.length) return;
        
        tbody.innerHTML = '';
        
        this.state.equipos.slice(0, 10).forEach(equipo => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td class="px-4 py-3">${this.escapeHtml(equipo.cliente_detectado || 'Sin cliente')}</td>
                <td class="px-4 py-3">${this.escapeHtml(equipo.serie_detectada || 'Sin serie')}</td>
                <td class="px-4 py-3 text-center">
                    <span class="badge bg-light text-dark">${this.escapeHtml(equipo.tipo_equipo_detectado || 'N/A')}</span>
                </td>
                <td class="px-4 py-3 text-center">
                    <small>B/N: ${this.formatNumber(equipo.contador_bn_actual || 0)}</small><br>
                    <small>Color: ${this.formatNumber(equipo.contador_color_actual || 0)}</small><br>
                    <strong>Total: ${this.formatNumber(equipo.contador_total_actual || 0)}</strong>
                </td>
                <td class="px-4 py-3 text-center">
                    <small>${this.formatDateTime(equipo.ultima_actualizacion)}</small>
                </td>
                <td class="px-4 py-3 text-center">
                    <span class="badge ${this.getEstadoClass(equipo.estado_ultimo)}">${equipo.estado_ultimo || 'N/A'}</span>
                </td>
            `;
            tbody.appendChild(row);
        });
        
        this.updateElement('showing_count', Math.min(10, this.state.equipos.length));
        this.updateElement('total_count', this.state.equipos.length);
    }
    
    // Utility functions
    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }
    
    formatNumber(number) {
        return new Intl.NumberFormat('es-ES').format(number || 0);
    }
    
    formatDateTime(dateStr) {
        if (!dateStr) return 'N/A';
        try {
            const date = new Date(dateStr);
            return date.toLocaleDateString('es-ES', {
                day: '2-digit',
                month: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch {
            return 'N/A';
        }
    }
    
    getEstadoClass(estado) {
        const clases = {
            'procesado': 'bg-success',
            'pendiente': 'bg-warning',
            'error': 'bg-danger',
            'manual': 'bg-info'
        };
        return clases[estado] || 'bg-secondary';
    }
    
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

ContadorDashboardWidget.template = `
<div class="o_dashboard_simple">
    <div t-if="state.loading" class="text-center p-5">
        <i class="fa fa-spinner fa-spin fa-2x"></i>
        <p>Cargando dashboard...</p>
    </div>
    <div t-else="">
        <h3>Dashboard funcionando</h3>
        <p>Los datos se cargarán en el DOM existente</p>
    </div>
</div>
`;

// Registrar como acción simple
registry.category("actions").add("contador_dashboard_simple", ContadorDashboardWidget);