/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";
import { useService } from "@web/core/utils/hooks";

console.log("🚀 Cargando módulo SelectionSubparts...");

class SelectionSubparts extends SelectionField {
    setup() {
        console.log("🔧 SelectionSubparts.setup() - Iniciando configuración");
        
        try {
            super.setup();
            console.log("✅ super.setup() ejecutado correctamente");
        } catch (error) {
            console.error("❌ Error en super.setup():", error);
        }

        try {
            this.action = useService("action");
            console.log("✅ Servicio 'action' cargado correctamente");
        } catch (error) {
            console.error("❌ Error cargando servicio 'action':", error);
        }

        try {
            this.notification = useService("notification");
            console.log("✅ Servicio 'notification' cargado correctamente");
        } catch (error) {
            console.error("❌ Error cargando servicio 'notification':", error);
        }

        console.log("📝 Props del campo:", {
            name: this.props.name,
            type: this.props.type,
            value: this.props.record.data[this.props.name],
            record: this.props.record
        });

        console.log("🔧 SelectionSubparts.setup() - Configuración completada");
    }

    async onChange(ev) {
        console.log("🔄 SelectionSubparts.onChange() - Evento disparado");
        
        const newVal = ev?.target?.value;
        console.log("📊 Nuevo valor seleccionado:", newVal);
        console.log("📊 Evento completo:", ev);

        try {
            console.log("⏳ Ejecutando super.onChange()...");
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
        console.log("📄 Registro completo:", rec);
        
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
                // Si tu wizard usa intervención, cambia a:
                // active_intervencion_id: resId,
                // default_intervencion_id: resId,
            },
        };

        console.log("🚀 Ejecutando acción con configuración:", actionConfig);

        try {
            await this.action.doAction(actionConfig);
            console.log("✅ Acción ejecutada correctamente");
        } catch (error) {
            console.error("❌ Error ejecutando acción:", error);
            
            // Mostrar error al usuario también
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

// Verificar que el template existe
if (SelectionField.template) {
    SelectionSubparts.template = SelectionField.template;
    console.log("✅ Template asignado correctamente:", SelectionField.template);
} else {
    console.error("❌ SelectionField.template no encontrado!");
}

// Verificar el registro en el registry
console.log("📋 Registrando widget 'selection_subparts'...");

try {
    const viewWidgetsRegistry = registry.category("view_widgets");
    console.log("📋 Registry de view_widgets encontrado:", viewWidgetsRegistry);
    
    // Verificar si ya existe
    const existingWidget = viewWidgetsRegistry.get("selection_subparts", null);
    if (existingWidget) {
        console.log("⚠️ Widget 'selection_subparts' ya existe:", existingWidget);
    }
    
    // Registrar el widget
    viewWidgetsRegistry.add("selection_subparts", { 
        component: SelectionSubparts 
    });
    
    console.log("✅ Widget 'selection_subparts' registrado correctamente");
    
    // Verificar el registro
    const registeredWidget = viewWidgetsRegistry.get("selection_subparts");
    console.log("✅ Widget verificado después del registro:", registeredWidget);
    
    // Mostrar todos los widgets disponibles para debug
    const allWidgets = viewWidgetsRegistry.getAll();
    console.log("📋 Todos los widgets disponibles:", Object.keys(allWidgets));
    
} catch (error) {
    console.error("❌ Error registrando widget:", error);
}

console.log("🎉 Módulo SelectionSubparts cargado completamente");