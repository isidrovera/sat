/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class SystrayAttendanceMenu extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
    }

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

    async onAttendanceClick() {
        const location = await this.getLocation();
        
        try {
            const result = await this.rpc("/hr_attendance/systray_check_in_out", {
                latitude: location.latitude,
                longitude: location.longitude,
                accuracy: location.accuracy
            });
            
            if (result.action) {
                // Manejar la respuesta según necesites
                this.notification.add("Attendance recorded with GPS", {
                    type: "success"
                });
            }
        } catch (error) {
            console.error("Attendance failed:", error);
            this.notification.add("Failed to record attendance", {
                type: "danger"
            });
        }
    }
}

SystrayAttendanceMenu.template = "sat.SystrayAttendanceMenu";

registry.category("systray").add("sat.SystrayAttendanceMenu", {
    Component: SystrayAttendanceMenu,
});