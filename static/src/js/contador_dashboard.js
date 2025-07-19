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
                eficiencia_sistema: 0
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
                []
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
            this.hideLoading();
        }
    }

    setupEventListeners() {
        // Botones de filtro
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.handleFilterClick(e.target.dataset.filter);
            });
        });

        // Búsqueda
        const searchInput = document.getElementById('search_input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.handleSearch(e.target.value);
            });
        }

        // Botón refresh flotante
        const floatingRefresh = document.getElementById('floating_refresh');
        if (floatingRefresh) {
            floatingRefresh.addEventListener('click', () => {
                this.refreshDashboard();
            });
        }

        // Refresh principal
        const refreshBtn = document.querySelector('[name="refresh_dashboard"]');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.refreshDashboard();
            });
        }
    }

    updateStatsDisplay() {
        const stats = this.state.estadisticas;
        
        // Actualizar números con animación
        this.animateNumber('equipos_hoy', stats.equipos_unicos_hoy);
        this.animateNumber('equipos_semana', stats.equipos_unicos_semana);
        this.animateNumber('total_equipos', stats.total_equipos_sistema);
        this.animateNumber('eficiencia', stats.eficiencia_sistema, '%');

        // Actualizar timestamp
        const lastUpdate = document.getElementById('last_update');
        if (lastUpdate) {
            lastUpdate.textContent = new Date().toLocaleString();
        }
    }

    animateNumber(elementId, targetValue, suffix = '') {
        const element = document.getElementById(elementId);
        if (!element) return;

        let current = 0;
        const increment = targetValue / 30; // 30 pasos de animación
        const duration = 1000; // 1 segundo
        const stepTime = duration / 30;

        const timer = setInterval(() => {
            current += increment;
            if (current >= targetValue) {
                current = targetValue;
                clearInterval(timer);
            }
            element.textContent = Math.floor(current) + suffix;
        }, stepTime);
    }

    renderEquiposList() {
        const tbody = document.getElementById('machines_tbody');
        if (!tbody) return;

        const startIndex = (this.state.currentPage - 1) * this.state.itemsPerPage;
        const endIndex = startIndex + this.state.itemsPerPage;
        const equiposPage = this.state.filteredEquipos.slice(startIndex, endIndex);

        tbody.innerHTML = '';

        equiposPage.forEach((equipo, index) => {
            const row = this.createEquipoRow(equipo, startIndex + index + 1);
            tbody.appendChild(row);
        });

        this.updateCounters();
        this.renderPagination();
    }

    createEquipoRow(equipo, index) {
        const tr = document.createElement('tr');
        tr.className = 'machine-row';
        tr.dataset.equipoId = equipo.id;

        // Determinar iconos y clases
        const tipoIcon = equipo.tipo_equipo_detectado === 'color' ? 
            '<i class="fa fa-palette"></i>' : '<i class="fa fa-circle"></i>';
        const tipoClass = equipo.tipo_equipo_detectado === 'color' ? 
            'color-equipment' : 'mono-equipment';

        // Estado badge
        const estadoClass = this.getEstadoClass(equipo.estado_ultimo);
        const estadoText = this.getEstadoText(equipo.estado_ultimo);

        // Fecha relativa
        const fechaRelativa = this.getRelativeTime(equipo.ultima_actualizacion);

        tr.innerHTML = `
            <td class="px-4">
                <div class="d-flex align-items-center">
                    <div class="equipment-icon ${tipoClass}">
                        ${tipoIcon}
                    </div>
                    <div>
                        <div class="fw-bold text-dark">${equipo.cliente_detectado || 'Cliente no detectado'}</div>
                        <small class="text-muted">Cliente ${index}</small>
                    </div>
                </div>
            </td>
            <td class="px-4">
                <div class="fw-bold text-primary">${equipo.serie_detectada || 'Sin serie'}</div>
                <small class="text-muted">Nº Serie</small>
            </td>
            <td class="px-4 text-center">
                <span class="badge ${equipo.tipo_equipo_detectado === 'color' ? 'bg-info' : 'bg-secondary'}">
                    ${tipoIcon} ${equipo.tipo_equipo_detectado || 'No detectado'}
                </span>
            </td>
            <td class="px-4 text-center">
                <div class="d-flex justify-content-center flex-wrap gap-1">
                    <span class="counter-badge">
                        <i class="fa fa-circle text-dark me-1"></i>
                        BN: ${(equipo.contador_bn_actual || 0).toLocaleString()}
                    </span>
                    ${equipo.tipo_equipo_detectado === 'color' ? `
                        <span class="counter-badge">
                            <i class="fa fa-palette text-info me-1"></i>
                            Color: ${(equipo.contador_color_actual || 0).toLocaleString()}
                        </span>
                    ` : ''}
                    <span class="counter-badge">
                        <i class="fa fa-scanner text-success me-1"></i>
                        Total: ${(equipo.contador_total_actual || 0).toLocaleString()}
                    </span>
                </div>
            </td>
            <td class="px-4 text-center">
                <div class="fw-bold">${fechaRelativa}</div>
                <small class="text-muted">${new Date(equipo.ultima_actualizacion).toLocaleDateString()}</small>
            </td>
            <td class="px-4 text-center">
                <span class="status-badge ${estadoClass}">
                    ${this.getEstadoIcon(equipo.estado_ultimo)} ${estadoText}
                </span>
            </td>
            <td class="px-4 text-center">
                <button type="button" class="btn-detail" onclick="window.dashboard.showDetail('${equipo.id}')">
                    <i class="fa fa-eye me-1"></i>
                    Detalle
                </button>
            </td>
        `;

        return tr;
    }

    getEstadoClass(estado) {
        const classes = {
            'procesado': 'status-procesado',
            'pendiente': 'status-pendiente',
            'error': 'status-error',
            'manual': 'status-manual'
        };
        return classes[estado] || 'status-pendiente';
    }

    getEstadoText(estado) {
        const texts = {
            'procesado': 'Procesado',
            'pendiente': 'Pendiente',
            'error': 'Error',
            'manual': 'Manual'
        };
        return texts[estado] || 'Pendiente';
    }

    getEstadoIcon(estado) {
        const icons = {
            'procesado': '<i class="fa fa-check"></i>',
            'pendiente': '<i class="fa fa-clock"></i>',
            'error': '<i class="fa fa-exclamation-triangle"></i>',
            'manual': '<i class="fa fa-hand-paper"></i>'
        };
        return icons[estado] || '<i class="fa fa-clock"></i>';
    }

    getRelativeTime(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffMins < 1) return 'Ahora mismo';
        if (diffMins < 60) return `Hace ${diffMins} min`;
        if (diffHours < 24) return `Hace ${diffHours}h`;
        if (diffDays < 7) return `Hace ${diffDays} días`;
        return date.toLocaleDateString();
    }

    handleFilterClick(filter) {
        // Actualizar botones activos
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-filter="${filter}"]`).classList.add('active');

        this.state.activeFilter = filter;
        this.applyFilters();
    }

    handleSearch(query) {
        this.state.searchQuery = query.toLowerCase();
        this.applyFilters();
    }

    applyFilters() {
        let filtered = [...this.state.equipos];

        // Aplicar filtro de tipo
        if (this.state.activeFilter !== 'all') {
            if (this.state.activeFilter === 'hoy') {
                const hoy = new Date();
                hoy.setHours(0, 0, 0, 0);
                filtered = filtered.filter(equipo => 
                    new Date(equipo.ultima_actualizacion) >= hoy
                );
            } else if (this.state.activeFilter === 'color') {
                filtered = filtered.filter(equipo => 
                    equipo.tipo_equipo_detectado === 'color'
                );
            } else if (this.state.activeFilter === 'mono') {
                filtered = filtered.filter(equipo => 
                    equipo.tipo_equipo_detectado === 'monocromatica'
                );
            }
        }

        // Aplicar búsqueda
        if (this.state.searchQuery) {
            filtered = filtered.filter(equipo => 
                (equipo.cliente_detectado || '').toLowerCase().includes(this.state.searchQuery) ||
                (equipo.serie_detectada || '').toLowerCase().includes(this.state.searchQuery)
            );
        }

        this.state.filteredEquipos = filtered;
        this.state.currentPage = 1;
        this.updatePagination();
        this.renderEquiposList();
    }

    updatePagination() {
        this.state.totalPages = Math.ceil(this.state.filteredEquipos.length / this.state.itemsPerPage);
    }

    updateCounters() {
        const showingCount = document.getElementById('showing_count');
        const totalCount = document.getElementById('total_count');
        
        if (showingCount && totalCount) {
            const startIndex = (this.state.currentPage - 1) * this.state.itemsPerPage;
            const endIndex = Math.min(startIndex + this.state.itemsPerPage, this.state.filteredEquipos.length);
            
            showingCount.textContent = `${startIndex + 1}-${endIndex}`;
            totalCount.textContent = this.state.filteredEquipos.length;
        }
    }

    renderPagination() {
        const pagination = document.getElementById('pagination');
        if (!pagination) return;

        pagination.innerHTML = '';

        // Botón anterior
        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${this.state.currentPage === 1 ? 'disabled' : ''}`;
        prevLi.innerHTML = `
            <a class="page-link" href="#" data-page="${this.state.currentPage - 1}">
                <i class="fa fa-chevron-left"></i>
            </a>
        `;
        pagination.appendChild(prevLi);

        // Páginas
        const startPage = Math.max(1, this.state.currentPage - 2);
        const endPage = Math.min(this.state.totalPages, this.state.currentPage + 2);

        for (let i = startPage; i <= endPage; i++) {
            const li = document.createElement('li');
            li.className = `page-item ${i === this.state.currentPage ? 'active' : ''}`;
            li.innerHTML = `<a class="page-link" href="#" data-page="${i}">${i}</a>`;
            pagination.appendChild(li);
        }

        // Botón siguiente
        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${this.state.currentPage === this.state.totalPages ? 'disabled' : ''}`;
        nextLi.innerHTML = `
            <a class="page-link" href="#" data-page="${this.state.currentPage + 1}">
                <i class="fa fa-chevron-right"></i>
            </a>
        `;
        pagination.appendChild(nextLi);

        // Event listeners para paginación
        pagination.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = parseInt(e.target.closest('a').dataset.page);
                if (page && page !== this.state.currentPage && page >= 1 && page <= this.state.totalPages) {
                    this.state.currentPage = page;
                    this.renderEquiposList();
                }
            });
        });
    }

    async showDetail(equipoId) {
        try {
            const detalle = await this.orm.call(
                "contador.automatico",
                "obtener_detalle_equipo",
                [parseInt(equipoId)]
            );

            this.renderDetailModal(detalle);
            
            // Mostrar modal usando Bootstrap
            const modal = new bootstrap.Modal(document.getElementById('detailModal'));
            modal.show();

        } catch (error) {
            console.error("Error cargando detalle:", error);
            this.notification.add("Error cargando detalle del equipo", {
                type: "danger"
            });
        }
    }

    renderDetailModal(detalle) {
        const modalContent = document.getElementById('modal_content');
        if (!modalContent) return;

        modalContent.innerHTML = `
            <div class="row">
                <div class="col-md-6">
                    <h6 class="text-primary mb-3">
                        <i class="fa fa-info-circle me-2"></i>Información del Equipo
                    </h6>
                    <table class="table table-borderless">
                        <tr>
                            <td class="fw-bold">Cliente:</td>
                            <td>${detalle.cliente_detectado || 'No detectado'}</td>
                        </tr>
                        <tr>
                            <td class="fw-bold">Serie:</td>
                            <td class="text-primary">${detalle.serie_detectada || 'No detectada'}</td>
                        </tr>
                        <tr>
                            <td class="fw-bold">Tipo:</td>
                            <td>
                                <span class="badge ${detalle.tipo_equipo_detectado === 'color' ? 'bg-info' : 'bg-secondary'}">
                                    ${detalle.tipo_equipo_detectado || 'No detectado'}
                                </span>
                            </td>
                        </tr>
                        <tr>
                            <td class="fw-bold">Estado:</td>
                            <td>
                                <span class="status-badge ${this.getEstadoClass(detalle.estado_ultimo)}">
                                    ${this.getEstadoIcon(detalle.estado_ultimo)} ${this.getEstadoText(detalle.estado_ultimo)}
                                </span>
                            </td>
                        </tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <h6 class="text-success mb-3">
                        <i class="fa fa-tachometer-alt me-2"></i>Contadores Actuales
                    </h6>
                    <div class="row text-center">
                        <div class="col-4">
                            <div class="border rounded p-3 mb-2">
                                <i class="fa fa-circle text-dark fa-2x mb-2"></i>
                                <h5 class="mb-1">${(detalle.contador_bn_actual || 0).toLocaleString()}</h5>
                                <small class="text-muted">B/N</small>
                            </div>
                        </div>
                        ${detalle.tipo_equipo_detectado === 'color' ? `
                            <div class="col-4">
                                <div class="border rounded p-3 mb-2">
                                    <i class="fa fa-palette text-info fa-2x mb-2"></i>
                                    <h5 class="mb-1 text-info">${(detalle.contador_color_actual || 0).toLocaleString()}</h5>
                                    <small class="text-muted">Color</small>
                                </div>
                            </div>
                        ` : ''}
                        <div class="col-4">
                            <div class="border rounded p-3 mb-2">
                                <i class="fa fa-chart-line text-success fa-2x mb-2"></i>
                                <h5 class="mb-1 text-success">${(detalle.contador_total_actual || 0).toLocaleString()}</h5>
                                <small class="text-muted">Total</small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <hr class="my-4">
            
            <div class="row">
                <div class="col-12">
                    <h6 class="text-warning mb-3">
                        <i class="fa fa-clock me-2"></i>Información Temporal
                    </h6>
                    <div class="row">
                        <div class="col-md-6">
                            <p><strong>Última actualización:</strong><br>
                            <span class="text-muted">${new Date(detalle.ultima_actualizacion).toLocaleString()}</span></p>
                        </div>
                        <div class="col-md-6">
                            <p><strong>Tiempo transcurrido:</strong><br>
                            <span class="text-muted">${this.getRelativeTime(detalle.ultima_actualizacion)}</span></p>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    async refreshDashboard() {
        this.showLoading();
        await this.loadDashboardData();
        
        this.notification.add("Dashboard actualizado correctamente", {
            type: "success"
        });
    }

    showLoading() {
        const loading = document.getElementById('loading_overlay');
        if (loading) {
            loading.classList.remove('d-none');
        }
    }

    hideLoading() {
        const loading = document.getElementById('loading_overlay');
        if (loading) {
            loading.classList.add('d-none');
        }
    }
}

// Registrar el controlador
registry.category("views").add("contador_dashboard_form", {
    ...registry.category("views").get("form"),
    Controller: ContadorDashboardController,
});

// Exponer funciones globalmente para uso en templates
window.dashboard = {
    showDetail: (equipoId) => {
        const controller = registry.category("views").get("contador_dashboard_form").Controller;
        if (controller.prototype.showDetail) {
            // Buscar la instancia activa del controlador
            const activeController = document.querySelector('.o_contador_dashboard_main')?.__owl__?.component;
            if (activeController) {
                activeController.showDetail(equipoId);
            }
        }
    }
};