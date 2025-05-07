// Archivo: /static/src/js/equipment_visit_report.js

/**
 * Módulo para mejorar la interactividad del informe de visitas técnicas
 */
odoo.define('sat.equipment_visit_report', [], function (require) {
    'use strict';
    
    var publicWidget = require('web.public.widget');
    
    var EquipmentVisitReport = publicWidget.Widget.extend({
        selector: '.page',
        
        /**
         * Inicializa el widget
         */
        start: function () {
            var self = this;
            this._super.apply(this, arguments);
            
            // Inicializar las funcionalidades
            this._setupStatCards();
            this._setupTooltips();
            
            return this._super.apply(this, arguments);
        },
        
        /**
         * Configura tooltips para elementos informativos
         */
        _setupTooltips: function () {
            // Encuentra todos los elementos que necesitan tooltips
            var tooltipElements = document.querySelectorAll('.ev-visit-count, .ev-client-count');
            
            // Implementación básica de tooltips
            tooltipElements.forEach(function(element) {
                // Código para inicializar tooltips si es necesario
            });
        },
        
        /**
         * Hace que las tarjetas de estadísticas sean interactivas
         */
        _setupStatCards: function () {
            var statCards = document.querySelectorAll('.ev-stat-card');
            
            // Agrega efectos de hover o click a las tarjetas
            statCards.forEach(function(card) {
                card.addEventListener('mouseover', function() {
                    // Efecto hover
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
    });
    
    publicWidget.registry.equipmentVisitReport = EquipmentVisitReport;
    
    return EquipmentVisitReport;
});