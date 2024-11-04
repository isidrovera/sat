/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

class GalleryWidget extends Component {
    static template = "reparaciones.GalleryWidget";
    static components = { Dialog };

    setup() {
        this.state = useState({
            selectedPhoto: null,
            isModalOpen: false,
            isLoading: true,
            photos: [],
            selectedPhotos: new Set(),
            selectMode: false
        });
        this.notification = useService("notification");
        this.orm = useService("orm");

        onMounted(() => this.loadPhotos());
    }

    async loadPhotos() {
        try {
            this.state.isLoading = true;
            const photos = await this.orm.call(
                'reparaciones.reparaciones',
                'get_photos_with_preview',
                [[this.props.record.resId]]
            );
            this.state.photos = photos;
        } catch (error) {
            console.error('Error al cargar fotos:', error);
            this.notification.add("Error al cargar las fotos", {
                type: 'danger',
            });
        } finally {
            this.state.isLoading = false;
        }
    }

    toggleSelectMode() {
        this.state.selectMode = !this.state.selectMode;
        if (!this.state.selectMode) {
            this.state.selectedPhotos.clear();
        }
    }

    togglePhotoSelection(photo, ev) {
        ev.stopPropagation();
        if (this.state.selectedPhotos.has(photo.id)) {
            this.state.selectedPhotos.delete(photo.id);
        } else {
            this.state.selectedPhotos.add(photo.id);
        }
    }

    selectAll() {
        if (this.state.selectedPhotos.size === this.state.photos.length) {
            this.state.selectedPhotos.clear();
        } else {
            this.state.selectedPhotos = new Set(this.state.photos.map(p => p.id));
        }
    }

    async uploadPhoto(ev) {
        const files = ev.target.files;
        if (!files.length) return;

        for (const file of files) {
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
                } catch (error) {
                    console.error('Error al subir foto:', error);
                    this.notification.add(`Error al subir ${file.name}`, {
                        type: 'danger',
                    });
                }
            };
            reader.readAsDataURL(file);
        }

        // Recargar todas las fotos después de subir
        await this.loadPhotos();
        this.notification.add("Fotos subidas exitosamente", {
            type: 'success',
        });
    }

    openPhotoModal(photo) {
        if (!this.state.selectMode && photo) {
            this.state.selectedPhoto = photo;
            this.state.isModalOpen = true;
        }
    }

    closePhotoModal() {
        this.state.isModalOpen = false;
        this.state.selectedPhoto = null;
    }

    async downloadSelectedPhotos() {
        if (this.state.selectedPhotos.size === 0) {
            this.notification.add("Selecciona al menos una foto", {
                type: 'warning',
            });
            return;
        }

        try {
            const zipUrl = await this.orm.call(
                'reparaciones.foto',
                'get_photos_zip',
                [[...this.state.selectedPhotos]]
            );
            if (zipUrl) {
                window.open(zipUrl, '_blank');
                this.state.selectMode = false;
                this.state.selectedPhotos.clear();
            } else {
                this.notification.add("Error al crear el archivo ZIP", {
                    type: 'warning',
                });
            }
        } catch (error) {
            this.notification.add("Error al descargar las fotos", {
                type: 'danger',
            });
        }
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