/** @odoo-module **/
import { registry } from "@web/core/registry";
import { SelectionField } from "@web/views/fields/selection/selection_field";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class SelectionSubparts extends SelectionField {
    setup() {
        super.setup();
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this._opening = false;
    }

    async onChange(ev) {
        const selected = ev?.target?.value;
        const fallback = this.props.record?.data?.[this.props.name];
        const value = selected ?? fallback;

        await super.onChange(ev);

        if (value !== "requiere_cambio" && value !== "cambio_de_repuestos") {
            return;
        }
        if (this._opening) return;
        this._opening = true;

        try {
            let resId = this.props.record?.resId;
            if (!resId) {
                // Tu caso normal: esto NO debería pasar porque la reparación ya existe.
                this.notification.add(
                    _t("Guarda el registro antes de agregar subpartes."),
                    { type: "warning" }
                );
                return;
            }

            const model = "reparaciones.reparaciones";
            const res = await this.orm.call(model, "rpc_prepare_subparts_wizard", [resId, this.props.name], {});
            if (res && res.intervencion_id) {
                await this.action.doAction("sat.action_reparacion_add_subparts_wizard", {
                    additionalContext: {
                        active_model: model,
                        active_id: resId,
                        active_intervencion_id: res.intervencion_id,
                        default_reparacion_id: resId,
                        default_intervencion_id: res.intervencion_id,
                    },
                });
            } else {
                this.notification.add(_t("No se pudo preparar el asistente de subpartes."), { type: "warning" });
            }
        } catch (e) {
            console.error("[SelectionSubparts] error:", e);
            this.notification.add(_t("No se pudo abrir el asistente de subpartes."), { type: "danger" });
        } finally {
            this._opening = false;
        }
    }
}
SelectionSubparts.props = { ...standardFieldProps };
registry.category("fields").add("selection_subparts", SelectionSubparts);
