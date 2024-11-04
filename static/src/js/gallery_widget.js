/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { Field } from "@web/views/fields/field";

class GalleryWidget extends Field {
    static template = "reparaciones.GalleryWidget";
    static components = { Dialog };

    setup() {
        super.setup();
        this.state = useState({
            selectedPhoto: null,
            isModalOpen: false,
            isLoading: true,
            photos: [],
            selectedPhotos: new Set(),
            selectMode: false,
            error: null
        });
        this.notification = useService("notification");
        this.orm = useService("orm");

        onMounted(() => this.loadPhotos());
    }

    async loadPhotos() {
        console.log("Iniciando carga de fotos");
        try {
            this.state.isLoading = true;
            const photos = await this.orm.call(
                'reparaciones.foto',
                'get_photos_preview',
                [[this.props.record.resId]]
            );
            console.log("Fotos obtenidas:", photos);
            this.state.photos = photos || [];
        } catch (error) {
            console.error('Error al cargar fotos:', error);
            this.state.error = error.message || "Error al cargar las fotos";
            this.notification.add(this.state.error, {
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

    async uploadPhoto(ev) {
        const files = Array.from(ev.target.files || []);
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

        // Recargar fotos después de la subida
        await this.loadPhotos();
    }

    async downloadPhoto(photo, ev) {
        if (!photo?.url_foto) return;
        ev?.stopPropagation();
        window.open(photo.url_foto, '_blank');
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

    get hasPhotos() {
        return this.state.photos && this.state.photos.length > 0;
    }

    get debugInfo() {
        return {
            totalPhotos: this.state.photos.length,
            selectedCount: this.state.selectedPhotos.size,
            error: this.state.error,
            loading: this.state.isLoading,
            recordId: this.props.record.resId,
        };
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