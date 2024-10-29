/** @odoo-module **/
// Archivo: static/src/js/estilo_dashboard.js

import { Component } from "@odoo/owl";

export class Dashboard extends Component {
    setup() {
        this.charts = {};
    }

    static template = 'sat.DashboardTemplate';

    async mounted() {
        this.setupChartExpansion();
    }

    setupChartExpansion() {
        const expandButtons = this.el.querySelectorAll('.expand-button');
        expandButtons.forEach(button => {
            button.addEventListener('click', () => this.toggleChart(button));
        });
    }

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
        
        // Ajusta el gráfico después de la transición
        setTimeout(() => {
            const chartId = container.querySelector('[id^="chart"]');
            if (this.charts[chartId]) {
                this.charts[chartId].resize();
            }
        }, 300);
    }
}
