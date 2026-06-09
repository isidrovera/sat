/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class EvaluacionPersonalDashboard extends Component {
    static template = "sat.EvaluacionPersonalDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            evaluaciones: [],
            kpis: {
                totalEvaluaciones: 0,
                totalTecnicos: 0,
                promedioPuntaje: 0,
                promedioProductividad: 0,
                totalReparaciones: 0,
                totalTickets: 0,
                totalTrabajos: 0,
                objetivoTotal: 0,
                deficientes: 0,
                seguimiento: 0,
                destacados: 0,
            },
            rankingPuntaje: [],
            rankingProductividad: [],
            niveles: [],
            productividadPorTecnico: [],
            reparacionesPorTecnico: [],
            ticketsPorTecnico: [],
            fechaInicio: null,
            fechaFin: null,
        });

        onWillStart(async () => {
            this._setDefaultDates();
            await this.loadDashboard();
        });
    }

    _setDefaultDates() {
        const today = new Date();
        const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
        const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0);

        this.state.fechaInicio = this._formatDate(firstDay);
        this.state.fechaFin = this._formatDate(lastDay);
    }

    _formatDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    async loadDashboard() {
        this.state.loading = true;

        try {
            const domain = [
                ["fecha", ">=", this.state.fechaInicio],
                ["fecha", "<=", this.state.fechaFin],
            ];

            const fields = [
                "name",
                "fecha",
                "usuario_id",
                "state",
                "cantidad_reparaciones",
                "objetivo_reparaciones",
                "porcentaje_reparaciones",
                "cantidad_tickets",
                "objetivo_tickets",
                "porcentaje_tickets",
                "puntaje_total",
                "nivel_desempeno",
                "total_dias_trabajados",
                "total_dias_sin_actividad",
                "necesita_capacitacion",

                // campos del archivo evaluacion_personal_dashboard.py
                "total_trabajos_mes",
                "objetivo_total_trabajos",
                "porcentaje_productividad_total",
                "estado_productividad",
                "estado_dashboard",
                "requiere_seguimiento",
                "prioridad_seguimiento",
                "resumen_dashboard",
                "alerta_dashboard",
                "indicador_actividad",
            ];

            const evaluaciones = await this.orm.searchRead(
                "evaluacion.personal",
                domain,
                fields,
                { order: "puntaje_total desc" }
            );

            this.state.evaluaciones = evaluaciones;
            this._computeDashboard(evaluaciones);
        } catch (error) {
            console.error("Error cargando dashboard de evaluaciones:", error);
            this.notification.add("No se pudo cargar el dashboard de evaluaciones.", {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    _computeDashboard(evaluaciones) {
        const totalEvaluaciones = evaluaciones.length;
        const tecnicos = new Set();

        let totalPuntaje = 0;
        let totalProductividad = 0;
        let totalReparaciones = 0;
        let totalTickets = 0;
        let totalTrabajos = 0;
        let objetivoTotal = 0;
        let deficientes = 0;
        let seguimiento = 0;
        let destacados = 0;

        const nivelesMap = {
            deficiente: 0,
            regular: 0,
            bueno: 0,
            muy_bueno: 0,
            excelente: 0,
        };

        for (const ev of evaluaciones) {
            if (ev.usuario_id && ev.usuario_id[0]) {
                tecnicos.add(ev.usuario_id[0]);
            }

            const puntaje = ev.puntaje_total || 0;
            const productividad = ev.porcentaje_productividad_total || 0;

            totalPuntaje += puntaje;
            totalProductividad += productividad;
            totalReparaciones += ev.cantidad_reparaciones || 0;
            totalTickets += ev.cantidad_tickets || 0;
            totalTrabajos += ev.total_trabajos_mes || 0;
            objetivoTotal += ev.objetivo_total_trabajos || 0;

            if (ev.nivel_desempeno === "deficiente") {
                deficientes += 1;
            }

            if (ev.requiere_seguimiento) {
                seguimiento += 1;
            }

            if (ev.estado_dashboard === "destacado" || ev.nivel_desempeno === "excelente") {
                destacados += 1;
            }

            if (ev.nivel_desempeno && nivelesMap[ev.nivel_desempeno] !== undefined) {
                nivelesMap[ev.nivel_desempeno] += 1;
            }
        }

        this.state.kpis = {
            totalEvaluaciones,
            totalTecnicos: tecnicos.size,
            promedioPuntaje: totalEvaluaciones ? totalPuntaje / totalEvaluaciones : 0,
            promedioProductividad: totalEvaluaciones ? totalProductividad / totalEvaluaciones : 0,
            totalReparaciones,
            totalTickets,
            totalTrabajos,
            objetivoTotal,
            deficientes,
            seguimiento,
            destacados,
        };

        this.state.rankingPuntaje = [...evaluaciones]
            .sort((a, b) => (b.puntaje_total || 0) - (a.puntaje_total || 0))
            .slice(0, 8);

        this.state.rankingProductividad = [...evaluaciones]
            .sort((a, b) => (b.porcentaje_productividad_total || 0) - (a.porcentaje_productividad_total || 0))
            .slice(0, 8);

        this.state.niveles = [
            { label: "Deficiente", key: "deficiente", value: nivelesMap.deficiente, className: "danger" },
            { label: "Regular", key: "regular", value: nivelesMap.regular, className: "warning" },
            { label: "Bueno", key: "bueno", value: nivelesMap.bueno, className: "info" },
            { label: "Muy Bueno", key: "muy_bueno", value: nivelesMap.muy_bueno, className: "primary" },
            { label: "Excelente", key: "excelente", value: nivelesMap.excelente, className: "success" },
        ];

        this.state.productividadPorTecnico = [...evaluaciones]
            .sort((a, b) => (b.porcentaje_productividad_total || 0) - (a.porcentaje_productividad_total || 0))
            .slice(0, 10);

        this.state.reparacionesPorTecnico = [...evaluaciones]
            .sort((a, b) => (b.cantidad_reparaciones || 0) - (a.cantidad_reparaciones || 0))
            .slice(0, 10);

        this.state.ticketsPorTecnico = [...evaluaciones]
            .sort((a, b) => (b.cantidad_tickets || 0) - (a.cantidad_tickets || 0))
            .slice(0, 10);
    }

    getNivelLabel(nivel) {
        const labels = {
            deficiente: "Deficiente",
            regular: "Regular",
            bueno: "Bueno",
            muy_bueno: "Muy Bueno",
            excelente: "Excelente",
        };
        return labels[nivel] || "Sin nivel";
    }

    getEstadoLabel(estado) {
        const labels = {
            sin_datos: "Sin Datos",
            requiere_revision: "Requiere Revisión",
            en_observacion: "En Observación",
            estable: "Estable",
            destacado: "Destacado",
        };
        return labels[estado] || "Sin datos";
    }

    getTecnicoName(record) {
        return record.usuario_id && record.usuario_id[1] ? record.usuario_id[1] : "Sin técnico";
    }

    getPercent(value) {
        return Math.round(value || 0);
    }

    getBarWidth(value) {
        return `width: ${Math.min(100, Math.max(0, value || 0))}%`;
    }

    getMaxValue(records, fieldName) {
        const values = records.map((r) => r[fieldName] || 0);
        return Math.max(...values, 1);
    }

    getRelativeWidth(value, maxValue) {
        const width = maxValue ? (value / maxValue) * 100 : 0;
        return `width: ${Math.min(100, Math.max(0, width))}%`;
    }

    async onApplyFilter() {
        await this.loadDashboard();
    }

    onChangeDateStart(ev) {
        this.state.fechaInicio = ev.target.value;
    }

    onChangeDateEnd(ev) {
        this.state.fechaFin = ev.target.value;
    }

    async openEvaluaciones() {
        await this.action.doAction("sat.action_evaluacion_personal");
    }

    async openEvaluacion(record) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Evaluación de Personal",
            res_model: "evaluacion.personal",
            res_id: record.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openFilteredEvaluaciones(domain, name = "Evaluaciones") {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "evaluacion.personal",
            views: [[false, "list"], [false, "form"], [false, "kanban"], [false, "pivot"], [false, "graph"]],
            domain,
            target: "current",
        });
    }

    async openSeguimiento() {
        await this.openFilteredEvaluaciones(
            [["requiere_seguimiento", "=", true]],
            "Evaluaciones con Seguimiento"
        );
    }
}

registry.category("actions").add("evaluacion_personal_dashboard_tag", EvaluacionPersonalDashboard);