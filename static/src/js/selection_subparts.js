/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class SelectionSubparts extends Component {
    static template = "SelectionSubparts.Template";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
    }

    get fieldInfo() {
        return this.props.record.fields[this.props.name];
    }

    get selection() {
        return this.fieldInfo.selection || [];
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    get displayValue() {
        const selection = this.selection;
        for (const [key, label] of selection) {
            if (key === this.value) {
                return label;
            }
        }
        return "";
    }

    async onChange(ev) {
        const newValue = ev.target.value;
        
        // Actualizar el valor en el record
        await this.props.record.update({ [this.props.name]: newValue });
        
        // Solo proceder si el valor es "requiere_cambio"
        if (newValue === "requiere_cambio") {
            const resId = this.props.record.resId;
            
            if (!resId) {
                this.notification.add(
                    "Primero guarda el registro para poder añadir subpartes.", 
                    { type: "warning" }
                );
                return;
            }

            // Abrir wizard
            try {
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
            } catch (error) {
                this.notification.add(
                    "Error abriendo el wizard: " + error.message,
                    { type: "danger" }
                );
            }
        }
    }
}

// Registrar el widget
registry.category("fields").add("selection_subparts", SelectionSubparts);