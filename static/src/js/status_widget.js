/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Field } from "@web/views/fields/field";
const { Component } = owl;

export class StatusField extends Component {
    static template = 'FieldStatusWidget';
    
    setup() {
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

    getStatusLabel(value) {
        const selection = this.props.record.field.selection;
        const option = selection.find(opt => opt[0] === value);
        return option ? option[1] : '';
    }

    async onStatusClick(newValue) {
        if (!this.props.readonly) {
            await this.props.update(newValue);
        }
    }

    toggleDropdown(ev) {
        if (!this.props.readonly) {
            const dropdown = ev.target.closest('.status-widget').querySelector('.status-dropdown');
            if (dropdown) {
                dropdown.classList.toggle('show');
                
                // Cerrar al hacer clic fuera
                const closeDropdown = (e) => {
                    if (!e.target.closest('.status-widget')) {
                        dropdown.classList.remove('show');
                        document.removeEventListener('click', closeDropdown);
                    }
                };
                
                document.addEventListener('click', closeDropdown);
            }
        }
    }
}

export const statusWidget = {
    component: StatusField,
    supportedTypes: ["selection"],
};

registry.category("fields").add("status_widget", statusWidget);