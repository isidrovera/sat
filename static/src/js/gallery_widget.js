/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { Field } from "@web/views/fields/field";

class GalleryWidget extends Field {
    static template = "reparaciones.GalleryWidget";
    static components = { Dialog };

    static props = {
        ...standardFieldProps,
        record: { type: Object },
        name: { type: String },
        update: { type: Function },
        readonly: { type: Boolean, optional: true },
    };

    static defaultProps = {
        readonly: false,
    };

    setup() {
        super.setup();
        this.state = useState({
            selectedPhoto: null,
            isModalOpen: false
        });
        this.notification = useService("notification");
        this.orm = useService("orm");
    }

    get photos() {
        // Asegurarse de que tenemos un array válido
        const value = this.props.record.data[this.props.name];
        return Array.isArray(value) ? value : [];
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
                console.error('Error al subir foto:', error);
                this.notification.add("Error al subir la foto", {
                    type: 'danger',
                });
            }
        };
        reader.readAsDataURL(file);
    }

    openPhotoModal(photo) {
        if (photo) {
            this.state.selectedPhoto = photo;
            this.state.isModalOpen = true;
        }
    }

    closePhotoModal() {
        this.state.isModalOpen = false;
        this.state.selectedPhoto = null;
    }

    downloadPhoto(photo, ev) {
        ev?.stopPropagation();
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