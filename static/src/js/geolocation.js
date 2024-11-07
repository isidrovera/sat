/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Record } from "@web/model/record";
import { browser } from "@web/core/browser/browser";
import { useService } from "@web/core/utils/hooks";

patch(Record.prototype, {
    setup() {
        super.setup();
        this.notification = useService("notification");
    },

    async _onClickAction(action) {
        if (action === "action_finalizar") {
            if (!browser.navigator.geolocation) {
                console.warn("Geolocalización no soportada");
                return super._onClickAction(...arguments);
            }

            try {
                await new Promise((resolve, reject) => {
                    browser.navigator.geolocation.getCurrentPosition(
                        (position) => {
                            this.update({
                                finish_latitude: position.coords.latitude,
                                finish_longitude: position.coords.longitude,
                                finish_datetime: moment().format('YYYY-MM-DD HH:mm:ss')
                            });
                            resolve();
                        },
                        (error) => {
                            console.error("Error al obtener ubicación:", error);
                            reject(error);
                        },
                        {
                            enableHighAccuracy: true,
                            timeout: 5000,
                            maximumAge: 0
                        }
                    );
                });
            } catch (error) {
                console.warn("No se pudo obtener la ubicación:", error);
            }
        }
        return super._onClickAction(...arguments);
    }
});