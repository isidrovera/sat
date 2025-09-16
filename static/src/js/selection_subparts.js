/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class SelectionSubparts extends Component {}
SelectionSubparts.template = "sat.SelectionSubparts";
SelectionSubparts.props = {
    // props “reales” del widget
    value: { type: [String, Number, Boolean], optional: true },
    selectionList: { type: Array },
    readonly: { type: Boolean, optional: true },
    onChange: { type: Function, optional: true },

    // ⚠ props que el Field pasa automáticamente (las ignoramos, pero hay que declararlas)
    id: { type: [String, Number], optional: true },
    name: { type: String, optional: true },
    record: { type: Object, optional: true },
};

const fieldRegistry = registry.category("fields");
fieldRegistry.add("selection_subparts", {
    component: SelectionSubparts,
    supportedTypes: ["selection"],
    extractProps: ({ field, record, value, attrs }) => {
        const currentValue = value !== undefined ? value : record?.data?.[field.name];
        const selection = field.selection || field.params?.selection || [];
        const readonly = Boolean(attrs?.readonly) || !record || Boolean(record?.isReadonly);

        const onChange = (ev) => {
            if (!record) return;
            let newVal = ev.target.value;
            const sample = selection.length ? selection[0][0] : undefined;
            if (typeof sample === "number" && newVal !== "" && !Number.isNaN(Number(newVal))) {
                newVal = Number(newVal);
            } else if (typeof sample === "boolean") {
                newVal = newVal === "true";
            }
            record.update({ [field.name]: newVal });
        };

        return { value: currentValue, selectionList: selection, readonly, onChange };
    },
    isEmpty: ({ value }) => value === undefined || value === null || value === "",
});
