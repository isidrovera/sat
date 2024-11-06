/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Field } from "@web/views/fields/field";

class StatusWidget extends Field {
    setup() {
        console.log('StatusWidget: Iniciando setup');
        try {
            super.setup();
            console.log('StatusWidget: Super setup completado');
            
            // Log de propiedades iniciales
            console.log('StatusWidget: Props iniciales:', {
                value: this.props.value,
                readonly: this.props.readonly,
                field: this.props.field
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
            
            console.log('StatusWidget: Configuración de estados cargada');
        } catch (error) {
            console.error('StatusWidget: Error en setup:', error);
        }
        console.log('StatusWidget: Setup finalizado');
    }

    getStatusConfig(value) {
        console.log('StatusWidget: Obteniendo configuración para valor:', value);
        try {
            const config = this.status_config[value] || this.status_config['sin_revisar'];
            console.log('StatusWidget: Configuración obtenida:', config);
            return config;
        } catch (error) {
            console.error('StatusWidget: Error al obtener configuración:', error);
            return this.status_config['sin_revisar'];
        }
    }

    async _onStatusClick(value) {
        console.log('StatusWidget: Click en estado:', value);
        console.log('StatusWidget: Estado readonly:', this.props.readonly);
        
        if (!this.props.readonly) {
            try {
                console.log('StatusWidget: Intentando actualizar a:', value);
                await this.props.update(value);
                console.log('StatusWidget: Actualización exitosa');
            } catch (error) {
                console.error('StatusWidget: Error al actualizar estado:', error);
                throw error;
            }
        } else {
            console.log('StatusWidget: No se actualiza por ser readonly');
        }
    }

    get selectionValues() {
        console.log('StatusWidget: Obteniendo valores de selección');
        try {
            if (this.props.field && this.props.field.selection) {
                const values = this.props.field.selection.slice().reverse();
                console.log('StatusWidget: Valores de selección:', values);
                return values;
            }
            console.warn('StatusWidget: No hay valores de selección disponibles');
            return [];
        } catch (error) {
            console.error('StatusWidget: Error al obtener valores de selección:', error);
            return [];
        }
    }
}

StatusWidget.template = 'sat.StatusWidget';
StatusWidget.props = {
    ...standardFieldProps,
};
StatusWidget.supportedTypes = ['selection'];

console.log('StatusWidget: Registrando widget en el registro de campos');
try {
    registry.category("fields").add("status_widget", StatusWidget);
    console.log('StatusWidget: Widget registrado exitosamente');
} catch (error) {
    console.error('StatusWidget: Error al registrar widget:', error);
}

export default StatusWidget;