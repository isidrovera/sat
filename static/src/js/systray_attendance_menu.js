/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ActivityMenu } from "@hr_attendance/components/systray_attendance/systray_attendance_menu";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { isIosApp } from "@web/core/browser/feature_detection";

patch(ActivityMenu.prototype, {
    setup() {
        super.setup();
        
        // Agregar estado para GPS
        Object.assign(this.state, {
            gpsLoading: false,
            gpsStatus: 'unknown' // unknown, granted, denied, unavailable
        });
        
        // Configuración GPS mejorada
        this.gpsOptions = {
            enableHighAccuracy: true,
            timeout: 10000, // 10 segundos
            maximumAge: 60000 // Cache por 1 minuto
        };
    },

    /**
     * Captura ubicación GPS con manejo mejorado de errores
     */
    async captureGpsLocation() {
        return new Promise((resolve) => {
            if (!navigator.geolocation) {
                console.warn("Geolocation not supported by this browser");
                this.state.gpsStatus = 'unavailable';
                resolve({ latitude: false, longitude: false });
                return;
            }

            // Mostrar indicador de carga
            this.state.gpsLoading = true;

            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const { latitude, longitude, accuracy } = position.coords;
                    console.log(`GPS captured: lat=${latitude}, lon=${longitude}, accuracy=${accuracy}m`);
                    
                    this.state.gpsLoading = false;
                    this.state.gpsStatus = 'granted';
                    
                    resolve({ 
                        latitude, 
                        longitude, 
                        accuracy,
                        timestamp: position.timestamp 
                    });
                },
                (error) => {
                    this.state.gpsLoading = false;
                    
                    // Manejo mejorado de errores GPS
                    let errorMessage = "";
                    switch(error.code) {
                        case error.PERMISSION_DENIED:
                            this.state.gpsStatus = 'denied';
                            errorMessage = _t("GPS permission denied. Please enable location access in your browser.");
                            break;
                        case error.POSITION_UNAVAILABLE:
                            this.state.gpsStatus = 'unavailable';
                            errorMessage = _t("GPS position unavailable. Check your device's location settings.");
                            break;
                        case error.TIMEOUT:
                            this.state.gpsStatus = 'timeout';
                            errorMessage = _t("GPS timeout. Continuing with IP-based location.");
                            break;
                        default:
                            this.state.gpsStatus = 'error';
                            errorMessage = _t("GPS error occurred.");
                            break;
                    }
                    
                    console.warn(`GPS Error: ${errorMessage}`, error);
                    
                    // Mostrar notificación solo para errores críticos
                    if (error.code === error.PERMISSION_DENIED) {
                        this.notification.add(errorMessage, { 
                            type: "warning",
                            title: _t("Location Access Required")
                        });
                    }
                    
                    // Continuar sin GPS
                    resolve({ latitude: false, longitude: false });
                },
                this.gpsOptions
            );
        });
    },

    /**
     * OVERRIDE: Método principal mejorado para manejar GPS
     */
    async signInOut() {
        this.dropdown.close();
        
        try {
            // Capturar ubicación GPS (funciona en la mayoría de navegadores/dispositivos)
            const gpsLocation = await this.captureGpsLocation();
            
            // Preparar datos para enviar
            const attendanceData = {
                latitude: gpsLocation.latitude,
                longitude: gpsLocation.longitude
            };
            
            // Agregar accuracy si está disponible
            if (gpsLocation.accuracy) {
                attendanceData.accuracy = gpsLocation.accuracy;
            }
            
            // Llamar al endpoint con coordenadas GPS
            const result = await rpc("/hr_attendance/systray_check_in_out", attendanceData);
            
            // Manejar errores del servidor
            if (result.error) {
                this.notification.add(result.error, { 
                    type: "danger",
                    title: _t("Attendance Error") 
                });
                return;
            }
            
            // Actualizar datos del empleado
            await this.searchReadEmployee();
            
            // Mostrar notificación de éxito mejorada
            const action = this.state.checkedIn ? _t("Check out") : _t("Check in");
            const locationInfo = gpsLocation.latitude ? 
                _t("with GPS location (±%(accuracy)sm)", { accuracy: Math.round(gpsLocation.accuracy || 0) }) : 
                _t("with IP-based location");
                
            this.notification.add(
                _t("%(action)s successful %(location)s", {
                    action: action,
                    location: locationInfo
                }), 
                { 
                    type: "success",
                    title: _t("Attendance Recorded") 
                }
            );
            
        } catch (error) {
            console.error("Attendance error:", error);
            this.notification.add(
                error.data?.message || _t("Error processing attendance"), 
                { 
                    type: "danger",
                    title: _t("Attendance Error") 
                }
            );
        }
    }
});