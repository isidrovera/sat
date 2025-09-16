/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";

// Registrar el widget para campos tipo selection
registry.category("fields").add("selection_subparts", SelectionField);
