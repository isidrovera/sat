/** @odoo-module **/

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { useState } from "@odoo/owl";

export class SubpartesSelectorField extends X2ManyField {
    static template = "copier_company.SubpartesSelector";

    setup() {
        super.setup();
        this.uiState = useState({ collapsed: {} });
    }

    get groupedRecords() {
        const groups = {};
        for (const record of this.list.records) {
            const key = record.data.componente_display || "Sin componente";
            if (!groups[key]) {
                groups[key] = { name: key, records: [] };
            }
            groups[key].records.push(record);
        }
        return Object.values(groups);
    }

    getGroupStats(group) {
        const total = group.records.length;
        const selected = group.records.filter(r => r.data.selected).length;
        return { total, selected };
    }

    getInitials(name) {
        if (!name) return "?";
        return name.split(" ")
            .map(w => w[0])
            .join("")
            .toUpperCase()
            .slice(0, 2);
    }

    async onCardClick(record) {
        const newSelected = !record.data.selected;
        await record.update({ selected: newSelected });
        if (newSelected && (!record.data.cantidad || record.data.cantidad === 0)) {
            await record.update({ cantidad: 1 });
        }
    }

    async onIncrement(ev, record) {
        ev.stopPropagation();
        const current = record.data.cantidad || 0;
        await record.update({ cantidad: current + 1 });
    }

    async onDecrement(ev, record) {
        ev.stopPropagation();
        const current = record.data.cantidad || 1;
        if (current > 1) {
            await record.update({ cantidad: current - 1 });
        }
    }

    toggleGroup(groupName) {
        this.uiState.collapsed[groupName] = !this.uiState.collapsed[groupName];
    }

    isCollapsed(groupName) {
        return !!this.uiState.collapsed[groupName];
    }

    get totalSelected() {
        return this.list.records.filter(r => r.data.selected).length;
    }
}

export const subpartesSelectorField = {
    ...x2ManyField,
    component: SubpartesSelectorField,
};

registry.category("fields").add("subpartes_selector", subpartesSelectorField);