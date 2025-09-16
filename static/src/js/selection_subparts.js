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

    // Capturamos el cambio y luego llamamos al super
    async onChange(ev) {
        // lee el valor nuevo antes del super (que actualiza el record)
        const newVal = ev?.target?.value;
        await super.onChange(ev);

        try {
            // Sólo dispara si el nuevo valor exige subpartes
            if (newVal === "cambiado") {
                const rec = this.props.record;
                const resId = rec?.resId;

                // Solo podemos abrir wizard si el registro EXISTE (tiene id)
                if (!resId) {
                    this.notification.add(
                        "Primero guarda el registro para poder añadir subpartes.",
                        { type: "warning" }
                    );
                    return;
                }

                // Lanza el wizard
                await this.action.doAction({
                    type: "ir.actions.act_window",
                    name: "Añadir/Editar Subpartes",
                    res_model: "reparacion.add.subparts.wizard",
                    target: "new",
                    views: [[false, "form"]],
                    // 👉 Ajusta el context a tu wizard real
                    // Si tu wizard necesita intervencion_id, pásalo también.
                    context: {
                        // Caso Reparación:
                        default_reparacion_id: resId,
                        active_id: resId,

                        // Si tu wizard es por Intervención, cambia esto:
                        // 'active_intervencion_id': resId,
                        // 'default_intervencion_id': resId,
                    },
                });
            }
        } catch (err) {
            console.error("Error abriendo wizard de subpartes:", err);
            this.notification.add("No se pudo abrir el asistente de subpartes.", { type: "danger" });
        }
    }
}

// Reutiliza el template nativo del selection
SelectionSubparts.template = SelectionField.template;

// Registra el widget para usarlo con widget="selection_subparts"
registry.category("view_widgets").add("selection_subparts", {
    component: SelectionSubparts,
});
