/** @odoo-module */

import { Component } from "@odoo/owl";

// ========== SAT MODERN FEATURES JS (Simplificado) ==========

// Funciones que se ejecutan cuando el DOM está listo
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 SAT Modern Features loading...');
    
    // Inicializar características modernas
    initModernFeatures();
    
    console.log('✨ SAT Modern Features initialized');
});

/**
 * Inicializar todas las características modernas
 */
function initModernFeatures() {
    initializeTooltips();
    setupAnimations();
    setupFilters();
    setupThemes();
    setupKeyboardShortcuts();
}

/**
 * Inicializar tooltips
 */
function initializeTooltips() {
    // Usar setTimeout para asegurar que Bootstrap esté cargado
    setTimeout(() => {
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[title]'));
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl, {
                    delay: { show: 500, hide: 100 },
                    placement: 'top'
                });
            });
        }
    }, 1000);
}

/**
 * Configurar animaciones básicas
 */
function setupAnimations() {
    // Animar entrada de filas
    setTimeout(() => {
        const rows = document.querySelectorAll('.modern-sat-table tbody tr');
        rows.forEach((row, index) => {
            row.style.opacity = '0';
            row.style.transform = 'translateY(20px)';
            
            setTimeout(() => {
                row.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                row.style.opacity = '1';
                row.style.transform = 'translateY(0)';
            }, index * 50);
        });
    }, 500);

    // Efecto hover en filas
    document.addEventListener('mouseover', function(e) {
        if (e.target.closest('.modern-sat-table tbody tr')) {
            const row = e.target.closest('tr');
            row.style.transform = 'translateX(5px)';
            row.style.boxShadow = '0 4px 15px rgba(0,0,0,0.1)';
        }
    });

    document.addEventListener('mouseout', function(e) {
        if (e.target.closest('.modern-sat-table tbody tr')) {
            const row = e.target.closest('tr');
            row.style.transform = 'translateX(0)';
            row.style.boxShadow = 'none';
        }
    });
}

/**
 * Configurar filtros básicos
 */
function setupFilters() {
    // Crear barra de búsqueda simple
    const searchContainer = createSimpleSearchBar();
    const table = document.querySelector('.modern-sat-table');
    
    if (table && table.parentElement) {
        table.parentElement.insertBefore(searchContainer, table);
    }
}

/**
 * Crear barra de búsqueda simple
 */
function createSimpleSearchBar() {
    const container = document.createElement('div');
    container.className = 'sat-search-container mb-3 p-3 bg-light rounded';
    container.innerHTML = `
        <div class="row align-items-center">
            <div class="col-md-6">
                <div class="input-group">
                    <span class="input-group-text">
                        <i class="fas fa-search"></i>
                    </span>
                    <input type="text" class="form-control" id="satGlobalSearch" 
                           placeholder="Buscar en la tabla...">
                    <button class="btn btn-outline-secondary" type="button" id="satClearSearch">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
            <div class="col-md-3">
                <select class="form-select" id="satAvailabilityFilter">
                    <option value="">Todas las disponibilidades</option>
                    <option value="disponible">Disponible</option>
                    <option value="separada">Separada</option>
                    <option value="no_disponible">No Disponible</option>
                </select>
            </div>
            <div class="col-md-3">
                <div class="d-flex gap-2">
                    <button class="btn btn-primary btn-sm" id="satApplyFilters">
                        <i class="fas fa-filter me-1"></i>Filtrar
                    </button>
                    <button class="btn btn-outline-secondary btn-sm" id="satResetFilters">
                        <i class="fas fa-undo me-1"></i>Limpiar
                    </button>
                </div>
            </div>
        </div>
        <div class="row mt-2">
            <div class="col-12">
                <small class="text-muted">
                    Mostrando <span id="satVisibleCount">0</span> de <span id="satTotalCount">0</span> registros
                </small>
            </div>
        </div>
    `;

    // Vincular eventos
    bindSimpleSearchEvents(container);
    
    return container;
}

/**
 * Vincular eventos de búsqueda simple
 */
function bindSimpleSearchEvents(container) {
    const searchInput = container.querySelector('#satGlobalSearch');
    const clearBtn = container.querySelector('#satClearSearch');
    const availabilityFilter = container.querySelector('#satAvailabilityFilter');
    const applyBtn = container.querySelector('#satApplyFilters');
    const resetBtn = container.querySelector('#satResetFilters');

    // Búsqueda en tiempo real
    searchInput.addEventListener('input', debounce(function(e) {
        performSimpleSearch(e.target.value);
    }, 300));

    // Limpiar búsqueda
    clearBtn.addEventListener('click', function() {
        searchInput.value = '';
        performSimpleSearch('');
    });

    // Aplicar filtros
    applyBtn.addEventListener('click', function() {
        applySimpleFilters();
    });

    // Resetear filtros
    resetBtn.addEventListener('click', function() {
        searchInput.value = '';
        availabilityFilter.value = '';
        showAllRows();
        updateRowCounts();
    });

    // Actualizar contadores inicial
    updateRowCounts();
}

/**
 * Realizar búsqueda simple
 */
function performSimpleSearch(searchTerm) {
    const rows = document.querySelectorAll('.modern-sat-table tbody tr');
    const term = searchTerm.toLowerCase();
    let visibleCount = 0;

    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        const matches = text.includes(term);
        
        if (matches || !term) {
            row.style.display = '';
            visibleCount++;
            highlightText(row, term);
        } else {
            row.style.display = 'none';
            removeHighlight(row);
        }
    });

    updateVisibleCount(visibleCount);
}

/**
 * Aplicar filtros simples
 */
