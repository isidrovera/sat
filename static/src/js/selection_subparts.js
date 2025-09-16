/** @odoo-module **/
import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

console.log("🚀 [SelectionSubparts] Iniciando carga del módulo para campo SELECTION");

export class SelectionSubparts extends SelectionField {
    setup() {
        console.log("🔧 [SelectionSubparts] Ejecutando setup() para campo selection");
        console.log("🔧 [SelectionSubparts] Props:", this.props);
        console.log("🔧 [SelectionSubparts] Field type:", this.props.type);
        
        super.setup();
        
        try {
            this.action = useService("action");
            this.orm = useService("orm");
            this.notification = useService("notification");
            console.log("✅ [SelectionSubparts] Servicios cargados correctamente");
        } catch (error) {
            console.error("❌ [SelectionSubparts] Error cargando servicios:", error);
        }
        
        console.log("✅ [SelectionSubparts] Setup completado");
    }

    async onChange(ev) {
        console.log("🎯 [SelectionSubparts] onChange() iniciado para campo selection");
        console.log("🎯 [SelectionSubparts] Evento:", ev);
        console.log("🎯 [SelectionSubparts] Target value:", ev.target.value);
        
        // Ejecutar el onChange del padre PRIMERO
        await super.onChange(ev);
        console.log("✅ [SelectionSubparts] super.onChange() completado");
        
        // Para campos selection, el valor está directamente en el target del evento
        const selectedValue = ev.target.value;
        console.log("📊 [SelectionSubparts] Valor seleccionado:", selectedValue);
        
        // También verificar el valor en el record
        const recordValue = this.props.record.data[this.props.name];
        console.log("📊 [SelectionSubparts] Valor en record:", recordValue);
        
        // Usar el valor del evento (más confiable para campos selection)
        const value = selectedValue || recordValue;
        console.log("📊 [SelectionSubparts] Valor final a evaluar:", value);
        
        if (value === "requiere_cambio" || value === "cambio_de_repuestos") {
            console.log("🔄 [SelectionSubparts] Condición cumplida, ejecutando acción");
            console.log("🔄 [SelectionSubparts] Record ID:", this.props.record.data.id);
            console.log("🔄 [SelectionSubparts] Field name:", this.props.name);
            
            try {
                console.log("🌐 [SelectionSubparts] Iniciando llamada RPC");
                
                const res = await this.orm.call(
                    "reparaciones.reparaciones",
                    "rpc_prepare_subparts_wizard",
                    [this.props.record.data.id, this.props.name]
                );
                
                console.log("✅ [SelectionSubparts] Respuesta RPC:", res);
                
                if (res && res.intervencion_id) {
                    console.log("🎭 [SelectionSubparts] Abriendo wizard con intervencion_id:", res.intervencion_id);
                    
                    const actionContext = {
                        active_id: this.props.record.data.id,
                        active_model: "reparaciones.reparaciones",
                        active_intervencion_id: res.intervencion_id,
                        default_reparacion_id: this.props.record.data.id,
                        default_intervencion_id: res.intervencion_id,
                    };
                    
                    console.log("🎭 [SelectionSubparts] Contexto:", actionContext);
                    
                    await this.action.doAction("sat.action_reparacion_add_subparts_wizard", {
                        additionalContext: actionContext,
                    });
                    
                    console.log("✅ [SelectionSubparts] Wizard abierto exitosamente");
                } else {
                    console.warn("⚠️ [SelectionSubparts] No se recibió intervencion_id en la respuesta");
                }
            } catch (e) {
                console.error("❌ [SelectionSubparts] Error en el proceso:", e);
                this.notification.add(_t("No se pudo abrir el asistente de subpartes."), { type: "danger" });
            }
        } else {
            console.log("🚫 [SelectionSubparts] Valor no coincide con condición");
            console.log("🚫 [SelectionSubparts] Esperado: 'requiere_cambio' o 'cambio_de_repuestos'");
            console.log("🚫 [SelectionSubparts] Recibido:", value);
        }
        
        console.log("🎯 [SelectionSubparts] onChange() finalizado");
    }
}

// Para campos selection, usar las props estándar sin modificaciones
SelectionSubparts.props = { ...standardFieldProps };

console.log("📋 [SelectionSubparts] Registrando widget para campos selection");
registry.category("fields").add("selection_subparts", SelectionSubparts);

// Verificación del registro
setTimeout(() => {
    try {
        const fieldsRegistry = registry.category("fields");
        const widget = fieldsRegistry.get("selection_subparts", null);
        
        if (widget) {
            console.log("✅ [SelectionSubparts] Widget registrado y verificado exitosamente");
        } else {
            console.error("❌ [SelectionSubparts] Widget NO encontrado en registry");
        }
    } catch (error) {
        console.error("❌ [SelectionSubparts] Error verificando registro:", error);
    }
}, 1000);

console.log("🎉 [SelectionSubparts] Módulo para campos selection cargado completamente");