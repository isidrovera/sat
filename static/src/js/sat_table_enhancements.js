// static/src/js/sat_table_enhancements.js
/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount } from "@odoo/owl";

// Patch para mejorar la funcionalidad de la tabla SAT
patch(ListController.prototype, {
    setup() {
        super.setup();
        onMounted(() => {
            if (this.props.resModel === "sat.sat") {
                this.initializeSatTableEnhancements();
            }
        });
        
        onWillUnmount(() => {
            this.cleanupSatTableEnhancements();
        });
    },

    initializeSatTableEnhancements() {
        // Inicializar mejoras para la tabla SAT
        this.setupTableAnimations();
        this.setupRowHoverEffects();
        this.setupResponsiveHandling();
        this.setupKeyboardNavigation();
        this.setupToolTips();
    },

    setupTableAnimations() {
        const table = document.querySelector('.modern-sat-table');
        if (!table) return;

        // Agregar clase de animación entrada
        table.classList.add('animate__animated', 'animate__fadeIn');

        // Animación escalonada para las filas
        const rows = table.querySelectorAll('tbody tr');
        rows.forEach((row, index) => {
            row.style.animationDelay = `${index * 0.05}s`;
            row.classList.add('animate__animated', 'animate__fadeInUp');
        });
    },

    setupRowHoverEffects() {
        const table = document.querySelector('.modern-sat-table');
        if (!table) return;

        const rows = table.querySelectorAll('tbody tr');
        rows.forEach(row => {
            // Efecto de resaltado al hacer hover
            row.addEventListener('mouseenter', () => {
                this.highlightRelatedData(row);
            });

            row.addEventListener('mouseleave', () => {
                this.clearHighlights();
            });

            // Efecto de click para selección
            row.addEventListener('click', (e) => {
                if (!e.target.closest('button')) {
                    this.selectRow(row);
                }
            });
        });
    },

    highlightRelatedData(currentRow) {
        const table = document.querySelector('.modern-sat-table');
        if (!table) return;

        // Obtener datos de la fila actual
        const clienteCell = currentRow.querySelector('.client-info');
        const marcaCell = currentRow.querySelector('.brand-modern');
        
        if (!clienteCell || !marcaCell) return;

        const cliente = clienteCell.textContent.trim();
        const marca = marcaCell.textContent.trim();

        // Resaltar filas relacionadas
        const allRows = table.querySelectorAll('tbody tr');
        allRows.forEach(row => {
            const rowCliente = row.querySelector('.client-info')?.textContent.trim();
            const rowMarca = row.querySelector('.brand-modern')?.textContent.trim();

            if (row !== currentRow && (rowCliente === cliente || rowMarca === marca)) {
                row.classList.add('related-highlight');
            }
        });
    },

    clearHighlights() {
        const highlightedRows = document.querySelectorAll('.related-highlight');
        highlightedRows.forEach(row => {
            row.classList.remove('related-highlight');
        });
    },

    selectRow(row) {
        // Limpiar selecciones previas
        const selectedRows = document.querySelectorAll('.row-selected');
        selectedRows.forEach(r => r.classList.remove('row-selected'));

        // Seleccionar fila actual
        row.classList.add('row-selected');

        // Mostrar información adicional si está disponible
        this.showRowDetails(row);
    },

    showRowDetails(row) {
        // Implementar mostrar detalles adicionales de la máquina
        const machineId = row.dataset.id;
        if (machineId) {
            // Aquí se puede agregar lógica para mostrar un panel de detalles
            console.log(`Máquina seleccionada: ${machineId}`);
        }
    },

    setupResponsiveHandling() {
        const handleResize = () => {
            const table = document.querySelector('.modern-sat-table');
            if (!table) return;

            const width = window.innerWidth;
            
            if (width < 768) {
                table.classList.add('mobile-view');
                this.setupMobileOptimizations();
            } else {
                table.classList.remove('mobile-view');
            }
        };

        window.addEventListener('resize', handleResize);
        handleResize(); // Ejecutar inmediatamente
    },

    setupMobileOptimizations() {
        const table = document.querySelector('.modern-sat-table');
        if (!table) return;

        // Hacer que los botones sean más grandes en móvil
        const buttons = table.querySelectorAll('.btn-modern');
        buttons.forEach(btn => {
            btn.classList.add('btn-mobile');
        });

        // Agregar scroll horizontal suave
        table.style.overflowX = 'auto';
        table.style.webkitOverflowScrolling = 'touch';
    },

    setupKeyboardNavigation() {
        const table = document.querySelector('.modern-sat-table');
        if (!table) return;

        table.addEventListener('keydown', (e) => {
            const selectedRow = table.querySelector('.row-selected');
            if (!selectedRow) return;

            let nextRow = null;

            switch(e.key) {
                case 'ArrowDown':
                    nextRow = selectedRow.nextElementSibling;
                    break;
                case 'ArrowUp':
                    nextRow = selectedRow.previousElementSibling;
                    break;
                case 'Enter':
                    // Activar el primer botón disponible
                    const firstButton = selectedRow.querySelector('button:not([invisible])');
                    if (firstButton) {
                        firstButton.click();
                    }
                    return;
            }

            if (nextRow && nextRow.tagName === 'TR') {
                e.preventDefault();
                this.selectRow(nextRow);
                nextRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        });

        // Hacer la tabla focusable
        table.setAttribute('tabindex', '0');
    },

    setupToolTips() {
        const table = document.querySelector('.modern-sat-table');
        if (!table) return;

        // Agregar tooltips informativos
        const availabilityBadges = table.querySelectorAll('.availability-badge-modern');
        availabilityBadges.forEach(badge => {
            const status = badge.textContent.trim().toLowerCase();
            let tooltipText = '';

            switch(status) {
                case 'disponible':
                    tooltipText = 'Máquina lista para venta';
                    break;
                case 'separada':
                    tooltipText = 'Máquina reservada por cliente';
                    break;
                case 'no_disponible':
                    tooltipText = 'Máquina no disponible temporalmente';
                    break;
            }

            if (tooltipText) {
                badge.setAttribute('title', tooltipText);
                badge.setAttribute('data-bs-toggle', 'tooltip');
            }
        });

        // Inicializar tooltips de Bootstrap si está disponible
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            const tooltipTriggerList = table.querySelectorAll('[data-bs-toggle="tooltip"]');
            [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
        }
    },

    cleanupSatTableEnhancements() {
        // Limpiar event listeners y recursos
        window.removeEventListener('resize', this.handleResize);
        
        // Limpiar tooltips
        const tooltips = document.querySelectorAll('.tooltip');
        tooltips.forEach(tooltip => tooltip.remove());
    },

    // Método para actualizar contadores en tiempo real
    updateCounters() {
        const counterCells = document.querySelectorAll('.counter-modern');
        counterCells.forEach(cell => {
            const currentValue = parseInt(cell.textContent) || 0;
            // Agregar efecto de actualización
            cell.classList.add('counter-updated');
            setTimeout(() => {
                cell.classList.remove('counter-updated');
            }, 1000);
        });
    },

    // Método para filtrar tabla por disponibilidad
    filterByAvailability(status) {
        const table = document.querySelector('.modern-sat-table');
        if (!table) return;

        const rows = table.querySelectorAll('tbody tr');
        rows.forEach(row => {
            const availabilityBadge = row.querySelector('.availability-badge-modern');
            if (availabilityBadge) {
                const rowStatus = availabilityBadge.textContent.trim().toLowerCase();
                if (status === 'all' || rowStatus === status.toLowerCase()) {
                    row.style.display = '';
                    row.classList.add('animate__animated', 'animate__fadeIn');
                } else {
                    row.style.display = 'none';
                }
            }
        });
    }
});

// Funciones utilitarias globales para la tabla SAT
window.SatTableUtils = {
    // Exportar datos de la tabla
    exportTableData() {
        const table = document.querySelector('.modern-sat-table');
        if (!table) return;

        const data = [];
        const rows = table.querySelectorAll('tbody tr');
        
        rows.forEach(row => {
            const rowData = {};
            const cells = row.querySelectorAll('td');
            cells.forEach((cell, index) => {
                const header = table.querySelectorAll('thead th')[index];
                if (header) {
                    rowData[header.textContent.trim()] = cell.textContent.trim();
                }
            });
            data.push(rowData);
        });

        return data;
    },

    // Buscar en la tabla
    searchTable(searchTerm) {
        const table = document.querySelector('.modern-sat-table');
        if (!table) return;

        const rows = table.querySelectorAll('tbody tr');
        const term = searchTerm.toLowerCase();

        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            if (text.includes(term)) {
                row.style.display = '';
                row.classList.add('search-match');
            } else {
                row.style.display = 'none';
                row.classList.remove('search-match');
            }
        });
    },

    // Limpiar búsqueda
    clearSearch() {
        const table = document.querySelector('.modern-sat-table');
        if (!table) return;

        const rows = table.querySelectorAll('tbody tr');
        rows.forEach(row => {
            row.style.display = '';
            row.classList.remove('search-match');
        });
    }
};