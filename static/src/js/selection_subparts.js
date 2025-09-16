/** @odoo-module **/

import { Component, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";

const TAG = "[selection_subparts]";

export class SelectionSubparts extends Component {
    setup() {
        // Log de ciclo de vida del componente
        onMounted(() => {
            const el = this.el?.querySelector("select");
            console.debug(TAG, "mounted", {
                hasEl: !!this.el,
                hasSelect: !!el,
                props: this.props,
            });

            // Log de estilos problemáticos (overlay / pointer-events)
            if (el) {
                const cs = getComputedStyle(el);
                console.debug(TAG, "computed styles", {
                    pointerEvents: cs.pointerEvents,
                    zIndex: cs.zIndex,
                    opacity: cs.opacity,
                    disabledAttr: el.hasAttribute("disabled"),
                });

                // Bordecito visual temporal para ver si hay overlay encima
                el.style.outline = "1px dashed #7c3aed"; // quitar luego
            }

            // Listeners para ver si recibe los eventos de click/focus
            this._dbgClick = (ev) => console.debug(TAG, "click", { target: ev.target, disabled: ev.target.disabled });
            this._dbgFocus = (ev) => console.debug(TAG, "focus", { target: ev.target, disabled: ev.target.disabled });
            this._dbgKey = (ev) => console.debug(TAG, "keydown", ev.key);

            el?.addEventListener("click", this._dbgClick);
            el?.addEventListener("focus", this._dbgFocus);
            el?.addEventListener("keydown", this._dbgKey);
        });

        onWillUnmount(() => {
            const el = this.el?.querySelector("select");
            if (el) {
                el.removeEventListener("click", this._dbgClick);
                el.removeEventListener("focus", this._dbgFocus);
                el.removeEventListener("keydown", this._dbgKey);
            }
        });
    }
}
SelectionSubparts.template = "sat.SelectionSubparts";
SelectionSubparts.props = {
    value: { type: [String, Number, Boolean], optional: true },
    selectionList: { type: Array },
    readonly: { type: Boolean, optional: true },
    onChange: { type: Function, optional: true },
    // props “extra” que Field puede inyectar
    id: { type: [String, Number], optional: true },
    name: { type: String, optional: true },
    record: { type: Object, optional: true },
};

const fieldRegistry = registry.category("fields");
fieldRegistry.add("selection_subparts", {
    component: SelectionSubparts,
    supportedTypes: ["selection"],

    extractProps: ({ field, record, value, attrs }) => {
        const currentValue = value !== undefined ? value : record?.data?.[field.name];

        // Fuente de opciones (varias rutas)
        const selection =
            field.selection ||
            field.params?.selection ||
            attrs?.selection ||
            [];

        const readonly = Boolean(attrs?.readonly) || Boolean(record?.isReadonly);

        const onChange = (ev) => {
            const newRaw = ev.target.value;
            console.debug(TAG, "onChange fired", { newRaw, hasRecord: !!record });
            if (!record) return;
            // tus opciones son strings → actualizar directo
            record.update({ [field.name]: newRaw });
        };

        // LOG CENTRAL: TODO lo que necesitamos ver
        console.debug(TAG, "extractProps", {
            model: record?.model?.name,
            fieldName: field?.name,
            readonly,
            hasRecord: !!record,
            hasData: !!record?.data,
            value: currentValue,
            selectionLen: selection.length,
            selectionPreview: selection.slice(0, 4), // muestra primeras 4
            attrs,
        });

        // Loga si la selección está vacía (motivo típico de “no se abre”)
        if (!selection.length) {
            console.warn(TAG, "EMPTY selectionList — el <select> no tendrá opciones");
        }

        return { value: currentValue, selectionList: selection, readonly, onChange };
    },

    isEmpty: ({ value }) => value === undefined || value === null || value === "",
});
