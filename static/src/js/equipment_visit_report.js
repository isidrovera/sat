/* Archivo: /static/src/js/equipment_visit_report.js */

odoo.define('sat.equipment_visit_report', function (require) {
    'use strict';

    // Este script se ejecutará cuando se cargue el informe

    /**
     * Inicializa los tooltips y elementos interactivos en el informe
     */
    function initReportEnhancements() {
        // Se asegura que el DOM esté completamente cargado
        document.addEventListener('DOMContentLoaded', function() {
            // Opcional: Añadir tooltips a los elementos del informe
            setupTooltips();
            
            // Si se necesita, podemos añadir interactividad a los gráficos
            enhanceCharts();
            
            // Para hacer que las tarjetas de resumen sean más interactivas
            setupStatCards();
        });
    }

    /**
     * Configura tooltips para elementos informativos
     */
    function setupTooltips() {
        // Encuentra todos los elementos que necesitan tooltips
        const tooltipElements = document.querySelectorAll('.ev-visit-count, .ev-client-count');
        
        // Aquí puedes agregar código para inicializar tooltips según la biblioteca que uses
        // Por ejemplo, si usas Bootstrap tooltips:
        tooltipElements.forEach(function(element) {
            // Código para inicializar tooltips
        });
    }

    /**
     * Mejora la visualización de los gráficos si están presentes
     */
    function enhanceCharts() {
        // Si los gráficos ya están renderizados como imágenes desde el backend,
        // este código no será necesario. En caso de implementar gráficos dinámicos con
        // bibliotecas como Chart.js, aquí iría ese código.
    }

    /**
     * Hace que las tarjetas de estadísticas sean interactivas
     */
    function setupStatCards() {
        const statCards = document.querySelectorAll('.ev-stat-card');
        
        // Agrega efectos de hover o click a las tarjetas
        statCards.forEach(function(card) {
            card.addEventListener('mouseover', function() {
                // Efecto hover - opcional
                this.style.transform = 'translateY(-5px)';
                this.style.boxShadow = '0 15px 20px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)';
            });
            
            card.addEventListener('mouseout', function() {
                // Restaurar estado normal
                this.style.transform = '';
                this.style.boxShadow = '';
            });
        });
    }

    // Inicializa el módulo
    initReportEnhancements();

    return {
        initReportEnhancements: initReportEnhancements,
    };
});