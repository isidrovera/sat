/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";
import { useService } from "@web/core/utils/hooks";

// Heredamos el widget nativo de selección y añadimos lógica extra
class SelectionSubpartsField extends SelectionField {
    setup() {
        super.setup();
        this.action = useService("action");
        this.notification = useService("notification");
    }

    async onChange(ev) {
        // Llamamos primero a la lógica nativa (escribe el valor)
        await super.onChange(ev);

        const newVal = ev.target.value;
        if (newVal === "cambio") {
            const recId = this.props.record.resId;
            if (!recId) {
                this.notification.add("Guarda el registro antes de abrir el asistente.", { type: "warning" });
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

// REGISTRO CORRECTO: categoría "fields"
registry.category("fields").add("selection_subparts", SelectionSubpartsField);
