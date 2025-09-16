/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";

// Registrar alias: tu nombre → componente nativo
registry.category("view_widgets").add("selection_subparts", {
    component: SelectionField,
});
