/** @odoo-module **/
import { registry } from "@web/core/registry";
import { StatusBar } from "@web/views/fields/status_bar/status_bar";

registry.category("fields").add("colored_statusbar", StatusBar.extend({
    _render() {
        this._super.apply(this, arguments);

        // Limpiar clases previas
        this.el.classList.remove("estado-sin_revisar", "estado-para_revision", "estado-asignado",
                                 "estado-en_revision", "estado-finalizado", "estado-con_problemas",
                                 "estado-de_partes", "estado-entregada");

        // Agregar clase basada en el valor del estado
        if (this.value) {
            this.el.classList.add(`estado-${this.value}`);
        }
    },
}));
