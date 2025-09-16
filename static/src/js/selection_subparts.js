/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";
import { useService } from "@web/core/utils/hooks";

console.log("🚀 Iniciando carga de SelectionSubparts...");

export class SelectionSubparts extends SelectionField {
    static template = SelectionField.template;
    
    setup() {
        console.log("🔧 Setup SelectionSubparts - Props:", this.props);
        
        // Validación defensiva de props
        if (!this.props || !this.props.name || !this.props.record) {
            console.error("❌ Props inválidos en SelectionSubparts:", this.props);
            super.setup();
            return;
        }
        
        try {
            super.setup();
            this.action = useService("action");
            this.notification = useService("notification");
            
            console.log("✅ SelectionSubparts configurado correctamente para campo:", this.props.name);
        } catch (error) {
            console.error("❌ Error en setup SelectionSubparts:", error);
            throw error;
        }
    }

    get selection() {
        // Override para asegurar que siempre tenemos una selección válida
        try {
            return super.selection || [];
        } catch (error) {
            console.error("❌ Error obteniendo selection:", error);
            return [];
        }
    }

    get value() {
        try {
            return super.value;
        } catch (error) {
            console.error("❌ Error obteniendo value:", error);
            return false;
        }
    }

    async onChange(ev) {
        console.log("🔄 onChange SelectionSubparts disparado");
        
        try {
            const newValue = ev?.target?.value;
            console.log("📊 Nuevo valor:", newValue);

            // Ejecutar onChange del padre PRIMERO
            await super.onChange(ev);
            
            // Solo proceder si el valor es "requiere_cambio"
            if (newValue !== "requiere_cambio") {
                console.log("⏭️ Valor no es 'requiere_cambio', saliendo");
                return;
            }

            console.log("🎯 Procesando 'requiere_cambio'");

            // Validar que tenemos el record
            const record = this.props?.record;
            if (!record) {
                console.error("❌ No hay record disponible");
                return;
            }

            const resId = record.resId;
            if (!resId) {
                console.log("⚠️ Registro no guardado");
                this.notification.add(
                    "Primero guarda el registro para poder añadir subpartes.", 
                    { type: "warning" }
                );
                return;
            }

            console.log("🚀 Abriendo wizard para resId:", resId);

            // Abrir wizard de subpartes
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Añadir/Editar Subpartes",
                res_model: "reparacion.add.subparts.wizard",
                target: "new",
                views: [[false, "form"]],
                context: {
                    default_reparacion_id: resId,
                    active_id: resId,
                    field_name: this.props.name, // Pasar el nombre del campo
                },
            });

        } catch (error) {
            console.error("❌ Error en onChange SelectionSubparts:", error);
            if (this.notification) {
                this.notification.add(
                    `Error: ${error.message}`, 
                    { type: "danger" }
                );
            }
        }
    }
}

// Registrar el widget
console.log("📋 Registrando widget SelectionSubparts...");
registry.category("fields").add("selection_subparts", SelectionSubparts);
console.log("✅ Widget SelectionSubparts registrado correctamente");