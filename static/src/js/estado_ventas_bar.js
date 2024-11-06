/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";

export class EstadoVentasBar extends Component {
    static template = 'sat.EstadoVentasBar';
    
    setup() {
        this.estados = [
            { value: 'sin_revisar', label: 'Sin revisar' },
            { value: 'para_revision', label: 'Para revision' },
            { value: 'asignado', label: 'Asignado' },
            { value: 'en_revision', label: 'En revisión' },
            { value: 'finalizado', label: 'Finalizado' },
            { value: 'con_problemas', label: 'Con problemas' },
            { value: 'de_partes', label: 'De partes' },
            { value: 'entregada', label: 'Entregada' }
        ];
    }

    getEstadoClass(estadoValue) {
        const classes = ['estado-option'];
        if (this.props.record.data.estado_ventas_id === estadoValue) {
            classes.push('active');
        }
        classes.push(`estado-${estadoValue}`);
        return classes.join(' ');
    }

    async onEstadoClick(estadoValue) {
        try {
            await this.props.record.update({
                estado_ventas_id: estadoValue
            });
        } catch (error) {
            console.error('Error al actualizar el estado:', error);
        }
    }
}

EstadoVentasBar.supportedTypes = ["selection"];

registry.category("fields").add("estado_ventas_bar", EstadoVentasBar);