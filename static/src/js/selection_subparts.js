/** @odoo-module **/
import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

console.log("🚀 [SelectionSubparts] Módulo cargando…");

export class SelectionSubparts extends SelectionField {
    setup() {
        super.setup();
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this._opening = false; // anti-doble click
        console.log("✅ [SelectionSubparts] Servicios listos");
    }

    async onChange(ev) {
        // 1) Captura el valor primero (ev puede reciclarse)
        const selected = ev?.target?.value;
        const fallback = this.props.record?.data?.[this.props.name];
        const value = selected ?? fallback;

        // 2) Llama al padre (actualiza el valor en el record)
        await super.onChange(ev);

        // 3) Evalúa condiciones
        if (value !== "requiere_cambio" && value !== "cambio_de_repuestos") {
            return;
        }
        if (this._opening) {
            return; // evita dobles aperturas
        }
        this._opening = true;

        try {
            const resId = this.props.record?.resId || this.props.record?.data?.id || false;
            const model = "reparaciones.reparaciones";

            // Si el registro NO está guardado, evita llamar al RPC que requiere ID
            if (!resId) {
                this.notification.add(
                    _t("Guarda el registro antes de agregar subpartes."),
                    { type: "warning" }
                );
                // Alternativa: abrir el wizard con defaults y sin active_id
                // await this.action.doAction("sat.action_reparacion_add_subparts_wizard", {
                //     additionalContext: {
                //         active_model: model,
                //         default_reparacion_id: false,
                //         default_intervencion_id: false,
                //     },
                // });
                return;
            }

            // Llama RPC solo si hay ID
            const res = await this.orm.call(
                model,
                "rpc_prepare_subparts_wizard",
                [resId, this.props.name],
                {} // kwargs
            );

            if (res && res.intervencion_id) {
                const ctx = {
                    active_id: resId,
                    active_model: model,
                    active_intervencion_id: res.intervencion_id,
                    default_reparacion_id: resId,
                    default_intervencion_id: res.intervencion_id,
                };
                await this.action.doAction("sat.action_reparacion_add_subparts_wizard", {
                    additionalContext: ctx,
                });
            } else {
                this.notification.add(
                    _t("No se pudo preparar el asistente de subpartes."),
                    { type: "warning" }
                );
            }
        } catch (e) {
            console.error("❌ [SelectionSubparts] Error:", e);
            this.notification.add(
                _t("No se pudo abrir el asistente de subpartes."),
                { type: "danger" }
            );
        } finally {
            this._opening = false;
        }
    }
}

SelectionSubparts.props = { ...standardFieldProps };
registry.category("fields").add("selection_subparts", SelectionSubparts);
console.log("🎉 [SelectionSubparts] Widget registrado");
