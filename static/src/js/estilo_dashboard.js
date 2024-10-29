/** @odoo-module */
// Archivo: static/src/js/dashboard.js

import { Component } from "@odoo/owl";
import { Chart } from 'chart.js/auto';

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
        }, 300);
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

    /**
     * Inicializa el gráfico de disponibilidad
     */
    async initDisponibilidadChart() {
        const ctx = document.getElementById('disponibilidadChart');
        if (!ctx) return;

        this.charts.disponibilidadChart = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: ['Disponibles', 'Separadas', 'No Disponibles'],
                datasets: [{
                    data: [50, 30, 20],
                    backgroundColor: ['#4BC0C0', '#FFCE56', '#FF6384']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }

    /**
     * Inicializa el gráfico de estado
     */
    async initEstadoChart() {
        const ctx = document.getElementById('estadoChart');
        if (!ctx) return;

        this.charts.estadoChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Revisión', 'Finalizadas', 'Con Problemas', 'De Partes'],
                datasets: [{
                    data: [25, 40, 15, 20],
                    backgroundColor: ['#36A2EB', '#4BC0C0', '#FF6384', '#FFCE56']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }

    /**
     * Inicializa el gráfico de técnicos
     */
    async initTecnicosChart() {
        const ctx = document.getElementById('tecnicosChart');
        if (!ctx) return;

        this.charts.tecnicosChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Técnico A', 'Técnico B', 'Técnico C', 'Técnico D'],
                datasets: [{
                    data: [15, 20, 12, 18],
                    backgroundColor: ['#36A2EB', '#4BC0C0', '#FF6384', '#FFCE56']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }

    /**
     * Inicializa el gráfico de asesoras
     */
    async initAsesoraChart() {
        const ctx = document.getElementById('asesoraChart');
        if (!ctx) return;

        this.charts.asesoraChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Asesora A', 'Asesora B', 'Asesora C', 'Asesora D'],
                datasets: [{
                    data: [25, 18, 22, 20],
                    backgroundColor: ['#36A2EB', '#4BC0C0', '#FF6384', '#FFCE56']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }

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