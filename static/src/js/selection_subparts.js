/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";
import { useService } from "@web/core/utils/hooks";

export class SelectionSubparts extends SelectionField {
    setup() {
        // Llamar al setup del padre primero
        super.setup();
        
        // Solo configurar servicios si todo está bien
        this.action = useService("action");
        this.notification = useService("notification");
    }

    async onChange(ev) {
        // Ejecutar onChange del padre primero
        await super.onChange(ev);
        
        const newValue = ev?.target?.value;
        
        // Solo actuar si el valor es "requiere_cambio"
        if (newValue === "requiere_cambio") {
            const resId = this.props?.record?.resId;
            
            if (!resId) {
                this.notification.add(
                    "Primero guarda el registro para poder añadir subpartes.", 
                    { type: "warning" }
                );
                return;
            }

            // Abrir wizard
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Añadir/Editar Subpartes",
                res_model: "reparacion.add.subparts.wizard",
                target: "new",
                views: [[false, "form"]],
                context: {
                    default_reparacion_id: resId,
                    active_id: resId,
                },
            });
        }
    }
}

// NO definir template estático - usar el del padre automáticamente
registry.category("fields").add("selection_subparts", SelectionSubparts);