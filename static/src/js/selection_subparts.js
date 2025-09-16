/** @odoo-module **/
import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

console.log("🚀 [SelectionSubparts] Iniciando carga del módulo");

export class SelectionSubparts extends SelectionField {
    setup() {
        console.log("🔧 [SelectionSubparts] Ejecutando setup()");
        console.log("🔧 [SelectionSubparts] Props recibidas:", this.props);
        
        try {
            super.setup();
            console.log("✅ [SelectionSubparts] Super.setup() ejecutado correctamente");
        } catch (error) {
            console.error("❌ [SelectionSubparts] Error en super.setup():", error);
        }

        try {
            this.action = useService("action");
            console.log("✅ [SelectionSubparts] Servicio 'action' cargado");
        } catch (error) {
            console.error("❌ [SelectionSubparts] Error cargando servicio 'action':", error);
        }

        try {
            this.orm = useService("orm");
            console.log("✅ [SelectionSubparts] Servicio 'orm' cargado");
        } catch (error) {
            console.error("❌ [SelectionSubparts] Error cargando servicio 'orm':", error);
        }

        try {
            this.notification = useService("notification");
            console.log("✅ [SelectionSubparts] Servicio 'notification' cargado");
        } catch (error) {
            console.error("❌ [SelectionSubparts] Error cargando servicio 'notification':", error);
        }

        console.log("🔧 [SelectionSubparts] Setup completado");
    }

    async onChange(ev) {
        console.log("🎯 [SelectionSubparts] onChange() iniciado");
        console.log("🎯 [SelectionSubparts] Evento recibido:", ev);
        
        try {
            await super.onChange(ev);
            console.log("✅ [SelectionSubparts] super.onChange() ejecutado correctamente");
        } catch (error) {
            console.error("❌ [SelectionSubparts] Error en super.onChange():", error);
        }

        const value = this.props.record.data[this.props.name];
        console.log("📊 [SelectionSubparts] Valor actual del campo:", value);
        console.log("📊 [SelectionSubparts] Nombre del campo:", this.props.name);
        console.log("📊 [SelectionSubparts] Datos del record:", this.props.record.data);
        
        if (value === "requiere_cambio" || value === "cambio_de_repuestos") {
            console.log("🔄 [SelectionSubparts] Valor coincide con condición, ejecutando acción");
            console.log("🔄 [SelectionSubparts] ID del record:", this.props.record.data.id);
            
            try {
                console.log("🌐 [SelectionSubparts] Iniciando llamada RPC");
                console.log("🌐 [SelectionSubparts] Modelo: reparaciones.reparaciones");
                console.log("🌐 [SelectionSubparts] Método: rpc_prepare_subparts_wizard");
                console.log("🌐 [SelectionSubparts] Parámetros:", [this.props.record.data.id, this.props.name]);
                
                const res = await this.orm.call(
                    "reparaciones.reparaciones",
                    "rpc_prepare_subparts_wizard",
                    [this.props.record.data.id, this.props.name]
                );
                
                console.log("✅ [SelectionSubparts] Respuesta RPC recibida:", res);
                
                if (res && res.intervencion_id) {
                    console.log("🎭 [SelectionSubparts] intervencion_id encontrado:", res.intervencion_id);
                    console.log("🎭 [SelectionSubparts] Preparando doAction");
                    
                    const actionContext = {
                        active_id: this.props.record.data.id,
                        active_model: "reparaciones.reparaciones",
                        active_intervencion_id: res.intervencion_id,
                        default_reparacion_id: this.props.record.data.id,
                        default_intervencion_id: res.intervencion_id,
                    };
                    
                    console.log("🎭 [SelectionSubparts] Contexto de acción:", actionContext);
                    
                    await this.action.doAction("sat.action_reparacion_add_subparts_wizard", {
                        additionalContext: actionContext,
                    });
                    
                    console.log("✅ [SelectionSubparts] doAction ejecutado correctamente");
                } else {
                    console.warn("⚠️ [SelectionSubparts] No se encontró intervencion_id en la respuesta");
                    console.warn("⚠️ [SelectionSubparts] Respuesta completa:", res);
                }
            } catch (e) {
                console.error("❌ [SelectionSubparts] Error en el proceso:", e);
                console.error("❌ [SelectionSubparts] Stack trace:", e.stack);
                
                try {
                    this.notification.add(_t("No se pudo abrir el asistente de subpartes."), { type: "danger" });
                    console.log("📢 [SelectionSubparts] Notificación de error mostrada");
                } catch (notifError) {
                    console.error("❌ [SelectionSubparts] Error mostrando notificación:", notifError);
                }
            }
        } else {
            console.log("🚫 [SelectionSubparts] Valor no coincide con condición, no se ejecuta acción");
            console.log("🚫 [SelectionSubparts] Valores esperados: 'requiere_cambio' o 'cambio_de_repuestos'");
            console.log("🚫 [SelectionSubparts] Valor actual:", value);
        }
        
        console.log("🎯 [SelectionSubparts] onChange() finalizado");
    }
}

console.log("📝 [SelectionSubparts] Configurando props del widget");
SelectionSubparts.template = "web.SelectionField";
SelectionSubparts.props = { ...standardFieldProps };
console.log("📝 [SelectionSubparts] Props configuradas:", SelectionSubparts.props);

console.log("📋 [SelectionSubparts] Registrando widget en registry");
try {
    registry.category("fields").add("selection_subparts", SelectionSubparts);
    console.log("✅ [SelectionSubparts] Widget registrado exitosamente");
} catch (error) {
    console.error("❌ [SelectionSubparts] Error registrando widget:", error);
}

// Verificar que el registry contiene nuestro widget
setTimeout(() => {
    const fields = registry.category("fields");
    const registeredWidgets = fields.getAll();
    console.log("📊 [SelectionSubparts] Widgets registrados en total:", Object.keys(registeredWidgets).length);
    console.log("📊 [SelectionSubparts] Lista de widgets:", Object.keys(registeredWidgets));
    
    if (registeredWidgets.selection_subparts) {
        console.log("✅ [SelectionSubparts] Widget encontrado en registry");
        console.log("✅ [SelectionSubparts] Detalles del widget:", registeredWidgets.selection_subparts);
    } else {
        console.error("❌ [SelectionSubparts] Widget NO encontrado en registry");
    }
}, 1000);

console.log("🎉 [SelectionSubparts] Módulo cargado completamente");