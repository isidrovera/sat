/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class SelectionSubparts extends Component {
    static template = "web.SelectionField"; // Usar el template base de Odoo
    
    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
    }
    
    async onChange(ev) {
        const newValue = ev.target.value;
        
        // Actualizar el valor en el record
        await this.props.record.update({ [this.props.name]: newValue });
        
        if (newValue === "requiere_cambio") {
            const resId = this.props.record.resId;
            
            if (!resId) {
                this.notification.add(
                    "Primero guarda el registro para poder añadir subpartes.", 
                    { type: "warning" }
                );
                return;
            }

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

registry.category("fields").add("selection_subparts", SelectionSubparts);