/** @odoo-module **/

import { registry } from "@web/core/registry";
import { StatusBar } from "@web/views/fields/status_bar/status_bar";

export class ColoredStatusBar extends StatusBar {
    setup() {
        super.setup();
    }

    get colorClass() {
        const value = this.props.value;
        if (!value) return '';
        return `estado-${value}`;
    }

    // Override del método de renderizado
    onPatched() {
        super.onPatched();
        
        // Remover clases anteriores
        this.el.classList.remove(
            "estado-sin_revisar",
            "estado-para_revision",
            "estado-asignado",
            "estado-en_revision",
            "estado-finalizado",
            "estado-con_problemas",
            "estado-de_partes",
            "estado-entregada"
        );

        // Agregar la nueva clase
        if (this.props.value) {
            this.el.classList.add(`estado-${this.props.value}`);
        }
    }
}

// Registrar el campo personalizado
registry.category("fields").add("colored_statusbar", ColoredStatusBar);