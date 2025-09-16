/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";
import { useService } from "@web/core/utils/hooks";

console.log("🚀 Cargando módulo SelectionSubparts...");

class SelectionSubparts extends SelectionField {
    static template = SelectionField.template;
    
    setup() {
        console.log("🔧 SelectionSubparts.setup() - Iniciando configuración");
        
        super.setup();
        
        this.action = useService("action");
        this.notification = useService("notification");

        console.log("📝 Props del campo:", {
            name: this.props?.name || 'undefined',
            type: this.props?.type || 'undefined',
            value: this.props?.record?.data?.[this.props?.name] || 'undefined',
            record: !!this.props?.record
        });
    }

    get fieldInfo() {
        return this.props?.record?.fields?.[this.props?.name] || {};
    }

    get value() {
        if (!this.props?.record?.data || !this.props?.name) {
            return false;
        }
        return this.props.record.data[this.props.name];
    }

    async onChange(ev) {
        console.log("🔄 SelectionSubparts.onChange() - Evento disparado");
        
        const newVal = ev?.target?.value;
        console.log("📊 Nuevo valor seleccionado:", newVal);

        // Validar que tenemos los props necesarios
        if (!this.props || !this.props.record) {
            console.error("❌ Props o record no están disponibles");
            return;
        }

        try {
            // Ejecutar el onChange padre primero
            await super.onChange(ev);
            console.log("✅ super.onChange() ejecutado correctamente");
        } catch (error) {
            console.error("❌ Error en super.onChange():", error);
            return;
        }

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
            
            try {
                this.notification.add(mensaje, { type: "warning" });
                console.log("✅ Notificación mostrada correctamente");
            } catch (error) {
                console.error("❌ Error mostrando notificación:", error);
            }
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
            
            try {
                this.notification.add(
                    `Error abriendo el wizard: ${error.message}`, 
                    { type: "danger" }
                );
            } catch (notifError) {
                console.error("❌ Error mostrando notificación de error:", notifError);
            }
        }

        console.log("🏁 SelectionSubparts.onChange() - Proceso completado");
    }
}

// Registrar solo en fields registry
registry.category("fields").add("selection_subparts", SelectionSubparts);

console.log("✅ Widget 'selection_subparts' registrado correctamente");