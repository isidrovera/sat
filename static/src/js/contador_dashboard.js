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

        onWillStart(async () => {
            console.log("🎯 Dashboard: onWillStart ejecutándose");
            await this.loadDashboardData();
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

    async waitForDOMAndUpdate() {
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
                        <i class="fa fa-inbox fa-3x text-muted mb-3"></i>
                        <h5>No hay equipos para mostrar</h5>
                        <p class="text-muted">No se encontraron registros con los filtros aplicados</p>
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

        // Determinar iconos y clases
        const tipoIcon = equipo.tipo_equipo_detectado === 'color' ? '🎨' : '⚫';
        const tipoClass = equipo.tipo_equipo_detectado === 'color' ? 'text-info' : 'text-secondary';

        // Estado badge
        const estadoBadge = this.getEstadoBadge(equipo.estado_ultimo);

        // Fecha relativa
        const fechaRelativa = this.getRelativeTime(equipo.ultima_actualizacion);

        tr.innerHTML = `
            <td class="px-3 py-2">
                <div class="d-flex align-items-center">
                    <span class="me-2 fs-4">${tipoIcon}</span>
                    <div>
                        <div class="fw-bold">${equipo.cliente_detectado || 'Cliente no detectado'}</div>
                        <small class="text-muted">Cliente #${index}</small>
                    </div>
                </div>
            </td>
            <td class="px-3 py-2">
                <div class="fw-bold text-primary">${equipo.serie_detectada || 'Sin serie'}</div>
                <small class="text-muted">Nº Serie</small>
            </td>
            <td class="px-3 py-2 text-center">
                <span class="badge bg-light ${tipoClass} border">
                    ${tipoIcon} ${equipo.tipo_equipo_detectado || 'No detectado'}
                </span>
            </td>
            <td class="px-3 py-2 text-center">
                <div class="small">
                    <div>⚫ BN: <strong>${(equipo.contador_bn_actual || 0).toLocaleString()}</strong></div>
                    ${equipo.tipo_equipo_detectado === 'color' ? 
                        `<div>🎨 Color: <strong class="text-info">${(equipo.contador_color_actual || 0).toLocaleString()}</strong></div>` : ''}
                    <div>📊 Total: <strong class="text-success">${(equipo.contador_total_actual || 0).toLocaleString()}</strong></div>
                </div>
            </td>
            <td class="px-3 py-2 text-center">
                <div class="fw-bold small">${fechaRelativa}</div>
                <small class="text-muted">${new Date(equipo.ultima_actualizacion).toLocaleDateString()}</small>
            </td>
            <td class="px-3 py-2 text-center">
                ${estadoBadge}
            </td>
            <td class="px-3 py-2 text-center">
                <button type="button" class="btn btn-sm btn-outline-primary btn-detail" data-equipo-id="${equipo.id}">
                    👁️ Ver
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
            'procesado': '<span class="badge bg-success">✅ Procesado</span>',
            'pendiente': '<span class="badge bg-warning">⏳ Pendiente</span>',
            'error': '<span class="badge bg-danger">❌ Error</span>',
            'manual': '<span class="badge bg-info">✋ Manual</span>'
        };
        return badges[estado] || '<span class="badge bg-secondary">❓ Desconocido</span>';
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
        // Aquí agregarías la lógica de paginación si es necesaria
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
                // Intentar con Bootstrap si está disponible
                if (typeof bootstrap !== 'undefined') {
                    const bsModal = new bootstrap.Modal(modal);
                    bsModal.show();
                } else {
                    // Fallback simple
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

        // Crear contenido del modal...
        modalContent.innerHTML = `
            <div class="row">
                <div class="col-md-6">
                    <h6 class="text-primary mb-3">📋 Información del Equipo</h6>
                    <table class="table table-sm">
                        <tr><td><strong>Cliente:</strong></td><td>${detalle.cliente_detectado || 'No detectado'}</td></tr>
                        <tr><td><strong>Serie:</strong></td><td class="text-primary">${detalle.serie_detectada || 'No detectada'}</td></tr>
                        <tr><td><strong>Tipo:</strong></td><td>${detalle.tipo_equipo_detectado || 'No detectado'}</td></tr>
                        <tr><td><strong>Estado:</strong></td><td>${this.getEstadoBadge(detalle.estado_ultimo)}</td></tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <h6 class="text-success mb-3">📊 Contadores Actuales</h6>
                    <div class="text-center">
                        <div class="row">
                            <div class="col-4">
                                <div class="border rounded p-2 mb-2">
                                    <div class="fs-1">⚫</div>
                                    <h6>${(detalle.contador_bn_actual || 0).toLocaleString()}</h6>
                                    <small>B/N</small>
                                </div>
                            </div>
                            ${detalle.tipo_equipo_detectado === 'color' ? `
                                <div class="col-4">
                                    <div class="border rounded p-2 mb-2">
                                        <div class="fs-1">🎨</div>
                                        <h6 class="text-info">${(detalle.contador_color_actual || 0).toLocaleString()}</h6>
                                        <small>Color</small>
                                    </div>
                                </div>
                            ` : ''}
                            <div class="col-4">
                                <div class="border rounded p-2 mb-2">
                                    <div class="fs-1">📊</div>
                                    <h6 class="text-success">${(detalle.contador_total_actual || 0).toLocaleString()}</h6>
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

// Exponer funciones globalmente para uso en templates
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
            
            console.log("🎨 Dashboard: Actualizando UI");
            // Actualizar UI
            this.updateStatsDisplay();
            this.renderEquiposList();
            
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
        
        // Botones de filtro
        const filterBtns = document.querySelectorAll('.filter-btn');
        console.log("🔍 Dashboard: Botones de filtro encontrados:", filterBtns.length);
        
        filterBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                console.log("🔍 Dashboard: Filtro clickeado:", e.target.dataset.filter);
                this.handleFilterClick(e.target.dataset.filter);
            });
        });

        // Búsqueda
        const searchInput = document.getElementById('search_input');
        if (searchInput) {
            console.log("🔍 Dashboard: Input de búsqueda encontrado");
            searchInput.addEventListener('input', (e) => {
                console.log("🔍 Dashboard: Búsqueda:", e.target.value);
                this.handleSearch(e.target.value);
            });
        } else {
            console.warn("⚠️ Dashboard: Input de búsqueda NO encontrado");
        }

        // Botón refresh flotante
        const floatingRefresh = document.getElementById('floating_refresh');
        if (floatingRefresh) {
            console.log("🔄 Dashboard: Botón refresh flotante encontrado");
            floatingRefresh.addEventListener('click', () => {
                console.log("🔄 Dashboard: Refresh flotante clickeado");
                this.refreshDashboard();
            });
        } else {
            console.warn("⚠️ Dashboard: Botón refresh flotante NO encontrado");
        }

        // Refresh principal
        const refreshBtn = document.querySelector('[name="refresh_dashboard"]');
        if (refreshBtn) {
            console.log("🔄 Dashboard: Botón refresh principal encontrado");
            refreshBtn.addEventListener('click', () => {
                console.log("🔄 Dashboard: Refresh principal clickeado");
                this.refreshDashboard();
            });
        } else {
            console.warn("⚠️ Dashboard: Botón refresh principal NO encontrado");
        }
        
        console.log("✅ Dashboard: Event listeners configurados");
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
                        <i class="fa fa-inbox fa-3x text-muted mb-3"></i>
                        <h5>No hay equipos para mostrar</h5>
                        <p class="text-muted">No se encontraron registros con los filtros aplicados</p>
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
                        <i class="fa fa-chart-line text-success me-1"></i>
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
                <button type="button" class="btn btn-sm btn-outline-primary" onclick="window.dashboard.showDetail('${equipo.id}')">
                    <i class="fa fa-eye me-1"></i>
                    Detalle
                </button>
            </td>
        `;

        return tr;
    }

    getEstadoClass(estado) {
        const classes = {
            'procesado': 'bg-success',
            'pendiente': 'bg-warning',
            'error': 'bg-danger',
            'manual': 'bg-info'
        };
        return classes[estado] || 'bg-secondary';
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

        // Crear elementos de paginación...
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
                // Intentar con Bootstrap si está disponible
                if (typeof bootstrap !== 'undefined') {
                    const bsModal = new bootstrap.Modal(modal);
                    bsModal.show();
                } else {
                    // Fallback simple
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

        // Crear contenido del modal...
        modalContent.innerHTML = `
            <div class="alert alert-info">
                <h5>Información del Equipo</h5>
                <p><strong>Cliente:</strong> ${detalle.cliente_detectado || 'No detectado'}</p>
                <p><strong>Serie:</strong> ${detalle.serie_detectada || 'No detectada'}</p>
                <p><strong>Tipo:</strong> ${detalle.tipo_equipo_detectado || 'No detectado'}</p>
                <p><strong>Estado:</strong> ${detalle.estado_ultimo || 'Sin estado'}</p>
            </div>
        `;
    }

    async refreshDashboard() {
        console.log("🔄 Dashboard: Refrescando dashboard");
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

// Exponer funciones globalmente para uso en templates
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