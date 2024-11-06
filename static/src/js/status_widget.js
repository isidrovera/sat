/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Field } from "@web/views/fields/field";

class StatusWidget extends Field {
    static componentName = "StatusWidget";  // Añadido nombre del componente
    
    static template = "sat.StatusWidget";
    
    static props = {
        ...standardFieldProps,
        readonly: { type: Boolean, optional: true },
    };

    static defaultProps = {  // Añadido defaultProps
        readonly: false,
    };

    setup() {
        console.log('StatusWidget: Iniciando setup');
        super.setup();
        
        // Debug props
        console.log('StatusWidget Props:', {
            name: this.props.name,
            record: this.props.record,
            value: this.props.value,
            readonly: this.props.readonly
        });

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

    get fieldInfo() {
        console.log('StatusWidget: Obteniendo fieldInfo');
        if (!this.props.record) {
            console.warn('StatusWidget: No hay record disponible');
            return null;
        }
        return this.props.record.fields[this.props.name] || null;
    }

    get selectionOptions() {
        console.log('StatusWidget: Obteniendo opciones de selección');
        const field = this.fieldInfo;
        if (!field || !field.selection) {
            console.warn('StatusWidget: No hay opciones de selección disponibles');
            return [];
        }
        return field.selection;
    }

    getStatusConfig(value) {
        console.log('StatusWidget: getStatusConfig llamado con valor:', value);
        if (!value) {
            console.warn('StatusWidget: Valor undefined, usando sin_revisar');
            return this.status_config['sin_revisar'];
        }
        return this.status_config[value] || this.status_config['sin_revisar'];
    }

    async onStatusClick(value) {
        console.log('StatusWidget: Click en estado:', value);
        if (!this.props.readonly) {
            try {
                await this.props.update(value);
                console.log('StatusWidget: Actualización exitosa');
            } catch (error) {
                console.error('StatusWidget: Error al actualizar:', error);
            }
        }
    }
}

// Registrar los widgets para diferentes vistas
registry.category("fields").add("status_widget", StatusWidget);
registry.category("fields").add("kanban_label_selection", StatusWidget);  // Añadido para vista kanban

export default StatusWidget;