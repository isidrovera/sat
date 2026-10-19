
/** @odoo-module **/

import { registry } from "@web/core/registry";
import {
    Many2OneField,
    buildM2OFieldDescription,
    extractM2OFieldProps,
    m2oSupportedOptions,
} from "@web/views/fields/many2one/many2one_field";

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

function toBool(value, fallback = false) {
    if (value === undefined || value === null || value === "") {
        return fallback;
    }

    if ([true, 1, "1", "true", "True"].includes(value)) {
        return true;
    }

    if ([false, 0, "0", "false", "False"].includes(value)) {
        return false;
    }

    return Boolean(value);
}

function normalizeStringProp(value) {
    if (
        value === undefined ||
        value === null ||
        value === "" ||
        value === false
    ) {
        return undefined;
    }

    return String(value);
}

function getRelationId(value) {
    if (!value) {
        return null;
    }

    if (Array.isArray(value)) {
        return getRelationId(value[0]);
    }

    if (typeof value === "object") {
        return getRelationId(value.id || value.resId);
    }

    const number = Number(value);

    return Number.isInteger(number) && number > 0
        ? number
        : null;
}

export class ChipSelectField extends Many2OneField {
    static template = "sat.ChipSelectField";

    static props = {
        ...Many2OneField.props,

        filterByField: {
            type: String,
            optional: true,
        },

        filterRelation: {
            type: String,
            optional: true,
        },

        shortenLabels: {
            type: Boolean,
            optional: true,
        },

        autoSave: {
            type: Boolean,
            optional: true,
        },

        kanbanWrite: {
            type: Boolean,
            optional: true,
        },
    };

    setup() {
        super.setup();

        this.orm = useService("orm");
        this.notification = useService("notification");

        this.uiState = useState({
            options: [],
            loading: true,
            expanded: false,
            saving: false,
            saved: false,
            saveError: false,
            saveMessage: "",
            localSelectedId: null,
        });

        this.onToggleOptions = (ev) => this.toggleOptions(ev);
        this.onSelectOption = (option, ev) =>
            this.selectOption(option, ev);

        this._lastTypeId = this.filterTypeId;
        this._lastRecordId = this.recordResId;
        this._optionsRequest = 0;

        this.loadOptions();

        onWillUpdateProps((nextProps) => {
            const typeId = this._extractTypeId(nextProps);
            const nextRecordId = this._extractRecordId(
                nextProps.record
            );

            if (nextRecordId !== this._lastRecordId) {
                this._lastRecordId = nextRecordId;
                this.uiState.localSelectedId = null;
                this.uiState.expanded = false;
            }

            if (typeId !== this._lastTypeId) {
                this._lastTypeId = typeId;
                this.uiState.expanded = false;
                this.uiState.localSelectedId = null;
                this.loadOptions(nextProps);
            }
        });
    }

    get relation() {
        return this.props.record.fields[this.props.name].relation;
    }

    get recordModel() {
        const record = this.props.record;

        return (
            record.resModel ||
            record.modelName ||
            record.config?.resModel ||
            record.model?.config?.resModel ||
            null
        );
    }

    _extractRecordId(record) {
        return getRelationId(
            record?.resId ||
            record?.res_id ||
            record?.data?.id
        );
    }

    get recordResId() {
        return this._extractRecordId(this.props.record);
    }

    get currentId() {
        if (this.uiState.localSelectedId !== null) {
            return this.uiState.localSelectedId;
        }

        return getRelationId(
            this.props.record.data[this.props.name]
        );
    }

    get selectedOption() {
        return (
            this.uiState.options.find(
                (option) => option.id === this.currentId
            ) || null
        );
    }

    get filterTypeId() {
        return this._extractTypeId(this.props);
    }

    _extractTypeId(props) {
        const field = props.filterByField;

        if (!field || !props.record?.data) {
            return null;
        }

        return getRelationId(
            props.record.data[field]
        );
    }

    get canSelect() {
        if (this.uiState.saving) {
            return false;
        }

        if (!this.props.readonly) {
            return true;
        }

        // Solo las vistas que lo autoricen explícitamente.
        return Boolean(
            this.props.kanbanWrite &&
            this.props.autoSave &&
            this.recordModel &&
            this.recordResId
        );
    }

    async loadOptions(props = this.props) {
        const requestId = ++this._optionsRequest;

        this.uiState.loading = true;

        try {
            const relation =
                props.record.fields[props.name].relation;

            const domain = this.buildDomain(props);

            let records;

            try {
                records = await this.orm.searchRead(
                    relation,
                    domain,
                    ["id", "name", "color"],
                    { limit: 100 }
                );
            } catch (error) {
                records = await this.orm.searchRead(
                    relation,
                    domain,
                    ["id", "name"],
                    { limit: 100 }
                );

                records = records.map((record) => ({
                    ...record,
                    color: 0,
                }));
            }

            if (requestId !== this._optionsRequest) {
                return;
            }

            this.uiState.options = records;

            console.log("[ChipSelect] Opciones cargadas", {
                relation,
                total: records.length,
            });
        } catch (error) {
            if (requestId !== this._optionsRequest) {
                return;
            }

            console.error(
                "[ChipSelect] Error cargando opciones",
                error
            );

            this.uiState.options = [];

            this.notification.add(
                "No se pudieron cargar los estados.",
                { type: "danger" }
            );
        } finally {
            if (requestId === this._optionsRequest) {
                this.uiState.loading = false;
            }
        }
    }

    buildDomain(props = this.props) {
        const typeId = this._extractTypeId(props);
        const relation = props.filterRelation;

        if (!typeId || !relation) {
            return [];
        }

        return [
            "|",
            [relation, "=", false],
            [relation, "in", [typeId]],
        ];
    }

