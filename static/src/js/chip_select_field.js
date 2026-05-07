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
        this.notification = useService("notification");

        this.uiState = useState({
            options: [],
            loading: true,
            loaded: false,
            expanded: false,
            saving: false,
            saved: false,
            saveError: false,
            saveMessage: "",
        });

        this._lastTypeId = this.filterTypeId;

        console.log("[ChipSelect][setup]", {
            fieldName: this.props.name,
            relation: this.relation,
            recordModel: this.recordModel,
            recordResId: this.recordResId,
            readonly: this.props.readonly,
            filterByField: this.props.filterByField,
            filterRelation: this.props.filterRelation,
            shortenLabels: this.props.shortenLabels,
            autoSave: this.props.autoSave,
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
                this.uiState.expanded = false;
                this.loadOptions();
            }
        });
    }

    _extractTypeId(props) {
        const filterField = props.filterByField;

        if (!filterField) {
            return null;
        }

        if (!props.record || !props.record.data) {
            return null;
        }

        const val = props.record.data[filterField];

        if (!val) {
            return null;
        }

        if (Array.isArray(val)) {
            return val[0];
        }

        if (typeof val === "object") {
            return val.id || val.resId || null;
        }

        return val;
    }

    get relation() {
        return this.props.record.fields[this.props.name].relation;
    }

    get recordModel() {
        return (
            this.props.record.resModel ||
            this.props.record.modelName ||
            this.props.record.config?.resModel ||
            null
        );
    }

    get recordResId() {
        const resId = this.props.record.resId;

        if (!resId) {
            return null;
        }

        if (typeof resId === "number") {
            return resId;
        }

        if (typeof resId === "string" && /^\d+$/.test(resId)) {
            return parseInt(resId, 10);
        }

        return null;
    }

    get currentId() {
        const val = this.props.record.data[this.props.name];

        if (!val) {
            return null;
        }

        if (Array.isArray(val)) {
            return val[0];
        }

        if (typeof val === "object") {
            return val.id || val.resId || null;
        }

        return val;
    }

    get selectedOption() {
        const currentId = this.currentId;

        if (!currentId || !this.uiState.options || !this.uiState.options.length) {
            return null;
        }

        return this.uiState.options.find((option) => option.id === currentId) || null;
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

            let records = [];

            try {
                records = await this.orm.searchRead(
                    this.relation,
                    domain,
                    ["id", "name", "color"],
                    { limit: 100 }
                );
            } catch (colorErr) {
                console.warn("[ChipSelect][loadOptions] Falló lectura con color. Reintentando sin color.", {
                    fieldName: this.props.name,
                    relation: this.relation,
                    domain: domain,
                    error: colorErr,
                });

                records = await this.orm.searchRead(
                    this.relation,
                    domain,
                    ["id", "name"],
                    { limit: 100 }
                );

                records = records.map((record) => ({
                    ...record,
                    color: 0,
                }));
            }

            this.uiState.options = records;
            this.uiState.loaded = true;

            console.log("[ChipSelect][loadOptions] Opciones cargadas", {
                fieldName: this.props.name,
                relation: this.relation,
                total: records.length,
                records: records,
            });

        } catch (err) {
            console.error("[ChipSelect][loadOptions] Error cargando opciones", {
                fieldName: this.props.name,
                relation: this.relation,
                filterByField: this.props.filterByField,
                filterRelation: this.props.filterRelation,
                filterTypeId: this.filterTypeId,
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

        return `background-color: white; border-color: ${palette.border}; color: ${palette.bg};`;
    }

    getShortLabel(option) {
        if (!option || !option.name) {
            return "";
        }

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
        if (!option) {
            return false;
        }

        return option.id === this.currentId;
    }

    toggleOptions(ev = null) {
        this._stopEvent(ev);

        if (this.props.readonly) {
            return;
        }

        this.uiState.expanded = !this.uiState.expanded;

        console.log("[ChipSelect][toggleOptions]", {
            fieldName: this.props.name,
            relation: this.relation,
            expanded: this.uiState.expanded,
            currentId: this.currentId,
            selectedOption: this.selectedOption,
            optionsCount: this.uiState.options.length,
        });
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

    _resetSaveStatus() {
        this.uiState.saving = false;
        this.uiState.saved = false;
        this.uiState.saveError = false;
        this.uiState.saveMessage = "";
    }

    _markSaving() {
        this.uiState.saving = true;
        this.uiState.saved = false;
        this.uiState.saveError = false;
        this.uiState.saveMessage = "Guardando...";
    }

    _markSaved() {
        this.uiState.saving = false;
        this.uiState.saved = true;
        this.uiState.saveError = false;
        this.uiState.saveMessage = "Guardado";

        window.setTimeout(() => {
            this.uiState.saved = false;
            this.uiState.saveMessage = "";
        }, 1800);
    }

    _markSaveError(message = "No se pudo guardar") {
        this.uiState.saving = false;
        this.uiState.saved = false;
        this.uiState.saveError = true;
        this.uiState.saveMessage = message;
    }

    async select(option, ev = null) {
        this._stopEvent(ev);

        console.log("[ChipSelect][select] Click recibido", {
            fieldName: this.props.name,
            relation: this.relation,
            option: option,
            currentIdBefore: this.currentId,
            readonly: this.props.readonly,
            autoSave: this.props.autoSave,
            recordModel: this.recordModel,
            recordResId: this.recordResId,
            recordDataBefore: this.props.record && this.props.record.data,
        });

        if (this.props.readonly) {
            return;
        }

        if (!option || !option.id) {
            console.warn("[ChipSelect][select] Opción inválida", {
                fieldName: this.props.name,
                option: option,
            });
            return;
        }

        try {
            this._resetSaveStatus();

            await this.props.record.update({
                [this.props.name]: [option.id, option.name],
            });

            this.uiState.expanded = false;

            if (this.props.autoSave) {
                await this._autoSaveOption(option);
            }

            console.log("[ChipSelect][select] Estado actualizado", {
                fieldName: this.props.name,
                relation: this.relation,
                selectedId: option.id,
                selectedName: option.name,
                currentIdAfter: this.currentId,
                expanded: this.uiState.expanded,
                recordDataAfter: this.props.record && this.props.record.data,
            });

        } catch (err) {
            console.error("[ChipSelect][select] Error actualizando record", {
                fieldName: this.props.name,
                relation: this.relation,
                option: option,
                error: err,
            });

            this._markSaveError("No se pudo actualizar");
            this.notification.add("No se pudo actualizar el estado.", {
                type: "danger",
            });
        }
    }

    async _autoSaveOption(option) {
        const model = this.recordModel;
        const resId = this.recordResId;

        if (!model || !resId) {
            console.warn("[ChipSelect][_autoSaveOption] Registro sin ID real. Solo queda en memoria hasta guardar formulario.", {
                fieldName: this.props.name,
                model: model,
                resId: resId,
                record: this.props.record,
            });

            this._markSaveError("Pendiente de guardar");

            this.notification.add("Cambio pendiente. Guarda el ticket antes de salir.", {
                type: "warning",
            });

            return;
        }

        this._markSaving();

        try {
            await this.orm.write(model, [resId], {
                [this.props.name]: option.id,
            });

            this._markSaved();

            console.log("[ChipSelect][_autoSaveOption] Guardado en BD", {
                model: model,
                resId: resId,
                fieldName: this.props.name,
                selectedId: option.id,
                selectedName: option.name,
            });

        } catch (err) {
            console.error("[ChipSelect][_autoSaveOption] Error guardando en BD", {
                model: model,
                resId: resId,
                fieldName: this.props.name,
                selectedId: option.id,
                error: err,
            });

            this._markSaveError("No guardado");

            this.notification.add("No se pudo guardar automáticamente. Usa Guardar cambios antes de salir.", {
                type: "danger",
            });

            throw err;
        }
    }
}

export const chipSelectField = {
    ...many2OneField,
    component: ChipSelectField,

    extractProps({ attrs, options }) {
        const props = many2OneField.extractProps(...arguments);

        const rawAutoSave =
            (attrs && attrs.auto_save) ||
            (options && options.auto_save);

        let autoSave = true;

        if (rawAutoSave === false || rawAutoSave === "false" || rawAutoSave === "0") {
            autoSave = false;
        }

        const finalProps = {
            ...props,
            filterByField: (attrs && attrs.filter_by_field) || (options && options.filter_by_field) || null,
            filterRelation: (attrs && attrs.filter_relation) || (options && options.filter_relation) || null,
            shortenLabels: !!((attrs && attrs.shorten_labels) || (options && options.shorten_labels)),
            autoSave: autoSave,
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
        { label: "Auto save", name: "auto_save", type: "boolean" },
    ],
};

registry.category("fields").add("chip_select", chipSelectField);