/** @odoo-module */
// Archivo: static/src/js/dashboard.js

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
        await this.initializeCharts();
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
            const chartId = container.querySelector('canvas').id;
            if (this.charts[chartId]) {
                this.charts[chartId].resize();
            }
        }, 500); // Aumentado a 500ms para asegurar la transición completa
    }

    /**
     * Inicializa todos los gráficos
     */
    async initializeCharts() {
        await this.initDisponibilidadChart();
        await this.initEstadoChart();
        await this.initTecnicosChart();
        await this.initAsesoraChart();
    }

    // Métodos de inicialización de gráficos (sin cambios)
    async initDisponibilidadChart() { /* ... */ }
    async initEstadoChart() { /* ... */ }
    async initTecnicosChart() { /* ... */ }
    async initAsesoraChart() { /* ... */ }

    /**
     * Actualiza los datos de los gráficos
     * @param {Object} data - Nuevos datos para actualizar los gráficos
     */
    updateCharts(data) {
        // Actualizar los datos de cada gráfico
        Object.keys(this.charts).forEach(chartId => {
            if (this.charts[chartId] && data[chartId]) {
                this.charts[chartId].data = data[chartId];
                this.charts[chartId].update();
            }
        });
    }
}
