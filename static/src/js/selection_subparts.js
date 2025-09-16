/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";
import { useService } from "@web/core/utils/hooks";

class SelectionSubparts extends SelectionField {
    setup() {
        super.setup();
        this.action = useService("action");
        this.notification = useService("notification");
    }

    async onChange(ev) {
        const newVal = ev?.target?.value;
        await super.onChange(ev);

        if (newVal !== "cambiado") {
            return;
        }
        const rec = this.props.record;
        const resId = rec?.resId;
        if (!resId) {
            this.notification.add("Primero guarda el registro para poder añadir subpartes.", { type: "warning" });
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
                // Si tu wizard usa intervención, cambia a:
                // active_intervencion_id: resId,
                // default_intervencion_id: resId,
            },
        });
    }
}

SelectionSubparts.template = SelectionField.template;

// nombre EXACTO que usas en la vista: widget="selection_subparts"
registry.category("view_widgets").add("selection_subparts", { component: SelectionSubparts });
