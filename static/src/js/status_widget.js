/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Field } from "@web/views/fields/field";

class StatusWidget extends Field {
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

    get statusColor() {
        return this.status_colors[this.props.value] || '#808080';
    }

    async onChange(newValue) {
        await this.props.update(newValue);
    }

    toggleDropdown() {
        if (!this.props.readonly) {
            const dropdown = this.el.querySelector('.status-dropdown');
            dropdown.classList.toggle('show');
        }
    }
}

StatusWidget.template = 'StatusWidgetTemplate';
StatusWidget.props = {
    ...standardFieldProps,
    record: { type: Object },
};

StatusWidget.supportedTypes = ['selection'];

registry.category("fields").add("status_widget", StatusWidget);

export default StatusWidget;