/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const TAG = "[selection_subparts]";

export class SelectionSubparts extends Component {
  setup() {
    this.orm = useService("orm");
    this.state = useState({
      options: Array.isArray(this.props.selectionList) ? this.props.selectionList : [],
      loading: false,
    });

    // Si no llegaron opciones, las pedimos al servidor vía fields_get
    onWillStart(async () => {
      if (this.state.options.length === 0 && this.props.record && this.props.name) {
        try {
          this.state.loading = true;
          const modelName = this.props.record.model?.name;
          const fieldName = this.props.name;

          // fields_get: queremos solo la selección de ese campo
          const res = await this.orm.call(modelName, "fields_get", [[fieldName], ["selection"]]);
          const sel = (res && res[fieldName] && res[fieldName].selection) || [];
          this.state.options = Array.isArray(sel) ? sel : [];
          // console.debug(TAG, "fields_get loaded", { modelName, fieldName, len: this.state.options.length });
        } catch (e) {
          // console.error(TAG, "fields_get failed", e);
          this.state.options = [];
        } finally {
          this.state.loading = false;
        }
      }
    });
  }
}
SelectionSubparts.template = "sat.SelectionSubparts";
SelectionSubparts.props = {
  // props “normales”
  value: { type: [String, Number, Boolean], optional: true },
  selectionList: { type: Array, optional: true },
  readonly: { type: Boolean, optional: true },
  onChange: { type: Function, optional: true },

  // props extra que Field suele inyectar
  id: { type: [String, Number], optional: true },
  name: { type: String, optional: true },   // <-- nombre del campo (p.ej. "black_id")
  record: { type: Object, optional: true }, // <-- record con model/data
};

const fieldRegistry = registry.category("fields");
fieldRegistry.add("selection_subparts", {
  component: SelectionSubparts,
  supportedTypes: ["selection"],

  extractProps: (args) => {
    const { record, value, attrs } = args;
    const fieldName = args.name; // <- en tu caso sí viene aquí
    const currentValue = value !== undefined ? value : record?.data?.[fieldName];

    // 1) Intentos “rápidos” de obtener opciones (si llegan por props)
    const fromField = args?.field?.selection || args?.field?.params?.selection;
    const fromAttrs = args?.attrs?.selection;
    const selection = fromField || fromAttrs || []; // si vacío, el componente hará RPC

    const readonly = Boolean(attrs?.readonly) || Boolean(record?.isReadonly);

    const onChange = (ev) => {
      const newVal = ev.target.value;
      if (record && typeof record.update === "function") {
        record.update({ [fieldName]: newVal });
      }
    };

    return {
      value: currentValue,
      selectionList: selection,
      readonly,
      onChange,
      name: fieldName,
      record: record,
    };
  },

  isEmpty: ({ value }) => value === undefined || value === null || value === "",
});
