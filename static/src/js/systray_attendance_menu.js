/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";

// Servicio GPS global para attendance
const attendanceGpsService = {
    dependencies: [],
    start(env) {
        const service = {
            gpsOptions: {
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 60000
            },

            async captureLocation() {
                return new Promise((resolve) => {
                    if (!navigator.geolocation) {
                        console.warn("Geolocation not supported");
                        resolve({ latitude: false, longitude: false });
                        return;
                    }

                    navigator.geolocation.getCurrentPosition(
                        (position) => {
                            const { latitude, longitude, accuracy } = position.coords;
                            console.log(`GPS: ${latitude}, ${longitude}, ±${accuracy}m`);
                            resolve({ 
                                latitude, 
                                longitude, 
                                accuracy, 
                                timestamp: position.timestamp 
                            });
                        },
                        (error) => {
                            console.warn("GPS error:", error.message);
                            resolve({ latitude: false, longitude: false });
                        },
                        this.gpsOptions
                    );
                });
            },

            async makeAttendanceCall(endpoint, data = {}) {
                const location = await this.captureLocation();
                const payload = {
                    ...data,
                    latitude: location.latitude,
                    longitude: location.longitude
                };
                
                if (location.accuracy) {
                    payload.accuracy = location.accuracy;
                }
                
                return await rpc(endpoint, payload);
            }
        };

        // Hacer el servicio disponible globalmente
        window.attendanceGPS = service;
        
        return service;
    }
};

// Registrar el servicio
registry.category("services").add("attendance_gps", attendanceGpsService);

// Función para interceptar llamadas de attendance existentes
function interceptAttendanceCalls() {
    // Interceptar RPC calls relacionados con attendance
    const originalRpc = window.rpc || rpc;
    
    // Override global para capturar attendance calls
    const interceptedEndpoints = [
        "/hr_attendance/systray_check_in_out",
        "attendance_barcode_scanned", 
        "manual_selection"
    ];
    
    function enhancedRpc(route, params = {}) {
        // Si es una llamada de attendance, agregar GPS
        if (interceptedEndpoints.some(endpoint => route.includes(endpoint) || route === endpoint)) {
            console.log("Intercepting attendance call:", route);
            
            if (window.attendanceGPS) {
                return window.attendanceGPS.makeAttendanceCall(route, params);
            }
        }
        
        // Para otras llamadas, usar RPC normal
        return originalRpc(route, params);
    }
    
    // Reemplazar rpc global si existe
    if (window.rpc) {
        window.rpc = enhancedRpc;
    }
}

// Función para monitorear y mejorar botones de attendance
function enhanceAttendanceUI() {
    // Buscar botones de attendance en el DOM
    const selectors = [
        '.o_systray_attendance',
        '[data-menu-xmlid="hr_attendance.menu_hr_attendance"]',
        '.attendance_button',
        '.o_attendance_sign_in_out_icon'
    ];
    
    selectors.forEach(selector => {
        const elements = document.querySelectorAll(selector);
        elements.forEach(element => {
            if (!element.hasAttribute('data-gps-enhanced')) {
                element.setAttribute('data-gps-enhanced', 'true');
                
                // Agregar evento click mejorado
                element.addEventListener('click', async function(event) {
                    if (window.attendanceGPS) {
                        console.log("GPS-enhanced attendance click detected");
                        
                        // Si el elemento tiene un handler original, lo preservamos
                        const originalHandler = element.onclick;
                        
                        // Interceptar solo si no hay un handler personalizado ya
                        if (!originalHandler) {
                            event.preventDefault();
                            
                            try {
                                const result = await window.attendanceGPS.makeAttendanceCall("/hr_attendance/systray_check_in_out");
                                console.log("Attendance recorded with GPS:", result);
                                
                                // Recargar la página o actualizar UI si es necesario
                                if (result && !result.error) {
                                    // Podrías agregar aquí lógica para actualizar la UI
                                    window.location.reload();
                                }
                            } catch (error) {
                                console.error("GPS attendance failed:", error);
                            }
                        }
                    }
                });
            }
        });
    });
}

// Función para aplicar mejoras de forma segura después de que todo se cargue
function initializeGpsEnhancements() {
    try {
        interceptAttendanceCalls();
        enhanceAttendanceUI();
        
        // Reexecutar periódicamente para capturar elementos dinámicos
        setInterval(enhanceAttendanceUI, 3000);
        
        console.log("GPS attendance enhancements initialized");
    } catch (error) {
        console.warn("Could not initialize GPS enhancements:", error);
    }
}

// Inicializar cuando el DOM esté listo
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(initializeGpsEnhancements, 1000);
    });
} else {
    setTimeout(initializeGpsEnhancements, 1000);
}

// También intentar cuando Odoo esté completamente cargado
if (typeof odoo !== 'undefined') {
    odoo.define('sat.attendance_gps_init', function(require) {
        setTimeout(initializeGpsEnhancements, 2000);
    });
}