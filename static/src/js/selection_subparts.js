/** @odoo-module **/

import { Component, onMounted, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const TAG = "[selection_subparts]";

export class SelectionSubparts extends Component {
  static template = "sat.SelectionSubpartsWrapper";
  
  static props = {
    ...standardFieldProps,
    actionMap: { type: Object, optional: true },
  };

  setup() {
    this.action = useService("action");
    this.selectRef = useRef("selectElement");

    onMounted(() => {
      const selectEl = this.selectRef.el;
      if (selectEl) {
        console.debug(TAG, "onMounted: elemento <select> encontrado");
      } else {
        console.warn(TAG, "onMounted: no se encontró el elemento <select>");
      }
    });
  }

  /**
   * Obtiene las opciones del campo selection
   */
  get selectionOptions() {
    const { record, name } = this.props;
    if (!record || !name) return [];
    
    // Odoo 18: la selection está en record.fields[name].selection
    const field = record.fields[name];
    return field?.selection || [];
  }

  /**
   * Obtiene el valor actual del campo
   */
  get currentValue() {
    const { record, name } = this.props;
    if (!record || !name) return undefined;
    return record.data[name];
  }

  /**
   * Handler cuando cambia el valor del select
   */
  onNativeChange(ev) {
    const newVal = ev?.target?.value;
    const { record, name } = this.props;

    console.debug(TAG, "onNativeChange", {
      fieldName: name,
      oldValue: this.currentValue,
      newValue: newVal,
      recordId: record?.resId,
    });

    // 1) Actualizar el valor en el record
    if (newVal !== this.currentValue) {
      record.update({ [name]: newVal }).catch((e) => {
        console.error(TAG, "Error al actualizar record", e);
      });
    }

    // 2) Obtener el action_map desde las opciones del widget
    const actionMap = this.props.actionMap || this.props.options?.action_map || {};
    
    console.debug(TAG, "actionMap disponible", actionMap);
    
    const actionConfig = actionMap[newVal];
    
    if (!actionConfig) {
      console.debug(TAG, `No hay acción configurada para el valor "${newVal}"`);
      return;
    }

    console.debug(TAG, `Ejecutando acción para "${newVal}"`, actionConfig);

    // 3) Preparar contexto
    const ctx = { ...(actionConfig.context || {}) };
    
    if (record?.resId) {
      ctx.active_id = record.resId;
      ctx.default_res_id = record.resId;
    }
    
    if (record?.resModel) {
      ctx.active_model = record.resModel;
    }

    // 4) Ejecutar la acción
    const actionPayload = {
      type: "ir.actions.act_window",
      target: "new",
      views: [[false, "form"]],
      ...actionConfig,
      context: ctx,
    };

    console.debug(TAG, "Ejecutando doAction", actionPayload);

    this.action.doAction(actionPayload).catch((e) => {
      console.error(TAG, "Error al ejecutar acción", e);
    });
  }
}

// Registro del widget
registry.category("fields").add("selection_subparts", {
  component: SelectionSubparts,
  supportedTypes: ["selection"],
});