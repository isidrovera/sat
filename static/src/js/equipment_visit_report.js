/** @odoo-module **/
import { registry } from "@web/core/registry/registry";
import publicWidget from "web.public.widget";

const { Component } = owl;

/**
 * Widget para mejorar la interactividad del informe de visitas técnicas
 */
export class EquipmentVisitReport extends publicWidget.Widget {
    /**
     * @override
     */
    start() {
        this._setupStatCards();
        this._setupTooltips();
        return this._super(...arguments);
    }

    /**
     * Configura tooltips para elementos informativos
     * @private
     */
    _setupTooltips() {
        // Encuentra todos los elementos que necesitan tooltips
        const tooltipElements = document.querySelectorAll('.ev-visit-count, .ev-client-count');
        
        // Implementación básica de tooltips
        tooltipElements.forEach(element => {
            // Código para inicializar tooltips si es necesario
        });
    }

    /**
     * Hace que las tarjetas de estadísticas sean interactivas
     * @private
     */
    _setupStatCards() {
        const statCards = document.querySelectorAll('.ev-stat-card');
        
        // Agrega efectos de hover o click a las tarjetas
        statCards.forEach(card => {
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
}

// Registra el widget en el registro de Odoo
registry.category("public_widgets").add("equipmentVisitReport", {
    Widget: EquipmentVisitReport,
    selector: '.page',
});