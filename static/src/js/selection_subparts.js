/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useEnv } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

class SelectionSubparts extends Component {
    static template = "sat.SelectionSubparts";
    static props = {
        ...standardFieldProps,   // record, name, value, readonly, update, etc.
    };

    setup() {
        this.env = useEnv();
        this.action = this.env.services.action;
    }

    get selection() {
        // opciones del campo selection: array tipo [[value,label], ...]
        const fieldInfo = this.props.record.fields[this.props.name];
        return fieldInfo && fieldInfo.selection ? fieldInfo.selection : [];
    }

    onChange(ev) {
        const newVal = ev.currentTarget.value || false;
        // notificar cambio al framework
        this.props.update(newVal);
    }

    openWizard() {
        // abre tu wizard; ajusta xmlid si difiere
        this.action.doAction("sat.action_reparacion_add_subparts_wizard", {
            additionalContext: {
                // pasa datos útiles al wizard
                active_model: this.props.record.resModel,     // 'reparaciones.reparaciones'
                active_id: this.props.record.data.id,
                default_reparacion_id: this.props.record.data.id,
                // si además necesitas la intervención, añádela según tu flujo
            },
        });
    }
}

registry.category("fields").add("selection_subparts", SelectionSubparts);
