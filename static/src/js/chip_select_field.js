/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Many2OneField, many2OneField } from "@web/views/fields/many2one/many2one_field";
import { useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// Mapeo paleta de colores Odoo (0-11) → CSS
const ODOO_COLOR_MAP = {
    0:  { bg: "#6c757d", border: "#adb5bd", text: "#495057" },  // Gris
    1:  { bg: "#e24b4a", border: "#e24b4a", text: "#ffffff" },  // Rojo
    2:  { bg: "#f06050", border: "#f06050", text: "#ffffff" },  // Naranja claro
    3:  { bg: "#ba7517", border: "#ba7517", text: "#ffffff" },  // Naranja
    4:  { bg: "#cb9a4a", border: "#cb9a4a", text: "#ffffff" },  // Amarillo
    5:  { bg: "#9c5b9d", border: "#9c5b9d", text: "#ffffff" },  // Morado
    6:  { bg: "#5b899e", border: "#5b899e", text: "#ffffff" },  // Azul claro
    7:  { bg: "#1f6abb", border: "#1f6abb", text: "#ffffff" },  // Azul
    8:  { bg: "#4f8e8a", border: "#4f8e8a", text: "#ffffff" },  // Verde azulado
    9:  { bg: "#9b59b6", border: "#9b59b6", text: "#ffffff" },  // Violeta
    10: { bg: "#639922", border: "#639922", text: "#ffffff" },  // Verde
    11: { bg: "#a8587b", border: "#a8587b", text: "#ffffff" },  // Rosa
};

export class ChipSelectField extends Many2OneField {
    static template = "sat.ChipSelectField";

    static props = {
        ...Many2OneField.props,
        filterByField: { type: String, optional: true },  // ej: "componente_tipo_id"
        filterRelation: { type: String, optional: true },  // ej: "componente_tipo_ids"
        shortenLabels: { type: Boolean, optional: true },  // Acortar nombres tipo "Tóner 30%" → "30%"
    };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.uiState = useState({
            options: [],
            loading: true,
            loaded: false,
            expanded: false,
        });
        this.loadOptions();
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

    get currentOption() {
        return this.uiState.options.find(o => o.id === this.currentId);
    }

    get filterTypeId() {
        // ID del tipo de componente/accesorio en la línea actual
        const filterField = this.props.filterByField;
        if (!filterField) return null;
        const val = this.props.record.data[filterField];
        if (!val) return null;
        if (Array.isArray(val)) return val[0];
        if (typeof val === "object") return val.id;
        return val;
    }

    async loadOptions() {
        this.uiState.loading = true;
        try {
            const domain = this.buildDomain();
            const records = await this.orm.searchRead(
                this.relation,
                domain,
                ["id", "name", "code", "color"],
                { limit: 100 }
            );
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
        // Filtro: estados que aplican al tipo de componente actual
        // O estados sin filtro (componente_tipo_ids vacío = aplica a todos)
        const typeId = this.filterTypeId;
        const filterRel = this.props.filterRelation;

        if (!typeId || !filterRel) {
            return [];
        }

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
        // Sin seleccionar: solo borde tintado, fondo blanco
        return `background-color: white; border-color: ${palette.border}; color: ${palette.bg};`;
    }

    getShortLabel(option) {
        if (!this.props.shortenLabels) return option.name;
        // Tóner 30% → 30%
        const match = option.name.match(/(\d+%)/);
        if (match) return match[1];
        // "Sin contenedor de tóner" → "Sin contenedor"
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

    toggleExpand() {
        this.uiState.expanded = !this.uiState.expanded;
    }

    // Cuando cambia el tipo de componente, recargar las opciones
    async onWillUpdateProps(nextProps) {
        // Detectar cambio en filterTypeId
        const prevFilter = this.filterTypeId;
        // Necesitamos re-leer después de update — Owl maneja esto automáticamente
        // Pero forzamos recarga si cambió el tipo
    }
}

// Extractor de props desde la vista XML
export const chipSelectField = {
    ...many2OneField,
    component: ChipSelectField,
    extractProps({ attrs, options }) {
        const props = many2OneField.extractProps(...arguments);
        return {
            ...props,
            filterByField: attrs.filter_by_field || options.filter_by_field,
            filterRelation: attrs.filter_relation || options.filter_relation,
            shortenLabels: !!(attrs.shorten_labels || options.shorten_labels),
        };
    },
    supportedOptions: [
        ...(many2OneField.supportedOptions || []),
        {
            label: "Filter by field",
            name: "filter_by_field",
            type: "string",
        },
        {
            label: "Filter relation",
            name: "filter_relation",
            type: "string",
        },
        {
            label: "Shorten labels",
            name: "shorten_labels",
            type: "boolean",
        },
    ],
};

registry.category("fields").add("chip_select", chipSelectField);