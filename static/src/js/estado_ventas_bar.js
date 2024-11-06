/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";

class EstadoVentasBar extends Component {
    static template = 'sat.EstadoVentasBar';
    static props = {
        name: { type: String, optional: true },
        record: { type: Object, optional: true },
        value: { type: String, optional: true },
        update: { type: Function, optional: true },
    };

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
        const classes = ['estado-option'];
        if (this.estado === estadoValue) {
            classes.push('active');
        }
        classes.push(`estado-${estadoValue}`);
        return classes.join(' ');
    }

    onEstadoClick(estadoValue) {
        if (this.props.update) {
            this.props.update(estadoValue);
        }
    }
}

registry.category("fields").add("estado_ventas_bar", EstadoVentasBar);

export default EstadoVentasBar;