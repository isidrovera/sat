/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * Widget para galería de fotos de reparaciones
 */
class ReparacionFotoGallery extends Component {
    setup() {
        this.state = useState({
            selectedPhoto: null,
            isModalOpen: false,
        });
        this.action = useService("action");
        this.notification = useService("notification");
        this.orm = useService("orm");
    }

    async downloadPhoto(photo) {
        try {
            if (photo.url_foto) {
                window.open(photo.url_foto, '_blank');
            } else {
                this.notification.add(this.env._t("URL de foto no disponible"), {
                    type: 'warning',
                });
            }
        } catch (error) {
            this.notification.add(this.env._t("Error al descargar la foto"), {
                type: 'danger',
            });
        }
    }

    openPhotoModal(photo) {
        this.state.selectedPhoto = photo;
        this.state.isModalOpen = true;
    }

    closePhotoModal() {
        this.state.isModalOpen = false;
        this.state.selectedPhoto = null;
    }

    async uploadPhoto(ev) {
        const file = ev.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async (e) => {
            const base64Data = e.target.result.split(',')[1];
            try {
                await this.orm.create(
                    'reparaciones.foto',
                    [{
                        nombre_foto: file.name,
                        foto_binario: base64Data,
                        reparacion_id: this.props.record.resId,
                    }]
                );
                // Recargar el record
                await this.props.record.load();
                this.notification.add(this.env._t("Foto subida correctamente"), {
                    type: 'success',
                });
            } catch (error) {
                this.notification.add(this.env._t("Error al subir la foto"), {
                    type: 'danger',
                });
            }
        };
        reader.readAsDataURL(file);
    }
}

ReparacionFotoGallery.template = 'reparaciones.PhotoGallery';
ReparacionFotoGallery.props = {
    ...standardFieldProps,
};

// Registrar el widget
registry.category("fields").add("reparacion_foto_gallery", ReparacionFotoGallery);