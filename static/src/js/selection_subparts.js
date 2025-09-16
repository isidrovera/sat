/** @odoo-module **/

import { Component, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";

const TAG = "[selection_subparts]";

export class SelectionSubparts extends Component {
  setup() {
    onMounted(() => {
      const el = this.el?.querySelector("select");
      const cs = el ? getComputedStyle(el) : null;
      console.debug(TAG, "mounted", {
        props: this.props,
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
  // props extra que Field puede inyectar
  id: { type: [String, Number], optional: true },
  name: { type: String, optional: true },
  record: { type: Object, optional: true },
};

const fieldRegistry = registry.category("fields");
fieldRegistry.add("selection_subparts", {
  component: SelectionSubparts,
  supportedTypes: ["selection"],

  extractProps: (args) => {
    const { field, record, value, attrs } = args;

    // 🔑 nombre del campo: usa args.name primero (algunas vistas lo pasan así)
    const fieldName = args.name || field?.name;

    // info del campo: toma desde fieldInfo, o desde el modelo, o desde attrs/options
    const fieldInfo   = field || record?.model?.fields?.[fieldName] || {};
    const selField    = fieldInfo.selection || fieldInfo.params?.selection;
    const selModel    = record?.model?.fields?.[fieldName]?.selection;
    const selAttrs    = attrs?.selection;
    const selOptions  = args.options?.selection; // por si algún caller lo pasa en options
    const selection   = selField || selModel || selAttrs || selOptions || [];

    const currentValue = value !== undefined ? value : record?.data?.[fieldName];
    const readonly     = Boolean(attrs?.readonly) || Boolean(record?.isReadonly);

    const onChange = (ev) => {
      const newVal = ev.target.value;
      console.debug(TAG, "onChange", { fieldName, newVal, hasRecord: !!record });
      if (record) record.update({ [fieldName]: newVal });
    };

    // Logs de diagnóstico
    console.debug(TAG, "extractProps", {
      model: record?.model?.name,
      fieldName,
      type_from_field: fieldInfo?.type,
      selFieldLen: (selField || []).length,
      selModelLen: (selModel || []).length,
      selAttrsLen: (selAttrs || []).length,
      selOptionsLen: (selOptions || []).length,
      finalLen: selection.length,
      readonly,
      value: currentValue,
    });

    if (!fieldName) {
      console.warn(TAG, "No llegó 'fieldName' (args.name/field.name). Revisa el uso del widget en la vista.");
    }
    if (!selection.length) {
      console.warn(TAG, "EMPTY selectionList — el <select> no tendrá opciones");
    }

    return { value: currentValue, selectionList: selection, readonly, onChange };
  },

  isEmpty: ({ value }) => value === undefined || value === null || value === "",
});
