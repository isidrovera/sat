/** @odoo-module */

import { registry } from '@web/core/registry';
import { Component, useState } from "@odoo/owl";

export class InspeccionForm extends Component {
    setup() {
        this.state = useState({
            loading: false,
            error: null,
            formData: {
                punto_corriente: 'no',
                punto_red: 'no',
                wifi: 'no',
                piso: '',
                espacio: '',
                ancho_pasillo: '',
                ascensor: false,
                observaciones: ''
            }
        });
    }

    onInputChange(event) {
        const { name, value, type, checked } = event.target;
        this.state.formData[name] = type === 'checkbox' ? checked : value;
    }

    async onSubmit(event) {
        event.preventDefault();
        if (this.state.loading) return;

        this.state.loading = true;
        this.state.error = null;

        try {
            const response = await fetch('/inspeccion/submit', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    ...this.state.formData,
                    token: this.props.token
                })
            });

            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.error || 'Error al enviar el formulario');
            }

            this.env.services.notification.add(
                this.env._t("Inspección enviada correctamente"),
                { type: "success" }
            );

            // Redirigir a página de confirmación
            setTimeout(() => {
                window.location.href = '/inspeccion/gracias';
            }, 1500);

        } catch (error) {
            this.state.error = error.message;
            this.env.services.notification.add(
                this.env._t("Error: ") + error.message,
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }
}

InspeccionForm.template = 'sat.InspeccionForm';
InspeccionForm.props = {
    token: String,
};

registry.category("web_components").add("inspeccion-form", InspeccionForm);