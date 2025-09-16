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
        // 1) Valor escogido (antes de que OWL recicle el evento)
        const selected = ev?.target?.value;
        // 2) Deja que SelectionField actualice normalmente
        await super.onChange(ev);

        // 3) Solo disparamos wizard para estos valores
        if (selected !== "requiere_cambio" && selected !== "cambio_de_repuestos") {
            return;
        }
        if (this._opening) return;
        this._opening = true;

        try {
            const rec = this.props?.record;
            const resId = rec?.resId || rec?.data?.id;
            if (!resId) {
                this.notification.add(_t("Guarda el registro antes de agregar subpartes."), { type: "warning" });
                return;
            }

            // Modelo y campo que cambió (ej. black_id, transfer_id, etc.)
            const model = "reparaciones.reparaciones";
            const fieldName = this.props.name;

            // Pide al servidor preparar/crear la intervención
            const res = await this.orm.call(model, "rpc_prepare_subparts_wizard", [resId, fieldName], {});
            if (!res || !res.intervencion_id) {
                this.notification.add(_t("No se pudo preparar el asistente de subpartes."), { type: "warning" });
                return;
            }

            // Abre el wizard con la intervención como active_id
            await this.action.doAction("sat.action_reparacion_add_subparts_wizard", {
                additionalContext: {
                    active_model: "reparacion.intervencion",
                    active_id: res.intervencion_id,
                    default_reparacion_id: resId,
                    default_intervencion_id: res.intervencion_id,
                },
            });
        } catch (e) {
            console.error("[SelectionSubparts] error:", e);
            this.notification.add(_t("No se pudo abrir el asistente de subpartes."), { type: "danger" });
        } finally {
            this._opening = false;
        }
    }
}

SelectionSubparts.props = { ...standardFieldProps };
SelectionSubparts.supportedTypes = ["selection"]; // <- clave
// opcional (si tu build lo requiere):
// SelectionSubparts.template = SelectionField.template;

registry.category("fields").add("selection_subparts", SelectionSubparts);
