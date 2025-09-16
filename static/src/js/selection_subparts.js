/** @odoo-module **/

import { Component, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";

const TAG = "[selection_subparts]";

export class SelectionSubparts extends Component {
  setup() {
    onMounted(() => {
      const el = this.el?.querySelector("select");
      const cs = el ? getComputedStyle(el) : null;
      console.debug(TAG, "mounted props=", this.props, {
        disabledAttr: el?.hasAttribute("disabled"),
        pointerEvents: cs?.pointerEvents,
      });
    });
  }
}
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
    const fieldName = field?.name;

    // 🔎 Captura selection desde varios lugares posibles
    const selField   = field?.selection || field?.params?.selection;
    const selModel   = record?.model?.fields?.[fieldName]?.selection; // ⬅️ fallback clave
    const selAttrs   = attrs?.selection;
    const selection  = selField || selModel || selAttrs || [];

    const currentValue = value !== undefined ? value : record?.data?.[fieldName];
    const readonly     = Boolean(attrs?.readonly) || Boolean(record?.isReadonly);

    const onChange = (ev) => {
      const newVal = ev.target.value;
      console.debug(TAG, "onChange", { newVal, hasRecord: !!record });
      if (record) record.update({ [fieldName]: newVal });
    };

    // Logs útiles
    console.debug(TAG, "extractProps", {
      model: record?.model?.name,
      fieldName,
      type: field?.type,
      selFieldLen: (selField || []).length,
      selModelLen: (selModel || []).length,
      selAttrsLen: (selAttrs || []).length,
      finalLen: selection.length,
      value: currentValue,
      readonly,
    });

    if (!selection.length) {
      console.warn(TAG, "EMPTY selectionList — revisa definición Python/herencias del campo", fieldName);
    }

    return { value: currentValue, selectionList: selection, readonly, onChange };
  },
  isEmpty: ({ value }) => value === undefined || value === null || value === "",
});
