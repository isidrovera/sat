/** @odoo-module **/

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { useState } from "@odoo/owl";

const ACCION_LABELS = {
    cambiado: "Cambiado",
    ajustado: "Ajustado",
    limpieza: "Limpieza",
    diagnosticado: "Diagnosticado",
    na: "No aplica",
};

export class ReparacionSubpartesSelectorField extends X2ManyField {
    static template = "sat.ReparacionSubpartesSelector";

    setup() {
        super.setup();

        this.uiState = useState({
            collapsed: {},
        });

        console.log("[ReparacionSubpartesSelector][setup]", {
            fieldName: this.props.name,
            recordsCount: this.list?.records?.length || 0,
            records: this.list?.records || [],
        });
    }

    get groupedRecords() {
        const groups = {};

        for (const record of this.list.records) {
            const key = record.data.componente_display || "Sin componente";

            if (!groups[key]) {
                groups[key] = {
                    name: key,
                    records: [],
                };
            }

            groups[key].records.push(record);
        }

        const result = Object.values(groups);

        console.log("[ReparacionSubpartesSelector][groupedRecords]", {
            groupsCount: result.length,
            groups: result.map((g) => ({
                name: g.name,
                recordsCount: g.records.length,
            })),
        });

        return result;
    }

    get totalSelected() {
        return this.list.records.filter((record) => record.data.selected).length;
    }

    get totalRecords() {
        return this.list.records.length;
    }

    getGroupStats(group) {
        const total = group.records.length;
        const selected = group.records.filter((record) => record.data.selected).length;

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

    getSubparteName(record) {
        const value = record.data.subparte_id;

        if (!value) {
            return "Sin subparte";
        }

        if (Array.isArray(value)) {
            return value[1] || "Sin subparte";
        }

        if (typeof value === "object") {
            return value.display_name || value.name || "Sin subparte";
        }

        return String(value);
    }

    getAccionLabel(value) {
        return ACCION_LABELS[value] || value || "Sin acción";
    }

    isCollapsed(groupName) {
        return !!this.uiState.collapsed[groupName];
    }

    toggleGroup(ev, groupName) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();

            if (ev.stopImmediatePropagation) {
                ev.stopImmediatePropagation();
            }
        }

        this.uiState.collapsed[groupName] = !this.uiState.collapsed[groupName];

        console.log("[ReparacionSubpartesSelector][toggleGroup]", {
            groupName,
            collapsed: this.uiState.collapsed[groupName],
        });
    }

    async onCardClick(record, ev = null) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();

            if (ev.stopImmediatePropagation) {
                ev.stopImmediatePropagation();
            }
        }

        const newSelected = !record.data.selected;

        console.log("[ReparacionSubpartesSelector][onCardClick]", {
            recordId: record.resId,
            subparte: this.getSubparteName(record),
            selectedBefore: record.data.selected,
            selectedAfter: newSelected,
            cantidadBefore: record.data.cantidad,
        });

        await record.update({
            selected: newSelected,
        });

        if (newSelected && (!record.data.cantidad || record.data.cantidad === 0)) {
            await record.update({
                cantidad: 1,
            });
        }

        console.log("[ReparacionSubpartesSelector][onCardClick] actualizado", {
            recordId: record.resId,
            selected: record.data.selected,
            cantidad: record.data.cantidad,
        });
    }

    async onIncrement(ev, record) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();

            if (ev.stopImmediatePropagation) {
                ev.stopImmediatePropagation();
            }
        }

        const current = record.data.cantidad || 0;
        const next = current + 1;

        console.log("[ReparacionSubpartesSelector][onIncrement]", {
            recordId: record.resId,
            current,
            next,
        });

        await record.update({
            cantidad: next,
            selected: true,
        });
    }

    async onDecrement(ev, record) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();

            if (ev.stopImmediatePropagation) {
                ev.stopImmediatePropagation();
            }
        }

        const current = record.data.cantidad || 1;
        const next = current > 1 ? current - 1 : 1;

        console.log("[ReparacionSubpartesSelector][onDecrement]", {
            recordId: record.resId,
            current,
            next,
        });

        await record.update({
            cantidad: next,
        });
    }

    async onActionChange(ev, record) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();

            if (ev.stopImmediatePropagation) {
                ev.stopImmediatePropagation();
            }
        }

        const value = ev.target.value;

        console.log("[ReparacionSubpartesSelector][onActionChange]", {
            recordId: record.resId,
            oldValue: record.data.accion_sub,
            newValue: value,
        });

        await record.update({
            accion_sub: value,
            selected: true,
        });
    }

    async onCodigoChange(ev, record) {
        if (ev) {
            ev.stopPropagation();

            if (ev.stopImmediatePropagation) {
                ev.stopImmediatePropagation();
            }
        }

        const value = ev.target.value || "";

        console.log("[ReparacionSubpartesSelector][onCodigoChange]", {
            recordId: record.resId,
            oldValue: record.data.codigo,
            newValue: value,
        });

        await record.update({
            codigo: value,
        });
    }

    async onNotaChange(ev, record) {
        if (ev) {
            ev.stopPropagation();

            if (ev.stopImmediatePropagation) {
                ev.stopImmediatePropagation();
            }
        }

        const value = ev.target.value || "";

        console.log("[ReparacionSubpartesSelector][onNotaChange]", {
            recordId: record.resId,
            oldValue: record.data.nota,
            newValue: value,
        });

        await record.update({
            nota: value,
        });
    }
}

export const reparacionSubpartesSelectorField = {
    ...x2ManyField,
    component: ReparacionSubpartesSelectorField,
};

registry.category("fields").add("reparacion_subpartes_selector", reparacionSubpartesSelectorField);