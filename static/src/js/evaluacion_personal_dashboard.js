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

        const today = new Date();

        const currentMonth = today.getMonth() + 1;
        const currentYear = today.getFullYear();

        const previous = this._getPreviousMonth(
            currentMonth,
            currentYear
        );

        this.state = useState({
            loading: true,
            loadingDetalle: false,

            // =====================================================
            // PERIODO PRINCIPAL
            // =====================================================

            mes: currentMonth,
            anio: currentYear,

            tipoOperativo: "todos",

            // =====================================================
            // COMPARACIÓN 1
            // Por defecto: mes anterior
            // =====================================================

            compare1Mes: previous.month,
            compare1Anio: previous.year,

            // =====================================================
            // COMPARACIÓN 2
            // Por defecto: mismo mes del año anterior
            // =====================================================

            compare2Mes: currentMonth,
            compare2Anio: currentYear - 1,

            // =====================================================
            // CATÁLOGOS
            // =====================================================

            meses: [
                { value: 1, label: "Enero" },
                { value: 2, label: "Febrero" },
                { value: 3, label: "Marzo" },
                { value: 4, label: "Abril" },
                { value: 5, label: "Mayo" },
                { value: 6, label: "Junio" },
                { value: 7, label: "Julio" },
                { value: 8, label: "Agosto" },
                { value: 9, label: "Septiembre" },
                { value: 10, label: "Octubre" },
                { value: 11, label: "Noviembre" },
                { value: 12, label: "Diciembre" },
            ],

            anios: this._buildYears(currentYear),

            // =====================================================
            // DATOS
            // =====================================================

            evaluaciones: [],
            detalleDiario: [],
            selectedEvaluacion: null,

            // =====================================================
            // KPI
            // =====================================================

            kpis: {
                totalTecnicos: 0,

                cumplenMeta: 0,
                noCumplenMeta: 0,

                conBono: 0,
                sinBono: 0,

                promedioProduccion: 0,
                promedioCalidad: 0,

                seguimiento: 0,
                reclamos: 0,

                encuestasRespondidas: 0,
                encuestasRequeridas: 0,

                variacionCompare1: 0,
                variacionCompare2: 0,
            },

            // =====================================================
            // PERFILES
            // =====================================================

            perfiles: {
                taller: 0,
                servicios: 0,
                mixto: 0,
            },

            // =====================================================
            // RANKINGS
            // =====================================================

            rankingProduccion: [],
            rankingCalidad: [],
            rankingBono: [],
            rankingSeguimiento: [],

            // =====================================================
            // GRÁFICA GENERAL
            // =====================================================

            chartMonths: [],
            chartSeries: [],
        });

        onWillStart(async () => {
            await this.loadDashboard();
        });
    }

    // ============================================================
    // CATÁLOGOS
    // ============================================================

    _buildYears(currentYear) {
        const years = [];

        for (
            let year = currentYear + 1;
            year >= currentYear - 6;
            year--
        ) {
            years.push(year);
        }

        return years;
    }

    // ============================================================
    // FECHAS
    // ============================================================

    _getPreviousMonth(month, year) {
        let newMonth = Number(month) - 1;
        let newYear = Number(year);

        if (newMonth <= 0) {
            newMonth = 12;
            newYear -= 1;
        }

        return {
            month: newMonth,
            year: newYear,
        };
    }

    _pad(value) {
        return String(value).padStart(2, "0");
    }

    _getPeriodRange(month, year) {
        month = Number(month);
        year = Number(year);

        const start =
            `${year}-${this._pad(month)}-01`;

        let nextMonth = month + 1;
        let nextYear = year;

        if (nextMonth > 12) {
            nextMonth = 1;
            nextYear += 1;
        }

        const end =
            `${nextYear}-${this._pad(nextMonth)}-01`;

        return {
            start,
            end,
        };
    }

    getMonthLabel(month, year) {
        const monthData = this.state.meses.find(
            (item) =>
                Number(item.value) === Number(month)
        );

        return `${monthData ? monthData.label : ""} ${year}`;
    }

    getSelectedPeriodLabel() {
        return this.getMonthLabel(
            this.state.mes,
            this.state.anio
        );
    }

    getCompare1Label() {
        return this.getMonthLabel(
            this.state.compare1Mes,
            this.state.compare1Anio
        );
    }

    getCompare2Label() {
        return this.getMonthLabel(
            this.state.compare2Mes,
            this.state.compare2Anio
        );
    }

    // ============================================================
    // CAMPOS PRINCIPALES
    // ============================================================

    _getMainFields() {
        return [
            "name",
            "fecha",
            "usuario_id",
            "evaluador_id",
            "state",

            "mes",
            "anio",

            "tipo_operativo",

            "dashboard_tipo_operativo_texto",
            "dashboard_periodo",
            "dashboard_unidad_produccion",

            // PRODUCCIÓN

            "meta_taller_ajustada",
            "meta_servicios_ajustada",

            "reparaciones_validas_bono",
            "tickets_validos_bono",

            "porcentaje_produccion_taller",
            "porcentaje_produccion_servicios",
            "porcentaje_produccion_total",

            "dashboard_meta_principal",
            "dashboard_real_principal",

            "dashboard_porcentaje_produccion",

            "dashboard_diferencia_meta",
            "dashboard_faltante_meta",
            "dashboard_exceso_meta",

            "dashboard_cumple_meta",
            "dashboard_cumple_minimo_bono_produccion",

            "dashboard_resumen_produccion",
            "dashboard_detalle_taller",
            "dashboard_detalle_servicios",

            // CALIDAD

            "puntaje_calidad_real",

            "reclamos_procedentes_count",
            "evaluaciones_criticas_count",

            "dashboard_calidad",
            "dashboard_estado_calidad",
            "dashboard_resumen_calidad",
            "dashboard_tiene_reclamos",

            // ENCUESTAS

            "evaluaciones_servicio_count",
            "evaluaciones_servicio_minimas",
            "evaluaciones_servicio_faltantes",
            "cumple_minimo_evaluaciones",
            "promedio_evaluacion_servicio",

            "dashboard_encuestas_aplican",

            "dashboard_encuestas_generadas",
            "dashboard_encuestas_respondidas",
            "dashboard_encuestas_no_respondidas",

            "dashboard_encuestas_requeridas",
            "dashboard_encuestas_faltantes",

            "dashboard_porcentaje_respuesta_encuestas",
            "dashboard_porcentaje_cobertura_minima",

            "dashboard_cumple_encuestas",
            "dashboard_resumen_encuestas",

            // ASISTENCIA

            "puntaje_asistencia_real",
            "puntaje_apoyo_real",

            "faltas_injustificadas_equivalentes",

            "dashboard_asistencia",
            "dashboard_apoyo",
            "dashboard_resumen_asistencia",

            // DISPONIBILIDAD

            "dias_laborables_equivalentes",
            "dias_ausencia_equivalentes",
            "dias_servicio_equivalentes",

            "dias_taller_disponibles",
            "dias_servicios_disponibles",

            "horas_servicio_mes",

            "dashboard_dias_laborables",
            "dashboard_dias_ausencia",
            "dashboard_dias_servicio",
            "dashboard_dias_taller",
            "dashboard_horas_servicio",

            "dashboard_dias_con_actividad",
            "dashboard_dias_sin_actividad",

            "dashboard_porcentaje_dias_activos",
            "dashboard_promedio_por_dia_activo",

            // BONO

            "puntaje_produccion_bono",
            "puntaje_calidad_bono",
            "puntaje_asistencia_bono",
            "puntaje_apoyo_bono",

            "puntaje_total_bono",

            "bono_base",
            "bono_extra_sobreproduccion",

            "monto_acelerador",
            "aplica_acelerador",

            "bono_final",

            "dashboard_aplica_bono",
            "dashboard_bono_bloqueado",

            "dashboard_motivo_bono_corto",
            "dashboard_motivos_bloqueo_bono",

            "dashboard_estado_bono",

            // ESTADO GERENCIAL

            "dashboard_estado",
            "dashboard_requiere_seguimiento",

            "dashboard_prioridad",
            "dashboard_alerta_principal",

            "dashboard_resumen_general",

            "dashboard_color_estado",
            "dashboard_color_produccion",
            "dashboard_color_calidad",
            "dashboard_color_bono",

            "dashboard_icono_estado",

            // EVALUACIÓN INTEGRAL

            "puntaje_total",
            "nivel_desempeno",

            "necesita_capacitacion",

            "fortalezas",
            "areas_mejora",
            "plan_accion",

            // HISTORIAL

            "dashboard_historial_12_meses",
            "dashboard_historial_anual",
        ];
    }

    // ============================================================
    // CARGAR PERIODO DE COMPARACIÓN
    // ============================================================

    async _loadComparisonPeriod(
        month,
        year,
        userIds
    ) {
        if (!userIds.length) {
            return [];
        }

        const range = this._getPeriodRange(
            month,
            year
        );

        const domain = [
            ["fecha", ">=", range.start],
            ["fecha", "<", range.end],
            ["usuario_id", "in", userIds],
        ];

        return await this.orm.searchRead(
            "evaluacion.personal",
            domain,
            [
                "usuario_id",

                "porcentaje_produccion_total",
                "puntaje_calidad_real",
                "bono_final",

                "reparaciones_validas_bono",
                "tickets_validos_bono",

                "meta_taller_ajustada",
                "meta_servicios_ajustada",
            ],
            {
                order: "fecha desc, id desc",
            }
        );
    }

    // ============================================================
    // UNIR COMPARACIONES
    // ============================================================

    _mergeComparisons(
        evaluaciones,
        compare1Records,
        compare2Records
    ) {
        const compare1Map = new Map();
        const compare2Map = new Map();

        for (const item of compare1Records) {
            if (
                item.usuario_id &&
                item.usuario_id[0] &&
                !compare1Map.has(item.usuario_id[0])
            ) {
                compare1Map.set(
                    item.usuario_id[0],
                    item
                );
            }
        }

        for (const item of compare2Records) {
            if (
                item.usuario_id &&
                item.usuario_id[0] &&
                !compare2Map.has(item.usuario_id[0])
            ) {
                compare2Map.set(
                    item.usuario_id[0],
                    item
                );
            }
        }

        for (const ev of evaluaciones) {
            const userId =
                ev.usuario_id &&
                ev.usuario_id[0];

            const compare1 =
                compare1Map.get(userId);

            const compare2 =
                compare2Map.get(userId);

            // -----------------------------------------
            // COMPARACIÓN 1
            // -----------------------------------------

            ev.compare1Disponible = !!compare1;

            ev.compare1Produccion =
                compare1
                    ? Number(
                        compare1.porcentaje_produccion_total || 0
                    )
                    : 0;

            ev.compare1Calidad =
                compare1
                    ? Number(
                        compare1.puntaje_calidad_real || 0
                    )
                    : 0;

            ev.compare1Bono =
                compare1
                    ? Number(
                        compare1.bono_final || 0
                    )
                    : 0;

            ev.compare1Variacion =
                compare1
                    ? (
                        Number(
                            ev.dashboard_porcentaje_produccion || 0
                        ) -
                        Number(
                            compare1.porcentaje_produccion_total || 0
                        )
                    )
                    : null;

            // -----------------------------------------
            // COMPARACIÓN 2
            // -----------------------------------------

            ev.compare2Disponible = !!compare2;

            ev.compare2Produccion =
                compare2
                    ? Number(
                        compare2.porcentaje_produccion_total || 0
                    )
                    : 0;

            ev.compare2Calidad =
                compare2
                    ? Number(
                        compare2.puntaje_calidad_real || 0
                    )
                    : 0;

            ev.compare2Bono =
                compare2
                    ? Number(
                        compare2.bono_final || 0
                    )
                    : 0;

            ev.compare2Variacion =
                compare2
                    ? (
                        Number(
                            ev.dashboard_porcentaje_produccion || 0
                        ) -
                        Number(
                            compare2.porcentaje_produccion_total || 0
                        )
                    )
                    : null;
        }
    }

    // ============================================================
    // CARGA PRINCIPAL
    // ============================================================

    async loadDashboard() {
        this.state.loading = true;

        try {
            const range = this._getPeriodRange(
                this.state.mes,
                this.state.anio
            );

            const domain = [
                ["fecha", ">=", range.start],
                ["fecha", "<", range.end],
            ];

            if (
                this.state.tipoOperativo !== "todos"
            ) {
                domain.push([
                    "tipo_operativo",
                    "=",
                    this.state.tipoOperativo,
                ]);
            }

            const evaluaciones =
                await this.orm.searchRead(
                    "evaluacion.personal",
                    domain,
                    this._getMainFields(),
                    {
                        order:
                            "usuario_id asc, fecha desc",
                    }
                );

            const userIds = evaluaciones
                .filter(
                    (ev) =>
                        ev.usuario_id &&
                        ev.usuario_id[0]
                )
                .map(
                    (ev) => ev.usuario_id[0]
                );

            const [
                compare1Records,
                compare2Records,
            ] = await Promise.all([
                this._loadComparisonPeriod(
                    this.state.compare1Mes,
                    this.state.compare1Anio,
                    userIds
                ),

                this._loadComparisonPeriod(
                    this.state.compare2Mes,
                    this.state.compare2Anio,
                    userIds
                ),
            ]);

            this._mergeComparisons(
                evaluaciones,
                compare1Records,
                compare2Records
            );

            this.state.evaluaciones =
                evaluaciones;

            this._computeDashboard(
                evaluaciones
            );

            this._buildComparisonChart(
                evaluaciones
            );

            if (evaluaciones.length) {
                const selectedStillExists =
                    this.state.selectedEvaluacion &&
                    evaluaciones.find(
                        (item) =>
                            item.id ===
                            this.state
                                .selectedEvaluacion.id
                    );

                if (selectedStillExists) {
                    await this.selectEvaluacion(
                        selectedStillExists
                    );
                } else {
                    await this.selectEvaluacion(
                        evaluaciones[0]
                    );
                }
            } else {
                this.state.selectedEvaluacion =
                    null;

                this.state.detalleDiario = [];
            }
        } catch (error) {
            console.error(
                "Error cargando dashboard gerencial:",
                error
            );

            this.notification.add(
                "No se pudo cargar el dashboard gerencial.",
                {
                    type: "danger",
                }
            );
        } finally {
            this.state.loading = false;
        }
    }

    // ============================================================
    // KPI
    // ============================================================

    _computeDashboard(evaluaciones) {
        const total = evaluaciones.length;

        let cumplenMeta = 0;
        let conBono = 0;

        let produccionTotal = 0;
        let calidadTotal = 0;

        let seguimiento = 0;
        let reclamos = 0;

        let encuestasRespondidas = 0;
        let encuestasRequeridas = 0;

        let compare1Total = 0;
        let compare1Count = 0;

        let compare2Total = 0;
        let compare2Count = 0;

        const perfiles = {
            taller: 0,
            servicios: 0,
            mixto: 0,
        };

        for (const ev of evaluaciones) {
            const produccion =
                Number(
                    ev.dashboard_porcentaje_produccion || 0
                );

            const calidad =
                Number(
                    ev.dashboard_calidad || 0
                );

            produccionTotal += produccion;
            calidadTotal += calidad;

            if (ev.dashboard_cumple_meta) {
                cumplenMeta += 1;
            }

            if (
                Number(ev.bono_final || 0) > 0
            ) {
                conBono += 1;
            }

            if (
                ev.dashboard_requiere_seguimiento
            ) {
                seguimiento += 1;
            }

            reclamos +=
                ev.reclamos_procedentes_count || 0;

            encuestasRespondidas +=
                ev.dashboard_encuestas_respondidas ||
                0;

            encuestasRequeridas +=
                ev.dashboard_encuestas_requeridas ||
                0;

            if (
                ev.compare1Variacion !== null
            ) {
                compare1Total +=
                    ev.compare1Variacion;

                compare1Count += 1;
            }

            if (
                ev.compare2Variacion !== null
            ) {
                compare2Total +=
                    ev.compare2Variacion;

                compare2Count += 1;
            }

            if (
                ev.tipo_operativo &&
                perfiles[
                    ev.tipo_operativo
                ] !== undefined
            ) {
                perfiles[
                    ev.tipo_operativo
                ] += 1;
            }
        }

        this.state.kpis = {
            totalTecnicos: total,

            cumplenMeta,
            noCumplenMeta:
                total - cumplenMeta,

            conBono,
            sinBono:
                total - conBono,

            promedioProduccion:
                total
                    ? produccionTotal / total
                    : 0,

            promedioCalidad:
                total
                    ? calidadTotal / total
                    : 0,

            seguimiento,
            reclamos,

            encuestasRespondidas,
            encuestasRequeridas,

            variacionCompare1:
                compare1Count
                    ? compare1Total /
                        compare1Count
                    : 0,

            variacionCompare2:
                compare2Count
                    ? compare2Total /
                        compare2Count
                    : 0,
        };

        this.state.perfiles =
            perfiles;

        this.state.rankingProduccion =
            [...evaluaciones].sort(
                (a, b) =>
                    Number(
                        b.dashboard_porcentaje_produccion ||
                            0
                    ) -
                    Number(
                        a.dashboard_porcentaje_produccion ||
                            0
                    )
            );

        this.state.rankingCalidad =
            [...evaluaciones].sort(
                (a, b) =>
                    Number(
                        b.dashboard_calidad || 0
                    ) -
                    Number(
                        a.dashboard_calidad || 0
                    )
            );

        this.state.rankingBono =
            [...evaluaciones].sort(
                (a, b) =>
                    Number(
                        b.bono_final || 0
                    ) -
                    Number(
                        a.bono_final || 0
                    )
            );

        this.state.rankingSeguimiento =
            evaluaciones.filter(
                (ev) =>
                    ev.dashboard_requiere_seguimiento
            );
    }

    // ============================================================
    // HISTORIAL MINI GRÁFICO
    // ============================================================

    getMiniHistory(record) {
        const history =
            Array.isArray(
                record.dashboard_historial_12_meses
            )
                ? record.dashboard_historial_12_meses
                : [];

        return [...history]
            .filter(
                (item) =>
                    item &&
                    item.fecha
            )
            .sort(
                (a, b) =>
                    String(a.fecha).localeCompare(
                        String(b.fecha)
                    )
            )
            .slice(-6);
    }

    getMiniChartPoints(record) {
        const history =
            this.getMiniHistory(record);

        if (!history.length) {
            return "";
        }

        const width = 300;
        const height = 72;

        const paddingX = 5;
        const paddingY = 7;

        const values =
            history.map(
                (item) =>
                    Number(
                        item.produccion || 0
                    )
            );

        const maxValue =
            Math.max(
                120,
                ...values
            );

        const range =
            Math.max(
                1,
                maxValue
            );

        const usableWidth =
            width - paddingX * 2;

        const usableHeight =
            height - paddingY * 2;

        const step =
            history.length > 1
                ? usableWidth /
                    (history.length - 1)
                : 0;

        return history
            .map(
                (item, index) => {
                    const value =
                        Number(
                            item.produccion || 0
                        );

                    const x =
                        paddingX +
                        index * step;

                    const normalized =
                        Math.min(
                            range,
                            Math.max(
                                0,
                                value
                            )
                        ) /
                        range;

                    const y =
                        paddingY +
                        usableHeight -
                        normalized *
                            usableHeight;

                    return `${x},${y}`;
                }
            )
            .join(" ");
    }

    getMiniChartDots(record) {
        const history =
            this.getMiniHistory(record);

        if (!history.length) {
            return [];
        }

        const width = 300;
        const height = 72;

        const paddingX = 5;
        const paddingY = 7;

        const values =
            history.map(
                (item) =>
                    Number(
                        item.produccion || 0
                    )
            );

        const maxValue =
            Math.max(
                120,
                ...values
            );

        const range =
            Math.max(
                1,
                maxValue
            );

        const usableWidth =
            width - paddingX * 2;

        const usableHeight =
            height - paddingY * 2;

        const step =
            history.length > 1
                ? usableWidth /
                    (history.length - 1)
                : 0;

        return history.map(
            (item, index) => {
                const value =
                    Number(
                        item.produccion || 0
                    );

                const x =
                    paddingX +
                    index * step;

                const normalized =
                    Math.min(
                        range,
                        Math.max(
                            0,
                            value
                        )
                    ) /
                    range;

                const y =
                    paddingY +
                    usableHeight -
                    normalized *
                        usableHeight;

                return {
                    x,
                    y,
                    value,
                    fecha: item.fecha,
                    label:
                        this.getMiniMonthLabel(
                            item.fecha
                        ),
                };
            }
        );
    }

    getMiniMonthLabel(dateStr) {
        if (!dateStr) {
            return "";
        }

        const date =
            new Date(
                `${dateStr}T00:00:00`
            );

        return date
            .toLocaleDateString(
                "es-PE",
                {
                    month: "short",
                }
            )
            .replace(".", "");
    }

    getMiniChartClass(record) {
        const history =
            this.getMiniHistory(record);

        if (history.length < 2) {
            return "neutral";
        }

        const first =
            Number(
                history[0].produccion || 0
            );

        const last =
            Number(
                history[
                    history.length - 1
                ].produccion || 0
            );

        const variation =
            last - first;

        if (variation >= 5) {
            return "positive";
        }

        if (variation <= -5) {
            return "negative";
        }

        return "neutral";
    }

    getMiniTrendDifference(record) {
        const history =
            this.getMiniHistory(record);

        if (history.length < 2) {
            return 0;
        }

        const first =
            Number(
                history[0].produccion || 0
            );

        const last =
            Number(
                history[
                    history.length - 1
                ].produccion || 0
            );

        return last - first;
    }

    // ============================================================
    // GRÁFICO GRANDE
    // ============================================================

    _buildComparisonChart(evaluaciones) {
        const monthMap = new Map();

        for (const ev of evaluaciones) {
            const history =
                Array.isArray(
                    ev.dashboard_historial_12_meses
                )
                    ? ev.dashboard_historial_12_meses
                    : [];

            for (const item of history) {
                if (!item.fecha) {
                    continue;
                }

                const key =
                    item.fecha.substring(
                        0,
                        7
                    );

                if (!monthMap.has(key)) {
                    monthMap.set(
                        key,
                        {
                            key,
                            fecha:
                                item.fecha,
                        }
                    );
                }
            }
        }

        let months =
            [...monthMap.values()].sort(
                (a, b) =>
                    a.key.localeCompare(
                        b.key
                    )
            );

        if (months.length > 8) {
            months =
                months.slice(-8);
        }

        const monthKeys =
            months.map(
                (item) => item.key
            );

        const series =
            evaluaciones.map(
                (ev, index) => {
                    const history =
                        Array.isArray(
                            ev.dashboard_historial_12_meses
                        )
                            ? ev.dashboard_historial_12_meses
                            : [];

                    const values =
                        monthKeys.map(
                            (key) => {
                                const found =
                                    history.find(
                                        (item) =>
                                            item.fecha &&
                                            item.fecha.substring(
                                                0,
                                                7
                                            ) ===
                                                key
                                    );

                                return found
                                    ? Number(
                                        found.produccion ||
                                            0
                                    )
                                    : null;
                            }
                        );

                    return {
                        id: ev.id,
                        index,
                        name:
                            this.getTecnicoName(
                                ev
                            ),
                        values,
                    };
                }
            );

        this.state.chartMonths =
            months;

        this.state.chartSeries =
            series;
    }

    getChartMonthLabel(month) {
        if (
            !month ||
            !month.fecha
        ) {
            return "";
        }

        const date =
            new Date(
                `${month.fecha}T00:00:00`
            );

        return date
            .toLocaleDateString(
                "es-PE",
                {
                    month: "short",
                    year: "2-digit",
                }
            )
            .replace(".", "");
    }

    getChartPolyline(series) {
        const values =
            series.values || [];

        if (!values.length) {
            return "";
        }

        const width = 1000;

        const usableHeight = 205;
        const top = 20;

        const validValues =
            values.filter(
                (value) =>
                    value !== null
            );

        const maxValue =
            Math.max(
                120,
                ...validValues.map(
                    (value) =>
                        Number(value || 0)
                )
            );

        const step =
            values.length > 1
                ? width /
                    (values.length - 1)
                : width;

        const points = [];

        values.forEach(
            (value, index) => {
                if (value === null) {
                    return;
                }

                const x =
                    index * step;

                const normalized =
                    Math.min(
                        maxValue,
                        Math.max(
                            0,
                            Number(value || 0)
                        )
                    ) /
                    maxValue;

                const y =
                    top +
                    usableHeight -
                    normalized *
                        usableHeight;

                points.push(
                    `${x},${y}`
                );
            }
        );

        return points.join(" ");
    }

    getChartPointX(index) {
        const total =
            this.state.chartMonths.length;

        if (total <= 1) {
            return 0;
        }

        return (
            1000 /
            (total - 1)
        ) * index;
    }

    getChartPointY(value) {
        const allValues = [];

        for (
            const series
            of this.state.chartSeries
        ) {
            for (
                const item
                of series.values || []
            ) {
                if (item !== null) {
                    allValues.push(
                        Number(item || 0)
                    );
                }
            }
        }

        const maxValue =
            Math.max(
                120,
                ...allValues
            );

        const usableHeight = 205;
        const top = 20;

        const normalized =
            Math.min(
                maxValue,
                Math.max(
                    0,
                    Number(value || 0)
                )
            ) /
            maxValue;

        return (
            top +
            usableHeight -
            normalized *
                usableHeight
        );
    }

    // ============================================================
    // DETALLE DIARIO
    // ============================================================

    async selectEvaluacion(ev) {
        this.state.selectedEvaluacion =
            ev;

        await this.loadDetalleDiario(
            ev.id
        );
    }

    async loadDetalleDiario(
        evaluacionId
    ) {
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

                "es_dia_laboral",

                "clientes_atendidos",
                "modelos_trabajados",
                "cantidad_clientes",

                "dashboard_color_estado_dia",
                "dashboard_icono_estado_dia",
                "dashboard_resumen_dia",
                "dashboard_actividad_dia",
                "dashboard_alerta_dia",
            ];

            const detalle =
                await this.orm.searchRead(
                    "evaluacion.personal.detalle.diario",
                    [
                        [
                            "evaluacion_id",
                            "=",
                            evaluacionId,
                        ],
                    ],
                    fields,
                    {
                        order:
                            "fecha asc",
                    }
                );

            this.state.detalleDiario =
                detalle;
        } catch (error) {
            console.error(
                "Error cargando detalle diario:",
                error
            );

            this.notification.add(
                "No se pudo cargar el detalle diario.",
                {
                    type: "warning",
                }
            );
        } finally {
            this.state.loadingDetalle =
                false;
        }
    }

    // ============================================================
    // HELPERS
    // ============================================================

    getTecnicoName(record) {
        return (
            record.usuario_id &&
            record.usuario_id[1]
        )
            ? record.usuario_id[1]
            : "Sin técnico";
    }

    getPercent(value) {
        return Number(
            value || 0
        ).toFixed(1);
    }

    getFloat(value) {
        return Number(
            value || 0
        ).toFixed(2);
    }

    getMoney(value) {
        return (
            `S/ ${Number(
                value || 0
            ).toFixed(2)}`
        );
    }

    getSigned(value) {
        if (
            value === null ||
            value === undefined
        ) {
            return "-";
        }

        const number =
            Number(value || 0);

        if (number > 0) {
            return (
                `+${number.toFixed(1)}`
            );
        }

        return number.toFixed(1);
    }

    getBarWidth(value) {
        return (
            `width: ${Math.min(
                100,
                Math.max(
                    0,
                    Number(value || 0)
                )
            )}%`
        );
    }

    getProductionClass(value) {
        const number =
            Number(value || 0);

        if (number >= 100) {
            return "success";
        }

        if (number >= 95) {
            return "primary";
        }

        if (number >= 80) {
            return "warning";
        }

        return "danger";
    }

    getQualityClass(value) {
        const number =
            Number(value || 0);

        if (number >= 90) {
            return "success";
        }

        if (number >= 80) {
            return "primary";
        }

        if (number >= 70) {
            return "warning";
        }

        return "danger";
    }

    getComparisonClass(
        available,
        variation
    ) {
        if (!available) {
            return "neutral";
        }

        const value =
            Number(
                variation || 0
            );

        if (value > 0) {
            return "positive";
        }

        if (value < 0) {
            return "negative";
        }

        return "neutral";
    }

    getStateLabel(state) {
        const labels = {
            sin_datos:
                "Sin datos",

            critico:
                "Crítico",

            requiere_revision:
                "Requiere revisión",

            en_observacion:
                "En observación",

            estable:
                "Estable",

            destacado:
                "Destacado",
        };

        return (
            labels[state] ||
            "Sin datos"
        );
    }

    getTipoLabel(tipo) {
        const labels = {
            taller:
                "Técnico de Taller",

            servicios:
                "Servicios / Alquiler",

            mixto:
                "Técnico Mixto",
        };

        return (
            labels[tipo] ||
            "Sin perfil"
        );
    }

    getInitials(record) {
        const name =
            this.getTecnicoName(record);

        const pieces =
            name
                .trim()
                .split(/\s+/)
                .filter(Boolean);

        if (!pieces.length) {
            return "T";
        }

        if (pieces.length === 1) {
            return pieces[0]
                .substring(0, 2)
                .toUpperCase();
        }

        return (
            pieces[0][0] +
            pieces[1][0]
        ).toUpperCase();
    }

    // ============================================================
    // CAMBIOS FILTRO PRINCIPAL
    // ============================================================

    onChangeMonth(event) {
        this.state.mes =
            Number(
                event.target.value
            );
    }

    onChangeYear(event) {
        this.state.anio =
            Number(
                event.target.value
            );
    }

    onChangeTipo(event) {
        this.state.tipoOperativo =
            event.target.value;
    }

    // ============================================================
    // CAMBIOS COMPARACIÓN 1
    // ============================================================

    onChangeCompare1Month(event) {
        this.state.compare1Mes =
            Number(
                event.target.value
            );
    }

    onChangeCompare1Year(event) {
        this.state.compare1Anio =
            Number(
                event.target.value
            );
    }

    // ============================================================
    // CAMBIOS COMPARACIÓN 2
    // ============================================================

    onChangeCompare2Month(event) {
        this.state.compare2Mes =
            Number(
                event.target.value
            );
    }

    onChangeCompare2Year(event) {
        this.state.compare2Anio =
            Number(
                event.target.value
            );
    }

    // ============================================================
    // APLICAR
    // ============================================================

    async onApplyFilter() {
        await this.loadDashboard();
    }

    async setCurrentMonth() {
        const today =
            new Date();

        const currentMonth =
            today.getMonth() + 1;

        const currentYear =
            today.getFullYear();

        const previous =
            this._getPreviousMonth(
                currentMonth,
                currentYear
            );

        this.state.mes =
            currentMonth;

        this.state.anio =
            currentYear;

        this.state.compare1Mes =
            previous.month;

        this.state.compare1Anio =
            previous.year;

        this.state.compare2Mes =
            currentMonth;

        this.state.compare2Anio =
            currentYear - 1;

        await this.loadDashboard();
    }

    // ============================================================
    // ACCIONES
    // ============================================================

    async openEvaluaciones() {
        await this.action.doAction(
            "sat.action_evaluacion_personal"
        );
    }

    async openEvaluacion(record) {
        await this.action.doAction({
            type:
                "ir.actions.act_window",

            name:
                "Evaluación de Personal",

            res_model:
                "evaluacion.personal",

            res_id:
                record.id,

            views:
                [[false, "form"]],

            target:
                "current",
        });
    }

    async openDetalleDiario(record) {
        await this.action.doAction({
            type:
                "ir.actions.act_window",

            name:
                `Detalle Diario - ${this.getTecnicoName(record)}`,

            res_model:
                "evaluacion.personal.detalle.diario",

            views: [
                [false, "list"],
                [false, "form"],
                [false, "pivot"],
                [false, "graph"],
            ],

            domain: [
                [
                    "evaluacion_id",
                    "=",
                    record.id,
                ],
            ],

            target:
                "current",
        });
    }

    async _callDashboardAction(
        record,
        method
    ) {
        if (
            !record ||
            !record.id
        ) {
            return;
        }

        try {
            const result =
                await this.orm.call(
                    "evaluacion.personal",
                    method,
                    [[record.id]]
                );

            if (result) {
                await this.action.doAction(
                    result
                );
            }
        } catch (error) {
            console.error(
                `Error ejecutando ${method}:`,
                error
            );

            this.notification.add(
                "No se pudo abrir la información solicitada.",
                {
                    type: "warning",
                }
            );
        }
    }

    async openReclamos(record) {
        await this._callDashboardAction(
            record,
            "action_dashboard_ver_reclamos"
        );
    }

    async openEncuestas(record) {
        await this._callDashboardAction(
            record,
            "action_dashboard_ver_todas_encuestas"
        );
    }

    async openHistorial(record) {
        await this._callDashboardAction(
            record,
            "action_dashboard_ver_historial"
        );
    }

    async openFilteredEvaluaciones(
        domain,
        name
    ) {
        await this.action.doAction({
            type:
                "ir.actions.act_window",

            name:
                name || "Evaluaciones",

            res_model:
                "evaluacion.personal",

            views: [
                [false, "list"],
                [false, "form"],
                [false, "kanban"],
                [false, "pivot"],
                [false, "graph"],
            ],

            domain,

            target:
                "current",
        });
    }

    async openSeguimiento() {
        await this.openFilteredEvaluaciones(
            [
                [
                    "dashboard_requiere_seguimiento",
                    "=",
                    true,
                ],
            ],
            "Personal que requiere seguimiento"
        );
    }

    async openConBono() {
        await this.openFilteredEvaluaciones(
            [
                [
                    "bono_final",
                    ">",
                    0,
                ],
            ],
            "Personal con bono"
        );
    }

    async openCumplenMeta() {
        await this.openFilteredEvaluaciones(
            [
                [
                    "dashboard_cumple_meta",
                    "=",
                    true,
                ],
            ],
            "Personal que cumple meta"
        );
    }
}


registry
    .category("actions")
    .add(
        "evaluacion_personal_dashboard_tag",
        EvaluacionPersonalDashboard
    );