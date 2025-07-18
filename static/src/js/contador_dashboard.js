/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { KanbanController } from "@web/views/kanban/kanban_controller";

export class ContadorDashboardKanban extends KanbanController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        
        this.state = useState({
            estadisticas: {
                equipos_unicos_hoy: 0,
                equipos_unicos_semana: 0,
                total_equipos_sistema: 0,
                eficiencia_sistema: 0,
                estado_sistema: 'optimo'
            },
            loading: true
        });

        onWillStart(this.loadDashboardData);
    }

    async loadDashboardData() {
        try {
            const estadisticas = await this.orm.call(
                "contador.dashboard",
                "obtener_estadisticas_dashboard",
                []
            );
            
            this.state.estadisticas = estadisticas;
            this.state.loading = false;
            
            // Actualizar los elementos del DOM
            this.updateStatsDisplay();
            
        } catch (error) {
            console.error("Error cargando dashboard:", error);
            this.notification.add("Error cargando datos del dashboard", {
                type: "danger"
            });
        }
    }

    updateStatsDisplay() {
        // Actualizar estadísticas en el DOM
        const stats = this.state.estadisticas;
        
        setTimeout(() => {
            const equiposHoy = document.getElementById('equipos_hoy');
            const equiposSemana = document.getElementById('equipos_semana');
            const totalEquipos = document.getElementById('total_equipos');
            const eficiencia = document.getElementById('eficiencia');
            
            if (equiposHoy) equiposHoy.textContent = stats.equipos_unicos_hoy;
            if (equiposSemana) equiposSemana.textContent = stats.equipos_unicos_semana;
            if (totalEquipos) totalEquipos.textContent = stats.total_equipos_sistema;
            if (eficiencia) eficiencia.textContent = `${stats.eficiencia_sistema}%`;
            
            // Animar números
            this.animateNumbers();
        }, 100);
    }

    animateNumbers() {
        // Animación de conteo para los números
        const elements = document.querySelectorAll('.stat-card h4');
        elements.forEach(el => {
            const target = parseInt(el.textContent);
            let current = 0;
            const increment = target / 20;
            
            const timer = setInterval(() => {
                current += increment;
                if (current >= target) {
                    current = target;
                    clearInterval(timer);
                }
                el.textContent = Math.floor(current);
            }, 50);
        });
    }

    async refreshDashboard() {
        this.state.loading = true;
        await this.loadDashboardData();
        await this.model.load();
        
        this.notification.add("Dashboard actualizado", {
            type: "success"
        });
    }

    // Override para manejar clicks en las tarjetas
    onRecordClick(record) {
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            name: `Detalle: ${record.data.cliente_detectado} - ${record.data.serie_detectada}`,
            res_model: "contador.detalle",
            view_mode: "form",
            target: "new",
            context: {
                default_serie: record.data.serie_detectada,
                default_cliente: record.data.cliente_detectado,
                form_view_initial_mode: "readonly",
            }
        });
    }
}

// Registrar el componente
registry.category("views").add("contador_dashboard_kanban", {
    ...registry.category("views").get("kanban"),
    Controller: ContadorDashboardKanban,
});