/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// Wrapper: usa el selection nativo si hay record+name; si no, fallback <select>
export class SelectionSubparts extends Component {
  setup() {
    this.action = useService("action");
  }

  onNativeChange(ev) {
    const newVal = ev.target?.value;
    const { record, name } = this.props;

    if (record && typeof record.update === "function") {
      record.update({ [name]: newVal });
    }

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

  // Fallback simple cuando no hay record/name (evita crash)
  onFallbackChange(ev) {
    // Sólo disparamos acciones; no podemos hacer record.update sin record
    const newVal = ev.target?.value;
    const actionMap =
      this.props.actionMap ||
      this.props.options?.action_map ||
      this.props.options?.actionMap ||
      {};
    const act = actionMap?.[newVal];
    if (act) this.action.doAction({ type: "ir.actions.act_window", target: "new", views: [[false, "form"]], ...act });
  }
}

// Tomamos el selection nativo desde el registry (compatible Odoo 16/17/18)
const fieldsRegistry = registry.category("fields");
const coreSelectionDef = fieldsRegistry.get("selection");
SelectionSubparts.components = { CoreSelection: coreSelectionDef?.component };

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

// Registro del widget
fieldsRegistry.add("selection_subparts", {
  component: SelectionSubparts,
  supportedTypes: ["selection"],
  extractProps: (args) => {
    const { record, value, attrs, viewType = args.viewType } = args;
    const name = args.name || args.field?.name || null;

    // intenta varios orígenes para la lista
    const selection =
      args?.field?.selection ||
      record?.model?.fieldsInfo?.[viewType]?.[name]?.selection ||
      record?.model?.root?.fieldsInfo?.[viewType]?.[name]?.selection ||
      args?.attrs?.selection ||
      [];

    const currentValue = value !== undefined ? value : record?.data?.[name];
    const readonly = Boolean(attrs?.readonly) || Boolean(record?.isReadonly);
    const required = Boolean(attrs?.required);

    return { name, record, value: currentValue, readonly, required, selection, options: args.options };
  },
  isEmpty: ({ value }) => value === undefined || value === null || value === "",
});
