/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Field } from "@web/views/fields/field";

export class StatusWidget extends Field {
    static template = "StatusWidgetTemplate";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        super.setup();
        this.status_colors = {
            'sin_revisar': '#808080',
            'para_revision': '#3498db',
            'asignado': '#f39c12',
            'en_revision': '#f1c40f',
            'finalizado': '#2ecc71',
            'con_problemas': '#e74c3c',
            'de_partes': '#9b59b6',
            'entregada': '#1abc9c'
        };
    }

    getStatusColor(value) {
        return this.status_colors[value] || '#808080';
    }

    async onChange(newValue) {
        await this.props.update(newValue);
    }

    onClickStatus() {
        if (!this.props.readonly) {
            const dropdown = this.el.querySelector('.status-dropdown');
            if (dropdown) {
                dropdown.classList.toggle('show');
            }
        }
    }
}

export const statusWidget = {
    component: StatusWidget,
    supportedTypes: ["selection"],
};

registry.category("fields").add("status_widget", statusWidget);