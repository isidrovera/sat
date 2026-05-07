/** @odoo-module **/

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { useState } from "@odoo/owl";

export class SubpartesSelectorField extends X2ManyField {
    static template = "sat.SubpartesSelector";

    setup() {
        super.setup();

        this.uiState = useState({
            collapsed: {},
        });

        /*
         * Funciones puente.
         * Importante para móvil y wizard modal:
         * evita que OWL pierda el contexto de "this".
         */
        this.onToggleGroupSafe = (groupName, ev = null) => {
            return this.toggleGroup(groupName, ev);
        };

        this.onCardClickSafe = (record, ev = null) => {
            return this.onCardClick(record, ev);
        };

        this.onIncrementSafe = (record, ev = null) => {
            return this.onIncrement(record, ev);
        };

        this.onDecrementSafe = (record, ev = null) => {
            return this.onDecrement(record, ev);
        };

        console.log("[SubpartesSelector][setup]", {
            totalRecords: this.list?.records?.length || 0,
            props: this.props,
            list: this.list,
        });
    }

    get groupedRecords() {
        const groups = {};
        const records = this.list?.records || [];

        for (const record of records) {
            const key = record.data.componente_display || "Sin componente";

            if (!groups[key]) {
                groups[key] = {
                    name: key,
                    records: [],
                };
            }

            groups[key].records.push(record);
        }

        return Object.values(groups);
    }

    getGroupStats(group) {
        const records = group?.records || [];
        const total = records.length;
        const selected = records.filter((record) => !!record.data.selected).length;

        return {
            total,
            selected,
        };
    }

    getInitials(name) {
        if (!name) {
            return "?";
        }

        return name
            .split(" ")
            .filter(Boolean)
            .map((word) => word[0])
            .join("")
            .toUpperCase()
            .slice(0, 2);
    }

    _stopEvent(ev = null) {
        if (!ev) {
            return;
        }

        ev.preventDefault();
        ev.stopPropagation();

        if (ev.stopImmediatePropagation) {
            ev.stopImmediatePropagation();
        }
    }

    async onCardClick(record, ev = null) {
        this._stopEvent(ev);

        if (!record) {
            console.warn("[SubpartesSelector][onCardClick] record vacío");
            return;
        }

        try {
            const newSelected = !record.data.selected;

            console.log("[SubpartesSelector][onCardClick]", {
                recordId: record.id,
                oldSelected: record.data.selected,
                newSelected: newSelected,
                data: record.data,
            });

            await record.update({
                selected: newSelected,
            });

            if (newSelected && (!record.data.cantidad || record.data.cantidad === 0)) {
                await record.update({
                    cantidad: 1,
                });
            }

        } catch (err) {
            console.error("[SubpartesSelector][onCardClick] Error", err);
        }
    }

    async onIncrement(record, ev = null) {
        this._stopEvent(ev);

        if (!record) {
            console.warn("[SubpartesSelector][onIncrement] record vacío");
            return;
        }

        try {
            const current = record.data.cantidad || 0;

            await record.update({
                cantidad: current + 1,
            });

            console.log("[SubpartesSelector][onIncrement]", {
                recordId: record.id,
                oldCantidad: current,
                newCantidad: current + 1,
            });

        } catch (err) {
            console.error("[SubpartesSelector][onIncrement] Error", err);
        }
    }

    async onDecrement(record, ev = null) {
        this._stopEvent(ev);

        if (!record) {
            console.warn("[SubpartesSelector][onDecrement] record vacío");
            return;
        }

        try {
            const current = record.data.cantidad || 1;

            if (current > 1) {
                await record.update({
                    cantidad: current - 1,
                });

                console.log("[SubpartesSelector][onDecrement]", {
                    recordId: record.id,
                    oldCantidad: current,
                    newCantidad: current - 1,
                });
            }

        } catch (err) {
            console.error("[SubpartesSelector][onDecrement] Error", err);
        }
    }

    toggleGroup(groupName, ev = null) {
        this._stopEvent(ev);

        if (!groupName) {
            return;
        }

        this.uiState.collapsed[groupName] = !this.uiState.collapsed[groupName];

        console.log("[SubpartesSelector][toggleGroup]", {
            groupName: groupName,
            collapsed: this.uiState.collapsed[groupName],
        });
    }

    isCollapsed(groupName) {
        return !!this.uiState.collapsed[groupName];
    }

    get totalSelected() {
        const records = this.list?.records || [];
        return records.filter((record) => !!record.data.selected).length;
    }
}

export const subpartesSelectorField = {
    ...x2ManyField,
    component: SubpartesSelectorField,
};

registry.category("fields").add("subpartes_selector", subpartesSelectorField);