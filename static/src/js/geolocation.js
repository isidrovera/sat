/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";

// Servicio de geolocalización
export const locationService = {
    dependencies: [],

    start() {
        return {
            async getLocation() {
                if (!browser.navigator.geolocation) {
                    throw new Error("Geolocalización no soportada");
                }

                return new Promise((resolve, reject) => {
                    browser.navigator.geolocation.getCurrentPosition(
                        (position) => {
                            resolve({
                                latitude: position.coords.latitude,
                                longitude: position.coords.longitude
                            });
                        },
                        (error) => {
                            let message = "Error desconocido";
                            switch(error.code) {
                                case error.PERMISSION_DENIED:
                                    message = "Permiso denegado para la ubicación";
                                    break;
                                case error.POSITION_UNAVAILABLE:
                                    message = "Ubicación no disponible";
                                    break;
                                case error.TIMEOUT:
                                    message = "Tiempo de espera agotado";
                                    break;
                            }
                            reject(new Error(message));
                        },
                        {
                            enableHighAccuracy: true,
                            timeout: 5000,
                            maximumAge: 0
                        }
                    );
                });
            }
        };
    },
};

// Registrar el servicio
registry.category("services").add("location", locationService);

// Middleware de acción para finalizar
export const finalizarLocationMiddleware = (action) => {
    const locationSrv = registry.category("services").get("location");
    
    if (action.tag === "ticket.alquiler" && action.params?.action === "finalizar") {
        return async (action) => {
            try {
                const location = await locationSrv.getLocation();
                return {
                    ...action,
                    context: {
                        ...action.context,
                        finish_latitude: location.latitude,
                        finish_longitude: location.longitude,
                        finish_datetime: moment().format('YYYY-MM-DD HH:mm:ss')
                    }
                };
            } catch (error) {
                console.warn("Error al obtener ubicación:", error);
                return action;
            }
        };
    }
    return action;
};

registry.category("action_middlewares").add("finalizarLocation", finalizarLocationMiddleware);