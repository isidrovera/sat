/** @odoo-module **/

import { Component, onWillStart, onMounted, onPatched, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";

console.log("🚀 Dashboard JS: Archivo cargado correctamente");

export class ContadorDashboardController extends FormController {
    setup() {
        console.log("🔧 Dashboard: Iniciando setup del controlador");
        super.setup();
        
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        
        console.log("✅ Dashboard: Servicios ORM y notification inicializados");
        
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
            activeFilter: 'all',
            domReady: false
        });

        console.log("✅ Dashboard: Estado inicial configurado", this.state);

        onWillStart(() => {
            console.log("🎯 Dashboard: onWillStart ejecutándose");
            return this.loadDashboardData();
        });
        
        onMounted(() => {
            console.log("🎯 Dashboard: onMounted ejecutándose");
            this.setupEventListeners();
            this.waitForDOMAndUpdate();
        });

        onPatched(() => {
            console.log("🎯 Dashboard: onPatched ejecutándose");
            if (!this.state.domReady) {
                this.waitForDOMAndUpdate();
            }
        });
    }

    waitForDOMAndUpdate() {
        console.log("⏳ Dashboard: Esperando que el DOM esté listo...");
        
        // Intentar encontrar elementos con retry
        let attempts = 0;
        const maxAttempts = 10;
        
        const checkDOM = () => {
            attempts++;
            console.log(`🔍 Dashboard: Intento ${attempts}/${maxAttempts} de encontrar elementos`);
            
            const equiposHoy = document.getElementById('equipos_hoy');
            const machinesTbody = document.getElementById('machines_tbody');
            
            if (equiposHoy && machinesTbody) {
                console.log("✅ Dashboard: DOM listo, actualizando UI");
                this.state.domReady = true;
                this.updateStatsDisplay();
                this.renderEquiposList();
                return true;
            }
            
            if (attempts < maxAttempts) {
                console.log("⏳ Dashboard: DOM no listo, reintentando en 100ms...");
                setTimeout(checkDOM, 100);
            } else {
                console.error("❌ Dashboard: DOM no se cargó después de todos los intentos");
                this.showFallbackMessage();
            }
            return false;
        };
        
        checkDOM();
    }

    showFallbackMessage() {
        // Mostrar mensaje si el DOM no se carga
        const container = document.querySelector('.o_contador_dashboard_main');
        if (container) {
            container.innerHTML = `
                <div class="alert alert-warning text-center m-4">
                    <h4>⚠️ Dashboard en modo de compatibilidad</h4>
                    <p>Los datos se han cargado correctamente:</p>
                    <ul class="list-unstyled">
                        <li><strong>Equipos hoy:</strong> ${this.state.estadisticas.equipos_unicos_hoy}</li>
                        <li><strong>Equipos semana:</strong> ${this.state.estadisticas.equipos_unicos_semana}</li>
                        <li><strong>Total equipos:</strong> ${this.state.estadisticas.total_equipos_sistema}</li>
                        <li><strong>Eficiencia:</strong> ${this.state.estadisticas.eficiencia_sistema}%</li>
                    </ul>
                    <p>Equipos encontrados: ${this.state.equipos.length}</p>
                    <button class="btn btn-primary" onclick="location.reload()">🔄 Recargar página</button>
                </div>
            `;
        }
    }

    async loadDashboardData() {
        console.log("📊 Dashboard: Iniciando carga de datos");
        this.state.loading = true;
        
        try {
            console.log("🔄 Dashboard: Llamando a obtener_estadisticas_dashboard");
            
            // Cargar estadísticas
            const estadisticas = await this.orm.call(
                "contador.automatico",
                "obtener_estadisticas_dashboard",
                []
            );
            
            console.log("✅ Dashboard: Estadísticas recibidas:", estadisticas);
            
            console.log("🔄 Dashboard: Llamando a obtener_lista_equipos_dashboard");
            
            // Cargar lista de equipos
            const equipos = await this.orm.call(
                "contador.automatico", 
                "obtener_lista_equipos_dashboard",
                []
            );
            
            console.log("✅ Dashboard: Equipos recibidos:", equipos);
            
            this.state.estadisticas = estadisticas;
            this.state.equipos = equipos;
            this.state.filteredEquipos = equipos;
            this.updatePagination();
            
            console.log("🎨 Dashboard: Datos cargados, esperando DOM para actualizar UI");
            
        } catch (error) {
            console.error("❌ Dashboard: Error cargando datos:", error);
            console.error("❌ Dashboard: Stack trace:", error.stack);
            
            this.notification.add("Error cargando datos del dashboard: " + error.message, {
                type: "danger"
            });
        } finally {
            this.state.loading = false;
            this.hideLoading();
            console.log("✅ Dashboard: Carga de datos finalizada");
        }
    }

    setupEventListeners() {
        console.log("🎧 Dashboard: Configurando event listeners");
        
        // Usar delegación de eventos para elementos que pueden no existir aún
        document.addEventListener('click', (e) => {
            // Botones de filtro
            if (e.target.closest('.filter-btn')) {
                const filter = e.target.closest('.filter-btn').dataset.filter;
                console.log("🔍 Dashboard: Filtro clickeado:", filter);
                this.handleFilterClick(filter);
            }
            
            // Botón refresh
            if (e.target.closest('[name="refresh_dashboard"]')) {
                console.log("🔄 Dashboard: Refresh clickeado");
                this.refreshDashboard();
            }
        });

        // Búsqueda con delegación
        document.addEventListener('input', (e) => {
            if (e.target.id === 'search_input') {
                console.log("🔍 Dashboard: Búsqueda:", e.target.value);
                this.handleSearch(e.target.value);
            }
        });
        
        console.log("✅ Dashboard: Event listeners configurados con delegación");
    }

    updateStatsDisplay() {
        console.log("📊 Dashboard: Actualizando display de estadísticas");
        const stats = this.state.estadisticas;
        console.log("📊 Dashboard: Stats a mostrar:", stats);
        
        // Actualizar números con animación
        this.animateNumber('equipos_hoy', stats.equipos_unicos_hoy);
        this.animateNumber('equipos_semana', stats.equipos_unicos_semana);
        this.animateNumber('total_equipos', stats.total_equipos_sistema);
        this.animateNumber('eficiencia', stats.eficiencia_sistema, '%');

        // Actualizar timestamp
        const lastUpdate = document.getElementById('last_update');
        if (lastUpdate) {
            lastUpdate.textContent = new Date().toLocaleString();
            console.log("✅ Dashboard: Timestamp actualizado");
        } else {
            console.warn("⚠️ Dashboard: Elemento last_update NO encontrado");
        }
    }

    animateNumber(elementId, targetValue, suffix = '') {
        const element = document.getElementById(elementId);
        if (!element) {
            console.warn(`⚠️ Dashboard: Elemento ${elementId} NO encontrado para animación`);
            return;
        }

        console.log(`🎬 Dashboard: Animando ${elementId} a ${targetValue}${suffix}`);

        let current = 0;
        const increment = targetValue / 30;
        const duration = 1000;
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
        console.log("📋 Dashboard: Renderizando lista de equipos");
        const tbody = document.getElementById('machines_tbody');
        if (!tbody) {
            console.error("❌ Dashboard: Elemento machines_tbody NO encontrado");
            return;
        }

        const startIndex = (this.state.currentPage - 1) * this.state.itemsPerPage;
        const endIndex = startIndex + this.state.itemsPerPage;
        const equiposPage = this.state.filteredEquipos.slice(startIndex, endIndex);

        console.log(`📋 Dashboard: Mostrando ${equiposPage.length} equipos de ${this.state.filteredEquipos.length} total`);

        tbody.innerHTML = '';

        if (equiposPage.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center py-4">
                        <div class="text-muted">
                            <i class="fa fa-inbox fa-3x mb-3"></i>
                            <h5>No hay equipos para mostrar</h5>
                            <p>No se encontraron registros con los filtros aplicados</p>
                        </div>
                    </td>
                </tr>
            `;
            console.log("📋 Dashboard: No hay equipos para mostrar");
            return;
        }

        equiposPage.forEach((equipo, index) => {
            const row = this.createEquipoRow(equipo, startIndex + index + 1);
            tbody.appendChild(row);
        });

        this.updateCounters();
        this.renderPagination();
        console.log("✅ Dashboard: Lista de equipos renderizada");
    }

    createEquipoRow(equipo, index) {
        console.log(`📋 Dashboard: Creando fila para equipo ${equipo.id}:`, equipo);
        
        const tr = document.createElement('tr');
        tr.className = 'table-row-hover';
        tr.dataset.equipoId = equipo.id;

        // Determinar iconos y clases con Bootstrap Icons
        const tipoIcon = equipo.tipo_equipo_detectado === 'color' ? 
            '<i class="bi bi-palette-fill text-info"></i>' : 
            '<i class="bi bi-circle-fill text-secondary"></i>';
        
        const tipoClass = equipo.tipo_equipo_detectado === 'color' ? 'text-info' : 'text-secondary';

        // Estado badge con Bootstrap
        const estadoBadge = this.getEstadoBadge(equipo.estado_ultimo);

        // Fecha relativa
        const fechaRelativa = this.getRelativeTime(equipo.ultima_actualizacion);

        tr.innerHTML = `
            <td class="px-3 py-2">
                <div class="d-flex align-items-center">
                    <span class="me-3 fs-4">${tipoIcon}</span>
                    <div>
                        <div class="fw-bold">${equipo.cliente_detectado || 'Cliente no detectado'}</div>
                        <small class="text-muted">Cliente #${index}</small>
                    </div>
                </div>
            </td>
            <td class="px-3 py-2">
                <div class="fw-bold text-primary">${equipo.serie_detectada || 'Sin serie'}</div>
                <small class="text-muted">
                    <i class="bi bi-hash"></i> Nº Serie
                </small>
            </td>
            <td class="px-3 py-2 text-center">
                <span class="badge bg-light ${tipoClass} border">
                    ${tipoIcon} ${equipo.tipo_equipo_detectado || 'No detectado'}
                </span>
            </td>
            <td class="px-3 py-2 text-center">
                <div class="small">
                    <div>
                        <i class="bi bi-circle-fill text-dark me-1"></i>
                        BN: <strong>${(equipo.contador_bn_actual || 0).toLocaleString()}</strong>
                    </div>
                    ${equipo.tipo_equipo_detectado === 'color' ? 
                        `<div>
                            <i class="bi bi-palette-fill text-info me-1"></i>
                            Color: <strong class="text-info">${(equipo.contador_color_actual || 0).toLocaleString()}</strong>
                        </div>` : ''}
                    <div>
                        <i class="bi bi-bar-chart-fill text-success me-1"></i>
                        Total: <strong class="text-success">${(equipo.contador_total_actual || 0).toLocaleString()}</strong>
                    </div>
                </div>
            </td>
            <td class="px-3 py-2 text-center">
                <div class="fw-bold small">${fechaRelativa}</div>
                <small class="text-muted">
                    <i class="bi bi-calendar3"></i>
                    ${new Date(equipo.ultima_actualizacion).toLocaleDateString()}
                </small>
            </td>
            <td class="px-3 py-2 text-center">
                ${estadoBadge}
            </td>
            <td class="px-3 py-2 text-center">
                <button type="button" class="btn btn-sm btn-outline-primary btn-detail" data-equipo-id="${equipo.id}">
                    <i class="bi bi-eye me-1"></i>Ver
                </button>
            </td>
        `;

        // Agregar event listener para el botón de detalle
        const btnDetail = tr.querySelector('.btn-detail');
        btnDetail.addEventListener('click', () => {
            this.showDetail(equipo.id);
        });

        return tr;
    }

    getEstadoBadge(estado) {
        const badges = {
            'procesado': '<span class="badge bg-success"><i class="bi bi-check-circle me-1"></i>Procesado</span>',
            'pendiente': '<span class="badge bg-warning"><i class="bi bi-clock me-1"></i>Pendiente</span>',
            'error': '<span class="badge bg-danger"><i class="bi bi-exclamation-triangle me-1"></i>Error</span>',
            'manual': '<span class="badge bg-info"><i class="bi bi-hand-index me-1"></i>Manual</span>'
        };
        return badges[estado] || '<span class="badge bg-secondary"><i class="bi bi-question-circle me-1"></i>Desconocido</span>';
    }

    getRelativeTime(dateString) {
        if (!dateString) return 'Sin fecha';
        
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
        console.log("🔍 Dashboard: Aplicando filtro:", filter);
        
        // Actualizar botones activos
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        
        const filterBtn = document.querySelector(`[data-filter="${filter}"]`);
        if (filterBtn) {
            filterBtn.classList.add('active');
        }

        this.state.activeFilter = filter;
        this.applyFilters();
    }

    handleSearch(query) {
        console.log("🔍 Dashboard: Búsqueda:", query);
        this.state.searchQuery = query.toLowerCase();
        this.applyFilters();
    }

    applyFilters() {
        console.log("🔍 Dashboard: Aplicando filtros. Filtro activo:", this.state.activeFilter, "Búsqueda:", this.state.searchQuery);
        
        let filtered = [...this.state.equipos];
        console.log("🔍 Dashboard: Equipos iniciales:", filtered.length);

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

        console.log("🔍 Dashboard: Después de filtro de tipo:", filtered.length);

        // Aplicar búsqueda
        if (this.state.searchQuery) {
            filtered = filtered.filter(equipo => 
                (equipo.cliente_detectado || '').toLowerCase().includes(this.state.searchQuery) ||
                (equipo.serie_detectada || '').toLowerCase().includes(this.state.searchQuery)
            );
        }

        console.log("🔍 Dashboard: Después de búsqueda:", filtered.length);

        this.state.filteredEquipos = filtered;
        this.state.currentPage = 1;
        this.updatePagination();
        this.renderEquiposList();
    }

    updatePagination() {
        this.state.totalPages = Math.ceil(this.state.filteredEquipos.length / this.state.itemsPerPage);
        console.log("📄 Dashboard: Paginación actualizada. Páginas totales:", this.state.totalPages);
    }

    updateCounters() {
        const showingCount = document.getElementById('showing_count');
        const totalCount = document.getElementById('total_count');
        
        if (showingCount && totalCount) {
            const startIndex = (this.state.currentPage - 1) * this.state.itemsPerPage;
            const endIndex = Math.min(startIndex + this.state.itemsPerPage, this.state.filteredEquipos.length);
            
            showingCount.textContent = `${startIndex + 1}-${endIndex}`;
            totalCount.textContent = this.state.filteredEquipos.length;
            
            console.log(`📊 Dashboard: Contadores actualizados: ${startIndex + 1}-${endIndex} de ${this.state.filteredEquipos.length}`);
        }
    }

    renderPagination() {
        const pagination = document.getElementById('pagination');
        if (!pagination) {
            console.warn("⚠️ Dashboard: Elemento pagination NO encontrado");
            return;
        }

        pagination.innerHTML = '';

        if (this.state.totalPages <= 1) {
            console.log("📄 Dashboard: Solo una página, no se muestra paginación");
            return;
        }

        console.log("📄 Dashboard: Renderizando paginación");
    }

    async showDetail(equipoId) {
        console.log("👁️ Dashboard: Mostrando detalle del equipo:", equipoId);
        try {
            const detalle = await this.orm.call(
                "contador.automatico",
                "obtener_detalle_equipo",
                [parseInt(equipoId)]
            );

            console.log("👁️ Dashboard: Detalle recibido:", detalle);
            this.renderDetailModal(detalle);
            
            // Mostrar modal
            const modal = document.getElementById('detailModal');
            if (modal) {
                if (typeof bootstrap !== 'undefined') {
                    const bsModal = new bootstrap.Modal(modal);
                    bsModal.show();
                } else {
                    modal.style.display = 'block';
                    modal.classList.add('show');
                }
            }

        } catch (error) {
            console.error("❌ Dashboard: Error cargando detalle:", error);
            this.notification.add("Error cargando detalle del equipo: " + error.message, {
                type: "danger"
            });
        }
    }

    renderDetailModal(detalle) {
        console.log("👁️ Dashboard: Renderizando modal de detalle");
        const modalContent = document.getElementById('modal_content');
        if (!modalContent) {
            console.error("❌ Dashboard: Elemento modal_content NO encontrado");
            return;
        }

        modalContent.innerHTML = `
            <div class="row">
                <div class="col-md-6">
                    <h6 class="text-primary mb-3">
                        <i class="bi bi-info-circle me-2"></i>
                        Información del Equipo
                    </h6>
                    <table class="table table-sm">
                        <tr>
                            <td><strong><i class="bi bi-building me-1"></i>Cliente:</strong></td>
                            <td>${detalle.cliente_detectado || 'No detectado'}</td>
                        </tr>
                        <tr>
                            <td><strong><i class="bi bi-hash me-1"></i>Serie:</strong></td>
                            <td class="text-primary">${detalle.serie_detectada || 'No detectada'}</td>
                        </tr>
                        <tr>
                            <td><strong><i class="bi bi-gear me-1"></i>Tipo:</strong></td>
                            <td>${detalle.tipo_equipo_detectado || 'No detectado'}</td>
                        </tr>
                        <tr>
                            <td><strong><i class="bi bi-check-circle me-1"></i>Estado:</strong></td>
                            <td>${this.getEstadoBadge(detalle.estado_ultimo)}</td>
                        </tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <h6 class="text-success mb-3">
                        <i class="bi bi-bar-chart me-2"></i>
                        Contadores Actuales
                    </h6>
                    <div class="text-center">
                        <div class="row">
                            <div class="col-4">
                                <div class="border rounded p-2 mb-2">
                                    <div class="fs-1">
                                        <i class="bi bi-circle-fill text-dark"></i>
                                    </div>
                                    <h6>${(detalle.contador_bn_actual || 0).toLocaleString()}</h6>
                                    <small>B/N</small>
                                </div>
                            </div>
                            ${detalle.tipo_equipo_detectado === 'color' ? `
                                <div class="col-4">
                                    <div class="border rounded p-2 mb-2">
                                        <div class="fs-1">
                                            <i class="bi bi-palette-fill text-info"></i>
                                        </div>
                                        <h6 class="text-info">${(detalle.contador_color_actual || 0).toLocaleString()}</h6>
                                        <small>Color</small>
                                    </div>
                                </div>
                            ` : ''}
                            <div class="col-4">
                                <div class="border rounded p-2 mb-2">
                                    <div class="fs-1">
                                        <i class="bi bi-bar-chart-fill text-success"></i>
                                    </div>
                                    <h6 class="text-success">${(detalle.contador_total_actual || 0).toLocaleString()}</h6>
                                    <small>Total</small>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }class="text-success">${(detalle.contador_total_actual || 0).toLocaleString()}</h6>
                                    <small>Total</small>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    async refreshDashboard() {
        console.log("🔄 Dashboard: Refrescando dashboard");
        this.showLoading();
        await this.loadDashboardData();
        
        if (this.state.domReady) {
            this.updateStatsDisplay();
            this.renderEquiposList();
        }
        
        this.notification.add("Dashboard actualizado correctamente", {
            type: "success"
        });
    }

    showLoading() {
        const loading = document.getElementById('loading_overlay');
        if (loading) {
            loading.classList.remove('d-none');
            console.log("⏳ Dashboard: Loading overlay mostrado");
        }
    }

    hideLoading() {
        const loading = document.getElementById('loading_overlay');
        if (loading) {
            loading.classList.add('d-none');
            console.log("✅ Dashboard: Loading overlay ocultado");
        }
    }
}

console.log("🎯 Dashboard: Registrando controlador en registry");

// Registrar el controlador
registry.category("views").add("contador_dashboard_form", {
    ...registry.category("views").get("form"),
    Controller: ContadorDashboardController,
});

console.log("✅ Dashboard: Controlador registrado correctamente");

// Exponer funciones globalmente
window.dashboard = {
    showDetail: (equipoId) => {
        console.log("🌐 Dashboard: showDetail llamado globalmente para equipo:", equipoId);
        const activeController = document.querySelector('.o_contador_dashboard_main')?.__owl__?.component;
        if (activeController && activeController.showDetail) {
            activeController.showDetail(equipoId);
        } else {
            console.error("❌ Dashboard: No se encontró controlador activo");
        }
    }
};

console.log("✅ Dashboard: Funciones globales expuestas en window.dashboard");