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

    // Improved selection extraction with better debugging
    let selection = [];
    
    // Try multiple sources for selection data
    if (field?.selection) {
      selection = field.selection;
      console.debug(TAG, "Selection found in field.selection", selection);
    } else if (field?.params?.selection) {
      selection = field.params.selection;
      console.debug(TAG, "Selection found in field.params.selection", selection);
    } else if (record?.model?.fields?.[fieldName]?.selection) {
      selection = record.model.fields[fieldName].selection;
      console.debug(TAG, "Selection found in record.model.fields", selection);
    } else if (attrs?.selection) {
      selection = attrs.selection;
      console.debug(TAG, "Selection found in attrs.selection", selection);
    } else if (args.options?.selection) {
      selection = args.options.selection;
      console.debug(TAG, "Selection found in args.options.selection", selection);
    } else {
      // Fallback: try to get from field definition in different ways
      const fieldDef = record?.model?.fields?.[fieldName];
      if (fieldDef) {
        // Check if it's a function that needs to be called
        if (typeof fieldDef.selection === 'function') {
          try {
            selection = fieldDef.selection();
            console.debug(TAG, "Selection obtained from function call", selection);
          } catch (error) {
            console.error(TAG, "Error calling selection function", error);
          }
        } else if (fieldDef.type === 'selection' && fieldDef.selection) {
          selection = fieldDef.selection;
          console.debug(TAG, "Selection found in fieldDef.selection", selection);
        }
      }
    }

    // Ensure selection is an array and has the correct format
    if (!Array.isArray(selection)) {
      console.warn(TAG, "Selection is not an array, converting:", selection);
      selection = [];
    }

    // Validate selection format - should be array of [value, label] pairs
    selection = selection.filter(item => {
      if (Array.isArray(item) && item.length >= 2) {
        return true;
      }
      console.warn(TAG, "Invalid selection item format:", item);
      return false;
    });

    const currentValue = value !== undefined ? value : record?.data?.[fieldName];
    const readonly = Boolean(attrs?.readonly) || Boolean(record?.isReadonly);

    const onChange = (ev) => {
      const newVal = ev.target.value;
      console.debug(TAG, "onChange", { fieldName, newVal, hasRecord: !!record });
      if (record && typeof record.update === 'function') {
        record.update({ [fieldName]: newVal });
      } else {
        console.warn(TAG, "Cannot update record - record.update not available");
      }
    };

    // Enhanced diagnostic logs
    console.debug(TAG, "extractProps", {
      model: record?.model?.name,
      fieldName,
      type_from_field: field?.type,
      field_has_selection: !!field?.selection,
      field_params_has_selection: !!field?.params?.selection,
      model_has_field: !!record?.model?.fields?.[fieldName],
      model_field_has_selection: !!record?.model?.fields?.[fieldName]?.selection,
      attrs_has_selection: !!attrs?.selection,
      options_has_selection: !!args.options?.selection,
      finalSelectionLength: selection.length,
      readonly,
      value: currentValue,
      args: args, // Full args for debugging
    });

    // Validation warnings
    if (!fieldName) {
      console.error(TAG, "CRITICAL: No fieldName found. Check widget usage in view. Args:", args);
    }
    
    if (!selection.length) {
      console.error(TAG, "CRITICAL: EMPTY selectionList — el <select> no tendrá opciones");
      console.error(TAG, "Field definition:", field);
      console.error(TAG, "Record model fields:", record?.model?.fields);
      console.error(TAG, "Attrs:", attrs);
      console.error(TAG, "Full args object:", args);
      
      // Try to provide helpful suggestions
      if (field?.type !== 'selection') {
        console.error(TAG, "Field type is not 'selection', it's:", field?.type);
      }
      
      // Provide empty option to prevent complete failure
      selection = [['', 'No options available']];
    }

    return { 
      value: currentValue, 
      selectionList: selection, 
      readonly, 
      onChange,
      id: args.id,
      name: fieldName,
      record: record
    };
  },

  isEmpty: ({ value }) => value === undefined || value === null || value === "",
});