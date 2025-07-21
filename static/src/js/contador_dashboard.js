/**
 * Contadores Dashboard JavaScript
 * static/src/js/contadores_dashboard.js
 */

class ContadoresDashboard {
    constructor() {
        this.currentFilter = 'all';
        this.isLoading = false;
        this.sortDirection = {};
        this.equipos = [];
        this.filteredEquipos = [];
        this.autoRefreshInterval = null;
        this.searchTimeout = null;
        
        this.init();
    }

    init() {
        this.initializeElements();
        this.bindEvents();
        this.initializeAnimations();
        this.updateFilterCounts();
        this.startAutoRefresh();
        this.initializeTooltips();
        console.log('Contadores Dashboard inicializado correctamente');
    }

    initializeElements() {
        // Elementos principales
        this.filterButtons = document.querySelectorAll('.filter-btn');
        this.tableRows = document.querySelectorAll('.table-row');
        this.searchInput = document.querySelector('.search-input');
        this.clearSearchBtn = document.getElementById('clearSearch');
        this.refreshBtn = document.getElementById('refreshBtn');
        this.mainFab = document.getElementById('mainFab');
        this.fabMenu = document.getElementById('fabMenu');
        this.sortableHeaders = document.querySelectorAll('.sortable');
        this.viewToggleBtn = document.getElementById('viewToggle');
        
        // Elementos de estadísticas
        this.statCards = document.querySelectorAll('.stat-card');
        
        // Almacenar datos de equipos
        this.extractEquiposData();
    }

    extractEquiposData() {
        this.equipos = [];
        this.tableRows.forEach(row => {
            const cliente = row.querySelector('.client-name')?.textContent?.trim() || '';
            const serie = row.querySelector('.serie-number')?.textContent?.trim() || '';
            const tipo = row.dataset.tipo || '';
            const estado = row.dataset.estado || '';
            const fechaElement = row.querySelector('.date-value');
            const fecha = fechaElement ? fechaElement.textContent.trim() : '';
            
            // Obtener contadores
            const contadorBn = this.extractCounterValue(row, 0);
            const contadorColor = this.extractCounterValue(row, 1);
            const contadorTotal = this.extractCounterValue(row, 2);
            
            this.equipos.push({
                element: row,
                cliente,
                serie,
                tipo,
                estado,
                fecha,
                contadorBn,
                contadorColor,
                contadorTotal,
                visible: true
            });
        });
        this.filteredEquipos = [...this.equipos];
    }

    extractCounterValue(row, index) {
        const counterItems = row.querySelectorAll('.counter-item');
        if (counterItems[index]) {
            const valueText = counterItems[index].querySelector('.counter-value')?.textContent || '0';
            return parseInt(valueText.replace(/,/g, '')) || 0;
        }
        return 0;
    }

