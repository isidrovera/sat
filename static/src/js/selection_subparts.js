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

    // Si aún no hay opciones, intenta pedirlas al servidor
    onWillStart(async () => {
      if (this.state.options.length) return;

      const modelName = this.props.record?.model?.name;
      const fieldName = this.props.name;
      if (!modelName || !fieldName) return;

      this.state.loading = true;
      try {
        // Usa el mismo context que la vista si existe
        const ctx =
          this.props.record?.model?.root?.context ||
          this.props.record?.model?.context ||
          {};

        const res = await this.orm.call(
          modelName,
          "fields_get",
          [[fieldName], ["selection"]],
          { context: ctx }
        );
        const sel = (res && res[fieldName] && res[fieldName].selection) || [];
        this.state.options = Array.isArray(sel) ? sel : [];
        // console.debug(TAG, "fields_get", { modelName, fieldName, len: this.state.options.length });
      } catch (e) {
        // console.error(TAG, "fields_get failed", e);
        this.state.options = [];
      } finally {
        this.state.loading = false;
      }
    });
  }
}
SelectionSubparts.template = "sat.SelectionSubparts";
SelectionSubparts.props = {
  value: { type: [String, Number, Boolean], optional: true },
  selectionList: { type: Array, optional: true },
  readonly: { type: Boolean, optional: true },
  onChange: { type: Function, optional: true },
  id: { type: [String, Number], optional: true },
  name: { type: String, optional: true },   // p.ej. "black_id"
  record: { type: Object, optional: true }, // contiene model/data
};

const fieldRegistry = registry.category("fields");
fieldRegistry.add("selection_subparts", {
  component: SelectionSubparts,
  supportedTypes: ["selection"],

  extractProps: (args) => {
    const { record, value, attrs, viewType = args.viewType } = args;
    const fieldName = args.name;

    // =============== TODOS LOS ORÍGENES POSIBLES EN EL CLIENTE ===============
    // (el nativo suele usar fieldsInfo[viewType][fieldName])
    const selField     = args?.field?.selection || args?.field?.params?.selection;
    const selFieldsInf = record?.model?.fieldsInfo?.[viewType]?.[fieldName]?.selection;
    const selRootFInf  = record?.model?.root?.fieldsInfo?.[viewType]?.[fieldName]?.selection;
    const selRootFlds  = record?.model?.root?.fields?.[fieldName]?.selection;
    const selAttrs     = args?.attrs?.selection;
    const selection    = selField || selFieldsInf || selRootFInf || selRootFlds || selAttrs || [];
    // ========================================================================

    const currentValue = value !== undefined ? value : record?.data?.[fieldName];
    const readonly     = Boolean(attrs?.readonly) || Boolean(record?.isReadonly);

    const onChange = (ev) => {
      const newVal = ev.target.value;
      if (record && typeof record.update === "function") {
        record.update({ [fieldName]: newVal });
      }
    };

    // DEBUG útil (déjalo mientras pruebas)
    console.debug(TAG, "extractProps", {
      model: record?.model?.name, fieldName, viewType,
      selFieldLen: (selField || []).length,
      selFieldsInfLen: (selFieldsInf || []).length,
      selRootFInfLen: (selRootFInf || []).length,
      selRootFldsLen: (selRootFlds || []).length,
      selAttrsLen: (selAttrs || []).length,
      finalLen: selection.length,
      readonly, value: currentValue,
    });

    return {
      value: currentValue,
      selectionList: selection,   // si va vacío, el componente hará RPC en onWillStart
      readonly,
      onChange,
      name: fieldName,
      record: record,
    };
  },

  isEmpty: ({ value }) => value === undefined || value === null || value === "",
});
