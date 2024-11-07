/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { ButtonBox } from "@web/views/form/button_box/button_box";

class GeolocationService {
    constructor() {
        this.options = {
            enableHighAccuracy: true,
            timeout: 5000,
            maximumAge: 0
        };
    }

    checkGeolocationSupport() {
        if (!navigator.geolocation) {
            throw new Error(_t('Geolocalización no soportada en su navegador'));
        }
        return true;
    }

    handleGeolocationError(error) {
        let errorMessage;
        switch (error.code) {
            case error.PERMISSION_DENIED:
                errorMessage = _t("Usuario denegó el permiso de ubicación");
                break;
            case error.POSITION_UNAVAILABLE:
                errorMessage = _t("Información de ubicación no disponible");
                break;
            case error.TIMEOUT:
                errorMessage = _t("Tiempo de espera agotado para obtener la ubicación");
                break;
            default:
                errorMessage = _t("Error desconocido al obtener la ubicación");
        }
        throw new Error(errorMessage);
    }

    async getCurrentPosition() {
        this.checkGeolocationSupport();

        return new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    resolve({
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                        accuracy: position.coords.accuracy
                    });
                },
                (error) => {
                    reject(this.handleGeolocationError(error));
                },
                this.options
            );
        });
    }
}

patch(ButtonBox, {
    setup() {
        super.setup();
        this.notification = this.env.services.notification;
        this.geolocationService = new GeolocationService();
    },

    async _onButtonClick(ev) {
        const buttonName = ev.target.getAttribute('name');
        if (buttonName === 'action_finalizar') {
            try {
                // Intentar obtener la ubicación antes de finalizar
                const position = await this.geolocationService.getCurrentPosition();
                
                // Agregar las coordenadas al contexto
                this.env.searchModel.dispatch('updateContext', {
                    additionalContext: {
                        finish_latitude: position.latitude,
                        finish_longitude: position.longitude,
                        finish_datetime: moment().format('YYYY-MM-DD HH:mm:ss')
                    },
                });

                // Mostrar notificación de éxito
                this.notification.add(
                    _t("Ubicación capturada correctamente"),
                    {
                        type: 'success',
                        sticky: false,
                        buttons: [{
                            name: _t("Ver en Google Maps"),
                            onClick: () => {
                                window.open(
                                    `https://www.google.com/maps?q=${position.latitude},${position.longitude}`,
                                    '_blank'
                                );
                            },
                        }],
                    }
                );
            } catch (error) {
                // Mostrar error pero permitir continuar
                this.notification.add(error.message, {
                    type: 'warning',
                    sticky: true,
                    message: _t("El ticket se finalizará sin registrar la ubicación"),
                });
            }
        }
        return super._onButtonClick(...arguments);
    },
});