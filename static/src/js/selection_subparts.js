/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class SelectionSubpartsWidget extends Component {
    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    get fieldName() {
        return this.props.name;                   // "black_id"
    }

    get value() {
        return this.props.value;                  // valor actual del Selection
    }

    get selectionList() {
        // opciones del selection definidas en el campo
        // props.record.fields[this.props.name].selection => [['ok','OK'], ...]
        const f = this.props.record.fields[this.fieldName];
        return (f && f.selection) ? f.selection : [];
    }

    async onChange(ev) {
        const newVal = ev.target.value;
        // escribe el nuevo valor en el registro en edición
        await this.props.record.update({ [this.fieldName]: newVal });

        if (newVal === "cambio") {
            try {
                // Abrimos el wizard con contexto útil
                const recId = this.props.record.resId;  // id de reparaciones.reparaciones
                if (!recId) {
                    this.notification.add("Guarda el registro antes de abrir el wizard.", { type: "warning" });
                    return;
                }
                await this.action.doAction("sat.action_reparacion_add_subparts_wizard", {
                    additionalContext: {
                        // lo que tu wizard espera
                        active_model: "reparaciones.reparaciones",
                        active_id: recId,

                        // si necesitas enlazar a una intervencion en particular:
                        // 'active_intervencion_id': <id_intervencion>,
                        // 'default_intervencion_id': <id_intervencion>,
                        // 'default_reparacion_id': recId,
                    },
                });
            } catch (e) {
                console.error(e);
                this.notification.add("No se pudo abrir el wizard de subpartes.", { type: "danger" });
            }
        }
    }
}

SelectionSubpartsWidget.template = "sat.SelectionSubparts";
registry.category("view_widgets").add("selection_subparts", { component: SelectionSubpartsWidget });
