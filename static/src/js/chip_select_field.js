/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Many2OneField, many2OneField } from "@web/views/fields/many2one/many2one_field";
import { useState, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const ODOO_COLOR_MAP = {
    0: { bg: "#6c757d", border: "#adb5bd", text: "#495057" },
    1: { bg: "#e24b4a", border: "#e24b4a", text: "#ffffff" },
    2: { bg: "#f06050", border: "#f06050", text: "#ffffff" },
    3: { bg: "#ba7517", border: "#ba7517", text: "#ffffff" },
    4: { bg: "#cb9a4a", border: "#cb9a4a", text: "#ffffff" },
    5: { bg: "#9c5b9d", border: "#9c5b9d", text: "#ffffff" },
    6: { bg: "#5b899e", border: "#5b899e", text: "#ffffff" },
    7: { bg: "#1f6abb", border: "#1f6abb", text: "#ffffff" },
    8: { bg: "#4f8e8a", border: "#4f8e8a", text: "#ffffff" },
    9: { bg: "#9b59b6", border: "#9b59b6", text: "#ffffff" },
    10: { bg: "#639922", border: "#639922", text: "#ffffff" },
    11: { bg: "#a8587b", border: "#a8587b", text: "#ffffff" },
};

function toBool(value, defaultValue = false) {
    if (value === undefined || value === null || value === "") {
        return defaultValue;
    }

    if (value === true || value === "true" || value === "1" || value === 1) {
        return true;
    }

    if (value === false || value === "false" || value === "0" || value === 0) {
        return false;
    }

    return Boolean(value);
}

function normalizeStringProp(value) {
    if (value === undefined || value === null || value === "") {
        return undefined;
    }

    if (value === false || value === "false" || value === "False") {
        return undefined;
    }

    return String(value);
}

export class ChipSelectField extends Many2OneField {
    static template = "sat.ChipSelectField";

    static props = {
        ...Many2OneField.props,

        filterByField: { type: String, optional: true },
        filterRelation: { type: String, optional: true },
        shortenLabels: { type: Boolean, optional: true },
        autoSave: { type: Boolean, optional: true },
    };

    setup() {
        super.setup();

        this.orm = useService("orm");
        this.notification = useService("notification");

        this.onToggleOptions = (ev) => {
            return this.toggleOptions(ev);
        };

        this.onSelectOption = (option, ev) => {
            return this.selectOption(option, ev);
        };

        this.uiState = useState({
            options: [],
            loading: true,
            loaded: false,
            expanded: false,
            saving: false,
            saved: false,
            saveError: false,
            saveMessage: "",
            localSelectedId: null,
        });

        this._lastTypeId = this.filterTypeId;

        console.log("[ChipSelect][setup FIX PROPS STRING]", {
            fieldName: this.props.name,
            relation: this.relation,
            readonly: this.props.readonly,
            filterByField: this.props.filterByField,
            filterRelation: this.props.filterRelation,
            shortenLabels: this.props.shortenLabels,
            autoSave: this.props.autoSave,
            recordModel: this.recordModel,
            recordResId: this.recordResId,
            currentId: this.currentId,
            recordData: this.props.record && this.props.record.data,
        });

        this.loadOptions();

        onWillUpdateProps((nextProps) => {
            const newTypeId = this._extractTypeId(nextProps);

            if (newTypeId !== this._lastTypeId) {
                this._lastTypeId = newTypeId;
                this.uiState.expanded = false;
                this.loadOptions();
            }
        });
    }

    _extractTypeId(props) {
        const filterField = props.filterByField;

        if (!filterField || !props.record || !props.record.data) {
            return null;
        }

        const val = props.record.data[filterField];

        if (!val) {
            return null;
        }

        if (Array.isArray(val)) {
            return val[0] || null;
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
            this.props.record._config?.resModel ||
            this.props.record.model?.config?.resModel ||
            null
        );
    }

    get recordResId() {
        const dataId = this.props.record.data && this.props.record.data.id;

        const resId =
            this.props.record.resId ||
            this.props.record.res_id ||
            dataId ||
            null;

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
        if (this.uiState.localSelectedId) {
            return this.uiState.localSelectedId;
        }

        const val = this.props.record.data[this.props.name];

        if (!val) {
            return null;
        }

        if (Array.isArray(val)) {
            return val[0] || null;
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
                console.warn("[ChipSelect][loadOptions] Sin campo color, reintentando", colorErr);

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

            console.log("[ChipSelect][loadOptions] Opciones cargadas", records);
        } catch (err) {
            console.error("[ChipSelect][loadOptions] Error", err);
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

    toggleOptions(ev = null) {
        this._stopEvent(ev);

        this.uiState.expanded = !this.uiState.expanded;

        console.log("[ChipSelect][toggleOptions]", {
            expanded: this.uiState.expanded,
            readonly: this.props.readonly,
            currentId: this.currentId,
        });
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

    _markSaveError(message = "No guardado") {
        this.uiState.saving = false;
        this.uiState.saved = false;
        this.uiState.saveError = true;
        this.uiState.saveMessage = message;
    }

    async selectOption(option, ev = null) {
        this._stopEvent(ev);

        console.log("[ChipSelect][selectOption] INICIO", {
            option: option,
            fieldName: this.props.name,
            relation: this.relation,
            readonly: this.props.readonly,
            autoSave: this.props.autoSave,
            recordModel: this.recordModel,
            recordResId: this.recordResId,
            recordDataBefore: this.props.record && this.props.record.data,
        });

        if (!option || !option.id) {
            console.warn("[ChipSelect][selectOption] Opción inválida", option);
            return;
        }

        this._resetSaveStatus();

        this.uiState.localSelectedId = option.id;
        this.uiState.expanded = false;

        try {
            await this.props.record.update({
                [this.props.name]: [option.id, option.name],
            });

            console.log("[ChipSelect][selectOption] record.update OK", {
                selectedId: option.id,
                selectedName: option.name,
            });
        } catch (updateErr) {
            console.warn(
                "[ChipSelect][selectOption] record.update FALLÓ, pero selección local queda marcada",
                updateErr
            );
        }

        if (this.props.autoSave) {
            try {
                await this._autoSaveOption(option);
            } catch (saveErr) {
                console.error("[ChipSelect][selectOption] autosave FALLÓ", saveErr);

                this._markSaveError("No guardado");

                this.notification.add(
                    "No se pudo guardar automáticamente. Usa Guardar cambios antes de salir.",
                    {
                        type: "warning",
                    }
                );
            }
        }

        console.log("[ChipSelect][selectOption] FIN", {
            localSelectedId: this.uiState.localSelectedId,
            currentId: this.currentId,
            selectedOption: this.selectedOption,
        });
    }

    async _autoSaveOption(option) {
        const model = this.recordModel;
        const resId = this.recordResId;

        if (!model || !resId) {
            console.warn("[ChipSelect][_autoSaveOption] Sin modelo o ID real", {
                model: model,
                resId: resId,
                record: this.props.record,
            });

            this._markSaveError("Pendiente de guardar");

            this.notification.add("Cambio pendiente. Usa Guardar cambios antes de salir.", {
                type: "warning",
            });

            return;
        }

        this._markSaving();

        await this.orm.write(model, [resId], {
            [this.props.name]: option.id,
        });

        this._markSaved();

        console.log("[ChipSelect][_autoSaveOption] Guardado en BD", {
            model: model,
            resId: resId,
            fieldName: this.props.name,
            selectedId: option.id,
        });
    }
}

export const chipSelectField = {
    ...many2OneField,
    component: ChipSelectField,

    extractProps({ attrs, options }) {
        const props = many2OneField.extractProps(...arguments);

        const rawAutoSave =
            attrs?.auto_save ??
            attrs?.autoSave ??
            options?.auto_save ??
            options?.autoSave ??
            true;

        const rawFilterByField =
            attrs?.filter_by_field ??
            attrs?.filterByField ??
            options?.filter_by_field ??
            options?.filterByField;

        const rawFilterRelation =
            attrs?.filter_relation ??
            attrs?.filterRelation ??
            options?.filter_relation ??
            options?.filterRelation;

        const filterByField = normalizeStringProp(rawFilterByField);
        const filterRelation = normalizeStringProp(rawFilterRelation);

        const finalProps = {
            ...props,

            shortenLabels: toBool(
                attrs?.shorten_labels ??
                attrs?.shortenLabels ??
                options?.shorten_labels ??
                options?.shortenLabels,
                false
            ),

            autoSave: toBool(rawAutoSave, true),
        };

        /*
         * Importante:
         * No enviar filterByField ni filterRelation si están vacíos.
         * En Owl, optional=true permite omitir la prop,
         * pero si la mandas como null/false, falla porque espera String.
         */
        if (filterByField !== undefined) {
            finalProps.filterByField = filterByField;
        }

        if (filterRelation !== undefined) {
            finalProps.filterRelation = filterRelation;
        }

        console.log("[ChipSelect][extractProps FIX]", finalProps);

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