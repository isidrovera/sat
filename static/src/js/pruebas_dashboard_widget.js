/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class SatPruebasDashboardWidget extends Component {
    static template = "sat.SatPruebasDashboardWidget";
    static props = {
        ...standardFieldProps,
    };

    // ==========================================================
    // DATA BASE
    // ==========================================================

    get rawValue() {
        return this.props.record.data[this.props.name] || "{}";
    }

    get data() {
        try {
            return JSON.parse(this.rawValue || "{}");
        } catch (error) {
            return {};
        }
    }

    get pruebas() {
        return this.data.items || [];
    }

    get ultima() {
        return this.data.ultima || {};
    }

    get hasData() {
        return this.pruebas.length > 0;
    }

    get totalPruebas() {
        return this.data.total_pruebas || 0;
    }

    // ==========================================================
    // TIPO DE MÁQUINA
    // ==========================================================

    get isColorMachine() {
        return this.data.es_color === true || this.data.tipo_id === "color";
    }

    get isBwMachine() {
        return !this.isColorMachine;
    }

    get machineTypeLabel() {
        return this.data.machine_type_label || (this.isColorMachine ? "Color" : "B/N");
    }

    get machineTypeIcon() {
        return this.isColorMachine ? "fa-tint" : "fa-adjust";
    }

    get machineTypeClass() {
        return this.isColorMachine ? "sat_machine_color" : "sat_machine_bn";
    }

    // ==========================================================
    // ESTADOS
    // ==========================================================

    get estadoGeneralClass() {
        const estado = this.ultima.estado_prueba || "pendiente";
        return `sat_estado_${estado}`;
    }

    get tonerGeneralClass() {
        const estado = this.ultima.estado_toner || "sin_datos";
        return `sat_toner_${estado}`;
    }

    get alertasCount() {
        return Number(this.ultima.cantidad_alertas_snmp || 0);
    }

    get hasAlertas() {
        return this.alertasCount > 0;
    }

    // ==========================================================
    // TÓNER
    // ==========================================================

    get tonerCards() {
        if (Array.isArray(this.ultima.toner_cards) && this.ultima.toner_cards.length) {
            return this.ultima.toner_cards.map((item) => ({
                key: item.key,
                label: item.label,
                code: item.code,
                value: this._safePercent(item.value),
                estado: item.estado || this._estadoByPercent(item.value),
                className: item.className || this._tonerClassByKey(item.key),
                description: item.description || "",
            }));
        }

        const cards = [
            {
                key: "negro",
                label: "Negro",
                code: "K",
                value: this._safePercent(this.ultima.toner_negro),
                estado: this._estadoByPercent(this.ultima.toner_negro),
                className: "sat_toner_k",
                description: "Tóner principal",
            },
        ];

        if (this.isColorMachine) {
            cards.push(
                {
                    key: "cyan",
                    label: "Cyan",
                    code: "C",
                    value: this._safePercent(this.ultima.toner_cyan),
                    estado: this._estadoByPercent(this.ultima.toner_cyan),
                    className: "sat_toner_c",
                    description: "Color cyan",
                },
                {
                    key: "magenta",
                    label: "Magenta",
                    code: "M",
                    value: this._safePercent(this.ultima.toner_magenta),
                    estado: this._estadoByPercent(this.ultima.toner_magenta),
                    className: "sat_toner_m",
                    description: "Color magenta",
                },
                {
                    key: "amarillo",
                    label: "Amarillo",
                    code: "Y",
                    value: this._safePercent(this.ultima.toner_amarillo),
                    estado: this._estadoByPercent(this.ultima.toner_amarillo),
                    className: "sat_toner_y",
                    description: "Color amarillo",
                }
            );
        }

        return cards;
    }

    get tonerMinimo() {
        const valid = this.tonerCards
            .map((t) => Number(t.value || 0))
            .filter((v) => v > 0);

        if (!valid.length) {
            return 0;
        }

        return Math.min(...valid);
    }

    get tonerResumenTexto() {
        if (!this.tonerCards.length) {
            return "Sin datos de tóner";
        }

        if (this.isColorMachine) {
            return "Mostrando K, C, M y Y porque la máquina es color.";
        }

        return "Mostrando solo tóner negro porque la máquina es monocromática.";
    }

    _tonerClassByKey(key) {
        const map = {
            negro: "sat_toner_k",
            black: "sat_toner_k",
            k: "sat_toner_k",
            cyan: "sat_toner_c",
            c: "sat_toner_c",
            magenta: "sat_toner_m",
            m: "sat_toner_m",
            amarillo: "sat_toner_y",
            yellow: "sat_toner_y",
            y: "sat_toner_y",
        };

        return map[key] || "sat_toner_k";
    }

    // ==========================================================
    // CONTADORES
    // ==========================================================

    get counters() {
        const base = [
            {
                key: "actual",
                icon: "fa-tachometer",
                label: "Contador actual",
                value: this.ultima.contador_actual_total,
                footer: `Inicial: ${this.formatNumber(this.ultima.contador_inicial_total)}`,
                main: true,
                delta: false,
                accent: "blue",
            },
            {
                key: "delta_total",
                icon: "fa-line-chart",
                label: "Δ Total",
                value: this.ultima.delta_total,
                footer: "Diferencia desde inicio",
                main: false,
                delta: true,
                accent: "green",
            },
            {
                key: "copias",
                icon: "fa-copy",
                label: "Copias",
                value: this.ultima.contador_copias,
                footer: `Δ ${this.formatDelta(this.ultima.delta_copias)}`,
                main: false,
                delta: false,
                accent: "slate",
            },
            {
                key: "impresiones",
                icon: "fa-print",
                label: "Impresiones",
                value: this.ultima.contador_impresiones,
                footer: `Δ ${this.formatDelta(this.ultima.delta_impresiones)}`,
                main: false,
                delta: false,
                accent: "purple",
            },
            {
                key: "scanner",
                icon: "fa-file-text-o",
                label: "Scanner",
                value: this.ultima.contador_scanner,
                footer: `Δ ${this.formatDelta(this.ultima.delta_scanner)}`,
                main: false,
                delta: false,
                accent: "cyan",
            },
            {
                key: "duplex",
                icon: "fa-columns",
                label: "Dúplex",
                value: this.ultima.contador_duplex,
                footer: `Δ ${this.formatDelta(this.ultima.delta_duplex)}`,
                main: false,
                delta: false,
                accent: "orange",
            },
            {
                key: "bn",
                icon: "fa-adjust",
                label: "B/N",
                value: this.ultima.contador_actual_bn,
                footer: `Δ ${this.formatDelta(this.ultima.delta_bn)}`,
                main: false,
                delta: false,
                accent: "dark",
            },
        ];

        if (this.isColorMachine) {
            base.push({
                key: "color",
                icon: "fa-tint",
                label: "Color",
                value: this.ultima.contador_actual_color,
                footer: `Δ ${this.formatDelta(this.ultima.delta_color)}`,
                main: false,
                delta: false,
                accent: "pink",
            });
        }

        return base;
    }

    // ==========================================================
    // VALIDACIONES
    // ==========================================================

    get pruebaChecks() {
        const checks = [
            {
                key: "impresion",
                icon: "fa-print",
                label: "Impresión",
                value: this.ultima.prueba_impresion_ok,
            },
            {
                key: "copia",
                icon: "fa-copy",
                label: "Copia",
                value: this.ultima.prueba_copia_ok,
            },
            {
                key: "scanner",
                icon: "fa-file-text-o",
                label: "Scanner",
                value: this.ultima.prueba_scanner_ok,
            },
            {
                key: "duplex",
                icon: "fa-columns",
                label: "Dúplex",
                value: this.ultima.prueba_duplex_ok,
            },
            {
                key: "bn",
                icon: "fa-adjust",
                label: "B/N",
                value: this.ultima.prueba_bn_ok,
            },
        ];

        if (this.isColorMachine) {
            checks.push({
                key: "color",
                icon: "fa-tint",
                label: "Color",
                value: this.ultima.prueba_color_ok,
            });
        }

        return checks;
    }

    get checksOkCount() {
        return this.pruebaChecks.filter((c) => c.value).length;
    }

    get checksTotalCount() {
        return this.pruebaChecks.length;
    }

    // ==========================================================
    // COMPONENTES SNMP
    // ==========================================================

    get componentesSnmp() {
        return this.ultima.componentes_snmp || [];
    }

    get hasComponentesSnmp() {
        return this.componentesSnmp.length > 0;
    }

    get unidadesSnmp() {
        return this.ultima.unidades_snmp || [];
    }

    get consumiblesSnmp() {
        return this.ultima.consumibles_snmp || [];
    }

    get accesoriosSnmp() {
        return this.ultima.accesorios_snmp || [];
    }

    get sistemaSnmp() {
        return this.ultima.sistema_snmp || [];
    }

    get hasUnidadesSnmp() {
        return this.unidadesSnmp.length > 0;
    }

    get hasConsumiblesSnmp() {
        return this.consumiblesSnmp.length > 0;
    }

    get hasAccesoriosSnmp() {
        return this.accesoriosSnmp.length > 0;
    }

    get hasSistemaSnmp() {
        return this.sistemaSnmp.length > 0;
    }

    get componentesResumen() {
        return [
            {
                key: "unidades",
                label: "Unidades",
                value: this.unidadesSnmp.length,
                icon: "fa-cogs",
                className: "sat_component_summary_units",
            },
            {
                key: "consumibles",
                label: "Consumibles",
                value: this.consumiblesSnmp.length,
                icon: "fa-flask",
                className: "sat_component_summary_supplies",
            },
            {
                key: "accesorios",
                label: "Accesorios",
                value: this.accesoriosSnmp.length,
                icon: "fa-puzzle-piece",
                className: "sat_component_summary_accessories",
            },
            {
                key: "sistema",
                label: "Sistema",
                value: this.sistemaSnmp.length,
                icon: "fa-hdd-o",
                className: "sat_component_summary_system",
            },
        ].filter((item) => item.value > 0);
    }

    get hasComponentesResumen() {
        return this.componentesResumen.length > 0;
    }

    componentCardClass(item) {
        const css = item.css_class || `sat_component_${item.tipo_visual || "other"}`;
        const level = this.getComponentLevelClass(item.valor, item.estado);
        return `sat_component_card ${css} ${level}`;
    }

    getComponentLevelClass(value, estado = null) {
        if (estado) {
            return `sat_component_${estado}`;
        }

        const percent = this._safePercent(value);

        if (percent <= 0) {
            return "sat_component_sin_datos";
        }

        if (percent <= 10) {
            return "sat_component_critico";
        }

        if (percent <= 25) {
            return "sat_component_bajo";
        }

        return "sat_component_ok";
    }

    getComponentEstadoLabel(item) {
        const estado = item.estado || this._estadoByPercent(item.valor);

        const labels = {
            ok: "OK",
            bajo: "Bajo",
            critico: "Crítico",
            sin_datos: "Sin dato",
            info: "Info",
        };

        return labels[estado] || "Info";
    }

    getComponentValue(item) {
        const value = Number(item.valor || 0);

        if (Number.isNaN(value)) {
            return 0;
        }

        return value;
    }

    getComponentBarStyle(item) {
        const value = item.valor_percent !== undefined ? item.valor_percent : item.valor;
        return this.percentStyle(value);
    }

    getComponentIcon(item) {
        return item.icono || "fa-cube";
    }

    getComponentTypeLabel(item) {
        return item.tipo_label || "Componente";
    }

    hasComponentPercent(item) {
        const value = Number(item.valor || 0);
        const unit = String(item.unidad || "").toLowerCase();

        if (unit.includes("%") || unit.includes("percent")) {
            return true;
        }

        return value >= 0 && value <= 100;
    }

    componentUnit(item) {
        return item.unidad || "%";
    }

    componentSource(item) {
        return item.source_name || item.oid || "";
    }

    // ==========================================================
    // HELPERS FORMATO
    // ==========================================================

    _safePercent(value) {
        const numberValue = Number(value || 0);

        if (Number.isNaN(numberValue)) {
            return 0;
        }

        if (numberValue < 0) {
            return 0;
        }

        if (numberValue > 100) {
            return 100;
        }

        return Math.round(numberValue);
    }

    _estadoByPercent(value) {
        const percent = this._safePercent(value);

        if (percent <= 0) {
            return "sin_datos";
        }

        if (percent <= 10) {
            return "critico";
        }

        if (percent <= 25) {
            return "bajo";
        }

        return "ok";
    }

    getTonerLevelClass(value) {
        const percent = this._safePercent(value);

        if (percent <= 0) {
            return "sat_level_empty";
        }

        if (percent <= 10) {
            return "sat_level_critical";
        }

        if (percent <= 25) {
            return "sat_level_low";
        }

        return "sat_level_ok";
    }

    getTonerMessage(value) {
        const percent = this._safePercent(value);

        if (percent <= 0) {
            return "Sin lectura";
        }

        if (percent <= 10) {
            return "Crítico";
        }

        if (percent <= 25) {
            return "Bajo";
        }

        return "Correcto";
    }

    formatNumber(value) {
        const numberValue = Number(value || 0);
        return new Intl.NumberFormat("es-PE").format(numberValue);
    }

    formatDecimal(value, digits = 0) {
        const numberValue = Number(value || 0);

        if (Number.isNaN(numberValue)) {
            return "0";
        }

        return new Intl.NumberFormat("es-PE", {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        }).format(numberValue);
    }

    formatValue(value, isDelta = false) {
        if (isDelta) {
            return this.formatDelta(value);
        }

        return this.formatNumber(value);
    }

    formatDelta(value) {
        const numberValue = Number(value || 0);

        if (numberValue > 0) {
            return `+${this.formatNumber(numberValue)}`;
        }

        return this.formatNumber(numberValue);
    }

    percentStyle(value) {
        const safe = this._safePercent(value);
        return `width:${safe}%`;
    }

    circleStyle(value) {
        const safe = this._safePercent(value);
        return `--sat-percent:${safe}`;
    }

    componentCircleStyle(item) {
        const safe = this._safePercent(item.valor_percent !== undefined ? item.valor_percent : item.valor);
        return `--sat-percent:${safe}`;
    }
}

registry.category("fields").add("sat_pruebas_dashboard", {
    component: SatPruebasDashboardWidget,
});