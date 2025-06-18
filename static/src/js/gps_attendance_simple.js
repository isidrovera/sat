// GPS Attendance Enhancement for Odoo 18
// Version: 1.0 - Compatible con todos los navegadores y sin dependencias complejas

(function() {
    'use strict';
    
    console.log("🚀 Loading GPS Attendance Enhancement v1.0");

    // ============== CONFIGURACIÓN GPS ==============
    const GPS_CONFIG = {
        enableHighAccuracy: true,
        timeout: 15000,          // 15 segundos
        maximumAge: 60000       // 1 minuto
    };

    // ============== SERVICIO GPS PRINCIPAL ==============
    const GPSAttendanceService = {
        
        /**
         * Captura la ubicación GPS del dispositivo
         * @returns {Promise} Promesa con las coordenadas
         */
        async captureLocation() {
            return new Promise((resolve) => {
                if (!navigator.geolocation) {
                    console.warn("⚠️ Geolocation no está disponible en este navegador");
                    resolve({ 
                        latitude: false, 
                        longitude: false, 
                        error: "Geolocation not supported" 
                    });
                    return;
                }

                // Mostrar indicador de carga si existe
                this.showLoadingIndicator();

                navigator.geolocation.getCurrentPosition(
                    (position) => {
                        const { latitude, longitude, accuracy } = position.coords;
                        const result = {
                            latitude: latitude,
                            longitude: longitude,
                            accuracy: Math.round(accuracy),
                            timestamp: Date.now(),
                            success: true
                        };
                        
                        console.log(`📍 GPS capturado: ${latitude.toFixed(6)}, ${longitude.toFixed(6)} (±${Math.round(accuracy)}m)`);
                        this.hideLoadingIndicator();
                        resolve(result);
                    },
                    (error) => {
                        console.warn("❌ Error GPS:", error.message);
                        this.hideLoadingIndicator();
                        resolve({ 
                            latitude: false, 
                            longitude: false, 
                            error: error.message,
                            success: false
                        });
                    },
                    GPS_CONFIG
                );
            });
        },

        /**
         * Muestra indicador de carga
         */
        showLoadingIndicator() {
            // Crear indicador temporal si no existe
            if (!document.getElementById('gps-loading')) {
                const indicator = document.createElement('div');
                indicator.id = 'gps-loading';
                indicator.innerHTML = '📍 Obteniendo ubicación...';
                indicator.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    background: #007bff;
                    color: white;
                    padding: 10px 15px;
                    border-radius: 5px;
                    z-index: 9999;
                    font-size: 14px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                `;
                document.body.appendChild(indicator);
            }
        },

        /**
         * Oculta indicador de carga
         */
        hideLoadingIndicator() {
            const indicator = document.getElementById('gps-loading');
            if (indicator) {
                indicator.remove();
            }
        },

        /**
         * Envía datos de attendance con GPS
         * @param {string} url - URL del endpoint
         * @param {object} additionalData - Datos adicionales
         */
        async sendAttendanceWithGPS(url = '/hr_attendance/systray_check_in_out', additionalData = {}) {
            try {
                console.log("🕐 Iniciando registro de attendance con GPS...");
                
                // Capturar ubicación
                const location = await this.captureLocation();
                
                // Preparar payload
                const payload = {
                    ...additionalData,
                    latitude: location.latitude || false,
                    longitude: location.longitude || false,
                    gps_accuracy: location.accuracy || null,
                    gps_timestamp: location.timestamp || Date.now(),
                    gps_enabled: location.success || false
                };

                // Log para debugging
                console.log("📤 Enviando datos:", payload);

                // Hacer la petición
                const response = await this.makeRequest(url, payload);
                
                if (response && !response.error) {
                    console.log("✅ Attendance registrado exitosamente");
                    this.showNotification("Attendance registrado con ubicación GPS", "success");
                    return response;
                } else {
                    throw new Error(response.error || "Error desconocido");
                }

            } catch (error) {
                console.error("❌ Error en attendance:", error);
                this.showNotification("Error al registrar attendance: " + error.message, "error");
                throw error;
            }
        },

        /**
         * Hace petición HTTP
         */
        async makeRequest(url, data) {
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
                             document.querySelector('input[name="csrf_token"]')?.value ||
                             this.getCookie('csrf_token');

            const headers = {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            };

            if (csrfToken) {
                headers['X-CSRF-TOKEN'] = csrfToken;
            }

            try {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify(data),
                    credentials: 'include'
                });

                if (!response.ok) {
                    throw new Error(`HTTP Error: ${response.status}`);
                }

                return await response.json();
            } catch (error) {
                console.error("Error en petición:", error);
                throw error;
            }
        },

        /**
         * Obtiene cookie por nombre
         */
        getCookie(name) {
            const value = `; ${document.cookie}`;
            const parts = value.split(`; ${name}=`);
            if (parts.length === 2) return parts.pop().split(';').shift();
            return null;
        },

        /**
         * Muestra notificación al usuario
         */
        showNotification(message, type = "info") {
            // Intentar usar el sistema de notificaciones de Odoo
            if (window.odoo && window.odoo.define) {
                try {
                    window.odoo.define('gps_notification', function(require) {
                        const Notification = require('web.Notification');
                        if (Notification) {
                            Notification.displayNotification({
                                title: type === "success" ? "Éxito" : "Error",
                                message: message,
                                type: type
                            });
                            return;
                        }
                    });
                } catch (e) {
                    // Fallback a notificación simple
                }
            }
            
            // Fallback: crear notificación personalizada
            this.createCustomNotification(message, type);
        },

        /**
         * Crea notificación visual personalizada
         */
        createCustomNotification(message, type) {
            const notification = document.createElement('div');
            notification.style.cssText = `
                position: fixed;
                top: 70px;
                right: 20px;
                background: ${type === 'success' ? '#28a745' : type === 'error' ? '#dc3545' : '#007bff'};
                color: white;
                padding: 15px 20px;
                border-radius: 5px;
                z-index: 10000;
                font-size: 14px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.3);
                max-width: 300px;
                animation: slideIn 0.3s ease;
            `;
            
            notification.innerHTML = `
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span>${type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'}</span>
                    <span>${message}</span>
                </div>
            `;

            document.body.appendChild(notification);

            // Remover después de 4 segundos
            setTimeout(() => {
                notification.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => notification.remove(), 300);
            }, 4000);
        }
    };

    // ============== INTERCEPTORES ==============

    /**
     * Intercepta clicks en botones de attendance
     */
    function setupClickInterceptor() {
        document.addEventListener('click', async function(event) {
            const target = event.target;
            
            // Detectar si es botón de attendance
            const isAttendanceButton = (
                target.classList.contains('o_attendance_sign_in_out_icon') ||
                target.closest('.o_attendance_sign_in_out_icon') ||
                target.classList.contains('o_systray_attendance') ||
                target.closest('.o_systray_attendance') ||
                target.getAttribute('data-action') === 'attendance' ||
                target.closest('[data-action="attendance"]') ||
                (target.textContent && (
                    target.textContent.toLowerCase().includes('check in') ||
                    target.textContent.toLowerCase().includes('check out') ||
                    target.textContent.toLowerCase().includes('marcar')
                ))
            );

            if (isAttendanceButton && !target.hasAttribute('data-gps-processing')) {
                console.log("🎯 Click en botón de attendance detectado");
                
                // Evitar múltiples procesamientos
                target.setAttribute('data-gps-processing', 'true');
                
                try {
                    // Capturar GPS inmediatamente
                    const location = await GPSAttendanceService.captureLocation();
                    
                    // Almacenar en el elemento para uso posterior
                    if (location.success) {
                        target.setAttribute('data-gps-lat', location.latitude);
                        target.setAttribute('data-gps-lon', location.longitude);
                        target.setAttribute('data-gps-accuracy', location.accuracy);
                        target.setAttribute('data-gps-timestamp', location.timestamp);
                        
                        console.log("📌 Datos GPS almacenados en el elemento");
                    }
                } finally {
                    // Remover flag después de un momento
                    setTimeout(() => {
                        target.removeAttribute('data-gps-processing');
                    }, 1000);
                }
            }
        }, true); // true = capture phase
    }

    /**
     * Intercepta envío de formularios
     */
    function setupFormInterceptor() {
        document.addEventListener('submit', async function(event) {
            const form = event.target;
            
            // Verificar si es formulario de attendance
            if (form.action && form.action.includes('attendance')) {
                console.log("📋 Formulario de attendance detectado");
                
                // Prevenir envío original
                event.preventDefault();
                
                try {
                    // Capturar ubicación
                    const location = await GPSAttendanceService.captureLocation();
                    
                    // Agregar campos GPS al formulario
                    if (location.success) {
                        ['latitude', 'longitude', 'gps_accuracy', 'gps_timestamp'].forEach(field => {
                            const existing = form.querySelector(`input[name="${field}"]`);
                            if (existing) existing.remove();
                        });
                        
                        const fields = {
                            latitude: location.latitude,
                            longitude: location.longitude,
                            gps_accuracy: location.accuracy,
                            gps_timestamp: location.timestamp
                        };
                        
                        Object.entries(fields).forEach(([name, value]) => {
                            const input = document.createElement('input');
                            input.type = 'hidden';
                            input.name = name;
                            input.value = value;
                            form.appendChild(input);
                        });
                        
                        console.log("📌 Campos GPS agregados al formulario");
                    }
                    
                    // Ahora sí enviar el formulario
                    form.submit();
                    
                } catch (error) {
                    console.error("Error al procesar formulario:", error);
                    // Enviar formulario sin GPS en caso de error
                    form.submit();
                }
            }
        });
    }

    /**
     * Intercepta RPC calls de Odoo
     */
    function setupRPCInterceptor() {
        // Esperar a que Odoo esté disponible
        let attempts = 0;
        const maxAttempts = 20;
        
        const checkOdoo = () => {
            attempts++;
            
            if (window.odoo && window.odoo.define) {
                console.log("🔧 Configurando interceptor RPC de Odoo");
                
                try {
                    window.odoo.define('gps_rpc_interceptor', function(require) {
                        const rpc = require('web.rpc');
                        if (rpc && rpc.query) {
                            const originalQuery = rpc.query;
                            
                            rpc.query = async function(params) {
                                // Interceptar llamadas de attendance
                                if (params.route && params.route.includes('attendance')) {
                                    console.log("🔗 Interceptando RPC de attendance");
                                    
                                    try {
                                        const location = await GPSAttendanceService.captureLocation();
                                        if (location.success) {
                                            params.latitude = location.latitude;
                                            params.longitude = location.longitude;
                                            params.gps_accuracy = location.accuracy;
                                            params.gps_timestamp = location.timestamp;
                                            console.log("📍 GPS agregado a RPC call");
                                        }
                                    } catch (error) {
                                        console.warn("Error al agregar GPS a RPC:", error);
                                    }
                                }
                                
                                return originalQuery.call(this, params);
                            };
                        }
                    });
                } catch (error) {
                    console.warn("Error configurando interceptor RPC:", error);
                }
                
            } else if (attempts < maxAttempts) {
                setTimeout(checkOdoo, 500);
            }
        };
        
        checkOdoo();
    }

    // ============== UTILIDADES GLOBALES ==============

    /**
     * Función global para uso manual
     */
    window.checkAttendanceWithGPS = async function() {
        try {
            return await GPSAttendanceService.sendAttendanceWithGPS();
        } catch (error) {
            console.error("Error en attendance manual:", error);
            throw error;
        }
    };

    /**
     * Servicio GPS disponible globalmente
     */
    window.GPSAttendanceService = GPSAttendanceService;

    // ============== INICIALIZACIÓN ==============

    function initialize() {
        console.log("🚀 Inicializando GPS Attendance Enhancement");
        
        // Configurar interceptores
        setupClickInterceptor();
        setupFormInterceptor();
        setupRPCInterceptor();
        
        // Configurar re-escaneo periódico para elementos dinámicos
        setInterval(() => {
            // Re-aplicar interceptores para contenido dinámico
            setupClickInterceptor();
        }, 5000);
        
        console.log("✅ GPS Attendance Enhancement inicializado correctamente");
        
        // Mostrar notificación de inicio (opcional)
        setTimeout(() => {
            GPSAttendanceService.showNotification("Sistema GPS para attendance activado", "success");
        }, 2000);
    }

    // ============== AUTO-INICIALIZACIÓN ==============

    // Ejecutar cuando el DOM esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize);
    } else {
        initialize();
    }

    // También ejecutar con delay para contenido dinámico
    setTimeout(initialize, 1000);
    setTimeout(initialize, 3000);

})();