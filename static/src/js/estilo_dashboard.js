/** @odoo-module **/
// Archivo: static/src/js/estilo_dashboard.js

import { Component } from "@odoo/owl";

export class Dashboard extends Component {
    setup() {
        this.charts = {};
    }

    static template = 'sat.DashboardTemplate';

    /**
     * @override
     */
    async mounted() {
        this.setupChartExpansion();
    }

    /**
     * Configura los listeners para expandir/contraer gráficos
     */
    setupChartExpansion() {
        const expandButtons = this.el.querySelectorAll('.expand-button');
        expandButtons.forEach(button => {
            button.addEventListener('click', () => this.toggleChart(button));
        });
    }

    /**
     * Alterna la expansión de un gráfico
     * @param {HTMLElement} button - Botón de expansión clickeado
     */
    toggleChart(button) {
        const container = button.closest('.chart-wrapper').querySelector('.chart-container');
        const icon = button.querySelector('i');
        
        container.classList.toggle('expanded');
        
        if (container.classList.contains('expanded')) {
            icon.classList.remove('fa-expand');
            icon.classList.add('fa-compress');
        } else {
            icon.classList.remove('fa-compress');
            icon.classList.add('fa-expand');
        }
        
        // Actualizar el gráfico después de la transición
        setTimeout(() => {
            const chartId = container.querySelector('[id^="chart"]'); // Selecciona el primer gráfico con id que contenga 'chart'
            if (this.charts[chartId]) {
                this.charts[chartId].resize();
            }
        }, 300);
    }
}
