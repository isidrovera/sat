/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class SelectionSubparts extends Component {}
SelectionSubparts.template = "sat.SelectionSubparts"; // tu template QWeb
SelectionSubparts.props = {
    value: { type: [String, Number, Boolean, null] },
    selectionList: { type: Array },            // [[value,label], ...]
    readonly: { type: Boolean, optional: true },
    onChange: { type: Function, optional: true },
};

// Registro CORRECTO en el registry de fields:
const fieldRegistry = registry.category("fields");
fieldRegistry.add("selection_subparts", {
    component: SelectionSubparts,
    supportedTypes: ["selection"], // o lo que apliquen
    extractProps: ({ field, record, attrs }) => ({
        value: record.data[field.name],
        selectionList: field.selection || [],
        readonly: attrs.readonly || false,
        onChange: (ev) => {
            const newVal = ev.target.value;
            record.update({ [field.name]: newVal });
        },
    }),
    isEmpty: ({ value }) => value === undefined || value === null || value === "",
});
