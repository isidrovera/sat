/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class PublicKioskApp extends Component {
    setup() {
        this.gpsService = {
            async getLocation() {
                return new Promise((resolve) => {
                    if (!navigator.geolocation) {
                        resolve({ latitude: false, longitude: false });
                        return;
                    }

                    navigator.geolocation.getCurrentPosition(
                        (position) => {
                            const { latitude, longitude, accuracy } = position.coords;
                            resolve({ latitude, longitude, accuracy });
                        },
                        (error) => {
                            console.warn("GPS error:", error.message);
                            resolve({ latitude: false, longitude: false });
                        },
                        {
                            enableHighAccuracy: true,
                            timeout: 10000,
                            maximumAge: 60000
                        }
                    );
                });
            }
        };
    }

    async handleAttendance() {
        const location = await this.gpsService.getLocation();
        
        // Lógica para manejar el attendance con GPS
        console.log("GPS Location:", location);
        
        // Aquí puedes agregar tu lógica específica del kiosco
    }
}

PublicKioskApp.template = "sat.PublicKioskApp";

registry.category("public_components").add("PublicKioskApp", PublicKioskApp);