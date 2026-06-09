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
            loadingDetalle: false,

            fechaInicio: null,
            fechaFin: null,

            evaluaciones: [],
            detalleDiario: [],
            selectedEvaluacion: null,

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
                diasActivos: 0,
                diasSinActividad: 0,
            },

            rankingPuntaje: [],
            rankingProductividad: [],
            reparacionesPorTecnico: [],
            ticketsPorTecnico: [],
            diasSinActividadRanking: [],

            niveles: [],
            estadosProductividad: [],
        });

        onWillStart(async () => {
            this._setDefaultDates();
            await this.loadDashboard();
        });
    }

    // ============================================================
    // FECHAS
    // ============================================================

    _setDefaultDates() {
        const today = new Date();

        // Carga todo el año actual para que no salga vacío si no hay datos del mes actual.
        const firstDay = new Date(today.getFullYear(), 0, 1);
        const lastDay = new Date(today.getFullYear(), 11, 31);

        this.state.fechaInicio = this._formatDate(firstDay);
        this.state.fechaFin = this._formatDate(lastDay);
    }

    _formatDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    // ============================================================
    // CARGA PRINCIPAL
    // ============================================================

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
                "evaluador_id",
                "state",

                "cantidad_reparaciones",
                "objetivo_reparaciones",
                "porcentaje_reparaciones",

                "cantidad_tickets",
                "objetivo_tickets",
                "porcentaje_tickets",

                "puntaje_objetivos",
                "puntaje_desempeno",
                "puntaje_total",
                "nivel_desempeno",

                "total_dias_trabajados",
                "total_dias_sin_actividad",
                "mejor_dia_fecha",
                "mejor_dia_total",
                "peor_dia_fecha",
                "peor_dia_total",

                "necesita_capacitacion",
                "temas_capacitacion",
                "fortalezas",
                "areas_mejora",
                "plan_accion",

                "total_trabajos_mes",
                "objetivo_total_trabajos",
                "porcentaje_productividad_total",
                "porcentaje_productividad_real",
                "promedio_diario_total",
                "diferencia_objetivo_total",
                "estado_productividad",
                "estado_dashboard",
                "requiere_seguimiento",
                "prioridad_seguimiento",
                "resumen_dashboard",
                "alerta_dashboard",
                "indicador_actividad",
                "resumen_productividad",
                "resumen_puntaje",
                "resumen_objetivo",
                "actividad_promedio_por_dia_activo",
            ];

            const evaluaciones = await this.orm.searchRead(
                "evaluacion.personal",
                domain,
                fields,
                { order: "fecha desc, puntaje_total desc" }
            );

            this.state.evaluaciones = evaluaciones;
            this._computeDashboard(evaluaciones);

            if (evaluaciones.length) {
                await this.selectEvaluacion(evaluaciones[0]);
            } else {
                this.state.selectedEvaluacion = null;
                this.state.detalleDiario = [];
            }
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
        let diasActivos = 0;
        let diasSinActividad = 0;

        const nivelesMap = {
            deficiente: 0,
            regular: 0,
            bueno: 0,
            muy_bueno: 0,
            excelente: 0,
        };

        const productividadMap = {
            sin_datos: 0,
            critico: 0,
            bajo: 0,
            aceptable: 0,
            bueno: 0,
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

            diasActivos += ev.total_dias_trabajados || 0;
            diasSinActividad += ev.total_dias_sin_actividad || 0;

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

            if (ev.estado_productividad && productividadMap[ev.estado_productividad] !== undefined) {
                productividadMap[ev.estado_productividad] += 1;
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
            diasActivos,
            diasSinActividad,
        };

        this.state.rankingPuntaje = [...evaluaciones]
            .sort((a, b) => (b.puntaje_total || 0) - (a.puntaje_total || 0))
            .slice(0, 10);

        this.state.rankingProductividad = [...evaluaciones]
            .sort((a, b) => (b.porcentaje_productividad_total || 0) - (a.porcentaje_productividad_total || 0))
            .slice(0, 10);

        this.state.reparacionesPorTecnico = [...evaluaciones]
            .sort((a, b) => (b.cantidad_reparaciones || 0) - (a.cantidad_reparaciones || 0))
            .slice(0, 10);

        this.state.ticketsPorTecnico = [...evaluaciones]
            .sort((a, b) => (b.cantidad_tickets || 0) - (a.cantidad_tickets || 0))
            .slice(0, 10);

        this.state.diasSinActividadRanking = [...evaluaciones]
            .sort((a, b) => (b.total_dias_sin_actividad || 0) - (a.total_dias_sin_actividad || 0))
            .slice(0, 10);

        this.state.niveles = [
            { label: "Deficiente", key: "deficiente", value: nivelesMap.deficiente, className: "danger" },
            { label: "Regular", key: "regular", value: nivelesMap.regular, className: "warning" },
            { label: "Bueno", key: "bueno", value: nivelesMap.bueno, className: "info" },
            { label: "Muy Bueno", key: "muy_bueno", value: nivelesMap.muy_bueno, className: "primary" },
            { label: "Excelente", key: "excelente", value: nivelesMap.excelente, className: "success" },
        ];

        this.state.estadosProductividad = [
            { label: "Crítico", key: "critico", value: productividadMap.critico, className: "danger" },
            { label: "Bajo", key: "bajo", value: productividadMap.bajo, className: "warning" },
            { label: "Aceptable", key: "aceptable", value: productividadMap.aceptable, className: "yellow" },
            { label: "Bueno", key: "bueno", value: productividadMap.bueno, className: "info" },
            { label: "Excelente", key: "excelente", value: productividadMap.excelente, className: "success" },
        ];
    }

    // ============================================================
    // DETALLE DIARIO
    // ============================================================

    async selectEvaluacion(ev) {
        this.state.selectedEvaluacion = ev;
        await this.loadDetalleDiario(ev.id);
    }

    async loadDetalleDiario(evaluacionId) {
        if (!evaluacionId) {
            this.state.detalleDiario = [];
            return;
        }

        this.state.loadingDetalle = true;

        try {
            const fields = [
                "fecha",
                "dia_semana",
                "cantidad_reparaciones",
                "cantidad_tickets",
                "total_trabajos",
                "objetivo_dia",
                "porcentaje_cumplimiento",
                "cumple_objetivo",
                "estado_dia",
                "clientes_atendidos",
                "modelos_trabajados",
                "cantidad_clientes",
            ];

            const detalle = await this.orm.searchRead(
                "evaluacion.personal.detalle.diario",
                [["evaluacion_id", "=", evaluacionId]],
                fields,
                { order: "fecha asc" }
            );

            this.state.detalleDiario = detalle;
        } catch (error) {
            console.error("Error cargando detalle diario:", error);
            this.notification.add("No se pudo cargar el detalle diario.", {
                type: "warning",
            });
        } finally {
            this.state.loadingDetalle = false;
        }
    }

    // ============================================================
    // HELPERS
    // ============================================================

    getTecnicoName(record) {
        return record.usuario_id && record.usuario_id[1] ? record.usuario_id[1] : "Sin técnico";
    }

    getEvaluadorName(record) {
        return record.evaluador_id && record.evaluador_id[1] ? record.evaluador_id[1] : "Sin evaluador";
    }

    getPercent(value) {
        return Math.round(value || 0);
    }

    getFloat(value) {
        return Number(value || 0).toFixed(2);
    }

    getBarWidth(value) {
        return `width: ${Math.min(100, Math.max(0, value || 0))}%`;
    }

    getRelativeWidth(value, maxValue) {
        const width = maxValue ? (value / maxValue) * 100 : 0;
        return `width: ${Math.min(100, Math.max(0, width))}%`;
    }

    getMaxValue(records, fieldName) {
        const values = records.map((record) => record[fieldName] || 0);
        return Math.max(...values, 1);
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

    getEstadoDiaLabel(estado) {
        const labels = {
            sin_actividad: "Sin Actividad",
            bajo: "Bajo",
            aceptable: "Aceptable",
            bueno: "Bueno",
            excelente: "Excelente",
        };
        return labels[estado] || "Sin datos";
    }

    getProductividadLabel(estado) {
        const labels = {
            sin_datos: "Sin Datos",
            critico: "Crítico",
            bajo: "Bajo",
            aceptable: "Aceptable",
            bueno: "Bueno",
            excelente: "Excelente",
        };
        return labels[estado] || "Sin datos";
    }

    getMonthName(dateStr) {
        if (!dateStr) {
            return "";
        }
        const date = new Date(`${dateStr}T00:00:00`);
        return date.toLocaleDateString("es-PE", {
            month: "long",
            year: "numeric",
        });
    }

    // ============================================================
    // EVENTOS
    // ============================================================

    async onApplyFilter() {
        await this.loadDashboard();
    }

    onChangeDateStart(ev) {
        this.state.fechaInicio = ev.target.value;
    }

    onChangeDateEnd(ev) {
        this.state.fechaFin = ev.target.value;
    }

    // ============================================================
    // ACCIONES ODOO
    // ============================================================

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

    async openDetalleDiario(record) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: `Detalle Diario - ${this.getTecnicoName(record)}`,
            res_model: "evaluacion.personal.detalle.diario",
            views: [[false, "list"], [false, "form"], [false, "pivot"], [false, "graph"]],
            domain: [["evaluacion_id", "=", record.id]],
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

    async openDeficientes() {
        await this.openFilteredEvaluaciones(
            [["nivel_desempeno", "=", "deficiente"]],
            "Evaluaciones Deficientes"
        );
    }

    async openDestacados() {
        await this.openFilteredEvaluaciones(
            [["estado_dashboard", "=", "destacado"]],
            "Evaluaciones Destacadas"
        );
    }
}

registry.category("actions").add("evaluacion_personal_dashboard_tag", EvaluacionPersonalDashboard);