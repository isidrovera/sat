/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class SelectionSubpartsWidget extends Component {
    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
    }
    get fieldName() {
        return this.props.name; // p.ej. "black_id"
    }
    get value() {
        return this.props.value;
    }
    get selectionList() {
        const f = this.props.record.fields[this.fieldName];
        return f?.selection || [];
    }
    async onChange(ev) {
        const newVal = ev.target.value;
        await this.props.record.update({ [this.fieldName]: newVal });
        if (newVal === "cambio") {
            const recId = this.props.record.resId;
            if (!recId) {
                this.notification.add("Guarda el registro antes de abrir el wizard.", { type: "warning" });
                return;
            }
            await this.action.doAction("sat.action_reparacion_add_subparts_wizard", {
                additionalContext: {
                    active_model: "reparaciones.reparaciones",
                    active_id: recId,
                    default_reparacion_id: recId,
                },
            });
        }
    }
}
SelectionSubpartsWidget.template = "sat.SelectionSubparts";

registry.category("view_widgets").add("selection_subparts", {
    component: SelectionSubpartsWidget,
});
