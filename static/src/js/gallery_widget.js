
/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";
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
            selectedPhotos: new Map(),
            selectMode: false,
        });
        
        this.notification = useService("notification");
        this.orm = useService("orm");

        // Bindeamos los métodos para evitar errores de contexto
        this.uploadPhotos = this.uploadPhotos.bind(this);
        this.downloadPhoto = this.downloadPhoto.bind(this);
        this.toggleSelectMode = this.toggleSelectMode.bind(this);
        this.togglePhotoSelection = this.togglePhotoSelection.bind(this);
        this.openPhotoModal = this.openPhotoModal.bind(this);
        this.closePhotoModal = this.closePhotoModal.bind(this);
        this.downloadSelectedPhotos = this.downloadSelectedPhotos.bind(this);

        onWillStart(async () => {
            await this.loadPhotos();
        });
    }

    async loadPhotos() {
        try {
            this.state.isLoading = true;
            const photos = await this.orm.call(
                'reparaciones.foto',
                'get_photos_preview',
                [[this.props.record.resId]]
            );
            this.state.photos = photos || [];
        } catch (error) {
            console.error('Error al cargar fotos:', error);
            this.notification.add("Error al cargar las fotos", {
                type: 'danger',
            });
        } finally {
            this.state.isLoading = false;
        }
    }

    async uploadPhotos(ev) {
        const files = Array.from(ev.target.files || []);
        if (!files.length) return;

        for (const file of files) {
            try {
                const reader = new FileReader();
                await new Promise((resolve, reject) => {
                    reader.onload = async (e) => {
                        try {
                            await this.orm.create(
                                'reparaciones.foto',
                                [{
                                    nombre_foto: file.name,
                                    foto_binario: e.target.result.split(',')[1],
                                    reparacion_id: this.props.record.resId,
                                }]
                            );
                            resolve();
                        } catch (error) {
                            reject(error);
                        }
                    };
                    reader.onerror = reject;
                    reader.readAsDataURL(file);
                });
            } catch (error) {
                console.error(`Error al subir ${file.name}:`, error);
                this.notification.add(`Error al subir ${file.name}`, {
                    type: 'danger',
                });
            }
        }

        // Recargar las fotos después de subir
        await this.loadPhotos();
        // Limpiar el input
        ev.target.value = '';
    }

    toggleSelectMode() {
        this.state.selectMode = !this.state.selectMode;
        this.state.selectedPhotos.clear();
    }

    togglePhotoSelection(photo, ev) {
        ev?.stopPropagation();
        if (this.state.selectedPhotos.has(photo.id)) {
            this.state.selectedPhotos.delete(photo.id);
        } else {
            this.state.selectedPhotos.set(photo.id, photo);
        }
    }

    openPhotoModal(photo) {
        if (this.state.selectMode) {
            this.togglePhotoSelection(photo);
        } else {
            this.state.selectedPhoto = photo;
            this.state.isModalOpen = true;
        }
    }

    closePhotoModal() {
        this.state.isModalOpen = false;
        this.state.selectedPhoto = null;
    }

    async downloadPhoto(photo, ev) {
        ev?.stopPropagation();
        try {
            if (photo?.download_url) {
                window.open(photo.download_url, '_blank');
            }
        } catch (error) {
            console.error('Error al descargar foto:', error);
            this.notification.add("Error al descargar la foto", {
                type: 'danger',
            });
        }
    }

    async downloadSelectedPhotos() {
        if (this.state.selectedPhotos.size === 0) {
            this.notification.add("Selecciona al menos una foto", {
                type: 'warning',
            });
            return;
        }

        try {
            const selectedIds = Array.from(this.state.selectedPhotos.keys());
            const result = await this.orm.call(
                'reparaciones.foto',
                'get_photos_zip',
                [selectedIds]
            );

            if (result && result.content) {
                const blob = new Blob([atob(result.content)], { type: 'application/zip' });
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = 'fotos_seleccionadas.zip';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                window.URL.revokeObjectURL(url);
                this.toggleSelectMode();
            }
        } catch (error) {
            console.error('Error al descargar fotos:', error);
            this.notification.add("Error al descargar las fotos", {
                type: 'danger',
            });
        }
    }

    get hasPhotos() {
        return this.state.photos.length > 0;
    }

    get selectedCount() {
        return this.state.selectedPhotos.size;
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
