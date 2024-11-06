/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Field } from "@web/views/fields/field";

class StatusWidget extends Field {
    setup() {
        super.setup();
        this.status_config = {
            'sin_revisar': {
                color: '#E0E0E0',
                icon: 'fa fa-clock-o',
                bgColor: '#F5F5F5',
                label: 'Sin Revisar'
            },
            'para_revision': {
                color: '#3498db',
                icon: 'fa fa-search',
                bgColor: '#EBF5FB',
                label: 'Para Revisión'
            },
            'asignado': {
                color: '#f39c12',
                icon: 'fa fa-user',
                bgColor: '#FEF5E7',
                label: 'Asignado'
            },
            'en_revision': {
                color: '#f1c40f',
                icon: 'fa fa-cogs',
                bgColor: '#FEF9E7',
                label: 'En Revisión'
            },
            'finalizado': {
                color: '#2ecc71',
                icon: 'fa fa-check-circle',
                bgColor: '#E8F8F5',
                label: 'Finalizado'
            },
            'con_problemas': {
                color: '#e74c3c',
                icon: 'fa fa-exclamation-triangle',
                bgColor: '#FDEDEC',
                label: 'Con Problemas'
            },
            'de_partes': {
                color: '#9b59b6',
                icon: 'fa fa-puzzle-piece',
                bgColor: '#F4ECF7',
                label: 'De Partes'
            },
            'entregada': {
                color: '#1abc9c',
                icon: 'fa fa-handshake-o',
                bgColor: '#E8F6F3',
                label: 'Entregada'
            }
        };
    }

    getStatusConfig(value) {
        return this.status_config[value] || this.status_config['sin_revisar'];
    }

    async _onStatusClick(value) {
        if (!this.props.readonly) {
            await this.props.update(value);
        }
    }
}

StatusWidget.template = 'sat.StatusWidget';
StatusWidget.props = {
    ...standardFieldProps,
};
StatusWidget.supportedTypes = ['selection'];

registry.category("fields").add("status_widget", StatusWidget);

export default StatusWidget;
