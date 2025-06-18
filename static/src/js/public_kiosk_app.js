/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { isIosApp } from "@web/core/browser/feature_detection";

// Verificar si el módulo del kiosk existe antes de hacer patch
let kioskAttendanceApp;
try {
    const module = await import("@hr_attendance/public_kiosk/public_kiosk_app");
    kioskAttendanceApp = module.kioskAttendanceApp;
} catch (error) {
    console.warn("kioskAttendanceApp module not found, skipping patch:", error);
}

// Solo aplicar patch si el módulo existe
if (kioskAttendanceApp && kioskAttendanceApp.prototype) {
    patch(kioskAttendanceApp.prototype, {
        setup() {
            super.setup();
            
            // Agregar configuraciones GPS al estado
            Object.assign(this.state, {
                gpsStatus: "unknown", // unknown, granted, denied, unavailable
                gpsLoading: false,
                gpsLastLocation: null
            });
            
            // Configuración GPS mejorada desde props del kiosk
            this.gpsOptions = {
                enableHighAccuracy: true,
                timeout: this.props.gpsTimeout || 10000,
                maximumAge: 30000 // Cache por 30 segundos en kiosk
            };
        },

        /**
         * Obtiene mensaje de error GPS localizado
         */
        getGpsErrorMessage(error) {
            switch(error.code) {
                case error.PERMISSION_DENIED:
                    return _t("GPS permission denied. Please allow location access to continue.");
                case error.POSITION_UNAVAILABLE:
                    return _t("GPS position unavailable. Please check your device settings.");
                case error.TIMEOUT:
                    return _t("GPS timeout. Please try again.");
                default:
                    return _t("GPS error occurred. Please try again.");
            }
        },

        /**
         * OVERRIDE: Método mejorado para capturar GPS con geolocalización
         */
        async makeRpcWithGeolocation(route, params) {
            // Si no hay GPS disponible o es iOS App, usar implementación original
            if (!navigator.geolocation || isIosApp()) {
                return rpc(route, { ...params });
            }

            return new Promise((resolve) => {
                this.state.gpsLoading = true;
                
                navigator.geolocation.getCurrentPosition(
                    async ({ coords: { latitude, longitude, accuracy }, timestamp }) => {
                        this.state.gpsLoading = false;
                        this.state.gpsLastLocation = { latitude, longitude, accuracy, timestamp };
                        
                        console.log(`Kiosk GPS captured: lat=${latitude}, lon=${longitude}, accuracy=${accuracy}m`);
                        
                        try {
                            const result = await rpc(route, {
                                ...params,
                                latitude,
                                longitude,
                                accuracy
                            });
                            resolve(result);
                        } catch (error) {
                            console.error("RPC error with GPS:", error);
                            resolve({ error: error.message });
                        }
                    },
                    async (error) => {
                        this.state.gpsLoading = false;
                        
                        console.warn("GPS error in kiosk:", error);
                        
                        // Si GPS es requerido, mostrar error
                        if (this.props.gpsRequired) {
                            const errorMsg = this.getGpsErrorMessage(error);
                            resolve({ error: errorMsg });
                            return;
                        }
                        
                        // Si GPS no es requerido, continuar sin GPS
                        try {
                            const result = await rpc(route, { ...params });
                            resolve(result);
                        } catch (rpcError) {
                            resolve({ error: rpcError.message });
                        }
                    },
                    this.gpsOptions
                );
            });
        },

        /**
         * OVERRIDE: Método mejorado para escaneo de códigos con GPS
         */
        async onBarcodeScanned(barcode) {
            if (this.lockScanner || this.state.active_display !== 'main') {
                return;
            }
            
            this.lockScanner = true;
            this.ui.block();

            try {
                // Usar método mejorado que captura GPS
                const result = await this.makeRpcWithGeolocation("attendance_barcode_scanned", {
                    barcode: barcode,
                    token: this.props.token,
                });

                if (result.error) {
                    this.displayNotification(result.error);
                } else if (result && result.employee_name) {
                    this.employeeData = result;
                    this.switchDisplay("greet");
                } else {
                    this.displayNotification(
                        _t("No employee corresponding to Badge ID '%(barcode)s.'", { barcode })
                    );
                }
            } catch (error) {
                console.error("Barcode scan error:", error);
                this.displayNotification(error.data?.message || _t("Error processing barcode"));
            } finally {
                this.lockScanner = false;
                this.ui.unblock();
            }
        },

        /**
         * OVERRIDE: Método mejorado para selección manual con mejor manejo de errores
         */
        async onManualSelection(employeeId, enteredPin) {
            try {
                const result = await this.makeRpcWithGeolocation('manual_selection', {
                    'token': this.props.token,
                    'employee_id': employeeId,
                    'pin_code': enteredPin
                });
                
                if (result.error) {
                    this.displayNotification(result.error);
                } else if (result && result.attendance) {
                    this.employeeData = result;
                    this.switchDisplay('greet');
                } else {
                    if (enteredPin) {
                        this.displayNotification(_t("Wrong PIN"));
                    } else {
                        this.displayNotification(_t("Error processing attendance"));
                    }
                }
            } catch (error) {
                console.error("Manual selection error:", error);
                this.displayNotification(error.data?.message || _t("Error processing attendance"));
            }
        }
    });
}