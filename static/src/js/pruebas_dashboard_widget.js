/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class SatPruebasDashboardWidget extends Component {
    static template = "sat.SatPruebasDashboardWidget";
    static props = {
        ...standardFieldProps,
    };

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

    get isColorMachine() {
        return this.data.es_color === true || this.data.tipo_id === "color";
    }

    get isBwMachine() {
        return !this.isColorMachine;
    }

    get totalPruebas() {
        return this.data.total_pruebas || 0;
    }

    get estadoGeneralClass() {
        const estado = this.ultima.estado_prueba || "pendiente";
        return `sat_estado_${estado}`;
    }

    get tonerGeneralClass() {
        const estado = this.ultima.estado_toner || "sin_datos";
        return `sat_toner_${estado}`;
    }

    get machineTypeLabel() {
        return this.isColorMachine ? "Color" : "B/N";
    }

    get tonerCards() {
        const cards = [
            {
                key: "negro",
                label: "Negro",
                code: "K",
                value: this._safePercent(this.ultima.toner_negro),
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
                    className: "sat_toner_c",
                    description: "Color cyan",
                },
                {
                    key: "magenta",
                    label: "Magenta",
                    code: "M",
                    value: this._safePercent(this.ultima.toner_magenta),
                    className: "sat_toner_m",
                    description: "Color magenta",
                },
                {
                    key: "amarillo",
                    label: "Amarillo",
                    code: "Y",
                    value: this._safePercent(this.ultima.toner_amarillo),
                    className: "sat_toner_y",
                    description: "Color amarillo",
                }
            );
        }

        return cards;
    }

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
            },
            {
                key: "delta_total",
                icon: "fa-line-chart",
                label: "Δ Total",
                value: this.ultima.delta_total,
                footer: "Diferencia desde inicio",
                main: false,
                delta: true,
            },
            {
                key: "copias",
                icon: "fa-copy",
                label: "Copias",
                value: this.ultima.contador_copias,
                footer: `Δ ${this.formatDelta(this.ultima.delta_copias)}`,
                main: false,
                delta: false,
            },
            {
                key: "impresiones",
                icon: "fa-print",
                label: "Impresiones",
                value: this.ultima.contador_impresiones,
                footer: `Δ ${this.formatDelta(this.ultima.delta_impresiones)}`,
                main: false,
                delta: false,
            },
            {
                key: "scanner",
                icon: "fa-file-text-o",
                label: "Scanner",
                value: this.ultima.contador_scanner,
                footer: `Δ ${this.formatDelta(this.ultima.delta_scanner)}`,
                main: false,
                delta: false,
            },
            {
                key: "duplex",
                icon: "fa-columns",
                label: "Dúplex",
                value: this.ultima.contador_duplex,
                footer: `Δ ${this.formatDelta(this.ultima.delta_duplex)}`,
                main: false,
                delta: false,
            },
            {
                key: "bn",
                icon: "fa-adjust",
                label: "B/N",
                value: this.ultima.contador_actual_bn,
                footer: `Δ ${this.formatDelta(this.ultima.delta_bn)}`,
                main: false,
                delta: false,
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
            });
        }

        return base;
    }

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
}

registry.category("fields").add("sat_pruebas_dashboard", {
    component: SatPruebasDashboardWidget,
});