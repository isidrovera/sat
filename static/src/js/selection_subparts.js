/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// === Wrapper que usa el widget nativo 'selection' y abre un wizard según la opción ===
export class SelectionSubparts extends Component {
  setup() {
    this.action = useService("action");
  }

  onNativeChange(ev) {
    const newVal = ev.target?.value;
    const { record, name } = this.props;

    // 1) actualizar el valor como hace el core
    if (record && typeof record.update === "function") {
      record.update({ [name]: newVal });
    }

    // 2) abrir wizard según la opción elegida
    const actionMap =
      this.props.actionMap ||
      this.props.options?.action_map ||
      this.props.options?.actionMap ||
      {};

    const act = actionMap?.[newVal];
    if (act) {
      const ctx = { ...(act.context || {}) };
      if (record?.data?.id && ctx.active_id === undefined) ctx.active_id = record.data.id;
      if (record?.data?.id && ctx.default_res_id === undefined) ctx.default_res_id = record.data.id;

      this.action.doAction({
        type: "ir.actions.act_window",
        target: "new",
        views: [[false, "form"]],
        ...act,
        context: ctx,
      });
    }
  }
}

// === Obtenemos el componente nativo del registry (no lo importamos) ===
const fieldsRegistry = registry.category("fields");
const coreSelectionDef = fieldsRegistry.get("selection"); // { component, supportedTypes, ... }
SelectionSubparts.components = { CoreSelection: coreSelectionDef.component };

SelectionSubparts.template = "sat.SelectionSubpartsWrapper";
SelectionSubparts.props = {
  value: { type: [String, Number, Boolean], optional: true },
  readonly: { type: Boolean, optional: true },
  required: { type: Boolean, optional: true },
  name: { type: String, optional: true },
  record: { type: Object, optional: true },
  selection: { type: Array, optional: true },
  options: { type: Object, optional: true },
  actionMap: { type: Object, optional: true },
};

// Registramos el widget de campo con nuestro wrapper
fieldsRegistry.add("selection_subparts", {
  component: SelectionSubparts,
  supportedTypes: ["selection"],
  extractProps: (args) => {
    const { record, value, attrs, viewType = args.viewType } = args;
    const name = args.name;

    // El core ya sabe sacar la selección; le pasamos sólo lo básico.
    const currentValue = value !== undefined ? value : record?.data?.[name];
    const readonly = Boolean(attrs?.readonly) || Boolean(record?.isReadonly);
    const required = Boolean(attrs?.required);

    // Si quieres, puedes seguir pasando una selección forzada desde la vista via attrs.selection
    const selection =
      args?.field?.selection ||
      record?.model?.fieldsInfo?.[viewType]?.[name]?.selection ||
      args?.attrs?.selection ||
      [];

    return {
      name,
      record,
      value: currentValue,
      readonly,
      required,
      selection,
      options: args.options,
    };
  },
  isEmpty: ({ value }) => value === undefined || value === null || value === "",
});