    bindEvents() {
        // Filtros
        this.filterButtons.forEach(btn => {
            btn.addEventListener('click', (e) => this.handleFilterClick(e));
        });

        // Búsqueda
        if (this.searchInput) {
            this.searchInput.addEventListener('input', (e) => this.handleSearch(e));
            this.searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.performSearch();
                }
            });
            
            // Mostrar/ocultar botón limpiar
            this.searchInput.addEventListener('input', (e) => {
                if (this.clearSearchBtn) {
                    this.clearSearchBtn.style.display = e.target.value ? 'block' : 'none';
                }
            });
        }

        // Limpiar búsqueda
        if (this.clearSearchBtn) {
            this.clearSearchBtn.addEventListener('click', () => this.clearSearch());
        }

        // Refresh
        if (this.refreshBtn) {
            this.refreshBtn.addEventListener('click', () => this.refreshDashboard());
        }

        // FAB Menu
        if (this.mainFab && this.fabMenu) {
            this.mainFab.addEventListener('click', () => this.toggleFabMenu());
        }

        // Vista Toggle
        if (this.viewToggleBtn) {
            this.viewToggleBtn.addEventListener('click', () => this.toggleTableView());
        }

        // Ordenamiento
        this.sortableHeaders.forEach(header => {
            header.addEventListener('click', (e) => this.handleSort(e));
        });

        // Cerrar FAB menu al hacer click fuera
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.fab-container')) {
                this.closeFabMenu();
            }
        });

        // Eventos de teclado globales
        this.bindKeyboardEvents();

        // Auto-actualización de fechas relativas
        setInterval(() => this.updateRelativeDates(), 60000); // Cada minuto

        // Responsive table scroll
        this.handleResponsiveTable();

        // Clicks en tarjetas de estadísticas
        this.statCards.forEach(card => {
            card.addEventListener('click', () => this.animateStatCard(card));
        });

        // Hover effects para filas de tabla
        this.tableRows.forEach(row => {
            row.addEventListener('mouseenter', () => this.highlightRow(row, true));
            row.addEventListener('mouseleave', () => this.highlightRow(row, false));
        });
    }

    bindKeyboardEvents() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + K para enfocar búsqueda
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                if (this.searchInput) {
                    this.searchInput.focus();
                    this.searchInput.select();
                }
            }
            
            // ESC para limpiar búsqueda o cerrar menús
            if (e.key === 'Escape') {
                if (this.searchInput && this.searchInput.value) {
                    this.clearSearch();
                } else {
                    this.closeFabMenu();
                }
            }

            // F5 para refresh (prevenir default y usar nuestro método)
            if (e.key === 'F5') {
                e.preventDefault();
                this.refreshDashboard();
            }

            // Números 1-5 para filtros rápidos
            if (e.key >= '1' && e.key <= '5' && !e.ctrlKey && !e.metaKey) {
                const filterIndex = parseInt(e.key) - 1;
                if (this.filterButtons[filterIndex]) {
                    this.filterButtons[filterIndex].click();
                }
            }
        });
    }

    initializeAnimations() {
        // Inicializar AOS si está disponible
        if (typeof AOS !== 'undefined') {
            AOS.init({
                duration: 600,
                easing: 'ease-out-cubic',
                once: true,
                offset: 50
            });
        }

        // Animación de entrada para las filas
        this.tableRows.forEach((row, index) => {
            row.style.animationDelay = `${index * 30}ms`;
            row.classList.add('fade-in-up');
        });

        // Animación para tarjetas de estadísticas
        this.statCards.forEach((card, index) => {
            card.style.animationDelay = `${index * 100}ms`;
        });
    }

    initializeTooltips() {
        // Inicializar tooltips de Bootstrap si está disponible
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[title]'));
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }
    }

    handleFilterClick(e) {
        const btn = e.currentTarget;
        const filter = btn.dataset.filter;

        // Actualizar botones activos
        this.filterButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        this.currentFilter = filter;
        this.applyFilters();

        // Animación del botón
        this.animateButton(btn);
        
        // Actualizar URL sin recargar
        this.updateUrlParams({ filter });
    }

    applyFilters() {
        let visibleCount = 0;
        const startTime = performance.now();

        this.equipos.forEach((equipo, index) => {
            let shouldShow = true;

            // Aplicar filtro
            switch (this.currentFilter) {
                case 'hoy':
                    shouldShow = this.isToday(equipo.fecha);
                    break;
                case 'color':
                    shouldShow = equipo.tipo.toLowerCase().includes('color');
                    break;
                case 'mono':
                    shouldShow = equipo.tipo.toLowerCase().includes('monocromatica') || 
                                equipo.tipo.toLowerCase().includes('mono');
                    break;
                case 'procesado':
                    shouldShow = equipo.estado === 'procesado';
                    break;
                case 'all':
                default:
                    shouldShow = true;
                    break;
            }

            // Aplicar filtro de búsqueda si existe
            if (shouldShow && this.searchInput?.value) {
                const searchTerm = this.searchInput.value.toLowerCase();
                shouldShow = equipo.cliente.toLowerCase().includes(searchTerm) ||
                           equipo.serie.toLowerCase().includes(searchTerm) ||
                           equipo.tipo.toLowerCase().includes(searchTerm);
            }

            // Mostrar/ocultar fila con animación
            if (shouldShow !== equipo.visible) {
                if (shouldShow) {
                    this.showRow(equipo.element, index);
                    visibleCount++;
                } else {
                    this.hideRow(equipo.element);
                }
                equipo.visible = shouldShow;
            } else if (shouldShow) {
                visibleCount++;
            }
        });

        const endTime = performance.now();
        console.log(`Filtros aplicados en ${endTime - startTime}ms`);

        this.updateFilterCounts();
        this.updateTableInfo(visibleCount);
        this.updateEmptyState(visibleCount);
    }

    showRow(element, index) {
        element.style.display = '';
        element.style.opacity = '0';
        element.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            element.style.transition = 'all 0.3s ease-out';
            element.style.opacity = '1';
            element.style.transform = 'translateY(0)';
        }, index * 20);
    }

    hideRow(element) {
        element.style.transition = 'all 0.2s ease-out';
        element.style.opacity = '0';
        element.style.transform = 'translateY(-10px)';
        
        setTimeout(() => {
            element.style.display = 'none';
        }, 200);
    }

    updateFilterCounts() {
        const counts = {
            all: this.equipos.length,
            hoy: this.equipos.filter(e => this.isToday(e.fecha)).length,
            color: this.equipos.filter(e => e.tipo.toLowerCase().includes('color')).length,
            mono: this.equipos.filter(e => 
                e.tipo.toLowerCase().includes('monocromatica') || 
                e.tipo.toLowerCase().includes('mono')
            ).length,
            procesado: this.equipos.filter(e => e.estado === 'procesado').length
        };

        Object.keys(counts).forEach(filter => {
            const countElement = document.getElementById(`count-${filter}`);
            if (countElement) {
                this.animateNumber(countElement, parseInt(countElement.textContent) || 0, counts[filter]);
            }
        });
    }

    animateNumber(element, from, to) {
        const duration = 500;
        const start = performance.now();
        
        const animate = (currentTime) => {
            const elapsed = currentTime - start;
            const progress = Math.min(elapsed / duration, 1);
            
            const current = Math.round(from + (to - from) * this.easeOutCubic(progress));
            element.textContent = current;
            
            if (progress < 1) {
                requestAnimationFrame(animate);
            }
        };
        
        requestAnimationFrame(animate);
    }

    easeOutCubic(t) {
        return 1 - Math.pow(1 - t, 3);
    }

    isToday(dateString) {
        if (!dateString) return false;
        
        try {
            const today = new Date();
            const itemDate = this.parseDate(dateString);
            
            return itemDate.toDateString() === today.toDateString();
        } catch (e) {
            return false;
        }
    }

    parseDate(dateString) {
        // Asume formato DD/MM/YYYY HH:MM
        const [datePart] = dateString.split(' ');
        const [day, month, year] = datePart.split('/');
        return new Date(year, month - 1, day);
    }

    handleSearch(e) {
        clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => {
            this.applyFilters();
        }, 300);
    }

    performSearch() {
        const form = this.searchInput.closest('form');
        if (form) {
            form.submit();
        }
    }

    clearSearch() {
        if (this.searchInput) {
            this.searchInput.value = '';
            if (this.clearSearchBtn) {
                this.clearSearchBtn.style.display = 'none';
            }
        }
        
        // Actualizar URL sin parámetro de búsqueda
        this.updateUrlParams({ search: null });
        
        this.applyFilters();
    }

    handleSort(e) {
        const header = e.currentTarget;
        const sortField = header.dataset.sort;
        
        if (!sortField) return;

        // Cambiar dirección de ordenamiento
        this.sortDirection[sortField] = this.sortDirection[sortField] === 'asc' ? 'desc' : 'asc';
        const direction = this.sortDirection[sortField];

        // Actualizar iconos
        this.updateSortIcons(header, direction);

        // Ordenar equipos
        this.sortEquipos(sortField, direction);
    }

    updateSortIcons(activeHeader, direction) {
        this.sortableHeaders.forEach(h => {
            const icon = h.querySelector('.sort-icon');
            if (icon) {
                if (h === activeHeader) {
                    icon.className = `fas sort-icon fa-sort-${direction === 'asc' ? 'up' : 'down'}`;
                    icon.style.color = 'var(--primary-color)';
                } else {
                    icon.className = 'fas sort-icon fa-sort';
                    icon.style.color = '';
                }
            }
        });
    }

    sortEquipos(field, direction) {
        const tbody = document.querySelector('.modern-table tbody');
        if (!tbody) return;

        const sortedEquipos = [...this.equipos].sort((a, b) => {
            let aValue, bValue;

            switch (field) {
                case 'cliente':
                    aValue = a.cliente.toLowerCase();
                    bValue = b.cliente.toLowerCase();
                    break;
                case 'serie':
                    aValue = a.serie.toLowerCase();
                    bValue = b.serie.toLowerCase();
                    break;
                case 'fecha':
                    aValue = this.parseDate(a.fecha);
                    bValue = this.parseDate(b.fecha);
                    break;
                default:
                    return 0;
            }

            if (aValue < bValue) return direction === 'asc' ? -1 : 1;
            if (aValue > bValue) return direction === 'asc' ? 1 : -1;
            return 0;
        });

        // Reordenar elementos en el DOM con animación
        sortedEquipos.forEach((equipo, index) => {
            setTimeout(() => {
                tbody.appendChild(equipo.element);
                equipo.element.style.animationDelay = `${index * 20}ms`;
                equipo.element.classList.add('fade-in-up');
            }, index * 10);
        });

        // Actualizar array de equipos
        this.equipos = sortedEquipos;
    }

    refreshDashboard() {
        if (this.isLoading) return;

        this.isLoading = true;
        this.setLoadingState(true);
        
        // Rotar icono
        const icon = this.refreshBtn.querySelector('i');
        if (icon) {
            icon.style.animation = 'spin 1s linear infinite';
        }

        // Intentar refresh via AJAX primero
        this.refreshViaAjax()
            .then(() => {
                this.showToast(this.createToast('Dashboard actualizado', 'success'));
            })
            .catch(() => {
                // Fallback a recarga completa
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
            })
            .finally(() => {
                this.isLoading = false;
                this.setLoadingState(false);
                if (icon) {
                    icon.style.animation = '';
                }
            });
    }

    async refreshViaAjax() {
        try {
            const response = await fetch('/dashboard/contador/refresh', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error('Error en la respuesta del servidor');
            }

            const data = await response.json();
            
            if (data.success) {
                // Actualizar timestamp
                this.updateLastRefreshTime();
                return Promise.resolve();
            } else {
                throw new Error(data.error || 'Error desconocido');
            }
        } catch (error) {
            console.error('Error en refresh AJAX:', error);
            return Promise.reject(error);
        }
    }

    updateLastRefreshTime() {
        const timestampElements = document.querySelectorAll('.last-update');
        const now = new Date().toLocaleString('es-ES');
        
        timestampElements.forEach(el => {
            el.innerHTML = `<i class="fas fa-clock me-1"></i>${now}`;
        });
    }

    setLoadingState(isLoading) {
        const elements = [this.refreshBtn, ...this.statCards];
        
        elements.forEach(el => {
            if (el) {
                if (isLoading) {
                    el.classList.add('loading');
                } else {
                    el.classList.remove('loading');
                }
            }
        });
    }

    toggleFabMenu() {
        const isActive = this.fabMenu.classList.contains('active');
        
        if (isActive) {
            this.closeFabMenu();
        } else {
            this.openFabMenu();
        }
    }

    openFabMenu() {
        this.fabMenu.classList.add('active');
        
        // Rotar icono principal
        const icon = this.mainFab.querySelector('i');
        if (icon) {
            icon.style.transform = 'rotate(45deg)';
        }

        // Animar botones del menú
        const fabButtons = this.fabMenu.querySelectorAll('.fab-secondary');
        fabButtons.forEach((btn, index) => {
            setTimeout(() => {
                btn.style.transform = 'scale(1) translateY(0)';
                btn.style.opacity = '1';
            }, index * 100);
        });
    }

    closeFabMenu() {
        this.fabMenu.classList.remove('active');
        
        const icon = this.mainFab.querySelector('i');
        if (icon) {
            icon.style.transform = '';
        }

        const fabButtons = this.fabMenu.querySelectorAll('.fab-secondary');
        fabButtons.forEach(btn => {
            btn.style.transform = 'scale(0) translateY(20px)';
            btn.style.opacity = '0';
        });
    }

    toggleTableView() {
        const table = document.querySelector('.modern-table');
        const isCompact = table.classList.contains('table-compact');
        
        table.classList.toggle('table-compact');
        
        const icon = this.viewToggleBtn.querySelector('i');
        if (icon) {
            icon.className = isCompact ? 'fas fa-th-large me-1' : 'fas fa-list me-1';
        }
    }

    updateRelativeDates() {
        document.querySelectorAll('.date-relative').forEach(element => {
            const dateValue = element.closest('.date-info')?.querySelector('.date-value')?.textContent;
            if (dateValue) {
                element.textContent = this.getRelativeTime(dateValue);
            }
        });
    }

    getRelativeTime(dateString) {
        try {
            const date = this.parseDate(dateString);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMins / 60);
            const diffDays = Math.floor(diffHours / 24);

            if (diffMins < 1) return 'Ahora mismo';
            if (diffMins < 60) return `Hace ${diffMins} min`;
            if (diffHours < 24) return `Hace ${diffHours}h`;
            if (diffDays < 7) return `Hace ${diffDays}d`;
            return dateString;
        } catch (e) {
            return dateString;
        }
    }

    updateTableInfo(visibleCount) {
        const info = document.querySelector('.table-subtitle');
        if (info) {
            const total = this.equipos.length;
            info.innerHTML = `Mostrando <span class="text-primary">${visibleCount}</span> de <span class="text-primary">${total}</span> equipos`;
        }

        // Actualizar info de paginación
        const paginationInfo = document.querySelector('.pagination-info');
        if (paginationInfo && visibleCount > 0) {
            paginationInfo.innerHTML = `Mostrando <strong>1-${visibleCount}</strong> de <strong>${this.equipos.length}</strong> registros`;
        }
    }

    updateEmptyState(visibleCount) {
        const tbody = document.querySelector('.modern-table tbody');
        const emptyState = document.querySelector('.empty-state');
        
        if (visibleCount === 0 && !emptyState && tbody) {
            const emptyRow = document.createElement('tr');
            emptyRow.innerHTML = `
                <td colspan="7" class="text-center py-5">
                    <div class="empty-state">
                        <div class="empty-icon">
                            <i class="fas fa-search"></i>
                        </div>
                        <h4 class="empty-title">No se encontraron equipos</h4>
                        <p class="empty-text">No hay registros que coincidan con los filtros aplicados</p>
                        <button class="btn btn-primary" onclick="window.contadoresDashboard.clearSearch(); window.contadoresDashboard.filterButtons[0].click();">
                            <i class="fas fa-refresh me-2"></i>Mostrar todos
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(emptyRow);
        } else if (visibleCount > 0 && emptyState) {
            emptyState.closest('tr')?.remove();
        }
    }

    handleResponsiveTable() {
        const table = document.querySelector('.table-responsive');
        if (!table) return;

        const updateScrollIndicator = () => {
            const isScrollable = table.scrollWidth > table.clientWidth;
            table.classList.toggle('has-scroll', isScrollable);
            
            if (isScrollable) {
                table.setAttribute('title', 'Desliza horizontalmente para ver más columnas');
            }
        };

        updateScrollIndicator();
        window.addEventListener('resize', updateScrollIndicator);
    }

    animateButton(button) {
        button.style.transform = 'scale(0.95)';
        setTimeout(() => {
            button.style.transform = '';
        }, 150);
    }

    animateStatCard(card) {
        card.style.transform = 'scale(0.98)';
        setTimeout(() => {
            card.style.transform = '';
        }, 200);
    }

    highlightRow(row, highlight) {
        if (highlight) {
            row.style.backgroundColor = 'rgba(102, 126, 234, 0.05)';
            row.style.transform = 'translateX(4px)';
        } else {
            row.style.backgroundColor = '';
            row.style.transform = '';
        }
    }

    startAutoRefresh() {
        // Auto-refresh cada 5 minutos
        this.autoRefreshInterval = setInterval(() => {
            if (!document.hidden && !this.isLoading) {
                this.showRefreshNotification();
            }
        }, 5 * 60 * 1000);

        // Pausar auto-refresh cuando la pestaña no está visible
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                if (this.autoRefreshInterval) {
                    clearInterval(this.autoRefreshInterval);
                }
            } else {
                this.startAutoRefresh();
            }
        });
    }

    showRefreshNotification() {
        const toast = this.createToast('Datos actualizados automáticamente', 'success');
        this.showToast(toast);
        
        this.updateLastRefreshTime();
    }

    createToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast-notification toast-${type}`;
        
        const icons = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        };
        
        const colors = {
            success: '#10b981',
            error: '#ef4444',
            warning: '#f59e0b',
            info: '#3b82f6'
        };
        
        toast.innerHTML = `
            <div class="toast-content">
                <i class="fas ${icons[type]} me-2"></i>
                ${message}
            </div>
            <button class="toast-close" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        // Estilos del toast
        Object.assign(toast.style, {
            position: 'fixed',
            top: '20px',
            right: '20px',
            background: colors[type],
            color: 'white',
            padding: '12px 20px',
            borderRadius: '8px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            zIndex: '9999',
            transform: 'translateX(100%)',
            transition: 'transform 0.3s ease-out',
            maxWidth: '350px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
        });

        return toast;
    }

    showToast(toast) {
        document.body.appendChild(toast);
        
        // Animar entrada
        setTimeout(() => {
            toast.style.transform = 'translateX(0)';
        }, 100);

        // Auto-remover después de 4 segundos
        setTimeout(() => {
            if (toast.parentNode) {
                toast.style.transform = 'translateX(100%)';
                setTimeout(() => {
                    if (toast.parentNode) {
                        toast.parentNode.removeChild(toast);
                    }
                }, 300);
            }
        }, 4000);
    }

    updateUrlParams(params) {
        const url = new URL(window.location);
        
        Object.keys(params).forEach(key => {
            if (params[key] === null || params[key] === undefined) {
                url.searchParams.delete(key);
            } else {
                url.searchParams.set(key, params[key]);
            }
        });
        
        window.history.replaceState({}, '', url);
    }

    // Método para exportar datos
    exportData(format = 'excel') {
        const exportBtn = document.createElement('a');
        exportBtn.href = `/dashboard/contador/export/${format}${window.location.search}`;
        exportBtn.style.display = 'none';
        document.body.appendChild(exportBtn);
        exportBtn.click();
        document.body.removeChild(exportBtn);

        this.showToast(this.createToast('Exportación iniciada', 'success'));
    }

    // Métodos de API para interactuar con el backend
    async loadEquipos(filters = {}) {
        try {
            const response = await fetch('/dashboard/contador/api/equipos', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(filters)
            });

            const data = await response.json();
            
            if (data.success) {
                this.updateTableWithData(data.data);
                return data;
            } else {
                throw new Error(data.error);
            }
        } catch (error) {
            console.error('Error cargando equipos:', error);
            this.showToast(this.createToast('Error cargando datos', 'error'));
            throw error;
        }
    }

    async loadStats() {
        try {
            const response = await fetch('/dashboard/contador/api/stats', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            const data = await response.json();
            
            if (data.success) {
                this.updateStatsCards(data.data.estadisticas_principales);
                return data;
            } else {
                throw new Error(data.error);
            }
        } catch (error) {
            console.error('Error cargando estadísticas:', error);
            this.showToast(this.createToast('Error cargando estadísticas', 'error'));
            throw error;
        }
    }

    updateTableWithData(data) {
        // Actualizar tabla con nuevos datos (para futuras implementaciones AJAX)
        const tbody = document.querySelector('.modern-table tbody');
        if (!tbody || !data) return;

        // Limpiar tabla actual
        tbody.innerHTML = '';

        // Agregar nuevas filas
        data.forEach((equipo, index) => {
            const row = this.createTableRow(equipo, index);
            tbody.appendChild(row);
        });

        // Reinicializar eventos y datos
        this.tableRows = document.querySelectorAll('.table-row');
        this.extractEquiposData();
        this.bindTableEvents();
    }

    createTableRow(equipo, index) {
        const row = document.createElement('tr');
        row.className = 'table-row';
        row.dataset.tipo = equipo.tipo || '';
        row.dataset.estado = equipo.estado || '';
        
        row.innerHTML = `
            <td class="px-4 py-3">
                <div class="client-info">
                    <div class="client-avatar">
                        <i class="fas fa-building"></i>
                    </div>
                    <div class="client-details">
                        <div class="client-name">${equipo.cliente || 'Sin cliente'}</div>
                        <div class="client-label">Cliente</div>
                    </div>
                </div>
            </td>
            <td class="px-4 py-3">
                <div class="serie-info">
                    <div class="serie-avatar">
                        <i class="fas fa-barcode"></i>
                    </div>
                    <div class="serie-details">
                        <div class="serie-number">${equipo.serie || 'Sin serie'}</div>
                        <div class="serie-label">N° Serie</div>
                    </div>
                </div>
            </td>
            <td class="text-center">
                <span class="type-badge type-${equipo.tipo || 'unknown'}">
                    <i class="fas me-1 ${equipo.tipo === 'color' ? 'fa-palette' : 'fa-circle'}"></i>
                    ${equipo.tipo || 'N/A'}
                </span>
            </td>
            <td class="text-center">
                <div class="counters-grid">
                    <div class="counter-item">
                        <div class="counter-icon"><i class="fas fa-circle"></i></div>
                        <div class="counter-value">${this.formatNumber(equipo.contador_bn || 0)}</div>
                        <div class="counter-label">B/N</div>
                    </div>
                    <div class="counter-item">
                        <div class="counter-icon color"><i class="fas fa-palette"></i></div>
                        <div class="counter-value">${this.formatNumber(equipo.contador_color || 0)}</div>
                        <div class="counter-label">Color</div>
                    </div>
                    <div class="counter-item total">
                        <div class="counter-icon"><i class="fas fa-plus"></i></div>
                        <div class="counter-value">${this.formatNumber(equipo.contador_total || 0)}</div>
                        <div class="counter-label">Total</div>
                    </div>
                </div>
            </td>
            <td class="text-center">
                <div class="date-info">
                    <div class="date-value">${equipo.fecha_formateada || 'N/A'}</div>
                    <div class="date-relative">Hace 2 horas</div>
                </div>
            </td>
            <td class="text-center">
                <span class="status-badge status-${equipo.estado || 'unknown'}">
                    <i class="fas me-1 ${this.getStatusIcon(equipo.estado)}"></i>
                    ${equipo.estado || 'N/A'}
                </span>
            </td>
            <td class="text-center">
                <div class="action-buttons">
                    <a href="/dashboard/contador/detalle/${equipo.id}" class="action-btn action-btn-primary" title="Ver detalle">
                        <i class="fas fa-eye"></i>
                    </a>
                    <a href="/dashboard/contador/historial/${equipo.id}" class="action-btn action-btn-secondary" title="Ver historial">
                        <i class="fas fa-history"></i>
                    </a>
                    <button class="action-btn action-btn-info" title="Más opciones" data-bs-toggle="dropdown">
                        <i class="fas fa-ellipsis-v"></i>
                    </button>
                </div>
            </td>
        `;

        return row;
    }

    getStatusIcon(estado) {
        const icons = {
            'procesado': 'fa-check-circle',
            'pendiente': 'fa-clock',
            'error': 'fa-exclamation-circle'
        };
        return icons[estado] || 'fa-question-circle';
    }

    bindTableEvents() {
        // Re-bindear eventos para nuevas filas
        this.tableRows.forEach(row => {
            row.addEventListener('mouseenter', () => this.highlightRow(row, true));
            row.addEventListener('mouseleave', () => this.highlightRow(row, false));
        });
    }

    updateStatsCards(stats) {
        // Actualizar tarjetas de estadísticas
        Object.keys(stats).forEach(key => {
            const element = document.querySelector(`[data-stat="${key}"]`);
            if (element) {
                const currentValue = parseInt(element.textContent) || 0;
                this.animateNumber(element, currentValue, stats[key]);
            }
        });
    }

    formatNumber(num) {
        return new Intl.NumberFormat('es-ES').format(num);
    }

    // Cleanup al destruir la instancia
    destroy() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
        }
        
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }
        
        // Remover event listeners
        document.removeEventListener('keydown', this.bindKeyboardEvents);
        document.removeEventListener('visibilitychange', this.startAutoRefresh);
    }
}

// Utilidades para el dashboard de contadores
class ContadoresUtils {
    static formatNumber(num) {
        return new Intl.NumberFormat('es-ES').format(num);
    }

    static formatDate(date, options = {}) {
        return new Intl.DateTimeFormat('es-ES', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            ...options
        }).format(new Date(date));
    }

    static debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    static throttle(func, limit) {
        let inThrottle;
        return function() {
            const args = arguments;
            const context = this;
            if (!inThrottle) {
                func.apply(context, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }

    static copyToClipboard(text) {
        if (navigator.clipboard) {
            return navigator.clipboard.writeText(text);
        } else {
            // Fallback para navegadores más antiguos
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.opacity = '0';
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            return Promise.resolve();
        }
    }

    static downloadJSON(data, filename = 'contadores_data.json') {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    static generateCSV(data, headers) {
        const csvContent = [
            headers.join(','),
            ...data.map(row => headers.map(header => `"${row[header] || ''}"`).join(','))
        ].join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'contadores_export.csv';
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    static validateForm(formElement) {
        const requiredFields = formElement.querySelectorAll('[required]');
        let isValid = true;

        requiredFields.forEach(field => {
            if (!field.value.trim()) {
                field.classList.add('is-invalid');
                isValid = false;
            } else {
                field.classList.remove('is-invalid');
            }
        });

        return isValid;
    }

    static showConfirmDialog(message, onConfirm, onCancel) {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Confirmación</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p>${message}</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-primary" id="confirmBtn">Confirmar</button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        const bootstrapModal = new bootstrap.Modal(modal);
        
        modal.querySelector('#confirmBtn').addEventListener('click', () => {
            if (onConfirm) onConfirm();
            bootstrapModal.hide();
        });

        modal.addEventListener('hidden.bs.modal', () => {
            if (onCancel) onCancel();
            document.body.removeChild(modal);
        });

        bootstrapModal.show();
    }
}

// Extensiones adicionales para funcionalidades específicas
class ContadoresCharts {
    constructor(dashboard) {
        this.dashboard = dashboard;
        this.charts = {};
    }

    createCountersChart(canvasId, data) {
        const ctx = document.getElementById(canvasId);
        if (!ctx || typeof Chart === 'undefined') return;

        this.charts[canvasId] = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['B/N', 'Color'],
                datasets: [{
                    data: [data.bn || 0, data.color || 0],
                    backgroundColor: ['#6b7280', '#3b82f6'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    createTrendChart(canvasId, data) {
        const ctx = document.getElementById(canvasId);
        if (!ctx || typeof Chart === 'undefined') return;

        this.charts[canvasId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: Object.keys(data),
                datasets: [{
                    label: 'Equipos por día',
                    data: Object.values(data),
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    destroyChart(canvasId) {
        if (this.charts[canvasId]) {
            this.charts[canvasId].destroy();
            delete this.charts[canvasId];
        }
    }

    destroyAllCharts() {
        Object.keys(this.charts).forEach(chartId => {
            this.destroyChart(chartId);
        });
    }
}

// Inicialización cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', function() {
    // Verificar si estamos en la página del dashboard de contadores
    if (document.querySelector('.dashboard-container')) {
        // Inicializar dashboard de contadores
        window.contadoresDashboard = new ContadoresDashboard();
        
        // Inicializar gráficos si hay contenedores
        if (document.querySelector('canvas')) {
            window.contadoresCharts = new ContadoresCharts(window.contadoresDashboard);
        }
        
        // Exponer utilidades globalmente
        window.ContadoresUtils = ContadoresUtils;

        // Manejar eventos globales del teclado
        document.addEventListener('keydown', function(e) {
            // Ctrl/Cmd + E para exportar
            if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
                e.preventDefault();
                window.contadoresDashboard.exportData();
            }
        });

        console.log('Dashboard de contadores cargado exitosamente');
    }
});

// Manejar errores globales
window.addEventListener('error', function(e) {
    console.error('Error en contadores dashboard:', e.error);
    
    // Mostrar toast de error si el dashboard está inicializado
    if (window.contadoresDashboard) {
        window.contadoresDashboard.showToast(
            window.contadoresDashboard.createToast('Se produjo un error inesperado', 'error')
        );
    }
});

// Manejar errores de promesas no capturadas
window.addEventListener('unhandledrejection', function(e) {
    console.error('Error no capturado:', e.reason);
    
    if (window.contadoresDashboard) {
        window.contadoresDashboard.showToast(
            window.contadoresDashboard.createToast('Error de conexión', 'error')
        );
    }
});

// Exportar para uso en otros módulos si es necesario
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { 
        ContadoresDashboard, 
        ContadoresUtils, 
        ContadoresCharts 
    };
}