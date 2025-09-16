/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class SelectionSubparts extends Component {}
SelectionSubparts.template = "sat.SelectionSubparts";
SelectionSubparts.props = {
    value: { type: [String, Number, Boolean], optional: true },
    selectionList: { type: Array },
    readonly: { type: Boolean, optional: true },
    onChange: { type: Function, optional: true },
};

const fieldRegistry = registry.category("fields");
fieldRegistry.add("selection_subparts", {
    component: SelectionSubparts,
    supportedTypes: ["selection"],

    extractProps: ({ field, record, value, attrs }) => {
        // Obtener valor actual de forma robusta
        const currentValue = value !== undefined ? value : record?.data?.[field.name];

        // Obtener lista de selección con fallbacks
        const selection = field.selection || 
                         field.params?.selection || 
                         attrs.selection || 
                         [];

        // Determinar si es readonly
        const readonly = Boolean(attrs.readonly) || 
                        !record || 
                        record.isReadonly || 
                        record.isInEdition === false;

        // Función onChange mejorada con validación
        const onChange = (ev) => {
            if (!record || readonly) {
                return; // No hacer nada si no hay record o es readonly
            }

            const newValue = ev.target.value;
            
            // Convertir valor según el tipo esperado
            let processedValue = newValue;
            if (newValue === "") {
                processedValue = false; // o null según tu lógica de negocio
            } else if (field.type === "selection" && !isNaN(newValue)) {
                // Si es numérico, convertir a number
                processedValue = parseInt(newValue, 10);
            }

            try {
                record.update({ [field.name]: processedValue });
            } catch (error) {
                console.warn(`Error updating field ${field.name}:`, error);
            }
        };

        return { 
            value: currentValue, 
            selectionList: selection, 
            readonly, 
            onChange 
        };
    },

    isEmpty: ({ value }) => {
        return value === undefined || 
               value === null || 
               value === "" || 
               value === false;
    },
});