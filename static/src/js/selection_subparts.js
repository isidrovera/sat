/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class SelectionSubparts extends Component {
    static template = `
        <select class="o_input" t-on-change="onChange" t-att-disabled="props.readonly">
            <option value="">-- Seleccionar --</option>
            <t t-foreach="selection" t-as="option" t-key="option[0]">
                <option t-att-value="option[0]" t-att-selected="option[0] === value ? 'selected' : null">
                    <t t-esc="option[1]"/>
                </option>
            </t>
        </select>
    `;

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
    }

    get fieldInfo() {
        return this.props.record?.fields?.[this.props.name] || {};
    }

    get selection() {
        const fieldInfo = this.fieldInfo;
        if (!fieldInfo.selection) return [];
        
        if (typeof fieldInfo.selection === 'function') {
            return fieldInfo.selection();
        }
        return fieldInfo.selection;
    }

    get value() {
        return this.props.record?.data?.[this.props.name] || "";
    }

    async onChange(ev) {
        const newValue = ev.target.value;
        
        // Actualizar el valor
        if (this.props.record && this.props.name) {
            await this.props.record.update({ [this.props.name]: newValue });
        }
        
        // Solo proceder si es "requiere_cambio"
        if (newValue === "requiere_cambio") {
            const resId = this.props.record?.resId;
            
            if (!resId) {
                this.notification.add(
                    "Primero guarda el registro para poder añadir subpartes.", 
                    { type: "warning" }
                );
                return;
            }

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
                    `Error: ${error.message}`,
                    { type: "danger" }
                );
            }
        }
    }
}

registry.category("fields").add("selection_subparts", SelectionSubparts);