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
    }

    async onChange(ev) {
        await super.onChange(ev);
        const value = this.props.record.data[this.props.name];
        if (value === "requiere_cambio" || value === "cambio_de_repuestos") {
            try {
                const res = await this.orm.call(
                    "reparaciones.reparaciones",
                    "rpc_prepare_subparts_wizard",
                    [this.props.record.data.id, this.props.name]
                );
                if (res && res.intervencion_id) {
                    await this.action.doAction("sat.action_reparacion_add_subparts_wizard", {
                        additionalContext: {
                            active_id: this.props.record.data.id,
                            active_model: "reparaciones.reparaciones",
                            active_intervencion_id: res.intervencion_id,
                            default_reparacion_id: this.props.record.data.id,
                            default_intervencion_id: res.intervencion_id,
                        },
                    });
                }
            } catch (e) {
                this.notification.add(_t("No se pudo abrir el asistente de subpartes."), { type: "danger" });
                // opcional: console.error(e);
            }
        }
    }
}
SelectionSubparts.props = { ...standardFieldProps };
registry.category("fields").add("selection_subparts", SelectionSubparts);