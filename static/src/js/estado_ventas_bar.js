/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";

class EstadoVentasBar extends Component {
    setup() {
        super.setup();
    }

    get estado() {
        return this.props.value || 'sin_revisar';
    }

    get estados() {
        return [
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
        return {
            'estado-option': true,
            'active': this.estado === estadoValue,
            [`estado-${estadoValue}`]: true
        };
    }

    async onEstadoClick(estadoValue) {
        await this.props.update(estadoValue);
    }
}

EstadoVentasBar.props = {
    value: { type: String, optional: true },
    update: { type: Function },
    record: { type: Object },
    name: { type: String },
};

EstadoVentasBar.template = 'sat.EstadoVentasBar';

registry.category("fields").add("estado_ventas_bar", EstadoVentasBar);