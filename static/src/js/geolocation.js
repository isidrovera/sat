/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const actionRegistry = registry.category("actions");

// Servicio de geolocalización
class LocationService {
    async getLocation() {
        if (!navigator.geolocation) {
            throw new Error("Geolocalización no soportada");
        }

        return new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(
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
}

// Registrar el servicio
registry.category("services").add("location", LocationService);

// Extender la acción de finalizar
async function extendFinalizarAction(action, options) {
    if (action.xml_id === "sat.action_finalizar") {
        const locationService = options.services.location;
        try {
            const location = await locationService.getLocation();
            action.context = {
                ...action.context,
                finish_latitude: location.latitude,
                finish_longitude: location.longitude,
                finish_datetime: moment().format('YYYY-MM-DD HH:mm:ss')
            };
        } catch (error) {
            console.warn("Error al obtener ubicación:", error);
        }
    }
    return action;
}

// Registrar el middleware
registry.category("action_middlewares").add("location_middleware", extendFinalizarAction);