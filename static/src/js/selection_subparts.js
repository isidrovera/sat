/** @odoo-module **/

import { Component, onMounted, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const TAG = "[selection_subparts]";

export class SelectionSubparts extends Component {
  setup() {
    this.action = useService("action");
    this.host = useRef("host"); // wrapper contenedor para enganchar el <select>

    // Listener de respaldo directo al <select> interno
    onMounted(() => {
      const root = this.host.el;
      if (!root) {
        console.warn(TAG, "onMounted: host.el no disponible");
        return;
      }
      // intenta localizar el <select> que renderiza el widget nativo
      const sel = root.querySelector("select");
      if (!sel) {
        console.warn(TAG, "onMounted: no encontré <select> dentro del CoreSelection");
      } else {
        console.debug(TAG, "onMounted: enganchando listener directo al <select>");
        sel.addEventListener("change", (ev) => {
          console.debug(TAG, "listener <select> (backup) change:", ev.target.value);
          this.onNativeChange(ev); // reusa el mismo handler
        });
      }
    });
  }

  // Handler principal (lo dispara el nativo y el backup)
  onNativeChange(ev) {
    const newVal = ev?.target?.value;
    const { record, name, options } = this.props;

    console.debug(TAG, "onNativeChange start", {
      fieldName: name,
      newVal,
      hasRecord: !!record,
      recId: record?.data?.id,
      currentValue: record?.data?.[name],
      options,
    });

    // 1) actualiza el valor en el record (igual que el core)
    try {
      if (record && typeof record.update === "function" && name) {
        record.update({ [name]: newVal });
        console.debug(TAG, "record.update OK", { [name]: newVal });
      } else {
        console.warn(TAG, "record.update NO ejecutado (falta record o name)");
      }
    } catch (e) {
      console.error(TAG, "record.update lanzó error", e);
    }

    // 2) obtener el mapa de acciones
    const actionMap =
      this.props.actionMap ||
      options?.action_map ||
      options?.actionMap ||
      {};

    console.debug(TAG, "action_map", actionMap);
    const act = actionMap[newVal];
    console.debug(TAG, "action_map[newVal]", { newVal, act });

    if (!act) {
      console.warn(TAG, `No hay acción para el valor "${newVal}". ¿La key coincide exactamente?`);
      return;
    }

    // 3) armar contexto y disparar doAction
    const ctx = { ...(act.context || {}) };
    if (record?.data?.id && ctx.active_id === undefined) ctx.active_id = record.data.id;
    if (record?.model?.name && ctx.active_model === undefined) ctx.active_model = record.model.name;
    if (record?.data?.id && ctx.default_res_id === undefined) ctx.default_res_id = record.data.id;

    const actionPayload = {
      type: "ir.actions.act_window",
      target: "new",
      views: [[false, "form"]],
      ...act,
      context: ctx,
    };
    console.debug(TAG, "doAction payload", actionPayload);

    try {
      const p = this.action.doAction(actionPayload);
      // en algunas versiones retorna promesa
      if (p && typeof p.then === "function") {
        p.then(() => console.debug(TAG, "doAction resolved")).catch((e) => {
          console.error(TAG, "doAction rejected", e);
        });
      }
    } catch (e) {
      console.error(TAG, "doAction threw", e);
    }
  }
}

// Tomamos el componente nativo desde el registry
const fieldsRegistry = registry.category("fields");
const coreSelectionDef = fieldsRegistry.get("selection"); // { component, ... }
SelectionSubparts.components = { CoreSelection: coreSelectionDef?.component };

SelectionSubparts.template = "sat.SelectionSubpartsWrapper";

// Props esperadas
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

    // Fallbacks de selección (el core igualmente la conoce)
    const selection =
      args?.field?.selection ||
      record?.model?.fieldsInfo?.[viewType]?.[name]?.selection ||
      args?.attrs?.selection ||
      [];

    const currentValue = value !== undefined ? value : record?.data?.[name];
    const readonly = Boolean(attrs?.readonly) || Boolean(record?.isReadonly);
    const required = Boolean(attrs?.required);

    console.debug(TAG, "extractProps", {
      model: record?.model?.name, fieldName: name,
      selLen: (selection || []).length,
      value: currentValue, readonly, required,
      options: args.options,
    });

    return { name, record, value: currentValue, readonly, required, selection, options: args.options };
  },
  isEmpty: ({ value }) => value === undefined || value === null || value === "",
});
