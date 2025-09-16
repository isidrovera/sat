/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";
import { useService } from "@web/core/utils/hooks";

console.log("🚀 Cargando módulo SelectionSubparts...");

class SelectionSubparts extends SelectionField {
    setup() {
        console.log("🔧 SelectionSubparts.setup() - Iniciando configuración");
        
        super.setup();
        this.action = useService("action");
        this.notification = useService("notification");

        console.log("📝 Props del campo:", {
            name: this.props.name,
            type: this.props.type,
            value: this.props.record.data[this.props.name],
        });
    }

    async onChange(ev) {
        console.log("🔄 SelectionSubparts.onChange() - Evento disparado");
        
        const newVal = ev?.target?.value;
        console.log("📊 Nuevo valor seleccionado:", newVal);

        // Ejecutar el onChange padre primero
        await super.onChange(ev);

        if (newVal !== "cambiado") {
            console.log("⏭️ Valor no es 'cambiado', saliendo. Valor actual:", newVal);
            return;
        }

        console.log("🎯 Valor es 'cambiado', procesando...");

        const rec = this.props.record;
        const resId = rec?.resId;
        console.log("🆔 ID del registro:", resId);

        if (!resId) {
            const mensaje = "Primero guarda el registro para poder añadir subpartes.";
            console.log("⚠️ Sin resId, mostrando notificación:", mensaje);
            this.notification.add(mensaje, { type: "warning" });
            return;
        }

        const actionConfig = {
            type: "ir.actions.act_window",
            name: "Añadir/Editar Subpartes",
            res_model: "reparacion.add.subparts.wizard",
            target: "new",
            views: [[false, "form"]],
            context: {
                default_reparacion_id: resId,
                active_id: resId,
            },
        };

        console.log("🚀 Ejecutando acción con configuración:", actionConfig);

        try {
            await this.action.doAction(actionConfig);
            console.log("✅ Acción ejecutada correctamente");
        } catch (error) {
            console.error("❌ Error ejecutando acción:", error);
            this.notification.add(
                `Error abriendo el wizard: ${error.message}`, 
                { type: "danger" }
            );
        }
    }
}

// Asignar el template - usar el del padre o uno personalizado si existe
SelectionSubparts.template = "sat.SelectionSubparts" || SelectionField.template;

// Registrar en ambos registries para mayor compatibilidad
registry.category("fields").add("selection_subparts", SelectionSubparts);
registry.category("view_widgets").add("selection_subparts", {
    component: SelectionSubparts,
});

console.log("✅ Widget 'selection_subparts' registrado en ambos registries");