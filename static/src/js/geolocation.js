/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Record } from "@web/model/record";

patch(Record.prototype, {
    async _onClickAction(action) {
        if (action === "action_finalizar") {
            try {
                const position = await new Promise((resolve, reject) => {
                    if (!navigator.geolocation) {
                        reject(new Error("Geolocalización no disponible"));
                        return;
                    }

                    navigator.geolocation.getCurrentPosition(resolve, reject, {
                        enableHighAccuracy: true,
                        timeout: 5000,
                        maximumAge: 0
                    });
                });

                // Agregar las coordenadas al contexto
                this.context = {
                    ...this.context,
                    finish_latitude: position.coords.latitude,
                    finish_longitude: position.coords.longitude
                };
            } catch (error) {
                console.warn("No se pudo obtener la ubicación:", error);
            }
        }
        return super._onClickAction(...arguments);
    }
});