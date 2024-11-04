/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

class GalleryWidget extends Component {
    static template = "reparaciones.GalleryWidget";
    static components = { Dialog };
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.state = useState({
            selectedPhoto: null,
            isModalOpen: false
        });
        this.notification = useService("notification");
        this.orm = useService("orm");
    }

    get photos() {
        return this.props.value || [];
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
                await this.props.record.load();
                this.notification.add("Foto subida exitosamente", {
                    type: 'success',
                });
            } catch (error) {
                this.notification.add("Error al subir la foto", {
                    type: 'danger',
                });
            }
        };
        reader.readAsDataURL(file);
    }

    openPhotoModal(photo) {
        this.state.selectedPhoto = photo;
        this.state.isModalOpen = true;
    }

    closePhotoModal() {
        this.state.isModalOpen = false;
        this.state.selectedPhoto = null;
    }

    downloadPhoto(photo) {
        if (photo?.url_foto) {
            window.open(photo.url_foto, '_blank');
        } else {
            this.notification.add("URL de foto no disponible", {
                type: 'warning',
            });
        }
    }
}

registry.category("fields").add("gallery_widget", GalleryWidget);

export default GalleryWidget;