// ========== SAT MODERN FILTERS JS ==========

odoo.define('sat.modern_filters', function (require) {
    'use strict';

    /**
     * Clase para manejar filtros avanzados
     */
    class SatModernFilters {
        
        constructor() {
            this.activeFilters = new Map();
            this.originalData = [];
            this.filteredData = [];
            this.init();
        }

        /**
         * Inicializar filtros
         */
        init() {
            this.setupAdvancedSearch();
            this.setupDateRangeFilter();
            this.setupMultiSelectFilters();
            this.setupSortingOptions();
            this.setupExportOptions();
            this.setupKeyboardShortcuts();
        }

        /**
         * Configurar búsqueda avanzada
         */
        setupAdvancedSearch() {
            const searchContainer = this.createAdvancedSearchContainer();
            const tableContainer = document.querySelector('.modern-sat-table')?.parentElement;
            
            if (tableContainer) {
                tableContainer.insertBefore(searchContainer, tableContainer.firstChild);
                this.bindAdvancedSearchEvents(searchContainer);
            }
        }

        /**
         * Crear contenedor de búsqueda avanzada
         */
        createAdvancedSearchContainer() {
            const container = document.createElement('div');
            container.className = 'advanced-search-container mb-4 p-4 bg-gradient rounded-4 shadow-sm';
            container.style.background = 'linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)';
            
            container.innerHTML = `
                <div class="row g-3">
                    <div class="col-md-4">
                        <label class="form-label fw-semibold">
                            <i class="fas fa-search me-1 text-primary"></i>
                            Búsqueda General
                        </label>
                        <div class="input-group">
                            <input type="text" class="form-control" id="globalSearch" 
                                   placeholder="Buscar en todos los campos...">
                            <button class="btn btn-outline-secondary" type="button" id="clearSearch">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                    
                    <div class="col-md-2">
                        <label class="form-label fw-semibold">
                            <i class="fas fa-filter me-1 text-success"></i>
                            Disponibilidad
                        </label>
                        <select class="form-select" id="availabilityFilter">
                            <option value="">Todas</option>
                            <option value="disponible">Disponible</option>
                            <option value="separada">Separada</option>
                            <option value="no_disponible">No Disponible</option>
                        </select>
                    </div>
                    
                    <div class="col-md-2">
                        <label class="form-label fw-semibold">
                            <i class="fas fa-chart-line me-1 text-info"></i>
                            Estado Ventas
                        </label>
                        <select class="form-select" id="salesStatusFilter">
                            <option value="">Todos</option>
                            <option value="sin_revisar">Sin Revisar</option>
                            <option value="en_revision">En Revisión</option>
                            <option value="finalizado">Finalizado</option>
                            <option value="entregada">Entregada</option>
                        </select>
                    </div>
                    
                    <div class="col-md-2">
                        <label class="form-label fw-semibold">
                            <i class="fas fa-calendar me-1 text-warning"></i>
                            Rango de Fecha
                        </label>
                        <input type="date" class="form-control" id="dateFromFilter">
                    </div>
                    
                    <div class="col-md-2">
                        <label class="form-label fw-semibold">&nbsp;</label>
                        <input type="date" class="form-control" id="dateToFilter">
                    </div>
                </div>
                
                <div class="row g-3 mt-2">
                    <div class="col-md-3">
                        <label class="form-label fw-semibold">
                            <i class="fas fa-industry me-1 text-purple"></i>
                            Tipo de Máquina
                        </label>
                        <select class="form-select" id="machineTypeFilter">
                            <option value="">Todos los tipos</option>
                        </select>
                    </div>
                    
                    <div class="col-md-3">
                        <label class="form-label fw-semibold">
                            <i class="fas fa-tag me-1 text-secondary"></i>
                            Marca
                        </label>
                        <select class="form-select" id="brandFilter">
                            <option value="">Todas las marcas</option>
                        </select>
                    </div>
                    
                    <div class="col-md-3">
                        <label class="form-label fw-semibold">
                            <i class="fas fa-map-marker-alt me-1 text-danger"></i>
                            Ubicación
                        </label>
                        <select class="form-select" id="locationFilter">
                            <option value="">Todas las ubicaciones</option>
                        </select>
                    </div>
                    
                    <div class="col-md-3">
                        <label class="form-label fw-semibold">
                            <i class="fas fa-tools me-1 text-dark"></i>
                            Acciones
                        </label>
                        <div class="d-grid">
                            <div class="btn-group" role="group">
                                <button type="button" class="btn btn-primary btn-sm" id="applyFilters">
                                    <i class="fas fa-filter me-1"></i>Aplicar
                                </button>
                                <button type="button" class="btn btn-outline-secondary btn-sm" id="resetFilters">
                                    <i class="fas fa-undo me-1"></i>Limpiar
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="row mt-3">
                    <div class="col-12">
                        <div class="d-flex justify-content-between align-items-center">
                            <div class="filter-status">
                                <span class="badge bg-info me-2">
                                    <i class="fas fa-list me-1"></i>
                                    Total: <span id="totalRecords">0</span>
                                </span>
                                <span class="badge bg-success me-2">
                                    <i class="fas fa-eye me-1"></i>
                                    Mostrando: <span id="visibleRecords">0</span>
                                </span>
                                <span class="badge bg-warning" id="activeFiltersCount" style="display: none;">
                                    <i class="fas fa-filter me-1"></i>
                                    Filtros activos: <span>0</span>
                                </span>
                            </div>
                            
                            <div class="quick-actions">
                                <button class="btn btn-outline-success btn-sm me-1" id="exportFiltered">
                                    <i class="fas fa-download me-1"></i>Exportar
                                </button>
                                <button class="btn btn-outline-info btn-sm" id="saveFilters">
                                    <i class="fas fa-save me-1"></i>Guardar Filtros
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            return container;
        }

        /**
         * Vincular eventos de búsqueda avanzada
         */
        bindAdvancedSearchEvents(container) {
            // Búsqueda global con debounce
            const globalSearch = container.querySelector('#globalSearch');
            globalSearch.addEventListener('input', this.debounce((e) => {
                this.applyGlobalSearch(e.target.value);
            }, 300));

            // Limpiar búsqueda
            container.querySelector('#clearSearch').addEventListener('click', () => {
                globalSearch.value = '';
                this.applyGlobalSearch('');
            });

            // Filtros de select
            const selectFilters = container.querySelectorAll('select[id$="Filter"]');
            selectFilters.forEach(select => {
                select.addEventListener('change', () => {
                    this.updateActiveFilters();
                });
            });

            // Filtros de fecha
            const dateFilters = container.querySelectorAll('input[type="date"]');
            dateFilters.forEach(input => {
                input.addEventListener('change', () => {
                    this.updateActiveFilters();
                });
            });

            // Botones de acción
            container.querySelector('#applyFilters').addEventListener('click', () => {
                this.applyAllFilters();
            });

            container.querySelector('#resetFilters').addEventListener('click', () => {
                this.resetAllFilters();
            });

            container.querySelector('#exportFiltered').addEventListener('click', () => {
                this.exportFilteredData();
            });

            container.querySelector('#saveFilters').addEventListener('click', () => {
                this.saveCurrentFilters();
            });

            // Poblar opciones de filtros dinámicamente
            this.populateFilterOptions();
        }

        /**
         * Poblar opciones de filtros dinámicamente
         */
        populateFilterOptions() {
            const rows = document.querySelectorAll('.modern-sat-table tbody tr');
            const machineTypes = new Set();
            const brands = new Set();
            const locations = new Set();

            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length >= 3) {
                    const machineType = cells[1]?.textContent?.trim();
                    const brand = cells[2]?.textContent?.trim();
                    const location = cells[5]?.textContent?.trim(); // Ajustar índice según estructura

                    if (machineType) machineTypes.add(machineType);
                    if (brand) brands.add(brand);
                    if (location) locations.add(location);
                }
            });

            // Poblar select de tipos de máquina
            const machineTypeSelect = document.querySelector('#machineTypeFilter');
            if (machineTypeSelect) {
                machineTypes.forEach(type => {
                    const option = document.createElement('option');
                    option.value = type;
                    option.textContent = type;
                    machineTypeSelect.appendChild(option);
                });
            }

            // Poblar select de marcas
            const brandSelect = document.querySelector('#brandFilter');
            if (brandSelect) {
                brands.forEach(brand => {
                    const option = document.createElement('option');
                    option.value = brand;
                    option.textContent = brand;
                    brandSelect.appendChild(option);
                });
            }

            // Poblar select de ubicaciones
            const locationSelect = document.querySelector('#locationFilter');
            if (locationSelect) {
                locations.forEach(location => {
                    const option = document.createElement('option');
                    option.value = location;
                    option.textContent = location;
                    locationSelect.appendChild(option);
                });
            }

            this.updateRecordCounts();
        }

        /**
         * Aplicar búsqueda global
         */
        applyGlobalSearch(searchTerm) {
            const rows = document.querySelectorAll('.modern-sat-table tbody tr');
            const term = searchTerm.toLowerCase();
            let visibleCount = 0;

            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                const matches = text.includes(term);
                
                if (matches || !term) {
                    row.style.display = '';
                    visibleCount++;
                    this.highlightSearchTerm(row, term);
                } else {
                    row.style.display = 'none';
                    this.removeHighlights(row);
                }
            });

            this.updateVisibleCount(visibleCount);
        }

        /**
         * Actualizar filtros activos
         */
        updateActiveFilters() {
            this.activeFilters.clear();
            
            const filters = {
                availability: document.querySelector('#availabilityFilter')?.value,
                salesStatus: document.querySelector('#salesStatusFilter')?.value,
                machineType: document.querySelector('#machineTypeFilter')?.value,
                brand: document.querySelector('#brandFilter')?.value,
                location: document.querySelector('#locationFilter')?.value,
                dateFrom: document.querySelector('#dateFromFilter')?.value,
                dateTo: document.querySelector('#dateToFilter')?.value
            };

            Object.entries(filters).forEach(([key, value]) => {
                if (value) {
                    this.activeFilters.set(key, value);
                }
            });

            this.updateActiveFiltersDisplay();
        }

        /**
         * Aplicar todos los filtros
         */
        applyAllFilters() {
            const rows = document.querySelectorAll('.modern-sat-table tbody tr');
            let visibleCount = 0;

            rows.forEach(row => {
                if (this.rowMatchesFilters(row)) {
                    row.style.display = '';
                    row.classList.add('animate__animated', 'animate__fadeIn');
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            this.updateVisibleCount(visibleCount);
            this.showFilterNotification(`Filtros aplicados. Mostrando ${visibleCount} registros.`, 'success');
        }

        /**
         * Verificar si una fila coincide con los filtros
         */
        rowMatchesFilters(row) {
            const cells = row.querySelectorAll('td');
            
            // Filtro de disponibilidad
            if (this.activeFilters.has('availability')) {
                const availabilityBadge = row.querySelector('.availability-badge-modern');
                const availability = availabilityBadge?.textContent?.toLowerCase();
                if (!availability?.includes(this.activeFilters.get('availability'))) {
                    return false;
                }
            }

            // Filtro de estado de ventas
            if (this.activeFilters.has('salesStatus')) {
                const salesBadge = row.querySelector('.sales-status-modern');
                const salesStatus = salesBadge?.textContent?.toLowerCase();
                if (!salesStatus?.includes(this.activeFilters.get('salesStatus'))) {
                    return false;
                }
            }

            // Filtro de tipo de máquina
            if (this.activeFilters.has('machineType')) {
                const machineType = cells[1]?.textContent?.trim();
                if (machineType !== this.activeFilters.get('machineType')) {
                    return false;
                }
            }

            // Filtro de marca
            if (this.activeFilters.has('brand')) {
                const brand = cells[2]?.textContent?.trim();
                if (brand !== this.activeFilters.get('brand')) {
                    return false;
                }
            }

            // Filtro de ubicación
            if (this.activeFilters.has('location')) {
                const location = cells[5]?.textContent?.trim();
                if (location !== this.activeFilters.get('location')) {
                    return false;
                }
            }

            // Filtros de fecha
            if (this.activeFilters.has('dateFrom') || this.activeFilters.has('dateTo')) {
                const dateCell = row.querySelector('[widget="remaining_days"]');
                if (dateCell) {
                    const dateText = dateCell.textContent;
                    const recordDate = this.extractDateFromText(dateText);
                    
                    if (this.activeFilters.has('dateFrom')) {
                        const fromDate = new Date(this.activeFilters.get('dateFrom'));
                        if (recordDate < fromDate) return false;
                    }
                    
                    if (this.activeFilters.has('dateTo')) {
                        const toDate = new Date(this.activeFilters.get('dateTo'));
                        if (recordDate > toDate) return false;
                    }
                }
            }

            return true;
        }

        /**
         * Resetear todos los filtros
         */
        resetAllFilters() {
            // Limpiar campos
            document.querySelector('#globalSearch').value = '';
            document.querySelectorAll('select[id$="Filter"]').forEach(select => {
                select.value = '';
            });
            document.querySelectorAll('input[type="date"]').forEach(input => {
                input.value = '';
            });

            // Mostrar todas las filas
            const rows = document.querySelectorAll('.modern-sat-table tbody tr');
            rows.forEach(row => {
                row.style.display = '';
                this.removeHighlights(row);
            });

            this.activeFilters.clear();
            this.updateActiveFiltersDisplay();
            this.updateRecordCounts();
            this.showFilterNotification('Filtros limpiados. Mostrando todos los registros.', 'info');
        }

        /**
         * Configurar filtros de rango de fecha
         */
        setupDateRangeFilter() {
            // Configurar fechas predefinidas
            const dateRangeButtons = document.createElement('div');
            dateRangeButtons.className = 'date-range-buttons mt-2';
            dateRangeButtons.innerHTML = `
                <div class="btn-group btn-group-sm" role="group">
                    <button type="button" class="btn btn-outline-secondary" data-range="today">Hoy</button>
                    <button type="button" class="btn btn-outline-secondary" data-range="week">Esta Semana</button>
                    <button type="button" class="btn btn-outline-secondary" data-range="month">Este Mes</button>
                    <button type="button" class="btn btn-outline-secondary" data-range="quarter">Trimestre</button>
                </div>
            `;

            const dateFromFilter = document.querySelector('#dateFromFilter');
            if (dateFromFilter && dateFromFilter.parentElement) {
                dateFromFilter.parentElement.appendChild(dateRangeButtons);

                // Configurar eventos para rangos predefinidos
                dateRangeButtons.addEventListener('click', (e) => {
                    if (e.target.dataset.range) {
                        this.setDateRange(e.target.dataset.range);
                    }
                });
            }
        }

        /**
         * Establecer rango de fecha
         */
        setDateRange(range) {
            const today = new Date();
            let fromDate, toDate;

            switch (range) {
                case 'today':
                    fromDate = toDate = today;
                    break;
                case 'week':
                    fromDate = new Date(today.setDate(today.getDate() - 7));
                    toDate = new Date();
                    break;
                case 'month':
                    fromDate = new Date(today.getFullYear(), today.getMonth(), 1);
                    toDate = new Date();
                    break;
                case 'quarter':
                    const quarter = Math.floor(today.getMonth() / 3);
                    fromDate = new Date(today.getFullYear(), quarter * 3, 1);
                    toDate = new Date();
                    break;
            }

            document.querySelector('#dateFromFilter').value = fromDate.toISOString().split('T')[0];
            document.querySelector('#dateToFilter').value = toDate.toISOString().split('T')[0];
            
            this.updateActiveFilters();
        }

        /**
         * Configurar opciones de ordenamiento
         */
        setupSortingOptions() {
            const sortingContainer = document.createElement('div');
            sortingContainer.className = 'sorting-options mb-3 p-3 bg-light rounded-3';
            sortingContainer.innerHTML = `
                <div class="row align-items-center">
                    <div class="col-md-3">
                        <label class="form-label fw-semibold mb-0">
                            <i class="fas fa-sort me-1"></i>Ordenar por:
                        </label>
                    </div>
                    <div class="col-md-4">
                        <select class="form-select form-select-sm" id="sortField">
                            <option value="name">Nombre</option>
                            <option value="client">Cliente</option>
                            <option value="type">Tipo</option>
                            <option value="brand">Marca</option>
                            <option value="date">Fecha Ingreso</option>
                            <option value="counter">Contador</option>
                        </select>
                    </div>
                    <div class="col-md-3">
                        <select class="form-select form-select-sm" id="sortDirection">
                            <option value="asc">Ascendente</option>
                            <option value="desc">Descendente</option>
                        </select>
                    </div>
                    <div class="col-md-2">
                        <button class="btn btn-primary btn-sm w-100" id="applySorting">
                            <i class="fas fa-sort me-1"></i>Aplicar
                        </button>
                    </div>
                </div>
            `;

            const searchContainer = document.querySelector('.advanced-search-container');
            if (searchContainer && searchContainer.parentElement) {
                searchContainer.parentElement.insertBefore(sortingContainer, searchContainer.nextSibling);
                this.bindSortingEvents(sortingContainer);
            }
        }

        /**
         * Vincular eventos de ordenamiento
         */
        bindSortingEvents(container) {
            container.querySelector('#applySorting').addEventListener('click', () => {
                const field = container.querySelector('#sortField').value;
                const direction = container.querySelector('#sortDirection').value;
                this.applySorting(field, direction);
            });
        }

        /**
         * Aplicar ordenamiento
         */
        applySorting(field, direction) {
            const tbody = document.querySelector('.modern-sat-table tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));

            rows.sort((a, b) => {
                let aValue, bValue;

                switch (field) {
                    case 'name':
                        aValue = a.querySelector('.machine-name-modern')?.textContent || '';
                        bValue = b.querySelector('.machine-name-modern')?.textContent || '';
                        break;
                    case 'client':
                        aValue = a.querySelector('.client-info')?.textContent || '';
                        bValue = b.querySelector('.client-info')?.textContent || '';
                        break;
                    case 'counter':
                        aValue = parseInt(a.querySelector('.counter-modern')?.textContent?.replace(/\D/g, '') || '0');
                        bValue = parseInt(b.querySelector('.counter-modern')?.textContent?.replace(/\D/g, '') || '0');
                        break;
                    default:
                        aValue = a.cells[0]?.textContent || '';
                        bValue = b.cells[0]?.textContent || '';
                }

                if (typeof aValue === 'string') {
                    aValue = aValue.toLowerCase();
                    bValue = bValue.toLowerCase();
                }

                if (direction === 'desc') {
                    return aValue < bValue ? 1 : (aValue > bValue ? -1 : 0);
                } else {
                    return aValue > bValue ? 1 : (aValue < bValue ? -1 : 0);
                }
            });

            // Reordenar filas en el DOM
            rows.forEach(row => {
                tbody.appendChild(row);
            });

            this.showFilterNotification(`Tabla ordenada por ${field} ${direction === 'desc' ? 'descendente' : 'ascendente'}`, 'success');
        }

        /**
         * Configurar opciones de exportación
         */
        setupExportOptions() {
            // Ya implementado en el HTML del contenedor
        }

        /**
         * Exportar datos filtrados
         */
        exportFilteredData() {
            const visibleRows = document.querySelectorAll('.modern-sat-table tbody tr:not([style*="display: none"])');
            const headers = Array.from(document.querySelectorAll('.modern-sat-table thead th')).map(th => th.textContent.trim());
            
            let csvContent = headers.join(',') + '\n';
            
            visibleRows.forEach(row => {
                const cells = Array.from(row.querySelectorAll('td')).map(cell => {
                    return '"' + cell.textContent.trim().replace(/"/g, '""') + '"';
                });
                csvContent += cells.join(',') + '\n';
            });

            this.downloadCSV(csvContent, 'sat_filtered_data.csv');
            this.showFilterNotification('Datos exportados exitosamente', 'success');
        }

        /**
         * Descargar CSV
         */
        downloadCSV(content, filename) {
            const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            
            if (link.download !== undefined) {
                const url = URL.createObjectURL(blob);
                link.setAttribute('href', url);
                link.setAttribute('download', filename);
                link.style.visibility = 'hidden';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }
        }

        /**
         * Guardar filtros actuales
         */
        saveCurrentFilters() {
            const filterData = {
                activeFilters: Object.fromEntries(this.activeFilters),
                globalSearch: document.querySelector('#globalSearch')?.value || '',
                timestamp: new Date().toISOString()
            };

            localStorage.setItem('sat_saved_filters', JSON.stringify(filterData));
            this.showFilterNotification('Filtros guardados exitosamente', 'success');
        }

        /**
         * Cargar filtros guardados
         */
        loadSavedFilters() {
            const savedData = localStorage.getItem('sat_saved_filters');
            if (savedData) {
                try {
                    const filterData = JSON.parse(savedData);
                    
                    // Restaurar filtros
                    Object.entries(filterData.activeFilters).forEach(([key, value]) => {
                        const element = document.querySelector(`#${key}Filter`);
                        if (element) element.value = value;
                    });

                    // Restaurar búsqueda global
                    const globalSearch = document.querySelector('#globalSearch');
                    if (globalSearch) globalSearch.value = filterData.globalSearch;

                    this.updateActiveFilters();
                    this.applyAllFilters();
                    
                    this.showFilterNotification('Filtros cargados exitosamente', 'info');
                } catch (e) {
                    console.error('Error loading saved filters:', e);
                }
            }
        }

        /**
         * Configurar atajos de teclado
         */
        setupKeyboardShortcuts() {
            document.addEventListener('keydown', (e) => {
                // Ctrl+F para enfocar búsqueda
                if (e.ctrlKey && e.key === 'f') {
                    e.preventDefault();
                    document.querySelector('#globalSearch')?.focus();
                }

                // Ctrl+R para resetear filtros
                if (e.ctrlKey && e.key === 'r') {
                    e.preventDefault();
                    this.resetAllFilters();
                }

                // Ctrl+S para guardar filtros
                if (e.ctrlKey && e.key === 's') {
                    e.preventDefault();
                    this.saveCurrentFilters();
                }

                // Ctrl+E para exportar
                if (e.ctrlKey && e.key === 'e') {
                    e.preventDefault();
                    this.exportFilteredData();
                }
            });
        }

        // Métodos auxiliares

        /**
         * Resaltar término de búsqueda
         */
        highlightSearchTerm(row, term) {
            if (!term) return;
            
            const walker = document.createTreeWalker(
                row,
                NodeFilter.SHOW_TEXT,
                null,
                false
            );
            
            const textNodes = [];
            let node;
            
            while (node = walker.nextNode()) {
                if (node.nodeValue.toLowerCase().includes(term)) {
                    textNodes.push(node);
                }
            }
            
            textNodes.forEach(textNode => {
                const parent = textNode.parentNode;
                if (parent.tagName !== 'MARK') {
                    const regex = new RegExp(`(${this.escapeRegExp(term)})`, 'gi');
                    const highlightedHTML = textNode.nodeValue.replace(regex, '<mark class="bg-warning bg-opacity-75">$1</mark>');
                    
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = highlightedHTML;
                    
                    while (tempDiv.firstChild) {
                        parent.insertBefore(tempDiv.firstChild, textNode);
                    }
                    parent.removeChild(textNode);
                }
            });
        }

        /**
         * Remover resaltados
         */
        removeHighlights(row) {
            const marks = row.querySelectorAll('mark');
            marks.forEach(mark => {
                mark.outerHTML = mark.textContent;
            });
        }

        /**
         * Actualizar contadores
         */
        updateRecordCounts() {
            const totalRows = document.querySelectorAll('.modern-sat-table tbody tr').length;
            const visibleRows = document.querySelectorAll('.modern-sat-table tbody tr:not([style*="display: none"])').length;
            
            document.querySelector('#totalRecords').textContent = totalRows;
            document.querySelector('#visibleRecords').textContent = visibleRows;
        }

        /**
         * Actualizar contador visible
         */
        updateVisibleCount(count) {
            document.querySelector('#visibleRecords').textContent = count;
        }

        /**
         * Actualizar display de filtros activos
         */
        updateActiveFiltersDisplay() {
            const activeCount = this.activeFilters.size;
            const badge = document.querySelector('#activeFiltersCount');
            
            if (activeCount > 0) {
                badge.style.display = 'inline-block';
                badge.querySelector('span').textContent = activeCount;
            } else {
                badge.style.display = 'none';
            }
        }

        /**
         * Mostrar notificación de filtro
         */
        showFilterNotification(message, type = 'info') {
            const notification = document.createElement('div');
            notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
            notification.style.cssText = 'top: 20px; right: 20px; z-index: 1060; min-width: 300px;';
            notification.innerHTML = `
                <i class="fas fa-filter me-2"></i>${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;
            
            document.body.appendChild(notification);
            
            setTimeout(() => {
                if (notification.parentElement) {
                    notification.remove();
                }
            }, 4000);
        }

        /**
         * Extraer fecha del texto
         */
        extractDateFromText(text) {
            const dateMatch = text.match(/\d{4}-\d{2}-\d{2}/);
            return dateMatch ? new Date(dateMatch[0]) : new Date();
        }

        /**
         * Escapar regex
         */
        escapeRegExp(string) {
            return string.replace(/[.*+?^${}()|[\]\\]/g, '\\            // Poblar select de ubicaciones
            const locationSelect = document.querySelector('#locationFilter');
            if (locationSelect) {
                locations.forEach(location => {
                    const');
        }

        /**
         * Debounce function
         */
        debounce(func, wait) {
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
    }

        /**
         * Configurar multi-select filters
         */
        setupMultiSelectFilters() {
            // Crear filtros multi-select para casos avanzados
            const multiSelectContainer = document.createElement('div');
            multiSelectContainer.className = 'multi-select-filters mt-3 p-3 bg-light bg-opacity-50 rounded-3';
            multiSelectContainer.innerHTML = `
                <div class="row">
                    <div class="col-12">
                        <h6 class="mb-3">
                            <i class="fas fa-layer-group me-2 text-primary"></i>
                            Filtros Avanzados Multi-Selección
                        </h6>
                    </div>
                </div>
                <div class="row g-3">
                    <div class="col-md-3">
                        <label class="form-label fw-semibold">Estados de Disponibilidad</label>
                        <div class="form-check-container">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" value="disponible" id="multiAvail1">
                                <label class="form-check-label" for="multiAvail1">Disponible</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" value="separada" id="multiAvail2">
                                <label class="form-check-label" for="multiAvail2">Separada</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" value="no_disponible" id="multiAvail3">
                                <label class="form-check-label" for="multiAvail3">No Disponible</label>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-3">
                        <label class="form-label fw-semibold">Estados de Ventas</label>
                        <div class="form-check-container">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" value="sin_revisar" id="multiSales1">
                                <label class="form-check-label" for="multiSales1">Sin Revisar</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" value="en_revision" id="multiSales2">
                                <label class="form-check-label" for="multiSales2">En Revisión</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" value="finalizado" id="multiSales3">
                                <label class="form-check-label" for="multiSales3">Finalizado</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" value="entregada" id="multiSales4">
                                <label class="form-check-label" for="multiSales4">Entregada</label>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-3">
                        <label class="form-label fw-semibold">Condiciones Especiales</label>
                        <div class="form-check-container">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" value="con_alertas" id="specialCond1">
                                <label class="form-check-label" for="specialCond1">Con Alertas</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" value="sin_precio" id="specialCond2">
                                <label class="form-check-label" for="specialCond2">Sin Precio</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" value="recientes" id="specialCond3">
                                <label class="form-check-label" for="specialCond3">Ingresadas Hoy</label>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-3">
                        <label class="form-label fw-semibold">Rango de Contador</label>
                        <div class="row g-2">
                            <div class="col-6">
                                <input type="number" class="form-control form-control-sm" 
                                       placeholder="Desde" id="counterFrom">
                            </div>
                            <div class="col-6">
                                <input type="number" class="form-control form-control-sm" 
                                       placeholder="Hasta" id="counterTo">
                            </div>
                        </div>
                        <div class="mt-2">
                            <button class="btn btn-outline-primary btn-sm w-100" id="applyCounterFilter">
                                <i class="fas fa-calculator me-1"></i>Aplicar Rango
                            </button>
                        </div>
                    </div>
                </div>
                
                <div class="row mt-3">
                    <div class="col-12">
                        <div class="d-flex justify-content-between">
                            <button class="btn btn-success btn-sm" id="applyMultiFilters">
                                <i class="fas fa-check me-1"></i>Aplicar Filtros Múltiples
                            </button>
                            <button class="btn btn-outline-warning btn-sm" id="clearMultiFilters">
                                <i class="fas fa-eraser me-1"></i>Limpiar Selección
                            </button>
                        </div>
                    </div>
                </div>
            `;

            const searchContainer = document.querySelector('.advanced-search-container');
            if (searchContainer && searchContainer.parentElement) {
                searchContainer.parentElement.insertBefore(multiSelectContainer, searchContainer.nextSibling);
                this.bindMultiSelectEvents(multiSelectContainer);
            }
        }

        /**
         * Vincular eventos de multi-select
         */
        bindMultiSelectEvents(container) {
            // Aplicar filtros múltiples
            container.querySelector('#applyMultiFilters').addEventListener('click', () => {
                this.applyMultiSelectFilters();
            });

            // Limpiar filtros múltiples
            container.querySelector('#clearMultiFilters').addEventListener('click', () => {
                const checkboxes = container.querySelectorAll('input[type="checkbox"]');
                checkboxes.forEach(cb => cb.checked = false);
                
                container.querySelector('#counterFrom').value = '';
                container.querySelector('#counterTo').value = '';
                
                this.resetAllFilters();
            });

            // Aplicar filtro de contador
            container.querySelector('#applyCounterFilter').addEventListener('click', () => {
                this.applyCounterRangeFilter();
            });
        }

        /**
         * Aplicar filtros multi-select
         */
        applyMultiSelectFilters() {
            const rows = document.querySelectorAll('.modern-sat-table tbody tr');
            let visibleCount = 0;

            const selectedAvailability = this.getSelectedCheckboxValues('input[id^="multiAvail"]:checked');
            const selectedSalesStatus = this.getSelectedCheckboxValues('input[id^="multiSales"]:checked');
            const selectedSpecialConditions = this.getSelectedCheckboxValues('input[id^="specialCond"]:checked');

            rows.forEach(row => {
                if (this.rowMatchesMultiFilters(row, selectedAvailability, selectedSalesStatus, selectedSpecialConditions)) {
                    row.style.display = '';
                    row.classList.add('animate__animated', 'animate__fadeIn');
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            this.updateVisibleCount(visibleCount);
            this.showFilterNotification(`Filtros múltiples aplicados. Mostrando ${visibleCount} registros.`, 'success');
        }

        /**
         * Verificar si fila coincide con filtros múltiples
         */
        rowMatchesMultiFilters(row, availability, salesStatus, specialConditions) {
            // Verificar disponibilidad
            if (availability.length > 0) {
                const availabilityBadge = row.querySelector('.availability-badge-modern');
                const rowAvailability = availabilityBadge?.textContent?.toLowerCase();
                const matches = availability.some(status => rowAvailability?.includes(status));
                if (!matches) return false;
            }

            // Verificar estado de ventas
            if (salesStatus.length > 0) {
                const salesBadge = row.querySelector('.sales-status-modern');
                const rowSalesStatus = salesBadge?.textContent?.toLowerCase();
                const matches = salesStatus.some(status => rowSalesStatus?.includes(status));
                if (!matches) return false;
            }

            // Verificar condiciones especiales
            if (specialConditions.length > 0) {
                for (let condition of specialConditions) {
                    switch (condition) {
                        case 'con_alertas':
                            if (!row.querySelector('.alert-modern')) return false;
                            break;
                        case 'sin_precio':
                            const priceField = row.querySelector('.price-modern');
                            if (priceField && priceField.textContent.trim() !== '') return false;
                            break;
                        case 'recientes':
                            const dateField = row.querySelector('[widget="remaining_days"]');
                            if (dateField) {
                                const today = new Date().toDateString();
                                const recordDate = this.extractDateFromText(dateField.textContent).toDateString();
                                if (recordDate !== today) return false;
                            }
                            break;
                    }
                }
            }

            return true;
        }

        /**
         * Aplicar filtro de rango de contador
         */
        applyCounterRangeFilter() {
            const fromValue = parseInt(document.querySelector('#counterFrom').value) || 0;
            const toValue = parseInt(document.querySelector('#counterTo').value) || Infinity;
            
            const rows = document.querySelectorAll('.modern-sat-table tbody tr');
            let visibleCount = 0;

            rows.forEach(row => {
                const counterField = row.querySelector('.counter-modern');
                if (counterField) {
                    const counterValue = parseInt(counterField.textContent.replace(/\D/g, '')) || 0;
                    
                    if (counterValue >= fromValue && counterValue <= toValue) {
                        row.style.display = '';
                        visibleCount++;
                    } else {
                        row.style.display = 'none';
                    }
                }
            });

            this.updateVisibleCount(visibleCount);
            this.showFilterNotification(`Filtro de contador aplicado: ${fromValue} - ${toValue}. Mostrando ${visibleCount} registros.`, 'info');
        }

        /**
         * Obtener valores de checkboxes seleccionados
         */
        getSelectedCheckboxValues(selector) {
            return Array.from(document.querySelectorAll(selector)).map(cb => cb.value);
        }

        /**
         * Configurar filtros guardados
         */
        setupSavedFilterPresets() {
            const presetContainer = document.createElement('div');
            presetContainer.className = 'filter-presets mb-3 p-3 bg-primary bg-opacity-10 rounded-3';
            presetContainer.innerHTML = `
                <div class="row align-items-center">
                    <div class="col-md-6">
                        <h6 class="mb-0">
                            <i class="fas fa-bookmark me-2 text-primary"></i>
                            Filtros Predefinidos
                        </h6>
                    </div>
                    <div class="col-md-6">
                        <div class="btn-group btn-group-sm w-100" role="group">
                            <button type="button" class="btn btn-outline-primary preset-btn" data-preset="available">
                                Disponibles
                            </button>
                            <button type="button" class="btn btn-outline-warning preset-btn" data-preset="pending">
                                Pendientes
                            </button>
                            <button type="button" class="btn btn-outline-success preset-btn" data-preset="completed">
                                Finalizadas
                            </button>
                            <button type="button" class="btn btn-outline-danger preset-btn" data-preset="alerts">
                                Con Alertas
                            </button>
                        </div>
                    </div>
                </div>
            `;

            const searchContainer = document.querySelector('.advanced-search-container');
            if (searchContainer && searchContainer.parentElement) {
                searchContainer.parentElement.insertBefore(presetContainer, searchContainer);
                this.bindPresetEvents(presetContainer);
            }
        }

        /**
         * Vincular eventos de presets
         */
        bindPresetEvents(container) {
            container.querySelectorAll('.preset-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const preset = e.target.dataset.preset;
                    this.applyFilterPreset(preset);
                    
                    // Actualizar estado activo
                    container.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                });
            });
        }

        /**
         * Aplicar preset de filtro
         */
        applyFilterPreset(preset) {
            this.resetAllFilters();

            switch (preset) {
                case 'available':
                    document.querySelector('#availabilityFilter').value = 'disponible';
                    break;
                case 'pending':
                    document.querySelector('#salesStatusFilter').value = 'en_revision';
                    break;
                case 'completed':
                    document.querySelector('#salesStatusFilter').value = 'finalizado';
                    break;
                case 'alerts':
                    // Mostrar solo filas con alertas
                    const rows = document.querySelectorAll('.modern-sat-table tbody tr');
                    let visibleCount = 0;
                    rows.forEach(row => {
                        if (row.querySelector('.alert-modern')) {
                            row.style.display = '';
                            visibleCount++;
                        } else {
                            row.style.display = 'none';
                        }
                    });
                    this.updateVisibleCount(visibleCount);
                    this.showFilterNotification(`Preset "${preset}" aplicado. Mostrando ${visibleCount} registros.`, 'info');
                    return;
            }

            this.updateActiveFilters();
            this.applyAllFilters();
        }

        /**
         * Configurar auto-guardado de filtros
         */
        setupAutoSave() {
            // Auto-guardar filtros cada 30 segundos si hay cambios
            setInterval(() => {
                if (this.activeFilters.size > 0) {
                    const autoSaveData = {
                        activeFilters: Object.fromEntries(this.activeFilters),
                        globalSearch: document.querySelector('#globalSearch')?.value || '',
                        timestamp: new Date().toISOString(),
                        autoSave: true
                    };
                    localStorage.setItem('sat_auto_saved_filters', JSON.stringify(autoSaveData));
                }
            }, 30000);
        }

        /**
         * Cargar auto-guardado
         */
        loadAutoSavedFilters() {
            const autoSavedData = localStorage.getItem('sat_auto_saved_filters');
            if (autoSavedData) {
                try {
                    const filterData = JSON.parse(autoSavedData);
                    const lastSave = new Date(filterData.timestamp);
                    const now = new Date();
                    const hoursDiff = (now - lastSave) / (1000 * 60 * 60);

                    // Solo cargar si es menor a 24 horas
                    if (hoursDiff < 24) {
                        this.showRestoreNotification(filterData);
                    }
                } catch (e) {
                    console.error('Error loading auto-saved filters:', e);
                }
            }
        }

        /**
         * Mostrar notificación de restauración
         */
        showRestoreNotification(filterData) {
            const notification = document.createElement('div');
            notification.className = 'alert alert-info alert-dismissible fade show position-fixed';
            notification.style.cssText = 'top: 20px; left: 50%; transform: translateX(-50%); z-index: 1060; min-width: 400px;';
            notification.innerHTML = `
                <div class="d-flex align-items-center">
                    <i class="fas fa-history me-2"></i>
                    <div class="flex-grow-1">
                        <strong>Filtros auto-guardados encontrados</strong><br>
                        <small>¿Deseas restaurar tus últimos filtros aplicados?</small>
                    </div>
                    <div class="btn-group btn-group-sm ms-2">
                        <button type="button" class="btn btn-primary btn-sm" onclick="this.closest('.alert').dispatchEvent(new CustomEvent('restore'))">
                            Restaurar
                        </button>
                        <button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="alert">
                            Ignorar
                        </button>
                    </div>
                </div>
            `;
            
            notification.addEventListener('restore', () => {
                this.restoreFilters(filterData);
                notification.remove();
            });
            
            document.body.appendChild(notification);
            
            // Auto-remover después de 10 segundos
            setTimeout(() => {
                if (notification.parentElement) {
                    notification.remove();
                }
            }, 10000);
        }

        /**
         * Restaurar filtros
         */
        restoreFilters(filterData) {
            // Restaurar filtros
            Object.entries(filterData.activeFilters).forEach(([key, value]) => {
                const element = document.querySelector(`#${key}Filter`);
                if (element) element.value = value;
            });

            // Restaurar búsqueda global
            const globalSearch = document.querySelector('#globalSearch');
            if (globalSearch) globalSearch.value = filterData.globalSearch;

            this.updateActiveFilters();
            this.applyAllFilters();
            
            this.showFilterNotification('Filtros restaurados exitosamente', 'success');
        }

        /**
         * Configurar estadísticas avanzadas
         */
        setupAdvancedStats() {
            const statsContainer = document.createElement('div');
            statsContainer.className = 'advanced-stats mt-3 p-3 bg-light bg-opacity-50 rounded-3';
            statsContainer.innerHTML = `
                <div class="row text-center">
                    <div class="col-md-2">
                        <div class="stat-card">
                            <div class="stat-number text-primary" id="statTotal">0</div>
                            <div class="stat-label">Total</div>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="stat-card">
                            <div class="stat-number text-success" id="statAvailable">0</div>
                            <div class="stat-label">Disponibles</div>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="stat-card">
                            <div class="stat-number text-warning" id="statSeparated">0</div>
                            <div class="stat-label">Separadas</div>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="stat-card">
                            <div class="stat-number text-danger" id="statUnavailable">0</div>
                            <div class="stat-label">No Disponibles</div>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="stat-card">
                            <div class="stat-number text-info" id="statAlerts">0</div>
                            <div class="stat-label">Con Alertas</div>
                        </div>
                    </div>
                    <div class="col-md-2">
                        <div class="stat-card">
                            <div class="stat-number text-secondary" id="statFiltered">0</div>
                            <div class="stat-label">Filtradas</div>
                        </div>
                    </div>
                </div>
            `;

            const filterContainer = document.querySelector('.advanced-search-container');
            if (filterContainer && filterContainer.parentElement) {
                filterContainer.parentElement.appendChild(statsContainer);
                this.updateAdvancedStats();
            }
        }

        /**
         * Actualizar estadísticas avanzadas
         */
        updateAdvancedStats() {
            const allRows = document.querySelectorAll('.modern-sat-table tbody tr');
            const visibleRows = document.querySelectorAll('.modern-sat-table tbody tr:not([style*="display: none"])');
            
            let available = 0, separated = 0, unavailable = 0, alerts = 0;
            
            allRows.forEach(row => {
                const availabilityBadge = row.querySelector('.availability-badge-modern');
                const alertIndicator = row.querySelector('.alert-modern');
                
                if (availabilityBadge) {
                    const status = availabilityBadge.textContent.toLowerCase();
                    if (status.includes('disponible')) available++;
                    else if (status.includes('separada')) separated++;
                    else if (status.includes('no_disponible')) unavailable++;
                }
                
                if (alertIndicator) alerts++;
            });
            
            // Actualizar estadísticas con animación
            this.animateStatNumber('statTotal', allRows.length);
            this.animateStatNumber('statAvailable', available);
            this.animateStatNumber('statSeparated', separated);
            this.animateStatNumber('statUnavailable', unavailable);
            this.animateStatNumber('statAlerts', alerts);
            this.animateStatNumber('statFiltered', visibleRows.length);
        }

        /**
         * Animar número de estadística
         */
        animateStatNumber(elementId, targetValue) {
            const element = document.getElementById(elementId);
            if (!element) return;

            const currentValue = parseInt(element.textContent) || 0;
            const increment = (targetValue - currentValue) / 30;
            let current = currentValue;

            const animation = setInterval(() => {
                current += increment;
                if ((increment > 0 && current >= targetValue) || (increment < 0 && current <= targetValue)) {
                    current = targetValue;
                    clearInterval(animation);
                }
                element.textContent = Math.floor(current);
            }, 16);
        }
    }

    // Inicializar cuando el DOM esté listo
    document.addEventListener('DOMContentLoaded', () => {
        const filters = new SatModernFilters();
        
        // Configurar características adicionales
        filters.setupSavedFilterPresets();
        filters.setupAdvancedStats();
        filters.setupAutoSave();
        filters.loadAutoSavedFilters();
        
        console.log('🔍 SAT Modern Filters initialized with advanced features');
    });

    return SatModernFilters;
});