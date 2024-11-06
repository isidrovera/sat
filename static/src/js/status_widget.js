/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Field } from "@web/views/fields/field";

class StatusWidget extends Field {
    static props = {
        ...standardFieldProps,
    };

    static template = "sat.StatusWidget";
    
    static supportedTypes = ["selection"];

    setup() {
        console.log('StatusWidget: Iniciando setup');
        super.setup();
        
        // Log las props completas para debugging
        console.log('StatusWidget: Props completas:', JSON.stringify(this.props, null, 2));
        
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

    get options() {
        console.log('StatusWidget: Obteniendo opciones');
        if (!this.props.record || !this.props.name) {
            console.warn('StatusWidget: Record o name no disponible');
            return [];
        }
        const field = this.props.record.fields[this.props.name];
        console.log('StatusWidget: Field obtenido:', field);
        return field?.selection || [];
    }

    getStatusConfig(value) {
        console.log('StatusWidget: getStatusConfig llamado con valor:', value);
        return this.status_config[value] || this.status_config['sin_revisar'];
    }

    getValue() {
        console.log('StatusWidget: Obteniendo valor actual');
        return this.props.value || 'sin_revisar';
    }

    async _onStatusClick(value) {
        console.log('StatusWidget: Click en estado:', value);
        if (!this.props.readonly) {
            try {
                await this.props.update(value);
                console.log('StatusWidget: Estado actualizado exitosamente a:', value);
            } catch (error) {
                console.error('StatusWidget: Error al actualizar estado:', error);
            }
        }
    }
}

// Registrar el widget
registry.category("fields").add("status_widget", StatusWidget);

export default StatusWidget;