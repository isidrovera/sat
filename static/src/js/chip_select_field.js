/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Many2OneField, many2OneField } from "@web/views/fields/many2one/many2one_field";
import { useState, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const ODOO_COLOR_MAP = {
    0:  { bg: "#6c757d", border: "#adb5bd", text: "#495057" },
    1:  { bg: "#e24b4a", border: "#e24b4a", text: "#ffffff" },
    2:  { bg: "#f06050", border: "#f06050", text: "#ffffff" },
    3:  { bg: "#ba7517", border: "#ba7517", text: "#ffffff" },
    4:  { bg: "#cb9a4a", border: "#cb9a4a", text: "#ffffff" },
    5:  { bg: "#9c5b9d", border: "#9c5b9d", text: "#ffffff" },
    6:  { bg: "#5b899e", border: "#5b899e", text: "#ffffff" },
    7:  { bg: "#1f6abb", border: "#1f6abb", text: "#ffffff" },
    8:  { bg: "#4f8e8a", border: "#4f8e8a", text: "#ffffff" },
    9:  { bg: "#9b59b6", border: "#9b59b6", text: "#ffffff" },
    10: { bg: "#639922", border: "#639922", text: "#ffffff" },
    11: { bg: "#a8587b", border: "#a8587b", text: "#ffffff" },
};

export class ChipSelectField extends Many2OneField {
    static template = "sat.ChipSelectField";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.uiState = useState({
            options: [],
            loading: true,
            loaded: false,
        });
        this._lastTypeId = this.filterTypeId;
        this.loadOptions();

        onWillUpdateProps((nextProps) => {
            // Detectar si cambió el tipo de componente
            const newTypeId = this._extractTypeId(nextProps);
            if (newTypeId !== this._lastTypeId) {
                this._lastTypeId = newTypeId;
                this.loadOptions();
            }
        });
    }

    _extractTypeId(props) {
        const filterField = props.filterByField;
        if (!filterField) return null;
        const val = props.record.data[filterField];
        if (!val) return null;
        if (Array.isArray(val)) return val[0];
        if (typeof val === "object") return val.id;
        return val;
    }

    get relation() {
        return this.props.record.fields[this.props.name].relation;
    }

    get currentId() {
        const val = this.props.record.data[this.props.name];
        if (!val) return null;
        if (Array.isArray(val)) return val[0];
        if (typeof val === "object") return val.id;
        return val;
    }

    get filterTypeId() {
        return this._extractTypeId(this.props);
    }

    async loadOptions() {
        this.uiState.loading = true;
        try {
            const domain = this.buildDomain();
            console.log("[ChipSelect]", this.props.name, "domain:", JSON.stringify(domain), "typeId:", this.filterTypeId);
            const records = await this.orm.searchRead(
                this.relation,
                domain,
                ["id", "name", "color"],
                { limit: 100 }
            );
            console.log("[ChipSelect]", this.props.name, "results:", records.length);
            this.uiState.options = records;
            this.uiState.loaded = true;
        } catch (err) {
            console.error("[ChipSelect] Error cargando opciones:", err);
            this.uiState.options = [];
        } finally {
            this.uiState.loading = false;
        }
    }

    buildDomain() {
        const typeId = this.filterTypeId;
        const filterRel = this.props.filterRelation;

        // Sin filtro configurado o sin tipo seleccionado → traer todo
        if (!typeId || !filterRel) {
            return [];
        }

        // Estados sin tipos asignados (aplican a todos) OR estados con este tipo
        return [
            "|",
            [filterRel, "=", false],
            [filterRel, "in", [typeId]],
        ];
    }

    getChipStyle(option, isSelected) {
        const colorIdx = option.color || 0;
        const palette = ODOO_COLOR_MAP[colorIdx] || ODOO_COLOR_MAP[0];

        if (isSelected) {
            return `background-color: ${palette.bg}; border-color: ${palette.border}; color: ${palette.text};`;
        }
        return `background-color: white; border-color: ${palette.border}; color: ${palette.bg};`;
    }

    getShortLabel(option) {
        if (!this.props.shortenLabels) return option.name;
        const match = option.name.match(/(\d+%)/);
        if (match) return match[1];
        return option.name.replace(/\s+de\s+t[oó]ner/i, "").replace(/T[oó]ner\s+/i, "");
    }

    isSelected(option) {
        return option.id === this.currentId;
    }

    async select(option) {
        if (this.props.readonly) return;
        await this.props.record.update({
            [this.props.name]: [option.id, option.name],
        });
    }
}

export const chipSelectField = {
    ...many2OneField,
    component: ChipSelectField,
    extractProps({ attrs, options }) {
        const props = many2OneField.extractProps(...arguments);
        return {
            ...props,
            filterByField: (attrs && attrs.filter_by_field) || (options && options.filter_by_field) || null,
            filterRelation: (attrs && attrs.filter_relation) || (options && options.filter_relation) || null,
            shortenLabels: !!((attrs && attrs.shorten_labels) || (options && options.shorten_labels)),
        };
    },
    supportedOptions: [
        ...(many2OneField.supportedOptions || []),
        { label: "Filter by field", name: "filter_by_field", type: "string" },
        { label: "Filter relation", name: "filter_relation", type: "string" },
        { label: "Shorten labels", name: "shorten_labels", type: "boolean" },
    ],
};

registry.category("fields").add("chip_select", chipSelectField);