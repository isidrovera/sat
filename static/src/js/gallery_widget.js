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
            selectMode: false,
            error: null
        });
        this.notification = useService("notification");
        this.orm = useService("orm");

        onMounted(() => this.loadPhotos());
    }

    async loadPhotos() {
        console.log("Cargando fotos para record:", this.props.record.resId);
        try {
            this.state.isLoading = true;
            this.state.error = null;
            const result = await this.orm.call(
                'reparaciones.foto',
                'search_read',
                [[['reparacion_id', '=', this.props.record.resId]]],
                {
                    fields: ['id', 'nombre_foto', 'url_foto']
                }
            );
            console.log("Fotos obtenidas:", result);
            this.state.photos = result.map(photo => ({
                ...photo,
                imageUrl: `/web/image/reparaciones.foto/${photo.id}/foto_binario`
            }));
        } catch (error) {
            console.error('Error al cargar fotos:', error);
            this.state.error = "Error al cargar las fotos";
            this.notification.add(this.state.error, { type: 'danger' });
        } finally {
            this.state.isLoading = false;
        }
    }

    onPhotoClick(photo) {
        if (!this.state.selectMode) {
            this.openPhotoModal(photo);
        } else {
            this.togglePhotoSelection(photo);
        }
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

    toggleSelectMode() {
        this.state.selectMode = !this.state.selectMode;
        this.state.selectedPhotos.clear();
    }

    togglePhotoSelection(photo) {
        if (this.state.selectedPhotos.has(photo.id)) {
            this.state.selectedPhotos.delete(photo.id);
        } else {
            this.state.selectedPhotos.add(photo.id);
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

        // Esperar un poco antes de recargar las fotos
        setTimeout(() => this.loadPhotos(), 1000);
    }

    async downloadPhoto(photo, ev) {
        ev?.stopPropagation();
        try {
            window.open(`/web/content/reparaciones.foto/${photo.id}/foto_binario?download=true`, '_blank');
        } catch (error) {
            this.notification.add("Error al descargar la foto", { type: 'danger' });
        }
    }

    get hasPhotos() {
        return this.state.photos.length > 0;
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