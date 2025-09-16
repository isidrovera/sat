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

    async _ensureRecordSaved() {
        // Intenta obtener un ID; si no hay, intenta guardar el formulario
        let resId = this.props.record?.resId || this.props.record?.data?.id || false;
        if (resId) return resId;

        // Algunos contextos exponen save() en el record; probamos de forma segura
        try {
            if (this.props.record?.save) {
                console.log("📝 [SelectionSubparts] Guardando record vía record.save()…");
                await this.props.record.save({ stayInEdit: true });
                resId = this.props.record?.resId || this.props.record?.data?.id || false;
                if (resId) return resId;
            } else if (this.props.record?.model?.root?.save) {
                console.log("📝 [SelectionSubparts] Guardando record vía model.root.save()…");
                await this.props.record.model.root.save({ stayInEdit: true });
                resId = this.props.record?.resId || this.props.record?.data?.id || false;
                if (resId) return resId;
            }
        } catch (e) {
            console.warn("⚠️ [SelectionSubparts] No se pudo hacer auto-save:", e);
        }
        return false;
    }

    async onChange(ev) {
        // 1) Captura el valor antes de llamar al padre
        const selected = ev?.target?.value;
        const fallback = this.props.record?.data?.[this.props.name];
        const value = selected ?? fallback;

        // 2) Actualiza el valor en el record
        await super.onChange(ev);

        // 3) Disparadores
        if (value !== "requiere_cambio" && value !== "cambio_de_repuestos") {
            return;
        }
        if (this._opening) return;
        this._opening = true;

        try {
            const model = "reparaciones.reparaciones";
            let resId = this.props.record?.resId || this.props.record?.data?.id || false;

            // Si no hay ID, intenta guardar automáticamente
            if (!resId) {
                resId = await this._ensureRecordSaved();
            }

            if (resId) {
                // Con ID: prepara intervención en el server y abre wizard
                const res = await this.orm.call(
                    model,
                    "rpc_prepare_subparts_wizard",
                    [resId, this.props.name],
                    {}
                );

                if (res?.intervencion_id) {
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
                    return;
                }
                this.notification.add(_t("No se pudo preparar el asistente de subpartes."), { type: "warning" });
                return;
            }

            // Sin ID y no se pudo guardar: abre wizard “en blanco” (último recurso).
            // El wizard se abrirá, el técnico selecciona subpartes, y al guardar el form principal podrás
            // empatar esa info (si decides implementar un buffer). Si no usarás buffer, mejor forzar guardado.
            await this.action.doAction("sat.action_reparacion_add_subparts_wizard", {
                additionalContext: {
                    active_model: model,
                    active_id: false,
                    active_intervencion_id: false,
                    default_reparacion_id: false,
                    default_intervencion_id: false,
                },
            });
            this.notification.add(_t("El registro aún no existe; se abrió el asistente sin vínculo."), { type: "warning" });
        } catch (e) {
            console.error("❌ [SelectionSubparts] Error:", e);
            this.notification.add(_t("No se pudo abrir el asistente de subpartes."), { type: "danger" });
        } finally {
            this._opening = false;
        }
    }
}

SelectionSubparts.props = { ...standardFieldProps };
registry.category("fields").add("selection_subparts", SelectionSubparts);
console.log("🎉 [SelectionSubparts] Widget registrado");
