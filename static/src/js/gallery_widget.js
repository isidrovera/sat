/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

class GalleryWidget extends Component {
    static template = "reparaciones.GalleryWidget";
    static components = { Dialog };

    setup() {
        this.state = useState({
            selectedPhoto: null,
            isModalOpen: false
        });
        this.notification = useService("notification");
        this.orm = useService("orm");
    }

    get photos() {
        // Asegurarse de que estamos obteniendo el array de fotos correctamente
        return this.props.record.data[this.props.name] || [];
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
                // Recargar el registro para actualizar la lista de fotos
                await this.props.record.load();
                this.notification.add("Foto subida exitosamente", {
                    type: 'success',
                });
            } catch (error) {
                console.error('Error al subir foto:', error);
                this.notification.add("Error al subir la foto", {
                    type: 'danger',
                });
            }
        };
        reader.readAsDataURL(file);
    }

    downloadPhoto(photo, ev) {
        ev?.stopPropagation();
        if (photo?.url_foto) {
            window.open(`/web/content/reparaciones.foto/${photo.id}/url_foto?download=true`, '_blank');
        } else {
            this.notification.add("URL de foto no disponible", {
                type: 'warning',
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
}

export const galleryWidget = {
    component: GalleryWidget,
    supportedTypes: ['one2many', 'many2many'],
    extractProps: ({ attrs, field }) => ({
        name: field.name,
        record: field.record,
        readonly: attrs.readonly === "1" || attrs.readonly === true,
    }),
};

registry.category("fields").add("gallery_widget", galleryWidget);