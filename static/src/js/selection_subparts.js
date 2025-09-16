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

    const selection = field.selection || field.params?.selection || attrs?.selection || [];

    // ✅ readonly SOLO si lo piden o el record es readonly
    const readonly = Boolean(attrs?.readonly) || Boolean(record?.isReadonly);

    const onChange = (ev) => {
      if (!record) return; // permite abrir sin romper si no hay record
      let newVal = ev.target.value;
      // tus opciones son strings; no hace falta castear
      record.update({ [field.name]: newVal });
    };

    console.debug("[selection_subparts] readonly=", readonly, "len(selection)=", selection.length, "value=", currentValue);

    return { value: currentValue, selectionList: selection, readonly, onChange };
  },
  isEmpty: ({ value }) => value === undefined || value === null || value === "",
});
