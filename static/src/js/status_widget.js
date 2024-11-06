/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Field } from "@web/views/fields/field";
const { Component } = owl;

export class StatusField extends Component {
    static template = 'sat.StatusField';
    
    setup() {
        this.status_config = {
            'sin_revisar': {
                color: '#E0E0E0',
                icon: 'fa-clock-o',
                bgColor: '#F5F5F5'
            },
            'para_revision': {
                color: '#3498db',
                icon: 'fa-search',
                bgColor: '#EBF5FB'
            },
            'asignado': {
                color: '#f39c12',
                icon: 'fa-user',
                bgColor: '#FEF5E7'
            },
            'en_revision': {
                color: '#f1c40f',
                icon: 'fa-cogs',
                bgColor: '#FEF9E7'
            },
            'finalizado': {
                color: '#2ecc71',
                icon: 'fa-check-circle',
                bgColor: '#E8F8F5'
            },
            'con_problemas': {
                color: '#e74c3c',
                icon: 'fa-exclamation-triangle',
                bgColor: '#FDEDEC'
            },
            'de_partes': {
                color: '#9b59b6',
                icon: 'fa-puzzle-piece',
                bgColor: '#F4ECF7'
            },
            'entregada': {
                color: '#1abc9c',
                icon: 'fa-handshake-o',
                bgColor: '#E8F6F3'
            }
        };
    }

    getStatusConfig(value) {
        return this.status_config[value] || this.status_config.sin_revisar;
    }

    getStatusLabel(value) {
        const selection = this.props.record.field.selection;
        const option = selection.find(opt => opt[0] === value);
        return option ? option[1] : '';
    }

    isActiveStatus(currentValue, optionValue) {
        const selection = this.props.record.field.selection;
        const currentIndex = selection.findIndex(opt => opt[0] === currentValue);
        const optionIndex = selection.findIndex(opt => opt[0] === optionValue);
        return optionIndex <= currentIndex;
    }

    async onStatusClick(newValue) {
        if (!this.props.readonly) {
            await this.props.update(newValue);
        }
    }
}

registry.category("fields").add("status_widget", {
    component: StatusField,
    supportedTypes: ["selection"],
});