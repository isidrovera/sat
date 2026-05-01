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

        console.log("[ChipSelect][setup]", {
            fieldName: this.props.name,
            relation: this.relation,
            readonly: this.props.readonly,
            filterByField: this.props.filterByField,
            filterRelation: this.props.filterRelation,
            shortenLabels: this.props.shortenLabels,
            currentId: this.currentId,
            filterTypeId: this.filterTypeId,
            recordData: this.props.record && this.props.record.data,
        });

        this.loadOptions();

        onWillUpdateProps((nextProps) => {
            const newTypeId = this._extractTypeId(nextProps);

            console.log("[ChipSelect][onWillUpdateProps]", {
                fieldName: nextProps.name,
                oldTypeId: this._lastTypeId,
                newTypeId: newTypeId,
                readonly: nextProps.readonly,
                recordData: nextProps.record && nextProps.record.data,
            });

            if (newTypeId !== this._lastTypeId) {
                this._lastTypeId = newTypeId;
                this.loadOptions();
            }
        });
    }

    _extractTypeId(props) {
        const filterField = props.filterByField;

        if (!filterField) {
            console.log("[ChipSelect][_extractTypeId] No hay filterByField");
            return null;
        }

        const val = props.record.data[filterField];

        console.log("[ChipSelect][_extractTypeId]", {
            filterField: filterField,
            value: val,
        });

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

            console.log("[ChipSelect][loadOptions] Cargando opciones", {
                fieldName: this.props.name,
                relation: this.relation,
                domain: domain,
                filterTypeId: this.filterTypeId,
                filterByField: this.props.filterByField,
                filterRelation: this.props.filterRelation,
            });

            const records = await this.orm.searchRead(
                this.relation,
                domain,
                ["id", "name", "color"],
                { limit: 100 }
            );

            console.log("[ChipSelect][loadOptions] Opciones encontradas", {
                fieldName: this.props.name,
                total: records.length,
                records: records,
            });

            this.uiState.options = records;
            this.uiState.loaded = true;

        } catch (err) {
            console.error("[ChipSelect][loadOptions] Error cargando opciones", {
                fieldName: this.props.name,
                relation: this.relation,
                error: err,
            });

            this.uiState.options = [];

        } finally {
            this.uiState.loading = false;
        }
    }

    buildDomain() {
        const typeId = this.filterTypeId;
        const filterRel = this.props.filterRelation;

        console.log("[ChipSelect][buildDomain]", {
            fieldName: this.props.name,
            typeId: typeId,
            filterRel: filterRel,
        });

        if (!typeId || !filterRel) {
            console.log("[ChipSelect][buildDomain] Sin filtro, retorna dominio vacío []");
            return [];
        }

        const domain = [
            "|",
            [filterRel, "=", false],
            [filterRel, "in", [typeId]],
        ];

        console.log("[ChipSelect][buildDomain] Dominio generado", domain);

        return domain;
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
        if (!this.props.shortenLabels) {
            return option.name;
        }

        const match = option.name.match(/(\d+%)/);

        if (match) {
            return match[1];
        }

        return option.name
            .replace(/\s+de\s+t[oó]ner/i, "")
            .replace(/T[oó]ner\s+/i, "");
    }

    isSelected(option) {
        return option.id === this.currentId;
    }

    async select(option, ev = null) {
        console.log("[ChipSelect][select] Click recibido", {
            fieldName: this.props.name,
            option: option,
            currentIdBefore: this.currentId,
            readonly: this.props.readonly,
            record: this.props.record,
            recordDataBefore: this.props.record && this.props.record.data,
        });

        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();

            if (ev.stopImmediatePropagation) {
                ev.stopImmediatePropagation();
            }

            console.log("[ChipSelect][select] Evento detenido correctamente");
        }

        if (!option || !option.id) {
            console.warn("[ChipSelect][select] Opción inválida", option);
            return;
        }

        try {
            await this.props.record.update({
                [this.props.name]: [option.id, option.name],
            });

            console.log("[ChipSelect][select] Record actualizado", {
                fieldName: this.props.name,
                selectedId: option.id,
                selectedName: option.name,
                currentIdAfter: this.currentId,
                recordDataAfter: this.props.record && this.props.record.data,
            });

        } catch (err) {
            console.error("[ChipSelect][select] Error actualizando record", {
                fieldName: this.props.name,
                option: option,
                error: err,
            });
        }
    }
}

export const chipSelectField = {
    ...many2OneField,
    component: ChipSelectField,

    extractProps({ attrs, options }) {
        const props = many2OneField.extractProps(...arguments);

        const finalProps = {
            ...props,
            filterByField: (attrs && attrs.filter_by_field) || (options && options.filter_by_field) || null,
            filterRelation: (attrs && attrs.filter_relation) || (options && options.filter_relation) || null,
            shortenLabels: !!((attrs && attrs.shorten_labels) || (options && options.shorten_labels)),
        };

        console.log("[ChipSelect][extractProps]", {
            attrs: attrs,
            options: options,
            finalProps: finalProps,
        });

        return finalProps;
    },

    supportedOptions: [
        ...(many2OneField.supportedOptions || []),
        { label: "Filter by field", name: "filter_by_field", type: "string" },
        { label: "Filter relation", name: "filter_relation", type: "string" },
        { label: "Shorten labels", name: "shorten_labels", type: "boolean" },
    ],
};

registry.category("fields").add("chip_select", chipSelectField);