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

    get tonerCards() {
        return [
            {
                key: "negro",
                label: "Negro",
                code: "K",
                value: this._safePercent(this.ultima.toner_negro),
                className: "sat_toner_k",
            },
            {
                key: "cyan",
                label: "Cyan",
                code: "C",
                value: this._safePercent(this.ultima.toner_cyan),
                className: "sat_toner_c",
            },
            {
                key: "magenta",
                label: "Magenta",
                code: "M",
                value: this._safePercent(this.ultima.toner_magenta),
                className: "sat_toner_m",
            },
            {
                key: "amarillo",
                label: "Amarillo",
                code: "Y",
                value: this._safePercent(this.ultima.toner_amarillo),
                className: "sat_toner_y",
            },
        ];
    }

    get pruebaChecks() {
        return [
            {
                label: "Impresión",
                value: this.ultima.prueba_impresion_ok,
            },
            {
                label: "Copia",
                value: this.ultima.prueba_copia_ok,
            },
            {
                label: "Scanner",
                value: this.ultima.prueba_scanner_ok,
            },
            {
                label: "Dúplex",
                value: this.ultima.prueba_duplex_ok,
            },
            {
                label: "B/N",
                value: this.ultima.prueba_bn_ok,
            },
            {
                label: "Color",
                value: this.ultima.prueba_color_ok,
            },
        ];
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

    formatNumber(value) {
        const numberValue = Number(value || 0);
        return new Intl.NumberFormat("es-PE").format(numberValue);
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