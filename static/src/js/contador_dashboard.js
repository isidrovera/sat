/** @odoo-module **/
import { Component, onWillStart, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";

export class ContadorDashboardController extends FormController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        
        this.state = useState({
            estadisticas: {
                equipos_unicos_hoy: 0,
                equipos_unicos_semana: 0,
                total_equipos_sistema: 0,
                eficiencia_sistema: 0,
                estado_sistema: 'optimo'
            },
            equipos: [],
            filteredEquipos: [],
            currentPage: 1,
            itemsPerPage: 10,
            totalPages: 1,
            loading: false,
            searchQuery: '',
            activeFilter: 'all'
        });
        
        onWillStart(this.loadDashboardData);
        onMounted(this.setupEventListeners);
    }

    async loadDashboardData() {
        this.state.loading = true;
        try {
            // Cargar estadísticas
            const estadisticas = await this.orm.call(
                "contador.automatico",
                "obtener_estadisticas_dashboard",
                []
            );
            
            // Cargar lista de equipos
            const equipos = await this.orm.call(
                "contador.automatico", 
                "obtener_lista_equipos_dashboard",
                [100] // Límite de equipos
            );
            
            this.state.estadisticas = estadisticas;
            this.state.equipos = equipos;
            this.state.filteredEquipos = equipos;
            this.updatePagination();
            
            // Actualizar UI
            this.updateStatsDisplay();
            this.renderEquiposList();
            
        } catch (error) {
            console.error("Error cargando dashboard:", error);
            this.notification.add("Error cargando datos del dashboard", {
                type: "danger"
            });
        } finally {
            this.state.loading = false;
            this.updateLoadingState();
        }
    }

    setupEventListeners() {
        // Auto-refresh cada 5 minutos
        this.refreshInterval = setInterval(() => {
            this.loadDashboardData();
        }, 5 * 60 * 1000);

        // Listeners para filtros y búsqueda
        const searchInput = document.getElementById('search_input');
        if (searchInput) {
            searchInput.addEventListener('input', this.handleSearch.bind(this));
        }

        // Listeners para botones de filtro
        const filterButtons = document.querySelectorAll('.filter-btn');
        filterButtons.forEach(btn => {
            btn.addEventListener('click', this.handleFilter.bind(this));
        });

        // Listener para botón de refresh
        const refreshBtn = document.getElementById('floating_refresh');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', this.refreshDashboard.bind(this));
        }
    }

    updateStatsDisplay() {
        const stats = this.state.estadisticas;
        
        // Actualizar contadores
        this.updateElement('equipos_hoy', this.formatNumber(stats.equipos_unicos_hoy));
        this.updateElement('equipos_semana', this.formatNumber(stats.equipos_unicos_semana));
        this.updateElement('total_equipos', this.formatNumber(stats.total_equipos_sistema));
        this.updateElement('eficiencia', `${stats.eficiencia_sistema}%`);
        
        // Actualizar timestamp
        this.updateElement('last_update', this.formatDateTime(new Date()));
        
        // Actualizar clase de eficiencia según el estado
        const eficienciaCard = document.querySelector('[id="eficiencia"]')?.closest('.stat-card');
        if (eficienciaCard) {
            eficienciaCard.className = `stat-card h-100 ${this.getEstadoClass(stats.estado_sistema)}`;
        }
    }

    renderEquiposList() {
        const tbody = document.getElementById('machines_tbody');
        if (!tbody) return;

        const start = (this.state.currentPage - 1) * this.state.itemsPerPage;
        const end = start + this.state.itemsPerPage;
        const pageEquipos = this.state.filteredEquipos.slice(start, end);

        tbody.innerHTML = '';

        if (pageEquipos.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center py-5">
                        <div class="text-muted">
                            <i class="fa fa-search fa-3x mb-3 d-block"></i>
                            <h5>No se encontraron equipos</h5>
                            <p>Intenta cambiar los filtros de búsqueda</p>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        pageEquipos.forEach(equipo => {
            const row = this.createEquipoRow(equipo);
            tbody.appendChild(row);
        });

        // Actualizar contadores
        this.updateElement('showing_count', pageEquipos.length);
        this.updateElement('total_count', this.state.filteredEquipos.length);
        
        this.renderPagination();
    }

    createEquipoRow(equipo) {
        const row = document.createElement('tr');
        row.className = 'machine-row';
        row.setAttribute('data-equipo-id', equipo.id);

        const estadoClass = this.getEstadoEquipoClass(equipo.estado_ultimo);
        const tipoIcon = this.getTipoIcon(equipo.tipo_equipo_detectado);

        row.innerHTML = `
            <td class="px-4 py-3">
                <div class="d-flex align-items-center">
                    <div class="avatar-sm bg-light rounded-circle me-3 d-flex align-items-center justify-content-center">
                        <i class="fa fa-building text-primary"></i>
                    </div>
                    <div>
                        <div class="fw-semibold">${this.escapeHtml(equipo.cliente_detectado || 'Sin cliente')}</div>
                        <small class="text-muted">Cliente</small>
                    </div>
                </div>
            </td>
            <td class="px-4 py-3">
                <div class="d-flex align-items-center">
                    <div class="avatar-sm bg-secondary rounded-circle me-3 d-flex align-items-center justify-content-center">
                        <i class="fa fa-barcode text-white"></i>
                    </div>
                    <div>
                        <div class="fw-semibold font-monospace">${this.escapeHtml(equipo.serie_detectada || 'Sin serie')}</div>
                        <small class="text-muted">Número de serie</small>
                    </div>
                </div>
            </td>
            <td class="px-4 py-3 text-center">
                <div class="badge bg-light text-dark">
                    <i class="fa ${tipoIcon} me-1"></i>
                    ${this.escapeHtml(equipo.tipo_equipo_detectado || 'Sin tipo')}
                </div>
            </td>
            <td class="px-4 py-3 text-center">
                <div class="counters-container">
                    <div class="row g-2">
                        <div class="col-4">
                            <div class="counter-item">
                                <div class="counter-value">${this.formatNumber(equipo.contador_bn_actual || 0)}</div>
                                <div class="counter-label">B/N</div>
                            </div>
                        </div>
                        <div class="col-4">
                            <div class="counter-item">
                                <div class="counter-value">${this.formatNumber(equipo.contador_color_actual || 0)}</div>
                                <div class="counter-label">Color</div>
                            </div>
                        </div>
                        <div class="col-4">
                            <div class="counter-item">
                                <div class="counter-value fw-bold text-primary">${this.formatNumber(equipo.contador_total_actual || 0)}</div>
                                <div class="counter-label">Total</div>
                            </div>
                        </div>
                    </div>
                </div>
            </td>
            <td class="px-4 py-3 text-center">
                <div class="text-muted small">
                    <i class="fa fa-clock me-1"></i>
                    ${this.formatDateTime(equipo.ultima_actualizacion)}
                </div>
                <div class="text-muted smaller">
                    ${this.getTimeAgo(equipo.ultima_actualizacion)}
                </div>
            </td>
            <td class="px-4 py-3 text-center">
                <span class="badge ${estadoClass}">
                    ${this.escapeHtml(equipo.estado_ultimo || 'Sin estado')}
                </span>
            </td>
            <td class="px-4 py-3 text-center">
                <div class="btn-group" role="group">
                    <button type="button" 
                            class="btn btn-sm btn-outline-primary"
                            onclick="dashboard.verDetalle(${equipo.id})"
                            title="Ver detalle">
                        <i class="fa fa-eye"></i>
                    </button>
                    <button type="button" 
                            class="btn btn-sm btn-outline-secondary"
                            onclick="dashboard.verHistorial(${equipo.id})"
                            title="Ver historial">
                        <i class="fa fa-history"></i>
                    </button>
                </div>
            </td>
        `;

        return row;
    }

    renderPagination() {
        const pagination = document.getElementById('pagination');
        if (!pagination) return;

        pagination.innerHTML = '';

        if (this.state.totalPages <= 1) return;

        // Botón anterior
        const prevBtn = this.createPaginationButton(
            this.state.currentPage - 1,
            '<i class="fa fa-chevron-left"></i>',
            this.state.currentPage === 1
        );
        pagination.appendChild(prevBtn);

        // Páginas
        const startPage = Math.max(1, this.state.currentPage - 2);
        const endPage = Math.min(this.state.totalPages, this.state.currentPage + 2);

        for (let i = startPage; i <= endPage; i++) {
            const pageBtn = this.createPaginationButton(i, i.toString(), false, i === this.state.currentPage);
            pagination.appendChild(pageBtn);
        }

        // Botón siguiente
        const nextBtn = this.createPaginationButton(
            this.state.currentPage + 1,
            '<i class="fa fa-chevron-right"></i>',
            this.state.currentPage === this.state.totalPages
        );
        pagination.appendChild(nextBtn);
    }

    createPaginationButton(page, text, disabled = false, active = false) {
        const li = document.createElement('li');
        li.className = `page-item ${disabled ? 'disabled' : ''} ${active ? 'active' : ''}`;

        const a = document.createElement('a');
        a.className = 'page-link';
        a.href = '#';
        a.innerHTML = text;

        if (!disabled) {
            a.addEventListener('click', (e) => {
                e.preventDefault();
                this.goToPage(page);
            });
        }

        li.appendChild(a);
        return li;
    }

    // Event Handlers
    handleSearch(event) {
        this.state.searchQuery = event.target.value.toLowerCase();
        this.applyFilters();
    }

    handleFilter(event) {
        const filterType = event.target.getAttribute('data-filter');
        
        // Actualizar botón activo
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        event.target.classList.add('active');
        
        this.state.activeFilter = filterType;
        this.applyFilters();
    }

    applyFilters() {
        let filtered = [...this.state.equipos];

        // Filtro por búsqueda
        if (this.state.searchQuery) {
            filtered = filtered.filter(equipo => {
                const cliente = (equipo.cliente_detectado || '').toLowerCase();
                const serie = (equipo.serie_detectada || '').toLowerCase();
                return cliente.includes(this.state.searchQuery) || 
                       serie.includes(this.state.searchQuery);
            });
        }

        // Filtro por tipo
        switch (this.state.activeFilter) {
            case 'hoy':
                const hoy = new Date();
                hoy.setHours(0, 0, 0, 0);
                filtered = filtered.filter(equipo => {
                    const fecha = new Date(equipo.ultima_actualizacion);
                    return fecha >= hoy;
                });
                break;
            case 'color':
                filtered = filtered.filter(equipo => 
                    equipo.tipo_equipo_detectado === 'color'
                );
                break;
            case 'mono':
                filtered = filtered.filter(equipo => 
                    equipo.tipo_equipo_detectado === 'monocromatica'
                );
                break;
        }

        this.state.filteredEquipos = filtered;
        this.state.currentPage = 1;
        this.updatePagination();
        this.renderEquiposList();
    }

    updatePagination() {
        this.state.totalPages = Math.ceil(this.state.filteredEquipos.length / this.state.itemsPerPage);
        if (this.state.currentPage > this.state.totalPages) {
            this.state.currentPage = Math.max(1, this.state.totalPages);
        }
    }

    goToPage(page) {
        if (page >= 1 && page <= this.state.totalPages) {
            this.state.currentPage = page;
            this.renderEquiposList();
        }
    }

    async refreshDashboard() {
        this.notification.add("Actualizando dashboard...", { type: "info" });
        await this.loadDashboardData();
        this.notification.add("Dashboard actualizado correctamente", { type: "success" });
    }

    async verDetalle(equipoId) {
        try {
            const detalle = await this.orm.call(
                "contador.automatico",
                "obtener_detalle_equipo",
                [equipoId]
            );

            this.mostrarModalDetalle(detalle);
        } catch (error) {
            this.notification.add("Error obteniendo detalle del equipo", { type: "danger" });
        }
    }

    mostrarModalDetalle(detalle) {
        const modalContent = document.getElementById('modal_content');
        if (!modalContent) return;

        modalContent.innerHTML = `
            <div class="row">
                <div class="col-md-6">
                    <h6 class="text-muted mb-3">Información General</h6>
                    <table class="table table-sm">
                        <tr>
                            <td><strong>Serie:</strong></td>
                            <td>${this.escapeHtml(detalle.serie_detectada || 'N/A')}</td>
                        </tr>
                        <tr>
                            <td><strong>Cliente:</strong></td>
                            <td>${this.escapeHtml(detalle.cliente_detectado || 'N/A')}</td>
                        </tr>
                        <tr>
                            <td><strong>Tipo:</strong></td>
                            <td>${this.escapeHtml(detalle.tipo_equipo_detectado || 'N/A')}</td>
                        </tr>
                        <tr>
                            <td><strong>Marca:</strong></td>
                            <td>${this.escapeHtml(detalle.marca_detectada || 'N/A')}</td>
                        </tr>
                        <tr>
                            <td><strong>Estado:</strong></td>
                            <td>
                                <span class="badge ${this.getEstadoEquipoClass(detalle.estado_ultimo)}">
                                    ${this.escapeHtml(detalle.estado_ultimo || 'N/A')}
                                </span>
                            </td>
                        </tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <h6 class="text-muted mb-3">Contadores Actuales</h6>
                    <div class="row g-3">
                        <div class="col-4 text-center">
                            <div class="bg-light rounded p-3">
                                <div class="h4 mb-1">${this.formatNumber(detalle.contador_bn_actual || 0)}</div>
                                <small class="text-muted">Blanco y Negro</small>
                            </div>
                        </div>
                        <div class="col-4 text-center">
                            <div class="bg-light rounded p-3">
                                <div class="h4 mb-1">${this.formatNumber(detalle.contador_color_actual || 0)}</div>
                                <small class="text-muted">Color</small>
                            </div>
                        </div>
                        <div class="col-4 text-center">
                            <div class="bg-primary text-white rounded p-3">
                                <div class="h4 mb-1">${this.formatNumber(detalle.contador_total_actual || 0)}</div>
                                <small>Total</small>
                            </div>
                        </div>
                    </div>
                    
                    <h6 class="text-muted mb-3 mt-4">Información Adicional</h6>
                    <table class="table table-sm">
                        <tr>
                            <td><strong>Archivo origen:</strong></td>
                            <td>${this.escapeHtml(detalle.archivo_origen || 'N/A')}</td>
                        </tr>
                        <tr>
                            <td><strong>Remitente:</strong></td>
                            <td>${this.escapeHtml(detalle.remitente || 'N/A')}</td>
                        </tr>
                        <tr>
                            <td><strong>Creado:</strong></td>
                            <td>${this.formatDateTime(detalle.create_date)}</td>
                        </tr>
                        <tr>
                            <td><strong>Actualizado:</strong></td>
                            <td>${this.formatDateTime(detalle.write_date)}</td>
                        </tr>
                    </table>
                </div>
            </div>
        `;

        // Mostrar modal (asumiendo Bootstrap)
        const modal = new bootstrap.Modal(document.getElementById('detailModal'));
        modal.show();
    }

    async verHistorial(equipoId) {
        this.notification.add("Funcionalidad de historial próximamente", { type: "info" });
    }

    // Utility functions
    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }

    updateLoadingState() {
        const overlay = document.getElementById('loading_overlay');
        if (overlay) {
            if (this.state.loading) {
                overlay.classList.remove('d-none');
            } else {
                overlay.classList.add('d-none');
            }
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
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch {
            return dateStr;
        }
    }

    getTimeAgo(dateStr) {
        if (!dateStr) return '';
        try {
            const date = new Date(dateStr);
            const now = new Date();
            const diffMs = now - date;
            const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
            const diffDays = Math.floor(diffHours / 24);

            if (diffHours < 1) return 'Hace menos de 1h';
            if (diffHours < 24) return `Hace ${diffHours}h`;
            if (diffDays < 7) return `Hace ${diffDays}d`;
            return '';
        } catch {
            return '';
        }
    }

    getEstadoClass(estado) {
        const clases = {
            'optimo': 'bg-success',
            'atencion': 'bg-warning',
            'critico': 'bg-danger'
        };
        return clases[estado] || 'bg-secondary';
    }

    getEstadoEquipoClass(estado) {
        const clases = {
            'procesado': 'bg-success',
            'pendiente': 'bg-warning',
            'error': 'bg-danger',
            'manual': 'bg-info'
        };
        return clases[estado] || 'bg-secondary';
    }

    getTipoIcon(tipo) {
        const iconos = {
            'color': 'fa-palette',
            'monocromatica': 'fa-circle'
        };
        return iconos[tipo] || 'fa-printer';
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Cleanup
    willUnmount() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }
}

// Registrar el controlador
registry.category("views").add("contador_dashboard_form", {
    type: "form",
    display_name: "Dashboard Contadores",
    icon: "fa fa-chart-line",
    multiRecord: false,
    Controller: ContadorDashboardController,
});

// Exponer dashboard globalmente para los onclick en HTML
window.dashboard = {
    verDetalle: (id) => {
        // Esta función será sobrescrita por la instancia del controlador
        console.log('Ver detalle:', id);
    },
    verHistorial: (id) => {
        console.log('Ver historial:', id);
    }
};