function applySimpleFilters() {
    const searchTerm = document.querySelector('#satGlobalSearch').value.toLowerCase();
    const availability = document.querySelector('#satAvailabilityFilter').value;
    const rows = document.querySelectorAll('.modern-sat-table tbody tr');
    let visibleCount = 0;

    rows.forEach(row => {
        let showRow = true;

        // Filtro de búsqueda
        if (searchTerm) {
            const text = row.textContent.toLowerCase();
            if (!text.includes(searchTerm)) {
                showRow = false;
            }
        }

        // Filtro de disponibilidad
        if (availability) {
            const availabilityBadge = row.querySelector('.availability-badge-modern');
            if (availabilityBadge) {
                const rowAvailability = availabilityBadge.textContent.toLowerCase();
                if (!rowAvailability.includes(availability)) {
                    showRow = false;
                }
            }
        }

        if (showRow) {
            row.style.display = '';
            visibleCount++;
        } else {
            row.style.display = 'none';
        }
    });

    updateVisibleCount(visibleCount);
    showNotification(`Filtros aplicados. Mostrando ${visibleCount} registros.`, 'success');
}

/**
 * Mostrar todas las filas
 */
function showAllRows() {
    const rows = document.querySelectorAll('.modern-sat-table tbody tr');
    rows.forEach(row => {
        row.style.display = '';
        removeHighlight(row);
    });
}

/**
 * Resaltar texto
 */
function highlightText(row, term) {
    if (!term) return;
    
    removeHighlight(row);
    
    const textNodes = getTextNodes(row);
    textNodes.forEach(node => {
        if (node.textContent.toLowerCase().includes(term)) {
            const parent = node.parentNode;
            const regex = new RegExp(`(${escapeRegExp(term)})`, 'gi');
            const highlighted = node.textContent.replace(regex, '<mark style="background: yellow;">$1</mark>');
            
            const wrapper = document.createElement('span');
            wrapper.innerHTML = highlighted;
            parent.replaceChild(wrapper, node);
        }
    });
}

/**
 * Remover resaltado
 */
function removeHighlight(row) {
    const marks = row.querySelectorAll('mark');
    marks.forEach(mark => {
        const parent = mark.parentNode;
        parent.replaceChild(document.createTextNode(mark.textContent), mark);
        parent.normalize();
    });
}

/**
 * Obtener nodos de texto
 */
function getTextNodes(element) {
    const textNodes = [];
    const walker = document.createTreeWalker(
        element,
        NodeFilter.SHOW_TEXT,
        null,
        false
    );
    
    let node;
    while (node = walker.nextNode()) {
        if (node.textContent.trim()) {
            textNodes.push(node);
        }
    }
    
    return textNodes;
}

/**
 * Actualizar contadores de filas
 */
function updateRowCounts() {
    const totalRows = document.querySelectorAll('.modern-sat-table tbody tr').length;
    const visibleRows = document.querySelectorAll('.modern-sat-table tbody tr:not([style*="display: none"])').length;
    
    const totalCount = document.querySelector('#satTotalCount');
    const visibleCount = document.querySelector('#satVisibleCount');
    
    if (totalCount) totalCount.textContent = totalRows;
    if (visibleCount) visibleCount.textContent = visibleRows;
}

/**
 * Actualizar contador visible
 */
function updateVisibleCount(count) {
    const visibleCount = document.querySelector('#satVisibleCount');
    if (visibleCount) visibleCount.textContent = count;
}

/**
 * Configurar temas básicos
 */
function setupThemes() {
    // Crear selector de tema simple
    const themeSelector = document.createElement('div');
    themeSelector.className = 'sat-theme-selector position-fixed top-0 end-0 m-3';
    themeSelector.style.zIndex = '1000';
    themeSelector.innerHTML = `
        <div class="dropdown">
            <button class="btn btn-outline-secondary btn-sm rounded-circle" type="button" data-bs-toggle="dropdown">
                <i class="fas fa-palette"></i>
            </button>
            <ul class="dropdown-menu dropdown-menu-end">
                <li><h6 class="dropdown-header">Tema</h6></li>
                <li><a class="dropdown-item theme-option" data-theme="light"><i class="fas fa-sun me-2"></i>Claro</a></li>
                <li><a class="dropdown-item theme-option" data-theme="dark"><i class="fas fa-moon me-2"></i>Oscuro</a></li>
            </ul>
        </div>
    `;
    
    document.body.appendChild(themeSelector);
    
    // Eventos de tema
    themeSelector.addEventListener('click', function(e) {
        if (e.target.closest('.theme-option')) {
            const theme = e.target.closest('.theme-option').dataset.theme;
            applyTheme(theme);
        }
    });
}

/**
 * Aplicar tema
 */
function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('sat-theme', theme);
    showNotification(`Tema ${theme} aplicado`, 'info');
}

/**
 * Configurar atajos de teclado básicos
 */
function setupKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Ctrl+F para búsqueda
        if (e.ctrlKey && e.key === 'f') {
            e.preventDefault();
            const searchInput = document.querySelector('#satGlobalSearch');
            if (searchInput) {
                searchInput.focus();
            }
        }
        
        // Escape para limpiar filtros
        if (e.key === 'Escape') {
            const resetBtn = document.querySelector('#satResetFilters');
            if (resetBtn) {
                resetBtn.click();
            }
        }
    });
}

/**
 * Mostrar notificación simple
 */
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 1060; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
    `;
    
    document.body.appendChild(notification);
    
    // Auto-remover después de 4 segundos
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 4000);
}

/**
 * Función debounce
 */
function debounce(func, wait) {
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

/**
 * Escapar regex
 */
function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Aplicar tema guardado al cargar
const savedTheme = localStorage.getItem('sat-theme');
if (savedTheme) {
    document.documentElement.setAttribute('data-theme', savedTheme);
}