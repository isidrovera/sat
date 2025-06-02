// ========== SAT MODERN TABLE JS ==========

odoo.define('sat.modern_table', function (require) {
    'use strict';

    const ListView = require('web.ListView');
    const ListRenderer = require('web.ListRenderer');
    const core = require('web.core');
    const QWeb = core.qweb;

    // Extender el renderer de lista para funcionalidades modernas
    const SatModernListRenderer = ListRenderer.extend({
        
        /**
         * Inicializar características modernas después del render
         */
        _renderView: function () {
            const result = this._super.apply(this, arguments);
            this._initializeModernFeatures();
            return result;
        },

        /**
         * Inicializar todas las características modernas
         */
        _initializeModernFeatures: function () {
            this._initializeTooltips();
            this._initializeAOS();
            this._addStaggerAnimation();
            this._setupDynamicCounters();
            this._setupAlertHandlers();
            this._addQuickFilters();
            this._setupThemeSelector();
            this._initializeSearch();
        },

        /**
         * Inicializar tooltips de Bootstrap
         */
        _initializeTooltips: function () {
            if (typeof bootstrap !== 'undefined') {
                const tooltipTriggerList = [].slice.call(
                    this.el.querySelectorAll('[data-bs-toggle="tooltip"]')
                );
                tooltipTriggerList.map(function (tooltipTriggerEl) {
                    return new bootstrap.Tooltip(tooltipTriggerEl, {
                        delay: { show: 500, hide: 100 },
                        placement: 'top',
                        animation: true
                    });
                });
            }
        },

        /**
         * Inicializar AOS (Animate On Scroll)
         */
        _initializeAOS: function () {
            if (typeof AOS !== 'undefined') {
                AOS.init({
                    duration: 800,
                    easing: 'ease-in-out',
                    once: true,
                    offset: 50
                });
            }
        },

        /**
         * Agregar animaciones escalonadas a las filas
         */
        _addStaggerAnimation: function () {
            const rows = this.el.querySelectorAll('tbody tr');
            rows.forEach((row, index) => {
                row.style.animationDelay = `${index * 0.05}s`;
                row.classList.add('stagger-item');
            });
        },

        /**
         * Configurar contadores dinámicos
         */
        _setupDynamicCounters: function () {
            const counters = this.el.querySelectorAll('.counter-modern');
            counters.forEach(counter => {
                this._animateCounter(counter);
            });
        },

        /**
         * Animar contador con efecto de conteo
         */
        _animateCounter: function (element) {
            const finalValue = element.textContent.replace(/[^\d]/g, '');
            if (!finalValue) return;
            
            const target = parseInt(finalValue) || 0;
            let current = 0;
            const increment = target / 60;
            const timer = setInterval(() => {
                current += increment;
                if (current >= target) {
                    current = target;
                    clearInterval(timer);
                }
                element.textContent = Math.floor(current).toLocaleString();
            }, 16);
        },

        /**
         * Configurar manejadores de alertas
         */
        _setupAlertHandlers: function () {
            const alerts = this.el.querySelectorAll('.alert-modern');
            alerts.forEach(alert => {
                alert.addEventListener('click', (e) => {
                    this._showAlertModal(e.target);
                });
            });
        },

        /**
         * Mostrar modal de alerta
         */
        _showAlertModal: function (alertElement) {
            const modal = document.createElement('div');
            modal.className = 'modal fade';
            modal.innerHTML = `
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content border-0 shadow-lg">
                        <div class="modal-header bg-gradient text-white border-0" style="background: linear-gradient(135deg, #ef4444, #dc2626);">
                            <h5 class="modal-title">
                                <i class="fas fa-exclamation-triangle me-2"></i>
                                Alerta de Máquina
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body p-4">
                            <div class="alert alert-warning border-0 bg-warning bg-opacity-10">
                                <h6 class="alert-heading">⚠️ Atención Requerida</h6>
                                <p class="mb-0">Esta máquina requiere revisión inmediata. Por favor, verifique los siguientes puntos:</p>
                            </div>
                            <ul class="list-unstyled mt-3">
                                <li class="mb-2"><i class="fas fa-check-circle text-primary me-2"></i>Estado general de la máquina</li>
                                <li class="mb-2"><i class="fas fa-tools text-warning me-2"></i>Último mantenimiento realizado</li>
                                <li class="mb-2"><i class="fas fa-user-cog text-info me-2"></i>Contactar técnico especializado</li>
                                <li class="mb-2"><i class="fas fa-clipboard-check text-success me-2"></i>Documentar hallazgos</li>
                            </ul>
                        </div>
                        <div class="modal-footer border-0 bg-light">
                            <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">
                                <i class="fas fa-times me-1"></i>Cerrar
                            </button>
                            <button type="button" class="btn btn-primary" onclick="this.closest('.modal').querySelector('[data-bs-dismiss]').click()">
                                <i class="fas fa-check me-1"></i>Marcar como Revisado
                            </button>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            
            if (typeof bootstrap !== 'undefined') {
                const bsModal = new bootstrap.Modal(modal);
                bsModal.show();
                
                modal.addEventListener('hidden.bs.modal', () => {
                    document.body.removeChild(modal);
                });
            }
        },

        /**
         * Agregar filtros rápidos
         */
        _addQuickFilters: function () {
            const existingFilters = document.querySelector('.sat-quick-filters');
            if (existingFilters) return;

            const filterContainer = document.createElement('div');
            filterContainer.className = 'sat-quick-filters mb-4 p-3 bg-light bg-opacity-50 rounded-4 backdrop-blur';
            filterContainer.innerHTML = `
                <div class="row align-items-center">
                    <div class="col-md-8">
                        <div class="d-flex flex-wrap gap-2">
                            <button class="btn btn-outline-success btn-sm rounded-pill filter-btn" data-filter="disponible">
                                <i class="fas fa-check-circle me-1"></i>Disponibles
                            </button>
                            <button class="btn btn-outline-warning btn-sm rounded-pill filter-btn" data-filter="separada">
                                <i class="fas fa-clock me-1"></i>Separadas
                            </button>
                            <button class="btn btn-outline-danger btn-sm rounded-pill filter-btn" data-filter="no_disponible">
                                <i class="fas fa-times-circle me-1"></i>No Disponibles
                            </button>
                            <button class="btn btn-outline-info btn-sm rounded-pill filter-btn" data-filter="con_alertas">
                                <i class="fas fa-exclamation-triangle me-1"></i>Con Alertas
                            </button>
                            <button class="btn btn-outline-secondary btn-sm rounded-pill" onclick="this.parentElement.parentElement.parentElement.nextElementSibling.querySelector('.search-input').focus()">
                                <i class="fas fa-search me-1"></i>Buscar
                            </button>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="stats-container d-flex justify-content-end">
                            <span class="badge bg-success me-1">Disp: <span id="availableCount">0</span></span>
                            <span class="badge bg-warning me-1">Sep: <span id="separatedCount">0</span></span>
                            <span class="badge bg-danger">Alert: <span id="alertCount">0</span></span>
                        </div>
                    </div>
                </div>
            `;

            const table = this.el.querySelector('.modern-sat-table');
            if (table && table.parentElement) {
                table.parentElement.insertBefore(filterContainer, table);
                this._setupFilterEvents(filterContainer);
                this._updateStats();
            }
        },

        /**
         * Configurar eventos de filtros
         */
        _setupFilterEvents: function (container) {
            const filterButtons = container.querySelectorAll('.filter-btn');
            filterButtons.forEach(button => {
                button.addEventListener('click', (e) => {
                    const filter = e.target.dataset.filter || e.target.closest('.filter-btn').dataset.filter;
                    this._applyFilter(filter);
                    
                    // Actualizar estado activo
                    filterButtons.forEach(btn => btn.classList.remove('active'));
                    button.classList.add('active');
                });
            });
        },

        /**
         * Aplicar filtro visual
         */
        _applyFilter: function (filter) {
            const rows = this.el.querySelectorAll('tbody tr');
            
            rows.forEach(row => {
                let show = true;
                
                switch (filter) {
                    case 'disponible':
                        show = row.querySelector('.availability-badge-modern')?.textContent.toLowerCase().includes('disponible');
                        break;
                    case 'separada':
                        show = row.querySelector('.availability-badge-modern')?.textContent.toLowerCase().includes('separada');
                        break;
                    case 'no_disponible':
                        show = row.querySelector('.availability-badge-modern')?.textContent.toLowerCase().includes('no_disponible');
                        break;
                    case 'con_alertas':
                        show = row.querySelector('.alert-modern') !== null;
                        break;
                }
                
                if (show) {
                    row.style.display = '';
                    row.classList.add('animate__fadeIn');
                } else {
                    row.style.display = 'none';
                }
            });
            
            this._updateStats();
        },

        /**
         * Actualizar estadísticas
         */
        _updateStats: function () {
            const visibleRows = this.el.querySelectorAll('tbody tr:not([style*="display: none"])');
            let available = 0, separated = 0, alerts = 0;
            
            visibleRows.forEach(row => {
                const availabilityBadge = row.querySelector('.availability-badge-modern');
                const alertIndicator = row.querySelector('.alert-modern');
                
                if (availabilityBadge) {
                    const status = availabilityBadge.textContent.toLowerCase();
                    if (status.includes('disponible')) available++;
                    else if (status.includes('separada')) separated++;
                }
                
                if (alertIndicator) alerts++;
            });
            
            const availableCount = document.getElementById('availableCount');
            const separatedCount = document.getElementById('separatedCount');
            const alertCount = document.getElementById('alertCount');
            
            if (availableCount) availableCount.textContent = available;
            if (separatedCount) separatedCount.textContent = separated;
            if (alertCount) alertCount.textContent = alerts;
        },

        /**
         * Configurar selector de tema
         */
        _setupThemeSelector: function () {
            if (document.querySelector('.sat-theme-selector')) return;

            const themeSelector = document.createElement('div');
            themeSelector.className = 'sat-theme-selector position-fixed top-0 end-0 p-3';
            themeSelector.style.zIndex = '1000';
            themeSelector.innerHTML = `
                <div class="dropdown">
                    <button class="btn btn-outline-secondary rounded-circle" type="button" data-bs-toggle="dropdown">
                        <i class="fas fa-palette"></i>
                    </button>
                    <ul class="dropdown-menu dropdown-menu-end">
                        <li><h6 class="dropdown-header">Seleccionar Tema</h6></li>
                        <li><a class="dropdown-item theme-option" data-theme="light"><i class="fas fa-sun me-2"></i>Claro</a></li>
                        <li><a class="dropdown-item theme-option" data-theme="dark"><i class="fas fa-moon me-2"></i>Oscuro</a></li>
                        <li><a class="dropdown-item theme-option" data-theme="blue"><i class="fas fa-droplet me-2 text-primary"></i>Azul</a></li>
                        <li><a class="dropdown-item theme-option" data-theme="green"><i class="fas fa-leaf me-2 text-success"></i>Verde</a></li>
                        <li><a class="dropdown-item theme-option" data-theme="purple"><i class="fas fa-gem me-2 text-purple"></i>Púrpura</a></li>
                    </ul>
                </div>
            `;
            
            document.body.appendChild(themeSelector);
            
            // Configurar eventos de tema
            const themeOptions = themeSelector.querySelectorAll('.theme-option');
            themeOptions.forEach(option => {
                option.addEventListener('click', (e) => {
                    e.preventDefault();
                    const theme = option.dataset.theme;
                    this._applyTheme(theme);
                });
            });
        },

        /**
         * Aplicar tema
         */
        _applyTheme: function (theme) {
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('sat-theme', theme);
            
            // Notificación
            this._showNotification(`Tema ${theme} aplicado`, 'success');
        },

        /**
         * Inicializar búsqueda avanzada
         */
        _initializeSearch: function () {
            const searchContainer = document.createElement('div');
            searchContainer.className = 'sat-search-container mb-3';
            searchContainer.innerHTML = `
                <div class="input-group">
                    <span class="input-group-text bg-primary text-white border-0">
                        <i class="fas fa-search"></i>
                    </span>
                    <input type="text" class="form-control search-input border-0 bg-light" 
                           placeholder="Buscar por cliente, máquina, serie..." 
                           style="border-radius: 0 0.5rem 0.5rem 0;">
                </div>
            `;
            
            const table = this.el.querySelector('.modern-sat-table');
            if (table && table.parentElement) {
                table.parentElement.insertBefore(searchContainer, table);
                
                const searchInput = searchContainer.querySelector('.search-input');
                searchInput.addEventListener('input', this._debounce((e) => {
                    this._performSearch(e.target.value);
                }, 300));
            }
        },

        /**
         * Realizar búsqueda
         */
        _performSearch: function (searchTerm) {
            const rows = this.el.querySelectorAll('tbody tr');
            const term = searchTerm.toLowerCase();
            
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                const matches = text.includes(term);
                
                row.style.display = matches ? '' : 'none';
                
                if (matches && term) {
                    this._highlightSearchTerm(row, term);
                } else {
                    this._removeHighlights(row);
                }
            });
            
            this._updateStats();
        },

        /**
         * Resaltar término de búsqueda
         */
        _highlightSearchTerm: function (row, term) {
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
                    const regex = new RegExp(`(${term})`, 'gi');
                    const highlightedHTML = textNode.nodeValue.replace(regex, '<mark class="bg-warning">$1</mark>');
                    
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = highlightedHTML;
                    
                    while (tempDiv.firstChild) {
                        parent.insertBefore(tempDiv.firstChild, textNode);
                    }
                    parent.removeChild(textNode);
                }
            });
        },

        /**
         * Remover resaltados
         */
        _removeHighlights: function (row) {
            const marks = row.querySelectorAll('mark');
            marks.forEach(mark => {
                mark.outerHTML = mark.textContent;
            });
        },

        /**
         * Función debounce para optimizar búsqueda
         */
        _debounce: function (func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        },

        /**
         * Mostrar notificación
         */
        _showNotification: function (message, type = 'info') {
            const notification = document.createElement('div');
            notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
            notification.style.cssText = 'top: 20px; right: 20px; z-index: 1060; min-width: 300px;';
            notification.innerHTML = `
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;
            
            document.body.appendChild(notification);
            
            setTimeout(() => {
                if (notification.parentElement) {
                    notification.remove();
                }
            }, 5000);
        }
    });

    // Extender ListView para usar el nuevo renderer
    const SatModernListView = ListView.extend({
        config: _.extend({}, ListView.prototype.config, {
            Renderer: SatModernListRenderer,
        }),
    });

    return SatModernListView;
});

// Inicialización global
document.addEventListener('DOMContentLoaded', function() {
    
    // Aplicar tema guardado
    const savedTheme = localStorage.getItem('sat-theme');
    if (savedTheme) {
        document.documentElement.setAttribute('data-theme', savedTheme);
    }
    
    // Configurar atajos de teclado
    document.addEventListener('keydown', function(e) {
        // Ctrl+F para búsqueda
        if (e.ctrlKey && e.key === 'f') {
            e.preventDefault();
            const searchInput = document.querySelector('.search-input');
            if (searchInput) {
                searchInput.focus();
            }
        }
        
        // Escape para limpiar filtros
        if (e.key === 'Escape') {
            const activeFilter = document.querySelector('.filter-btn.active');
            if (activeFilter) {
                activeFilter.classList.remove('active');
                const rows = document.querySelectorAll('tbody tr');
                rows.forEach(row => row.style.display = '');
            }
        }
    });
    
    console.log('🚀 SAT Modern Table initialized successfully');
});