    getChipStyle(option, selected = false) {
        const palette =
            ODOO_COLOR_MAP[option?.color || 0] ||
            ODOO_COLOR_MAP[0];

        if (selected) {
            return (
                `background-color: ${palette.bg};` +
                `border-color: ${palette.border};` +
                `color: ${palette.text};`
            );
        }

        return (
            "background-color: white;" +
            `border-color: ${palette.border};` +
            `color: ${palette.bg};`
        );
    }

    getShortLabel(option) {
        if (!option?.name) {
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
        return Boolean(
            option && option.id === this.currentId
        );
    }

    _stopEvent(ev) {
        if (!ev) {
            return;
        }

        ev.preventDefault();
        ev.stopPropagation();

        if (ev.stopImmediatePropagation) {
            ev.stopImmediatePropagation();
        }
    }

    toggleOptions(ev) {
        this._stopEvent(ev);

        if (!this.canSelect) {
            return;
        }

        this.uiState.expanded = !this.uiState.expanded;
    }

    _resetStatus() {
        this.uiState.saving = false;
        this.uiState.saved = false;
        this.uiState.saveError = false;
        this.uiState.saveMessage = "";
    }

    async selectOption(option, ev) {
        this._stopEvent(ev);

        if (!option?.id || this.uiState.saving) {
            return;
        }

        if (!this.canSelect) {
            this.notification.add(
                "Este estado no está habilitado para edición.",
                { type: "warning" }
            );
            return;
        }

        const oldId = this.currentId;

        if (oldId === option.id) {
            this.uiState.expanded = false;
            return;
        }

        this._resetStatus();
        this.uiState.saving = true;
        this.uiState.saveMessage = "Guardando...";

        try {
            if (this.props.readonly) {
                // Escritura directa: únicamente para Kanban
                // habilitado explícitamente en la vista.
                await this._writeKanbanOption(option);
            } else {
                // Formulario editable: actualizar el modelo
                // de Odoo mediante el mecanismo normal.
                await this.props.record.update({
                    [this.props.name]: [
                        option.id,
                        option.name,
                    ],
                });

                if (this.props.autoSave) {
                    const model = this.recordModel;
                    const resId = this.recordResId;

                    if (model && resId) {
                        await this.orm.write(
                            model,
                            [resId],
                            {
                                [this.props.name]: option.id,
                            }
                        );
                    }
                }
            }

            this.uiState.localSelectedId = option.id;
            this.uiState.expanded = false;
            this.uiState.saved = true;
            this.uiState.saveMessage = "Guardado";

            console.log("[ChipSelect] Estado actualizado", {
                model: this.recordModel,
                id: this.recordResId,
                field: this.props.name,
                estado: option.id,
            });

            this.notification.add(
                `Estado actualizado: ${option.name}`,
                { type: "success" }
            );
        } catch (error) {
            this.uiState.localSelectedId = oldId;
            this.uiState.saveError = true;
            this.uiState.saveMessage = "No guardado";

            console.error(
                "[ChipSelect] Error guardando estado",
                error
            );

            this.notification.add(
                "No se pudo guardar el estado. " +
                "Verifica los permisos o las reglas de reparación.",
                { type: "danger" }
            );
        } finally {
            this.uiState.saving = false;
        }
    }

    async _writeKanbanOption(option) {
        const model = this.recordModel;
        const resId = this.recordResId;

        if (
            !this.props.kanbanWrite ||
            !this.props.autoSave ||
            !model ||
            !resId
        ) {
            throw new Error(
                "No se permite guardar esta tarjeta Kanban."
            );
        }

        // orm.write utiliza los permisos y las reglas
        // del servidor Odoo. No se utiliza sudo.
        await this.orm.write(
            model,
            [resId],
            {
                [this.props.name]: option.id,
            }
        );
    }
}

export const chipSelectField = {
    ...buildM2OFieldDescription(ChipSelectField),

    component: ChipSelectField,

    extractProps({ attrs, options }) {
        const props = extractM2OFieldProps(
            ...arguments
        );

        const filterByField = normalizeStringProp(
            attrs?.filter_by_field ??
            attrs?.filterByField ??
            options?.filter_by_field ??
            options?.filterByField
        );

        const filterRelation = normalizeStringProp(
            attrs?.filter_relation ??
            attrs?.filterRelation ??
            options?.filter_relation ??
            options?.filterRelation
        );

        const finalProps = {
            ...props,

            shortenLabels: toBool(
                attrs?.shorten_labels ??
                attrs?.shortenLabels ??
                options?.shorten_labels ??
                options?.shortenLabels,
                false
            ),

            autoSave: toBool(
                attrs?.auto_save ??
                attrs?.autoSave ??
                options?.auto_save ??
                options?.autoSave,
                true
            ),

            kanbanWrite: toBool(
                attrs?.kanban_write ??
                attrs?.kanbanWrite ??
                options?.kanban_write ??
                options?.kanbanWrite,
                false
            ),
        };

        if (filterByField !== undefined) {
            finalProps.filterByField = filterByField;
        }

        if (filterRelation !== undefined) {
            finalProps.filterRelation = filterRelation;
        }

        return finalProps;
    },

    supportedOptions: [
        ...(m2oSupportedOptions || []),
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
        {
            label: "Auto save",
            name: "auto_save",
            type: "boolean",
        },
        {
            label: "Kanban write",
            name: "kanban_write",
            type: "boolean",
        },
    ],
};

registry.category("fields").add(
    "chip_select",
    chipSelectField
);
