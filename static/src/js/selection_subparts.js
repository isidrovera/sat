/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FieldSelection } from "@web/views/fields/selection/selection_field";

export class SelectionSubparts extends Component {
  setup() {
    this.action = useService("action");
  }

  // Handler único: actualiza el valor y luego abre el wizard según la opción
  onNativeChange(ev) {
    const newVal = ev.target?.value;
    const { record, name } = this.props;

    // 1) Actualiza el campo en el record (igual que el widget nativo)
    if (record && typeof record.update === "function") {
      record.update({ [name]: newVal });
    }

    // 2) Mapa de acciones (se puede pasar desde XML via options="{'action_map': {...}}")
    const actionMap =
      this.props.actionMap ||
      this.props.options?.action_map ||
      this.props.options?.actionMap ||
      {};

    // 3) Arma la acción y lanza el wizard
    const act = actionMap[newVal];
    if (act) {
      // Permite usar placeholders simples en context
      const ctx = Object.assign({}, act.context || {});
      if (record?.data?.id && ctx.active_id === undefined) ctx.active_id = record.data.id;
      if (record?.data?.id && ctx.default_res_id === undefined) ctx.default_res_id = record.data.id;

      this.action.doAction({
        type: "ir.actions.act_window",
        target: "new",
        views: [[false, "form"]],
        // lo que venga en el map sobrescribe lo anterior
        ...act,
        context: ctx,
      });
    }
  }
}

// Usamos el nativo FieldSelection por dentro
SelectionSubparts.components = { FieldSelection };
SelectionSubparts.template = "sat.SelectionSubpartsWrapper";

// Props que acepta el wrapper
SelectionSubparts.props = {
  value: { type: [String, Number, Boolean], optional: true },
  readonly: { type: Boolean, optional: true },
  required: { type: Boolean, optional: true },
  name: { type: String, optional: true },
  record: { type: Object, optional: true },
  selection: { type: Array, optional: true },    // lista de opciones (si el core ya la trae)
  options: { type: Object, optional: true },     // options del XML
  actionMap: { type: Object, optional: true },   // alias de options.action_map
};

// Registro en el field registry
const fieldRegistry = registry.category("fields");
fieldRegistry.add("selection_subparts", {
  component: SelectionSubparts,
  supportedTypes: ["selection"],

  // Delegamos casi todo al core; sólo recolectamos selection y props básicas
  extractProps: (args) => {
    const { record, value, attrs, viewType = args.viewType } = args;
    const name = args.name;

    // dónde puede venir la selección en el cliente
    const selField     = args?.field?.selection || args?.field?.params?.selection;
    const selFieldsInf = record?.model?.fieldsInfo?.[viewType]?.[name]?.selection;
    const selRootFInf  = record?.model?.root?.fieldsInfo?.[viewType]?.[name]?.selection;
    const selFromAttrs = args?.attrs?.selection;
    const selection    = selField || selFieldsInf || selRootFInf || selFromAttrs || [];

    const currentValue = value !== undefined ? value : record?.data?.[name];
    const readonly     = Boolean(attrs?.readonly) || Boolean(record?.isReadonly);
    const required     = Boolean(attrs?.required);

    return {
      name,
      record,
      value: currentValue,
      readonly,
      required,
      selection,          // si viniera vacío, FieldSelection igualmente sabe manejarlo
      options: args.options, // para leer options.action_map
    };
  },

  isEmpty: ({ value }) => value === undefined || value === null || value === "",
});
