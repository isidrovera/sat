/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// Wrapper: usa el selection nativo y al cambiar abre wizard según el valor
export class SelectionSubparts extends Component {
  setup() {
    this.action = useService("action");
  }

  onNativeChange(ev) {
    const newVal = ev?.target?.value;
    const { record, name } = this.props;

    // 1) actualiza el valor en el record (como hace el core)
    if (record && typeof record.update === "function" && name) {
      record.update({ [name]: newVal });
    }

    // 2) lee el mapa de acciones (desde options.action_map o actionMap)
    const actionMap =
      this.props.actionMap ||
      this.props.options?.action_map ||
      this.props.options?.actionMap ||
      {};

    const act = actionMap[newVal];
    if (!act) return; // nada que abrir para esa opción

    // 3) arma contexto y abre wizard
    const ctx = { ...(act.context || {}) };
    if (record?.data?.id && ctx.active_id === undefined) ctx.active_id = record.data.id;
    if (record?.data?.id && ctx.active_model === undefined) ctx.active_model = record?.model?.name;
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

// Tomamos el componente nativo desde el registry (compatible 16/17/18)
const fieldsRegistry = registry.category("fields");
const coreSelectionDef = fieldsRegistry.get("selection");
SelectionSubparts.components = { CoreSelection: coreSelectionDef?.component };

SelectionSubparts.template = "sat.SelectionSubpartsWrapper";

// Props básicas que pasan los Fields
SelectionSubparts.props = {
  value: { type: [String, Number, Boolean], optional: true },
  readonly: { type: Boolean, optional: true },
  required: { type: Boolean, optional: true },
  name: { type: String, optional: true },
  record: { type: Object, optional: true },
  selection: { type: Array, optional: true }, // (el core ya la trae)
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

    // El core sabe de dónde sacar la selección; enviamos lo básico
    const currentValue = value !== undefined ? value : record?.data?.[name];
    const readonly = Boolean(attrs?.readonly) || Boolean(record?.isReadonly);
    const required = Boolean(attrs?.required);

    // Fallback por si quieres forzar desde XML: selection="[(...)]"
    const selection =
      args?.field?.selection ||
      record?.model?.fieldsInfo?.[viewType]?.[name]?.selection ||
      args?.attrs?.selection ||
      [];

    return { name, record, value: currentValue, readonly, required, selection, options: args.options };
  },
  isEmpty: ({ value }) => value === undefined || value === null || value === "",
});
