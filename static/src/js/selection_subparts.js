/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";
import { useService } from "@web/core/utils/hooks";

export class SelectionSubparts extends SelectionField {
    setup() {
        super.setup();
        this.action = useService("action");
        this.notification = useService("notification");
    }

    async onChange(ev) {
        // Primero ejecutar el onChange original
        const result = await super.onChange(ev);
        
        // Después verificar si necesitamos abrir el wizard
        const newValue = ev.target.value;
        if (newValue === "requiere_cambio") {
            const resId = this.props.record.resId;
            
            if (!resId) {
                this.notification.add(
                    "Primero guarda el registro para poder añadir subpartes.", 
                    { type: "warning" }
                );
                return result;
            }

            // Por ahora, solo mostrar una notificación para probar
            this.notification.add(
                `Campo ${this.props.name} cambió a requiere_cambio. ResId: ${resId}`,
                { type: "info" }
            );
        }
        
        return result;
    }
}

registry.category("fields").add("selection_subparts", SelectionSubparts);