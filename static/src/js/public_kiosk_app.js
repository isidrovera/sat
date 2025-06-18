/** @odoo-module **/

// Versión ultra simple que no depende de módulos específicos de Odoo
console.log("Loading GPS attendance enhancement...");

// Funciones GPS básicas
const GPS_ATTENDANCE = {
    async getLocation() {
        return new Promise((resolve) => {
            if (!navigator.geolocation) {
                resolve({ latitude: false, longitude: false });
                return;
            }

            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const { latitude, longitude, accuracy } = position.coords;
                    console.log(`GPS captured: ${latitude}, ${longitude}`);
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
    },

    async sendAttendance(url, data = {}) {
        const location = await this.getLocation();
        
        const payload = {
            ...data,
            latitude: location.latitude,
            longitude: location.longitude
        };
        
        if (location.accuracy) {
            payload.accuracy = location.accuracy;
        }

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(payload)
            });
            
            return await response.json();
        } catch (error) {
            console.error("Attendance request failed:", error);
            throw error;
        }
    }
};

// Hacer disponible globalmente
window.GPS_ATTENDANCE = GPS_ATTENDANCE;

// Función para interceptar clicks en botones de attendance
function setupAttendanceInterception() {
    // Interceptar todos los clicks en el documento
    document.addEventListener('click', async function(event) {
        const target = event.target;
        
        // Buscar si el click es en un elemento relacionado con attendance
        const isAttendanceButton = (
            target.classList.contains('o_systray_attendance') ||
            target.closest('.o_systray_attendance') ||
            target.getAttribute('data-action') === 'attendance' ||
            target.closest('[data-action="attendance"]') ||
            target.textContent.toLowerCase().includes('check in') ||
            target.textContent.toLowerCase().includes('check out')
        );
        
        if (isAttendanceButton) {
            console.log("Attendance button detected, enhancing with GPS");
            
            // Agregar un pequeño delay para permitir que se capture la ubicación
            const location = await GPS_ATTENDANCE.getLocation();
            
            if (location.latitude) {
                console.log("GPS location captured for attendance");
                
                // Agregar datos GPS al elemento para que puedan ser usados por Odoo
                target.setAttribute('data-gps-lat', location.latitude);
                target.setAttribute('data-gps-lon', location.longitude);
                if (location.accuracy) {
                    target.setAttribute('data-gps-accuracy', location.accuracy);
                }
            }
        }
    }, true); // true para capturar en fase de captura
}

// Función para monitorear formularios de attendance
function setupFormInterception() {
    // Interceptar envíos de formularios
    document.addEventListener('submit', async function(event) {
        const form = event.target;
        
        // Verificar si es un formulario de attendance
        if (form.action && form.action.includes('attendance')) {
            console.log("Attendance form submission detected");
            
            const location = await GPS_ATTENDANCE.getLocation();
            
            if (location.latitude) {
                // Agregar campos hidden con coordenadas GPS
                const latInput = document.createElement('input');
                latInput.type = 'hidden';
                latInput.name = 'latitude';
                latInput.value = location.latitude;
                form.appendChild(latInput);
                
                const lonInput = document.createElement('input');
                lonInput.type = 'hidden';
                lonInput.name = 'longitude';
                lonInput.value = location.longitude;
                form.appendChild(lonInput);
                
                if (location.accuracy) {
                    const accInput = document.createElement('input');
                    accInput.type = 'hidden';
                    accInput.name = 'accuracy';
                    accInput.value = location.accuracy;
                    form.appendChild(accInput);
                }
                
                console.log("GPS data added to attendance form");
            }
        }
    });
}

// Inicializar cuando el DOM esté listo
function initializeGPS() {
    console.log("Initializing GPS attendance enhancement");
    setupAttendanceInterception();
    setupFormInterception();
}

// Ejecutar cuando el DOM esté listo
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeGPS);
} else {
    initializeGPS();
}

// También ejecutar después de un delay para capturar contenido dinámico
setTimeout(initializeGPS, 2000);