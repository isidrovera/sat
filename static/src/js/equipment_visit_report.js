/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onMounted } from "@odoo/owl";

/**
 * Widget para mejorar la interactividad del informe de visitas técnicas
 */
export class EquipmentVisitReport extends Component {
    static template = "sat.EquipmentVisitReportTemplate";

    setup() {
        onMounted(() => {
            this._setupStatCards();
            this._setupTooltips();
        });
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
            element.addEventListener('mouseenter', function() {
                // Agregar tooltip si es necesario
            });
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
                this.style.transition = 'all 0.3s ease';
            });
            
            card.addEventListener('mouseout', function() {
                // Restaurar estado normal
                this.style.transform = '';
                this.style.boxShadow = '';
            });
        });
    }
}

// Registra el componente en el registro de Odoo 18
registry.category("public_widgets").add("equipmentVisitReport", {
    Component: EquipmentVisitReport,
    selector: '.equipment-visit-report-container',
});